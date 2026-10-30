"""Validate concurrent public HTTP/2 traffic, including receive-window refill."""
import struct,json,uuid,hashlib
def check(data,cases):
 def q(offset):return struct.unpack_from('<q',data,offset)[0]
 assert q(0)==0x48324832
 assert q(8)==0,('client result',q(8))
 assert q(16)==q(24)==len(cases)==2 and q(56)==2
 replies=[]
 for i in range(2):
  p=256+i*64
  if i==0 and cases[0].endswith('/delay/5'):
   assert q(64)==1 and q(p+24)==2 and q(p+16)==0
   replies.append(dict(url=cases[i],cancelled=True));continue
  assert q(p)==200 and q(p+8)>=2 and q(p+24)==1
  n=q(p+16);assert 0<n<=131072
  body=data[4096+i*131072:4096+i*131072+n]
  if i==0:uuid.UUID(json.loads(body)['uuid'])
  else:assert n==70000
  replies.append(dict(url=cases[i],bytes=n,sha256=hashlib.sha256(body).hexdigest()))
 return dict(replies=replies,peak_active_streams=q(56),max_step_us=q(32),max_service_us=q(40),elapsed_us=q(48),complete_http2_client=False)
