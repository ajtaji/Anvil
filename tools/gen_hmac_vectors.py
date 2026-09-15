#!/usr/bin/env python
# ----------------------------------------------------------------------
# gen_hmac_vectors.py - emit a house-dialect DataSection include of
# HMAC-SHA-256 test vectors for the M2 self-test (BearSSL TLS translation,
# LANE A).
#
# Two sources of truth, both external to the library under test:
#   * RFC 4231 test cases 1-7 (the standard HMAC-SHA-256 vectors). Their
#     expected MACs are recomputed here with python's hmac module and, for
#     the RFC-published bytes, asserted to match - so a transcription slip
#     in either place is caught at generation time.
#   * ~50 random (key,message) pairs with python-hmac reference MACs.
#
# Layout is one forward-readable stream, like gen_sha256_vectors.py: a meta
# table (keylen, msglen, outlen per case, Read.l) then, per case, the key
# bytes, the message bytes and the outlen expected MAC bytes (Read.b). The
# self-test reads the meta whole, then walks the data section once.
#
# Deterministic: a fixed seed means the same vectors every run.
#
# Usage:  python tools/gen_hmac_vectors.py [randcount] > out.inc
# ----------------------------------------------------------------------
import sys, random, hmac, hashlib

def mac(key, msg, outlen=32):
    d = hmac.new(key, msg, hashlib.sha256).digest()
    return d[:outlen]

# RFC 4231, cases 1-7. (key, message, out_len, published_mac_or_None)
# The published MACs are the RFC's own hex; case 5 is the 128-bit
# truncation case, so out_len there is 16.
RFC4231 = [
    (bytes.fromhex("0b"*20),
     b"Hi There", 32,
     "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"),
    (b"Jefe",
     b"what do ya want for nothing?", 32,
     "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"),
    (bytes.fromhex("aa"*20),
     bytes.fromhex("dd"*50), 32,
     "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe"),
    (bytes.fromhex("0102030405060708090a0b0c0d0e0f10111213141516171819"),
     bytes.fromhex("cd"*50), 32,
     "82558a389a443c0ea4cc819899f2083a85f0faa3e578f8077a2e3ff46729665b"),
    (bytes.fromhex("0c"*20),
     b"Test With Truncation", 16,
     "a3b6167473100ee06e0c796c2955552b"),
    (bytes.fromhex("aa"*131),
     b"Test Using Larger Than Block-Size Key - Hash Key First", 32,
     "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"),
    (bytes.fromhex("aa"*131),
     b"This is a test using a larger than block-size key and a larger "
     b"than block-size data. The key needs to be hashed before being "
     b"used by the HMAC algorithm.", 32,
     "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2"),
]

def build_cases(randcount, seed=0x4231):
    cases = []
    for key, msg, outlen, pub in RFC4231:
        got = mac(key, msg, outlen)
        if pub is not None:
            want = bytes.fromhex(pub)
            assert got == want, "RFC 4231 mismatch: %s vs %s" % (got.hex(), pub)
        cases.append((key, msg, outlen, got))
    rng = random.Random(seed)
    # random keys (0..80 bytes, straddling the 64-byte block boundary so
    # the hash-the-key path is exercised) and messages (0..200 bytes).
    for _ in range(randcount):
        klen = rng.randint(0, 80)
        mlen = rng.randint(0, 200)
        key = bytes(rng.randint(0, 255) for _ in range(klen))
        msg = bytes(rng.randint(0, 255) for _ in range(mlen))
        cases.append((key, msg, 32, mac(key, msg, 32)))
    return cases

def emit(randcount=50, seed=0x4231):
    cases = build_cases(randcount, seed)
    out = []
    out.append("; ======================================================================")
    out.append("; hmac-sha256 test vectors - AUTO-GENERATED, do not edit by hand.")
    out.append(";   generator: tools/gen_hmac_vectors.py   seed: 0x%04X" % seed)
    out.append(";   RFC 4231 cases 1-7 (case 5 is the 128-bit truncation), then")
    out.append(";   %d random (key,message) pairs with python-hmac reference MACs." % randcount)
    out.append("; Meta table: keylen, msglen, outlen per case (Read.l). Data stream:")
    out.append(";   per case its key bytes, message bytes, then outlen MAC bytes.")
    out.append("; ======================================================================")
    out.append("#HMAC_VEC_COUNT = %d" % len(cases))
    out.append("")
    out.append("DataSection")
    out.append("  HmacVecMeta:")
    for key, msg, outlen, _ in cases:
        out.append("  Data.l %d, %d, %d" % (len(key), len(msg), outlen))
    out.append("  HmacVecData:")
    for idx, (key, msg, outlen, want) in enumerate(cases):
        blob = key + msg + want
        out.append("  ; --- case %d: keylen %d msglen %d outlen %d ---"
                   % (idx, len(key), len(msg), outlen))
        if len(blob) == 0:
            continue
        for i in range(0, len(blob), 16):
            row = blob[i:i+16]
            out.append("  Data.b " + ", ".join(str(b) for b in row))
    out.append("EndDataSection")
    out.append("")
    return "\n".join(out)

if __name__ == "__main__":
    randcount = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    sys.stdout.write(emit(randcount))
