"""Check byte-fragmented and coalesced event-stream results from physical RAM."""
import struct

def check(raw,cases):
    assert struct.unpack_from('<2q',raw)==(0x53534531,len(cases))
    for index,c in enumerate(cases):
        p=256+index*512
        rc,n,off,retry,idlen,eof=struct.unpack_from('<6q',raw,p)
        assert (rc,n,retry,eof)==(c['rc'],len(c['events']),c['retry'],c['rc']),(c['name'],rc,n,retry,eof)
        assert raw[p+448:p+448+idlen].hex()==c['last'],c['name']
        if rc==0:assert off==len(bytes.fromhex(c['wire'])),c['name']
        for i,e in enumerate(c['events']):
            q=p+64+i*192
            dl,el,il=struct.unpack_from('<3q',raw,q)
            assert raw[q+32:q+32+dl].hex()==e['data'],(c['name'],'data')
            assert raw[q+96:q+96+el].hex()==e['event'],(c['name'],'event')
            assert raw[q+128:q+128+il].hex()==e['id'],(c['name'],'id')
    return {'cases':len(cases),'fragmented_and_coalesced':True}
