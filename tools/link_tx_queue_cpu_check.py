"""Independent FIFO model and complete queue-byte oracle for physical results."""
import struct

def check(raw,cases):
 assert struct.unpack_from('<2q',raw)==(0x51554531,len(cases))
 contexts=[None,None]
 for index,(op,which,gen,a,b) in enumerate(cases):
  q=contexts[which]
  valid=q is not None and q['gen']==gen and gen>0
  if op=='init':
   if gen<=0 or (q is not None and gen<=q['gen']):rc=-1
   else:
    rc=len(q['fifo']) if q else 0
    q=dict(gen=gen,head=0,next=1,accepted=0,sent=0,failed=0,error=0,fifo=[],slots=[None]*4)
    contexts[which]=q
  elif op in ('submit','alias'):
   if not valid or op=='alias' or not 1<=a<=1514:rc=-1
   elif len(q['fifo'])==4:rc=0
   else:
    slot=(q['head']+len(q['fifo']))%4
    packet=(q['next'],bytes((i*7+b)&255 for i in range(a)))
    q['slots'][slot]=packet;q['fifo'].append(packet)
    q['next']+=1;q['accepted']+=1;rc=1
  else:
   if not valid or not q['fifo'] or q['fifo'][0][0]!=a or b>1:rc=-1
   elif b==0:rc=0
   else:
    q['slots'][q['head']]=None;q['head']=(q['head']+1)%4;q['fifo'].pop(0)
    if b==1:q['sent']+=1
    else:q['failed']+=1;q['error']=b
    rc=1
  expected=bytearray(6224)
  if q:
   struct.pack_into('<9q',expected,0,0x54585131,q['gen'],q['head'],len(q['fifo']),q['next'],q['accepted'],q['sent'],q['failed'],q['error'])
   for slot,packet in enumerate(q['slots']):
    if packet:
     ticket,data=packet;p=80+slot*1536
     struct.pack_into('<2q',expected,p,len(data),ticket);expected[p+16:p+16+len(data)]=data
  current=q is not None and q['gen']==gen and gen>0
  front=q['fifo'][0] if current and q['fifo'] else None
  metadata=(rc,len(q['fifo']) if current else -1,len(front[1]) if front else 0,front[0] if front else 0)
  p=256+index*6272
  assert struct.unpack_from('<4q',raw,p)==metadata,(index,op,struct.unpack_from('<4q',raw,p),metadata)
  actual=raw[p+32:p+32+6224]
  assert actual==expected,(index,op,'queue bytes',next((i for i,(x,y) in enumerate(zip(actual,expected)) if x!=y),None))
 return dict(passed=True,cases=len(cases),scope='owned FIFO state, exact copied frames, backpressure, stale completions and generation reset; no live driver integration')
