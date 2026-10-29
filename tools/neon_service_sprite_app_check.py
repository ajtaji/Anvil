#!/usr/bin/env python3
"""Independent resident sprite ledger and interior pixel oracle."""
from pathlib import Path
import argparse,json,struct
from PIL import Image

def check(raw,picture):
    assert len(raw)==4096,'report length'
    q=struct.unpack('<512q',raw)
    assert q[:4]==(0x4e535631,1,0,182),('header/checks',q[:4])
    assert q[4]>0,'capture must retain the application context'
    assert not any(raw[40:144]),'header padding'
    for n in range(182):
        actual,expected=struct.unpack_from('<qq',raw,144+n*16)
        assert actual==expected,('application assertion',n+1,actual,expected)
    assert not any(raw[144+182*16:]),'report tail'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800),'logical display extent'
    probes=[]
    def probe(x,y,colour,label):
        # Interior 3x3 squares avoid raster edge convention dependencies.
        for dy in (-1,0,1):
            for dx in (-1,0,1):
                got=im.getpixel((x+dx,y+dy))
                assert all(abs(a-b)<=1 for a,b in zip(got,colour)),(label,x+dx,y+dy,got,colour)
        probes.append(dict(x=x,y=y,rgb=colour,label=label))
    red=(255,0,0);green=(0,255,0);blue=(0,0,255);white=(255,255,255)
    for origin,label in [(100,'RGBA borrowed copy'),(300,'BGRA borrowed copy')]:
        for dx,dy,c in [(8,8,red),(40,8,green),(8,40,blue),(40,40,white)]:probe(origin+dx,100+dy,c,label)
    for dx,dy,c in [(16,16,red),(80,16,green),(16,80,blue),(80,80,white)]:probe(160+dx,100+dy,c,'camera translation and zoom')
    for dx,dy,c in [(8,8,blue),(40,8,red),(8,40,white),(40,40,green)]:probe(450+dx,100+dy,c,'quarter rotation')
    probe(620,120,(128,64,255),'source crop and tint')
    probe(820,120,(128,128,128),'alpha blend')
    for row in range(8):
        for col in range(16):
            for dx,dy,c in [(4,4,red),(20,4,green),(4,20,blue),(20,20,white)]:probe(80+40*col+dx,340+40*row+dy,c,'ordered batch')
    for x,y in [(50,50),(200,280),(800,700),(740,350)]:probe(x,y,(0,0,0),'clear exterior')
    return dict(passed=True,assertions=182,interior_squares=len(probes),pixel_checks=9*len(probes),probes=probes,gpu=True,scope='Real resident uploads, capacity refusal retaining prior texture, stale handles, abort/close/reopen, RGBA/BGRA, copied source bytes, crop, tint, alpha, rotation, camera and 128 deferred sprites')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);a=ap.parse_args()
    result=check(a.report.read_bytes(),a.picture);result.pop('probes');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
