"""Emitted T6 kern/GPOS pair-position and layout gate."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from truetype_t1_check import compile_gate, run_entry, ROOT  # noqa: E402
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

GATE = ROOT / "RaspberryPi4/Tests/truetype_t6_gate.pi4"
META, BASE, MAGIC = 0x0F000000, 0x10000000, 0x54543652
TEXT = 0x0E000000

def cmap4() -> bytes:
    ends = (0x41, 0x42, 0x56, 0xFFFF)
    starts = ends
    deltas = ((1-0x41)&0xFFFF, (3-0x42)&0xFFFF, (2-0x56)&0xFFFF, 1)
    segs = len(ends)
    power = 1
    selector = 0
    while power * 2 <= segs:
        power *= 2
        selector += 1
    body = bytearray(struct.pack(">HHHHHHH", 4, 16 + 8*segs, 0, 2*segs,
                                 2*power, selector, 2*segs-2*power))
    body += struct.pack(">"+"H"*segs, *ends) + b"\0\0"
    body += struct.pack(">"+"H"*segs, *starts)
    body += struct.pack(">"+"H"*segs, *deltas)
    body += b"\0\0" * segs
    return struct.pack(">HHHH", 0, 1, 3, 1) + struct.pack(">I", 12) + body

def pairpos1() -> bytes:
    value1 = struct.pack(">hhhh", 3, -4, -100, 0)
    value2 = struct.pack(">hhhh", 5, 6, 20, 0)
    pairset = struct.pack(">HH", 1, 2) + value1 + value2
    coverage = struct.pack(">HHH", 1, 1, 1)
    header = struct.pack(">HHHHHH", 1, 32, 0xF, 0xF, 1, 12)
    return header + pairset + coverage

def pairpos2(class_mutant=False) -> bytes:
    matrix = bytearray(16)
    struct.pack_into(">hh", matrix, 12, -50, 10)  # class1=1, class2=1
    class1 = struct.pack(">HHHH", 1, 1, 1, 2 if class_mutant else 1)
    class2 = struct.pack(">HHHH", 1, 2, 1, 1)
    coverage = struct.pack(">HHH", 1, 1, 1)
    header = struct.pack(">HHHHHHHH", 2, 48, 4, 4, 32, 40, 2, 2)
    return header + matrix + class1 + class2 + coverage

def gpos(*, lookup_flag=False, class_mutant=False) -> bytes:
    sub1, sub2 = pairpos1(), pairpos2(class_mutant)
    script_list = struct.pack(">H4sH", 1, b"latn", 8) + struct.pack(">HH", 4, 0) + struct.pack(">HHHH", 0, 0xFFFF, 1, 0)
    feature_list = struct.pack(">H4sH", 1, b"kern", 8) + struct.pack(">HHHH", 0, 2, 0, 1)
    lookup0 = struct.pack(">HHHH", 2, 1 if lookup_flag else 0, 1, 8) + sub1
    lookup1 = struct.pack(">HHHH", 2, 0, 1, 8) + sub2
    lookup_list = struct.pack(">HHH", 2, 6, 6+len(lookup0)) + lookup0 + lookup1
    script_off = 10
    feature_off = script_off + len(script_list)
    lookup_off = feature_off + len(feature_list)
    header = struct.pack(">HHHHH", 1, 0, script_off, feature_off, lookup_off)
    return header + script_list + feature_list + lookup_list

def kern() -> bytes:
    pair = struct.pack(">HHh", 1, 2, -30)
    sub = struct.pack(">HHHHHHH", 0, 20, 1, 1, 6, 0, 0) + pair
    return struct.pack(">HH", 0, 1) + sub

def sfnt(*, include_gpos=True, lookup_flag=False, class_mutant=False) -> bytes:
    head = bytearray(54)
    struct.pack_into(">I", head, 0, 0x00010000)
    struct.pack_into(">I", head, 12, 0x5F0F3CF5)
    struct.pack_into(">H", head, 18, 1000)
    struct.pack_into(">h", head, 50, 0)
    maxp = bytearray(32)
    struct.pack_into(">IH", maxp, 0, 0x00010000, 4)
    hhea = bytearray(36)
    struct.pack_into(">I", hhea, 0, 0x00010000)
    struct.pack_into(">H", hhea, 34, 4)
    hmtx = b"".join(struct.pack(">Hh", 500, 0) for _ in range(4))
    tables = [(b"head", bytes(head)), (b"maxp", bytes(maxp)), (b"hhea", bytes(hhea)),
              (b"hmtx", hmtx), (b"cmap", cmap4()), (b"kern", kern())]
    if include_gpos:
        tables.append((b"GPOS", gpos(lookup_flag=lookup_flag, class_mutant=class_mutant)))
    count = len(tables)
    out = bytearray(12 + count*16)
    struct.pack_into(">IHHHH", out, 0, 0x00010000, count, 0, 0, 0)
    records = []
    for tag, data in tables:
        while len(out) & 3:
            out.append(0)
        offset = len(out)
        out.extend(data)
        padded = data + b"\0"*((-len(data))&3)
        checksum_data = padded
        if tag == b"head":
            checksum_data = bytearray(padded)
            checksum_data[8:12] = b"\0"*4
        words = struct.unpack(">"+"I"*(len(checksum_data)//4), checksum_data)
        checksum = sum(words) & 0xFFFFFFFF
        records.append((tag, checksum, offset, len(data)))
    for index, rec in enumerate(records):
        struct.pack_into(">4sIII", out, 12+index*16, *rec)
    return bytes(out)

def memory(font: bytes, mode: int, text=b"AVA"):
    meta = struct.pack("<3I", MAGIC, len(font), mode)
    result = {META+i: b for i, b in enumerate(meta)}
    result.update({BASE+i: b for i, b in enumerate(font)})
    result.update({TEXT+i: b for i, b in enumerate(text)})
    return result

def source_mutant(compiler: Path, temp: Path, font: bytes) -> bool:
    stage = temp/"mutant"
    rels = [
        "Anvil/Graphics/truetype.pbi", "Anvil/Graphics/truetype_metrics.pbi",
        "Anvil/Graphics/truetype_cmap.pbi", "Anvil/Graphics/truetype_outlines.pbi",
        "Anvil/Graphics/truetype_raster.pbi", "Anvil/Graphics/truetype_kern.pbi",
        "Anvil/Graphics/truetype_gpos.pbi", "Anvil/Graphics/truetype_layout.pbi",
        "Anvil/Graphics/truetype_slots.pbi", "Anvil/Graphics/truetype_renderer.pbi",
        "RaspberryPi4/Tests/truetype_t6_gate.pi4",
        "RaspberryPi4/Intrinsics/bcm2711_hardware.def", "Boards/Raspberry_Pi_4.board",
    ]
    for rel in rels:
        target=stage/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/rel,target)
    module=stage/"Anvil/Graphics/truetype_gpos.pbi"
    source=module.read_text()
    anchor="PeekI(valuesOut+field*SizeOf(.i))+anvil_tg_lookupValues[field]"
    if anchor not in source:
        raise SystemExit("T6 lookup accumulation mutant anchor missing")
    module.write_text(source.replace(anchor,"anvil_tg_lookupValues[field]",1))
    image=temp/"truetype_t6_mutant.img"
    symbols,blob=compile_gate(compiler,stage,stage/"RaspberryPi4/Tests/truetype_t6_gate.pi4",image)
    result,_=run_entry(symbols,blob,memory(font,1,b"AVA"))
    return result!=0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    compiler = Path(args.compiler).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="anvil-truetype-t6-") as folder:
        folder=Path(folder)
        image = folder/"truetype_t6.img"
        symbols, blob = compile_gate(compiler, ROOT, GATE, image)
        valid_font=sfnt()
        cases = [
            ("format1+format2 pair accumulation and wrapped layout", sfnt(), 1, b"AVA", 0),
            ("legacy kern fallback only when GPOS kern feature is absent", sfnt(include_gpos=False), 2, b"AV", 0),
            ("unsupported selected GPOS suppresses legacy fallback", sfnt(lookup_flag=True), 3, b"AV", 0),
            ("out-of-range class value rejected", sfnt(class_mutant=True), 4, b"AV", 0),
            ("CRLF hard break and centered measured positions", sfnt(), 5, b"AV\r\nA", 0),
            ("consecutive and trailing hard breaks", sfnt(), 6, b"A\n\nA\n", 0),
            ("leading hard break", sfnt(), 7, b"\nA", 0),
        ]
        for name, font, mode, text, expected in cases:
            result, steps = run_entry(symbols, blob, memory(font, mode, text))
            if result != expected:
                raise SystemExit(f"T6 emitted gate failed ({name}): case {result}")
            print(f"PASS: {name}; {steps} interpreter instructions")
        if not source_mutant(compiler,folder,valid_font):
            raise SystemExit("T6 weakened multi-lookup accumulation mutant was not rejected")
        print("PASS: GPOS overwrite instead of lookup accumulation source mutant rejected")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
