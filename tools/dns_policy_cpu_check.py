"""Check resolver precedence and unchanged lease/routing inputs."""
import struct,ipaddress

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==131072 and q(0)==0x444e5350 and q(8)==12
 expected=[0x08080808,0x01010101,0,0x01010101,0,0,0,0,0x08080808,0,0,0x08080404]
 routes=[1,1,2,2,1,1,1,0,1,1,0,2];used=set(range(16))
 for i in cases:
  p=256+i*32;used.update(range(p,p+24))
  lease=0 if i==9 else 0x08080404 if i==11 else 0x08080808
  assert [q(p),q(p+8),q(p+16)]==[expected[i],lease,routes[i]],i
 for i in range(12):
  p=4096+i*32;used.update(range(p,p+24))
  good={1:'2001:4860:4860::8888',2:'fd12:3456:789a::53',3:'fe80::1'}
  assert q(p)==(16 if i in good else 0 if i==0 else -1),(i,q(p))
  assert data[p+8:p+24]==(ipaddress.IPv6Address(good[i]).packed if i in good else b'\xa5'*16),i
 assert all(v==165 for i,v in enumerate(data) if i not in used)
 return dict(cases=24,lease_and_route_unchanged=True)
