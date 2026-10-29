#!/usr/bin/env python3
"""Check every byte of the portable input client qualification report."""
from pathlib import Path
import argparse,json,struct
PLAN=json.loads(Path(__file__).with_name('native_input_resident_cases.json').read_text(encoding='utf8'))
def check(data):
    assert len(data)==PLAN['report_bytes'],'report length'
    wanted=bytearray(len(data))
    for off,v in [(0,0x4e495231),(8,1),(16,len(PLAN['cases'])),(24,0)]:struct.pack_into('<q',wanted,off,v)
    for i,row in enumerate(PLAN['cases']):struct.pack_into('<2q',wanted,128+i*16,row['expected'],row['expected'])
    capabilities,width,height,events,context=struct.unpack_from('<5q',data,64)
    assert 1<=capabilities<=7 and 1<=width<=8192 and 1<=height<=8192
    assert 0<=events<=64 and 1<=context<=2147483647
    wanted[64:104]=data[64:104]
    if data!=wanted:
        p=next(i for i,(a,b) in enumerate(zip(data,wanted)) if a!=b)
        idx=(p-128)//16
        name=PLAN['cases'][idx]['expression'] if 0<=idx<len(PLAN['cases']) and p>=128 else 'header/unused'
        raise AssertionError((name,'byte',p,data[p],wanted[p]))
    return dict(passed=True,checks=len(PLAN['cases']),report_bytes=len(data),scope='Resident service; no physical actuation claim')
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
    data=a.report.read_bytes();result=check(data)
    if a.self_test:
        count=0
        positions=[0,8,16,24,127,8191]+[128+i*16+j for i in range(len(PLAN['cases'])) for j in [0,8]]
        for p in positions:
            bad=bytearray(data);bad[p]^=1
            try:check(bad)
            except AssertionError:count+=1
            else:raise AssertionError(('accepted corruption',p))
        try:check(data[:-1])
        except AssertionError:count+=1
        else:raise AssertionError('accepted truncation')
        for offset,value in [(64,0),(64,8),(72,0),(72,8193),(80,0),(80,8193),(88,-1),(88,65),(96,0),(96,2147483648)]:
            bad=bytearray(data);struct.pack_into('<q',bad,offset,value)
            try:check(bad)
            except AssertionError:count+=1
            else:raise AssertionError(('accepted invalid telemetry',offset,value))
        result['rejected_corruptions']=count
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
