"""Independent ordering, multiset and guard checks for cache-range sorting."""
import collections,struct
CASES=[(0,0),(1,0),(2,1),(3,2),(7,3),(31,4),(32,1),(33,2),(128,3),(257,4),(1024,2),(14460,1),(14460,3),(92160,0)]
SIZE=2097152
def pair(i,n,mode):
    if mode==0:a=1+i*32
    elif mode==1:a=1+(n-1-i)*32
    elif mode==2:a=1+((i*73)%n)*32
    elif mode==3:a=1+(i%7)*64
    else:return (100,100+n-i)
    return (a,a+1+i%1024)
def layout():
    at=512
    for n,mode in CASES:
        yield at,n,mode
        at=(at+32+n*16+63)&~63
    assert at<SIZE
def check(report):
    if len(report)!=SIZE:raise ValueError('report length')
    expected=bytearray([0xa5])*SIZE
    struct.pack_into('<QQ',expected,0,0x53525431,len(CASES))
    for at,n,mode in layout():
        guard=(0x12345678,0x12345690) if n<92160 else (0,0)
        struct.pack_into('<4Q',expected,at,n,mode,*guard)
        pairs=list(struct.iter_unpack('<QQ',report[at+32:at+32+n*16]))
        if any(pairs[i-1][0]>pairs[i][0] for i in range(1,n)):raise ValueError(('order',n,mode))
        if collections.Counter(pairs)!=collections.Counter(pair(i,n,mode) for i in range(n)):raise ValueError(('multiset',n,mode))
        expected[at+32:at+32+n*16]=report[at+32:at+32+n*16]
    if report!=expected:raise ValueError('header or guard bytes')
    return dict(cases=len(CASES),intervals=sum(n for n,_ in CASES),exact_guarded_bytes=SIZE,largest_unordered=14460,capacity_ordered=92160)
