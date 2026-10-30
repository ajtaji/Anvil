"""Check negotiation and single-owner HTTP/1 handoff on physical target reports."""
import struct

def check(data,cases):
 def q(at):return struct.unpack_from('<q',data,at)[0]
 assert q(0)==0x48324E47 and q(8)==10 and cases==list(range(10))
 for mode in cases:
  p=256+mode*8192
  assert q(p)==0,(mode,'assertion',q(p))
  assert q(p+16)==1 and q(p+24)==1,(mode,'ownership')
  expected=b'\x02h2\x08http/1.1'
  if mode in (4,5):expected=b'\x02h2'
  if mode==9:expected=b''
  assert q(p+40)==len(expected) and data[p+128:p+128+len(expected)]==expected,(mode,'offer')
  wire=data[p+256:p+256+q(p+32)]
  if mode==0:
   assert wire==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'+bytes.fromhex('00000c040000000000000200000000000600010000'),wire.hex()
  elif mode in (1,2,9):
   assert wire==b'GET /test HTTP/1.1\r\nHost: example.org\r\n\r\n',wire
   assert q(p+48)==200 and q(p+56)==2
   if mode!=9:assert q(p+64)==-550
  else:assert wire==b'',(mode,'unexpected application bytes')
  if mode in (3,4,5):assert q(p+8)==-3252
  if mode==6:assert q(p+8)==-3255,(mode,'timeout result')
  if mode==7:assert q(p+8)==-3256,(mode,'cancellation result')
  if mode==8:assert q(p+8)==-109
  assert q(p+72)==(0 if mode in (6,7,9) else 1)
 return {'cases':10,'ownership':'one open and one close per exchange','automatic_webclient_dispatch':False}
