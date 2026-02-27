#!/usr/bin/env python3
"""
Vectrod AI Font Generator
Claude API → SVG paths → TTF/OTF font
"""

import json, re, os, math, time
import urllib.request, urllib.error

# ── Claude API ────────────────────────────────────────────────────────────────
def call_claude(prompt: str, system: str = "") -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise Exception("ANTHROPIC_API_KEY not set")

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": prompt}]
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["content"][0]["text"]


# ── SVG path üretici ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert font designer who creates SVG path data for individual characters.

Rules:
- Respond ONLY with valid JSON, no markdown, no explanation
- Each path must be valid SVG path data (M, L, C, Q, A, Z commands)
- Coordinate space: 0,0 is top-left, width ~500, height ~700 (baseline at y=550)
- Paths must be FILLED shapes (closed paths with Z), not strokes
- Make characters recognizable and consistent with the requested style
- JSON format: {"A": "M ... Z", "B": "M ... Z", ...}"""


def generate_char_batch(chars: list, style_desc: str, progress_cb=None) -> dict:
    """Bir grup karakteri Claude API ile üret"""

    chars_str = "".join(chars)
    prompt = f"""Generate SVG path data for these characters: {chars_str}

Font style: {style_desc}

Requirements:
- Each character should be a filled closed path
- Width: approximately 400-600 units
- Height: approximately 600-700 units  
- Consistent stroke weight matching the style
- Characters must be clearly recognizable

Return JSON only: {{"char": "svg_path_data", ...}}"""

    try:
        response = call_claude(prompt, SYSTEM_PROMPT)
        # JSON'u temizle
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"```json?\s*|\s*```", "", response)
        data = json.loads(response)
        return data
    except Exception as e:
        print(f"  [API ERROR] {e}")
        return {}


def fallback_glyph(char: str, style: dict) -> tuple:
    """API başarısız olursa geometrik fallback"""
    sw = style.get("stroke_width", 80)
    ch = 700
    w = 500

    if char == " ":
        return "", 250

    # Basit dikdörtgen placeholder
    r = sw // 3
    path = (f"M {r} 0 L {w-r} 0 Q {w} 0 {w} {r} "
            f"L {w} {ch-r} Q {w} {ch} {w-r} {ch} "
            f"L {r} {ch} Q 0 {ch} 0 {ch-r} "
            f"L 0 {r} Q 0 0 {r} 0 Z "
            f"M {sw} {sw} L {w-sw} {sw} L {w-sw} {ch-sw} L {sw} {ch-sw} Z")
    return path, w + 60


# ── Stil analizi ──────────────────────────────────────────────────────────────
def build_style_description(prompt: str) -> str:
    """Prompt'u API için zenginleştir"""
    p = prompt.lower()

    details = []

    # Ağırlık
    if any(w in p for w in ["kalin", "bold", "heavy", "thick", "güçlü"]):
        details.append("very bold heavy strokes")
    elif any(w in p for w in ["ince", "thin", "light", "slim"]):
        details.append("thin delicate strokes")
    else:
        details.append("medium weight strokes")

    # Stil
    if any(w in p for w in ["serif", "klasik", "classic", "roman"]):
        details.append("classic serif style with serifs on stroke endings")
    elif any(w in p for w in ["sans", "modern", "minimal", "clean"]):
        details.append("clean sans-serif modern style")
    elif any(w in p for w in ["gotik", "gothic", "blackletter", "metal"]):
        details.append("dramatic gothic blackletter style")
    elif any(w in p for w in ["yuvarlak", "rounded", "soft", "playful"]):
        details.append("friendly rounded soft style")
    elif any(w in p for w in ["geometric", "geometrik", "sharp"]):
        details.append("precise geometric angular style")

    # Dekoratif
    if any(w in p for w in ["cicek", "çiçek", "floral", "flower"]):
        details.append("with decorative floral elements and petal motifs incorporated into letterforms")
    if any(w in p for w in ["arabesk", "arabesque", "ornament", "süslü"]):
        details.append("with ornamental arabesque decorations")
    if any(w in p for w in ["yildiz", "yıldız", "star"]):
        details.append("with star motifs and pointed decorative elements")
    if any(w in p for w in ["vintage", "retro", "antika"]):
        details.append("vintage retro aesthetic")
    if any(w in p for w in ["luxury", "lüks", "elegant", "şık"]):
        details.append("luxury elegant refined style")
    if any(w in p for w in ["graffiti", "street", "urban"]):
        details.append("urban graffiti street art style")
    if any(w in p for w in ["3d", "three", "üç boyut"]):
        details.append("3D extruded dimensional effect")
    if any(w in p for w in ["outline", "hollow", "içi boş"]):
        details.append("outline hollow letter style")
    if any(w in p for w in ["shadow", "gölge"]):
        details.append("with drop shadow effect")

    base = prompt if len(prompt) < 200 else prompt[:200]
    return f"{base}. Style details: {', '.join(details)}."


# ── Ana üretici ───────────────────────────────────────────────────────────────
def generate_ai_font(prompt: str, font_name: str, output_dir: str,
                     progress_callback=None) -> tuple:
    """
    Prompt → Claude API → SVG → TTF/OTF
    Returns: (ttf_path, otf_path)
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from engine import build_font

    def prog(msg, pct=None):
        if progress_callback:
            progress_callback(msg, pct)
        print(f"  [AI] {msg}" + (f" ({pct}%)" if pct else ""))

    prog("Analyzing prompt...", 5)
    style_desc = build_style_description(prompt)
    prog(f"Style: {style_desc[:80]}...", 8)

    # Tüm karakterler
    all_chars = (
        list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") +
        list("abcdefghijklmnopqrstuvwxyz") +
        list("0123456789") +
        list(".,!?;:'\"()-_/@#$%&*+= ")
    )

    # Fallback stil
    fallback_style = {"stroke_width": 80}

    char_paths = {}
    api_available = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if api_available:
        # API ile üret - batch'ler halinde
        batches = [
            ("A-Z", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), 15),
            ("a-z", list("abcdefghijklmnopqrstuvwxyz"), 40),
            ("0-9", list("0123456789"), 65),
            ("symbols", list(".,!?;:'\"()-_/@#$%&*+= "), 75),
        ]

        for batch_name, batch_chars, pct in batches:
            prog(f"Generating {batch_name} with Claude AI...", pct)
            result = generate_char_batch(batch_chars, style_desc, prog)

            for char in batch_chars:
                if char in result and result[char]:
                    char_paths[char] = (result[char], 560)
                else:
                    path, adv = fallback_glyph(char, fallback_style)
                    char_paths[char] = (path, adv)

            prog(f"  ✓ {batch_name} done ({len([c for c in batch_chars if c in result and result[c]])}/{len(batch_chars)} from API)", pct + 5)
    else:
        # API yok — geometrik fallback
        prog("⚠ No API key — using geometric fallback", 10)
        from ai_font_geo import GlyphDrawer, analyze_prompt as geo_analyze
        style = geo_analyze(prompt)
        drawer = GlyphDrawer(style)
        for i, char in enumerate(all_chars):
            try:
                path, adv = drawer.draw(char)
                char_paths[char] = (path, adv)
            except:
                char_paths[char] = fallback_glyph(char, fallback_style)
            if i % 20 == 0:
                prog(f"Drawing {i+1}/{len(all_chars)}...", 10 + int(i/len(all_chars)*60))

    prog("Building SVG structure...", 80)

    # SVG dosyası oluştur
    svg_path = os.path.join(output_dir, "ai_input.svg")
    write_svg(char_paths, svg_path, all_chars)

    prog("Converting to font...", 85)

    ttf_path, otf_path = build_font(
        svg_path, font_name, output_dir,
        char_order=all_chars
    )

    prog("✓ Complete!", 100)
    return ttf_path, otf_path


def write_svg(char_paths: dict, output_path: str, char_order: list):
    """Karakterleri grid SVG'ye yaz"""
    grid_cols = 10
    cell = 700
    chars = [c for c in char_order if c in char_paths]
    rows = math.ceil(len(chars) / grid_cols)

    W = grid_cols * cell
    H = rows * cell

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
    ]

    for i, char in enumerate(chars):
        col = i % grid_cols
        row = i // grid_cols
        tx = col * cell + 80
        ty = row * cell + 20
        path_data, adv = char_paths[char]
        if path_data:
            parts.append(
                f'<g transform="translate({tx},{ty})" id="c_{ord(char)}">'
                f'<path d="{path_data}" fill="black"/>'
                f'</g>'
            )

    parts.append("</svg>")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
