#!/usr/bin/env python3
"""The X.509 acceptance corpus (module M12), seam stubbed.

Bakes real captured certificate chains (the BearSSL sample set: an EC chain
root->ica->ee and an RSA chain root->ica->ee) plus a two-anchor trust set
(one ECDSA root, one RSA root) into the body of a self-test that runs the
lifted X.509 engine bytecode on t0vm and checks the verdict of each case.

Cases exercise every named outcome the engine can reach WITHOUT the
signature-verify seam (module M9 ecdsa / M10 rsa), plus the two CA chains
which correctly reach that seam:

  * direct-trust EC / RSA end-entity  -> OK (32)
  * expired / notBefore-in-future     -> EXPIRED (54)
  * wrong server name                 -> BAD_SERVER_NAME (56)
  * broken chain (subject!=issuer)    -> DN_MISMATCH (55)
  * no anchor                         -> NOT_TRUSTED (62)
  * real EC / RSA CA chain            -> SEAM (200)

IN THIS TREE THE CORPUS IS CONSUMED IN PROCESS. tools/a64/a64_x509_check.py
imports this module and parses build_body() - the generated source is the
specification, so the gate carries no certificate and no expectation of its
own. The certificates are the six public BearSSL sample certificates
(cert-*.pem; MIT, notice in licenses/BearSSL-LICENSE.txt), kept beside the
other published reference data in RaspberryPi4/Reference/. No private key
is read or needed.

Run on its own, this prints the corpus summary.
"""
import os, sys, datetime

# THE CERTIFICATES ARE READ WITH THE STANDARD LIBRARY (2026-10-14). This
# module used to import the third-party `cryptography` package for four
# things - PEM to DER, the subject Name's DER, and the EC point or RSA
# modulus/exponent - and on a machine without that package the whole x509
# gate (tools/a64/a64_x509_check.py, which imports this file) could not
# start. The same four things are now taken by the small DER reader in
# tools/x509_public_chains_gen.py. Where `cryptography` IS installed, every
# value is still cross-checked against it, so the package went from being
# a requirement to being a second opinion.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x509_public_chains_gen as _der  # noqa: E402
try:
    from cryptography import x509 as _cx509
    from cryptography.hazmat.primitives.serialization import Encoding as _Enc, PublicFormat as _PF
    from cryptography.hazmat.primitives.asymmetric import ec as _cec, rsa as _crsa
except ImportError:
    _cx509 = None


class _Cert:
    """The DER of one certificate and the parts this generator reads."""

    def __init__(self, der_bytes):
        self.der = der_bytes
        self.parts = _der.cert_parts(der_bytes)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
SAMPLES = os.path.join(REPO, "RaspberryPi4", "Reference")

CURVE_ID = {"secp256r1": 23, "secp384r1": 24, "secp521r1": 25}

# verdict codes (must match RaspberryPi4/Lib/x509.pi4 #X509ERR_*)
OK, EXPIRED, DN_MISMATCH, BAD_SERVER_NAME, NOT_TRUSTED, SEAM = 32, 54, 55, 56, 62, 200


def load(n):
    p = os.path.join(SAMPLES, n)
    if not os.path.exists(p):
        sys.exit("The BearSSL sample certificate %s was not found. Check that "
                 "RaspberryPi4/Reference/ holds the six cert-*.pem files from "
                 "BearSSL's samples directory." % p)
    text = open(p, "rb").read()
    ders = _der.pem_certs(text.decode("ascii", "replace"))
    if len(ders) != 1:
        sys.exit("%s should hold exactly one certificate" % p)
    c = _Cert(ders[0])
    if _cx509 is not None:
        ref = _cx509.load_pem_x509_certificate(text)
        if ref.public_bytes(_Enc.DER) != c.der or ref.subject.public_bytes() != c.parts["subject"]:
            sys.exit("the standard-library DER reader and the cryptography "
                     "package disagree about %s" % p)
    return c


def der(c):
    return c.der


def subject_dn_der(c, full_der):
    b = c.parts["subject"]
    if b not in full_der:
        sys.exit("The subject DN of a sample certificate does not appear "
                 "verbatim in its DER; check that the certificate file is the "
                 "unmodified BearSSL sample.")
    return b


def pubkey_of(c):
    """Return ('EC', curve_id, point_bytes) or ('RSA', n_bytes, e_bytes)."""
    k = _der.spki_key(c.parts["spki"])
    out = None
    if k is not None and k["type"] == 2:
        out = ("EC", k["curve"], k["a"])
    elif k is not None and k["type"] == 1:
        out = ("RSA", k["a"], k["b"])
    if out is not None and _cx509 is not None:
        pk = _cx509.load_der_x509_certificate(c.der).public_key()
        if isinstance(pk, _cec.EllipticCurvePublicKey):
            ref = ("EC", CURVE_ID[pk.curve.name],
                   pk.public_bytes(_Enc.X962, _PF.UncompressedPoint))
        else:
            nums = pk.public_numbers()
            ref = ("RSA", nums.n.to_bytes((nums.n.bit_length() + 7) // 8, "big"),
                   nums.e.to_bytes((nums.e.bit_length() + 7) // 8, "big"))
        if ref != out:
            sys.exit("the standard-library key reader and the cryptography "
                     "package disagree about a sample certificate")
    if out is not None:
        return out
    sys.exit("A sample certificate carries a key that is neither EC nor RSA; "
             "check the certificate files in RaspberryPi4/Reference/.")


def unix(y, mo, d):
    return int(datetime.datetime(y, mo, d, tzinfo=datetime.timezone.utc).timestamp())


# ---- load the sample chains ----
ee_ec, ica_ec, root_ec = load("cert-ee-ec.pem.txt"), load("cert-ica-ec.pem.txt"), load("cert-root-ec.pem.txt")
ee_rsa, ica_rsa, root_rsa = load("cert-ee-rsa.pem.txt"), load("cert-ica-rsa.pem.txt"), load("cert-root-rsa.pem.txt")

CERTS = {}   # label -> der bytes
BLOBS = {}   # label -> bytes (DNs, keys)


def cert(label, c):
    CERTS[label] = der(c)
    return label


def blob(label, b):
    BLOBS[label] = bytes(b)
    return label


cert("der_ee_ec", ee_ec);   cert("der_ica_ec", ica_ec)
cert("der_ee_rsa", ee_rsa); cert("der_ica_rsa", ica_rsa)
cert("der_root_rsa", root_rsa)

# anchors: EC root (CA), RSA root (CA), and the two EE keys as direct-trust anchors
blob("dn_root_ec", subject_dn_der(root_ec, der(root_ec)))
blob("dn_root_rsa", subject_dn_der(root_rsa, der(root_rsa)))
blob("dn_ee_ec", subject_dn_der(ee_ec, der(ee_ec)))
blob("dn_ee_rsa", subject_dn_der(ee_rsa, der(ee_rsa)))

k = pubkey_of(root_ec);  blob("q_root_ec", k[2]); RC_EC = k[1]
k = pubkey_of(root_rsa); blob("n_root_rsa", k[1]); blob("e_root_rsa", k[2])
k = pubkey_of(ee_ec);    blob("q_ee_ec", k[2]);   EE_EC_CURVE = k[1]
k = pubkey_of(ee_rsa);   blob("n_ee_rsa", k[1]);  blob("e_ee_rsa", k[2])

VALID = unix(2020, 6, 1)      # inside every cert's 2010..2037 window
FUTURE = unix(2099, 1, 1)     # after notAfter -> EXPIRED
PAST = unix(2000, 1, 1)       # before notBefore -> EXPIRED

# Each case: (name, [cert labels], anchors, serverAddr_label/None, serverStr,
#             unixtime, expected)
# anchors: list of ("CA_EC", dn, q, curve) / ("CA_RSA", dn, n, e) /
#          ("DT_EC", dn, q, curve) / ("DT_RSA", dn, n, e)
CASES = [
    ("direct_trust_ec", ["der_ee_ec"],
        [("DT_EC", "dn_ee_ec", "q_ee_ec", EE_EC_CURVE)], None, "", VALID, OK),
    ("direct_trust_rsa", ["der_ee_rsa"],
        [("DT_RSA", "dn_ee_rsa", "n_ee_rsa", "e_ee_rsa")], None, "", VALID, OK),
    ("expired", ["der_ee_ec"], [], None, "", FUTURE, EXPIRED),
    ("not_before_future", ["der_ee_ec"], [], None, "", PAST, EXPIRED),
    ("wrong_server_name", ["der_ee_ec"],
        [("DT_EC", "dn_ee_ec", "q_ee_ec", EE_EC_CURVE)], "srv_wrong",
        "wrong.example.com", VALID, BAD_SERVER_NAME),
    ("untrusted_root", ["der_ee_ec"], [], None, "", VALID, NOT_TRUSTED),
    ("broken_chain", ["der_ee_ec", "der_root_rsa"],
        [("CA_RSA", "dn_root_rsa", "n_root_rsa", "e_root_rsa")], None, "",
        VALID, DN_MISMATCH),
    ("real_ec_chain_seam", ["der_ee_ec", "der_ica_ec"],
        [("CA_EC", "dn_root_ec", "q_root_ec", RC_EC)], None, "", VALID, SEAM),
    ("real_rsa_chain_seam", ["der_ee_rsa", "der_ica_rsa"],
        [("CA_RSA", "dn_root_rsa", "n_root_rsa", "e_root_rsa")], None, "",
        VALID, SEAM),
]

# server-name string blobs
for _, _, _, saddr, sstr, _, _ in CASES:
    if saddr:
        blob(saddr, sstr.encode("ascii"))


def data_lines(name, byts):
    L = ["%s:" % name]
    if not byts:
        byts = b"\x00"
    for i in range(0, len(byts), 16):
        L.append("  Data.a " + ", ".join(str(b) for b in byts[i:i + 16]))
    return L


def build_body():
    L = []
    a = L.append
    a("")
    a("Global Dim gC.i[8]")
    a("Global Dim gL.i[8]")
    a("")
    a("Global LibChecks.i")
    a("Global LibFails.i")
    a("Global LibFirstFail.i")
    a("Global LibFirstGot.i")
    a("Global LibFirstWant.i")
    a("Global LibDone.i")
    a("")
    a("Procedure Check(got.i, want.i)")
    a("  LibChecks = LibChecks + 1")
    a("  If got <> want")
    a("    If LibFails = 0")
    a("      LibFirstFail = LibChecks")
    a("      LibFirstGot = got")
    a("      LibFirstWant = want")
    a("    EndIf")
    a("    LibFails = LibFails + 1")
    a("  EndIf")
    a("EndProcedure")
    a("")
    a("Procedure RunAll()")
    a("  Protected r.i")
    a("  LibChecks = 0")
    a("  LibFails = 0")
    a("  LibFirstFail = 0")
    for name, clabels, anchors, saddr, sstr, ut, exp in CASES:
        a("  ; ---- %s ----" % name)
        a("  X509ResetAnchors()")
        for anc in anchors:
            kind = anc[0]
            if kind == "CA_EC":
                a("  X509AddAnchorEC(1, ?%s, %d, %d, ?%s, %d)"
                  % (anc[1], len(BLOBS[anc[1]]), anc[3], anc[2], len(BLOBS[anc[2]])))
            elif kind == "DT_EC":
                a("  X509AddAnchorEC(0, ?%s, %d, %d, ?%s, %d)"
                  % (anc[1], len(BLOBS[anc[1]]), anc[3], anc[2], len(BLOBS[anc[2]])))
            elif kind == "CA_RSA":
                a("  X509AddAnchorRSA(1, ?%s, %d, ?%s, %d, ?%s, %d)"
                  % (anc[1], len(BLOBS[anc[1]]), anc[2], len(BLOBS[anc[2]]),
                     anc[3], len(BLOBS[anc[3]])))
            elif kind == "DT_RSA":
                a("  X509AddAnchorRSA(0, ?%s, %d, ?%s, %d, ?%s, %d)"
                  % (anc[1], len(BLOBS[anc[1]]), anc[2], len(BLOBS[anc[2]]),
                     anc[3], len(BLOBS[anc[3]])))
        for idx, cl in enumerate(clabels):
            a("  gC[%d] = ?%s : gL[%d] = %d" % (idx, cl, idx, len(CERTS[cl])))
        if saddr:
            a("  r = X509ValidateChain(@gC, @gL, %d, ?%s, %d, %d)"
              % (len(clabels), saddr, len(BLOBS[saddr]), ut))
        else:
            a("  r = X509ValidateChain(@gC, @gL, %d, 0, -1, %d)"
              % (len(clabels), ut))
        a("  Check(r, %d)" % exp)
    a("  LibDone = $600DCAFE")
    a("EndProcedure")
    a("")
    a("RunAll()")
    a("")
    a("Repeat")
    a("ForEver")
    a("")
    a("DataSection")
    for label, b in CERTS.items():
        L += data_lines(label, b)
    for label, b in BLOBS.items():
        L += data_lines(label, b)
    a("EndDataSection")
    return "\n".join(L)


def main():
    body = build_body()
    print("cases: %d   certs baked: %d   anchors/blobs: %d   body: %d lines"
          % (len(CASES), len(CERTS), len(BLOBS), body.count("\n") + 1))
    print("This corpus is run in process by tools/a64/a64_x509_check.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
