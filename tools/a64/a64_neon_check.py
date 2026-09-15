#!/usr/bin/env python3
"""Executable gate for RaspberryPi4/Lib/neon.pi4 - the NeonArcade engine.

It builds RaspberryPi4/Examples/Diagnostics/pi4NeonGate.pi4, runs it on the
A64 interpreter against the V3D model in a64_v3d_rcl_check.py, and decodes
the bin list, vertex array, uniforms, shader state records and glyph
rectangles the engine produced.

WHAT THIS GATE IS FOR, GIVEN A BOARD RUN CAN COUNT PIXELS
  pi4NeonBox.pi4 and pi4NeonText.pi4 count every pixel on silicon.  What a
  board run cannot say is caught here:
  * A PACKET THAT IS WRONG BUT HARMLESS for the colours and geometry that
    were drawn - a misordered state packet, a field one bit too narrow, a
    blend factor that happens to give the same answer.
  * THE REFUSALS, which the working board run never takes.
  * THE ARITHMETIC AT ITS EDGES.
  * WHETHER THE GATE ITSELF WOULD NOTICE: --mutate breaks a temporary copy
    of neon.pi4 on purpose and requires each break to go red.

WHERE EACH ANSWER COMES FROM
  THE PACKET LAYOUTS AND BLEND ENUMS are the pinned v3d_packet.xml tables in
  a64_v3d_rcl_check.py, IMPORTED and not copied, so two copies of a V3D
  model cannot drift.
  THE FLOATS are checked against the host's own IEEE 754 (struct.pack of an
  honest division), which shares nothing with neon.pi4's long division.
  THE GLYPHS are checked against a second, independent read of display.pi4's
  font blob, one question per pixel.

WHAT IT CANNOT DO
  1. It cannot rasterise; there is no V3D in the interpreter.
  2. It cannot say the packet SUBSET is right.
  3. It cannot say the XML describes this silicon.
  4. It runs a 640 x 480 surface at a low framebuffer address, so it does
     not exercise the megabyte page table; pi4NeonBox.pi4 does, on a board.

  python tools/a64/a64_neon_check.py --compiler <PureMetalForge.exe>
  python tools/a64/a64_neon_check.py --compiler <PureMetalForge.exe> --mutate
"""

import argparse
import contextlib
import importlib.util
import io
import os
import pathlib
import re
import struct
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
NEON = ROOT / "RaspberryPi4" / "Lib" / "neon.pi4"
DISPLAY = ROOT / "RaspberryPi4" / "Lib" / "display.pi4"
PROBE = ROOT / "RaspberryPi4" / "Examples" / "Diagnostics" / "pi4NeonGate.pi4"
NEON_INCLUDE = 'XIncludeFile "RaspberryPi4/Lib/neon.pi4"'


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(HERE))
R = _load("a64_v3d_rcl_check", HERE / "a64_v3d_rcl_check.py")


def _constant(path: pathlib.Path, name: str) -> int:
    m = re.search(r"^#%s\s*=\s*([^\s;]+)" % re.escape(name), R.text(path), re.M)
    if not m:
        raise SystemExit("a64_neon_check: %s has no #%s." % (path.name, name))
    tok = m.group(1)
    return int(tok[1:], 16) if tok.startswith("$") else int(tok, 10)


def probe_constant(name: str) -> int:
    return _constant(PROBE, name)


def neon_constant(name: str) -> int:
    return _constant(NEON, name)


def font_blob() -> dict:
    """display.pi4's 8x16 cell font, read straight out of its DataSection.

    THE SECOND WITNESS FOR EVERY GLYPH.  neon.pi4 never sees this parse
    and this parse never sees neon.pi4.
    """
    src = R.text(DISPLAY)
    i = src.index("dsp_font8x16:")
    rows = []
    for line in src[i:].split("\n")[1:]:
        m = re.match(r"\s*Data\.a\s+(.*?)(?:;|$)", line)
        if not m:
            if rows:
                break
            continue
        vals = [v.strip() for v in m.group(1).split(",") if v.strip()]
        rows.append([int(v[1:], 16) for v in vals])
    if len(rows) != 95 or any(len(r) != 16 for r in rows):
        raise SystemExit(
            "a64_neon_check: display.pi4's font blob parsed as %d glyphs of "
            "%s bytes.  It has to be 95 of 16 - ASCII 32..126, an 8x16 cell "
            "- and if it is not, this gate's glyph oracle is wrong rather "
            "than merely failing."
            % (len(rows), sorted(set(len(r) for r in rows))))
    return {32 + n: r for n, r in enumerate(rows)}


def build(compiler: str, probe: pathlib.Path, work: pathlib.Path):
    img = R.compile_probe(compiler, probe, work / "neongate.img")
    syms = {}
    symfile = img.with_suffix(".img.sym")
    if symfile.exists():
        for line in symfile.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                syms[k.strip()] = int(v.strip(), 0)
    if not syms:
        raise SystemExit(
            "a64_neon_check: there is no symbol file beside %s.  Without it "
            "this gate cannot find the probe's globals, and it will not fall "
            "back to the probe's own printed verdict." % img)
    return img, syms


def gvar(cpu, syms, name: str) -> int:
    for cand in ("global_" + name.lower(), name.lower(), "_" + name.lower()):
        if cand in syms:
            a = syms[cand]
            v = sum(cpu.memory.get(a + i, 0) << (8 * i) for i in range(8))
            return v - (1 << 64) if v >= (1 << 63) else v
    raise SystemExit("a64_neon_check: the image has no symbol for %s." % name)


def grab(cpu, lo: int, n: int) -> bytes:
    return bytes(cpu.memory.get(lo + i, 0) for i in range(n))


def u32(cpu, a: int) -> int:
    return sum(cpu.memory.get(a + i, 0) << (8 * i) for i in range(4))


def s32(cpu, a: int) -> int:
    v = u32(cpu, a)
    return v - (1 << 32) if v >= (1 << 31) else v


ROWS = [0]


def row(name, want, got, fails):
    ROWS[0] += 1
    ok = (want == got)
    print("  %-46s %-18s %s" % (name, got, "OK" if ok else "WANTED %s" % (want,)))
    if not ok:
        fails.append("%s: got %s, wanted %s" % (name, got, want))
    return ok


def check(fails: list, counts: dict, compiler: str, work: pathlib.Path,
          probe: pathlib.Path = PROBE) -> None:
    img, syms = build(compiler, probe, work)
    m = R.Model()
    cpu, uart = R.run(img, m)

    print(uart.rstrip())
    print()

    rc = gvar(cpu, syms, "ngRc")
    row("the probe's own return code", 0, rc, fails)
    if rc != 0:
        print("  the probe did not finish - nothing below means anything")
        return

    W = probe_constant("NG_W")
    H = probe_constant("NG_H")
    cx, cy = W // 2, H // 2

    bcl = gvar(cpu, syms, "ngBclAddr")
    bcl_len = gvar(cpu, syms, "ngBclLen")
    verts = gvar(cpu, syms, "ngVerts")
    nverts = gvar(cpu, syms, "ngVertCount")
    ndraws = gvar(cpu, syms, "ngDraws")
    tfirst = gvar(cpu, syms, "ngTextFirst")
    tcount = gvar(cpu, syms, "ngTextCount")
    nglyphs = gvar(cpu, syms, "ngGlyphs")
    nruns = gvar(cpu, syms, "ngRuns")

    # 1. THE BIN LIST, decoded with the pinned layouts
    print("1  the bin control list")
    by_code = R.parse_packets()
    data = grab(cpu, bcl, bcl_len)
    walk = R.decode_list(by_code, data)
    names = [n for (n, _f, _o) in walk]
    print("     %d bytes, %d packets" % (bcl_len, len(walk)))
    print("     %s" % " ".join(names))

    consumed = 0
    for (_n, _f, off) in walk:
        consumed = max(consumed, off)
    row("the walk reaches the last byte", True, consumed <= bcl_len, fails)

    def one(pkt_name):
        got = [f for (n, f, _o) in walk if n == pkt_name]
        if len(got) != 1:
            fails.append("%s appears %d times, wanted once" % (pkt_name, len(got)))
            return None
        return got[0]

    # 2. THE BLEND, every value from the pinned XML enums by NAME
    print()
    print("2  the blend, against v3d_packet.xml's enumerations")
    src_alpha = R.enum_value("Blend Factor", "SRC_ALPHA")
    inv_src = R.enum_value("Blend Factor", "INV_SRC_ALPHA")
    add = R.enum_value("Blend Mode", "ADD")
    row("Blend Factor SRC_ALPHA, from the XML", 6, src_alpha, fails)
    row("Blend Factor INV_SRC_ALPHA, from the XML", 7, inv_src, fails)
    row("Blend Mode ADD, from the XML", 0, add, fails)

    be = one("Blend Enables")
    if be is not None:
        row("BLEND_ENABLES mask", 1, be["Mask"], fails)
    bc = one("Blend Cfg")
    if bc is not None:
        row("BLEND_CFG colour src factor", src_alpha,
            bc["Color blend src factor"], fails)
        row("BLEND_CFG colour dst factor", inv_src,
            bc["Color blend dst factor"], fails)
        row("BLEND_CFG colour mode", add, bc["Color blend mode"], fails)
        row("BLEND_CFG alpha src factor", src_alpha,
            bc["Alpha blend src factor"], fails)
        row("BLEND_CFG alpha dst factor", inv_src,
            bc["Alpha blend dst factor"], fails)
        row("BLEND_CFG alpha mode", add, bc["Alpha blend mode"], fails)
        row("BLEND_CFG render target mask covers RT0", True,
            bool(bc["Render Target Mask"] & 1), fails)
    cfg = one("Cfg Bits")
    if cfg is not None:
        row("CFG_BITS blend enable", True, bool(cfg["Blend enable"]), fails)
        # No depth buffer exists, so nothing may be testing against one.
        row("CFG_BITS Z updates enable", False,
            bool(cfg["Z updates enable"]), fails)
        row("CFG_BITS forward facing enabled", True,
            bool(cfg["Enable Forward Facing Primitive"]), fails)
        row("CFG_BITS reverse facing enabled", True,
            bool(cfg["Enable Reverse Facing Primitive"]), fails)
    cwm = one("Color Write Masks")
    if cwm is not None:
        # Mesa's translate_colormask ends `return (~colormask) & 0xf`
        # (mesa-24.3.4 src/gallium/drivers/v3d/v3dx_emit.c:82-91), so a SET
        # bit MASKS OFF a channel and "write everything" is zero.
        row("COLOR_WRITE_MASKS - zero writes every channel", 0,
            cwm["Mask"], fails)

    # 3. THE DRAWS
    print()
    print("3  the draw calls")
    tris = R.enum_value("Primitive", "TRIANGLES")
    shader_states = [f for (n, f, _o) in walk if n == "GL Shader State"]
    prims = [f for (n, f, _o) in walk if n == "Vertex Array Prims"]
    row("GL_SHADER_STATE packets", ndraws, len(shader_states), fails)
    row("VERTEX_ARRAY_PRIMS packets", ndraws, len(prims), fails)
    row("draw calls the engine counted", 4, ndraws, fails)
    if prims:
        row("every draw is GL_TRIANGLES", True,
            all(p["mode"] == tris for p in prims), fails)
        # The slices must tile the vertex array exactly, in order.
        cursor = 0
        contiguous = True
        for p in prims:
            if p["Index of First Vertex"] != cursor:
                contiguous = False
            cursor += p["Length"]
        row("the draw slices tile the vertex array", True, contiguous, fails)
        row("the slices account for every vertex", nverts, cursor, fails)
    attrs = neon_constant("NEON_ATTRS")
    if shader_states:
        row("every record declares %d attribute arrays" % attrs, True,
            all(s["number of attribute arrays"] == attrs
                for s in shader_states), fails)

    # THE SCISSOR: full surface, the clip, full surface again - one packet
    # per CHANGE, not per draw.
    clips = [f for (n, f, _o) in walk if n == "clip_window"]
    row("CLIP_WINDOW packets - one per CHANGE, not per draw", 3,
        len(clips), fails)
    if len(clips) == 3:
        def box(c):
            return (c["Clip Window Left Pixel Coordinate"],
                    c["Clip Window Bottom Pixel Coordinate"],
                    c["Clip Window Width in pixels"],
                    c["Clip Window Height in pixels"])
        row("clip 0 is the whole surface", (0, 0, W, H), box(clips[0]), fails)
        row("clip 1 is what Neon_ScissorSet asked for",
            (probe_constant("NG_CLIPX"), probe_constant("NG_CLIPY"),
             probe_constant("NG_CLIPW"), probe_constant("NG_CLIPH")),
            box(clips[1]), fails)
        row("clip 2 is the whole surface again", (0, 0, W, H), box(clips[2]),
            fails)

    # 4. THE VERTICES, against the host's own IEEE 754
    print()
    print("4  the vertex array")
    stride = neon_constant("NEON_VERT_BYTES")
    row("vertex stride", 16, stride, fails)
    badf = 0
    for i in range(nverts):
        b = verts + i * stride
        xc, yc = u32(cpu, b + 0), u32(cpu, b + 4)
        xs, ys = s32(cpu, b + 8), s32(cpu, b + 12)
        if xs % 256 or ys % 256:
            fails.append("vertex %d: Xs or Ys is not a whole pixel" % i)
            break
        px, py = xs // 256 + cx, ys // 256 + cy
        want_xc = struct.unpack("<I", struct.pack("<f", (px - cx) / cx))[0]
        want_yc = struct.unpack("<I", struct.pack("<f", (py - cy) / cy))[0]
        if xc != want_xc or yc != want_yc:
            badf += 1
            if badf == 1:
                fails.append(
                    "vertex %d at pixel (%d,%d): Xc $%08X Yc $%08X, IEEE 754 "
                    "says $%08X $%08X" % (i, px, py, xc, yc, want_xc, want_yc))
    row("vertices whose clip coordinate differs", 0, badf, fails)
    counts["verts"] = nverts

    # 5. THE FRAGMENT UNIFORMS
    print()
    print("5  the fragment uniform blocks")
    unif = gvar(cpu, syms, "ngUnif")
    ustride = neon_constant("NEON_UNIF_STRIDE")
    tlb = neon_constant("NEON_TLB_CONF")
    swap = 1  # neon_rbSwap's default; the probe never changes it
    wanted = [tuple(probe_constant("NG_%s_%s" % (k, ch)) for ch in "RGBA")
              for k in ("BOXC", "ALPHAC", "CLIPC", "TEXTC")]
    badu = 0
    for d, (r_, g_, b_, a_) in enumerate(wanted):
        base = unif + d * ustride
        got = [u32(cpu, base + 4 * k) for k in range(5)]
        first, third = (b_, r_) if swap else (r_, b_)
        exp = [struct.unpack("<I", struct.pack("<f", v / 255.0))[0]
               for v in (first, g_, third, a_)] + [tlb]
        if got != exp:
            badu += 1
            if badu == 1:
                fails.append("draw %d uniforms %s, IEEE 754 says %s"
                             % (d, ["$%08X" % v for v in got],
                                ["$%08X" % v for v in exp]))
    row("uniform blocks that differ", 0, badu, fails)
    row("the TLB configuration word", "$FFFFFFFF", "$%08X" % tlb, fails)

    # 6. THE GLYPHS, against a second read of the font blob
    print()
    print("6  the glyph decomposition, against display.pi4's own blob")
    font = font_blob()
    tx, ty = probe_constant("NG_TEXTX"), probe_constant("NG_TEXTY")
    text = [c for c in range(33, 97)]
    row("glyphs the engine counted", len(text), nglyphs, fails)
    row("rectangles the engine counted", tcount // 6, nruns, fails)

    got_px = {}
    overlap = 0
    outside = 0
    spans = {}
    vstride = neon_constant("NEON_VERT_BYTES")
    for k in range(tcount // 6):
        b = verts + (tfirst + k * 6) * vstride
        xs = [s32(cpu, b + j * vstride + 8) // 256 + cx for j in range(6)]
        ys = [s32(cpu, b + j * vstride + 12) // 256 + cy for j in range(6)]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        if x1 <= x0 or y1 <= y0:
            fails.append("glyph rectangle %d has no area" % k)
            break
        if y0 < ty or y1 > ty + 16:
            outside += 1
        spans.setdefault((x0, x1), []).append((y0, y1))
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                if (xx, yy) in got_px:
                    overlap += 1
                got_px[(xx, yy)] = True

    want_px = set()
    for idx, ch in enumerate(text):
        for r_ in range(16):
            bits = font[ch][r_]
            for c_ in range(8):
                if bits & (128 >> c_):
                    want_px.add((tx + idx * 8 + c_, ty + r_))
    got = set(got_px)
    row("ink pixels the rectangles cover", len(want_px), len(got), fails)
    row("pixels the rectangles missed", 0, len(want_px - got), fails)
    row("pixels the rectangles added", 0, len(got - want_px), fails)
    row("rectangles that overlap", 0, overlap, fails)
    row("rectangles outside the cell", 0, outside, fails)

    # THE RECTANGLE SET ITSELF - a model agreeing with a model, said out
    # loud.  A decomposition that skipped the vertical band merge covers
    # exactly the same pixels and emits two or three times as many
    # rectangles; only this walk sees that.  (The attractive independent
    # property "equal-width rectangles that abut should have merged" is
    # wrong: the merge is per ROW PATTERN, so it fires on correct output.)
    want_rects = set()
    for idx, ch in enumerate(text):
        r_ = 0
        while r_ < 16:
            bits = font[ch][r_]
            span = 1
            while r_ + span < 16 and font[ch][r_ + span] == bits:
                span += 1
            if bits:
                c_ = 0
                start = -1
                while c_ <= 8:
                    if c_ < 8 and (bits & (128 >> c_)):
                        if start < 0:
                            start = c_
                    else:
                        if start >= 0:
                            want_rects.add((tx + idx * 8 + start, ty + r_,
                                            tx + idx * 8 + c_, ty + r_ + span))
                            start = -1
                    c_ += 1
            r_ += span
    got_rects = set()
    for (x0, x1), ys in spans.items():
        for (y0, y1) in ys:
            got_rects.add((x0, y0, x1, y1))
    row("rectangles the second walk expects", len(want_rects),
        len(got_rects), fails)
    row("rectangles emitted that should not have been", 0,
        len(got_rects - want_rects), fails)
    row("rectangles not emitted", 0, len(want_rects - got_rects), fails)
    counts["glyphs"] = len(text)
    counts["rects"] = tcount // 6

    # 7. THE SHADER STATE RECORDS AND THE ATTRIBUTE RECORDS, decoded with
    # the pinned struct layouts.  A struct has no opcode byte, so the
    # payload is assembled here rather than through Packet.decode().
    print()
    print("7  the shader state records and their attribute records")
    shrec = gvar(cpu, syms, "ngShrec")
    rstride = neon_constant("NEON_SHREC_STRIDE")
    rec_p = R.parse_struct("GL Shader State Record")
    attr_p = R.parse_struct("GL Shader State Attribute Record")
    row("the record is 36 bytes", 36, rec_p.length, fails)
    row("an attribute record is 16 bytes", 16, attr_p.length, fails)
    row("records are 32-byte aligned", True, (rstride % 32) == 0, fails)

    def decode_struct(pk, data):
        payload = 0
        for i in range(pk.length):
            payload |= data[i] << (8 * i)
        return {f.name: f.get(payload) for f in pk.fields}

    must_be_zero = [
        "Point size in shaded vertex data",
        "Vertex ID read by coordinate shader",
        "Instance ID read by coordinate shader",
        "Base Instance ID read by coordinate shader",
        "Vertex ID read by vertex shader",
        "Instance ID read by vertex shader",
        "Base Instance ID read by vertex shader",
        "Fragment shader does Z writes",
        "Turn off early-z test",
        "Enable Sample Rate Shading",
        "Any shader reads hardware-written Primitive ID",
        "Insert Primitive ID as first varying to fragment shader",
        "Turn off scoreboard",
        "Do scoreboard wait on first thread switch",
        "No prim pack",
    ]
    bad_zero = bad_clip = bad_vary = bad_thread = bad_attr = 0
    n_attr_checked = 0
    for d in range(ndraws):
        r = decode_struct(rec_p, grab(cpu, shrec + d * rstride, rec_p.length))
        for k in must_be_zero:
            if r.get(k):
                bad_zero += 1
        if not r["Enable clipping"]:
            bad_clip += 1
        if r["Number of varyings in Fragment Shader"] != 0:
            bad_vary += 1
        if not r["Disable implicit point/line varyings"]:
            bad_vary += 1
        # THE THREE THREAD-SECTION BITS ARE NOT ALL THE SAME: a coordinate
        # or vertex shader with no thread switch of its own starts past the
        # last THRSW, while a fragment shader's TLB writes must come AFTER a
        # real last-THRSW pair (mesa-24.3.4 src/broadcom/compiler/
        # nir_to_vir.c:4886-4890 and :4959).
        if r["Coordinate Shader start in final thread section"] != 1:
            bad_thread += 1
        if r["Vertex Shader start in final thread section"] != 1:
            bad_thread += 1
        if r["Fragment Shader start in final thread section"] != 0:
            bad_thread += 1
        for k in range(attrs):
            base = shrec + d * rstride + rec_p.length + k * attr_p.length
            at = decode_struct(attr_p, grab(cpu, base, attr_p.length))
            n_attr_checked += 1
            if at["Address"] != verts + k * 4:
                bad_attr += 1
            if at["Stride"] != neon_constant("NEON_VERT_BYTES"):
                bad_attr += 1
            if at["Number of values read by Coordinate shader"] != 1:
                bad_attr += 1
            if at["Number of values read by Vertex shader"] != 1:
                bad_attr += 1
            if at["Instance Divisor"] != 0:
                bad_attr += 1
            # SLOTS 2 AND 3 ARE Xs AND Ys, SIGNED INTEGERS READ AS INTEGERS.
            # $00001800 read as a float is a denormal; a fetcher that
            # flushed it to zero would collapse every primitive onto the
            # viewport centre.
            if k in (2, 3):
                if not at["Signed int type"] or not at["Read as int/uint"]:
                    bad_attr += 1
                if at["Type"] != 6:          # INT
                    bad_attr += 1
            else:
                if at["Type"] != 2:          # FLOAT
                    bad_attr += 1
                if at["Read as int/uint"]:
                    bad_attr += 1
            if at["Normalized int type"]:
                bad_attr += 1
    row("record booleans that should be zero and are not", 0, bad_zero, fails)
    row("records with clipping disabled", 0, bad_clip, fails)
    row("records with a varying declared", 0, bad_vary, fails)
    row("thread-section bits wrong", 0, bad_thread, fails)
    row("attribute records checked", ndraws * attrs, n_attr_checked, fails)
    row("attribute record fields wrong", 0, bad_attr, fails)
    counts["records"] = ndraws

    # 8. THE REFUSALS, which no board run reaches, read out of the source
    print()
    print("8  the guards, read out of the source")
    src = R.text(NEON)
    for name, pat in (
            ("a box with no alpha is dropped, not drawn",
             r"If Neon_A\(colour\) = 0"),
            ("the vertex arena is bounded",
             r"If neon_nVerts >= #NEON_MAX_VERTS"),
            ("the draw arena is bounded",
             r"If neon_nDraws >= #NEON_MAX_DRAWS"),
            ("a primitive outside a frame is refused",
             r"neon_err = #NEON_ERR_NOFRAME"),
            ("a second NeonFrameBegin is refused",
             r"neon_err = #NEON_ERR_INFRAME"),
            ("the arena must be page aligned",
             r"\(base % 4096\) <> 0"),
            ("the arena must not overlap the framebuffer",
             r"If neon_top > fbPage0"),
            ("the MMU is turned off on shutdown",
             r"ProcedureReturn V3dMmuOff\(\)"),
    ):
        row(name, True, bool(re.search(pat, src)), fails)


# =====================================================================
#  --mutate: each edit is applied to a TEMPORARY COPY of neon.pi4, and a
#  copy of the probe includes that copy.  RaspberryPi4/ is never written.
# =====================================================================
MUTANTS = [
    ("blend-src-one",
     "the colour source factor becomes ONE, so a translucent box paints at "
     "full strength.",
     "V3dClBlendCfg(1, #V3D_BF_INV_SRC_ALPHA, #V3D_BF_SRC_ALPHA, #V3D_BM_ADD, #V3D_BF_INV_SRC_ALPHA, #V3D_BF_SRC_ALPHA, #V3D_BM_ADD)",
     "V3dClBlendCfg(1, #V3D_BF_INV_SRC_ALPHA, #V3D_BF_ONE, #V3D_BM_ADD, #V3D_BF_INV_SRC_ALPHA, #V3D_BF_SRC_ALPHA, #V3D_BM_ADD)"),
    ("no-blend-bit",
     "CFG_BITS bit 19 is cleared; the blend packets still decode and the "
     "blender is simply off.",
     "cfg = V3dCfgBitsWord(1, 1, 0, 7) | (1 << 19)",
     "cfg = V3dCfgBitsWord(1, 1, 0, 7)"),
    ("write-mask-inverted",
     "COLOR_WRITE_MASKS is given $F instead of 0, which stores nothing - "
     "the polarity mistake v3dx_emit.c:82-91 exists to prevent.",
     "V3dClColorWriteMasks(0)",
     "V3dClColorWriteMasks($F)"),
    ("clip-every-draw",
     "the clip window is re-emitted for every draw instead of on a change. "
     "The picture is identical and the list is bigger.",
     """  If x = neon_emitClipX
    If y = neon_emitClipY
      If w = neon_emitClipW
        If h = neon_emitClipH
          ProcedureReturn
        EndIf
      EndIf
    EndIf
  EndIf""",
     "  EndIf"),
    ("glyph-drop-last-run",
     "the run walk stops at col < fw instead of col <= fw, so a run reaching "
     "the right edge of the cell is never emitted.",
     "While col <= neon_fw", "While col < neon_fw"),
    ("glyph-no-merge",
     "the vertical band merge is disabled.  THE PICTURE IS IDENTICAL; this "
     "proves the gate checks the rectangle COUNT and not only coverage.",
     """    span = 1
    While (row + span) < neon_fh
      nextBits = neon_GlyphRow(ch, row + span, bold)
      If nextBits <> bits
        Break
      EndIf
      span = span + 1
    Wend""",
     "    span = 1"),
    ("f32-truncate",
     "the mantissa rounds by truncation instead of to nearest.",
     "    mant = (m + half) >> sh", "    mant = m >> sh"),
    ("vertex-no-swap",
     "the red and blue components are handed to the shader unswapped.",
     "Global neon_rbSwap.i = 1", "Global neon_rbSwap.i = 0"),
    ("thread-section-all-alike",
     "the fragment shader's record says it starts in the final thread "
     "section, like the other two.  It must not.",
     "V3dShaderRecordFragment(neon_code + (2 * #NEON_CODE_SLOT), neon_unif + (slot * #NEON_UNIF_STRIDE), 1, 0, 1)",
     "V3dShaderRecordFragment(neon_code + (2 * #NEON_CODE_SLOT), neon_unif + (slot * #NEON_UNIF_STRIDE), 1, 1, 1)"),
    ("attr-xs-as-float",
     "Xs is declared FLOAT instead of a signed integer read as an integer.",
     "  V3dAttrRecordType(2, 1, #V3D_ATTR_INT, 1, 0, 1, 0)",
     "  V3dAttrRecordType(2, 1, #V3D_ATTR_FLOAT, 0, 0, 0, 0)"),
    ("clipping-off",
     "the shader record's Enable clipping bit is cleared.",
     "  V3dShaderRecordFlags(1, 0, 0, 0, 1, 0)",
     "  V3dShaderRecordFlags(0, 0, 0, 0, 1, 0)"),
    # Anchor repaired for Anvil main: the shared vertex arena global is
    # gNeonVerts there (RaspberryPi4/Lib/neon.pi4, the V3dAttrRecord call in
    # the shader-record setup), where the older copy called it neon_verts.
    ("attr-stride-wrong",
     "the attribute stride is the OLD 32-byte vertex instead of the 16-byte "
     "one, so every second vertex read would be garbage.",
     "V3dAttrRecord(k, gNeonVerts + (k * 4), #NEON_VERT_BYTES, #NEON_MAX_VERTS - 1, 1, 1)",
     "V3dAttrRecord(k, gNeonVerts + (k * 4), 32, #NEON_MAX_VERTS - 1, 1, 1)"),
]


def mutate(compiler: str, work: pathlib.Path) -> int:
    original = NEON.read_text(encoding="utf-8")
    killed = 0
    for i, (name, why, before, after) in enumerate(MUTANTS):
        if original.count(before) != 1:
            print("  %-26s COULD NOT BE APPLIED - the text it replaces is not "
                  "in neon.pi4 exactly once.  A mutant that cannot be applied "
                  "is not a passing mutant." % name)
            return 1
        mdir = work / ("mutant%02d" % i)
        probe = R.mutant_probe(mdir, mdir / "neon_mutant.pi4",
                               original.replace(before, after, 1), PROBE,
                               NEON_INCLUDE)
        fails: list = []
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                check(fails, {}, compiler, mdir, probe)
        except SystemExit as e:
            fails.append("the gate refused: %s" % e)
        except Exception as e:                     # noqa: BLE001
            fails.append("the gate raised: %r" % e)
        if fails:
            killed += 1
            print("  %-26s KILLED   (%d checks went red)" % (name, len(fails)))
        else:
            print("  %-26s SURVIVED - THE GATE DOES NOT SEE THIS" % name)
        print("      %s" % why)
    print()
    print("  %d of %d mutants killed" % (killed, len(MUTANTS)))
    return 0 if killed == len(MUTANTS) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compiler", default=os.environ.get("PMF_COMPILER"),
                    help="the PureMetalForge executable (default: PMF_COMPILER)")
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    if not a.compiler:
        raise SystemExit("No compiler was named. Pass --compiler or set "
                         "PMF_COMPILER to the PureMetalForge executable.")
    with tempfile.TemporaryDirectory(prefix="anvil-neon-") as td:
        work = pathlib.Path(td)
        if a.mutate:
            print("a64_neon_check --mutate")
            print()
            return mutate(a.compiler, work)
        fails: list = []
        counts: dict = {}
        print("a64_neon_check - the NeonArcade engine on V3D")
        print()
        check(fails, counts, a.compiler, work)
    print()
    print("  %d vertices checked against IEEE 754." % counts.get("verts", 0))
    print("  %d glyphs decomposed into %d rectangles; coverage checked against"
          % (counts.get("glyphs", 0), counts.get("rects", 0)))
    print("      an independent read of display.pi4's font blob.")
    print("  WHAT THIS GATE CANNOT SAY: that any of it rasterises.")
    print()
    if fails:
        print("FAIL - %d of %d checks" % (len(fails), ROWS[0]))
        for f in fails:
            print("  * %s" % f)
        return 1
    print("PASS - %d checks" % ROWS[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
