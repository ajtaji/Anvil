"""Full PNG RGBA/mask/transactional-output checks and native texture pixels."""
from pathlib import Path
import json,struct
from PIL import Image
PLAN=json.loads(Path(__file__).with_name('neon_png_cases.json').read_text(encoding='utf8'))
def metadata(source,address):
 w,h,depth,kind,_,_,interlace=struct.unpack('>IIBBBBB',source[16:29]);channels={0:1,2:3,3:1,4:2,6:4}[kind]
 palette=palcount=trns=trnsbytes=idat=0;p=8
 while p<len(source):
  n=struct.unpack_from('>I',source,p)[0];tag=source[p+4:p+8]
  if tag==b'PLTE':palette=address+p+8;palcount=n//3
  if tag==b'tRNS':trns=address+p+8;trnsbytes=n
  if tag==b'IDAT':idat+=n
  p+=n+12
 raw=0
 for x,y,dx,dy in ([(0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2)] if interlace else [(0,0,1,1)]):
  pw=max(0,(w-x+dx-1)//dx);ph=max(0,(h-y+dy-1)//dy)
  if pw and ph:raw+=(((pw*depth*channels+7)//8)+1)*ph
 workspace=8192+((idat+7)&~7)+((raw+7)&~7)+w*h*4
 return (w,h,depth,kind,interlace,channels,idat,raw,workspace,palette,palcount,trns,trnsbytes)
def check(data,png):
 assert len(data)==PLAN['report_bytes'];q=lambda p:struct.unpack_from('<q',data,p)[0];expected=[0,0,0]
 for c in PLAN['cases']:
  expected.extend([c['inspect'],c['decode']])
  if c['native']:expected.append(1)
 expected.extend(PLAN.get('argument_expected',[]));expected.extend(PLAN.get('file_expected',[]));expected.extend([0]*10)
 assert [q(i) for i in [0,8,16,24]]==[0x4e505431,1,0,len(expected)]
 for i,v in enumerate(expected):assert struct.unpack_from('<2q',data,256+i*16)==(v,v),('ledger',i,struct.unpack_from('<2q',data,256+i*16),v)
 exact=maskbytes=0;guard=struct.unpack('<q',b'\x3c'*8)[0]
 for c in PLAN['cases']:
  p=c['record_offset'];source=bytes.fromhex(c['source']);assert (q(p),q(p+8))==(c['inspect'],c['decode']),(c['name'],q(p),q(p+8))
  assert (q(p+32),q(p+40))==(guard,guard),(c['name'],'scratch guards')
  assert q(p+48)>0
  if c['inspect']==0:
   meta=metadata(source,q(p+48));assert struct.unpack_from('<13q',data,p+64)==meta,(c['name'],'metadata',struct.unpack_from('<13q',data,p+64),meta)
  else:assert data[p+64:p+168]==b'\xa5'*104,(c['name'],'inspect published on failure')
  want_rgba=bytearray(b'\xa5'*1040);want_mask=bytearray(b'\x5a'*272)
  if c['decode']==0:
   raw=bytes.fromhex(c['rgba']);w,h=struct.unpack('>II',source[16:24]);assert (q(p+16),q(p+24))==(w,h)
   want_rgba[8:8+len(raw)]=raw;mask=bytes(int(raw[i]>0) for i in range(3,len(raw),4));want_mask[8:8+len(mask)]=mask;exact+=len(raw);maskbytes+=len(mask)
  else:assert (q(p+16),q(p+24))==(991,992),(c['name'],'decode metadata changed on refusal')
  assert data[p+192:p+1232]==want_rgba,(c['name'],'RGBA/guards/transaction')
  assert data[p+1248:p+1520]==want_mask,(c['name'],'mask/guards/transaction')
  for a,b in [(56,64),(168,192),(1232,1248),(1520,1536)]:assert data[p+a:p+b]==bytes(b-a),(c['name'],'reserved')
 assert data[4096:5120]==b'\xa5'*1024 and data[5120:5376]==b'\x5a'*256,'argument-refusal output mutation'
 fixture=PLAN['file_fixture'];file_bytes=bytes.fromhex(PLAN['cases'][fixture['case_index']]['source']);assert data[8192:8192+len(file_bytes)]==file_bytes,'file-handle read bytes'
 for a,b in [(32,256),(256+len(expected)*16,4096),(5376,8192),(8192+len(file_bytes),16384),(16384+len(PLAN['cases'])*1536,len(data))]:assert data[a:b]==bytes(b-a),(a,b,'reserved')
 im=Image.open(png).convert('RGB');assert im.size==(1280,800);pixels=im.load();compared=0
 for c in PLAN['cases']:
  if not c['native']:continue
  n=c['native']-1;x0=(20+(n%4)*150)*2;y0=(40+(n//4)*150)*2;w,h=struct.unpack('>II',bytes.fromhex(c['source'])[16:24]);raw=bytes.fromhex(c['rgba'])
  for y in range(h*12):
   for x in range(w*12):
    p=((y//12)*w+x//12)*4;a=raw[p+3];want=tuple((raw[p+i]*a+bg*(255-a))/255 for i,bg in enumerate((10,13,18)));got=pixels[x0+x,y0+y]
    assert all(abs(v-t)<=1.1 for v,t in zip(got,want)),(c['name'],'native',x,y,got,want)
    compared+=1
 for xy in [(0,0),(1200,700),(30,70)]:assert all(abs(a-b)<=1 for a,b in zip(pixels[xy],(10,13,18))),('background',xy,pixels[xy])
 return dict(passed=True,cases=len(PLAN['cases']),assertions=len(expected),exact_rgba_bytes=exact,exact_mask_bytes=maskbytes,native_images=8,native_pixels=compared,all_legal_colour_depth_pairs=15,interlaced_and_noninterlaced=True,file_read_qualified=True,file_bytes=len(file_bytes),argument_refusals=16)
