"""
ai_font_geo.py — Geometric Font Engine v2
Draws real letterforms using mathematical construction.
Works 100% offline, no API key needed.
Supports 5 style families: sans, serif, bold, rounded, mono
"""
import math

# ── EM SQUARE ─────────────────────────────────────────────
EM   = 700   # total em height
BASE = 560   # baseline Y (from top)
CAP  = 100   # cap-height Y
MID  = 330   # x-height Y
DESC = 650   # descender Y
ADV  = 560   # default advance width


def analyze_prompt(prompt: str) -> dict:
    p = prompt.lower()
    style = {
        'family': 'sans',
        'sw': 55,        # stroke width
        'serif': False,
        'rounded': False,
        'mono': False,
        'bold': False,
        'italic': False,
        'condensed': False,
        'wide': False,
    }
    if any(w in p for w in ['serif','classic','roman','elegant','luxury','fashion','magazine','wedding','vogue']):
        style['family']='serif'; style['serif']=True; style['sw']=42
    if any(w in p for w in ['bold','heavy','thick','black','strong','impact','powerful','aggressive']):
        style['bold']=True; style['sw']=110; style['family']='bold'
    if any(w in p for w in ['round','bubble','cute','kawaii','soft','friendly','playful','fun']):
        style['rounded']=True; style['family']='rounded'; style['sw']=70
    if any(w in p for w in ['mono','code','terminal','typewriter','tech','cyber','matrix','digital']):
        style['mono']=True; style['family']='mono'; style['sw']=50
    if any(w in p for w in ['thin','light','hairline','delicate','fine']):
        style['sw']=22; style['bold']=False
    if any(w in p for w in ['italic','slant','oblique']): style['italic']=True
    if any(w in p for w in ['condensed','narrow','slim','tall']): style['condensed']=True
    if any(w in p for w in ['wide','extended','expanded','fat']): style['wide']=True
    return style


class GlyphDrawer:
    def __init__(self, style: dict):
        self.s = style
        sw = style['sw']
        self.sw  = sw       # stroke width
        self.sw2 = sw // 2  # half stroke
        self.r   = sw // 3 if style.get('rounded') else 0  # corner radius
        # Scale advance width
        if style.get('condensed'): self.adv = int(ADV * 0.75)
        elif style.get('wide'):    self.adv = int(ADV * 1.25)
        else:                      self.adv = ADV

    # ── PATH PRIMITIVES ───────────────────────────────────
    def rect(self, x, y, w, h) -> str:
        """Filled rectangle"""
        r = min(self.r, w//2, h//2)
        if r <= 1:
            return f"M{x},{y} L{x+w},{y} L{x+w},{y+h} L{x},{y+h} Z"
        return (f"M{x+r},{y} L{x+w-r},{y} Q{x+w},{y} {x+w},{y+r} "
                f"L{x+w},{y+h-r} Q{x+w},{y+h} {x+w-r},{y+h} "
                f"L{x+r},{y+h} Q{x},{y+h} {x},{y+h-r} "
                f"L{x},{y+r} Q{x},{y} {x+r},{y} Z")

    def vrect(self, cx, y1, y2) -> str:
        """Vertical stroke centered at cx"""
        return self.rect(cx - self.sw2, y1, self.sw, y2 - y1)

    def hrect(self, x1, x2, cy) -> str:
        """Horizontal stroke centered at cy"""
        return self.rect(x1, cy - self.sw2, x2 - x1, self.sw)

    def diag(self, x1, y1, x2, y2) -> str:
        """Diagonal stroke from (x1,y1) to (x2,y2)"""
        dx, dy = x2 - x1, y2 - y1
        ln = math.hypot(dx, dy)
        if ln < 1: return ""
        nx, ny = -dy/ln * self.sw2, dx/ln * self.sw2
        return (f"M{x1+nx:.1f},{y1+ny:.1f} L{x2+nx:.1f},{y2+ny:.1f} "
                f"L{x2-nx:.1f},{y2-ny:.1f} L{x1-nx:.1f},{y1-ny:.1f} Z")

    def oval(self, cx, cy, rx, ry) -> str:
        """Ellipse"""
        k = 0.5523
        return (f"M{cx-rx},{cy} "
                f"C{cx-rx},{cy-ry*k:.1f} {cx-rx*k:.1f},{cy-ry} {cx},{cy-ry} "
                f"C{cx+rx*k:.1f},{cy-ry} {cx+rx},{cy-ry*k:.1f} {cx+rx},{cy} "
                f"C{cx+rx},{cy+ry*k:.1f} {cx+rx*k:.1f},{cy+ry} {cx},{cy+ry} "
                f"C{cx-rx*k:.1f},{cy+ry} {cx-rx},{cy+ry*k:.1f} {cx-rx},{cy} Z")

    def oval_stroke(self, cx, cy, rx, ry) -> str:
        """Oval ring (stroke outline)"""
        outer = self.oval(cx, cy, rx, ry)
        sw = self.sw
        inner = self.oval(cx, cy, max(4, rx-sw), max(4, ry-sw))
        return outer + " " + inner

    def arc_stroke(self, cx, cy, rx, ry, a1, a2) -> str:
        """Arc stroke from angle a1 to a2 (degrees, 0=right, CCW)"""
        sw = self.sw
        def pt(r, a):
            rad = math.radians(a)
            return cx + r*math.cos(rad), cy - r*math.sin(rad)
        steps = max(8, int(abs(a2-a1)/10))
        angles = [a1 + (a2-a1)*i/(steps) for i in range(steps+1)]
        outer_pts = [pt(rx, a) for a in angles]
        inner_pts = [pt(max(4, rx-sw), a) for a in reversed(angles)]
        all_pts = outer_pts + inner_pts
        d = f"M{all_pts[0][0]:.1f},{all_pts[0][1]:.1f}"
        for x,y in all_pts[1:]: d += f" L{x:.1f},{y:.1f}"
        return d + " Z"

    def serif_foot(self, x, y, width=None) -> str:
        """Small serif bar at position"""
        w = width or self.sw * 2
        h = max(5, self.sw // 4)
        return self.rect(x - w//2, y - h, w, h)

    # ── LETTER CONSTRUCTION ───────────────────────────────
    def draw(self, char: str) -> tuple:
        """Returns (svg_path_d, advance_width)"""
        sw = self.sw
        adv = self.adv
        parts = []

        # Convenience shortcuts
        top, bot = CAP, BASE
        mid = MID
        desc = DESC
        left = 40
        right = adv - 40
        w = right - left
        cx = left + w // 2

        if char == ' ':
            return "", adv // 2

        fn = getattr(self, f'_draw_{char}', None) if char.isalpha() or char.isdigit() else None

        # Try specific draws
        m = {
            'A': self._A, 'B': self._B, 'C': self._C, 'D': self._D, 'E': self._E,
            'F': self._F, 'G': self._G, 'H': self._H, 'I': self._I, 'J': self._J,
            'K': self._K, 'L': self._L, 'M': self._M, 'N': self._N, 'O': self._O,
            'P': self._P, 'Q': self._Q, 'R': self._R, 'S': self._S, 'T': self._T,
            'U': self._U, 'V': self._V, 'W': self._W, 'X': self._X, 'Y': self._Y,
            'Z': self._Z,
            'a': self._la, 'b': self._lb, 'c': self._lc, 'd': self._ld, 'e': self._le,
            'f': self._lf, 'g': self._lg, 'h': self._lh, 'i': self._li, 'j': self._lj,
            'k': self._lk, 'l': self._ll, 'm': self._lm, 'n': self._ln, 'o': self._lo,
            'p': self._lp, 'q': self._lq, 'r': self._lr, 's': self._ls, 't': self._lt,
            'u': self._lu, 'v': self._lv, 'w': self._lw, 'x': self._lx, 'y': self._ly,
            'z': self._lz,
            '0': self._d0, '1': self._d1, '2': self._d2, '3': self._d3, '4': self._d4,
            '5': self._d5, '6': self._d6, '7': self._d7, '8': self._d8, '9': self._d9,
            '.': self._dot, ',': self._comma, '!': self._excl, '?': self._quest,
            '-': self._dash, '_': self._under, '(': self._lparen, ')': self._rparen,
            '/': self._slash, '@': self._at,
        }
        fn = m.get(char)
        if fn:
            path = fn()
            return path, adv
        # Fallback: simple box outline
        return self.rect(left+sw, top+sw, w-sw*2, bot-top-sw*2), adv

    # ── UPPERCASE ─────────────────────────────────────────
    def _A(self):
        sw=self.sw; left=40; right=self.adv-40; top=CAP; bot=BASE
        cx=(left+right)//2
        return (self.diag(cx,top,left,bot) + " " +
                self.diag(cx,top,right,bot) + " " +
                self.hrect(left+(right-left)//4, right-(right-left)//4, (top+bot)//2))

    def _B(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; cx=l+sw
        mid=(t+b)//2
        bump_r1 = l + (r-l)*70//100
        bump_r2 = l + (r-l)*80//100
        stem = self.vrect(l+sw//2, t, b)
        top_curve = (f"M{cx},{t} L{bump_r1},{t} "
                     f"C{r},{t} {r},{mid} {bump_r1},{mid} L{cx},{mid} Z "
                     f"M{cx+sw},{t+sw} L{bump_r1},{t+sw} "
                     f"C{r-sw},{t+sw} {r-sw},{mid} {bump_r1},{mid} L{cx+sw},{mid} Z")
        bot_curve = (f"M{cx},{mid} L{bump_r2},{mid} "
                     f"C{r+sw//2},{mid} {r+sw//2},{b} {bump_r2},{b} L{cx},{b} Z "
                     f"M{cx+sw},{mid+sw} L{bump_r2},{mid+sw} "
                     f"C{r-sw//2},{mid+sw} {r-sw//2},{b-sw} {bump_r2},{b-sw} L{cx+sw},{b-sw} Z")
        top_bar = self.hrect(cx, bump_r1, t+sw//2)
        mid_bar = self.hrect(cx, bump_r2, mid)
        bot_bar = self.hrect(cx, bump_r2, b-sw//2)
        return stem + " " + top_bar + " " + mid_bar + " " + bot_bar

    def _C(self):
        l=40; r=self.adv-40; t=CAP; b=BASE; sw=self.sw
        cx=(l+r)//2; cy=(t+b)//2; rx=(r-l)//2; ry=(b-t)//2
        # C = arc from 40° to 320°
        return self.arc_stroke(cx, cy, rx, ry, 40, 320)

    def _D(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        stem = self.vrect(l+sw//2, t, b)
        cx=l+sw; cy=(t+b)//2; rx=(r-l-sw); ry=(b-t)//2
        outer = (f"M{cx},{t} C{cx+rx*2},{t} {cx+rx*2},{b} {cx},{b} L{cx},{b-sw} "
                 f"C{cx+rx*2-sw*2},{b-sw} {cx+rx*2-sw*2},{t+sw} {cx},{t+sw} Z")
        top_bar = self.hrect(l+sw, l+sw+rx//2, t+sw//2)
        bot_bar = self.hrect(l+sw, l+sw+rx//2, b-sw//2)
        return stem + " " + outer + " " + top_bar + " " + bot_bar

    def _E(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(t+b)//2
        return (self.vrect(l+sw//2, t, b) + " " +
                self.hrect(l+sw, r, t+sw//2) + " " +
                self.hrect(l+sw, r-sw*2, mid) + " " +
                self.hrect(l+sw, r, b-sw//2))

    def _F(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(t+b)//2
        return (self.vrect(l+sw//2, t, b) + " " +
                self.hrect(l+sw, r, t+sw//2) + " " +
                self.hrect(l+sw, r-sw*2, mid))

    def _G(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        cx=(l+r)//2; cy=(t+b)//2; rx=(r-l)//2; ry=(b-t)//2
        arc = self.arc_stroke(cx, cy, rx, ry, 20, 320)
        mid_bar = self.hrect(cx, r, cy+sw//2)
        stub = self.vrect(r-sw//2, cy, cy+ry//2)
        return arc + " " + mid_bar + " " + stub

    def _H(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(t+b)//2
        return (self.vrect(l+sw//2, t, b) + " " +
                self.vrect(r-sw//2, t, b) + " " +
                self.hrect(l+sw, r-sw, mid))

    def _I(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; cx=(l+r)//2
        parts = self.vrect(cx, t, b)
        if self.s.get('serif'):
            parts += " " + self.hrect(l, r, t+sw//2) + " " + self.hrect(l, r, b-sw//2)
        return parts

    def _J(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        # Vertical stem + bottom curve
        stem = self.vrect(r-sw//2, t, b-sw*3)
        hook_cx=l+sw*2; hook_cy=b-sw*3
        hook = self.arc_stroke(hook_cx, hook_cy, (r-l-sw)//2, sw*3, 0, -180)
        return stem + " " + hook

    def _K(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(t+b)//2
        return (self.vrect(l+sw//2, t, b) + " " +
                self.diag(l+sw, mid, r, t) + " " +
                self.diag(l+sw, mid, r, b))

    def _L(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        return (self.vrect(l+sw//2, t, b) + " " +
                self.hrect(l+sw, r, b-sw//2))

    def _M(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; cx=(l+r)//2
        return (self.vrect(l+sw//2, t, b) + " " +
                self.vrect(r-sw//2, t, b) + " " +
                self.diag(l+sw, t, cx, (t+b)//2) + " " +
                self.diag(r-sw, t, cx, (t+b)//2))

    def _N(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        return (self.vrect(l+sw//2, t, b) + " " +
                self.vrect(r-sw//2, t, b) + " " +
                self.diag(l+sw, t, r-sw, b))

    def _O(self):
        l=40; r=self.adv-40; t=CAP; b=BASE; sw=self.sw
        cx=(l+r)//2; cy=(t+b)//2; rx=(r-l)//2; ry=(b-t)//2
        return self.oval_stroke(cx, cy, rx, ry)

    def _P(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(t+b)//2-sw
        stem = self.vrect(l+sw//2, t, b)
        cx = l+sw; bump_r = l+(r-l)*75//100; ry=(mid-t)//2
        bulge = (f"M{cx},{t} L{bump_r},{t} "
                 f"C{r+sw},{t} {r+sw},{mid} {bump_r},{mid} L{cx},{mid} Z "
                 f"M{cx+sw},{t+sw} L{bump_r},{t+sw} "
                 f"C{r-sw//2},{t+sw} {r-sw//2},{mid} {bump_r},{mid} L{cx+sw},{mid} Z")
        bar_t = self.hrect(cx, bump_r, t+sw//2)
        bar_m = self.hrect(cx, bump_r, mid)
        return stem + " " + bulge + " " + bar_t + " " + bar_m

    def _Q(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        cx=(l+r)//2; cy=(t+b)//2; rx=(r-l)//2; ry=(b-t)//2
        o = self.oval_stroke(cx, cy, rx, ry)
        tail = self.diag(cx, cy+ry//2, r, b+sw*2)
        return o + " " + tail

    def _R(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(t+b)//2
        p = self._P()
        leg = self.diag(l+sw+sw//2, mid, r, b)
        return p + " " + leg

    def _S(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        cx=(l+r)//2; cy=(t+b)//2; rx=(r-l)//2; ry=(b-t)//2
        top_arc = self.arc_stroke(cx, t+ry//2, rx*8//10, ry//2, 0, -200)
        bot_arc = self.arc_stroke(cx, b-ry//2, rx*8//10, ry//2, 180, -200)
        return top_arc + " " + bot_arc

    def _T(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; cx=(l+r)//2
        return (self.hrect(l, r, t+sw//2) + " " +
                self.vrect(cx, t+sw, b))

    def _U(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        cx=(l+r)//2; bot_cy=b-sw*2
        stem_l = self.vrect(l+sw//2, t, bot_cy)
        stem_r = self.vrect(r-sw//2, t, bot_cy)
        bowl = self.arc_stroke(cx, bot_cy, (r-l)//2, sw*2, 0, -180)
        return stem_l + " " + stem_r + " " + bowl

    def _V(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; cx=(l+r)//2
        return (self.diag(l, t, cx, b) + " " +
                self.diag(r, t, cx, b))

    def _W(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        q1=l+(r-l)//4; q2=l+(r-l)//2; q3=l+3*(r-l)//4
        return (self.diag(l, t, q1, b) + " " +
                self.diag(r, t, q3, b) + " " +
                self.diag(q1, b, q2, (t+b)//2+sw*2) + " " +
                self.diag(q3, b, q2, (t+b)//2+sw*2))

    def _X(self):
        l=40; r=self.adv-40; t=CAP; b=BASE
        return (self.diag(l, t, r, b) + " " +
                self.diag(r, t, l, b))

    def _Y(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; cx=(l+r)//2; mid=(t+b)//2
        return (self.diag(l, t, cx, mid) + " " +
                self.diag(r, t, cx, mid) + " " +
                self.vrect(cx, mid, b))

    def _Z(self):
        l=40; r=self.adv-40; t=CAP; b=BASE; sw=self.sw
        return (self.hrect(l, r, t+sw//2) + " " +
                self.diag(r-sw, t+sw, l+sw, b-sw) + " " +
                self.hrect(l, r, b-sw//2))

    # ── LOWERCASE ─────────────────────────────────────────
    def _la(self):  # a
        sw=self.sw; l=40; r=self.adv-40; t=MID; b=BASE
        cx=(l+r)//2; cy=(t+b)//2; rx=(r-l)//2; ry=(b-t)//2
        return (self.oval_stroke(cx,cy,rx,ry) + " " +
                self.vrect(r-sw//2, t+sw, b))

    def _lb(self):  # b
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        stem = self.vrect(l+sw//2, t, b)
        cx=l+sw+(r-l-sw)//2; cy=(MID+b)//2; rx=(r-l-sw)//2; ry=(b-MID)//2
        bowl = self.oval_stroke(cx, cy, rx, ry)
        return stem + " " + bowl

    def _lc(self):  # c
        l=40; r=self.adv-40; t=MID; b=BASE; sw=self.sw
        cx=(l+r)//2; cy=(t+b)//2; rx=(r-l)//2; ry=(b-t)//2
        return self.arc_stroke(cx, cy, rx, ry, 35, 325)

    def _ld(self):  # d
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        stem = self.vrect(r-sw//2, t, b)
        cx=l+(r-l-sw)//2; cy=(MID+b)//2; rx=(r-l-sw)//2; ry=(b-MID)//2
        bowl = self.oval_stroke(cx, cy, rx, ry)
        return bowl + " " + stem

    def _le(self):  # e
        l=40; r=self.adv-40; t=MID; b=BASE; sw=self.sw
        cx=(l+r)//2; cy=(t+b)//2; rx=(r-l)//2; ry=(b-t)//2
        arc = self.arc_stroke(cx, cy, rx, ry, 10, 320)
        bar = self.hrect(l+sw, r-sw//2, cy)
        return arc + " " + bar

    def _lf(self):  # f
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; cx=(l+r)//2
        stem = self.vrect(cx, t+sw*2, b)
        top = self.arc_stroke(cx, t+sw*2, sw*3, sw*2, 90, -90)
        bar = self.hrect(l, cx+sw*3, MID)
        return stem + " " + top + " " + bar

    def _lg(self):  # g
        sw=self.sw; l=40; r=self.adv-40; b=BASE; desc=DESC
        bowl_cx=(l+r)//2; bowl_cy=(MID+b)//2; rx=(r-l)//2; ry=(b-MID)//2
        bowl = self.oval_stroke(bowl_cx, bowl_cy, rx, ry)
        stem = self.vrect(r-sw//2, MID, desc-sw*2)
        hook = self.arc_stroke((l+r)//2, desc-sw*2, rx*9//10, sw*2, 0, -180)
        return bowl + " " + stem + " " + hook

    def _lh(self):  # h
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        stem = self.vrect(l+sw//2, t, b)
        arch_cx=(l+r)//2; arch_top=MID-sw
        arch = self.arc_stroke(arch_cx, arch_top, (r-l-sw)//2, sw*3, 180, 0)
        leg = self.vrect(r-sw//2, arch_top+sw*3, b)
        return stem + " " + arch + " " + leg

    def _li(self):  # i
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2
        dot_y = MID - sw*3
        return (self.vrect(cx, MID, BASE) + " " +
                self.oval(cx, dot_y, sw*0.8, sw*0.8))

    def _lj(self):  # j
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2+sw
        dot_y = MID - sw*3
        stem = self.vrect(cx, MID, DESC-sw*2)
        hook = self.arc_stroke(cx-sw*3, DESC-sw*2, sw*3, sw*2, 0, -180)
        dot = self.oval(cx, dot_y, sw*0.8, sw*0.8)
        return stem + " " + hook + " " + dot

    def _lk(self):  # k
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(MID+b)//2
        return (self.vrect(l+sw//2, t, b) + " " +
                self.diag(l+sw, mid, r, MID) + " " +
                self.diag(l+sw, mid, r, b))

    def _ll(self):  # l
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2
        return self.vrect(cx, CAP, BASE)

    def _lm(self):  # m
        sw=self.sw; l=40; r=self.adv-40; t=MID; b=BASE
        adv=self.adv; q=(r-l)//2+l
        stem_l = self.vrect(l+sw//2, t, b)
        stem_r = self.vrect(r-sw//2, t, b)
        stem_m = self.vrect(q, t+sw*2, b)
        arch1 = self.arc_stroke((l+q)//2, t, (q-l-sw)//2, sw*2, 180, 0)
        arch2 = self.arc_stroke((q+r)//2, t, (r-q-sw)//2, sw*2, 180, 0)
        return stem_l + " " + stem_r + " " + stem_m + " " + arch1 + " " + arch2

    def _ln(self):  # n
        sw=self.sw; l=40; r=self.adv-40; t=MID; b=BASE
        stem_l = self.vrect(l+sw//2, t, b)
        stem_r = self.vrect(r-sw//2, t+sw*2, b)
        arch = self.arc_stroke((l+r)//2, t, (r-l-sw)//2, sw*2, 180, 0)
        return stem_l + " " + stem_r + " " + arch

    def _lo(self):  # o
        l=40; r=self.adv-40; sw=self.sw
        cx=(l+r)//2; cy=(MID+BASE)//2; rx=(r-l)//2; ry=(BASE-MID)//2
        return self.oval_stroke(cx, cy, rx, ry)

    def _lp(self):  # p
        sw=self.sw; l=40; r=self.adv-40
        stem = self.vrect(l+sw//2, MID, DESC)
        cx=l+sw+(r-l-sw)//2; cy=(MID+BASE)//2; rx=(r-l-sw)//2; ry=(BASE-MID)//2
        bowl = self.oval_stroke(cx, cy, rx, ry)
        return stem + " " + bowl

    def _lq(self):  # q
        sw=self.sw; l=40; r=self.adv-40
        stem = self.vrect(r-sw//2, MID, DESC)
        cx=l+(r-l-sw)//2; cy=(MID+BASE)//2; rx=(r-l-sw)//2; ry=(BASE-MID)//2
        bowl = self.oval_stroke(cx, cy, rx, ry)
        return bowl + " " + stem

    def _lr(self):  # r
        sw=self.sw; l=40; r=self.adv-40
        stem = self.vrect(l+sw//2, MID, BASE)
        bump_r = l + (r-l)*70//100
        bump = (f"M{l+sw},{MID} L{bump_r},{MID} "
                f"C{r+sw},{MID} {r+sw},{MID+sw*4} {bump_r},{MID+sw*4} "
                f"L{l+sw},{MID+sw*4} Z "
                f"M{l+sw*2},{MID+sw} L{bump_r},{MID+sw} "
                f"C{r-sw//2},{MID+sw} {r-sw//2},{MID+sw*3} {bump_r},{MID+sw*3} "
                f"L{l+sw*2},{MID+sw*3} Z")
        return stem + " " + bump

    def _ls(self):  # s
        sw=self.sw; l=40; r=self.adv-40
        cx=(l+r)//2; ry=(BASE-MID)//2
        t_arc = self.arc_stroke(cx, MID+ry//2, (r-l)*4//10, ry//2, 0, -200)
        b_arc = self.arc_stroke(cx, BASE-ry//2, (r-l)*4//10, ry//2, 180, -200)
        return t_arc + " " + b_arc

    def _lt(self):  # t
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2
        stem = self.vrect(cx, CAP+sw*3, BASE)
        bar = self.hrect(l+sw, r-sw, MID)
        top = self.arc_stroke(cx, CAP+sw*3, sw*2, sw*3, 90, -90)
        return stem + " " + bar + " " + top

    def _lu(self):  # u
        sw=self.sw; l=40; r=self.adv-40
        cx=(l+r)//2; bot_cy=BASE-sw*2
        sl = self.vrect(l+sw//2, MID, bot_cy)
        sr = self.vrect(r-sw//2, MID, BASE)
        bowl = self.arc_stroke(cx, bot_cy, (r-l)//2, sw*2, 0, -180)
        return sl + " " + sr + " " + bowl

    def _lv(self):  # v
        l=40; r=self.adv-40; cx=(l+r)//2
        return (self.diag(l, MID, cx, BASE) + " " +
                self.diag(r, MID, cx, BASE))

    def _lw(self):  # w
        sw=self.sw; l=40; r=self.adv-40; q=(r-l)//2+l
        q1=l+(r-l)//4; q3=l+3*(r-l)//4
        return (self.diag(l, MID, q1, BASE) + " " +
                self.diag(r, MID, q3, BASE) + " " +
                self.diag(q1, BASE, q, (MID+BASE)//2) + " " +
                self.diag(q3, BASE, q, (MID+BASE)//2))

    def _lx(self):  # x
        l=40; r=self.adv-40
        return (self.diag(l, MID, r, BASE) + " " +
                self.diag(r, MID, l, BASE))

    def _ly(self):  # y
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2; mid=(MID+BASE)//2
        return (self.diag(l, MID, cx, mid) + " " +
                self.diag(r, MID, l, DESC))

    def _lz(self):  # z
        l=40; r=self.adv-40; sw=self.sw
        return (self.hrect(l, r, MID+sw//2) + " " +
                self.diag(r-sw, MID+sw, l+sw, BASE-sw) + " " +
                self.hrect(l, r, BASE-sw//2))

    # ── DIGITS ────────────────────────────────────────────
    def _d0(self):
        l=40; r=self.adv-40; sw=self.sw
        cx=(l+r)//2; cy=(CAP+BASE)//2; rx=(r-l)//2; ry=(BASE-CAP)//2
        o = self.oval_stroke(cx,cy,rx,ry)
        slash = self.diag(cx-rx//2, cy-ry//3, cx+rx//2, cy+ry//3)
        return o + " " + slash

    def _d1(self):
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2
        stem = self.vrect(cx, CAP, BASE)
        leg = self.diag(l+sw, CAP+sw*4, cx, CAP)
        bar = self.hrect(l, r, BASE-sw//2)
        return stem + " " + leg + " " + bar

    def _d2(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        cx=(l+r)//2; top_cy=t+sw*3
        arc = self.arc_stroke(cx, top_cy, (r-l)//2, sw*3, 0, -210)
        diag = self.diag(l+sw, b-sw*4, r-sw, t+sw*5)
        bot = self.hrect(l, r, b-sw//2)
        return arc + " " + diag + " " + bot

    def _d3(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        cx=(l+r)//2; mid=(t+b)//2
        t_arc = self.arc_stroke(cx, t+sw*3, (r-l)*45//100, sw*3, 200, -260)
        b_arc = self.arc_stroke(cx, b-sw*3, (r-l)*45//100, sw*3, 160, -300)
        return t_arc + " " + b_arc

    def _d4(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(t+b)*55//100
        return (self.diag(r-sw*3, t, l, mid) + " " +
                self.hrect(l, r, mid) + " " +
                self.vrect(r-sw*2, t, b))

    def _d5(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(t+b)//2
        top = self.hrect(l, r, t+sw//2)
        stem = self.vrect(l+sw//2, t+sw, mid)
        mid_bar = self.hrect(l, r-sw*2, mid)
        arc = self.arc_stroke((l+r)//2, b-sw*3, (r-l)*45//100, sw*3, 160, -300)
        return top + " " + stem + " " + mid_bar + " " + arc

    def _d6(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        cx=(l+r)//2; cy=(MID+b)//2; rx=(r-l)//2; ry=(b-MID)//2
        bowl = self.oval_stroke(cx, cy, rx, ry)
        arc = self.arc_stroke(cx, t+ry, rx*8//10, ry, 90, -90)
        stem = self.vrect(l+sw//2, t+ry, cy-ry)
        return bowl + " " + arc + " " + stem

    def _d7(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        return (self.hrect(l, r, t+sw//2) + " " +
                self.diag(r-sw, t+sw, l+sw, b))

    def _d8(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE; mid=(t+b)//2
        cx=(l+r)//2
        t_oval = self.oval_stroke(cx, (t+mid)//2, (r-l)*45//100, (mid-t)//2)
        b_oval = self.oval_stroke(cx, (mid+b)//2, (r-l)//2, (b-mid)//2)
        return t_oval + " " + b_oval

    def _d9(self):
        sw=self.sw; l=40; r=self.adv-40; t=CAP; b=BASE
        cx=(l+r)//2; cy=(t+MID)//2; rx=(r-l)//2; ry=(MID-t)//2
        bowl = self.oval_stroke(cx, cy, rx, ry)
        stem = self.vrect(r-sw//2, cy, b)
        arc = self.arc_stroke(cx, b-ry, rx*8//10, ry, -90, 90)
        return bowl + " " + stem + " " + arc

    # ── PUNCTUATION ───────────────────────────────────────
    def _dot(self):
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2
        return self.oval(cx, BASE-sw, sw, sw)

    def _comma(self):
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2
        return (self.oval(cx, BASE-sw, sw, sw) + " " +
                self.diag(cx-sw//2, BASE, cx+sw//4, BASE+sw*2))

    def _excl(self):
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2
        return (self.vrect(cx, CAP, BASE-sw*3) + " " +
                self.oval(cx, BASE-sw, sw, sw))

    def _quest(self):
        sw=self.sw; l=40; r=self.adv-40; cx=(l+r)//2
        arc = self.arc_stroke(cx, CAP+sw*3, (r-l)//2, sw*3, 0, -200)
        stem = self.vrect(cx, CAP+sw*5, BASE-sw*3)
        dot = self.oval(cx, BASE-sw, sw, sw)
        return arc + " " + stem + " " + dot

    def _dash(self):
        sw=self.sw; l=40; r=self.adv-40; mid=(CAP+BASE)//2
        return self.hrect(l, r, mid)

    def _under(self):
        l=40; r=self.adv-40
        return self.hrect(l, r, BASE+self.sw//2)

    def _lparen(self):
        sw=self.sw; l=40; r=self.adv-40
        cx=r; cy=(CAP+BASE)//2; rx=(r-l)*6//10; ry=(BASE-CAP)//2
        return self.arc_stroke(cx, cy, rx, ry, 120, -120)

    def _rparen(self):
        sw=self.sw; l=40; r=self.adv-40
        cx=l; cy=(CAP+BASE)//2; rx=(r-l)*6//10; ry=(BASE-CAP)//2
        return self.arc_stroke(cx, cy, rx, ry, 60, 300)

    def _slash(self):
        l=40; r=self.adv-40
        return self.diag(r-self.sw, CAP, l, BASE)

    def _at(self):
        sw=self.sw; l=40; r=self.adv-40
        cx=(l+r)//2; cy=(CAP+BASE)//2; rx=(r-l)//2; ry=(BASE-CAP)//2
        outer = self.oval_stroke(cx, cy, rx, ry)
        inner = self.oval_stroke(cx+sw, cy, rx//3, ry*4//10)
        return outer + " " + inner
