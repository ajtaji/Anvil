"""Check per-prefix lifetime state, address bytes and untouched record guards."""
import struct

def check(report,cases):
 assert struct.unpack_from('<Q',report)[0]==0x534c4141
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*128
  got=list(struct.unpack_from('<6q',report,p))
  assert got==c['expected'],(c['name'],got,c['expected'])
  assert report[p+48:p+64]==bytes.fromhex(c['address']),c['name']
  assert report[p+64:p+128]==b'\xa5'*64,c['name']
 return dict(cases=len(cases),passed=True)
