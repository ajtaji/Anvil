"""Check exact ND validation, checksums, emitted bytes and output guards."""
import struct

def check(raw,cases):
 def q(p):return struct.unpack_from('<q',raw,p)[0]
 assert q(0)==0x49503634 and q(8)==len(cases)
 for i,c in enumerate(cases):
  p=256+i*256
  assert q(p)==c['rc'],(i,c['name'],q(p),c['rc'])
  if c['rc']==0:
   assert q(p+8)==c['kind'] and q(p+16)==c['flags'],(i,'view')
   if 'target' in c:assert raw[p+64:p+80].hex()==c['target'],(i,'target')
   assert q(p+40)==1,(i,'guard')
   if 'built' in c:
    expected=bytes.fromhex(c['built'])
    assert q(p+24)==len(expected) and q(p+32)==-720,(i,'build result',q(p+24))
    assert raw[p+96:p+96+len(expected)]==expected,(i,'emitted packet')
 return dict(passed=True,cases=len(cases))
