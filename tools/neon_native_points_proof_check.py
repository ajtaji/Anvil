#!/usr/bin/env python3
"""Verify full native fan GPU input and explicit line-expansion refusal."""
from pathlib import Path
import argparse,struct,json

def verify(r,p):
 assert len(r)==8192 and len(p)==16384, 'Complete report and GPU frame required.'
 w=struct.unpack_from('<64I',r)
 assert w[0]==0x4157564e and w[63]==0x4e565741 and w[1]==0 and w[21]==0 and w[53]==1
 assert w[24:28]==(47,642,47,642) and w[36]==0 and w[37]==1 and w[51]==0
 assert struct.unpack_from('<18q',r,0x1000)==(0,1,262144,262144,0,262144,1,0,262144,1,1,0,262144,0,786432,-21203,0,1), 'Point boundary, guard/refusal, full draw or separate line limit differs.'
 assert struct.unpack_from('<q',r,0x1188)[0]==0, 'Final memory remains live.'
 expected=b''.join(struct.pack('<I',0xff00ff00 if 4<=x<28 and 4<=y<28 else 0xff1a334d) for y in range(64) for x in range(64))
 assert p==expected, 'Full GPU rectangle differs; the final vertices must reach the GPU.'
 return dict(fan_input_points=262144,fan_gpu_vertices=262144,exact_gpu_bytes=16384,line_staged_points=262144,line_expansion_vertices=786432,line_draw_still_refused=True,final_memory=0)

def self_test(r,p):
 cases=[]
 for off in [0,4,84,96,100,104,108,144,148,204,212,252]+list(range(0x1000,0x1090,8))+[0x1188]:
  rr=bytearray(r);rr[off]^=1;cases.append((rr,p))
 for off in (0,4*256+4*4,16*256+16*4,28*256+28*4,16383):
  pp=bytearray(p);pp[off]^=1;cases.append((r,pp))
 cases.extend([(r[:-1],p),(r,p[:-4])])
 for rr,pp in cases:
  try:verify(rr,pp)
  except AssertionError:continue
  raise AssertionError('Corrupted proof accepted.')
 return len(cases)

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--pixels',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 r=a.report.read_bytes();p=a.pixels.read_bytes();result=verify(r,p)
 if a.self_test:result['rejected_mutations']=self_test(r,p)
 print('Neon native points PASS',json.dumps(result))
