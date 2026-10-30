"""Check physical GCM job authentication, output, guards and per-call timing."""
import struct
def check(raw,cases):
 assert struct.unpack_from('<2q',raw)==(0x47434d31,len(cases))
 rows=[]
 for i,c in enumerate(cases):
  rc,result,bad,guard,cost,baseline,busy,wipe=struct.unpack_from('<8q',raw,256+i*64)
  assert (rc,result,bad,guard,busy,wipe)==(1,int(c['mode']!=2),0,1,-2,0),(i,c,rc,result,bad,guard,busy,wipe)
  rows.append(dict(**c,max_call_us=cost,synchronous_us=baseline))
 return dict(passed=True,cases=len(cases),max_call_us=max(x['max_call_us'] for x in rows),rows=rows)
