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
