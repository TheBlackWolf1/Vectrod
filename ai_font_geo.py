"""
ai_font_geo.py v3 — DISTINCT STYLES ENGINE
7 families: sans, serif, bold, rounded, mono, horror, display
Each produces genuinely different letterforms.
"""
import math
EM=700; BASE=560; CAP=100; MID=330; DESC=650

def analyze_prompt(prompt:str)->dict:
    p=prompt.lower()
    # Score each family — highest score wins
    scores={'sans':0,'serif':0,'bold':0,'rounded':0,'mono':0,'horror':0,'display':0}
    
    # SERIF signals
    for w in ['serif','classic','roman','elegant','luxury','fashion','magazine','wedding','vogue','editorial','refined','high contrast','thin stroke','newspaper']:
        if w in p: scores['serif']+=2
    
    # BOLD signals
    for w in ['bold','heavy','thick','black','strong','impact','powerful','aggressive','fat','chunky','wide stroke','condensed bold','massive']:
        if w in p: scores['bold']+=2
    
    # ROUNDED signals
    for w in ['round','bubble','cute','kawaii','soft','friendly','playful','fun','chubby','bubbly','pudgy','smooth','pill']:
        if w in p: scores['rounded']+=2
    
    # MONO/TECH signals — cyber goes here, NOT horror
    for w in ['mono','code','terminal','typewriter','tech','cyber','cyberpunk','digital','matrix','pixel','glitch','angular','electric','neon','sci-fi','futuristic','robotic','computer','hacker']:
        if w in p: scores['mono']+=2
    
    # HORROR signals — must be explicitly dark/scary
    for w in ['horror','creepy','scary','blood','halloween','drip','dripping','unsettl','irregular','spooky','scary','sinister','evil','gore','zombie']:
        if w in p: scores['horror']+=2
    
    # DISPLAY/RETRO signals
    for w in ['retro','70s','60s','80s','vintage','groove','funky','poster','display','grunge','western','slab','wood','old','antique','hand-lettered','wild west','cowboy','stamp']:
        if w in p: scores['display']+=2
    
    # THIN/MINIMAL
    for w in ['thin','light','hairline','delicate','fine','minimal','clean','swiss','geometric','modern sans']:
        if w in p: scores['sans']+=2; scores['sans']+=1  # boost sans

    # Gothic goes to display, not horror
    if 'gothic' in p: scores['display']+=2
    if 'dark' in p and 'web' in p: scores['mono']+=3  # dark web = cyber
    if 'dark' in p and ('horror' not in p and 'creepy' not in p): scores['display']+=1

    best = max(scores, key=scores.get)
    # Default stroke widths per family
    sw_map={'sans':50,'serif':28,'bold':115,'rounded':72,'mono':48,'horror':52,'display':88}
    s={'family':best,'sw':sw_map[best],'slant':0,'condensed':False,'wide':False}
    
    # Override stroke if explicit
    if any(w in p for w in ['thin','light','hairline','ultra-light']): s['sw']=max(18,s['sw']//3)
    elif any(w in p for w in ['ultra bold','extra bold','black','extrabold']): s['sw']=min(130,s['sw']+30)
    
    if any(w in p for w in ['condensed','narrow','slim','tall']): s['condensed']=True
    if any(w in p for w in ['wide','extended','expanded']): s['wide']=True
    return s

class GlyphDrawer:
    def __init__(self,style:dict):
        self.s=style; self.fam=style['family']
        adv=520
        if style.get('condensed'): adv=360
        if style.get('wide'):      adv=660
        if self.fam=='bold':       adv=580
        if self.fam=='mono':       adv=520
        drawers={'sans':SansDrawer,'serif':SerifDrawer,'bold':BoldDrawer,
                 'rounded':RoundedDrawer,'mono':MonoDrawer,'horror':HorrorDrawer,'display':DisplayDrawer}
        self._d=drawers.get(self.fam,SansDrawer)(style,adv)
    def draw(self,char:str)->tuple:
        return self._d.draw(char)

class BaseDrawer:
    def __init__(self,style,adv):
        self.sw=style['sw']; self.sw2=style['sw']//2; self.adv=adv; self.s=style
    @property
    def L(self): return 40
    @property
    def R(self): return self.adv-40
    @property
    def W(self): return self.R-self.L
    @property
    def CX(self): return self.L+self.W//2

    def rect(self,x,y,w,h,r=0):
        if r<=1: return f"M{x},{y} L{x+w},{y} L{x+w},{y+h} L{x},{y+h} Z"
        r=min(r,w//2,h//2)
        return (f"M{x+r},{y} L{x+w-r},{y} Q{x+w},{y} {x+w},{y+r} "
                f"L{x+w},{y+h-r} Q{x+w},{y+h} {x+w-r},{y+h} "
                f"L{x+r},{y+h} Q{x},{y+h} {x},{y+h-r} L{x},{y+r} Q{x},{y} {x+r},{y} Z")
    def vbar(self,cx,y1,y2,r=0): return self.rect(cx-self.sw2,y1,self.sw,y2-y1,r)
    def hbar(self,x1,x2,cy,r=0): return self.rect(x1,cy-self.sw2,x2-x1,self.sw,r)
    def diag(self,x1,y1,x2,y2):
        dx,dy=x2-x1,y2-y1; ln=math.hypot(dx,dy)
        if ln<1: return ""
        nx,ny=-dy/ln*self.sw2,dx/ln*self.sw2
        return (f"M{x1+nx:.1f},{y1+ny:.1f} L{x2+nx:.1f},{y2+ny:.1f} "
                f"L{x2-nx:.1f},{y2-ny:.1f} L{x1-nx:.1f},{y1-ny:.1f} Z")
    def oval(self,cx,cy,rx,ry):
        k=0.5523
        return (f"M{cx-rx},{cy} C{cx-rx},{cy-ry*k:.1f} {cx-rx*k:.1f},{cy-ry} {cx},{cy-ry} "
                f"C{cx+rx*k:.1f},{cy-ry} {cx+rx},{cy-ry*k:.1f} {cx+rx},{cy} "
                f"C{cx+rx},{cy+ry*k:.1f} {cx+rx*k:.1f},{cy+ry} {cx},{cy+ry} "
                f"C{cx-rx*k:.1f},{cy+ry} {cx-rx},{cy+ry*k:.1f} {cx-rx},{cy} Z")
    def ring(self,cx,cy,rx,ry): return self.oval(cx,cy,rx,ry)+" "+self.oval(cx,cy,max(5,rx-self.sw),max(5,ry-self.sw))
    def arc(self,cx,cy,rx,ry,a1,a2,sw=None):
        sw=sw or self.sw; steps=max(8,int(abs(a2-a1)/8))
        angles=[a1+(a2-a1)*i/steps for i in range(steps+1)]
        def pt(r,a): rad=math.radians(a); return cx+r*math.cos(rad),cy-r*math.sin(rad)
        op=[pt(rx,a) for a in angles]; ip=[pt(max(3,rx-sw),a) for a in reversed(angles)]
        pts=op+ip; d=f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
        for x,y in pts[1:]: d+=f" L{x:.1f},{y:.1f}"
        return d+" Z"
    def draw(self,char):
        MAP={'.':'dot',',':'comma','!':'excl','?':'quest','-':'dash','_':'under',
             '(':'lparen',')':'rparen','/':'slash','@':'at',' ':None}
        if char in MAP:
            if MAP[char] is None: return "",self.adv//2
            fn=getattr(self,f'c_{MAP[char]}',None)
            if fn: return fn(),self.adv
        fn=getattr(self,f'c_{char}',None)
        if fn: return fn(),self.adv
        return self.rect(self.L+self.sw,CAP+self.sw,self.W-self.sw*2,BASE-CAP-self.sw*2),self.adv

# ── SANS (geometric clean) ─────────────────────────────
class SansDrawer(BaseDrawer):
    def c_A(self):
        cx=self.CX
        return (self.diag(cx,CAP,self.L,BASE)+" "+self.diag(cx,CAP,self.R,BASE)+" "+
                self.hbar(self.L+self.W//4,self.R-self.W//4,(CAP+BASE)//2))
    def c_B(self):
        l=self.L; sw=self.sw; cx=l+sw; mid=(CAP+BASE)//2; w=self.W
        s=self.vbar(l+sw//2,CAP,BASE)
        tb=self.rect(cx,CAP,w*62//100,mid-CAP)
        ti=self.rect(cx+sw,CAP+sw,w*62//100-sw*2,mid-CAP-sw*2)
        bb=self.rect(cx,mid,w*72//100,BASE-mid)
        bi=self.rect(cx+sw,mid+sw,w*72//100-sw*2,BASE-mid-sw*2)
        return " ".join([s,tb,ti,bb,bi])
    def c_C(self):
        cx=self.CX;cy=(CAP+BASE)//2;rx=self.W//2;ry=(BASE-CAP)//2
        return self.arc(cx,cy,rx,ry,35,325)
    def c_D(self):
        l=self.L; sw=self.sw; cx=l+sw; cy=(CAP+BASE)//2; rx=self.W*82//100; ry=(BASE-CAP)//2
        s=self.vbar(l+sw//2,CAP,BASE)
        return s+" "+self.oval(cx,cy,rx,ry)+" "+self.oval(cx,cy,max(5,rx-sw),max(5,ry-sw))
    def c_E(self):
        s=self.vbar(self.L+self.sw//2,CAP,BASE)
        return (s+" "+self.hbar(self.L+self.sw,self.R,CAP+self.sw//2)+" "+
                self.hbar(self.L+self.sw,self.R-self.W//5,(CAP+BASE)//2)+" "+
                self.hbar(self.L+self.sw,self.R,BASE-self.sw//2))
    def c_F(self):
        s=self.vbar(self.L+self.sw//2,CAP,BASE)
        return (s+" "+self.hbar(self.L+self.sw,self.R,CAP+self.sw//2)+" "+
                self.hbar(self.L+self.sw,self.R-self.W//5,(CAP+BASE)//2))
    def c_G(self):
        cx=self.CX; cy=(CAP+BASE)//2; rx=self.W//2; ry=(BASE-CAP)//2
        return (self.arc(cx,cy,rx,ry,15,320)+" "+
                self.hbar(cx,self.R,cy+self.sw//2)+" "+self.vbar(self.R-self.sw//2,cy,cy+ry//2))
    def c_H(self):
        m=(CAP+BASE)//2
        return (self.vbar(self.L+self.sw//2,CAP,BASE)+" "+
                self.vbar(self.R-self.sw//2,CAP,BASE)+" "+self.hbar(self.L+self.sw,self.R-self.sw,m))
    def c_I(self): return self.vbar(self.CX,CAP,BASE)
    def c_J(self):
        cx=self.R-self.sw//2; bot=BASE-self.sw*3
        return (self.vbar(cx,CAP,bot)+" "+
                self.arc(self.L+self.sw*2,bot,(self.R-self.L-self.sw)//2,self.sw*3,0,-180))
    def c_K(self):
        mid=(MID+BASE)//2
        return (self.vbar(self.L+self.sw//2,CAP,BASE)+" "+
                self.diag(self.L+self.sw,mid,self.R,CAP)+" "+self.diag(self.L+self.sw,mid,self.R,BASE))
    def c_L(self):
        return self.vbar(self.L+self.sw//2,CAP,BASE)+" "+self.hbar(self.L+self.sw,self.R,BASE-self.sw//2)
    def c_M(self):
        cx=self.CX
        return (self.vbar(self.L+self.sw//2,CAP,BASE)+" "+self.vbar(self.R-self.sw//2,CAP,BASE)+" "+
                self.diag(self.L+self.sw,CAP,cx,(CAP+BASE)//2)+" "+self.diag(self.R-self.sw,CAP,cx,(CAP+BASE)//2))
    def c_N(self):
        return (self.vbar(self.L+self.sw//2,CAP,BASE)+" "+self.vbar(self.R-self.sw//2,CAP,BASE)+" "+
                self.diag(self.L+self.sw,CAP,self.R-self.sw,BASE))
    def c_O(self):
        cx=self.CX; cy=(CAP+BASE)//2; rx=self.W//2; ry=(BASE-CAP)//2
        return self.ring(cx,cy,rx,ry)
    def c_P(self):
        mid=(CAP+BASE)//2-self.sw; l=self.L; sw=self.sw; cx=l+sw
        s=self.vbar(l+sw//2,CAP,BASE)
        bulge=self.rect(cx,CAP,self.W*70//100,mid-CAP)
        hole=self.rect(cx+sw,CAP+sw,self.W*70//100-sw*2,mid-CAP-sw*2)
        return s+" "+bulge+" "+hole
    def c_Q(self):
        return self.c_O()+" "+self.diag(self.CX,MID+self.W//6,self.R,BASE+self.sw*2)
    def c_R(self):
        mid=(CAP+BASE)//2
        return self.c_P()+" "+self.diag(self.L+self.sw+self.sw//2,mid,self.R,BASE)
    def c_S(self):
        cx=self.CX; ry=(BASE-CAP)//2
        return (self.arc(cx,CAP+ry//2,self.W*42//100,ry//2,0,-210)+" "+
                self.arc(cx,BASE-ry//2,self.W*42//100,ry//2,180,-210))
    def c_T(self):
        return self.hbar(self.L,self.R,CAP+self.sw//2)+" "+self.vbar(self.CX,CAP+self.sw,BASE)
    def c_U(self):
        bot=BASE-self.sw*2
        return (self.vbar(self.L+self.sw//2,CAP,bot)+" "+
                self.arc(self.CX,bot,self.W//2,self.sw*2,0,-180)+" "+
                self.vbar(self.R-self.sw//2,CAP,bot))
    def c_V(self): return self.diag(self.L,CAP,self.CX,BASE)+" "+self.diag(self.R,CAP,self.CX,BASE)
    def c_W(self):
        q1=self.L+self.W//4; q3=self.L+3*self.W//4; mid=(CAP+BASE)//2+self.sw*2
        return (self.diag(self.L,CAP,q1,BASE)+" "+self.diag(self.R,CAP,q3,BASE)+" "+
                self.diag(q1,BASE,self.CX,mid)+" "+self.diag(q3,BASE,self.CX,mid))
    def c_X(self): return self.diag(self.L,CAP,self.R,BASE)+" "+self.diag(self.R,CAP,self.L,BASE)
    def c_Y(self):
        mid=(CAP+BASE)//2
        return (self.diag(self.L,CAP,self.CX,mid)+" "+self.diag(self.R,CAP,self.CX,mid)+" "+
                self.vbar(self.CX,mid,BASE))
    def c_Z(self):
        sw=self.sw
        return (self.hbar(self.L,self.R,CAP+sw//2)+" "+
                self.diag(self.R-sw,CAP+sw,self.L+sw,BASE-sw)+" "+
                self.hbar(self.L,self.R,BASE-sw//2))
    # lowercase
    def c_a(self):
        cx=self.CX; cy=(MID+BASE)//2; rx=self.W//2; ry=(BASE-MID)//2
        return self.ring(cx,cy,rx,ry)+" "+self.vbar(self.R-self.sw//2,MID+self.sw,BASE)
    def c_b(self):
        cx=self.L+self.sw+(self.W-self.sw)//2; cy=(MID+BASE)//2; rx=(self.W-self.sw)//2; ry=(BASE-MID)//2
        return self.vbar(self.L+self.sw//2,CAP,BASE)+" "+self.ring(cx,cy,rx,ry)
    def c_c(self):
        cx=self.CX; cy=(MID+BASE)//2; rx=self.W//2; ry=(BASE-MID)//2
        return self.arc(cx,cy,rx,ry,35,325)
    def c_d(self):
        cx=self.L+(self.W-self.sw)//2; cy=(MID+BASE)//2; rx=(self.W-self.sw)//2; ry=(BASE-MID)//2
        return self.ring(cx,cy,rx,ry)+" "+self.vbar(self.R-self.sw//2,CAP,BASE)
    def c_e(self):
        cx=self.CX; cy=(MID+BASE)//2; rx=self.W//2; ry=(BASE-MID)//2
        return self.arc(cx,cy,rx,ry,10,330)+" "+self.hbar(self.L+self.sw,self.R-self.sw//2,cy)
    def c_f(self):
        cx=self.CX
        return (self.vbar(cx,CAP+self.sw*2,BASE)+" "+
                self.arc(cx,CAP+self.sw*2,self.sw*3,self.sw*2,90,-90)+" "+
                self.hbar(self.L,cx+self.sw*3,MID))
    def c_g(self):
        cx=self.CX; cy=(MID+BASE)//2; rx=self.W//2; ry=(BASE-MID)//2
        return (self.ring(cx,cy,rx,ry)+" "+self.vbar(self.R-self.sw//2,MID,DESC-self.sw*2)+" "+
                self.arc(cx,DESC-self.sw*2,rx*9//10,self.sw*2,0,-180))
    def c_h(self):
        at=MID-self.sw
        return (self.vbar(self.L+self.sw//2,CAP,BASE)+" "+
                self.arc(self.CX,at,(self.W-self.sw)//2,self.sw*3,180,0)+" "+
                self.vbar(self.R-self.sw//2,at+self.sw*3,BASE))
    def c_i(self): return self.vbar(self.CX,MID,BASE)+" "+self.oval(self.CX,MID-self.sw*3,self.sw*.8,self.sw*.8)
    def c_j(self):
        cx=self.CX+self.sw
        return (self.vbar(cx,MID,DESC-self.sw*2)+" "+
                self.arc(cx-self.sw*3,DESC-self.sw*2,self.sw*3,self.sw*2,0,-180)+" "+
                self.oval(cx,MID-self.sw*3,self.sw*.8,self.sw*.8))
    def c_k(self):
        mid=(MID+BASE)//2
        return (self.vbar(self.L+self.sw//2,CAP,BASE)+" "+
                self.diag(self.L+self.sw,mid,self.R,MID)+" "+self.diag(self.L+self.sw,mid,self.R,BASE))
    def c_l(self): return self.vbar(self.CX,CAP,BASE)
    def c_m(self):
        q=self.CX
        return (self.vbar(self.L+self.sw//2,MID,BASE)+" "+self.vbar(self.R-self.sw//2,MID,BASE)+" "+
                self.vbar(q,MID+self.sw*2,BASE)+" "+
                self.arc((self.L+q)//2,MID,(q-self.L-self.sw)//2,self.sw*2,180,0)+" "+
                self.arc((q+self.R)//2,MID,(self.R-q-self.sw)//2,self.sw*2,180,0))
    def c_n(self):
        return (self.vbar(self.L+self.sw//2,MID,BASE)+" "+
                self.arc(self.CX,MID,(self.W-self.sw)//2,self.sw*2,180,0)+" "+
                self.vbar(self.R-self.sw//2,MID+self.sw*2,BASE))
    def c_o(self):
        cx=self.CX; cy=(MID+BASE)//2; rx=self.W//2; ry=(BASE-MID)//2
        return self.ring(cx,cy,rx,ry)
    def c_p(self):
        cx=self.L+self.sw+(self.W-self.sw)//2; cy=(MID+BASE)//2; rx=(self.W-self.sw)//2; ry=(BASE-MID)//2
        return self.vbar(self.L+self.sw//2,MID,DESC)+" "+self.ring(cx,cy,rx,ry)
    def c_q(self):
        cx=self.L+(self.W-self.sw)//2; cy=(MID+BASE)//2; rx=(self.W-self.sw)//2; ry=(BASE-MID)//2
        return self.ring(cx,cy,rx,ry)+" "+self.vbar(self.R-self.sw//2,MID,DESC)
    def c_r(self):
        s=self.vbar(self.L+self.sw//2,MID,BASE); br=self.L+self.W*62//100
        bump=(f"M{self.L+self.sw},{MID} L{br},{MID} C{self.R+self.sw},{MID} {self.R+self.sw},{MID+self.sw*5} {br},{MID+self.sw*5} L{self.L+self.sw},{MID+self.sw*5} Z "
              f"M{self.L+self.sw*2},{MID+self.sw} L{br},{MID+self.sw} C{self.R-self.sw//2},{MID+self.sw} {self.R-self.sw//2},{MID+self.sw*4} {br},{MID+self.sw*4} L{self.L+self.sw*2},{MID+self.sw*4} Z")
        return s+" "+bump
    def c_s(self):
        cx=self.CX; ry=(BASE-MID)//2
        return (self.arc(cx,MID+ry//2,self.W*4//10,ry//2,0,-210)+" "+
                self.arc(cx,BASE-ry//2,self.W*4//10,ry//2,180,-210))
    def c_t(self):
        cx=self.CX
        return (self.vbar(cx,CAP+self.sw*3,BASE)+" "+self.hbar(self.L+self.sw,self.R-self.sw,MID)+" "+
                self.arc(cx,CAP+self.sw*3,self.sw*2,self.sw*3,90,-90))
    def c_u(self):
        bot=BASE-self.sw*2
        return (self.vbar(self.L+self.sw//2,MID,bot)+" "+
                self.arc(self.CX,bot,self.W//2,self.sw*2,0,-180)+" "+
                self.vbar(self.R-self.sw//2,MID,BASE))
    def c_v(self): return self.diag(self.L,MID,self.CX,BASE)+" "+self.diag(self.R,MID,self.CX,BASE)
    def c_w(self):
        q1=self.L+self.W//4; q3=self.L+3*self.W//4; mid=(MID+BASE)//2
        return (self.diag(self.L,MID,q1,BASE)+" "+self.diag(self.R,MID,q3,BASE)+" "+
                self.diag(q1,BASE,self.CX,mid)+" "+self.diag(q3,BASE,self.CX,mid))
    def c_x(self): return self.diag(self.L,MID,self.R,BASE)+" "+self.diag(self.R,MID,self.L,BASE)
    def c_y(self):
        mid=(MID+BASE)//2
        return self.diag(self.L,MID,self.CX,mid)+" "+self.diag(self.R,MID,self.L,DESC)
    def c_z(self):
        sw=self.sw
        return (self.hbar(self.L,self.R,MID+sw//2)+" "+
                self.diag(self.R-sw,MID+sw,self.L+sw,BASE-sw)+" "+
                self.hbar(self.L,self.R,BASE-sw//2))
    def c_0(self):
        cx=self.CX; cy=(CAP+BASE)//2; rx=self.W//2; ry=(BASE-CAP)//2
        return self.ring(cx,cy,rx,ry)+" "+self.diag(cx-rx//2,cy-ry//3,cx+rx//2,cy+ry//3)
    def c_1(self):
        cx=self.CX
        return (self.vbar(cx,CAP,BASE)+" "+self.diag(self.L+self.sw,CAP+self.sw*4,cx,CAP)+" "+
                self.hbar(self.L,self.R,BASE-self.sw//2))
    def c_2(self):
        cx=self.CX; top=CAP+self.sw*3
        return (self.arc(cx,top,self.W//2,self.sw*3,0,-210)+" "+
                self.diag(self.R-self.sw,CAP+self.sw*5,self.L+self.sw,BASE-self.sw)+" "+
                self.hbar(self.L,self.R,BASE-self.sw//2))
    def c_3(self):
        cx=self.CX
        return (self.arc(cx,CAP+self.sw*3,self.W*45//100,self.sw*3,200,-260)+" "+
                self.arc(cx,BASE-self.sw*3,self.W*45//100,self.sw*3,160,-300))
    def c_4(self):
        mid=(CAP+BASE)*55//100
        return (self.diag(self.R-self.sw*3,CAP,self.L,mid)+" "+
                self.hbar(self.L,self.R,mid)+" "+self.vbar(self.R-self.sw*2,CAP,BASE))
    def c_5(self):
        cx=self.CX; mid=(CAP+BASE)//2
        return (self.hbar(self.L,self.R,CAP+self.sw//2)+" "+
                self.vbar(self.L+self.sw//2,CAP+self.sw,mid)+" "+
                self.arc(cx,BASE-self.sw*3,self.W*45//100,self.sw*3,160,-300))
    def c_6(self):
        cx=self.CX; cy=(MID+BASE)//2; rx=self.W//2; ry=(BASE-MID)//2
        return (self.ring(cx,cy,rx,ry)+" "+
                self.arc(cx,CAP+ry,rx*8//10,ry,90,-90)+" "+
                self.vbar(self.L+self.sw//2,CAP+ry,cy-ry))
    def c_7(self):
        return self.hbar(self.L,self.R,CAP+self.sw//2)+" "+self.diag(self.R-self.sw,CAP+self.sw,self.L+self.sw,BASE)
    def c_8(self):
        cx=self.CX; mid=(CAP+BASE)//2
        return (self.ring(cx,(CAP+mid)//2,self.W*43//100,(mid-CAP)//2)+" "+
                self.ring(cx,(mid+BASE)//2,self.W//2,(BASE-mid)//2))
    def c_9(self):
        cx=self.CX; cy=(CAP+MID)//2; rx=self.W//2; ry=(MID-CAP)//2
        return self.ring(cx,cy,rx,ry)+" "+self.vbar(self.R-self.sw//2,cy,BASE)
    def c_dot(self): return self.oval(self.CX,BASE-self.sw,self.sw,self.sw)
    def c_comma(self):
        cx=self.CX
        return self.oval(cx,BASE-self.sw,self.sw,self.sw)+" "+self.diag(cx-self.sw//2,BASE,cx,BASE+self.sw*2)
    def c_excl(self): return self.vbar(self.CX,CAP,BASE-self.sw*3)+" "+self.oval(self.CX,BASE-self.sw,self.sw,self.sw)
    def c_quest(self):
        cx=self.CX; top=CAP+self.sw*3
        return (self.arc(cx,top,self.W//2,self.sw*3,0,-200)+" "+
                self.vbar(cx,top+self.sw*4,BASE-self.sw*3)+" "+
                self.oval(cx,BASE-self.sw,self.sw,self.sw))
    def c_dash(self): return self.hbar(self.L,self.R,(CAP+BASE)//2)
    def c_under(self): return self.hbar(self.L,self.R,BASE+self.sw//2)
    def c_lparen(self): return self.arc(self.R,(CAP+BASE)//2,self.W*6//10,(BASE-CAP)//2,120,-120)
    def c_rparen(self): return self.arc(self.L,(CAP+BASE)//2,self.W*6//10,(BASE-CAP)//2,60,300)
    def c_slash(self): return self.diag(self.R-self.sw,CAP,self.L,BASE)
    def c_at(self):
        cx=self.CX; cy=(CAP+BASE)//2; rx=self.W//2; ry=(BASE-CAP)//2
        return self.ring(cx,cy,rx,ry)+" "+self.ring(cx+self.sw,cy,rx//3,ry*4//10)


# ── SERIF — High contrast, thin/thick strokes, wedge serifs ─
class SerifDrawer(SansDrawer):
    def vbar(self,cx,y1,y2,r=0):
        sw=self.sw*2; return self.rect(cx-sw//2,y1,sw,y2-y1)
    def hbar(self,x1,x2,cy,r=0):
        sw=max(8,self.sw//3); return self.rect(x1,cy-sw//2,x2-x1,sw)
    def _slab(self,cx,y):
        w=self.sw*4; h=max(8,self.sw//2)
        return self.rect(cx-w//2,y-h//2,w,h)
    def c_A(self):
        cx=self.CX; sw2=self.sw*2; thin=max(8,self.sw//3)
        ll=self.diag(cx,CAP,self.L,BASE); rl=self.diag(cx,CAP,self.R,BASE)
        bar=self.rect(self.L+self.W//4,(CAP+BASE)//2-thin//2,self.W//2,thin)
        return ll+" "+rl+" "+bar+" "+self._slab(self.L,BASE)+" "+self._slab(self.R,BASE)+" "+self._slab(cx,CAP)
    def c_I(self):
        cx=self.CX; sw2=self.sw*2
        return (self.rect(cx-sw2//2,CAP,sw2,BASE-CAP)+" "+
                self.rect(cx-sw2*3//2,CAP,sw2*3,max(10,self.sw//3)*2)+" "+
                self.rect(cx-sw2*3//2,BASE-max(10,self.sw//3)*2,sw2*3,max(10,self.sw//3)*2))
    def c_T(self):
        thin=max(8,self.sw//3); cx=self.CX; sw2=self.sw*2
        return (self.rect(self.L,CAP,self.W,thin*2)+" "+
                self.rect(cx-sw2//2,CAP,sw2,BASE-CAP)+" "+
                self._slab(self.L,CAP)+" "+self._slab(self.R,CAP)+" "+self._slab(cx,BASE))
    def c_H(self):
        sw2=self.sw*2; thin=max(8,self.sw//3)
        return (self.rect(self.L,CAP,sw2,BASE-CAP)+" "+
                self.rect(self.R-sw2,CAP,sw2,BASE-CAP)+" "+
                self.rect(self.L+sw2,(CAP+BASE)//2-thin//2,self.W-sw2*2,thin)+" "+
                self._slab(self.L,CAP)+" "+self._slab(self.L,BASE)+" "+
                self._slab(self.R,CAP)+" "+self._slab(self.R,BASE))


# ── BOLD — Ultra heavy, condensed ─────────────────────
class BoldDrawer(SansDrawer):
    def c_O(self):
        cx=self.CX; cy=(CAP+BASE)//2; rx=self.W//2; ry=(BASE-CAP)//2
        return self.oval(cx,cy,rx,ry)+" "+self.oval(cx,cy,max(10,rx-self.sw),max(10,ry-self.sw))
    def c_C(self):
        cx=self.CX; cy=(CAP+BASE)//2; rx=self.W//2; ry=(BASE-CAP)//2
        return self.arc(cx,cy,rx,ry,22,338)
    def c_S(self):
        cx=self.CX; ry=(BASE-CAP)//2
        return (self.arc(cx,CAP+ry//2,self.W*48//100,ry//2,0,-225,self.sw)+" "+
                self.arc(cx,BASE-ry//2,self.W*48//100,ry//2,180,-225,self.sw))
    def c_A(self):
        cx=self.CX; sw=self.sw
        return (self.diag(cx,CAP-sw//4,self.L-sw//4,BASE)+" "+
                self.diag(cx,CAP-sw//4,self.R+sw//4,BASE)+" "+
                self.hbar(self.L+self.W//6,self.R-self.W//6,(CAP+BASE)//2))


# ── ROUNDED — Big radii, soft and bubbly ─────────────
class RoundedDrawer(SansDrawer):
    def rect(self,x,y,w,h,r=0):
        r=min(max(self.sw//3,8),w//2,h//2)
        return super().rect(x,y,w,h,r)
    def vbar(self,cx,y1,y2,r=0):
        r=self.sw//2
        return self.rect(cx-self.sw2,y1,self.sw,y2-y1,r)
    def hbar(self,x1,x2,cy,r=0):
        r=self.sw//2
        return self.rect(x1,cy-self.sw2,x2-x1,self.sw,r)
    def c_O(self):
        cx=self.CX; cy=(CAP+BASE)//2; rx=self.W//2; ry=(BASE-CAP)//2
        return self.ring(cx,cy,rx,ry)
    def c_o(self):
        cx=self.CX; cy=(MID+BASE)//2; rx=self.W//2; ry=(BASE-MID)//2
        return self.ring(cx,cy,rx,ry)
    def c_a(self):
        cx=self.CX; cy=(MID+BASE)//2; rx=self.W//2; ry=(BASE-MID)//2
        return self.ring(cx,cy,rx,ry)+" "+self.vbar(self.R-self.sw//2,MID+self.sw,BASE)


# ── MONO — Square, no curves, terminal/pixel ─────────
class MonoDrawer(SansDrawer):
    def oval(self,cx,cy,rx,ry):
        pts=[(cx+rx*math.cos(math.radians(a)),cy+ry*math.sin(math.radians(a))) for a in range(0,360,45)]
        d=f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
        for x,y in pts[1:]: d+=f" L{x:.1f},{y:.1f}"
        return d+" Z"
    def ring(self,cx,cy,rx,ry):
        return self.oval(cx,cy,rx,ry)+" "+self.oval(cx,cy,max(5,rx-self.sw),max(5,ry-self.sw))
    def arc(self,cx,cy,rx,ry,a1,a2,sw=None):
        sw=sw or self.sw; steps=max(4,int(abs(a2-a1)/22))
        angles=[a1+(a2-a1)*i/steps for i in range(steps+1)]
        def pt(r,a): rad=math.radians(a); return cx+r*math.cos(rad),cy-r*math.sin(rad)
        op=[pt(rx,a) for a in angles]; ip=[pt(max(3,rx-sw),a) for a in reversed(angles)]
        pts=op+ip; d=f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
        for x,y in pts[1:]: d+=f" L{x:.1f},{y:.1f}"
        return d+" Z"
    def c_O(self):
        l=self.L; r=self.R; sw=self.sw; c=sw*2
        return (f"M{l+c},{CAP} L{r-c},{CAP} L{r},{CAP+c} L{r},{BASE-c} L{r-c},{BASE} L{l+c},{BASE} L{l},{BASE-c} L{l},{CAP+c} Z "
                f"M{l+c+sw},{CAP+sw} L{r-c-sw},{CAP+sw} L{r-sw},{CAP+c+sw} L{r-sw},{BASE-c-sw} L{r-c-sw},{BASE-sw} L{l+c+sw},{BASE-sw} L{l+sw},{BASE-c-sw} L{l+sw},{CAP+c+sw} Z")
    def c_o(self):
        l=self.L; r=self.R; sw=self.sw; c=sw; t=MID; b=BASE
        return (f"M{l+c},{t} L{r-c},{t} L{r},{t+c} L{r},{b-c} L{r-c},{b} L{l+c},{b} L{l},{b-c} L{l},{t+c} Z "
                f"M{l+c+sw},{t+sw} L{r-c-sw},{t+sw} L{r-sw},{t+c+sw} L{r-sw},{b-c-sw} L{r-c-sw},{b-sw} L{l+c+sw},{b-sw} L{l+sw},{b-c-sw} L{l+sw},{t+c+sw} Z")
    def c_C(self):
        sw=self.sw
        return (self.hbar(self.L,self.R,CAP+sw//2)+" "+self.hbar(self.L,self.R,BASE-sw//2)+" "+
                self.vbar(self.L+sw//2,CAP+sw,BASE-sw))
    def c_S(self):
        sw=self.sw; mid=(CAP+BASE)//2
        return (self.hbar(self.L,self.R,CAP+sw//2)+" "+self.hbar(self.L,self.R,mid)+" "+
                self.hbar(self.L,self.R,BASE-sw//2)+" "+
                self.vbar(self.L+sw//2,CAP+sw,mid)+" "+self.vbar(self.R-sw//2,mid,BASE-sw))


# ── HORROR — Jagged, dripping, irregular ──────────────
class HorrorDrawer(SansDrawer):
    def vbar(self,cx,y1,y2,r=0):
        sw=self.sw; w=sw; j=sw//3; x=cx-sw//2
        pts=[(x,y1),(x+w,y1+j),(x+w,y2-j*2),(x+w+j,y2),(x,y2+j),(x-j,y2-j),(x,y1+j*2)]
        d=f"M{pts[0][0]},{pts[0][1]}"
        for px,py in pts[1:]: d+=f" L{px},{py}"
        return d+" Z"
    def hbar(self,x1,x2,cy,r=0):
        sw=self.sw; j=sw//4; y=cy-sw//2; h=sw
        pts=[(x1,y+j),(x1+j,y),(x2-j,y+j//2),(x2,y+h//2),(x2-j,y+h),(x1,y+h-j//2)]
        d=f"M{pts[0][0]},{pts[0][1]}"
        for px,py in pts[1:]: d+=f" L{px},{py}"
        return d+" Z"
    def oval(self,cx,cy,rx,ry):
        pts=[]
        for i,a in enumerate(range(0,360,20)):
            rad=math.radians(a)
            w=1.0+(0.1 if i%3==0 else -0.07 if i%3==1 else 0.04)
            pts.append((cx+rx*w*math.cos(rad),cy+ry*w*math.sin(rad)))
        d=f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
        for x,y in pts[1:]: d+=f" L{x:.1f},{y:.1f}"
        return d+" Z"
    def ring(self,cx,cy,rx,ry): return self.oval(cx,cy,rx,ry)+" "+self.oval(cx,cy,max(4,rx-self.sw),max(4,ry-self.sw))
    def _drip(self,x,y):
        w=self.sw//2
        return (f"M{x-w},{y} L{x+w},{y} L{x+w//2},{y+self.sw*2} "
                f"L{x+w//4},{y+self.sw*3} L{x},{y+self.sw*4} L{x-w//4},{y+self.sw*3} L{x-w//2},{y+self.sw*2} Z")
    def c_O(self): return super().c_O()+" "+self._drip(self.CX+self.sw,BASE)
    def c_B(self): return super().c_B()+" "+self._drip(self.CX,BASE-self.sw)
    def c_A(self):
        cx=self.CX; j=self.sw//3
        return (f"M{cx},{CAP-j} L{cx+j},{CAP+j} L{self.R+j},{BASE+j} "
                f"L{self.R-self.sw},{BASE} L{cx+self.sw},{(CAP+BASE)//2+j} "
                f"L{cx-self.sw},{(CAP+BASE)//2} L{self.L+self.sw},{BASE} "
                f"L{self.L-j},{BASE+j} Z "
                f"M{self.L+self.W//4},{(CAP+BASE)//2-j} "
                f"L{self.R-self.W//4+j},{(CAP+BASE)//2+j} "
                f"L{self.R-self.W//4+j},{(CAP+BASE)//2+self.sw+j} "
                f"L{self.L+self.W//4-j},{(CAP+BASE)//2+self.sw} Z")


# ── DISPLAY — Slab serif, retro poster ────────────────
class DisplayDrawer(SansDrawer):
    def _slab(self,cx,y,w=None):
        w=w or self.sw*3; h=self.sw*3//4
        return self.rect(cx-w//2,y-h//2,w,h)
    def vbar(self,cx,y1,y2,r=0):
        return super().vbar(cx,y1,y2,r)+" "+self._slab(cx,y1)+" "+self._slab(cx,y2)
    def c_A(self):
        cx=self.CX; sw=self.sw
        ll=self.diag(cx,CAP,self.L,BASE); rl=self.diag(cx,CAP,self.R,BASE)
        bar=self.hbar(self.L+self.W//5,self.R-self.W//5,(CAP+BASE)//2+sw)
        return (ll+" "+rl+" "+bar+" "+
                self._slab(self.L,BASE,sw*4)+" "+self._slab(self.R,BASE,sw*4)+" "+self._slab(cx,CAP,sw*2))
    def c_I(self):
        cx=self.CX; sw=self.sw
        return (self.rect(cx-sw//2,CAP,sw,BASE-CAP)+" "+
                self.rect(self.L,CAP,self.W,sw)+" "+self.rect(self.L,BASE-sw,self.W,sw))
    def c_T(self):
        sw=self.sw; cx=self.CX
        return (self.rect(self.L,CAP,self.W,sw)+" "+
                self.rect(cx-sw//2,CAP,sw,BASE-CAP)+" "+
                self._slab(self.L,CAP,sw*3)+" "+self._slab(self.R,CAP,sw*3)+" "+self._slab(cx,BASE,sw*3))
    def c_H(self):
        sw=self.sw
        return (self.rect(self.L,CAP,sw,BASE-CAP)+" "+
                self.rect(self.R-sw,CAP,sw,BASE-CAP)+" "+
                self.hbar(self.L+sw,self.R-sw,(CAP+BASE)//2)+" "+
                self._slab(self.L,CAP,sw*3)+" "+self._slab(self.L,BASE,sw*3)+" "+
                self._slab(self.R,CAP,sw*3)+" "+self._slab(self.R,BASE,sw*3))
