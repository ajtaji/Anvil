"""Validate the existing RSA signature corpus and published X25519 vectors."""
import struct
def check(raw,cases):
 def q(p):return struct.unpack_from('<q',raw,p)[0]
 assert q(0)==0x4b4a4231 and q(8)==len(cases)
 timings=[]
 for i,c in enumerate(cases):
  p=256+i*1024;param=c['param'];kind=param&255
  if c['module']==14:
   assert q(p)==1,(i,'X25519 completion')
   if c.get('cooperative_context'):assert 1<q(p+16)<300,(i,'context scheduling')
   else:assert q(p+16)==300,(i,'ladder steps')
   assert raw[p+128:p+160].hex()==c['expected'],(i,'shared secret')
   assert raw[p+160:p+192]==b'\xa5'*32,(i,'guard')
   assert q(p+40)==1 and q(p+48)==1,(i,'secret wipe/cancel')
  else:
   assert q(p)==((param>>8)&255),(i,'RSA verdict',q(p),param)
   if kind==2 and q(p)==1 and c['expected']:assert raw[p+128:p+160].hex()==c['expected'],(i,'recovered hash')
   if kind==4:assert raw[p+128:p+160]==b'\xa5'*32,(i,'missing key')
  assert q(p+32)==-1,(i,'inactive')
  timings.append(dict(module=c['module'],vector=c['vector'],max_call_us=q(p+8),steps=q(p+16),total_us=q(p+24)))
 return dict(passed=True,cases=len(cases),timings=timings,max_call_us=max(x['max_call_us'] for x in timings))
