#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/sdio.pi4 and Anvil/Net/cyw43.pbi.

No CYW43455 is attached to a desk, so both sides of the bus are modelled
here: an SDHCI controller at the Arasan block's address, an SDIO card
behind it with two I/O functions, a backplane with a chip ID and an EROM
table on it, and a VideoCore that answers the property mailbox.

The program executed is the REAL ARTEFACT -
RaspberryPi4/Examples/Diagnostics/pi4SdioProbe.pi4 by default, or
pi4WifiScan.pi4 with --scan - compiled by the PureMetal compiler and run
on this repository's A64 interpreter (tools/a64/a64_interp.py).  Its
serial output is printed below, so the log here is what the board will
say before the board says it.

NOTHING THE MODEL CHECKS AGAINST IS TRANSCRIBED FROM THE LIBRARIES.
Every register offset, command opcode, argument field, CCCR address,
backplane constant, chip-ID mask and struct layout comes from the
published vendor sources the libraries cite.  Those sources are
third-party code and are NOT copied into this repository: the values
this gate needs are pinned in the PINNED table below, each one with the
upstream project, version, file and line it was read from, so every
number can be checked against the upstream tree:

    Linux v6.12                     include/linux/mmc/sdio.h, mmc.h, sd.h
                                    drivers/mmc/core/sdio_ops.c
                                    drivers/net/wireless/broadcom/brcm80211/
                                      brcmfmac/{sdio.h,sdio.c,bcmsdh.c,chip.c,
                                      firmware.c,bcdc.c,fweh.h,fwil.h,
                                      fwil_types.h}
                                      include/{soc.h,chipcommon.h,
                                      brcm_hw_ids.h,brcmu_wifi.h}
    Raspberry Pi Linux rpi-6.12.y   drivers/mmc/host/sdhci.h
                                    arch/arm/boot/dts/broadcom/bcm270x.dtsi,
                                      bcm2711.dtsi, bcm2711-rpi-ds.dtsi
                                    include/dt-bindings/pinctrl/bcm2835.h
                                    drivers/gpio/gpio-raspberrypi-exp.c
    Linux                           include/soc/bcm2835/raspberrypi-firmware.h
    U-Boot v2025.01                 arch/arm/mach-bcm283x/include/mach/mbox.h
                                    drivers/mmc/bcm2835_sdhost.c (a NEGATIVE
                                      claim)
    Raspberry Pi                    BCM2711 ARM Peripherals document, the
                                      GPIO_PUP_PDN_CNTRL field encoding

The library and the gate are then two independent readings of one set of
documents and CAN DISAGREE.  If a constant in sdio.pi4 or cyw43.pi4 is
edited, this goes red.

WHAT IS ASSERTED, beyond "the probe printed plausible numbers"

  * the controller base is DERIVED from bcm270x.dtsi's mmcnr node
    through bcm2711.dtsi's soc ranges, and every MMIO access the image
    makes lands inside that node's declared window
  * sdhost is NOT touched, and the U-Boot driver's own header is cited
    for why it could not work if it were
  * the six SDIO pins are muxed to the function the device tree names,
    with the pulls the device tree names, and NOTHING ELSE in either
    GPIO register moves
  * WL_ON is known high through the mailbox BEFORE the first SD command
  * the base clock is fetched for mailbox clock id EMMC, not EMMC2
  * every command index issued is one of the six opcodes the headers
    define, and each carries the response flags its response type allows
    - in particular CMD5 carries NO CRC and NO index check, because R4
    has neither and enabling them makes the controller reject a good
    response
  * every CMD52 and CMD53 argument decodes, through the sdio_ops.c
    packing, to the function and register the caller asked for
  * the backplane window is programmed with the address SHIFTED RIGHT
    EIGHT, in three byte writes, to the three cited registers
  * every 32-bit backplane access carries SBSDIO_SB_ACCESS_2_4B_FLAG and
    an offset inside SBSDIO_SB_OFT_ADDR_MASK
  * the chip ID is read from SI_ENUM_BASE + offsetof(chipid), and the
    probe reports the fields the modelled register actually encodes
  * the EROM walk finds exactly the cores the modelled table contains,
    with the right ids, revisions and bases - including one deliberately
    awkward core with a size descriptor and a 64-bit address descriptor,
    which is where a walker desynchronises if it gets the skip wrong
  * block-mode CMD53 reads the same bytes as byte mode, the RAM walk and
    the first bulk write hold up, and Cyw43Start refuses with no image
  * with --scan: the SDPCM framing, the CLM chunking, the escan request,
    the bss_info layout, the duplicate fold, and the cooked NVRAM image
    that lands at the top of chip RAM

EVERY DATA ACCESS IS ALIGNMENT-CHECKED through the interpreter's shared
rule (A64.align_guard, named by attach_symbols).  This gate is where that
rule came from: on 2026-08-27 --scan passed on a cyw43.pi4 that wrote a
u32 two bytes off a word boundary and wedged the board.  With the MMU off
every data access is Device memory, where an unaligned wide access is an
Alignment fault whatever SCTLR.A says; see the note above AlignmentFault
in tools/a64/a64_interp.py.

WHAT THIS GATE CANNOT DO

  * Association.  Nothing about the join is modelled: an offline model
    cannot fail an authentication, and the interesting answers come from
    the access point at the other end of the radio.
  * The CLM's CONTENT and the scan_ver verdict - only silicon can say
    whether the firmware parses the blob, and which escan version it
    accepts.
  * The board's NVRAM.  The real NVRAM text is board calibration and
    identity data and is not distributed with this repository (see
    Firmware/CYW43455/README.txt), so --scan uploads a SYNTHETIC text by
    default and derives its expected cooked image from firmware.c's
    parser rules.  Pass --nvram with a board's file to upload that
    instead.
  * Timing.  The modelled counter runs deliberately fast; every wait in
    both libraries is a deadline, not a calibration.

Run:  python tools/a64/a64_sdio_check.py --compiler <PureMetalForge>
      python tools/a64/a64_sdio_check.py --compiler <...> --verbose
      python tools/a64/a64_sdio_check.py --compiler <...> --scan
      (PMF_COMPILER may stand in for --compiler.)
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "tools" / "a64"
sys.path.insert(0, str(HERE))
from a64_interp import A64, AlignmentFault, attach_symbols  # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

# The CYW43455 firmware image and CLM blob Anvil ships for the Raspberry
# Pi 4's radio.  The scan gate loads these exact bytes into DRAM, where
# Anvil's `load` puts them on the board.
FIRMWARE = ROOT / "Firmware" / "CYW43455"

# =====================================================================
#  THE NETWORKS THE MODELLED FIRMWARE REPORTS
#
#  Chosen to be awkward on purpose. A scan list that is five ordinary
#  names proves the happy path and nothing else:
#
#    * a HIDDEN network - SSID_len 0. The list must show it as hidden
#      rather than as an empty row or as the previous entry's name.
#    * a FULL-LENGTH name - exactly 32 bytes, the maximum. One byte of
#      over-read here would run into the rateset that follows.
#    * a name with a BYTE THAT IS NOT PRINTABLE. It arrives from the
#      air and must not be able to move the cursor.
#    * a NEGATIVE RSSI near the bottom of the range, so a driver that
#      reads it unsigned prints 65491 instead of -45.
#    * channels in both bands, including one above 14, so a channel
#      byte read from the wrong half of chanspec is visible.
#
#  ctl_ch is set EQUAL to chanspec's low byte in every entry, so
#  cyw43.pi4's channel cross-check must come back zero. A non-zero
#  count in the log means one of the two offsets is wrong.
# =====================================================================
MODEL_BSS = [
    # (ssid bytes, channel, rssi, privacy) - the FIRST sighting of each
    (b"PureMetalForge", 6, -45, 1),
    (b"", 1, -62, 0),                       # hidden
    (b"A" * 32, 11, -70, 1),                # the longest name allowed
    (b"caf\xc3\xa9-guest", 44, -55, 0),     # UTF-8: two non-ASCII bytes
    (b"nc-2", 149, -88, 1),                 # 5 GHz, channel > 14
]

# =====================================================================
#  AND THE SAME NETWORKS HEARD AGAIN
#
#  MODEL_BSS is the list of DISTINCT access points. Real escan does not
#  send a distinct list: it sends one PARTIAL event per beacon or probe
#  response the radio heard, so a scan hears an AP several times and the
#  host is what merges them.  On the bench, five records arrived for two
#  real networks.
#
#  WITHOUT THIS LIST THE FOLD SHIPS UNTESTED.  Five records with five
#  different BSSIDs pass identically whether cyw43_ParseBss folds or
#  appends, so the model has to say the same thing twice before the
#  merge is exercised at all.
#
#  Each entry is (before, index, rssi): the repeat of MODEL_BSS[index]
#  is emitted immediately BEFORE original number `before`, carrying
#  `rssi`.  Everything else - SSID, channel, privacy, and therefore the
#  BSSID, which _bss_record derives from the channel - is identical to
#  the original, which is what makes it a duplicate rather than a sixth
#  network.
#
#  THE RSSIs ARE CHOSEN TO PIN DOWN WHICH ONE SURVIVES.  A fold that
#  kept the LAST reading and a fold that kept the BEST one are the same
#  program on a list where every repeat is stronger than the one before,
#  so one repeat here is stronger than the first sighting and one is
#  weaker AND LAST.  The row must end up showing the strongest of the
#  three; -77 must not appear anywhere in the network list.
#
#  The last entry repeats a network with EVERY FIELD IDENTICAL, which is
#  the ordinary case and the one a comparison written against the wrong
#  offset still passes - so it is here beside the awkward ones, not
#  instead of them.
# =====================================================================
MODEL_BSS_REPEATS = [
    (2, 0, -39),                # stronger than PureMetalForge's -45
    (5, 0, -77),                # weaker, and the LAST word on that BSSID
    (5, 4, -88),                # nc-2 again, byte for byte
]

PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4SdioProbe.pi4"
SCAN = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4WifiScan.pi4"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0

UART_DR = 0xFE201000
UART_FR = 0xFE201018

MBX_READ = 0xFE00B880
MBX_STATUS0 = 0xFE00B898
MBX_WRITE = 0xFE00B8A0
MBX_STATUS1 = 0xFE00B8B8
MBX_EMPTY = 0x40000000
MBX_CHANNEL = 8
BUS_OFFSET = 0xC0000000

GPIO_BASE = 0xFE200000
GPFSEL3 = GPIO_BASE + 0x0C
GPPUP2 = GPIO_BASE + 0xEC

CNTFRQ = 54_000_000
# HOW FAST THE MODELLED COUNTER RUNS.  This is a knob, not a
# measurement, and it is turned up hard on purpose: sdio.pi4 spends a
# millisecond letting the bus power settle and ten milliseconds between
# CMD5 tries, which at a realistic ratio would be several million
# interpreter steps of doing nothing.  Every wait in both libraries is a
# DEADLINE and none of them is a calibration, so making the clock fast
# shortens the run without changing any decision the code takes.  The
# one thing it must not do is stop advancing - a frozen counter turns
# every bounded wait into an unbounded one.
TICKS_PER_STEP = 64

# What the modelled card is.  Chip id $4345, revision 6 - which is
# inside the mask sdio.c line 652 gives for the 43455 firmware, so the
# probe must report "CYW43455".
MODEL_CHIP_ID = 0x4345
MODEL_CHIP_REV = 6
MODEL_CHIP_PKG = 0
MODEL_CHIP_CCOUNT = 8
MODEL_RCA = 0x0001
# The I/O OCR the modelled card publishes: 2.7V through 3.4V, which is
# the usual shape and which overlaps the 3.2-3.4 window sdio.pi4 asks
# for.  If the library ever asked for a window outside this, the model
# refuses rather than pretending.
MODEL_OCR = 0x00FF8000
MODEL_NFUNC = 2
MODEL_EROM_ADDR = 0x18010000
# The 16K region the fourth core carries ahead of its real registers.
# Nothing may ever report this as a core's base - see Cyw43Card._build_erom.
AWKWARD_REGION = 0x18F00000


# ---- the modelled ARM CR4 -------------------------------------------------
# The register base must match the fourth core in _build_erom's table; the
# offsets are chip.c's, lines 205-217.
MODEL_CR4_BASE     = 0x18003000
ARMCR4_CAP         = 0x04
ARMCR4_BANKIDX     = 0x40
ARMCR4_BANKINFO    = 0x44
MODEL_CR4_NAB      = 3
MODEL_CR4_NBB      = 3
MODEL_CR4_BANKINFO = 15
MODEL_RAMSIZE      = ((MODEL_CR4_NAB + MODEL_CR4_NBB)
                      * (MODEL_CR4_BANKINFO + 1) * 8192)
# chip.c lines 713-714: the base is a TABLE LOOKUP on the chip id, not
# anything the chip reports, and $198000 is the entry for a $4345.
MODEL_RAMBASE      = 0x00198000

# bcm2835-mmc.c line 1360 (rpi-6.12.y drivers/mmc/host/bcm2835-mmc.c), "mmc->max_blk_size = 512". One of the three
# bounds in sdio_max_byte_size(); on this board it is never the binding
# one, and it is here so the model takes a minimum rather than assuming
# which term wins.
MODEL_HOST_MAX_BLK_SIZE = 512
# Function 1's block size is NOT aliased here. It is parsed out of
# bcmsdh.c line 44 into k["SDIO_FUNC1_BLOCKSIZE"] and the assertions use
# it from there, so the ceiling this gate checks against comes from the
# vendor source and not from a number typed into this file.


# =====================================================================
#  THE VENDOR FACTS, PINNED AND CITED
#
#  Each entry is NAME: (value, line) under the upstream file it was read
#  from.  The files are third-party source code and are deliberately not
#  in this repository; a reader verifies an entry by opening the cited
#  line in the named upstream tree.  THESE VALUES WERE NOT TAKEN FROM
#  sdio.pi4 OR cyw43.pi4 - that is the whole point of the gate.
#
#  A value that needs changing here means the upstream document changed,
#  and then the libraries need looking at too.
# =====================================================================

LINUX = "Linux v6.12"
RPI = "Raspberry Pi Linux rpi-6.12.y"
UBOOT = "U-Boot v2025.01"
BRCMF = "drivers/net/wireless/broadcom/brcm80211/brcmfmac/"
BRCMU = "drivers/net/wireless/broadcom/brcm80211/include/"

PINNED: dict = {}


def _pin(project: str, path: str, table: dict) -> None:
    for name, (value, line) in table.items():
        if name in PINNED:
            raise SystemExit(
                "The pinned vendor constant %s is declared twice; the second "
                "declaration would silently replace the first." % name)
        PINNED[name] = (value, "%s %s:%s" % (project, path, line))


_pin(RPI, "drivers/mmc/host/sdhci.h", {
    "SDHCI_BLOCK_SIZE": (0x04, 30), "SDHCI_BLOCK_COUNT": (0x06, 33),
    "SDHCI_ARGUMENT": (0x08, 35), "SDHCI_TRANSFER_MODE": (0x0C, 37),
    "SDHCI_TRNS_BLK_CNT_EN": (0x02, 39), "SDHCI_TRNS_READ": (0x10, 43),
    "SDHCI_TRNS_MULTI": (0x20, 44), "SDHCI_COMMAND": (0x0E, 46),
    "SDHCI_CMD_RESP_MASK": (0x03, 47), "SDHCI_CMD_CRC": (0x08, 48),
    "SDHCI_CMD_INDEX": (0x10, 49), "SDHCI_CMD_DATA": (0x20, 50),
    "SDHCI_CMD_RESP_NONE": (0x00, 53), "SDHCI_CMD_RESP_LONG": (0x01, 54),
    "SDHCI_CMD_RESP_SHORT": (0x02, 55),
    "SDHCI_CMD_RESP_SHORT_BUSY": (0x03, 56),
    # SDHCI_MAKE_CMD(c, f) is (((c & 0xff) << 8) | (f & 0xff)): the shape
    # of the 16-bit command register, which decides whether the index
    # lands at bit 24 or bit 26 of the 32-bit word written at $0C.
    "CMD_INDEX_SHIFT_IN_HALFWORD": (8, 58),
    "SDHCI_RESPONSE": (0x10, 61), "SDHCI_BUFFER": (0x20, 63),
    "SDHCI_PRESENT_STATE": (0x24, 65), "SDHCI_CMD_INHIBIT": (0x01, 66),
    "SDHCI_DATA_INHIBIT": (0x02, 67), "SDHCI_SPACE_AVAILABLE": (0x400, 70),
    "SDHCI_DATA_AVAILABLE": (0x800, 71), "SDHCI_HOST_CONTROL": (0x28, 83),
    "SDHCI_CTRL_4BITBUS": (0x02, 85), "SDHCI_POWER_CONTROL": (0x29, 97),
    "SDHCI_POWER_ON": (0x01, 98), "SDHCI_POWER_330": (0x0E, 101),
    "SDHCI_CLOCK_CONTROL": (0x2C, 117), "SDHCI_DIVIDER_SHIFT": (8, 118),
    "SDHCI_DIVIDER_HI_SHIFT": (6, 119), "SDHCI_DIV_MASK": (0xFF, 120),
    "SDHCI_DIV_HI_MASK": (0x300, 122), "SDHCI_CLOCK_CARD_EN": (0x04, 124),
    "SDHCI_CLOCK_INT_STABLE": (0x02, 126), "SDHCI_CLOCK_INT_EN": (0x01, 127),
    "SDHCI_TIMEOUT_CONTROL": (0x2E, 129), "SDHCI_SOFTWARE_RESET": (0x2F, 131),
    "SDHCI_RESET_ALL": (0x01, 132), "SDHCI_RESET_CMD": (0x02, 133),
    "SDHCI_RESET_DATA": (0x04, 134), "SDHCI_INT_STATUS": (0x30, 136),
    "SDHCI_INT_ENABLE": (0x34, 137), "SDHCI_SIGNAL_ENABLE": (0x38, 138),
    "SDHCI_INT_RESPONSE": (0x01, 139), "SDHCI_INT_DATA_END": (0x02, 140),
    "SDHCI_INT_SPACE_AVAIL": (0x10, 143), "SDHCI_INT_DATA_AVAIL": (0x20, 144),
    "SDHCI_INT_CARD_INT": (0x100, 147), "SDHCI_INT_TIMEOUT": (0x10000, 151),
    "SDHCI_INT_ERROR_MASK": (0xFFFF8000, 164),
    "SDHCI_CAPABILITIES": (0x40, 210), "SDHCI_CLOCK_BASE_SHIFT": (8, 215),
    "SDHCI_CAPABILITIES_1": (0x44, 231), "SDHCI_HOST_VERSION": (0xFE, 279),
    "SDHCI_VENDOR_VER_SHIFT": (8, 281), "SDHCI_SPEC_VER_MASK": (0xFF, 282),
})

# The controller's address.  The mmcnr node's unit address and its reg
# property agree, and it is "brcm,bcm2835-sdhci" compatible - the whole
# register map above rests on that compatible string.
_pin(RPI, "arch/arm/boot/dts/broadcom/bcm270x.dtsi", {
    "MMCNR_BUS": (0x7E300000, "50-52"),
    "MMCNR_SIZE": (0x100, 52),
    "MMCNR_IS_SDHCI": (1, 51),
})
# The bus -> ARM translation: the soc node's
# ranges = <0x7e000000 0x0 0xfe000000 0x01800000>.
_pin(RPI, "arch/arm/boot/dts/broadcom/bcm2711.dtsi", {
    "SOC_BUS_BASE": (0x7E000000, 41),
    "SOC_ARM_BASE": (0xFE000000, 41),
    "SOC_WINDOW": (0x01800000, 41),
})
_pin(RPI, "arch/arm/boot/dts/broadcom/bcm2711-rpi-ds.dtsi", {
    "SDIO_PINS": ((34, 35, 36, 37, 38, 39), 318),
    # brcm,function = <BCM2835_FSEL_ALT3>
    "SDIO_FSEL_NAME": ("BCM2835_FSEL_ALT3", 319),
    "SDIO_PULLS": ((0, 2, 2, 2, 2, 2), 320),
})
_pin(RPI, "include/dt-bindings/pinctrl/bcm2835.h", {
    "BCM2835_FSEL_ALT3": (7, 19),
    "BCM2835_PUD_OFF": (0, 22), "BCM2835_PUD_DOWN": (1, 23),
    "BCM2835_PUD_UP": (2, 24),
})
# THE PULL ENCODINGS.  TWO OF THEM, AND THEY DISAGREE.
# This check once compared the BCM2711's GPIO_PUP_PDN_CNTRL field straight
# against the device tree's brcm,pull number, and it PASSED while the
# library programmed a pull-DOWN on CMD and on all four DAT lines.  The
# gate had been built from the same misreading as the library.  So both
# numberings are pinned from their own documents and the translation
# between them is explicit.  The register's, from the peripherals
# document's GPIO_PUP_PDN_CNTRL_REG field description:
#     00 = no resistor, 01 = pull up, 10 = pull down
_pin("Raspberry Pi", "BCM2711 ARM Peripherals, GPIO_PUP_PDN_CNTRL_REGn", {
    "REG_PULL_NONE": (0b00, "field table"),
    "REG_PULL_UP": (0b01, "field table"),
    "REG_PULL_DOWN": (0b10, "field table"),
})

_pin(LINUX, "include/linux/mmc/sdio.h", {
    "SD_IO_SEND_OP_COND": (5, 12), "SD_IO_RW_DIRECT": (52, 13),
    "SD_IO_RW_EXTENDED": (53, 14),
    "R4_18V_PRESENT": (1 << 24, 37), "R4_MEMORY_PRESENT": (1 << 27, 38),
    "R5_OUT_OF_RANGE": (1 << 8, 59),
    "SDIO_CCCR_CCCR": (0x00, 67), "SDIO_CCCR_IOEx": (0x02, 87),
    "SDIO_CCCR_IORx": (0x03, 88), "SDIO_CCCR_ABORT": (0x06, 93),
    "SDIO_CCCR_IF": (0x07, 95), "SDIO_BUS_WIDTH_MASK": (0x03, 97),
    "SDIO_BUS_WIDTH_4BIT": (0x02, 100), "SDIO_BUS_CD_DISABLE": (0x80, 106),
    "SDIO_CCCR_CAPS": (0x08, 108),
    # SDIO_FBR_BASE(f) is ((f) * 0x100)
    "SDIO_FBR_STEP": (0x100, 171),
    "SDIO_FBR_BLKSIZE": (0x10, 192),
})
_pin(LINUX, "include/linux/mmc/mmc.h", {
    "MMC_GO_IDLE_STATE": (0, 31), "MMC_SELECT_CARD": (7, 38),
    "MMC_CARD_BUSY": (0x80000000, 206),
})
_pin(LINUX, "include/linux/mmc/sd.h", {"SD_SEND_RELATIVE_ADDR": (3, 14)})
# How mmc_io_rw_direct_host() and mmc_io_rw_extended() pack the argument.
_pin(LINUX, "drivers/mmc/core/sdio_ops.c", {
    "ARG_ADDR_MAX": (0x1FFFF, 72),         # if (addr & ~0x1FFFF)
    "ARG_WRITE": (0x80000000, 76),         # write ? 0x80000000 : 0
    "ARG_FN_SHIFT": (28, 77),              # fn << 28
    "ARG_RAW": (0x08000000, 78),           # (write && out) ? 0x08000000
    "ARG_ADDR_SHIFT": (9, 79),             # addr << 9
    "ARG_INCR": (0x04000000, 138),         # incr_addr ? 0x04000000
    "ARG_BLOCKMODE": (0x08000000, 143),    # 0x08000000 | blocks
    "ABORT_RES": (0x08, 213),              # abort |= 0x08
})

_pin(LINUX, BRCMF + "sdio.h", {
    "SDIO_FUNC_ENABLE_1": (0x02, 16), "SDIO_FUNC_ENABLE_2": (0x04, 17),
    "SBSDIO_FUNC1_SBADDRLOW": (0x1000A, 75),
    "SBSDIO_FUNC1_SBADDRMID": (0x1000B, 77),
    "SBSDIO_FUNC1_SBADDRHIGH": (0x1000C, 79),
    "SBSDIO_FUNC1_CHIPCLKCSR": (0x1000E, 83),
    "SBSDIO_FUNC1_SDIOPULLUP": (0x1000F, 85),
    "SBSDIO_SB_OFT_ADDR_MASK": (0x07FFF, 122),
    "SBSDIO_SB_ACCESS_2_4B_FLAG": (0x08000, 125),
    "SBSDIO_SBWINDOW_MASK": (0xFFFF8000, 128),
})
_pin(LINUX, BRCMF + "sdio.c", {
    "BRCMF_FIRSTREAD": (1 << 6, 136),
    "SBSDIO_FORCE_ALP": (0x01, 177), "SBSDIO_FORCE_HT": (0x02, 179),
    "SBSDIO_ALP_AVAIL_REQ": (0x08, 183), "SBSDIO_HT_AVAIL_REQ": (0x10, 185),
    "SBSDIO_FORCE_HW_CLKREQ_OFF": (0x20, 187),
    "SBSDIO_ALP_AVAIL": (0x40, 189), "SBSDIO_HT_AVAIL": (0x80, 191),
    "SMB_DATA_VERSION_SHIFT": (16, 260), "SDPCM_PROT_VERSION": (4, 290),
    "SDPCM_HWHDR_LEN": (4, 1328), "SDPCM_SWHDR_LEN": (8, 1330),
    "SDPCM_SEQ_MASK": (0x000000FF, 1333),
    "SDPCM_CHANNEL_MASK": (0x00000F00, 1335), "SDPCM_CHANNEL_SHIFT": (8, 1336),
    "SDPCM_CONTROL_CHANNEL": (0, 1337), "SDPCM_EVENT_CHANNEL": (1, 1338),
    "SDPCM_DATA_CHANNEL": (2, 1339), "SDPCM_GLOM_CHANNEL": (3, 1340),
    "SDPCM_NEXTLEN_SHIFT": (16, 1344), "SDPCM_DOFFSET_SHIFT": (24, 1346),
    "SDPCM_WINDOW_SHIFT": (8, 1349),
})
# The firmware table: brcmf_sdio_fwnames[] has one entry per revision
# group of a chip, BRCMF_FW_ENTRY(chip, revmask, name).  For chip $4345:
FW_4345_ENTRIES = (
    (0x00000200, 43456, LINUX + " " + BRCMF + "sdio.c:651"),
    (0xFFFFFDC0, 43455, LINUX + " " + BRCMF + "sdio.c:652"),
)
# ... and the selection rule, firmware.c:813,
#     mapping_table[i].revmask & BIT(chiprev)
# so the mask is a BITMAP OVER REVISION NUMBERS (firmware.h: "bitmask of
# revisions, e.g. 0x10 means rev 4 only").  Taking the first 4345 entry
# gives the 43456, which is a different part; the rule is applied below.
FW_SELECT_RULE = LINUX + " " + BRCMF + "firmware.c:813"

_pin(LINUX, BRCMU + "brcm_hw_ids.h", {"BRCM_CC_4345_CHIP_ID": (0x4345, 34)})
_pin(LINUX, BRCMU + "soc.h", {"SI_ENUM_BASE_DEFAULT": (0x18000000, 9)})
_pin(LINUX, BRCMU + "chipcommon.h", {
    # The struct's own offset comments, "u32 chipid; /* 0x0 */" and
    # "u32 eromptr; /* 0xfc */"; cyw43.pi4 cites the same comments.
    "CC_CHIPID": (0x00, 14), "CC_EROMPTR": (0xFC, 107),
    "CID_ID_MASK": (0x0000FFFF, 222), "CID_REV_MASK": (0x000F0000, 223),
    "CID_REV_SHIFT": (16, 224), "CID_PKG_MASK": (0x00F00000, 225),
    "CID_PKG_SHIFT": (20, 226), "CID_CC_MASK": (0x0F000000, 227),
    "CID_CC_SHIFT": (24, 228), "CID_TYPE_MASK": (0xF0000000, 229),
    "CID_TYPE_SHIFT": (28, 230),
})
_pin(LINUX, BRCMF + "chip.c", {
    "SOCI_SB": (0, 21), "SOCI_AI": (1, 22),
    "DMP_DESC_TYPE_MSK": (0x0000000F, 25), "DMP_DESC_EMPTY": (0x00000000, 26),
    "DMP_DESC_VALID": (0x00000001, 27), "DMP_DESC_COMPONENT": (0x00000001, 28),
    "DMP_DESC_MASTER_PORT": (0x00000003, 29),
    "DMP_DESC_ADDRESS": (0x00000005, 30),
    "DMP_DESC_ADDRSIZE_GT32": (0x00000008, 31),
    "DMP_DESC_EOT": (0x0000000F, 32),
    "DMP_COMP_PARTNUM": (0x000FFF00, 36), "DMP_COMP_PARTNUM_S": (8, 37),
    "DMP_COMP_REVISION": (0xFF000000, 40), "DMP_COMP_REVISION_S": (24, 41),
    "DMP_COMP_NUM_SWRAP": (0x00F80000, 42), "DMP_COMP_NUM_SWRAP_S": (19, 43),
    "DMP_COMP_NUM_MWRAP": (0x0007C000, 44), "DMP_COMP_NUM_MWRAP_S": (14, 45),
    "DMP_SLAVE_ADDR_BASE": (0xFFFFF000, 56),
    "DMP_SLAVE_TYPE": (0x000000C0, 60), "DMP_SLAVE_TYPE_S": (6, 61),
    "DMP_SLAVE_TYPE_SLAVE": (0, 62), "DMP_SLAVE_TYPE_SWRAP": (2, 64),
    "DMP_SLAVE_SIZE_TYPE": (0x00000030, 66), "DMP_SLAVE_SIZE_TYPE_S": (4, 67),
    "DMP_SLAVE_SIZE_4K": (0, 68), "DMP_SLAVE_SIZE_8K": (1, 69),
    "DMP_SLAVE_SIZE_DESC": (3, 71),
})
_pin(LINUX, BRCMF + "bcmsdh.c", {
    "SDIO_FUNC1_BLOCKSIZE": (64, 44), "SDIO_FUNC2_BLOCKSIZE": (512, 45),
})

# -- THE TRANSPORT --------------------------------------------------------
_pin(LINUX, BRCMF + "bcdc.c", {
    "BCDC_DCMD_ERROR": (0x01, 34), "BCDC_DCMD_SET": (0x02, 35),
    "BCDC_DCMD_IF_SHIFT": (12, 37), "BCDC_DCMD_ID_SHIFT": (16, 39),
    "BCDC_HEADER_LEN": (4, 47), "BCDC_PROTO_VER": (2, 48),
    "BCDC_FLAG_VER_SHIFT": (4, 50),
})
_pin(LINUX, BRCMF + "fwil.h", {
    "BRCMF_C_UP": (2, 13), "BRCMF_C_GET_VAR": (262, 78),
    "BRCMF_C_SET_VAR": (263, 79),
})
_pin(LINUX, BRCMF + "fweh.h", {
    # BRCMF_ENUM_DEF(ESCAN_RESULT, 69) in the X-macro event list
    "BRCMF_E_ESCAN_RESULT": (69, 89),
    "BRCMF_E_STATUS_SUCCESS": (0, 114), "BRCMF_E_STATUS_NO_NETWORKS": (3, 117),
    "BRCMF_E_STATUS_PARTIAL": (8, 122),
})
_pin(LINUX, BRCMF + "fwil_types.h", {
    "BRCMF_SCANTYPE_ACTIVE": (0, 62), "BRCMF_SCANTYPE_PASSIVE": (1, 63),
    "BRCMF_ESCAN_REQ_VERSION": (1, 73), "BRCMF_MCSSET_LEN": (16, 163),
})
_pin(LINUX, BRCMU + "brcmu_wifi.h", {"WL_CHANSPEC_CHAN_MASK": (0x00FF, 42)})

# -- the firmware mailbox and the expander ------------------------------
_pin("Linux", "include/soc/bcm2835/raspberrypi-firmware.h", {
    "RPI_FIRMWARE_GET_POWER_STATE": (0x00020001, 50),
    "RPI_FIRMWARE_SET_POWER_STATE": (0x00028001, 52),
    "RPI_FIRMWARE_GET_CLOCK_STATE": (0x00030001, 53),
    "RPI_FIRMWARE_GET_CLOCK_RATE": (0x00030002, 54),
    "RPI_FIRMWARE_GET_CLOCK_MEASURED": (0x00030047, 76),
    "RPI_FIRMWARE_SET_CLOCK_STATE": (0x00038001, 78),
    "RPI_FIRMWARE_GET_GPIO_STATE": (0x00030041, 84),
    "RPI_FIRMWARE_SET_GPIO_STATE": (0x00038041, 85),
    "RPI_FIRMWARE_GET_GPIO_CONFIG": (0x00030043, 87),
    "RPI_FIRMWARE_SET_GPIO_CONFIG": (0x00038043, 88),
})
_pin(RPI, "drivers/gpio/gpio-raspberrypi-exp.c", {
    "RPI_EXP_GPIO_BASE": (128, 20),
})
_pin(UBOOT, "arch/arm/mach-bcm283x/include/mach/mbox.h", {
    "BCM2835_MBOX_CLOCK_ID_EMMC": (1, 229),
    "BCM2835_MBOX_CLOCK_ID_EMMC2": (12, 239),
})
# -- the NEGATIVE claim: sdhost cannot do SDIO ---------------------------
# The driver's header comment says the sdhost controller "supports the
# sdcard only".  sdio.pi4's whole argument for using $FE300000 instead of
# $FE202000 rests on that sentence.
_pin(UBOOT, "drivers/mmc/bcm2835_sdhost.c", {
    "SDHOST_IS_SDCARD_ONLY": (1, "9-10"),
})

ETH_ALEN = 6        # Linux include/uapi/linux/if_ether.h
IFNAMSIZ = 16       # Linux include/uapi/linux/if.h


# =====================================================================
#  A C STRUCT LAYOUT CALCULATOR, AND WHY THIS GATE HAS ONE
#
#  struct brcmf_bss_info_le is NOT __packed. Its wire format therefore
#  contains compiler padding, and three of the fields cyw43.pi4 reads -
#  chanspec, RSSI and ctl_ch - sit where they sit ONLY because of that
#  padding. cyw43.pi4 carries their offsets as constants.
#
#  A model that took those constants from the library could not catch a
#  wrong one: it would write the SSID where the library expected to find
#  it and both would be wrong together. So this computes the layout from
#  the STRUCT'S MEMBER LIST, pinned below in declaration order, with
#  ordinary C alignment rules, and the model lays out its synthetic scan
#  results at the offsets that fall out. If the library's constants and
#  this calculation disagree, the SSIDs the library prints are not the
#  SSIDs the model wrote, and the assertion on the network list goes red.
# =====================================================================

_C_TYPES = {
    "u8": (1, 1), "s8": (1, 1), "char": (1, 1),
    "__le16": (2, 2), "__be16": (2, 2),
    "__le32": (4, 4), "__be32": (4, 4),
}

# Linux v6.12 brcmfmac/fweh.h:211-217, __packed.
BRCM_ETHHDR = (
    ("__be16", "subtype", 1), ("__be16", "length", 1), ("u8", "version", 1),
    ("u8", "oui", 3), ("__be16", "usr_subtype", 1),
)
# Linux v6.12 brcmfmac/fweh.h:219-231, __packed.
BRCMF_EVENT_MSG_BE = (
    ("__be16", "version", 1), ("__be16", "flags", 1),
    ("__be32", "event_type", 1), ("__be32", "status", 1),
    ("__be32", "reason", 1), ("__be32", "auth_type", 1),
    ("__be32", "datalen", 1), ("u8", "addr", ETH_ALEN),
    ("char", "ifname", IFNAMSIZ), ("u8", "ifidx", 1), ("u8", "bsscfgidx", 1),
)
# Linux v6.12 brcmfmac/fwil_types.h:314-348, NOT packed.  The anonymous
# `rateset` struct at :324-327 is flattened: its members are contiguous
# and its own alignment (4) is that of its first member.
BRCMF_BSS_INFO_LE = (
    ("__le32", "version", 1), ("__le32", "length", 1),
    ("u8", "BSSID", ETH_ALEN), ("__le16", "beacon_period", 1),
    ("__le16", "capability", 1), ("u8", "SSID_len", 1), ("u8", "SSID", 32),
    ("__le32", "count", 1), ("u8", "rates", 16),
    ("__le16", "chanspec", 1), ("__le16", "atim_window", 1),
    ("u8", "dtim_period", 1), ("__le16", "RSSI", 1), ("s8", "phy_noise", 1),
    ("u8", "n_cap", 1), ("__le32", "nbss_cap", 1), ("u8", "ctl_ch", 1),
    ("__le32", "reserved32", 1), ("u8", "flags", 1), ("u8", "reserved", 3),
    ("u8", "basic_mcs", 16),           # BRCMF_MCSSET_LEN, fwil_types.h:163
    ("__le16", "ie_offset", 1), ("__le32", "ie_length", 1),
    ("__le16", "SNR", 1),
)


def c_struct_offsets(members, packed: bool = False) -> dict:
    off = 0
    align = 1
    out = {}
    for ctype, cname, n in members:
        if ctype not in _C_TYPES:
            raise SystemExit(
                "The struct member type '%s' is not one this layout "
                "calculator knows, and it refuses to guess at it." % ctype)
        sz, al = _C_TYPES[ctype]
        if packed:
            al = 1
        off = (off + al - 1) // al * al
        out[cname] = off
        off += sz * n
        align = max(align, al)
    out["__size__"] = (off + align - 1) // align * align
    return out


def read_constants() -> dict:
    """The pinned vendor facts, plus the values derived from them."""
    k = {name: value for name, (value, _where) in PINNED.items()}

    if not k["MMCNR_IS_SDHCI"]:
        raise SystemExit("The mmcnr node is recorded as not sdhci-compatible; "
                         "the whole register map in sdio.pi4 rests on it.")
    if not k["SDHOST_IS_SDCARD_ONLY"]:
        raise SystemExit("The sdhost negative claim is no longer recorded; "
                         "re-read bcm2835_sdhost.c before trusting sdio.pi4.")
    if not (k["SOC_BUS_BASE"] <= k["MMCNR_BUS"]
            < k["SOC_BUS_BASE"] + k["SOC_WINDOW"]):
        raise SystemExit("The mmcnr node is outside the soc node's ranges "
                         "window, so it has no ARM address.")

    k["SDIO_FSEL"] = k[k["SDIO_FSEL_NAME"]]
    # device-tree pull value -> register pull value.  UP and DOWN swap
    # places between the two numberings.
    k["PULL_DT_TO_REG"] = {
        k["BCM2835_PUD_OFF"]: k["REG_PULL_NONE"],
        k["BCM2835_PUD_UP"]: k["REG_PULL_UP"],
        k["BCM2835_PUD_DOWN"]: k["REG_PULL_DOWN"],
    }
    k["SBSDIO_AVBITS"] = k["SBSDIO_ALP_AVAIL"] | k["SBSDIO_HT_AVAIL"]

    # WHICH FIRMWARE FILE THIS CHIP AND REVISION NEED, by the rule and not
    # by the first matching chip id.
    hits = [(mask, name) for (mask, name, _w) in FW_4345_ENTRIES
            if (mask >> MODEL_CHIP_REV) & 1]
    if len(hits) != 1:
        raise SystemExit(
            "Chip $4345 revision %d matches %d firmware entries under the "
            "rule at %s; the table is meant to be unambiguous."
            % (MODEL_CHIP_REV, len(hits), FW_SELECT_RULE))
    k["FW_REVMASK"], k["FW_BASENAME"] = hits[0]

    # SDPCM_HDRLEN is defined as the SUM of the other two (sdio.c:1331),
    # so it is composed here from the two terms it is composed from there.
    k["SDPCM_HDRLEN"] = k["SDPCM_HWHDR_LEN"] + k["SDPCM_SWHDR_LEN"]

    # The event packet's fixed prefix, DERIVED rather than taken as 72:
    # ethhdr is 14 by definition and the other two are measured.
    k["BRCM_ETHHDR_LEN"] = c_struct_offsets(BRCM_ETHHDR, packed=True)["__size__"]
    k["EVENT_MSG_OFF"] = c_struct_offsets(BRCMF_EVENT_MSG_BE, packed=True)
    k["EVENT_MSG_BE_LEN"] = k["EVENT_MSG_OFF"]["__size__"]
    k["EVENT_PREFIX"] = 14 + k["BRCM_ETHHDR_LEN"] + k["EVENT_MSG_BE_LEN"]

    # And the bss_info's field offsets, computed from the member list.
    k["BSS_OFF"] = c_struct_offsets(BRCMF_BSS_INFO_LE)
    return k


# =====================================================================
#  THE NVRAM, AND WHY THE SCAN GATE MAKES ITS OWN
#
#  The board's NVRAM text is calibration and identity data for one board
#  and is not distributed with this repository.  The scan payload needs
#  SOME NVRAM in DRAM, and the gate needs to know what cyw43.pi4 must
#  turn it into - so the default is a SYNTHETIC text, deliberately
#  awkward, and the expected cooked image is computed HERE from
#  brcmfmac's own parser rules rather than taken from the library.
#
#  The synthetic text is not calibration data for any radio.  It
#  exercises what the parser has to get right: whole-line comments, CRLF
#  line ends, blank and whitespace-only lines, leading whitespace before
#  a key, RAW1 (treated as a comment), a key containing a space (skipped),
#  a comment that follows a value on the same line, an unprintable byte
#  before a key (stepped over), and a final entry with no newline.
#
#  AND ITS ENTRIES END EXACTLY ON A WORD BOUNDARY, which is the case the
#  "+ 1" in roundup(len + 1, 4) exists for: without it a list whose length
#  is already a multiple of four gets no terminating NUL.  Any other
#  length pads identically with or without the "+ 1", so a text that
#  missed the boundary would let that mistake through - it did, once,
#  while this gate was being ported.  scan_gate refuses a synthetic text
#  that loses the property.
# =====================================================================

SYNTHETIC_NVRAM = (
    b"# Synthetic NVRAM text for tools/a64/a64_sdio_check.py.\n"
    b"# NOT calibration data for any board or radio.\r\n"
    b"\n"
    b"manfid=0x2d0\n"
    b"prodid=0x06e4\r\n"
    b"vendid=0x14e4\n"
    b"   devid=0x43ab\n"
    b"boardtype=0x06e4\n"
    b"boardrev=0x1304\n"
    b"boardnum=222\n"
    b" \t \n"
    b"RAW1=80 32 fe 21 02 0c 00 22\n"
    b"bad key=a key with a space in it is not a key\n"
    b"xtalfreq=37400\n"
    b"aa2g=1# a comment after a value ends the value\n"
    b"\x01ofdm2gpo=0x00000000\n"
    b"macaddr=02:00:00:00:00:01\n"
    b"ccode=ALL\n"
    b"last=an entry with no newline"
)

# brcmf_fw_add_defaults(), firmware.c:371-378, appends this when the text
# supplies no boardrev.  cyw43.pi4 refuses such a text instead; the
# synthetic text supplies boardrev, and a --nvram file without one is
# expected to disagree here and go red.
BRCMF_FW_DEFAULT_BOARDREV = b"boardrev=0xff"    # firmware.c:23


def cook_nvram_model(data: bytes) -> bytes:
    """The NVRAM image brcmfmac would upload for `data`.

    Linux v6.12 brcmfmac/firmware.c: is_nvram_char() :72-80,
    is_whitespace() :82-85, the IDLE/KEY/VALUE/COMMENT states :87-189,
    brcmf_fw_add_defaults() :371-378, and brcmf_fw_nvram_strip() :395-448
    for the padding - roundup(len + 1, 4) at :435 - and the length token
    at :441-446.  The parser runs over a NUL-terminated buffer
    (strchr(sol, '\\0') at :179), so the end of the input terminates an
    open value.  The multi-device devpath/pcie stripping at :232-370 and
    the platform MAC override are not modelled; a text that needs either
    is refused.
    """
    def is_nvram_char(c: int) -> bool:
        return c != 0x23 and 0x20 <= c < 0x7F

    buf = data + b"\0"
    out = bytearray()
    state, pos, entry = "IDLE", 0, 0
    boardrev = False
    while pos < len(buf) and state != "END":
        c = buf[pos]
        if state == "IDLE":
            if c == 0x0A or c == 0x23:
                state = "COMMENT"
            elif c in (0x20, 0x0D, 0x0A, 0x09) or c == 0:
                pos += 1
            elif is_nvram_char(c):
                entry, state = pos, "KEY"
            else:
                pos += 1
        elif state == "KEY":
            if c == 0x3D:
                key = bytes(buf[entry:pos])
                state = "COMMENT" if key.startswith(b"RAW1") else "VALUE"
                if key.startswith(b"devpath") or key.startswith(b"pcie/"):
                    raise SystemExit(
                        "The NVRAM text carries a multi-device %r entry, which "
                        "this gate's parser model does not implement." % key)
                if key.startswith(b"boardrev"):
                    boardrev = True
                pos += 1
            elif not is_nvram_char(c) or c == 0x20:
                state = "COMMENT"
            else:
                pos += 1
        elif state == "VALUE":
            if not is_nvram_char(c):
                out += buf[entry:pos] + b"\0"
                state = "IDLE"
            else:
                pos += 1
        else:   # COMMENT
            eoc = buf.find(b"\n", pos)
            if eoc < 0:
                state = "END"
            else:
                pos, state = eoc + 1, "IDLE"
    if not boardrev:
        out += BRCMF_FW_DEFAULT_BOARDREV + b"\0"
    padded = (len(out) + 1 + 3) & ~3
    out += bytes(padded - len(out))
    words = padded // 4
    token = ((~words & 0xFFFF) << 16) | (words & 0xFFFF)
    return bytes(out) + token.to_bytes(4, "little")


# =====================================================================
#  THE MODELLED CHIP
# =====================================================================

class Cyw43Card:
    """A CYW43455, as far as SDIO can see it.

    Everything below is built FROM the parsed constants, so a change in
    the vendor source moves the model and the library independently.
    """

    def __init__(self, k: dict) -> None:
        self.k = k
        self.selected = False
        self.rca = 0
        self.ioe = 0                     # CCCR IOEx
        self.ior = 0                     # CCCR IORx
        self.cccr_if = 0x00              # bus interface control
        self.opcond_polls = 0
        self.window = 0
        self.window_writes: list[tuple[int, int]] = []
        self.f1misc: dict[int, int] = {}
        self.fbr: dict[int, int] = {}
        self.backplane: dict[int, int] = {}
        self.bp_reads: list[int] = []
        self.access_flag_seen = 0
        self.access_flag_missing = 0
        self.alp_forced = False
        self.ht_forced = False
        self.pullup_cleared = False

        # CHIPCLKCSR starts with nothing available, which is what an
        # unclocked part looks like.
        self.f1misc[k["SBSDIO_FUNC1_CHIPCLKCSR"]] = 0x00

        # ---- the SDPCM transport ------------------------------------
        self.f2_txbuf = bytearray()     # the frame being assembled by us
        self.f2_queue = []              # frames waiting to be read
        self.f2_pos = 0                 # how far into the head frame
        self.f2_seq_expect = 0          # the sequence the next frame must carry
        self.f2_credit = 4              # what the model advertises
        self.frames_in = 0              # control frames we accepted
        self.ioctls = []                # (cmd, set, id, payload)
        self.escan_started = 0
        # PARTIAL results actually put on the wire - the distinct
        # networks plus the repeats. Counted here rather than assumed
        # from the length of the two lists, so that the number the
        # assertions compare against is one the model MEASURED.
        self.escan_partials = 0
        self.event_mask = None
        self.wlc_up = 0
        self.f2_addr_bad = 0

        # ---- the CLM downloader -------------------------------------
        # THE MODEL REASSEMBLES THE BLOB rather than counting chunks,
        # because a chunk count proves nothing about the flags. It keeps
        # the bytes, checks that DL_BEGIN and DL_END land on the right
        # chunks, and REFUSES THE ESCAN until a complete blob has
        # arrived - so a driver that forgets the CLM fails here with
        # BCME_NOTUP, which is exactly how it failed on silicon on
        # 2026-08-27, instead of passing.
        self.clm = bytearray()
        self.clm_chunks = 0
        self.clm_begun = False
        self.clm_done = False           # DL_END has been seen
        self.clm_status_reads = 0
        self.gets: list[bytes] = []     # every iovar name that was GET

        self._build_backplane()

    # -- the chip's own registers -------------------------------------
    def _build_backplane(self) -> None:
        k = self.k
        base = k["SI_ENUM_BASE_DEFAULT"]
        chipid = (MODEL_CHIP_ID & k["CID_ID_MASK"])
        chipid |= (MODEL_CHIP_REV << k["CID_REV_SHIFT"]) & k["CID_REV_MASK"]
        chipid |= (MODEL_CHIP_PKG << k["CID_PKG_SHIFT"]) & k["CID_PKG_MASK"]
        chipid |= (MODEL_CHIP_CCOUNT << k["CID_CC_SHIFT"]) & k["CID_CC_MASK"]
        chipid |= (k["SOCI_AI"] << k["CID_TYPE_SHIFT"]) & k["CID_TYPE_MASK"]
        self.chipid = chipid
        self.backplane[base + k["CC_CHIPID"]] = chipid
        self.backplane[base + k["CC_EROMPTR"]] = MODEL_EROM_ADDR
        self.cores = self._build_erom()

        # ---- the ARM CR4's memory-bank registers ----------------------
        # brcmf_chip_tcm_ramsize() (chip.c lines 680-707) walks these to
        # work out how much RAM the part has, and there is no table to
        # look it up in.  ARMCR4_CAP carries the bank counts split into
        # A-banks and B-banks; each bank is then SELECTED by writing its
        # index to ARMCR4_BANKIDX and its size read out of BANKINFO.
        #
        # EVERY BANK IS THE SAME SIZE HERE, so BANKINFO can be one static
        # value - but the index writes are RECORDED, because a driver
        # that never wrote BANKIDX would get the right total out of this
        # model and the wrong total out of a real chip with unequal
        # banks.  The assertion at the bottom of this file checks that
        # every index from 0 to totb-1 was selected, in order.
        #
        # (nab 3) + (nbb 3) = 6 banks; ((15 & BSZ_MASK) + 1) * 8192 =
        # 131,072 bytes each; 786,432 in total, which is what a CYW43455
        # is generally reported as having.
        self.bankidx_writes = []
        self.backplane[MODEL_CR4_BASE + ARMCR4_CAP] = (
            MODEL_CR4_NAB | (MODEL_CR4_NBB << 4))
        self.backplane[MODEL_CR4_BASE + ARMCR4_BANKINFO] = MODEL_CR4_BANKINFO

    def _build_erom(self) -> list[tuple[int, int, int, int]]:
        """Lay an EROM out at MODEL_EROM_ADDR and return what it encodes.

        THE FOURTH CORE IS DELIBERATELY AWKWARD.  Ahead of its real
        register descriptor it carries a 16K region whose descriptor has
        BOTH the 64-bit address flag and a size-descriptor size type -
        the two places brcmf_chip_dmp_get_regaddr() has to consume an
        EXTRA word (chip.c lines 875-885), and a size class that is
        neither 4K nor 8K, which chip.c lines 886-889 reject.

        WHAT IT PROVES: that a walker does not take a 16K region as a
        core's register base (assertion 10 would then report the awkward
        region's address for core 3), and that the extra words do not
        push it off the end of the table.

        WHAT IT DOES NOT PROVE, MEASURED RATHER THAN ASSUMED: removing
        the ADDRSIZE_GT32 skip from cyw43.pi4 and re-running this gate
        was tried on 2026-08-25 and the gate stayed GREEN.  The reason is
        worth writing down rather than papering over: the words that get
        skipped are an upper address half and a size, and in any
        realistic table both are ZERO in their low nibble - which a
        walker classifies as DMP_DESC_EMPTY and steps over harmlessly.
        It resynchronises on the next real descriptor and produces the
        right answer by accident.

        Making it bite would take an upper-address word whose low nibble
        was 5 or 1, i.e. a region above 4 GiB with a descriptor-shaped
        address - which is not something a CYW43 backplane has, so
        putting one here would be inventing hardware to fail a test.
        THE SKIP IS STILL CORRECT AND STILL REQUIRED; this gate simply
        cannot be the thing that proves it, and saying so is better than
        leaving a reader to assume it does.
        """
        k = self.k
        words: list[int] = []
        cores = [
            # (id, rev, base, wrap, awkward)
            (0x800, 0x31, 0x18000000, 0x18100000, False),
            (0x829, 0x0B, 0x18001000, 0x18101000, False),
            (0x812, 0x2C, 0x18002000, 0x18102000, False),
            (0x83E, 0x07, 0x18003000, 0x18103000, True),
        ]
        for (cid, rev, cbase, cwrap, awkward) in cores:
            # component descriptor 1: designer, part number, class, type
            w = (0x4BF << 20)
            w |= (cid << k["DMP_COMP_PARTNUM_S"]) & k["DMP_COMP_PARTNUM"]
            w |= k["DMP_DESC_COMPONENT"]
            words.append(w)
            # component descriptor 2: revision and the wrapper counts
            w = (rev << k["DMP_COMP_REVISION_S"]) & k["DMP_COMP_REVISION"]
            w |= (1 << k["DMP_COMP_NUM_SWRAP_S"]) & k["DMP_COMP_NUM_SWRAP"]
            w |= (1 << k["DMP_COMP_NUM_MWRAP_S"]) & k["DMP_COMP_NUM_MWRAP"]
            w |= k["DMP_DESC_COMPONENT"]
            words.append(w)
            if awkward:
                # A region that must be SKIPPED: 64-bit address, and a
                # size that lives in its own descriptor.  Three words to
                # consume, and its size type is neither 4K nor 8K, so it
                # is not a register base and must not be taken as one.
                w = AWKWARD_REGION & k["DMP_SLAVE_ADDR_BASE"]
                w |= (k["DMP_SLAVE_TYPE_SLAVE"] << k["DMP_SLAVE_TYPE_S"]) \
                    & k["DMP_SLAVE_TYPE"]
                w |= (k["DMP_SLAVE_SIZE_DESC"] << k["DMP_SLAVE_SIZE_TYPE_S"]) \
                    & k["DMP_SLAVE_SIZE_TYPE"]
                w |= k["DMP_DESC_ADDRESS"] | k["DMP_DESC_ADDRSIZE_GT32"]
                words.append(w)
                words.append(0x00000000)      # the upper 32 address bits
                words.append(0x00004000)      # the size descriptor, 16K
            # the slave address descriptor - the real register base
            w = cbase & k["DMP_SLAVE_ADDR_BASE"]
            w |= (k["DMP_SLAVE_TYPE_SLAVE"] << k["DMP_SLAVE_TYPE_S"]) \
                & k["DMP_SLAVE_TYPE"]
            w |= (k["DMP_SLAVE_SIZE_4K"] << k["DMP_SLAVE_SIZE_TYPE_S"]) \
                & k["DMP_SLAVE_SIZE_TYPE"]
            w |= k["DMP_DESC_ADDRESS"]
            words.append(w)
            # the wrapper address descriptor
            w = cwrap & k["DMP_SLAVE_ADDR_BASE"]
            w |= (k["DMP_SLAVE_TYPE_SWRAP"] << k["DMP_SLAVE_TYPE_S"]) \
                & k["DMP_SLAVE_TYPE"]
            w |= (k["DMP_SLAVE_SIZE_4K"] << k["DMP_SLAVE_SIZE_TYPE_S"]) \
                & k["DMP_SLAVE_SIZE_TYPE"]
            w |= k["DMP_DESC_ADDRESS"]
            words.append(w)
        words.append(k["DMP_DESC_EOT"])

        for i, w in enumerate(words):
            self.backplane[MODEL_EROM_ADDR + i * 4] = w
        return [(c[0], c[1], c[2], c[3]) for c in cores]

    # -- CMD52 --------------------------------------------------------
    def cmd52(self, write: bool, fn: int, addr: int, data: int) -> int:
        k = self.k
        if fn == 0:
            return self._cccr(write, addr, data)
        if fn == 1:
            return self._func1(write, addr, data)
        if fn == 2:
            return 0
        raise SystemExit(f"the image talked to SDIO function {fn}, which "
                         f"this card does not have")

    def _cccr(self, write: bool, addr: int, data: int) -> int:
        k = self.k
        if addr == k["SDIO_CCCR_ABORT"]:
            return 0
        if addr == k["SDIO_CCCR_CCCR"]:
            return 0x43            # CCCR 3.00 / SDIO 3.00
        if addr == k["SDIO_CCCR_CAPS"]:
            return 0x17
        if addr == k["SDIO_CCCR_IOEx"]:
            if write:
                self.ioe = data
                # The card brings a function up "immediately" here; the
                # library still has to poll IORx for it, and the poll is
                # what is being gated.
                self.ior = data
                return data
            return self.ioe
        if addr == k["SDIO_CCCR_IORx"]:
            return self.ior
        if addr == k["SDIO_CCCR_IF"]:
            if write:
                self.cccr_if = data
                return data
            return self.cccr_if
        # The FBR block-size registers.
        step = k["SDIO_FBR_STEP"]
        if addr >= step:
            fnum = addr // step
            off = addr % step
            if off in (k["SDIO_FBR_BLKSIZE"], k["SDIO_FBR_BLKSIZE"] + 1):
                if write:
                    self.fbr[addr] = data
                    return data
                return self.fbr.get(addr, 0)
        return 0

    def _func1(self, write: bool, addr: int, data: int) -> int:
        k = self.k
        lo = k["SBSDIO_FUNC1_SBADDRLOW"]
        if lo <= addr <= k["SBSDIO_FUNC1_SBADDRHIGH"]:
            if write:
                shift = 8 * (addr - lo) + 8
                mask = 0xFF << shift
                self.window = (self.window & ~mask) | ((data & 0xFF) << shift)
                self.window_writes.append((addr, data))
                return data
            return (self.window >> (8 * (addr - lo) + 8)) & 0xFF

        if addr == k["SBSDIO_FUNC1_CHIPCLKCSR"]:
            cur = self.f1misc.get(addr, 0)
            if write:
                # THE MODEL IS THE HARDWARE, NOT THE DRIVER: the two
                # AVAILABLE bits are the chip's to set and a write cannot
                # touch them.  A library that expected its own value back
                # verbatim would fail here, which is the point.
                cur = (data & ~k["SBSDIO_AVBITS"]) & 0xFF
                if data & k["SBSDIO_ALP_AVAIL_REQ"]:
                    cur |= k["SBSDIO_ALP_AVAIL"]
                if data & k["SBSDIO_FORCE_ALP"]:
                    cur |= k["SBSDIO_ALP_AVAIL"]
                    self.alp_forced = True
                # HT IMPLIES ALP AND THE MODEL HAD FORGOTTEN TO SAY SO.
                # sdio.h line 195 defines SBSDIO_HTAV(regval) as
                # ((regval & SBSDIO_AVBITS) == SBSDIO_AVBITS) - BOTH
                # bits, not just HT - so a chip that offered HT without
                # ALP would be a chip no driver accepts. Until
                # 2026-08-27 this model answered an HT request with
                # neither bit, so Cyw43HtClock timed out against a model
                # that was simply not implementing the register.
                if data & (k["SBSDIO_HT_AVAIL_REQ"] | k["SBSDIO_FORCE_HT"]):
                    cur |= k["SBSDIO_ALP_AVAIL"] | k["SBSDIO_HT_AVAIL"]
                    if data & k["SBSDIO_FORCE_HT"]:
                        self.ht_forced = True
                self.f1misc[addr] = cur
                return cur
            return cur

        if addr == k["SBSDIO_FUNC1_SDIOPULLUP"]:
            if write:
                self.f1misc[addr] = data
                if data == 0:
                    self.pullup_cleared = True
                return data
            return self.f1misc.get(addr, 0)

        if write:
            self.f1misc[addr] = data
            return data
        return self.f1misc.get(addr, 0)

    # =================================================================
    #  FUNCTION 2 - THE FRAME FIFO
    #
    #  Both directions go to the CHIPCOMMON core's base seen through the
    #  backplane window, with the 2/4-byte access flag, and BOTH HALVES
    #  OF THAT ARE CHECKED HERE. brcmf_sdiod_recv_pkt and
    #  brcmf_sdiod_send_buf (bcmsdh.c) each do
    #      set_backplane_window(cc_core->base);
    #      addr &= SBSDIO_SB_OFT_ADDR_MASK;
    #      addr |= SBSDIO_SB_ACCESS_2_4B_FLAG;
    #  which is not guessable, so a driver that got it wrong would be
    #  reading some other part of the chip and this model would happily
    #  hand it frames if it did not look.
    #
    #  THE ADDRESS IS NOT A POSITION IN THE FRAME, AND THAT IS THE
    #  SUBTLE PART. brcmf_sdiod_recv_pkt sets the address to
    #  cc_core->base for EVERY read, so two consecutive reads of the
    #  same frame - the 64-byte header read and then the remainder -
    #  both start from the same address. F2 is a FIFO: it advances
    #  itself as bytes are taken out. Only WITHIN one logical transfer
    #  does the address increment, because the MMC layer's
    #  sdio_io_rw_ext_helper walks it across chunks.
    #
    #  So the model tracks its own read position and uses the address
    #  only to check the two things that ARE checkable: the 2/4-byte
    #  flag, and that the backplane window is at the ChipCommon base.
    #  A model that treated the address as a position would have
    #  demanded the library do something the vendor driver does not.
    # =================================================================
    def _f2_check(self, addr: int, what: str) -> None:
        k = self.k
        if not (addr & k["SBSDIO_SB_ACCESS_2_4B_FLAG"]):
            raise SystemExit(
                f"a function 2 {what} at ${addr:05X} without the 2/4-byte "
                f"access flag. bcmsdh.c ORs SBSDIO_SB_ACCESS_2_4B_FLAG into "
                f"every F2 address")
        if self.window != k["SI_ENUM_BASE_DEFAULT"]:
            raise SystemExit(
                f"a function 2 {what} with the backplane window at "
                f"${self.window:08X}, not the ChipCommon base "
                f"${k['SI_ENUM_BASE_DEFAULT']:08X}. brcmf_sdiod_recv_pkt "
                f"sets the window to cc_core->base before every frame")

    def f2_write(self, addr: int, payload: bytes) -> None:
        self._f2_check(addr, "write")
        self.f2_txbuf += payload
        if len(self.f2_txbuf) < 4:
            return
        size = int.from_bytes(self.f2_txbuf[0:2], "little")
        padded = (size + 3) & ~3
        if size and len(self.f2_txbuf) >= padded:
            self._sdpcm_rx(bytes(self.f2_txbuf[:size]))
            self.f2_txbuf = bytearray()

    def f2_read(self, addr: int, nbytes: int) -> bytes:
        self._f2_check(addr, "read")
        if not self.f2_queue:
            # AN EMPTY FIFO ANSWERS WITH ZEROS. sdio.c line 1383, "All
            # zero means no more to read" - it is the documented poll,
            # not an error, and a model that raised here would fail a
            # correct driver on its very first read.
            return bytes(nbytes)
        frame = self.f2_queue[0]
        out = frame[self.f2_pos:self.f2_pos + nbytes]
        self.f2_pos += nbytes
        if self.f2_pos >= len(frame):
            # THE READ CONSUMED THE REST OF THE FRAME. A read that runs
            # past the end does not spill into the next frame: the
            # firmware pads to the transfer size and the FIFO aligns to
            # the next frame's header. That is what lets brcmfmac read
            # a fixed 64 bytes before it knows the length.
            self.f2_queue.pop(0)
            self.f2_pos = 0
        return out + bytes(nbytes - len(out))


    # =================================================================
    #  SDPCM, THE RECEIVING END, AND IT REFUSES.
    #
    #  This is the half of the gate that can DISAGREE with cyw43.pi4.
    #  Every field below is checked against a constant parsed out of a
    #  vendor header, not against anything the library says, so a
    #  library that builds the header slightly wrong is caught here
    #  instead of on the bench - which is exactly what did NOT happen
    #  for the byte-mode ceiling on 2026-08-26.
    # =================================================================
    def _sdpcm_rx(self, frame: bytes) -> None:
        k = self.k
        hdr = k["SDPCM_HDRLEN"]

        size = int.from_bytes(frame[0:2], "little")
        comp = int.from_bytes(frame[2:4], "little")
        if (size ^ comp) != 0xFFFF:
            raise SystemExit(
                f"an SDPCM frame whose length ${size:04X} and complement "
                f"${comp:04X} do not sum to $FFFF. sdio.c line 1391 is "
                f"`if ((u16)(~(len ^ checksum)))` and the firmware drops "
                f"the frame without saying so")
        if size != len(frame):
            raise SystemExit(
                f"an SDPCM frame claiming {size} bytes in a transfer that "
                f"delivered {len(frame)}")
        if size < hdr:
            raise SystemExit(f"an SDPCM frame of {size} bytes, shorter than "
                             f"the {hdr}-byte header itself")

        seq = frame[4]
        chan = (frame[5] & (k["SDPCM_CHANNEL_MASK"] >> k["SDPCM_CHANNEL_SHIFT"]))
        doff = frame[7]

        # THE SEQUENCE NUMBER MUST ADVANCE BY EXACTLY ONE. The firmware's
        # flow control counts frames; a skipped sequence reads as a lost
        # frame and a repeated one as a retransmission. The library is
        # only allowed to advance it on a send that actually happened,
        # which is a rule that is easy to get wrong on an error path.
        if seq != self.f2_seq_expect:
            raise SystemExit(
                f"an SDPCM frame with sequence {seq}; the previous frame "
                f"makes {self.f2_seq_expect} the only correct value. A "
                f"skipped sequence reads to the firmware as a lost frame")
        self.f2_seq_expect = (self.f2_seq_expect + 1) & 0xFF

        # THE CREDIT WINDOW SLIDES, AND IT DID NOT UNTIL 2026-08-27.
        # This model advertised a FIXED 4 in every reply's window byte,
        # which is not what a credit window is: the field is the highest
        # sequence number the host may still send, and real firmware
        # advances it as it consumes frames. A constant 4 is harmless
        # for the first four frames and then permanently equal to the
        # host's sequence, so the driver's stall path fires and stays
        # fired.
        #
        # IT WENT UNNOTICED BECAUSE THE PAYLOAD ONLY EVER SENT THREE
        # IOCTLS. The CLM added seven more and the fourth one stalled -
        # a gate defect that had been sitting there since the model was
        # written, and that presented as a driver failure. Worth the
        # paragraph: the reason it was caught at all is that
        # `credit stalls` is a counter with its own assertion rather
        # than something folded into a pass/fail.
        self.f2_credit = (self.f2_seq_expect + 4) & 0xFF

        if chan != k["SDPCM_CONTROL_CHANNEL"]:
            raise SystemExit(
                f"the host sent a frame on channel {chan}. Nothing in this "
                f"driver has anything to send on any channel but "
                f"{k['SDPCM_CONTROL_CHANNEL']} (control)")
        if doff != hdr:
            raise SystemExit(
                f"an SDPCM control frame with data_offset {doff}; the BCDC "
                f"header follows the SDPCM header immediately, so it must "
                f"be {hdr}")

        bcdc = k["BCDC_HEADER_LEN"]
        if size < doff + 16:
            raise SystemExit(
                f"a control frame of {size} bytes cannot hold a "
                f"{doff}-byte SDPCM header and a 16-byte BCDC header")

        cmd = int.from_bytes(frame[doff + 0:doff + 4], "little")
        plen = int.from_bytes(frame[doff + 4:doff + 8], "little")
        flags = int.from_bytes(frame[doff + 8:doff + 12], "little")
        rid = (flags >> k["BCDC_DCMD_ID_SHIFT"]) & 0xFFFF
        is_set = bool(flags & k["BCDC_DCMD_SET"])
        payload = frame[doff + 16:]

        if rid == 0:
            raise SystemExit(
                "a BCDC request with id 0. bcdc.c line 152 matches replies "
                "by id alone, and 0 is indistinguishable from an "
                "uninitialised header")
        if plen != len(payload):
            raise SystemExit(
                f"a BCDC header claiming {plen} payload bytes behind "
                f"{len(payload)} actual ones")

        self.frames_in += 1
        self.ioctls.append((cmd, is_set, rid, bytes(payload)))
        self._dispatch(cmd, is_set, rid, bytes(payload))

    # -----------------------------------------------------------------
    #  What the modelled firmware does with each command.
    # -----------------------------------------------------------------
    def _dispatch(self, cmd: int, is_set: bool, rid: int, payload: bytes):
        k = self.k
        if cmd == k["BRCMF_C_UP"]:
            if not is_set:
                raise SystemExit("WLC_UP was sent as a GET")
            if payload:
                raise SystemExit("WLC_UP carries no payload")
            self.wlc_up += 1
            self._reply(rid, b"", 0)
            return

        if cmd == k["BRCMF_C_SET_VAR"]:
            name, _, rest = payload.partition(b"\x00")
            if name == b"bsscfg:event_msgs":
                self._event_msgs(rid, rest)
                return
            if name == b"escan":
                self._escan(rid, rest)
                return
            if name == b"clmload":
                self._clmload(rid, rest)
                return
            raise SystemExit(
                f"the driver set an iovar this model does not serve: "
                f"{name!r}. Either it is new, or its name is misspelt - and "
                f"a misspelt iovar is not an error the firmware reports")

        if cmd == k["BRCMF_C_GET_VAR"]:
            name, _, rest = payload.partition(b"\x00")
            self.gets.append(name)
            self._get_var(rid, name, rest, len(payload))
            return

        raise SystemExit(
            f"the driver issued ioctl {cmd}, which this model does not "
            f"serve. fwil.h names it if it is real")

    # -----------------------------------------------------------------
    #  clmload - the regulatory blob, chunk by chunk.
    #
    #  MODELLED FROM THE VENDOR HEADER AND NOT FROM EITHER DRIVER:
    #  struct brcmf_dload_data_le is fwil_types.h:1106 and the flag bits
    #  are :187-194. The checks here are the ones a real downloader must
    #  make in order to assemble anything at all - the first chunk has
    #  to announce itself, a chunk after the end is nonsense, and the
    #  declared length has to match what actually arrived.
    #
    #  WHAT THIS DOES NOT MODEL, AND SAY SO OUT LOUD: the firmware's own
    #  parse of the assembled blob. Real clmload_status can be non-zero
    #  for a blob that arrived intact and is simply not a CLM, or is for
    #  another part; this model answers 0 to any assembly that satisfies
    #  the rules above. So a PASS here means the CHUNKING is right. It
    #  does not mean the bytes are a valid CLM - only the board can say
    #  that, and it says it through clmload_status.
    # -----------------------------------------------------------------
    def _clmload(self, rid: int, rest: bytes) -> None:
        if len(rest) < 12:
            raise SystemExit(
                f"a clmload chunk of {len(rest)} bytes cannot hold the "
                f"12-byte struct brcmf_dload_data_le (fwil_types.h:1106)")
        flag = int.from_bytes(rest[0:2], "little")
        dtype = int.from_bytes(rest[2:4], "little")
        dlen = int.from_bytes(rest[4:8], "little")
        crc = int.from_bytes(rest[8:12], "little")
        data = rest[12:]

        ver = (flag & 0xF000) >> 12
        if ver != 1:
            raise SystemExit(
                f"clmload flag declares downloader version {ver}, not "
                f"DLOAD_HANDLER_VER 1. The version lives in the TOP NIBBLE "
                f"(DLOAD_FLAG_VER_SHIFT is 12, fwil_types.h:189) - a driver "
                f"that writes a bare 1 there sets bit 0 and declares "
                f"version 0")
        if dtype != 2:
            raise SystemExit(
                f"clmload dload_type {dtype}, not DL_TYPE_CLM (2), "
                f"fwil_types.h:194")
        if crc != 0:
            raise SystemExit(
                f"clmload crc field is ${crc:08X}. brcmf_c_download writes "
                f"cpu_to_le32(0) unconditionally; a non-zero value here is "
                f"a field being used for something the firmware does not "
                f"expect")
        if dlen > 1400:
            raise SystemExit(
                f"a clmload chunk of {dlen} bytes exceeds MAX_CHUNK_LEN "
                f"(1400, fwil_types.h:185), which the header's own comment "
                f"attributes to a firmware payload limit")
        if len(data) < dlen:
            raise SystemExit(
                f"a clmload chunk declaring {dlen} bytes behind only "
                f"{len(data)} - the length field and the payload disagree")

        begin = bool(flag & 0x0002)
        end = bool(flag & 0x0004)

        if self.clm_done:
            raise SystemExit(
                "a clmload chunk arrived AFTER the one carrying DL_END. "
                "The blob was already closed, so this one is either a "
                "misplaced END flag or a loop that does not stop")
        if not self.clm_begun:
            if not begin:
                raise SystemExit(
                    "the first clmload chunk does not carry DL_BEGIN "
                    "(0x0002, fwil_types.h:191). The firmware has nothing "
                    "to append to and drops it")
            self.clm_begun = True
        elif begin:
            raise SystemExit(
                "DL_BEGIN on a chunk that is not the first. That restarts "
                "the blob, so everything sent before it is discarded and "
                "the CLM ends up being only its own last chunk")

        self.clm += data[:dlen]
        self.clm_chunks += 1
        if end:
            self.clm_done = True
        self._reply(rid, b"", 0)

    # -----------------------------------------------------------------
    #  The GETs. Each one is a question this file had to answer from the
    #  vendor sources, and the answer is written down beside it.
    # -----------------------------------------------------------------
    def _get_var(self, rid: int, name: bytes, rest: bytes,
                 asked: int) -> None:
        if name == b"clmload_status":
            self.clm_status_reads += 1
            # 0 means "the blob I assembled is usable". See the caveat
            # in _clmload: this model checks assembly, not content.
            if not self.clm_done:
                raise SystemExit(
                    "clmload_status was read before a chunk carrying "
                    "DL_END. There is no assembled blob to have a status")
            self._reply(rid, (0).to_bytes(4, "little"), 0)
            return

        if name == b"clmver":
            # Shape only. The real string is the CLM's own version
            # block and no capture of this board's exists in the
            # repository, so the model sends something of the right
            # SHAPE and the board's log is what records the real text.
            self._reply(rid, b"API: 12.2\nData: 9.10.39\n\x00", 0)
            return

        if name == b"country":
            # struct brcmf_fil_country_le, fwil_types.h:764-768:
            # char country_abbrev[4]; le32 rev; char ccode[4].
            #
            # THE MODEL ANSWERS "00" WITH REV 0 because that is what
            # cfg80211.c:8190 says the firmware holds at boot - "The
            # country code gets set to 00 by default at boot". It is
            # the value the real part is most likely to give, and if
            # the board disagrees the board's answer is the fact.
            body = bytearray(12)
            body[0:2] = b"00"
            body[8:10] = b"00"
            self._reply(rid, bytes(body), 0)
            return

        if name == b"scan_ver":
            # -BRCMF_FW_UNSUPPORTED, i.e. -23. feature.c:20 defines the
            # constant and feature.c:196 is the test: anything OTHER
            # than this enables SCAN_V2. This firmware family predates
            # the iovar, so the model refuses it - which is the answer
            # that keeps the driver's v1 escan correct. THE BOARD IS
            # THE AUTHORITY HERE AND THE GATE IS NOT: if silicon answers
            # differently, the silicon is right and this line is what
            # has to change.
            self._reply(rid, b"", -23)
            return

        if name == b"sup_wpa":
            # -23 AGAIN, AND THIS ONE IS NOT A PREDICTION - IT IS A
            # TRANSCRIPTION. The board was asked on 2026-08-27 and
            # answered rc -3, status -23, value -1, so this line copies
            # silicon rather than guessing ahead of it.
            #
            # WHAT THE ANSWER MEANS. feature.c:341 wires this iovar to
            # BRCMF_FEAT_FWSUP through brcmf_feat_iovar_int_get, whose
            # rule (feature.c:184-201) is that anything OTHER than
            # -BRCMF_FW_UNSUPPORTED enables the feature. -23 therefore
            # says this firmware does not ADVERTISE an in-firmware
            # supplicant - which is consistent with how a Raspberry Pi
            # actually runs, since Linux does not offload the handshake
            # on this part but runs wpa_supplicant in userspace.
            #
            # IT IS SERVED ONLY SO THE SCAN GATE DOES NOT DIE ON AN
            # UNSERVED NAME. This model does NOT implement the
            # supplicant, the PMK ioctl, WLC_SET_SSID or any association
            # event, and NOTHING ABOUT ASSOCIATION CAN BE TESTED HERE.
            # See WHAT THIS GATE CANNOT DO at the head of the file.
            self._reply(rid, b"", -23)
            return

        raise SystemExit(
            f"the driver read an iovar this model does not serve: "
            f"{name!r} (asked for {asked} bytes back)")

    def _event_msgs(self, rid: int, rest: bytes) -> None:
        k = self.k
        if len(rest) < 4:
            raise SystemExit("bsscfg:event_msgs with no bsscfg index")
        idx = int.from_bytes(rest[0:4], "little")
        if idx != 0:
            raise SystemExit(f"bsscfg:event_msgs for bsscfg {idx}, not 0")
        mask = rest[4:]
        ev = k["BRCMF_E_ESCAN_RESULT"]
        if len(mask) * 8 <= ev:
            raise SystemExit(
                f"an event mask of {len(mask)} bytes cannot address event "
                f"{ev} - ESCAN_RESULT would never be delivered and the scan "
                f"would time out with no explanation")
        if not (mask[ev // 8] & (1 << (ev % 8))):
            raise SystemExit(
                f"the event mask does not enable ESCAN_RESULT (event {ev}, "
                f"mask byte {ev // 8} bit {ev % 8}). The scan would run and "
                f"report nothing")
        self.event_mask = bytes(mask)
        self._reply(rid, b"", 0)

    def _escan(self, rid: int, rest: bytes) -> None:
        """Validate the escan request, then answer it with results.

        THE FIRST THING CHECKED IS THE CLM AND IT IS NOT A VALIDATION
        ERROR. Without regulatory data the PHY has no legal channel
        list, so real firmware refuses the escan with BCME_NOTUP (-4)
        even though WLC_UP itself returned 0 - two different meanings of
        "up", and this driver spent 2026-08-27 believing the first one.
        So the model REFUSES rather than raising: a driver that skips
        the CLM must fail here exactly the way it failed on silicon,
        with a status word to read, not with a Python traceback that
        tells it something the part would never have said.
        """
        k = self.k
        if not self.clm_done:
            self._reply(rid, b"", -4)
            return
        if len(rest) != 76:
            raise SystemExit(
                f"an escan request of {len(rest)} parameter bytes. "
                f"sizeof(struct brcmf_escan_params_le) is 76 - 8 for "
                f"version/action/sync_id plus 68 for the scan params - and "
                f"the firmware reads a fixed-size struct")
        ver = int.from_bytes(rest[0:4], "little")
        action = int.from_bytes(rest[4:6], "little")
        sync = int.from_bytes(rest[6:8], "little")
        ssid_len = int.from_bytes(rest[8:12], "little")
        bssid = rest[44:50]
        bss_type = rest[50]
        scan_type = rest[51]
        timings = rest[52:68]

        if ver != k["BRCMF_ESCAN_REQ_VERSION"]:
            raise SystemExit(
                f"escan version {ver}, not BRCMF_ESCAN_REQ_VERSION "
                f"({k['BRCMF_ESCAN_REQ_VERSION']})")
        if action != 1:
            raise SystemExit(f"escan action {action}, not START (1)")
        if sync == 0:
            raise SystemExit(
                "escan sync_id 0. The firmware echoes it into every result "
                "and a driver that sends 0 cannot tell its own results from "
                "a previous scan's")
        if ssid_len != 0:
            raise SystemExit(
                f"escan ssid_len {ssid_len}; a broadcast scan sends 0 and "
                f"anything else asks for one named network only")
        if bssid != b"\xff" * 6:
            raise SystemExit(
                f"escan bssid {bssid.hex(':')}, not broadcast. A zero BSSID "
                f"asks for the network at 00:00:00:00:00:00")
        if bss_type != 2:
            raise SystemExit(f"escan bss_type {bss_type}, not ANY (2)")
        if scan_type not in (k["BRCMF_SCANTYPE_ACTIVE"],
                             k["BRCMF_SCANTYPE_PASSIVE"]):
            raise SystemExit(f"escan scan_type {scan_type} is neither active "
                             f"nor passive")
        if timings != b"\xff" * 16:
            raise SystemExit(
                "escan nprobes/active_time/passive_time/home_time are not "
                "all -1. Anything else asks for dwell times this driver has "
                "no way to have chosen")

        self.escan_started += 1
        self._reply(rid, b"", 0)

        # A repeat scheduled at or before its own original is not a
        # repeat - it is the first sighting, and the entry in MODEL_BSS
        # becomes the duplicate. The list would still produce five rows
        # and three folds, so the gate would stay green while testing
        # something other than what it says. Refuse instead.
        for before, idx, _r in MODEL_BSS_REPEATS:
            if before <= idx:
                raise SystemExit(
                    f"MODEL_BSS_REPEATS says a repeat of network {idx} is "
                    f"sent before original {before}, so it would arrive "
                    f"first and be the one that appends")

        # And now the results, plus a terminal SUCCESS.
        #
        # THE REPEATS ARE SPLICED INTO THE STREAM, NOT APPENDED TO IT.
        # A run of duplicates at the end would only exercise folding
        # into the most recently written row; interleaved, one of them
        # folds into a row three entries back, which is the case a
        # lookup that only checks the last record still gets wrong.
        def partial(idx: int, rssi: int) -> None:
            ssid, chan, _first, priv = MODEL_BSS[idx]
            self._escan_event(k["BRCMF_E_STATUS_PARTIAL"],
                              self._bss_record(ssid, chan, rssi, priv), sync)
            self.escan_partials += 1

        for i, (ssid, chan, rssi, priv) in enumerate(MODEL_BSS):
            for before, idx, rrssi in MODEL_BSS_REPEATS:
                if before == i:
                    partial(idx, rrssi)
            partial(i, rssi)
        for before, idx, rrssi in MODEL_BSS_REPEATS:
            if before == len(MODEL_BSS):
                partial(idx, rrssi)

        self._escan_event(k["BRCMF_E_STATUS_SUCCESS"], b"", sync)

    # -----------------------------------------------------------------
    #  Building the frames the firmware sends back.
    # -----------------------------------------------------------------
    def _sdpcm_wrap(self, chan: int, payload: bytes) -> bytes:
        """One SDPCM frame: the 12-byte header then payload."""
        k = self.k
        hdr = k["SDPCM_HDRLEN"]
        total = hdr + len(payload)
        f = bytearray(hdr)
        f[0:2] = (total & 0xFFFF).to_bytes(2, "little")
        f[2:4] = ((~total) & 0xFFFF).to_bytes(2, "little")
        f[4] = 0                      # our sequence; the driver ignores it
        f[5] = chan
        f[6] = 0
        f[7] = hdr
        f[8] = 0
        f[9] = self.f2_credit         # the credit the driver must pick up
        return bytes(f) + payload

    def _reply(self, rid: int, payload: bytes, status: int) -> None:
        """A BCDC control reply carrying the request's id."""
        k = self.k
        msg = bytearray(16)
        msg[0:4] = (0).to_bytes(4, "little")
        msg[4:8] = len(payload).to_bytes(4, "little")
        flags = (rid << k["BCDC_DCMD_ID_SHIFT"])
        if status:
            flags |= k["BCDC_DCMD_ERROR"]
        msg[8:12] = flags.to_bytes(4, "little")
        msg[12:16] = (status & 0xFFFFFFFF).to_bytes(4, "little")
        self.f2_queue.append(
            self._sdpcm_wrap(k["SDPCM_CONTROL_CHANNEL"], bytes(msg) + payload))

    def _bss_record(self, ssid: bytes, chan: int, rssi: int,
                    priv: int) -> bytes:
        """One brcmf_bss_info_le, laid out at the offsets the struct
        calculator derived - NOT at offsets copied from cyw43.pi4."""
        k = self.k
        o = k["BSS_OFF"]
        n = o["__size__"]
        b = bytearray(n)

        def put(field, val, width, signed=False):
            b[o[field]:o[field] + width] = val.to_bytes(width, "little",
                                                        signed=signed)

        put("version", 109, 4)
        put("length", n, 4)
        b[o["BSSID"]:o["BSSID"] + 6] = bytes([0x02, 0x11, 0x22, 0x33,
                                              0x44, chan & 0xFF])
        put("beacon_period", 100, 2)
        put("capability", 0x0010 if priv else 0x0001, 2)
        b[o["SSID_len"]] = len(ssid)
        b[o["SSID"]:o["SSID"] + len(ssid)] = ssid
        # chanspec's low byte is the channel - brcmu_wifi.h's
        # CHSPEC_CHANNEL - and the upper bits are band and bandwidth,
        # set here to something non-zero so that a driver reading the
        # whole halfword as a channel number is visible.
        put("chanspec", (0x1000 | chan) & 0xFFFF, 2)
        put("RSSI", rssi, 2, signed=True)
        b[o["ctl_ch"]] = chan & 0xFF
        return bytes(b)

    def _escan_event(self, status: int, bss: bytes, sync: int) -> None:
        """An ESCAN_RESULT on the event channel.

        THE BDC data_offset IS SET TO 1, NOT 0, DELIBERATELY. bcdc.c's
        hdrpull does `skb_pull(pktbuf, h->data_offset << 2)`, so a
        non-zero value shifts the Ethernet frame four bytes further on.
        A value of 1 has been observed on event frames from a sibling
        part. A driver that hard-codes the payload offset instead of
        honouring the field reads every field four bytes early, which
        produces a plausible-looking wrong SSID rather than an error.
        """
        k = self.k
        doff_words = 1

        ev = bytearray(k["EVENT_PREFIX"])
        # ethhdr: destination, source, ethertype. Not read by anything
        # here, but present because the offsets behind it depend on it.
        ev[12:14] = (0x886C).to_bytes(2, "big")
        # brcm_ethhdr, big-endian.
        eo = 14
        ev[eo + 0:eo + 2] = (0x0000).to_bytes(2, "big")     # subtype
        ev[eo + 2:eo + 4] = (0x0000).to_bytes(2, "big")     # length
        # brcmf_event_msg_be, BIG-ENDIAN, at the offsets the calculator
        # derived from the struct rather than at remembered ones.
        mo = 14 + k["BRCM_ETHHDR_LEN"]
        m = k["EVENT_MSG_OFF"]
        payload = b""
        if bss:
            esc = bytearray(12)
            esc[0:4] = (12 + len(bss)).to_bytes(4, "little")   # buflen
            esc[4:8] = (109).to_bytes(4, "little")             # version
            esc[8:10] = (sync & 0xFFFF).to_bytes(2, "little")  # sync_id
            esc[10:12] = (1).to_bytes(2, "little")             # bss_count
            payload = bytes(esc) + bss
        ev[mo + m["version"]:mo + m["version"] + 2] = (2).to_bytes(2, "big")
        ev[mo + m["event_type"]:mo + m["event_type"] + 4] = \
            k["BRCMF_E_ESCAN_RESULT"].to_bytes(4, "big")
        ev[mo + m["status"]:mo + m["status"] + 4] = status.to_bytes(4, "big")
        ev[mo + m["datalen"]:mo + m["datalen"] + 4] = \
            len(payload).to_bytes(4, "big")

        bdc = bytearray(k["BCDC_HEADER_LEN"] + doff_words * 4)
        bdc[0] = (k["BCDC_PROTO_VER"] << k["BCDC_FLAG_VER_SHIFT"]) & 0xFF
        bdc[3] = doff_words
        self.f2_queue.append(
            self._sdpcm_wrap(k["SDPCM_EVENT_CHANNEL"],
                             bytes(bdc) + bytes(ev) + payload))

    # -- CMD53 --------------------------------------------------------
    def cmd53_read(self, fn: int, addr: int, nbytes: int, incr: int) -> bytes:
        k = self.k
        if fn == 2:
            return self.f2_read(addr, nbytes)
        if fn != 1:
            raise SystemExit(f"a CMD53 read on function {fn}; this model only "
                             f"serves the backplane on function 1 and frames "
                             f"on function 2")
        if addr & k["SBSDIO_SB_ACCESS_2_4B_FLAG"]:
            self.access_flag_seen += 1
        else:
            self.access_flag_missing += 1
        off = addr & k["SBSDIO_SB_OFT_ADDR_MASK"]
        out = bytearray()
        a = self.window | off
        for i in range(0, nbytes, 4):
            word = self.backplane.get(a + (i if incr else 0), 0)
            self.bp_reads.append(a + (i if incr else 0))
            out += word.to_bytes(4, "little")
        return bytes(out)

    def cmd53_write(self, fn: int, addr: int, payload: bytes, incr: int) -> None:
        k = self.k
        if fn == 2:
            self.f2_write(addr, payload)
            return
        off = addr & k["SBSDIO_SB_OFT_ADDR_MASK"]
        a = self.window | off
        for i in range(0, len(payload), 4):
            target = a + (i if incr else 0)
            val = int.from_bytes(payload[i:i + 4], "little")
            if target == MODEL_CR4_BASE + ARMCR4_BANKIDX:
                self.bankidx_writes.append(val)
            self.backplane[target] = val


class Sdhci:
    """The Arasan controller at the mmcnr node's address."""

    def __init__(self, k: dict, card: Cyw43Card, base: int) -> None:
        self.k = k
        self.card = card
        self.base = base
        self.reg: dict[int, int] = {}
        self.intstat = 0
        self.resp = [0, 0, 0, 0]
        self.fifo = bytearray()
        self.fifo_out = bytearray()
        self.pending_write = 0
        self.pending_target = None
        self.commands: list[tuple[int, int, int]] = []   # (index, flags, arg)
        self.blksize = 0
        self.blkcount = 0
        self.powered = False
        self.clock_on = False
        self.trace: list[str] = []
        # Set when the card answers a data command with an R5 refusal.
        # The data phase then never runs, so DAT Inhibit stays asserted
        # until the data line is reset - see PRESENT_STATE below
        # and the refusal path in _cmd53.
        self.card_refused = False
        self.dat_inhibited = False

        # Capabilities: ENTIRELY ZERO, which is what the board reported
        # on 2026-08-26 - $FE300040 and $FE300044 both read $00000000
        # while $FE3000FC read $99020000 - and which the driver
        # Raspberry Pi binds to this node tolerates because it never
        # reads the register for anything (rpi-6.12.y bcm2835-mmc.c
        # mentions SDHCI_CAPABILITIES once, at lines 255-257, inside a
        # pr_debug dump).
        #
        # IT USED TO BE 0x01000000 HERE, and that bit was doing real
        # harm: it let the library's old "Capabilities all-zero means
        # wrong device" refusal pass a gate that the board then failed.
        # A model that is kinder than the silicon is a model that
        # certifies bugs.  A base clock of zero in bits 13:8 is kept
        # because it forces the library down the "ask the mailbox" path
        # this gate exists to check - and with the whole register zero
        # that is automatic.
        self.caps0 = 0x00000000 | (0 << k["SDHCI_CLOCK_BASE_SHIFT"])
        self.caps1 = 0x00000000
        # Host Controller Version, spec 3.00 (value 2), vendor 0x99.
        self.hostver = (0x99 << k["SDHCI_VENDOR_VER_SHIFT"]) | 2

    # -- register access ----------------------------------------------
    def read(self, off: int) -> int:
        k = self.k
        if off == k["SDHCI_INT_STATUS"]:
            return self.intstat
        if off == k["SDHCI_PRESENT_STATE"]:
            # Card inserted and stable, which is what a soldered-down
            # device reads as. CMD Inhibit is never set - this model
            # completes every command synchronously - but DAT Inhibit IS,
            # once a data command has been refused, because that is what
            # the board did and it is what makes a missing
            # sdio_ResetLine visible instead of invisible.
            st = 0x00030000
            if self.dat_inhibited:
                st |= k["SDHCI_DATA_INHIBIT"]
            return st
        if off == (k["SDHCI_CLOCK_CONTROL"] & ~3):
            # CLOCK_CONTROL / TIMEOUT / SOFTWARE_RESET share this word.
            # The reset bits are self-clearing and read back as zero;
            # Internal Clock Stable is always set.
            return self.reg.get(off, 0) | k["SDHCI_CLOCK_INT_STABLE"]
        if off == k["SDHCI_CAPABILITIES"]:
            return self.caps0
        if off == k["SDHCI_CAPABILITIES_1"]:
            return self.caps1
        if off == (k["SDHCI_HOST_VERSION"] & ~3):
            return self.hostver << 16
        if off == k["SDHCI_BUFFER"]:
            if len(self.fifo) < 4:
                raise SystemExit("the image read the Buffer Data Port with "
                                 "nothing in it")
            # NO ASSERTION THAT BUFFER READ READY IS STILL SET HERE, and
            # that is deliberate rather than an omission. The bit is a
            # LATCHED EVENT, cleared by writing it back, and both this
            # library and Linux clear it and THEN drain the block - the
            # data lives in the FIFO, not in the flag. An assertion here
            # would have failed a correct driver.
            w = int.from_bytes(self.fifo[:4], "little")
            del self.fifo[:4]
            # BUFFER READ READY IS RAISED ONCE PER BLOCK, not once per
            # transfer. A driver that clears it after block 1 and waits
            # for it again before block 2 - which is what a multi-block
            # PIO loop must do - only works if the controller re-raises
            # it, so the model re-raises it at every block boundary.
            if self.fifo and self.blksize and len(self.fifo) % self.blksize == 0:
                self.intstat |= k["SDHCI_INT_DATA_AVAIL"]
            if not self.fifo:
                self.intstat |= k["SDHCI_INT_DATA_END"]
            return w
        if off == k["SDHCI_RESPONSE"]:
            return self.resp[0]
        if off in (k["SDHCI_RESPONSE"] + 4, k["SDHCI_RESPONSE"] + 8,
                   k["SDHCI_RESPONSE"] + 12):
            return self.resp[(off - k["SDHCI_RESPONSE"]) // 4]
        return self.reg.get(off, 0)

    def write(self, off: int, val: int) -> None:
        k = self.k
        if off == k["SDHCI_INT_STATUS"]:
            self.intstat &= ~val & 0xFFFFFFFF
            return
        if off == k["SDHCI_BUFFER"]:
            if self.pending_target is None:
                raise SystemExit("the image wrote the Buffer Data Port with "
                                 "no data command outstanding")
            # See the read side: the ready bit is latched and cleared
            # before the block moves, so its state during the block says
            # nothing.
            self.fifo_out += (val & 0xFFFFFFFF).to_bytes(4, "little")
            if len(self.fifo_out) >= self.pending_write:
                self._finish_write()
            elif self.blksize and len(self.fifo_out) % self.blksize == 0:
                # The next block's worth of room, announced the same way
                # the read side announces the next block's worth of data.
                self.intstat |= k["SDHCI_INT_SPACE_AVAIL"]
            return
        if off == (k["SDHCI_CLOCK_CONTROL"] & ~3):
            # A DATA (or ALL) software reset is what clears a stuck DAT
            # Inhibit. This is the line that lets a correct driver
            # recover from a refused command and the line that leaves an
            # incorrect one wedged.
            if (val >> 24) & (k["SDHCI_RESET_DATA"] | k["SDHCI_RESET_ALL"]):
                self.dat_inhibited = False
            # Software Reset self-clears; store the rest.
            self.reg[off] = val & ~(
                (k["SDHCI_RESET_ALL"] | k["SDHCI_RESET_CMD"]
                 | k["SDHCI_RESET_DATA"]) << 24)
            if val & (k["SDHCI_CLOCK_CARD_EN"]):
                self.clock_on = True
            return
        if off == (k["SDHCI_POWER_CONTROL"] & ~3):
            self.reg[off] = val
            if (val >> 8) & k["SDHCI_POWER_ON"]:
                self.powered = True
            return
        if off == k["SDHCI_BLOCK_SIZE"]:
            self.blksize = val & 0xFFF
            self.blkcount = (val >> 16) & 0xFFFF
            self.reg[off] = val
            return
        if off == (k["SDHCI_TRANSFER_MODE"] & ~3):
            self._command(val)
            return
        self.reg[off] = val

    # -- the command --------------------------------------------------
    def _command(self, word: int) -> None:
        k = self.k
        shift = k["CMD_INDEX_SHIFT_IN_HALFWORD"]
        cmdreg = (word >> 16) & 0xFFFF
        index = (cmdreg >> shift) & 0x3F
        flags = cmdreg & 0xFF
        tm = word & 0xFFFF
        arg = self.reg.get(k["SDHCI_ARGUMENT"], 0)
        self.commands.append((index, flags, arg))

        if not self.powered:
            raise SystemExit(f"CMD{index} was issued before the bus was "
                             f"powered - SDHCI_POWER_ON was never written")

        # A command carrying data cannot be issued while DAT Inhibit is
        # set. The library's sdio_WaitInhibit is supposed to catch that
        # and time out; if it ever does not, the model says so rather
        # than quietly running the command anyway.
        if self.dat_inhibited and (flags & k["SDHCI_CMD_DATA"]):
            raise SystemExit(
                f"CMD{index} with data was issued while DAT Inhibit was "
                f"still set from an earlier REFUSED command. The data line "
                f"was never reset - see the R5 refusal path in "
                f"sdio_Cmd53Xfer")

        resp = self._card_command(index, flags, arg, tm)
        self.resp = [resp & 0xFFFFFFFF, 0, 0, 0]
        self.intstat |= k["SDHCI_INT_RESPONSE"]
        if flags & k["SDHCI_CMD_RESP_MASK"] == k["SDHCI_CMD_RESP_SHORT_BUSY"]:
            self.intstat |= k["SDHCI_INT_DATA_END"]

    def _card_command(self, index: int, flags: int, arg: int, tm: int) -> int:
        k = self.k
        card = self.card
        if index == k["MMC_GO_IDLE_STATE"]:
            return 0
        if index == k["SD_IO_SEND_OP_COND"]:
            if arg == 0:
                # The probe pass: functions and the OCR, busy CLEAR.
                return (MODEL_NFUNC << 28) | MODEL_OCR
            want = arg & 0x00FFFFFF
            if (want & MODEL_OCR) == 0:
                raise SystemExit("the image asked CMD5 for a voltage window "
                                 "this card does not support - a real card "
                                 "would go permanently inactive")
            card.opcond_polls += 1
            # Ready on the SECOND ask, so the poll loop is exercised
            # rather than skipped.
            busy = k["MMC_CARD_BUSY"] if card.opcond_polls >= 2 else 0
            return busy | (MODEL_NFUNC << 28) | MODEL_OCR
        if index == k["SD_SEND_RELATIVE_ADDR"]:
            card.rca = MODEL_RCA
            return MODEL_RCA << 16
        if index == k["MMC_SELECT_CARD"]:
            if (arg >> 16) != MODEL_RCA:
                raise SystemExit(f"CMD7 selected RCA ${arg >> 16:04X}, not the "
                                 f"one the card published (${MODEL_RCA:04X})")
            card.selected = True
            return 0
        if index == k["SD_IO_RW_DIRECT"]:
            return self._cmd52(arg)
        if index == k["SD_IO_RW_EXTENDED"]:
            return self._cmd53(arg, tm)
        raise SystemExit(f"the image issued CMD{index}, which is not one of "
                         f"the opcodes the cited headers define")

    def _decode(self, arg: int) -> tuple[int, int, int]:
        """rw, fn, addr - through the formula parsed out of sdio_ops.c."""
        k = self.k
        rw = 1 if (arg & k["ARG_WRITE"]) else 0
        fn = (arg >> k["ARG_FN_SHIFT"]) & 0x7
        addr = (arg >> k["ARG_ADDR_SHIFT"]) & k["ARG_ADDR_MAX"]
        return rw, fn, addr

    def _cmd52(self, arg: int) -> int:
        k = self.k
        rw, fn, addr = self._decode(arg)
        data = arg & 0xFF
        out = self.card.cmd52(bool(rw), fn, addr, data)
        self.trace.append(
            "CMD52 %-5s fn%d @$%05X %s$%02X"
            % ("write" if rw else "read", fn, addr,
               "-> " if not rw else "<- ", data if rw else out))
        return out & 0xFF          # R5: flags in 15:8 are all clear = ok

    def _cmd53(self, arg: int, tm: int) -> int:
        k = self.k
        rw, fn, addr = self._decode(arg)
        incr = 1 if (arg & k["ARG_INCR"]) else 0
        block = 1 if (arg & k["ARG_BLOCKMODE"]) else 0
        count = arg & 0x1FF
        if block:
            # BLOCK MODE. The nine bits are a BLOCK count and the card
            # takes the block SIZE from its own FBR register, which the
            # image must have written first - the argument does not
            # carry it. That is the one failure in this mode that has no
            # error bit anywhere on a real bus, so it is checked here.
            if count == 0:
                raise SystemExit(
                    "CMD53 block mode with a block count of 0. That is the "
                    "infinite form, which runs until a CCCR abort; nothing "
                    "in this project issues an abort mid-transfer, so a 0 "
                    "here is a hung bus")
            blocks = count
            fbr = self.card.fbr.get(fn * k["SDIO_FBR_STEP"]
                                    + k["SDIO_FBR_BLKSIZE"])
            fbr_hi = self.card.fbr.get(fn * k["SDIO_FBR_STEP"]
                                       + k["SDIO_FBR_BLKSIZE"] + 1, 0)
            if fbr is None:
                raise SystemExit(
                    f"CMD53 block mode on function {fn}, whose FBR block "
                    f"size was never written. The card would use its reset "
                    f"default and the two ends would count different numbers "
                    f"of bytes with no error bit set anywhere")
            card_blksz = (fbr_hi << 8) | fbr
            if card_blksz != self.blksize:
                raise SystemExit(
                    f"CMD53 block mode: the CARD's block size for function "
                    f"{fn} is {card_blksz} but SDHCI_BLOCK_SIZE says "
                    f"{self.blksize}. Those must be the same number or the "
                    f"transfer silently misaligns")
            if self.blkcount != blocks:
                raise SystemExit(
                    f"CMD53 asked for {blocks} blocks but SDHCI_BLOCK_COUNT "
                    f"says {self.blkcount}")
            multi = bool(tm & k["SDHCI_TRNS_MULTI"])
            if blocks > 1 and not multi:
                raise SystemExit(
                    f"CMD53 with {blocks} blocks and SDHCI_TRNS_MULTI clear; "
                    f"bcm2835-mmc.c line 632 sets it whenever blocks > 1")
            if blocks == 1 and multi:
                raise SystemExit(
                    "CMD53 with one block and SDHCI_TRNS_MULTI set; that "
                    "same line clears it whenever blocks == 1 and the "
                    "opcode is not a multi-block memory command")
            n = blocks * self.blksize
        else:
            n = 512 if count == 0 else count

            # ---- THE BYTE-MODE CEILING IS THE CARD'S, NOT THE
            # PROTOCOL'S. ADDED 2026-08-26, AFTER THIS MODEL PASSED A
            # BUILD THE SILICON REFUSED.
            #
            # This gate reported green while the board answered a
            # 256-byte byte-mode read of function 1 with an R5 refusal.
            # The model had no opinion about byte-mode length at all, so
            # it certified a bug. sdio_max_byte_size(),
            # Linux v6.12 drivers/mmc/core/sdio_io.c lines 189-202, is the rule Linux
            # applies and the reason it never issues one:
            #
            #     mval = host->max_blk_size            (512 here)
            #     mval = min(mval, cur_blksize)        (64 for func 1)
            #     return min(mval, 512u)
            #
            # The ceiling is taken from the card's OWN FBR register
            # rather than from anything the library announced, so a
            # library that chunks to a number it merely believes cannot
            # pass this by agreeing with itself.
            fbr = self.card.fbr.get(fn * k["SDIO_FBR_STEP"]
                                    + k["SDIO_FBR_BLKSIZE"])
            if fbr is not None:
                fbr_hi = self.card.fbr.get(fn * k["SDIO_FBR_STEP"]
                                           + k["SDIO_FBR_BLKSIZE"] + 1, 0)
                card_blksz = (fbr_hi << 8) | fbr
                ceiling = min(MODEL_HOST_MAX_BLK_SIZE, card_blksz, 512)
                if n > ceiling:
                    # An R5 REFUSAL, not an exception - because what the
                    # silicon did NEXT is the other half of the lesson.
                    # The controller sees a perfectly good Command
                    # Complete, no error bit is set anywhere, and the
                    # data phase it was promised never happens. DAT
                    # Inhibit therefore stays asserted for ever and
                    # every later command dies of a timeout that has
                    # nothing to do with this one. Modelling the refusal
                    # without modelling the wedge would let a driver
                    # that forgets to reset the data line still pass.
                    self.card_refused = True
                    self.dat_inhibited = True
                    self.trace.append(
                        "CMD53 REFUSED fn%d @$%05X %d bytes byte mode - the "
                        "function's ceiling is %d (R5 OUT_OF_RANGE)"
                        % (fn, addr, n, ceiling))
                    return k["R5_OUT_OF_RANGE"]

            if n != self.blksize:
                raise SystemExit(
                    f"CMD53 asked for {n} bytes but SDHCI_BLOCK_SIZE says "
                    f"{self.blksize}; the two must agree or the controller "
                    f"and the card disagree about the transfer length")
            if self.blkcount != 1:
                raise SystemExit(f"CMD53 byte mode with a block count of "
                                 f"{self.blkcount}; it must be 1")
            if tm & k["SDHCI_TRNS_MULTI"]:
                raise SystemExit("CMD53 byte mode with SDHCI_TRNS_MULTI set; "
                                 "a byte-mode transfer is one block")
        if not (tm & k["SDHCI_TRNS_BLK_CNT_EN"]):
            raise SystemExit("CMD53 without SDHCI_TRNS_BLK_CNT_EN; "
                             "bcm2835-mmc.c sets it unconditionally for any "
                             "command that carries data")
        if rw:
            if tm & k["SDHCI_TRNS_READ"]:
                raise SystemExit("a CMD53 WRITE with the transfer-mode read "
                                 "bit set")
            self.pending_write = n
            self.pending_target = (fn, addr, incr)
            self.fifo_out = bytearray()
            self.intstat |= k["SDHCI_INT_SPACE_AVAIL"]
            self.trace.append("CMD53 write fn%d @$%05X %d bytes incr=%d%s"
                              % (fn, addr, n, incr,
                                 " BLOCK x%d" % self.blkcount if block else ""))
        else:
            if not (tm & k["SDHCI_TRNS_READ"]):
                raise SystemExit("a CMD53 READ without the transfer-mode read "
                                 "bit set")
            self.fifo = bytearray(self.card.cmd53_read(fn, addr, n, incr))
            self.intstat |= k["SDHCI_INT_DATA_AVAIL"]
            self.trace.append("CMD53 read  fn%d @$%05X %d bytes incr=%d%s"
                              % (fn, addr, n, incr,
                                 " BLOCK x%d" % self.blkcount if block else ""))
        return 0

    def _finish_write(self) -> None:
        fn, addr, incr = self.pending_target
        self.card.cmd53_write(fn, addr, bytes(self.fifo_out), incr)
        self.fifo_out = bytearray()
        self.pending_write = 0
        self.pending_target = None
        self.intstat |= self.k["SDHCI_INT_DATA_END"]


class Firmware:
    """The VideoCore's property channel, for the tags the probe uses."""

    def __init__(self, k: dict) -> None:
        self.k = k
        self.by_number = {
            k["RPI_FIRMWARE_GET_CLOCK_RATE"]: "GET_CLOCK_RATE",
            k["RPI_FIRMWARE_GET_GPIO_CONFIG"]: "GET_GPIO_CONFIG",
            k["RPI_FIRMWARE_SET_GPIO_CONFIG"]: "SET_GPIO_CONFIG",
            k["RPI_FIRMWARE_GET_GPIO_STATE"]: "GET_GPIO_STATE",
            k["RPI_FIRMWARE_SET_GPIO_STATE"]: "SET_GPIO_STATE",
            k["RPI_FIRMWARE_GET_POWER_STATE"]: "GET_POWER_STATE",
            k["RPI_FIRMWARE_SET_POWER_STATE"]: "SET_POWER_STATE",
            k["RPI_FIRMWARE_GET_CLOCK_STATE"]: "GET_CLOCK_STATE",
            k["RPI_FIRMWARE_SET_CLOCK_STATE"]: "SET_CLOCK_STATE",
            k["RPI_FIRMWARE_GET_CLOCK_MEASURED"]: "GET_CLOCK_MEASURED",
        }
        self.clock_asked: list[int] = []
        self.gpio_set: list[tuple[int, int, int]] = []   # gpio, dir, state
        self.wl_on_at_command = None
        # The rate the modelled firmware reports for the EMMC clock, in
        # Hz.  Deliberately NOT 250 MHz: that is the number fat.pi4
        # records for EMMC2, and a library that had it hard-coded would
        # pass a gate that used it too.
        self.emmc_hz = 200_000_000
        self.emmc2_hz = 250_000_000

        # ---- the expander, as a level per firmware GPIO --------------
        # SET_GPIO_CONFIG and SET_GPIO_STATE both move it and
        # GET_GPIO_STATE reads it back, so the model has to hold it
        # rather than answer each tag in isolation.  Everything starts
        # LOW, which is the pessimistic assumption and the one the board
        # appears to agree with: the first bench run found WL_ON not
        # asserted.
        # THE EXPANDER, AS THE BOARD ACTUALLY PRESENTED IT on 2026-08-26.
        # The firmware had ALREADY configured WL_ON as an output and
        # ALREADY driven it high before our image ran, which is
        # consistent with bcm2711-rpi-4-b.dts deleting the wifi-pwrseq
        # node: no downstream driver sequences this pin because the
        # firmware has.  A model that started the pin low would let the
        # library get away with a sequence that only works on a pin it
        # is allowed to write - and it is not allowed to write it.
        wl = k["RPI_EXP_GPIO_BASE"] + 1
        self.gpio_level: dict[int, int] = {wl: 1}
        self.gpio_dir: dict[int, int] = {wl: 1}

        # ---- power devices and clocks, as the firmware sees them -----
        # REWRITTEN 2026-08-26 EVENING FROM THE SECOND BENCH RUN.  The
        # model now reproduces what the Pi 4's firmware actually said,
        # including the parts that make no sense, because a model that
        # is more coherent than the silicon cannot catch a library that
        # believes the silicon.
        #
        #     power devid 0       state 1   exists, ON
        #     power devid 1..10   state 0   exists, off
        #
        # Device id 1 is UART0 - the property document's own list, line
        # 169 - and UART0 was transmitting that very line.  So: every id
        # answers, none reports NODEV, and only id 0 reports on.
        self.power_devids = set(range(0, 11))
        self.power_on: dict[int, int] = {0: 1}
        # Clock 1 (EMMC) reports OFF and clock 12 (EMMC2) reports ON,
        # while clock 1 MEASURES 250000496 Hz.  The contradiction is the
        # finding, so it is modelled rather than tidied away.
        self.clock_ids = {k["BCM2835_MBOX_CLOCK_ID_EMMC"],
                          k["BCM2835_MBOX_CLOCK_ID_EMMC2"]}
        self.clock_on: dict[int, int] = {
            k["BCM2835_MBOX_CLOCK_ID_EMMC"]: 0,
            k["BCM2835_MBOX_CLOCK_ID_EMMC2"]: 1,
        }
        # And SET_CLOCK_STATE does not stick on the EMMC clock: the
        # board read back 0 afterwards.  The library has to keep working
        # with a clock it cannot claim, so the model refuses to be
        # claimed.
        self.clock_set_sticks = False
        # SET_GPIO_CONFIG is DECLINED - the tag comes back with its own
        # response bit clear, which is how the firmware says "I did not
        # service that", and which mailbox.pi4 reports as #MBX_ERR_TAG.
        # This is what stopped the WL_ON ladder at rung 3 on the board.
        # Every other expander tag on the same pin worked.
        # THE OBSERVED SYMPTOM, NOT A CONCLUSION ABOUT ITS CAUSE.
        # Measured on the board: GET_GPIO_CONFIG and GET_GPIO_STATE
        # answered for pin 129 in the same run in which SET_GPIO_CONFIG
        # and SET_GPIO_STATE both came back with that tag's response bit
        # clear, which mailbox.pi4 reports as #MBX_ERR_TAG.
        #
        # WHY THAT HAPPENS IS OPEN.
        # It may be that the firmware declines expander writes.  It may
        # instead be that these sets return a zero-length reply and
        # mailbox.pi4's per-tag check - stricter than U-Boot's, by its
        # own header - is reading a success as a failure.  See AN OPEN
        # QUESTION in RaspberryPi4/Lib/sdio.pi4.
        #
        # THE MODEL REPRODUCES THE SYMPTOM EITHER WAY, and that is the
        # point: a library that survives this response is a library that
        # is correct under both explanations.  If the second one wins,
        # the fix belongs in mailbox.pi4 and these two lines go away
        # without sdio.pi4 changing.
        self.declined = {"SET_GPIO_CONFIG", "SET_GPIO_STATE"}
        self.declined_seen: list[str] = []
        # Whether the FIRST GET_GPIO_STATE of the run found the pin
        # already high.  The low half of a power cycle is only legal
        # when it did; see the check that reads this.
        self.wl_on_found_high = False
        self._first_get_state_done = False
        # When the pin first became KNOWN HIGH - by a read that said so
        # or by a write that took - measured in SD commands issued so
        # far.  Reading it high is just as good as driving it high, and
        # on this firmware it is the only option available.
        self.wl_on_known_high_at_command = None
        self.wl_on_writes = 0
        self._cmd_count = None
        self.power_set: list[tuple[int, int]] = []
        self.clock_set: list[tuple[int, int]] = []
        # How many words the image declared for GET_GPIO_CONFIG.  The
        # answer must be five; see the check that reads it.
        self.get_cfg_words = None

    # Bit 0 on/off, bit 1 "does not exist" - the encoding shared by both
    # power-state tags and both clock-state tags.
    ON = 1
    NODEV = 2

    def commands_so_far(self) -> int:
        # Wired up by Board so the firmware model can timestamp events
        # against SD commands; 0 until a controller is attached.
        return self._cmd_count() if self._cmd_count else 0

    def answer(self, name: str, values: list[int]) -> list[int]:
        k = self.k
        if name == "GET_CLOCK_RATE":
            cid = values[0]
            self.clock_asked.append(cid)
            if cid == k["BCM2835_MBOX_CLOCK_ID_EMMC"]:
                return [cid, self.emmc_hz]
            if cid == k["BCM2835_MBOX_CLOCK_ID_EMMC2"]:
                return [cid, self.emmc2_hz]
            return [cid, 0]
        if name == "GET_CLOCK_MEASURED":
            # The measured rate is zero while the clock is gated.  That
            # is the whole point of the tag and the reason the probe
            # prints it beside GET_CLOCK_RATE, which answers with a rate
            # either way.
            cid = values[0]
            if not self.clock_on.get(cid, 0):
                return [cid, 0]
            if cid == k["BCM2835_MBOX_CLOCK_ID_EMMC"]:
                return [cid, self.emmc_hz]
            if cid == k["BCM2835_MBOX_CLOCK_ID_EMMC2"]:
                return [cid, self.emmc2_hz]
            return [cid, 0]
        if name == "GET_GPIO_CONFIG":
            # gpio, direction, polarity, term_en, term_pull_up.  FIVE
            # words - struct gpio_get_config has no trailing state - and
            # word 0 comes back 0 on success, which is what the expander
            # driver checks.
            g = values[0]
            self.get_cfg_words = len(values)
            return [0, self.gpio_dir.get(g, 0), 0, 0, 0]
        if name == "SET_GPIO_CONFIG":
            g = values[0]
            self.gpio_dir[g] = values[1]
            self.gpio_level[g] = values[5]
            self.gpio_set.append((g, values[1], values[5]))
            return [0, 0, 0, 0, 0, 0]
        if name == "GET_GPIO_STATE":
            g = values[0]
            lvl = self.gpio_level.get(g, 0)
            if not self._first_get_state_done:
                self._first_get_state_done = True
                self.wl_on_found_high = (lvl == 1)
            if lvl == 1 and self.wl_on_known_high_at_command is None:
                self.wl_on_known_high_at_command = self.commands_so_far()
            return [0, lvl]
        if name == "SET_GPIO_STATE":
            g = values[0]
            self.gpio_level[g] = values[1]
            self.gpio_set.append((g, self.gpio_dir.get(g, 0), values[1]))
            return [0, values[1]]
        if name == "GET_POWER_STATE":
            d = values[0]
            if d not in self.power_devids:
                return [d, Firmware.NODEV]
            return [d, self.power_on.get(d, 0) & Firmware.ON]
        if name == "SET_POWER_STATE":
            d = values[0]
            if d not in self.power_devids:
                return [d, Firmware.NODEV]
            self.power_set.append((d, values[1]))
            self.power_on[d] = values[1] & Firmware.ON
            return [d, self.power_on[d]]
        if name == "GET_CLOCK_STATE":
            c = values[0]
            if c not in self.clock_ids:
                return [c, Firmware.NODEV]
            return [c, self.clock_on.get(c, 0) & Firmware.ON]
        if name == "SET_CLOCK_STATE":
            c = values[0]
            if c not in self.clock_ids:
                return [c, Firmware.NODEV]
            self.clock_set.append((c, values[1]))
            # The board accepted this tag and the state did not move.
            # See clock_set_sticks: the request is acknowledged, the
            # clock stays where it was, and the library has to notice
            # the difference between that and a refusal.
            if self.clock_set_sticks:
                self.clock_on[c] = values[1] & Firmware.ON
            return [c, self.clock_on.get(c, 0) & Firmware.ON]
        return [0]


class Board:
    def __init__(self, cpu: A64, k: dict, hc: Sdhci, fw: Firmware) -> None:
        self.cpu = cpu
        self.k = k
        self.hc = hc
        fw._cmd_count = lambda: len(hc.commands)
        self.fw = fw
        self.uart = bytearray()
        self.reply: int | None = None
        self.steps = 0
        self.gpfsel3 = 0x00000000
        self.gppup2 = 0xAAAAAAAA      # every pin pulled up, so a write
                                      # that changes a field outside the
                                      # six is visible
        self.gpfsel3_before = self.gpfsel3
        self.gppup2_before = self.gppup2
        self.gpio_writes = 0

    def mailbox_write(self, msg: int) -> None:
        chan = msg & 0xF
        if chan != MBX_CHANNEL:
            raise SystemExit(f"the image used mailbox channel {chan}, not 8")
        arm = (msg & ~0xF) - BUS_OFFSET
        ld = self.cpu.load
        st = self.cpu.store
        total = ld(arm + 0, 4)
        tag = ld(arm + 8, 4)
        vallen = ld(arm + 12, 4)
        values = [ld(arm + 20 + i * 4, 4) for i in range(vallen // 4)]
        name = self.fw.by_number.get(tag)
        if name is not None and name in self.fw.declined:
            # THE FIRMWARE ANSWERED AND DID NOT SERVICE THE TAG.  Whole
            # message SUCCESS, tag response bit left CLEAR.  That is a
            # real thing this firmware does - it is what happened to
            # SET_GPIO_CONFIG on the board - and it is a different
            # failure from an unrecognised tag, from a transport
            # timeout, and from an outright error code.  mailbox.pi4
            # reports it as #MBX_ERR_TAG.
            self.fw.declined_seen.append(name)
            if name == "SET_GPIO_CONFIG" or name == "SET_GPIO_STATE":
                if values and values[0] == self.k["RPI_EXP_GPIO_BASE"] + 1:
                    self.fw.wl_on_writes += 1
            st(arm + 4, 0x80000000, 4)
            st(arm + 16, 0, 4)
            self.reply = msg
            return
        if name is None:
            st(arm + 4, 0x80000000, 4)
            st(arm + 16, 0, 4)
        else:
            # FIRST write wins, not last.  The library power-cycles
            # WL_ON now - config low, wait, state high - so there are
            # two writes and the question the check below asks is when
            # the SEQUENCE started relative to the SD commands.
            if name == "SET_GPIO_CONFIG" or name == "SET_GPIO_STATE":
                if self.fw.wl_on_at_command is None:
                    self.fw.wl_on_at_command = len(self.hc.commands)
                if values and values[0] == self.k["RPI_EXP_GPIO_BASE"] + 1:
                    self.fw.wl_on_writes += 1
            resp = self.fw.answer(name, values)
            for i, v in enumerate(resp):
                if 20 + i * 4 < total:
                    st(arm + 20 + i * 4, v & 0xFFFFFFFF, 4)
            st(arm + 4, 0x80000000, 4)
            st(arm + 16, 0x80000000 | (len(resp) * 4), 4)
        self.reply = msg


def build(compiler: str, source: pathlib.Path, out: pathlib.Path) -> None:
    # A diagnostic, not a board file: nothing here is a build of Anvil, so
    # nothing is recorded with tools/build_count.py.
    r = subprocess.run(
        [compiler, "--compile", str(source), "-t", "pi4",
         "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
         "--entry-returns", "-o", str(out)],
        cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not out.is_file():
        raise SystemExit("The compile of %s failed, so there is no image to "
                         "run:\n%s" % (source, r.stdout))


def run(img: pathlib.Path, k: dict, board_out: list, limit: int = 60_000_000,
        dram: dict | None = None):
    blob = img.read_bytes()
    cpu = A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    # A fault names "procedure+offset, file line" from the compiler's .dbg
    # rather than printing a bare hex PC.
    attach_symbols(cpu, img, LOAD)
    # DRAM the payload expects to find already populated - on the board
    # Anvil's `load` puts the firmware there before the payload runs, so
    # the gate does the same rather than pretending the payload reads
    # a filesystem it does not touch.
    if dram:
        for addr, data in dram.items():
            for i, b in enumerate(data):
                cpu.memory[addr + i] = b
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR

    card = Cyw43Card(k)
    hcbase = k["SOC_ARM_BASE"] + (k["MMCNR_BUS"] - k["SOC_BUS_BASE"])
    hc = Sdhci(k, card, hcbase)
    fw = Firmware(k)
    board = Board(cpu, k, hc, fw)
    board_out.append(board)
    board_out.append(hc)
    board_out.append(card)
    board_out.append(fw)

    mem = cpu.memory
    top = hcbase + k["MMCNR_SIZE"]

    # EVERY closure below calls cpu.align_guard FIRST.  The rule and its
    # argument live in a64_interp.py; this payload never enables the MMU,
    # so the strict default applies to every wide data access.

    def load(addr: int, size: int) -> int:
        cpu.align_guard(addr, size, False)
        if addr >= 0xFE000000:
            if addr == UART_FR:
                return 0
            if addr == MBX_STATUS1:
                return 0
            if addr == MBX_STATUS0:
                return 0 if board.reply is not None else MBX_EMPTY
            if addr == MBX_READ:
                r = board.reply
                if r is None:
                    raise SystemExit("the image read an empty mailbox")
                board.reply = None
                return r
            if addr == GPFSEL3:
                return board.gpfsel3
            if addr == GPPUP2:
                return board.gppup2
            if hcbase <= addr < top:
                return hc.read(addr - hcbase)
            raise SystemExit(
                f"unmodelled MMIO read at ${addr:08X}. If that is inside "
                f"another SD controller's window, the library has the wrong "
                f"base address - see sdio.pi4's THE CONTROLLER.")
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr: int, value: int, size: int) -> None:
        cpu.align_guard(addr, size, True)
        v = value & 0xFFFFFFFF
        if addr >= 0xFE000000:
            if addr == UART_DR:
                board.uart.append(value & 0xFF)
                return
            if addr == MBX_WRITE:
                board.mailbox_write(v)
                return
            if addr == GPFSEL3:
                board.gpfsel3 = v
                board.gpio_writes += 1
                return
            if addr == GPPUP2:
                board.gppup2 = v
                board.gpio_writes += 1
                return
            if hcbase <= addr < top:
                hc.write(addr - hcbase, v)
                return
            raise SystemExit(
                f"unmodelled MMIO write at ${addr:08X}. A store to a real, "
                f"powered peripheral that is not the intended one is the "
                f"failure this whole gate exists to catch.")
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)

    def step() -> None:
        board.steps += 1
        ins = load(cpu.pc, 4)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:        # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:        # MRS Xt, CNTPCT_EL0
            cpu.x[ins & 31] = board.steps * TICKS_PER_STEP
            cpu.pc += 4
            return
        plain_step()

    cpu.step = step
    n = 0
    try:
        while cpu.pc != LOADER_LR:
            n += 1
            if n > limit:
                raise SystemExit("the probe never returned to its loader\n"
                                 + board.uart.decode("latin-1"))
            step()
    except AlignmentFault as fault:
        # Refuse, loudly, exactly where silicon would fault.  On the board
        # no vector is installed, so this is not a message there - it is a
        # payload that stops printing mid-line and never comes back.
        raise SystemExit(board.uart.decode("latin-1") + "\n" + fault.message())
    return cpu, board


# =====================================================================
#  THE ASSERTIONS
# =====================================================================

def scan_gate(k: dict, verbose: bool, compiler: str, work: pathlib.Path,
              nvram_path: str | None) -> int:
    """Build and run pi4WifiScan.pi4 against the SDPCM model.

    THIS IS THE SLOW ONE AND THE REASON IS ARITHMETIC. The payload CRCs
    609,309 bytes bit by bit and then uploads and reads back the whole
    image, so the emulator executes tens of millions of instructions.
    It is a gate to run before a board session, not on every edit.
    """
    fails: list[str] = []

    checks = [0]

    def ck(cond, msg):
        checks[0] += 1
        if not cond:
            fails.append(msg)

    fw = FIRMWARE / "brcmfmac43455-sdio.bin"
    clm = FIRMWARE / "brcmfmac43455-sdio.clm_blob"
    for f in (fw, clm):
        if not f.exists():
            raise SystemExit(
                f"The firmware is missing: {f}. pi4WifiScan expects Anvil to "
                "have loaded it into DRAM, so the gate loads the same bytes "
                "from the repository; without it this gate tests nothing.")
    if nvram_path:
        nv = pathlib.Path(nvram_path)
        if not nv.is_file():
            raise SystemExit(f"The NVRAM file named by --nvram does not exist: {nv}")
        nvb = nv.read_bytes()
        nv_what = str(nv)
    else:
        nvb = SYNTHETIC_NVRAM
        nv_what = "the synthetic NVRAM text"

    fwb = fw.read_bytes()
    clmb = clm.read_bytes()
    # What cyw43.pi4 must turn the NVRAM into, from brcmfmac's parser rules
    # and not from the library. For the board's own 2,074-byte text this
    # model yields 1,748 bytes, which is the length the board measured.
    cooked_want = cook_nvram_model(nvb)
    if not nvram_path:
        # The entry list, NUL-terminated entries included, is everything
        # before the padding: the last entry's own NUL survives rstrip as +1.
        entries = len(cooked_want[:-4].rstrip(b"\0")) + 1
        if entries % 4 != 0:
            raise SystemExit(
                "The synthetic NVRAM's entries are %d bytes, not a multiple "
                "of four, so the roundup(len + 1, 4) terminator case is no "
                "longer exercised. Adjust SYNTHETIC_NVRAM rather than "
                "letting that coverage lapse." % entries)

    # THE ADDRESSES AND CRCs COME OUT OF THE ARTEFACT, NOT OUT OF THIS
    # FILE. pi4WifiScan refuses to run unless DRAM CRCs to a constant it
    # carries; if the gate typed its own copy of that constant the two
    # could drift and the gate would be loading the wrong bytes into a
    # payload that was checking for different ones.
    src = SCAN.read_text(encoding="utf-8", errors="replace")

    def const(name: str) -> int:
        m = re.search(r"^#" + name + r"\s*=\s*(\$?[0-9A-Fa-f]+)\s*$",
                      src, re.M)
        if not m:
            raise SystemExit(f"pi4WifiScan.pi4 no longer declares #{name}")
        t = m.group(1)
        return int(t[1:], 16) if t.startswith("$") else int(t)

    fw_addr, fw_len, fw_crc = const("FW_ADDR"), const("FW_LEN"), const("FW_CRC")
    nv_addr, nv_len, nv_crc = const("NV_ADDR"), const("NV_LEN"), const("NV_CRC")
    clm_addr, clm_len, clm_crc = (const("CLM_ADDR"), const("CLM_LEN"),
                                  const("CLM_CRC"))

    ck(len(fwb) == fw_len,
       "the firmware in the repository is %d bytes but pi4WifiScan expects "
       "%d" % (len(fwb), fw_len))
    ck(zlib.crc32(fwb) & 0xFFFFFFFF == fw_crc,
       "the firmware's crc32 is $%08X but pi4WifiScan expects $%08X - the "
       "board's own read-back measured that constant, so a mismatch means "
       "the repository copy is not the file the board ran"
       % (zlib.crc32(fwb) & 0xFFFFFFFF, fw_crc))
    # THE NVRAM CONSTANTS IN THE ARTEFACT DESCRIBE ONE BOARD'S FILE, which
    # is not in this repository. When the text being uploaded is a
    # different one, the gate builds a COPY of pi4WifiScan with #NV_LEN
    # and #NV_CRC set to that text's length and crc32 - exactly one line
    # each, refused loudly if the declarations ever stop being unique -
    # so the payload's own CRC guard still runs, against the bytes that
    # are really in DRAM. The firmware and CLM constants are never
    # rewritten: those files ARE in the repository and must match.
    payload = src
    nv_crc_have = zlib.crc32(nvb) & 0xFFFFFFFF
    if len(nvb) != nv_len or nv_crc_have != nv_crc:
        for name, val in (("NV_LEN", "%d" % len(nvb)),
                          ("NV_CRC", "$%08X" % nv_crc_have)):
            pat = re.compile(r"^#" + name + r"\s*=\s*\$?[0-9A-Fa-f]+\s*$",
                             re.M)
            if len(pat.findall(payload)) != 1:
                raise SystemExit(
                    "pi4WifiScan.pi4 no longer declares #%s exactly once, so "
                    "the gate cannot point the payload's CRC guard at %s."
                    % (name, nv_what))
            payload = pat.sub(lambda _m: "#%s = %s" % (name, val), payload)
        print("scan gate: uploading %s (%d bytes, crc32 $%08X) through a copy "
              "of pi4WifiScan whose #NV_LEN/#NV_CRC name it; the artefact's "
              "own constants describe the board's file (%d bytes, crc32 $%08X)"
              % (nv_what, len(nvb), nv_crc_have, nv_len, nv_crc))
    ck(len(nvb) + 8 <= const("NV_WORK_MAX"),
       "the NVRAM text is %d bytes and pi4WifiScan's cook buffer holds %d; "
       "cyw43_NvramCook needs length + 8" % (len(nvb), const("NV_WORK_MAX")))
    ck(len(clmb) == clm_len,
       "the CLM blob is %d bytes, not %d" % (len(clmb), clm_len))
    ck(zlib.crc32(clmb) & 0xFFFFFFFF == clm_crc,
       "the CLM blob's crc32 is $%08X but pi4WifiScan expects $%08X - that "
       "constant was measured on the board with Anvil's own crc32 over "
       "BRCMCLM.BLB, so a mismatch means the stick and the repository hold "
       "different blobs"
       % (zlib.crc32(clmb) & 0xFFFFFFFF, clm_crc))
    if fails:
        print("\na64_sdio_check --scan: FAIL - %d of %d checks failed"
              % (len(fails), checks[0]))
        for f in fails:
            print("   " + f)
        return 1

    print("scan gate: firmware %d bytes crc32 $%08X, nvram %d bytes "
          "crc32 $%08X, clm %d bytes crc32 $%08X - all three match what "
          "pi4WifiScan expects"
          % (len(fwb), zlib.crc32(fwb) & 0xFFFFFFFF,
             len(nvb), zlib.crc32(nvb) & 0xFFFFFFFF,
             len(clmb), zlib.crc32(clmb) & 0xFFFFFFFF))
    o = k["BSS_OFF"]
    print("scan gate: bss_info offsets derived from the header - "
          "SSID +%d, chanspec +%d, RSSI +%d, ctl_ch +%d, size %d"
          % (o["SSID"], o["chanspec"], o["RSSI"], o["ctl_ch"], o["__size__"]))
    print("scan gate: event prefix %d = ethhdr 14 + brcm_ethhdr %d + msg %d"
          % (k["EVENT_PREFIX"], k["BRCM_ETHHDR_LEN"], k["EVENT_MSG_BE_LEN"]))
    print("scan gate: building and running. THIS TAKES MINUTES - the payload "
          "CRCs and uploads the real 609 KB image, so the emulator executes "
          "tens of millions of instructions.", flush=True)

    img = work / "scancheck.img"
    if payload != src:
        copy = work / SCAN.name
        copy.write_text(payload, encoding="utf-8", newline="")
        build(compiler, copy, img)
    else:
        build(compiler, SCAN, img)

    parts: list = []
    t0 = time.time()
    cpu, board = run(img, k, parts, limit=400_000_000,
                     dram={fw_addr: fwb, nv_addr: nvb, clm_addr: clmb})
    board, hc, card, fwm = parts[0], parts[1], parts[2], parts[3]
    text = board.uart.decode("utf-8", "replace")
    print(text)
    if verbose:
        for t in hc.trace[-40:]:
            print("   " + t)

    def said(label: str):
        m = re.search(re.escape(label) + r"\s+(-?\d+)", text)
        return int(m.group(1)) if m else None

    # -- the bring-up still holds ---------------------------------------
    ck(said("Cyw43UploadFirmware (want 1)") == 1,
       "the firmware upload failed under the model")
    ck(said("Cyw43UploadNvram (want 1)") == 1, "the NVRAM upload failed")
    # THE COOKED NVRAM, BY LENGTH AND BY BYTE. The length is padded length
    # plus the four-byte token; the bytes are read back out of the modelled
    # chip RAM where Cyw43UploadNvram put them - measured DOWN from the top
    # of RAM, sdio.c's "ramsize - varsz + rambase" - so the comment
    # stripping, the padding and the token are all compared against the
    # parser model, not merely counted.
    ck(said("nvram after cooking") == len(cooked_want),
       "the cooked NVRAM is %s bytes; firmware.c's parser makes %d bytes of "
       "%s, which is padded length plus the four-byte token"
       % (said("nvram after cooking"), len(cooked_want), nv_what))
    nv_dest = MODEL_RAMBASE + MODEL_RAMSIZE - len(cooked_want)
    nv_got = b"".join(card.backplane.get(nv_dest + i, 0).to_bytes(4, "little")
                      for i in range(0, len(cooked_want), 4))
    ck(nv_got == cooked_want,
       "the %d bytes at the top of chip RAM ($%08X) are not the cooked NVRAM "
       "firmware.c's parser produces for %s; first difference at byte %s"
       % (len(cooked_want), nv_dest, nv_what,
          next((i for i in range(len(cooked_want))
                if nv_got[i] != cooked_want[i]), None)))
    ck(said("Cyw43Start (want 1)") == 1, "the ARM was not released")
    ck(said("enable F2 (want 1)") == 1, "F2 never came ready")

    # -- the CLM -----------------------------------------------------------
    # THE BYTES ARE COMPARED, NOT THE COUNT. The model reassembles the
    # blob out of the chunks it was sent, so this is the check that a
    # chunk was not dropped, duplicated, truncated or sent twice - none
    # of which the chunk count would notice.
    ck(bytes(card.clm) == clmb,
       "the blob the model reassembled from the chunks is %d bytes and the "
       "file is %d; the chunking dropped, duplicated or truncated something"
       % (len(card.clm), len(clmb)))
    ck(card.clm_done,
       "no clmload chunk ever carried DL_END, so the firmware would still "
       "be waiting for the rest of the blob")
    expect_chunks = (len(clmb) + 1023) // 1024
    ck(card.clm_chunks == expect_chunks,
       "the model received %d clmload chunks; %d bytes at #CYW43_CLM_CHUNK "
       "= 1024 is %d" % (card.clm_chunks, len(clmb), expect_chunks))
    ck(expect_chunks >= 3,
       "this blob no longer needs three chunks, so the gate has stopped "
       "covering the middle-chunk case - the one neither reference driver "
       "exercises. Say so rather than letting the coverage lapse quietly")
    ck(card.clm_status_reads == 1,
       "clmload_status was read %d times, not once. The upload is not "
       "verified unless it is asked about" % card.clm_status_reads)
    ck(said("  clm chunks sent") == expect_chunks,
       "the payload reported %s chunks sent, the model counted %d"
       % (said("  clm chunks sent"), expect_chunks))
    ck(said("  clm status (want 0)") == 0,
       "the payload did not report clm status 0")

    # -- the transport ---------------------------------------------------
    ck(said("Cyw43WifiUp (want 0)") == 0, "WLC_UP did not succeed")
    ck(card.wlc_up == 1,
       "the model saw WLC_UP %d times, not once" % card.wlc_up)
    ck(card.event_mask is not None,
       "the event mask was never set, so ESCAN_RESULT would never arrive")
    ck(said("Cyw43ScanStart (want 0)") == 0, "the scan request was refused")
    ck(card.escan_started == 1,
       "the model saw %d escan requests, not one" % card.escan_started)

    # -- the three questions the payload asks the radio --------------------
    # The model answers all three, so these check that the payload ASKS
    # and reads the answer back correctly. What the answers MEAN is a
    # board question and the model is explicit about not knowing.
    for want in (b"clmver", b"country", b"scan_ver"):
        ck(want in card.gets,
           "the payload never read the %r iovar" % want.decode())
    ck(said("scan_ver status  ") == -23,
       "the payload read scan_ver status %s; the model refuses the iovar "
       "with -BRCMF_FW_UNSUPPORTED (-23) and the payload has to sign-extend "
       "a 32-bit status into a 64-bit register to see it"
       % said("scan_ver status  "))
    ck("escan v1 is correct" in text,
       "the payload did not conclude v1 from a -23 scan_ver status")

    # -- AND THE POINT OF ALL OF IT --------------------------------------
    # Every SSID the model wrote must come back, in order, spelled the
    # way the model spelled it. This is what catches a wrong bss_info
    # offset: the fields are laid out by the struct calculator and read
    # back by cyw43.pi4's own constants, and nothing connects the two
    # except being right.
    #
    # THE ROWS ARE PARSED, NOT SEARCHED FOR. This block used to ask
    # whether each SSID, each channel and each RSSI appeared ANYWHERE in
    # the log, which is three independent substring tests that a table
    # with the right values in the wrong rows passes cleanly. It cannot
    # survive folding: the whole question now is which value ended up on
    # which row. Every network row carries " dBm" and nothing else in
    # the log does, so the rows come out in order and each is read as a
    # record.
    rows = []
    for ln in text.splitlines():
        if " dBm" not in ln:
            continue
        m = re.match(
            r"\s*(\d+)\s+ch\s+(\d+)(?:/c(\d+))?\s+(-?\d+) dBm\s+"
            r"(enc|open)\s+([0-9A-F]{2}(?::[0-9A-F]{2}){5})\s\s(.*?)\s*$", ln)
        if not m:
            fails.append("a network row did not parse: %r. The gate reads "
                         "the columns out of this line, so a change to the "
                         "row format in pi4WifiScan.pi4 has to be matched "
                         "here" % ln)
            continue
        rows.append({"idx": int(m.group(1)), "chan": int(m.group(2)),
                     "cspec": m.group(3), "rssi": int(m.group(4)),
                     "priv": m.group(5), "bssid": m.group(6),
                     "ssid": m.group(7)})

    ck(said("networks found") == len(MODEL_BSS),
       "the scan reported %s networks; the model sent %d DISTINCT ones "
       "(plus %d repeats of them, which must fold rather than appear)"
       % (said("networks found"), len(MODEL_BSS), len(MODEL_BSS_REPEATS)))
    ck(len(rows) == len(MODEL_BSS),
       "the log holds %d network rows, not %d" % (len(rows), len(MODEL_BSS)))

    # WHAT EACH ROW MUST SAY, WORKED OUT FROM THE STREAM RATHER THAN
    # COPIED. The surviving RSSI is the STRONGEST reading of that BSSID,
    # over the first sighting and every repeat - which is the rule
    # cyw43_ParseBss states, computed here independently of it.
    best = {}
    for i, (_s, _c, rssi, _p) in enumerate(MODEL_BSS):
        best[i] = rssi
    for _before, idx, rssi in MODEL_BSS_REPEATS:
        best[idx] = max(best[idx], rssi)

    for i, (ssid, chan, rssi, priv) in enumerate(MODEL_BSS):
        if ssid:
            want = "".join(chr(c) if 32 <= c <= 126 else "." for c in ssid)
        else:
            want = "<hidden>"
        if i >= len(rows):
            continue
        row = rows[i]
        ck(row["idx"] == i,
           "row %d is numbered %d; the rows are out of order" % (i, row["idx"]))
        ck(row["ssid"] == want,
           "row %d prints its name as %r and should print %r. A wrong SSID "
           "offset produces a plausible name, not an error"
           % (i, row["ssid"], want))
        ck(row["chan"] == chan,
           "row %d shows channel %d, not %d" % (i, row["chan"], chan))
        ck(row["rssi"] == best[i],
           "row %d shows %d dBm; the strongest reading the model sent for "
           "that BSSID is %d. An RSSI read unsigned prints %d instead, a "
           "fold that keeps the LAST reading instead of the best one prints "
           "whichever repeat came last"
           % (i, row["rssi"], best[i], best[i] & 0xFFFF))
        ck(row["priv"] == ("enc" if priv else "open"),
           "row %d is %s and should be %s"
           % (i, row["priv"], "enc" if priv else "open"))
        ck(row["bssid"] == "02:11:22:33:44:%02X" % chan,
           "row %d shows BSSID %s; _bss_record writes 02:11:22:33:44:%02X "
           "for a network on channel %d" % (i, row["bssid"], chan, chan))

    # -- THE FOLD ---------------------------------------------------------
    # The model said the same thing several times; the table has to have
    # noticed. Three separate readings, because each of them fails on a
    # different mistake:
    #
    #   * the count of folds, which a parser that appends leaves at zero
    #     while the row count goes to eight;
    #   * the overflow counter, which must stay zero - a duplicate that
    #     consumed a table slot would be silently correct here at 32
    #     rows and wrong at 33;
    #   * the arithmetic, rows + folds = PARTIALs the model measured
    #     itself putting on the wire, which catches a record quietly
    #     dropped on a path that counts neither.
    ck(card.escan_partials == len(MODEL_BSS) + len(MODEL_BSS_REPEATS),
       "the model emitted %d PARTIAL results; %d networks plus %d repeats "
       "is %d" % (card.escan_partials, len(MODEL_BSS),
                  len(MODEL_BSS_REPEATS),
                  len(MODEL_BSS) + len(MODEL_BSS_REPEATS)))
    ck(said("duplicates folded") == len(MODEL_BSS_REPEATS),
       "the driver folded %s records; the model sent %d repeats of BSSIDs "
       "it had already reported. Zero here means cyw43_ParseBss is still "
       "appending every record, which is what this list exists to catch"
       % (said("duplicates folded"), len(MODEL_BSS_REPEATS)))
    if said("networks found") is not None and said("duplicates folded") is not None:
        ck(said("networks found") + said("duplicates folded")
           == card.escan_partials,
           "%s rows plus %s folds is not the %d PARTIAL results the model "
           "sent - a record went somewhere neither counter is watching"
           % (said("networks found"), said("duplicates folded"),
              card.escan_partials))

    # The stale reading must be GONE, not merely outvoted. -77 dBm was
    # the LAST thing the model said about network 0 and it is the value
    # a fold that overwrites rather than compares would leave behind.
    stale = min(r for _b, i, r in MODEL_BSS_REPEATS if i == 0)
    ck(not any(row["rssi"] == stale for row in rows),
       "a row shows %d dBm. That was the last repeat's reading and it is "
       "weaker than the first sighting, so a fold that keeps the newest "
       "value rather than the best one is what put it there" % stale)

    # -- the cross-checks that say the layout is right -------------------
    # ON THE BENCH THIS COUNTER IS EXPECTED TO BE NON-ZERO - it counts
    # 40 and 80 MHz access points, whose ctl_ch and chanspec channel
    # legitimately differ. HERE IT MUST BE ZERO, because the model
    # writes the same channel into both fields, so a mismatch under the
    # model can only mean a wrong bss_info offset. Same counter, two
    # readings, and the difference is that the model's networks are all
    # 20 MHz.
    ck(said("channel mismatch") == 0,
       "chanspec's low byte and ctl_ch disagreed. The model writes the same "
       "channel into both, so a mismatch means one of the two bss_info "
       "offsets in cyw43.pi4 is wrong")
    ck(said("sync id mismatch") == 0,
       "the sync_id the driver read back is not the one it sent")
    ck(said("bad headers") == 0, "the driver rejected a header the model "
                                 "built from the vendor's own field masks")
    ck(said("too big") == 0, "a frame was refused as oversize")
    ck(said("too short") == 0, "a frame was refused as too short")
    ck(said("bad event prefix") == 0,
       "an event frame was too short for its own 72-byte prefix - the most "
       "likely cause is the BDC data_offset not being honoured")
    # THIS ONE IS ZERO FOR A REASON THAT IS NOT A PASS. The board reports
    # exactly one payload-less credit frame per scan; the model has never
    # sent one and cannot be made to send one without teaching it a
    # transmit-window it does not have. Zero here says "the model did not
    # produce the case", not "the driver handles it" - the evidence for
    # that is the bench log and the transcript in cyw43_RxFrame.
    ck(said("empty events") == 0,
       "the driver saw %s payload-less event frames. The model never sends "
       "one, so any count here is the driver miscounting something else "
       "into cyw43_evEmpty" % said("empty events"))
    ck(said("table overflow") == 0, "the scan table overflowed")
    ck(said("credit stalls") == 0,
       "the driver stalled waiting for a credit. The model advertises four; "
       "a stall means credits are not being picked up out of the SDPCM "
       "header's window byte")

    print("model: %d control frames in, %d ioctls, %d escan requests, "
          "%d PARTIAL results sent for %d distinct networks, %.1f s"
          % (card.frames_in, len(card.ioctls), card.escan_started,
             card.escan_partials, len(MODEL_BSS), time.time() - t0))

    if fails:
        print("\na64_sdio_check --scan: FAIL - %d of %d checks failed"
              % (len(fails), checks[0]))
        for f in fails:
            print("   " + f)
        return 1
    print("\na64_sdio_check --scan: PASS - %d checks. The SDPCM framing, "
          "the cooked NVRAM, the CLM " % checks[0] +
          
          "chunking, the escan request and the bss_info layout all agree "
          "with the vendor headers, and every SSID the model sent came back "
          "spelled right.")
    print("   WHAT THIS PASS DOES NOT COVER, said plainly because this gate "
          "once passed a payload that faulted on silicon (2026-08-27):")
    print("   * the CLM's CONTENT. The model checks that the chunks "
          "reassemble to the file byte for byte and that BEGIN/END land on "
          "the right ones. Whether the firmware can PARSE the result is "
          "clmload_status's answer and only the board can give it.")
    print("   * the scan_ver verdict. The model refuses the iovar with -23 "
          "because this firmware family predates it; if silicon answers "
          "otherwise, silicon is right and the model is what changes.")
    print("   * the country default. The model answers \"00\" from "
          "cfg80211.c:8190. What this board actually holds is a bench fact "
          "and the payload prints it.")
    print("   * THE PAYLOAD-LESS EVENT FRAME. Real firmware sends one SDPCM "
          "frame per scan that is twelve bytes of header and no payload, "
          "carrying only a credit update; the driver counts it in "
          "\"empty events\" and drops it. THIS MODEL CANNOT SEND ONE - it "
          "has no transmit window to advertise out of band - so the zero "
          "in that row above is an absence of the case, not a pass on it. "
          "The evidence for that path is the bench log of 2026-08-27 and "
          "the byte-for-byte transcript in cyw43_RxFrame.")
    print("   * ASSOCIATION. NOTHING ABOUT THE JOIN IS TESTED HERE AND THE "
          "MODEL WAS DELIBERATELY NOT EXTENDED TO COVER IT. It serves the "
          "sup_wpa probe with a -23 copied off silicon and stops there: it "
          "does not implement WLC_SET_SSID, WLC_SET_WSEC_PMK, any bsscfg "
          "security iovar, or a single association event.")
    print("     THE REASON IS NOT EFFORT. AN OFFLINE MODEL CANNOT FAIL AN "
          "AUTHENTICATION. Every interesting thing the join met on the "
          "bench came from the OTHER END OF THE RADIO or from firmware "
          "internals no header describes - an access point answering "
          "ASSOC status 1 reason 43 AKMP_NOT_VALID because our key "
          "management suite is not one it accepts; a firmware refusing "
          "bsscfg:sup_wpa with -23 while accepting bsscfg:wsec with 0; "
          "WLC_SET_WSEC_PMK answering -2 at both documented struct sizes. "
          "A model would have to be TOLD each of those answers, and would "
          "then assert exactly what it was told. That is a transcript of "
          "an earlier bench session dressed as a test, and it would go green on "
          "the day the access point's configuration changed - which is "
          "precisely when it needs to go red.")
    print("     What a join model COULD honestly check is the SHAPE of what "
          "goes out: that the SSID struct is 36 bytes with a real length, "
          "that a bsscfg payload carries name + NUL + index + value, that "
          "the event mask enables every event the classifier decodes, that "
          "the PMK buffer is wiped after the ioctl. Those are claims about "
          "THIS code and they would be worth having. The verdict of an "
          "association is not one of them.")
    return 0


def probe_gate(k: dict, verbose: bool, compiler: str, work: pathlib.Path) -> int:
    hcbase = k["SOC_ARM_BASE"] + (k["MMCNR_BUS"] - k["SOC_BUS_BASE"])
    print("constants, pinned from the cited vendor sources:")
    print("   mmcnr@%08x, %d bytes  ->  ARM $%08X"
          % (k["MMCNR_BUS"], k["MMCNR_SIZE"], hcbase))
    print("   sdio pins %s  fsel %d  pulls %s"
          % (list(k["SDIO_PINS"]), k["SDIO_FSEL"], list(k["SDIO_PULLS"])))
    print("   CMD%d GO_IDLE  CMD%d SEND_RCA  CMD%d IO_OP_COND  CMD%d SELECT"
          % (k["MMC_GO_IDLE_STATE"], k["SD_SEND_RELATIVE_ADDR"],
             k["SD_IO_SEND_OP_COND"], k["MMC_SELECT_CARD"]))
    print("   CMD%d IO_RW_DIRECT  CMD%d IO_RW_EXTENDED"
          % (k["SD_IO_RW_DIRECT"], k["SD_IO_RW_EXTENDED"]))
    print("   arg: write $%08X  fn<<%d  addr<<%d  raw $%08X  incr $%08X"
          % (k["ARG_WRITE"], k["ARG_FN_SHIFT"], k["ARG_ADDR_SHIFT"],
             k["ARG_RAW"], k["ARG_INCR"]))
    print("   SI_ENUM_BASE $%08X  chipid +$%02X  eromptr +$%02X"
          % (k["SI_ENUM_BASE_DEFAULT"], k["CC_CHIPID"], k["CC_EROMPTR"]))
    print("   SBADDRLOW $%05X  2/4B flag $%05X  window mask $%08X"
          % (k["SBSDIO_FUNC1_SBADDRLOW"], k["SBSDIO_SB_ACCESS_2_4B_FLAG"],
             k["SBSDIO_SBWINDOW_MASK"]))
    print("   BRCM_CC_4345_CHIP_ID $%04X  43455 firmware revmask $%08X"
          % (k["BRCM_CC_4345_CHIP_ID"], k["FW_REVMASK"]))
    print("   mailbox clock id EMMC %d, EMMC2 %d  (they are NOT the same clock)"
          % (k["BCM2835_MBOX_CLOCK_ID_EMMC"], k["BCM2835_MBOX_CLOCK_ID_EMMC2"]))
    print("   expander gpio base %d  ->  WL_ON is firmware gpio %d"
          % (k["RPI_EXP_GPIO_BASE"], k["RPI_EXP_GPIO_BASE"] + 1))
    print()

    img = work / "sdiocheck.img"
    build(compiler, PROBE, img)

    parts: list = []
    cpu, board = run(img, k, parts)
    board, hc, card, fw = parts[0], parts[1], parts[2], parts[3]
    text = board.uart.decode("utf-8", "replace")
    print(text.rstrip())
    print()

    if verbose:
        print("-- register trace --")
        for line in hc.trace:
            print("   " + line)
        print()

    fails: list[str] = []

    checks = [0]

    def ck(cond: bool, msg: str) -> None:
        checks[0] += 1
        if not cond:
            fails.append(msg)

    def said(label: str, last: bool = False):
        # last=True picks the FINAL occurrence, for a label the log emits
        # more than once. The block-mode comparison and the RAM
        # write-back both print "mismatches (want 0)", and asserting on
        # the first one twice would leave the second unchecked.
        ms = list(re.finditer(re.escape(label) + r"\s+(-?\d+)", text))
        if not ms:
            return None
        return int((ms[-1] if last else ms[0]).group(1))

    def said_hex(label: str):
        m = re.search(re.escape(label) + r"\s+\$([0-9A-F]+)", text)
        return int(m.group(1), 16) if m else None

    # -- 1. the power rail came first ----------------------------------
    # REWRITTEN 2026-08-26 EVENING.  These checks used to demand that the
    # image DRIVE WL_ON high through the mailbox, and that demand is now
    # known to be unsatisfiable: this firmware refuses both expander
    # write tags while answering both read tags.  A gate that insists on
    # an impossible mechanism fails a correct library.
    #
    # What actually matters has never been the write.  It is that the
    # radio is KNOWN to be powered before the first SD command goes out.
    # Reading the pin high is exactly as good as driving it high, and on
    # this platform it is the only thing available.
    wl = k["RPI_EXP_GPIO_BASE"] + 1
    ck(fw.wl_on_known_high_at_command is not None,
       "WL_ON (firmware gpio %d) was never established as high - neither "
       "read high nor successfully driven high" % wl)
    ck(fw.wl_on_known_high_at_command == 0,
       "WL_ON was only established as high after %s SD commands had "
       "already been issued; a card that is not powered answers nothing "
       "and every failure below would be the same failure"
       % fw.wl_on_known_high_at_command)
    ck(fw.gpio_level.get(wl, 0) == 1,
       "WL_ON is not high at the end of the run; the radio was powered "
       "down and left that way")

    # THE SHORT CIRCUIT MUST ACTUALLY SHORT-CIRCUIT.  When the pin is
    # found already an output and already high there is nothing to do,
    # and the library must send NO write to it at all.  This is the
    # regression that cost the third bench run: the sequence asked the
    # firmware to set a pin that was already set, the firmware declined
    # the tag, and the library reported failure while standing on the
    # goal.
    if fw.wl_on_found_high and fw.gpio_dir.get(wl, 0) == 1:
        ck(fw.wl_on_writes == 0,
           "WL_ON was found already high and already an output, and the "
           "library wrote to it %d time(s) anyway.  On this firmware "
           "those writes are refused and the refusal was being reported "
           "as a failure to power the radio." % fw.wl_on_writes)

    # If a write IS attempted - on a board where the pin is not already
    # right - the direction in a SET_GPIO_CONFIG still has to be
    # RPI_EXP_GPIO_DIR_OUT, which is 1.  Writing 0 there is DIR_IN: the
    # firmware would accept the transaction and the state word in the
    # same message would have nothing to drive.
    dir_out = 1
    cfgs = [(g, d, st) for (g, d, st) in fw.gpio_set if g == wl]
    ck(all(d == dir_out for (g, d, st) in cfgs),
       "WL_ON was configured with direction 0, which is "
       "RPI_EXP_GPIO_DIR_IN - the pin is an input and the state word is "
       "ignored")

    # And it must never be driven LOW unless it was found high, because
    # a low that is not followed by a successful high leaves the radio
    # switched off by the procedure that exists to switch it on.
    lows = [st for (g, d, st) in fw.gpio_set if g == wl and st == 0]
    ck(not lows or fw.wl_on_found_high,
       "WL_ON was driven LOW on a board where it was found LOW; the "
       "power cycle is only safe when there was something to cycle")

    # The get-config payload is FIVE words, not six.  struct
    # gpio_get_config has no trailing state field; only
    # struct gpio_set_config does.  See the expander driver, lines 32-47.
    ck(fw.get_cfg_words is None or fw.get_cfg_words == 5,
       "GET_GPIO_CONFIG was sent with a %s-word payload; struct "
       "gpio_get_config is five words and the firmware is handed one "
       "size for both the request and the reply" % fw.get_cfg_words)

    # -- 2. the base clock came from the right clock -------------------
    ck(k["BCM2835_MBOX_CLOCK_ID_EMMC"] in fw.clock_asked,
       "the probe never asked the mailbox for the EMMC clock")
    ck(k["BCM2835_MBOX_CLOCK_ID_EMMC2"] not in fw.clock_asked,
       "the probe asked for the EMMC2 clock (id %d). That is the micro-SD "
       "controller's clock, not this one's."
       % k["BCM2835_MBOX_CLOCK_ID_EMMC2"])
    ck(said("EMMC clock Hz (id 1)") == fw.emmc_hz,
       "the probe reported an EMMC clock the firmware did not give it")
    ck(said("base clock kHz") == fw.emmc_hz // 1000,
       "the base clock handed to sdio.pi4 is not the mailbox's answer in kHz")

    # -- 3. the pins ----------------------------------------------------
    # Every one of the six named pins is in GPFSEL3 (pins 30..39) and the
    # fields are three bits at (pin - 30) * 3.
    for pin, want_pull in zip(k["SDIO_PINS"], k["SDIO_PULLS"]):
        ck(30 <= pin <= 39,
           "sdio_pins names GPIO %d, which is not in GPFSEL3" % pin)
        sh = (pin - 30) * 3
        got = (board.gpfsel3 >> sh) & 7
        ck(got == k["SDIO_FSEL"],
           "GPIO %d is function %d, the device tree says %d"
           % (pin, got, k["SDIO_FSEL"]))
        psh = (pin - 32) * 2
        gotp = (board.gppup2 >> psh) & 3
        # TRANSLATED, NOT COMPARED RAW.  The device tree numbers pull-up
        # 2 and the BCM2711 register numbers 2 pull-down; see
        # PULL_DT_TO_REG above for why this line is not a simple
        # equality any more.
        want_reg = k["PULL_DT_TO_REG"][want_pull]
        ck(gotp == want_reg,
           "GPIO %d pull field is %d; the device tree asks for %d "
           "(brcm,pull numbering) which is %d in the BCM2711's "
           "GPIO_PUP_PDN_CNTRL numbering"
           % (pin, gotp, want_pull, want_reg))
    # Nothing outside the six may move.  GPFSEL3 also holds 30..33 and
    # GPPUP2 holds 32..47; a whole-register write would clobber them.
    keep_fsel = 0
    for pin in range(30, 40):
        if pin not in k["SDIO_PINS"]:
            keep_fsel |= 7 << ((pin - 30) * 3)
    ck((board.gpfsel3 & keep_fsel) == (board.gpfsel3_before & keep_fsel),
       "the pin mux disturbed a GPFSEL3 field outside sdio_pins - a "
       "whole-register write instead of a read-modify-write")
    keep_pull = 0
    for pin in range(32, 48):
        if pin not in k["SDIO_PINS"]:
            keep_pull |= 3 << ((pin - 32) * 2)
    ck((board.gppup2 & keep_pull) == (board.gppup2_before & keep_pull),
       "the pin mux disturbed a pull outside sdio_pins")

    # -- 4. the commands issued -----------------------------------------
    legal = {k["MMC_GO_IDLE_STATE"], k["SD_SEND_RELATIVE_ADDR"],
             k["SD_IO_SEND_OP_COND"], k["MMC_SELECT_CARD"],
             k["SD_IO_RW_DIRECT"], k["SD_IO_RW_EXTENDED"]}
    for (idx, flags, arg) in hc.commands:
        ck(idx in legal, "CMD%d is not one of the cited opcodes" % idx)

    def flags_for(index: int) -> set[int]:
        return {f for (i, f, a) in hc.commands if i == index}

    # CMD5 answers R4, which has NO CRC and NO index.  Enabling either
    # makes a real controller reject a perfectly good response, and the
    # symptom is a CMD5 that "times out" against a card that answered.
    for f in flags_for(k["SD_IO_SEND_OP_COND"]):
        ck((f & k["SDHCI_CMD_CRC"]) == 0,
           "CMD5 was issued with CRC checking on; R4 carries no CRC")
        ck((f & k["SDHCI_CMD_INDEX"]) == 0,
           "CMD5 was issued with index checking on; R4 carries no index")
        ck((f & k["SDHCI_CMD_RESP_MASK"]) == k["SDHCI_CMD_RESP_SHORT"],
           "CMD5 must ask for a 48-bit response")
    # CMD0 has no response at all.
    for f in flags_for(k["MMC_GO_IDLE_STATE"]):
        ck((f & k["SDHCI_CMD_RESP_MASK"]) == k["SDHCI_CMD_RESP_NONE"],
           "CMD0 was issued expecting a response; it has none")
    # CMD3 (R6) and CMD52/53 (R5) all carry a CRC and an index.
    for idx, name in ((k["SD_SEND_RELATIVE_ADDR"], "CMD3"),
                      (k["SD_IO_RW_DIRECT"], "CMD52"),
                      (k["SD_IO_RW_EXTENDED"], "CMD53")):
        for f in flags_for(idx):
            ck((f & k["SDHCI_CMD_CRC"]) != 0,
               "%s was issued without CRC checking" % name)
            ck((f & k["SDHCI_CMD_INDEX"]) != 0,
               "%s was issued without index checking" % name)
    for f in flags_for(k["SD_IO_RW_EXTENDED"]):
        ck((f & k["SDHCI_CMD_DATA"]) != 0,
           "CMD53 was issued without Data Present Select; the controller "
           "would never move a byte")
    # CMD7 selects with an R1b, and the busy period is on DAT0.
    for f in flags_for(k["MMC_SELECT_CARD"]):
        ck((f & k["SDHCI_CMD_RESP_MASK"]) in
           (k["SDHCI_CMD_RESP_SHORT"], k["SDHCI_CMD_RESP_SHORT_BUSY"]),
           "CMD7 must ask for a 48-bit response")
        ck((f & k["SDHCI_CMD_CRC"]) != 0, "CMD7 without CRC checking")

    # The ordering of the identification sequence.
    order = [i for (i, f, a) in hc.commands
             if i in (k["MMC_GO_IDLE_STATE"], k["SD_IO_SEND_OP_COND"],
                      k["SD_SEND_RELATIVE_ADDR"], k["MMC_SELECT_CARD"])]
    want = [k["MMC_GO_IDLE_STATE"], k["SD_IO_SEND_OP_COND"]]
    ck(order[:2] == want,
       "the identification sequence starts %s, not CMD0 then CMD5" % order[:2])
    ck(order.index(k["SD_SEND_RELATIVE_ADDR"]) <
       order.index(k["MMC_SELECT_CARD"]),
       "CMD7 was issued before CMD3 published an RCA")
    ck(card.opcond_polls >= 2,
       "the CMD5 busy loop only ran once; it must poll until the card "
       "reports ready")

    # -- 5. what the probe reported about the bus -----------------------
    ck(said("SdioInit (want 1)") == 1, "SdioInit failed")
    ck(said("io functions     ") == MODEL_NFUNC,
       "the probe read %s I/O functions out of R4, the card said %d"
       % (said("io functions     "), MODEL_NFUNC))
    ck(said("memory present   ") == 0,
       "the probe decoded a memory-present bit the card did not set")
    ck(said_hex("io ocr           ") == MODEL_OCR,
       "the OCR the probe reported is not the one the card published")
    ck(said_hex("rca              ") == MODEL_RCA,
       "the RCA the probe reported is not the one CMD3 returned")
    ck(said("bus width        ") == 4,
       "the bus never went to four bits")
    ck((card.cccr_if & k["SDIO_BUS_WIDTH_MASK"]) == k["SDIO_BUS_WIDTH_4BIT"],
       "CCCR bus interface control does not say four-bit")
    ck((card.cccr_if & k["SDIO_BUS_CD_DISABLE"]) != 0,
       "the DAT3 card-detect pull-up was left on with four data lines "
       "driving it")
    ck(said("bus clock kHz    ") is not None
       and said("bus clock kHz    ") <= 25000,
       "the bus is faster than Default Speed and nothing enabled high speed")

    # -- 6. the SDIO functions ------------------------------------------
    ck(said("enable F1 (want 1)") == 1, "function 1 never enabled")
    ck(said("enable F2 (want 1)") == 1, "function 2 never enabled")
    ck((card.ioe & k["SDIO_FUNC_ENABLE_1"]) != 0,
       "CCCR IOEx does not have function 1 enabled")
    ck((card.ioe & k["SDIO_FUNC_ENABLE_2"]) != 0,
       "CCCR IOEx does not have function 2 enabled - enabling F2 must be a "
       "read-modify-write, not a slam that turns F1 off")
    f1 = card.fbr.get(1 * k["SDIO_FBR_STEP"] + k["SDIO_FBR_BLKSIZE"])
    f2 = card.fbr.get(2 * k["SDIO_FBR_STEP"] + k["SDIO_FBR_BLKSIZE"])
    ck(f1 == (k["SDIO_FUNC1_BLOCKSIZE"] & 0xFF),
       "the F1 block size low byte is %s, bcmsdh.c says %d"
       % (f1, k["SDIO_FUNC1_BLOCKSIZE"]))
    ck(f2 == (k["SDIO_FUNC2_BLOCKSIZE"] & 0xFF),
       "the F2 block size low byte is %s, bcmsdh.c says %d"
       % (f2, k["SDIO_FUNC2_BLOCKSIZE"]))

    # -- 7. the clock sequence ------------------------------------------
    ck(card.alp_forced,
       "the ALP clock was requested but never FORCED; brcmf_sdio_buscoreprep "
       "writes SBSDIO_FORCE_ALP after the wait")
    ck(card.pullup_cleared,
       "SBSDIO_FUNC1_SDIOPULLUP was never cleared")
    csr = said_hex("chipclkcsr       ")
    ck(csr is not None and (csr & k["SBSDIO_ALP_AVAIL"]) != 0,
       "the probe reported a CHIPCLKCSR with no ALP available")

    # -- 8. the backplane window ----------------------------------------
    ck(len(card.window_writes) >= 3,
       "the backplane window was never programmed")
    ck(len(card.window_writes) % 3 == 0,
       "the window was programmed in %d byte writes; it takes three at a "
       "time" % len(card.window_writes))
    lo = k["SBSDIO_FUNC1_SBADDRLOW"]
    for i in range(0, len(card.window_writes), 3):
        trio = card.window_writes[i:i + 3]
        ck([a for (a, d) in trio] == [lo, lo + 1, lo + 2],
           "a window update wrote %s, not SBADDRLOW/MID/HIGH in order"
           % [hex(a) for (a, d) in trio])
    ck(card.access_flag_seen > 0 and card.access_flag_missing == 0,
       "%d backplane accesses went out WITHOUT SBSDIO_SB_ACCESS_2_4B_FLAG; "
       "those are not 32-bit backplane reads" % card.access_flag_missing)
    ck((k["SI_ENUM_BASE_DEFAULT"] + k["CC_CHIPID"]) in card.bp_reads,
       "the chip ID was never read from SI_ENUM_BASE + offsetof(chipid)")
    ck((k["SI_ENUM_BASE_DEFAULT"] + k["CC_EROMPTR"]) in card.bp_reads,
       "the EROM pointer was never read from SI_ENUM_BASE + offsetof(eromptr)")

    # -- 9. the chip ----------------------------------------------------
    ck(said("Cyw43Attach (want 1)") == 1, "Cyw43Attach failed")
    ck(said_hex("chipid raw       ") == card.chipid,
       "the probe reported chip id $%s, the card holds $%08X"
       % (said_hex("chipid raw       "), card.chipid))
    ck(said_hex("chip id          ") == MODEL_CHIP_ID,
       "the CID_ID field was decoded wrong")
    ck(said("chip rev         ") == MODEL_CHIP_REV,
       "the CID_REV field was decoded wrong")
    ck(said("chip package     ") == MODEL_CHIP_PKG,
       "the CID_PKG field was decoded wrong")
    ck(said("backplane type   ") == k["SOCI_AI"],
       "the CID_TYPE field was decoded wrong")
    ck(said("chipid corecount ") == MODEL_CHIP_CCOUNT,
       "the CID_CC field was decoded wrong")
    # The 43455 rule: chip $4345 with a revision inside the mask.
    want455 = 1 if (MODEL_CHIP_ID == k["BRCM_CC_4345_CHIP_ID"]
                    and (k["FW_REVMASK"] >> MODEL_CHIP_REV) & 1) else 0
    ck(said("is CYW43455      ") == want455,
       "Cyw43IsCyw43455 said %s; sdio.c's revision mask $%08X says %d for "
       "revision %d" % (said("is CYW43455      "), k["FW_REVMASK"],
                        want455, MODEL_CHIP_REV))

    # -- 10. the core walk ----------------------------------------------
    ck(said("cores found      ") == len(card.cores),
       "the walk found %s cores, the modelled EROM encodes %d"
       % (said("cores found      "), len(card.cores)))
    for n, (cid, rev, cbase, cwrap) in enumerate(card.cores):
        m = re.search(r"core %d id \$([0-9A-F]+) rev (\d+) base \$([0-9A-F]+) "
                      r"wrap \$([0-9A-F]+)" % n, text)
        if not m:
            fails.append("core %d is missing from the log" % n)
            continue
        ck(int(m.group(1), 16) == cid,
           "core %d id is $%s, the EROM says $%03X" % (n, m.group(1), cid))
        ck(int(m.group(2)) == rev,
           "core %d rev is %s, the EROM says %d" % (n, m.group(2), rev))
        ck(int(m.group(3), 16) == cbase,
           "core %d base is $%s, the EROM says $%08X"
           % (n, m.group(3), cbase))
        ck(int(m.group(4), 16) == cwrap,
           "core %d wrapper is $%s, the EROM says $%08X"
           % (n, m.group(4), cwrap))

    # A 16K region is not a core's register space (chip.c lines 886-889),
    # and the awkward core exists so that a walker which ignores the size
    # class reports one here instead of the 4K slave that follows it.
    ck("$%08X" % AWKWARD_REGION not in text,
       "a core was given the 16K skip region $%08X as its base; only 4K and "
       "8K regions are register spaces" % AWKWARD_REGION)

    # -- 11. BLOCK-MODE CMD53, and it is the point of the 2026-08-26 work
    #
    # The image reads one region of the chip twice in byte mode and once
    # in block mode and prints the three comparisons.  What is asserted
    # here is not "it printed 0" but the whole shape of the experiment:
    # the control must be clean BEFORE the result means anything, and a
    # control that was skipped is not a control.
    # said() returns None when the row is not a number, and probe_Count
    # prints "NOT COMPARED" rather than 0 when the reads it needed did
    # not both succeed. So None here means the control never ran, which
    # is a FAIL and used to be an invisible pass - on 2026-08-26 this
    # row printed 0 with nothing compared behind it.
    ck(said("control mismatches (want 0)") == 0,
       "the control did not run, or the two byte-mode reads of the same "
       "region disagreed. Either way the block-mode comparison below "
       "proves nothing")
    ck(said("byte-mode read (want 1)") == 1,
       "the byte-mode bulk read failed - nothing about block mode can be "
       "concluded from this run")
    ck(said("block mode on (want 1)") == 1,
       "block mode would not turn on; Cyw43SetBlockIo or the F1 block size "
       "was refused")
    ck(said("block-mode read (want 1)") == 1,
       "the block-mode bulk read failed outright")
    # TWO DIFFERENT FAILURES, TWO DIFFERENT MESSAGES. None means the
    # comparison never ran (probe_Count printed NOT COMPARED); a
    # non-zero count means it ran and the two modes disagreed. Reporting
    # the second when it was the first is how a reader gets sent to the
    # wrong file, which is what happened on 2026-08-26.
    ck(said("mismatches (want 0)") is not None,
       "the block-versus-byte comparison never ran - one of the reads it "
       "needed failed, so look at those rows and not at block mode")
    if said("mismatches (want 0)") is not None:
        ck(said("mismatches (want 0)") == 0,
           "block mode and byte mode read DIFFERENT BYTES from the same "
           "address. The transfer completed and moved the wrong data, which "
           "is the exact failure a firmware upload would not survive and "
           "would not report")
    ck(said("bytes compared") is not None and said("bytes compared") >= 256,
       "fewer than 256 bytes were compared - that is under four of function "
       "1's 64-byte blocks, and a comparison that short does not exercise "
       "the per-block loop this change added")

    # -- the byte-mode ceiling, which the board taught this gate --------
    # NO CMD53 ANYWHERE IN THE RUN MAY EXCEED THE FUNCTION'S CEILING.
    # The model refuses one with an R5 now, so a violation shows up as a
    # failed transfer too - but this asserts on the trace directly, so
    # the log names the real fault instead of a downstream symptom.
    refused = [t for t in hc.trace if "REFUSED" in t]
    ck(not refused,
       "the card refused a command: %s. A byte-mode CMD53 may not exceed "
       "min(host max_blk_size, the function's block size, 512) - "
       "sdio_max_byte_size(), sdio_io.c lines 189-202"
       % (refused[0] if refused else ""))
    ck(said("byte-mode max") == k["SDIO_FUNC1_BLOCKSIZE"],
       "the library thinks function 1's byte-mode ceiling is %s; the card's "
       "block size is %d and the ceiling is the smaller of that, the host's "
       "512 and the protocol's 512"
       % (said("byte-mode max"), k["SDIO_FUNC1_BLOCKSIZE"]))
    ck(said("card can multi-block (want 1)") == 1,
       "the library did not read CCCR CAPS bit SMB back, or read it wrong - "
       "Linux gates its entire block-mode branch on that bit")

    # The trace must actually CONTAIN a multi-block command. Without this
    # the five assertions above would all pass on a build that quietly
    # fell back to byte mode.
    multi = [t for t in hc.trace if "BLOCK x" in t]
    ck(len(multi) > 0,
       "no CMD53 in the whole run was issued in block mode, so every "
       "assertion about block mode above passed vacuously")
    ck(any(int(t.split("BLOCK x")[1]) > 1 for t in multi),
       "block mode was used but never with more than one block, so "
       "SDHCI_TRNS_MULTI and the per-block buffer-ready re-arm were "
       "never exercised")

    # -- 11b. the RAM walk -----------------------------------------------
    # The base is a table lookup and the size is walked out of the CR4's
    # banks, so they are checked in two different ways: the base against
    # chip.c's table, the size against the model's own banks.
    ck(said("Cyw43PrepareDownload (want 1)") == 1,
       "the cores would not go down, so nothing above this line can be "
       "uploaded to")
    ck(said("CR4 is up (want 1)") == 1,
       "the ARM CR4 did not read back as out of reset with its clock on")
    ck(said_hex("ram base (want $198000)") == MODEL_RAMBASE,
       "the RAM base is not $%08X, which is chip.c line 713's entry for a "
       "$4345 and the only value that is not a guess" % MODEL_RAMBASE)
    ck(said("ram size bytes") == MODEL_RAMSIZE,
       "the RAM size is not %d, which is what this model's ARMCR4 bank "
       "registers add up to" % MODEL_RAMSIZE)
    want_idx = list(range(MODEL_CR4_NAB + MODEL_CR4_NBB))
    ck(card.bankidx_writes == want_idx,
       "ARMCR4_BANKIDX was written as %r, not %r - a driver that does not "
       "select every bank in turn gets the right total from a model whose "
       "banks are all the same size and the wrong one from a chip whose "
       "banks are not" % (card.bankidx_writes, want_idx))

    # -- 11c. the RAM write, which is the first bulk WRITE ever made -----
    ck(said("Cyw43WriteMem (want 1)") == 1,
       "the bulk write to chip RAM failed")
    ck(said("ram mismatches (want 0)") == 0,
       "chip RAM did not read back what was written to it, or the verify "
       "pass never ran")

    # -- 11d. what is STILL refused, and for the right reason ------------
    ck(said("firmware required (want 1)") == 1,
       "Cyw43FirmwareRequired must say 1 - there is no configuration that "
       "makes this part run without a downloaded image")
    ck(said("Cyw43Start with nothing loaded (want 0)") == 0,
       "Cyw43Start released the ARM with no verified image and no verified "
       "NVRAM in the chip, which runs whatever was in that RAM")
    # THE REFUSAL LIST IS EMPTY AND THIS BLOCK IS DOWN TO ONE CHECK.
    # Cyw43ScanStart came off it on the morning of 2026-08-27 when the
    # SDPCM transport made it real, and Cyw43Join came off it the same
    # evening when the association path landed and the board joined a
    # real access point. Calling either in the probe would now ATTEMPT
    # the operation on a radio with no firmware in it rather than print
    # a refusal, which is a worse test than none.
    #
    # Cyw43Start above is the survivor, and it is the right one: it is
    # the only call that must still refuse without an image, and its
    # guard is the one whose failure releases the radio's ARM into
    # empty RAM.
    ck("brcmfmac%d-sdio.bin" % k["FW_BASENAME"] in text,
       "the log does not name brcmfmac%d-sdio.bin, which is the file "
       "sdio.c line 652 says this chip needs" % k["FW_BASENAME"])

    # THE OLD ASSERTION HERE WANTED THE WORD "REFUSED" AND A LICENCE
    # ARGUMENT, and it is gone deliberately rather than by neglect. Until
    # 2026-08-26 cyw43.pi4 refused every firmware operation on the
    # grounds that the image was not on the disk and that redistributing
    # it was an open decision. The image is now in the repository at
    # Firmware/CYW43455/ with the licence text in licenses/, and upload
    # and start are implemented. What is
    # still refused is Cyw43Start without an image, and the gate checks
    # that it refuses for the RIGHT reason instead of checking that it
    # refuses at all.
    #
    # THE "SDPCM" ASSERTION THAT LIVED HERE IS GONE, 2026-08-27 evening,
    # and its removal is the interesting half. It required the refusal
    # text to blame the missing transport - which was true that morning
    # and became false the same day, twice over. An assertion that
    # demands a specific EXCUSE ages badly; the one below demands that
    # the message name the thing the caller must actually do, which does
    # not.
    ck("verified image" in text,
       "Cyw43Start's refusal no longer says WHAT is missing. A caller "
       "told only 'refused' has nowhere to go; told that it needs a "
       "verified image and a verified NVRAM, they have.")

    # -- 12. nothing touched the SD card's controller --------------------
    # Enforced by construction: any MMIO outside the modelled windows
    # raises. This records that the constraint was in force.
    print("model: %d SD commands, %d CMD52/53 traced, %d backplane reads, "
          "%d GPIO writes, %d steps"
          % (len(hc.commands), len(hc.trace), len(card.bp_reads),
             board.gpio_writes, board.steps))
    print("       the only MMIO windows opened were $%08X..$%08X (mmcnr), the "
          "PL011, the mailbox and two GPIO registers."
          % (hcbase, hcbase + k["MMCNR_SIZE"] - 1))
    print("       sdhost at $FE202000 and emmc2 at $FE340000 were never "
          "addressed; a store to either would have stopped this run.")

    if fails:
        print("\na64_sdio_check: FAIL - %d of %d checks failed"
              % (len(fails), checks[0]))
        for f in fails:
            print("   " + f)
        return 1
    print("\na64_sdio_check: PASS - %d checks. sdio.pi4 and cyw43.pi4 "
          "agree with the " % checks[0] +
          
          "vendor sources; block-mode CMD53 reads the same bytes as byte "
          "mode; the RAM walk and the first bulk write hold up.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetal compiler (default: PMF_COMPILER)")
    ap.add_argument("--verbose", action="store_true",
                    help="print the CMD52/CMD53 trace")
    ap.add_argument("--scan", action="store_true",
                    help="run pi4WifiScan.pi4 against the SDPCM model "
                         "instead of the probe. SLOW - it CRCs and uploads "
                         "the real 609 KB image.")
    ap.add_argument("--nvram", default=None,
                    help="with --scan, a board NVRAM text file to upload "
                         "instead of the synthetic one")
    args = ap.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        print("a64_sdio_check needs the PureMetal compiler: pass --compiler "
              "or set PMF_COMPILER.", file=sys.stderr)
        return 2
    if not pathlib.Path(args.compiler).is_file():
        print("The compiler named by --compiler or PMF_COMPILER does not "
              "exist: %s" % args.compiler, file=sys.stderr)
        return 2
    if args.nvram and not args.scan:
        print("--nvram only applies to --scan; the probe uploads no NVRAM.",
              file=sys.stderr)
        return 2

    k = read_constants()
    with tempfile.TemporaryDirectory(prefix="a64-sdio-") as tmp:
        work = pathlib.Path(tmp)
        if args.scan:
            return scan_gate(k, args.verbose, args.compiler, work, args.nvram)
        return probe_gate(k, args.verbose, args.compiler, work)


if __name__ == "__main__":
    sys.exit(main())
