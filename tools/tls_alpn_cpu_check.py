"""Check the physical shared ALPN codec fixture, not a complete TLS handshake."""
import struct

def check(raw,cases):
    assert struct.unpack_from('<q',raw)[0]==0x414C5031
    for index,c in enumerate(cases):
        p=256+index*1024
        setrc,hello,eerc,error,early,late,short=struct.unpack_from('<7q',raw,p)
        assert error==c['error'],(c['name'],'error',error,c['error'])
        assert early==-1,(c['name'],'premature protocol exposure')
        if not error:
            expected=bytes.fromhex(c['selected'])
            assert (setrc,eerc,late)==(1,1,len(expected)),(c['name'],setrc,eerc,late)
            assert short==(-1 if expected else 0),(c['name'],'short destination')
            assert raw[p+700:p+700+len(expected)]==expected,c['name']
            assert raw[p+700+len(expected):p+956]==bytes([0xA5])*(256-len(expected)),c['name']
        else:
            assert late==-1,c['name']
            assert raw[p+700:p+956]==bytes([0xA5])*256,c['name']
        if hello>0:
            wire=raw[p+128:p+128+hello]
            assert wire[:3]==b'\x16\x03\x01' and int.from_bytes(wire[3:5],'big')==hello-5,c['name']
            assert wire[5]==1 and int.from_bytes(wire[6:9],'big')==hello-9,c['name']
            q=9+2+32;q+=1+wire[q];q+=2+int.from_bytes(wire[q:q+2],'big');q+=1+wire[q]
            total=int.from_bytes(wire[q:q+2],'big');q+=2;end=q+total;assert end==hello,c['name']
            extensions=[]
            while q<end:
                kind,n=struct.unpack_from('>HH',wire,q);q+=4;assert q+n<=end
                if kind==16:extensions.append(wire[q:q+n])
                q+=n
            offer=bytes.fromhex(c['offer'])
            assert extensions==([len(offer).to_bytes(2,'big')+offer] if offer else []),c['name']
        else:assert raw[p+128:p+640]==bytes([0xA5])*512,(c['name'],'write before capacity/config acceptance')
    return {'alpn_wire_and_refusal_cases':len(cases),'opaque_maximum_name':True,'selection_hidden_before_connected':True,'legacy_offer_unchanged':True,'full_verified_handshake':False}
