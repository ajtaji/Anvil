"""Independent byte oracle for physical UDP6 stack/dispatcher results."""
import struct
def check(report,cases):
 assert len(report)==131072
 assert struct.unpack_from('<Q',report)[0]==0x55444936
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*2048;expected=bytearray(b'\xa5'*2048)
  struct.pack_into('<11q',expected,0,*c['expected'])
  for key,at in [('wire',128),('addresses',1648),('data',1680)]:
   b=bytes.fromhex(c[key]);expected[at:at+len(b)]=b
  got=report[p:p+2048]
  assert got==expected,(c['name'],list(struct.unpack_from('<11q',got)),c['expected'],next((j for j in range(2048) if got[j]!=expected[j]),None))
 return dict(cases=len(cases),passed=True)
