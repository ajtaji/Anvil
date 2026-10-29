"""Check the native target dispatcher and its captured CRT output."""
import math
import struct
from PIL import Image

EXPECTED = [0,0,0,1,-21503,-21500,-21506,-21342,0,0,0,0,0,0,0,
            -21503,0,-21503,-21500,-21500,0,0,0,1,1,1,1,1,1,0,0]

def check(report, picture):
    assert len(report)==16384
    expected=bytearray(16384)
    for offset,value in {0:0x4e434431,8:2,24:len(EXPECTED)}.items():
        struct.pack_into('<q',expected,offset,value)
    for i,value in enumerate(EXPECTED):
        struct.pack_into('<2q',expected,1024+i*16,value,value)
    assert report==expected, 'dispatcher report differs: '+str([
        (i,struct.unpack_from('<q',report,i)[0],struct.unpack_from('<q',expected,i)[0])
        for i in range(0,len(report),8) if report[i:i+8]!=expected[i:i+8]][:12])
    count=check_picture(picture)
    return dict(checks=len(EXPECTED),pixel_samples=count,scope='Native GPU target dispatcher; not installed resident service')

def check_picture(picture):
    im=Image.open(picture).convert('RGB')
    assert im.size==(1280,800)
    assert im.crop((0,0,240,800)).getbbox() is None
    assert im.crop((1040,0,1280,800)).getbbox() is None
    count=0
    for x in [240,250,280,320,440,639,800,960,1000,1039]:
        for y in [0,10,40,80,200,399,560,720,760,799]:
            u=2*(x-240+.5)/800-1; v=2*(y+.5)/800-1
            k=.015*(u*u+v*v); u=(u+u*k)*.5+.5; v=(v+v*k)*.5+.5
            values=[0,0,0]
            if 0<=u<=1 and 0<=v<=1:
                t=max(0,min(1,(math.hypot(u-.5,v-.5)-.3)/.5))
                values=[max(0,(c-255*.04*math.sin(v*800-1.25))*(1-t*t*(3-2*t))) for c in [26,26,230]]
            rgb=im.getpixel((x,y))
            assert max(abs(c-value) for c,value in zip(rgb,values))<=2,(x,y,rgb,values)
            count+=1
    return count
