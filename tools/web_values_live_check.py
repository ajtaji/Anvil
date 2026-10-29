"""Validate real HTTPS authentication and form response bodies."""
import json,struct

def check(report,cases):
 assert len(report)>=32768
 assert struct.unpack_from('<2q',report)==(0x57435632,1)
 rows=[]
 for i,name in enumerate(cases):
  p=256+i*4096;rc,status,elapsed,n,sent,total=struct.unpack_from('<6q',report,p)
  assert rc==1 and status==(401 if i==1 else 200),(name,rc,status)
  assert 0<n<=3072 and 0<elapsed<20000,(name,n,elapsed)
  obj=json.loads(report[p+64:p+64+n])
  if i<2:assert obj['authorized']==(i==0),(name,obj)
  elif i==2:assert obj['authenticated'] is True and obj['token']=='synthetic-test-token',obj
  else:
   assert obj['form']=={'road':['Taylor St + 5th & Main']},obj
   assert sent==total and total>21,(sent,total)
  rows.append(dict(name=name,status=status,ms=elapsed,body_bytes=n))
 return dict(cases=rows,exact_form=True,wrong_password_refused=True)
