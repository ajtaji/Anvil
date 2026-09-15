#!/usr/bin/env python3
"""Build the payload ABI board proof's three containers, and check them.

    python tools/pi4_svcprobe_negcontrols.py --compiler <PureMetalForge.exe> \
           [--out _work/svcprobe]

It builds, checks and hashes the containers tools/pi4_svcprobe_proof.py
sends to a board. Nothing here needs a board.

  svcprobe.img.pmf  the reference payload, built --entry-returns
                    --wants-services.

  svcmaj.img.pmf    the reference payload with #SVCP_NEED_MAJOR bumped to 2,
                    so a 1.x monitor is OLDER than it needs. On the board it
                    must refuse without calling a single slot, leave its
                    sentence at $01401000 naming both versions, and come back
                    with a non-zero failure count in x0.

  svcboth.pmf       the reference payload's own container with bit 1 set
                    BESIDE bit 2, which the compiler will not emit and must
                    never emit. On the board the ninth guard must refuse it
                    before placement, naming both flags, having loaded nothing.

WHY BIT 1 IS SET BY HAND AND NOT BY A FLAG. There is no compiler option that
produces this container and there should not be: it asks for two different
things in one register, and a compiler that could emit it on request could
emit it by accident. The guard exists for a file that arrived from somewhere
else, or was damaged, so the honest way to test it is to damage one.

THE FLAGS WORD IS AT OFFSET 56 in both header versions, and the digest in
the header covers the IMAGE and not the header - which is exactly why the
ninth guard runs before the hash rather than after it. If a future container
format covers its own header, this script has to change and the refusal it
tests moves; the checks below fail loudly in that case rather than writing a
file that no longer means anything.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import struct
import subprocess
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4SvcProbe.pi4"

PMF_FLAG_RETURNS = 1
PMF_FLAG_WANTS_DTB = 2
PMF_FLAG_WANTS_SERVICES = 4
FLAGS_OFF = 56
SHA_OFF, SHA_LEN = 64, 32
# pmfboot.pbi's field table: version -> header length.
HDR_LEN = {1: 96, 2: 128}


def report(path: pathlib.Path) -> None:
    b = path.read_bytes()
    print("    %-20s %9d bytes  crc32 %08X  sha256 %s"
          % (path.name, len(b), zlib.crc32(b) & 0xFFFFFFFF, hashlib.sha256(b).hexdigest()))


def build(compiler: str, src: pathlib.Path, out: pathlib.Path, extra: list[str]) -> pathlib.Path:
    cmd = [compiler, "--compile", str(src), "-t", "pi4", "-o", str(out)] + extra
    r = subprocess.run(cmd, cwd=ROOT, text=True, env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    pmf = pathlib.Path(str(out) + ".pmf")
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not pmf.exists():
        sys.exit("The build of %s failed, so no container was written. The "
                 "compiler said:\n%s" % (src.name, r.stdout[-3000:]))
    return pmf


def header(path: pathlib.Path) -> dict:
    b = path.read_bytes()
    if b[:8] != b"PMFBOOT\x00":
        sys.exit("%s does not start with the container magic." % path)
    version, hdrlen = struct.unpack_from("<II", b, 8)
    if HDR_LEN.get(version) != hdrlen:
        sys.exit("%s declares version %d with a %d-byte header, which is not a "
                 "container pmfboot.pbi reads." % (path, version, hdrlen))
    flags, = struct.unpack_from("<I", b, FLAGS_OFF)
    imglen, = struct.unpack_from("<Q", b, 32)
    image = b[hdrlen:]
    return {"bytes": b, "version": version, "hdrlen": hdrlen, "flags": flags,
            "imglen": imglen, "image": image, "sha": b[SHA_OFF:SHA_OFF + SHA_LEN]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge compiler (default: $PMF_COMPILER)")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "_work" / "svcprobe",
                    help="where the containers are written (default _work/svcprobe)")
    args = ap.parse_args()
    if not args.compiler:
        sys.exit("No compiler was named. Pass --compiler with the path to "
                 "PureMetalForge.exe, or set PMF_COMPILER.")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    flags_args = ["--load-addr", "0x400000", "--stack-addr", "0x3000000",
                  "--entry-returns", "--wants-services"]
    checks = 0

    def check(cond: bool, sentence: str) -> None:
        nonlocal checks
        if not cond:
            sys.exit(sentence)
        checks += 1

    # ---- 0. the reference payload -----------------------------------
    ref_pmf = build(args.compiler, PROBE, out / "svcprobe.img", flags_args)
    ref = header(ref_pmf)
    check(bool(ref["flags"] & PMF_FLAG_WANTS_SERVICES),
          "The reference container does not have bit 2 set, so setting bit 1 "
          "beside it would not be the pair the ninth guard refuses. flags = %d" % ref["flags"])
    check(not ref["flags"] & PMF_FLAG_WANTS_DTB,
          "The reference container ALREADY has bit 1 set. The compiler must never "
          "emit that pair; this is a compiler defect and not a negative control. "
          "flags = %d" % ref["flags"])
    check(hashlib.sha256(ref["image"]).digest() == ref["sha"] and len(ref["image"]) == ref["imglen"],
          "The reference container's digest does not cover exactly its image, so "
          "the offsets this script edits are not the ones it thinks.")

    # ---- 1. the payload that needs a major this monitor does not have --
    src = PROBE.read_text(encoding="utf-8")
    find = "#SVCP_NEED_MAJOR = 1"
    check(src.count(find) == 1,
          "pi4SvcProbe.pi4 no longer declares %s exactly once, so the "
          "major-mismatch control cannot be built." % find)
    mutant = out / "svcprobe_major.pi4"
    mutant.write_text(src.replace(find, "#SVCP_NEED_MAJOR = 2", 1), encoding="utf-8")
    maj_pmf = build(args.compiler, mutant, out / "svcmaj.img", flags_args)
    maj = header(maj_pmf)
    check(maj["flags"] == ref["flags"],
          "The major-mismatch container's flags differ from the reference's; "
          "it would be testing two things at once.")
    check(maj["image"] != ref["image"],
          "Bumping #SVCP_NEED_MAJOR did not change the image, so the control "
          "is the reference payload under another name.")

    # ---- 2. the container that asks for both ------------------------
    b = bytearray(ref["bytes"])
    struct.pack_into("<I", b, FLAGS_OFF, ref["flags"] | PMF_FLAG_WANTS_DTB)
    both = out / "svcboth.pmf"
    both.write_bytes(bytes(b))
    bh = header(both)
    check(bh["flags"] == ref["flags"] | PMF_FLAG_WANTS_DTB,
          "The both-flags container does not carry bits 1 and 2 after writing.")
    check(bh["image"] == ref["image"] and bh["sha"] == ref["sha"],
          "Setting bit 1 changed something other than the flags word.")
    diff = [i for i in range(len(b)) if b[i] != ref["bytes"][i]]
    check(diff and all(FLAGS_OFF <= i < FLAGS_OFF + 4 for i in diff),
          "The both-flags container differs from the reference outside the "
          "flags word, at offsets %r." % diff[:8])

    print("  the reference payload:")
    report(ref_pmf)
    print("  the negative controls:")
    report(maj_pmf)
    report(both)
    print()
    print("  container version %d, flags: reference %d (returns|wants-services), "
          "both-flags %d" % (ref["version"], ref["flags"], bh["flags"]))
    print("  PASS: %d offline checks. The board proof is tools/pi4_svcprobe_proof.py." % checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
