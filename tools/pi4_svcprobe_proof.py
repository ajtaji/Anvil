#!/usr/bin/env python3
r"""pi4_svcprobe_proof.py - run the payload ABI's board proof and read the verdict.

    python tools/pi4_svcprobe_proof.py --console-ip 192.168.1.30 \
           --probe _work/svcprobe/svcprobe.img.pmf \
           --major _work/svcprobe/svcmaj.img.pmf \
           --both  _work/svcprobe/svcboth.pmf

The three containers come from tools/pi4_svcprobe_negcontrols.py.

WHAT THIS IS FOR, AND WHY IT IS NOT A PERSON READING A HEX DUMP

The reference payload's whole verdict is fifty-six 64-bit words at a
stated address, and the proof is not "the numbers looked right" - it is
each named word against what the ABI says it must be.  Fifty-six words
read by eye at the end of a bench session is exactly how a wrong verdict
gets recorded as a right one.  So the dump is parsed and every word is
judged here, by name, with the expectation beside it.

THE BOARD IS THE INSTRUMENT AND THE CONSOLE IS THE TRANSCRIPT.  Every
command and every reply is printed as it happens.  Nothing below infers a
result it did not read back off the board.

HOW A CONTAINER REACHES THE BOARD.  The same way tools/board_run.py sends
one, and through its own helpers: ask the running monitor where to stage
(`map`), arm a one-shot listener (`net recv`), stream the file, and require
the board's own length and SHA-256 of the MEMORY it wrote before anything
is booted (`boot mem`).  This tool never replaces the monitor on the card;
it runs against whatever monitor is up, and a monitor too old to know the
payload ABI simply refuses the containers and says so.

THE THREE PARTS

  1. the reference payload           every judged word of the result block
  2. the major-mismatch payload      built needing ABI 2.0; must refuse
                                     without calling a slot
  3. the both-flags container        bit 1 set beside bit 2, by hand; the
                                     ninth guard must refuse it unplaced

The guarded setting (boot.fails) is refused inside part 1.

The re-entrancy witness is deliberately NOT here.  It needs a slot entered
twice at once, and this ABI masks interrupts at entry and has no callback
for a second entry to arrive through, so the only honest place to run it is
the emulator: part F of tools/a64/a64_abi_check.py.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import struct
import sys
import time
import zlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board_run  # noqa: E402

RESULT = 0x01400000
SENTENCE = 0x01401000
WORDS = 56

SVC_OK = 0
SVC_ENOSYS = -100
SVC_ENOCAP = -101
SVC_EPERM = -106
SVC_EABI = -109
SVCP_MAGIC = 0x50435653          # 'SVCP'
SVCP_DONE = 0x454E4F44           # 'DONE'

# 'NOTWRIT!', the value the probe stamps into all 56 words before its run
# starts.  A word that still says this was NEVER WRITTEN by the run, and
# that is a different fault from a wrong answer - uninitialised DRAM reads as
# a number and a number reads as an answer; only the payload can say it
# never answered, and this constant is it saying so.
SVCP_UNSET = 0x2154495257544F4E
SVC_MAGIC = 0x53564E41           # 'ANVS'
# Anvil main publishes 1.2 (Anvil/Hal/abi_version.pbi).  The reference probe
# is built needing 1.0 and the major-mismatch control needing 2.0.
ABI_MAJOR, ABI_MINOR, SLOT_COUNT = 1, 2, 184
PROBE_NEED_MINOR = 0

# The result block, word by word, from pi4SvcProbe.pi4's own header.
# RESTATED here rather than parsed: a reader that took its map from the
# thing it is reading would agree with a wrong one.
R = {
    "magic": 0, "table": 1, "hdr_magic": 2, "hdr_major": 3, "hdr_minor": 4,
    "hdr_count": 5, "need_major": 6, "need_minor": 7, "abi_rc": 8,
    "abi_text": 9, "slot_major": 10, "slot_minor": 11, "board_id": 12,
    "name_ptr": 13, "mmu": 14, "ticks0": 15, "cap0": 16,
    "scr_w": 30, "scr_h": 31, "tier": 32, "text_h": 33, "frame_rc": 34,
    "frame_cost": 35, "text_width": 36, "gpio_count": 37, "gpio_mode": 38,
    "gpio_level": 39, "gpio_pull": 40, "veh_up": 41, "veh_loss": 42,
    "errtext": 43, "detail": 44, "perm_rc": 45, "append_rc": 46,
    "storage_up": 47, "file_rc": 48, "null_slots": 49, "unimpl_rc": 50,
    "clock_prov": 51, "netup_rc": 52, "ticks1": 53, "fails": 54, "done": 55,
}

CAPS = ["storage", "net", "gpio", "i2c", "mmc", "usb", "boot_el1", "touch",
        "gnss", "vehlink", "spi", "uart", "rtc", "console"]


# ---------------------------------------------------------------------
#  Reading memory off the board
# ---------------------------------------------------------------------
def read_memory(con: board_run.NetConsole, addr: int, length: int) -> bytes:
    """`memory <addr> <len>` in chunks, parsed back into bytes.

    THE LENGTH IS CHECKED, not just the hex.  A dump that came back short -
    datagrams dropped, a reply still in flight from an earlier command -
    would parse perfectly and mean nothing, so a short read is refused.
    """
    out = bytearray()
    while len(out) < length:
        chunk = min(0x100, length - len(out))
        text = con.command("memory %X %s" % (addr + len(out),
                                             board_run.monitor_hex_count(chunk)), 30)
        blob = board_run.parse_dump(text)
        if len(blob) != chunk:
            raise SystemExit(
                "the board's dump of %d bytes at %08X came back with %d bytes. "
                "Nothing is judged from a partial read: run it again, and if it "
                "keeps happening the console is dropping datagrams rather than "
                "the memory being wrong." % (chunk, addr + len(out), len(blob)))
        out.extend(blob)
    return bytes(out)


def words(blob: bytes, n: int) -> list[int]:
    return [struct.unpack_from("<Q", blob, i * 8)[0] for i in range(n)]


def signed(v: int) -> int:
    return v - (1 << 64) if v >> 63 else v


def cstring(con, addr: int, limit: int = 512) -> str:
    blob = read_memory(con, addr, limit)
    end = blob.find(b"\x00")
    return blob[:end if end >= 0 else limit].decode("latin-1")


# ---------------------------------------------------------------------
#  Staging and booting
# ---------------------------------------------------------------------
def report_file(path: pathlib.Path) -> None:
    b = path.read_bytes()
    print("    %-22s %9d bytes  crc32 %08X" % (path.name, len(b), zlib.crc32(b) & 0xFFFFFFFF))
    print("    %-22s sha256 %s" % ("", hashlib.sha256(b).hexdigest()))


def stage(con: board_run.NetConsole, board_ip: str, port: int, path: pathlib.Path) -> int:
    """Send one container and prove it landed.  Returns the staging address."""
    data = path.read_bytes()
    want = hashlib.sha256(data).hexdigest()
    addr = board_run.parse_stage_address(con.command("map", 12))
    if addr is None:
        raise SystemExit("The board did not say where to stage a file (`map`), so "
                         "nothing was sent.")
    con.settle(quiet=0.3, cap=3.0)
    con.send("net recv %d %X" % (port, addr))
    listen = con.read_until(["for ONE connection", "!!", "? net"], 15)
    if "for ONE connection" not in listen:
        raise SystemExit("The board did not arm a listener, so %s was not sent. "
                         "It said:\n%s" % (path.name, listen))
    board_run.stream_file(board_ip, port, data)
    verdict = listen + con.read_until(["sha256 ", "!!"], 30.0 + len(data) / 40000.0)
    got_len, _ms, got_sha = board_run.parse_recv_verdict(verdict)
    if got_len != len(data) or got_sha != want:
        raise SystemExit(
            "The upload of %s did not verify, so nothing was booted. The board "
            "hashes the memory it received and this tool hashes the file; they "
            "disagreed (host %d bytes %s, board %s bytes %s), and a payload is "
            "never entered on a digest that does not match."
            % (path.name, len(data), want, got_len, got_sha))
    print("    staged %s at %08X, %d bytes, digest verified on the board"
          % (path.name, addr, len(data)))
    return addr


def boot(con: board_run.NetConsole, addr: int, timeout: float) -> str:
    con.settle(quiet=0.3, cap=3.0)
    con.send("boot mem %X" % addr)
    return con.read_until(["Its x0 register held", "!!", "? boot"], timeout)


# ---------------------------------------------------------------------
#  The judgements
# ---------------------------------------------------------------------
def judge_reference(w: list[int]) -> list[str]:
    bad: list[str] = []

    def want(key: str, expect: int, why: str) -> None:
        if w[R[key]] == SVCP_UNSET:
            bad.append("%s was NEVER WRITTEN by the payload - the word still holds "
                       "the 'NOTWRIT!' stamp the run starts with, so no call was "
                       "made and there is no answer to judge. This is a defect in "
                       "the payload's control flow, not in the monitor's %s" % (key, why))
            return
        got = signed(w[R[key]])
        if got != expect:
            bad.append("%s is %d, expected %d - %s" % (key, got, expect, why))

    if w[R["magic"]] != SVCP_MAGIC:
        bad.append("the block does not start with 'SVCP', so this is not the "
                   "probe's result block - check the address, not the ABI")
        return bad
    if w[R["done"]] != SVCP_DONE:
        bad.append("the block is not stamped 'DONE', so the payload stopped part "
                   "way through and every word below it is from an incomplete run")
    if w[R["table"]] == 0:
        bad.append("the payload was entered with x0 = 0, so the service table was "
                   "never handed over. Check that the container really has bit 2 set")
    want("hdr_magic", SVC_MAGIC, "the table header's magic word")
    want("hdr_major", ABI_MAJOR, "the table header's major")
    want("hdr_minor", ABI_MINOR, "the table header's minor")
    want("hdr_count", SLOT_COUNT, "the table header's entry_count")
    want("slot_major", ABI_MAJOR, "slot 0, read through a CALL")
    want("slot_minor", ABI_MINOR, "slot 1, read through a CALL")
    want("null_slots", 0, "every slot must point at something")
    want("abi_rc", SVC_OK, "a matching version must not refuse")
    want("veh_up", SVC_ENOCAP, "the vehicle-link group is absent on this board, "
                               "so it refuses with ENOCAP")
    want("veh_loss", SVC_ENOCAP, "the same, from a second slot in the group")
    want("perm_rc", SVC_EPERM, "boot.fails must be refused on purpose")
    want("unimpl_rc", SVC_ENOSYS, "a reserved slot answers ENOSYS, not a fault")
    want("append_rc", SVC_ENOSYS, "file append is not implemented yet and must "
                                  "say so rather than fall back")
    for key in ("errtext", "ticks0", "ticks1", "fails"):
        if w[R[key]] == SVCP_UNSET:
            bad.append("%s was NEVER WRITTEN by the payload - it still holds the "
                       "'NOTWRIT!' stamp, so the run did not reach the line that "
                       "records it" % key)
    if w[R["errtext"]] == 0:
        bad.append("SvcErrText returned 0, so the payload would have had nothing "
                   "to draw at the moment it most needed something")
    if (w[R["ticks0"]] != SVCP_UNSET and w[R["ticks1"]] != SVCP_UNSET
            and signed(w[R["ticks1"]]) < signed(w[R["ticks0"]])):
        bad.append("uptime went backwards across the run")
    if w[R["fails"]] != SVCP_UNSET and signed(w[R["fails"]]) != 0:
        bad.append("the payload counted %d failure(s) of its own - x0 is the "
                   "verdict and it is not zero" % signed(w[R["fails"]]))
    return bad


def judge_refusal(w: list[int], sentence: str, want_major: int,
                  want_minor: int) -> list[str]:
    bad: list[str] = []
    if w[R["magic"]] != SVCP_MAGIC:
        bad.append("this is not the probe's result block")
        return bad
    if signed(w[R["abi_rc"]]) != SVC_EABI:
        bad.append("the payload did not refuse: abi_rc is %d, expected %d"
                   % (signed(w[R["abi_rc"]]), SVC_EABI))
    if signed(w[R["need_major"]]) != want_major:
        bad.append("the payload says it needs major %d, expected %d"
                   % (signed(w[R["need_major"]]), want_major))
    if signed(w[R["fails"]]) == 0:
        bad.append("the refusal came back with a failure count of 0, so the "
                   "monitor's own last line would have read as a pass")
    here = "%d.%d" % (ABI_MAJOR, ABI_MINOR)
    theirs = "%d.%d" % (want_major, want_minor)
    for token in (here, theirs, "-109", "SVC_EABI"):
        if token not in sentence:
            bad.append("the refusal does not say %r. It says: %r" % (token, sentence[:200]))
    # A MAJOR MISMATCH CALLS NO SLOT, so the words only slots can fill must
    # still hold the stamp.
    if w[R["slot_major"]] != SVCP_UNSET:
        bad.append("slot 0 was called even though the major differs - the payload "
                   "must touch no slot at all in that case")
    return bad


# ---------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--console-ip", required=True, help="the board's UDP console")
    ap.add_argument("--console-port", type=int, default=board_run.DEFAULT_CONSOLE_PORT)
    ap.add_argument("--board-ip", default=None, help="where containers are streamed; "
                    "default the console address")
    ap.add_argument("--port", type=int, default=board_run.DEFAULT_RECV_PORT)
    ap.add_argument("--probe", type=pathlib.Path, required=True)
    ap.add_argument("--major", type=pathlib.Path)
    ap.add_argument("--both", type=pathlib.Path)
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()
    board_ip = args.board_ip or args.console_ip

    print("=" * 70)
    print("THE PAYLOAD ABI ON SILICON - Raspberry Pi 4 at %s" % args.console_ip)
    print("=" * 70)
    for p in (args.probe, args.major, args.both):
        if p:
            if not p.is_file():
                print("!! there is no file at %s, so nothing was run." % p)
                return 2
            report_file(p)
    print()

    con = board_run.NetConsole(args.console_ip, args.console_port)
    problems: list[tuple[str, list[str]]] = []
    try:
        if not con.at_prompt():
            print("!! no Anvil prompt on %s. Is the board powered and is this the "
                  "right console? Nothing was sent." % con.name)
            return 1
        print("-- the monitor answers " + "-" * 46)
        print(con.command("version", 10).strip())

        # ---- 1. the reference payload -----------------------------------
        print()
        print("-- 1. the reference payload " + "-" * 41)
        addr = stage(con, board_ip, args.port, args.probe)
        print(boot(con, addr, args.timeout).strip())
        time.sleep(1.0)
        w = words(read_memory(con, RESULT, WORDS * 8), WORDS)
        bad = judge_reference(w)

        def shown(key: str) -> str:
            return "-" if w[R[key]] == SVCP_UNSET else str(signed(w[R[key]]))

        def cap_shown(i: int) -> str:
            v = w[R["cap0"] + i]
            return "-" if v == SVCP_UNSET else str(signed(v))

        print()
        print("    board id %s, screen %sx%s, tier %s, frame %s us"
              % (shown("board_id"), shown("scr_w"), shown("scr_h"),
                 shown("tier"), shown("frame_cost")))
        print("    capabilities: " + ", ".join(
            "%s=%s" % (CAPS[i], cap_shown(i)) for i in range(14)))
        print("    gpio 4: mode %s level %s pull %s"
              % (shown("gpio_mode"), shown("gpio_level"), shown("gpio_pull")))
        print("    storage up %s, write-and-read-back %s, mmu state %s"
              % (shown("storage_up"), shown("file_rc"), shown("mmu")))
        problems.append(("the reference payload", bad))

        # ---- 2. the major-mismatch payload -------------------------------
        if args.major:
            print()
            print("-- 2. a payload built for a major this monitor is not " + "-" * 15)
            addr = stage(con, board_ip, args.port, args.major)
            print(boot(con, addr, args.timeout).strip())
            time.sleep(1.0)
            w2 = words(read_memory(con, RESULT, WORDS * 8), WORDS)
            sentence = cstring(con, SENTENCE)
            print()
            print("    the payload's own refusal, read out of its memory:")
            print("      %s" % sentence)
            problems.append(("the major-mismatch refusal",
                             judge_refusal(w2, sentence, ABI_MAJOR + 1, PROBE_NEED_MINOR)))

        # ---- 3. the container that asks for both --------------------------
        if args.both:
            print()
            print("-- 3. a container asking for both a device tree and the table " + "-" * 6)
            addr = stage(con, board_ip, args.port, args.both)
            reply = boot(con, addr, 30.0)
            print(reply.strip())
            bad = []
            low = reply.lower()
            if "both" not in low:
                bad.append("the refusal does not say the container asked for BOTH: %r"
                           % reply[:300])
            if "bit 1" not in low or "bit 2" not in low:
                bad.append("the refusal does not name both flags by number")
            if "nothing was loaded" not in low:
                bad.append("the refusal does not say that nothing was loaded, which "
                           "is the part that says the guard ran before the image did")
            if "its x0 register held" in low:
                bad.append("THE PAYLOAD WAS ENTERED. The ninth guard did not refuse "
                           "this container at all")
            problems.append(("the ninth guard", bad))
    except board_run.StreamError as error:
        problems.append(("the console", [str(error)]))
    finally:
        con.close()

    print()
    print("=" * 70)
    total = 0
    for title, bad in problems:
        if bad:
            print("  %s: RED" % title)
            for b in bad:
                print("    !! %s" % b)
            total += len(bad)
        else:
            print("  %s: GREEN" % title)
    print("=" * 70)
    if total:
        print("RESULT: RED (%d problem(s) on the board)" % total)
        return 1
    print("RESULT: GREEN - the payload ABI works through the real boot path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
