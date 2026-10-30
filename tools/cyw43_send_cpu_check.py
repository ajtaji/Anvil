"""Physical emitted send policy with independent SDPCM/BDC and mutation checks."""
import struct
def check(raw,cases):
    assert struct.unpack_from('<2q',raw)==(0x54525931,len(cases))
    for i,c in enumerate(cases):
        p=256+i*2048
        actual=list(struct.unpack_from('<6q',raw,p))
        assert actual==c['expected'],(c['name'],actual,c['expected'])
        assert struct.unpack_from('<q',raw,p+48)[0]==actual[2]
        expected=bytearray([165]*1536)
        expected[16:1530]=bytes((j*7+3)&255 for j in range(1514))
        sync,n,seq,credit,after,bus=c['input']
        if actual[1]:
            total=n+16;pad=(total+3)&~3
            struct.pack_into('<HH',expected,0,total,(~total)&65535)
            expected[4:10]=bytes([seq,2,0,12,0,0])
            expected[12:16]=bytes([32,0,0,0]);expected[total:pad]=bytes(pad-total)
        assert raw[p+64:p+64+1536]==expected,c['name']+' changed unexpected TX bytes'
    return dict(passed=True,cases=len(cases),scope='send policy with controlled credit and bus outcomes; no SDIO hardware claim')
