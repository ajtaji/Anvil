"""Validate actual resident DNS results and unchanged report guards."""
import struct,ipaddress

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==131072 and q(0)==0x444e5336 and q(8)>=12 and q(16)==-102
 expected6={ipaddress.IPv6Address(a).packed for a in ['2606:4700:4700::1111','2606:4700:4700::1001']}
 expected4={0x01010101,0x01000001};used=set(range(24));rows=[];first6=None;first4=None
 for i in range(8):
  p=256+i*64;kind,rc,ms=q(p),q(p+8),q(p+16);used.update(range(p,p+24))
  assert 0<=ms<6000
  if i%2==0:
   addr=data[p+24:p+40];used.update(range(p+24,p+40))
   assert kind==28 and rc==16 and addr in expected6,(i,kind,rc,addr.hex())
   if first6 is None:first6=addr
   assert addr==first6
   value=str(ipaddress.IPv6Address(addr))
  else:
   assert kind==1 and rc in expected4,(i,kind,rc)
   if first4 is None:first4=rc
   assert rc==first4
   value=str(ipaddress.IPv4Address(rc))
  rows.append(dict(kind=kind,result=value,elapsed_ms=ms))
 assert all(v==165 for i,v in enumerate(data) if i not in used),'report guard changed'
 return rows
