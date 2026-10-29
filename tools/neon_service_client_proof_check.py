#!/usr/bin/env python3
"""Independent packet/ledger oracle for the controlled pure service client."""
from pathlib import Path
import struct,json,argparse

def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def check(raw,actual_minor=None):
    assert len(raw)==4096,'report length'
    q=struct.unpack('<512q',raw)
    assert q[:6]==(0x4e534331,1,0,82,48,40),('header/assertions',q[:6])
    assert q[6:19]==(4,7,4,3,2,4,3,4,4,2,3,1,1),('provider call ledger',q[6:19])
    assert q[19:23]==(0,0,0,0),'wrong context or retained ownership at end'
    if actual_minor is not None:
        assert q[24]==actual_minor,('resident ABI',q[24],actual_minor)
    if 0<=q[24]<8:assert q[25]==-21501,'old monitor must refuse before querying the reserved slot'
    else:assert q[25]==999,'new monitor is not queried by this controlled proof'
    assert not any(q[26:32]),'header padding'
    assert q[32:40]==tuple(map(bits,[42,122,196,36,.15,.2,.6,1])),'retained button packet'
    assert q[40:48]==tuple(map(bits,[.25,.5,3.75,4.125,.1,.2,.3,.4])),'direct box packet'
    assert q[48:56]==(0,bits(1.25),bits(2.5),114,bits(1),bits(.5),bits(.25),bits(1)),'text packet'
    assert q[56:66]==(bits(4),bits(5),bits(6),bits(7),16,bits(.1),bits(.2),bits(.3),bits(1),1),'polygon packet'
    assert q[66:70]==(bits(0),bits(0),bits(0),bits(1)),'frame clear packet'
    assert not any(q[70:]),'unused report'
    return dict(passed=True,assertions=82,api_bytes=48,surface_bytes=40,provider_calls=list(q[6:19]),resident_abi_minor=q[24],old_monitor_refusal=q[25],target=q[23],gpu=False,scope='Controlled dispatch, packet values, client ownership/refusals and retained adapter; not a resident Vulkan service or display test')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--actual-minor',type=int);a=ap.parse_args()
    print(json.dumps(check(a.report.read_bytes(),a.actual_minor),indent=2))
if __name__=='__main__':main()
