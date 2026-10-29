import json,struct
def check(report,cases):
 assert len(report)>=32768 and struct.unpack_from('<3q',report)==(0x57434b32,1,0)
 rows=[]
 for i,name in enumerate(cases):
  p=256+i*4096;rc,status,ms,n,sent,captured,now=struct.unpack_from('<7q',report,p)
  assert rc==1 and status==200 and 0<n<=3072,(name,rc,status,n)
  assert sent==([0,19,19,0][i]) and captured==([1,0,1,0][i]),(name,sent,captured)
  assert now>1700000000
  body=json.loads(report[p+64:p+64+n])
  if i==1:assert body=={'cookies':{'anvil_session':'ready'}},body
  elif i==3:assert body=={'cookies':{}},body
  rows.append(dict(name=name,status=status,ms=ms,sent_cookie_bytes=sent,captured_fields=captured))
 return dict(cases=rows,session_replay_and_deletion=True,jar_wiped=True)
