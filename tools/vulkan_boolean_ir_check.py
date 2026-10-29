"""Check physical shared-IR validation results; no GPU execution claim."""
import struct
EXPECTED=[]
for lanes in range(1,5):
    EXPECTED += [0,-23205,-23205,-23205,-23205,-23205,-23205,-23205,
                 -23211,-23204,-23210,-23205,0 if lanes==1 else -23205,0,0]
EXPECTED += [-23205]*8

def check(report):
    assert len(report)==16384
    assert struct.unpack_from('<3q',report)==(0x424f4f31,len(EXPECTED),0)
    for i,value in enumerate(EXPECTED):
        assert struct.unpack_from('<2q',report,64+i*16)==(value,value),i
    assert not any(report[24:64]) and not any(report[64+16*len(EXPECTED):])
    return dict(checks=len(EXPECTED),scalar_and_vector_widths=[1,2,3,4],
                selection_version_rule_checked=True,gpu_execution=False)
