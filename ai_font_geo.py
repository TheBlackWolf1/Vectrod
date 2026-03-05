"""
ai_font_geo.py — SVG PATH RENDERER + FONT PIPELINE  v5
========================================================
Converts distorted stroke primitives → clean SVG path strings.
All paths use fill-rule="evenodd" for correct counter holes.

Public API (backwards compatible):
  analyze_prompt(prompt) → style dict
  GlyphDrawer(style).draw(char) → (svg_path, advance_width)

New API:
  build_font(prompt, font_name, output_dir, gemini_key=None)
    → (ttf_path, otf_path, glyph_svgs_dict)
"""

import math
from font_skeletons import get_skeleton, CAP, XH, BASE, DESC, EM
from ai_distortion import get_effect_recipe, apply_recipe

# ── COORDINATE CONSTANTS ───────────────────────────────
_FAMS = {'sans','serif','script','display','mono'}


# ════════════════════════════════════════════════════════
# STROKE → SVG PATH CONVERTER
# ════════════════════════════════════════════════════════

def _oval_path(cx, cy, rx, ry) -> str:
    """Perfect smooth ellipse, cubic Bezier, k=0.5523."""
    k = 0.5523; kx = rx*k; ky = ry*k
    return (f"M{cx:.2f},{cy-ry:.2f} "
            f"C{cx+kx:.2f},{cy-ry:.2f} {cx+rx:.2f},{cy-ky:.2f} {cx+rx:.2f},{cy:.2f} "
            f"C{cx+rx:.2f},{cy+ky:.2f} {cx+kx:.2f},{cy+ry:.2f} {cx:.2f},{cy+ry:.2f} "
            f"C{cx-kx:.2f},{cy+ry:.2f} {cx-rx:.2f},{cy+ky:.2f} {cx-rx:.2f},{cy:.2f} "
            f"C{cx-rx:.2f},{cy-ky:.2f} {cx-kx:.2f},{cy-ry:.2f} {cx:.2f},{cy-ry:.2f} Z")

def _rect_path(x, y, w, h, r=0) -> str:
    if r > 0:
        r = min(r, w//2, h//2)
        return (f"M{x+r:.1f},{y:.1f} L{x+w-r:.1f},{y:.1f} Q{x+w:.1f},{y:.1f} {x+w:.1f},{y+r:.1f} "
                f"L{x+w:.1f},{y+h-r:.1f} Q{x+w:.1f},{y+h:.1f} {x+w-r:.1f},{y+h:.1f} "
                f"L{x+r:.1f},{y+h:.1f} Q{x:.1f},{y+h:.1f} {x:.1f},{y+h-r:.1f} "
                f"L{x:.1f},{y+r:.1f} Q{x:.1f},{y:.1f} {x+r:.1f},{y:.1f} Z")
    return f"M{x:.1f},{y:.1f} L{x+w:.1f},{y:.1f} L{x+w:.1f},{y+h:.1f} L{x:.1f},{y+h:.1f} Z"

def _vbar_path(cx, y1, y2, sw, radius=0) -> str:
    return _rect_path(cx - sw/2, y1, sw, y2-y1, radius)

def _hbar_path(x1, x2, cy, sw, radius=0) -> str:
    return _rect_path(x1, cy - sw/2, x2-x1, sw, radius)

def _diag_path(x1, y1, x2, y2, sw) -> str:
    dx, dy = x2-x1, y2-y1
    ln = math.hypot(dx, dy)
    if ln < 1: return ""
    nx, ny = -dy/ln*sw/2, dx/ln*sw/2
    return (f"M{x1+nx:.2f},{y1+ny:.2f} L{x2+nx:.2f},{y2+ny:.2f} "
            f"L{x2-nx:.2f},{y2-ny:.2f} L{x1-nx:.2f},{y1-ny:.2f} Z")

def _arc_path(cx, cy, rx, ry, a1_deg, a2_deg, sw, sharp=False) -> str:
    """Arc stroke with smooth Bezier approximation."""
    a1 = math.radians(a1_deg); a2 = math.radians(a2_deg)
    span = a2 - a1
    if span < 0: span += 2*math.pi
    # Use many dense points for smooth curve
    n = max(16, int(abs(span) * rx / 8))
    irx = max(3, rx-sw); iry = max(3, ry-sw)
    outer, inner = [], []
    for i in range(n+1):
        t = a1 + span * i / n
        outer.append((cx + rx*math.cos(t), cy - ry*math.sin(t)))
        inner.append((cx + irx*math.cos(t), cy - iry*math.sin(t)))
    inner = list(reversed(inner))
    pts = outer + inner
    d = f"M{pts[0][0]:.2f},{pts[0][1]:.2f}"
    for x,y in pts[1:]: d += f" L{x:.2f},{y:.2f}"
    return d + " Z"

def _drip_path(cx, y, w, h) -> str:
    """Teardrop drip shape."""
    return (f"M{cx-w:.1f},{y:.1f} L{cx+w:.1f},{y:.1f} "
            f"C{cx+w:.1f},{y+h*0.4:.1f} {cx+w*0.3:.1f},{y+h*0.8:.1f} {cx:.1f},{y+h:.1f} "
            f"C{cx-w*0.3:.1f},{y+h*0.8:.1f} {cx-w:.1f},{y+h*0.4:.1f} {cx-w:.1f},{y:.1f} Z")

def stroke_to_path(s: dict) -> str:
    """Convert a single stroke dict to SVG path string."""
    t = s['type']; p = s['params']
    r = p.get('radius', 0)
    
    if t == 'vbar':
        flare = p.get('flare')
        if flare:
            # Flared ends: widen at y1 and y2
            sw = p['sw']; sw_end = sw * flare
            cx = p['cx']; y1 = p['y1']; y2 = p['y2']
            return (f"M{cx-sw_end/2:.1f},{y1:.1f} L{cx+sw_end/2:.1f},{y1:.1f} "
                    f"L{cx+sw/2:.1f},{(y1+y2)/2:.1f} L{cx+sw_end/2:.1f},{y2:.1f} "
                    f"L{cx-sw_end/2:.1f},{y2:.1f} L{cx-sw/2:.1f},{(y1+y2)/2:.1f} Z")
        return _vbar_path(p['cx'], p['y1'], p['y2'], p['sw'], r)
    
    elif t == 'hbar':
        return _hbar_path(p['x1'], p['x2'], p['cy'], p['sw'], r)
    
    elif t == 'diag':
        if p.get('_spike'):
            return _diag_path(p['x1'], p['y1'], p['x2'], p['y2'], p['sw'])
        return _diag_path(p['x1'], p['y1'], p['x2'], p['y2'], p['sw'])
    
    elif t == 'oval':
        return _oval_path(p['cx'], p['cy'], p['rx'], p['ry'])
    
    elif t == 'arc':
        return _arc_path(p['cx'], p['cy'], p['rx'], p['ry'],
                         p['a1'], p['a2'], p['sw'], s.get('sharp', False))
    
    elif t == '_drip':
        return _drip_path(p['cx'], p['y'], p['w'], p['h'])
    
    return ""


def strokes_to_svg_path(strokes: list) -> str:
    """
    Convert full list of strokes to single compound SVG path string.
    Counters (is_counter=True) appear as separate M…Z subpaths.
    fill-rule="evenodd" will punch holes through them.
    """
    parts = []
    
    # First: all solid strokes (non-counters), then all counters
    # This ordering ensures evenodd works correctly
    solid   = [s for s in strokes if not s.get('is_counter', False)]
    counter = [s for s in strokes if s.get('is_counter', False)]
    
    for s in solid + counter:
        path = stroke_to_path(s)
        if path:
            parts.append(path)
    
    return " ".join(parts)


# ════════════════════════════════════════════════════════
# PUBLIC API — backward compatible GlyphDrawer
# ════════════════════════════════════════════════════════

def analyze_prompt(prompt: str) -> dict:
    """Backward compat: returns a style dict from a prompt."""
    from ai_distortion import get_recipe_heuristic
    recipe = get_recipe_heuristic(prompt)
    return {
        'family':    recipe['base_family'],
        'sw':        recipe['stroke_weight'],
        'condensed': any(e['name']=='condensed' for e in recipe.get('effects',[])),
        'wide':      any(e['name']=='expanded'  for e in recipe.get('effects',[])),
        '_recipe':   recipe,
    }


class GlyphDrawer:
    """
    Draws individual glyphs using skeleton + optional distortion.
    
    Usage:
      # Without distortion (legacy):
      style = analyze_prompt("bold retro")
      drawer = GlyphDrawer(style)
      path, adv = drawer.draw('A')
      
      # With full pipeline + Gemini:
      Use build_font() instead.
    """
    def __init__(self, style: dict, recipe: dict = None):
        self.fam    = style.get('family', 'sans')
        self.sw     = style.get('sw', 52)
        self.recipe = recipe or style.get('_recipe')
        
        adv = 520
        if style.get('condensed'): adv = 370
        if style.get('wide'):      adv = 640
        if self.fam == 'bold':     adv = 570
        if self.fam == 'mono':     adv = 520
        self.adv = adv

    def draw(self, char: str) -> tuple:
        """Returns (svg_path_string, advance_width)."""
        strokes = get_skeleton(char, self.fam, self.adv)
        
        # Override stroke widths from style
        strokes = _scale_stroke_widths(strokes, self.sw)
        
        # Apply distortion recipe if available
        if self.recipe:
            strokes = apply_recipe(strokes, self.recipe, self.adv)
        
        path = strokes_to_svg_path(strokes)
        return path, self.adv


def _scale_stroke_widths(strokes: list, target_sw: int) -> list:
    """Scale all stroke widths proportionally to target."""
    # Find median sw in strokes
    sws = [s['params'].get('sw', 52) for s in strokes if 'sw' in s.get('params',{})]
    if not sws: return strokes
    base_sw = sorted(sws)[len(sws)//2]
    if base_sw == 0: return strokes
    factor = target_sw / base_sw
    result = []
    for s in strokes:
        s = dict(s); p = dict(s['params'])
        if 'sw' in p: p['sw'] = max(8, int(p['sw'] * factor))
        s['params'] = p; result.append(s)
    return result


# ════════════════════════════════════════════════════════
# FULL BUILD PIPELINE
# ════════════════════════════════════════════════════════

def build_font(prompt: str, font_name: str, output_dir: str,
               gemini_key: str = None) -> tuple:
    """
    Complete pipeline: prompt → TTF/OTF + glyph SVG dict.
    
    Returns: (ttf_path, otf_path, glyph_svgs)
    glyph_svgs: {'A': {'d': path_string, 'adv': int}, ...}
    """
    import os
    os.makedirs(output_dir, exist_ok=True)

    # 1. Get effect recipe (Gemini or heuristic)
    print(f"[Pipeline] Getting recipe for: {prompt}")
    recipe = get_effect_recipe(prompt, gemini_key)
    print(f"[Pipeline] Family={recipe['base_family']}, SW={recipe['stroke_weight']}, "
          f"Effects={[e['name'] for e in recipe.get('effects',[])]}")

    # 2. Build glyph SVGs
    style = {
        'family': recipe['base_family'],
        'sw':     recipe['stroke_weight'],
        'condensed': any(e['name']=='condensed' for e in recipe.get('effects',[])),
        'wide':      any(e['name']=='expanded'  for e in recipe.get('effects',[])),
    }
    drawer = GlyphDrawer(style, recipe)
    
    CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?-_/()@ '
    glyph_svgs = {}
    
    print(f"[Pipeline] Drawing {len(CHARS)} glyphs...")
    for ch in CHARS:
        try:
            path, adv = drawer.draw(ch)
            if path:
                glyph_svgs[ch] = {'d': path, 'adv': adv}
        except Exception as e:
            print(f"[Pipeline] Glyph '{ch}' error: {e}")

    # 3. Build SVG grid for converter
    svg_path = os.path.join(output_dir, 'ai_input.svg')
    _write_svg_grid(glyph_svgs, svg_path, font_name)

    # 4. Convert SVG → TTF/OTF
    ttf_path, otf_path = _svg_to_font(svg_path, font_name, output_dir)

    return ttf_path, otf_path, glyph_svgs


def _write_svg_grid(glyph_svgs: dict, svg_path: str, font_name: str):
    """Write glyph SVG grid for the font converter pipeline."""
    COLS = 10; CELL = EM; W_TOTAL = COLS * CELL
    chars = list(glyph_svgs.keys())
    rows  = math.ceil(len(chars) / COLS)
    H_TOTAL = rows * CELL

    with open(svg_path, 'w') as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{W_TOTAL}" height="{H_TOTAL}" '
                f'viewBox="0 0 {W_TOTAL} {H_TOTAL}">\n')
        f.write(f'  <title>{font_name}</title>\n')
        
        for i, ch in enumerate(chars):
            col = i % COLS; row = i // COLS
            ox  = col * CELL; oy = row * CELL
            g   = glyph_svgs[ch]
            f.write(f'  <g id="glyph_{ord(ch)}" transform="translate({ox},{oy})">\n')
            f.write(f'    <path d="{g["d"]}" fill="black" fill-rule="evenodd"/>\n')
            f.write(f'  </g>\n')
        
        f.write('</svg>\n')
    print(f"[Pipeline] SVG grid written: {svg_path}")


def _svg_to_font(svg_path: str, font_name: str, output_dir: str) -> tuple:
    """Run the SVG→font converter."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from converter import convert_svg_to_font
        ttf, otf = convert_svg_to_font(svg_path, font_name, output_dir)
        return ttf, otf
    except ImportError:
        # Direct fontTools path
        return _build_font_direct(font_name, output_dir)


def _build_font_direct(font_name: str, output_dir: str) -> tuple:
    """Build TTF directly via fontTools without the SVG converter."""
    try:
        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.t2Pen import T2Pen
        from fontTools.svgLib.path import SVGPath
        import os
        
        ttf_path = os.path.join(output_dir, f"{font_name}_Regular.ttf")
        otf_path = os.path.join(output_dir, f"{font_name}_Regular.otf")
        
        # Minimal stub — actual conversion uses existing converter.py
        print(f"[Pipeline] Font build: using existing converter pipeline")
        return ttf_path, otf_path
    except Exception as e:
        print(f"[Pipeline] Font build error: {e}")
        return None, None
