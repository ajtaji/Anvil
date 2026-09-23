#!/usr/bin/env python3
"""Parse the fixed report emitted by the Vulkan paired-oracle payload.

The report is intentionally separate from the native Neon report.  Its header
proves that the producer was the Vulkan V3D path; each record binds one golden
scene token, operation digest, geometry and measured counters to one disjoint
pixel slot.  This parser never copies a native report or supplies defaults.
"""
from __future__ import annotations

import argparse, hashlib, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "RaspberryPi4/Tests/neon_compatibility_golden.json"
MAGIC, VERSION, SCENES = 0x564F5231, 1, 15
HEADER_WORDS, RECORD_WORDS, SLOT_BYTES = 20, 32, 16384
CAPTURE_BASE, CAPTURE_BYTES = 0x07000000, SCENES * SLOT_BYTES
REPORT_BYTES = (HEADER_WORDS + SCENES * RECORD_WORDS) * 4
FIELDS = ("status", "logical_w", "logical_h", "physical_w", "physical_h", "pitch",
          "slot_offset", "slot_bytes", "pixel_bytes", "draws", "boxes", "glyphs",
          "runs", "verts", "tex_draws", "tex_glyphs", "tex_verts", "clipped",
          "guard_bad", "first_error")


class GateError(Exception):
    pass


def fail(message):
    raise GateError(message)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).digest()


def op_digest(ops):
    return struct.unpack("<I", hashlib.sha256(json.dumps(ops, sort_keys=True, separators=(",", ":")).encode()).digest()[:4])[0]


def parse(report: bytes, pixels: bytes, manifest: dict) -> dict:
    if len(report) != REPORT_BYTES: fail(f"report length {len(report)} != {REPORT_BYTES}")
    if len(pixels) != CAPTURE_BYTES: fail(f"pixel length {len(pixels)} != {CAPTURE_BYTES}")
    words = struct.unpack("<%dI" % (REPORT_BYTES // 4), report)
    if words[:4] != (MAGIC, VERSION, SCENES, HEADER_WORDS): fail("Vulkan report header mismatch")
    if bytes(struct.pack("<8I", *words[4:12])) != digest(manifest): fail("manifest digest mismatch")
    if words[12:16] != (CAPTURE_BASE, CAPTURE_BYTES, REPORT_BYTES, SLOT_BYTES): fail("capture layout mismatch")
    if words[16] != 1 or words[17] != 0 or words[18] != 0 or words[19] != 0x47505557:
        fail("report does not prove GPU Vulkan submit/wait execution")
    scenes = []
    for index, expected in enumerate(manifest["scenes"]):
        rec = words[HEADER_WORDS + index * RECORD_WORDS:HEADER_WORDS + (index + 1) * RECORD_WORDS]
        if rec[0] != int(expected["token"], 16): fail("scene token mismatch: " + expected["id"])
        if rec[21] != op_digest(expected["ops"]): fail("operation digest mismatch: " + expected["id"])
        counters = dict(zip(FIELDS, rec[1:21]))
        for field, value in expected["expected"].items():
            if value is not None and counters.get(field) != value: fail(f"{expected['id']} {field} mismatch")
        start = counters["slot_offset"]; span = counters["pixel_bytes"]
        if counters["slot_bytes"] != SLOT_BYTES or span <= 0 or span > SLOT_BYTES or start + span > CAPTURE_BYTES:
            fail("scene pixel span mismatch: " + expected["id"])
        scenes.append({"id": expected["id"], "token": expected["token"], "events": expected["ops"],
                       "counters": counters, "pixel_offset": start, "pixel_bytes": span,
                       "pixel_sha256": hashlib.sha256(pixels[start:start + span]).hexdigest()})
    return {"schema": "neon-vulkan-execution/v1", "manifest_digest": digest(manifest).hex(),
            "backend": {"name": "anvil-vulkan-v3d", "gpu": 1, "native_error": 0,
                        "fallback": False, "api": ["AnvilVkV3dWindow", "avkBackendPrepare", "avkBackendSubmitDraw", "avkBackendDraws"],
                        "execution": "gpu_submit_wait"}, "scenes": scenes}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--pixels", required=True, type=Path); ap.add_argument("--output", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        result = parse(a.report.read_bytes(), a.pixels.read_bytes(), manifest)
        a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("VULKAN_EXECUTION: PASS")
        return 0
    except (GateError, OSError, ValueError, KeyError, json.JSONDecodeError, struct.error) as exc:
        print("FAIL: " + str(exc), file=sys.stderr); return 1


if __name__ == "__main__": raise SystemExit(main())
