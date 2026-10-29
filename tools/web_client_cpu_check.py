import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==16384 and q(0)==0x57455831 and q(8)==8
 rows=[]
 for i in cases:
  p=256+i*256;row=[q(p+j*8) for j in range(9)];rows.append(row)
  rc={2:-552,3:-553,5:-77,6:-524}.get(i,1)
  assert row[0]==rc and row[1]==(2 if rc==1 else -1),(i,row,rc)
  expected=b'abcabc' if i==7 else (b'no!' if i==1 else (b'ab' if i==6 else (b'abc' if i in (0,4) else b'')))
  assert row[3]==len(expected) and data[p+80:p+80+row[3]]==expected,(i,row,expected)
  assert row[2]==(413 if i==1 else (200 if i in (0,4,6,7) else 0)),(i,row)
  assert row[4]==(0 if i in (0,4,7) else 1) and row[8]==1,(i,row)
  assert row[5]==(1 if i in (0,4,7) else 0),(i,row)
  if i==7:assert row[6]==0,(i,row)
 assert data[256+8*256:]==bytes([0xA5])*(16384-256-8*256)
 return rows
