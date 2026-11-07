#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W090: icons for the Start menu's Graphics Tools (tools/make-start-menu.py).

The test programs (glxgears, vkcube, vkspin64) have no icon resources, so the shortcuts point
to these .ico files: each drawn here, 16, 32 and 48 pixels, 32-bit BGRA with an AND mask.
glxgears: three gears (red, green, blue); vkcube: a shaded cube; vkspin64: the probe's
red-green-blue triangle; mangohud: an orange tile with an M, for the MangoHud configuration.
Output: out/icons/<name>.ico and manifest.json.
"""
import hashlib,json,math,pathlib,struct
ROOT=pathlib.Path(__file__).resolve().parents[1];out=ROOT/'out/icons'
SIZES=(16,32,48)

def blend(pixel,colour,alpha):
    return tuple(int(pixel[i]*(1-alpha)+colour[i]*alpha) for i in range(3))+(max(pixel[3],int(255*alpha)),)

def raster(size,inside):
    """inside(x,y) in unit coordinates -> (r,g,b) or None; 4x4 supersampling for the edges"""
    pixels=[]
    for y in range(size):
        row=[]
        for x in range(size):
            hits={}
            for sy in range(4):
                for sx in range(4):
                    colour=inside((x+(sx+.5)/4)/size,(y+(sy+.5)/4)/size)
                    if colour:hits[colour]=hits.get(colour,0)+1
            pixel=(0,0,0,0)
            for colour,count in sorted(hits.items(),key=lambda item:item[1]):
                pixel=blend(pixel,colour,count/16) if pixel[3] else colour+(int(255*count/16),)
            row.append(pixel)
        pixels.append(row)
    return pixels

def gear(cx,cy,radius,teeth,phase,colour):
    def inside(x,y):
        dx,dy=x-cx,y-cy;r=math.hypot(dx,dy);a=math.atan2(dy,dx)+phase
        outer=radius*(1.0 if math.cos(a*teeth)>0 else .78)
        return colour if radius*.32<r<outer else None
    return inside

def glxgears(x,y):
    for shape in (gear(.36,.40,.30,10,0,(220,40,40)),gear(.74,.34,.21,9,.3,(40,190,70)),gear(.66,.76,.20,9,.1,(60,90,230))):
        colour=shape(x,y)
        if colour:return colour
    return None

def polygon(points,x,y):
    inside=False
    for i in range(len(points)):
        (x1,y1),(x2,y2)=points[i],points[i-1]
        if (y1>y)!=(y2>y) and x<(x2-x1)*(y-y1)/(y2-y1)+x1:inside=not inside
    return inside

def vkcube(x,y):
    # isometric cube: top, left and right faces around the tile's centre
    s=.40;h=s*math.sqrt(3)/2;c=(.5,.52)
    def at(dx,dy):return (c[0]+dx,c[1]+dy)
    top,ur,lr,bottom,ll,ul,centre=at(0,-s),at(h,-s/2),at(h,s/2),at(0,s),at(-h,s/2),at(-h,-s/2),at(0,0)
    if polygon((top,ur,centre,ul),x,y):return (235,80,80)
    if polygon((ul,centre,bottom,ll),x,y):return (175,35,45)
    if polygon((centre,ur,lr,bottom),x,y):return (120,20,30)
    return None

def vkspin64(x,y):
    # the G001 probe's triangle (native/vk_probe/shaders/triangle.vert), colours by barycentre
    a,b,c=(.5,.10),(.92,.86),(.08,.86)
    det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    l1=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/det
    l2=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/det
    l3=1-l1-l2
    if min(l1,l2,l3)<0:return None
    peak=max(l1,l2,l3)
    return tuple(int(255*v/peak) for v in (l1,l2,l3))

def mangohud(x,y):
    # rounded orange tile with a white M
    if abs(x-.5)>.44 or abs(y-.5)>.44:return None
    if (abs(x-.5)>.34 and abs(y-.5)>.34) and math.hypot(abs(x-.5)-.34,abs(y-.5)-.34)>.10:return None
    if .26<y<.74:
        u=(x-.22)/.56
        if 0<=u<=1:
            stroke=.13
            if u<stroke or u>1-stroke:return (255,255,255)
            v=(y-.26)/.48
            if v<.62 and (abs(u-.5)-(.5-stroke)*(1-v/.62))**2<.004:return (255,255,255)
    return (240,130,30)

def web(x,y):
    # W179: a blue globe with an equator, two parallels and three meridians (Internet Explorer)
    dx,dy=x-.5,y-.5;r=math.hypot(dx,dy)
    if r>.43:return None
    line=(30,70,170)
    if r>.40:return line
    if abs(dy)<.022 or abs(abs(dy)-.21)<.02:return line
    for width in (0,.20,.36):
        if width and abs(dx*dx/(width*width)+dy*dy/(.43*.43)-1)<.10:return line
        if not width and abs(dx)<.022:return line
    return (90,160,240)

def webview(x,y):
    # W179: a window with the globe inside (the WebView test programs)
    if not (.06<x<.94 and .12<y<.90):return None
    if y<.26:return (40,90,190)
    if x<.10 or x>.90 or y>.86:return (110,110,120)
    globe=web(.5+(x-.5)/.68,.5+(y-.58)/.68)
    return globe or (250,250,250)

def ico(images):
    """ICO with one 32-bit BMP (BITMAPINFOHEADER, bottom-up, height doubled for the mask) per size"""
    header=struct.pack('<HHH',0,1,len(images));entries=b'';data=b''
    offset=6+16*len(images)
    for size,pixels in images:
        xor=b''.join(bytes((p[2],p[1],p[0],p[3])) for row in reversed(pixels) for p in row)
        mask_row=((size+31)//32)*4
        mask=b''
        for row in reversed(pixels):
            line=bytearray(mask_row)
            for i,p in enumerate(row):
                if p[3]==0:line[i//8]|=0x80>>(i%8)
            mask+=bytes(line)
        bmp=struct.pack('<IiiHHIIiiII',40,size,size*2,1,32,0,len(xor)+len(mask),0,0,0,0)+xor+mask
        entries+=struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(bmp),offset)
        data+=bmp;offset+=len(bmp)
    return header+entries+data

out.mkdir(parents=True,exist_ok=True)
manifest={'schema_version':1,'generator':'tools/make-icons.py','icons':{}}
for name,shape in (('glxgears',glxgears),('vkcube',vkcube),('vkspin64',vkspin64),('mangohud',mangohud),
                   ('web',web),('webview',webview)):
    target=out/(name+'.ico');target.write_bytes(ico([(size,raster(size,shape)) for size in SIZES]))
    manifest['icons'][name+'.ico']=hashlib.sha256(target.read_bytes()).hexdigest()
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest['icons']))
