"""
cyber_engine.py — Vectrod Cyber/Tech/Gothic Font Engine
=========================================================
Handles: cyberpunk, neon, tech, gothic, retro, bold, display styles.

Design DNA → glyph features:
  sharp_terminals → clipped diagonal ends (not rounded)
  inline          → engraved inner line through stroke
  condensed       → adv * factor
  expanded        → adv * factor
  slab_serif      → rectangular serifs at stem ends
  rounded_corners → beveled/rounded joins
  bold/heavy      → SW 60-120

UPM=1000, CAP=700, XH=480, BASE=0, DESC=-150
fill-rule=evenodd → inline grooves cut through stroke automatically
"""
import math, io, os
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen  import TTGlyphPen
from fontTools.pens.cu2quPen    import Cu2QuPen
from fontTools.svgLib.path      import SVGPath as SVGPathLib

# ── CONSTANTS ────────────────────────────────────────────────────
UPM  = 1000
CAP  = 700
XH   = 480
BASE = 0
DESC = -150
K    = 0.5523   # bezier circle constant

# ── HELPERS ──────────────────────────────────────────────────────
def _j(*parts):
    return " ".join(p for p in parts if p and p.strip())

class CyberGlyphBuilder:
    """
    Builds one glyph from DNA parameters.
    DNA keys used:
      sw (int)              — stroke weight
      condensed (float)     — width factor (default 1.0)
      expanded  (float)     — width factor (default 1.0)
      sharp_terminals (bool)— clip ends at angle
      inline (float)        — inner groove ratio (0.22 = groove width 22% of sw)
      slab_serif (float)    — slab height as ratio of sw (0 = none)
      rounded_corners (bool)— slightly round joins
      decorations (list)    — [{shape, anchor, scale, angle, every_nth}]
      char_index (int)      — position in alphabet (for every_nth)
    """
    def __init__(self, dna: dict):
        self.sw   = int(dna.get('stroke_weight', 52))
        self.sw   = max(18, min(120, self.sw))

        # Width scale
        width_scale = 1.0
        for e in dna.get('effects', []):
            if e['name'] == 'condensed':
                width_scale = float(e['params'].get('factor', 0.82))
            elif e['name'] == 'expanded':
                width_scale = float(e['params'].get('factor', 1.20))
        self.ws   = width_scale

        # Effects
        eff_names = {e['name']: e.get('params', {}) for e in dna.get('effects', [])}
        self.sharp     = 'sharp_terminals' in eff_names
        self.inline_r  = float(eff_names.get('inline', {}).get('thin_ratio', 0)) if 'inline' in eff_names else 0
        self.slab_r    = float(eff_names.get('slab_serif', {}).get('height_ratio', 0)) if 'slab_serif' in eff_names else 0
        self.slab_w    = float(eff_names.get('slab_serif', {}).get('width_ratio', 2.5)) if 'slab_serif' in eff_names else 2.5
        self.rounded   = 'rounded_corners' in eff_names

        self.decorations = dna.get('decorations', [])
        self.dna = dna

    # ── PRIMITIVE STROKES ─────────────────────────────────────────

    def _stroke(self, x1, y1, x2, y2, sw=None, sharp=None):
        """Filled capsule stroke. sharp=True → diagonal clip ends."""
        if sw is None: sw = self.sw
        sw = max(4, sw)
        if sharp is None: sharp = self.sharp
        dx, dy = x2-x1, y2-y1
        ln = math.hypot(dx, dy)
        if ln < 1: return ""
        nx, ny = -dy/ln*(sw/2),  dx/ln*(sw/2)
        ux, uy =  dx/ln*(sw/2),  dy/ln*(sw/2)

        if sharp:
            # Sharp diagonal cut: parallelogram shape
            return (
                f"M{x1+nx:.1f},{y1+ny:.1f} "
                f"L{x2+nx:.1f},{y2+ny:.1f} "
                f"L{x2-nx:.1f},{y2-ny:.1f} "
                f"L{x1-nx:.1f},{y1-ny:.1f} Z"
            )
        else:
            # Round caps
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

    def _slab(self, cx, y, sw=None):
        """Rectangular slab serif at (cx, y)."""
        if self.slab_r <= 0: return ""
        if sw is None: sw = self.sw
        sh  = max(6, int(sw * self.slab_r))
        sw2 = int(sw * self.slab_w)
        x1, x2 = cx - sw2//2, cx + sw2//2
        if self.rounded:
            r = min(sh//2, 4)
            return (
                f"M{x1+r:.1f},{y:.1f} L{x2-r:.1f},{y:.1f} "
                f"C{x2:.1f},{y:.1f} {x2:.1f},{y:.1f} {x2:.1f},{y-r:.1f} "
                f"L{x2:.1f},{y-sh+r:.1f} "
                f"C{x2:.1f},{y-sh:.1f} {x2:.1f},{y-sh:.1f} {x2-r:.1f},{y-sh:.1f} "
                f"L{x1+r:.1f},{y-sh:.1f} "
                f"C{x1:.1f},{y-sh:.1f} {x1:.1f},{y-sh:.1f} {x1:.1f},{y-sh+r:.1f} "
                f"L{x1:.1f},{y-r:.1f} "
                f"C{x1:.1f},{y:.1f} {x1:.1f},{y:.1f} {x1+r:.1f},{y:.1f} Z"
            )
        return (f"M{x1:.1f},{y:.1f} L{x2:.1f},{y:.1f} "
                f"L{x2:.1f},{y-sh:.1f} L{x1:.1f},{y-sh:.1f} Z")

    def _inline_groove(self, x1, y1, x2, y2, sw=None):
        """Thin engraved line through center of stroke (evenodd punches hole)."""
        if self.inline_r <= 0: return ""
        if sw is None: sw = self.sw
        groove_w = max(3, int(sw * self.inline_r))
        return self._stroke(x1, y1, x2, y2, groove_w, sharp=True)

    def _oval(self, cx, cy, rx, ry):
        """Filled ellipse (outer bowl)."""
        kx, ky = rx*K, ry*K
        return (
            f"M{cx:.1f},{cy-ry:.1f} "
            f"C{cx+kx:.1f},{cy-ry:.1f} {cx+rx:.1f},{cy-ky:.1f} {cx+rx:.1f},{cy:.1f} "
            f"C{cx+rx:.1f},{cy+ky:.1f} {cx+kx:.1f},{cy+ry:.1f} {cx:.1f},{cy+ry:.1f} "
            f"C{cx-kx:.1f},{cy+ry:.1f} {cx-rx:.1f},{cy+ky:.1f} {cx-rx:.1f},{cy:.1f} "
            f"C{cx-rx:.1f},{cy-ky:.1f} {cx-kx:.1f},{cy-ry:.1f} {cx:.1f},{cy-ry:.1f} Z"
        )

    def _counter(self, cx, cy, rx, ry):
        """Counter-clockwise hole (evenodd punch)."""
        kx, ky = rx*K, ry*K
        return (
            f"M{cx:.1f},{cy-ry:.1f} "
            f"C{cx-kx:.1f},{cy-ry:.1f} {cx-rx:.1f},{cy-ky:.1f} {cx-rx:.1f},{cy:.1f} "
            f"C{cx-rx:.1f},{cy+ky:.1f} {cx-kx:.1f},{cy+ry:.1f} {cx:.1f},{cy+ry:.1f} "
            f"C{cx+kx:.1f},{cy+ry:.1f} {cx+rx:.1f},{cy+ky:.1f} {cx+rx:.1f},{cy:.1f} "
            f"C{cx+rx:.1f},{cy-ky:.1f} {cx+kx:.1f},{cy-ry:.1f} {cx:.1f},{cy-ry:.1f} Z"
        )

    def _arc(self, cx, cy, rx, ry, a1d, a2d, sw=None):
        """Thick arc stroke (polygon approx)."""
        if sw is None: sw = self.sw
        sw = max(4, sw)
        N = 20
        a1 = math.radians(a1d); a2 = math.radians(a2d)
        while a2 <= a1: a2 += 2*math.pi
        pts = [(cx+rx*math.cos(a1+(a2-a1)*i/N),
                cy+ry*math.sin(a1+(a2-a1)*i/N)) for i in range(N+1)]
        half = sw/2
        outer, inner = [], []
        for i, (px, py) in enumerate(pts):
            if i == 0: ddx, ddy = pts[1][0]-px, pts[1][1]-py
            elif i == len(pts)-1: ddx, ddy = px-pts[-2][0], py-pts[-2][1]
            else: ddx, ddy = pts[i+1][0]-pts[i-1][0], pts[i+1][1]-pts[i-1][1]
            ln = math.hypot(ddx, ddy) or 0.001
            nx2, ny2 = -ddy/ln*half, ddx/ln*half
            outer.append((px+nx2, py+ny2))
            inner.append((px-nx2, py-ny2))

        parts = [f"M{outer[0][0]:.1f},{outer[0][1]:.1f}"]
        for p in outer[1:]: parts.append(f"L{p[0]:.1f},{p[1]:.1f}")
        i_end = inner[-1]
        parts.append(f"L{i_end[0]:.1f},{i_end[1]:.1f}")
        for p in reversed(inner[:-1]): parts.append(f"L{p[0]:.1f},{p[1]:.1f}")
        parts.append("Z")
        return " ".join(parts)

    # ── DECORATION SHAPES ─────────────────────────────────────────

    def _deco_shape(self, name, cx, cy, size, angle_deg):
        """Render a decoration shape at (cx,cy) with given size and rotation."""
        a  = math.radians(angle_deg)
        ca, sa = math.cos(a), math.sin(a)

        def rot(lx, ly):
            return cx+lx*ca-ly*sa, cy+lx*sa+ly*ca

        if name == 'lightning':
            # Zigzag bolt
            pts = [(0,size*0.5),(size*0.15,-size*0.05),
                   (size*0.05,-size*0.05),(size*0.25,-size*0.5)]
            rpts = [rot(p[0]-size*0.12, p[1]) for p in pts]
            sw2 = max(3, int(size*0.18))
            parts = []
            for i in range(len(rpts)-1):
                parts.append(self._stroke(rpts[i][0],rpts[i][1],
                                          rpts[i+1][0],rpts[i+1][1], sw2, sharp=True))
            return _j(*parts)

        elif name == 'diamond':
            t,r,b,l = rot(0,size*0.48), rot(size*0.30,0), rot(0,-size*0.48), rot(-size*0.30,0)
            sw2 = max(3, int(size*0.16))
            s1 = self._stroke(t[0],t[1],r[0],r[1],sw2,sharp=True)
            s2 = self._stroke(r[0],r[1],b[0],b[1],sw2,sharp=True)
            s3 = self._stroke(b[0],b[1],l[0],l[1],sw2,sharp=True)
            s4 = self._stroke(l[0],l[1],t[0],t[1],sw2,sharp=True)
            return _j(s1,s2,s3,s4)

        elif name == 'hexagon':
            verts = [rot(size*0.38*math.cos(math.radians(60*i)),
                         size*0.38*math.sin(math.radians(60*i))) for i in range(6)]
            sw2 = max(3, int(size*0.14))
            parts = []
            for i in range(6):
                a2, b2 = verts[i], verts[(i+1)%6]
                parts.append(self._stroke(a2[0],a2[1],b2[0],b2[1],sw2,sharp=True))
            return _j(*parts)

        elif name == 'cross':
            sw2 = max(3, int(size*0.20))
            h1  = self._stroke(*rot(-size*0.4,0), *rot(size*0.4,0), sw2)
            h2  = self._stroke(*rot(0,-size*0.4), *rot(0,size*0.4), sw2)
            return _j(h1,h2)

        elif name == 'arrow_right':
            sw2 = max(3, int(size*0.18))
            tip = rot(size*0.4, 0)
            bl  = rot(-size*0.1, -size*0.3)
            tl  = rot(-size*0.1,  size*0.3)
            body= self._stroke(*rot(-size*0.4,0), *tip, sw2, sharp=True)
            head= self._stroke(*bl, *tip, sw2, sharp=True)
            head2=self._stroke(*tl, *tip, sw2, sharp=True)
            return _j(body, head, head2)

        elif name == 'gear_tooth':
            # Simplified gear tooth
            sw2 = max(3, int(size*0.20))
            pts = [rot(-size*0.2,0),rot(-size*0.1,size*0.4),
                   rot(size*0.1,size*0.4),rot(size*0.2,0)]
            parts = []
            for i in range(len(pts)-1):
                parts.append(self._stroke(pts[i][0],pts[i][1],
                                          pts[i+1][0],pts[i+1][1],sw2,sharp=True))
            return _j(*parts)

        elif name == 'flower':
            # Soft flower fallback for non-cyber modes
            petals = 5; inner_r = size*0.18; outer_r = size*0.48
            parts = []
            for i in range(petals):
                a_mid  = 2*math.pi*i/petals - math.pi/2 + a
                spread = math.pi/petals * 0.78
                a1p = a_mid - spread; a2p = a_mid + spread
                b1x = cx+inner_r*math.cos(a1p); b1y = cy+inner_r*math.sin(a1p)
                b2x = cx+inner_r*math.cos(a2p); b2y = cy+inner_r*math.sin(a2p)
                tx  = cx+outer_r*math.cos(a_mid); ty = cy+outer_r*math.sin(a_mid)
                side = 0.30
                cp1x = b1x+(tx-b1x)*0.55-(b1y-ty)*side
                cp1y = b1y+(ty-b1y)*0.55-(b1x-tx)*side
                cp2x = tx+(b2x-tx)*0.45+(b2y-ty)*side
                cp2y = ty+(b2y-ty)*0.45-(b2x-tx)*side
                mid_x = (b1x+b2x)/2*0.8; mid_y = (b1y+b2y)/2*0.8
                if i==0: parts.append(f"M{b1x:.1f},{b1y:.1f}")
                parts.append(f"C{cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {tx:.1f},{ty:.1f}")
                parts.append(f"C{cp2x:.1f},{cp2y:.1f} {mid_x:.1f},{mid_y:.1f} {b2x:.1f},{b2y:.1f}")
            parts.append("Z")
            return " ".join(parts)

        elif name == 'leaf':
            h = size*0.62; w = size*0.24
            def r2(lx,ly): return cx+lx*ca-ly*sa, cy+lx*sa+ly*ca
            tip  = r2(h,0); base = r2(-h*0.12,0)
            cl1  = r2(h*0.55, w*0.90); cl2 = r2(-h*0.05, w*0.65)
            cr1  = r2(h*0.55,-w*0.90); cr2 = r2(-h*0.05,-w*0.65)
            return (f"M{tip[0]:.1f},{tip[1]:.1f} "
                    f"C{cl1[0]:.1f},{cl1[1]:.1f} {cl2[0]:.1f},{cl2[1]:.1f} {base[0]:.1f},{base[1]:.1f} "
                    f"C{cr2[0]:.1f},{cr2[1]:.1f} {cr1[0]:.1f},{cr1[1]:.1f} {tip[0]:.1f},{tip[1]:.1f} Z")

        elif name == 'crown_spike':
            # Gothic spike
            sw2 = max(3, int(size*0.20))
            tip = rot(0, size*0.5)
            l   = rot(-size*0.2, 0)
            r2_ = rot( size*0.2, 0)
            return _j(self._stroke(l[0],l[1],tip[0],tip[1],sw2,sharp=True),
                      self._stroke(r2_[0],r2_[1],tip[0],tip[1],sw2,sharp=True))

        elif name == 'ink_drop':
            r2_ = size*0.35
            circ = self._oval(cx, cy, r2_, r2_)
            tail = self._stroke(cx, cy+r2_, cx, cy+r2_+size*0.3, max(3,int(r2_*0.5)))
            return _j(circ, tail)

        else:
            # Unknown shape → tiny diamond as safe fallback
            return self._deco_shape('diamond', cx, cy, size, angle_deg)

    def _place_decos(self, char, adv, anchors, char_idx=0):
        """Place all decorations from DNA onto glyph anchors."""
        from shape_library import get_shape, place
        parts = []
        for dec in self.decorations:
            every_nth = max(1, dec.get('every_nth', 1))
            if char_idx % every_nth != 0:
                continue
            shape = dec.get('shape', 'diamond')
            anchor_type = dec.get('anchor', 'top_right')
            scale = float(dec.get('scale', 1.0))
            angle = float(dec.get('angle', 0))

            size = self.sw * scale * 1.8
            # Find anchor coordinates
            ax, ay = self._anchor_pos(char, adv, anchor_type)
            if ax is None:
                continue
            deco = self._deco_shape(shape, ax, ay, size, angle)
            if deco:
                parts.append(deco)
        return _j(*parts)

    def _anchor_pos(self, char, adv, anchor_type):
        """Return (x, y) for a named anchor on this glyph."""
        # Standard positions based on letter class
        L   = 55 * self.ws
        R   = adv - 55 * self.ws
        CX  = adv / 2
        sw  = self.sw
        is_lower = char.islower()
        top_y = XH if is_lower else CAP

        m = {
            'top_center':  (CX,   top_y + sw//2),
            'top_left':    (L,    top_y + sw//2),
            'top_right':   (R,    top_y + sw//2),
            'base_left':   (L,    BASE),
            'base_right':  (R,    BASE),
            'base_center': (CX,   BASE),
            'bowl_top':    (CX,   top_y * 0.75),
            'bowl_right':  (R,    top_y * 0.5),
            'crossbar':    (CX,   top_y * 0.5),
            'ascender':    (CX,   CAP + sw//2) if is_lower else (CX, CAP + sw//2),
            'descender':   (CX,   DESC),
            'terminal_top':(R - sw, top_y + sw),
        }
        pos = m.get(anchor_type)
        if pos: return pos
        return None

    # ── GLYPH BUILDER ─────────────────────────────────────────────

    def build_glyph(self, char: str, char_idx: int = 0):
        """Returns (svg_path, advance_width) for a character."""
        sw = self.sw
        SB = int(55 * self.ws)

        # Width categories
        WN  = int(520 * self.ws)
        WW  = int(600 * self.ws)
        WNR = int(280 * self.ws)
        WM  = int(640 * self.ws)
        WLN = int(400 * self.ws)
        WLW = int(460 * self.ws)
        WLN2= int(260 * self.ws)

        def adv(W): return W + 2*SB

        def s(x1,y1,x2,y2,sw2=None): return self._stroke(x1,y1,x2,y2,sw2)
        def sl(cx,y): return _j(self._slab(cx,y,sw), self._slab(cx,y-CAP,sw)) if self.slab_r>0 else ""
        def slbase(cx): return self._slab(cx, BASE+self.sw//2, sw) if self.slab_r>0 else ""
        def sltop(cx):  return self._slab(cx, CAP-self.sw//2+int(sw*self.slab_r), sw) if self.slab_r>0 else ""
        def gr(x1,y1,x2,y2): return self._inline_groove(x1,y1,x2,y2)
        def arc(cx,cy,rx,ry,a1,a2,sw2=None): return self._arc(cx,cy,rx,ry,a1,a2,sw2)
        def oval(cx,cy,rx,ry): return self._oval(cx,cy,rx,ry)
        def hole(cx,cy,rx,ry): return self._counter(cx,cy,rx,ry)

        # ── UPPERCASE ──────────────────────────────────────────────
        if char == 'A':
            W=WN; L=SB; R=SB+W; CX=(L+R)//2; by=int(CAP*0.42)
            p = _j(s(L,BASE,CX,CAP), s(R,BASE,CX,CAP), s(L+W//4,by,R-W//4,by),
                   gr(L,BASE,CX,CAP), gr(R,BASE,CX,CAP),
                   slbase(L+sw//2), slbase(R-sw//2))
        elif char == 'B':
            W=WN; L=SB; Lx=L+sw//2; mid=int(CAP*0.50)
            p = _j(s(Lx,BASE,Lx,CAP),
                   arc(Lx,mid+(CAP-mid)//2,int(W*0.44),(CAP-mid)//2,270,90),
                   arc(Lx,mid//2,int(W*0.48),mid//2,270,90),
                   gr(Lx,BASE,Lx,CAP), sltop(Lx), slbase(Lx))
        elif char == 'C':
            W=WW; CX=SB+W//2; CY=CAP//2
            p = _j(arc(CX,CY,W//2-sw//2,CAP//2-sw//2,35,325))
        elif char == 'D':
            W=WW; L=SB; Lx=L+sw//2
            p = _j(s(Lx,BASE,Lx,CAP),
                   arc(Lx,CAP//2,W-sw,CAP//2,270,90),
                   gr(Lx,BASE,Lx,CAP), sltop(Lx), slbase(Lx))
        elif char == 'E':
            W=WN; L=SB; Lx=L+sw//2; mid=int(CAP*0.50); R=SB+W
            p = _j(s(Lx,BASE,Lx,CAP), s(Lx,CAP,R,CAP), s(Lx,mid,R-W//5,mid), s(Lx,BASE,R,BASE),
                   gr(Lx,BASE,Lx,CAP), sltop(Lx), slbase(Lx))
        elif char == 'F':
            W=WN; L=SB; Lx=L+sw//2; mid=int(CAP*0.54); R=SB+W
            p = _j(s(Lx,BASE,Lx,CAP), s(Lx,CAP,R,CAP), s(Lx,mid,R-W//4,mid),
                   gr(Lx,BASE,Lx,CAP), sltop(Lx), slbase(Lx))
        elif char == 'G':
            W=WW; CX=SB+W//2; CY=CAP//2; rx=W//2-sw//2; ry=CAP//2-sw//2
            p = _j(arc(CX,CY,rx,ry,15,325), s(CX,CY,CX+rx,CY))
        elif char == 'H':
            W=WN; L=SB; R=SB+W; cy=int(CAP*0.48)
            p = _j(s(L+sw//2,BASE,L+sw//2,CAP), s(R-sw//2,BASE,R-sw//2,CAP), s(L+sw,cy,R-sw,cy),
                   gr(L+sw//2,BASE,L+sw//2,CAP), gr(R-sw//2,BASE,R-sw//2,CAP),
                   sltop(L+sw//2), sltop(R-sw//2), slbase(L+sw//2), slbase(R-sw//2))
        elif char == 'I':
            W=WNR; CX=SB+W//2
            p = _j(s(CX,BASE,CX,CAP), gr(CX,BASE,CX,CAP),
                   s(CX-W//3,CAP,CX+W//3,CAP), s(CX-W//3,BASE,CX+W//3,BASE))
        elif char == 'J':
            W=WNR; R=SB+W; Rx=R-sw//2; hcy=int(CAP*0.22)
            p = _j(s(Rx,hcy,Rx,CAP), s(Rx-W//2,CAP,Rx+W//4,CAP),
                   arc(Rx-W//3,hcy,W//3,int(CAP*0.20),0,180),
                   gr(Rx,hcy,Rx,CAP))
        elif char == 'K':
            W=WN; L=SB; Lx=L+sw//2; R=SB+W; mid=int(CAP*0.48)
            p = _j(s(Lx,BASE,Lx,CAP), s(Lx+sw,mid,R,CAP), s(Lx+sw,mid,R,BASE),
                   gr(Lx,BASE,Lx,CAP), sltop(Lx), slbase(Lx))
        elif char == 'L':
            W=WN; L=SB; Lx=L+sw//2; R=SB+W
            p = _j(s(Lx,BASE,Lx,CAP), s(Lx,BASE,R,BASE),
                   gr(Lx,BASE,Lx,CAP), slbase(Lx))
        elif char == 'M':
            W=WM; L=SB; R=SB+W; CX=(L+R)//2
            p = _j(s(L+sw//2,BASE,L+sw//2,CAP), s(R-sw//2,BASE,R-sw//2,CAP),
                   s(L+sw,CAP,CX,int(CAP*0.38)), s(R-sw,CAP,CX,int(CAP*0.38)),
                   gr(L+sw//2,BASE,L+sw//2,CAP), gr(R-sw//2,BASE,R-sw//2,CAP))
        elif char == 'N':
            W=WN; L=SB; R=SB+W
            p = _j(s(L+sw//2,BASE,L+sw//2,CAP), s(R-sw//2,BASE,R-sw//2,CAP),
                   s(L+sw,CAP,R-sw,BASE),
                   gr(L+sw//2,BASE,L+sw//2,CAP), gr(R-sw//2,BASE,R-sw//2,CAP))
        elif char == 'O':
            W=WW; CX=SB+W//2; CY=CAP//2; rx=W//2-sw//2; ry=CAP//2-sw//2
            p = _j(oval(CX,CY,rx,ry), hole(CX,CY,max(2,rx-sw),max(2,ry-sw)))
        elif char == 'P':
            W=WN; L=SB; Lx=L+sw//2; mid=int(CAP*0.50)
            p = _j(s(Lx,BASE,Lx,CAP),
                   arc(Lx,mid+(CAP-mid)//2,int((W-sw)*0.90),(CAP-mid)//2,270,90),
                   gr(Lx,BASE,Lx,CAP), sltop(Lx), slbase(Lx))
        elif char == 'Q':
            W=WW; CX=SB+W//2; CY=CAP//2; rx=W//2-sw//2; ry=CAP//2-sw//2
            p = _j(oval(CX,CY,rx,ry), hole(CX,CY,max(2,rx-sw),max(2,ry-sw)),
                   s(CX+rx*0.4,CY-ry*0.4,CX+rx+sw,CY-ry-sw*2))
        elif char == 'R':
            W=WN; L=SB; Lx=L+sw//2; R=SB+W; mid=int(CAP*0.50)
            p = _j(s(Lx,BASE,Lx,CAP),
                   arc(Lx,mid+(CAP-mid)//2,int((W-sw)*0.90),(CAP-mid)//2,270,90),
                   s(Lx+int((W-sw)*0.90*0.6),mid,R,BASE),
                   gr(Lx,BASE,Lx,CAP), sltop(Lx), slbase(Lx))
        elif char == 'S':
            W=WN; CX=SB+W//2; rx=W//2-sw//2
            p = _j(arc(CX,int(CAP*0.70),rx,int(CAP*0.24),195,355),
                   arc(CX,int(CAP*0.30),rx,int(CAP*0.24),15,175))
        elif char == 'T':
            W=WN; L=SB; R=SB+W; CX=(L+R)//2
            p = _j(s(CX,BASE,CX,CAP), s(L,CAP,R,CAP),
                   gr(CX,BASE,CX,CAP), slbase(CX))
        elif char == 'U':
            W=WN; L=SB; R=SB+W; CX=(L+R)//2; bcy=int(CAP*0.28); brx=(R-L-sw)//2
            p = _j(s(L+sw//2,bcy,L+sw//2,CAP), s(R-sw//2,bcy,R-sw//2,CAP),
                   arc(CX,bcy,brx,int(CAP*0.28),180,0),
                   gr(L+sw//2,bcy,L+sw//2,CAP), gr(R-sw//2,bcy,R-sw//2,CAP))
        elif char == 'V':
            W=WN; L=SB; R=SB+W; CX=(L+R)//2
            p = _j(s(L,CAP,CX,BASE), s(R,CAP,CX,BASE))
        elif char == 'W':
            W=WM; L=SB; R=SB+W; CX=(L+R)//2; q1=(L*2+R)//3; q2=(L+R*2)//3
            p = _j(s(L,CAP,q1,BASE), s(q1,BASE,CX,int(CAP*0.44)),
                   s(CX,int(CAP*0.44),q2,BASE), s(q2,BASE,R,CAP))
        elif char == 'X':
            W=WN; L=SB; R=SB+W
            p = _j(s(L,CAP,R,BASE), s(R,CAP,L,BASE))
        elif char == 'Y':
            W=WN; L=SB; R=SB+W; CX=(L+R)//2; mid=int(CAP*0.46)
            p = _j(s(L,CAP,CX,mid), s(R,CAP,CX,mid), s(CX,BASE,CX,mid),
                   gr(CX,BASE,CX,mid), slbase(CX))
        elif char == 'Z':
            W=WN; L=SB; R=SB+W
            p = _j(s(L,CAP,R,CAP), s(L,BASE,R,BASE), s(R,CAP,L,BASE))

        # ── LOWERCASE ──────────────────────────────────────────────
        elif char == 'a':
            W=WLN; L=SB; R=SB+W; CX=(L+R)//2
            p = _j(arc(CX,XH//2,W//2-sw//2,XH//2-sw//4,22,338),
                   s(R-sw//2,BASE,R-sw//2,XH))
        elif char == 'b':
            W=WLN; L=SB; Lx=L+sw//2
            p = _j(s(Lx,BASE,Lx,CAP), arc(Lx,XH//2,W-sw,XH//2,270,90),
                   gr(Lx,BASE,Lx,CAP))
        elif char == 'c':
            W=WLN; CX=SB+W//2
            p = _j(arc(CX,XH//2,W//2-sw//2,XH//2-sw//4,35,325))
        elif char == 'd':
            W=WLN; R=SB+W; Rx=R-sw//2
            p = _j(s(Rx,BASE,Rx,CAP), arc(Rx,XH//2,W-sw,XH//2,90,270),
                   gr(Rx,BASE,Rx,CAP))
        elif char == 'e':
            W=WLN; L=SB; R=SB+W; CX=(L+R)//2
            p = _j(arc(CX,XH//2,W//2-sw//2,XH//2-sw//4,8,320),
                   s(CX-(W//2-sw//2)+sw,XH//2,CX+(W//2-sw//2)-sw,XH//2,sw-6))
        elif char == 'f':
            W=WLN2; CX=SB+W//2+4; hcx=CX+W//3; hcy=int(CAP*0.82)
            p = _j(s(CX,BASE,CX,hcy), arc(hcx,hcy,W//3,int(CAP*0.13),180,270),
                   s(CX-W//2,int(XH*0.68),CX+W//2,int(XH*0.68)), gr(CX,BASE,CX,hcy))
        elif char == 'g':
            W=WLN; L=SB; R=SB+W; CX=(L+R)//2; Rx=R-sw//2
            p = _j(arc(CX,XH//2,W//2-sw//2,XH//2-sw//4,22,338),
                   s(Rx,DESC//2,Rx,XH),
                   arc(CX,DESC//2,(W-sw)//2,abs(DESC//2)-sw//2,0,180),
                   gr(Rx,DESC//2,Rx,XH))
        elif char == 'h':
            W=WLN; L=SB; Lx=L+sw//2; acx=Lx+W//3
            p = _j(s(Lx,BASE,Lx,CAP), arc(acx,XH,W//3,int(XH*0.30),180,0),
                   s(acx+W//3,BASE,acx+W//3,XH),
                   gr(Lx,BASE,Lx,CAP), gr(acx+W//3,BASE,acx+W//3,XH))
        elif char == 'i':
            W=WLN2; CX=SB+W//2
            dot_r = max(4, sw//2)
            p = _j(s(CX,BASE,CX,XH), gr(CX,BASE,CX,XH),
                   oval(CX,XH+dot_r*3,dot_r,dot_r))
        elif char == 'j':
            W=WLN2; CX=SB+W//2+W//5; dot_r=max(4,sw//2)
            p = _j(s(CX,DESC//2,CX,XH), arc(CX-W//3,DESC//2,W//3,int(abs(DESC//2)*0.75),0,180),
                   oval(CX,XH+dot_r*3,dot_r,dot_r))
        elif char == 'k':
            W=WLN; L=SB; Lx=L+sw//2; R=SB+W; mid=int(XH*0.50)
            p = _j(s(Lx,BASE,Lx,CAP), s(Lx+sw,mid,R,XH), s(Lx+sw,mid,R,BASE),
                   gr(Lx,BASE,Lx,CAP))
        elif char == 'l':
            W=WLN2; CX=SB+W//2
            p = _j(s(CX,BASE,CX,CAP), gr(CX,BASE,CX,CAP), s(CX-sw,BASE,CX+sw*2,BASE))
        elif char == 'm':
            W=WLW; L=SB; st=W//3
            p = _j(s(L+sw//2,BASE,L+sw//2,XH),
                   arc(L+sw+st//2,XH,st//2-2,int(XH*0.28),180,0),
                   s(L+sw+st,BASE,L+sw+st,XH),
                   arc(L+sw+st+st//2,XH,st//2-2,int(XH*0.28),180,0),
                   s(L+sw+st*2,BASE,L+sw+st*2,XH),
                   gr(L+sw//2,BASE,L+sw//2,XH))
        elif char == 'n':
            W=WLN; L=SB; Lx=L+sw//2; acx=Lx+W//3
            p = _j(s(Lx,BASE,Lx,XH), arc(acx,XH,W//3,int(XH*0.30),180,0),
                   s(acx+W//3,BASE,acx+W//3,XH),
                   gr(Lx,BASE,Lx,XH), gr(acx+W//3,BASE,acx+W//3,XH))
        elif char == 'o':
            W=WLN; CX=SB+W//2; rx=W//2-sw//2; ry=XH//2-sw//4
            p = _j(oval(CX,XH//2,rx,ry), hole(CX,XH//2,max(2,rx-sw),max(2,ry-sw)))
        elif char == 'p':
            W=WLN; L=SB; Lx=L+sw//2
            p = _j(s(Lx,DESC//2,Lx,XH), arc(Lx,XH//2,W-sw,XH//2,270,90),
                   gr(Lx,DESC//2,Lx,XH))
        elif char == 'q':
            W=WLN; R=SB+W; Rx=R-sw//2
            p = _j(s(Rx,DESC//2,Rx,XH), arc(Rx,XH//2,W-sw,XH//2,90,270),
                   gr(Rx,DESC//2,Rx,XH))
        elif char == 'r':
            W=WLN2; L=SB; Lx=L+sw//2; acx=Lx+W//3
            p = _j(s(Lx,BASE,Lx,XH), arc(acx,XH,W//3,int(XH*0.28),180,60))
        elif char == 's':
            W=WLN; CX=SB+W//2; rx=W//2-sw//2
            p = _j(arc(CX,int(XH*0.70),rx,int(XH*0.24),200,355),
                   arc(CX,int(XH*0.30),rx,int(XH*0.24),20,175))
        elif char == 't':
            W=WLN2; CX=SB+W//2
            p = _j(s(CX,BASE,CX,int(CAP*0.80)), gr(CX,BASE,CX,int(CAP*0.80)),
                   s(CX-W//2,int(XH*0.68),CX+W//2,int(XH*0.68)))
        elif char == 'u':
            W=WLN; L=SB; R=SB+W; CX=(L+R)//2; bcy=int(XH*0.32); brx=(R-L-sw)//2
            p = _j(s(L+sw//2,bcy,L+sw//2,XH), s(R-sw//2,BASE,R-sw//2,XH),
                   arc(CX,bcy,brx,int(XH*0.32),180,0))
        elif char == 'v':
            W=WLN; L=SB; R=SB+W; CX=(L+R)//2
            p = _j(s(L,XH,CX,BASE), s(R,XH,CX,BASE))
        elif char == 'w':
            W=WLW; L=SB; R=SB+W; CX=(L+R)//2; q1=(L*2+R)//3; q2=(L+R*2)//3
            p = _j(s(L,XH,q1,BASE), s(q1,BASE,CX,int(XH*0.45)),
                   s(CX,int(XH*0.45),q2,BASE), s(q2,BASE,R,XH))
        elif char == 'x':
            W=WLN; L=SB; R=SB+W
            p = _j(s(L,XH,R,BASE), s(R,XH,L,BASE))
        elif char == 'y':
            W=WLN; L=SB; R=SB+W; CX=(L+R)//2; mid=int(XH*0.44)
            p = _j(s(L,XH,CX,mid), s(R,XH,CX,mid), s(CX,DESC//2,CX,mid),
                   arc(CX-(W-sw)//2,DESC//2,(W-sw)//2,abs(DESC//2)-sw//2,0,180))
        elif char == 'z':
            W=WLN; L=SB; R=SB+W
            p = _j(s(L,XH,R,XH), s(L,BASE,R,BASE), s(R,XH,L,BASE))

        # ── NUMERALS ──────────────────────────────────────────────
        elif char == '0':
            W=WW; CX=SB+W//2; CY=CAP//2; rx=W//2-sw//2; ry=CAP//2-sw//2
            p = _j(oval(CX,CY,rx,ry), hole(CX,CY,max(2,rx-sw),max(2,ry-sw)))
        elif char == '1':
            W=WNR; CX=SB+W//2
            p = _j(s(CX,BASE,CX,CAP), gr(CX,BASE,CX,CAP),
                   s(CX-W//3,BASE,CX+W//2,BASE), s(CX-W//3,int(CAP*0.76),CX,CAP))
        elif char == '2':
            W=WN; L=SB; R=SB+W; CX=SB+W//2
            acy=int(CAP*0.70); arx=W//2-sw//2; ary=int(CAP*0.24)
            a2r = math.radians(345)
            tx = CX+arx*math.cos(a2r); ty = acy+ary*math.sin(a2r)
            p = _j(arc(CX,acy,arx,ary,215,345), s(tx,ty,L,BASE+sw//2), s(L,BASE,R,BASE))
        elif char == '3':
            W=WN; CX=SB+W//2; rx=W//2-sw//2
            p = _j(arc(CX,int(CAP*0.72),rx,int(CAP*0.24),215,340),
                   arc(CX,int(CAP*0.28),rx,int(CAP*0.26),20,340))
        elif char == '4':
            W=WN; L=SB; R=SB+W; sx=SB+int(W*0.66)
            p = _j(s(L,CAP,sx-sw//2,int(CAP*0.44)), s(L,int(CAP*0.44),R,int(CAP*0.44)),
                   s(sx,BASE,sx,CAP), gr(sx,BASE,sx,CAP))
        elif char == '5':
            W=WN; L=SB; R=SB+W; CX=SB+W//2; Lx=L+sw//2
            p = _j(s(L,CAP,R,CAP), s(Lx,int(CAP*0.50),Lx,CAP),
                   arc(CX,int(CAP*0.28),W//2-sw//2,int(CAP*0.26),175,355))
        elif char == '6':
            W=WN; CX=SB+W//2; rx=W//2-sw//2
            p = _j(oval(CX,int(CAP*0.30),rx,int(CAP*0.28)),
                   hole(CX,int(CAP*0.30),max(2,rx-sw),max(2,int(CAP*0.28)-sw)),
                   arc(CX,int(CAP*0.62),rx,int(CAP*0.30),178,285))
        elif char == '7':
            W=WN; L=SB; R=SB+W
            p = _j(s(L,CAP,R,CAP), s(R,CAP,SB+W//3,BASE), gr(R,CAP,SB+W//3,BASE))
        elif char == '8':
            W=WN; CX=SB+W//2; rx=W//2-sw//2
            t_rx=rx; t_ry=int(CAP*0.22); b_ry=int(CAP*0.26)
            p = _j(oval(CX,int(CAP*0.72),t_rx,t_ry),
                   hole(CX,int(CAP*0.72),max(2,t_rx-sw),max(2,t_ry-sw)),
                   oval(CX,int(CAP*0.28),rx,b_ry),
                   hole(CX,int(CAP*0.28),max(2,rx-sw),max(2,b_ry-sw)))
        elif char == '9':
            W=WN; CX=SB+W//2; rx=W//2-sw//2
            p = _j(oval(CX,int(CAP*0.68),rx,int(CAP*0.26)),
                   hole(CX,int(CAP*0.68),max(2,rx-sw),max(2,int(CAP*0.26)-sw)),
                   arc(CX,int(CAP*0.38),rx,int(CAP*0.28),355,100))

        # ── PUNCTUATION ───────────────────────────────────────────
        elif char == '.':
            r = max(sw//2, 8)
            p = oval(SB+r, BASE+r, r, r)
            W = r*2+SB
        elif char == ',':
            r = max(sw//2, 8)
            p = _j(oval(SB+r,BASE+r,r,r), s(SB+r,BASE+r,SB+r-int(r*0.8),BASE-int(r*1.5),int(r*0.5)))
            W = r*2+SB
        elif char == '!':
            W=WLN2; CX=SB+W//2; r=max(sw//2,8)
            p = _j(s(CX,int(XH*0.30),CX,XH), gr(CX,int(XH*0.30),CX,XH),
                   oval(CX,BASE+r,r,r))
        elif char == '?':
            W=WLN; CX=SB+W//2; r=max(sw//2,8)
            p = _j(arc(CX,int(CAP*0.66),W//3,int(CAP*0.20),215,355),
                   s(CX,int(XH*0.28),CX,int(CAP*0.48)), oval(CX,BASE+r,r,r))
        elif char == '-':
            W=WN//2
            p = s(SB,CAP//2,SB+W,CAP//2)
        elif char == ':':
            r = max(sw//2, 8); W=r*2+SB
            p = _j(oval(SB+r,BASE+r,r,r), oval(SB+r,XH//2+r,r,r))
        elif char == ';':
            r = max(sw//2, 8); W=r*2+SB
            p = _j(oval(SB+r,XH//2+r,r,r),
                   oval(SB+r,BASE+r,r,r),
                   s(SB+r,BASE+r,SB+r-int(r*0.8),BASE-int(r*1.5),int(r*0.5)))
        elif char == '/':
            W=WN; L=SB; R=SB+W
            p = s(R-sw,CAP,L,BASE)
        elif char == '(':
            W=WNR; CX=SB+W//2+W//4
            p = arc(CX,CAP//2,W//3,(CAP-BASE)//2,120,240)
        elif char == ')':
            W=WNR; CX=SB+W//4
            p = arc(CX,CAP//2,W//3,(CAP-BASE)//2,300,60)
        elif char == '+':
            W=WN; L=SB; R=SB+W; CX=(L+R)//2
            p = _j(s(L+sw,CAP//2,R-sw,CAP//2), s(CX,CAP//5,CX,CAP*4//5))
        elif char == '@':
            W=WW; CX=SB+W//2; CY=CAP//2; rx=W//2-sw//2; ry=CAP//2-sw//2
            p = _j(oval(CX,CY,rx,ry), hole(CX,CY,max(2,rx-sw),max(2,ry-sw)),
                   s(CX+sw,CY+ry-sw,CX+rx-sw,CY,sw-4))
        elif char == '#':
            W=WN; L=SB; R=SB+W; CX=(L+R)//2
            p = _j(s(CX-W//5,CAP+sw,CX-W//5,BASE-sw,sw//2),
                   s(CX+W//5,CAP+sw,CX+W//5,BASE-sw,sw//2),
                   s(L+sw,CAP//2-sw*2,R-sw,CAP//2-sw*2,sw//2),
                   s(L+sw,CAP//2+sw*2,R-sw,CAP//2+sw*2,sw//2))
        elif char == '&':
            W=WW; CX=SB+W//2
            p = _j(arc(CX,int(CAP*0.70),W//3,int(CAP*0.24),0,360,sw),
                   s(SB,BASE,SB+W,BASE))
        elif char == '*':
            W=WNR; CX=SB+W//2; cy=CAP//2; r=W//2-sw
            p = _j(s(CX,cy-r,CX,cy+r,sw//2),
                   s(CX-int(r*0.87),cy-r//2,CX+int(r*0.87),cy+r//2,sw//2),
                   s(CX-int(r*0.87),cy+r//2,CX+int(r*0.87),cy-r//2,sw//2))
        elif char == '%':
            W=WN; L=SB; R=SB+W; r=W//6
            p = _j(oval(L+r+sw,CAP-r-sw,r,r),
                   hole(L+r+sw,CAP-r-sw,max(2,r-sw),max(2,r-sw)),
                   oval(R-r-sw,BASE+r+sw,r,r),
                   hole(R-r-sw,BASE+r+sw,max(2,r-sw),max(2,r-sw)),
                   s(R-sw,CAP,L+sw,BASE,sw//2))
        elif char == '_':
            W=WN; p = s(SB,BASE-sw//2,SB+W,BASE-sw//2)
        elif char == '[':
            W=WNR; L=SB; Lx=L+sw//2
            p = _j(s(Lx,BASE,Lx,CAP), s(Lx,CAP,Lx+W//2,CAP), s(Lx,BASE,Lx+W//2,BASE))
        elif char == ']':
            W=WNR; R=SB+W; Rx=R-sw//2
            p = _j(s(Rx,BASE,Rx,CAP), s(Rx,CAP,Rx-W//2,CAP), s(Rx,BASE,Rx-W//2,BASE))
        elif char == '=':
            W=WN; L=SB; R=SB+W
            p = _j(s(L+sw,CAP//2-sw*2,R-sw,CAP//2-sw*2),
                   s(L+sw,CAP//2+sw*2,R-sw,CAP//2+sw*2))
        elif char == ' ':
            p = ""; W = int(280*self.ws)
        else:
            # Fallback: simple rectangle placeholder
            W=WN; CX=SB+W//2
            p = s(CX-sw,BASE,CX-sw,CAP) + " " + s(CX+sw,BASE,CX+sw,CAP)

        advance = adv(W) if char not in ('.', ',', '!', '?', ':', ';', ' ') else adv(W)

        # Add decorations
        if char != ' ' and self.decorations:
            deco = self._place_decos(char, advance, None, char_idx)
            p = _j(p, deco)

        return p, advance


# ── FONT BUILDER ─────────────────────────────────────────────────

CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?:;-_/()[]+@#&=*%'

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

def build_from_dna(dna: dict, output_path: str, font_name: str = None):
    """
    Build a font from a DNA recipe dict.
    DNA format matches ai_distortion.get_effect_recipe() output.
    """
    if font_name is None:
        font_name = dna.get('font_name', 'VectrodFont')

    builder  = CyberGlyphBuilder(dna)
    chars    = list(CHARS)
    gnames   = ['.notdef', 'space'] + [f'uni{ord(c):04X}' for c in chars]

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(gnames)
    fb.setupCharacterMap({32: 'space', **{ord(c): f'uni{ord(c):04X}' for c in chars}})

    glyph_map = {'.notdef': _empty(), 'space': _empty()}
    metrics   = {'.notdef': (500, 0), 'space': (int(220 * builder.ws), 0)}

    ok = fail = 0
    for idx, c in enumerate(chars):
        gn = f'uni{ord(c):04X}'
        try:
            path, adv = builder.build_glyph(c, idx)
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

    # Cu2Qu refinement
    conv = {}
    for gn, g in glyph_map.items():
        if not hasattr(g, 'draw'): conv[gn] = g; continue
        try:
            p2 = TTGlyphPen(None)
            g.draw(Cu2QuPen(p2, max_err=0.6, reverse_direction=False))
            conv[gn] = p2.glyph()
        except:
            conv[gn] = g

    sw = builder.sw
    ASC = CAP + sw * 3
    DSC = DESC - sw

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
        usWeightClass=max(100, min(900, int(sw * 6.5))),
        fsType=0, fsSelection=0x40, achVendID="VCTD",
        ulUnicodeRange1=0b10000000000000000000000011111111,
    )
    fb.setupPost(isFixedPitch=0, underlinePosition=-100, underlineThickness=sw)
    fb.setupHead(unitsPerEm=UPM, lowestRecPPEM=8, indexToLocFormat=0)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    fb.font.save(output_path)

    sz = os.path.getsize(output_path) / 1024
    print(f"  ✅ cyber_engine: {sz:.1f}KB | {ok}✓ {fail}✗ | sw={sw} ws={builder.ws:.2f}")
    return output_path
