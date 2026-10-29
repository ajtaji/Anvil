"""Compare all URL records and guards with the explicit URI case expectations."""
import struct
def check(data,cases):
    expected=bytearray([0xA5]*16384)
    struct.pack_into('<QQ',expected,0,0x55524C31,len(cases))
    for i,c in enumerate(cases):
        at=256+i*448;expected[at:at+448]=bytes(448)
        struct.pack_into('<q',expected,at,c[2])
        if c[2]==0:
            host=c[3].encode();target=c[7].encode()
            struct.pack_into('<5q',expected,at+8,c[4],c[5],c[6],len(host),len(target))
            expected[at+48:at+48+len(host)]=host
            expected[at+304:at+304+len(target)]=target
    if data!=expected:
        difference=next((i for i,(a,b) in enumerate(zip(data,expected)) if a!=b),min(len(data),len(expected)))
        raise AssertionError(f'URL report mismatch at byte {difference}, case {(difference-256)//448}')
    return {'cases':len(cases),'report_bytes':len(data),'exact':True}
