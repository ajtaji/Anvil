"""Verify real TLS ALPN fallback, HTTP/1 body bytes and single-owner transfer."""
import struct,hashlib

def check(data,cases):
 def q(at):return struct.unpack_from('<q',data,at)[0]
 assert q(0)==0x48324642 and q(8)==2 and len(cases)==2
 results=[]
 for index,row in enumerate(cases):
  p=256+index*128
  assert q(p)==0,(row['host'],'target result',q(p))
  assert q(p+8)==row['status'],(row['host'],'HTTP status',q(p+8))
  assert q(p+16)==(8 if row['alpn']=='http/1.1' else 0),(row['host'],'ALPN length')
  assert q(p+24)==row['bytes'],(row['host'],'body bytes',q(p+24))
  assert q(p+32)==1 and q(p+40)==1,(row['host'],'open/close ownership')
  first=4096+index*200000;digest=hashlib.sha256(data[first:first+q(p+24)]).hexdigest()
  assert digest==row['sha256'],(row['host'],'body digest',digest)
  results.append(dict(host=row['host'],status=q(p+8),body_bytes=q(p+24),sha256=digest,elapsed_us=q(p+48),max_step_us=q(p+56),max_service_us=q(p+64)))
 return {'cases':results,'automatic_webclient_dispatch':False}
