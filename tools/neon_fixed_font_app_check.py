"""Fixed-spacing isolation against independent positioned glyph draws."""
from pathlib import Path
import json,struct,math,argparse,tempfile
from PIL import Image,ImageChops
PLAN=json.loads(Path(__file__).with_name('neon_fixed_font_cases.json').read_text(encoding='utf8'))
def check(data,png):
 assert len(data)==8192
 want=bytearray(8192);checks=PLAN['checks']
 struct.pack_into('<4q',want,0,0x4e465831,1,0,len(checks))
 for i,v in enumerate(checks):struct.pack_into('<2q',want,256+i*16,v,v)
 widths=struct.unpack_from('<4f',data,128)
 assert all(math.isfinite(v) and 0<v<200 for v in widths) and all(v==widths[0] for v in widths),widths
 want[128:144]=data[128:144]
 if data!=want:
  p=next(i for i,(a,b) in enumerate(zip(data,want)) if a!=b)
  raise AssertionError(('report byte mismatch',p,data[p],want[p]))
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 inks=[];matched=0
 for row in PLAN['rows']:
  y=row['y']*2
  left=im.crop((40,y,600,y+48));right=im.crop((680,y,1240,y+48))
  extrema=ImageChops.difference(left,right).getextrema()
  assert all(v[1]==0 for v in extrema),(row,extrema)
  ink=sum(min(c)>100 and max(c)-min(c)<5 for c in left.getdata())
  assert ink>300,(row,ink)
  inks.append(ink);matched+=560*48
 for xy in [(0,0),(1200,780)]:assert all(abs(a-b)<=1 for a,b in zip(im.getpixel(xy),(10,13,18)))
 return dict(passed=True,assertions=len(checks),rows=6,matched_native_pixels=matched,max_channel_error=0,ink_pixels=inks,proportional_width=widths[0],fixed_width=154.0,fractional_width=82.5)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--png',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 data=a.report.read_bytes();result=check(data,a.png)
 if a.self_test:
  positions=[0,8,16,24,128,132,136,140,8191]+[256+i*16 for i in range(len(PLAN['checks']))]
  count=0
  for pos in positions:
   bad=bytearray(data);bad[pos]^=1
   try:check(bad,a.png)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted report mutation',pos))
  try:check(data[:-1],a.png)
  except AssertionError:count+=1
  else:raise AssertionError('accepted truncation')
  with tempfile.TemporaryDirectory() as tmp:
   for y in [row['y']*2 for row in PLAN['rows']]:
    for x in [40,680]:
     im=Image.open(a.png).convert('RGB');c=im.getpixel((x,y));im.putpixel((x,y),tuple(v^128 for v in c));p=Path(tmp)/'bad.png';im.save(p)
     try:check(data,p)
     except AssertionError:count+=1
     else:raise AssertionError(('accepted image mutation',x,y))
  result['rejected_corruptions']=count
 print(json.dumps(result,indent=2))
