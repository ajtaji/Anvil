#!/usr/bin/env python3
"""Strict actual WSI freshness trace; old consumption is explicitly negative."""
from pathlib import Path
import argparse,json,struct

def values(old=False):
    rows=[0,0,0]
    for mode in range(7):
        stale=mode in (1,2,3,4)
        published=1 if old or mode not in (1,2) else 0
        matches=1 if old or not stale else 0
        rows.extend([0]*9+[published,0,matches,matches,4,1,3,published,matches])
        rows.extend([4,1,3,published] if stale and not old else [0,0,0,0])
        rows.extend([1,0]+[0]*7)
    if not old:
        rows.extend([0]*8+[1,1]+[0]*5+[1,4,1,3,1,1]+[0]*3)
        rows.append(-20002)
        for mode in range(3):
            error=0 if mode==0 else (-1000001004 if mode==1 else -1000000000)
            rows.extend([0]*11+[-20004,0,0,0,error,error,3,3,1]+[0]*9)
    rows.extend([0,0]);assert len(rows)==(222 if old else 334)
    return rows

def expected_report(chip=2711,old=False):
    rows=values(old);failures=30 if old else 0
    raw=struct.pack('<8q',0x57504650,failures,chip,len(rows),failures,1,0,0x50465057)
    raw+=b''.join(struct.pack('<2q',i+1,value) for i,value in enumerate(rows))
    return raw+bytes(8192-len(raw))

def verify(raw,chip=2711,old=False):
    expected=expected_report(chip,old)
    if raw!=expected:
        first=next((i for i,(a,b) in enumerate(zip(raw,expected)) if a!=b),None)
        raise AssertionError('WSI freshness trace differs: bytes='+str(len(raw))+' first mismatch='+str(first))
    return dict(observations=len(values(old)),expected_failures=30 if old else 0,
                expected_stale_consumption=old,includes_new_query_cases=not old,
                actual_wsi_core=True,actual_bridge=True,actual_record=True,gpu_execution=False,scanout_execution=False)

def self_test(chip=2711):
    raw=expected_report(chip);verify(raw,chip);offsets=list(range(0,64+334*16,8))+[64+334*16,8191]
    for offset in offsets:
        bad=bytearray(raw);bad[offset]^=1
        try:verify(bytes(bad),chip)
        except AssertionError:continue
        raise AssertionError('Damaged freshness observation accepted')
    for bad in [raw[:-1],raw+b'\0',expected_report(chip,True)]:
        try:verify(bad,chip)
        except AssertionError:continue
        raise AssertionError('Old consumption or wrong size accepted')
    verify(expected_report(chip,True),chip,True)
    differences=sum(a!=b for a,b in zip(values()[:220],values(True)[:220]));assert differences==30
    return dict(synthetic_corruptions_rejected=len(offsets)+2,old_capture_contract_rejected=True,
                common_case_differences=differences,synthetic_only=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path)
    ap.add_argument('--chip',type=int,default=2711);ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--expect-stale-consumption',action='store_true',help='Only the exact old unsafe consumption trace; never ordinary success.')
    a=ap.parse_args()
    if not a.report and not a.self_test:ap.error('Provide --report or --self-test.')
    result={}
    if a.report:result.update(verify(a.report.read_bytes(),a.chip,a.expect_stale_consumption))
    if a.self_test:result.update(self_test(a.chip))
    print(json.dumps(result))
if __name__=='__main__':main()
