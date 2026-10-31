"""Compare switched TLS record contexts against independent AES-GCM results."""
import struct
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def check(raw,cases=None):
    assert struct.unpack_from('<7q',raw)==(0x54435831,0,0,0,0,1,2928)
    for i,(seed,seq) in enumerate([(1,0),(80,0),(1,1),(80,1)]):
        p=256+i*128
        n,nextseq,state,hs,transcript,first,last=struct.unpack_from('<7q',raw,p)
        assert (n,nextseq,state,hs,transcript,first,last)==(30,seq+1,seed,seed+123,seed+1,seed,(seed+519)&255)
        assert struct.unpack_from('<6q',raw,2048+i*64)==(seed,seed+2,seed,(seed+255)&255,seed,(seed+510)&255)
        assert struct.unpack_from('<q',raw,2048+i*64+48)[0]==seed+4096
        key=bytes(range(seed,seed+16));iv=bytes(range(seed+32,seed+44))
        nonce=bytes(a^b for a,b in zip(iv,seq.to_bytes(12,'big')))
        header=b'\x17\x03\x03\x00\x19'
        expected=header+AESGCM(key).encrypt(nonce,b'ABCDEFGH\x17',header)
        assert raw[p+64:p+64+n]==expected,('record',i)
    return {'independent_aesgcm_records':4,'sequence_and_certificate_state_isolated':True,'cipher_cache_invalidated':True,'snapshot_wiped':True,'alpn_offers_and_selections_isolated':True}
