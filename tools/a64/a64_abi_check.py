#!/usr/bin/env python3
r"""Executable gate for Anvil's PAYLOAD ABI - the service table in x0.

    python tools/a64/a64_abi_check.py --compiler <PureMetalForge.exe>
    python tools/a64/a64_abi_check.py --compiler <...> --mutate

WHAT THIS PROVES, AND WHY EACH PART IS HERE
===========================================
Anvil/Hal/abi.pbi hands a separately compiled payload one pointer and a
contract.  Everything about that contract is a NUMBER agreed between two
programs that never see each other's source - a slot index, a capability
id, an error code - and the failure mode of a wrong number is the worst one
this table can have: THE WRONG PROCEDURE CALLED WITH THE RIGHT ARGUMENTS,
which returns a plausible value and is diagnosed days later.

The published half of the ABI is three files on Anvil main:
Anvil/Hal/abi_version.pbi (major, minor, slot count), Anvil/Hal/seams.pbi
(the capability ids and the module slots) and Anvil/Hal/abi.pbi (the error
set, the group bases and the table itself).

  A. STATIC - the sources are read and cross-checked.
       * every #SVC_* error code is inside -100..-199, and no #HW_* code in
         hal.pbi lands in that range.  #HW_* ERROR codes are held above the
         -99 floor as well; the #HW_* constants that are impossible VALUES
         rather than error codes are exempt from the floor BY NAME in
         HW_VALUE_SENTINELS, never by pattern, and are still bound by the
         range.
       * every constant the reference payload RESTATES (it cannot include
         the ABI files) equals the published value.
       * the group bases, the version and the capability ids match this
         file's own statement of them.
       * the guarded setting names match pmfboot.pbi's spelling.

  B. SOURCE HYGIENE - the reference payload names no chip.  A probe that
     reached for one Pi 4 library "just for its output" would prove the
     opposite of what it appears to.

  C. THE CONTAINER FLAG - the compiler emits bit 2 for --wants-services,
     decoded here from pmfboot.pbi's field table rather than from the
     writer, and the flag changes nothing but the header.

  D. DYNAMIC - the real compiled monitor (RaspberryPi4/Board/board.pi4) is
     run on the project's A64 emulator, BuildServiceTable() is called, and
     the table it built is read back:
       * the header words; NO SLOT IS NULL; every RESERVED slot points at
         SvcUnimplemented SPECIFICALLY; every INSTALLED slot points at the
         procedure this file says, resolved through the compiler's .sym map.

  E. THE VERSION GATE - the compiled probe is entered with a synthetic table
     at a chosen version, and must refuse an older one in a sentence
     carrying both versions and the code, run on a newer one, touch no slot
     at all when the MAJOR differs, and record its capability refusal on a
     board with a console and no framebuffer.

  F. THE RE-ENTRANCY WITNESS - a slot is re-entered part way through a call,
     exactly as an interrupt handler calling the same slot would, and the
     interrupted call must still come back with ITS OWN answer.

     THIS PART CHANGED MEANING ON ANVIL MAIN, and the change is recorded
     rather than hidden.  When this gate was written every procedure
     parameter was a static global the compiler emitted by name
     (`svcerrtext_code`), and the witness rewrote that global mid-call and
     REQUIRED the corruption, so that nobody concluded the constraint was
     theoretical.  Procedure locals and parameters now live in the
     invocation's frame (RaspberryPi4/Lib/mailbox.pi4's reentrancy note,
     2026-09-11), and the compiler emits no such global.  So the witness now
     asserts both halves of the new fact: the per-parameter global is GONE
     from the symbol map, and a genuinely nested call on the stack below
     the interrupted one leaves the interrupted call's answer intact.  The
     table still has no callbacks: shared globals such as the detail
     sentence are still shared, and this part says nothing about them.

--mutate
========
--mutate damages COPIES of the ABI sources and the probe (in a temporary
directory; the tree is never written) and requires each defect to be CAUGHT:

  null-slot              a reserved slot nulled after the fill.  D red.
  short-count            entry_count written one short.  D red.
  moved-slot             two GPIO slots swapped.  D red.
  seam-slots-swapped     the two module slots (14 and 15) swapped.  D red.
  minor-bump             abi_minor raised with no slot appended.  D red.
  collide-errs           #SVC_ENOCAP moved into the #HW_I2C_NACK collision.
                         A red.
  probe-veh-conditional  the probe's judged vehicle-link write made
                         conditional on a drawing property.  E red.
  probe-no-prefill       the probe's 'NOTWRIT!' pre-fill deleted.  E red.

WHY THE HARNESS RE-STATES WHAT IT CHECKS
========================================
The expected slot map below is written out here, by hand, from abi.pbi's
group table - not parsed out of BuildServiceTable.  A harness that read the
table it is testing against would agree with a wrong one.  Three independent
statements of the ABI - abi.pbi, pi4SvcProbe.pi4 and this file - and the
gate is green only when all three agree.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
import build_count  # noqa: E402

ABI = ROOT / "Anvil" / "Hal" / "abi.pbi"
ABI_VERSION = ROOT / "Anvil" / "Hal" / "abi_version.pbi"
SEAMS = ROOT / "Anvil" / "Hal" / "seams.pbi"
HAL = ROOT / "Anvil" / "Hal" / "hal.pbi"
PMFBOOT = ROOT / "Anvil" / "Core" / "pmfboot.pbi"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4SvcProbe.pi4"
BOARD = ROOT / "RaspberryPi4" / "Board" / "board.pi4"
PROOF = ROOT / "tools" / "pi4_svcprobe_proof.py"

CTX = {"compiler": None, "work": None}

# ---------------------------------------------------------------------
#  THE SOURCES AS TEXT.  --mutate substitutes a damaged copy here; nothing
#  in the tree is ever opened for writing.
# ---------------------------------------------------------------------
OVERRIDE: dict[pathlib.Path, str] = {}


def text(path: pathlib.Path) -> str:
    if path in OVERRIDE:
        return OVERRIDE[path]
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------
#  THE ABI, RESTATED.  From abi.pbi's group table and abi_version.pbi's
#  history, by hand.
# ---------------------------------------------------------------------
ABI_MAJOR = 1
# 2 on Anvil main: 1.1 filled core slots 14/15 (SvcSeamFill, SvcSeamGet) and
# 1.2 filled console slot 13 (SvcScreenCapture) - abi_version.pbi:16-57.
ABI_MINOR = 2
SLOT_COUNT = 184
HDR_BYTES = 16
MAGIC = 0x53564E41              # 'ANVS'

GROUPS = [
    (0,   "core",     16),
    (16,  "clock",     8),
    (24,  "console",  16),
    (40,  "touch",     8),
    (48,  "file",     16),
    (64,  "setting",   8),
    (72,  "net",      24),
    (96,  "usb",      12),
    (108, "gpio",      8),
    (116, "i2c",      12),
    (128, "spi",       8),
    (136, "uart",      8),
    (144, "veh",      12),
    (156, "gnss",     12),
    (168, "crypto",   16),
]

INSTALLED = {
    0: "SvcAbiMajor", 1: "SvcAbiMinor", 2: "SvcBoardId", 3: "SvcBoardName",
    4: "SvcCapGet", 5: "SvcRequireCap", 6: "SvcPet", 7: "SvcBootOk",
    8: "SvcReturn", 9: "SvcReboot", 10: "SvcMmuState", 11: "SvcUptimeUs",
    12: "SvcErrText", 13: "SvcErrDetail",
    # ABI 1.1: the module half of the table (seams.pbi #SVC_SEAM_SLOT_*).
    14: "SvcSeamFill", 15: "SvcSeamGet",

    16: "SvcTicks", 17: "SvcUtc", 18: "SvcClockProvenance",
    19: "SvcClockUncertaintyMs", 20: "SvcUtcLastSyncTicks",

    24: "SvcScreenWidth", 25: "SvcScreenHeight", 26: "SvcScreenTier",
    27: "SvcFrameBegin", 28: "SvcFrameEnd", 29: "SvcRect", 30: "SvcText",
    31: "SvcTextWidth", 32: "SvcClip", 33: "SvcLine", 34: "SvcFrameCostUs",
    35: "SvcBacklight", 36: "SvcTextHeight",
    # ABI 1.2: console slot 13.
    37: "SvcScreenCapture",

    40: "SvcTouchPoll", 41: "SvcTouchQueued", 42: "SvcTouchFlush",
    43: "SvcTouchMaxPoints",

    48: "SvcStorageUp", 49: "SvcFileOpen", 50: "SvcFileSize",
    51: "SvcFileReadAt", 52: "SvcFileClose", 53: "SvcFileWritable",
    54: "SvcFileWriteAll", 55: "SvcFileAppend", 56: "SvcFileLastError",
    57: "SvcFileErrText", 58: "SvcFileCanList", 59: "SvcDirOpen",
    60: "SvcDirNext", 61: "SvcDirClose",

    64: "SvcSettingGet", 65: "SvcSettingSet", 66: "SvcSettingSave",
    67: "SvcSettingDel",

    96: "SvcUsbEnumerate", 97: "SvcUsbDevCount", 98: "SvcUsbDevKind",
    99: "SvcUsbStorageReady", 100: "SvcUsbReadBlock", 101: "SvcUsbWriteBlock",

    108: "SvcGpioCount", 109: "SvcGpioModeGet", 110: "SvcGpioLevelGet",
    111: "SvcGpioPullGet", 112: "SvcGpioMode", 113: "SvcGpioWrite",

    116: "SvcI2cDefaultBus", 117: "SvcI2cUp", 118: "SvcI2cProbe",
    119: "SvcI2cRead", 120: "SvcI2cWrite", 121: "SvcI2cSetSpeed",
    122: "SvcI2cGetSpeed", 123: "SvcI2cPin",

    128: "SvcSpiUp", 129: "SvcSpiSetSpeed", 130: "SvcSpiGetSpeed",
    131: "SvcSpiXfer", 132: "SvcSpiPin",

    136: "SvcUartCount", 137: "SvcUartOpen", 138: "SvcUartRead",
    139: "SvcUartWrite", 140: "SvcUartRxOverrun", 141: "SvcUartClose",

    144: "SvcVehUp", 145: "SvcVehDown", 146: "SvcVehState",
    147: "SvcVehTransport", 148: "SvcVehPoll", 149: "SvcVehData",
    150: "SvcVehLastHeardMs", 151: "SvcVehLossState",
    152: "SvcVehEngineLostMs", 153: "SvcVehDiag", 154: "SvcVehUnitId",

    156: "SvcGnssUp", 157: "SvcGnssPoll", 158: "SvcGnssFix",
    159: "SvcGnssAgeMs", 160: "SvcGnssPpsTicks", 161: "SvcGnssSatsUsed",
    162: "SvcGnssErrText",

    168: "SvcSha256",
}

SVC_ERRS = {
    "#SVC_OK": 0, "#SVC_ENOSYS": -100, "#SVC_ENOCAP": -101,
    "#SVC_EARG": -102, "#SVC_EBUSY": -103, "#SVC_ETIMEOUT": -104,
    "#SVC_EIO": -105, "#SVC_EPERM": -106, "#SVC_EFLAG": -107,
    "#SVC_ESTATE": -108, "#SVC_EABI": -109,
}
SVC_RANGE_LO, SVC_RANGE_HI = -199, -100
HW_FLOOR = -99

# THE SENTINELS THAT ARE NOT ERROR CODES, by name.  #HW_TEMP_NONE is -273151
# millidegrees, below absolute zero on purpose.  Exempt from the floor and
# NOT from the range.
HW_VALUE_SENTINELS = {
    "#HW_TEMP_NONE",
}

# Capability ids.  Frozen; id 9 was _CAN and KEPT its number when it became
# _VEHLINK.  14 (reserved) and 15 were appended at 1.1 in seams.pbi.
SVCCAPS = {
    "#SVCCAP_STORAGE": 0, "#SVCCAP_NET": 1, "#SVCCAP_GPIO": 2,
    "#SVCCAP_I2C": 3, "#SVCCAP_MMC": 4, "#SVCCAP_USB": 5,
    "#SVCCAP_BOOT_EL1": 6, "#SVCCAP_TOUCH": 7, "#SVCCAP_GNSS": 8,
    "#SVCCAP_VEHLINK": 9, "#SVCCAP_SPI": 10, "#SVCCAP_UART": 11,
    "#SVCCAP_RTC": 12, "#SVCCAP_CONSOLE": 13, "#SVCCAP_PWM": 14,
    "#SVCCAP_THERMAL": 15, "#SVCCAP_MAX": 15,
}
SEAM_SLOTS = {"#SVC_SEAM_SLOT_FILL": 14, "#SVC_SEAM_SLOT_GET": 15,
              "#SVC_SEAM_HDR_BYTES": 16}

FORBIDDEN_IN_PROBE = [
    (r'XIncludeFile', "an include - the probe must reach nothing but the table"),
    (r'\bUart\w*\(', "a UART library call"),
    (r'\bDisplay\w*\(', "a display library call"),
    (r'\bMmu\w*\(', "an MMU library call"),
    (r'\bHw[A-Z]\w*\(', "a Hw* seam call - that is Anvil's side of the seam"),
    (r'\bBCM\d|\bbcm\d', "a chip part number"),
    (r'0x?FE2\d\d\d\d\d|\$FE[0-9A-F]{6}', "a peripheral register address"),
    (r'#CAP_', "a compile-time board capability - the payload cannot see those"),
]


def fail(problems, msg):
    problems.append(msg)


CONST_RE = re.compile(r'^\s*(#[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?\$?[0-9A-Fa-f]+)\s*(?:;.*)?$')


def read_consts(body: str) -> dict[str, int]:
    """A LINE-ORIENTED REGEX AND NOT AN EVALUATOR: a gate that could
    evaluate expressions could also evaluate a wrong one into the right
    answer."""
    out: dict[str, int] = {}
    for line in body.splitlines():
        m = CONST_RE.match(line)
        if not m:
            continue
        name, raw = m.group(1), m.group(2)
        neg = raw.startswith("-")
        if neg:
            raw = raw[1:]
        try:
            v = int(raw[1:], 16) if raw.startswith("$") else int(raw, 10)
        except ValueError:
            continue
        out[name] = -v if neg else v
    return out


def published() -> dict[str, int]:
    """abi_version.pbi, seams.pbi and abi.pbi together - the published ABI."""
    merged: dict[str, int] = {}
    for path in (ABI_VERSION, SEAMS, ABI):
        merged.update(read_consts(text(path)))
    return merged


# ---------------------------------------------------------------------
#  A. STATIC
# ---------------------------------------------------------------------
def check_static() -> list[str]:
    problems: list[str] = []
    abi = published()
    hal = read_consts(text(HAL))
    probe = read_consts(text(PROBE))

    for name, want in SVC_ERRS.items():
        got = abi.get(name)
        if got is None:
            fail(problems, f"{name} is not declared in the ABI files any more")
        elif got != want:
            fail(problems, f"{name} is {got} in abi.pbi, expected {want}")

    for name, v in abi.items():
        if name.startswith("#SVC_E"):
            if not (SVC_RANGE_LO <= v <= SVC_RANGE_HI):
                fail(problems, f"{name} = {v} is outside the reserved #SVC_* "
                               f"range {SVC_RANGE_LO}..{SVC_RANGE_HI}")
    for name, v in hal.items():
        if not name.startswith("#HW_"):
            continue
        if SVC_RANGE_LO <= v <= SVC_RANGE_HI:
            fail(problems, f"{name} = {v} in hal.pbi is INSIDE the reserved "
                           f"#SVC_* range {SVC_RANGE_LO}..{SVC_RANGE_HI}: a "
                           "re-exported seam slot answers both vocabularies "
                           "from one register, so this number now means two things")
        elif v < HW_FLOOR and name not in HW_VALUE_SENTINELS:
            fail(problems, f"{name} = {v} in hal.pbi is below the error-code "
                           f"floor {HW_FLOOR}. If it is not an error code but an "
                           "impossible VALUE, add it to HW_VALUE_SENTINELS by "
                           "name and say why")

    for name, want in SVCCAPS.items():
        got = abi.get(name)
        if got != want:
            fail(problems, f"{name} is {got} in seams.pbi, expected {want} "
                           "(these ids are frozen)")
    if "#SVCCAP_CAN" in abi:
        fail(problems, "#SVCCAP_CAN is back; id 9 is #SVCCAP_VEHLINK and the "
                       "CAN seam was removed")
    for name, want in SEAM_SLOTS.items():
        if abi.get(name) != want:
            fail(problems, f"{name} is {abi.get(name)} in seams.pbi, expected {want}")

    for k, want in (("#SVC_ABI_MAJOR", ABI_MAJOR), ("#SVC_ABI_MINOR", ABI_MINOR),
                    ("#SVC_SLOT_COUNT", SLOT_COUNT), ("#SVC_MAGIC", MAGIC)):
        if abi.get(k) != want:
            fail(problems, f"{k} is {abi.get(k)} in the ABI files, expected {want}")

    names = {"core": "#SVC_BASE_CORE", "clock": "#SVC_BASE_CLOCK",
             "console": "#SVC_BASE_CONSOLE", "touch": "#SVC_BASE_TOUCH",
             "file": "#SVC_BASE_FILE", "setting": "#SVC_BASE_SETTING",
             "net": "#SVC_BASE_NET", "usb": "#SVC_BASE_USB",
             "gpio": "#SVC_BASE_GPIO", "i2c": "#SVC_BASE_I2C",
             "spi": "#SVC_BASE_SPI", "uart": "#SVC_BASE_UART",
             "veh": "#SVC_BASE_VEH", "gnss": "#SVC_BASE_GNSS",
             "crypto": "#SVC_BASE_CRYPTO"}
    for base, g, _res in GROUPS:
        if abi.get(names[g]) != base:
            fail(problems, f"{names[g]} is {abi.get(names[g])}, expected {base}")

    # THE PAYLOAD'S RESTATEMENT.  A stale copy would call the wrong procedure
    # with the right arguments.
    for name, v in probe.items():
        if name in abi and abi[name] != v:
            fail(problems, f"pi4SvcProbe.pi4 restates {name} = {v} but the "
                           f"ABI files say {abi[name]}")
    for name, v in probe.items():
        if name.startswith("#SLOT_") and not (0 <= v < SLOT_COUNT):
            fail(problems, f"pi4SvcProbe.pi4's {name} = {v} is outside the "
                           f"table (0..{SLOT_COUNT - 1})")

    abi_txt = text(ABI)
    boot_txt = text(PMFBOOT)
    for key in ('"boot.fails"', '"boot.maxfails"'):
        if key not in abi_txt:
            fail(problems, f"abi.pbi no longer guards {key}")
        if key not in boot_txt:
            fail(problems, f"pmfboot.pbi no longer spells {key} the same way")

    # THE NEVER-WRITTEN STAMP, SPELLED THE SAME IN THREE PLACES: the probe
    # writes it, this gate reads it back, and tools/pi4_svcprobe_proof.py
    # reads it off the board.
    if probe.get("#SVCP_UNSET") != SVCP_UNSET:
        fail(problems, "the probe's #SVCP_UNSET is %s and this gate expects "
                       "0x%X. A word that was never written would stop being "
                       "reported as never written" % (probe.get("#SVCP_UNSET"), SVCP_UNSET))
    proof_txt = PROOF.read_text(encoding="utf-8") if PROOF.exists() else ""
    if ("SVCP_UNSET = 0x%X" % SVCP_UNSET) not in proof_txt:
        fail(problems, "tools/pi4_svcprobe_proof.py does not carry SVCP_UNSET = "
                       "0x%X, so the board proof would grade an unwritten word "
                       "as a wrong answer" % SVCP_UNSET)

    if "PmfCheckFlags" not in boot_txt:
        fail(problems, "pmfboot.pbi has no PmfCheckFlags - the ninth guard is gone")
    if "#PMF_FLAG_WANTS_SERVICES" not in boot_txt:
        fail(problems, "pmfboot.pbi does not declare #PMF_FLAG_WANTS_SERVICES")
    return problems


# ---------------------------------------------------------------------
#  B. SOURCE HYGIENE
# ---------------------------------------------------------------------
def check_probe_hygiene() -> list[str]:
    problems: list[str] = []
    for n, raw in enumerate(text(PROBE).splitlines(), 1):
        line = raw.split(";", 1)[0]
        if not line.strip():
            continue
        for pat, why in FORBIDDEN_IN_PROBE:
            if re.search(pat, line):
                fail(problems, f"pi4SvcProbe.pi4:{n} contains {why}: {line.strip()[:70]}")
    return problems


# ---------------------------------------------------------------------
#  BUILDING
# ---------------------------------------------------------------------
PMF_FLAG_RETURNS = 1
PMF_FLAG_WANTS_DTB = 2
PMF_FLAG_WANTS_SERVICES = 4


def compile_to(source: pathlib.Path, out: pathlib.Path, extra: list[str]) -> dict[str, int]:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [CTX["compiler"], "--compile", str(source), "-t", "pi4", "-s",
           "-o", str(out)] + extra
    # PIN THE TREE.  Without PMF_ROOT the compiler's include search can reach
    # a sibling checkout and build a different program under the same name.
    r = subprocess.run(cmd, cwd=ROOT, text=True,
                       env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not out.exists():
        raise SystemExit("The build of %s failed, so nothing about it was "
                         "tested. The compiler said:\n%s" % (source.name, r.stdout[-4000:]))
    syms: dict[str, int] = {}
    symfile = pathlib.Path(str(out) + ".sym")
    if symfile.exists():
        for line in symfile.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                try:
                    syms[k.strip()] = int(v.strip(), 0)
                except ValueError:
                    pass
    return syms


def materialise(path: pathlib.Path, into: pathlib.Path) -> pathlib.Path:
    """The file to hand the compiler: the tree's own, or a copy of an
    overridden source with overridden includes pointed at their copies."""
    body = text(path)
    into.mkdir(parents=True, exist_ok=True)
    for other, obody in OVERRIDE.items():
        rel = other.relative_to(ROOT).as_posix()
        marker = 'XIncludeFile "%s"' % rel
        if marker in body:
            copy = into / other.name
            copy.write_text(obody, encoding="utf-8")
            body = body.replace(marker, 'XIncludeFile "%s"' % copy.resolve().as_posix())
    if body == path.read_text(encoding="utf-8", errors="replace") and path not in OVERRIDE:
        return path
    into.mkdir(parents=True, exist_ok=True)
    dst = into / path.name
    dst.write_text(body, encoding="utf-8")
    return dst


# ---------------------------------------------------------------------
#  C. THE CONTAINER FLAG
# ---------------------------------------------------------------------
def check_container() -> list[str]:
    problems: list[str] = []
    work = CTX["work"] / "container"
    src = materialise(PROBE, work / "src")
    out = work / "svcprobe.img"
    compile_to(src, out, ["--load-addr", "0x400000", "--stack-addr", "0x3000000",
                          "--entry-returns", "--wants-services"])
    pmf = pathlib.Path(str(out) + ".pmf")
    if not pmf.exists():
        fail(problems, "the compiler wrote no .pmf container beside the image")
        return problems
    b = pmf.read_bytes()
    if b[:8] != b"PMFBOOT\x00":
        fail(problems, "the container magic is wrong")
    version, hdrlen = struct.unpack_from("<II", b, 8)
    # pmfboot.pbi's field table: version 1 is 96 bytes, version 2 is 128.
    if (version, hdrlen) not in ((1, 96), (2, 128)):
        fail(problems, f"the container declares version {version} with a "
                       f"{hdrlen}-byte header; pmfboot.pbi reads 1/96 and 2/128")
    flags, = struct.unpack_from("<I", b, 56)
    if not flags & PMF_FLAG_WANTS_SERVICES:
        fail(problems, f"--wants-services did not set bit 2; flags = {flags}")
    if not flags & PMF_FLAG_RETURNS:
        fail(problems, f"--entry-returns did not set bit 0; flags = {flags}")
    if flags & PMF_FLAG_WANTS_DTB:
        fail(problems, f"bit 1 is set as well as bit 2; flags = {flags}. That "
                       "pair is what the ninth guard refuses, and the compiler "
                       "must never emit it")
    if version == 2:
        arch, target = struct.unpack_from("<II", b, 96)
        if (arch, target) != (1, 2711):
            fail(problems, f"the version-2 container names architecture {arch} "
                           f"and target {target}; a -t pi4 build is AArch64 (1) "
                           "for BCM2711 (2711)")

    plain = work / "svcprobe_plain.img"
    compile_to(src, plain, ["--load-addr", "0x400000", "--stack-addr", "0x3000000",
                            "--entry-returns"])
    if out.read_bytes() != plain.read_bytes():
        fail(problems, "--wants-services changed the emitted image, not just the "
                       "container header")
    return problems


# ---------------------------------------------------------------------
#  D. DYNAMIC - build the real table and walk it
# ---------------------------------------------------------------------
UART_DR = 0xFE201000
UART_FR = 0xFE201018
FR_IDLE = 0x90
STEP_LIMIT = 400_000_000

# THE MONITOR'S LINK ADDRESS, declared by board.pi4's LoadAddress ($200000).
# Stated, not parsed, so a differently-linked image is noticed.
ANVIL_LOAD = 0x200000


def code_addr(syms: dict[str, int], name: str):
    """CODE SYMBOLS ARE IMAGE-RELATIVE AND GLOBALS ARE ABSOLUTE.  Getting
    that backwards reads eight bytes two megabytes past the array."""
    v = syms.get(name.lower())
    if v is None:
        return None
    return v + ANVIL_LOAD


# THE MONITOR IS BUILT ONCE PER DISTINCT SET OF SOURCES and shared by D and
# F, keyed on the overridden texts, so a mutant always gets its own build.
_ANVIL: dict = {}


def anvil_image() -> tuple[pathlib.Path, dict[str, int]]:
    key = tuple(sorted((str(p), hash(t)) for p, t in OVERRIDE.items()))
    if key not in _ANVIL:
        work = CTX["work"] / ("anvil_%d" % len(_ANVIL))
        src = materialise(BOARD, work / "src")
        out = work / "anvil.img"
        syms = compile_to(src, out, [])
        # A whole board file was compiled and the image exists: count it.
        counted = build_count.record_build(src, "pi4", out, by="tools/a64/a64_abi_check.py",
                                           compiler=CTX["compiler"])
        print("     build count: %s" % counted.message)
        _ANVIL[key] = (out, syms)
    return _ANVIL[key]


def fresh_monitor(uart: bytearray | None = None) -> tuple[A64, dict[str, int]]:
    out, syms = anvil_image()
    blob = out.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[ANVIL_LOAD + i] = b
    attach_symbols(cpu, out, ANVIL_LOAD)

    def ld(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if addr >= 0xFE000000:
            return FR_IDLE if addr == UART_FR else 0
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def st(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        if addr >= 0xFE000000:
            if addr == UART_DR and uart is not None:
                uart.append(value & 0xFF)
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = ld
    cpu.store = st
    return cpu, syms


def run_build_table() -> tuple[dict[str, int], dict[int, int], bytes]:
    """Call BuildServiceTable() directly - not Main(), which brings up a
    clock, a mailbox, a display and a USB host none of which the table
    depends on - and read the table back."""
    cpu, syms = fresh_monitor()
    entry = syms.get("global_gsvctab")
    build_sym = code_addr(syms, "BuildServiceTable")
    if entry is None or build_sym is None:
        raise SystemExit("The symbol map has no %s, so the gate cannot find the table."
                         % ("gSvcTab" if entry is None else "BuildServiceTable"))
    lr = 0xDEADBEE0
    cpu.pc = build_sym
    cpu.sp = 0x00100000
    cpu.x[30] = lr
    steps = 0
    while steps < STEP_LIMIT:
        if cpu.pc == lr:
            break
        cpu.step()
        steps += 1
    else:
        raise SystemExit("BuildServiceTable never returned.")

    def word(a: int) -> int:
        return sum(cpu.memory.get(a + i, 0) << (8 * i) for i in range(8))

    header = bytes(cpu.memory.get(entry + i, 0) for i in range(16))
    slots = {i: word(entry + HDR_BYTES + i * 8) for i in range(SLOT_COUNT)}
    return syms, slots, header


def check_dynamic() -> list[str]:
    problems: list[str] = []
    syms, slots, header = run_build_table()

    magic, major, minor, count = struct.unpack("<IIII", header)
    if magic != MAGIC:
        fail(problems, f"header magic is 0x{magic:08X}, expected 0x{MAGIC:08X}")
    if major != ABI_MAJOR:
        fail(problems, f"header abi_major is {major}, expected {ABI_MAJOR}")
    if minor != ABI_MINOR:
        fail(problems, f"header abi_minor is {minor}, expected {ABI_MINOR}")
    if count != SLOT_COUNT:
        fail(problems, f"header entry_count is {count}, expected {SLOT_COUNT}")

    unimpl = code_addr(syms, "SvcUnimplemented")
    if unimpl is None:
        fail(problems, "SvcUnimplemented is not in the symbol map")
        return problems

    nulls = [i for i, v in slots.items() if v == 0]
    if nulls:
        fail(problems, f"{len(nulls)} slot(s) are NULL, first at {nulls[0]}. A "
                       "null slot is a branch to address 0 the first time an "
                       "over-new payload reaches for it.")

    # The net group is deliberately empty in this build and the crypto group
    # is one slot; both are stated in abi.pbi with their reasons.
    expected_unimpl = set(range(SLOT_COUNT)) - set(INSTALLED)
    for i in sorted(expected_unimpl):
        if slots[i] != unimpl:
            named = [k for k, v in syms.items() if v + ANVIL_LOAD == slots[i]]
            fail(problems, f"reserved slot {i} points at {named or hex(slots[i])}, "
                           "not SvcUnimplemented. A slot filled with the wrong "
                           "procedure passes a null check and returns nonsense.")
    for i, name in sorted(INSTALLED.items()):
        want = code_addr(syms, name)
        if want is None:
            fail(problems, f"{name} (slot {i}) is not in the symbol map")
            continue
        if slots[i] != want:
            named = [k for k, v in syms.items() if v + ANVIL_LOAD == slots[i]]
            fail(problems, f"slot {i} should be {name} but holds {named or hex(slots[i])}")
    return problems


# ---------------------------------------------------------------------
#  E. THE VERSION GATE - THE PAYLOAD'S OWN REFUSAL, RUN FOR REAL
#
#  A synthetic service table at a chosen version, because Anvil's own table
#  is at one version and a gate that could only test that version could not
#  test the refusal at all.  The newer-table case is the one that tells a
#  correct gate from one that refuses everything.
# ---------------------------------------------------------------------
SYNTH_TABLE = 0x00A00000
SYNTH_STUB = 0x00B00000
PROBE_LOAD = 0x00400000
PROBE_STACK = 0x03000000

# From the probe's own header, stated rather than parsed.
PROBE_RESULT = 0x01400000
PROBE_SENTENCE = 0x01401000
R_ABIRC = 8
R_ABITEXT = 9
R_FRAMERC = 34
R_VEHUP = 41
R_WORDS = 56
R_DONE = 55
SVCP_DONE = 0x454E4F44
SVCP_UNSET = 0x2154495257544F4E   # 'NOTWRIT!' - the probe's own stamp
SVC_EABI = -109
SVC_EIO = -105
SLOT_CAPGET = 4
SLOT_FRAMEBEGIN = 27

# WHAT THE RESULT BLOCK HOLDS BEFORE THE PROBE RUNS, AND WHY IT IS NOT ZERO.
# On the board the block is DRAM nothing clears; emulated memory starts at
# zero, and zero is a plausible answer.  Poisoning the block first makes an
# unwritten word visible here the way it is on silicon.
PROBE_POISON_BASE = 0x00D1ED0000000000


def probe_poison(index: int) -> int:
    return PROBE_POISON_BASE | index


# mov x0, #0 ; ret
STUB_CODE = struct.pack("<II", 0xD2800000, 0xD65F03C0)
# THE BOARD WITH A CONSOLE AND NO FRAMEBUFFER.
#   capget:     cmp x0, #13 ; b.ne +12 ; mov x0, #1 ; ret ; mov x0, #0 ; ret
#   framebegin: movn x0, #104 ; ret        (that is -105)
STUB_CAPGET_CONSOLE = struct.pack(
    "<IIIIII", 0xF100341F, 0x54000061, 0xD2800020, 0xD65F03C0,
    0xD2800000, 0xD65F03C0)
STUB_FRAMEBEGIN_EIO = struct.pack("<II", 0x92800D00, 0xD65F03C0)


def build_probe_needing(major: int, minor: int, tag: str) -> pathlib.Path:
    """The probe, compiled with its REQUIRED version set to major.minor."""
    src = text(PROBE)
    for find, repl in (("#SVCP_NEED_MAJOR = 1", "#SVCP_NEED_MAJOR = %d" % major),
                       ("#SVCP_NEED_MINOR = 0", "#SVCP_NEED_MINOR = %d" % minor)):
        if find not in src:
            raise SystemExit("pi4SvcProbe.pi4 no longer declares %s, so the version "
                             "gate cannot be built at another version and this part "
                             "of the gate proves nothing" % find.split(" =")[0])
        src = src.replace(find, repl, 1)
    work = CTX["work"] / "version"
    work.mkdir(parents=True, exist_ok=True)
    key = "%x" % (hash(src) & 0xFFFFFFFF)
    srcfile = work / ("probe_%s_%s.pi4" % (tag, key))
    srcfile.write_text(src, encoding="utf-8")
    img = work / ("probe_%s_%s.img" % (tag, key))
    compile_to(srcfile, img, ["--load-addr", "0x400000", "--stack-addr", "0x3000000",
                              "--entry-returns", "--wants-services"])
    return img


def run_probe(img: pathlib.Path, tab_major: int, tab_minor: int,
              slots_poisoned: bool, console_no_fb: bool = False) -> dict:
    blob = img.read_bytes()
    cpu = A64()
    mem = cpu.memory
    for i, b in enumerate(blob):
        mem[PROBE_LOAD + i] = b
    attach_symbols(cpu, img, PROBE_LOAD)

    def ld(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def st(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = ld
    cpu.store = st

    for i, b in enumerate(STUB_CODE):
        mem[SYNTH_STUB + i] = b
    capget_stub = SYNTH_STUB + 0x1000
    framebegin_stub = SYNTH_STUB + 0x2000
    for i, b in enumerate(STUB_CAPGET_CONSOLE):
        mem[capget_stub + i] = b
    for i, b in enumerate(STUB_FRAMEBEGIN_EIO):
        mem[framebegin_stub + i] = b
    for i, b in enumerate(struct.pack("<IIII", MAGIC, tab_major, tab_minor, SLOT_COUNT)):
        mem[SYNTH_TABLE + i] = b
    target = 0 if slots_poisoned else SYNTH_STUB
    for slot in range(SLOT_COUNT):
        at = target
        if console_no_fb and not slots_poisoned:
            if slot == SLOT_CAPGET:
                at = capget_stub
            elif slot == SLOT_FRAMEBEGIN:
                at = framebegin_stub
        for i, b in enumerate(struct.pack("<Q", at)):
            mem[SYNTH_TABLE + HDR_BYTES + slot * 8 + i] = b

    for idx in range(R_WORDS):
        for i, b in enumerate(struct.pack("<Q", probe_poison(idx))):
            mem[PROBE_RESULT + idx * 8 + i] = b

    lr = 0xDEADBEE0
    cpu.pc = PROBE_LOAD
    cpu.sp = PROBE_STACK
    cpu.x[0] = SYNTH_TABLE
    cpu.x[30] = lr
    steps = 0
    while steps < STEP_LIMIT:
        if cpu.pc == lr:
            break
        cpu.step()
        steps += 1
    else:
        raise SystemExit("The probe never returned.")

    def word(a: int) -> int:
        return sum(mem.get(a + i, 0) << (8 * i) for i in range(8))

    def signed(a: int) -> int:
        v = word(a)
        return v - (1 << 64) if v >> 63 else v

    sentence = bytearray()
    a = PROBE_SENTENCE
    while mem.get(a, 0) and len(sentence) < 600:
        sentence.append(mem[a])
        a += 1

    def unwritten(index: int) -> bool:
        """Never written by the run: either the probe's own stamp, or the
        poison showing through where the stamp is missing."""
        v = word(PROBE_RESULT + index * 8)
        return v == SVCP_UNSET or v == probe_poison(index)

    return {"x0": cpu.x[0],
            "abirc": signed(PROBE_RESULT + R_ABIRC * 8),
            "abitext": word(PROBE_RESULT + R_ABITEXT * 8),
            "framerc": signed(PROBE_RESULT + R_FRAMERC * 8),
            "vehup": signed(PROBE_RESULT + R_VEHUP * 8),
            "vehup_unwritten": unwritten(R_VEHUP),
            "framerc_unwritten": unwritten(R_FRAMERC),
            "abitext_stamped": word(PROBE_RESULT + R_ABITEXT * 8) == SVCP_UNSET,
            "done": word(PROBE_RESULT + R_DONE * 8),
            "sentence": sentence.decode("latin-1")}


def check_version_gate() -> list[str]:
    problems: list[str] = []
    probe = read_consts(text(PROBE))
    need_major = probe.get("#SVCP_NEED_MAJOR", 1)
    need_minor = probe.get("#SVCP_NEED_MINOR", 0)
    here = "%d.%d" % (ABI_MAJOR, ABI_MINOR)

    # 1. THE MATCHING CASE: the probe as committed on the table this monitor
    #    publishes.  Nothing is refused and the run completes.
    same = build_probe_needing(need_major, need_minor, "same")
    r = run_probe(same, ABI_MAJOR, ABI_MINOR, slots_poisoned=False)
    if r["abirc"] != 0:
        fail(problems, "a payload needing %d.%d refused a %s table at code %d"
                       % (need_major, need_minor, here, r["abirc"]))
    if r["done"] != SVCP_DONE:
        fail(problems, "the matching run did not stamp DONE")

    # 2. A NEWER TABLE IS NOT AN ERROR.
    newer = "%d.%d" % (ABI_MAJOR, ABI_MINOR + 9)
    r = run_probe(same, ABI_MAJOR, ABI_MINOR + 9, slots_poisoned=False)
    if r["abirc"] != 0:
        fail(problems, "a payload needing %d.%d refused a NEWER %s table at code "
                       "%d. A minor bump only appends" % (need_major, need_minor, newer, r["abirc"]))

    # 3. MINOR OLDER THAN THE PAYLOAD NEEDS.  Refuse, with both numbers.
    wants = "%d.%d" % (ABI_MAJOR, ABI_MINOR + 4)
    need_newer = build_probe_needing(ABI_MAJOR, ABI_MINOR + 4, "minor")
    r = run_probe(need_newer, ABI_MAJOR, ABI_MINOR, slots_poisoned=False)
    if r["abirc"] != SVC_EABI:
        fail(problems, "a payload needing %s ran on a %s table instead of "
                       "refusing (code %d, expected %d)" % (wants, here, r["abirc"], SVC_EABI))
    if r["x0"] == 0:
        fail(problems, "the minor-older refusal returned a failure count of 0")
    for want in (here, wants, "-109", "SVC_EABI"):
        if want not in r["sentence"]:
            fail(problems, "the minor-older refusal does not say %r. It says: %r"
                           % (want, r["sentence"][:200]))

    # 4. MAJOR DIFFERENT.  Refuse WITHOUT CALLING A SLOT - every slot holds 0.
    other = "%d.%d" % (ABI_MAJOR + 1, ABI_MINOR)
    need_major_img = build_probe_needing(ABI_MAJOR + 1, ABI_MINOR, "major")
    r = run_probe(need_major_img, ABI_MAJOR, ABI_MINOR, slots_poisoned=True)
    if r["abirc"] != SVC_EABI:
        fail(problems, "a payload built for major %d ran on a major %d table "
                       "instead of refusing (code %d, expected %d)"
                       % (ABI_MAJOR + 1, ABI_MAJOR, r["abirc"], SVC_EABI))
    if r["x0"] == 0:
        fail(problems, "the major-mismatch refusal returned a failure count of 0")
    for want in (here, other, "-109", "SVC_EABI"):
        if want not in r["sentence"]:
            fail(problems, "the major-mismatch refusal does not say %r. It says: %r"
                           % (want, r["sentence"][:200]))
    if r["abitext"] != PROBE_SENTENCE:
        fail(problems, "the major-mismatch run did not record where it wrote its sentence")

    # 5. THE BOARD WITH A CONSOLE AND NO FRAMEBUFFER.  What is asserted is
    #    that the judged word was WRITTEN, not what it holds.
    r = run_probe(same, ABI_MAJOR, ABI_MINOR, slots_poisoned=False, console_no_fb=True)
    if r["done"] != SVCP_DONE:
        fail(problems, "the console-without-framebuffer run did not stamp DONE")
    if r["framerc_unwritten"] or r["framerc"] != SVC_EIO:
        fail(problems, "this case is meant to enter the console path and be "
                       "refused a frame at %d, and frame_rc came back as %s"
                       % (SVC_EIO, "never written" if r["framerc_unwritten"] else r["framerc"]))
    if r["vehup_unwritten"]:
        fail(problems, "veh_up was NEVER WRITTEN on a board that has a console "
                       "and no framebuffer. The judged refusal is being taken "
                       "inside the drawing block; take it unconditionally")

    # 6. THE PRE-FILL IS THERE AND IT RAN.
    r = run_probe(same, ABI_MAJOR, ABI_MINOR, slots_poisoned=False)
    if not r["abitext_stamped"]:
        fail(problems, "a word this run never writes does not hold the 'NOTWRIT!' "
                       "stamp, so the probe is not stamping its result block "
                       "before it runs")
    return problems


# ---------------------------------------------------------------------
#  F. THE RE-ENTRANCY WITNESS
# ---------------------------------------------------------------------
WITNESS_CODE = -101             # #SVC_ENOCAP, what the interrupted call asks
WITNESS_INTRUDER = -106         # #SVC_EPERM, what the nested call asks
WITNESS_INTERPOSE_AT = 4        # instructions into the call - past the prologue
NESTED_LR = 0xDEADBEF0


def cstring(cpu: A64, a: int) -> str:
    out = bytearray()
    while cpu.memory.get(a, 0) and len(out) < 400:
        out.append(cpu.memory[a])
        a += 1
    return out.decode("latin-1")


def call_svc_errtext(cpu: A64, syms: dict[str, int], code: int, nested: int | None):
    """SvcErrText(code), optionally with a NESTED SvcErrText(nested) run part
    way through it, the way an interrupt handler would run it: every
    register saved, the nested call on the stack below the interrupted one,
    every register restored.  Returns (outer sentence, nested sentence)."""
    entry = code_addr(syms, "SvcErrText")
    if entry is None:
        raise SystemExit("The symbol map has no SvcErrText, so the witness cannot run.")
    lr = 0xDEADBEE0
    cpu.pc = entry
    cpu.sp = 0x00100000
    cpu.x[30] = lr
    cpu.x[0] = code & ((1 << 64) - 1)
    nested_text = None
    steps = 0
    while steps < STEP_LIMIT:
        if cpu.pc == lr:
            break
        if nested is not None and steps == WITNESS_INTERPOSE_AT:
            saved = {k: (list(v) if isinstance(v, list) else v)
                     for k, v in vars(cpu).items()
                     if k != "memory" and not callable(v)}
            cpu.sp = ((cpu.sp - 0x200) // 16) * 16
            cpu.x[0] = nested & ((1 << 64) - 1)
            cpu.x[30] = NESTED_LR
            cpu.pc = entry
            inner = 0
            while cpu.pc != NESTED_LR:
                cpu.step()
                inner += 1
                if inner > STEP_LIMIT:
                    raise SystemExit("The nested SvcErrText never returned.")
            nested_text = cstring(cpu, cpu.x[0])
            for k, v in saved.items():
                setattr(cpu, k, list(v) if isinstance(v, list) else v)
        cpu.step()
        steps += 1
    else:
        raise SystemExit("SvcErrText never returned.")
    return cstring(cpu, cpu.x[0]), nested_text


def check_reentrancy_witness() -> list[str]:
    problems: list[str] = []
    cpu, syms = fresh_monitor()
    clean, _ = call_svc_errtext(cpu, syms, WITNESS_CODE, None)
    if "-101" not in clean or "SVC_ENOCAP" not in clean:
        fail(problems, "the CLEAN call to SvcErrText(-101) did not come back with "
                       "the -101 sentence, so this witness is not reaching the "
                       "procedure at all. It said: %r" % clean[:160])
        return problems

    # THE OLD MECHANISM IS GONE: no per-parameter global in the symbol map.
    static_params = sorted(k for k in syms if k.startswith("svcerrtext_"))
    if static_params:
        fail(problems, "the symbol map carries %s, a static global for "
                       "SvcErrText's parameter. Parameters are meant to live in "
                       "the invocation's frame on Anvil main; a static parameter "
                       "is back, and with it the corruption an interrupt handler "
                       "calling a slot would cause" % static_params)

    cpu, syms = fresh_monitor()
    outer, inner = call_svc_errtext(cpu, syms, WITNESS_CODE, WITNESS_INTRUDER)
    print("     clean        SvcErrText(%d) -> %r" % (WITNESS_CODE, clean[:72]))
    print("     nested       SvcErrText(%d) -> %r" % (WITNESS_INTRUDER, (inner or "")[:72]))
    print("     interrupted  SvcErrText(%d) -> %r" % (WITNESS_CODE, outer[:72]))
    if inner is None or "-106" not in inner:
        fail(problems, "the nested call did not return the -106 sentence, so the "
                       "witness never re-entered the slot and proves nothing. It "
                       "said: %r" % (inner or "")[:160])
    elif outer != clean:
        fail(problems, "THE INTERRUPTED CALL CAME BACK WRONG. SvcErrText(%d) "
                       "returned %r after a nested call ran on the stack below "
                       "it; its parameter did not survive re-entry"
                       % (WITNESS_CODE, outer[:120]))
    return problems


# ---------------------------------------------------------------------
#  --mutate
# ---------------------------------------------------------------------
MUTANTS = {
    "null-slot": (
        # ONE reserved slot nulled after the fill - slot 155, the vehicle
        # link block's spare - so the ONLY thing that can see it is the null
        # walk (the symbol and every other slot stay as they were).
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH + 10] = @SvcVehUnitId",
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH + 10] = @SvcVehUnitId\n"
        "  gSvcTab[#SVC_HDR_WORDS + 155] = 0",
        "dynamic", ABI,
    ),
    "short-count": (
        "  gSvcTab[1] = #SVC_ABI_MINOR | (#SVC_SLOT_COUNT << 32)",
        "  gSvcTab[1] = #SVC_ABI_MINOR | ((#SVC_SLOT_COUNT - 1) << 32)",
        "dynamic", ABI,
    ),
    "moved-slot": (
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 0] = @SvcGpioCount\n"
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 1] = @SvcGpioModeGet",
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 0] = @SvcGpioModeGet\n"
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 1] = @SvcGpioCount",
        "dynamic", ABI,
    ),
    "seam-slots-swapped": (
        # The two slots a MODULE finds by number.  A module calling the fill
        # slot would call the getter with a function pointer as its index.
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE + #SVC_SEAM_SLOT_FILL] = @SvcSeamFill\n"
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE + #SVC_SEAM_SLOT_GET]  = @SvcSeamGet",
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE + #SVC_SEAM_SLOT_FILL] = @SvcSeamGet\n"
        "  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE + #SVC_SEAM_SLOT_GET]  = @SvcSeamFill",
        "dynamic", ABI,
    ),
    "minor-bump": (
        # abi_minor raised with no slot appended.  The minor lives in
        # abi_version.pbi on Anvil main.
        "#SVC_ABI_MINOR   = 2",
        "#SVC_ABI_MINOR   = 3",
        "dynamic", ABI_VERSION,
    ),
    "collide-errs": (
        "#SVC_ENOCAP    = -101",
        "#SVC_ENOCAP    = -2",
        "static", ABI,
    ),
    "probe-veh-conditional": (
        # THE WRITE OF A JUDGED WORD MADE CONDITIONAL ON A DRAWING PROPERTY.
        # Case 5 of part E is the only thing that enters the console path.
        "  vrc = svc_vehup()\n  Put(#R_VEHUP, vrc)",
        "  vrc = svc_vehup()\n  If svc_scrw() > 0\n    Put(#R_VEHUP, vrc)\n  EndIf",
        "version", PROBE,
    ),
    "probe-no-prefill": (
        "  i = 0\n  While i < #R_WORDS\n    Put(i, #SVCP_UNSET)\n    i = i + 1\n  Wend",
        "  i = 0",
        "version", PROBE,
    ),
}


def mutate() -> int:
    parts = {"static": check_static, "dynamic": check_dynamic,
             "version": check_version_gate}
    failures = 0
    for name, (find, repl, which, path) in MUTANTS.items():
        print(f"\n=== mutant: {name} (part {which} must go RED) ===")
        original = path.read_text(encoding="utf-8")
        if original.count(find) != 1:
            print(f"  !! the mutation site for {name} occurs {original.count(find)} "
                  f"times in {path.name}, not once; this mutant proves nothing and "
                  "the gate is ABSTAINING on it")
            failures += 1
            continue
        OVERRIDE.clear()
        OVERRIDE[path] = original.replace(find, repl, 1)
        try:
            probs = parts[which]()
        except (SystemExit, RuntimeError) as e:
            print(f"  caught: the mutant did not run cleanly ({e})")
            continue
        finally:
            OVERRIDE.clear()
        if not probs:
            print(f"  !! NOT CAUGHT - part {which} still reported clean with {name} "
                  "applied. The check this mutant removes is not doing anything.")
            failures += 1
        else:
            print(f"  caught: {len(probs)} problem(s), first: {probs[0][:110]}")
    print("\nNo tracked file was opened for writing; every mutant was a copy in a "
          "temporary directory.")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge compiler (default: $PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true",
                    help="damage copies of the ABI sources and the probe, and "
                         "require each defect to be caught")
    args = ap.parse_args()
    if not args.compiler:
        raise SystemExit("No compiler was named. Pass --compiler with the path "
                         "to PureMetalForge.exe, or set PMF_COMPILER.")
    if not pathlib.Path(args.compiler).is_file():
        raise SystemExit(f"The compiler {args.compiler} does not exist, so "
                         "nothing can be built.")
    CTX["compiler"] = str(pathlib.Path(args.compiler).resolve())

    with tempfile.TemporaryDirectory(prefix="anvil-abicheck-") as td:
        CTX["work"] = pathlib.Path(td)
        if args.mutate:
            bad = mutate()
            print()
            if bad:
                print(f"RESULT: RED ({bad} of {len(MUTANTS)} mutants not caught)")
                return 1
            print(f"RESULT: GREEN - all {len(MUTANTS)} damaged ABIs were caught")
            return 0

        total = 0
        parts = (("A  static - the constants agree", check_static),
                 ("B  hygiene - the probe names no chip", check_probe_hygiene),
                 ("C  container - --wants-services sets bit 2", check_container),
                 ("D  dynamic - the built table is correct", check_dynamic),
                 ("E  version gate - the payload refuses an older table", check_version_gate),
                 ("F  re-entrancy - an interrupted slot keeps its own answer",
                  check_reentrancy_witness))
        for title, fn in parts:
            print("=" * 70)
            print(title)
            print("=" * 70)
            probs = fn()
            if probs:
                for p in probs:
                    print(f"  !! {p}")
                print(f"  {title[0]}: RED ({len(probs)})")
                total += len(probs)
            else:
                print(f"  {title[0]}: GREEN")
            print()

    if total:
        print(f"RESULT: RED ({total} problem(s))")
        return 1
    print(f"RESULT: GREEN - {len(parts)} of {len(parts)}")
    print("  the constants agree across abi_version.pbi, seams.pbi, abi.pbi,")
    print("  hal.pbi, pmfboot.pbi and the probe;")
    print("  the reference payload names no chip;")
    print("  --wants-services sets bit 2 and changes nothing else;")
    print(f"  all {SLOT_COUNT} slots are non-null and hold what the map says;")
    print("  the payload refuses an older table in a sentence carrying both")
    print("  versions and the code, runs on a newer one, touches no slot when the")
    print("  MAJOR differs, and records its refusal on a console without a")
    print("  framebuffer;")
    print("  and a slot re-entered mid-call leaves the interrupted call's answer intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
