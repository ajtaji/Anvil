"""Check uploads continue and GOAWAY drains before the single close."""
import struct
from h2_upload_cpu_check import check as upload_check

def check(data,cases):
 result=upload_check(data,cases)
 q=lambda p:struct.unpack_from('<q',data,p)[0]
 for i,c in enumerate(cases):
  p=256+i*120000;wire=data[p+256:p+256+q(p+32)];at=24;goaway=[]
  while at<len(wire):
   n=int.from_bytes(wire[at:at+3],'big')
   if wire[at+3]==7:
    assert wire[at+4:at+9]==bytes(5)
    goaway.append(wire[at+9:at+9+n])
   at+=9+n
  if c['error']:assert goaway==[] and q(p+96)==0
  else:assert goaway==[bytes(8)] and q(p+88)==5 and q(p+96)==1,c['name']
 result['uploads_during_shutdown']=True
 return result
