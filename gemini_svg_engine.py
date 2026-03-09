"""
gemini_svg_engine.py — Vectrod Gemini SVG Pipeline
====================================================
1. Kullanıcı prompt → Gemini'ye gönder
2. Gemini her harf için SVG path üretir (JSON formatında)
3. Biz SVG dosyası oluştururuz (engine.py formatında)
4. engine.py ile TTF/OTF yaparız
5. Kullanıcıya sunarız
"""

import os, json, re, math, time, tempfile, shutil
import urllib.request, urllib.error

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
CHARS_UPPERCASE = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
CHARS_LOWERCASE = list('abcdefghijklmnopqrstuvwxyz')
CHARS_DIGITS    = list('0123456789')
CHARS_PUNCT     = list('.,!?;:\'"()-_/@#$%&*+=')

ALL_CHARS = CHARS_UPPERCASE + CHARS_LOWERCASE + CHARS_DIGITS + CHARS_PUNCT

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# SVG canvas size per glyph (must match engine.py expectations)
CANVAS = 200   # her harf 200x200 canvas'ta çizilir
SPACING = 220  # gruplar arası mesafe


# ── GEMINI PROMPT ─────────────────────────────────────────────────────────────
def build_gemini_prompt(user_prompt: str, chars: list) -> str:
    chars_str = ', '.join([repr(c) for c in chars])
    n = len(chars)
    return (
        f'You are an SVG font designer. Font style: "{user_prompt}"\n\n'
        f'Generate SVG paths for {n} characters: {chars_str}\n\n'
        'Canvas: 200x200. Uppercase/digits: y=10 (top) to y=170 (baseline). '
        'Lowercase: y=60 (top) to y=170 (baseline).\n'
        'Paths must be filled, closed (Z), use only M L C Q Z commands.\n\n'
        'Example for letter A:\n'
        '"A": "M100,10 L160,170 L140,170 L100,50 L60,170 L40,170 Z M70,120 L130,120 L120,140 L80,140 Z"\n\n'
        'Return ONLY raw JSON, no markdown, no explanation:\n'
        '{"style_name": "name", "chars": {"A": "path", "B": "path", ...}}\n\n'
        f'Include all {n} characters. Make each letter readable and beautiful.'
    )


# ── GEMINI API CALL ───────────────────────────────────────────────────────────
def call_gemini(prompt: str, api_key: str, retries: int = 3) -> dict:
    """Call Gemini API, return parsed JSON response."""
    url = f"{GEMINI_URL}?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 65536}
    }).encode('utf-8')
    headers = {"Content-Type": "application/json", "User-Agent": "Vectrod/3.0"}

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode('utf-8')
            data = json.loads(raw)
            print(f"  [Gemini] keys: {list(data.keys())}")

            if 'candidates' not in data or not data['candidates']:
                print(f"  [Gemini] no candidates. response: {raw[:400]}")
                raise RuntimeError("Gemini returned no candidates")

            cand = data['candidates'][0]
            if 'content' not in cand:
                finish = cand.get('finishReason', '?')
                raise RuntimeError(f"Gemini no content, finishReason={finish}")

            text = ''.join(p.get('text','') for p in cand['content'].get('parts',[])).strip()
            print(f"  [Gemini] response length: {len(text)}")

            if not text:
                raise RuntimeError("Gemini empty text")

            if text.startswith('`'):
                text = re.sub(r'^```[a-z]*\n?', '', text)
                text = re.sub(r'```$', '', text).strip()

            s, e = text.find('{'), text.rfind('}')
            if s == -1 or e == -1:
                raise RuntimeError(f"No JSON object in response: {text[:200]}")

            result = json.loads(text[s:e+1])
            print(f"  [Gemini] parsed OK — {len(result.get('chars',{}))} chars")
            return result

        except urllib.error.HTTPError as ex:
            body = ex.read().decode('utf-8', errors='replace')
            print(f"  [Gemini] HTTP {ex.code}: {body[:300]}")
            if ex.code in (429, 503) and attempt < retries-1:
                time.sleep(8*(attempt+1))
                continue
            raise
        except (json.JSONDecodeError, RuntimeError) as ex:
            print(f"  [Gemini] attempt {attempt+1}: {ex}")
            if attempt < retries-1:
                time.sleep(4)
                continue
            raise
        except Exception as ex:
            print(f"  [Gemini] unexpected attempt {attempt+1}: {ex}")
            if attempt < retries-1:
                time.sleep(3)
                continue
            raise

    raise RuntimeError("Gemini API failed after all retries")

# ── SVG ASSEMBLER ──────────────────────────────────────────────────────────────
def assemble_svg(char_paths: dict, chars_order: list) -> str:
    """
    Assemble individual char paths into one SVG file
    matching engine.py's expected format:
    - Each char in its own <g translate(x,0)> group
    - Left-to-right layout
    """
    cols = 13  # chars per row
    groups = []

    for i, ch in enumerate(chars_order):
        if ch not in char_paths:
            continue

        path_d = char_paths[ch].strip()
        if not path_d:
            continue

        col = i % cols
        row = i // cols
        tx = col * SPACING
        ty = row * SPACING

        safe_ch = ch.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        groups.append(
            f'  <g transform="translate({tx},{ty})" data-char="{safe_ch}">\n'
            f'    <path d="{path_d}" fill="#000"/>\n'
            f'  </g>'
        )

    total_cols = min(len(chars_order), cols)
    total_rows = math.ceil(len(chars_order) / cols)
    width  = total_cols * SPACING
    height = total_rows * SPACING

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">\n'
        + '\n'.join(groups)
        + '\n</svg>'
    )
    return svg


# ── PATH VALIDATOR & FIXER ─────────────────────────────────────────────────────
def validate_path(path_d: str, char: str) -> str:
    """Basic validation — ensure path ends with Z, has reasonable content."""
    if not path_d:
        return _fallback_path(char)

    # Must have M command
    if 'M' not in path_d and 'm' not in path_d:
        return _fallback_path(char)

    # Ensure closed
    if not path_d.strip().upper().endswith('Z'):
        path_d = path_d.strip() + ' Z'

    return path_d


# Proper geometric fallback — real letter shapes, not rectangles
_FALLBACK = {
    'A':'M100,10 L160,170 L140,170 L100,55 L60,170 L40,170 Z M72,122 L128,122 L118,142 L82,142 Z',
    'B':'M40,10 L40,170 L110,170 C148,170 165,150 165,128 C165,108 150,98 128,95 C150,92 163,80 163,58 C163,30 145,10 108,10 Z M65,100 L65,148 L108,148 C128,148 138,138 138,126 C138,113 128,100 108,100 Z M65,32 L65,80 L105,80 C123,80 135,70 135,56 C135,42 124,32 105,32 Z',
    'C':'M160,38 C142,12 58,12 40,52 C28,78 28,122 40,148 C58,188 142,188 160,162 L138,148 C126,165 74,165 62,145 C52,128 52,72 62,55 C74,35 126,35 138,52 Z',
    'D':'M40,10 L40,170 L100,170 C155,170 175,138 175,90 C175,42 155,10 100,10 Z M65,32 L65,148 L100,148 C138,148 150,126 150,90 C150,54 138,32 100,32 Z',
    'E':'M40,10 L40,170 L165,170 L165,145 L65,145 L65,102 L150,102 L150,78 L65,78 L65,35 L165,35 L165,10 Z',
    'F':'M40,10 L40,170 L65,170 L65,102 L148,102 L148,78 L65,78 L65,35 L162,35 L162,10 Z',
    'G':'M162,38 C144,12 58,12 40,52 C28,78 28,122 40,148 C58,188 144,188 162,155 L162,90 L105,90 L105,112 L138,112 L138,148 C126,165 74,165 62,145 C52,128 52,72 62,55 C74,35 126,35 138,52 Z',
    'H':'M40,10 L40,170 L65,170 L65,102 L135,102 L135,170 L160,170 L160,10 L135,10 L135,78 L65,78 L65,10 Z',
    'I':'M78,10 L78,170 L122,170 L122,10 Z',
    'J':'M60,10 L60,132 C60,148 72,162 95,162 C118,162 130,148 130,132 L130,10 L105,10 L105,130 C105,138 101,142 95,142 C89,142 85,138 85,130 L85,10 Z',
    'K':'M40,10 L40,170 L65,170 L65,102 L135,170 L165,170 L88,90 L160,10 L130,10 L65,78 L65,10 Z',
    'L':'M40,10 L40,170 L165,170 L165,145 L65,145 L65,10 Z',
    'M':'M30,10 L30,170 L55,170 L55,55 L100,130 L145,55 L145,170 L170,170 L170,10 L145,10 L100,82 L55,10 Z',
    'N':'M40,10 L40,170 L65,170 L65,55 L135,170 L160,170 L160,10 L135,10 L135,125 L65,10 Z',
    'O':'M100,10 C60,10 30,42 30,90 C30,138 60,170 100,170 C140,170 170,138 170,90 C170,42 140,10 100,10 Z M100,35 C125,35 145,60 145,90 C145,120 125,145 100,145 C75,145 55,120 55,90 C55,60 75,35 100,35 Z',
    'P':'M40,10 L40,170 L65,170 L65,108 L108,108 C145,108 165,88 165,58 C165,28 145,10 108,10 Z M65,32 L65,86 L108,86 C128,86 140,75 140,58 C140,42 128,32 108,32 Z',
    'Q':'M100,10 C60,10 30,42 30,90 C30,138 60,168 100,168 L115,185 L132,168 C148,155 170,128 170,90 C170,42 140,10 100,10 Z M100,35 C125,35 145,60 145,90 C145,115 132,135 115,145 L102,128 L85,145 C70,135 55,115 55,90 C55,60 75,35 100,35 Z',
    'R':'M40,10 L40,170 L65,170 L65,108 L108,108 L145,170 L175,170 L135,105 C152,95 165,78 165,58 C165,28 145,10 108,10 Z M65,32 L65,86 L108,86 C128,86 140,75 140,58 C140,42 128,32 108,32 Z',
    'S':'M155,35 C138,12 62,12 45,40 C32,62 42,85 65,98 L115,120 C132,128 138,138 130,152 C120,168 78,168 62,150 L40,165 C58,188 142,190 160,162 C174,140 165,115 140,102 L90,80 C74,72 66,62 74,48 C84,32 118,32 135,48 Z',
    'T':'M15,10 L15,35 L88,35 L88,170 L112,170 L112,35 L185,35 L185,10 Z',
    'U':'M40,10 L40,128 C40,152 65,172 100,172 C135,172 160,152 160,128 L160,10 L135,10 L135,126 C135,140 120,150 100,150 C80,150 65,140 65,126 L65,10 Z',
    'V':'M20,10 L80,170 L100,170 L120,170 L180,10 L155,10 L100,148 L45,10 Z',
    'W':'M10,10 L50,170 L75,170 L100,80 L125,170 L150,170 L190,10 L165,10 L138,130 L112,10 L88,10 L62,130 L35,10 Z',
    'X':'M30,10 L85,90 L30,170 L58,170 L100,110 L142,170 L170,170 L115,90 L170,10 L142,10 L100,70 L58,10 Z',
    'Y':'M20,10 L88,100 L88,170 L112,170 L112,100 L180,10 L152,10 L100,78 L48,10 Z',
    'Z':'M35,10 L35,35 L142,35 L35,148 L35,170 L165,170 L165,145 L58,145 L165,32 L165,10 Z',
    '0':'M100,10 C60,10 30,42 30,90 C30,138 60,170 100,170 C140,170 170,138 170,90 C170,42 140,10 100,10 Z M100,35 C125,35 145,60 145,90 C145,120 125,145 100,145 C75,145 55,120 55,90 C55,60 75,35 100,35 Z',
    '1':'M70,10 L100,10 L100,170 L125,170 L125,10 L70,45 Z',
    '2':'M45,52 C45,25 65,10 100,10 C135,10 155,28 155,55 C155,78 140,95 118,112 L50,165 L155,165 L155,145 L88,145 L135,110 C158,90 175,72 175,52 C175,22 152,10 100,10 C55,10 22,28 22,58 Z',
    '3':'M48,38 C62,12 138,12 152,42 C162,65 150,85 125,95 C152,105 165,128 155,152 C140,185 58,185 45,158 L68,145 C78,162 122,162 132,145 C142,128 130,112 108,108 L85,108 L85,85 L108,85 C128,85 138,70 132,55 C125,40 78,40 68,55 Z',
    '4':'M130,10 L40,122 L40,142 L130,142 L130,170 L155,170 L155,142 L175,142 L175,118 L155,118 L155,10 Z M118,118 L65,118 L118,52 Z',
    '5':'M150,10 L55,10 L45,90 L68,78 C80,70 92,68 100,68 C125,68 142,85 142,108 C142,132 125,148 100,148 C80,148 64,135 56,118 L32,130 C44,162 70,172 100,172 C142,172 168,148 168,108 C168,68 145,48 108,48 C97,48 84,52 74,58 L80,35 L150,35 Z',
    '6':'M148,38 C132,12 68,12 50,50 C36,80 36,125 50,150 C65,178 135,178 150,150 C162,125 158,95 138,80 C118,65 80,68 64,85 C65,60 76,36 100,33 C118,30 132,40 142,55 Z M100,145 C80,145 64,130 64,108 C64,86 80,70 100,70 C120,70 136,86 136,108 C136,130 120,145 100,145 Z',
    '7':'M28,10 L28,35 L135,35 L65,170 L92,170 L168,28 L168,10 Z',
    '8':'M100,10 C68,10 42,28 42,55 C42,75 55,90 75,98 C52,108 35,126 35,150 C35,165 48,172 100,172 C152,172 165,165 165,150 C165,126 148,108 125,98 C145,90 158,75 158,55 C158,28 132,10 100,10 Z M100,32 C118,32 130,42 130,55 C130,68 118,78 100,78 C82,78 70,68 70,55 C70,42 82,32 100,32 Z M100,100 C120,100 138,112 138,128 C138,145 120,152 100,152 C80,152 62,145 62,128 C62,112 80,100 100,100 Z',
    '9':'M150,32 C135,5 65,5 50,35 C36,62 42,95 62,110 C82,125 120,122 136,108 C136,128 126,152 100,155 C82,158 68,148 58,135 L35,148 C52,178 148,178 162,140 C175,108 170,72 160,45 Z M100,32 C120,32 136,48 136,72 C136,95 120,110 100,110 C80,110 64,95 64,72 C64,48 80,32 100,32 Z',
}

def _fallback_path(char: str) -> str:
    """Geometric fallback — real letter shapes."""
    if char in _FALLBACK:
        return _FALLBACK[char]
    # For lowercase: scale uppercase
    up = char.upper()
    if up in _FALLBACK:
        return _scale_path_for_lowercase(_FALLBACK[up])
    # Unknown char: simple rectangle
    return "M40,10 L160,10 L160,170 L40,170 Z"


# ── CHAR ORDER FOR ENGINE ──────────────────────────────────────────────────────
def get_char_order_from_paths(char_paths: dict) -> list:
    """Return chars in engine.py's expected order."""
    from engine import DEFAULT_CHAR_ORDER
    order = []
    for ch in DEFAULT_CHAR_ORDER:
        if ch in char_paths:
            order.append(ch)
    return order


# ── MAIN PIPELINE ──────────────────────────────────────────────────────────────
def build_from_prompt(
    prompt: str,
    font_name: str,
    output_dir: str,
    gemini_key: str = '',
) -> tuple:
    """
    Main entry point.
    Returns: (ttf_path, otf_path, glyph_svgs_dict, style_info)
    """
    os.makedirs(output_dir, exist_ok=True)

    # Which chars to generate
    target_chars = CHARS_UPPERCASE + CHARS_LOWERCASE + CHARS_DIGITS

    print(f"\n[GeminiSVG] prompt=\"{prompt[:60]}\"")
    print(f"[GeminiSVG] target={len(target_chars)} chars")

    char_paths = {}
    style_name = "custom"

    if gemini_key:
        # 4 small batches — more reliable than 2 large ones
        batches = [
            ('A-M+digits', list('ABCDEFGHIJKLM') + CHARS_DIGITS),
            ('N-Z',        list('NOPQRSTUVWXYZ')),
            ('a-m',        list('abcdefghijklm')),
            ('n-z',        list('nopqrstuvwxyz')),
        ]
        for bname, bchars in batches:
            print(f"[GeminiSVG] Batch {bname}: {len(bchars)} chars...")
            try:
                p = build_gemini_prompt(prompt, bchars)
                r = call_gemini(p, gemini_key)
                if style_name == 'custom':
                    style_name = r.get('style_name', 'custom')
                got = r.get('chars', {})
                for ch, d in got.items():
                    char_paths[ch] = validate_path(d, ch)
                print(f"  [GeminiSVG] got {len(got)} chars")
            except Exception as e:
                print(f"  [GeminiSVG] Batch {bname} FAILED: {e}")
                # For lowercase batches, derive from uppercase
                if bname in ('a-m', 'n-z'):
                    for ch in bchars:
                        if ch not in char_paths:
                            up = ch.upper()
                            if up in char_paths:
                                char_paths[ch] = _scale_path_for_lowercase(char_paths[up])


    else:
        print("[GeminiSVG] No API key — using geometric fallback")
        char_paths = _geometric_fallback(target_chars)

    # If Gemini totally failed, use geometric fallback so user gets SOMETHING
    if not char_paths:
        print("[GeminiSVG] WARNING: Gemini returned nothing — using geometric fallback")
        char_paths = _geometric_fallback(target_chars)

    if not char_paths:
        raise RuntimeError("No character paths generated")

    print(f"[GeminiSVG] Total chars: {len(char_paths)}")

    # ── STEP 3: Assemble SVG ───────────────────────────────────────────
    char_order = get_char_order_from_paths(char_paths)
    svg_content = assemble_svg(char_paths, char_order)

    svg_path = os.path.join(output_dir, f"{font_name}_glyphs.svg")
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    print(f"[GeminiSVG] SVG assembled: {len(svg_content)} bytes")

    # ── STEP 4: Build TTF via engine.py ───────────────────────────────
    from engine import build_font, DEFAULT_CHAR_ORDER
    print("[GeminiSVG] Building TTF...")
    ttf_path, otf_path = build_font(
        svg_file   = svg_path,
        font_name  = font_name,
        output_dir = output_dir,
        char_order = char_order,
    )

    if not ttf_path or not os.path.exists(ttf_path):
        raise RuntimeError("engine.py failed to build TTF")

    print(f"[GeminiSVG] ✅ TTF: {ttf_path}")

    # ── STEP 5: Glyph SVGs for preview ────────────────────────────────
    glyph_svgs = {}
    for ch, d in char_paths.items():
        glyph_svgs[ch] = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
            f'<path d="{d}" fill="#333"/>'
            f'</svg>'
        )

    style_info = {
        'style_name':  style_name,
        'engine':      'gemini-svg',
        'char_count':  len(char_paths),
        '_otf_path':   otf_path,
    }

    return ttf_path, style_info, glyph_svgs


# ── LOWERCASE SCALE HELPER ────────────────────────────────────────────────────
def _scale_path_for_lowercase(path_d: str) -> str:
    """
    Scale uppercase path to lowercase proportions.
    Uppercase: 10→170 (160px tall, baseline 170)
    Lowercase: 60→170 (110px tall, baseline 170)
    Scale Y by 110/160 = 0.6875, translate to fit
    """
    import re
    sy = 110 / 160
    # We keep baseline at 170, scale from bottom
    # y_new = 170 - (170 - y_old) * sy = 170 - 170*sy + y_old*sy
    # y_new = y_old * 0.6875 + 52.5
    offset_y = 170 * (1 - sy)  # ~52.5

    def transform_coord(x_str, y_str):
        try:
            y = float(y_str)
            y_new = y * sy + offset_y
            return x_str, f"{y_new:.1f}"
        except:
            return x_str, y_str

    # Parse and transform all coordinate pairs
    tokens = re.findall(r'[MCLCSQZz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', path_d)
    result = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in 'ML':
            result.append(t); i += 1
            while i < len(tokens) and tokens[i] not in 'MCLCSQZz':
                if i+1 < len(tokens) and tokens[i+1] not in 'MCLCSQZz':
                    x, y = transform_coord(tokens[i], tokens[i+1])
                    result.append(f"{tokens[i]},{y}")
                    i += 2
                else:
                    result.append(tokens[i]); i += 1
        elif t == 'C':
            result.append('C'); i += 1
            while i < len(tokens) and tokens[i] not in 'MCLCSQZz':
                if i+1 < len(tokens) and tokens[i+1] not in 'MCLCSQZz':
                    x, y = transform_coord(tokens[i], tokens[i+1])
                    result.append(f"{tokens[i]},{y}")
                    i += 2
                else:
                    result.append(tokens[i]); i += 1
        elif t in 'Zz':
            result.append('Z'); i += 1
        else:
            result.append(t); i += 1

    return ' '.join(result)


# ── GEOMETRIC FALLBACK (no API key) ───────────────────────────────────────────
def _geometric_fallback(chars: list) -> dict:
    """Very basic geometric font as fallback when no API key."""
    paths = {}
    for ch in chars:
        paths[ch] = _fallback_path(ch)
    return paths
