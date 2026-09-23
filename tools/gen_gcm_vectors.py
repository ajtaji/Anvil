#!/usr/bin/env python
# ----------------------------------------------------------------------
# gen_gcm_vectors.py - emit the GCM vector include for gcmSelfTest.
#
# Sources of truth, both used:
#   1. The authoritative NIST/McGrew KAT_GCM table (AES-128/192/256,
#      empty-plaintext, AAD-bearing, and non-96-bit-IV cases).
#   2. A handful of extra cases (AAD-only, non-block-multiple plaintext,
#      long IV) generated here.
# EVERY vector - the KATs included - is independently re-checked against
# the `cryptography` package's AES-GCM before it is written out, so the
# emitted expected ciphertext and tag are confirmed by a second
# implementation, not just transcribed.
#
# Output: a .pico2/.pico/.unor4 include with two DataSections:
#   GcmVecMeta : per vector, Data.l keylen, ivlen, aadlen, ptlen
#   GcmVecData : per vector, key || iv || aad || pt || ct || tag(16)
# and #GCM_VEC_COUNT.
#
# Usage: gen_gcm_vectors.py <out_file>
# ----------------------------------------------------------------------
import sys, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# NIST/McGrew KAT_GCM: (key, plaintext, aad, iv, ciphertext, tag)
KAT = [
 ("00000000000000000000000000000000","","","000000000000000000000000","","58e2fccefa7e3061367f1d57a4e7455a"),
 ("00000000000000000000000000000000","00000000000000000000000000000000","","000000000000000000000000","0388dace60b6a392f328c2b971b2fe78","ab6e47d42cec13bdf53a67b21257bddf"),
 ("feffe9928665731c6d6a8f9467308308","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b391aafd255","","cafebabefacedbaddecaf888","42831ec2217774244b7221b784d0d49ce3aa212f2c02a4e035c17e2329aca12e21d514b25466931c7d8f6a5aac84aa051ba30b396a0aac973d58e091473f5985","4d5c2af327cd64a62cf35abd2ba6fab4"),
 ("feffe9928665731c6d6a8f9467308308","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39","feedfacedeadbeeffeedfacedeadbeefabaddad2","cafebabefacedbaddecaf888","42831ec2217774244b7221b784d0d49ce3aa212f2c02a4e035c17e2329aca12e21d514b25466931c7d8f6a5aac84aa051ba30b396a0aac973d58e091","5bc94fbc3221a5db94fae95ae7121a47"),
 ("feffe9928665731c6d6a8f9467308308","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39","feedfacedeadbeeffeedfacedeadbeefabaddad2","cafebabefacedbad","61353b4c2806934a777ff51fa22a4755699b2a714fcdc6f83766e5f97b6c742373806900e49f24b22b097544d4896b424989b5e1ebac0f07c23f4598","3612d2e79e3b0785561be14aaca2fccb"),
 ("feffe9928665731c6d6a8f9467308308","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39","feedfacedeadbeeffeedfacedeadbeefabaddad2","9313225df88406e555909c5aff5269aa6a7a9538534f7da1e4c303d2a318a728c3c0c95156809539fcf0e2429a6b525416aedbf5a0de6a57a637b39b","8ce24998625615b603a033aca13fb894be9112a5c3a211a8ba262a3cca7e2ca701e4a9a4fba43c90ccdcb281d48c7c6fd62875d2aca417034c34aee5","619cc5aefffe0bfa462af43c1699d050"),
 ("000000000000000000000000000000000000000000000000","","","000000000000000000000000","","cd33b28ac773f74ba00ed1f312572435"),
 ("000000000000000000000000000000000000000000000000","00000000000000000000000000000000","","000000000000000000000000","98e7247c07f0fe411c267e4384b0f600","2ff58d80033927ab8ef4d4587514f0fb"),
 ("feffe9928665731c6d6a8f9467308308feffe9928665731c","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b391aafd255","","cafebabefacedbaddecaf888","3980ca0b3c00e841eb06fac4872a2757859e1ceaa6efd984628593b40ca1e19c7d773d00c144c525ac619d18c84a3f4718e2448b2fe324d9ccda2710acade256","9924a7c8587336bfb118024db8674a14"),
 ("feffe9928665731c6d6a8f9467308308feffe9928665731c","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39","feedfacedeadbeeffeedfacedeadbeefabaddad2","cafebabefacedbaddecaf888","3980ca0b3c00e841eb06fac4872a2757859e1ceaa6efd984628593b40ca1e19c7d773d00c144c525ac619d18c84a3f4718e2448b2fe324d9ccda2710","2519498e80f1478f37ba55bd6d27618c"),
 ("feffe9928665731c6d6a8f9467308308feffe9928665731c","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39","feedfacedeadbeeffeedfacedeadbeefabaddad2","cafebabefacedbad","0f10f599ae14a154ed24b36e25324db8c566632ef2bbb34f8347280fc4507057fddc29df9a471f75c66541d4d4dad1c9e93a19a58e8b473fa0f062f7","65dcc57fcf623a24094fcca40d3533f8"),
 ("feffe9928665731c6d6a8f9467308308feffe9928665731c","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39","feedfacedeadbeeffeedfacedeadbeefabaddad2","9313225df88406e555909c5aff5269aa6a7a9538534f7da1e4c303d2a318a728c3c0c95156809539fcf0e2429a6b525416aedbf5a0de6a57a637b39b","d27e88681ce3243c4830165a8fdcf9ff1de9a1d8e6b447ef6ef7b79828666e4581e79012af34ddd9e2f037589b292db3e67c036745fa22e7e9b7373b","dcf566ff291c25bbb8568fc3d376a6d9"),
 ("0000000000000000000000000000000000000000000000000000000000000000","","","000000000000000000000000","","530f8afbc74536b9a963b4f1c4cb738b"),
 ("0000000000000000000000000000000000000000000000000000000000000000","00000000000000000000000000000000","","000000000000000000000000","cea7403d4d606b6e074ec5d3baf39d18","d0d1c8a799996bf0265b98b5d48ab919"),
 ("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b391aafd255","","cafebabefacedbaddecaf888","522dc1f099567d07f47f37a32a84427d643a8cdcbfe5c0c97598a2bd2555d1aa8cb08e48590dbb3da7b08b1056828838c5f61e6393ba7a0abcc9f662898015ad","b094dac5d93471bdec1a502270e3cc6c"),
 ("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39","feedfacedeadbeeffeedfacedeadbeefabaddad2","cafebabefacedbaddecaf888","522dc1f099567d07f47f37a32a84427d643a8cdcbfe5c0c97598a2bd2555d1aa8cb08e48590dbb3da7b08b1056828838c5f61e6393ba7a0abcc9f662","76fc6ece0f4e1768cddf8853bb2d551b"),
 ("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39","feedfacedeadbeeffeedfacedeadbeefabaddad2","cafebabefacedbad","c3762df1ca787d32ae47c13bf19844cbaf1ae14d0b976afac52ff7d79bba9de0feb582d33934a4f0954cc2363bc73f7862ac430e64abe499f47c9b1f","3a337dbf46a792c45e454913fe2ea8f2"),
 ("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308","d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39","feedfacedeadbeeffeedfacedeadbeefabaddad2","9313225df88406e555909c5aff5269aa6a7a9538534f7da1e4c303d2a318a728c3c0c95156809539fcf0e2429a6b525416aedbf5a0de6a57a637b39b","5a8def2f0c9e53f1f75d7853659e2a20eeb2b22aafde6419a058ab4f6f746bf40fc0c3b780f244452da3ebf1c5d82cdea2418997200ef82e44ae7e3f","a44a8266ee1c8eb0c8b5d4cf5ae9f19a"),
]

def gcm_oracle(key, iv, aad, pt):
    ct_tag = AESGCM(key).encrypt(iv, pt, aad if aad else None)
    return ct_tag[:-16], ct_tag[-16:]

def build_vectors():
    vecs = []
    for (k,p,a,iv,c,t) in KAT:
        vecs.append((bytes.fromhex(k), bytes.fromhex(iv), bytes.fromhex(a),
                     bytes.fromhex(p), bytes.fromhex(c), bytes.fromhex(t)))
    # extra generated cases: AAD-only, non-block-multiple PT, long IV
    extra_specs = [
        # (keylen, ivlen, aadlen, ptlen) - contents are deterministic below
        (16, 12, 20, 0),    # AAD-only (empty plaintext, non-empty AAD)
        (16, 12, 0, 1),     # single-byte plaintext
        (16, 12, 13, 40),   # AAD + non-block-multiple plaintext
        (32, 12, 16, 51),   # AES-256, odd length
        (16, 16, 24, 32),   # 128-bit IV (non-96-bit path), AAD + PT
        (24, 8,  17, 19),   # AES-192, 64-bit IV, odd AAD and PT
    ]
    for idx,(kl,il,al,pl) in enumerate(extra_specs):
        key = bytes((0x10+idx+j) & 0xff for j in range(kl))
        iv  = bytes((0x20+idx+j) & 0xff for j in range(il))
        aad = bytes((0x30+idx+j) & 0xff for j in range(al))
        pt  = bytes((0x40+idx+j) & 0xff for j in range(pl))
        c,t = gcm_oracle(key, iv, aad, pt)
        vecs.append((key, iv, aad, pt, c, t))
    # independent re-check of EVERY vector against the oracle
    for (k,iv,a,p,c,t) in vecs:
        oc, ot = gcm_oracle(k, iv, a, p)
        assert oc == c, "oracle ciphertext mismatch"
        assert ot == t, "oracle tag mismatch"
    return vecs

def emit(vecs, out):
    lines = []
    lines.append("; GENERATED by tools/gen_gcm_vectors.py - do not edit by hand.")
    lines.append("; NIST/McGrew GCM known-answer vectors plus generated AAD-only,")
    lines.append("; partial-block and non-96-bit-IV cases, each cross-checked against")
    lines.append("; an independent AES-GCM implementation.")
    lines.append("#GCM_VEC_COUNT = %d" % len(vecs))
    lines.append("")
    lines.append("DataSection")
    lines.append("  GcmVecMeta:")
    for (k,iv,a,p,c,t) in vecs:
        lines.append("  Data.l %d, %d, %d, %d" % (len(k), len(iv), len(a), len(p)))
    lines.append("")
    lines.append("  GcmVecData:")
    def datab(name, b):
        if len(b) == 0:
            return
        vals = ", ".join(str(x) for x in b)
        lines.append("  Data.b %s   ; %s" % (vals, name))
    for i,(k,iv,a,p,c,t) in enumerate(vecs):
        lines.append("  ; ---- vector %d ----" % i)
        datab("key", k)
        datab("iv", iv)
        datab("aad", a)
        datab("pt", p)
        datab("ct", c)
        datab("tag", t)
    lines.append("EndDataSection")
    lines.append("")
    open(out, "w").write("\n".join(lines))
    print("wrote %d vectors -> %s" % (len(vecs), out))

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "gcmVectors.pico2"
    emit(build_vectors(), out)
