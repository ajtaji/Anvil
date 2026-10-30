"""Validate uninterrupted request framing before the connection-error GOAWAY."""
import struct
from hpack import Decoder

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x48325550 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*120000;name=c['name'];mode=c['mode']
  assert q(p)==c['error'] and q(p+64)==1,(name,'failure/close',q(p),q(p+64))
  assert q(p+88)>9 and q(p+120)==1 and q(p+128)==-3203 and q(p+136)==-1,(name,'not a partial frame at failure')
  assert q(p+104)==q(p+112),(name,'received after failure')
  wire=data[p+256:p+256+q(p+32)]
  assert wire[:24]==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
  at=24;block=b'';headers=[];continuing=False;header_frames=0;payload=b'';pings=0;goaway=0;last_header=0
  while at<len(wire):
   assert at+9<=len(wire),(name,'partial header')
   n=int.from_bytes(wire[at:at+3],'big');kind=wire[at+3];flags=wire[at+4];sid=int.from_bytes(wire[at+5:at+9],'big')
   assert at+9+n<=len(wire),(name,'partial payload')
   b=wire[at+9:at+9+n];at+=9+n
   if continuing:assert kind==9 and sid==1,(name,'interrupted CONTINUATION')
   if kind in (1,9):
    assert sid==1 and (kind==9)==continuing
    block+=b;header_frames+=1;continuing=not bool(flags&4)
    if not continuing:headers=Decoder().decode(block);last_header=at
   elif kind==0:
    assert mode==0 and sid==1 and flags==0 and headers;payload+=b
   elif kind==6:
    assert mode==9 and headers and sid==0 and flags==1 and b==b'12345678';pings+=1
   elif kind==7:
    assert not continuing and headers and sid==0 and flags==0 and b==bytes(7)+b'\x06' and at==len(wire)
    goaway+=1
   else:assert kind==4
  assert goaway==1 and not continuing and pings==(60 if mode==9 else 0)
  h=dict(headers)
  assert h[':method']==('POST' if mode==0 else 'GET') and h[':path']=='/upload' and h[':authority']=='example.org' and h[':scheme']=='https'
  assert h['x-test']=='value' and h['cookie']=='a=b; c=d'
  if mode==0:
   assert q(p+8)==16375 and payload==b'a'*16375 and header_frames==1 and q(p+96)==0
   assert last_header<q(p+144)<last_header+9+16375
  else:
   assert not payload and header_frames==2 and q(p+96)>16384 and q(p+144)<last_header
   assert sum(k=='x-large' and v=='L'*1000 for k,v in headers)==31
 return dict(cases=len(cases),partial_data_completed=True,continuation_order_preserved=True,queued_controls_preserved=True)
