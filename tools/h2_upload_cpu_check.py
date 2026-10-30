"""Independent wire checks for shared WebRequest HTTP/2 uploads."""
import struct
from hpack import Decoder
def check(data,cases):
 def q(at):return struct.unpack_from('<q',data,at)[0]
 assert q(0)==0x48325550 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*120000;mode=c['mode']
  assert q(p)==c['error'],(c['name'],'result',q(p),c['error'])
  assert q(p+64)==1,(c['name'],'close count')
  out=data[p+256:p+256+q(p+32)]
  assert out[:24]==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
  at=24;block=b'';headers=[];payload=b'';parts=[];resets=[];header_frames=0;continuing=False;local_end=False
  while at<len(out):
   assert at+9<=len(out)
   n=int.from_bytes(out[at:at+3],'big');kind=out[at+3];flags=out[at+4];sid=int.from_bytes(out[at+5:at+9],'big')
   assert at+9+n<=len(out)
   b=out[at+9:at+9+n];at+=9+n
   if continuing:assert kind==9 and sid==1
   if kind in [1,9]:
    assert sid==1
    if kind==1:assert not continuing;local_end=bool(flags&1)
    else:assert continuing and flags&1==0
    header_frames+=1;block+=b;continuing=not bool(flags&4)
    if not continuing:headers=Decoder().decode(block)
   if kind==0:
    assert sid==1 and not continuing
    payload+=b;parts.append(n)
    if flags&1:local_end=True
   if kind==3:resets.append((sid,int.from_bytes(b,'big')))
  assert not continuing
  if c['error']:
   assert not headers and not payload and q(p+40)==1 and q(p+48)==0 and q(p+72)==1 and q(p+80)==0,c['name']
   continue
  assert q(p+8)==c['upload'] and q(p+24)==c['status'] and q(p+40)==2,c['name']
  assert q(p+16)==(0 if mode in [4,6] else 2)
  h=dict(headers)
  assert h[':method']==c['method'] and h[':scheme']=='https' and h[':path']=='/upload' and h[':authority']=='example.org',h
  assert h['x-test']=='value' and h['cookie']=='a=b; c=d'
  assert all(not getattr(x,'indexable',True) for x in headers)
  assert 'connection' not in h and 'transfer-encoding' not in h
  if mode in [1,6]:assert h['content-length']==str(c['goal'])
  else:assert 'content-length' not in h
  expected=bytes(range(17)) if mode==2 else b'a'*c['upload']
  assert payload==expected,(c['name'],'upload bytes')
  if mode==1:assert parts==[16375,16375,16375,16375,35,4465],parts
  if mode==2:assert parts==[5,5,5,2],parts
  if mode==3:assert parts==[0]
  if mode==5:assert header_frames==2 and sum(k=='x-large' and v=='L'*1000 for k,v in headers)==31
  if mode==6:assert resets==[(1,0)] and not local_end
  else:assert not resets and local_end
 return dict(cases=len(cases),connection_window_exhaustion=True,stream_window_exhaustion=True,large_headers=True,complete_webclient_dispatch=False)
