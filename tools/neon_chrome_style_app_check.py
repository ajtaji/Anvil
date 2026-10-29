#!/usr/bin/env python3
"""Independent shared-palette, callback-equivalence and native-raster oracle."""
import struct,math
from PIL import Image
DEFAULT=[(.129,.133,.145),(.145,.149,.161),(.169,.173,.184),(.196,.200,.212),(.863,.863,.863),(.576,.596,.635),(.435,.459,.498),(.353,.741,.816),(.882,.647,.259),(.361,.749,.596),(.867,.494,.494),(.663,.596,.878),(.118,.122,.133),(.09,.093,.102),(.31,.33,.36)]
def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
def check(report,png):
 assert len(report)==16384
 q=lambda o:struct.unpack_from('<q',report,o)[0]
 assert q(0)==0x4e535431 and q(8)==1 and q(16)==0
 # Pin every expected ledger value, independently of the runtime-written expectation.
 expected=[180,0,0,0,0,1,-22400,-22400,-22400,-22400]+[-22400]*45
 expected += [1,0,0,2,0,struct.unpack('<I',struct.pack('<f',.1))[0],-22400,0,0,3,0,3]
 expected += [0]*4+[0]*23
 expected += [0,struct.unpack('<I',struct.pack('<f',1.0))[0],0,0,struct.unpack('<I',struct.pack('<f',1.0))[0],0,0,struct.unpack('<I',struct.pack('<f',1.0))[0]]
 # Reentrant draw emits four busy assertions before the enclosing draw result.
 expected += [-22401]*4+[0,1,0,-22499,0,-22104,0,0,0]+[0,0,0,0,1,0,0,0]+[0,0,0,1]
 expected += [0]*23+[0]+[0]*4+[0,0]+[0]*23+[0]+[0]*4+[0,0,0]
 assert q(24)==len(expected),(q(24),len(expected))
 for i,want in enumerate(expected,1):
  assert struct.unpack_from('<2q',report,256+i*16)==(want,want),(i,struct.unpack_from('<2q',report,256+i*16),want)
 assert q(48)==0 and q(56)>0 and q(64)>3
 default=struct.unpack_from('<45f',report,14400);custom=struct.unpack_from('<45f',report,14592)
 assert default==tuple(f32(c) for rgb in DEFAULT for c in rgb)
 custom_expected=[f32(f32(.1)+f32(f32(i)*f32(.01))) for i in range(45)]
 custom_expected[12:15]=map(f32,[.9,.95,1]);custom_expected[21:24]=map(f32,[.8,.45,.95])
 assert all(abs(a-b)<1e-7 for a,b in zip(custom,custom_expected))
 n=q(40);assert 20<n<80 and q(32)==n*2
 colourpairs=[(tuple(map(f32,a)),custom[j*3:j*3+3]) for j,a in enumerate(DEFAULT)]
 colourpairs += [(tuple(f32(f32(DEFAULT[7][c])*f32(k)) for c,k in enumerate([.30,.30,.34])),tuple(f32(custom[21+c]*f32(k)) for c,k in enumerate([.30,.30,.34])))]
 for i in range(n):
  a=4096+i*64;b=a+n*64
  assert report[a:a+16]==report[b:b+16] and report[a+48:a+64]==bytes(16)==report[b+48:b+64]
  op=q(a);assert op in [1,2,3,4]
  assert q(a+8)==(q(56) if op==2 else 0)
  av=struct.unpack_from('<8f',report,a+16);bv=struct.unpack_from('<8f',report,b+16)
  assert all(math.isfinite(v) for v in av+bv)
  if op==4:assert av==bv==(0.,)*8
  if op==3:assert av[4:]==bv[4:]==(0.,)*4
  if op in [1,3]:assert av[2]>0 and av[3]>0
  assert abs(bv[0]-av[0]-(0 if op==4 else 310))<.0002
  assert av[1:4]==bv[1:4] and av[7]==bv[7]
  if op in [1,2]:
   matching=[new for old,new in colourpairs if all(abs(av[4+c]-old[c])<1e-6 for c in range(3))]
   assert matching,(i,av)
   assert any(all(abs(bv[4+c]-new[c])<1e-6 for c in range(3)) for new in matching),(i,av,bv)
  else:assert av[4:]==bv[4:]
 assert report[4096+q(32)*64:14336]==bytes(14336-4096-q(32)*64)
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 probes=[(30,30,DEFAULT[2]),(80,30,DEFAULT[7]),(600,30,custom[6:9]),(600,70,custom[0:3]),(600,120,custom[39:42]),(600,235,custom[36:39]),(331,180,custom[21:24])]
 for x,y,rgb in probes:
  actual=im.getpixel((x*2,y*2));want=tuple(round(c*255) for c in rgb)
  assert all(abs(a-b)<=1 for a,b in zip(actual,want)),(x,y,actual,want)
 ink=sum(1 for y in range(202,258) for x in range(676,1150) if all(abs(a-b)<=1 for a,b in zip(im.getpixel((x,y)),(230,242,255))))
 assert ink>100,ink
 return dict(text_ink_pixels=ink,passed=True,checks=len(expected),packets=n*2,palette_fields=45,geometry_translation=310,native_probes=len(probes))
