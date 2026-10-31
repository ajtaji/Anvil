"""Compare physical QUIC packets/keys with independent RFC and AEAD expectations."""
import struct

def check(raw,cases):
 assert len(raw)==262144 and struct.unpack_from('<QQ',raw)==(0x51434331,len(cases))
 keymax=beginmax=stepmax=0
 for index,c in enumerate(cases):
  p=256+index*4096;r=struct.unpack_from('<16q',raw,p)
  assert r[0]==c['rc'],(index,c['name'],r)
  assert r[8]==r[9]==r[12]==r[13]==0,(c['name'],'early write/guard/owner',r)
  if c['mode'] not in (2,3):assert r[15]==r[0],(c['name'],'terminal result')
  if c['mode']==1:assert r[10]==r[11]==-3342,(c['name'],'owner not protected')
  if c['mode']==2:assert r[11]==1,(c['name'],'foreign owner cancelled')
  assert struct.unpack_from('<3q',raw,p+224)==(0,0,0),(c['name'],'secret retained or TLS record interleave failed')
  actual=raw[p+256:p+256+len(bytes.fromhex(c['input']))]
  if c['output'] is not None:assert actual==bytes.fromhex(c['output']),(c['name'],'packet mismatch',actual[:32].hex())
  expected=bytearray(88)
  if c['mode']!=3:
   secret,key,iv,hp=map(bytes.fromhex,c['keys'])
   if c['wrong_key']:key=bytes([key[0]^1])+key[1:]
   expected[:32]=secret;expected[32:48]=key;expected[48:60]=iv;expected[64:80]=hp;struct.pack_into('<q',expected,80,1)
  assert raw[p+128:p+216]==expected,(c['name'],'key derivation mismatch')
  if r[0]==1:
   assert r[14]>r[7],(c['name'],'missing cipher invalidation')
   assert r[1]==c['number'] and r[2]==len(bytes.fromhex(c['header'])) and r[3]==len(bytes.fromhex(c['plain'])),(c['name'],'metadata',r)
  keymax=max(keymax,r[4]);beginmax=max(beginmax,r[5]);stepmax=max(stepmax,r[6])
 return dict(passed=True,cases=len(cases),key_step_max_us=keymax,begin_max_us=beginmax,packet_step_max_us=stepmax)
