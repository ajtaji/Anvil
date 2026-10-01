from __future__ import annotations

import argparse
import struct
import re
from pathlib import Path

SOURCE = Path("RaspberryPi4/Examples/Diagnostics/vulkanClearExtent1024Proof.pi4")
COMMAND = Path("Anvil/Graphics/Vulkan/vk_command.pbi")
BACKEND = Path("Anvil/Graphics/Vulkan/vk_v3d_backend.pi4")
NEON = Path("RaspberryPi4/Lib/neon.pi4")
REPORT_BYTES = 64 * 8
U64 = (1 << 64) - 1
SURFACE = 0x06000000
GUARD_BYTES = 4_096_000
WIN_BASE = SURFACE + GUARD_BYTES
WIN_BYTES = 3_145_728
EXPECTED_PIXEL = 0xFF3380B2
GUARD_WORD = 0x5A3C0FF0
ERRSTAT_VCDI_IDLE = 1 << 12
SLOT_NAMES = (
    "magic", "status", "detail", "detail2", "surface", "pitch", "width", "height",
    "window_base", "window_bytes", "image_address", "expected_pixel", "first_pixel",
    "last_pixel", "mismatch_count", "first_bad_offset", "image_size", "image_row_pitch",
    "image_alignment", "memory_type_count", "heap_bytes", "bin_before", "bin_after",
    "render_before", "render_after", "bin_oom", "bin_errstat", "render_errstat",
    "mmu_faults", "mmu_vio_address", "mmu_vio_id", "guard_before", "guard_after",
    "layout_before", "layout_after", "fence_before", "fence_after", "submit_rc",
    "wait_rc", "native_error", "submit_us", "readback_us", "backend_gpu",
    "backend_name", "fault_text", "display_error", "arena_need", "present_verdict",
    "shutdown", "fault_count",
) + tuple(f"reserved_{i}" for i in range(50, 64))


def guard_checksum() -> int:
    count = GUARD_BYTES // 4
    return (GUARD_WORD * count + 4 * count * (count - 1) // 2) & 0xFFFFFFFFFFFF


def validate_report(data: bytes) -> list[str]:
    errors: list[str] = []
    if len(data) != REPORT_BYTES:
        return [f"report is {len(data)} bytes; expected exactly {REPORT_BYTES}"]
    slots = struct.unpack("<64Q", data)

    exact = {
        0: 0x564B4350, 1: 0, 2: 0, 3: 0,
        4: SURFACE, 5: 4096, 6: 1024, 7: 768,
        8: WIN_BASE, 9: WIN_BYTES, 11: EXPECTED_PIXEL,
        12: EXPECTED_PIXEL, 13: EXPECTED_PIXEL, 14: 0,
        15: U64, 16: WIN_BYTES, 17: 4096,
        25: 0, 28: 0, 29: 0, 30: 0,
        33: 0, 34: 7, 35: 1, 36: 0,
        37: 0, 38: 0, 39: 0, 42: 1,
        44: 0, 45: 0, 47: 0, 48: 1, 49: 0,
    }
    for index, expected in exact.items():
        if slots[index] != expected:
            errors.append(f"slot {index} ({SLOT_NAMES[index]}) is 0x{slots[index]:X}; expected 0x{expected:X}")
    for index in (26, 27):
        if slots[index] & ~ERRSTAT_VCDI_IDLE:
            errors.append(f"slot {index} ({SLOT_NAMES[index]}) has error bits 0x{slots[index] & ~ERRSTAT_VCDI_IDLE:X}")

    if not (WIN_BASE <= slots[10] < WIN_BASE + WIN_BYTES) or slots[10] & 3:
        errors.append(f"slot 10 ({SLOT_NAMES[10]}) is outside the target window or not word aligned")
    if slots[18] == 0 or slots[18] & (slots[18] - 1):
        errors.append(f"slot 18 ({SLOT_NAMES[18]}) is not a nonzero power-of-two alignment")
    if slots[19] == 0 or slots[20] == 0 or slots[46] == 0:
        errors.append("slot 19/20/46 memory properties or required arena size are absent")
    if slots[22] <= slots[21] or slots[24] <= slots[23]:
        errors.append("slot 21..24 V3D bin/render job counters did not both increase")
    checksum = guard_checksum()
    if slots[31] != checksum or slots[32] != checksum:
        errors.append("slot 31/32 native guard checksum differs before/after or from the expected pattern")
    if slots[43] == 0:
        errors.append("slot 43 backend name is absent")
    if any(slots[i] != 0 for i in range(50, 64)):
        errors.append("reserved report slots 50..63 are nonzero")
    return errors


def describe_report(data: bytes) -> list[str]:
    if len(data) != REPORT_BYTES:
        return [f"report_bytes={len(data)} expected={REPORT_BYTES}"]
    slots = struct.unpack("<64Q", data)
    return [f"slot {i:02d} {SLOT_NAMES[i]}=0x{value:016X}" for i, value in enumerate(slots)]


def synthetic_report() -> bytes:
    values = [0] * 64
    values[0:4] = [0x564B4350, 0, 0, 0]
    values[4:10] = [SURFACE, 4096, 1024, 768, WIN_BASE, WIN_BYTES]
    values[10] = WIN_BASE
    values[11:16] = [EXPECTED_PIXEL, EXPECTED_PIXEL, EXPECTED_PIXEL, 0, U64]
    values[16:21] = [WIN_BYTES, 4096, 4096, 3, 64 * 1024 * 1024]
    values[21:25] = [10, 11, 20, 21]
    values[26] = ERRSTAT_VCDI_IDLE
    values[27] = ERRSTAT_VCDI_IDLE
    values[31] = guard_checksum()
    values[32] = guard_checksum()
    values[33:40] = [0, 7, 1, 0, 0, 0, 0]
    values[42:50] = [1, 1, 0, 0, 0, 0, 1, 0]
    values[46] = 4096
    values[48] = 1
    values[49] = 0
    return struct.pack("<64Q", *values)


def procedure(text: str, name: str) -> str:
    match = re.search(rf"(?mi)^\s*Procedure(?:\.i)?\s+{re.escape(name)}\s*\([^\n]*\).*?$", text)
    if not match:
        return ""
    end = re.search(r"(?mi)^\s*EndProcedure\s*$", text[match.end():])
    return text[match.start():match.end() + end.end()] if end else ""


def validate(candidate: str, command: str, backend: str, neon: str) -> list[str]:
    errors: list[str] = []
    required = {
        "target width": "#VCP_TARGET_W = 1024",
        "target height": "#VCP_TARGET_H = 768",
        "target pitch": "#VCP_TARGET_PITCH = 4096",
        "target byte size": "#VCP_TARGET_BYTES = 3145728",
        "native guard size": "#VCP_SCREEN_BYTES = 4096000",
        "target geometry selection": "  w = #VCP_TARGET_W\n  h = #VCP_TARGET_H\n  pitch = #VCP_TARGET_PITCH",
        "offscreen window selection": "  winBase = #VCP_SURFACE + #VCP_SCREEN_BYTES\n  winBytes = #VCP_TARGET_BYTES",
        "native engine surface retained": "NeonSurface(#VCP_SURFACE, #VCP_PANEL_W, #VCP_PANEL_H, #VCP_PANEL_PITCH)",
        "both target and guard mapped": "NeonSurfaceMapSpan(#VCP_SCREEN_BYTES * 2)",
        "target requirement checked": "AnvilVkImageRowPitch(img) <> pitch Or req\\size <> #VCP_TARGET_BYTES",
        "public clear submitted": "vkCmdClearColorImage(cmd, img, #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL",
        "guard checked around submit": "vcpSum(#VCP_SURFACE, #VCP_SCREEN_BYTES)",
    }
    for label, token in required.items():
        if token not in candidate:
            errors.append(f"missing {label}")
    if re.search(r"(?m)^\s*(?!;)(?:DisplayAdopt|DisplayBlit|DisplayFlush)\s*\(", candidate):
        errors.append("presentation call is present")
    poison = candidate.find("vcpFill(imgBase")
    submit = candidate.find("vkQueueSubmit(")
    if poison < 0 or submit < 0 or poison > submit:
        errors.append("target poison is not before submit")

    clear = procedure(backend, "avkBackendClearSupported")
    backend_checks = (
        "Neon_Ready() = 0", "w < 8 Or h < 8",
        "w > Neon_CapacityPhysicalW() Or h > Neon_CapacityPhysicalH()",
        "pitch <> (w * 4)", "bytes < (pitch * h)",
        "base = Neon_SurfaceBase()",
    )
    if not clear or any(token not in clear for token in backend_checks):
        errors.append("current backend clear acceptance predicates changed")

    command_body = procedure(command, "AnvilVkCmdClearColorImage")
    if not command_body or "avkBackendClearSupported(AnvilVkImageAddress(image)" not in command_body:
        errors.append("recording does not use the current backend clear gate")

    rebind = procedure(neon, "NeonRebindSurface")
    rebind_checks = (
        "pw > neon_capPhysW Or ph > neon_capPhysH",
        "V3dRenderPlanBuild(pw, ph, outFmt, 1, 0, 0, @plan)",
    )
    if not rebind or any(token not in rebind for token in rebind_checks):
        errors.append("current transactional surface rebind rejects or fails to plan the bounded target")

    image_plan = procedure(backend, "avkBackendImagePlan")
    if not image_plan or "*plan\\rowPitch = avkBackendRowPitchFor(width)" not in image_plan or "*plan\\bytes = *plan\\rowPitch * height" not in image_plan:
        errors.append("current linear image planner does not use the stated tight row geometry")

    surface = procedure(neon, "NeonSurfaceOriented")
    surface_checks = (
        "maxDim = pw", "If ph > maxDim : maxDim = ph : EndIf",
        "If neon_capPhysW < maxDim : neon_capPhysW = maxDim : EndIf",
        "If neon_capPhysH < maxDim : neon_capPhysH = maxDim : EndIf",
    )
    if not surface or any(token not in surface for token in surface_checks):
        errors.append("startup surface no longer establishes the documented square capacity")

    try:
        width = int(re.search(r"#VCP_TARGET_W\s*=\s*(\d+)", candidate).group(1))
        height = int(re.search(r"#VCP_TARGET_H\s*=\s*(\d+)", candidate).group(1))
        pitch = int(re.search(r"#VCP_TARGET_PITCH\s*=\s*(\d+)", candidate).group(1))
        size = int(re.search(r"#VCP_TARGET_BYTES\s*=\s*(\d+)", candidate).group(1))
        guard_bytes = int(re.search(r"#VCP_SCREEN_BYTES\s*=\s*(\d+)", candidate).group(1))
    except (AttributeError, ValueError):
        errors.append("target geometry constants are not literal integers")
    else:
        capacity = max(800, 1280)
        if (width, height, pitch, size) != (1024, 768, 4096, 3_145_728):
            errors.append("target does not match the requested geometry")
        if width > capacity or height > capacity or pitch != width * 4 or size != pitch * height:
            errors.append("target fails the current backend capacity/pitch/size predicates")
        if size > guard_bytes or guard_bytes + size > 2 * guard_bytes:
            errors.append("target does not fit the declared mapped Vulkan window")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path, help="exact 512-byte runtime report returned in x0")
    args = parser.parse_args()
    candidate = SOURCE.read_text(encoding="utf-8")
    command = COMMAND.read_text(encoding="utf-8")
    backend = BACKEND.read_text(encoding="utf-8")
    neon = NEON.read_text(encoding="utf-8")
    errors = validate(candidate, command, backend, neon)
    if errors:
        print("clear-extent-1024 FAIL: " + "; ".join(errors))
        return 1
    if args.report is not None:
        report_errors = validate_report(args.report.read_bytes())
        for line in describe_report(args.report.read_bytes()):
            print(line)
        if report_errors:
            print("clear-extent-1024 REPORT FAIL: " + "; ".join(report_errors))
            return 1
        print("clear-extent-1024 REPORT PASS; all 64 slots decoded")
    elif not args.self_test:
        print("clear-extent-1024 FAIL: supply --report with the exact 512-byte runtime report")
        return 2
    if args.self_test:
        mutations = [
            (candidate, "#VCP_TARGET_W = 1024", "#VCP_TARGET_W = 800"),
            (candidate, "#VCP_TARGET_H = 768", "#VCP_TARGET_H = 480"),
            (candidate, "#VCP_TARGET_PITCH = 4096", "#VCP_TARGET_PITCH = 3200"),
            (candidate, "#VCP_TARGET_BYTES = 3145728", "#VCP_TARGET_BYTES = 4096000"),
            (candidate, "winBytes = #VCP_TARGET_BYTES", "winBytes = #VCP_SCREEN_BYTES"),
            (candidate, "NeonSurfaceMapSpan(#VCP_SCREEN_BYTES * 2)", "NeonSurfaceMapSpan(#VCP_SCREEN_BYTES)"),
            (candidate, "vkCmdClearColorImage(cmd, img, #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL", "vkCmdFillBuffer(cmd, 0, 0, 4, 0"),
            (candidate, "  vcpPut(#VCP_S_PRESENT, #VCP_P_NOT_TRIED)", "  DisplayBlit(imgBase, pitch, 0, 0, w, h)"),
            (backend, "If w > Neon_CapacityPhysicalW() Or h > Neon_CapacityPhysicalH()", "If w <> Neon_SurfaceW() Or h <> Neon_SurfaceH()"),
            (neon, "If neon_capPhysW < maxDim : neon_capPhysW = maxDim : EndIf", "If neon_capPhysW < maxDim : neon_capPhysW = 0 : EndIf"),
        ]
        caught = 0
        for target, old, new in mutations:
            mutated = target.replace(old, new, 1)
            values = [candidate, command, backend, neon]
            if target == candidate:
                values[0] = mutated
            elif target == backend:
                values[2] = mutated
            else:
                values[3] = mutated
            if old not in target or not validate(*values):
                print(f"self-test mutation escaped: {old}")
                return 1
            caught += 1
        report = synthetic_report()
        if validate_report(report):
            print("self-test synthetic report rejected")
            return 1
        report_mutations = [
            (1, 1), (5, 3200), (6, 800), (7, 1280), (8, WIN_BASE + 4),
            (9, 4_096_000), (11, 0), (12, 0), (13, 0), (14, 1),
            (15, 0), (22, 10), (24, 20), (25, 1), (26, 1), (27, 1),
            (28, 1), (31, 0), (32, 0), (33, 1), (34, 0), (35, 0),
            (36, 1), (37, 1), (38, 1), (39, 1), (42, 0), (44, 1),
            (45, 1), (47, 1), (48, 0), (49, 1), (50, 1),
        ]
        base = list(struct.unpack("<64Q", report))
        for index, value in report_mutations:
            changed = base.copy()
            changed[index] = value
            if not validate_report(struct.pack("<64Q", *changed)):
                print(f"self-test report mutation escaped: slot {index}")
                return 1
            caught += 1
        for bad_length in (REPORT_BYTES - 8, REPORT_BYTES + 8):
            malformed = report[:bad_length] if bad_length < REPORT_BYTES else report + bytes(bad_length - REPORT_BYTES)
            if not validate_report(malformed):
                print(f"self-test report length mutation escaped: {bad_length}")
                return 1
            caught += 1
        print(f"clear-extent-1024 PASS; desk gates; {caught} hostile mutations caught")
    else:
        print("clear-extent-1024 PASS; exact runtime report validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
