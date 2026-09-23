"""Read Build-specific Pi 3 console/framebuffer state over the existing UART protocol.

The symbol file is authoritative for every BSS address. This never writes board
memory or emits a reset/payload command; it only sends `version` and `md.l`.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import re
import sys
import time
from pathlib import Path


def read_symbols(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in path.read_text(encoding="ascii", errors="strict").splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        if value.isdecimal():
            result[name.lower()] = int(value)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", type=Path, required=True)
    ap.add_argument("--update-helper", type=Path, default=Path(__file__).with_name("pi3_serial_self_update.py"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--port", default="COM30")
    ap.add_argument("--expect-build", type=int, required=True)
    ap.add_argument("--execute", action="store_true", help="open the UART and run read-only queries")
    args = ap.parse_args()
    if not args.execute:
        ap.error("pass --execute to authorize the read-only UART query")
    symbols = read_symbols(args.symbols)
    helper_spec = importlib.util.spec_from_file_location("pi3_serial_self_update", args.update_helper)
    if helper_spec is None or helper_spec.loader is None:
        raise RuntimeError(f"cannot load serial helper: {args.update_helper}")
    helper = importlib.util.module_from_spec(helper_spec)
    sys.modules[helper_spec.name] = helper
    helper_spec.loader.exec_module(helper)

    # Keep the failure diagnosis first: a responsive console with a blank
    # panel should produce the decisive state before slower descriptive reads.
    fields = [
        ("screen_init_state", "global_pi3_screen_init_state", 4),
        ("screen_fault", "global_pi3_screen_fault", 4),
        ("screen_initialized", "global_pi3_screen_initialized", 4),
        ("screen_attached", "global_pi3_screen_attached", 4),
        ("banner_phase", "global_pi3_screen_banner_phase", 4),
        ("dma_state", "global_pi3_fb_dma_state", 4),
        ("dma_error", "global_pi3_fb_dma_error", 4),
        ("dma_active", "global_pi3_fb_dma_active", 4),
        ("fb_error", "global_pi3_fb_error", 4),
        ("clear_pending", "global_pi3_fb_clear_pending", 4),
        ("present_pending", "global_pi3_fb_present_pending", 4),
        ("dma_submissions", "global_pi3_fb_dma_submissions", 4),
        ("dma_completions", "global_pi3_fb_dma_completions", 4),
        ("dma_last_us", "global_pi3_fb_dma_last_us", 4),
        ("dma_fail_cs", "global_pi3_fb_dma_fail_cs", 4),
        ("dma_fail_conblk", "global_pi3_fb_dma_fail_conblk", 4),
        ("dma_fail_debug", "global_pi3_fb_dma_fail_debug", 4),
        ("dma_fail_elapsed_us", "global_pi3_fb_dma_fail_elapsed_us", 4),
        ("dma_fail_ti", "global_pi3_fb_dma_fail_ti", 4),
        ("dma_fail_src", "global_pi3_fb_dma_fail_src", 4),
        ("dma_fail_dst", "global_pi3_fb_dma_fail_dst", 4),
        ("dma_fail_length", "global_pi3_fb_dma_fail_length", 4),
        ("dma_fail_stride", "global_pi3_fb_dma_fail_stride", 4),
        ("dma_fail_current_ti", "global_pi3_fb_dma_fail_current_ti", 4),
        ("dma_fail_current_src", "global_pi3_fb_dma_fail_current_src", 4),
        ("dma_fail_current_dst", "global_pi3_fb_dma_fail_current_dst", 4),
        ("dma_fail_current_length", "global_pi3_fb_dma_fail_current_length", 4),
        ("dma_fail_current_stride", "global_pi3_fb_dma_fail_current_stride", 4),
        ("render_base", "global_pi3_fb", 8),
        ("scanout_base", "global_pi3_fb_scanout", 8),
        ("width", "global_pi3_fb_width", 4),
        ("height", "global_pi3_fb_height", 4),
        ("pitch", "global_pi3_fb_pitch", 4),
        ("render_bytes", "global_pi3_fb_render_bytes", 8),
        ("dma_cb", "global_pi3_fb_dma_cb", 8),
        ("dirty", "global_pi3_fb_dirty", 4),
        ("dirty_left", "global_pi3_fb_dirty_left", 4),
        ("dirty_top", "global_pi3_fb_dirty_top", 4),
        ("dirty_right", "global_pi3_fb_dirty_right", 4),
        ("dirty_bottom", "global_pi3_fb_dirty_bottom", 4),
        ("logo_row", "global_pi3_screen_logo_row", 4),
        ("cell_w", "global_pi3_screen_cell_w", 4),
        ("cell_h", "global_pi3_screen_cell_h", 4),
        ("origin_y", "global_pi3_screen_origin_y", 4),
        ("cols", "global_pi3_screen_cols", 4),
        ("rows", "global_pi3_screen_rows", 4),
        ("wfe_ready", "global_anvil_promptwfeready", 4),
        ("wfe_enabled", "global_anvil_promptwfeenabled", 4),
        ("cpu0_usage", "global_pi3_screen_usage", 4),
    ]
    missing = sorted({sym for _, sym, _ in fields if sym not in symbols})
    if missing:
        raise ValueError("symbols missing from selected image map: " + ", ".join(missing))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    def log(kind: str, data: bytes = b"", **extra: object) -> None:
        record = {"kind": kind, "time": time.time(), "hex": data.hex(),
                  "text": data.decode("ascii", "replace"), **extra}
        with args.out.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()

    import serial
    port = serial.Serial(args.port, 115200, timeout=.05, write_timeout=5,
                         dsrdtr=False, rtscts=False)
    port.dtr = False
    port.rts = False
    read_prompt = helper.make_prompt_reader(port, log)
    try:
        log("open", port=args.port, baud=115200, dtr=False, rts=False,
            symbols=str(args.symbols), expected_build=args.expect_build)
        port.write(b"\r")
        port.flush()
        initial = read_prompt(60)
        if not helper.PROMPT.search(initial):
            raise helper.UpdateError("fresh prompt missing")
        version = helper.command(port, read_prompt, log, "version", timeout=30)
        if f"build {args.expect_build}".encode() not in version.lower():
            raise helper.UpdateError("running build does not match selected symbol file")
        for label, symbol, width_bytes in fields:
            addr = symbols[symbol]
            response = helper.command(port, read_prompt, log,
                                      f"md.l {addr:X} {width_bytes:X}", timeout=20)
            match = re.search(rb"(?m)^\s*[0-9A-F]{8,16}:\s+([0-9A-F]{8})", response)
            if not match:
                raise helper.UpdateError(f"no 32-bit value parsed for {label} at 0x{addr:X}")
            value = int(match.group(1), 16)
            log("state", label=label, symbol=symbol, address=f"0x{addr:08X}",
                value=f"0x{value:08X}", access_bytes=width_bytes)
        # Safe, read-only BCM2837 DMA channel-5 status registers. `md.l` is
        # deliberately 32-bit; never use byte reads for device registers.
        for label, addr in (("dma5_cs", 0x3F007500),
                            ("dma5_conblk", 0x3F007504),
                            ("dma5_debug", 0x3F007520)):
            response = helper.command(port, read_prompt, log, f"md.l {addr:X} 4", timeout=20)
            match = re.search(rb"(?m)^\s*[0-9A-F]{8,16}:\s+([0-9A-F]{8})", response)
            if not match:
                raise helper.UpdateError(f"no 32-bit value parsed for {label}")
            log("register", label=label, address=f"0x{addr:08X}",
                value=f"0x{int(match.group(1),16):08X}", access_bytes=4)
        log("PASS", expected_build=args.expect_build)
    except Exception as exc:
        log("ERROR", error=str(exc))
        raise
    finally:
        port.close()
    print(f"Read-only state captured: {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
