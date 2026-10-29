"""Exact decoded-byte, failure/guard and native RGBA sprite verification."""
from pathlib import Path
import json,struct
from PIL import Image
PLAN=json.loads((Path(__file__).with_name('neon_inflate_cases.json')).read_text(encoding='utf8'))
def check(data,png):
 assert len(data)==PLAN['report_bytes']
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 count=len(PLAN['cases']);assert [q(p) for p in [0,8,16,24,32]]==[0x4e494631,1,0,count+24,88]
 expected_ledger=[c['return_value'] for c in PLAN['cases']]+[-22900]*17+[0,0,0,1,0,0,0]
 for i,expect in enumerate(expected_ledger):assert struct.unpack_from('<2q',data,256+i*16)==(expect,expect),(i,PLAN['cases'][i]['name'] if i<count else 'argument/native',struct.unpack_from('<2q',data,256+i*16),expect)
 assert data[40:128]==data[128:216],"refused arguments mutated state"
 a5=struct.unpack('<q',b'\xa5'*8)[0];guard=struct.unpack('<q',b'\x5a'*8)[0];exact=0;cursor=16384
 for i,c in enumerate(PLAN['cases']):
  got=struct.unpack_from('<8q',data,4096+i*64);rc=c['return_value'];assert got[0]==rc,(c['name'],got,rc)
  assert got[4:]==(a5,165,guard,guard),(c['name'],'guards',got)
  assert 0<=got[1]<=c['capacity'] and 0<=got[3]<=len(bytes.fromhex(c['source']))
  assert got[2]==(0 if rc>=0 else rc),(c['name'],'state error',got)
  if rc>=0:
   expected=bytes.fromhex(c['expected']);assert got[1]==len(expected)
   assert data[c['output_offset']:c['output_offset']+len(expected)]==expected,(c['name'],'decoded bytes')
   assert c['output_offset']==cursor;cursor+=len(expected);exact+=len(expected)
 for a,b in [(216,256),(256+len(expected_ledger)*16,4096),(4096+count*64,16384),(cursor,len(data))]:assert data[a:b]==bytes(b-a),(a,b,'reserved')
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 raw=bytes.fromhex(PLAN['cases'][PLAN['pixel_case']]['expected']);pixels=im.load();compared=0
 for y in range(384):
  sy=y//12
  for x in range(768):
   sx=x//12;p=(sy*64+sx)*4;want=tuple(raw[p:p+3]);got=pixels[80+x,120+y]
   assert all(abs(a-b)<=1 for a,b in zip(got,want)),('native sprite',x,y,got,want)
   compared+=1
 for x,y in [(0,0),(79,119),(848,504),(1200,700)]:assert all(abs(a-b)<=1 for a,b in zip(pixels[x,y],(10,13,18))),(x,y,pixels[x,y])
 return dict(passed=True,cases=count,assertions=len(expected_ledger),exact_decoded_bytes=exact,native_pixels=compared,background_probes=4,png_container_supported=False)
