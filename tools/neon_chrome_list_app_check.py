#!/usr/bin/env python3
"""Independent prepared list/tree state, complete callback and native raster oracle."""
from pathlib import Path
import argparse,json,struct,math
from PIL import Image
EXPECTED=(112, 56, 0, -22204, 0, 0, 0, 0, 0, 1920298835, -22206, -22200, -22200, 0, 3, 2, 18, 144, 0, 0, 0, 15, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 40, 0, 0, 10, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0, 2, 0, 0, 0, 2, 15, 0, 0, 0, 900001, 0, 2, 0, 2, 900001, 0, 0, 0, 1, 20, -22199, 20, 0, 0, 20, -22199, 2, -22204, 0, -22202, -22202, -22198, -22198, 0, 0, 1, 1, 0, 0, -22197, -22201, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

def packet(op,font=0,rect=(0,0,0,0),colour=(0,0,0,0),text=''):
    raw=text.encode('utf8');assert len(raw)<64
    return struct.pack('<qq8f8sq64s',op,font,*rect,*colour,raw[:8].ljust(8,b'\0'),len(raw),raw.ljust(64,b'\0'))

def golden_trace():
    out=[packet(4)]
    def box(x,y,w,h,c,a=1):out.append(packet(1,rect=(x,y,w,h),colour=(*c,a)))
    def text(x,y,s,c):out.append(packet(2,rect=(x,y,0,0),colour=(*c,1),text=s))
    f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
    mul=lambda a,b:f32(f32(a)*f32(b))
    acc=(.353,.741,.816);faint=(.435,.459,.498)
    box(10,20,200,65,(.118,.122,.133));out.append(packet(3,rect=(10,20,190,65)))
    text(18,22,'Sources',(.882,.647,.259))
    box(10,40,190,20,(mul(.353,.30),mul(.741,.30),mul(.816,.34)))
    box(10,40,2,20,acc);text(32,42,'main.avr',acc);text(138,42,'changed',faint)
    text(46,62,'an extremely lo...',(.863,)*3);text(194,62,'',faint)
    text(18,82,'Footer',(.863,)*3);out.append(packet(4))
    box(200,20,10,65,(.129,.133,.145));box(202,20,6,39,(.31,.33,.36));out.append(packet(4))
    assert len(out)==15
    return b''.join(out)

def check(report,picture,scene):
    assert scene in (1,2) and len(report)==16384
    n=len(EXPECTED);assert struct.unpack_from('<5q',report)==(0x4e4c5431,1,0,n,15),struct.unpack_from('<5q',report)
    for i,e in enumerate(EXPECTED):
        got=struct.unpack_from('<2q',report,272+i*16);assert got==(e,e),(i+1,got,e)
    assert report[3072:3091]==b'an extremely lo...\0'
    gold=golden_trace()
    for i in range(15):assert report[4096+i*128:4096+(i+1)*128]==gold[i*128:(i+1)*128],('callback',i+1,report[4096+i*128:4096+(i+1)*128].hex(),gold[i*128:(i+1)*128].hex())
    assert struct.unpack_from('<2q',report,128)==(scene,(scene-1)*2)
    font=struct.unpack_from('<q',report,56)[0];assert font>0 and font&65535==1
    h,w=struct.unpack_from('<2f',report,64);assert math.isfinite(h) and 0<h<24 and math.isfinite(w) and 0<w<=198
    raw=report[3328:3456].split(b'\0',1)[0];shown=raw.decode('utf8');source='an extremely long file name'
    assert shown==source or (shown.endswith('...') and source.startswith(shown[:-3]))
    unused=bytearray(report)
    for a,b in [(0,40),(56,72),(128,144),(272,272+n*16),(3072,3091),(3328,3329+len(raw)),(4096,4096+len(gold))]:unused[a:b]=b'\0'*(b-a)
    assert not any(unused),'unused report bytes'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    a=im.crop((40,100,540,270));b=im.crop((720,100,1220,270))
    assert max(abs(v-z) for p,q in zip(a.getdata(),b.getdata()) for v,z in zip(p,q))<=1,'pane/reference'
    assert len(set(a.getdata()))>20,'empty text pane'
    probes=0
    def pixel(x,y,c):
        nonlocal probes
        p=(math.floor(x*2+.5),math.floor(y*2+.5));assert im.getpixel(p)==c,(p,im.getpixel(p),c);probes+=1
    pixel(21,51,(30,31,34));pixel(261,51,(33,34,37));pixel(10,200,(0,0,0));pixel(40,136,(0,0,0))
    if scene==1:
        pixel(20,76,(90,189,208));pixel(265,60,(79,84,92));pixel(265,120,(33,34,37))
    else:
        pixel(265,60,(33,34,37));pixel(265,120,(79,84,92));pixel(21,76,(30,31,34))
    return dict(passed=True,checks=n,exact_callback_packets=15,full_callback_text=True,reference_pane_pixels=85000,geometry_probes=probes)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--scene',choices=['basic','scrolled'],required=True);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture,dict(basic=1,scrolled=2)[a.scene]),indent=2))
if __name__=='__main__':main()
