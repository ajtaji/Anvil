"""Independent integer/wire expectations from RFC 9000, not implementation output."""
import random
MAX=(1<<62)-1
ARG,SHORT,VERSION,RANGE,FORMAT=-3301,-3302,-3303,-3304,-3305

def integer(value,width=0):
    if not width:width=next(n for n in (1,2,4,8) if value<(1<<(8*n-2)))
    return (({1:0,2:1,4:2,8:3}[width]<<(8*width-2))|value).to_bytes(width,'big')

def long(kind=0,dcid=b'abcdefgh',scid=b'WXYZ',token=b'',pn=7,pnbytes=4,cipher=16):
    prefix=bytes([192+16*kind+pnbytes-1])+b'\0\0\0\1'+bytes([len(dcid)])+dcid+bytes([len(scid)])+scid
    if kind==0:prefix+=integer(len(token))+token
    return prefix+integer(pnbytes+cipher)+pn.to_bytes(pnbytes,'big')

def cases():
    rows=[]
    def add(name,op,wire=b'',args=(),rc=1,**expected):
        rows.append(dict(name=name,op=op,wire=wire.hex(),args=list(args),rc=rc,**expected))
    values=[0,1,63,64,16383,16384,(1<<30)-1,1<<30,MAX]
    values += [37,15293,494878333,151288809941952652]
    for value in values:
        for width in (1,2,4,8):
            if value >= 1<<(width*8-2):continue
            wire=integer(value,width)
            add(f'integer-{value}-{width}',0,wire,rc=width,value=value)
            for n in range(width):add(f'integer-cut-{value}-{width}-{n}',0,wire[:n],rc=SHORT,value=-777)
            add(f'write-{value}-{width}',1,args=(value,width,16),rc=width,output=wire.hex())
        wire=integer(value)
        add(f'write-minimal-{value}',1,args=(value,0,16),rc=len(wire),output=wire.hex())
        add(f'write-short-{value}',1,args=(value,0,len(wire)-1),rc=SHORT,output='')
    for value,width,capacity,rc in [(-1,0,16,RANGE),(MAX+1,0,16,RANGE),(64,1,16,RANGE),(1,3,16,ARG),(1,1,-1,ARG)]:
        add(f'write-invalid-{value}-{width}-{capacity}',1,args=(value,width,capacity),rc=rc,output='')
    # Packet header field order matches the documented public structure.
    def packet(name,wire,kind,dcid,scid,token,pnoff,protected,packetbytes,voff=0,vcount=0,shortid=0,version=1):
        expected=[wire[0],version,kind,*dcid,*scid,*token,pnoff,protected,packetbytes,voff,vcount]
        add(name,2,wire,args=(shortid,),fields=expected)
    for kind in (0,1,2):
        for dcid,scid,token in [(b'',b'',b''),(b'abcdefgh',b'WXYZ',b'abc' if kind==0 else b''),(b'd'*20,b's'*20,b't'*70 if kind==0 else b'')]:
            header=long(kind,dcid,scid,token);wire=header+b'\0'*16
            at=7+len(dcid)+len(scid)
            tok=(at+len(integer(len(token))),len(token)) if kind==0 else (0,0)
            packet(f'packet-{kind}-{len(dcid)}',wire,kind,(6,len(dcid)),(7+len(dcid),len(scid)),tok,len(header)-4,20,len(wire))
    header=long();wire=header+b'\0'*16
    packet('coalesced-first',wire+long(2)+b'\0'*16,0,(6,8),(15,4),(20,0),len(header)-4,20,len(wire))
    for n in range(len(wire)):add(f'packet-cut-{n}',2,wire[:n],rc=SHORT)
    # Length values that fit in all legal widths; reserved/PN bits remain opaque.
    for width in (2,4,8):
        head=b'\xcf\0\0\0\1\0\0'+integer(0,8)+integer(20,width)
        packet(f'nonminimal-length-{width}',head+b'\0'*20,0,(6,0),(7,0),(15,0),len(head),20,len(head)+20)
    for n in (0,1,19):add(f'too-short-protected-{n}',2,b'\xe0\0\0\0\1\0\0'+integer(n)+b'\0'*n,rc=FORMAT)
    add('length-overflow',2,b'\xe0\0\0\0\1\0\0'+integer(MAX),rc=SHORT)
    add('token-overflow',2,b'\xc0\0\0\0\1\0\0'+integer(MAX),rc=SHORT)
    add('large-dcid-v1',2,b'\xc0\0\0\0\1\x15'+b'a'*21+b'\0',rc=FORMAT)
    add('large-scid-v1',2,b'\xc0\0\0\0\1\0\x15'+b'a'*21,rc=FORMAT)
    add('fixed-bit-long',2,b'\x80\0\0\0\1\0\0',rc=FORMAT)
    add('fixed-bit-short',2,b'\0'+b'\0'*20,rc=FORMAT)
    add('unknown-version',2,b'\x80\xff\xff\xff\xff\x15'+b'a'*21+b'\0',rc=VERSION)
    for n in (0,8,20):
        wire=b'\x7f'+b'd'*n+b'\0'*20
        packet(f'short-{n}',wire,4,(1,n),(0,0),(0,0),1+n,20,len(wire),shortid=n)
        add(f'short-truncated-{n}',2,wire[:-1],args=(n,),rc=SHORT)
    add('bad-short-id',2,b'\x40'+b'\0'*30,args=(21,),rc=ARG)
    for cid in (b'',b'd'*255):
        wire=b'\x80\0\0\0\0'+bytes([len(cid)])+cid+b'\0'+b'\0\0\0\1\x6b\x33\x43\xcf'
        packet(f'negotiation-{len(cid)}',wire,5,(6,len(cid)),(7+len(cid),0),(0,0),0,0,len(wire),7+len(cid),2,version=0)
    for n in (0,1,3,5):add(f'bad-vn-{n}',2,b'\xff\0\0\0\0\0\0'+b'\0'*n,rc=FORMAT)
    retry=b'\xff\0\0\0\1\0\0abc'+b'\0'*16
    packet('retry',retry,3,(6,0),(7,0),(7,3),0,0,len(retry))
    for n in (0,15,16):add(f'empty-retry-{n}',2,b'\xf0\0\0\0\1\0\0'+b'\0'*n,rc=SHORT)
    # Golden reconstruction selects the nearest representative; ties go up.
    rng=random.Random(9000)
    pnrows=[(0,1,-1),(255,1,-1),(0,1,255),(255,1,256),(0,1,127),(255,1,126),(0x9b32,2,0xa82f30ea)]
    for width in range(1,5):
        pnrows += [(rng.randrange(1<<(8*width)),width,rng.randrange(MAX-1000000)) for _ in range(16)]
    pnrows += [(255,1,MAX-1),(0,1,MAX),(0,1,MAX-1)]
    for index,(low,width,largest) in enumerate(pnrows):
        span=1<<(8*width);expected=largest+1;base=(expected//span)*span+low
        # Do not move a valid base above the maximum PN. An already overflowing
        # base can still be selected by the nearest window and must be refused.
        window=[v for v in (base-span,base,base+span) if v>=0 and (v<=MAX or base>MAX)]
        value=min(window,key=lambda v:(abs(v-expected),-v))
        rc=1 if value<=MAX else RANGE
        add(f'number-{index}',3,args=(low,width,largest),rc=rc,value=value if rc==1 else -777)
    for args,rc in [((256,1,0),RANGE),((-1,1,0),RANGE),((0,0,0),ARG),((0,5,0),ARG),((0,1,-2),RANGE)]:
        add(f'invalid-number-{args}',3,args=args,rc=rc,value=-777)
    for kind in range(3):
        for width in range(1,5):
            token=b'abc' if kind==0 else b''
            wire=long(kind,token=token,pn=(1<<(width*8))-1,pnbytes=width,cipher=20-width)
            spec=[kind,8,4,len(token),(1<<(width*8))-1,width,20-width]
            add(f'long-write-{kind}-{width}',4,b'abcdefghWXYZ'+token,args=(128,),rc=len(wire),spec=spec,output=wire.hex())
            add(f'long-write-short-{kind}-{width}',4,b'abcdefghWXYZ'+token,args=(len(wire)-1,),rc=SHORT,spec=spec,output='')
    for spec,rc in [([3,0,0,0,0,4,16],ARG),([0,21,0,0,0,4,16],ARG),([1,0,0,1,0,4,16],ARG),([0,0,0,0,256,1,19],RANGE),([0,0,0,0,0,4,15],RANGE),([0,0,0,0,0,1,16],RANGE),([0,0,0,0,0,4,MAX],RANGE)]:
        add(f'bad-long-{spec}',4,b'x'*64,args=(128,),rc=rc,spec=spec,output='')
    for which in range(11):add(f'null-or-negative-{which}',5,b'x',args=(which,),rc=ARG)
    return rows
