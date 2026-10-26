#!/usr/bin/env python3
"""Verify physical public counter, clip/error and callback ownership evidence."""
from pathlib import Path
import argparse,json,struct

def verify(r,p):
 assert len(r)==8192 and len(p)==16384, 'Complete report and frame required.'
 w=struct.unpack_from('<64I',r)
 assert w[0]==0x4157564e and w[63]==0x4e565741 and w[1]==0 and w[21]==0 and w[53]==1
 assert w[24:28]==(47,642,47,642) and w[36]==0 and w[37]==1 and w[51]==0
 assert struct.unpack_from('<4q',r,0x1000)==(0,2,162,18), 'Draw preparation or return failed.'
 expected=(2,1,3,26,162,1,3,18,0)
 for off in (0x1020,0x1100,0x1220):
  assert struct.unpack_from('<9q',r,off)==expected, 'Public counters differ before/after submit or refused geometry.'
 assert struct.unpack_from('<4q',r,0x10b0)==(0,800,-21202,-21202), 'Refused clip or error ownership differs.'
 assert struct.unpack_from('<q',r,0x1188)[0]==0, 'Final allocations remain.'
 assert struct.unpack_from('<q',r,0x1300)[0]==6, 'Lifecycle/error/readiness contract groups did not complete.'
 assert struct.unpack_from('<9q',r,0x1400)==(0,0,3,0,0,0,0,0,5), 'Blank/clip statistics differ.'
 assert struct.unpack_from('<9q',r,0x1450)==(0,)*9, 'Abort did not reset counters.'
 for off in (0x1500,0x1580):
  assert struct.unpack_from('<9q',r,off)==tuple(range(101,110)), 'Native fallback was overwritten by owner data.'
 font=r[0x1200:0x1210]
 assert font==bytes.fromhex('00000018183c2c24667e42c300000000')
 pixels=bytearray()
 for y in range(64):
  for x in range(64):
   word=0xff1a334d
   if 4<=x<12 and 4<=y<12:word=0xffff0000
   for left in (4,20):
    if left<=x<left+8 and 20<=y<36 and font[y-20]&(128>>(x-left)):word=0xff00ff00
    if left<=x<left+8 and 40<=y<56 and font[y-40]&(128>>(x-left)):word=0xff0000ff
   pixels+=struct.pack('<I',word)
 assert p==pixels, 'Complete GPU glyph/box oracle differs.'
 return dict(public_counters=9,contract_groups=6,exact_gpu_bytes=16384,final_memory=0)

def self_test(r,p):
 cases=[]
 offsets=[0,4,84,96,100,104,108,144,148,204,212,252]+list(range(0x1000,0x1068,8))+list(range(0x1100,0x1148,8))+list(range(0x1220,0x1268,8))+[0x10b0,0x10b8,0x10c0,0x10c8,0x1188,0x1200,0x1300]
 offsets+=list(range(0x1400,0x1448,8))+list(range(0x1450,0x1498,8))+list(range(0x1500,0x1548,8))+list(range(0x1580,0x15c8,8))
 for off in offsets:
  rr=bytearray(r);rr[off]^=1;cases.append((rr,p))
 for off in (0,4*256+4*4,20*256+8*4,40*256+8*4,16383):
  pp=bytearray(p);pp[off]^=1;cases.append((r,pp))
 cases.extend([(r[:-1],p),(r,p[:-4])])
 for rr,pp in cases:
  try:verify(rr,pp)
  except AssertionError:continue
  raise AssertionError('Corrupted evidence accepted.')
 return len(cases)

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--pixels',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 r=a.report.read_bytes();p=a.pixels.read_bytes();result=verify(r,p)
 if a.self_test:result['rejected_mutations']=self_test(r,p)
 print('Neon public state PASS',json.dumps(result))
