"""Verify live TLS protocol negotiation, owned offers and ABI refusals."""
import struct

def check(raw,cases=None):
 header=struct.unpack_from('<5q',raw)
 assert header[0]==0x414C5331 and header[1]>=13 and header[2]==200 and header[3]==3,header
 for i,expected in enumerate([b'h2',b'http/1.1']):
  p=256+i*256;row=struct.unpack_from('<7q',raw,p)
  assert row[0]>0 and row[1:]==(-110,4,-102,len(expected),0,-102),(i,row)
  assert struct.unpack_from('<q',raw,p+56)[0]==0xA5,(i,'short output modified')
  assert raw[p+64:p+64+len(expected)]==expected,(i,raw[p+64:p+80])
  assert raw[p+64+len(expected):p+80]==b'\xa5'*(16-len(expected))
 assert struct.unpack_from('<q',raw,768)[0]>0
 assert struct.unpack_from('<q',raw,784)[0]==4
 assert struct.unpack_from('<2q',raw,800)==(0,0)
 assert struct.unpack_from('<6q',raw,1024)==(-102,)*6
 return dict(live_h2_and_http1_negotiation=True,concurrent_owned_offers=True,legacy_no_offer=True,refusals=6,max_service_us=header[4],http2_request_engine=False)
