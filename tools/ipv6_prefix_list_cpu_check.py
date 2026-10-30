"""Check prefix union, route matching, expiry and guard bytes."""
import struct

def check(report,cases):
 assert struct.unpack_from('<Q',report)[0]==0x50524658
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*256;got=list(struct.unpack_from('<4q',report,p))
  assert got==c['expected'],(c['name'],got,c['expected'])
  assert report[p+32:p+128]==bytes.fromhex(c['rows']),c['name']
  assert report[p+128:p+256]==b'\xa5'*128,c['name']
 return dict(cases=len(cases),passed=True)
