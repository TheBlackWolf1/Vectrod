"""
floral_engine.py  — Vectrod Organic Floral Font  v2
====================================================
Matches Gemini reference: monoline thin strokes, small leaves/buds
integrated at terminals and junctions, fluid cubic bezier, open counters.

Rules:
  UPM=1000, CAP=850, XH=580, BASE=0, DESC=-180
  SW=28 monoline  |  fill-rule=evenodd (counters always open)
  Leaf scale ~SW*2.6, Bud scale ~SW*1.8
  NO stars. NO geometric decorations. Leaf + bud ONLY.
"""
import math, io, os
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen  import TTGlyphPen
from fontTools.pens.cu2quPen    import Cu2QuPen
from fontTools.svgLib.path      import SVGPath as SVGPathLib

# ── SYSTEM CONSTANTS ──────────────────────────────────────────────
UPM  = 1000
CAP  = 850
XH   = 580
BASE = 0
DESC = -180
SW   = 28
SB   = 55        # side bearing
K    = 0.5523    # bezier circle constant
LS   = int(SW * 2.6)   # leaf size   ≈ 72
BS   = int(SW * 1.8)   # bud size    ≈ 50

# ── HELPERS ───────────────────────────────────────────────────────
def _j(*parts):
    return " ".join(p for p in parts if p and p.strip())

def _adv(W):
    return W + 2 * SB

WN  = 520   # normal caps
WW  = 600   # wide caps (O,G,C,D,Q)
WNR = 300   # narrow (I,J)
WM  = 660   # extra wide (M,W)
WLN = 420   # lowercase normal
WLW = 480   # lowercase wide (m,w)
WLN2= 280   # lowercase narrow (f,i,j,r,t)

# ── STROKE PRIMITIVES ─────────────────────────────────────────────

def stroke(x1, y1, x2, y2, sw=None):
    """Capsule stroke from (x1,y1) to (x2,y2) with round caps."""
    if sw is None: sw = SW
    sw = max(4, sw)
    dx, dy = x2-x1, y2-y1
    ln = math.hypot(dx, dy)
    if ln < 1: return ""
    nx, ny = -dy/ln*(sw/2),  dx/ln*(sw/2)
    ux, uy =  dx/ln*(sw/2),  dy/ln*(sw/2)
    # 4 cubic bezier arcs: right side → end cap → left side → start cap
    return (
        f"M{x1+nx:.1f},{y1+ny:.1f} "
        f"L{x2+nx:.1f},{y2+ny:.1f} "
        f"C{x2+nx+ux*K:.1f},{y2+ny+uy*K:.1f} "
        f"{x2+ux+nx*K:.1f},{y2+uy+ny*K:.1f} "
        f"{x2+ux:.1f},{y2+uy:.1f} "
        f"C{x2+ux-nx*K:.1f},{y2+uy-ny*K:.1f} "
        f"{x2-nx+ux*K:.1f},{y2-ny+uy*K:.1f} "
        f"{x2-nx:.1f},{y2-ny:.1f} "
        f"L{x1-nx:.1f},{y1-ny:.1f} "
        f"C{x1-nx-ux*K:.1f},{y1-ny-uy*K:.1f} "
        f"{x1-ux-nx*K:.1f},{y1-uy-ny*K:.1f} "
        f"{x1-ux:.1f},{y1-uy:.1f} "
        f"C{x1-ux+nx*K:.1f},{y1-uy+ny*K:.1f} "
        f"{x1+nx-ux*K:.1f},{y1+ny-uy*K:.1f} "
        f"{x1+nx:.1f},{y1+ny:.1f} Z"
    )

def arc_stroke(cx, cy, rx, ry, a1_deg, a2_deg, sw=None):
    """Thick open arc stroke with rounded caps. Uses polygon approximation."""
    if sw is None: sw = SW
    sw = max(4, sw)
    N = 24
    a1 = math.radians(a1_deg)
    a2 = math.radians(a2_deg)
    # Ensure a2 > a1 going counter-clockwise
    while a2 <= a1:
        a2 += 2 * math.pi

    # Sample center-line points
    pts = []
    for i in range(N + 1):
        t = i / N
        a = a1 + (a2 - a1) * t
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))

    # Build offset outer and inner paths
    half = sw / 2
    outer, inner = [], []
    for i, (px, py) in enumerate(pts):
        if i == 0:
            dx, dy = pts[1][0]-px, pts[1][1]-py
        elif i == len(pts)-1:
            dx, dy = px-pts[-2][0], py-pts[-2][1]
        else:
            dx = pts[i+1][0]-pts[i-1][0]
            dy = pts[i+1][1]-pts[i-1][1]
        ln = math.hypot(dx, dy)
        if ln < 0.001: ln = 0.001
        nx2, ny2 = -dy/ln*half, dx/ln*half
        outer.append((px+nx2, py+ny2))
        inner.append((px-nx2, py-ny2))

    # Build path: outer forward, round end cap, inner backward, round start cap
    parts = [f"M{outer[0][0]:.1f},{outer[0][1]:.1f}"]
    for p in outer[1:]:
        parts.append(f"L{p[0]:.1f},{p[1]:.1f}")

    # End cap: semicircle from outer[-1] → inner[-1]
    ex, ey   = pts[-1]
    o_end    = outer[-1]; i_end = inner[-1]
    dx2, dy2 = pts[-1][0]-pts[-2][0], pts[-1][1]-pts[-2][1]
    ln2 = math.hypot(dx2, dy2)
    if ln2 > 0.001:
        ux2, uy2 = dx2/ln2*half, dy2/ln2*half
        parts.append(
            f"C{o_end[0]+ux2*K:.1f},{o_end[1]+uy2*K:.1f} "
            f"{ex+ux2+uy2*K*0:.1f},{ey+uy2:.1f} "
            f"{i_end[0]+ux2*K:.1f},{i_end[1]+uy2*K:.1f}"
        )
    else:
        parts.append(f"L{i_end[0]:.1f},{i_end[1]:.1f}")

    for p in reversed(inner[:-1]):
        parts.append(f"L{p[0]:.1f},{p[1]:.1f}")

    # Start cap
    sx, sy   = pts[0]
    o_st     = outer[0]; i_st = inner[0]
    dx3, dy3 = pts[1][0]-pts[0][0], pts[1][1]-pts[0][1]
    ln3 = math.hypot(dx3, dy3)
    if ln3 > 0.001:
        ux3, uy3 = dx3/ln3*half, dy3/ln3*half
        parts.append(
            f"C{i_st[0]-ux3*K:.1f},{i_st[1]-uy3*K:.1f} "
            f"{sx-ux3:.1f},{sy-uy3:.1f} "
            f"{o_st[0]-ux3*K:.1f},{o_st[1]-uy3*K:.1f}"
        )
    parts.append("Z")
    return " ".join(parts)

def oval_stroke(cx, cy, rx, ry, sw=None):
    """Closed oval donut. fill-rule=evenodd keeps center open."""
    if sw is None: sw = SW
    sw = max(4, sw)
    half = sw / 2
    ox, oy = rx + half, ry + half
    ix, iy = max(2, rx - half), max(2, ry - half)
    kx_o, ky_o = ox*K, oy*K
    kx_i, ky_i = ix*K, iy*K
    outer = (
        f"M{cx:.1f},{cy-oy:.1f} "
        f"C{cx+kx_o:.1f},{cy-oy:.1f} {cx+ox:.1f},{cy-ky_o:.1f} {cx+ox:.1f},{cy:.1f} "
        f"C{cx+ox:.1f},{cy+ky_o:.1f} {cx+kx_o:.1f},{cy+oy:.1f} {cx:.1f},{cy+oy:.1f} "
        f"C{cx-kx_o:.1f},{cy+oy:.1f} {cx-ox:.1f},{cy+ky_o:.1f} {cx-ox:.1f},{cy:.1f} "
        f"C{cx-ox:.1f},{cy-ky_o:.1f} {cx-kx_o:.1f},{cy-oy:.1f} {cx:.1f},{cy-oy:.1f} Z"
    )
    inner = (
        f"M{cx:.1f},{cy-iy:.1f} "
        f"C{cx+kx_i:.1f},{cy-iy:.1f} {cx+ix:.1f},{cy-ky_i:.1f} {cx+ix:.1f},{cy:.1f} "
        f"C{cx+ix:.1f},{cy+ky_i:.1f} {cx+kx_i:.1f},{cy+iy:.1f} {cx:.1f},{cy+iy:.1f} "
        f"C{cx-kx_i:.1f},{cy+iy:.1f} {cx-ix:.1f},{cy+ky_i:.1f} {cx-ix:.1f},{cy:.1f} "
        f"C{cx-ix:.1f},{cy-ky_i:.1f} {cx-kx_i:.1f},{cy-iy:.1f} {cx:.1f},{cy-iy:.1f} Z"
    )
    return outer + " " + inner

def curved_vbar(cx, y1, y2, sw=None, curve=0):
    """Vertical bar with optional horizontal curve offset at midpoint."""
    if sw is None: sw = SW
    if curve == 0:
        return stroke(cx, y1, cx, y2, sw)
    mid_y = (y1+y2)/2
    half = sw/2
    # Left contour: 3 cubic segments
    return (
        f"M{cx-half:.1f},{y1:.1f} "
        f"C{cx-half+curve*K:.1f},{y1:.1f} "
        f"{cx+curve-half:.1f},{mid_y-abs(y2-y1)*0.15:.1f} "
        f"{cx+curve-half:.1f},{mid_y:.1f} "
        f"C{cx+curve-half:.1f},{mid_y+abs(y2-y1)*0.15:.1f} "
        f"{cx-half+curve*K:.1f},{y2:.1f} "
        f"{cx-half:.1f},{y2:.1f} "
        f"C{cx+half+curve*K:.1f},{y2:.1f} "   # right side
        f"{cx+curve+half:.1f},{mid_y+abs(y2-y1)*0.15:.1f} "
        f"{cx+curve+half:.1f},{mid_y:.1f} "
        f"C{cx+curve+half:.1f},{mid_y-abs(y2-y1)*0.15:.1f} "
        f"{cx+half+curve*K:.1f},{y1:.1f} "
        f"{cx+half:.1f},{y1:.1f} Z"
    )

# ── BOTANICAL DECORATIONS ─────────────────────────────────────────

def leaf_at(cx, cy, angle_deg, size=None):
    """
    Organic teardrop leaf growing from (cx,cy) in direction angle_deg.
    angle_deg=0 → leaf points RIGHT, 90 → UP, 270 → DOWN, etc.
    """
    if size is None: size = LS
    a  = math.radians(angle_deg)
    h  = size * 0.62
    w  = size * 0.24

    def rot(lx, ly):
        return (cx + lx*math.cos(a) - ly*math.sin(a),
                cy + lx*math.sin(a) + ly*math.cos(a))

    tip  = rot(h, 0)
    base = rot(-h*0.12, 0)
    cl1  = rot(h*0.55,  w*0.90)
    cl2  = rot(-h*0.05, w*0.65)
    cr1  = rot(h*0.55, -w*0.90)
    cr2  = rot(-h*0.05,-w*0.65)

    return (
        f"M{tip[0]:.1f},{tip[1]:.1f} "
        f"C{cl1[0]:.1f},{cl1[1]:.1f} {cl2[0]:.1f},{cl2[1]:.1f} {base[0]:.1f},{base[1]:.1f} "
        f"C{cr2[0]:.1f},{cr2[1]:.1f} {cr1[0]:.1f},{cr1[1]:.1f} {tip[0]:.1f},{tip[1]:.1f} Z"
    )

def leaf_pair(cx, cy, stem_angle_deg, size=None):
    """Two mirrored leaves at a junction point. stem_angle=direction of stem."""
    if size is None: size = int(LS * 0.78)
    # leaves grow perpendicular to stem
    s = size
    perp1 = stem_angle_deg + 78
    perp2 = stem_angle_deg - 78
    a1 = math.radians(perp1); a2 = math.radians(perp2)
    off = s * 0.28
    p1 = (cx + off*math.cos(a1), cy + off*math.sin(a1))
    p2 = (cx + off*math.cos(a2), cy + off*math.sin(a2))
    return _j(leaf_at(p1[0], p1[1], perp1, s),
              leaf_at(p2[0], p2[1], perp2, s))

def bud_at(cx, cy, angle_deg, size=None):
    """
    Flower bud: tiny stem + round head. The peach/orange dot from the reference.
    Angle points AWAY from the letter (direction bud grows).
    """
    if size is None: size = BS
    a   = math.radians(angle_deg)
    sl  = size * 0.50   # stem length
    r   = size * 0.40   # bud radius

    bx  = cx + sl * math.cos(a)
    by  = cy + sl * math.sin(a)

    stem_part = stroke(cx, cy, bx, by, max(3, SW // 5))
    circle = (
        f"M{bx:.1f},{by-r:.1f} "
        f"C{bx+r*K:.1f},{by-r:.1f} {bx+r:.1f},{by-r*K:.1f} {bx+r:.1f},{by:.1f} "
        f"C{bx+r:.1f},{by+r*K:.1f} {bx+r*K:.1f},{by+r:.1f} {bx:.1f},{by+r:.1f} "
        f"C{bx-r*K:.1f},{by+r:.1f} {bx-r:.1f},{by+r*K:.1f} {bx-r:.1f},{by:.1f} "
        f"C{bx-r:.1f},{by-r*K:.1f} {bx-r*K:.1f},{by-r:.1f} {bx:.1f},{by-r:.1f} Z"
    )
    return _j(stem_part, circle)

def tl(cx, cy, angle_deg):
    """Tiny leaf — shorthand for tight spaces."""
    return leaf_at(cx, cy, angle_deg, int(LS * 0.60))

# ── UPPERCASE GLYPHS ──────────────────────────────────────────────

def glyph_A():
    W=WN; L=SB; R=SB+W; CX=(L+R)//2; cy=int(CAP*0.42)
    s1 = stroke(L,    BASE, CX, CAP, SW)
    s2 = stroke(R,    BASE, CX, CAP, SW)
    br = stroke(L+W//4, cy, R-W//4, cy, SW)
    return _j(s1, s2, br,
              bud_at(CX, CAP, 90, BS),
              leaf_at(L, BASE, 210, LS), leaf_at(R, BASE, 330, LS)), _adv(W)

def glyph_B():
    W=WN; L=SB; Lx=L+SW//2; mid=int(CAP*0.50)
    stem  = stroke(Lx, BASE, Lx, CAP, SW)
    bowl_t= arc_stroke(Lx, mid + (CAP-mid)//2, int(W*0.44), (CAP-mid)//2, 270, 90)
    bowl_b= arc_stroke(Lx, mid//2,              int(W*0.48), mid//2,       270, 90)
    return _j(stem, bowl_t, bowl_b,
              leaf_pair(Lx, CAP, 90),
              leaf_pair(Lx, BASE, 270)), _adv(W)

def glyph_C():
    W=WW; CX=SB+W//2; CY=CAP//2
    rx=W//2-SW//2; ry=CAP//2-SW//2
    arc = arc_stroke(CX, CY, rx, ry, 32, 328)
    a1r = math.radians(32);  a2r = math.radians(328)
    return _j(arc,
              leaf_at(CX+rx*math.cos(a1r), CY+ry*math.sin(a1r), 32+90, LS),
              leaf_at(CX+rx*math.cos(a2r), CY+ry*math.sin(a2r), 328-90, LS)), _adv(W)

def glyph_D():
    W=WW; L=SB; Lx=L+SW//2
    stem  = stroke(Lx, BASE, Lx, CAP, SW)
    bowl  = arc_stroke(Lx, CAP//2, W-SW, CAP//2, 270, 90)
    return _j(stem, bowl,
              leaf_pair(Lx, CAP, 90),
              leaf_pair(Lx, BASE, 270)), _adv(W)

def glyph_E():
    W=WN; L=SB; Lx=L+SW//2; mid=int(CAP*0.50); R=SB+W
    stem = stroke(Lx, BASE, Lx, CAP, SW)
    t    = stroke(Lx, CAP, R, CAP, SW)
    m    = stroke(Lx, mid, R-W//5, mid, SW)
    b    = stroke(Lx, BASE, R, BASE, SW)
    return _j(stem, t, m, b,
              leaf_at(R, CAP, 0, int(LS*0.85)),
              leaf_at(R-W//5, mid, 0, int(LS*0.75)),
              leaf_at(R, BASE, 340, int(LS*0.80))), _adv(W)

def glyph_F():
    W=WN; L=SB; Lx=L+SW//2; mid=int(CAP*0.54); R=SB+W
    stem = stroke(Lx, BASE, Lx, CAP, SW)
    t    = stroke(Lx, CAP, R, CAP, SW)
    m    = stroke(Lx, mid, R-W//4, mid, SW)
    return _j(stem, t, m,
              leaf_at(R, CAP, 0, int(LS*0.85)),
              leaf_at(R-W//4, mid, 0, int(LS*0.75)),
              tl(Lx, BASE, 270)), _adv(W)

def glyph_G():
    W=WW; CX=SB+W//2; CY=CAP//2
    rx=W//2-SW//2; ry=CAP//2-SW//2
    arc  = arc_stroke(CX, CY, rx, ry, 12, 328)
    spur = stroke(CX, CY, CX+rx, CY, SW)
    a1r  = math.radians(12); a2r = math.radians(328)
    return _j(arc, spur,
              leaf_at(CX+rx*math.cos(a1r), CY+ry*math.sin(a1r), 12+90, LS),
              leaf_at(CX+rx*math.cos(a2r), CY+ry*math.sin(a2r), 328-90, LS)), _adv(W)

def glyph_H():
    W=WN; L=SB; R=SB+W; cy=int(CAP*0.48)
    ls = stroke(L+SW//2, BASE, L+SW//2, CAP, SW)
    rs = stroke(R-SW//2, BASE, R-SW//2, CAP, SW)
    br = stroke(L+SW, cy, R-SW, cy, SW)
    return _j(ls, rs, br,
              leaf_pair(L+SW//2, CAP, 90),
              leaf_pair(R-SW//2, CAP, 90),
              tl(L+SW//2, BASE, 250), tl(R-SW//2, BASE, 290)), _adv(W)

def glyph_I():
    W=WNR; CX=SB+W//2
    stem = stroke(CX, BASE, CX, CAP, SW)
    t    = stroke(CX-W//3, CAP, CX+W//3, CAP, SW)
    b    = stroke(CX-W//3, BASE, CX+W//3, BASE, SW)
    return _j(stem, t, b,
              bud_at(CX, CAP, 90, BS), tl(CX, BASE, 270)), _adv(W)

def glyph_J():
    W=WNR; R=SB+W; Rx=R-SW//2; hcy=int(CAP*0.22)
    stem = stroke(Rx, hcy, Rx, CAP, SW)
    t    = stroke(Rx-W//2, CAP, Rx+W//4, CAP, SW)
    hook = arc_stroke(Rx-W//3, hcy, W//3, int(CAP*0.20), 0, 180)
    return _j(stem, t, hook,
              bud_at(Rx, CAP, 90, BS),
              leaf_at(Rx-W//3-W//3, hcy, 180, LS)), _adv(W)

def glyph_K():
    W=WN; L=SB; Lx=L+SW//2; R=SB+W; mid=int(CAP*0.48)
    stem = stroke(Lx, BASE, Lx, CAP, SW)
    ku   = stroke(Lx+SW, mid, R, CAP, SW)
    kl   = stroke(Lx+SW, mid, R, BASE, SW)
    return _j(stem, ku, kl,
              leaf_pair(Lx, CAP, 90),
              leaf_at(R, CAP, 45, LS), leaf_at(R, BASE, 315, LS)), _adv(W)

def glyph_L():
    W=WN; L=SB; Lx=L+SW//2; R=SB+W
    stem = stroke(Lx, BASE, Lx, CAP, SW)
    base_= stroke(Lx, BASE, R, BASE, SW)
    return _j(stem, base_,
              bud_at(Lx, CAP, 90, BS),
              leaf_at(R, BASE, 0, int(LS*0.90))), _adv(W)

def glyph_M():
    W=WM; L=SB; R=SB+W; CX=(L+R)//2
    ls = stroke(L+SW//2, BASE, L+SW//2, CAP, SW)
    rs = stroke(R-SW//2, BASE, R-SW//2, CAP, SW)
    ld = stroke(L+SW, CAP, CX, int(CAP*0.38), SW)
    rd = stroke(R-SW, CAP, CX, int(CAP*0.38), SW)
    return _j(ls, rs, ld, rd,
              leaf_pair(L+SW//2, CAP, 90),
              leaf_pair(R-SW//2, CAP, 90)), _adv(W)

def glyph_N():
    W=WN; L=SB; R=SB+W
    ls = stroke(L+SW//2, BASE, L+SW//2, CAP, SW)
    rs = stroke(R-SW//2, BASE, R-SW//2, CAP, SW)
    dg = stroke(L+SW,    CAP,  R-SW,    BASE, SW)
    return _j(ls, rs, dg,
              leaf_pair(L+SW//2, CAP, 90),
              leaf_pair(R-SW//2, CAP, 90)), _adv(W)

def glyph_O():
    W=WW; CX=SB+W//2; CY=CAP//2
    body = oval_stroke(CX, CY, W//2-SW//2, CAP//2-SW//2)
    return _j(body,
              leaf_pair(CX, CAP-SW//2, 0, int(LS*0.72))), _adv(W)

def glyph_P():
    W=WN; L=SB; Lx=L+SW//2; mid=int(CAP*0.50)
    stem  = stroke(Lx, BASE, Lx, CAP, SW)
    bowl  = arc_stroke(Lx, mid+(CAP-mid)//2, int((W-SW)*0.90), (CAP-mid)//2, 270, 90)
    return _j(stem, bowl,
              leaf_pair(Lx, CAP, 90),
              tl(Lx, BASE, 270)), _adv(W)

def glyph_Q():
    W=WW; CX=SB+W//2; CY=CAP//2; rx=W//2-SW//2; ry=CAP//2-SW//2
    body = oval_stroke(CX, CY, rx, ry)
    tail = stroke(CX+rx*0.4, CY-ry*0.4, CX+rx+SW, CY-ry-SW*2, SW)
    return _j(body, tail,
              leaf_pair(CX, CAP-SW//2, 0, int(LS*0.72))), _adv(W)

def glyph_R():
    W=WN; L=SB; Lx=L+SW//2; R=SB+W; mid=int(CAP*0.50)
    stem = stroke(Lx, BASE, Lx, CAP, SW)
    bowl = arc_stroke(Lx, mid+(CAP-mid)//2, int((W-SW)*0.90), (CAP-mid)//2, 270, 90)
    leg  = stroke(Lx+int((W-SW)*0.90*0.6), mid, R, BASE, SW)
    return _j(stem, bowl, leg,
              leaf_pair(Lx, CAP, 90),
              leaf_at(R, BASE, 315, LS)), _adv(W)

def glyph_S():
    W=WN; CX=SB+W//2; rx=W//2-SW//2
    cyt  = int(CAP*0.70); ryt = int(CAP*0.24)
    cyb  = int(CAP*0.30); ryb = int(CAP*0.24)
    top  = arc_stroke(CX, cyt, rx, ryt, 195, 355)
    bot  = arc_stroke(CX, cyb, rx, ryb,  15, 175)
    a1r  = math.radians(195); a2r = math.radians(355)
    b1r  = math.radians(15);  b2r = math.radians(175)
    return _j(top, bot,
              leaf_at(CX+rx*math.cos(a1r), cyt+ryt*math.sin(a1r), 195-90, int(LS*0.85)),
              leaf_at(CX+rx*math.cos(b2r), cyb+ryb*math.sin(b2r), 175+90, int(LS*0.85))), _adv(W)

def glyph_T():
    W=WN; L=SB; R=SB+W; CX=(L+R)//2
    stem = stroke(CX, BASE, CX, CAP, SW)
    top  = stroke(L, CAP, R, CAP, SW)
    return _j(stem, top,
              leaf_at(L, CAP, 150, LS),
              leaf_at(R, CAP, 30, LS),
              tl(CX, BASE, 270)), _adv(W)

def glyph_U():
    W=WN; L=SB; R=SB+W; CX=(L+R)//2; bcy=int(CAP*0.28); brx=(R-L-SW)//2
    ls   = stroke(L+SW//2, bcy, L+SW//2, CAP, SW)
    rs   = stroke(R-SW//2, bcy, R-SW//2, CAP, SW)
    bowl = arc_stroke(CX, bcy, brx, int(CAP*0.28), 180, 0)
    return _j(ls, rs, bowl,
              leaf_pair(L+SW//2, CAP, 90),
              leaf_pair(R-SW//2, CAP, 90)), _adv(W)

def glyph_V():
    W=WN; L=SB; R=SB+W; CX=(L+R)//2
    ld = stroke(L, CAP, CX, BASE, SW)
    rd = stroke(R, CAP, CX, BASE, SW)
    return _j(ld, rd,
              leaf_pair(L, CAP, 120),
              leaf_pair(R, CAP, 60),
              tl(CX, BASE, 270)), _adv(W)

def glyph_W():
    W=WM; L=SB; R=SB+W; CX=(L+R)//2; q1=(L*2+R)//3; q2=(L+R*2)//3
    d1 = stroke(L,  CAP, q1, BASE, SW)
    d2 = stroke(q1, BASE, CX, int(CAP*0.44), SW)
    d3 = stroke(CX, int(CAP*0.44), q2, BASE, SW)
    d4 = stroke(q2, BASE, R, CAP, SW)
    return _j(d1, d2, d3, d4,
              leaf_pair(L, CAP, 120),
              leaf_pair(R, CAP, 60)), _adv(W)

def glyph_X():
    W=WN; L=SB; R=SB+W
    d1 = stroke(L, CAP, R, BASE, SW)
    d2 = stroke(R, CAP, L, BASE, SW)
    return _j(d1, d2,
              leaf_at(L, CAP, 150, LS), leaf_at(R, CAP, 30, LS),
              tl(L, BASE, 210), tl(R, BASE, 330)), _adv(W)

def glyph_Y():
    W=WN; L=SB; R=SB+W; CX=(L+R)//2; mid=int(CAP*0.46)
    lu   = stroke(L, CAP, CX, mid, SW)
    ru   = stroke(R, CAP, CX, mid, SW)
    stem = stroke(CX, BASE, CX, mid, SW)
    return _j(lu, ru, stem,
              leaf_pair(L, CAP, 120),
              leaf_pair(R, CAP, 60),
              tl(CX, BASE, 270)), _adv(W)

def glyph_Z():
    W=WN; L=SB; R=SB+W
    t  = stroke(L, CAP, R, CAP, SW)
    b  = stroke(L, BASE, R, BASE, SW)
    dg = stroke(R, CAP, L, BASE, SW)
    return _j(t, b, dg,
              leaf_at(R, CAP, 45, LS),
              leaf_at(L, BASE, 225, LS)), _adv(W)

# ── LOWERCASE ─────────────────────────────────────────────────────

def glyph_a():
    W=WLN; L=SB; R=SB+W; CX=(L+R)//2; CY=XH//2
    rx=W//2-SW//2; ry=XH//2-SW//4
    bowl  = arc_stroke(CX, CY, rx, ry, 22, 338)
    stem  = stroke(R-SW//2, BASE, R-SW//2, XH, SW)
    return _j(bowl, stem, bud_at(CX, XH, 90, int(BS*0.85))), _adv(W)

def glyph_b():
    W=WLN; L=SB; Lx=L+SW//2
    stem = stroke(Lx, BASE, Lx, CAP, SW)
    bowl = arc_stroke(Lx, XH//2, W-SW, XH//2, 270, 90)
    return _j(stem, bowl,
              bud_at(Lx, CAP, 90, int(BS*0.85))), _adv(W)

def glyph_c():
    W=WLN; CX=SB+W//2; CY=XH//2; rx=W//2-SW//2; ry=XH//2-SW//4
    arc  = arc_stroke(CX, CY, rx, ry, 35, 325)
    a1r  = math.radians(35); a2r = math.radians(325)
    return _j(arc,
              leaf_at(CX+rx*math.cos(a1r), CY+ry*math.sin(a1r), 35+90, int(LS*0.78)),
              leaf_at(CX+rx*math.cos(a2r), CY+ry*math.sin(a2r), 325-90, int(LS*0.70))), _adv(W)

def glyph_d():
    W=WLN; R=SB+W; Rx=R-SW//2
    stem = stroke(Rx, BASE, Rx, CAP, SW)
    bowl = arc_stroke(Rx, XH//2, W-SW, XH//2, 90, 270)
    return _j(stem, bowl, bud_at(Rx, CAP, 90, int(BS*0.85))), _adv(W)

def glyph_e():
    W=WLN; L=SB; R=SB+W; CX=(L+R)//2; CY=XH//2; rx=W//2-SW//2; ry=XH//2-SW//4
    arc  = arc_stroke(CX, CY, rx, ry, 8, 320)
    bar  = stroke(CX-rx+SW, CY, CX+rx-SW, CY, SW-6)
    a1r  = math.radians(8)
    tx   = CX+rx*math.cos(a1r); ty = CY+ry*math.sin(a1r)
    return _j(arc, bar, leaf_at(tx, ty, 8+90, int(LS*0.78))), _adv(W)

def glyph_f():
    W=WLN2; CX=SB+W//2+4; hcx=CX+W//3; hcy=int(CAP*0.82)
    stem  = stroke(CX, BASE, CX, hcy, SW)
    hook  = arc_stroke(hcx, hcy, W//3, int(CAP*0.13), 180, 270)
    cross = stroke(CX-W//2, int(XH*0.68), CX+W//2, int(XH*0.68), SW)
    return _j(stem, hook, cross,
              bud_at(hcx+W//3, hcy, 90, int(BS*0.80)),
              tl(CX, BASE, 270)), _adv(W)

def glyph_g():
    W=WLN; L=SB; R=SB+W; CX=(L+R)//2; Rx=R-SW//2
    bowl  = arc_stroke(CX, XH//2, W//2-SW//2, XH//2-SW//4, 22, 338)
    stem  = stroke(Rx, DESC//2, Rx, XH, SW)
    loop  = arc_stroke(CX, DESC//2, (W-SW)//2, abs(DESC//2)-SW//2, 0, 180)
    return _j(bowl, stem, loop, bud_at(CX, XH, 90, int(BS*0.80))), _adv(W)

def glyph_h():
    W=WLN; L=SB; Lx=L+SW//2; acx=Lx+W//3; acy=XH
    stem  = stroke(Lx, BASE, Lx, CAP, SW)
    arch  = arc_stroke(acx, acy, W//3, int(XH*0.30), 180, 0)
    rs    = stroke(acx+W//3, BASE, acx+W//3, XH, SW)
    return _j(stem, arch, rs,
              bud_at(Lx, CAP, 90, int(BS*0.85)),
              tl(Lx, BASE, 250), tl(acx+W//3, BASE, 290)), _adv(W)

def glyph_i():
    W=WLN2; CX=SB+W//2
    stem = stroke(CX, BASE, CX, XH, SW)
    dot  = bud_at(CX, XH+int(BS*0.70), 90, int(BS*0.90))
    return _j(stem, dot, tl(CX, BASE, 270)), _adv(W)

def glyph_j():
    W=WLN2; CX=SB+W//2+W//5
    stem = stroke(CX, DESC//2, CX, XH, SW)
    hook = arc_stroke(CX-W//3, DESC//2, W//3, int(abs(DESC//2)*0.75), 0, 180)
    dot  = bud_at(CX, XH+int(BS*0.70), 90, int(BS*0.90))
    return _j(stem, hook, dot), _adv(W)

def glyph_k():
    W=WLN; L=SB; Lx=L+SW//2; R=SB+W; mid=int(XH*0.50)
    stem = stroke(Lx, BASE, Lx, CAP, SW)
    ku   = stroke(Lx+SW, mid, R, XH, SW)
    kl   = stroke(Lx+SW, mid, R, BASE, SW)
    return _j(stem, ku, kl,
              bud_at(Lx, CAP, 90, int(BS*0.85)),
              leaf_at(R, XH, 45, int(LS*0.78)),
              tl(R, BASE, 315)), _adv(W)

def glyph_l():
    W=WLN2; CX=SB+W//2
    stem = stroke(CX, BASE, CX, CAP, SW)
    bbot = stroke(CX-SW, BASE, CX+SW*2, BASE, SW)
    return _j(stem, bbot, bud_at(CX, CAP, 90, BS)), _adv(W)

def glyph_m():
    W=WLW; L=SB; st=W//3
    s1 = stroke(L+SW//2,       BASE, L+SW//2,       XH, SW)
    a1 = arc_stroke(L+SW+st//2, XH, st//2-2, int(XH*0.28), 180, 0)
    s2 = stroke(L+SW+st,       BASE, L+SW+st,       XH, SW)
    a2 = arc_stroke(L+SW+st+st//2, XH, st//2-2, int(XH*0.28), 180, 0)
    s3 = stroke(L+SW+st*2,     BASE, L+SW+st*2,     XH, SW)
    return _j(s1, a1, s2, a2, s3,
              bud_at(L+SW//2, XH, 90, int(BS*0.75))), _adv(W)

def glyph_n():
    W=WLN; L=SB; Lx=L+SW//2; acx=Lx+W//3
    ls   = stroke(Lx, BASE, Lx, XH, SW)
    arch = arc_stroke(acx, XH, W//3, int(XH*0.30), 180, 0)
    rs   = stroke(acx+W//3, BASE, acx+W//3, XH, SW)
    return _j(ls, arch, rs,
              tl(Lx, BASE, 250), tl(acx+W//3, BASE, 290)), _adv(W)

def glyph_o():
    W=WLN; CX=SB+W//2; CY=XH//2
    body = oval_stroke(CX, CY, W//2-SW//2, XH//2-SW//4)
    return _j(body, leaf_pair(CX, XH-SW//2, 0, int(LS*0.65))), _adv(W)

def glyph_p():
    W=WLN; L=SB; Lx=L+SW//2
    stem = stroke(Lx, DESC//2, Lx, XH, SW)
    bowl = arc_stroke(Lx, XH//2, W-SW, XH//2, 270, 90)
    return _j(stem, bowl, tl(Lx, DESC//2, 270)), _adv(W)

def glyph_q():
    W=WLN; R=SB+W; Rx=R-SW//2
    stem = stroke(Rx, DESC//2, Rx, XH, SW)
    bowl = arc_stroke(Rx, XH//2, W-SW, XH//2, 90, 270)
    return _j(stem, bowl, tl(Rx, DESC//2, 270)), _adv(W)

def glyph_r():
    W=WLN2; L=SB; Lx=L+SW//2; acx=Lx+W//3
    stem = stroke(Lx, BASE, Lx, XH, SW)
    arch = arc_stroke(acx, XH, W//3, int(XH*0.28), 180, 60)
    ar   = math.radians(60)
    tx   = acx + W//3*math.cos(ar); ty = XH + int(XH*0.28)*math.sin(ar)
    return _j(stem, arch,
              leaf_at(tx, ty, 60-90, int(LS*0.72)),
              tl(Lx, BASE, 270)), _adv(W)

def glyph_s():
    W=WLN; CX=SB+W//2; rx=W//2-SW//2
    cyt=int(XH*0.70); ryt=int(XH*0.24)
    cyb=int(XH*0.30); ryb=int(XH*0.24)
    top = arc_stroke(CX, cyt, rx, ryt, 200, 355)
    bot = arc_stroke(CX, cyb, rx, ryb,  20, 175)
    a1r = math.radians(200); b2r = math.radians(175)
    return _j(top, bot,
              leaf_at(CX+rx*math.cos(a1r), cyt+ryt*math.sin(a1r), 200-90, int(LS*0.72)),
              leaf_at(CX+rx*math.cos(b2r), cyb+ryb*math.sin(b2r), 175+90, int(LS*0.72))), _adv(W)

def glyph_t():
    W=WLN2; CX=SB+W//2
    stem  = stroke(CX, BASE, CX, int(CAP*0.80), SW)
    cross = stroke(CX-W//2, int(XH*0.68), CX+W//2, int(XH*0.68), SW)
    return _j(stem, cross,
              leaf_at(CX-W//2, int(XH*0.68), 150, int(LS*0.72)),
              leaf_at(CX+W//2, int(XH*0.68), 30, int(LS*0.72)),
              tl(CX, BASE, 270)), _adv(W)

def glyph_u():
    W=WLN; L=SB; R=SB+W; CX=(L+R)//2; bcy=int(XH*0.32); brx=(R-L-SW)//2
    ls   = stroke(L+SW//2, bcy, L+SW//2, XH, SW)
    rs   = stroke(R-SW//2, BASE, R-SW//2, XH, SW)
    bowl = arc_stroke(CX, bcy, brx, int(XH*0.32), 180, 0)
    return _j(ls, rs, bowl, tl(L+SW//2, BASE, 270)), _adv(W)

def glyph_v():
    W=WLN; L=SB; R=SB+W; CX=(L+R)//2
    ld = stroke(L, XH, CX, BASE, SW)
    rd = stroke(R, XH, CX, BASE, SW)
    return _j(ld, rd,
              leaf_pair(L, XH, 120, int(LS*0.75)),
              leaf_pair(R, XH, 60, int(LS*0.75))), _adv(W)

def glyph_w():
    W=WLW; L=SB; R=SB+W; CX=(L+R)//2; q1=(L*2+R)//3; q2=(L+R*2)//3
    d1 = stroke(L,  XH, q1, BASE, SW)
    d2 = stroke(q1, BASE, CX, int(XH*0.45), SW)
    d3 = stroke(CX, int(XH*0.45), q2, BASE, SW)
    d4 = stroke(q2, BASE, R, XH, SW)
    return _j(d1, d2, d3, d4,
              leaf_pair(L, XH, 120, int(LS*0.72)),
              leaf_pair(R, XH, 60, int(LS*0.72))), _adv(W)

def glyph_x():
    W=WLN; L=SB; R=SB+W
    d1 = stroke(L, XH, R, BASE, SW)
    d2 = stroke(R, XH, L, BASE, SW)
    return _j(d1, d2,
              tl(L, XH, 150), tl(R, XH, 30),
              tl(L, BASE, 210), tl(R, BASE, 330)), _adv(W)

def glyph_y():
    W=WLN; L=SB; R=SB+W; CX=(L+R)//2; mid=int(XH*0.44)
    lu   = stroke(L, XH, CX, mid, SW)
    ru   = stroke(R, XH, CX, mid, SW)
    stem = stroke(CX, DESC//2, CX, mid, SW)
    hook = arc_stroke(CX-(W-SW)//2, DESC//2, (W-SW)//2, abs(DESC//2)-SW//2, 0, 180)
    return _j(lu, ru, stem, hook,
              leaf_pair(L, XH, 120, int(LS*0.75)),
              leaf_pair(R, XH, 60, int(LS*0.75))), _adv(W)

def glyph_z():
    W=WLN; L=SB; R=SB+W
    t  = stroke(L, XH, R, XH, SW)
    b  = stroke(L, BASE, R, BASE, SW)
    dg = stroke(R, XH, L, BASE, SW)
    return _j(t, b, dg,
              leaf_at(R, XH, 45, int(LS*0.78)),
              leaf_at(L, BASE, 225, int(LS*0.78))), _adv(W)

# ── NUMERALS ──────────────────────────────────────────────────────

def glyph_0():
    W=WW; CX=SB+W//2; CY=CAP//2
    body = oval_stroke(CX, CY, W//2-SW//2, CAP//2-SW//2)
    return _j(body, leaf_pair(CX, CAP-SW//2, 0, int(LS*0.68))), _adv(W)

def glyph_1():
    W=WNR; CX=SB+W//2
    stem  = stroke(CX, BASE, CX, CAP, SW)
    base_ = stroke(CX-W//3, BASE, CX+W//2, BASE, SW)
    shdr  = stroke(CX-W//3, int(CAP*0.76), CX, CAP, SW)
    return _j(stem, base_, shdr, bud_at(CX, CAP, 90, BS)), _adv(W)

def glyph_2():
    W=WN; L=SB; R=SB+W; CX=SB+W//2
    acy=int(CAP*0.70); arx=W//2-SW//2; ary=int(CAP*0.24)
    top  = arc_stroke(CX, acy, arx, ary, 215, 345)
    a2r  = math.radians(345)
    tx   = CX+arx*math.cos(a2r); ty = acy+ary*math.sin(a2r)
    diag_= stroke(tx, ty, L, BASE+SW//2, SW)
    base_= stroke(L, BASE, R, BASE, SW)
    return _j(top, diag_, base_,
              leaf_at(tx, ty, 345-90, int(LS*0.78))), _adv(W)

def glyph_3():
    W=WN; CX=SB+W//2; rx=W//2-SW//2
    top  = arc_stroke(CX, int(CAP*0.72), rx, int(CAP*0.24), 215, 340)
    bot  = arc_stroke(CX, int(CAP*0.28), rx, int(CAP*0.26),  20, 340)
    a1r  = math.radians(215); ryt=int(CAP*0.24)
    return _j(top, bot,
              tl(CX+rx*math.cos(a1r), int(CAP*0.72)+ryt*math.sin(a1r), 215-90)), _adv(W)

def glyph_4():
    W=WN; L=SB; R=SB+W; sx=SB+int(W*0.66)
    dg   = stroke(L, CAP, sx-SW//2, int(CAP*0.44), SW)
    bar  = stroke(L, int(CAP*0.44), R, int(CAP*0.44), SW)
    stem = stroke(sx, BASE, sx, CAP, SW)
    return _j(dg, bar, stem,
              leaf_at(L, CAP, 150, int(LS*0.80)),
              bud_at(sx, CAP, 90, BS)), _adv(W)

def glyph_5():
    W=WN; L=SB; R=SB+W; CX=SB+W//2; Lx=L+SW//2
    top  = stroke(L, CAP, R, CAP, SW)
    ls   = stroke(Lx, int(CAP*0.50), Lx, CAP, SW)
    bowl = arc_stroke(CX, int(CAP*0.28), W//2-SW//2, int(CAP*0.26), 175, 355)
    return _j(top, ls, bowl,
              leaf_at(R, CAP, 30, int(LS*0.80)),
              leaf_at(L, CAP, 150, int(LS*0.80))), _adv(W)

def glyph_6():
    W=WN; CX=SB+W//2; rx=W//2-SW//2
    circ = oval_stroke(CX, int(CAP*0.30), rx, int(CAP*0.28))
    tail = arc_stroke(CX, int(CAP*0.62), rx, int(CAP*0.30), 178, 285)
    return _j(circ, tail,
              leaf_pair(CX, int(CAP*0.58+CAP*0.30), 0, int(LS*0.62))), _adv(W)

def glyph_7():
    W=WN; L=SB; R=SB+W
    top  = stroke(L, CAP, R, CAP, SW)
    stem = stroke(R, CAP, SB+W//3, BASE, SW)
    return _j(top, stem,
              leaf_at(L, CAP, 150, int(LS*0.80)),
              leaf_at(R, CAP, 30, int(LS*0.80))), _adv(W)

def glyph_8():
    W=WN; CX=SB+W//2; rx=W//2-SW//2
    top  = oval_stroke(CX, int(CAP*0.72), rx, int(CAP*0.22))
    bot  = oval_stroke(CX, int(CAP*0.28), rx, int(CAP*0.26))
    return _j(top, bot,
              leaf_pair(CX, int(CAP*0.72+CAP*0.22), 0, int(LS*0.62))), _adv(W)

def glyph_9():
    W=WN; CX=SB+W//2; rx=W//2-SW//2
    circ = oval_stroke(CX, int(CAP*0.68), rx, int(CAP*0.26))
    tail = arc_stroke(CX, int(CAP*0.38), rx, int(CAP*0.28), 355, 100)
    return _j(circ, tail,
              leaf_pair(CX, int(CAP*0.94), 0, int(LS*0.62))), _adv(W)

# ── PUNCTUATION ───────────────────────────────────────────────────

def _small_circle(cx, cy, r):
    return (f"M{cx:.1f},{cy-r:.1f} "
            f"C{cx+r*K:.1f},{cy-r:.1f} {cx+r:.1f},{cy-r*K:.1f} {cx+r:.1f},{cy:.1f} "
            f"C{cx+r:.1f},{cy+r*K:.1f} {cx+r*K:.1f},{cy+r:.1f} {cx:.1f},{cy+r:.1f} "
            f"C{cx-r*K:.1f},{cy+r:.1f} {cx-r:.1f},{cy+r*K:.1f} {cx-r:.1f},{cy:.1f} "
            f"C{cx-r:.1f},{cy-r*K:.1f} {cx-r*K:.1f},{cy-r:.1f} {cx:.1f},{cy-r:.1f} Z")

def glyph_period():
    CX=SB+SW; r=int(SW*0.7)
    return _small_circle(CX, BASE+r, r), _adv(SW*2)

def glyph_comma():
    CX=SB+SW; r=int(SW*0.7)
    dot  = _small_circle(CX, BASE+r, r)
    tail = stroke(CX, BASE+r, CX-int(SW*0.8), BASE-int(SW*1.5), int(SW*0.5))
    return _j(dot, tail), _adv(SW*2)

def glyph_excl():
    CX=SB+SW
    bar = stroke(CX, int(XH*0.30), CX, XH, SW)
    dot = _small_circle(CX, BASE+int(SW*0.7), int(SW*0.7))
    return _j(bar, dot, bud_at(CX, XH, 90, int(BS*0.80))), _adv(SW*2)

def glyph_question():
    W=WLN2; CX=SB+W//2
    arc  = arc_stroke(CX, int(CAP*0.66), W//3, int(CAP*0.20), 215, 355)
    stem = stroke(CX, int(XH*0.28), CX, int(CAP*0.48), SW)
    dot  = _small_circle(CX, BASE+int(SW*0.7), int(SW*0.7))
    return _j(arc, stem, dot), _adv(W)

def glyph_dash():
    W=WN//2
    return stroke(SB, CAP//2, SB+W, CAP//2, SW), _adv(W)

def glyph_colon():
    CX=SB+SW; r=int(SW*0.7)
    d1 = _small_circle(CX, BASE+r, r)
    d2 = _small_circle(CX, XH//2+r, r)
    return _j(d1, d2), _adv(SW*2)

# ── GLYPH MAP ─────────────────────────────────────────────────────
GLYPHS = {
    'A':glyph_A,'B':glyph_B,'C':glyph_C,'D':glyph_D,'E':glyph_E,
    'F':glyph_F,'G':glyph_G,'H':glyph_H,'I':glyph_I,'J':glyph_J,
    'K':glyph_K,'L':glyph_L,'M':glyph_M,'N':glyph_N,'O':glyph_O,
    'P':glyph_P,'Q':glyph_Q,'R':glyph_R,'S':glyph_S,'T':glyph_T,
    'U':glyph_U,'V':glyph_V,'W':glyph_W,'X':glyph_X,'Y':glyph_Y,'Z':glyph_Z,
    'a':glyph_a,'b':glyph_b,'c':glyph_c,'d':glyph_d,'e':glyph_e,
    'f':glyph_f,'g':glyph_g,'h':glyph_h,'i':glyph_i,'j':glyph_j,
    'k':glyph_k,'l':glyph_l,'m':glyph_m,'n':glyph_n,'o':glyph_o,
    'p':glyph_p,'q':glyph_q,'r':glyph_r,'s':glyph_s,'t':glyph_t,
    'u':glyph_u,'v':glyph_v,'w':glyph_w,'x':glyph_x,'y':glyph_y,'z':glyph_z,
    '0':glyph_0,'1':glyph_1,'2':glyph_2,'3':glyph_3,'4':glyph_4,
    '5':glyph_5,'6':glyph_6,'7':glyph_7,'8':glyph_8,'9':glyph_9,
    '.':glyph_period,',':glyph_comma,'!':glyph_excl,'?':glyph_question,
    '-':glyph_dash,':':glyph_colon,
}

# ── FONT BUILDER ──────────────────────────────────────────────────

def _to_glyph(path_d):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg">'
           f'<path d="{path_d}" fill-rule="evenodd"/></svg>')
    pen = TTGlyphPen(None)
    SVGPathLib(io.BytesIO(svg.encode())).draw(
        Cu2QuPen(pen, max_err=0.6, reverse_direction=True))
    return pen.glyph()

def _empty():
    pen = TTGlyphPen(None)
    pen.moveTo((0,0)); pen.lineTo((1,0)); pen.lineTo((1,1)); pen.lineTo((0,1))
    pen.closePath(); return pen.glyph()

def build(output_path="VectrodFloral.ttf", font_name="VectrodFloral"):
    chars  = sorted(GLYPHS.keys())
    gnames = ['.notdef','space'] + [f'uni{ord(c):04X}' for c in chars]

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(gnames)
    fb.setupCharacterMap({32:'space', **{ord(c):f'uni{ord(c):04X}' for c in chars}})

    glyph_map = {'.notdef': _empty(), 'space': _empty()}
    metrics   = {'.notdef': (500,0),  'space': (220,0)}

    ok = fail = 0
    for c in chars:
        gn = f'uni{ord(c):04X}'
        try:
            path, adv = GLYPHS[c]()
            if not path.strip():
                raise ValueError("empty path")
            glyph_map[gn] = _to_glyph(path)
            metrics[gn]   = (adv, 0)
            ok += 1
        except Exception as e:
            print(f"  ✗ '{c}': {e}")
            glyph_map[gn] = _empty()
            metrics[gn]   = (500, 0)
            fail += 1

    # Cu2Qu refinement pass
    conv = {}
    for gn, g in glyph_map.items():
        if not hasattr(g, 'draw'): conv[gn] = g; continue
        try:
            p2 = TTGlyphPen(None)
            g.draw(Cu2QuPen(p2, max_err=0.6, reverse_direction=False))
            conv[gn] = p2.glyph()
        except:
            conv[gn] = g

    ASC = CAP + LS + BS + 40
    DSC = DESC - 20

    fb.setupGlyf(conv)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASC, descent=DSC)
    fb.setupNameTable({
        "familyName": font_name, "styleName": "Regular",
        "uniqueFontIdentifier": f"{font_name}-Regular",
        "fullName": f"{font_name} Regular",
        "version": "Version 2.0",
        "psName": f"{font_name}-Regular",
    })
    fb.setupOS2(
        sTypoAscender=ASC, sTypoDescender=DSC, sTypoLineGap=0,
        usWinAscent=ASC+20, usWinDescent=abs(DSC),
        sxHeight=XH, sCapHeight=CAP,
        usWeightClass=300, fsType=0, fsSelection=0x40, achVendID="VCTD",
        ulUnicodeRange1=0b10000000000000000000000011111111,
    )
    fb.setupPost(isFixedPitch=0, underlinePosition=-100, underlineThickness=SW)
    fb.setupHead(unitsPerEm=UPM, lowestRecPPEM=8, indexToLocFormat=0)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    fb.font.save(output_path)

    sz = os.path.getsize(output_path) / 1024
    print(f"  ✅ {sz:.1f} KB  |  {ok} ✓  {fail} ✗  |  {output_path}")
    return output_path

if __name__ == '__main__':
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/vf2/VectrodFloral.ttf'
    build(out)
