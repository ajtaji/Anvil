"""Resident snap API, ABI validation and native GPU screenshot oracle."""
from pathlib import Path
import json,struct,argparse
from PIL import Image,ImageChops
PLAN=json.loads(Path(__file__).with_name('neon_font_controls_cases.json').read_text(encoding='utf8'))
def check(data,png):
 assert len(data)==8192
 want=bytearray(8192)
 struct.pack_into('<4q',want,0,0x4e434631,1,0,len(PLAN['checks']))
 for i,v in enumerate(PLAN['checks']):struct.pack_into('<2q',want,256+i*16,v,v)
 assert data==want,('report mismatch',next((i for i,(a,b) in enumerate(zip(data,want)) if a!=b),None))
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 crops=[];inks=[]
 for row in PLAN['rows']:
  y=row['y'];a=im.crop((20,y,260,y+32));b=im.crop((400,y,640,y+32))
  assert all(v[1]==0 for v in ImageChops.difference(a,b).getextrema()),row
  n=sum(c[0]>100 and c[1]>80 for c in a.getdata());assert (n==0 if row['kind']=='all-hidden' else n>100),(row,n)
  if row['kind']=='all-hidden':assert all(all(abs(v-w)<=1 for v,w in zip(c,(10,13,18))) for c in a.getdata())
  inks.append(n);crops.append(a.tobytes())
 return dict(passed=True,assertions=len(PLAN['checks']),rows=6,matched_native_pixels=46080,max_channel_error=0,ink_pixels=inks)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);ap.add_argument('--png',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 d=a.report.read_bytes();result=check(d,a.png)
 if a.self_test:
  count=0
  for pos in [0,8,16,24,8191]+[256+i*16 for i in range(len(PLAN['checks']))]:
   bad=bytearray(d);bad[pos]^=1
   try:check(bad,a.png)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted mutation',pos))
  try:check(d[:-1],a.png)
  except AssertionError:count+=1
  else:raise AssertionError('accepted truncation')
  result['rejected_report_corruptions']=count
 print(json.dumps(result,indent=2))
