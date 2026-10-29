import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==16384 and q(0)==0x57524432 and q(8)==len(cases)
 rows=[]
 for i,c in enumerate(cases):
  p=256+i*1024;rc=q(p);text=data[p+64:p+64+q(p+8)].decode();rows.append(dict(rc=rc,request=text))
  assert rc==c['expected'],(i,c,rows[-1])
  if rc>0:
   method='GET' if rc==1 else c['method'];path='/b/c/d;p?q' if c['cross']==0 else '/next';host='other:8443' if c['cross']==1 else 'a'
   assert text.startswith(f'{method} {path} HTTP/1.1\r\nHost: {host}\r\n'),(i,text)
   for field in ['Authorization:','Cookie:','X-Api-Key:']:assert (field in text)==(c['cross']==0),(i,field,text)
   assert 'Range:' not in text and 'Accept: text/plain\r\n' in text,(i,text)
   assert ('Content-Type:' in text)==(rc==2),(i,text)
   if rc==2 and c['length']==-1:assert 'Transfer-Encoding: chunked\r\n' in text
   if rc==2 and c['length']>0:assert f"Content-Length: {c['length']}\r\n" in text
 assert q(0x3d00)==0 and data[0x3d10:0x3d30].split(b'\0')[0]==b'/b/c/d;p?q'
 return rows
