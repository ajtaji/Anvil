"""Check read-and-decode equivalence using independently known GGA fix values."""
import struct
SENTENCE=b'$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n'
N=len(SENTENCE)
EXPECTED=[-1,-1,-1,-1,-1,0]
for mode in (0,1):
    EXPECTED += [1,N,N,1,0,N if mode==0 else 1,2,0,1,-1,-1,N,1]
EXPECTED += [0]
FIX=(2,481173000,115166667,545400,-1,-1,-1,8,0,45319000,90,1,10000000,-1,3)
def check(data):
    if len(data)!=2048 or struct.unpack_from('<5Q',data)!=(0x474E5231,len(EXPECTED),0,N,0x454E4421):
        raise ValueError('Incomplete GNSS read report')
    for i,value in enumerate(EXPECTED):
        if struct.unpack_from('<2q',data,64+16*i)!=(value,value):
            raise ValueError(f'GNSS read check {i} differs')
    for offset in (1024,1088):
        if struct.unpack_from('<12iq2i',data,offset)!=FIX:
            raise ValueError('Decoded GGA fix differs from known position/time')
    if any(data[40:64]) or any(data[64+16*len(EXPECTED):1024]) or any(data[1152:]):
        raise ValueError('Unexpected report bytes')
    return dict(checks=len(EXPECTED),sentence_bytes=N,identical_fix_records=True,scope='Real service/framer with chunked provider; no physical receiver or network I/O')
