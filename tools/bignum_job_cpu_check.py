"""Check actual board results against Python integer modular exponentiation."""
import struct

def check(report,cases):
 def q(p):return struct.unpack_from('<q',report,p)[0]
 assert q(0)==0x42504a31 and q(8)==len(cases)
 timings=[]
 for i,c in enumerate(cases):
  p=256+i*1024;n=c['bytes']
  assert q(p)==1 and q(p+8)==1,(i,'completion')
  assert q(p+16)==c['calls'],(i,'budget')
  assert report[p+128:p+128+n].hex()==c['expected'],(i,'first result')
  assert report[p+384:p+384+n].hex()==c['expected'],(i,'interleaved result')
  assert q(p+48)==-1,(i,'invalid budget')
  assert q(p+56)==(-2 if c['exponent_bytes'] else 0),(i,'busy refusal')
  assert q(p+64)==1 and q(p+72)==-1,(i,'wipe/cancel')
  timings.append(dict(bits=c['bits'],max_step_us=q(p+24),begin_us=q(p+32),both_jobs_us=q(p+40)))
 return dict(passed=True,cases=len(cases),timings=timings)
