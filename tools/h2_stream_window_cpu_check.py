"""Verify isolated resets, exact wire codes, sibling responses and queue pressure."""
import struct
from h2_client_cpu_check import check as check_client

def check(data,cases):
 result=check_client(data,cases)
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 for i,c in enumerate(cases):
  p=256+i*8192
  assert q(p+72)==(c['resets'][0][1] if c['resets'] else 0),c['name']
  assert q(p+80)==c['local_error'],c['name']
  assert q(p+88)==(1 if c['mode']==9 else 0),c['name']
  assert q(p+96)==(3 if c['result']==0 else -1),c['name']
  out=data[p+256:p+256+q(p+32)];at=24;pings=0
  while at<len(out):
   n=int.from_bytes(out[at:at+3],'big')
   if out[at+3]==6:pings+=1
   at+=9+n
  assert pings==(60 if c['mode']==9 else 0),c['name']
 result.update(stream_window_error_isolation=True,queue_congestion=True)
 return result
