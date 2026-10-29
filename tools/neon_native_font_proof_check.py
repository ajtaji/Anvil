"""Check direct native methods, teardown and actual Vulkan attachment crops."""
from pathlib import Path
import json,struct,math,argparse,tempfile
from PIL import Image,ImageChops
PLAN=json.loads(Path(__file__).with_name('neon_native_font_cases.json').read_text(encoding='utf8'))
def check(data,pixels):
 assert len(data)==16384 and len(pixels)==368672
 parent=struct.unpack_from('<64I',data);want=bytearray(16384)
 exact={0:0x4157564e,1:0,2:9,3:256,15:4096000,16:3200,20:1,23:1,53:1,54:0x181,55:1,56:1,58:0x3dcccccd,59:0x3e4ccccd,60:0x3e99999a,61:0x3f800000,63:0x4e565741}
 for i in range(64):
  if 4<=i<=13:
   assert parent[i]>0,(i,parent[i]);struct.pack_into('<I',want,i*4,parent[i])
  elif i==14:
   assert 0x033e8000<=parent[i] and parent[i]+4096000<=0x03fe8000
   struct.pack_into('<I',want,i*4,parent[i])
  else:struct.pack_into('<I',want,i*4,exact.get(i,0))
 p=512
 for off,v in [(0,0x4e465031),(8,1),(16,0),(24,len(PLAN['checks'])),(32,6),(40,368640),(48,368672),(80,0),(88,0),(112,58),(120,738)]:struct.pack_into('<q',want,p+off,v)
 widths=struct.unpack_from('<2f',data,p+128)
 assert math.isfinite(widths[0]) and 0<widths[0]<240 and widths[0]==widths[1],widths
 want[p+128:p+136]=data[p+128:p+136]
 for i,v in enumerate(PLAN['checks']):struct.pack_into('<2q',want,p+512+i*16,v,v)
 if data!=want:
  pos=next(i for i,(a,b) in enumerate(zip(data,want)) if a!=b)
  raise AssertionError(('report mismatch',pos,data[pos],want[pos]))
 assert pixels[:16]==b'\xa5'*16 and pixels[-16:]==b'\xa5'*16
 ink=[];gold=0
 for i,row in enumerate(PLAN['rows']):
  start=16+i*61440
  left=Image.frombytes('RGBA',(240,32),pixels[start:start+30720],'raw','BGRA')
  right=Image.frombytes('RGBA',(240,32),pixels[start+30720:start+61440],'raw','BGRA')
  assert all(e[1]==0 for e in ImageChops.difference(left,right).getextrema()),row['kind']
  rgba=list(left.getdata())
  if row['kind']=='retained':
   n=sum(c[0]>100 and c[0]>c[1]>c[2] and c[3]>100 for c in rgba);gold=n
  else:n=sum(min(c[:3])>100 and max(c[:3])-min(c[:3])<5 for c in rgba)
  assert n>100,(row,n)
  ink.append(n)
  assert all(abs(a-b)<=1 for a,b in zip(left.getpixel((239,31)),(10,13,18,255)))
 return dict(passed=True,assertions=len(PLAN['checks']),gpu_rows=6,matched_attachment_pixels=46080,max_channel_error=0,ink_pixels=ink,retained_gold_pixels=gold,draws=58,vertices=738,glyph_raster_delta=0,atlas_upload_delta=0,retired_handle_refusals=2,retirement_fault_counter=0,original_proportional_width=widths[0])
def montage(pixels,path):
 im=Image.new('RGBA',(480,192))
 for i in range(6):
  start=16+i*61440
  im.paste(Image.frombytes('RGBA',(240,32),pixels[start:start+30720],'raw','BGRA'),(0,i*32))
  im.paste(Image.frombytes('RGBA',(240,32),pixels[start+30720:start+61440],'raw','BGRA'),(240,i*32))
 im.save(path)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--pixels',type=Path,required=True);ap.add_argument('--montage',type=Path);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 data=a.report.read_bytes();pixels=a.pixels.read_bytes();result=check(data,pixels)
 if a.montage:montage(pixels,a.montage)
 if a.self_test:
  positions=[0,4,8,12,60,64,80,92,204,216,220,224,232,252,16383]
  positions.extend(512+i for i in [0,8,16,24,32,40,48,80,88,112,120,128,132,136])
  positions.extend(1024+i*16 for i in range(len(PLAN['checks'])))
  count=0
  for pos in positions:
   bad=bytearray(data);bad[pos]^=1
   try:check(bad,pixels)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted report fault',pos))
  for pos in [0,15,368656,368671]+[16+i*30720+j for i in range(12) for j in [0,1,2,3,30719]]:
   bad=bytearray(pixels);bad[pos]^=128
   try:check(data,bad)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted pixel fault',pos))
  for bad in [data[:-1]]:
   try:check(bad,pixels)
   except AssertionError:count+=1
   else:raise AssertionError('accepted truncated report')
  try:check(data,pixels[:-1])
  except AssertionError:count+=1
  else:raise AssertionError('accepted truncated pixels')
  result['rejected_corruptions']=count
 print(json.dumps(result,indent=2))
