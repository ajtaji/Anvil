#!/usr/bin/env python3
"""Strict captured report for the actual WSI core/bridge transaction proof."""
from pathlib import Path
import argparse,json,struct

def expected_records():
    rows=[(tag,0) for tag in range(100,108)]+[(108,1),(110,-29999),(111,1)]
    for stage in range(1,5):
        base=200+stage*100
        rows.extend([(base,0),(base+1,0),(base+2,1),(base+3,1)])
        rows.extend([(base+20,1),(base+21,0),(base+22,0)])
        rows.extend([(base+40,-29999),(base+41,1),(base+42,-21202),(base+43,0),(base+44,-21202),(base+45,0)])
        if stage>=2:rows.append((base+4,0))
        if stage>=2:rows.append((base+23,0))
        if stage>=2:rows.extend([(base+46,-21202),(base+47,0)])
        if stage>=3:rows.extend([(base+5,0),(base+6,1),(base+25,0),(base+48,-21202),(base+49,0)])
        if stage==4:rows.extend([(base+7,0),(base+8,3),(base+26,0),(base+50,-21202),(base+51,0),(base+9,1),(base+10,1)])
        rows.extend([(base+11,1 if stage==4 else 0),(base+12,0),(base+13,0),
                     (base+14,-1),(base+15,0),(base+16,0),(base+17,0),(base+18,0)])
        rows.append((base+24,1))
        rows.extend([(base+52,-29999),(base+53,1)])
        if stage>=3:rows.append((base+19,-20002))
    rows.extend((700+i,value) for i,value in enumerate([0,0,0,0,-20004,2,1,1,1,1,7,2]))
    rows.extend([(717,0),(718,-21202),(719,0)])
    rows.extend((712+i,value) for i,value in enumerate([-20004,0,0,0,0]))
    rows.extend((800+i,value) for i,value in enumerate([0,0,0,0,0,1,0,0,4,1,1,3,1,0,0,0]))
    rows.extend((850+i,value) for i,value in enumerate([0,0,1,0,1,0]))
    rows.extend([(858,-21202),(859,0),(856,0),(857,0)])
    rows.extend((900+i,value) for i,value in enumerate([0,0,0,0,-20004,2,0,0,0,-1000000000,0,0,0,0,0]))
    assert len(rows)==199 and len(set(tag for tag,_ in rows))==len(rows)
    return rows

def expected_report(chip=2711):
    rows=expected_records()
    raw=struct.pack('<8q',0x4e575450,0,chip,len(rows),0,2,0,0x5054574e)
    raw+=b''.join(struct.pack('<2q',*row) for row in rows)
    return raw+bytes(4096-len(raw))

def verify(raw,chip=2711):
    expected=expected_report(chip)
    if raw!=expected:
        first=next((i for i,(a,b) in enumerate(zip(raw,expected)) if a!=b),None)
        raise AssertionError('Actual WSI transaction report differs: bytes='+str(len(raw))+' first mismatch='+str(first))
    return dict(observations=len(expected_records()),actual_wsi_core=True,actual_adapter_bridge=True,
                actual_present_record=True,state_backend=True,gpu_execution=False,scanout_execution=False)

def self_test(chip=2711):
    raw=expected_report(chip);verify(raw,chip)
    offsets=list(range(0,64+16*len(expected_records()),8))+[64+16*len(expected_records()),4095]
    for offset in offsets:
        bad=bytearray(raw);bad[offset]^=1
        try:verify(bytes(bad),chip)
        except AssertionError:continue
        raise AssertionError('Damaged WSI observation accepted')
    for bad in [raw[:-1],raw+b'\0']:
        try:verify(bad,chip)
        except AssertionError:continue
        raise AssertionError('Wrong-size WSI report accepted')
    return dict(synthetic_corruptions_rejected=len(offsets)+2,synthetic_only=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path)
    ap.add_argument('--chip',type=int,default=2711);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
    if not a.report and not a.self_test:ap.error('Provide --report or --self-test.')
    result={}
    if a.report:result.update(verify(a.report.read_bytes(),a.chip))
    if a.self_test:result.update(self_test(a.chip))
    print(json.dumps(result))
if __name__=='__main__':main()
