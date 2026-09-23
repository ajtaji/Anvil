#!/usr/bin/env python3
"""Emitted BCM2711 HDMI DDC register/protocol gate with mocked MMIO."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4" / "Tests" / "hdmi_ddc_gate.pi4"
INTERP = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD, STACK, RETURN = 0x400000, 0x3000000, 0x7000000
CTRL, EDID_DEST = 0x06000000, 0x06001000
AUTO = (0xFEF00B00, 0xFEF05B00)
BSC = (0xFEF04500, 0xFEF09500)
ADDR, DATA_IN, CNT, CTL, IICEN, DATA_OUT, CTLHI = 0, 4, 0x24, 0x28, 0x2C, 0x30, 0x50
DTF_READ = 1
IIC_ENABLE, INTRP, NOACK = 1, 2, 4
NOSTOP, NOSTART, RESTART = 0x10, 0x20, 0x40


def load_a64():
    spec = importlib.util.spec_from_file_location("hdmi_ddc_a64", INTERP)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load A64 interpreter: {INTERP}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_fixture(compiler: Path, work: Path):
    image = work / "hdmi-ddc.img"
    cmd = [str(compiler), "--compile", str(SOURCE), "-t", "pi4",
           "--entry-returns", "--load-addr", hex(LOAD), "--stack-addr",
           hex(STACK), "-s", "-o", str(image)]
    result = subprocess.run(cmd, cwd=ROOT,
                            env=dict(os.environ, PMF_ROOT=str(ROOT)),
                            capture_output=True, text=True)
    if result.returncode or not image.is_file():
        raise SystemExit("HDMI DDC fixture compile failed\n" + result.stdout + result.stderr)
    sym = Path(str(image) + ".sym")
    if not sym.is_file():
        raise SystemExit("compiler omitted HDMI DDC fixture symbol map")
    symbols = {k.lower(): int(v, 0) for k, v in
               (line.split("=", 1) for line in sym.read_text().splitlines() if "=" in line)}
    return image.read_bytes(), symbols


def write32(mem, addr, value):
    for i, b in enumerate((value & 0xFFFFFFFF).to_bytes(4, "little")):
        mem[addr + i] = b


def read32(mem, addr):
    return sum(mem.get(addr + i, 0) << (8 * i) for i in range(4))


def make_dtd(width, height, clock10=6500):
    d = bytearray(18)
    hb, hf, hs, vb, vf, vs = 320, 24, 136, 38, 3, 6
    d[:2] = clock10.to_bytes(2, "little")
    d[2], d[3] = width & 255, hb & 255
    d[4] = ((width >> 8) << 4) | (hb >> 8)
    d[5], d[6] = height & 255, vb & 255
    d[7] = ((height >> 8) << 4) | (vb >> 8)
    d[8], d[9] = hf & 255, hs & 255
    d[10] = ((vf & 15) << 4) | (vs & 15)
    d[11] = ((hf >> 8) << 6) | ((hs >> 8) << 4) | ((vf >> 4) << 2) | (vs >> 4)
    d[17] = 0x1E
    return d


def fix_checksum(block):
    block[127] = (-sum(block[:127])) & 255


def make_edid(extensions=1, *, bad_base=False, bad_ext=False):
    base = bytearray(128)
    base[:8] = bytes.fromhex("00 ff ff ff ff ff ff 00")
    base[18:20] = bytes((1, 4))
    base[24] = 2
    base[54:72] = make_dtd(1024, 768)
    base[126] = extensions
    fix_checksum(base)
    if bad_base:
        base[127] ^= 1
    blocks = [base]
    for i in range(extensions):
        cta = bytearray(128)
        cta[0], cta[1], cta[2] = 2, 3, 6
        cta[4], cta[5] = 0x41, 16
        fix_checksum(cta)
        if bad_ext and i == 0:
            cta[127] ^= 1
        blocks.append(cta)
    return bytes().join(blocks)


class MockMachine:
    def __init__(self, a64, blob, symbols, edid, *, failure="none"):
        class CPU(a64.A64):
            pass
        self.cpu = CPU()
        original_load = self.cpu.load
        original_store = self.cpu.store
        self.cpu.memory.update({LOAD + i: b for i, b in enumerate(blob)})
        self.symbols = symbols
        self.edid = edid
        self.failure = failure
        self.writes = []
        self.transactions = []
        self.selected = 0
        self.address = 0
        self.length = 0
        self.ctl = 0
        self.in_words = {}
        self.active = False
        self.active_read = False
        self.segment = 0
        self.offset = 0
        self.cursor = 0
        self.data_cursor = 0
        self.active_port = 0
        self.expire = 0
        self.data_reads = []

        def load(address, size):
            if address in BSC:
                return 0
            for port, base in enumerate(BSC):
                if address == base + IICEN:
                    if self.active:
                        if self.failure == "timeout":
                            return 0
                        if self.failure == "nack" or (self.failure == "nack_block1" and self.active_block == 1):
                            return INTRP | NOACK
                        return INTRP
                    return 0
                if base + DATA_OUT <= address < base + DATA_OUT + 32 and self.active_read:
                    n = (address - (base + DATA_OUT)) // 4
                    start = self.data_cursor
                    word = 0
                    for j in range(4):
                        index = start + j
                        b = self.edid[index] if index < len(self.edid) else 0
                        word |= b << (j * 8)
                    self.data_cursor += 4
                    self.data_reads.append((address, start, word))
                    return word
            return original_load(address, size)

        def store(address, value, size):
            value &= 0xFFFFFFFF
            for port, base in enumerate(AUTO):
                if base <= address < base + 0x300:
                    self.writes.append((address, value, size))
                    return
            for port, base in enumerate(BSC):
                if base <= address < base + 0x80:
                    self.writes.append((address, value, size))
                    off = address - base
                    if off == ADDR:
                        self.address = value & 0x7F
                    elif off == CNT:
                        self.length = value & 0x3F
                        self.in_words = {}
                    elif DATA_IN <= off < DATA_IN + 0x20 and (off - DATA_IN) % 4 == 0:
                        self.in_words[(off - DATA_IN) // 4] = value
                    elif off == CTL:
                        self.ctl = value
                    elif off == IICEN:
                        if value & IIC_ENABLE:
                            self.active = True
                            self.active_port = port
                            payload = []
                            for wi in range((self.length + 3) // 4):
                                word = self.in_words.get(wi, 0)
                                payload.extend((word >> (8 * j)) & 255 for j in range(4))
                            is_read = bool(self.ctl & DTF_READ)
                            self.active_read = is_read
                            block_no = self.segment * 2 + self.offset // 128
                            self.active_block = block_no
                            self.transactions.append((port, self.address, self.length, is_read,
                                                      value & 0x70, tuple(payload[:self.length])))
                            if not is_read:
                                if self.address == 0x30 and payload:
                                    self.segment = payload[0]
                                elif self.address == 0x50 and payload:
                                    self.offset = payload[0]
                                    self.cursor = self.segment * 256 + self.offset
                            else:
                                if (value & NOSTART) == 0:
                                    self.cursor = self.segment * 256 + self.offset
                                    self.data_cursor = self.cursor
                        else:
                            self.active = False
                            self.active_read = False
                    return
            original_store(address, value, size)

        self.cpu.load = load
        self.cpu.store = store

    def call(self, op, *args, expired=0, limit=3_000_000):
        for i in range(8):
            write32(self.cpu.memory, CTRL + i * 8, 0)
        write32(self.cpu.memory, CTRL, op)
        write32(self.cpu.memory, CTRL + 8, expired)
        for i, arg in enumerate(args):
            write32(self.cpu.memory, CTRL + 16 + i * 8, arg)
        self.cpu.pc = LOAD + self.symbols["main"]
        self.cpu.sp = STACK
        self.cpu.x[30] = RETURN
        for n in range(limit):
            if self.cpu.pc == RETURN:
                return self.cpu.x[0], n
            self.cpu.step()
        raise AssertionError(f"operation {op} exceeded {limit:,} A64 instructions")


def cases(a64, blob, symbols):
    checks = steps = 0
    # Each port must release and configure only its own controller.
    for port in (0, 1):
        m = MockMachine(a64, blob, symbols, make_edid())
        result, n = m.call(1, port)
        steps += n
        assert result == 0
        base = BSC[port]
        assert (AUTO[port] + 0x26C, 2, 4) in m.writes
        assert (base + CTLHI, 0x40, 4) in m.writes
        assert (base + CTL, 0x90, 4) in m.writes
        assert not any(AUTO[1-port] <= a < AUTO[1-port] + 0x300 for a,_,_ in m.writes)
        assert not any(BSC[1-port] <= a < BSC[1-port] + 0x80 for a,_,_ in m.writes)
        checks += 4
    m = MockMachine(a64, blob, symbols, make_edid())
    result, n = m.call(1, 2)
    steps += n
    assert result == 0xFFFFFFFF and not m.writes, (result, m.writes[:8])
    checks += 1

    # A two-block raw EDID read exercises offset write/repeated-start and four
    # no-start 32-byte continuations. It also feeds the shared parser.
    m = MockMachine(a64, blob, symbols, make_edid())
    result, n = m.call(3, 0, 8, EDID_DEST)
    steps += n
    assert result == 1, (result, bytes(m.cpu.memory.get(EDID_DEST+i,0) for i in range(40)), m.data_reads[:12], m.writes[-8:], m.transactions[-8:])
    assert read32(m.cpu.memory, CTRL + 0x80) == 2
    assert read32(m.cpu.memory, CTRL + 0x88) == 0
    assert bytes(m.cpu.memory.get(EDID_DEST + i, 0) for i in range(256)) == make_edid(), "DDC bytes differ from fixture"
    assert m.call(7)[0] == 1
    direct_parse, _ = m.call(15)
    mode_rc, _ = m.call(14,1)
    mode_width, mode_height = read32(m.cpu.memory,CTRL+0x28), read32(m.cpu.memory,CTRL+0x30)
    pref_width, pref_height = m.call(8)[0], m.call(9)[0]
    assert direct_parse == 1 and mode_rc == 1 and mode_width == 1024 and mode_height == 768 and pref_width == 1024 and pref_height == 768, (direct_parse,mode_rc,mode_width,mode_height,pref_width,pref_height,m.call(10)[0],m.call(12)[0])
    tx = m.transactions
    assert tx[0][1:] == (0x50, 1, False, 0x50, (0,))
    assert [x[1] for x in tx if x[3]] == [0x50] * 8
    assert all(x[2] == 32 for x in tx if x[3])
    assert [x[4] for x in tx if x[3]] == [0x10, 0x30, 0x30, 0x20] * 2
    # Verify the parser received byte-identical block content in caller memory.
    assert bytes(m.cpu.memory.get(EDID_DEST + i, 0) for i in range(256)) == make_edid()
    checks += 9

    # Block 2 requires segment pointer 1; offsets and 0x30 addressing are
    # separate writes, then a repeated-start read from 0x50.
    m = MockMachine(a64, blob, symbols, make_edid(extensions=2))
    result, n = m.call(2, 0, 2, EDID_DEST)
    steps += n
    assert result == 0
    assert m.transactions[0][1:] == (0x30, 1, False, 0, (1,))
    assert m.transactions[1][1:] == (0x50, 1, False, 0x50, (0,))
    assert m.transactions[2][1:4] == (0x50, 32, True)
    assert bytes(m.cpu.memory.get(EDID_DEST + i, 0) for i in range(128)) == make_edid(2)[256:384]
    checks += 4

    # maxBlocks truncation and a transport NACK preserve valid base data while
    # reporting the bounded prefix; malformed base checksum is rejected.
    m = MockMachine(a64, blob, symbols, make_edid())
    assert m.call(3, 0, 1, EDID_DEST)[0] == 1
    assert read32(m.cpu.memory, CTRL + 0x88) == 1
    assert m.call(11)[0] == 1
    checks += 3
    m = MockMachine(a64, blob, symbols, make_edid(), failure="nack")
    result, n = m.call(2, 0, 0, EDID_DEST)
    steps += n
    assert result == -3 and m.call(4)[0] == -3 and m.call(5)[0] == 0
    checks += 3
    m = MockMachine(a64, blob, symbols, make_edid(), failure="timeout")
    result, n = m.call(2, 0, 0, EDID_DEST, expired=1)
    steps += n
    assert result == -4 and m.call(4)[0] == -4 and m.call(6)[0] == 0
    checks += 3
    m = MockMachine(a64, blob, symbols, make_edid(extensions=1), failure="nack_block1")
    assert m.call(3, 0, 8, EDID_DEST)[0] == 1
    assert read32(m.cpu.memory, CTRL + 0x80) == 1
    assert read32(m.cpu.memory, CTRL + 0x88) == 1
    assert m.call(7)[0] == 1 and m.call(11)[0] == 1
    checks += 5
    m = MockMachine(a64, blob, symbols, make_edid(bad_base=True))
    assert m.call(3, 0, 8, EDID_DEST)[0] == 0
    assert m.call(7)[0] == 0 and m.call(12)[0] == 3
    checks += 3
    return checks, steps


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", required=True, type=Path)
    args = ap.parse_args()
    compiler = args.compiler.resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    with tempfile.TemporaryDirectory(prefix="anvil-hdmi-ddc-") as tmp:
        blob, symbols = compile_fixture(compiler, Path(tmp))
        required = ("main", "pi4hdmiddcinit", "pi4hdmiddcreadblock", "pi4hdmiddcread")
        missing = [name for name in required if name not in symbols]
        if missing:
            raise SystemExit("compiler omitted HDMI DDC entry points: " + ", ".join(missing))
        checks, steps = cases(load_a64(), blob, symbols)
    print(f"PASS: {checks} HDMI DDC emitted assertions / {steps:,} A64 instructions")
    print("  per-port AUTOI2C release, BSC timing/setup, E-DDC segment/offset and repeated-start chunk reads")
    print("  native NACK/timeout, truncation, parser checksums and preferred-mode handoff")


if __name__ == "__main__":
    main()
