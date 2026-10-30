"""Rebuild independent HPACK vectors; requires the test-only hpack==4.2.0 package.

RFC 7541 Appendix C.4 supplies the three literal request examples. Other valid
blocks are encoded/decoded by the independent oracle, not by Anvil. Invalid
cases exercise the specification and Anvil's documented implementation limits.
No oracle implementation is linked into or copied to the target library.
"""
from pathlib import Path
import json,sys,random
import hpack
assert hpack.__version__=='4.2.0','Qualification vectors use hpack 4.2.0 as an independent oracle'
output=Path(__file__).resolve().parent/'hpack_cases.json'

rows=[];decoder=None

def add(blob,reset=False,limit=-1,error=0,list_limit=65536,label=''):
 global decoder
 if reset:decoder=hpack.Decoder(max_header_list_size=list_limit)
 decoder.max_header_list_size=list_limit
 if limit>=0:decoder.max_allowed_table_size=limit
 row=dict(blob=blob.hex(),reset=reset,limit=limit,error=error,list_limit=list_limit,label=label)
 if not error:
  headers=decoder.decode(blob,raw=True);row['fields']=[[bytes(n).hex(),bytes(v).hex(),int(not getattr(f,'indexable',True))] for f in headers for n,v in [f]]
  entries=list(decoder.header_table.dynamic_entries);row['entries']=len(entries);row['size']=sum(len(n)+len(v)+32 for n,v in entries);row['maximum']=decoder.header_table_size
 else:
  try:decoder.decode(blob,raw=True);row['oracle_rejected']=False
  except hpack.HPACKError:row['oracle_rejected']=True
 rows.append(row)
for i,wire in enumerate(['828684418cf1e3c2e5f23a6ba0ab90f4ff','828684be5886a8eb10649cbf','828785bf408825a849e95ba97d7f8925a849e95bb8e8b4bf']):add(bytes.fromhex(wire),reset=i==0,label='RFC C.4 request '+str(i+1))
for huff in [False,True]:
 enc=hpack.Encoder()
 for i in range(5):
  hdr=[(b':status',b'200'),(b'content-type',b'application/json'),(b'x-iteration',str(i).encode()),(b'x-shared',b'repeated header value'),(b'authorization',b'Bearer opaque',True)]
  add(enc.encode(hdr,huffman=huff),reset=i==0,label='response chain '+str(huff)+'/'+str(i))
enc=hpack.Encoder();add(enc.encode([(b'x-all',bytes(range(256)))],huffman=True),reset=True,label='all 256 Huffman symbols');add(enc.encode([(b'x-all',bytes(range(256)))],huffman=True),label='dynamic binary value reference')
add(bytes.fromhex('40017801614001780161bebf'),reset=True,label='duplicate dynamic entries')
add(bytes.fromhex('3f2140017801617e0162be'),reset=True,label='indexed name survives eviction')
enc=hpack.Encoder();add(enc.encode([(b'x-old',b'old')]),reset=True,label='pre oversized entry');add(enc.encode([(b'x-large',b'z'*5000)],huffman=False),label='oversized entry empties table')
enc=hpack.Encoder();add(enc.encode([(b'x',b'a')]),reset=True,label='resize start');enc.header_table_size=0;enc.header_table_size=128;add(enc.encode([(b'x',b'b')]),limit=128,label='minimum and final update');enc.header_table_size=8192;add(enc.encode([(b'x',b'c')]),limit=8192,label='grow table');enc.header_table_size=0;add(enc.encode([(b'x',b'd')]),limit=0,label='table disabled')
enc=hpack.Encoder();add(enc.encode([(b'x',b'e')]),reset=True,label='required minimum seed');decoder.max_allowed_table_size=0
# Simulate shrink then raise before the next block in the physical fixture.
enc.header_table_size=0;enc.header_table_size=4096;add(enc.encode([(b'x',b'f')]),limit=4096,label='minimum survives raised allowance');rows[-1]['shrink_first']=True
for i,wire in enumerate(['80','be','ff808080808000','ffffffff7f','40','400561','400178','0084ffffffff00','00810000','0081ff00','883fe21f','8820','3fe21f']):add(bytes.fromhex(wire),reset=True,error=-3211,label='malformed '+str(i))
add(bytes.fromhex('202020'),reset=True,error=-3211,label='more than two size updates')
add(bytes.fromhex('88'),reset=True,limit=0,error=-3211,label='missing required update')
add(b'',reset=True,limit=0,error=-3211,label='empty block missing update')
add(bytes.fromhex('88'),reset=True,error=-3212,list_limit=32,label='header list limit')
rng=random.Random(1092)
for group in range(3):
 enc=hpack.Encoder()
 for j in range(4):
  hdr=[(b':status',b'200')]+[(('x-random-'+str(k)).encode(),bytes(rng.randrange(32,127) for _ in range(rng.randrange(0,45)))) for k in range(12)]
  add(enc.encode(hdr,huffman=bool(j%2)),reset=j==0,label='random chain '+str(group)+'/'+str(j))
enc=hpack.Encoder();add(enc.encode([(b'x',b'\xff'*8191)],huffman=True),reset=True,label='long Huffman field within workspace')
enc=hpack.Encoder();add(enc.encode([(b'x',b'\xff'*8192)],huffman=True),reset=True,error=-3212,label='Huffman field workspace overflow')
add(bytes.fromhex('3fe17f')+bytes.fromhex('400000')*512,reset=True,limit=16384,label='maximum table with 512 empty entries')
add(bytes.fromhex('3fe13f'),limit=8192,label='single pass evicts 256 oldest entries')
add(bytes.fromhex('7e7fe13e')+b'a'*8160,label='large insertion evicts retained entries')
assert len(rows)*16384<=1048576
output.write_text(json.dumps(dict(oracle='hpack '+hpack.__version__,cases=rows),indent=2)+'\n');print(len(rows),'cases',sum(len(bytes.fromhex(c['blob'])) for c in rows),'encoded bytes')
