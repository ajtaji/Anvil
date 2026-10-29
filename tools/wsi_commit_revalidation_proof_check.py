#!/usr/bin/env python3
"""Exact captured WSI commit report; old-commit evidence is explicitly negative."""
from pathlib import Path
import argparse,json,struct

def values(missing=False):
    result=[0,0,0]
    for mode in range(7):
        refused=mode in (1,2,4,5)
        wanted=-1000001004 if mode in (1,4) else (-1000000000 if mode in (2,5) else 0)
        accepted=not refused or missing
        count=2 if mode in (4,5) else 1
        result.extend([0]*12)
        result.append(0 if missing else wanted)
        result.extend(3 if accepted and j<count else 2 for j in range(2))
        result.append(1)
        result.append(-20004 if accepted else wanted)
        result.extend([0,2,2]+[0]*8)
    result.extend([0,0])
    assert len(result)==201
    return result

def expected_report(chip=2711,missing=False):
    failures=14 if missing else 0
    raw=struct.pack('<8q',0x57435250,failures,chip,201,failures,1,0,0x50524357)
    raw+=b''.join(struct.pack('<2q',i+1,value) for i,value in enumerate(values(missing)))
    return raw+bytes(4096-len(raw))

def verify(raw,chip=2711,missing=False):
    wanted=expected_report(chip,missing)
    if raw!=wanted:
        first=next((i for i,(a,b) in enumerate(zip(raw,wanted)) if a!=b),None)
        raise AssertionError('WSI commit trace differs: bytes='+str(len(raw))+' first mismatch='+str(first))
    return dict(observations=201,cases=7,expected_failures=14 if missing else 0,
                expected_missing_revalidation=missing,actual_wsi_core=True,gpu_execution=False,scanout_execution=False)

def self_test(chip=2711):
    raw=expected_report(chip);verify(raw,chip);offsets=list(range(0,64+201*16,8))+[64+201*16,4095]
    for offset in offsets:
        bad=bytearray(raw);bad[offset]^=1
        try:verify(bytes(bad),chip)
        except AssertionError:continue
        raise AssertionError('Corrupt WSI commit report accepted')
    for bad in [raw[:-1],raw+b'\0',expected_report(chip,True)]:
        try:verify(bad,chip)
        except AssertionError:continue
        raise AssertionError('Invalid size or old unsafe contract accepted')
    verify(expected_report(chip,True),chip,True)
    differences=sum(a!=b for a,b in zip(values(),values(True)));assert differences==14
    return dict(synthetic_corruptions_rejected=len(offsets)+2,old_commit_rejected=True,
                old_commit_observation_differences=differences,synthetic_only=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path)
    ap.add_argument('--chip',type=int,default=2711);ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--expect-missing-revalidation',action='store_true',help='Accept only the exact unsafe old-commit reproduction, never ordinary success.')
    a=ap.parse_args()
    if not a.report and not a.self_test:ap.error('Provide --report or --self-test.')
    result={}
    if a.report:result.update(verify(a.report.read_bytes(),a.chip,a.expect_missing_revalidation))
    if a.self_test:result.update(self_test(a.chip))
    print(json.dumps(result))
if __name__=='__main__':main()
