"""Check physical credential/form output against independent byte fixtures."""
import struct

def check(report,cases):
 assert len(report)>=65536
 assert struct.unpack_from('<2q',report)==(0x57435631,len(cases))
 for i,c in enumerate(cases):
  p=256+i*1024;rc,query,wipe=struct.unpack_from('<3q',report,p)
  assert rc==c['rc'],(i,'result',rc,c)
  assert wipe==0,(i,'wipe',wipe)
  expected=bytes.fromhex(c['expected'])
  if rc>=0:
   assert query==len(expected),(i,'measurement',query)
   assert report[p+32:p+32+len(expected)]==expected,(i,'output')
   assert report[p+32+len(expected)]==0xa5,(i,'overrun')
  else:
   assert report[p+32:p+32+768]==bytes([0xa5])*768,(i,'refusal modified output')
 return dict(cases=len(cases),exact_bytes=True,refusals_preserve_output=True,wipe=True)
