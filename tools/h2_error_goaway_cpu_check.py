"""Independently validate error codes, exact wire framing and bounded failure ownership."""
import struct
from hpack import Decoder

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x48324843 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*8192;name=c['name']
  assert q(p)==c['result'],(name,'result',q(p),c['result'])
  assert q(p+64)==1,(name,'single close',q(p+64))
  assert q(p+72)==1 and q(p+80)==c['original_error'],(name,'latched original',q(p+72),q(p+80))
  assert q(p+88)==q(p+96),(name,'received while draining')
  assert q(p+136)==-3251,(name,'accepted new request',q(p+136))
  assert q(p+128)==(0 if c['mode']==15 else -1),(name,'final state',q(p+128))
  assert 0<q(p+56)<100000,(name,'not bounded')
  wire=data[p+256:p+256+q(p+32)]
  assert wire[:24]==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
  at=24;goaway=[];requests=0;pings=0;partial=False
  while at<len(wire):
   if c.get('partial') and len(wire)-at<17:
    expected=b'\x00\x00\x08\x07'+bytes(13)
    assert 0<len(wire)-at<17 and wire[at:]==expected[:len(wire)-at],(name,'partial GOAWAY prefix')
    assert q(p+104)==len(wire)-at,(name,'partial write offset')
    partial=True;break
   assert at+9<=len(wire),(name,'partial frame header')
   n=int.from_bytes(wire[at:at+3],'big');kind=wire[at+3];flags=wire[at+4];sid=int.from_bytes(wire[at+5:at+9],'big')
   if at+9+n>len(wire):
    assert c.get('partial') and kind==7 and n==8 and sid==0 and flags==0,(name,'unexpected partial frame')
    assert wire[at+9:]==bytes(len(wire)-at-9),(name,'partial graceful GOAWAY content')
    partial=True;break
   b=wire[at+9:at+9+n];at+=9+n
   if kind==1:
    assert flags==5 and sid==1
    assert dict(Decoder().decode(b))=={':method':'GET',':scheme':'https',':path':'/test?x=1',':authority':'example.org'}
    requests+=1
   elif kind==7:
    assert n==8 and sid==0 and flags==0 and b[:4]==bytes(4)
    goaway.append(int.from_bytes(b[4:],'big'))
    if goaway[-1]!=0:assert at==len(wire),(name,'output after error GOAWAY')
   elif kind==6:
    assert c['mode']==10 and flags==1 and sid==0 and b==b'12345678';pings+=1
   else:assert kind==4,(name,'unexpected frame',kind)
  assert requests==1 and goaway==c['goaway'],(name,'GOAWAY',goaway,c['goaway'])
  assert partial==c.get('partial',False),(name,'deadline truncation',partial)
  assert pings==(60 if c['mode']==10 else 0),(name,'queued controls',pings)
  if c['mode'] in (17,18):assert q(p+104)>0 and q(p+112)==1,(name,'no partial graceful output',q(p+104))
  if c['mode']==16:assert q(p+120)==65537
  if c['mode'] in (10,17,20):assert q(p+160)==5,(name,'premature TLS close',q(p+160))
  if c['mode']==21:assert q(p+160)==1
  if c['mode']==22:assert q(p+160)>4
  if c['mode']==23:assert q(p+160)==0
 return dict(cases=len(cases),error_goaway=True,no_receive_during_error_drain=True,original_error_preserved=True,complete_http2_client=False)
