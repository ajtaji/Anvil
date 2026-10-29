"""Check GPU ordered comparison/OR/selection colors, including unordered inputs."""
import struct
from neon_canvas_filter_check import check as filter_check
BITS=[[0, 1065353216, 2147483648, 0], [3212836864, 1065353217, 1065353215, 0], [8388608, 2155872256, 1056964608, 0], [2143363909, 4290847557, 2139169605, 0], [2139095040, 4286578688, 1065353216, 0], [1065353215, 1065353217, 0, 0]]

def check(report,picture):
    assert len(report)==16384
    assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,40)
    assert not any(report[15736:16128]) and not any(report[16176:])
    pixels=struct.unpack_from('<6Q',report,16128)
    rows=[]
    for i,(pixel,bits) in enumerate(zip(pixels,BITS)):
        assert pixel>>24==255,(i,hex(pixel))
        expected=[]
        for j in range(3):
            v=struct.unpack('<f',struct.pack('<I',bits[j]))[0]
            expected.append(128+255*(.25 if v>1 else .125 if v<0 else 0))
        actual=[(pixel>>16)&255,(pixel>>8)&255,pixel&255]
        assert all(abs(a-e)<=1 for a,e in zip(actual,expected)),(i,hex(pixel),actual,expected)
        rows.append(dict(bits=bits,pixel=hex(pixel),expected=expected))
    clean=bytearray(report);clean[15712:]=bytes(16384-15712)
    result=filter_check(clean,picture)
    result.update(boolean_rows=rows,channels=18,ordered_nan_and_signed_zero=True)
    return result
