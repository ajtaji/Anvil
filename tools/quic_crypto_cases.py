"""Independent QUIC protection oracle: standard Python HMAC and cryptography AEAD."""
import hashlib,hmac,re
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from quic_wire_cases import long
SALT=bytes.fromhex('38762cf7f55934b34d179ae6a4c80cadccbb7f0a')
CID=bytes.fromhex('8394c8f03e515708')

def expand(secret,label,n):
    label=b'tls13 '+label
    info=n.to_bytes(2,'big')+bytes([len(label)])+label+b'\0'
    return hmac.new(secret,info+b'\x01',hashlib.sha256).digest()[:n]

def keys(seed,side,traffic=False):
    secret=seed if traffic else expand(hmac.new(SALT,seed,hashlib.sha256).digest(),b'server in' if side else b'client in',32)
    return secret,expand(secret,b'quic key',16),expand(secret,b'quic iv',12),expand(secret,b'quic hp',16)

def protect(header,plain,number,k):
    secret,key,iv,hp=k
    nonce=(int.from_bytes(iv,'big')^number).to_bytes(12,'big')
    wire=bytearray(header+AESGCM(key).encrypt(nonce,plain,header))
    width=(header[0]&3)+1;offset=len(header)-width
    mask=Cipher(algorithms.AES(hp),modes.ECB()).encryptor().update(bytes(wire[offset+4:offset+20]))
    wire[0]^=mask[0]&(15 if header[0]&128 else 31)
    for i in range(width):wire[offset+i]^=mask[i+1]
    return bytes(wire)

def rfc_vectors(text):
    result=[]
    for title,end,side in [('A.2.  Client Initial','A.3.  Server Initial',0),('A.3.  Server Initial','A.4.  Retry',1)]:
        section=text[text.rindex(title):text.rindex(end)]
        groups=re.findall(r'(?m)(?:^   [0-9a-f]{2,}(?: [0-9a-f]+)*\s*\n)+',section)
        blobs=[bytes.fromhex(g) for g in groups]
        # The longest hex block is the fully protected packet; the first block
        # is plaintext, and the next short block is its unprotected header.
        wire=max(blobs,key=len);plain=blobs[0];header=blobs[1]
        if side==0:plain=plain.ljust(1162,b'\0');number=2
        else:number=1
        assert protect(header,plain,number,keys(CID,side))==wire,(title,[len(b) for b in blobs])
        result.append(dict(header=header.hex(),plain=plain.hex(),wire=wire.hex(),number=number,side=side))
    return result

def cases(vectors):
    rows=[]
    def pair(name,header,plain,pn,seed=CID,side=0,traffic=False,shortid=0):
        k=keys(seed,side,traffic);wire=protect(header,plain,pn,k)
        common=dict(name=name,seed=seed.hex(),side=side,traffic=traffic,shortid=shortid,number=pn,header=header.hex(),plain=plain.hex(),keys=[x.hex() for x in k],rc=1,mode=0,cancel=0,wrong_key=False)
        rows.append(dict(common,encrypt=1,input=(header+plain+b'\0'*16).hex(),output=wire.hex()))
        rows.append(dict(common,encrypt=0,input=wire.hex(),output=(header+plain+wire[-16:]).hex()))
        return wire,common
    for n,v in enumerate(vectors):pair(f'rfc-initial-{n}',bytes.fromhex(v['header']),bytes.fromhex(v['plain']),v['number'],side=v['side'])
    for width in range(1,5):
        pn=(1<<(width*8-1))+7;plain=bytes(range(33))
        pair(f'handshake-{width}',long(2,pn=pn,pnbytes=width,cipher=len(plain)+16),plain,pn)
    traffic=bytes(range(32));pn=(1<<40)+17;plain=b'HTTP/3 packet protection boundary'
    header=b'\x43abcdefgh'+(pn&0xffffffff).to_bytes(4,'big')
    wire,base=pair('traffic-short-high-pn',header,plain,pn,seed=traffic,traffic=True,shortid=8)
    for i in range(16):
        altered=bytearray(wire);altered[-1-i]^=1
        rows.append(dict(base,name=f'bad-tag-{i}',encrypt=0,input=altered.hex(),output=altered.hex(),rc=-3343))
    for pos in [0,1,9,15]:
        altered=bytearray(wire);altered[pos]^=8 if pos==0 else 1
        rows.append(dict(base,name=f'bad-header-cipher-{pos}',encrypt=0,input=altered.hex(),output=altered.hex(),rc=-3343))
    reserved=bytes([header[0]|8])+header[1:]
    altered=protect(reserved,plain,pn,keys(traffic,0,True))
    rows.append(dict(base,name='authenticated-reserved',encrypt=0,input=altered.hex(),output=altered.hex(),rc=-3344))
    rows.append(dict(base,name='wrong-payload-key',encrypt=0,input=wire.hex(),output=wire.hex(),rc=-3343,wrong_key=True))
    for encrypt in (0,1):
        for step in (1,2):
            data=wire if encrypt==0 else header+plain+b'\0'*16
            rows.append(dict(base,name=f'cancel-{encrypt}-{step}',encrypt=encrypt,input=data.hex(),output=None,rc=-3345,cancel=step))
    rows.append(dict(base,name='second-packet-owner',encrypt=0,input=wire.hex(),output=(header+plain+wire[-16:]).hex(),mode=1))
    rows.append(dict(base,name='foreign-gcm-owner',encrypt=0,input=wire.hex(),output=wire.hex(),rc=-3342,mode=2))
    for phase in (0,1,2,3,4):
        rows.append(dict(base,name=f'key-cancel-{phase}',seed=CID.hex(),traffic=False,encrypt=0,input=wire.hex(),output=wire.hex(),rc=-3345,mode=3,cancel=phase))
    rows.extend([dict(rows[0],name='tls-interleave-encrypt',mode=4),dict(rows[1],name='tls-interleave-decrypt',mode=4)])
    # RFC 9001 Appendix A.4, independently reproduced with AESGCM.
    retry=bytes.fromhex('ff000000010008f067a5502a4262b5746f6b656e04a265ba2eff4d829058fb3f0f2496ba')
    retrykey=bytes.fromhex('be0c690b9f66575a1d766b54e368c84e')
    retrynonce=bytes.fromhex('461599d35d632bf2239825bb')
    def retry_pair(name,odcid,header):
        prefix=bytes([len(odcid)])+odcid
        tag=AESGCM(retrykey).encrypt(retrynonce,b'',prefix+header)
        wire=prefix+header+tag
        common=dict(rows[0],name=name,retry=1,number=0,header=header.hex(),plain='')
        rows.append(dict(common,encrypt=1,input=(prefix+header+b'\0'*16).hex(),output=wire.hex()))
        rows.append(dict(common,encrypt=0,input=wire.hex(),output=wire.hex()))
        return rows[-1]
    sample=retry_pair('rfc-retry',CID,retry[:-16])
    assert bytes.fromhex(sample['input'])[9:]==retry
    retry_pair('retry-zero-odcid',b'',retry[:15]+b'x')
    retry_pair('retry-long-token',bytes(range(20)),retry[:15]+bytes(range(256))*4)
    for i in range(16):
        bad=bytearray.fromhex(sample['input']);bad[-1-i]^=1
        rows.append(dict(sample,name=f'retry-bad-tag-{i}',input=bad.hex(),output=bad.hex(),rc=-3343))
    for pos in (1,9,25):
        bad=bytearray.fromhex(sample['input']);bad[pos]^=1
        rows.append(dict(sample,name=f'retry-bad-id-header-token-{pos}',input=bad.hex(),output=bad.hex(),rc=-3343))
    rows.append(dict(sample,name='retry-second-owner',mode=1))
    rows.append(dict(sample,name='retry-foreign-owner',mode=2,rc=-3342))
    for step in (1,2):rows.append(dict(sample,name=f'retry-cancel-{step}',cancel=step,rc=-3345))
    rows.extend([dict(sample,name='retry-tls-interleave',mode=4),dict(rows[-2],name='retry-cancel-tls',mode=4)])
    bad=bytes([21])+bytes.fromhex(sample['input'])[1:]
    rows.append(dict(sample,name='retry-invalid-odcid-length',input=bad.hex(),output=bad.hex(),rc=-3341,begin_error=True))
    bad=bytes([8])+CID+bytes.fromhex(rows[1]['input'])
    rows.append(dict(sample,name='retry-wrong-packet-kind',input=bad.hex(),output=bad.hex(),rc=-3341,begin_error=True))
    return rows
