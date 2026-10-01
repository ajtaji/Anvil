"""Strict host oracle for the full 15-scene Pi 4 RAM capture."""
from pathlib import Path
import argparse
import hashlib
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs/evidence/neon-texttex-20260926/native-pixels.bgra"
HISTORICAL = ROOT / "docs/evidence/vulkan-paired-all15-20260926/vulkan-pixels.bgra"
HISTORICAL_REPORT = ROOT / "docs/evidence/vulkan-paired-all15-20260926/report.bin"
EXPECTED_SHA = "34f541a88313f370f5cbaf62639241562cc8d909094143504962e0f8925e8727"
SCENE_BYTES = 16384
SCENES = 15
SLAB_BYTES = 0x40000
# RAM slot for each scene in canonical native-golden order. The full payload
# captures boxes first at slot 0; its scene-0 clear is captured at slot 12.
SLOT_OFFSETS = (
    0x34000, 0x00000, 0x08000, 0x0C000, 0x14000,
    0x18000, 0x1C000, 0x10000, 0x20000, 0x24000,
    0x28000, 0x2C000, 0x30000, 0x38000, 0x3C000,
)
# Separate source-call capture order and live-established native scene pairing.
# Keep this independent of SLOT_OFFSETS so the historical self-test catches a
# mistaken canonical order rather than round-tripping that same mistake.
SOURCE_CAPTURE_ORDER = (
    0x00000, 0x08000, 0x0C000, 0x10000, 0x14000,
    0x18000, 0x1C000, 0x20000, 0x24000, 0x28000,
    0x2C000, 0x30000, 0x34000, 0x38000, 0x3C000,
)
GOLDEN_TO_SOURCE = (12, 0, 1, 2, 4, 5, 6, 3, 7, 8, 9, 10, 11, 13, 14)

def corpus_from_slab(slab: bytes) -> bytes:
    assert len(slab) == SLAB_BYTES, "capture slab length"
    return b"".join(slab[start:start + SCENE_BYTES] for start in SLOT_OFFSETS)

def slab_from_corpus(corpus: bytes) -> bytes:
    assert len(corpus) == SCENES * SCENE_BYTES
    slab = bytearray([0xA5] * SLAB_BYTES)
    for scene, source_index in enumerate(GOLDEN_TO_SOURCE):
        start = SOURCE_CAPTURE_ORDER[source_index]
        slab[start:start + SCENE_BYTES] = corpus[scene * SCENE_BYTES:(scene + 1) * SCENE_BYTES]
    return bytes(slab)

def check(candidate: bytes) -> int:
    golden = GOLDEN.read_bytes()
    assert len(golden) == SCENES * SCENE_BYTES and hashlib.sha256(golden).hexdigest() == EXPECTED_SHA, "golden integrity"
    assert len(candidate) == len(golden), "capture length"
    for index, (got, want) in enumerate(zip(candidate, golden)):
        if got != want:
            scene, offset = divmod(index, SCENE_BYTES)
            raise AssertionError(f"scene {scene} byte {offset} differs: {got:02x} != {want:02x}")
    return len(candidate)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slab", type=Path, help="262144-byte RAM capture from 0x07000000; reorder its 15 occupied 16-KiB slots")
    parser.add_argument("--corpus", type=Path, help="already ordered 245760-byte corpus")
    parser.add_argument("--report", type=Path, help="256-byte x0 report from the full-mode run")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        checks = 0
        if args.self_test:
            old = HISTORICAL.read_bytes()
            checks += check(old)
            assert SLOT_OFFSETS == tuple(SOURCE_CAPTURE_ORDER[index] for index in GOLDEN_TO_SOURCE), "source-to-golden pairing"
            assert SLOT_OFFSETS[0] == 0x34000 and SLOT_OFFSETS[1] == 0x00000 and SLOT_OFFSETS[7] == 0x10000, "clear/boxes/alpha anchors"
            slab = slab_from_corpus(old)
            checks += check(corpus_from_slab(slab))
            assert hashlib.sha256(corpus_from_slab(slab)[4 * SCENE_BYTES:5 * SCENE_BYTES]).hexdigest() == "0670700ea847876846f0785f8b55a66b1c8d951ecaf52842ce7a6e827f2be3c7", "fan index"
            assert hashlib.sha256(corpus_from_slab(slab)[5 * SCENE_BYTES:6 * SCENE_BYTES]).hexdigest() == "8499dae5dd040c3dc7ededc827a7825d3fc12def66e0719b1e595a41cb6604f6", "line index"
            for scene, start in enumerate(SLOT_OFFSETS):
                bad_slab = bytearray(slab)
                bad_slab[start + 99] ^= 1
                try:
                    check(corpus_from_slab(bad_slab))
                except AssertionError as error:
                    assert f"scene {scene} byte 99" in str(error), "wrong scene mutation attribution"
                else:
                    raise AssertionError(f"scene {scene} mutation passed")
            wrong_order = bytearray(slab)
            a, b = SLOT_OFFSETS[0], SLOT_OFFSETS[12]
            wrong_order[a:a + SCENE_BYTES], wrong_order[b:b + SCENE_BYTES] = slab[b:b + SCENE_BYTES], slab[a:a + SCENE_BYTES]
            try:
                check(corpus_from_slab(wrong_order))
            except AssertionError as error:
                assert "scene 0" in str(error), "wrong-order attribution"
            else:
                raise AssertionError("wrong-order slab passed")
            try:
                corpus_from_slab(slab[:-1])
            except AssertionError as error:
                assert "slab length" in str(error)
            else:
                raise AssertionError("short slab passed")
            broken = bytearray(old)
            broken[4 * SCENE_BYTES + 99] ^= 1
            try:
                check(broken)
            except AssertionError as error:
                assert "scene 4 byte 99" in str(error)
            else:
                raise AssertionError("hostile mutation passed")
            try:
                check(old[:-1])
            except AssertionError as error:
                assert "length" in str(error)
            else:
                raise AssertionError("short corpus passed")
            old_report = HISTORICAL_REPORT.read_bytes()
            assert len(old_report) == 256 and struct.unpack_from("<I", old_report, 62 * 4)[0] == 3505, "historical full-mode marker"
            broken_report = bytearray(old_report)
            struct.pack_into("<I", broken_report, 62 * 4, 0)
            assert struct.unpack_from("<I", broken_report, 62 * 4)[0] != 3505, "capacity marker mutation passed"
        if args.corpus:
            checks += check(args.corpus.read_bytes())
        if args.slab:
            checks += check(corpus_from_slab(args.slab.read_bytes()))
        if args.report:
            report = args.report.read_bytes()
            assert len(report) == 256, "report length"
            assert struct.unpack_from("<I", report, 62 * 4)[0] == 3505, "full-mode capacity marker"
            checks += 2
        assert args.self_test or args.slab or args.corpus or args.report, "choose a check"
    except (AssertionError, OSError) as error:
        print(f"all15 corpus FAIL: {error}", file=sys.stderr)
        return 1
    print(f"all15 corpus PASS: {checks} exact bytes plus hostile mutation checks")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
