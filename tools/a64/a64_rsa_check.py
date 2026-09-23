#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/rsa.pi4 - RSA signature VERIFY
(PKCS#1 v1.5 and PSS) on AArch64.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  THE VECTORS ARE THE ONES THE PICO GATES ALREADY USE.  They are not
  transcribed here and they are not invented here: this gate IMPORTS
  tools/gen_rsa_vectors.py and calls its record builders in main()'s
  order, so it walks the SAME 23 records that get baked into
  rsaVectors.pico2 / .pico / .unor4 - down to the same fixed RNG seed
  and the same real self-signed RSA-2048 certificate.  One oracle, four
  families.  "The Pi 4 passes the same vectors" is then a fact about
  the source rather than a claim about two lists that were once
  eyeballed.  The generator's emit is already behind an
  `if __name__ == "__main__":` guard, so importing it writes nothing.

  THE OPERATIONS ARE THE ONES rsaSelfTest.pico2 PERFORMS.  Each op below
  mirrors that self-test's calls exactly - RsaPkcs1Vrfy for kind 0,
  RsaVrfy plus a caller-side byte compare for kind 2, RsaPssVrfy for
  kind 1 - so a difference in an answer is a difference in the library
  and not in how it was driven.

  THE NEGATIVES ARE THE POINT.  The imported set already refuses a
  tampered signature, a corrupted pad, a wrong message and a wrong salt
  length.  Eight more negatives are DERIVED from those same records -
  never transcribed, never generated - by re-pointing a good signature
  at the wrong key or the wrong scheme:

    * a valid signature against a DIFFERENT 2048-bit modulus,
      both PKCS#1 and PSS;
    * a PSS signature offered to the PKCS#1 verifier and a PKCS#1
      signature offered to the PSS verifier (scheme confusion);
    * the modulus itself presented as the signature - not a proper
      representative, so the public operation must refuse it;
    * the modulus with its low bit cleared - an EVEN modulus, which
      has no Montgomery m0i and must be refused;
    * a signature one byte short of the modulus length;
    * a DigestInfo-wrapped signature offered in the raw (hashOid = 0)
      mode.

  Plus one free check with no modular arithmetic in it at all: that
  RsaOidSha256() really does build the SHA-256 DigestInfo OID, compared
  against the bytes sliced out of the generator's own DigestInfo prefix.

  AND THE FORGOTTEN SETUP STEP.  RsaSetPubKey is the one procedure this
  family adds, and a setup call the caller must remember is a shape this
  project has been bitten by before (the i2c subcommands that skipped
  HwI2cUp() and then blamed the wiring).  rsa.pi4's header answers the
  objection in prose - "forgetting is safe rather than silent" - so job
  d10 turns the prose into a measurement: with a ZERO key installed all
  three entry points must return 0 AND the recovery buffer must come
  back holding nothing but the 0xA5 sentinel.  It is free, because
  RsaPublic refuses on the length before it decodes anything.

  EVERY VERDICT IS READ AT FULL 64-BIT WIDTH.  The harness stores each
  answer with PokeI and this file unpacks it with "<Q".  That is not
  decoration: the first A64 GCM gate stored its verdict with PokeN, and
  the one mutation it existed to catch survived because the wrong
  value's set bits were all above bit 31 and the low half read back
  clean.  Mutation M2 below is that exact defect planted in
  RsaPssVrfyUnpad - a REJECT that hands back $FFFFFFFF00000000, whose
  low 32 bits are zero - and the sweep watches it die.

  IT RUNS ON ALL CORES.  A 4096-bit public operation is tens of
  millions of model instructions and the whole set is close to a
  billion, which is hours in one process.  The image is built ONCE and
  the job list is sharded across a process pool.  --jobs overrides;
  use it when other work is sharing the machine.

THERE IS NO --timing FLAG, AND THAT IS DELIBERATE

  A signature and a public key are PUBLIC DATA.  There is no secret in
  a verify for a timing channel to carry, and the three 32-bit families
  have no constant-time gate for this module either - their
  constant-time A/B tool is driven for the record layer and the AEAD,
  and rsa appears in its TLS 1.3 harness only as an include, never as
  a measured primitive.  Inventing a constant-time A/B here would measure
  something nobody has claimed and would suggest a property this code
  does not promise: rsa.pi4's padding walk branches on lengths and on
  byte values, on purpose, exactly as the .pico2 copy does.  The part
  of this path that DOES matter for other protocols is the modular
  exponentiation, and it is cycle-equal under
  tools/a64/a64_bignum_check.py --timing.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.  The oracle is a model of the
    instruction set: no caches, no memory system, no clock.
  * That RSA verification is safe against a fault-injected key.  It
    checks answers, not physics.

Run: python tools/a64/a64_rsa_check.py --jobs 6
     python tools/a64/a64_rsa_check.py --quick
     python tools/a64/a64_rsa_check.py --mutate
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import os
import pathlib
import struct
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent

# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN.  A root pinned
# into the file made another gate build a DIFFERENT working copy, with
# that copy's compiler, and print the answer as this tree's.  The tree
# actually read is printed below.
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
# --jobs, remembered for the pools that are not handed it directly.
JOBS_CAP = None
RSA = ROOT / "RaspberryPi4" / "Lib" / "rsa.pi4"
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
H_OUT = 0x0B000000

STEP_LIMIT = 40_000_000_000

SCRIPT_HDR = 36             # nine 32-bit fields
RESULT_STRIDE = 32          # verdict, aux, outlen, spare - all i64
SENTINEL = 0xA5

OP_END, OP_PKCS1, OP_PSS, OP_SEAM, OP_RAW, OP_OID, OP_NOKEY = range(7)


# =====================================================================
#  THE HARNESS
# =====================================================================
#  It reads a script of jobs out of memory at #H_SCRIPT, runs each one,
#  and writes a fixed 32-byte record per job at #H_RESULT plus any
#  produced bytes at #H_OUT.  Every vector is DATA, so adding one never
#  changes this text.
#
#  SCRIPT RECORD - a 36-byte header, then n || e || sig || msg, padded
#  to 4:
#      +0 op  +4 saltLen  +8 hashLen  +12 nLen  +16 eLen
#      +20 sigLen  +24 msgLen  +28 outlen  +32 (spare)
#  op 0 ends the script.
#
#  RESULT RECORD - 32 bytes, FOUR 64-BIT FIELDS:
#      +0  verdict   the library's answer, stored WITHOUT narrowing
#      +8  aux       the caller-side answer where a job has one (the
#                    certificate seam's byte compare)
#      +16 outlen    the byte count written to #H_OUT for this job
#      +24 spare
# =====================================================================
HARNESS = r'''
; ======================================================================
;  rsaharness.pi4 - GENERATED BY tools/a64/a64_rsa_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "Anvil/Core/sha256.pbi"
XIncludeFile "RaspberryPi4/Lib/bignum.pi4"
XIncludeFile "__RSA__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000
#H_OUT    = $0B000000

; THE i15 BUFFERS LIVE INSIDE rsa.pi4 AND ARE DECLARED `.w` THERE.  This
; harness only ever hands the library BYTE STRINGS, which is the whole
; API surface a TLS layer touches, so every buffer here is `.a`.  Shape 1
; of the four-shape audit - an array element is EIGHT bytes on this part
; - therefore lands inside the library, and mutation M0 is exactly that:
; RsaM declared `.i` instead of `.w`.
Global Dim NBuf.a[512]               ; modulus bytes
Global Dim EBuf.a[16]                ; public exponent bytes
Global Dim SigBuf.a[512]             ; signature bytes
Global Dim MsgBuf.a[2048]            ; message (a cert TBS reaches ~530)
Global Dim HashBuf.a[32]             ; SHA-256 of the message
Global Dim RecovBuf.a[64]            ; hash recovered through the seam

; RhSame(pa, pb, n) - 1 when the n bytes match, else 0. This is
; rsaSelfTest's SameBytes: the certificate-seam records compare the
; RECOVERED hash here, the way the chain engine's caller does.
Procedure.i RhSame(pa.i, pb.i, n.i)
  Define i.i
  i = 0
  While i < n
    If (PeekA(pa + i) & 255) <> (PeekA(pb + i) & 255)
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

Procedure RhCopy(dst.i, src.i, n.i)
  Define i.i
  i = 0
  While i < n
    PokeB(dst + i, PeekA(src + i) & 255)
    i = i + 1
  Wend
EndProcedure

; RhFill(dst, n, v) - paint a buffer with a sentinel so "the refusal
; wrote nothing" can be MEASURED rather than assumed. Used by the
; no-key job below and by nothing else.
Procedure RhFill(dst.i, n.i, v.i)
  Define i.i
  i = 0
  While i < n
    PokeB(dst + i, v & 255)
    i = i + 1
  Wend
EndProcedure

Procedure.i Main()
  Define p.i
  Define q.i
  Define o.i
  Define op.i
  Define saltLen.i
  Define hashLen.i
  Define nLen.i
  Define eLen.i
  Define sigLen.i
  Define msgLen.i
  Define outlen.i
  Define bn.i
  Define be.i
  Define bs.i
  Define bm.i
  Define v0.i
  Define v1.i

  Sha256Begin()                      ; warm the K table before the loop

  p = #H_SCRIPT
  q = #H_RESULT
  o = #H_OUT

  Repeat
    op      = PeekN(p)
    saltLen = PeekN(p + 4)
    hashLen = PeekN(p + 8)
    nLen    = PeekN(p + 12)
    eLen    = PeekN(p + 16)
    sigLen  = PeekN(p + 20)
    msgLen  = PeekN(p + 24)
    outlen  = PeekN(p + 28)
    If op = 0
      Break
    EndIf
    bn = p + 36
    be = bn + nLen
    bs = be + eLen
    bm = bs + sigLen

    v0 = 0
    v1 = 0

    If op = 5
      ; OID - no modular arithmetic at all: just the cached
      ; length-prefixed SHA-256 DigestInfo OID, out to the host.
      RhCopy(o, RsaOidSha256(), outlen)
    ElseIf op = 6
      ; NO KEY INSTALLED. RsaSetPubKey is the one procedure this family
      ; adds and it is a SETUP STEP THE CALLER MUST REMEMBER - a known
      ; bug shape: a setup step the caller must remember, remembered by
      ; only some callers. rsa.pi4's header answers it by
      ; ARGUING that forgetting is safe: with nothing installed
      ; RsaKeyNLen is 0 and RsaPublic refuses a zero-length modulus. An
      ; argument in a comment is not a measurement, so this job installs
      ; a ZERO key and requires all three entry points to refuse AND the
      ; recovery buffer to come back untouched.
      ;
      ; It is FREE: RsaPublic returns before it decodes anything, so no
      ; modular exponentiation runs and the job is in every level,
      ; including the mutation sweep's subset.
      RhCopy(@SigBuf, bs, sigLen)
      RhCopy(@MsgBuf, bm, msgLen)
      Sha256Of(@MsgBuf, msgLen, @HashBuf)
      RhFill(@RecovBuf, outlen, $A5)
      RsaSetPubKey(0, 0, 0, 0)
      v0 = RsaVrfy(@SigBuf, sigLen, RsaOidSha256(), hashLen, @RecovBuf)
      ; v1 is the OTHER two entry points added together, so a single
      ; expected 0 covers both. Neither may accept anything.
      v1 = RsaPkcs1Vrfy(@SigBuf, sigLen, RsaOidSha256(), hashLen, @HashBuf)
      v1 = v1 + RsaPssVrfy(@SigBuf, sigLen, @HashBuf, hashLen, saltLen)
      ; The recovered-hash buffer goes out to the host, which compares it
      ; against the sentinel byte for byte - a refusal that returns 0 and
      ; writes anyway fails here rather than passing quietly.
      RhCopy(o, @RecovBuf, outlen)
    Else
      RhCopy(@NBuf, bn, nLen)
      RhCopy(@EBuf, be, eLen)
      RhCopy(@SigBuf, bs, sigLen)
      RhCopy(@MsgBuf, bm, msgLen)
      Sha256Of(@MsgBuf, msgLen, @HashBuf)

      ; INSTALL THE KEY FIRST. On this part the three entry points take
      ; the key from here rather than as four more arguments, because
      ; the AArch64 backend passes eight and they declared nine - see
      ; "THE NINTH ARGUMENT" in rsa.pi4's header. Every job installs its
      ; own, so no job can pass on a stale key to the next.
      RsaSetPubKey(@NBuf, nLen, @EBuf, eLen)

      If op = 1
        ; PKCS#1 v1.5, compare-inside.
        v0 = RsaPkcs1Vrfy(@SigBuf, sigLen, RsaOidSha256(), hashLen, @HashBuf)
        v1 = v0
      ElseIf op = 2
        ; RSA-PSS.
        v0 = RsaPssVrfy(@SigBuf, sigLen, @HashBuf, hashLen, saltLen)
        v1 = v0
      ElseIf op = 3
        ; The certificate seam: recover the signed hash out to the
        ; caller, then compare it here - exactly what the chain engine
        ; does. v0 is RsaVrfy's OWN answer, stored unnarrowed.
        v0 = RsaVrfy(@SigBuf, sigLen, RsaOidSha256(), hashLen, @RecovBuf)
        v1 = 0
        If v0 <> 0
          v1 = RhSame(@RecovBuf, @HashBuf, hashLen)
        EndIf
      ElseIf op = 4
        ; PKCS#1 v1.5 in the RAW mode (no DigestInfo wrapper).
        v0 = RsaPkcs1Vrfy(@SigBuf, sigLen, 0, hashLen, @HashBuf)
        v1 = v0
      EndIf
    EndIf

    PokeI(q, v0)
    PokeI(q + 8, v1)
    PokeI(q + 16, outlen)
    PokeI(q + 24, 0)

    p = p + 36 + nLen + eLen + sigLen + msgLen
    p = ((p + 3) / 4) * 4
    q = q + 32
    o = o + (((outlen + 3) / 4) * 4)
  ForEver

  UartWriteStr("rsaharness done")
  ProcedureReturn 0
EndProcedure
'''


# =====================================================================
#  THE VECTOR SET, IMPORTED FROM THE GENERATOR THE PICO GATES USE
# =====================================================================
def load_records():
    """Import tools/gen_rsa_vectors.py and build its record table.

    THE BUILDERS ARE CALLED IN main()'S ORDER AND ONLY IN main()'S
    ORDER.  The generator seeds one module-level Random at import, so
    2048-full, 3072, 4096, smoke is not a preference - any other order
    produces different keys and different signatures, and the Pi 4
    would then be passing a vector set nobody else runs.  main() itself
    is NOT called: it would rewrite the three families' baked vector
    files as a side effect of running this gate.
    """
    gen_path = ROOT / "tools" / "gen_rsa_vectors.py"
    if not gen_path.exists():
        raise SystemExit(
            "the vector oracle is missing: %s\n"
            "This gate deliberately has no vectors of its own - it reads\n"
            "the same generator that emits rsaVectors.pico2 for the Pico\n"
            "gates. Check that the file was not moved out of tools/."
            % gen_path)
    spec = importlib.util.spec_from_file_location("gen_rsa_vectors", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in ("RECORDS", "build_for_key", "build_smoke", "K_PKCS1",
                 "K_PSS", "K_SEAM", "SHA256_DI_PREFIX", "HLEN"):
        if not hasattr(mod, name):
            raise SystemExit(
                "gen_rsa_vectors.py no longer defines %r; this gate reads "
                "its table BY NAME and must be updated WITH it, not around "
                "it. Check that the builder functions were not renamed."
                % name)
    if mod.RECORDS:
        raise SystemExit(
            "gen_rsa_vectors.py populated RECORDS at import time, so this "
            "gate cannot control the build order. Move the emit behind an "
            "`if __name__ == \"__main__\":` guard, as tools/"
            "gen_bignum_vectors.py already is.")
    mod.build_for_key(2048, full=True)
    mod.build_for_key(3072, full=False)
    mod.build_for_key(4096, full=False)
    mod.build_smoke()
    if not mod.RECORDS:
        raise SystemExit("gen_rsa_vectors.py built no records at all; check "
                         "that build_for_key still appends to RECORDS.")
    return mod


class Script:
    """The job list, in the order the harness will walk it."""

    def __init__(self):
        self.jobs = []            # (label, expected_v0, expected_v1, out)
        self.records = []
        self.out_off = []
        self._o = 0
        self.buf = bytearray()

    def add(self, op, label, n=b"", e=b"", sig=b"", msg=b"", saltlen=0,
            hashlen=32, out=None, v0=None, v1=None):
        outlen = 0 if out is None else len(out)
        rec = struct.pack("<9I", op, saltlen, hashlen, len(n), len(e),
                          len(sig), len(msg), outlen, 0)
        rec += n + e + sig + msg
        rec += b"\x00" * ((-len(rec)) % 4)
        self._append(rec, label, v0, v1, out)

    def _append(self, rec, label, v0, v1, out):
        self.jobs.append((label, v0, v1, out))
        self.records.append(rec)
        self.out_off.append(self._o)
        self._o += ((0 if out is None else len(out)) + 3) // 4 * 4
        self.buf += rec

    def done(self):
        return bytes(self.buf) + struct.pack("<9I", OP_END, 0, 0, 0, 0,
                                             0, 0, 0, 0)

    def __len__(self):
        return len(self.jobs)


KIND_OP = {}          # filled from the generator's own constants
KIND_NAME = {}

# THE MUTANT SUBSET IS FIVE RECORDS, NAMED BY THE GENERATOR'S OWN MESSAGE
# TAGS, AND IT IS A MEASUREMENT THAT MADE IT THIS SHORT.  One 2048-bit
# public operation is 49,584,060 model instructions - the smallest
# modulus the shared oracle produces - so a sweep is priced in units of
# fifty million and every record dropped is real time.  Each of the five
# is here because at least one mutation is invisible without it:
#
#   a                 the PKCS#1 happy path: the DigestInfo template,
#                     the hash copy, the OID and RsaMemEq's MATCH.
#   badpad-pkcs1      the only record whose 0xFF run is corrupted.
#   message-B         the only PKCS#1 record whose wrapper is perfect
#                     and whose HASH is wrong, so it is the only one
#                     that reaches RsaMemEq's MISMATCH.
#   puremetal rsa pss vector
#                     the PSS happy path at salt length 32.  Salt 0
#                     will not do: a mutation that moves the salt
#                     pointer is invisible when no salt is hashed.
#   pss-message-B     a PSS signature that satisfies every check except
#                     H', so it is the only record that can see the H'
#                     comparison disappear - and the only PSS REJECT
#                     the subset carries, which is what M2 needs.
#
# --mutate refuses to run if any mutation's `needs` tag is missing from
# this set, so shrinking it further fails loudly rather than quietly.
MUTANT_TAGS = (b"a", b"badpad-pkcs1", b"message-B",
               b"puremetal rsa pss vector", b"pss-message-B")


def build_script(g, level="full"):
    """level: "full" (every imported record + every derived negative),
    "quick" (2048-bit records only), "mutant" (the sweep's cheap subset).

    THE MUTANT SUBSET IS A TIME DECISION WITH ONE HARD REQUIREMENT: it
    must still reach every line a mutation can be planted in, and
    --mutate CHECKS that rather than trusting it (see needs_covered).
    See MUTANT_TAGS above for which five records survive the cut and
    why.  The two FREE jobs - the OID and the short-signature refusal,
    neither of which runs a modular exponentiation - are in every level
    because M10 and M5 need them and they cost nothing.
    """
    KIND_OP.update({g.K_PKCS1: OP_PKCS1, g.K_PSS: OP_PSS, g.K_SEAM: OP_SEAM})
    KIND_NAME.update({g.K_PKCS1: "pkcs1", g.K_PSS: "pss",
                      g.K_SEAM: "pkcs1 seam"})

    s = Script()
    picked = 0
    for i, (kind, expect, n, e, sig, msg, saltlen) in enumerate(g.RECORDS):
        bits = len(n) * 8
        if level == "quick" and bits != 2048:
            continue
        if level == "mutant":
            if msg not in MUTANT_TAGS or bits != 2048:
                continue
            picked += 1
        tag = msg[:26].decode("latin-1") or "(empty message)"
        s.add(KIND_OP[kind],
              "%02d %s %d-bit %s %r" % (i, KIND_NAME[kind], bits,
                                        "accept" if expect else "REFUSE", tag),
              n=n, e=e, sig=sig, msg=msg, saltlen=saltlen,
              v0=expect, v1=expect)

    if level == "mutant" and picked != len(MUTANT_TAGS):
        raise SystemExit(
            "the mutant subset matched %d of the %d records it names by "
            "message tag; gen_rsa_vectors.py's tags moved, so update "
            "MUTANT_TAGS deliberately rather than sweeping a subset that "
            "no longer reaches the lines it is supposed to."
            % (picked, len(MUTANT_TAGS)))

    # ---- THE DERIVED NEGATIVES ---------------------------------------
    # Every one of these re-points a record the generator already made.
    # Nothing below invents a signature, a key or a hash.
    pk = next(r for r in g.RECORDS
              if r[0] == g.K_PKCS1 and r[1] == 1 and len(r[2]) == 256
              and r[3] == b"\x03")
    ps = next(r for r in g.RECORDS
              if r[0] == g.K_PSS and r[1] == 1 and len(r[2]) == 256
              and r[6] == g.HLEN)
    other_n = next(r[2] for r in g.RECORDS
                   if len(r[2]) == 256 and r[2] != pk[2])

    # The short-signature refusal costs nothing: RsaPublic bails out on
    # the length before it decodes anything.  It is in EVERY level,
    # including the mutant subset, because it is the only job there for
    # which the public operation refuses at all - which is what makes
    # mutation M5 reachable.
    s.add(OP_PKCS1, "d1 pkcs1 REFUSE a signature one byte short of the "
                    "modulus", n=pk[2], e=pk[3], sig=pk[4][:-1], msg=pk[5],
          v0=0, v1=0)

    # The OID is free too, and it is the only job that touches
    # RsaOidSha256's table without a modular exponentiation in front of
    # it.  Expected bytes SLICED OUT OF THE GENERATOR'S OWN DigestInfo
    # prefix (30 31 30 0d 06 <len> <oid...> 05 00 04 20), never typed.
    oid = g.SHA256_DI_PREFIX[5:15]
    s.add(OP_OID, "d2 the length-prefixed SHA-256 DigestInfo OID",
          out=oid, v0=0, v1=0)

    # THE FORGOTTEN SETUP STEP, MEASURED RATHER THAN ARGUED.
    # RsaSetPubKey is this family's single addition and it has a known
    # bug shape: a setup step the caller must remember, remembered by
    # only some callers - the same family as the i2c
    # subcommands that skipped HwI2cUp().  rsa.pi4's header ANSWERS the
    # objection in prose ("forgetting is safe rather than silent"); this
    # job turns the prose into a measurement.  All three entry points
    # must refuse with a zero key installed, and the recovery buffer
    # must come back holding nothing but the sentinel.
    #
    # It is in EVERY level including the mutant subset, and it is free:
    # RsaPublic refuses on the length before it decodes anything, so no
    # modular exponentiation runs.
    #
    # NO MUTATION IS PLANTED FOR IT, and that is recorded rather than
    # left as a silence.  The guard reads `nLen = 0 Or nLen >
    # #RsaMaxBytes Or xlen <> nLen`, and against a real 256-byte
    # signature the THIRD term refuses on its own - so deleting the
    # `nLen = 0` term changes no verdict this job can see, and a
    # mutation that cannot die is worse than none.  What the job does
    # catch is the failure the header claims cannot happen: an entry
    # point that runs the arithmetic anyway, or a refusal that writes
    # into the caller's buffer.  Either shows as a wrong verdict or a
    # broken sentinel.
    s.add(OP_NOKEY, "d10 REFUSE every entry point with NO KEY INSTALLED, "
                    "and write nothing",
          sig=pk[4], msg=pk[5], saltlen=g.HLEN,
          out=bytes([0xA5]) * 32, v0=0, v1=0)

    if level != "mutant":
        s.add(OP_PKCS1, "d3 pkcs1 REFUSE a good signature against the wrong "
                        "modulus", n=other_n, e=pk[3], sig=pk[4], msg=pk[5],
              v0=0, v1=0)
        s.add(OP_PSS, "d4 pss REFUSE a good signature against the wrong "
                      "modulus", n=other_n, e=ps[3], sig=ps[4], msg=ps[5],
              saltlen=ps[6], v0=0, v1=0)
        s.add(OP_PSS, "d5 pss REFUSE a PKCS#1 signature (scheme confusion)",
              n=pk[2], e=pk[3], sig=pk[4], msg=pk[5], saltlen=g.HLEN,
              v0=0, v1=0)
        s.add(OP_PKCS1, "d6 pkcs1 REFUSE a PSS signature (scheme confusion)",
              n=ps[2], e=ps[3], sig=ps[4], msg=ps[5], v0=0, v1=0)
        s.add(OP_PKCS1, "d7 pkcs1 REFUSE the modulus itself as the signature "
                        "(not a proper representative)",
              n=pk[2], e=pk[3], sig=pk[2], msg=pk[5], v0=0, v1=0)
        even = pk[2][:-1] + bytes([pk[2][-1] & 0xFE])
        s.add(OP_PKCS1, "d8 pkcs1 REFUSE an EVEN modulus (no Montgomery m0i)",
              n=even, e=pk[3], sig=pk[4], msg=pk[5], v0=0, v1=0)
        s.add(OP_RAW, "d9 pkcs1-raw REFUSE a DigestInfo-wrapped signature "
                      "in the raw mode", n=pk[2], e=pk[3], sig=pk[4],
              msg=pk[5], v0=0, v1=0)
    return s


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def build(rsa_include, harness, img):
    WORK.mkdir(exist_ok=True)
    src = HARNESS.replace("__RSA__", rsa_include)
    harness.write_text(src, encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(harness), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)
    return img.stat().st_size


def run_raw(img_bytes, script, count, out_bytes):
    """Execute one script under the model.  Returns (records, out, steps)."""
    from a64_interp import A64
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(img_bytes):
        mem[LOAD + i] = b
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    for i in range(count * RESULT_STRIDE):
        mem[H_RESULT + i] = SENTINEL
    for i in range(out_bytes):
        mem[H_OUT + i] = SENTINEL

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
        if steps > STEP_LIMIT:
            raise SystemExit("the harness never returned after %d model "
                             "instructions; raise STEP_LIMIT only after "
                             "checking the script is not malformed\n%s"
                             % (steps, uart.decode("latin-1")))

    if b"rsaharness done" not in uart:
        raise SystemExit("the harness returned without finishing its "
                         "script; check the last job's blob lengths:\n"
                         + uart.decode("latin-1"))

    recs = [bytes(mem.get(H_RESULT + i * RESULT_STRIDE + j, 0)
                  for j in range(RESULT_STRIDE))
            for i in range(count)]
    out = bytes(mem.get(H_OUT + i, 0) for i in range(out_bytes))
    return recs, out, steps


def check_shard(script, recs, out):
    bad = []
    for i, (label, e0, e1, expect) in enumerate(script.jobs):
        rec = recs[i]
        v0, v1, outlen, _ = struct.unpack("<QQQQ", rec)
        if rec == bytes([SENTINEL]) * RESULT_STRIDE:
            bad.append("%s: no record was written at all" % label)
            continue
        # THE VERDICT IS COMPARED AT FULL 64-BIT WIDTH.  A wrong answer
        # whose low half happens to be zero is still a wrong answer;
        # that is the whole reason this field is a Q and not an I.
        if e0 is not None and v0 != e0:
            bad.append("%s: the library answered %d (%016x at full width), "
                       "want %d" % (label, v0, v0, e0))
        if e1 is not None and v1 != e1:
            bad.append("%s: the caller-side answer is %d (%016x at full "
                       "width), want %d" % (label, v1, v1, e1))
        if expect is not None:
            off = script.out_off[i]
            got = out[off:off + len(expect)]
            if got != expect:
                bad.append("%s: %d bytes differ\n    want %s\n    got  %s"
                           % (label, len(expect), expect.hex(), got.hex()))
    return bad


def shard(script, n):
    """Split a Script into n Scripts, keeping every job's expectations.

    THE JOBS ARE INDEPENDENT.  Unlike the bignum gate there is no
    loaded-modulus state to carry: every record hands the library its
    own modulus and exponent, so a shard is a smaller run of the same
    thing and nothing has to be replicated into every worker.
    """
    if n <= 1 or len(script.jobs) < 2:
        return [script]
    # Interleave rather than block, so the expensive 4096-bit jobs are
    # spread across workers instead of all landing in one.
    out = []
    for k in range(n):
        idxs = list(range(k, len(script.jobs), n))
        if not idxs:
            continue
        s = Script()
        for idx in idxs:
            label, v0, v1, expect = script.jobs[idx]
            s._append(script.records[idx], label, v0, v1, expect)
        out.append(s)
    return out


def _worker(args):
    img_bytes, blob, count, out_bytes = args
    return run_raw(img_bytes, blob, count, out_bytes)


def run_all(img, script, jobs=None, quiet=False):
    """Run every job, across a process pool.  Returns (failures, steps)."""
    img_bytes = img.read_bytes()
    n = jobs or max(1, (os.cpu_count() or 2) - 2)
    shards = shard(script, n)
    if len(shards) == 1:
        recs, out, steps = run_raw(img_bytes, shards[0].done(),
                                   len(shards[0]), shards[0]._o)
        return check_shard(shards[0], recs, out), steps

    if not quiet:
        print("[gate] %d jobs across %d workers" % (len(script), len(shards)),
              file=sys.stderr)
    args = [(img_bytes, s.done(), len(s), s._o) for s in shards]
    bad = []
    steps = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=len(shards)) as ex:
        for s, (recs, out, st) in zip(shards, ex.map(_worker, args)):
            bad += check_shard(s, recs, out)
            steps += st
    return bad, steps


# =====================================================================
#  THE MUTATIONS
# =====================================================================
#  Each is (label, find, replace, verdict, needs).  The verdict is what
#  the mutation is EXPECTED to earn:
#
#    "kill"     the vector set must catch it.  A survivor is a hole.
#    a string   an EXPECTED survivor, and the string is the argument for
#               why no known-answer test can see it.  These are NOT
#               deleted: the day one of them starts being caught is the
#               day its argument stopped being true, and that is as loud
#               a failure as an unexpected survivor.
#
#  `needs` lists substrings that must appear in the MUTANT SUBSET's job
#  labels for the mutation to be reachable at all.  --mutate checks them
#  before it runs anything, because a subset that quietly stops reaching
#  a line is how a mutation survives for the wrong reason.
#
#  THE FIRST FIVE ARE THE FOUR-SHAPE AUDIT, PLANTED, AND THEY EXIST
#  BECAUSE THERE IS ALMOST NO DIFF TO READ.  Not one line of rsa.pi4's
#  core changed for the word size - the only divergence from rsa.pico2
#  is the arity split forced by the backend's eight-argument limit - so
#  the header's audit is a list of "not present" findings, and a list of
#  absences proves nothing on its own.  M0 and M1 plant shape 1 (an i15
#  buffer declared `.i`, and a clear loop striding four bytes); M4 plants
#  shape 3; M2 and M3 plant THE FIFTH SHAPE - the `>> 31` sign test and
#  the `! $FFFFFFFF` complement that made GcmDecrypt return
#  $FFFFFFFF00000000 for a forged tag - into two of the eight verdict
#  sites the header enumerates.  M17 covers the one procedure the .pico2
#  copy does not have.
# =====================================================================
MUTATIONS = [
    ("M0  shape 1: RsaM is declared .i, so an i15 word is eight bytes",
     "Global Dim RsaM.w[#RsaMaxWords]      ; modulus, i15",
     "Global Dim RsaM.i[#RsaMaxWords]      ; modulus, i15",
     "AN EXPECTED SURVIVOR. RsaM is only ever reached as @RsaM and addressed "
     "at i15 (two-byte) offsets, so declaring it .i only over-allocates it; "
     "nothing indexes it by element and no known-answer test can see it.",
     ["pkcs1"]),

    ("M1  shape 1 as a stride: RsaClear steps four bytes per i15 word",
     "    PokeW(x + (idx << 1), 0)",
     "    PokeW(x + (idx << 2), 0)",
     "kill", ["pkcs1"]),

    ("M2  shape 5: RsaPssVrfyUnpad's REJECT returns the gcm mask "
     "($FFFFFFFF00000000, whose low 32 bits are ZERO)",
     "  If r = 0\n    ProcedureReturn 1\n  EndIf\n  ProcedureReturn 0",
     "  If r = 0\n    ProcedureReturn 1\n  EndIf\n"
     "  u = (r | (0 - r)) >> 31\n  ProcedureReturn u ! $FFFFFFFF",
     "kill", ["pss", "pss 2048-bit REFUSE"]),

    ("M3  shape 5: RsaMemEq's MISMATCH returns the gcm mask",
     "  If diff = 0\n    ProcedureReturn 1\n  EndIf\n  ProcedureReturn 0",
     "  If diff = 0\n    ProcedureReturn 1\n  EndIf\n"
     "  ProcedureReturn ((diff | (0 - diff)) >> 31) ! $FFFFFFFF",
     "kill", ["message-B"]),

    ("M4  shape 3: RsaDecodeMod's comparison collapse loses its mask",
     "    r = (r >> 1) & $7FFFFFFF",
     "    r = r >> 1",
     "AN EXPECTED SURVIVOR, AND THE ONE THE HEADER ARGUES ABOUT. r is "
     "-1, 0 or +1 and must leave as an all-ones MASK for 'below the "
     "modulus'. With the mask, -1 becomes $00000000FFFFFFFF here and "
     "$FFFFFFFF on a 32-bit part - different bit patterns, same mask "
     "everywhere it is read. WITHOUT it, -1 >> 1 is still -1 and "
     "-1 | -2 is still -1, so r stays all-ones at 64 bits and `r & xw` "
     "and `r & 1` are unchanged. No known-answer test can tell, because "
     "nothing ever reads r at full width. Kept because the day a caller "
     "does, this line is what stops the sign smearing - and because the "
     "32-bit copies need it for a different reason and the two files "
     "are meant to read the same.",
     ["pkcs1"]),

    ("M5  RsaPublic returns 1 unconditionally - its three refusals (odd "
     "modulus, proper representative, matching length) all disabled",
     "  ProcedureReturn r\nEndProcedure",
     "  ProcedureReturn 1\nEndProcedure",
     "AN EXPECTED SURVIVOR, AND A FINDING RATHER THAN A GAP. RsaPublic's "
     "three preconditions are HYGIENE, not the forgery detector: when "
     "any of them fails the value left in the working buffer is either "
     "all zeros (a non-representative decodes to zero) or garbage from "
     "a Montgomery reduction with m0i = 0, and the PKCS#1 padding walk "
     "refuses both at the second byte. The gate proves the REFUSALS "
     "happen - d1, d7 and d8 all require exactly 0 at full 64-bit width "
     "- but no known-answer test can attribute a refusal to the "
     "precondition rather than to the pad. Constructing one needs a "
     "private key and a chosen EM, which is signing, which this module "
     "does not do.",
     ["pkcs1", "one byte short"]),

    ("M6  RsaPkcs1SigUnpad skips the fixed eight-0xFF pad1 prefix",
     "  idx = 2\n  While idx < 10\n    If (PeekA(sig + idx) & 255) <> $FF\n"
     "      ProcedureReturn 0\n    EndIf\n    idx = idx + 1\n  Wend",
     "  idx = 2",
     "kill", ["badpad-pkcs1"]),

    ("M7  RsaPkcs1SigUnpad's DigestInfo template declares hashLen + 1",
     "    RsaPad2[padLen - 1] = hashLen",
     "    RsaPad2[padLen - 1] = hashLen + 1",
     "kill", ["pkcs1 2048-bit accept"]),

    ("M8  RsaPkcs1SigUnpad recovers the hash one byte early",
     "    PokeB(hashOut + idx, PeekA(sig + sigLen - hashLen + idx) & 255)",
     "    PokeB(hashOut + idx, PeekA(sig + sigLen - hashLen + idx - 1) & 255)",
     "kill", ["pkcs1 2048-bit accept"]),

    ("M9  RsaPkcs1SigUnpad drops the OID-length bound that keeps the "
     "template inside RsaPad2",
     "    If x3 > 48\n      ProcedureReturn 0\n    EndIf\n",
     "",
     "AN EXPECTED SURVIVOR, AND UNREACHABLE BY CONSTRUCTION. The only "
     "OID any of these vectors carries is the 9-byte SHA-256 one, so x3 "
     "is 9 and the bound never fires. It is not there for a signature: "
     "it is there for the CHAIN ENGINE, which hands this procedure an "
     "OID out of a certificate's bytecode data block, and an "
     "attacker-chosen 60-byte OID would otherwise write past a 65-byte "
     "buffer. Reaching it needs a caller-supplied OID, which is x509's "
     "gate to build, not a signature vector.",
     ["pkcs1"]),

    ("M10 RsaOidSha256 builds one wrong OID byte",
     "    RsaOid[4] = $01",
     "    RsaOid[4] = $02",
     "kill", ["DigestInfo OID"]),

    ("M11 RsaPssVrfyUnpad's byte-aligned branch stops checking the "
     "leading byte",
     "  If (nBitlen & 7) = 0\n    r = r | (PeekA(xPtr) & 255)\n"
     "    emBase = 1",
     "  If (nBitlen & 7) = 0\n    emBase = 1",
     "AN EXPECTED SURVIVOR, AND A DEAD BRANCH FOR EVERY RSA KEY ANYONE "
     "ISSUES. nBitlen here is modBits - 1, and every modulus in the set "
     "(and every modulus a CA emits) has a bit length that is a "
     "multiple of 8, so nBitlen & 7 is 7 and this branch is never "
     "entered. Reaching it needs a modulus whose bit length is 1 mod 8 "
     "- a 2041-bit key - which no vector oracle here produces and no "
     "certificate carries. Recorded rather than deleted because the "
     "branch is correct and the .pico2 copy has it.",
     ["pss"]),

    ("M12 RsaPssVrfyUnpad stops masking the unused leading bits",
     "    r = r | ((PeekA(xPtr) & 255) & ($FF << (nBitlen & 7)))",
     "    r = r | (PeekA(xPtr) & 255)",
     "kill", ["pss 2048-bit accept"]),

    ("M13 RsaPssVrfyUnpad never compares H'",
     "  idx = 0\n  While idx < hashLen\n    r = r | ((RsaTmp[idx] & 255) ! "
     "(PeekA(xPtr + emBase + xlen - hashLen - 1 + idx) & 255))",
     "  idx = 0\n  While idx < 0\n    r = r | ((RsaTmp[idx] & 255) ! "
     "(PeekA(xPtr + emBase + xlen - hashLen - 1 + idx) & 255))",
     "kill", ["pss", "pss-message-B"]),

    ("M14 RsaPssVrfyUnpad's salt pointer is one byte low",
     "  salt = xPtr + emBase + xlen - hashLen - saltLen - 1",
     "  salt = xPtr + emBase + xlen - hashLen - saltLen - 2",
     "kill", ["pss 2048-bit accept"]),

    ("M15 RsaMgf1Xor writes the MGF1 block counter little-endian",
     "    RsaMgfCnt[0] = (cnt >> 24) & 255\n"
     "    RsaMgfCnt[1] = (cnt >> 16) & 255\n"
     "    RsaMgfCnt[2] = (cnt >> 8) & 255\n"
     "    RsaMgfCnt[3] = cnt & 255",
     "    RsaMgfCnt[0] = cnt & 255\n"
     "    RsaMgfCnt[1] = (cnt >> 8) & 255\n"
     "    RsaMgfCnt[2] = (cnt >> 16) & 255\n"
     "    RsaMgfCnt[3] = (cnt >> 24) & 255",
     "kill", ["pss 2048-bit accept"]),

    ("M16 RsaPssVrfyUnpad hashes seven zero bytes of M' instead of eight",
     "  Sha256Update(@RsaTmp, 8)",
     "  Sha256Update(@RsaTmp, 7)",
     "kill", ["pss 2048-bit accept"]),

    # THE ONLY MUTATION IN CODE THE .pico2 COPY DOES NOT HAVE.
    # RsaSetPubKey is this file's single addition, forced by the
    # backend's eight-argument limit, so it gets its own line in the
    # sweep rather than riding on the twins' coverage.
    ("M17 RsaSetPubKey stores the exponent where the modulus belongs",
     "  RsaKeyN = nPtr\n  RsaKeyNLen = nLen",
     "  RsaKeyN = ePtr\n  RsaKeyNLen = eLen",
     "kill", ["pkcs1", "pss"]),
]


def needs_covered(script):
    """Every mutation's reachability tag must appear in the subset."""
    labels = " || ".join(j[0] for j in script.jobs)
    missing = []
    for label, _f, _r, _v, needs in MUTATIONS:
        for tag in needs:
            if tag not in labels:
                missing.append("%s needs a job matching %r and the mutant "
                               "subset has none" % (label.split()[0], tag))
    return missing


def mutate_source(idx, find, replace):
    """Write a mutated COPY into _work/ and return its include path.

    THIS NEVER OPENS THE REAL SOURCE FOR WRITING, and every mutation
    gets its OWN filename.  When the A64 GCM sweep let every mutant of
    one file share a name, four of them raced, the compiler read a
    half-written file, and the pool reported four survivors that were
    nothing of the kind.
    """
    WORK.mkdir(exist_ok=True)
    text = RSA.read_text(encoding="utf-8")
    # EVERY ANCHOR IS A LINE ANCHOR, and that is not tidiness.  This
    # file's header QUOTES its own code - the four-shape audit prints
    # `r = (r >> 1) & $7FFFFFFF` in prose to argue about it - so an
    # anchor matched as a bare substring finds the comment as well as
    # the code and the uniqueness check refuses to run at all.  Matching
    # "\n" + find pins it to the start of a line, where a comment's
    # leading ";" cannot follow.
    find, replace = "\n" + find, "\n" + replace
    if text.count(find) != 1:
        raise SystemExit("mutation anchor found %d times in %s (want 1); the "
                         "source moved under the table:\n%r"
                         % (text.count(find), RSA.name, find))
    out = WORK / ("mut%02d_%s" % (idx, RSA.name))
    out.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return "_work/" + out.name


def build_mutant(idx, include, img):
    WORK.mkdir(exist_ok=True)
    src = HARNESS.replace("__RSA__", include)
    hp = WORK / ("rsaharness_mut%02d.pi4" % idx)
    hp.write_text(src, encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(hp), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)
    return img.stat().st_size


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
    ap.add_argument("--quick", action="store_true",
                    help="the 2048-bit records only")
    ap.add_argument("--mutate", action="store_true", help="the mutation sweep")
    ap.add_argument("--mutation", type=int, default=None,
                    help="run ONE mutation by index (used by the pool)")
    ap.add_argument("--jobs", type=int, default=None,
                    help="worker processes (default: cores - 2)")
    args = ap.parse_args(argv)
    globals()["PMFC"] = resolve_compiler(args.compiler)
    globals()["JOBS_CAP"] = args.jobs

    print("[gate] tree under test: %s" % ROOT, file=sys.stderr)

    g = load_records()

    if args.mutation is not None:
        i = args.mutation
        label, find, repl, verdict, _needs = MUTATIONS[i]
        inc = mutate_source(i, find, repl)
        img = WORK / ("rsa_mut%02d.img" % i)
        try:
            build_mutant(i, inc, img)
        except SystemExit as e:
            # A MUTANT THAT WILL NOT BUILD IS KILLED BY THE COMPILER, and
            # that is a legitimate kill - but it is a DIFFERENT verdict
            # from "the vectors caught it" and is printed as one.
            print("NOBUILD  %s\n         %s" % (label, str(e).splitlines()[0]))
            return 0
        s = build_script(g, level="mutant")
        bad, _ = run_all(img, s, jobs=args.jobs, quiet=True)

        if verdict == "kill":
            if bad:
                print("KILLED   %s\n         first: %s"
                      % (label, bad[0].splitlines()[0]))
                return 0
            print("SURVIVED %s\n         (the vector set was expected to "
                  "catch this one)" % label)
            return 1

        if bad:
            print("UNEXPECTED-KILL %s\n         the vector set now catches "
                  "this, so the recorded argument is stale:\n         %s\n"
                  "         first: %s"
                  % (label, verdict, bad[0].splitlines()[0]))
            return 1
        print("EXPECTED-SURVIVOR %s" % label)
        return 0

    if args.mutate:
        s = build_script(g, level="mutant")
        missing = needs_covered(s)
        if missing:
            for m in missing:
                print("FAIL: " + m)
            print("MUTATION SWEEP RED: the cheap subset does not reach every "
                  "mutated line, so a survivor would mean nothing")
            return 1
        print("[gate] the mutant subset is %d jobs and reaches every mutated "
              "line" % len(s))
        n = args.jobs or max(1, (os.cpu_count() or 2) - 2)
        print("[gate] %d mutations across %d workers" % (len(MUTATIONS), n))
        t0 = time.time()
        survivors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            futs = {ex.submit(subprocess.run,
                              [sys.executable, __file__, "--mutation",
                               str(i), "--jobs", "1",
                               "--compiler", str(PMFC)],
                              cwd=ROOT, env=BUILD_ENV,
                              capture_output=True, text=True): i
                    for i in range(len(MUTATIONS))}
            for f in concurrent.futures.as_completed(futs):
                i = futs[f]
                r = f.result()
                sys.stdout.write(r.stdout)
                if r.returncode != 0:
                    sys.stdout.write(r.stderr)
                    survivors.append(MUTATIONS[i][0])
        expected = sum(1 for m in MUTATIONS if m[3] != "kill")
        print("[gate] sweep took %.0f s" % (time.time() - t0))
        if survivors:
            print("MUTATION SWEEP RED: %d unexpected outcome(s):\n  %s"
                  % (len(survivors), "\n  ".join(survivors)))
            return 1
        print("MUTATION SWEEP GREEN: 0 unexpected outcomes of %d "
              "(%d of them are EXPECTED survivors, each with its recorded "
              "argument in the table)" % (len(MUTATIONS), expected))
        return 0

    s = build_script(g, level="quick" if args.quick else "full")
    img = WORK / "rsaharness.img"
    size = build("RaspberryPi4/Lib/rsa.pi4", WORK / "rsaharness.pi4", img)
    print("[gate] image %d bytes, %d jobs (%d imported records, %d derived)"
          % (size, len(s), len(g.RECORDS) if not args.quick else
             sum(1 for r in g.RECORDS if len(r[2]) == 256),
             len(s) - (len(g.RECORDS) if not args.quick else
                       sum(1 for r in g.RECORDS if len(r[2]) == 256))))
    t0 = time.time()
    bad, steps = run_all(img, s, jobs=args.jobs)
    for b in bad:
        print("FAIL: " + b)
    print("[gate] %d jobs, %d model instructions, %.0f s"
          % (len(s), steps, time.time() - t0))
    if bad:
        print("RSA GATE RED: %d of %d jobs wrong" % (len(bad), len(s)))
        return 1
    print("RSA GATE GREEN: %d jobs on the shared RSA vector set, "
          "%d model instructions" % (len(s), steps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
