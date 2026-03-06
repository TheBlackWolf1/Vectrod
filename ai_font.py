#!/usr/bin/env python3
"""
Vectrod AI Font Generator v8
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Claude API  → SVG paths → engine v8 → TTF/OTF
Gemini API  → per-glyph design calls → shape_library decorations
"""

import json, re, os, math, time
import urllib.request, urllib.error


# ── API Wrappers ──────────────────────────────────────────────────────────────

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


def call_gemini(prompt: str, gemini_key: str) -> str:
    """Gemini 1.5 Flash API call"""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": 512}
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"models/gemini-1.5-flash:generateContent?key={gemini_key}")
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"]


# ── Claude SVG Path Üretici ───────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert font designer creating SVG path data for individual characters.

CRITICAL RULES:
- Respond ONLY with valid JSON, no markdown, no explanation
- Coordinate space: 0,0 is TOP-LEFT of cell
  * CAP height starts at y=80 (top of capitals)
  * BASELINE is at y=560
  * Cell width = 700, Cell height = 700
  * Left margin: x=44, Right margin: x=476
- Paths MUST be FILLED closed shapes (end with Z)
- FILL the entire cap height space: paths should span y=80 to y=560
- Stroke width should be 60-100 units (NOT thin lines)
- JSON format: {"A": "M ... Z", "B": "M ... Z", ...}

IMPORTANT: Characters must be LARGE — filling the full 80→560 vertical range.
Thin or tiny characters are WRONG. Make them bold and clear."""


def generate_char_batch(chars: list, style_desc: str, progress_cb=None) -> dict:
    """Bir grup karakteri Claude API ile üret"""
    chars_str = "".join(chars)

    prompt = f"""Generate SVG path data for these characters: {chars_str}

Font style: {style_desc}

COORDINATE SYSTEM (MANDATORY):
- Cell: 700x700 units
- Capital top: y=80, Baseline: y=560
- Left edge: x=44, Right edge: x=476
- Characters MUST fill from y=80 to y=560 (480 units tall)
- Stroke width: 60-90 units minimum

EXAMPLE for letter 'I' (bold sans-serif):
{{"I": "M 160 80 L 340 80 L 340 140 L 290 140 L 290 500 L 340 500 L 340 560 L 160 560 L 160 500 L 210 500 L 210 140 L 160 140 Z"}}

Now generate for: {chars_str}
Return JSON only: {{"char": "svg_path_data", ...}}"""

    try:
        response = call_claude(prompt, SYSTEM_PROMPT)
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"```json?\s*|\s*```", "", response)
        data = json.loads(response)
        return data
    except Exception as e:
        print(f"  [Claude API ERROR] {e}")
        return {}


# ── Stil Analizi ──────────────────────────────────────────────────────────────

def build_style_description(prompt: str) -> str:
    p = prompt.lower()
    details = []

    if any(w in p for w in ["kalin", "bold", "heavy", "thick"]):
        details.append("very bold heavy strokes, stroke-width 90+")
    elif any(w in p for w in ["ince", "thin", "light"]):
        details.append("thin delicate strokes, stroke-width 35")
    else:
        details.append("medium weight strokes, stroke-width 65")

    if any(w in p for w in ["serif", "klasik", "roman"]):
        details.append("classic serif with serifs on stroke endings")
    elif any(w in p for w in ["sans", "modern", "minimal"]):
        details.append("clean sans-serif modern")
    elif any(w in p for w in ["gotik", "gothic", "blackletter"]):
        details.append("dramatic gothic blackletter")
    elif any(w in p for w in ["yuvarlak", "rounded", "soft"]):
        details.append("friendly rounded soft")
    elif any(w in p for w in ["geometric", "geometrik"]):
        details.append("precise geometric angular")

    if any(w in p for w in ["cicek", "çiçek", "floral", "flower"]):
        details.append("with decorative floral elements")
    if any(w in p for w in ["vintage", "retro"]):
        details.append("vintage retro aesthetic")
    if any(w in p for w in ["luxury", "lüks", "elegant"]):
        details.append("luxury elegant refined")

    base = prompt[:200]
    return f"{base}. Details: {', '.join(details)}."


def get_gemini_style_for_char(char: str, style_desc: str, gemini_key: str) -> str:
    """Gemini'den tek harf için sanatsal tasarım rehberi al"""
    if not gemini_key:
        return ""
    try:
        prompt = f"""As a master calligrapher, describe in 2-3 sentences how the letter '{char}' 
should look in this style: {style_desc[:150]}
Focus on: proportions, distinctive features, artistic flourishes.
Be specific and technical. Reply in English."""
        return call_gemini(prompt, gemini_key)
    except Exception as e:
        print(f"  [Gemini design] '{char}': {e}")
        return ""


# ── Fallback Geometrik ────────────────────────────────────────────────────────

def fallback_glyph(char: str, style: dict) -> tuple:
    """API başarısız olursa geometrik fallback — TAM BOY"""
    # CAP=80, BASE=560 aralığını tam dolduran büyük glyph
    sw = style.get("stroke_width", 70)
    CAP, BASE = 80, 560
    L, R = 44, 476
    W = R - L
    CX = (L + R) // 2

    if char == " ":
        return "", 250

    # Büyük dolu dikdörtgen placeholder (küçük değil!)
    path = (
        f"M {L} {CAP} L {R} {CAP} L {R} {BASE} L {L} {BASE} Z "
        f"M {L+sw} {CAP+sw} L {R-sw} {CAP+sw} L {R-sw} {BASE-sw} L {L+sw} {BASE-sw} Z"
    )
    return path, W + 60


# ── Ana Üretici ───────────────────────────────────────────────────────────────

def generate_ai_font(prompt: str, font_name: str, output_dir: str,
                     progress_callback=None,
                     gemini_key: str = "") -> tuple:
    """
    Prompt → Claude/Gemini API → SVG → engine v8 → TTF/OTF
    
    gemini_key: Gemini API key (opsiyonel)
                Her harf için sanatsal Design Call yapar
    
    Returns: (ttf_path, otf_path)
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from engine import build_font

    def prog(msg, pct=None):
        if progress_callback:
            progress_callback(msg, pct)
        pct_str = f" ({pct}%)" if pct is not None else ""
        print(f"  [AI] {msg}{pct_str}")

    prog("Prompt analiz ediliyor...", 5)
    style_desc = build_style_description(prompt)
    prog(f"Stil: {style_desc[:80]}...", 8)

    if gemini_key:
        prog("✦ Gemini API etkin — per-glyph design calls aktif", 9)

    # Tüm karakterler
    all_chars = (
        list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") +
        list("abcdefghijklmnopqrstuvwxyz") +
        list("0123456789") +
        list(".,!?;:'\"()-_/@#$%&*+= ")
    )

    fallback_style = {"stroke_width": 70}
    char_paths = {}

    api_available = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if api_available:
        batches = [
            ("A-Z", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), 15),
            ("a-z", list("abcdefghijklmnopqrstuvwxyz"), 40),
            ("0-9", list("0123456789"), 65),
            ("symbols", list(".,!?;:'\"()-_/@#$%&*+= "), 75),
        ]

        for batch_name, batch_chars, pct in batches:
            prog(f"Claude API ile {batch_name} üretiliyor...", pct)

            # Gemini per-char design call (sadece önemli karakterler için)
            if gemini_key and batch_name in ("A-Z", "a-z"):
                prog(f"  ✦ Gemini design calls for {batch_name}...", pct)
                # Batch'i Gemini style notlarıyla zenginleştir
                sample_chars = batch_chars[:3]  # İlk 3 için örnek al
                style_notes = []
                for sc in sample_chars:
                    note = get_gemini_style_for_char(sc, style_desc, gemini_key)
                    if note:
                        style_notes.append(f"'{sc}': {note[:80]}")
                if style_notes:
                    enriched_style = style_desc + " Gemini notes: " + "; ".join(style_notes)
                else:
                    enriched_style = style_desc
            else:
                enriched_style = style_desc

            result = generate_char_batch(batch_chars, enriched_style, prog)

            success_count = 0
            for char in batch_chars:
                if char in result and result[char]:
                    char_paths[char] = (result[char], 560)
                    success_count += 1
                else:
                    path, adv = fallback_glyph(char, fallback_style)
                    char_paths[char] = (path, adv)

            prog(f"  ✓ {batch_name}: {success_count}/{len(batch_chars)} API'den", pct + 5)

    else:
        # API yok — geometrik fallback (tam boy)
        prog("⚠ API key yok — geometrik fallback (tam boy)", 10)
        try:
            from ai_font_geo import GlyphDrawer, analyze_prompt as geo_analyze
            style = geo_analyze(prompt)
            drawer = GlyphDrawer(style)
            for i, char in enumerate(all_chars):
                try:
                    path, adv = drawer.draw(char)
                    char_paths[char] = (path, adv)
                except Exception:
                    char_paths[char] = fallback_glyph(char, fallback_style)
                if i % 20 == 0:
                    prog(f"Çiziliyor {i+1}/{len(all_chars)}...",
                         10 + int(i / len(all_chars) * 60))
        except ImportError:
            prog("ai_font_geo bulunamadı — basit fallback", 10)
            for char in all_chars:
                char_paths[char] = fallback_glyph(char, fallback_style)

    prog("SVG yapısı oluşturuluyor...", 80)
    svg_path = os.path.join(output_dir, "ai_input.svg")
    write_svg(char_paths, svg_path, all_chars)

    prog("Font dönüştürülüyor (engine v8)...", 85)
    ttf_path, otf_path = build_font(
        svg_path, font_name, output_dir,
        char_order=all_chars,
        gemini_key=gemini_key,
        style_prompt=style_desc,
        progress_callback=progress_callback
    )

    prog("✅ Tamamlandı!", 100)
    return ttf_path, otf_path


def write_svg(char_paths: dict, output_path: str, char_order: list):
    """
    Karakterleri grid SVG'ye yaz.
    Her hücre 700x700, translate ile konumlandırılır.
    Bu format engine v8'in collect_groups() ile %100 uyumlu.
    """
    grid_cols = 10
    cell = 700
    chars = [c for c in char_order if c in char_paths]
    rows = math.ceil(len(chars) / grid_cols)

    W = grid_cols * cell
    H = rows * cell

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
    ]

    for i, char in enumerate(chars):
        col = i % grid_cols
        row = i // grid_cols
        # translate = hücrenin sol üst köşesi (ABSOLUTE koordinat)
        # engine v8 bu tx/ty'yi direkt kullanır
        tx = col * cell
        ty = row * cell

        path_data, adv = char_paths[char]
        if path_data:
            # Path koordinatları LOCAL (0-700 aralığında)
            # Ama engine absolute bekliyor, bu yüzden SVG_LEFT offset ekle
            parts.append(
                f'<g transform="translate({tx},{ty})" '
                f'id="c_{ord(char)}" data-char="{char}">'
                f'<path d="{path_data}" fill="black" fill-rule="evenodd"/>'
                f'</g>'
            )

    parts.append("</svg>")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(f"  [SVG] Yazıldı: {output_path} ({len(chars)} karakter, {rows} satır)")
