#!/usr/bin/env python3
"""Desk gate for the Rock Pi 4C RK3399 MiniDP preferred-mode path."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import build_count

ROOT = Path(__file__).resolve().parents[1]
ROCK = ROOT / "RockPi4C"
FIRMWARE_SHA256 = "203c5f061fb5075e4ca5398f8becc74e7cc450b494af857da5400788a7eae20b"
SAFE_MODE = (1024, 768, 65000000, 1344, 1048, 1184, 806, 771, 777, 0, 0, 4096)
PREFERRED_1080P = (
    1920, 1080, 148500000, 2200, 2008, 2052, 1125, 1084, 1089, 1, 1, 7680,
)
MAX_MODE_WIDTH = 2560
MAX_MODE_HEIGHT = 1600
MAX_MODE_PIXEL_HZ = 360000000
MAX_FRAMEBUFFER_BYTES = MAX_MODE_WIDTH * MAX_MODE_HEIGHT * 4
PINNED_VPLL = {
    594000000: (1, 123, 5, 1, 0, 0xC00000),
    593406593: (1, 123, 5, 1, 0, 10508804),
    297000000: (1, 123, 5, 2, 0, 0xC00000),
    296703297: (1, 123, 5, 2, 0, 10508807),
    148500000: (1, 129, 7, 3, 0, 0xF00000),
    148351648: (1, 123, 5, 4, 0, 10508800),
    106500000: (1, 124, 7, 4, 0, 0x400000),
    74250000: (1, 129, 7, 6, 0, 0xF00000),
    74175824: (1, 129, 7, 6, 0, 13550823),
    65000000: (1, 113, 7, 6, 0, 0xC00000),
    59340659: (1, 121, 7, 7, 0, 2581098),
    54000000: (1, 110, 7, 7, 0, 0x400000),
    27000000: (1, 55, 7, 7, 0, 0x200000),
    26973027: (1, 55, 7, 7, 0, 1173232),
}


def vpll_reference_plan(pixel_hz: int) -> tuple[int, ...] | None:
    """Independent integer model of the pinned-first RK3399 VPLL planner."""
    if pixel_hz == 24000000:
        return None
    plan = PINNED_VPLL.get(pixel_hz)
    if plan is None:
        post1 = post2 = 0
        for first in range(1, 8):
            for second in range(1, 8):
                vco = pixel_hz * first * second
                if 800000000 <= vco <= 2000000000:
                    post1, post2 = first, second
                    break
            if post1:
                break
        if not post1:
            return None
        if pixel_hz % 1000000 == 0:
            from math import gcd
            common = gcd(24, vco // 1000000)
            ref, fb, dsmpd, fraction = 24 // common, vco // 1000000 // common, 1, 0
        else:
            from math import gcd
            vco_mhz = vco // 1000000
            common = gcd(24, vco_mhz)
            ref, fb = 24 // common, vco_mhz // common
            remainder = vco % 1000000
            divisor = 24000000 // ref
            fraction = (remainder << 24) // divisor
            dsmpd = int(fraction == 0)
        plan = ref, fb, post1, post2, dsmpd, fraction
    ref, fb, post1, post2, dsmpd, fraction = plan
    if not (1 <= ref <= 63 and 16 <= fb <= 3200 and
            1 <= post1 <= 7 and 1 <= post2 <= 7):
        return None
    actual = ((24000000 * (fb * 16777216 + fraction) // ref) //
              (16777216 * post1 * post2))
    if actual > pixel_hz or pixel_hz - actual > 1:
        return None
    return ref, fb, post1, post2, dsmpd, fraction, actual


def detailed_timing(
    width: int, height: int, pixel_khz: int, hblank: int, hfront: int,
    hsync: int, vblank: int, vfront: int, vsync: int, *,
    hsync_positive: bool, vsync_positive: bool, interlaced: bool = False,
) -> bytes:
    """Generate one EDID detailed-timing descriptor for independent tests."""
    require(pixel_khz % 10 == 0, "EDID pixel clock is not representable in 10 kHz")
    require(all(0 <= value < 4096 for value in (width, hblank)),
            "horizontal DTD field is out of range")
    require(all(0 <= value < 2048 for value in (height, vblank)),
            "vertical DTD field is out of range")
    dtd = bytearray(18)
    dtd[0:2] = (pixel_khz // 10).to_bytes(2, "little")
    dtd[2], dtd[3] = width & 255, hblank & 255
    dtd[4] = ((width >> 8) << 4) | (hblank >> 8)
    dtd[5], dtd[6] = height & 255, vblank & 255
    dtd[7] = ((height >> 8) << 4) | (vblank >> 8)
    dtd[8], dtd[9] = hfront & 255, hsync & 255
    dtd[10] = ((vfront & 15) << 4) | (vsync & 15)
    dtd[11] = ((hfront >> 8) << 6) | ((hsync >> 8) << 4) | \
              ((vfront >> 4) << 2) | (vsync >> 4)
    # Digital separate sync. Bits 2 and 1 are the vertical and horizontal
    # positive-polarity flags respectively.
    dtd[17] = 0x18 | (4 if vsync_positive else 0) | \
              (2 if hsync_positive else 0) | (0x80 if interlaced else 0)
    return bytes(dtd)


def base_edid(dtd: bytes, *, valid_checksum: bool = True,
              advertise_fallback: bool = False) -> bytes:
    """Generate a minimal base EDID with ``dtd`` as its preferred timing."""
    require(len(dtd) == 18, "EDID DTD must be exactly 18 bytes")
    edid = bytearray(128)
    edid[:8] = bytes.fromhex("00 ff ff ff ff ff ff 00")
    edid[18:20] = bytes((1, 4))
    edid[24] = 2                 # preferred-timing bit
    if advertise_fallback:
        edid[36] |= 8            # established 1024x768@60
    edid[54:72] = dtd
    edid[126] = 0               # no extension is needed by these tests
    edid[127] = (-sum(edid[:127])) & 255
    if not valid_checksum:
        edid[127] ^= 1
    return bytes(edid)


def checksum_edid_block(block: bytes | bytearray) -> bytes:
    """Return one exact 128-byte EDID block with a valid checksum."""
    require(len(block) == 128, "EDID block must be exactly 128 bytes")
    result = bytearray(block)
    result[127] = (-sum(result[:127])) & 255
    return bytes(result)


def capability_test_edid() -> bytes:
    """Two-block EDID exercising every supported inventory source."""
    base = bytearray(base_edid(detailed_timing(
        1920, 1080, 148500, 280, 88, 44, 45, 4, 5,
        hsync_positive=True, vsync_positive=False,
    ), advertise_fallback=True))
    base[38:54] = b"\x01\x01" * 8
    base[38:40] = bytes((0x81, 0x80))  # 1280x1024@60 standard timing.
    base[72:90] = bytes((0, 0, 0, 0xFD, 0, 48, 144, 30, 180, 36,
                         0, 0, 0, 0, 0, 0, 0, 0))
    base[126] = 1
    base = bytearray(checksum_edid_block(base))

    cta = bytearray(128)
    cta[0:4] = bytes((2, 3, 8, 1))  # CTA-861, DBC end=8, one native DTD.
    cta[4:8] = bytes((0x43, 0x80 | 16, 4, 127))
    cta[8:26] = detailed_timing(
        1920, 1080, 297000, 280, 88, 44, 45, 4, 5,
        hsync_positive=True, vsync_positive=True,
    )
    return bytes(base) + checksum_edid_block(cta)


def select_reference_mode(edid: bytes) -> tuple[tuple[int, ...] | None, str, str]:
    """Independent model of the deliberately bounded preferred-DTD policy."""
    def fallback(reason: str) -> tuple[tuple[int, ...] | None, str, str]:
        if len(edid) >= 128 and edid[:8] == bytes.fromhex(
                "00 ff ff ff ff ff ff 00") and not sum(edid[:128]) & 255 and \
                edid[18] == 1 and edid[19] <= 4 and edid[36] & 8:
            return SAFE_MODE, "fallback", reason
        return None, "none", reason

    if len(edid) < 128 or edid[:8] != bytes.fromhex("00 ff ff ff ff ff ff 00"):
        return None, "none", "header"
    if sum(edid[:128]) & 255:
        return None, "none", "checksum"
    if edid[18] != 1 or edid[19] > 4:
        return None, "none", "version"
    dtd = edid[54:72]
    pixel_hz = int.from_bytes(dtd[:2], "little") * 10000
    if not pixel_hz:
        return fallback("no-preferred-dtd")
    width = dtd[2] | ((dtd[4] >> 4) << 8)
    hblank = dtd[3] | ((dtd[4] & 15) << 8)
    height = dtd[5] | ((dtd[7] >> 4) << 8)
    vblank = dtd[6] | ((dtd[7] & 15) << 8)
    hfront = dtd[8] | ((dtd[11] >> 6) << 8)
    hsync = dtd[9] | (((dtd[11] >> 4) & 3) << 8)
    vfront = (dtd[10] >> 4) | (((dtd[11] >> 2) & 3) << 4)
    vsync = (dtd[10] & 15) | ((dtd[11] & 3) << 4)
    flags = dtd[17]
    if flags & 0x80:
        return fallback("interlaced")
    if flags & 0x18 != 0x18:
        return fallback("non-separate-sync")
    if flags & 0x61:
        return fallback("stereo")
    if (not width or not height or not hblank or not vblank or not hfront or
            not hsync or not vfront or not vsync or hfront + hsync > hblank or
            vfront + vsync > vblank):
        return fallback("geometry")
    htotal, vtotal = width + hblank, height + vblank
    hsync_start, hsync_end = width + hfront, width + hfront + hsync
    vsync_start, vsync_end = height + vfront, height + vfront + vsync
    if (width > MAX_MODE_WIDTH or height > MAX_MODE_HEIGHT or htotal > 8191 or
            hsync_start > 8191 or hsync_end > 8191 or vtotal > 8191 or
            vsync_start > 8191 or vsync_end > 8191):
        return fallback("vop-limit")
    pitch = (width * 4 + 15) & ~15
    if pitch < width * 4 or pitch & 15 or pitch // 4 > 0x3FFF or \
            pitch * height > MAX_FRAMEBUFFER_BYTES:
        return fallback("pitch")
    if pixel_hz * 24 > 2 * 540000000 * 8:
        return fallback("link-rate")
    if vpll_reference_plan(pixel_hz) is None:
        return fallback("vpll-rate")
    mode = (width, height, pixel_hz, htotal, width + hfront,
            width + hfront + hsync, vtotal, height + vfront,
            height + vfront + vsync, 1 if flags & 2 else 0,
            1 if flags & 4 else 0, pitch)
    return mode, "preferred", "preferred"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def source_contract() -> None:
    libraries = {path.name: path.read_text(encoding="utf-8")
                 for path in (ROCK / "Lib").glob("*.pbi")}
    joined = "\n".join(libraries.values()).lower()
    for width_bug in ("peekn", "poken"):
        offenders = [name for name, text in libraries.items()
                     if re.search(rf"\b{width_bug}\s*\(", text, re.I)]
        require(not offenders,
                f"64-bit {width_bug} used against 32-bit RK3399 MMIO: {offenders}")
    for token in (
        "$ff310000", "$ff760000", "$ff770000", "$ff7c0000",
        "$fec00000", "$ff8f0000", "rockpmupoweron(14",
        "rockpmupoweron(24", "rockpmupoweron(20", "rockpmupoweron(8",
        "rockpmuidlerelease(17", "rockpmuidlerelease(11",
        "rockpmuidlerelease(8", "$30003000", "$10001000",
        "rock_cru_gpll_rate = rockcrupllrate($80,1,47)",
        "rockcruvpllmode()", "$1fdf,$0080 | (aclkdivider-1)",
        "rockcdnfirmwareload", "rockcdnhotplug", "rockcdndpcd",
        "rockcdnreadedid", "rockmodeselect(edid.i)", "rockcdntrain",
        "rockcdnvideomode", "rockcdnlinkcarriesmode", "rockvopupmode",
        "dp08 visible ",
    ):
        require(token in joined, f"missing display contract token: {token}")
    board = (ROCK / "Board/board.rockpi4c").read_text(encoding="utf-8").lower()
    for include in ("cru.pbi", "tcphy.pbi", "cdn_dp.pbi", "vop.pbi", "display.pbi"):
        require(include in board, f"composition root omits {include}")
    require('xincludefile "raspberrypi4/' not in board,
            "Pi 4 hardware leaked into Rock Pi composition root")
    edid_caps = libraries["edid_caps.pbi"].lower()
    for token in (
        "#rock_edid_max_blocks = 256", "#rock_edid_cap_max = 30400",
        "procedure.i rockedidblockchecksum", "procedure.i rockedidcapsestablished",
        "procedure.i rockedidcapsstandard", "procedure.i rockedidcapdtd",
        "procedure rockedidcapsrange", "procedure.i rockedidcapctasvd",
        "procedure.i rockedidcapscta", "procedure.i rockedidcapscollect",
        "for block=1 to extensioncount", "rock_edid_extension_tag[block]=tag",
        "rock_edid_extension_parsed[block]=1", "default : mapped=0",
        "rock_edid_error=#rock_edid_error_capacity",
    ):
        require(token in edid_caps, f"EDID capability inventory drifted: {token}")
    require(30400 >= 29 + 255 * 119,
            "EDID capability storage cannot hold the bounded wire maximum")
    cdn = libraries["cdn_dp.pbi"].lower()
    for token in (
        "#cdn_edid_bytes = 32768",
        "global dim rock_cdn_edid.a[#cdn_edid_bytes-1]",
        "extensioncount=peeka(@rock_cdn_edid[0]+126) & 255",
        "for block=1 to extensioncount",
        "rockcdnreadedidblock(block,@rock_cdn_edid[0]+block*128)",
        "rockedidcapscollect(@rock_cdn_edid[0],extensioncount+1)",
    ):
        require(token in cdn, f"complete EDID acquisition drifted: {token}")
    require("extensioncount>1" not in cdn,
            "EDID acquisition silently truncates advertised extension blocks")
    display = libraries["display.pbi"].lower()
    display_up = display.split("procedure.i rockdisplayup()", 1)[1].split(
        "endprocedure", 1
    )[0]
    order = [
        "rockcrudisplayprepare", "rockcrucadencerelease", "rockcdninternalclocks",
        "rockcdnfirmwareload", "rockcdnfirmwareactive", "rockcdnenableevents",
        "rocktcphyup", "$30003000", "rockcdnhotplug",
        "rockcdnhostcapabilities", "rockcdndpcd", "rockcdnreadedid",
        "rockcdntrain", "rockcdnvideostatus(0)", "rockcdnvideomode",
        "rockcruvpllmode", "rockvopupmode", "dp06 color bars and text armed",
        "rockcdnvideostatus(1)", "dp08 visible ",
    ]
    positions = [display_up.index(token) for token in order]
    require(positions == sorted(positions), "cold-to-visible stage order drifted")
    prepare_failure = display_up.split("if prepared=0", 1)[1].split(
        "endif", 1
    )[0]
    require("rockdisplaycrutelemetry()" in prepare_failure and
            prepare_failure.index("rockdisplaycrutelemetry()") <
            prepare_failure.index("rockdisplayfail(1"),
            "DPE1 no longer emits CRU/PMU evidence before refusing")
    dp_power = display.split("procedure rockdisplaydppowertelemetry()", 1)[1].split(
        "endprocedure", 1
    )[0]
    firmware_telemetry = display.split(
        "procedure rockdisplayfirmwaretelemetry()", 1
    )[1].split("endprocedure", 1)[0]
    tcphy_telemetry = display.split("procedure rockdisplaytcphytelemetry()", 1)[1].split(
        "endprocedure", 1
    )[0]
    grf_telemetry = display.split("procedure rockdisplaygrftelemetry()", 1)[1].split(
        "endprocedure", 1
    )[0]
    for token in ('peekl(#rock_gpio1+$50) & $ffffffff',
                  'rockuarttext("dp_pwr level ")', '(value >> 24) & 1'):
        require(token in dp_power, f"DP_PWR input witness drifted: {token}")
    require("pokel" not in dp_power,
            "DP_PWR telemetry must not drive or reconfigure the board pin")
    require('rockuarttext("cadence fw ")' in firmware_telemetry and
            "rockdisplayhexlong(rock_cdn_firmware_version)" in firmware_telemetry,
            "Cadence firmware-version witness drifted")
    for token in ('rockuarttext("tcphy cmn ")',
                  "rocktcread(#tcphy_pma_cmn_ctrl1)",
                  "rocktcread(#tcphy_dp_mode_ctl)",
                  "rocktcread(#tcphy_pma_lane_cfg)",
                  "rocktcread(#tcphy_tx_ana1)"):
        require(token in tcphy_telemetry, f"TCPHY readback witness drifted: {token}")
    require("rocktcwrite" not in tcphy_telemetry and "pokel" not in tcphy_telemetry,
            "TCPHY telemetry gained a functional register write")
    require('rockuarttext("grf_soc_con26 ")' in grf_telemetry and
            "peekl(#rock_grf+$6268) & $ffffffff" in grf_telemetry,
            "GRF_SOC_CON26 readback witness drifted")
    require("pokel" not in grf_telemetry,
            "GRF telemetry gained a functional register write")
    witness_order = [
        "prepared = rockcrudisplayprepare()", "rockdisplaydppowertelemetry()",
        "if prepared=0", "rockcdnfirmwareload()", "rockdisplayfirmwaretelemetry()",
        "rocktcphyup()", "rockdisplaytcphytelemetry()", "$30003000",
        "rockdisplaygrftelemetry()", "rockcdnhotplug()",
    ]
    positions = [display_up.index(token) for token in witness_order]
    require(positions == sorted(positions),
            "silicon readbacks moved away from their completed owner stages")
    failure_witnesses = {
        "rockcrucadencerelease()": ("dpe3 cru err ", "rock_cru_error"),
        "rockcdnfirmwareload()": ("dpe4 cdn err ", "rock_cdn_error"),
        "rockcdnfirmwareactive(1)": ("dpe5 cdn err ", "rock_cdn_error"),
        "rockcdnenableevents()": ("dpe6 cdn err ", "rock_cdn_error"),
        "rocktcphyup()": ("dpe2 tcphy err ", "rock_tcphy_error"),
        "rockcdnhotplug()": ("dpe7 cdn err ", "rock_cdn_error"),
        "rockcdnhostcapabilities()": ("dpef cdn err ", "rock_cdn_error"),
        "rockcdnreadedid()": ("dpe9 cdn err ", "rock_cdn_error"),
        "rockcdntrain()": ("dpeb cdn err ", "rock_cdn_error"),
        "rockcdnvideostatus(0)": ("dpec cdn err ", "rock_cdn_error"),
        "rockcruvpllmode()": ("dpe1 cru err ", "rock_cru_error"),
        "rockvopupmode()": ("dpea vop err ", "rock_vop_error"),
        "rockcdnvideostatus(1)": ("dpee cdn err ", "rock_cdn_error"),
    }
    for owner_call, (label, error) in failure_witnesses.items():
        start = display_up.index(f"if {owner_call}=0")
        end = display_up.index("procedurereturn rockdisplayfail", start)
        failure = display_up[start:end + len("procedurereturn rockdisplayfail")]
        require(f'rockdisplaysubsystemtelemetry("{label}",{error})' in failure and
                failure.index("rockdisplaysubsystemtelemetry") <
                failure.index("rockdisplayfail"),
                f"{owner_call} no longer reports its exact subsystem error")
    mode_retry = display_up.split(
        "configured = rockcdnvideomode()", 1
    )[1].split("if configured=0", 1)[0]
    for token in ("rock_cdn_error = 35 or rock_cdn_error = 36",
                  "modefailure = rock_cdn_error",
                  "rockmodefallback(@rock_cdn_edid[0],modefailure)",
                  'rockdisplaymodetelemetry("dp mode fallback ")'):
        require(token in mode_retry,
                f"trained-link preferred-mode fallback drifted: {token}")
    configured_failure = display_up.split("if configured=0", 1)[1].split(
        "endif", 1
    )[0]
    require('rockdisplaysubsystemtelemetry("dped cdn err ",rock_cdn_error)' in
            configured_failure and "rockdisplayfail(13" in configured_failure,
            "unsupported selected mode can be mistaken for configured video")
    for token in (
        "procedure rockdisplayedidtelemetry()",
        "for block=0 to rock_edid_block_count-1",
        "procedure rockdisplayedidcapabilities()",
        'rockuarttext("edid ext ")', 'rockuarttext(" parsed ")',
        'rockuarttext("edid range v ")', 'rockuarttext("edid cap ")',
    ):
        require(token in display, f"EDID report surface drifted: {token}")
    cru = libraries["cru.pbi"].lower()
    power_order = ["rockpmupoweron(14", "rockpmupoweron(24",
                   "rockpmupoweron(20", "rockpmuidlerelease(8",
                   "rockpmupoweron(8"]
    positions = [cru.index(token) for token in power_order]
    require(positions == sorted(positions), "RK3399 power hierarchy order drifted")
    power = cru.split("procedure.i rockcrudisplaypower()", 1)[1].split(
        "endprocedure", 1
    )[0]
    hdcp_transition = ["rockpmuidlerelease(17,54)", "rockcrugate(11,3,1)",
                       "rockcrugate(11,10,1)", "rockcrugate(11,12,1)",
                       "rockpmupoweron(24,56)", "rockpmuidlerelease(11,57)"]
    positions = [power.index(token) for token in hdcp_transition]
    require(positions == sorted(positions),
            "HDCP clocks are not enabled immediately before its power/idle transition")
    require("rockpmupoweron(14,53)=0 or" not in power and
            "rockpmupoweron(24,56)=0 or" not in power,
            "eager Or can release bus idle after a failed domain power-on")
    require("gpio1_d0, not gpio1_c0" in cru, "exact MiniDP power pin correction missing")
    require("$00030000" in cru and "$00030001" in cru,
            "GPIO1_D0 input/pull-up pinctrl contract missing")
    prepare = cru.split("procedure.i rockcrudisplayprepare()", 1)[1].split(
        "endprocedure", 1
    )[0]
    for token in ("#rock_reset_uphy0_pipe_l00 = 148",
                  "#rock_reset_uphy0 = 149",
                  "#rock_reset_p_uphy0_tcphy = 332"):
        require(token in cru, f"TCPHY reset identity drifted: {token}")
    require("rockcrureset(#rock_reset_uphy0_pipe_l00,1)" in prepare and
            "rockcrureset(#rock_reset_uphy0,1)" in prepare and
            "rockcrureset(#rock_reset_p_uphy0_tcphy,1)" in prepare and
            "rockcrureset(#rock_reset_p_uphy0_tcphy,0)" not in prepare,
            "TCPHY/UPHY/PIPE resets are not held through owner pre-init")
    require("rockcrugate(21,5,1)" in cru and "rockcrugate(21,6,1)" in cru,
            "TCPHY0 APB register clocks TCPHY_G/TCPD_G are not both enabled")
    tcphy = libraries["tcphy.pbi"].lower()
    tcphy_up = tcphy.split("procedure.i rocktcphyup()", 1)[1].split(
        "endprocedure", 1
    )[0]
    tcphy_order = [
        "pokel(#rock_grf+$e588,$40004000)",
        "pokel(#rock_grf+$e580,$00080000)",
        "rockcrureset(#rock_reset_p_uphy0_tcphy,0)",
        "pokel(#rock_grf+$e580,$00010000)",
        "rocktcread(#tcphy_tx_ana1)",
        "rocktccommon24m()", "rocktcwrite(#tcphy_pma_lane_cfg,$5100)",
        "rocktcdprbrpll()", "rocktcwrite(#tcphy_dp_mode_ctl",
        "rockcrureset(#rock_reset_uphy0,0)",
        "rocktcwaitmask(#tcphy_pma_cmn_ctrl1,1,1,100000,10)",
        "rockcrureset(#rock_reset_uphy0_pipe_l00,0)",
        "pokel(#rock_grf+$6268,$00080000)",
        "rocktcwaitmask(#tcphy_dp_mode_ctl,$40,$40,100000,1000)",
        "rocktcauxcalibrate()", "rocktcpowerstate(0)",
    ]
    positions = [tcphy_up.index(token) for token in tcphy_order]
    require(positions == sorted(positions),
            "TCPHY pre-init/config/reset/readiness order drifted from pinned owner")
    require("rock_tcphy_error=47" in tcphy_up,
            "PIPE reset-release failure lacks an exact TCPHY refusal code")
    tcphy_stages = [f'tp0{digit} ' for digit in "0123456789abc"]
    for stage in tcphy_stages:
        require(stage in tcphy_up, f"TCPHY serial progress witness missing: {stage}")
    wait_mask = tcphy.split("procedure.i rocktcwaitmask", 1)[1].split(
        "endprocedure", 1
    )[0]
    require("attempts = timeoutus/stepus" in wait_mask and
            "rocktimerwaitus(stepus)" in wait_mask,
            "TCPHY readiness poll lost its paced finite ceiling")
    power_state = tcphy.split("procedure.i rocktcpowerstate", 1)[1].split(
        "endprocedure", 1
    )[0]
    require("for attempt = 0 to 10000" in power_state and
            "rocktimerwaitus(10)" in power_state,
            "TCPHY A0 transition poll lost its pinned pacing/ceiling")
    cru_telemetry = display.split("procedure rockdisplaycrutelemetry()", 1)[1].split(
        "endprocedure", 1
    )[0]
    for token in (
        'rockuarttext("dpe1 detail err ")', 'rockuarttext(" source ")',
        'rockuarttext(" cpll ")', 'rockuarttext("gpll")',
        'rockuarttext("vio")', 'rockuarttext("hdcp")',
        'rockuarttext("vo")', 'rockuarttext("vopl")',
        'rockuarttext("tcpd0")', 'rockuarttext("vpll")',
        "rockcruread($60)", "rockcruread($64)", "rockcruread($68)",
        "rockcruread($6c)", "rockcruread($80)", "rockcruread($84)",
        "rockcruread($88)", "rockcruread($8c)",
        "rockcruread($c0)", "rockcruread($c4)",
        "rockcruread($c8)", "rockcruread($cc)",
        "peekl(#rock_pmu+#rock_pmu_pwrdn_st) & $ffffffff",
        "peekl(#rock_pmu+#rock_pmu_bus_idle_req) & $ffffffff",
        "peekl(#rock_pmu+#rock_pmu_bus_idle_st) & $ffffffff",
        "peekl(#rock_pmu+#rock_pmu_bus_idle_ack) & $ffffffff",
    ):
        require(token in cru_telemetry, f"DPE1 raw witness drifted: {token}")
    for token in ("rock_cru_gpll_rate = rockcrupllrate($80,1,47)",
                  "rockcruceilingdivider(rock_cru_gpll_rate,50000000)",
                  "rockcruceilingdivider(rock_cru_gpll_rate,100000000)",
                  "rockcruceilingdivider(rock_cru_gpll_rate,200000000)",
                  "rockcruceilingdivider(rock_cru_gpll_rate,400000000)",
                  "rockcruceilingdivider(aclkrate,200000000)",
                  "rock_cru_error=errorcode",
                  "rock_cru_error=errorcode+1",
                  "rock_cru_error=errorcode+2"):
        require(token in cru, f"DPE1 PLL refusal mapping drifted: {token}")
    require("rockcruceilingdivider(aclkrate,100000000)" not in cru,
            "VOP1 HCLK regressed below the pinned RK3399 200 MHz assignment")
    vpll = cru.split("procedure.i rockcruvpllset(pixelhz.i)", 1)[1].split(
        "endprocedure", 1
    )[0]
    vpll_order = [
        "rockcrufield($cc,$0300,$0000)",
        "rockcrufield($cc,$0001,$0001)",
        "rockcrufield($c0,$0fff,rock_mode_vpll_fb)",
        "rockcrufield($c4,$773f,rock_mode_vpll_ref | (rock_mode_vpll_post1 << 8) | (rock_mode_vpll_post2 << 12))",
        "con2 = rockcruread($c8)",
        "rockcruwrite($c8,(con2 & $ff000000) | rock_mode_vpll_frac)",
        "rockcrufield($cc,$0008,rock_mode_vpll_dsmpd << 3)",
        "rockcrufield($cc,$0001,$0000)",
        "rockcruwait($c8,$80000000,$80000000)",
        "rockcrufield($cc,$0300,$0100)",
        "rate = rockcrupllrate($c0,0,63)",
        "if rate <> rock_mode_vpll_actual_hz or rate>pixelhz or pixelhz-rate>1",
    ]
    positions = [vpll.index(token) for token in vpll_order]
    require(positions == sorted(positions),
            "selected VPLL slow/powerdown/program/lock/normal order drifted")
    require("#rock_cru_clksel+$1ac" not in cru,
            "DCLK_VOP1 regressed to an imprecise fractional divider")
    require("rockcrupllrate($60" not in cru,
            "display clock admission still depends on bypassed CPLL")
    require("rockcrugate(10,13,0)" in cru,
            "VOP DCLK is not gated while its VPLL parent is reprogrammed")
    display_clocks = cru.split("procedure.i rockcrudisplayclocks()", 1)[1].split(
        "endprocedure", 1
    )[0]
    dclk_order = ["rockcrugate(10,13,0)", "rockcruvpll65()",
                  "rockcrufield(#rock_cru_clksel+$c8,$0bff,$0000)",
                  "rockcrugate(10,13,1)"]
    positions = [display_clocks.index(token) for token in dclk_order]
    require(positions == sorted(positions),
            "VPLL/DCLK gate, parent and enable order drifted")
    selected_clock = cru.split("procedure.i rockcruvpllmode()", 1)[1].split(
        "endprocedure", 1
    )[0]
    selected_order = ["rockcrugate(10,13,0)",
                      "rockcruvpllset(rock_mode_pixel_hz)",
                      "rockcrufield(#rock_cru_clksel+$c8,$0bff,$0000)",
                      "rockcrugate(10,13,1)"]
    positions = [selected_clock.index(token) for token in selected_order]
    require(positions == sorted(positions) and
            "rock_mode_valid=0" in selected_clock,
            "selected VPLL does not remain gated and validity-bound")
    require("rockcdnwrite(#cdn_sw_clk_h,rock_cru_dp_core_rate/1000000)" in display,
            "Cadence SW clock does not receive the derived core MHz")
    prepare_clock = prepare.index("rockcrudisplayclocks()")
    for reset in ("rockcrureset(275,1)", "rockcrureset(279,1)",
                  "rockcrureset(281,1)"):
        require(prepare.index(reset) < prepare_clock,
                f"{reset} does not hold VOP before VPLL/DCLK programming")
    for token in ("rockpmupoweron(14,53)", "rockpmuidlerelease(17,54)",
                  "rockpmupoweron(24,56)", "rockpmuidlerelease(11,57)",
                  "rockpmupoweron(20,59)", "rockpmuidlerelease(8,60)",
                  "rockpmupoweron(8,62)"):
        require(token in cru, f"DPE1 PMU refusal mapping drifted: {token}")
    vop = libraries["vop.pbi"].lower()
    require("procedure.i rockvopframebuffer()" in vop and
            "& $fffffffffffffff0" in vop,
            "framebuffer base is not derived at its required 16-byte alignment")
    line_buffer = vop.split("procedure.i rockvoplinebuffermode(width.i)", 1)[1].split(
        "endprocedure", 1
    )[0]
    for token in ("width < 1 or width > #rock_vop_max_width",
                  "if width > 1920 : procedurereturn #vop_lb_rgb_2560x4",
                  "procedurereturn #vop_lb_rgb_1920x5"):
        require(token in line_buffer,
                f"pinned VOP line-buffer selection drifted: {token}")
    require("procedurereturn 5" not in line_buffer,
            "obsolete RGB1280 line-buffer mode remains selectable")
    vop_valid = vop.split("procedure.i rockvopmodevalid()", 1)[1].split(
        "endprocedure", 1
    )[0]
    for token in ("#rock_vop_max_width", "#rock_vop_max_height",
                  "#rock_vop_timing_max", "#rock_vop_stride_word_max",
                  "rock_mode_pitch*rock_mode_height > #rock_fb_max_bytes"):
        require(token in vop_valid, f"dynamic VOP admission bound missing: {token}")
    vop_up = vop.split("procedure.i rockvopupmode()", 1)[1].split(
        "endprocedure", 1
    )[0]
    line_buffer_order = ["rockvopmodevalid()",
                         "linebuffermode=rockvoplinebuffermode(rock_mode_width)",
                         "if linebuffermode < 0", "rockcruvoprelease()",
                         "rockvopwrite(#vop_win0_ctrl0,#vop_win_enable | (linebuffermode << #vop_win_lb_mode_shift))"]
    positions = [vop_up.index(token) for token in line_buffer_order]
    require(positions == sorted(positions),
            "WIN0 line-buffer admission/programming moved after hardware release")
    outstanding = "rockvopfield(#vop_sys_ctrl1,$0003f000,$0003d000)"
    require(outstanding in vop_up and
            vop_up.index("rockcrureset(279,0)") < vop_up.index(outstanding) <
            vop_up.index("rockvopwrite(#vop_win0_ctrl0"),
            "VOP 30-read AXI throughput contract is absent or armed too late")
    gather = "rockvopfield(#vop_win0_ctrl1,#vop_win0_gather_mask,#vop_win0_argb8888_gather)"
    require(gather in vop_up and
            vop_up.index("rockvopwrite(#vop_win0_vir") < vop_up.index(gather) <
            vop_up.index("rockvopwrite(#vop_win0_ctrl0"),
            "ARGB8888 AXI gather contract is absent or armed after WIN0")
    win_scale = "rockvopwrite(#vop_win0_scl_factor,#vop_scale_unity_xy)"
    post_scale = "rockvopwrite(#vop_post_scl_factor,#vop_scale_unity_xy)"
    require("#vop_scale_unity_xy = $10001000" in vop and
            win_scale in vop_up and post_scale in vop_up and
            "rockvopfield(#vop_post_scl_ctrl,$3,0)" in vop_up,
            "native VOP window/post scale factors are not explicitly unity")
    require(vop_up.index(win_scale) < vop_up.index(gather) and
            vop_up.index(post_scale) < vop_up.index("rockvopwrite(#vop_win0_act_info"),
            "native VOP scale factors are armed after their consumers")
    for timing in (
        "rockvopwrite(#vop_htotal,hsynclength | (rock_mode_htotal << 16))",
        "rockvopwrite(#vop_hact,hactiveend | (hactivestart << 16))",
        "rockvopwrite(#vop_vtotal,vsynclength | (rock_mode_vtotal << 16))",
        "rockvopwrite(#vop_vact,vactiveend | (vactivestart << 16))",
        "rockvopwrite(#vop_post_hact,hactiveend | (hactivestart << 16))",
        "rockvopwrite(#vop_post_vact,vactiveend | (vactivestart << 16))",
        "rockvopwrite(#vop_win0_vir,rock_mode_pitch >> 2)",
    ):
        require(timing in vop_up, f"dynamic VOP timing/stride drifted: {timing}")
    for token in ("if rock_mode_hsync_positive <> 0 : pinpolarity=pinpolarity | 1",
                  "if rock_mode_vsync_positive <> 0 : pinpolarity=pinpolarity | 2",
                  "rockvopfield(#vop_dsp_ctrl1,$000f0012,(pinpolarity << 16) | #vop_dsp_p888_pre_dither)"):
        require(token in vop_up, f"dynamic VOP polarity drifted: {token}")
    require("#vop_dsp_p888_pre_dither = $00000002" in vop,
            "RK3399 VOPL P888 pre-dither contract is absent")

    # RockCruVpllMode is the final DCLK owner. Trace its complete downstream
    # source path rather than merely validating isolated PLL arithmetic.
    post_selected_clock = display_up.split("if rockcruvpllmode()=0", 1)[1]
    for forbidden in ("rockcruvpll65", "rockcrudisplayclocks", "rockcruvpllset",
                      "rockcrufield", "rockcrugate"):
        require(forbidden not in post_selected_clock,
                f"post-selection display path can overwrite DCLK: {forbidden}")
    vop_release = cru.split("procedure.i rockcruvoprelease()", 1)[1].split(
        "endprocedure", 1
    )[0]
    require(vop_release.count("rockcrureset(") == 3 and
            "rockcrureset(275,0)" in vop_release and
            "rockcrureset(279,0)" in vop_release and
            "rockcrureset(281,0)" in vop_release,
            "VOP A/H/D reset release contract drifted")
    for forbidden in ("rockcrufield", "rockcrugate", "rockcruvpll",
                      "#rock_cru_clksel", "rockcruwrite"):
        require(forbidden not in vop_release,
                f"VOP reset release can overwrite selected DCLK: {forbidden}")
    cdn = libraries["cdn_dp.pbi"].lower()
    video_mode = cdn.split("procedure.i rockcdnvideomode()", 1)[1].split(
        "endprocedure", 1
    )[0]
    for timing in ("negativeh.i = bool(rock_mode_hsync_positive = 0)",
                   "negativev.i = bool(rock_mode_vsync_positive = 0)",
                   "rockcdnregwrite(#cdn_framer_sp,(negativeh << 1) | negativev)",
                   "(rock_mode_hsync_end-rock_mode_hsync_start) | (negativeh << 15)",
                   "(rock_mode_vsync_end-rock_mode_vsync_start) | (negativev << 15)"):
        require(timing in video_mode,
                f"Cadence selected-mode polarity/timing drifted: {timing}")
    require("rockcdnlinkcarriesmode(linkmhz)" in video_mode,
            "selected-mode link-bandwidth admission check missing")
    live_link = cdn.split("procedure.i rockcdnreadlivelinkstatus()", 1)[1].split(
        "endprocedure", 1
    )[0]
    for token in ("pokea(@rock_cdn_message[0]+1,6)",
                  "pokea(@rock_cdn_message[0]+3,2)",
                  "pokea(@rock_cdn_message[0]+4,2)",
                  "rockcdnreceive(#cdn_mb_dp_tx,#cdn_read_dpcd,11",
                  "rockcdnlastauxstatus()"):
        require(token in live_link,
                f"post-video DPCD 0202h link witness drifted: {token}")
    require("requiredmbps.i = (rock_mode_pixel_hz * 24 + 999999) / 1000000" in cdn and
            "availablembps = linkmhz * rock_cdn_link_lanes * 8" in cdn,
            "selected-mode link-bandwidth arithmetic drifted")
    for token in (
        "#cdn_get_last_aux_status = 14", "#cdn_aux_ack = 0",
        "#cdn_aux_nack = 1", "#cdn_aux_defer = 2",
        "#cdn_aux_sink_error = 3", "#cdn_aux_bus_error = 4",
        "#cdn_dpcd_phase_send = 1", "#cdn_dpcd_phase_response = 2",
        "#cdn_dpcd_phase_aux_mailbox = 3", "#cdn_dpcd_phase_aux_result = 4",
        "procedure.i rockcdnlastauxstatus()",
    ):
        require(token in cdn, f"DPCD AUX status contract drifted: {token}")
    dpcd = cdn.split("procedure.i rockcdndpcd()", 1)[1].split(
        "procedure.i rockcdnreadlivelinkstatus", 1)[0]
    transaction_order = [
        "rockcdnsend(#cdn_mb_dp_tx,#cdn_read_dpcd",
        "rockcdnreceive(#cdn_mb_dp_tx,#cdn_read_dpcd",
        "aux = rockcdnlastauxstatus()",
    ]
    positions = [dpcd.index(token) for token in transaction_order]
    require(positions == sorted(positions),
            "DPCD response must be consumed before AUX status is requested")
    require("rockcdnsend(#cdn_mb_dp_tx,#cdn_read_dpcd,5,@rock_cdn_message[0]) = 0 : procedurereturn 0" in dpcd,
            "DPCD send errors must stop without retrying a partial request")
    require("rockcdnreceive(#cdn_mb_dp_tx,#cdn_read_dpcd,21,@rock_cdn_message[32]) = 0 : procedurereturn 0" in dpcd,
            "DPCD transport errors must stop without retrying a dirty mailbox")
    require("if aux < 0 : procedurereturn 0" in dpcd,
            "AUX-status mailbox errors must stop without retry")
    defer = dpcd.split("case #cdn_aux_defer", 1)[1].split(
        "case #cdn_aux_nack", 1)[0]
    require("rocktimerwaitus(500)" in defer,
            "AUX DEFER no longer owns the sole DPCD retry delay")
    require(dpcd.count("rocktimerwaitus(") == 1,
            "a non-DEFER DPCD path gained a retry delay")
    ack = dpcd.split("case #cdn_aux_ack", 1)[1].split(
        "case #cdn_aux_defer", 1)[0]
    require("procedurereturn 1" in ack and "procedurereturn 0" in ack,
            "AUX ACK must accept valid DPCD and refuse an invalid revision")
    for fatal in ("#cdn_aux_nack", "#cdn_aux_sink_error", "#cdn_aux_bus_error"):
        branch = dpcd.split(f"case {fatal}", 1)[1].split("case ", 1)[0]
        require("procedurereturn 0" in branch,
                f"fatal AUX result became retryable: {fatal}")
    require("default" in dpcd and "rock_cdn_error = 40 : procedurereturn 0" in dpcd,
            "unknown AUX status must fail closed")
    require("rock_cdn_error = 41" in dpcd,
            "AUX DEFER exhaustion must fail closed")
    require("for attempt = 0 to 31" in dpcd,
            "DPCD retry count drifted from the 32-attempt owner contract")
    for phase in ("send", "response", "aux_mailbox", "aux_result"):
        require(f"rock_cdn_dpcd_phase = #cdn_dpcd_phase_{phase}" in dpcd,
                f"DPCD telemetry omits {phase} phase")
    require("rock_cdn_aux_status = aux" in dpcd,
            "DPCD telemetry omits the last AUX result")
    require(not re.search(r"rockcdnregwrite[^\n]*\bor\b[^\n]*rockcdnregwrite", cdn),
            "eager Or can enqueue a second command after a failed Cadence write")
    send = cdn.split("procedure.i rockcdnsend", 1)[1].split(
        "procedure.i rockcdnreceive", 1
    )[0]
    require(not re.search(r"rockcdnmailboxput[^\n]*\bor\b[^\n]*rockcdnmailboxput", send),
            "eager Or can continue a failed Cadence mailbox header")
    for header in ("rockcdnmailboxput(opcode)", "rockcdnmailboxput(module)",
                   "rockcdnmailboxput((bytes >> 8) & 255)",
                   "rockcdnmailboxput(bytes & 255)"):
        require(f"if {header} = 0 : procedurereturn 0" in send,
                f"mailbox header byte is not fail-fast: {header}")
    edid = cdn.split("procedure.i rockcdnreadedidblock", 1)[1].split(
        "procedure.i rockcdnreadedid()", 1
    )[0]
    request_zero = edid.index("pokea(@rock_cdn_message[0],block >> 1)")
    request_one = edid.index("pokea(@rock_cdn_message[0]+1,block & 1)")
    edid_send = edid.index("rockcdnsend(#cdn_mb_dp_tx,#cdn_get_edid,2,@rock_cdn_message[0])")
    require(edid.index("for attempt = 0 to 3") < request_zero < request_one < edid_send,
            "EDID request metadata is not rebuilt for every safe retry")
    require("rockcdnsend(#cdn_mb_dp_tx,#cdn_get_edid,2,@rock_cdn_message[0]) = 0 : procedurereturn 0" in edid and
            "rockcdnreceive(#cdn_mb_dp_tx,#cdn_get_edid,130,@rock_cdn_message[64]) = 0 : procedurereturn 0" in edid,
            "EDID transport failure can retry a dirty mailbox")
    require("peeka(@rock_cdn_message[64])" in edid and
            "peeka(@rock_cdn_message[64]+1)" in edid and
            "peeka(@rock_cdn_message[64]+2+index)" in edid,
            "EDID response does not remain disjoint from its request")
    read_edid = cdn.split("procedure.i rockcdnreadedid()", 1)[1].split(
        "endprocedure", 1
    )[0]
    require("rockmodeselect(@rock_cdn_edid[0])" in read_edid and
            "rock_cdn_error = 30" in read_edid,
            "EDID acquisition can bypass fail-closed mode selection")
    mode = libraries["display_mode.pbi"].lower()
    for name in ("width", "height", "pixel_hz", "htotal", "hsync_start",
                 "hsync_end", "vtotal", "vsync_start", "vsync_end",
                 "hsync_positive", "vsync_positive", "pitch", "source",
                 "reason", "valid"):
        require(f"global rock_mode_{name}.i" in mode,
                f"selected-mode ABI field missing: rock_mode_{name}")
    for name in ("ref", "fb", "post1", "post2", "dsmpd", "frac", "actual_hz"):
        require(f"global rock_mode_vpll_{name}.i" in mode,
                f"selected VPLL plan field missing: rock_mode_vpll_{name}")
    base_reason = mode.split("procedure.i rockmodeedidbasereason(edid.i)", 1)[1].split(
        "endprocedure", 1
    )[0]
    for token in ("edid=0", "$00", "$ff", "for index=0 to 127",
                  "if sum<>0", "peeka(edid+18)", "peeka(edid+19)"):
        require(token in base_reason, f"EDID base-block trust gate missing: {token}")
    fallback = mode.split("procedure.i rockmodefallback(edid.i,reason.i)", 1)[1].split(
        "endprocedure", 1
    )[0]
    require("rockmodeedidbasereason(edid)" in fallback and
            "(peeka(edid+36) & 255) & 8" in fallback and
            "rockmodecommit(1024,768,65000000,1344,1048,1184,806,771,777,0,0,4096" in fallback,
            "safe fallback is no longer tied to trusted established 1024x768@60")
    selector = mode.split("procedure.i rockmodeselect(edid.i)", 1)[1].split(
        "endprocedure", 1
    )[0]
    for token in ("dtd=edid+54", "pixelhz=((peeka(dtd)",
                  "width=(peeka(dtd+2)", "hblank=(peeka(dtd+3)",
                  "height=(peeka(dtd+5)", "vblank=(peeka(dtd+6)",
                  "hoffset=(peeka(dtd+8)", "hwidth=(peeka(dtd+9)",
                  "voffset=((peeka(dtd+10)", "vwidth=(peeka(dtd+10)",
                  "(flags & $80)", "(flags & $18)<>$18", "(flags & $61)",
                  "#rock_mode_reason_h_geometry", "#rock_mode_reason_v_geometry",
                  "#rock_mode_reason_vop_limit", "#rock_mode_reason_pitch",
                  "#rock_mode_reason_link_rate", "rockmodecommit(width,height,pixelhz"):
        require(token in selector, f"preferred-DTD decoder/admission missing: {token}")
    commit = mode.split("procedure rockmodecommit(", 1)[1].split(
        "endprocedure", 1
    )[0]
    require(commit.rfind("rock_mode_valid=1") > commit.rfind("rock_mode_reason=reason"),
            "mode validity is published before the full ABI commit")
    planner = mode.split("procedure.i rockmodevpllplan(pixelhz.i)", 1)[1].split(
        "endprocedure", 1
    )[0]
    for pixel_hz in PINNED_VPLL:
        require(f"case {pixel_hz}" in planner,
                f"pinned VPLL tuple disappeared: {pixel_hz}")
    for token in ("if pixelhz=24000000 : procedurereturn 0",
                  "for postdivider1=1 to 7", "for postdivider2=1 to 7",
                  "vco>=800000000", "vco<=2000000000",
                  "rockmodegcd(24", "fraction=(remainder << 24)/divisor",
                  "pixelhz-actualhz>1", "rockmodevpllpublish("):
        require(token in planner, f"generic VPLL planner drifted: {token}")
    require("rockdisplaydpcdtelemetry()" in display and
            'rockuarttext("dpe8 dpcd phase ")' in display and
            'rockuarttext(" aux ")' in display,
            "serial DPCD phase/AUX telemetry is missing")
    receive = cdn.split("procedure.i rockcdnreceive", 1)[1].split(
        "procedure.i rockcdnregwrite", 1)[0]
    for token in (
        "rock_cdn_mailbox_actual_opcode = gotopcode",
        "rock_cdn_mailbox_actual_module = gotmodule",
        "rock_cdn_mailbox_actual_size = count",
        "rock_cdn_mailbox_drain_count = rock_cdn_mailbox_drain_count + 1",
        "rock_cdn_mailbox_drain_complete = 1",
        "if count = 5 : rock_cdn_mailbox_payload5_valid = 1",
    ):
        require(token in receive, f"mailbox mismatch diagnostic drifted: {token}")
    mismatch = receive.split(
        "if gotopcode <> opcode or gotmodule <> module or count <> bytes", 1
    )[1].split("rock_cdn_error = 24", 1)[0]
    require(mismatch.index("low = rockcdnmailboxget()") <
            mismatch.index("rock_cdn_mailbox_drain_count = rock_cdn_mailbox_drain_count + 1"),
            "mailbox drain count advances before a byte was consumed")
    require("if rock_cdn_mailbox_drain_count = count" in mismatch,
            "mailbox drain completeness is not tied to the advertised payload size")
    witness_reset = cdn.split("procedure rockcdnmailboxwitnessreset", 1)[1].split(
        "endprocedure", 1
    )[0]
    for token in ("rock_cdn_mailbox_actual_opcode = -1",
                  "rock_cdn_mailbox_actual_module = -1",
                  "rock_cdn_mailbox_actual_size = -1",
                  "rock_cdn_mailbox_actual_size_high = -1",
                  "rock_cdn_mailbox_actual_size_low = -1",
                  "rock_cdn_mailbox_header_count = 0",
                  "rock_cdn_mailbox_drain_count = 0",
                  "rock_cdn_mailbox_payload5_valid = 0"):
        require(token in witness_reset, f"mailbox witness reset drifted: {token}")
    for token in ("rock_cdn_mailbox_header_count = 1",
                  "rock_cdn_mailbox_header_count = 2",
                  "rock_cdn_mailbox_actual_size_high = high",
                  "rock_cdn_mailbox_header_count = 3",
                  "rock_cdn_mailbox_actual_size_low = low",
                  "rock_cdn_mailbox_header_count = 4"):
        require(token in receive, f"partial mailbox header witness drifted: {token}")
    require(dpcd.index("rockcdnmailboxwitnessreset(#cdn_mb_dp_tx,#cdn_read_dpcd,21)") <
            dpcd.index("for attempt = 0 to 31"),
            "DPCD send can expose stale mailbox witness state")
    last_aux = cdn.split("procedure.i rockcdnlastauxstatus()", 1)[1].split(
        "endprocedure", 1
    )[0]
    require(last_aux.index(
                "rockcdnmailboxwitnessreset(#cdn_mb_dp_tx,#cdn_get_last_aux_status,1)"
            ) < last_aux.index("rockcdnsend("),
            "AUX-status send can expose stale mailbox witness state")
    dpcd_telemetry = display.split("procedure rockdisplaydpcdtelemetry()", 1)[1].split(
        "endprocedure", 1
    )[0]
    require("rock_cdn_dpcd_phase = #cdn_dpcd_phase_response or "
            "rock_cdn_dpcd_phase = #cdn_dpcd_phase_aux_mailbox" in dpcd_telemetry and
            "rockdisplaymailboxtelemetry()" in dpcd_telemetry,
            "partial mailbox telemetry is not attached to response/AUX-mailbox failures")
    require("rock_cdn_error = 24" not in dpcd_telemetry,
            "mailbox telemetry is still limited to complete header mismatches")
    mailbox_telemetry = display.split("procedure rockdisplaymailboxtelemetry()", 1)[1].split(
        "endprocedure", 1
    )[0]
    for unsafe in ("rockcdnmailboxget", "rockcdnreceive", "rockcdnlastauxstatus",
                   "rockcdnsend", "pokel"):
        require(unsafe not in mailbox_telemetry,
                f"mailbox witness performs an unsafe diagnostic operation: {unsafe}")
    for token in ("rock_cdn_mailbox_actual_size_high",
                  "rock_cdn_mailbox_header_count",
                  'rockuarttext(" header ")', 'rockuarttext("/04")'):
        require(token in mailbox_telemetry,
                f"partial mailbox serial diagnostic drifted: {token}")
    for token in ('rockuarttext(" mbox got ")', 'rockuarttext(" expect ")',
                  'rockuarttext(" header ")', 'rockuarttext(" drain ")',
                  'rockuarttext(" payload")', 'rockuarttext(" cdnerr ")'):
        require(token in display, f"serial mailbox diagnostic missing: {token}")


def firmware_contract() -> None:
    text = (ROCK / "Lib/cdn_dp.pbi").read_text(encoding="utf-8")
    data = text.split("rock_dptx_firmware:", 1)[1].split("EndDataSection", 1)[0]
    firmware = bytes(int(value, 16) for value in re.findall(r"\$([0-9A-Fa-f]{2})(?![0-9A-Fa-f])", data))
    require(len(firmware) == 98320, f"embedded dptx firmware is {len(firmware)} bytes")
    digest = hashlib.sha256(firmware).hexdigest()
    require(digest == FIRMWARE_SHA256, f"embedded dptx firmware hash drifted: {digest}")
    total = int.from_bytes(firmware[0:4], "little")
    header = int.from_bytes(firmware[4:8], "little")
    iram = int.from_bytes(firmware[8:12], "little")
    dram = int.from_bytes(firmware[12:16], "little")
    require((total, header, iram, dram) == (98320, 16, 65536, 32768),
            "dptx firmware header/IRAM/DRAM contract drifted")


def arithmetic_contract() -> None:
    def pll_rate(con0: int, con1: int, con2: int, con3: int,
                 integer_only: bool) -> int | None:
        # RK3399 PLL_CON fields and formula from the pinned Rockchip drivers.
        if not con2 & 0x80000000 or ((con3 >> 8) & 3) != 1 or con3 & 1:
            return None
        if integer_only and not con3 & 8:
            return None
        fb = con0 & 0xFFF
        ref = con1 & 0x3F
        post1 = (con1 >> 8) & 7
        post2 = (con1 >> 12) & 7
        if not 16 <= fb <= 3200 or not ref or not post1 or not post2:
            return None
        fraction = 0 if con3 & 8 else con2 & 0xFFFFFF
        scaled = fb * 16777216 + fraction
        vco = (24000000 * scaled // ref) // 16777216
        rate = vco // post1 // post2
        if not 800000000 <= vco <= 3200000000:
            return None
        if not 16000000 <= rate <= 3200000000:
            return None
        return rate

    # The first tuple is the exact stock-silicon capture. The second is the
    # VPLL-specific 65 MHz entry in Radxa's pinned RK3399 clock table.
    require(pll_rate(0x64, 0x1301, 0x8000031F, 0x108, True) == 800000000,
            "captured 800 MHz GPLL decode drifted")
    require(pll_rate(0x71, 0x6701, 0x80C00000, 0x100, False) == 65000000,
            "pinned fractional VPLL 65 MHz decode drifted")
    require(pll_rate(0xC0, 0x1302, 0x8000031F, 0x8, True) is None,
            "slow-mode CPLL negative control was admitted")
    require(pll_rate(0x64, 0x1300, 0x8000031F, 0x108, True) is None,
            "zero REFDIV negative control was admitted")
    require(pll_rate(0xFFF, 0x1101, 0x80000000, 0x108, True) is None,
            "out-of-range PLL negative control was admitted")

    def ceiling_divider(parent: int, target: int) -> int:
        return (parent + target - 1) // target

    expected_clocks = {
        594000000: (0xCB, 0x85, 0x8200, 0x281, 99),
        800000000: (0xCF, 0x87, 0x8300, 0x381, 100),
    }
    for parent, expected_clock in expected_clocks.items():
        tcp = ceiling_divider(parent, 50000000)
        dp = ceiling_divider(parent, 100000000)
        spdif = ceiling_divider(parent, 200000000)
        aclk = ceiling_divider(parent, 400000000)
        hclk = ceiling_divider(parent // aclk, 100000000)
        actual = (0xC0 | tcp - 1, 0x80 | dp - 1,
                  0x8000 | ((spdif - 1) << 8),
                  0x80 | (aclk - 1) | ((hclk - 1) << 8),
                  (parent // dp) // 1000000)
        require(actual == expected_clock,
                f"GPLL-derived display clock plan drifted for {parent}: {actual}")

    required_mbps = (65000 * 24 + 999) // 1000
    for rate_mhz in (162, 270, 540):
        for lanes in (1, 2):
            carries = required_mbps <= rate_mhz * lanes * 8
            require(carries == ((rate_mhz, lanes) != (162, 1)),
                    f"1024x768 bandwidth admission drift for {rate_mhz} MHz/{lanes} lanes")
    expected = {(162, 2): (32, 19, 259, 4),
                (270, 2): (32, 11, 555, 5),
                (540, 2): (32, 5, 777, 4)}
    for (rate_mhz, lanes), answer in expected.items():
        selected = None
        for tu in range(32, 66, 2):
            scaled = tu * 65000 * 24 // (lanes * rate_mhz * 8)
            symbol, remainder = divmod(scaled, 1000)
            if symbol > 1 and tu - symbol >= 4 and 100 <= remainder <= 850:
                fifo = ((65000 * (symbol + 1) // 1000) + rate_mhz) // (lanes * rate_mhz)
                fifo = 8 * (symbol + 1) // 24 - fifo + 2
                selected = (tu, symbol, remainder, fifo)
                break
        require(selected == answer,
                f"TU model drift for {rate_mhz} MHz/{lanes} lanes: {selected}")
    # This is the exact unit error in the private U-Boot reference: retaining
    # kHz here produces no valid TU. Keep it as a negative control.
    bad = []
    for tu in range(32, 66, 2):
        scaled = tu * 65000 * 24 // (2 * 162000 * 8)
        symbol, remainder = divmod(scaled, 1000)
        if symbol > 1 and tu - symbol >= 4 and 100 <= remainder <= 850:
            bad.append(tu)
    require(not bad, "the known kHz/MHz TU mutation unexpectedly passed")
    source = (ROCK / "Lib/cdn_dp.pbi").read_text(encoding="utf-8").lower()
    require("linkmhz = 162" in source and "linkmhz = 162000" not in source,
            "TU implementation regressed to the kHz/MHz unit defect")


def mode_arithmetic_contract() -> None:
    def win0_control(width: int) -> int | None:
        if width < 1 or width > 2560:
            return None
        line_buffer_mode = 3 if width > 1920 else 4
        return 1 | (line_buffer_mode << 5)

    expected_win0 = {0: None, 1280: 0x81, 1920: 0x81,
                     1921: 0x61, 2560: 0x61, 2561: None}
    for width, expected_control in expected_win0.items():
        require(win0_control(width) == expected_control,
                f"WIN0 line-buffer control drifted at width {width}: "
                f"{win0_control(width)}")
    require(win0_control(1920) != 0xA1,
            "preferred 1080p retained the obsolete RGB1280 line-buffer control")

    preferred_dtd = detailed_timing(
        1920, 1080, 148500, 280, 88, 44, 45, 4, 5,
        hsync_positive=True, vsync_positive=True,
    )
    preferred_edid = base_edid(preferred_dtd)
    mode, source, reason = select_reference_mode(preferred_edid)
    require((mode, source, reason) ==
            (PREFERRED_1080P, "preferred", "preferred"),
            f"preferred 1080p DTD decoded incorrectly: {mode}, {source}, {reason}")

    # Polarity is semantic, not a synonym for one fixed mode. Exercise all four
    # separate-sync combinations while retaining the same variable geometry.
    for hpositive in (False, True):
        for vpositive in (False, True):
            candidate = base_edid(detailed_timing(
                1280, 720, 74250, 370, 110, 40, 30, 5, 5,
                hsync_positive=hpositive, vsync_positive=vpositive,
            ))
            selected, selected_source, selected_reason = select_reference_mode(candidate)
            require(selected_source == "preferred" and
                    selected_reason == "preferred" and
                    selected[9:11] == (int(hpositive), int(vpositive)),
                    "preferred-mode sync polarity was not preserved")
            # Cadence encodes negative polarity, while VOP owns positive bits.
            cdn_h = 0 if hpositive else 0x8000
            cdn_v = 0 if vpositive else 0x8000
            framer_sp = ((not hpositive) << 1) | (not vpositive)
            vop = int(hpositive) | (int(vpositive) << 1)
            require((bool(cdn_h), bool(cdn_v), vop) ==
                    (not hpositive, not vpositive,
                     int(hpositive) | (int(vpositive) << 1)),
                    "VOP/Cadence polarity model drifted")
            require(framer_sp == ({(False, False): 3, (False, True): 2,
                                   (True, False): 1, (True, True): 0}
                                  [(hpositive, vpositive)]),
                    "Cadence FRAMER_SP HSP/VSP bit assignment drifted")

    malformed = bytearray(preferred_edid)
    malformed[0] = 1
    bad_geometry = detailed_timing(
        1920, 1080, 148500, 100, 88, 44, 45, 4, 5,
        hsync_positive=True, vsync_positive=True,
    )
    oversized = detailed_timing(
        2564, 1080, 148500, 280, 88, 44, 45, 4, 5,
        hsync_positive=True, vsync_positive=True,
    )
    refused_cases = {
        "header": bytes(malformed),
        "checksum": base_edid(preferred_dtd, valid_checksum=False),
    }
    for expected_reason, candidate in refused_cases.items():
        selected, selected_source, selected_reason = select_reference_mode(candidate)
        require(selected is None and selected_source == "none" and
                selected_reason == expected_reason,
                f"untrusted EDID was admitted: {expected_reason} -> "
                f"{selected_source}, {selected_reason}, {selected}")

    fallback_cases = {
        "no-preferred-dtd": base_edid(bytes(18), advertise_fallback=True),
        "interlaced": base_edid(detailed_timing(
            1920, 1080, 74250, 280, 88, 44, 45, 4, 5,
            hsync_positive=True, vsync_positive=True, interlaced=True,
        ), advertise_fallback=True),
        "non-separate-sync": base_edid(
            preferred_dtd[:-1] + b"\x00", advertise_fallback=True),
        "geometry": base_edid(bad_geometry, advertise_fallback=True),
        "vop-limit": base_edid(oversized, advertise_fallback=True),
        "vpll-rate": base_edid(detailed_timing(
            640, 480, 24000, 160, 16, 96, 45, 10, 2,
            hsync_positive=True, vsync_positive=True,
        ), advertise_fallback=True),
    }
    for expected_reason, candidate in fallback_cases.items():
        selected, selected_source, selected_reason = select_reference_mode(candidate)
        require(selected == SAFE_MODE and selected_source == "fallback" and
                selected_reason == expected_reason,
                f"invalid preferred DTD did not fail to the safe mode: "
                f"{expected_reason} -> {selected_source}, {selected_reason}, "
                f"{selected}")

    no_advertised_fallback = base_edid(oversized)
    selected, selected_source, selected_reason = select_reference_mode(
        no_advertised_fallback)
    require(selected is None and selected_source == "none" and
            selected_reason == "vop-limit",
            "unsupported native mode silently succeeded without an advertised fallback")

    padded, padded_source, padded_reason = select_reference_mode(base_edid(
        detailed_timing(1366, 768, 85500, 426, 70, 143, 30, 3, 3,
                        hsync_positive=True, vsync_positive=False)))
    require(padded_source == "preferred" and padded_reason == "preferred" and
            padded is not None and padded[-1] == 5472,
            f"non-16-byte native pitch was not safely padded: {padded}")

    require(vpll_reference_plan(65000000) ==
            (1, 113, 7, 6, 0, 0xC00000, 65000000),
            "pinned Radxa 65 MHz VPLL tuple drifted")
    require(vpll_reference_plan(148500000) ==
            (1, 129, 7, 3, 0, 0xF00000, 148500000),
            "pinned Radxa 148.5 MHz VPLL tuple drifted")
    require(vpll_reference_plan(85500000) ==
            (8, 285, 2, 5, 1, 0, 85500000),
            "generic integer 85.5 MHz VPLL plan drifted")
    require(vpll_reference_plan(154000000) ==
            (2, 77, 1, 6, 1, 0, 154000000),
            "generic integer 154 MHz VPLL plan drifted")
    require(vpll_reference_plan(241500000) ==
            (4, 161, 1, 4, 1, 0, 241500000),
            "generic integer 241.5 MHz VPLL plan drifted")
    require(vpll_reference_plan(24000000) is None,
            "24 MHz fin=fout VPLL negative control was admitted")
    require(vpll_reference_plan(24010000) ==
            (1, 35, 5, 7, 0, 244667, 24009999),
            "24.01 MHz fractional VPLL boundary plan drifted")
    require(vpll_reference_plan(10000000) is None,
            "unrepresentable low VPLL rate was admitted")

    def link_carries(pixel_khz: int, link_mhz: int, lanes: int) -> bool:
        required_mbps = (pixel_khz * 24 + 999) // 1000
        return required_mbps <= link_mhz * lanes * 8

    require(not link_carries(148500, 162, 2) and
            link_carries(148500, 270, 2),
            "1080p link admission can silently accept an undersized 2-lane link")
    require(link_carries(65000, 162, 2),
            "safe-mode link admission rejected the baseline 2-lane link")

    def tu_for(pixel_khz: int, link_mhz: int, lanes: int) -> tuple[int, ...] | None:
        for tu in range(32, 66, 2):
            scaled = tu * pixel_khz * 24 // (lanes * link_mhz * 8)
            symbol, remainder = divmod(scaled, 1000)
            if symbol > 1 and tu - symbol >= 4 and 100 <= remainder <= 850:
                fifo = ((pixel_khz * (symbol + 1) // 1000) + link_mhz) // \
                       (lanes * link_mhz)
                fifo = 8 * (symbol + 1) // 24 - fifo + 2
                return tu, symbol, remainder, fifo
        return None

    expected_tu = {
        (65000, 162, 2): (32, 19, 259, 4),
        (65000, 270, 2): (32, 11, 555, 5),
        (148500, 162, 2): None,
        (148500, 270, 2): (32, 26, 400, 4),
        (148500, 540, 2): (32, 13, 200, 4),
    }
    for inputs, expected in expected_tu.items():
        require(tu_for(*inputs) == expected,
                f"variable-mode TU model drifted for {inputs}: {tu_for(*inputs)}")

    require(MAX_FRAMEBUFFER_BYTES == 16384000,
            "maximum preferred-mode framebuffer size drifted")
    require(0x02800000 + MAX_FRAMEBUFFER_BYTES + 16 <= 0x04000000,
            "maximum framebuffer cannot fit in the expanded BSS window")
    require(0x02800000 < 0x04000000 <= 0x04F00000 < 0x05000000 < 0x05100000,
            "code/BSS/stack/guard ownership windows overlap")


def emitted_mode_contract(compiler: Path, work: Path) -> None:
    """Execute the real emitted preferred-mode parser in the A64 model."""
    load = 0x02000040
    bss = 0x02800000
    stack = 0x05000000
    returned = 0x06000000
    edid_address = 0x07000000
    fixture = work / "rockpi4c_mode_fixture.rockpi4c"
    fixture.write_text(
        '; Desk-only selected-mode fixture. It must never be booted.\n'
        'XIncludeFile "RockPi4C/Lib/display_mode.pbi"\n\n'
        'Procedure.i Main()\n'
        f'  RockEdidCapsCollect(${edid_address:08X},1)\n'
        f'  ProcedureReturn RockModeSelect(${edid_address:08X})\n'
        'EndProcedure\n',
        encoding="utf-8", newline="\n",
    )
    image = work / "rockpi4c_mode_fixture.img"
    command = [
        str(compiler), "--compile", str(fixture), "-t", "rockpi4c",
        "--entry-returns", "--load-addr", hex(load), "--bss-addr", hex(bss),
        "--stack-addr", hex(stack), "-S", "-s", "-o", str(image),
    ]
    run = subprocess.run(
        command, cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)}, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
    )
    require(run.returncode == 0 and image.is_file(),
            "selected-mode fixture compile failed:\n" + run.stdout)
    symbol_file = Path(str(image) + ".sym")
    require(symbol_file.is_file(), "selected-mode fixture omitted its symbol map")
    symbols = {key.lower(): int(value, 0) for key, value in (
        line.split("=", 1) for line in symbol_file.read_text().splitlines()
        if "=" in line
    )}
    required = ["main", "rockmodeselect", "rockmodecommit",
                "rockedidcapscollect", "__bss_start__", "__bss_end__"] + [
                    f"global_rock_mode_{name}" for name in (
                    "width", "height", "pixel_hz", "htotal", "hsync_start",
                    "hsync_end", "vtotal", "vsync_start", "vsync_end",
                    "hsync_positive", "vsync_positive", "pitch", "source",
                    "reason", "valid")] + [f"global_rock_edid_{name}" for name in (
                    "block_count", "cap_count", "error", "range_count",
                    "extension_tag", "extension_parsed", "cap_source",
                    "cap_code", "cap_native", "cap_preferred", "cap_mapped", "cap_width",
                    "cap_height", "cap_refresh_millihz")]
    missing_symbols = [name for name in required if name not in symbols]
    require(not missing_symbols,
            "selected-mode fixture symbols are incomplete: " + ", ".join(missing_symbols))

    interpreter_path = ROOT / "tools/a64/a64_interp.py"
    spec = importlib.util.spec_from_file_location("rockpi4c_mode_a64", interpreter_path)
    require(spec is not None and spec.loader is not None,
            "cannot load the repository A64 interpreter")
    a64 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = a64
    spec.loader.exec_module(a64)
    blob = image.read_bytes()

    def signed(value: int) -> int:
        return value - (1 << 64) if value & (1 << 63) else value

    def run_case(edid: bytes) -> tuple[int, tuple[int, ...]]:
        cpu = a64.A64()
        for offset, byte in enumerate(blob):
            cpu.memory[load + offset] = byte
        for offset, byte in enumerate(edid):
            cpu.memory[edid_address + offset] = byte
        a64.attach_symbols(cpu, image, load)
        cpu.pc = load + symbols["rockmodeselect"]
        cpu.sp = stack
        cpu.x[0] = edid_address
        cpu.x[30] = returned
        for _ in range(1_000_000):
            if cpu.pc == returned:
                break
            cpu.step()
        else:
            raise AssertionError("emitted RockModeSelect did not return")
        values = []
        for name in ("width", "height", "pixel_hz", "htotal", "hsync_start",
                     "hsync_end", "vtotal", "vsync_start", "vsync_end",
                     "hsync_positive", "vsync_positive", "pitch", "source",
                     "reason", "valid"):
            address = symbols[f"global_rock_mode_{name}"]
            values.append(signed(cpu.load(address, 8)))
        return signed(cpu.x[0]), tuple(values)

    def run_caps(edid: bytes, blocks: int) -> tuple[int, dict[str, int],
                                                    list[tuple[int, ...]]]:
        cpu = a64.A64()
        for offset, byte in enumerate(blob):
            cpu.memory[load + offset] = byte
        for offset, byte in enumerate(edid):
            cpu.memory[edid_address + offset] = byte
        a64.attach_symbols(cpu, image, load)
        cpu.pc = load + symbols["rockedidcapscollect"]
        cpu.sp = stack
        cpu.x[0] = edid_address
        cpu.x[1] = blocks
        cpu.x[30] = returned
        for _ in range(2_000_000):
            if cpu.pc == returned:
                break
            cpu.step()
        else:
            raise AssertionError("emitted RockEdidCapsCollect did not return")
        scalar_names = ("block_count", "cap_count", "error", "range_count")
        state = {name: signed(cpu.load(symbols[f"global_rock_edid_{name}"], 8))
                 for name in scalar_names}
        records = []
        array_names = ("cap_source", "cap_code", "cap_native", "cap_preferred", "cap_mapped",
                       "cap_width", "cap_height", "cap_refresh_millihz")
        for slot in range(max(0, state["cap_count"])):
            records.append(tuple(signed(cpu.load(
                symbols[f"global_rock_edid_{name}"] + slot * 8, 8))
                for name in array_names))
        state["extension_tag_1"] = signed(cpu.load(
            symbols["global_rock_edid_extension_tag"] + 8, 8))
        state["extension_parsed_1"] = signed(cpu.load(
            symbols["global_rock_edid_extension_parsed"] + 8, 8))
        return signed(cpu.x[0]), state, records

    preferred = base_edid(detailed_timing(
        1920, 1080, 148500, 280, 88, 44, 45, 4, 5,
        hsync_positive=True, vsync_positive=True,
    ))
    result, values = run_case(preferred)
    require(result == 1 and values == PREFERRED_1080P + (1, 0, 1),
            f"emitted parser misdecoded preferred 1080p: {result}, {values}")

    padded = base_edid(detailed_timing(
        1366, 768, 85500, 426, 70, 143, 30, 3, 3,
        hsync_positive=True, vsync_positive=False,
    ))
    result, values = run_case(padded)
    expected_padded = (1366, 768, 85500000, 1792, 1436, 1579,
                       798, 771, 774, 1, 0, 5472, 1, 0, 1)
    require(result == 1 and values == expected_padded,
            f"emitted parser lost padded-pitch mode: {result}, {values}")

    no_dtd = base_edid(bytes(18), advertise_fallback=True)
    result, values = run_case(no_dtd)
    require(result == 1 and values == SAFE_MODE + (0, 5, 1),
            f"emitted parser lost advertised fallback: {result}, {values}")

    interlaced = base_edid(detailed_timing(
        1920, 1080, 74250, 280, 88, 44, 45, 4, 5,
        hsync_positive=True, vsync_positive=True, interlaced=True,
    ), advertise_fallback=True)
    result, values = run_case(interlaced)
    require(result == 1 and values == SAFE_MODE + (0, 6, 1),
            f"emitted parser did not reject interlace: {result}, {values}")

    malformed = base_edid(preferred[54:72], valid_checksum=False)
    result, values = run_case(malformed)
    require(result == 0 and values[-3:] == (-1, 3, 0),
            f"emitted parser admitted malformed EDID: {result}, {values}")

    over_link = base_edid(detailed_timing(
        1920, 1080, 594000, 280, 88, 44, 45, 4, 5,
        hsync_positive=True, vsync_positive=True,
    ))
    result, values = run_case(over_link)
    require(result == 0 and values[-3:] == (-1, 14, 0),
            f"emitted parser silently admitted an unsupported native mode: "
            f"{result}, {values}")

    complete = capability_test_edid()
    result, state, records = run_caps(complete, 2)
    require(result == 1 and state == {
        "block_count": 2, "cap_count": 7, "error": 0, "range_count": 1,
        "extension_tag_1": 2, "extension_parsed_1": 1,
    }, f"emitted EDID inventory state drifted: {result}, {state}")
    require((4, 127, 0, 0, 0, 0, 0, 0) in records,
            f"unsupported CTA VIC was hidden or synthesized: {records}")
    require((3, 0, 0, 1, 1, 1920, 1080, 60000) in records and
            (4, 16, 1, 0, 1, 1920, 1080, 60000) in records and
            (5, 0, 1, 0, 1, 1920, 1080, 120000) in records,
            f"CTA native/SVD/DTD capability identity drifted: {records}")

    bad_checksum = bytearray(complete)
    bad_checksum[-1] ^= 1
    result, state, _ = run_caps(bytes(bad_checksum), 2)
    require(result == 0 and state["error"] == 3,
            f"bad extension checksum was admitted: {result}, {state}")

    truncated = bytearray(complete)
    truncated[128 + 2] = 6
    truncated[128:256] = checksum_edid_block(truncated[128:256])
    result, state, _ = run_caps(bytes(truncated), 2)
    require(result == 0 and state["error"] == 7,
            f"truncated CTA data block was admitted: {result}, {state}")

    unknown = bytearray(complete)
    unknown[128] = 0x70
    unknown[128:256] = checksum_edid_block(unknown[128:256])
    result, state, records = run_caps(bytes(unknown), 2)
    require(result == 1 and state["extension_tag_1"] == 0x70 and
            state["extension_parsed_1"] == 0 and len(records) == 3,
            f"valid unknown extension was not honestly reported: {result}, {state}")

    result, state, _ = run_caps(complete, 1)
    require(result == 0 and state["error"] == 1,
            f"truncated advertised extension set was admitted: {result}, {state}")


def emitted_line_buffer_contract(image: Path, symbols: dict[str, int]) -> None:
    """Execute the production line-buffer selector from the full image."""
    load = 0x02000040
    returned = 0x06000000
    procedure = symbols.get("rockvoplinebuffermode")
    require(procedure is not None,
            "full image omitted RockVopLineBufferMode")
    spec = importlib.util.spec_from_file_location(
        "rockpi4c_line_buffer_a64", ROOT / "tools/a64/a64_interp.py")
    require(spec is not None and spec.loader is not None,
            "cannot load the repository A64 interpreter")
    a64 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = a64
    spec.loader.exec_module(a64)
    blob = image.read_bytes()

    def selected(width: int) -> int:
        cpu = a64.A64()
        for offset, byte in enumerate(blob):
            cpu.memory[load + offset] = byte
        a64.attach_symbols(cpu, image, load)
        cpu.pc = load + procedure
        cpu.sp = 0x05000000
        cpu.x[0] = width & ((1 << 64) - 1)
        cpu.x[30] = returned
        for _ in range(10_000):
            if cpu.pc == returned:
                value = cpu.x[0]
                return value - (1 << 64) if value & (1 << 63) else value
            cpu.step()
        raise AssertionError("emitted RockVopLineBufferMode did not return")

    expected = {0: -1, 1280: 4, 1920: 4, 1921: 3, 2560: 3, 2561: -1}
    for width, mode in expected.items():
        actual = selected(width)
        require(actual == mode,
                f"emitted line-buffer mode drifted at {width}: {actual}, expected {mode}")
        if mode >= 0:
            control = 1 | (actual << 5)
            require(control == (0x81 if width <= 1920 else 0x61),
                    f"emitted WIN0 control is wrong at {width}: {control:#x}")


def emitted_cdn_video_contract(image: Path, symbols: dict[str, int]) -> None:
    """Execute production CDN timing math with mailbox writes modeled."""
    load = 0x02000040
    returned = 0x06000000
    required = ("rockcdnvideomode", "rockcdnregwrite", "rockcdnregfield")
    require(all(name in symbols for name in required),
            "full image omitted the Cadence video arithmetic call chain")
    spec = importlib.util.spec_from_file_location(
        "rockpi4c_cdn_video_a64", ROOT / "tools/a64/a64_interp.py")
    require(spec is not None and spec.loader is not None,
            "cannot load the repository A64 interpreter")
    a64 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = a64
    spec.loader.exec_module(a64)
    blob = image.read_bytes()

    mode = {
        "rock_mode_width": 1920, "rock_mode_height": 1080,
        "rock_mode_pixel_hz": 148500000, "rock_mode_htotal": 2200,
        "rock_mode_hsync_start": 2008, "rock_mode_hsync_end": 2052,
        "rock_mode_vtotal": 1125, "rock_mode_vsync_start": 1084,
        "rock_mode_vsync_end": 1089, "rock_mode_pitch": 7680,
        "rock_mode_valid": 1, "rock_cdn_link_rate": 20,
        "rock_cdn_link_lanes": 2,
    }

    def absolute(name: str) -> int:
        return load + symbols[name]

    def run_case(hpositive: bool, vpositive: bool) -> None:
        cpu = a64.A64()
        for offset, byte in enumerate(blob):
            cpu.memory[load + offset] = byte
        for name, value in mode.items():
            cpu.raw_store(symbols["global_" + name], value, 8)
        cpu.raw_store(symbols["global_rock_mode_hsync_positive"], int(hpositive), 8)
        cpu.raw_store(symbols["global_rock_mode_vsync_positive"], int(vpositive), 8)
        a64.attach_symbols(cpu, image, load)
        writes: list[tuple[int, int]] = []
        fields: list[tuple[int, int, int, int]] = []
        cpu.pc = absolute("rockcdnvideomode")
        cpu.sp = 0x05000000
        cpu.x[30] = returned
        for _ in range(100_000):
            if cpu.pc == returned:
                break
            if cpu.pc == absolute("rockcdnregwrite"):
                writes.append((cpu.x[0], cpu.x[1]))
                cpu.x[0] = 1
                cpu.pc = cpu.x[30]
                continue
            if cpu.pc == absolute("rockcdnregfield"):
                fields.append(tuple(cpu.x[:4]))
                cpu.x[0] = 1
                cpu.pc = cpu.x[30]
                continue
            cpu.step()
        else:
            raise AssertionError("emitted RockCdnVideoMode did not return")
        require(cpu.x[0] == 1, "emitted 1080p Cadence video setup refused")
        negative_h, negative_v = int(not hpositive), int(not vpositive)
        expected = [
            (0x0B00, 0x2000), (0x0B10, 0),
            # HBR2 x2: TU=32, VS=13. TU_CNT_RST_EN is pinned bit 15.
            (0x2208, 0x8000 | (32 << 8) | 13), (0x2254, 4),
            (0x220C, 0x102),
            (0x2210, (negative_h << 1) | negative_v),
            (0x2278, (88 << 16) | 148), (0x227C, 1920 * 3),
            (0x2280, 2200 | (192 << 16)),
            (0x2284, 44 | (negative_h << 15) | (1920 << 16)),
            (0x2288, 1125 | (41 << 16)),
            (0x228C, 5 | (negative_v << 15) | (1080 << 16)),
            (0x2290, 32), (0x2294, 1),
            (0x22B0, 44 | (1920 << 16)),
            (0x22B4, 1080 | (41 << 16)), (0x22B8, 1125),
        ]
        require(writes == expected,
                f"emitted CDN timing differs for H{int(hpositive)}V{int(vpositive)}: "
                f"{writes!r}")
        require(fields == [(0x2258, 2, 1, 0)],
                f"emitted CDN video-valid field drifted: {fields!r}")

    for hpositive in (False, True):
        for vpositive in (False, True):
            run_case(hpositive, vpositive)


def compiler_contract(compiler: Path) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="anvil-rockpi4c-display-") as temp_name:
        emitted_mode_contract(compiler, Path(temp_name))
        output = Path(temp_name) / "display.img"
        command = [
            str(compiler), "--compile", "RockPi4C/Board/board.rockpi4c",
            "-t", "rockpi4c", "--load-addr", "0x02000040",
            "--bss-addr", "0x02800000", "--stack-addr", "0x05000000",
            "--jobs", "auto", "-S", "-o", str(output),
        ]
        run = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=300)
        require(run.returncode == 0, "Rock Pi display compile failed:\n" + run.stdout)
        require(output.is_file() and output.stat().st_size > 98320,
                "compiler wrote no complete firmware-bearing image")
        for suffix in (".pmf", ".asm", ".sym", ".sym.meta"):
            require(Path(str(output) + suffix).is_file(), f"compiler omitted {suffix}")
        # Count the successful compiler invocation before any emitted-code
        # assertion can fail. A red gate is still a real board build.
        counted = build_count.record_build(
            ROCK / "Board/board.rockpi4c", "rockpi4c", output,
            by="tools/rockpi4c_display_check.py", compiler=compiler,
        )
        print(f"  build count: {counted.message}")
        asm = Path(str(output) + ".asm").read_text(encoding="utf-8", errors="replace").lower()
        for token in ("str w", "ldr w", "rockdisplayup"):
            require(token in asm, f"emitted display image lacks {token}")
        for label in ("rockdisplaydppowertelemetry:",
                      "rockdisplayfirmwaretelemetry:",
                      "rockdisplaytcphytelemetry:",
                      "rockdisplaygrftelemetry:",
                      "rockdisplaysubsystemtelemetry:",
                      "rockcdnmailboxwitnessreset:",
                      "rockmodeselect:",
                      "rockmodecommit:",
                      "rockcrupllrate:",
                      "rockcruceilingdivider:",
                      "rockcruvpllmode:",
                      "rockvopmodevalid:",
                      "rockvopupmode:",
                      "rockcdnlinkcarriesmode:",
                      "rockcdnvideomode:"):
            require(label in asm, f"emitted silicon witness is missing: {label}")
        display_up_asm = asm.split("rockdisplayup:", 1)[1].split(
            "rockdisplaybuffer:", 1
        )[0]
        emitted_witnesses = [
            "bl rockdisplaydppowertelemetry", "bl rockdisplayfirmwaretelemetry",
            "bl rockdisplaytcphytelemetry", "bl rockdisplaygrftelemetry",
        ]
        positions = [display_up_asm.index(call) for call in emitted_witnesses]
        require(positions == sorted(positions),
                "emitted stage-local silicon witness order drifted")
        display_source = (ROCK / "Lib/display.pbi").read_text(
            encoding="utf-8").lower()
        display_source_up = display_source.split(
            "procedure.i rockdisplayup()", 1)[1].split("endprocedure", 1)[0]
        expected_subsystem_witnesses = display_source_up.count(
            "rockdisplaysubsystemtelemetry(")
        require(expected_subsystem_witnesses > 0 and
                display_up_asm.count("bl rockdisplaysubsystemtelemetry") ==
                expected_subsystem_witnesses,
                "emitted subsystem error witnesses differ from guarded source branches")
        require("global_rock_cru_dp_core_rate" in display_up_asm,
                "emitted Cadence setup lost the live core-clock handoff")
        dpcd_telemetry_asm = asm.split("rockdisplaydpcdtelemetry:", 1)[1].split(
            "rockdisplayup:", 1
        )[0]
        require("bl rockdisplaymailboxtelemetry" in dpcd_telemetry_asm,
                "emitted DPCD failure lost its partial-header witness")
        for unsafe in ("bl rockcdnmailboxget", "bl rockcdnreceive",
                       "bl rockcdnlastauxstatus", "bl rockcdnsend"):
            require(unsafe not in dpcd_telemetry_asm,
                    f"emitted DPCD telemetry performs unsafe mailbox traffic: {unsafe}")
        power_asm = asm.split("rockcrudisplaypower:", 1)[1].split(
            "rockcrudisplayprepare:", 1
        )[0]
        power_calls = [(match.start(), match.group(1)) for match in re.finditer(
            r"\bbl\s+(rockpmupoweron|rockpmuidlerelease)\b", power_asm
        )]
        require([name for _, name in power_calls[:4]] ==
                ["rockpmupoweron", "rockpmuidlerelease",
                 "rockpmupoweron", "rockpmuidlerelease"],
                "emitted VIO/HDCP power calls drifted")
        for first, second in ((power_calls[0][0], power_calls[1][0]),
                              (power_calls[2][0], power_calls[3][0])):
            require(re.search(r"\bret\b", power_asm[first:second]) is not None,
                    "emitted domain failure cannot return before idle release")
        prepare_asm = asm.split("rockcrudisplayprepare:", 1)[1].split(
            "rockcrucadencerelease:", 1
        )[0]
        require(len(re.findall(r"\bbl\s+rockcrureset\b", prepare_asm)) == 10,
                "emitted prepare no longer leaves all asserted display resets held")
        tcphy_up_asm = asm.split("rocktcphyup:", 1)[1].split(
            "rockcdnmailboxwitnessreset:", 1
        )[0]
        tcphy_resets = [match.start() for match in re.finditer(
            r"\bbl\s+rockcrureset\b", tcphy_up_asm
        )]
        require(len(tcphy_resets) == 3,
                "emitted TCPHY reset-release count drifted")
        common = tcphy_up_asm.index("bl rocktccommon24m")
        pll = tcphy_up_asm.index("bl rocktcdprbrpll")
        waits = [match.start() for match in re.finditer(
            r"\bbl\s+rocktcwaitmask\b", tcphy_up_asm
        )]
        calibrate = tcphy_up_asm.index("bl rocktcauxcalibrate")
        power_state = tcphy_up_asm.index("bl rocktcpowerstate")
        require(len(waits) == 2 and
                tcphy_resets[0] < common < pll < tcphy_resets[1] < waits[0] <
                tcphy_resets[2] < waits[1] < calibrate < power_state,
                "emitted TCPHY config/reset/readiness order drifted")
        video_asm = asm.split("rockcdnvideomode:", 1)[1].split(
            "rock_dptx_firmware:", 1)[0]
        reg_writes = [match.start() for match in re.finditer(
            r"\bbl\s+rockcdnregwrite\b", video_asm
        )]
        require(len(reg_writes) == 17,
                f"emitted video register-write count drifted: {len(reg_writes)}")
        for first, second in zip(reg_writes, reg_writes[1:]):
            require(re.search(r"\bret\b", video_asm[first:second]) is not None,
                    "emitted Cadence failure can reach a later mailbox write")
        send_asm = asm.split("rockcdnsend:", 1)[1].split("rockcdnreceive:", 1)[0]
        header_puts = [match.start() for match in re.finditer(
            r"\bbl\s+rockcdnmailboxput\b", send_asm
        )]
        require(len(header_puts) == 5,
                f"emitted mailbox put count drifted: {len(header_puts)}")
        for first, second in zip(header_puts, header_puts[1:]):
            require(re.search(r"\bret\b", send_asm[first:second]) is not None,
                    "emitted mailbox header failure can reach its next byte")
        edid_asm = asm.split("rockcdnreadedidblock:", 1)[1].split(
            "rockcdnreadedid:", 1)[0]
        edid_send_call = edid_asm.index("bl rockcdnsend")
        edid_receive_call = edid_asm.index("bl rockcdnreceive")
        require(re.search(r"\bret\b", edid_asm[edid_send_call:edid_receive_call]) is not None,
                "emitted EDID send failure can reach receive/retry")
        # Immediate spelling is an assembler-format detail (the compiler normally
        # synthesizes 32-bit colours with MOVZ/MOVK). Assert the pattern in source
        # and require its renderer plus 32-bit stores in the emitted program.
        vop = (ROCK / "Lib/vop.pbi").read_text(encoding="utf-8").lower()
        for colour in ("$ffffffff", "$ffffff00", "$ff00ffff", "$ff00ff00",
                       "$ffff00ff", "$ffff0000", "$ff0000ff", "$ff101010",
                       "$ff40ff40"):
            require(colour in vop, f"first-frame colour missing: {colour}")
        first_frame = asm.split("rockvopfirstframe:", 1)[1].split(
            "rockvopmodevalid:", 1)[0]
        require("str w" in first_frame and "rockvoptext" in first_frame,
                "emitted first-frame renderer lacks pixel stores or text")
        require("ldr x" not in "\n".join(line for line in asm.splitlines()
                                         if "fec00000" in line or "ff7c0000" in line),
                "64-bit load emitted at a display MMIO base")
        symbols = Path(str(output) + ".sym").read_text(encoding="utf-8")
        values = dict(re.findall(r"^([A-Za-z0-9_]+)=([0-9]+)$", symbols, re.M))
        emitted_line_buffer_contract(
            output, {name.lower(): int(value) for name, value in values.items()})
        emitted_cdn_video_contract(
            output, {name.lower(): int(value) for name, value in values.items()})
        metadata = Path(str(output) + ".sym.meta").read_text(encoding="utf-8")
        sizes = {name: int(size) for name, size in
                 re.findall(r"^([^|]+)\|([0-9]+)\|", metadata, re.M)}
        bss_start = int(values["__bss_start__"])
        bss_end = int(values["__bss_end__"])
        framebuffer_storage = int(values["global_rock_vop_framebuffer"])
        framebuffer = (framebuffer_storage + 15) & ~15
        require(bss_start == 0x02800000 and bss_end <= 0x04000000,
                f"display BSS escaped its owned window: {bss_start:#x}..{bss_end:#x}")
        require(framebuffer % 16 == 0 and
                framebuffer + MAX_FRAMEBUFFER_BYTES <= bss_end,
                f"framebuffer is misaligned or not fully allocated: "
                f"buffer={framebuffer:#x}, "
                f"end={framebuffer + MAX_FRAMEBUFFER_BYTES:#x}, "
                f"bss_end={bss_end:#x}")
        storage_size = sizes.get("global_rock_vop_framebuffer")
        require(storage_size == MAX_FRAMEBUFFER_BYTES + 16,
                "framebuffer storage lacks exactly one alignment unit of slack")
        require(framebuffer + MAX_FRAMEBUFFER_BYTES <=
                framebuffer_storage + storage_size,
                "aligned framebuffer escaped its backing object")
        return output.stat().st_size, hashlib.sha256(output.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    source_contract()
    firmware_contract()
    arithmetic_contract()
    mode_arithmetic_contract()
    if args.compiler:
        size, digest = compiler_contract(args.compiler.resolve())
        print(f"emitted image: {size} bytes, SHA-256 {digest}")
    print("ROCK Pi 4C MiniDP desk gate: PASS")
    print("silicon: NOT RUN; next witness is numbered UART stages then selected-mode bars/text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
