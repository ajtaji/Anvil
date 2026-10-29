#!/usr/bin/env python3
"""Whole-byte public byte-order, standalone DNS and physical counter report."""
from pathlib import Path
import argparse,json,struct
PLAN=json.loads(Path(__file__).with_name('public_byte_order_dns_cases.json').read_text(encoding='utf8'))
def check(raw):
    assert len(raw)==8192
    wanted=bytearray(8192)
    for off,value in [(0,0x4e424331),(8,1),(16,len(PLAN['cases']))]:
        struct.pack_into('<q',wanted,off,value)
    hz,start,end=struct.unpack_from('<3q',raw,64)
    assert hz==54000000 and 0<start<end and end-start<10*hz,'published counter report'
    wanted[64:88]=raw[64:88]
    for i,row in enumerate(PLAN['cases']):struct.pack_into('<2q',wanted,128+i*16,row['expected'],row['expected'])
    wanted[2048:2080]=bytes.fromhex(PLAN['output'])
    assert raw==wanted,'literal DNS/byte-order/guard/unused report mismatch'
    return dict(passed=True,checks=len(PLAN['cases']),bytes=len(raw),counter_hz=hz,counter_elapsed_ticks=end-start,scope=PLAN['scope'])
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(check(a.report.read_bytes()),indent=2))
if __name__=='__main__':main()
