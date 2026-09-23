#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/genet.pi4 - the BCM2711 GENET v5.

There is no Pi 4 here, no cable, and no switch.  All three are
fabricated: a PL011 that swallows characters, a GENETv5 register block
with 256 RX and 256 TX descriptors in MMIO, a BCM54213PE-shaped clause-22
PHY at MDIO address 1 that has negotiated 1000BASE-T full duplex, and a
network that sends us exactly one frame.

NOTHING HERE IS TRANSCRIBED FROM genet.pi4.

  * every register offset, bit and composite value the model uses comes
    from the #define bodies of Das U-Boot v2025.01
    drivers/net/bcmgenet.c - the macro definitions themselves, with their
    arithmetic resolved here, so TDMA_RING_REG_BASE is computed from
    GENET_TX_OFF, TOTAL_DESCS, DMA_DESC_SIZE, DEFAULT_Q and DMA_RING_SIZE
    exactly as the driver computes it.  The driver is third-party source
    and is not copied into this tree: each needed #define is pinned in
    UBOOT_BCMGENET with its body and its line.  If the library and the
    driver disagree about where a register lives, the model raises
    "unmodelled MMIO" and this goes red rather than agreeing with the
    library by construction.
  * the block's base address is derived from the ethernet@7d580000 node
    of the Raspberry Pi device tree (raspberrypi/linux rpi-6.12.y,
    bcm2711.dtsi), translated through the soc node's own ranges - pinned,
    and not typed in as $FD580000.
  * the PHY's MDIO address comes from bcm2711-rpi-4-b.dts (pinned).
  * the clause-22 register numbers and bits the model's PHY implements
    come from Linux v6.12 include/uapi/linux/mii.h (pinned).
  * UMAC_MODE, the one register in the library with a single source,
    comes from Linux v6.12 drivers/net/ethernet/broadcom/unimac.h (pinned)
    and is modelled READ-ONLY: a write to it fails the gate, because a
    library must not steer on a register only one header has ever heard of.
  * the expected values in the refusal section are parsed out of the
    PROBE'S OWN PRINTED LABELS - "(want -13)" - so the probe declares
    what it expects and the gate only enforces the agreement.

WHAT IS ASSERTED, beyond "it ran"

  * SYS_REV_CTRL's major nibble is read and compared against SIX, which
    is what GENETv5 reports.  A library looking for five is rejected.
  * THE UMAC RESET SEQUENCE IS COMPARED AS AN ORDERED TRACE against the
    sequence bcmgenet_umac_reset() performs - including that the soft
    reset carries CMD_LCL_LOOP_EN, which is the bit most likely to be
    "cleaned up" by somebody who reads it as a test mode.
  * EVERY MDIO TRANSACTION IS TWO WRITES: the command word, then a
    separate read-modify-write that sets START_BUSY.  One combined
    write fails.
  * RBUF_CTRL and EXT_RGMII_OOB_CTRL are preloaded with foreign bits and
    those bits must survive.  A blind write fails.  EXT_RGMII_OOB_CTRL's
    preload is no longer invented: it is $00F00000, MEASURED off the
    board before any Anvil code had touched the block.
    Bits 20-23 are set by the hardware and named by NEITHER source, so
    they are exactly what a read-modify-write is for.  The old preload
    guessed OOB_DISABLE was set at reset; it is clear.
  * THE PORT MODE IS NOT INHERITED.  SYS_PORT_CTRL is preloaded with the
    measured reset value of zero, so a library that never writes
    PORT_MODE_EXT_GPHY fails rather than coasting on a lucky default.
  * THE SPEED FIELD MUST SURVIVE THE ENABLE.  UMAC_CMD ends holding
    (UMAC_SPEED_1000 << CMD_SPEED_SHIFT) | CMD_TX_EN | CMD_RX_EN.  A
    blind write of the two enables at the end - which is the obvious
    way to write that line - leaves a gigabit link running at the
    10 Mbit/s encoding, and that combination passes traffic badly
    instead of failing.
  * ALL 256 RX DESCRIPTORS are initialised, each pointing at
    base + i * RX_BUF_LENGTH, with the HIGH half written too, and with
    DMA_OWN set.
  * THE RING INDICES ARE ADOPTED, NOT ASSUMED.  The model starts
    RDMA_PROD_INDEX at 7 and TDMA_CONS_INDEX at 5 - neither zero - and
    the library must pick its cursors up from them.  A library that
    assumed zero transmits into the wrong descriptor and receives
    nothing, and both show up here.
  * THE TX DESCRIPTOR IS WRITTEN ADDRESS-FIRST, LENGTH-STATUS-LAST, and
    TDMA_PROD_INDEX is written after all three.  The order is checked as
    a sequence, not as a set.
  * THE FRAME THAT LEFT is decoded here from the bytes the model read
    out of memory at the address the descriptor gave: broadcast
    destination, the source address the probe set, and its EtherType.
  * ONE FRAME IS INJECTED and must come back with the two RBUF_ALIGN_2B
    pad bytes stripped and RDMA_CONS_INDEX advanced by exactly one.
  * THE NETWORK DOES NOT ANSWER ON THE FIRST POLL.  The injection is
    withheld until the library has read RDMA_PROD_INDEX
    RX_ANSWER_AFTER_POLLS times, so a receive stage bounded by a poll
    count instead of by a clock fails.  This was added on 2026-08-26
    after the eight-iteration loop that shipped to silicon produced a
    false "receive is broken" report; the model used to answer
    instantly and the gate was green throughout.
  * THE MAC'S OWN LINK BIT IS DERIVED, NOT PRELOADED.  UMAC_MODE's
    MODE_LINK_STATUS is computed from EXT_RGMII_OOB_CTRL exactly as the
    silicon computes it - set only once OOB_DISABLE is clear and
    RGMII_LINK is set - so the probe must read 0 before bring-up and 1
    after.  It used to be a constant 1, which made the bit useless as
    evidence and hid both the ordering and the RGMII_LINK write itself.
  * THE PROBE READS SIX REGISTERS BACK OFF THE BUS after bring-up -
    EXT_RGMII_OOB_CTRL, UMAC_CMD, both DMA_CTRLs, the RX indices and the
    discard count - and those PRINTED values are graded too.  Everything
    else here grades what the library WROTE; this grades what a human
    staring at the serial log would actually see.
  * NOT ONE WRITE LANDS ON SYS_TBUF_FLUSH_CTRL OR UMAC_MODE.  The cited
    driver never writes either; the first is the TX-side twin of a
    register the reset sequence does use, and the second is the
    single-source one.

Run:  python tools/a64/a64_genet_check.py --compiler <PureMetalForge.exe>
      python tools/a64/a64_genet_check.py --compiler <PureMetalForge.exe> --mutate

--mutate rebuilds a COPY of the library once per entry in MUTATIONS, each
with a deliberate defect in it, and requires the gate to go RED each time.  A gate nobody has ever
seen fail is a gate nobody has any reason to believe.
"""

from __future__ import annotations
import os

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from a64_interp import A64, attach_symbols  # noqa: E402
import sys as _pmfsys
import pathlib as _pmfpath
_pmfsys.path.insert(0, str(_pmfpath.Path(__file__).resolve().parents[1]))
from pmf_compiler import resolve_compiler  # noqa: E402

LIB = ROOT / "RaspberryPi4" / "Lib" / "genet.pi4"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4GenetProbe.pi4"
COMPILER: str = ""

DRIVER_NAME = "U-Boot v2025.01 drivers/net/bcmgenet.c"

LOAD = 0x00400000
STACK = 0x03000000
LOADER_SP = 0x00100000
LOADER_LR = 0xDEADBEE0
CNTFRQ = 54_000_000
STEPS_PER_TICK = 8
STEP_LIMIT = 60_000_000

UART_LO = 0xFE201000
UART_HI = 0xFE201048
UART_DR = 0xFE201000
UART_FR = 0xFE201018

# What the model's imaginary network sends us, and what the probe should
# have sent.  Both are decoded from raw bytes below, not compared against
# anything the library exports.
INJECT_ETHERTYPE = 0x0806          # ARP - the thing that actually turns
                                   # up unbidden on a real switch port
INJECT_PAYLOAD_LEN = 60

# HOW MANY TIMES THE RECEIVER MUST LOOK BEFORE THE NETWORK ANSWERS.
#
# This model used to inject its frame on the FIRST read of
# RDMA_PROD_INDEX after a transmission, and that kindness hid a real
# defect for as long as this gate has existed.  The probe's receive
# stage polled eight times in a bare loop with no delay - microseconds
# of listening - and the model answered instantly, so the gate went
# green.  On silicon on 2026-08-26 the same code reported "polls used
# 8, bytes 0" against a live switch and it was read as a broken receive
# path.  It was a broken diagnostic.
#
# A REAL NETWORK DOES NOT ANSWER ON THE FIRST POLL, so the model no
# longer does either.  Forty is not a measurement of anything; it is
# comfortably more than any fixed poll count a person would write by
# hand and trivially small for a caller holding a real deadline.  Its
# whole job is to make "I looked N times" fail and "I listened for N
# milliseconds" pass.
RX_ANSWER_AFTER_POLLS = 40


# =====================================================================
#  THE VENDOR SOURCE, RESOLVED
# =====================================================================
# The driver writes almost every offset as arithmetic over other macros.
# Regexing out the literals would therefore miss the interesting half -
# TDMA_RING_REG_BASE, DMA_FC_THRESH_VALUE, ENET_MAX_MTU_SIZE - and those
# are exactly the ones a human retyping them gets wrong.  So the macros
# are resolved symbolically instead.
#
# The four names the driver takes from Linux headers it includes rather
# than defines are supplied here.  They are Ethernet frame-format
# constants, not Broadcom's, and the driver states the same arithmetic
# in words in its own comment at v2025.01_bcmgenet.c:102-104, which is
# the second witness for them.
EXTERNS = {
    "ETH_DATA_LEN": 1500,
    "ETH_HLEN": 14,
    "ETH_FCS_LEN": 4,
    "VLAN_HLEN": 4,
}


# =====================================================================
#  THE PINNED VENDOR DEFINITIONS (cited, not copied)
# =====================================================================
# Each table is  NAME: (#define body, line)  for exactly the macros this
# gate resolves, and the macros those bodies name.  Bodies are kept as
# the vendor wrote them so the arithmetic is still resolved here.

# Das U-Boot v2025.01 (revision 6d41f0a39d6423c8e57e92ebbe9f8c0333a63f72),
# drivers/net/bcmgenet.c.
UBOOT_BCMGENET = {
    'SYS_REV_CTRL': ('0x00', 40),
    'SYS_PORT_CTRL': ('0x04', 42),
    'PORT_MODE_EXT_GPHY': ('3', 43),
    'GENET_SYS_OFF': ('0x0000', 45),
    'SYS_RBUF_FLUSH_CTRL': ('(GENET_SYS_OFF + 0x08)', 46),
    'SYS_TBUF_FLUSH_CTRL': ('(GENET_SYS_OFF + 0x0c)', 47),
    'GENET_EXT_OFF': ('0x0080', 49),
    'EXT_RGMII_OOB_CTRL': ('(GENET_EXT_OFF + 0x0c)', 50),
    'RGMII_LINK': ('BIT(4)', 51),
    'OOB_DISABLE': ('BIT(5)', 52),
    'RGMII_MODE_EN': ('BIT(6)', 53),
    'ID_MODE_DIS': ('BIT(16)', 54),
    'GENET_RBUF_OFF': ('0x0300', 56),
    'RBUF_TBUF_SIZE_CTRL': ('(GENET_RBUF_OFF + 0xb4)', 57),
    'RBUF_CTRL': ('(GENET_RBUF_OFF + 0x00)', 58),
    'RBUF_ALIGN_2B': ('BIT(1)', 59),
    'GENET_UMAC_OFF': ('0x0800', 61),
    'UMAC_MIB_CTRL': ('(GENET_UMAC_OFF + 0x580)', 62),
    'UMAC_MAX_FRAME_LEN': ('(GENET_UMAC_OFF + 0x014)', 63),
    'UMAC_MAC0': ('(GENET_UMAC_OFF + 0x00c)', 64),
    'UMAC_MAC1': ('(GENET_UMAC_OFF + 0x010)', 65),
    'UMAC_CMD': ('(GENET_UMAC_OFF + 0x008)', 66),
    'MDIO_CMD': ('(GENET_UMAC_OFF + 0x614)', 67),
    'UMAC_TX_FLUSH': ('(GENET_UMAC_OFF + 0x334)', 68),
    'MDIO_START_BUSY': ('BIT(29)', 69),
    'MDIO_READ_FAIL': ('BIT(28)', 70),
    'MDIO_WR': ('BIT(26)', 72),
    'MDIO_PMD_SHIFT': ('21', 73),
    'MDIO_PMD_MASK': ('0x1f', 74),
    'MDIO_REG_SHIFT': ('16', 75),
    'MDIO_REG_MASK': ('0x1f', 76),
    'UMAC_SPEED_1000': ('2', 82),
    'CMD_SPEED_SHIFT': ('2', 84),
    'CMD_SPEED_MASK': ('3', 85),
    'CMD_SW_RESET': ('BIT(13)', 86),
    'CMD_LCL_LOOP_EN': ('BIT(15)', 87),
    'CMD_TX_EN': ('BIT(0)', 88),
    'CMD_RX_EN': ('BIT(1)', 89),
    'MIB_RESET_RX': ('BIT(0)', 91),
    'MIB_RESET_RUNT': ('BIT(1)', 92),
    'MIB_RESET_TX': ('BIT(2)', 93),
    'TOTAL_DESCS': ('256', 96),
    'RX_DESCS': ('TOTAL_DESCS', 97),
    'DEFAULT_Q': ('0x10', 100),
    'ENET_BRCM_TAG_LEN': ('6', 105),
    'ENET_PAD': ('8', 106),
    'ENET_MAX_MTU_SIZE': ('(ETH_DATA_LEN + ETH_HLEN + VLAN_HLEN + ENET_BRCM_TAG_LEN + ETH_FCS_LEN + ENET_PAD)', 107),
    'DMA_EN': ('BIT(0)', 112),
    'DMA_RING_BUF_EN_SHIFT': ('0x01', 113),
    'DMA_BUFLENGTH_MASK': ('0x0fff', 115),
    'DMA_BUFLENGTH_SHIFT': ('16', 116),
    'DMA_RING_SIZE_SHIFT': ('16', 117),
    'DMA_OWN': ('0x8000', 118),
    'DMA_EOP': ('0x4000', 119),
    'DMA_SOP': ('0x2000', 120),
    'DMA_MAX_BURST_LENGTH': ('0x8', 122),
    'DMA_TX_APPEND_CRC': ('0x0040', 125),
    'DMA_TX_QTAG_SHIFT': ('7', 128),
    'DMA_RING_SIZE': ('0x40', 131),
    'DMA_RINGS_SIZE': ('(DMA_RING_SIZE * (DEFAULT_Q + 1))', 132),
    'DMA_DESC_LENGTH_STATUS': ('0x00', 135),
    'DMA_DESC_ADDRESS_LO': ('0x04', 136),
    'DMA_DESC_ADDRESS_HI': ('0x08', 137),
    'DMA_DESC_SIZE': ('12', 138),
    'GENET_RX_OFF': ('0x2000', 140),
    'GENET_RDMA_REG_OFF': ('(GENET_RX_OFF + TOTAL_DESCS * DMA_DESC_SIZE)', 141),
    'GENET_TX_OFF': ('0x4000', 143),
    'GENET_TDMA_REG_OFF': ('(GENET_TX_OFF + TOTAL_DESCS * DMA_DESC_SIZE)', 144),
    'DMA_FC_THRESH_HI': ('(RX_DESCS >> 4)', 147),
    'DMA_FC_THRESH_LO': ('5', 148),
    'DMA_FC_THRESH_VALUE': ('((DMA_FC_THRESH_LO << 16) | DMA_FC_THRESH_HI)', 149),
    'TDMA_RING_REG_BASE': ('(GENET_TDMA_REG_OFF + DEFAULT_Q * DMA_RING_SIZE)', 154),
    'TDMA_READ_PTR': ('(TDMA_RING_REG_BASE + 0x00)', 156),
    'TDMA_CONS_INDEX': ('(TDMA_RING_REG_BASE + 0x08)', 157),
    'TDMA_PROD_INDEX': ('(TDMA_RING_REG_BASE + 0x0c)', 158),
    'DMA_RING_BUF_SIZE': ('0x10', 159),
    'DMA_START_ADDR': ('0x14', 160),
    'DMA_END_ADDR': ('0x1c', 161),
    'DMA_MBUF_DONE_THRESH': ('0x24', 162),
    'TDMA_FLOW_PERIOD': ('(TDMA_RING_REG_BASE + 0x28)', 163),
    'TDMA_WRITE_PTR': ('(TDMA_RING_REG_BASE + 0x2c)', 164),
    'RDMA_RING_REG_BASE': ('(GENET_RDMA_REG_OFF + DEFAULT_Q * DMA_RING_SIZE)', 166),
    'RDMA_WRITE_PTR': ('(RDMA_RING_REG_BASE + 0x00)', 168),
    'RDMA_PROD_INDEX': ('(RDMA_RING_REG_BASE + 0x08)', 169),
    'RDMA_CONS_INDEX': ('(RDMA_RING_REG_BASE + 0x0c)', 170),
    'RDMA_XON_XOFF_THRESH': ('(RDMA_RING_REG_BASE + 0x28)', 171),
    'RDMA_READ_PTR': ('(RDMA_RING_REG_BASE + 0x2c)', 172),
    'TDMA_REG_BASE': ('(GENET_TDMA_REG_OFF + DMA_RINGS_SIZE)', 174),
    'RDMA_REG_BASE': ('(GENET_RDMA_REG_OFF + DMA_RINGS_SIZE)', 175),
    'DMA_RING_CFG': ('0x00', 176),
    'DMA_CTRL': ('0x04', 177),
    'DMA_SCB_BURST_SIZE': ('0x0c', 178),
    'RX_BUF_LENGTH': ('2048', 180),
    'RX_BUF_OFFSET': ('2', 182),
}

# Linux v6.12 (revision adc218676eef25575469234709c2d87185ca223a),
# drivers/net/ethernet/broadcom/unimac.h.
LINUX_UNIMAC_H = {
    'CMD_RX_PAUSE_IGNORE': ('(1 << 8)', 23),
    'CMD_TX_PAUSE_IGNORE': ('(1 << 28)', 35),
    'UMAC_MODE': ('0x044', 42),
    'MODE_LINK_STATUS': ('(1 << 5)', 43),
}

# Linux v6.12 (same revision), include/uapi/linux/mii.h.
LINUX_MII_H = {
    'MII_BMCR': ('0x00', 16),
    'MII_BMSR': ('0x01', 17),
    'MII_PHYSID1': ('0x02', 18),
    'MII_PHYSID2': ('0x03', 19),
    'MII_ADVERTISE': ('0x04', 20),
    'MII_LPA': ('0x05', 21),
    'MII_CTRL1000': ('0x09', 23),
    'MII_STAT1000': ('0x0a', 24),
    'BMCR_SPEED1000': ('0x0040', 42),
    'BMCR_FULLDPLX': ('0x0100', 44),
    'BMCR_ANRESTART': ('0x0200', 45),
    'BMCR_ISOLATE': ('0x0400', 46),
    'BMCR_ANENABLE': ('0x1000', 48),
    'BMSR_LSTATUS': ('0x0004', 57),
    'BMSR_ANEGCAPABLE': ('0x0008', 58),
    'BMSR_ANEGCOMPLETE': ('0x0020', 60),
    'BMSR_ESTATEN': ('0x0100', 62),
    'BMSR_10HALF': ('0x0800', 65),
    'BMSR_10FULL': ('0x1000', 66),
    'BMSR_100HALF': ('0x2000', 67),
    'BMSR_100FULL': ('0x4000', 68),
    'ADVERTISE_CSMA': ('0x0001', 73),
    'ADVERTISE_10HALF': ('0x0020', 74),
    'ADVERTISE_10FULL': ('0x0040', 76),
    'ADVERTISE_100HALF': ('0x0080', 78),
    'ADVERTISE_100FULL': ('0x0100', 80),
    'ADVERTISE_PAUSE_CAP': ('0x0400', 83),
    'ADVERTISE_PAUSE_ASYM': ('0x0800', 84),
    'LPA_10HALF': ('0x0020', 97),
    'LPA_10FULL': ('0x0040', 99),
    'LPA_100HALF': ('0x0080', 101),
    'LPA_100FULL': ('0x0100', 103),
    'LPA_LPACK': ('0x4000', 110),
    'ADVERTISE_1000FULL': ('0x0200', 152),
    'ADVERTISE_1000HALF': ('0x0100', 153),
    'LPA_1000FULL': ('0x0800', 163),
    'LPA_1000HALF': ('0x0400', 164),
}

# Linux v6.12 (same revision), drivers/net/ethernet/broadcom/genet/bcmgenet.h.
LINUX_BCMGENET_H = {
    'UMAC_MIB_START': ('0x400', 155),
    'RBUF_OVFL_CNT_V3PLUS': ('0x94', 169),
    'RBUF_ERR_CNT_V3PLUS': ('0x98', 181),
    'UMAC_MDF_ERR_CNT': ('0x638', 182),
}

# Linux v6.12 (same revision), drivers/net/ethernet/broadcom/genet/bcmgenet.c.
LINUX_BCMGENET_C = {
    'BCMGENET_STAT_OFFSET': ('0xc', 1025),
}

# Linux v6.12 bcmgenet.h: the MIB counter structures, field names in
# declaration order.  "@name" is an embedded struct bcmgenet_pkt_counters.
#   struct name: (first line, last line, fields)
LINUX_BCMGENET_H_STRUCTS = {
    'bcmgenet_pkt_counters': (77, 88, ['cnt_64', 'cnt_127', 'cnt_255', 'cnt_511', 'cnt_1023', 'cnt_1518', 'cnt_mgv', 'cnt_2047', 'cnt_4095', 'cnt_9216']),
    'bcmgenet_rx_counters': (91, 112, ['@pkt_cnt', 'pkt', 'bytes', 'mca', 'bca', 'fcs', 'cf', 'pf', 'uo', 'aln', 'flr', 'cde', 'fcr', 'ovr', 'jbr', 'mtue', 'pok', 'uc', 'ppp', 'rcrc']),
    'bcmgenet_tx_counters': (115, 136, ['@pkt_cnt', 'pkts', 'mca', 'bca', 'pf', 'cf', 'fcs', 'ovr', 'drf', 'edf', 'scl', 'mcl', 'lcl', 'ecl', 'frg', 'ncl', 'jbr', 'bytes', 'pok', 'uc']),
}

# raspberrypi/linux rpi-6.12.y, arch/arm64/boot/dts/broadcom/bcm2711.dtsi
#   :41-43    soc ranges = <child 0x0 parent size>, three entries
#   :587-589  genet: ethernet@7d580000 { ... reg = <0x0 0x7d580000 0x10000>;
DT_SOC_RANGES = [
    (0x7E000000, 0xFE000000, 0x01800000),
    (0x7C000000, 0xFC000000, 0x02000000),
    (0x40000000, 0xFF800000, 0x00800000),
]
DT_GENET_NODE = 0x7D580000
DT_GENET_REG = (0x7D580000, 0x10000)
# the same tree, arch/arm64/boot/dts/broadcom/bcm2711-rpi-4-b.dts
#   :213-216  phy1: ethernet-phy@1 { reg = <0x1>; ...
DT_PHY_UNIT = 0x1
DT_PHY_REG = 0x1

def pinned(tab: dict[str, tuple[str, int]]) -> dict[str, str]:
    return {name: body for name, (body, _line) in tab.items()}


def parse_mib_layout() -> dict[str, int]:
    """The UniMAC statistics block, laid out from Linux's own structures.

    THIS IS THE POINT OF THE WHOLE FUNCTION: genet.pi4 carries thirteen
    MIB offsets as literals, and the only way to grade a literal is to
    derive the same number from the vendor independently.  Nothing here
    reads the library.

    The layout is the declaration order of struct bcmgenet_rx_counters
    and struct bcmgenet_tx_counters in bcmgenet.h, each opening with an
    embedded struct bcmgenet_pkt_counters, starting at UMAC_MIB_START.

    AND THERE IS A GAP BETWEEN THE GROUPS THAT THE C STRUCTURES DO NOT
    SHOW.  bcmgenet_update_mib_counters walks the list with a running byte
    offset and adds BCMGENET_STAT_OFFSET when it crosses from the RX group
    into the TX group (bcmgenet.c:1213-1220, and the comment at
    :1022-1024).  A reader that trusts the structures alone lands three
    registers early on the TX side, on plausible numbers - which is the
    failure this layout exists to make impossible.

    Checked against the vendor's own three annotations: rx.pkt is
    commented "(0x428)", tx.pkts "(0x4a8)" and tx.uc "(0x4f0)".
    """
    def fields(struct_name: str) -> list[str]:
        out: list[str] = []
        for f in LINUX_BCMGENET_H_STRUCTS[struct_name][2]:
            if f.startswith("@"):
                out += [f[1:] + "." + x for x in fields("bcmgenet_pkt_counters")]
            else:
                out.append(f)
        return out

    kh = linux_macros()
    kc = Macros(pinned(LINUX_BCMGENET_C))
    start = kh["UMAC_MIB_START"]
    gap = kc["BCMGENET_STAT_OFFSET"]

    layout: dict[str, int] = {}
    off = start
    for group in ("rx", "tx"):
        for name in fields("bcmgenet_%s_counters" % group):
            layout["%s.%s" % (group, name)] = off
            off += 4
        off += gap

    for name, want in (("rx.pkt", 0x428), ("tx.pkts", 0x4A8), ("tx.uc", 0x4F0)):
        if layout.get(name) != want:
            raise SystemExit(
                "The MIB layout put %s at $%03X and the vendor's own comment "
                "in bcmgenet.h says $%03X. The pinned structure table is "
                "wrong, not the library - fix it before grading anything."
                % (name, layout.get(name, 0), want))
    return layout


_CACHE: dict[str, object] = {}


def linux_macros() -> "Macros":
    """Linux bcmgenet.h's pinned #defines, resolved once."""
    if "lnx" not in _CACHE:
        _CACHE["lnx"] = Macros(pinned(LINUX_BCMGENET_H))
    return _CACHE["lnx"]


def mib_layout_cached() -> dict[str, int]:
    if "mib" not in _CACHE:
        _CACHE["mib"] = parse_mib_layout()
    return _CACHE["mib"]


class Macros(dict):
    """Lazy symbolic evaluator over a #define table."""

    def __init__(self, *tables: dict[str, str]) -> None:
        super().__init__()
        self.defs: dict[str, str] = {}
        for tab in tables:
            self.defs.update(tab)
        self._busy: set[str] = set()

    def __missing__(self, key: str):
        if key == "BIT":
            return lambda n: 1 << n
        if key in EXTERNS:
            return EXTERNS[key]
        if key not in self.defs:
            raise SystemExit(
                f"The pinned vendor tables do not define {key}. Pin it from "
                f"the cited source with its line; if the source no longer "
                f"defines it, the library's citation for it is stale.")
        if key in self._busy:
            raise SystemExit(f"{key} is defined in terms of itself.")
        self._busy.add(key)
        try:
            body = self.defs[key]
            try:
                value = eval(body, {"__builtins__": {}}, self)   # noqa: S307
            except SyntaxError:
                raise SystemExit(f"Cannot evaluate #define {key} {body!r}.")
        finally:
            self._busy.discard(key)
        if not isinstance(value, int):
            raise SystemExit(f"#define {key} did not resolve to an integer.")
        self[key] = value
        return value


def dtsi_genet_base() -> tuple[int, int]:
    """ARM address and length of the ethernet node, from the device tree.

    The node's reg is a legacy VideoCore bus address.  The soc node's own
    ranges translate it, and the translation is applied here rather than
    assumed, so that a device tree with different ranges would move the
    model instead of silently disagreeing with it.
    """
    bus, length = DT_GENET_REG
    if bus != DT_GENET_NODE:
        raise SystemExit("The pinned ethernet node's unit address and reg disagree.")
    for c, p, s in DT_SOC_RANGES:
        if c <= bus < c + s:
            return p + (bus - c), length
    raise SystemExit(f"No soc range covers the ethernet node at 0x{bus:x}.")


def dts_phy_address() -> int:
    if DT_PHY_REG != DT_PHY_UNIT:
        raise SystemExit("The pinned ethernet-phy node's unit address and reg disagree.")
    return DT_PHY_REG


# =====================================================================
#  THE MODELLED BOARD
# =====================================================================
class Genet:
    def __init__(self, cpu, k: "Macros", base: int, size: int, phy_addr: int,
                 mii: "Macros", half_duplex: bool = False,
                 pause_advertised: bool = False) -> None:
        # Linux's header and the statistics layout are pure functions of
        # files on disk, so they are read once and cached rather than
        # threaded through four call sites that have no opinion on them.
        lnx = linux_macros()
        mib_layout = mib_layout_cached()
        self.cpu = cpu
        self.k = k
        self.mii = mii
        self.lnx = lnx
        self.half_duplex = half_duplex
        # A PHY THAT COMES UP ALREADY ADVERTISING PAUSE, which is the
        # case GenetPhyPauseSet() has to correct rather than leave alone.
        self.pause_advertised = pause_advertised
        self.base = base
        self.size = size
        self.phy_addr = phy_addr
        self.uart = bytearray()
        self.steps = 0

        # ---- the register map, composed the way the driver composes it
        ring = k["DMA_RING_SIZE"]
        rdma_ring = k["RDMA_RING_REG_BASE"]
        tdma_ring = k["TDMA_RING_REG_BASE"]
        rdma_eng = k["RDMA_REG_BASE"]
        tdma_eng = k["TDMA_REG_BASE"]
        assert ring  # keeps the name honest if the driver ever drops it

        named: dict[int, str] = {}
        for n in ("SYS_REV_CTRL", "SYS_PORT_CTRL", "SYS_RBUF_FLUSH_CTRL",
                  "SYS_TBUF_FLUSH_CTRL", "EXT_RGMII_OOB_CTRL", "RBUF_CTRL",
                  "RBUF_TBUF_SIZE_CTRL", "UMAC_CMD", "UMAC_MAC0", "UMAC_MAC1",
                  "UMAC_MAX_FRAME_LEN", "UMAC_TX_FLUSH", "UMAC_MIB_CTRL",
                  "MDIO_CMD", "TDMA_READ_PTR", "TDMA_CONS_INDEX",
                  "TDMA_PROD_INDEX", "TDMA_FLOW_PERIOD", "TDMA_WRITE_PTR",
                  "RDMA_WRITE_PTR", "RDMA_PROD_INDEX", "RDMA_CONS_INDEX",
                  "RDMA_XON_XOFF_THRESH", "RDMA_READ_PTR"):
            named[k[n]] = n
        for pfx, blk in (("TDMA", tdma_ring), ("RDMA", rdma_ring)):
            for n in ("DMA_RING_BUF_SIZE", "DMA_START_ADDR", "DMA_END_ADDR",
                      "DMA_MBUF_DONE_THRESH"):
                named[blk + k[n]] = f"{pfx}_{n[4:]}"
        for pfx, blk in (("TDMA", tdma_eng), ("RDMA", rdma_eng)):
            for n in ("DMA_RING_CFG", "DMA_CTRL", "DMA_SCB_BURST_SIZE"):
                named[blk + k[n]] = f"{pfx}_{n[4:]}"
        # The one single-source register the library reads.  Modelled
        # read-only on purpose - see the module docstring.
        self.umac_mode = k["GENET_UMAC_OFF"] + k["UMAC_MODE"]
        named[self.umac_mode] = "UMAC_MODE"

        # THE UNIMAC STATISTICS BLOCK, PLACED FROM LINUX'S OWN STRUCTURES
        # AND NOT FROM THE LIBRARY.  parse_mib_layout() walks struct
        # bcmgenet_rx_counters and struct bcmgenet_tx_counters in
        # declaration order from UMAC_MIB_START, applying the $C gap the
        # driver's own MIB walk applies between the groups.  Every
        # counter is named here, so a library that computes ONE of these
        # offsets wrongly either lands on a different named counter -
        # which the read trace catches by name - or lands nowhere, and
        # the model refuses with "unmodelled MMIO".  Grading them by
        # VALUE would not do this: every counter reads zero on a healthy
        # link, so a wrong offset would read zero and look right.
        self.mib = {}
        for name, rel in mib_layout.items():
            off = k["GENET_UMAC_OFF"] + rel
            named[off] = "MIB_" + name
            self.mib[name] = off
        # The three counters that are NOT in the MIB block: two in the
        # RBUF block at the GENETv3-and-later offsets, and the address
        # filter's error count in the UMAC block.
        self.rbuf_ovfl = k["GENET_RBUF_OFF"] + lnx["RBUF_OVFL_CNT_V3PLUS"]
        self.rbuf_err = k["GENET_RBUF_OFF"] + lnx["RBUF_ERR_CNT_V3PLUS"]
        self.mdf_err = k["GENET_UMAC_OFF"] + lnx["UMAC_MDF_ERR_CNT"]
        named[self.rbuf_ovfl] = "RBUF_OVFL_CNT"
        named[self.rbuf_err] = "RBUF_ERR_CNT"
        named[self.mdf_err] = "UMAC_MDF_ERR_CNT"
        # MODE_LINK_STATUS IS DERIVED, NOT PRELOADED - see load().
        # It used to be a constant 1 in this model, which meant the gate
        # could not tell the MAC's link bit apart from a stuck bit, and
        # could not see WHEN the library read it. On silicon the probe
        # read it before bring-up, got the 0 the hardware owed it, and
        # that 0 was mistaken for a MAC/PHY disagreement. The model now
        # drives the bit from EXT_RGMII_OOB_CTRL exactly as the silicon
        # does, so reading it at the wrong moment is a gate failure.
        self.named = named
        self.reg: dict[int, int] = {off: 0 for off in named}

        # ---- descriptors, which on this part are MMIO
        self.n_desc = k["TOTAL_DESCS"]
        self.desc_size = k["DMA_DESC_SIZE"]
        self.rx_desc_lo = k["GENET_RX_OFF"]
        self.rx_desc_hi = self.rx_desc_lo + self.n_desc * self.desc_size
        self.tx_desc_lo = k["GENET_TX_OFF"]
        self.tx_desc_hi = self.tx_desc_lo + self.n_desc * self.desc_size
        self.rxdesc = [[0, 0, 0] for _ in range(self.n_desc)]
        self.txdesc = [[0, 0, 0] for _ in range(self.n_desc)]

        # ---- what a real board would already have in these registers.
        # The foreign bits are what the read-modify-write assertions are
        # made of: nothing here owns them, so nothing here may lose them.
        #
        # SYS_REV_CTRL's low bits are invented on purpose. The board
        # reads $06000000, but a model that also reads $06000000 cannot
        # tell a correct mask from one that happens to return zero. The
        # major nibble is the measured one; the rest is a tripwire.
        self.reg[k["SYS_REV_CTRL"]] = (6 << 24) | (0 << 16) | 0x1234
        self.reg[self.umac_mode] = 0                # MODE_LINK_STATUS derived
        self.reg[k["RBUF_CTRL"]] = 0x00000101       # bits 0 and 8, foreign
        # THE MEASURED RESET VALUE, read off the board on 2026-08-26 from
        # a monitor that does not link genet.pi4 at all, so nothing of
        # ours had touched the block when it was taken.
        #
        # This line used to be a GUESS - OOB_DISABLE together with an
        # invented bit 9 - and the guess was wrong in the direction that
        # mattered. OOB_DISABLE is CLEAR at reset, not set. The bits that
        # are actually set are 20 through 23, and they are named by
        # NEITHER source: U-Boot defines four bits in this register
        # (:51-54) and Linux defines five (bcmgenet.h:322-326), and
        # nothing in either accounts for $00F00000.
        #
        # That makes them a better read-modify-write witness than the
        # invented bit ever was, because they are real hardware bits
        # rather than ones this gate made up. A blind write of the RGMII
        # configuration would clear four bits that nobody on this disk
        # can name, and would do it silently.
        self.reg[k["EXT_RGMII_OOB_CTRL"]] = 0x00F00000
        # Measured as well, and it settles a question that was raised as
        # a second candidate for the silent-receive symptom: the port
        # mode is NOT inherited from the firmware. It reads zero, and
        # PORT_MODE_EXT_GPHY is 3, so it genuinely has to be programmed.
        self.reg[k["SYS_PORT_CTRL"]] = 0x00000000
        self.reg[k["UMAC_CMD"]] = 0x00000000
        self.reg[k["UMAC_MAC0"]] = 0x00000000
        self.reg[k["UMAC_MAC1"]] = 0x00000000
        # NEITHER INDEX STARTS AT ZERO.  The driver's own comments say
        # these cannot be initialised by software, and a library that
        # assumed zero would use the wrong descriptors.
        self.rdma_prod = 7
        self.tdma_cons = 5
        self.reg[k["RDMA_PROD_INDEX"]] = self.rdma_prod
        self.reg[k["TDMA_CONS_INDEX"]] = self.tdma_cons
        self.tx_cursor = self.tdma_cons & 0xFF
        self.tx_prod_seen = None

        # ---- the PHY
        self.phy = self._build_phy()
        self.mdio_reads: list[tuple[int, int]] = []
        self.mdio_writes: list[tuple[int, int, int]] = []
        self.mdio_cmd_trace: list[tuple[str, int]] = []

        # ---- traces
        self.writes: list[tuple[str, int]] = []      # (name, value)
        self.reads: list[str] = []
        self.desc_trace: list[tuple[str, int, str, int]] = []
        self.order: list[str] = []                   # everything, in order
        self.sent: list[bytes] = []
        self.rx_countdown = 0        # polls still owed before we answer
        self.rx_polls = 0            # how many the library actually did
        self.injected: bytes | None = None
        self.forbidden_writes: list[tuple[str, int]] = []

    # -----------------------------------------------------------------
    def _build_phy(self) -> dict[int, int]:
        m = self.mii
        bmsr = (m["BMSR_LSTATUS"] | m["BMSR_ANEGCAPABLE"] |
                m["BMSR_ANEGCOMPLETE"] | m["BMSR_ESTATEN"] |
                m["BMSR_100FULL"] | m["BMSR_100HALF"] |
                m["BMSR_10FULL"] | m["BMSR_10HALF"])
        return {
            m["MII_BMCR"]: m["BMCR_ANENABLE"] | m["BMCR_SPEED1000"] |
                           m["BMCR_FULLDPLX"],
            m["MII_BMSR"]: bmsr,
            # A Broadcom OUI.  The library must not care what it is - it
            # only refuses all-zeros and all-ones - so the value here is
            # deliberately not any particular part number.
            m["MII_PHYSID1"]: 0x600D,
            m["MII_PHYSID2"]: 0x84A2,
            m["MII_ADVERTISE"]: (m["ADVERTISE_CSMA"] | m["ADVERTISE_10HALF"] |
                                 m["ADVERTISE_10FULL"] | m["ADVERTISE_100HALF"] |
                                 m["ADVERTISE_100FULL"] |
                                 # THE PAUSE PAIR IS NORMALLY ABSENT,
                                 # which is what this board's PHY does
                                 # out of reset and is why the ordinary
                                 # pass must see NO write here. The
                                 # pause_advertised pass turns them on
                                 # so the correcting path is exercised.
                                 ((m["ADVERTISE_PAUSE_CAP"] |
                                   m["ADVERTISE_PAUSE_ASYM"])
                                  if self.pause_advertised else 0)),
            m["MII_LPA"]: (m["LPA_10HALF"] | m["LPA_10FULL"] |
                           m["LPA_100HALF"] | m["LPA_100FULL"] |
                           m["LPA_LPACK"]),
            # We advertise gigabit full and the partner reports gigabit
            # full, so the AND survives and the resolved link is 1000FD.
            # In the half-duplex pass only the HALF bits are advertised
            # on both sides, so the AND resolves to 1000 half - which is
            # the link genet.pi4 refuses to bring a MAC up on.
            m["MII_CTRL1000"]: (m["ADVERTISE_1000HALF"] if self.half_duplex
                                else m["ADVERTISE_1000FULL"] |
                                     m["ADVERTISE_1000HALF"]),
            m["MII_STAT1000"]: (m["LPA_1000HALF"] if self.half_duplex
                                else m["LPA_1000FULL"] | m["LPA_1000HALF"]),
        }

    # -----------------------------------------------------------------
    def _mdio_run(self, cmd: int) -> int:
        """Execute the transaction the command word describes."""
        k = self.k
        addr = (cmd >> k["MDIO_PMD_SHIFT"]) & k["MDIO_PMD_MASK"]
        reg = (cmd >> k["MDIO_REG_SHIFT"]) & k["MDIO_REG_MASK"]
        out = cmd & ~k["MDIO_START_BUSY"] & 0xFFFFFFFF
        if cmd & k["MDIO_WR"]:
            if addr == self.phy_addr:
                self.phy[reg] = cmd & 0xFFFF
                self.mdio_writes.append((addr, reg, cmd & 0xFFFF))
            return out
        # a read
        if addr != self.phy_addr:
            # Nothing there.  A real MAC sets READ_FAIL and the data
            # bits float high; a library that ignores READ_FAIL reads
            # $FFFF and believes it.
            return (out | k["MDIO_READ_FAIL"] | 0xFFFF) & 0xFFFFFFFF
        self.mdio_reads.append((addr, reg))
        return (out & 0xFFFF0000) | self.phy.get(reg, 0)

    # -----------------------------------------------------------------
    def load(self, addr: int, size: int) -> int:
        if UART_LO <= addr <= UART_HI:
            if addr == UART_FR:
                return 0
            return 0
        off = addr - self.base
        if not (0 <= off < self.size):
            raise SystemExit(f"The probe read outside every modelled block at ${addr:08X}.")
        if size != 4:
            raise SystemExit(
                f"a {size}-byte read of a 32-bit GENET register at +${off:04X}. "
                "Every register in this block is 32 bits; a bare Peek is "
                "eight bytes on this target and would return two registers "
                "concatenated.")
        if self.rx_desc_lo <= off < self.rx_desc_hi:
            i, f = divmod(off - self.rx_desc_lo, self.desc_size)
            self.desc_trace.append(("R", i, self._field(f), 0))
            return self.rxdesc[i][f // 4]
        if self.tx_desc_lo <= off < self.tx_desc_hi:
            i, f = divmod(off - self.tx_desc_lo, self.desc_size)
            return self.txdesc[i][f // 4]
        if off in self.named:
            name = self.named[off]
            self.reads.append(name)
            self.order.append("r:" + name)
            if name == "RDMA_PROD_INDEX":
                # The network does not answer on the first poll.  See
                # RX_ANSWER_AFTER_POLLS.
                if self.rx_countdown > 0:
                    self.rx_polls += 1
                    self.rx_countdown -= 1
                    if self.rx_countdown == 0:
                        self._inject()
                return self.rdma_prod
            if name == "TDMA_CONS_INDEX":
                return self.tdma_cons
            if name == "UMAC_MODE":
                # MODE_LINK_STATUS is not a register bit software owns.
                # It is the MAC's view of the RGMII link, and on this
                # part that view comes from EXT_RGMII_OOB_CTRL: the MAC
                # believes the line is up only once OOB_DISABLE has been
                # cleared and RGMII_LINK has been set, which is what
                # bcmgenet_adjust_link() does at :461-462.  Linux drives
                # the same pair from the other side - it sets RGMII_LINK
                # on link-up (v6.12_bcmmii.c:74-77), clears it on
                # link-down (:113), and reads MODE_LINK_STATUS straight
                # back out as the link state (:128-130).
                oob = self.reg[self.k["EXT_RGMII_OOB_CTRL"]]
                v = self.reg[off] & ~self.k["MODE_LINK_STATUS"]
                if (oob & self.k["RGMII_LINK"]) and not (oob & self.k["OOB_DISABLE"]):
                    v |= self.k["MODE_LINK_STATUS"]
                return v
            return self.reg[off]
        raise SystemExit(
            f"unmodelled MMIO read at GENET +${off:04X} (${addr:08X}).\n"
            "No macro in " + DRIVER_NAME + " names that offset, so either "
            "the library computed one wrongly or the driver has moved a "
            "register and the library's citation is stale.")

    def _field(self, f: int) -> str:
        return {self.k["DMA_DESC_LENGTH_STATUS"]: "LEN",
                self.k["DMA_DESC_ADDRESS_LO"]: "LO",
                self.k["DMA_DESC_ADDRESS_HI"]: "HI"}[f]

    # -----------------------------------------------------------------
    def store(self, addr: int, value: int, size: int) -> None:
        v = value & 0xFFFFFFFF
        if UART_LO <= addr <= UART_HI:
            if addr == UART_DR:
                self.uart.append(v & 0xFF)
            return
        off = addr - self.base
        if not (0 <= off < self.size):
            raise SystemExit(f"MMIO write outside every modelled block at ${addr:08X}")
        if size != 4:
            raise SystemExit(
                f"a {size}-byte write to a 32-bit GENET register at +${off:04X}")

        if self.rx_desc_lo <= off < self.rx_desc_hi:
            i, f = divmod(off - self.rx_desc_lo, self.desc_size)
            self.rxdesc[i][f // 4] = v
            self.desc_trace.append(("W", i, self._field(f), v))
            self.order.append(f"rxdesc{i}:{self._field(f)}")
            return
        if self.tx_desc_lo <= off < self.tx_desc_hi:
            i, f = divmod(off - self.tx_desc_lo, self.desc_size)
            self.txdesc[i][f // 4] = v
            self.order.append(f"txdesc{i}:{self._field(f)}")
            return

        if off not in self.named:
            raise SystemExit(
                f"unmodelled MMIO write at GENET +${off:04X} (${addr:08X}) "
                f"= ${v:08X}.\nNo macro in {DRIVER_NAME} names that offset.")

        name = self.named[off]
        # The two registers the cited driver never writes.
        if name in ("SYS_TBUF_FLUSH_CTRL", "UMAC_MODE"):
            self.forbidden_writes.append((name, v))
        self.writes.append((name, v))
        self.order.append(f"w:{name}=${v:08X}")

        if name == "MDIO_CMD":
            self.mdio_cmd_trace.append(("busy" if v & self.k["MDIO_START_BUSY"]
                                        else "cmd", v))
            if v & self.k["MDIO_START_BUSY"]:
                self.reg[off] = self._mdio_run(v)
            else:
                self.reg[off] = v
            return

        if name == "TDMA_PROD_INDEX":
            self._tx(v)
            self.reg[off] = v
            return

        if name == "RDMA_CONS_INDEX":
            self.reg[off] = v
            return

        self.reg[off] = v

    # -----------------------------------------------------------------
    def _mem(self, addr: int, n: int) -> bytes:
        return bytes(self.cpu.memory.get(addr + i, 0) for i in range(n))

    def _tx(self, prod: int) -> None:
        """A write to the producer index is what starts a transmission."""
        if self.tx_prod_seen is None:
            self.tx_prod_seen = prod
            return                       # the ring-init alignment write
        count = (prod - self.tx_prod_seen) & 0xFFFF
        self.tx_prod_seen = prod
        for _ in range(count):
            d = self.txdesc[self.tx_cursor]
            lenstat, lo, hi = d[0], d[1], d[2]
            length = ((lenstat >> self.k["DMA_BUFLENGTH_SHIFT"]) &
                      self.k["DMA_BUFLENGTH_MASK"])
            self.sent.append(self._mem((hi << 32) | lo, length))
            self.tx_cursor = (self.tx_cursor + 1) % self.n_desc
        self.tdma_cons = prod
        # The network answers EVENTUALLY - not on the next poll.
        self.rx_countdown = RX_ANSWER_AFTER_POLLS

    def _inject(self) -> None:
        """Put one frame into the descriptor the library is looking at."""
        i = self.rdma_prod & 0xFF
        lo, hi = self.rxdesc[i][1], self.rxdesc[i][2]
        buf = (hi << 32) | lo
        pad = self.k["RX_BUF_OFFSET"]
        frame = bytearray(INJECT_PAYLOAD_LEN)
        frame[0:6] = bytes.fromhex("020000010203")          # to us-ish
        frame[6:12] = bytes.fromhex("AABBCCDDEEFF")         # from a switch
        frame[12] = (INJECT_ETHERTYPE >> 8) & 0xFF
        frame[13] = INJECT_ETHERTYPE & 0xFF
        for j in range(14, INJECT_PAYLOAD_LEN):
            frame[j] = (0xA0 + j) & 0xFF
        self.injected = bytes(frame)
        # The hardware writes the frame two bytes in, because
        # RBUF_ALIGN_2B told it to, and reports the padded length.
        for j in range(pad):
            self.cpu.memory[buf + j] = 0
        for j, b in enumerate(frame):
            self.cpu.memory[buf + pad + j] = b
        total = INJECT_PAYLOAD_LEN + pad
        self.rxdesc[i][0] = (total << self.k["DMA_BUFLENGTH_SHIFT"])
        self.rdma_prod = (self.rdma_prod + 1) & 0xFFFF
        self.reg[self.k["RDMA_PROD_INDEX"]] = self.rdma_prod


# =====================================================================
#  BUILD AND RUN
# =====================================================================
def build(source: pathlib.Path, out: pathlib.Path) -> None:
    cmd = [COMPILER, "--compile", str(source), "-t", "pi4",
           "--load-addr", hex(LOAD), "--stack-addr", hex(STACK),
           "--entry-returns", "-o", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    if r.returncode != 0 or not out.exists():
        raise SystemExit("The GENET probe did not build:\n" + r.stdout)


def run(img: pathlib.Path, factory):
    blob = img.read_bytes()
    cpu = A64()
    for i, b in enumerate(blob):
        cpu.memory[LOAD + i] = b
    # Names for the alignment rule's message, read from the `.dbg` the
    # compiler writes. A missing `.dbg` costs the name, not the check.
    attach_symbols(cpu, img, LOAD)
    cpu.pc = LOAD
    cpu.sp = LOADER_SP
    cpu.x[30] = LOADER_LR

    board = factory(cpu)
    mem = cpu.memory
    lo, hi = board.base, board.base + board.size

    def load(addr, size):
        # THE ALIGNMENT RULE. This closure replaces A64.load, so the
        # guard has to be CALLED here - see a64_interp.py's ALIGNMENT
        # RULE note. With the MMU off every data access is
        # Device-nGnRnE and an unaligned wide one is a silent runaway
        # on the part; without this line the gate models a machine
        # more permissive than the board it certifies.
        cpu.align_guard(addr, size, False)
        if lo <= addr < hi or UART_LO <= addr <= UART_HI:
            return board.load(addr, size)
        return sum(mem.get(addr + i, 0) << (8 * i) for i in range(size))

    def store(addr, value, size):
        cpu.align_guard(addr, size, True)
        if lo <= addr < hi or UART_LO <= addr <= UART_HI:
            board.store(addr, value, size)
            return
        for i in range(size):
            mem[addr + i] = (value >> (8 * i)) & 0xFF

    cpu.load = load
    cpu.store = store
    plain_step = A64.step.__get__(cpu)

    def step():
        board.steps += 1
        # cpu.fetch, not load: an instruction fetch is Normal
        # Non-Cacheable with the MMU off, not Device, so it is not
        # subject to the data alignment rule. It still goes through
        # the closure above, so MMIO decoding is unchanged.
        ins = cpu.fetch(cpu.pc)
        if (ins & 0xFFFFFFE0) == 0xD53BE000:        # MRS Xt, CNTFRQ_EL0
            cpu.x[ins & 31] = CNTFRQ
            cpu.pc += 4
            return
        if (ins & 0xFFFFFFE0) == 0xD53BE020:        # MRS Xt, CNTPCT_EL0
            cpu.x[ins & 31] = board.steps // STEPS_PER_TICK
            cpu.pc += 4
            return
        plain_step()

    cpu.step = step
    for _ in range(STEP_LIMIT):
        if cpu.pc == LOADER_LR:
            return cpu, board
        step()
    raise SystemExit(f"the probe never returned ({board.steps} steps)\n"
                     + board.uart.decode("latin-1"))


# =====================================================================
#  THE ASSERTIONS
# =====================================================================
NEWLINE = "\n"
MUTNL = "\n"


EXPECTS = 0


def expect(cond, what, fails):
    global EXPECTS
    EXPECTS += 1
    if not cond:
        fails.append(what)


def check(board: Genet, text: str, k: Macros, mii: Macros,
          base: int, phy_addr: int, fails: list[str]) -> None:

    wr = board.writes
    names = [n for n, _ in wr]

    def value_of(name):
        for n, v in reversed(wr):
            if n == name:
                return v
        return None

    def all_of(name):
        return [v for n, v in wr if n == name]

    # -- the map the probe printed, against the parsed source ----------
    def said_hex(label):
        m = re.search(re.escape(label) + r"\s+\$([0-9A-F]+)", text)
        return int(m.group(1), 16) if m else None

    def said_dec(label):
        m = re.search(re.escape(label) + r"\s+(-?\d+)", text)
        return int(m.group(1)) if m else None

    for label, want in (
            ("base", base),
            ("SYS_REV_CTRL", k["SYS_REV_CTRL"]),
            ("SYS_PORT_CTRL", k["SYS_PORT_CTRL"]),
            ("EXT_RGMII_OOB", k["EXT_RGMII_OOB_CTRL"]),
            ("UMAC_CMD", k["UMAC_CMD"]),
            ("UMAC_MAC0", k["UMAC_MAC0"]),
            ("MDIO_CMD", k["MDIO_CMD"]),
            ("RX desc base", k["GENET_RX_OFF"]),
            ("RDMA ring base", k["RDMA_RING_REG_BASE"]),
            ("RDMA reg base", k["RDMA_REG_BASE"]),
            ("TX desc base", k["GENET_TX_OFF"]),
            ("TDMA ring base", k["TDMA_RING_REG_BASE"]),
            ("TDMA reg base", k["TDMA_REG_BASE"])):
        got = said_hex(label)
        expect(got == want,
               "the library's %s is $%X; %s says $%X"
               % (label, got if got is not None else -1, DRIVER_NAME, want),
               fails)

    # -- 1. the version nibble -----------------------------------------
    expect(said_dec("major (want 6)") == 6,
           "the major revision nibble must read 6 for a GENETv5 "
           "(v2025.01_bcmgenet.c:638-639 rejects anything else)", fails)
    expect(said_dec("probe ok       ") == 1, "GenetProbe() must succeed", fails)

    # -- 2. the reset sequence, as an ordered trace ---------------------
    # bcmgenet_umac_reset(), v2025.01_bcmgenet.c:199-234.  Composed here
    # from the parsed macros, not copied from the library.
    want_seq = [
        ("SYS_RBUF_FLUSH_CTRL", 0x2),                 # set BIT(1)
        ("SYS_RBUF_FLUSH_CTRL", 0x0),                 # clear it
        ("SYS_RBUF_FLUSH_CTRL", 0x0),                 # then a bare zero
        ("UMAC_CMD", 0),
        ("UMAC_CMD", k["CMD_SW_RESET"] | k["CMD_LCL_LOOP_EN"]),
        ("UMAC_CMD", 0),
        ("UMAC_MIB_CTRL", k["MIB_RESET_RX"] | k["MIB_RESET_TX"] |
                          k["MIB_RESET_RUNT"]),
        ("UMAC_MIB_CTRL", 0),
        ("UMAC_MAX_FRAME_LEN", k["ENET_MAX_MTU_SIZE"]),
    ]
    # Find the reset run: it begins at the first SYS_RBUF_FLUSH_CTRL write.
    try:
        start = names.index("SYS_RBUF_FLUSH_CTRL")
        got_seq = wr[start:start + len(want_seq)]
    except ValueError:
        got_seq = []
    expect(got_seq == want_seq,
           "the UMAC reset sequence does not match bcmgenet_umac_reset().\n"
           "      want %s\n      got  %s"
           % (want_seq, got_seq), fails)
    expect(any(n == "UMAC_CMD" and (v & k["CMD_LCL_LOOP_EN"])
               for n, v in wr),
           "the soft reset must carry CMD_LCL_LOOP_EN - the driver's own "
           "comment at :657 says it is there to give the MAC a stable "
           "rxclk, not to test loopback", fails)
    expect(value_of("RBUF_TBUF_SIZE_CTRL") == 1,
           "RBUF_TBUF_SIZE_CTRL must be written 1 (:233)", fails)

    # -- read-modify-write, proved by preloaded foreign bits ------------
    rbuf = value_of("RBUF_CTRL")
    expect(rbuf is not None and (rbuf & k["RBUF_ALIGN_2B"]),
           "RBUF_ALIGN_2B was never set", fails)
    expect(rbuf is not None and (rbuf & 0x00000101) == 0x00000101,
           "RBUF_CTRL was written blind - the bits the model preloaded "
           "(0x101) did not survive, so this is not a read-modify-write",
           fails)

    oob = value_of("EXT_RGMII_OOB_CTRL")
    expect(oob is not None and (oob & k["OOB_DISABLE"]) == 0,
           "OOB_DISABLE must be CLEARED (:461-462)", fails)
    expect(oob is not None and
           (oob & (k["RGMII_LINK"] | k["RGMII_MODE_EN"])) ==
           (k["RGMII_LINK"] | k["RGMII_MODE_EN"]),
           "RGMII_LINK and RGMII_MODE_EN must both be set (:461-462)", fails)
    expect(oob is not None and (oob & k["ID_MODE_DIS"]),
           "ID_MODE_DIS must be set for rgmii-rxid (:464-466) - the PHY "
           "supplies the RX delay and the MAC must add none", fails)
    expect(oob is not None and (oob & 0x00F00000) == 0x00F00000,
           "EXT_RGMII_OOB_CTRL was written blind - bits 20-23 did not "
           "survive. Those four are the board's MEASURED reset state "
           "($00F00000, read 2026-08-26) and they are named by NEITHER "
           "source: U-Boot defines four bits in this register (:51-54) "
           "and Linux five (bcmgenet.h:322-326), and none of them is "
           "these. Clearing four hardware bits nobody can name, "
           "silently, is what a blind write here costs", fails)

    # -- 3. SYS_PORT_CTRL ----------------------------------------------
    expect(value_of("SYS_PORT_CTRL") == k["PORT_MODE_EXT_GPHY"],
           "SYS_PORT_CTRL must be PORT_MODE_EXT_GPHY (:612)", fails)

    # -- 4. MDIO: two writes per transaction ----------------------------
    trace = board.mdio_cmd_trace
    expect(len(trace) >= 4, "almost no MDIO traffic happened", fails)
    bad = []
    i = 0
    while i < len(trace):
        if trace[i][0] != "cmd":
            bad.append(i)
            i += 1
            continue
        if i + 1 >= len(trace) or trace[i + 1][0] != "busy":
            bad.append(i)
            i += 1
            continue
        cmd, busy = trace[i][1], trace[i + 1][1]
        if (busy & ~k["MDIO_START_BUSY"]) != cmd:
            bad.append(i)
        i += 2
    expect(not bad,
           "every MDIO transaction must be a command word and then a "
           "SEPARATE read-modify-write that sets START_BUSY "
           "(bcmgenet_mdio_start(), :539-542). %d of %d were not"
           % (len(bad), len(trace) // 2), fails)
    expect(all((c & k["MDIO_START_BUSY"]) == 0
               for kind, c in trace if kind == "cmd"),
           "a command word carried START_BUSY - the two writes were "
           "collapsed into one", fails)

    # -- 5. the PHY ------------------------------------------------------
    expect(said_dec("address        ") == phy_addr,
           "the PHY must be found at MDIO address %d "
           "(bcm2711-rpi-4-b.dts)" % phy_addr, fails)
    want_id = (board.phy[mii["MII_PHYSID1"]] << 16) | board.phy[mii["MII_PHYSID2"]]
    expect(said_hex("PHY id         ") == want_id,
           "the PHY id must be (PHYSID1 << 16) | PHYSID2", fails)
    expect(said_dec("speed Mbit/s   ") == 1000,
           "the AND of CTRL1000 and STAT1000 gives 1000BASE-T", fails)
    expect(said_dec("full duplex    ") == 1, "and full duplex", fails)
    # THE MAC'S LINK BIT, READ AT BOTH OF THE TWO INSTANTS THAT MATTER.
    # The model derives MODE_LINK_STATUS from EXT_RGMII_OOB_CTRL (see
    # load()), so these two lines are an ORDERING assertion, not just a
    # register-offset one: before bring-up the RGMII block has not been
    # told there is a link and the MAC must say so, and after bring-up
    # it must have been told.
    expect(said_dec("MAC link pre   ") == 0,
           "before GenetStart() the MAC's MODE_LINK_STATUS must read 0. "
           "EXT_RGMII_OOB_CTRL is still at its reset value there - "
           "OOB_DISABLE set, RGMII_LINK clear - so the MAC is taking its "
           "link indication from in-band RGMII signalling this PHY does "
           "not send. A 1 here means the model or the library has the "
           "wrong register", fails)
    expect(said_dec("MAC-side link  ") == 1,
           "after GenetStart() the MAC's own MODE_LINK_STATUS reads 0. "
           "Either GenetAdjustLink() never set RGMII_LINK / never "
           "cleared OOB_DISABLE (:461-462), or the library is reading "
           "the wrong offset for UMAC_MODE (unimac.h:43, $044 within the "
           "UMAC block), or the bit number is wrong. THIS IS THE READING "
           "THAT MEANS SOMETHING - the one before bring-up does not",
           fails)
    # BMSR must be read twice per link check - it latches low.
    bmsr_reads = [r for _a, r in board.mdio_reads if r == mii["MII_BMSR"]]
    expect(len(bmsr_reads) >= 4,
           "BMSR is a latching-low register and must be read twice per "
           "link check (genphy_update_link, v2025.01_phy.c:284-290); only "
           "%d reads happened in total" % len(bmsr_reads), fails)

    # -- 5b. THE PHY'S LED SOURCES ---------------------------------------
    # Until 2026-08-26 genet.pi4 never wrote a single LED register, so
    # the jack's LEDs stayed dark through a 1000 Mbit/s full-duplex link
    # and fourteen frames the far end counted.  The port looked dead
    # while it worked, which cost an afternoon of credibility.
    #
    # These three MDIO writes are the whole repair, and they are graded
    # by VALUE because the two windows they go through are indirect: a
    # write to register $1C with the wrong selector in bits 14..10 lands
    # in a different shadow register entirely and reports no error, and
    # a write to $15 without the matching $17 first lands wherever the
    # selector happened to be left.  Neither mistake is visible from
    # outside without checking the exact words.
    #
    # The expected values are recomputed here from brcmphy.h's own
    # field definitions rather than copied from genet.pi4, so a wrong
    # shift in the library does not agree with a wrong shift here.
    SHD_REG, EXP_SEL_REG, EXP_DATA_REG = 0x1C, 0x17, 0x15
    SHD_WRITE = 0x8000                      # brcmphy.h:118
    SHD_LEDS1 = 0x0D                        # brcmphy.h:212
    SRC_MULTICOLOR = 0xA                    # brcmphy.h:162
    EXP_MULTICOLOR = 0x0F00 + 0x04          # brcmphy.h:95 + :171
    MC_IN_PHASE = 0x100                     # brcmphy.h:172
    MC_LINK_ACT = 0x0                       # brcmphy.h:173
    # LED1 at bits 3..0 (brcmphy.h:217), LED3 at bits 7..4 (:215).
    leds1_val = (SRC_MULTICOLOR << 0) | (SRC_MULTICOLOR << 4)
    mc_val = MC_IN_PHASE | (MC_LINK_ACT << 0) | (MC_LINK_ACT << 4)

    want_led = [
        (SHD_REG, SHD_WRITE | (SHD_LEDS1 << 10) | leds1_val),
        (EXP_SEL_REG, EXP_MULTICOLOR),
        (EXP_DATA_REG, mc_val),
    ]
    got_led = [(r, v) for _a, r, v in board.mdio_writes]

    def subsequence_at(hay, needle):
        for i in range(len(hay) - len(needle) + 1):
            if hay[i:i + len(needle)] == needle:
                return i
        return -1

    where = subsequence_at(got_led, want_led)
    if where < 0:
        lines = [
            "the PHY's LED sources were never programmed, or were "
            "programmed with the wrong words.  Wanted these three MDIO "
            "writes, consecutively:",
            "        reg $%02X = $%04X  (shadow window: WRITE | LEDS1 "
            "selector $%02X | LED1 = LED3 = MULTICOLOR1)"
            % (want_led[0][0], want_led[0][1], SHD_LEDS1),
            "        reg $%02X = $%04X  (expansion selector: "
            "BCM_EXP_MULTICOLOR)" % (want_led[1][0], want_led[1][1]),
            "        reg $%02X = $%04X  (IN_PHASE | LED1 = LED3 = "
            "LINK_ACT)" % (want_led[2][0], want_led[2][1]),
            "      and the MDIO writes that actually happened were:",
            "        " + ", ".join("$%02X=$%04X" % (r, v)
                                   for r, v in got_led),
            "      See GenetPhyLeds in genet.pi4 and "
            "Linux v6.12 include/linux/brcmphy.h",
        ]
        fails.append(NEWLINE.join(lines))

    # -- 6. the rings ----------------------------------------------------
    end_addr = k["RX_DESCS"] * k["DMA_DESC_SIZE"] // 4 - 1
    ring_bufsz = (k["RX_DESCS"] << k["DMA_RING_SIZE_SHIFT"]) | k["RX_BUF_LENGTH"]
    dma_ctrl_en = (1 << (k["DEFAULT_Q"] + k["DMA_RING_BUF_EN_SHIFT"])) | k["DMA_EN"]
    ring_cfg = 1 << k["DEFAULT_Q"]

    for pfx in ("RDMA", "TDMA"):
        expect(value_of(pfx + "_SCB_BURST_SIZE") == k["DMA_MAX_BURST_LENGTH"],
               "%s_SCB_BURST_SIZE must be DMA_MAX_BURST_LENGTH (%d)"
               % (pfx, k["DMA_MAX_BURST_LENGTH"]), fails)
        expect(value_of(pfx + "_START_ADDR") == 0,
               pfx + "_START_ADDR must be 0", fails)
        expect(value_of(pfx + "_END_ADDR") == end_addr,
               "%s_END_ADDR must be %d - descriptors are counted in 32-bit "
               "WORDS, not bytes" % (pfx, end_addr), fails)
        expect(value_of(pfx + "_RING_BUF_SIZE") == ring_bufsz,
               "%s_RING_BUF_SIZE must be $%08X" % (pfx, ring_bufsz), fails)
        expect(value_of(pfx + "_RING_CFG") == ring_cfg,
               "%s_RING_CFG must enable ring %d only ($%08X)"
               % (pfx, k["DEFAULT_Q"], ring_cfg), fails)
    expect(value_of("RDMA_XON_XOFF_THRESH") == k["DMA_FC_THRESH_VALUE"],
           "RDMA_XON_XOFF_THRESH must be DMA_FC_THRESH_VALUE ($%08X)"
           % k["DMA_FC_THRESH_VALUE"], fails)
    expect(value_of("TDMA_MBUF_DONE_THRESH") == 1,
           "TDMA_MBUF_DONE_THRESH must be 1 (:433)", fails)
    expect(value_of("TDMA_FLOW_PERIOD") == 0,
           "TDMA_FLOW_PERIOD must be 0 (:434)", fails)

    # DMA is disabled before the rings are programmed and enabled after.
    ctrl_writes = [(n, v) for n, v in wr if n.endswith("_CTRL")
                   and n.startswith(("RDMA", "TDMA"))]
    expect(len(ctrl_writes) >= 4,
           "DMA_CTRL must be written to disable and then to enable", fails)
    # Both engines must have been ENABLED with exactly this value at some
    # point. Not "at the end" - the probe stops the interface deliberately
    # and grading the final value would grade the wrong instant.
    for pfx in ("TDMA", "RDMA"):
        enabling = [v for n, v in ctrl_writes
                    if n == pfx + "_CTRL" and (v & k["DMA_EN"])]
        expect(any((v & dma_ctrl_en) == dma_ctrl_en for v in enabling),
               "%s_CTRL was never written with $%08X - DMA_EN plus the "
               "ring-%d enable bit (:264-268). Saw %s"
               % (pfx, dma_ctrl_en, k["DEFAULT_Q"],
                  ["$%08X" % v for v in enabling] or "no enabling write"),
               fails)
    expect(any(n.endswith("_CTRL") and (v & k["DMA_EN"]) == 0
               for n, v in ctrl_writes),
           "the DMA engines must be DISABLED before the rings are "
           "programmed (:486)", fails)
    # ...and disabled again by GenetStop(), with the ring-enable bit
    # left alone: :254-255 is a clrbits of DMA_EN only.
    for pfx in ("TDMA", "RDMA"):
        last = value_of(pfx + "_CTRL")
        expect(last is not None and (last & k["DMA_EN"]) == 0,
               "%s_CTRL must end with DMA_EN clear - GenetStop() left "
               "$%08X" % (pfx, last or 0), fails)
    expect(all_of("UMAC_TX_FLUSH")[:2] == [1, 0],
           "UMAC_TX_FLUSH must be pulsed 1 then 0 (:257-259)", fails)

    # -- 7. the RX descriptors -------------------------------------------
    want_lenstat = (k["RX_BUF_LENGTH"] << k["DMA_BUFLENGTH_SHIFT"]) | k["DMA_OWN"]
    rxregion = said_hex("rx region      ")
    bad_desc = []
    for i in range(k["RX_DESCS"]):
        lenstat, lo, hi = board.rxdesc[i]
        if i == (board.rdma_prod - 1) & 0xFF and board.injected:
            lenstat = want_lenstat        # this one was overwritten by us
        want_buf = rxregion + i * k["RX_BUF_LENGTH"]
        if lo != (want_buf & 0xFFFFFFFF) or hi != (want_buf >> 32):
            bad_desc.append(i)
        elif lenstat != want_lenstat:
            bad_desc.append(i)
    expect(not bad_desc,
           "%d of %d RX descriptors are wrong (first: %s). Each must hold "
           "base + i * RX_BUF_LENGTH split across LO and HI, and "
           "(RX_BUF_LENGTH << 16) | DMA_OWN (:385-394)"
           % (len(bad_desc), k["RX_DESCS"], bad_desc[:1]), fails)
    hi_writes = [t for t in board.desc_trace if t[0] == "W" and t[2] == "HI"]
    expect(len(hi_writes) >= k["RX_DESCS"],
           "ADDRESS_HI must be written for every descriptor even when it "
           "is zero - a stale high half is a DMA write four gigabytes "
           "from anywhere anyone is looking", fails)

    # -- 8. the indices were ADOPTED, not assumed -------------------------
    expect(value_of("RDMA_CONS_INDEX") is not None,
           "RDMA_CONS_INDEX was never written", fails)
    cons_writes = all_of("RDMA_CONS_INDEX")
    expect(cons_writes and cons_writes[0] == 7,
           "RDMA_CONS_INDEX must be aligned onto whatever RDMA_PROD_INDEX "
           "already said (:408-410); the model started it at 7 and the "
           "library wrote %s" % (cons_writes[:1],), fails)
    prod_writes = all_of("TDMA_PROD_INDEX")
    expect(prod_writes and prod_writes[0] == 5,
           "TDMA_PROD_INDEX must be aligned onto TDMA_CONS_INDEX "
           "(:429-431); the model started it at 5 and the library wrote %s"
           % (prod_writes[:1],), fails)

    # -- 9. UMAC_CMD when the interface came up, and after it stopped -----
    # The value that matters is the one in the register at the moment
    # both enables went on, NOT the last write of all - the probe stops
    # the interface at the end on purpose, and looking only at the final
    # value would grade the wrong instant.
    speed_field = k["UMAC_SPEED_1000"] << k["CMD_SPEED_SHIFT"]
    # THE PAUSE PAIR IS PART OF THE EXPECTED VALUE AS OF 2026-09-09, and
    # the two bits come out of unimac.h rather than out of genet.pi4 -
    # this gate reads the vendor's sources, never the library, so the
    # two can still disagree.
    #
    # WHY BOTH BITS MUST BE SET. A UniMAC with CMD_TX_PAUSE_IGNORE clear
    # emits 802.3x PAUSE frames whenever the RX DMA asks, on a link
    # where nothing negotiated flow control; on 2026-09-08 that stopped
    # the bench laptop's Realtek Ethernet card - twelve transmit hangs
    # and then Windows disabled the device. bcmgenet_mac_config sets
    # both bits from priv->rx_pause / priv->tx_pause at
    # v6.12_bcmmii.c:62-66 and this driver's pair is 0/0. $0000000B, the
    # value this gate demanded until that day, is now the FAILURE.
    pause_off = k["CMD_RX_PAUSE_IGNORE"] | k["CMD_TX_PAUSE_IGNORE"]
    cfg_field = speed_field | pause_off
    want_cmd = cfg_field | k["CMD_TX_EN"] | k["CMD_RX_EN"]
    enables = k["CMD_TX_EN"] | k["CMD_RX_EN"]
    running = [v for n, v in wr if n == "UMAC_CMD" and (v & enables) == enables]
    expect(running and running[-1] == want_cmd,
           "when the interface came up UMAC_CMD must have held $%08X - the "
           "speed field, BOTH PAUSE_IGNORE BITS and both enables. Got %s. "
           "If the speed is missing, the final enable was a blind write "
           "instead of setbits (:511) and a gigabit link would run on the "
           "10 Mbit/s encoding, which passes traffic badly rather than "
           "failing. If the two pause bits are missing, the MAC is running "
           "with 802.3x flow control ON in both directions on a link that "
           "negotiated none - the configuration that stopped a laptop's "
           "network card on 2026-09-08."
           % (want_cmd, ["$%08X" % v for v in running] or "no such write"),
           fails)

    # AND THE PAUSE BITS MUST ARRIVE WITH THE SPEED, IN ONE WRITE.
    # bcmgenet_mac_config builds speed, duplex and pause into one
    # cmd_bits value and does a single read-modify-write of UMAC_CMD
    # (v6.12_bcmmii.c:79-90). Two writes would leave a window in which
    # the MAC is configured and flow control is still on, and a gate
    # that only graded the final value could not tell the two apart.
    speed_mask = k["CMD_SPEED_MASK"] << k["CMD_SPEED_SHIFT"]
    cfg_writes = [v for n, v in wr
                  if n == "UMAC_CMD" and (v & speed_mask) == speed_field]
    expect(cfg_writes and all((v & pause_off) == pause_off for v in cfg_writes),
           "every UMAC_CMD write carrying the speed field must carry both "
           "PAUSE_IGNORE bits in the SAME write. Got %s. A second write to "
           "add them afterwards leaves the MAC configured with flow "
           "control on in between."
           % (["$%08X" % v for v in cfg_writes] or "no such write"), fails)

    expect(value_of("UMAC_CMD") == cfg_field,
           "after GenetStop() UMAC_CMD must hold $%08X - the enables "
           "cleared and the SPEED FIELD AND BOTH PAUSE BITS INTACT. Got "
           "$%08X. Stop is a clrbits of two bits (:676), not a write; "
           "clobbering the rest here is invisible until somebody restarts "
           "the interface."
           % (cfg_field, value_of("UMAC_CMD") or 0), fails)

    # -- 9a. THE PHY'S PAUSE ADVERTISEMENT, AND THE LINK LEFT ALONE -------
    # The model's PHY comes up advertising no pause, which is what this
    # board's PHY does out of reset. GenetPhyPauseSet() must therefore
    # READ MII_ADVERTISE, find nothing to change, and WRITE NOTHING -
    # genphy_config_aneg's own rule at v2025.01_phy.c:182-216, "only
    # restart aneg if we are advertising something different than we
    # were before".
    #
    # THIS IS THE ASSERTION THAT KEEPS A LINK FLAP OUT OF THE BRING-UP.
    # Restarting negotiation takes a gigabit link down for seconds, and a
    # partner whose transmit is cut off over and over is the OTHER way to
    # produce the tx hang this whole change is about. A driver that
    # restarted unconditionally would pass every value check above.
    adv_writes = [v for _a, r, v in board.mdio_writes
                  if r == mii["MII_ADVERTISE"]]
    bmcr_writes = [v for _a, r, v in board.mdio_writes if r == mii["MII_BMCR"]]
    expect(any(r == mii["MII_ADVERTISE"] for _a, r in board.mdio_reads),
           "MII_ADVERTISE was never read. GenetPhyPauseSet() has to look "
           "at what the PHY advertises before it can leave it alone, and a "
           "bring-up that never looks cannot know whether this board is "
           "promising a partner a pause capability the MAC refuses to "
           "honour.", fails)
    expect(not adv_writes,
           "MII_ADVERTISE was written %s on a PHY that already advertises "
           "no pause. genphy_config_advert writes only when the value "
           "changes (v2025.01_phy.c:41-120) and this one did not."
           % (["$%04X" % v for v in adv_writes],), fails)
    expect(not bmcr_writes,
           "BMCR was written %s during an ordinary bring-up. Nothing in "
           "genet.pi4 may restart auto-negotiation unless the "
           "advertisement actually changed: a restart drops a gigabit link "
           "for seconds, and a link that keeps going away under a partner "
           "mid-transmit is the second way to hang its transmit queue."
           % (["$%04X" % v for v in bmcr_writes],), fails)
    expect(said_hex("pause bits set ") == pause_off,
           "GenetPauseApplied() says $%08X went into UMAC_CMD; want $%08X, "
           "CMD_RX_PAUSE_IGNORE | CMD_TX_PAUSE_IGNORE"
           % (said_hex("pause bits set ") or 0, pause_off), fails)
    adv_seen = said_hex("phy advertise  ")
    expect(adv_seen is not None and
           (adv_seen & (mii["ADVERTISE_PAUSE_CAP"] |
                        mii["ADVERTISE_PAUSE_ASYM"])) == 0,
           "the PHY is advertising $%04X, which claims a pause capability "
           "this MAC is configured to ignore. What this board says on the "
           "wire and what its MAC will do have to agree."
           % (adv_seen or 0), fails)

    # -- 9c. THE MIB COUNTERS LAND ON THE VENDOR'S OFFSETS ----------------
    # Graded BY NAME out of the read trace, not by value. Every counter
    # reads zero on a healthy link, so a library that computed one of
    # these offsets wrongly would read zero off the WRONG counter and
    # look perfectly right. The model names each offset from Linux's own
    # structures (parse_mib_layout), gap and all, so a wrong offset
    # either shows up here as the wrong name having been read or lands
    # on nothing at all and the model refuses with "unmodelled MMIO".
    want_mib = ["MIB_" + n for n in
                ("tx.pf", "rx.pf", "tx.pkts", "rx.pkt", "rx.fcs", "rx.aln",
                 "rx.flr", "rx.ovr", "rx.jbr", "tx.fcs", "tx.ovr", "tx.lcl",
                 "tx.ecl")]
    want_mib += ["RBUF_OVFL_CNT", "RBUF_ERR_CNT", "UMAC_MDF_ERR_CNT"]
    seen = set(board.reads)
    missing = [n for n in want_mib if n not in seen]
    expect(not missing,
           "the probe never read %s. Those are the statistics registers "
           "the vendor's own structures put at those offsets, and a "
           "counter nothing reads cannot say what the MAC did."
           % (", ".join(missing) or "-"), fails)
    strays = sorted(n for n in seen
                    if n.startswith("MIB_") and n not in want_mib)
    expect(not strays,
           "the probe read %s - a MIB counter genet.pi4 does not mean to "
           "read. One of its offsets is wrong and has landed on a "
           "neighbouring counter, which reads zero and looks correct."
           % (", ".join(strays)), fails)
    expect(said_dec("tx pause frames") == 0,
           "the MAC counted %s PAUSE frames TRANSMITTED. With "
           "CMD_TX_PAUSE_IGNORE set this must be zero: a PAUSE frame out "
           "of this board is what stopped the bench laptop's Ethernet "
           "card on 2026-09-08." % (said_dec("tx pause frames"),), fails)
    expect(said_dec("bring-ups      ") == 1,
           "GenetStartCount() says %s. One probe run brings the interface "
           "up exactly once; more than that means something is rebuilding "
           "the MAC behind the caller's back."
           % (said_dec("bring-ups      "),), fails)
    expect(said_dec("aneg restarts  ") == 0,
           "GenetAnegRestarts() says %s on a PHY that already advertised "
           "what this driver wants. Negotiation was restarted for nothing, "
           "and every restart is seconds of link down under a partner that "
           "may be transmitting."
           % (said_dec("aneg restarts  "),), fails)

    # -- 9b. the register window the probe reads BACK off the bus ---------
    # These are not duplicates of the checks above. Everything above
    # grades what the library WROTE, taken from the bus trace. These
    # grade what the probe PRINTED after reading the block back, and
    # that is the only part a human staring at a serial log ever sees.
    # A diagnostic that reads the wrong register prints a plausible
    # number and no write-trace assertion can notice.
    oob_raw = said_hex("OOB raw        ")
    want_oob_on = k["RGMII_LINK"] | k["RGMII_MODE_EN"] | k["ID_MODE_DIS"]
    expect(oob_raw is not None and (oob_raw & want_oob_on) == want_oob_on
           and (oob_raw & k["OOB_DISABLE"]) == 0,
           "EXT_RGMII_OOB_CTRL read back as $%08X after bring-up. It must "
           "have RGMII_LINK | RGMII_MODE_EN | ID_MODE_DIS set and "
           "OOB_DISABLE clear (:461-466). Without RGMII_LINK the MAC "
           "believes the line is down: it will still transmit, and it "
           "will not receive." % (oob_raw if oob_raw is not None else 0),
           fails)
    expect(said_hex("UMAC_CMD raw   ") == want_cmd,
           "UMAC_CMD read back as $%08X after bring-up, want $%08X - the "
           "speed field and both enables"
           % (said_hex("UMAC_CMD raw   ") or 0, want_cmd), fails)
    for pfx in ("RDMA", "TDMA"):
        got = said_hex("%s_CTRL raw  " % pfx)
        expect(got == dma_ctrl_en,
               "%s_CTRL read back as $%08X after bring-up, want $%08X - "
               "DMA_EN plus the ring-%d enable (:264-268)"
               % (pfx, got or 0, dma_ctrl_en, k["DEFAULT_Q"]), fails)
    expect(said_dec("RX discards    ") == 0,
           "the RX ring reported %s discarded frames before anything was "
           "even sent. The discard count is the top half of "
           "RDMA_PROD_INDEX (v6.12_bcmgenet.h:341-342) and a non-zero "
           "value there means frames reached the MAC and the ring threw "
           "them away" % said_dec("RX discards    "), fails)
    prod_raw = said_hex("RX prod raw    ")
    cons_raw = said_hex("RX cons raw    ")
    expect(prod_raw is not None and cons_raw is not None and
           (prod_raw & 0xFFFF) == (cons_raw & 0xFFFF) ==
           said_dec("RX cIndex ours "),
           "before any traffic the RX producer index ($%08X), the "
           "consumer index ($%08X) and the library's own idea of the "
           "consumer index (%s) must all agree. They are aligned onto "
           "whatever the hardware already had (:408-410); a disagreement "
           "here means the library is counting from somewhere else"
           % (prod_raw or 0, cons_raw or 0, said_dec("RX cIndex ours ")),
           fails)

    # -- 10. the frame that left -------------------------------------------
    expect(len(board.sent) == 1,
           "exactly one frame should have been transmitted, saw %d"
           % len(board.sent), fails)
    if board.sent:
        f = board.sent[0]
        expect(len(f) == 60,
               "the transmitted frame is %d bytes, want 60" % len(f), fails)
        expect(f[0:6] == b"\xff" * 6,
               "the destination should be broadcast", fails)
        mac0 = said_hex("UMAC_MAC0 image")
        mac1 = said_hex("UMAC_MAC1 image")
        want_src = mac0.to_bytes(4, "big") + (mac1 & 0xFFFF).to_bytes(2, "big")
        expect(f[6:12] == want_src,
               "the source address on the wire (%s) is not the one written "
               "into UMAC_MAC0/MAC1 (%s)" % (f[6:12].hex(), want_src.hex()),
               fails)
        expect(value_of("UMAC_MAC0") == mac0 and value_of("UMAC_MAC1") == mac1,
               "UMAC_MAC0/MAC1 on the bus do not match what the library "
               "said it built (:243-247)", fails)

    # the TX descriptor's flag word, composed from the parsed macros
    want_flags = ((0x3F << k["DMA_TX_QTAG_SHIFT"]) | k["DMA_TX_APPEND_CRC"] |
                  k["DMA_SOP"] | k["DMA_EOP"])
    want_lenstat_tx = (60 << k["DMA_BUFLENGTH_SHIFT"]) | want_flags
    txi = board.tdma_cons and 5
    expect(board.txdesc[txi][0] == want_lenstat_tx,
           "TX descriptor %d holds $%08X, want $%08X "
           "((len << 16) | ($3F << QTAG) | APPEND_CRC | SOP | EOP, :290-296)"
           % (txi, board.txdesc[txi][0], want_lenstat_tx), fails)

    # ordering: LO, HI, LEN, then the producer index
    seq = [s for s in board.order
           if s.startswith(f"txdesc{txi}:") or s.startswith("w:TDMA_PROD_INDEX")]
    tail = [s.split(":")[-1].split("=")[0] for s in seq[-4:]]
    expect(tail[:3] == ["LO", "HI", "LEN"],
           "the TX descriptor must be written address-first and "
           "length/status LAST (:294-296); got %s" % (tail[:3],), fails)
    expect(len(seq) >= 4 and tail[3] == "TDMA_PROD_INDEX",
           "TDMA_PROD_INDEX must be written AFTER the whole descriptor - "
           "it is what starts the transmission. The tail of the sequence "
           "was %s" % (tail,), fails)

    # -- 11. the frame that arrived ----------------------------------------
    # THE RECEIVER MUST KEEP LOOKING. The model deliberately does not
    # answer until the library has polled RX_ANSWER_AFTER_POLLS times -
    # see the note there. A receive stage bounded by a poll count
    # instead of by a clock fails here, which is exactly what the eight-
    # iteration loop that shipped to silicon on 2026-08-26 would do.
    expect(board.injected is not None,
           "the model never got to inject a frame. It answers only after "
           "%d polls of RDMA_PROD_INDEX and the library managed %d, so "
           "the receive path gave up early. A LOOP COUNT IS NOT A "
           "DURATION - a bare N-iteration poll of GenetRecv() is "
           "microseconds of listening, and the traffic it is waiting for "
           "arrives in seconds. Use GenetRecvWait()."
           % (RX_ANSWER_AFTER_POLLS, board.rx_polls), fails)
    listened = said_dec("listen ms      ")
    expect(listened is not None and listened >= 1000,
           "the receive stage listened for %s ms. Unsolicited traffic on "
           "a quiet switch port - an ARP, a spanning-tree hello - arrives "
           "on the order of seconds; anything under a second cannot "
           "distinguish 'nothing arrived' from 'we did not wait'"
           % listened, fails)
    n = said_dec("bytes          ")
    expect(n == INJECT_PAYLOAD_LEN,
           "the received length should be %d - the descriptor reported %d "
           "and RX_BUF_OFFSET (%d) is the RBUF_ALIGN_2B pad the hardware "
           "inserted (:354-356). Got %s"
           % (INJECT_PAYLOAD_LEN, INJECT_PAYLOAD_LEN + k["RX_BUF_OFFSET"],
              k["RX_BUF_OFFSET"], n), fails)
    expect(said_hex("ethertype      ") == INJECT_ETHERTYPE,
           "the EtherType read back is not the one injected - the two pad "
           "bytes were probably not skipped", fails)
    # Guarded, because "the model never answered" is now a REACHABLE
    # failure rather than an impossible one - it is the whole point of
    # RX_ANSWER_AFTER_POLLS - and a gate that crashes instead of
    # reporting is a gate that gets ignored.
    expect(board.injected is not None and
           said_hex("dst[0]         ") == board.injected[0],
           "the first byte of the received frame is wrong", fails)
    expect(len(cons_writes) >= 2 and
           (cons_writes[-1] - cons_writes[0]) & 0xFFFF == 1,
           "RDMA_CONS_INDEX must advance by exactly one per frame consumed "
           "(:369-370); it went %s" % (cons_writes,), fails)
    expect(said_dec("rx count       ") == 1, "one frame received", fails)
    expect(said_dec("tx count       ") == 1, "one frame transmitted", fails)

    # -- 11b. the live register dump taken before anything stopped --------
    # Step 7b of the probe reads the whole block back while the MAC is
    # still running. It exists because the refusal suite ends by calling
    # GenetStop(), so this is the last instant at which any of these
    # values still describes a working interface. The assertions here
    # are on the PRINTED numbers, which is what a person debugging from
    # a serial log actually has in front of them.
    expect(said_hex("port mode      ") == k["PORT_MODE_EXT_GPHY"],
           "the port mode reads $%08X while the interface is up, want "
           "$%08X (PORT_MODE_EXT_GPHY, :43). The board reads ZERO here "
           "at reset - measured 2026-08-26 - so this is not inherited "
           "from firmware and a zero means the write never happened"
           % (said_hex("port mode      ") or 0, k["PORT_MODE_EXT_GPHY"]),
           fails)
    live_oob = said_hex("rgmii oob ctrl ")
    expect(live_oob is not None and (live_oob & 0x00F00000) == 0x00F00000
           and (live_oob & want_oob_on) == want_oob_on
           and (live_oob & k["OOB_DISABLE"]) == 0,
           "the live RGMII out-of-band control register reads $%08X. It "
           "must still carry the four measured reset bits ($00F00000), "
           "must have RGMII_LINK, RGMII_MODE_EN and ID_MODE_DIS set, and "
           "must have OOB_DISABLE clear" % (live_oob or 0), fails)
    expect(said_hex("umac command   ") == want_cmd,
           "the live UniMAC command register reads $%08X, want $%08X"
           % (said_hex("umac command   ") or 0, want_cmd), fails)
    expect(said_hex("station addr hi") == said_hex("UMAC_MAC0 image") and
           said_hex("station addr lo") == said_hex("UMAC_MAC1 image"),
           "the station address in the hardware ($%08X $%08X) is not the "
           "one this program built ($%08X $%08X). A MAC filtering on the "
           "wrong address, or on all zeros, accepts nothing and the only "
           "symptom is a silent receive path"
           % (said_hex("station addr hi") or 0, said_hex("station addr lo") or 0,
              said_hex("UMAC_MAC0 image") or 0, said_hex("UMAC_MAC1 image") or 0),
           fails)
    expect(said_hex("rbuf control   ") is not None and
           (said_hex("rbuf control   ") & k["RBUF_ALIGN_2B"]),
           "the live receive buffer control register does not have "
           "RBUF_ALIGN_2B set. The receive path skips two pad bytes on "
           "the strength of that bit; without it every frame is silently "
           "shifted by two", fails)
    for label, want in (("rx ring config ", ring_cfg),
                        ("tx ring config ", ring_cfg),
                        ("rx dma control ", dma_ctrl_en),
                        ("tx dma control ", dma_ctrl_en)):
        expect(said_hex(label) == want,
               "the live %s reads $%08X, want $%08X"
               % (label.strip(), said_hex(label) or 0, want), fails)
    expect(said_dec("rx discarded   ") == 0,
           "the receive ring discarded %s frames. That is the top half "
           "of RDMA_PROD_INDEX (v6.12_bcmgenet.h:341-342), and non-zero "
           "means frames DID reach the MAC and the ring threw them away "
           "- a different fault entirely from nothing arriving"
           % said_dec("rx discarded   "), fails)
    expect(said_dec("mac link now   ") == 1,
           "the MAC's link indication reads 0 AFTER traffic, having read "
           "1 immediately after bring-up. That means it was set and then "
           "lost, which is a different bug from never having been set "
           "and has a different fix - which is the whole reason this "
           "reading is taken three times", fails)

    # -- 12. nothing landed where nothing should ---------------------------
    expect(not board.forbidden_writes,
           "the library WROTE a register the cited driver never writes: %s. "
           "SYS_TBUF_FLUSH_CTRL is the TX twin of a register the reset "
           "sequence uses and touching it is a guess; UMAC_MODE has one "
           "source on this whole disk and must be read, never steered on."
           % (board.forbidden_writes,), fails)

    # -- 13. the refusals, against the probe's own declared expectations ---
    # The probe prints "(want -13)" beside each; nothing here transcribes
    # a refusal code, so the two files cannot drift into agreement.
    declared = re.findall(r"\(want\s*(-?\d+)\)\s+(-?\d+)", text)
    expect(len(declared) >= 12,
           "the probe printed only %d declared expectations; the refusal "
           "section did not run" % len(declared), fails)
    for want, got in declared:
        expect(int(want) == int(got),
               "a declared expectation failed: wanted %s, got %s" % (want, got),
               fails)
    # And they must be DISTINCT codes, or the library is collapsing
    # different faults into one.
    codes = {int(w) for w, _g in declared if int(w) < 0}
    expect(len(codes) >= 4,
           "the refusals all report the same code (%s) - different faults "
           "must be distinguishable" % (sorted(codes),), fails)

    expect(said_dec("addr is wide   (want 1)  ") == 1,
           "the 64-bit canary failed - this build truncates addresses "
           "above 4 GiB and a DMA buffer up there would be handed to the "
           "controller as its low half", fails)


# ---------------------------------------------------------------------
#  SECOND PASS: THE SAME IMAGE, A HALF-DUPLEX LINK
# ---------------------------------------------------------------------
#  The loudest refusal in genet.pi4 is the one it makes when the link
#  negotiates half duplex, and the first pass cannot exercise it - a
#  full-duplex link never reaches it. So the identical image is run
#  again against a PHY that advertises only 1000BASE-T HALF on both
#  sides, and the refusal is watched happening.
#
#  A refusal nobody has ever seen fire is a comment, not a refusal.
def half_duplex_pass(img, k, mii, base, size, phy_addr, fails):
    _cpu, half = run(img, lambda c: Genet(c, k, base, size, phy_addr, mii,
                                          half_duplex=True))
    htext = half.uart.decode("utf-8", "replace")

    def hsaid(label):
        m = re.search(re.escape(label) + r"\s+(-?\d+)", htext)
        return int(m.group(1)) if m else None

    expect(hsaid("full duplex    ") == 0,
           "the half-duplex pass still resolved FULL duplex - the AND of "
           "CTRL1000 and STAT1000 is not being computed", fails)
    expect(hsaid("speed Mbit/s   ") == 1000,
           "the half-duplex pass should still resolve 1000 Mbit/s", fails)
    expect(hsaid("start ok       ") == 0,
           "GenetStart() SUCCEEDED on a half-duplex link. The cited driver "
           "never writes CMD_HD_EN, so the MAC would be left full-duplex "
           "on a half-duplex wire - collisions and terrible throughput, "
           "with no error anywhere", fails)
    expect("HALF duplex" in htext,
           "the half-duplex refusal did not print its reason - "
           "GenetErrorText() must explain itself, not just return a number",
           fails)
    enables = k["CMD_TX_EN"] | k["CMD_RX_EN"]
    expect(not any(n == "UMAC_CMD" and (v & enables) for n, v in half.writes),
           "the MAC was ENABLED on a half-duplex link", fails)
    expect(not any(n == "EXT_RGMII_OOB_CTRL" for n, _v in half.writes),
           "EXT_RGMII_OOB_CTRL was written before the duplex was checked - "
           "the refusal must come first, or the RGMII block is left half "
           "configured for a link that was then rejected", fails)
    return half, htext


# ---------------------------------------------------------------------
#  THIRD PASS: A PHY THAT COMES UP ALREADY ADVERTISING PAUSE
# ---------------------------------------------------------------------
#  The first pass proves genet.pi4 leaves a correct advertisement alone,
#  which is the ordinary case and is most of the value - it is what keeps
#  a link flap out of every bring-up. It cannot prove the other half:
#  that a PHY left claiming a pause capability by a previous boot, by the
#  firmware, or by anything else that ran before us gets CORRECTED.
#
#  Both halves matter and they fail in opposite directions. A driver that
#  never writes passes the first pass and leaves the board lying to its
#  partner; a driver that always writes passes this one and renegotiates
#  the link on every command. Only the two together say the rule is the
#  vendor's - write when it changed, and only then.
def pause_advertised_pass(img, k, mii, base, size, phy_addr, fails):
    _cpu, brd = run(img, lambda c: Genet(c, k, base, size, phy_addr, mii,
                                         pause_advertised=True))
    ptext = brd.uart.decode("utf-8", "replace")
    pause_bits = mii["ADVERTISE_PAUSE_CAP"] | mii["ADVERTISE_PAUSE_ASYM"]

    def psaid(label):
        m = re.search(re.escape(label) + r"\s+(-?\d+)", ptext)
        return int(m.group(1)) if m else None

    def phex(label):
        m = re.search(re.escape(label) + r"\s+\$?([0-9A-Fa-f]+)", ptext)
        return int(m.group(1), 16) if m else None

    adv = [v for _a, r, v in brd.mdio_writes if r == mii["MII_ADVERTISE"]]
    bmcr = [v for _a, r, v in brd.mdio_writes if r == mii["MII_BMCR"]]
    expect(len(adv) == 1,
           "a PHY advertising Pause and Asym_Pause must have MII_ADVERTISE "
           "written EXACTLY ONCE; it was written %d times %s"
           % (len(adv), ["$%04X" % v for v in adv]), fails)
    expect(adv and (adv[-1] & pause_bits) == 0,
           "MII_ADVERTISE was rewritten as $%04X and still claims a pause "
           "capability. This driver ignores every PAUSE frame it receives "
           "and emits none, so advertising one is a lie the partner acts "
           "on." % (adv[-1] if adv else 0), fails)
    expect(adv and (adv[-1] & ~pause_bits) ==
           (mii["ADVERTISE_CSMA"] | mii["ADVERTISE_10HALF"] |
            mii["ADVERTISE_10FULL"] | mii["ADVERTISE_100HALF"] |
            mii["ADVERTISE_100FULL"]),
           "MII_ADVERTISE was rewritten as $%04X and lost bits that are "
           "nothing to do with pause. genphy_config_advert clears only the "
           "fields it owns; the speed advertisement is not one of this "
           "procedure's." % (adv[-1] if adv else 0), fails)
    expect(len(bmcr) == 1 and (bmcr[0] & mii["BMCR_ANRESTART"]) and
           (bmcr[0] & mii["BMCR_ANENABLE"]) and
           not (bmcr[0] & mii["BMCR_ISOLATE"]),
           "after changing the advertisement the driver must restart "
           "auto-negotiation exactly once, with ANENABLE set and ISOLATE "
           "clear (genphy_restart_aneg, v2025.01_phy.c:155-170). BMCR "
           "writes were %s" % (["$%04X" % v for v in bmcr],), fails)
    expect(psaid("aneg restarts  ") == 1,
           "GenetAnegRestarts() says %s after one necessary restart"
           % (psaid("aneg restarts  "),), fails)
    expect(phex("phy advertise  ") is not None and
           (phex("phy advertise  ") & pause_bits) == 0,
           "after the correction the PHY still advertises $%04X"
           % (phex("phy advertise  ") or 0), fails)
    expect(psaid("start ok       ") == 1,
           "the interface did not come up on a PHY whose advertisement "
           "had to be corrected. Correcting it must not cost the link.",
           fails)
    return brd, ptext


# =====================================================================
#  MUTATION - proof the gate can go red
# =====================================================================
MUTATIONS = [
    ("the final enable written blind instead of setbits",
     "If genet_Modify(#GENET_UMAC_CMD, 0, #GENET_CMD_TX_EN | #GENET_CMD_RX_EN) = 0",
     "If genet_Poke(#GENET_UMAC_CMD, #GENET_CMD_TX_EN | #GENET_CMD_RX_EN) = 0"),
    ("the PHY's LED sources never programmed",
     "  GenetPhyLeds()",
     "  ; the LED programming, removed by a mutation"),

    ("the LED shadow selector written without the WRITE bit",
     "  v = #GENET_PHY_SHD_WRITE" + MUTNL +
     "  v = v | ((sel & #GENET_PHY_SHD_SEL_MASK) << #GENET_PHY_SHD_SEL_SHIFT)",
     "  v = 0" + MUTNL +
     "  v = v | ((sel & #GENET_PHY_SHD_SEL_MASK) << #GENET_PHY_SHD_SEL_SHIFT)"),

    ("MDIO command and START_BUSY collapsed into one write",
     "  cmd = cmd | ((reg & #GENET_MDIO_REG_MASK) << #GENET_MDIO_REG_SHIFT)\n"
     "  If genet_Poke(#GENET_MDIO_CMD, cmd) = 0\n"
     "    ProcedureReturn genet_err\n"
     "  EndIf",
     "  cmd = cmd | ((reg & #GENET_MDIO_REG_MASK) << #GENET_MDIO_REG_SHIFT)\n"
     "  If genet_Poke(#GENET_MDIO_CMD, cmd | #GENET_MDIO_START_BUSY) = 0\n"
     "    ProcedureReturn genet_err\n"
     "  EndIf"),
    ("RBUF_CTRL written blind instead of read-modify-write",
     "If genet_Modify(#GENET_RBUF_CTRL, 0, #GENET_RBUF_ALIGN_2B) = 0",
     "If genet_Poke(#GENET_RBUF_CTRL, #GENET_RBUF_ALIGN_2B) = 0"),
    # The one that matters most, because it is the refusal a future
    # reader is most likely to delete as over-cautious.
    ("the half-duplex refusal deleted",
     "  If genet_fullDuplex = 0\n"
     "    genet_err = #GENET_ERR_HALF_DUPLEX\n"
     "    ProcedureReturn 0\n"
     "  EndIf",
     "  ; the refusal, removed by a mutation"),
    # THE ONE THE GATE COULD NOT CATCH UNTIL 2026-08-26. Dropping
    # RGMII_LINK leaves the MAC believing the line is down: it still
    # transmits - a MAC will happily send into a link it thinks is dead -
    # and it never receives. That is the exact shape of the first
    # silicon report, and it was the leading hypothesis for it. The
    # model used to hold MODE_LINK_STATUS at a constant 1 and the probe
    # never read EXT_RGMII_OOB_CTRL back, so this mutation would have
    # sailed straight through. It now fails twice over: the derived
    # MAC-side link bit reads 0 after bring-up, and the raw OOB readback
    # is missing the bit.
    ("RGMII_LINK dropped from GenetAdjustLink - the MAC never told "
     "there is a link",
     "If genet_Modify(#GENET_EXT_RGMII_OOB_CTRL, #GENET_OOB_DISABLE, "
     "#GENET_RGMII_LINK | #GENET_RGMII_MODE_EN) = 0",
     "If genet_Modify(#GENET_EXT_RGMII_OOB_CTRL, #GENET_OOB_DISABLE, "
     "#GENET_RGMII_MODE_EN) = 0"),
    # Only catchable since the board's reset value was measured. The
    # model used to preload an INVENTED foreign bit here; now it
    # preloads the real $00F00000, four bits set by the hardware that
    # neither U-Boot nor Linux names. A blind write clears all four.
    ("EXT_RGMII_OOB_CTRL written blind - the four unnamed hardware bits "
     "at 20-23 lost",
     "If genet_Modify(#GENET_EXT_RGMII_OOB_CTRL, #GENET_OOB_DISABLE, "
     "#GENET_RGMII_LINK | #GENET_RGMII_MODE_EN) = 0",
     "If genet_Poke(#GENET_EXT_RGMII_OOB_CTRL, "
     "#GENET_RGMII_LINK | #GENET_RGMII_MODE_EN) = 0"),
    # THE 2026-09-09 PAIR. Both of these restore the exact configuration
    # that stopped the bench laptop's Ethernet card on 2026-09-08, and
    # both are the sort of change a later reader makes while tidying: one
    # deletes two bits from a register write that "already works", the
    # other deletes a call that "writes nothing anyway".
    ("the PAUSE_IGNORE bits dropped from the UMAC_CMD write - 802.3x "
     "flow control back ON, in both directions, on a link that "
     "negotiated none",
     "  If genet_Poke(#GENET_UMAC_CMD, (speed << #GENET_CMD_SPEED_SHIFT) | pause) = 0",
     "  If genet_Poke(#GENET_UMAC_CMD, speed << #GENET_CMD_SPEED_SHIFT) = 0"),
    ("the pause advertisement never settled - the PHY left claiming "
     "whatever it came up with",
     "\n  GenetPhyPauseSet()\n",
     "\n  ; the pause advertisement, removed by a mutation\n"),
    ("the TX descriptor armed before its address is written",
     "  If genet_Poke(d + #GENET_DESC_ADDRESS_LO, addr & $FFFFFFFF) = 0\n"
     "    ProcedureReturn 0\n"
     "  EndIf\n"
     "  If genet_Poke(d + #GENET_DESC_ADDRESS_HI, (addr >> 32) & $FFFFFFFF) = 0\n"
     "    ProcedureReturn 0\n"
     "  EndIf\n"
     "  If genet_Poke(d + #GENET_DESC_LENGTH_STATUS, lenStat) = 0\n"
     "    ProcedureReturn 0\n"
     "  EndIf",
     "  If genet_Poke(d + #GENET_DESC_LENGTH_STATUS, lenStat) = 0\n"
     "    ProcedureReturn 0\n"
     "  EndIf\n"
     "  If genet_Poke(d + #GENET_DESC_ADDRESS_LO, addr & $FFFFFFFF) = 0\n"
     "    ProcedureReturn 0\n"
     "  EndIf\n"
     "  If genet_Poke(d + #GENET_DESC_ADDRESS_HI, (addr >> 32) & $FFFFFFFF) = 0\n"
     "    ProcedureReturn 0\n"
     "  EndIf"),
]


def mutate_run(name, old, new, k, mii, base, phy_addr) -> bool:
    """Returns True if the gate went red, which is what we want.

    The mutant is a COPY of genet.pi4 in a temporary directory, included by
    a copy of the probe by absolute path; nothing in the tree is written.
    old == new == "" is the control, which must come back GREEN.
    """
    src = LIB.read_text(encoding="utf-8", errors="replace")
    if old and src.count(old) != 1:
        print("   ANCHOR BROKEN - the anchor text appears %d times in "
              "genet.pi4; repair the anchor, do not delete the mutation"
              % src.count(old))
        return False
    with tempfile.TemporaryDirectory(prefix="genetcheck-mut-") as td:
        work = pathlib.Path(td)
        mut_lib = work / "genet_mut.pi4"
        mut_lib.write_text(src.replace(old, new) if old else src, encoding="utf-8")

        inc = 'XIncludeFile "RaspberryPi4/Lib/genet.pi4"'
        probe = PROBE.read_text(encoding="utf-8", errors="replace")
        if probe.count(inc) != 1:
            raise SystemExit("pi4GenetProbe.pi4 no longer includes "
                             "RaspberryPi4/Lib/genet.pi4 exactly once, so the "
                             "mutation harness cannot substitute a mutant.")
        mut_probe = work / "genetprobe_mut.pi4"
        mut_probe.write_text(
            probe.replace(inc, 'XIncludeFile "%s"' % mut_lib.as_posix()),
            encoding="utf-8")

        img = work / "genetcheck_mut.img"
        try:
            build(mut_probe, img)
            _cpu, board = run(img, lambda c: Genet(c, k, base, 0x10000, phy_addr, mii))
            fails: list[str] = []
            check(board, board.uart.decode("utf-8", "replace"), k, mii,
                  base, phy_addr, fails)
            # The half-duplex pass too, or the mutation that deletes the
            # duplex refusal would sail through.
            half_duplex_pass(img, k, mii, base, 0x10000, phy_addr, fails)
            # And the pause-advertised pass, for the same reason.
            pause_advertised_pass(img, k, mii, base, 0x10000, phy_addr, fails)
            return bool(fails)
        except SystemExit as e:
            # The model refusing to run the mutated code counts as red -
            # that is the "unmodelled MMIO" path doing its job.
            print("   (the model refused it: %s)" % str(e).splitlines()[0][:90])
            return True


# =====================================================================
def main(argv: list[str] | None = None) -> int:
    global COMPILER
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="PureMetalForge.exe (default: $PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true",
                    help="prove the gate can fail, by breaking the library")
    args = ap.parse_args(argv); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    if not args.compiler:
        ap.error("No compiler was named. Pass --compiler with the path to "
                 "PureMetalForge.exe, or set PMF_COMPILER.")
    COMPILER = args.compiler

    # THE TABLES ARE KEPT APART ON PURPOSE. Merging unimac.h into the
    # driver's table looks harmless and is not: unimac.h defines UMAC_CMD as
    # $008, the offset WITHIN the UMAC block, while the driver defines it as
    # GENET_UMAC_OFF + 0x008 = $808, the offset within the whole register
    # file. Both are correct in their own frame of reference, and one
    # silently shadowing the other would move every UMAC register 2 KiB.
    k = Macros(pinned(UBOOT_BCMGENET))
    uni = Macros(pinned(LINUX_UNIMAC_H))
    mii = Macros(pinned(LINUX_MII_H))
    k["UMAC_MODE"] = uni["UMAC_MODE"]
    k["MODE_LINK_STATUS"] = uni["MODE_LINK_STATUS"]
    # The two PAUSE_IGNORE bits are defined in unimac.h and nowhere in
    # U-Boot's driver, which is why they are lifted one at a time the way
    # UMAC_MODE is rather than by merging the tables. Their MEANING is
    # attested in Linux's driver - bcmgenet_get_pauseparam reports tx_pause
    # as !(cmd & CMD_TX_PAUSE_IGNORE) at bcmgenet.c:933, and
    # bcmgenet_mac_config builds the same pair at bcmmii.c:56-66.
    k["CMD_RX_PAUSE_IGNORE"] = uni["CMD_RX_PAUSE_IGNORE"]
    k["CMD_TX_PAUSE_IGNORE"] = uni["CMD_TX_PAUSE_IGNORE"]
    base, size = dtsi_genet_base()
    phy_addr = dts_phy_address()

    print("constants, resolved from the pinned %s definitions:" % DRIVER_NAME)
    for n in ("SYS_PORT_CTRL", "EXT_RGMII_OOB_CTRL", "UMAC_CMD", "MDIO_CMD",
              "GENET_RX_OFF", "RDMA_RING_REG_BASE", "RDMA_REG_BASE",
              "GENET_TX_OFF", "TDMA_RING_REG_BASE", "TDMA_REG_BASE",
              "ENET_MAX_MTU_SIZE", "DMA_FC_THRESH_VALUE"):
        print("   %-22s $%08X  (%d)" % (n, k[n], k[n]))
    print("   %-22s $%08X   (bcm2711.dtsi, translated)" % ("block base", base))
    print("   %-22s %d          (bcm2711-rpi-4-b.dts)" % ("PHY address", phy_addr))
    print()

    with tempfile.TemporaryDirectory(prefix="genetcheck-") as td:
        img = pathlib.Path(td) / "genetcheck.img"
        build(PROBE, img)
        _cpu, board = run(img, lambda c: Genet(c, k, base, size, phy_addr, mii))
        text = board.uart.decode("utf-8", "replace")
        print(text.rstrip())
        print()
        print("register traffic: %d writes, %d reads, %d MDIO transactions, "
              "%d frames out, %d in"
              % (len(board.writes), len(board.reads),
                 len(board.mdio_cmd_trace) // 2, len(board.sent),
                 1 if board.injected else 0))
        print()

        fails: list[str] = []
        check(board, text, k, mii, base, phy_addr, fails)

        print("second pass: the same image against a HALF-duplex link")
        half, htext = half_duplex_pass(img, k, mii, base, size, phy_addr, fails)
        m = re.search(r"->\s*(genet: REFUSED[^\r\n]*)", htext)
        print("   start refused: %s" % (m.group(1)[:96] if m else "IT DID NOT"))
        print()

        print("third pass: a PHY that came up already advertising Pause")
        pbrd, _ptext = pause_advertised_pass(img, k, mii, base, size, phy_addr,
                                             fails)
    padv = [v for _a, r, v in pbrd.mdio_writes if r == mii["MII_ADVERTISE"]]
    pbmcr = [v for _a, r, v in pbrd.mdio_writes if r == mii["MII_BMCR"]]
    print("   advertisement rewritten: %s, negotiation restarted: %s"
          % (["$%04X" % v for v in padv] or "IT WAS NOT",
             ["$%04X" % v for v in pbmcr] or "IT WAS NOT"))
    print()

    if fails:
        print("a64_genet_check: FAIL %d of %d checks" % (len(fails), EXPECTS))
        for f in fails:
            print("   " + f)
        return 1
    print("a64_genet_check: PASS %d checks over three passes - the GENET "
          "sequence matches %s" % (EXPECTS, DRIVER_NAME))

    if args.mutate:
        print()
        print("--mutate: breaking the library on purpose; each must go RED")
        if mutate_run("control", "", "", k, mii, base, phy_addr):
            print("  CONTROL FAILED - the unmutated copy does not pass through "
                  "the mutation path, so no RED below would mean anything.")
            return 1
        print("  control: the unmutated copy passes")
        bad = 0
        for name, old, new in MUTATIONS:
            print("  * %s" % name)
            if mutate_run(name, old, new, k, mii, base, phy_addr):
                print("    RED, as required")
            else:
                print("    *** STILL GREEN - the gate does not catch this ***")
                bad += 1
        if bad:
            return 1
        print("  all %d mutations caught" % len(MUTATIONS))

    return 0


if __name__ == "__main__":
    sys.exit(main())
