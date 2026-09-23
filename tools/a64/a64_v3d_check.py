#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/v3d.pi4 - stage 0 of the V3D bring-up.

=====================================================================
 READ THIS BEFORE TRUSTING A GREEN RUN FROM THIS FILE.
=====================================================================

Four times in one week a gate in this directory passed on broken
source because its model was more forgiving than the part.  The worst
of them, a64_sdio_check.py, waved through a payload that wedged the
board dead, because its memory was a Python dict of bytes that did not
care about alignment.  So this file opens with what it CANNOT do,
before anything it can.

WHAT THIS GATE CANNOT DO

  1. IT CANNOT SAY THE GPU WILL ANSWER.  There is no V3D in
     a64_interp.py and there is no V3D anywhere on this machine.  The
     hub, core, PM and ASB models below are written HERE, by hand,
     from the same four source files v3d.pi4 was written from.  When
     the library and the model agree about what a register does, that
     agreement means only that one file was read the same way
     twice.  The IDENT value this gate hands back is a value this file
     chose.  ONLY THE BOARD CAN SAY WHAT $FEC0000C READS.

  2. IT CANNOT VALIDATE THE POWER-UP ORDER AGAINST SILICON.  The model
     makes the hub read zeros until the reset is deasserted and both
     ASB bridges are enabled.  THAT IS AN ASSUMPTION, not a citation -
     nothing consulted says what a V3D in reset returns.  It is a
     deliberately STRICT assumption, so the gate demands the whole
     sequence; if the board turns out to answer IDENT before any of it
     (which is one of the outcomes pi4V3dIdent is built to detect),
     then this model was wrong in the safe direction and should be
     corrected from the bench log, not the other way round.

  3. IT CANNOT REPRODUCE A BUS LOCKUP, A HUNG BRIDGE THAT NEVER
     TIMES OUT, OR A RESET OF THE SoC.  It models the PM password by
     DISCARDING an unpassworded write, which is what the hardware
     does, and it refuses a write to PM_RSTC or PM_WDOG by name - but
     a refusal in Python is a message and on the board it is a reboot.

  4. NO PART OF THIS GATE TOUCHES A SERIAL PORT OR THE BOARD.

  5. IT CANNOT SAY THE TILING MODEL IS RIGHT.  Stage 1 below checks
     that the library asks the TFU for a LINEARTILE conversion and
     that the bytes come back where the LINEARTILE layout says.  Both
     the probe's expectation and this file's engine model are
     TRANSCRIPTIONS of the same file, Mesa's v3d_tiling.c.
     They were written independently, in different languages, and
     agreeing means two readings of one document agree.  It does not
     mean the document describes this silicon.  Only the board can say
     that, and the probe is built so that the board CAN say it - the
     bytes are compared on the CPU, not a status bit.

  6. IT CANNOT CATCH A CACHE COHERENCY BUG.  The model's memory is a
     flat dictionary of bytes.  There are no caches in it, so THIS
     GATE WOULD PASS WITH EVERY V3dCacheRange() CALL IN v3d.pi4
     DELETED.  The same was shown about the 91-case
     DMA gate on 2026-08-27, where the gate's own hygiene was masking
     the thing it tested.  Coherency is a bench question and this file
     is not evidence about it either way.

  7. IT CANNOT REPRODUCE AN AXI DEADLOCK, A PARTIAL WRITE, OR WHAT A
     REAL TFU DOES WITH A JOB DESCRIPTION IT DISLIKES.  The engine
     model below either performs the whole conversion or refuses BY
     NAME.  Real hardware has a third option.

WHAT IT CAN DO, AND ALL FIVE ARE WORTH HAVING

  1. EVERY CONSTANT IN v3d.pi4 IS CHECKED AGAINST PINNED SOURCE VALUES.
     Register offsets and field shifts out of linux/v3d_regs.h; the
     PM/ASB offsets, bits, password and bridge magic out of
     linux/bcm2835-power.c; the four block bases out of the DEVICE
     tree's legacy addresses, run through the vendor manual's
     legacy-to-ARM rule rather than copied; the clock id out of linux/rpi-firmware.h's enum by
     counting it; the two DIFFERENT V3D power-domain numbers out of
     rpi-power-bindings.h and raspberrypi-power.c; every mailbox tag
     out of BOTH headers that carry it.  The library and this file
     therefore read the same sources independently and can disagree -
     which is the whole point of a gate.  The source values were
     read out of those files by a parser and are PINNED in this
     file with citations; see PINNED SOURCES below.

  2. THE PROBE IS ACTUALLY RUN, and EVERY access it makes is checked
     for alignment - DRAM as well as MMIO, which closes the hole filed
     against the A64 gates on 2026-08-27 after a64_sdio_check.py --scan
     PASSED on a cyw43.pi4 whose PokeL at offset 18 of a DRAM buffer
     wedged the board dead.  With the ARM MMU off every access is
     Device-nGnRnE and an unaligned one faults whatever SCTLR.A says,
     with no vector installed, so on the board it is silence rather
     than a message.  MMIO accesses are additionally checked for
     WIDTH.  A peripheral register
     touched with anything other than a 4-byte access is refused by
     name: that is the `Poke` instead of `PokeL` trap, which on this
     part silently takes the neighbouring register with it, and at
     $FEC00008 it would return a plausible-looking word made of
     HUB_IDENT0 and HUB_IDENT1 glued together.

  3. THE SAFETY PROPERTY IS TESTED, NOT ASSERTED.  Under a model whose
     bridge IDs are wrong, the gate counts the writes the library made
     to the PM block and requires the count to be ZERO.  The PM block
     holds PM_RSTC and PM_WDOG; "it will not write there if the
     mapping is wrong" is a claim about control flow, and this is the
     mechanical check of it.

  4. THE FIRMWARE MODEL LIES THE WAY THE BOARD LIES.  On a BCM2711 the
     power and clock STATE bits mean "some client has claimed this",
     not "the hardware is running" - recorded at sdio.pi4:1690-1790
     after four witnesses, including the firmware reporting a
     transmitting UART as powered off.  So this model answers every
     set with "on", leaves every state bit where it was, and reports a
     measured clock rate anyway.  A library that treated any of that
     as proof, or as failure, fails here.

  5. TWENTY-TWO NEGATIVE MODELS.  A gate whose refusals have never
     been seen to refuse anything is a gate nobody knows is broken.
     Each mutated model below must drive the library to a NAMED error
     code, and the gate fails if the library sails through.

  6. THE STAGE 1 ENGINE IS ACTUALLY EXECUTED, THROUGH A REAL PAGE
     TABLE WALK.  The TFU model reads its input and writes its output
     by walking the page table the LIBRARY built, out of the same
     memory the payload wrote it into, honouring VALID and WRITEABLE
     and setting MMU_CTL's sticky fault bits when a walk fails.  A
     library that wrote PT_PA_BASE unshifted, or forgot the flush, or
     mapped the wrong page, produces a fault here rather than a
     plausible-looking pass - and then the probe's own byte comparison
     has to agree as well.

  7. AND THE STATUS-BIT LIE IS ONE OF THE NEGATIVE MODELS.  A TFU that
     increments its conversion counter, sets HUB_INT_STS.TFUC, and
     writes nothing at all must NOT produce a passing run.  That is
     the single most important test in this file, because it is the
     failure this project keeps finding and the one a register-only
     check cannot see.

MUTATION TESTED, AND THE SURVIVORS ARE LISTED

  This gate has no --mutate mode.  The record below is from the
  gate's original development against an earlier v3d.pi4.

  Stage 0's gate was mutation tested when it was written: fifteen faults
  injected one at a time, fourteen died, and the one that lived did so
  because two version checks covered for each other - fixed by splitting
  one negative model into three.

  Stage 1 was put through the same exercise on 2026-08-27.
  TWENTY-SEVEN FAULTS, ONE AT A TIME, TWENTY-FOUR KILLED.  Among the
  dead: PT_PA_BASE written unshifted; a PTE built without WRITEABLE;
  V3dMmuMap() not flushing; ICFG written before IOS; ICA never written;
  IIS given in bytes instead of texels; IOS's two halves swapped; the
  completion wait declaring success immediately; the VA-page-0 guard
  removed; the output-alignment guard removed; the interrupt mask never
  restored; and - in the probe - the LINEARTILE index arithmetic broken
  two different ways, the destination never poisoned, and each of the
  three byte comparisons neutered, and a DRAM store moved two bytes
  off alignment - which is named down to the procedure and the source
  line.

  ONE FAILURE WAS FOUND IN THIS FILE BY DOING IT, and it is the
  instructive one.  A probe whose SOURCE comparison had been mutated to
  count nothing survived, because the negative model that exists to
  catch it looked for the words "input texels changed" - which the probe
  prints on EVERY run, followed by a zero.  A needle that matches the
  label rather than the number is not a check.  All three count needles
  now require a non-zero value.

  THE THREE THAT SURVIVE ON PURPOSE, because the model cannot represent
  what they break:

    1. DELETE ANY V3dCacheRange() CALL.  The model's memory is a flat
       dictionary.  There are no caches in it.  See limitation 6.
    2. DELETE THE BARRIER BEFORE THE ICFG WRITE.  The model executes
       stores in program order and cannot reorder DRAM against MMIO.
    3. NEVER WRITE MMUC_CONTROL_ENABLE.  The model's walker reads the
       table out of memory directly and has no PTE cache in front of
       it, so enabling that cache is invisible to it.

  All three are BENCH questions.  A green run from this file is not
  evidence about any of them.

PINNED SOURCES

  No third-party source file is in this repository and this gate reads
  none.  The values it checks the library against were parsed out of:

    Linux, tag v6.12 (torvalds/linux):
      drivers/gpu/drm/v3d/v3d_regs.h, v3d_drv.h, v3d_mmu.c
      drivers/pmdomain/bcm/bcm2835-power.c, raspberrypi-power.c
      include/dt-bindings/power/raspberrypi-power.h
      include/soc/bcm2835/raspberrypi-firmware.h
    The BCM2711 device tree, bcm2711.dtsi (nodes `v3d: gpu@7ec00000`
      and `pm: watchdog@7e100000`)
    Mesa, tag mesa-24.3.4 (commit 769e51468b49b2a42f0a0eaf71cf9eed5ff4e5de):
      src/broadcom/common/v3d_tfu.h, src/broadcom/common/v3d_tiling.c,
      src/gallium/drivers/v3d/v3d_resource.c,
      src/gallium/drivers/v3d/v3dx_tfu.c, src/broadcom/cle/v3d_packet.xml

  and are pinned below with the line each came from in that version.
  The version-gated TFU offsets are the 4.2 arm of each
  `((ver >= 71) ? A : B)` macro, evaluated for 42.  The microtile
  geometry is the result of parsing v3d_utile_width/height.  A pinned
  value cannot notice a later change upstream; re-derive it from the
  cited line.

Run: python tools/a64/a64_v3d_check.py --compiler PureMetalForge.exe
"""
from __future__ import annotations
import argparse
import os
import tempfile

import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = ROOT / "RaspberryPi4" / "Lib" / "v3d.pi4"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4V3dIdent.pi4"
TFU_PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4V3dTfu.pi4"

# Set by main(): the compiler to run and the temporary build directory.
COMPILER: str | None = None
WORKDIR: pathlib.Path | None = None

sys.path.insert(0, str(HERE))
from a64_interp import A64  # noqa: E402

LOAD = 0x400000
STACK = 0x3000000
LOADER_LR = 0xDEADBEE0
CNTFRQ = 54_000_000

UART_DR = 0xFE201000
UART_FR = 0xFE201018

MBX_READ = 0xFE00B880
MBX_STATUS0 = 0xFE00B898
MBX_WRITE = 0xFE00B8A0
MBX_STATUS1 = 0xFE00B8B8
MBX_EMPTY = 0x40000000
MBX_BUS_OFFSET = 0xC0000000


# =====================================================================
#  PART 1 - RE-DERIVING EVERY CONSTANT FROM THE SOURCES ON DISK
#
#  Nothing below is typed from memory and nothing is copied out of
#  v3d.pi4.  Where a number can be computed rather than read, it is
#  computed: the four block bases come out of the device tree through
#  the manual's translation rule, and the V3D clock id comes out of an
#  enum by counting its members.
# =====================================================================

def _text(p: pathlib.Path) -> str:
    if not p.exists():
        raise SystemExit("a64_v3d_check: the source file %s is missing." % p)
    return p.read_text(errors="replace")


# =====================================================================
#  PINNED SOURCE VALUES - see PINNED SOURCES in the docstring.
#  Each line names the file and line the value was parsed from.
# =====================================================================
PINNED = {
    "V3D_HUB_IDENT0":                    0x8,  # v3d_regs.h:27 V3D_HUB_IDENT0
    "V3D_HUB_IDENT1":                    0xC,  # v3d_regs.h:29 V3D_HUB_IDENT1
    "V3D_HUB_IDENT2":                    0x10,  # v3d_regs.h:43 V3D_HUB_IDENT2
    "V3D_HUB_IDENT3":                    0x14,  # v3d_regs.h:48 V3D_HUB_IDENT3
    "V3D_HUB_INT_STS":                   0x50,  # v3d_regs.h:54 V3D_HUB_INT_STS
    "V3D_HUB_INT_CLR":                   0x58,  # v3d_regs.h:56 V3D_HUB_INT_CLR
    "V3D_MMU_DEBUG_INFO":                0x1238,  # v3d_regs.h:201 V3D_MMU_DEBUG_INFO
    "V3D_CTL_IDENT0":                    0x0,  # v3d_regs.h:211 V3D_CTL_IDENT0
    "V3D_CTL_IDENT1":                    0x4,  # v3d_regs.h:215 V3D_CTL_IDENT1
    "V3D_CTL_IDENT2":                    0x8,  # v3d_regs.h:230 V3D_CTL_IDENT2
    "V3D_CTL_INT_STS":                   0x50,  # v3d_regs.h:267 V3D_CTL_INT_STS
    "V3D_CTL_INT_CLR":                   0x58,  # v3d_regs.h:269 V3D_CTL_INT_CLR
    "V3D_ERR_STAT":                      0xF20,  # v3d_regs.h:495 V3D_ERR_STAT
    "V3D_HUB_IDENT2_WITH_MMU":           0x100,  # v3d_regs.h:44 V3D_HUB_IDENT2_WITH_MMU
    "V3D_HUB_IDENT1_TVER_SHIFT":         0x0,  # v3d_regs.h:41 V3D_HUB_IDENT1_TVER_SHIFT
    "V3D_HUB_IDENT1_REV_SHIFT":          0x4,  # v3d_regs.h:39 V3D_HUB_IDENT1_REV_SHIFT
    "V3D_HUB_IDENT1_NCORES_SHIFT":       0x8,  # v3d_regs.h:37 V3D_HUB_IDENT1_NCORES_SHIFT
    "V3D_HUB_IDENT1_NHOSTS_SHIFT":       0xC,  # v3d_regs.h:35 V3D_HUB_IDENT1_NHOSTS_SHIFT
    "V3D_IDENT1_NSLC_SHIFT":             0x4,  # v3d_regs.h:226 V3D_IDENT1_NSLC_SHIFT
    "V3D_IDENT1_QUPS_SHIFT":             0x8,  # v3d_regs.h:224 V3D_IDENT1_QUPS_SHIFT
    "V3D_IDENT1_NTMU_SHIFT":             0xC,  # v3d_regs.h:222 V3D_IDENT1_NTMU_SHIFT
    "V3D_IDENT1_NSEM_SHIFT":             0x10,  # v3d_regs.h:220 V3D_IDENT1_NSEM_SHIFT
    "V3D_IDENT1_VPM_SIZE_SHIFT":         0x1C,  # v3d_regs.h:218 V3D_IDENT1_VPM_SIZE_SHIFT
    "V3D_IDENT0_VER_SHIFT":              0x18,  # v3d_regs.h:213 V3D_IDENT0_VER_SHIFT
    "PM_GRAFX":                          0x10C,  # bcm2835-power.c:80 PM_GRAFX
    "PM_V3DRSTN":                        0x40,  # bcm2835-power.c:86 PM_V3DRSTN
    "PM_ENAB":                           0x1000,  # bcm2835-power.c:82 PM_ENAB
    "PM_ISFUNC":                         0x20,  # bcm2835-power.c:87 PM_ISFUNC
    "PM_PASSWORD":                       0x5A000000,  # bcm2835-power.c:100 PM_PASSWORD
    "ASB_V3D_S_CTRL":                    0x8,  # bcm2835-power.c:115 ASB_V3D_S_CTRL
    "ASB_V3D_M_CTRL":                    0xC,  # bcm2835-power.c:116 ASB_V3D_M_CTRL
    "ASB_AXI_BRDG_ID":                   0x20,  # bcm2835-power.c:127 ASB_AXI_BRDG_ID
    "ASB_REQ_STOP":                      0x1,  # bcm2835-power.c:122 ASB_REQ_STOP
    "ASB_ACK":                           0x2,  # bcm2835-power.c:123 ASB_ACK
    "BCM2835_BRDG_ID":                   0x62726467,  # bcm2835-power.c:129 BCM2835_BRDG_ID
    "TFU_CS":                            0x400,  # v3d_regs.h:91 V3D_TFU_CS, 4.2 arm
    "TFU_SU":                            0x404,  # v3d_regs.h:101 V3D_TFU_SU, 4.2 arm
    "TFU_ICFG":                          0x408,  # v3d_regs.h:112 V3D_TFU_ICFG, 4.2 arm
    "TFU_IIA":                           0x40C,  # v3d_regs.h:117 V3D_TFU_IIA, 4.2 arm
    "TFU_ICA":                           0x410,  # v3d_regs.h:119 V3D_TFU_ICA, 4.2 arm
    "TFU_IIS":                           0x414,  # v3d_regs.h:121 V3D_TFU_IIS, 4.2 arm
    "TFU_IUA":                           0x418,  # v3d_regs.h:123 V3D_TFU_IUA, 4.2 arm
    "TFU_IOA":                           0x41C,  # v3d_regs.h:127 V3D_TFU_IOA, 4.2 arm
    "TFU_IOS":                           0x420,  # v3d_regs.h:129 V3D_TFU_IOS, 4.2 arm
    "TFU_COEF0":                         0x424,  # v3d_regs.h:131 V3D_TFU_COEF0, 4.2 arm
    "TFU_COEF1":                         0x428,  # v3d_regs.h:135 V3D_TFU_COEF1, 4.2 arm
    "TFU_COEF2":                         0x42C,  # v3d_regs.h:137 V3D_TFU_COEF2, 4.2 arm
    "TFU_COEF3":                         0x430,  # v3d_regs.h:139 V3D_TFU_COEF3, 4.2 arm
    "V3D_TFU_CRC":                       0x434,  # v3d_regs.h:142 V3D_TFU_CRC
    "V3D_TFU_CS_TFURST":                 0x80000000,  # v3d_regs.h:94 V3D_TFU_CS_TFURST
    "TFU_CS_CVTCT_SHIFT":                0x10,  # v3d_regs.h:96 V3D_TFU_CS_CVTCT_SHIFT
    "TFU_CS_NFREE_SHIFT":                0x8,  # v3d_regs.h:98 V3D_TFU_CS_NFREE_SHIFT
    "V3D_TFU_CS_BUSY":                   0x1,  # v3d_regs.h:99 V3D_TFU_CS_BUSY
    "ICFG_IOC":                          0x1,  # v3d_regs.h:114 V3D_TFU_ICFG_IOC
    "COEF0_USECOEF":                     0x80000000,  # v3d_regs.h:133 V3D_TFU_COEF0_USECOEF
    "HUB_INT_TFUC":                      0x2,  # v3d_regs.h:65 V3D_HUB_INT_TFUC
    "HUB_INT_TFUF":                      0x1,  # v3d_regs.h:66 V3D_HUB_INT_TFUF
    "V3D_HUB_INT_MMU_WRV":               0x20,  # v3d_regs.h:61 V3D_HUB_INT_MMU_WRV
    "V3D_HUB_INT_MMU_PTI":               0x10,  # v3d_regs.h:62 V3D_HUB_INT_MMU_PTI
    "V3D_HUB_INT_MMU_CAP":               0x8,  # v3d_regs.h:63 V3D_HUB_INT_MMU_CAP
    "HUB_INT_MSK_STS":                   0x5C,  # v3d_regs.h:57 V3D_HUB_INT_MSK_STS
    "HUB_INT_MSK_SET":                   0x60,  # v3d_regs.h:58 V3D_HUB_INT_MSK_SET
    "HUB_INT_MSK_CLR":                   0x64,  # v3d_regs.h:59 V3D_HUB_INT_MSK_CLR
    "MMUC_CONTROL":                      0x1000,  # v3d_regs.h:146 V3D_MMUC_CONTROL
    "MMUC_CONTROL_FLUSHING":             0x4,  # v3d_regs.h:148 V3D_MMUC_CONTROL_FLUSHING
    "MMUC_CONTROL_FLUSH":                0x2,  # v3d_regs.h:149 V3D_MMUC_CONTROL_FLUSH
    "MMUC_CONTROL_ENABLE":               0x1,  # v3d_regs.h:150 V3D_MMUC_CONTROL_ENABLE
    "MMU_CTL":                           0x1200,  # v3d_regs.h:152 V3D_MMU_CTL
    "V3D_MMU_CTL_CAP_EXCEEDED":          0x8000000,  # v3d_regs.h:153 V3D_MMU_CTL_CAP_EXCEEDED
    "V3D_MMU_CTL_CAP_EXCEEDED_ABORT":    0x4000000,  # v3d_regs.h:154 V3D_MMU_CTL_CAP_EXCEEDED_ABORT
    "V3D_MMU_CTL_CAP_EXCEEDED_INT":      0x2000000,  # v3d_regs.h:155 V3D_MMU_CTL_CAP_EXCEEDED_INT
    "V3D_MMU_CTL_PT_INVALID":            0x100000,  # v3d_regs.h:157 V3D_MMU_CTL_PT_INVALID
    "V3D_MMU_CTL_PT_INVALID_ABORT":      0x80000,  # v3d_regs.h:158 V3D_MMU_CTL_PT_INVALID_ABORT
    "V3D_MMU_CTL_PT_INVALID_INT":        0x40000,  # v3d_regs.h:159 V3D_MMU_CTL_PT_INVALID_INT
    "V3D_MMU_CTL_PT_INVALID_ENABLE":     0x10000,  # v3d_regs.h:161 V3D_MMU_CTL_PT_INVALID_ENABLE
    "V3D_MMU_CTL_WRITE_VIOLATION":       0x1000,  # v3d_regs.h:162 V3D_MMU_CTL_WRITE_VIOLATION
    "V3D_MMU_CTL_WRITE_VIOLATION_ABORT": 0x800,  # v3d_regs.h:163 V3D_MMU_CTL_WRITE_VIOLATION_ABORT
    "V3D_MMU_CTL_WRITE_VIOLATION_INT":   0x400,  # v3d_regs.h:164 V3D_MMU_CTL_WRITE_VIOLATION_INT
    "MMU_CTL_TLB_CLEARING":              0x80,  # v3d_regs.h:166 V3D_MMU_CTL_TLB_CLEARING
    "MMU_CTL_TLB_CLEAR":                 0x4,  # v3d_regs.h:168 V3D_MMU_CTL_TLB_CLEAR
    "V3D_MMU_CTL_ENABLE":                0x1,  # v3d_regs.h:170 V3D_MMU_CTL_ENABLE
    "MMU_PT_PA_BASE":                    0x1204,  # v3d_regs.h:172 V3D_MMU_PT_PA_BASE
    "MMU_HIT":                           0x1208,  # v3d_regs.h:173 V3D_MMU_HIT
    "MMU_MISSES":                        0x120C,  # v3d_regs.h:174 V3D_MMU_MISSES
    "MMU_VIO_ID":                        0x122C,  # v3d_regs.h:192 V3D_MMU_VIO_ID
    "MMU_ILLEGAL_ADDR":                  0x1230,  # v3d_regs.h:195 V3D_MMU_ILLEGAL_ADDR
    "V3D_MMU_ILLEGAL_ADDR_ENABLE":       0x80000000,  # v3d_regs.h:196 V3D_MMU_ILLEGAL_ADDR_ENABLE
    "MMU_VIO_ADDR":                      0x1234,  # v3d_regs.h:199 V3D_MMU_VIO_ADDR
    "V3D_CTL_SLCACTL":                   0x24,  # v3d_regs.h:243 V3D_CTL_SLCACTL
    "V3D_CTL_L2TCACTL":                  0x30,  # v3d_regs.h:253 V3D_CTL_L2TCACTL
    "V3D_CTL_L2TFLSTA":                  0x34,  # v3d_regs.h:264 V3D_CTL_L2TFLSTA
    "V3D_CTL_L2TFLEND":                  0x38,  # v3d_regs.h:265 V3D_CTL_L2TFLEND
    "V3D_L2TCACTL_TMUWCF":               0x100,  # v3d_regs.h:254 V3D_L2TCACTL_TMUWCF
    "V3D_L2TCACTL_L2TFLS":               0x1,  # v3d_regs.h:263 V3D_L2TCACTL_L2TFLS
    "V3D_L2TCACTL_FLM_FLUSH":            0x0,  # v3d_regs.h:256 V3D_L2TCACTL_FLM_FLUSH
    "V3D_L2TCACTL_FLM_SHIFT":            0x1,  # v3d_regs.h:262 V3D_L2TCACTL_FLM_SHIFT
    "SLCACTL_TVCCS_SHIFT":               0x18,  # v3d_regs.h:245 V3D_SLCACTL_TVCCS_SHIFT
    "SLCACTL_TDCCS_SHIFT":               0x10,  # v3d_regs.h:247 V3D_SLCACTL_TDCCS_SHIFT
    "SLCACTL_UCC_SHIFT":                 0x8,  # v3d_regs.h:249 V3D_SLCACTL_UCC_SHIFT
    "SLCACTL_ICC_SHIFT":                 0x0,  # v3d_regs.h:251 V3D_SLCACTL_ICC_SHIFT
    "V3D_MMU_PAGE_SHIFT":                0xC,  # v3d_drv.h:24 V3D_MMU_PAGE_SHIFT
    "V3D_PTE_SUPERPAGE":                 0x80000000,  # v3d_mmu.c:27 V3D_PTE_SUPERPAGE
    "V3D_PTE_WRITEABLE":                 0x20000000,  # v3d_mmu.c:28 V3D_PTE_WRITEABLE
    "V3D_PTE_VALID":                     0x10000000,  # v3d_mmu.c:29 V3D_PTE_VALID
    "ICFG_NUMMM_SHIFT":                  0x5,  # v3d_tfu.h:36 V3D33_TFU_ICFG_NUMMM_SHIFT
    "ICFG_TTYPE_SHIFT":                  0x9,  # v3d_tfu.h:37 V3D33_TFU_ICFG_TTYPE_SHIFT
    "ICFG_FORMAT_SHIFT":                 0x12,  # v3d_tfu.h:41 V3D33_TFU_ICFG_FORMAT_SHIFT
    "ICFG_OPAD_SHIFT":                   0x16,  # v3d_tfu.h:39 V3D33_TFU_ICFG_OPAD_SHIFT
    "IFMT_RASTER":                       0x0,  # v3d_tfu.h:42 V3D33_TFU_ICFG_FORMAT_RASTER
    "IFMT_SAND_128":                     0x1,  # v3d_tfu.h:43 V3D33_TFU_ICFG_FORMAT_SAND_128
    "IFMT_SAND_256":                     0x2,  # v3d_tfu.h:44 V3D33_TFU_ICFG_FORMAT_SAND_256
    "IFMT_LINEARTILE":                   0xB,  # v3d_tfu.h:45 V3D33_TFU_ICFG_FORMAT_LINEARTILE
    "IFMT_UBLINEAR_1":                   0xC,  # v3d_tfu.h:46 V3D33_TFU_ICFG_FORMAT_UBLINEAR_1_COLUMN
    "IFMT_UBLINEAR_2":                   0xD,  # v3d_tfu.h:47 V3D33_TFU_ICFG_FORMAT_UBLINEAR_2_COLUMN
    "IFMT_UIF_NO_XOR":                   0xE,  # v3d_tfu.h:48 V3D33_TFU_ICFG_FORMAT_UIF_NO_XOR
    "IFMT_UIF_XOR":                      0xF,  # v3d_tfu.h:49 V3D33_TFU_ICFG_FORMAT_UIF_XOR
    "IOA_DIMTW":                         0x1,  # v3d_tfu.h:28 V3D33_TFU_IOA_DIMTW
    "IOA_FORMAT_SHIFT":                  0x3,  # v3d_tfu.h:29 V3D33_TFU_IOA_FORMAT_SHIFT
    "OFMT_LINEARTILE":                   0x3,  # v3d_tfu.h:30 V3D33_TFU_IOA_FORMAT_LINEARTILE
    "OFMT_UBLINEAR_1":                   0x4,  # v3d_tfu.h:31 V3D33_TFU_IOA_FORMAT_UBLINEAR_1_COLUMN
    "OFMT_UBLINEAR_2":                   0x5,  # v3d_tfu.h:32 V3D33_TFU_IOA_FORMAT_UBLINEAR_2_COLUMN
    "OFMT_UIF_NO_XOR":                   0x6,  # v3d_tfu.h:33 V3D33_TFU_IOA_FORMAT_UIF_NO_XOR
    "OFMT_UIF_XOR":                      0x7,  # v3d_tfu.h:34 V3D33_TFU_IOA_FORMAT_UIF_XOR
    "TEXFMT_RGBA8":                      4,  # v3d_packet.xml:1646 Texture Data Format RGBA8
    "TEXFMT_R32F":                       29,  # v3d_packet.xml:1674 Texture Data Format R32F
    "UTILE_W":                           4,  # v3d_tiling.c:37 v3d_utile_width(4)
    "UTILE_H":                           4,  # v3d_tiling.c:55 v3d_utile_height(4)
}

# Firmware property tags, include/soc/bcm2835/raspberrypi-firmware.h
# (Linux v6.12).  The Raspberry Pi downstream copy of that header carried
# the same ten values when they were pinned.
PINNED_TAGS = {
    "GET_POWER_STATE":       0x00020001,  # raspberrypi-firmware.h:50
    "SET_POWER_STATE":       0x00028001,  # raspberrypi-firmware.h:52
    "GET_CLOCK_STATE":       0x00030001,  # raspberrypi-firmware.h:53
    "SET_CLOCK_STATE":       0x00038001,  # raspberrypi-firmware.h:78
    "GET_CLOCK_RATE":        0x00030002,  # raspberrypi-firmware.h:54
    "SET_CLOCK_RATE":        0x00038002,  # raspberrypi-firmware.h:79
    "GET_MAX_CLOCK_RATE":    0x00030004,  # raspberrypi-firmware.h:56
    "GET_CLOCK_MEASURED":    0x00030047,  # raspberrypi-firmware.h:76
    "GET_DOMAIN_STATE":      0x00030030,  # raspberrypi-firmware.h:74
    "SET_DOMAIN_STATE":      0x00038030,  # raspberrypi-firmware.h:83
}

# The device tree's `reg` cells, bcm2711.dtsi.
#   v3d: gpu@7ec00000        reg = <0x0 0x7ec00000 0x4000>, <0x0 0x7ec04000 0x4000>;
#                            reg-names = "hub", "core0";
#   pm: watchdog@7e100000    reg = <0x7e100000 0x114>, <0x7e00a000 0x24>,
#                                  <0x7ec11000 0x20>;
#                            reg-names = "pm", "asb", "rpivid_asb";
DTSI_LEGACY = {
    "hub": 0x7EC00000, "core0": 0x7EC04000, "pm": 0x7E100000,
    "asb": 0x7E00A000, "rpivid_asb": 0x7EC11000,
}
DTSI_WINDOW_SIZES = {"hub": 0x4000, "core0": 0x4000}

# RPI_FIRMWARE_V3D_CLK_ID, counted from `RPI_FIRMWARE_EMMC_CLK_ID = 1,`
# through the implicit members: raspberrypi-firmware.h:140-144.
PINNED_CLOCK_ID = 5
# RPI_POWER_DOMAIN_V3D, include/dt-bindings/power/raspberrypi-power.h:22.
PINNED_DT_POWER_DOMAIN_V3D = 10
# raspberrypi-power.c:120 - `dom->domain = xlate_index + 1;`, the +1 that
# separates the binding index from the firmware's domain number.
PINNED_DOMAIN_XLATE_PLUS = 1
# RPI_OLD_POWER_DOMAIN_V3D, raspberrypi-power.c:21.
PINNED_OLD_POWER_DOMAIN_V3D = 10

# The transcribed arithmetic, and the lines it was transcribed from
# (Mesa mesa-24.3.4).  The model below and pi4V3dTfu.pi4 both use it.
TRANSCRIBED = (
    ("src/broadcom/common/v3d_tiling.c:84", "return x * cpp + y * utile_w * cpp;"),
    ("src/broadcom/common/v3d_tiling.c:102", "return (64 * (utile_index_x + utile_index_y) +"),
    ("src/broadcom/common/v3d_tiling.c:100", "assert(utile_index_x == 0 || utile_index_y == 0);"),
    ("src/gallium/drivers/v3d/v3d_resource.c:650", "slice->tiling = V3D_TILING_LINEARTILE;"),
    ("src/gallium/drivers/v3d/v3dx_tfu.c:58", "/* Can't write to raster. */"),
)


def lib_constant(name: str) -> int:
    """A '#NAME = value' line in the .pi4 library.  $hex or decimal."""
    text = _text(LIB)
    m = re.search(r"^#" + re.escape(name) +
                  r"\s*=\s*(-?)(?:\$([0-9A-Fa-f]+)|(\d+))\s*(?:;.*)?$",
                  text, re.MULTILINE)
    if not m:
        raise SystemExit("a64_v3d_check: #%s was not found in %s." % (name, LIB))
    v = int(m.group(2), 16) if m.group(2) is not None else int(m.group(3), 10)
    return -v if m.group(1) else v


def lib_has_no(pattern: str) -> bool:
    return re.search(pattern, _text(LIB), re.MULTILINE) is None


# ---------------------------------------------------------------------
#  THE V3DRSTN STRUCTURAL RULE.
#
#  A blanket "this bit is never cleared" refusal cannot tell a power-off
#  from a bounded reset used for ownership handoff (modelled on
#  bcm2835-power.c's own reset authority): both clear the bit, and only
#  one of them is legitimate. The rule that actually matters is
#  structural: a clearing write may exist only inside a procedure that
#  re-asserts the bit again before EVERY one of its return paths, and
#  nothing outside such a procedure may clear it at all. A clear with no
#  matching re-set anywhere in its procedure is exactly a power-off path
#  and is refused the same as before.
#
#  This is source-text analysis, not emulation: procedures in this
#  language are straight-line code with early `ProcedureReturn`s and no
#  gotos or backward jumps, so text order is execution order and a
#  region between a clear and the next re-set can be scanned for a
#  return the way a human reader would.
# ---------------------------------------------------------------------

_V3DRSTN_CLEAR_RE = re.compile(r"~\s*#V3D_PM_V3DRSTN")
_V3DRSTN_SET_RE = re.compile(r"\|\s*#V3D_PM_V3DRSTN")
_PROCEDURE_RE = re.compile(
    r"Procedure(?:\.\w+)?\s+(\w+)\s*\([^)]*\)(.*?)EndProcedure", re.S)
_PROCEDURE_RETURN_RE = re.compile(r"\bProcedureReturn\b")


def v3drstn_violations(code: str) -> list[str]:
    """Every #V3D_PM_V3DRSTN clear must live in a procedure that
    re-asserts it before every return that follows the clear; a clear
    that is never followed by a re-set anywhere in its procedure, or
    one that sits outside any procedure at all, is a violation too.
    `code` is the library source with comments already stripped."""
    violations: list[str] = []
    procedures = list(_PROCEDURE_RE.finditer(code))

    def owner(pos: int):
        for m in procedures:
            if m.start() <= pos < m.end():
                return m
        return None

    for clear in _V3DRSTN_CLEAR_RE.finditer(code):
        proc = owner(clear.start())
        if proc is None:
            line_no = code.count("\n", 0, clear.start()) + 1
            violations.append(
                "line %d clears V3DRSTN outside any procedure - a bounded "
                "reset must be a single named procedure, not loose code."
                % line_no)
            continue
        name = proc.group(1)
        rel_clear = clear.start() - proc.start()
        body = proc.group(0)
        sets_after = [m.start() for m in _V3DRSTN_SET_RE.finditer(body)
                      if m.start() > rel_clear]
        if not sets_after:
            violations.append(
                "%s() clears V3DRSTN but never re-asserts it anywhere in "
                "the same procedure - that is a power-off path, not a "
                "bounded reset." % name)
            continue
        restore_at = min(sets_after)
        for ret in _PROCEDURE_RETURN_RE.finditer(body):
            if rel_clear < ret.start() < restore_at:
                line_no = code.count("\n", 0, proc.start() + ret.start()) + 1
                violations.append(
                    "%s() returns at line %d after clearing V3DRSTN and "
                    "before re-asserting it - that path leaves the rail "
                    "down." % (name, line_no))
    return violations


# A self-test of the rule above, run against two small fixtures rather
# than the real library, so a change to the rule itself is proven
# before it is trusted to grade v3d.pi4.  The two procedure bodies are
# the real V3dOwnershipHardwareReset() shape cut down to its clear/set
# skeleton: POSITIVE restores on both its paths; NEGATIVE is the exact
# defect this rule exists to catch - one refusal that returns between
# the clear and the re-set, matching the pre-fix v3d.pi4.
_V3DRSTN_SELFTEST_POSITIVE = """
Procedure.i FixtureBoundedResetGood()
  Protected g.i
  Protected clk.i
  g = V3dPmRead(#V3D_PM_GRAFX)
  V3dPmWrite(#V3D_PM_GRAFX, g & (~#V3D_PM_V3DRSTN))
  clk = v3d_MbxIdState(#V3D_TAG_SET_CLOCK_STATE, #V3D_CLOCK_ID, #V3D_MBX_STATE_ON, 1)
  If clk <> #V3D_MBX_STATE_ON
    V3dPmWrite(#V3D_PM_GRAFX, g | #V3D_PM_V3DRSTN)
    ProcedureReturn #V3D_ERR_OWNER_RESET
  EndIf
  V3dPmWrite(#V3D_PM_GRAFX, g | #V3D_PM_V3DRSTN)
  ProcedureReturn #V3D_OK
EndProcedure
"""

_V3DRSTN_SELFTEST_NEGATIVE = """
Procedure.i FixtureBoundedResetMissingRestore()
  Protected g.i
  Protected clk.i
  g = V3dPmRead(#V3D_PM_GRAFX)
  V3dPmWrite(#V3D_PM_GRAFX, g & (~#V3D_PM_V3DRSTN))
  clk = v3d_MbxIdState(#V3D_TAG_SET_CLOCK_STATE, #V3D_CLOCK_ID, #V3D_MBX_STATE_ON, 1)
  If clk <> #V3D_MBX_STATE_ON
    ProcedureReturn #V3D_ERR_OWNER_RESET
  EndIf
  V3dPmWrite(#V3D_PM_GRAFX, g | #V3D_PM_V3DRSTN)
  ProcedureReturn #V3D_OK
EndProcedure
"""


def v3drstn_selftest(expect) -> None:
    good = v3drstn_violations(_V3DRSTN_SELFTEST_POSITIVE)
    expect(good == [],
           "the V3DRSTN structural rule false-flagged a fixture where "
           "every return after the clear is preceded by the re-set: %r"
           % good)
    bad = v3drstn_violations(_V3DRSTN_SELFTEST_NEGATIVE)
    expect(len(bad) == 1,
           "the V3DRSTN structural rule did not catch a fixture with one "
           "early return between the clear and the re-set (this must go "
           "red): %r" % bad)


# bcm2711-peripherals.txt:330, section 1.2.4: a peripheral at legacy
# 0x7Enn_nnnn "is visible to the ARM at 0x0_FEnn_nnnn if Low Peripheral
# mode is enabled", and :322 gives that window as 0xFC00_0000 to
# 0xFF7F_FFFF.  So the translation is a fixed +0x80000000 within the
# 0x7Cxx_xxxx..0x7Fxx_xxxx band.  Applying the rule rather than pinning
# the ARM addresses is the point.
def legacy_to_arm(legacy: int) -> int:
    if not (0x7C000000 <= legacy <= 0x7FFFFFFF):
        raise SystemExit("a64_v3d_check: 0x%08X is outside the legacy "
                         "peripheral band, so the translation rule at "
                         "bcm2711-peripherals.txt:330 does not apply to it."
                         % legacy)
    return legacy + 0x80000000


def derive_bases() -> dict[str, int]:
    return {name: legacy_to_arm(addr) for name, addr in DTSI_LEGACY.items()}


def probe_constant(path: pathlib.Path, name: str) -> int:
    """A '#NAME = value' line in a .pi4 PROBE (not the library)."""
    m = re.search(r"^#" + re.escape(name) +
                  r"\s*=\s*(?:\$([0-9A-Fa-f]+)|(\d+))\s*(?:;.*)?$",
                  _text(path), re.MULTILINE)
    if not m:
        raise SystemExit("a64_v3d_check: #%s not found in %s" % (name, path))
    return int(m.group(1), 16) if m.group(1) is not None else int(m.group(2), 10)


# =====================================================================
#  PART 2 - THE MODEL
#
#  Everything here is a hand-written model of hardware nobody on this
#  machine has ever seen answer.  See limitation 1 in the docstring.
# =====================================================================

class Firmware:
    """The property mailbox, answering the way a BCM2711 answers.

    THE STATE BITS LIE, ON PURPOSE.  sdio.pi4:1690-1790 records four
    witnesses that on this part a power or clock state bit means "some
    client has claimed this" and not "the hardware is running": the
    firmware reported UART0 unpowered in the message the PL011 was
    transmitting, and reported the EMMC clock stopped while its own
    counter measured 250000496 Hz on it, twice, with different jitter.
    A SET is accepted, replies "on", and the bit does not move.

    So: every set here returns 1 and changes nothing, and the measured
    clock is reported anyway.  A library that read any of that as proof
    of power, or as a reason to stop, is wrong on this part and this
    model is what says so.
    """

    def __init__(self, tags: dict[str, int], clock_id: int,
                 domain_new: int, power_old: int,
                 clock_measured: int = 499_998_688,
                 answer_tags: bool = True):
        self.tags = tags
        self.clock_id = clock_id
        self.domain_new = domain_new
        self.power_old = power_old
        self.clock_rate = 500_000_000
        self.clock_max = 500_000_000
        self.clock_measured = clock_measured
        self.answer_tags = answer_tags
        self.seen: list[tuple[int, tuple[int, ...]]] = []
        self.reply: int | None = None

    def _value(self, tag: int, words: list[int]) -> list[int] | None:
        t = self.tags
        if tag == t["GET_CLOCK_RATE"]:
            return [words[0], self.clock_rate]
        if tag == t["GET_MAX_CLOCK_RATE"]:
            return [words[0], self.clock_max]
        if tag == t["GET_CLOCK_MEASURED"]:
            return [words[0], self.clock_measured]
        if tag == t["SET_CLOCK_RATE"]:
            # The firmware CLAMPS silently and reports success - the
            # behaviour clocks.pi4's header is built around.
            return [words[0], min(words[1], self.clock_max)]
        if tag in (t["GET_CLOCK_STATE"], t["GET_DOMAIN_STATE"],
                   t["GET_POWER_STATE"]):
            return [words[0], 0]          # never claimed, per the note above
        if tag in (t["SET_CLOCK_STATE"], t["SET_DOMAIN_STATE"],
                   t["SET_POWER_STATE"]):
            return [words[0], 1]          # "on", and nothing moves
        return None

    def submit(self, msg: int, mem) -> None:
        base = (msg & ~0xF) - MBX_BUS_OFFSET
        total = _read(mem, base + 0, 4)
        off = 8
        while off < total - 4:
            tag = _read(mem, base + off + 0, 4)
            if tag == 0:
                break
            vallen = _read(mem, base + off + 4, 4)
            nwords = vallen // 4
            words = [_read(mem, base + off + 12 + 4 * i, 4) for i in range(nwords)]
            self.seen.append((tag, tuple(words)))
            out = self._value(tag, words)
            if out is None or not self.answer_tags:
                # An unrecognised tag is left with bit 31 CLEAR while the
                # buffer still reports success.  mailbox.pi4 checks that
                # per tag, and modelling it is what lets the answer_tags
                # switch below be a real negative test.
                _write(mem, base + off + 8, 0, 4)
            else:
                for i, w in enumerate(out):
                    _write(mem, base + off + 12 + 4 * i, w & 0xFFFFFFFF, 4)
                _write(mem, base + off + 8, 0x80000000 | (len(out) * 4), 4)
            off += 12 + max(vallen, 4)
            off = (off + 3) & ~3
        _write(mem, base + 4, 0x80000000, 4)   # RPI_FIRMWARE_STATUS_SUCCESS
        self.reply = msg


class V3dMmu:
    """The V3D's own single-level page table walker.

    NOT the A72's MMU.  This is the one in the V3D hub that every
    address the engine is handed goes through - v3d_submit.c:1054-1055,
    "the TFU is behind the MMU".  Modelled from linux/v3d_mmu.c, which
    is 120 lines and complete: entry format at :27-29, the entry built
    at :90 and :96, the base register scaled by the page shift at :67,
    the control word at :68-75.

    IT WALKS THE TABLE THE PAYLOAD BUILT, out of the same memory
    dictionary the payload wrote it into.  Nothing here is told where
    the table is; it reads PT_PA_BASE as the library wrote it.  So a
    library that stored the address unshifted walks somewhere else,
    reads whatever is there, and faults - which is the behaviour of the
    hardware and not a check bolted on afterwards.
    """

    def __init__(self, k: dict, mem, force_readonly: bool = False,
                 tlb_never_idle: bool = False, drop_enable: bool = False):
        self.k = k
        self.mem = mem
        self.pt_base = 0            # as written: a PAGE NUMBER
        self.ctl = 0
        self.mmuc = 0
        self.illegal = 0
        self.hits = 0
        self.misses = 0
        self.vio_addr = 0
        self.vio_id = 0
        self.flushes = 0
        self.force_readonly = force_readonly
        self.tlb_never_idle = tlb_never_idle
        self.drop_enable = drop_enable

    # -- the sticky fault bits live in MMU_CTL itself ------------------
    def _fault(self, bit: int, va: int) -> None:
        self.ctl |= bit
        self.vio_addr = va
        self.vio_id = 0

    def enabled(self) -> bool:
        return bool(self.ctl & self.k["V3D_MMU_CTL_ENABLE"])

    def translate(self, va: int, write: bool) -> int | None:
        k = self.k
        shift = k["V3D_MMU_PAGE_SHIFT"]
        if not self.enabled():
            # An engine handed an address with the MMU off is not
            # something any source describes.  Refuse rather than
            # invent a pass-through, which is exactly the guess this
            # project does not ship.
            raise SystemExit(
                "a64_v3d_check: the engine was given address $%08X with "
                "MMU_CTL.ENABLE clear.  Nothing on disk says what the "
                "hardware does then, so this model will not guess." % va)
        entry_addr = (self.pt_base << shift) + ((va >> shift) * 4)
        pte = _read(self.mem, entry_addr, 4)
        if not (pte & k["V3D_PTE_VALID"]):
            self.misses += 1
            self._fault(k["V3D_MMU_CTL_PT_INVALID"], va)
            return None
        if write and (self.force_readonly
                      or not (pte & k["V3D_PTE_WRITEABLE"])):
            self.misses += 1
            self._fault(k["V3D_MMU_CTL_WRITE_VIOLATION"], va)
            return None
        self.hits += 1
        pfn = pte & 0x00FFFFFF          # v3d_mmu.c:99 - 24 bits of PFN
        return (pfn << shift) | (va & ((1 << shift) - 1))

    def read32(self, va: int) -> int | None:
        pa = self.translate(va, False)
        if pa is None:
            return None
        return _read(self.mem, pa, 4)

    def write32(self, va: int, value: int) -> bool:
        pa = self.translate(va, True)
        if pa is None:
            return False
        _write(self.mem, pa, value & 0xFFFFFFFF, 4)
        return True


class Tfu:
    """The Texture Formatting Unit, hub side.

    Register set and launch semantics from linux/v3d_sched.c:299-315
    and mesa/v3dx_simulator.c:179-205, which agree.  Field layout of
    ICFG and IOA from Mesa's src/broadcom/common/v3d_tfu.h, used the way
    src/gallium/drivers/v3d/v3dx_tfu.c:120-155 uses it.  Output byte
    placement transcribed from src/broadcom/common/v3d_tiling.c.

    `mode` is what makes this a gate rather than a demonstration:

      normal        do the conversion properly
      counter_only  bump CVTCT, set TFUC, WRITE NOTHING.  The lie.
      no_tiling     write the raster layout instead of the tiled one
      dead          do nothing at all, not even the counter
      fail          set TFUF and do not convert
      spill         convert, then write four bytes past the image
      clobber_src   convert, and also scribble on the input
      tfuc_only     set TFUC but never move CVTCT
    """

    def __init__(self, k: dict, mmu: V3dMmu, mode: str = "normal"):
        self.k = k
        self.mmu = mmu
        self.mode = mode
        self.reg: dict[int, int] = {}
        self.cvtct = 0
        self.busy = 0
        self.jobs: list[dict] = []
        self.writes = 0
        self.int_sts = 0

    # cpp for a Texture Data Format code.  Only the codes this gate has
    # a size for are accepted; anything else is a refusal by name,
    # because a wrong texel size silently changes the microtile
    # geometry and the output would be wrong in a plausible way.
    def _cpp(self, ttype: int) -> int:
        if ttype in (self.k["TEXFMT_RGBA8"], self.k["TEXFMT_R32F"]):
            return 4
        raise SystemExit(
            "a64_v3d_check: the library asked for texture data format %d, "
            "which this model has no texel size for.  Add it from "
            "v3d_packet.xml's enum - and note that the texel size fixes "
            "the microtile geometry, so guessing it would make the whole "
            "output comparison meaningless." % ttype)

    def write(self, off: int, value: int) -> None:
        k = self.k
        self.reg[off] = value & 0xFFFFFFFF
        self.writes += 1
        if off == k["TFU_ICFG"]:
            self._run()

    def read(self, off: int) -> int:
        k = self.k
        if off == k["TFU_CS"]:
            return ((self.cvtct & 0xFF) << k["TFU_CS_CVTCT_SHIFT"]) \
                | (8 << k["TFU_CS_NFREE_SHIFT"]) | self.busy
        return self.reg.get(off, 0)

    def _need(self, off: int, name: str) -> int:
        if off not in self.reg:
            raise SystemExit(
                "a64_v3d_check: the library launched a TFU job without ever "
                "writing %s.  v3d_sched.c:299-315 writes all of IIA, IIS, "
                "ICA, IUA, IOA, IOS and COEF0 before ICFG, every time, "
                "because they are STATE and the block may have been used "
                "before." % name)
        return self.reg[off]

    def _run(self) -> None:
        k = self.k
        icfg = self.reg[k["TFU_ICFG"]]
        iia = self._need(k["TFU_IIA"], "TFU_IIA")
        iis = self._need(k["TFU_IIS"], "TFU_IIS")
        self._need(k["TFU_ICA"], "TFU_ICA")
        self._need(k["TFU_IUA"], "TFU_IUA")
        ioa = self._need(k["TFU_IOA"], "TFU_IOA")
        ios = self._need(k["TFU_IOS"], "TFU_IOS")
        coef0 = self._need(k["TFU_COEF0"], "TFU_COEF0")

        iformat = (icfg >> k["ICFG_FORMAT_SHIFT"]) & 0xF
        ttype = (icfg >> k["ICFG_TTYPE_SHIFT"]) & 0x1FF
        nummm = (icfg >> k["ICFG_NUMMM_SHIFT"]) & 0xF
        opad = (icfg >> k["ICFG_OPAD_SHIFT"]) & 0x3FF
        ioc = icfg & k["ICFG_IOC"]

        width = ios & 0xFFFF
        height = (ios >> 16) & 0xFFFF
        ofmt = (ioa >> k["IOA_FORMAT_SHIFT"]) & 0x7
        dimtw = ioa & k["IOA_DIMTW"]
        dst = ioa & ~0x3F

        job = dict(icfg=icfg, iia=iia, iis=iis, ioa=ioa, ios=ios,
                   iformat=iformat, ttype=ttype, nummm=nummm, opad=opad,
                   ioc=ioc, width=width, height=height, ofmt=ofmt,
                   dimtw=dimtw, dst=dst, coef0=coef0)
        self.jobs.append(job)

        if self.mode == "dead":
            return
        if self.mode == "fail":
            self.int_sts |= k["HUB_INT_TFUF"]
            return
        if self.mode == "tfuc_only":
            self.int_sts |= k["HUB_INT_TFUC"]
            return

        # -- everything this model refuses to pretend to do ------------
        if iformat != k["IFMT_RASTER"]:
            raise SystemExit(
                "a64_v3d_check: the library asked for input tiling code %d. "
                "This model only implements RASTER (%d) input; a tiled "
                "input reads IIS as padded_height / (2 * utile_h) instead "
                "of a texel stride (v3dx_tfu.c:110-116) and pretending "
                "otherwise would test nothing."
                % (iformat, k["IFMT_RASTER"]))
        if ofmt != k["OFMT_LINEARTILE"]:
            raise SystemExit(
                "a64_v3d_check: the library asked for output tiling code %d. "
                "This model only implements LINEARTILE (%d)."
                % (ofmt, k["OFMT_LINEARTILE"]))
        if nummm != 0 or dimtw != 0 or opad != 0:
            raise SystemExit(
                "a64_v3d_check: the library asked for mipmaps (NUMMM=%d, "
                "DIMTW=%d) or UIF padding (OPAD=%d).  v3d.pi4's TFU section "
                "says it does not encode those, so either the library grew "
                "a feature or a field landed in the wrong bits."
                % (nummm, dimtw, opad))
        if coef0 & k["COEF0_USECOEF"]:
            raise SystemExit(
                "a64_v3d_check: COEF0.USECOEF is set, so the unit would "
                "read COEF1..3 - which v3d_sched.c:308-312 only writes in "
                "that case and v3d.pi4 never writes at all.")
        if not ioc:
            raise SystemExit(
                "a64_v3d_check: ICFG was written without IOC.  "
                "v3d_sched.c:314 ORs V3D_TFU_ICFG_IOC into every "
                "submission; without it the completion interrupt never "
                "fires and a driver that used interrupts would hang.")

        cpp = self._cpp(ttype)
        uw, uh = k["UTILE_W"], k["UTILE_H"]

        # -- the layout, transcribed ----------------------------------
        # Mesa mesa-24.3.4 src/broadcom/common/v3d_tiling.c:70-82 and
        # :84-102.  The lines transcribed are listed in TRANSCRIBED.
        def utile_off(x, y):
            return x * cpp + y * uw * cpp

        def lt_off(x, y):
            return (64 * ((x // uw) + (y // uh))
                    + utile_off(x % uw, y % uh))

        if (width > uw) and (height > uh):
            raise SystemExit(
                "a64_v3d_check: a %dx%d LINEARTILE image is more than one "
                "microtile in BOTH directions.  v3d_tiling.c:96 asserts "
                "that cannot happen - LINEARTILE is a single line of "
                "microtiles - so the layout below would be a fiction."
                % (width, height))

        out: list[tuple[int, int]] = []
        for y in range(height):
            for x in range(width):
                src_va = iia + (y * iis + x) * cpp
                word = self.mmu.read32(src_va)
                if word is None:
                    return          # the fault is recorded in MMU_CTL
                if self.mode == "no_tiling":
                    off = (y * width + x) * cpp
                else:
                    off = lt_off(x, y)
                out.append((dst + off, word))

        if self.mode != "counter_only":
            for va, word in out:
                if not self.mmu.write32(va, word):
                    return
            if self.mode == "spill":
                self.mmu.write32(dst + width * height * cpp, 0x1BADD00D)
            if self.mode == "clobber_src":
                self.mmu.write32(iia, 0xDEADDEAD)

        self.cvtct = (self.cvtct + 1) & 0xFF
        self.int_sts |= k["HUB_INT_TFUC"]


class Board:
    """PM, both ASB bridges, and the V3D hub and core.

    THE PASSWORD IS MODELLED THE WAY THE HARDWARE FAILS, which is
    silently: a PM or ASB write whose top byte is not 0x5A is
    DISCARDED, no fault, no message, execution continues.  That is the
    entire reason v3d.pi4 reads PM_GRAFX back instead of trusting the
    write, and a model that raised an exception on a bad password would
    be testing something the board does not do.
    """

    def __init__(self, k: dict, brdg_legacy: int, brdg_rpivid: int,
                 asb_ack_sticks: bool = False,
                 password_rejected: bool = False,
                 ident1_when_up: int | None = None,
                 ident1_when_down: int = 0x00000000,
                 stage1: bool = False,
                 ident2_when_up: int | None = None,
                 tfu_mode: str = "normal",
                 mmu_force_readonly: bool = False,
                 mmu_tlb_never_idle: bool = False,
                 mmu_drop_enable: bool = False):
        self.k = k
        self.brdg_legacy = brdg_legacy
        self.brdg_rpivid = brdg_rpivid
        self.asb_ack_sticks = asb_ack_sticks
        self.password_rejected = password_rejected
        self.ident1_up = ident1_when_up
        self.ident1_down = ident1_when_down

        # -- stage 1 ---------------------------------------------------
        # stage1 is FALSE for the identity probe, and with it false any
        # write to a V3D register is still a refusal by name.  That
        # check is the reason v3d.pi4's stage 0 half can be trusted to
        # have stayed read-only while a whole stage 1 was bolted on
        # underneath it.
        self.stage1 = stage1
        self.tfu_mode = tfu_mode
        self.mmu_force_readonly = mmu_force_readonly
        self.mmu_tlb_never_idle = mmu_tlb_never_idle
        self.mmu_drop_enable = mmu_drop_enable
        self.ident2_up = ident2_when_up
        if self.ident2_up is None:
            self.ident2_up = k["V3D_HUB_IDENT2_WITH_MMU"]
        self.mmu: V3dMmu | None = None
        self.tfu: Tfu | None = None
        # THE INTERRUPT MASK STARTS ALL ONES, i.e. everything masked,
        # and HUB_INT_STS is modelled as STS & ~MSK.  That is the
        # STRICT reading and it is a choice: nothing on disk says
        # whether this part's STS is pre- or post-mask.  Strict means a
        # library that decided a job was finished by watching
        # HUB_INT_STS.TFUC without unmasking would time out here, which
        # is the safe direction to be wrong in.  v3d_irq_disable
        # (v3d_irq.c:278-293) writes ~0 to MSK_SET, so all-ones is also
        # what a kernel that had finished with the block leaves behind.
        self.int_msk = 0xFFFFFFFF
        self.core_writes: dict[int, int] = {}
        self.hub_writes = 0

        # PM_GRAFX as the firmware is imagined to leave it: the rail is
        # up (ENAB, ISPOW, POWOK, ISFUNC) and V3D is HELD IN RESET, so
        # the deassert the library performs is a real state change that
        # the gate can observe.  Whether the real firmware leaves it
        # this way is exactly what pi4V3dIdent's four snapshots are for.
        self.grafx = k["PM_ENAB"] | k["PM_ISFUNC"] | 0x06
        # Both bridges start STOPPED and acknowledging it.
        self.asb = {k["ASB_V3D_M_CTRL"]: k["ASB_REQ_STOP"] | k["ASB_ACK"],
                    k["ASB_V3D_S_CTRL"]: k["ASB_REQ_STOP"] | k["ASB_ACK"]}

        self.pm_writes = 0
        self.asb_writes = 0
        self.v3d_writes = 0
        self.uart = bytearray()

    def attach(self, mem) -> None:
        """Give the engine models the payload's own memory.

        The page table the TFU walks is the one the PAYLOAD wrote, in
        the same dictionary, at whatever address the payload chose.
        Nothing here is told where it is.
        """
        self.mmu = V3dMmu(self.k, mem,
                          force_readonly=self.mmu_force_readonly,
                          tlb_never_idle=self.mmu_tlb_never_idle,
                          drop_enable=self.mmu_drop_enable)
        self.tfu = Tfu(self.k, self.mmu, mode=self.tfu_mode)

    # -- the assumption, isolated in one place so it can be corrected --
    def _up(self) -> bool:
        """Does the hub answer?

        ASSUMPTION, NOT A CITATION.  Nothing consulted says what a V3D
        held in reset returns on the ARM's read.  Modelled as: zeros
        until the reset is deasserted AND both async bridges are
        enabled.  Deliberately strict, so the gate demands the whole
        sequence; correct it from a bench log if the board disagrees.
        """
        k = self.k
        if (self.grafx & k["PM_V3DRSTN"]) == 0:
            return False
        for reg in (k["ASB_V3D_M_CTRL"], k["ASB_V3D_S_CTRL"]):
            if self.asb[reg] & k["ASB_ACK"]:
                return False
        return True

    def _pm_ok(self, value: int) -> bool:
        if self.password_rejected:
            return False
        return (value >> 24) == 0x5A

    def pm_read(self, off: int) -> int:
        if off == self.k["PM_GRAFX"]:
            return self.grafx
        raise SystemExit(
            "a64_v3d_check: unmodelled PM read at offset $%03X.  v3d.pi4 has "
            "no business anywhere in the PM block except PM_GRAFX ($%03X)."
            % (off, self.k["PM_GRAFX"]))

    def pm_write(self, off: int, value: int) -> None:
        if off in (0x1C, 0x24):
            raise SystemExit(
                "a64_v3d_check: THE LIBRARY WROTE PM_RSTC/PM_WDOG (offset "
                "$%03X).  On the board that resets the SoC.  This is a "
                "refusal and not a warning." % off)
        if off != self.k["PM_GRAFX"]:
            raise SystemExit(
                "a64_v3d_check: write to PM offset $%03X, which v3d.pi4 has "
                "no reason to touch.  The PM block holds the SoC's reset "
                "path; every write into it must be a named register." % off)
        self.pm_writes += 1
        if not self._pm_ok(value):
            # Discarded.  Silently, exactly like the hardware.
            return
        self.grafx = value & 0x00FFFFFF

    def asb_read(self, off: int) -> int:
        if off == self.k["ASB_AXI_BRDG_ID"]:
            return self.brdg_rpivid
        if off in self.asb:
            return self.asb[off]
        raise SystemExit("a64_v3d_check: unmodelled rpivid-ASB read at $%02X"
                         % off)

    def asb_write(self, off: int, value: int) -> None:
        if off not in self.asb:
            raise SystemExit(
                "a64_v3d_check: write to rpivid-ASB offset $%02X.  Only the "
                "two V3D bridge control registers ($%02X master, $%02X "
                "slave) belong to this library." %
                (off, self.k["ASB_V3D_M_CTRL"], self.k["ASB_V3D_S_CTRL"]))
        self.asb_writes += 1
        if not self._pm_ok(value):
            return                      # discarded, like PM
        v = value & 0x00FFFFFF
        # ACK follows REQ_STOP: the bridge acknowledges that it HAS
        # stopped.  Enabling means clearing REQ_STOP and waiting for the
        # acknowledgement to GO AWAY - bcm2835-power.c:179-186, whose
        # loop continues while `!!(reg & ACK) == enable`.  A library
        # that waited for ACK to APPEAR would hang here, which is the
        # whole reason this is modelled rather than stubbed.
        k = self.k
        if self.asb_ack_sticks:
            self.asb[off] = (v & ~k["ASB_ACK"]) | k["ASB_ACK"]
            return
        if v & k["ASB_REQ_STOP"]:
            self.asb[off] = v | k["ASB_ACK"]
        else:
            self.asb[off] = v & ~k["ASB_ACK"]

    def hub_read(self, off: int) -> int:
        k = self.k
        up = self._up()
        if off == k["V3D_HUB_IDENT1"]:
            if not up:
                return self.ident1_down
            return self.ident1_up
        if not up:
            return self.ident1_down if self.ident1_down == 0xFFFFFFFF else 0
        if off == k["V3D_HUB_IDENT0"]:
            return 0x00000000
        if off == k["V3D_HUB_IDENT2"]:
            # WITH_MMU set, no L3 cache.  A guess about the part, and it
            # is not asserted against anywhere - it is here so the probe
            # has something to print.  A negative model clears WITH_MMU
            # to check that V3dMmuInit() believes the part over its own
            # arithmetic.
            return self.ident2_up
        if off == k["V3D_HUB_IDENT3"]:
            return 0x00000000
        if off == k["V3D_MMU_DEBUG_INFO"]:
            return (6 << 8) | (6 << 4) | 2
        if off == k["V3D_HUB_INT_STS"]:
            # Post-mask.  See the note on self.int_msk.
            return self.tfu.int_sts & ~self.int_msk if self.tfu else 0
        if off == k["HUB_INT_MSK_STS"]:
            return self.int_msk
        if self.stage1:
            m = self.mmu
            if off == k["MMU_CTL"]:
                v = m.ctl
                if m.tlb_never_idle:
                    v |= k["MMU_CTL_TLB_CLEARING"]
                return v
            if off == k["MMU_PT_PA_BASE"]:
                return m.pt_base
            if off == k["MMU_ILLEGAL_ADDR"]:
                return m.illegal
            if off == k["MMU_HIT"]:
                return m.hits
            if off == k["MMU_MISSES"]:
                return m.misses
            if off == k["MMU_VIO_ADDR"]:
                return m.vio_addr
            if off == k["MMU_VIO_ID"]:
                return m.vio_id
            if off == k["MMUC_CONTROL"]:
                # The flush is modelled as instantaneous, so FLUSHING is
                # never observed set.  A model where it stuck would test
                # the same wait the TLB_CLEARING one already tests.
                return m.mmuc & ~k["MMUC_CONTROL_FLUSHING"]
            if k["TFU_CS"] <= off <= k["V3D_TFU_CRC"]:
                return self.tfu.read(off)
        raise SystemExit("a64_v3d_check: unmodelled hub read at offset $%05X"
                         % off)

    # -----------------------------------------------------------------
    #  HUB AND CORE WRITES.
    #
    #  With stage1 false these are still refusals: the identity probe
    #  must not write a single V3D register, and that is the check that
    #  keeps stage 0 honest now that a stage 1 exists underneath it.
    # -----------------------------------------------------------------
    def hub_write(self, off: int, value: int, where: str) -> None:
        k = self.k
        self.v3d_writes += 1
        if not self.stage1:
            raise SystemExit(
                "a64_v3d_check: the identity probe WROTE a V3D hub register "
                "(offset $%05X).  Stage 0 is a read-only stage; v3d.pi4's "
                "own header says pi4V3dIdent submits no jobs.\n  at %s"
                % (off, where))
        self.hub_writes += 1

        if off == k["V3D_HUB_INT_CLR"]:
            self.tfu.int_sts &= ~value
            return
        if off == k["HUB_INT_MSK_SET"]:
            self.int_msk |= value        # SET masks - v3d_irq.c:274
            return
        if off == k["HUB_INT_MSK_CLR"]:
            self.int_msk &= ~value       # CLR unmasks - v3d_irq.c:275
            return
        if off == k["MMU_PT_PA_BASE"]:
            # Stored EXACTLY as written.  The walker shifts it back up
            # by the page shift, so a library that wrote the address
            # unshifted walks a table 4096 times too far up memory and
            # faults.  That is the hardware's behaviour and it is why
            # this is not a separate assertion.
            self.mmu.pt_base = value
            return
        if off == k["MMU_CTL"]:
            v = value
            if self.mmu_drop_enable:
                v &= ~k["V3D_MMU_CTL_ENABLE"]
            if value & k["MMU_CTL_TLB_CLEAR"]:
                self.mmu.flushes += 1
            self.mmu.ctl = v & ~k["MMU_CTL_TLB_CLEAR"]
            return
        if off == k["MMU_ILLEGAL_ADDR"]:
            self.mmu.illegal = value
            return
        if off == k["MMUC_CONTROL"]:
            self.mmu.mmuc = value & ~k["MMUC_CONTROL_FLUSH"]
            return
        if k["TFU_CS"] <= off <= k["V3D_TFU_CRC"]:
            self.tfu.write(off, value)
            return
        raise SystemExit(
            "a64_v3d_check: write to hub offset $%05X, which v3d.pi4 has no "
            "named register for.  Every offset it writes is a constant out "
            "of v3d_regs.h; an address this gate does not know is either a "
            "new register - model it - or a field that landed in the wrong "
            "half of a word.\n  at %s" % (off, where))

    def core_write(self, off: int, value: int, where: str) -> None:
        k = self.k
        self.v3d_writes += 1
        if not self.stage1:
            raise SystemExit(
                "a64_v3d_check: the identity probe WROTE a V3D core register "
                "(offset $%05X).  See the hub message.\n  at %s"
                % (off, where))
        allowed = {k["V3D_CTL_L2TFLSTA"]: "L2TFLSTA",
                   k["V3D_CTL_L2TFLEND"]: "L2TFLEND",
                   k["V3D_CTL_L2TCACTL"]: "L2TCACTL",
                   k["V3D_CTL_SLCACTL"]: "SLCACTL"}
        if off not in allowed:
            raise SystemExit(
                "a64_v3d_check: write to CORE 0 register $%05X.  The only "
                "core registers v3d.pi4 may write are the four cache ones "
                "($%03X L2TFLSTA, $%03X L2TFLEND, $%03X L2TCACTL, $%03X "
                "SLCACTL).  The CLE, the GMP, the PTB and the QPU live in "
                "this block too and none of them belong to this file.\n"
                "  at %s"
                % (off, k["V3D_CTL_L2TFLSTA"], k["V3D_CTL_L2TFLEND"],
                   k["V3D_CTL_L2TCACTL"], k["V3D_CTL_SLCACTL"], where))
        self.core_writes[off] = value

    def core_read(self, off: int) -> int:
        k = self.k
        if not self._up():
            return 0
        if off == k["V3D_CTL_IDENT0"]:
            return 0x00000000
        if off == k["V3D_CTL_IDENT1"]:
            # NSLC=2, QUPS=4 - the geometry py-videocore6/README.md:23
            # states for VideoCore VI.  NTMU=2, NSEM=16, VPM=16 KB are
            # placeholders and nothing asserts on them.
            return ((16 - 16) << 28) | (16 << 16) | (2 << 12) | (4 << 8) | (2 << 4) | 2
        if off == k["V3D_CTL_IDENT2"]:
            return 0
        if off == k["V3D_CTL_INT_STS"]:
            return 0
        if off == k["V3D_ERR_STAT"]:
            return 0
        raise SystemExit("a64_v3d_check: unmodelled core0 read at offset $%05X"
                         % off)


def _read(mem, addr: int, size: int) -> int:
    return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))


def _write(mem, addr: int, value: int, size: int) -> None:
    for i in range(size):
        mem[addr + i] = (value >> (8 * i)) & 0xFF


# =====================================================================
#  NAMING A FAULT RATHER THAN PRINTING A HEX PC
#
#  pmfc writes a `.dbg` beside every image: `kind|offset|name|source`,
#  kind 1 being a procedure and the offset an IMAGE offset.  Copied in
#  shape from a64_sdio_check.py:2148-2170, which added it after a fault
#  report that was a bare hex number nobody could act on.
# =====================================================================
def _symbols(img: pathlib.Path) -> list[tuple[int, str, str]]:
    dbg = pathlib.Path(str(img) + ".dbg")
    out: list[tuple[int, str, str]] = []
    if not dbg.exists():
        return out
    for line in dbg.read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 4 and f[0] == "1" and f[1].isdigit():
            out.append((LOAD + int(f[1]), f[2], f[3]))
    out.sort()
    return out


def _where(syms, pc: int) -> str:
    best = None
    for addr, name, src in syms:
        if addr <= pc:
            best = (addr, name, src)
        else:
            break
    if best is None:
        return "$%08X (no symbol covers it)" % pc
    return "$%08X - %s+%d, %s" % (pc, best[1], pc - best[0], best[2])


def build(probe: pathlib.Path = PROBE, name: str = "v3dident.img") -> pathlib.Path:
    if COMPILER is None or WORKDIR is None:
        raise SystemExit("a64_v3d_check: build() was called before main() named "
                         "the compiler and the build directory.")
    img = WORKDIR / name
    r = subprocess.run(
        [COMPILER, "--compile", str(probe), "-t", "pi4", "--entry-returns",
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-o", str(img)],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
        capture_output=True, text=True)
    if r.returncode != 0 or not img.exists():
        raise SystemExit("a64_v3d_check: %s did not build (exit code %d).\n%s%s"
                         % (probe.name, r.returncode, r.stdout, r.stderr))
    return img


def run(img: pathlib.Path, k: dict, board: Board, fw: Firmware,
        limit: int = 80_000_000, entry: str | None = None,
        tick_step: int = 64, args: tuple[int, ...] = ()):
    """Execute the probe against the model.  Returns (x0, uart text).

    `entry` names ONE PROCEDURE to enter directly, by its symbol,
    instead of running the whole image from its entry point.  It exists
    for a single test and the reason is worth writing down.

    THE PROBE CHECKS THE BRIDGE IDs ITSELF and returns before it ever
    calls V3dInit.  So a negative model with a bad bridge ID proves
    only that THE PROBE stopped: the library's own precondition inside
    V3dBringUp() is never reached and never tested, and a gate that
    counted zero PM writes there would be reporting the probe's guard
    while appearing to report the library's.  Entering at v3dbringup
    with a bad-bridge model tests the library's guard on its own, which
    is the one that matters - the next caller of that procedure will
    not be this probe.

    Entering mid-image skips the startup that zeroes the globals.  That
    is acceptable HERE AND ONLY HERE: the path under test reads the two
    bridge registers and returns before touching a global that startup
    would have had to initialise.  If that stops being true this test
    starts lying rather than failing, which is why it is confined to
    one named procedure and not offered as a general facility.
    """
    cpu = A64()
    board.attach(cpu.memory)
    syms = _symbols(img)
    for i, b in enumerate(img.read_bytes()):
        cpu.memory[LOAD + i] = b
    cpu.pc = LOAD
    if entry is not None:
        hit = [a for a, n, _ in syms if n == entry]
        if len(hit) != 1:
            raise SystemExit("a64_v3d_check: %d symbols named %r in the .dbg; "
                             "expected exactly one" % (len(hit), entry))
        cpu.pc = hit[0]
    cpu.sp = STACK
    cpu.x[30] = LOADER_LR
    # ARGUMENTS FOR A DIRECT ENTRY.  AAPCS64 puts the first eight
    # integer arguments in x0..x7, so a procedure entered by symbol can
    # be handed a crafted argument list and its REFUSALS tested on
    # their own.  Same restriction as `entry` above and for the same
    # reason: the startup that zeroes the globals has been skipped, so
    # this is only honest for a path that refuses before it reads one.
    for i, a in enumerate(args):
        cpu.x[i] = a & 0xFFFFFFFFFFFFFFFF
    mem = cpu.memory

    bases = k["bases"]
    hub, core0 = bases["hub"], bases["core0"]
    pm, asb_legacy, asb = bases["pm"], bases["asb"], bases["rpivid_asb"]

    # =================================================================
    #  ALIGNMENT AND WIDTH, AND WHY BOTH.
    #
    #  ALIGNMENT is a64_sdio_check.py's lesson (its lines 2206-2252) and
    #  the reasoning is copied because it is not obvious: SCTLR_EL2.A is
    #  CLEAR on this board, so strict alignment checking is off - but
    #  SCTLR_EL2.M is clear too, and with the MMU off ARMv8-A treats
    #  every data access as Device-nGnRnE, where an unaligned access is
    #  an Alignment fault WHATEVER .A says.  No vector is installed, so
    #  on the board that is not an error message, it is a board that
    #  stops printing mid-line.
    #
    #  WIDTH is this file's own addition and it matters more here than
    #  it did there.  A peripheral register is 32 bits.  `Poke` instead
    #  of `PokeL`, or `Peek` instead of `PeekN`, is EIGHT bytes on this
    #  target and takes the neighbouring register with it - and at
    #  $FEC00008 that returns a plausible-looking value made of
    #  HUB_IDENT0 and HUB_IDENT1 glued together, which would decode into
    #  a wrong-but-believable version number.  There is no way to catch
    #  that by reading the output.
    # =================================================================
    def mmio_guard(addr: int, size: int, write: bool) -> None:
        if size != 4:
            raise SystemExit(
                "a64_v3d_check: a %d-BYTE %s at $%08X.  Peripheral registers "
                "on this part are 32 bits and must be touched with PeekN / "
                "PokeL; a bare Peek/Poke is eight bytes and takes the "
                "neighbouring register with it.\n  at %s"
                % (size, "write" if write else "read", addr, _where(syms, cpu.pc)))
        if addr % 4:
            raise SystemExit(
                "a64_v3d_check: UNALIGNED MMIO %s at $%08X.  With the MMU off "
                "every data access is Device-nGnRnE and an unaligned one is "
                "an Alignment fault whatever SCTLR.A says; no vector is "
                "installed, so on the board this is silence.\n  at %s"
                % ("write" if write else "read", addr, _where(syms, cpu.pc)))

    # -----------------------------------------------------------------
    #  DRAM ALIGNMENT, NOT JUST MMIO ALIGNMENT.
    #
    #  Filed as an open bug against the A64 gates on 2026-08-27: twelve
    #  of them check alignment only on peripheral addresses, and
    #  `a64_sdio_check.py --scan` PASSED on a `cyw43.pi4` whose
    #  `PokeL` at offset 18 of a DRAM buffer wedged the board dead.
    #  With the ARM MMU off every access is Device-nGnRnE, where an
    #  unaligned access is an Alignment fault WHATEVER SCTLR.A says, and
    #  no vector is installed - so on the board it is not an error
    #  message, it is a board that stops printing.
    #
    #  The peripheral window has its own guard because it ALSO enforces
    #  the four-byte width; this one is alignment only, and it applies
    #  everywhere, including the page table and both image buffers.
    # -----------------------------------------------------------------
    def dram_guard(addr: int, size: int, write: bool) -> None:
        if size > 1 and addr % size:
            raise SystemExit(
                "a64_v3d_check: UNALIGNED %d-BYTE %s at $%08X in DRAM.  With "
                "the ARM MMU off every data access is Device-nGnRnE and an "
                "unaligned one is an Alignment fault whatever SCTLR.A says; "
                "no vector is installed, so on the board this is silence, "
                "not a message.\n  at %s"
                % (size, "write" if write else "read", addr,
                   _where(syms, cpu.pc)))

    def load(addr: int, size: int) -> int:
        if addr < 0xFC000000:
            dram_guard(addr, size, False)
        if addr >= 0xFC000000:
            mmio_guard(addr, size, False)
            if addr == UART_FR:
                return 0
            if addr == MBX_STATUS1:
                return 0                      # never FULL
            if addr == MBX_STATUS0:
                return 0 if fw.reply is not None else MBX_EMPTY
            if addr == MBX_READ:
                if fw.reply is None:
                    raise SystemExit("a64_v3d_check: the image read an empty "
                                     "mailbox\n  at %s" % _where(syms, cpu.pc))
                r, fw.reply = fw.reply, None
                return r
            if addr == asb_legacy + k["ASB_AXI_BRDG_ID"]:
                return board.brdg_legacy
            if asb <= addr < asb + 0x20 + 4:
                return board.asb_read(addr - asb)
            if pm <= addr < pm + 0x114:
                return board.pm_read(addr - pm)
            if hub <= addr < hub + 0x4000:
                return board.hub_read(addr - hub)
            if core0 <= addr < core0 + 0x4000:
                return board.core_read(addr - core0)
            raise SystemExit(
                "a64_v3d_check: UNMODELLED MMIO READ at $%08X.\n  at %s\n"
                "  Every address v3d.pi4 touches is a named constant derived "
                "from a cited source.  An address this gate does not know is "
                "either a new register - model it - or a wrong base, which is "
                "the failure the bridge witness exists to catch."
                % (addr, _where(syms, cpu.pc)))
        return _read(mem, addr, size)

    def store(addr: int, value: int, size: int) -> None:
        if addr < 0xFC000000:
            dram_guard(addr, size, True)
        if addr >= 0xFC000000:
            mmio_guard(addr, size, True)
            v = value & 0xFFFFFFFF
            if addr == UART_DR:
                board.uart.append(v & 0xFF)
                return
            if addr == MBX_WRITE:
                fw.submit(v, mem)
                return
            if asb <= addr < asb + 0x24:
                board.asb_write(addr - asb, v)
                return
            if pm <= addr < pm + 0x114:
                board.pm_write(addr - pm, v)
                return
            if hub <= addr < hub + 0x4000:
                board.hub_write(addr - hub, v, _where(syms, cpu.pc))
                return
            if core0 <= addr < core0 + 0x4000:
                board.core_write(addr - core0, v, _where(syms, cpu.pc))
                return
            if addr == asb_legacy + k["ASB_AXI_BRDG_ID"]:
                raise SystemExit("a64_v3d_check: wrote the legacy bridge ID "
                                 "register, which is read-only")
            raise SystemExit(
                "a64_v3d_check: UNMODELLED MMIO WRITE at $%08X.\n  at %s"
                % (addr, _where(syms, cpu.pc)))
        _write(mem, addr, value, size)

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)

    # The interpreter has no MRS.  Shim exactly the two this payload
    # reads, as a64_mmu_check.py:186-193 and a64_watchdog_check.py do.
    # CNTPCT_EL0 MUST ADVANCE: v3d.pi4's delays and both ASB deadlines
    # are written against it, and a frozen counter would turn every
    # bounded wait into the spin-count backstop - which would still
    # terminate, and would take twenty million iterations to do it.
    #
    # tick_step IS A MODELLING KNOB AND NOT A LIBRARY ONE.  Stage 1's
    # deadlines are 100 ms, which is the kernel's own number for the
    # MMU (v3d_mmu.c:37 through v3d_drv.h:488).  At 54 MHz and 64 ticks
    # per counter read, a model that has to reach that deadline spends
    # some five million interpreted instructions doing it, three times
    # over, in the negative runs that exist to check the deadline
    # works.  Running the model's clock faster changes how long the
    # timeout takes to ARRIVE and changes nothing about whether it is
    # enforced - the spin-count backstop and the instruction limit are
    # both still there and both still catch an unbounded loop.
    ticks = [0]

    def step() -> None:
        ins = load(cpu.pc, 4)
        base = ins & 0xFFFFFFE0
        if base == 0xD53BE020:          # mrs Xt, cntpct_el0
            ticks[0] += tick_step
            cpu.x[ins & 31] = ticks[0]
            cpu.pc += 4
            return
        if base == 0xD53BE000:          # mrs Xt, cntfrq_el0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        plain_step()

    for _ in range(limit):
        if cpu.pc == LOADER_LR:
            break
        step()
    else:
        raise SystemExit("a64_v3d_check: the probe did not return within %d "
                         "instructions.  A spin that should have been bounded "
                         "was not." % limit)
    return cpu.x[0] & 0xFFFFFFFF, board.uart.decode("utf-8", "replace")


# =====================================================================
#  PART 3 - THE CHECKS
# =====================================================================

def collect_constants() -> dict:
    """Every source value the checks below use, from the pinned tables."""
    k: dict = dict(PINNED)
    k["bases"] = derive_bases()
    for name, size in DTSI_WINDOW_SIZES.items():
        if size != 0x4000:
            raise SystemExit("a64_v3d_check: the pinned %s window is %#x, not "
                             "0x4000." % (name, size))
    if k["UTILE_W"] * k["UTILE_H"] * 4 != 64:
        raise SystemExit(
            "a64_v3d_check: a microtile came out %dx%d at 4 bytes per texel, "
            "which is not the 64 bytes v3d_tiling.c:35 states, so the pinned "
            "geometry is wrong." % (k["UTILE_W"], k["UTILE_H"]))
    k["clock_id"] = PINNED_CLOCK_ID
    k["domain_new"] = PINNED_DT_POWER_DOMAIN_V3D + PINNED_DOMAIN_XLATE_PLUS
    k["power_old"] = PINNED_OLD_POWER_DOMAIN_V3D
    k["tags"] = dict(PINNED_TAGS)
    return k


def ident1_word(k: dict, tver=4, rev=2, ncores=1, nhosts=1,
                caps=0x000A0000) -> int:
    """Build a HUB_IDENT1 out of the field shifts read from v3d_regs.h.

    Composed from the parsed shifts rather than written as a literal
    $2124, so that a shift the library got wrong and a shift this gate
    got wrong cannot cancel out.
    """
    return (caps
            | (nhosts << k["V3D_HUB_IDENT1_NHOSTS_SHIFT"])
            | (ncores << k["V3D_HUB_IDENT1_NCORES_SHIFT"])
            | (rev << k["V3D_HUB_IDENT1_REV_SHIFT"])
            | (tver << k["V3D_HUB_IDENT1_TVER_SHIFT"]))


def verdict_of(text: str) -> str:
    m = re.search(r"^verdict: (.+?)\s*$", text, re.MULTILINE)
    if m:
        return m.group(1).split(" -")[0]
    m = re.search(r"^STOPPED: (.+?)\s*$", text, re.MULTILINE)
    if m:
        return m.group(1).split(" -")[0]
    return "<no verdict line>"



# =====================================================================
#  PART 4 - STAGE 1.  THE TFU, THE V3D MMU, AND THE BYTES.
#
#  WHAT MAKES THIS DIFFERENT FROM PART 3.  Everything above checks
#  register traffic: the right value into the right offset in the right
#  order.  That is necessary and it is exactly what cannot tell a
#  working engine from one that increments a counter and does nothing.
#  So the model below is not a register recorder - it EXECUTES the job,
#  through the page table the payload built, and puts real bytes in
#  real memory.  The payload then reads those bytes back and compares
#  them against a layout it computed itself, and the gate checks the
#  payload's verdict.
#
#  AND THE VERDICT IS ONLY WORTH ANYTHING BECAUSE OF THE NEGATIVE
#  MODELS.  A payload whose byte comparison was broken - always
#  returning "no mismatches" - would pass a positive run and would fail
#  every one of N11, N12, N16, N17 and N22 below, each of which hands
#  it wrong bytes and requires it to notice.  That is the check that
#  the pass criterion has teeth, and it is not circular, because the
#  payload's expectation is written in one language and this file's
#  engine in another, from the same document.
# =====================================================================

def stage1_checks(k: dict, expect, fails: list[str]) -> None:
    print("=" * 66)
    print(" STAGE 1 - THE TFU: A JOB THE ENGINE EXECUTES, AND ITS BYTES")
    print("=" * 66)

    # -----------------------------------------------------------------
    #  THE TRANSCRIPTIONS, CHECKED AGAINST THEIR SOURCE.
    #
    #  Two pieces of the model below are hand-copied ARITHMETIC rather
    #  than parsed constants, because they are expressions and there is
    #  nothing to parse.  A transcription whose source has moved on is
    #  a model that tests a document nobody is reading any more, and it
    #  fails silently.  These four cost nothing.
    # -----------------------------------------------------------------
    #  The lines the model's layout arithmetic was transcribed from.  A
    #  transcription whose source moves on tests a document nobody reads
    #  any more; these citations are where to re-check it.
    for where, line in TRANSCRIBED:
        print("   %-44s %s" % (where, line))
    print("the transcribed Mesa lines the layout model rests on (pinned).")
    print()

    img = build(TFU_PROBE, "v3dtfu.img")

    # The probe's own memory map, read out of the probe.  The gate is
    # not told where the page table is; it checks that the library put
    # PT_PA_BASE where the probe asked for it, shifted.
    pt = probe_constant(TFU_PROBE, "TFU_PT")
    pt_bytes = probe_constant(TFU_PROBE, "TFU_PT_BYTES")
    src = probe_constant(TFU_PROBE, "TFU_SRC")
    dst = probe_constant(TFU_PROBE, "TFU_DST")
    illegal = probe_constant(TFU_PROBE, "TFU_ILLEGAL")
    img_bytes = probe_constant(TFU_PROBE, "TFU_IMG_BYTES")
    j1w = probe_constant(TFU_PROBE, "TFU_J1_W")
    j1h = probe_constant(TFU_PROBE, "TFU_J1_H")
    j2w = probe_constant(TFU_PROBE, "TFU_J2_W")
    j2h = probe_constant(TFU_PROBE, "TFU_J2_H")

    def fresh1(**kw):
        board = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
                      ident1_when_up=ident1_word(k), stage1=True, **kw)
        fw = Firmware(k["tags"], k["clock_id"], k["domain_new"],
                      k["power_old"])
        return board, fw

    LIMIT = 400_000_000
    STEP = 4096

    # -----------------------------------------------------------------
    #  THE POSITIVE RUN
    # -----------------------------------------------------------------
    board, fw = fresh1()
    x0, text = run(img, k, board, fw, limit=LIMIT, tick_step=STEP)
    print("positive run: verdict %r, x0 %d bytes verified"
          % (verdict_of(text), x0))
    expect(verdict_of(text) == "OK",
           "the healthy stage 1 model did not produce verdict OK; it said "
           "%r.  The whole log is the diagnosis." % verdict_of(text))
    expect(x0 == 3 * img_bytes,
           "the probe verified %d output bytes, expected %d (three jobs of "
           "%d)" % (x0, 3 * img_bytes, img_bytes))

    # -- the MMU was really built, and the base was really shifted -----
    mmu = board.mmu
    expect(mmu.pt_base == pt >> k["V3D_MMU_PAGE_SHIFT"],
           "MMU_PT_PA_BASE holds $%08X; the probe's table is at $%08X and "
           "v3d_mmu.c:67 writes it SHIFTED DOWN by %d, so it should hold "
           "$%08X.  Unshifted, the walk lands 4096 times too high."
           % (mmu.pt_base, pt, k["V3D_MMU_PAGE_SHIFT"],
              pt >> k["V3D_MMU_PAGE_SHIFT"]))
    expect(mmu.illegal == ((illegal >> k["V3D_MMU_PAGE_SHIFT"])
                           | k["V3D_MMU_ILLEGAL_ADDR_ENABLE"]),
           "MMU_ILLEGAL_ADDR holds $%08X, expected the probe's scratch page "
           "$%08X shifted, with the enable bit" % (mmu.illegal, illegal))
    for bit in ("V3D_MMU_CTL_ENABLE", "V3D_MMU_CTL_PT_INVALID_ENABLE",
                "V3D_MMU_CTL_PT_INVALID_ABORT",
                "V3D_MMU_CTL_WRITE_VIOLATION_ABORT",
                "V3D_MMU_CTL_CAP_EXCEEDED_ABORT"):
        expect((mmu.ctl & k[bit]) != 0,
               "MMU_CTL was programmed without %s.  The ABORTs are the "
               "reason a bad address faults instead of quietly landing "
               "somewhere and producing wrong data." % bit)
    expect((mmu.ctl & k["MMU_CTL_TLB_CLEARING"]) == 0,
           "MMU_CTL has TLB_CLEARING set after a clean run")
    expect(mmu.flushes >= 3,
           "only %d TLB clears.  V3dMmuInit() does one and each of the two "
           "V3dMmuMap() calls does one; a PTE the CPU wrote is invisible to "
           "the engine until the TLB and the MMUC have been cleared "
           "(v3d_mmu.c:31-64)." % mmu.flushes)
    expect(mmu.hits > 0,
           "the engine never completed a page table walk, so nothing it did "
           "went through the MMU at all")
    expect(mmu.misses == 0,
           "%d page table walks failed on a clean run" % mmu.misses)
    print("   page table at $%08X, PT_PA_BASE $%08X (shifted by %d),"
          % (pt, mmu.pt_base, k["V3D_MMU_PAGE_SHIFT"]))
    print("   MMU_CTL $%08X, %d TLB clears, %d walks hit, %d missed"
          % (mmu.ctl, mmu.flushes, mmu.hits, mmu.misses))

    # -- THE TABLE IS SPARSE.  Exactly two valid pages, both identity --
    valid = []
    for i in range(pt_bytes // 4):
        pte = _read(board.tfu.mmu.mem, pt + i * 4, 4)
        if pte & k["V3D_PTE_VALID"]:
            valid.append((i, pte))
    expect(len(valid) == 2,
           "%d page table entries are VALID.  The probe maps exactly two "
           "pages and every other address in the whole 16 MiB window must "
           "fault by construction; a table with more valid entries than "
           "that is a table that lets a wrong address land somewhere real."
           % len(valid))
    for page, pte in valid:
        pfn = pte & 0x00FFFFFF
        expect(pfn == page,
               "VA page $%X maps to PA page $%X.  The probe asks for an "
               "identity map." % (page, pfn))
        expect((pte & k["V3D_PTE_WRITEABLE"]) != 0,
               "the PTE for VA page $%X is not WRITEABLE.  v3d_mmu.c:90 "
               "sets WRITEABLE | VALID on every entry, and the TFU writes "
               "its output through one of them." % page)
        expect((pte & k["V3D_PTE_SUPERPAGE"]) == 0,
               "the PTE for VA page $%X has SUPERPAGE set.  v3d_mmu.c:24-26 "
               "warns that every PTE of a 1 MB superpage has to carry it, "
               "which is a footgun with no benefit at these sizes." % page)
    mapped = {page << k["V3D_MMU_PAGE_SHIFT"] for page, _ in valid}
    expect(mapped == {src, dst},
           "the mapped pages are %s; the probe's input and output pages are "
           "$%08X and $%08X" % (sorted("$%08X" % p for p in mapped), src, dst))
    print("   exactly two VALID entries, both identity, both writeable:")
    print("      $%08X and $%08X" % (src, dst))

    # -- the three jobs, decoded from what was actually written --------
    jobs = board.tfu.jobs
    expect(len(jobs) == 3,
           "the probe launched %d TFU jobs, expected 3" % len(jobs))
    if len(jobs) == 3:
        want = [(j1w, j1h, k["TEXFMT_R32F"]),
                (j2w, j2h, k["TEXFMT_R32F"]),
                (j2w, j2h, k["TEXFMT_RGBA8"])]
        for n, (job, (w, h, tt)) in enumerate(zip(jobs, want), start=1):
            expect(job["width"] == w and job["height"] == h,
                   "J%d's IOS says %dx%d, the probe asked for %dx%d.  IOS is "
                   "(height << 16) | width - both witnesses agree - and "
                   "getting the halves the wrong way round produces a job "
                   "that is the right size and the wrong shape."
                   % (n, job["width"], job["height"], w, h))
            expect(job["ttype"] == tt,
                   "J%d's ICFG carries texture data format %d, expected %d"
                   % (n, job["ttype"], tt))
            expect(job["iformat"] == k["IFMT_RASTER"],
                   "J%d's input tiling code is %d, not RASTER (%d)"
                   % (n, job["iformat"], k["IFMT_RASTER"]))
            expect(job["ofmt"] == k["OFMT_LINEARTILE"],
                   "J%d's output tiling code is %d, not LINEARTILE (%d)"
                   % (n, job["ofmt"], k["OFMT_LINEARTILE"]))
            expect(job["iis"] == w,
                   "J%d's IIS is %d.  For a raster source it is the stride "
                   "in TEXELS - stride_bytes / cpp, v3dx_tfu.c:114 - which "
                   "for a tightly packed %d-wide image is %d.  IIS in BYTES "
                   "would be %d and would read every row four times too far "
                   "apart." % (n, job["iis"], w, w, w * 4))
            expect(job["iia"] == src,
                   "J%d's IIA is $%08X, the probe's input page is $%08X"
                   % (n, job["iia"], src))
            expect(job["dst"] == dst,
                   "J%d's IOA carries destination $%08X, expected $%08X"
                   % (n, job["dst"], dst))
            expect(job["nummm"] == 0 and job["opad"] == 0
                   and job["dimtw"] == 0,
                   "J%d asked for mipmaps or UIF padding (NUMMM=%d OPAD=%d "
                   "DIMTW=%d); v3d.pi4 does not encode those"
                   % (n, job["nummm"], job["opad"], job["dimtw"]))
            expect(job["ioc"] != 0,
                   "J%d's ICFG went in without IOC.  v3d_sched.c:314 ORs it "
                   "into every submission." % n)
            expect(job["coef0"] == 0,
                   "J%d wrote COEF0 = $%08X.  A left-over YUV coefficient "
                   "control is state the engine reads." % (n, job["coef0"]))
        print("   3 jobs: %s"
              % ", ".join("%dx%d fmt %d" % (j["width"], j["height"],
                                            j["ttype"]) for j in jobs))

    # -----------------------------------------------------------------
    #  THE BYTES, CHECKED WITHOUT USING THE LAYOUT MODEL AT ALL.
    #
    #  Everything above and everything the payload did runs through one
    #  transcription of v3d_tiling.c or the other.  These two checks do
    #  not: a tiling is a PERMUTATION, so whatever the layout is, the
    #  output must hold the same multiset of bytes as the input and -
    #  for the last job, which is 16 wide and therefore four microtiles
    #  across - must not hold them in the same ORDER.  That is a
    #  statement about what tiling IS, and it would catch a model and a
    #  payload that had made the same transcription error.
    # -----------------------------------------------------------------
    mem = board.tfu.mmu.mem
    src_bytes = bytes(mem.get(src + i, 0) for i in range(img_bytes))
    dst_bytes = bytes(mem.get(dst + i, 0) for i in range(img_bytes))
    expect(sorted(dst_bytes) == sorted(src_bytes),
           "the output is not a permutation of the input.  A tiling moves "
           "bytes; it does not create, drop or alter them.")
    expect(dst_bytes != src_bytes,
           "the last job was %d texels wide, which is %d microtiles across, "
           "so its LINEARTILE output CANNOT equal its raster input - and it "
           "does.  Either the engine copied verbatim or the tiling code "
           "never reached it." % (j2w, j2w // k["UTILE_W"]))
    print("   the output holds the same 256 bytes as the input, in a")
    print("   different order.  That is what a tiling is, and it is")
    print("   checked here without using the layout model.")

    # -- the caches, and only the four registers that are cache --------
    cw = board.core_writes
    for name, want_val in (("V3D_CTL_L2TFLSTA", 0),
                           ("V3D_CTL_L2TFLEND", 0xFFFFFFFF),
                           ("V3D_CTL_L2TCACTL",
                            k["V3D_L2TCACTL_L2TFLS"]
                            | (k["V3D_L2TCACTL_FLM_FLUSH"]
                               << k["V3D_L2TCACTL_FLM_SHIFT"])),
                           ("V3D_CTL_SLCACTL", 0x0F0F0F0F)):
        off = k[name]
        expect(off in cw,
               "%s was never written.  v3d_gem.c:229-240 is the "
               "before-a-job sequence and v3d_init_core:34-35 sets the "
               "flush RANGE; a flush of the wrong range reports success "
               "and flushes nothing." % name)
        if off in cw:
            expect(cw[off] == want_val,
                   "%s got $%08X, expected $%08X"
                   % (name, cw[off], want_val))
    print("   core 0: the four cache registers written, nothing else")

    # -- the interrupt mask was borrowed and given back ----------------
    expect(board.int_msk == 0xFFFFFFFF,
           "the hub interrupt mask is $%08X after the run.  The probe "
           "unmasks TFUC and TFUF around the jobs and must put the mask "
           "back; a library that left VideoCore IRQ 10 asserted for a GIC "
           "it does not own has done something nobody asked for."
           % board.int_msk)
    print("   hub interrupt mask restored to $%08X" % board.int_msk)
    print()

    # -----------------------------------------------------------------
    #  THE NEGATIVE MODELS.
    # -----------------------------------------------------------------
    print("stage 1 negative models - each must be CAUGHT, and the first")
    print("one is the whole reason this file compares bytes at all:")

    def neg(label: str, want_verdict: str, needles=(), **kw) -> None:
        """Run one mutated model and require a NAMED failure.

        `needles` are REGULAR EXPRESSIONS and several of them insist on a
        NON-ZERO COUNT rather than merely on the label being present.
        That distinction was earned: the probe prints "input texels
        changed 0" on every run, so a needle of the bare phrase was
        satisfied by a probe whose source comparison had been mutated to
        count nothing.  Mutation testing found it; the fix is to require
        the number.
        """
        bd, f = fresh1(**kw)
        try:
            _, t = run(img, k, bd, f, limit=LIMIT, tick_step=STEP)
        except SystemExit as e:
            fails.append("%s: the model itself refused - %s" % (label, e))
            return
        got = verdict_of(t)
        ok = got == want_verdict
        for needle in needles:
            if re.search(needle, t) is None:
                ok = False
        print("   %-34s -> %-16s %s" % (label, got, "ok" if ok else "WRONG"))
        if got != want_verdict:
            fails.append("%s: expected verdict %r, got %r"
                         % (label, want_verdict, got))
        for needle in needles:
            if re.search(needle, t) is None:
                fails.append("%s: the log never matched %r" % (label, needle))

    # N11 - THE LIE.  A unit that increments its conversion counter,
    #       sets HUB_INT_STS.TFUC, and writes not one byte.  Every
    #       register-level check in this file passes on it.  The bytes
    #       are the only thing that does not.
    neg("counter moves, nothing written", "TFU_UNVERIFIED",
        (r"texels wrong\s*[1-9]",), tfu_mode="counter_only")

    # N12 - the unit writes the RASTER layout instead of the tiled one.
    #       J1 is one microtile wide, so its two layouts coincide and it
    #       still passes; J2 and J3 must not.  This is the model that
    #       says the probe is checking a FORMATTING and not just a copy.
    neg("output not tiled, just copied", "TFU_UNVERIFIED",
        ("FIRST MISMATCH",), tfu_mode="no_tiling")

    # N13 - nothing at all.  The deadline has to end it.
    neg("unit never responds", "TFU_UNVERIFIED",
        ("TFU_TIMEOUT",), tfu_mode="dead")

    # N14 - the unit reports failure.
    neg("unit raises TFUF", "TFU_UNVERIFIED",
        ("TFU_FAIL",), tfu_mode="fail")

    # N15 - TFUC IS SET AND THE COUNTER NEVER MOVES.  This is the model
    #       that justifies polling TFU_CS.CVTCT instead of the interrupt
    #       status bit: a library that trusted TFUC would call this a
    #       success and then read poison.
    neg("TFUC set but CVTCT frozen", "TFU_UNVERIFIED",
        ("TFU_TIMEOUT",), tfu_mode="tfuc_only")

    # N16 - a correct image plus four bytes past the end.  The texel
    #       comparison cannot see this; the spill check can.
    neg("writes four bytes past the image", "TFU_UNVERIFIED",
        (r"bytes written past image\s*[1-9]",), tfu_mode="spill")

    # N17 - a correct image, and a scribble on the source.
    neg("scribbles on its own input", "TFU_UNVERIFIED",
        (r"input texels changed\s*[1-9]",), tfu_mode="clobber_src")

    # N18 - the destination page refuses writes.  The MMU must raise
    #       WRITE_VIOLATION and the library must report it rather than
    #       spinning to the deadline.
    neg("every page is read-only", "TFU_UNVERIFIED",
        ("MMU_FAULT",), mmu_force_readonly=True)

    # N19 - the TLB clear never finishes.  The library must give up, and
    #       it must give up BEFORE it has touched the TFU.
    bd, f = fresh1(mmu_tlb_never_idle=True)
    _, t = run(img, k, bd, f, limit=LIMIT, tick_step=STEP)
    got = verdict_of(t)
    print("   %-34s -> %-16s %s"
          % ("TLB clear never completes", got,
             "ok" if got == "MMU_FLUSH" else "WRONG"))
    if got != "MMU_FLUSH":
        fails.append("TLB clear never completes: expected MMU_FLUSH, got %r"
                     % got)
    expect(len(bd.tfu.jobs) == 0,
           "the library launched %d TFU job(s) after the TLB clear timed "
           "out.  A page table the engine cannot see is worse than no page "
           "table: the addresses are plausible and the translations are "
           "stale." % len(bd.tfu.jobs))

    # N20 - the MMU enable does not stick.  Read-back is the only thing
    #       that can catch it, exactly as with PM_GRAFX in stage 0.
    neg("MMU enable does not stick", "MMU_OFF", (), mmu_drop_enable=True)

    # N21 - the part says it has no MMU.
    neg("part reports no MMU", "MMU_ABSENT", (),
        ident2_when_up=0)

    # -----------------------------------------------------------------
    #  THE ARGUMENT GUARDS, TESTED ON THEIR OWN.
    #
    #  Every refusal above is reached through the probe.  These are
    #  not: they are the guards a FUTURE caller will hit, and a guard
    #  nobody has seen refuse anything is a guard nobody knows is
    #  broken.  Each enters one procedure by symbol with a crafted
    #  argument list and requires the named error back.
    #
    #  ENTERING MID-IMAGE SKIPS THE STARTUP THAT ZEROES THE GLOBALS,
    #  which is why every case below is one that refuses BEFORE it
    #  reads a global.  V3dMmuMap()'s argument checks were deliberately
    #  moved ahead of its state check so that is true of them; if that
    #  order is ever reversed these tests start lying rather than
    #  failing, so the order is also asserted, on the source, below.
    # -----------------------------------------------------------------
    print("   argument guards, each entered directly by symbol:")
    guards = [
        ("v3dmmumap", (0, src, 0x1000), "V3D_ERR_MMU_RANGE",
         "VA page 0.  v3d_gem.c:276 never hands out page 0, and a TFU "
         "address register that was never written reads as zero."),
        ("v3dmmumap", (src + 64, src, 0x1000), "V3D_ERR_MMU_ALIGN",
         "a VA that is not 4 KiB aligned - the table has one entry per "
         "page and no offset field."),
        ("v3dmmumap", (src, src + 64, 0x1000), "V3D_ERR_MMU_ALIGN",
         "a PA that is not 4 KiB aligned."),
        ("v3dmmumap", (src, src, 0x800), "V3D_ERR_MMU_ALIGN",
         "half a page.  Rounding up silently would map memory the "
         "caller never offered, to a bus master."),
        ("v3dtfudest", (dst + 8, k["OFMT_LINEARTILE"], 256),
         "V3D_ERR_MMU_ALIGN",
         "an output address with low bits set.  IOA's bits 5:0 are the "
         "tiling format and the level-0 skip, so those bits would "
         "silently change the job."),
        ("v3dtfudest", (dst, k["OFMT_LINEARTILE"] - 1, 256),
         "V3D_ERR_TFU_ARGS",
         "an output tiling code below LINEARTILE.  There is no RASTER "
         "output - v3dx_tfu.c:59-60, 'Can't write to raster'."),
        ("v3dtfudest", (dst, k["OFMT_UIF_XOR"] + 1, 256),
         "V3D_ERR_TFU_ARGS", "an output tiling code above UIF_XOR."),
        ("v3dtfubegin", (0, 4, k["TEXFMT_R32F"]), "V3D_ERR_TFU_ARGS",
         "a zero width."),
        ("v3dtfubegin", (0x10000, 4, k["TEXFMT_R32F"]), "V3D_ERR_TFU_ARGS",
         "a width of 65536, which would land in IOS's height field - "
         "neither Mesa witness masks before shifting."),
        ("v3dtfubegin", (4, 0x10000, k["TEXFMT_R32F"]), "V3D_ERR_TFU_ARGS",
         "a height of 65536."),
        ("v3dtfubegin", (4, 4, 256), "V3D_ERR_TFU_ARGS",
         "a texture format code of 256, which would reach ICFG's input "
         "format field and change what the job MEANS."),
    ]
    for sym, argv, errname, why in guards:
        bd, f = fresh1()
        rc, _ = run(img, k, bd, f, limit=LIMIT, tick_step=STEP,
                    entry=sym, args=argv)
        want = lib_constant(errname[1:]) if errname.startswith("#")             else lib_constant(errname)
        ok = rc == want
        print("      %-13s %-26s -> %d %s"
              % (sym, ", ".join(str(a) for a in argv), rc,
                 "ok" if ok else "WRONG, wanted %d" % want))
        if not ok:
            fails.append("%s%r: returned %d, expected #%s = %d.  It was "
                         "handed %s" % (sym, argv, rc, errname, want, why))
        expect(bd.pm_writes == 0 and bd.hub_writes == 0,
               "%s%r made %d PM and %d hub writes on its way to a refusal"
               % (sym, argv, bd.pm_writes, bd.hub_writes))

    # And the ORDER those guards are written in, on the source, because
    # the tests above are only honest while the argument checks come
    # first.
    code0 = "\n".join(l.split(";")[0] for l in _text(LIB).splitlines())
    mapsrc = re.search(r"Procedure\.i\s+V3dMmuMap\b.*?EndProcedure",
                       code0, re.S)
    expect(mapsrc is not None, "V3dMmuMap() is gone")
    if mapsrc:
        body = mapsrc.group(0)
        expect(body.index("#V3D_MMU_PAGE_BYTES") < body.index("v3d_ptBase = 0"),
               "V3dMmuMap() checks its state before its arguments.  The "
               "direct-entry tests above enter with the globals unzeroed "
               "and would then be testing the state check instead of the "
               "guard they name - they would pass for the wrong reason.")
    print()

    # N22 - the part says it has no TFU.  HUB_IDENT1's capability bits
    #       are the part's own answer and beat any arithmetic here.
    bd, f = fresh1()
    bd.ident1_up = ident1_word(k, caps=0)
    _, t = run(img, k, bd, f, limit=LIMIT, tick_step=STEP)
    got = verdict_of(t)
    ok = got == "TFU_UNVERIFIED" and "TFU_ABSENT" in t
    print("   %-34s -> %-16s %s"
          % ("part reports no TFU", got, "ok" if ok else "WRONG"))
    if not ok:
        fails.append("part reports no TFU: verdict %r, TFU_ABSENT in log: %s"
                     % (got, "TFU_ABSENT" in t))
    expect(len(bd.tfu.jobs) == 0,
           "the library launched a TFU job on a part whose HUB_IDENT1 says "
           "WITH_TFU is clear")
    print()

def _main() -> int:
    fails: list[str] = []

    def expect(cond: bool, what: str) -> None:
        if not cond:
            fails.append(what)

    k = collect_constants()
    b = k["bases"]

    # -----------------------------------------------------------------
    #  1. THE CONSTANTS, RE-DERIVED
    # -----------------------------------------------------------------
    print("bases, derived from bcm2711.dtsi through the legacy-to-ARM rule")
    print("at bcm2711-peripherals.txt:330 (0x7Enn_nnnn -> 0x0_FEnn_nnnn):")
    for name, libname in (("hub", "V3D_HUB_BASE"), ("core0", "V3D_CORE0_BASE"),
                          ("pm", "V3D_PM_BASE"), ("asb", "V3D_ASB_BASE"),
                          ("rpivid_asb", "V3D_RPIVID_ASB_BASE")):
        got = lib_constant(libname)
        print("   %-12s $%08X   #%s" % (name, b[name], libname))
        expect(got == b[name],
               "#%s is $%08X, the device tree gives $%08X"
               % (libname, got, b[name]))
    print()

    pairs = [
        ("V3D_HUB_IDENT0", "V3D_HUB_IDENT0"), ("V3D_HUB_IDENT1", "V3D_HUB_IDENT1"),
        ("V3D_HUB_IDENT2", "V3D_HUB_IDENT2"), ("V3D_HUB_IDENT3", "V3D_HUB_IDENT3"),
        ("V3D_HUB_INT_STS", "V3D_HUB_INT_STS"),
        ("V3D_HUB_INT_CLR", "V3D_HUB_INT_CLR"),
        ("V3D_MMU_DEBUG_INFO", "V3D_MMU_DEBUG_INFO"),
        ("V3D_CTL_IDENT0", "V3D_CTL_IDENT0"), ("V3D_CTL_IDENT1", "V3D_CTL_IDENT1"),
        ("V3D_CTL_IDENT2", "V3D_CTL_IDENT2"),
        ("V3D_CTL_INT_STS", "V3D_CTL_INT_STS"),
        ("V3D_CTL_INT_CLR", "V3D_CTL_INT_CLR"),
        ("V3D_ERR_STAT", "V3D_ERR_STAT"),
        ("V3D_PM_GRAFX", "PM_GRAFX"), ("V3D_PM_V3DRSTN", "PM_V3DRSTN"),
        ("V3D_PM_ENAB", "PM_ENAB"), ("V3D_PM_ISFUNC", "PM_ISFUNC"),
        ("V3D_PM_PASSWORD", "PM_PASSWORD"),
        ("V3D_ASB_V3D_S_CTRL", "ASB_V3D_S_CTRL"),
        ("V3D_ASB_V3D_M_CTRL", "ASB_V3D_M_CTRL"),
        ("V3D_ASB_AXI_BRDG_ID", "ASB_AXI_BRDG_ID"),
        ("V3D_ASB_REQ_STOP", "ASB_REQ_STOP"), ("V3D_ASB_ACK", "ASB_ACK"),
        ("V3D_BRDG_ID", "BCM2835_BRDG_ID"),
        ("V3D_IDENT1_TVER_SHIFT", "V3D_HUB_IDENT1_TVER_SHIFT"),
        ("V3D_IDENT1_REV_SHIFT", "V3D_HUB_IDENT1_REV_SHIFT"),
        ("V3D_IDENT1_NCORES_SHIFT", "V3D_HUB_IDENT1_NCORES_SHIFT"),
        ("V3D_IDENT1_NHOSTS_SHIFT", "V3D_HUB_IDENT1_NHOSTS_SHIFT"),
        ("V3D_CTL_IDENT1_NSLC_SHIFT", "V3D_IDENT1_NSLC_SHIFT"),
        ("V3D_CTL_IDENT1_QUPS_SHIFT", "V3D_IDENT1_QUPS_SHIFT"),
        ("V3D_CTL_IDENT1_NTMU_SHIFT", "V3D_IDENT1_NTMU_SHIFT"),
        ("V3D_CTL_IDENT1_NSEM_SHIFT", "V3D_IDENT1_NSEM_SHIFT"),
        ("V3D_CTL_IDENT1_VPM_SIZE_SHIFT", "V3D_IDENT1_VPM_SIZE_SHIFT"),
        ("V3D_CTL_IDENT0_VER_SHIFT", "V3D_IDENT0_VER_SHIFT"),
        ("V3D_IDENT2_WITH_MMU", "V3D_HUB_IDENT2_WITH_MMU"),

        # -- stage 1: the TFU block, version-gated offsets evaluated ---
        ("V3D_TFU_CS", "TFU_CS"), ("V3D_TFU_SU", "TFU_SU"),
        ("V3D_TFU_ICFG", "TFU_ICFG"), ("V3D_TFU_IIA", "TFU_IIA"),
        ("V3D_TFU_ICA", "TFU_ICA"), ("V3D_TFU_IIS", "TFU_IIS"),
        ("V3D_TFU_IUA", "TFU_IUA"), ("V3D_TFU_IOA", "TFU_IOA"),
        ("V3D_TFU_IOS", "TFU_IOS"), ("V3D_TFU_COEF0", "TFU_COEF0"),
        ("V3D_TFU_COEF1", "TFU_COEF1"), ("V3D_TFU_COEF2", "TFU_COEF2"),
        ("V3D_TFU_COEF3", "TFU_COEF3"), ("V3D_TFU_CRC", "V3D_TFU_CRC"),
        ("V3D_TFU_CS_TFURST", "V3D_TFU_CS_TFURST"),
        ("V3D_TFU_CS_CVTCT_SHIFT", "TFU_CS_CVTCT_SHIFT"),
        ("V3D_TFU_CS_NFREE_SHIFT", "TFU_CS_NFREE_SHIFT"),
        ("V3D_TFU_CS_BUSY", "V3D_TFU_CS_BUSY"),
        ("V3D_TFU_ICFG_IOC", "ICFG_IOC"),
        ("V3D_TFU_COEF0_USECOEF", "COEF0_USECOEF"),

        # -- hub interrupt status and mask -----------------------------
        ("V3D_HUB_INT_TFUC", "HUB_INT_TFUC"),
        ("V3D_HUB_INT_TFUF", "HUB_INT_TFUF"),
        ("V3D_HUB_INT_MMU_WRV", "V3D_HUB_INT_MMU_WRV"),
        ("V3D_HUB_INT_MMU_PTI", "V3D_HUB_INT_MMU_PTI"),
        ("V3D_HUB_INT_MMU_CAP", "V3D_HUB_INT_MMU_CAP"),
        ("V3D_HUB_INT_MSK_STS", "HUB_INT_MSK_STS"),
        ("V3D_HUB_INT_MSK_SET", "HUB_INT_MSK_SET"),
        ("V3D_HUB_INT_MSK_CLR", "HUB_INT_MSK_CLR"),

        # -- the V3D MMU -----------------------------------------------
        ("V3D_MMUC_CONTROL", "MMUC_CONTROL"),
        ("V3D_MMUC_CONTROL_FLUSHING", "MMUC_CONTROL_FLUSHING"),
        ("V3D_MMUC_CONTROL_FLUSH", "MMUC_CONTROL_FLUSH"),
        ("V3D_MMUC_CONTROL_ENABLE", "MMUC_CONTROL_ENABLE"),
        ("V3D_MMU_CTL", "MMU_CTL"),
        ("V3D_MMU_CTL_CAP_EXCEEDED", "V3D_MMU_CTL_CAP_EXCEEDED"),
        ("V3D_MMU_CTL_CAP_EXCEEDED_ABORT", "V3D_MMU_CTL_CAP_EXCEEDED_ABORT"),
        ("V3D_MMU_CTL_CAP_EXCEEDED_INT", "V3D_MMU_CTL_CAP_EXCEEDED_INT"),
        ("V3D_MMU_CTL_PT_INVALID", "V3D_MMU_CTL_PT_INVALID"),
        ("V3D_MMU_CTL_PT_INVALID_ABORT", "V3D_MMU_CTL_PT_INVALID_ABORT"),
        ("V3D_MMU_CTL_PT_INVALID_INT", "V3D_MMU_CTL_PT_INVALID_INT"),
        ("V3D_MMU_CTL_PT_INVALID_ENABLE", "V3D_MMU_CTL_PT_INVALID_ENABLE"),
        ("V3D_MMU_CTL_WRITE_VIOLATION", "V3D_MMU_CTL_WRITE_VIOLATION"),
        ("V3D_MMU_CTL_WRITE_VIOLATION_ABORT", "V3D_MMU_CTL_WRITE_VIOLATION_ABORT"),
        ("V3D_MMU_CTL_WRITE_VIOLATION_INT", "V3D_MMU_CTL_WRITE_VIOLATION_INT"),
        ("V3D_MMU_CTL_TLB_CLEARING", "MMU_CTL_TLB_CLEARING"),
        ("V3D_MMU_CTL_TLB_CLEAR", "MMU_CTL_TLB_CLEAR"),
        ("V3D_MMU_CTL_ENABLE", "V3D_MMU_CTL_ENABLE"),
        ("V3D_MMU_PT_PA_BASE", "MMU_PT_PA_BASE"),
        ("V3D_MMU_HIT", "MMU_HIT"), ("V3D_MMU_MISSES", "MMU_MISSES"),
        ("V3D_MMU_VIO_ID", "MMU_VIO_ID"),
        ("V3D_MMU_ILLEGAL_ADDR", "MMU_ILLEGAL_ADDR"),
        ("V3D_MMU_ILLEGAL_ADDR_ENABLE", "V3D_MMU_ILLEGAL_ADDR_ENABLE"),
        ("V3D_MMU_VIO_ADDR", "MMU_VIO_ADDR"),
        ("V3D_MMU_PAGE_SHIFT", "V3D_MMU_PAGE_SHIFT"),
        ("V3D_PTE_SUPERPAGE", "V3D_PTE_SUPERPAGE"),
        ("V3D_PTE_WRITEABLE", "V3D_PTE_WRITEABLE"),
        ("V3D_PTE_VALID", "V3D_PTE_VALID"),

        # -- core 0's four cache registers -----------------------------
        ("V3D_CTL_SLCACTL", "V3D_CTL_SLCACTL"),
        ("V3D_CTL_L2TCACTL", "V3D_CTL_L2TCACTL"),
        ("V3D_CTL_L2TFLSTA", "V3D_CTL_L2TFLSTA"),
        ("V3D_CTL_L2TFLEND", "V3D_CTL_L2TFLEND"),
        ("V3D_L2TCACTL_TMUWCF", "V3D_L2TCACTL_TMUWCF"),
        ("V3D_L2TCACTL_L2TFLS", "V3D_L2TCACTL_L2TFLS"),
        ("V3D_L2TCACTL_FLM_FLUSH", "V3D_L2TCACTL_FLM_FLUSH"),
        ("V3D_L2TCACTL_FLM_SHIFT", "V3D_L2TCACTL_FLM_SHIFT"),

        # -- ICFG and IOA's fields, from the fetched Mesa header -------
        ("V3D_TFU_ICFG_NUMMM_SHIFT", "ICFG_NUMMM_SHIFT"),
        ("V3D_TFU_ICFG_TTYPE_SHIFT", "ICFG_TTYPE_SHIFT"),
        ("V3D_TFU_ICFG_FORMAT_SHIFT", "ICFG_FORMAT_SHIFT"),
        ("V3D_TFU_ICFG_OPAD_SHIFT", "ICFG_OPAD_SHIFT"),
        ("V3D_TFU_IFMT_RASTER", "IFMT_RASTER"),
        ("V3D_TFU_IFMT_SAND_128", "IFMT_SAND_128"),
        ("V3D_TFU_IFMT_SAND_256", "IFMT_SAND_256"),
        ("V3D_TFU_IFMT_LINEARTILE", "IFMT_LINEARTILE"),
        ("V3D_TFU_IFMT_UBLINEAR_1", "IFMT_UBLINEAR_1"),
        ("V3D_TFU_IFMT_UBLINEAR_2", "IFMT_UBLINEAR_2"),
        ("V3D_TFU_IFMT_UIF_NO_XOR", "IFMT_UIF_NO_XOR"),
        ("V3D_TFU_IFMT_UIF_XOR", "IFMT_UIF_XOR"),
        ("V3D_TFU_IOA_DIMTW", "IOA_DIMTW"),
        ("V3D_TFU_IOA_FORMAT_SHIFT", "IOA_FORMAT_SHIFT"),
        ("V3D_TFU_OFMT_LINEARTILE", "OFMT_LINEARTILE"),
        ("V3D_TFU_OFMT_UBLINEAR_1", "OFMT_UBLINEAR_1"),
        ("V3D_TFU_OFMT_UBLINEAR_2", "OFMT_UBLINEAR_2"),
        ("V3D_TFU_OFMT_UIF_NO_XOR", "OFMT_UIF_NO_XOR"),
        ("V3D_TFU_OFMT_UIF_XOR", "OFMT_UIF_XOR"),

        # -- and the two texture data format codes ---------------------
        ("V3D_TEXFMT_RGBA8", "TEXFMT_RGBA8"),
        ("V3D_TEXFMT_R32F", "TEXFMT_R32F"),
    ]
    bad = 0
    for libname, srcname in pairs:
        got, want = lib_constant(libname), k[srcname]
        if got != want:
            bad += 1
            fails.append("#%s is $%X, the source gives $%X (%s)"
                         % (libname, got, want, srcname))
    print("%d register offsets, field shifts and bit masks checked against"
          % len(pairs))
    print("values pinned from v3d_regs.h, bcm2835-power.c and Mesa: %d wrong" % bad)
    print()

    # The two numbers that are the same block and are not the same
    # number.  Getting these the wrong way round is a silent no-op.
    print("the V3D ids, and there are three of them:")
    print("   firmware clock id   %d   (counted out of raspberrypi-firmware.h's enum)"
          % k["clock_id"])
    print("   SET_DOMAIN_STATE    %d   (rpi-power-bindings.h + the +1 at "
          "raspberrypi-power.c:120)" % k["domain_new"])
    print("   SET_POWER_STATE     %d   (RPI_OLD_POWER_DOMAIN_V3D)"
          % k["power_old"])
    expect(lib_constant("V3D_CLOCK_ID") == k["clock_id"],
           "#V3D_CLOCK_ID is %d, the enum counts %d"
           % (lib_constant("V3D_CLOCK_ID"), k["clock_id"]))
    expect(lib_constant("V3D_DOMAIN_ID_NEW") == k["domain_new"],
           "#V3D_DOMAIN_ID_NEW is %d, the sources give %d"
           % (lib_constant("V3D_DOMAIN_ID_NEW"), k["domain_new"]))
    expect(lib_constant("V3D_POWER_ID_OLD") == k["power_old"],
           "#V3D_POWER_ID_OLD is %d, the sources give %d"
           % (lib_constant("V3D_POWER_ID_OLD"), k["power_old"]))
    expect(k["domain_new"] != k["power_old"],
           "the two domain numbers came out equal, which means the +1 was "
           "lost somewhere in this gate")
    print()

    tagmap = {"V3D_TAG_GET_POWER_STATE": "GET_POWER_STATE",
              "V3D_TAG_SET_POWER_STATE": "SET_POWER_STATE",
              "V3D_TAG_GET_CLOCK_STATE": "GET_CLOCK_STATE",
              "V3D_TAG_SET_CLOCK_STATE": "SET_CLOCK_STATE",
              "V3D_TAG_GET_DOMAIN_STATE": "GET_DOMAIN_STATE",
              "V3D_TAG_SET_DOMAIN_STATE": "SET_DOMAIN_STATE"}
    for libname, srcname in tagmap.items():
        expect(lib_constant(libname) == k["tags"][srcname],
               "#%s is $%08X, the headers give $%08X"
               % (libname, lib_constant(libname), k["tags"][srcname]))
    print("%d mailbox tags cross-checked against the pinned tag values"
          % len(tagmap))
    print()

    # The pass criterion the library states in advance.  Recomposed here
    # from the parsed field shifts, so a shift the library got wrong and
    # a shift this gate got wrong cannot cancel each other out.
    want_low12 = ((1 << k["V3D_HUB_IDENT1_NCORES_SHIFT"])
                  | (2 << k["V3D_HUB_IDENT1_REV_SHIFT"])
                  | (4 << k["V3D_HUB_IDENT1_TVER_SHIFT"])) & 0xFFF
    expect(lib_constant("V3D_IDENT1_EXPECT_LOW12") == want_low12,
           "#V3D_IDENT1_EXPECT_LOW12 is $%X; TVER=4 REV=2 NCORES=1 through "
           "the shifts in v3d_regs.h is $%X"
           % (lib_constant("V3D_IDENT1_EXPECT_LOW12"), want_low12))
    print("pass criterion, recomposed from the field shifts: low 12 bits "
          "of HUB_IDENT1 = $%03X" % want_low12)
    print()

    # -----------------------------------------------------------------
    #  THE TWO COMPOSED WORDS, RECOMPOSED.  Both are constants in the
    #  library that are the SUM of several parsed fields, which is
    #  exactly where a transcription error hides: the word looks
    #  plausible and no single field is visibly wrong.
    # -----------------------------------------------------------------
    want_faults = (k["V3D_MMU_CTL_PT_INVALID"]
                   | k["V3D_MMU_CTL_WRITE_VIOLATION"]
                   | k["V3D_MMU_CTL_CAP_EXCEEDED"])
    expect(lib_constant("V3D_MMU_CTL_FAULTS") == want_faults,
           "#V3D_MMU_CTL_FAULTS is $%X; the three sticky status bits in "
           "v3d_regs.h are $%X" % (lib_constant("V3D_MMU_CTL_FAULTS"),
                                   want_faults))
    want_slc = ((0xF << k["SLCACTL_TVCCS_SHIFT"])
                | (0xF << k["SLCACTL_TDCCS_SHIFT"])
                | (0xF << k["SLCACTL_UCC_SHIFT"])
                | (0xF << k["SLCACTL_ICC_SHIFT"]))
    expect(lib_constant("V3D_SLCACTL_ALL") == want_slc,
           "#V3D_SLCACTL_ALL is $%X; 0xF in each of the four fields "
           "v3d_gem.c:221-226 writes is $%X"
           % (lib_constant("V3D_SLCACTL_ALL"), want_slc))
    expect(lib_constant("V3D_MMU_PAGE_BYTES") == 1 << k["V3D_MMU_PAGE_SHIFT"],
           "#V3D_MMU_PAGE_BYTES is %d, but the page shift is %d"
           % (lib_constant("V3D_MMU_PAGE_BYTES"), k["V3D_MMU_PAGE_SHIFT"]))
    expect(lib_constant("V3D_PTE_PFN_LIMIT") == 1 << 24,
           "#V3D_PTE_PFN_LIMIT is $%X; v3d_mmu.c:99's BUG_ON is against "
           "BIT(24)" % lib_constant("V3D_PTE_PFN_LIMIT"))
    print("composed words recomposed from their parsed fields:")
    print("   MMU_CTL sticky faults  $%08X" % want_faults)
    print("   SLCACTL, all four      $%08X" % want_slc)
    print("   a microtile is %dx%d texels at 4 bytes each = %d bytes"
          % (k["UTILE_W"], k["UTILE_H"], k["UTILE_W"] * k["UTILE_H"] * 4))
    print("   texture data formats   RGBA8 %d, R32F %d"
          % (k["TEXFMT_RGBA8"], k["TEXFMT_R32F"]))
    print()

    # -----------------------------------------------------------------
    #  2. THE POSITIVE RUN
    #
    #  STOP HERE IF A CONSTANT IS ALREADY WRONG.  A wrong base address
    #  makes the model raise on an unmodelled MMIO access, and that
    #  exception leaves the process before the accumulated failures are
    #  printed - so the run reports "unmodelled read at $FE00A00C" and
    #  says nothing about the base that caused it.  The proximate
    #  message is true and the useful one is the one above it.
    # -----------------------------------------------------------------
    if fails:
        print("FAIL - a constant disagrees with its source, so the run below")
        print("would only report the consequences.  Fix these first:")
        for f in fails:
            print("   " + f)
        return 1

    img = build()
    good_ident1 = ident1_word(k)

    def fresh(**kw):
        board = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
                      ident1_when_up=good_ident1, **kw)
        fw = Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"])
        return board, fw

    board, fw = fresh()
    x0, text = run(img, k, board, fw)
    print("positive run: verdict %r, x0 $%X" % (verdict_of(text), x0))
    expect(verdict_of(text) == "OK",
           "the healthy model did not produce verdict OK; it said %r"
           % verdict_of(text))
    expect(x0 == want_low12,
           "the probe returned $%X, expected the pass criterion $%X"
           % (x0, want_low12))

    # The bring-up must have actually happened, not been skipped because
    # the model was generous.
    expect((board.grafx & k["PM_V3DRSTN"]) != 0,
           "PM_GRAFX.V3DRSTN is still clear after a clean run - the reset "
           "was never deasserted")
    for name, reg in (("master", k["ASB_V3D_M_CTRL"]),
                      ("slave", k["ASB_V3D_S_CTRL"])):
        expect((board.asb[reg] & k["ASB_REQ_STOP"]) == 0,
               "the ASB %s bridge still has REQ_STOP set" % name)
        expect((board.asb[reg] & k["ASB_ACK"]) == 0,
               "the ASB %s bridge still acknowledges being stopped" % name)
    print("   PM_GRAFX $%06X, ASB master $%X, ASB slave $%X"
          % (board.grafx, board.asb[k["ASB_V3D_M_CTRL"]],
             board.asb[k["ASB_V3D_S_CTRL"]]))

    # Both ASB bridges were written, and PM_GRAFX exactly once.  A
    # second PM write would mean the deassert is being done twice, which
    # is harmless and is also a sign somebody rearranged the sequence.
    expect(board.pm_writes == 1,
           "PM_GRAFX was written %d times, expected exactly 1"
           % board.pm_writes)
    expect(board.v3d_writes == 0,
           "stage 0 wrote %d V3D registers; it must write none"
           % board.v3d_writes)

    # -- the mailbox side actually happened -----------------------------
    tags_seen = {t for t, _ in fw.seen}
    # SET_POWER_STATE IS A FALLBACK, NOT A REQUIREMENT.  v3d.pi4:1778-1782
    # sends the old tag only when SET_DOMAIN_STATE did not answer 1, after
    # the board showed the redundant old tag wedging the property channel.
    # This model's firmware answers 1, so the old tag must be ABSENT here
    # and PRESENT, with device 10, under N9 below, where nothing answers.
    expect(k["tags"]["SET_POWER_STATE"] not in {t for t, _ in fw.seen},
           "the library sent SET_POWER_STATE although SET_DOMAIN_STATE "
           "answered 1.  v3d.pi4:1778-1782 makes the old tag a fallback "
           "because sending it after the new one stopped the property "
           "channel answering on the board.")
    for want_name in ("GET_DOMAIN_STATE", "SET_DOMAIN_STATE",
                      "GET_POWER_STATE",
                      "GET_CLOCK_STATE", "SET_CLOCK_STATE",
                      "GET_CLOCK_RATE", "GET_MAX_CLOCK_RATE",
                      "SET_CLOCK_RATE", "GET_CLOCK_MEASURED"):
        expect(k["tags"][want_name] in tags_seen,
               "the library never issued %s ($%08X)"
               % (want_name, k["tags"][want_name]))
    print("   %d mailbox transactions, %d distinct tags"
          % (len(fw.seen), len(tags_seen)))

    # AND THE IDS IN THEM ARE THE RIGHT ONES.  This is the check that
    # catches the domain-11-versus-device-10 mistake, which is otherwise
    # a silent no-op: the firmware answers happily either way.
    for tag_name, want_id in (("SET_DOMAIN_STATE", k["domain_new"]),
                              ("GET_DOMAIN_STATE", k["domain_new"]),
                              ("GET_POWER_STATE", k["power_old"]),
                              ("SET_CLOCK_STATE", k["clock_id"]),
                              ("GET_CLOCK_RATE", k["clock_id"]),
                              ("SET_CLOCK_RATE", k["clock_id"]),
                              ("GET_CLOCK_MEASURED", k["clock_id"])):
        sent = [w for t, w in fw.seen if t == k["tags"][tag_name]]
        expect(bool(sent) and all(w[0] == want_id for w in sent),
               "%s was sent with id %r, expected %d"
               % (tag_name, [w[0] for w in sent], want_id))
    print("   every tag carried the right id (domain %d, power %d, clock %d)"
          % (k["domain_new"], k["power_old"], k["clock_id"]))

    # THE FIRMWARE LIED AND THE LIBRARY DID NOT CARE.  Every state bit
    # in the model stays 0 while every set replies 1; the run above
    # still ended OK.  This assertion is what makes that deliberate
    # rather than incidental.
    expect(re.search(r"^\s+clock 5 state after\s+0\s*$",
                     text.replace("\r", ""), re.MULTILINE) is not None,
           "the probe did not report the clock state as still 0 - the "
           "model's lying firmware is not reaching the log")
    expect(re.search(r"^\s+clock 5 MEASURED Hz\s+49\d{7}\s*$",
                     text.replace("\r", ""), re.MULTILINE) is not None,
           "the probe did not report a measured clock rate.  MEASURED is "
           "the only clock number on this part that is an observation "
           "rather than an intention (clocks.pi4's header, and the bench "
           "evidence at sdio.pi4:1760-1780); a log without it cannot "
           "distinguish a dark block from an unclocked one.")
    expect("verdict: OK" in text,
           "the library treated a lying state bit as a failure")
    print("   the model's firmware reported every state bit as 0 and every")
    print("   set as 'on'; the library ignored both and passed on IDENT.")
    print()

    # -----------------------------------------------------------------
    #  3. THE NEGATIVE MODELS
    #
    #  A refusal nobody has seen refuse anything is a refusal nobody
    #  knows is broken.  Each of these must produce a NAMED failure.
    # -----------------------------------------------------------------
    print("negative models - each must drive the library to a named error:")

    def negative(label: str, board: Board, fw: Firmware, want: str,
                 extra=None) -> None:
        try:
            x, t = run(img, k, board, fw)
        except SystemExit as e:
            fails.append("%s: the model itself refused - %s" % (label, e))
            return
        got = verdict_of(t)
        ok = got == want
        print("   %-28s -> %-16s %s" % (label, got, "ok" if ok else "WRONG"))
        if not ok:
            fails.append("%s: expected verdict %r, got %r" % (label, want, got))
        if extra is not None:
            extra(board, t)

    # N1 - the legacy bridge ID is wrong.  The library must stop before
    #      writing anything at all, and THE WRITE COUNT IS THE TEST.
    def no_writes(bd: Board, t: str) -> None:
        if bd.pm_writes != 0 or bd.asb_writes != 0:
            fails.append("N1: with a bad bridge ID the library still made "
                         "%d PM and %d ASB writes.  The PM block holds "
                         "PM_RSTC and PM_WDOG."
                         % (bd.pm_writes, bd.asb_writes))
    bd = Board(k, 0xDEADBEEF, k["BCM2835_BRDG_ID"], ident1_when_up=good_ident1)
    negative("bad legacy bridge ID", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "BRIDGE_LEGACY", no_writes)

    # N2 - the rpivid bridge ID is wrong.  Same requirement.
    bd = Board(k, k["BCM2835_BRDG_ID"], 0x00000000, ident1_when_up=good_ident1)
    negative("bad rpivid bridge ID", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "BRIDGE_RPIVID", no_writes)

    # N3 - the PM password is not accepted, so the reset write is
    #      DISCARDED silently, which is what the hardware does.  The
    #      library's read-back is the only thing that can catch it.
    bd = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
               password_rejected=True, ident1_when_up=good_ident1)
    negative("PM write discarded", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "RESET")

    # N4 - a bridge that never stops acknowledging.  This is the one
    #      that would be a HANG on the board if the timeout were wrong,
    #      and the interpreter's step limit is what would catch it here.
    bd = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
               asb_ack_sticks=True, ident1_when_up=good_ident1)
    negative("ASB ACK never clears", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "ASB_MASTER")

    # N5 - the whole sequence works and the hub answers all-ones, the
    #      signature of nothing being there.
    bd = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
               ident1_when_up=0xFFFFFFFF, ident1_when_down=0xFFFFFFFF)
    negative("hub reads all-ones", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "IDENT_ONES")

    # N6 - a V3D 7.1 part.  THE LIBRARY MUST REFUSE, NOT ADAPT: on 7.1
    #      TFU_CS alone moves from $400 to $700 (v3d_regs.h:99), so
    #      shrugging at the version means writing 4.2 offsets into a
    #      different part's register map.
    #
    #      THREE MODELS AND NOT ONE, and the reason is a mutant that
    #      survived while there was only one.  7.1 has BOTH fields
    #      wrong, so either half of the library's version test passing
    #      alone still produces IDENT_VERSION - and deleting the TVER
    #      comparison went undetected because the REV comparison
    #      covered for it.  One model per field is the fix.  A negative
    #      test that can be satisfied by a different check than the one
    #      it is aiming at is not testing that check.
    bd = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
               ident1_when_up=ident1_word(k, tver=7, rev=1))
    negative("a V3D 7.1 part", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "IDENT_VERSION")

    # N6a - only TVER is wrong.  Isolates the TVER comparison.
    bd = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
               ident1_when_up=ident1_word(k, tver=7, rev=2))
    negative("TVER wrong, REV right", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "IDENT_VERSION")

    # N6b - only REV is wrong.  Isolates the REV comparison.  A V3D 4.1
    #       is a real part, not an invented one, and several things in
    #       v3d_regs.h are gated at `ver < 41`.
    bd = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
               ident1_when_up=ident1_word(k, tver=4, rev=1))
    negative("REV wrong, TVER right", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "IDENT_VERSION")

    # N7 - two cores.  v3d_drv.c:302 carries WARN_ON(v3d->cores > 1);
    #      this library refuses instead, because it has no second-core
    #      base and would silently use core 0 for everything.
    bd = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
               ident1_when_up=ident1_word(k, ncores=2))
    negative("two cores reported", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "IDENT_CORES")

    # N8 - the sequence completes and the block stays dark.  The most
    #      likely real failure, and the one whose message has to be
    #      distinguishable from N5's.
    bd = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
               ident1_when_up=0x00000000)
    negative("hub stays dark", bd,
             Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"]),
             "IDENT_ZERO")

    # N9 - the firmware refuses every tag (bit 31 of the tag code left
    #      clear).  The library must still reach IDENT and pass: the
    #      mailbox is belt and braces, not a dependency.
    bd = Board(k, k["BCM2835_BRDG_ID"], k["BCM2835_BRDG_ID"],
               ident1_when_up=good_ident1)
    fw = Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"],
                  answer_tags=False)
    negative("firmware answers nothing", bd, fw, "OK")
    # And the fallback fires, to the OLD device number (v3d.pi4:1780-1781).
    sent_old = [w for t, w in fw.seen if t == k["tags"]["SET_POWER_STATE"]]
    expect(bool(sent_old) and all(w[0] == k["power_old"] for w in sent_old),
           "with no tag answered, SET_POWER_STATE was sent with ids %r; "
           "v3d.pi4:1780-1781 falls back to it, with device %d, when "
           "SET_DOMAIN_STATE does not answer 1"
           % ([w[0] for w in sent_old], k["power_old"]))
    print("   fallback SET_POWER_STATE sent with device %d when nothing answered"
          % k["power_old"])
    print()

    # -----------------------------------------------------------------
    #  N10 - THE LIBRARY'S OWN GUARD, TESTED WITHOUT THE PROBE'S.
    #
    #  N1 and N2 above prove that the PROBE stops on a bad bridge ID.
    #  They do not prove the LIBRARY does, because the probe returns
    #  before V3dInit is ever called.  This enters V3dBringUp() by
    #  symbol, with both bridge IDs wrong, and requires it to come back
    #  with #V3D_ERR_BRIDGE_LEGACY having written nothing.
    #
    #  This is the check that stands between a future caller and a
    #  password-bearing write into the block that holds PM_RSTC and
    #  PM_WDOG.
    # -----------------------------------------------------------------
    bd = Board(k, 0x11111111, 0x22222222, ident1_when_up=good_ident1)
    fw = Firmware(k["tags"], k["clock_id"], k["domain_new"], k["power_old"])
    rc, _ = run(img, k, bd, fw, entry="v3dbringup")
    want_rc = lib_constant("V3D_ERR_BRIDGE_LEGACY")
    print("   %-28s -> returned %d, %d PM writes, %d ASB writes"
          % ("V3dBringUp() alone, bad IDs", rc, bd.pm_writes, bd.asb_writes))
    expect(rc == want_rc,
           "V3dBringUp() called directly with bad bridge IDs returned %d, "
           "expected #V3D_ERR_BRIDGE_LEGACY = %d" % (rc, want_rc))
    expect(bd.pm_writes == 0 and bd.asb_writes == 0,
           "V3dBringUp() made %d PM and %d ASB writes with the bridge "
           "witness failing.  Its own precondition is not doing its job, "
           "and the probe's separate check was covering for it."
           % (bd.pm_writes, bd.asb_writes))
    print()

    # -----------------------------------------------------------------
    #  STAGE 1
    # -----------------------------------------------------------------
    stage1_checks(k, expect, fails)

    # -----------------------------------------------------------------
    #  5. THE STRUCTURAL CHECKS ON THE SOURCE ITSELF
    # -----------------------------------------------------------------
    src = _text(LIB)

    # Comments are stripped first.  The header of v3d.pi4 QUOTES the two
    # XIncludeFile lines a program must write, and an earlier draft of
    # this check went red on its own documentation - which is exactly
    # the shape of false positive that gets a real check deleted.
    code_lines = []
    for line in src.splitlines():
        cut = line.find(";")
        code_lines.append(line if cut < 0 else line[:cut])
    code = "\n".join(code_lines)

    expect(re.search(r"^\s*X?IncludeFile\b", code, re.MULTILINE) is None,
           "v3d.pi4 includes another library.  A library never includes a "
           "library; the PROGRAM includes mailbox.pi4 first.")

    # Every write into the PM or ASB block must go through the one
    # procedure that ORs in the password, and the only Poke naming those
    # bases must be the one inside that procedure.  So: exactly one
    # each, and it has to be the right one.  Counting rather than
    # forbidding is what makes this survive the procedure existing at
    # all, and it still catches a second call site.
    for base, wrapper in (("#V3D_PM_BASE", "V3dPmWrite"),
                          ("#V3D_RPIVID_ASB_BASE", "V3dAsbWrite")):
        pokes = re.findall(r"Poke[LNAXCBI]?\s*\(\s*" + re.escape(base), code)
        expect(len(pokes) == 1,
               "%d Pokes name %s.  Exactly one may exist - the one inside "
               "%s() that ORs in $5A000000. A write without the password "
               "is discarded by the hardware with no fault and no message."
               % (len(pokes), base, wrapper))
        body = re.search(r"Procedure\s+" + wrapper + r"\b.*?EndProcedure",
                         code, re.S)
        expect(body is not None and base in body.group(0),
               "the single Poke into %s is not inside %s()" % (base, wrapper))
        expect(body is not None and "#V3D_PM_PASSWORD" in body.group(0),
               "%s() does not OR in #V3D_PM_PASSWORD" % wrapper)

    # No character literals - the house rule.  A quoted string is fine.
    expect(re.search(r"'.'", code) is None,
           "there is a character literal in v3d.pi4")

    # No unbounded power-off path.  Turning a rail off with no consumer
    # of it is how a board stops working; mailbox.pi4:245-247 makes the
    # same ruling about the power-domain tags.  But a blanket "never
    # cleared" refusal cannot tell that ruling apart from a BOUNDED
    # reset used for ownership handoff (modelled on bcm2835-power.c's
    # own reset authority), which also clears the bit - on purpose, and
    # only long enough to re-assert it before returning.  The rule below
    # is structural instead: prove the self-test first, so a defect in
    # the rule itself is caught before it is trusted to grade the file.
    v3drstn_selftest(expect)
    for msg in v3drstn_violations(code):
        expect(False, msg)

    # -- stage 1's structural rules -----------------------------------
    #
    # ONE WRITE PATH INTO THE HUB AND ONE INTO CORE 0, for the same
    # reason there is one into PM: a second Poke naming those bases is
    # a second place a width or an offset can be wrong, and PokeL
    # versus Poke is a four-versus-eight byte mistake that takes the
    # neighbouring register with it.
    for base, wrapper in (("#V3D_HUB_BASE", "V3dHubWrite"),
                          ("#V3D_CORE0_BASE", "V3dCoreWrite")):
        pokes = re.findall(r"Poke[LNAXCBI]?\s*\(\s*" + re.escape(base), code)
        expect(len(pokes) == 1,
               "%d Pokes name %s.  Exactly one may exist - the one inside "
               "%s()." % (len(pokes), base, wrapper))
        body = re.search(r"Procedure\s+" + wrapper + r"\b.*?EndProcedure",
                         code, re.S)
        expect(body is not None and base in body.group(0),
               "the single Poke into %s is not inside %s()" % (base, wrapper))

    # ICFG IS WRITTEN LAST.  v3d_sched.c:313 - "ICFG kicks off the job."
    # Everything else has to be in place when that store retires, and
    # the ordering is not something a reader can see at a glance in a
    # list of eight near-identical calls.
    submit = re.search(r"Procedure\.i\s+V3dTfuSubmit\b.*?EndProcedure",
                       code, re.S)
    expect(submit is not None, "V3dTfuSubmit() is gone")
    if submit:
        written = re.findall(r"V3dHubWrite\(\s*(#V3D_TFU_\w+)",
                             submit.group(0))
        expect(written and written[-1] == "#V3D_TFU_ICFG",
               "the last TFU register V3dTfuSubmit() writes is %r.  ICFG "
               "must be last - v3d_sched.c:313 says it is what starts the "
               "job - so anything written after it is written to a running "
               "engine." % (written[-1] if written else None))
        for need in ("#V3D_TFU_IIA", "#V3D_TFU_IIS", "#V3D_TFU_ICA",
                     "#V3D_TFU_IUA", "#V3D_TFU_IOA", "#V3D_TFU_IOS",
                     "#V3D_TFU_COEF0"):
            expect(need in written,
                   "V3dTfuSubmit() never writes %s.  The kernel writes all "
                   "seven every time (v3d_sched.c:299-307) because they are "
                   "STATE and the block may have been used before." % need)

    # SUPERPAGE IS NEVER SET.  v3d_mmu.c:24-26 warns that every PTE of a
    # 1 MB superpage has to carry the bit; a partial set is a footgun
    # with no benefit at these sizes and the constant exists only so
    # that a reader knows bit 31 is spoken for.
    expect(re.search(r"[|=]\s*#V3D_PTE_SUPERPAGE", code) is None,
           "something in v3d.pi4 sets #V3D_PTE_SUPERPAGE")

    # And exactly one place BUILDS a page table entry.  Two mentions of
    # the constant: its own definition, and the single PokeL in
    # V3dMmuMap().  A third would be a second entry format.
    ptes = re.findall(r"#V3D_PTE_VALID", code)
    expect(len(ptes) == 2,
           "%d places name #V3D_PTE_VALID.  Two - its definition and the "
           "one PokeL in V3dMmuMap() that builds an entry." % len(ptes))
    mapbody = re.search(r"Procedure\.i\s+V3dMmuMap\b.*?EndProcedure",
                        code, re.S)
    expect(mapbody is not None and "#V3D_PTE_VALID" in mapbody.group(0),
           "the one use of #V3D_PTE_VALID is not inside V3dMmuMap()")

    print("structural checks on v3d.pi4: no library include, exactly one")
    print("passworded write path into PM and into ASB, one write path into")
    print("the hub and one into core 0, ICFG written last with all seven")
    print("registers before it, one page-table-entry writer, no SUPERPAGE,")
    print("no character literal, no power-off path.")
    print()

    if fails:
        print("FAIL")
        for f in fails:
            print("   " + f)
        return 1

    print("PASS - and read the docstring before believing it means the GPU")
    print("works.")
    print()
    print("WHAT IS PROVEN.  Every one of the library's constants checked")
    print("above matches its pinned source value - the TFU offsets as the")
    print("4.2 arm of v3d_regs.h's version-gated macros, the block bases by")
    print("running the device tree's legacy addresses through the manual's")
    print("translation rule, the microtile geometry as parsed from Mesa's")
    print("tiling source.  The stage 0 bring-up is issued in the right order")
    print("with the right three ids, and no write reaches the PM block until")
    print("both bridges have answered.  Stage 1 builds a page table the model")
    print("then WALKS, and a TFU model EXECUTES three jobs through it and puts")
    print("real bytes in real memory, which the payload reads back and checks.")
    print("Every MMIO access is 4-byte aligned and 4 bytes wide.  Mutated")
    print("models and crafted arguments each produce the named failure,")
    print("including a unit that increments its completion counter and")
    print("writes nothing, which a register-level check cannot see.  The")
    print("fault classes this model cannot represent are named in the")
    print("docstring.")
    print()
    print("WHAT IS NOT PROVEN, AND CANNOT BE ON THIS MACHINE.  That")
    print("$FEC0000C reads $2124.  That the TFU exists and answers.  That")
    print("LINEARTILE on silicon is the layout Mesa's tiling source")
    print("describes - the payload and this file are two transcriptions of")
    print("one document and agreeing means they read it the same way.  And")
    print("nothing whatever about cache coherency: this model has a flat")
    print("dictionary for memory, so it would pass with every")
    print("V3dCacheRange() call in v3d.pi4 deleted.  Only the board can say.")
    return 0


def main() -> int:
    global COMPILER, WORKDIR
    ap = argparse.ArgumentParser(description="Executable gate for RaspberryPi4/Lib/v3d.pi4.")
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge compiler executable")
    args = ap.parse_args()
    if not args.compiler:
        ap.error("No compiler was named.  Pass --compiler or set PMF_COMPILER to the "
                 "PureMetalForge executable.")
    COMPILER = args.compiler
    with tempfile.TemporaryDirectory(prefix="v3d-check-") as td:
        WORKDIR = pathlib.Path(td)
        return _main()


if __name__ == "__main__":
    raise SystemExit(main())
