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
    assert len(raw)==32768 and struct.unpack_from('<QQ',raw)==(0x57534331,16)
    expected=[2,2,-607,-606,-605,-554,-553,-552,2,-552,-105,-109,-553,2,-552,2]
    rows=[]
    for i in cases:
        p=256+i*1024
        row=struct.unpack_from('<8q',raw,p)
        rc,state,closed,n,count,tx,rng,tick=row
        drains,dropped,late_recv,repeated=struct.unpack_from('<4q',raw,p+80)
        assert rc==expected[i] and repeated==rc,(i,row,repeated)
        assert closed==1 and state==(3 if rc==2 else -1),(i,row)
        assert late_recv==0,(i,'received after close drain',late_recv)
        if i in (0,1,4,8,9,10,11,12,13,14):
            assert raw[p+64:p+64+n]==b'Hi' and count==2,(i,n,count)
        else:assert n==0,(i,n)
        wire=frames(raw[p+256:p+256+tx])
        if i in (0,1,8,9,10,11,12,13):
            assert wire==[(1,b'Hello'),(10,b'!'),(8,b'\x03\xe8')],(i,wire)
        if i in (7,15):assert wire==[(8,b'')],(i,wire)
        if i==14:assert wire==[(1,b'Hello'),(10,b'!')],(i,wire)
        if i in (8,15):assert drains==6 and dropped==0,(i,drains,dropped)
        if i in (7,9,14):assert tick>=2000,(i,tick)
        if i==9:assert drains>1000 and dropped==8,(i,drains,dropped)
        if i==10:assert drains==1 and dropped==8,(i,drains,dropped)
        if i==11:assert drains==0 and dropped==8,(i,drains,dropped)
        if i==12:assert drains==2 and dropped==8,(i,drains,dropped)
        if i in (0,1,13,14):assert drains==0 and dropped==0,(i,drains,dropped)
        rows.append(dict(case=i,row=row,drains=drains,dropped=dropped,late_recv=late_recv,repeated=repeated))
    return dict(passed=True,rows=rows)
