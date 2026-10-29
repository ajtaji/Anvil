"""Retained SPIR-V logical dataflow qualification on the physical CPU."""
import struct
EXPECTED=[]
for width in range(1,5):
    EXPECTED += [0,0,1,0,10,1,0,0,16,17,18,19,3,32,
                 10 if width==1 else 14,11 if width==1 else 15,
                 -20001,0,0,-20005]
EXPECTED += [-20005,0,0,-20005,-20001,-20005,-20001,-20005,-20001,-20001,-20005]
def check(report):
    assert len(report)==16384
    assert struct.unpack_from('<3q',report)==(0x42535031,len(EXPECTED),0)
    for i,value in enumerate(EXPECTED):
        assert struct.unpack_from('<2q',report,64+i*16)==(value,value),i
    assert not any(report[24:64]) and not any(report[64+16*len(EXPECTED):])
    return dict(checks=len(EXPECTED),retained_widths=[1,2,3,4],
                independent_storage_after_failed_parse=True,gpu_execution=False)
