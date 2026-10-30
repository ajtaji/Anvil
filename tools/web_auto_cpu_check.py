"""Independent response and outgoing HTTP wire checks for negotiated WebClient."""
import struct
from hpack import Decoder

def check(data,cases):
 def q(at):return struct.unpack_from('<q',data,at)[0]
 assert q(0)==0x48324155 and q(8)==len(cases)==24
 for index,c in enumerate(cases):
  p=256+index*32768;mode=c['mode'];label=c['name']
  assert q(p)==c['error'],(label,'result',q(p),c['error'])
  assert q(p+8)==c['upload'],(label,'accepted upload',q(p+8))
  body=bytes.fromhex(c['body'])
  assert q(p+16)==len(body) and data[p+25000:p+25000+len(body)]==body,(label,'body')
  assert q(p+24)==c['status'],(label,'status',q(p+24))
  assert q(p+64)==c['protocol'],(label,'protocol',q(p+64))
  assert q(p+56)==(2 if c['protocol']==2 else 1),(label,'version major')
  assert q(p+72)==1 and q(p+192)==1,(label,'single open/close',q(p+72),q(p+192))
  if c['error']==0:
   assert q(p+40)==2 and q(p+48)==9 and q(p+120)==0,(label,'completion')
   assert q(p+88)==int(c['reusable']),(label,'reuse decision')
  else:assert q(p+40)==-1 and q(p+48)!=9,(label,'failure state')
  assert q(p+112)==c.get('reset',0),(label,'reset code')
  offer=b'' if mode in (17,18,19) else b'\x02h2\x08http/1.1'
  assert q(p+128)==len(offer) and data[p+208:p+208+len(offer)]==offer,(label,'ALPN offer')
  first=q(p+96);wire=data[first:first+q(p+32)]
  metadata=data[p+20000:p+20000+q(p+80)]
  if c['protocol']==1:
   assert wire==b'GET /upload HTTP/1.1\r\nHost: example.org\r\nX-Test: value\r\n\r\n',(label,wire)
   assert metadata.startswith(b'HTTP/1.1 200 OK\r\n')
   assert q(p+176)==len(wire) and q(p+184)==q(p+168)
   continue
  if c['protocol']==0:
   assert wire==b'',(label,'bytes before negotiation')
   continue
  assert q(p+152)==len(wire) and q(p+160)==q(p+168),(label,'H2 wire counters')
  assert wire.startswith(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'),label
  at=24;decoder=Decoder();headers={};block=b'';uploads=b'';ends=set();resets=[];continued=0
  while at<len(wire):
   assert at+9<=len(wire),label
   n=int.from_bytes(wire[at:at+3],'big');kind=wire[at+3];flags=wire[at+4];sid=int.from_bytes(wire[at+5:at+9],'big')
   b=wire[at+9:at+9+n];assert len(b)==n,label;at+=9+n
   if continued:assert kind==9 and sid==continued,label
   if kind in (1,9):
    if kind==1:assert not block,label
    block+=b;continued=0 if flags&4 else sid
    if flags&4:headers[sid]=decoder.decode(block);block=b''
   if kind==0:uploads+=b
   if kind in (0,1) and flags&1:ends.add(sid)
   if kind==3:resets.append((sid,int.from_bytes(b,'big')))
  assert not block and not continued,label
  if mode==10:
   assert not headers and not uploads,label
   continue
  assert set(headers)==({1,3} if mode==14 else {1}),label
  for sid,fields in headers.items():
   h=dict(fields)
   assert h[':method']==(c['method'] if sid==1 else 'GET'),(label,h)
   assert h[':scheme']=='https' and h[':authority']=='example.org'
   assert h[':path']==('/second' if sid==3 else '/upload')
   if sid==1:assert h['x-test']=='value'
   assert 'connection' not in h and 'transfer-encoding' not in h
   assert all(not getattr(field,'indexable',True) for field in fields)
  expected=bytes(range(17)) if mode==2 else b'a'*c['upload']
  assert uploads==expected,(label,'exact uploaded bytes')
  if mode==4:assert resets==[(1,0)] and q(p+144)==995,(label,'early final response')
  else:assert resets==[],(label,'unexpected reset')
  if c['error']==0 and mode!=4:assert set(headers)<=ends,(label,'request end')
  if c['error']==0:assert metadata.startswith(b'HTTP/2 200\r\n') or (mode==4 and metadata.startswith(b'HTTP/2 413\r\n')),(label,metadata)
  if mode==0:
   assert metadata==b'HTTP/2 200\r\ncontent-length: 5\r\nx-trace: one\r\nx-trace: two\r\nset-cookie: a=1\r\nset-cookie: b=2\r\n\r\nx-trailer: done\r\n\r\n',metadata
   assert q(p+104)==1 and q(p+136)==5
  if mode==3:assert b'content-length: 42\r\n' in metadata and body==b''
  if mode==14:assert b'x-reused: same\r\n' in metadata and q(p+176)<len(wire)
 return {'cases':24,'automatic_webclient_dispatch':True,'reused_connection':True}
