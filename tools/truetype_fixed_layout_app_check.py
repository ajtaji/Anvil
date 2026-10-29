"""Validate original-layout baseline and independently calculated fixed cells."""
from pathlib import Path
import argparse,json,struct,math
from PIL import Image
PLAN=json.loads(Path(__file__).with_name('truetype_fixed_layout_cases.json').read_text(encoding='utf8'))
Q=lambda b,p:struct.unpack_from('<q',b,p)[0]
def expected_fixed(c,baseline):
 t=bytes.fromhex(c['source'])[:-1].decode('utf8');parts=t.replace('\r\n','\n').replace('\r','\n').split('\n')
 glyphs=[Q(baseline,8192+c['baseline']*768+72+i*8) for i in range(sum(len(p) for p in parts))]
 adv=c['fixed'];maxw=c['width']*65536;out=[];gi=0;line=0;measured=0
 for part in parts:
  chunks=[part[i:i+max(1,maxw//adv)] for i in range(0,len(part),max(1,maxw//adv))] if maxw else [part]
  if not chunks:chunks=['']
  for chunk in chunks:
   width=len(chunk)*adv;offset=0
   if maxw>width:
    if c['alignment']==1:offset=(maxw-width)//2
    elif c['alignment']==2:offset=maxw-width
   for i,ch in enumerate(chunk):out.append((glyphs[gi],offset+i*adv,-line*16*65536,adv));gi+=1
   measured=max(measured,width);line+=1
 return out,line,measured
def check(data,png,baseline=None):
 assert len(data)==65536
 n=Q(data,32);isbase=n==PLAN['baseline_count'];assert n in [PLAN['baseline_count'],len(PLAN['cases'])]
 want=bytearray(65536);struct.pack_into('<5q',want,0,0x54465831,1,0,7,n)
 for i,v in enumerate([0,656568,1,1,1,1,1]):struct.pack_into('<2q',want,256+i*16,v,v)
 if not isbase:
  assert baseline is not None
  baseline=Path(baseline).read_bytes() if isinstance(baseline,(str,Path)) else baseline
  check(baseline,png)
 for i,c in enumerate(PLAN['cases'][:n]):
  p=8192+i*768;arrays=[bytearray(b'\xa5'*144) for j in range(4)]
  if i<PLAN['baseline_count']:
   source=bytes.fromhex(c['source'])[:-1].decode('utf8')
   count=sum(ch not in '\r\n' for ch in source)
   assert Q(data,p)==1 and Q(data,p+8)==0 and Q(data,p+16)==count
   lines=Q(data,p+24);width=Q(data,p+32)
   assert 1<=lines<=16 and 0<=width<=16777216*65536
   for j in range(count):
    vals=[Q(data,p+64+k*144+8+j*8) for k in range(4)]
    assert 0<=vals[0]<65536 and 0<=vals[3]<=512*4*65536
    assert all(abs(x)<=16777216*65536 for x in vals[1:3])
    for k,x in enumerate(vals):struct.pack_into('<q',arrays[k],8+j*8,x)
   struct.pack_into('<5q',want,p,1,0,count,lines,width)
   for k,raw in enumerate(arrays):want[p+64+k*144:p+208+k*144]=raw
   if not isbase:assert data[p:p+768]==baseline[p:p+768],('proportional regression',i)
  elif c.get('refused'):
   error=1 if c['fixed']<0 or c['fixed']>536870912 or c['capacity']<0 else 2
   struct.pack_into('<5q',want,p,0,error,-99,-99,-99)
   for k,raw in enumerate(arrays):want[p+64+k*144:p+208+k*144]=raw
  else:
   rows,lines,width=expected_fixed(c,baseline)
   struct.pack_into('<5q',want,p,1,0,len(rows),lines,width)
   for j,values in enumerate(rows):
    for k,x in enumerate(values):struct.pack_into('<q',arrays[k],8+j*8,x)
   for k,raw in enumerate(arrays):want[p+64+k*144:p+208+k*144]=raw
 if data!=want:
  p=next(i for i,(a,b) in enumerate(zip(data,want)) if a!=b)
  raise AssertionError(('report byte mismatch',p,data[p],want[p]))
 assert Image.open(png).size==(1280,800)
 return dict(passed=True,baseline=isbase,cases=n,setup_assertions=7,unchanged_proportional_cases=16 if not isbase else 0,fixed_cases=48 if not isbase else 0,refused_cases=5 if not isbase else 0)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--png',type=Path,required=True);ap.add_argument('--baseline-report',type=Path);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
 data=a.report.read_bytes();result=check(data,a.png,a.baseline_report)
 if a.self_test:
  assert not result['baseline'];positions=[0,8,16,24,32,65535]
  for i in range(len(PLAN['cases'])):
   positions.extend(8192+i*768+j for j in [0,8,16,24,32,40,64,72,200,208,216,344,352,360,488,496,504,632,767])
  count=0
  for p in positions:
   # Proportional dynamic values are pinned against the separate original run.
   bad=bytearray(data);bad[p]^=1
   try:check(bad,a.png,a.baseline_report)
   except AssertionError:count+=1
   else:raise AssertionError(('accepted mutation',p))
  try:check(data[:-1],a.png,a.baseline_report)
  except AssertionError:count+=1
  else:raise AssertionError('accepted truncation')
  result['rejected_corruptions']=count
 print(json.dumps(result,indent=2))
