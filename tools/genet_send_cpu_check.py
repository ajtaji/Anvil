"""Check physical GENET ownership traces with independently specified outcomes."""
import struct

def check(raw,cases):
 assert struct.unpack_from('<2q',raw)==(0x474E5431,len(cases))
 for i,c in enumerate(cases):
  p=256+i*2048;actual=list(struct.unpack_from('<10q',raw,p))
  assert actual==c['expected'],(i,c['name'],actual,c['expected'])
  expected=bytes((j*7+3)&255 for j in range(c['copied']))+bytes(1536-c['copied'])
  assert raw[p+80:p+80+1536]==expected,(i,c['name'],'owned DMA bytes')
 return dict(passed=True,cases=len(cases),scope='physical CPU with controlled register access; no Ethernet wire claim')
