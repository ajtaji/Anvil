"""Verify actual WSS echo, frame boundaries and graceful close."""
import struct

def check(raw,cases):
    assert len(raw)==16384 and struct.unpack_from('<QQ',raw)==(0x57534c31,0)
    rc,state,status,n,frames,elapsed,maxstep,randomused,secure=struct.unpack_from('<9q',raw,16)
    assert (rc,state,status,n,secure)==(2,3,101,15,1),(rc,state,status,n,secure)
    assert raw[256:256+n]==b'Anvil websocket'
    assert frames>=1
    drain_calls,drain_pending,drain_max,service_max=struct.unpack_from('<4q',raw,120)
    assert drain_calls>=1 and drain_pending<drain_calls
    assert struct.unpack_from('<q',raw,88)[0]==2 and raw[1536:1538]==b'\x03\xe8'
    if cases==['secure-resident-echo']:
        assert randomused==16
        assert struct.unpack_from('<2q',raw,96)==(0,1),'resident RNG unavailable'
        return dict(passed=True,frames=frames,elapsed_ms=elapsed,max_step_us=maxstep,resident_rng=True,drain_calls=drain_calls,drain_pending=drain_pending,max_drain_us=drain_max,max_service_us=service_max,nonce_us=struct.unpack_from('<q',raw,112)[0])
    assert randomused>=24
    return dict(passed=True,frames=frames,elapsed_ms=elapsed,max_step_us=maxstep,random_bytes=randomused)
