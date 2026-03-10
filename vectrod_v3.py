"""
vectrod_v3.py  —  Vectrod DNA Matrix Engine v3.0
=================================================
TEMEL FİZİK:
  shape_library.place(path, cx, cy, SIZE, angle)
    → SIZE = pixel çapı. Şekil ±0.5 birim, SIZE=96 → 96px çap.
  Dekorasyon terminal noktasından DIŞA büyür, advance'e sığar.
  UPM=1000, CAP=800, SW minimum 44.

DNA:
  stroke_weight : int 44-80
  decoration    : floral | cyber | gothic | kawaii | retro | minimal
  density       : float 0-1
  deco_size_mul : float 1.5-3.0   (SIZE = SW × deco_size_mul)
  shapes        : list of shape_library names
"""

import math, io, os
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen   import Cu2QuPen
from fontTools.svgLib.path     import SVGPath as SVGPathLib

UPM=1000; CAP=800; XH=560; BASE=0; DESC=-160; K=0.5523

# ── YARDIMCI ─────────────────────────────────────────────────────
def _j(*p): return " ".join(x for x in p if x and x.strip())

# ── STROKE PRİMİTİFLERİ ──────────────────────────────────────────

def stroke(x1,y1,x2,y2,sw):
    sw=max(6,sw); dx,dy=x2-x1,y2-y1; ln=math.hypot(dx,dy)
    if ln<1: return ""
    nx,ny=-dy/ln*(sw/2), dx/ln*(sw/2); ux,uy=dx/ln*(sw/2), dy/ln*(sw/2)
    return (f"M{x1+nx:.1f},{y1+ny:.1f} L{x2+nx:.1f},{y2+ny:.1f} "
            f"C{x2+nx+ux*K:.1f},{y2+ny+uy*K:.1f} {x2+ux+nx*K:.1f},{y2+uy+ny*K:.1f} {x2+ux:.1f},{y2+uy:.1f} "
            f"C{x2+ux-nx*K:.1f},{y2+uy-ny*K:.1f} {x2-nx+ux*K:.1f},{y2-ny+uy*K:.1f} {x2-nx:.1f},{y2-ny:.1f} "
            f"L{x1-nx:.1f},{y1-ny:.1f} "
            f"C{x1-nx-ux*K:.1f},{y1-ny-uy*K:.1f} {x1-ux-nx*K:.1f},{y1-uy-ny*K:.1f} {x1-ux:.1f},{y1-uy:.1f} "
            f"C{x1-ux+nx*K:.1f},{y1-uy+ny*K:.1f} {x1+nx-ux*K:.1f},{y1+ny-uy*K:.1f} {x1+nx:.1f},{y1+ny:.1f} Z")

def arc_thick(cx,cy,rx,ry,a1d,a2d,sw):
    sw=max(6,sw); N=20; a1=math.radians(a1d); a2=math.radians(a2d)
    while a2<=a1: a2+=2*math.pi
    pts=[(cx+rx*math.cos(a1+(a2-a1)*i/N), cy+ry*math.sin(a1+(a2-a1)*i/N)) for i in range(N+1)]
    h=sw/2; op=[]; ip=[]
    for i,(px,py) in enumerate(pts):
        if i==0: ddx,ddy=pts[1][0]-px,pts[1][1]-py
        elif i==len(pts)-1: ddx,ddy=px-pts[-2][0],py-pts[-2][1]
        else: ddx,ddy=pts[i+1][0]-pts[i-1][0],pts[i+1][1]-pts[i-1][1]
        ln=math.hypot(ddx,ddy) or 0.001; nx2,ny2=-ddy/ln*h, ddx/ln*h
        op.append((px+nx2,py+ny2)); ip.append((px-nx2,py-ny2))
    r=["M{:.1f},{:.1f}".format(*op[0])]
    for pt in op[1:]: r.append("L{:.1f},{:.1f}".format(*pt))
    r.append("L{:.1f},{:.1f}".format(*ip[-1]))
    for pt in reversed(ip[:-1]): r.append("L{:.1f},{:.1f}".format(*pt))
    r.append("Z"); return " ".join(r)

def oval_donut(cx,cy,rx,ry,sw):
    sw=max(6,sw)
    def el(ex,ey,ccw=False):
        kx,ky=ex*K,ey*K
        if not ccw:
            return (f"M{cx:.1f},{cy-ey:.1f} C{cx+kx:.1f},{cy-ey:.1f} {cx+ex:.1f},{cy-ky:.1f} {cx+ex:.1f},{cy:.1f} "
                    f"C{cx+ex:.1f},{cy+ky:.1f} {cx+kx:.1f},{cy+ey:.1f} {cx:.1f},{cy+ey:.1f} "
                    f"C{cx-kx:.1f},{cy+ey:.1f} {cx-ex:.1f},{cy+ky:.1f} {cx-ex:.1f},{cy:.1f} "
                    f"C{cx-ex:.1f},{cy-ky:.1f} {cx-kx:.1f},{cy-ey:.1f} {cx:.1f},{cy-ey:.1f} Z")
        else:
            return (f"M{cx:.1f},{cy-ey:.1f} C{cx-kx:.1f},{cy-ey:.1f} {cx-ex:.1f},{cy-ky:.1f} {cx-ex:.1f},{cy:.1f} "
                    f"C{cx-ex:.1f},{cy+ky:.1f} {cx-kx:.1f},{cy+ey:.1f} {cx:.1f},{cy+ey:.1f} "
                    f"C{cx+kx:.1f},{cy+ey:.1f} {cx+ex:.1f},{cy+ky:.1f} {cx+ex:.1f},{cy:.1f} "
                    f"C{cx+ex:.1f},{cy-ky:.1f} {cx+kx:.1f},{cy-ey:.1f} {cx:.1f},{cy-ey:.1f} Z")
    return el(rx+sw/2,ry+sw/2)+" "+el(max(6,rx-sw/2),max(6,ry-sw/2),ccw=True)

def dot_circle(cx,cy,r):
    kx,ky=r*K,r*K
    return (f"M{cx:.0f},{cy-r:.0f} C{cx+kx:.0f},{cy-r:.0f} {cx+r:.0f},{cy-ky:.0f} {cx+r:.0f},{cy:.0f} "
            f"C{cx+r:.0f},{cy+ky:.0f} {cx+kx:.0f},{cy+r:.0f} {cx:.0f},{cy+r:.0f} "
            f"C{cx-kx:.0f},{cy+r:.0f} {cx-r:.0f},{cy+ky:.0f} {cx-r:.0f},{cy:.0f} "
            f"C{cx-r:.0f},{cy-ky:.0f} {cx-kx:.0f},{cy-r:.0f} {cx:.0f},{cy-r:.0f} Z")

# ── DEKORASYON ───────────────────────────────────────────────────

class Deco:
    """
    shape_library üzerinden terminal dekorasyonu.
    SIZE = SW × deco_size_mul → place() doğrudan pixel çapı alır.
    """
    def __init__(self, dna):
        from shape_library import get_shape, place as sl_place
        self._get   = get_shape
        self._place = sl_place
        sw          = max(44, int(dna.get('stroke_weight', 44)))
        mul         = float(dna.get('deco_size_mul', 2.2))
        self.size   = int(sw * mul)
        dens        = float(dna.get('density', 0.5))
        self.do_top  = dens >= 0.20
        self.do_base = dens >= 0.50
        self.do_side = dens >= 0.75
        raw_shapes   = dna.get('shapes', _def_shapes(dna.get('decoration','floral')))
        self.shapes  = [s for s in raw_shapes if s] or ['leaf']

    def _shape(self, idx): return self.shapes[idx % len(self.shapes)]

    def put(self, cx, cy, angle_deg=0, idx=0, mul=1.0):
        """Doğrudan koordinata yerleştir. Minimum 70px — görünür olmak zorunda."""
        try:
            sz = max(70, int(self.size * mul))
            return self._place(self._get(self._shape(idx)), cx, cy, sz, angle_deg)
        except: return ""

    def top(self, cx, y_top, idx=0, mul=1.0):
        """Üst terminal: şekil merkezi y_top + size*0.55 yukarıda."""
        if not self.do_top: return ""
        off = int(self.size * mul * 0.55)
        return self.put(cx, y_top + off, angle_deg=0, idx=idx, mul=mul)

    def base(self, cx, y_base, idx=0, mul=0.80):
        """Alt terminal: şekil merkezi y_base - size*0.55 aşağıda."""
        if not self.do_base: return ""
        off = int(self.size * mul * 0.55)
        return self.put(cx, y_base - off, angle_deg=0, idx=idx, mul=mul)

    def side_r(self, x_right, cy, idx=0, mul=0.70):
        if not self.do_side: return ""
        off = int(self.size * mul * 0.55)
        return self.put(x_right + off, cy, angle_deg=0, idx=idx, mul=mul)


def _def_shapes(deco):
    return {'floral':['flower','leaf','petal'],
            'cyber':['lightning','diamond','hexagon'],
            'gothic':['crown_spike','diamond'],
            'kawaii':['heart','flower4'],
            'retro':['diamond','arrow_right'],
            'minimal':[]}.get(deco, ['leaf'])


# ── GLYPH BUILDER ────────────────────────────────────────────────

class GB:
    def __init__(self, dna):
        self.sw  = max(44, min(80, int(dna.get('stroke_weight', 44))))
        self.dna = dna
        self.d   = Deco(dna)
        SB       = max(55, self.sw + 20)
        self.SB  = SB
        W        = int(CAP * 0.72)
        self.W0  = W   # base width

    def dims(self, wf=1.0):
        SB=self.SB; W=int(self.W0*wf)
        L=SB; R=SB+W; CX=(L+R)//2; adv=W+2*SB
        return L,R,CX,adv

    def build(self, c, idx=0):
        sw=self.sw; d=self.d
        s=lambda x1,y1,x2,y2,w=None: stroke(x1,y1,x2,y2,w or sw)
        a=lambda cx,cy,rx,ry,a1,a2: arc_thick(cx,cy,rx,ry,a1,a2,sw)
        o=lambda cx,cy,rx,ry: oval_donut(cx,cy,rx,ry,sw)

        # ── UPPERCASE ──────────────────────────────────────────────
        if c=='A':
            L,R,CX,adv=self.dims(1.0); by=int(CAP*0.42)
            p=_j(s(L,BASE,CX,CAP),s(R,BASE,CX,CAP),
                 s(L+int((R-L)*0.24),by,R-int((R-L)*0.24),by))
            p=_j(p,d.top(CX,CAP,idx))
        elif c=='B':
            L,R,CX,adv=self.dims(1.0); Lx=L+sw//2; mid=int(CAP*0.52)
            top_rx=int((R-Lx)*0.78); top_ry=(CAP-mid)//2
            bot_rx=int((R-Lx)*0.88); bot_ry=mid//2
            p=_j(s(Lx,BASE,Lx,CAP),
                 arc_thick(Lx,mid+top_ry,top_rx,top_ry,270,90,sw),
                 arc_thick(Lx,bot_ry,    bot_rx,bot_ry,270,90,sw))
            p=_j(p,d.top(Lx,CAP,idx),d.base(Lx,BASE,idx+1,0.8))
        elif c=='C':
            L,R,CX,adv=self.dims(1.1); rx=(R-L)//2-sw//2; ry=CAP//2-sw//2
            p=a(CX,CAP//2,rx,ry,32,328)
            a1r=math.radians(32); tx=CX+rx*math.cos(a1r); ty=CAP//2+ry*math.sin(a1r)
            p=_j(p,d.put(tx,ty+int(d.size*0.52),-90,idx) if d.do_top else "")
        elif c=='D':
            L,R,CX,adv=self.dims(1.1); Lx=L+sw//2
            p=_j(s(Lx,BASE,Lx,CAP),a(Lx,CAP//2,R-Lx-sw//2,CAP//2,270,90))
            p=_j(p,d.top(Lx,CAP,idx),d.base(Lx,BASE,idx+1,0.8))
        elif c=='E':
            L,R,CX,adv=self.dims(0.95); Lx=L+sw//2; mid=int(CAP*0.50)
            p=_j(s(Lx,BASE,Lx,CAP),s(Lx,CAP,R,CAP),s(Lx,mid,R-int((R-L)*0.12),mid),s(Lx,BASE,R,BASE))
            p=_j(p,d.top(Lx,CAP,idx),d.base(Lx,BASE,idx+1,0.75))
        elif c=='F':
            L,R,CX,adv=self.dims(0.92); Lx=L+sw//2; mid=int(CAP*0.54)
            p=_j(s(Lx,BASE,Lx,CAP),s(Lx,CAP,R,CAP),s(Lx,mid,R-int((R-L)*0.18),mid))
            p=_j(p,d.top(Lx,CAP,idx),d.base(Lx,BASE,idx+1,0.75))
        elif c=='G':
            L,R,CX,adv=self.dims(1.1); rx=(R-L)//2-sw//2; ry=CAP//2-sw//2
            p=_j(a(CX,CAP//2,rx,ry,15,325),s(CX,CAP//2,CX+rx,CAP//2))
            a1r=math.radians(15); tx=CX+rx*math.cos(a1r); ty=CAP//2+ry*math.sin(a1r)
            p=_j(p,d.put(tx,ty+int(d.size*0.52),-90,idx) if d.do_top else "")
        elif c=='H':
            L,R,CX,adv=self.dims(1.0); cy=int(CAP*0.48)
            p=_j(s(L+sw//2,BASE,L+sw//2,CAP),s(R-sw//2,BASE,R-sw//2,CAP),s(L+sw,cy,R-sw,cy))
            p=_j(p,d.top(L+sw//2,CAP,idx),d.top(R-sw//2,CAP,idx+1),
                 d.base(L+sw//2,BASE,idx+2,0.75),d.base(R-sw//2,BASE,idx,0.75))
        elif c=='I':
            L,R,CX,adv=self.dims(0.48); W=R-L
            p=_j(s(CX,BASE,CX,CAP),s(CX-W//3,CAP,CX+W//3,CAP),s(CX-W//3,BASE,CX+W//3,BASE))
            p=_j(p,d.top(CX,CAP,idx))
        elif c=='J':
            L,R,CX,adv=self.dims(0.52); Rx=R-sw//2; hcy=int(CAP*0.22); W=R-L
            p=_j(s(Rx,hcy,Rx,CAP),s(Rx-W//2,CAP,Rx+W//4,CAP),a(Rx-W//3,hcy,W//3,int(CAP*0.20),0,180))
            p=_j(p,d.top(Rx,CAP,idx))
        elif c=='K':
            L,R,CX,adv=self.dims(1.0); Lx=L+sw//2; mid=int(CAP*0.48)
            p=_j(s(Lx,BASE,Lx,CAP),s(Lx+sw,mid,R,CAP),s(Lx+sw,mid,R,BASE))
            p=_j(p,d.top(Lx,CAP,idx),d.base(Lx,BASE,idx+1,0.75))
        elif c=='L':
            L,R,CX,adv=self.dims(0.95); Lx=L+sw//2
            p=_j(s(Lx,BASE,Lx,CAP),s(Lx,BASE,R,BASE))
            p=_j(p,d.top(Lx,CAP,idx),d.side_r(R,BASE,idx+1,0.65))
        elif c=='M':
            L,R,CX,adv=self.dims(1.28)
            p=_j(s(L+sw//2,BASE,L+sw//2,CAP),s(R-sw//2,BASE,R-sw//2,CAP),
                 s(L+sw,CAP,CX,int(CAP*0.38)),s(R-sw,CAP,CX,int(CAP*0.38)))
            p=_j(p,d.top(L+sw//2,CAP,idx),d.top(R-sw//2,CAP,idx+1))
        elif c=='N':
            L,R,CX,adv=self.dims(1.0)
            p=_j(s(L+sw//2,BASE,L+sw//2,CAP),s(R-sw//2,BASE,R-sw//2,CAP),s(L+sw,CAP,R-sw,BASE))
            p=_j(p,d.top(L+sw//2,CAP,idx),d.top(R-sw//2,CAP,idx+1))
        elif c=='O':
            L,R,CX,adv=self.dims(1.1); rx=(R-L)//2-sw//2; ry=CAP//2-sw//2
            p=o(CX,CAP//2,rx,ry)
            p=_j(p,d.top(CX,CAP//2+ry+sw//2,idx,0.85))
        elif c=='P':
            L,R,CX,adv=self.dims(1.0); Lx=L+sw//2; mid=int(CAP*0.50)
            p=_j(s(Lx,BASE,Lx,CAP),a(Lx,mid+(CAP-mid)//2,int((R-Lx)*0.90),(CAP-mid)//2,270,90))
            p=_j(p,d.top(Lx,CAP,idx),d.base(Lx,BASE,idx+1,0.8))
        elif c=='Q':
            L,R,CX,adv=self.dims(1.1); rx=(R-L)//2-sw//2; ry=CAP//2-sw//2
            p=_j(o(CX,CAP//2,rx,ry),s(CX+int(rx*0.4),CAP//2-int(ry*0.4),CX+rx+sw,CAP//2-ry-sw*2))
            p=_j(p,d.top(CX,CAP//2+ry+sw//2,idx,0.85))
        elif c=='R':
            L,R,CX,adv=self.dims(1.0); Lx=L+sw//2; mid=int(CAP*0.50); bx=int((R-Lx)*0.90)
            p=_j(s(Lx,BASE,Lx,CAP),a(Lx,mid+(CAP-mid)//2,bx,(CAP-mid)//2,270,90),s(Lx+int(bx*0.6),mid,R,BASE))
            p=_j(p,d.top(Lx,CAP,idx),d.base(R,BASE,idx+1,0.7))
        elif c=='S':
            L,R,CX,adv=self.dims(1.0); rx=(R-L)//2-sw//2
            cyt=int(CAP*0.68); ryt=int(CAP*0.26); cyb=int(CAP*0.32); ryb=int(CAP*0.26)
            # Üst: sola açık yay (180°→355°), Alt: sağa açık yay (5°→180°)
            p=_j(a(CX,cyt,rx,ryt,180,355),a(CX,cyb,rx,ryb,5,180))
            # Terminal dekorasyonları: üst-sağ ve alt-sol uçlar
            import math as _m
            tx=CX+rx*_m.cos(_m.radians(180)); ty=cyt+ryt*_m.sin(_m.radians(180))
            bx=CX+rx*_m.cos(_m.radians(180)); by=cyb+ryb*_m.sin(_m.radians(180))
            p=_j(p,d.put(tx,ty+int(d.size*0.55),-90,idx) if d.do_top else "",
                 d.put(bx,by-int(d.size*0.45),90,idx+1,0.8) if d.do_base else "")
        elif c=='T':
            L,R,CX,adv=self.dims(1.0)
            p=_j(s(CX,BASE,CX,CAP),s(L,CAP,R,CAP))
            p=_j(p,d.top(CX,CAP,idx,1.0),d.base(CX,BASE,idx+2,0.8))
        elif c=='U':
            L,R,CX,adv=self.dims(1.0); bcy=int(CAP*0.28); brx=(R-L-sw)//2
            p=_j(s(L+sw//2,bcy,L+sw//2,CAP),s(R-sw//2,bcy,R-sw//2,CAP),a(CX,bcy,brx,int(CAP*0.28),180,0))
            p=_j(p,d.top(L+sw//2,CAP,idx),d.top(R-sw//2,CAP,idx+1))
        elif c=='V':
            L,R,CX,adv=self.dims(1.0)
            p=_j(s(L,CAP,CX,BASE),s(R,CAP,CX,BASE))
            p=_j(p,d.top(L,CAP,idx,0.85),d.top(R,CAP,idx+1,0.85),d.base(CX,BASE,idx+2,0.8))
        elif c=='W':
            L,R,CX,adv=self.dims(1.28); q1=(L*2+R)//3; q2=(L+R*2)//3
            p=_j(s(L,CAP,q1,BASE),s(q1,BASE,CX,int(CAP*0.44)),s(CX,int(CAP*0.44),q2,BASE),s(q2,BASE,R,CAP))
            p=_j(p,d.top(L,CAP,idx,0.85),d.top(R,CAP,idx+1,0.85))
        elif c=='X':
            L,R,CX,adv=self.dims(1.0)
            p=_j(s(L,CAP,R,BASE),s(R,CAP,L,BASE))
            p=_j(p,d.top(L,CAP,idx,0.85),d.top(R,CAP,idx+1,0.85))
        elif c=='Y':
            L,R,CX,adv=self.dims(1.0); mid=int(CAP*0.46)
            p=_j(s(L,CAP,CX,mid),s(R,CAP,CX,mid),s(CX,BASE,CX,mid))
            p=_j(p,d.top(L,CAP,idx,0.85),d.top(R,CAP,idx+1,0.85),d.base(CX,BASE,idx+2,0.8))
        elif c=='Z':
            L,R,CX,adv=self.dims(1.0)
            p=_j(s(L,CAP,R,CAP),s(L,BASE,R,BASE),s(R,CAP,L,BASE))
            p=_j(p,d.top(R,CAP,idx,0.85),d.base(L,BASE,idx+1,0.75))

        # ── LOWERCASE ──────────────────────────────────────────────
        elif c=='a':
            L,R,CX,adv=self.dims(0.82); rx=(R-L)//2-sw//2; ry=XH//2-sw//4
            p=_j(a(CX,XH//2,rx,ry,22,338),s(R-sw//2,BASE,R-sw//2,XH))
            p=_j(p,d.top(CX,XH,idx,0.85))
        elif c=='b':
            L,R,CX,adv=self.dims(0.82); Lx=L+sw//2
            p=_j(s(Lx,BASE,Lx,CAP),a(Lx,XH//2,R-Lx-sw//2,XH//2,270,90))
            p=_j(p,d.top(Lx,CAP,idx))
        elif c=='c':
            L,R,CX,adv=self.dims(0.82); rx=(R-L)//2-sw//2; ry=XH//2-sw//4
            p=a(CX,XH//2,rx,ry,35,325)
            a1r=math.radians(35); tx=CX+rx*math.cos(a1r); ty=XH//2+ry*math.sin(a1r)
            p=_j(p,d.put(tx,ty+int(d.size*0.52),-90,idx) if d.do_top else "")
        elif c=='d':
            L,R,CX,adv=self.dims(0.82); Rx=R-sw//2
            p=_j(s(Rx,BASE,Rx,CAP),a(Rx,XH//2,R-L-sw//2,XH//2,90,270))
            p=_j(p,d.top(Rx,CAP,idx))
        elif c=='e':
            L,R,CX,adv=self.dims(0.82); rx=(R-L)//2-sw//2; ry=XH//2-sw//4
            p=_j(a(CX,XH//2,rx,ry,8,320),s(CX-rx+sw,XH//2,CX+rx-sw,XH//2,max(6,sw-8)))
            a1r=math.radians(8); tx=CX+rx*math.cos(a1r); ty=XH//2+ry*math.sin(a1r)
            p=_j(p,d.put(tx,ty+int(d.size*0.52),-90,idx) if d.do_top else "")
        elif c=='f':
            L,R,CX,adv=self.dims(0.52); W=R-L; hcx=CX+W//3; hcy=int(CAP*0.82)
            p=_j(s(CX,BASE,CX,hcy),a(hcx,hcy,W//3,int(CAP*0.13),180,270),
                 s(CX-W//2,int(XH*0.68),CX+W//2,int(XH*0.68)))
            p=_j(p,d.top(hcx+W//3,hcy,idx,0.85))
        elif c=='g':
            L,R,CX,adv=self.dims(0.82); Rx=R-sw//2; rx=(R-L)//2-sw//2; ry=XH//2-sw//4
            p=_j(a(CX,XH//2,rx,ry,22,338),s(Rx,DESC//2,Rx,XH),
                 a(CX,DESC//2,(R-L-sw)//2,abs(DESC//2)-sw//2,0,180))
            p=_j(p,d.top(CX,XH,idx,0.85))
        elif c=='h':
            L,R,CX,adv=self.dims(0.82); Lx=L+sw//2; W=R-L; acx=Lx+W//3
            p=_j(s(Lx,BASE,Lx,CAP),a(acx,XH,W//3,int(XH*0.30),180,0),s(acx+W//3,BASE,acx+W//3,XH))
            p=_j(p,d.top(Lx,CAP,idx))
        elif c=='i':
            L,R,CX,adv=self.dims(0.38); dr=max(sw//2+2,int(sw*0.62))
            p=_j(s(CX,BASE,CX,XH),dot_circle(CX,XH+dr*3,dr))
            p=_j(p,d.top(CX,XH+dr*4,idx,0.7))
        elif c=='j':
            L,R,CX,adv=self.dims(0.38); CX2=CX+sw//3; dr=max(sw//2+2,int(sw*0.62))
            W=R-L
            p=_j(s(CX2,DESC//2,CX2,XH),a(CX2-W//2,DESC//2,W//2,int(abs(DESC//2)*0.75),0,180),
                 dot_circle(CX2,XH+dr*3,dr))
        elif c=='k':
            L,R,CX,adv=self.dims(0.82); Lx=L+sw//2; mid=int(XH*0.50)
            p=_j(s(Lx,BASE,Lx,CAP),s(Lx+sw,mid,R,XH),s(Lx+sw,mid,R,BASE))
            p=_j(p,d.top(Lx,CAP,idx))
        elif c=='l':
            L,R,CX,adv=self.dims(0.35)
            p=_j(s(CX,BASE,CX,CAP),s(CX-sw,BASE,CX+sw*2,BASE))
            p=_j(p,d.top(CX,CAP,idx))
        elif c=='m':
            L,R,CX,adv=self.dims(1.10); W=R-L; st=W//3
            p=_j(s(L+sw//2,BASE,L+sw//2,XH),
                 a(L+sw+st//2,XH,max(6,st//2-2),int(XH*0.28),180,0),
                 s(L+sw+st,BASE,L+sw+st,XH),
                 a(L+sw+st+st//2,XH,max(6,st//2-2),int(XH*0.28),180,0),
                 s(L+sw+st*2,BASE,L+sw+st*2,XH))
            p=_j(p,d.top(L+sw//2,XH,idx,0.8))
        elif c=='n':
            L,R,CX,adv=self.dims(0.82); Lx=L+sw//2; W=R-L; acx=Lx+W//3
            p=_j(s(Lx,BASE,Lx,XH),a(acx,XH,W//3,int(XH*0.30),180,0),s(acx+W//3,BASE,acx+W//3,XH))
            p=_j(p,d.top(Lx,XH,idx,0.85))
        elif c=='o':
            L,R,CX,adv=self.dims(0.88); rx=(R-L)//2-sw//2; ry=XH//2-sw//4
            p=oval_donut(CX,XH//2,rx,ry,sw)
            p=_j(p,d.top(CX,XH//2+ry+sw//2,idx,0.80))
        elif c=='p':
            L,R,CX,adv=self.dims(0.82); Lx=L+sw//2; W=R-L
            p=_j(s(Lx,DESC//2,Lx,XH),a(Lx,XH//2,W-sw//2,XH//2,270,90))
            p=_j(p,d.top(Lx,XH,idx,0.85))
        elif c=='q':
            L,R,CX,adv=self.dims(0.82); Rx=R-sw//2; W=R-L
            p=_j(s(Rx,DESC//2,Rx,XH),a(Rx,XH//2,W-sw//2,XH//2,90,270))
            p=_j(p,d.top(Rx,XH,idx,0.85))
        elif c=='r':
            L,R,CX,adv=self.dims(0.55); Lx=L+sw//2; W=R-L; acx=Lx+W//3
            p=_j(s(Lx,BASE,Lx,XH),a(acx,XH,W//3,int(XH*0.28),180,60))
            p=_j(p,d.top(Lx,XH,idx,0.85))
        elif c=='s':
            L,R,CX,adv=self.dims(0.82); rx=(R-L)//2-sw//2
            # S harfi: üst sola açık yay + alt sağa açık yay
            # Üst: cy=XH*0.68, sola açık → 0°→180° (soldan sağa, üstte)  
            # Alt: cy=XH*0.32, sağa açık → 180°→360° (sağdan sola, altta)
            cyt=int(XH*0.68); ryt=int(XH*0.27)
            cyb=int(XH*0.32); ryb=int(XH*0.27)
            p=_j(a(CX,cyt,rx,ryt,0,190),a(CX,cyb,rx,ryb,180,370))
        elif c=='t':
            L,R,CX,adv=self.dims(0.52); W=R-L
            p=_j(s(CX,BASE,CX,int(CAP*0.80)),s(CX-W//2,int(XH*0.68),CX+W//2,int(XH*0.68)))
            p=_j(p,d.top(CX,int(CAP*0.80),idx,0.85))
        elif c=='u':
            L,R,CX,adv=self.dims(0.82); bcy=int(XH*0.32); brx=(R-L-sw)//2
            p=_j(s(L+sw//2,bcy,L+sw//2,XH),s(R-sw//2,BASE,R-sw//2,XH),a(CX,bcy,brx,int(XH*0.32),180,0))
            p=_j(p,d.top(L+sw//2,XH,idx,0.85))
        elif c=='v':
            L,R,CX,adv=self.dims(0.82)
            p=_j(s(L,XH,CX,BASE),s(R,XH,CX,BASE))
            p=_j(p,d.top(L,XH,idx,0.85),d.top(R,XH,idx+1,0.85))
        elif c=='w':
            L,R,CX,adv=self.dims(1.05); q1=(L*2+R)//3; q2=(L+R*2)//3
            p=_j(s(L,XH,q1,BASE),s(q1,BASE,CX,int(XH*0.45)),s(CX,int(XH*0.45),q2,BASE),s(q2,BASE,R,XH))
            p=_j(p,d.top(L,XH,idx,0.8),d.top(R,XH,idx+1,0.8))
        elif c=='x':
            L,R,CX,adv=self.dims(0.82)
            p=_j(s(L,XH,R,BASE),s(R,XH,L,BASE))
            p=_j(p,d.top(L,XH,idx,0.8),d.top(R,XH,idx+1,0.8))
        elif c=='y':
            L,R,CX,adv=self.dims(0.82); mid=int(XH*0.44)
            p=_j(s(L,XH,CX,mid),s(R,XH,CX,mid),s(CX,DESC//2,CX,mid),
                 a(CX-(R-L-sw)//2,DESC//2,(R-L-sw)//2,abs(DESC//2)-sw//2,0,180))
            p=_j(p,d.top(L,XH,idx,0.8))
        elif c=='z':
            L,R,CX,adv=self.dims(0.82)
            p=_j(s(L,XH,R,XH),s(L,BASE,R,BASE),s(R,XH,L,BASE))
            p=_j(p,d.top(R,XH,idx,0.8))

        # ── RAKAMLAR ──────────────────────────────────────────────
        elif c=='0':
            L,R,CX,adv=self.dims(1.1); rx=(R-L)//2-sw//2; ry=CAP//2-sw//2
            p=o(CX,CAP//2,rx,ry)
        elif c=='1':
            L,R,CX,adv=self.dims(0.48); W=R-L
            p=_j(s(CX,BASE,CX,CAP),s(CX-W//3,BASE,CX+W//2,BASE),s(CX-W//4,int(CAP*0.76),CX,CAP))
            p=_j(p,d.top(CX,CAP,idx,0.85))
        elif c=='2':
            L,R,CX,adv=self.dims(1.0); arx=(R-L)//2-sw//2; ary=int(CAP*0.26)
            acy=int(CAP*0.72)
            # Üst yay: sola açık (180°→350°) → aşağı çizgi → alt bar
            import math as _m
            a2r=_m.radians(350); tx=CX+arx*_m.cos(a2r); ty=acy+ary*_m.sin(a2r)
            p=_j(a(CX,acy,arx,ary,180,350),s(tx,ty,L,BASE+sw//2),s(L,BASE,R,BASE))
        elif c=='3':
            L,R,CX,adv=self.dims(1.0); rx=(R-L)//2-sw//2
            # Üst: sağa açık (180°→355°), Alt: sağa açık (5°→180°)
            p=_j(a(CX,int(CAP*0.70),rx,int(CAP*0.24),180,355),
                 a(CX,int(CAP*0.30),rx,int(CAP*0.26),5,180))
        elif c=='4':
            L,R,CX,adv=self.dims(1.0); sx=L+int((R-L)*0.66)
            p=_j(s(L,CAP,sx-sw//2,int(CAP*0.44)),s(L,int(CAP*0.44),R,int(CAP*0.44)),s(sx,BASE,sx,CAP))
            p=_j(p,d.top(sx,CAP,idx,0.85))
        elif c=='5':
            L,R,CX,adv=self.dims(1.0); Lx=L+sw//2
            p=_j(s(L,CAP,R,CAP),s(Lx,int(CAP*0.50),Lx,CAP),a(CX,int(CAP*0.28),(R-L)//2-sw//2,int(CAP*0.26),175,355))
        elif c=='6':
            L,R,CX,adv=self.dims(1.0); rx=(R-L)//2-sw//2; ry=int(CAP*0.28)
            # Alt: tam oval (counter açık), Üst: sola kıvrılan kanca
            p=_j(oval_donut(CX,int(CAP*0.32),rx,ry,sw),
                 a(CX,int(CAP*0.60),rx,int(CAP*0.28),90,180))
        elif c=='7':
            L,R,CX,adv=self.dims(1.0)
            p=_j(s(L,CAP,R,CAP),s(R,CAP,L+int((R-L)*0.33),BASE))
            p=_j(p,d.top(R,CAP,idx,0.85))
        elif c=='8':
            L,R,CX,adv=self.dims(1.0); rx=(R-L)//2-sw//2
            p=_j(oval_donut(CX,int(CAP*0.72),rx,int(CAP*0.22),sw),oval_donut(CX,int(CAP*0.28),rx,int(CAP*0.26),sw))
        elif c=='9':
            L,R,CX,adv=self.dims(1.0); rx=(R-L)//2-sw//2
            p=_j(oval_donut(CX,int(CAP*0.68),rx,int(CAP*0.26),sw),
                 a(CX,int(CAP*0.40),rx,int(CAP*0.28),0,270))

        # ── NOKTALAMA ─────────────────────────────────────────────
        elif c=='.':
            r=max(sw//2+4,int(sw*0.65)); cx2=self.SB+r
            p=dot_circle(cx2,r,r); adv=r*2+self.SB*2
        elif c==',':
            r=max(sw//2+4,int(sw*0.65)); cx2=self.SB+r
            p=_j(dot_circle(cx2,r,r),stroke(cx2,r,cx2-int(r*0.8),-int(r*1.5),int(sw*0.45)))
            adv=r*2+self.SB*2
        elif c=='!':
            L,R,CX,adv=self.dims(0.38); r=max(sw//2+4,int(sw*0.65))
            p=_j(s(CX,int(XH*0.32),CX,XH),dot_circle(CX,r,r))
            p=_j(p,d.top(CX,XH,idx,0.85))
        elif c=='?':
            L,R,CX,adv=self.dims(0.72); r=max(sw//2+4,int(sw*0.65)); rx2=(R-L)//3
            p=_j(a(CX,int(CAP*0.66),rx2,int(CAP*0.20),215,355),s(CX,int(XH*0.30),CX,int(CAP*0.48)),dot_circle(CX,r,r))
        elif c=='-':
            L,R,CX,adv=self.dims(0.55); p=s(L,CAP//2,R,CAP//2)
        elif c==':':
            r=max(sw//2+4,int(sw*0.65)); cx2=self.SB+r
            p=_j(dot_circle(cx2,r,r),dot_circle(cx2,XH//2+r,r)); adv=r*2+self.SB*2
        elif c==';':
            r=max(sw//2+4,int(sw*0.65)); cx2=self.SB+r
            p=_j(dot_circle(cx2,XH//2+r,r),dot_circle(cx2,r,r),stroke(cx2,r,cx2-int(r*0.8),-int(r*1.5),int(sw*0.45)))
            adv=r*2+self.SB*2
        elif c=='/':
            L,R,CX,adv=self.dims(0.75); p=s(R-sw,CAP,L,BASE)
        elif c in ('(','['):
            L,R,CX,adv=self.dims(0.45); p=arc_thick(CX+int((R-L)*0.1),CAP//2,int((R-L)*0.45),(CAP-BASE)//2,120,240,sw)
        elif c in (')',']'):
            L,R,CX,adv=self.dims(0.45); p=arc_thick(CX-int((R-L)*0.1),CAP//2,int((R-L)*0.45),(CAP-BASE)//2,300,420,sw)
        elif c=='+':
            L,R,CX,adv=self.dims(0.85); p=_j(s(L+sw,CAP//2,R-sw,CAP//2),s(CX,CAP//5,CX,CAP*4//5))
        elif c=='_':
            L,R,CX,adv=self.dims(1.0); p=s(L,BASE-sw//2,R,BASE-sw//2)
        elif c=='@':
            L,R,CX,adv=self.dims(1.1); rx=(R-L)//2-sw//2; ry=CAP//2-sw//2
            p=_j(oval_donut(CX,CAP//2,rx,ry,sw),s(CX+sw,CAP//2+ry-sw,CX+rx-sw,CAP//2,sw-8))
        elif c=='#':
            L,R,CX,adv=self.dims(1.0)
            p=_j(s(CX-int((R-L)*0.2),CAP+sw,CX-int((R-L)*0.2),BASE-sw,sw//2),
                 s(CX+int((R-L)*0.2),CAP+sw,CX+int((R-L)*0.2),BASE-sw,sw//2),
                 s(L+sw,CAP//2-sw*2,R-sw,CAP//2-sw*2,sw//2),
                 s(L+sw,CAP//2+sw*2,R-sw,CAP//2+sw*2,sw//2))
        elif c=='&':
            L,R,CX,adv=self.dims(1.1); rx=(R-L)//2-sw//2
            p=_j(a(CX,int(CAP*0.68),rx,int(CAP*0.26),0,360),s(L,BASE,R,BASE))
        elif c=='=':
            L,R,CX,adv=self.dims(0.85)
            p=_j(s(L+sw,CAP//2-sw*2,R-sw,CAP//2-sw*2),s(L+sw,CAP//2+sw*2,R-sw,CAP//2+sw*2))
        elif c=='*':
            L,R,CX,adv=self.dims(0.55); cy2=CAP//2; r=int((R-L)*0.4)
            p=_j(s(CX,cy2-r,CX,cy2+r,sw//2),
                 s(CX-int(r*0.87),cy2-r//2,CX+int(r*0.87),cy2+r//2,sw//2),
                 s(CX-int(r*0.87),cy2+r//2,CX+int(r*0.87),cy2-r//2,sw//2))
        elif c=='%':
            L,R,CX,adv=self.dims(1.0); r=int((R-L)*0.14)
            p=_j(oval_donut(L+r+sw,CAP-r-sw,r,r,sw//2),
                 oval_donut(R-r-sw,BASE+r+sw,r,r,sw//2),
                 s(R-sw,CAP,L+sw,BASE,sw//2))
        elif c==' ':
            p=""; adv=int(CAP*0.32)
        else:
            L,R,CX,adv=self.dims(0.82); p=s(CX-sw,BASE,CX-sw,CAP)

        return p.strip(), adv


# ── FONT BUILD ───────────────────────────────────────────────────

CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?:;-_/()[]+@#&=*% '

def _to_glyph(path_d):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg"><path d="{path_d}" fill-rule="evenodd"/></svg>'
    pen=TTGlyphPen(None)
    SVGPathLib(io.BytesIO(svg.encode())).draw(Cu2QuPen(pen,max_err=0.5,reverse_direction=True))
    return pen.glyph()

def _empty():
    pen=TTGlyphPen(None); pen.moveTo((0,0)); pen.lineTo((10,0)); pen.lineTo((10,10)); pen.lineTo((0,10))
    pen.closePath(); return pen.glyph()

def build_font(dna:dict, output_path:str, font_name:str="VectrodFont") -> str:
    gb=GB(dna); sw=gb.sw; chars=list(CHARS)
    gnames=['.notdef','space']+[f'uni{ord(c):04X}' for c in chars if c!=' ']
    fb=FontBuilder(UPM,isTTF=True); fb.setupGlyphOrder(gnames)
    cmap_d={32:'space'}; cmap_d.update({ord(c):f'uni{ord(c):04X}' for c in chars if c!=' '})
    fb.setupCharacterMap(cmap_d)
    gmap={'.notdef':_empty(),'space':_empty()}
    mets={'.notdef':(500,0),'space':(int(CAP*0.32),0)}
    ok=fail=0
    for idx,c in enumerate(chars):
        if c==' ': continue
        gn=f'uni{ord(c):04X}'
        try:
            path,adv=gb.build(c,idx)
            if not path: raise ValueError("empty")
            gmap[gn]=_to_glyph(path); mets[gn]=(adv,0); ok+=1
        except Exception as e:
            print(f"  ✗ '{c}': {e}"); gmap[gn]=_empty(); mets[gn]=(600,0); fail+=1
    conv={}
    for gn,g in gmap.items():
        if not hasattr(g,'draw'): conv[gn]=g; continue
        try:
            p2=TTGlyphPen(None); g.draw(Cu2QuPen(p2,max_err=0.5,reverse_direction=False)); conv[gn]=p2.glyph()
        except: conv[gn]=g
    deco_room=gb.d.size+40; ASC=CAP+deco_room; DSC=DESC-20
    fb.setupGlyf(conv); fb.setupHorizontalMetrics(mets)
    fb.setupHorizontalHeader(ascent=ASC,descent=DSC)
    fb.setupNameTable({"familyName":font_name,"styleName":"Regular",
                       "uniqueFontIdentifier":f"{font_name}-Regular",
                       "fullName":f"{font_name} Regular","version":"Version 3.0",
                       "psName":f"{font_name}-Regular"})
    fb.setupOS2(sTypoAscender=ASC,sTypoDescender=DSC,sTypoLineGap=0,
                usWinAscent=ASC+30,usWinDescent=abs(DSC),
                sxHeight=XH,sCapHeight=CAP,usWeightClass=max(100,min(900,int(sw*7))),
                fsType=0,fsSelection=0x40,achVendID="VCTD",
                ulUnicodeRange1=0b10000000000000000000000011111111)
    fb.setupPost(isFixedPitch=0,underlinePosition=-80,underlineThickness=sw)
    fb.setupHead(unitsPerEm=UPM,lowestRecPPEM=8,indexToLocFormat=0)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)),exist_ok=True)
    fb.font.save(output_path)
    sz=os.path.getsize(output_path)//1024
    print(f"  ✅ v3 TTF: {sz}KB | {ok}✓ {fail}✗ | sw={sw} deco_size={gb.d.size}")
    return output_path


def build_otf(dna:dict, output_path:str, font_name:str="VectrodFont") -> str:
    """TTF'den OTF türet — aynı veriyle CFF tabanlı."""
    try:
        from fontTools.ttLib import TTFont as _TT
        ttf_path = output_path.replace('.otf', '.ttf')
        if not os.path.exists(ttf_path): return None
        # fontTools'ta TTF→OTF dönüşümü: tt2otf veya manuel CFF
        # En güvenli: TTFont'u OTF olarak kaydet (CFF olmadan, ama .otf uzantılı)
        tt = _TT(ttf_path)
        tt.save(output_path)
        tt.close()
        sz = os.path.getsize(output_path)//1024
        print(f"  ✅ v3 OTF: {sz}KB")
        return output_path
    except Exception as e:
        print(f"  [OTF] Error: {e}"); return None


# ── DNA OLUŞTURUCULAR ────────────────────────────────────────────

GEMINI_PROMPT="""You are Vectrod's creative director and type designer. Analyze the font style request and output ONLY valid JSON — no markdown, no explanation, nothing else.

Output exactly this structure:
{"stroke_weight":52,"decoration":"floral","density":0.65,"deco_size_mul":2.8,"shapes":["flower","leaf","petal"]}

PARAMETER GUIDE:
stroke_weight (int 44-80):
  44-50 = thin / light / elegant / fashion / luxury
  51-60 = regular / normal / clean / minimal
  61-70 = semi-bold / strong / display
  71-80 = bold / heavy / impact / black / fat

decoration (pick ONE best match):
  "floral"  = flowers, botanical, nature, garden, spring, petal, bloom, rose, romantic
  "cyber"   = cyberpunk, tech, neon, digital, glitch, matrix, sci-fi, hacker, futuristic
  "gothic"  = gothic, horror, dark, medieval, vampire, skull, death, metal, blackletter
  "kawaii"  = kawaii, cute, bubbly, sweet, chibi, pastel, adorable, playful, round
  "retro"   = retro, vintage, western, slab, poster, old, classic, 70s, 80s, grunge
  "minimal" = minimal, swiss, geometric, clean, modern, corporate, simple, sans

density (float 0.0-0.8):
  0.0 = no decorations at all
  0.3 = subtle / sparse decorations
  0.55 = moderate decorations
  0.70 = rich / abundant decorations
  0.80 = maximum decorations — every terminal

deco_size_mul (float 1.6-3.2):
  Decoration size = stroke_weight × this value.
  1.6-2.0 = small subtle decorations
  2.0-2.6 = normal decorations
  2.6-3.2 = large prominent decorations (use for floral/kawaii)

shapes (list of 1-3, CHOOSE BEST for the style):
  Floral: "flower" "flower4" "leaf" "petal"
  Cute:   "heart" "flower4" "petal"
  Tech:   "lightning" "hexagon" "gear_tooth" "diamond"
  Gothic: "crown_spike" "diamond"
  Retro:  "diamond" "gear_tooth"
  FORBIDDEN — NEVER USE: star4, star5, star6, starburst, starburst_ray

DECISION EXAMPLES (study these carefully):
  "cute minimalist flower font"        → {"stroke_weight":48,"decoration":"floral","density":0.70,"deco_size_mul":2.8,"shapes":["flower","petal","leaf"]}
  "botanical garden spring blossom"    → {"stroke_weight":54,"decoration":"floral","density":0.75,"deco_size_mul":3.0,"shapes":["flower","leaf","petal"]}
  "bold cyberpunk neon display"        → {"stroke_weight":72,"decoration":"cyber","density":0.50,"deco_size_mul":2.2,"shapes":["lightning","hexagon","diamond"]}
  "dark gothic horror medieval"        → {"stroke_weight":68,"decoration":"gothic","density":0.60,"deco_size_mul":2.4,"shapes":["crown_spike","diamond"]}
  "kawaii bubbly sweet pastel"         → {"stroke_weight":70,"decoration":"kawaii","density":0.75,"deco_size_mul":2.8,"shapes":["heart","flower4","petal"]}
  "vintage retro western poster"       → {"stroke_weight":74,"decoration":"retro","density":0.40,"deco_size_mul":2.0,"shapes":["diamond","gear_tooth"]}
  "elegant luxury fashion thin"        → {"stroke_weight":46,"decoration":"floral","density":0.38,"deco_size_mul":2.0,"shapes":["petal","leaf"]}
  "clean minimal geometric modern"     → {"stroke_weight":52,"decoration":"minimal","density":0.0,"deco_size_mul":1.0,"shapes":[]}
  "heavy bold black impact"            → {"stroke_weight":80,"decoration":"minimal","density":0.0,"deco_size_mul":1.0,"shapes":[]}
  "sci-fi tech futuristic hacker"      → {"stroke_weight":58,"decoration":"cyber","density":0.55,"deco_size_mul":2.3,"shapes":["lightning","gear_tooth","hexagon"]}
  "cute pink flower kawaii girly"      → {"stroke_weight":62,"decoration":"kawaii","density":0.80,"deco_size_mul":3.0,"shapes":["flower4","heart","petal"]}

Be creative and precise. The JSON must perfectly capture the essence of the requested style."""


def dna_from_gemini(prompt:str, api_key:str):
    import urllib.request, json, re, time

    MODELS = [
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
        "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent",
    ]

    for attempt, base_url in enumerate(MODELS):
        url = f"{base_url}?key={api_key}"
        try:
            body=json.dumps({
                "system_instruction":{"parts":[{"text":GEMINI_PROMPT}]},
                "contents":[{"parts":[{"text":f"Font style: {prompt}"}]}],
                "generationConfig":{"temperature":0.45,"maxOutputTokens":400}
            }).encode()
            req=urllib.request.Request(url,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=25) as r:
                data=json.loads(r.read().decode())

            model_name = base_url.split("/models/")[1]
            print(f"[Gemini DNA] Connected: {model_name}")

            if "error" in data:
                raise RuntimeError(f"API error: {data['error'].get('message',str(data['error']))[:150]}")
            if "candidates" not in data or not data["candidates"]:
                raise RuntimeError(f"No candidates: {str(data)[:200]}")

            text=data["candidates"][0]["content"]["parts"][0]["text"].strip()
            text=re.sub(r'^```json\s*|\s*```$','',text,flags=re.MULTILINE).strip()
            s,e=text.find("{"),text.rfind("}")
            if s==-1 or e==-1: raise RuntimeError(f"No JSON: {text[:100]}")
            dna=json.loads(text[s:e+1])

            dna["stroke_weight"] = max(44, min(80, int(dna.get("stroke_weight", 54))))
            dna["density"]       = max(0.0, min(0.8, float(dna.get("density", 0.5))))
            dna["deco_size_mul"] = max(1.6, min(3.2, float(dna.get("deco_size_mul", 2.2))))
            valid_decos = ("floral","cyber","gothic","kawaii","retro","minimal")
            dna["decoration"]    = dna.get("decoration","floral") if dna.get("decoration") in valid_decos else "floral"
            bad = {"star4","star5","star6","starburst","starburst_ray"}
            dna["shapes"] = [sh for sh in dna.get("shapes",[]) if sh and sh.lower() not in bad][:3]
            if not dna["shapes"]:
                dna["shapes"] = _def_shapes(dna["decoration"])

            print(f"[Gemini DNA] ✓ sw={dna['stroke_weight']} deco={dna['decoration']} "
                  f"density={dna['density']} shapes={dna['shapes']} mul={dna['deco_size_mul']}")
            return dna

        except urllib.error.HTTPError as e:
            body_err = e.read().decode("utf-8","replace")[:200]
            print(f"[Gemini DNA] {model_name} → HTTP {e.code}: {body_err}")
            time.sleep(1)
        except Exception as e:
            model_name = base_url.split("/models/")[1]
            print(f"[Gemini DNA] {model_name} → {e}")
            time.sleep(1)

    print("[Gemini DNA] All models failed → using heuristic")
    return None


def dna_heuristic(prompt:str) -> dict:
    p=prompt.lower()
    # Kalınlık modifier — her stil için geçerli
    is_bold    = any(w in p for w in ['bold','heavy','thick','black','fat','güçlü','kalın'])
    is_thin    = any(w in p for w in ['thin','light','hair','ultra','delicate','ince','minimal'])
    sw_mod     = +20 if is_bold else (-10 if is_thin else 0)

    if any(w in p for w in ['floral','flower','botanical','leaf','spring','bloom','petal','vine',
                              'romantic','nature','garden','çiçek','cicek','blossom']):
        sw = max(44, min(80, 52 + sw_mod))
        dn = 0.65 if any(w in p for w in ['rich','heavy','dense','full']) else 0.55
        return {"stroke_weight":sw,"decoration":"floral","density":dn,"deco_size_mul":2.8,"shapes":["flower","leaf","petal"]}
    elif any(w in p for w in ['cyber','punk','neon','tech','glitch','digital','hacker','matrix','sci-fi']):
        sw = max(44, min(80, 58 + sw_mod))
        return {"stroke_weight":sw,"decoration":"cyber","density":0.45,"deco_size_mul":2.2,"shapes":["lightning","diamond","hexagon"]}
    elif any(w in p for w in ['gothic','horror','dark','skull','death','blood','metal','medieval','vampire']):
        sw = max(44, min(80, 68 + sw_mod))
        return {"stroke_weight":sw,"decoration":"gothic","density":0.60,"deco_size_mul":2.4,"shapes":["crown_spike","diamond"]}
    elif any(w in p for w in ['kawaii','cute','bubbly','round','chibi','pastel','sweet','adorable']):
        sw = max(44, min(80, 68 + sw_mod))
        return {"stroke_weight":sw,"decoration":"kawaii","density":0.62,"deco_size_mul":2.4,"shapes":["heart","flower4","petal"]}
    elif any(w in p for w in ['retro','western','vintage','slab','poster','cowboy']):
        sw = max(44, min(80, 76 + sw_mod))
        return {"stroke_weight":sw,"decoration":"retro","density":0.40,"deco_size_mul":1.8,"shapes":["diamond","arrow_right"]}
    elif any(w in p for w in ['elegant','luxury','fashion','editorial','vogue','chic']):
        sw = max(44, min(80, 44 + sw_mod))
        return {"stroke_weight":sw,"decoration":"floral","density":0.40,"deco_size_mul":2.0,"shapes":["leaf","petal"]}
    elif any(w in p for w in ['bold','black','heavy','impact','display','poster']):
        return {"stroke_weight":80,"decoration":"minimal","density":0.0,"deco_size_mul":1.0,"shapes":[]}
    else:
        sw = max(44, min(80, 58 + sw_mod))
        return {"stroke_weight":sw,"decoration":"minimal","density":0.0,"deco_size_mul":1.0,"shapes":[]}


def build_from_prompt(prompt:str, font_name:str, output_dir:str, gemini_key:str='') -> tuple:
    """
    Tam pipeline: prompt → DNA → TTF + OTF.
    Returns (ttf_path, dna, glyph_svgs)   # app.py uyumluluğu için
    """
    os.makedirs(output_dir,exist_ok=True)
    dna=None
    if gemini_key: dna=dna_from_gemini(prompt,gemini_key)
    if dna is None:
        dna=dna_heuristic(prompt)
        print(f"[v3] Heuristic: sw={dna['stroke_weight']} deco={dna['decoration']} shapes={dna['shapes']}")
    ttf=os.path.join(output_dir,f"{font_name}_Regular.ttf")
    otf=os.path.join(output_dir,f"{font_name}_Regular.otf")
    build_font(dna,ttf,font_name)
    # OTF: TTF kopyası farklı uzantıyla (tüm font viewer'lar okur)
    try:
        import shutil; shutil.copy2(ttf, otf)
        print(f"  ✅ v3 OTF: {os.path.getsize(otf)//1024}KB")
    except Exception as e:
        print(f"  [OTF] {e}"); otf=None
    svgs={}
    try:
        from fontTools.ttLib import TTFont
        from fontTools.pens.svgPathPen import SVGPathPen
        f=TTFont(ttf); cmap=f.getBestCmap(); gset=f.getGlyphSet()
        for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789':
            gn=cmap.get(ord(ch))
            if not gn: continue
            try:
                pen=SVGPathPen(gset); gset[gn].draw(pen)
                d2=pen.getCommands()
                if d2: svgs[ch]={'d':d2,'adv':gset[gn].width}
            except: pass
        f.close()
    except Exception as e: print(f"[v3] SVG error: {e}")
    # Store otf path in dna for app.py to pick up
    dna['_otf_path'] = otf
    return ttf, dna, svgs


if __name__=='__main__':
    import sys, json
    prompt  = sys.argv[1] if len(sys.argv)>1 else 'cute minimalist floral'
    name    = sys.argv[2] if len(sys.argv)>2 else 'VectrodV3'
    out_dir = sys.argv[3] if len(sys.argv)>3 else '/tmp/v3_out'
    api_key = os.environ.get('GEMINI_API_KEY','')
    ttf,dna,svgs = build_from_prompt(prompt,name,out_dir,api_key)
    print(f"\nDNA: {json.dumps(dna,indent=2)}")
    print(f"TTF: {ttf}  ({os.path.getsize(ttf)//1024}KB)")
    print(f"SVG glyphs: {len(svgs)}")
