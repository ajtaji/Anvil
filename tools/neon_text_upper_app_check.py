"""Exact Unicode17 uppercase corpus and native/reference label pixels."""
from pathlib import Path
import argparse,json,struct,tempfile
from PIL import Image,ImageChops
PLAN=json.loads(Path(__file__).with_name('neon_text_upper_cases.json').read_text(encoding='utf8'))
def check(data,png):
 assert len(data)==PLAN['report_bytes']
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 checks=[]
 for c in PLAN['cases']:checks.extend([c['wanted'],c['rc'],c['first_scalar']])
 checks.extend([-23200,-23200,-23200,-23200,-23202,-23200,-23200,-23200,-22006,-22006,-22006,-22006,-22006,1114111])
 native=PLAN['native_upper'].encode();checks.extend([0,0,0,1,len(native),0,0,0,0,0,0])
 want=bytearray(len(data));struct.pack_into('<6q',want,0,0x554e5431,1,0,len(checks),PLAN['mappings'],PLAN['mapping_data_bytes'])
 for i,v in enumerate(checks):struct.pack_into('<2q',want,256+i*16,v,v)
 total=0
 for i,c in enumerate(PLAN['cases']):
  p=8192+i*PLAN['record_stride'];struct.pack_into('<6q',want,p,c['wanted'],c['rc'],c['capacity'],c['budget'],c['offset'],c['first_scalar'])
  raw=bytearray(b'\xa5'*16400)
  if c['rc']>=0:
   output=bytes.fromhex(c['output']);assert len(output)==c['rc']+1
   raw[c['offset']:c['offset']+len(output)]=output;total+=c['rc']
  want[p+48:p+16448]=raw
 want[0x3c000:0x3c000+16400]=b'\xa5'*16400
 p=0x42000;assert q(p+8)>3
 struct.pack_into('<2q',want,p,len(native),q(p+8));want[p+64:p+65+len(native)]=native+b'\0'
 if data!=want:
  pos=next(i for i,(a,b) in enumerate(zip(data,want)) if a!=b)
  raise AssertionError(f'report byte{pos}: got{data[pos]:02x}, expected{want[pos]:02x}')
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 left=im.crop((40,160,600,224));right=im.crop((680,160,1240,224))
 extrema=ImageChops.difference(left,right).getextrema();assert all(x[1]==0 for x in extrema),extrema
 ink=sum(1 for rgb in left.getdata() if min(rgb)>32 and max(rgb)-min(rgb)<5);assert ink>100
 for xy in [(0,0),(1200,700)]:assert all(abs(a-b)<=1 for a,b in zip(im.getpixel(xy),(10,13,18)))
 return dict(passed=True,cases=len(PLAN['cases']),assertions=len(checks),changed_mappings=1580,exact_uppercase_bytes=total,matched_native_pixels=35840,native_ink_pixels=ink,native_upper=PLAN['native_upper'],max_pixel_error=0)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--png',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args();data=a.report.read_bytes();result=check(data,a.png)
 if a.self_test:
  positions=list(range(0,48,8))+[256+i*16 for i in range(result['assertions'])]+[0x3c000,0x3c000+16399,len(data)-1]
  for i,c in enumerate(PLAN['cases']):
   p=8192+i*16448;positions.extend(p+n for n in [0,8,24,40,48,55,56,57,16439,16447])
   if c['rc']>0:positions.extend([p+48+c['offset']+c['rc']//2,p+48+c['offset']+c['rc']-1])
  count=0
  for pos in positions:
   bad=bytearray(data);bad[pos]^=1
   try:check(bad,a.png)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted report corruption',pos))
  try:check(data[:-1],a.png)
  except AssertionError:count+=1
  else:raise AssertionError('accepted truncation')
  with tempfile.TemporaryDirectory() as d:
   for xy in [(40,160),(680,160),(0,0)]:
    im=Image.open(a.png).convert('RGB');old=im.getpixel(xy);im.putpixel(xy,tuple(v^128 for v in old));p=Path(d)/'bad.png';im.save(p)
    try:check(data,p)
    except AssertionError:count+=1
    else:raise AssertionError(('accepted image corruption',xy))
  result['rejected_corruptions']=count
 print(json.dumps(result,indent=2))
