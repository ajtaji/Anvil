#!/usr/bin/env python3
"""Check captured target-ownership observations; synthetic self-test is not execution."""
from pathlib import Path
import argparse,json,struct

def records(legacy=False):
    rows=[]
    unchanged=[111,64,32,64,32,256,0,64,32,41,41]
    rebound=[222,96,48,48,96,192,90,96,48,42,42]
    def add(tag,values):
        rows.extend((tag+i,v) for i,v in enumerate(values))
    for kind in range(1,8):
        accepted=legacy and kind in (3,4)
        add(100+kind*20,([0]+rebound+[0,0]) if accepted else ([-21202]+unchanged+[-21202,0]))
    add(260,[0]+rebound+[0,0,1,1001,1002,222,48,96,192])
    add(290,[-20004]+unchanged+[-20004,1])
    for kind in range(1,7):
        accepted=legacy and kind in (2,3,4)
        add(300+kind*20,[23 if accepted else -21202]+unchanged+[99,1 if accepted else 0])
    add(440,[23]+unchanged+[99,1,11,22,3,41])
    assert len(rows)==235
    return rows

def expected_report(chip=2711,legacy=False):
    rows=records(legacy)
    failures=sum(a!=b for a,b in zip(rows,records(False)))
    assert failures==(32 if legacy else 0)
    raw=struct.pack('<8q',0x544F4650,failures,chip,len(rows),failures,2,0,0x50464F54)
    raw+=b''.join(struct.pack('<2q',*row) for row in rows)
    return raw+bytes(4096-len(raw))

def verify(raw,chip=2711,legacy=False):
    wanted=expected_report(chip,legacy)
    if raw!=wanted:
        offsets=[i for i,(a,b) in enumerate(zip(raw,wanted)) if a!=b]
        raise AssertionError('Ownership report mismatch: length='+str(len(raw))+' offsets='+str(offsets[:8]))
    return dict(observations=235,expected_failures=32 if legacy else 0,controlled_providers=True,gpu_execution=False)

def self_test(chip,legacy):
    raw=expected_report(chip,legacy);verify(raw,chip,legacy)
    variants=[]
    for offset in list(range(0,64+235*16,8))+[64+235*16,4095]:
        data=bytearray(raw);data[offset]^=1;variants.append(bytes(data))
    variants += [raw[:-1],raw+b'\0',expected_report(chip,not legacy)]
    for data in variants:
        try:verify(data,chip,legacy)
        except AssertionError:continue
        raise AssertionError('Corrupt or opposite-schema report accepted')
    return dict(synthetic_corruptions_and_opposite_schema_rejected=len(variants),synthetic_only=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path);ap.add_argument('--chip',type=int,default=2711)
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--expect-legacy-guards',action='store_true',help='Check only the planted old-guard negative, never a production pass.')
    a=ap.parse_args()
    if not a.report and not a.self_test:ap.error('Provide --report or --self-test.')
    result={}
    if a.report:result.update(verify(a.report.read_bytes(),a.chip,a.expect_legacy_guards))
    if a.self_test:result.update(self_test(a.chip,a.expect_legacy_guards))
    print(json.dumps(result))
if __name__=='__main__':main()
