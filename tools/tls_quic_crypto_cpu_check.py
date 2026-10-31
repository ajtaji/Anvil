"""Check real TLS message boundaries and Finished against independent crypto."""
import struct
def check(raw,cases):
 assert len(raw)==65536 and struct.unpack_from('<QQ',raw)==(0x51544331,len(cases))
 for i,c in enumerate(cases):
  p=256+i*2048;err,state,pos,largest,n,tickets,buffered=struct.unpack_from('<7q',raw,p)
  assert (err,state)==(c['error'],c['state']),(c['name'],err,state,pos,n)
  assert largest<=256,(c['name'],'unbounded input')
  if 'consumed' in c:assert pos==c['consumed'],(c['name'],'consumed',pos)
  if c['mode']==5:assert tickets==1 and largest==256 and buffered==0
  if 'output' in c:
   expected=bytes.fromhex(c['output']);assert n==len(expected),(c['name'],'length',n)
   assert raw[p+128:p+128+n]==expected,(c['name'],'Finished output')
   assert raw[p+128+n:p+256]==b'\xa5'*(128-n),(c['name'],'output guard')
  if 'secrets' in c:assert raw[p+256:p+320]==bytes.fromhex(c['secrets']),(c['name'],'application secret')
 return dict(passed=True,cases=len(cases),real_x25519_hkdf_finished=True,full_certificate_handshake=False)
