"""Check real concurrent HTTPS responses complete before graceful close."""
import struct,json,uuid

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x48324832 and q(8)==0,('probe result',q(8))
 assert cases==['https://httpbin.org/uuid','https://httpbin.org/bytes/70000']
 assert q(0x10)==2 and q(0x18)==2 and q(0x38)==2
 assert q(0x50)==5 and q(0x58)==0,'transport not gracefully closed'
 assert q(0x100)==200 and q(0x118)==1
 uuid.UUID(json.loads(data[4096:4096+q(0x110)])['uuid'])
 assert q(0x140)==200 and q(0x150)==70000 and q(0x158)==1
 return dict(completed_streams=2,completed_bytes=q(0x110)+70000,graceful_close=True,elapsed_us=q(0x30),max_step_us=q(0x20),max_service_us=q(0x28))
