"""Check public CRT canvas state refusals together with valid rendering."""
import struct
from neon_canvas_retro_check import check as render_check
EXPECTED=[-21342]*3+[-21202,1,2097152,2097152,0,1234567,-7654321]+[-21341]*3+[-21343]*3+[1234567,-7654321,-21341]+[-21202,-21201]+[-21342]*3

def check(report,picture,trace):
    result=render_check(report,picture)
    assert len(trace)==12288 and struct.unpack_from('<3q',trace)==(0x43524631,len(EXPECTED),0)
    # Only the header and result pairs are owned; padding is not initialized.
    for i,expected in enumerate(EXPECTED):
        assert struct.unpack_from('<2q',trace,64+16*i)==(expected,expected),i
    result.update(contract_checks=len(EXPECTED))
    return result
