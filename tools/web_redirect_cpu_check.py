import struct

def check(data,cases):
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 assert len(data)==16384 and q(0)==0x57524431 and q(8)==len(cases)
 rows=[]
 for i,c in enumerate(cases):
  p=256+i*256;rc=q(p);host=data[p+32:p+96].split(b'\0')[0].decode();target=data[p+96:p+256].split(b'\0')[0].decode()
  row=dict(rc=rc,host=host,target=target);rows.append(row)
  if c['target'] is None:assert rc<0,(i,c,row)
  else:assert rc==0 and q(p+8)==c['secure'] and q(p+16)==c['port'] and host==c['host'] and target==c['target'],(i,c,row)
 assert data[256+len(cases)*256:]==bytes([0xA5])*(16384-256-len(cases)*256)
 return rows
