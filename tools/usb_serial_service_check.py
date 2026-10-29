"""Independent returned-report oracle for the USB serial service routing test."""
import struct
EXPECTED=[1,0,0,117,0,0,1,0,-1,-1,0,0,0,0,1,2,116,111,1,1,115200,5,1,
          0x1234,0xabcd,3,2,65,66,99,2,65,-1,-1,-1,-1,-1,-1,0,0,13,-1,65,66,99,9,0]
def check(data):
    if len(data)!=2048:
        raise ValueError('Incomplete serial service report')
    magic,count,failed,end=struct.unpack_from('<4Q',data)
    if (magic,count,failed,end)!=(0x55535331,len(EXPECTED),0,0x454E4421):
        raise ValueError('Serial service did not complete all checks')
    for i,value in enumerate(EXPECTED):
        if struct.unpack_from('<2q',data,64+i*16)!=(value,value):
            raise ValueError(f'Serial service check {i} differs')
    if any(data[32:64]) or any(data[64+16*len(EXPECTED):]):
        raise ValueError('Report padding changed')
    return dict(checks=count,scope='Shared transport and Pi adapter routing with driver doubles; no physical receiver claim')
