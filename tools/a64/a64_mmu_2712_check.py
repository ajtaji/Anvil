#!/usr/bin/env python3
"""Desk gate for the BCM2712 (-t pi5) arm of RaspberryPi4/Lib/mmu.pi4.

Builds RaspberryPi5/Tests/mmu2712_tables_probe.pi5 with `-t pi5`, runs it in
tools/a64/a64_interp.py so MmuBuildTables() writes its three tables into the
model's memory, then WALKS them here the way the hardware would - from the
TTBR the builder handed over, at the starting level the TCR it handed over
implies - and checks the result against a map derived in THIS file from the
pinned sources, not from mmu.pi4:

  bcm2712.dtsi:189-191   soc@107c000000 -> $10_0000_0000, 2 GiB
  bcm2712.dtsi:424-435   axi identity ranges: RAM 0..$10_0000_0000, SoC
                         $10_0000_0000 + 4 GiB
  bcm2712.dtsi:545-549   pcie2 (RP1) 32-bit window $1F_0000_0000, ~4 GiB
  bcm2712-ds.dtsi:402-416, dtb  V3D hub/core0/sms
  HARDWARE-BRINGUP.md    EL3 stub 0..$80000, DTB $2EFEC600, firmware
                         framebuffer $3F800000, GIC $10_7FFF_9000, PM,
                         RP1 UART0 $1F_0003_0000
  RaspberryPi4/Board/memmap.pi4:65-70, 217-219, 309-310, 551-566
                         the monitor's own low-memory bands
  U-Boot v2025.01 arch/arm/include/asm/armv8/mmu.h:28-68, 83-104 and
  arch/arm/cpu/armv8/cache_v8.c:73-103, 121-139 (vault
  "Raspberry Pi 5/Sources/uboot-v2025.01/"): descriptor bits, MAIR
  indices, TCR fields, the ips/va_bits choice and the starting level.

Checked, per case (RAM default 1 GiB, 4/8/16 GiB, a sub-GiB DTB value, two
Non-Cacheable regions): every level-0/1/2 descriptor; every address the
monitor, the stub, the DTB, the framebuffers and the page tables occupy is
mapped Normal (and the framebuffer Normal Non-Cacheable); every device
address is Device-nGnRnE; NOTHING at or above $10_0000_0000 is Normal; no
RAM gigabyte is mapped beyond the RAM size; the Access Flag is set on every
block; the TCR covers every mapped PA and VA; the refusals refuse.

--mutate builds broken copies of mmu.pi4 and demands each one fails.

WHAT IT CANNOT PROVE: that the A76 accepts the tables. a64_interp performs no
translation; only the board can. It also does not test the enable sequence,
which is the Pi 4's, unchanged (TCR_EL3 shares TCR_EL2's layout,
mmu.h:103-104).

Run:  py -3 -B tools/a64/a64_mmu_2712_check.py --compiler <PureMetalForge.exe> [--mutate]
      (PMF_ALLOW_UNTRACKED_COMPILER=1 for a private compiler build)
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE_REL = pathlib.Path("RaspberryPi5") / "Tests" / "mmu2712_tables_probe.pi5"
LIB_REL = pathlib.Path("RaspberryPi4") / "Lib" / "mmu.pi4"
DEF_REL = pathlib.Path("RaspberryPi4") / "Intrinsics" / "bcm2711_hardware.def"

sys.path.insert(0, str(HERE))
from a64_interp import A64  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from pmf_compiler import resolve_compiler  # noqa: E402

LOAD, STACK, LOADER_LR = 0x400000, 0x3000000, 0xDEADBEE0
MP_IN = 0x5F0000
TABLES = 0x600000

GiB = 1 << 30
MiB2 = 1 << 21
SOC_LO, SOC_HI = 0x10_0000_0000, 0x11_0000_0000           # axi ranges, 4 GiB
RP1_LO, RP1_HI = 0x1F_0000_0000, 0x20_0000_0000           # pcie2 32-bit window

# U-Boot mmu.h:28-32 MAIR indices, :34-38 MEMORY_ATTRIBUTES bytes.
MAIR_BYTE = {0: 0x00, 1: 0x04, 2: 0x0C, 3: 0x44, 4: 0xFF}
KIND = {0x00: "Device-nGnRnE", 0x44: "Normal-NC", 0xFF: "Normal-WB"}

DEVICE_ADDRS = {
    "GICD $10_7FFF_9000": 0x10_7FFF_9000,
    "GICC $10_7FFF_A000": 0x10_7FFF_A000,
    "SD $10_00FF_F000": 0x10_00FF_F000,
    "SDIO2 $10_0110_0000": 0x10_0110_0000,
    "V3D hub $10_0200_0000": 0x10_0200_0000,
    "V3D core0 $10_0200_8000": 0x10_0200_8000,
    "V3D sms $10_0203_0800": 0x10_0203_0800,
    "PM $10_7D20_0000": 0x10_7D20_0000,
    "UART10 $10_7D00_1000": 0x10_7D00_1000,
    "LOCAL_CONTROL $10_7C28_0000": 0x10_7C28_0000,
    "soc base $10_7C00_0000": 0x10_7C00_0000,
    "PCIe2 regs $10_0012_0000": 0x10_0012_0000,
    "RP1 UART0 $1F_0003_0000": 0x1F_0003_0000,
    "RP1 GPIO $1F_000D_0000": 0x1F_000D_0000,
}


def ram_ranges(fb_lo: int, fb_hi: int) -> dict[str, tuple[int, int]]:
    return {
        "EL3 stub 0..$80000": (0x0, 0x80000),
        "monitor stack band ..$100000": (0x80000, 0x100000),
        "monitor image $200000": (0x200000, 0x0A00000),
        "DSI framebuffers $08A00000": (0x08A00000, 0x09200000),
        "capture $0B000000": (0x0B000000, 0x0BC00000),
        "Vulkan heap $0C000000": (0x0C000000, 0x0D000000),
        "monitor BSS (mailbox buffer) $0D000000": (0x0D000000, 0x0E000000),
        "Pi 5 board stack below $8000000": (0x07F00000, 0x08000000),
        "DTB $2EFEC600": (0x2EFEC600, 0x2F000000),
        "payload $400000": (0x400000, 0x600000),
        "page tables": (TABLES, TABLES + 3 * 4096),
        "framebuffer": (fb_lo, fb_hi),
    }


class Fail(Exception):
    pass


def build(root: pathlib.Path, compiler: str, out: pathlib.Path) -> pathlib.Path:
    r = subprocess.run(
        [compiler, "--compile", str(root / PROBE_REL), "-t", "pi5", "--entry-returns",
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-o", str(out)],
        cwd=root, env=dict(os.environ, PMF_ROOT=str(root)), capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        raise Fail("build failed (exit %d)\n%s%s" % (r.returncode, r.stdout[-2000:], r.stderr))
    if "target BCM2712" not in r.stdout:
        raise Fail("the compiler did not build for BCM2712 - it does not know -t pi5")
    return out


def run(img: pathlib.Path, ram: int, nclo: int, nchi: int, base: int):
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(img.read_bytes()):
        mem[LOAD + i] = b

    def put(addr, v):
        for i in range(8):
            mem[addr + i] = (v >> (8 * i)) & 0xFF
    put(MP_IN, ram)
    put(MP_IN + 8, nclo)
    put(MP_IN + 16, nchi)
    put(MP_IN + 24, base)
    cpu.pc, cpu.sp, cpu.x[30] = LOAD, STACK, LOADER_LR

    def load(addr, size):
        if size > 1 and addr % size:
            raise Fail("unaligned %d-byte load at $%X" % (size, addr))
        if addr >= 0x40000000:
            raise Fail("the table builder read $%X, outside RAM" % addr)
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        if size > 1 and addr % size:
            raise Fail("unaligned %d-byte store at $%X - a descriptor is 8 bytes" % (size, addr))
        if addr >= 0x40000000:
            raise Fail("the table builder wrote $%X, outside RAM" % addr)
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load, cpu.store = load, store
    for _ in range(5_000_000):
        if cpu.pc == LOADER_LR:
            break
        cpu.step()
    else:
        raise Fail("the probe did not return")

    def rd(a):
        return sum(mem.get(a + i, 0) << (8 * i) for i in range(8))
    rc = cpu.x[0] - (1 << 64) if cpu.x[0] >> 63 else cpu.x[0]
    return rc, rd(MP_IN + 32), rd(MP_IN + 40), rd


def decode_tcr(tcr: int) -> dict:
    return {"t0sz": tcr & 0x3F, "irgn": (tcr >> 8) & 3, "orgn": (tcr >> 10) & 3,
            "sh": (tcr >> 12) & 3, "tg0": (tcr >> 14) & 3, "ps": (tcr >> 16) & 7,
            "res1": (tcr >> 31) & 1 and (tcr >> 23) & 1}


PS_BITS = {0: 32, 1: 36, 2: 40, 3: 42, 4: 44, 5: 48}   # cache_v8.c:73-90


def walk(rd, ttbr: int, tcr: int, va: int):
    """Translate va. Returns (pa, attrindx, block_desc) or None for a fault."""
    t = decode_tcr(tcr)
    va_bits = 64 - t["t0sz"]
    if va >> va_bits:
        return None
    level = 1 if va_bits < 39 else 0                      # cache_v8.c:137-139
    table = ttbr
    while True:
        shift = 12 + 9 * (3 - level)                     # cache_v8.c:121-125
        idx = (va >> shift) & 0x1FF
        d = rd(table + idx * 8)
        typ = d & 3
        if typ == 0:
            return None
        if typ == 1:                                     # block
            if level == 0:
                raise Fail("a BLOCK descriptor at level 0 (not allowed with 4 KiB granules)")
            out = d & ((1 << 48) - 1) & ~((1 << shift) - 1)
            return out | (va & ((1 << shift) - 1)), (d >> 2) & 7, d
        if level == 2:
            raise Fail("a level-3 table was referenced; none is built")
        table = d & ((1 << 48) - 1) & ~0xFFF
        level += 1


def check_case(name: str, img: pathlib.Path, ram: int, nclo: int, nchi: int) -> list[str]:
    errs: list[str] = []
    rc, ttbr, tcr, rd = run(img, ram, nclo, nchi, TABLES)
    if rc != 0:
        return [f"{name}: MmuBuildTables returned {rc}"]
    t = decode_tcr(tcr)
    va_bits, pa_bits = 64 - t["t0sz"], PS_BITS.get(t["ps"], 0)
    if not t["res1"] or t["tg0"] != 0 or t["sh"] != 3 or t["irgn"] != 1 or t["orgn"] != 1:
        errs.append(f"{name}: TCR ${tcr:X} fields wrong {t}")
    if (1 << pa_bits) < RP1_HI:
        errs.append(f"{name}: TCR PS gives {pa_bits}-bit PA; the RP1 window ends at ${RP1_HI:X}")
    if (1 << va_bits) < RP1_HI:
        errs.append(f"{name}: TCR T0SZ gives {va_bits}-bit VA; the map needs ${RP1_HI:X}")
    # U-Boot's choice for max_addr in (2^36, 2^40]: ips 2, va_bits 40 (cache_v8.c:82-84).
    if (t["ps"], va_bits) != (2, 40):
        errs.append(f"{name}: TCR is ips {t['ps']} / va_bits {va_bits}, U-Boot's rule gives 2 / 40")
    if ttbr % 4096 or not (TABLES <= ttbr < TABLES + 3 * 4096):
        errs.append(f"{name}: TTBR ${ttbr:X} not a table inside the table area")

    ram_top = max(GiB, min((ram >> 30) << 30 if ram >= GiB else GiB, SOC_LO))

    def kind(a):
        w = walk(rd, ttbr, tcr, a)
        if w is None:
            return None
        pa, idx, d = w
        if pa != a:
            raise Fail(f"{name}: ${a:X} translates to ${pa:X}; the map must be identity")
        if not d & (1 << 10):
            errs.append(f"{name}: block for ${a:X} has no Access Flag (mmu.h:65)")
        return KIND.get(MAIR_BYTE.get(idx), f"attr{idx}")

    # RAM bands the monitor, stub, DTB and framebuffer occupy: mapped Normal.
    for label, (lo, hi) in ram_ranges(nclo or 0x3F800000, nchi or 0x3FBF4000).items():
        a = lo
        while a < hi:
            k = kind(a)
            want_nc = nclo and nclo <= a < nchi
            if k is None:
                errs.append(f"{name}: HOLE - {label} at ${a:X} is unmapped")
                break
            if want_nc and k != "Normal-NC":
                errs.append(f"{name}: {label} at ${a:X} is {k}, want Normal-NC")
                break
            if not want_nc and label != "framebuffer" and k != "Normal-WB":
                errs.append(f"{name}: {label} at ${a:X} is {k}, want Normal-WB")
                break
            a += MiB2 if (hi - lo) > MiB2 else max(1, (hi - lo))
    # The whole low GiB, block by block; above it every GiB.
    for a in range(0, GiB, MiB2):
        k = kind(a)
        nc = nclo and (a + MiB2 > (nclo >> 21 << 21)) and a < ((nchi + MiB2 - 1) >> 21 << 21)
        want = "Normal-NC" if nc else "Normal-WB"
        if k != want:
            errs.append(f"{name}: low-GiB block ${a:X} is {k}, want {want}")
            break
    for g in range(1, 512):
        a = g * GiB
        k = kind(a)
        if a < ram_top:
            want = "Normal-WB"
        elif SOC_LO <= a < SOC_HI or RP1_LO <= a < RP1_HI:
            want = "Device-nGnRnE"
        else:
            want = None
        if k != want:
            errs.append(f"{name}: GiB {g} (${a:X}) is {k}, want {want}")
    for va in (512 * GiB, 1 << 39 | 0x1000):
        if walk(rd, ttbr, tcr, va) is not None:
            errs.append(f"{name}: ${va:X} (beyond 512 GiB) is mapped")
    # Every named device is Device, and nothing at or above the SoC base is Normal.
    for label, a in DEVICE_ADDRS.items():
        k = kind(a)
        if k != "Device-nGnRnE":
            errs.append(f"{name}: {label} is {k}, want Device-nGnRnE")
    return errs


def scenarios(img: pathlib.Path) -> list[str]:
    fb_lo, fb_hi = 0x3F800000, 0x3F800000 + 1920 * 1080 * 2        # granted 16 bpp
    errs = []
    errs += check_case("default RAM, firmware FB NC", img, 0, fb_lo, fb_hi)
    errs += check_case("4 GiB", img, 4 * GiB, fb_lo, fb_hi)
    errs += check_case("8 GiB", img, 8 * GiB, fb_lo, fb_hi)
    errs += check_case("16 GiB", img, 16 * GiB, fb_lo, fb_hi)
    errs += check_case("DTB source value 640 MiB", img, 0x28000000, fb_lo, fb_hi)
    errs += check_case("absurd 200 GiB (capped at the SoC)", img, 200 * GiB, fb_lo, fb_hi)
    errs += check_case("DSI framebuffer window NC", img, 8 * GiB, 0x08A00000, 0x09200000)
    for base, want in ((0x3000, -3), (0x600800, -2), (0, -1)):
        rc, *_ = run(img, 0, 0, 0, base)
        if rc != want:
            errs.append(f"refusal: base ${base:X} returned {rc}, want {want}")
    return errs


MUTANTS = [
    ("PS 36-bit", "#MMU_TCR_2712     = $80823518", "#MMU_TCR_2712     = $80813518"),
    ("T0SZ 25 with a level-0 table", "#MMU_TCR_2712     = $80823518", "#MMU_TCR_2712     = $80823519"),
    ("RP1 window cacheable", "    ElseIf i >= #MMU_PCIE_SLOT_LO And i <= #MMU_PCIE_SLOT_HI\n      d = pa | #MMU_ATTR_DEVICE",
     "    ElseIf i >= #MMU_PCIE_SLOT_LO And i <= #MMU_PCIE_SLOT_HI\n      d = pa | #MMU_DRAM_ATTR"),
    ("one GiB past RAM", "    ElseIf i < ramSlots And i < #MMU_SOC_SLOT_LO", "    ElseIf i <= ramSlots And i < #MMU_SOC_SLOT_LO"),
    ("SoC window missing a GiB", "#MMU_SOC_SLOT_HI  = 67", "#MMU_SOC_SLOT_HI  = 66"),
    ("NC ignored on 2712", "    If mmu_BlockNc(pa) <> 0\n      d = pa | #MMU_ATTR_NORMAL_NC\n    Else\n      d = pa | #MMU_DRAM_ATTR\n    EndIf\n    PokeI(l2 + (i << 3), d)\n  Next\n\n  ; ---- level 1: 512",
     "    d = pa | #MMU_DRAM_ATTR\n    PokeI(l2 + (i << 3), d)\n  Next\n\n  ; ---- level 1: 512"),
    ("level-0 entry faulted", "    If i = 0\n      d = base | #MMU_DESC_TABLE", "    If i = 99\n      d = base | #MMU_DESC_TABLE"),
    # Both RAM guards at once - the cap in MmuSetRamBytes and the SoC-slot
    # bound in the builder each protect the map alone, so removing only one
    # is (correctly) not a fault; removing both must be.
    ("RAM guards removed", "  If bytes > #MMU_PERIPH_BASE\n    bytes = #MMU_PERIPH_BASE\n  EndIf\n", "",
     "    ElseIf i < ramSlots And i < #MMU_SOC_SLOT_LO", "    ElseIf i < ramSlots"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Desk gate for the BCM2712 arm of mmu.pi4.")
    ap.add_argument("--compiler", default=None)
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    compiler = resolve_compiler(a.compiler)
    with tempfile.TemporaryDirectory(prefix="mmu2712-") as td:
        wd = pathlib.Path(td)
        try:
            errs = scenarios(build(ROOT, compiler, wd / "probe.img"))
        except Fail as e:
            errs = [str(e)]
        for e in errs:
            print("FAIL", e)
        print(f"a64_mmu_2712_check: 7 map cases + 3 refusals, {len(errs)} failure(s)")
        rc = 1 if errs else 0
        if a.mutate:
            src = (ROOT / LIB_REL).read_text(encoding="utf-8")
            killed = 0
            for i, (label, *pairs) in enumerate(MUTANTS):
                text = src.replace("\r\n", "\n")
                stale = False
                for j in range(0, len(pairs), 2):
                    if text.count(pairs[j]) != 1:
                        stale = True
                    text = text.replace(pairs[j], pairs[j + 1])
                if stale:
                    print(f"MUTANT {label}: pattern not found exactly once - list is stale")
                    rc = 1
                    continue
                mroot = wd / f"m{i}"
                for rel in (LIB_REL, DEF_REL, PROBE_REL):
                    (mroot / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / rel, mroot / rel)
                (mroot / LIB_REL).write_text(text, encoding="utf-8")
                try:
                    merr = scenarios(build(mroot, compiler, wd / f"m{i}.img"))
                except Fail as e:
                    merr = [str(e)]
                ok = bool(merr)
                killed += ok
                print(f"MUTANT {label}: {'killed' if ok else 'SURVIVED'}"
                      + (f" ({merr[0].splitlines()[0][:100]})" if ok else ""))
            print(f"mutants: {killed}/{len(MUTANTS)} killed")
            if killed != len(MUTANTS):
                rc = 1
        return rc


if __name__ == "__main__":
    raise SystemExit(main())
