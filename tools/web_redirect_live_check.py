import struct,json

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==16384 and q(0)==0x57524433 and q(8)==3 and q(16)==0
 rows=[]
 for i,name in enumerate(cases):
  p=256+i*4096;row=dict(case=name,rc=q(p),status=q(p+8),hops=q(p+16),bodyBytes=q(p+24),milliseconds=q(p+32),target=data[p+512:p+768].split(b'\0')[0].decode(),chain=[[q(p+128+j*24+k*8) for k in range(3)] for j in range(q(p+16)+1)])
  rows.append(row)
  if name=='limit':assert row['rc']==-563 and row['status']==302 and row['hops']==1,row
  else:
   assert row['rc']==1 and row['status']==200 and row['hops']==2 and row['target']=='/get',row
   body=json.loads(data[p+1024:p+1024+row['bodyBytes']]);assert body['url']=='https://httpbingo.org/get',(row,body)
   assert [x[0] for x in row['chain']]==[302,302,200],row
 return rows
