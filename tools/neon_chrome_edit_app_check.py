#!/usr/bin/env python3
"""Independent single-line editor ledger, complete callback and resident raster oracle."""
from pathlib import Path
import argparse,json,struct,math
from PIL import Image
EXPECTED=(56, 72, 20, 0, -22104, 0, 0, 1684107090, 0, 0, 0, 0, 1, 1, 0, 0, 11, 0, 0, -22199, -22104, 0, -22102, -22102, -22198, -22198, 0, 0, 1, 0, 0, 2, -22101, 0, 4, 4, -22100, 0, 6, 0, 4, 0, 2, 0, 0, 2, 0, 0, 0, 0, 2, 0, 1, 0, 0, 0, 2, 0, 0, 2, -22106, 0, 0, 1, 0, 4, 0, 0, 0, 1, 0, 1, 0, -22197, -22101, 0, 0, 0, -22103, 3, 0, 0, -22103, 3, 3, 1, 0, 0, -22106, 4, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

def packet(op,font=0,rect=(0,0,0,0),colour=(0,0,0,0),text=''):
    raw=text.encode('utf8');assert len(raw)<64
    return struct.pack('<qq8f8sq64s',op,font,*rect,*colour,raw[:8].ljust(8,b'\0'),len(raw),raw.ljust(64,b'\0'))

def golden_trace():
    out=[packet(4)]
    def box(x,y,w,h,c,a=1):out.append(packet(1,rect=(x,y,w,h),colour=(*c,a)))
    acc=(.353,.741,.816)
    box(10,20,200,30,(.09,.093,.102))
    box(10,20,200,1,acc);box(10,49,200,1,acc)
    box(10,21,1,28,acc);box(209,21,1,28,acc)
    out.append(packet(3,rect=(11,21,198,28)))
    box(16,27,36,16,acc,.35)
    out.append(packet(2,rect=(18,27,0,0),colour=(.863,.863,.863,1),text='Road'))
    box(50,27,1.5,16,acc);out.append(packet(4))
    assert len(out)==11
    return b''.join(out)

def check(report,picture,scene):
    assert scene in (1,2)
    assert len(report)==16384
    n=len(EXPECTED);assert struct.unpack_from('<5q',report)==(0x4e455431,1,0,n,11),struct.unpack_from('<5q',report)
    for i,e in enumerate(EXPECTED):
        got=struct.unpack_from('<2q',report,272+i*16);assert got==(e,e),(i+1,got,e)
    for pos,raw in [(3072,b'Road\0'),(3328,'é'.encode()+b'\0'),(3584,b' B\0')]:assert report[pos:pos+len(raw)]==raw,('edited-text',pos,report[pos:pos+len(raw)],raw)
    gold=golden_trace()
    for i in range(11):assert report[4096+i*128:4096+(i+1)*128]==gold[i*128:(i+1)*128],('callback',i+1)
    assert struct.unpack_from('<q',report,128)[0]==scene
    font=struct.unpack_from('<q',report,56)[0];assert font>0 and font&65535==1
    h,w,c=struct.unpack_from('<3f',report,64)
    assert all(math.isfinite(v) for v in (h,w,c)) and 0<h<34 and 50<w<230 and c==w
    unused=bytearray(report)
    for a,b in [(0,40),(56,76),(128,136),(272,272+n*16),(3072,3077),(3328,3331),(3584,3587),(4096,4096+len(gold))]:unused[a:b]=b'\0'*(b-a)
    assert not any(unused),'unused report bytes'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    total=0
    for y,width in [(50,250),(110,250),(170,90)]:
        a=im.crop((40,y*2,(20+width)*2,(y+34)*2));b=im.crop((720,y*2,(360+width)*2,(y+34)*2))
        assert max(abs(v-z) for p,q in zip(a.getdata(),b.getdata()) for v,z in zip(p,q))<=1,('field/reference',y)
        assert len(set(a.getdata()))>10,('empty text',y)
        total+=width*2*68
    probes=0
    def pixel(x,y,colour):
        nonlocal probes
        p=(math.floor(x*2+.5),math.floor(y*2+.5));assert im.getpixel(p)==colour,(p,im.getpixel(p),colour);probes+=1
    pixel(20,50,(90,189,208));pixel(20,110,(50,51,54));pixel(20,170,(50,51,54))
    pixel(25,55,(23,24,26));pixel(111,180,(0,0,0));pixel(10,200,(0,0,0))
    pixel(28+w+.5,50+(34-h)/2+h/2,(90,189,208))
    if scene==2:
        p=(52,math.floor((50+(34-h)/2+1)*2+.5));assert im.getpixel(p)!=(23,24,26),'missing selection'
    return dict(passed=True,checks=n,exact_callback_packets=11,full_callback_text=True,reference_field_pixels=total,geometry_probes=probes)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--scene',choices=['basic','selection'],required=True);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture,dict(basic=1,selection=2)[a.scene]),indent=2))
if __name__=='__main__':main()
