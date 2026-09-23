#!/usr/bin/env python3
"""Strict manifest-bound Neon native/Vulkan oracle checker."""
from __future__ import annotations
import argparse, hashlib, json, struct, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Examples/Diagnostics/neonCompatibilityPixelOracle.pi4"
MANIFEST = ROOT / "RaspberryPi4/Tests/neon_compatibility_golden.json"
MAGIC, VERSION, SCENE_COUNT, SCENE_BYTES = 0x4E434F32, 1, 15, 16384
HEADER_WORDS, RECORD_WORDS = 16, 32
CAPTURE_BASE, CAPTURE_BYTES = 0x07000000, SCENE_COUNT * SCENE_BYTES
REPORT_BYTES = (HEADER_WORDS + SCENE_COUNT * RECORD_WORDS) * 4

class GateError(Exception): pass
def fail(message): raise GateError(message)

def load_manifest():
    try: data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: fail(f"manifest read failed: {exc}")
    if data.get("schema") != "neon-compatibility-golden/v2": fail("schema drift")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != SCENE_COUNT: fail("scene count drift")
    if len({s.get("id") for s in scenes}) != SCENE_COUNT or len({s.get("token") for s in scenes}) != SCENE_COUNT: fail("scene ids/tokens are not unique")
    for s in scenes:
        if not isinstance(s.get("ops"), list) or not s["ops"] or not isinstance(s.get("expected"), dict): fail(f"invalid scene: {s.get('id')}")
        if s["expected"].get("slot_bytes") != SCENE_BYTES: fail(f"slot size drift: {s['id']}")
        pb=s["expected"].get("pixel_bytes"); pitch=s["expected"].get("pitch"); ph=s["expected"].get("physical_h")
        if not isinstance(pb,int) or pb <= 0 or pb > SCENE_BYTES or pb != pitch * ph: fail(f"pixel span drift: {s['id']}")
    return data

def digest(data): return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).digest()

def check_source(data, source_text=None):
    text = SOURCE.read_text(encoding="utf-8") if source_text is None else source_text
    for needle in ("#NCO_MAGIC = $4E434F32", "#NCO_VERSION = 1", "#NCO_SCENES = 15", "#NCO_REPORT_HEADER_WORDS = 16", "#NCO_REPORT_RECORD_WORDS = 32", "#NCO_SCENE_BYTES = 16384", "NCO_FIRST_ERROR", "NeonFrameBegin(", "NeonFrameEnd()", "NeonFanOutline", "NeonFanEnd", "Neon_TextTex", "NeonRebindSurface", "NCO_TOKEN_", "Procedure ncoProgress(scene.i, value.i)", "ncoProgress(scene, $200 + scene)", "& $FFFFFFFF) <> #NCO_POISON"):
        if needle not in text: fail("source anchor missing: " + needle)
    if "ncoWord(#NCO_REPORT_HEADER_WORDS, $200 + scene)" in text: fail("scene progress overwrites record zero")
    h=digest(data); words=struct.unpack("<8I", h)
    for i,w in enumerate(words):
        if ("$%08X" % w) not in text: fail("source manifest digest word missing: " + str(i))
    for s in data["scenes"]:
        marker = "NCO_SCENE_" + s["id"].upper().replace("-", "_")
        if marker not in text or s["token"] not in text: fail("source/manifest scene marker missing: " + s["id"])
    return 22 + len(data["scenes"])

FIELDS = ("status", "logical_w", "logical_h", "physical_w", "physical_h", "pitch", "slot_offset", "slot_bytes", "pixel_bytes", "draws", "boxes", "glyphs", "runs", "verts", "tex_draws", "tex_glyphs", "tex_verts", "clipped", "guard_bad", "first_error")

def parse_report(blob, data, pixels):
    if len(pixels) != CAPTURE_BYTES: fail(f"pixel artifact length mismatch: {len(pixels)} != {CAPTURE_BYTES}")
    need = (HEADER_WORDS + SCENE_COUNT * RECORD_WORDS) * 4
    if len(blob) != need: fail(f"report length mismatch: {len(blob)} != {need}")
    words = struct.unpack_from("<%dI" % (HEADER_WORDS + SCENE_COUNT * RECORD_WORDS), blob)
    if words[:3] != (MAGIC, VERSION, SCENE_COUNT): fail("report magic/version/scene count mismatch")
    if words[3] != HEADER_WORDS or words[12] != CAPTURE_BASE or words[13] != CAPTURE_BYTES or words[14] != REPORT_BYTES or words[15] != SCENE_BYTES: fail("report header dimensions/addresses mismatch")
    if bytes(struct.pack("<8I", *words[4:12])) != digest(data)[:32]: fail("manifest digest mismatch")
    records=[]
    for i,s in enumerate(data["scenes"]):
        rec=words[HEADER_WORDS+i*RECORD_WORDS:HEADER_WORDS+(i+1)*RECORD_WORDS]
        if rec[0] != int(s["token"],16): fail("token mismatch: "+s["id"])
        got=dict(zip(FIELDS,rec[1:1+len(FIELDS)])); expected=s["expected"]
        for f in FIELDS:
            if expected[f] is not None and got[f] != expected[f]: fail(f"{s['id']} {f}: {got[f]} != {expected[f]}")
        start,end=got["slot_offset"],got["slot_offset"]+got["pixel_bytes"]
        if start<0 or end>len(pixels): fail("pixel span outside artifact: "+s["id"])
        got["pixel_sha256"] = hashlib.sha256(pixels[start:end]).hexdigest()
        if s.get("pixel_sha256") and got["pixel_sha256"] != s["pixel_sha256"]: fail("pixel hash mismatch: " + s["id"])
        records.append(got)
    return records

def synthetic(data):
    d=digest(data); words=[MAGIC,VERSION,SCENE_COUNT,HEADER_WORDS]+list(struct.unpack("<8I",d[:32]))+[CAPTURE_BASE,CAPTURE_BYTES,REPORT_BYTES,SCENE_BYTES]; pixels=bytearray(SCENE_COUNT*SCENE_BYTES)
    for s in data["scenes"]:
        e=s["expected"]; words += [int(s["token"],16)]+[(0 if e[f] is None else e[f]) for f in FIELDS]+[0]*(RECORD_WORDS-1-len(FIELDS))
    return struct.pack("<%dI"%len(words),*words),bytes(pixels)

def mutations(data):
    report, pixels = synthetic(data)
    parse_report(report, data, pixels)
    total = 0
    def expect(label, bad_report=None, bad_pixels=None, bad_data=None):
        nonlocal total
        try:
            parse_report(bad_report if bad_report is not None else report,
                         bad_data if bad_data is not None else data,
                         bad_pixels if bad_pixels is not None else pixels)
        except (GateError, ValueError, struct.error):
            total += 1
            return
        fail("mutation escaped: " + label)
    # Header and fixed-record corruption.
    expect("magic", struct.pack("<I", 0) + report[4:])
    expect("version", report[:4] + struct.pack("<I", 2) + report[8:])
    expect("status", report[:(HEADER_WORDS + 1) * 4] + struct.pack("<I", 9) + report[(HEADER_WORDS + 2) * 4:])
    expect("guard", report[:(HEADER_WORDS + 18) * 4] + struct.pack("<I", 1) + report[(HEADER_WORDS + 19) * 4:])
    expect("token", report[:HEADER_WORDS * 4] + struct.pack("<I", 0) + report[(HEADER_WORDS + 1) * 4:])
    expect("logical-dim", report[:(HEADER_WORDS + 2) * 4] + struct.pack("<I", 99) + report[(HEADER_WORDS + 3) * 4:])
    expect("physical-dim", report[:(HEADER_WORDS + 3) * 4] + struct.pack("<I", 99) + report[(HEADER_WORDS + 4) * 4:])
    expect("pitch", report[:(HEADER_WORDS + 6) * 4] + struct.pack("<I", 1) + report[(HEADER_WORDS + 7) * 4:])
    expect("offset", report[:(HEADER_WORDS + 7) * 4] + struct.pack("<I", CAPTURE_BYTES) + report[(HEADER_WORDS + 8) * 4:])
    expect("span", report[:(HEADER_WORDS + 8) * 4] + struct.pack("<I", 1) + report[(HEADER_WORDS + 9) * 4:])
    expect("counter", report[:(HEADER_WORDS + 9) * 4] + struct.pack("<I", 999) + report[(HEADER_WORDS + 10) * 4:])
    expect("report-truncation", report[:-4])
    # Pixel corruption is checked with a cloned manifest carrying synthetic hashes.
    hashed = json.loads(json.dumps(data))
    for scene in hashed["scenes"]:
        e=scene["expected"]; scene["pixel_sha256"] = hashlib.sha256(bytes(e["pixel_bytes"])).hexdigest()
    good_report, good_pixels = synthetic(hashed); parse_report(good_report, hashed, good_pixels)
    bad_pixels = bytearray(good_pixels); bad_pixels[0] ^= 1
    expect("pixel-hash-corruption", good_report, bytes(bad_pixels), hashed)
    expect("pixel-truncation", report, pixels[:-1])
    # Reordered/missing records are rejected by the ordered token join.
    rec0 = report[HEADER_WORDS * 4:(HEADER_WORDS + RECORD_WORDS) * 4]
    rec1 = report[(HEADER_WORDS + RECORD_WORDS) * 4:(HEADER_WORDS + 2 * RECORD_WORDS) * 4]
    swapped = report[:HEADER_WORDS * 4] + rec1 + rec0 + report[(HEADER_WORDS + 2 * RECORD_WORDS) * 4:]
    expect("reordered-scene", swapped)
    expect("missing-scene", report[:-RECORD_WORDS * 4])
    # Manifest operation/token binding: changing the manifest invalidates its digest.
    changed = json.loads(json.dumps(data)); changed["scenes"][0]["ops"][0]["op"] = "tampered"
    expect("operation-token", bad_data=changed)
    # Source-level mutations cover the two historical oracle defects.
    source = SOURCE.read_text(encoding="utf-8")
    for label, mutated in (
        ("progress overwrites scene zero", source.replace("ncoProgress(scene, $200 + scene)", "ncoWord(#NCO_REPORT_HEADER_WORDS, $200 + scene)")),
        ("signed guard compare", source.replace("(PeekL(Neon_GuardAddr() + (i * 4)) & $FFFFFFFF)", "PeekL(Neon_GuardAddr() + (i * 4))")),
    ):
        try:
            check_source(data, mutated)
        except GateError:
            total += 1
        else:
            fail("source mutation escaped: " + label)
    # Vulkan artifact mutations exercise provenance and pixel binding, rather
    # than only the native report parser.
    valid = {"schema": "neon-paired-trace/v1", "producer": "anvil-vulkan-v3d",
             "execution_schema": "neon-vulkan-execution/v1", "backend_gpu": 1,
             "native_error": 0, "fallback": False,
             "backend_api": ["AnvilVkV3dWindow", "avkBackendPrepare", "avkBackendSubmitDraw", "avkBackendDraws"],
             "backend_execution": "gpu_submit_wait", "manifest_digest": digest(data).hex(), "scenes": []}
    for s in data["scenes"]:
        e = s["expected"]; span = e["pixel_bytes"]
        valid["scenes"].append({"id": s["id"], "token": s["token"], "events": s["ops"],
                                 "counters": e, "pixel_offset": e["slot_offset"],
                                 "pixel_bytes": span, "pixel_sha256": hashlib.sha256(bytes(span)).hexdigest()})
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "vulkan.json"
        pixels = bytes(CAPTURE_BYTES)
        path.write_text(json.dumps(valid), encoding="utf-8")
        check_trace(path, data, require_vulkan=True, pixels=pixels)
        for label, key, value in (("producer", "producer", "native-copy"),
                                  ("fallback", "fallback", True),
                                  ("pixel-digest", "pixel_sha256", "00" * 32)):
            mutated = json.loads(json.dumps(valid))
            if label == "pixel-digest": mutated["scenes"][0][key] = value
            else: mutated[key] = value
            path.write_text(json.dumps(mutated), encoding="utf-8")
            try:
                check_trace(path, data, require_vulkan=True, pixels=pixels)
            except GateError:
                total += 1
            else:
                fail("Vulkan artifact mutation escaped: " + label)
    return total

def check_trace(path, data, require_vulkan=False, pixels=None):
    try: trace = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: fail("trace read failed: " + str(exc))
    if trace.get("schema") != "neon-paired-trace/v1": fail("trace schema mismatch")
    if require_vulkan:
        if trace.get("producer") != "anvil-vulkan-v3d": fail("Vulkan trace producer is not the Anvil V3D backend")
        if trace.get("execution_schema") != "neon-vulkan-execution/v1": fail("Vulkan execution schema missing")
        if trace.get("backend_gpu") != 1 or trace.get("native_error") != 0: fail("Vulkan trace does not prove a GPU execution")
        if trace.get("fallback") is not False: fail("Vulkan trace fallback marker is not false")
        if trace.get("backend_api") != ["AnvilVkV3dWindow", "avkBackendPrepare", "avkBackendSubmitDraw", "avkBackendDraws"]:
            fail("Vulkan trace backend API seam is incomplete")
        if trace.get("backend_execution") != "gpu_submit_wait": fail("Vulkan trace has no GPU submit/wait completion")
    if trace.get("manifest_digest") != digest(data).hex(): fail("trace manifest digest mismatch")
    got = trace.get("scenes")
    if not isinstance(got, list) or len(got) != SCENE_COUNT: fail("trace scene count mismatch")
    for expected, actual in zip(data["scenes"], got):
        if actual.get("id") != expected["id"] or actual.get("token") != expected["token"]: fail("trace scene join mismatch: " + expected["id"])
        if not isinstance(actual.get("events"), list) or not isinstance(actual.get("counters"), dict): fail("trace payload mismatch: " + expected["id"])
        if actual["events"] != expected["ops"]: fail("trace operation mismatch: " + expected["id"])
        for field, value in expected["expected"].items():
            if value is not None and actual["counters"].get(field) != value: fail("trace counter mismatch: " + expected["id"] + " " + field)
        if require_vulkan:
            offset = actual.get("pixel_offset")
            span = actual.get("pixel_bytes")
            sha = actual.get("pixel_sha256")
            if pixels is None or not isinstance(offset, int) or not isinstance(span, int) or not isinstance(sha, str):
                fail("Vulkan trace pixel binding missing: " + expected["id"])
            if offset != expected["expected"]["slot_offset"] or span != expected["expected"]["pixel_bytes"]:
                fail("Vulkan trace pixel span mismatch: " + expected["id"])
            if hashlib.sha256(pixels[offset:offset + span]).hexdigest() != sha:
                fail("Vulkan trace pixel digest mismatch: " + expected["id"])
    return len(got) + 2

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("--native-report-bin",type=Path); ap.add_argument("--native-pixels",type=Path); ap.add_argument("--write-native-json",type=Path); ap.add_argument("--native-trace",type=Path); ap.add_argument("--vulkan-trace",type=Path); ap.add_argument("--vulkan-pixels",type=Path); ap.add_argument("--mutate",action="store_true"); a=ap.parse_args(argv)
    try:
        data=load_manifest(); checks=check_source(data)
        if a.mutate: checks += mutations(data)
        if bool(a.vulkan_trace) != bool(a.vulkan_pixels): fail("Vulkan mode requires trace and pixels")
        if a.vulkan_trace:
            if not a.native_report_bin or not a.native_pixels: fail("Vulkan mode requires native report and pixels")
            vulkan_pixels = a.vulkan_pixels.read_bytes()
            checks += check_trace(a.vulkan_trace, data, require_vulkan=True, pixels=vulkan_pixels)
            if a.native_trace:
                checks += check_trace(a.native_trace, data)
            if a.native_pixels:
                native_pixels = a.native_pixels.read_bytes()
                if len(vulkan_pixels) != CAPTURE_BYTES: fail("Vulkan pixel artifact length mismatch")
                for scene in data["scenes"]:
                    e = scene["expected"]; start = e["slot_offset"]; end = start + e["pixel_bytes"]
                    if native_pixels[start:end] != vulkan_pixels[start:end]: fail("native/Vulkan pixel span mismatch: " + scene["id"])
        if bool(a.native_report_bin) != bool(a.native_pixels): fail("binary mode requires report and pixels")
        if a.native_trace and not a.vulkan_trace: checks += check_trace(a.native_trace, data)
        native="NOT_AVAILABLE"
        if a.native_report_bin:
            records=parse_report(a.native_report_bin.read_bytes(),data,a.native_pixels.read_bytes()); native="PASS"
            if a.write_native_json: a.write_native_json.write_text(json.dumps({"schema":"neon-native-artifact/v1","manifest_digest":digest(data).hex(),"records":records},indent=2)+"\n",encoding="utf-8")
        print(f"PASS: {checks} contract checks"); print("NATIVE_GOLDEN: "+native); return 0
    except (GateError,OSError,KeyError,TypeError,ValueError,struct.error) as exc: print("FAIL: "+str(exc),file=sys.stderr); return 1
if __name__ == "__main__": raise SystemExit(main())
