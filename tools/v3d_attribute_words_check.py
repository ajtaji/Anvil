import struct
CASES=[[1, 0, 305419896, 16, 2309737967, 1, 1, 0], [4, 3, 4294967295, 2147483648, 4294967295, 15, 0, 0], [31, 30, 1250999896491, -1, 4886718345, 0, 15, 0], [4, 0, 0, 0, 0, 0, 0, 0], [4, -1, 1, 16, 1, 1, 1, 0], [4, 4, 1, 16, 1, 1, 1, 0], [4, 0, 1, 16, 1, 16, 1, 0], [4, 0, 1, 16, 1, 1, -1, 0], [0, 0, 1, 16, 1, 1, 1, 0], [1, 0, 1, 16, 1, 1, 1, 1]]
def expected():
 out=bytearray(b'\xa5'*16384)
 struct.pack_into('<2Q',out,0,0x41545231,len(CASES))
 for i,(attrs,n,addr,stride,maxidx,cs,vs,misalign) in enumerate(CASES):
  base=512+i*1024;began=(1<=attrs<=31 and misalign==0)
  valid=began and 0<=n<attrs and 0<=cs<=15 and 0<=vs<=15
  struct.pack_into('<2Q',out,base,int(began),int(valid))
  if began:out[base+64:base+64+36+attrs*16]=bytes(36+attrs*16)
  if valid:
   off=base+64+36+n*16
   struct.pack_into('<I',out,off,addr&0xffffffff)
   out[off+4:off+8]=bytes((9,cs+16*vs,0,0))
   struct.pack_into('<2I',out,off+8,stride&0xffffffff,maxidx&0xffffffff)
 return bytes(out)
def check(report):
 want=expected()
 if report!=want:
  differences=[i for i,(a,b) in enumerate(zip(report,want)) if a!=b]
  raise ValueError(('record bytes',len(report),len(differences),differences[:16]))
 return dict(cases=len(CASES),exact_bytes=len(want),passed=True)
