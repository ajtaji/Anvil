#!/usr/bin/env python3
"""Independent prepared menu state, complete callback trace and raster oracle."""
from pathlib import Path
import argparse,json,struct,math
from PIL import Image
EXPECTED={1: (88, -21804, 0, 0, 0, 0, -21800, 0, -21803, 0, -21801, 0, 1701603654, -21800, 0, -21801, 0, 1, 1, 0, 0, 0, 1, 0, 178, 111, 0, 49, 0, 0, 0, 21, 0, 0, 1, 0, 0, 0, 0, 64, 322, 0, 48, 0, 638, 0, 632, 0, 0, 1, 0, 0, 0, -21900, 1, -21804, 0, -21802, -21802, -21901, -21901, 0, 0, 0, 0, 0, 0, 0, 0, 0, 464, 286, 0, 0, 0, 0, 0, 0, 336, -21800, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0), 2: (88, -21804, 0, 0, 0, 0, -21800, 0, -21803, 0, -21801, 0, 1701603654, -21800, 0, -21801, 0, 1, 1, 0, 0, 0, 1, 0, 178, 111, 0, 49, 0, 0, 0, 21, 0, 0, 1, 0, 0, 0, 0, 64, 322, 0, 48, 0, 638, 0, 632, 0, 0, 1, 0, 0, 0, -21900, 1, -21804, 0, -21802, -21802, -21901, -21901, 0, 0, 0, 0, 0, 0, 0, 0, 0, 464, 286, 0, 0, 0, 0, 0, 0, 336, -21800, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0), 3: (88, -21804, 0, 0, 0, 0, -21800, 0, -21803, 0, -21801, 0, 1701603654, -21800, 0, -21801, 0, 1, 1, 0, 0, 0, 1, 0, 178, 111, 0, 49, 0, 0, 0, 21, 0, 0, 1, 0, 0, 0, 0, 64, 322, 0, 48, 0, 638, 0, 632, 0, 0, 1, 0, 0, 0, -21900, 1, -21804, 0, -21802, -21802, -21901, -21901, 0, 0, 0, 0, 0, 0, 0, 0, 0, 464, 286, 0, 0, 0, 0, 0, 0, 336, -21800, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)}

def f(v):return struct.unpack('<f',struct.pack('<f',v))[0]
def mul(a,b):return f(f(a)*f(b))
def packet(op,font=0,rect=(0,0,0,0),colour=(0,0,0,0),text=''):
    raw=text.encode();return struct.pack('<qq8f8sq16x',op,font,*rect,*colour,raw[:8].ljust(8,b'\0'),len(raw))
def golden_trace():
    out=[]
    def box(x,y,w,h,c):out.append(packet(1,rect=(x,y,w,h),colour=(*c,1)))
    def text(font,x,y,s,c):out.append(packet(2,font,rect=(x,y,0,0),colour=(*c,1),text=s))
    def clear():out.append(packet(4))
    def clip(x,y,w,h):out.append(packet(3,rect=(x,y,w,h)))
    head=(.169,.173,.184);line=(.196,.2,.212);acc=(.353,.741,.816);white=(.863,)*3;faint=(.435,.459,.498)
    def panel(x,y,w,h,vy,vh):
        for j in range(1,5):out.append(packet(1,rect=(x-j,y-j,w+j*2,h+j*2),colour=(0,0,0,f(f(.45)/mul(j,1.5)))))
        box(x,y,w,h,head)
        border=tuple(mul(c,.55) for c in acc)
        for rect in [(x,y,w,1),(x,y+h-1,w,1),(x,y,1,h),(x+w-1,y,1,h)]:box(*rect,border)
        clip(x,vy,w,vh)
    clear();box(0,0,640,30,head);box(0,29,640,1,line);clip(0,0,640,30)
    box(8,0,56,30,(mul(.353,.30),mul(.741,.30),mul(.816,.34)))
    box(8,28,56,2,acc);text(0,20,7,'File',acc);text(0,76,7,'Tools',white)
    clear();panel(8,30,172,137,34,129)
    text(0,26,38,'Open',white);text(1,118,39,'Ctrl+O',faint)
    for j,dy in enumerate([2,3,4,3,2,1,0]):box(12+j*1.5,64.75+dy*1.5,1.5,4.5,(.361,.749,.596))
    text(0,26,62,'Show grid',white);text(0,26,86,'Disabled',faint)
    box(18,110.5,152,1,line)
    box(9,115,170,24,(mul(.353,.28),mul(.741,.28),mul(.816,.32)))
    text(0,26,119,'More',white);text(0,164,119,'>',(.576,.596,.635));text(0,26,143,'Exit',white)
    clear();panel(178,111,180,56,115,48);text(0,196,119,'First',white);text(0,196,143,'Last',white);clear()
    assert len(out)==49
    return b''.join(out)

def check(report,picture,scene):
    assert scene in EXPECTED and len(report)==16384,'scene/report size'
    n=len(EXPECTED[scene]);assert struct.unpack_from('<5q',report)==(0x4e4d4131,1,0,n,49),struct.unpack_from('<5q',report)
    assert struct.unpack_from('<q',report,56)[0]>0 and struct.unpack_from('<q',report,56)[0]&65535==1,'font handle'
    assert struct.unpack_from('<q',report,128)[0]==scene,'scene field'
    for i,e in enumerate(EXPECTED[scene]):assert struct.unpack_from('<2q',report,272+i*16)==(e,e),(i+1,struct.unpack_from('<2q',report,272+i*16),e)
    gold=golden_trace();got=report[4096:4096+len(gold)]
    if got!=gold:
        for i in range(49):assert got[i*80:(i+1)*80]==gold[i*80:(i+1)*80],('callback',i+1,got[i*80:(i+1)*80].hex(),gold[i*80:(i+1)*80].hex())
    unused=bytearray(report)
    for a,b in [(0,40),(56,68),(72,120),(128,144),(148,160),(272,272+n*16),(4096,4096+len(gold))]:unused[a:b]=b'\0'*(b-a)
    assert not any(unused),'unused report bytes'
    height=struct.unpack_from('<f',report,64)[0];ow,sw=struct.unpack_from('<2f',report,72)
    rx,ry,rw,rh,vy,vh=struct.unpack_from('<6f',report,80);sx,sy,ssw,sh=struct.unpack_from('<4f',report,104)
    fw,dfw=struct.unpack_from('<2f',report,136);refx,labelx,rowy=struct.unpack_from('<3f',report,148)
    assert fw==dfw and 0<fw<100 and 0<height<40 and 0<ow<70 and 0<sw<100,'font metrics'
    wantw=160 if scene==2 else max(160,f(f(f(46+ow)+46)+sw))
    wantx=8 if scene==1 else f(f(8+fw)+24) if scene==2 else f(636-wantw)
    for a,b in zip((rx,ry,rw,rh,vy,vh),(wantx,30,wantw,362 if scene==2 else 137,50 if scene==2 else 34,322 if scene==2 else 129)):
        assert abs(a-b)<.002,('root layout',a,b)
    if scene!=2:
        for a,b in zip((sx,sy,ssw,sh),(rx+rw-2 if scene==1 else rx-178,111,180,56)):assert abs(a-b)<.002,('sub layout',a,b)
    else:assert (sx,sy,ssw,sh)==(0,0,0,0),'closed submenu'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    probes=0
    def pixel(x,y,c):
        nonlocal probes
        p=(int(math.floor(x*2+.5)),int(math.floor(y*2+.5)));got=im.getpixel(p)
        assert got==c,(p,got,c);probes+=1
    head=(43,44,47);hover=(25,53,67);line=(50,51,54)
    px=rx+2 if scene!=3 else rx+rw-3
    for y in range(int(vy)+2,int(vy+vh)-2,4):
        selected=98<=y<122 if scene==2 else 115<=y<139
        pixel(px,y,hover if selected else head)
    if scene!=2:
        for y in range(118,161,4):pixel(sx+2,y,head)
        for j,dy in enumerate([2,3,4,3,2,1,0]):pixel(rx+4+(j+.5)*1.5,64.75+dy*1.5+2.0,(92,191,152))
        disabled=im.crop((round((rx+18)*2),164,round((rx+100)*2),212))
        ink=[p for p in disabled.getdata() if p!=head];assert len(ink)>100 and max(max(p) for p in ink)<=128,'disabled text colour/ink'
    else:
        pixel(rx+3,40,line);pixel(rx+3,380,line)
    pixel(10,380,(0,0,0))
    if scene==3:pixel(10,5,(0,0,0))
    x0=int(math.floor(labelx*2));xr=int(math.floor(refx*2));y0=round(rowy*2)
    a=im.crop((x0,y0,x0+140,y0+48));b=im.crop((xr,y0,xr+140,y0+48))
    assert sum(p!=head for p in a.getdata())>100,'empty label'
    assert max(abs(x-y) for p,q in zip(a.getdata(),b.getdata()) for x,y in zip(p,q))<=1,'menu/reference glyph raster'
    return dict(checks=n,exact_callback_packets=49,geometry_probes=probes,reference_cell_pixels=140*48,passed=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--scene',choices=['menu','scroll','edge'],required=True);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args()
    print(json.dumps(check(a.report.read_bytes(),a.picture,dict(menu=1,scroll=2,edge=3)[a.scene]),indent=2))
if __name__=='__main__':main()
