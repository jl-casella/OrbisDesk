#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Draw OrbisDesk's extra desktop wallpapers (W292): procedural landscapes in the spirit of the
default rolling-hills one, generated here with fixed seeds, so nothing is downloaded or copied.

  orbis-dusk.bmp    sunset: orange to violet sky, a low sun, layered hill silhouettes
  orbis-aurora.bmp  night: stars and green aurora curtains over dark hills and a still lake
  orbis-meadow.bmp  morning: pale sky, soft haze, rolling green and gold fields

Output: out/wallpaper-set/<name>.bmp (1280x720, 24-bit bottom-up BMP, as ps5drv's wallpaper layer
and user32's LoadImage read them) and out/wallpaper-set/manifest.json with each file's sha256.
Intended home: tools/make-wallpaper-set.py (the repository root is its parent's parent).
Pure Python; about a minute for the three on a desktop CPU."""
import hashlib,json,math,pathlib,random,struct,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
if len(sys.argv)>1:ROOT=pathlib.Path(sys.argv[1]).resolve()
WIDTH,HEIGHT=1280,720
OUT=ROOT/'out/wallpaper-set'

def mix(a,b,t):
    t=0.0 if t<0 else 1.0 if t>1 else t
    return (a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t)
def ramp(stops,t):
    """colour at t on a list of (position, colour) stops"""
    if t<=stops[0][0]:return stops[0][1]
    for (p0,c0),(p1,c1) in zip(stops,stops[1:]):
        if t<=p1:return mix(c0,c1,(t-p0)/(p1-p0))
    return stops[-1][1]
def ridge(seed,base,amp,waves):
    """a hill line: y of the ridge at column x"""
    rng=random.Random(seed);parts=[(rng.uniform(0.6,1.4)*w,rng.uniform(0,6.3),a) for w,a in waves]
    return lambda x:base-amp*sum(a*math.sin(x/WIDTH*math.pi*w+p) for w,p,a in parts)
def bmp(rows):
    image=b''.join(rows[::-1])  # bottom-up
    return (b'BM'+struct.pack('<IHHI',54+len(image),0,0,54)+
            struct.pack('<IiiHHIIiiII',40,WIDTH,HEIGHT,1,24,0,len(image),2835,2835,0,0)+image)
def pixel(c):return bytes(max(0,min(255,int(v+0.5))) for v in (c[2],c[1],c[0]))

def dusk():
    rng=random.Random(2921)
    sky=[(0.0,(58,36,110)),(0.35,(150,62,120)),(0.62,(240,120,70)),(0.78,(255,190,110))]
    sun_x,sun_y,sun_r=820,455,46
    hills=[(ridge(11,470,40,[(1.3,1.0),(3.1,0.35),(7.0,0.12)]),(118,56,104),0.0),
           (ridge(12,525,55,[(0.9,1.0),(2.6,0.4),(6.0,0.15)]),(78,34,82),0.0),
           (ridge(13,600,60,[(0.7,1.0),(2.2,0.45),(5.5,0.12)]),(44,20,52),0.0)]
    rows=[]
    for y in range(HEIGHT):
        row=bytearray()
        for x in range(WIDTH):
            c=ramp(sky,y/HEIGHT)
            d=math.hypot(x-sun_x,y-sun_y)
            if d<sun_r:c=mix((255,236,170),(255,214,130),d/sun_r)
            else:c=mix(c,(255,200,120),0.55*math.exp(-(d-sun_r)/140.0))
            for line,colour,_ in hills:
                top=line(x)
                if y>top:c=mix(colour,(colour[0]*0.6,colour[1]*0.6,colour[2]*0.7),(y-top)/220.0)
            g=rng.uniform(-1.5,1.5);row+=pixel((c[0]+g,c[1]+g,c[2]+g))
        rows.append(bytes(row))
    return rows

def aurora():
    rng=random.Random(2922)
    stars={(rng.randrange(WIDTH),rng.randrange(0,430)):rng.uniform(0.35,1.0) for _ in range(900)}
    curtains=[(rng.uniform(0,6.3),rng.uniform(0.6,1.2),rng.uniform(140,240),rng.uniform(0.7,1.0),cx,rng.uniform(260,420)) for cx in (260,700,1080)]
    hill=ridge(21,455,45,[(1.1,1.0),(2.9,0.4),(6.5,0.15)])
    shore=520
    def sky_at(x,y):
        c=ramp([(0.0,(6,10,30)),(0.45,(14,30,62)),(0.66,(26,56,84))],y/HEIGHT)
        glow=0.0
        for phase,freq,top,strength,cx,spread in curtains:
            centre=top+60*math.sin(x/WIDTH*math.pi*2*freq+phase)+18*math.sin(x/37.0+phase)
            if y<centre+150:
                below=(y-centre)/150.0
                v=math.exp(-below*below*4.0) if below>0 else math.exp(-below*below*1.2)
                v*=0.7+0.3*math.sin(x/41.0+phase*3)**2  # soft vertical rays
                v*=math.exp(-((x-cx)/spread)**2)  # each curtain covers part of the sky
                glow=max(glow,v*strength)
        c=mix(c,(70,230,150),glow*0.7)
        if glow>0.6:c=mix(c,(170,120,230),(glow-0.6)*0.6)
        return c
    rows=[]
    for y in range(HEIGHT):
        row=bytearray()
        for x in range(WIDTH):
            if y<shore:
                c=sky_at(x,y)
                s=stars.get((x,y))
                if s:c=mix(c,(240,245,255),s*(1-0.8*min(1.0,y/430)))
                if y>hill(x):c=mix((12,22,30),(6,12,18),(y-hill(x))/80.0)
            else:
                # the lake mirrors the sky and hills, darker, with ripples
                my=2*shore-y+round(1.5*math.sin(x/15.0+y/2.0))
                c=sky_at(x,my) if my>=0 else (6,10,30)
                if my>hill(x):c=(10,18,26)
                c=mix(c,(4,8,16),0.45+0.35*(y-shore)/(HEIGHT-shore))
            g=rng.uniform(-1.2,1.2);row+=pixel((c[0]+g,c[1]+g,c[2]+g))
        rows.append(bytes(row))
    return rows

def meadow():
    rng=random.Random(2923)
    sky=[(0.0,(120,170,225)),(0.45,(196,222,240)),(0.6,(236,238,228))]
    far=ridge(31,430,25,[(1.4,1.0),(3.6,0.3)])
    fields=[(ridge(32,470,40,[(1.0,1.0),(2.7,0.35)]),(150,186,96)),
            (ridge(33,520,55,[(0.8,1.0),(2.4,0.4)]),(198,190,92)),
            (ridge(34,590,65,[(0.6,1.0),(2.0,0.45)]),(104,160,60))]
    clouds=[(rng.uniform(0,WIDTH),rng.uniform(70,250),rng.uniform(90,190),rng.uniform(22,38)) for _ in range(7)]
    rows=[]
    for y in range(HEIGHT):
        row=bytearray()
        for x in range(WIDTH):
            c=ramp(sky,y/HEIGHT)
            cover=0.0
            for cx,cy,rx,ry in clouds:
                dx,dy=(x-cx)/rx,(y-cy)/ry;d=dx*dx+dy*dy
                if d<2.5:cover=max(cover,math.exp(-2.2*d))
            c=mix(c,(252,252,250),cover*0.9)
            if y>far(x):c=mix((150,180,175),(130,165,140),(y-far(x))/60.0)
            for line,colour in fields:
                top=line(x)
                if y>top:
                    depth=(y-top)/(HEIGHT-top+1)
                    c=mix(colour,(colour[0]*0.7,colour[1]*0.75,colour[2]*0.6),depth*1.2)
                    # rows in the field, converging upward
                    c=mix(c,(c[0]*0.9,c[1]*0.92,c[2]*0.85),0.5+0.5*math.sin((x-WIDTH/2)/(6+depth*40)+y/8.0))
            g=rng.uniform(-3,3);row+=pixel((c[0]+g,c[1]+g,c[2]+g*0.6))
        rows.append(bytes(row))
    return rows

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);items=[]
    for name,draw,seed in (('orbis-dusk.bmp',dusk,2921),('orbis-aurora.bmp',aurora,2922),('orbis-meadow.bmp',meadow,2923)):
        data=bmp(draw());(OUT/name).write_bytes(data)
        items.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'width':WIDTH,'height':HEIGHT,'seed':seed})
        print(name,items[-1]['sha256'],flush=True)
    (OUT/'manifest.json').write_text(json.dumps({'generator':'tools/make-wallpaper-set.py','wallpapers':items},indent=2)+'\n')
