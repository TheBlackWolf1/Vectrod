"""
dna_engine.py — Vectrod v2.0 DNA Font Engine Coordinator
==========================================================
THE DNA PIPELINE:
  1. Gemini API (or heuristic fallback) → JSON DNA
  2. DNA analyzed → correct engine selected
  3. Engine builds every glyph from DNA parameters
  4. TTF/OTF exported with proper UPM=1000 metrics

DNA Structure (matches ai_distortion.get_effect_recipe()):
  base_family: 'sans' | 'serif' | 'display' | 'mono'
  stroke_weight: int (18-120)
  effects: [{name, params}]
  decorations: [{shape, anchor, scale, angle, every_nth}]
  reasoning: str

Engine routing:
  floral/botanical/leaf/vine/romantic → floral_engine
  cyber/tech/neon/mono/sharp/inline   → cyber_engine  (CyberGlyphBuilder)
  serif/elegant/luxury                → cyber_engine  (serif mode, slab)
  gothic/horror/dark                  → cyber_engine  (heavy sharp)
  sans/clean/minimal/display/retro    → cyber_engine  (standard)
"""
import os, time, json
from ai_distortion import get_effect_recipe

# ── ENGINE ROUTING ────────────────────────────────────────────────

_FLORAL_KEYWORDS = {
    'floral','flower','botanical','leaf','vine','petal','bloom',
    'blossom','rose','garden','spring','romantic','nature','ivy',
    'organic','botanical','çiçek','cicek','spring','minimal floral',
}
_CYBER_HEAVY = {
    'cyberpunk','neon','tech','digital','matrix','hacker','sci-fi',
    'robot','ai','cyber','glitch','punk','futur','electric',
}
_GOTHIC_KEYWORDS = {
    'gothic','horror','dark','metal','black','death','vampire',
    'medieval','occult','grunge',
}

def _route_engine(dna: dict, prompt: str = '') -> str:
    """Return engine name: 'floral' | 'cyber'"""
    p = prompt.lower()
    effects = {e['name'] for e in dna.get('effects', [])}
    deco_shapes = {d.get('shape','') for d in dna.get('decorations', [])}

    # Hard overrides: if prompt has gothic/cyber/tech → cyber regardless
    _FORCE_CYBER = (_CYBER_HEAVY | _GOTHIC_KEYWORDS |
                    {'retro','western','bold','heavy','slab','serif','minimal',
                     'sans','display','mono','neon','clean','sharp','inline'})
    if any(k in p for k in _FORCE_CYBER):
        # Unless prompt ALSO has explicit floral override
        if not any(k in p for k in _FLORAL_KEYWORDS):
            return 'cyber'

    # Floral route: decorations are STRICTLY botanical (not raindrop — it's in both)
    _BOTANICAL_STRICT = {'flower','flower4','flower6','flower_cluster',
                         'leaf','petal','fleur_tip','scroll','wave','spiral'}
    has_botanical = bool(deco_shapes & _BOTANICAL_STRICT)
    has_floral_prompt = any(k in p for k in _FLORAL_KEYWORDS)

    if has_botanical or has_floral_prompt:
        return 'floral'

    return 'cyber'


# ── GEMINI SYSTEM PROMPT v2.0 ────────────────────────────────────
# Upgraded for DNA-precise output

GEMINI_SYSTEM_PROMPT_V2 = """You are the chief type designer at Vectrod, a cutting-edge type foundry.
Your job: given a font description, output a precise JSON Design DNA.

CRITICAL RULES:
1. Return ONLY valid JSON. No markdown, no explanation, no backticks.
2. star4/star5/star6/starburst are FORBIDDEN decoration shapes. Never use them.
3. For floral/botanical styles: use ONLY flower, leaf, petal, raindrop, fleur_tip, scroll, spiral
4. For tech/cyber styles: use lightning, diamond, hexagon, gear_tooth, arrow_right, cross, ink_drop
5. stroke_weight must be integer 18-120

OUTPUT SCHEMA:
{
  "base_family": "serif",
  "stroke_weight": 28,
  "effects": [
    {"name": "thin_contrast", "params": {"thin_ratio": 0.32}},
    {"name": "italic_shear",  "params": {"angle": 9}}
  ],
  "decorations": [
    {"shape": "flower", "anchor": "top_center", "scale": 1.6, "angle": 0,  "every_nth": 1},
    {"shape": "leaf",   "anchor": "base_right",  "scale": 1.1, "angle": 38, "every_nth": 2}
  ],
  "reasoning": "Why this design works"
}

EFFECTS (exact names):
  thin_contrast      {thin_ratio: 0.28-0.45}    — thin horizontal strokes (floral/serif)
  slab_serif         {width_ratio: 2.0-3.5, height_ratio: 0.3-0.6}  — rectangular serifs
  sharp_terminals    {}                          — diagonal cuts at stroke ends (cyber)
  inline             {thin_ratio: 0.18-0.35}     — engraved groove through stroke
  italic_shear       {angle: 6-15}               — slant
  condensed          {factor: 0.70-0.90}         — narrow
  expanded           {factor: 1.10-1.35}         — wide
  rounded_corners    {radius: 0.3-0.8}           — soft joins

ANCHOR TYPES:
  top_center, top_left, top_right, base_left, base_right, base_center,
  bowl_top, bowl_right, crossbar, terminal_top, ascender, descender

STYLE RECIPES (reference, not copy):

MINIMAL FLORAL (monoline organic):
  family: serif, sw: 26-32, effects: [thin_contrast 0.32, italic_shear 9]
  decos: flower top_center 1.6 every_nth:1, leaf base_right 1.1 angle:38 every_nth:2,
         petal top_right 0.8 angle:20 every_nth:3

CYBERPUNK (sharp inline condensed):
  family: mono, sw: 44-56, effects: [sharp_terminals, inline 0.22, condensed 0.84]
  decos: lightning top_right 0.9 every_nth:2, diamond base_right 0.6 angle:45 every_nth:3

GOTHIC/HORROR (heavy sharp slab):
  family: serif, sw: 65-85, effects: [sharp_terminals, slab_serif width:3.0 height:0.5]
  decos: crown_spike top_center 1.8 every_nth:1, ink_drop base_left 0.9 every_nth:2

ELEGANT/LUXURY (ultra-thin contrast):
  family: serif, sw: 18-26, effects: [thin_contrast 0.22, flare 1.8, sharp_terminals]
  decos: fleur_tip top_center 1.0 every_nth:3, scroll base_right 0.7 every_nth:4

RETRO/WESTERN (slab bold):
  family: display, sw: 80-110, effects: [slab_serif width:3.0 height:0.5, expanded 1.18]
  decos: diamond top_right 0.9 angle:45 every_nth:3, banner_end base_center 1.2 every_nth:4

KAWAII/CUTE (round bold):
  family: sans, sw: 68-85, effects: [rounded_corners 0.72]
  decos: heart top_center 1.1 every_nth:2, flower4 base_right 0.85 every_nth:2

BOLD/BLACK (ultra heavy):
  family: display, sw: 95-120, effects: [slab_serif, expanded 1.1]
  decos: none or minimal diamond

MINIMAL SANS (clean geometric):
  family: sans, sw: 44-54, effects: [condensed 0.92]
  decos: none

Remember: FORBIDDEN shapes = star4, star5, star6, star_smooth, starburst, starburst_ray
"""


def call_gemini_v2(prompt: str, api_key: str) -> dict:
    """Gemini v2 call with updated DNA system prompt."""
    import urllib.request, re
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"models/gemini-2.0-flash:generateContent?key={api_key}")
    payload = json.dumps({
        "system_instruction": {"parts": [{"text": GEMINI_SYSTEM_PROMPT_V2}]},
        "contents": [{"parts": [{"text": f"Design a font for: {prompt}"}]}],
        "generationConfig": {"temperature": 0.60, "maxOutputTokens": 900}
    }).encode('utf-8')
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode())
        text = data['candidates'][0]['content']['parts'][0]['text'].strip()
        text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.MULTILINE).strip()
        dna  = json.loads(text)
        # Validate
        assert dna.get('base_family') in ('sans','serif','display','mono')
        assert isinstance(dna.get('stroke_weight'), (int, float))
        # Enforce no-star rule
        for dec in dna.get('decorations', []):
            if dec.get('shape','') in ('star4','star5','star6','star_smooth',
                                        'starburst','starburst_ray'):
                dec['shape'] = 'flower'
                print(f"[DNA] Banned star → flower redirect")
        print(f"[Gemini v2] ✅ family={dna['base_family']} sw={dna['stroke_weight']}")
        print(f"[Gemini v2] Effects: {[e['name'] for e in dna.get('effects',[])]}")
        print(f"[Gemini v2] Decos: {[d['shape']+'@'+d['anchor'] for d in dna.get('decorations',[])]}")
        return dna
    except Exception as e:
        print(f"[Gemini v2] Error: {e}")
        return None


def get_dna(prompt: str, gemini_key: str = '') -> dict:
    """Get font DNA from Gemini or heuristic fallback."""
    dna = None
    if gemini_key:
        dna = call_gemini_v2(prompt, gemini_key)
    if dna is None:
        from ai_distortion import get_recipe_heuristic
        dna = get_recipe_heuristic(prompt)
        print(f"[DNA] Heuristic: {dna['base_family']} sw={dna['stroke_weight']}")
    return dna


# ── MAIN BUILD FUNCTION ───────────────────────────────────────────

def build_font_from_dna(
    prompt: str,
    font_name: str,
    output_dir: str,
    gemini_key: str = '',
    dna: dict = None,
) -> tuple:
    """
    Complete pipeline: prompt → DNA → TTF + OTF.
    Returns (ttf_path, otf_path, dna, glyph_svgs_dict)
    """
    os.makedirs(output_dir, exist_ok=True)
    t0 = time.time()

    # ── Step 1: Get DNA ──────────────────────────────────────────
    if dna is None:
        dna = get_dna(prompt, gemini_key)
    print(f"[DNA] Recipe in {time.time()-t0:.1f}s → routing to engine...")

    # ── Step 2: Route to engine ──────────────────────────────────
    engine_name = _route_engine(dna, prompt)
    print(f"[DNA] Engine: {engine_name}")

    ttf_out = os.path.join(output_dir, f"{font_name}_Regular.ttf")

    # ── Step 3: Build font ───────────────────────────────────────
    if engine_name == 'floral':
        ttf_out = _build_floral(dna, ttf_out, font_name)
    else:
        ttf_out = _build_cyber(dna, ttf_out, font_name)

    if not ttf_out or not os.path.exists(ttf_out):
        raise RuntimeError("Font build failed")

    # ── Step 4: Generate preview SVGs ───────────────────────────
    glyph_svgs = _make_preview_svgs(ttf_out)

    # ── Step 5: Create OTF copy ──────────────────────────────────
    otf_out = ttf_out.replace('.ttf', '.otf')
    try:
        from fontTools.ttLib import TTFont as _TT
        f = _TT(ttf_out)
        f.flavor = None
        f.save(otf_out)
    except Exception as e:
        print(f"[DNA] OTF copy failed: {e}")
        otf_out = None

    sz = os.path.getsize(ttf_out) / 1024
    print(f"[DNA] ✅ Done in {time.time()-t0:.1f}s | {sz:.1f}KB | engine={engine_name}")
    return ttf_out, otf_out, dna, glyph_svgs


def _build_floral(dna, output_path, font_name):
    """Build using floral_engine with DNA parameters."""
    import importlib, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    fe = importlib.import_module('floral_engine')
    # Inject DNA stroke_weight into floral_engine constants
    fe.SW = max(18, min(60, int(dna.get('stroke_weight', 28))))
    fe.LS = int(fe.SW * 2.6)
    fe.BS = int(fe.SW * 1.8)
    # Rebuild GLYPHS with new constants (functions use module-level vars)
    path = fe.build(output_path, font_name)
    return path


def _build_cyber(dna, output_path, font_name):
    """Build using cyber_engine with DNA parameters."""
    import importlib, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    ce = importlib.import_module('cyber_engine')
    path = ce.build_from_dna(dna, output_path, font_name)
    return path


def _make_preview_svgs(ttf_path: str) -> dict:
    """Extract glyph preview paths from TTF for frontend rendering."""
    try:
        from fontTools.ttLib import TTFont
        from fontTools.pens.svgPathPen import SVGPathPen
        f     = TTFont(ttf_path)
        cmap  = f.getBestCmap()
        gset  = f.getGlyphSet()
        svgs  = {}
        for char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789':
            cp = ord(char)
            gn = cmap.get(cp)
            if not gn: continue
            try:
                pen = SVGPathPen(gset)
                gset[gn].draw(pen)
                d = pen.getCommands()
                w = gset[gn].width
                if d:
                    svgs[char] = {'d': d, 'adv': w}
            except Exception:
                pass
        return svgs
    except Exception as e:
        print(f"[DNA] Preview SVG error: {e}")
        return {}


# ── STANDALONE TEST ───────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    prompt    = sys.argv[1] if len(sys.argv) > 1 else 'minimal floral botanical'
    font_name = sys.argv[2] if len(sys.argv) > 2 else 'TestFont'
    out_dir   = sys.argv[3] if len(sys.argv) > 3 else '/tmp/dna_test'

    gemini_key = os.environ.get('GEMINI_API_KEY', '')
    ttf, otf, dna_out, svgs = build_font_from_dna(prompt, font_name, out_dir, gemini_key)
    print(f"\nTTF: {ttf}")
    print(f"OTF: {otf}")
    print(f"Preview glyphs: {len(svgs)}")
    print(f"DNA: {json.dumps(dna_out, indent=2)}")
