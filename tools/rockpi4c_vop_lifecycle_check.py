#!/usr/bin/env python3
"""Focused source/emitted gate for the RK3399 little-VOP lifecycle."""
from __future__ import annotations

import argparse
from pathlib import Path
import re


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"rockpi4c_vop_lifecycle_check: FAIL: {message}")


def procedure(source: str, name: str) -> str:
    match = re.search(
        rf"procedure(?:\.i)?\s+{re.escape(name)}\([^\n]*\)(.*?)endprocedure",
        source,
        re.DOTALL,
    )
    require(match is not None, f"missing {name} procedure")
    return match.group(1)


def ordered(body: str, tokens: tuple[str, ...], contract: str) -> None:
    positions = []
    for token in tokens:
        require(token in body, f"{contract}: missing {token}")
        positions.append(body.index(token))
    require(positions == sorted(positions), f"{contract}: order drifted")


def check_source(vop_path: Path) -> None:
    source = vop_path.read_text(encoding="utf-8").lower()

    for token in (
        "#rock_vop_max_width = 2560",
        "#rock_vop_max_height = 1600",
        "#rock_vop_timing_max = 8191",
        "#rock_vop_stride_word_max = 16383",
        "#vop_win0_ctrl0_rgb_base = $3a000000",
        "#vop_win0_ctrl1_rgb_unity = $00400000",
        "#vop_win0_src_alpha_opaque = $00ff0000",
        "#vop_scale_unity_xy = $10001000",
    ):
        require(token in source, f"missing pinned constant {token}")

    valid = procedure(source, "rockvopmodevalid")
    for token in (
        "rock_mode_valid=0",
        "#rock_vop_max_width",
        "#rock_vop_max_height",
        "#rock_vop_timing_max",
        "#rock_vop_stride_word_max",
        "rock_mode_pitch*rock_mode_height > #rock_fb_max_bytes",
    ):
        require(token in valid, f"mode admission omits {token}")

    line_buffer = procedure(source, "rockvoplinebuffermode")
    ordered(
        line_buffer,
        (
            "width < 1 or width > #rock_vop_max_width",
            "if width > 1920 : procedurereturn #vop_lb_rgb_2560x4",
            "procedurereturn #vop_lb_rgb_1920x5",
        ),
        "RGB line-buffer selection",
    )
    require("procedurereturn 5" not in line_buffer,
            "obsolete 1280-only line-buffer mode is selectable")

    latch = procedure(source, "rockvoplatchframe")
    ordered(
        latch,
        (
            "rockvopwrite(#vop_intr_clear0,$00010001)",
            "dsb sy",
            "rockvopwrite(#vop_cfg_done,1)",
            "timeoutticks=(rock_timer_frequency/1000000)*#vop_frame_wait_us",
            "rockvopread(#vop_intr_raw_status0) & #vop_intr_fs",
        ),
        "bounded CFG_DONE/frame-start latch",
    )
    require("for attempt=0 to 9999999" in latch and
            "now-start >= timeoutticks" in latch,
            "frame-start witness is not bounded by time and iteration")

    prepare = procedure(source, "rockvoppreparemode")
    ordered(
        prepare,
        (
            "rockvopmodevalid()",
            "rockcruvoprelease()",
            "rockvopfield(#vop_afbcd0_ctrl,$00000001,0)",
            "rockvopwrite(#vop_win0_ctrl0,#vop_win0_ctrl0_rgb_base)",
            "rockvopfield(#vop_win2_ctrl0,$00000011,0)",
            "rockvopfield(#vop_sys_ctrl,$0063f800,$00000800)",
            "rockvopfield(#vop_sys_ctrl1,$0003f000,$0003d000)",
            "rockvopwrite(#vop_dsp_ctrl0,0)",
            "rockvopwrite(#vop_htotal,hsynclength | (rock_mode_htotal << 16))",
            "rockvopwrite(#vop_post_scl_factor,#vop_scale_unity_xy)",
            "rockvopwrite(#vop_cabc_ctrl0,(pixeltotal << 4) | $00000008)",
            "rockvopfield(#vop_yuv2yuv_win,$00000007,0)",
            "rockvoplatchframe()",
            "rock_vop_prepared=1",
        ),
        "background CRTC prepare",
    )
    for timing in (
        "rockvopwrite(#vop_hact,hactiveend | (hactivestart << 16))",
        "rockvopwrite(#vop_vtotal,vsynclength | (rock_mode_vtotal << 16))",
        "rockvopwrite(#vop_vact,vactiveend | (vactivestart << 16))",
        "rockvopwrite(#vop_post_hact,hactiveend | (hactivestart << 16))",
        "rockvopwrite(#vop_post_vact,vactiveend | (vactivestart << 16))",
    ):
        require(timing in prepare, f"background CRTC omits {timing}")
    for bypass in (
        "rockvopwrite(#vop_dsp_bg,0)",
        "rockvopfield(#vop_post_scl_ctrl,$00000007,0)",
        "rockvopfield(#vop_bcsh_color_bar,$00000001,0)",
        "rockvopfield(#vop_bcsh_ctrl,$00000011,0)",
    ):
        require(bypass in prepare, f"clean RGB/post state omits {bypass}")
    require("rockcrureset(" not in prepare,
            "VOP prepare reintroduces a post-MMIO reset pulse")
    require("#rock_grf" not in prepare and "$6224" not in prepare,
            "VOP prepare usurps the facade-owned encoder route")

    # Independently exercise the exact CABC pixel-count expressions for both
    # the proven fallback and native preferred mode. Both fields are 23 bits.
    for width, height in ((1024, 768), (1920, 1080), (2560, 1600)):
        pixels = width * height
        require(pixels <= 0x7fffff,
                f"{width}x{height} exceeds the CABC pixel-count field")
        require(((pixels << 4) | 8) & 0xf == 8,
                f"{width}x{height} corrupts CABC disabled config mode")

    configure = procedure(source, "rockvopconfigureprimary")
    ordered(
        configure,
        (
            "rock_vop_configured=0",
            "rock_vop_prepared=0",
            "rockvopmodevalid()",
            "linebuffermode=rockvoplinebuffermode(rock_mode_width)",
            "rockvopfirstframe()",
            "rockvopwrite(#vop_win0_ctrl0,#vop_win0_ctrl0_rgb_base | (linebuffermode << #vop_win_lb_mode_shift))",
            "rockvopwrite(#vop_win0_vir,rock_mode_pitch >> 2)",
            "rockvopwrite(#vop_win0_yrgb_mst,rockvopframebuffer())",
            "rockvopwrite(#vop_win0_act_info,(rock_mode_width-1) | ((rock_mode_height-1) << 16))",
            "rockvopwrite(#vop_win0_scl_factor,#vop_scale_unity_xy)",
            "rockvopwrite(#vop_win0_src_alpha_ctrl,#vop_win0_src_alpha_opaque)",
            "rockvopfield(#vop_dsp_ctrl1,$0000ff00,#vop_dsp_layer_little)",
            "rock_vop_configured=1",
        ),
        "disabled primary-plane configure",
    )
    for token in (
        "rockvopwrite(#vop_win0_ctrl1,#vop_win0_ctrl1_rgb_unity)",
        "rockvopwrite(#vop_win0_dsp_info,(rock_mode_width-1) | ((rock_mode_height-1) << 16))",
        "rockvopwrite(#vop_win0_dsp_st,hactivestart | (vactivestart << 16))",
    ):
        require(token in configure, f"primary-plane state omits {token}")
    require("#vop_win_enable" not in configure and
            "#vop_cfg_done" not in configure and
            "rockvoplatchframe" not in configure,
            "configure phase enables or latches WIN0 before encoder enable")
    require("#vop_win0_gather" not in configure and
            "$00001303" not in configure,
            "configure phase reintroduces unsupported RGB gather programming")

    start = procedure(source, "rockvopstartprimary")
    ordered(
        start,
        (
            "rock_vop_ready=0",
            "rock_vop_prepared=0 or rock_vop_configured=0",
            "rockvopfield(#vop_win0_ctrl0,#vop_win_enable,#vop_win_enable)",
            "rockvoplatchframe()",
            "rock_vop_ready=1",
        ),
        "primary-plane start",
    )

    wrapper = procedure(source, "rockvopupmode")
    ordered(
        wrapper,
        (
            "rockvoppreparemode()",
            "rockvopconfigureprimary()",
            "rockvopstartprimary()",
        ),
        "compatibility lifecycle wrapper",
    )


def check_assembly(assembly_path: Path) -> None:
    assembly = assembly_path.read_text(encoding="utf-8", errors="replace").lower()

    def emitted(name: str) -> str:
        # PureMetal's listing emits public Procedure labels at column zero and
        # may place private __a64 labels inside them. Bound a procedure by the
        # next public Rock* symbol, not by a global search of the whole image.
        match = re.search(
            rf"(?m)^{re.escape(name)}:\s*$([\s\S]*?)(?=^rock[a-z0-9_]+:\s*$|\Z)",
            assembly,
        )
        require(match is not None, f"emitted assembly omits {name}:")
        return match.group(1)

    latch = emitted("rockvoplatchframe")
    prepare = emitted("rockvoppreparemode")
    configure = emitted("rockvopconfigureprimary")
    start = emitted("rockvopstartprimary")

    require(re.search(r"\bbl\s+rockvopwrite\b", latch) is not None and
            re.search(r"\bbl\s+rocktimerticks\b", latch) is not None,
            "emitted latch omits CFG_DONE/frame timeout owners")
    require(re.search(r"\bbl\s+rockcruvoprelease\b", prepare) is not None and
            re.search(r"\bbl\s+rockvoplatchframe\b", prepare) is not None,
            "emitted prepare omits reset release or background latch")
    require(re.search(r"\bbl\s+rockvopfirstframe\b", configure) is not None and
            re.search(r"\bbl\s+rockvoplatchframe\b", configure) is None,
            "emitted configure does not remain a disabled, unlatch plane phase")
    require(re.search(r"\bbl\s+rockvopfield\b", start) is not None and
            re.search(r"\bbl\s+rockvoplatchframe\b", start) is not None,
            "emitted start omits WIN0 enable or frame latch")
    for phase, body in (("prepare", prepare), ("configure", configure),
                        ("start", start)):
        require(re.search(r"\bbl\s+rockcrureset\b", body) is None,
                f"emitted VOP {phase} directly calls the reset primitive")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--assembly", type=Path)
    args = parser.parse_args()
    vop_path = args.root / "RockPi4C" / "Lib" / "vop.pbi"
    require(vop_path.is_file(), f"missing source {vop_path}")
    check_source(vop_path)
    if args.assembly is not None:
        require(args.assembly.is_file(), f"missing assembly {args.assembly}")
        check_assembly(args.assembly)
    print("rockpi4c_vop_lifecycle_check: PASS")


if __name__ == "__main__":
    main()
