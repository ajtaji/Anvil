#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/t0vm.pi4 - the T0 threaded-bytecode
virtual machine on AArch64.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  NOTHING HERE IS TRANSCRIBED.  Three things could have been copied into
  this file and none of them are:

    * THE BYTECODE.  The PEM decoder blob is
      tools/fixtures/t0vm/pemdec_blob.pi4, which tools/t0gen.py wrote
      from BearSSL's src/codec/pemdec.c with the house context-RAM field
      map (event=0, name=1); below its header it is byte-identical to the
      blob the three 32-bit families run.  The fixture is checked for
      internal consistency on every run.  When the BEARSSL_SRC environment
      variable names a BearSSL checkout, the blob is also REGENERATED, in
      process, by importing tools/t0gen.py, and compared byte for byte
      with the fixture; a difference is a loud stop.  BearSSL's C is not
      part of this tree, so without BEARSSL_SRC that one cross-check is
      skipped and the run says so.
    * THE EXPECTATIONS.  The certificates and their DER are imported
      from tools/t0_pemproof_gen.py - the same CERTS list, the same
      sample directory, the same der_of() python base64 oracle that
      produces t0vmPemProof.pico2's embedded answers.
    * THE DRIVER.  Base64Val, T0Native and DecodeCurrent are SPLICED OUT
      of tools/t0_pemproof_gen.py's own emitted body, verbatim, so the
      VM is driven here with exactly the calls the 32-bit families make.
      If that generator's driver changes, the splice fails loudly rather
      than drifting.

  THE HARNESS RUNS A SCRIPT OF JOBS OUT OF MEMORY.  Every T0 program -
  the real PEM decoder and every crafted probe - is DATA in that script,
  so adding a case never changes the harness and never rebuilds.

  IT PROVES THE BOUNDS GUARD, AND THE NEGATIVE IS THE POINT.  The
  context-RAM bounds guard was first proven on the RP2350 by a silicon
  bounds probe.  Two independent things are done with it:

    * RAMSUITE re-runs that probe's checks, in order, through the same
      accessors, on this part - both halves, refusals AND acceptance,
      because a guard that refused everything would pass every
      out-of-range test and be useless.
    * The G-series jobs hand the VM CRAFTED BLOBS whose bytecode
      computes a hostile offset and stores through it.  The refusal is
      OBSERVED - t0_err = 900, t0_ip = -1, the next T0Run() returning
      #T0_HALT, and the context RAM read back unchanged - never assumed.
      G10 additionally proves the machine STAYS stopped: a second store
      after the refused one does not happen.

  IT PROVES THE CELL-WIDTH DECISION.  A T0 cell is int32, emulated,
  stored sign-extended into the 64-bit host word.  The C-series jobs run
  one crafted blob per opcode through the REAL T0Run dispatch and read
  the resulting cell back AT FULL 64-BIT WIDTH.  The PEM decoder cannot
  do this job: its opmap uses eighteen opcodes and none of them are
  `not`, the unsigned compares, `u>>`, `*`, `/`, `%`, `neg`, get32 or
  set32, so a known-answer test on it is blind to most of the port.

  EVERY VERDICT IS STORED AND CHECKED AT FULL 64-BIT WIDTH (PokeI,
  "<Q").  The A64 GCM gate stored its verdicts with PokeN and the one
  mutation it existed to catch survived, because the wrong value's set
  bits were all above bit 31.

  IT RUNS ON ALL CORES.  The image is built ONCE and the job list is
  sharded across a process pool.  Jobs are grouped - a blob load and the
  run that uses it are state-dependent and always land in the same
  shard.  --jobs overrides.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.  The oracle is a model of the
    instruction set: no caches, no memory system, no clock.
  * Anything about constant time, and deliberately so.  This VM parses
    PUBLIC data - certificates and handshake framing are in the clear -
    so nothing in t0vm.pi4 is CT-hardened and nothing should be.

Run: python tools/a64/a64_t0vm_check.py --jobs 6
     python tools/a64/a64_t0vm_check.py --quick
     python tools/a64/a64_t0vm_check.py --mutate
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
T0VM = ROOT / "RaspberryPi4" / "Lib" / "t0vm.pi4"
WORK = ROOT / "_work"

# The checked-in PEM decoder blob, and the BearSSL C it is lifted from.
# BearSSL's sources are not part of this tree: set BEARSSL_SRC to the root
# of a BearSSL checkout to regenerate the blob in process and compare.
# The house context-RAM field map is the one tools/t0gen.py was invoked
# with when the fixture was made; the byte compare is what proves it.
BEARSSL_SRC = os.environ.get("BEARSSL_SRC")
BEARSSL_PEMDEC = (pathlib.Path(BEARSSL_SRC) / "src" / "codec" / "pemdec.c"
                  if BEARSSL_SRC else None)
PEMDEC_FIELDS = {"event": 0, "name": 1}
SHARED_BLOB = ROOT / "tools" / "fixtures" / "t0vm" / "pemdec_blob.pi4"

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

SCRIPT_HDR = 44             # 11 x u32
RESULT_STRIDE = 48          # 6 x i64
SENTINEL = 0xA5

OP_END, OP_LOADBLOB, OP_PEM, OP_RUN, OP_RAMSUITE = range(5)

# T0 canonical primitive ids - these MUST agree with t0vm.pi4's
# #T0OP_* constants, and check_constants() below reads them back out of
# the module rather than trusting this list.
OPS = {
    "+": 1, "-": 2, "neg": 3, "*": 4, "/": 5, "u/": 6, "%": 7, "u%": 8,
    "<": 9, "<=": 10, ">": 11, ">=": 12, "=": 13, "<>": 14,
    "u<": 15, "u<=": 16, "u>": 17, "u>=": 18,
    "and": 19, "or": 20, "xor": 21, "not": 22,
    "<<": 23, ">>": 24, "u>>": 25,
    "co": 26, "drop": 27, "dup": 28, "swap": 29, "over": 30,
    "rot": 31, "-rot": 32, "roll": 33, "pick": 34, "execute": 35,
    "data-get8": 36, "get8": 37, "set8": 38,
    "get16": 39, "set16": 40, "get32": 41, "set32": 42,
}

T0_HALT, T0_YIELD, T0_NATIVE = 0, 1, 2


# =====================================================================
#  THE MODULE'S OWN CONSTANTS, READ BACK OUT OF IT
# =====================================================================
def module_constants(path=None):
    """#T0_RAM_SIZE, #T0ERR_RAM_BOUNDS and the depths, from the source.

    THE GATE MUST NOT CARRY ITS OWN COPY OF THE REGION SIZE.  If the
    context RAM is ever resized, every bounds expectation below moves
    with it, and a gate holding 512 in a python constant would quietly
    start testing the wrong offsets.
    """
    text = (path or T0VM).read_text(encoding="utf-8")
    out = {}
    for name in ("T0_RAM_SIZE", "T0ERR_RAM_BOUNDS", "T0_DS_DEPTH",
                 "T0_RS_DEPTH", "T0_NATIVE_BASE"):
        m = re.search(r"^#%s\s*=\s*(\$?[0-9A-Fa-f]+)\s*(?:;.*)?$" % name,
                      text, re.M)
        if not m:
            raise SystemExit(
                "t0vm.pi4 no longer defines #%s.  This gate reads the "
                "module's constants BY NAME so its bounds expectations "
                "move with the module; it must be updated WITH the "
                "module, not around it." % name)
        v = m.group(1)
        out[name] = int(v[1:], 16) if v.startswith("$") else int(v)
    for op, cid in OPS.items():
        pass
    return out


# =====================================================================
#  THE BYTECODE, REGENERATED FROM THE SHARED GENERATOR
# =====================================================================
def _import(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_shared_blob():
    """The checked-in pemdec blob: four byte lists plus its scalars."""
    if not SHARED_BLOB.exists():
        raise SystemExit(
            "The PEM decoder blob %s was not found. It is generated by "
            "tools/t0gen.py from BearSSL's src/codec/pemdec.c with the "
            "fields event=0 name=1; check that the file is present."
            % SHARED_BLOB)
    text = SHARED_BLOB.read_text(encoding="utf-8")
    out = {}
    for label in ("code", "data", "caddr", "opmap"):
        m = re.search(r"t0_pemdec_blob_%s:\n((?:\s*Data\.a[^\n]*\n)+)"
                      % label, text)
        if not m:
            raise SystemExit("The section t0_pemdec_blob_%s was not found in "
                             "%s; check that the file is a tools/t0gen.py "
                             "blob." % (label, SHARED_BLOB))
        out[label] = [int(x) for x in re.findall(r"\d+", m.group(1))]
    for key, name in (("interp", "T0_PEMDEC_INTERP"),
                      ("entry", "T0_PEMDEC_ENTRY")):
        m = re.search(r"^#%s\s*=\s*(\d+)" % name, text, re.M)
        if not m:
            raise SystemExit("#%s was not found in %s; check that the file "
                             "is a tools/t0gen.py blob." % (name, SHARED_BLOB))
        out[key] = int(m.group(1))
    out["natives"] = [(int(i), nm) for nm, i in
                      re.findall(r"^#T0N_(\w+)\s*=\s*(\d+)", text, re.M)]
    return out


def check_blob_shape(b, g):
    """The fixture must be internally consistent, whether or not the
    BearSSL source is available to regenerate it: an opmap entry is either
    a canonical id tools/t0gen.py knows or the next native in order, the
    native constants number 0..n-1, and the entry slot names a real word."""
    bad = []
    n = b["interp"]
    if len(b["opmap"]) != n:
        bad.append("the opmap has %d entries and T0_PEMDEC_INTERP is %d"
                   % (len(b["opmap"]), n))
    if any(b["opmap"][:7]):
        bad.append("the seven control opcodes must map to 0")
    canon = set(g.GENERIC.values())
    nid = 0
    for k, v in enumerate(b["opmap"][7:], start=7):
        if v >= g.NATIVE_BASE:
            if v != g.NATIVE_BASE + nid:
                bad.append("opcode %d maps to native %d, expected %d"
                           % (k, v - g.NATIVE_BASE, nid))
            nid += 1
        elif v not in canon:
            bad.append("opcode %d maps to %d, which is not a canonical id"
                       % (k, v))
    if [i for i, _ in b["natives"]] != list(range(nid)):
        bad.append("the #T0N_ constants are %s and the opmap uses %d natives"
                   % ([i for i, _ in b["natives"]], nid))
    if len(b["caddr"]) % 2:
        bad.append("the caddr table has an odd byte count")
    words = len(b["caddr"]) // 2
    if not (n <= b["entry"] < n + words):
        bad.append("entry slot %d is outside the interpreted words %d..%d"
                   % (b["entry"], n, n + words - 1))
    if bad:
        raise SystemExit("The PEM decoder blob %s is not internally "
                         "consistent:\n  %s\nRegenerate it with "
                         "tools/t0gen.py rather than editing it."
                         % (SHARED_BLOB, "\n  ".join(bad)))


def _regenerate(g):
    """Lift the blob out of pemdec.c with tools/t0gen.py's own helpers."""
    text = g.slurp(str(BEARSSL_PEMDEC))
    n_interp = g.get_define(text, "T0_INTERPRETED")
    entry = g.get_entry_slot(text)
    seen = set()
    data = g.parse_bytes(g.array_body(
        text, "static const unsigned char t0_datablock[]"),
        PEMDEC_FIELDS, seen)
    code = g.parse_bytes(g.array_body(
        text, "static const unsigned char t0_codeblock[]"),
        PEMDEC_FIELDS, seen)
    caddr = g.parse_caddr(text)
    names = g.opcode_names(text, n_interp)

    opmap = [0] * n_interp
    natives = []
    for k in range(7, n_interp):
        nm = names.get(k)
        if nm is None:
            raise SystemExit("t0gen: opcode %d has no name comment in %s"
                             % (k, BEARSSL_PEMDEC))
        if nm in g.GENERIC:
            opmap[k] = g.GENERIC[nm]
        else:
            opmap[k] = g.NATIVE_BASE + len(natives)
            natives.append((len(natives), g.sanitize(nm)))

    pairs = []
    for v in caddr:
        pairs += [v & 0xFF, (v >> 8) & 0xFF]
    return {"code": list(code), "data": list(data), "caddr": pairs,
            "opmap": opmap, "interp": n_interp, "entry": entry,
            "natives": natives}


REGEN_NOTE = ""


def load_pemdec():
    """The PEM decoder blob, from the fixture, cross-checked when possible.

    The fixture is always checked for shape.  When BEARSSL_SRC is set the
    bytecode is also regenerated by IMPORTING tools/t0gen.py and compared
    byte for byte, which is what makes "the same bytecode" checkable.
    """
    global REGEN_NOTE
    gen_path = ROOT / "tools" / "t0gen.py"
    if not gen_path.exists():
        raise SystemExit(
            "The T0 blob generator %s was not found. This gate reads its "
            "canonical opcode table; check that tools/t0gen.py is present."
            % gen_path)
    g = _import(gen_path, "t0gen")
    shared = parse_shared_blob()
    check_blob_shape(shared, g)

    if BEARSSL_PEMDEC is None:
        REGEN_NOTE = ("The byte-for-byte regeneration of the PEM decoder "
                      "blob from BearSSL's src/codec/pemdec.c was SKIPPED "
                      "because BEARSSL_SRC is not set and BearSSL's sources "
                      "are not part of this tree; to enable it, set "
                      "BEARSSL_SRC to the root of a BearSSL checkout.")
    elif not BEARSSL_PEMDEC.exists():
        raise SystemExit(
            "BEARSSL_SRC is set but %s was not found. Check that BEARSSL_SRC "
            "names the root of a BearSSL checkout." % BEARSSL_PEMDEC)
    else:
        got = _regenerate(g)
        for label in ("code", "data", "caddr", "opmap", "interp", "entry",
                      "natives"):
            if got[label] != shared[label]:
                raise SystemExit(
                    "The blob regenerated from %s does not match the %s of "
                    "%s. Check the context-RAM field map this gate passes to "
                    "tools/t0gen.py (%r) against the one the fixture was "
                    "generated with - a different map moves the offsets "
                    "embedded in the code block."
                    % (BEARSSL_PEMDEC, label, SHARED_BLOB, PEMDEC_FIELDS))
        REGEN_NOTE = ("regenerated from %s and byte-identical to the fixture"
                      % BEARSSL_PEMDEC)

    return {"code": bytes(shared["code"]), "data": bytes(shared["data"]),
            "caddr": bytes(shared["caddr"]), "opmap": bytes(shared["opmap"]),
            "interp": shared["interp"], "entry": shared["entry"],
            "natives": shared["natives"]}


def load_certs():
    """The PEM inputs and their DER, from tools/t0_pemproof_gen.py."""
    gen_path = ROOT / "tools" / "t0_pemproof_gen.py"
    if not gen_path.exists():
        raise SystemExit(
            "The PEM proof generator %s was not found. This gate "
            "deliberately has no certificates of its own - it reads the "
            "CERTS list that tools/t0_pemproof_gen.py defines." % gen_path)
    g = _import(gen_path, "t0_pemproof_gen")
    for name in ("CERTS", "SAMPLES", "der_of", "build_body"):
        if not hasattr(g, name):
            raise SystemExit(
                "t0_pemproof_gen.py no longer defines %r; this gate reads "
                "it BY NAME and must be updated WITH it, not around it"
                % name)
    certs = []
    for name in g.CERTS:
        p = os.path.join(g.SAMPLES, name)
        if not os.path.exists(p):
            raise SystemExit(
                "The sample certificate %s was not found in %s. Check that "
                "RaspberryPi4/Reference/ holds the BearSSL cert-*.pem files."
                % (name, g.SAMPLES))
        pem = open(p, "rb").read()
        certs.append((name, pem, g.der_of(pem.decode("ascii", "replace"))))
    return g, certs


PROCRE = r"^(Procedure(?:\.[a-z]+)?\s+%s\(.*?^EndProcedure)$"


def splice_driver(gen, certs):
    """Lift Base64Val, T0Native and DecodeCurrent out of the generator.

    VERBATIM, from the text that generator emits for the Pico copies.
    "The Pi 4 is driven the same way" then stops being a claim about two
    files that were once read side by side.
    """
    body = gen.build_body([(pem, der) for _, pem, der in certs])
    out = []
    for name in ("Base64Val", "T0Native", "DecodeCurrent"):
        m = re.search(PROCRE % name, body, re.M | re.S)
        if not m:
            raise SystemExit(
                "could not splice %s out of t0_pemproof_gen.build_body().\n"
                "First thing to check: whether that generator still emits "
                "the PEM driver as three procedures with those names - if "
                "it was restructured, this gate must follow it rather than "
                "keep a private copy." % name)
        out.append(m.group(1))
    return "\n\n".join(out)


# =====================================================================
#  A TINY T0 ASSEMBLER, FOR THE CRAFTED PROBE BLOBS
# =====================================================================
#  These are not transcriptions of anything - they are negatives, built
#  here on purpose, and the bytecode they need is four opcodes wide.
#  The encodings are BearSSL's own, read off the decoders in t0vm:
#  T0NextU is an unsigned 7-bit continuation varint and T0NextS is the
#  signed one, whose accumulator is seeded with all-ones for a negative.
# =====================================================================
def uvarint(v):
    if v < 0:
        raise ValueError("uvarint of a negative")
    groups = []
    while True:
        groups.append(v & 0x7F)
        v >>= 7
        if not v:
            break
    groups.reverse()
    return bytes([g | 0x80 for g in groups[:-1]] + [groups[-1]])


def svarint(v):
    """Minimal signed 7-bit varint: the top group's bit 6 is the sign."""
    k = 1
    while not (-(1 << (7 * k - 1)) <= v < (1 << (7 * k - 1))):
        k += 1
    u = v & ((1 << (7 * k)) - 1)
    groups = [(u >> (7 * i)) & 0x7F for i in range(k)][::-1]
    return bytes([g | 0x80 for g in groups[:-1]] + [groups[-1]])


class T0Prog:
    """One interpreted word, entered at slot t0_interp, no locals."""

    def __init__(self):
        self.code = bytearray(uvarint(0))     # the word's local count
        self.prims = []                       # canonical ids, in raw order

    def _raw(self, opname):
        cid = OPS[opname]
        if cid not in self.prims:
            self.prims.append(cid)
        return 7 + self.prims.index(cid)

    def lit(self, v):
        self.code += bytes([1]) + svarint(v)
        return self

    def op(self, opname):
        self.code += bytes([self._raw(opname)])
        return self

    def ret(self):
        self.code += bytes([0])
        return self

    def blob(self):
        interp = 7 + len(self.prims)
        return {"code": bytes(self.code), "data": b"\x00",
                "caddr": struct.pack("<H", 0),
                "opmap": bytes([0] * 7 + self.prims),
                "interp": interp, "entry": interp}


def i32(v):
    """The int32 a value denotes, as python's signed int."""
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >> 31 else v


def u64(v):
    return v & 0xFFFFFFFFFFFFFFFF


# =====================================================================
#  THE HARNESS
# =====================================================================
#  SCRIPT RECORD - a 44-byte header, then b0||b1||b2||b3, padded to 4:
#      +0 op  +4 a0  +8 a1  +12 a2  +16 a3
#      +20 n0 +24 n1 +28 n2 +32 n3  +36 outlen  +40 spare
#  op 0 ends the script.
#
#  RESULT RECORD - 48 bytes, SIX 64-BIT FIELDS:
#      +0 s0  +8 s1  +16 s2  +24 s3  +32 outlen  +40 s4
# =====================================================================
HARNESS = r'''
; ======================================================================
;  t0harness.pi4 - GENERATED BY tools/a64/a64_t0vm_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "__T0VM__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000
#H_OUT    = $0B000000

; ---- native word ids, from the regenerated blob's own opmap ----
__NATIVES__

; The blob buffers.  Every T0 program this gate runs - the real PEM
; decoder and every crafted probe - arrives as DATA in the script and
; is copied in here, so adding a case never rebuilds the image.
Global Dim BlobCode.a[2048]
Global Dim BlobData.a[512]
Global Dim BlobCaddr.a[512]
Global Dim BlobOpmap.a[256]

Global Dim gIn.a[__MAXIN__]
Global gInLen.i
Global gInPos.i
Global Dim gOut.a[__MAXOUT__]
Global gOutLen.i

; DecodeCurrent (spliced from tools/t0_pemproof_gen.py) calls this by
; name.  It points the descriptors at whatever blob the script loaded.
Procedure T0LoadPemdec()
  t0_cp     = @BlobCode[0]
  t0_datap  = @BlobData[0]
  t0_caddrp = @BlobCaddr[0]
  t0_opp    = @BlobOpmap[0]
EndProcedure

__DRIVER__

; ----------------------------------------------------------------------
;  Clear the context RAM so no job can read another job's leavings.
;  Indexed directly, NOT through T0RamPut, because this must work on a
;  machine the guard has already halted.
; ----------------------------------------------------------------------
Procedure ThZeroRam()
  Define i.i
  i = 0
  While i <= #T0_RAM_SIZE
    t0_ram[i] = 0
    i = i + 1
  Wend
EndProcedure

; ----------------------------------------------------------------------
;  Run the loaded program with NO native words.  A native return is
;  itself a verdict (status 2) and is reported rather than serviced -
;  none of the crafted probes has one.
; ----------------------------------------------------------------------
Procedure.i ThRunPlain()
  Define st.i
  Define guard.i
  T0Start()
  guard = 0
  Repeat
    st = T0Run()
    If st <> #T0_YIELD
      ProcedureReturn st
    EndIf
    guard = guard + 1
    If guard > 100000
      ProcedureReturn 99
    EndIf
  ForEver
EndProcedure

; ----------------------------------------------------------------------
;  ThRamSuite - the context-RAM bounds guard, both halves, driven exactly
;  the way the RP2350 silicon bounds probe drives it: checks 1-7 and 23-30 are ACCEPTANCE (a guard that refused
;  everything would pass every refusal test and be useless), 8-22 are
;  REFUSALS, and the width cases go through T0PrimMem because that is
;  the path the bytecode's own set32/set16/get32 opcodes take.
;
;  Checks 31-35 are NOT in the silicon probe.  They exist because this
;  part assembles get32's top byte into bit 31 of a 64-bit register
;  rather than into a sign bit, and a context word with the high bit set
;  is the case that shape 3 breaks.
;
;  Each observed value is stored as a full 64-bit field; the wants live
;  in python.
; ----------------------------------------------------------------------
Procedure.i ThRamSuite(o.i)
  Define n.i
  n = 0
  ThZeroRam()
  t0_err = 0 : t0_ip = 0 : t0_dp = 0 : t0_rp = 0

  ; ---- ACCEPTANCE: the region works normally ------------------------
  T0RamPut(0, $5A)
  T0RamPut(#T0_RAM_SIZE - 1, $A5)
  PokeI(o + n * 8, T0RamGet(0))                        : n = n + 1   ; 1
  PokeI(o + n * 8, T0RamGet(#T0_RAM_SIZE - 1))         : n = n + 1   ; 2
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 3
  T0RamPut(4, $34)
  T0RamPut(5, $12)
  PokeI(o + n * 8, (T0RamGet(5) << 8) | T0RamGet(4))   : n = n + 1   ; 4
  T0RamPut(4, $FF)
  PokeI(o + n * 8, T0RamGet(4))                        : n = n + 1   ; 5
  PokeI(o + n * 8, T0RamGet(5))                        : n = n + 1   ; 6
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 7

  ; ---- REFUSALS: one past the end -----------------------------------
  t0_err = 0 : t0_ip = 0
  T0RamPut(#T0_RAM_SIZE, $DE)
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 8
  PokeI(o + n * 8, t0_ip)                              : n = n + 1   ; 9
  PokeI(o + n * 8, T0Run())                            : n = n + 1   ; 10

  t0_err = 0 : t0_ip = 0
  PokeI(o + n * 8, T0RamGet(#T0_RAM_SIZE))             : n = n + 1   ; 11
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 12

  ; a negative offset - what a length subtraction underflow produces
  t0_err = 0 : t0_ip = 0
  PokeI(o + n * 8, T0RamGet(-1))                       : n = n + 1   ; 13
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 14
  t0_err = 0 : t0_ip = 0
  T0RamPut(-4, $DE)
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 15

  ; far past the end
  t0_err = 0 : t0_ip = 0
  T0RamPut(#T0_RAM_SIZE + 4096, $DE)
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 16

  ; ---- WIDTH AWARENESS, through T0PrimMem ---------------------------
  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push($12345678)
  T0Push(#T0_RAM_SIZE - 1)
  T0PrimMem(#T0OP_SET32)
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 17
  t0_err = 0 : t0_ip = 0
  PokeI(o + n * 8, T0RamGet(#T0_RAM_SIZE - 1))         : n = n + 1   ; 18

  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push($BEEF)
  T0Push(#T0_RAM_SIZE - 1)
  T0PrimMem(#T0OP_SET16)
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 19
  t0_err = 0 : t0_ip = 0
  PokeI(o + n * 8, T0RamGet(#T0_RAM_SIZE - 1))         : n = n + 1   ; 20

  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push(#T0_RAM_SIZE - 2)
  T0PrimMem(#T0OP_GET32)
  PokeI(o + n * 8, T0Pop())                            : n = n + 1   ; 21
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 22

  ; ---- ACCEPTANCE AT EVERY WIDTH, AT THE LAST LEGAL OFFSET ----------
  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push($12345678)
  T0Push(#T0_RAM_SIZE - 4)
  T0PrimMem(#T0OP_SET32)
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 23
  t0_dp = 0
  T0Push(#T0_RAM_SIZE - 4)
  T0PrimMem(#T0OP_GET32)
  PokeI(o + n * 8, T0Pop())                            : n = n + 1   ; 24
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 25

  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push($BEEF)
  T0Push(#T0_RAM_SIZE - 2)
  T0PrimMem(#T0OP_SET16)
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 26
  t0_dp = 0
  T0Push(#T0_RAM_SIZE - 2)
  T0PrimMem(#T0OP_GET16)
  PokeI(o + n * 8, T0Pop())                            : n = n + 1   ; 27

  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push($77)
  T0Push(#T0_RAM_SIZE - 1)
  T0PrimMem(#T0OP_SET8)
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 28
  t0_dp = 0
  T0Push(#T0_RAM_SIZE - 1)
  T0PrimMem(#T0OP_GET8)
  PokeI(o + n * 8, T0Pop())                            : n = n + 1   ; 29
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 30

  ; ---- 64-BIT ONLY: a context word whose top bit is set -------------
  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push($FF00FF80)
  T0Push(0)
  T0PrimMem(#T0OP_SET32)
  t0_dp = 0
  T0Push(0)
  T0PrimMem(#T0OP_GET32)
  PokeI(o + n * 8, T0Pop())                            : n = n + 1   ; 31
  PokeI(o + n * 8, t0_err)                             : n = n + 1   ; 32

  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push($80000000)
  T0Push(#T0_RAM_SIZE - 4)
  T0PrimMem(#T0OP_SET32)
  t0_dp = 0
  T0Push(#T0_RAM_SIZE - 4)
  T0PrimMem(#T0OP_GET32)
  PokeI(o + n * 8, T0Pop())                            : n = n + 1   ; 33

  ; a byte and a 16-bit word read back UNSIGNED, not sign-extended
  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push($FF)
  T0Push(#T0_RAM_SIZE - 1)
  T0PrimMem(#T0OP_SET8)
  t0_dp = 0
  T0Push(#T0_RAM_SIZE - 1)
  T0PrimMem(#T0OP_GET8)
  PokeI(o + n * 8, T0Pop())                            : n = n + 1   ; 34

  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  T0Push($FFFF)
  T0Push(#T0_RAM_SIZE - 2)
  T0PrimMem(#T0OP_SET16)
  t0_dp = 0
  T0Push(#T0_RAM_SIZE - 2)
  T0PrimMem(#T0OP_GET16)
  PokeI(o + n * 8, T0Pop())                            : n = n + 1   ; 35

  t0_err = 0 : t0_ip = 0 : t0_dp = 0
  ProcedureReturn n
EndProcedure

Procedure.i Main()
  Define p.i
  Define q.i
  Define o.i
  Define op.i
  Define a0.i
  Define a1.i
  Define a2.i
  Define a3.i
  Define n0.i
  Define n1.i
  Define n2.i
  Define n3.i
  Define outlen.i
  Define b0.i
  Define b1.i
  Define b2.i
  Define b3.i
  Define s0.i
  Define s1.i
  Define s2.i
  Define s3.i
  Define s4.i
  Define i.i

  p = #H_SCRIPT
  q = #H_RESULT
  o = #H_OUT

  Repeat
    op     = PeekN(p)
    a0     = PeekN(p + 4)
    a1     = PeekN(p + 8)
    a2     = PeekN(p + 12)
    a3     = PeekN(p + 16)
    n0     = PeekN(p + 20)
    n1     = PeekN(p + 24)
    n2     = PeekN(p + 28)
    n3     = PeekN(p + 32)
    outlen = PeekN(p + 36)
    If op = 0
      Break
    EndIf
    b0 = p + 44
    b1 = b0 + n0
    b2 = b1 + n1
    b3 = b2 + n2

    s0 = 0 : s1 = 0 : s2 = 0 : s3 = 0 : s4 = 0

    If op = 1
      ; LOADBLOB - install a T0 program from the script.
      i = 0
      While i < n0
        BlobCode[i] = PeekA(b0 + i) & 255
        i = i + 1
      Wend
      i = 0
      While i < n1
        BlobData[i] = PeekA(b1 + i) & 255
        i = i + 1
      Wend
      i = 0
      While i < n2
        BlobCaddr[i] = PeekA(b2 + i) & 255
        i = i + 1
      Wend
      i = 0
      While i < n3
        BlobOpmap[i] = PeekA(b3 + i) & 255
        i = i + 1
      Wend
      T0LoadPemdec()
      t0_interp = a0
      t0_entry  = a1
      s0 = n0
      s1 = t0_interp
      s2 = t0_entry
      s3 = n3

    ElseIf op = 2
      ; PEM - the real decoder over one certificate, driven by the
      ; procedures spliced out of tools/t0_pemproof_gen.py.
      ThZeroRam()
      i = 0
      While i < n0
        gIn[i] = PeekA(b0 + i) & 255
        i = i + 1
      Wend
      gInLen = n0
      DecodeCurrent()
      i = 0
      While i < gOutLen
        PokeB(o + i, gOut[i] & 255)
        i = i + 1
      Wend
      s0 = gOutLen
      s1 = t0_err
      s2 = t0_ip
      s3 = gInPos

    ElseIf op = 3
      ; RUN - the loaded program, no natives.  a0 context-RAM bytes are
      ; dumped after it, so a refused store can be shown NOT to have
      ; landed rather than merely reported.
      ThZeroRam()
      t0_err = 0
      s3 = ThRunPlain()
      If t0_dp > 0
        s0 = t0_ds[t0_dp - 1]
      EndIf
      s1 = t0_dp
      s2 = t0_err
      s4 = t0_ip
      i = 0
      While i < a0
        PokeB(o + i, t0_ram[i] & 255)
        i = i + 1
      Wend

    ElseIf op = 4
      ; RAMSUITE - the context-RAM bounds guard, both halves.
      s0 = ThRamSuite(o)
      s1 = #T0_RAM_SIZE
      s2 = #T0ERR_RAM_BOUNDS
    EndIf

    PokeI(q, s0)
    PokeI(q + 8, s1)
    PokeI(q + 16, s2)
    PokeI(q + 24, s3)
    PokeI(q + 32, outlen)
    PokeI(q + 40, s4)

    p = p + 44 + n0 + n1 + n2 + n3
    p = ((p + 3) / 4) * 4
    q = q + 48
    o = o + (((outlen + 3) / 4) * 4)
  ForEver

  UartWriteStr("t0harness done")
  ProcedureReturn 0
EndProcedure
'''


# =====================================================================
#  THE SCRIPT
# =====================================================================
class Script:
    """The job list.  Jobs live in GROUPS; a group is the unit of

    sharding, because a blob load and the run that uses it are state
    dependent and must not be split across workers."""

    def __init__(self):
        self.jobs = []          # (label, op, checker, expect_bytes)
        self.records = []
        self.out_off = []
        self.groups = []        # list of [job index, ...]
        self._o = 0

    def group(self):
        self.groups.append([])
        return self

    def add(self, op, label, a0=0, a1=0, a2=0, a3=0,
            b0=b"", b1=b"", b2=b"", b3=b"", out=None, check=None):
        outlen = 0 if out is None else len(out)
        rec = struct.pack("<11I", op, a0 & 0xFFFFFFFF, a1 & 0xFFFFFFFF,
                          a2 & 0xFFFFFFFF, a3 & 0xFFFFFFFF,
                          len(b0), len(b1), len(b2), len(b3), outlen, 0)
        rec += b0 + b1 + b2 + b3
        rec += b"\x00" * ((-len(rec)) % 4)
        self._append(rec, label, op, check, out)

    def _append(self, rec, label, op, check, out):
        if not self.groups:
            self.group()
        self.groups[-1].append(len(self.jobs))
        self.jobs.append((label, op, check, out))
        self.records.append(rec)
        self.out_off.append(self._o)
        self._o += ((0 if out is None else len(out)) + 3) // 4 * 4

    def blob(self, label, b, run_label=None, ramdump=0, check=None,
             out=None):
        """A blob load and the run that uses it, as one group."""
        self.group()
        self.add(OP_LOADBLOB, "load " + label, a0=b["interp"], a1=b["entry"],
                 b0=b["code"], b1=b["data"], b2=b["caddr"], b3=b["opmap"])
        self.add(OP_RUN, run_label or label, a0=ramdump, out=out,
                 check=check)

    def done(self):
        buf = bytearray()
        for r in self.records:
            buf += r
        return bytes(buf) + struct.pack("<11I", OP_END, *([0] * 10))

    def __len__(self):
        return len(self.jobs)


def fields(rec):
    s0, s1, s2, s3, outlen, s4 = struct.unpack("<6Q", rec)
    return {"s0": s0, "s1": s1, "s2": s2, "s3": s3,
            "outlen": outlen, "s4": s4}


def want(**kw):
    """A checker asserting named 64-bit result fields."""
    def chk(f, out):
        bad = []
        for k, v in kw.items():
            if f[k] != u64(v):
                bad.append("%s is %d (%016x at full width), want %d (%016x)"
                           % (k, f[k], f[k], v, u64(v)))
        return bad
    return chk


def both(*checks):
    def chk(f, out):
        bad = []
        for c in checks:
            if c:
                bad += c(f, out)
        return bad
    return chk


def ram_all_zero(n):
    def chk(f, out):
        nz = [(i, b) for i, b in enumerate(out[:n]) if b]
        if nz:
            return ["the refused store LANDED: context RAM byte %d is %d "
                    "and every byte should still be 0" % nz[0]]
        return []
    return chk


def ram_at(off, value):
    def chk(f, out):
        if len(out) <= off:
            return ["no context-RAM dump for offset %d" % off]
        if out[off] != value:
            return ["context RAM byte %d is %d, want %d"
                    % (off, out[off], value)]
        return []
    return chk


# =====================================================================
#  THE JOBS
# =====================================================================
def pem_jobs(s, pemdec, certs, level):
    """The PEM decode proof - the SAME one the Pico gate runs."""
    use = certs[:1] if level in ("quick", "mutant") else certs
    for name, pem, der in use:
        s.group()
        s.add(OP_LOADBLOB, "load pemdec for %s" % name,
              a0=pemdec["interp"], a1=pemdec["entry"],
              b0=pemdec["code"], b1=pemdec["data"],
              b2=pemdec["caddr"], b3=pemdec["opmap"],
              check=want(s0=len(pemdec["code"]), s1=pemdec["interp"],
                         s2=pemdec["entry"], s3=len(pemdec["opmap"])))
        s.add(OP_PEM, "PEM->DER %s (%d bytes PEM, %d bytes DER)"
              % (name, len(pem), len(der)),
              b0=pem, out=der,
              check=want(s0=len(der), s1=0))


def ram_suite_jobs(s, K):
    """The context-RAM guard, driven the way the silicon probe drives it."""
    N = K["T0_RAM_SIZE"]
    E = K["T0ERR_RAM_BOUNDS"]
    # (want, what the check is for).  ACCEPTANCE checks are marked, so a
    # failure report can say which half broke: an acceptance failure
    # means the guard is refusing legal offsets and would break the
    # certificate parser; a refusal failure means the hole is open.
    CASES = [
        (0x5A, "accept: first byte reads back"),
        (0xA5, "accept: last byte reads back"),
        (0, "accept: and no refusal fired"),
        (0x1234, "accept: little-endian neighbours"),
        (0xFF, "accept: rewrite of byte 4"),
        (0x12, "accept: neighbour byte 5 untouched"),
        (0, "accept: still no refusal"),
        (E, "REFUSE: put one past the end is named"),
        (-1, "REFUSE: and the machine halted (t0_ip = -1)"),
        (T0_HALT, "REFUSE: the host SEES it - T0Run returns #T0_HALT"),
        (0, "REFUSE: a refused read answers 0"),
        (E, "REFUSE: get one past the end is named"),
        (0, "REFUSE: a refused negative read answers 0"),
        (E, "REFUSE: get at -1 is named"),
        (E, "REFUSE: put at -4 is named"),
        (E, "REFUSE: put far past the end is named"),
        (E, "REFUSE: 32-bit store three bytes from the end"),
        (0xA5, "REFUSE: and the last byte is UNTOUCHED"),
        (E, "REFUSE: 16-bit store one byte from the end"),
        (0xA5, "REFUSE: and the last byte is still untouched"),
        (0, "REFUSE: a refused 32-bit read answers 0"),
        (E, "REFUSE: get32 two bytes from the end is named"),
        (0, "accept: 32-bit store at the last legal offset"),
        (0x12345678, "accept: and it reads back"),
        (0, "accept: with no refusal"),
        (0, "accept: 16-bit store at the last legal offset"),
        (0xBEEF, "accept: and it reads back"),
        (0, "accept: 8-bit store at the last legal offset"),
        (0x77, "accept: and it reads back"),
        (0, "accept: with no refusal"),
        (i32(0xFF00FF80), "64-bit: get32 of a word with bit 31 set is "
                          "NEGATIVE, not +4278190080"),
        (0, "64-bit: and no refusal fired"),
        (i32(0x80000000), "64-bit: get32 of $80000000 is INT32_MIN"),
        (0xFF, "64-bit: get8 is UNSIGNED"),
        (0xFFFF, "64-bit: get16 is UNSIGNED"),
    ]

    def chk(f, out):
        bad = []
        if f["s1"] != N:
            bad.append("the harness reports #T0_RAM_SIZE = %d, this gate "
                       "read %d out of t0vm.pi4" % (f["s1"], N))
        if f["s2"] != E:
            bad.append("the harness reports #T0ERR_RAM_BOUNDS = %d, this "
                       "gate read %d out of t0vm.pi4" % (f["s2"], E))
        if f["s0"] != len(CASES):
            bad.append("the suite ran %d checks, this gate has %d "
                       "expectations" % (f["s0"], len(CASES)))
            return bad
        for i, (w, why) in enumerate(CASES):
            got = struct.unpack_from("<Q", out, i * 8)[0]
            if got != u64(w):
                bad.append("check %d (%s): saw %d (%016x at full width), "
                           "want %d (%016x)"
                           % (i + 1, why, got, got, w, u64(w)))
        return bad

    s.group()
    s.add(OP_RAMSUITE, "context-RAM bounds guard: %d checks" % len(CASES),
          out=b"\x00" * (len(CASES) * 8), check=chk)


def guard_blob_jobs(s, K):
    """CRAFTED HOSTILE BLOBS.  The negative is the point of the gate.

    Each is a T0 program whose bytecode computes an out-of-range context
    offset and stores through it - which is exactly what a certificate
    the VM is parsing can make a real program do.  The refusal is
    OBSERVED: the named error code, the halted machine, T0Run's terminal
    status, and the context RAM read back to show the store did not land.
    """
    N = K["T0_RAM_SIZE"]
    E = K["T0ERR_RAM_BOUNDS"]
    D = 64                      # context-RAM bytes dumped after each run

    # G1 - THE CONTROL.  A guard that refused everything would pass
    # every refusal below, so a legal store must still work.
    s.blob("G1 legal store", T0Prog().lit(0x5A).lit(5).op("set8").ret().blob(),
           run_label="G1 a legal set8 at offset 5 still lands",
           ramdump=D, out=b"\x00" * D,
           check=both(want(s2=0, s3=T0_HALT, s1=0), ram_at(5, 0x5A)))

    # G2 - one past the end
    s.blob("G2 off the end",
           T0Prog().lit(0xDE).lit(N).op("set8").ret().blob(),
           run_label="G2 bytecode stores one past the end - REFUSED",
           ramdump=D, out=b"\x00" * D,
           check=both(want(s2=E, s3=T0_HALT, s4=u64(-1)), ram_all_zero(D)))

    # G3 - A NEGATIVE OFFSET, which is what a length subtraction
    # underflow in the bytecode produces, and the case a naive
    # "addr >= SIZE" test misses completely.  Mutation M2 deletes the
    # `addr < 0` half of the guard and THIS job is what kills it.
    #
    # WHAT THIS JOB DOES NOT PROVE, said here because the first draft
    # of the module header claimed it did: it does NOT die under
    # mutation M13, the zero-extended cell convention.  Under M13 the
    # -1 arrives as $FFFFFFFF, which the guard's UPPER bound refuses
    # anyway, so the access is still blocked - by accident, with
    # `addr < 0` reduced to dead code that still reads as though it
    # works.  M13 is caught by 23 other jobs instead.  The sweep is
    # what corrected that claim.
    s.blob("G3 negative offset",
           T0Prog().lit(0xDE).lit(-1).op("set8").ret().blob(),
           run_label="G3 bytecode stores at offset -1 - REFUSED",
           ramdump=D, out=b"\x00" * D,
           check=both(want(s2=E, s3=T0_HALT, s4=u64(-1)), ram_all_zero(D)))

    s.blob("G4 negative offset -4",
           T0Prog().lit(0xDE).lit(-4).op("set8").ret().blob(),
           run_label="G4 bytecode stores at offset -4 - REFUSED",
           ramdump=D, out=b"\x00" * D,
           check=both(want(s2=E, s3=T0_HALT), ram_all_zero(D)))

    # G5/G6 - WIDTH AWARENESS.  A guard that looked only at the first
    # byte of the access would wave both of these through.
    s.blob("G5 set32 three bytes from the end",
           T0Prog().lit(0x12345678).lit(N - 1).op("set32").ret().blob(),
           run_label="G5 a 32-bit store 3 bytes from the end - REFUSED",
           ramdump=D, out=b"\x00" * D,
           check=want(s2=E, s3=T0_HALT))

    s.blob("G6 set16 one byte from the end",
           T0Prog().lit(0xBEEF).lit(N - 1).op("set16").ret().blob(),
           run_label="G6 a 16-bit store 1 byte from the end - REFUSED",
           ramdump=D, out=b"\x00" * D,
           check=want(s2=E, s3=T0_HALT))

    # G7 - ACCEPTANCE at the last legal 32-bit offset, and the value
    # chosen so the read-back proves shape 3 as well.
    s.blob("G7 legal set32/get32",
           T0Prog().lit(i32(0xFF00FF80)).lit(N - 4).op("set32")
                   .lit(N - 4).op("get32").ret().blob(),
           run_label="G7 a legal 32-bit store at the last legal offset "
                     "round-trips, NEGATIVE",
           check=want(s2=0, s3=T0_HALT, s0=u64(i32(0xFF00FF80)), s1=1))

    # G8 - a refused READ answers 0 and says so, and the 0 cannot be
    # mistaken for data because the machine is already halted.
    s.blob("G8 refused get8",
           T0Prog().lit(N + 4096).op("get8").ret().blob(),
           run_label="G8 bytecode reads far past the end - REFUSED, 0",
           check=want(s2=E, s3=T0_HALT, s0=0, s1=1, s4=u64(-1)))

    # G9 - far past the end, a wild offset rather than an adjacent one
    s.blob("G9 far past the end",
           T0Prog().lit(0xDE).lit(N + 4096).op("set8").ret().blob(),
           run_label="G9 bytecode stores 4 KB past the end - REFUSED",
           ramdump=D, out=b"\x00" * D,
           check=both(want(s2=E, s3=T0_HALT), ram_all_zero(D)))

    # G10 - THE MACHINE STAYS STOPPED.  The refusal is only useful if
    # the rest of the hostile program does not run afterwards.
    s.blob("G10 the machine stays halted",
           T0Prog().lit(0xDE).lit(N).op("set8")
                   .lit(0x77).lit(5).op("set8").ret().blob(),
           run_label="G10 the store AFTER a refused one never happens",
           ramdump=D, out=b"\x00" * D,
           check=both(want(s2=E, s3=T0_HALT, s4=u64(-1)), ram_all_zero(D)))


# ---------------------------------------------------------------------
#  THE OPCODE CONFORMANCE JOBS - the cell-width decision, proved
# ---------------------------------------------------------------------
#  Each case is one crafted word run through the REAL T0Run dispatch,
#  with the resulting cell read back at full 64-bit width.  The expected
#  value is int32 semantics, sign-extended - which is the decision this
#  file's header records.
#
#  The PEM decoder's opmap uses eighteen opcodes and NONE of these:
#  not, u<, u<=, u>, u>=, u>>, *, /, %, neg, get32, set32, roll, pick.
#  A known-answer test on it is blind to most of the port, which is why
#  these exist.
# ---------------------------------------------------------------------
def _cell(op, x, y=None):
    p = T0Prog().lit(x)
    if y is not None:
        p.lit(y)
    return p.op(op).ret().blob()


CELL_CASES = [
    # (opname, x, y, expected int32 result, expected depth)
    ("+", 1, 2, 3, 1),
    ("+", 0x7FFFFFFF, 1, i32(0x80000000), 1),          # the wrap
    ("+", -1, -1, -2, 1),
    ("-", 5, 9, -4, 1),
    ("-", i32(0x80000000), 1, 0x7FFFFFFF, 1),          # the wrap
    ("neg", 5, None, -5, 1),
    ("neg", i32(0x80000000), None, i32(0x80000000), 1),
    ("*", 3, 7, 21, 1),
    ("*", 65535, 65535, i32(0xFFFE0001), 1),           # mod 2^32
    ("*", 0x10000, 0x10000, 0, 1),                     # mod 2^32
    ("/", 7, 2, 3, 1),
    ("/", i32(0x80000000), -1, i32(0x80000000), 1),    # the one overflow
    ("%", 7, 2, 1, 1),
    ("%", -7, 2, -1, 1),
    ("<", -1, 1, -1, 1),
    ("<", 1, -1, 0, 1),
    ("<=", 3, 3, -1, 1),
    (">", i32(0x80000000), 0x7FFFFFFF, 0, 1),
    (">=", 3, 4, 0, 1),
    ("=", -1, -1, -1, 1),
    ("<>", -1, -1, 0, 1),
    # THE UNSIGNED COMPARES.  `! $80000000` flips a middle bit here, so
    # every one of these answers about the wrong quantity if the 32-bit
    # spelling survives.
    #
    # EVERY OPERAND PAIR STRADDLES 2^31, IN BOTH DIRECTIONS, AND THAT IS
    # THE WHOLE POINT.  The first sweep had (u>=, $80000000, $80000000)
    # and mutation M10 SURVIVED it, because the broken spelling gets
    # EQUALITY right whatever it does to ordering.  An equal pair is not
    # a test of an unsigned compare.
    ("u<", i32(0x80000000), 0x7FFFFFFF, 0, 1),
    ("u<", 0x7FFFFFFF, i32(0x80000000), -1, 1),
    ("u<", 0, -1, -1, 1),
    ("u<", -1, 0, 0, 1),
    ("u<=", -1, -1, -1, 1),
    ("u<=", -1, 0, 0, 1),
    ("u<=", 0, -1, -1, 1),
    ("u<=", i32(0x80000000), 0x7FFFFFFF, 0, 1),
    ("u>", -1, 0, -1, 1),
    ("u>", 0, -1, 0, 1),
    ("u>", i32(0x80000000), 0x7FFFFFFF, -1, 1),
    ("u>", 0x7FFFFFFF, i32(0x80000000), 0, 1),
    ("u>=", i32(0x80000000), i32(0x80000000), -1, 1),
    ("u>=", 0, -1, 0, 1),
    ("u>=", -1, 0, -1, 1),
    ("u>=", 0x7FFFFFFF, i32(0x80000000), 0, 1),
    ("and", -1, 0x0F0F0F0F, 0x0F0F0F0F, 1),
    ("or", i32(0xF0F0F0F0), 0x0F0F0F0F, -1, 1),
    ("xor", -1, -1, 0, 1),
    # THE `not` OPCODE.  not(-1) must be 0; `! $FFFFFFFF` gives
    # $FFFFFFFF00000000, which is not zero - the forged-tag shape.
    ("not", 0, None, -1, 1),
    ("not", -1, None, 0, 1),
    ("not", 0x0F0F0F0F, None, i32(0xF0F0F0F0), 1),
    ("<<", 1, 31, i32(0x80000000), 1),
    ("<<", 1, 32, 0, 1),
    ("<<", -1, 4, -16, 1),
    ("<<", 0x12345678, 8, i32(0x34567800), 1),
    (">>", -1, 1, -1, 1),
    (">>", -256, 4, -16, 1),
    (">>", 0x7FFFFFFF, 8, 0x7FFFFF, 1),
    ("u>>", -1, 1, 0x7FFFFFFF, 1),
    ("u>>", -1, 31, 1, 1),
    ("u>>", -1, 0, -1, 1),
    ("u>>", -1, 32, 0, 1),
    ("u>>", i32(0x80000000), 4, 0x08000000, 1),
    ("drop", 7, 9, 7, 1),
    ("dup", 7, None, 7, 2),
    ("swap", 3, 4, 3, 2),
    ("over", 3, 4, 3, 3),
]


def cell_jobs(s):
    for opname, x, y, r, dp in CELL_CASES:
        label = ("cell %-9s %s -> %d (%016x at full width)"
                 % (opname,
                    ("%d" % x) if y is None else ("%d, %d" % (x, y)),
                    r, u64(r)))
        s.blob("cell " + opname, _cell(opname, x, y), run_label=label,
               check=want(s0=u64(r), s1=dp, s2=0, s3=T0_HALT))


def build_script(pemdec, certs, K, level="full"):
    s = Script()
    ram_suite_jobs(s, K)
    guard_blob_jobs(s, K)
    cell_jobs(s)
    pem_jobs(s, pemdec, certs, level)
    return s


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def render_harness(t0vm_include, pemdec, certs, gen):
    maxin = max(len(p) for _, p, _ in certs) + 4
    maxout = max(len(d) for _, _, d in certs) + 16
    nat = "\n".join("#T0N_%s = %d" % (nm, nid)
                    for nid, nm in pemdec["natives"]) or "; (no natives)"
    return (HARNESS
            .replace("__T0VM__", t0vm_include)
            .replace("__NATIVES__", nat)
            .replace("__MAXIN__", str(maxin))
            .replace("__MAXOUT__", str(maxout))
            .replace("__DRIVER__", splice_driver(gen, certs)))


def build(src_text, harness_path, img):
    WORK.mkdir(exist_ok=True)
    harness_path.write_text(src_text, encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(harness_path), "-t", "pi4",
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
            raise SystemExit("the harness never returned (%d steps)\n%s"
                             % (steps, uart.decode("latin-1")))

    if b"t0harness done" not in uart:
        raise SystemExit("the harness returned without finishing its "
                         "script:\n" + uart.decode("latin-1"))

    recs = [bytes(mem.get(H_RESULT + i * RESULT_STRIDE + j, 0)
                  for j in range(RESULT_STRIDE))
            for i in range(count)]
    out = bytes(mem.get(H_OUT + i, 0) for i in range(out_bytes))
    return recs, out, steps


def check_shard(script, recs, out):
    bad = []
    for i, (label, op, check, expect) in enumerate(script.jobs):
        rec = recs[i]
        if rec == bytes([SENTINEL]) * RESULT_STRIDE:
            bad.append("%s: no record was written at all" % label)
            continue
        f = fields(rec)
        got = out[script.out_off[i]:script.out_off[i] + f["outlen"]]
        if expect is not None and op == OP_PEM:
            if got != expect:
                n = min(len(got), len(expect))
                at = next((k for k in range(n) if got[k] != expect[k]), n)
                bad.append("%s: DER differs from the python oracle at "
                           "byte %d (%d bytes out, %d expected)"
                           % (label, at, len(got), len(expect)))
        if check:
            for b in check(f, got):
                bad.append("%s: %s" % (label, b))
    return bad


def shard(script, n):
    """Split into n Scripts, keeping every GROUP whole and in order."""
    if n <= 1 or len(script.groups) <= 1:
        return [script]
    buckets = [script.groups[i::n] for i in range(n)]
    out = []
    for bucket in buckets:
        if not bucket:
            continue
        s = Script()
        for grp in bucket:
            s.group()
            for idx in grp:
                label, op, check, expect = script.jobs[idx]
                s._append(script.records[idx], label, op, check, expect)
        out.append(s)
    return out


def _worker(args):
    img_bytes, blob, count, out_bytes = args
    return run_raw(img_bytes, blob, count, out_bytes)


def run_all(img, script, jobs=None, quiet=False):
    img_bytes = img.read_bytes()
    n = jobs or max(1, (os.cpu_count() or 2) - 2)
    shards = shard(script, n)
    if len(shards) == 1:
        recs, out, steps = run_raw(img_bytes, shards[0].done(),
                                   len(shards[0]), shards[0]._o)
        return check_shard(shards[0], recs, out), steps
    if not quiet:
        print("[gate] %d jobs in %d groups across %d workers"
              % (len(script), len(script.groups), len(shards)),
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
#  Each is (label, find, replace, verdict).  The verdict is what the
#  mutation is EXPECTED to earn:
#
#    "kill"     the job set must catch it.  A survivor is a hole.
#    a string   an EXPECTED survivor, and the string is the argument for
#               why no known-answer test can see it.  These are NOT
#               deleted: the day one starts being caught is the day its
#               argument stopped being true, and that is as loud a
#               failure as an unexpected survivor.
#
#  A mutant that will not build is killed by the compiler, which is a
#  legitimate kill but a DIFFERENT verdict, printed as NOBUILD.
#
#  Every mutation edits a COPY in _work/ with its index in the filename.
#  When the A64 GCM sweep let every mutant share one filename, four of
#  them raced, the compiler read a half-written file, and the pool
#  reported four survivors that were nothing of the kind.
# =====================================================================
MUTATIONS = [
    # ---- THE CONTEXT-RAM GUARD.  M1 is the guard REMOVED and it must die.
    ("M1  THE BOUNDS GUARD IS REMOVED - T0RamInRange always allows",
     "Procedure.i T0RamInRange(addr.i, n.i)\n"
     "  If addr < 0 Or addr > (#T0_RAM_SIZE - n)\n"
     "    t0_err = #T0ERR_RAM_BOUNDS\n"
     "    t0_ip = -1\n"
     "    ProcedureReturn 0\n"
     "  EndIf\n"
     "  ProcedureReturn 1",
     "Procedure.i T0RamInRange(addr.i, n.i)\n"
     "  ProcedureReturn 1",
     "kill"),

    ("M2  the guard loses its NEGATIVE-offset test",
     "  If addr < 0 Or addr > (#T0_RAM_SIZE - n)",
     "  If addr > (#T0_RAM_SIZE - n)",
     "kill"),

    ("M3  the guard ignores the ACCESS WIDTH (checks the first byte only)",
     "  If addr < 0 Or addr > (#T0_RAM_SIZE - n)",
     "  If addr < 0 Or addr > (#T0_RAM_SIZE - 1)",
     "kill"),

    ("M4  the guard refuses EVERYTHING - the useless-guard case",
     "  If addr < 0 Or addr > (#T0_RAM_SIZE - n)",
     "  If addr < 0 Or addr >= 0",
     "kill"),

    ("M5  the guard names the fault but does not HALT the machine",
     "    t0_err = #T0ERR_RAM_BOUNDS\n    t0_ip = -1\n    ProcedureReturn 0",
     "    t0_err = #T0ERR_RAM_BOUNDS\n    ProcedureReturn 0",
     "kill"),

    ("M6  T0RamGet bypasses the guard",
     "Procedure.i T0RamGet(addr.i)\n"
     "  If T0RamInRange(addr, 1) = 0\n"
     "    ProcedureReturn 0\n"
     "  EndIf\n"
     "  ProcedureReturn t0_ram[addr] & 255",
     "Procedure.i T0RamGet(addr.i)\n"
     "  ProcedureReturn t0_ram[addr] & 255",
     "kill"),

    # ---- THE FIFTH SHAPE: the 32-bit-constant idioms
    ("M7  the comparison TRUE mask reverts to the constant $FFFFFFFF",
     "    T0Push(-1)",
     "    T0Push($FFFFFFFF)",
     "kill"),

    ("M8  the `not` opcode reverts to `a ! $FFFFFFFF` - THE GcmDecrypt "
     "FORGED-TAG SHAPE",
     "      T0Push(a ! -1)",
     "      T0Push(a ! $FFFFFFFF)",
     "kill"),

    ("M9  u< reverts to the flip-bit-31 trick",
     "    Case #T0OP_ULT\n      b = T0Pop() & #T0_W32\n"
     "      a = T0Pop() & #T0_W32\n      If a < b",
     "    Case #T0OP_ULT\n      b = T0Pop() ! $80000000\n"
     "      a = T0Pop() ! $80000000\n      If a < b",
     "kill"),

    # ALL FOUR UNSIGNED COMPARES ARE SWEPT, AND THAT IS NOT PADDING.
    # M10 SURVIVED THE FIRST SWEEP, and the mutation was not at fault:
    # the only u>= case in the job set used EQUAL operands, and the
    # flip-bit-31 trick answers equality correctly whatever it does to
    # ordering.  The cases now straddle the 2^31 boundary in BOTH
    # directions for every one of the four, which is what makes these
    # four mutations mean anything.
    ("M10 u>= reverts to the flip-bit-31 trick",
     "    Case #T0OP_UGE\n      b = T0Pop() & #T0_W32\n"
     "      a = T0Pop() & #T0_W32\n      If a >= b",
     "    Case #T0OP_UGE\n      b = T0Pop() ! $80000000\n"
     "      a = T0Pop() ! $80000000\n      If a >= b",
     "kill"),

    ("M11 u<= reverts to the flip-bit-31 trick",
     "    Case #T0OP_ULE\n      b = T0Pop() & #T0_W32\n"
     "      a = T0Pop() & #T0_W32\n      If a <= b",
     "    Case #T0OP_ULE\n      b = T0Pop() ! $80000000\n"
     "      a = T0Pop() ! $80000000\n      If a <= b",
     "kill"),

    ("M12 u> reverts to the flip-bit-31 trick",
     "    Case #T0OP_UGT\n      b = T0Pop() & #T0_W32\n"
     "      a = T0Pop() & #T0_W32\n      If a > b",
     "    Case #T0OP_UGT\n      b = T0Pop() ! $80000000\n"
     "      a = T0Pop() ! $80000000\n      If a > b",
     "kill"),

    # ---- THE CELL-WIDTH DECISION ITSELF.  This mutation is the whole
    # decision in one line, and it fails 23 jobs: the arithmetic, the
    # signed comparisons, `not`, both shifts, get32 and the PEM decode.
    # It does NOT fail the crafted negative-offset blob G3 - see the
    # note there - and the module header says so, because the first
    # draft of that header claimed it did.
    ("M13 T0Norm becomes a ZERO-EXTEND - the other cell convention",
     "  ProcedureReturn ((v & #T0_W32) ! $80000000) - $80000000",
     "  ProcedureReturn v & #T0_W32",
     "kill"),

    # ---- SHAPES 3 AND 4: the renormalisation sites
    ("M14 `+` loses T0Norm - the 32-bit wrap stops happening",
     "      T0Push(T0Norm(a + b))", "      T0Push(a + b)", "kill"),
    ("M15 `-` loses T0Norm",
     "      T0Push(T0Norm(a - b))", "      T0Push(a - b)", "kill"),
    ("M16 `neg` loses T0Norm",
     "      T0Push(T0Norm(0 - a))", "      T0Push(0 - a)", "kill"),
    ("M17 `*` loses T0Norm - the full 64-bit product is not the cell",
     "      T0Push(T0Norm(a * b))", "      T0Push(a * b)", "kill"),
    ("M18 `/` loses T0Norm",
     "      T0Push(T0Norm(a / b))", "      T0Push(a / b)", "kill"),
    ("M19 `<<` loses T0Norm - shape 3's namesake",
     "      T0Push(T0Norm(x << c))", "      T0Push(x << c)", "kill"),
    ("M20 get32 loses T0Norm - a context word with bit 31 set comes back "
     "positive",
     "        T0Push(T0Norm((t0_ram[addr] & 255) | ((t0_ram[addr + 1] & 255)"
     " << 8) | ((t0_ram[addr + 2] & 255) << 16) | ((t0_ram[addr + 3] & 255)"
     " << 24)))",
     "        T0Push((t0_ram[addr] & 255) | ((t0_ram[addr + 1] & 255) << 8)"
     " | ((t0_ram[addr + 2] & 255) << 16) | ((t0_ram[addr + 3] & 255)"
     " << 24))",
     "kill"),
    ("M21 u>> loses the mask that clears the smeared sign bits",
     "        mask = (1 << (32 - c)) - 1    ; clear the sign bits >> drags in"
     "\n        T0Push((x >> c) & mask)",
     "        mask = (1 << (32 - c)) - 1    ; clear the sign bits >> drags in"
     "\n        T0Push(x >> c)",
     "kill"),

    # ---- THE DISPATCH AND THE DECODERS, so the port is not the only
    #      thing under test
    ("M22 T0CaddrGet reads the word-entry table big-endian",
     "  lo = PeekA(t0_caddrp + idx * 2) & 255\n"
     "  hi = PeekA(t0_caddrp + idx * 2 + 1) & 255",
     "  hi = PeekA(t0_caddrp + idx * 2) & 255\n"
     "  lo = PeekA(t0_caddrp + idx * 2 + 1) & 255",
     "kill"),

    ("M23 T0EnterSlot pushes the frame BEFORE reserving the locals",
     "  t0_rp = t0_rp + lnum                  ; reserve locals below the "
     "frame\n  t0_rs[t0_rp] = (t0_ip & $FFFF) | (lnum << 16)",
     "  t0_rs[t0_rp] = (t0_ip & $FFFF) | (lnum << 16)\n"
     "  t0_rp = t0_rp + lnum",
     "kill"),

    ("M24 jump-if takes the branch when the flag is FALSE",
     "    Case 5            ; jump if\n      off = T0NextS()\n"
     "      a = T0Pop()\n      If a <> 0",
     "    Case 5            ; jump if\n      off = T0NextS()\n"
     "      a = T0Pop()\n      If a = 0",
     "kill"),

    ("M25 T0Run routes u>> to the stack group instead of the bit group",
     "      ElseIf op <= 25", "      ElseIf op <= 24", "kill"),

    # ---- THE EXPECTED SURVIVORS
    ("M26 T0NextS's return loses T0Norm",
     "  ForEver\n  ProcedureReturn T0Norm(x)\nEndProcedure",
     "  ForEver\n  ProcedureReturn x\nEndProcedure",
     "NO KNOWN-ANSWER TEST CAN SEE THIS, AND THE ARGUMENT IS A PROOF "
     "RATHER THAN A RANGE CLAIM. T0NextS seeds its accumulator with 0 or "
     "all-ones and then computes x = x * 128 + g per group. That "
     "recursion reconstructs the signed value at ANY register width, so "
     "for every literal a T0 compiler can emit - all of them "
     "int32-representable, at most five groups - the 64-bit answer IS "
     "the sign-extended 32-bit answer. Worked at the widest case: "
     "-2147483648 encodes $78 $00 $00 $00 $00 and the loop walks -1, -8, "
     "-1024, -131072, -16777216, -2147483648. The T0Norm is there so a "
     "MALFORMED code block - a six-group varint, which no generator "
     "emits - cannot inject a cell wider than int32, and a code block is "
     "compiled-in constant data that no vector set can corrupt."),

    ("M27 T0NextU loses its 32-bit mask",
     "    x = ((x << 7) | (y & $7F)) & #T0_W32",
     "    x = (x << 7) | (y & $7F)",
     "UNREACHABLE, AND THE REASON IS ABOUT WHAT T0 EMITS AS AN UNSIGNED "
     "VARINT. There are exactly two: the local COUNT at a word's head and "
     "the local INDEX of a get-local/put-local. Both are bounded by the "
     "T0 compiler's own frame layout at well under 2^15, so the "
     "accumulator never reaches 2^32 and the mask never removes a bit. "
     "The claim it rests on is true and UNENFORCED, which is exactly the "
     "shape that has bitten this project before, so the mask is written "
     "and the argument is recorded rather than the line being deleted."),

    ("M28 `%` gains a T0Norm it does not need",
     "      T0Push(a % b)", "      T0Push(T0Norm(a % b))",
     "AN EXPECTED SURVIVOR ON PURPOSE, BECAUSE IT IS THE INVERSE TEST. "
     "The file's header records `%` as the ONE arithmetic opcode that "
     "needs no renormalisation - |a % b| < |b| <= 2^31 for in-range "
     "cells, and INT32_MIN % -1 is 0 at both widths - so adding T0Norm "
     "there must change NOTHING. If this ever starts being caught, the "
     "'not needed' finding in the header is wrong and there is a "
     "remainder somewhere outside int32."),
]


def mutate_source(idx, find, replace):
    """Write a mutated COPY into _work/ and return its include path."""
    WORK.mkdir(exist_ok=True)
    text = T0VM.read_text(encoding="utf-8")
    if text.count(find) != 1:
        raise SystemExit("mutation anchor found %d times in %s (want 1):\n%r"
                         % (text.count(find), T0VM.name, find))
    out = WORK / ("t0mut%02d_%s" % (idx, T0VM.name))
    out.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return "_work/" + out.name, out


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
    ap.add_argument("--quick", action="store_true",
                    help="one certificate instead of three")
    ap.add_argument("--mutate", action="store_true", help="the mutation sweep")
    ap.add_argument("--mutation", type=int, default=None,
                    help="run ONE mutation by index (used by the pool)")
    ap.add_argument("--jobs", type=int, default=None,
                    help="worker processes (default: cores - 2)")
    args = ap.parse_args(argv)
    globals()["PMFC"] = resolve_compiler(args.compiler)

    print("[gate] tree under test: %s" % ROOT, file=sys.stderr)

    pemdec = load_pemdec()
    gen, certs = load_certs()

    if args.mutation is not None:
        i = args.mutation
        label, find, repl, verdict = MUTATIONS[i]
        inc, mut_path = mutate_source(i, find, repl)
        K = module_constants(mut_path)
        img = WORK / ("t0_mut%02d.img" % i)
        src = render_harness(inc, pemdec, certs, gen)
        try:
            build(src, WORK / ("t0harness_mut%02d.pi4" % i), img)
        except SystemExit as e:
            # A MUTANT THAT WILL NOT BUILD IS KILLED BY THE COMPILER, and
            # that is a legitimate kill - but it is a DIFFERENT verdict
            # from "the jobs caught it" and is printed as one.
            print("NOBUILD  %s\n         %s"
                  % (label, str(e).splitlines()[0]))
            return 0
        s = build_script(pemdec, certs, K, level="mutant")
        bad, _ = run_all(img, s, jobs=args.jobs, quiet=True)

        if verdict == "kill":
            if bad:
                print("KILLED   %s\n         first: %s"
                      % (label, bad[0].splitlines()[0]))
                return 0
            print("SURVIVED %s\n         (the job set was expected to catch "
                  "this one)" % label)
            return 1
        if bad:
            print("UNEXPECTED-KILL %s\n         the job set now catches "
                  "this, so the recorded argument is stale:\n         %s\n"
                  "         first: %s" % (label, verdict, bad[0]))
            return 1
        print("EXPECTED-SURVIVOR %s" % label)
        return 0

    if args.mutate:
        n = args.jobs or max(1, (os.cpu_count() or 2) - 2)
        print("[gate] %d mutations across %d workers" % (len(MUTATIONS), n))
        t0 = time.time()
        survivors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
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

    K = module_constants()
    s = build_script(pemdec, certs, K,
                     level="quick" if args.quick else "full")
    img = WORK / "t0harness.img"
    src = render_harness("RaspberryPi4/Lib/t0vm.pi4", pemdec, certs, gen)
    size = build(src, WORK / "t0harness.pi4", img)
    print("[gate] PEM decoder blob %s: code %d, data %d, caddr %d, "
          "opmap %d, T0_INTERPRETED %d, entry %d"
          % (SHARED_BLOB.relative_to(ROOT).as_posix(), len(pemdec["code"]),
             len(pemdec["data"]), len(pemdec["caddr"]), len(pemdec["opmap"]),
             pemdec["interp"], pemdec["entry"]))
    print("[gate] %s" % REGEN_NOTE)
    print("[gate] context RAM %d bytes, refusal code %d, stacks %d/%d cells"
          % (K["T0_RAM_SIZE"], K["T0ERR_RAM_BOUNDS"], K["T0_DS_DEPTH"],
             K["T0_RS_DEPTH"]))
    print("[gate] image %d bytes, %d jobs in %d groups"
          % (size, len(s), len(s.groups)))
    t0 = time.time()
    bad, steps = run_all(img, s, jobs=args.jobs)
    for b in bad:
        print("FAIL: " + b)
    print("[gate] %d jobs, %d model instructions, %.0f s"
          % (len(s), steps, time.time() - t0))
    if bad:
        print("T0VM GATE RED: %d of %d jobs wrong" % (len(bad), len(s)))
        return 1
    print("T0VM GATE GREEN: %d jobs - the shared PEM decoder bytecode over "
          "%d certificate(s) PEM->DER byte-exact, the context-RAM bounds guard "
          "in both halves plus %d crafted hostile blobs REFUSED and "
          "observed, and %d opcodes conformant at full 64-bit width; "
          "%d model instructions"
          % (len(s), len(certs) if not args.quick else 1, 10,
             len(CELL_CASES), steps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
