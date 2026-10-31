"""Check bytes, borrowed views and refusal sentinels from the physical CPU."""
import struct

def check(report,cases):
 assert len(report)==131072
 assert struct.unpack_from('<Q',report)[0]==0x55445036
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*2048;got=list(struct.unpack_from('<9q',report,p))
  assert got==c['expected'],(c['name'],got,c['expected'])
  assert report[p+72:p+80]==b'\xa5'*8,c['name']
  wire=bytes.fromhex(c['wire'])
  assert report[p+80:p+1594]==wire+b'\xa5'*(1514-len(wire)),c['name']
  assert report[p+1594:p+2048]==b'\xa5'*454,c['name']
 return dict(cases=len(cases),passed=True)
