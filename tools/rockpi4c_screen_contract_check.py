#!/usr/bin/env python3
"""Structural contract for the Rock Pi 4C standard Anvil screen adapter."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / "RockPi4C/Lib/screen_console.pbi"


def body(text: str, name: str) -> str:
    found = re.search(
        rf"(?ms)^Procedure(?:\.i)? {re.escape(name)}\(.*?\)\n(.*?)^EndProcedure",
        text,
    )
    if not found:
        raise AssertionError(f"{name} not found")
    return found.group(1)


def require(text: str, token: str, reason: str) -> None:
    if token not in text:
        raise AssertionError(reason)


def validate(text: str) -> None:
    # The visual identity is the existing Anvil contract, not an RK variant.
    for token in (
        "#ROCK_SCREEN_RING_BYTES = 8192",
        "#ROCK_SCREEN_SERVICE_BYTES = 32",
        "#ROCK_SCREEN_SERVICE_US = 1500",
        "#ROCK_SCREEN_CPU_WATCHDOG_BYTES = 262144",
        "#ROCK_SCREEN_BANNER_H = 120",
        "#ROCK_SCREEN_BG = $FF000028",
        "#ROCK_SCREEN_STEEL = $FFE2E8F0",
        "#ROCK_SCREEN_ORANGE = $FFFF9430",
        "#ROCK_SCREEN_FAINT = $FF788496",
        'text = "PureMetal Forge"',
        'RockScreenText("A N V I L"',
        'RockScreenText("CPU0 --.--%"',
        "AnvilBuildLabel(#ANVIL_BUILD, #ANVIL_BUILD_DATE, #ANVIL_BUILD_TIME)",
        "?anvilPix",
        "#ANVIL_PIC_W",
        "#ANVIL_PIC_H",
    ):
        require(text, token, f"standard Anvil screen token missing: {token}")

    # UART producer work is a ring append and metadata only. It may neither
    # draw nor call DMA, VOP, watchdog, or the service consumer.
    producer = body(text, "RockScreenMirrorByteStyle") + body(
        text, "RockScreenMirrorByte"
    )
    for forbidden in (
        "PokeL(",
        "RockDma",
        "RockVop",
        "RockScreenService(",
        "RockScreenPaintByte(",
        "RockWatchdogPet(",
    ):
        if forbidden in producer:
            raise AssertionError(f"UART producer entered rendering path: {forbidden}")
    require(producer, "rock_screen_ring[rock_screen_head]", "producer no longer enqueues")
    require(
        producer,
        "rock_screen_ring_style[rock_screen_head]",
        "producer no longer preserves screen style",
    )

    service = body(text, "RockScreenService")
    require(
        service,
        "count < #ROCK_SCREEN_SERVICE_BYTES",
        "screen drain lost its 32-byte bound",
    )
    require(
        service,
        "RockScreenTimeExpired(start)",
        "screen drain lost its 1500-us deadline",
    )
    require(
        service,
        "RockScreenBannerService(start)",
        "banner is no longer service-driven",
    )

    banner = body(text, "RockScreenBannerService")
    require(banner, "rock_dma_pl330_ready <> 0", "initial clear no longer gates DMA on admission")
    require(
        banner,
        "RockDmaFill32(rock_display_buffer, #ROCK_SCREEN_BG, total)",
        "initial framebuffer clear no longer prefers one full DMA request",
    )
    require(
        banner,
        "RockScreenCpuFill32(rock_display_buffer, #ROCK_SCREEN_BG, total)",
        "initial framebuffer clear lost its CPU fallback",
    )
    if "rock_screen_banner_row < rock_display_height" in banner:
        raise AssertionError("initial framebuffer clear is visible scanline by scanline")
    compose = body(text, "RockScreenComposeStandardFrame")
    require(
        compose,
        "For pass = 0 To 255",
        "pre-scanout banner composition lost its instruction ceiling",
    )
    require(
        compose,
        "RockScreenBannerService(RockTimerTicks())",
        "pre-scanout entry no longer composes the standard banner",
    )

    fill = body(text, "RockScreenFillRect")
    require(fill, "#ROCK_SCREEN_DMA_MIN_BYTES", "fill lost its DMA threshold")
    require(fill, "RockDmaFill32(", "large fill no longer attempts DMA")
    require(fill, "RockScreenCpuFill32(", "fill no longer has CPU fallback")
    require(fill, "rock_dma_pl330_ready <> 0", "fill can call an unadmitted DMA controller")
    scroll = body(text, "RockScreenScroll")
    require(scroll, "rock_screen_scroll_active = 1", "scroll is no longer deferred")
    scroll_service = body(text, "RockScreenScrollService")
    require(scroll_service, "RockDmaCopy(", "large scroll no longer attempts DMA")
    require(scroll_service, "RockScreenCpuCopyUp(", "scroll no longer has CPU fallback")
    require(scroll_service, "rock_dma_pl330_ready <> 0", "scroll can call an unadmitted DMA controller")
    require(scroll_service, "chunk > rock_screen_scroll_gap", "DMA scroll chunk can overlap its source")
    require(scroll_service, "#ROCK_SCREEN_SCROLL_CHUNK_BYTES", "DMA scroll work is no longer bounded")

    for cpu_name in ("RockScreenCpuFill32", "RockScreenCpuCopyUp"):
        cpu = body(text, cpu_name)
        require(cpu, "#ROCK_SCREEN_CPU_WATCHDOG_BYTES", f"{cpu_name} lost its fixed watchdog cadence")
        require(cpu, "RockWatchdogPet()", f"{cpu_name} can starve the deadman")

    # This adapter consumes a published surface. Display mode ownership stays
    # in the existing VOP/HDMI files.
    for forbidden in (
        "RockVopPrepareMode(",
        "RockVopConfigurePrimary(",
        "RockVopStartPrimary(",
        "#VOP_",
        "#ROCK_VOP",
    ):
        if forbidden in text:
            raise AssertionError(f"screen adapter re-entered display setup: {forbidden}")

    for name in (
        "HwConWidth",
        "HwConHeight",
        "HwConTier",
        "HwConTextHeight",
        "HwConFrameBegin",
        "HwConFrameEnd",
        "HwConRect",
        "HwConText",
        "HwConTextWidth",
        "HwConCapture",
        "HwConBacklight",
    ):
        body(text, name)

    frame_end = body(text, "HwConFrameEnd")
    require(frame_end, "dsb sy", "frame end no longer publishes framebuffer writes")
    tier = body(text, "HwConTier")
    require(tier, "rock_dma_pl330_ready <> 0", "HwCon tier no longer follows DMA admission")
    require(tier, "ProcedureReturn #HW_TIER_CPU", "HwCon claims DMA after failed admission")
    if "XIncludeFile" in text:
        raise AssertionError("screen adapter violates board-owned include order")


def main() -> int:
    validate(SCREEN.read_text(encoding="utf-8"))
    print("PASS: RK3399 standard banner, admitted DMA/CPU fallback, bounded UART service and HwCon seam")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
