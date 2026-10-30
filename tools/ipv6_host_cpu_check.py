"""Verify composed host state and independently constructed full packets."""
import struct

def check(report,cases):
 assert struct.unpack_from('<Q',report)[0]==0x484F5354
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*2048;got=list(struct.unpack_from('<7q',report,p))
  assert got==c['expected'],(c['name'],got,c['expected'])
  wire=bytes.fromhex(c['wire'])
  assert report[p+64:p+64+1514]==wire+b'\xa5'*(1514-len(wire)),c['name']
 return dict(cases=len(cases),passed=True)
