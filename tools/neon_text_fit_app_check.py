"""Exact UTF8 corpus checks and independent native prefix enumeration/pixels."""
from pathlib import Path
import json,struct,math,argparse,tempfile
from PIL import Image,ImageChops
PLAN=json.loads(Path(__file__).with_name('neon_text_fit_cases.json').read_text(encoding='utf8'))
def check(data,png):
 assert len(data)==65536
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 f=lambda p:struct.unpack_from('<f',data,p)[0]
 checks=[0]+[c['rc'] for c in PLAN['cases']]+[0,-23105,-23100,0,-23100,-23100,-23100,-23100,-23100,-23102,-23103,-23103,-23104,-23104,3,1]+[0,0,0,1,0,0,0,1,1,0,0,0,0,0]
 want=bytearray(65536);struct.pack_into('<4q',want,0,0x4e465431,1,0,len(checks))
 for i,v in enumerate(checks):struct.pack_into('<2q',want,256+i*16,v,v)
 want[4096:4240]=b'\xa5'*144
 for i,c in enumerate(PLAN['cases']):
  at=8192+i*512;src=bytes.fromhex(c['source']);tail=bytes.fromhex(c['marker'])
  struct.pack_into('<4q',want,at,c['rc'],c['capacity'],len(src),len(tail))
  struct.pack_into('<f',want,at+32,c['room']);want[at+40:at+56]=b'\x3c'*16
  raw=bytearray(b'\xa5'*144)
  if c['rc']>=0:
   output=bytes.fromhex(c['output']);assert len(output)==c['rc']+1
   raw[8:8+len(output)]=output
  want[at+64:at+208]=raw
 # Native font metrics are runtime values. Enumerate every possible ASCII
 # prefix independently; no binary-search or UTF8-prefix production helper.
 at=49152;s=PLAN['native_source'].encode();n=len(s);room=PLAN['native_room']
 assert q(at+8)==n and q(at+16)>3 and math.isfinite(f(at+24)) and f(at+24)>room
 widths=[f(at+512+i*4) for i in range(n)]
 assert all(math.isfinite(v) and 0<=v<=16777216 for v in widths)
 viable=[len(s[:i].rstrip(b' ')) for i,v in enumerate(widths) if v<=room];assert viable
 best=max(viable);text=s[:best]+b'...';assert q(at)==len(text) and q(at+32)==best
 assert math.isfinite(f(at+28)) and 0<=f(at+28)<=room
 assert abs(f(at+28)-widths[best])<0.01
 native=bytearray(128);native[:len(text)+1]=text+b'\0'
 reference=bytearray(128);last=s[:-1].rstrip(b' ')+b'...\0';reference[:len(last)]=last
 reference[:len(text)+1]=text+b'\0'
 assert data[at+64:at+192]==native and data[at+256:at+384]==reference
 # Admit only the individually validated dynamic fields, not arbitrary padding.
 for a,b in [(at,at+40),(at+64,at+192),(at+256,at+384),(at+512,at+512+n*4)]:want[a:b]=data[a:b]
 if data!=want:
  pos=next(i for i,(a,b) in enumerate(zip(data,want)) if a!=b)
  raise AssertionError(f'report byte{pos}: got{data[pos]:02x}, expected{want[pos]:02x}')
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 left=im.crop((40,160,600,224));right=im.crop((680,160,1240,224))
 extrema=ImageChops.difference(left,right).getextrema();assert all(v[1]==0 for v in extrema),extrema
 ink=sum(1 for pixel in left.getdata() if max(pixel)-min(pixel)<5 and min(pixel)>32);assert ink>100,ink
 for xy in [(0,0),(1200,700)]:assert all(abs(a-b)<=1 for a,b in zip(im.getpixel(xy),(10,13,18)))
 return dict(passed=True,cases=len(PLAN['cases']),assertions=len(checks),native_prefixes=n,matched_native_pixels=560*64,native_ink_pixels=ink,fitted_text=text.decode(),max_pixel_error=0)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--png',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args();data=a.report.read_bytes();result=check(data,a.png)
 if a.self_test:
  positions=[0,8,16,24,4096,4239,65535]
  positions.extend(256+i*16 for i in range(result['assertions']))
  positions.extend(8192+i*512+n for i in range(len(PLAN['cases'])) for n in [0,8,40,48,64,72,200,207,511])
  count=0
  for p in positions:
   bad=bytearray(data);bad[p]^=1
   try:check(bad,a.png)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted report mutation',p))
  bad=bytearray(data);struct.pack_into('<I',bad,49152+512,0x7fc00000)
  try:check(bad,a.png)
  except AssertionError:count+=1
  else:raise AssertionError('accepted NaN native metric')
  try:check(data[:-1],a.png)
  except AssertionError:count+=1
  else:raise AssertionError('accepted report truncation')
  with tempfile.TemporaryDirectory() as d:
   for xy in [(40,160),(680,160),(0,0)]:
    im=Image.open(a.png).convert('RGB');old=im.getpixel(xy);im.putpixel(xy,tuple(v^128 for v in old));p=Path(d)/'mutant.png';im.save(p)
    try:check(data,p)
    except AssertionError:count+=1
    else:raise AssertionError(('accepted pixel mutation',xy))
  result['rejected_corruptions']=count
 print(json.dumps(result,indent=2))
