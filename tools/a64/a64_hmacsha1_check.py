#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/hmacsha1.pi4.

WHY THIS FILE IS WRITTEN THE WAY IT IS

  THE FIRST ORACLE IS RFC 2202, PARSED OFF THE DISK.  All seven
  HMAC-SHA-1 test cases in its section 3 - keys, messages and digests
  - are read out of RaspberryPi4/Reference/rfc2202.txt at run time.
  Nothing is transcribed into this file, because a transcription is a
  chance to be wrong that a parse does not have, and because a
  hardcoded vector set silently stops being the RFC's the moment
  somebody "fixes" a typo in it.

  THE SECOND ORACLE IS NIST CAVP, AND IT IS HERE BECAUSE THE MUTATION
  SWEEP DEMANDED IT.  With RFC 2202 alone, two deliberate defects
  survived: moving the long-key test from `> 64` to `>= 64`, and
  clamping an over-length truncation request to the wrong ceiling.
  Neither is subtle - both are wrong in a way that would disagree with
  every other implementation on Earth - but RFC 2202 contains no
  64-byte key and no truncation request longer than the MAC, so the
  gate could not see either.  A gate that cannot see a bug it was
  built to catch is the thing this project keeps finding, so the
  answer was a better oracle rather than a quieter mutation.
  RaspberryPi4/Reference/cavp_HMAC.rsp is NIST's own HMAC validation
  set; its [L=20] section is 300 HMAC-SHA-1 vectors with key lengths
  of 10, 32, 64, 70 and 80 bytes and tag lengths of 10, 12, 16 and 20.
  Klen = 64 is the exact boundary case, and Tlen = 16 is the length
  WPA2's EAPOL-Key MIC uses.

  THE PARSE IS CHECKED AGAINST THE RFC'S OWN LENGTHS.  Every case
  states key_len and data_len alongside the values.  This gate
  reassembles each value and then requires the length to match what
  the RFC says it should be.  That is what makes the parser
  trustworthy rather than merely plausible - case 7's data is split
  across two lines and case 3's key is written as "0xaa repeated 20
  times", and both of those are ways for a parser to be quietly wrong.

  THE CACHED KEY STATE IS THE THING MOST WORTH TESTING.  hmacsha1.pi4
  snapshots the ipad and opad SHA-1 states so that PBKDF2's 8192 MACs
  do not re-hash the pads.  A naive implementation cannot get that
  wrong because it does not do it; this one can, and the failure is
  invisible to a test that computes each MAC from a fresh key.  So
  every case is also run as TWO MACs from ONE HmacSha1Key, and the
  SECOND one is what is compared.

  TRUNCATION IS A TESTED PATH.  RFC 2202 case 5 publishes a 96-bit
  answer as well as the full one, and WPA2's EAPOL-Key MIC is this
  same MAC truncated to 128 bits, so the truncating branch is on the
  critical path for the whole Wi-Fi task.  Both truncations are
  checked.

  --mutate IS THE POINT.  Nine deliberate defects, each of which a
  person could plausibly write.  EIGHT MUST GO RED.  ONE MUST GO
  GREEN, and it is kept rather than deleted because the sweep is what
  proved it harmless: `secHmacS1Blk` is a byte array and the XOR
  operand is below 256, so a signed read of a key byte cannot change
  anything that gets stored.  The sweep fails if any mutation deviates
  from its recorded expectation in either direction.

WHAT THIS GATE DOES NOT SAY

  * That any of this runs on silicon.  tools/a64/a64_interp.py models
    the instruction set, not the BCM2711.
  * Anything about SHA-1's collision resistance.  See sha1.pi4's
    header; HMAC does not depend on it, which is the whole reason
    WPA2 is still allowed to use it.

Run: python tools/a64/a64_hmacsha1_check.py
     python tools/a64/a64_hmacsha1_check.py --mutate
"""

from __future__ import annotations
import os

import argparse
import pathlib
import re
import struct
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
# THE TREE UNDER TEST IS THE ONE THIS SCRIPT LIVES IN. A root pinned into
# the file made this gate build a DIFFERENT working copy, with that copy's
# compiler, and print the answer as this tree's. Override deliberately with
# PMF_REPO; the tree actually read is printed below so a wrong one is visible.
ROOT = pathlib.Path(__file__).resolve().parents[2]
print("[gate] tree under test: %s" % ROOT, file=sys.stderr)
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402
from a64_target import (TARGETS, apply_target,  # noqa: E402
                        patch_harness)

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LIB = ROOT / "RaspberryPi4" / "Lib" / "hmacsha1.pi4"
REF = ROOT / "RaspberryPi4" / "Reference"
RFC2202 = REF / "rfc2202.txt"
CAVP_HMAC = REF / "cavp_HMAC.rsp"
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

H_SCRIPT = 0x06000000
H_RESULT = 0x0A000000

STEP_LIMIT = 2_000_000_000

OP_END = 0
OP_ONESHOT = 1
OP_BYTEWISE = 2
OP_REUSE = 3
OP_TRUNC = 4


# =====================================================================
#  THE HARNESS
# =====================================================================
#  SCRIPT RECORD, 16 bytes then the key then the message, each padded
#  to 4:
#      +0 op   +4 arg   +8 keylen   +12 msglen   +16 key ... msg ...
#  op 0 ends the script.
#
#  RESULT RECORD: 20 bytes, one per script record.  A truncated MAC is
#  written into a zeroed 20-byte field, so the gate can see both that
#  the leading bytes are right AND that nothing was written past the
#  requested length.
# =====================================================================
HARNESS = r'''
; ======================================================================
;  hmacsha1harness.pi4 - GENERATED BY tools/a64/a64_hmacsha1_check.py.
;  NOT A SOURCE FILE. DO NOT EDIT.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "RaspberryPi4/Lib/sha1.pi4"
XIncludeFile "__LIB__"

#H_SCRIPT = $06000000
#H_RESULT = $0A000000

Global Dim hFirst.a[20]

Procedure.i Main()
  Define p.i
  Define q.i
  Define op.i
  Define arg.i
  Define klen.i
  Define mlen.i
  Define key.i
  Define msg.i
  Define off.i
  Define i.i
  Define n.i

  p = #H_SCRIPT
  q = #H_RESULT

  Repeat
    op   = PeekN(p)
    arg  = PeekN(p + 4)
    klen = PeekN(p + 8)
    mlen = PeekN(p + 12)
    If op = 0
      Break
    EndIf
    key = p + 16
    msg = key + (((klen + 3) / 4) * 4)

    ; The result field starts zeroed, so a short write leaves zeroes
    ; behind it and the gate can tell a truncation from an overrun.
    i = 0
    While i < 20
      PokeB(q + i, 0)
      i = i + 1
    Wend

    If op = 1
      HmacSha1Of(key, klen, msg, mlen, q)

    ElseIf op = 2
      ; Streamed one byte at a time.
      HmacSha1Key(key, klen)
      off = 0
      While off < mlen
        HmacSha1Update(msg + off, 1)
        off = off + 1
      Wend
      n = HmacSha1End(q, 20)

    ElseIf op = 3
      ; TWO MACs from ONE key. The first is thrown away; the SECOND is
      ; reported. If the cached ipad/opad states did not survive the
      ; first End(), the second answer is wrong.
      HmacSha1Key(key, klen)
      HmacSha1Update(msg, mlen)
      n = HmacSha1End(@hFirst[0], 20)
      HmacSha1Begin()
      HmacSha1Update(msg, mlen)
      n = HmacSha1End(q, 20)

    ElseIf op = 4
      ; Truncated to arg bytes.
      HmacSha1Key(key, klen)
      HmacSha1Update(msg, mlen)
      n = HmacSha1End(q, arg)
      ; The returned length is stamped into the last byte of the
      ; field so the gate can check the RETURN VALUE and not only the
      ; bytes. For a request shorter than 19 this lands in the zeroed
      ; tail and costs nothing; for a request of 20 or more - which
      ; must clamp to 20 - it overwrites the last MAC byte, and the
      ; gate's expected image is built to match. Every other record
      ; covers that byte.
      PokeB(q + 19, n & 255)
    EndIf

    p = p + 16 + (((klen + 3) / 4) * 4) + (((mlen + 3) / 4) * 4)
    q = q + 20
  ForEver

  UartWriteStr("hmacsha1harness done")
  ProcedureReturn 0
EndProcedure
'''


class Script:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: list[str] = []
        self.expect: list[bytes] = []

    def add(self, op: int, label: str, expect: bytes, key: bytes,
            msg: bytes, arg: int = 0) -> None:
        self.labels.append(label)
        self.expect.append(expect)
        self.buf += struct.pack("<IIII", op, arg, len(key), len(msg))
        self.buf += key + b"\x00" * ((-len(key)) % 4)
        self.buf += msg + b"\x00" * ((-len(msg)) % 4)

    def done(self) -> bytes:
        return bytes(self.buf) + struct.pack("<IIII", OP_END, 0, 0, 0)


# =====================================================================
#  RFC 2202, PARSED
# =====================================================================
REPEATED = re.compile(r"0x([0-9a-fA-F]{2})\s+repeated\s+(\d+)\s+times")


def _value(body: str, field: str, case: int) -> bytes:
    """Turn one RFC 2202 right-hand side into bytes.

    Three forms appear in the document and all three are handled here
    rather than special-cased at the call site:

        0x0b0b0b...                 a hex string
        "Hi There"                  a quoted ASCII string, which MAY
                                    be broken across two lines
        0xaa repeated 80 times      a run
    """
    body = body.strip()

    m = REPEATED.search(body)
    if m:
        return bytes([int(m.group(1), 16)]) * int(m.group(2))

    if body.startswith("0x"):
        h = re.sub(r"[^0-9a-fA-F]", "", body[2:])
        if len(h) % 2:
            raise SystemExit(
                f"rfc2202.txt case {case}: {field} has an odd hex digit count")
        return bytes.fromhex(h)

    if body.startswith('"'):
        if not body.endswith('"'):
            raise SystemExit(
                f"rfc2202.txt case {case}: {field} is a quoted string that "
                "never closes - the continuation-line join in this parser "
                "is wrong for the current text")
        return body[1:-1].encode("latin-1")

    raise SystemExit(f"rfc2202.txt case {case}: cannot read {field}: {body!r}")


def parse_rfc2202() -> list[dict]:
    """The seven HMAC-SHA-1 cases out of RFC 2202 section 3.

    Section 2 carries the HMAC-MD5 cases in the identical layout, so
    the section boundaries are found first and only section 3 is read.
    Reading the whole file would silently gate SHA-1 on MD5's answers.

    The RFC's page furniture repeats cases 5, 6 and 7 across a page
    break with different line wrapping.  Cases are therefore keyed by
    test_case number and the FIRST occurrence wins; the duplicate is
    then required to agree, so a page-break artefact cannot quietly
    substitute one case for another.
    """
    if not RFC2202.exists():
        raise SystemExit(
            f"the oracle is missing: {RFC2202}\n"
            "Fetch https://www.rfc-editor.org/rfc/rfc2202.txt into "
            "RaspberryPi4/Reference/ - do not invent replacements.")
    text = RFC2202.read_text(errors="replace")

    start = text.find("3. Test Cases for HMAC-SHA-1")
    end = text.find("4. Security Considerations", start + 1)
    if start < 0 or end < 0:
        raise SystemExit(
            "rfc2202.txt: cannot find section 3's boundaries. The document "
            "has changed shape; find the new headings rather than widening "
            "the search, or this gate will read the MD5 vectors.")
    body = text[start:end]

    # Strip page furniture: the running header, the running footer and
    # the form feeds between them.
    lines = []
    for ln in body.splitlines():
        if ln.startswith("\f"):
            continue
        if "Cheng & Glenn" in ln or ln.startswith("RFC 2202 "):
            continue
        lines.append(ln)

    # Join a continued quoted string onto the line that opened it.
    joined = []
    for ln in lines:
        if joined and joined[-1].count('"') == 1 and '"' in joined[-1]:
            joined[-1] = joined[-1].rstrip() + " " + ln.strip()
        else:
            joined.append(ln)

    cases: dict[int, dict] = {}

    def flush(cur):
        """Validate one finished case and file it under its number.

        A case is only finished when the NEXT one begins, or when the
        section ends.  Finishing it as soon as `digest` arrives would
        drop case 5's `digest-96`, which is the published truncated
        answer and the only external evidence that RFC 2104's
        truncation takes the LEADING bytes.
        """
        if cur is None:
            return
        n = cur["case"]
        for want in ("key", "data", "digest", "key_len", "data_len"):
            if want not in cur:
                raise SystemExit(
                    "rfc2202.txt case %d has no %s" % (n, want))
        if len(cur["key"]) != cur["key_len"]:
            raise SystemExit(
                "rfc2202.txt case %d: parsed a %d-byte key but the document "
                "says key_len = %d" % (n, len(cur["key"]), cur["key_len"]))
        if len(cur["data"]) != cur["data_len"]:
            raise SystemExit(
                "rfc2202.txt case %d: parsed %d bytes of data but the "
                "document says data_len = %d. The most likely cause is the "
                "continuation-line join in this parser."
                % (n, len(cur["data"]), cur["data_len"]))
        if len(cur["digest"]) != 20:
            raise SystemExit(
                "rfc2202.txt case %d: the digest is not 20 bytes - is this "
                "the MD5 section?" % n)
        if n in cases:
            if cases[n] != cur:
                raise SystemExit(
                    "rfc2202.txt case %d appears twice with different "
                    "content. The page-break de-duplication in this parser "
                    "is wrong." % n)
        else:
            cases[n] = cur

    cur = None
    for ln in joined:
        m = re.match(r"\s*test_case\s*=\s*(\d+)", ln)
        if m:
            flush(cur)
            cur = {"case": int(m.group(1))}
            continue
        if cur is None:
            continue
        m = re.match(r"\s*(key|data|digest-96|digest|key_len|data_len)\s*=\s*(.*)", ln)
        if not m:
            continue
        field, rhs = m.group(1), m.group(2)
        if field in cur:
            # A field arriving twice inside one case means the page
            # break has spliced the TAIL of an earlier case onto this
            # one.  RFC 2202 does exactly that at the foot of page 4:
            # case 7 is followed, with no test_case line of its own, by
            # the last three lines of case 5 repeated.  Close the case
            # that was complete and ignore the orphan until the next
            # test_case heading.
            flush(cur)
            cur = None
            continue
        if field in ("key_len", "data_len"):
            cur[field] = int(rhs.strip())
        else:
            cur[field] = _value(rhs, field, cur["case"])
    flush(cur)

    if sorted(cases) != [1, 2, 3, 4, 5, 6, 7]:
        raise SystemExit(
            "rfc2202.txt: expected HMAC-SHA-1 cases 1..7, parsed %s"
            % sorted(cases))
    return [cases[i] for i in range(1, 8)]


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def build(lib_include: str, harness: pathlib.Path, img: pathlib.Path) -> None:
    WORK.mkdir(exist_ok=True)
    harness.write_text(patch_harness(HARNESS.replace("__LIB__",
                                                 lib_include),
                                 globals()),
                       encoding="utf-8")
    cmd = [str(PMFC), "--compile", str(harness), "-t", TFLAG,
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(img)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)


def run(img: pathlib.Path, script: bytes, count: int):
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR
    # Names for the alignment rule's message, from the `.dbg` pmfc
    # writes beside the image - NOT the `.sym`, which mixes absolute
    # BSS addresses with load-relative code ones
    # (A64Assembler.pbi:1994-1997).
    attach_symbols(cpu, img, LOAD)

    uart = bytearray()

    def load(addr, size):
        # THE ALIGNMENT RULE. This closure replaces A64.load, so the
        # guard has to be CALLED here - see a64_interp.py's ALIGNMENT
        # RULE note. With the MMU off every data access is
        # Device-nGnRnE and an unaligned wide one is a silent runaway
        # on the part; without this line the gate models a machine
        # more permissive than the board it certifies.
        cpu.align_guard(addr, size, False)
        if UART_LO <= addr <= UART_HI:
            return 0
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
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
    if b"hmacsha1harness done" not in uart:
        raise SystemExit("the harness returned without finishing its script:\n"
                         + uart.decode("latin-1"))

    out = []
    for i in range(count):
        a = H_RESULT + i * 20
        out.append(bytes(mem.get(a + j, 0) for j in range(20)))
    return out, steps


def parse_cavp_hmac() -> list[dict]:
    """The [L=20] - that is, HMAC-SHA-1 - section of NIST's HMAC.rsp.

    THE SECTION BOUNDARY IS LOAD-BEARING.  The same file carries
    [L=28], [L=32], [L=48] and [L=64] - SHA-224 through SHA-512 - in
    the identical layout.  Reading past the boundary would gate SHA-1
    on SHA-224's answers, and every one of them would fail, which is
    the good case; reading a PREFIX of the wrong section is the bad
    one.  So the section is sliced by its own headings and the count
    is reported, and a change in the file's shape raises rather than
    silently testing fewer vectors.
    """
    if not CAVP_HMAC.exists():
        raise SystemExit(
            f"the oracle is missing: {CAVP_HMAC}\n"
            "It is NIST's CAVP HMAC validation set, hmactestvectors.zip from\n"
            "csrc.nist.gov. Fetch it into RaspberryPi4/Reference/ - do not\n"
            "invent replacements and do not weaken the mutations that need it.")
    text = CAVP_HMAC.read_text(errors="replace")
    start = text.find("[L=20]")
    if start < 0:
        raise SystemExit("cavp_HMAC.rsp: no [L=20] section - wrong file?")
    nxt = re.search(r"\[L=(?!20\])\d+\]", text[start + 6:])
    body = text[start:start + 6 + nxt.start()] if nxt else text[start:]

    out = []
    cur: dict = {}
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("Count ="):
            cur = {"count": int(line.split("=", 1)[1])}
        elif line.startswith("Klen ="):
            cur["klen"] = int(line.split("=", 1)[1])
        elif line.startswith("Tlen ="):
            cur["tlen"] = int(line.split("=", 1)[1])
        elif line.startswith("Key ="):
            cur["key"] = bytes.fromhex(line.split("=", 1)[1].strip())
        elif line.startswith("Msg ="):
            cur["msg"] = bytes.fromhex(line.split("=", 1)[1].strip())
        elif line.startswith("Mac ="):
            cur["mac"] = bytes.fromhex(line.split("=", 1)[1].strip())
            for want in ("klen", "tlen", "key", "msg"):
                if want not in cur:
                    raise SystemExit("cavp_HMAC.rsp: a Mac with no %s" % want)
            if len(cur["key"]) != cur["klen"]:
                raise SystemExit(
                    "cavp_HMAC.rsp count %d: Klen says %d, the key is %d bytes"
                    % (cur["count"], cur["klen"], len(cur["key"])))
            if len(cur["mac"]) != cur["tlen"]:
                raise SystemExit(
                    "cavp_HMAC.rsp count %d: Tlen says %d, the Mac is %d bytes"
                    % (cur["count"], cur["tlen"], len(cur["mac"])))
            if cur["tlen"] > 20:
                raise SystemExit(
                    "cavp_HMAC.rsp count %d: Tlen %d is longer than SHA-1's "
                    "digest - this is not the [L=20] section"
                    % (cur["count"], cur["tlen"]))
            out.append(cur)
            cur = {}
    if not out:
        raise SystemExit("cavp_HMAC.rsp: [L=20] parsed to nothing")
    return out


def build_script(subset: bool = False) -> Script:
    """The full vector set, or - for the mutation sweep - a subset.

    THE SUBSET IS A TIME DECISION.  The full set is 343 vectors and 70
    million model instructions, a bit over two minutes; nine mutations
    of that is twenty minutes and a sweep nobody runs is a sweep that
    does not exist.  Every fifth CAVP vector is kept, which preserves
    all five key lengths and all four tag lengths - including Klen=64
    and Tlen=16, the two the sweep specifically needs - and the whole
    of RFC 2202 is kept regardless, because seven cases cost nothing.
    """
    s = Script()

    # ---- NIST CAVP, the wide set --------------------------------------
    cavp = parse_cavp_hmac()
    if subset:
        cavp = cavp[::5]
    for c in cavp:
        tlen = c["tlen"]
        # The harness zeroes the 20-byte result field and stamps the
        # returned length into its last byte, so the expected image is
        # the tag, then zeroes, then the length.  Tlen = 20 fills the
        # field, so those cases are compared as a plain full MAC.
        if tlen == 20:
            s.add(OP_ONESHOT,
                  "CAVP HMAC-SHA1 count=%d Klen=%d Tlen=20"
                  % (c["count"], c["klen"]), c["mac"], c["key"], c["msg"])
        else:
            exp = c["mac"] + b"\x00" * (19 - tlen) + bytes([tlen])
            s.add(OP_TRUNC,
                  "CAVP HMAC-SHA1 count=%d Klen=%d Tlen=%d"
                  % (c["count"], c["klen"], tlen), exp, c["key"], c["msg"],
                  arg=tlen)

    # ---- RFC 2202, the deep set ---------------------------------------
    for c in parse_rfc2202():
        n = c["case"]
        key = c["key"]
        data = c["data"]
        md = c["digest"]
        s.add(OP_ONESHOT, "RFC 2202 case %d one shot" % n, md, key, data)
        s.add(OP_BYTEWISE, "RFC 2202 case %d streamed a byte at a time" % n,
              md, key, data)
        s.add(OP_REUSE, "RFC 2202 case %d second MAC from the cached key" % n,
              md, key, data)
        if "digest-96" in c:
            t = c["digest-96"]
            if t != md[:len(t)]:
                raise SystemExit(
                    "rfc2202.txt case %d: digest-96 is not a prefix of "
                    "digest - the parse is wrong" % n)
            # The harness zeroes the field and writes the returned
            # length into byte 19, so the expected image is the
            # truncated MAC, zeroes, then the length.
            exp = t + b"\x00" * (19 - len(t)) + bytes([len(t)])
            s.add(OP_TRUNC, "RFC 2202 case %d truncated to %d bytes"
                  % (n, len(t)), exp, key, data, arg=len(t))
        # WPA2's EAPOL-Key MIC is this MAC cut to 128 bits.  There is
        # no published 128-bit answer, but "the first 16 bytes of the
        # published 160-bit answer" is not a guess - it is what RFC
        # 2104 section 5 defines truncation to be, and case 5's
        # digest-96 above confirms the RFC means the LEADING bytes.
        exp16 = md[:16] + b"\x00" * 3 + bytes([16])
        s.add(OP_TRUNC, "RFC 2202 case %d truncated to 16 bytes (the "
              "EAPOL-Key MIC length)" % n, exp16, key, data, arg=16)

        # TWO REQUESTS THAT MUST CLAMP UP TO THE FULL MAC: 32 bytes,
        # which is longer than SHA-1 has, and 0, which the API defines
        # as "all of it".  Both must write 20 bytes and return 20.  The
        # harness stamps the returned length over byte 19, so the
        # expected image loses the last MAC byte for these two records
        # and every other record covers it.
        #
        # THESE EXIST BECAUSE A MUTATION SURVIVED WITHOUT THEM.  With
        # no request longer than 20 bytes, the clamp `If n > 20 : n =
        # 20` is unreachable and a mutation that sets it to 16 is
        # invisible.  An unreachable line is not a safe line - it is a
        # line the next caller reaches.
        exp_full = md[:19] + bytes([20])
        s.add(OP_TRUNC, "RFC 2202 case %d asked for 32 bytes, must clamp "
              "to 20" % n, exp_full, key, data, arg=32)
        s.add(OP_TRUNC, "RFC 2202 case %d asked for 0 bytes, must mean the "
              "full 20" % n, exp_full, key, data, arg=0)
    return s


def check(img: pathlib.Path, s: Script, quiet: bool = False) -> list[str]:
    got, steps = run(img, s.done(), len(s.labels))
    bad = []
    for i, label in enumerate(s.labels):
        if got[i] != s.expect[i]:
            bad.append("  %s\n      expected %s\n      got      %s"
                       % (label, s.expect[i].hex(), got[i].hex()))
    if not quiet:
        print("  %d vectors, %s, %d steps"
              % (len(s.labels), "ALL PASS" if not bad else
                 "%d FAILED" % len(bad), steps))
    return bad


# =====================================================================
#  MUTATIONS
# =====================================================================
#  Each entry is (name, expect_red, old, new, count, why).
#
#  expect_red IS NOT A CONVENIENCE.  One of the defects below is
#  PROVABLY not a defect at all, and the sweep found that rather than
#  being told it.  Deleting the entry would hide the finding; calling it
#  a failure would leave a permanent false alarm.  So each mutation
#  records what it is expected to do and the sweep fails if any
#  mutation deviates IN EITHER DIRECTION - a line that becomes
#  observable later is news this gate will deliver.
MUTATIONS = [
    ("ipad and opad swapped", True,
     "secHmacS1Blk[i] = (PeekA(kb + i) & 255) ! $36",
     "secHmacS1Blk[i] = (PeekA(kb + i) & 255) ! $5C", 1,
     "two opad blocks; RFC 2104 needs one of each"),

    ("opad pad byte wrong", True,
     "    secHmacS1Blk[i] = $5C\n", "    secHmacS1Blk[i] = $5D\n", 1,
     "the zero-extension of a short key must be the pad byte itself"),

    ("long-key threshold off by one", True,
     "If keylen > #HMACSHA1_BLOCK", "If keylen >= #HMACSHA1_BLOCK", 1,
     "a 64-byte key must be used as-is, not hashed"),

    ("long keys not hashed at all", True,
     "If keylen > #HMACSHA1_BLOCK", "If keylen > 1000000", 1,
     "RFC 2202 cases 6 and 7 use an 80-byte key"),

    # THIS ONE MUST GO GREEN, AND THE SWEEP TAUGHT IT TWICE.
    #
    # First spelling: PeekB with the "& 255" left in place.  Green, and
    # obviously so - the mask cuts the sign extension off before the
    # XOR sees it.
    #
    # Second spelling, below: PeekB with the mask ALSO removed.  Still
    # green, and this time for a better reason. `secHmacS1Blk` is a
    # byte array, so the store itself truncates to eight bits; and XOR
    # with a value below 256 cannot change any bit above bit 7.  So
    # (PeekA(x) & 255) ! $5C and PeekB(x) ! $5C agree in the low octet
    # for every possible input, and the low octet is all that is kept.
    # THE MUTATION IS NOT A DEFECT - it is a different spelling of the
    # same function.
    #
    # WHICH MEANS THERE IS NO OBSERVABLE SIGNED-READ DEFECT IN THIS
    # FILE, and that is worth stating rather than hunting for one.  The
    # only other byte read hmacsha1.pi4 performs is the long-key
    # Sha1Of, and the accessors inside sha1.pi4 are mutation-tested by
    # a64_sha1_check.py where they live.  Keeping the mutation here,
    # marked green with its proof, records the search; deleting it
    # would leave the next reader to redo it.
    ("signed key byte, unmasked", False,
     "secHmacS1Blk[i] = (PeekA(kb + i) & 255) ! $5C",
     "secHmacS1Blk[i] = PeekB(kb + i) ! $5C", 1,
     "PROVABLY UNOBSERVABLE. The destination is a byte array and the "
     "XOR operand is below 256, so only the low octet can differ and "
     "only the low octet is stored"),

    ("outer hash absorbs the wrong length", True,
     "Sha1Update(@secHmacS1Inner[0], #HMACSHA1_MAC)",
     "Sha1Update(@secHmacS1Inner[0], 16)", 1,
     "the outer hash takes the whole 20-byte inner digest"),

    ("the opad state is never restored", True,
     "  Sha1Restore(@secHmacS1Opad[0])\n", "\n", 1,
     "without it the outer hash continues the inner one"),

    ("Begin restores opad instead of ipad", True,
     "Procedure HmacSha1Begin()\n  Sha1Restore(@secHmacS1Ipad[0])",
     "Procedure HmacSha1Begin()\n  Sha1Restore(@secHmacS1Opad[0])", 1,
     "only the reuse cases would notice, which is why they exist"),

    ("truncation clamps to the wrong ceiling", True,
     "  If n > #HMACSHA1_MAC\n    n = #HMACSHA1_MAC\n  EndIf",
     "  If n > #HMACSHA1_MAC\n    n = 16\n  EndIf", 1,
     "asking for 20 bytes would silently get 16"),
]


def mutate() -> int:
    src = LIB.read_text(encoding="utf-8")
    s = build_script(subset=True)
    failures = 0
    print("MUTATION TEST - each defect must do what its expectation says")
    for name, expect_red, old, new, count, why in MUTATIONS:
        n = src.count(old)
        if n != count:
            print("  %-40s CANNOT APPLY - anchor occurs %d times, expected %d"
                  % (name, n, count))
            failures += 1
            continue
        mut = WORK / "hmacsha1_mut.pi4"
        mut.write_text(src.replace(old, new), encoding="utf-8")
        red = None
        note = ""
        try:
            build("_work/hmacsha1_mut.pi4", WORK / "hmacsha1harness_mut.pi4",
                  WORK / "hmacsha1check_mut.img")
        except SystemExit:
            red, note = True, "refused to build"
        if red is None:
            try:
                bad = check(WORK / "hmacsha1check_mut.img", s, quiet=True)
                red = len(bad) > 0
                note = "%d of %d" % (len(bad), len(s.labels))
            except SystemExit:
                red, note = True, "the harness did not complete"

        if red == expect_red:
            print("  %-40s %-5s (%s)" % (name, "RED" if red else "GREEN", note))
            if not expect_red:
                print("        expected green: %s" % why)
        else:
            failures += 1
            if expect_red:
                print("  %-40s *** GREEN - THE GATE DID NOT SEE IT *** %s"
                      % (name, why))
            else:
                print("  %-40s *** RED, EXPECTED GREEN *** %s" % (name, why))
    return failures


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="path of PureMetalForge.exe (or set PMF_COMPILER); "
                         "it is run with --compile")
    ap.add_argument("--target", choices=sorted(TARGETS),
                    default="pi4",
                    help="which AArch64 board's image contract "
                         "to build and grade against")
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args()
    globals()["PMFC"] = resolve_compiler(args.compiler)
    apply_target(globals(), args.target)
    # A GATE THAT DOES NOT SAY WHICH BOARD IT GRADED IS A RESULT
    # THAT CAN BE FILED AGAINST THE WRONG ONE.  Printed before any
    # work, so it is at the top of the transcript even on a failure.
    print("[gate] target %s - %s, image at $%08X, stack $%08X"
          % (TARGET_NAME, TARGET_WHAT, LOAD, STACK))

    WORK.mkdir(exist_ok=True)
    build("RaspberryPi4/Lib/hmacsha1.pi4", WORK / "hmacsha1harness.pi4",
          WORK / "hmacsha1check.img")

    if args.mutate:
        s = build_script(subset=True)
        bad = check(WORK / "hmacsha1check.img", s)
        if bad:
            print("the unmutated library is already failing; fix that first")
            print("\n".join(bad[:10]))
            return 1
        return 1 if mutate() else 0

    t0 = time.time()
    print("HMAC-SHA1 gate - oracle: RFC 2202 section 3, parsed from disk")
    s = build_script()
    bad = check(WORK / "hmacsha1check.img", s)
    print("  %.1f s" % (time.time() - t0))
    if bad:
        print("\nFAILURES")
        print("\n".join(bad))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
