#!/usr/bin/env python3
"""Desk gate for the ROCK Pi 4C MiniDP link: host link training and the
per-rate Type-C PHY owner.

Reference: the shipped Radxa kernel that drove this connector at 1920x1080,
linux-image-4.4.154-116 (same cdn-dp sources as the 2020 -110 image),
decompiled: cdn_dp_train_link, cdn_dp_software_train_link, cdn_dp_set_pattern,
cdn_dp_set_link_train, cdn_dp_get_adjust_train, typec_dp_phy_config; plus the
5.10.110-6 binary's tcphy_dp_cfg_lane and PLL tables. The rule it pins:

  * the HOST trains the link first and re-programs TCPHY PLL1, the clock
    dividers and each lane's PLL clock select for RBR/HBR/HBR2;
  * firmware training (DPTX_TRAINING_CONTROL) is only the fallback, and only
    that path sends SET_VIDEO idle/valid;
  * 1920x1080@60 (148.5 MHz, 24 bpp) does not fit RBR x2 and must be carried
    by HBR or HBR2;
  * a native attempt that fails at or after link training is followed by ONE
    cold retry on the pre-host-training path: WIN0 stopped, the whole chain
    from the CRU resets up again, firmware training on the cold RBR PHY and
    the established 1024x768@60 mode.

It fails on the pre-fix source, where RockDisplayUp called the firmware
training alone and the PHY stayed at its cold RBR setup.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"rockpi4c_dp_link_training_check: FAIL: {message}")


def procedure(source: str, name: str) -> str:
    match = re.search(
        rf"procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)(.*?)endprocedure",
        source,
        re.DOTALL,
    )
    require(match is not None, f"missing {name} procedure")
    return match.group(1)


def ordered(body: str, tokens: tuple[str, ...], contract: str) -> None:
    position = -1
    for token in tokens:
        found = body.find(token, position + 1)
        require(found >= 0, f"{contract}: missing or out of order: {token}")
        position = found


# (register constant, value) in write order, from the pinned 4.4 source and
# byte-identical to 5.10.110-6 dp_pll_rbr_ssc_cfg / dp_pll_hbr(2)_ssc_cfg.
PLL_RBR = (
    ("vcocal_init", "$f0"), ("vcocal_iter", "$18"), ("vcocal_start", "$30b9"),
    ("pll1_intdiv", "$86"), ("pll1_fracdiv", "$f915"), ("pll1_high_thr", "$22"),
    ("pll1_ss_ctrl1", "$140"), ("pll1_ss_ctrl2", "$7f03"), ("pll1_dsm_diag", "$20"),
    ("pllsm1_user", "0"), ("pll1_ovrd", "0"), ("pll1_fbh", "0"), ("pll1_fbl", "0"),
    ("pll1_v2i", "6"), ("pll1_cp", "$45"), ("pll1_lf", "8"), ("pll1_ptat1", "$100"),
    ("pll1_ptat2", "7"), ("pll1_inclk", "1"),
)
PLL_HBR = (
    ("vcocal_init", "$f0"), ("vcocal_iter", "$18"), ("vcocal_start", "$30b4"),
    ("pll1_intdiv", "$e0"), ("pll1_fracdiv", "$f479"), ("pll1_high_thr", "$38"),
    ("pll1_ss_ctrl1", "$204"), ("pll1_ss_ctrl2", "$7f03"), ("pll1_dsm_diag", "$20"),
    ("pllsm1_user", "$1000"), ("pll1_ovrd", "0"), ("pll1_fbh", "0"), ("pll1_fbl", "0"),
    ("pll1_v2i", "7"), ("pll1_cp", "$45"), ("pll1_lf", "8"), ("pll1_ptat1", "1"),
    ("pll1_ptat2", "1"), ("pll1_inclk", "1"),
)


def pll_writes(block: str) -> list[tuple[str, str]]:
    return re.findall(r"rocktcwrite\(#tcphy_(?:cmn_)?(\w+),([^)]+)\)", block)


def check_tcphy(source: str) -> None:
    for token in ("#tcphy_dp_rate_rbr = 162000", "#tcphy_dp_rate_hbr = 270000",
                  "#tcphy_dp_rate_hbr2 = 540000", "#tcphy_dp_mode_timeout_us = 100000"):
        require(token in source, f"missing pinned constant {token}")

    load = procedure(source, "rocktcdppllload")
    split = load.index("else")
    rbr = [(n.replace("pll1_vcocal", "vcocal"), v.strip()) for n, v in pll_writes(load[:split])]
    hbr = [(n.replace("pll1_vcocal", "vcocal"), v.strip()) for n, v in pll_writes(load[split:])]
    require(tuple(rbr) == PLL_RBR, f"RBR PLL1 table drifted: {rbr}")
    require(tuple(hbr) == PLL_HBR, f"HBR/HBR2 PLL1 table drifted: {hbr}")

    cold = procedure(source, "rocktcdprbrpll")
    ordered(cold, ("#tcphy_dp_clk_ctl,$2405", "| $30", "rocktcdppllload(#tcphy_dp_rate_rbr)",
                   "rock_tcphy_dp_rate=#tcphy_dp_rate_rbr"), "cold tcphy_cfg_dp_pll(RBR)")

    lane = procedure(source, "rocktcdplane")
    require("procedure rocktcdplane(lane.i, rate.i, swing.i, emphasis.i)" in source,
            "tcphy_dp_cfg_lane must take the link rate")
    require("swing = 2 and emphasis = 0 and rate <> #tcphy_dp_rate_hbr2" in lane,
            "swing-2/pre-emphasis-0 drive override must exclude HBR2")
    require("(value & $8fff) | $5000" in lane and "(value & $8fff) | $6000" in lane,
            "XCVR_DIAG_PLLDRC_CTRL must select 5 at HBR2 and 6 below it")

    rate = procedure(source, "rocktcdpsetlinkrate")
    ordered(rate, (
        "rocktcpowerstate(#tcphy_dp_power_a3)",
        "~#tcphy_dp_pll_clock_enable",
        "rocktcdpclkwait(#tcphy_dp_pll_clock_ack,0",
        "~#tcphy_dp_pll_enable",
        "rocktcdpclkwait(#tcphy_dp_pll_ready,0",
        "rocktcwrite(#tcphy_hsclk_sel,hsclk)",
        "rocktcwrite(#tcphy_dp_clk_ctl,clkctl)",
        "rocktcdppllload(rate)",
        "| #tcphy_dp_pll_enable",
        "rocktcdpclkwait(#tcphy_dp_pll_ready,#tcphy_dp_pll_ready",
        "| #tcphy_dp_pll_clock_enable",
        "rocktcdpclkwait(#tcphy_dp_pll_clock_ack,#tcphy_dp_pll_clock_ack",
        "rocktcpowerstate(#tcphy_dp_power_a2)",
        "rocktcpowerstate(#tcphy_dp_power_a0)",
        "rock_tcphy_dp_rate=rate",
    ), "tcphy_dp_set_link_rate")
    require("hsclk = hsclk | $20" in rate and "clkctl = clkctl | $1200" in rate,
            "HBR2 must select PLL1 divide-by-1 and DP_PLL_DATA_RATE_HBR2")
    require("hsclk = hsclk | $30" in rate and "clkctl = clkctl | $2400" in rate,
            "RBR/HBR must select PLL1 divide-by-2 and DP_PLL_DATA_RATE_RBR/HBR")

    count = procedure(source, "rocktcdpsetlanecount")
    require("| $f000" in count and "case 2 : value = value & $ffffcfff" in count,
            "tcphy_dp_set_lane_count must disable every unused DP lane")

    config = procedure(source, "rocktcdpconfig")
    ordered(config, ("rocktcdpsetlanecount(lanes)", "rocktcdpsetlinkrate(rate)",
                     "rocktcdplane(2,rate", "rocktcdplane(3,rate"), "typec_dp_phy_config")

    up = procedure(source, "rocktcphyup")
    ordered(up, ("rocktcdprbrpll()", "rocktcdplane(2,#tcphy_dp_rate_rbr,0,0)",
                 "rocktcdplane(3,#tcphy_dp_rate_rbr,0,0)", "rock_tcphy_dp_lanes=0"),
            "cold PHY setup")


def check_cdn(source: str) -> None:
    for token in ("#cdn_source_hdtx_car = $0900", "#cdn_tx_phy_config = $2000",
                  "#cdn_framer_global_config = $2200", "#cdn_lane_en = $2300",
                  "#cdn_enhncd = $2304", "#cdn_write_dpcd = 4"):
        require(token in source, f"missing pinned constant {token}")

    pattern = procedure(source, "rockcdnsetpattern")
    for token in ("| $c8", "$d1000", "framer | $20", "phy | $21 | ((pattern & 3) << 1)",
                  "(1 << rock_cdn_link_lanes)-1", "> $10 and (rock_cdn_dpcd[2] & $80)"):
        require(token in pattern, f"cdn_dp_set_pattern value drifted: {token}")
    ordered(pattern, ("#cdn_framer_global_config", "#cdn_tx_phy_config", "#cdn_lane_en",
                      "#cdn_enhncd"), "cdn_dp_set_pattern write order")

    link = procedure(source, "rockcdnsetlinktrain")
    require("rockcdndpcdwritebytes($102,count" in link and "rock_cdn_link_lanes+1" in link,
            "cdn_dp_set_link_train must write TRAINING_PATTERN_SET plus lane sets")

    update = procedure(source, "rockcdnupdatelinktrain")
    ordered(update, ("rockcdnsetsignallevels()", "rockcdndpcdwritebytes($103"),
            "cdn_dp_update_link_train")

    levels = procedure(source, "rockcdnsetsignallevels")
    require("rocktcdpconfig(rockcdnratekhz(rock_cdn_link_rate),rock_cdn_link_lanes,set & 3,(set >> 3) & 3)"
            in levels, "signal levels must drive typec_dp_phy_config(rate, lanes, swing, pre-emphasis)")

    adjust = procedure(source, "rockcdngetadjusttrain")
    for token in ("if voltage >= 2 : voltage=6", "case 0 : limit=$18", "case 1 : limit=$10",
                  "case 2 : limit=$08", "emphasis=limit | $20"):
        require(token in adjust, f"cdn_dp_get_adjust_train drifted: {token}")

    per_rate = procedure(source, "rockcdnsoftwaretrainrate")
    ordered(per_rate, (
        "rockcdnsetsignallevels()", "rockcdnsetpattern($21)", "rockcdnsetlinktrain($21)",
        "rockcdntraindelay(0)", "rockcdnreadlivelinkstatus()", "rockcdnclockrecoveryok(",
        "if tries > 4", "if maxswing<>0", "rockcdngetadjusttrain()", "rockcdnupdatelinktrain()",
        "pattern=2", "> $11 and (rock_cdn_dpcd[2] & $40)", "rockcdnsetpattern(pattern | $20)",
        "rockcdnsetlinktrain(pattern | $20)", "for tries=5 to 1 step -1", "rockcdntraindelay(1)",
        "rockcdnchanneleqok(",
    ), "clock recovery then channel equalization")

    train = procedure(source, "rockcdnsoftwaretrain")
    ordered(train, (
        "rockcdndpcdreadbytes(0,15,@rock_cdn_dpcd[0])", "if sinklanes > 2 : sinklanes=2",
        "if sinkrate > 540000 : sinkrate=540000", "rockcdndpcdwritebytes($107,2",
        "rockcdndpcdwritebytes($100,2", "rockcdnsoftwaretrainrate()",
        "case #cdn_link_hbr2 : rock_cdn_link_rate=#cdn_link_hbr",
        "case #cdn_link_hbr : rock_cdn_link_rate=#cdn_link_rbr",
        "rockcdnsetpattern(0)", "rockcdnsetlinktrain(0)",
    ), "cdn_dp_software_train_link")

    top = procedure(source, "rockcdntrainlink")
    ordered(top, ("rock_cdn_use_fw_training=1", "rockcdnsoftwaretrain()",
                  "rockcdnregwrite(#cdn_source_hdtx_car,$f)", "rock_cdn_use_fw_training=0",
                  "rockcdntrain()"), "cdn_dp_train_link: software first, firmware fallback")

    delay = procedure(source, "rockcdntraindelay")
    require("rock_cdn_dpcd[14]" in delay and "interval*4000" in delay and
            "rocktimerwaitus(400)" in delay and "rocktimerwaitus(100)" in delay,
            "training delays must follow TRAINING_AUX_RD_INTERVAL like the 4.4 helpers")


def check_display(source: str) -> None:
    up = procedure(source, "rockdisplayupattempt")
    require("procedure.i rockdisplayupattempt(native.i)" in source,
            "the MiniDP lifecycle must be one attempt parameterised by native/fallback")
    ordered(up, ("rockvopselectminidp()", "rockcrudisplayprepare()",
                 "rocktcphyup()", "rockcdnhostcapabilities()", "rockcdnreadedid()",
                 "rock_display_link_reached=1", "rockcdntrainlink()", "rockcdnplanvideo()",
                 "rockcruvpllmode()", "rockvoppreparemode()", "rockcdnvideomode()",
                 "rockvopconfigureprimary()", "rockvopstartprimary()"), "MiniDP lifecycle")
    require(up.count("if rock_cdn_use_fw_training<>0") == 2,
            "SET_VIDEO idle and valid must be sent only for a firmware-trained link")
    # The native attempt trains on the host; the firmware alone trains only in
    # the fallback branch, on the cold RBR PHY, for the established 1024x768.
    for token in ("if native<>0", "trained=rockcdntrain()", "rock_display_link_reached=0"):
        require(token in up, f"MiniDP attempt is missing {token}")
    split = up.index("if native<>0")
    native_else = up.index("else", split)
    native_end = up.index("endif", up.index("trained=rockcdntrain()"))
    native_branch = up[split:native_else]
    fallback_branch = up[native_else:native_end]
    require("trained=rockcdntrainlink()" in native_branch and
            "rockcdntrain()" not in native_branch.replace("rockcdntrainlink()", ""),
            "the native attempt must train on the host first")
    ordered(fallback_branch, (
        "rockmodefallback(@rock_cdn_edid[0],#rock_mode_reason_link_rate)",
        "rockmodeselect(@rock_cdn_edid[0])", "rock_cdn_use_fw_training=1",
        "trained=rockcdntrain()"), "fallback: 1024x768 then firmware training")
    require("rockcdntrainlink()" not in fallback_branch and "rocktcdpconfig" not in fallback_branch,
            "the fallback must not re-enter host training or the per-rate PHY")
    require(up.index("rock_display_link_reached=0") < up.index("rockcrudisplayprepare()"),
            "each attempt must clear the link-reached marker before any hardware")

    wrapper = procedure(source, "rockdisplayup")
    ordered(wrapper, ("rockdisplayupattempt(1)<>0 : procedurereturn 1",
                      "if rock_display_link_reached=0 : procedurereturn 0",
                      "rock_display_native_error=rock_display_error",
                      "rock_display_fallback_used=1", "rockwatchdogpet()",
                      "rockdisplaystopscanout()", "procedurereturn rockdisplayupattempt(0)"),
            "RockDisplayUp: native first, one cold fallback after a link-stage failure")
    require(wrapper.count("rockdisplayupattempt(") == 2,
            "RockDisplayUp must make exactly one fallback attempt")
    stop = procedure(source, "rockdisplaystopscanout")
    ordered(stop, ("rockvopselectminidp()", "if rock_vop_configured<>0",
                   "rock_vop_win0_ctrl0_pending & ~#vop_win_enable", "rockvoplatchframe()",
                   "rock_vop_prepared=0", "rock_vop_configured=0"),
            "WIN0 must stop fetching before the cold retry resets VOPL")


def check_recovery(source: str) -> None:
    require("help hdmi minidp payload" in source, "recovery help omits minidp")
    minidp = procedure(source, "rockrecoveryminidp")
    ordered(minidp, ("rock_recovery_minidp_attempted<>0",
                     "rock_hdmi_attempted<>0 and rock_display_stage>=$d006",
                     "rockwatchdogarm()", "rock_recovery_minidp_attempted=1", "rockdisplayup()"),
            "minidp command: one attempt, never under a live HDMI VPLL, deadman first")
    hdmi = procedure(source, "rockrecoveryhdmi")
    require("rock_recovery_minidp_attempted<>0" in hdmi,
            "hdmi must refuse after MiniDP owns VPLL and the scanout")


def plan_video(pixel_khz: int, code: int, lanes: int) -> tuple[int, int, int] | None:
    """Exact mirror of RockCdnPlanVideo / cdn_dp_config_video integer maths."""
    link_mhz = {6: 162, 10: 270, 20: 540}[code]
    if (pixel_khz * 1000 * 24 + 999999) // 1000000 > link_mhz * lanes * 8:
        return None
    tu = 30
    while True:
        tu += 2
        scaled = (tu * pixel_khz * 24) // (lanes * link_mhz * 8)
        symbol, remainder = divmod(scaled, 1000)
        if tu > 64:
            return None
        if symbol > 1 and tu - symbol >= 4 and 100 <= remainder <= 850:
            break
    fifo = ((pixel_khz * (symbol + 1) // 1000) + link_mhz) // (lanes * link_mhz)
    fifo = 8 * (symbol + 1) // 24 - fifo + 2
    return tu, symbol, fifo


def check_arithmetic(cdn: str) -> None:
    plan = procedure(cdn, "rockcdnplanvideo")
    for token in ("tu = tu + 2", "(tu * pixelkhz * 24) / (rock_cdn_link_lanes * linkmhz * 8)",
                  "until symbol > 1 and tu-symbol >= 4 and remainder <= 850 and remainder >= 100"):
        require(token in plan, f"TU/VS search drifted: {token}")
    # 1920x1080@60, 148.5 MHz: RBR x2 cannot carry it; HBR x2 and HBR2 x2 can.
    require(plan_video(148500, 6, 2) is None, "1080p60 must not be admitted on RBR x2")
    require(plan_video(148500, 10, 2) == (32, 26, 4), f"HBR x2 plan {plan_video(148500, 10, 2)}")
    require(plan_video(148500, 20, 2) == (32, 13, 4), f"HBR2 x2 plan {plan_video(148500, 20, 2)}")
    # 1024x768@60, 65 MHz fits even RBR x2 - the only mode the old path reached.
    require(plan_video(65000, 6, 2) is not None, "1024x768@60 must fit RBR x2")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    lib = args.root / "RockPi4C" / "Lib"
    sources = {}
    for name in ("tcphy.pbi", "cdn_dp.pbi", "display.pbi", "recovery.pbi"):
        path = lib / name
        require(path.is_file(), f"missing source {path}")
        sources[name] = path.read_text(encoding="utf-8").lower()
    check_tcphy(sources["tcphy.pbi"])
    check_cdn(sources["cdn_dp.pbi"])
    check_arithmetic(sources["cdn_dp.pbi"])
    check_display(sources["display.pbi"])
    check_recovery(sources["recovery.pbi"])
    print("rockpi4c_dp_link_training_check: PASS")


if __name__ == "__main__":
    main()
