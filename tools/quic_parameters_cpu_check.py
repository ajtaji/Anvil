"""Independent physical report check: records, refusals, guards and ID binding."""
import struct
def check(raw,cases):
 assert len(raw)==262144 and struct.unpack_from('<QQ',raw)==(0x51545031,len(cases))
 maximum=0
 for i,c in enumerate(cases):
  p=256+i*2304;r=struct.unpack_from('<10q',raw,p)
  assert r[0]==c['rc'],(c['name'],r)
  assert r[1]==(-3389 if c['rc']==-3381 else c['rc']),(c['name'],'terminal result',r)
  assert r[5:8]==(0,0,0),(c['name'],'guard/input/visibility',r)
  assert r[8]==(c['ids_rc'] if c['rc']==1 else -3389),(c['name'],'connection ID binding',r)
  if c['rc']==1:
   assert r[2]==len(c['entries']) and r[3]==len(bytes.fromhex(c['wire'])),(c['name'],'count/cursor',r)
   for j,e in enumerate(c['entries']):assert struct.unpack_from('<4q',raw,p+256+j*32)==tuple(e),(c['name'],j,e)
  assert raw[p+256+r[2]*32:p+2304]==b'\xa5'*(2048-r[2]*32),(c['name'],'partial entry write')
  maximum=max(maximum,r[9])
 return dict(passed=True,cases=len(cases),max_step_us=maximum)
