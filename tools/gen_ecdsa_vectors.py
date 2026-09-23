#!/usr/bin/env python
# ----------------------------------------------------------------------
# gen_ecdsa_vectors.py - emit the P-256 ECDSA signature-VERIFY vectors
# for the M9 self-test.
#
# The oracle is a self-contained, dependency-free pure-python P-256
# ECDSA implementation (affine curve arithmetic, RFC 6979 deterministic
# signing, and the FIPS 186-4 verify equation). No pip install, no
# network. Its correctness is ANCHORED before a single vector is
# written, against three INDEPENDENT published/produced sources - any
# mismatch aborts this script rather than baking a wrong expectation:
#
#   1. The P-256 generator-multiply known answer (NIST / vendor test
#      corpus): k*G for the RFC 6979 private key must be the published
#      public point.
#   2. RFC 6979 appendix A.2.5 - the PUBLISHED deterministic ECDSA
#      signatures over P-256 with SHA-256 for the messages "sample" and
#      "test". The oracle must reproduce both (r,s) pairs byte-exact
#      AND verify them, in raw and in DER form.
#   3. Two REAL certificate signatures produced by a different
#      implementation entirely (the OpenSSL-generated EC chain already
#      baked into the X.509 path-validation corpus): the end-entity
#      certificate signed by the intermediate CA, and the intermediate
#      signed by the root. Both must verify.
#
# ON CAVP: the NIST CAVP SigVer .rsp files are not present on this
# machine and this script installs nothing and fetches nothing. What is
# emitted therefore follows the CAVP SigVer RECORD SHAPE and its failure
# taxonomy - (Msg, Qx, Qy, R, S, Result) with the six standard reasons
# for an "F" record: message changed, R changed, S changed, wrong public
# key, R out of range, S out of range - with every expectation produced
# by the anchored oracle above. Where a record comes from a published
# source it is labelled as such in the emitted comment. Said plainly so
# the next reader knows which vectors are transcribed and which are
# oracle-derived.
#
# It writes ecdsaVectors.<ext> into each family's Verification folder
# (the vectors are portable; the self-test that reads them is built per
# family). Three case tables, all sharing one record layout:
#
#   u32 qlen | q bytes | u32 hashlen | hash bytes | u32 siglen |
#   sig bytes | u32 expected (1 = must verify, 0 = must be rejected) |
#   u32 case tag (echoed into the verdict globals on a failure)
#
#   EcdsaRawCases  - raw r||s signatures
#   EcdsaAsn1Cases - ASN.1 DER SEQUENCE{INTEGER r, INTEGER s}
#   EcdsaDerCases  - malformed DER shapes, every one expected to reject
#
# Usage:  python tools/gen_ecdsa_vectors.py
# ----------------------------------------------------------------------
import os, hmac, hashlib, random

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAMILIES = [
    ("RP2350/Examples/Diagnostics", "pico2"),
    ("RP2040/Examples/Diagnostics", "pico"),
    ("RA4M1AndRelated/Examples/Diagnostics", "unor4"),
]

# ------------------------------------------------------------- P-256
P  = 2**256 - 2**224 + 2**192 + 2**96 - 1
A  = (-3) % P
B  = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b
Gx = 0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296
Gy = 0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5
N  = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
G  = (Gx, Gy)


def inv(x, m=P):
    return pow(x, m - 2, m)


def pt_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        m = (3 * x1 * x1 + A) * inv(2 * y1) % P
    else:
        m = (y2 - y1) * inv(x2 - x1) % P
    x3 = (m * m - x1 - x2) % P
    return (x3, (m * (x1 - x3) - y1) % P)


def pt_mul(k, p):
    r = None
    while k:
        if k & 1:
            r = pt_add(r, p)
        p = pt_add(p, p)
        k >>= 1
    return r


def on_curve(x, y):
    return (y * y - (x * x * x + A * x + B)) % P == 0


def enc_point(pt):
    x, y = pt
    return bytes([0x04]) + x.to_bytes(32, "big") + y.to_bytes(32, "big")


def bits2int(h, qlen=256):
    x = int.from_bytes(h, "big")
    excess = len(h) * 8 - qlen
    if excess > 0:
        x >>= excess
    return x


def verify(q, msghash, r, s):
    """The reference verify. q is the 65-byte uncompressed point."""
    if len(q) != 65 or q[0] != 0x04:
        return False
    if not (1 <= r < N and 1 <= s < N):
        return False
    qx = int.from_bytes(q[1:33], "big")
    qy = int.from_bytes(q[33:65], "big")
    if qx >= P or qy >= P or not on_curve(qx, qy):
        return False
    e = bits2int(msghash)
    w = inv(s, N)
    pt = pt_add(pt_mul(e * w % N, G), pt_mul(r * w % N, (qx, qy)))
    if pt is None:
        return False
    return pt[0] % N == r % N


def sign_rfc6979(x, msghash):
    """RFC 6979 deterministic ECDSA, HMAC-SHA256, over P-256."""
    xb = x.to_bytes(32, "big")
    h1o = (bits2int(msghash) % N).to_bytes(32, "big")
    V = b"\x01" * 32
    K = b"\x00" * 32
    K = hmac.new(K, V + b"\x00" + xb + h1o, hashlib.sha256).digest()
    V = hmac.new(K, V, hashlib.sha256).digest()
    K = hmac.new(K, V + b"\x01" + xb + h1o, hashlib.sha256).digest()
    V = hmac.new(K, V, hashlib.sha256).digest()
    while True:
        V = hmac.new(K, V, hashlib.sha256).digest()
        k = bits2int(V)
        if 1 <= k < N:
            pt = pt_mul(k, G)
            r = pt[0] % N
            if r != 0:
                s = inv(k, N) * (bits2int(msghash) + r * x) % N
                if s != 0:
                    return r, s
        K = hmac.new(K, V + b"\x00", hashlib.sha256).digest()
        V = hmac.new(K, V, hashlib.sha256).digest()


# ------------------------------------------------------- encodings
def raw_sig(r, s, width=32):
    return r.to_bytes(width, "big") + s.to_bytes(width, "big")


def der_int(v):
    b = v.to_bytes(max(1, (v.bit_length() + 7) // 8), "big")
    if b[0] & 0x80:
        b = b"\x00" + b
    return bytes([0x02, len(b)]) + b


def der_sig(r, s):
    body = der_int(r) + der_int(s)
    assert len(body) < 0x80
    return bytes([0x30, len(body)]) + body


def der_split(sig):
    assert sig[0] == 0x30
    off = 2 if sig[1] < 0x80 else 3
    assert sig[off] == 0x02
    rl = sig[off + 1]
    r = int.from_bytes(sig[off + 2:off + 2 + rl], "big")
    off += 2 + rl
    assert sig[off] == 0x02
    sl = sig[off + 1]
    s = int.from_bytes(sig[off + 2:off + 2 + sl], "big")
    return r, s


# ------------------------------------------------- published anchors
# RFC 6979 appendix A.2.5 - P-256 key and its two SHA-256 signatures.
RFC6979_X  = 0xC9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721
RFC6979_UX = 0x60FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB6
RFC6979_UY = 0x7903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299
RFC6979_SIGS = {
    "sample": ("EFD48B2AACB6A8FD1140DD9CD45E81D69D2C877B56AAF991C34D0EA84EAF3716",
               "F7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8"),
    "test":   ("F1ABB023518351CD71D881567B1EA663ED3EFCF6C5132B354F28D3B0B7D38367",
               "019F4113742A2B14BD25926B49C649155F267E60D3814B4C0CC84250E46F0083"),
}

# Real ECDSA-P256/SHA-256 certificate signatures, produced by a different
# implementation and already baked into the X.509 chain corpus. Each is
# (TBS SHA-256 digest, issuer public point, DER signature).
REAL_CHAIN = [
    ("end-entity signed by the intermediate CA",
     "62eaed7ea9e5d0536e7a881e8df36ab54fb69ee8dfa82c6cb85562a7b7c3a348",
     "04702e928201176c6dabe1d163094849d2a63552d33c73bbb288379887f18de0ec"
     "659a0e13f5ed9161c8b66d33846eae8e5580cd499e07bfd0ae9de6d0b32716a1",
     "304502210091fbf404d0e52e01d48cf017620fdccc80ca18c4407c2703cb34030d"
     "9bc8594d0220055569e2d8a14033340e7e4932641d3f6b1fd02db72f520456afd3"
     "378f8799a2"),
    ("intermediate CA signed by the root",
     "a7edf7174945f5724f69b30c366607f5c8ada9f352981954c93c160c40ee28a8",
     "047174baabb9302e81d5e557f9f320680c9cf964dbb4200d6dea40d04a6e42fdb6"
     "9a682544f6df7bc4fcdedd7bbbc5db7c763f4166406edba787c2e5d8c5f37f8d",
     "304602210085e3466899d6027a59661cb74f352d083638617e0548d869431feb56"
     "e9ad060e0221008270b462034946c8545905d978db531ce06e66f50f143bc92d38"
     "12709156f9a9"),
]


def anchor():
    # 1. generator multiply known answer
    if pt_mul(RFC6979_X, G) != (RFC6979_UX, RFC6979_UY):
        raise SystemExit("ABORT: P-256 oracle failed the generator-multiply anchor")
    q = enc_point((RFC6979_UX, RFC6979_UY))
    # 2. RFC 6979 published signatures, reproduced and verified
    for msg, (wr, ws) in RFC6979_SIGS.items():
        h = hashlib.sha256(msg.encode()).digest()
        r, s = sign_rfc6979(RFC6979_X, h)
        if r != int(wr, 16) or s != int(ws, 16):
            raise SystemExit("ABORT: oracle failed the RFC 6979 anchor for %r" % msg)
        if not verify(q, h, r, s):
            raise SystemExit("ABORT: oracle cannot verify its own RFC 6979 anchor")
        rr, ss = der_split(der_sig(r, s))
        if (rr, ss) != (r, s):
            raise SystemExit("ABORT: DER round-trip broken for %r" % msg)
        # a one-bit change must NOT verify - an oracle that says yes to
        # everything anchors just as well as a correct one otherwise
        if verify(q, h, r ^ 1, s):
            raise SystemExit("ABORT: oracle accepted a corrupted r")
        if verify(q, bytes([h[0] ^ 1]) + h[1:], r, s):
            raise SystemExit("ABORT: oracle accepted a corrupted hash")
    # 3. real certificate signatures from a foreign implementation
    for name, hh, qq, sg in REAL_CHAIN:
        r, s = der_split(bytes.fromhex(sg))
        if not verify(bytes.fromhex(qq), bytes.fromhex(hh), r, s):
            raise SystemExit("ABORT: oracle rejected the real chain anchor (%s)" % name)
    return q


# ------------------------------------------------------ emit helpers
def u32(n):
    n &= 0xFFFFFFFF
    return "  Data.b %d,%d,%d,%d\n" % (n & 255, (n >> 8) & 255,
                                       (n >> 16) & 255, (n >> 24) & 255)


def blob(bs):
    out = ""
    for i in range(0, len(bs), 16):
        out += "  Data.b " + ",".join(str(b) for b in bs[i:i + 16]) + "\n"
    return out


def record(q, h, sig, expect, tag, note):
    s = "  ; case %d - %s\n" % (tag, note)
    s += u32(len(q)) + blob(q)
    s += u32(len(h)) + blob(h)
    s += u32(len(sig)) + blob(sig)
    s += u32(expect) + u32(tag)
    return s


# ---------------------------------------------------------- corpus
rng = random.Random(0x9EC0_2026)


def rand_scalar():
    return (rng.getrandbits(256) % (N - 1)) + 1


def flip(bs, idx, bit=1):
    b = bytearray(bs)
    b[idx] ^= bit
    return bytes(b)


def build():
    q6979 = enc_point((RFC6979_UX, RFC6979_UY))
    raw = []
    asn1 = []
    der = []
    tag = 0

    def add_raw(q, h, sig, expect, note):
        nonlocal tag
        tag += 1
        raw.append((q, h, sig, expect, tag, note))

    def add_asn1(q, h, sig, expect, note):
        nonlocal tag
        tag += 1
        asn1.append((q, h, sig, expect, tag, note))

    def add_der(q, h, sig, note):
        nonlocal tag
        tag += 1
        der.append((q, h, sig, 0, tag, note))

    # ---- published RFC 6979 records, raw and DER -------------------
    pub = []
    for msg in ("sample", "test"):
        h = hashlib.sha256(msg.encode()).digest()
        r, s = sign_rfc6979(RFC6979_X, h)
        pub.append((msg, h, r, s))
        add_raw(q6979, h, raw_sig(r, s), 1,
                "PUBLISHED RFC 6979 A.2.5, message %r, P-256/SHA-256" % msg)
        add_asn1(q6979, h, der_sig(r, s), 1,
                 "PUBLISHED RFC 6979 A.2.5, message %r, DER encoded" % msg)

    # ---- oracle-generated valid records (CAVP 'P' shape) -----------
    gen = []
    for i in range(2):
        d = rand_scalar()
        qq = enc_point(pt_mul(d, G))
        msg = bytes(rng.getrandbits(8) for _ in range(rng.randrange(1, 120)))
        h = hashlib.sha256(msg).digest()
        r, s = sign_rfc6979(d, h)
        assert verify(qq, h, r, s)
        gen.append((qq, h, r, s))
        add_raw(qq, h, raw_sig(r, s), 1,
                "oracle-generated valid signature #%d" % (i + 1))
    # one of them also in DER
    qq, h, r, s = gen[0]
    add_asn1(qq, h, der_sig(r, s), 1, "oracle-generated valid signature, DER")

    # ---- the two real certificate signatures, DER ------------------
    for name, hh, qc, sg in REAL_CHAIN:
        add_asn1(bytes.fromhex(qc), bytes.fromhex(hh), bytes.fromhex(sg), 1,
                 "real certificate chain: %s" % name)

    # ---- CAVP 'F' shapes, raw --------------------------------------
    msg, h, r, s = pub[0]
    sig = raw_sig(r, s)
    add_raw(q6979, h, flip(sig, 0, 0x80), 0, "F: R changed (high bit of r)")
    add_raw(q6979, h, flip(sig, 31, 0x01), 0, "F: R changed (low bit of r)")
    add_raw(q6979, h, flip(sig, 32, 0x80), 0, "F: S changed (high bit of s)")
    add_raw(q6979, h, flip(sig, 63, 0x01), 0, "F: S changed (low bit of s)")
    add_raw(q6979, flip(h, 0, 0x80), sig, 0, "F: message changed (hash bit 0)")
    add_raw(q6979, flip(h, 31, 0x01), sig, 0, "F: message changed (hash last bit)")
    # wrong public key, still a valid on-curve point
    qwrong = enc_point(pt_mul(rand_scalar(), G))
    add_raw(qwrong, h, sig, 0, "F: wrong (valid, on-curve) public key")
    # public key with one flipped bit - lands off the curve
    add_raw(flip(q6979, 1, 0x01), h, sig, 0, "F: public key bit flipped (off curve)")
    # r and s at or beyond the group order
    add_raw(q6979, h, raw_sig(0, s), 0, "F: R = 0")
    add_raw(q6979, h, raw_sig(r, 0), 0, "F: S = 0")
    add_raw(q6979, h, N.to_bytes(32, "big") + s.to_bytes(32, "big"), 0,
            "F: R = n (out of range)")
    add_raw(q6979, h, r.to_bytes(32, "big") + N.to_bytes(32, "big"), 0,
            "F: S = n (out of range)")
    add_raw(q6979, h, b"\xff" * 32 + s.to_bytes(32, "big"), 0,
            "F: R = 2^256-1 (out of range)")
    add_raw(q6979, h, r.to_bytes(32, "big") + b"\xff" * 32, 0,
            "F: S = 2^256-1 (out of range)")
    # malformed framing on the raw side
    add_raw(q6979[:64], h, sig, 0, "F: public point 64 bytes, not 65")
    add_raw(bytes([0x06]) + q6979[1:], h, sig, 0, "F: public point prefix not 0x04")
    add_raw(q6979, h, sig[:63], 0, "F: raw signature length odd")
    # off-curve public point built by hand: X kept, Y set to X
    offc = bytes([0x04]) + q6979[1:33] + q6979[1:33]
    add_raw(offc, h, sig, 0, "F: public point off the curve")

    # ---- CAVP 'F' shapes, DER --------------------------------------
    d1 = der_sig(r, s)
    # flip a content bit inside the r INTEGER (offset 4 is the first
    # content byte for a 0x00-padded 33-byte integer)
    add_asn1(q6979, h, flip(d1, 5, 0x40), 0, "F: DER r content changed")
    add_asn1(q6979, h, flip(d1, len(d1) - 1, 0x01), 0, "F: DER s content changed")
    add_asn1(q6979, flip(h, 7, 0x10), d1, 0, "F: DER, message changed")
    add_asn1(qwrong, h, d1, 0, "F: DER, wrong public key")

    # ---- malformed DER shapes, all rejected ------------------------
    body = der_int(r) + der_int(s)
    good = bytes([0x30, len(body)]) + body
    add_der(q6979, h, bytes([0x31]) + good[1:], "bad SEQUENCE tag 0x31")
    add_der(q6979, h, good[:-1], "truncated: last byte dropped")
    add_der(q6979, h, bytes([0x30, 0x81, len(body)]) + body,
            "non-minimal length: long form 0x81 for a short length")
    add_der(q6979, h, bytes([0x30, 0x82, 0x00, len(body)]) + body,
            "over-long length: two-byte long form")
    add_der(q6979, h, bytes([0x30, 0x80]) + body,
            "indefinite length marker 0x80")
    # negative INTEGER: strip the 0x00 pad that makes r positive
    rb = r.to_bytes(32, "big")
    sb = der_int(s)
    negbody = bytes([0x02, 32]) + rb + sb
    if rb[0] & 0x80:
        add_der(q6979, h, bytes([0x30, len(negbody)]) + negbody,
                "negative INTEGER: r high bit set with no 0x00 pad")
    else:
        raise SystemExit("ABORT: anchor r has no high bit; pick another vector")
    # non-minimal leading zero on s (s already starts below 0x80 here)
    sbare = s.to_bytes((s.bit_length() + 7) // 8, "big")
    padded = b"\x00\x00" + sbare
    nmbody = der_int(r) + bytes([0x02, len(padded)]) + padded
    add_der(q6979, h, bytes([0x30, len(nmbody)]) + nmbody,
            "non-minimal INTEGER: two leading zero bytes on s")
    add_der(q6979, h, bytes([0x30, len(body), 0x03]) + body[1:],
            "bad INTEGER tag on r (0x03)")
    badsbody = bytearray(body)
    badsbody[len(der_int(r))] = 0x04
    add_der(q6979, h, bytes([0x30, len(body)]) + bytes(badsbody),
            "bad INTEGER tag on s (0x04)")
    add_der(q6979, h, good + b"\x00", "trailing garbage byte after the SEQUENCE")
    emptybody = bytes([0x02, 0x00]) + der_int(s)
    add_der(q6979, h, bytes([0x30, len(emptybody)]) + emptybody,
            "empty INTEGER: r has zero content bytes")
    runbody = bytes([0x02, 0x7E]) + der_int(r)[2:] + der_int(s)
    add_der(q6979, h, bytes([0x30, len(runbody)]) + runbody,
            "INTEGER length runs past the end of the SEQUENCE")
    add_der(q6979, h, bytes([0x30, len(body) - 1]) + body,
            "SEQUENCE length shorter than its contents")
    add_der(q6979, h, bytes([0x30, 0x03, 0x02, 0x01, 0x01]),
            "too short to be a signature at all")
    add_der(q6979, h, bytes([0x30, 0x06, 0x02, 0x01, 0x01, 0x02, 0x01, 0x01]),
            "well-formed DER but r = s = 1 (not a signature)")

    return raw, asn1, der


HDR = (";{eq}\n"
       "; ecdsaVectors - GENERATED by tools/gen_ecdsa_vectors.py. DO NOT EDIT.\n"
       ";\n"
       "; P-256 ECDSA signature-VERIFY vectors, raw (r||s) and ASN.1 DER.\n"
       "; Every expectation comes from a dependency-free pure-python P-256\n"
       "; ECDSA oracle anchored, before generation, to the published RFC 6979\n"
       "; A.2.5 P-256/SHA-256 signatures, the P-256 generator-multiply known\n"
       "; answer, and two real certificate signatures produced by a different\n"
       "; implementation. Records follow the CAVP SigVer shape and failure\n"
       "; taxonomy; the CAVP .rsp files themselves are not on this machine, so\n"
       "; records not marked PUBLISHED are oracle-derived. No expected value\n"
       "; came from running the code under test.\n"
       ";\n"
       "; Record layout, identical in all three tables:\n"
       ";   u32 qlen | q | u32 hashlen | hash | u32 siglen | sig |\n"
       ";   u32 expected (1 verify / 0 reject) | u32 case tag\n"
       "; Counts and lengths are 4-byte little-endian; integers are\n"
       "; big-endian. Walked by the self-test with Restore/Read.\n"
       ";{eq}\n")


def emit(path, raw, asn1, der):
    s = HDR.format(eq="=" * 70)
    s += "#ECDSA_RAW_COUNT  = %d\n" % len(raw)
    s += "#ECDSA_ASN1_COUNT = %d\n" % len(asn1)
    s += "#ECDSA_DER_COUNT  = %d\n\n" % len(der)
    s += "DataSection\n"
    s += "EcdsaRawCases:\n"
    for q, h, sig, exp, tag, note in raw:
        s += record(q, h, sig, exp, tag, note)
    s += "EcdsaAsn1Cases:\n"
    for q, h, sig, exp, tag, note in asn1:
        s += record(q, h, sig, exp, tag, note)
    s += "EcdsaDerCases:\n"
    for q, h, sig, exp, tag, note in der:
        s += record(q, h, sig, exp, tag, note)
    s += "EndDataSection\n"
    open(path, "w").write(s)


def main():
    anchor()
    raw, asn1, der = build()
    for folder, ext in FAMILIES:
        if not os.path.isdir(os.path.join(REPO, folder)):
            print("  skipped %s: the folder is not in this tree" % folder)
            continue
        p = os.path.join(REPO, folder, "ecdsaVectors." + ext)
        emit(p, raw, asn1, der)
        print("  wrote %s  raw=%d asn1=%d malformed-der=%d"
              % (p, len(raw), len(asn1), len(der)))
    npos = sum(1 for c in raw if c[3] == 1) + sum(1 for c in asn1 if c[3] == 1)
    nneg = len(raw) + len(asn1) + len(der) - npos
    print("ecdsa vectors generated: %d must verify, %d must reject" % (npos, nneg))
    print("oracle anchored to RFC 6979 A.2.5, the P-256 generator KAT, and two"
          " real certificate signatures")


if __name__ == "__main__":
    main()
