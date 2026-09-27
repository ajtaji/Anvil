#!/usr/bin/env python3
"""pi5_card_build_check.py - tools/pi5_card_build.py, gated on a fake card.

Builds one commit twice with the tool and requires the same two hashes both
times (and ANVIL5.IMG != ANVIL5.NOC). Then drives write_card against a fake
card FOLDER - config.txt from the vault's Boot staging, an armstub8-2712.bin
built from this tree's RaspberryPi5/Board/armstub8-2712.asm, an old
ANVIL5.IMG - with the disk identity supplied by the gate instead of
PowerShell. Rows (each names what the folder must hold afterwards):

  good card               ANVIL5.IMG/.NOC are the build, the old image is ANVIL5.OLD
  second write            ANVIL5.OLD is NOT overwritten (still the first old image)
  wrong serial            refused, folder byte-identical
  wrong label             refused, folder byte-identical
  config.txt lacks pciex4_reset=0   refused, folder byte-identical
  armstub corrupted       refused (a64_el3_pi5_check --image red), folder byte-identical

and the source transforms: a Pi5CachesOn block that is not exactly the three
lines (changed, missing, doubled) is refused; a #PMF_CHIP line that is not
the bridge is refused; an absent bridge is fine.

MUTANTS of the tool, each must turn a row red: the serial check removed;
ANVIL5.OLD overwritten every time; the block check removed; the config
check removed.

    py -3 tools/pi5_card_build_check.py --compiler PureMetalForge.exe [--commit REV]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import pi5_card_build as T                               # noqa: E402

STAGING = pathlib.Path(r"C:\Users\ajtaj\Desktop\CompilerEmbedded\Raspberry Pi 5\Boot staging\config.txt")
OLD = b"OLD ANVIL5 IMAGE " * 300


def snapshot(d: pathlib.Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir() if p.is_file()}


def make_card(d: pathlib.Path, stub: bytes, config: bytes, old_img=OLD, old_old=None):
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / "config.txt").write_bytes(config)
    (d / "armstub8-2712.bin").write_bytes(stub)
    if old_img is not None:
        (d / "ANVIL5.IMG").write_bytes(old_img)
    if old_old is not None:
        (d / "ANVIL5.OLD").write_bytes(old_old)


def rows(mod, res, stub, config, work, quiet=False):
    fails = []

    def check(ok, what):
        if not quiet:
            print("  %s  %s" % ("ok  " if ok else "FAIL", what))
        if not ok:
            fails.append(what)

    def attempt(card, serial, label):
        mod.drive_identity = lambda drive: (serial, label)
        try:
            mod.write_card(res, "Z:", say=lambda *a: None, root=card)
            return None
        except mod.Refused as e:
            return str(e)

    img = (res["dir"] / "ANVIL5.IMG").read_bytes()
    noc = (res["dir"] / "ANVIL5.NOC").read_bytes()
    card = work / "card"
    make_card(card, stub, config)
    err = attempt(card, T.CARD_SERIAL, T.CARD_LABEL)
    got = {n: (card / n).read_bytes() if (card / n).exists() else None for n in ("ANVIL5.IMG", "ANVIL5.NOC", "ANVIL5.OLD")}
    check(err is None and got["ANVIL5.IMG"] == img and got["ANVIL5.NOC"] == noc and got["ANVIL5.OLD"] == OLD,
          "good card: IMG and NOC written, the old image kept as ANVIL5.OLD (%s)" % err)
    (card / "ANVIL5.IMG").write_bytes(b"A NEWER IMAGE")
    err = attempt(card, T.CARD_SERIAL, T.CARD_LABEL)
    check(err is None and (card / "ANVIL5.OLD").read_bytes() == OLD and (card / "ANVIL5.IMG").read_bytes() == img,
          "second write: ANVIL5.OLD left as it was, ANVIL5.IMG replaced (%s)" % err)
    for why, serial, label, cfg, stubx in (
            ("wrong serial", "121220160205", T.CARD_LABEL, config, stub),
            ("wrong label", T.CARD_SERIAL, "BOOTFS", config, stub),
            ("config.txt lacks pciex4_reset=0", T.CARD_SERIAL, T.CARD_LABEL,
             config.replace(b"pciex4_reset=0", b"# pciex4_reset=0"), stub),
            ("armstub corrupted", T.CARD_SERIAL, T.CARD_LABEL, config,
             stub[:0x40] + bytes([stub[0x40] ^ 0xFF]) + stub[0x41:])):
        make_card(card, stubx, cfg)
        before = snapshot(card)
        err = attempt(card, serial, label)
        check(err is not None and snapshot(card) == before,
              "%s: refused, the folder unchanged (%s)" % (why, (err or "NOT REFUSED")[:90]))

    text = (ROOT / T.BOARD).read_text(encoding="utf-8").replace("\r\n", "\n")
    blk = T.CACHE_BLOCK
    for why, bad in (("changed", text.replace(blk, blk.replace("    Pi5CachesOn()\n", "    Pi5CachesOn()\n    CacheDmaPolicy()\n"))),
                     ("missing", text.replace(blk, "")),
                     ("doubled", text.replace(blk, blk + blk))):
        try:
            mod.drop_caches(bad)
            check(False, "a Pi5CachesOn block %s is refused (it was accepted)" % why)
        except mod.Refused:
            check(True, "a Pi5CachesOn block %s is refused" % why)
    nb, present = mod.drop_bridge(text)
    try:
        mod.drop_bridge(text.replace("\n", "\n#PMF_CHIP = 2712\n", 1))
        check(False, "a #PMF_CHIP line other than the bridge is refused (accepted)")
    except mod.Refused:
        check(True, "a #PMF_CHIP line other than the bridge is refused")
    again, p2 = mod.drop_bridge(nb)
    check(again == nb and not p2, "an absent bridge line is fine (bridge was %s at this commit)"
          % ("present" if present else "absent"))
    return fails


MUTANTS = [
    ("the serial check removed", "    if serial != CARD_SERIAL:", "    if False:"),
    ("ANVIL5.OLD overwritten every time", "    if cur is not None and old is None:", "    if cur is not None:"),
    ("the block check removed", "    if n != 1 or calls != 1:", "    if False:"),
    ("the config check removed", "    if missing:\n        raise Refused(\"config.txt on the card lacks",
     "    if False:\n        raise Refused(\"config.txt on the card lacks"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--commit", default="HEAD")
    a = ap.parse_args()
    if not a.compiler:
        raise SystemExit("pass --compiler or set PMF_COMPILER")
    config = STAGING.read_bytes()
    with tempfile.TemporaryDirectory(prefix="pi5card_check_") as td:
        work = pathlib.Path(td)
        r = subprocess.run([a.compiler, "--compile", "--armstub", "-t", "pi4",
                            "RaspberryPi5/Board/armstub8-2712.asm", "-o", str(work / "stub.bin")],
                           cwd=str(ROOT), env=dict(os.environ, PMF_ROOT=str(ROOT)), capture_output=True, text=True)
        if r.returncode != 0 or not (work / "stub.bin").is_file():
            raise SystemExit("the armstub would not build:\n" + r.stdout[-1000:])
        stub = (work / "stub.bin").read_bytes()
        try:
            r1 = T.build(a.commit, a.compiler, work / "b1")
            r2 = T.build(a.commit, a.compiler, work / "b2", say=lambda *x: None)
        except T.Refused as e:
            print("pi5_card_build_check: FAIL - the build refused: %s" % e)
            return 1
        fails = []
        ok = (r1["ANVIL5.IMG"], r1["ANVIL5.NOC"]) == (r2["ANVIL5.IMG"], r2["ANVIL5.NOC"])
        print("  %s  the hashes are reproducible: a second build of %s gives the same two"
              % ("ok  " if ok else "FAIL", r1["commit"][:7]))
        if not ok:
            fails.append("reproducible")
        ok = r1["ANVIL5.IMG"] != r1["ANVIL5.NOC"]
        print("  %s  ANVIL5.NOC differs from ANVIL5.IMG" % ("ok  " if ok else "FAIL"))
        if not ok:
            fails.append("noc differs")
        real_identity = T.drive_identity
        fails += rows(T, r1, stub, config, work)
        T.drive_identity = real_identity
        src = (HERE / "pi5_card_build.py").read_text(encoding="utf-8")
        survived = 0
        for why, old, new in MUTANTS:
            if src.count(old) != 1:
                print("  SURVIVED  %s (the edit matched %d times)" % (why, src.count(old)))
                survived += 1
                continue
            m = types.ModuleType("pi5_card_build_mut")
            m.__dict__["__file__"] = str(HERE / "pi5_card_build.py")
            exec(compile(src.replace(old, new), "pi5_card_build_mut", "exec"), m.__dict__)
            red = rows(m, r1, stub, config, work / "mut", quiet=True)
            print("  %s  %s%s" % ("KILLED  " if red else "SURVIVED", why, (" (%s)" % red[0][:70]) if red else ""))
            survived += 0 if red else 1
    if fails or survived:
        print("pi5_card_build_check: FAIL - %d row(s) red, %d mutant(s) survived" % (len(fails), survived))
        return 1
    print("pi5_card_build_check: PASS - reproducible images, the card identity, stub and config gates, "
          "the .OLD rule and the block check, all on a fake card. %d mutants killed." % len(MUTANTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
