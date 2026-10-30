"""Check physical scoped DNS selection with controlled hardware-state doubles."""
import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==131072 and q(0)==0x52445343 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*64
  assert q(p)==c['rc'],(c['name'],q(p),c['rc'])
  expected=bytes.fromhex('fe8000000000000000000000000000')+bytes([c['source']]) if c['source'] else b'\xa5'*16
  assert data[p+40:p+56]==expected,c['name']
  assert data[p+56:p+64]==b'\xa5'*8,c['name']
 assert q(256+9*64+8)==1 and q(256+9*64+16)==1
 assert q(256+15*64+8)==2 and q(256+15*64+16)==1
 assert data[256+15*64+24:256+15*64+40]==bytes.fromhex('fe800000000000000000000000000035')
 assert data[256+len(cases)*64:]==b'\xa5'*(len(data)-256-len(cases)*64)
 return dict(cases=len(cases),passed=True)
