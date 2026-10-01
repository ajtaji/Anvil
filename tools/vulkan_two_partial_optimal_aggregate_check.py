from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path

SOURCE = Path("RaspberryPi4/Examples/Diagnostics/vulkanTwoPartialOptimalUploads256Proof.pi4")
REPORT_WORDS = 264
REPORT_BYTES = REPORT_WORDS * 4
MAGIC = 0x59524156
TAIL = 0x56415259
U32 = 0xFFFFFFFF
BUDGETS = (64, 128, 192, 256)


def pattern(x: int, y: int, seed: int) -> int:
    return (
        0xFF000000
        | (((x * 17 + y * 3 + seed * 11) & 255) << 16)
        | (((x * 5 + y * 29 + seed * 7) & 255) << 8)
        | ((x * 37 + y * 11 + seed * 13) & 255)
    )


def oracle_offset(x: int, y: int) -> int:
    column_group, in_group = divmod(x, 32)
    block_column = in_group // 8
    block_row = y // 8
    quadrant = 2 * ((y % 8) // 4) + ((x % 8) // 4)
    return 8192 * column_group + 1024 * block_row + 256 * block_column + 64 * quadrant + 16 * (y % 4) + 4 * (x % 4)


ANCHORS = {
    (0, 0): 0, (4, 0): 64, (0, 4): 128, (8, 0): 256,
    (32, 0): 8192, (40, 0): 8448, (64, 0): 16384, (71, 63): 23804,
}


def source_errors(source: str) -> list[str]:
    required = {
        "72x64 image": ("#AGG_W = 72", "#AGG_H = 64"),
        "two region calls": (
            "vkCmdCopyBufferToImage(cmd, stage, image, #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, @region)",
            "region\\imageOffset\\x = #AGG_W - width",
        ),
        "independent oracle": (
            "Procedure.i aggOracleOffset(x.i, y.i)",
            "group * 8192 + blockRow * 1024 + blockColumn * 256 + quadrant * 64 + inRow",
            "Procedure.i aggAnchors()",
        ),
        "TFU baseline before DMA": ("If baseline <> #AGG_W * #AGG_H : status = 48", "region\\bufferOffset = #AGG_LEFT"),
        "cache maintenance": ("DmaCacheRange(mapped + bindOffset - 256, imageBytes + 512)", "DmaCacheRange(mapped, #AGG_STAGE_BYTES)"),
        "full exact oracle": ("For y = 0 To #AGG_H - 1", "For x = 0 To #AGG_W - 1", "aggPattern(x - (#AGG_W - width), y, 53)"),
        "guards": ("bindOffset - 256", "bindOffset + imageBytes", "35008 + k * 4"),
        "padded UIF preservation": ("#AGG_S_PAD_BEFORE", "#AGG_S_PAD_AFTER", "For x = #AGG_W To 95"),
        "independent TFU baseline": ("initTfuBefore = V3dTfuJobs()", "If rc <> #VK_SUCCESS Or V3dTfuJobs() <> initTfuBefore + 1"),
        "native fault refusal": ("AnvilVkFaultCount() <> 0 Or AnvilVkFaultText() <> 0",),
        "timing": ("#AGG_S_INIT_US", "#AGG_S_BASE_US", "#AGG_S_UPLOAD_US", "#AGG_S_FINAL_US", "#AGG_S_TOTAL_US"),
    }
    errors = [
        f"missing {label}"
        for label, tokens in required.items()
        if any(source.count(token) < (2 if label == "two region calls" and token.startswith("vkCmd") else 3 if label == "cache maintenance" and token.startswith("DmaCacheRange(mapped + bindOffset") else 1) for token in tokens)
    ]
    if "AnvilVkV3dTextureUifOffset(" in source:
        errors.append("oracle calls the production UIF offset helper")
    match = re.search(r"(?m)^#AGG_TILES = (\d+)\s*$", source)
    if not match or int(match.group(1)) not in BUDGETS:
        errors.append("budget is not one of 64/128/192/256")
    return errors


def report_errors(data: bytes, budget: int) -> list[str]:
    if budget not in BUDGETS:
        return ["invalid requested budget"]
    if len(data) != REPORT_BYTES:
        return [f"report is {len(data)} bytes, expected {REPORT_BYTES}"]
    s = struct.unpack("<264I", data)
    w = budget // 8
    expected = {
        0: MAGIC, 1: 0, 2: 0, 3: 0, 82: 0, 85: 0, 95: 0, 96: 0, 97: 0,
        110: 1, 125: 4, 126: REPORT_BYTES, 128: 0, 220: 4608,
        221: 2 * w * 64, 222: (72 - 2 * w) * 64,
        223: (72 + 2 * w) * 64, 224: 2 * (32 - w) * 64,
        225: 128, 226: U32, 232: 8, 233: w, 234: budget,
        237: 35072, 238: 64, 239: 0, 248: 0,
        259: pattern(0, 0, 29), 260: pattern(w - 1, 63, 53),
        262: 24576, 263: TAIL,
    }
    errors = [f"slot {i} is 0x{s[i]:X}, expected 0x{value:X}" for i, value in expected.items() if s[i] != value]
    for before, after, delta, label in ((251, 252, budget, "DMA"), (253, 254, 2, "backend jobs"), (249, 250, 0, "TFU")):
        if s[after] != s[before] + delta:
            errors.append(f"{label} delta is {s[after] - s[before]}, expected {delta}")
    if s[218] != s[217] + 1 or s[249] != s[218]:
        errors.append("TFU baseline job did not advance exactly once before partial uploads")
    if s[215] != s[216]:
        errors.append("padded UIF storage changed")
    if s[235] == 0 or s[235] & (s[235] - 1) or s[236] < 256 or s[236] % s[235]:
        errors.append("image requirement alignment or binding offset invalid")
    if not (0 < s[227] < 15_000_000 and 0 < s[229] < 15_000_000 and 0 < s[231] < 15_000_000):
        errors.append("timing missing or outside 15-second diagnostic envelope")
    if s[231] < s[227] + s[228] + s[229] + s[230]:
        errors.append("total time shorter than timed stages")
    allowed = set(expected) | {215, 216, 217, 218, 227, 228, 229, 230, 231, 235, 236, 249, 250, 251, 252, 253, 254}
    errors += [f"unexpected nonzero slot {i}" for i, value in enumerate(s) if i not in allowed and value]
    return errors


def synthetic_report(budget: int) -> bytes:
    w = budget // 8
    s = [0] * REPORT_WORDS
    values = {
        0: MAGIC, 110: 1, 125: 4, 126: REPORT_BYTES, 220: 4608,
        221: 2 * w * 64, 222: (72 - 2 * w) * 64,
        223: (72 + 2 * w) * 64, 224: 2 * (32 - w) * 64,
        225: 128, 226: U32, 227: 100, 228: 100, 229: 200,
        230: 100, 231: 600, 232: 8, 233: w, 234: budget,
        235: 4096, 236: 4096, 237: 35072, 238: 64,
        215: 34567, 216: 34567, 217: 0, 218: 1,
        249: 1, 250: 1, 251: 5, 252: 5 + budget,
        253: 2, 254: 4, 259: pattern(0, 0, 29),
        260: pattern(w - 1, 63, 53), 262: 24576, 263: TAIL,
    }
    for slot, value in values.items():
        s[slot] = value
    return struct.pack("<264I", *s)


def self_test(source: str) -> int:
    if any(oracle_offset(*point) != expected for point, expected in ANCHORS.items()):
        raise AssertionError("independent anchor table failed")
    checks = len(ANCHORS)
    for budget in BUDGETS:
        data = synthetic_report(budget)
        if report_errors(data, budget):
            raise AssertionError(f"synthetic {budget} report rejected")
        checks += 1
        base = list(struct.unpack("<264I", data))
        for slot in (0, 1, 82, 85, 95, 96, 97, 110, 125, 126, 215, 216, 218, 220, 221, 222, 223, 224, 225, 226, 227, 229, 231, 232, 233, 234, 235, 236, 237, 238, 239, 248, 250, 252, 254, 259, 260, 262, 263):
            candidate = base.copy()
            candidate[slot] = 0 if slot in (227, 229, 231) else candidate[slot] ^ 1
            if not report_errors(struct.pack("<264I", *candidate), budget):
                raise AssertionError(f"slot {slot} mutation escaped")
            checks += 1
    for old, new in (
        ("#AGG_W = 72", "#AGG_W = 64"),
        ("#AGG_H = 64", "#AGG_H = 32"),
        ("region\\imageOffset\\x = #AGG_W - width", "region\\imageOffset\\x = width"),
        ("group * 8192 + blockRow * 1024", "group * 4096 + blockRow * 1024"),
        ("If baseline <> #AGG_W * #AGG_H : status = 48", "If baseline < 0 : status = 48"),
        ("DmaCacheRange(mapped + bindOffset - 256, imageBytes + 512)", "DmaCacheRange(imageBase, 0)"),
    ):
        if old not in source or not source_errors(source.replace(old, new, 1)):
            raise AssertionError(f"source mutation escaped: {old}")
        checks += 1
    return checks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    source = args.source.read_text(encoding="utf-8")
    failures = source_errors(source)
    match = re.search(r"(?m)^#AGG_TILES = (\d+)\s*$", source)
    budget = int(match.group(1)) if match else 0
    if args.report:
        failures += report_errors(args.report.read_bytes(), budget)
    if failures:
        print("aggregate upload FAIL: " + "; ".join(failures))
        return 1
    checks = self_test(source) if args.self_test else 0
    print(f"aggregate upload PASS: source budget={budget}; hostile/anchor checks={checks}; report={'PASS' if args.report else 'not supplied'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
