"""Check HTTPS contents and report all observed TLS service/state call costs."""
import struct
from web_content_live_check import check as content_check

def check(report,cases):
 rows=content_check(report,cases)
 for i,row in enumerate(rows):
  p=256+i*4096
  row.update(zip(['start_us','step_max_us','service_max_us','decode_max_us'],struct.unpack_from('<4q',report,p+64)))
  row['phases']=[dict(state=j,service_max_us=struct.unpack_from('<q',report,p+128+j*16)[0],state_query_max_us=struct.unpack_from('<q',report,p+136+j*16)[0]) for j in range(1,6)]
 result=dict(contents_passed=True,rows=rows,max_observed_call_us=max(max(r['start_us'],r['step_max_us'],r['service_max_us'],*(s['state_query_max_us'] for s in r['phases'])) for r in rows))
 if struct.unpack_from('<q',report,24)[0]==0x43414e31:
  result['cancellation']=[]
  for i in range(2):
   h,st,cost,closed,stale=struct.unpack_from('<5q',report,0x3000+i*64)
   assert h>0 and st==2+i and cost>=1500 and closed==0 and stale==-102,(i,h,st,cost,closed,stale)
   result['cancellation'].append(dict(handle=h,state=st,last_call_us=cost,close=closed,stale=stale))
 if struct.unpack_from('<q',report,24)[0]==0x43414e30:
  result['preparation_cancellation']=[]
  for i in range(2):
   h,st,cost,closed,stale,opened=struct.unpack_from('<6q',report,0x3000+i*64)
   assert h>0 and st==i and closed==0 and stale==-102,(i,h,st,cost,closed,stale)
   result['preparation_cancellation'].append(dict(handle=h,state=st,last_call_us=cost,open_us=opened,close=closed,stale=stale))
 if struct.unpack_from('<q',report,32)[0]==0x524f4f54:
  result['root_file_probe']=[]
  for i in range(2):
   opened,cost,size,read,readcost=struct.unpack_from('<5q',report,0x3100+i*64)
   assert opened==1 and size>=4096 and read==4096,(i,opened,size,read)
   result['root_file_probe'].append(dict(open_us=cost,bytes=size,read_us=readcost))
 return result
