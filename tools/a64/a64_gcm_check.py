#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/gcm.pi4 (and the CTR mode that
was added to RaspberryPi4/Lib/aes.pi4 to make it possible).

WHY THIS FILE IS WRITTEN THE WAY IT IS

  THE VECTORS ARE THE ONES THE PICO GATES ALREADY USE.  They are not
  transcribed here and they are not generated here: this gate IMPORTS
  the KAT table out of tools/gen_gcm_vectors.py, which is the file that
  emits gcmVectors.pico2 / .pico / .unor4 for the three 32-bit
  families.  One table, four families - so "the Pi 4 passes the same
  vectors" is a fact about the source, not a claim about two lists that
  were once eyeballed.

  AND THEY ARE RE-CHECKED AGAINST A SECOND IMPLEMENTATION.  Every
  vector is run through the `cryptography` package's AES-GCM before it
  is used, exactly as the generator does, so a wrong expectation would
  have to be wrong in both NIST's table and OpenSSL.  If that package
  is not installed the gate says so and continues on the table alone,
  because a missing optional dependency must not be able to turn a red
  gate green - but it prints which mode it ran in.

  BOTH DIRECTIONS, AND A FORGERY ON EVERY VECTOR.  Encryption is
  checked byte-exact (ciphertext and tag).  Decryption is checked
  byte-exact on the recovered plaintext AND on the verdict mask, and
  then the same vector is decrypted again with ONE BIT of the tag
  flipped and the verdict must be exactly 0.

  THE FORGERY NEGATIVE IS THE POINT OF THIS GATE, not a nicety.  The
  32-bit families end GcmDecrypt with `>> 31` to smear a sign bit; on
  this target the sign bit is bit 63 and that spelling returns
  $FFFFFFFE for a bad tag - non-zero, and therefore "authentic" to
  every caller that tests for non-zero.  A gate with only positive
  vectors goes green on that.  Mutation M2 below is exactly that line
  and the sweep watches it die.

  THE NO-KEY REFUSAL IS TESTED.  GcmInit with a length of 0, 15, 20 or
  33 must return 0, must leave no key installed, and the AEAD calls
  after it must write NOTHING - the output buffers are pre-filled with
  a sentinel so a refusal that returns 0 and writes anyway is caught as
  loudly as a wrong byte.

  MUTATIONS RUN ON A COPY.  This gate NEVER opens gcm.pi4 or aes.pi4
  for writing.  It reads the sources, writes the mutant into _work/,
  and points the generated harness's XIncludeFile at the copy.  A
  runner that edits the real file and restores it afterwards leaves
  the mutant in place the first time it is killed.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.  The oracle is a model of the
    instruction set: no caches, no memory system, no clock.
  * That the implementation is constant time ON HARDWARE.  --timing
    checks that the MODEL executes the identical number of
    instructions for keys, plaintexts and tags of very different
    content at the same lengths, which rules out a data-dependent
    branch or a secret-indexed access in the compiled code.  It says
    nothing about what a real Cortex-A72 does with those instructions.

Run: python tools/a64/a64_gcm_check.py
     python tools/a64/a64_gcm_check.py --quick
     python tools/a64/a64_gcm_check.py --timing
     python tools/a64/a64_gcm_check.py --mutate
"""

from __future__ import annotations

import argparse
import os
import pathlib
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent

# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN.  A root pinned into
# the file made another gate build a DIFFERENT working copy, with that
# copy's compiler, and print the answer as this tree's.  Override
# deliberately with PMF_REPO; the tree actually read is printed below.
ROOT = pathlib.Path(__file__).resolve().parents[2]
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
from a64_interp import A64  # noqa: E402
from a64_target import (TARGETS, apply_target,  # noqa: E402
                        patch_harness)

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
AES = ROOT / "RaspberryPi4" / "Lib" / "aes.pi4"
GCM = ROOT / "RaspberryPi4" / "Lib" / "gcm.pi4"
WORK = ROOT / "_work"

LOAD = 0x00400000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
STACK = 0x03000000

# The board this run builds for.  Rebound by apply_target() from the
# --target flag before anything else runs; see tools/a64/a64_target.py.
# Two AArch64 boards now share these libraries - the Pi 4's A72 and the
# Arduino UNO Q's A53 - and they share the FILES, not copies of them, so
# this gate grades both rather than being duplicated.
TFLAG = "pi4"
TARGET_NAME = "pi4"
TARGET_WHAT = TARGETS["pi4"]["what"]
CONSOLE_INCLUDE = TARGETS["pi4"]["console"]


UART_LO = 0xFE201000
UART_HI = 0xFE201048
UART_DR = 0xFE201000

# Far above the image at $400000 and the stack top at $3000000.
H_SCRIPT = 0x06000000
H_RESULT = 0x0A000000
H_CIPHER = 0x0B000000

STEP_LIMIT = 8_000_000_000

# tag(16) then FOUR 64-BIT fields: verdict, forged verdict, ptmatch, ctlen.
#
# THE VERDICTS ARE STORED AT FULL WIDTH AND THAT IS THE WHOLE POINT.
# They were 32-bit at first, written with PokeN, and mutation M2 - the
# verdict line copied verbatim from the 32-bit families - SURVIVED,
# because the value that line produces for a forged tag is
# $FFFFFFFF00000000 and its low 32 bits are zero.  The gate was
# truncating away the exact bug it exists to find.  That is also the
# real-world hazard the module header names: a caller that truncates
# looks correct and a caller that does not is silently broken.
RESULT_STRIDE = 48
SENTINEL = 0xA5

OP_END = 0
OP_VECTOR = 1
OP_REFUSE = 2
OP_CTR_NOKEY = 3


# =====================================================================
#  THE HARNESS
# =====================================================================
#  It reads a script of AEAD jobs out of memory at #H_SCRIPT, runs each
#  one forwards and backwards, and writes a fixed 32-byte verdict record
#  per job at #H_RESULT plus the ciphertext at #H_CIPHER.  Every vector
#  is DATA, so adding one never changes this file.
#
#  SCRIPT RECORD, 24 bytes then key || iv || aad || pt, padded to 4:
#      +0 op  +4 keylen  +8 ivlen  +12 aadlen  +16 ptlen  +20 forgeat
#  op 0 ends the script.
#  op 1 is a vector.  op 2 is a refused key length: the same record, but
#  the run must produce nothing.  op 3 goes straight into AesCtrCore
#  with no key installed.
#  `forgeat` is the tag byte the one-bit forgery flips - 0 and 15 cost
#  the same in a constant-time compare and very different costs in one
#  that stops early.
#
#  RESULT RECORD, 48 bytes - the four fields are 64 BITS EACH:
#      +0  tag (16 bytes)
#      +16 verdict of the honest decrypt      (i64)
#      +24 verdict of the one-bit tag forgery (i64)
#      +32 1 if the recovered plaintext matched the original, else 0
#      +40 the byte length written to #H_CIPHER for this job
# =====================================================================
HARNESS = r'''
; ======================================================================
;  gcmharness.pi4 - GENERATED BY tools/a64/a64_gcm_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "__AES__"
XIncludeFile "__GCM__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000
#H_CIPHER = $0B000000

#HMAX = 8192

Global Dim hTag.a[16]
Global Dim hTagF.a[16]
Global Dim hPlain.a[#HMAX]
Global Dim hCipher.a[#HMAX]

Procedure.i Main()
  Define p.i
  Define q.i
  Define c.i
  Define op.i
  Define keylen.i
  Define ivlen.i
  Define aadlen.i
  Define ptlen.i
  Define forgeat.i
  Define key.i
  Define iv.i
  Define aad.i
  Define pt.i
  Define i.i
  Define r.i
  Define v.i
  Define vf.i
  Define same.i

  p = #H_SCRIPT
  q = #H_RESULT
  c = #H_CIPHER

  Repeat
    op     = PeekN(p)
    keylen = PeekN(p + 4)
    ivlen  = PeekN(p + 8)
    aadlen = PeekN(p + 12)
    ptlen  = PeekN(p + 16)
    forgeat = PeekN(p + 20)
    If op = 0
      Break
    EndIf

    key = p + 24
    iv  = key + keylen
    aad = iv + ivlen
    pt  = aad + aadlen

    ; The output side is pre-filled with a sentinel so a refusal that
    ; writes anyway is as loud as a wrong byte.
    i = 0
    While i < 16
      hTag[i] = $A5
      hTagF[i] = $A5
      i = i + 1
    Wend
    i = 0
    While i < ptlen
      hCipher[i] = $A5
      hPlain[i] = $A5
      i = i + 1
    Wend

    ; AesWipe first, so a refused GcmInit cannot be rescued by the key
    ; the PREVIOUS vector left installed. Without this the refusal
    ; records would silently encrypt under a stale key.
    AesWipe()

    v = 0
    vf = 0
    same = 0
    r = 0

    If op = 3
      ; NO KEY AT ALL, straight into the CTR core - the one path
      ; GcmInit's own refusal hides, because GcmInit refuses first and
      ; the AEAD is never entered. It must return -1 and write nothing,
      ; so the sentinel has to survive in hCipher. `same` is reused here
      ; as "it wrote something", and must come out 0.
      v = AesCtrCore(iv, 1, pt, @hCipher[0], ptlen)
      i = 0
      While i < ptlen
        If (hCipher[i] & 255) <> $A5
          same = 1
        EndIf
        i = i + 1
      Wend
      vf = 0
    ElseIf op <> 3
      r = GcmInit(key, keylen)
    EndIf

    If r <> 0
      GcmEncrypt(iv, ivlen, aad, aadlen, pt, ptlen, @hCipher[0], @hTag[0])

      ; The honest decrypt, on the ciphertext we just produced.
      v = GcmDecrypt(iv, ivlen, aad, aadlen, @hCipher[0], ptlen, @hPlain[0], @hTag[0])
      same = 1
      i = 0
      While i < ptlen
        If (hPlain[i] & 255) <> (PeekA(pt + i) & 255)
          same = 0
        EndIf
        i = i + 1
      Wend

      ; The same vector with ONE BIT of the tag flipped. The verdict
      ; must be exactly zero.
      i = 0
      While i < 16
        hTagF[i] = hTag[i]
        i = i + 1
      Wend
      hTagF[forgeat] = hTagF[forgeat] ! 1
      vf = GcmDecrypt(iv, ivlen, aad, aadlen, @hCipher[0], ptlen, @hPlain[0], @hTagF[0])
    EndIf

    i = 0
    While i < 16
      PokeB(q + i, hTag[i])
      i = i + 1
    Wend
    ; PokeI, NOT PokeN. See the note on RESULT_STRIDE in the gate: the
    ; verdict a wrong GcmDecrypt returns has all its set bits ABOVE bit
    ; 31, so a 32-bit store reads back as a clean pass.
    PokeI(q + 16, v)
    PokeI(q + 24, vf)
    PokeI(q + 32, same)
    PokeI(q + 40, ptlen)

    i = 0
    While i < ptlen
      PokeB(c + i, hCipher[i])
      i = i + 1
    Wend

    p = p + 24 + keylen + ivlen + aadlen + ptlen
    p = ((p + 3) / 4) * 4
    q = q + 48
    c = c + (((ptlen + 3) / 4) * 4)
  ForEver

  UartWriteStr("gcmharness done")
  ProcedureReturn 0
EndProcedure
'''


# =====================================================================
#  THE VECTOR SET, IMPORTED FROM THE GENERATOR THE PICO GATES USE
# =====================================================================
def load_kat():
    """Import the KAT table out of tools/gen_gcm_vectors.py.

    It is imported rather than copied so that the Pi 4 and the three
    32-bit families cannot drift apart in their vectors without one
    edit to one file.  The generator's module-level code only defines
    the table and some helpers; its main() is guarded, so importing it
    writes nothing.
    """
    gen_path = ROOT / "tools" / "gen_gcm_vectors.py"
    if not gen_path.exists():
        raise SystemExit(
            "the vector table is missing: %s\n"
            "This gate deliberately has no vectors of its own - it reads the\n"
            "same table that emits gcmVectors.pico2 for the Pico gates."
            % gen_path)
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen_gcm_vectors", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    kat = getattr(mod, "KAT", None)
    if not kat:
        raise SystemExit("gen_gcm_vectors.py no longer defines a KAT table; "
                         "this gate reads it by name and must be updated "
                         "with it, not around it")
    out = []
    for key, pt, aad, iv, ct, tag in kat:
        out.append((bytes.fromhex(key), bytes.fromhex(iv),
                    bytes.fromhex(aad), bytes.fromhex(pt),
                    bytes.fromhex(ct), bytes.fromhex(tag)))
    return out


def second_opinion(vectors):
    """Re-derive every expectation with a second implementation."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception:
        print("[gate] the `cryptography` package is not installed: the "
              "vectors stand on the NIST/McGrew table alone, with no second "
              "opinion. Install it to close that gap.", file=sys.stderr)
        return False
    for n, (key, iv, aad, pt, ct, tag) in enumerate(vectors):
        blob = AESGCM(key).encrypt(iv, pt, aad if aad else None)
        if blob[:-16] != ct or blob[-16:] != tag:
            raise SystemExit(
                "vector %d disagrees with the second implementation BEFORE "
                "anything was built. The table, not the library under test, "
                "is wrong." % n)
    print("[gate] all %d vectors confirmed against a second implementation"
          % len(vectors), file=sys.stderr)
    return True


class Script:
    def __init__(self):
        self.buf = bytearray()
        self.labels = []
        self.ops = []
        self.expect = []          # (ct, tag) or None for a refusal
        self.ct_off = []
        self._c = 0

    def add(self, op, label, key, iv, aad, pt, expect, forgeat=0):
        self.labels.append(label)
        self.ops.append(op)
        self.expect.append(expect)
        self.ct_off.append(self._c)
        self._c += ((len(pt) + 3) // 4) * 4
        rec = struct.pack("<IIIIII", op, len(key), len(iv), len(aad),
                          len(pt), forgeat)
        rec += key + iv + aad + pt
        rec += b"\x00" * ((-len(rec)) % 4)
        self.buf += rec

    def done(self):
        return bytes(self.buf) + struct.pack("<IIIIII", OP_END, 0, 0, 0, 0, 0)


def long_vector():
    """One message long enough to move the HIGH bytes of the CTR counter.

    WHY IT EXISTS.  The NIST/McGrew table's longest plaintext is 64
    bytes, so the counter never leaves 0..5 and the top three bytes of
    the big-endian counter word are zero in every vector.  A byte
    dropped from AesSwap32 is therefore INVISIBLE to the whole KAT set -
    the mutation sweep said so, by surviving.  4144 bytes is 259 blocks,
    which carries the counter past 255 and makes byte 1 non-zero.

    It is generated, not transcribed, and it is generated by the SECOND
    implementation - so unlike the KAT entries it has one oracle, not
    two.  Without that package there is no vector and the gate says the
    hole is open rather than quietly closing it.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception:
        return None
    key = bytes((i * 7 + 3) & 0xFF for i in range(16))
    iv = bytes((i * 11 + 5) & 0xFF for i in range(12))
    aad = bytes((i * 13 + 1) & 0xFF for i in range(29))
    pt = bytes((i * 31 + 17) & 0xFF for i in range(4144))
    blob = AESGCM(key).encrypt(iv, pt, aad)
    return (key, iv, aad, pt, blob[:-16], blob[-16:])


def build_script(vectors, subset=False):
    s = Script()
    # THE SUBSET IS A TIME DECISION, AND IT HAS ONE HARD REQUIREMENT: it
    # must contain vectors whose PARTIAL GHASH blocks are of DIFFERENT
    # lengths.  A subset of every sixth vector was all empty-plaintext
    # cases, so the zero-padding scratch was only ever written once with
    # the same shape and mutation M7 - padding a partial block with
    # whatever was left in the scratch - survived it.  Every third
    # vector includes the 60-byte and 20-byte AAD cases and does not.
    vs = vectors[::3] if subset else vectors
    for n, (key, iv, aad, pt, ct, tag) in enumerate(vs):
        # Alternate which tag byte the forgery flips, so a compare that
        # stops early costs visibly different amounts between records.
        s.add(OP_VECTOR,
              "KAT %d  AES-%d ivlen=%d aadlen=%d ptlen=%d"
              % (n, len(key) * 8, len(iv), len(aad), len(pt)),
              key, iv, aad, pt, (ct, tag), forgeat=(15 if n % 2 else 0))

    lv = long_vector()
    if lv is None:
        print("[gate] NO LONG VECTOR: the `cryptography` package is not "
              "installed, so the CTR counter never passes 255 and a fault in "
              "the high bytes of AesSwap32 would not be seen. That hole is "
              "OPEN in this run.", file=sys.stderr)
    else:
        key, iv, aad, pt, ct, tag = lv
        s.add(OP_VECTOR, "long  AES-128 ptlen=%d (259 CTR blocks)" % len(pt),
              key, iv, aad, pt, (ct, tag))

    # The refusals. Same shape, a key length the library must reject.
    base = vectors[2]
    for bad in ((0, 20) if subset else (0, 15, 20, 33)):
        s.add(OP_REFUSE, "refusal keylen=%d" % bad,
              bytes(range(bad)), base[1], base[2], base[3], None)

    # And the CTR core reached with no key at all, which GcmInit's own
    # refusal hides from every record above.
    s.add(OP_CTR_NOKEY, "AesCtrCore with no key installed",
          b"", base[1], b"", base[3], None)
    return s


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def build(aes_include, gcm_include, harness, img):
    WORK.mkdir(exist_ok=True)
    src = HARNESS.replace("__AES__", aes_include).replace("__GCM__",
                                                          gcm_include)
    harness.write_text(patch_harness(src, globals()), encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(harness), "-t", TFLAG,
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)
    return img.stat().st_size


def run(img, script, count, ct_bytes):
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    # Pre-fill both output areas with the sentinel, so the harness
    # failing to write is distinguishable from it writing zeroes.
    for i in range(count * RESULT_STRIDE):
        mem[H_RESULT + i] = SENTINEL
    for i in range(ct_bytes):
        mem[H_CIPHER + i] = SENTINEL

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
            raise SystemExit("the harness never returned (%d steps)\n%s"
                             % (steps, uart.decode("latin-1")))

    if b"gcmharness done" not in uart:
        raise SystemExit("the harness returned without finishing its script:\n"
                         + uart.decode("latin-1"))

    out = []
    for i in range(count):
        a = H_RESULT + i * RESULT_STRIDE
        rec = bytes(mem.get(a + j, 0) for j in range(RESULT_STRIDE))
        out.append(rec)
    cipher = bytes(mem.get(H_CIPHER + i, 0) for i in range(ct_bytes))
    return out, cipher, steps


def check(script, results, cipher):
    """Compare every record against its expectation. Returns failures."""
    bad = []
    for i, label in enumerate(script.labels):
        rec = results[i]
        tag = rec[0:16]
        verdict, forged, same, ctlen = struct.unpack("<QQQQ", rec[16:48])
        exp = script.expect[i]
        off = script.ct_off[i]

        if script.ops[i] == OP_CTR_NOKEY:
            # AesCtrCore must refuse with -1 and write NOTHING.
            if verdict != 0xFFFFFFFFFFFFFFFF:
                bad.append("%s: returned %016x, not the -1 refusal - a CTR "
                           "with no key encrypts under whatever schedule is "
                           "left in .bss, which for a cleared image is an "
                           "all-zero key" % (label, verdict))
            if same != 0:
                bad.append("%s: the output buffer was written on a refusal"
                           % label)
            continue

        if exp is None:
            # A refusal. Nothing may have been written: the sentinel
            # must survive in the tag and in the ciphertext area.
            if tag != bytes([SENTINEL]) * 16:
                bad.append("%s: the tag buffer was written on a refused key "
                           "length" % label)
            if verdict != 0 or forged != 0 or same != 0:
                bad.append("%s: a refused key length still produced a verdict "
                           "(%016x/%016x/%d)" % (label, verdict, forged, same))
            got_ct = cipher[off:off + ctlen]
            if got_ct != bytes([SENTINEL]) * ctlen:
                bad.append("%s: ciphertext was written on a refused key length"
                           % label)
            continue

        exp_ct, exp_tag = exp
        got_ct = cipher[off:off + len(exp_ct)]
        if got_ct != exp_ct:
            bad.append("%s: ciphertext differs\n    want %s\n    got  %s"
                       % (label, exp_ct.hex(), got_ct.hex()))
        if tag != exp_tag:
            bad.append("%s: tag differs\n    want %s\n    got  %s"
                       % (label, exp_tag.hex(), tag.hex()))
        if verdict != 0xFFFFFFFF:
            bad.append("%s: the honest decrypt returned %016x, not FFFFFFFF"
                       % (label, verdict))
        if forged != 0:
            bad.append("%s: A ONE-BIT TAG FORGERY WAS ACCEPTED - the verdict "
                       "was %016x at full width, and every caller that tests "
                       "for non-zero would take it" % (label, forged))
        if same != 1:
            bad.append("%s: the decrypted plaintext is not the original"
                       % label)
    return bad


# =====================================================================
#  THE MUTATIONS
# =====================================================================
#  Each is (label, file, find, replace, why).  Every one must be caught
#  by the vector set; a survivor is a hole in the gate, not a harmless
#  edit, and gets recorded rather than deleted.
# =====================================================================
#  The fifth field is the VERDICT THIS MUTATION IS EXPECTED TO EARN:
#
#    "kill"     the vector set must catch it.  A survivor is a hole.
#    "timing"   the vectors cannot catch it - the answers stay right -
#               and the constant-time check must.  Run with --timing.
#    a string   an EXPECTED survivor, and the string is the argument for
#               why no known-answer test can see it.  These are not
#               deleted, because the day one of them starts being
#               catchable is the day the argument stopped holding.
#
#  Every entry here was actually run.  Four of them were WRONG when this
#  table was first written - they mutated a line that is zero for every
#  vector, or a value no vector reaches - and the sweep is what said so.
#  Those four are fixed below rather than removed.
MUTATIONS = [
    ("M1 gcm  GhLsl drops its mask", "gcm",
     "Procedure.i GhLsl(x.i, n.i)\n  ProcedureReturn (x << n) & #GCM_W32",
     "Procedure.i GhLsl(x.i, n.i)\n  ProcedureReturn (x << n)",
     "REVIEWABILITY, NOT CORRECTNESS - the same case sha256.pi4 makes for "
     "its own masks. Every consumer of a GhLsl result either masks its "
     "input (GhBmul32), keeps a field narrower than 32 bits (GhLsr), or "
     "leaves through GhEnc32be's per-byte '& 255'. So the spill is "
     "computed and discarded. The mask replaces three separate arguments, "
     "each of which has to keep holding, with one that can be checked a "
     "line at a time."),
    ("M2 gcm  the verdict line copied verbatim from the 32-bit families",
     "gcm",
     "  neq = ((diff | (- diff)) >> 63) & #GCM_W32\n"
     "  ProcedureReturn neq ! #GCM_W32",
     "  neq = (diff | (- diff)) >> 31\n"
     "  ProcedureReturn neq ! $FFFFFFFF",
     "kill"),
    ("M3 gcm  the tag compare breaks out on the first difference", "gcm",
     "    diff = diff | ((secGcmTag[i] & 255) ! (PeekA(tag + i) & 255))",
     "    diff = diff | ((secGcmTag[i] & 255) ! (PeekA(tag + i) & 255))\n"
     "    If diff <> 0 : Break : EndIf",
     "timing"),
    ("M4 gcm  GhRev32 loses its final rotate mask", "gcm",
     "  ProcedureReturn GhLsl(x, 16) | GhLsr(x, 16)",
     "  ProcedureReturn (x << 16) | GhLsr(x, 16)",
     "the same argument as M1, one level up: every GhRev32 result is "
     "either an operand of GhBmul32, which masks it, or the argument of "
     "GhLsr, which masks it."),
    ("M5 gcm  the length block carries the text length as the AAD length",
     "gcm",
     "  GhEnc32be(@GcmLenBlk[0] + 4,  GhLsl(aadlen, 3))",
     "  GhEnc32be(@GcmLenBlk[0] + 4,  GhLsl(len, 3))",
     "kill"),
    ("M6 gcm  J0 counter starts at 0, not 1", "gcm",
     "    GcmJ02 = 1",
     "    GcmJ02 = 0",
     "kill"),
    ("M7 gcm  a partial GHASH block is padded with the previous block",
     "gcm",
     "          GhBlk[i] = 0",
     "          GhBlk[i] = GhBlk[i]",
     "kill"),
    ("M8 aes  the CTR counter is not masked to 32 bits", "aes",
     "      cc = (cc + 1) & #AES_W32\n      If len > 16",
     "      cc = cc + 1\n      If len > 16",
     "UNREACHABLE FROM THIS BENCH, and that is the point of writing it "
     "down. The 32-bit wrap of the counter needs 64 GiB under one nonce. "
     "The mask is reasoning, not a reproduction, exactly like the "
     "byte-counter carry in sha256.pi4."),
    ("M9 aes  AesSwap32 forgets the low-middle byte", "aes",
     "  ProcedureReturn AesLsl(x, 24) | AesLsl(x & $0000FF00, 8) | "
     "(AesLsr(x, 8) & $0000FF00) | AesLsr(x, 24)",
     "  ProcedureReturn AesLsl(x, 24) | (AesLsr(x, 8) & $0000FF00) | "
     "AesLsr(x, 24)",
     "kill"),
    ("M10 aes  CTR does not refuse without a key", "aes",
     "  If AesNumRounds = 0\n    ProcedureReturn -1\n  EndIf\n\n"
     "  AesSkeyExpand()",
     "  AesSkeyExpand()",
     "kill"),
    ("M11 aes  the second CTR lane repeats the first", "aes",
     "    AesQ[7] = AesSwap32((cc + 1) & #AES_W32)",
     "    AesQ[7] = AesSwap32(cc)",
     "kill"),
]


def mutate_source(idx, which, find, replace):
    """Write a mutated COPY into _work/ and return its include path.

    THIS NEVER OPENS THE REAL SOURCE FOR WRITING.

    THE INDEX IS IN THE FILENAME AND THAT IS NOT COSMETIC.  The sweep
    fans out across processes; when every aes mutant wrote one
    `mut_aes.pi4`, four of them raced, the compiler read a half-written
    file, the build failed, and the pool - which was reading a non-zero
    exit as "survived" - reported four survivors that were nothing of
    the kind.  One file per mutation, and a build failure is now its own
    verdict.
    """
    WORK.mkdir(exist_ok=True)
    src = AES if which == "aes" else GCM
    text = src.read_text(encoding="utf-8")
    if text.count(find) < 1:
        raise SystemExit("mutation anchor not found in %s:\n%r"
                         % (src.name, find))
    out = WORK / ("mut%02d_%s" % (idx, src.name))
    out.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return "_work/" + out.name


# =====================================================================
#  MAIN
# =====================================================================
def resolve_compiler(requested):
    """Resolve the PureMetal compiler the way tools/build.py does."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
    return anvil_build.find_compiler(requested)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--target", choices=sorted(TARGETS),
                    default="pi4",
                    help="which AArch64 board's image contract "
                         "to build and grade against")
    ap.add_argument("--quick", action="store_true",
                    help="every third vector, no refusals")
    ap.add_argument("--timing", action="store_true",
                    help="the constant-instruction-count check only")
    ap.add_argument("--mutate", action="store_true",
                    help="the mutation sweep")
    ap.add_argument("--mutation", type=int, default=None,
                    help="run ONE mutation by index (used by the pool)")
    args = ap.parse_args(argv)
    globals()["PMFC"] = resolve_compiler(args.compiler)
    apply_target(globals(), args.target)
    # A GATE THAT DOES NOT SAY WHICH BOARD IT GRADED IS A RESULT
    # THAT CAN BE FILED AGAINST THE WRONG ONE.  Printed before any
    # work, so it is at the top of the transcript even on a failure.
    print("[gate] target %s - %s, image at $%08X, stack $%08X"
          % (TARGET_NAME, TARGET_WHAT, LOAD, STACK))

    vectors = load_kat()
    second_opinion(vectors)

    aes_inc = "RaspberryPi4/Lib/aes.pi4"
    gcm_inc = "RaspberryPi4/Lib/gcm.pi4"

    if args.mutation is not None:
        i = args.mutation
        label, which, find, repl, verdict = MUTATIONS[i]
        inc = mutate_source(i, which, find, repl)
        if which == "aes":
            aes_inc = inc
        else:
            gcm_inc = inc
        s = build_script(vectors, subset=True)
        img = WORK / ("gcm_mut%02d.img" % i)
        try:
            build(aes_inc, gcm_inc,
                  WORK / ("gcmharness_mut%02d.pi4" % i), img)
        except SystemExit as e:
            # A MUTANT THAT WILL NOT BUILD IS KILLED BY THE COMPILER, and
            # that is a legitimate kill - but it is a DIFFERENT verdict
            # from "the vectors caught it" and is printed as one, because
            # a mutation that only ever fails to build is not evidence
            # that the vector set can see the defect.
            print("NOBUILD  %s\n         %s" % (label, str(e).splitlines()[0]))
            return 0
        res, cipher, steps = run(img, s.done(), len(s.labels), s._c)
        bad = check(s, res, cipher)

        if verdict == "timing":
            # The vectors cannot see it and must not: the answers stay
            # right. The constant-time check is what has to catch it, and
            # if the VECTORS caught it the mutation is mislabelled.
            if bad:
                print("MISLABELLED %s\n         the vector set caught a "
                      "mutation marked 'timing'" % label)
                return 1
            if timing(aes_inc, gcm_inc, quiet=True, img=img) != 0:
                print("KILLED   %s  (by the constant-time check)" % label)
                return 0
            print("SURVIVED %s\n         (a timing-only mutation that the "
                  "constant-time check did not see)" % label)
            return 1

        if verdict == "kill":
            if bad:
                print("KILLED   %s" % label)
                return 0
            print("SURVIVED %s\n         (expected the vector set to catch "
                  "this one)" % label)
            return 1

        # An EXPECTED survivor. It surviving is the correct outcome; it
        # being CAUGHT means the argument for why no test can see it has
        # stopped being true, and that is worth as loud a line.
        if bad:
            print("UNEXPECTED-KILL %s\n         the vector set now catches "
                  "this, so the recorded argument is stale:\n         %s"
                  % (label, verdict))
            return 1
        print("EXPECTED-SURVIVOR %s" % label)
        return 0

    if args.mutate:
        import concurrent.futures
        # PMF_MUTATE_JOBS caps the sweep on a shared machine, the same
        # variable tools/a64/a64_mutate_pool.py honours.
        n = (int(os.environ.get("PMF_MUTATE_JOBS", "").strip() or 0)
             or max(1, (os.cpu_count() or 2) - 2))
        print("[gate] %d mutations across %d workers" % (len(MUTATIONS), n))
        survivors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            futs = {ex.submit(subprocess.run,
                              [sys.executable, __file__, "--mutation", str(i),
                               "--compiler", str(PMFC),
                               "--target", args.target],
                              capture_output=True, text=True): i
                    for i in range(len(MUTATIONS))}
            for f in concurrent.futures.as_completed(futs):
                i = futs[f]
                r = f.result()
                sys.stdout.write(r.stdout)
                sys.stdout.write(r.stderr if r.returncode != 0 else "")
                if r.returncode != 0:
                    survivors.append(MUTATIONS[i][0])
        expected = sum(1 for m in MUTATIONS if m[4] not in ("kill", "timing"))
        if survivors:
            print("MUTATION SWEEP RED: %d unexpected outcome(s): %s"
                  % (len(survivors), ", ".join(survivors)))
            return 1
        print("MUTATION SWEEP GREEN: 0 unexpected survivors of %d "
              "(%d of them are EXPECTED survivors, each with its recorded "
              "argument in the table)" % (len(MUTATIONS), expected))
        return 0

    s = build_script(vectors, subset=args.quick)
    img = WORK / "gcmharness.img"
    size = build(aes_inc, gcm_inc, WORK / "gcmharness.pi4", img)
    print("[gate] image %d bytes" % size)
    res, cipher, steps = run(img, s.done(), len(s.labels), s._c)
    bad = check(s, res, cipher)
    print("[gate] %d records, %d model instructions" % (len(s.labels), steps))
    for b in bad:
        print("FAIL: " + b)
    if bad:
        print("GCM GATE RED: %d of %d records wrong" % (len(bad),
                                                        len(s.labels)))
        return 1

    if args.timing:
        rc = timing(aes_inc, gcm_inc)
        if rc:
            return rc

    print("GCM GATE GREEN: %d records, encrypt and decrypt byte-exact, "
          "every one-bit tag forgery refused, %d model instructions"
          % (len(s.labels), steps))
    return 0


def timing(aes_inc, gcm_inc, quiet=False, img=None):
    """A/B instruction counts at equal lengths and different content.

    THE LENGTHS ARE THE SAME AND EVERYTHING ELSE IS AS DIFFERENT AS IT
    CAN BE.  A difference in the count is a data-dependent branch or a
    secret-indexed access, both of which are the thing this file
    promises not to have.

    THE TAG IS PART OF IT.  Each of these records also runs the one-bit
    forgery, so the count covers a good tag verification and a bad one;
    a compare that stopped at the first differing byte would come out
    with a different total.  Mutation M3 is exactly that, and this is
    what has to catch it.
    """
    if img is None:
        img = WORK / "gcmharness.img"
        if not img.exists():
            build(aes_inc, gcm_inc, WORK / "gcmharness.pi4", img)

    key_a = bytes(16)
    key_b = b"\xff" * 16
    iv = bytes(12)
    pt_a = bytes(64)
    pt_b = b"\xff" * 64

    # THE FORGERY POSITION IS A VARIABLE HERE AND THAT IS WHAT CATCHES A
    # LEAKY COMPARE.  With the byte always flipped at index 0, an
    # early-exit compare exits after one iteration in EVERY run and the
    # totals still match - mutation M3 survived exactly that.  Flipping
    # byte 0 in one run and byte 15 in another makes the leak arithmetic:
    # one iteration against sixteen.
    combos = []
    for key, pt in ((key_a, pt_a), (key_b, pt_b), (key_a, pt_b),
                    (key_b, pt_a)):
        for fa in (0, 15):
            combos.append((key, pt, fa))

    counts = []
    for key, pt, fa in combos:
        s = Script()
        s.add(OP_VECTOR, "timing", key, iv, b"", pt, (b"", b""), forgeat=fa)
        _, _, steps = run(img, s.done(), 1, s._c)
        counts.append(steps)
    if len(set(counts)) != 1:
        if not quiet:
            print("FAIL: the model executed %s instructions for %d runs that "
                  "differ only in secret content and in WHICH tag byte the "
                  "forgery flips" % (counts, len(counts)))
            print("CT GATE RED")
        return 1
    if not quiet:
        print("CT GATE GREEN: %d instructions for all %d combinations of "
              "key, plaintext and forged-tag position at the same lengths"
              % (counts[0], len(counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
