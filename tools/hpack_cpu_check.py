"""Compare physical HPACK output byte-for-byte with independent test vectors."""
import struct

def check(raw,cases):
 assert len(raw)==1048576,len(raw)
 fields=0;worst=0;failures=0
 for index,c in enumerate(cases):
  base=index*16384;row=struct.unpack_from('<15q',raw,base)
  assert row[0]==0 and row[14]==0,(index,c['label'],'init/limit',row)
  assert row[1]==c['error'] and row[2]==c['error'],(index,c['label'],'result',row[:3],c['error'])
  assert row[11:13]==(0xa5a5,0xa5a5),(index,'canary',row[11:13])
  worst=max(worst,row[13])
  if c['error']:failures+=1;continue
  assert row[3:6]==(c['size'],c['maximum'],c['entries']),(index,'table',row[3:6],c)
  assert row[6]==c['size']-28*c['entries'],(index,'storage')
  assert row[7]==len(bytes.fromhex(c['blob'])),(index,'input consumption')
  assert row[9]==len(c['fields']),(index,'field count',row[9],c['fields'])
  at=base+128;actual=[]
  for _ in range(row[9]):
   n,v,sensitive=struct.unpack_from('<3q',raw,at);at+=24
   assert n>=0 and v>=0 and at+n+v<=base+16384
   actual.append([raw[at:at+n].hex(),raw[at+n:at+n+v].hex(),sensitive]);at+=n+v
  assert actual==c['fields'],(index,c['label'],'field bytes',actual,c['fields'])
  assert row[10]==at-base-128
  assert row[8]==sum(len(bytes.fromhex(n))+len(bytes.fromhex(v))+32 for n,v,_ in actual)
  fields+=len(actual)
 return dict(cases=len(cases),fields_exact=fields,malformed_or_limit_refusals=failures,max_field_step_us=worst,huffman_all_octets=True,dynamic_tables=True,output_guards=True)
