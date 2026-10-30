"""Compare emitted transcript bytes with independent hashlib expectations."""
import struct

def check(raw,cases):
 def q(p):return struct.unpack_from('<q',raw,p)[0]
 assert q(0)==0x54524131 and q(8)==len(cases)
 rows=[]
 for i,c in enumerate(cases):
  p=256+i*128
  assert q(p)==c['rc'] and q(p+8)==c['err'],(i,'return/error',q(p),q(p+8))
  assert q(p+16)==(10 if c['rc']==0 else 0),(i,'terminal state')
  assert raw[p+64:p+96].hex()==c['expected'],(i,'transcript digest')
  expected_calls=0 if c['mode']==0 or c['err']==27 else c['cancel'] or ((c['bytes']+511)//512+1)
  assert q(p+24)==expected_calls,(i,'yield boundaries',q(p+24),expected_calls)
  assert q(p+56)==(0 if c['rc']==0 else -1),(i,'terminal retry')
  rows.append(dict(bytes=c['bytes'],cancel=c['cancel'],calls=q(p+24),max_interval_us=q(p+32),synchronous_us=q(p+40),elapsed_us=q(p+48)))
 return dict(passed=True,cases=len(cases),rows=rows)
