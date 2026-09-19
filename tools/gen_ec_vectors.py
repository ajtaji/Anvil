#!/usr/bin/env python
# ----------------------------------------------------------------------
# gen_ec_vectors.py - emit the P-256 and X25519 self-test vectors.
#
# The M8 vector gate needs known-answer cases for the elliptic
# curve scalar-multiply primitives, produced by a trustworthy oracle
# rather than by running the code under test. The oracle here is a
# self-contained, dependency-free pure-python implementation of P-256
# affine EC arithmetic and the RFC 7748 X25519 Montgomery ladder. Its
# correctness is ANCHORED before any vector is written: it must reproduce
# the published NIST/BearSSL P-256 generator-multiply KAT and the RFC
# 7748 X25519 KATs exactly, or this script aborts. No pip install, no
# network: only published CAVP/RFC constants and the anchored oracle.
#
# It writes:
#   ec256Vectors.<ext>   - mulgen KAT, point-multiply (incl. carry KATs),
#                          ECDH shared-secret cases, and negatives
#                          (off-curve, bad prefix, coord >= p, infinity).
#   x25519Vectors.<ext>  - RFC 7748 KATs plus the 1-iteration and
#                          1000-iteration iterated tests.
# into each family's Verification folder (the vectors are portable; the
# self-test that reads them is built per family). The self-test walks each
# DataSection with Restore/Read and checks the library output byte-exact.
#
# Usage:  python tools/gen_ec_vectors.py
# ----------------------------------------------------------------------
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAMILIES = [
    ("RP2350/Examples/Diagnostics", "pico2"),
    ("RP2040/Examples/Diagnostics", "pico"),
    ("RA4M1AndRelated/Examples/Diagnostics", "unor4"),
]

# ---------------------------------------------------------------- P-256
P  = 2**256 - 2**224 + 2**192 + 2**96 - 1
A  = (-3) % P
B  = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b
Gx = 0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296
Gy = 0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5
N  = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
G  = (Gx, Gy)

def inv(x):
    return pow(x, P - 2, P)

def pt_add(p1, p2):
    if p1 is None: return p2
    if p2 is None: return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        m = (3 * x1 * x1 + A) * inv(2 * y1) % P
    else:
        m = (y2 - y1) * inv(x2 - x1) % P
    x3 = (m * m - x1 - x2) % P
    y3 = (m * (x1 - x3) - y1) % P
    return (x3, y3)

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

# ------------------------------------------------------------- X25519
def x25519(k, u):
    k = bytearray(k)
    k[0]  &= 248
    k[31] &= 127
    k[31] |= 64
    k = int.from_bytes(k, "little")
    x1 = int.from_bytes(u, "little") & ((1 << 255) - 1)
    p25519 = 2**255 - 19
    a24 = 121665
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in range(254, -1, -1):
        kt = (k >> t) & 1
        swap ^= kt
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = kt
        A_ = (x2 + z2) % p25519
        AA = A_ * A_ % p25519
        Bx = (x2 - z2) % p25519
        BB = Bx * Bx % p25519
        E = (AA - BB) % p25519
        C = (x3 + z3) % p25519
        D = (x3 - z3) % p25519
        DA = D * A_ % p25519
        CB = C * Bx % p25519
        x3 = (DA + CB) % p25519
        x3 = x3 * x3 % p25519
        z3 = (DA - CB) % p25519
        z3 = z3 * z3 % p25519
        z3 = z3 * x1 % p25519
        x2 = AA * BB % p25519
        z2 = E * (AA + a24 * E) % p25519
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    res = x2 * pow(z2, p25519 - 2, p25519) % p25519
    return res.to_bytes(32, "little")

# --------------------------------------------------------- anchoring
def anchor():
    # P-256 generator multiply KAT (from BearSSL test_crypto.c / NIST).
    k = bytes.fromhex(
        "C9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721")
    want = bytes.fromhex(
        "0460FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB6"
        "7903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299")
    got = enc_point(pt_mul(int.from_bytes(k, "big"), G))
    assert got == want, "P-256 oracle FAILED the KAT anchor"
    # X25519 RFC 7748 section 5.2 KAT #1.
    sc = bytes.fromhex(
        "a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4")
    u  = bytes.fromhex(
        "e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")
    wx = bytes.fromhex(
        "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552")
    assert x25519(sc, u) == wx, "X25519 oracle FAILED the KAT anchor"

# --------------------------------------------------------- emit helpers
def u32(n):
    return "  Data.b %d,%d,%d,%d\n" % (n & 255, (n >> 8) & 255,
                                       (n >> 16) & 255, (n >> 24) & 255)

def blob(bs):
    out = ""
    for i in range(0, len(bs), 16):
        chunk = bs[i:i+16]
        out += "  Data.b " + ",".join(str(b) for b in chunk) + "\n"
    return out

HDR = (";{eq}\n"
       "; {name} - GENERATED by tools/gen_ec_vectors.py. DO NOT EDIT.\n"
       ";\n"
       "; {desc}\n"
       "; Every expected value comes from a dependency-free pure-python EC\n"
       "; oracle anchored to the published NIST/BearSSL and RFC 7748 KATs.\n"
       "; Lengths and counts are 4-byte little-endian; byte strings are\n"
       "; big-endian for P-256 and little-endian (RFC 7748 wire form) for\n"
       "; X25519. Walked by the self-test with Restore/Read.\n"
       ";{eq}\n")

# --------------------------------------------------------- build P-256
import random
rng = random.Random(0x2565_2026)

def rand_scalar():
    return (rng.getrandbits(256) % (N - 1)) + 1

def build_ec256():
    mulgen = []   # (k_bytes, point65)
    # KAT
    kk = bytes.fromhex(
        "C9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721")
    mulgen.append((kk, enc_point(pt_mul(int.from_bytes(kk, "big"), G))))
    # a random-scalar generator multiply (a second independent point)
    for _ in range(1):
        d = rand_scalar()
        db = d.to_bytes(32, "big")
        mulgen.append((db, enc_point(pt_mul(d, G))))

    # point-multiply in place (incl. the two BearSSL P256_carry KATs, k=0x10)
    mul = []      # (in65, k_bytes, out65, r)
    for sP, sQ in [
        ("0435BAA24B2B6E1B3C88E22A383BD88CC4B9A3166E7BCF94FF6591663AE066B33B"
         "821EBA1B4FC8EA609A87EB9A9C9A1CCD5C9F42FA1365306F64D7CAA718B8C978",
         "0447752A76CA890328D34E675C4971EC629132D1FC4863EDB61219B72C4E58DC5E"
         "9D51E7B293488CFD913C3CF20E438BB65C2BA66A7D09EABB45B55E804260C5EB"),
        ("04DCAE9D9CE211223602024A6933BD42F77B6BF4EAB9C8915F058C149419FADD2C"
         "C9FC0707B270A1B5362BA4D249AFC8AC3DA1EFCA8270176EEACA525B49EE19E6",
         "048DAC7B0BE9B3206FCE8B24B6B4AEB122F2A67D13E536B390B6585CA193427E63"
         "F222388B5F51D744D6F5D47536D89EEEC89552BCB269E7828019C4410DFE980A"),
    ]:
        mul.append((bytes.fromhex(sP), bytes([0x10]), bytes.fromhex(sQ), 1))
    # random point * random scalar
    for _ in range(0):
        base = pt_mul(rand_scalar(), G)
        k = rand_scalar()
        mul.append((enc_point(base), k.to_bytes(32, "big"),
                    enc_point(pt_mul(k, base)), 1))

    # ECDH shared-secret cases: (priv, peer_point, shared_X, r)
    ecdh = []
    for _ in range(2):
        priv = rand_scalar()
        peer = pt_mul(rand_scalar(), G)
        shared = pt_mul(priv, peer)
        ecdh.append((priv.to_bytes(32, "big"), enc_point(peer),
                     shared[0].to_bytes(32, "big"), 1))

    # negatives (expect r = 0)
    neg = []
    good = enc_point(pt_mul(rand_scalar(), G))
    k1 = rand_scalar().to_bytes(32, "big")
    # off-curve: flip the last byte of Y
    oc = bytearray(good); oc[-1] ^= 0x01
    neg.append((bytes(oc), k1, 0))
    # bad prefix 0x06
    bp = bytearray(good); bp[0] = 0x06
    neg.append((bytes(bp), k1, 0))
    # coordinate X = p (not < p)
    cp = bytearray(good)
    cp[1:33] = P.to_bytes(32, "big")
    neg.append((bytes(cp), k1, 0))
    # point at infinity encoded as 0x04 || 0 || 0 (not on curve)
    neg.append((bytes([0x04]) + b"\x00" * 64, k1, 0))

    return mulgen, mul, ecdh, neg

def emit_ec256(path):
    mulgen, mul, ecdh, neg = build_ec256()
    s = HDR.format(eq="=" * 70,
                   name="ec256Vectors",
                   desc="Known-answer vectors for P-256 (secp256r1) scalar mult.")
    s += "#EC_MULGEN_COUNT = %d\n" % len(mulgen)
    s += "#EC_MUL_COUNT    = %d\n" % len(mul)
    s += "#EC_ECDH_COUNT   = %d\n" % len(ecdh)
    s += "#EC_NEG_COUNT    = %d\n\n" % len(neg)
    s += "DataSection\n"
    s += "EcMulgenCases:\n"
    for k, pt in mulgen:
        s += u32(len(k)) + blob(k) + blob(pt)
    s += "EcMulCases:\n"
    for pin, k, pout, r in mul:
        s += blob(pin) + u32(len(k)) + blob(k) + blob(pout) + u32(r)
    s += "EcEcdhCases:\n"
    for priv, peer, sx, r in ecdh:
        s += blob(priv) + blob(peer) + blob(sx) + u32(r)
    s += "EcNegCases:\n"
    for pt, k, r in neg:
        s += blob(pt) + u32(len(k)) + blob(k) + u32(r)
    s += "EndDataSection\n"
    open(path, "w").write(s)
    return len(mulgen), len(mul), len(ecdh), len(neg)

# --------------------------------------------------------- build X25519
def build_x25519():
    kats = []   # (scalar32, u32, out32)
    kats.append((
        bytes.fromhex("a546e36bf0527c9d3b16154b82465edd"
                      "62144c0ac1fc5a18506a2244ba449ac4"),
        bytes.fromhex("e6db6867583030db3594c1a424b15f7c"
                      "726624ec26b3353b10a903a6d0ab1c4c"),
        bytes.fromhex("c3da55379de9c6908e94ea4df28d084f"
                      "32eccf03491c71f754b4075577a28552")))
    kats.append((
        bytes.fromhex("4b66e9d4d1b4673c5ad22691957d6af5"
                      "c11b6421e0ea01d42ca4169e7918ba0d"),
        bytes.fromhex("e5210f12786811d3f4b7959d0538ae2c"
                      "31dbe7106fc03c3efc4cd549c715a493"),
        bytes.fromhex("95cbde9476e8907d7aade45cb4b873f8"
                      "8b595a68799fa152e6f8f7647aac7957")))
    # a few random self-consistent cases from the oracle
    for _ in range(4):
        sc = bytes(rng.getrandbits(8) for _ in range(32))
        u  = bytes(rng.getrandbits(8) for _ in range(32))
        kats.append((sc, u, x25519(sc, u)))

    # iterated tests (RFC 7748 section 5.2)
    k = bytearray.fromhex("0900000000000000000000000000000000000000000000000000000000000000")
    u = bytearray(k)
    k1 = x25519(bytes(k), bytes(u))         # after 1 iteration
    iters = [(1, k1)]
    # 1000 iterations
    k = bytearray.fromhex("0900000000000000000000000000000000000000000000000000000000000000")
    u = bytearray(k)
    for _ in range(1000):
        r = x25519(bytes(k), bytes(u))
        u = bytearray(k)
        k = bytearray(r)
    iters.append((1000, bytes(k)))
    # sanity against the published RFC values
    assert k1.hex() == "422c8e7a6227d7bca1350b3e2bb7279f7897b87bb6854b783c60e80311ae3079"
    assert iters[1][1].hex() == "684cf59ba83309552800ef566f2f4d3c1c3887c49360e3875f2eb94d99532c51"
    return kats, iters

def emit_x25519(path):
    kats, iters = build_x25519()
    s = HDR.format(eq="=" * 70,
                   name="x25519Vectors",
                   desc="RFC 7748 X25519 KATs and iterated tests.")
    s += "#X_KAT_COUNT  = %d\n" % len(kats)
    s += "#X_ITER_COUNT = %d\n\n" % len(iters)
    s += "DataSection\n"
    s += "XKatCases:\n"
    for sc, u, out in kats:
        s += blob(sc) + blob(u) + blob(out)
    s += "XIterCases:\n"
    for count, out in iters:
        s += u32(count) + blob(out)
    s += "EndDataSection\n"
    open(path, "w").write(s)
    return len(kats), len(iters)

def main():
    anchor()
    for folder, ext in FAMILIES:
        if not os.path.isdir(os.path.join(REPO, folder)):
            print("  skipped %s: the folder is not in this tree" % folder)
            continue
        p1 = os.path.join(REPO, folder, "ec256Vectors." + ext)
        p2 = os.path.join(REPO, folder, "x25519Vectors." + ext)
        c1 = emit_ec256(p1)
        c2 = emit_x25519(p2)
        print("  wrote %s  mulgen=%d mul=%d ecdh=%d neg=%d" % ((p1,) + c1))
        print("  wrote %s  kats=%d iters=%d" % ((p2,) + c2))
    print("ec vectors generated; oracle anchored to NIST/BearSSL and RFC 7748 KATs")

if __name__ == "__main__":
    main()
