#!/usr/bin/env python3
# ----------------------------------------------------------------------
# gen_rsa_vectors.py - emit the RSA signature-verify self-test vectors.
#
# The M10 vector gate needs known-answer cases for RSA signature
# verification - both PKCS#1 v1.5 and PSS - at 2048/3072/4096-bit moduli,
# plus corrupted-padding / wrong-salt / tampered-signature negatives, and
# a real-certificate smoke.
#
# The oracle is PURE PYTHON, independent of the code under test: RSA keys
# are generated from a fixed seed (Miller-Rabin over python's big ints),
# and the signatures are produced by independent EMSA-PKCS1-v1_5 and
# EMSA-PSS encoders written straight from RFC 8017, then raised to the
# private exponent with pow(). No third-party package is imported (no pip),
# so the vectors are reproducible on any box with python 3. NIST CAVP
# SigVer response files are not present on this machine and cannot be
# downloaded here; this independent oracle gives the same coverage - valid
# signatures must verify, mangled ones must not - against a second
# implementation of the same specs.
#
# The real-certificate smoke is baked from BearSSL's own test corpus: the
# self-signed RSA-2048 root CA certificate (test/x509/root.crt, signed
# sha256WithRSAEncryption), whose TBS is verified against the very key it
# carries. That is a genuine certificate signature, not a synthetic one.
# The certificate is kept, byte for byte, as
# RaspberryPi4/Reference/bearssl_test_x509_root.crt (BearSSL is MIT; its
# notice ships as licenses/BearSSL-LICENSE.txt).
#
# It writes an identical rsaVectors.<ext> into each family's Verification
# folder; the self-test that reads them is built per family.
#
# Usage:  python tools/gen_rsa_vectors.py
# ----------------------------------------------------------------------
import os, hashlib, random

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERT = os.path.join(REPO, "RaspberryPi4", "Reference",
                    "bearssl_test_x509_root.crt")

OUT = [
    ("RP2350/Examples/Diagnostics/rsaVectors.pico2",  "RP2350"),
    ("RP2040/Examples/Diagnostics/rsaVectors.pico",   "RP2040"),
    ("RA4M1AndRelated/Examples/Diagnostics/rsaVectors.unor4", "Uno R4"),
]

rng = random.Random(0x1517_2026)      # fixed seed: deterministic vectors

# record kinds in the emitted byte stream
K_PKCS1 = 0
K_PSS   = 1
K_SEAM  = 2       # PKCS#1 v1.5 through the certificate-seam RECOVERY call
K_END   = 255

# SHA-256 DigestInfo prefix (RFC 8017), and the length-prefixed OID the
# library's RsaOidSha256() builds.
SHA256_DI_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
HLEN = 32

# ---- pure-python RSA -------------------------------------------------

def is_probable_prime(n, rounds=24):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = rng.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        ok = False
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                ok = True
                break
        if not ok:
            return False
    return True


def gen_prime(bits):
    while True:
        c = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(c):
            return c


def gen_key(bits, e=0x10001):
    while True:
        p = gen_prime(bits // 2)
        q = gen_prime(bits // 2)
        if p == q:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        phi = (p - 1) * (q - 1)
        if phi % e == 0:
            continue
        d = pow(e, -1, phi)
        return n, e, d


def i2osp(x, length):
    return x.to_bytes(length, "big")


def rsasp(m_int, d, n, k):
    return i2osp(pow(m_int, d, n), k)


# ---- EMSA-PKCS1-v1_5 (RFC 8017 9.2) ----------------------------------

def emsa_pkcs1(mhash, k):
    di = SHA256_DI_PREFIX + mhash
    ps = b"\xff" * (k - len(di) - 3)
    return b"\x00\x01" + ps + b"\x00" + di


# ---- EMSA-PSS-ENCODE (RFC 8017 9.1.1) --------------------------------

def mgf1(seed, length):
    out = b""
    c = 0
    while len(out) < length:
        out += hashlib.sha256(seed + i2osp(c, 4)).digest()
        c += 1
    return out[:length]


def emsa_pss(mhash, salt, embits):
    emlen = (embits + 7) // 8
    slen = len(salt)
    mp = b"\x00" * 8 + mhash + salt
    h = hashlib.sha256(mp).digest()
    ps = b"\x00" * (emlen - slen - HLEN - 2)
    db = ps + b"\x01" + salt
    dbmask = mgf1(h, emlen - HLEN - 1)
    maskeddb = bytes(a ^ b for a, b in zip(db, dbmask))
    # clear the leftmost 8*emlen - embits bits of maskeddb
    clear = 8 * emlen - embits
    maskeddb = bytes([maskeddb[0] & (0xFF >> clear)]) + maskeddb[1:]
    return maskeddb + h + b"\xBC"


# ---- record assembly -------------------------------------------------

RECORDS = []   # each: (kind, expect, n, e, sig, msg, saltlen)


def add(kind, expect, n, e, sig, msg, saltlen):
    RECORDS.append((kind, expect, n, e, sig, msg, saltlen))


def build_for_key(bits, full):
    # Generated keys use e=3 (public exponent), which exercises exactly the
    # same public-operation path - decode, Montgomery modmul ladder, encode
    # - as e=65537 but with far fewer ladder iterations, so the 3072/4096
    # emulator runs stay tractable. The real-certificate smoke below keeps
    # e=65537, so the common-exponent path is proven on genuine data too.
    # "full" fans a rich negative set out at 2048 (the rejection logic is
    # modulus-size independent); 3072/4096 carry a valid+invalid pair per
    # scheme, which is what proves the big-integer arithmetic at those sizes.
    n, e, d = gen_key(bits, 3)
    k = bits // 8
    ebytes = i2osp(e, (e.bit_length() + 7) // 8)
    nbytes = i2osp(n, k)
    embits = bits - 1

    # --- PKCS#1 v1.5 valid ------------------------------------------
    pk_msgs = [b"", b"a", b"puremetal rsa pkcs1 vector"] if full else [b"pkcs1-%d" % bits]
    for tag in pk_msgs:
        h = hashlib.sha256(tag).digest()
        sig = rsasp(int.from_bytes(emsa_pkcs1(h, k), "big"), d, n, k)
        add(K_PKCS1, 1, nbytes, ebytes, sig, tag, 0)

    # negative: valid signature, one flipped signature byte
    tag = b"tamper-pkcs1-%d" % bits
    h = hashlib.sha256(tag).digest()
    sig = bytearray(rsasp(int.from_bytes(emsa_pkcs1(h, k), "big"), d, n, k))
    sig[k // 2] ^= 0x01
    add(K_PKCS1, 0, nbytes, ebytes, bytes(sig), tag, 0)

    if full:
        # negative: sign a corrupted EM (a padding FF turned to FE)
        tag = b"badpad-pkcs1"
        h = hashlib.sha256(tag).digest()
        em = bytearray(emsa_pkcs1(h, k))
        em[5] = 0xFE                # inside the 0xFF run
        sig = rsasp(int.from_bytes(bytes(em), "big"), d, n, k)
        add(K_PKCS1, 0, nbytes, ebytes, sig, tag, 0)

        # negative: signature over a different message than the one stored
        signed = hashlib.sha256(b"message-A").digest()
        sig = rsasp(int.from_bytes(emsa_pkcs1(signed, k), "big"), d, n, k)
        add(K_PKCS1, 0, nbytes, ebytes, sig, b"message-B", 0)

    # --- RSA-PSS valid ----------------------------------------------
    # salt length = hash length (TLS 1.3 rsa_pss_rsae_sha256)
    ps_msgs = [b"", b"puremetal rsa pss vector"] if full else [b"pss-%d" % bits]
    for tag in ps_msgs:
        h = hashlib.sha256(tag).digest()
        salt = bytes(rng.getrandbits(8) for _ in range(HLEN))
        sig = rsasp(int.from_bytes(emsa_pss(h, salt, embits), "big"), d, n, k)
        add(K_PSS, 1, nbytes, ebytes, sig, tag, HLEN)

    if full:
        # valid, salt length 0
        tag = b"pss-salt0"
        h = hashlib.sha256(tag).digest()
        sig = rsasp(int.from_bytes(emsa_pss(h, b"", embits), "big"), d, n, k)
        add(K_PSS, 1, nbytes, ebytes, sig, tag, 0)

    # negative: valid PSS, one flipped signature byte
    tag = b"tamper-pss-%d" % bits
    h = hashlib.sha256(tag).digest()
    salt = bytes(rng.getrandbits(8) for _ in range(HLEN))
    sig = bytearray(rsasp(int.from_bytes(emsa_pss(h, salt, embits), "big"), d, n, k))
    sig[k // 3] ^= 0x02
    add(K_PSS, 0, nbytes, ebytes, bytes(sig), tag, HLEN)

    if full:
        # negative: signed with salt 32 but verified expecting salt 0
        tag = b"pss-wrongsalt"
        h = hashlib.sha256(tag).digest()
        salt = bytes(rng.getrandbits(8) for _ in range(HLEN))
        sig = rsasp(int.from_bytes(emsa_pss(h, salt, embits), "big"), d, n, k)
        add(K_PSS, 0, nbytes, ebytes, sig, tag, 0)

        # negative: signature over a different message than stored
        signed = hashlib.sha256(b"pss-message-A").digest()
        salt = bytes(rng.getrandbits(8) for _ in range(HLEN))
        sig = rsasp(int.from_bytes(emsa_pss(signed, salt, embits), "big"), d, n, k)
        add(K_PSS, 0, nbytes, ebytes, sig, b"pss-message-B", HLEN)

    return n.bit_length()


# ---- real-certificate smoke -----------------------------------------

def der_tlv(b, o):
    tag = b[o]
    o1 = o + 1
    length = b[o1]
    o1 += 1
    if length & 0x80:
        nb = length & 0x7F
        length = int.from_bytes(b[o1:o1 + nb], "big")
        o1 += nb
    return tag, o1, o1 + length          # tag, content_start, content_end


def build_smoke():
    # root-rsa2048 public key, from BearSSL test/x509/alltests.txt [key]
    n = int(
        "B6D934D450FDB3AF7A73F1CE38BF5D6F45E1FD4EB198C6608326D217D1C5B79A"
        "A3C1DE6339979CF05E5CC81C17B988196DF0B62E3050A1546E93C0DBCF30CB9F"
        "1E2779F1C3995235AA3DB6DFB0AD7CCB49CDC0EDE766102AE9CE281F2150FA77"
        "4C2DDAEF3C58EB4EBFCEE9FB1ADAA383A3CDA3CA9380DCDAF317CC7AAB33809C"
        "B2D47F463FC53CDC6194B727296E2ABC5B0936D4C63B0DEBBECEDB1D1CBC106A"
        "7171B3F2CA289A77F28AEC42EFB14A8EE2F21A322ACDC0A6462C9AC28537917F"
        "46A19381A17466DFBAB339209193FA1DA1A885E7E4F907F610F6A82701B67F12"
        "C340C3C9E2B0AB49183A64B659B795B59636DF2269AA726A544E2729A30E9715", 16)
    e = 0x10001
    k = 256
    if not os.path.isfile(CERT):
        raise SystemExit(
            "The real-certificate smoke could not be built because its "
            "certificate is missing: %s. Restore BearSSL's test/x509/root.crt "
            "there under that name; do not substitute another certificate."
            % CERT)
    data = open(CERT, "rb").read()
    _, c0, c1 = der_tlv(data, 0)         # outer SEQUENCE content
    # child 1: tbsCertificate (a SEQUENCE); we need its full DER element
    tbs_tag = data[c0]
    _, t0, t1 = der_tlv(data, c0)
    tbs_der = data[c0:t1]
    # child 2: signatureAlgorithm
    _, s0, s1 = der_tlv(data, t1)
    # child 3: signatureValue (BIT STRING)
    _, v0, v1 = der_tlv(data, s1)
    sig = data[v0 + 1:v1]                # drop the leading unused-bits byte
    assert len(sig) == k, "smoke cert signature is not 256 bytes"
    # self-consistency check in the oracle before we bake it
    em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
    assert em[-32:] == hashlib.sha256(tbs_der).digest(), "smoke self-check failed"
    add(K_PKCS1, 1, i2osp(n, k), i2osp(e, 3), sig, tbs_der, 0)
    # The same genuine certificate signature, driven through the CERTIFICATE
    # SEAM entry point instead: recover the hash out to the caller, which
    # compares it itself. That is the exact call shape the chain-validation
    # engine makes, so the seam is proven on real data and on the common
    # e=65537 exponent - not only through the compare-inside convenience API.
    add(K_SEAM, 1, i2osp(n, k), i2osp(e, 3), sig, tbs_der, 0)
    # ...and the seam must REJECT: one flipped signature byte, same key.
    bad = bytearray(sig)
    bad[k // 2] ^= 0x01
    add(K_SEAM, 0, i2osp(n, k), i2osp(e, 3), bytes(bad), tbs_der, 0)


# ---- emit ------------------------------------------------------------

def data_bytes(bs):
    lines = []
    for i in range(0, len(bs), 16):
        chunk = bs[i:i + 16]
        lines.append("  Data.b " + ",".join(str(x) for x in chunk))
    if not lines:
        lines.append("  Data.b 0")
    return "\n".join(lines)


def u16(v):
    return bytes([v & 255, (v >> 8) & 255])


def record_stream():
    out = bytearray()
    for kind, expect, n, e, sig, msg, saltlen in RECORDS:
        out += bytes([kind, expect])
        out += u16(len(n)) + n
        out += u16(len(e)) + e
        out += u16(len(sig)) + sig
        out += u16(len(msg)) + msg
        out += u16(saltlen)
    out += bytes([K_END])
    return bytes(out)


def emit(path):
    stream = record_stream()
    L = []
    W = L.append
    W("; ======================================================================")
    W("; rsaVectors - GENERATED by tools/gen_rsa_vectors.py. DO NOT EDIT.")
    W(";")
    W("; RSA signature-verify known-answer vectors (PKCS#1 v1.5 and PSS) at")
    W("; 2048/3072/4096-bit, produced by an independent python RSA oracle,")
    W("; plus a real self-signed RSA-2048 certificate smoke. Walked by")
    W("; rsaSelfTest with Restore/Read. One byte stream, all Data.b, read")
    W("; longhand so nothing needs a 4-byte-aligned Data.l run.")
    W(";")
    W("; Record: kind.b expect.b nLen.u16 n... eLen.u16 e... sigLen.u16 sig...")
    W(";         msgLen.u16 msg... saltLen.u16   (u16 little-endian, two bytes)")
    W("; kind 0=PKCS#1 v1.5, 1=PSS, 2=PKCS#1 v1.5 through the certificate-seam")
    W(";      recovery call, 255=end. expect 1=must verify, 0=must fail.")
    W("; ======================================================================")
    W("#RSA_VEC_COUNT = %d" % len(RECORDS))
    W("")
    W("DataSection")
    W("  RsaVecStream:")
    W(data_bytes(stream))
    W("EndDataSection")
    text = "\n".join(L) + "\n"
    full = os.path.join(REPO, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", newline="\n").write(text)


def main():
    counts = {}
    counts[2048] = build_for_key(2048, full=True)
    counts[3072] = build_for_key(3072, full=False)
    counts[4096] = build_for_key(4096, full=False)
    build_smoke()
    for path, fam in OUT:
        if not os.path.isdir(os.path.join(REPO, path.split("/")[0])):
            print("  skipped %s: the %s folder is not in this tree" % (path, fam))
            continue
        emit(path)
    npos = sum(1 for r in RECORDS if r[1] == 1)
    nneg = sum(1 for r in RECORDS if r[1] == 0)
    npk = sum(1 for r in RECORDS if r[0] == K_PKCS1)
    nps = sum(1 for r in RECORDS if r[0] == K_PSS)
    nsm = sum(1 for r in RECORDS if r[0] == K_SEAM)
    print("generated %d records: %d positive, %d negative" % (len(RECORDS), npos, nneg))
    print("  PKCS#1 v1.5: %d   PSS: %d   seam-recovery: %d   (3 real-cert records)"
          % (npk, nps, nsm))
    for path, fam in OUT:
        if os.path.isdir(os.path.join(REPO, path.split("/")[0])):
            print("  wrote %s" % path)


if __name__ == "__main__":
    main()
