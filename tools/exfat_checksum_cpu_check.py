"""Independent checksum oracle and physical regression verdict."""
import struct
def check(raw,cases):
    magic,regression,hz,fault=struct.unpack_from('<4q',raw)
    assert magic==0x58464336 and regression==0 and hz>0 and fault==-1,(magic,regression,hz,fault)
    assert struct.unpack_from('<6q',raw,64)==(-1,2,20,10,0,-1),'profile clock/guard accounting failed'
    assert struct.unpack_from('<q',raw,128)[0]==0,'directory cache regression failed'
    assert struct.unpack_from('<2q',raw,136)==(0,4),'boot snapshot validation/read count failed'
    assert struct.unpack_from('<q',raw,152)[0]==0,'mount stage publication/guard regression failed'
    assert struct.unpack_from('<q',raw,160)[0]==0,'mount owner/cancel regression failed'
    rows=[]
    for i,n in enumerate(cases):
        old,new,slow,fast,reads=struct.unpack_from('<5q',raw,256+i*64)
        expected=0
        for j in range(n): expected=(((expected>>1)|((expected&1)<<31))+((j*37+19)&255))&0xffffffff
        assert old==new==expected,(n,old,new,expected)
        assert reads<=(n+4095)//4096+3,(n,reads)
        rows.append(dict(bytes=n,old_us=slow*1000000/hz,new_us=fast*1000000/hz,reads=reads))
    validation=[]
    for i in range(7):
        old,new,slow,fast=struct.unpack_from('<4q',raw,4096+i*64)
        assert old==new==int(i<2),(i,old,new)
        validation.append(dict(case=i,valid=bool(new),old_us=slow*1000000/hz,new_us=fast*1000000/hz))
    assert struct.unpack_from('<2q',raw,4096+32)==(1,255)
    assert struct.unpack_from('<2q',raw,32)==(0,0),'malformed mandatory ASCII mapping accepted'
    return dict(passed=True,regression=regression,read_failure_refused=True,rows=rows,validation=validation)
