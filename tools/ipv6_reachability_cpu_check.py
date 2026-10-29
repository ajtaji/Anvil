"""Check neighbor state, MAC preservation, routing invalidation and timers."""
import struct
def check(raw,cases):
 assert struct.unpack_from('<qq',raw)==(0x49503635,len(cases))
 for i,c in enumerate(cases):
  actual=list(struct.unpack_from('<6q',raw,256+i*64))
  assert actual==c['expected'],(i,c['name'],actual,c['expected'])
 return dict(passed=True,cases=len(cases))
