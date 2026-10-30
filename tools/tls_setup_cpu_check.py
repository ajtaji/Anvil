"""Validate setup cancellation, entropy refusal and bounded retry decisions."""
import struct

def check(raw,cases):
 def q(p):return struct.unpack_from('<q',raw,p)[0]
 assert q(0)==0x54534b31 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*128
  actual=[q(p+8*j) for j in range(7)]
  expected=[c['rc'],c['err'],10 if c['rc']==0 else 0,c['draws'],c['derives'],c['checks'],32 if c['rc']==1 else 0]
  assert actual==expected,(i,actual,expected)
  assert q(p+56)==(32 if c['draws']>=2 and c['fail']!=2 else 0),(i,'session id publication')
 return dict(passed=True,cases=len(cases),scope='scheduling and refusal with RNG/key-derivation doubles; no cryptographic correctness claim')
