#!/usr/bin/env python3
"""Composition contract for Rock Pi HDMI, PL330 and the Anvil screen."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "RockPi4C/Board/board.rockpi4c"
PLATFORM = ROOT / "RockPi4C/Board/platform.pbi"
HDMI = ROOT / "RockPi4C/Lib/hdmi_display.pbi"
UART = ROOT / "RockPi4C/Lib/uart2.pbi"
STORAGE = ROOT / "RockPi4C/Lib/storage_proof.pbi"
RECOVERY = ROOT / "RockPi4C/Lib/recovery.pbi"


def body(text: str, name: str) -> str:
    found = re.search(
        rf"(?ms)^Procedure(?:\.i)?\s+{re.escape(name)}\b.*?^EndProcedure\s*$",
        text,
    )
    if not found:
        raise AssertionError(f"missing {name}")
    return found.group(0)


def ordered(text: str, tokens: tuple[str, ...], reason: str) -> None:
    positions = [text.find(token) for token in tokens]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError(f"{reason}: {tokens}")


def main() -> int:
    board = BOARD.read_text(encoding="utf-8")
    platform = PLATFORM.read_text(encoding="utf-8")
    hdmi = HDMI.read_text(encoding="utf-8")
    uart = UART.read_text(encoding="utf-8")
    storage = STORAGE.read_text(encoding="utf-8")
    recovery_source = RECOVERY.read_text(encoding="utf-8")

    # Board composition supplies every dependency once, in dependency order.
    ordered(
        board,
        (
            'XIncludeFile "RockPi4C/Lib/uart2.pbi"',
            'XIncludeFile "Anvil/Core/build_identity.pbi"',
            'XIncludeFile "Anvil/Graphics/text_glyph.pbi"',
            'XIncludeFile "Anvil/Graphics/anvil_logo.pbi"',
            'XIncludeFile "RockPi4C/Lib/watchdog.pbi"',
            'XIncludeFile "RockPi4C/Lib/dma_pl330.pbi"',
            'XIncludeFile "RockPi4C/Lib/display.pbi"',
            'XIncludeFile "RockPi4C/Lib/hdmi.pbi"',
            'XIncludeFile "RockPi4C/Lib/screen_console.pbi"',
            'XIncludeFile "RockPi4C/Lib/hdmi_display.pbi"',
            'XIncludeFile "RockPi4C/Lib/recovery.pbi"',
        ),
        "board include order no longer satisfies screen dependencies",
    )
    for include in (
        "Anvil/Core/build_identity.pbi",
        "Anvil/Graphics/text_glyph.pbi",
        "Anvil/Graphics/anvil_logo.pbi",
        "RockPi4C/Lib/dma_pl330.pbi",
        "RockPi4C/Lib/screen_console.pbi",
    ):
        if board.count(include) != 1:
            raise AssertionError(f"board does not include {include} exactly once")

    recovery = body(board, "RockRecoveryLoop")
    ordered(
        recovery,
        ("RockRecoveryPoll()", "RockScreenService()", "RockTimerWaitUs(1000)"),
        "recovery loop lost bounded cooperative screen service",
    )

    # A completed command has exactly one facade invocation and one success
    # print. The emitted recovery gate separately executes this chain and
    # proves that an idle poll cannot replay it.
    recovery_hdmi = body(recovery_source, "RockRecoveryHdmi")
    if recovery_hdmi.count("ready=RockHdmiDisplayUp()") != 1:
        raise AssertionError("recovery HDMI command no longer invokes the facade exactly once")
    if recovery_hdmi.count('RockUartLine("HDMI INIT READY")') != 1:
        raise AssertionError("recovery HDMI command no longer has one success print")
    ordered(
        recovery_hdmi,
        (
            "rock_recovery_hdmi_attempted=1",
            "ready=RockHdmiDisplayUp()",
            'RockUartLine("HDMI INIT READY")',
        ),
        "one-shot HDMI latch/call/success order changed",
    )

    # ConfigurePrimary deliberately leaves WIN0 disabled. The complete banner
    # is therefore composed into its exact published surface before scanout.
    up = body(hdmi, "RockHdmiDisplayUp")
    ordered(
        up,
        (
            "RockVopConfigurePrimary()",
            "rock_display_width=rock_mode_width",
            "rock_display_buffer=RockVopFramebuffer()",
            "rock_display_ready=1",
            "dmaReady=RockDmaPl330Init()",
            'RockUartText("HDMI DMA UNAVAILABLE DMA_ERR=")',
            "RockScreenComposeStandardFrame()",
            "RockUartSetMirrorHook(@RockScreenMirrorByte)",
            "RockVopStartPrimary()",
            "RockDisplayFrameTelemetry()",
        ),
        "HDMI publication/banner/start order changed",
    )
    if up.count("rock_display_buffer=RockVopFramebuffer()") != 1:
        raise AssertionError("HDMI publishes more than one framebuffer seam")
    if up.count("dmaReady=RockDmaPl330Init()") != 1 or "If dmaReady=0" not in up:
        raise AssertionError("HDMI no longer records PL330 admission before selecting its fallback")
    for token in (
        'RockUartText("HDMI DMA UNAVAILABLE DMA_ERR=")',
        "RockDisplayHexByte(rock_dma_pl330_error)",
        'RockUartLine("; CPU FRAME FALLBACK")',
        'RockHdmiDisplayFail(35,"HDE9B STANDARD ANVIL FRAME COMPOSITION FAILED.")',
    ):
        if token not in up:
            raise AssertionError(f"missing degraded-DMA integration result: {token}")
    if 'RockHdmiDisplayFail(34,"HDE9A RK3399 PL330 DMA INITIALIZATION FAILED.")' in up:
        raise AssertionError("failed DMA admission still prevents CPU-composed scanout")

    failed = body(hdmi, "RockHdmiDisplayFail")
    for token in (
        "RockUartSetMirrorHook(0)",
        "rock_display_ready=0",
        'RockUartText(" DMA_ERR=")',
        'RockUartText(" SCREEN_ERR=")',
    ):
        if token not in failed:
            raise AssertionError(f"HDMI failure lost screen/DMA refusal state: {token}")

    # The UART remains independently linkable. Its optional hook runs only
    # after a byte has been accepted by THR and performs no rendering itself.
    tx = body(uart, "RockUartByte")
    ordered(
        tx,
        ("PokeL(#ROCK_UART2 + #ROCK_UART_THR, value)", "rock_uart_mirror_hook(value)"),
        "UART mirror runs before successful transmission",
    )
    if "*rock_uart_mirror_hook(value)" in tx:
        raise AssertionError("UART mirror call dereferences its void return value")
    for forbidden in ("RockScreen", "RockDma", "RockVop"):
        if forbidden in tx:
            raise AssertionError(f"UART producer directly entered display work: {forbidden}")

    # A get command emits opaque bytes through RockUartByte. It must detach
    # the text hook around that exact loop and restore it before all messages.
    get_file = body(storage, "RockStorageGetFile")
    ordered(
        get_file,
        (
            "*mirror = RockUartSetMirrorHook(0)",
            "For index = 0 To length - 1",
            "RockUartByte(PeekA(@rock_storage_stage[0] + index) & 255)",
            "RockUartSetMirrorHook(*mirror)",
            'RockUartLine("DATA DONE")',
        ),
        "binary transfer is no longer isolated from the screen text ring",
    )
    if get_file.count("RockUartSetMirrorHook(*mirror)") != 3:
        raise AssertionError("binary transfer does not restore the mirror on success and both failures")

    # Desk composition must not promote unverified hardware capability or
    # turn the one-shot diagnostic into automatic boot display.
    for token in ("#CAP_DISPLAY = 0", "#ROCK_DIRECTSD_HDMI_AUTO = 0"):
        if token not in platform:
            raise AssertionError(f"unproven display policy changed: {token}")

    print("rockpi4c screen integration: PASS")
    print("  VOPB configure -> preferred PL330 / bounded CPU fallback -> complete frame -> WIN0 start")
    print("  recovery service and UART text mirror are bounded; binary get is isolated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
