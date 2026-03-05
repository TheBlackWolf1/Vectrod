"""
ai_distortion.py — GEMINI BRAIN + EFFECT ENGINE
=================================================
Architecture:
  1. Gemini reads the user prompt → returns structured "Effect Recipe"
  2. Effect Recipe = list of named distortion commands with parameters
  3. Each command maps to a pure-math function that operates on stroke primitives
  4. Final SVG paths generated AFTER all distortions applied

Effect Commands Gemini can produce:
  • tremor          — irregular wobble on all strokes
  • slab_serif      — add rectangular slabs at terminals  
  • ink_trap        — cut notches at junctions
  • sharp_terminals — points instead of flat ends
  • flare           — stroke widths flare at terminals
  • bounce          — randomize vertical position slightly
  • crystal         — add geometric spike decorations at terminals
  • inline          — add thin inner line parallel to strokes
  • shadow_offset   — duplicate strokes offset
  • condensed       — scale x by factor
  • expanded        — scale x by factor
  • italic_shear    — apply horizontal shear
  • rounded_corners — add radius to all rect corners
  • eroded          — rough up edges irregularly
  • neon_glow       — stroke expansion (visual only, SVG filter)
  • drip            — add tear-drop drips at bottom terminals
  • stencil_cut     — cut rectangular gaps in strokes
  • layered         — duplicate with slight offset for 3D look
"""

import math, json, random, os, re

# ── EFFECT REGISTRY ────────────────────────────────────
# Maps effect name → applicator function
# Each function takes (strokes, params, adv) → modified strokes

def _effect_tremor(strokes, params, adv):
    """Shake all coordinates by a small random amount."""
    intensity = params.get('intensity', 0.05)  # fraction of stroke width
    seed = params.get('seed', 42)
    rng = random.Random(seed)
    def jitter(v, sw):
        return v + rng.uniform(-sw * intensity, sw * intensity)
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        sw = p.get('sw', 50)
        if s['type'] == 'vbar':
            p['cx'] = jitter(p['cx'], sw); p['y1'] = jitter(p['y1'], sw); p['y2'] = jitter(p['y2'], sw)
        elif s['type'] == 'hbar':
            p['cy'] = jitter(p['cy'], sw); p['x1'] = jitter(p['x1'], sw); p['x2'] = jitter(p['x2'], sw)
        elif s['type'] == 'diag':
            for k in ['x1','y1','x2','y2']: p[k] = jitter(p[k], sw)
        elif s['type'] == 'oval':
            p['cx'] = jitter(p['cx'], sw*0.3); p['cy'] = jitter(p['cy'], sw*0.3)
        s['params'] = p; result.append(s)
    return result

def _effect_slab_serif(strokes, params, adv):
    """Add rectangular slab serifs at all vbar terminals."""
    slab_w = params.get('width_ratio', 2.8)   # multiplier of stroke width
    slab_h_ratio = params.get('height_ratio', 0.5)
    result = list(strokes)
    for s in strokes:
        if s['type'] == 'vbar' and not s['is_counter']:
            p = s['params']; sw = p['sw']; cx = p['cx']
            sw_s = int(sw * slab_w); sh = max(8, int(sw * slab_h_ratio))
            for y in [p['y1'], p['y2']]:
                result.append({
                    'type': 'hbar',
                    'params': {'x1': cx - sw_s//2, 'x2': cx + sw_s//2, 'cy': y, 'sw': sh},
                    'role': 'serif', 'is_counter': False
                })
    return result

def _effect_sharp_terminals(strokes, params, adv):
    """Convert arc terminals to sharp diagonal points."""
    # Mark arc strokes as 'sharp' style — path renderer handles it
    result = []
    for s in strokes:
        s = dict(s)
        if s['type'] == 'arc':
            s['sharp'] = True
        result.append(s)
    return result

def _effect_flare(strokes, params, adv):
    """Flare stroke widths at terminals — thicker ends."""
    factor = params.get('factor', 1.6)
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] in ('vbar','hbar','diag') and not s['is_counter']:
            p['flare'] = factor
        s['params'] = p; result.append(s)
    return result

def _effect_crystal(strokes, params, adv):
    """Add geometric spike decorations at all terminal points."""
    spike_len = params.get('length_ratio', 1.2)
    spike_w   = params.get('width_ratio', 0.4)
    result = list(strokes)
    for s in strokes:
        if s['type'] == 'vbar' and not s['is_counter']:
            p = s['params']; sw = p['sw']; cx = p['cx']
            sp_l = int(sw * spike_len); sp_w = int(sw * spike_w)
            for y, dy in [(p['y1'], -1), (p['y2'], 1)]:
                # Central spike
                result.append({'type':'diag','params':{
                    'x1':cx-sp_w,'y1':y,'x2':cx+sp_w,'y2':y,'sw':2,'_spike':True,
                }, 'role':'decoration','is_counter':False})
                result.append({'type':'diag','params':{
                    'x1':cx,'y1':y,'x2':cx,'y2':y+dy*sp_l,'sw':sp_w,'_spike':True,
                }, 'role':'decoration','is_counter':False})
                # Side crystals
                for dx in [-1, 1]:
                    result.append({'type':'diag','params':{
                        'x1':cx,'y1':y,'x2':cx+dx*sp_l*0.7,'y2':y+dy*sp_l*0.7,'sw':sp_w//2,'_spike':True,
                    }, 'role':'decoration','is_counter':False})
    return result

def _effect_bounce(strokes, params, adv):
    """Random baseline bounce per glyph — looks hand-stamped."""
    dy = params.get('dy', 15)
    seed = params.get('seed', 0)
    offset = random.Random(seed).uniform(-dy, dy)
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        for k in ['y1','y2','cy']:
            if k in p: p[k] = p[k] + offset
        for k in ['cy']:
            if k in p: p[k] = p[k] + offset
        s['params'] = p; result.append(s)
    return result

def _effect_inline(strokes, params, adv):
    """Add thin inner line parallel to all strokes."""
    gap = params.get('gap', 0.15)
    result = list(strokes)
    for s in strokes:
        if s['type'] in ('vbar','hbar') and not s['is_counter'] and s['role'] != 'serif':
            p = s['params']; sw = p['sw']
            thin_sw = max(4, int(sw * 0.12))
            g = int(sw * gap)
            inline = dict(s); ip = dict(p)
            if s['type'] == 'vbar':
                ip['x1_offset'] = g  # renderer uses this hint
            inline['params'] = ip
            inline['role'] = 'inline'
            inline['is_counter'] = True   # cuts a thin line through
            result.append(inline)
    return result

def _effect_italic_shear(strokes, params, adv):
    """Apply horizontal italic shear to all coordinates."""
    angle_deg = params.get('angle', 12)
    shear = math.tan(math.radians(angle_deg))
    def sx(x, y): return x + (BASE - y) * shear   # pivot at baseline
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] == 'vbar':
            p['cx'] = sx(p['cx'], (p['y1']+p['y2'])//2)
        elif s['type'] == 'hbar':
            p['x1'] = sx(p['x1'], p['cy']); p['x2'] = sx(p['x2'], p['cy'])
        elif s['type'] == 'diag':
            p['x1'] = sx(p['x1'],p['y1']); p['x2'] = sx(p['x2'],p['y2'])
        elif s['type'] == 'oval':
            p['cx'] = sx(p['cx'], p['cy'])
        elif s['type'] == 'arc':
            p['cx'] = sx(p['cx'], p['cy'])
        s['params'] = p; result.append(s)
    return result

def _effect_condensed(strokes, params, adv):
    """Scale all x coordinates toward center."""
    factor = params.get('factor', 0.72)
    cx_adv = adv / 2
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        def scx(x): return cx_adv + (x - cx_adv) * factor
        if s['type'] == 'vbar':   p['cx'] = scx(p['cx'])
        elif s['type'] == 'hbar': p['x1'] = scx(p['x1']); p['x2'] = scx(p['x2'])
        elif s['type'] == 'diag': p['x1'] = scx(p['x1']); p['x2'] = scx(p['x2'])
        elif s['type'] == 'oval': p['cx'] = scx(p['cx']); p['rx'] = p['rx'] * factor
        elif s['type'] == 'arc':  p['cx'] = scx(p['cx']); p['rx'] = p['rx'] * factor
        s['params'] = p; result.append(s)
    return result

def _effect_expanded(strokes, params, adv):
    params2 = dict(params); params2['factor'] = params.get('factor', 1.28)
    return _effect_condensed(strokes, params2, adv)

def _effect_rounded_corners(strokes, params, adv):
    """Add radius hint to all rect strokes."""
    radius = params.get('radius', 0.5)  # fraction of sw
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if s['type'] in ('vbar','hbar') and not s['is_counter']:
            p['radius'] = int(p.get('sw',50) * radius)
        s['params'] = p; result.append(s)
    return result

def _effect_drip(strokes, params, adv):
    """Add teardrop drips at bottom terminals."""
    count   = params.get('count', 2)
    length  = params.get('length_ratio', 2.0)
    result  = list(strokes)
    bottoms = []
    for s in strokes:
        if s['type'] == 'vbar' and not s['is_counter']:
            p = s['params']
            bottoms.append((p['cx'], p['y2'], p['sw']))
    # Sort, take bottom-most `count`
    bottoms.sort(key=lambda b: -b[1])
    for cx, y, sw in bottoms[:count]:
        drip_h = int(sw * length)
        drip_w = sw // 2
        result.append({'type':'_drip',
                       'params':{'cx':cx,'y':y,'w':drip_w,'h':drip_h},
                       'role':'decoration','is_counter':False})
    return result

def _effect_stencil_cut(strokes, params, adv):
    """Cut rectangular gaps through strokes (stencil look)."""
    gap_h    = params.get('gap_height', 0.3)
    gap_pos  = params.get('position', 0.5)   # 0=top, 1=bottom
    result   = list(strokes)
    for s in strokes:
        if s['type'] == 'vbar' and not s['is_counter']:
            p = s['params']; sw = p['sw']
            h = p['y2'] - p['y1']
            gy = p['y1'] + h * gap_pos - h * gap_h / 2
            gh = max(6, int(h * gap_h))
            result.append({'type':'hbar',
                           'params':{'x1':p['cx']-sw//2-2,'x2':p['cx']+sw//2+2,'cy':gy+gh//2,'sw':gh},
                           'role':'cut','is_counter':True})
    return result

def _effect_eroded(strokes, params, adv):
    """Roughen edges by adding tiny notch counters along strokes."""
    density = params.get('density', 6)
    size    = params.get('size', 0.18)
    seed    = params.get('seed', 7)
    rng     = random.Random(seed)
    result  = list(strokes)
    for s in strokes:
        if s['type'] == 'vbar' and not s['is_counter']:
            p = s['params']; sw = p['sw']; cx = p['cx']
            h = p['y2'] - p['y1']
            for _ in range(density):
                ny = p['y1'] + rng.uniform(0.1, 0.9) * h
                nx = cx + rng.choice([-1,1]) * sw * 0.45
                nr = max(3, int(sw * size))
                result.append({'type':'oval',
                               'params':{'cx':nx,'cy':ny,'rx':nr,'ry':nr},
                               'role':'erosion','is_counter':True})
    return result

def _effect_layered(strokes, params, adv):
    """Duplicate strokes with offset for layered/shadow look."""
    dx = params.get('dx', 8); dy = params.get('dy', 8)
    result = []
    # Background layer first (offset)
    for s in strokes:
        if s['is_counter']: continue
        s2 = dict(s); p2 = dict(s['params'])
        for k in ['cx','x1','x2']: 
            if k in p2: p2[k] = p2[k] + dx
        for k in ['cy','y1','y2']:
            if k in p2: p2[k] = p2[k] + dy
        s2['params'] = p2; s2['role'] = 'shadow'; result.append(s2)
    result.extend(strokes)
    return result

# ── EFFECT REGISTRY ────────────────────────────────────
EFFECTS = {
    'tremor':          _effect_tremor,
    'slab_serif':      _effect_slab_serif,
    'sharp_terminals': _effect_sharp_terminals,
    'flare':           _effect_flare,
    'crystal':         _effect_crystal,
    'bounce':          _effect_bounce,
    'inline':          _effect_inline,
    'italic_shear':    _effect_italic_shear,
    'condensed':       _effect_condensed,
    'expanded':        _effect_expanded,
    'rounded_corners': _effect_rounded_corners,
    'drip':            _effect_drip,
    'stencil_cut':     _effect_stencil_cut,
    'eroded':          _effect_eroded,
    'layered':         _effect_layered,
}


# ── GEMINI BRAIN ───────────────────────────────────────
GEMINI_SYSTEM_PROMPT = """You are a professional type designer AI. Given a font description prompt, 
you output a JSON "Effect Recipe" that describes how to stylize a base font skeleton.

IMPORTANT RULES:
1. Return ONLY valid JSON, no markdown, no explanation.
2. Choose 2-5 effects from the available list.
3. Parameters must be numbers (no strings except where noted).
4. The base_family must be one of: sans, serif, script, display, mono
5. Be creative — match the effects to the visual style described.

Available effects and their parameters:
- tremor: {intensity: 0.02-0.15, seed: int}
- slab_serif: {width_ratio: 1.5-4.0, height_ratio: 0.3-0.8}
- sharp_terminals: {}
- flare: {factor: 1.2-2.5}
- crystal: {length_ratio: 0.8-2.0, width_ratio: 0.2-0.6}
- bounce: {dy: 5-30, seed: int}
- inline: {gap: 0.1-0.25}
- italic_shear: {angle: 8-20}
- condensed: {factor: 0.55-0.85}
- expanded: {factor: 1.15-1.5}
- rounded_corners: {radius: 0.2-0.8}
- drip: {count: 1-4, length_ratio: 1.0-3.5}
- stencil_cut: {gap_height: 0.15-0.4, position: 0.3-0.7}
- eroded: {density: 3-12, size: 0.1-0.25, seed: int}
- layered: {dx: 4-16, dy: 4-16}

Output format:
{
  "base_family": "sans|serif|script|display|mono",
  "stroke_weight": 40-120,
  "effects": [
    {"name": "effect_name", "params": {...}},
    ...
  ],
  "reasoning": "brief explanation"
}

Examples:
Prompt "horror dripping dark blood font" → 
{
  "base_family": "serif",
  "stroke_weight": 55,
  "effects": [
    {"name": "drip", "params": {"count": 3, "length_ratio": 2.8}},
    {"name": "tremor", "params": {"intensity": 0.08, "seed": 13}},
    {"name": "eroded", "params": {"density": 8, "size": 0.2, "seed": 7}}
  ],
  "reasoning": "Serif base with drips, tremor for unstable feel, erosion for decay"
}

Prompt "clean minimal swiss geometric" →
{
  "base_family": "sans",
  "stroke_weight": 40,
  "effects": [
    {"name": "sharp_terminals", "params": {}},
    {"name": "condensed", "params": {"factor": 0.88}}
  ],
  "reasoning": "Thin sans with sharp clean terminals, slightly condensed"
}
"""

def call_gemini(prompt: str, api_key: str) -> dict:
    """Call Gemini API to get Effect Recipe for a font prompt."""
    import urllib.request
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    payload = json.dumps({
        "system_instruction": {"parts": [{"text": GEMINI_SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": f"Font prompt: {prompt}"}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 512}
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        text = data['candidates'][0]['content']['parts'][0]['text'].strip()
        # Strip markdown fences if present
        text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.MULTILINE).strip()
        recipe = json.loads(text)
        print(f"[Gemini] Recipe: {json.dumps(recipe, indent=2)}")
        return recipe
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return None

def get_recipe_heuristic(prompt: str) -> dict:
    """
    Offline fallback — rule-based recipe when no Gemini key.
    Uses keyword scoring to pick best effects.
    """
    p = prompt.lower()
    
    # Base family
    family_scores = {'sans':0,'serif':0,'display':0,'mono':0}
    for w in ['serif','elegant','luxury','classic','roman','book']: 
        if w in p: family_scores['serif']+=2
    for w in ['mono','tech','code','cyber','digital','terminal','matrix','pixel','sci-fi']:
        if w in p: family_scores['mono']+=2
    for w in ['retro','poster','display','slab','western','vintage','grunge','funky']:
        if w in p: family_scores['display']+=2
    for w in ['minimal','clean','swiss','geometric','modern']:
        if w in p: family_scores['sans']+=2
    best_family = max(family_scores, key=family_scores.get) if max(family_scores.values())>0 else 'sans'
    
    # Stroke weight
    weight = 55
    if any(w in p for w in ['bold','heavy','thick','black','fat']): weight = 100
    if any(w in p for w in ['thin','light','hairline','minimal','delicate']): weight = 28
    if any(w in p for w in ['ultra','extra bold']): weight = 118
    
    effects = []
    
    # Horror / scary
    if any(w in p for w in ['horror','scary','blood','creepy','spooky','evil','dark','drip']):
        effects.append({'name':'drip','params':{'count':3,'length_ratio':2.5}})
        effects.append({'name':'tremor','params':{'intensity':0.07,'seed':13}})
        effects.append({'name':'eroded','params':{'density':6,'size':0.18,'seed':7}})
        best_family = 'serif'
        weight = 55
    
    # Retro / western / slab
    elif any(w in p for w in ['retro','slab','western','cowboy','poster','vintage','bold']):
        effects.append({'name':'slab_serif','params':{'width_ratio':2.5,'height_ratio':0.5}})
        if any(w in p for w in ['rough','grunge','distressed']):
            effects.append({'name':'eroded','params':{'density':4,'size':0.15,'seed':3}})
        best_family = 'display'
    
    # Cyber / tech / mono
    elif any(w in p for w in ['cyber','glitch','neon','matrix','hacker','digital']):
        effects.append({'name':'sharp_terminals','params':{}})
        effects.append({'name':'stencil_cut','params':{'gap_height':0.22,'position':0.5}})
        if 'glitch' in p: effects.append({'name':'tremor','params':{'intensity':0.04,'seed':99}})
        best_family = 'mono'
    
    # Elegant / luxury / serif
    elif any(w in p for w in ['elegant','luxury','serif','fashion','magazine','editorial']):
        effects.append({'name':'flare','params':{'factor':1.5}})
        effects.append({'name':'sharp_terminals','params':{}})
        best_family = 'serif'; weight = 28
    
    # Kawaii / cute / rounded
    elif any(w in p for w in ['cute','kawaii','round','bubble','soft','fun','friendly']):
        effects.append({'name':'rounded_corners','params':{'radius':0.7}})
        effects.append({'name':'bounce','params':{'dy':12,'seed':5}})
        weight = 70
    
    # Crystal / geometric / sharp
    elif any(w in p for w in ['crystal','sharp','spike','geometric','diamond','star']):
        effects.append({'name':'crystal','params':{'length_ratio':1.3,'width_ratio':0.35}})
        effects.append({'name':'sharp_terminals','params':{}})
    
    # Italic / script
    elif any(w in p for w in ['italic','slant','oblique','script','calligraphy']):
        effects.append({'name':'italic_shear','params':{'angle':14}})
        effects.append({'name':'flare','params':{'factor':1.4}})
        best_family = 'serif'
    
    # Minimal / swiss / thin
    elif any(w in p for w in ['minimal','thin','swiss','clean','simple']):
        effects.append({'name':'sharp_terminals','params':{}})
        weight = 24
    
    # Default — add subtle flare
    if not effects:
        effects.append({'name':'flare','params':{'factor':1.2}})
    
    return {
        'base_family': best_family,
        'stroke_weight': weight,
        'effects': effects,
        'reasoning': f'Heuristic: {best_family}, sw={weight}'
    }


def get_effect_recipe(prompt: str, gemini_key: str = None) -> dict:
    """
    Main entry point: get effect recipe for a prompt.
    Uses Gemini if key available, else heuristic fallback.
    """
    if not gemini_key:
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
    
    if gemini_key:
        print(f"[Brain] Using Gemini API...")
        recipe = call_gemini(prompt, gemini_key)
        if recipe:
            return recipe
        print("[Brain] Gemini failed, using heuristic fallback")
    else:
        print("[Brain] No Gemini key — using heuristic fallback")
    
    return get_recipe_heuristic(prompt)


def apply_recipe(strokes: list, recipe: dict, adv: int) -> list:
    """
    Apply all effects from a recipe to a list of strokes.
    Returns the distorted stroke list.
    """
    result = strokes
    char_seed = hash(str(strokes)) & 0xFFFF
    
    for effect in recipe.get('effects', []):
        name   = effect.get('name', '')
        params = dict(effect.get('params', {}))
        
        # Inject per-glyph seed variation so glyphs differ
        if 'seed' in params:
            params['seed'] = params['seed'] ^ char_seed
        
        fn = EFFECTS.get(name)
        if fn:
            try:
                result = fn(result, params, adv)
            except Exception as e:
                print(f"[Effect] {name} failed: {e}")
        else:
            print(f"[Effect] Unknown effect: {name}")
    
    return result
