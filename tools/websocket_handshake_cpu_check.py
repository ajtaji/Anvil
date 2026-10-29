"""Check handshake fixtures and independently computed SHA1/Base64 values."""
import struct,hashlib,base64

def check(raw,cases):
    assert len(raw)==16384 and struct.unpack_from('<QQ',raw)==(0x57534831,len(cases))
    rc,n=struct.unpack_from('<qq',raw,16);assert rc==0,rc
    request=raw[0x3000:0x3000+n]
    key=base64.b64encode(b'the sample nonce')
    accept=base64.b64encode(hashlib.sha1(key+b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
    assert raw[0x3400:0x3418]==key
    assert raw[0x3420:0x343c]==accept
    assert raw[0x3440:0x3454]==hashlib.sha1(b'prefixsuffix').digest()
    assert request==b'GET /chat HTTP/1.1\r\nHost: example.com\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: '+key+b'\r\n\r\n',request
    for i,c in enumerate(cases):
        rc,used,status=struct.unpack_from('<3q',raw,256+i*64)
        assert rc==c['rc'],(c['name'],rc,c['rc'])
        assert used==c['consumed'],(c['name'],'overread',used,c['consumed'])
    return dict(passed=True,cases=len(cases))
