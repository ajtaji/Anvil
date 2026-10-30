"""Check composed address lifetimes, DAD receipts, exact frames and guards."""
import struct

def check(report,cases):
 assert struct.unpack_from('<Q',report)[0]==0x4f574e52
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*2048;got=list(struct.unpack_from('<8q',report,p))
  assert got==c['expected'],(c['name'],got,c['expected'])
  wire=bytes.fromhex(c['wire'])
  assert report[p+64:p+1578]==wire+b'\xa5'*(1514-len(wire)),c['name']
  assert report[p+1578:p+2048]==b'\xa5'*470,c['name']
 return dict(cases=len(cases),passed=True)
