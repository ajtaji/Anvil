import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import board_run as br
GOOD='a'*64
class Fake:
 def __init__(self,mode='ok'):
  self.mode=mode;self.addr=('192.168.1.114',5555);self.transcript=[];self.closed=False;self.commands=[]
 def at_prompt(self,timeout):return self.mode!='silent'
 def command(self,line,seconds):
  self.commands.append(line)
  if self.mode=='timeout':raise br.CommandTimeout(line,seconds,0,0,False)
  return 'The sha256sum is '+(GOOD if self.mode=='ok' else 'b'*64)
 def close(self):self.closed=True
def check(modes,expected):
 old=Fake();xs=[Fake(x) for x in modes]
 with patch.object(br,'NetConsole',side_effect=xs) as create:
  try:
   result,record=br.verify_upload_after_reply_loss(old,0x1000000,2582520,GOOD)
   assert expected=='ok' and result is old and record['attempt']==len(modes)
   assert record['verified_by']=='destination_range_sha256'
  except br.UploadDigestMismatch:assert expected=='mismatch'
  except br.StreamError:assert expected=='silent'
  assert create.call_count==len(modes)
 assert all(c.startswith('sha256sum ') for x in xs for c in x.commands)
check(['ok'],'ok')
check(['silent','ok'],'ok')
check(['timeout','silent','ok'],'ok')
check(['silent','silent','silent'],'silent')
check(['bad'],'mismatch')
print('PASS: five bounded upload recovery cases; no upload/boot/reset retries')

class TransferFake(Fake):
 def __init__(self,mode='ok'):
  super().__init__(mode)
  self.accepted_datagrams=[];self.keepalives=0
 def settle(self,**kwargs):return ''
 def keepalive(self):pass
 def send(self,line):self.commands.append(line)
 def read_until_or_prompt(self,line,needles,timeout,seen=''):
  if needles==['for ONE connection']:
   return line+'\nListening for ONE connection\n','needle'
  return 'Received 4 bytes in 1 ms\nsha256 '+(GOOD if self.mode=='ok' else 'b'*64),'needle'

for second,expected in [('ok','ok'),('bad','mismatch'),('silent','silent')]:
 first=TransferFake('bad')
 fresh=[TransferFake(second) for _ in range(3)]
 with patch.object(br,'NetConsole',side_effect=fresh), patch.object(br,'stream_file',return_value=0.01) as stream:
  try:
   result=br.verified_ram_upload(first,'192.168.1.114',5001,0x1000000,b'data',GOOD)
   assert expected=='ok' and len(result['reuploads'])==1
  except br.UploadDigestMismatch:assert expected=='mismatch'
  except br.StreamError:assert expected=='silent'
  assert stream.call_count==(1 if expected=='silent' else 2)
 assert all(c.startswith('net recv ') for x in [first,*fresh] for c in x.commands)
print('PASS: one verified-mismatch resend, second mismatch refusal, fresh-prompt requirement')


# A TCP reset can leave either a complete or partial image. The same bounded
# RAM verification decides whether to accept it, resend once, or stop.
for mode in ['complete', 'partial', 'twice', 'unknown']:
 first=TransferFake('ok')
 fresh=TransferFake('ok')
 failures=[ConnectionResetError('connection reset')] if mode in ['complete','unknown'] else [ConnectionResetError('connection reset'), 0.01 if mode=='partial' else ConnectionResetError('connection reset again')]
 def recover(console,address,size,want):
  if mode in ['partial','twice']:raise br.UploadDigestMismatch('partial RAM image')
  if mode=='unknown':raise br.StreamError('three bounded verification probes failed')
  return console,dict(bytes=4,sha256=GOOD,verified_by='destination_range_sha256',attempt=1)
 with patch.object(br,'stream_file',side_effect=failures) as stream, patch.object(br,'verify_upload_after_reply_loss',side_effect=recover) as verify, patch.object(br,'NetConsole',return_value=fresh):
  try:
   result=br.verified_ram_upload(first,'192.168.1.114',5001,0x1000000,b'data',GOOD)
   assert mode in ['complete','partial']
   assert len(result['send_interruptions'])==1
   assert len(result.get('reuploads',[]))==(1 if mode=='partial' else 0)
  except br.UploadDigestMismatch:assert mode=='twice'
  except br.StreamError:assert mode=='unknown'
  assert stream.call_count==(2 if mode in ['partial','twice'] else 1)
  assert verify.call_count==(2 if mode=='twice' else 1)
 assert all(c.startswith('net recv ') for x in [first,fresh] for c in x.commands)
print('PASS: TCP interruption accepts verified full RAM, resends known partial once, refuses second/unknown')


import hashlib
class ChunkFake(TransferFake):
 payload=b''
 def read_until_or_prompt(self,line,needles,timeout,seen=''):
  if needles==['for ONE connection']:return line+'\nListening for ONE connection\n','needle'
  return f'Received {len(self.payload)} bytes in 1 ms\nsha256 '+hashlib.sha256(self.payload).hexdigest(),'needle'
for final_bad in [False,True]:
 console=ChunkFake();writes=[];data=b'0123456789';digest=hashlib.sha256(data).hexdigest()
 def send(ip,port,part,**kwargs):console.payload=part;writes.append(part);return 0.01
 def verify(console,address,size,want):
  assert address==0x1000000 and size==10 and want==digest
  if final_bad:raise br.UploadDigestMismatch('whole range mismatch')
  return console,dict(bytes=size,sha256=want,verified_by='destination_range_sha256')
 with patch.object(br,'RAM_UPLOAD_CHUNK_BYTES',4),patch.object(br,'stream_file',side_effect=send),patch.object(br,'verify_upload_after_reply_loss',side_effect=verify) as complete:
  try:
   result=br.verified_ram_upload(console,'192.168.1.114',5001,0x1000000,data,digest)
   assert not final_bad and len(result['chunks'])==3 and result['bytes']==10
  except br.UploadDigestMismatch:assert final_bad
  assert writes==[b'0123',b'4567',b'89'] and complete.call_count==1
 assert console.commands==['net recv 5001 1000000','net recv 5001 1000004','net recv 5001 1000008']
print('PASS: bounded chunks use offset addresses and require complete-range digest before returning')
