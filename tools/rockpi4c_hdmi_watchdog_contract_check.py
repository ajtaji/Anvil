#!/usr/bin/env python3
"""Check that Rock Pi 4C HDMI watchdog feeds prove forward progress."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
HDMI = ROOT / "RockPi4C/Lib/hdmi_display.pbi"
HDMI_CORE = ROOT / "RockPi4C/Lib/hdmi.pbi"
VOP = ROOT / "RockPi4C/Lib/vop.pbi"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def procedure(source: str, name: str) -> str:
    match = re.search(
        rf"(?ims)^Procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)\s*$"
        rf"(.*?)^EndProcedure\s*$",
        source,
    )
    require(match is not None, f"missing {name}")
    return match.group(1)


def main() -> int:
    hdmi = HDMI.read_text(encoding="utf-8")
    hdmi_core = HDMI_CORE.read_text(encoding="utf-8")
    vop = VOP.read_text(encoding="utf-8")
    display_up = procedure(hdmi, "RockHdmiDisplayUp")
    ddc = procedure(hdmi_core, "RockHdmiReadEdidBlock")
    ddc_wait = procedure(hdmi_core, "RockHdmiWaitDdcDone")
    phy_write = procedure(hdmi_core, "RockHdmiPhyI2cWrite")
    phy_wait = procedure(hdmi_core, "RockHdmiWaitPhyI2c")
    phy_powerdown = procedure(hdmi_core, "RockHdmiPhyWaitPowerDown")
    phy_configure = procedure(hdmi_core, "RockHdmiPhyConfigure")
    enable = procedure(hdmi_core, "RockHdmiEnableSelected")
    telemetry = procedure(hdmi_core, "RockHdmiStateTelemetry")
    vop_telemetry = procedure(hdmi, "RockHdmiVopTelemetry")
    first_frame = procedure(vop, "RockVopFirstFrame")
    latch = procedure(vop, "RockVopLatchFrame")

    # Each facade feed follows a successful return or an explicit MMIO
    # readback. Keep polling loops feed-free so the hardware deadman can fire.
    hpd_loop = re.search(r"(?is)For hpdAttempt=0 To 2999(.*?)Next", display_up)
    require(hpd_loop is not None, "HDMI HPD loop changed shape")
    require("RockWatchdogPet" not in hpd_loop.group(1),
            "HPD polling can hide a wedged transmitter from the watchdog")
    require("RockWatchdogPet" not in ddc_wait,
            "DDC status polling can conceal a wedged transaction")
    require("RockWatchdogPet" not in phy_wait,
            "PHY-I2C status polling can conceal a wedged transaction")
    require("RockWatchdogPet" not in phy_powerdown,
            "PHY power-down polling can conceal a wedged PLL")
    tx_off = phy_configure.index(
        "RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$08,$00)")
    lock_low = phy_configure.index("RockHdmiPhyWaitPowerDown()")
    pddq = phy_configure.index(
        "RockHdmiUpdate8(#ROCK_HDMI_PHY_CONF0,$10,$10)")
    require(tx_off < lock_low < pddq,
            "Gen2 PHY no longer proves lock low between TX power-off and PDDQ")

    ordered = (
        "If RockCruHdmiPrepare()=0",
        "If RockPmicHdmiRailsEnsure()=0",
        "If hpd=0",
        "If RockHdmiReadEdid(@rock_hdmi_edid[0])=0",
        "If RockModeSelect(@rock_hdmi_edid[0])=0",
        "If RockVopModeValid()=0",
        "If RockCruVpllModeForVop(0)=0",
        "If RockVopPrepareMode()=0",
        "If route<>0",
        "If RockHdmiEnableSelected()=0",
        "If RockVopConfigurePrimary()=0",
        "If RockVopStartPrimary()=0",
    )
    positions = [display_up.index(marker) for marker in ordered]
    require(positions == sorted(positions), "HDMI lifecycle order drifted")
    for index, start in enumerate(positions):
        end = positions[index + 1] if index + 1 < len(positions) else len(display_up)
        require("RockWatchdogPet()" in display_up[start:end],
                f"successful HDMI milestone lacks watchdog feed: {ordered[index]}")

    require("If (y & 31)=31 Or y=rock_mode_height-1 : RockWatchdogPet() : EndIf"
            in first_frame,
            "large framebuffer fill lacks coarse completed-scanline feeds")
    require("rock_hdmi_edid_staging[index]=RockHdmiRead8" in ddc and
            "If (index & 15)=15 : RockWatchdogPet() : EndIf" in ddc,
            "successful DDC byte batches do not feed the watchdog")
    require("completed=RockHdmiWaitPhyI2c()" in phy_write and
            "If completed<>0 : RockWatchdogPet() : EndIf" in phy_write,
            "successful PHY-I2C transactions do not feed the watchdog")
    for field in ("PHY_STAT", "PHY_CONF", "PWRDN", "CLKDIS", "SWRSTZ",
                  "FC_INVID", "TX_INVID", "VP_CONF", "HDCP0", "IH_PHY",
                  "IH_FC2", "IH_PHYI2C", "FC_STAT2"):
        require(field in telemetry, f"final HDMI telemetry omits {field}")
    require("RockHdmiStateTelemetry()" in display_up,
            "successful HDMI bring-up omits final raw-state telemetry")
    setup_order = (
        "RockHdmiComposeTiming()",
        "RockHdmiPhyConfigure(rock_mode_pixel_hz)",
        "RockHdmiWrite8(#ROCK_HDMI_FC_CTRLDUR,12)",
        "RockHdmiConfigureAvi()",
        "RockHdmiVideoPacketize()",
        "RockHdmiVideoCsc()",
        "RockHdmiVideoSample()",
        "RockHdmiVideoHdcp()",
        "RockHdmiWrite8(#ROCK_HDMI_MC_SWRSTZ,$FD)",
    )
    require([enable.index(marker) for marker in setup_order] == sorted(
        enable.index(marker) for marker in setup_order),
        "HDMI setup no longer follows the released driver block order")
    for field in ("raw_version", "raw_sys_ctrl", "raw_sys_ctrl1",
                  "raw_dsp_ctrl0", "raw_dsp_ctrl1", "raw_win0_ctrl0",
                  "raw_win0_vir", "raw_win0_mst", "raw_htotal",
                  "raw_hact", "raw_vtotal", "raw_vact", "raw_status",
                  "raw_intr", "route_before", "route_after"):
        require(field in vop_telemetry,
                f"final VOP/route telemetry omits {field}")
    require("RockHdmiVopTelemetry()" in display_up,
            "successful HDMI bring-up omits final VOP/route telemetry")
    require("RockWatchdogPet" not in latch,
            "VOP frame-start polling can conceal a wedged CRTC")
    require(first_frame.count("RockWatchdogPet()") == 1,
            "framebuffer renderer gained an unreviewed watchdog feed")

    print("Rock Pi 4C HDMI watchdog progress contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
