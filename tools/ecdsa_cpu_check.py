"""Judge every published ECDSA verdict and diagnostic; report positive timings."""
import struct
def check(raw,cases):
 assert struct.unpack_from('<2q',raw)==(0x45434431,len(cases))
 positive=[]
 for row in cases:
  idx=row[1];param=row[8];want={0:0,1:1,2:-1}[(param>>8)&255];err=(param>>16)&255
  got=struct.unpack_from('<4q',raw,256+idx*32)
  assert got[:3]==(idx,want,err),(idx,got,want,err)
  assert got[3]>=0
  if want==1:positive.append({'id':idx,'microseconds':got[3]})
 return {'cases':len(cases),'positive_timings':positive}
