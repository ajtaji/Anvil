#!/usr/bin/env python3
"""Bind a real Anvil V3D execution capture to the 15-scene paired-oracle schema.

This is deliberately a converter, not a renderer.  The execution JSON is
written by a Vulkan diagnostic after it has submitted the scene through
Anvil's V3D backend, and the pixel file is the backend's mapped image span.
No native report is accepted as input and no pixels or counters are invented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "RaspberryPi4/Tests/neon_compatibility_golden.json"
CAPTURE_BYTES = 15 * 16384


class GateError(Exception):
    pass


def fail(message: str) -> None:
    raise GateError(message)


def manifest_digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_manifest() -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema") != "neon-compatibility-golden/v2" or len(data.get("scenes", [])) != 15:
        fail("manifest schema/scene count mismatch")
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execution", required=True, type=Path,
                    help="JSON emitted by the Vulkan diagnostic")
    ap.add_argument("--pixels", required=True, type=Path,
                    help="raw packed BGRA8 bytes from the Vulkan image span")
    ap.add_argument("--trace-out", required=True, type=Path)
    ap.add_argument("--pixels-out", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        manifest = load_manifest()
        execution = json.loads(args.execution.read_text(encoding="utf-8"))
        if execution.get("schema") != "neon-vulkan-execution/v1":
            fail("execution schema is not neon-vulkan-execution/v1")
        if execution.get("schema") == "neon-native-artifact/v1" or execution.get("native_fallback"):
            fail("native artifact/fallback is not a Vulkan execution")
        if execution.get("manifest_digest") != manifest_digest(manifest):
            fail("execution manifest digest mismatch")
        backend = execution.get("backend")
        if not isinstance(backend, dict) or backend.get("name") != "anvil-vulkan-v3d":
            fail("execution does not identify the Anvil Vulkan V3D backend")
        if backend.get("gpu") != 1 or backend.get("native_error") != 0:
            fail("execution does not prove successful GPU backend ownership")
        if backend.get("fallback") is not False:
            fail("execution fallback marker is not false")
        required_api = ["AnvilVkV3dWindow", "avkBackendPrepare", "avkBackendSubmitDraw", "avkBackendDraws"]
        if backend.get("api") != required_api:
            fail("execution backend API seam is incomplete")
        if backend.get("execution") != "gpu_submit_wait":
            fail("execution does not record GPU submit/wait completion")
        scenes = execution.get("scenes")
        if not isinstance(scenes, list) or len(scenes) != len(manifest["scenes"]):
            fail("execution scene count mismatch")
        pixels = args.pixels.read_bytes()
        if len(pixels) != CAPTURE_BYTES:
            fail(f"Vulkan pixel span length mismatch: {len(pixels)} != {CAPTURE_BYTES}")
        out_scenes = []
        for expected, actual in zip(manifest["scenes"], scenes):
            if actual.get("id") != expected["id"] or actual.get("token") != expected["token"]:
                fail("scene identity/token mismatch: " + expected["id"])
            if actual.get("events") != expected["ops"]:
                fail("scene operation trace mismatch: " + expected["id"])
            counters = actual.get("counters")
            if not isinstance(counters, dict):
                fail("scene counters missing: " + expected["id"])
            for field, value in expected["expected"].items():
                if value is not None and counters.get(field) != value:
                    fail(f"{expected['id']} {field}: {counters.get(field)} != {value}")
            offset = expected["expected"]["slot_offset"]
            span = expected["expected"]["pixel_bytes"]
            out_scenes.append({"id": expected["id"], "token": expected["token"],
                               "events": expected["ops"], "counters": counters,
                               "pixel_offset": offset, "pixel_bytes": span,
                               "pixel_sha256": hashlib.sha256(pixels[offset:offset + span]).hexdigest()})
        args.pixels_out.write_bytes(pixels)
        trace = {
            "schema": "neon-paired-trace/v1",
            "producer": "anvil-vulkan-v3d",
            "execution_schema": "neon-vulkan-execution/v1",
            "backend_gpu": 1,
            "native_error": 0,
            "fallback": False,
            "backend_api": required_api,
            "backend_execution": "gpu_submit_wait",
            "manifest_digest": manifest_digest(manifest),
            "scenes": out_scenes,
        }
        args.trace_out.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
        print("VULKAN_TRACE: PASS")
        print("VULKAN_PIXELS: PASS")
        print("PRODUCER: anvil-vulkan-v3d")
        return 0
    except (GateError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
