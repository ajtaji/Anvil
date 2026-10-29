#!/usr/bin/env python3
"""Exact order/state oracle. Providers are controlled; no hardware timing claim."""
from pathlib import Path
import argparse,json,struct

def records(old=False):
    # Result,pending,copy-ledger,copies,consumes,matches,main-rebinds,failovers,
    # pending-at-copy,target-at-copy,banner-releases,idle,unsafe,device,releases.
    if not old:
        rows=[
          ([1,0,0,1,1,2,0,0,1,1000,0,0,0,0,0],[13,2,3,2,4]),
          ([0,1,1,1,0,1,0,1,1,1000,0,0,0,0,0],[13,2,3,7]),
          ([0,1,0,0,0,1,0,1,-1,-1,0,0,0,0,0],[13,2,7]),
          ([0,1,0,1,1,2,0,1,1,1000,0,0,0,0,0],[13,2,3,2,4,7]),
          ([0,1,0,0,0,0,0,1,-1,-1,0,0,0,0,0],[13,7]),
          ([1,0,0,1,1,2,1,0,1,2000,0,0,0,0,0],[10,11,12,13,2,5,2,4,9]),
          ([0,1,1,1,0,1,0,0,1,2000,0,0,0,0,0],[10,11,12,13,2,5]),
          ([1,0,0,1,1,2,0,0,1,1000,0,0,0,0,0],[11,12,13,2,6,2,4]),
          ([0,0,0,0,0,0,0,0,-1,-1,0,0,0,0,0],[10,11]),
          ([0,1,0,0,0,0,0,0,-1,-1,0,0,0,0,0],[10,11,12,13]),
          ([0,0,0,1,1,2,1,0,1,2000,0,0,0,0,0],[10,11,12,13,2,5,2,4,9]),
          ([0,1,1,0,0,0,0,0,-1,-1,0,0,1,201,0],[14,15]),
          ([0,1,1,0,0,0,0,0,-1,-1,0,0,1,201,0],[14]),
          ([1,0,0,0,0,0,0,0,-1,-1,1,1,0,0,3],[14,15,16,17,18]),
        ]
    else:
        rows=[
          ([1,0,0,1,1,1,0,0,0,1000,0,0,0,0,0],[13,2,4,3]),
          ([0,0,0,1,1,1,0,1,0,1000,0,0,0,0,0],[13,2,4,3,7]),
          ([0,1,0,0,0,1,0,1,-1,-1,0,0,0,0,0],[13,2,7]),
          ([0,1,0,0,1,1,0,1,-1,-1,0,0,0,0,0],[13,2,4,7]),
          ([0,0,0,0,1,1,0,1,-1,-1,0,0,0,0,0],[13,2,4,7]),
          ([1,0,0,1,1,1,1,0,0,1000,0,0,0,0,0],[10,11,12,13,2,4,9,5]),
          ([0,0,0,1,1,1,1,0,0,1000,0,0,0,0,0],[10,11,12,13,2,4,9,5]),
          ([1,0,0,1,1,1,0,0,0,1000,0,0,0,0,0],[11,12,13,2,4,6]),
          ([0,0,0,0,0,0,1,0,-1,-1,0,0,0,0,0],[10,11,9]),
          ([0,0,0,0,1,1,1,0,-1,-1,0,0,0,0,0],[10,11,12,13,2,4,9]),
          ([0,0,0,0,1,1,1,0,-1,-1,0,0,0,0,0],[10,11,12,13,2,4,9]),
          ([1,0,1,0,0,0,0,0,-1,-1,1,1,0,0,3],[16,17,18]),
          ([1,0,1,0,0,0,0,0,-1,-1,1,1,0,0,3],[16,17,18]),
          ([1,0,1,0,0,0,0,0,-1,-1,1,1,0,0,3],[16,17,18]),
        ]
    assert len(rows)==14 and all(len(fields)==15 and len(events)<=16 for fields,events in rows)
    return [[i+1]+fields+events+[0]*(16-len(events)) for i,(fields,events) in enumerate(rows)]

def expected_report(chip=2711,old=False):
    raw=struct.pack('<8q',0x43504f50,0,chip,14,0,1,0,0x504f5043)
    raw+=b''.join(struct.pack('<32q',*row) for row in records(old))
    return raw+bytes(4096-len(raw))

def verify(raw,chip=2711,old=False):
    expected=expected_report(chip,old)
    if raw!=expected:
        first=next((i for i,(a,b) in enumerate(zip(raw,expected)) if a!=b),None)
        raise AssertionError('Console present order differs: bytes='+str(len(raw))+' first mismatch='+str(first))
    return dict(cases=14,state_and_event_words=448,expected_old_order=old,controlled_providers=True,gpu_execution=False,dma_execution=False)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path);ap.add_argument('--chip',type=int,default=2711)
    ap.add_argument('--expect-old-order',action='store_true');ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
    if not a.report and not a.self_test:ap.error('Provide --report or --self-test.')
    result={}
    if a.report:result.update(verify(a.report.read_bytes(),a.chip,a.expect_old_order))
    if a.self_test:
        raw=expected_report(a.chip);verify(raw,a.chip);offsets=list(range(0,64+448*8,8))+[64+448*8,4095]
        for offset in offsets:
            bad=bytearray(raw);bad[offset]^=1
            try:verify(bytes(bad),a.chip)
            except AssertionError:continue
            raise AssertionError('Corrupt order/state observation accepted')
        for bad in [raw[:-1],raw+b'\0',expected_report(a.chip,True)]:
            try:verify(bad,a.chip)
            except AssertionError:continue
            raise AssertionError('Old order or wrong-size report accepted')
        result.update(synthetic_corruptions_rejected=len(offsets)+2,opposite_order_rejected=True,synthetic_only=True)
    print(json.dumps(result))
if __name__=='__main__':main()
