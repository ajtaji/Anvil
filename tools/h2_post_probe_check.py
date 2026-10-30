"""Validate the actual public HTTP/2 POST echo byte for byte."""
import struct,json,hashlib
def check(data,cases):
 def q(p):return struct.unpack_from('<q',data,p)[0]
 assert q(0)==0x4832504F and q(8)==0,('result',q(8))
 assert q(16)==70000 and q(32)==200 and q(64)==2
 n=q(24);assert 0<n<=131072
 body=json.loads(data[4096:4096+n]);assert body['data']=='a'*70000
 headers={k.lower():v for k,v in body['headers'].items()}
 assert headers['x-anvil-probe']=='shared request' and headers['content-type']=='text/plain'
 assert body['url']==cases[0]
 return dict(url=cases[0],uploaded_bytes=q(16),echoed_body_sha256=hashlib.sha256(body['data'].encode()).hexdigest(),response_bytes=n,max_step_us=q(40),max_service_us=q(48),elapsed_us=q(56),complete_webclient_dispatch=False)
