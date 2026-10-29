#!/usr/bin/env python3
"""Strict oracle for captured framebuffer target-preflight observations."""
from pathlib import Path
import argparse,json,struct

def expected_records():
    rows=[]
    def add(tag,values):rows.extend((tag+i,v) for i,v in enumerate(values))
    add(100,[0]*9)
    add(110,[0])
    add(122,[128])
    add(111,[-20002,-20002,-20002,-20003,0])
    add(223,[0,-20001])
    add(116,[-20001,-20001,-20001,-20001,0,0])
    add(130,[-20004])
    add(139,[-20004])
    add(131,[1,-20004,1,-20004,1,-20004,1,0])
    add(140,[-20002,0,1,0])
    add(150,[-20004,0,1,-20004,0,0])
    add(160,[-20004,0,1,-20004,0,0,0])
    add(170,[-20002,0,0,1,0,0,0])
    add(180,[0,0,0,-20004])
    add(187,[-20004])
    add(184,[0,0,0])
    add(200,[0,0,0,0,0,128,-20001,0,-20001,-20003,-20002])
    add(190,[0]*6)
    assert len(rows)==83
    return rows

def expected_report(chip=2711):
    rows=expected_records()
    raw=struct.pack('<8q',0x46425150,0,chip,len(rows),0,2,0,0x50514246)
    raw+=b''.join(struct.pack('<2q',*row) for row in rows)
    return raw+bytes(4096-len(raw))

def verify(raw,chip=2711):
    if raw!=expected_report(chip):raise AssertionError('Framebuffer target report differs from exact object/ownership/generation contract')
    return dict(observations=83,state_backend=True,controlled_retention_injection=True,gpu_execution=False)

def self_test(chip=2711):
    raw=expected_report(chip);verify(raw,chip)
    offsets=list(range(0,64+83*16,8))+[64+83*16,4095]
    for off in offsets:
        data=bytearray(raw);data[off]^=1
        try:verify(bytes(data),chip)
        except AssertionError:continue
        raise AssertionError('Corrupt framebuffer report accepted')
    for data in [raw[:-1],raw+b'\0']:
        try:verify(data,chip)
        except AssertionError:continue
        raise AssertionError('Wrong report length accepted')
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
