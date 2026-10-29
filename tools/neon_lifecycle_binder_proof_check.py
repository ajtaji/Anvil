#!/usr/bin/env python3
"""Strict captured CPU binder report oracle; self-test is synthetic only."""
from pathlib import Path
import argparse,json,struct

def expected_report(chip=2711):
    # Frozen A1 02 03 A4 clear colour, rounded to binary32 by the public API.
    words=[0x42494E44,0,chip,1,0,2,2,1,1,0,0,0,0,
           0x3C008081,0x3C40C0C1,0x3F24A4A5,0x3F21A1A2,0x444E4942]
    raw=struct.pack('<18q',*words)
    return raw+bytes(4096-len(raw))

def verify(raw,chip=2711):
    if raw!=expected_report(chip):raise AssertionError('Binder report differs from exact status/callback/clear/final-owner contract')
    return dict(report_words=18,controlled_provider=True,gpu_execution=False)

def self_test(chip):
    raw=expected_report(chip);verify(raw,chip);offsets=list(range(0,144,8))+[144,4095]
    for off in offsets:
        data=bytearray(raw);data[off]^=1
        try:verify(bytes(data),chip)
        except AssertionError:continue
        raise AssertionError('Accepted corrupted report')
    for data in [raw[:-1],raw+b'\0']:
        try:verify(data,chip)
        except AssertionError:continue
        raise AssertionError('Accepted wrong report length')
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
