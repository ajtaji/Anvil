#!/usr/bin/env python3
"""Independent prepared tab-strip state, full text callback and raster oracle."""
from pathlib import Path
import argparse,json,struct,math
from PIL import Image
EXPECTED=(88, 80, -22004, 0, 0, 0, 0, 6647375, 0, 2, 114, 20, 0, 0, 20, 0, 10, 0, 0, 10, 0, 0, 0, 30, 1, 0, 198, 114, 0, 0, 0, 0, 17, 0, 0, -22099, -22004, 0, -22002, -22002, -22098, -22098, 0, 0, 0, 0, 148, 13, 104, 250, 0, 0, 0, 0, 0, 0, 10, 0, 10, 0, 0, 250, 0, 0, 0, 0, 0, 0, 3, 0, 4, 0, 3, -22006, 0, -22006, 0, -22000, -22001, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

def packet(op,font=0,rect=(0,0,0,0),colour=(0,0,0,0),text=''):
    raw=text.encode('utf8');assert len(raw)<64
    return struct.pack('<qq8f8sq64s',op,font,*rect,*colour,raw[:8].ljust(8,b'\0'),len(raw),raw.ljust(64,b'\0'))
def golden_trace():
    out=[]
    def box(x,y,w,h,c):out.append(packet(1,rect=(x,y,w,h),colour=(*c,1)))
    def text(font,x,y,s,c):out.append(packet(2,font,rect=(x,y,0,0),colour=(*c,1),text=s))
    line=(.196,.2,.212);dim=(.576,.596,.635)
    out.append(packet(4));box(10,20,600,30,(.129,.133,.145));box(10,49,600,1,line)
    out.append(packet(3,rect=(10,20,600,30)))
    box(14,20,68,29,(.145,.149,.161));box(14,20,1,29,line);box(81,20,1,29,line)
    text(0,26,27,'One',(.863,)*3);text(1,68.5,27.5,'x',dim)
    text(0,94,27,'pipe|name',dim)
    box(185,28.5,6,6,dim);box(183,34.5,10,2,dim);box(187,36.5,2,5,dim)
    text(2,210,27,'Preview',dim);text(1,298.5,27.5,'x',dim)
    box(14,20,68,2,(.353,.741,.816));out.append(packet(4));assert len(out)==17
    return b''.join(out)
def check(report,picture,scene):
    assert scene in (1,2) and len(report)==16384
    n=len(EXPECTED);assert struct.unpack_from('<5q',report)==(0x4e545431,1,0,n,17),struct.unpack_from('<5q',report)
    font=struct.unpack_from('<q',report,56)[0];assert font>0 and font&65535==1
    assert struct.unpack_from('<q',report,128)[0]==scene
    active,shownN=struct.unpack_from('<2q',report,136);assert active==(10 if scene==1 else 40)
    for i,e in enumerate(EXPECTED):assert struct.unpack_from('<2q',report,272+i*16)==(e,e),(i+1,struct.unpack_from('<2q',report,272+i*16),e)
    gold=golden_trace();got=report[4096:4096+len(gold)]
    for i in range(17):assert got[i*128:(i+1)*128]==gold[i*128:(i+1)*128],('callback',i+1,got[i*128:(i+1)*128].hex(),gold[i*128:(i+1)*128].hex())
    assert report[3072:3086]==b'an extreme...\0','fitted mock label'
    assert 0<shownN<64
    shown=report[3200:3200+shownN].decode('utf8');assert report[3200+shownN]==0
    if scene==1:assert shown=='One'
    else:
        assert shown.endswith('...') and 'an extremely long document name which needs shortening'.startswith(shown[:-3]),shown
    unused=bytearray(report)
    for a,b in [(0,40),(56,124),(128,152),(272,272+n*16),(3072,3086),(3200,3201+shownN),(4096,4096+len(gold))]:unused[a:b]=b'\0'*(b-a)
    assert not any(unused),'unused report bytes'
    side,scroll,vl,vr,labelx,refx,cw,ty,width,h,shownW,uiH,pinX,pinY,u=struct.unpack_from('<15f',report,64)
    assert all(math.isfinite(v) and abs(v)<=1000000 for v in (side,scroll,vl,vr,labelx,refx,cw,ty,width,h,shownW,uiH,pinX,pinY,u))
    assert abs(ty-(50+(30-uiH)/2))<.001
    assert 18<=side<=29 and 0<uiH<40 and h==30 and abs(cw-shownW-2)<.001
    assert abs(side/9-u)<.0001 and abs(pinY-(50+(29-side)/2))<.001
    if scene==1:
        assert scroll==0 and vl==20 and vr==620 and labelx==36
        assert abs(width-shownW-26-side)<.002
    else:
        assert scroll>0 and abs(vl-20-side-4)<.002 and vr==220
        assert abs(width-(200-2*(side+4)-8))<.002
        assert abs(labelx-(220-width+12))<.002 and shownW<=width-19-side+.002
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    probes=0
    def pixel(x,y,c):
        nonlocal probes
        p=(math.floor(x*2+.5),math.floor(y*2+.5));assert im.getpixel(p)==c,(p,im.getpixel(p),c);probes+=1
    bg=(33,34,37);panel=(37,38,41);line=(50,51,54)
    pixel(21,53,bg);pixel(labelx-10,60,panel);pixel(labelx-8,51,(90,189,208));pixel(21,79,line);pixel(10,200,(0,0,0))
    if scene==1:
        for x,y in [(pinX+4.5*u,pinY+3*u),(pinX+4.5*u,pinY+5*u),(pinX+4.5*u,pinY+6.5*u)]:pixel(x,y,(147,152,162))
    else:pixel(vl-1,53,line)
    x0=math.floor(labelx*2);xr=math.floor(refx*2);pixels=max(1,math.floor(cw*2));a=im.crop((x0,104,x0+pixels,156));b=im.crop((xr,104,xr+pixels,156))
    assert sum(p!=panel for p in a.getdata())>30,'empty active label'
    assert max(abs(x-y) for p,q in zip(a.getdata(),b.getdata()) for x,y in zip(p,q))<=1,'tab/reference glyph raster'
    return dict(checks=n,exact_callback_packets=17,full_callback_text=True,geometry_probes=probes,reference_cell_pixels=pixels*52,passed=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--scene',choices=['basic','overflow'],required=True);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture,dict(basic=1,overflow=2)[a.scene]),indent=2))
if __name__=='__main__':main()
