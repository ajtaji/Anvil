#!/usr/bin/env python3
"""Emit tools/fixtures/x509_public_chains.json - REAL public certificate
chains for tools/a64/a64_x509_check.py's mode D.

WHAT IS IN IT, AND WHERE EACH PIECE COMES FROM

  * The chains are what real HTTPS servers sent, captured with
        openssl s_client -connect HOST:443 -servername HOST -showcerts
    and kept as PEM in tools/fixtures/x509_public/HOST.pem.  Certificates
    are public; nothing secret was sent or received to get them.
  * The trust anchors are the Mozilla root store - the same ca-bundle.crt
    Anvil reads from the stick (Anvil/Core/tls_roots.pbi).  For each
    chain every bundle root whose subject is the issuer of one of the
    chain's certificates is handed over, exactly as the board would have
    it among its 121, decoded the way tls_roots.pbi decodes it: the
    subject Name DER, and an RSA modulus/exponent or an EC curve id and
    uncompressed point.
  * The validation time is the capture time, recorded in the fixture, so
    the expectation does not change as the certificates age.
  * EVERY EXPECTATION IS OPENSSL'S.  Each positive is checked with
        openssl verify -attime T -no-CApath -CAfile ROOTS -untrusted REST LEAF
    plus -verify_hostname HOST, and must say OK.  The negatives tamper
    one signature byte of one certificate; OpenSSL must REFUSE the
    tampered chain, and the expected engine code (BearSSL's) is assigned
    by the rule written beside each one.

Usage: py -3 tools/x509_public_chains_gen.py [--bundle PATH] [--openssl PATH]
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHAINS = ROOT / "tools" / "fixtures" / "x509_public"
OUT = ROOT / "tools" / "fixtures" / "x509_public_chains.json"

# Capture time of the PEM files in tools/fixtures/x509_public/ (2026-10-14
# 22:52 UTC). Every certificate in them is inside its validity window then.
CAPTURE_TIME = 1792018348

# host -> (what the case proves, [(tamper slot, expected code, why)])
HOSTS = {
    "www.google.com": (
        "WE2 (P-256 key) signed ecdsa-with-SHA384 by GTS Root R4, a P-384 "
        "Mozilla root; leaf ecdsa-with-SHA256",
        # FIRST WRITTEN AS 62 AND THE ENGINE ANSWERED 52 - AND THE ENGINE
        # WAS RIGHT (2026-10-14). The anchor step against GTS Root R4 fails,
        # but that is not the end of THIS chain: google.com also sends GTS
        # Root R4's own cross-certificate (same key, issued by GlobalSign
        # Root CA, which is not in the bundle), so the walk goes on and
        # checks WE2's signature EXPLICITLY against that certificate's key
        # inside the chain - and that check is #X509ERR_BAD_SIGNATURE. A
        # chain that ENDS at the tampered anchor step answers 62 (see mode C).
        [(1, 52, "the anchor step fails, then the walk checks WE2's signature "
                 "explicitly against the next certificate - GTS Root R4's "
                 "cross-certificate, the same P-384 key - which is "
                 "#X509ERR_BAD_SIGNATURE")]),
    "github.com": (
        "Sectigo E36 signed ecdsa-with-SHA384 by Sectigo Public Server "
        "Authentication Root E46 (P-384); the E46 cross-certificate from "
        "USERTrust ECC follows and is never needed",
        []),
    "example.com": (
        "Cloudflare TLS Issuing ECC CA 3 signed ecdsa-with-SHA384 by an "
        "INTERMEDIATE with a P-384 key (SSL.com TLS Transit ECC CA R2), "
        "which is signed by SSL.com TLS ECC Root CA 2022 (P-384)",
        [(1, 52, "CA 3's signature is checked against the NEXT certificate's "
                 "P-384 key inside the chain walk, explicitly: "
                 "#X509ERR_BAD_SIGNATURE")]),
    "letsencrypt.org": (
        "three P-384 verifications with SHA-384 in one chain: the leaf by "
        "YE2, YE2 by Root YE, Root YE by ISRG Root X2",
        []),
    "www.microsoft.com": (
        "RSA all the way, sha384WithRSAEncryption at every link, 4096-bit "
        "intermediates, ending at DigiCert Global Root G2",
        [(0, 52, "the leaf's PKCS#1 v1.5 SHA-384 signature under the "
                 "intermediate's RSA-4096 key: #X509ERR_BAD_SIGNATURE")]),
}


# ------------------------------------------------------------------ DER
def tlv(buf, off):
    tag = buf[off]
    ln = buf[off + 1]
    hdr = 2
    if ln & 0x80:
        k = ln & 0x7F
        ln = int.from_bytes(buf[off + 2:off + 2 + k], "big")
        hdr = 2 + k
    return tag, off + hdr, ln, off + hdr + ln       # tag, body, len, end


def children(buf, off, end):
    out = []
    while off < end:
        t, b, ln, e = tlv(buf, off)
        out.append((t, off, b, ln, e))
        off = e
    return out


def cert_parts(der):
    """subject, issuer (whole TLVs), the SPKI, and the signature BIT
    STRING's last byte offset."""
    _, b, _, e = tlv(der, 0)
    top = children(der, b, e)                       # tbs, sigalg, sig
    t, toff, tb, tl, te = top[0]
    f = children(der, tb, te)
    i = 0
    if f[0][0] == 0xA0:                             # [0] version
        i = 1
    issuer = der[f[i + 2][1]:f[i + 2][4]]
    subject = der[f[i + 4][1]:f[i + 4][4]]
    spki = der[f[i + 5][1]:f[i + 5][4]]
    return dict(issuer=issuer, subject=subject, spki=spki,
                sig_last=top[2][4] - 1)


OID_RSA = bytes.fromhex("2a864886f70d010101")
OID_EC = bytes.fromhex("2a8648ce3d0201")
CURVES = {bytes.fromhex("2a8648ce3d030107"): 23,
          bytes.fromhex("2b81040022"): 24,
          bytes.fromhex("2b81040023"): 25}


def spki_key(spki):
    _, b, _, e = tlv(spki, 0)
    alg, bits = children(spki, b, e)[:2]
    a = children(spki, alg[2], alg[4])
    oid = spki[a[0][2]:a[0][4]]
    key = spki[bits[2] + 1:bits[4]]                 # skip unused-bits byte
    if oid == OID_RSA:
        _, kb, _, ke = tlv(key, 0)
        n, ex = children(key, kb, ke)[:2]
        nb = key[n[2]:n[4]].lstrip(b"\x00")
        eb = key[ex[2]:ex[4]].lstrip(b"\x00")
        return dict(type=1, curve=0, a=nb, b=eb)
    if oid == OID_EC:
        curve = CURVES.get(spki[a[1][2]:a[1][4]])
        if curve is None:
            return None
        return dict(type=2, curve=curve, a=key, b=b"")
    return None


def pem_certs(text):
    return [base64.b64decode("".join(m.group(1).split()))
            for m in re.finditer(r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----",
                                 text, re.S)]


def pem(der):
    b = base64.b64encode(der).decode()
    return ("-----BEGIN CERTIFICATE-----\n"
            + "\n".join(b[i:i + 64] for i in range(0, len(b), 64))
            + "\n-----END CERTIFICATE-----\n")


def ossl_verify(openssl, tmp, roots, chain, host, t):
    rp, up, lp = (tmp / "roots.pem", tmp / "untrusted.pem", tmp / "leaf.pem")
    rp.write_text("".join(pem(r) for r in roots))
    up.write_text("".join(pem(c) for c in chain[1:]))
    lp.write_text(pem(chain[0]))
    cmd = [openssl, "verify", "-attime", str(t), "-no-CApath", "-CAfile", str(rp),
           "-verify_hostname", host]
    if len(chain) > 1:
        cmd += ["-untrusted", str(up)]
    cmd.append(str(lp))
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip().endswith(": OK"), (r.stdout + r.stderr).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=r"C:\Program Files\Git\ucrt64\etc\ssl\certs\ca-bundle.crt")
    ap.add_argument("--openssl", default=shutil.which("openssl")
                    or r"C:\Program Files\Git\ucrt64\bin\openssl.exe")
    a = ap.parse_args()
    bundle = pem_certs(pathlib.Path(a.bundle).read_text(errors="replace"))
    by_subject = {}
    for r in bundle:
        by_subject.setdefault(cert_parts(r)["subject"], []).append(r)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="x509pub_"))
    cases = []
    try:
        for host, (what, tampers) in HOSTS.items():
            chain = pem_certs((CHAINS / (host + ".pem")).read_text())
            parts = [cert_parts(c) for c in chain]
            roots = []
            for p in parts:
                for r in by_subject.get(p["issuer"], []):
                    if r not in roots:
                        roots.append(r)
            if not roots:
                raise SystemExit("%s: no Mozilla root issues any certificate "
                                 "in the chain" % host)
            ok, msg = ossl_verify(a.openssl, tmp, roots, chain, host, CAPTURE_TIME)
            if not ok:
                raise SystemExit("%s: OpenSSL does not validate the captured "
                                 "chain:\n%s" % (host, msg))
            anchors = []
            for r in roots:
                rp = cert_parts(r)
                k = spki_key(rp["spki"])
                if k is None:
                    raise SystemExit("%s: a root with a key tls_roots.pbi "
                                     "would not decode" % host)
                anchors.append(dict(dn=rp["subject"].hex(), type=k["type"],
                                    curve=k["curve"], a=k["a"].hex(), b=k["b"].hex()))
            base = dict(host=host, what=what, time=CAPTURE_TIME,
                        certs=[c.hex() for c in chain], anchors=anchors)
            cases.append(dict(base, label="%s, captured chain" % host, expect=32,
                              openssl="verify OK"))
            for slot, code, why in tampers:
                bad = [bytearray(c) for c in chain]
                bad[slot][parts[slot]["sig_last"]] ^= 0x01
                bad = [bytes(c) for c in bad]
                ok, msg = ossl_verify(a.openssl, tmp, roots, bad, host, CAPTURE_TIME)
                if ok:
                    raise SystemExit("%s: OpenSSL ACCEPTS the chain with "
                                     "certificate %d's signature tampered" % (host, slot))
                cases.append(dict(base, certs=[c.hex() for c in bad],
                                  label="%s, last signature byte of certificate %d "
                                        "flipped" % (host, slot),
                                  expect=code, why=why,
                                  openssl=msg.splitlines()[-1][:160]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    OUT.write_text(json.dumps(dict(
        note="Generated by tools/x509_public_chains_gen.py from the captured "
             "chains in tools/fixtures/x509_public/ and the Mozilla bundle; "
             "every positive validated by openssl verify at the capture time, "
             "every tamper refused by it.",
        bundle=str(a.bundle), cases=cases), indent=1) + "\n", encoding="utf-8")
    print("wrote %s: %d cases" % (OUT, len(cases)))
    for c in cases:
        print("  %-60s expect %d  (%d certs, %d anchors) openssl: %s"
              % (c["label"], c["expect"], len(c["certs"]), len(c["anchors"]),
                 c["openssl"][:60]))


if __name__ == "__main__":
    main()
