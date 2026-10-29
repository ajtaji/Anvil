#!/usr/bin/env python3
"""Independent strict oracle for shared lifecycle guard and handoff observations."""
from pathlib import Path
import argparse,struct,json
def expected_records(legacy=False):
 out=[]
 def add(tag,values):out.extend((tag+i,v) for i,v in enumerate(values))
 case=0
 for ready in (0,1):
  for frame in (0,1):
   for flags in range(4):
    allowed=not ready and not frame and not(flags&1)
    add(1000+case*10,[0 if allowed else 16,int(allowed),0]);case+=1
 case=0
 for mode in (0,1):
  for ready in (0,1):
   for frame in (0,1):
    for flags in range(4):
     for active in (0,1):
      allowed=mode==0 and ready==1 and frame==0 and flags==1 and active==1
      add(2000+case*10,[0 if allowed else 16,1 if allowed else mode,int(allowed),0 if allowed else 1]);case+=1
 for which in range(4):add(2700+which*10,[15,1,1]);add(2800+which*10,[15,1,1])
 add(3000,[1,0,1,1,0,1,2,0,1,11,1,0,0,10,6,1,1,0,0,0,2,4,2])
 add(3100,[0,16,7,0])
 if not legacy:add(3090,[1,0,0])
 add(3104,[0,1,0,11,16,0,16,0,16,1,1,0,0,0,0,0,2,2,1,2 if legacy else 3])
 add(3200,[0,16,1,1,0,0,1,8])
 if not legacy:add(3250,[1,16,1,0,2,0,0,0,1,1,0,1,0,0,0,0,1])
 add(3210,[0,16,0,0,1,1,0,7,0,0,0,1])
 add(3230,[0,0,0,0,0,0,1,1,0,1,0,0,0,1])
 if not legacy:
  add(3300,[16,1,0,1,16,16,16,16,1,16,1,1,0,8,0,2,0,0,1,0,0,0])
  add(3340,[16,1,1,0,8,16,0,2,0,0,0])
  add(3360,[0,16,1,1,16,0,16,0,16,1,16,0,0,0,0])
 assert len(out)==(409 if legacy else 477)
 return out
def expected_report(chip=2711,missing_frame_guard=False,legacy=False):
 rows=expected_records(legacy)
 if missing_frame_guard:
  changed={2230:0,2231:1,2232:1,2233:0};assert sum(t in changed for t,v in rows)==4
  rows=[(t,changed.get(t,v)) for t,v in rows]
 failures=4 if missing_frame_guard else 0
 data=struct.pack('<8q',0x4e4c4650,failures,chip,len(rows),failures,1 if legacy else 2,0,0x50464c4e)
 data+=b''.join(struct.pack('<2q',*row) for row in rows)
 return data+bytes(8192-len(data))
def verify(raw,chip=2711,missing_frame_guard=False,legacy=False):
 wanted=expected_report(chip,missing_frame_guard,legacy)
 if raw!=wanted:
  diffs=[i for i,(a,b) in enumerate(zip(raw,wanted)) if a!=b]
  raise AssertionError('Lifecycle report differs; bytes='+str(len(raw))+', first offsets='+str(diffs[:8]))
 return {'observations':409 if legacy else 477,'unprepared_inputs':16,'prepared_inputs':64,'missing_callback_cases':8,'controlled_provider_only':True,'gpu_execution':False,'expected_missing_frame_guard':missing_frame_guard}
def self_test(chip=2711,missing_frame_guard=False,legacy=False):
 raw=expected_report(chip,missing_frame_guard,legacy);verify(raw,chip,missing_frame_guard,legacy)
 count=len(expected_records(legacy));offsets=list(range(0,64+count*16,8))+[64+count*16,8191]
 variants=[]
 for off in offsets:
  data=bytearray(raw);data[off]^=1;variants.append(bytes(data))
 variants += [raw[:-1],raw+b'\0',expected_report(chip,not missing_frame_guard,legacy),expected_report(chip,missing_frame_guard,not legacy)]
 for data in variants:
  try:verify(data,chip,missing_frame_guard,legacy)
  except AssertionError:continue
  raise AssertionError('Corrupted or wrong-schema lifecycle report accepted.')
 return dict(synthetic_corruptions_and_opposite_schemas_rejected=len(variants),synthetic_only=True)

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--report',type=Path);ap.add_argument('--chip',type=int,default=2711)
 ap.add_argument('--self-test',action='store_true')
 ap.add_argument('--expect-missing-frame-guard',action='store_true',help='Require only the deliberate negative with four failed observations.')
 ap.add_argument('--legacy-409',action='store_true',help='Explicit historical version1 schema; never validates the current cleanup policy.')
 a=ap.parse_args()
 if not a.report and not a.self_test:ap.error('Provide --report or --self-test.')
 result={}
 if a.report:result.update(verify(a.report.read_bytes(),a.chip,a.expect_missing_frame_guard,a.legacy_409))
 if a.self_test:result.update(self_test(a.chip,a.expect_missing_frame_guard,a.legacy_409))
 print(json.dumps(result))
if __name__=='__main__':main()
