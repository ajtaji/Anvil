#!/usr/bin/env python3
"""Verify physical native-unit family budgets and five complete GPU frames."""
from pathlib import Path
import struct,json,argparse

def verify(r,p):
 assert len(r)==8192 and len(p)==81920, 'Complete native report and five GPU frames required.'
 words=struct.unpack_from('<64I',r)
 assert words[0]==0x4157564e and words[63]==0x4e565741 and words[1]==0 and words[21]==0 and words[53]==1
 assert words[24:28]==(47,642,47,642) and words[30]==72 and words[36]==0 and words[37]==1 and words[51]==0
 q=struct.unpack_from('<32q',r,0x1000)
 assert q[:12]==(0,11,190,78,4096,2048,24576,12288,262144,6,6,98304), 'Family boundary or native font comparison failed.'
 assert q[12:]==(6,168,1,18,94)*4, 'Repeated point accounting or rotation state differs.'
 assert struct.unpack_from('<q',r,0x1188)[0]==0, 'Resources remain live.'
 assert struct.unpack_from('<2q',r,0x11a0)==(0,5), 'Large owner creation did not complete.'
 assert struct.unpack_from('<3q',r,0x1300)==(7,84,36), 'Extension refusal or accounting checks failed.'
 font=r[0x1200:0x1210]
 assert font==bytes.fromhex('00000018183c2c24667e42c300000000'), 'Native glyph row fixture differs.'
 expected=bytearray()
 for turn in range(5):
  for y in range(64):
   for x in range(64):
    word=0xff1a334d
    if turn<4 and 6<=x<10 and 6<=y<10:word=0xffff0000
    for left in ((4,20) if turn<4 else ()):
     if left<=x<left+8 and 20<=y<36 and font[y-20] & (128>>(x-left)):word=0xff00ff00
     if left<=x<left+8 and 40<=y<56 and font[y-40] & (128>>(x-left)):word=0xff0000ff
    if turn<4 and ((x==48 and 4<=y<12) or (y==12 and 40<=x<48)):word=0xffffff00
    if turn<4 and 40<=x<48 and 4<=y<12:word=0xff00ffff
    if turn<4 and 4<=x<28 and y==60:word=0xffffffff
    expected+=struct.pack('<I',word)
 assert p==expected, 'GPU bytes differ from the complete independent glyph/shape oracle.'
 return dict(flat_draw_limit=4096,textured_draw_limit=2048,flat_input_vertex_limit=262144,textured_vertex_limit=98304,native_glyph_cases=190,seeded_extension_refusals=7,exact_gpu_bytes=81920,final_memory=0)

def self_test(r,p):
 cases=[]
 for off in [0,4,84,96,100,104,108,120,144,148,204,212,252]+list(range(0x1000,0x1100,8))+[0x1188,0x11a0,0x11a8,0x1200,0x1300,0x1308,0x1310]:
  bad=bytearray(r);bad[off]^=1;cases.append((bad,p))
 for frame in range(5):
  bad=bytearray(p);bad[frame*16384+6*256+6*4]^=1;cases.append((r,bad))
 cases.extend([(r[:-1],p),(r,p[:-4])])
 for rr,pp in cases:
  try:verify(rr,pp)
  except AssertionError:continue
  raise AssertionError('Corrupted proof accepted.')
 return len(cases)

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--pixels',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 report=a.report.read_bytes();pixels=a.pixels.read_bytes();result=verify(report,pixels)
 if a.self_test:result['rejected_mutations']=self_test(report,pixels)
 print('Neon family budgets PASS',json.dumps(result))
