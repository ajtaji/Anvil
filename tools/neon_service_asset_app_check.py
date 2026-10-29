#!/usr/bin/env python3
"""Independent decoded bytes, masks, file ownership and display oracle."""
from pathlib import Path
import argparse,json,struct
from PIL import Image

def check(raw,picture):
    assert len(raw)==4096,'report length'
    q=struct.unpack('<512q',raw)
    assert q[:4]==(0x4e414531,1,0,133),('header/assertions',q[:4])
    assert q[4]>0,'live context before scoped cleanup'
    assert not any(raw[40:144]),'header padding'
    for n in range(133):
        a,e=struct.unpack_from('<qq',raw,144+16*n)
        assert a==e,('assertion',n+1,a,e)
    expected24=bytes([255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255,255,255,0,255,0,0,0,0])
    expected32=bytes([255,255,255,0,0,255,0,128,0,0,255,255,255,0,0,255])
    assert raw[2304:2328]==expected24,'bottom-up BMP24, padding and colour key'
    assert raw[2336:2342]==bytes([1,1,1,1,1,0]),'BMP24 mask'
    assert raw[2368:2384]==expected32,'top-down BMP32 straight alpha'
    assert raw[2400:2404]==bytes([0,1,1,1]),'BMP32 mask'
    occupied=set(range(144+16*133)) | set(range(2304,2328)) | set(range(2336,2342)) | set(range(2368,2384)) | set(range(2400,2404))
    assert not any(v for i,v in enumerate(raw) if i not in occupied),'report padding/tail'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    probes=[(100,120,(255,0,0)),(140,120,(0,255,0)),(180,120,(0,0,255)),(100,160,(255,255,255)),(140,160,(255,255,0)),(180,160,(0,0,255)),(320,120,(0,0,255)),(360,120,(0,128,127)),(320,160,(0,0,255)),(360,160,(255,0,0)),(40,40,(0,0,255)),(500,500,(0,0,255))]
    for x,y,c in probes:
        for dx in (-2,-1,0,1,2):
            for dy in (-2,-1,0,1,2):
                got=im.getpixel((x+dx,y+dy));assert all(abs(a-b)<=1 for a,b in zip(got,c)),('display',x+dx,y+dy,got,c)
    return dict(passed=True,assertions=133,decoded_bytes=40,mask_bytes=10,pixel_checks=len(probes)*25,scope='Pure BMP and file client plus real file-backed resident textures; PNG/JPEG not implemented')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
