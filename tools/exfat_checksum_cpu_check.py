"""Independent checksum oracle and physical regression verdict."""
import struct
def check(raw,cases):
    magic,regression,hz,fault=struct.unpack_from('<4q',raw)
    assert magic==0x58464331 and regression==0 and hz>0 and fault==-1,(magic,regression,hz,fault)
    rows=[]
    for i,n in enumerate(cases):
        old,new,slow,fast,reads=struct.unpack_from('<5q',raw,256+i*64)
        expected=0
        for j in range(n): expected=(((expected>>1)|((expected&1)<<31))+((j*37+19)&255))&0xffffffff
        assert old==new==expected,(n,old,new,expected)
        assert reads<=n//512+3,(n,reads)
        rows.append(dict(bytes=n,old_us=slow*1000000/hz,new_us=fast*1000000/hz,reads=reads))
    validation=[]
    for i in range(7):
        old,new,slow,fast=struct.unpack_from('<4q',raw,4096+i*64)
        assert old==new==int(i<2),(i,old,new)
        validation.append(dict(case=i,valid=bool(new),old_us=slow*1000000/hz,new_us=fast*1000000/hz))
    assert struct.unpack_from('<2q',raw,4096+32)==(1,255)
    assert struct.unpack_from('<2q',raw,32)==(0,0),'malformed mandatory ASCII mapping accepted'
    return dict(passed=True,regression=regression,read_failure_refused=True,rows=rows,validation=validation)
