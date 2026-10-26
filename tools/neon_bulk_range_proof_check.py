#!/usr/bin/env python3
"""Check complete physical Neon bulk range evidence; never runs an emulator."""
from pathlib import Path
import argparse,json,struct

def verify(report,pixels):
 assert len(report)==8192, 'Complete native report required.'
 w=struct.unpack_from('<64I',report)
 assert w[0]==0x4157564e and w[63]==0x4e565741, 'Report markers differ.'
 assert w[1]==0 and w[21]==0 and w[53]==1, 'Setup or teardown failed.'
 assert w[36]==0 and w[37]==1 and w[51]==0, 'Unexpected GPU, display or validation status.'
 assert struct.unpack_from('<4q',report,0x1000)==(0,0,0,24), 'Native refusal or exact capacity check failed.'
 values=[0,-1,5,0x2000000000000000,0x2AAAAAAAAAAAAAAB,0x7FFFFFFFFFFFFFFF,0x4000000000000000,0x5555555555555556]
 for i,value in enumerate(values):
  assert struct.unpack_from('<3q',report,0x1020+i*24)==(value,-1,0), 'Invalid reservation accepted or cursor changed.'
 for i,(first,count) in enumerate([(-1,1),(13,1),(7,1),(0,0x2000000000000000)]):
  assert struct.unpack_from('<4q',report,0x1100+i*32)==(first,count,-21201,0), 'Invalid range recorded.'
 assert struct.unpack_from('<7q',report,0x1180)==(2,0,-21202,1,0,-21201,-21202), 'Retirement, guard, empty or frame-state semantics differ.'
 assert len(pixels)==16384, 'Complete GPU frame required.'
 expected=bytearray()
 for y in range(64):
  for x in range(64):
   word=0xff1a334d
   if 4<=x<28 and y in (8,24):word=0xffff0000
   if 4<=x<28 and y in (40,56):word=0xff00ff00
   expected+=struct.pack('<I',word)
 assert pixels==expected, 'GPU output differs from the complete independent line oracle.'
 return dict(invalid_reservations=8,invalid_draw_ranges=4,vertex_capacity=24,draws=2,guard_bytes=592,exact_gpu_bytes=16384,final_memory=0)

def self_test(report,pixels):
 variants=[]
 offsets=[0,4,84,144,148,204,212,252]+list(range(0x1000,0x10e0,8))+list(range(0x1100,0x11b8,8))
 for off in offsets:
  bad=bytearray(report);bad[off]^=1;variants.append((bad,pixels))
 for off in [0,8*256+4*4,40*256+4*4,16383]:
  bad=bytearray(pixels);bad[off]^=1;variants.append((report,bad))
 variants += [(report[:-1],pixels),(report,pixels[:-4])]
 for rr,pp in variants:
  try:verify(rr,pp)
  except AssertionError:continue
  raise AssertionError('Corrupted evidence accepted at mutation '+str(len(variants)))
 return len(variants)

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--report',type=Path,required=True);ap.add_argument('--pixels',type=Path,required=True)
 ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 report=a.report.read_bytes();pixels=a.pixels.read_bytes();result=verify(report,pixels)
 if a.self_test:result['rejected_mutations']=self_test(report,pixels)
 print('Neon bulk range PASS',json.dumps(result))
