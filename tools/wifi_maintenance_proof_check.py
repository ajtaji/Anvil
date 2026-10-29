"""Independent full-report oracle; no network or emulation."""
import struct

def check(report):
    assert len(report)==4096,'report length'
    expected=bytearray([0xA5]*4096)
    values=(0x574D3136,0,0,12,1,1,1,0,1,1,1,1,122,0,0,0)
    struct.pack_into('<16Q',expected,0,*values)
    assert report==expected,'maintenance routing, payload result or report guard differs'
    return dict(passed=True,words=len(values),exact_bytes=len(expected),payload_result=0,
                scope='Physical CPU, real service and adapter with radio doubles; payload engine regression; no radio disruption or GPU claim')
