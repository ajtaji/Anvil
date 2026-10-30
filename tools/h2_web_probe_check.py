"""Verify an actual HTTP/2 GET response captured on the physical target."""
import struct,json,uuid

def check(raw,cases=None):
 magic,rc,body_bytes,count,frames,end,max_decode=struct.unpack_from('<7q',raw)
 assert magic==0x48324731 and rc==0,('probe result',magic,rc)
 assert 0<body_bytes<=4096 and count>0 and 2<=frames<=256
 fields=[];at=512
 for _ in range(count):
  n,v,sensitive=struct.unpack_from('<3q',raw,at);at+=24
  assert n>0 and v>=0 and at+n+v<=8192
  fields.append((raw[at:at+n],raw[at+n:at+n+v]));at+=n+v
 assert at==end
 assert [v for n,v in fields if n==b':status']==[b'200'],fields
 body=raw[8192:8192+body_bytes];parsed=json.loads(body);uuid.UUID(parsed['uuid'])
 lengths=[int(v) for n,v in fields if n==b'content-length'];assert all(n==body_bytes for n in lengths)
 assert any(n==b'content-type' and b'application/json' in v for n,v in fields),fields
 return dict(verified_http2_get=True,status=200,body_bytes=body_bytes,json_uuid=parsed['uuid'],frames=frames,decoded_headers=[(n.decode('ascii'),v.decode('latin1')) for n,v in fields],max_decode_step_us=max_decode,complete_http2_client=False)
