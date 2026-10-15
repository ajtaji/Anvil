#!/usr/bin/env python3
"""Emit tools/fixtures/ecp_vectors.json - the P-384 and P-521 ECDSA
signature-VERIFY vectors for tools/a64/a64_ecp_check.py.

WHERE EVERY SIGNATURE AND EVERY EXPECTATION COMES FROM

  OpenSSL signs; OpenSSL and an independent pure-Python verifier judge.
  Each run makes two throw-away key pairs per curve with
  `openssl ecparam -genkey`, signs messages with `openssl dgst -shaNNN
  -sign`, and keeps only the PUBLIC point, the message hash and the
  signature.  The private keys live in a temporary directory that is
  deleted on exit and are never written to the fixture.

  Every record whose signature can be written in DER is then handed back
  to `openssl dgst -verify`, and its verdict must equal the record's
  expectation, AND the pure-Python FIPS 186-4 verifier below must agree.
  Records whose public key OpenSSL cannot even import (off the curve, a
  coordinate >= p, a compressed or truncated point) are judged by the
  Python verifier and by the FIPS 186-4 rule that names the refusal.

ON CAVP: the NIST CAVP SigVer .rsp files are not on this machine and this
script fetches nothing.  The records follow the SigVer RECORD SHAPE and
its failure taxonomy - message changed, r changed, s changed, wrong key,
r or s out of range - with every expectation produced by the two
verifiers above.  Said plainly so the next reader knows which vectors
are transcribed (none) and which are oracle-derived (all).

Usage:  py -3 tools/gen_ecp_vectors.py [--openssl PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "tools" / "fixtures" / "ecp_vectors.json"

CURVES = {
    24: "secp384r1",
    25: "secp521r1",
}


# ---------------------------------------------------------------- params
def ec_params(openssl, name):
    out = subprocess.run([openssl, "ecparam", "-name", name, "-param_enc",
                          "explicit", "-text", "-noout"],
                         capture_output=True, text=True, check=True).stdout

    def grab(label):
        m = re.search(r"^%s:?\s*\n((?:\s+[0-9a-f:]+\n)+)" % re.escape(label),
                      out, re.M)
        if not m:
            raise SystemExit("openssl ecparam output has no %r block" % label)
        return int(re.sub(r"[\s:]", "", m.group(1)), 16)

    p, a, b, n = grab("Prime"), grab("A"), grab("B"), grab("Order")
    g = grab("Generator (uncompressed)")
    L = (p.bit_length() + 7) // 8
    gb = g.to_bytes(1 + 2 * L, "big")
    return dict(p=p, a=a, b=b, n=n, L=L,
                gx=int.from_bytes(gb[1:1 + L], "big"),
                gy=int.from_bytes(gb[1 + L:], "big"))


# ---------------------------------------------- the independent verifier
def pt_add(P1, P2, c):
    p = c["p"]
    if P1 is None:
        return P2
    if P2 is None:
        return P1
    x1, y1 = P1
    x2, y2 = P2
    if x1 == x2:
        if (y1 + y2) % p == 0:
            return None
        lam = (3 * x1 * x1 + c["a"]) * pow(2 * y1, -1, p) % p
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, p) % p
    x3 = (lam * lam - x1 - x2) % p
    return (x3, (lam * (x1 - x3) - y1) % p)


def pt_mul(k, P, c):
    R = None
    while k:
        if k & 1:
            R = pt_add(R, P, c)
        P = pt_add(P, P, c)
        k >>= 1
    return R


def on_curve(x, y, c):
    p = c["p"]
    return (y * y - (x * x * x + c["a"] * x + c["b"])) % p == 0


def bits2int(h, c):
    nb = c["n"].bit_length()
    e = int.from_bytes(h, "big")
    if len(h) * 8 > nb:
        e >>= len(h) * 8 - nb
    return e


def py_verify(q, h, r, s, c):
    """FIPS 186-4 6.4.2, with SEC 1 point decoding. 1 valid / 0 not."""
    L, p, n = c["L"], c["p"], c["n"]
    if not (0 < r < n and 0 < s < n):
        return 0
    if len(q) != 1 + 2 * L or q[0] != 4:
        return 0
    x = int.from_bytes(q[1:1 + L], "big")
    y = int.from_bytes(q[1 + L:], "big")
    if x >= p or y >= p or not on_curve(x, y, c):
        return 0
    e = bits2int(h, c) % n
    w = pow(s, -1, n)
    R = pt_add(pt_mul(e * w % n, (c["gx"], c["gy"]), c),
               pt_mul(r * w % n, (x, y), c), c)
    if R is None:
        return 0
    return 1 if R[0] % n == r else 0


def py_sign(d, h, c):
    """Plain FIPS 186-4 6.4.1 signing with a random nonce - used ONLY to
    sign under the two edge keys OpenSSL will not generate. Its output
    is judged by OpenSSL, never trusted on its own."""
    import secrets
    n = c["n"]
    e = bits2int(h, c) % n
    while True:
        k = secrets.randbelow(n - 1) + 1
        R = pt_mul(k, (c["gx"], c["gy"]), c)
        r = R[0] % n
        if r == 0:
            continue
        s = pow(k, -1, n) * (e + r * d) % n
        if s:
            return r, s


CURVE_OID = {24: bytes.fromhex("2b81040022"), 25: bytes.fromhex("2b81040023")}


def spki_pem(point, cid):
    """SubjectPublicKeyInfo { id-ecPublicKey, namedCurve } around a point."""
    import base64

    def tlv(tag, body):
        if len(body) < 128:
            return bytes([tag, len(body)]) + body
        return bytes([tag, 0x81, len(body)]) + body
    alg = tlv(0x30, tlv(0x06, bytes.fromhex("2a8648ce3d0201")) + tlv(0x06, CURVE_OID[cid]))
    der = tlv(0x30, alg + tlv(0x03, b"\x00" + point))
    b64 = base64.b64encode(der).decode()
    return ("-----BEGIN PUBLIC KEY-----\n"
            + "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
            + "\n-----END PUBLIC KEY-----\n")


# ------------------------------------------------------------------- DER
def der_int(v):
    b = v.to_bytes(max(1, (v.bit_length() + 7) // 8), "big")
    if b[0] & 0x80:
        b = b"\x00" + b
    return b"\x02" + bytes([len(b)]) + b


def der_sig(r, s):
    body = der_int(r) + der_int(s)
    if len(body) < 128:
        return b"\x30" + bytes([len(body)]) + body
    return b"\x30\x81" + bytes([len(body)]) + body


def der_split(sig):
    assert sig[0] == 0x30
    off = 2 if sig[1] < 0x80 else 3
    assert sig[off] == 2
    rl = sig[off + 1]
    r = int.from_bytes(sig[off + 2:off + 2 + rl], "big")
    off = off + 2 + rl
    assert sig[off] == 2
    sl = sig[off + 1]
    s = int.from_bytes(sig[off + 2:off + 2 + sl], "big")
    return r, s


# --------------------------------------------------------------- openssl
class Ossl:
    def __init__(self, exe, tmp):
        self.exe, self.tmp, self.k = exe, pathlib.Path(tmp), 0

    def run(self, *a, ok=True):
        r = subprocess.run([self.exe, *a], capture_output=True)
        if ok and r.returncode != 0:
            raise SystemExit("openssl %s failed:\n%s" % (a, r.stderr.decode()))
        return r

    def keypair(self, name):
        self.k += 1
        key = self.tmp / ("k%d.pem" % self.k)
        pub = self.tmp / ("p%d.pem" % self.k)
        der = self.tmp / ("p%d.der" % self.k)
        self.run("ecparam", "-name", name, "-genkey", "-noout", "-out", str(key))
        self.run("ec", "-in", str(key), "-pubout", "-out", str(pub))
        self.run("ec", "-in", str(key), "-pubout", "-outform", "DER", "-out", str(der))
        return key, pub, der.read_bytes()

    def sign(self, key, dg, msg):
        m = self.tmp / "m.bin"
        s = self.tmp / "s.der"
        m.write_bytes(msg)
        self.run("dgst", "-" + dg, "-sign", str(key), "-out", str(s), str(m))
        return s.read_bytes()

    def verify(self, pub, dg, msg, sig):
        m = self.tmp / "m.bin"
        s = self.tmp / "s.der"
        m.write_bytes(msg)
        s.write_bytes(sig)
        r = self.run("dgst", "-" + dg, "-verify", str(pub), "-signature",
                     str(s), str(m), ok=False)
        return 1 if b"Verified OK" in r.stdout else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--openssl", default=shutil.which("openssl")
                    or r"C:\Program Files\Git\ucrt64\bin\openssl.exe")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="ecpvec_")
    o = Ossl(a.openssl, tmp)
    recs = []
    try:
        for cid, name in CURVES.items():
            c = ec_params(a.openssl, name)
            L, n, p = c["L"], c["n"], c["p"]
            # the curve itself, before any vector: G on it, n*G infinite
            if not on_curve(c["gx"], c["gy"], c):
                raise SystemExit("%s: G is not on the curve" % name)
            if pt_mul(n, (c["gx"], c["gy"]), c) is not None:
                raise SystemExit("%s: n*G is not the point at infinity" % name)
            k1, pub1, spki1 = o.keypair(name)
            k2, pub2, spki2 = o.keypair(name)
            q1 = spki1[-(1 + 2 * L):]
            q2 = spki2[-(1 + 2 * L):]

            def add(label, q, h, r, s, expect, kind, msg=None, dg=None,
                    pub=None, raw=None, rule=None):
                # rule names the FIPS 186-4 / encoding rule that decides a
                # record the Python verifier cannot express (a raw form of
                # the wrong shape); every other record it must agree with.
                if raw is None:
                    raw = r.to_bytes(L, "big") + s.to_bytes(L, "big")
                rec = dict(curve=cid, label="%s %s" % (name, label),
                           q=q.hex(), hash=h.hex(), raw=raw.hex(),
                           der=der_sig(r, s).hex() if (r > 0 and s > 0) else "",
                           expect=expect, kind=kind)
                if rule:
                    rec["rule"] = rule
                else:
                    pv = py_verify(q, h, r, s, c)
                    if pv != expect:
                        raise SystemExit("%s: the Python verifier says %d, the "
                                         "record says %d" % (rec["label"], pv, expect))
                if msg is not None and pub is not None and rec["der"]:
                    ov = o.verify(pub, dg, msg, bytes.fromhex(rec["der"]))
                    if ov != expect:
                        raise SystemExit("%s: openssl says %d, the record says %d"
                                         % (rec["label"], ov, expect))
                    rec["openssl"] = ov
                recs.append(rec)

            msg = ("Anvil P-%d vector, curve %d" % (n.bit_length(), cid)).encode()
            for dg in ("sha256", "sha384", "sha512"):
                h = hashlib.new(dg, msg).digest()
                sig = o.sign(k1, dg, msg)
                r, s = der_split(sig)
                add("valid, %s" % dg, q1, h, r, s, 1, "full", msg, dg, pub1)
                if dg == "sha384":
                    # the same signature through the DER seam, as OpenSSL
                    # wrote it (it may carry a 0x81 long form on P-521)
                    recs[-1]["der_as_signed"] = sig.hex()
                    # (r, n - s) is ALSO a valid ECDSA signature
                    add("valid, %s, s replaced by n - s" % dg, q1, h, r, n - s, 1,
                        "full", msg, dg, pub1)
                    other = msg + b"!"
                    h2 = hashlib.new(dg, other).digest()
                    add("message changed", q1, h2, r, s, 0, "full", other, dg, pub1)
                    add("r changed", q1, h, (r + 1) % n or 1, s, 0, "full", msg, dg, pub1)
                    add("s changed", q1, h, r, (s + 1) % n or 1, 0, "full", msg, dg, pub1)
                    add("wrong public key", q2, h, r, s, 0, "full", msg, dg, pub2)
                    add("r = 0", q1, h, 0, s, 0, "cheap")
                    add("s = 0", q1, h, r, 0, 0, "cheap")
                    add("r = n", q1, h, n, s, 0, "cheap", msg, dg, pub1)
                    add("s = n", q1, h, r, n, 0, "cheap", msg, dg, pub1)
                    if (n + r).bit_length() <= 8 * L:
                        # only expressible where n + r still fits L bytes
                        # (P-521: 521-bit n in 66 bytes)
                        add("r + n (same residue, out of range)", q1, h, n + r, s,
                            0, "cheap", msg, dg, pub1)
                    x = int.from_bytes(q1[1:1 + L], "big")
                    y = int.from_bytes(q1[1 + L:], "big")
                    add("public key off the curve (y + 1)", b"\x04" + x.to_bytes(L, "big")
                        + ((y + 1) % p).to_bytes(L, "big"), h, r, s, 0, "cheap")
                    # x + p where it still fits L bytes (the same residue, an
                    # on-curve point mod p, and still refused: x must be < p);
                    # p itself where it does not
                    xx = x + p if (x + p).bit_length() <= 8 * L else p
                    add("public key x coordinate >= p", b"\x04" + xx.to_bytes(L, "big")
                        + y.to_bytes(L, "big"), h, r, s, 0, "cheap")
                    add("public key compressed prefix 0x02", b"\x02" + q1[1:], h, r, s,
                        0, "cheap")
                    add("public key truncated by one byte", q1[:-1], h, r, s, 0, "cheap")
                    add("raw signature of odd length", q1, h, r, s, 0, "cheap",
                        raw=r.to_bytes(L, "big") + s.to_bytes(L, "big")[:-1],
                        rule="r || s must split into two equal halves")
                    add("raw r and s one byte wider than the curve, value too large",
                        q1, h, r, s, 0, "cheap",
                        raw=b"\x01" + r.to_bytes(L, "big") + b"\x01" + s.to_bytes(L, "big"),
                        rule="each half is 2^(8L) + value, above n")
                    # THE SPECIAL CASES OF THE POINT ADDITION. With d = 1 the
                    # public key IS G, so the verifier's precomputed G + Q is
                    # a doubling reached through the addition formula; with
                    # d = n - 1 it is -G and G + Q is the point at infinity.
                    # OpenSSL will not generate these keys, so the Python
                    # signer below makes the signatures and OpenSSL, handed
                    # the public point as a SubjectPublicKeyInfo, judges them.
                    for d, what in ((1, "public key = G (d = 1)"),
                                    (n - 1, "public key = -G (d = n - 1)")):
                        Q = pt_mul(d, (c["gx"], c["gy"]), c)
                        qe = b"\x04" + Q[0].to_bytes(L, "big") + Q[1].to_bytes(L, "big")
                        pubp = o.tmp / "edge.pem"
                        pubp.write_text(spki_pem(qe, cid))
                        er, es = py_sign(d, h, c)
                        add("valid, " + what, qe, h, er, es, 1, "full", msg, dg, pubp)
                        add("tampered s, " + what, qe, h, er, (es + 1) % n or 1, 0,
                            "full", msg, dg, pubp)
                    add("raw r and s with a leading zero byte each (same values)",
                        q1, h, r, s, 1, "full",
                        raw=b"\x00" + r.to_bytes(L, "big") + b"\x00" + s.to_bytes(L, "big"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(
        note="Generated by tools/gen_ecp_vectors.py. Signatures by OpenSSL "
             "(throw-away keys, private halves discarded); every expectation "
             "agreed by openssl dgst -verify where the record is expressible "
             "in DER and by the pure-Python FIPS 186-4 verifier in the "
             "generator. Not CAVP files - see the generator's header.",
        openssl=subprocess.run([a.openssl, "version"], capture_output=True,
                               text=True).stdout.strip(),
        records=recs), indent=1) + "\n", encoding="utf-8")
    print("wrote %s: %d records" % (OUT, len(recs)))


if __name__ == "__main__":
    main()
