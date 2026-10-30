"""Verify expiry of one real HTTPS stream while its sibling completes."""
import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x48324832 and q(8)==0,('probe result',q(8))
 assert cases==['https://httpbin.org/delay/5','https://httpbin.org/bytes/70000']
 assert q(0x10)==2 and q(0x18)==2 and q(0x38)==2
 assert q(0x40)==1 and q(0x48)==-3255
 assert q(0x100)==0 and q(0x110)==0 and q(0x118)==2,'delayed stream did not expire'
 assert q(0x140)==200 and q(0x150)==70000 and q(0x158)==1,'sibling request failed'
 return dict(expired_stream=1,completed_stream=3,completed_bytes=70000,elapsed_us=q(0x30),max_step_us=q(0x20),max_service_us=q(0x28))
