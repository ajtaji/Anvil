#!/usr/bin/env python3
"""Independent desktop button formulas, full callback packets and native references."""
import struct,math
from PIL import Image,ImageChops
EXPECTED=[144, 56, -22804, -22804, 0, -22804, 195, 169, 0, 0, 1088421888, 0, -22801, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -22800, 1, -22800, 0, -22806, 5, -22806, -22800, 0, -22898, 0, -22805, 0, -22804, -22899, -22802, -22802, -22802, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1065353216, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -22702, -22702, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, -22800, -22800, 0, 0, 0, 0, 0, 0, 28, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
LABELS=['Drive','Route','Unavailable','Confirm']
def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
def records(widths,heights,hover,font):
 result=[]
 def box(x,y,w,h,rgb,a=1.):result.append((1,0,(x,y,w,h),(*rgb,a),''))
 for i,label in enumerate(LABELS):
  x=20.;y=50.+i*70;h=hover[i];body=[.196,.200,.212];text=[.863]*3
  if i==1:body=[.157,.365,.408];text=[.588,.816,.867]
  if i==2:text=[.435,.459,.498]
  if h>0:
   for radius in range(1,5):box(x-radius,y-radius,280+radius*2,36+radius*2,(.353,.741,.816),.16*h/(radius*1.5))
   body=[body[c]+[.06,.07,.08][c]*h for c in range(3)]
  box(x,y,280,36,body);box(x,y,280,1,(.216,.259,.325));box(x,y+35,280,1,(.129,.133,.145))
  result.append((2,font,(x+(280-widths[i])/2,y+(36-heights[i])/2,0.,0.),(*text,1.),label))
 for radius in range(1,5):box(20-radius,335-radius,280+radius*2,32+radius*2,(.7,.5,.2),.12/(radius*1.5))
 box(20,335,280,1,(.7,.5,.2));box(20,366,280,1,(.7,.5,.2));box(20,335,1,32,(.7,.5,.2));box(299,335,1,32,(.7,.5,.2))
 return result

def check(report,png):
 assert len(report)==16384
 q=lambda p:struct.unpack_from('<q',report,p)[0]
 assert q(0)==0x4e425431 and q(8) in [1,2] and q(16)==0 and q(24)==len(EXPECTED)
 assert q(32)==q(40)==28 and q(48)>0 and q(56)==0
 assert 0x1080000<=q(64)<=0x1090000 and q(64)%8==0 and q(72)==q(80)==0 and q(88)==1
 for i,v in enumerate(EXPECTED,1):assert struct.unpack_from('<2q',report,256+i*16)==(v,v),(i,struct.unpack_from('<2q',report,256+i*16),v)
 widths=[];heights=[];hovers=[]
 for i in range(4):
  p=128+i*24;v=struct.unpack_from('<3f',report,p);assert all(math.isfinite(x) for x in v) and report[p+12:p+16]==bytes(4) and q(p+16)==i+1
  width,height,hover=v;assert 0<width<280 and 0<height<36
  want=0. if i<3 else 1. if q(8)==1 else 1-math.exp(-.9)
  assert abs(hover-want)<.000001,(i,hover,want)
  widths.append(width);heights.append(height);hovers.append(hover)
 for base,plan in [(8192,records([35,35,77,49],[16]*4,[0,0,0,1],1)),(12288,records(widths,heights,hovers,q(48)))]:
  assert len(plan)==28
  for i,(op,font,geometry,rgba,text) in enumerate(plan):
   p=base+i*128;assert q(p)==op and q(p+8)==font
   actual=struct.unpack_from('<8f',report,p+16);assert all(math.isfinite(v) for v in actual)
   assert all(abs(a-b)<.0001 for a,b in zip(actual[:4],geometry)),(base,i,'geometry',actual[:4],geometry)
   assert all(abs(a-b)<.000001 for a,b in zip(actual[4:],rgba)),(base,i,'colour',actual[4:],rgba)
   raw=text.encode();assert q(p+48)==len(raw) and q(p+56)==0 and report[p+64:p+128]==raw+bytes(64-len(raw))
 for a,b in [(96,128),(224,272),(272+len(EXPECTED)*16,8192),(11776,12288),(15872,16384)]:assert report[a:b]==bytes(b-a),(a,b)
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 checked=0;worst=0
 for rect in [(32,92,608,604),(32,662,608,742)]:
  x,y,xx,yy=rect;delta=ImageChops.difference(im.crop(rect),im.crop((x+640,y,xx+640,yy)));maximum=max(v[1] for v in delta.getextrema());assert maximum<=1,(rect,maximum);worst=max(worst,maximum);checked+=(xx-x)*(yy-y)
 probes=[(25,83,(10,13,18)),(295,60,(10,13,18)),(30,65,(50,51,54)),(30,135,(40,93,104)),(30,205,(50,51,54)),(21,335,(179,128,51))]
 hover=hovers[3];probes.append((30,275,tuple(round((v+factor*hover)*255) for v,factor in zip([.196,.2,.212],[.06,.07,.08]))))
 for x,y,want in probes:
  got=im.getpixel((x*2,y*2));assert all(abs(a-b)<=1 for a,b in zip(got,want)),(x,y,got,want)
 return dict(passed=True,scene=q(8),checks=len(EXPECTED),fake_packets=28,native_packets=28,reference_pixels=checked,maximum_channel_error=worst,probes=len(probes))
