__VERSION__ = "v8.0-rich-recipes"
"""
ai_distortion.py — GEMINI CHIEF DESIGNER + DECORATION ENGINE  v8
==================================================================
v8 changes:
  - Gemini system prompt completely rewritten — richer, more precise
  - Floral recipe: vine_tendril effect, 4 decoration types, ince stroke
  - New effect: vine_tendril (organic curling line at stem tops)
  - New effect: thin_contrast (thick/thin stroke contrast like real serif)
  - All recipes produce much more detailed, beautiful output
"""

import math, json, os, re


# ── STRUCTURAL EFFECTS ──────────────────────────────────

def _effect_slab_serif(strokes, params, adv):
    slab_w = params.get('width_ratio', 2.5)
    slab_h = params.get('height_ratio', 0.45)
    result = list(strokes)
    for s in strokes:
        if s['type'] == 'vbar' and not s['is_counter'] and s['role'] != 'serif':
            p = s['params']; sw = p['sw']; cx = p['cx']
            sw_s = int(sw * slab_w); sh = max(6, int(sw * slab_h))
            for y in [p['y1'], p['y2']]:
                result.append({'type':'hbar',
                    'params':{'x1':cx-sw_s//2,'x2':cx+sw_s//2,'cy':y,'sw':sh},
                    'role':'serif','is_counter':False})
    return result

def _effect_sharp_terminals(strokes, params, adv):
    return [dict(s, sharp=True) if s['type']=='arc' else s for s in strokes]

def _effect_flare(strokes, params, adv):
    factor = params.get('factor', 1.5)
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] in ('vbar','hbar','diag') and not s['is_counter']:
            p['flare'] = factor
        s['params'] = p; result.append(s)
    return result

def _effect_italic_shear(strokes, params, adv):
    from font_skeletons import BASE
    angle_deg = params.get('angle', 12)
    shear = math.tan(math.radians(angle_deg))
    def sx(x, y): return x + (BASE - y) * shear
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] == 'vbar':   p['cx'] = sx(p['cx'], (p['y1']+p['y2'])//2)
        elif s['type'] == 'hbar': p['x1'] = sx(p['x1'],p['cy']); p['x2'] = sx(p['x2'],p['cy'])
        elif s['type'] == 'diag': p['x1'] = sx(p['x1'],p['y1']); p['x2'] = sx(p['x2'],p['y2'])
        elif s['type'] in ('oval','arc'): p['cx'] = sx(p['cx'], p['cy'])
        s['params'] = p; result.append(s)
    return result

def _effect_condensed(strokes, params, adv):
    factor = params.get('factor', 0.72)
    cx = adv / 2
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] == 'vbar':   p['cx'] = cx + (p['cx']-cx)*factor
        elif s['type'] == 'hbar': p['x1'] = cx+(p['x1']-cx)*factor; p['x2'] = cx+(p['x2']-cx)*factor
        elif s['type'] == 'diag': p['x1'] = cx+(p['x1']-cx)*factor; p['x2'] = cx+(p['x2']-cx)*factor
        elif s['type'] in ('oval','arc'): p['cx'] = cx+(p['cx']-cx)*factor; p['rx'] = p.get('rx',50)*factor
        s['params'] = p; result.append(s)
    return result

def _effect_expanded(strokes, params, adv):
    return _effect_condensed(strokes, {'factor': params.get('factor', 1.28)}, adv)

def _effect_rounded_corners(strokes, params, adv):
    radius = params.get('radius', 0.5)
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] in ('vbar','hbar','diag') and not s['is_counter']:
            p['radius'] = radius
        s['params'] = p; result.append(s)
    return result

def _effect_inline(strokes, params, adv):
    thin_ratio = params.get('thin_ratio', 0.28)
    result = list(strokes)
    for s in strokes:
        if s['type'] in ('vbar','hbar','diag') and not s['is_counter']:
            s2 = dict(s); p2 = dict(s['params'])
            thin = max(2, int(p2['sw'] * thin_ratio))
            p2['sw'] = thin
            s2['params'] = p2; s2['role'] = 'inline'; s2['is_counter'] = True
            result.append(s2)
    return result

def _effect_thin_contrast(strokes, params, adv):
    """
    Thin/thick stroke contrast — horizontals become thin like classic serif.
    Makes floral/elegant fonts look much more refined.
    """
    thin_ratio = params.get('thin_ratio', 0.38)
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] == 'hbar' and not s['is_counter'] and s.get('role') in ('bar','serif'):
            p['sw'] = max(6, int(p['sw'] * thin_ratio))
        s['params'] = p; result.append(s)
    return result

EFFECTS = {
    'slab_serif':      _effect_slab_serif,
    'sharp_terminals': _effect_sharp_terminals,
    'flare':           _effect_flare,
    'italic_shear':    _effect_italic_shear,
    'condensed':       _effect_condensed,
    'expanded':        _effect_expanded,
    'rounded_corners': _effect_rounded_corners,
    'inline':          _effect_inline,
    'thin_contrast':   _effect_thin_contrast,
}


# ── GEMINI SYSTEM PROMPT ────────────────────────────────

GEMINI_SYSTEM_PROMPT = """You are the chief type designer at Vectrod, a cutting-edge type foundry.
Your job: given a font description, produce a precise JSON Design DNA that drives an automated font engine.

CRITICAL RULES — MUST FOLLOW OR FONT BREAKS:
1. Return ONLY valid JSON. Zero markdown, zero explanation, zero backticks.
2. star4 / star5 / star6 / starburst / starburst_ray are FOREVER BANNED. Never use them.
3. stroke_weight must be an integer, range 18–120.
4. base_family must be exactly one of: sans | serif | display | mono
5. For floral/botanical: only use flower, leaf, petal, raindrop, fleur_tip, scroll, spiral, wave
6. For tech/cyber/gothic: use lightning, diamond, hexagon, gear_tooth, arrow_right, cross, crown_spike, ink_drop

VECTROD ENGINE DNA SCHEMA — return exactly this structure:
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
  "reasoning": "Why this design achieves the requested style"
}

EFFECTS — use exact names, 0–4 effects max:
  thin_contrast    {"thin_ratio": 0.22–0.45}          thinner horizontal strokes (floral, elegant serif)
  slab_serif       {"width_ratio": 2.0–3.5,            rectangular serifs at stem ends
                    "height_ratio": 0.30–0.60}
  sharp_terminals  {}                                  diagonal cuts at stroke ends (cyber, gothic)
  inline           {"thin_ratio": 0.16–0.34}           engraved center groove (cyber, tech)
  italic_shear     {"angle": 6–16}                     italic slant
  condensed        {"factor": 0.68–0.92}               compress letter width
  expanded         {"factor": 1.08–1.38}               widen letter width
  rounded_corners  {"radius": 0.3–0.8}                 soft rounded joins (kawaii, friendly)
  flare            {"factor": 1.3–2.2}                 stroke widens at terminals

DECORATION ANCHORS:
  top_center   apex or topmost point (A, I, T, cap of b/d/l)
  top_left     top of left stem
  top_right    top of right stem
  base_left    bottom left of letter at baseline
  base_right   bottom right of letter at baseline
  base_center  center of baseline
  bowl_top     top of circular counter (B, D, O, P, R, b, d, g, o)
  bowl_right   rightmost bowl point
  crossbar     horizontal crossbar center (H, A, E, F, t)
  terminal_top open terminal at top (C, G, S, c, e, s)
  descender    bottom of descenders (g, j, p, q, y)

DECORATION FIELDS:
  shape      string from allowed shapes list
  anchor     string from anchor types above
  scale      float 0.4–2.8 (relative to stroke_weight × 1.8)
  angle      float 0–360 degrees
  every_nth  int: 1=every letter, 2=every other, 3=every third, 4=every fourth

PROVEN STYLE RECIPES (reference these, DO NOT copy blindly — adapt to the prompt):

MINIMAL FLORAL:
  family: serif  sw: 26–32  effects: [thin_contrast:0.32, italic_shear:9]
  decos: flower@top_center scale:1.6 nth:1, leaf@base_right scale:1.1 angle:38 nth:2,
         petal@top_right scale:0.8 angle:20 nth:3

CYBERPUNK / NEON:
  family: mono  sw: 44–56  effects: [sharp_terminals, inline:0.22, condensed:0.84]
  decos: lightning@top_right scale:0.9 nth:2, diamond@base_right scale:0.6 angle:45 nth:3, hexagon@top_left scale:0.55 nth:4

GOTHIC / HORROR:
  family: serif  sw: 65–85  effects: [sharp_terminals, slab_serif width:3.0 height:0.5]
  decos: crown_spike@top_center scale:1.8 nth:1, ink_drop@base_left scale:0.9 nth:2

ELEGANT / LUXURY:
  family: serif  sw: 18–26  effects: [thin_contrast:0.22, flare:1.8, sharp_terminals]
  decos: fleur_tip@top_center scale:1.0 nth:3, scroll@base_right scale:0.7 nth:4

RETRO / WESTERN:
  family: display  sw: 80–110  effects: [slab_serif width:3.0 height:0.5, expanded:1.18]
  decos: diamond@top_right scale:0.9 angle:45 nth:3

KAWAII / CUTE:
  family: sans  sw: 70–88  effects: [rounded_corners:0.72]
  decos: heart@top_center scale:1.1 nth:2, flower@base_right scale:0.85 nth:2

BOLD / HEAVY DISPLAY:
  family: display  sw: 95–120  effects: [slab_serif, expanded:1.1]

MINIMAL SANS / GEOMETRIC:
  family: sans  sw: 38–52  effects: [sharp_terminals] or []

ITALIC / SCRIPT:
  family: serif  sw: 32–44  effects: [italic_shear:14, thin_contrast:0.30, flare:1.6]

FORBIDDEN: star4, star5, star6, star_smooth, starburst, starburst_ray — these crash the engine.
"""




def call_gemini(prompt: str, api_key: str) -> dict:
    import urllib.request
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = json.dumps({
        "system_instruction": {"parts": [{"text": GEMINI_SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": f"Create a font design recipe for: {prompt}"}]}],
        "generationConfig": {"temperature": 0.65, "maxOutputTokens": 800}
    }).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=22) as resp:
            data = json.loads(resp.read().decode())
        text = data['candidates'][0]['content']['parts'][0]['text'].strip()
        text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.MULTILINE).strip()
        recipe = json.loads(text)
        # Validate required fields
        assert recipe.get('base_family') in ('sans','serif','display','mono')
        assert isinstance(recipe.get('stroke_weight'), (int,float))
        print(f"[Gemini] ✅ Family={recipe['base_family']} SW={recipe['stroke_weight']}")
        print(f"[Gemini] Effects: {[e['name'] for e in recipe.get('effects',[])]}")
        print(f"[Gemini] Decorations: {[d['shape']+'@'+d['anchor'] for d in recipe.get('decorations',[])]}")
        return recipe
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return None


def get_recipe_heuristic(prompt: str) -> dict:
    """Rich offline fallback — rule-based recipes with full detail."""
    p = prompt.lower()

    # ── FLORAL / BOTANICAL ─────────────────────────────
    if any(w in p for w in ['floral','flower','fleur','botanical','rose','garden',
                              'spring','bloom','blossom','botanical','cicek','çiçek',
                              'nature','vine','ivy','leaf','romantic']):
        sw = 24 if any(w in p for w in ['thin','delicate','light']) else 32
        sw = 48 if any(w in p for w in ['bold','heavy','thick']) else sw
        return {
            'base_family': 'serif',
            'stroke_weight': sw,
            'effects': [
                {'name': 'thin_contrast', 'params': {'thin_ratio': 0.32}},
                {'name': 'italic_shear',  'params': {'angle': 9}},
            ],
            'decorations': [
                {'shape': 'flower',   'anchor': 'top_center', 'scale': 1.8,  'angle': 0,   'every_nth': 1},
                {'shape': 'leaf',     'anchor': 'base_right', 'scale': 1.1,  'angle': 38,  'every_nth': 2},
                {'shape': 'petal',    'anchor': 'top_right',  'scale': 0.85, 'angle': 20,  'every_nth': 2},
                {'shape': 'raindrop', 'anchor': 'base_left',  'scale': 0.65, 'angle': 175, 'every_nth': 3},
            ],
            'reasoning': 'Floral botanical: thin elegant serif, italic lean, rich botanical ornaments'
        }

    # ── GOTHIC / HORROR / DARK ─────────────────────────
    elif any(w in p for w in ['horror','gothic','dark','skull','death','blood',
                               'creepy','vampire','demon','shadow','grim','sinister']):
        return {
            'base_family': 'serif',
            'stroke_weight': 68,
            'effects': [
                {'name': 'sharp_terminals', 'params': {}},
                {'name': 'slab_serif',       'params': {'width_ratio': 3.0, 'height_ratio': 0.38}},
            ],
            'decorations': [
                {'shape': 'crown_spike', 'anchor': 'top_center', 'scale': 1.9, 'angle': 0,   'every_nth': 1},
                {'shape': 'raindrop',    'anchor': 'base_left',  'scale': 1.1, 'angle': 180, 'every_nth': 2},
                {'shape': 'flame',       'anchor': 'top_right',  'scale': 0.9, 'angle': 0,   'every_nth': 3},
                {'shape': 'ink_drop',    'anchor': 'base_right', 'scale': 0.8, 'angle': 200, 'every_nth': 4},
            ],
            'reasoning': 'Gothic horror: heavy serif, spike crowns, blood drops, flames'
        }

    # ── KAWAII / CUTE ──────────────────────────────────
    elif any(w in p for w in ['kawaii','cute','bubbly','sweet','fun','friendly',
                               'round','chibi','adorable','pastel','pink']):
        return {
            'base_family': 'sans',
            'stroke_weight': 76,
            'effects': [
                {'name': 'rounded_corners', 'params': {'radius': 0.72}},
            ],
            'decorations': [
                {'shape': 'heart',   'anchor': 'top_center', 'scale': 1.2,  'angle': 0,  'every_nth': 2},
                {'shape': 'flower4', 'anchor': 'base_right', 'scale': 0.85, 'angle': 15, 'every_nth': 2},
                {'shape': 'flower4', 'anchor': 'top_right',  'scale': 0.65, 'angle': 20, 'every_nth': 3},
                {'shape': 'petal',   'anchor': 'base_left',  'scale': 0.7,  'angle': 330,'every_nth': 4},
            ],
            'reasoning': 'Kawaii cute: round bold sans, hearts, flowers, stars'
        }

    # ── CYBERPUNK / TECH / NEON ────────────────────────
    elif any(w in p for w in ['cyber','glitch','tech','neon','digital','matrix',
                               'hacker','punk','futur','sci-fi','robot','ai']):
        return {
            'base_family': 'mono',
            'stroke_weight': 50,
            'effects': [
                {'name': 'inline',          'params': {'thin_ratio': 0.22}},
                {'name': 'sharp_terminals', 'params': {}},
                {'name': 'condensed',       'params': {'factor': 0.84}},
            ],
            'decorations': [
                {'shape': 'lightning', 'anchor': 'top_right',  'scale': 0.95, 'angle': 0,  'every_nth': 2},
                {'shape': 'diamond',   'anchor': 'base_right', 'scale': 0.6,  'angle': 45, 'every_nth': 3},
                {'shape': 'hexagon',   'anchor': 'top_left',   'scale': 0.55, 'angle': 0,  'every_nth': 4},
            ],
            'reasoning': 'Cyberpunk: condensed mono, inline engraved, lightning accents'
        }

    # ── RETRO / WESTERN / VINTAGE ──────────────────────
    elif any(w in p for w in ['retro','western','cowboy','slab','vintage',
                               'poster','wild west','rodeo','saloon']):
        return {
            'base_family': 'display',
            'stroke_weight': 96,
            'effects': [
                {'name': 'slab_serif', 'params': {'width_ratio': 3.0, 'height_ratio': 0.50}},
                {'name': 'expanded',   'params': {'factor': 1.18}},
            ],
            'decorations': [
                {'shape': 'diamond',    'anchor': 'top_right',   'scale': 0.9, 'angle': 45, 'every_nth': 3},
                {'shape': 'banner_end', 'anchor': 'base_center', 'scale': 1.2, 'angle': 0,  'every_nth': 4},
                {'shape': 'diamond',    'anchor': 'top_left',    'scale': 0.7, 'angle': 45, 'every_nth': 5},
            ],
            'reasoning': 'Retro western: heavy slab serif, wide, star and banner accents'
        }

    # ── ELEGANT / LUXURY / FASHION ─────────────────────
    elif any(w in p for w in ['elegant','luxury','fashion','editorial','vogue',
                               'haute','couture','chic','minimal serif','fine']):
        return {
            'base_family': 'serif',
            'stroke_weight': 26,
            'effects': [
                {'name': 'thin_contrast',   'params': {'thin_ratio': 0.26}},
                {'name': 'flare',           'params': {'factor': 1.9}},
                {'name': 'sharp_terminals', 'params': {}},
            ],
            'decorations': [
                {'shape': 'fleur_tip', 'anchor': 'top_center', 'scale': 1.0, 'angle': 0,  'every_nth': 3},
                {'shape': 'scroll',    'anchor': 'base_right', 'scale': 0.8, 'angle': 0,  'every_nth': 4},
            ],
            'reasoning': 'Elegant luxury: hairline serif, extreme contrast, minimal fleur ornaments'
        }

    # ── STEAMPUNK / MECHANICAL ─────────────────────────
    elif any(w in p for w in ['steampunk','gear','mechanical','industrial','victorian','clockwork']):
        return {
            'base_family': 'serif',
            'stroke_weight': 68,
            'effects': [
                {'name': 'slab_serif',    'params': {'width_ratio': 2.4}},
                {'name': 'thin_contrast', 'params': {'thin_ratio': 0.48}},
            ],
            'decorations': [
                {'shape': 'gear_tooth', 'anchor': 'top_right',  'scale': 1.1, 'angle': 0,  'every_nth': 2},
                {'shape': 'rivet',      'anchor': 'crossbar',   'scale': 0.55,'angle': 0,  'every_nth': 2},
                {'shape': 'diamond',    'anchor': 'base_left',  'scale': 0.65,'angle': 45, 'every_nth': 3},
            ],
            'reasoning': 'Steampunk: heavy serif, gear and rivet accents'
        }

    # ── MINIMAL / CLEAN / GEOMETRIC ────────────────────
    elif any(w in p for w in ['minimal','thin','swiss','clean','geometric','bauhaus','modern']):
        sw = 22 if any(w in p for w in ['ultra thin','hairline','hair']) else 34
        return {
            'base_family': 'sans',
            'stroke_weight': sw,
            'effects': [
                {'name': 'sharp_terminals', 'params': {}},
            ],
            'decorations': [],
            'reasoning': 'Minimal clean: thin geometric sans, no decoration'
        }

    # ── ITALIC / SCRIPT / CALLIGRAPHY ─────────────────
    elif any(w in p for w in ['italic','script','calligraphy','cursive','handwriting','brush']):
        return {
            'base_family': 'serif',
            'stroke_weight': 38,
            'effects': [
                {'name': 'italic_shear',  'params': {'angle': 16}},
                {'name': 'thin_contrast', 'params': {'thin_ratio': 0.30}},
                {'name': 'flare',         'params': {'factor': 1.6}},
            ],
            'decorations': [],
            'reasoning': 'Italic calligraphy: sharp italic lean, strong stroke contrast'
        }

    # ── DEFAULT ────────────────────────────────────────
    else:
        # Try to detect weight
        sw = 52
        if any(w in p for w in ['bold','heavy','black']): sw = 88
        if any(w in p for w in ['thin','light']): sw = 28
        fam = 'sans'
        if any(w in p for w in ['serif','classic']): fam = 'serif'
        return {
            'base_family': fam,
            'stroke_weight': sw,
            'effects': [{'name': 'flare', 'params': {'factor': 1.3}}],
            'decorations': [],
            'reasoning': f'Default: {fam} sw={sw}'
        }


def get_effect_recipe(prompt: str, gemini_key: str = None) -> dict:
    if not gemini_key:
        gemini_key = os.environ.get('GEMINI_API_KEY','')
    if gemini_key:
        print(f"[Brain] Calling Gemini for: \"{prompt[:60]}\"")
        recipe = call_gemini(prompt, gemini_key)
        if recipe:
            return recipe
        print("[Brain] Gemini failed — heuristic fallback")
    else:
        print("[Brain] No Gemini key — heuristic")
    return get_recipe_heuristic(prompt)


# ── DECORATION PLACEMENT ENGINE ────────────────────────

def place_decorations(strokes: list, recipe: dict, char: str, adv: int) -> list:
    """
    Place decorative shapes from recipe onto glyph anchor points.
    v8: Better scale calculation, all anchors attempted.
    """
    decorations = recipe.get('decorations', [])
    if not decorations:
        return strokes

    from glyph_anchors import get_anchors
    from shape_library import get_shape, place

    anchors = get_anchors(char)
    sw = recipe.get('stroke_weight', 52)
    result = list(strokes)
    char_idx = ord(char)

    for dec in decorations:
        shape_name = dec.get('shape', 'flower')
        anchor_type = dec.get('anchor', 'top_center')
        dec_scale = dec.get('scale', 1.0)
        angle = dec.get('angle', 0)
        every_nth = max(1, dec.get('every_nth', 1))

        if every_nth > 1 and (char_idx % every_nth) != 0:
            continue

        # Find matching anchors
        matching = [(x, y) for atype, x, y in anchors if atype == anchor_type]
        if not matching:
            # Smart fallback: find closest anchor type
            fallbacks = {
                'top_center': ['top_left','top_right','ascender'],
                'base_left':  ['base_center','base_right'],
                'base_right': ['base_center','base_left'],
                'crossbar':   ['top_center','bowl_top'],
                'ascender':   ['top_center','top_left'],
                'descender':  ['base_center','base_left'],
            }
            for fb_type in fallbacks.get(anchor_type, ['top_center']):
                matching = [(x, y) for atype, x, y in anchors if atype == fb_type]
                if matching: break
            if not matching and anchors:
                matching = [(anchors[0][1], anchors[0][2])]

        for ax, ay in matching:
            try:
                shape_path = get_shape(shape_name)
                # Scale: glyph-height based so decorations are always visible
                # glyph_h = BASE - CAP = 480 font units
                # dec_scale=1.0 -> ~22% of glyph height (good default)
                from font_skeletons import BASE, CAP
                glyph_h = BASE - CAP  # 480
                size = glyph_h * dec_scale * 0.22
                placed = place(shape_path, ax, ay, size, angle)
                result.append({
                    'type': '_decoration',
                    'params': {'path': placed},
                    'role': 'decoration',
                    'is_counter': False,
                    'shape_name': shape_name,
                })
            except Exception as e:
                print(f"[Decoration] {shape_name}@{anchor_type} failed: {e}")

    return result


def apply_recipe(strokes: list, recipe: dict, adv: int, char: str = '') -> list:
    """Apply effects + decorations from recipe to stroke list."""
    result = strokes

    for effect in recipe.get('effects', []):
        name = effect.get('name', '')
        params = dict(effect.get('params', {}))
        fn = EFFECTS.get(name)
        if fn:
            try:
                result = fn(result, params, adv)
            except Exception as e:
                print(f"[Effect] {name} failed: {e}")

    if char:
        result = place_decorations(result, recipe, char, adv)

    return result
