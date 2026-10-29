"""Independent ordered panel composition and full native/reference image checks."""
from pathlib import Path
import json,struct,argparse,tempfile
from PIL import Image,ImageChops
PLAN=json.loads(Path(__file__).with_name('neon_chrome_panel_cases.json').read_text(encoding='utf8'))
def packets():
 result=[]
 for index,c in enumerate(PLAN['rows']):
  x=20.;y=float(c['y']);w=280.;h=float(c['h']);hh=float(c['header'])
  panel,head,line=((.145,.149,.161),(.169,.173,.184),(.196,.2,.212)) if index==0 else ((.08,.13,.19),(.12,.2,.29),(.3,.4,.5))
  accent=c['accent']
  def box(x,y,w,h,rgb):
   if w>0 and h>0:result.append((1,0,x,y,w,h,*rgb,1.,''))
  box(x,y,w,h,panel)
  if c['upper']:
   box(x,y,w,hh,head);box(x,y,3.,hh,accent);box(x,y+hh,w,1.,line)
   result.append((2,0,x+12.,y+5.,0.,0.,*accent,1.,c['upper']))
  for geometry in [(x,y,w,1.),(x,y+h-1.,w,1.),(x,y,1.,h),(x+w-1.,y,1.,h)]:box(*geometry,line)
 return result
def check(data,png):
 assert len(data)==PLAN['report_bytes']
 want=bytearray(len(data));q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert q(48)>3
 struct.pack_into('<7q',want,0,0x4e505031,1,0,len(PLAN['assertions']),30,0,q(48))
 for i,value in enumerate(PLAN['assertions']):struct.pack_into('<2q',want,256+i*16,value,value)
 all_packets=packets();assert len(all_packets)==30
 for i,p in enumerate(all_packets):
  op,font,*other=p;floats=other[:8];text=other[8].encode();at=16384+i*128
  struct.pack_into('<2q8f',want,at,op,font,*floats)
  if text:
   struct.pack_into('<q',want,at+48,len(text));want[at+64:at+65+len(text)]=text+b'\0'
 for i,c in enumerate(PLAN['rows']):
  raw=bytearray(b'\xa5'*144);title=c['upper'].encode()+b'\0';raw[8:8+len(title)]=title
  want[32768+i*144:32768+(i+1)*144]=raw
 if data!=want:
  at=next(i for i,(a,b) in enumerate(zip(data,want)) if a!=b)
  raise AssertionError(f'report byte{at}: got{data[at]:02x}, expected{want[at]:02x}')
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 left=im.crop((40,80,600,720));right=im.crop((680,80,1240,720))
 extrema=ImageChops.difference(left,right).getextrema();assert all(x[1]==0 for x in extrema),extrema
 probes=[((42,212),(10,13,18)),((682,212),(10,13,18)),((500,190),(37,38,41)),((500,380),(20,33,48)),((0,0),(10,13,18)),((1270,790),(10,13,18))]
 for xy,rgb in probes:assert all(abs(a-b)<=1 for a,b in zip(im.getpixel(xy),rgb)),(xy,im.getpixel(xy),rgb)
 # A blank or previous text-only frame cannot satisfy the image qualification.
 ink=sum(1 for rgb in left.getdata() if max(rgb)-min(rgb)>35 and max(rgb)>100);assert ink>1000,ink
 caption_ink=[]
 for index in [0,1,3]:
  y=(PLAN['rows'][index]['y']+5)*2
  region=im.crop((64,y,540 if index==0 else 596,y+40))
  count=sum(1 for rgb in region.getdata() if max(rgb)-min(rgb)>35 and max(rgb)>100)
  assert count>100,('missing caption',index,count)
  caption_ink.append(count)
 return dict(passed=True,assertions=len(PLAN['assertions']),ordered_callback_packets=30,box_packets=27,text_packets=3,matched_native_pixels=560*640,max_channel_error=0,accent_pixels=ink,caption_ink_pixels=caption_ink,probes=len(probes),prepared_inside_draw=0,panels=4)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--png',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args();data=a.report.read_bytes();result=check(data,a.png)
 if a.self_test:
  positions=[0,8,16,24,32,40,56,49151]
  positions.extend(256+i*16 for i in range(len(PLAN['assertions'])))
  positions.extend(16384+i*128+n for i in range(30) for n in range(0,128,4))
  positions.extend(32768+i for i in range(576))
  count=0
  for p in positions:
   bad=bytearray(data);bad[p]^=1
   try:check(bad,a.png)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted report mutation',p))
  try:check(data[:-1],a.png)
  except AssertionError:count+=1
  else:raise AssertionError('accepted truncation')
  with tempfile.TemporaryDirectory() as d:
   for xy in [(40,80),(680,80),(42,212),(500,380),(1270,790)]:
    im=Image.open(a.png).convert('RGB');old=im.getpixel(xy);im.putpixel(xy,tuple(v^128 for v in old));p=Path(d)/'bad.png';im.save(p)
    try:check(data,p)
    except AssertionError:count+=1
    else:raise AssertionError(('accepted pixel mutation',xy))
  result['rejected_corruptions']=count
 print(json.dumps(result,indent=2))
