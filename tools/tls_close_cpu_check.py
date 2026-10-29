import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==16384 and q(0)==0x54434C31 and q(8)==8
 rows=[]
 expected=[[-105,-105,-105,-105,1,0,1],[-105,-105,-105,-105,1,0,1],[4,5,3,5,2,2,0],[5,5,0,5,1,1,0],[-105,-105,-105,-105,1,0,1],[-105,-105,-105,-105,1,0,1],[4,-105,-105,-105,2,1,1],[4,-105,-105,-105,1,1,1]]
 for i in cases:
  p=256+i*128;row=[q(p+j*8) for j in range(7)];rows.append(row);assert row==expected[i],(i,row,expected[i])
  if i==2:assert data[p+64:p+67]==b'ABC'
 return rows
