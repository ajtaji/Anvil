#!/usr/bin/env python3
"""Independent numeric oracle for controlled renderer output; never renders."""
import argparse,struct,json,math
from pathlib import Path
def expected_events():
    events=[]
    def event(op,x,y,w,h,r,g,b,a,extra=0):events.append((op,x,y,w,h,r,g,b,a,extra))
    def box(x,y,w,h,r,g,b,a=1):event(1,x,y,w,h,r,g,b,a)
    def text(x,y,r,g,b,ch=65):event(2,x,y,0,0,r,g,b,1,ch)
    def poly(x,y,rad,r,g,b):event(3,x,y,rad,rad,r,g,b,1,16)
    text(10,10,1,.8,.2)
    text(10,30,.4,.8,1);box(10,50,24,2,.2,.4,.8)
    box(24,74,100,30,0,0,0,.4);box(20,70,100,30,.4,.4,.4)
    box(22,72,96,26,.15,.2,.6);text(58,77,.902,.902,.902)
    text(20,118,.6,.8,1);box(20,150,200,10,.1,.1,.15)
    box(20,150,110,10,0,.8,1);box(122,140,16,30,.6,.6,.6)
    text(300,77,.8,.8,.8);box(420,75,60,20,.1,.1,.1)
    box(450,75,30,20,.2,.9,.2);box(450,75,30,20,.6,1,.6)
    text(300,114,.8,.8,.8);box(300,140,200,30,.05,.05,.05)
    for i in range(20):
        green=.8 if i<=10 else .1
        # Binary32 arithmetic matches the documented .f coordinate contract.
        seg=f32(f32(200-6)/20)
        xx=f32(f32(300+3)+f32(f32(i)*seg))
        box(xx,143,f32(seg-2),24,0,green,f32(f32(green)*f32(.5)))
    text(20,218,.8,.8,.8);box(20,240,100,70,.1,.1,.1);box(24,244,92,62,.02,.02,.02)
    for i,sx in enumerate([30,70]):
        box(sx+6,246,8,8,0,0,0);box(sx,258,20,42,0,0,0)
        box(sx+2,260,16,20,.8,.9,1);poly(sx+10,250,3,.1,1,.2)
        text(sx+6,315,.5,.5,.5,49+i)
    box(300,240,200,30,.05,.05,.05);box(298,238,204,34,0,1,1,.5)
    text(316,247,.5,.5,.5,60);text(476,247,.5,.5,.5,62);text(396,247,.902,.902,.902)
    poly(-40,-60,4,1,0,0)
    # The next draw fails on its first text call, and must emit nothing else.
    text(10,10,1,.8,.2)
    return events
def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
def check(raw):
    assert len(raw)==4096,'report length'
    words=struct.unpack('<512q',raw)
    assert words[0]==0x4e525431,'magic'
    assert words[1]==0, f'failed assertion {words[1]}'
    assert words[2]==115,'assertion coverage'
    assert words[4:9]==(41,13,3,14,1),words[4:9]
    assert words[9]==0x3154524e,'tail'
    events=expected_events();assert words[10]==len(events),(words[10],len(events))
    assert not any(raw[88:256]),'header padding'
    for i,e in enumerate(events):
        p=256+i*56;actual=struct.unpack_from('<q8fq',raw,p)
        assert actual[0]==e[0] and actual[9]==e[9],(i,actual,e)
        for a,b in zip(actual[1:9],e[1:9]):assert math.isfinite(a) and abs(a-f32(b))<=0.0001,(i,actual,e)
        assert not any(raw[p+48:p+56]),('event padding',i)
    assert not any(raw[256+len(events)*56:]),'unused report changed'
    return dict(passed=True,checks=words[2],target=words[3],boxes=words[4],texts=words[5],polygons=words[6],prepared=words[7],callbacks=words[8],ordered_events=len(events),gpu=False)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);a=ap.parse_args()
    print(json.dumps(check(a.report.read_bytes()),indent=2))
if __name__=='__main__':main()
