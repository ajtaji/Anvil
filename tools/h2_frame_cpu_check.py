"""Check physical HTTP/2 header reports against explicit RFC 9113 cases."""
import struct

def check(report,cases):
 assert len(report)==65536,len(report)
 def q(at):return struct.unpack_from('<q',report,at)[0]
 assert q(0)==0x48324631,'report magic'
 for index,c in enumerate(cases):
  for split in range(10):
   error=c['error']
   expected=[error if error and split==9 else split,error if error else 9-split,error,9,c['length'],c['kind'],c['flags'],c['stream'],error]
   actual=list(struct.unpack_from('<9q',report,256+index*800+split*80))
   assert actual==expected,(index,split,actual,expected)
  at=49152+index*32;err=c['write_error'];assert q(at)==(err or 9),(index,'write return',q(at),err)
  wire=bytearray.fromhex(c['wire']);wire[5]&=127
  if c['kind']<10:wire[4]&=[9,45,0,0,1,8,1,0,0,4][c['kind']]
  expected=bytes([165])*16 if err else bytes(wire)+bytes([165])*7
  assert report[at+8:at+24]==expected,(index,'write bytes/canary',report[at+8:at+24].hex(),expected.hex())
 expected=[-3201,165,24,-3201,-3201,-3201,-3201,165,-3201,165]
 actual=[q(at) for at in range(8,88,8)]
 assert actual==expected,('argument/preface checks',actual,expected)
 assert report[128:160]==b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'+bytes([165])*8,'exact preface and tail guard'
 return dict(cases=len(cases),fragmented_headers=len(cases)*10,preface=True,argument_refusals=True,output_guards=True)
