import struct
def check(report,cases):
 assert len(report)>=65536 and struct.unpack_from('<2q',report)==(0x57434b31,len(cases))
 for i,c in enumerate(cases):
  p=256+i*1024;n,query,wipe=struct.unpack_from('<3q',report,p);expected=c['expected'].encode()
  assert query==len(expected),(c['name'],'query',query,expected)
  assert wipe==0,(c['name'],'wipe')
  assert list(struct.unpack_from('<'+str(len(c['codes']))+'q',report,p+32))==c['codes'],(c['name'],'store',struct.unpack_from('<'+str(len(c['codes']))+'q',report,p+32))
  if c['cap']<len(expected):
   assert n==-662 and report[p+128:p+896]==b'\xa5'*768,(c['name'],'short output')
  else:
   assert n==len(expected) and report[p+128:p+128+n]==expected,(c['name'],'bytes',n,report[p+128:p+128+max(n,0)])
   assert report[p+128+n]==0xa5,(c['name'],'overrun')
 return dict(cases=len(cases),scope_expiry_order_and_cleanup=True)
