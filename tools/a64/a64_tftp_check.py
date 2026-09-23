#!/usr/bin/env python3
r"""Executable gate for RaspberryPi4/Lib/tftp.pi4 - TFTP, RFC 1350, client side.

There is no Pi 4 here, no network, no server and no filesystem.  None of
them is needed, and that is a property of the library rather than a
shortcut taken by the gate: tftp.pi4 performs no input and no output.
It never calls NetUdpBuild, it never calls GenetSend, it never calls
FatWrite, it touches no MMIO.  It builds TFTP payloads into one buffer
and parses TFTP payloads out of another, so the only thing that has to
be fabricated to test it is a PL011 that swallows characters.

WHAT THIS GATE DOES

  A fixed harness - written into _work by this script, never edited by
  hand - includes uart.pi4 and tftp.pi4 and executes a SCRIPT that this
  script writes into the machine's memory before the run.  Each script
  record names one library call and carries its arguments and, where
  there is one, a TFTP payload.  Each result record carries the return
  value, TftpError(), three extra readings, and a byte-for-byte copy of
  whatever the library staged in TftpOutBuf().

  So the gate hands the library REAL TFTP DATAGRAMS, BYTE BY BYTE, and
  grades REAL TFTP DATAGRAMS, BYTE BY BYTE.  A read request is nineteen
  octets and all nineteen are compared, against bytes assembled from
  words read out of the RFC.

HOW HONEST THIS GATE IS, STATED PLAINLY - AND IT IS MORE HONEST THAN
a64_net_check.py CAN BE

  That gate has to say of itself: "EVERYTHING ELSE ... is written here
  from the protocol definitions, exactly as it is written in net.pi4.
  THAT IS A SECOND TRANSCRIPTION, NOT A SECOND READING."  It then asks
  for the RFCs to be put on the disk so that the gate can parse the
  spec instead of restating it.

  THEY ARE ON THE DISK NOW.  RaspberryPi4/Reference/rfc1350.txt was
  downloaded on 2026-08-26, with rfc1123.txt, rfc768.txt, rfc826.txt,
  rfc791.txt, rfc792.txt, rfc2347.txt, rfc2348.txt and rfc2349.txt
  beside it.  So this gate does not restate the protocol.  It PARSES it:

    * THE FIVE OPCODES are read out of the table at rfc1350.txt:266-271
      by regular expression, and cross-checked against the #define block
      in v2025.01_net_tftp.c:35-39, and cross-checked again against the
      #TFTP_OP_* constants parsed out of tftp.pi4 itself.  THREE
      INDEPENDENT READINGS, and any two disagreeing turns this gate red.
    * THE EIGHT ERROR CODES are read out of the table at
      rfc1350.txt:511-522, with their English meanings, and matched
      against #TFTP_ERR_* in the library.
    * THE WORD "octet" IS NOT TYPED HERE.  It is lifted out of
      rfc1350.txt:298 - the sentence listing the three modes - and the
      expected bytes of every read request are built from it.  So a
      library that spelled the mode wrong could not be graded green by a
      gate that had made the same slip, because the gate did not spell
      it at all.
    * 512, 511, 516 AND 69 are all matched out of the RFC's own
      sentences rather than typed, and each match is printed with its
      line number when the gate runs.
    * THE SORCERER'S APPRENTICE RULE is located in rfc1123.txt by its
      own words and its line number reported, so that the comment in
      tftp.pi4 citing it cannot go stale unnoticed.

  What remains untested by construction is the same thing that is
  untested in every codec gate: this proves the bytes are the bytes the
  documents describe.  It does not prove a real server likes them.  For
  that, plug the cable in and read the last section of tftp.pi4's
  header.

WHAT IS ASSERTED

  * A READ REQUEST IS BYTE-EXACT, opcode and filename and terminator and
    mode and terminator, and it goes to PORT 69 - which is the only
    packet in a transfer that ever does.
  * THE SERVER'S TRANSFER IDENTIFIER IS ADOPTED FROM THE FIRST DATA
    PACKET, and every packet after it is addressed there and not to 69.
    This is the classic first-TFTP-client failure and it has its own
    case, its own accessor check, and its own mutation.
  * A WRONG TRANSFER IDENTIFIER IS ANSWERED, NOT DROPPED - with ERROR 5,
    addressed to the STRANGER and not to the server - AND THE TRANSFER
    IS UNDISTURBED, which is checked by carrying on with it afterwards.
  * A DUPLICATE DATA PACKET STAGES NOTHING AT ALL.  The Sorcerer's
    Apprentice rule, receiving side.
  * A DUPLICATE ACK STAGES NOTHING AT ALL.  The Sorcerer's Apprentice
    rule as RFC 1123 words it, sending side.
  * A BLOCK FROM THE FUTURE re-acknowledges the last good block ONCE,
    and the second one is silent.
  * A SHORT BLOCK ENDS THE TRANSFER, and its acknowledgement is still
    staged and must still be sent.
  * A FILE THAT IS AN EXACT MULTIPLE OF 512 IS TESTED IN BOTH
    DIRECTIONS.  Reading, a zero-length final DATA must end it.
    Writing, a zero-length final DATA must be produced - a four-byte
    datagram that is entirely header.  Two of the sixteen mutations
    exist only to break this one case.
  * BLOCK NUMBER WRAPAROUND IS EXERCISED AT THE BOUNDARY: 65534, 65535,
    0, 1, with the byte offsets required to stay contiguous across it,
    and with a duplicate of block 0 and a duplicate of block 65535
    required to be recognised as duplicates rather than as a gap.
  * THE DESTINATION IS BOUNDS CHECKED AND THE REFUSAL IS BEFORE THE
    WRITE.  The gate reads the emulator's memory past the capacity
    afterwards and requires it to be untouched.
  * AN ERROR PACKET FAILS THE TRANSFER, STAGES NOTHING, and its code and
    the server's own message text come back intact.
  * EVERY ERROR CODE HAS DISTINCT ENGLISH, checked by pulling all nine
    sentences out of the running library and requiring them to differ.
  * THE RETRANSMIT TIMER FIRES, REBUILDS THE PACKET BYTE-IDENTICALLY,
    AND GIVES UP AFTER THE RETRY COUNT - and progress restarts it.

Run:  python tools/a64/a64_tftp_check.py
      python tools/a64/a64_tftp_check.py --mutate

--mutate rebuilds the library with a deliberate defect in it, sixteen
times, and requires the gate to go RED each time.  A gate that only
tested the happy path would pass on a client that never retransmits, so
one of the sixteen is exactly that.
"""

from __future__ import annotations
import os

import argparse
import pathlib
import re
import struct
import sys

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

REFERENCE = ROOT / "RaspberryPi4" / "Reference"
RFC1350 = REFERENCE / "rfc1350.txt"
RFC1123 = REFERENCE / "rfc1123.txt"
RFC2347 = REFERENCE / "rfc2347.txt"
UBOOT_TFTP = REFERENCE / "v2025.01_net_tftp.c"
UBOOT_CMD = REFERENCE / "v2025.01_cmd_net.c"

PMFC = os.environ.get("PMF_COMPILER") or "PureMetalForge.exe"  # rebound from --compiler
# Every compile resolves includes from THIS tree only.
BUILD_ENV = dict(os.environ, PMF_ROOT=str(ROOT))
LIB = ROOT / "RaspberryPi4" / "Lib" / "tftp.pi4"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4TftpProbe.pi4"
WORK = ROOT / "_work"

LOAD = 0x00400000
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

LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
STEP_LIMIT = 400_000_000

UART_LO = 0xFE201000
UART_HI = 0xFE201048
UART_DR = 0xFE201000

# Where the script and the results live, and where the transfer's
# memory lives.  All far above the image at $400000 and the stack top at
# $3000000, and nowhere near anything tftp.pi4 or uart.pi4 touches.
H_SCRIPT = 0x06000000
H_RESULT = 0x06800000
DEST = 0x07000000        # a read's destination window
SRC = 0x07800000         # a write's source buffer


# =====================================================================
#  THE SPEC, PARSED - NOT TYPED
# =====================================================================
# Everything in this section is READ OFF THE DISK.  If a number appears
# as a literal below it is only ever as something to CHECK a parsed
# value against, never as the value itself, and the check names the file
# and the line it came from.


def read_lines(path: pathlib.Path) -> list[str]:
    if not path.exists():
        raise SystemExit(
            "the citation is missing: %s\n"
            "Download it into RaspberryPi4/Reference/ - it is small, it is\n"
            "stable, and this gate PARSES it rather than restating it.\n"
            "  https://www.rfc-editor.org/rfc/%s" % (path, path.name))
    # SPLIT ON NEWLINES ONLY.  Python's str.splitlines() also breaks on
    # a form feed, and an RFC is full of them - one per page - so its
    # line numbers came out four or five higher than the ones a person
    # gets from grep, and every citation this gate printed would have
    # sent the next reader to the wrong line.
    return path.read_text(errors="replace").split(chr(10))


class Spec:
    """Everything this gate knows about TFTP, and where each bit came
    from.  Nothing is constructed here that was not found in a file."""

    def __init__(self) -> None:
        self.cite: dict[str, str] = {}
        rfc = read_lines(RFC1350)
        self.opcodes = self._opcodes(rfc)
        self.errors = self._errors(rfc)
        self.mode = self._mode(rfc)
        self.port = self._port(rfc)
        self.block = self._block(rfc)
        self.short_max = self._short_max(rfc)
        self.datagram_max = self._datagram_max(rfc)
        self.sas_line = self._sas(read_lines(RFC1123))
        self.sequence = self._sequence(rfc)
        self.oack = self._oack(read_lines(RFC2347))
        self.uboot = self._uboot()

    # ---- RFC 1350, the DATA packet figure: the block number's width ---
    def _sequence(self, rfc: list[str]) -> int:
        """The block number field is two octets wide, so it wraps at 65536.

        Read from the DATA packet figure, whose width row sits directly
        above the row naming the fields.
        """
        for i, line in enumerate(rfc):
            if "| Opcode |" in line and "Block #" in line and "Data" in line:
                widths = re.findall(r"(\d+) bytes", rfc[i - 2] if i >= 2 else "")
                if len(widths) >= 2:
                    self.cite["sequence"] = "rfc1350.txt:%d" % (i - 1)
                    return 1 << (8 * int(widths[1]))
        raise SystemExit(
            "rfc1350.txt no longer carries the DATA packet figure with the "
            "width of the block number field.  Check the figure in section 5.")

    # ---- RFC 2347, the option acknowledgement opcode ------------------
    def _oack(self, rfc: list[str]) -> int:
        want = re.compile(r"The opcode field contains a (\d+), for Option Acknowledgment")
        for i, line in enumerate(rfc, 1):
            m = want.search(line)
            if m:
                self.cite["oack"] = "rfc2347.txt:%d" % i
                return int(m.group(1))
        raise SystemExit(
            "rfc2347.txt no longer states the opcode of the option "
            "acknowledgement (OACK) packet.  Check the OACK format section.")

    # ---- RFC 1350, section 5, the opcode table ----------------------
    def _opcodes(self, rfc: list[str]) -> dict[str, int]:
        """
                  opcode  operation
                    1     Read request (RRQ)
                    ...
        """
        want = re.compile(r"^\s+([1-5])\s+[A-Za-z][A-Za-z ]*\((RRQ|WRQ|DATA|ACK|ERROR)\)\s*$")
        found: dict[str, int] = {}
        for i, line in enumerate(rfc, 1):
            m = want.match(line)
            if m:
                found[m.group(2)] = int(m.group(1))
                self.cite.setdefault("opcodes", "rfc1350.txt:%d" % i)
        if len(found) != 5:
            raise SystemExit(
                "rfc1350.txt no longer carries the five-row opcode table this "
                "gate parses (found %r).  Do not replace it with literals - "
                "find where the table moved." % sorted(found))
        return found

    # ---- RFC 1350, appendix, the error code table -------------------
    def _errors(self, rfc: list[str]) -> dict[int, str]:
        start = None
        for i, line in enumerate(rfc):
            if line.strip() == "Error Codes":
                start = i
                break
        if start is None:
            raise SystemExit("rfc1350.txt no longer has an 'Error Codes' section.")
        want = re.compile(r"^\s{3}([0-7])\s{5,}(\S.*?)\s*$")
        found: dict[int, str] = {}
        for i in range(start, min(start + 30, len(rfc))):
            m = want.match(rfc[i])
            if m:
                found[int(m.group(1))] = m.group(2)
                self.cite.setdefault("errors", "rfc1350.txt:%d" % (i + 1))
        if sorted(found) != [0, 1, 2, 3, 4, 5, 6, 7]:
            raise SystemExit(
                "rfc1350.txt's error code table no longer has codes 0..7 "
                "(found %r)." % sorted(found))
        return found

    # ---- the three transfer modes -----------------------------------
    def _mode(self, rfc: list[str]) -> bytes:
        """Lift the word octet out of the RFC's own sentence.

        rfc1350.txt:298 reads
            string "netascii", "octet", or "mail" (or any combination of
        and this gate never types the word itself, so a gate and a
        library cannot agree on the same misspelling.
        """
        want = re.compile(r'"netascii",\s*"([a-z]+)",\s*or\s*"mail"')
        for i, line in enumerate(rfc, 1):
            m = want.search(line)
            if m:
                self.cite["mode"] = "rfc1350.txt:%d" % i
                return m.group(1).encode("ascii")
        raise SystemExit(
            "rfc1350.txt no longer carries the sentence naming the three "
            "transfer modes, which is where this gate gets the mode string.")

    # ---- the well known port ----------------------------------------
    def _port(self, rfc: list[str]) -> int:
        want = re.compile(r"known TID (\d+) decimal")
        for i, line in enumerate(rfc, 1):
            m = want.search(line)
            if m:
                self.cite["port"] = "rfc1350.txt:%d" % i
                return int(m.group(1))
        raise SystemExit("rfc1350.txt no longer states the well known TID.")

    # ---- the block size ---------------------------------------------
    def _block(self, rfc: list[str]) -> int:
        # THE SENTENCE WRAPS in the RFC's own text - "in fixed" ends one
        # line and "length blocks of 512 bytes" begins the next - so the
        # search is over the joined text and the citation is the line
        # the number itself lives on.  Matching the whole sentence one
        # line at a time looked correct and found nothing.
        joined = " ".join(x.strip() for x in rfc)
        m = re.search(r"fixed\s+length blocks of (\d+) bytes", joined)
        if not m:
            raise SystemExit("rfc1350.txt no longer states the 512-byte block.")
        for i, line in enumerate(rfc, 1):
            if "length blocks of" in line:
                self.cite["block"] = "rfc1350.txt:%d" % i
                break
        return int(m.group(1))

    # ---- what ends a transfer ---------------------------------------
    def _short_max(self, rfc: list[str]) -> int:
        """"if it is from zero to 511 bytes long, it signals the end"."""
        want = re.compile(r"from zero to (\d+) bytes long, it signals the end")
        joined = " ".join(s.strip() for s in rfc)
        m = want.search(joined)
        if not m:
            raise SystemExit(
                "rfc1350.txt no longer carries the sentence that defines what "
                "ends a transfer.  That sentence is the whole reason this "
                "gate has an exact-multiple-of-512 case.")
        for i, line in enumerate(rfc, 1):
            if "signals the end" in line:
                self.cite["short"] = "rfc1350.txt:%d" % i
                break
        return int(m.group(1))

    def _datagram_max(self, rfc: list[str]) -> int:
        """"(i.e., Datagram length < 516)" - the same rule, said in
        octets rather than in payload bytes, and the number this gate
        checks #TFTP_OUT_MAX against."""
        want = re.compile(r"Datagram length < (\d+)")
        for i, line in enumerate(rfc, 1):
            m = want.search(line)
            if m:
                self.cite["datagram"] = "rfc1350.txt:%d" % i
                return int(m.group(1))
        raise SystemExit("rfc1350.txt no longer states the 516-octet datagram.")

    # ---- RFC 1123, the Sorcerer's Apprentice MUST -------------------
    def _sas(self, rfc: list[str]) -> int:
        # The sentence is broken by a PAGE BREAK in the RFC - the words
        # "duplicate ACK" are on the next page, with a footer, a header
        # and four blank lines in between - so only the half before the
        # break is matched.  Matching the whole thing found nothing.
        joined = " ".join(s.strip() for s in rfc)
        if "must never resend the current DATA packet on receipt of a" not in joined:
            raise SystemExit(
                "rfc1123.txt no longer carries the Sorcerer's Apprentice "
                "requirement, which tftp.pi4 cites by line number.")
        for i, line in enumerate(rfc, 1):
            if "Sorcerer's Apprentice" in line and "Syndrome" in line and i > 200:
                self.cite["sas"] = "rfc1123.txt:%d" % i
                return i
        return 0

    # ---- U-Boot, the second reading ---------------------------------
    def _uboot(self) -> dict[str, int]:
        # U-Boot's net/tftp.c is third-party source code and is not
        # redistributed with this repository.  When a local copy is present
        # it is a second reading of the constants; when it is absent that
        # one cross-check is skipped, loudly, and the RFC readings remain.
        if not UBOOT_TFTP.exists():
            print("NOTE: %s is not present, so the U-Boot cross-check of the "
                  "TFTP constants is skipped.  The RFC 1350 and RFC 2347 "
                  "readings are still checked against tftp.pi4."
                  % UBOOT_TFTP.relative_to(ROOT).as_posix())
            return {}
        text = UBOOT_TFTP.read_text(errors="replace")
        out: dict[str, int] = {}
        for name in ("TFTP_RRQ", "TFTP_WRQ", "TFTP_DATA", "TFTP_ACK",
                     "TFTP_ERROR", "TFTP_OACK"):
            m = re.search(r"#define\s+%s\s+(\d+)" % name, text)
            if not m:
                raise SystemExit(
                    "v2025.01_net_tftp.c no longer defines %s, which this "
                    "gate uses as its second reading of the opcodes." % name)
            out[name] = int(m.group(1))
        m = re.search(r"#define\s+WELL_KNOWN_PORT\s+(\d+)", text)
        if not m:
            raise SystemExit("v2025.01_net_tftp.c no longer defines WELL_KNOWN_PORT.")
        out["PORT"] = int(m.group(1))
        m = re.search(r"#define\s+TFTP_BLOCK_SIZE\s+(\d+)", text)
        if not m:
            raise SystemExit("v2025.01_net_tftp.c no longer defines TFTP_BLOCK_SIZE.")
        out["BLOCK"] = int(m.group(1))
        m = re.search(r"#define\s+TFTP_SEQUENCE_SIZE\s+\(\(ulong\)\(1<<(\d+)\)\)", text)
        if not m:
            raise SystemExit("v2025.01_net_tftp.c no longer defines TFTP_SEQUENCE_SIZE.")
        out["SEQUENCE"] = 1 << int(m.group(1))
        return out


def library_constants() -> dict[str, int]:
    """Parse the #TFTP_* constants out of tftp.pi4.

    The library states them; the RFC states them; U-Boot states them.
    The gate's job is to notice when the three stop agreeing, which it
    cannot do if it only ever reads one of them.
    """
    text = LIB.read_text(encoding="utf-8", errors="replace")
    out: dict[str, int] = {}
    for m in re.finditer(r"^#(TFTP_[A-Za-z0-9_]+)\s*=\s*(\$?[0-9A-Fa-f]+)\s*(?:;.*)?$",
                         text, re.M):
        raw = m.group(2)
        out[m.group(1)] = int(raw[1:], 16) if raw.startswith("$") else int(raw)
    return out


def confirm_three_readings(spec: Spec, lib: dict[str, int], fails: list[str]) -> None:
    """The opcodes, the port, the block size and the error codes, from
    the RFC, from U-Boot and from the library.  Any two disagreeing is a
    failure and the message names which two."""
    pairs = [("RRQ", "TFTP_OP_RRQ", "TFTP_RRQ"),
             ("WRQ", "TFTP_OP_WRQ", "TFTP_WRQ"),
             ("DATA", "TFTP_OP_DATA", "TFTP_DATA"),
             ("ACK", "TFTP_OP_ACK", "TFTP_ACK"),
             ("ERROR", "TFTP_OP_ERROR", "TFTP_ERROR")]
    # When the U-Boot source is absent (it is third-party code and is not
    # redistributed), each U-Boot reading falls back to the RFC reading, so
    # the comparison degrades to RFC against library and never to nothing.
    ub = spec.uboot
    for rfcname, libname, ubname in pairs:
        r = spec.opcodes[rfcname]
        u = ub.get(ubname, r)
        v = lib.get(libname)
        if v is None:
            fails.append("tftp.pi4 does not define #%s" % libname)
            continue
        if not (r == u == v):
            fails.append("opcode %s: rfc1350 says %d, u-boot says %d, "
                         "tftp.pi4 says %d" % (rfcname, r, u, v))

    if not (spec.oack == ub.get("TFTP_OACK", spec.oack) == lib.get("TFTP_OP_OACK")):
        fails.append("the option acknowledgement opcode: rfc2347 says %d, "
                     "u-boot says %s, tftp.pi4 says %s"
                     % (spec.oack, ub.get("TFTP_OACK", "(not read)"),
                        lib.get("TFTP_OP_OACK")))

    if not (spec.port == ub.get("PORT", spec.port) == lib.get("TFTP_WELL_KNOWN_PORT")):
        fails.append("the well known port: rfc1350 says %d, u-boot says %s, "
                     "tftp.pi4 says %s"
                     % (spec.port, ub.get("PORT", "(not read)"),
                        lib.get("TFTP_WELL_KNOWN_PORT")))

    if not (spec.block == ub.get("BLOCK", spec.block) == lib.get("TFTP_BLOCK")):
        fails.append("the block size: rfc1350 says %d, u-boot says %s, "
                     "tftp.pi4 says %s"
                     % (spec.block, ub.get("BLOCK", "(not read)"),
                        lib.get("TFTP_BLOCK")))

    if not (spec.sequence == ub.get("SEQUENCE", spec.sequence) == lib.get("TFTP_SEQUENCE")):
        fails.append("the block number wraps at %s in tftp.pi4, at %d by "
                     "rfc1350's two-octet block field, and at %s in u-boot"
                     % (lib.get("TFTP_SEQUENCE"), spec.sequence,
                        ub.get("SEQUENCE", "(not read)")))

    # The RFC states the end of a transfer twice, once as "zero to 511
    # bytes of payload" and once as "Datagram length < 516".  Those two
    # must agree with each other and with the library's buffer.
    if spec.short_max + 1 != spec.block:
        fails.append("rfc1350 says a block is %d bytes but that a payload of "
                     "up to %d ends the transfer, and those cannot both be "
                     "true" % (spec.block, spec.short_max))
    derived = lib.get("TFTP_DATA_HDR", 0) + lib.get("TFTP_BLOCK", 0)
    if lib.get("TFTP_OUT_MAX") != derived:
        fails.append("#TFTP_OUT_MAX is %s but #TFTP_DATA_HDR + #TFTP_BLOCK is "
                     "%d - this compiler takes only a literal in a constant "
                     "declaration, so the two have to be kept in step by hand "
                     "and this is the check that notices"
                     % (lib.get("TFTP_OUT_MAX"), derived))
    if derived != spec.datagram_max:
        fails.append("the largest datagram is %d octets by tftp.pi4's "
                     "arithmetic and %d by rfc1350's own sentence"
                     % (derived, spec.datagram_max))

    # The eight error codes, by value.  Their English is checked
    # separately, out of the running library.
    for code, meaning in spec.errors.items():
        libname = {0: "TFTP_ERR_UNDEFINED", 1: "TFTP_ERR_NOT_FOUND",
                   2: "TFTP_ERR_ACCESS", 3: "TFTP_ERR_DISK_FULL",
                   4: "TFTP_ERR_ILLEGAL", 5: "TFTP_ERR_UNKNOWN_TID",
                   6: "TFTP_ERR_EXISTS", 7: "TFTP_ERR_NO_USER"}[code]
        if lib.get(libname) != code:
            fails.append("error code %d (%s): tftp.pi4's #%s is %s"
                         % (code, meaning, libname, lib.get(libname)))

    # The mode string, one letter at a time, against the #TFTP_CH_*
    # constants the library writes it from.  This is the one place the
    # house rule about character literals can actually be graded.
    for ch in sorted(set(spec.mode)):
        name = "TFTP_CH_%s" % chr(ch)
        if lib.get(name) != ch:
            fails.append("the mode string needs the letter %s, which is ASCII "
                         "%d; tftp.pi4's #%s is %s"
                         % (chr(ch), ch, name, lib.get(name)))


# =====================================================================
#  AN INDEPENDENT ENCODER
# =====================================================================
# Written from the parsed spec, not from the library.  Every field is
# packed big-endian with struct, where the library walks bytes and
# shifts - two implementations that share no code do not share a
# byte-order slip.
class Wire:
    def __init__(self, spec: Spec) -> None:
        self.s = spec

    def rrq(self, name: bytes) -> bytes:
        return (struct.pack(">H", self.s.opcodes["RRQ"])
                + name + b"\x00" + self.s.mode + b"\x00")

    def wrq(self, name: bytes) -> bytes:
        return (struct.pack(">H", self.s.opcodes["WRQ"])
                + name + b"\x00" + self.s.mode + b"\x00")

    def data(self, block: int, payload: bytes) -> bytes:
        return struct.pack(">HH", self.s.opcodes["DATA"], block) + payload

    def ack(self, block: int) -> bytes:
        return struct.pack(">HH", self.s.opcodes["ACK"], block)

    def error(self, code: int, msg: bytes) -> bytes:
        return struct.pack(">HH", self.s.opcodes["ERROR"], code) + msg + b"\x00"

    def oack(self, body: bytes) -> bytes:
        return struct.pack(">H", 6) + body


def ip4(a: int, b: int, c: int, d: int) -> int:
    return (a << 24) | (b << 16) | (c << 8) | d


def dotted(v: int) -> str:
    return "%d.%d.%d.%d" % ((v >> 24) & 0xFF, (v >> 16) & 0xFF,
                            (v >> 8) & 0xFF, v & 0xFF)


def pattern(block: int, n: int) -> bytes:
    """A payload whose every byte depends on the block number, so that a
    block stored at the wrong offset cannot look right."""
    return bytes(((block * 37 + i * 11) & 0xFF) for i in range(n))


# =====================================================================
#  THE HARNESS
# =====================================================================
# A fixed source file.  Everything that varies between runs arrives as
# DATA in memory, so this text is the same for the clean library and for
# every mutant, and no test case is ever expressed in harness source.
(OP_RESET, OP_TIMEOUT, OP_SINK, OP_READ, OP_WRITE, OP_INPUT, OP_TICK,
 OP_CANCEL, OP_STATUS, OP_COUNTS, OP_COUNTS2, OP_TID, OP_SRVERR,
 OP_BLOCKWIN, OP_PORT, OP_FORCE, OP_ERRTEXT, OP_CODETEXT, OP_INTEXT,
 OP_STATETEXT) = range(1, 21)

SINK_NONE, SINK_MEMORY, SINK_CALLER = 0, 1, 2

HARNESS = r'''
; ======================================================================
;  tftpharness.pi4 - GENERATED BY tools/a64/a64_tftp_check.py. DO NOT EDIT.
; ======================================================================
;  It reads a script of library calls out of memory at #H_SCRIPT, runs
;  them, and writes a result record for each into #H_RESULT. The gate
;  puts the script there before the run and reads the results out
;  afterwards, so every datagram in every test case is DATA and this
;  file never has to change to add one.
;
;  SCRIPT RECORD, 24 bytes then `ln` bytes of blob, padded to 4:
;     +0 op  +4 a  +8 b  +12 c  +16 d  +20 ln  +24 blob
;  op 0 ends the script.
;
;  RESULT RECORD, 28 bytes then `n` bytes of blob, padded to 4:
;     +0 op  +4 result  +8 err  +12 e1  +16 e2  +20 e3  +24 n  +28 blob
;
;  For every op that can stage a packet, e1/e2/e3 are TftpOutIp(),
;  TftpOutPort() and TftpState(), and the blob is the staged packet
;  byte for byte. That means EVERY record in the run is graded on where
;  the packet was going as well as on what was in it.
; ======================================================================
XIncludeFile "RaspberryPi4/Lib/uart.pi4"
XIncludeFile "__LIB__"

#H_SCRIPT = $06000000
#H_RESULT = $06800000

Procedure.i hStrLen(*s)
  Define i.i
  i = 0
  While PeekA(*s + i) <> 0
    i = i + 1
  Wend
  ProcedureReturn i
EndProcedure

Procedure.i Main()
  Define p.i
  Define q.i
  Define op.i
  Define a.i
  Define b.i
  Define c.i
  Define d.i
  Define ln.i
  Define blob.i
  Define r.i
  Define er.i
  Define e1.i
  Define e2.i
  Define e3.i
  Define n.i
  Define src.i
  Define i.i

  TftpInit()
  p = #H_SCRIPT
  q = #H_RESULT

  Repeat
    op = PeekN(p)
    If op = 0
      Break
    EndIf
    a    = PeekN(p + 4)
    b    = PeekN(p + 8)
    c    = PeekN(p + 12)
    d    = PeekN(p + 16)
    ln   = PeekN(p + 20)
    blob = p + 24

    r = 0
    er = 0
    e1 = 0
    e2 = 0
    e3 = 0
    n = 0
    src = 0

    If op = 1
      TftpInit()
      r = 1
    ElseIf op = 2
      r = TftpSetTimeout(a, b)
    ElseIf op = 3
      If a = 0
        r = TftpSetSinkNone()
      ElseIf a = 1
        r = TftpSetMemory(b, c)
      Else
        r = TftpSetSinkCaller()
      EndIf
    ElseIf op = 4
      r = TftpBeginRead(a, blob, b)
    ElseIf op = 5
      r = TftpBeginWrite(a, blob, b, c, d)
    ElseIf op = 6
      r = TftpInput(a, b, c, blob, ln)
    ElseIf op = 7
      r = TftpTick(a)
    ElseIf op = 8
      r = TftpCancel()
    ElseIf op = 9
      r = TftpBlocksDone()
      e1 = TftpBlock()
      e2 = TftpWraps()
      e3 = TftpBytes()
    ElseIf op = 10
      r = TftpDataCount()
      e1 = TftpDupCount()
      e2 = TftpGapCount()
      e3 = TftpStrangerCount()
    ElseIf op = 11
      r = TftpRetransmitCount()
      e1 = TftpIgnoredCount()
      e2 = TftpTriesUsed()
      e3 = TftpState()
    ElseIf op = 12
      r = TftpServerPort()
      e1 = TftpLocalPort()
      e2 = TftpTidLocked()
      e3 = TftpServerIp()
    ElseIf op = 13
      r = TftpServerCode()
      e1 = TftpServerMessageLen()
      e2 = TftpRetryWorthwhile()
      src = TftpServerMessage()
      n = e1
    ElseIf op = 14
      r = TftpBlockLen()
      src = TftpBlockData()
      n = r
    ElseIf op = 15
      r = TftpSuggestPort(a)
    ElseIf op = 16
      ; THE ONE WHITE-BOX POKE IN THIS GATE. See the gate's own comment
      ; at THE WRAPAROUND for why: reaching block 65535 honestly costs
      ; 33 MB of script and hours of emulation, and the arithmetic being
      ; tested is four lines long.
      tftp_block = a
      tftp_wraps = b
      r = 1
    ElseIf op = 17
      src = TftpErrorText()
      n = hStrLen(src)
      r = n
    ElseIf op = 18
      src = TftpCodeText(a)
      n = hStrLen(src)
      r = n
    ElseIf op = 19
      src = TftpInputText(a)
      n = hStrLen(src)
      r = n
    ElseIf op = 20
      src = TftpStateText()
      n = hStrLen(src)
      r = n
    EndIf

    ; The default readings, taken for every op that did not fill them in
    ; itself. A record that stages nothing therefore still says where
    ; nothing was staged to, which is how "the buffer was cleared" gets
    ; graded rather than assumed.
    If op < 9
      er = TftpError()
      e1 = TftpOutIp()
      e2 = TftpOutPort()
      e3 = TftpState()
      n = TftpOutLen()
      src = TftpOutBuf()
    EndIf
    If op = 16
      er = TftpError()
      e1 = TftpOutIp()
      e2 = TftpOutPort()
      e3 = TftpState()
      n = TftpOutLen()
      src = TftpOutBuf()
    EndIf

    PokeN(q + 0, op)
    PokeN(q + 4, r)
    PokeN(q + 8, er)
    PokeN(q + 12, e1)
    PokeN(q + 16, e2)
    PokeN(q + 20, e3)
    PokeN(q + 24, n)
    If n > 0
      i = 0
      While i < n
        PokeB(q + 28 + i, PeekA(src + i))
        i = i + 1
      Wend
    EndIf

    p = p + 24 + (((ln + 3) / 4) * 4)
    q = q + 28 + (((n + 3) / 4) * 4)
  ForEver

  PokeN(q, 0)
  UartWriteStr("tftpharness done")
  ProcedureReturn 0
EndProcedure
'''


class Script:
    """Builds the byte stream the harness walks, and remembers what each
    record was for so a failure can name itself."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: list[str] = []

    def add(self, op: int, label: str, a: int = 0, b: int = 0, c: int = 0,
            d: int = 0, blob: bytes = b"") -> int:
        idx = len(self.labels)
        self.labels.append(label)
        self.buf += struct.pack("<6I", op, a & 0xFFFFFFFF, b & 0xFFFFFFFF,
                                c & 0xFFFFFFFF, d & 0xFFFFFFFF, len(blob))
        self.buf += blob
        while len(self.buf) % 4:
            self.buf.append(0)
        return idx

    def finish(self) -> bytes:
        return bytes(self.buf) + struct.pack("<I", 0)


class Result:
    __slots__ = ("op", "r", "err", "e1", "e2", "e3", "blob", "label")

    def __init__(self, op, r, err, e1, e2, e3, blob, label):
        self.op, self.r, self.err = op, r, err
        self.e1, self.e2, self.e3 = e1, e2, e3
        self.blob, self.label = blob, label


def signed(v: int) -> int:
    return v - 0x100000000 if v & 0x80000000 else v


def read_results(mem, labels: list[str]) -> list[Result]:
    out: list[Result] = []
    addr = H_RESULT
    while True:
        def w(off):
            return sum(mem.get(addr + off + i, 0) << (8 * i) for i in range(4))
        op = w(0)
        if op == 0:
            break
        n = w(24)
        if n > 4096:
            raise SystemExit(
                "a result record claims %d bytes of datagram, which is longer "
                "than any TFTP packet can be.  The harness or the result "
                "stream has been corrupted." % n)
        blob = bytes(mem.get(addr + 28 + i, 0) for i in range(n))
        i = len(out)
        out.append(Result(op, signed(w(4)), signed(w(8)), w(12), w(16), w(20),
                          blob, labels[i] if i < len(labels) else "?"))
        addr += 28 + ((n + 3) // 4) * 4
    return out


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def write_harness(lib_include: str, path: pathlib.Path) -> None:
    WORK.mkdir(exist_ok=True)
    path.write_text(patch_harness(HARNESS.replace("__LIB__", lib_include),
                              globals()), encoding="utf-8")


def build(source: pathlib.Path, out: pathlib.Path) -> None:
    import subprocess
    WORK.mkdir(exist_ok=True)
    cmd = [str(PMFC), "--compile", str(source), "-t", TFLAG,
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, env=BUILD_ENV, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("build failed:\n" + r.stdout)


def run(img: pathlib.Path, script: bytes, preload: dict[int, bytes]):
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[LOAD + i] = b
    # Names for the alignment rule's message. "alignment fault at
    # $00484EDA" sends someone hunting; "cyw43seteventmask+332,
    # cyw43.pi4 line 4762" ends the search. Read from the `.dbg` pmfc
    # already writes - NOT the `.sym`, which mixes absolute BSS
    # addresses with load-relative code ones (A64Assembler.pbi:1994-1997)
    # and whose wrong half reads as a column of zeroes rather than an
    # error. A missing `.dbg` costs the name, not the check.
    attach_symbols(cpu, img, LOAD)
    for i, b in enumerate(script):
        mem[H_SCRIPT + i] = b
    for base, data in preload.items():
        for i, b in enumerate(data):
            mem[base + i] = b
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR

    uart = bytearray()
    steps = [0]

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
    plain_step = A64.step.__get__(cpu)

    def step():
        steps[0] += 1
        # cpu.fetch, not load: an instruction fetch is Normal
        # Non-Cacheable with the MMU off, not Device, so it is not
        # subject to the data alignment rule. It still goes through
        # the closure above, so MMIO decoding is unchanged.
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:        # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = 54_000_000
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:        # MRS Xt, CNTPCT_EL0
            cpu.x[ins & 31] = steps[0] // 8
            cpu.pc += 4
            return
        plain_step()

    cpu.step = step
    for _ in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, uart, steps[0]
        step()
    raise SystemExit("the harness never returned (%d steps)\n%s"
                     % (steps[0], uart.decode("latin-1")))


# =====================================================================
#  THE BENCH GEOMETRY
# =====================================================================
SERVER = ip4(192, 168, 1, 20)
STRANGER_IP = ip4(192, 168, 1, 77)
OUR_TID = 2048
SRV_TID = 5000
SRV_TID2 = 5001
SRV_TID3 = 6789
NAME = b"anvil.img"

# The refusal codes.  Written here rather than parsed out of tftp.pi4,
# and unlike the protocol constants that is legitimate, because these
# are OURS.  If the two files disagree the gate goes red and one of them
# is wrong.
E_ARG = -200
E_STATE = -201
E_NO_DEST = -202
E_NAME = -203
E_PORT = -204
E_RUNT = -205
E_OPCODE = -206
E_OACK = -207
E_OVERSIZE = -208
E_FIRST_BLOCK = -209
E_DEST_FULL = -210
E_SERVER = -211
E_TIMEOUT = -212
E_SOURCE = -213
E_CANCELLED = -214

IN_IGNORED, IN_DATA, IN_LAST, IN_DUP = 0, 1, 2, 3
IN_GAP, IN_STRANGER, IN_ERROR, IN_ACKED, IN_SENT = 4, 5, 6, 7, 8

ST_IDLE, ST_RRQ, ST_READING, ST_WRQ, ST_WRITING, ST_COMPLETE, ST_FAILED = range(7)

# The two error messages this file sends that are worth pinning
# byte-for-byte.  Everything else is graded structurally - opcode, code,
# printable, NUL-terminated - but these two are the ones a person reads
# at three in the morning, and a silent reword should be noticed.
MSG_UNKNOWN_TID = b"that transfer identifier belongs to no transfer on this board"
MSG_DISK_FULL = b"the board has no room left for this file"

# A source buffer of exactly two blocks.  THE WHOLE POINT: 1024 is an
# exact multiple of 512, so the write must end with a zero-length DATA.
SRC_EXACT = pattern(200, 1024)
# And one that is not, so the ordinary short-block ending is covered too.
SRC_SHORT = pattern(201, 700)


def build_script(spec: Spec) -> tuple[Script, dict]:
    w = Wire(spec)
    s = Script()
    at: dict[str, int] = {}

    def a(name, *args, **kw):
        at[name] = s.add(*args, **kw)

    # =================================================================
    #  1. REFUSALS BEFORE ANYTHING IS SET UP
    # =================================================================
    a("init", OP_RESET, "TftpInit")

    # A read with no destination chosen. THE SAFETY DEFAULT: a library
    # that guessed a load address here would be a library that can
    # damage the boot image by omission.
    a("read_no_dest", OP_READ, "TftpBeginRead with no destination chosen",
      a=SERVER, b=OUR_TID, blob=NAME + b"\x00")

    a("sink_none", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("name_empty", OP_READ, "an empty filename", a=SERVER, b=OUR_TID,
      blob=b"\x00")
    a("name_control", OP_READ, "a filename with a control character",
      a=SERVER, b=OUR_TID, blob=b"an\x07vil.img\x00")
    a("name_high", OP_READ, "a filename with a byte above 126",
      a=SERVER, b=OUR_TID, blob=b"an\xE9vil.img\x00")
    a("name_long", OP_READ, "a filename of 200 bytes with no terminator "
      "inside the limit", a=SERVER, b=OUR_TID, blob=b"a" * 200 + b"\x00")
    a("port_zero", OP_READ, "transfer identifier 0", a=SERVER, b=0,
      blob=NAME + b"\x00")
    a("port_high", OP_READ, "transfer identifier 65536", a=SERVER, b=65536,
      blob=NAME + b"\x00")
    a("mem_null", OP_SINK, "TftpSetMemory at address 0", a=SINK_MEMORY,
      b=0, c=4096)
    a("mem_zero", OP_SINK, "TftpSetMemory with no capacity", a=SINK_MEMORY,
      b=DEST, c=0)
    a("timeout_zero", OP_TIMEOUT, "TftpSetTimeout(0, 5)", a=0, b=5)
    a("retries_zero", OP_TIMEOUT, "TftpSetTimeout(5000, 0)", a=5000, b=0)

    # TftpSuggestPort is U-Boot's own arithmetic and lands in 1024..4095.
    a("port_seed0", OP_PORT, "TftpSuggestPort(0)", a=0)
    a("port_seed1", OP_PORT, "TftpSuggestPort(1)", a=1)
    a("port_wrap", OP_PORT, "TftpSuggestPort(3072)", a=3072)
    a("port_big", OP_PORT, "TftpSuggestPort(123456789)", a=123456789)

    # =================================================================
    #  2. A READ REQUEST, BYTE FOR BYTE, TO PORT 69
    # =================================================================
    a("reset2", OP_RESET, "TftpInit")
    a("mem", OP_SINK, "TftpSetMemory", a=SINK_MEMORY, b=DEST, c=1 << 20)
    a("read", OP_READ, "TftpBeginRead", a=SERVER, b=OUR_TID,
      blob=NAME + b"\x00")
    a("tid_before", OP_TID, "the server's TID before any reply")

    # =================================================================
    #  3. THE FIRST BLOCK CARRIES THE SERVER'S TRANSFER IDENTIFIER
    # =================================================================
    a("data1", OP_INPUT, "DATA block 1, 512 bytes, from a NEW source port",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.data(1, pattern(1, 512)))
    a("tid_after", OP_TID, "the server's TID after the first block")
    a("status1", OP_STATUS, "one block in")

    a("data2", OP_INPUT, "DATA block 2, 512 bytes", a=SERVER, b=SRV_TID,
      c=OUR_TID, blob=w.data(2, pattern(2, 512)))

    # =================================================================
    #  4. THE SORCERER'S APPRENTICE, RECEIVING SIDE
    # =================================================================
    a("data2_dup", OP_INPUT, "DATA block 2 AGAIN - a duplicate", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.data(2, pattern(2, 512)))
    a("data1_dup", OP_INPUT, "DATA block 1 again - two behind", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.data(1, pattern(1, 512)))

    # =================================================================
    #  5. A GAP, AND THE RATE LIMIT ON COMPLAINING ABOUT IT
    # =================================================================
    a("gap5", OP_INPUT, "DATA block 5 when block 3 was expected", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.data(5, pattern(5, 512)))
    a("gap6", OP_INPUT, "DATA block 6 - the rest of a lost window",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.data(6, pattern(6, 512)))
    a("counts_gap", OP_COUNTS, "the counters after two gaps")

    # =================================================================
    #  6. A STRANGER WITH THE WRONG TRANSFER IDENTIFIER
    # =================================================================
    a("stranger", OP_INPUT, "DATA block 3 from the WRONG source port",
      a=SERVER, b=SRV_TID2, c=OUR_TID, blob=w.data(3, pattern(99, 512)))
    a("stranger_status", OP_STATUS, "the transfer must be untouched")
    a("other_host", OP_INPUT, "a packet from a different host entirely",
      a=STRANGER_IP, b=SRV_TID, c=OUR_TID, blob=w.data(3, pattern(98, 512)))
    a("wrong_local", OP_INPUT, "a packet addressed to the wrong local port",
      a=SERVER, b=SRV_TID, c=OUR_TID + 1, blob=w.data(3, pattern(97, 512)))

    # ...and the transfer carries on, which is the whole requirement.
    a("data3", OP_INPUT, "DATA block 3 - the transfer was undisturbed",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.data(3, pattern(3, 512)))

    # =================================================================
    #  7. A SHORT BLOCK ENDS IT - AND ITS ACK IS STILL STAGED
    # =================================================================
    a("data4_short", OP_INPUT, "DATA block 4, 100 bytes - short, so final",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.data(4, pattern(4, 100)))
    a("status_done", OP_STATUS, "four blocks and 1636 bytes")
    a("after_done", OP_INPUT, "a packet after the transfer completed",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.data(5, pattern(5, 512)))

    # =================================================================
    #  8. THE EXACT MULTIPLE OF 512 - THE TRAP, READING
    # =================================================================
    a("reset3", OP_RESET, "TftpInit")
    a("mem3", OP_SINK, "TftpSetMemory", a=SINK_MEMORY, b=DEST + 0x10000,
      c=1 << 20)
    a("read3", OP_READ, "a read of a file that is exactly 1024 bytes",
      a=SERVER, b=OUR_TID, blob=b"exact1024.bin\x00")
    a("ex_d1", OP_INPUT, "block 1 of 512", a=SERVER, b=SRV_TID3, c=OUR_TID,
      blob=w.data(1, pattern(11, 512)))
    a("ex_d2", OP_INPUT, "block 2 of 512 - the file is now complete but the "
      "protocol does not know it", a=SERVER, b=SRV_TID3, c=OUR_TID,
      blob=w.data(2, pattern(12, 512)))
    a("ex_d3", OP_INPUT, "block 3 of ZERO bytes - the four-byte datagram "
      "that ends an exact multiple", a=SERVER, b=SRV_TID3, c=OUR_TID,
      blob=w.data(3, b""))
    a("ex_status", OP_STATUS, "exactly 1024 bytes, three blocks")

    # =================================================================
    #  9. BLOCK NUMBER WRAPAROUND
    # =================================================================
    # Reaching block 65535 honestly costs 65535 script records of 516
    # bytes each - 33 MB of script and hours of emulation - to test four
    # lines of arithmetic.  So this is the ONE white-box case in the
    # gate: the harness writes tftp_block and tftp_wraps directly, which
    # it can do because it is compiled together with the library, and
    # then every packet after that goes through the ordinary front door.
    # There is precedent: a64_net_check.py's OP_SPIN calls net_Ticks(),
    # which is also private.
    a("reset4", OP_RESET, "TftpInit")
    a("sink4", OP_SINK, "TftpSetSinkNone - 33 MB will not fit in the "
      "emulator's memory and does not need to", a=SINK_NONE)
    a("read4", OP_READ, "a read of a very large file", a=SERVER, b=OUR_TID,
      blob=b"huge.img\x00")
    a("wrap_first", OP_INPUT, "block 1, so the TID locks normally",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.data(1, pattern(1, 512)))
    a("force", OP_FORCE, "wind the block counter to 65534", a=65534, b=0)
    a("wrap_65535", OP_INPUT, "block 65535 - the last before the wrap",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.data(65535, pattern(21, 512)))
    a("wrap_65535_st", OP_STATUS, "the offset just below the wrap")
    a("wrap_0", OP_INPUT, "block 0 - THE WRAP", a=SERVER, b=SRV_TID,
      c=OUR_TID, blob=w.data(0, pattern(22, 512)))
    a("wrap_0_st", OP_STATUS, "the wrap counter and a contiguous offset")
    a("wrap_1", OP_INPUT, "block 1 after the wrap", a=SERVER, b=SRV_TID,
      c=OUR_TID, blob=w.data(1, pattern(23, 512)))
    a("wrap_1_st", OP_STATUS, "still contiguous")
    a("wrap_dup0", OP_INPUT, "block 0 again - a DUPLICATE across the wrap, "
      "not a gap", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=w.data(0, pattern(22, 512)))
    a("wrap_dup65535", OP_INPUT, "block 65535 again - two behind, across "
      "the wrap", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=w.data(65535, pattern(21, 512)))
    a("wrap_gap", OP_INPUT, "block 4 when 2 was expected - a gap, still, "
      "after a wrap", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=w.data(4, pattern(24, 512)))

    # =================================================================
    #  10. THE DESTINATION IS BOUNDS CHECKED
    # =================================================================
    a("reset5", OP_RESET, "TftpInit")
    a("mem5", OP_SINK, "TftpSetMemory with room for 600 bytes only",
      a=SINK_MEMORY, b=DEST + 0x20000, c=600)
    a("read5", OP_READ, "a read into a window too small for the file",
      a=SERVER, b=OUR_TID, blob=b"big.img\x00")
    a("full_d1", OP_INPUT, "block 1 of 512 - fits", a=SERVER, b=SRV_TID,
      c=OUR_TID, blob=w.data(1, pattern(31, 512)))
    a("full_d2", OP_INPUT, "block 2 of 512 - does NOT fit", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.data(2, pattern(32, 512)))
    a("full_after", OP_STATUS, "nothing was written and nothing advanced")

    # =================================================================
    #  11. THE CALLER SINK - HOW A FILE REACHES fat.pi4
    # =================================================================
    a("reset6", OP_RESET, "TftpInit")
    a("sink6", OP_SINK, "TftpSetSinkCaller", a=SINK_CALLER)
    a("read6", OP_READ, "a read straight through to the caller", a=SERVER,
      b=OUR_TID, blob=b"stream.bin\x00")
    a("caller_d1", OP_INPUT, "block 1", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=w.data(1, pattern(41, 512)))
    a("caller_win", OP_BLOCKWIN, "the window the caller hands to fat.pi4")

    # =================================================================
    #  12. AN ERROR PACKET
    # =================================================================
    a("reset7", OP_RESET, "TftpInit")
    a("sink7", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read7", OP_READ, "a read of a file that is not there", a=SERVER,
      b=OUR_TID, blob=b"missing.img\x00")
    a("err_notfound", OP_INPUT, "ERROR 1, File not found", a=SERVER,
      b=SRV_TID, c=OUR_TID,
      blob=w.error(1, b"File not found: /srv/tftp/missing.img"))
    a("err_read", OP_SRVERR, "the server's code and its own words")
    a("err_text", OP_ERRTEXT, "the refusal, in English")

    a("reset8", OP_RESET, "TftpInit")
    a("sink8", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read8", OP_READ, "another read", a=SERVER, b=OUR_TID,
      blob=b"x.img\x00")
    a("err_diskfull", OP_INPUT, "ERROR 3, which IS worth retrying",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.error(3, b"Disk full"))
    a("err_read2", OP_SRVERR, "retrying this one could help")

    # An ERROR with no message at all, which is legal - the string is
    # just its terminator.
    a("reset9", OP_RESET, "TftpInit")
    a("sink9", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read9", OP_READ, "another read", a=SERVER, b=OUR_TID,
      blob=b"y.img\x00")
    a("err_empty", OP_INPUT, "ERROR 2 with an empty message", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.error(2, b""))
    a("err_read3", OP_SRVERR, "an empty message is legal")

    # =================================================================
    #  13. MALFORMED, ILLEGAL AND OVERSIZED
    # =================================================================
    a("reset10", OP_RESET, "TftpInit")
    a("sink10", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read10", OP_READ, "a read", a=SERVER, b=OUR_TID, blob=b"z.img\x00")
    a("runt1", OP_INPUT, "a one-byte datagram", a=SERVER, b=SRV_TID,
      c=OUR_TID, blob=b"\x00")
    a("runt_data", OP_INPUT, "a DATA packet with no block number",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=b"\x00\x03\x00")
    a("oversize", OP_INPUT, "a DATA packet with 513 bytes of payload",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.data(1, pattern(1, 513)))

    a("reset11", OP_RESET, "TftpInit")
    a("sink11", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read11", OP_READ, "a read", a=SERVER, b=OUR_TID, blob=b"z.img\x00")
    a("first_not_1", OP_INPUT, "the first DATA is block 2", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.data(2, pattern(2, 512)))

    a("reset12", OP_RESET, "TftpInit")
    a("sink12", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read12", OP_READ, "a read", a=SERVER, b=OUR_TID, blob=b"z.img\x00")
    a("oack", OP_INPUT, "an OACK for options that were never offered",
      a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.oack(b"blksize\x001428\x00"))

    a("reset13", OP_RESET, "TftpInit")
    a("sink13", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read13", OP_READ, "a read", a=SERVER, b=OUR_TID, blob=b"z.img\x00")
    a("got_rrq", OP_INPUT, "a READ REQUEST sent to a client", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.rrq(b"whatever"))

    a("reset14", OP_RESET, "TftpInit")
    a("sink14", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read14", OP_READ, "a read", a=SERVER, b=OUR_TID, blob=b"z.img\x00")
    a("got_ack", OP_INPUT, "an ACK during a read", a=SERVER, b=SRV_TID,
      c=OUR_TID, blob=w.ack(1))

    a("reset15", OP_RESET, "TftpInit")
    a("sink15", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read15", OP_READ, "a read", a=SERVER, b=OUR_TID, blob=b"z.img\x00")
    a("got_junk", OP_INPUT, "opcode 99", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=struct.pack(">H", 99) + b"nonsense")

    # =================================================================
    #  14. THE RETRANSMIT TIMER
    # =================================================================
    a("reset16", OP_RESET, "TftpInit")
    a("sink16", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("timeout16", OP_TIMEOUT, "a 1000 ms timeout and three retries",
      a=1000, b=3)
    a("read16", OP_READ, "a read nobody answers", a=SERVER, b=OUR_TID,
      blob=NAME + b"\x00")
    a("tick_arm", OP_TICK, "the first tick only arms the timer", a=10_000)
    a("tick_early", OP_TICK, "999 ms later - not yet", a=10_999)
    a("tick_fire1", OP_TICK, "1000 ms later - RETRANSMIT", a=11_000)
    a("tick_fire2", OP_TICK, "again", a=12_000)
    a("tick_fire3", OP_TICK, "and again - the third and last retry",
      a=13_000)
    a("tick_giveup", OP_TICK, "the fourth is one too many", a=14_000)
    a("giveup_state", OP_COUNTS2, "three retransmissions and a failure")

    # Progress restarts the clock.
    a("reset17", OP_RESET, "TftpInit")
    a("sink17", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("timeout17", OP_TIMEOUT, "a 1000 ms timeout", a=1000, b=3)
    a("read17", OP_READ, "a read", a=SERVER, b=OUR_TID, blob=NAME + b"\x00")
    a("p_arm", OP_TICK, "arm", a=0)
    a("p_fire", OP_TICK, "fire once", a=1000)
    a("p_data", OP_INPUT, "and then a block actually arrives", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.data(1, pattern(51, 512)))
    a("p_rearm", OP_TICK, "the tick after progress only re-arms", a=1500)
    a("p_quiet", OP_TICK, "and the old deadline has been forgotten",
      a=2200)
    a("p_counts", OP_COUNTS2, "the retry count went back to zero")
    a("p_fire2", OP_TICK, "1000 ms after the re-arm, an ACK is re-sent",
      a=2500)

    # =================================================================
    #  15. THE WRITE DIRECTION
    # =================================================================
    a("reset18", OP_RESET, "TftpInit")
    a("write_bad_src", OP_WRITE, "a write of 10 bytes from address 0",
      a=SERVER, b=OUR_TID, c=0, d=10, blob=b"out.bin\x00")
    a("write", OP_WRITE, "a write of exactly 1024 bytes", a=SERVER,
      b=OUR_TID, c=SRC, d=len(SRC_EXACT), blob=b"out.bin\x00")
    a("w_ack0", OP_INPUT, "ACK block 0 - the answer to a write request, "
      "and it carries the server's TID", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=w.ack(0))
    a("w_tid", OP_TID, "the TID was adopted from the ACK")
    a("w_ack0_dup", OP_INPUT, "ACK block 0 AGAIN - the duplicate ACK that "
      "RFC 1123 forbids answering", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=w.ack(0))
    a("w_ack1", OP_INPUT, "ACK block 1", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=w.ack(1))
    a("w_ack2", OP_INPUT, "ACK block 2 - the file is out, and the ZERO "
      "LENGTH final block must now be built", a=SERVER, b=SRV_TID,
      c=OUR_TID, blob=w.ack(2))
    a("w_ack3", OP_INPUT, "ACK block 3 - the empty one", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.ack(3))
    a("w_status", OP_COUNTS2, "the write is complete")

    # The ordinary, non-exact case, and a retransmission in the middle.
    a("reset19", OP_RESET, "TftpInit")
    a("write19", OP_WRITE, "a write of 700 bytes", a=SERVER, b=OUR_TID,
      c=SRC + 0x1000, d=len(SRC_SHORT), blob=b"odd.bin\x00")
    a("w2_ack0", OP_INPUT, "ACK 0", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=w.ack(0))
    a("w2_arm", OP_TICK, "arm", a=0)
    a("w2_retx", OP_TICK, "the data block is retransmitted BYTE-IDENTICALLY",
      a=99_000)
    a("w2_ack1", OP_INPUT, "ACK 1", a=SERVER, b=SRV_TID, c=OUR_TID,
      blob=w.ack(1))
    a("w2_ack2", OP_INPUT, "ACK 2 - the 188-byte block was short, so this "
      "ends it", a=SERVER, b=SRV_TID, c=OUR_TID, blob=w.ack(2))

    # A write that a server answers with DATA is nonsense.
    a("reset20", OP_RESET, "TftpInit")
    a("write20", OP_WRITE, "a write", a=SERVER, b=OUR_TID, c=SRC,
      d=len(SRC_EXACT), blob=b"out.bin\x00")
    a("w3_data", OP_INPUT, "DATA arriving during a write", a=SERVER,
      b=SRV_TID, c=OUR_TID, blob=w.data(1, pattern(1, 512)))

    # =================================================================
    #  16. CANCELLING
    # =================================================================
    a("reset21", OP_RESET, "TftpInit")
    a("sink21", OP_SINK, "TftpSetSinkNone", a=SINK_NONE)
    a("read21", OP_READ, "a read", a=SERVER, b=OUR_TID, blob=b"z.img\x00")
    a("cancel", OP_CANCEL, "TftpCancel")
    a("cancel_again", OP_CANCEL, "cancelling a cancelled transfer")

    # =================================================================
    #  17. EVERY SENTENCE, OUT OF THE RUNNING LIBRARY
    # =================================================================
    for code in range(0, 10):
        a("codetext%d" % code, OP_CODETEXT, "TftpCodeText(%d)" % code, a=code)
    for r in range(0, 9):
        a("intext%d" % r, OP_INTEXT, "TftpInputText(%d)" % r, a=r)
    a("statetext", OP_STATETEXT, "TftpStateText")

    return s, at


# =====================================================================
#  GRADING
# =====================================================================
def hexdiff(got: bytes, want: bytes) -> str:
    if len(got) != len(want):
        return ("length %d, wanted %d\n        got  %s\n        want %s"
                % (len(got), len(want), got.hex(), want.hex()))
    for i, (g, wnt) in enumerate(zip(got, want)):
        if g != wnt:
            return ("first difference at offset %d: got $%02X, wanted $%02X\n"
                    "        got  %s\n        want %s"
                    % (i, g, wnt, got.hex(), want.hex()))
    return ""


def check(res: list[Result], at: dict, spec: Spec, mem, fails: list[str]) -> None:
    w = Wire(spec)

    def R(name) -> Result:
        i = at[name]
        if i >= len(res):
            fails.append("%s: the harness never ran this record" % name)
            return Result(0, 0, 0, 0, 0, 0, b"", name)
        return res[i]

    def code(name, want, note=""):
        r = R(name)
        if r.r != want:
            fails.append("%s (%s): returned %d, wanted %d%s"
                         % (name, r.label, r.r, want,
                            "  [" + note + "]" if note else ""))

    def err(name, want):
        r = R(name)
        if r.err != want:
            fails.append("%s (%s): TftpError() is %d, wanted %d"
                         % (name, r.label, r.err, want))

    def nothing(name, note=""):
        r = R(name)
        if r.blob:
            fails.append("%s (%s): staged a %d-byte packet and should have "
                         "staged NOTHING.  %s" % (name, r.label, len(r.blob), note))

    def packet(name, want, ip=None, port=None, note=""):
        r = R(name)
        d = hexdiff(r.blob, want)
        if d:
            fails.append("%s (%s)%s: %s"
                         % (name, r.label, "  " + note if note else "", d))
        if ip is not None and r.e1 != ip:
            fails.append("%s (%s): the packet was addressed to %s, wanted %s"
                         % (name, r.label, dotted(r.e1), dotted(ip)))
        if port is not None and r.e2 != port:
            fails.append("%s (%s): the packet was addressed to port %d, "
                         "wanted %d" % (name, r.label, r.e2, port))

    def state(name, want):
        r = R(name)
        if r.e3 != want:
            fails.append("%s (%s): the state is %d, wanted %d"
                         % (name, r.label, r.e3, want))

    # ---- 1. refusals -------------------------------------------------
    code("read_no_dest", 0,
         "a library that guesses a load address can destroy a boot image")
    err("read_no_dest", E_NO_DEST)
    nothing("read_no_dest")
    for n in ("name_empty", "name_control", "name_high", "name_long"):
        code(n, 0)
        err(n, E_NAME)
        nothing(n)
    for n in ("port_zero", "port_high"):
        code(n, 0)
        err(n, E_PORT)
    for n in ("mem_null", "mem_zero", "timeout_zero", "retries_zero"):
        code(n, 0)
        err(n, E_ARG)

    # U-Boot's own band, 1024..4095 [v2025.01_net_tftp.c:924].
    code("port_seed0", 1024)
    code("port_seed1", 1025)
    code("port_wrap", 1024, "3072 % 3072 is 0, so this wraps to the base")
    p = R("port_big").r
    if not (1024 <= p <= 4095):
        fails.append("TftpSuggestPort(123456789) gave %d, outside U-Boot's "
                     "1024..4095 band" % p)

    # ---- 2. the read request, byte for byte -------------------------
    code("read", 1)
    packet("read", w.rrq(NAME), ip=SERVER, port=spec.port,
           note="opcode, filename, zero, mode, zero - and the ONLY packet in a "
           "transfer that goes to the well known port")
    r = R("read")
    if len(r.blob) != 2 + len(NAME) + 1 + len(spec.mode) + 1:
        fails.append("the read request is %d octets; it must be exactly "
                     "2 + %d + 1 + %d + 1" % (len(r.blob), len(NAME),
                                              len(spec.mode)))
    state("read", ST_RRQ)
    t = R("tid_before")
    if t.r != spec.port:
        fails.append("before any reply the server's TID must be %d and it is "
                     "%d" % (spec.port, t.r))
    if t.e2 != 0:
        fails.append("the TID is reported as locked before any reply arrived")

    # ---- 3. the TID is adopted from the first DATA ------------------
    code("data1", IN_DATA)
    packet("data1", w.ack(1), ip=SERVER, port=SRV_TID,
           note="THE ACK GOES TO THE SERVER'S NEW PORT, NOT TO 69.  This is the "
           "classic first-TFTP-client failure")
    state("data1", ST_READING)
    t = R("tid_after")
    if t.r != SRV_TID:
        fails.append("the server's TID was not adopted from the first DATA "
                     "packet: it is %d and the packet came from %d"
                     % (t.r, SRV_TID))
    if t.e2 != 1:
        fails.append("the TID is not reported as locked after the first block")
    st = R("status1")
    if (st.r, st.e1, st.e2, st.e3) != (1, 1, 0, 512):
        fails.append("after one block: blocks %d, block %d, wraps %d, bytes "
                     "%d - wanted 1, 1, 0, 512"
                     % (st.r, st.e1, st.e2, st.e3))

    code("data2", IN_DATA)
    packet("data2", w.ack(2), ip=SERVER, port=SRV_TID)

    # ---- 4. duplicates are answered with silence --------------------
    code("data2_dup", IN_DUP)
    nothing("data2_dup",
            "RE-ACKNOWLEDGING A DUPLICATE IS THE SORCERER'S APPRENTICE BUG.  "
            "rfc1123.txt:2589-2603, and v2025.01_net_tftp.c:597-604 breaks "
            "out before building an ACK for exactly this reason")
    code("data1_dup", IN_DUP)
    nothing("data1_dup")

    # ---- 5. a gap, complained about once ----------------------------
    code("gap5", IN_GAP)
    packet("gap5", w.ack(2), ip=SERVER, port=SRV_TID,
           note="a gap re-acknowledges the last GOOD block, which is 2, not the "
           "block that arrived")
    code("gap6", IN_DUP, "the second complaint about the same gap is "
         "suppressed - v2025.01_net_tftp.c:605-616, 'overwhelms the server'")
    nothing("gap6")
    c = R("counts_gap")
    if c.e2 != 2:
        fails.append("two blocks arrived out of order and the gap counter "
                     "says %d" % c.e2)

    # ---- 6. the stranger --------------------------------------------
    code("stranger", IN_STRANGER)
    packet("stranger", w.error(5, MSG_UNKNOWN_TID), ip=SERVER, port=SRV_TID2,
           note="THE ERROR GOES TO THE STRANGER, not to the server.  "
           "rfc1350.txt:239-246: 'An error packet should be sent to the "
           "source of the incorrect packet, while not disturbing the "
           "transfer'")
    st = R("stranger_status")
    if (st.r, st.e3) != (2, 1024):
        fails.append("the stranger disturbed the transfer: it is now at block "
                     "%d and %d bytes, and it was at block 2 and 1024 bytes"
                     % (st.r, st.e3))
    code("other_host", IN_IGNORED)
    nothing("other_host",
            "a packet from a forged source address must not make this board "
            "send anything anywhere")
    code("wrong_local", IN_IGNORED)
    nothing("wrong_local")
    code("data3", IN_DATA, "the transfer must have survived the stranger")
    packet("data3", w.ack(3), ip=SERVER, port=SRV_TID)

    # ---- 7. a short block ends it -----------------------------------
    code("data4_short", IN_LAST)
    packet("data4_short", w.ack(4), ip=SERVER, port=SRV_TID,
           note="THE FINAL ACK IS STILL STAGED AND MUST STILL BE SENT - "
           "rfc1350.txt:420-428")
    state("data4_short", ST_COMPLETE)
    st = R("status_done")
    if (st.r, st.e3) != (4, 3 * 512 + 100):
        fails.append("after the short block: %d blocks and %d bytes, wanted "
                     "4 and %d" % (st.r, st.e3, 3 * 512 + 100))
    code("after_done", E_STATE)
    err("after_done", E_STATE)

    # the bytes actually landed where they should have
    for blk, n in ((1, 512), (2, 512), (3, 512), (4, 100)):
        off = (blk - 1) * 512
        got = bytes(mem.get(DEST + off + i, 0) for i in range(n))
        want = pattern(blk, n)
        if got != want:
            fails.append("block %d did not land at offset %d: %s"
                         % (blk, off, hexdiff(got[:32], want[:32])))
    # ...and the stranger's payload did not.
    ghost = bytes(mem.get(DEST + 2 * 512 + i, 0) for i in range(32))
    if ghost == pattern(99, 32):
        fails.append("the stranger's payload was STORED.  A wrong transfer "
                     "identifier must not be able to write into the "
                     "destination")

    # ---- 8. the exact multiple of 512 -------------------------------
    code("ex_d1", IN_DATA)
    code("ex_d2", IN_DATA, "512 bytes is NOT short, so this does not end it")
    packet("ex_d2", w.ack(2), ip=SERVER, port=SRV_TID3)
    code("ex_d3", IN_LAST,
         "A ZERO-LENGTH DATA PACKET ENDS A TRANSFER.  rfc1350.txt:361-364 "
         "and :418-419.  A file that is an exact multiple of 512 has no "
         "short block, so this four-byte datagram is the only thing that "
         "can end it")
    packet("ex_d3", w.ack(3), ip=SERVER, port=SRV_TID3)
    state("ex_d3", ST_COMPLETE)
    st = R("ex_status")
    if (st.r, st.e3) != (3, 1024):
        fails.append("an exact multiple of 512: %d blocks and %d bytes, "
                     "wanted 3 and 1024" % (st.r, st.e3))
    for blk, src in ((1, 11), (2, 12)):
        off = (blk - 1) * 512
        got = bytes(mem.get(DEST + 0x10000 + off + i, 0) for i in range(32))
        if got != pattern(src, 32):
            fails.append("the exact-multiple file's block %d is wrong at "
                         "offset %d" % (blk, off))

    # ---- 9. the wraparound ------------------------------------------
    code("wrap_65535", IN_DATA)
    packet("wrap_65535", w.ack(65535), ip=SERVER, port=SRV_TID)
    st = R("wrap_65535_st")
    if (st.e1, st.e2, st.e3) != (65535, 0, 65535 * 512):
        fails.append("at block 65535: block %d, wraps %d, bytes %d - wanted "
                     "65535, 0, %d" % (st.e1, st.e2, st.e3, 65535 * 512))
    code("wrap_0", IN_DATA,
         "block 0 is the block AFTER 65535, not a restart and not a duplicate")
    packet("wrap_0", w.ack(0), ip=SERVER, port=SRV_TID)
    st = R("wrap_0_st")
    if (st.e1, st.e2) != (0, 1):
        fails.append("after the wrap: block %d, wraps %d - wanted 0 and 1"
                     % (st.e1, st.e2))
    if st.r != 65536:
        fails.append("TftpBlocksDone() is %d after the wrap and must be 65536"
                     % st.r)
    if st.e3 != 65536 * 512:
        fails.append("THE OFFSET IS NOT CONTIGUOUS ACROSS THE WRAP: %d bytes "
                     "after 65536 blocks, wanted %d.  A 16-bit block number "
                     "caps a naive client at 32 MB and this is the line that "
                     "lifts the cap" % (st.e3, 65536 * 512))
    code("wrap_1", IN_DATA)
    st = R("wrap_1_st")
    if (st.r, st.e3) != (65537, 65537 * 512):
        fails.append("the block after the wrap: %d blocks, %d bytes, wanted "
                     "65537 and %d" % (st.r, st.e3, 65537 * 512))
    code("wrap_dup0", IN_DUP,
         "one behind, across the wrap - modular arithmetic, not a comparison")
    nothing("wrap_dup0")
    code("wrap_dup65535", IN_DUP, "two behind, across the wrap")
    nothing("wrap_dup65535")
    code("wrap_gap", IN_GAP, "a gap is still a gap after a wrap")
    packet("wrap_gap", w.ack(1), ip=SERVER, port=SRV_TID)

    # ---- 10. the destination bounds ---------------------------------
    code("full_d1", IN_DATA)
    code("full_d2", E_DEST_FULL)
    err("full_d2", E_DEST_FULL)
    packet("full_d2", w.error(3, MSG_DISK_FULL), ip=SERVER, port=SRV_TID,
           note="the server is told, with the code RFC 1350 reserves for it "
           "(rfc1350.txt:518)")
    state("full_d2", ST_FAILED)
    st = R("full_after")
    if st.e3 != 512:
        fails.append("the refused block was counted anyway: %d bytes, wanted "
                     "512" % st.e3)
    tail = bytes(mem.get(DEST + 0x20000 + 512 + i, 0) for i in range(120))
    if tail != b"\x00" * 120:
        fails.append("THE REFUSED BLOCK WAS PARTLY WRITTEN.  %d bytes past "
                     "the 512 that fit are not zero.  The bounds check must "
                     "come BEFORE the copy, not after it"
                     % sum(1 for b in tail if b))

    # ---- 11. the caller sink ----------------------------------------
    code("caller_d1", IN_DATA)
    cw = R("caller_win")
    if cw.r != 512:
        fails.append("TftpBlockLen() is %d after a 512-byte block" % cw.r)
    if cw.blob != pattern(41, 512):
        fails.append("the caller's window does not hold the block that "
                     "arrived - and in this mode the library copies nothing, "
                     "so the window IS the caller's own receive buffer: %s"
                     % hexdiff(cw.blob[:32], pattern(41, 512)[:32]))

    # ---- 12. error packets ------------------------------------------
    code("err_notfound", IN_ERROR)
    nothing("err_notfound",
            "an ERROR packet is never acknowledged - rfc1350.txt:407-414")
    state("err_notfound", ST_FAILED)
    err("err_notfound", E_SERVER)
    e = R("err_read")
    if e.r != 1:
        fails.append("the server's error code came back as %d, wanted 1" % e.r)
    if e.blob != b"File not found: /srv/tftp/missing.img":
        fails.append("the server's own message was not kept intact: %r"
                     % e.blob)
    if e.e2 != 0:
        fails.append("file-not-found is worth retrying according to the "
                     "library, and U-Boot prints 'Not retrying...' for it "
                     "(v2025.01_net_tftp.c:682-687)")
    t = R("err_text")
    if b"SERVER" not in t.blob:
        fails.append("TftpErrorText() after a server error does not mention "
                     "the server: %r" % t.blob)
    e = R("err_read2")
    if (e.r, e.e2) != (3, 1):
        fails.append("a disk-full error: code %d, worth retrying %d - wanted "
                     "3 and 1" % (e.r, e.e2))
    e = R("err_read3")
    if (e.r, e.e1) != (2, 0):
        fails.append("an ERROR with an empty message: code %d, message length "
                     "%d - wanted 2 and 0" % (e.r, e.e1))

    # ---- 13. malformed ----------------------------------------------
    for n in ("runt1", "runt_data"):
        code(n, E_RUNT)
        err(n, E_RUNT)
        nothing(n)
    code("oversize", E_OVERSIZE)
    err("oversize", E_OVERSIZE)
    o = R("oversize")
    if not o.blob:
        fails.append("an oversized block should be refused WITH an error "
                     "packet, so the server stops sending them")
    code("first_not_1", E_FIRST_BLOCK)
    state("first_not_1", ST_FAILED)
    code("oack", E_OACK)
    packet("oack", w.error(8, R("oack").blob[4:-1]), ip=SERVER, port=SRV_TID,
           note="an OACK for options nobody offered gets error 8")
    if R("oack").blob[:4] != struct.pack(">HH", spec.opcodes["ERROR"], 8):
        fails.append("the OACK refusal is not an ERROR 8: %s"
                     % R("oack").blob[:4].hex())
    for n in ("got_rrq", "got_ack", "got_junk"):
        code(n, E_OPCODE)
        state(n, ST_FAILED)
        r = R(n)
        if r.blob[:4] != struct.pack(">HH", spec.opcodes["ERROR"], 4):
            fails.append("%s (%s): should be answered with ERROR 4, "
                         "'Illegal TFTP operation' (rfc1350.txt:519); got %s"
                         % (n, r.label, r.blob[:4].hex()))

    # every error packet we send must be a printable, NUL-terminated
    # sentence rather than a bare code
    for n in ("stranger", "full_d2", "oack", "got_rrq", "got_ack",
              "got_junk", "oversize", "cancel"):
        b = R(n).blob
        if len(b) < 6:
            fails.append("%s: the error packet has no message at all" % n)
            continue
        if b[-1] != 0:
            fails.append("%s: the error message is not NUL-terminated" % n)
        msg = b[4:-1]
        if not msg or not all(32 <= c <= 126 for c in msg):
            fails.append("%s: the error message is not a printable sentence: "
                         "%r" % (n, msg))
        if len(msg) < 20:
            fails.append("%s: the error message is %d characters, which is a "
                         "code wearing a sentence's clothes: %r"
                         % (n, len(msg), msg))

    # ---- 14. the retransmit timer -----------------------------------
    code("tick_arm", 0, "the first tick only starts the clock")
    nothing("tick_arm")
    code("tick_early", 0)
    nothing("tick_early")
    for n in ("tick_fire1", "tick_fire2", "tick_fire3"):
        code(n, 1)
        packet(n, w.rrq(NAME), ip=SERVER, port=spec.port,
               note="a retransmitted request must be BYTE-IDENTICAL to the first, "
               "so a server deduplicating requests can tell")
    code("tick_giveup", E_TIMEOUT)
    nothing("tick_giveup")
    state("tick_giveup", ST_FAILED)
    g = R("giveup_state")
    if (g.r, g.e2, g.e3) != (3, 4, ST_FAILED):
        fails.append("after giving up: %d retransmissions, %d tries, state "
                     "%d - wanted 3, 4 and %d" % (g.r, g.e2, g.e3, ST_FAILED))

    code("p_fire", 1)
    code("p_data", IN_DATA)
    code("p_rearm", 0, "progress disarms the timer so the next tick re-arms "
         "it from now - v2025.01_net_tftp.c:652-653")
    code("p_quiet", 0, "the deadline from before the block must have been "
         "forgotten")
    pc = R("p_counts")
    if pc.e2 != 0:
        fails.append("the retry count is %d after a block arrived; it must go "
                     "back to zero, or a long transfer over a slightly lossy "
                     "link fails while succeeding "
                     "(v2025.01_net_tftp.c:275)" % pc.e2)
    code("p_fire2", 1)
    packet("p_fire2", w.ack(1), ip=SERVER, port=SRV_TID,
           note="a read that times out re-acknowledges the last block it has")

    # ---- 15. the write direction ------------------------------------
    code("write_bad_src", 0)
    err("write_bad_src", E_SOURCE)
    code("write", 1)
    packet("write", w.wrq(b"out.bin"), ip=SERVER, port=spec.port)
    state("write", ST_WRQ)
    code("w_ack0", IN_ACKED)
    packet("w_ack0", w.data(1, SRC_EXACT[0:512]), ip=SERVER, port=SRV_TID,
           note="the first data block, addressed to the TID the ACK came from")
    t = R("w_tid")
    if t.r != SRV_TID:
        fails.append("a write must adopt the server's TID from ACK 0; it is "
                     "%d" % t.r)
    code("w_ack0_dup", IN_DUP)
    nothing("w_ack0_dup",
            "RFC 1123 4.2.3.1 is a MUST and it is worded as narrowly as this: "
            "'the sender ... must never resend the current DATA packet on "
            "receipt of a duplicate ACK'  [rfc1123.txt:2589-2603]")
    code("w_ack1", IN_ACKED)
    packet("w_ack1", w.data(2, SRC_EXACT[512:1024]), ip=SERVER, port=SRV_TID)
    code("w_ack2", IN_ACKED)
    packet("w_ack2", w.data(3, b""), ip=SERVER, port=SRV_TID,
           note="A ZERO-LENGTH FINAL DATA PACKET.  The file is 1024 bytes, an "
           "exact multiple of 512, so there is no short block to end on and "
           "this four-byte datagram is the only thing that can")
    if len(R("w_ack2").blob) != 4:
        fails.append("the final data packet of an exact multiple must be four "
                     "octets and is %d" % len(R("w_ack2").blob))
    code("w_ack3", IN_SENT)
    nothing("w_ack3")
    ws = R("w_status")
    if ws.e3 != ST_COMPLETE:
        fails.append("the write did not complete: state %d" % ws.e3)

    code("w2_ack0", IN_ACKED)
    packet("w2_ack0", w.data(1, SRC_SHORT[0:512]), ip=SERVER, port=SRV_TID)
    code("w2_retx", 1)
    packet("w2_retx", w.data(1, SRC_SHORT[0:512]), ip=SERVER, port=SRV_TID,
           note="a retransmitted data block must be byte-identical")
    code("w2_ack1", IN_ACKED)
    packet("w2_ack1", w.data(2, SRC_SHORT[512:700]), ip=SERVER, port=SRV_TID,
           note="188 bytes, which is short, so it is the last")
    code("w2_ack2", IN_SENT)
    nothing("w2_ack2")

    code("w3_data", E_OPCODE)

    # ---- 16. cancelling ----------------------------------------------
    code("cancel", 1)
    state("cancel", ST_FAILED)
    if R("cancel").blob[:4] != struct.pack(">HH", spec.opcodes["ERROR"], 0):
        fails.append("TftpCancel must send an ERROR 0 to the server; it sent "
                     "%s" % R("cancel").blob[:4].hex())
    code("cancel_again", 0)
    err("cancel_again", E_STATE)

    # ---- 17. every sentence is a different sentence ------------------
    seen: dict[bytes, str] = {}
    for c in range(0, 10):
        t = R("codetext%d" % c)
        if not t.blob:
            fails.append("TftpCodeText(%d) is empty" % c)
            continue
        if len(t.blob) < 25:
            fails.append("TftpCodeText(%d) is %d characters, which is not "
                         "English: %r" % (c, len(t.blob), t.blob))
        if t.blob in seen:
            fails.append("TftpCodeText(%d) and %s give the same sentence, so "
                         "one of the nine error codes is being reported as "
                         "another" % (c, seen[t.blob]))
        seen[t.blob] = "TftpCodeText(%d)" % c
    # ...and the eight the RFC actually defines must be recognisably about
    # what the RFC says they are about.
    KEY = {1: b"no such file", 2: b"access", 3: b"room", 5: b"transfer identifier",
           6: b"already exists", 7: b"user"}
    for c, needle in KEY.items():
        t = R("codetext%d" % c).blob.lower()
        if needle not in t:
            fails.append("TftpCodeText(%d) should be about %r - rfc1350.txt "
                         "calls it %r - and says %r"
                         % (c, needle.decode(), spec.errors[c], t))
    seen.clear()
    for r in range(0, 9):
        t = R("intext%d" % r)
        if not t.blob:
            fails.append("TftpInputText(%d) is empty" % r)
            continue
        if t.blob in seen:
            fails.append("TftpInputText(%d) and %s give the same sentence"
                         % (r, seen[t.blob]))
        seen[t.blob] = "TftpInputText(%d)" % r


# =====================================================================
#  MUTATIONS
# =====================================================================
# Each is a real defect somebody could plausibly write, or plausibly
# tidy INTO the file while making it simpler.  Every one must turn the
# gate red.
MUTATIONS = [
    # ---- byte order.  The classic, and the one that produces a
    # plausible wrong number rather than a crash: block 1 read the wrong
    # way round is block 256.
    ("the block number and opcode written LITTLE-endian",
     "Procedure tftp_PutWord(v.i)\n"
     "  tftp_PutByte((v >> 8) & $FF)\n"
     "  tftp_PutByte(v & $FF)\n"
     "EndProcedure",
     "Procedure tftp_PutWord(v.i)\n"
     "  tftp_PutByte(v & $FF)\n"
     "  tftp_PutByte((v >> 8) & $FF)\n"
     "EndProcedure"),

    ("the block number and opcode READ little-endian",
     "  ProcedureReturn (PeekA(*p) << 8) | PeekA(*p + 1)",
     "  ProcedureReturn PeekA(*p) | (PeekA(*p + 1) << 8)"),

    # ---- the TID rule, which is the classic first-client failure ----
    ("the server's transfer identifier never adopted - everything still "
     "addressed to port 69",
     "    tftp_serverPort = fromPort\n"
     "    tftp_tidLocked = 1\n"
     "    tftp_state = #TFTP_READING",
     "    tftp_tidLocked = 1\n"
     "    tftp_state = #TFTP_READING"),

    ("a packet from the wrong transfer identifier accepted as if it "
     "belonged to the transfer",
     "  If tftp_tidLocked = 1 And fromPort <> tftp_serverPort\n"
     "    tftp_strangerCount = tftp_strangerCount + 1",
     "  If tftp_tidLocked = 2 And fromPort <> tftp_serverPort\n"
     "    tftp_strangerCount = tftp_strangerCount + 1"),

    # ---- the Sorcerer's Apprentice, both halves ---------------------
    ("a duplicate DATA packet acknowledged again - the Sorcerer's "
     "Apprentice bug, receiving side",
     "      tftp_dupCount = tftp_dupCount + 1\n"
     "      ProcedureReturn #TFTP_IN_DUP\n"
     "    EndIf\n"
     "\n"
     "    ; A GAP.",
     "      tftp_dupCount = tftp_dupCount + 1\n"
     "      tftp_BuildAck(tftp_block)\n"
     "      ProcedureReturn #TFTP_IN_DUP\n"
     "    EndIf\n"
     "\n"
     "    ; A GAP."),

    ("a duplicate ACK answered by resending the current DATA packet - the "
     "Sorcerer's Apprentice bug, sending side, which RFC 1123 makes a MUST",
     "    tftp_dupCount = tftp_dupCount + 1\n"
     "    ProcedureReturn #TFTP_IN_DUP\n"
     "  EndIf\n"
     "\n"
     "  If tftp_finalSent = 1",
     "    tftp_dupCount = tftp_dupCount + 1\n"
     "    tftp_RetransmitData()\n"
     "    ProcedureReturn #TFTP_IN_DUP\n"
     "  EndIf\n"
     "\n"
     "  If tftp_finalSent = 1"),

    ("the rate limit on complaining about a gap removed, so a whole lost "
     "window produces a whole window of complaints",
     "    If tftp_haveNacked = 1 And tftp_lastNack = tftp_block\n"
     "      ProcedureReturn #TFTP_IN_DUP\n"
     "    EndIf",
     "    ; the rate limit, removed by a mutation"),

    # ---- what ends a transfer ---------------------------------------
    ("a short block no longer ends the transfer - only a zero-length one "
     "does",
     "  If length < #TFTP_BLOCK\n"
     "    tftp_state = #TFTP_COMPLETE\n"
     "    ProcedureReturn #TFTP_IN_LAST\n"
     "  EndIf\n"
     "  ProcedureReturn #TFTP_IN_DATA",
     "  If length = 0\n"
     "    tftp_state = #TFTP_COMPLETE\n"
     "    ProcedureReturn #TFTP_IN_LAST\n"
     "  EndIf\n"
     "  ProcedureReturn #TFTP_IN_DATA"),

    ("a ZERO-LENGTH final block not recognised - the exact-multiple-of-512 "
     "trap, receiving",
     "  If length < #TFTP_BLOCK\n"
     "    tftp_state = #TFTP_COMPLETE\n"
     "    ProcedureReturn #TFTP_IN_LAST\n"
     "  EndIf\n"
     "  ProcedureReturn #TFTP_IN_DATA",
     "  If length > 0 And length < #TFTP_BLOCK\n"
     "    tftp_state = #TFTP_COMPLETE\n"
     "    ProcedureReturn #TFTP_IN_LAST\n"
     "  EndIf\n"
     "  ProcedureReturn #TFTP_IN_DATA"),

    ("a write that ends when the source runs out instead of on a short "
     "block - the exact-multiple-of-512 trap, sending",
     "  If length < #TFTP_BLOCK\n"
     "    tftp_finalSent = 1\n"
     "  EndIf",
     "  If length < #TFTP_BLOCK And length > 0\n"
     "    tftp_finalSent = 1\n"
     "  EndIf"),

    # ---- the wraparound ---------------------------------------------
    ("the block number wrap not counted, so a transfer silently restarts "
     "at offset zero every 32 MB",
     "  If blk = 0\n"
     "    tftp_wraps = tftp_wraps + 1\n"
     "  EndIf",
     "  ; the wrap count, removed by a mutation"),

    ("old and new decided by comparing block numbers instead of modulo "
     "65536, which is correct until the wrap",
     "    ahead = (blk - expected) & #TFTP_BLOCK_MASK\n"
     "    If ahead >= #TFTP_HALF_SEQUENCE",
     "    ahead = (blk - expected) & #TFTP_BLOCK_MASK\n"
     "    If blk < expected"),

    # ---- the destination --------------------------------------------
    ("the destination bounds check removed - a file larger than the window "
     "writes past the end of it",
     "    If offset + length > tftp_destCap\n"
     "      tftp_err = #TFTP_E_DEST_FULL\n"
     "      ProcedureReturn 0\n"
     "    EndIf",
     "    ; the bounds check, removed by a mutation"),

    # ---- the timer, which a reader is most likely to delete as noise --
    ("the retransmission removed from TftpTick - a gate that only tested "
     "the happy path would still be green",
     "  If tftp_state = #TFTP_RRQ_SENT\n"
     "    tftp_BuildRequest(#TFTP_OP_RRQ)\n"
     "    ProcedureReturn 1\n"
     "  EndIf",
     "  If tftp_state = #TFTP_RRQ_SENT\n"
     "    ProcedureReturn 0\n"
     "  EndIf"),

    ("progress no longer restarts the clock, so a long transfer over a "
     "lossy link fails while succeeding",
     "Procedure tftp_Progress()\n"
     "  tftp_tries = 0\n"
     "  tftp_armed = 0\n"
     "EndProcedure",
     "Procedure tftp_Progress()\n"
     "EndProcedure"),

    # ---- the request itself ------------------------------------------
    ("the mode spelled with the wrong letter",
     "#TFTP_CH_o = 111          ; the letter o, lower case",
     "#TFTP_CH_o = 110          ; the letter o, lower case"),

    ("the filename's terminating zero left out of the request",
     "  tftp_PutByte(#TFTP_CH_NUL)\n"
     "  tftp_PutOctetMode()",
     "  tftp_PutOctetMode()"),

    ("a read request built with the write opcode",
     "  tftp_state = #TFTP_RRQ_SENT\n"
     "  tftp_BuildRequest(#TFTP_OP_RRQ)",
     "  tftp_state = #TFTP_RRQ_SENT\n"
     "  tftp_BuildRequest(#TFTP_OP_WRQ)"),

    ("the request sent to the wrong well known port",
     "#TFTP_WELL_KNOWN_PORT = 69",
     "#TFTP_WELL_KNOWN_PORT = 68"),

    # ---- errors ------------------------------------------------------
    ("an ERROR packet from the server acknowledged, which RFC 1350 says "
     "must never happen",
     "  tftp_err = #TFTP_E_SERVER\n"
     "  tftp_state = #TFTP_FAILED\n"
     "  ProcedureReturn #TFTP_IN_ERROR",
     "  tftp_err = #TFTP_E_SERVER\n"
     "  tftp_state = #TFTP_FAILED\n"
     "  tftp_BuildAck(tftp_block)\n"
     "  ProcedureReturn #TFTP_IN_ERROR"),

    ("the wrong-identifier error addressed to the server instead of to the "
     "stranger, which tells the server ITS transfer failed",
     "    tftp_BuildError(fromIp, fromPort, #TFTP_ERR_UNKNOWN_TID,",
     "    tftp_BuildError(tftp_serverIp, tftp_serverPort, #TFTP_ERR_UNKNOWN_TID,"),
]


def one_run(lib_include: str, harness: pathlib.Path, img: pathlib.Path,
            script: Script):
    write_harness(lib_include, harness)
    build(harness, img)
    preload = {SRC: SRC_EXACT, SRC + 0x1000: SRC_SHORT}
    cpu, uart, steps = run(img, script.finish(), preload)
    res = read_results(cpu.memory, script.labels)
    return cpu, res, uart, steps


MUT_AT: dict = {}
MUT_SPEC: list = []


def mutate_run(name, old, new, script: Script) -> bool:
    """Returns True if the gate went red, which is what we want."""
    WORK.mkdir(exist_ok=True)
    src = LIB.read_text(encoding="utf-8", errors="replace")
    if src.count(old) != 1:
        print("   SKIPPED - the anchor text appears %d times in tftp.pi4, "
              "not once" % src.count(old))
        return False
    (WORK / "tftp_mut.pi4").write_text(src.replace(old, new), encoding="utf-8")
    try:
        cpu, res, _uart, _steps = one_run("_work/tftp_mut.pi4",
                                          WORK / "tftpharness_mut.pi4",
                                          WORK / "tftpcheck_mut.img", script)
    except SystemExit as e:
        print("   (the harness refused it: %s)" % str(e).splitlines()[0][:90])
        return True
    fails: list[str] = []
    # The three-readings check reads the mutant's own constants, so a
    # mutation of a constant is caught there as well as in the run.
    mut_lib = {}
    text = (WORK / "tftp_mut.pi4").read_text(encoding="utf-8")
    for m in re.finditer(r"^#(TFTP_[A-Za-z0-9_]+)\s*=\s*(\$?[0-9A-Fa-f]+)\s*(?:;.*)?$",
                         text, re.M):
        raw = m.group(2)
        mut_lib[m.group(1)] = int(raw[1:], 16) if raw.startswith("$") else int(raw)
    confirm_three_readings(MUT_SPEC[0], mut_lib, fails)
    check(res, MUT_AT, MUT_SPEC[0], cpu.memory, fails)
    return bool(fails)


# =====================================================================
def resolve_compiler(requested):
    """Resolve the PureMetal compiler the way tools/build.py does."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build as anvil_build  # noqa: E402
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
    ap.add_argument("--mutate", action="store_true",
                    help="prove the gate can fail, by breaking the library")
    ap.add_argument("--dump", action="store_true",
                    help="print every packet the library staged")
    args = ap.parse_args()
    globals()["PMFC"] = resolve_compiler(args.compiler)
    apply_target(globals(), args.target)
    # A GATE THAT DOES NOT SAY WHICH BOARD IT GRADED IS A RESULT
    # THAT CAN BE FILED AGAINST THE WRONG ONE.  Printed before any
    # work, so it is at the top of the transcript even on a failure.
    print("[gate] target %s - %s, image at $%08X, stack $%08X"
          % (TARGET_NAME, TARGET_WHAT, LOAD, STACK))

    spec = Spec()
    print("what this gate READ rather than typed:")
    print("   the five opcodes            %s   %s"
          % (spec.cite["opcodes"], spec.opcodes))
    print("   the eight error codes       %s" % spec.cite["errors"])
    print("   the mode string %-11r %s" % (spec.mode.decode(), spec.cite["mode"]))
    print("   the well known port %-7d %s" % (spec.port, spec.cite["port"]))
    print("   the block size %-12d %s" % (spec.block, spec.cite["block"]))
    print("   a short block, 0..%-9d%s" % (spec.short_max, spec.cite["short"]))
    print("   a datagram under %-10d%s" % (spec.datagram_max, spec.cite["datagram"]))
    print("   the Sorcerer's Apprentice   %s" % spec.cite.get("sas", "?"))
    print("   the block number wraps at %-3d %s" % (spec.sequence, spec.cite["sequence"]))
    print("   the OACK opcode %-11d %s" % (spec.oack, spec.cite["oack"]))
    if spec.uboot:
        print("   the second reading of all of it: v2025.01_net_tftp.c:26-40,117-120")
    else:
        print("   no U-Boot second reading (its source is not in this tree)")
    print()

    lib = library_constants()
    fails: list[str] = []
    confirm_three_readings(spec, lib, fails)
    if fails:
        print("a64_tftp_check: FAIL - the RFCs, U-Boot (when present) and the "
              "library disagree before a single byte has been run")
        for f in fails:
            print("   " + f)
        return 1
    print("the RFCs%s and tftp.pi4 agree on every opcode, every error code,"
          % (", U-Boot" if spec.uboot else ""))
    print("the port, the block size, the block number wrap and the datagram "
          "ceiling.")
    print()

    script, at = build_script(spec)
    MUT_AT.clear()
    MUT_AT.update(at)
    MUT_SPEC.clear()
    MUT_SPEC.append(spec)

    cpu, res, uart, steps = one_run("RaspberryPi4/Lib/tftp.pi4",
                                    WORK / "tftpharness.pi4",
                                    WORK / "tftpcheck.img", script)

    print("%d script records, %d results, %d instructions, console %r"
          % (len(script.labels), len(res), steps, uart.decode("latin-1")))
    print()

    if args.dump:
        for r in res:
            print("  %-26s r=%-6d err=%-6d -> %s:%-6d %s"
                  % (r.label[:26], r.r, r.err, dotted(r.e1), r.e2,
                     r.blob.hex()))
        print()

    for name in ("read", "data1", "stranger", "ex_d3", "w_ack2", "full_d2"):
        r = res[at[name]]
        print("  %-11s %-44s -> %s:%d, %d octets"
              % (name, r.label[:44], dotted(r.e1), r.e2, len(r.blob)))
        if r.blob:
            for off in range(0, min(len(r.blob), 64), 16):
                print("      %04X  %s" % (off, r.blob[off:off + 16].hex(" ")))
    print()

    fails = []
    check(res, at, spec, cpu.memory, fails)

    if fails:
        print("a64_tftp_check: FAIL")
        for f in fails:
            print("   " + f)
        return 1
    print("a64_tftp_check: PASS - %d cases, every packet byte-exact and every "
          "destination checked" % len(script.labels))

    # The probe is BUILT here, not run.  Running it needs the GENET
    # register model and the whole of net.pi4 underneath, and both of
    # those have their own gates; duplicating them here would be two
    # more models to keep in step.  Building it still catches the thing
    # that actually goes wrong with a probe - that somebody changed an
    # API in tftp.pi4 and did not change its caller.
    if PROBE.exists():
        build(PROBE, WORK / "tftpprobe.img")
        head = PROBE.read_text(encoding="utf-8", errors="replace")[:4000]
        need = ("--load-addr 0x400000", "--stack-addr 0x3000000",
                "--entry-returns")
        missing = [n for n in need if n not in head]
        if missing:
            print("a64_tftp_check: FAIL - pi4TftpProbe.pi4's header does not "
                  "document %s in its build line" % ", ".join(missing))
            return 1
        print("           pi4TftpProbe.pi4 builds, and its header documents "
              "its own build line")
    else:
        print("           pi4TftpProbe.pi4 is not there yet")

    if args.mutate:
        print()
        print("--mutate: breaking the library on purpose; each must go RED")
        bad = 0
        for name, old, new in MUTATIONS:
            print("  * %s" % name)
            if mutate_run(name, old, new, script):
                print("    RED, as required")
            else:
                print("    *** STILL GREEN - the gate does not catch this ***")
                bad += 1
        for leftover in ("tftp_mut.pi4", "tftpharness_mut.pi4",
                         "tftpcheck_mut.img", "tftpcheck_mut.img.dbg",
                         "tftpcheck_mut.img.sym", "tftpcheck_mut.img.sym.meta",
                         "tftpcheck_mut.img.asm"):
            p = WORK / leftover
            if p.exists():
                p.unlink()
        if bad:
            return 1
        print("  all %d mutations caught" % len(MUTATIONS))

    return 0


if __name__ == "__main__":
    sys.exit(main())
