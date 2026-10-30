"""Verify physical source selection outcomes and exact HTTP request bytes."""
import struct
def check(report,cases):
 assert struct.unpack_from('<Q',report)[0]==0x53454c36
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*2048;got=list(struct.unpack_from('<10q',report,p))
  assert got==c['expected'],(c['name'],got,c['expected'])
  wire=bytes.fromhex(c['wire'])
  assert report[p+80:p+1594]==wire+b'\xa5'*(1514-len(wire)),c['name']
  assert report[p+1594:p+2048]==b'\xa5'*454,c['name']
 return dict(cases=len(cases),passed=True)
