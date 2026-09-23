#!/usr/bin/env python3
"""Compile/execute the transfer-pump receive-ownership gate.

The fixture includes the real net/netif/tftp/link stack and has the
production pumps spliced into it verbatim: NetServiceInput, netcon_PumpOne,
NetConsolePump and NetConsoleCommandDone from Anvil/Core/netconsole.pbi,
OutBreakByte/OutBreak from Anvil/Core/rxbreak.pbi, and NetXferSend/
NetXferPump/NetXferRun from Anvil/Core/net_cmd.pbi. It then drives a whole
put and a whole get over a modelled interface, with the replies coming back
to each of the two addresses the cable holds, from an ephemeral server port,
with a lost acknowledgement, with duplicated acknowledgements, and with
console and DHCP-service datagrams interleaved.

Each mutant restores one behaviour and must be rejected at a named
assertion:

  console-drain   the console's pump reads a claimed queue again, which is
                  the code that shipped in build 55: it takes the transfer's
                  acknowledgement off the wire and drops it, and the board
                  then spends its whole retransmit budget in silence
  no-release      the claim is never released, so the console's pump never
                  reads that interface again after the first transfer
  no-listener     the console's port goes back to riding the one movable
                  bind, so a command's own reply port displaces it and the
                  board cannot be typed at over the network for the whole
                  of that command
  no-retransmit   the sender's own timer no longer puts the block back on
                  the wire, so a lost acknowledgement is never recovered
  dup-ack-resend  the sender answers a DUPLICATE acknowledgement by
                  resending - the Sorcerer's Apprentice bug RFC 1123
                  names, which doubles every packet from then on

Requires external tools; neither is copied into the product tree:
  PMF_COMPILER=<path-to-PureMetalForge.exe> PMF_A64_INTERP=<path-to-a64_interp.py> \
      python tools/net_xfer_pump_ownership_emitted_check.py
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import tcp_multiif_emitted_check as emitted


ROOT = Path(__file__).resolve().parents[1]
NETCONSOLE = ROOT / "Anvil" / "Core" / "netconsole.pbi"
RXBREAK = ROOT / "Anvil" / "Core" / "rxbreak.pbi"
NET_CMD = ROOT / "Anvil" / "Core" / "net_cmd.pbi"
TFTP = ROOT / "RaspberryPi4" / "Lib" / "tftp.pi4"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "net_xfer_pump_ownership_emitted_gate.pi4"

ASSERTIONS = 71

MARKERS = {
    "; @@PRODUCTION_SERVICE_INPUT@@": "service",
    "; @@PRODUCTION_CONSOLE_PUMP@@": "console",
    "; @@PRODUCTION_COMMAND_DONE@@": "done",
    "; @@PRODUCTION_OUTBREAK@@": "outbreak",
    "; @@PRODUCTION_XFER@@": "xfer",
}

# The console pump's ownership test, as shipped after 2026-09-11.
OWNERSHIP_TEST = "  If NetIfRxOwner() = kind\n    ProcedureReturn\n  EndIf\n"


def span(source: str, first: str, last: str, label: str) -> str:
    """Everything from the header `first` to the end of the procedure `last`."""
    for needle in (first, last):
        if source.count(needle) != 1:
            raise SystemExit(
                f"pump ownership gate: {label} marker {needle!r} count "
                f"{source.count(needle)}"
            )
    start = source.index(first)
    end = source.find("\nEndProcedure", source.index(last))
    if end < 0 or end < start:
        raise SystemExit(f"pump ownership gate: {label} has no end")
    return source[start : end + len("\nEndProcedure")] + "\n"


def production() -> dict[str, str]:
    console = NETCONSOLE.read_text(encoding="utf-8")
    rxbreak = RXBREAK.read_text(encoding="utf-8")
    cmd = NET_CMD.read_text(encoding="utf-8")
    blocks = {
        "service": span(
            console,
            "Procedure.i NetServiceInput(kind.i, *frame, rc.i)",
            "Procedure.i NetServiceInput(kind.i, *frame, rc.i)",
            "NetServiceInput",
        ),
        "console": span(
            console,
            "Procedure netcon_PumpOne(kind.i)",
            "Procedure NetConsolePump()",
            "the console pump",
        ),
        "done": span(
            console,
            "Procedure NetConsoleCommandDone()",
            "Procedure NetConsoleCommandDone()",
            "NetConsoleCommandDone",
        ),
        "outbreak": span(
            rxbreak,
            "Global gAbort.i",
            "Procedure.i OutBreak()",
            "the break reader",
        ),
        "xfer": span(
            cmd,
            "Procedure.i NetXferSend(kind.i)",
            "Procedure.i NetXferRun(kind.i)",
            "the transfer pump",
        ),
    }
    required = (
        ("console", OWNERSHIP_TEST),
        ("console", "NetServiceInput(kind, p, rc)"),
        ("console", "NetUdpListen(k, #NETCON_PORT, 1)"),
        ("console", "NetUdpListen(k, #NETCON_PORT, 0)"),
        ("done", "NetIfReleaseRx()"),
        ("outbreak", "NetConsolePump()"),
        # THE SLICE GOES ON THE TRANSFER'S OWN WIRE - 2026-09-16. This
        # was LinkPumpAllNet(ms), the fair pump, whose rotating cursor
        # parked the whole 200 ms slice on the radio after every block on
        # a board holding a cable and a lease at once. See
        # LinkPumpAllNetPrefer in RaspberryPi4/Lib/link.pi4.
        ("xfer", "LinkPumpAllNetPrefer(kind, ms)"),
        ("xfer", "TftpTick(millis())"),
        ("xfer", "OutBreak()"),
    )
    for name, needle in required:
        if needle not in blocks[name]:
            raise SystemExit(
                f"pump ownership gate: the {name} block lost {needle!r}"
            )
    return blocks


def fixture(blocks: dict[str, str]) -> str:
    text = FIXTURE.read_text(encoding="utf-8")
    for marker, name in MARKERS.items():
        if text.count(marker) != 1:
            raise SystemExit(
                f"pump ownership gate: fixture marker {marker} count "
                f"{text.count(marker)}"
            )
        text = text.replace(marker, blocks[name])
    return text


def mutate(blocks: dict[str, str], name: str) -> dict[str, str]:
    out = dict(blocks)
    if name == "console-drain":
        out["console"] = replace_once(
            blocks["console"],
            OWNERSHIP_TEST,
            "  ; the receive-ownership test removed by mutation\n",
            name,
        )
    elif name == "no-release":
        out["done"] = replace_once(
            blocks["done"],
            "  NetIfReleaseRx()\n",
            "  ; the release removed by mutation\n",
            name,
        )
    elif name == "no-listener":
        out["console"] = replace_once(
            blocks["console"],
            "      NetUdpListen(k, #NETCON_PORT, 1)\n",
            "      ; the console's persistent listener removed by mutation\n",
            name,
        )
    elif name == "no-retransmit":
        out["xfer"] = replace_once(
            blocks["xfer"],
            "  t = TftpTick(millis())\n  If t = 1\n    NetXferSend(kind)\n  EndIf\n",
            "  t = TftpTick(millis())\n",
            name,
        )
    else:
        raise SystemExit(f"pump ownership gate: unknown mutation {name}")
    return out


def replace_once(text: str, needle: str, replacement: str, name: str) -> str:
    if text.count(needle) != 1:
        raise SystemExit(
            f"pump ownership gate: {name} mutation site count {text.count(needle)}"
        )
    return text.replace(needle, replacement, 1)


# The library mutation is applied to a generated copy of tftp.pi4 and reaches
# the fixture through its own include line, so every other protocol rule in
# that file stays exactly as it ships.
DUP_ACK_SITE = """    tftp_dupCount = tftp_dupCount + 1
    ProcedureReturn #TFTP_IN_DUP
"""
DUP_ACK_BROKEN = """    tftp_dupCount = tftp_dupCount + 1
    tftp_RetransmitData()
    ProcedureReturn #TFTP_IN_DUP
"""


def tftp_mutant(work: Path, text: str) -> str:
    library = TFTP.read_text(encoding="utf-8")
    if library.count(DUP_ACK_SITE) != 1:
        raise SystemExit(
            f"pump ownership gate: duplicate-ack site count {library.count(DUP_ACK_SITE)}"
        )
    broken = work / "tftp_dup_ack_resend.pi4"
    broken.write_text(
        library.replace(DUP_ACK_SITE, DUP_ACK_BROKEN, 1), encoding="utf-8", newline="\n"
    )
    include = 'XIncludeFile "RaspberryPi4/Lib/tftp.pi4"'
    if text.count(include) != 1:
        raise SystemExit("pump ownership gate: the fixture's tftp include drifted")
    return text.replace(include, f'XIncludeFile "{broken.as_posix()}"', 1)


# ----------------------------------------------------------------------
#  THE COUNTER FREQUENCY IS DECLARED HERE, NOT BAKED INTO THE MODEL.
#
#  net.pi4 divides CNTFRQ_EL0 to turn an ARP lifetime in milliseconds
#  into ticks, and the interpreter refuses that register by name so that
#  one board's frequency cannot be handed silently to another board's
#  image. 54 MHz is the Raspberry Pi 4's, which is the target this
#  fixture is compiled for. CNTPCT_EL0 the interpreter counts itself.
# ----------------------------------------------------------------------
CNTFRQ = 54_000_000
STEP_LIMIT = 60_000_000


def execute(a64, image: Path) -> tuple[int, int]:
    blob = image.read_bytes()
    bss_lo, bss_hi = emitted.symbol_bounds(image.with_suffix(image.suffix + ".sym"))
    image_range = (emitted.LOAD, emitted.LOAD + len(blob))
    bss_range = (bss_lo, bss_hi)
    stack_range = (emitted.STACK - emitted.STACK_BYTES, emitted.STACK + 16)
    readable = (image_range, bss_range, stack_range)
    writable = (bss_range, stack_range)

    def contains(ranges, addr: int, size: int) -> bool:
        return size > 0 and any(lo <= addr and addr + size <= hi for lo, hi in ranges)

    cpu = a64.A64()
    for offset, byte in enumerate(blob):
        cpu.memory[emitted.LOAD + offset] = byte
    a64.attach_symbols(cpu, image, emitted.LOAD)
    cpu.pc = emitted.LOAD
    cpu.sp = emitted.STACK
    cpu.x[30] = emitted.LOADER_LR

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if not contains(readable, addr, size):
            raise SystemExit(
                f"pump ownership gate: read outside image/BSS/stack at ${addr:08X}+{size}"
            )
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if not contains(writable, addr, size):
            raise SystemExit(
                f"pump ownership gate: write outside BSS/stack at ${addr:08X}+{size}"
            )
        for i in range(size):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = a64.A64.step.__get__(cpu)
    for steps in range(STEP_LIMIT):
        if cpu.pc == emitted.LOADER_LR:
            return cpu.x[0], steps
        if (load(cpu.pc, 4) & 0xFFFFFFE0) == 0xD53BE000:   # mrs Xt, cntfrq_el0
            cpu.x[load(cpu.pc, 4) & 31] = CNTFRQ
            cpu.pc += 4
        else:
            plain_step()
    raise SystemExit(f"pump ownership gate: no return in {STEP_LIMIT:,} instructions")


def build(compiler: Path, work: Path, text: str, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists():
        shutil.copy2(compiler, staged)
    boards = ROOT / "Boards"
    if boards.is_dir() and not (work / "Boards").exists():
        shutil.copytree(boards, work / "Boards")
    source = work / f"{stem}.pi4"
    source.write_text(text, encoding="utf-8", newline="\n")
    image = work / f"{stem}.img"
    command = [
        str(staged), "--compile",
        str(source),
        "-t", "pi4",
        "--load-addr", hex(emitted.LOAD),
        "--stack-addr", hex(emitted.STACK),
        "--entry-returns",
        "-o", str(image),
        "-s",
    ]
    run = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PMF_ROOT": str(ROOT)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit(f"pump ownership gate: {stem} compile failed\n{run.stdout}")
    if not image.is_file() or not image.with_suffix(image.suffix + ".sym").is_file():
        raise SystemExit(
            f"pump ownership gate: {stem} compiler omitted image or symbol map"
        )
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    parser.add_argument("--interp", default=os.environ.get("PMF_A64_INTERP"))
    args = parser.parse_args()
    compiler = emitted.required_path(args.compiler, "PMF_COMPILER")
    interp = emitted.required_path(args.interp, "PMF_A64_INTERP")
    a64 = emitted.load_interpreter(interp)

    blocks = production()
    digest = hashlib.sha256(
        "".join(blocks[name] for name in sorted(blocks)).encode("utf-8")
    ).hexdigest()

    # Each mutation names the first assertion that must reject it.
    #
    # console-drain MOVED FROM 2 TO 67 ON 2026-09-16, and not because
    # anything here got weaker. NetXferPump used to call LinkPumpAllNet,
    # the fair pump, which parked its whole slice on the other interface
    # after every block; the acknowledgement therefore lay in the wired
    # queue until the loop came round to OutBreak(), and the console's
    # pump - unclaimed, by this mutation - read it first and dropped it.
    # That is what assertion 2, the plain put, was catching. The pump now
    # spends the slice on the transfer's own wire
    # (LinkPumpAllNetPrefer), so for a SINGLE copy of an acknowledgement
    # the transfer takes it before any other reader is even called and
    # the plain put completes with the claim removed.
    #
    # THE CLAIM IS STILL LOAD-BEARING and case 11 says so: when every
    # acknowledgement arrives TWICE - ordinary on a segment - the
    # transfer's pump takes one copy and the unclaimed console pump eats
    # the other, so TftpDupCount() never reaches 3. Assertion 67 is that
    # count, and it is a counter no other reader can touch. Two correct
    # things now stand between the console and a transfer's reply; this
    # gate still refuses to let either of them be removed.
    mutations = (
        ("console-drain", 67),
        ("no-listener", 43),
        ("no-release", 56),
        ("no-retransmit", 33),
    )

    with tempfile.TemporaryDirectory(prefix="anvil-pump-ownership-") as temporary:
        work = Path(temporary)
        image = build(compiler, work, fixture(blocks), "net_xfer_pump_ownership_gate")
        result, steps = execute(a64, image)
        if result:
            print(
                f"net_xfer_pump_ownership_emitted_check: FAIL assertion {result} "
                f"after {steps:,} A64 instructions"
            )
            return 1

        killed = []
        for name, expected in mutations:
            mutant = fixture(mutate(blocks, name))
            mutant_image = build(compiler, work, mutant, f"pump_ownership_mutant_{name}")
            mutant_result, mutant_steps = execute(a64, mutant_image)
            if mutant_result != expected:
                print(
                    f"net_xfer_pump_ownership_emitted_check: FAIL {name} mutation "
                    f"returned {mutant_result}; expected assertion {expected}"
                )
                return 1
            killed.append((name, expected, mutant_steps))

        mutant = tftp_mutant(work, fixture(blocks))
        mutant_image = build(compiler, work, mutant, "pump_ownership_mutant_dup_ack")
        mutant_result, mutant_steps = execute(a64, mutant_image)
        if mutant_result != 65:
            print(
                "net_xfer_pump_ownership_emitted_check: FAIL dup-ack-resend mutation "
                f"returned {mutant_result}; expected assertion 65"
            )
            return 1
        killed.append(("dup-ack-resend", 65, mutant_steps))

    print(
        f"net_xfer_pump_ownership_emitted_check: PASS - {ASSERTIONS} assertions, "
        f"{steps:,} A64 instructions"
    )
    for name, expected, mutant_steps in killed:
        print(
            f"  {name} mutation rejected at assertion {expected} "
            f"after {mutant_steps:,} instructions"
        )
    print(f"  production pump blocks sha256 {digest}")
    print("No hardware was contacted; the wire, the peer machine and the console's")
    print("keystroke ring are modelled seams, so this is an emitted-code proof only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
