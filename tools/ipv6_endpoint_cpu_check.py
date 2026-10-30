"""Independent state and wire-image checks for the physical IPv6 endpoint."""
import struct

def check(raw,cases):
 assert struct.unpack_from('<2q',raw)==(0x45503631,len(cases))
 for i,c in enumerate(cases):
  p=256+i*2048;actual=list(struct.unpack_from('<6q',raw,p))
  assert actual==c['expected'],(i,c['name'],actual,c['expected'])
  wire=bytes.fromhex(c['wire']);expected=wire+bytes([165])*(1514-len(wire))
  assert raw[p+64:p+64+1514]==expected,(i,c['name'],'wire bytes or output guard')
 return dict(passed=True,cases=len(cases),scope='physical CPU state and wire codecs; no live interface claim')
