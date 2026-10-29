"""Exact scalar-column corpus and native prefix/caret composition oracle."""
from pathlib import Path
import json,struct,math,argparse,tempfile
from PIL import Image,ImageChops
PLAN=json.loads(Path(__file__).with_name('neon_text_column_cases.json').read_text(encoding='utf8'))
F=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
def check(data,png):
 assert len(data)==32768
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 f=lambda p:struct.unpack_from('<f',data,p)[0]
 want=bytearray(32768);checks=PLAN['checks']
 struct.pack_into('<4q',want,0,0x4e434c31,1,0,len(checks))
 for i,v in enumerate(checks):struct.pack_into('<2q',want,256+i*16,v,v)
 for i,c in enumerate(PLAN['cases']):
  p=8192+i*160;struct.pack_into('<q',want,p,c['rc'])
  raw=bytearray(b'\xa5'*32)
  if c['result'] is not None:struct.pack_into('<qfI',raw,8,*c['result'],0)
  want[p+8:p+40]=raw;want[p+40:p+56]=b'\x3c'*16
  src=bytes.fromhex(c['source']);want[p+64:p+64+len(src)]=src
 for i in range(PLAN['extra_refusals']):want[23040+i*32:23072+i*32]=b'\xa5'*32
 p=24576;n=PLAN['native_count']
 assert q(p)>3
 struct.pack_into('<q',want,p,q(p))
 widths=[f(p+64+i*4) for i in range(n+1)]
 assert widths[0]==0 and all(math.isfinite(x) and 0<=x<=16777216 for x in widths)
 assert all(a<b for a,b in zip(widths,widths[1:])),widths
 for i,x in enumerate(widths):
  struct.pack_into('<f',want,p+64+i*4,x)
  struct.pack_into('<qfI',want,p+256+i*16,i,x,0)
 for i in range(1,n+1):
  x=F(widths[i-1]+F(F(widths[i]-widths[i-1])*0.5))
  nearest=next((j for j in range(n) if x<F(widths[j]+F(F(widths[j+1]-widths[j])*0.5))),n)
  struct.pack_into('<f',want,p+512+i*24,x)
  struct.pack_into('<qfI',want,p+520+i*24,nearest,widths[nearest],0)
 if data!=want:
  at=next(i for i,(a,b) in enumerate(zip(data,want)) if a!=b)
  raise AssertionError(f'report byte{at}: got{data[at]:02x}, wanted{want[at]:02x}')
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 left=im.crop((40,152,600,232));right=im.crop((680,152,1240,232))
 assert all(e[1]==0 for e in ImageChops.difference(left,right).getextrema())
 pixels=list(left.getdata())
 ink=sum(min(c)>100 and max(c)-min(c)<5 for c in pixels)
 caret=sum(c[2]>150 and c[1]>120 and c[0]<100 for c in pixels)
 assert ink>100 and caret>=80,(ink,caret)
 for xy in [(0,0),(1200,700)]:assert all(abs(a-b)<=1 for a,b in zip(im.getpixel(xy),(10,13,18)))
 return dict(passed=True,cases=len(PLAN['cases']),assertions=len(checks),native_scalar_boundaries=n+1,midpoint_queries=n,matched_native_pixels=44800,max_channel_error=0,ink_pixels=ink,caret_pixels=caret)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--png',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 data=a.report.read_bytes();result=check(data,a.png)
 if a.self_test:
  positions=[0,8,16,24,32767]
  positions.extend(256+i*16 for i in range(len(PLAN['checks'])))
  positions.extend(8192+i*160+j for i in range(len(PLAN['cases'])) for j in [0,8,16,24,32,40,48,64,159])
  positions.extend(24576+256+i*16+j for i in range(12) for j in [0,8,12])
  positions.extend(24576+512+i*24+j for i in range(1,12) for j in [0,8,16,20])
  count=0
  for pos in positions:
   b=bytearray(data);b[pos]^=1
   try:check(b,a.png)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted report mutation',pos))
  try:check(data[:-1],a.png)
  except AssertionError:count+=1
  else:raise AssertionError('accepted truncation')
  with tempfile.TemporaryDirectory() as tmp:
   for xy in [(40,160),(680,160),(0,0)]:
    im=Image.open(a.png).convert('RGB');c=im.getpixel(xy);im.putpixel(xy,tuple(v^128 for v in c));p=Path(tmp)/'bad.png';im.save(p)
    try:check(data,p)
    except AssertionError:count+=1
    else:raise AssertionError(('accepted image mutation',xy))
  result['rejected_corruptions']=count
 print(json.dumps(result,indent=2))
