"""Check lifecycle outcomes and independently unmask emitted client frames."""
import struct

def frames(data):
    out=[];at=0
    while at<len(data):
        first,n=data[at:at+2];assert first&128 and n&128 and (n&127)<126
        n&=127;mask=data[at+2:at+6];assert len(mask)==4
        payload=bytes(x^mask[j%4] for j,x in enumerate(data[at+6:at+6+n]))
        assert len(payload)==n
        out.append((first&15,payload));at+=6+n
    assert at==len(data)
    return out

def check(raw,cases):
    assert len(raw)==16384 and struct.unpack_from('<QQ',raw)==(0x57534331,8)
    expected=[2,2,-607,-606,-605,-554,-553,-552]
    rows=[]
    for i in cases:
        p=256+i*1024;row=struct.unpack_from('<8q',raw,p);rc,state,closed,n,count,tx,rng,tick=row
        assert rc==expected[i],(i,row)
        assert closed==1,(i,'close count',closed)
        assert state==(3 if rc==2 else -1),(i,state)
        if i in (0,1,4):assert raw[p+64:p+64+n]==b'Hi' and count==2
        else:assert n==0
        if i in (0,1):assert frames(raw[p+256:p+256+tx])==[(1,b'Hello'),(10,b'!'),(8,b'\x03\xe8')]
        if i==7:assert frames(raw[p+256:p+256+tx])==[(8,b'')] and tick>=2000
        rows.append(row)
    return dict(passed=True,rows=rows)
