#!/usr/bin/env python3
"""Desk gate: the Pi 5's CYW43455 on BCM2712 SDIO2, through the shared Wi-Fi stack.

SILICON OWED. Builds RaspberryPi5/Tests/wifi2712_probe.pi5 with `-t pi5`
(RaspberryPi4/Lib/sdio.pi4 through its #PMF_CHIP = 2712 seams, and
Anvil/Net/cyw43.pbi unchanged) and runs it on tools/a64/a64_interp.py with:

  * a pinned firmware DTB in DRAM, from which sdio.pi4's
    SdioSetPinctrlFromDtb takes the pinctrl stepping (C0 from
    bcm2712-rpi-5-b.dtb, D0 from bcm2712d0-rpi-5-b.dtb, and a refusal for
    bcm2712-d-rpi-5-b.dtb, whose pinctrl@7d504100 carries neither
    compatible)
  * the BCM2712 SDIO2 host, cfg block, gio (WL_ON = GPIO28) and pinctrl
    model of tools/a64/a64_sdio_pi5_check.py: the card answers only after
    WL_ON has been cycled and high for the regulator's startup delay, with
    its six pins on sd2 and presence forced
  * the CYW43455 model of tools/a64/a64_sdio_check.py (backplane, chip ID,
    EROM, RAM, NVRAM, ARM start, HT clock, the host mailbox, SDPCM, CLM),
    with one change: after IOEx enables function 2, IORx reports it ready
    only on the third read, and any function-2 transfer before that is a
    failure - so a driver that does not wait for F2 is caught
  * the firmware and CLM Anvil ships (Firmware/CYW43455), the firmware cut
    to its first 32 KiB to keep the run short (the full 609,309-byte
    upload is the Pi 4 scan gate's), and the Pi 4 gate's synthetic NVRAM

The path: pinctrl from the DTB, SdioInit (CMD52 abort, CMD0, CMD5, CMD3,
CMD7, 4-bit), F1 enable, Cyw43Attach, block mode, PrepareDownload,
UploadFirmware, UploadNvram, Start, HtClock, AnnounceHost, F2 enable, and
Cyw43WifiUp (CLM download and the first ioctls over F2).

MUTANTS (unless --no-mutants): a wrong SDIO2 host base, a wrong WL_ON pin,
the F2 ready wait skipped, and the two pinctrl steppings swapped.

WHY THE FIRMWARE IS THE PI 4'S: brcmfmac picks the firmware by chip, not by
board - brcmfmac/sdio.c 633 (BRCMF_FW_CLM_DEF(43455, "brcmfmac43455-sdio"))
and 665 (chip $4345, revision mask $FFFFFDC0) - so the .bin and .clm_blob are
the same files on both boards. The NVRAM is per board: firmware.c 640-657
appends the board type, which of.c 102-114 takes from the root compatible,
so the Pi 5 wants brcmfmac43455-sdio.raspberrypi,5-model-b.txt. That file's
content is in no pinned source (owed).

Run from PowerShell:
  $env:PMF_ALLOW_UNTRACKED_COMPILER = 1
  py -3 -B tools/a64/a64_wifi_pi5_check.py --compiler <PureMetalForge.exe>
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "a64"))
sys.path.insert(0, str(ROOT / "tools"))
from a64_interp import A64, AlignmentFault, attach_symbols  # noqa: E402
from pmf_compiler import resolve_compiler  # noqa: E402
import a64_sdio_check as pi4gate  # noqa: E402
import a64_sdio_pi5_check as hostgate  # noqa: E402

FIXTURE = pathlib.PurePosixPath("RaspberryPi5/Tests/wifi2712_probe.pi5")
LIBRARY = pathlib.PurePosixPath("RaspberryPi4/Lib/sdio.pi4")
MUTANT_FILES = (FIXTURE, LIBRARY,
                pathlib.PurePosixPath("Anvil/Net/cyw43.pbi"),
                pathlib.PurePosixPath("Anvil/Net/cyw43_rx_glom.pbi"),
                pathlib.PurePosixPath("RaspberryPi4/Intrinsics/bcm2711_hardware.def"))

LOAD, STACK, LOADER_SP, LOADER_LR = 0x00400000, 0x03000000, 0x00100000, 0xDEADBEE0
CTL, OUT, DONE = 0x00E00000, 0x00E00100, 0x600DF00D
FW, NV, CLM, DTB = 0x01000000, 0x01200000, 0x01300000, 0x02000000
FW_PREFIX = 32768
TREES = {"bcm2712-rpi-5-b.dtb": "C0", "bcm2712d0-rpi-5-b.dtb": "D0", "bcm2712-d-rpi-5-b.dtb": None}


class Cyw43Card2712(pi4gate.Cyw43Card):
    """The Pi 4 gate's CYW43455, with function 2 slow to come ready."""
    F2_READY_POLLS = 3

    def __init__(self, k):
        super().__init__(k)
        self.f2_countdown = 0
        self.f2_ready_reads = 0

    def _cccr(self, write, addr, data):
        k = self.k
        if addr == k["SDIO_CCCR_IOEx"] and write:
            newly = bool(data & 4) and not (self.ioe & 4)
            r = super()._cccr(write, addr, data)
            if newly:
                self.ior &= ~4
                self.f2_countdown = self.F2_READY_POLLS
            return r
        if addr == k["SDIO_CCCR_IORx"] and not write and self.f2_countdown:
            self.f2_ready_reads += 1
            self.f2_countdown -= 1
            if self.f2_countdown == 0:
                self.ior |= 4
        return super()._cccr(write, addr, data)

    def cmd53_read(self, fn, addr, nbytes, incr):
        if fn == 2 and not (self.ior & 4):
            raise SystemExit("a function-2 read before IORx reported function 2 ready")
        return super().cmd53_read(fn, addr, nbytes, incr)

    def cmd53_write(self, fn, addr, payload, incr):
        if fn == 2 and not (self.ior & 4):
            raise SystemExit("a function-2 write before IORx reported function 2 ready")
        return super().cmd53_write(fn, addr, payload, incr)


def build(compiler, root, out):
    r = subprocess.run([compiler, "--compile", str(FIXTURE), "-t", "pi5", "--load-addr", hex(LOAD),
                        "--stack-addr", hex(STACK), "--entry-returns", "-o", str(out)],
                       cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise SystemExit("BUILD FAILED:\n" + r.stdout[-2500:])


def run(img, k, k4, scenario, tree_bytes, stepping, blobs, limit=400_000_000):
    cpu = A64()
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    attach_symbols(cpu, img, LOAD)
    fwb, nvb, clmb = blobs
    for base, data in ((DTB, tree_bytes), (FW, fwb), (NV, nvb), (CLM, clmb)):
        for i, v in enumerate(data):
            cpu.memory[base + i] = v
    ctl = struct.pack("<IIQIII", scenario, 0, DTB if tree_bytes else 0, len(fwb), len(nvb), len(clmb))
    for i, v in enumerate(ctl):
        cpu.memory[CTL + i] = v
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, LOADER_SP, LOADER_LR

    board = hostgate.Board(k, stepping or "C0", True, False)
    card = Cyw43Card2712(k4)
    hc = hostgate.Sdhci2712(k4, card, k["HOST_PHYS"], board)
    windows = [("host", k["HOST_PHYS"], k["HOST_SIZE"]), ("cfg", k["CFG_PHYS"], k["CFG_SIZE"]),
               ("pinctrl", k["PINCTRL_PHYS"], k["PINCTRL_SIZE_" + (stepping or "C0")]),
               ("gio", k["GIO_PHYS"], k["GIO_SIZE"])]

    def window(addr):
        for name, base, size in windows:
            if base <= addr < base + size:
                return name, addr - base
        return None, 0

    def load(addr, sz):
        cpu.align_guard(addr, sz, False)
        if addr >= 0x40000000:
            name, off = window(addr)
            if name is None or sz != 4:
                raise SystemExit(f"unmodelled MMIO read at ${addr:X}")
            board.touched.append(name)
            if name == "host":
                return hc.read(off)
            if name == "cfg":
                return board.cfg.get(off, 0)
            if name == "pinctrl":
                return board.pinctrl[off]
            return board.gio[off]
        return sum(cpu.memory.get(addr + i, 0) << (8 * i) for i in range(sz))

    def store(addr, value, sz):
        cpu.align_guard(addr, sz, True)
        v = value & 0xFFFFFFFF
        if addr >= 0x40000000:
            name, off = window(addr)
            if name is None or sz != 4:
                raise SystemExit(f"unmodelled MMIO write at ${addr:X}")
            board.touched.append(name)
            if name == "host":
                hc.write(off, v)
            elif name == "cfg":
                board.cfg[off] = v
            elif name == "pinctrl":
                board.pinctrl[off] = v
            else:
                board.gio_write(off, v)
            return
        for i in range(sz):
            cpu.memory[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    plain = A64.step.__get__(cpu)

    def step():
        board.steps += 1
        ins = load(cpu.pc, 4)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:
            cpu.x[ins & 31] = hostgate.CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:
            cpu.x[ins & 31] = board.tick()
            cpu.pc += 4
            return
        plain()

    n = 0
    try:
        while cpu.pc != LOADER_LR:
            n += 1
            if n > limit:
                raise SystemExit("the fixture never returned")
            step()
    except AlignmentFault as f:
        raise SystemExit(f.message())
    out = [struct.unpack_from("<I", bytes(cpu.memory.get(OUT + 4 * j + i, 0) for i in range(4)))[0]
           for j in range(17)]
    out = [v - (1 << 32) if v & 0x80000000 else v for v in out]
    return board, hc, card, out


def gate(img, k, k4, trees, blobs, verbose, radio_trees=("bcm2712-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb")):
    ck = hostgate.Checks(verbose)
    # Pinctrl from each pinned tree, and from no tree at all.
    for name, want in TREES.items():
        b, hc, card, o = run(img, k, k4, 2, trees[name], want, blobs)
        exp = {"C0": 1, "D0": 2, None: -2}[want]
        ck(o[16] == DONE and o[1] == exp and o[0] == (1 if want else 0),
           f"{name}: SdioSetPinctrlFromDtb -> {o[0]}, result {o[1]} (want {exp})")
    b, hc, card, o = run(img, k, k4, 2, b"", None, blobs)
    ck(o[0] == 0 and o[1] == -1, f"no tree: refused, result {o[1]} (want -1)")
    # The radio, on each stepping.
    for name in radio_trees:
        want = TREES[name]
        tag = f"{want} ({name})"
        b, hc, card, o = run(img, k, k4, 1, trees[name], want, blobs)
        steps = dict(zip(("SdioInit", "F1", "Attach", "PrepareDownload", "UploadFirmware",
                          "UploadNvram", "Start", "HtClock", "AnnounceHost", "F2"),
                         (o[2], o[4], o[5], o[7], o[8], o[9], o[10], o[11], o[12], o[13])))
        ck(all(v == 1 for v in steps.values()), f"{tag}: every step returned 1 {steps} (cyw43 error {o[15]})")
        ck(o[6] == 0x4345, f"{tag}: chip ID ${o[6] & 0xFFFF:04X} (want $4345)")
        ck(o[14] == 0, f"{tag}: Cyw43WifiUp returned {o[14]} (0 is success: CLM loaded, ioctls answered over F2)")
        hostgate.check_wl_on(ck, tag, b, k)
        hostgate.check_pins(ck, tag, b, k)
        idx = [c[0] for c in hc.commands]
        try:
            order = [idx.index(5), idx.index(3), idx.index(7)]
        except ValueError:
            order = []
        ck(len(order) == 3 and order == sorted(order), f"{tag}: CMD5, CMD3, CMD7 in order")
        ck(card.ioe & 0x6 == 0x6 and card.ior & 0x6 == 0x6, f"{tag}: F1 and F2 enabled and ready")
        ck(card.f2_ready_reads >= Cyw43Card2712.F2_READY_POLLS,
           f"{tag}: the driver read IORx {card.f2_ready_reads} times waiting for F2")
        ck(card.clm_done, f"{tag}: the CLM download finished (DL_END)")
        ck(not hc.silent, f"{tag}: every command answered")
    return ck


def _once(t, old, new):
    if t.count(old) != 1:
        raise SystemExit(f"mutant anchor not unique: {old!r} ({t.count(old)})")
    return t.replace(old, new)


MUTANTS = [
    ("wrong SDIO2 base (sdio1 at $1000FFF000)",
     lambda t: _once(t, "#SDIO_BASE     = $1001100000", "#SDIO_BASE     = $1000FFF000")),
    ("wrong WL_ON pin (GPIO29, BT_ON)",
     lambda t: _once(t, "#SDIO_WL_ON_BIT    = $10000000", "#SDIO_WL_ON_BIT    = $20000000")),
    ("F2 ready wait skipped",
     lambda t: _once(t, "  If SdioCmd52Write(0, #SDIO_CCCR_IOEx, reg | (1 << fn)) = 0\n    ProcedureReturn 0\n  EndIf\n",
                     "  If SdioCmd52Write(0, #SDIO_CCCR_IOEx, reg | (1 << fn)) = 0\n    ProcedureReturn 0\n  EndIf\n  ProcedureReturn 1\n")),
    ("pinctrl steppings swapped",
     lambda t: _once(t, "    sdio_pinctrlDtb = 1\n    ProcedureReturn SdioSetPinctrl(#SDIO_PINCTRL_C0)",
                     "    sdio_pinctrlDtb = 1\n    ProcedureReturn SdioSetPinctrl(#SDIO_PINCTRL_D0)")),
]


def mutants(compiler, k, k4, trees, blobs, work):
    raw = (ROOT / LIBRARY).read_bytes().decode("latin-1")
    crlf = "\r\n" in raw
    lib = raw.replace("\r\n", "\n")
    alive = []
    for name, edit in MUTANTS:
        root = work / "m"
        if root.exists():
            shutil.rmtree(root)
        for f in MUTANT_FILES:
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / f, root / f)
        text = edit(lib)
        (root / LIBRARY).write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("latin-1"))
        img = work / "m.img"
        try:
            build(compiler, root, img)
            ck = gate(img, k, k4, trees, blobs, False, radio_trees=("bcm2712-rpi-5-b.dtb",))
            red, why = bool(ck.bad), (ck.bad[0] if ck.bad else "every check passed")
        except SystemExit as e:
            red, why = True, str(e).splitlines()[0][:150]
        print(f"  mutant {'RED  ' if red else 'ALIVE'} {name}: {why[:150]}")
        if not red:
            alive.append(name)
    return alive


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--sources", default=str(hostgate.DEFAULT_SOURCES),
                    help="the vault's 'Raspberry Pi 5' folder: the pinned DTBs are read from it")
    ap.add_argument("--no-mutants", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if not a.compiler:
        hostgate.fail("pass --compiler or set PMF_COMPILER")
    compiler = str(resolve_compiler(a.compiler))
    src = pathlib.Path(a.sources)
    if not src.is_dir():
        raise SystemExit(f"a64_wifi_pi5_check: the pinned DTBs are needed and {src} is not a folder")
    k = hostgate.constants(src)
    k4 = pi4gate.read_constants()
    trees = {name: (src / "Boot staging" / name).read_bytes() for name in TREES}
    fw = (pi4gate.FIRMWARE / "brcmfmac43455-sdio.bin").read_bytes()[:FW_PREFIX]
    clm = (pi4gate.FIRMWARE / "brcmfmac43455-sdio.clm_blob").read_bytes()
    blobs = (fw, pi4gate.SYNTHETIC_NVRAM, clm)
    with tempfile.TemporaryDirectory(prefix="pmf_wifi_pi5_") as td:
        work = pathlib.Path(td)
        img = work / "wifi2712.img"
        build(compiler, ROOT, img)
        ck = gate(img, k, k4, trees, blobs, a.verbose)
        for m in ck.bad:
            print("  FAIL " + m)
        alive = [] if a.no_mutants else mutants(compiler, k, k4, trees, blobs, work)
    if ck.bad or alive:
        print(f"a64_wifi_pi5_check: FAIL - {len(ck.bad)} of {ck.n} checks red, {len(alive)} mutant(s) alive")
        return 1
    print(f"a64_wifi_pi5_check: PASS - {ck.n} checks"
          + ("" if a.no_mutants else f", {len(MUTANTS)}/{len(MUTANTS)} mutants red")
          + ". Desk only: silicon owed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
