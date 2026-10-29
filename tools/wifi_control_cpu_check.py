"""Independent full-report oracle for physical Wi-Fi control dispatch."""
import struct

def check(data):
    rows=[[-30001,0,0,0,0,0]]
    rows += [[0,1,1,1,0,1],[0,1,1,2,0,1],[0,1,2,1,1,1],[0,1,2,2,2,1],
             [0,1,3,0,0,1],[0,1,4,1,0,1],[0,1,4,600,1,1],
             [-77,1,5,0,0,1],[-77,1,5,1,0,1]]
    rows += [[-30002,0,0,0,0,1] for _ in range(12)]
    rows += [[-30001,0,0,0,0,0]]
    expected=bytearray([0xA5]*16384)
    struct.pack_into('<QQ',expected,0,0x57464331,len(rows))
    for i,row in enumerate(rows):struct.pack_into('<6q',expected,256+i*48,*row)
    assert data==expected,'control dispatch report differs from independent expected bytes'
    return {'cases':len(rows),'bytes':len(data),'radio_actions':0}
