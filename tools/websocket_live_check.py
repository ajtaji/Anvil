"""Verify actual WSS echo, frame boundaries and graceful close."""
import struct

def check(raw,cases):
    assert len(raw)==16384 and struct.unpack_from('<QQ',raw)==(0x57534c31,0)
    rc,state,status,n,frames,elapsed,maxstep,randomused,secure=struct.unpack_from('<9q',raw,16)
    assert (rc,state,status,n,secure)==(2,3,101,15,1),(rc,state,status,n,secure)
    assert raw[256:256+n]==b'Anvil websocket'
    assert frames>=1 and randomused>=24
    return dict(passed=True,frames=frames,elapsed_ms=elapsed,max_step_us=maxstep,random_bytes=randomused)
