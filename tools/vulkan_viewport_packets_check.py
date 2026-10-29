"""Independent full-report oracle for viewport packet transitions."""
import struct,hashlib
BASE=(0,0,80,60,1,0)
SCENES=[
 [BASE], [BASE,BASE], [BASE,(1,0,80,60,1,0)], [BASE,(0,1,80,60,1,0)],
 [BASE,(2,3,80,60,1,0),BASE],
 [BASE,(0,0,81,60,1,0),(0,0,81,61,1,0)],
 [BASE,(8,9,40,30,0,0),BASE],
 [BASE,(8,9,40,30,0,0),(8,9,40,30,1,0)],
 [BASE,(0,0,1,1,1,1),BASE],
 [(8,9,40,30,0,0),(0,0,1,1,1,1),(8,9,40,30,1,0)],
 [(0,0,32767,32767,1,0),(32766,32766,1,1,1,0)],
 [BASE,(1,0,78,60,1,0),(1,0,78,60,1,0),(1,1,78,58,1,0)],
]
def expected():
 b=bytearray([0xa5]*8192);struct.pack_into('<Q',b,0,0x56505431)
 for i,scene in enumerate(SCENES):
  new=old=0;vp=None;dims=None;fixed=False;clip=True;events=[]
  for x,y,w,h,mask,clear in scene:
   if clear:
    new+=128;old+=128;vp=dims=None;fixed=False;clip=False;continue
   if not mask:continue
   new+=15;old+=15
   if not fixed:new+=11;old+=11;fixed=True
   if not clip:new+=9;old+=9;clip=True
   if (w,h)!=dims:old+=18;dims=w,h
   if (x,y,w,h)!=vp:
    new+=18;vp=x,y,w,h
    bits=lambda n:struct.unpack('<I',struct.pack('<f',n))[0]
    events.append((bits(w*128),bits(h*128),x*256+w*128,y*256+h*128))
  start=256+i*512;struct.pack_into('<QQQ',b,start,new,old,len(events))
  for k,event in enumerate(events):struct.pack_into('<4Q',b,start+64+k*32,*event)
 return bytes(b)
def check(report):
 e=expected();assert len(report)==8192,len(report)
 if report!=e:
  first=next(i for i,(a,b) in enumerate(zip(report,e)) if a!=b)
  raise AssertionError(f'report differs at {first:#x}: got {report[first]:02x}, expected {e[first]:02x}')
 return dict(cases=12,bytes=8192,sha256=hashlib.sha256(report).hexdigest(),old_origin_undercount_reproduced=True)
