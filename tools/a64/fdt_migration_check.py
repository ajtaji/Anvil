#!/usr/bin/env python3
"""Differential gate for moving a private device-tree reader onto
Anvil/Core/fdt.pbi (vault "The shared FDT reader - fdt.pbi and its
migration 2026-09-26").

For one migrated caller it builds ONE image holding both the new
procedure (the shipped source, now on fdt.pbi) and the OLD one (the same
file at the commit before the migration, `git show <rev>:<path>`, every
identifier renamed so the two coexist), runs both in tools/a64/a64_interp.py
on the same trees, and requires the same answer:

  * the valid trees the caller's own gate uses, and variants that exercise
    every rule the old walker enforced;
  * every single-byte corruption (three values per byte) of each base tree;
  * truncations.

A tree the OLD reader refused and the NEW accepts is a FAILURE. A tree the
old accepted and the new refuses is reported, with fdt.pbi's error code, and
allowed only when FdtCheck refuses it (the shared reader is stricter by
design - see the note - and the difference is listed, not hidden).

Callers: --caller boot_memory (Pi3BootRanges).
Run:  py -3 -B tools/a64/fdt_migration_check.py --compiler <PureMetalForge.exe> --caller boot_memory
      [--old-rev ef0e4cd | --old-file <path>] [--mutate]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pi5_desk as d                               # noqa: E402

ROOT = d.ROOT
LOAD, STACK = d.LOAD, d.STACK
TREE = 0x0100_0000


# ======================================================================
#  Trees
# ======================================================================
def word(x):
    return struct.pack(">I", x)


class Builder:
    def __init__(self):
        self.names = b""
        self.tree = b""

    def name(self, s):
        k = s.encode() + b"\0"
        i = self.names.find(k)
        if i < 0 or (i > 0 and self.names[i - 1] != 0):
            i = len(self.names)
            self.names += k
        return i

    def node(self, s):
        raw = s.encode() + b"\0"
        self.tree += word(1) + raw + b"\0" * ((-len(raw)) % 4)

    def prop(self, n, v):
        self.tree += word(3) + word(len(v)) + word(self.name(n)) + v + b"\0" * ((-len(v)) % 4)

    def end(self):
        self.tree += word(2)

    def blob(self, reserve=(), version=17, last=16, strings_first=False):
        tree = self.tree + word(9)
        res = b"".join(struct.pack(">QQ", *r) for r in reserve) + bytes(16)
        names = self.names + b"\0" * ((-len(self.names)) % 4)
        if strings_first:
            # A valid tree whose blocks are NOT in the flattened-format order:
            # strings, then structure.
            strings = 40 + len(res)
            off = strings + len(names)
            total = off + len(tree)
            hdr = struct.pack(">10I", 0xD00DFEED, total, off, strings, 40, version, last, 0,
                              len(self.names), len(tree))
            return hdr + res + names + tree
        off = 40 + len(res)
        strings = off + len(tree)
        total = strings + len(self.names)
        hdr = struct.pack(">10I", 0xD00DFEED, total, off, strings, 40, version, last, 0,
                          len(self.names), len(tree))
        return hdr + res + tree + self.names


def pi3_tree(reserve=(), fixed=None, rm_cells=(2, 2), root_cells=(2, 2), ranges=b"",
             extra_rm=False, grandchild=False, no_rm_cells=False, rm_name="reserved-memory",
             reg_len=None, version=17, last=16, second_root=False, strings_first=False):
    b = Builder()
    b.node("")
    if root_cells is not None:
        b.prop("#address-cells", word(root_cells[0]))
        b.prop("#size-cells", word(root_cells[1]))
    b.node("chosen")
    b.prop("bootargs", b"console=serial0\0")
    b.end()
    if fixed is not None:
        for k in range(2 if extra_rm else 1):
            b.node(rm_name)
            if not no_rm_cells:
                b.prop("#address-cells", word(rm_cells[0]))
                b.prop("#size-cells", word(rm_cells[1]))
            if ranges is not None:
                b.prop("ranges", ranges)
            b.node("test@0")
            a, s = fixed
            ac, sc = rm_cells
            v = (struct.pack(">Q", a) if ac == 2 else word(a & 0xFFFFFFFF)) + \
                (struct.pack(">Q", s) if sc == 2 else word(s & 0xFFFFFFFF))
            if reg_len is not None:
                v = v[:reg_len]
            b.prop("reg", v)
            if grandchild:
                b.node("deeper")
                b.end()
            b.end()
            b.end()
    b.end()
    if second_root:
        b.node("")
        b.end()
    return b.blob(reserve, version, last, strings_first)


def boot_memory_corpus():
    base = [
        ("empty", pi3_tree()),
        ("reserve ok", pi3_tree(reserve=((0x1000000, 4096),))),
        ("reserve in band", pi3_tree(reserve=((0x2000000, 1),))),
        ("reserve low band", pi3_tree(reserve=((0x80000, 1),))),
        ("fixed in band", pi3_tree(fixed=(0x2000000, 4096))),
        ("fixed high ok", pi3_tree(fixed=(0x30000000, 4096))),
        ("fixed edge", pi3_tree(fixed=(0x1FF0000, 1))),
    ]
    struct_variants = [
        ("rm 1/1 cells, root 1/1", pi3_tree(fixed=(0x30000000, 4096), rm_cells=(1, 1), root_cells=(1, 1))),
        ("rm cells differ from root", pi3_tree(fixed=(0x30000000, 4096), rm_cells=(1, 1))),
        ("root cells absent (2/1)", pi3_tree(fixed=(0x30000000, 4096), rm_cells=(2, 1), root_cells=None)),
        ("root cells 3", pi3_tree(root_cells=(3, 1))),
        ("root size cells 0", pi3_tree(root_cells=(2, 0))),
        ("rm cells absent", pi3_tree(fixed=(0x30000000, 4096), no_rm_cells=True)),
        ("rm ranges absent", pi3_tree(fixed=(0x30000000, 4096), ranges=None)),
        ("rm ranges not empty", pi3_tree(fixed=(0x30000000, 4096), ranges=word(0) * 6)),
        ("two reserved-memory", pi3_tree(fixed=(0x30000000, 4096), extra_rm=True)),
        ("grandchild", pi3_tree(fixed=(0x30000000, 4096), grandchild=True)),
        ("reg short", pi3_tree(fixed=(0x30000000, 4096), reg_len=12)),
        ("reg empty", pi3_tree(fixed=(0x30000000, 4096), reg_len=0)),
        ("unit-addressed name", pi3_tree(fixed=(0x2000000, 4096), rm_name="reserved-memory@0")),
        ("last_comp 17", pi3_tree(last=17)),
        ("last_comp 18 version 18", pi3_tree(version=18, last=18)),
        ("version 16", pi3_tree(version=16)),
        ("second root", pi3_tree(second_root=True)),
        ("strings before structure", pi3_tree(strings_first=True)),
        ("strings first, fixed ok", pi3_tree(fixed=(0x30000000, 4096), strings_first=True)),
        ("negative reserve", pi3_tree(reserve=((0x8000000000000000, 1),))),
        ("negative fixed", pi3_tree(fixed=(0x8000000000000010, 1))),
        ("wrapping fixed", pi3_tree(fixed=(0x7FFFFFFFFFFFFF00, 0x1000))),
    ]
    cases = [(n, t, len(t)) for n, t in base + struct_variants]
    # Header fields the old reader examined, and a wrong `total`.
    for n, t in base[:2] + base[5:6]:
        for field, values in ((4, (39, len(t) + 4, len(t) - 4)), (8, (41, 0x44, 0xFFFF)),
                              (12, (0, 40, 0xFFFFFF)), (16, (41, 44, 0x100)),
                              (20, (16,)), (24, (18,)), (32, (0, 1, 0xFFFF)), (36, (0, 8, 0x100000))):
            for v in values:
                m = bytearray(t)
                struct.pack_into(">I", m, field, v & 0xFFFFFFFF)
                cases.append(("%s hdr+%d=%X" % (n, field, v), bytes(m), len(m)))
        cases.append(("%s total-1" % n, t, len(t) - 1))
        cases.append(("%s total+4" % n, t + bytes(4), len(t) + 4))
    # Every byte, three ways, of three base trees.
    for n, t in (base[0], base[1], base[5]):
        for i in range(len(t)):
            for v in (0x00, 0xFF, t[i] ^ 0x01):
                if v == t[i]:
                    continue
                m = bytearray(t)
                m[i] = v
                cases.append(("%s byte%d=%02X" % (n, i, v), bytes(m), len(m)))
        for cut in range(40, len(t), 8):
            cases.append(("%s cut%d" % (n, cut), t[:cut], cut))
    return cases


# ======================================================================
#  Callers
# ======================================================================
CALLERS = {
    "boot_memory": dict(
        path="RaspberryPi3/Lib/boot_memory.pbi",
        target="pi3",
        old_prefix="p3bm", old_entry="Pi3BootRanges",
        call=lambda mc, name, addr, n: mc.call(name, addr, n),
        corpus=boot_memory_corpus,
        mutations=[
            ("root cells default 2 not 1 for size", 'rootSize = p3bmCells(root, "#size-cells", 1)',
             'rootSize = p3bmCells(root, "#size-cells", 2)'),
            ("last_comp policy dropped", "Or p3bmBe32(dtb + 24) > 17 :", ":"),
            ("block order policy dropped", "  If r >= s Or s + bytes > strings : ProcedureReturn 0 : EndIf\n",
             "  If 0 : ProcedureReturn 0 : EndIf\n"),
            ("reserve map not checked", "    If p3bmRange(FdtRegBase(), FdtRegLength()) = 0 : ProcedureReturn 0 : EndIf\n  Next\n  root",
             "  Next\n  root"),
            ("rm cells may be absent", 'If p3bmCells(rm, "#address-cells", 0) <> rootAddress',
             'If p3bmCells(rm, "#address-cells", rootAddress) <> rootAddress'),
            ("rm ranges may be absent", '  If FdtGetProp(rm, "ranges") = 0 Or FdtPropLen() <> 0 : ProcedureReturn 0 : EndIf\n',
             '  If FdtGetProp(rm, "ranges") <> 0 And FdtPropLen() <> 0 : ProcedureReturn 0 : EndIf\n'),
            ("second reserved-memory allowed", "      If rm <> 0 : ProcedureReturn 0 : EndIf\n", ""),
            ("grandchildren allowed", "    If FdtFirstChild(child) <> 0 : ProcedureReturn 0 : EndIf\n", ""),
            ("exact total not required", "  If p3bmBe32(dtb + 4) <> total Or", "  If 0 Or"),
        ],
    ),
}


def old_source(caller, rev, old_file):
    c = CALLERS[caller]
    if old_file:
        text = pathlib.Path(old_file).read_text(encoding="utf-8", errors="replace")
    else:
        r = subprocess.run(["git", "show", "%s:%s" % (rev, c["path"])], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise SystemExit("cannot read the old %s at %s: %s" % (c["path"], rev, r.stderr.strip()))
        text = r.stdout
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\b%s" % re.escape(c["old_prefix"]), "old_" + c["old_prefix"], text)
    text = re.sub(r"\b%s\b" % re.escape(c["old_entry"]), "Old" + c["old_entry"], text)
    return text


def build(caller, ov, work, cc, old_text):
    c = CALLERS[caller]
    work.mkdir(parents=True, exist_ok=True)
    new_text = d.source(c["path"], ov).replace("\r\n", "\n")
    (work / "new.pbi").write_text(new_text, encoding="utf-8")
    (work / "old.pbi").write_text(old_text, encoding="utf-8")
    drv = ("; fdt_migration_check driver - generated\n"
           'XIncludeFile "Anvil/Core/fdt.pbi"\n'
           'XIncludeFile "%s"\nXIncludeFile "%s"\n'
           "Global gate_never.i\nIf gate_never = 1\n  %s(0, 0) : Old%s(0, 0) : FdtError()\nEndIf\n"
           % ((work / "new.pbi").resolve().as_posix(), (work / "old.pbi").resolve().as_posix(),
              c["old_entry"], c["old_entry"]))
    src = work / "drv.pi4"
    src.write_text(drv, encoding="utf-8")
    img = work / "drv.img"
    r = subprocess.run([cc, "--compile", str(src), "-t", c["target"], "--entry-returns",
                        "--load-addr", hex(LOAD), "--stack-addr", hex(STACK), "-o", str(img)],
                       cwd=str(ROOT), env=dict(os.environ, PMF_ROOT=str(ROOT)),
                       capture_output=True, text=True)
    if r.returncode != 0 or "pmfc: OK" not in r.stdout or not img.exists():
        d.die("the driver would not build:\n" + r.stdout[-2500:] + r.stderr[-800:])
    procs = {}
    for line in pathlib.Path(str(img) + ".dbg").read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[0] == "1" and f[1].isdigit():
            procs[f[2].lower()] = LOAD + int(f[1])
    return img, procs


def no_device(addr, size, value):
    d.die("the reader touched device address $%X" % addr)


def gate(caller, ov, work, cc, old_text, verbose=False):
    c = CALLERS[caller]
    img, procs = build(caller, ov, work, cc, old_text)
    mc = d.Machine(img, procs, no_device)
    cases = c["corpus"]()
    stricter, bad = [], []
    agree = 0
    region = 0x20000
    for name, blob, n in cases:
        mc.poke(TREE, bytes(region))
        mc.poke(TREE, blob)
        new = mc.signed(c["call"](mc, c["old_entry"], TREE, n))
        err = mc.signed(mc.call("FdtError"))
        old = mc.signed(c["call"](mc, "Old" + c["old_entry"], TREE, n))
        if new == old:
            agree += 1
        elif old == 1 and new == 0 and err != 0:
            stricter.append((name, err))
        else:
            bad.append((name, old, new, err))
    if bad:
        d.die("%d of %d trees answered differently (old, new, FdtError); first: %s"
              % (len(bad), len(cases), bad[:3]))
    return len(cases), agree, stricter


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"))
    ap.add_argument("--caller", required=True, choices=sorted(CALLERS))
    ap.add_argument("--old-rev", default="ef0e4cd")
    ap.add_argument("--old-file", default=None)
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--only", default=None, help="run only mutants whose label contains this")
    a = ap.parse_args()
    cc = d.compiler(a.compiler)
    old = old_source(a.caller, a.old_rev, a.old_file)
    top = pathlib.Path(tempfile.mkdtemp(prefix="anvil-fdtmig-"))
    try:
        try:
            n, agree, stricter = gate(a.caller, {}, top / "gate", cc, old)
        except d.GateFail as e:
            print("fdt_migration_check %s: FAIL - %s" % (a.caller, e))
            return 1
        print("fdt_migration_check %s: PASS - %d trees; %d same answer; %d refused only by the "
              "shared reader (FdtCheck, stricter by design)" % (a.caller, n, agree, len(stricter)))
        codes = {}
        for name, err in stricter:
            codes.setdefault(err, []).append(name)
        for err, names in sorted(codes.items()):
            print("   FdtError %d: %d trees, e.g. %s" % (err, len(names), ", ".join(names[:3])))
        if a.mutate:
            muts = [(CALLERS[a.caller]["path"], why, o, nw) for why, o, nw in CALLERS[a.caller]["mutations"]
                    if a.only is None or a.only in why]

            def g(ov, w):
                gate(a.caller, ov, w, cc, old)
            left = d.run_mutations("fdt_migration_check " + a.caller, muts, g, top / "mut")
            return 1 if left else 0
        return 0
    finally:
        shutil.rmtree(top, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
