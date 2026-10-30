"""Check production TLS queue ownership with controlled record/TCP doubles."""
import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x54445231 and q(8)==len(cases)==8
 expected=[1,0,-103,-105,-102,1,-105,0]
 for i in cases:
  p=256+i*256
  assert q(p)==(17 if i in (0,1,2,3,6) else 0),(i,'accepted bytes',q(p))
  assert q(p+24)==expected[i],(i,'drain result',q(p+24),expected[i])
  assert q(p+72)==1 and q(p+80)==0 and q(p+88)==0 and q(p+96)==-102,(i,'close ownership/invalidated handle')
  if i<3:assert q(p+8)==0 and q(p+16)==0,(i,'early completion')
  if i==0:
   assert q(p+32)==17 and data[p+128:p+145]==bytes(range(65,82)),(i,'copied plaintext')
   assert q(p+40)>=8 and q(p+48)==6 and q(p+56)==0 and q(p+64)==0
  else:assert q(p+32)==0,(i,'unexpected output')
  if i==1:assert q(p+40)==102 and q(p+48)==100 and q(p+64)==17
  if i==6:assert q(p+56)==17
 return dict(cases=8,queued_plaintext_not_drained=True,partial_records_not_drained=True,copied_buffer_preserved=True,transport_errors_preserved=True,real_crypto=False)
