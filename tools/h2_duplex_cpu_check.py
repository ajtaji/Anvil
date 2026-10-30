"""Check bounded duplex progress, exact frames and failure ownership on the Pi."""
import struct
from hpack import Decoder

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x48324155 and q(8)==len(cases)==7
 for index,c in enumerate(cases):
  p=256+index*32768;mode=c['mode'];label=c['name'];success=c['error']==0
  assert q(p)==c['error'],(label,'result',q(p))
  assert q(p+8)==16375 and q(p+200)==1,(label,'stalled accepted upload')
  assert q(p+72)==1 and q(p+192)==1,(label,'single ownership')
  assert q(p+64)==2 and q(p+56)==2
  if success:
   assert q(p+24)==413 and q(p+16)==2 and data[p+25000:p+25002]==b'no',label
   assert q(p+40)==2 and q(p+48)==9 and q(p+120)==0,label
   assert q(p+168)==len(bytes.fromhex(c['wire'])) and q(p+232)==65535,label
   assert q(p+144)==(-1 if mode==30 else 53625),label
  else:
   assert q(p+40)==-1 and q(p+16)==0 and q(p+24)==0,label
  if mode==26:assert q(p+224)==1,'retained DATA prevented outgoing progress'
  if mode==27:assert q(p+240)==1020,'queue overflow boundary'
  wire=data[q(p+96):q(p+96)+q(p+32)]
  assert wire[:24]==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
  assert q(p+152)==len(wire) and q(p+160)==q(p+168)
  at=24;upload=b'';headers={};resets=[];credits=[];pings=[];settings=0;partial=False
  while at<len(wire):
   assert at+9<=len(wire),label
   n=int.from_bytes(wire[at:at+3],'big');kind=wire[at+3];flags=wire[at+4];sid=int.from_bytes(wire[at+5:at+9],'big');body=wire[at+9:at+9+n]
   if len(body)!=n:
    assert not success and kind==0 and sid==1 and body==b'a'*88,(label,'partial frame')
    partial=True;break
   if kind==0:assert flags==0 and sid==1;upload+=body
   if kind==1:headers=dict(Decoder().decode(body))
   if kind==3:resets.append((sid,int.from_bytes(body,'big')))
   if kind==8:credits.append((sid,int.from_bytes(body,'big')))
   if kind==6:assert flags==1 and sid==0;pings.append(body)
   if kind==4 and flags==1:settings+=1
   at+=9+n
  assert headers[':method']=='POST' and headers[':path']=='/upload' and headers[':authority']=='example.org'
  if mode==30:assert 'content-length' not in headers and 'transfer-encoding' not in headers
  else:assert headers['content-length']=='70000'
  if success:
   assert not partial and upload==b'a'*16375 and resets==[(1,0)] and credits==[(0,2)],label
   assert pings==([b'12345678'] if mode==25 else []),label
   assert settings==(2 if mode==25 else 1),label
  else:assert partial and not upload and not resets and not credits,label
 return dict(cases=7,stalled_write_zero_and_busy=True,retained_event_transmit=True,bounded_control_queue=True,exact_wire=True)
