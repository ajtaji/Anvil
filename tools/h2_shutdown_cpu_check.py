"""Check graceful GOAWAY, response draining and single transport ownership."""
import struct
from hpack import Decoder

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x48324843 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*8192;mode=c['mode'];label=c['name'];success=c['result']==0
  assert q(p)==c['result'],(label,'result',q(p))
  assert (q(p+8),q(p+16))==(c['body_bytes'],c['body_sum']),(label,'body')
  assert q(p+64)==1 and q(p+72)==1,(label,'ownership/start')
  assert q(p+80)==(5 if success else -1) and q(p+88)==int(mode!=24),label
  if success:assert q(p+24)==c['wanted'],label
  wire=data[p+256:p+256+q(p+32)];at=24;dec=Decoder();requests=[];goaway=[];reset=[];credit=0;pings=0
  assert wire[:24]==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
  while at<len(wire):
   assert at+9<=len(wire)
   n=int.from_bytes(wire[at:at+3],'big');kind=wire[at+3];flags=wire[at+4];sid=int.from_bytes(wire[at+5:at+9],'big');body=wire[at+9:at+9+n]
   assert len(body)==n,(label,'partial frame')
   if kind==1:
    assert flags==5 and dict(dec.decode(body))=={':method':'GET',':scheme':'https',':authority':'example.org',':path':'/test?x=1'}
    requests.append(sid)
   if kind==6:assert mode==28 and flags==1 and body==bytes(8);pings+=1
   if kind==7:assert sid==0 and flags==0;goaway.append(body)
   if kind==3:reset.append((sid,int.from_bytes(body,'big')))
   if kind==8:assert sid==0;credit+=int.from_bytes(body,'big')
   at+=9+n
  assert requests==([] if mode==20 else ([1] if mode==24 else [1,3])),(label,requests)
  assert goaway==([] if mode==24 else [bytes(8)]),(label,'GOAWAY',goaway)
  assert reset==([(1,8)] if mode==27 else []),(label,reset)
  assert pings==(60 if mode==28 else 0),label
  assert credit==(0 if mode in (20,23,24) else 5),(label,credit)
 return dict(cases=len(cases),graceful_shutdown=True,retained_data=True,peer_goaway=True,deadline_and_cancel=True)
