"""Independent retained-frame and counter checks for the physical CYW queue adapter."""
import struct

def check(raw,cases):
 assert struct.unpack_from('<2q',raw)==(0x43595131,len(cases))
 for i,c in enumerate(cases):
  p=256+i*2048;got=list(struct.unpack_from('<9q',raw,p));assert got==c['expected'],(i,c['name'],got,c['expected'])
  n=c['expected'][8];expected=bytes((j*7+c['seed'])&255 for j in range(n))+bytes(1514-n)
  assert raw[p+80:p+80+1514]==expected,(i,c['name'],'retained packet')
 expected_receipts=[0,1,-2,-2,1,0,1,-1,-2,1,-2,-2,-2]
 assert list(struct.unpack_from('<13q',raw,65536))==expected_receipts,('packet receipts',list(struct.unpack_from('<13q',raw,65536)))
 return dict(passed=True,cases=len(cases)+13,scope='shared hook routing and CYW queue lifecycle with controlled bus outcomes')
