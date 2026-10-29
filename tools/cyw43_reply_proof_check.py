"""Independent expected reply values, command output and full report guards."""
import struct

def check(report):
    assert len(report)==4096,'length'
    expected=bytearray([0xA5]*4096)
    struct.pack_into('<3Q',expected,0,0x43595231,15,5)
    values=[0,-1,-2147483648,2147483647,0x78563412]+[0]*9+[0xA5A5A5A5A5A5A5A5]
    for i,value in enumerate(values):
        status=[-4,-2147483648,7][i%3]
        struct.pack_into('<3Q',expected,256+i*32,int(i<5),value&((1<<64)-1),status&((1<<64)-1))
    texts=['bcn_timeout = \n',
           'bcn_timeout: the firmware reply does not contain a complete 32-bit value.\n',
           'bcn_timeout: the firmware refused the read (rc , firmware status ).\n',
           'Wi-Fi: the radio is not up, so there is no firmware to ask.\n',
           'wifi iovar <name>   - read one 32-bit firmware variable, e.g. bcn_timeout.\n']
    for i,text in enumerate(texts):
        base=1024+i*512
        words=([1,1,-1,0,11,16,2000] if i==0 else
               [1,0,0,0,11,16,2000] if i==1 else
               [1,2,-123,-4,11,16,2000] if i==2 else [0]*7)
        struct.pack_into('<7Q',expected,base,*(v&((1<<64)-1) for v in words))
        encoded=text.encode()+b'\0';expected[base+64:base+64+len(encoded)]=encoded
    assert report==expected,'reply value, bounded read, command output or guards differ'
    return dict(passed=True,direct_cases=15,command_cases=5,exact_bytes=4096)
