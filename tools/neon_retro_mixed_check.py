"""Check two separately timed CRT draws followed by ordinary image and box draws."""
import struct
from neon_outside_check import expected,POINTS
from neon_canvas_filter_check import check as filter_check

def check(report,picture):
    assert len(report)==16384
    assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,18)
    assert not any(report[15736:16144]) and not any(report[16264:])
    pixels=struct.unpack_from('<15Q',report,16144)
    rows=[]
    for i,pixel in enumerate(pixels[:12]):
        x,y=POINTS[i%6];t=[0,.125][i//6]
        value,outside=expected(x,y,t)
        assert pixel>>24==255,(i,hex(pixel))
        delta=max(abs(((pixel>>shift)&255)-value) for shift in (0,8,16))
        assert (pixel==0xff000000 if outside else delta<=1),(i,hex(pixel),value)
        rows.append(dict(time=t,point=[x,y],pixel=hex(pixel),expected=value))
    assert list(pixels[12:])==[0xff606060,0xffa0a0a0,0xffff0000],pixels[12:]
    clean=bytearray(report);clean[15712:]=bytes(16384-15712)
    result=filter_check(clean,picture)
    result.update(mixed_rows=rows,ordinary_pixels=[hex(v) for v in pixels[12:]])
    return result
