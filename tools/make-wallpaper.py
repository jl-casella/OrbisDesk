#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Draw the hardware desktop wallpaper: a sky with soft clouds over rolling green hills.

W044. The picture is generated here, deterministically (fixed seed), so the package
carries no third-party artwork. Output: out/wallpaper/orbis-hills.bmp, 1280x720,
24-bit bottom-up BMP, which Wine's desktop loads with LoadImage(LR_LOADFROMFILE).
"""
import hashlib,json,math,pathlib,random,struct
ROOT=pathlib.Path(__file__).resolve().parents[1]
WIDTH,HEIGHT=1280,720
out=ROOT/'out/wallpaper';out.mkdir(parents=True,exist_ok=True)
rng=random.Random(44)
def mix(a,b,t):return tuple(a[i]+(b[i]-a[i])*t for i in range(3))
# clouds: clusters of soft ellipses in the upper sky
clouds=[]
for _ in range(9):
    cx,cy=rng.uniform(-50,WIDTH+50),rng.uniform(40,330);scale=rng.uniform(0.6,1.6)
    for _ in range(rng.randint(5,9)):
        clouds.append((cx+rng.uniform(-110,110)*scale,cy+rng.uniform(-18,18)*scale,
                       rng.uniform(40,90)*scale,rng.uniform(16,34)*scale))
def cloud_cover(x,y):
    cover=0.0
    for cx,cy,rx,ry in clouds:
        dx,dy=(x-cx)/rx,(y-cy)/ry;d=dx*dx+dy*dy
        if d<1.6:cover=max(cover,math.exp(-1.8*d))
    return min(1.0,cover*1.25)
def hill(x):
    """Height of the front hill's ridge (pixels from the top) at column x."""
    return 430-70*math.sin((x/WIDTH)*math.pi*0.95+0.25)+18*math.sin(x/97.0)+9*math.sin(x/41.0+1.3)
def far_hill(x):return 470-30*math.sin((x/WIDTH)*math.pi*1.7+2.2)+6*math.sin(x/53.0)
rows=[]
for y in range(HEIGHT):
    row=bytearray()
    for x in range(WIDTH):
        t=y/HEIGHT
        colour=mix((22,84,196),(150,200,245),min(1.0,t*1.6))
        c=cloud_cover(x,y) if y<420 else 0.0
        if c:colour=mix(colour,(250,252,255),c)
        if y>far_hill(x):colour=mix((70,120,90),(95,140,95),min(1.0,(y-far_hill(x))/80))
        ridge=hill(x)
        if y>ridge:
            depth=(y-ridge)/(HEIGHT-ridge+1)
            colour=mix((96,176,44),(40,110,22),min(1.0,depth*1.3))
            # a little grain so the grass is not flat
            g=rng.uniform(-6,6);colour=(colour[0]+g,colour[1]+g,colour[2]+g*0.5)
        row+=bytes(max(0,min(255,int(v))) for v in (colour[2],colour[1],colour[0]))
    rows.append(bytes(row))
stride=WIDTH*3
image=b''.join(rows[::-1])  # bottom-up
header=b'BM'+struct.pack('<IHHI',14+40+len(image),0,0,54)+struct.pack('<IiiHHIIiiII',40,WIDTH,HEIGHT,1,24,0,len(image),2835,2835,0,0)
target=out/'orbis-hills.bmp';target.write_bytes(header+image)
digest=hashlib.sha256(target.read_bytes()).hexdigest()
(out/'manifest.json').write_text(json.dumps({'wallpaper':{'path':'orbis-hills.bmp','sha256':digest,'width':WIDTH,'height':HEIGHT,
                                                          'generator':'tools/make-wallpaper.py','seed':44}},indent=2)+'\n')
print(json.dumps({'wallpaper':str(target.relative_to(ROOT)),'sha256':digest}))
