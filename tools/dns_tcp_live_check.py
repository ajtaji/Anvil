"""Check the TCP DNS wire response independently of the compiled decoder."""
import struct


def check(data,cases):
    q=lambda p:struct.unpack_from('<q',data,p)[0]
    assert len(data)==16384 and q(0)==0x444e544c
    assert q(8)==3 and q(16)==0 and q(48)==0,[q(p) for p in range(8,72,8)]
    size=q(56);assert 14<=size<=4096 and q(64)>2
    wire=data[256:256+size];assert int.from_bytes(wire[:2],'big')==size-2
    body=wire[2:];qid,flags,qd,an,ns,ar=struct.unpack_from('>6H',body)
    assert qid==0x4231 and flags&0x8000 and not flags&0x020f and qd==1
    def name(pos):
        labels=[];end=None
        for _ in range(128):
            n=body[pos];pos+=1
            if n&0xc0==0xc0:
                target=((n&63)<<8)|body[pos]
                if end is None:end=pos+1
                pos=target;continue
            assert n<64 and pos+n<=len(body)
            if not n:return b'.'.join(labels).lower(),end if end is not None else pos
            labels.append(body[pos:pos+n]);pos+=n
        raise AssertionError('name pointer loop')
    question,pos=name(12);assert question==b'example.com'
    assert body[pos:pos+4]==b'\0\1\0\1';pos+=4
    answers=[]
    for _ in range(an):
        owner,pos=name(pos);kind,klass,ttl,n=struct.unpack_from('>HHIH',body,pos);pos+=10
        assert pos+n<=len(body)
        if owner==question and kind==1 and klass==1:
            assert n==4;answers.append((int.from_bytes(body[pos:pos+4],'big'),ttl if ttl<0x80000000 else 0))
        pos+=n
    assert answers and q(24) in [a[0] for a in answers]
    assert q(32)==min(a[1] for a in answers)
    return dict(passed=True,milliseconds=q(40),answer_bytes=size-2,ttl=q(32),address_count=len(answers))
