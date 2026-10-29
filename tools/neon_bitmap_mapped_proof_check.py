"""Independent bitmap-row oracle for mapped text, alignment, clipping and retry."""
from pathlib import Path
import argparse,struct,json
def verify(report,pixels):
 assert len(report)==8192 and len(pixels)==393216,'Capture size'
 assert struct.unpack_from('<I',report,0)[0]==0x4157564e and struct.unpack_from('<I',report,4)[0]==0
 for off,value in [(0x1000,0),(0x1008,24),(0x1010,24),(0x1188,0),(0x1190,0),(0x1198,0),(0x11a0,0)]:assert struct.unpack_from('<q',report,off)[0]==value,hex(off)
 source=report[0x1400:0x19f0]
 def rows(ch,bold=False):return [v|(v>>1) if bold else v for v in source[(ord(ch)-32)*16:(ord(ch)-31)*16]]
 def cost(text,bold=False):
  rectangles=0
  for ch in text:
   previous=None
   for bits in rows(ch,bold):
    if bits!=previous:rectangles+=sum(bool(bits&(128>>x)) and (x==0 or not bits&(128>>(x-1))) for x in range(8))
    previous=bits
  return rectangles*6
 for turn in range(4):assert struct.unpack_from('<11q',report,0xc00+turn*128)==(1,-21201,-21203,-21201,-21204,-21202,-21204,0,0,1,1),'Refusal/no-op did not preserve state and unused storage'
 for frame in range(24):
  kind=frame%6;text='A A' if kind in [0,2] else ('AB' if kind in [1,5] else 'A');bold=kind==1;scale=0.5 if kind==4 else 2;col=0xff00ff00 if bold else 0xffffffff
  native=cost(text,bold);ink=sum(any(rows(ch,bold)) for ch in text)
  assert struct.unpack_from('<8q',report,0x400+frame*64)==(0,native,1,ink*6,1,len(text),native//6,1),('Counters',frame,struct.unpack_from('<8q',report,0x400+frame*64))
  image=[0xff000000]*4096
  for j,ch in enumerate(text):
   glyph=rows(ch,bold);origin=4+j*8*scale
   for y in range(64):
    for x in range(64):
     if kind==3 and not (12<=x<28 and 8<=y<24):continue
     gx=int((x+0.5-origin)//scale);gy=int((y+0.5-4)//scale)
     if 0<=gx<8 and 0<=gy<16 and glyph[gy]&(128>>gx):image[y*64+x]=col
  expected=struct.pack('<4096I',*image);actual=pixels[frame*16384:(frame+1)*16384]
  assert actual==expected,('Pixels',frame,sum(a!=b for a,b in zip(actual,expected)))
 return dict(frames=24,rotations=4,exact_gpu_bytes=len(pixels),same_frame_refusal_retries=4,source_width=24)
def self_test(report,pixels):
 offsets=[0,4,0x1000,0x1008,0x1010,0x1188,0x1190,0x1198,0x11a0,0x1400+(65-32)*16]
 offsets+=list(range(0x400,0x440,8))+list(range(0x400+23*64,0x440+23*64,8))+list(range(0xc00,0xc58,8))
 rejected=0
 for offset in offsets:
  bad=bytearray(report);bad[offset]^=1
  try:verify(bad,pixels)
  except AssertionError:rejected+=1
  else:raise AssertionError(('Corrupt report accepted',offset))
 for frame in range(24):
  bad=bytearray(pixels);bad[frame*16384+4096]^=1
  try:verify(report,bad)
  except AssertionError:rejected+=1
  else:raise AssertionError(('Corrupt pixels accepted',frame))
 return rejected
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--self-test',action='store_true');ap.add_argument('--report',type=Path,required=True);ap.add_argument('--pixels',type=Path,required=True);a=ap.parse_args();report=a.report.read_bytes();pixels=a.pixels.read_bytes();result=verify(report,pixels)
 if a.self_test:result['corruptions_rejected']=self_test(report,pixels)
 print('PASS',json.dumps(result))
if __name__=='__main__':main()
