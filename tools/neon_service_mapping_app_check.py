#!/usr/bin/env python3
"""Independent resident UI/world packet-ledger and raster acceptance oracle."""
from pathlib import Path
import argparse,json,struct
from PIL import Image
EXPECTED_VALUES=(
    48,64,56,48,-21501,0,0,1280,800,-21503,
    0,0,0,0,-21500,-21500,0,1,0,1,
    0,-21503,-21503,0,-21503,0,0,0,0,0,
    -21500,-21500,-21500,-21500,-21500,-21500,
)+(0,)*23
EXPECTED_CHECKS=len(EXPECTED_VALUES)

def check(report,picture):
    assert len(report)==4096,'report size'
    words=struct.unpack('<512q',report)
    assert words[:4]==(0x4e4d5031,1,0,EXPECTED_CHECKS),words[:4]
    assert words[4]>0 and words[4]&65535==1,'registered font'
    assert not any(words[5:34]),'unused report header'
    for i in range(EXPECTED_CHECKS):
        a,e=words[34+i*2:36+i*2]
        assert a==e==EXPECTED_VALUES[i],(i+1,a,e,EXPECTED_VALUES[i])
    assert not any(words[34+EXPECTED_CHECKS*2:]),'report padding'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800),im.size
    # Desktop base-canvas/camera equations, independent of native Q8 vertices.
    def expected(x,y):
        colour=(0,0,0)
        if 10<x<20 and 10<y<20:colour=(255,255,255)
        if 100<x<220 and 80<y<160:
            colour=(255,0,0)
            if abs(x-200)/60+abs(y-120)/40<1:colour=(0,255,255)
        if 200<x<280 and 160<y<200:colour=(0,255,0)
        if 320<x<340 and 280<y<300:colour=(0,0,255)
        if 500<x<530 and 50<y<70:colour=(255,255,0)
        if 380<x<400 and 100<y<140:colour=(0,0,255)
        if abs(x-680)/40+abs(y-360)/20<1:colour=(255,0,255)
        return colour
    edges_x=(10,20,100,220,200,280,320,340,500,530,380,400)
    edges_y=(10,20,80,160,200,280,300,50,70,100,140)
    samples=0
    for y in range(3,800,4):
        for x in range(3,1280,4):
            if 40<x<310 and 215<y<225:continue
            if 50<x<1210 and (490<y<580 or 640<y<740):continue
            if any(abs(x-e)<2 for e in edges_x) or any(abs(y-e)<2 for e in edges_y):continue
            if 100<x<220 and 80<y<160 and abs(abs(x-200)/60+abs(y-120)/40-1)<0.06:continue
            if abs(abs(x-680)/40+abs(y-360)/20-1)<0.08:continue
            got=im.getpixel((x,y));want=expected(x,y)
            assert max(abs(a-b) for a,b in zip(got,want))<=1,(x,y,got,want)
            samples+=1
    for x,y,want in [(15,15,(255,255,255)),(110,90,(255,0,0)),(200,120,(0,255,255)),(240,180,(0,255,0)),(330,290,(0,0,255)),(515,60,(255,255,0)),(390,120,(0,0,255)),(680,360,(255,0,255))]:
        assert im.getpixel((x,y))==want,(x,y,im.getpixel((x,y)),want)
    line=im.crop((40,215,310,225))
    white=sum(p==(255,255,255) for p in line.getdata())
    assert 240<=white<=510,white
    assert not any(p!=(0,0,0) for p in im.crop((40,250,310,270)).getdata()),'one-vertex limit emitted geometry'
    a=im.crop((60,500,500,580));b=im.crop((660,500,1100,580))
    assert a.tobytes()==b.tobytes(),'virtual text vs camera-transformed target text'
    ink=sum(p!=(0,0,0) for p in a.getdata());assert ink>300,ink
    ca=im.crop((60,650,500,730));cb=im.crop((660,650,1100,730))
    assert ca.tobytes()==cb.tobytes(),'clipped mapped text equivalence'
    clipped_ink=sum(p!=(0,0,0) for p in ca.getdata());assert 300<clipped_ink<ink,clipped_ink
    assert not any(p!=(0,0,0) for p in im.crop((160,650,500,730)).getdata()),'text escaped first scissor'
    assert not any(p!=(0,0,0) for p in im.crop((760,650,1100,730)).getdata()),'text escaped replacement scissor'
    return dict(clipped_text_ink_pixels=clipped_ink,checks=EXPECTED_CHECKS,lattice_samples=samples,static_line_white_pixels=white,text_ink_pixels=ink,passed=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture),indent=2))
if __name__=='__main__':main()
