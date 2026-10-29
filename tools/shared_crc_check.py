"""Independent zlib oracle for the returning shared-CRC RAM proof."""
import struct,zlib

def check(report):
    if len(report)!=2048: raise ValueError('report length')
    values=struct.unpack('<256Q',report)
    expected=[0]
    for data in (bytes(512),bytes([255])*512,bytes(range(256))*2,bytes((i*73+19)&255 for i in range(512))):
        expected.extend([zlib.crc32(data)]*2)
    expected += [0xCBF43926,zlib.crc32(b'123456789',0x12345678^0xffffffff)^0xffffffff,0x12345678]
    if values[:5]!=(0x43524331,len(expected),0x454E4421,0xA5,0x5A): raise ValueError('header or guards')
    if list(values[8:8+len(expected)])!=expected: raise ValueError('CRC values')
    if any(values[5:8]) or any(values[8+len(expected):]): raise ValueError('reserved bytes')
    return {'checks':len(expected),'passed':True}
