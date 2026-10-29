"""Full report oracle for merge refusal and source-preserving ordered batching."""
import struct,hashlib
SIZE=312

def check(b):
 assert len(b)==16384,len(b)
 expected=bytearray([0xa5]*16384)
 struct.pack_into('<4Q',expected,0,0x42415431,SIZE,64,5)
 struct.pack_into('<64Q',expected,256,1,*([0]*63))
 # Runtime snapshot addresses are opaque but must be aligned inside this proof's BSS.
 pointers={k:struct.unpack_from('<Q',b,4096+k*8)[0] for k in (10,27,31)}
 for p in pointers.values():assert 0x1080000<=p<0x1081600 and p%8==0,p
 source=[]
 for i in range(7):
  row=[0]*39
  values={0:1 if i==2 else 0,1:1,2:0x3000000,3:4096,4:32,5:32,6:128,9:2,11:6,12:i*6,16:i*6+5,17:0 if i==4 else 1,18:1,21:32,22:32,25:32,26:32,28:16,37:1,**pointers}
  for k,value in values.items():row[k]=value
  source.append(row)
 raw=b''.join(struct.pack('<39Q',*x) for x in source)
 expected[4096:4096+len(raw)]=raw;expected[8192:8192+len(raw)]=raw
 output=[source[i][:] for i in (0,2,3,4,5)]
 output[0][11]=12;output[0][16]=11;output[4][11]=12;output[4][16]=41
 raw=b''.join(struct.pack('<39Q',*x) for x in output);expected[12288:12288+len(raw)]=raw
 if b!=expected:
  i=next(i for i,(x,y) in enumerate(zip(b,expected)) if x!=y)
  raise AssertionError(f'mismatch at {i:#x}: {b[i]:02x} != {expected[i]:02x}')
 return dict(cases=64,input_draws=7,execution_draws=5,bytes=16384,sha256=hashlib.sha256(b).hexdigest())
