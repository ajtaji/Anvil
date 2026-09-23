#!/usr/bin/env python3
"""The M11 acceptance corpus: run the T0 PEM decoder bytecode on the t0vm
core and prove its DER output matches a python base64 oracle, byte for
byte, for several real certificates.

build_body() emits the driver (Base64Val, T0Native, DecodeCurrent) and the
per-certificate checks as source text, with each certificate's PEM text as
input and the python-decoded DER as the expected answer.

IN THIS TREE THE CORPUS IS CONSUMED IN PROCESS. tools/a64/a64_t0vm_check.py
imports CERTS, SAMPLES and der_of() from here and splices the driver
procedures out of build_body() verbatim, so the AArch64 run is driven with
exactly the calls this generator emits. The certificates are public BearSSL
sample certificates (MIT, notice in licenses/BearSSL-LICENSE.txt) kept in
RaspberryPi4/Reference/.

Run on its own, this prints the corpus summary.
"""
import os, re, base64, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
SAMPLES = os.path.join(REPO, "RaspberryPi4", "Reference")

CERTS = ["cert-ee-ec.pem.txt", "cert-ee-rsa.pem.txt", "cert-root-rsa.pem.txt"]


def der_of(pem_text):
    m = re.search(r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----",
                  pem_text, re.S)
    return base64.b64decode("".join(m.group(1).split()))


def data_lines(name, byts):
    L = ["%s:" % name]
    if not byts:
        byts = b"\x00"
    for i in range(0, len(byts), 16):
        L.append("  Data.a " + ", ".join(str(b) for b in byts[i:i + 16]))
    return L


def build_body(certs):
    """The part of the source identical across families (after the includes)."""
    maxin = max(len(p) for p, _ in certs) + 4
    maxout = max(len(d) for _, d in certs) + 16
    L = []
    a = L.append
    a("")
    a("Global Dim gIn.a[%d]" % maxin)
    a("Global gInLen.i")
    a("Global gInPos.i")
    a("Global Dim gOut.a[%d]" % maxout)
    a("Global gOutLen.i")
    a("")
    a("; --- verdict globals ---")
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
    a("; base64 char -> 6-bit value (0..63), -1 for '=', -2 otherwise.")
    a("Procedure.i Base64Val(c.i)")
    a("  If c >= 65 And c <= 90")
    a("    ProcedureReturn c - 65")
    a("  EndIf")
    a("  If c >= 97 And c <= 122")
    a("    ProcedureReturn c - 71")
    a("  EndIf")
    a("  If c >= 48 And c <= 57")
    a("    ProcedureReturn c + 4")
    a("  EndIf")
    a("  If c = 43")
    a("    ProcedureReturn 62")
    a("  EndIf")
    a("  If c = 47")
    a("    ProcedureReturn 63")
    a("  EndIf")
    a("  If c = 61")
    a("    ProcedureReturn -1")
    a("  EndIf")
    a("  ProcedureReturn -2")
    a("EndProcedure")
    a("")
    a("; The host native-word dispatcher for the PEM decoder program.")
    a("Procedure T0Native(nid.i)")
    a("  Protected v.i")
    a("  Protected c.i")
    a("  Select nid")
    a("    Case #T0N_read8_native")
    a("      If gInPos < gInLen")
    a("        T0Push(gIn[gInPos] & 255)")
    a("        gInPos = gInPos + 1")
    a("      Else")
    a("        T0Push(-1)")
    a("      EndIf")
    a("    Case #T0N_write8")
    a("      v = T0Pop() & 255")
    a("      gOut[gOutLen] = v")
    a("      gOutLen = gOutLen + 1")
    a("    Case #T0N_flush_buf")
    a("      ; output is written straight to gOut; nothing is staged")
    a("    Case #T0N_from_base64")
    a("      c = T0Pop() & 255")
    a("      T0Push(Base64Val(c))")
    a("  EndSelect")
    a("EndProcedure")
    a("")
    a("; Drive the VM over the currently loaded input; fills gOut/gOutLen.")
    a("Procedure DecodeCurrent()")
    a("  Protected st.i")
    a("  Protected guard.i")
    a("  gOutLen = 0")
    a("  gInPos = 0")
    a("  T0LoadPemdec()")
    a("  T0Start()")
    a("  guard = 0")
    a("  Repeat")
    a("    st = T0Run()")
    a("    If st = #T0_NATIVE")
    a("      T0Native(t0_native_id)")
    a("    ElseIf st = #T0_YIELD")
    a("      If gInPos >= gInLen")
    a("        Break")
    a("      EndIf")
    a("    Else")
    a("      Break")
    a("    EndIf")
    a("    guard = guard + 1")
    a("    If guard > 2000000")
    a("      Break")
    a("    EndIf")
    a("  ForEver")
    a("EndProcedure")
    a("")
    # per-cert load + compare procedures
    for idx, (pem, der) in enumerate(certs):
        a("Procedure LoadInput%d()" % idx)
        a("  Protected i.i")
        a("  Protected p.i")
        a("  p = ?gPem%d" % idx)
        a("  gInLen = %d" % len(pem))
        a("  i = 0")
        a("  While i < gInLen")
        a("    gIn[i] = PeekB(p + i) & 255")
        a("    i = i + 1")
        a("  Wend")
        a("EndProcedure")
        a("")
    a("Procedure RunAll()")
    a("  Protected i.i")
    a("  Protected p.i")
    a("  Protected want.i")
    a("  LibChecks = 0")
    a("  LibFails = 0")
    a("  LibFirstFail = 0")
    for idx, (pem, der) in enumerate(certs):
        a("  ; ---- cert %d ----" % idx)
        a("  LoadInput%d()" % idx)
        a("  DecodeCurrent()")
        a("  Check(gOutLen, %d)                ; DER length matches oracle" % len(der))
        a("  p = ?gDer%d" % idx)
        a("  i = 0")
        a("  While i < %d" % len(der))
        a("    want = PeekB(p + i) & 255")
        a("    Check(gOut[i] & 255, want)")
        a("    i = i + 1")
        a("  Wend")
    a("  LibDone = $600DCAFE")
    a("EndProcedure")
    a("")
    a("RunAll()")
    a("")
    a("Repeat")
    a("ForEver")
    a("")
    a("DataSection")
    for idx, (pem, der) in enumerate(certs):
        L += data_lines("gPem%d" % idx, pem)
        L += data_lines("gDer%d" % idx, der)
    a("EndDataSection")
    return "\n".join(L)


def main():
    certs = []
    for name in CERTS:
        p = os.path.join(SAMPLES, name)
        if not os.path.exists(p):
            sys.exit("The sample certificate %s was not found. Check that "
                     "RaspberryPi4/Reference/ holds the BearSSL cert-*.pem "
                     "files." % p)
        pem = open(p, "rb").read()
        der = der_of(pem.decode("ascii", "replace"))
        certs.append((pem, der))
        print("  %-22s PEM=%dB DER=%dB" % (name, len(pem), len(der)))
    body = build_body(certs)
    print("body: %d lines for %d certificates" % (body.count("\n") + 1, len(certs)))
    print("This corpus is run in process by tools/a64/a64_t0vm_check.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
