#!/usr/bin/env python3
"""Host IEEE conversion oracle for selected raw binary32 patterns."""
import argparse,json,struct,math
from pathlib import Path
CASES=[0x00000000,0x80000000,0x00000001,0x80000001,0x007fffff,0x807fffff,0x00800000,0x80800000,0x3f000000,0xbf000000,0x3f7fffff,0xbf7fffff,0x3f800000,0xbf800000,0x3fc00000,0xbfc00000,0x4effffff,0xceffffff,0x4f000000,0xcf000000,0x4f000001,0xcf000001,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc00000,0xffc00000,0x7f800001,0xff800001,0x437f8000,0xc37f8000]
def check(raw,picture=None):
    assert len(raw)==4096
    q=struct.unpack('<512q',raw)
    assert q[:4]==(0x46435031,1,0,67584),('header/comparisons',q[:4])
    assert not any(raw[32:128]),'first failure or header padding'
    for i in range(32):
        bits,got=struct.unpack_from('<qq',raw,128+16*i)
        assert bits==CASES[i],('selected input pattern',i,hex(bits))
        value=struct.unpack('<f',struct.pack('<I',bits))[0]
        expected=0 if math.isnan(value) else max(-2147483647,min(2147483647,value))
        expected=math.trunc(expected)
        assert got==expected,(hex(bits),got,expected)
    assert not any(raw[640:]),'report tail'
    return dict(passed=True,reference_comparisons=67584,independent_host_patterns=32,gpu=False)
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();print(json.dumps(check(a.report.read_bytes()),indent=2))
if __name__=='__main__':main()
