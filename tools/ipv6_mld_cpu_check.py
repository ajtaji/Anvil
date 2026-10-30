"""Validate physical MLD output against independently encoded packets."""
import struct

def check(raw,cases):
 assert struct.unpack_from('<2q',raw)==(0x4d4c4431,len(cases))
 for i,c in enumerate(cases):
  p=256+i*256
  assert list(struct.unpack_from('<6q',raw,p))==[c['rc']]+c['query'],(i,c['name'],list(struct.unpack_from('<6q',raw,p)))
  assert list(struct.unpack_from('<8q',raw,p+192))==c.get('policy',[0]*8),(i,c['name'],'interface policy',list(struct.unpack_from('<8q',raw,p+192)))
  assert raw[p+64:p+192]==bytes.fromhex(c['output']),(i,c['name'],'wire bytes or output guard')
 return dict(passed=True,cases=len(cases),scope='physical CPU MLD codec and interface compatibility; no live membership claim')
