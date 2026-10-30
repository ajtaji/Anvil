import struct
def check(data,cases):
 assert struct.unpack_from('<q',data)[0]==0x54444941
 expected=[(3,6,2,0,1,1,1,-102),(3,6,2,1,1,1,1,-102),(1,0,0,1,1,0,0,-102),(-104,0,0,1,1,0,0,-102),(3,4,1,1,1,1,1,-102),(-105,0,0,1,1,0,0,-102),(1,0,0,1,1,0,0,-102)]
 rows=[]
 for i in cases:
  row=struct.unpack_from('<8q',data,256+i*64);assert row==expected[i],(i,row,expected[i]);rows.append(row)
 return dict(cases=7,rows=rows,hostnamePreserved=True,cleanup=True)
