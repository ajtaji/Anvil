#!/usr/bin/env python3
"""ecdsa_x509_gen.py - the M9 corpus: the certificate path validator's
SIGNATURE SEAM goes live when the ecdsa module is linked ahead of it.

The M12 corpus (tools/x509_proof_gen.py) links NEITHER signature module:
it defines #X509_SIG_LINKED = 0, so the loud stubs answer "not linked" and
every chain that reaches a signature check ends at #X509ERR_SEAM (200).

This corpus is the same certificates with #X509_SIG_LINKED = 1 and the
ecdsa module included ahead of the validator, so the same real EC chain
that stopped at 200 must now come back with a REAL verdict:

    real_ec_chain            -> #X509ERR_OK (32)          validated
    corrupted ee signature   -> #X509ERR_BAD_SIGNATURE (52)
    corrupted ica signature  -> #X509ERR_NOT_TRUSTED (62)   see below
                                (a corrupt CA signature is a TRUST failure,
                                 not a signature one)
    malformed ee signature   -> #X509ERR_BAD_SIGNATURE (52)
    the non-signature verdicts (direct trust, expired, notBefore, wrong
    server name, untrusted root, broken chain) are re-run unchanged, to
    show that linking the seam moved the signature verdicts and NOTHING
    else.

The RSA half of the seam is deliberately NOT linked in this corpus: every
RSA chain here still reports 200, which is the truth about that image.
tools/a64/a64_x509_check.py's mode C links both halves on AArch64.

The certificate corpus is lifted verbatim out of the DataSection that
tools/x509_proof_gen.py emits, so the two corpora cannot drift apart: the
bytes are read out of that generated source rather than re-derived.

IN THIS TREE THE CORPUS IS CONSUMED IN PROCESS by
tools/a64/a64_x509_check.py. Run on its own, this prints a summary.
"""
import os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lift_datasection_text(txt):
    """Return (datasection_text, {label: bytearray}) from M12 proof source text."""
    i = txt.index("DataSection")
    j = txt.index("EndDataSection")
    ds = txt[i:j]
    blobs = {}
    cur = None
    for line in ds.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if m:
            cur = m.group(1)
            blobs[cur] = bytearray()
            continue
        m = re.match(r"^\s*Data\.a\s+(.*)$", line)
        if m and cur is not None:
            for tok in m.group(1).split(","):
                blobs[cur].append(int(tok.strip()) & 255)
    return ds, blobs


def lift_datasection(path):
    """Return (datasection_text, {label: bytearray}) from an M12 proof source file."""
    return lift_datasection_text(
        open(path, encoding="utf-8", errors="replace").read())


def data_lines(label, b):
    out = ["%s:" % label]
    for k in range(0, len(b), 16):
        out.append("  Data.a " + ", ".join(str(x) for x in b[k:k + 16]))
    return out


def corrupt_last_sig_byte(der):
    """Flip the low bit of the final byte of the certificate's signature
    BIT STRING - still well-formed DER, mathematically wrong."""
    b = bytearray(der)
    b[-1] ^= 0x01
    return b


def malform_sig_tag(der):
    """Break the signature's SEQUENCE tag. Walk the certificate to find
    where the signatureValue BIT STRING's content starts."""
    b = bytearray(der)
    def tlv(off):
        l = b[off + 1]
        if l < 0x80:
            return off + 2, l, 2 + l
        n = l & 0x7F
        ln = int.from_bytes(bytes(b[off + 2:off + 2 + n]), "big")
        return off + 2 + n, ln, 2 + n + ln
    coff, _clen, _ = tlv(0)                 # Certificate SEQUENCE
    _toff, _tlen, ttot = tlv(coff)          # tbsCertificate
    _aoff, _alen, atot = tlv(coff + ttot)   # signatureAlgorithm
    soff, _slen, _ = tlv(coff + ttot + atot)  # signatureValue BIT STRING
    b[soff + 1] ^= 0x01                     # 0x30 -> 0x31
    return b


def build(ext, blobs):
    ee = blobs["der_ee_ec"]
    ica = blobs["der_ica_ec"]
    extra = {
        "der_ee_ec_badsig": corrupt_last_sig_byte(ee),
        "der_ica_ec_badsig": corrupt_last_sig_byte(ica),
        "der_ee_ec_malformed": malform_sig_tag(ee),
    }

    L = []
    a = L.append
    a("")
    a("Global Dim gC.i[8]")
    a("Global Dim gL.i[8]")
    a("")
    a("Global LibChecks.i")
    a("Global LibPasses.i")
    a("Global LibFails.i")
    a("Global LibFirstFail.i")
    a("Global LibFirstGot.i")
    a("Global LibFirstWant.i")
    a("Global LibDone.i")
    a("")
    a("Procedure Check(got.i, want.i)")
    a("  LibChecks = LibChecks + 1")
    a("  If got = want")
    a("    LibPasses = LibPasses + 1")
    a("    ProcedureReturn")
    a("  EndIf")
    a("  If LibFails = 0")
    a("    LibFirstFail = LibChecks")
    a("    LibFirstGot = got")
    a("    LibFirstWant = want")
    a("  EndIf")
    a("  LibFails = LibFails + 1")
    a("EndProcedure")
    a("")
    a("Procedure RunAll()")
    a("  Protected r.i")
    a("  LibChecks = 0")
    a("  LibPasses = 0")
    a("  LibFails = 0")
    a("  LibFirstFail = 0")
    a("  EcdsaInit()")
    a("")
    a("  ; ---- THE ONE THAT MOVED: real EC chain, signatures now checked")
    a("  ;      for real. Under the M12 proof this same case answered 200")
    a("  ;      (#X509ERR_SEAM); linking ecdsa must make it 32 (validated).")
    a("  X509ResetAnchors()")
    a("  X509AddAnchorEC(1, ?dn_root_ec, 30, 23, ?q_root_ec, 65)")
    a("  gC[0] = ?der_ee_ec : gL[0] = %d" % len(ee))
    a("  gC[1] = ?der_ica_ec : gL[1] = %d" % len(ica))
    a("  r = X509ValidateChain(@gC, @gL, 2, 0, -1, 1590969600)")
    a("  Check(r, 32)")
    a("")
    a("  ; the same chain with the server name checked as well")
    a("  X509ResetAnchors()")
    a("  X509AddAnchorEC(1, ?dn_root_ec, 30, 23, ?q_root_ec, 65)")
    a("  gC[0] = ?der_ee_ec : gL[0] = %d" % len(ee))
    a("  gC[1] = ?der_ica_ec : gL[1] = %d" % len(ica))
    a("  r = X509ValidateChain(@gC, @gL, 2, ?srv_localhost, 9, 1590969600)")
    a("  Check(r, 32)")
    a("")
    a("  ; ---- corrupted END-ENTITY signature: one flipped bit, still")
    a("  ;      well-formed DER. Must be BAD_SIGNATURE (52), never OK.")
    a("  X509ResetAnchors()")
    a("  X509AddAnchorEC(1, ?dn_root_ec, 30, 23, ?q_root_ec, 65)")
    a("  gC[0] = ?der_ee_ec_badsig : gL[0] = %d" % len(extra["der_ee_ec_badsig"]))
    a("  gC[1] = ?der_ica_ec : gL[1] = %d" % len(ica))
    a("  r = X509ValidateChain(@gC, @gL, 2, 0, -1, 1590969600)")
    a("  Check(r, 52)")
    a("")
    a("  ; ---- corrupted INTERMEDIATE signature: the CA's own signature is the")
    a("  ;      one that fails. The answer is NOT_TRUSTED (62), NOT")
    a("  ;      BAD_SIGNATURE (52), and the distinction is upstream's, not ours.")
    a("  ;      An end-entity signature is verified explicitly against the")
    a("  ;      issuer's key, so corrupting it returns BAD_SIGNATURE (check 3")
    a("  ;      above, which passes). The intermediate-versus-anchor step is the")
    a("  ;      TRUST decision: xm_end_chain sets NOT_TRUSTED whenever the walk")
    a("  ;      finishes without an anchor validating, which is exactly what a")
    a("  ;      corrupt CA signature causes. This vector expected 52 and the")
    a("  ;      board answered 62; the board was right and the expectation was")
    a("  ;      wrong. Both are refusals - the chain is rejected either way, so")
    a("  ;      this failed closed throughout - but the REASON matters when")
    a("  ;      someone is reading a diagnostic.")
    a("  X509ResetAnchors()")
    a("  X509AddAnchorEC(1, ?dn_root_ec, 30, 23, ?q_root_ec, 65)")
    a("  gC[0] = ?der_ee_ec : gL[0] = %d" % len(ee))
    a("  gC[1] = ?der_ica_ec_badsig : gL[1] = %d" % len(extra["der_ica_ec_badsig"]))
    a("  r = X509ValidateChain(@gC, @gL, 2, 0, -1, 1590969600)")
    a("  Check(r, 62)")
    a("")
    a("  ; ---- malformed signature ENCODING (broken SEQUENCE tag). The")
    a("  ;      verifier refuses the encoding; the chain is rejected.")
    a("  X509ResetAnchors()")
    a("  X509AddAnchorEC(1, ?dn_root_ec, 30, 23, ?q_root_ec, 65)")
    a("  gC[0] = ?der_ee_ec_malformed : gL[0] = %d" % len(extra["der_ee_ec_malformed"]))
    a("  gC[1] = ?der_ica_ec : gL[1] = %d" % len(ica))
    a("  r = X509ValidateChain(@gC, @gL, 2, 0, -1, 1590969600)")
    a("  Check(r, 52)")
    a("")
    a("  ; ---- linking the seam must not disturb anything else. These are")
    a("  ;      the M12 verdicts that never reach a signature check.")
    a("  X509ResetAnchors()")
    a("  X509AddAnchorEC(0, ?dn_ee_ec, 35, 23, ?q_ee_ec, 65)")
    a("  gC[0] = ?der_ee_ec : gL[0] = %d" % len(ee))
    a("  r = X509ValidateChain(@gC, @gL, 1, 0, -1, 1590969600)")
    a("  Check(r, 32)")
    a("")
    a("  X509ResetAnchors()")
    a("  gC[0] = ?der_ee_ec : gL[0] = %d" % len(ee))
    a("  r = X509ValidateChain(@gC, @gL, 1, 0, -1, 4070908800)")
    a("  Check(r, 54)")
    a("")
    a("  X509ResetAnchors()")
    a("  gC[0] = ?der_ee_ec : gL[0] = %d" % len(ee))
    a("  r = X509ValidateChain(@gC, @gL, 1, 0, -1, 946684800)")
    a("  Check(r, 54)")
    a("")
    a("  X509ResetAnchors()")
    a("  X509AddAnchorEC(0, ?dn_ee_ec, 35, 23, ?q_ee_ec, 65)")
    a("  gC[0] = ?der_ee_ec : gL[0] = %d" % len(ee))
    a("  r = X509ValidateChain(@gC, @gL, 1, ?srv_wrong, 17, 1590969600)")
    a("  Check(r, 56)")
    a("")
    a("  X509ResetAnchors()")
    a("  gC[0] = ?der_ee_ec : gL[0] = %d" % len(ee))
    a("  r = X509ValidateChain(@gC, @gL, 1, 0, -1, 1590969600)")
    a("  Check(r, 62)")
    a("")
    a("  ; ---- the RSA half of the seam is NOT linked in this image, and")
    a("  ;      says so: an RSA chain still reports 200.")
    a("  X509ResetAnchors()")
    a("  X509AddAnchorRSA(1, ?dn_root_rsa, 30, ?n_root_rsa, 256, ?e_root_rsa, 3)")
    a("  gC[0] = ?der_ee_rsa : gL[0] = %d" % len(blobs["der_ee_rsa"]))
    a("  gC[1] = ?der_ica_rsa : gL[1] = %d" % len(blobs["der_ica_rsa"]))
    a("  r = X509ValidateChain(@gC, @gL, 2, 0, -1, 1590969600)")
    a("  Check(r, 200)")
    a("")
    a("  LibDone = $600DCAFE")
    a("EndProcedure")
    a("")
    a("RunAll()")
    a("")
    a("Repeat")
    a("ForEver")
    a("")
    return "\n".join(L), extra


def main():
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import x509_proof_gen  # noqa: E402
    _ds, blobs = lift_datasection_text(x509_proof_gen.build_body())
    body, extra = build("pi4", blobs)
    print("checks: %d   tampered certificates: %d   lifted blobs: %d"
          % (body.count("Check(r,"), len(extra), len(blobs)))
    print("This corpus is run in process by tools/a64/a64_x509_check.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
