"""Check DMA queue and completion latch traces from the physical CPU."""
import struct

def check(raw,cases):
 assert struct.unpack_from('<2q',raw)==(0x444D5131,len(cases))
 for i,c in enumerate(cases):
  p=256+i*2048;actual=list(struct.unpack_from('<10q',raw,p))
  assert actual==c['expected'],(i,c['name'],actual,c['expected'])
  expected=bytes((j*7+c['seed'])&255 for j in range(c['copied']))+bytes(1514-c['copied'])
  assert raw[p+80:p+80+1514]==expected,(i,c['name'],'owned frame bytes')
 return dict(passed=True,cases=len(cases),scope='physical CPU, controlled driver completion; no Ethernet wire claim')
