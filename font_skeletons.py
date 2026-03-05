"""
font_skeletons.py — BASE SKELETON ENGINE
=========================================
5 production-quality base fonts: Sans, Serif, Script, Display, Mono
Each glyph is stored as a list of "strokes" — mathematical primitives
(not SVG strings yet). The distortion engine operates on these primitives
before final SVG path generation.

Coordinate system:
  CAP  =  80   top of capitals
  XH   = 300   x-height (top of lowercase)
  BASE = 560   baseline
  DESC = 660   descender
  EM   = 700   full em

Each stroke is a dict:
  { type: 'oval'|'rect'|'diag'|'arc'|'bezier'|'vbar'|'hbar',
    params: {...},
    role: 'stem'|'bowl'|'bar'|'serif'|'terminal'|'counter',
    is_counter: bool  (True = punches a hole via evenodd)
  }
"""
import math

# ── CONSTANTS ──────────────────────────────────────────
CAP  =  80
XH   = 300
BASE = 560
DESC = 660
EM   = 700

# ── STROKE TYPES ───────────────────────────────────────
def vbar(cx, y1, y2, sw, role='stem'):
    return {'type':'vbar','params':{'cx':cx,'y1':y1,'y2':y2,'sw':sw},'role':role,'is_counter':False}

def hbar(x1, x2, cy, sw, role='bar'):
    return {'type':'hbar','params':{'x1':x1,'x2':x2,'cy':cy,'sw':sw},'role':role,'is_counter':False}

def diag(x1, y1, x2, y2, sw, role='stem'):
    return {'type':'diag','params':{'x1':x1,'y1':y1,'x2':x2,'y2':y2,'sw':sw},'role':role,'is_counter':False}

def oval(cx, cy, rx, ry, role='bowl', is_counter=False):
    return {'type':'oval','params':{'cx':cx,'cy':cy,'rx':rx,'ry':ry},'role':role,'is_counter':is_counter}

def arc(cx, cy, rx, ry, a1, a2, sw, role='arc'):
    return {'type':'arc','params':{'cx':cx,'cy':cy,'rx':rx,'ry':ry,'a1':a1,'a2':a2,'sw':sw},'role':role,'is_counter':False}

def bezier(pts, sw, role='curve', closed=True):
    """pts: list of (x,y) control points for cubic bezier chain"""
    return {'type':'bezier','params':{'pts':pts,'sw':sw,'closed':closed},'role':role,'is_counter':False}

def serif_foot(cx, y, width, height, role='serif'):
    return {'type':'hbar','params':{'x1':cx-width//2,'x2':cx+width//2,'cy':y,'sw':height},'role':role,'is_counter':False}


# ════════════════════════════════════════════════════════
# BASE SKELETON FACTORY
# Returns list of stroke dicts for any char + family
# ════════════════════════════════════════════════════════
def get_skeleton(char: str, family: str, adv: int) -> list:
    """
    Get the base skeleton strokes for a character.
    family: 'sans' | 'serif' | 'script' | 'display' | 'mono'
    adv: advance width
    Returns: list of stroke dicts
    """
    L   = 44
    R   = adv - 44
    W   = R - L
    CX  = (L + R) // 2

    # Stroke widths per family
    sw_map = {
        'sans':    {'stem':52,'thin':52,'serif':0},
        'serif':   {'stem':56,'thin':18,'serif':24},
        'script':  {'stem':40,'thin':22,'serif':0},
        'display': {'stem':90,'thin':90,'serif':36},
        'mono':    {'stem':50,'thin':50,'serif':0},
    }
    SW = sw_map.get(family, sw_map['sans'])
    S  = SW['stem']   # main stroke width
    T  = SW['thin']   # thin stroke (for serif contrast)
    sf = SW['serif']  # serif size

    fns = _GLYPH_MAP.get(char)
    if fns:
        strokes = fns(L, R, W, CX, S, T, sf, family, adv)
        return strokes
    # Fallback rectangle
    return [vbar(CX, CAP+S, BASE-S, S*2, 'stem')]


# ── PUNCTUATION HANDLER ─────────────────────────────────
_PUNCT_MAP = {
    '.': lambda L,R,W,CX,S,T,sf,fam,adv: [oval(CX, BASE-S, S, S, 'terminal')],
    ',': lambda L,R,W,CX,S,T,sf,fam,adv: [oval(CX, BASE-S, S, S, 'terminal'),
                                            diag(CX-S//2, BASE, CX, BASE+S*2, S//2, 'terminal')],
    '!': lambda L,R,W,CX,S,T,sf,fam,adv: [vbar(CX,CAP,BASE-S*3,S,'stem'), oval(CX,BASE-S,S,S,'terminal')],
    '-': lambda L,R,W,CX,S,T,sf,fam,adv: [hbar(L,R,(CAP+BASE)//2,S,'bar')],
    '_': lambda L,R,W,CX,S,T,sf,fam,adv: [hbar(L,R,BASE+S//2,S,'bar')],
    '/': lambda L,R,W,CX,S,T,sf,fam,adv: [diag(R-S,CAP,L,BASE,S,'stem')],
}


# ════════════════════════════════════════════════════════
# GLYPH SKELETONS — Each returns list of strokes
# All 62 chars: A-Z, a-z, 0-9
# ════════════════════════════════════════════════════════

def _glyph_A(L,R,W,CX,S,T,sf,fam,adv):
    strokes = [
        diag(CX, CAP, L, BASE, S, 'stem'),
        diag(CX, CAP, R, BASE, S, 'stem'),
        hbar(L+W//4, R-W//4, (CAP+BASE)//2, T if fam=='serif' else S, 'bar'),
    ]
    if sf: strokes += [serif_foot(L,BASE,sf*3,sf), serif_foot(R,BASE,sf*3,sf)]
    return strokes

def _glyph_B(L,R,W,CX,S,T,sf,fam,adv):
    mid = (CAP+BASE)//2
    return [
        vbar(L+S//2, CAP, BASE, S, 'stem'),
        # Top bump — outer + counter
        oval(L+S+W*33//100, (CAP+mid)//2, W*36//100, (mid-CAP)//2, 'bowl'),
        oval(L+S+W*33//100, (CAP+mid)//2, max(4,W*36//100-S), max(4,(mid-CAP)//2-S), 'counter', True),
        # Bottom bump — outer + counter
        oval(L+S+W*37//100, (mid+BASE)//2, W*40//100, (BASE-mid)//2, 'bowl'),
        oval(L+S+W*37//100, (mid+BASE)//2, max(4,W*40//100-S), max(4,(BASE-mid)//2-S), 'counter', True),
    ]

def _glyph_C(L,R,W,CX,S,T,sf,fam,adv):
    return [arc(CX,(CAP+BASE)//2, W//2,(BASE-CAP)//2, 35,325, S,'arc')]

def _glyph_D(L,R,W,CX,S,T,sf,fam,adv):
    rx=W*82//100; ry=(BASE-CAP)//2; cy=(CAP+BASE)//2; cx=L+S
    return [
        vbar(L+S//2, CAP, BASE, S, 'stem'),
        oval(cx, cy, rx, ry, 'bowl'),
        oval(cx, cy, max(4,rx-S), max(4,ry-S), 'counter', True),
    ]

def _glyph_E(L,R,W,CX,S,T,sf,fam,adv):
    mid=(CAP+BASE)//2
    return [
        vbar(L+S//2, CAP, BASE, S, 'stem'),
        hbar(L+S, R, CAP+S//2, T if fam=='serif' else S, 'bar'),
        hbar(L+S, R-W//5, mid, T if fam=='serif' else S, 'bar'),
        hbar(L+S, R, BASE-S//2, T if fam=='serif' else S, 'bar'),
    ]

def _glyph_F(L,R,W,CX,S,T,sf,fam,adv):
    mid=(CAP+BASE)//2
    return [
        vbar(L+S//2, CAP, BASE, S, 'stem'),
        hbar(L+S, R, CAP+S//2, T if fam=='serif' else S, 'bar'),
        hbar(L+S, R-W//5, mid, T if fam=='serif' else S, 'bar'),
    ]

def _glyph_G(L,R,W,CX,S,T,sf,fam,adv):
    cy=(CAP+BASE)//2
    return [
        arc(CX,cy, W//2,(BASE-CAP)//2, 15,320, S,'arc'),
        hbar(CX,R, cy+S//2, S,'bar'),
        vbar(R-S//2, cy, cy+(BASE-CAP)//4, S,'stem'),
    ]

def _glyph_H(L,R,W,CX,S,T,sf,fam,adv):
    mid=(CAP+BASE)//2
    strokes = [
        vbar(L+S//2, CAP, BASE, S,'stem'),
        vbar(R-S//2, CAP, BASE, S,'stem'),
        hbar(L+S, R-S, mid, T if fam=='serif' else S,'bar'),
    ]
    if sf:
        for cx,y in [(L,CAP),(L,BASE),(R,CAP),(R,BASE)]:
            strokes.append(serif_foot(cx,y,sf*3,sf))
    return strokes

def _glyph_I(L,R,W,CX,S,T,sf,fam,adv):
    if sf:
        return [
            vbar(CX, CAP, BASE, S*2,'stem'),
            hbar(CX-S*3,CX+S*3, CAP, sf*2,'serif'),
            hbar(CX-S*3,CX+S*3, BASE, sf*2,'serif'),
        ]
    return [vbar(CX, CAP, BASE, S,'stem')]

def _glyph_J(L,R,W,CX,S,T,sf,fam,adv):
    cx=R-S//2; bot=BASE-S*3
    return [
        vbar(cx, CAP, bot, S,'stem'),
        arc(L+S*2, bot, (W-S)//2, S*3, 0,-180, S,'arc'),
    ]

def _glyph_K(L,R,W,CX,S,T,sf,fam,adv):
    mid=(XH+BASE)//2
    return [
        vbar(L+S//2, CAP, BASE, S,'stem'),
        diag(L+S, mid, R, CAP, S,'stem'),
        diag(L+S, mid, R, BASE, S,'stem'),
    ]

def _glyph_L(L,R,W,CX,S,T,sf,fam,adv):
    strokes = [
        vbar(L+S//2, CAP, BASE, S,'stem'),
        hbar(L+S, R, BASE-S//2, T if fam=='serif' else S,'bar'),
    ]
    if sf: strokes.append(serif_foot(L,CAP,sf*3,sf))
    return strokes

def _glyph_M(L,R,W,CX,S,T,sf,fam,adv):
    return [
        vbar(L+S//2, CAP, BASE, S,'stem'),
        vbar(R-S//2, CAP, BASE, S,'stem'),
        diag(L+S, CAP, CX, (CAP+BASE)//2, S,'stem'),
        diag(R-S, CAP, CX, (CAP+BASE)//2, S,'stem'),
    ]

def _glyph_N(L,R,W,CX,S,T,sf,fam,adv):
    return [
        vbar(L+S//2, CAP, BASE, S,'stem'),
        vbar(R-S//2, CAP, BASE, S,'stem'),
        diag(L+S, CAP, R-S, BASE, S,'stem'),
    ]

def _glyph_O(L,R,W,CX,S,T,sf,fam,adv):
    cx=CX; cy=(CAP+BASE)//2; rx=W//2; ry=(BASE-CAP)//2
    return [
        oval(cx, cy, rx, ry,'bowl'),
        oval(cx, cy, max(5,rx-S), max(5,ry-S),'counter',True),
    ]

def _glyph_P(L,R,W,CX,S,T,sf,fam,adv):
    mid=(CAP+BASE)//2-S; cx=L+S
    return [
        vbar(L+S//2, CAP, BASE, S,'stem'),
        oval(cx, (CAP+mid)//2, W*36//100, (mid-CAP)//2,'bowl'),
        oval(cx, (CAP+mid)//2, max(4,W*36//100-S), max(4,(mid-CAP)//2-S),'counter',True),
    ]

def _glyph_Q(L,R,W,CX,S,T,sf,fam,adv):
    return _glyph_O(L,R,W,CX,S,T,sf,fam,adv) + [
        diag(CX, XH+W//6, R, BASE+S*2, S,'stem')
    ]

def _glyph_R(L,R,W,CX,S,T,sf,fam,adv):
    mid=(CAP+BASE)//2-S
    return _glyph_P(L,R,W,CX,S,T,sf,fam,adv) + [
        diag(L+S+S//2, mid, R, BASE, S,'stem')
    ]

def _glyph_S(L,R,W,CX,S,T,sf,fam,adv):
    ry=(BASE-CAP)//2
    return [
        arc(CX, CAP+ry//2, W*44//100, ry//2, 0,-210, S,'arc'),
        arc(CX, BASE-ry//2, W*44//100, ry//2, 180,-210, S,'arc'),
    ]

def _glyph_T(L,R,W,CX,S,T,sf,fam,adv):
    strokes = [
        hbar(L,R, CAP+S//2, T if fam=='serif' else S,'bar'),
        vbar(CX, CAP+S, BASE, S,'stem'),
    ]
    if sf:
        strokes += [serif_foot(L,CAP,sf*3,sf), serif_foot(R,CAP,sf*3,sf), serif_foot(CX,BASE,sf*3,sf)]
    return strokes

def _glyph_U(L,R,W,CX,S,T,sf,fam,adv):
    bot=BASE-S*2
    return [
        vbar(L+S//2, CAP, bot, S,'stem'),
        arc(CX, bot, W//2, S*2, 0,-180, S,'arc'),
        vbar(R-S//2, CAP, bot, S,'stem'),
    ]

def _glyph_V(L,R,W,CX,S,T,sf,fam,adv):
    return [diag(L,CAP,CX,BASE,S,'stem'), diag(R,CAP,CX,BASE,S,'stem')]

def _glyph_W(L,R,W,CX,S,T,sf,fam,adv):
    q1=L+W//4; q3=L+3*W//4; mid=(CAP+BASE)//2+S*2
    return [
        diag(L,CAP,q1,BASE,S,'stem'), diag(R,CAP,q3,BASE,S,'stem'),
        diag(q1,BASE,CX,mid,S,'stem'), diag(q3,BASE,CX,mid,S,'stem'),
    ]

def _glyph_X(L,R,W,CX,S,T,sf,fam,adv):
    return [diag(L,CAP,R,BASE,S,'stem'), diag(R,CAP,L,BASE,S,'stem')]

def _glyph_Y(L,R,W,CX,S,T,sf,fam,adv):
    mid=(CAP+BASE)//2
    return [
        diag(L,CAP,CX,mid,S,'stem'),
        diag(R,CAP,CX,mid,S,'stem'),
        vbar(CX,mid,BASE,S,'stem'),
    ]

def _glyph_Z(L,R,W,CX,S,T,sf,fam,adv):
    return [
        hbar(L,R, CAP+S//2, T if fam=='serif' else S,'bar'),
        diag(R-S,CAP+S, L+S,BASE-S, S,'stem'),
        hbar(L,R, BASE-S//2, T if fam=='serif' else S,'bar'),
    ]

# ── LOWERCASE ─────────────────────────────────────────

def _glyph_la(L,R,W,CX,S,T,sf,fam,adv):
    cy=(XH+BASE)//2; rx=W//2; ry=(BASE-XH)//2
    return [
        oval(CX, cy, rx, ry,'bowl'),
        oval(CX, cy, max(4,rx-S), max(4,ry-S),'counter',True),
        vbar(R-S//2, XH+S, BASE, S,'stem'),
    ]

def _glyph_lb(L,R,W,CX,S,T,sf,fam,adv):
    cx=L+S+(W-S)//2; cy=(XH+BASE)//2; rx=(W-S)//2; ry=(BASE-XH)//2
    return [
        vbar(L+S//2, CAP, BASE, S,'stem'),
        oval(cx, cy, rx, ry,'bowl'),
        oval(cx, cy, max(4,rx-S), max(4,ry-S),'counter',True),
    ]

def _glyph_lc(L,R,W,CX,S,T,sf,fam,adv):
    cy=(XH+BASE)//2; rx=W//2; ry=(BASE-XH)//2
    return [arc(CX, cy, rx, ry, 35,325, S,'arc')]

def _glyph_ld(L,R,W,CX,S,T,sf,fam,adv):
    cx=L+(W-S)//2; cy=(XH+BASE)//2; rx=(W-S)//2; ry=(BASE-XH)//2
    return [
        oval(cx, cy, rx, ry,'bowl'),
        oval(cx, cy, max(4,rx-S), max(4,ry-S),'counter',True),
        vbar(R-S//2, CAP, BASE, S,'stem'),
    ]

def _glyph_le(L,R,W,CX,S,T,sf,fam,adv):
    cy=(XH+BASE)//2; rx=W//2; ry=(BASE-XH)//2
    return [
        arc(CX, cy, rx, ry, 10,330, S,'arc'),
        hbar(L+S, R-S//2, cy, S,'bar'),
    ]

def _glyph_lf(L,R,W,CX,S,T,sf,fam,adv):
    return [
        vbar(CX, CAP+S*2, BASE, S,'stem'),
        arc(CX, CAP+S*2, S*3, S*2, 90,-90, S,'arc'),
        hbar(L, CX+S*3, XH, S,'bar'),
    ]

def _glyph_lg(L,R,W,CX,S,T,sf,fam,adv):
    cy=(XH+BASE)//2; rx=W//2; ry=(BASE-XH)//2
    return [
        oval(CX, cy, rx, ry,'bowl'),
        oval(CX, cy, max(4,rx-S), max(4,ry-S),'counter',True),
        vbar(R-S//2, XH, DESC-S*2, S,'stem'),
        arc(CX, DESC-S*2, rx*9//10, S*2, 0,-180, S,'arc'),
    ]

def _glyph_lh(L,R,W,CX,S,T,sf,fam,adv):
    at=XH-S
    return [
        vbar(L+S//2, CAP, BASE, S,'stem'),
        arc(CX, at, (W-S)//2, S*3, 180,0, S,'arc'),
        vbar(R-S//2, at+S*3, BASE, S,'stem'),
    ]

def _glyph_li(L,R,W,CX,S,T,sf,fam,adv):
    return [
        vbar(CX, XH, BASE, S,'stem'),
        oval(CX, XH-S*3, S*0.8, S*0.8,'terminal'),
    ]

def _glyph_lj(L,R,W,CX,S,T,sf,fam,adv):
    cx=CX+S
    return [
        vbar(cx, XH, DESC-S*2, S,'stem'),
        arc(cx-S*3, DESC-S*2, S*3, S*2, 0,-180, S,'arc'),
        oval(cx, XH-S*3, S*0.8, S*0.8,'terminal'),
    ]

def _glyph_lk(L,R,W,CX,S,T,sf,fam,adv):
    mid=(XH+BASE)//2
    return [
        vbar(L+S//2, CAP, BASE, S,'stem'),
        diag(L+S, mid, R, XH, S,'stem'),
        diag(L+S, mid, R, BASE, S,'stem'),
    ]

def _glyph_ll(L,R,W,CX,S,T,sf,fam,adv):
    return [vbar(CX, CAP, BASE, S,'stem')]

def _glyph_lm(L,R,W,CX,S,T,sf,fam,adv):
    q=CX
    return [
        vbar(L+S//2, XH, BASE, S,'stem'),
        vbar(R-S//2, XH, BASE, S,'stem'),
        vbar(q, XH+S*2, BASE, S,'stem'),
        arc((L+q)//2, XH, (q-L-S)//2, S*2, 180,0, S,'arc'),
        arc((q+R)//2, XH, (R-q-S)//2, S*2, 180,0, S,'arc'),
    ]

def _glyph_ln(L,R,W,CX,S,T,sf,fam,adv):
    return [
        vbar(L+S//2, XH, BASE, S,'stem'),
        arc(CX, XH, (W-S)//2, S*2, 180,0, S,'arc'),
        vbar(R-S//2, XH+S*2, BASE, S,'stem'),
    ]

def _glyph_lo(L,R,W,CX,S,T,sf,fam,adv):
    cy=(XH+BASE)//2; rx=W//2; ry=(BASE-XH)//2
    return [
        oval(CX, cy, rx, ry,'bowl'),
        oval(CX, cy, max(4,rx-S), max(4,ry-S),'counter',True),
    ]

def _glyph_lp(L,R,W,CX,S,T,sf,fam,adv):
    cx=L+S+(W-S)//2; cy=(XH+BASE)//2; rx=(W-S)//2; ry=(BASE-XH)//2
    return [
        vbar(L+S//2, XH, DESC, S,'stem'),
        oval(cx, cy, rx, ry,'bowl'),
        oval(cx, cy, max(4,rx-S), max(4,ry-S),'counter',True),
    ]

def _glyph_lq(L,R,W,CX,S,T,sf,fam,adv):
    cx=L+(W-S)//2; cy=(XH+BASE)//2; rx=(W-S)//2; ry=(BASE-XH)//2
    return [
        oval(cx, cy, rx, ry,'bowl'),
        oval(cx, cy, max(4,rx-S), max(4,ry-S),'counter',True),
        vbar(R-S//2, XH, DESC, S,'stem'),
    ]

def _glyph_lr(L,R,W,CX,S,T,sf,fam,adv):
    bw=W*65//100; bh=(BASE-XH)//2
    return [
        vbar(L+S//2, XH, BASE, S,'stem'),
        arc(L+S+bw//2, XH, bw//2, bh//2, 180,0, S,'arc'),
    ]

def _glyph_ls(L,R,W,CX,S,T,sf,fam,adv):
    ry=(BASE-XH)//2
    return [
        arc(CX, XH+ry//2, W*42//100, ry//2, 0,-210, S,'arc'),
        arc(CX, BASE-ry//2, W*42//100, ry//2, 180,-210, S,'arc'),
    ]

def _glyph_lt(L,R,W,CX,S,T,sf,fam,adv):
    return [
        vbar(CX, CAP+S*3, BASE, S,'stem'),
        hbar(L+S, R-S, XH, S,'bar'),
        arc(CX, CAP+S*3, S*2, S*2, 90,-90, S,'arc'),
    ]

def _glyph_lu(L,R,W,CX,S,T,sf,fam,adv):
    bot=BASE-S*2
    return [
        vbar(L+S//2, XH, bot, S,'stem'),
        arc(CX, bot, W//2, S*2, 0,-180, S,'arc'),
        vbar(R-S//2, XH, BASE, S,'stem'),
    ]

def _glyph_lv(L,R,W,CX,S,T,sf,fam,adv):
    return [diag(L,XH,CX,BASE,S,'stem'), diag(R,XH,CX,BASE,S,'stem')]

def _glyph_lw(L,R,W,CX,S,T,sf,fam,adv):
    q1=L+W//4; q3=L+3*W//4; mid=(XH+BASE)//2
    return [
        diag(L,XH,q1,BASE,S,'stem'), diag(R,XH,q3,BASE,S,'stem'),
        diag(q1,BASE,CX,mid,S,'stem'), diag(q3,BASE,CX,mid,S,'stem'),
    ]

def _glyph_lx(L,R,W,CX,S,T,sf,fam,adv):
    return [diag(L,XH,R,BASE,S,'stem'), diag(R,XH,L,BASE,S,'stem')]

def _glyph_ly(L,R,W,CX,S,T,sf,fam,adv):
    mid=(XH+BASE)//2
    return [diag(L,XH,CX,mid,S,'stem'), diag(R,XH,L,DESC,S,'stem')]

def _glyph_lz(L,R,W,CX,S,T,sf,fam,adv):
    return [
        hbar(L,R, XH+S//2, S,'bar'),
        diag(R-S,XH+S, L+S,BASE-S, S,'stem'),
        hbar(L,R, BASE-S//2, S,'bar'),
    ]

# ── DIGITS ────────────────────────────────────────────

def _glyph_d0(L,R,W,CX,S,T,sf,fam,adv):
    cy=(CAP+BASE)//2; rx=W//2; ry=(BASE-CAP)//2
    return [
        oval(CX,cy,rx,ry,'bowl'), oval(CX,cy,max(5,rx-S),max(5,ry-S),'counter',True),
        diag(CX-rx//2,cy-ry//3, CX+rx//2,cy+ry//3, S,'stem'),
    ]

def _glyph_d1(L,R,W,CX,S,T,sf,fam,adv):
    return [
        vbar(CX,CAP,BASE,S,'stem'),
        diag(L+S,CAP+S*4,CX,CAP,S,'stem'),
        hbar(L,R,BASE-S//2,S,'bar'),
    ]

def _glyph_d2(L,R,W,CX,S,T,sf,fam,adv):
    top=CAP+S*3
    return [
        arc(CX,top, W//2,S*3, 0,-210, S,'arc'),
        diag(R-S,CAP+S*5, L+S,BASE-S, S,'stem'),
        hbar(L,R, BASE-S//2, S,'bar'),
    ]

def _glyph_d3(L,R,W,CX,S,T,sf,fam,adv):
    return [
        arc(CX,CAP+S*3, W*45//100,S*3, 200,-260, S,'arc'),
        arc(CX,BASE-S*3, W*45//100,S*3, 160,-300, S,'arc'),
    ]

def _glyph_d4(L,R,W,CX,S,T,sf,fam,adv):
    mid=(CAP+BASE)*55//100
    return [
        diag(R-S*3,CAP, L,mid, S,'stem'),
        hbar(L,R, mid, S,'bar'),
        vbar(R-S*2, CAP, BASE, S,'stem'),
    ]

def _glyph_d5(L,R,W,CX,S,T,sf,fam,adv):
    mid=(CAP+BASE)//2
    return [
        hbar(L,R, CAP+S//2, S,'bar'),
        vbar(L+S//2, CAP+S, mid, S,'stem'),
        arc(CX,BASE-S*3, W*45//100,S*3, 160,-300, S,'arc'),
    ]

def _glyph_d6(L,R,W,CX,S,T,sf,fam,adv):
    cy=(XH+BASE)//2; rx=W//2; ry=(BASE-XH)//2
    return [
        oval(CX,cy,rx,ry,'bowl'), oval(CX,cy,max(4,rx-S),max(4,ry-S),'counter',True),
        arc(CX,CAP+ry, rx*8//10,ry, 90,-90, S,'arc'),
        vbar(L+S//2, CAP+ry, cy-ry, S,'stem'),
    ]

def _glyph_d7(L,R,W,CX,S,T,sf,fam,adv):
    return [
        hbar(L,R, CAP+S//2, S,'bar'),
        diag(R-S,CAP+S, L+S,BASE, S,'stem'),
    ]

def _glyph_d8(L,R,W,CX,S,T,sf,fam,adv):
    mid=(CAP+BASE)//2
    return [
        oval(CX,(CAP+mid)//2, W*43//100,(mid-CAP)//2,'bowl'),
        oval(CX,(CAP+mid)//2, max(4,W*43//100-S),max(4,(mid-CAP)//2-S),'counter',True),
        oval(CX,(mid+BASE)//2, W//2,(BASE-mid)//2,'bowl'),
        oval(CX,(mid+BASE)//2, max(4,W//2-S),max(4,(BASE-mid)//2-S),'counter',True),
    ]

def _glyph_d9(L,R,W,CX,S,T,sf,fam,adv):
    cy=(CAP+XH)//2; rx=W//2; ry=(XH-CAP)//2
    return [
        oval(CX,cy,rx,ry,'bowl'), oval(CX,cy,max(4,rx-S),max(4,ry-S),'counter',True),
        vbar(R-S//2, cy, BASE, S,'stem'),
    ]


# ── CHARACTER MAP ──────────────────────────────────────
_GLYPH_MAP = {
    'A':_glyph_A,'B':_glyph_B,'C':_glyph_C,'D':_glyph_D,'E':_glyph_E,
    'F':_glyph_F,'G':_glyph_G,'H':_glyph_H,'I':_glyph_I,'J':_glyph_J,
    'K':_glyph_K,'L':_glyph_L,'M':_glyph_M,'N':_glyph_N,'O':_glyph_O,
    'P':_glyph_P,'Q':_glyph_Q,'R':_glyph_R,'S':_glyph_S,'T':_glyph_T,
    'U':_glyph_U,'V':_glyph_V,'W':_glyph_W,'X':_glyph_X,'Y':_glyph_Y,'Z':_glyph_Z,
    'a':_glyph_la,'b':_glyph_lb,'c':_glyph_lc,'d':_glyph_ld,'e':_glyph_le,
    'f':_glyph_lf,'g':_glyph_lg,'h':_glyph_lh,'i':_glyph_li,'j':_glyph_lj,
    'k':_glyph_lk,'l':_glyph_ll,'m':_glyph_lm,'n':_glyph_ln,'o':_glyph_lo,
    'p':_glyph_lp,'q':_glyph_lq,'r':_glyph_lr,'s':_glyph_ls,'t':_glyph_lt,
    'u':_glyph_lu,'v':_glyph_lv,'w':_glyph_lw,'x':_glyph_lx,'y':_glyph_ly,'z':_glyph_lz,
    '0':_glyph_d0,'1':_glyph_d1,'2':_glyph_d2,'3':_glyph_d3,'4':_glyph_d4,
    '5':_glyph_d5,'6':_glyph_d6,'7':_glyph_d7,'8':_glyph_d8,'9':_glyph_d9,
    **_PUNCT_MAP,
}
