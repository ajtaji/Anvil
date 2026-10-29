#!/usr/bin/env python3
"""Independent byte-packet and ownership oracle for the pure sprite client."""
import argparse,json,struct
from pathlib import Path

def check(raw):
    assert len(raw)==4096,'report length'
    q=struct.unpack('<512q',raw)
    assert q[:4]==(0x4e535031,1,0,50),('header/assertions',q[:4])
    assert q[4]==19,('provider call count',q[4])
    assert 0x1000000<=q[5]<=0x108ffff,'payload pixel pointer'
    assert not any(raw[48:256]),'header padding'
    def packet(op,data):
        start=256+(op-14)*128
        assert struct.unpack_from('<q',raw,start)[0]==len(data),('packet length',op)
        assert raw[start+8:start+8+len(data)]==data,('packet bytes',op)
        assert not any(raw[start+8+len(data):start+128]),('packet padding',op)
    packet(14,bytes(32))
    packet(15,struct.pack('<6q',3,q[5],16,2,2,1))
    packet(16,struct.pack('<q',701))
    packet(17,struct.pack('<q8fq4fq',701,1.25,2.5,90,2,.25,.5,.75,1,1,3,4,5,6,1))
    packet(18,struct.pack('<3fI',12.5,-3.25,2,0))
    packet(19,struct.pack('<q',701))
    packet(20,struct.pack('<9fIq',7,8,9,10,180,.1,.2,.3,.4,0,1))
    packet(21,b'')
    assert not any(raw[1280:]),'report tail'
    return dict(passed=True,assertions=q[3],provider_calls=q[4],gpu=False,scope='Controlled sprite packets, minor negotiation and retained failure ownership; no native texture/rendering claim')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',required=True,type=Path);a=ap.parse_args()
    print(json.dumps(check(a.report.read_bytes()),indent=2))
if __name__=='__main__':main()
