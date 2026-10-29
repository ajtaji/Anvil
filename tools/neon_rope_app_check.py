#!/usr/bin/env python3
"""Independent Pillow composition and exact CPU asset/native-pixel verification."""
from pathlib import Path
from functools import cache
import argparse,json,struct
from PIL import Image,ImageDraw

@cache
def rope():
 im=Image.new('RGBA',(32,64),(180,120,0,255));d=ImageDraw.Draw(im)
 d.rectangle((8,0,23,63),fill=(255,210,50,255))
 d.rectangle((0,0,2,63),fill=(80,50,0,255));d.rectangle((29,0,31,63),fill=(80,50,0,255))
 overlay=Image.new('RGBA',im.size);d=ImageDraw.Draw(overlay)
 for y in range(0,65,8):d.rectangle((0,y,31,y+1),fill=(100,60,0,150))
 return Image.alpha_composite(im,overlay)

def expected_report():
 data=bytearray(49152);checks=[]
 for i in range(13):checks.extend([-21323 if i in (3,4) else -21320,991,992,0])
 checks.extend([0,0,0,0,-21320,991,992,0,0,-21323,991,992,0,0,1,0,1,0,-21323,0,0,0,0,0])
 assert len(checks)==76
 struct.pack_into('<4q',data,0,0x4e525431,1,0,len(checks))
 for i,value in enumerate(checks):struct.pack_into('<2q',data,256+i*16,value,value)
 for slot in range(3):
  at=8192+slot*12288;meta=(991,992) if slot==2 else (32,64)
  struct.pack_into('<2q',data,at,*meta);pixels=bytearray(b'\xa5'*8216);mask=bytearray(b'\x5a'*2072)
  if slot<2:
   offset=8+slot;pixels[offset:offset+8192]=rope().tobytes()
   if slot==0:mask[8:2056]=b'\1'*2048
  data[at+32:at+8248]=pixels;data[at+8248:at+10320]=mask
 return bytes(data)

@cache
def scene_samples():
 image=rope().convert('RGB');samples={}
 for x0,y0,scale,source in [(40,40,1,image),(120,40,3,image),(280,40,4,image.crop((8,8,24,24)))]:
  im=source.resize((source.width*scale*2,source.height*scale*2),Image.Resampling.NEAREST)
  for y in range(im.height):
   for x in range(im.width):samples[(x0*2+x,y0*2+y)]=im.getpixel((x,y))
 return samples

def check(data,png):
 want=expected_report();assert len(data)==len(want),(len(data),len(want))
 if data!=want:
  at=next(i for i,(a,b) in enumerate(zip(data,want)) if a!=b)
  raise AssertionError(f'report byte {at}: got{data[at]:02x}, expected{want[at]:02x}')
 im=Image.open(png).convert('RGB');assert im.size==(1280,800)
 for xy,want in scene_samples().items():
  got=im.getpixel(xy);assert all(abs(a-b)<=1 for a,b in zip(got,want)),('native',xy,got,want)
 for xy in [(0,0),(1270,790),(10,200),(600,600)]:assert all(abs(a-b)<=1 for a,b in zip(im.getpixel(xy),(10,13,18))),('background',xy)
 return dict(passed=True,assertions=76,argument_refusals=13,service_refusals=3,exact_rgba_bytes=16384,exact_mask_bytes=2048,native_pixels=len(scene_samples()),resident_images=2,draws=3)

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--png',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 data=a.report.read_bytes();result=check(data,a.png)
 if a.self_test:
  count=0
  for at in list(range(0,32,8))+[256+i*16 for i in range(76)]+[8192+i*12288+n for i in range(3) for n in (0,8,16,32,39,40,41,8230,8247,8248,8256,10303,10319)]+[49151]:
   mutant=bytearray(data);mutant[at]^=1
   try:check(mutant,a.png)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted report mutation',at))
  try:check(data[:-1],a.png)
  except AssertionError:count+=1
  else:raise AssertionError('accepted truncated report')
  # Each checked texture texel and all colour channels must affect the oracle.
  # This branch checks the actual full-image routine using three representative
  # pixels, without replacing the production samples or broadening tolerance.
  import tempfile
  with tempfile.TemporaryDirectory() as td:
   for xy in [(80,80),(240,80),(560,80),(0,0)]:
    im=Image.open(a.png).convert('RGB');old=im.getpixel(xy);im.putpixel(xy,tuple(v^128 for v in old));p=Path(td)/'bad.png';im.save(p)
    try:check(data,p)
    except AssertionError:count+=1
    else:raise AssertionError(('accepted pixel mutation',xy))
  result['rejected_corruptions']=count
 print(json.dumps(result,indent=2))
