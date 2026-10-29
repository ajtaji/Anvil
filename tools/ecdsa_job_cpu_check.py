"""Validate signature decisions and report cooperative service-call bounds."""
import struct
from ecdsa_cpu_check import check as verdicts

def check(raw,cases):
 result=verdicts(raw,cases)
 rows=[]
 for row in cases:
  index=row[1];maximum,steps=struct.unpack_from('<2q',raw,0x3000+index*16)
  assert maximum>=0 and 0<=steps<1000,(index,maximum,steps)
  if ((row[8]>>8)&255)==1:assert steps>128,(index,'must actually resume')
  rows.append(dict(id=index,max_call_us=maximum,steps=steps))
 result['scheduling']=rows
 result['max_call_us']=max(x['max_call_us'] for x in rows)
 return result
