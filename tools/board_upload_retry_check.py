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
