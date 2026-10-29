import struct,json

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==16384 and q(0)==0x57434431 and q(8)==len(cases) and q(16)==0
 rows=[]
 for i,name in enumerate(cases):
  p=256+i*4096;row=dict(case=name,rc=q(p),status=q(p+8),mode=q(p+16),decodedBytes=q(p+24),milliseconds=q(p+32),encodedBytes=q(p+40),members=q(p+48),steps=q(p+56));rows.append(row)
  assert row['rc']==1 and row['status']==200 and row['mode']=={'gzip':1,'deflate':2,'identity':0}[name],row
  assert 0<row['decodedBytes']<=2048,row
  body=json.loads(data[p+1024:p+1024+row['decodedBytes']])
  if name=='gzip':assert body['gzipped'] is True,(row,body)
  elif name=='deflate':assert body['deflated'] is True,(row,body)
  else:assert body['url']=='https://httpbingo.org/get',(row,body)
 return rows
