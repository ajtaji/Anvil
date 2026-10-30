"""Check router slots, selection, revisions and unchanged memory guards."""
import struct

def check(report,cases):
 assert struct.unpack_from('<Q',report)[0]==0x44525442
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*256;got=list(struct.unpack_from('<6q',report,p))
  assert got==c['expected'],(c['name'],got,c['expected'])
  assert report[p+48:p+144]==bytes.fromhex(c['rows']),c['name']
  assert report[p+144:p+256]==b'\xa5'*112,c['name']
 return dict(cases=len(cases),passed=True)
