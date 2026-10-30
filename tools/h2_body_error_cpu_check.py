"""Verify rejected bodies do not leak or consume sibling connection credit."""
import struct
from h2_stream_window_cpu_check import check as check_stream

def check(data,cases):
 result=check_stream(data,cases)
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 for i,c in enumerate(cases):
  p=256+i*8192
  assert q(p+104)==0,(c['name'],'unflushed discarded credit')
  if c['result']==0:assert q(p+112)==65535,(c['name'],'connection credit',q(p+112))
 result.pop('stream_window_error_isolation',None)
 result.update(response_body_error_isolation=True,discarded_connection_credit=True)
 return result
