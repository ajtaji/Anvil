"""Compare RA copy-out state against independent network-order packet fixtures."""
import struct

def check(report,cases):
 assert struct.unpack_from('<Q',report)[0]==0x524f5554
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*512
  assert struct.unpack_from('<q',report,p)[0]==c['rc'],c['name']
  got=report[p+8:p+376];expected=bytes.fromhex(c['output'])
  assert got==expected,(c['name'],got.hex(),expected.hex())
  assert report[p+376:p+512]==b'\xa5'*136,c['name']
 return dict(cases=len(cases),passed=True)
