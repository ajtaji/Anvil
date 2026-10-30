"""Verify physical shared ingress results and independently built wire replies."""
import struct

def check(report,cases):
 assert struct.unpack_from('<Q',report)[0]==0x494E4736
 assert struct.unpack_from('<Q',report,8)[0]==len(cases)
 for i,c in enumerate(cases):
  p=256+i*2048;rc,n,called,proto,nested,replaced=struct.unpack_from('<6q',report,p)
  assert [rc,n,called,proto]==[c['rc'],c['length'],c['called'],c['proto']],(c['name'],rc,n,called,proto)
  if c['wire'] is not None:assert report[p+64:p+64+n]==bytes.fromhex(c['wire']),c['name']
  if c['name'].startswith('IPv4'):
   b=report[p+64:p+64+n];total=int.from_bytes(b[16:18],'big')
   assert b[:14]==bytes.fromhex('0209080706050201020304050800'),c['name']
   assert b[26:34]==bytes([192,0,2,1,192,0,2,2]) and b[34:36]==bytes(2),c['name']
   assert b[38:48]==bytes.fromhex('00010002')+b'legacy',c['name']
   for part in [b[14:34],b[34:14+total]]:
    if len(part)&1:part+=bytes(1)
    summed=sum(struct.unpack('>'+str(len(part)//2)+'H',part))
    while summed>>16:summed=(summed&65535)+(summed>>16)
    assert summed==65535,c['name']
   assert b[14+total:]==bytes(n-14-total),c['name']
  if c['name'].startswith('handler replacement'):assert nested==0 and replaced==-100,(nested,replaced)
  else:assert nested==0 and replaced==0,c['name']
 return dict(cases=len(cases),passed=True)
