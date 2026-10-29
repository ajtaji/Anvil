"""Independent exact request bytes and no-connect refusal oracle."""
import struct
def check(data,cases):
    expected=bytearray([0xA5]*16384)
    struct.pack_into('<QQ',expected,0,0x57525131,len(cases))
    for i,(_,port,host,target) in enumerate(cases):
        at=256+i*1536;expected[at:at+1536]=bytes(1536)
        if port:
            request=(f'GET {target} HTTP/1.1\r\nHost: {host}\r\nAccept-Encoding: identity\r\nUser-Agent: Anvil\r\nAccept: */*\r\nConnection: close\r\n\r\n').encode()
            struct.pack_into('<3Q',expected,at,1,port,len(request));expected[at+32:at+32+len(request)]=request
    assert data==expected,'HTTPS request bytes, connect calls or guards differ'
    return {'cases':len(cases),'exact_request_bytes':True,'network_actions':0}
