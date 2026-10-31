"""Check physical output against independent Python integer and packet fixtures."""
import struct

def check(raw,cases):
    assert len(raw)==262144 and struct.unpack_from('<QQ',raw)==(0x51574331,len(cases))
    for index,c in enumerate(cases):
        p=256+index*256;rc,value=struct.unpack_from('<2q',raw,p)
        assert rc==c['rc'],(index,c['name'],rc,c['rc'])
        if 'value' in c:assert value==c['value'],(c['name'],value,c['value'])
        if 'fields' in c:assert list(struct.unpack_from('<14q',raw,p+16))==c['fields'],(c['name'],struct.unpack_from('<14q',raw,p+16),c['fields'])
        expected=bytearray(b'\xa5'*128)
        if 'output' in c:
            output=bytes.fromhex(c['output']);expected[8:8+len(output)]=output
        assert raw[p+128:p+256]==expected,(c['name'],'output/sentinel mismatch')
    return dict(passed=True,cases=len(cases),integer_cases=sum(c['op'] in (0,1) for c in cases),packet_cases=sum(c['op']==2 for c in cases),number_cases=sum(c['op']==3 for c in cases),writer_cases=sum(c['op']==4 for c in cases))
