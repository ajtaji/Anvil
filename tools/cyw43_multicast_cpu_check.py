"""Independent wire/ownership oracle for CYW43 multicast controls."""
import struct

def check(report,cases):
 assert struct.unpack_from('<Q',report)[0]==0x4D434334
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*512;rc,kind,n,ms=struct.unpack_from('<4q',report,p)
  wire=bytes.fromhex(c['wire'])
  assert [rc,kind,n,ms]==[c['rc'],c['kind'],len(wire),c['ms']],(c['name'],rc,kind,n,ms)
  assert report[p+32:p+224]==wire+bytes(192-len(wire)),c['name']
  assert report[p+224:p+398]==bytes.fromhex(c['output']),c['name']
 return dict(cases=len(cases),passed=True)
