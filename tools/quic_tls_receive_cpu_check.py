"""Check real TLS cryptography and receive-stream state together."""
import struct
from tls_quic_crypto_cpu_check import check as tls_check

def check(raw,cases):
 result=tls_check(raw,cases)
 for i,c in enumerate(cases):
  p=256+i*2048
  if 'step_error' in c:
   assert struct.unpack_from('<q',raw,p+32)[0]==c['step_error'],c['name']
   assert struct.unpack_from('<q',raw,p+56)[0]==-3428,(c['name'],'failure not terminal')
   assert struct.unpack_from('<q',raw,p+112)[0]==-3428,(c['name'],'failed stream accepted data')
  if 'phases' in c:assert list(struct.unpack_from('<3q',raw,p+64))==c['phases'],c['name']
  if 'bases' in c:assert list(struct.unpack_from('<3q',raw,p+88))==c['bases'],c['name']
  if c['mode'] in (0,1):assert struct.unpack_from('<q',raw,p+120)[0]==0,(c['name'],'sealed stream not idle')
 result['receive_stream_integration']=True
 return result
