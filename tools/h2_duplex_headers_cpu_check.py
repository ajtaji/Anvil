"""Independent HPACK and frame-order checks for simultaneous header traffic."""
import struct
from hpack import Decoder

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 p=256
 assert q(0)==0x48325550 and q(8)==len(cases)==1
 assert q(p)==0,('result',q(p))
 assert q(p+8)==0 and q(p+16)==0 and q(p+24)==200
 assert q(p+64)==1 and q(p+72)==5 and q(p+80)==0
 assert q(p+88)==1 and q(p+96)==2,'no proved overlap or incomplete streams'
 wire=data[p+256:p+256+q(p+32)];at=24;block=b'';continued=0;headers={};decoder=Decoder(max_header_list_size=65536);ping=0;continuations=0
 assert wire[:24]==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
 while at<len(wire):
  assert at+9<=len(wire)
  n=int.from_bytes(wire[at:at+3],'big');kind=wire[at+3];flags=wire[at+4];sid=int.from_bytes(wire[at+5:at+9],'big');body=wire[at+9:at+9+n]
  assert len(body)==n
  if continued:assert kind==9 and sid==continued,'interleaved CONTINUATION'
  if kind in (1,9):
   if kind==1:assert flags&1 and not block
   if kind==9:continuations+=1
   block+=body;continued=0 if flags&4 else sid
   if flags&4:headers[sid]=decoder.decode(block);block=b''
  if kind==6:
   assert flags==1 and sid==0 and body==b'12345678' and 3 in headers
   ping+=1
  assert kind not in (0,3,8)
  at+=9+n
 assert not block and not continued and continuations==1 and ping==1
 assert dict(headers[1])=={':method':'GET',':scheme':'https',':authority':'example.org',':path':'/first'}
 h=dict(headers[3]);assert h[':method']=='GET' and h[':path']=='/upload' and h['x-test']=='value' and h['cookie']=='a=b; c=d'
 large=[v for k,v in headers[3] if k=='x-large'];assert large==['L'*1000]*31
 return dict(overlapping_header_directions=True,requests=2,large_header_bytes=31000,continuation_preserved=True,ping_deferred_until_header_end=True)
