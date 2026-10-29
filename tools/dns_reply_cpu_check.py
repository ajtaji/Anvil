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
        rows.append(dict(case=c['name'],rc=actual[0],ttl=actual[4]))
    for i,expected in enumerate([(0x01020304,0),(0x01020304,0),(0,0),(0x01020304,0),(0x01020304,0)]):
        actual=(q(4096+i*32),q(4104+i*32));assert actual==expected,('cache',i,actual,expected)
    return dict(replies=rows,cache_cases=5)
