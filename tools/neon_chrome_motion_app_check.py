#!/usr/bin/env python3
"""Independent easing schedule, drawn hover-map and native image verifier."""
import struct,math
from PIL import Image
PREFIX=[32, 40, 0, -22601, 0, -22601, 0, 1088421888, -22601, 0, 0, 1, 1, 0, 0, 0, 1, 0, 1, -22602, 1, -22600, -22600, -22600, -22603, 0, 0, 2, 0, 0, 0, 0, 0, 1, 1082130432, 0, 0, 1090519040, 0, 0, -22600, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 1, 2, 0, 0, 1, 0, 0, 1, 2, 0, 1, 0, 0, 0, 0, -22702, 3, -22702, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -22701, 0, -22702, -22702, 0, 0, 0, 0, 0, -22401, -22401, -22401, -22401, -22703, -22703, -22703, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
def check(report,png):
 assert len(report)==16384
 q=lambda p:struct.unpack_from('<q',report,p)[0]
 scene=q(8);assert scene in [1,2,3]
 expected=PREFIX+([0] if scene==2 else [])+[0]*240+[1,9,1,10,5,0]+([0,1,3,11,0] if scene==2 else [])+([1,11,1,1,6,1,1,8,99] if scene==3 else [])+[0]
 assert [q(p) for p in [0,16,24,32,40,48,56]]==[0x4e4d5231,0,len(expected),60,{1:44,2:66,3:51}[scene],{1:10,2:12,3:13}[scene],540 if scene==3 else 480]
 for i,v in enumerate(expected,1):assert struct.unpack_from('<2q',report,256+i*16)==(v,v),(i,struct.unpack_from('<2q',report,256+i*16),v)
 owners=[q(p) for p in [64,72,80,88,96]];assert len(set(owners))==5 and all(0x1080000<=a<=0x1090000 and a%8==0 for a in owners)
 assert q(104)>0 and 60*33333<=q(112)<6000000
 current=f32(20);blend=f32(1-f32(math.exp(f32(-8*f32(1/30)))))
 for i in range(60):
  p=12032+i*24;value,target=struct.unpack_from('<2f',report,p);want=100 if i<20 else 300 if i<40 else 180
  current=f32(current+f32(f32(want-current)*blend))
  if abs(want-current)<.002:current=f32(want)
  assert math.isfinite(value) and abs(value-current)<.0004 and target==want,(i,value,current,target)
  assert q(p+8)==int(current!=want) and q(p+16)==q(48)
  assert 0<q(13600+i*8)<1000000
 for i in range(q(40)):
  p=7168+i*64;op=q(p);assert op in [1,2,3,4] and q(p+8)==(q(104) if op==2 else 0)
  v=struct.unpack_from('<8f',report,p+16);assert all(math.isfinite(x) for x in v)
  assert report[p+48:p+64]==bytes(16)
  if op in [1,3]:assert v[2]>0 and v[3]>0
  if op in [3,4]:assert v[4:]==(0.,)*4
  if op==4:assert v==(0.,)*8
 records=[]
 for i in range(q(48)):
  p=14592+i*40;identity=struct.unpack_from('<3q',report,p);rect=struct.unpack_from('<4f',report,p+24);assert all(math.isfinite(v) for v in rect) and rect[2]>0 and rect[3]>0;records.append((identity,rect))
 tabcount=4 if scene==3 else 2
 identities=([(5,owners[1],1),(6,owners[1],1),(5,owners[1],2),(11,owners[1],1)] if scene==3 else [(5,owners[1],1),(5,owners[1],2)])
 identities += [(9,owners[2],1)]+[(10,owners[3],i) for i in range(1,6)]+[(7,owners[4],900010)]
 if scene==3:identities += [(8,owners[4],99)]
 identities += [(2,owners[0],10)]
 if scene==2:identities += [(0,0,0),(3,owners[0],11)]
 assert [a for a,b in records]==identities
 if scene==3:
  first,close,second,arrow=[r for a,r in records[:4]]
  assert first[0:2]==(24.,55.) and first[3]==29 and 50<first[2]<100
  assert second[0]==first[0]+first[2] and second[1]==55 and second[3]==29 and 0<second[2]<first[2]
  assert arrow[1]==55 and arrow[3]==29 and 22<=arrow[2]<=33 and abs(arrow[0]+arrow[2]-160)<.0001
  assert abs(second[0]+second[2]-arrow[0])<.0001
  side=arrow[2]-4
  assert abs(close[0]-(first[0]+first[2]-side-1))<.0001 and abs(close[2]-side)<.0001 and abs(close[3]-side)<.0001
 else:
  for i in range(2):
   x,y,width,height=records[i][1];assert abs(y-55)<.0001 and height==29 and 40<width<160
   assert abs(x-(24 if i==0 else records[0][1][0]+records[0][1][2]))<.0001
 assert records[tabcount][1]==(20.,100.,290.,30.)
 for i in range(5):assert records[tabcount+1+i][1]==(20.,145.+24*i,280.,24. if i<4 else 4.)
 x,y,width,height=records[tabcount+6][1];assert (x,y,width)==(302.,145.,6.) and abs(height-100*4/6)<.0001
 if scene==3:assert records[11][1]==(20.,262.,58.,8.)
 root=12 if scene==3 else 9
 x,y,width,height=records[root][1];assert (x,y,height)==(28.,20.,26.) and 20<width<100
 if scene==2:
  block=records[10][1];row=records[11][1];assert block[0:2]==(28.,46.) and block[3]==56 and 100<block[2]<280
  assert row==(block[0],50.,block[2],24.)
 for a,b in [(120,272),(272+len(expected)*16,7168),(7168+q(40)*64,12032),(13472,13600),(14080,14592),(14592+q(48)*40,16384)]:assert report[a:b]==bytes(b-a),(a,b)
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 probes=[(600,350,(0,0,0)),(190,310,(51,204,255)),(280,120,(23,24,26)),(280,235,(30,31,34)),(300,30,(43,44,47))]
 for x,y,want in probes:
  got=im.getpixel((x*2,y*2));assert all(abs(a-b)<=1 for a,b in zip(got,want)),(x,y,got,want)
 ink=sum(min(im.getpixel((x,y)))>150 for y in range(210,252) for x in range(56,550));assert ink>100
 return dict(passed=True,scene=scene,checks=len(expected),ends=60,packets=q(40),regions=q(48),easing_samples=60,image_probes=len(probes),field_ink_pixels=ink,frame_work_max_us=max(q(13600+i*8) for i in range(60)))
