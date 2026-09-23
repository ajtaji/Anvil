#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/x509.pi4 and
RaspberryPi4/Lib/x509_blob.pi4 - X.509 certificate-chain validation on
AArch64.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  NO CERTIFICATE IS TRANSCRIBED HERE, AND NEITHER IS AN EXPECTATION.
  Both case lists are PARSED OUT OF THE GENERATORS THAT EMIT THE PICO
  GATES: tools/x509_proof_gen.py's build_body() for the seam-stubbed
  half, and tools/ecdsa_x509_gen.py's build() for the seam-linked half.
  Those two functions are what write x509Proof.pico2 and
  ecdsaX509Proof.pico2, so every anchor, every chain, every date and
  every expected verdict in this gate is the SAME OBJECT the 32-bit
  families are held to - not a second list that was once eyeballed
  against the first.  The certificate bytes come with them, out of
  x509_proof_gen's CERTS/BLOBS and out of ecdsa_x509_gen's own
  lift_datasection() and tamper functions.

  Exactly TWO cases are this gate's own, and neither contains a
  certificate:
    * EMPTY CHAIN.  count = 0 must be #X509ERR_EMPTY_CHAIN (35).  No
      32-bit gate covers it, and mutation M14 is the guard that refuses
      it being loosened.
    * THE CELL PROBE.  It drives XnMem's get32 native directly - which
      is what the VM does - and reads the pushed cell back at full
      64-bit width.  It exists because SHAPE 3 lands at exactly one
      place in this module, the host->cell boundary, and no certificate
      reaches it: a T0 cell is a SIGN-EXTENDED int32 and Xr32's `<< 24`
      no longer lands in the sign bit here.

  THE PROOF IS THE NAME OF THE REFUSAL, NOT THE FACT OF ONE.  A gate
  that accepted "any non-OK code" for any tampering would pass an
  engine that answers 62 to everything, including to a valid chain's
  neighbours.  Every case below carries ITS OWN verdict code and the
  failure line prints what the code MEANS.

  THERE ARE THREE IMAGES, NOT TWO, AND THE THIRD IS ONE NO 32-BIT
  FAMILY CAN BUILD.  Mode A builds with #X509_SIG_LINKED = 0 and
  requires that every chain reaching a signature check ends at
  #X509ERR_SEAM (200) and NEVER at OK.  Mode B builds with
  #X509_SIG_LINKED = 1 and ecdsa.pi4 linked, so the same EC chain comes
  back #X509ERR_OK (32) and three tampered variants come back
  #X509ERR_BAD_SIGNATURE (52).  The RSA half of the seam stays stubbed
  in mode B, exactly as the .pico2 proof does, because rsa.pi4's
  RsaVrfy takes FIVE arguments (the four public-key arguments moved to
  RsaSetPubKey when the A64 backend refused a ninth) and the seam is
  declared with NINE.  Every RSA chain in mode B therefore still
  reports 200, which is the truth about that image.

  MODE C LINKS ecdsa.pi4 AND rsa.pi4 AND STUBS NOTHING.  It exists
  because the split the backend's eight-argument limit forced on this
  family is exactly what makes the seam's RsaVrfy satisfiable: the
  32-bit copies have a nine-argument seam and a nine-argument
  implementation and STILL keep the RSA half stubbed in their own
  proof, so no .pico/.pico2/.unor4 image has ever run this path.  The
  RSA chains that answer 200 in modes A and B answer #X509ERR_OK (32)
  here, and their tampered variants answer #X509ERR_BAD_SIGNATURE (52).
  Run bare, this gate runs all three; --stub-only is A, --linked-only
  is B and C, --mode picks exactly one.

  EVERY VERDICT IS STORED AND CHECKED AT FULL 64-BIT WIDTH.  The
  harness writes with PokeI and this file unpacks with "<Q".  The A64
  GCM gate stored its verdicts with PokeN and the one mutation it
  existed to catch survived, because the wrong value's set bits were
  all above bit 31.

  IT RUNS ON ALL CORES.  The image is built ONCE per mode and the job
  list is sharded across a process pool.  --jobs overrides; use it when
  other workers are on the machine.

  THE BLOB IS GATED, NOT TRUSTED.  x509_blob.pi4 is lifted bytecode:
  tools/t0gen.py --native-ram over BearSSL's src/x509/x509_minimal.c,
  with x509.pi4's own #X_ context-RAM layout as the field map and
  inc/bearssl_x509.h for the named constants.  check_blob() below proves
  on every run that the blob is internally consistent - its header
  counts match its sections, every opmap entry is a canonical id or the
  next native in order, the #T0N_ constants number 0..n-1, and the entry
  slot names a real word.  BearSSL's C is not part of this tree; when the
  BEARSSL_SRC environment variable names a BearSSL checkout the blob is
  also REGENERATED in process and compared byte for byte, and without it
  that one cross-check is skipped and the run says so.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.  The oracle is a model of the
    instruction set: no caches, no memory system, no clock.
  * Anything about constant time, and deliberately so.  X.509 is PUBLIC
    data - certificates are on the wire in the clear - so there is no
    --timing mode here and there should not be.  The secret-bearing
    work is behind the signature seam and is gated in ecdsa.pi4's and
    rsa.pi4's own files.

Run: python tools/a64/a64_x509_check.py --jobs 6
     python tools/a64/a64_x509_check.py --stub-only
     python tools/a64/a64_x509_check.py --mutate
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import os
import pathlib
import re
import struct
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent

# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN.  A root pinned
# into the file made another gate build a DIFFERENT working copy, with
# that copy's compiler, and print the answer as this tree's.  The
# tree actually read is printed below.
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
X509 = ROOT / "RaspberryPi4" / "Lib" / "x509.pi4"
BLOB_A64 = ROOT / "RaspberryPi4" / "Lib" / "x509_blob.pi4"
# BearSSL's sources are not part of this tree. Set BEARSSL_SRC to the root
# of a BearSSL checkout to regenerate the blob in process and compare.
BEARSSL_SRC = os.environ.get("BEARSSL_SRC")
WORK = ROOT / "_work"

LOAD = 0x00400000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
STACK = 0x03000000

UART_LO = 0xFE201000
UART_HI = 0xFE201048
UART_DR = 0xFE201000

H_SCRIPT = 0x06000000
H_RESULT = 0x0A000000
H_DATA = 0x0B000000

# A whole seam-linked EC chain is two ECDSA verifications on top of the
# i15 core, which is tens of millions of model instructions.  The limit
# is a runaway detector, not a budget.
STEP_LIMIT = 20_000_000_000
# A RUNAWAY MUST STOP IN MINUTES, NOT IN DAYS, and a mutant that loops
# forever is a real outcome of a sweep that has to be REPORTED rather
# than waited on.  The model runs at roughly 200k instructions a second
# in one process.  Mode A's whole corpus is under 40 million, so 250
# million is six times the honest cost; a mode B/C mutant runs one
# tampered EC chain, which is two ECDSA verifications at roughly 155
# million each (measured by tools/a64/a64_ecdsa_check.py), so one
# billion is three times its honest cost.
MUTANT_STEP_LIMIT = {"A": 250_000_000, "B": 1_000_000_000,
                     "C": 1_000_000_000}

JOB_STRIDE = 256            # one script record
RESULT_STRIDE = 32          # four i64 fields
SENTINEL = 0xA5
MAX_CERTS = 4
MAX_ANCHORS = 4

OP_END, OP_VALIDATE, OP_CELLPROBE = 0, 1, 2

# How a multi-line failure is re-indented under a mutation verdict,
# so the reader sees the CODE THAT CAME BACK and not only the case
# name.
IND = "\n         "

# The verdict codes, and what each one MEANS.  A gate that prints only
# the number makes the reader go and look it up, and the house rule says
# an error keeps the number AND names the thing to check.
VERDICT_NAMES = {
    32: "#X509ERR_OK - the chain validated",
    35: "#X509ERR_EMPTY_CHAIN - no certificate was supplied",
    49: "#X509ERR_UNSUPPORTED - an algorithm this build does not wire",
    51: "#X509ERR_WRONG_KEY_TYPE - signer key type is not the one the "
        "signature algorithm needs",
    52: "#X509ERR_BAD_SIGNATURE - a signature did not verify",
    53: "#X509ERR_TIME_UNKNOWN - no validity date was available",
    54: "#X509ERR_EXPIRED - outside the certificate's validity window "
        "(notBefore or notAfter)",
    55: "#X509ERR_DN_MISMATCH - a certificate's issuer DN is not the "
        "next certificate's subject DN (the chain is broken)",
    56: "#X509ERR_BAD_SERVER_NAME - the expected server name is not in "
        "the certificate",
    58: "#X509ERR_NOT_CA - a certificate in the path is not a CA",
    60: "#X509ERR_WEAK_PUBLIC_KEY - the public key is below the "
        "configured minimum",
    62: "#X509ERR_NOT_TRUSTED - the chain reached no configured trust "
        "anchor",
    199: "#X509ERR_GUARD - the run guard tripped; the bytecode did not "
         "terminate (this should never fire)",
    200: "#X509ERR_SEAM - the signature-verify seam is not linked "
         "(#X509_SIG_LINKED = 0, or an unlinked half)",
}


def verdict(code):
    if code in VERDICT_NAMES:
        return "%d (%s)" % (code, VERDICT_NAMES[code])
    return ("%d (0x%016X at full width) - NOT A VERDICT CODE THIS ENGINE "
            "DEFINES; check that the harness stored the field with PokeI "
            "and that the run reached end_chain" % (code, code & (2**64 - 1)))


# =====================================================================
#  THE HARNESS
# =====================================================================
#  It reads a script of jobs out of memory at #H_SCRIPT, runs each one,
#  and writes a fixed 32-byte record per job at #H_RESULT.  The
#  certificate, DN, key and server-name bytes all live in one flat area
#  at #H_DATA and the script carries OFFSETS into it, so adding a case
#  never changes this text.
#
#  SCRIPT RECORD - 256 bytes, fixed stride:
#     +0   op        u32   0 end / 1 validate / 2 cell probe
#     +4   ncerts    u32
#     +8   nanchors  u32
#     +12  srvOff    u32
#     +16  srvLen    i64   signed; < 0 means "no server name expected"
#     +24  unixTime  i64   signed; 64 BITS, because 2099 does not fit 32
#     +32  certOff[4]  u32 x4        +48  certLen[4]  u32 x4
#     +64  ancIsCA[4]  u32 x4        +80  ancType[4]  u32 x4  (1 RSA, 2 EC)
#     +96  ancCurve[4] u32 x4        +112 ancDnOff[4] u32 x4
#     +128 ancDnLen[4] u32 x4        +144 ancAOff[4]  u32 x4  (n / q)
#     +160 ancALen[4]  u32 x4        +176 ancBOff[4]  u32 x4  (e)
#     +192 ancBLen[4]  u32 x4
#
#  RESULT RECORD - 32 bytes, FOUR 64-BIT FIELDS:
#     +0  s0   the verdict code, or the probed cell
#     +8   s1  the end-entity key type (0 none / 1 RSA / 2 EC), or the
#              probe's host-side value
#     +16  s2  spare      +24  s3  spare
# =====================================================================
HARNESS = r'''
; ======================================================================
;  xharness.pi4 - GENERATED BY tools/a64/a64_x509_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
; ======================================================================
EnableExplicit
#X509_SIG_LINKED = __LINKED__
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "RaspberryPi4/Lib/t0vm.pi4"
XIncludeFile "Anvil/Core/sha256.pbi"
__SIGINC__
XIncludeFile "__BLOB__"
XIncludeFile "__X509__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000
#H_DATA   = $0B000000

; THE CALLER'S ARRAY-OF-CELLS.  `.i` IS DELIBERATE AND IT IS THE
; CONTRACT x509.pi4's header states: X509ValidateChain walks these with
; a #X_CELL (eight-byte) stride and reads each entry with PeekI, which
; reads eight.  Declaring them `.l` or `.n` compiles and is wrong, which
; is mutation M2.
Global Dim gC.i[8]
Global Dim gL.i[8]

Procedure.i Main()
  Define p.i
  Define q.i
  Define op.i
  Define ncerts.i
  Define nanc.i
  Define srvOff.i
  Define srvLen.i
  Define utime.i
  Define j.i
  Define s0.i
  Define s1.i
  Define aIsCA.i
  Define aType.i
  Define aCurve.i
  Define aDn.i
  Define aDnLen.i
  Define aA.i
  Define aALen.i
  Define aB.i
  Define aBLen.i

  p = #H_SCRIPT
  q = #H_RESULT
__ECDSAINIT__
  Repeat
    op = PeekN(p)
    If op = 0
      Break
    EndIf
    s0 = 0
    s1 = 0

    If op = 1
      ncerts = PeekN(p + 4)
      nanc   = PeekN(p + 8)
      srvOff = PeekN(p + 12)
      srvLen = PeekI(p + 16)
      utime  = PeekI(p + 24)

      X509ResetAnchors()
      j = 0
      While j < nanc
        aIsCA  = PeekN(p + 64 + (j << 2))
        aType  = PeekN(p + 80 + (j << 2))
        aCurve = PeekN(p + 96 + (j << 2))
        aDn    = #H_DATA + PeekN(p + 112 + (j << 2))
        aDnLen = PeekN(p + 128 + (j << 2))
        aA     = #H_DATA + PeekN(p + 144 + (j << 2))
        aALen  = PeekN(p + 160 + (j << 2))
        aB     = #H_DATA + PeekN(p + 176 + (j << 2))
        aBLen  = PeekN(p + 192 + (j << 2))
        If aType = 1
          X509AddAnchorRSA(aIsCA, aDn, aDnLen, aA, aALen, aB, aBLen)
        Else
          X509AddAnchorEC(aIsCA, aDn, aDnLen, aCurve, aA, aALen)
        EndIf
        j = j + 1
      Wend

      j = 0
      While j < ncerts
        gC[j] = #H_DATA + PeekN(p + 32 + (j << 2))
        gL[j] = PeekN(p + 48 + (j << 2))
        j = j + 1
      Wend

      If srvLen < 0
        s0 = X509ValidateChain(@gC, @gL, ncerts, 0, -1, utime)
      Else
        s0 = X509ValidateChain(@gC, @gL, ncerts, #H_DATA + srvOff, srvLen, utime)
      EndIf
      s1 = X509EePkeyType

    ElseIf op = 2
      ; THE CELL PROBE.  Drive XnMem's get32 native the way the VM does
      ; and read the pushed cell back.  A T0 cell is the SIGN-EXTENDED
      ; int32, so $FFFFFFFF in the context RAM must arrive as -1 and
      ; never as $00000000FFFFFFFF; the host-side Xr32 of the same four
      ; bytes must be the POSITIVE 4294967295, because that is what a
      ; 64-bit register makes of `<< 24` and it is the right answer for
      ; an unsigned field.  Both are checked at full width.
      t0_dp = 0
      XrSet32(#X_cert_length, $FFFFFFFF)
      T0Push(#X_cert_length)
      XnMem(#T0N_get32)
      s0 = T0Pop()
      s1 = Xr32(#X_cert_length)
    EndIf

    PokeI(q, s0)
    PokeI(q + 8, s1)
    PokeI(q + 16, 0)
    PokeI(q + 24, 0)

    p = p + 256
    q = q + 32
  ForEver

  UartWriteStr("xharness done")
  ProcedureReturn 0
EndProcedure
'''

# The seam-linked half.  RsaVrfy is supplied here, answering "not
# linked" (-1) exactly as x509.pi4's own compiled-out stub would, for
# the reason the module header records: rsa.pi4's RsaVrfy takes FIVE
# arguments because the A64 backend passes eight and the seam declares
# nine.  This is what ecdsaX509Proof.pico2 does too, and it is why every
# RSA chain in mode B still reports #X509ERR_SEAM (200).
SIGINC_LINKED = '''XIncludeFile "RaspberryPi4/Lib/bignum.pi4"
XIncludeFile "RaspberryPi4/Lib/ec256.pi4"
XIncludeFile "RaspberryPi4/Lib/ecdsa.pi4"

; The RSA half of the seam, unlinked in this image. -1 is exactly what
; x509.pi4's compiled-out stub returns and it becomes the loud
; #X509ERR_SEAM (200) at the caller - never an accept.
;
; NOTE THE SHAPE: five arguments plus RsaSetPubKey, not the nine the
; .pico2 proof writes. That is not a convenience - this backend passes
; EIGHT arguments and refuses a ninth with a FRONTEND FATAL ERROR, so
; the nine-argument spelling does not exist on this part, in the
; library or in a local stub.
Procedure RsaSetPubKey(nPtr.i, nLen.i, ePtr.i, eLen.i)
  nPtr = 0 : nLen = 0 : ePtr = 0 : eLen = 0
EndProcedure
Procedure.i RsaVrfy(sigAddr.i, sigLen.i, hashOidAddr.i, hashLen.i, outAddr.i)
  ProcedureReturn -1
EndProcedure
'''

# Mode C: BOTH halves of the seam, which is an image no 32-bit family
# can build.  rsa.pi4's RsaVrfy is the five-argument certificate-seam
# entry point and rsa.pi4 exports RsaSetPubKey, so the split x509.pi4
# had to make for the eight-argument backend is exactly the shape this
# module already speaks.  Nothing is stubbed here.
SIGINC_FULL = '''XIncludeFile "RaspberryPi4/Lib/bignum.pi4"
XIncludeFile "RaspberryPi4/Lib/ec256.pi4"
XIncludeFile "RaspberryPi4/Lib/ecdsa.pi4"
XIncludeFile "RaspberryPi4/Lib/rsa.pi4"
'''


# =====================================================================
#  THE BLOB IS LIFTED DATA, SO THE LIFT IS CHECKED
# =====================================================================
def _blob_sections(text):
    out = {}
    for label in ("code", "data", "caddr", "opmap"):
        m = re.search(r"t0_x509_blob_%s:\n((?:\s*Data\.a[^\n]*\n)+)"
                      % label, text)
        if not m:
            raise SystemExit(
                "The section t0_x509_blob_%s was not found in %s; check that "
                "the file is still a tools/t0gen.py blob." % (label, BLOB_A64))
        out[label] = [int(x) for x in re.findall(r"\d+", m.group(1))]
    return out


def _blob_scalar(text, pattern, what):
    m = re.search(pattern, text, re.M)
    if not m:
        raise SystemExit("%s was not found in %s; check that the file is "
                         "still a tools/t0gen.py blob." % (what, BLOB_A64))
    return [int(x) for x in m.groups()]


def check_blob():
    """x509_blob.pi4 must be a consistent tools/t0gen.py --native-ram lift,
    and, when the BearSSL source is available, THE lift of x509_minimal.c.

    A drift here is a different bytecode program wearing the same name.
    Returns (description of what was proven, number of data bytes)."""
    g = _import(ROOT / "tools" / "t0gen.py", "t0gen")
    text = BLOB_A64.read_text(encoding="utf-8").replace("\r\n", "\n")
    sec = _blob_sections(text)
    interp, = _blob_scalar(text, r"^#T0_X509_INTERP\s*=\s*(\d+)",
                           "#T0_X509_INTERP")
    entry, = _blob_scalar(text, r"^#T0_X509_ENTRY\s*=\s*(\d+)",
                          "#T0_X509_ENTRY")
    h_interp, h_entry, h_words = _blob_scalar(
        text, r"T0_INTERPRETED = (\d+)\s+entry slot = (\d+)\s+"
        r"interpreted words = (\d+)", "The header's T0_INTERPRETED line")
    h_code, h_data, h_nat = _blob_scalar(
        text, r"code (\d+) bytes\s+data (\d+) bytes\s+natives (\d+)",
        "The header's code/data/natives line")
    natives = [(nm, int(i)) for nm, i in
               re.findall(r"^#T0N_(\w+)\s*=\s*(\d+)", text, re.M)]

    bad = []
    if (h_interp, h_entry) != (interp, entry):
        bad.append("the header says interp %d entry %d, the constants say "
                   "%d and %d" % (h_interp, h_entry, interp, entry))
    if len(sec["code"]) != h_code or len(sec["data"]) != h_data:
        bad.append("the header says code %d / data %d bytes and the sections "
                   "hold %d / %d" % (h_code, h_data, len(sec["code"]),
                                     len(sec["data"])))
    if len(sec["caddr"]) != 2 * h_words:
        bad.append("the header says %d interpreted words and caddr holds %d "
                   "bytes" % (h_words, len(sec["caddr"])))
    if len(sec["opmap"]) != interp:
        bad.append("the opmap has %d entries and T0_INTERPRETED is %d"
                   % (len(sec["opmap"]), interp))
    if any(sec["opmap"][:7]):
        bad.append("the seven control opcodes must map to 0")
    # --native-ram: the six context-memory words are natives, not generic.
    canon = {v for k, v in g.GENERIC.items() if k not in g.MEM_WORDS}
    nid = 0
    for k, v in enumerate(sec["opmap"][7:], start=7):
        if v >= g.NATIVE_BASE:
            if v != g.NATIVE_BASE + nid:
                bad.append("opcode %d maps to native %d, expected %d"
                           % (k, v - g.NATIVE_BASE, nid))
            nid += 1
        elif v not in canon:
            bad.append("opcode %d maps to %d, which is not a canonical id "
                       "for a --native-ram lift" % (k, v))
    if [i for _, i in natives] != list(range(nid)) or len(natives) != h_nat:
        bad.append("the #T0N_ constants number %s, the header says %d natives "
                   "and the opmap uses %d" % ([i for _, i in natives], h_nat,
                                              nid))
    if not (interp <= entry < interp + h_words):
        bad.append("entry slot %d is outside the interpreted words %d..%d"
                   % (entry, interp, interp + h_words - 1))
    if bad:
        raise SystemExit(
            "%s is not a consistent tools/t0gen.py lift:\n  %s\nRegenerate "
            "it from x509_minimal.c; do not hand-edit it."
            % (BLOB_A64, "\n  ".join(bad)))
    proven = ("x509_blob.pi4 is a consistent --native-ram lift (%d words, "
              "%d natives)" % (h_words, nid))

    if not BEARSSL_SRC:
        return (proven + ". The byte-for-byte regeneration from BearSSL's "
                "src/x509/x509_minimal.c was SKIPPED because BEARSSL_SRC is "
                "not set and BearSSL's sources are not part of this tree; to "
                "enable it, set BEARSSL_SRC to the root of a BearSSL checkout.",
                len(sec["code"]))

    csrc = pathlib.Path(BEARSSL_SRC) / "src" / "x509" / "x509_minimal.c"
    hsrc = pathlib.Path(BEARSSL_SRC) / "inc" / "bearssl_x509.h"
    for f in (csrc, hsrc):
        if not f.exists():
            raise SystemExit("BEARSSL_SRC is set but %s was not found. Check "
                             "that BEARSSL_SRC names the root of a BearSSL "
                             "checkout." % f)
    # The field map: x509.pi4's own context-RAM layout, plus the named
    # constants the T0 program embeds, taken from BearSSL's header.
    lib = X509.read_text(encoding="utf-8")
    fields = {m.group(1): int(m.group(2)) for m in
              re.finditer(r"^#X_(\w+)\s*=\s*(\d+)", lib, re.M)}
    fields.update({m.group(1): int(m.group(2)) for m in
                   re.finditer(r"#define\s+(BR_\w+)\s+(\d+)\b",
                               hsrc.read_text(errors="replace"))})
    ctext = g.slurp(str(csrc))
    n_interp = g.get_define(ctext, "T0_INTERPRETED")
    c_entry = g.get_entry_slot(ctext)
    seen = set()
    data = g.parse_bytes(g.array_body(
        ctext, "static const unsigned char t0_datablock[]"), fields, seen)
    code = g.parse_bytes(g.array_body(
        ctext, "static const unsigned char t0_codeblock[]"), fields, seen)
    pairs = []
    for v in g.parse_caddr(ctext):
        pairs += [v & 0xFF, (v >> 8) & 0xFF]
    names = g.opcode_names(ctext, n_interp)
    generic = {k: v for k, v in g.GENERIC.items() if k not in g.MEM_WORDS}
    opmap, nat = [0] * n_interp, []
    for k in range(7, n_interp):
        nm = names.get(k)
        if nm is None:
            raise SystemExit("opcode %d has no name comment in %s" % (k, csrc))
        if nm in generic:
            opmap[k] = generic[nm]
        else:
            opmap[k] = g.NATIVE_BASE + len(nat)
            nat.append(g.sanitize(nm))
    got = {"code": code, "data": data, "caddr": pairs, "opmap": opmap}
    for label in ("code", "data", "caddr", "opmap"):
        if got[label] != sec[label]:
            raise SystemExit(
                "The X.509 bytecode regenerated from %s does not match the %s "
                "section of %s. Check the #X_ context-RAM layout in "
                "x509.pi4 against the one the blob was lifted with; a moved "
                "field moves the offsets embedded in the code block."
                % (csrc, label, BLOB_A64))
    if (n_interp, c_entry) != (interp, entry) or nat != [nm for nm, _ in natives]:
        raise SystemExit(
            "The regenerated X.509 program's interp/entry/native list does "
            "not match %s; regenerate the blob from %s." % (BLOB_A64, csrc))
    return (proven + "; regenerated from %s and byte-identical" % csrc,
            len(sec["code"]))


def check_blob_identity():
    """The name other tools call. Runs check_blob(), raising SystemExit
    with a full sentence on any inconsistency or regeneration mismatch,
    and returns the number of code bytes proven."""
    _proven, n = check_blob()
    return n


# =====================================================================
#  THE CASES, PARSED OUT OF THE TWO GENERATORS
# =====================================================================
def _import(path, name):
    if not path.exists():
        raise SystemExit(
            "%s is missing.\nThis gate deliberately has no certificates and "
            "no expectations of its own: it reads the very functions that "
            "emit the Pico proofs, so 'the Pi 4 runs the same chains' is a "
            "fact about the source rather than a claim about two lists."
            % path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RE_ANC_EC = re.compile(
    r"X509AddAnchorEC\((\d+),\s*\?(\w+),\s*(\d+),\s*(\d+),\s*\?(\w+),\s*(\d+)\)")
RE_ANC_RSA = re.compile(
    r"X509AddAnchorRSA\((\d+),\s*\?(\w+),\s*(\d+),\s*\?(\w+),\s*(\d+),"
    r"\s*\?(\w+),\s*(\d+)\)")
RE_CERT = re.compile(r"gC\[(\d+)\]\s*=\s*\?(\w+)\s*:\s*gL\[(\d+)\]\s*=\s*(\d+)")
RE_RUN = re.compile(
    r"X509ValidateChain\(@gC,\s*@gL,\s*(\d+),\s*(\?\w+|0),\s*(-?\d+),\s*(\d+)\)")
RE_CHECK = re.compile(r"Check\(r,\s*(\d+)\)")


def parse_cases(body, source):
    """Turn a generated proof BODY into case dicts.

    THE GENERATED SOURCE IS THE SPECIFICATION.  Parsing it, rather than
    re-deriving the same list here, is what makes this gate and the Pico
    gates provably the same corpus: a case added to the generator shows
    up here on the next run, and a case whose expected verdict is
    changed there changes here.
    """
    cases = []
    cur = None
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("X509ResetAnchors()"):
            cur = {"anchors": [], "certs": [], "server": None,
                   "srvlen": -1, "time": None, "expect": None}
            continue
        if cur is None:
            continue
        m = RE_ANC_EC.search(s)
        if m:
            cur["anchors"].append(
                dict(isCA=int(m.group(1)), type=2, dn=m.group(2),
                     dnlen=int(m.group(3)), curve=int(m.group(4)),
                     a=m.group(5), alen=int(m.group(6)), b=None, blen=0))
            continue
        m = RE_ANC_RSA.search(s)
        if m:
            cur["anchors"].append(
                dict(isCA=int(m.group(1)), type=1, dn=m.group(2),
                     dnlen=int(m.group(3)), curve=0,
                     a=m.group(4), alen=int(m.group(5)),
                     b=m.group(6), blen=int(m.group(7))))
            continue
        m = RE_CERT.search(s)
        if m:
            if int(m.group(1)) != len(cur["certs"]):
                raise SystemExit(
                    "%s emits its chain slots out of order at %r - this "
                    "parser assumes gC[0], gC[1], ... in sequence" % (source, s))
            cur["certs"].append((m.group(2), int(m.group(4))))
            continue
        m = RE_RUN.search(s)
        if m:
            if int(m.group(1)) != len(cur["certs"]):
                raise SystemExit("%s: chain count %s but %d gC slots at %r"
                                 % (source, m.group(1), len(cur["certs"]), s))
            cur["server"] = None if m.group(2) == "0" else m.group(2)[1:]
            cur["srvlen"] = int(m.group(3))
            cur["time"] = int(m.group(4))
            continue
        m = RE_CHECK.search(s)
        if m and cur.get("time") is not None:
            cur["expect"] = int(m.group(1))
            cases.append(cur)
            cur = None
    if not cases:
        raise SystemExit(
            "no cases were parsed out of %s. The generator's emitted shape "
            "has changed and this gate reads it BY SHAPE; update the two "
            "together, not around each other." % source)
    return cases


def name_cases(cases, prefix):
    """A stable, readable label per case, from what the case actually is."""
    out = []
    seen = {}
    for c in cases:
        certs = "+".join(l for l, _ in c["certs"]) or "no-cert"
        anc = "-".join(("CA" if a["isCA"] else "DT") +
                       ("RSA" if a["type"] == 1 else "EC")
                       for a in c["anchors"]) or "no-anchor"
        srv = c["server"] or "noname"
        base = "%s %s / %s / %s / t=%d" % (prefix, certs, anc, srv, c["time"])
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append(base if n == 0 else "%s #%d" % (base, n + 1))
    return out


def load_modeA():
    """The seam-stubbed corpus, out of tools/x509_proof_gen.py."""
    g = _import(ROOT / "tools" / "x509_proof_gen.py", "x509_proof_gen")
    for n in ("build_body", "CERTS", "BLOBS"):
        if not hasattr(g, n):
            raise SystemExit(
                "tools/x509_proof_gen.py no longer defines %r; this gate "
                "reads it BY NAME and must be updated WITH it, not around "
                "it" % n)
    blobs = dict(g.CERTS)
    blobs.update(g.BLOBS)
    cases = parse_cases(g.build_body(), "tools/x509_proof_gen.py")
    return cases, blobs


def load_modeB():
    """The seam-linked corpus, out of tools/ecdsa_x509_gen.py.

    Its build() takes the DataSection that tools/x509_proof_gen.py
    emits for the M12 proof, lifted out of that generated source text, so
    the two corpora cannot drift apart - and neither can this gate."""
    g = _import(ROOT / "tools" / "ecdsa_x509_gen.py", "ecdsa_x509_gen")
    for n in ("build", "lift_datasection_text", "corrupt_last_sig_byte"):
        if not hasattr(g, n):
            raise SystemExit(
                "tools/ecdsa_x509_gen.py no longer defines %r; this gate "
                "reads it BY NAME and must be updated WITH it" % n)
    m12 = _import(ROOT / "tools" / "x509_proof_gen.py", "x509_proof_gen")
    _ds, blobs = g.lift_datasection_text(m12.build_body())
    body, extra = g.build("pi4", blobs)
    blobs = {k: bytes(v) for k, v in blobs.items()}
    blobs.update({k: bytes(v) for k, v in extra.items()})
    # main() appends this one after build(); it is a nine-byte ASCII
    # host name, not a certificate.
    blobs["srv_localhost"] = b"localhost"
    cases = parse_cases(body, "tools/ecdsa_x509_gen.py")
    return cases, blobs, g


def load_modeC():
    """The same corpus with BOTH halves of the seam linked.

    TWO THINGS CHANGE FROM MODE B, and both are argued rather than
    assumed:

      * every case the generator expects to answer #X509ERR_SEAM (200)
        is expected to answer #X509ERR_OK (32) here.  200 is what that
        generator's image MEANS by "the RSA half of this build is not
        linked" - it says so in its own header - and in this image it
        is.  Overriding an imported expectation is exactly the kind of
        thing that hides a bug, so it is done by RULE (200 -> 32, for
        every case, no exceptions and no hand-picking) and it is
        checked: if there is no such case, or if a case that was
        expected to reach the seam does not now validate, the gate goes
        red.
      * two RSA chains are TAMPERED, with the very function
        tools/ecdsa_x509_gen.py uses to tamper the EC ones, so the RSA
        half is proven BY NAME and not merely by a green OK.  No
        certificate is transcribed to do it.

        AND THE TWO TAMPERS DO NOT EXPECT THE SAME CODE, which is the
        whole point of checking the name.  Corrupting the END-ENTITY's
        signature is BAD_SIGNATURE (52): that signature is verified
        explicitly against the issuer's key.  Corrupting the
        INTERMEDIATE's is NOT_TRUSTED (62): the intermediate-versus-
        anchor step is the TRUST decision, and xm_end_chain sets
        NOT_TRUSTED whenever the walk finishes without an anchor
        validating, which is exactly what a corrupt CA signature
        causes.  Both are refusals and the chain is rejected either
        way - this failed CLOSED throughout - but the reason matters to
        whoever reads the diagnostic.

        THIS WAS WRONG HERE UNTIL 2026-09-05 AND THE BOARD FOUND IT.
        Both tampers expected 52; the Pi 4's on-board self-test
        answered 62 for the intermediate one and the board was right.
        The identical correction had already been made for the EC pair
        - on the RP2350 copy, and in tools/ecdsa_x509_gen.py and the
        other two copies - and the RSA pair was missed every time, because THIS PART IS THE ONLY
        FAMILY THAT CAN LINK THE RSA HALF OF THE SEAM AT ALL.  Mode C
        exists nowhere else, so no 32-bit family has ever executed this
        case.  A gate whose expectation is wrong is a gate that will
        one day certify the wrong answer.
    """
    cases, blobs, g = load_modeB()
    rsa_chain = None
    for c in cases:
        if c["expect"] == 200:
            rsa_chain = c
    if rsa_chain is None:
        raise SystemExit(
            "tools/ecdsa_x509_gen.py no longer emits a case that reaches "
            "#X509ERR_SEAM (200), so there is nothing for mode C to prove: "
            "mode C exists precisely to link the half that image leaves "
            "stubbed. Update the two together.")
    if len(rsa_chain["certs"]) != 2 or rsa_chain["anchors"][0]["type"] != 1:
        raise SystemExit(
            "the case that reaches the seam in tools/ecdsa_x509_gen.py is no "
            "longer a two-certificate RSA chain; mode C's tamper cases are "
            "built from it and must be rechecked by a human.")
    out = []
    for c in cases:
        c = dict(c)
        if c["expect"] == 200:
            c["expect"] = 32
        out.append(c)
    # slot 0 is the END-ENTITY and slot 1 the INTERMEDIATE, and they
    # answer different codes - see the docstring. Written as a table so
    # the difference is visible at the assignment rather than buried in
    # a conditional.
    TAMPER_EXPECT = {0: 52, 1: 62}
    for slot in (0, 1):
        lab = rsa_chain["certs"][slot][0]
        bad = lab + "_badsig"
        blobs[bad] = bytes(g.corrupt_last_sig_byte(blobs[lab]))
        c = dict(rsa_chain)
        c["certs"] = list(rsa_chain["certs"])
        c["certs"][slot] = (bad, rsa_chain["certs"][slot][1])
        c["expect"] = TAMPER_EXPECT[slot]
        out.append(c)
    return out, blobs


# =====================================================================
#  BUILDING THE SCRIPT
# =====================================================================
class Script:
    """The job list plus the flat data area the offsets point into."""

    def __init__(self):
        self.buf = bytearray()
        self.data = bytearray()
        self._at = {}
        self.jobs = []          # (label, expect_s0, expect_s1_or_None)
        self.records = []

    def blob(self, label, byts):
        if label not in self._at:
            self._at[label] = len(self.data)
            self.data += byts
            self.data += b"\x00" * ((-len(self.data)) % 8)
        return self._at[label]

    def _emit(self, label, rec, e0, e1):
        if len(rec) != JOB_STRIDE:
            raise SystemExit("a script record is %d bytes, not %d"
                             % (len(rec), JOB_STRIDE))
        self.jobs.append((label, e0, e1))
        self.records.append(bytes(rec))
        self.buf += rec

    def add_validate(self, label, case, blobs, expect_keytype=None):
        r = bytearray(JOB_STRIDE)
        certs, anchors = case["certs"], case["anchors"]
        if len(certs) > MAX_CERTS:
            raise SystemExit("%s has %d certificates and the script record "
                             "holds %d" % (label, len(certs), MAX_CERTS))
        if len(anchors) > MAX_ANCHORS:
            raise SystemExit("%s has %d anchors and the script record holds "
                             "%d" % (label, len(anchors), MAX_ANCHORS))

        def u32(off, v):
            struct.pack_into("<I", r, off, v & 0xFFFFFFFF)

        def i64(off, v):
            struct.pack_into("<q", r, off, v)

        u32(0, OP_VALIDATE)
        u32(4, len(certs))
        u32(8, len(anchors))
        srv = case["server"]
        u32(12, self.blob(srv, blobs[srv]) if srv else 0)
        i64(16, case["srvlen"])
        i64(24, case["time"])
        for k, (lab, ln) in enumerate(certs):
            if lab not in blobs:
                raise SystemExit("%s names a blob %r the generator did not "
                                 "hand over" % (label, lab))
            if len(blobs[lab]) != ln:
                raise SystemExit(
                    "%s: the generator says %s is %d bytes and its own blob "
                    "is %d - the two halves of that generator disagree"
                    % (label, lab, ln, len(blobs[lab])))
            u32(32 + 4 * k, self.blob(lab, blobs[lab]))
            u32(48 + 4 * k, ln)
        for k, a in enumerate(anchors):
            u32(64 + 4 * k, a["isCA"])
            u32(80 + 4 * k, a["type"])
            u32(96 + 4 * k, a["curve"])
            u32(112 + 4 * k, self.blob(a["dn"], blobs[a["dn"]]))
            u32(128 + 4 * k, a["dnlen"])
            u32(144 + 4 * k, self.blob(a["a"], blobs[a["a"]]))
            u32(160 + 4 * k, a["alen"])
            if a["b"]:
                u32(176 + 4 * k, self.blob(a["b"], blobs[a["b"]]))
                u32(192 + 4 * k, a["blen"])
        self._emit(label, r, case["expect"], expect_keytype)

    def add_cellprobe(self, label):
        r = bytearray(JOB_STRIDE)
        struct.pack_into("<I", r, 0, OP_CELLPROBE)
        # -1 as the CELL (sign-extended int32), 4294967295 as the host
        # value.  Both at full 64-bit width, which is the whole point.
        self._emit(label, r, -1 & (2**64 - 1), 0xFFFFFFFF)

    def done(self):
        return bytes(self.buf) + b"\x00" * JOB_STRIDE

    def __len__(self):
        return len(self.jobs)


def build_script(mode, mutant=False):
    if mode == "A":
        cases, blobs = load_modeA()
    elif mode == "B":
        cases, blobs, _g = load_modeB()
    else:
        cases, blobs = load_modeC()
    if mutant and mode in ("B", "C"):
        # THE MUTANT SUBSET FOR THE LINKED MODES IS ONE TAMPERED CHAIN.
        # A seam-linked case is two ECDSA verifications at roughly 155
        # million model instructions each, and the whole mode is ten of
        # them; running that under every mutation would be the entire
        # cost of the sweep for one mutation's worth of information.
        # The tampered chain is the discriminating case: it is the one
        # that answers #X509ERR_BAD_SIGNATURE only if the verdict of a
        # real verification is being read, so a mutation in the
        # signature path shows up in it.  This mirrors
        # tools/a64/a64_ecdsa_check.py's own mutant subset and its
        # reasoning.
        cases = [c for c in cases if c["expect"] == 52][:1]
        if not cases:
            raise SystemExit(
                "mode %s has no tampered-signature case, so a mutation in "
                "the signature path has nothing to fail against. The "
                "generator stopped emitting one; fix that rather than "
                "letting the sweep run on a corpus that cannot see the "
                "thing it is sweeping." % mode)
    labels = name_cases(cases, mode)
    s = Script()
    for lab, c in zip(labels, cases):
        kt = None
        if c["expect"] == 32:
            # A validated chain must also have handed back the decoded
            # end-entity key.  0 there would mean "OK with no key", which
            # is not a validated chain.
            kt = "nonzero"
        s.add_validate(lab, c, blobs, kt)
    if mode == "A":
        # THIS GATE'S OWN TWO.  Neither contains a certificate.
        empty = {"anchors": [], "certs": [], "server": None, "srvlen": -1,
                 "time": cases[0]["time"], "expect": 35}
        s.add_validate("A empty chain (count = 0)", empty, blobs)
        s.add_cellprobe("A cell probe: get32 across bit 31")
    return s


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def build(mode, x509_include, blob_include, harness_path, img):
    WORK.mkdir(exist_ok=True)
    siginc = {"A": "", "B": SIGINC_LINKED, "C": SIGINC_FULL}[mode]
    src = (HARNESS
           .replace("__LINKED__", "0" if mode == "A" else "1")
           .replace("__SIGINC__", siginc)
           .replace("__ECDSAINIT__", "" if mode == "A" else "  EcdsaInit()")
           .replace("__BLOB__", blob_include)
           .replace("__X509__", x509_include))
    harness_path.write_text(src, encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(harness_path), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)
    return img.stat().st_size


class Runaway(Exception):
    pass


def run_raw(img_bytes, script, data, count, step_limit=STEP_LIMIT):
    """Execute one script under the model.  Returns (records, steps)."""
    from a64_interp import A64
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(img_bytes):
        mem[LOAD + i] = b
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    for i, b in enumerate(data):
        mem[H_DATA + i] = b
    for i in range(count * RESULT_STRIDE):
        mem[H_RESULT + i] = SENTINEL

    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR
    uart = bytearray()

    def load(addr, size):
        if UART_LO <= addr <= UART_HI:
            return 0                       # a PL011 that is never busy
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        if UART_LO <= addr <= UART_HI:
            if addr == UART_DR:
                uart.append(value & 0xFF)
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store

    steps = 0
    while cpu.pc != LOADER_LR:
        cpu.step()
        steps += 1
        if steps > step_limit:
            raise Runaway("the harness never returned (%d model instructions; "
                          "the engine's own run guard is 20,000,000 bytecode "
                          "steps, so this means it is not even reaching that)"
                          "\n%s" % (steps, uart.decode("latin-1")))

    if b"xharness done" not in uart:
        raise SystemExit("the harness returned without finishing its script "
                         "- it never printed its completion line, so some "
                         "job faulted:\n" + uart.decode("latin-1"))

    recs = [bytes(mem.get(H_RESULT + i * RESULT_STRIDE + j, 0)
                  for j in range(RESULT_STRIDE))
            for i in range(count)]
    return recs, steps


def check_shard(script, recs):
    bad = []
    for i, (label, e0, e1) in enumerate(script.jobs):
        rec = recs[i]
        s0, s1, _s2, _s3 = struct.unpack("<QQQQ", rec)
        if rec == bytes([SENTINEL]) * RESULT_STRIDE:
            bad.append("%s: no record was written at all - the harness never "
                       "reached this job" % label)
            continue
        if e0 is not None and s0 != (e0 & (2**64 - 1)):
            bad.append("%s\n    got  %s\n    want %s"
                       % (label, verdict(s0), verdict(e0)))
        if e1 == "nonzero":
            if s1 == 0:
                bad.append("%s: the chain validated but X509EePkeyType is 0 "
                           "- a validated chain must hand back the decoded "
                           "end-entity key (1 = RSA, 2 = EC)" % label)
        elif e1 is not None and s1 != (e1 & (2**64 - 1)):
            bad.append("%s: second field is %d (0x%016X at full width), "
                       "want %d (0x%016X)" % (label, s1, s1, e1, e1))
    return bad


def shard(script, n):
    """Split a Script into n Scripts.  Every job here is independent -
    X509ValidateChain resets the whole context RAM, the anchor table and
    the VM on entry - so unlike the bignum gate there is no state to
    carry into a shard."""
    if n <= 1 or len(script) <= 1:
        return [script]
    buckets = [list(range(len(script)))[i::n] for i in range(n)]
    out = []
    for b in buckets:
        if not b:
            continue
        s = Script()
        s.data = script.data
        for idx in b:
            s._emit(script.jobs[idx][0], script.records[idx],
                    script.jobs[idx][1], script.jobs[idx][2])
        out.append(s)
    return out


def _worker(args):
    img_bytes, blob, data, count, limit = args
    return run_raw(img_bytes, blob, data, count, limit)


def run_all(img, script, jobs=None, quiet=False, limit=STEP_LIMIT):
    img_bytes = img.read_bytes()
    n = jobs or max(1, (os.cpu_count() or 2) - 2)
    shards = shard(script, n)
    if len(shards) == 1:
        recs, steps = run_raw(img_bytes, shards[0].done(), shards[0].data,
                              len(shards[0]), limit)
        return check_shard(shards[0], recs), steps
    if not quiet:
        print("[gate] %d jobs across %d workers" % (len(script), len(shards)),
              file=sys.stderr)
    args = [(img_bytes, s.done(), bytes(s.data), len(s), limit) for s in shards]
    bad, steps = [], 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=len(shards)) as ex:
        for s, (recs, st) in zip(shards, ex.map(_worker, args)):
            bad += check_shard(s, recs)
            steps += st
    return bad, steps


# =====================================================================
#  THE MUTATIONS
# =====================================================================
#  Each is (label, file, mode, find, replace, verdict).  The verdict is
#  what the mutation is EXPECTED to earn:
#
#    "kill"     the corpus must catch it.  A survivor is a hole.
#    a string   an EXPECTED survivor, and the string is the argument for
#               why no known-answer test can see it.  These are NOT
#               deleted: the day one of them starts being caught is the
#               day its argument stopped being true, and that is as loud
#               a failure as an unexpected survivor.
#
#  "harness" as the file mutates the GENERATED harness instead of the
#  library, which is the only way to test a claim this module's header
#  makes about its CALLERS.
#
#  mode "A" runs the seam-stubbed corpus only; "AB" runs the linked one
#  as well, for the mutations that live in the signature path.
# =====================================================================
MUTATIONS = [
    ("M1  the certificate array reverts to a FOUR-byte cell stride "
     "(THE DEFECT THIS PORT FOUND)", "x509", "A",
     "    certAddr = PeekI(certsAddr + i * #X_CELL)\n"
     "    certLen  = PeekI(lensAddr + i * #X_CELL)",
     "    certAddr = PeekI(certsAddr + i * 4)\n"
     "    certLen  = PeekI(lensAddr + i * 4)",
     "kill"),

    ("M2  a caller declares its chain array .l instead of .i",
     "harness", "A",
     "Global Dim gC.i[8]\nGlobal Dim gL.i[8]",
     "Global Dim gC.l[8]\nGlobal Dim gL.l[8]",
     "kill"),

    ("M3  XnMem's get32 pushes a raw Xr32, without T0Norm", "x509", "A",
     "      T0Push(T0Norm(Xr32(a)))",
     "      T0Push(Xr32(a))",
     "kill"),

    ("M4  the end-chain OK test is respelled as the GcmDecrypt mask "
     "(correct on a 32-bit .i, ACCEPTS EVERY REFUSAL here)", "x509", "A",
     "  ; mirror end_chain\n  If xErr = #X509ERR_OK",
     "  ; mirror end_chain\n"
     "  terminal = xErr - #X509ERR_OK\n"
     "  terminal = ((terminal | (0 - terminal)) >> 31) ! $FFFFFFFF\n"
     "  If terminal",
     "kill"),

    ("M5  X509RunOneCert's terminal test is respelled as a >> 31 sign "
     "test", "x509", "A",
     "      X509Native(t0_native_id)\n      If xErr <> 0",
     "      X509Native(t0_native_id)\n"
     "      If ((xErr | (0 - xErr)) >> 31) & 1",
     "xErr is a small POSITIVE verdict code, and (x | -x) of any "
     "non-zero value is negative at ANY width, so an arithmetic >> 31 "
     "still delivers a set bit to bit 0 and the & 1 still reads 1. Two "
     "wrongs that were never wrong: unlike the end-chain mask of M4, "
     "nothing here is XOR-ed against a 32-bit all-ones, so no set bits "
     "are left stranded above bit 31. It is in the table because that "
     "is the reasoning the header claims for SHAPE 5, and this is where "
     "the claim is measured rather than asserted. It starts being "
     "caught the day xErr can be exactly 2^31, or the day >> stops "
     "being arithmetic."),

    ("M6  X509VerifySig's EC branch treats a FAILED verify as success",
     "x509", "AB",
     "    If r = 0\n      ProcedureReturn #X509ERR_BAD_SIGNATURE\n    EndIf\n"
     "    ProcedureReturn 0\n  EndIf\n  ProcedureReturn #X509ERR_UNSUPPORTED",
     "    ProcedureReturn 0\n  EndIf\n  ProcedureReturn #X509ERR_UNSUPPORTED",
     "kill"),

    ("M7  X509VerifySig's EC branch drops the 'seam not linked' test",
     "x509", "A",
     "    r = EcdsaVrfy(keyN, @xTbsHash, hashLen, keyE, keyElen, sigAddr, sigLen)\n"
     "    If r < 0\n      ProcedureReturn #X509ERR_SEAM\n    EndIf\n",
     "    r = EcdsaVrfy(keyN, @xTbsHash, hashLen, keyE, keyElen, sigAddr, sigLen)\n",
     "kill"),

    ("M8  Xr32 drops its top byte", "x509", "A",
     "  ProcedureReturn (xRam[a] & 255) | ((xRam[a + 1] & 255) << 8) | "
     "((xRam[a + 2] & 255) << 16) | ((xRam[a + 3] & 255) << 24)",
     "  ProcedureReturn (xRam[a] & 255) | ((xRam[a + 1] & 255) << 8) | "
     "((xRam[a + 2] & 255) << 16)",
     "kill"),

    ("M9  Xr16 drops its high byte", "x509", "A",
     "  ProcedureReturn (xRam[a] & 255) | ((xRam[a + 1] & 255) << 8)\n"
     "EndProcedure\nProcedure XrSet16",
     "  ProcedureReturn (xRam[a] & 255)\n"
     "EndProcedure\nProcedure XrSet16",
     "kill"),

    ("M10 XramEq answers 'equal' for everything", "x509", "A",
     "Procedure.i XramEq(p1.i, p2.i, len.i)\n  Protected i.i\n  i = 0",
     "Procedure.i XramEq(p1.i, p2.i, len.i)\n  Protected i.i\n  "
     "ProcedureReturn 1\n  i = 0",
     "kill"),

    ("M11 check-validity-range's notBefore and notAfter answers are "
     "swapped", "x509", "A",
     "      If xValidDays < nbd Or (xValidDays = nbd And xValidSecs < nbs)\n"
     "        r = -1\n"
     "      ElseIf xValidDays > nad Or (xValidDays = nad And xValidSecs > nas)\n"
     "        r = 1",
     "      If xValidDays < nbd Or (xValidDays = nbd And xValidSecs < nbs)\n"
     "        r = 1\n"
     "      ElseIf xValidDays > nad Or (xValidDays = nad And xValidSecs > nas)\n"
     "        r = -1",
     "THE ENGINE HAS ONE CODE FOR BOTH SIDES. BearSSL's x509_minimal "
     "reports #X509ERR_EXPIRED (54) whether the date is before "
     "notBefore or after notAfter, so swapping the two answers is "
     "invisible to any test that can only read the verdict - and a "
     "verdict is all X.509 offers. Seeing this would need a code the "
     "standard does not define. It stays in the table because the same "
     "swap would be caught the day a caller is given a reason string, "
     "and because it is the honest record that the two date cases "
     "distinguish the BRANCH but not the ANSWER."),

    ("M12 match-server-name drops its case folding", "x509", "A",
     "          If c1 >= 65 And c1 <= 90\n            c1 = c1 + 32\n"
     "          EndIf\n          If c2 >= 65 And c2 <= 90\n"
     "            c2 = c2 + 32\n          EndIf\n          If c1 <> c2\n"
     "            ok = 0\n            Break\n          EndIf\n"
     "          i = i + 1\n        Wend\n      EndIf",
     "          If c1 <> c2\n            ok = 0\n            Break\n"
     "          EndIf\n          i = i + 1\n        Wend\n      EndIf",
     "EVERY NAME IN THE CORPUS IS ALREADY LOWER CASE. The BearSSL "
     "sample end-entity certificate carries the SAN 'localhost' and the "
     "two names the proofs check against are 'localhost' and "
     "'wrong.example.com'; folding a string that has nothing to fold "
     "changes nothing, so no known-answer test in this corpus can see "
     "the fold being removed. This is reasoning about the vectors, not "
     "a reproduction, and it is labelled as such - exactly like the CTR "
     "counter wrap in gcm.pi4. It would need a chain whose SAN is "
     "mixed case, which means minting one, which means the corpus is no "
     "longer the captured sample set the four families share."),

    ("M13 the context RAM is no longer cleared between chains",
     "x509", "A",
     "  ; reset the whole context RAM and run state\n"
     "  i = 0\n  While i < #X_RAM_SIZE\n    xRam[i] = 0\n    i = i + 1\n  Wend",
     "  ; reset the whole context RAM and run state\n  i = 0",
     "kill"),

    ("M14 the empty-chain guard accepts count = 0", "x509", "A",
     "  If count <= 0\n    X509Err = #X509ERR_EMPTY_CHAIN",
     "  If count < 0\n    X509Err = #X509ERR_EMPTY_CHAIN",
     "kill"),
]


def mutate_source(idx, which, find, replace, harness_text):
    """Write a mutated COPY into _work/ and return (include, harness).

    THIS NEVER OPENS THE REAL SOURCE FOR WRITING, and every mutation
    gets its OWN filename.  When the A64 GCM sweep let every mutant of
    one file share a name, four of them raced, the compiler read a
    half-written file, and the pool reported four survivors that were
    nothing of the kind.
    """
    WORK.mkdir(exist_ok=True)
    if which == "harness":
        if harness_text.count(find) != 1:
            raise SystemExit("mutation anchor not unique in the harness:\n%r"
                             % find)
        return "RaspberryPi4/Lib/x509.pi4", harness_text.replace(
            find, replace, 1)
    text = X509.read_text(encoding="utf-8").replace("\r\n", "\n")
    if text.count(find) != 1:
        raise SystemExit("mutation anchor found %d times in %s (want 1):\n%r"
                         % (text.count(find), X509.name, find))
    out = WORK / ("mut%02d_x509.pi4" % idx)
    out.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return "_work/" + out.name, harness_text


def run_one_mutation(i, jobs):
    label, which, modes, find, repl, expected = MUTATIONS[i]
    inc, harness_text = mutate_source(i, which, find, repl, HARNESS)
    saved, ok = HARNESS, True
    globals()["HARNESS"] = harness_text
    try:
        for mode in ("A", "B") if modes == "AB" else ("A",):
            img = WORK / ("x509_mut%02d_%s.img" % (i, mode))
            hp = WORK / ("xharness_mut%02d_%s.pi4" % (i, mode))
            try:
                build(mode, inc, "RaspberryPi4/Lib/x509_blob.pi4", hp, img)
            except SystemExit as e:
                print("NOBUILD  %s\n         %s"
                      % (label, str(e).splitlines()[0]))
                return 0
            s = build_script(mode, mutant=True)
            try:
                bad, _ = run_all(img, s, jobs=jobs, quiet=True,
                                 limit=MUTANT_STEP_LIMIT[mode])
            except Runaway as e:
                bad = ["mode %s did not terminate: %s"
                       % (mode, str(e).splitlines()[0])]
            if bad:
                if expected == "kill":
                    print("KILLED   %s\n         first: %s"
                          % (label, IND.join(bad[0].splitlines())))
                    return 0
                print("UNEXPECTED-KILL %s\n         the corpus now catches "
                      "this, so the recorded argument is stale:\n"
                      "         %s\n         first: %s"
                      % (label, expected,
                         IND.join(bad[0].splitlines())))
                return 1
    finally:
        globals()["HARNESS"] = saved
    if expected == "kill":
        print("SURVIVED %s\n         (the corpus was expected to catch this "
              "one)" % label)
        return 1
    print("EXPECTED-SURVIVOR %s" % label)
    return 0


# =====================================================================
#  MAIN
# =====================================================================
def resolve_compiler(requested):
    """Resolve the PureMetal compiler. A named compiler (explicit or
    PMF_COMPILER) is routed through the shared, validating resolver
    (tools/pmf_compiler.py): refuses a missing, retired, or
    untracked/stale executable (forum 977). With nothing named, this
    falls back to tools/build.py's bare-PATH search, unchanged."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    if requested or os.environ.get("PMF_COMPILER"):
        from pmf_compiler import resolve_compiler as _pmf_resolve_compiler  # noqa: E402
        return _pmf_resolve_compiler(requested)
    return anvil_build.find_compiler(requested)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--stub-only", action="store_true",
                    help="mode A only (#X509_SIG_LINKED = 0)")
    ap.add_argument("--linked-only", action="store_true",
                    help="modes B and C only (#X509_SIG_LINKED = 1)")
    ap.add_argument("--mode", choices=["A", "B", "C"], default=None,
                    help="run exactly one mode")
    ap.add_argument("--mutate", action="store_true", help="the mutation sweep")
    ap.add_argument("--mutation", type=int, default=None,
                    help="run ONE mutation by index (used by the pool)")
    ap.add_argument("--jobs", type=int, default=None,
                    help="worker processes (default: cores - 2)")
    args = ap.parse_args(argv)
    globals()["PMFC"] = resolve_compiler(args.compiler)

    print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
    proven, _n = check_blob()
    print("[gate] %s" % proven, file=sys.stderr)

    if args.mutation is not None:
        return run_one_mutation(args.mutation, args.jobs)

    if args.mutate:
        nw = args.jobs or max(1, (os.cpu_count() or 2) - 2)
        print("[gate] %d mutations across %d workers" % (len(MUTATIONS), nw))
        t0 = time.time()
        survivors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=nw) as ex:
            futs = {ex.submit(subprocess.run,
                              [sys.executable, __file__, "--mutation",
                               str(i), "--jobs", "1", "--compiler", PMFC],
                              capture_output=True, text=True,
                              env=BUILD_ENV): i
                    for i in range(len(MUTATIONS))}
            for f in concurrent.futures.as_completed(futs):
                i = futs[f]
                r = f.result()
                sys.stdout.write(r.stdout)
                if r.returncode != 0:
                    sys.stdout.write(r.stderr)
                    survivors.append(MUTATIONS[i][0])
        expected = sum(1 for m in MUTATIONS if m[5] != "kill")
        print("[gate] sweep took %.0f s" % (time.time() - t0))
        if survivors:
            print("MUTATION SWEEP RED: %d unexpected outcome(s):\n  %s"
                  % (len(survivors), "\n  ".join(survivors)))
            return 1
        print("MUTATION SWEEP GREEN: 0 unexpected outcomes of %d "
              "(%d of them are EXPECTED survivors, each with its recorded "
              "argument in the table)" % (len(MUTATIONS), expected))
        return 0

    modes = ["A", "B", "C"]
    if args.stub_only:
        modes = ["A"]
    if args.linked_only:
        modes = ["B", "C"]
    if args.mode:
        modes = [args.mode]

    TITLES = {
        "A": "#X509_SIG_LINKED = 0, the seam STUBBED - a chain that reaches "
             "a signature check must end at #X509ERR_SEAM (200), never at OK",
        "B": "#X509_SIG_LINKED = 1, ecdsa.pi4 LINKED and the RSA half "
             "locally stubbed - the image tools/ecdsa_x509_gen.py describes",
        "C": "#X509_SIG_LINKED = 1, ecdsa.pi4 AND rsa.pi4 LINKED - an image "
             "no 32-bit family can build, because the eight-argument seam "
             "split is what makes RsaVrfy satisfiable",
    }
    rc = 0
    total = 0
    for mode in modes:
        title = TITLES[mode]
        print("\n== MODE %s: %s" % (mode, title))
        s = build_script(mode)
        img = WORK / ("xharness_%s.img" % mode)
        size = build(mode, "RaspberryPi4/Lib/x509.pi4",
                     "RaspberryPi4/Lib/x509_blob.pi4",
                     WORK / ("xharness_%s.pi4" % mode), img)
        print("[gate] image %d bytes, %d jobs, %d bytes of certificate data"
              % (size, len(s), len(s.data)))
        t0 = time.time()
        bad, steps = run_all(img, s, jobs=args.jobs)
        total += steps
        for b in bad:
            print("FAIL: " + b)
        print("[gate] mode %s: %d jobs, %d model instructions, %.0f s"
              % (mode, len(s), steps, time.time() - t0))
        if bad:
            print("X509 GATE RED (mode %s): %d of %d verdicts wrong"
                  % (mode, len(bad), len(s)))
            rc = 1
        else:
            print("mode %s GREEN: %d verdicts, every one BY NAME" % (mode, len(s)))

    if rc:
        return rc
    print("\nX509 GATE GREEN: %s, %d model instructions"
          % (" + ".join("mode " + m for m in modes), total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
