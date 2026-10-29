"""Independent host-checksum comparison for the physical checksum report."""
import struct

def check(raw,cases):
 def q(p):return struct.unpack_from('<q',raw,p)[0]
 assert q(0)==0x49503633 and q(8)==len(cases)
 alignments={}
 for i,c in enumerate(cases):
  p=256+i*128
  assert q(p)==c['expected'] and q(p+8)==c['generic'],(i,c['bytes'],q(p),c['expected'])
  assert q(p+16)==1,(i,'guard')
  alignments.setdefault(c['bytes'],set()).add(q(p+24))
 assert all(x=={0,1,2,3} for x in alignments.values())
 return dict(passed=True,cases=len(cases),largest_bytes=max(alignments))
