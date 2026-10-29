"""Check explicit unsupported lifecycle behavior; no graphics device is started."""
import struct
def check(report,picture=None):
    assert len(report)==16384
    expected=bytearray(16384)
    struct.pack_into('<3q',expected,0,0x4e4c4131,0,12)
    for i,value in enumerate([0,0,16,0,16,10,0,0,0,16,0,0]):
        struct.pack_into('<2q',expected,256+i*16,value,value)
    assert report==expected
    return dict(passed=True,checks=12,native_ownership=False,native_rendering=False,scope='Physical CPU execution of shared absent-lifecycle refusal; no GPU support claimed')
