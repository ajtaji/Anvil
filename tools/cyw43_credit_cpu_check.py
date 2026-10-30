"""Validate credit-wait policy; does not claim radio/SDIO qualification."""
import struct
def check(raw,cases):
 assert struct.unpack_from('<qq',raw)==(0x43524431,len(cases))
 for i,c in enumerate(cases):
  actual=list(struct.unpack_from('<6q',raw,256+i*64))
  assert actual==c['expected'],(i,c['name'],actual,c['expected'])
 return dict(passed=True,cases=len(cases),scope='compiled credit-poll policy with controlled RX events')
