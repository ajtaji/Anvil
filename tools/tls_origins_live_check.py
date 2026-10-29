"""Check independently verified HTTP replies from three hostnames."""
import json,struct

def check(report,cases):
 assert len(report)>=16384
 magic,rc,count,total=struct.unpack_from('<4q',report)
 assert (magic,rc,count)==(0x544d4c31,0,3),(magic,rc,count,total)
 handles=struct.unpack_from('<4q',report,32)
 assert len(set(handles))==4 and min(handles)>0,handles
 rows=[]
 for i,name in enumerate(cases):
  p=256+i*2048;done,status,ms,n=struct.unpack_from('<4q',report,p)
  assert done==1 and status==200,(name,done,status)
  assert 0<=n<=1536
  body=report[p+64:p+64+n]
  if i==1:assert b'Example Domain' in body,(name,body)
  elif i==2:assert b'h=www.cloudflare.com' in body and b'tls=TLSv1.3' in body,(name,body)
  elif i==3:assert body==b'parallel HTTPS reply',body
  rows.append(dict(name=name,handle=handles[i],ms=ms,bytes=n))
 arrivals=[]
 for i in range(3):
  p=0x3000+i*256;n,en,ms,step=struct.unpack_from('<4q',report,p)
  assert 0<n<=192 and en==4 and report[p+224:p+228]==b'ping'
  event=json.loads(report[p+32:p+32+n]);assert event['id']==i,event
  if i<2:assert step==0
  arrivals.append(ms)
 assert min(x['ms'] for x in rows[1:])<rows[0]['ms']
 return dict(connections=rows,event_arrivals_ms=arrivals,total_ms=total)
