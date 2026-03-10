"""
gemini_svg_engine.py — Vectrod AI SVG Font Pipeline v3
=======================================================
Kullanıcı prompt → Claude API (Anthropic) → SVG paths → engine.py → TTF/OTF
NOT: Gemini 429 quota hatası aldığı için Anthropic Claude API'ye geçildi.
ANTHROPIC_API_KEY Railway'de zaten mevcut.
"""

import os, json, re, math, time
import urllib.request, urllib.error

CHARS_UPPERCASE = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
CHARS_LOWERCASE = list('abcdefghijklmnopqrstuvwxyz')
CHARS_DIGITS    = list('0123456789')

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
CANVAS  = 200
SPACING = 220


# ── STYLE-AWARE PROMPT ────────────────────────────────────────────────────────
def build_prompt(style: str, chars: list) -> str:
    clist = ', '.join(repr(c) for c in chars)
    n = len(chars)
    style_lower = style.lower()

    if any(w in style_lower for w in ['flower','floral','botanical','rose','petal','bloom']):
        style_notes = (
            "STYLE: Cute floral/botanical font.\n"
            "- All stroke ends are ROUNDED (not sharp) — use C curves to create teardrop terminals\n"
            "- Strokes have organic swelling in the middle (wider in center, narrower at ends)\n"
            "- Letter bowls (in B,D,O,P,R,Q) are big and round like petals\n"
            "- Crossbars (A,H,e,f) curve gently upward in the middle\n"
            "- Stroke width: ~18-22px, consistent\n"
            "- Overall feel: a font you would see on a flower shop, soft and feminine\n"
            "- NO sharp corners anywhere — every corner should be softened with curves"
        )
    elif any(w in style_lower for w in ['kawaii','cute','bubbly','playful','fun','round']):
        style_notes = (
            "STYLE: Kawaii/cute bubbly font.\n"
            "- Very thick rounded strokes (~30-35px)\n"
            "- Exaggerated large round counters and bowls\n"
            "- All terminals are perfectly round circles\n"
            "- Large x-height (lowercase almost as tall as uppercase)"
        )
    elif any(w in style_lower for w in ['minimal','minimalist','clean','geometric','swiss']):
        style_notes = (
            "STYLE: Minimalist geometric sans-serif.\n"
            "- Perfectly consistent stroke width (~16px)\n"
            "- Based on pure circles and straight lines\n"
            "- No serifs, clean terminals cut at 90 degrees\n"
            "- Circular O, perfect rectangles for E,F,L"
        )
    elif any(w in style_lower for w in ['bold','heavy','black','impact','display']):
        style_notes = (
            "STYLE: Bold heavy display font.\n"
            "- Very thick strokes (~40-45px wide)\n"
            "- Tight spacing, powerful presence\n"
            "- Minimal interior space in counters"
        )
    elif any(w in style_lower for w in ['elegant','luxury','serif','thin','fashion','vogue']):
        style_notes = (
            "STYLE: Elegant luxury serif.\n"
            "- High contrast: thick verticals (~20px), hairline horizontals (~4px)\n"
            "- Classical proportions, sharp refined serifs at stroke ends\n"
            "- Think Vogue magazine typography"
        )
    elif any(w in style_lower for w in ['gothic','blackletter','medieval','old english']):
        style_notes = (
            "STYLE: Gothic blackletter.\n"
            "- Angular diagonal strokes, diamond pen nib feel\n"
            "- Heavy vertical strokes with thin diagonal connectors\n"
            "- Traditional medieval proportions"
        )
    elif any(w in style_lower for w in ['cyber','tech','futur','sci-fi','neon','glitch','matrix']):
        style_notes = (
            "STYLE: Cyberpunk/tech font.\n"
            "- Sharp angular cuts into letters (diagonal slices)\n"
            "- Geometric precision, technical feel\n"
            "- Think LED display meets sci-fi UI"
        )
    elif any(w in style_lower for w in ['vintage','retro','old','classic','western','wood']):
        style_notes = (
            "STYLE: Vintage/retro font.\n"
            "- Slab serifs (thick rectangular serifs)\n"
            "- Slight irregularity for hand-crafted feel\n"
            "- Strong thick/thin contrast, like old posters"
        )
    else:
        style_notes = f"STYLE: {style}\nCreate a beautiful readable font that clearly matches this style description."

    if any(c.islower() for c in chars):
        height_note = "These are LOWERCASE letters: top=60, baseline=170 (110px tall). Center x=100."
    else:
        height_note = "These are UPPERCASE letters and digits: top=10, baseline=170 (160px tall). Center x=100."

    return (
        "You are an expert SVG font designer. Generate precise SVG paths for a font.\n\n"
        + style_notes + "\n\n"
        "CANVAS: 200x200 pixels per character.\n"
        + height_note + "\n"
        "Typical widths: I=40px, narrow=50px, normal=100-120px, wide M/W=150px\n\n"
        f"REQUIRED CHARACTERS ({n} total): {clist}\n\n"
        "SVG PATH RULES:\n"
        "- Use ONLY commands: M, L, C, Q, Z\n"
        "- All paths must be FILLED and CLOSED (end with Z)\n"
        "- For letters with holes (O,B,D,P,R,Q,0,4,6,8,9,a,b,d,e,g,o,p,q): "
        "include BOTH outer shape AND inner cutout as subpaths in same d= string\n"
        "- Use C curves generously for smooth organic shapes\n\n"
        "LETTER ANATOMY:\n"
        "- A: two diagonal legs + crossbar + inner triangle cutout\n"
        "- B: vertical stem + two round bumps + two counter cutouts\n"
        "- E: vertical stem + 3 horizontal bars\n"
        "- O: outer oval + inner oval counter\n"
        "- R: stem + round bump top-right + diagonal leg bottom-right\n"
        "- lowercase a: round bowl + vertical stroke on right\n"
        "- lowercase e: round shape with horizontal cut\n"
        "- lowercase g: top bowl + bottom loop\n\n"
        "Return ONLY valid JSON, no markdown, no explanation:\n"
        '{"style_name": "2-3 word name", "chars": {"A": "M...Z", "B": "M...Z"}}\n\n'
        f"Every single one of the {n} characters must be present."
    )


# ── ANTHROPIC API CALL ────────────────────────────────────────────────────────
def call_gemini(prompt: str, api_key: str, timeout: int = 120) -> dict:
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 32768}
    }).encode('utf-8')

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Vectrod/3.0"
    }

    for attempt in range(3):
        try:
            req = urllib.request.Request(f"{GEMINI_URL}?key={api_key}", data=payload, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode('utf-8')

            data = json.loads(raw)
            print(f"  [Gemini] keys: {list(data.keys())}")

            if 'candidates' not in data or not data['candidates']:
                raise RuntimeError(f"No candidates: {raw[:300]}")

            cand = data['candidates'][0]
            if 'content' not in cand:
                raise RuntimeError(f"No content, finishReason={cand.get('finishReason')}")

            text = ''.join(
                p.get('text','') for p in cand['content'].get('parts',[])
            ).strip()
            print(f"  [Gemini] response length: {len(text)}")

            if not text:
                raise RuntimeError("Empty response")

            text = re.sub(r'^```[a-z]*\n?', '', text)
            text = re.sub(r'\n?```$', '', text).strip()

            s, e = text.find('{'), text.rfind('}')
            if s == -1 or e == -1:
                raise RuntimeError(f"No JSON: {text[:150]}")

            result = json.loads(text[s:e+1])
            n = len(result.get('chars', {}))
            print(f"  [Gemini] parsed OK — {n} chars, style='{result.get('style_name')}'")
            return result

        except urllib.error.HTTPError as ex:
            body = ex.read().decode('utf-8', errors='replace')
            print(f"  [Gemini] HTTP {ex.code}: {body[:200]}")
            if ex.code in (429, 529, 503) and attempt < 2:
                time.sleep(15 * (attempt+1)); continue
            raise
        except (json.JSONDecodeError, RuntimeError) as ex:
            print(f"  [Gemini] attempt {attempt+1}: {ex}")
            if attempt < 2:
                time.sleep(5); continue
            raise
        except Exception as ex:
            print(f"  [Gemini] unexpected {attempt+1}: {ex}")
            if attempt < 2:
                time.sleep(3); continue
            raise

    raise RuntimeError("Claude API failed after all retries")


# ── PATH HELPERS ──────────────────────────────────────────────────────────────
def validate_path(d: str, char: str) -> str:
    if not d or 'M' not in d.upper():
        return _fallback_path(char)
    d = d.strip()
    if not d.upper().endswith('Z'):
        d += ' Z'
    return d


def _scale_for_lowercase(path_d: str) -> str:
    sy = 110 / 160
    offset_y = 170 * (1 - sy)
    tokens = re.findall(r'[MCLQZz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', path_d)
    result = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.upper() in 'MCLQ':
            result.append(t); i += 1
            while i < len(tokens) and tokens[i] not in 'MCLQZzmclq':
                try:
                    x_str = tokens[i]; i += 1
                    if i >= len(tokens) or tokens[i] in 'MCLQZzmclq':
                        result.append(x_str); break
                    y_val = float(tokens[i]); i += 1
                    y_new = y_val * sy + offset_y
                    result.append(f"{x_str},{y_new:.1f}")
                except:
                    break
        elif t in 'Zz':
            result.append('Z'); i += 1
        else:
            result.append(t); i += 1
    return ' '.join(result)


# ── GEOMETRIC FALLBACK ────────────────────────────────────────────────────────
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
    if char in _FALLBACK:
        return _FALLBACK[char]
    up = char.upper()
    if up in _FALLBACK:
        return _scale_for_lowercase(_FALLBACK[up])
    return "M40,10 L160,10 L160,170 L40,170 Z"

def _geometric_fallback(chars: list) -> dict:
    return {ch: _fallback_path(ch) for ch in chars}


# ── SVG ASSEMBLER ─────────────────────────────────────────────────────────────
def assemble_svg(char_paths: dict, chars_order: list) -> str:
    cols = 13
    groups = []
    for i, ch in enumerate(chars_order):
        if ch not in char_paths: continue
        path_d = char_paths[ch].strip()
        if not path_d: continue
        col, row = i % cols, i // cols
        tx, ty = col * SPACING, row * SPACING
        safe = ch.replace('"','&quot;').replace('<','&lt;').replace('>','&gt;')
        groups.append(
            f'  <g transform="translate({tx},{ty})" data-char="{safe}">\n'
            f'    <path d="{path_d}" fill="#000"/>\n'
            f'  </g>'
        )
    tc = min(len(chars_order), cols)
    tr = math.ceil(len(chars_order) / cols)
    w, h = tc * SPACING, tr * SPACING
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
        + '\n'.join(groups) + '\n</svg>'
    )

def get_char_order_from_paths(char_paths: dict) -> list:
    from engine import DEFAULT_CHAR_ORDER
    return [ch for ch in DEFAULT_CHAR_ORDER if ch in char_paths]


# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────
def build_from_prompt(prompt: str, font_name: str, output_dir: str,
                      gemini_key: str = '') -> tuple:
    os.makedirs(output_dir, exist_ok=True)
    target_chars = CHARS_UPPERCASE + CHARS_LOWERCASE + CHARS_DIGITS

    # Anthropic key (gemini_key param kept for backward compat)
    api_key = os.environ.get('GEMINI_API_KEY', '') or gemini_key

    print(f"\n[AI-Font] prompt=\"{prompt[:80]}\"")
    print(f"[AI-Font] API: {'Gemini' if api_key else 'NO KEY - fallback'}")

    char_paths = {}
    style_name = 'custom'

    if api_key:
        batches = [
            ('UC+digits', CHARS_UPPERCASE + CHARS_DIGITS),
            ('lowercase', CHARS_LOWERCASE),
        ]
        for bname, bchars in batches:
            print(f"[AI-Font] Requesting {bname} ({len(bchars)} chars)...")
            try:
                p = build_prompt(prompt, bchars)
                r = call_gemini(p, api_key, timeout=120)
                style_name = r.get('style_name', style_name)
                got = r.get('chars', {})
                for ch, d in got.items():
                    char_paths[ch] = validate_path(d, ch)
                print(f"  [AI-Font] {bname}: {len(got)} chars OK")
            except Exception as ex:
                print(f"  [AI-Font] {bname} FAILED: {ex}")
                if bname == 'lowercase':
                    for ch in bchars:
                        if ch not in char_paths:
                            src = char_paths.get(ch.upper(), _fallback_path(ch.upper()))
                            char_paths[ch] = _scale_for_lowercase(src)

    # Fill missing with fallback
    missing = [ch for ch in target_chars if ch not in char_paths]
    for ch in missing:
        char_paths[ch] = _fallback_path(ch)

    if missing:
        print(f"[AI-Font] Fallback used for {len(missing)} chars: {''.join(missing[:10])}")

    if not char_paths:
        raise RuntimeError("No character paths generated")

    ai_chars = len(target_chars) - len(missing)
    print(f"[AI-Font] Total: {len(char_paths)} chars | AI={ai_chars} | Fallback={len(missing)}")

    char_order = get_char_order_from_paths(char_paths)
    svg_content = assemble_svg(char_paths, char_order)
    svg_path = os.path.join(output_dir, f"{font_name}_glyphs.svg")
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    print(f"[AI-Font] SVG: {len(svg_content)} bytes")

    from engine import build_font
    ttf_path, otf_path = build_font(svg_path, font_name, output_dir, char_order=char_order)

    if not ttf_path or not os.path.exists(ttf_path):
        raise RuntimeError("engine.py failed to build TTF")

    sz = os.path.getsize(ttf_path) // 1024
    print(f"[AI-Font] Done: {sz}KB")

    glyph_svgs = {
        ch: f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><path d="{d}" fill="#333"/></svg>'
        for ch, d in char_paths.items()
    }

    return ttf_path, {
        'style_name': style_name,
        'engine': 'claude-svg-v3',
        'char_count': len(char_paths),
        '_otf_path': otf_path,
    }, glyph_svgs
