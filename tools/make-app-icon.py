#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""PKG icon (icon0.png, 512x512): a four-pane window whose panes form a PS4 silhouette.

The console stands upright, seen from the front left: a narrow side strip and the
front face, both cut by the slanted groove. Strip and face are the window's two
columns, the groove its transom; the groove glows like the light bar. Pure Python
(no PIL): polygons filled by scanline at 4x and averaged down.
"""
import pathlib,struct,sys,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
SIZE,SS=512,4;BIG=SIZE*SS

def fill(polygon):
    """coverage 0..1 per output pixel of a polygon given in output coordinates"""
    pts=[(x*SS,y*SS) for x,y in polygon];mask=bytearray(BIG*BIG)
    ys=[p[1] for p in pts]
    for row in range(max(0,int(min(ys))),min(BIG,int(max(ys))+1)):
        y=row+0.5;xs=[]
        for (x0,y0),(x1,y1) in zip(pts,pts[1:]+pts[:1]):
            if (y0<=y<y1) or (y1<=y<y0):xs.append(x0+(y-y0)*(x1-x0)/(y1-y0))
        xs.sort()
        for a,b in zip(xs[::2],xs[1::2]):
            a=max(0,int(a+0.5));b=min(BIG,int(b+0.5))
            if b>a:mask[row*BIG+a:row*BIG+b]=b'\1'*(b-a)
    cov=[0.0]*(SIZE*SIZE)
    for oy in range(SIZE):
        rows=[mask[(oy*SS+k)*BIG:(oy*SS+k+1)*BIG] for k in range(SS)]
        if not any(any(r) for r in rows):continue
        for ox in range(SIZE):
            s=sum(sum(r[ox*SS:ox*SS+SS]) for r in rows)
            if s:cov[oy*SIZE+ox]=s/(SS*SS)
    return cov

def lerp(a,b,t):return tuple(a[i]+(b[i]-a[i])*max(0.0,min(1.0,t)) for i in range(3))
def hexrgb(h):return tuple(int(h[i:i+2],16) for i in (1,3,5))

# background: deep navy, lighter towards the top
img=[lerp(hexrgb('#16305c'),hexrgb('#070f22'),y/(SIZE-1)) for y in range(SIZE) for x in range(SIZE)]
def paint(cov,color_at,alpha=1.0):
    for i,c in enumerate(cov):
        if c:
            y=i//SIZE;img[i]=lerp(img[i],color_at(y),c*alpha)

# columns: side strip L0..L1, front face R0..R1; the gap between them is the mullion
L0,L1,R0,R1=122,166,180,392
TOP_L,TOP_R=64,112           # the face's top edge falls to the right (perspective)
FOOT,BASE_L,BASE_R=456,438,428  # strip foot, face bottom at R0 and R1
GROOVE,SLOPE,HALF=196,0.1376,7  # groove centre at x=R0, its slope, half its width
def groove(x):return GROOVE+SLOPE*(x-R0)
side_top=lambda y:lerp(hexrgb('#3a9cf0'),hexrgb('#1866c4'),(y-TOP_L)/(groove(L0)-TOP_L))
side_low=lambda y:lerp(hexrgb('#155cb8'),hexrgb('#0a3d8a'),(y-groove(L0))/(FOOT-groove(L0)))
face_top=lambda y:lerp(hexrgb('#62c4ff'),hexrgb('#2a8af0'),(y-TOP_L)/(groove(R1)-TOP_L))
face_low=lambda y:lerp(hexrgb('#2380ea'),hexrgb('#0d4fb0'),(y-groove(R0))/(BASE_L-groove(R0)))

# light bar: halo, then the bar itself along the groove
for grow,alpha in ((9,0.12),(5,0.22),(2,0.4)):
    paint(fill([(L0,groove(L0)-3-grow),(R1,groove(R1)-3-grow),(R1,groove(R1)+3+grow),(L0,groove(L0)+3+grow)]),
          lambda y:hexrgb('#5fd0ff'),alpha)
paint(fill([(L0,groove(L0)-2),(R1,groove(R1)-2),(R1,groove(R1)+2),(L0,groove(L0)+2)]),lambda y:hexrgb('#c8f0ff'))
# the four panes
paint(fill([(L0,TOP_L+6),(L1,TOP_L),(L1,groove(L1)-HALF),(L0,groove(L0)-HALF)]),side_top)
paint(fill([(L0,groove(L0)+HALF),(L1,groove(L1)+HALF),(L1,BASE_L),(L0,FOOT)]),side_low)
paint(fill([(R0,TOP_L),(R1,TOP_R),(R1,groove(R1)-HALF),(R0,groove(R0)-HALF)]),face_top)
paint(fill([(R0,groove(R0)+HALF),(R1,groove(R1)+HALF),(R1,BASE_R),(R0,BASE_L)]),face_low)
# a highlight along the top edges
paint(fill([(L0+2,TOP_L+7),(L1-2,TOP_L+1),(L1-2,TOP_L+6),(L0+2,TOP_L+12)]),lambda y:(255,255,255),0.3)
paint(fill([(R0+2,TOP_L+1),(R1-2,TOP_R-1),(R1-2,TOP_R+4),(R0+2,TOP_L+6)]),lambda y:(255,255,255),0.3)

def png(path):
    raw=b''.join(b'\0'+bytes(int(max(0,min(255,round(v)))) for p in img[y*SIZE:(y+1)*SIZE] for v in p) for y in range(SIZE))
    chunk=lambda t,d:struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',SIZE,SIZE,8,2,0,0,0))+
                     chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b''))
target=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'out/app-icon/icon0.png'
png(target);print(target)
