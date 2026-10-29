"""Check the original curved-screen opaque border against GPU readback."""
import math
import struct
from neon_canvas_filter_check import check as filter_check

POINTS=[(0,0),(255,0),(0,255),(255,255),(127,127),(10,127)]

def expected(x,y,t):
    u=2*(x+.5)/256-1
    v=2*(y+.5)/256-1
    k=.015*(u*u+v*v)
    u=(u+u*k)*.5+.5
    v=(v+v*k)*.5+.5
    outside=u<0 or u>1 or v<0 or v>1
    if outside:
        return 0.,True
    column=max(0,min(63,math.floor(64*u)))
    value=(160 if column%2 else 96)-255*.04*math.sin(v*800-t*10)
    blend=max(0,min(1,(math.hypot(u-.5,v-.5)-.3)/.5))
    return value*(1-blend*blend*(3-2*blend)),False

def inspect(report,picture):
    assert len(report)==16384
    assert struct.unpack_from('<3q',report,15712)==(0x4e435531,0,25)
    for i in range(25):
        assert struct.unpack_from('<2q',report,15744+i*16)==(0,0),i
    pixels=struct.unpack_from('<18Q',report,16144)
    errors=[]
    rows=[]
    for i,pixel in enumerate(pixels):
        t=[0,.125,12.5][i//6]
        x,y=POINTS[i%6]
        value,outside=expected(x,y,t)
        assert pixel>>24==255,(i,hex(pixel))
        delta=max(abs(((pixel>>shift)&255)-value) for shift in (0,8,16))
        good=pixel==0xff000000 if outside else delta<=1
        rows.append(dict(point=[x,y],time=t,pixel=hex(pixel),expected=value,outside=outside,passed=good))
        if not good:errors.append(i)
    assert not any(report[15736:15744]) and not any(report[16288:])
    clean=bytearray(report)
    clean[15712:]=bytes(16384-15712)
    result=filter_check(clean,picture)
    result.update(outside_rows=rows,failed_samples=errors)
    return result

def check(report,picture):
    result=inspect(report,picture)
    assert not result['failed_samples'],result['outside_rows']
    return result
