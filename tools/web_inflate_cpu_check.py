import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==16384 and q(0)==0x494e4631 and q(8)==len(cases)
 rows=[]
 for i,c in enumerate(cases):
  p=256+i*128;row=[q(p+j*8) for j in range(9)];rows.append(row)
  assert row[0]==(c['error'] or 1) and row[3]==0,(i,c,row)
  assert row[5:]==[165]*4,(i,c,row)
  if not c['error']:assert row[1]==c['wireBytes'] and row[2]==c['outputBytes'],(i,c,row)
 return rows
