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
    chars_str = ', '.join([f'"{c}"' for c in chars])
    return f"""You are a professional type designer and SVG expert. Create a complete font based on this style description:

STYLE: "{user_prompt}"

Generate SVG paths for EXACTLY these {len(chars)} characters: {chars_str}

CRITICAL REQUIREMENTS:
1. Each character must be a FILLED SVG path (not stroked)
2. Each path must fit within a 200x200 coordinate space (0,0 top-left, 200,200 bottom-right)
3. Uppercase letters: use ~160px height (baseline at y=170, cap-height at y=10)
4. Lowercase letters: use ~110px height (baseline at y=170, x-height at y=60)
5. Digits: same as uppercase
6. ALL paths must be CLOSED (end with Z)
7. Use M, L, C, Q, S, Z commands only — no transforms
8. Make letters visually distinct, readable, and stylistically consistent with: "{user_prompt}"
9. IMPORTANT: Every letter must look correct and beautiful — not abstract blobs

Return ONLY valid JSON in this exact format, no markdown, no explanation:
{{
  "style_name": "short style name",
  "chars": {{
    "A": "M100,10 L160,170 L140,170 L100,50 L60,170 L40,170 Z M70,120 L130,120 L120,140 L80,140 Z",
    "B": "M40,10 L40,170 ...",
    ...one entry per requested character...
  }}
}}

Make EVERY character beautiful and on-style. The font will be used commercially."""


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


def _fallback_path(char: str) -> str:
    """Simple rectangle fallback for missing/broken chars."""
    return "M40,10 L160,10 L160,170 L40,170 Z M50,20 L150,20 L150,160 L50,160 Z"


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
        # ── STEP 1: Ask Gemini for uppercase + digits ──────────────────
        batch1 = CHARS_UPPERCASE + CHARS_DIGITS
        print(f"[GeminiSVG] Batch 1: {len(batch1)} chars (A-Z + 0-9)...")
        try:
            p1 = build_gemini_prompt(prompt, batch1)
            r1 = call_gemini(p1, gemini_key)
            style_name = r1.get('style_name', 'custom')
            for ch, d in r1.get('chars', {}).items():
                char_paths[ch] = validate_path(d, ch)
            print(f"  [GeminiSVG] Batch 1 got {len(r1.get('chars',{}))} chars")
        except Exception as e:
            print(f"  [GeminiSVG] Batch 1 error: {e}")

        # ── STEP 2: Ask Gemini for lowercase ──────────────────────────
        print(f"[GeminiSVG] Batch 2: {len(CHARS_LOWERCASE)} chars (a-z)...")
        try:
            p2 = build_gemini_prompt(prompt, CHARS_LOWERCASE)
            r2 = call_gemini(p2, gemini_key)
            for ch, d in r2.get('chars', {}).items():
                char_paths[ch] = validate_path(d, ch)
            print(f"  [GeminiSVG] Batch 2 got {len(r2.get('chars',{}))} chars")
        except Exception as e:
            print(f"  [GeminiSVG] Batch 2 error: {e}")
            # Fallback: use uppercase scaled down
            print("  [GeminiSVG] Using uppercase fallback for lowercase")
            for ch in CHARS_LOWERCASE:
                upper = ch.upper()
                if upper in char_paths:
                    char_paths[ch] = _scale_path_for_lowercase(char_paths[upper])

    else:
        print("[GeminiSVG] No API key — using geometric fallback")
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
