"""Check exact packet bytes, first errors, partial overflow and record guards."""
import struct
def check(report,picture):
 assert len(report)==16384
 expected=bytearray(16384);struct.pack_into('<4q',expected,0,0x56505731,1,148,6)
 n=0
 for width in [2,4]:
  for align in range(4):
   for remain in range(6):
    for state in range(3):
     value=[0x89abcdef,-1,0x100000001][(align+remain)%3]
     packet=(bytes([107])+(value&0xffff).to_bytes(2,"little")+bytes.fromhex("34127856bc9a")) if width==2 else bytes([104])+(value&0xffffffff).to_bytes(4,"little")
     written=min(len(packet),remain) if state==0 else 0
     error=29 if state==1 else 27 if state==2 else 28 if remain<len(packet) else 0
     row=128+n*80;struct.pack_into('<8q',expected,row,width,align,remain,state,0,8+written,error,0)
     expected[row+64:row+80]=packet[:written]+bytes([0xa5])*(16-written)
     n+=1
 for align in range(4):
  row=128+n*80;struct.pack_into('<8q',expected,row,100,align,9,0,0,17,0,0)
  expected[row+64:row+80]=bytes.fromhex('6befcd34127856bc9a')+bytes([0xa5])*7;n+=1
 first_offset=struct.unpack_from('<q',report,11968+8)[0]
 assert 32<=first_offset<=63 and first_offset%8==0
 for i,attrs in enumerate([1,3,31,0,32,1]):
  row=11968+i*640
  actual=struct.unpack_from('<4q',report,row);offset=actual[1]
  assert offset==first_offset+(1 if i==5 else 0),(i,offset)
  ok=i<3
  struct.pack_into('<4q',expected,row,attrs,offset,0 if ok else 27,int(ok))
  buf=bytearray([0xa5]*608)
  if ok:buf[offset:offset+36+attrs*16]=bytes(36+attrs*16)
  if i==0:buf[offset+8:offset+12]=bytes.fromhex("78563412")
  expected[row+32:row+640]=buf
 assert expected==report,'packet/record bytes or guards differ'
 return dict(packet_cases=144,full_clip_alignments=4,record_zero_cases=6,raw_report_bytes=16384,passed=True,scope='Physical CPU packet/record bytes and error guards; no GPU submission')

if __name__=="__main__":
 import argparse,json
 from pathlib import Path
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--report",required=True,type=Path);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes(),None),indent=2))
