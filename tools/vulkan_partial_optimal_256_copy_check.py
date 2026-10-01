from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path

SOURCE = Path("RaspberryPi4/Examples/Diagnostics/vulkanPartialOptimalCopy256Proof.pi4")
WORDS = 264
BYTES = WORDS * 4
MAGIC = 0x59524156
TAIL = 0x56415259
U32 = 0xFFFFFFFF
BUDGETS = (64, 128, 256)
WINDOW_BASE = 0x063E8000
WINDOW_BYTES = 4227072


def pattern(x: int, y: int, seed: int) -> int:
    return (0xFF000000
            | (((x * 17 + y * 3 + seed * 11) & 255) << 16)
            | (((x * 5 + y * 29 + seed * 7) & 255) << 8)
            | ((x * 37 + y * 11 + seed * 13) & 255))


def oracle_offset(x: int, y: int) -> int:
    group, rem = divmod(x, 32)
    return (group * 8192 + (y // 8) * 1024 + (rem // 8) * 256
            + (((y % 8) // 4) * 2 + ((rem % 8) // 4)) * 64
            + (y % 4) * 16 + (rem % 4) * 4)


ANCHORS = {(0, 0): 0, (4, 0): 64, (0, 4): 128, (8, 0): 256,
           (32, 0): 8192, (40, 0): 8448, (64, 0): 16384,
           (71, 63): 23804}


def source_errors(source: str) -> list[str]:
    groups = {
        "separate optimal images": ("vkCreateImage(dev, @ici, 0, @sourceImage)",
                                    "vkCreateImage(dev, @ici, 0, @destinationImage)",
                                    "vkBindImageMemory(dev, sourceImage, sourceMem, bindOffset)",
                                    "vkBindImageMemory(dev, destinationImage, destinationMem, bindOffset)"),
        "public partial image copy": ("vkCmdCopyImage(cmd, sourceImage, #VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, destinationImage, #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, @copy)",
                                      "copy\\dstOffset\\x = 8", "copy\\extent\\width = width",
                                      "Define status.i = #VVP_OK, rc.i, width.i = #COPY_TILES / 4"),
        "independent TFU baselines": ("vkCmdCopyBufferToImage(cmd, stage, image, #VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, @region)",
                                       "If V3dTfuJobs() <> initTfuBefore + 2",
                                       "If sourceBaseline <> #COPY_W * #COPY_H Or destinationBaseline <> #COPY_W * #COPY_H"),
        "independent UIF oracle": ("Procedure.i copyOracleOffset(x.i, y.i)",
                                   "group * 8192 + blockRow * 1024 + blockColumn * 256 + quadrant * 64 + inRow",
                                   "Procedure.i copyAnchors()"),
        "full source/destination oracle": ("For y = 0 To #COPY_H - 1", "For x = 0 To #COPY_W - 1",
                                           "copyPattern(x - 8, y, 29)", "copyPattern(x, y, 7)",
                                           "sourceUnchanged + 1", "changed + 1", "untouched + 1"),
        "guard cache maintenance": ("DmaCacheRange(mapped + bindOffset - 256, imageBytes + 512)",
                                    "DmaCacheRange(mapped, #COPY_STAGE_BYTES)"),
        "live distinct allocation ranges": ("vvpPut(#COPY_S_ALLOCATION, allocationBytes)",
                                            "vvpPut(#COPY_S_SOURCE_BASE, sourceBase)",
                                            "vvpPut(#COPY_S_DEST_BASE, destinationBase)",
                                            "If destinationBase - sourceBase < allocationBytes : status = 53",
                                            "If sourceBase - destinationBase < allocationBytes : status = 53",
                                            "If status = #VVP_OK : vvpPut(#COPY_S_DISJOINT, 1)",
                                            "If mapped + bindOffset <> base"),
        "both padded UIF regions": ("#COPY_S_PAD_BEFORE", "#COPY_S_PAD_AFTER",
                                    "#COPY_S_DEST_PAD_BEFORE", "#COPY_S_DEST_PAD_AFTER",
                                    "For x = #COPY_W To 95"),
        "fault refusal and timing": ("AnvilVkFaultCount() <> 0 Or AnvilVkFaultText() <> 0",
                                     "#COPY_S_TOTAL_US", "#COPY_S_UPLOAD_US"),
    }
    errors = [f"missing {name}" for name, tokens in groups.items()
              if any(token not in source for token in tokens)]
    if source.count("DmaCacheRange(mapped + bindOffset - 256, imageBytes + 512)") < 3:
        errors.append("image guards lack full pre/post cache maintenance")
    preflight = source.find("If status = #VVP_OK : vvpPut(#COPY_S_DISJOINT, 1)")
    guard_write = source.find("PokeL(mapped + bindOffset - 256 + k * 4, $A5A5A5A5)")
    if preflight < 0 or guard_write < 0 or guard_write <= preflight:
        errors.append("guard writes precede mapped-allocation preflight")
    if "AnvilVkV3dTextureUifOffset(" in source:
        errors.append("oracle calls production UIF offset helper")
    if "#COPY_W = 72" not in source or "#COPY_H = 64" not in source:
        errors.append("wrong image dimensions")
    match = re.search(r"(?m)^#COPY_TILES = (\d+)\s*$", source)
    if not match or int(match.group(1)) not in BUDGETS:
        errors.append("budget is not 64/128/256")
    return errors


def report_errors(data: bytes, budget: int) -> list[str]:
    if budget not in BUDGETS:
        return ["invalid budget"]
    if len(data) != BYTES:
        return [f"report length {len(data)} rather than {BYTES}"]
    s = struct.unpack("<264I", data)
    width = budget // 4
    last = pattern(63, 63, 29) if width == 64 else pattern(71, 63, 7)
    expected = {
        0: MAGIC, 1: 0, 2: 0, 3: 0, 82: 0, 85: 0, 95: 0, 96: 0, 97: 0,
        110: 1, 125: 4, 126: BYTES, 128: 0, 212: 1,
        219: 4608, 220: 4608, 221: width * 64, 222: (72 - width) * 64,
        223: 4608, 224: 9216, 225: 256, 226: U32, 232: 8,
        233: width, 234: budget, 237: 37056, 238: 48, 239: 0, 248: 0,
        259: pattern(0, 0, 7), 260: last, 262: 24576, 263: TAIL,
    }
    errors = [f"slot {i}=0x{s[i]:X}, expected 0x{value:X}"
              for i, value in expected.items() if s[i] != value]
    for a, b, delta, label in ((217, 218, 2, "TFU initialization"),
                               (249, 250, 0, "TFU copy"),
                               (251, 252, budget, "DMA copy"),
                               (253, 254, 1, "backend job")):
        if s[b] != s[a] + delta:
            errors.append(f"{label} delta {s[b] - s[a]} rather than {delta}")
    if s[249] != s[218]:
        errors.append("copy did not start after both TFU baselines")
    if s[213] != s[214] or s[215] != s[216]:
        errors.append("padded UIF storage changed")
    if s[235] == 0 or s[235] & (s[235] - 1) or s[236] < 256 or s[236] % s[235]:
        errors.append("image memory alignment/binding invalid")
    allocation = s[209]
    image_bytes = s[262]
    if allocation != s[236] + image_bytes + 256 or allocation > WINDOW_BYTES:
        errors.append("reported image allocation size invalid")
    for slot in (210, 211):
        base = s[slot]
        if (base == 0 or base > U32 - image_bytes
                or base < WINDOW_BASE + s[236]
                or allocation > WINDOW_BYTES
                or base - s[236] - WINDOW_BASE > WINDOW_BYTES - allocation):
            errors.append(f"mapped image base in slot {slot} outside declared GPU window")
    if (s[210] + image_bytes > s[211]
            and s[211] + image_bytes > s[210]):
        errors.append("mapped image byte ranges overlap")
    if abs(s[210] - s[211]) < allocation:
        errors.append("full image allocations overlap")
    if not (0 < s[227] < 15_000_000 and 0 < s[229] < 15_000_000
            and 0 < s[231] < 15_000_000):
        errors.append("missing or over-budget stage/full time")
    if s[231] < sum(s[i] for i in (227, 228, 229, 230)):
        errors.append("full time shorter than timed stages")
    allowed = (set(expected) | {209, 210, 211, 213, 214, 215, 216, 217, 218,
                                227, 228, 229, 230, 231, 235, 236,
                                249, 250, 251, 252, 253, 254})
    errors += [f"unexpected nonzero slot {i}" for i, value in enumerate(s)
               if i not in allowed and value]
    return errors


def synthetic_report(budget: int) -> bytes:
    width = budget // 4
    s = [0] * WORDS
    values = {0: MAGIC, 110: 1, 125: 4, 126: BYTES, 219: 4608, 220: 4608,
              221: width * 64, 222: (72 - width) * 64, 223: 4608, 224: 9216,
              225: 256, 226: U32, 227: 100, 228: 100, 229: 200, 230: 100,
              231: 600, 232: 8, 233: width, 234: budget, 235: 4096,
              236: 4096, 237: 37056, 238: 48,
              209: 4096 + 24576 + 256,
              210: WINDOW_BASE + 4096, 211: WINDOW_BASE + 4096 + 32768,
              212: 1,
              213: 12345, 214: 12345, 215: 45678, 216: 45678,
              217: 0, 218: 2, 249: 2, 250: 2,
              251: 0, 252: budget, 253: 2, 254: 3,
              259: pattern(0, 0, 7),
              260: pattern(63, 63, 29) if width == 64 else pattern(71, 63, 7),
              262: 24576, 263: TAIL}
    for slot, value in values.items():
        s[slot] = value
    return struct.pack("<264I", *s)


def self_test(source: str) -> int:
    if any(oracle_offset(*point) != value for point, value in ANCHORS.items()):
        raise AssertionError("UIF anchor mismatch")
    checks = len(ANCHORS)
    for budget in BUDGETS:
        good = synthetic_report(budget)
        if report_errors(good, budget):
            raise AssertionError(f"synthetic {budget} rejected")
        checks += 1
        base = list(struct.unpack("<264I", good))
        for slot in (0, 1, 82, 85, 95, 96, 97, 110, 125, 126,
                     209, 212, 213, 214, 215, 216, 218, 219, 220, 221, 222, 223,
                     224, 225, 226, 227, 229, 231, 232, 233, 234, 235,
                     236, 237, 238, 239, 248, 250, 252, 254, 259, 260,
                     262, 263):
            variant = base.copy()
            variant[slot] = 0 if slot in (227, 229, 231) else variant[slot] ^ 1
            if not report_errors(struct.pack("<264I", *variant), budget):
                raise AssertionError(f"slot {slot} mutation escaped")
            checks += 1
        for slot, value in ((210, 0), (211, 0),
                            (210, WINDOW_BASE - 4),
                            (211, WINDOW_BASE + WINDOW_BYTES),
                            (211, base[210] + 64),
                            (211, base[210] + 24576)):
            variant = base.copy()
            variant[slot] = value
            if not report_errors(struct.pack("<264I", *variant), budget):
                raise AssertionError(f"address mutation {slot}=0x{value:X} escaped")
            checks += 1
    for old, new in (("copy\\dstOffset\\x = 8", "copy\\dstOffset\\x = 4"),
                     ("copy\\extent\\width = width", "copy\\extent\\width = 72"),
                     ("group * 8192 + blockRow * 1024", "group * 4096 + blockRow * 1024"),
                     ("If sourceBaseline <> #COPY_W * #COPY_H Or destinationBaseline <> #COPY_W * #COPY_H",
                      "If sourceBaseline < 0"),
                     ("DmaCacheRange(mapped + bindOffset - 256, imageBytes + 512)",
                      "DmaCacheRange(mapped, 0)"),
                     ("If destinationBase - sourceBase < allocationBytes : status = 53",
                      "If destinationBase - sourceBase < 0 : status = 53"),
                     ("If mapped + bindOffset <> base", "If mapped + bindOffset < 0")):
        if old not in source or not source_errors(source.replace(old, new, 1)):
            raise AssertionError(f"source mutation escaped: {old}")
        checks += 1
    verdict = "If status = #VVP_OK : vvpPut(#COPY_S_DISJOINT, 1)"
    write = "PokeL(mapped + bindOffset - 256 + k * 4, $A5A5A5A5)"
    if verdict not in source or write not in source:
        raise AssertionError("range/guard ordering tokens missing")
    if not source_errors(source.replace(verdict, write + "\n" + verdict, 1)):
        raise AssertionError("early guard write escaped")
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
    match = re.search(r"(?m)^#COPY_TILES = (\d+)\s*$", source)
    budget = int(match.group(1)) if match else 0
    if args.report:
        failures += report_errors(args.report.read_bytes(), budget)
    if failures:
        print("partial optimal copy FAIL: " + "; ".join(failures))
        return 1
    checks = self_test(source) if args.self_test else 0
    print(f"partial optimal copy PASS: budget={budget}, hostile/anchor checks={checks}, "
          f"report={'PASS' if args.report else 'not supplied'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
