#!/usr/bin/env python3
"""pi5_card_build.py - build the Pi 5 card images from one commit, and optionally write the card.

    py -3 tools/pi5_card_build.py <commit> --compiler PureMetalForge.exe [--out DIR] [--write H:]

  1. Exports <commit> of this repository (git archive) into a temporary tree;
     nothing in the working tree is read or written.
  2. In the export only, drops board.pi4's `#PMF_CHIP = 2711` line - the
     bridge the tracked compiler needs and a -t pi5 build refuses - until
     the signed compiler lands. Present: removed. Absent: nothing to do.
     Any OTHER `#PMF_CHIP =` line is a changed pattern and stops the run.
  3. Builds ANVIL5.IMG (caches on) and ANVIL5.NOC - the same export with
     Main's three-line Pi5CachesOn block removed. The block must be
     exactly those three lines, once, or the run stops: a fallback built
     from a guess is not a fallback.
  4. Prints both SHA-256s. Same commit and compiler -> same hashes.

  --write DRIVE  copies both images to the card, only after:
     * the disk behind DRIVE has serial 121220160204 and the volume is
       labelled ANVILBOOT (the bench card; anything else is refused);
     * armstub8-2712.bin on the card passes
       tools/a64/a64_el3_pi5_check.py --image;
     * config.txt on the card has kernel=ANVIL5.IMG,
       armstub=armstub8-2712.bin, enable_rp1_uart=1 and pciex4_reset=0.
     An existing ANVIL5.IMG is kept as ANVIL5.OLD only when there is no
     ANVIL5.OLD already (the known-good fallback is never overwritten).
     Both files are read back and their hashes compared.

Every refusal happens before the first byte is written.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
BOARD = "RaspberryPi4/Board/board.pi4"
BRIDGE = "#PMF_CHIP = 2711"
CACHE_BLOCK = "  CompilerIf #PMF_CHIP = 2712\n    Pi5CachesOn()\n  CompilerEndIf\n"
CARD_SERIAL = "121220160204"
CARD_LABEL = "ANVILBOOT"
STUB = "armstub8-2712.bin"
CONFIG_LINES = ("kernel=ANVIL5.IMG", "armstub=armstub8-2712.bin", "enable_rp1_uart=1", "pciex4_reset=0")


class Refused(Exception):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


# ----------------------------------------------------------------------
#  source transforms (pure text; the gate calls these directly)
# ----------------------------------------------------------------------
def drop_bridge(text: str) -> tuple[str, bool]:
    """text with the bridge line removed; (text, was_present). Any other
    #PMF_CHIP assignment is a changed pattern: refused."""
    lines = text.split("\n")
    hits = [i for i, l in enumerate(lines) if re.match(r"^\s*#PMF_CHIP\s*=", l.rstrip("\r"))]
    exact = [i for i in hits if lines[i].rstrip("\r") == BRIDGE]
    if len(hits) != len(exact) or len(exact) > 1:
        raise Refused("board.pi4's #PMF_CHIP lines are not the expected bridge (%s): %r"
                      % (BRIDGE, [lines[i] for i in hits]))
    if not exact:
        return text, False
    del lines[exact[0]]
    return "\n".join(lines), True


def drop_caches(text: str) -> str:
    """text with Main's Pi5CachesOn block removed, refused unless it is
    exactly CACHE_BLOCK, once."""
    t = text.replace("\r\n", "\n")
    n = t.count(CACHE_BLOCK)
    calls = len(re.findall(r"^\s*Pi5CachesOn\(\)\s*$", t, re.M))
    if n != 1 or calls != 1:
        raise Refused("the Pi5CachesOn block is not the expected three lines exactly once "
                      "(block found %d times; %d call lines) - ANVIL5.NOC not built" % (n, calls))
    return t.replace(CACHE_BLOCK, "")


def config_missing(text: str) -> list:
    have = set()
    for ln in text.splitlines():
        ln = ln.split("#", 1)[0].strip()
        if "=" in ln:
            k, v = ln.split("=", 1)
            have.add((k.strip() + "=" + v.strip()).lower())
    return [c for c in CONFIG_LINES if c.lower() not in have]


# ----------------------------------------------------------------------
#  export and build
# ----------------------------------------------------------------------
def export(commit: str, dest: pathlib.Path) -> str:
    full = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", commit + "^{commit}"],
                          capture_output=True, text=True)
    if full.returncode != 0:
        raise Refused("%s is not a commit in %s" % (commit, ROOT))
    full = full.stdout.strip()
    tar = subprocess.run(["git", "-C", str(ROOT), "-c", "core.autocrlf=false", "archive", "--format=tar", full],
                         capture_output=True)
    if tar.returncode != 0:
        raise Refused("git archive failed: %s" % tar.stderr.decode(errors="replace")[-300:])
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as tf:
        tf.extractall(dest)
    return full


def compile_board(cc: str, tree: pathlib.Path, text: str, name: str, out: pathlib.Path) -> bytes:
    src = tree / "RaspberryPi4" / "Board" / name
    src.write_text(text, encoding="utf-8", newline="\n")
    r = subprocess.run([cc, "--compile", str(src), "-t", "pi5", "-o", str(out)], cwd=str(tree),
                       env=dict(os.environ, PMF_ROOT=str(tree)), capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not out.is_file():
        raise Refused("%s would not build:\n%s%s" % (name, r.stdout[-1500:], r.stderr[-500:]))
    return out.read_bytes()


def build(commit: str, cc: str, outdir: pathlib.Path, say=print) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pi5card_") as td:
        tree = pathlib.Path(td) / "tree"
        tree.mkdir()
        full = export(commit, tree)
        text = (tree / BOARD).read_text(encoding="utf-8").replace("\r\n", "\n")
        text, bridged = drop_bridge(text)
        say("commit %s; the %s line was %s in the export" % (full, BRIDGE, "removed" if bridged else "absent"))
        noc_text = drop_caches(text)          # refused here, before anything is built
        img = compile_board(cc, tree, text, "board_card_img.pi4", outdir / "ANVIL5.IMG")
        noc = compile_board(cc, tree, noc_text, "board_card_noc.pi4", outdir / "ANVIL5.NOC")
    res = {"commit": full, "ANVIL5.IMG": sha(img), "ANVIL5.NOC": sha(noc),
           "sizes": (len(img), len(noc)), "dir": outdir}
    say("ANVIL5.IMG  %9d bytes  sha256 %s  (caches on)" % (len(img), res["ANVIL5.IMG"]))
    say("ANVIL5.NOC  %9d bytes  sha256 %s  (caches off)" % (len(noc), res["ANVIL5.NOC"]))
    return res


# ----------------------------------------------------------------------
#  the card
# ----------------------------------------------------------------------
def drive_identity(drive: str) -> tuple[str, str]:
    """(disk serial, volume label) of the volume at a Windows drive letter."""
    letter = drive.strip().rstrip(":\\/")
    if not re.fullmatch(r"[A-Za-z]", letter):
        raise Refused("--write takes a drive letter such as H:, not %r" % drive)
    ps = ("$v = Get-Volume -DriveLetter %s -ErrorAction Stop; "
          "$d = Get-Partition -DriveLetter %s -ErrorAction Stop | Get-Disk; "
          "Write-Output ('SERIAL=' + $d.SerialNumber); Write-Output ('LABEL=' + $v.FileSystemLabel)"
          % (letter, letter))
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, errors="replace")
    vals = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
    if r.returncode != 0 or "SERIAL" not in vals:
        raise Refused("could not read the disk behind %s: %s" % (drive, r.stderr.strip()[-300:]))
    return vals["SERIAL"].strip(), vals.get("LABEL", "").strip()


def drive_root(drive: str) -> pathlib.Path:
    return pathlib.Path(drive.strip().rstrip("\\/") + "\\")


def find_file(root: pathlib.Path, name: str):
    for p in root.iterdir():
        if p.is_file() and p.name.lower() == name.lower():
            return p
    return None


def stub_check(stub: pathlib.Path) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(ROOT / "tools/a64/a64_el3_pi5_check.py"), "--image", str(stub)],
                       cwd=str(ROOT), capture_output=True, text=True, errors="replace")
    return r.returncode == 0, (r.stdout + r.stderr).strip()[-400:]


def write_card(res: dict, drive: str, say=print, root: pathlib.Path | None = None) -> None:
    serial, label = drive_identity(drive)
    if serial != CARD_SERIAL:
        raise Refused("the disk behind %s has serial %r, not the bench card's %s - nothing written"
                      % (drive, serial, CARD_SERIAL))
    if label.upper() != CARD_LABEL:
        raise Refused("the volume at %s is labelled %r, not %s - nothing written" % (drive, label, CARD_LABEL))
    root = root or drive_root(drive)
    stub = find_file(root, STUB)
    if stub is None:
        raise Refused("%s is not on the card - nothing written" % STUB)
    ok, why = stub_check(stub)
    if not ok:
        raise Refused("%s on the card fails a64_el3_pi5_check --image - nothing written:\n%s" % (STUB, why))
    cfg = find_file(root, "config.txt")
    if cfg is None:
        raise Refused("config.txt is not on the card - nothing written")
    missing = config_missing(cfg.read_text(encoding="utf-8", errors="replace"))
    if missing:
        raise Refused("config.txt on the card lacks %s - nothing written" % ", ".join(missing))
    say("card %s: serial %s, label %s, %s passes the EL3 gate, config.txt has the four lines"
        % (drive, serial, label, STUB))
    cur = find_file(root, "ANVIL5.IMG")
    old = find_file(root, "ANVIL5.OLD")
    if cur is not None and old is None:
        shutil.copyfile(cur, root / "ANVIL5.OLD")
        if sha((root / "ANVIL5.OLD").read_bytes()) != sha(cur.read_bytes()):
            raise Refused("ANVIL5.OLD did not read back equal to the ANVIL5.IMG it keeps - stopped "
                          "before ANVIL5.IMG was replaced")
        say("kept the previous ANVIL5.IMG as ANVIL5.OLD")
    elif cur is not None:
        say("ANVIL5.OLD already exists and is left as it is; the current ANVIL5.IMG is replaced")
    for name in ("ANVIL5.IMG", "ANVIL5.NOC"):
        shutil.copyfile(res["dir"] / name, root / name)
        got = sha((root / name).read_bytes())
        if got != res[name]:
            raise Refused("%s read back as %s, not %s - THE CARD HOLDS A BAD %s" % (name, got, res[name], name))
        say("wrote %s, read back %s" % (name, got))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("commit")
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "_work" / "pi5_card")
    ap.add_argument("--write", metavar="DRIVE")
    a = ap.parse_args(argv)
    if not a.compiler:
        ap.error("pass --compiler or set PMF_COMPILER")
    try:
        res = build(a.commit, a.compiler, a.out)
        if a.write:
            write_card(res, a.write)
    except Refused as e:
        print("!! " + str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
