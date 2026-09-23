#!/usr/bin/env python3
"""Desk build and returned-trace grader for vulkanTripleResourceProof.pi4.

The build is made from a private snapshot so the compiler cannot update the
shared Pi board build stamp.  A board run is deliberately outside this tool;
``--trace`` grades a captured md.l/board_run transcript only after the board
owner has explicitly authorized that run.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = pathlib.Path("RaspberryPi4/Examples/Diagnostics/vulkanTripleResourceProof.pi4")
MAGIC = 0x59524156
TAIL = 0x56415259
WORDS = 240
LOAD_ADDRESS = 0x500000
TRACE_BYTES = WORDS * 4
TRACE_ROWS = TRACE_BYTES // 16
ARTIFACT_PARENT = ROOT / "_work"
INSTALLED_COMPILER = pathlib.Path(
    r"C:\Embedded Compiler\PureBasicCode\OpenGl Work\ArduinoBasic\PureMetalForge.exe"
)
INSTALLED_COMPILER_SHA256 = "8f2e43d4b260c5fa049762e6212c4355ea9cf49d30c0c10092783d3a664a5367"
INSTALLED_KEYWORDS_SHA256 = "5167b0b5f1de571ad596d274eabbd0669852bf4997a5cdbf0483e898e05ae1b5"
# The silicon-faulting image was reproduced byte-for-byte before correcting
# the fixture.  The corrected image differs at the image-view slot lookup's
# ADRP/ADD address pair only; pin that predicted surgical result before build.
FAULTING_IMAGE_SHA256 = "fc895149836cdd6214b2537db9b47be6a8d7046d9c95a7b60ea9a9ea387d218b"
SLOT_FIXED_IMAGE_SHA256 = "38940e7709cd4360d20da668adbab90338c9b3a8ced917eb129aaa7a2c67ab0c"
FIXED_IMAGE_SHA256 = "c942fdf52697c80dbc3acc56850431366c04addbaa050fc840ecac3fb965922a"
SNAPSHOT_ITEMS = (pathlib.Path("Anvil"), pathlib.Path("RaspberryPi4"),
                  pathlib.Path("Boards"), pathlib.Path("tools"), pathlib.Path("keywords.def"))


@contextlib.contextmanager
def checker_lock():
    lock_path = pathlib.Path(tempfile.gettempdir()) / "anvil_vk_pipeline_check.lock"
    with lock_path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def need(ok: bool, text: str, bad: list[str]) -> None:
    if not ok:
        bad.append(text)


def sourcecheck(root: pathlib.Path) -> list[str]:
    text = (root / SOURCE).read_text(encoding="utf-8")
    bad: list[str] = []
    anchors = (
        "Procedure.i vvpBuildFsMixed()",
        "vtpHeader(35)",
        "vtpIns(133, 4) : vtpW(5) : vtpW(33) : vtpW(28) : vtpW(32)",
        "vtpIns(129, 4) : vtpW(5) : vtpW(34) : vtpW(33) : vtpW(30)",
        "dslb[0]\\descriptorType = #VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER",
        "dslb[1]\\descriptorType = #VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER",
        "vkDestroyShaderModule(dev, vs, 0) : vs = #VK_NULL_HANDLE",
        "vkDestroyShaderModule(dev, fs, 0) : fs = #VK_NULL_HANDLE",
        "vkDestroyPipelineLayout(dev, layout, 0) : layout = #VK_NULL_HANDLE",
        "vkCmdBindDescriptorSets(cmd, #VK_PIPELINE_BIND_POINT_GRAPHICS, layoutNew",
        "vkCmdPushConstants(cmd, layoutNew, #VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, @push[0])",
        "If elapsed >= 15000000",
        "#VVP_S_TAIL = 239",
        "aimg = avkIvImgSlot[av] : amem = avkImgMemSlot[aimg]",
        "vvpPut(#VVP_S_FAULT_CODE_BEFORE_MIX, AnvilVkFaultCode())",
        "vvpPut(#VVP_S_FAULT_CODE_AFTER_MIX, AnvilVkFaultCode())",
        "vvpGet(#VVP_S_FAULT_AFTER_MIX) <> vvpGet(#VVP_S_FAULT_BEFORE_MIX)",
    )
    for anchor in anchors:
        need(text.count(anchor) == 1, f"source anchor count != 1: {anchor}", bad)
    need("vvpSamplePass(phys, dev, queue, cmd, fence, @si, @bi, @rpbi, bufAll, bufUni, memUni, imgBase)" in text,
         "Main does not pass the UBO into the triple-resource path", bad)
    need("aimg = avkIvImage[av] : amem = avkImgMemSlot[aimg]" not in text,
         "attachment opaque image handle is used as an image-table index", bad)
    return bad


def file_sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_files(root: pathlib.Path) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for rel in SNAPSHOT_ITEMS:
        item = root / rel
        if item.is_file():
            files.append(item)
        else:
            files.extend(p for p in item.rglob("*") if p.is_file()
                         and "__pycache__" not in p.parts
                         and p.suffix not in (".pyc", ".img", ".tmp"))
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def manifest(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for path in manifest_files(root):
        name = path.relative_to(root).as_posix().encode("utf-8")
        value = bytes.fromhex(file_sha256(path))
        digest.update(struct.pack("<I", len(name)))
        digest.update(name)
        digest.update(value)
    return digest.hexdigest()


def validate_pmf_payload(image: bytes, payload: bytes) -> tuple[int, int]:
    if len(payload) < 128 or payload[:8] != b"PMFBOOT\0":
        raise ValueError("PMF payload lacks the exact PMFBOOT v2 header")
    version = struct.unpack_from("<I", payload, 8)[0]
    header_bytes = struct.unpack_from("<I", payload, 12)[0]
    load_address = struct.unpack_from("<Q", payload, 16)[0]
    entry_address = struct.unpack_from("<Q", payload, 24)[0]
    image_bytes = struct.unpack_from("<Q", payload, 32)[0]
    bss_base = struct.unpack_from("<Q", payload, 40)[0]
    bss_bytes = struct.unpack_from("<Q", payload, 48)[0]
    flags = struct.unpack_from("<I", payload, 56)[0]
    reserved = struct.unpack_from("<I", payload, 60)[0]
    architecture = struct.unpack_from("<I", payload, 96)[0]
    target = struct.unpack_from("<I", payload, 100)[0]
    stack_address = struct.unpack_from("<Q", payload, 104)[0]
    valid = (
        version == 2 and header_bytes == 128
        and load_address == LOAD_ADDRESS and entry_address == LOAD_ADDRESS
        and image_bytes == len(image) and len(payload) == header_bytes + len(image)
        and payload[header_bytes:] == image
        and payload[64:96] == hashlib.sha256(image).digest()
        and flags == 1 and reserved == 0
        and architecture == 1 and target == 2711
        and stack_address == 0x4F00000 and payload[112:128] == bytes(16)
    )
    if not valid:
        raise ValueError("PMF payload fails exact v2/AArch64/BCM2711/returns/image admission")
    return bss_base, bss_bytes


def report_symbol(symbols: pathlib.Path) -> int:
    # A64Assembler.pbi's symbol export contract is asymmetric: code labels are
    # image-relative, while BSS/global labels are already absolute addresses.
    # vvpReport is a global, so its decimal sidecar value is the trace address.
    matches = re.findall(
        r"(?m)^global_vvpreport=([0-9]+)\s*$",
        symbols.read_text(encoding="utf-8-sig"),
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one global_vvpreport symbol, found {len(matches)}")
    address = int(matches[0], 10)
    if address < LOAD_ADDRESS or address + TRACE_BYTES > 0x4F00000:
        raise RuntimeError(
            f"global_vvpreport address {address:#x} is outside the compiled image/BSS window")
    return address


def exact_decimal_symbol(symbols: pathlib.Path, name: str) -> int:
    matches = re.findall(
        rf"(?m)^{re.escape(name)}=([0-9]+)\s*$",
        symbols.read_text(encoding="utf-8-sig"),
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one {name} symbol, found {len(matches)}")
    return int(matches[0], 10)


def emitted_array_bases(image: bytes, symbols: pathlib.Path) -> list[int]:
    """Decode the compiler's five-instruction global array access idiom.

    This is intentionally a tiny A64 decoder, not a disassembler dependency.
    It proves that vvpSamplePass indexes the attachment memory table with the
    retained image *slot*: fb-view -> image-view slot -> image memory slot.
    """
    start = exact_decimal_symbol(symbols, "vvpsamplepass")
    end = exact_decimal_symbol(symbols, "main")
    if not (0 <= start < end <= len(image)):
        raise RuntimeError("vvpSamplePass/main code-symbol range is invalid")
    words = struct.unpack_from(f"<{(end - start) // 4}I", image, start)
    bases: list[int] = []
    for index in range(len(words) - 4):
        lsl, adrp, add_imm, add_reg, load = words[index:index + 5]
        if (lsl != 0xD37DF18B or add_reg != 0x8B0B018D
                or load != 0xF94001AB):
            continue
        if (adrp & 0x9F00001F) != 0x9000000C:
            continue
        if (add_imm & 0xFFC003FF) != 0x9100018C:
            continue
        pc = LOAD_ADDRESS + start + (index + 1) * 4
        immlo = (adrp >> 29) & 3
        immhi = (adrp >> 5) & 0x7FFFF
        pages = (immhi << 2) | immlo
        if pages & (1 << 20):
            pages -= 1 << 21
        page = (pc & ~0xFFF) + (pages << 12)
        shift = 12 if ((add_imm >> 22) & 1) else 0
        immediate = ((add_imm >> 10) & 0xFFF) << shift
        bases.append(page + immediate)
    return bases


def validate_emitted_attachment_slot(image: bytes, symbols: pathlib.Path) -> list[int]:
    bases = emitted_array_bases(image, symbols)
    fb_view = exact_decimal_symbol(symbols, "global_avkfbview")
    image_slot = exact_decimal_symbol(symbols, "global_avkivimgslot")
    opaque_image = exact_decimal_symbol(symbols, "global_avkivimage")
    memory_slot = exact_decimal_symbol(symbols, "global_avkimgmemslot")
    wanted = [fb_view, image_slot, memory_slot]
    wrong = [fb_view, opaque_image, memory_slot]
    triples = [bases[index:index + 3] for index in range(len(bases) - 2)]
    if triples.count(wanted) != 1:
        raise RuntimeError(
            "emitted vvpSamplePass lacks one exact fb-view -> image-slot -> memory-slot chain")
    if wrong in triples:
        raise RuntimeError(
            "emitted vvpSamplePass indexes image memory with an opaque image handle")
    return wanted


def private_build() -> dict[str, object]:
    compiler = INSTALLED_COMPILER.resolve()
    if not compiler.is_file():
        raise RuntimeError(f"mandated installed compiler missing: {compiler}")
    compiler_before = file_sha256(compiler)
    if compiler_before != INSTALLED_COMPILER_SHA256:
        raise RuntimeError(f"installed compiler hash {compiler_before} != pinned {INSTALLED_COMPILER_SHA256}")
    runtime_keywords = compiler.parent / "keywords.def"
    if not runtime_keywords.is_file():
        raise RuntimeError(f"installed compiler keywords missing: {runtime_keywords}")
    runtime_keywords_before = file_sha256(runtime_keywords)
    if runtime_keywords_before != INSTALLED_KEYWORDS_SHA256:
        raise RuntimeError(
            f"installed compiler keywords hash {runtime_keywords_before} != pinned "
            f"{INSTALLED_KEYWORDS_SHA256}")
    temp = pathlib.Path(tempfile.mkdtemp(prefix="anvil-vulkan-triple-desk-"))
    snap = temp / "Anvil"
    snap.mkdir()
    published: pathlib.Path | None = None
    try:
        with checker_lock():
            shared_before = manifest(ROOT)
            for rel in SNAPSHOT_ITEMS:
                source = ROOT / rel
                target = snap / rel
                if source.is_dir():
                    shutil.copytree(source, target, ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc", "*.img", "*.tmp"))
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            snapshot_manifest = manifest(snap)
            if snapshot_manifest != shared_before:
                raise RuntimeError(f"snapshot manifest {snapshot_manifest} != shared {shared_before}")
            snapshot_source_bad = sourcecheck(snap)
            if snapshot_source_bad:
                raise RuntimeError("frozen snapshot source check failed: " + "; ".join(snapshot_source_bad))
        out = temp / "vulkanTripleResourceProof.img"
        cmd = [str(compiler), "--compile", str(SOURCE), "-t", "pi4",
               "--load-addr", hex(LOAD_ADDRESS), "--stack-addr", "0x4F00000",
               "--entry-returns", "-o", str(out)]
        env = os.environ.copy()
        env["PMF_ROOT"] = str(snap)
        proc = subprocess.run(cmd, cwd=snap, text=True, capture_output=True,
                              timeout=300, env=env)
        log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            raise RuntimeError(f"compiler exited {proc.returncode}\n{log}")
        if not out.is_file() or out.stat().st_size == 0:
            raise RuntimeError(f"compiler returned success without image\n{log}")
        pmf = pathlib.Path(str(out) + ".pmf")
        symbols = pathlib.Path(str(out) + ".sym")
        debug = pathlib.Path(str(out) + ".dbg")
        symbol_meta = pathlib.Path(str(out) + ".sym.meta")
        if not all(path.is_file() for path in (pmf, symbols, debug, symbol_meta)):
            raise RuntimeError(
                "compiler returned success without .img.pmf/.img.sym/.img.dbg/.img.sym.meta sidecars")
        image_data = out.read_bytes()
        pmf_data = pmf.read_bytes()
        try:
            bss_base, bss_bytes = validate_pmf_payload(image_data, pmf_data)
        except ValueError as exc:
            raise RuntimeError(f"compiler .img.pmf is not deployable: {exc}") from exc
        report_address = report_symbol(symbols)
        attachment_slot_chain = validate_emitted_attachment_slot(image_data, symbols)
        if not (bss_base <= report_address
                and report_address + TRACE_BYTES <= bss_base + bss_bytes):
            raise RuntimeError(
                f"global_vvpreport [{report_address:#x},{report_address + TRACE_BYTES:#x}) "
                f"is outside PMF BSS [{bss_base:#x},{bss_base + bss_bytes:#x})")
        digest = hashlib.sha256(image_data).hexdigest()
        if digest != FIXED_IMAGE_SHA256:
            raise RuntimeError(
                f"corrected raw image hash {digest} != pinned fixed image {FIXED_IMAGE_SHA256}")
        compiler_after = file_sha256(compiler)
        if compiler_after != compiler_before:
            raise RuntimeError("installed compiler changed during build")
        runtime_keywords_after = file_sha256(runtime_keywords)
        if runtime_keywords_after != runtime_keywords_before:
            raise RuntimeError("installed compiler keywords changed during build")
        with checker_lock():
            shared_after = manifest(ROOT)
        if shared_after != shared_before:
            raise RuntimeError(f"shared input manifest changed: {shared_after} != {shared_before}")

        ARTIFACT_PARENT.mkdir(parents=True, exist_ok=True)
        published = pathlib.Path(tempfile.mkdtemp(
            prefix="vulkan-triple-resource-proof-", dir=ARTIFACT_PARENT))
        artifact_names = (out.name, pmf.name, symbols.name, debug.name, symbol_meta.name)
        for name in artifact_names:
            shutil.copy2(temp / name, published / name)
        (published / "compile.log").write_text(log, encoding="utf-8")
        provenance = {
            "compiler": str(compiler),
            "compiler_sha256": compiler_before,
            "compiler_keywords": str(runtime_keywords),
            "compiler_keywords_sha256": runtime_keywords_before,
            "snapshot_manifest": snapshot_manifest,
            "shared_manifest_before": shared_before,
            "shared_manifest_after": shared_after,
            "load_address": LOAD_ADDRESS,
            "report_symbol": "global_vvpreport",
            "report_symbol_address_rule": "BSS/global .sym values are absolute",
            "report_symbol_value": report_address,
            "report_address": report_address,
            "report_bytes": TRACE_BYTES,
            "bss_base": bss_base,
            "bss_bytes": bss_bytes,
            "image": out.name,
            "image_bytes": len(image_data),
            "image_sha256": digest,
            "faulting_image_sha256": FAULTING_IMAGE_SHA256,
            "slot_fixed_image_sha256": SLOT_FIXED_IMAGE_SHA256,
            "attachment_slot_chain": attachment_slot_chain,
            "payload": pmf.name,
            "payload_bytes": len(pmf_data),
            "payload_sha256": hashlib.sha256(pmf_data).hexdigest(),
            "symbols": symbols.name,
            "symbols_sha256": file_sha256(symbols),
            "debug": debug.name,
            "debug_sha256": file_sha256(debug),
            "symbol_meta": symbol_meta.name,
            "symbol_meta_sha256": file_sha256(symbol_meta),
            "pmf_root": str(snap),
            "command": cmd,
        }
        provenance_path = published / "provenance.json"
        provenance_path.write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = dict(provenance)
        result["artifact_dir"] = str(published.resolve())
        result["provenance"] = str(provenance_path.resolve())
        published = None
        return result
    finally:
        if published is not None:
            shutil.rmtree(published, ignore_errors=True)
        shutil.rmtree(temp, ignore_errors=True)


def extract_report(text: str, report_address: int) -> list[int]:
    rows: list[tuple[int, list[int], str]] = []
    word_row = re.compile(
        r"(?i)^\s*([0-9a-f]{8,16})\s*:\s*"
        r"((?:[0-9a-f]{8}\s+){3}[0-9a-f]{8})(?:\s+\|.*)?\s*$"
    )
    byte_row = re.compile(
        r"(?i)^\s*([0-9a-f]{8,16})\s*:\s*"
        r"((?:[0-9a-f]{2}\s+){15}[0-9a-f]{2})(?:\s+\|.*)?\s*$"
    )
    for line in text.splitlines():
        match = word_row.match(line)
        if match is not None:
            data = [int(value, 16) for value in match.group(2).split()]
            rows.append((int(match.group(1), 16), data, "u32"))
            continue
        match = byte_row.match(line)
        if match is not None:
            data_bytes = bytes(int(value, 16) for value in match.group(2).split())
            data = list(struct.unpack("<4I", data_bytes))
            rows.append((int(match.group(1), 16), data, "bytes"))
    expected_addresses = [report_address + 16 * i for i in range(TRACE_ROWS)]
    addresses = [address for address, _, _ in rows]
    formats = {format_name for _, _, format_name in rows}
    if len(rows) != TRACE_ROWS or addresses != expected_addresses or len(formats) != 1:
        raise ValueError(
            f"trace rows must be exactly {TRACE_ROWS} contiguous memory/md.l rows from "
            f"{report_address:08X}; got {len(rows)} rows starting "
            f"{addresses[0]:08X}" if addresses else
            f"trace rows must be exactly {TRACE_ROWS} contiguous memory/md.l rows from "
            f"{report_address:08X}; got no rows"
        )
    words = [word for _, data, _ in rows for word in data]
    if words[0] != MAGIC or words[-1] != TAIL:
        raise ValueError("anchored 960-byte report lacks VARY...YRAV framing")
    return words


def validate_provenance(path: pathlib.Path) -> tuple[dict[str, object], int]:
    provenance = json.loads(path.read_text(encoding="utf-8"))
    if provenance.get("compiler") != str(INSTALLED_COMPILER.resolve()):
        raise ValueError("trace provenance compiler path is not the mandated installed compiler")
    if provenance.get("compiler_sha256") != INSTALLED_COMPILER_SHA256:
        raise ValueError("trace provenance compiler hash is not the pinned installed compiler")
    if provenance.get("compiler_keywords") != str((INSTALLED_COMPILER.parent / "keywords.def").resolve()):
        raise ValueError("trace provenance keywords path is not the installed compiler keywords")
    if provenance.get("compiler_keywords_sha256") != INSTALLED_KEYWORDS_SHA256:
        raise ValueError("trace provenance keywords hash is not pinned")
    if provenance.get("report_symbol") != "global_vvpreport":
        raise ValueError("trace provenance does not name global_vvpreport")
    if provenance.get("report_symbol_address_rule") != "BSS/global .sym values are absolute":
        raise ValueError("trace provenance does not use the absolute BSS/global symbol rule")
    if provenance.get("load_address") != LOAD_ADDRESS:
        raise ValueError("trace provenance load address is not 0x500000")
    if provenance.get("report_bytes") != TRACE_BYTES:
        raise ValueError("trace provenance report size is not 960 bytes")
    report_address = int(provenance["report_address"])
    if provenance.get("report_symbol_value") != report_address:
        raise ValueError("trace provenance symbol value does not equal its report address")

    image = path.parent / str(provenance["image"])
    payload = path.parent / str(provenance["payload"])
    symbols = path.parent / str(provenance["symbols"])
    debug = path.parent / str(provenance["debug"])
    symbol_meta = path.parent / str(provenance["symbol_meta"])
    for artifact in (image, payload, symbols, debug, symbol_meta):
        if artifact.parent.resolve() != path.parent.resolve() or not artifact.is_file():
            raise ValueError(f"trace provenance sibling artifact is missing: {artifact.name}")
    image_data = image.read_bytes()
    payload_data = payload.read_bytes()
    if len(image_data) != provenance.get("image_bytes") or file_sha256(image) != provenance.get("image_sha256"):
        raise ValueError("trace provenance image size/hash mismatch")
    if len(payload_data) != provenance.get("payload_bytes") or file_sha256(payload) != provenance.get("payload_sha256"):
        raise ValueError("trace provenance PMF payload size/hash mismatch")
    if file_sha256(symbols) != provenance.get("symbols_sha256"):
        raise ValueError("trace provenance symbol hash mismatch")
    if file_sha256(debug) != provenance.get("debug_sha256"):
        raise ValueError("trace provenance debug-map hash mismatch")
    if file_sha256(symbol_meta) != provenance.get("symbol_meta_sha256"):
        raise ValueError("trace provenance symbol-metadata hash mismatch")
    bss_base, bss_bytes = validate_pmf_payload(image_data, payload_data)
    if provenance.get("bss_base") != bss_base or provenance.get("bss_bytes") != bss_bytes:
        raise ValueError("trace provenance BSS range differs from its PMF header")
    if report_symbol(symbols) != report_address:
        raise ValueError("trace provenance report address differs from the compiled symbol sidecar")
    if not (bss_base <= report_address
            and report_address + TRACE_BYTES <= bss_base + bss_bytes):
        raise ValueError("trace provenance report lies outside the PMF BSS range")
    return provenance, report_address


def grade_metadata_and_faults(words: list[int]) -> list[str]:
    bad: list[str] = []
    # Semantic order, independent of where this report stores the late-added
    # UBO config index: push RGBA, UBO address/config, texture/sampler, TLB.
    meta = words[206:211] + [words[233]] + words[211:214]
    need(meta == [4, 5, 6, 7, 2, 3, 0, 1, 8], f"canonical metadata indices={meta!r}", bad)
    # FaultClear clears the current code/text, deliberately not the lifetime
    # refusal count. Five earlier hostile probes are expected; equality across
    # pass D plus clear current codes proves the mixed path added none.
    need(words[214] == 5 and words[215] == words[214] and words[96] == words[215],
         f"cumulative validation faults={words[214]}/{words[215]}/{words[96]}", bad)
    need(words[237] == 0 and words[238] == 0,
         f"mixed-path current fault codes={words[237]}/{words[238]}", bad)
    return bad


def causal_selfcheck() -> list[str]:
    words = [0] * WORDS
    words[206:214] = [4, 5, 6, 7, 2, 0, 1, 8]
    words[233] = 3
    words[214] = words[215] = words[96] = 5
    bad: list[str] = []
    need(grade_metadata_and_faults(words) == [], "causal baseline", bad)
    for index, value, label in (
        (206, 3, "metadata order"),
        (215, 6, "new mixed fault"),
        (237, 0xFFFFFFFF, "uncleared pre-mix fault"),
        (238, 0xFFFFFFFF, "uncleared post-mix fault"),
    ):
        changed = list(words)
        changed[index] = value
        need(bool(grade_metadata_and_faults(changed)), f"causal mutation escaped: {label}", bad)
    return bad


def grade(words: list[int]) -> list[str]:
    bad: list[str] = []
    need(len(words) == WORDS, "report length", bad)
    if len(words) != WORDS:
        return bad
    need(words[0] == MAGIC and words[239] == TAIL, "report magic/tail", bad)
    need(words[126] == WORDS * 4, "reported byte count", bad)
    need(words[128] == 0, f"triple-resource verdict={words[128]}", bad)
    need(words[131] == 0 and words[132] == 0, "submit/wait result", bad)
    need(words[133:136] == [0xFF808000, 0xFF800080, 0xFFFF0000],
         f"inside pixels={words[133:136]!r}", bad)
    need(words[136:139] == [0xFF3380B2] * 3, "outside pixels", bad)
    need(words[176] == 1, "module/layout destroy-reuse lifetime", bad)
    need(words[177] == words[181] and words[179] == words[183], "module slot reuse", bad)
    need(words[182] != words[178] and words[184] != words[180], "module generation advance", bad)
    need(words[185] == words[187] and words[188] != words[186], "layout slot/generation reuse", bad)
    need(words[189] == 0 and words[190] == 0 and words[191:200] == [0] * 9,
         f"retains not released={words[189:200]!r}", bad)
    need(words[200:204] == [0x3F000000, 0x3F000000, 0x3F000000, 0], "push payload", bad)
    need(words[205] == 9, f"uniform word count={words[205]}", bad)
    bad.extend(grade_metadata_and_faults(words))
    need(words[224:228] == [0x3F000000, 0x3F000000, 0x3F000000, 0], "patched push words", bad)
    need(words[228] == words[204] and words[229] == 0xFFFFFF7C, "patched UBO words", bad)
    need(words[143:149] == [words[129], 0x10000000, 0x00400400, 0x00A9C840, 0x83, 0x00090000],
         f"decoded texture/sampler state={words[143:149]!r}", bad)
    need(words[236] == 0x40, f"optimal UIF word4={words[236]:08x}", bad)
    need((words[230] & 0xF) == 0xF and (words[231] & 1) == 1
         and (words[231] & 0xFFFFFFFE) - (words[230] & 0xFFFFFFF0) == 256,
         "texture/sampler pointer tags or state-base spacing", bad)
    need(words[232] == 0xFFFFFFFF, "patched TLB word", bad)
    need(words[234] == 0 and words[235] == 0, "sequential descriptor updates", bad)
    need(0 < words[216] < 15_000_000, f"deadman elapsed={words[216]}us", bad)
    need(words[217:220] == [0xFF808000, 0xFF800080, 0xFFFF0000] and words[220] == 1,
         "expected/exact pixel evidence", bad)
    need(words[221] == 1 and words[222] == 1, "exact V3D bin/render job deltas", bad)
    need(words[160] - words[159] == 1, "exact TFU job delta", bad)
    need(words[164] == 0 and words[165] == 0 and words[166] == 5,
         "copy submit/wait/layout", bad)
    need(words[139] == 376 and words[157] != 0 and words[158] == 4,
         "fragment bytes/shader record/backend draw count", bad)
    need(words[110] == 1 and words[125] == 13, "shutdown/final step", bad)
    need(words[153] == 0 and words[154] == 0 and words[155] == 0,
         "MMU/OOM/native fault", bad)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--trace", type=pathlib.Path)
    ap.add_argument("--provenance", type=pathlib.Path,
                    help="provenance.json from the exact compiled payload used for --trace")
    args = ap.parse_args()

    bad = sourcecheck(ROOT)
    if bad:
        print("vulkan_triple_resource_proof_check: FAIL (source)")
        for item in bad:
            print(f"  - {item}")
        return 1
    print("vulkan_triple_resource_proof_check: source PASS")
    bad = causal_selfcheck()
    if bad:
        print("vulkan_triple_resource_proof_check: FAIL (causal desk checks)")
        for item in bad:
            print(f"  - {item}")
        return 1
    print("vulkan_triple_resource_proof_check: causal desk PASS - metadata order/count delta/current-code mutations rejected")

    if args.compile:
        built = private_build()
        print(f"vulkan_triple_resource_proof_check: compiler={INSTALLED_COMPILER} sha256={INSTALLED_COMPILER_SHA256}")
        print(f"vulkan_triple_resource_proof_check: compiler keywords={built['compiler_keywords']} sha256={built['compiler_keywords_sha256']}")
        print(f"vulkan_triple_resource_proof_check: snapshot manifest={built['snapshot_manifest']}")
        print(f"vulkan_triple_resource_proof_check: shared pre={built['shared_manifest_before']} post={built['shared_manifest_after']}")
        print(f"vulkan_triple_resource_proof_check: compile PASS bytes={built['image_bytes']} sha256={built['image_sha256']}")
        print(f"vulkan_triple_resource_proof_check: deployable payload={pathlib.Path(str(built['artifact_dir'])) / str(built['payload'])}")
        print(f"vulkan_triple_resource_proof_check: symbols={pathlib.Path(str(built['artifact_dir'])) / str(built['symbols'])}")
        print(f"vulkan_triple_resource_proof_check: debug={pathlib.Path(str(built['artifact_dir'])) / str(built['debug'])}")
        print(f"vulkan_triple_resource_proof_check: symbol metadata={pathlib.Path(str(built['artifact_dir'])) / str(built['symbol_meta'])}")
        print(f"vulkan_triple_resource_proof_check: provenance={built['provenance']}")
        print(f"vulkan_triple_resource_proof_check: report address={int(built['report_address']):08X} bytes={TRACE_BYTES}")

    if args.trace:
        try:
            if args.provenance is None:
                raise ValueError("--trace requires the exact compiled --provenance file")
            _provenance, report_address = validate_provenance(args.provenance)
            report = extract_report(
                args.trace.read_text(encoding="utf-8", errors="replace"),
                report_address,
            )
            bad = grade(report)
        except (KeyError, json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            bad = [str(exc)]
        if bad:
            print("vulkan_triple_resource_proof_check: FAIL (trace)")
            for item in bad:
                print(f"  - {item}")
            return 1
        print("vulkan_triple_resource_proof_check: trace PASS - exact pixel/lifetime/metadata/post-submit-release/deadman proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
