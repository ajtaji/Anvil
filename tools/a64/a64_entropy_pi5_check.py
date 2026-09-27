#!/usr/bin/env python3
"""Desk gate: RaspberryPi4/Lib/entropy.pi4 on the Pi 5 (-t pi5) - the
BCM2712's RNG200 at $107D208000.

SILICON OWED. The Pi 4 gate, tools/a64/a64_entropy_check.py, is the model
and the transcript: this runs ITS check_citations, check_behaviour and check_stuck (every
register access in order, the warm-up, the FIFO guard, the health bits,
the stuck-value detector) against a -t pi5 build, with the model's window
moved to the Pi 5 address, and ITS chip-agnostic mutants against that
build too. What this gate adds:

  * THE PI 5 ADDRESS AND THE PART, FROM THE PINNED DTBs. In each of
    bcm2712-rpi-5-b, bcm2712d0-rpi-5-b and bcm2712-d-rpi-5-b.dtb (vault
    "Raspberry Pi 5/Boot staging"): exactly one node whose compatible is
    "brcm,bcm2711-rng200" - the Pi 4's own string, so the driver path
    entropy.pi4 cites is the one Linux takes on this part - status okay,
    its reg through the /soc ranges equal to entropy.pi4's 2712
    #ENTROPY_BASE, and its length covering the highest register used.
  * Two 2712 mutants: the base off by a page, and the old refusal put
    back in EntropyBegin.

A mutant that does not build is an ERROR, not a kill.

  $env:PMF_ALLOW_UNTRACKED_COMPILER = 1
  py -3 -B tools/a64/a64_entropy_pi5_check.py --compiler <PureMetalForge.exe> [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "RaspberryPi5" / "Boot"))
import a64_entropy_check as ec              # noqa: E402
from pmf_compiler import resolve_compiler   # noqa: E402

DEFAULT_SOURCES = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5")
TREES = ("bcm2712-rpi-5-b.dtb", "bcm2712d0-rpi-5-b.dtb", "bcm2712-d-rpi-5-b.dtb")
PI5_BASE_PINNED = 0x10_7D20_8000
BASE_RE = re.compile(r"CompilerIf #PMF_CHIP = 2712\s*\n\s*#ENTROPY_BASE\s*=\s*\$([0-9A-Fa-f]+)")


def pi5_base(text):
    m = BASE_RE.search(text)
    if not m:
        raise SystemExit("entropy.pi4 has no #PMF_CHIP = 2712 #ENTROPY_BASE")
    return int(m.group(1), 16)


def check_dtb(src, base, K):
    from dtb_contract import parse, strings, mapped_reg
    highest = max(K[n] for n in K if n.startswith(("RNG_", "RBG_")) and n.endswith("_OFF"))
    for name in TREES:
        n = parse((src / "Boot staging" / name).read_bytes())
        hits = [p for p, v in n.items()
                if "compatible" in v and "brcm,bcm2711-rng200" in strings(v["compatible"])]
        ec.check(len(hits) == 1, "%s: %d brcm,bcm2711-rng200 nodes, want 1" % (name, len(hits)))
        if len(hits) != 1:
            continue
        node = n[hits[0]]
        ec.check(strings(node.get("status", b"okay\0")) == ["okay"], "%s: the RNG200 is not okay" % name)
        ec.check(mapped_reg(n, hits[0]) == base,
                 "%s: %s is CPU $%X, entropy.pi4's 2712 base is $%X" % (name, hits[0], mapped_reg(n, hits[0]), base))
        size = int.from_bytes(node["reg"][-4:], "big")
        ec.check(highest + 4 == size, "%s: reg length $%X, highest offset used $%X + 4" % (name, size, highest))
    ec.check(base == PI5_BASE_PINNED, "the 2712 base $%X is not the pinned $%X" % (base, PI5_BASE_PINNED))


def build(lib, img):
    harness = img.parent / "entropyharness5.pi4"
    harness.write_text(ec.HARNESS.replace("__LIB__", lib.resolve().as_posix()), encoding="utf-8")
    r = subprocess.run([ec.COMPILER, "--compile", str(harness), "-t", "pi5",
                        "--load-addr", hex(ec.LOAD), "--stack-addr", hex(ec.STACK),
                        "--entry-returns", "-o", str(img)],
                       cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout:
        raise RuntimeError("BUILD: the -t pi5 entropy harness did not build:\n" + r.stdout[-2000:])


def gate(lib, src, work):
    """Returns (checks, failures). A build failure raises RuntimeError."""
    ec.FAILURES, ec.CHECKS = [], 0
    text = lib.read_text(encoding="utf-8")
    K = ec.parse_pi4_constants(lib)
    base = pi5_base(text)
    K["ENTROPY_BASE"] = base
    ec.RNG_LO, ec.RNG_HI = base, base + 0x27
    check_dtb(src, base, K)
    ec.check_citations(K, lib)             # the register map and composed words
    img = work / "entropy5.img"
    build(lib, img)
    try:
        ec.check_behaviour(img, K)
        ec.check_stuck(img, K)
    except SystemExit as e:                # a FATAL from the model
        ec.FAILURES.append("model: %s" % e)
    except Exception as e:                 # noqa: BLE001 - a mutant the model cannot even represent
        ec.FAILURES.append("model raised %r" % e)
    return ec.CHECKS, list(ec.FAILURES)


PI5_MUTATIONS = [
    ("the 2712 base off by a page", "  #ENTROPY_BASE = $107D208000", "  #ENTROPY_BASE = $107D209000"),
    ("the old 2712 refusal put back in EntropyBegin",
     "Procedure.i EntropyBegin()\n",
     "Procedure.i EntropyBegin()\n  CompilerIf #PMF_CHIP = 2712\n  ProcedureReturn #ENTROPY_ERR_OFF\n  CompilerEndIf\n"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    if not a.compiler:
        ap.error("pass --compiler or set PMF_COMPILER")
    ec.COMPILER = str(resolve_compiler(a.compiler))
    src = pathlib.Path(a.sources)
    with tempfile.TemporaryDirectory(prefix="entropy5-") as td:
        work = pathlib.Path(td)
        ec.WORK = work
        n, fails = gate(ec.LIB, src, work)
        print("a64_entropy_pi5_check: %d checks, %d failed" % (n, len(fails)))
        for f in fails:
            print("  FAIL: " + f)
        if fails:
            return 1
        if a.mutate:
            original = ec.LIB.read_text(encoding="utf-8").replace("\r\n", "\n")
            muts = [(nm, o, w) for nm, o, w in ec.MUTATIONS if "$FE10" not in o] + PI5_MUTATIONS
            bad = 0
            for i, (name, old, new) in enumerate(muts):
                if original.count(old) != 1:
                    print("  %2d  ERROR     %s (anchor matched %d times)" % (i, name, original.count(old)))
                    bad += 1
                    continue
                copy = work / ("m%02d_entropy.pi4" % i)
                copy.write_text(original.replace(old, new), encoding="utf-8")
                try:
                    _, f = gate(copy, src, work)
                except RuntimeError:
                    print("  %2d  ERROR     %s (did not build)" % (i, name))
                    bad += 1
                    continue
                if f:
                    print("  %2d  KILLED    %s (%s)" % (i, name, f[0][:100]))
                else:
                    print("  %2d  SURVIVED  %s" % (i, name))
                    bad += 1
            print("a64_entropy_pi5_check mutations: %d killed, %d not" % (len(muts) - bad, bad))
            if bad:
                return 1
    print("Desk only: nothing touched silicon, and nothing here says anything about")
    print("the quality of the hardware's output - there is no oracle for that.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
