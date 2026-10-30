"""Check physical group scheduling, packet bytes and retained source storage."""
import struct

def check(raw,cases):
 assert struct.unpack_from('<2q',raw)==(0x4d475231,len(cases))
 for i,c in enumerate(cases):
  p=256+i*4096
  actual=list(struct.unpack_from('<11q',raw,p))
  assert actual==c['expected'],(i,c['name'],actual,c['expected'])
  assert raw[p+128:p+1628]==bytes.fromhex(c['packet']),(i,c['name'],'packet/guard')
  assert raw[p+1728:p+3152]==bytes.fromhex(c['sources']),(i,c['name'],'owned source list')
 return dict(passed=True,cases=len(cases),scope='physical CPU per-group MLD scheduler; no live multicast claim')
