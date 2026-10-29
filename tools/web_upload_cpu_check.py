import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==16384 and q(0)==0x57555031 and q(8)==len(cases)
 rows=[]
 for i,c in enumerate(cases):
  p=256+i*768;row=[q(p+j*8) for j in range(4)];rows.append(row)
  error=-541 if c['bad'] or c['method']=='CONNECT' else (-544 if c['length'] in (2,4) else 0)
  if error:
   assert row[0]==error and row[1]==-1,(i,row,error)
  else:
   assert row[0]>=0 and row[1]==2 and row[2]==3,(i,row)
   expected=(c['method']+' /upload?x=1 HTTP/1.1\r\nHost: example.com:8443\r\n'+('Transfer-Encoding: chunked\r\n' if c['length']==-1 else 'Content-Length: 3\r\n')+'Content-Type: text/plain\r\n\r\n').encode()
   expected+=b'3\r\n\x00\xffa\r\n0\r\n\r\n' if c['length']==-1 else b'\x00\xffa'
   assert row[3]==len(expected) and data[p+64:p+64+row[3]]==expected,(i,row,data[p+64:p+64+row[3]],expected)
 assert data[256+len(cases)*768:]==bytes([0xA5])*(16384-256-len(cases)*768)
 return rows
