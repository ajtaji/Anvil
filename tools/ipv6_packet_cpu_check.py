"""Validate exact IPv6 header bytes and bounded parser results."""
import struct

def check(raw,cases):
 def q(p):return struct.unpack_from('<q',raw,p)[0]
 assert q(0)==0x49503632 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*256
  assert q(p)==c['rc'],(i,c['name'],'result',q(p))
  assert q(p+72)==c['action'],(i,'option action')
  if c['rc']==0:
   actual=[q(p+j*8) for j in range(1,8)]
   assert actual==[c['packet_bytes'],c['offset'],c['payload_bytes'],c['protocol'],64,165,0x12345],(i,'view',actual)
   assert q(p+80)==40 and q(p+88)==1,(i,'build/guard')
   assert q(p+96)==c.get('fragmented',0),(i,'fragment flag')
   h=bytes.fromhex(c['header']);assert raw[p+128:p+168]==h,(i,'header')
   assert raw[p+176:p+208]==h[8:40],(i,'addresses')
 return dict(passed=True,cases=len(cases))
