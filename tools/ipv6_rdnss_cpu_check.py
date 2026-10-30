"""Independent bytes and guard oracle for physical RDNSS decoding."""
import struct

def check(report,cases):
 assert len(report)==131072
 assert struct.unpack_from('<2q',report)==(0x52444e53,len(cases))
 for i,c in enumerate(cases):
  p=256+i*4096
  assert struct.unpack_from('<q',report,p)[0]==c['rc'],c['name']
  assert report[p+8:p+3112]==bytes.fromhex(c['output']),c['name']
  assert report[p+3112:p+4096]==b'\xa5'*984,c['name']
 assert report[16:256]==b'\xa5'*240
 assert report[256+4096*len(cases):]==b'\xa5'*(len(report)-256-4096*len(cases))
 return dict(passed=True,cases=len(cases))
