"""Check fragmented transport and malformed-message CPU results."""
import struct
from hpack import Decoder
def check(data,cases):
 def q(p):return struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x48324843 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*8192
  assert q(p)==c['result'],(c['name'],'result',q(p),c['result'])
  assert (q(p+8),q(p+16))==(c['body_bytes'],c['body_sum']),(c['name'],'body',q(p+8),q(p+16))
  assert q(p+64)==1,(c['name'],'close ownership',q(p+64))
  out=data[p+256:p+256+q(p+32)]
  assert out[:24]==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
  at=24;requests=0;credit=0;ping=False;dec=Decoder()
  while at+9<=len(out):
   n=int.from_bytes(out[at:at+3],'big');kind=out[at+3];flags=out[at+4];sid=int.from_bytes(out[at+5:at+9],'big')
   assert at+9+n<=len(out),(c['name'],'partial outbound frame')
   b=out[at+9:at+9+n];at+=9+n
   if kind==1:
    assert flags==5 and sid==requests*2+1
    assert dict(dec.decode(b))=={':method':'GET',':scheme':'https',':path':'/test?x=1',':authority':'example.org'}
    requests+=1
   if kind==8 and sid==0:credit+=int.from_bytes(b,'big')
   if kind==6:assert flags==1 and b==b'12345678';ping=True
  assert at==len(out) and requests==c['requests'],c['name']
  if c['name']=='two streams with persistent HPACK':assert credit==9
  if c['name']=='PING acknowledged':assert ping
  if c['name']=='body exceeds initial receive window':assert credit==70000
 return dict(cases=len(cases),refusals=sum(x['result']<0 for x in cases),fragmented_send_bytes=3,fragmented_receive_bytes=5,complete_http2_client=False)
