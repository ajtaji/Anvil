"""Verify physical DNS reply matching and TTL/cache boundary results."""
import struct


def check(data,cases):
    q=lambda offset:struct.unpack_from('<q',data,offset)[0]
    assert len(data)==16384 and q(0)==0x444e5332 and q(8)==len(cases)
    rows=[]
    for i,c in enumerate(cases):
        p=256+i*64;actual=[q(p+j*8) for j in range(7)]
        expected=[c['rc'],min(c['rc'],0),max(c['rc'],0),c['ip'],c['ttl'],0,0]
        assert actual==expected,(c['name'],actual,expected)
        v6=bytes.fromhex(c['ip6']) if c.get('ip6') else None
        off=8192+i*32
        assert q(off)==(16 if v6 else -200),(c['name'],'v6 result status',q(off))
        assert data[off+8:off+24]==(v6 if v6 else b'\xa5'*16),(c['name'],'v6 bytes/stale write')
        rows.append(dict(case=c['name'],rc=actual[0],ttl=actual[4]))
    for i,expected in enumerate([(0x01020304,0),(0x01020304,0),(0,0),(0x01020304,0),(0x01020304,0)]):
        actual=(q(4096+i*32),q(4104+i*32));assert actual==expected,('cache',i,actual,expected)
    for i,(length,error) in enumerate([(30,0),(30,0),(0,-200),(0,-202),(0,-202),(0,-202),(271,0),(0,-201)]):
        actual=[q(12288+i*32+j*8) for j in range(3)]
        assert actual==[length,error,length],('query',i,actual)
    assert [q(13568+i*8) for i in range(8)]==[0x01020304,16,0,0x01020304,16,0,0,0x01020304]
    for i in range(4):
        assert data[13632+i*16:13648+i*16]==(bytes(range(16,32)) if i in (0,2) else b'\xa5'*16)
    return dict(replies=rows,cache_cases=5,typed_cache_checks=12,query_cases=8)
