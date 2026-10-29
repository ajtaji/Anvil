#!/usr/bin/env python3
"""Independent particle ledger, capacity raster and desktop transform oracle."""
from pathlib import Path
import argparse,json,struct,math
from PIL import Image

SCENE=[(100.25,100.75,46.5,0,(255,0,0),255),(250.5,100.25,63.5,.4,(0,255,0),255),(400.25,100.75,80,0,(0,0,255),255),(410.75,110.25,70.5,0,(255,0,0),128),(540.5,120.5,.001,0,(255,255,0),255),(1200.25,760.75,100.5,.55,(0,255,255),255),(600,350,160,.125,(255,255,0),191),(640,340,100,-.7,(255,0,255),128),(-15.25,200,80,-.4,(0,255,255),255),(1100,100,12.25,math.pi/2,(255,255,255),255)]

def check(raw,picture,scene='mixed'):
    assert len(raw)==4096,'report length'
    q=struct.unpack('<512q',raw);dense=scene=='dense';count=39 if dense else 58
    assert q[:5]==(0x4e505031,1,0,count,1 if dense else 2),('header/checks',q[:5])
    for n in range(count):
        a,e=struct.unpack_from('<qq',raw,272+16*n)
        assert a==e,('check',n+1,a,e)
    for n in range(8,12):assert 0<q[n]<5000000,('timing',n,q[n])
    assert 0<q[13]<5000000,'warm preparation time'
    if not dense:assert 0<q[12]<5000000,'mixed preparation time'
    used=set(range(40))|set(range(64,96 if dense else 104))|set(range(104,112))|set(range(272,272+count*16))
    assert not any(v for i,v in enumerate(raw) if i not in used),'report padding'
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    if dense:
        expected=Image.new('RGB',(1280,800))
        for row in range(100):
            for col in range(100):expected.paste((255,0,0),(99+10*col,99+5*row,102+10*col,102+5*row))
        assert im.tobytes()==expected.tobytes(),'10000 copied fractional quads'
        pixels=1280*800
    else:
        pixels=0
        # Compare a regular screen lattice except a narrow edge band. This
        # uses desktop centre/rotation geometry, not the renderer's Q8 code.
        for y in range(2,800,3):
            for x in range(2,1280,3):
                out=(0,0,0);edge=False
                for cx,cy,size,angle,colour,alpha in SCENE:
                    c=math.cos(angle);s=math.sin(angle);dx=x+.5-cx;dy=y+.5-cy
                    u=c*dx+s*dy;v=-s*dx+c*dy;half=size*.5
                    if abs(abs(u)-half)<.2 and abs(v)<half+.2 or abs(abs(v)-half)<.2 and abs(u)<half+.2:edge=True
                    if abs(u)<half and abs(v)<half:
                        out=tuple((src*alpha+dst*(255-alpha)+127)//255 for src,dst in zip(colour,out))
                if not edge:
                    got=im.getpixel((x,y));assert all(abs(a-b)<=1 for a,b in zip(got,out)),('desktop transform/order',x,y,got,out)
                    pixels+=1
        assert im.getpixel((77,90))==(255,0,0),'fractional camera must not round to whole pixels'
        assert im.getpixel((400,100))==(128,0,127),'ordered source-alpha overlap'
        assert im.getpixel((540,120))==(0,0,0),'subpixel-degenerate particle must add no ink'
    return dict(passed=True,scene=scene,assertions=count,checked_pixels=pixels,list_build_us=q[8],dense_prepare_us=q[9],dense_warm_prepare_us=q[13],dense_draw_cpu_us=q[10],dense_frame_us=q[11],mixed_prepare_us=q[12] if not dense else None,scope='Actual resident particles;10000 copied records or fractional/camera/rotation/order/clip scene;CPU timing includes waits where called')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--picture',type=Path,required=True);ap.add_argument('--scene',choices=['dense','mixed'],required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),a.picture,a.scene),indent=2))
if __name__=='__main__':main()
