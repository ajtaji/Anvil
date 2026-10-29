"""Independent six-vertex byte oracle for rotated, packed quad construction."""
import struct,hashlib
RECTS=[(1,2,9,12),(-100,50,150,-20),(0,0,0,0),(-100000,90000,130000,-40000),(63,31,64,32)]
UVS=[(0,0,0x3f800000,0x3f800000),(0xffffffff,0x80000000,0x7fc01234,0x12345678),(1,2,3,4),(0xdeadbeef,0x87654321,0xfedcba98,0x01234567),(0x3e800000,0x3f000000,0x3f400000,0x3f800000)]
CASES=[(rot,align,j) for rot in (0,90,180,270) for align in (0,4) for j in range(len(RECTS))]
def expected():
    b=bytearray([0xa5])*32768
    struct.pack_into('<QQ',b,0,0x51554131,len(CASES))
    for i,(rot,align,j) in enumerate(CASES):
        x0,y0,x1,y1=RECTS[j];u0,v0,u1,v1=UVS[j]
        corners=[(x0,y0,u0,v0),(x0,y1,u0,v1),(x1,y1,u1,v1),(x0,y0,u0,v0),(x1,y1,u1,v1),(x1,y0,u1,v0)]
        w,h=(32,64) if rot in (90,270) else (64,32)
        for k,(x,y,u,v) in enumerate(corners):
            if rot==90:tx,ty=32-y,x
            elif rot==180:tx,ty=64-x,32-y
            elif rot==270:tx,ty=y,64-x
            else:tx,ty=x,y
            at=512+i*512+64+align+3*24+k*24
            # Power-of-two dimensions make these ratios exact before binary32 rounding.
            struct.pack_into('<ffIIII',b,at,(2*tx-w)/w,(2*ty-h)/h,u,v,0x3f800000,0x3f800000)
    return bytes(b)
def check(report):
    e=expected()
    if report!=e:
        if len(report)!=len(e):raise ValueError('length')
        bad=[i for i,(x,y) in enumerate(zip(report,e)) if x!=y]
        raise ValueError(('quad bytes or guards',len(bad),bad[:8]))
    return dict(cases=len(CASES),vertices=len(CASES)*6,exact_bytes=len(e),sha256=hashlib.sha256(e).hexdigest())
