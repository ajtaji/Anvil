"""Check real HTTPS through WebClientStartAuto/Step/Next and HTTP/1 fallback."""
import json,struct,hashlib,uuid

def check(data,cases):
 def q(at):return struct.unpack_from('<q',data,at)[0]
 assert q(0)==0x4832414C and q(8)==4
 assert [r['host'] for r in cases]==['www.openbsd.org','www.sqlite.org']
 results=[]
 for index in range(4):
  p=256+index*128;first=4096+index*200000;n=q(p+40)
  assert q(p)==0,(index,'target result',q(p))
  assert q(p+8)==200 and q(p+16)==(2 if index<2 else 1) and q(p+24)==q(p+16),(index,'protocol/status')
  assert q(p+32)==(70000 if index==0 else 0),(index,'upload')
  assert q(p+48)==1 and q(p+56)==(0 if index==0 else 1),(index,'TLS ownership')
  assert 0<n<=196608,(index,'body size')
  body=data[first:first+n]
  if index==0:
   document=json.loads(body)
   assert document['data']=='a'*70000 and document['url']=='https://httpbin.org/post'
   assert document['headers']['X-Anvil-Probe']=='automatic client'
   assert document['headers']['Content-Type']=='text/plain'
   assert q(p+88)==1 and q(p+96)>0
  elif index==1:
   document=json.loads(body);uuid.UUID(document['uuid'])
   assert q(p+88)==3 and q(p+96)==q(256+96),(index,'same connection, new stream')
  else:
   reference=cases[index-2]
   assert n==reference['bytes'] and hashlib.sha256(body).hexdigest()==reference['sha256'],(index,'reference body')
  results.append(dict(index=index,protocol=q(p+16),body_bytes=n,elapsed_us=q(p+64),max_step_us=q(p+72),max_service_us=q(p+80),sent=q(p+104),received=q(p+112)))
 return {'cases':results,'automatic_webclient_dispatch':True,'http2_connection_reused':True}
