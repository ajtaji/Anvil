"""Validate server-echoed full-record application bytes from physical TLS."""
import json,struct
def check(raw,cases=None):
    magic,rc,status,sent,n,step,service,ms=struct.unpack_from('<8q',raw)
    assert (magic,rc,status,sent)==(0x54534E31,1,200,32768),(magic,rc,status,sent)
    assert 0<n<=60000,n
    reply=json.loads(raw[256:256+n])
    expected=''.join(chr(65+i%26) for i in range(32768))
    assert reply['data']==expected,'server received different application bytes'
    return dict(passed=True,body_bytes=sent,echo_bytes=n,max_step_us=step,max_service_us=service,elapsed_ms=ms)
