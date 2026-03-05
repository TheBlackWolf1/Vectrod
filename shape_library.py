"""
shape_library.py — DECORATIVE SHAPE LIBRARY
=============================================
30 mathematically-defined vector shapes.
Each function returns a CW SVG path string (compatible with our winding system).
All shapes are unit-scale (fit in ~1x1 box), scaled at placement time.

Shape catalog:
  NATURE:    flower, rose, leaf, petal, branch, snowflake, raindrop, flame
  GEOMETRIC: star4, star5, star6, diamond, arrow_up, arrow_right, chevron,
             triangle, shield, hexagon, cross, infinity_loop
  ORNAMENT:  scroll, flourish, swash, serif_bracket, ink_drop, teardrop,
             spiral_arm, crown_spike, fleur_de_lis_tip, wave_crest
  RETRO:     lightning, gear_tooth, banner_end, rivet, starburst_ray
"""
import math


# ── HELPERS ─────────────────────────────────────────────
def _rotate_pt(x, y, angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return x*c - y*s, x*s + y*c

def _scale_path(d, sx, sy, tx, ty):
    """Scale and translate an SVG path string."""
    import re
    tokens = re.findall(r'[MCLCSZz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', d)
    result = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in 'MmLl':
            result.append(t)
            i += 1
            while i < len(tokens) and tokens[i] not in 'MCLCSZzmls':
                result.append(f"{float(tokens[i])*sx+tx:.3f}")
                i += 1
                if i < len(tokens) and tokens[i] not in 'MCLCSZzmls':
                    result.append(f"{float(tokens[i])*sy+ty:.3f}")
                    i += 1
        elif t == 'C':
            result.append('C')
            i += 1
            for _ in range(3):
                if i+1 < len(tokens):
                    result.append(f"{float(tokens[i])*sx+tx:.3f}")
                    result.append(f"{float(tokens[i+1])*sy+ty:.3f}")
                    i += 2
        elif t in 'Zz':
            result.append('Z')
            i += 1
        else:
            result.append(t)
            i += 1
    return ' '.join(result)

def place(shape_path, cx, cy, size, angle_deg=0):
    """
    Place a unit shape (centered at 0,0, radius ~0.5) at (cx,cy) with given size.
    angle_deg: rotation in degrees
    Returns scaled+rotated SVG path string.
    """
    # Parse, rotate, scale, translate
    import re
    tokens = re.findall(r'[MCLCSZz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', shape_path)
    angle = math.radians(angle_deg)

    def transform_pt(x, y):
        rx, ry = _rotate_pt(float(x), float(y), angle)
        return rx * size + cx, ry * size + cy

    result = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in 'ML':
            result.append(t); i += 1
            while i < len(tokens) and tokens[i] not in 'MCLCSZzmls':
                px, py = transform_pt(tokens[i], tokens[i+1])
                result.append(f"{px:.2f},{py:.2f}")
                i += 2
        elif t == 'C':
            result.append('C'); i += 1
            for _ in range(3):
                if i+1 < len(tokens):
                    px, py = transform_pt(tokens[i], tokens[i+1])
                    result.append(f"{px:.2f},{py:.2f}")
                    i += 2
        elif t in 'Zz':
            result.append('Z'); i += 1
        else:
            result.append(t); i += 1
    return ' '.join(result)


# ════════════════════════════════════════════════════════
# NATURE SHAPES
# ════════════════════════════════════════════════════════

def flower(petals=5, inner_r=0.18, outer_r=0.48) -> str:
    """
    Flower with smooth cubic-bezier petals.
    Returns CW path centered at 0,0 in unit space.
    """
    k = 0.5523
    parts = []
    for i in range(petals):
        a = 2 * math.pi * i / petals - math.pi/2
        a_next = 2 * math.pi * (i+1) / petals - math.pi/2
        a_mid = (a + a_next) / 2

        # Petal tip
        tip_x = outer_r * math.cos(a_mid)
        tip_y = outer_r * math.sin(a_mid)

        # Base points on inner circle
        b1x = inner_r * math.cos(a)
        b1y = inner_r * math.sin(a)
        b2x = inner_r * math.cos(a_next)
        b2y = inner_r * math.sin(a_next)

        # Bezier control points for smooth petal
        w = 0.55
        cp1x = b1x + (tip_x - b1x) * w + (b1y - tip_y) * 0.2
        cp1y = b1y + (tip_y - b1y) * w - (b1x - tip_x) * 0.2
        cp2x = tip_x + (b2x - tip_x) * (1-w) - (b2y - tip_y) * 0.2
        cp2y = tip_y + (b2y - tip_y) * (1-w) + (b2x - tip_x) * 0.2

        if i == 0:
            parts.append(f"M{b1x:.4f},{b1y:.4f}")
        parts.append(f"C{cp1x:.4f},{cp1y:.4f} {cp2x:.4f},{cp2y:.4f} {tip_x:.4f},{tip_y:.4f}")

        # Return to inner circle
        lx = inner_r * math.cos(a_next)
        ly = inner_r * math.sin(a_next)
        mid_cp_x = (tip_x + lx) / 2
        mid_cp_y = (tip_y + ly) / 2
        parts.append(f"C{mid_cp_x:.4f},{mid_cp_y:.4f} {mid_cp_x:.4f},{mid_cp_y:.4f} {lx:.4f},{ly:.4f}")

    parts.append("Z")
    # Center circle
    k = 0.5523; r = inner_r * 0.6
    parts.append(f"M{0:.4f},{-r:.4f} C{r*k:.4f},{-r:.4f} {r:.4f},{-r*k:.4f} {r:.4f},{0:.4f} "
                 f"C{r:.4f},{r*k:.4f} {r*k:.4f},{r:.4f} {0:.4f},{r:.4f} "
                 f"C{-r*k:.4f},{r:.4f} {-r:.4f},{r*k:.4f} {-r:.4f},{0:.4f} "
                 f"C{-r:.4f},{-r*k:.4f} {-r*k:.4f},{-r:.4f} {0:.4f},{-r:.4f} Z")
    return ' '.join(parts)


def leaf(width=0.28, height=0.5) -> str:
    """Smooth pointed leaf shape."""
    w, h = width/2, height/2
    k = 0.6
    return (f"M0,{-h:.4f} "
            f"C{w*k:.4f},{-h*0.3:.4f} {w:.4f},{h*0.1:.4f} {w*0.5:.4f},{h*0.5:.4f} "
            f"C{w*0.2:.4f},{h:.4f} 0,{h:.4f} 0,{h:.4f} "
            f"C0,{h:.4f} {-w*0.2:.4f},{h:.4f} {-w*0.5:.4f},{h*0.5:.4f} "
            f"C{-w:.4f},{h*0.1:.4f} {-w*k:.4f},{-h*0.3:.4f} 0,{-h:.4f} Z")


def petal(width=0.22, height=0.48) -> str:
    """Single teardrop petal — use rotated copies for flower."""
    w, h = width/2, height/2
    return (f"M0,{-h:.4f} "
            f"C{w:.4f},{-h*0.2:.4f} {w:.4f},{h*0.4:.4f} 0,{h:.4f} "
            f"C{-w:.4f},{h*0.4:.4f} {-w:.4f},{-h*0.2:.4f} 0,{-h:.4f} Z")


def raindrop() -> str:
    """Teardrop / ink drop shape, point at top."""
    return ("M0,-0.5 C0.28,-0.15 0.38,0.1 0.3,0.28 "
            "C0.2,0.46 -0.2,0.46 -0.3,0.28 "
            "C-0.38,0.1 -0.28,-0.15 0,-0.5 Z")


def flame() -> str:
    """Organic flame / fire shape."""
    return ("M0,0.5 C-0.35,0.2 -0.4,-0.1 -0.15,-0.3 "
            "C-0.05,-0.38 0,-0.5 -0.05,-0.3 "
            "C0.1,-0.45 0.2,-0.35 0.05,-0.15 "
            "C0.2,-0.3 0.38,-0.1 0.35,0.2 C0.3,0.4 0.1,0.5 0,0.5 Z")


def snowflake(arms=6) -> str:
    """6-armed snowflake with branch details."""
    parts = []
    for i in range(arms):
        a = 2 * math.pi * i / arms - math.pi/2
        # Main arm
        x1, y1 = 0.45*math.cos(a), 0.45*math.sin(a)
        # Branch points at 40% and 70%
        for frac, blen in [(0.45, 0.18), (0.7, 0.12)]:
            bx = frac * math.cos(a)
            by = frac * math.sin(a)
            for sign in [1, -1]:
                ba = a + sign * math.pi/3
                ex = bx + blen * math.cos(ba)
                ey = by + blen * math.sin(ba)
                parts.append(f"M{bx:.3f},{by:.3f} L{ex:.3f},{ey:.3f}")
        parts.append(f"M0,0 L{x1:.3f},{y1:.3f}")
    # Stroke arms as thin diamonds
    result = []
    sw = 0.04
    for i in range(arms):
        a = 2 * math.pi * i / arms - math.pi/2
        tip_x, tip_y = 0.45*math.cos(a), 0.45*math.sin(a)
        nx = -math.sin(a)*sw; ny = math.cos(a)*sw
        result.append(f"M{nx:.3f},{ny:.3f} L{tip_x:.3f},{tip_y:.3f} "
                      f"L{-nx:.3f},{-ny:.3f} L{-tip_x*0.05:.3f},{-tip_y*0.05:.3f} Z")
    return ' '.join(result)


# ════════════════════════════════════════════════════════
# GEOMETRIC SHAPES
# ════════════════════════════════════════════════════════

def star(points=5, inner_r=0.2, outer_r=0.5) -> str:
    """N-pointed star, pure Bezier for smooth transitions."""
    pts = []
    for i in range(points * 2):
        a = math.pi * i / points - math.pi/2
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((r * math.cos(a), r * math.sin(a)))
    d = f"M{pts[0][0]:.4f},{pts[0][1]:.4f}"
    for x, y in pts[1:]:
        d += f" L{x:.4f},{y:.4f}"
    return d + " Z"


def star_smooth(points=5, inner_r=0.22, outer_r=0.48) -> str:
    """Star with smooth curved indentations — more organic."""
    result = []
    for i in range(points):
        a_out = 2*math.pi * i / points - math.pi/2
        a_in1 = 2*math.pi * (i + 0.5) / points - math.pi/2
        a_in2 = 2*math.pi * (i - 0.5) / points - math.pi/2

        ox, oy = outer_r*math.cos(a_out), outer_r*math.sin(a_out)
        ix, iy = inner_r*math.cos(a_in1), inner_r*math.sin(a_in1)
        px, py = inner_r*math.cos(a_in2), inner_r*math.sin(a_in2)

        if i == 0:
            result.append(f"M{ox:.4f},{oy:.4f}")
        result.append(f"C{ox:.4f},{oy:.4f} {ix:.4f},{iy:.4f} {ix:.4f},{iy:.4f}")
        # Next outer
        a_next = 2*math.pi * (i+1) / points - math.pi/2
        nox, noy = outer_r*math.cos(a_next), outer_r*math.sin(a_next)
        result.append(f"C{ix:.4f},{iy:.4f} {nox:.4f},{noy:.4f} {nox:.4f},{noy:.4f}")
    result.append("Z")
    return ' '.join(result)


def diamond() -> str:
    return "M0,-0.5 L0.35,0 L0,-0.5 M0,-0.5 L0.35,0 L0,0.5 L-0.35,0 Z"


def diamond_clean() -> str:
    return "M0,-0.5 L0.35,0 L0,0.5 L-0.35,0 Z"


def arrow_up() -> str:
    return "M0,-0.5 L0.35,0 L0.12,0 L0.12,0.5 L-0.12,0.5 L-0.12,0 L-0.35,0 Z"


def arrow_right() -> str:
    return "M0.5,0 L0,-0.35 L0,-0.12 L-0.5,-0.12 L-0.5,0.12 L0,0.12 L0,0.35 Z"


def chevron() -> str:
    """V-shaped chevron / checkmark."""
    return "M-0.5,-0.1 L-0.2,0.4 L0,0.15 L0.2,0.4 L0.5,-0.1 L0.2,0.2 L0,-0.05 L-0.2,0.2 Z"


def crown_spike() -> str:
    """Single crown spike / Gothic pinnacle."""
    return ("M-0.18,0.5 L-0.18,-0.1 C-0.18,-0.3 -0.08,-0.45 0,-0.5 "
            "C0.08,-0.45 0.18,-0.3 0.18,-0.1 L0.18,0.5 Z")


def lightning() -> str:
    """Lightning bolt / electric."""
    return "M0.15,-0.5 L-0.1,0 L0.1,0 L-0.15,0.5 L0.35,-0.05 L0.1,-0.05 L0.35,-0.5 Z"


def heart() -> str:
    """Smooth heart shape."""
    return ("M0,0.35 C-0.5,0.05 -0.5,-0.35 -0.25,-0.4 "
            "C-0.1,-0.45 0,-0.25 0,-0.1 "
            "C0,-0.25 0.1,-0.45 0.25,-0.4 "
            "C0.5,-0.35 0.5,0.05 0,0.35 Z")


def hexagon() -> str:
    pts = [(0.5*math.cos(math.pi/6 + math.pi/3*i),
            0.5*math.sin(math.pi/6 + math.pi/3*i)) for i in range(6)]
    d = f"M{pts[0][0]:.4f},{pts[0][1]:.4f}"
    for x,y in pts[1:]: d += f" L{x:.4f},{y:.4f}"
    return d + " Z"


def cross_shape() -> str:
    w = 0.15
    return (f"M{-w},-0.5 L{w},-0.5 L{w},{-w} L0.5,{-w} "
            f"L0.5,{w} L{w},{w} L{w},0.5 L{-w},0.5 "
            f"L{-w},{w} L-0.5,{w} L-0.5,{-w} L{-w},{-w} Z")


# ════════════════════════════════════════════════════════
# ORNAMENTAL SHAPES
# ════════════════════════════════════════════════════════

def teardrop() -> str:
    """Smooth teardrop, point at bottom."""
    return ("M0,-0.42 C0.28,-0.42 0.42,-0.18 0.42,0.05 "
            "C0.42,0.32 0.22,0.5 0,0.5 "
            "C-0.22,0.5 -0.42,0.32 -0.42,0.05 "
            "C-0.42,-0.18 -0.28,-0.42 0,-0.42 Z")


def ink_drop() -> str:
    """Elongated ink drop / brush stroke end."""
    return ("M0,-0.5 C0.12,-0.38 0.22,-0.1 0.18,0.15 "
            "C0.14,0.4 0.06,0.5 0,0.5 "
            "C-0.06,0.5 -0.14,0.4 -0.18,0.15 "
            "C-0.22,-0.1 -0.12,-0.38 0,-0.5 Z")


def scroll_end() -> str:
    """Decorative scroll / volute terminal."""
    k = 0.5523
    # Outer spiral arm
    return ("M0.5,0 C0.5,0.28 0.28,0.5 0,0.5 "
            "C-0.28,0.5 -0.5,0.28 -0.5,0 "
            "C-0.5,-0.2 -0.35,-0.38 -0.15,-0.38 "
            "C0,-0.38 0.12,-0.28 0.12,-0.15 "
            "C0.12,-0.05 0.05,0 0,0 Z")


def fleur_tip() -> str:
    """Fleur-de-lis petal tip."""
    return ("M0,-0.5 C0.2,-0.4 0.35,-0.1 0.25,0.1 "
            "C0.15,0.3 0.05,0.35 0,0.5 "
            "C-0.05,0.35 -0.15,0.3 -0.25,0.1 "
            "C-0.35,-0.1 -0.2,-0.4 0,-0.5 Z")


def wave_crest() -> str:
    """Single wave / ocean crest shape."""
    return ("M-0.5,0.1 C-0.35,-0.35 -0.15,-0.45 0,-0.3 "
            "C0.15,-0.15 0.15,0.1 0.3,0.15 "
            "C0.42,0.2 0.48,0.1 0.5,0 "
            "L0.5,0.5 L-0.5,0.5 Z")


def spiral_arm() -> str:
    """Decorative spiral arm / musical note curl."""
    return ("M0.4,-0.1 C0.4,0.15 0.22,0.35 0,0.35 "
            "C-0.22,0.35 -0.4,0.18 -0.4,0 "
            "C-0.4,-0.18 -0.25,-0.3 -0.08,-0.25 "
            "C0.05,-0.2 0.1,-0.08 0.05,0 "
            "C0.02,0.05 -0.02,0.08 -0.05,0.06 "
            "L-0.05,-0.5 L0.05,-0.5 "
            "C0.05,-0.5 0.4,-0.35 0.4,-0.1 Z")


def banner_end() -> str:
    """Swallowtail banner / ribbon end."""
    return "M-0.5,-0.3 L0.5,-0.3 L0.5,0.3 L0,0 L-0.5,0.3 Z"


def rivet() -> str:
    """Small circular rivet / dot with ring — steampunk."""
    k = 0.5523; r1=0.5; r2=0.25
    outer = (f"M0,{-r1} C{r1*k},{-r1} {r1},{-r1*k} {r1},0 "
             f"C{r1},{r1*k} {r1*k},{r1} 0,{r1} "
             f"C{-r1*k},{r1} {-r1},{r1*k} {-r1},0 "
             f"C{-r1},{-r1*k} {-r1*k},{-r1} 0,{-r1} Z")
    inner = (f"M0,{-r2} C{r2*k},{-r2} {r2},{-r2*k} {r2},0 "
             f"C{r2},{r2*k} {r2*k},{r2} 0,{r2} "
             f"C{-r2*k},{r2} {-r2},{r2*k} {-r2},0 "
             f"C{-r2},{-r2*k} {-r2*k},{-r2} 0,{-r2} Z")
    return outer + " " + inner


def starburst_ray() -> str:
    """Single ray for starburst / sun — repeat rotated."""
    return ("M0,-0.5 C0.06,-0.35 0.08,-0.15 0.06,0 "
            "C0.08,0.15 0.06,0.35 0,0.5 "
            "C-0.06,0.35 -0.08,0.15 -0.06,0 "
            "C-0.08,-0.15 -0.06,-0.35 0,-0.5 Z")


def gear_tooth() -> str:
    """Single gear tooth — steampunk/mechanical."""
    return "M-0.12,-0.5 L-0.12,-0.1 L-0.5,-0.1 L-0.5,0.1 L-0.12,0.1 L-0.12,0.5 L0.12,0.5 L0.12,0.1 L0.5,0.1 L0.5,-0.1 L0.12,-0.1 L0.12,-0.5 Z"


# ════════════════════════════════════════════════════════
# COMPOSITE BUILDERS
# ════════════════════════════════════════════════════════

def build_flower_cluster(n=3, radius=0.5, petals=5, size=0.4) -> str:
    """Multiple small flowers arranged in a circle."""
    parts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        cx = radius * math.cos(a) * 0.6
        cy = radius * math.sin(a) * 0.6
        parts.append(place(flower(petals), cx, cy, size))
    return ' '.join(parts)


def build_starburst(rays=8, inner_r=0.15, outer_r=0.5) -> str:
    """Full starburst from rotated rays."""
    parts = []
    for i in range(rays):
        a = 360 * i / rays
        parts.append(place(starburst_ray(), 0, 0, outer_r, a))
    return ' '.join(parts)


def build_snowflake_full() -> str:
    return snowflake(arms=6)


# ════════════════════════════════════════════════════════
# SHAPE REGISTRY — maps name → (function, description)
# ════════════════════════════════════════════════════════
SHAPES = {
    # Nature
    'flower':         (lambda: flower(5),      "5-petal flower"),
    'flower4':        (lambda: flower(4),      "4-petal flower"),
    'flower6':        (lambda: flower(6),      "6-petal flower"),
    'flower_cluster': (build_flower_cluster,   "3 small flowers"),
    'leaf':           (leaf,                   "pointed leaf"),
    'petal':          (petal,                  "single teardrop petal"),
    'raindrop':       (raindrop,               "raindrop / tear"),
    'flame':          (flame,                  "fire / flame"),
    'snowflake':      (build_snowflake_full,   "6-arm snowflake"),
    # Geometric
    'star4':          (lambda: star(4),        "4-pointed star"),
    'star5':          (lambda: star(5),        "5-pointed star"),
    'star6':          (lambda: star(6),        "6-pointed star"),
    'star_smooth':    (star_smooth,            "smooth 5-pt star"),
    'diamond':        (diamond_clean,          "diamond shape"),
    'arrow_up':       (arrow_up,               "upward arrow"),
    'arrow_right':    (arrow_right,            "right arrow"),
    'chevron':        (chevron,                "V chevron"),
    'crown_spike':    (crown_spike,            "gothic crown spike"),
    'lightning':      (lightning,              "lightning bolt"),
    'heart':          (heart,                  "heart shape"),
    'hexagon':        (hexagon,                "hexagon"),
    'cross':          (cross_shape,            "plus cross"),
    'starburst':      (build_starburst,        "8-ray starburst"),
    # Ornamental
    'teardrop':       (teardrop,               "smooth teardrop"),
    'ink_drop':       (ink_drop,               "ink drop"),
    'scroll':         (scroll_end,             "decorative scroll"),
    'fleur_tip':      (fleur_tip,              "fleur-de-lis tip"),
    'wave':           (wave_crest,             "wave crest"),
    'spiral':         (spiral_arm,             "spiral arm"),
    'banner_end':     (banner_end,             "swallowtail banner"),
    'rivet':          (rivet,                  "steampunk rivet"),
    'gear_tooth':     (gear_tooth,             "gear tooth"),
    'starburst_ray':  (starburst_ray,          "single sun ray"),
}


def get_shape(name: str) -> str:
    """Get a shape path by name. Returns unit-scale CW path."""
    entry = SHAPES.get(name)
    if not entry:
        print(f"[Shape] Unknown: '{name}', using star5")
        entry = SHAPES['star5']
    fn = entry[0]
    return fn()


def list_shapes() -> list:
    return list(SHAPES.keys())
