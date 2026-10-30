"""Compare complete two-interface state with hand-specified lifecycle results."""
import struct

def check(report,cases):
 assert len(report)==131072
 assert struct.unpack_from('<2q',report)==(0x52444c53,len(cases))
 for i,c in enumerate(cases):
  p=256+i*384
  assert struct.unpack_from('<q',report,p)[0]==c['rc'],c['name']
  got=report[p+8:p+296];want=bytes.fromhex(c['state'])
  assert got==want,(c['name'],got.hex(),want.hex())
  assert report[p+296:p+384]==b'\xa5'*88,c['name']
 assert report[16:256]==b'\xa5'*240
 assert report[256+384*len(cases):]==b'\xa5'*(len(report)-256-384*len(cases))
 return dict(passed=True,steps=len(cases),interface_states_per_step=2)
