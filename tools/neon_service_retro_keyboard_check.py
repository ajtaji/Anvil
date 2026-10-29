"""Validate scripted editing through the installed curved target service."""
import math,struct
from PIL import Image
EXPECTED=[0,0,0,0,0,1,0]+[0]*65+[3,3,65,66,90,0,1,0]
ROWS=[[2,2,1,0,0,0],[2,2,1,0,0,0],[3,3,1,0,90,0],[3,3,1,1,90,1],[3,3,0,1,90,0]]
def check(report,picture):
    assert len(report)==16384
    expected=bytearray(16384)
    for o,v in {0:0x4e524b31,8:1,24:len(EXPECTED)}.items():struct.pack_into('<q',expected,o,v)
    for i,v in enumerate(EXPECTED):struct.pack_into('<2q',expected,1024+16*i,v,v)
    for i,row in enumerate(ROWS):struct.pack_into('<6q',expected,256+48*i,*row)
    assert report==expected,'resident keyboard report differs: '+str([(i,struct.unpack_from('<q',report,i)[0],struct.unpack_from('<q',expected,i)[0]) for i in range(0,len(report),8) if report[i:i+8]!=expected[i:i+8]][:16])
    im=Image.open(picture).convert('RGB');assert im.size==(1280,800)
    assert im.crop((0,0,107,800)).getbbox() is None and im.crop((1173,0,1280,800)).getbbox() is None
    for x,y,rgb in [(680,310,(32,160,240)),(640,760,(128,128,128)),(640,400,(128,128,128))]:
        u=2*(x-107+.5)/1066-1;v=2*(y+.5)/800-1
        k=.015*(u*u+v*v);u=(u+u*k)*.5+.5;v=(v+v*k)*.5+.5
        t=max(0,min(1,(math.hypot(u-.5,v-.5)-.3)/.5));shade=1-t*t*(3-2*t)
        wanted=[max(0,min(255,(c-255*.04*math.sin(v*800))*shade)) for c in rgb]
        actual=im.getpixel((x,y));assert max(abs(a-e) for a,e in zip(actual,wanted))<=2,(x,y,actual,wanted)
    assert im.getpixel((107,0))==(0,0,0)
    ink=sum(min(p)>180 for p in im.crop((210,295,300,340)).getdata());assert ink>30,ink
    return dict(checks=len(EXPECTED),frames=5,final_text='ABZ',submissions=1,final_focus=0,scope='Scripted native input and real resident rendering; no physical input actuation')
