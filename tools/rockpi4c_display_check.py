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
        "rockcrurequirepll($60,384000000", "rockcrurequirepll($80,594000000",
        "$1fdf,$0340",
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
    order = [
        "rockcrudisplayprepare", "rockcrucadencerelease", "rockcdninternalclocks",
        "rockcdnfirmwareload", "rockcdnfirmwareactive", "rockcdnenableevents",
        "rocktcphyup", "$30003000", "rockcdnhotplug",
        "rockcdnhostcapabilities", "rockcdndpcd", "rockcdnreadedid",
        "rockvopup1024x768", "rockcdntrain", "rockcdnvideostatus(0)",
        "rockcdnvideo1024x768", "rockcdnvideostatus(1)",
    ]
    positions = [display.index(token) for token in order]
    require(positions == sorted(positions), "cold-to-visible stage order drifted")
    cru = libraries["cru.pbi"].lower()
    power_order = ["rockpmupoweron(14", "rockpmupoweron(24",
                   "rockpmupoweron(20", "rockpmuidlerelease(8",
                   "rockpmupoweron(8"]
    positions = [cru.index(token) for token in power_order]
    require(positions == sorted(positions), "RK3399 power hierarchy order drifted")
    require("gpio1_d0, not gpio1_c0" in cru, "exact MiniDP power pin correction missing")
    require("$00030000" in cru and "$00030001" in cru,
            "GPIO1_D0 input/pull-up pinctrl contract missing")
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
    require("rockdisplaydpcdtelemetry()" in display and
            'rockuarttext("dpe8 dpcd phase ")' in display and
            'rockuarttext(" aux ")' in display,
            "serial DPCD phase/AUX telemetry is missing")


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
        asm = Path(str(output) + ".asm").read_text(encoding="utf-8", errors="replace").lower()
        for token in ("str w", "ldr w", "rockdisplayup"):
            require(token in asm, f"emitted display image lacks {token}")
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
        counted = build_count.record_build(
            ROCK / "Board/board.rockpi4c", "rockpi4c", output,
            by="tools/rockpi4c_display_check.py", compiler=compiler,
        )
        print(f"  build count: {counted.message}")
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
