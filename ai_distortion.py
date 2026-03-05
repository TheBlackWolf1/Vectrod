"""
ai_distortion.py — GEMINI CHIEF DESIGNER + DECORATION ENGINE  v6
==================================================================
Architecture:
  User prompt → Gemini → Design Recipe JSON
  Design Recipe → skeleton strokes + decorative shapes placed on anchors
  pathops.union merges everything → clean single-body glyph

NO random noise. NO tremor. NO eroded.
Only: clean geometric effects + Gemini-placed decorative shapes.

Effect commands (clean, intentional):
  slab_serif      — rectangular slabs at terminals
  sharp_terminals — pointed stroke ends
  flare           — stroke width widens at terminals  
  italic_shear    — horizontal italic slant
  condensed       — scale x narrow
  expanded        — scale x wide
  inline          — thin inner line (engraved look)
  rounded_corners — soft radius on all rect corners

Decoration commands (via shape_library):
  {name, shape, anchor_type, scale, angle, every_nth}
  → placed on glyph anchor points using shape_library + pathops.union
"""

import math, json, os, re


# ── CLEAN EFFECTS ──────────────────────────────────────

def _effect_slab_serif(strokes, params, adv):
    """Rectangular slab serifs at all vbar terminals."""
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
    """Mark arc ends as sharp — rendered as points."""
    return [dict(s, sharp=True) if s['type']=='arc' else s for s in strokes]

def _effect_flare(strokes, params, adv):
    """Flare stroke width at terminals."""
    factor = params.get('factor', 1.5)
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] in ('vbar','hbar','diag') and not s['is_counter']:
            p['flare'] = factor
        s['params'] = p; result.append(s)
    return result

def _effect_italic_shear(strokes, params, adv):
    """Horizontal italic shear."""
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
    cx_adv = adv / 2
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        def scx(x): return cx_adv + (x - cx_adv) * factor
        if s['type'] == 'vbar':   p['cx'] = scx(p['cx'])
        elif s['type'] == 'hbar': p['x1'] = scx(p['x1']); p['x2'] = scx(p['x2'])
        elif s['type'] == 'diag': p['x1'] = scx(p['x1']); p['x2'] = scx(p['x2'])
        elif s['type'] in ('oval','arc'): p['cx'] = scx(p['cx']); p['rx'] = p.get('rx',50)*factor
        s['params'] = p; result.append(s)
    return result

def _effect_expanded(strokes, params, adv):
    p2 = dict(params); p2['factor'] = params.get('factor', 1.25)
    return _effect_condensed(strokes, p2, adv)

def _effect_rounded_corners(strokes, params, adv):
    radius = params.get('radius', 0.5)
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] in ('vbar','hbar') and not s['is_counter']:
            p['radius'] = max(4, int(p.get('sw',50) * radius))
        s['params'] = p; result.append(s)
    return result

def _effect_inline(strokes, params, adv):
    """Thin engraved line through stroke centers."""
    result = list(strokes)
    for s in strokes:
        if s['type'] in ('vbar','hbar') and not s['is_counter'] and s['role'] not in ('serif','inline'):
            p = s['params']; sw = p['sw']
            thin = max(6, int(sw * 0.12))
            s2 = dict(s); p2 = dict(p)
            p2['sw'] = thin
            s2['params'] = p2; s2['role'] = 'inline'; s2['is_counter'] = True
            result.append(s2)
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
}


# ── GEMINI BRAIN ───────────────────────────────────────

GEMINI_SYSTEM_PROMPT = """You are a professional type designer. Given a font description, output a JSON Design Recipe.

RULES:
1. Return ONLY valid JSON. No markdown. No explanation.
2. base_family: one of sans | serif | display | mono
3. stroke_weight: 24–120
4. effects: 0–3 clean structural effects from the allowed list
5. decorations: 0–4 decorative shapes placed on letter anchor points

ALLOWED EFFECTS: slab_serif, sharp_terminals, flare, italic_shear, condensed, expanded, rounded_corners, inline

ALLOWED SHAPES: flower, flower4, flower6, flower_cluster, leaf, petal, raindrop, flame, snowflake,
  star4, star5, star6, star_smooth, diamond, arrow_up, arrow_right, chevron, crown_spike,
  lightning, heart, hexagon, cross, starburst, teardrop, ink_drop, scroll, fleur_tip,
  wave, spiral, banner_end, rivet, gear_tooth

ANCHOR TYPES: top_center, top_left, top_right, base_left, base_right, base_center,
  bowl_top, bowl_right, terminal_top, crossbar, ascender, descender

DECORATION FIELDS:
  shape: shape name from the list above
  anchor: anchor type to attach to
  scale: 0.5–2.5 (relative to stroke width)
  angle: 0–360 rotation
  every_nth: 1=all letters, 2=every other, 3=every third (for rare accents)

OUTPUT FORMAT:
{
  "base_family": "serif",
  "stroke_weight": 55,
  "effects": [
    {"name": "slab_serif", "params": {"width_ratio": 2.5}}
  ],
  "decorations": [
    {"shape": "flower", "anchor": "top_center", "scale": 1.2, "angle": 0, "every_nth": 2},
    {"shape": "leaf",   "anchor": "base_left",  "scale": 0.9, "angle": 45, "every_nth": 3}
  ],
  "reasoning": "brief note"
}

EXAMPLES:
"floral romantic cursive" →
  base_family: serif, sw: 36, effects: [italic_shear 12°],
  decorations: [flower top_center scale:1.4, leaf base_right scale:0.8 angle:30]

"horror gothic dark" →
  base_family: serif, sw: 60, effects: [sharp_terminals],
  decorations: [crown_spike top_center scale:1.5, raindrop base_left scale:1.0]

"retro western bold" →
  base_family: display, sw: 90, effects: [slab_serif],
  decorations: [star5 top_right scale:0.8, banner_end base_center scale:1.0]

"cyberpunk tech neon" →
  base_family: mono, sw: 48, effects: [inline, sharp_terminals],
  decorations: [lightning top_right scale:0.7, diamond base_right scale:0.6]

"kawaii cute bubbly" →
  base_family: sans, sw: 72, effects: [rounded_corners],
  decorations: [heart top_center scale:1.0, flower4 base_right scale:0.7]

"minimal clean geometric" →
  base_family: sans, sw: 32, effects: [sharp_terminals],
  decorations: []

"steampunk mechanical gear" →
  base_family: serif, sw: 64, effects: [slab_serif],
  decorations: [gear_tooth top_right scale:0.9, rivet crossbar scale:0.6]
"""


def call_gemini(prompt: str, api_key: str) -> dict:
    import urllib.request
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = json.dumps({
        "system_instruction": {"parts": [{"text": GEMINI_SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": f"Font prompt: {prompt}"}]}],
        "generationConfig": {"temperature": 0.75, "maxOutputTokens": 600}
    }).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=18) as resp:
            data = json.loads(resp.read().decode())
        text = data['candidates'][0]['content']['parts'][0]['text'].strip()
        text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.MULTILINE).strip()
        recipe = json.loads(text)
        print(f"[Gemini] ✅ Family={recipe['base_family']} SW={recipe['stroke_weight']}")
        print(f"[Gemini] Effects: {[e['name'] for e in recipe.get('effects',[])]}")
        print(f"[Gemini] Decorations: {[d['shape']+'@'+d['anchor'] for d in recipe.get('decorations',[])]}")
        return recipe
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return None


def get_recipe_heuristic(prompt: str) -> dict:
    """Offline fallback — rule-based recipe."""
    p = prompt.lower()

    family_scores = {'sans':0,'serif':0,'display':0,'mono':0}
    for w in ['serif','elegant','luxury','classic','roman','floral','romantic']: 
        if w in p: family_scores['serif']+=2
    for w in ['mono','tech','code','cyber','digital','terminal','matrix','gear','steampunk']:
        if w in p: family_scores['mono']+=2
    for w in ['retro','poster','display','slab','western','vintage','bold']:
        if w in p: family_scores['display']+=2
    for w in ['minimal','clean','swiss','geometric','modern','thin']:
        if w in p: family_scores['sans']+=2
    best = max(family_scores, key=family_scores.get)
    if max(family_scores.values()) == 0: best = 'sans'

    weight = 52
    if any(w in p for w in ['bold','heavy','thick','black']): weight = 88
    if any(w in p for w in ['thin','light','minimal','delicate','hair']): weight = 26
    if any(w in p for w in ['ultra','extra bold']): weight = 115

    effects = []
    decorations = []

    if any(w in p for w in ['floral','flower','fleur','botanical','rose','garden','spring']):
        best = 'serif'; weight = 38
        effects = [{'name':'italic_shear','params':{'angle':10}}]
        decorations = [
            {'shape':'flower','anchor':'top_center','scale':1.4,'angle':0,'every_nth':1},
            {'shape':'leaf',  'anchor':'base_right', 'scale':0.85,'angle':35,'every_nth':2},
        ]
    elif any(w in p for w in ['horror','gothic','dark','skull','death','blood','creepy']):
        best = 'serif'; weight = 58
        effects = [{'name':'sharp_terminals','params':{}}]
        decorations = [
            {'shape':'crown_spike','anchor':'top_center','scale':1.5,'angle':0,'every_nth':1},
            {'shape':'raindrop',   'anchor':'base_left', 'scale':1.0,'angle':180,'every_nth':2},
        ]
    elif any(w in p for w in ['kawaii','cute','bubbly','sweet','fun','friendly','round']):
        best = 'sans'; weight = 72
        effects = [{'name':'rounded_corners','params':{'radius':0.65}}]
        decorations = [
            {'shape':'heart',   'anchor':'top_center','scale':1.0,'angle':0,'every_nth':2},
            {'shape':'flower4', 'anchor':'base_right','scale':0.7,'angle':15,'every_nth':3},
        ]
    elif any(w in p for w in ['retro','western','cowboy','slab','vintage','poster']):
        best = 'display'; weight = 92
        effects = [{'name':'slab_serif','params':{'width_ratio':2.8,'height_ratio':0.48}}]
        decorations = [
            {'shape':'star5',     'anchor':'top_right', 'scale':0.9,'angle':15,'every_nth':3},
            {'shape':'banner_end','anchor':'base_center','scale':1.1,'angle':0,'every_nth':4},
        ]
    elif any(w in p for w in ['cyber','glitch','tech','neon','digital','matrix','hacker']):
        best = 'mono'; weight = 50
        effects = [{'name':'inline','params':{}}, {'name':'sharp_terminals','params':{}}]
        decorations = [
            {'shape':'lightning','anchor':'top_right','scale':0.8,'angle':0,'every_nth':3},
            {'shape':'diamond',  'anchor':'base_right','scale':0.55,'angle':45,'every_nth':4},
        ]
    elif any(w in p for w in ['steampunk','gear','mechanical','industrial','victorian']):
        best = 'serif'; weight = 66
        effects = [{'name':'slab_serif','params':{'width_ratio':2.2}}]
        decorations = [
            {'shape':'gear_tooth','anchor':'top_right','scale':0.9,'angle':0,'every_nth':2},
            {'shape':'rivet',     'anchor':'crossbar', 'scale':0.5,'angle':0,'every_nth':3},
        ]
    elif any(w in p for w in ['star','space','cosmic','galaxy','celestial','astro']):
        best = 'sans'; weight = 44
        effects = [{'name':'condensed','params':{'factor':0.82}}]
        decorations = [
            {'shape':'star6',   'anchor':'top_center','scale':0.9,'angle':15,'every_nth':2},
            {'shape':'teardrop','anchor':'base_left', 'scale':0.6,'angle':180,'every_nth':3},
        ]
    elif any(w in p for w in ['elegant','luxury','fashion','editorial','vogue','serif']):
        best = 'serif'; weight = 28
        effects = [{'name':'flare','params':{'factor':1.6}}, {'name':'sharp_terminals','params':{}}]
        decorations = [
            {'shape':'fleur_tip','anchor':'top_center','scale':0.9,'angle':0,'every_nth':3},
        ]
    elif any(w in p for w in ['minimal','thin','swiss','clean','geometric']):
        best = 'sans'; weight = 26
        effects = [{'name':'sharp_terminals','params':{}}]
        decorations = []
    elif any(w in p for w in ['italic','script','calligraphy','cursive']):
        best = 'serif'; weight = 36
        effects = [{'name':'italic_shear','params':{'angle':14}}, {'name':'flare','params':{'factor':1.5}}]
        decorations = []
    else:
        effects = [{'name':'flare','params':{'factor':1.2}}]

    return {
        'base_family': best,
        'stroke_weight': weight,
        'effects': effects,
        'decorations': decorations,
        'reasoning': f'Heuristic: {best} sw={weight}'
    }


def get_effect_recipe(prompt: str, gemini_key: str = None) -> dict:
    if not gemini_key:
        gemini_key = os.environ.get('GEMINI_API_KEY','')
    if gemini_key:
        print(f"[Brain] Calling Gemini for: \"{prompt[:50]}\"")
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
    Returns strokes with decoration shapes appended as '_decoration' type.
    """
    decorations = recipe.get('decorations', [])
    if not decorations:
        return strokes

    from glyph_anchors import get_anchors
    from shape_library import get_shape, place

    anchors = get_anchors(char)
    sw = recipe.get('stroke_weight', 52)
    result = list(strokes)

    # Use char index for every_nth — consistent per-character filtering
    char_idx = ord(char)

    for dec in decorations:
        shape_name = dec.get('shape','star5')
        anchor_type = dec.get('anchor','top_center')
        dec_scale = dec.get('scale', 1.0)
        angle = dec.get('angle', 0)
        every_nth = max(1, dec.get('every_nth', 1))

        # every_nth filter — skip some letters for variety
        if every_nth > 1 and (char_idx % every_nth) != 0:
            continue

        # Find matching anchors on this letter
        matching = [(x, y) for atype, x, y in anchors if atype == anchor_type]
        if not matching:
            # Fallback: use any anchor
            matching = [(x, y) for _, x, y in anchors[:1]]

        for ax, ay in matching:
            shape_path = get_shape(shape_name)
            size = sw * dec_scale
            placed = place(shape_path, ax, ay, size, angle)
            result.append({
                'type': '_decoration',
                'params': {'path': placed},
                'role': 'decoration',
                'is_counter': False,
                'shape_name': shape_name,
            })

    return result


def apply_recipe(strokes: list, recipe: dict, adv: int, char: str = '') -> list:
    """Apply effects + decorations from recipe to stroke list."""
    result = strokes

    # Apply structural effects
    for effect in recipe.get('effects', []):
        name = effect.get('name','')
        params = dict(effect.get('params', {}))
        fn = EFFECTS.get(name)
        if fn:
            try:
                result = fn(result, params, adv)
            except Exception as e:
                print(f"[Effect] {name} failed: {e}")

    # Place decorations
    if char:
        result = place_decorations(result, recipe, char, adv)

    return result
