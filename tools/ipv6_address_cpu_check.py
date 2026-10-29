"""Check physical IPv6 address results against Python ipaddress fixtures."""
import struct

def check(raw,cases):
 def q(p):return struct.unpack_from('<q',raw,p)[0]
 assert q(0)==0x49503631 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*256
  assert q(p+32)==1,(i,c['text'],'guard')
  if c['valid']:
   assert q(p)==0,(i,c['text'],'parse',q(p))
   assert raw[p+64:p+80].hex()==c['address'],(i,'bytes')
   assert q(p+8)==q(p+16)==len(c['formatted']),(i,'length')
   assert raw[p+96:p+96+q(p+8)+1]==c['formatted'].encode()+b'\0',(i,'format')
   assert q(p+24)==-2 and q(p+40)==133,(i,'capacity/prefix')
  else:assert q(p)==-1,(i,c['text'],'refusal')
 return dict(passed=True,cases=len(cases),valid=sum(c['valid'] for c in cases))
