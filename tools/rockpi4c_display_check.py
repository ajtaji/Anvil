#!/usr/bin/env python3
"""Desk gate for the original Rock Pi 4C RK3399 MiniDP first-light path."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

import build_count

ROOT = Path(__file__).resolve().parents[1]
ROCK = ROOT / "RockPi4C"
FIRMWARE_SHA256 = "203c5f061fb5075e4ca5398f8becc74e7cc450b494af857da5400788a7eae20b"


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
        "rockcruvpll65()", "$1fdf,$0080 | (aclkdivider-1)",
        "rockcdnfirmwareload", "rockcdnhotplug", "rockcdndpcd",
        "rockcdnreadedid", "rockcdntrain", "rockcdnvideo1024x768",
        "rockvopup1024x768", "dp08 visible 1024x768",
    ):
        require(token in joined, f"missing display contract token: {token}")
    board = (ROCK / "Board/board.rockpi4c").read_text(encoding="utf-8").lower()
    for include in ("cru.pbi", "tcphy.pbi", "cdn_dp.pbi", "vop.pbi", "display.pbi"):
        require(include in board, f"composition root omits {include}")
    require('xincludefile "raspberrypi4/' not in board,
            "Pi 4 hardware leaked into Rock Pi composition root")
    display = libraries["display.pbi"].lower()
    display_up = display.split("procedure.i rockdisplayup()", 1)[1].split(
        "endprocedure", 1
    )[0]
    order = [
        "rockcrudisplayprepare", "rockcrucadencerelease", "rockcdninternalclocks",
        "rockcdnfirmwareload", "rockcdnfirmwareactive", "rockcdnenableevents",
        "rocktcphyup", "$30003000", "rockcdnhotplug",
        "rockcdnhostcapabilities", "rockcdndpcd", "rockcdnreadedid",
        "rockvopup1024x768", "rockcdntrain", "rockcdnvideostatus(0)",
        "rockcdnvideo1024x768", "rockcdnvideostatus(1)",
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
        "rockvopup1024x768()": ("dpea vop err ", "rock_vop_error"),
        "rockcdntrain()": ("dpeb cdn err ", "rock_cdn_error"),
        "rockcdnvideostatus(0)": ("dpec cdn err ", "rock_cdn_error"),
        "rockcdnvideo1024x768()": ("dped cdn err ", "rock_cdn_error"),
        "rockcdnvideostatus(1)": ("dpee cdn err ", "rock_cdn_error"),
    }
    for owner_call, (label, error) in failure_witnesses.items():
        failure = display_up.split(f"if {owner_call}=0", 1)[1].split("endif", 1)[0]
        require(f'rockdisplaysubsystemtelemetry("{label}",{error})' in failure and
                failure.index("rockdisplaysubsystemtelemetry") <
                failure.index("rockdisplayfail"),
                f"{owner_call} no longer reports its exact subsystem error")
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
    require("rockcrureset(148,1)" in prepare and
            "rockcrureset(149,1)" in prepare and
            "rockcrureset(332,1)" in prepare and
            "rockcrureset(332,0)" not in prepare,
            "TCPHY/UPHY/PIPE resets are not held through owner pre-init")
    tcphy = libraries["tcphy.pbi"].lower()
    tcphy_up = tcphy.split("procedure.i rocktcphyup()", 1)[1].split(
        "endprocedure", 1
    )[0]
    tcphy_order = [
        "pokel(#rock_grf+$e588,$40004000)",
        "pokel(#rock_grf+$e580,$00080000)",
        "rockcrureset(149,0)",
        "pokel(#rock_grf+$e580,$00010000)",
        "rocktcread(#tcphy_tx_ana1)",
        "rocktccommon24m()", "rocktcwrite(#tcphy_pma_lane_cfg,$5100)",
        "rocktcdprbrpll()", "rocktcwrite(#tcphy_dp_mode_ctl",
        "rockcrureset(148,0)",
        "rocktcwaitmask(#tcphy_pma_cmn_ctrl1,1,1,100000)",
        "rockcrureset(332,0)", "pokel(#rock_grf+$6268,$00080000)",
        "rocktcwaitmask(#tcphy_dp_mode_ctl,$40,$40,100000)",
        "rocktcauxcalibrate()", "rocktcpowerstate(0)",
    ]
    positions = [tcphy_up.index(token) for token in tcphy_order]
    require(positions == sorted(positions),
            "TCPHY pre-init/config/reset/readiness order drifted from pinned owner")
    require("rock_tcphy_error=47" in tcphy_up,
            "PIPE reset-release failure lacks an exact TCPHY refusal code")
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
                  "rock_cru_error=errorcode",
                  "rock_cru_error=errorcode+1",
                  "rock_cru_error=errorcode+2"):
        require(token in cru, f"DPE1 PLL refusal mapping drifted: {token}")
    for token in ("rockcrufield($cc,$0300,$0000)",
                  "rockcrufield($cc,$0001,$0001)",
                  "rockcrufield($c0,$0fff,$0071)",
                  "rockcrufield($c4,$773f,$6701)",
                  "rockcruwrite($c8,(con2 & $ff000000) | $00c00000)",
                  "rockcrufield($cc,$0008,$0000)",
                  "rockcrufield($cc,$0001,$0000)",
                  "rockcruwait($c8,$80000000,$80000000)",
                  "rockcrufield($cc,$0300,$0100)",
                  "rockcrufield(#rock_cru_clksel+$c8,$0bff,$0000)"):
        require(token in cru, f"exact 65 MHz VPLL owner sequence drifted: {token}")
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
    for timing in (
        "rockvopwrite(#vop_hact,1320 | (296 << 16))",
        "rockvopwrite(#vop_vact,803 | (35 << 16))",
        "rockvopwrite(#vop_post_hact,1320 | (296 << 16))",
        "rockvopwrite(#vop_post_vact,803 | (35 << 16))",
    ):
        require(timing in vop, f"VOP start/end field order drifted: {timing}")
    require("rockvopfield(#vop_dsp_ctrl1,$000f0000,0)" in vop and
            "rockvopfield(#vop_dsp_ctrl1,$000f0000,$00080000)" not in vop,
            "VOP DP clock/pin polarity drifted from the pinned RK3399 path")
    cdn = libraries["cdn_dp.pbi"].lower()
    for timing in (
        "#cdn_sync_negative = $8000",
        "rockcdnregwrite(#cdn_framer_sp,3)",
        "136 | #cdn_sync_negative | (1024 << 16)",
        "6 | #cdn_sync_negative | (768 << 16)",
    ):
        require(timing in cdn,
                f"Cadence negative-sync encoding drifted: {timing}")
    require("rockcdnlinkcarries1024x768(linkmhz)" in cdn,
            "1024x768 link-bandwidth admission check missing")
    require("requiredmbps.i = (65000 * 24 + 999) / 1000" in cdn and
            "availablembps = linkmhz * rock_cdn_link_lanes * 8" in cdn,
            "1024x768 link-bandwidth arithmetic drifted")
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
        "procedure.i rockcdnreadedidblock", 1)[0]
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
        "procedure.i rockcdnedidsupports1024x768", 1
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


def compiler_contract(compiler: Path) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="anvil-rockpi4c-display-") as temp_name:
        output = Path(temp_name) / "display.img"
        command = [
            str(compiler), "--compile", "RockPi4C/Board/board.rockpi4c",
            "-t", "rockpi4c", "--load-addr", "0x02000040",
            "--bss-addr", "0x02800000", "--stack-addr", "0x03000000",
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
                      "rockcrupllrate:",
                      "rockcruceilingdivider:",
                      "rockcruvpll65:"):
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
        require(display_up_asm.count("bl rockdisplaysubsystemtelemetry") == 13,
                "emitted subsystem error witnesses are incomplete")
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
        video_asm = asm.split("rockcdnvideo1024x768:", 1)[1].split(
            "rockcdnvideostatus:", 1
        )[0]
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
            "rockcdnedidsupports1024x768:", 1
        )[0]
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
        first_frame = asm.split("rockvopfirstframe:", 1)[1].split("rockvopup1024x768:", 1)[0]
        require("str w" in first_frame and "rockvoptext" in first_frame,
                "emitted first-frame renderer lacks pixel stores or text")
        require("ldr x" not in "\n".join(line for line in asm.splitlines()
                                         if "fec00000" in line or "ff7c0000" in line),
                "64-bit load emitted at a display MMIO base")
        symbols = Path(str(output) + ".sym").read_text(encoding="utf-8")
        values = dict(re.findall(r"^([A-Za-z0-9_]+)=([0-9]+)$", symbols, re.M))
        metadata = Path(str(output) + ".sym.meta").read_text(encoding="utf-8")
        sizes = {name: int(size) for name, size in
                 re.findall(r"^([^|]+)\|([0-9]+)\|", metadata, re.M)}
        bss_start = int(values["__bss_start__"])
        bss_end = int(values["__bss_end__"])
        framebuffer_storage = int(values["global_rock_vop_framebuffer"])
        framebuffer = (framebuffer_storage + 15) & ~15
        require(bss_start == 0x02800000 and bss_end <= 0x02C00000,
                f"display BSS escaped its owned window: {bss_start:#x}..{bss_end:#x}")
        require(framebuffer % 16 == 0 and framebuffer + 1024 * 768 * 4 <= bss_end,
                f"framebuffer is misaligned or not fully allocated: "
                f"buffer={framebuffer:#x}, end={framebuffer + 1024 * 768 * 4:#x}, "
                f"bss_end={bss_end:#x}")
        storage_size = sizes.get("global_rock_vop_framebuffer")
        require(storage_size == 1024 * 768 * 4 + 16,
                "framebuffer storage lacks exactly one alignment unit of slack")
        require(framebuffer + 1024 * 768 * 4 <= framebuffer_storage + storage_size,
                "aligned framebuffer escaped its backing object")
        return output.stat().st_size, hashlib.sha256(output.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    source_contract()
    firmware_contract()
    arithmetic_contract()
    if args.compiler:
        size, digest = compiler_contract(args.compiler.resolve())
        print(f"emitted image: {size} bytes, SHA-256 {digest}")
    print("ROCK Pi 4C MiniDP desk gate: PASS")
    print("silicon: NOT RUN; next witness is numbered UART stages then 1024x768 bars/text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
