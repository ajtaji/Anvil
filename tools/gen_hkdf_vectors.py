#!/usr/bin/env python
# ----------------------------------------------------------------------
# gen_hkdf_vectors.py - emit a house-dialect DataSection include of HKDF
# (RFC 5869) and TLS 1.3 key-schedule (RFC 8446 / RFC 8448) test vectors
# for the M3b hkdf self-test (LANE A of the BearSSL TLS translation).
#
# Two oracles, both independent of the library under test:
#   * RFC 5869: python hashlib/hmac from-scratch HKDF, ANCHORED to the
#     Appendix-A SHA-256 known-answer vectors (A.1/A.2/A.3), whose PRK and
#     OKM are asserted at generation time before any random case is emitted.
#   * RFC 8446 key schedule: a from-scratch python re-implementation of
#     HKDF-Expand-Label and Derive-Secret, ANCHORED to the worked
#     intermediate byte values published in RFC 8448 "Example Handshake
#     Traces for TLS 1.3" (Simple 1-RTT Handshake). Every baked value is a
#     literal from RFC 8448 and is re-derived and asserted here, so a wrong
#     re-implementation is caught before it can vector anything.
#
# Layout - two tables:
#   HKDF 5869 : meta (saltlen, ikmlen, infolen, outlen); data (salt, ikm,
#               info, 32-byte PRK, outlen-byte OKM) per case.
#   HKDF 8448 : meta (op, in1len, in2len, in3len, outlen); data (in1, in2,
#               in3, outlen-byte expected) per case. op: 1=Extract,
#               2=ExpandLabel, 3=DeriveSecret. For ExpandLabel/DeriveSecret
#               in1=secret, in2=label text, in3=context/transcript-hash.
#               For Extract in1=salt, in2=IKM.
#
# Deterministic. Usage: python tools/gen_hkdf_vectors.py [randcount] > out.inc
# ----------------------------------------------------------------------
import sys, random, hmac, hashlib

def hkdf_extract(salt, ikm):
    if salt is None or len(salt) == 0:
        salt = b"\x00" * 32
    return hmac.new(salt, ikm, hashlib.sha256).digest()

def hkdf_expand(prk, info, length):
    out = b""; t = b""; i = 1
    while len(out) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        out += t; i += 1
    return out[:length]

def expand_label(secret, label, context, length):
    full = b"tls13 " + label
    hkdflabel = (length.to_bytes(2, "big") + bytes([len(full)]) + full
                 + bytes([len(context)]) + context)
    return hkdf_expand(secret, hkdflabel, length)

def derive_secret(secret, label, transcript_hash):
    return expand_label(secret, label, transcript_hash, 32)

def H(x):
    return bytes.fromhex(x.replace(" ", "").replace("\n", ""))

# ---------------- RFC 5869 Appendix A SHA-256 anchors ----------------
A1 = dict(ikm=b"\x0b"*22, salt=H("000102030405060708090a0b0c"),
          info=H("f0f1f2f3f4f5f6f7f8f9"), L=42,
          prk=H("077709362c2e32df0ddc3f0dc47bba6390b6c73bb50f9c3122ec844ad7c2b3e5"),
          okm=H("3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"))
A2 = dict(ikm=bytes(range(0x50)), salt=bytes(range(0x60,0xb0)), info=bytes(range(0xb0,0x100)), L=82,
          prk=H("06a6b88c5853361a06104c9ceb35b45cef760014904671014a193f40c15fc244"),
          okm=H("b11e398dc80327a1c8e7f78c596a49344f012eda2d4efad8a050cc4c19afa97c"
                "59045a99cac7827271cb41c65e590e09da3275600c2f09b8367793a9aca3db71"
                "cc30c58179ec3e87c14c01d5c1f3434f1d87"))
A3 = dict(ikm=b"\x0b"*22, salt=b"", info=b"", L=42,
          prk=H("19ef24a32c717b167f33a91d6f648bdf96596776afdb6377ac434c1c293ccb04"),
          okm=H("8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8"))

def build_5869(randcount, seed=0x5869):
    cases = []
    for a in (A1, A2, A3):
        prk = hkdf_extract(a["salt"], a["ikm"])
        okm = hkdf_expand(prk, a["info"], a["L"])
        assert prk == a["prk"], "5869 PRK anchor mismatch"
        assert okm == a["okm"], "5869 OKM anchor mismatch"
        cases.append((a["salt"], a["ikm"], a["info"], a["L"], prk, okm))
    rng = random.Random(seed)
    for _ in range(randcount):
        saltlen = rng.choice([0, rng.randint(1, 48)])
        ikmlen = rng.randint(1, 64)
        infolen = rng.randint(0, 40)
        outlen = rng.randint(1, 130)      # crosses several 32-byte blocks
        salt = bytes(rng.randint(0,255) for _ in range(saltlen))
        ikm = bytes(rng.randint(0,255) for _ in range(ikmlen))
        info = bytes(rng.randint(0,255) for _ in range(infolen))
        prk = hkdf_extract(salt, ikm)
        okm = hkdf_expand(prk, info, outlen)
        cases.append((salt, ikm, info, outlen, prk, okm))
    return cases

# ---------------- RFC 8448 Simple 1-RTT Handshake anchors ----------------
ZEROS   = b"\x00"*32
EMPTYH  = hashlib.sha256(b"").digest()
ECDHE   = H("8bd4054fb55b9d63fdfbacf9f04b9f0d35e6d63f537563efd46272900f89492d")
TH_SH   = H("860c06edc07858ee8e78f0e7428c58edd6b43f2ca3e6e95f02ed063cf0e1cad8")
TH_SF   = H("9608102a0f1ccc6db6250b7b7e417b1a000eaada3daae4777a7686c9ff83df13")

RFC8448 = {
 "early":    H("33ad0a1c607ec03b09e6cd9893680ce210adf300aa1f2660e1b22e10f170f92a"),
 "derived1": H("6f2615a108c702c5678f54fc9dbab69716c076189c48250cebeac3576c3611ba"),
 "hs":       H("1dc826e93606aa6fdc0aadc12f741b01046aa6b99f691ed221a9f0ca043fbeac"),
 "c_hs":     H("b3eddb126e067f35a780b3abf45e2d8f3b1a950738f52e9600746a0e27a55a21"),
 "s_hs":     H("b67b7d690cc16c4e75e54213cb2d37b4e9c912bcded9105d42befd59d391ad38"),
 "s_key":    H("3fce516009c21727d0f2e4e86ee403bc"),
 "s_iv":     H("5d313eb2671276ee13000b30"),
 "derived2": H("43de77e0c77713859a944db9db2590b53190a65b3ee2e4f12dd7a0bb7ce254b4"),
 "master":   H("18df06843d13a08bf2a449844c5f8a478001bc4d4c627984d5a41da8d0402919"),
 "c_ap":     H("9e40646ce79a7f9dc05af8889bce6552875afa0b06df0087f792ebb7c17504a5"),
 "s_ap":     H("a11af9f05531f856ad47116b45a950328204b4f44bfb6b3a4b4f1f3fcb631643"),
}

OP_EXTRACT, OP_EXPANDLABEL, OP_DERIVE = 1, 2, 3

def build_8448():
    early    = hkdf_extract(b"", ZEROS)
    derived1 = derive_secret(early, b"derived", EMPTYH)
    hs       = hkdf_extract(derived1, ECDHE)
    c_hs     = derive_secret(hs, b"c hs traffic", TH_SH)
    s_hs     = derive_secret(hs, b"s hs traffic", TH_SH)
    s_key    = expand_label(s_hs, b"key", b"", 16)
    s_iv     = expand_label(s_hs, b"iv", b"", 12)
    derived2 = derive_secret(hs, b"derived", EMPTYH)
    master   = hkdf_extract(derived2, ZEROS)
    c_ap     = derive_secret(master, b"c ap traffic", TH_SF)
    s_ap     = derive_secret(master, b"s ap traffic", TH_SF)
    got = dict(early=early, derived1=derived1, hs=hs, c_hs=c_hs, s_hs=s_hs,
               s_key=s_key, s_iv=s_iv, derived2=derived2, master=master,
               c_ap=c_ap, s_ap=s_ap)
    for k, v in RFC8448.items():
        assert got[k] == v, "RFC8448 anchor mismatch at %s: %s" % (k, got[k].hex())
    # (op, in1, in2, in3, outlen, expected)
    return [
        (OP_EXTRACT,     b"",       ZEROS,          b"",      32, early),
        (OP_DERIVE,      early,     b"derived",     EMPTYH,   32, derived1),
        (OP_EXTRACT,     derived1,  ECDHE,          b"",      32, hs),
        (OP_DERIVE,      hs,        b"c hs traffic",TH_SH,    32, c_hs),
        (OP_DERIVE,      hs,        b"s hs traffic",TH_SH,    32, s_hs),
        (OP_EXPANDLABEL, s_hs,      b"key",         b"",      16, s_key),
        (OP_EXPANDLABEL, s_hs,      b"iv",          b"",      12, s_iv),
        (OP_DERIVE,      hs,        b"derived",     EMPTYH,   32, derived2),
        (OP_EXTRACT,     derived2,  ZEROS,          b"",      32, master),
        (OP_DERIVE,      master,    b"c ap traffic",TH_SF,    32, c_ap),
        (OP_DERIVE,      master,    b"s ap traffic",TH_SF,    32, s_ap),
    ]

def rows(blob):
    out = []
    for i in range(0, len(blob), 16):
        out.append("  Data.b " + ", ".join(str(b) for b in blob[i:i+16]))
    return out

def emit(randcount=20, seed=0x5869):
    c5869 = build_5869(randcount, seed)
    c8448 = build_8448()
    o = []
    o.append("; ======================================================================")
    o.append("; HKDF (RFC 5869) + TLS 1.3 key-schedule (RFC 8446/8448) test vectors -")
    o.append(";   AUTO-GENERATED by tools/gen_hkdf_vectors.py, do not edit by hand.")
    o.append(";   RFC 5869 cases 0-2 are the Appendix-A SHA-256 known answers; the")
    o.append(";   rest are random cases from an independent python HKDF.")
    o.append(";   RFC 8448 cases are the published Simple 1-RTT key-schedule")
    o.append(";   intermediates, matched byte-for-byte.")
    o.append("; ======================================================================")
    o.append("#HKDF5869_COUNT = %d" % len(c5869))
    o.append("#HKDF8448_COUNT = %d" % len(c8448))
    o.append("#HKDF_OP_EXTRACT = %d" % OP_EXTRACT)
    o.append("#HKDF_OP_EXPANDLABEL = %d" % OP_EXPANDLABEL)
    o.append("#HKDF_OP_DERIVE = %d" % OP_DERIVE)
    o.append("")
    o.append("DataSection")
    o.append("  Hkdf5869Meta:")
    for salt, ikm, info, outlen, prk, okm in c5869:
        o.append("  Data.l %d, %d, %d, %d" % (len(salt), len(ikm), len(info), outlen))
    o.append("  Hkdf5869Data:")
    for idx, (salt, ikm, info, outlen, prk, okm) in enumerate(c5869):
        o.append("  ; --- 5869 case %d: saltlen %d ikmlen %d infolen %d outlen %d ---"
                 % (idx, len(salt), len(ikm), len(info), outlen))
        blob = salt + ikm + info + prk + okm
        if blob:
            o += rows(blob)
    o.append("  Hkdf8448Meta:")
    for op, i1, i2, i3, outlen, exp in c8448:
        o.append("  Data.l %d, %d, %d, %d, %d" % (op, len(i1), len(i2), len(i3), outlen))
    o.append("  Hkdf8448Data:")
    names = ["early","derived1","handshake","c hs traffic","s hs traffic",
             "server key","server iv","derived2","master","c ap traffic","s ap traffic"]
    for idx, (op, i1, i2, i3, outlen, exp) in enumerate(c8448):
        o.append("  ; --- 8448 case %d (%s): op %d in1 %d in2 %d in3 %d out %d ---"
                 % (idx, names[idx], op, len(i1), len(i2), len(i3), outlen))
        blob = i1 + i2 + i3 + exp
        if blob:
            o += rows(blob)
    o.append("EndDataSection")
    o.append("")
    return "\n".join(o)

if __name__ == "__main__":
    randcount = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    sys.stdout.write(emit(randcount))
