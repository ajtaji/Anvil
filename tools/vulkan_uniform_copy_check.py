"""Compare every byte, including uniform padding and refused-write guards."""
import struct,hashlib

def expected():
    b=bytearray([0xa5])*262144
    struct.pack_into('<QQ',b,0,0x554e4931,88)
    source=bytes((i*37+11)&255 for i in range(8192))
    b[0x3c000:0x3e000]=source
    def number(n):return struct.pack('<f',float(n)) if 0<n<16777216 else bytes(4)
    for i in range(32768):b[512+i*4:516+i*4]=number(i*128)
    k=0
    for i in range(24):
        for delta in (-1,0,1):
            at=0x20200+k*4;b[at:at+4]=number((1<<i)+delta);k+=1
    for i,n in enumerate((-1,16777216,16777215)):
        at=0x20320+i*4;b[at:at+4]=number(n)
    for i in range(1,65):
        at=0x21000+(i-1)*1024+64+320
        b[at:at+i*4]=source[6656:6656+i*4]
    for i in range(24):
        base=0x21000+(64+i)*1024
        cs,vs=4+i%7,32-i%7;w,h=1+i*1424,32767-i*1424
        if i==16:w=0
        if i==17:h=32768
        if i==18:cs=3
        if i==19:vs=33
        if i==20:w=-1
        if i==21:h=-1
        if i==22:w,h,cs,vs=32767,1,32,4
        if i==23:w,h=0,0
        valid=1<=w<=32767 and 1<=h<=32767 and 4<=cs<=32 and 4<=vs<=32
        struct.pack_into('<q',b,base,0 if valid or i==23 else -20001)
        if valid:
            for off,src,words in ((640,6144,cs),(768,6400,vs)):
                at=base+64+off;b[at:at+words*4]=source[src:src+words*4]
                b[at+words*4-8:at+words*4]=number(w*128)+number(h*128)
    return bytes(b)

def check(report):
    e=expected()
    if report!=e:
        if len(report)!=len(e):raise ValueError('length')
        bad=[i for i,(a,b) in enumerate(zip(report,e)) if a!=b]
        raise ValueError(('uniform/math/guard mismatch',len(bad),bad[:8]))
    return dict(exact_bytes=len(e),viewport_values=32768,integer_boundaries=75,uniform_cases=88,sha256=hashlib.sha256(e).hexdigest())
