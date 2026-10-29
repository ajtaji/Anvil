"""Paired renderer oracle plus disjoint portable submission phase clocks."""
import struct
from neon_paired_boxes_check import check as paired_check

def check(report,pixels,**kwargs):
 assert len(report)==16384,'report length'
 clean=bytearray(report);clean[10240:10752]=bytes(512)
 result=paired_check(clean,pixels,**kwargs)
 hz=struct.unpack_from('<Q',report,8208)[0];rows=[]
 for index in range(8):
  ticks=struct.unpack_from('<4Q',report,10240+index*64)
  calls=struct.unpack_from('<4Q',report,10240+index*64+32)
  if index<4:assert ticks==(0,0,0,0) and calls==(0,0,0,0),'native submitted Vulkan work'
  else:
   end=struct.unpack_from('<Q',report,8192+64+index*64+24)[0]
   assert calls==(1,1,1,1),'phase invocation count'
   assert all(0<t<=end for t in ticks),'phase outside End envelope'
   assert sum(ticks)<=end,'disjoint phases exceed End'
   rows.append(dict(frame=index-4,preflight_us=ticks[0]*1e6/hz,retain_us=ticks[1]*1e6/hz,release_us=ticks[2]*1e6/hz,backend_submit_us=ticks[3]*1e6/hz,other_end_us=(end-sum(ticks))*1e6/hz))
 result['portable_submission']=rows
 return result
