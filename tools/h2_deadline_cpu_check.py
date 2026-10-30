"""Verify independent deadlines, preserved events and exact HTTP2 reset traffic."""
import struct
from hpack import Decoder

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x48324843 and q(8)==len(cases)==8
 for i,c in enumerate(cases):
  p=256+i*8192;mode=c['mode'];label=c['name']
  assert q(p)==0,(label,'result',q(p))
  assert (q(p+8),q(p+16))==(c['body_bytes'],c['body_sum']),(label,'body',q(p+8),q(p+16))
  assert q(p+24)==2 and q(p+64)==1,(label,'completion/ownership')
  assert q(p+72)==c['reset_mask'] and q(p+80)==c['expired'],(label,'isolated reset')
  assert q(p+88)==int(mode in (11,12)) and q(p+96)==int(mode==17),(label,'retained event/deferred queue')
  wire=data[p+256:p+256+q(p+32)];at=24;requests=[];resets=[];credit=0;pings=0;dec=Decoder()
  assert wire[:24]==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
  while at<len(wire):
   assert at+9<=len(wire)
   n=int.from_bytes(wire[at:at+3],'big');kind=wire[at+3];flags=wire[at+4];sid=int.from_bytes(wire[at+5:at+9],'big');body=wire[at+9:at+9+n]
   assert len(body)==n,(label,'truncated frame')
   if kind==1:
    assert flags==5
    assert dict(dec.decode(body))=={':method':'GET',':scheme':'https',':authority':'example.org',':path':'/test?x=1'}
    requests.append(sid)
   if kind==3:resets.append((sid,int.from_bytes(body,'big')))
   if kind==8:assert sid==0;credit+=int.from_bytes(body,'big')
   if kind==6:assert mode==17 and flags==1 and body==bytes(8);pings+=1
   at+=9+n
  assert requests==[1,3],label
  assert resets==([(1,8),(3,8)] if mode==16 else ([(1,8)] if c['expired'] else [])),(label,resets)
  assert credit==(0 if mode==16 else 5),(label,'connection credit',credit)
  assert pings==(60 if mode==17 else 0),label
 return dict(cases=8,independent_stream_deadlines=True,retained_events=True,wrap32=True,queue_backpressure=True)
