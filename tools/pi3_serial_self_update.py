#!/usr/bin/env python3
"""Stage and verify a Pi 3 kernel8.img through the monitor's `receive`/`save` path.

This helper deliberately does not reset the board. By default it validates the
bundle manifest locally and prints the planned addresses. `--execute` enables
the serial transfer and the in-place `kernel8.img` write; use it only after the
candidate build has passed its emitted gates and has been reviewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import zlib

STAGE = 0x02E00000
LOW_WINDOW_END = 0x03000000
MAX_KERNEL_BYTES = LOW_WINDOW_END - STAGE
BLOCK = 1024
PROMPT = re.compile(rb"pmf>\s*$", re.I)


class UpdateError(RuntimeError):
    pass


def load_bundle(bundle: Path, manifest_sha: str) -> tuple[Path, bytes, dict]:
    manifest_path = bundle / "SHA256.json"
    raw_manifest = manifest_path.read_bytes()
    got_manifest_sha = hashlib.sha256(raw_manifest).hexdigest()
    if got_manifest_sha.lower() != manifest_sha.lower():
        raise UpdateError(f"bundle manifest SHA mismatch: {got_manifest_sha}")
    manifest = json.loads(raw_manifest)
    pmf = manifest.get("monitorPmf", {})
    if (pmf.get("target") != 2837 or pmf.get("loadAddress") != 0x00200000 or
            pmf.get("imageBytes") != len((bundle / "kernel8.img").read_bytes()) or
            pmf.get("architecture") != 1):
        raise UpdateError("bundle PMF metadata is not a Pi3 AArch64 image at 0x00200000")
    entry = manifest.get("files", {}).get("kernel8.img")
    if not isinstance(entry, dict):
        raise UpdateError("SHA256.json has no kernel8.img entry")
    image_path = bundle / "kernel8.img"
    image = image_path.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    if len(image) != entry.get("bytes") or digest.lower() != str(entry.get("sha256", "")).lower():
        raise UpdateError("kernel8.img does not match its bundle manifest")
    if not image:
        raise UpdateError("kernel8.img is empty")
    # The live Pi3 map has a 2 MiB low payload interval at 0x02e00000 before
    # the fixed display render area at 0x03000000. The saved file is loaded
    # back over this same span after writing, so no second buffer is needed.
    # Refuse before opening COM30 if the candidate no longer fits that layout.
    if len(image) > MAX_KERNEL_BYTES:
        raise UpdateError(f"image is {len(image)} bytes; exceeds the verified 2 MiB low-window gap")
    return image_path, image, manifest


def make_prompt_reader(port, log):
    pending = bytearray()

    def read_prompt(timeout: float, *, stop_at: bytes | None = None) -> bytes:
        deadline = time.monotonic() + timeout
        received = bytearray()
        while time.monotonic() < deadline:
            if pending:
                chunk = bytes(pending)
                pending.clear()
            else:
                chunk = port.read(port.in_waiting or 1)
            if chunk:
                received.extend(chunk)
                if stop_at is not None:
                    at = received.lower().find(stop_at.lower())
                    if at >= 0:
                        end_at = at + len(stop_at)
                        pending.extend(received[end_at:])
                        raw = bytes(received[:end_at])
                        log("rx", raw, timeout_s=timeout,
                            stop_at=stop_at.decode("ascii", "replace"))
                        return raw
                prompt = PROMPT.search(received)
                if prompt:
                    pending.extend(received[prompt.end():])
                    raw = bytes(received[:prompt.end()])
                    log("rx", raw, timeout_s=timeout, stop_at="prompt")
                    return raw
            else:
                time.sleep(.002)
        raw = bytes(received)
        log("rx", raw, timeout_s=timeout,
            stop_at=stop_at.decode("ascii", "replace") if stop_at else "prompt")
        if not raw:
            raise UpdateError("serial receive timed out without bytes")
        return raw
    return read_prompt


def command(port, read_prompt, log, line: str, timeout: float = 180,
            stop_after: bytes | None = None) -> bytes:
    """Send a line with echo pacing; never continue after a missing echo."""
    log("command", b"", command=line)
    output = bytearray()
    expected = bytearray()
    echo_line = bytearray()
    for char in line:
        encoded = char.encode("ascii")
        expected.extend(encoded)
        port.write(encoded)
        port.flush()
        deadline = time.monotonic() + 60
        seen = bytearray()
        matched = False
        while time.monotonic() < deadline:
            chunk = port.read(port.in_waiting or 1)
            if chunk:
                seen.extend(chunk)
                echo_line.extend(chunk)
                if echo_line.lower().endswith(expected.lower()):
                    matched = True
                    break
            else:
                time.sleep(.002)
        raw = bytes(seen)
        log("echo", raw, command_prefix=expected.decode("ascii"))
        output.extend(raw)
        if not matched:
            raise UpdateError(f"command echo prefix {expected!r} not observed; aborted before CR")
    port.write(b"\r")
    port.flush()
    tail = read_prompt(timeout, stop_at=stop_after)
    output.extend(tail)
    if stop_after is not None:
        if stop_after.lower() not in tail.lower():
            raise UpdateError(f"expected response marker {stop_after!r} missing after {line}")
    elif not PROMPT.search(tail):
        raise UpdateError(f"prompt missing after command: {line}")
    return bytes(output)


def transfer(port, read_prompt, log, image: bytes, crc: int) -> None:
    header = f"receive {STAGE:X} {len(image):X} {crc:08X}"
    response = command(port, read_prompt, log, header, timeout=30,
                       stop_after=b"rdy")
    if not re.search(rb"(?:^|\r?\n)rdy(?:\r?\n|$)", response, re.I):
        raise UpdateError("monitor did not issue rdy; image bytes were not sent")
    count = (len(image) + BLOCK - 1) // BLOCK
    for index in range(count):
        start = index * BLOCK
        chunk = image[start:start + BLOCK]
        log("tx-block", b"", offset=start, length=len(chunk), block=index + 1, blocks=count)
        port.write(chunk)
        port.flush()
        ack = read_prompt(15, stop_at=b"+")
        if b"+" not in ack:
            raise UpdateError(f"missing block ACK after offset 0x{start:X}")
    # The final '+' is followed by the monitor's success prose, `ok`, and prompt.
    verdict = read_prompt(120)
    if not re.search(rb"(?:^|\r?\n)ok(?:\r?\n|$)", verdict, re.I):
        raise UpdateError("receiver did not report the exact ok verdict")


def expect_crc(response: bytes, crc: int, label: str) -> None:
    match = re.search(rb"The CRC32 is ([0-9A-F]{8})\.", response, re.I)
    if not match or int(match.group(1), 16) != crc:
        raise UpdateError(f"{label} CRC32 mismatch or missing readback")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="staged direct-boot bundle containing SHA256.json")
    parser.add_argument("--manifest-sha256", required=True,
                        help="reviewed SHA-256 of this bundle's SHA256.json")
    parser.add_argument("--expected-running-build", type=int, required=True,
                        help="build number reported by the monitor before any write")
    parser.add_argument("--execute", action="store_true",
                        help="transfer and overwrite kernel8.img; no backup and no reset")
    parser.add_argument("--port", default="COM30")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--evidence", type=Path, default=Path("pi3-self-update.jsonl"))
    args = parser.parse_args()

    image_path, image, manifest = load_bundle(args.bundle, args.manifest_sha256)
    image_sha = hashlib.sha256(image).hexdigest()
    image_crc = zlib.crc32(image) & 0xFFFFFFFF
    # Reuse the same RAM span for readback after the file is safely saved.
    # The file is a separate medium source, so loading it over the staging
    # bytes is a direct verification and permits images up to the full 2 MiB
    # gap without needing a second adjacent buffer.
    verify_addr = STAGE
    summary = {
        "bundle": str(args.bundle.resolve()),
        "manifest_sha256": args.manifest_sha256.lower(),
        "kernel": str(image_path.resolve()),
        "kernel_bytes": len(image),
        "kernel_sha256": image_sha,
        "kernel_crc32": f"{image_crc:08X}",
        "stage": f"0x{STAGE:08X}",
        "readback": f"0x{verify_addr:08X} (same stage span after save)",
        "expected_running_build": args.expected_running_build,
        "execute": args.execute,
        "reboot": False,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)

    def log(kind: str, raw: bytes = b"", **extra) -> None:
        record = {"kind": kind, "time": time.time(), "hex": raw.hex(),
                  "text": raw.decode("latin1", "replace"), **extra}
        with args.evidence.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
            stream.flush()

    log("candidate", **summary)
    if not args.execute:
        print(json.dumps(summary, indent=2))
        print("Dry run only. Add --execute after artifact review and gate signoff.")
        return 0

    try:
        import serial
    except ImportError as exc:
        raise UpdateError("pyserial is required for --execute") from exc

    port = serial.Serial(args.port, args.baud, timeout=.05, write_timeout=5,
                         dsrdtr=False, rtscts=False)
    port.dtr = False
    port.rts = False
    read_prompt = make_prompt_reader(port, log)
    try:
        log("open", port=args.port, baud=args.baud, dtr=False, rts=False)
        port.write(b"\r")
        port.flush()
        prompt = read_prompt(60)
        if not PROMPT.search(prompt):
            raise UpdateError("no fresh monitor prompt")

        version = command(port, read_prompt, log, "version")
        version_lower = version.lower()
        if (f"build {args.expected_running_build}".encode() not in version_lower or
                b"raspberry pi 3 model b" not in version_lower or b"target pi3" not in version_lower):
            raise UpdateError("running board/build identity did not match the required Pi3 build")

        transfer(port, read_prompt, log, image, image_crc)
        stage_crc = command(port, read_prompt, log, f"crc32 {STAGE:X} {len(image):X}")
        expect_crc(stage_crc, image_crc, "staged RAM")

        # This is the only destructive command. There is intentionally no
        # automatic backup or reset; failure stops here and leaves the board
        # at its prompt for an operator-directed recovery.
        saved = command(port, read_prompt, log,
                        f"save kernel8.img {STAGE:X} {len(image):X}", timeout=300)
        if not re.search(rb"(?:^|\r?\n)written\.(?:\r?\n|$)", saved, re.I):
            raise UpdateError("save did not report written.; do not reset")

        loaded = command(port, read_prompt, log,
                         f"load kernel8.img {verify_addr:X}", timeout=180)
        if f"Loaded {len(image)} bytes into memory".encode() not in loaded:
            raise UpdateError("readback load length did not match; do not reset")
        readback_crc = command(port, read_prompt, log,
                               f"crc32 {verify_addr:X} {len(image):X}")
        expect_crc(readback_crc, image_crc, "saved kernel8.img")
        log("PASS", **summary, ram_crc_verified=True,
            save_reported_written=True, file_readback_length=len(image),
            file_readback_crc32=f"{image_crc:08X}")
        print("PASS: RAM transfer, in-place kernel8.img save, and file readback CRC verified.")
        print("No reset was sent. Keep the board at the prompt until separately authorized.")
        return 0
    except Exception as exc:
        log("ABORT", error=repr(exc))
        raise
    finally:
        port.close()
        log("close")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UpdateError as exc:
        print(f"pi3 self-update aborted: {exc}", file=sys.stderr)
        raise SystemExit(2)
