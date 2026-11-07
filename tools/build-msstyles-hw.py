#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build two visual styles from Wine's aero.msstyles: Luna (Windows XP look) and Noir (Royale Noir look).

W176. Original work, not Microsoft's files: aero.msstyles (LGPL, dlls/aero.msstyles of the pinned
Wine) is copied to an overlay per style. Every bitmap is first recoloured to the style's palette;
the parts Wine draws with a theme and that set the look are then drawn here, state by state, at
Aero's sizes and layouts (Aero's INI keeps working): push buttons, check boxes, radio buttons,
scroll bars, tabs, headers, group boxes, edit and combo box borders. The INI gets the style's
name and the XP / Royale Noir system colours ([SysMetrics], which uxtheme applies when the style
is chosen: title bars, menus, dialog faces). Wine draws title bars, frames and caption buttons
itself, with those colours, not with the theme. Each style is compiled with the commands the
pinned build uses for aero.msstyles (from `make -n`), with the overlay as source.
Output: out/msstyles-hw/<style>/<style>.msstyles and manifest.json.
"""
import hashlib,json,pathlib,re,shlex,shutil,struct,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
AERO=SOURCE/'dlls/aero.msstyles';work=ROOT/'build/msstyles-hw';out=ROOT/'out/msstyles-hw'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')

# ---------------------------------------------------------------- bitmaps (24/32-bit BI_RGB)
def read_bmp(path):
    d=path.read_bytes();off,=struct.unpack_from('<I',d,10);w,h=struct.unpack_from('<ii',d,18)
    bpp,=struct.unpack_from('<H',d,28);comp,=struct.unpack_from('<I',d,30)
    if comp not in (0,3) or bpp not in (24,32):raise SystemExit('%s: unexpected bitmap format'%path)
    stride=((w*bpp//8)+3)&~3;H=abs(h);px=[]
    for y in range(H):
        row=off+(H-1-y if h>0 else y)*stride
        for x in range(w):
            at=row+x*bpp//8;px.append([d[at+2],d[at+1],d[at],d[at+3] if bpp==32 else 255])
    return {'w':w,'h':H,'bpp':bpp,'px':px,'header':d[:off],'topdown':h<0}
def write_bmp(path,img):
    w,H,bpp=img['w'],img['h'],img['bpp'];stride=((w*bpp//8)+3)&~3;rows=[]
    for y in range(H):
        r=bytearray()
        for x in range(w):
            R,G,B,A=(int(round(min(255,max(0,v)))) for v in img['px'][y*w+x]);r+=bytes((B,G,R))+(bytes((A,)) if bpp==32 else b'')
        rows.append(bytes(r+bytes(stride-len(r))))
    if not img['topdown']:rows.reverse()
    path.write_bytes(img['header']+b''.join(rows))

# ---------------------------------------------------------------- colour helpers
def mix(a,b,t):return [a[i]+(b[i]-a[i])*t for i in range(3)]
def lum(c):return (0.299*c[0]+0.587*c[1]+0.114*c[2])/255
def chroma(c):return (max(c[:3])-min(c[:3]))/255
def vgrad(stops,t):
    """colour at t in [0,1] along [(t0,colour),...]"""
    t=min(1,max(0,t))
    for (t0,c0),(t1,c1) in zip(stops,stops[1:]):
        if t<=t1:return mix(c0,c1,(t-t0)/(t1-t0) if t1>t0 else 0)
    return list(stops[-1][1])

# ---------------------------------------------------------------- drawing on one frame
class Frame:
    """a w x h state image; pixels are RGBA lists, alpha 0 = see-through"""
    def __init__(self,w,h,bg=None):
        self.w,self.h=w,h;self.px=[list(bg)+[255] if bg else [0,0,0,0] for _ in range(w*h)]
    def blend(self,x,y,c,a):
        if not (0<=x<self.w and 0<=y<self.h) or a<=0:return
        p=self.px[y*self.w+x];a=min(1,a);pa=p[3]/255;na=a+pa*(1-a)
        if na<=0:return
        for i in range(3):p[i]=(c[i]*a+p[i]*pa*(1-a))/na
        p[3]=na*255
    def shape(self,inside,colour_at,ss=4):
        """fill where inside(x,y) holds (pixel coordinates, sampled ss x ss), colour_at(x,y)"""
        for y in range(self.h):
            for x in range(self.w):
                n=sum(inside(x+(i+.5)/ss,y+(j+.5)/ss) for i in range(ss) for j in range(ss))
                if n:self.blend(x,y,colour_at(x,y),n/(ss*ss))
def in_rrect(x0,y0,x1,y1,r):
    def inside(x,y):
        if not (x0<=x<=x1 and y0<=y<=y1):return False
        cx=min(max(x,x0+r),x1-r);cy=min(max(y,y0+r),y1-r)
        return (x-cx)**2+(y-cy)**2<=r*r
    return inside
def rrect(f,x0,y0,x1,y1,r,colour_at):f.shape(in_rrect(x0,y0,x1,y1,r),colour_at)
def ring(f,x0,y0,x1,y1,r,width,colour_at):
    outer=in_rrect(x0,y0,x1,y1,r);inner=in_rrect(x0+width,y0+width,x1-width,y1-width,max(0,r-width))
    f.shape(lambda x,y:outer(x,y) and not inner(x,y),colour_at)
def circle(f,cx,cy,r,colour_at):f.shape(lambda x,y:(x-cx)**2+(y-cy)**2<=r*r,colour_at)
def solid(c):return lambda x,y:c
def line(f,x0,y0,x1,y1,width,c):
    """anti-aliased thick segment"""
    def inside(x,y):
        dx,dy=x1-x0,y1-y0;t=max(0,min(1,((x-x0)*dx+(y-y0)*dy)/(dx*dx+dy*dy)))
        return (x-x0-t*dx)**2+(y-y0-t*dy)**2<=(width/2)**2
    f.shape(inside,solid(c))
def stack(frames,like):
    """frames stacked vertically into an image with like's header and depth"""
    w=frames[0].w;img={'w':w,'h':sum(f.h for f in frames),'bpp':like['bpp'],'header':like['header'],'topdown':like['topdown'],'px':[]}
    for f in frames:
        for p in f.px:
            if like['bpp']==24:
                bg=like['bg'];a=p[3]/255;img['px'].append([p[i]*a+bg[i]*(1-a) for i in range(3)]+[255])
            else:img['px'].append(list(p))
    if img['h']!=like['h'] or w!=like['w']:raise SystemExit('frame layout differs from Aero: %dx%d drawn, %dx%d in Aero'%(w,img['h'],like['w'],like['h']))
    return img

# ---------------------------------------------------------------- the two styles
LUNA={
 'name':'Luna','tooltip':'Estilo Luna (aspecto de Windows XP)','color':'Azul',
 'face':(236,233,216),'window':(255,255,255),'text':(0,0,0),
 'sys':{'Scrollbar':(212,208,200),'Background':(0,78,152),'ActiveCaption':(0,84,227),'InactiveCaption':(122,150,223),
        'Menu':(255,255,255),'Window':(255,255,255),'WindowFrame':(0,0,0),'MenuText':(0,0,0),'WindowText':(0,0,0),
        'CaptionText':(255,255,255),'ActiveBorder':(0,84,227),'InactiveBorder':(122,150,223),'AppWorkSpace':(128,128,128),
        'Highlight':(49,106,197),'HighlightText':(255,255,255),'BtnFace':(236,233,216),'BtnShadow':(172,168,153),
        'GrayText':(172,168,153),'BtnText':(0,0,0),'InactiveCaptionText':(216,228,248),'BtnHighlight':(255,255,255),
        'DkShadow3d':(113,111,100),'Light3d':(241,239,226),'InfoText':(0,0,0),'InfoBk':(255,255,225),
        # W179: solid title bars and borders in XP's blue (the user: "pleno"); Wine draws both itself
        'ButtonAlternateFace':(181,181,181),'HotTracking':(0,0,128),'GradientActiveCaption':(0,84,227),
        'GradientInactiveCaption':(122,150,223),'MenuHilight':(49,106,197),'MenuBar':(236,233,216)},
 # W179: shell parts drawn by explorer from the style (taskbar, Start, taskbar buttons)
 'taskbar':[(0,(92,142,240)),(.08,(61,129,243)),(.2,(36,94,220)),(.85,(30,80,200)),(1,(25,65,165))],'taskbar_fill':(36,94,220),
 'start':[(0,(150,220,140)),(.1,(99,191,90)),(.5,(58,152,52)),(1,(40,127,36))],
 'start_hot':[(0,(170,235,160)),(.1,(120,210,110)),(.5,(72,170,66)),(1,(50,140,46))],
 'start_pressed':[(0,(30,100,28)),(.5,(44,118,40)),(1,(56,140,52))],
 'band':[(0,(115,165,250)),(.15,(70,135,240)),(1,(42,104,226))],'band_border':(24,64,180),
 'band_hot':[(0,(140,185,255)),(.15,(95,155,250)),(1,(60,122,236))],
 'band_checked':[(0,(24,62,170)),(.2,(30,76,190)),(1,(36,88,206))],
 # push button
 'btn_border':(0,60,116),'btn_face':[(0,(255,255,255)),(.75,(240,240,234)),(.9,(226,223,214)),(1,(214,208,197))],
 'btn_hot':[(0,(255,240,207)),(1,(248,179,48))],'btn_pressed':[(0,(209,204,193)),(.2,(226,226,218)),(1,(242,242,236))],
 'btn_dis_border':(201,199,186),'btn_dis_face':(245,244,234),'btn_default':[(0,(206,231,255)),(1,(105,130,238))],
 # check / radio
 'chk_border':(28,81,128),'chk_face':[(0,(220,220,215)),(1,(255,255,255))],'chk_pressed':[(0,(176,176,167)),(1,(227,226,218))],
 'chk_hot':(248,179,48),'chk_hot_in':(255,240,207),'chk_dis':(202,200,187),'mark':(33,161,33),'mark_hi':(85,213,81),
 # scroll bars
 'sb_border':(149,175,230),'sb_face':[(0,(214,226,252)),(1,(184,204,250))],'sb_hot':[(0,(226,236,255)),(1,(200,218,255))],
 'sb_pressed':[(0,(176,198,242)),(1,(158,186,238))],'sb_dis':(242,241,236),'sb_dis_border':(220,219,213),
 'sb_grip_light':(238,244,254),'sb_grip_dark':(140,176,248),'track':(243,241,236),'track_pressed':(229,227,218),
 'glyph':(77,97,133),'glyph_dis':(201,199,186),
 # tabs, headers, borders
 'tab_border':(145,155,156),'tab_face':[(0,(255,255,255)),(1,(236,235,230))],'tab_hot':(255,200,60),'tab_sel_top':(230,139,44),
 'pane':(252,252,254),'header_face':(235,234,219),'header_lines':[(226,222,205),(214,210,194),(203,199,184)],'header_hot':(248,169,0),
 'edit_border':(127,157,185),'group_border':(208,208,191),
 'progress':{'ProgressChunkSize':'8','ProgressSpaceSize':'2','fill':(49,211,49),'border':(104,104,104),'bar':(255,255,255)},
 'accent':(49,106,197),
}
NOIR={
 'name':'Noir','tooltip':'Estilo Noir (aspecto de Royale Noir)','color':'Noir',
 'face':(45,45,48),'window':(30,30,32),'text':(235,235,235),
 'sys':{'Scrollbar':(30,30,30),'Background':(0,0,0),'ActiveCaption':(232,112,24),'InactiveCaption':(58,58,60),
        'Menu':(38,38,40),'Window':(30,30,32),'WindowFrame':(10,10,10),'MenuText':(235,235,235),'WindowText':(235,235,235),
        'CaptionText':(255,255,255),'ActiveBorder':(232,112,24),'InactiveBorder':(58,58,60),'AppWorkSpace':(25,25,25),
        'Highlight':(85,105,135),'HighlightText':(255,255,255),'BtnFace':(45,45,48),'BtnShadow':(25,25,28),
        'GrayText':(130,130,130),'BtnText':(235,235,235),'InactiveCaptionText':(160,160,160),'BtnHighlight':(90,90,95),
        'DkShadow3d':(10,10,10),'Light3d':(70,70,74),'InfoText':(235,235,235),'InfoBk':(50,50,54),
        # W179: solid title bars and borders in orange (the user), dark grey when inactive
        'ButtonAlternateFace':(45,45,48),'HotTracking':(150,170,200),'GradientActiveCaption':(232,112,24),
        'GradientInactiveCaption':(58,58,60),'MenuHilight':(85,105,135),'MenuBar':(38,38,40)},
 'taskbar':[(0,(96,96,100)),(.06,(62,62,66)),(.5,(30,30,32)),(1,(8,8,8))],'taskbar_fill':(30,30,32),
 'start':[(0,(255,200,140)),(.1,(255,165,70)),(.5,(232,112,24)),(1,(180,80,10))],
 'start_hot':[(0,(255,215,165)),(.1,(255,180,95)),(.5,(245,130,40)),(1,(200,95,20))],
 'start_pressed':[(0,(150,65,5)),(.5,(190,88,14)),(1,(215,100,20))],
 'band':[(0,(84,84,88)),(.15,(58,58,62)),(1,(34,34,36))],'band_border':(110,110,114),
 'band_hot':[(0,(104,104,108)),(.15,(76,76,80)),(1,(48,48,50))],
 'band_checked':[(0,(20,20,22)),(.2,(30,30,32)),(1,(44,44,46))],
 'btn_border':(8,8,8),'btn_face':[(0,(108,108,110)),(.48,(66,66,68)),(.52,(38,38,40)),(1,(52,52,54))],
 'btn_hot':[(0,(170,170,175)),(1,(110,110,115))],'btn_pressed':[(0,(20,20,20)),(1,(44,44,46))],
 'btn_dis_border':(36,36,38),'btn_dis_face':(52,52,54),'btn_default':[(0,(140,160,190)),(1,(85,105,135))],
 'chk_border':(140,140,145),'chk_face':[(0,(24,24,26)),(1,(58,58,62))],'chk_pressed':[(0,(14,14,14)),(1,(34,34,36))],
 'chk_hot':(205,205,210),'chk_hot_in':(80,80,84),'chk_dis':(70,70,72),'mark':(230,230,230),'mark_hi':(255,255,255),
 'sb_border':(14,14,14),'sb_face':[(0,(92,92,96)),(1,(56,56,60))],'sb_hot':[(0,(112,112,116)),(1,(72,72,76))],
 'sb_pressed':[(0,(44,44,46)),(1,(32,32,34))],'sb_dis':(36,36,38),'sb_dis_border':(28,28,30),
 'sb_grip_light':(130,130,134),'sb_grip_dark':(26,26,28),'track':(28,28,30),'track_pressed':(18,18,20),
 'glyph':(215,215,220),'glyph_dis':(80,80,84),
 'tab_border':(92,92,96),'tab_face':[(0,(64,64,68)),(1,(42,42,44))],'tab_hot':(150,150,155),'tab_sel_top':(190,190,195),
 'pane':(38,38,40),'header_face':(50,50,52),'header_lines':[(40,40,42),(32,32,34),(24,24,26)],'header_hot':(170,170,175),
 'edit_border':(100,100,104),'group_border':(85,85,88),
 'progress':{'ProgressChunkSize':'1','ProgressSpaceSize':'0','fill':(140,190,110),'border':(90,90,94),'bar':(30,30,32)},
 'accent':(140,160,190),
}

# ---------------------------------------------------------------- general recolour of every Aero bitmap
AERO_BLUE=(48,150,250)
def recolour(style,c):
    """Aero's whites, greys and blue accents into the style's palette, keeping lightness steps"""
    l=lum(c)
    if chroma(c)>0.25:                       # an accent (Aero's blue, the close button's red, ...)
        a=style['accent'];k=0.6+0.8*l;return [min(255,v*k) for v in a]
    if style is LUNA:                       # neutral: towards XP's warm greys
        return mix([v*l for v in (236,233,216)],[255,255,255],l**6) if l<0.97 else [255,255,255]
    return [max(0,min(255,24+ (1-l)*200))]*3   # Noir: light becomes dark, dark becomes light

# ---------------------------------------------------------------- hand-drawn parts
def push_button(style,w,h):
    s=style;frames=[]
    for state in ('normal','hot','pressed','disabled','default','default_anim'):
        f=Frame(w,h)
        border=s['btn_dis_border'] if state=='disabled' else s['btn_border']
        rrect(f,0,0,w,h,3.5,solid(border))
        if state=='disabled':rrect(f,1,1,w-1,h-1,2.5,solid(s['btn_dis_face']))
        elif state=='pressed':rrect(f,1,1,w-1,h-1,2.5,lambda x,y:vgrad(s['btn_pressed'],y/h))
        else:
            rrect(f,1,1,w-1,h-1,2.5,lambda x,y:vgrad(s['btn_face'],y/h))
            if state=='hot':ring(f,1,1,w-1,h-1,2.5,2,lambda x,y:vgrad(s['btn_hot'],y/h))
            if state in ('default','default_anim'):ring(f,1,1,w-1,h-1,2.5,1.5 if state=='default' else 2,lambda x,y:vgrad(s['btn_default'],y/h))
        frames.append(f)
    return frames
def check_marks(f,size,kind,colour,hi):
    k=size/13
    if kind=='check':
        for (x0,y0,x1,y1) in ((3.5,6.5,5.6,8.8),(5.6,8.8,9.6,3.8)):line(f,x0*k,y0*k,x1*k,y1*k,2.1*k,colour)
    elif kind=='mixed':rrect(f,3.5*k,3.5*k,9.5*k,9.5*k,0.5*k,lambda x,y:mix(hi,colour,(y/size)))
    elif kind=='x':
        line(f,4*k,4*k,9*k,9*k,1.8*k,colour);line(f,9*k,4*k,4*k,9*k,1.8*k,colour)
def checkbox(style,size,count):
    s=style;frames=[];k=size/13
    for group in ('none','check','mixed','implicit','x')[:count//4]:
        for state in ('normal','hot','pressed','disabled'):
            f=Frame(size,size,s['face'])
            dis=state=='disabled'
            rrect(f,0,0,size,size,0,solid(s['chk_dis'] if dis else s['chk_border']))
            inner=(lambda x,y:s['window']) if dis else (lambda x,y:vgrad(s['chk_pressed'] if state=='pressed' else s['chk_face'],(x+y)/(2*size)))
            rrect(f,k,k,size-k,size-k,0,inner)
            if state=='hot':ring(f,k,k,size-k,size-k,0,max(1,1.6*k),lambda x,y:mix(s['chk_hot_in'],s['chk_hot'],y/size))
            if group!='none':
                mark=s['chk_dis'] if dis else (mix(s['mark'],s['face'],.45) if group=='implicit' else s['mark'])
                check_marks(f,size,'check' if group in ('check','implicit') else group,mark,s['mark_hi'])
            frames.append(f)
    return frames
def radio(style,size):
    s=style;frames=[];r=size/2
    for group in ('none','dot'):
        for state in ('normal','hot','pressed','disabled'):
            f=Frame(size,size);dis=state=='disabled'
            circle(f,r,r,r-0.2,solid(s['chk_dis'] if dis else s['chk_border']))
            inner=(lambda x,y:s['window']) if dis else (lambda x,y:vgrad(s['chk_pressed'] if state=='pressed' else s['chk_face'],(x+y)/(2*size)))
            circle(f,r,r,r-1.1*size/13,inner)
            if state=='hot':
                f.shape(lambda x,y:(r-2.9*size/13)**2<(x-r)**2+(y-r)**2<=(r-1.1*size/13)**2,lambda x,y:mix(s['chk_hot_in'],s['chk_hot'],y/size))
            if group=='dot':
                circle(f,r,r,2.6*size/13,(lambda x,y:s['chk_dis']) if dis else (lambda x,y:mix(s['mark_hi'],s['mark'],(y-r+2.6*size/13)/(5.2*size/13))))
            frames.append(f)
    return frames
def scroll_face(style,f,state,horizontal,r=2.5):
    s=style;w,h=f.w,f.h
    if state=='disabled':
        rrect(f,0,0,w,h,r,solid(s['sb_dis_border']));rrect(f,1,1,w-1,h-1,r-1,solid(s['sb_dis']));return
    stops=s['sb_pressed'] if state=='pressed' else s['sb_hot'] if state=='hot' else s['sb_face']
    rrect(f,0,0,w,h,r,solid(s['sb_border']))
    rrect(f,1,1,w-1,h-1,r-1,lambda x,y:vgrad(stops,(y/h) if horizontal else (x/w)))
SB_STATES=('normal','hot','pressed','disabled','hover')
def scroll_thumb(style,w,h,horizontal):return [_thumb(style,w,h,horizontal,state) for state in SB_STATES]
def _thumb(style,w,h,horizontal,state):
    f=Frame(w,h,style['track']);scroll_face(style,f,'hot' if state=='hover' else state,horizontal);return f
def scroll_arrows(style,w,h):
    frames=[]
    for direction in ('up','down','left','right'):
        for state in ('normal','hot','pressed','disabled'):
            f=Frame(w,h,style['track']);scroll_face(style,f,state,direction in ('up','down'));frames.append(f)
    for direction in ('up','down','left','right'):
        f=Frame(w,h,style['track']);scroll_face(style,f,'hot',direction in ('up','down'));frames.append(f)
    return frames
def scroll_track(style,w,h):
    return [Frame(w,h,style['track_pressed'] if state=='pressed' else style['track']) for state in SB_STATES]
def tab_item(style,w,h,edge):
    s=style;frames=[]
    for state in ('normal','hot','selected','disabled','focused'):
        f=Frame(w,h,s['face'])
        x0=0 if edge in ('left','both') else -3;x1=w if edge in ('right','both') else w+3
        rrect(f,x0,0,x1,h+4,2.5,solid(s['tab_border']))
        face=(lambda x,y:s['window']) if state in ('selected','focused') else (lambda x,y:s['btn_dis_face']) if state=='disabled' else (lambda x,y:vgrad(s['tab_face'],y/h))
        rrect(f,x0+1,1,x1-1,h+4,1.5,face)
        if state in ('hot','selected','focused'):
            top=s['tab_sel_top'] if state!='hot' else s['tab_hot']
            rrect(f,x0+1,1,x1-1,3.2,1.5,lambda x,y:mix(s['tab_hot'],top,y/3))
        frames.append(f)
    return frames
def header_item(style,w,h,count):
    s=style;frames=[]
    for i in range(count):
        state=('normal','hot','pressed')[i%3];f=Frame(w,h,s['face'] if state!='pressed' else mix(s['face'],(0,0,0),.06))
        for j,c in enumerate(s['header_lines']):
            for x in range(w):f.blend(x,h-3+j,c,1)
        if state=='hot':
            for j in range(3):
                for x in range(w):f.blend(x,h-3+j,s['header_hot'],1)
        frames.append(f)
    return frames
def plain_border(style,w,h,count,colour,fill,disabled):
    frames=[]
    for i in range(count):
        f=Frame(w,h,fill);c=disabled if i==count-1 and count>1 else colour
        ring(f,0,0,w,h,0,1,solid(c));frames.append(f)
    return frames
def groupbox(style,w,h):
    f=Frame(w,h);ring(f,0,0,w,h,3,1,solid(style['group_border']));return [f]

def painters(style):
    """bitmap name -> function(like image) -> frames"""
    s=style;p={}
    p['blue_button']=lambda img:push_button(s,img['w'],img['h']//6)
    for size in (13,16,20,26,32,40,52):p['blue_checkbox_%dpx'%size]=lambda img,size=size:checkbox(s,size,20)
    for size in (13,16,19,22,25,28,31):p['blue_radiobutton_%dpx'%size]=lambda img,size=size:radio(s,size)
    p['blue_scrollbar_thumb_vertical']=lambda img:scroll_thumb(s,img['w'],img['h']//5,False)
    p['blue_scrollbar_thumb_horizontal']=lambda img:scroll_thumb(s,img['w'],img['h']//5,True)
    p['blue_scrollbar_arrows']=lambda img:scroll_arrows(s,img['w'],img['h']//20)
    for name in ('lower_track_vertical','upper_track_vertical','lower_track_horizontal','upper_track_horizontal'):
        p['blue_scrollbar_'+name]=lambda img:scroll_track(s,img['w'],img['h']//5)
    # grippers keep Aero's drawing, recoloured: some of its gripper images are not 5 equal states
    p['blue_tab_item']=lambda img:tab_item(s,img['w'],img['h']//5,'both')
    p['blue_tab_item_left']=lambda img:tab_item(s,img['w'],img['h']//5,'left')
    p['blue_tab_item_right']=lambda img:tab_item(s,img['w'],img['h']//5,'right')
    p['blue_header_item']=lambda img:header_item(s,img['w'],img['h']//12,12)
    for name in ('noscroll','hscroll','vscroll','hvscroll'):
        p['blue_edit_border_'+name]=lambda img:plain_border(s,img['w'],img['h']//4,4,s['edit_border'],s['window'],s['btn_dis_border'])
    p['blue_combobox_border']=lambda img:plain_border(s,img['w'],img['h']//4,4,s['edit_border'],s['window'],s['btn_dis_border'])
    p['blue_groupbox']=lambda img:groupbox(s,img['w'],img['h'])
    return p

# ---------------------------------------------------------------- shell parts (W179)
# XP's shell classes, which Aero lacks: explorer (tools/build-explorer-hw.py) draws the taskbar from
# Taskbar.BackgroundBottom, the Start button from Start::Button (SetWindowTheme "Start") and the
# window buttons from TaskBand::Toolbar (SetWindowTheme "TaskBand"); without them it stays classic.
def new_bitmap(w,frames):
    """a 32-bit bottom-up BI_RGB bitmap of frames stacked vertically"""
    h=sum(f.h for f in frames);size=w*h*4
    header=b'BM'+struct.pack('<IHHI',54+size,0,0,54)+struct.pack('<IiiHHIIiiII',40,w,h,1,32,0,size,2835,2835,0,0)
    return {'w':w,'h':h,'bpp':32,'header':header,'topdown':False,'px':[list(p) for f in frames for p in f.px]}
def shell_parts(style):
    s=style;parts={}
    # taskbar: one image, stretched
    f=Frame(8,30);rrect(f,0,0,8,30,0,lambda x,y:vgrad(s['taskbar'],y/30));parts['orbis_taskbar.bmp']=new_bitmap(8,[f])
    # Start: square on both sides (W182: the user asked for no rounded right edge); Button.Pushbutton's six states
    frames=[]
    for state in ('normal','hot','pressed','disabled','default','default_anim'):
        stops=s['start_hot'] if state=='hot' else s['start_pressed'] if state=='pressed' else s['start']
        f=Frame(64,30);rrect(f,-16,0,64,30,0,lambda x,y,stops=stops:vgrad(stops,y/30))
        ring(f,-16,0,64,30,0,1,solid([v*0.7 for v in stops[-1][1]]))
        if state=='disabled':
            for p in f.px:p[:3]=[sum(p[:3])/3]*3
        frames.append(f)
    parts['orbis_start.bmp']=new_bitmap(64,frames)
    # window buttons: Toolbar.Button's eight states (normal, hot, pressed, disabled, checked,
    # hotchecked, nearhot, othersidehot); explorer shows the active window's as checked
    frames=[]
    for state in ('normal','hot','pressed','disabled','checked','hotchecked','nearhot','othersidehot'):
        stops=s['band_hot'] if state in ('hot','hotchecked') else s['band_checked'] if state in ('pressed','checked') else s['band']
        f=Frame(24,24);rrect(f,0,0,24,24,3,solid(s['band_border']))
        rrect(f,1,1,23,23,2,lambda x,y,stops=stops:vgrad(stops,y/24))
        frames.append(f)
    parts['orbis_taskband.bmp']=new_bitmap(24,frames)
    ini=['[Taskbar.BackgroundBottom]','BgType = ImageFile','ImageFile = orbis_taskbar.bmp','SizingType = Stretch',
         'SizingMargins = 0, 0, 0, 0','FillColor = %d %d %d'%s['taskbar_fill'],'TextColor = 255 255 255','',
         '[Start::Button.Pushbutton]','BgType = ImageFile','ImageFile = orbis_start.bmp','ImageCount = 6','ImageLayout = Vertical',
         'SizingType = Stretch','SizingMargins = 4, 4, 12, 12','ContentMargins = 4, 4, 2, 2','TextColor = 255 255 255','',
         '[TaskBand::Toolbar.Button]','BgType = ImageFile','ImageFile = orbis_taskband.bmp','ImageCount = 8','ImageLayout = Vertical',
         'SizingType = Stretch','SizingMargins = 4, 4, 4, 4','ContentMargins = 4, 4, 2, 2','TextColor = 255 255 255','']
    return parts,ini

GLYPH=re.compile(r'blue_(scrollbar_arrow_glyphs|combobox_dropdownbutton(_left|_right)?_glyph|spin_glyph|header_sort_arrow)')
def style_bitmap(style,name,img,paint):
    if name in paint:
        img['bg']=style['face'] if img['bpp']==24 else None
        return stack(paint[name](img),img)
    glyph=GLYPH.match(name) is not None
    # scroll arrow glyphs: 20 states (up, down, left, right x normal, hot, pressed, disabled; 4 hover)
    frame_h=img['h']//20 if name.startswith('blue_scrollbar_arrow_glyphs') else 0
    for i,p in enumerate(img['px']):
        if img['bpp']==24 and tuple(p[:3])==(255,0,255):continue
        if glyph and img['bpp']==32:
            state=(i//img['w'])//frame_h if frame_h else 0
            p[:3]=style['glyph_dis'] if frame_h and state<16 and state%4==3 else style['glyph'];continue
        p[:3]=recolour(style,p)
    return img

# ---------------------------------------------------------------- INI and names
def style_rc(style,rc):
    s=style
    rc=rc.replace('"DisplayName = Aero\\r\\n"','"DisplayName = %s\\r\\n"'%s['name'])
    rc=rc.replace('"ToolTip = Aero Visual Style\\r\\n"','"ToolTip = %s\\r\\n"'%s['tooltip'])
    rc=rc.replace('IDS_COLOR_DISPLAY_NAME_BLUE         "Blue"','IDS_COLOR_DISPLAY_NAME_BLUE         "%s"'%s['color'])
    rc=rc.replace('IDS_COLOR_TOOLTIP_BLUE         "Blue"','IDS_COLOR_TOOLTIP_BLUE         "%s"'%s['color'])
    ini_start=rc.index('BLUE_INI TEXTFILE');head,ini=rc[:ini_start],rc[ini_start:]
    sysm=ini.index('[SysMetrics]');end=ini.index('; Nonclient metrics')
    block=ini[sysm:end]
    # replacements are functions: a template string would turn the rc's \r\n into control characters
    for key,colour in s['sys'].items():
        block,n=re.subn(r'"%s = \d+ \d+ \d+\\r\\n"'%key,lambda m,key=key,colour=colour:'"%s = %d %d %d\\r\\n"'%((key,)+tuple(colour)),block)
        if n!=1:raise SystemExit('SysMetrics colour %s not found once'%key)
    rest=ini[:sysm]+block+ini[end:]
    # control colours outside SysMetrics: Aero's defaults through the style's recolour; text in the
    # style's text colour (Aero's white text on its blue pressed button would vanish on XP's beige)
    def colour_value(m):
        r,g,b=(int(v) for v in m.group(2).split())
        if 'text' in m.group(1).lower() and chroma((r,g,b))<0.25:c=s['text']
        else:c=recolour(s,[r,g,b])
        return '"%s = %d %d %d\\r\\n"'%(m.group(1),*(int(round(v)) for v in c))
    pre,post=rest[:rest.index('[SysMetrics]')],rest[rest.index('; Nonclient metrics'):]
    post=re.sub(r'"(\w*Colou?r\w*) = (\d+ \d+ \d+)\\r\\n"',colour_value,post)
    pre=re.sub(r'"(\w*Colou?r\w*) = (\d+ \d+ \d+)\\r\\n"',colour_value,pre)
    rest=pre+rest[rest.index('[SysMetrics]'):rest.index('; Nonclient metrics')]+post
    # progress bar: XP's green blocks / Noir's smooth fill
    pg=s['progress']
    rest=rest.replace('"ProgressChunkSize = 1\\r\\n"','"ProgressChunkSize = %s\\r\\n"'%pg['ProgressChunkSize'],1)
    rest=rest.replace('"ProgressSpaceSize = 0\\r\\n"','"ProgressSpaceSize = %s\\r\\n"'%pg['ProgressSpaceSize'],1)
    prog_start=rest.index('"[Progress]\\r\\n"');prog_end=rest.index('"[Progress.Fill(Error)]\\r\\n"')
    prog=rest[prog_start:prog_end]
    prog=re.sub(r'"FillColor = \d+ \d+ \d+\\r\\n"',lambda m:'"FillColor = %d %d %d\\r\\n"'%pg['fill'],prog)
    prog=re.sub(r'"BorderColor = \d+ \d+ \d+\\r\\n"',lambda m:'"BorderColor = %d %d %d\\r\\n"'%pg['border'],prog)
    prog=prog.replace('"[Progress.Bar]\\r\\n"\n"MinSize = 10, 10\\r\\n"\n"FillColor = %d %d %d\\r\\n"'%pg['fill'],
                      '"[Progress.Bar]\\r\\n"\n"MinSize = 10, 10\\r\\n"\n"FillColor = %d %d %d\\r\\n"'%pg['bar'])
    prog=prog.replace('"[Progress.BarVert]\\r\\n"\n"FillColor = %d %d %d\\r\\n"'%pg['fill'],
                      '"[Progress.BarVert]\\r\\n"\n"FillColor = %d %d %d\\r\\n"'%pg['bar'])
    rest=rest[:prog_start]+prog+rest[prog_end:]
    # no state transitions: Aero's 100 ms fades repaint each control several times per change, and
    # Aero felt slower on the console (W175); XP and Royale Noir switched states at once
    kept,skipping,dropped=[],False,0
    for line in rest.split('\n'):
        if line.startswith('"TransitionDurations'):skipping=True;dropped+=1
        if not skipping:kept.append(line)
        elif '\\r\\n"' in line:skipping=False
    if dropped!=32:raise SystemExit('expected 32 TransitionDurations in Aero, found %d'%dropped)
    rc=head+'\n'.join(kept)
    # W179: the shell parts, after the recolour (their colours are the style's own), and their bitmaps
    parts,ini=shell_parts(s)
    first=rc.index('"[Button.Pushbutton]\\r\\n"')
    rc=rc[:first]+''.join('"%s\\r\\n"\n'%line for line in ini)+rc[first:]
    rc+='\n/* W179: shell parts (tools/build-msstyles-hw.py) */\n'+''.join(
        '%s BITMAP "%s"\n'%(name.upper().replace('.','_'),name) for name in sorted(parts))
    return rc

# ---------------------------------------------------------------- build
dry=subprocess.run(['make','-n','-W','../../source/dlls/aero.msstyles/aero.rc','dlls/aero.msstyles/x86_64-windows/aero.msstyles'],
                   cwd=BUILD,capture_output=True,text=True,check=True).stdout.replace('\\\n',' ')
commands=[l for l in dry.splitlines() if 'aero.msstyles' in l and not l.startswith('make')]
if len(commands)!=2 or 'wrc' not in commands[0] or 'winegcc' not in commands[1]:
    raise SystemExit('make -n did not give the aero.msstyles commands:\n'+dry[-2000:])
if work.exists():shutil.rmtree(work)
if out.exists():shutil.rmtree(out)
manifest={'schema_version':1,'wine_commit':commit,'builder_sha256':sha(__file__),'styles':{},'source_patches':False}
for style in (LUNA,NOIR):
    key=style['name'].lower();overlay=work/key/'src';overlay.mkdir(parents=True)
    paint=painters(style);drawn=[]
    for path in sorted(AERO.iterdir()):
        if path.suffix=='.bmp':
            img=style_bitmap(style,path.stem,read_bmp(path),paint);write_bmp(overlay/path.name,img)
            if path.stem in paint:drawn.append(path.name)
        elif path.suffix in ('.rc','.h'):shutil.copyfile(path,overlay/path.name)
    (overlay/'aero.rc').write_text(style_rc(style,(AERO/'aero.rc').read_text()))
    for name,img in shell_parts(style)[0].items():write_bmp(overlay/name,img);drawn.append(name)
    res=work/key/(key+'.res');target=out/key/(key+'.msstyles');target.parent.mkdir(parents=True)
    wrc=commands[0].replace('-I../../source/dlls/aero.msstyles','-I'+str(overlay)).replace(
        '../../source/dlls/aero.msstyles/aero.rc',str(overlay/'aero.rc')).replace('-o dlls/aero.msstyles/aero.res','-o '+str(res))
    link=commands[1].replace('-o dlls/aero.msstyles/x86_64-windows/aero.msstyles','-o '+str(target)).replace(
        ' dlls/aero.msstyles/aero.res',' '+str(res))
    if str(overlay) not in wrc or str(res) not in link or str(target) not in link:raise SystemExit('could not redirect the aero commands')
    for command in (wrc,link):
        run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
        if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
    manifest['styles'][key]={'path':'%s/%s.msstyles'%(key,key),'sha256':sha(target),'display_name':style['name'],
                             'color_name':'Blue','drawn_bitmaps':drawn,'commands':[wrc,link]}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:{'sha256':v['sha256'][:16],'drawn':len(v['drawn_bitmaps'])} for k,v in manifest['styles'].items()}))
