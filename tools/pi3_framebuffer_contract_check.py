"""Execute the production Pi 3 framebuffer contract against modeled firmware.

This is a desk gate: it compiles the isolated fixture and runs the emitted A64
in the repository interpreter.  It neither contacts a board nor substitutes a
Python implementation for Pi3FbInit/Pi3FbPack/Pi3FbError.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pi3_gate_build


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi3" / "Tests" / "framebuffer_contract.pi3"
BOARD = ROOT / "RaspberryPi3" / "Board" / "board.pi3"
INTERPRETER = ROOT / "tools" / "a64" / "a64_interp.py"
LOAD = 0x400000
STACK = 0x3000000
RETURN = 0x7000000
# Production draws to a fixed NC render buffer and DMA blits to firmware
# scanout. Keep both addresses distinct in the emitted model.
SCANOUT = 0x10000000
FRAMEBUFFER = 0x03000000
PITCH = 2560
HEIGHT = 480
FB_SIZE = PITCH * HEIGHT
DDC = 0x3F805000
I2C_C, I2C_S, I2C_DLEN, I2C_A = 0, 4, 8, 12
I2C_FIFO, I2C_DIV, I2C_DEL, I2C_CLKT = 16, 20, 24, 28
I2C_TA, I2C_DONE, I2C_TXD, I2C_RXD = 1, 2, 0x10, 0x20
I2C_ERR, I2C_CLKT_ERR = 0x100, 0x200
DMA = 0x3F007000
DMA_CHANNEL = 5
DMA_CS_ACTIVE, DMA_CS_END, DMA_CS_ERROR = 1, 2, 0x100
DMA_CS_ABORT, DMA_CS_RESET = 0x40000000, 0x80000000
DMA_WAITING_WRITES = 0x40
DMA_TDMODE, DMA_WAIT_RESP = 2, 8
DMA_D_WIDTH, DMA_S_WIDTH, DMA_BURST_SIZE2 = 0x20, 0x200, 2 << 12
DMA_DEST_INC, DMA_SRC_INC = 0x10, 0x100
DMA_BURST_MASK = 0xF000
DMA_GLOBAL_ENABLE = DMA + 0xFF0
DMA_CH = DMA + DMA_CHANNEL * 0x100
DTB = 0x00300000
DTB_END = DTB + 4096
SCRATCH = 0x06000000

# Linux bcm2708_fb-style geometry/offset/allocation order, with the two
# independently queried format properties and VC-memory ownership proof.
TAGS = (
    (0x00048003, 8, (640, 480)),
    (0x00048004, 8, (640, 480)),
    (0x00048005, 4, (32,)),
    (0x00048009, 8, (0, 0)),
    (0x00040001, 8, (4096, 0)),
    (0x00040008, 4, (0,)),
    (0x00040006, 4, (0,)),
    (0x00040007, 4, (0,)),
    (0x00010006, 8, (0, 0)),
)
EXPECTED_ERRORS = {
    "none": 0,
    "ownership": 1,
    "mailbox": 2,
    "tag_reply": 3,
    "geometry": 4,
    "pixel_order": 5,
    "alpha_mode": 6,
    "allocation": 7,
    "vc_range": 8,
    "overlap": 9,
}


def load_interpreter():
    spec = importlib.util.spec_from_file_location("pi3_fb_a64", INTERPRETER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load A64 interpreter: {INTERPRETER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_image(compiler: Path, work: Path, source: Path, name: str):
    image = work / f"{name}.img"
    command = [
        str(compiler), "--compile", str(source), "-t", "pi3",
        "--entry-returns", "--load-addr", hex(LOAD),
        "--stack-addr", hex(STACK), "-s", "-o", str(image),
    ]
    def run() -> None:
        result = subprocess.run(
            command, cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)),
            capture_output=True, text=True,
        )
        if result.returncode or not image.exists():
            raise SystemExit(
                "framebuffer fixture compile failed\n" + result.stdout + result.stderr
            )

    # One of this gate's cases compiles the real board entry point rather than
    # the isolated fixture, and that is a build of the monitor like any other.
    pi3_gate_build.compile_counted(
        run, source, image, compiler=compiler,
        by="tools/pi3_framebuffer_contract_check.py", root=ROOT,
    )
    symbol_file = Path(str(image) + ".sym")
    if not symbol_file.exists():
        raise SystemExit("compiler omitted framebuffer fixture symbol map")
    symbols = {
        key.lower(): int(value, 0)
        for key, value in (
            line.split("=", 1) for line in symbol_file.read_text().splitlines()
            if "=" in line
        )
    }
    return image.read_bytes(), symbols


def symbol(symbols: dict[str, int], name: str, base: int = LOAD) -> int:
    value = symbols[name.lower()]
    return value if name.lower().startswith("global_") else base + value


def write32(cpu, address: int, value: int) -> None:
    for index, byte in enumerate((value & 0xFFFFFFFF).to_bytes(4, "little")):
        cpu.memory[address + index] = byte


def read32(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + index, 0) << (8 * index) for index in range(4))


def read_tag_list(cpu, address: int, case=None):
    total = read32(cpu, address)
    if total not in (28, 32, 160, 176):
        raise AssertionError(f"unexpected property buffer size {total}")
    if read32(cpu, address + 4) != 0:
        raise AssertionError("property request code is not zero")
    tags = []
    offset = 8
    while True:
        tag = read32(cpu, address + offset)
        if tag == 0:
            expected_end = total - 4
            if offset != expected_end:
                raise AssertionError(f"end tag at {offset}, expected {expected_end}")
            break
        size = read32(cpu, address + offset + 4)
        code = read32(cpu, address + offset + 8)
        if code != 0:
            raise AssertionError(f"tag {tag:#x} request code is {code:#x}, expected zero")
        values = tuple(read32(cpu, address + offset + 12 + n) for n in range(0, size, 4))
        tags.append((tag, size, values))
        offset += 12 + ((size + 3) & ~3)
    if total == 176:
        width = case.width if case is not None else 640
        height = case.height if case is not None else 480
        expected = list(TAGS)
        expected[0] = (expected[0][0], expected[0][1], (width, height))
        expected[1] = (expected[1][0], expected[1][1], (width, height))
        if tuple(tags) != tuple(expected):
            raise AssertionError(f"framebuffer tag sequence/shape differs:\n{tuple(tags)!r}\n!=\n{tuple(expected)!r}")
    elif total == 160:
        if len(tags) != 1 or tags[0][0:2] != (0x30020, 136):
            raise AssertionError(f"EDID property tag shape differs: {tags!r}")
    elif len(tags) != 1 or tags[0][0:2] != (0x40003, 8):
        raise AssertionError(f"current-mode property tag shape differs: {tags!r}")
    return tags


def make_test_edid(width: int, height: int, *, bad_checksum: bool = False) -> bytes:
    """One checksum-valid EDID base block with the requested preferred DTD."""
    dtd = bytearray(18)
    pixel_clock_10khz = 14850 if (width, height) == (1920, 1080) else 6500
    hblank, hfront, hsync = ((280, 88, 44) if width >= 1920 else (320, 24, 136))
    vblank, vfront, vsync = ((45, 4, 5) if height >= 1080 else (38, 3, 6))
    dtd[0:2] = pixel_clock_10khz.to_bytes(2, "little")
    dtd[2], dtd[3] = width & 255, hblank & 255
    dtd[4] = ((width >> 8) << 4) | (hblank >> 8)
    dtd[5], dtd[6] = height & 255, vblank & 255
    dtd[7] = ((height >> 8) << 4) | (vblank >> 8)
    dtd[8], dtd[9] = hfront & 255, hsync & 255
    dtd[10] = ((vfront & 15) << 4) | (vsync & 15)
    dtd[11] = ((hfront >> 8) << 6) | ((hsync >> 8) << 4) | \
              ((vfront >> 4) << 2) | (vsync >> 4)
    dtd[17] = 0x18 | 0x06
    edid = bytearray(128)
    edid[:8] = bytes.fromhex("00 ff ff ff ff ff ff 00")
    edid[18:20] = bytes((1, 4))
    edid[24] = 2
    edid[54:72] = dtd
    edid[126] = 0
    edid[127] = (-sum(edid[:127])) & 255
    if bad_checksum:
        edid[127] ^= 1
    return bytes(edid)


def make_edid_chain(width: int, height: int, extension_count: int) -> bytes:
    """Checksum-valid base plus empty CTA blocks to exercise BSC2 segments."""
    if not 0 <= extension_count <= 4:
        raise ValueError("fixture extension count must fit the eight-block reader")
    base = bytearray(make_test_edid(width, height))
    base[126] = extension_count
    base[127] = (-sum(base[:127])) & 255
    blocks = [bytes(base)]
    for _ in range(extension_count):
        ext = bytearray(128)
        ext[0] = 0x02  # CTA extension, revision 3, no data blocks/DTD.
        ext[1] = 3
        ext[2] = 4
        ext[127] = (-sum(ext[:127])) & 255
        blocks.append(bytes(ext))
    return b"".join(blocks)


class FirmwareCase:
    def __init__(self, mode: str, alias: int = 0xC0000000,
                 alpha: int = 2, pixel_order: int = 1,
                 pitch: int | None = None, size: int | None = None,
                 sctlr: int = 0, width: int = 640, height: int = 480,
                 current_width: int = 640, current_height: int = 480,
                 edid: bytes | None = None, edid_status: int = 1,
                 actual_width: int | None = None, actual_height: int | None = None,
                 ddc_mode: str = "ok", ddc_busy: bool = False,
                 dma_mode: str = "ok"):
        self.mode = mode
        self.alias = alias
        self.alpha = alpha
        self.pixel_order = pixel_order
        self.width = width
        self.height = height
        self.current_width = current_width
        self.current_height = current_height
        self.expected_width = width
        self.expected_height = height
        self.actual_width = width if actual_width is None else actual_width
        self.actual_height = height if actual_height is None else actual_height
        self.edid = edid
        self.edid_status = edid_status
        self.ddc_mode = ddc_mode
        self.ddc_busy = ddc_busy
        self.dma_mode = dma_mode
        self.pitch = ((self.actual_width * 4 + 63) & ~63) if pitch is None else pitch
        self.size = self.pitch * self.actual_height if size is None else size
        self.sctlr = sctlr


def make_machine(a64, blob: bytes, symbols: dict[str, int], case: FirmwareCase,
                 base: int = LOAD, el: int = 3):
    class Machine(a64.A64):
        def __init__(self):
            super().__init__()
            self.case = case
            self.tick = 0
            self.request = 0
            self.requests: list[tuple] = []
            self.framebuffer_writes: list[tuple[int, int, int]] = []
            self.scanout_cpu_writes: list[tuple[int, int, int]] = []
            self.uart = bytearray()
            self.events: list[str] = []
            self.fb_candidate = DTB if case.mode == "overlap" else FRAMEBUFFER
            self.fb_extent = case.size
            self.requested_modes: list[tuple[int, int]] = []
            self.mailbox_tags: list[int] = []
            self.timing_payload: bytes | None = None
            self.hold_async_hpd = False
            self.ddc_transactions: list[tuple[int, int, int]] = []
            self.ddc_writes: list[tuple[int, int]] = []
            self.ddc_segment = 0
            self.ddc_offset = 0
            self.ddc_address = 0
            self.ddc_length = 0
            self.ddc_reading = False
            self.ddc_tx_pending = False
            self.ddc_fault = False
            self.ddc_fifo = bytearray()
            self.ddc_write_byte = -1
            self.ddc_read_count = 0
            self.ddc_core_max = 400_000_000
            self.dma_regs: dict[int, int] = {}
            self.dma_operations: list[tuple[int, int, int, int]] = []
            self.dma_tis: list[int] = []
            self.dma_lengths: list[int] = []
            self.dma_strides: list[int] = []
            self.dma_row_starts: list[list[tuple[int, int]]] = []
            self.dma_written_bytes = 0
            self.dma_outside_writes = 0

        def _complete_dma(self):
            cb = self.dma_regs.get(DMA_CH + 4, 0) & 0x3FFFFFFF
            ti = read32(self, cb)
            self.dma_tis.append(ti)
            src = read32(self, cb + 4) & 0x3FFFFFFF
            dst = read32(self, cb + 8) & 0x3FFFFFFF
            length = read32(self, cb + 12)
            stride = read32(self, cb + 16)
            xlen = length & 0xFFFF
            # BCM2835 TDMODE encodes YLENGTH as row_count - 1.  This model
            # deliberately decodes hardware semantics rather than echoing
            # the producer's encoded high half.
            ylen = (((length >> 16) & 0xFFFF) + 1) if ti & DMA_TDMODE else 1
            # On this BCM2837 path the observed BURST_LENGTH field value 2
            # reads three 128-bit beats (48 bytes) per fixed-source burst.
            # Model that source footprint explicitly: repeating only the
            # first 32-bit word hides reads into adjacent mailbox fields.
            burst_field = (ti & DMA_BURST_MASK) >> 12
            source_burst_bytes = ((burst_field + 1) * 16
                                  if ti & DMA_S_WIDTH else 4)
            src_stride = stride & 0xFFFF
            dst_stride = (stride >> 16) & 0xFFFF
            if src_stride & 0x8000:
                src_stride -= 0x10000
            if dst_stride & 0x8000:
                dst_stride -= 0x10000
            self.dma_operations.append((src, dst, xlen, ylen))
            self.dma_lengths.append(length)
            self.dma_strides.append(stride)
            row_starts = []
            for _ in range(ylen):
                row_starts.append((src, dst))
                for offset in range(0, xlen, 4):
                    # Incrementing transfers advance the working SRC pointer
                    # below as each word is consumed; fixed-source transfers
                    # select within the burst tile from the original address.
                    source_offset = (0 if ti & DMA_SRC_INC else
                                     offset % source_burst_bytes)
                    word = bytes(self.memory.get(src + source_offset + byte, 0)
                                 for byte in range(4))
                    for byte, value in enumerate(word):
                        address = dst + byte
                        self.memory[address] = value
                        if FRAMEBUFFER <= address < FRAMEBUFFER + self.fb_extent:
                            self.dma_written_bytes += 1
                        elif SCANOUT <= address < SCANOUT + self.fb_extent:
                            self.dma_written_bytes += 1
                        else:
                            self.dma_outside_writes += 1
                    if ti & DMA_SRC_INC:
                        src += 4
                    if ti & DMA_DEST_INC:
                        dst += 4
                if ti & DMA_TDMODE:
                    src += src_stride
                    dst += dst_stride
            self.dma_row_starts.append(row_starts)
            self.dma_regs[DMA_CH] = DMA_CS_END
            self.dma_regs[DMA_CH + 4] = 0

        def load(self, address, size):
            if DMA <= address <= DMA_GLOBAL_ENABLE + 4:
                return self.dma_regs.get(address, 0)
            if address == 0x3F003008:
                return 0
            if address == 0x3F003004:
                self.tick += (1_000_000 if self.case.mode == "timing_timeout" and self.hold_async_hpd
                              else 100000 if self.case.ddc_mode in ("timeout", "fifo_timeout")
                              else 1000)
                return self.tick
            if address == 0x3F00B8B8:  # mailbox FULL
                return 0
            if address == 0x3F00B898:  # mailbox EMPTY
                return 0x40000000 if self.hold_async_hpd else 0
            if address == 0x3F00B880:
                return self.request
            if address == 0x3F201018:  # PL011 FR
                return 0
            if address == 0x3F200004:  # GPIO GPFSEL1
                return 0
            if address == DDC + I2C_S:
                if self.case.ddc_busy and not self.ddc_transactions:
                    return I2C_TA
                if self.ddc_fault:
                    return I2C_ERR
                if self.ddc_tx_pending:
                    return I2C_TXD | I2C_TA
                if self.ddc_reading:
                    if self.case.ddc_mode == "timeout" or (
                        self.case.ddc_mode == "fifo_timeout" and self.ddc_read_count >= 16
                    ):
                        return I2C_TA
                    if self.ddc_fifo:
                        return I2C_RXD | I2C_TA
                    return I2C_DONE
                return I2C_DONE
            if address == DDC + I2C_A:
                return self.ddc_address
            if address == DDC + I2C_DLEN:
                return self.ddc_length
            if address == DDC + I2C_FIFO and self.ddc_reading:
                if self.ddc_fifo:
                    self.ddc_read_count += 1
                    return self.ddc_fifo.pop(0)
                return 0
            return super().load(address, size)

        def store(self, address, value, size):
            if DDC <= address < DDC + 32:
                self.ddc_writes.append((address, value & 0xFFFFFFFF))
            if SCANOUT <= address < SCANOUT + self.fb_extent:
                self.scanout_cpu_writes.append((address, value & 0xFFFFFFFF, size))
            if self.fb_candidate <= address < self.fb_candidate + self.fb_extent:
                self.framebuffer_writes.append((address, value & 0xFFFFFFFF, size))
                for byte in range(size):
                    self.memory[address + byte] = (value >> (byte * 8)) & 255
                return
            if address == DMA_GLOBAL_ENABLE:
                if self.case.dma_mode != "disabled":
                    self.dma_regs[address] = value & 0xFFFFFFFF
                return
            if DMA <= address <= DMA_GLOBAL_ENABLE + 4:
                self.dma_regs[address] = value & 0xFFFFFFFF
                if address == DMA_CH + 0x20:  # DEBUG is write-one-to-clear.
                    self.dma_regs[address] = 0
                elif address == DMA_CH:
                    if value & DMA_CS_ABORT:
                        if self.case.dma_mode == "abort_unsafe":
                            self.dma_regs[DMA_CH] = DMA_CS_ACTIVE | DMA_CS_ABORT
                        else:
                            self.dma_regs[DMA_CH] = 0
                            self.dma_regs[DMA_CH + 4] = 0
                    elif value & DMA_CS_RESET:
                        if self.case.dma_mode != "abort_unsafe":
                            self.dma_regs[DMA_CH] = 0
                            self.dma_regs[DMA_CH + 4] = 0
                    elif value & DMA_CS_ACTIVE:
                        cb = self.dma_regs.get(DMA_CH + 4, 0) & 0x3FFFFFFF
                        # The live channel registers reflect the descriptor
                        # that was fetched, including while a modeled transfer
                        # is stalled and before production snapshots pre-abort.
                        for reg, offset in ((8, 0), (12, 4), (16, 8),
                                            (20, 12), (24, 16)):
                            self.dma_regs[DMA_CH + reg] = read32(self, cb + offset)
                        self.dma_regs[DMA_CH] = DMA_CS_ACTIVE
                        if self.case.dma_mode not in ("timeout_safe", "abort_unsafe"):
                            self._complete_dma()
                return
            if address == 0x3F201000:
                self.uart.append(value & 0xFF)
                self.events.append("uart")
                return
            if address == 0x3F00B8A0:
                self.request = value & 0xFFFFFFFF
                buffer = self.request & 0x3FFFFFF0
                total = read32(self, buffer)
                if total == 32 and read32(self, buffer + 8) == 0x30041:
                    self.events.append("hpd_mailbox_pending")
                    self.mailbox_tags.append(0x30041)
                    if self.case.mode == "hpd_race":
                        self.hold_async_hpd = True
                        return
                    write32(self, buffer + 4, 0x80000000)
                    write32(self, buffer + 16, 0x80000008)
                    write32(self, buffer + 20, 0)
                    write32(self, buffer + 24, 0)
                    return
                if total == 32 and read32(self, buffer + 8) == 0x30004:
                    self.mailbox_tags.append(0x30004)
                    self.events.append("clock_max_mailbox")
                    write32(self, buffer + 4, 0x80000000)
                    write32(self, buffer + 16, 0x80000008)
                    write32(self, buffer + 20, read32(self, buffer + 20))
                    write32(self, buffer + 24, self.ddc_core_max)
                    return
                if total == 32 and read32(self, buffer + 8) == 0x10006:
                    self.events.append("vc_memory_mailbox")
                    self.mailbox_tags.append(0x10006)
                    write32(self, buffer + 4, 0x80000000)
                    write32(self, buffer + 16, 0x80000008)
                    write32(self, buffer + 20, 0x10000000)
                    write32(self, buffer + 24, 0x10000000)
                    return
                if total == 32 and read32(self, buffer + 8) == 0x48019:
                    self.events.append("display_power_mailbox")
                    self.mailbox_tags.append(0x48019)
                    write32(self, buffer + 4, 0x80000000)
                    write32(self, buffer + 16,
                            0x80000002 if self.case.mode == "power_short" else
                            0x80000004)
                    if self.case.mode == "power_bad_tag":
                        write32(self, buffer + 8, 0x40019)
                    if self.case.mode == "power_bad_size":
                        write32(self, buffer + 12, 4)
                    # Firmware rewrites the setter payload; Linux does not
                    # treat it as a display-id echo.
                    write32(self, buffer + 20, 1)
                    return
                if total == 60 and read32(self, buffer + 8) in (0x48017, 0x40017):
                    tag = read32(self, buffer + 8)
                    self.events.append("set_timing_mailbox" if tag == 0x48017 else "get_timing_mailbox")
                    self.mailbox_tags.append(tag)
                    if self.case.mode == "timing_timeout":
                        self.hold_async_hpd = True
                        return
                    write32(self, buffer + 4, 0x80000000)
                    # Deployed Pi 3 firmware leaves the no-payload SET tag's
                    # response length at zero. GET returns the full structure.
                    write32(self, buffer + 16, 0 if tag == 0x48017 else 0x80000024)
                    if tag == 0x48017:
                        self.timing_payload = bytes(self.memory.get(buffer + i, 0) for i in range(20, 56))
                    else:
                        payload = self.timing_payload
                        if payload is None:
                            # Plausible progressive firmware-current timing.
                            values = bytearray(36)
                            values[0] = 2
                            values[4:8] = (25_200).to_bytes(4, "little")
                            for off, val in ((8, self.case.current_width), (10, self.case.current_width + 16),
                                             (12, self.case.current_width + 112), (14, self.case.current_width + 160),
                                             (18, self.case.current_height), (20, self.case.current_height + 10),
                                             (22, self.case.current_height + 12), (24, self.case.current_height + 45)):
                                values[off:off + 2] = val.to_bytes(2, "little")
                            payload = bytes(values)
                        if self.case.mode == "timing_mismatch":
                            payload = bytearray(payload); payload[8:10] = (639).to_bytes(2, "little"); payload = bytes(payload)
                        for i, byte in enumerate(payload): self.memory[buffer + 20 + i] = byte
                    return
                if total == 28 and read32(self, buffer + 8) == 0x40002:
                    blank = read32(self, buffer + 20)
                    self.events.append("blank_on_mailbox" if blank else "blank_off_mailbox")
                    self.mailbox_tags.append(0x40002)
                    if self.case.mode == "blank_hold":
                        self.hold_async_hpd = True
                        return
                    write32(self, buffer + 4, 0x80000000)
                    write32(self, buffer + 16, 0x80000004)
                    return
                if total == 24 and read32(self, buffer + 8) == 0x48001:
                    self.events.append("release_mailbox")
                    self.mailbox_tags.append(0x48001)
                    write32(self, buffer + 4, 0x80000000)
                    write32(self, buffer + 16, 0x80000000)
                    return
                if total == 160:
                    tags = read_tag_list(self, buffer, case)
                    self.events.append("edid_mailbox")
                    self.requests.append(tuple(tags))
                    write32(self, buffer + 4, 0x80000000)
                    write32(self, buffer + 16, 0x80000088)
                    block = read32(self, buffer + 20)
                    write32(self, buffer + 20, block)
                    write32(self, buffer + 24, case.edid_status)
                    if case.edid is not None and block * 128 < len(case.edid):
                        source = case.edid[block * 128:(block + 1) * 128]
                        for index, byte in enumerate(source):
                            self.memory[buffer + 28 + index] = byte
                    return
                if total == 32:
                    tags = read_tag_list(self, buffer, case)
                    self.events.append("current_mode_mailbox")
                    self.requests.append(tuple(tags))
                    self.mailbox_tags.append(tags[0][0])
                    write32(self, buffer + 4, 0x80000000)
                    write32(self, buffer + 16, 0x80000008)
                    write32(self, buffer + 20, case.current_width)
                    write32(self, buffer + 24, case.current_height)
                    return
                self.events.append("framebuffer_mailbox")
                case.width, case.height = read32(self, buffer + 20), read32(self, buffer + 24)
                tags = read_tag_list(self, buffer, case)
                self.mailbox_tags.extend(tag for tag, _, _ in tags)
                self.requests.append(tuple(tags))
                self.requested_modes.append((case.width, case.height))
                if case.mode == "mailbox":
                    # A matching mailbox word with a non-success envelope is a
                    # bounded, owned failure rather than a timeout fixture.
                    write32(self, buffer + 4, 0x80000001)
                    return
                write32(self, buffer + 4, 0x80000000)
                offsets = (8, 28, 48, 64, 84, 104, 120, 136, 152)
                for (tag, size, _), offset in zip(TAGS, offsets):
                    write32(self, buffer + offset + 8, 0x80000000 | size)
                # Echoed/negotiated geometry.
                for off, val in ((20, case.actual_width), (24, case.actual_height),
                                 (40, case.actual_width), (44, case.actual_height),
                                 (60, 32), (76, 0), (80, 0)):
                    write32(self, buffer + off, val)
                write32(self, buffer + 96, SCANOUT | case.alias)
                write32(self, buffer + 100, case.size)
                write32(self, buffer + 116, case.pitch)
                write32(self, buffer + 132, case.pixel_order)
                write32(self, buffer + 148, case.alpha)
                write32(self, buffer + 164, 0x10000000)
                write32(self, buffer + 168, 0x10000000)
                if case.mode == "tag_reply":
                    write32(self, buffer + 8 + 8, 0x80000004)
                elif case.mode == "geometry":
                    write32(self, buffer + 20, 639)
                elif case.mode == "pixel_order":
                    write32(self, buffer + 132, 7)
                elif case.mode == "alpha_mode":
                    write32(self, buffer + 148, 3)
                elif case.mode == "allocation":
                    write32(self, buffer + 116, max(0, case.pitch - 4))
                elif case.mode == "size_short":
                    write32(self, buffer + 100, case.pitch * HEIGHT - 4)
                elif case.mode == "pitch_unaligned":
                    write32(self, buffer + 100, 2562 * HEIGHT)
                    write32(self, buffer + 116, 2562)
                elif case.mode == "pitch_over":
                    write32(self, buffer + 100, 16388 * HEIGHT)
                    write32(self, buffer + 116, 16388)
                elif case.mode == "vc_range":
                    write32(self, buffer + 164, 0x02000000)
                    write32(self, buffer + 168, 0x00100000)
                elif case.mode == "overlap":
                    write32(self, buffer + 96, 0x00300000 | case.alias)
                return
            if address == DDC + I2C_C:
                value &= 0xFFFFFFFF
                if value & 0x80:  # START
                    self.ddc_reading = bool(value & 1)
                    self.ddc_transactions.append((self.ddc_address, self.ddc_length,
                                                  int(self.ddc_reading)))
                    self.ddc_fault = self.case.ddc_mode == "nack" and self.ddc_address in (0x30, 0x50)
                    self.ddc_tx_pending = not self.ddc_reading and not self.ddc_fault
                    self.ddc_read_count = 0
                    self.ddc_fifo = bytearray()
                    if self.ddc_reading and not self.ddc_fault and self.case.ddc_mode != "timeout":
                        block = self.ddc_segment * 2 + (self.ddc_offset // 128)
                        start = block * 128 + (self.ddc_offset & 127)
                        source = self.case.edid or b""
                        available = max(0, min(self.ddc_length, len(source) - start))
                        self.ddc_fifo.extend(source[start:start + available])
                        if self.case.ddc_mode == "short_read" and self.ddc_fifo:
                            self.ddc_fifo = self.ddc_fifo[:-1]
                    return
                if value & 0x30:  # FIFO clear; leave controller idle.
                    self.ddc_fifo.clear()
                    self.ddc_reading = False
                    self.ddc_tx_pending = False
                    self.ddc_fault = False
                return
            if address == DDC + I2C_A:
                self.ddc_address = value & 0x7F
                return
            if address == DDC + I2C_DLEN:
                self.ddc_length = value & 0xFFFF
                return
            if address == DDC + I2C_FIFO and not self.ddc_reading:
                self.ddc_write_byte = value & 0xFF
                self.ddc_tx_pending = False
                if self.ddc_address == 0x30:
                    self.ddc_segment = self.ddc_write_byte
                    if (self.case.ddc_mode == "nack_segment_zero" and
                            self.ddc_write_byte == 0):
                        # Some displays do not ACK the optional segment
                        # pointer at zero. EDID blocks 0 and 1 must still be
                        # read directly through 0x50, offsets 0 and 128.
                        self.ddc_fault = True
                elif self.ddc_address == 0x50:
                    self.ddc_offset = self.ddc_write_byte
                return
            if address == DDC + I2C_S:
                # BSC status bits are write-one-to-clear.
                if value & I2C_DONE:
                    self.ddc_fault = False
                return
            if 0x3F000000 <= address < 0x40000000:
                return
            return super().store(address, value, size)

    cpu = Machine()
    cpu.memory.update({base + index: byte for index, byte in enumerate(blob)})
    # Direct Pi 3 firmware startup and property transactions are EL3-owned.
    cpu.enable_system_registers(el=el, preset={0xD51E1000: case.sctlr})  # SCTLR_EL3
    return cpu


def begin_call(cpu, symbols: dict[str, int], name: str, *args):
    cpu.pc = symbol(symbols, name)
    cpu.sp = STACK
    cpu.x[30] = RETURN
    for index, value in enumerate(args):
        cpu.x[index] = value & ((1 << 64) - 1)


def call(cpu, symbols: dict[str, int], name: str, *args, limit=20_000_000):
    begin_call(cpu, symbols, name, *args)
    for steps in range(limit):
        if cpu.pc == RETURN:
            return cpu.x[0], steps
        cpu.step()
    raise AssertionError(f"{name} did not return within {limit:,} A64 instructions")


def set_global(cpu, symbols, name, value):
    cpu.store(symbol(symbols, "global_" + name), value, 8)


def get_global(cpu, symbols, name):
    return cpu.load(symbol(symbols, "global_" + name), 8)


def error(cpu, symbols):
    result, _ = call(cpu, symbols, "Pi3FbError", limit=1_000)
    return result


def init_case(a64, blob, symbols, case, expected_error, success=False,
              complete_success=True):
    cpu = make_machine(a64, blob, symbols, case)
    if success and not complete_success:
        begin_call(cpu, symbols, "Pi3FbInit", DTB, DTB_END, 0x80000, 0x3F000000)
        for steps in range(100_000):
            if get_global(cpu, symbols, "pi3_fb") == FRAMEBUFFER:
                break
            if cpu.pc == RETURN:
                raise AssertionError((case.mode, "returned before allocation commit", cpu.x[0]))
            cpu.step()
        else:
            raise AssertionError((case.mode, "did not commit valid allocation"))
        result = 1
    else:
        result, steps = call(cpu, symbols, "Pi3FbInit", DTB, DTB_END, 0x80000, 0x3F000000)
    assert (result == 1) == success, (case.mode, result)
    assert error(cpu, symbols) == EXPECTED_ERRORS[expected_error], (
        case.mode, error(cpu, symbols), expected_error)
    if success:
        assert get_global(cpu, symbols, "pi3_fb") == FRAMEBUFFER
        assert get_global(cpu, symbols, "pi3_fb_scanout") == SCANOUT
        assert get_global(cpu, symbols, "pi3_fb_pitch") == case.pitch
        assert get_global(cpu, symbols, "pi3_fb_size") == case.size
        assert get_global(cpu, symbols, "pi3_fb_width") == case.actual_width
        assert get_global(cpu, symbols, "pi3_fb_height") == case.actual_height
        assert get_global(cpu, symbols, "pi3_fb_requested_width") == case.expected_width, (
            case.mode, "requested width", get_global(cpu, symbols, "pi3_fb_requested_width"), case.expected_width,
            cpu.ddc_transactions, cpu.ddc_writes, cpu.events)
        assert get_global(cpu, symbols, "pi3_fb_requested_height") == case.expected_height, (
            case.mode, "requested height", get_global(cpu, symbols, "pi3_fb_requested_height"), case.expected_height)
        assert cpu.requested_modes[-1] == (case.expected_width, case.expected_height)
        # Allocation establishes ownership only. The caller maps it NC before
        # its first pixel write, so initialization itself must not touch it.
        assert not cpu.framebuffer_writes, "Pi3FbInit wrote before MMU mapping"
        # Primitive drawing/DMA cases below begin after the lifecycle's
        # successful REDRAW publication; the compatibility initializer only
        # establishes allocation ownership.
        set_global(cpu, symbols, "pi3_fb_attached", 1)
    else:
        assert not cpu.framebuffer_writes, f"{case.mode} wrote untrusted framebuffer"
        assert get_global(cpu, symbols, "pi3_fb") == 0
        assert get_global(cpu, symbols, "pi3_fb_pitch") == 0
        assert get_global(cpu, symbols, "pi3_fb_size") == 0
    return cpu, steps


def check_hpd_property_isolation(a64, blob, symbols):
    steps = 0
    # Pi 3 Model B samples HPD through an asynchronous firmware-expander
    # request.  A synchronous property helper may run before that request is
    # complete; its request construction must never overwrite the dedicated
    # in-flight HPD lane.
    race = make_machine(a64, blob, symbols, FirmwareCase("hpd_race"), el=3)
    hpd_result = SCRATCH + 0x100
    rc, count = call(race, symbols, "Pi3FirmwareGpioGetStateStep", 132, hpd_result,
                     limit=100_000)
    steps += count
    property_base = (symbol(symbols, "global_pi3_property") + 15) & ~15
    hpd_lane = property_base + 64
    pending = bytes(race.memory.get(hpd_lane + offset, 0) for offset in range(32))
    assert rc == 0 and read32(race, hpd_lane + 8) == 0x30041
    assert get_global(race, symbols, "pi3_mailbox_outstanding") == 1
    rc, count = call(race, symbols, "Pi3ClockMaxRate", 4, limit=100_000)
    steps += count
    assert rc == 0xffffffffffffffff
    assert bytes(race.memory.get(hpd_lane + offset, 0) for offset in range(32)) == pending
    assert race.mailbox_tags == [0x30041] and race.events == ["hpd_mailbox_pending"]
    return 6, steps


def drive_step(cpu, symbols, name, *, limit=256):
    """Drive a cooperative production step until COMPLETE/RETRY/fatal."""
    steps = 0
    for ticks in range(limit):
        before = len(cpu.events)
        rc, count = call(cpu, symbols, name, limit=200_000)
        steps += count
        # A tick may submit at most one firmware transaction.
        assert len(cpu.events) - before <= 1, (name, rc, cpu.events[before:])
        if rc != 0:
            return rc, ticks + 1, steps
    raise AssertionError(f"{name} remained pending for {limit} ticks")


def check_incremental_attach(a64, blob, symbols):
    """Exercise one-shot cold firmware-mode adoption and fail-closed replug."""
    checks = steps = 0
    edid = make_test_edid(1920, 1080)
    headless = make_machine(a64, blob, symbols, FirmwareCase("headless"), el=3)
    rc, count = call(headless, symbols, "Pi3FbDeferredPrepare", DTB, DTB_END, 0x80000, 0x08000000)
    steps += count
    assert rc == 1 and "framebuffer_mailbox" not in headless.events
    assert get_global(headless, symbols, "pi3_fb") == 0
    checks += 3

    def prepared(case):
        nonlocal steps
        cpu = make_machine(a64, blob, symbols, case, el=3)
        rc, count = call(cpu, symbols, "Pi3FbDeferredPrepare", DTB, DTB_END, 0x80000, 0x08000000)
        steps += count
        assert rc == 1
        # Direct procedure execution bypasses the image startup that copies
        # initialized globals; reproduce the production cold value here.
        set_global(cpu, symbols, "pi3_fb_initial_probe", 1)
        return cpu

    cold = prepared(FirmwareCase("cold_inherited", width=1920, height=1080,
                                 current_width=1920, current_height=1080, edid=edid, edid_status=0))
    _, count = call(cold, symbols, "Pi3FbInitialPresence", 1, limit=10_000); steps += count
    assert get_global(cold, symbols, "pi3_fb_initial_probe") == 0
    assert get_global(cold, symbols, "pi3_fb_initial_connected") == 1
    rc, ticks, count = drive_step(cold, symbols, "Pi3FbAttachStep"); steps += count
    assert rc == 1 and ticks > 2
    assert (get_global(cold, symbols, "pi3_fb_width"), get_global(cold, symbols, "pi3_fb_height")) == (1920, 1080)
    assert get_global(cold, symbols, "pi3_fb_mode_source") == 5
    assert cold.events.index("current_mode_mailbox") < cold.events.index("framebuffer_mailbox")
    assert not ({"blank_on_mailbox", "set_timing_mailbox", "get_timing_mailbox"} & set(cold.events))
    assert get_global(cold, symbols, "pi3_fb_initial_connected") == 0
    checks += 10

    set_global(cold, symbols, "pi3_fb_attached", 1)
    rc, _, count = drive_step(cold, symbols, "Pi3FbDetachStep"); steps += count
    assert rc == 1 and get_global(cold, symbols, "pi3_fb") == FRAMEBUFFER
    before_events, before_allocations = len(cold.events), cold.events.count("framebuffer_mailbox")
    rc, _, count = drive_step(cold, symbols, "Pi3FbAttachStep"); steps += count
    assert rc == 2
    later = cold.events[before_events:]
    assert cold.events.count("framebuffer_mailbox") == before_allocations
    assert not ({"release_mailbox", "blank_on_mailbox", "set_timing_mailbox", "get_timing_mailbox"} & set(later))
    assert get_global(cold, symbols, "pi3_fb") == FRAMEBUFFER
    checks += 7

    absent = prepared(FirmwareCase("initial_absent", width=1920, height=1080,
                                   current_width=1920, current_height=1080, edid=edid, edid_status=0))
    _, count = call(absent, symbols, "Pi3FbInitialPresence", 0, limit=10_000); steps += count
    _, count = call(absent, symbols, "Pi3FbInitialPresence", 1, limit=10_000); steps += count
    assert get_global(absent, symbols, "pi3_fb_initial_probe") == 0
    assert get_global(absent, symbols, "pi3_fb_initial_connected") == 0
    rc, _, count = drive_step(absent, symbols, "Pi3FbAttachStep"); steps += count
    assert rc == 2 and "framebuffer_mailbox" not in absent.events
    assert "current_mode_mailbox" not in absent.events
    checks += 5

    mismatch = prepared(FirmwareCase("physical_mismatch", width=1920, height=1080,
                                     current_width=1280, current_height=720, edid=edid, edid_status=0))
    _, count = call(mismatch, symbols, "Pi3FbInitialPresence", 1, limit=10_000); steps += count
    rc, _, count = drive_step(mismatch, symbols, "Pi3FbAttachStep"); steps += count
    assert rc == 0xffffffffffffffff
    assert "current_mode_mailbox" in mismatch.events and "framebuffer_mailbox" not in mismatch.events
    assert get_global(mismatch, symbols, "pi3_fb") == 0
    assert get_global(mismatch, symbols, "pi3_fb_attach_error_phase") == 13
    assert get_global(mismatch, symbols, "pi3_fb_attach_error_tag") == 0x40003
    assert get_global(mismatch, symbols, "pi3_fb_attach_error_value0") == 1280
    assert get_global(mismatch, symbols, "pi3_fb_attach_error_value1") == 720
    checks += 8
    return checks, steps

def check_timing_reply_contract(a64, blob, symbols):
    """Gate the live Pi 3 SET zero-ack without weakening strict GET."""
    checks = steps = 0
    cpu = make_machine(a64, blob, symbols, FirmwareCase("headless"), el=3)
    message = 0x06000000

    def set_header(tag, value_bytes, reply):
        write32(cpu, message + 8, tag)
        write32(cpu, message + 12, value_bytes)
        write32(cpu, message + 16, reply)

    for reply, accepted in ((0, 1), (0x80000024, 1),
                            (0x80000000, 0), (36, 0)):
        set_header(0x48017, 36, reply)
        rc, count = call(cpu, symbols, "Pi3FbSetTimingReply", message, 8)
        steps += count
        assert rc == accepted, (hex(reply), rc)
        checks += 1
    for tag, value_bytes in ((0x40017, 36), (0x48017, 32)):
        set_header(tag, value_bytes, 0)
        rc, count = call(cpu, symbols, "Pi3FbSetTimingReply", message, 8)
        steps += count
        assert rc == 0
        checks += 1

    # GET_TIMING continues through the generic response validator: a zero or
    # short response and wrong tag/shape are all refused. Field mismatch is
    # independently exercised by the incremental attach case below.
    for tag, value_bytes, reply in (
        (0x40017, 36, 0),
        (0x40017, 36, 0x80000020),
        (0x48017, 36, 0x80000024),
        (0x40017, 32, 0x80000024),
    ):
        set_header(tag, value_bytes, reply)
        rc, count = call(cpu, symbols, "Pi3FbReply", message, 8, 0x40017, 36)
        steps += count
        assert rc == 0
        checks += 1
    return checks, steps


def check_power_reply_contract(a64, blob, symbols):
    """Require the live POWER1 response shape before any unblank."""
    checks = steps = 0
    for mode, wanted in (("power_ok", 1), ("power_short", -1),
                         ("power_bad_tag", -1), ("power_bad_size", -1)):
        cpu = make_machine(a64, blob, symbols, FirmwareCase(mode), el=3)
        for _ in range(4):
            rc, count = call(cpu, symbols, "Pi3FbPowerBegin", 1, limit=100_000)
            steps += count
            if rc != 0:
                break
        assert rc == 1, (mode, "begin", rc)
        for _ in range(4):
            rc, count = call(cpu, symbols, "Pi3FbPowerPoll", limit=100_000)
            steps += count
            if rc != 0:
                break
        assert rc == (wanted & ((1 << 64) - 1)), (mode, "poll", rc)
        assert cpu.events == ["display_power_mailbox"]
        assert "blank_off_mailbox" not in cpu.events
        checks += 3
    return checks, steps


def check_direct_contract(a64, blob, symbols):
    checks, steps = check_hpd_property_isolation(a64, blob, symbols)
    timing_checks, timing_steps = check_timing_reply_contract(a64, blob, symbols)
    checks += timing_checks
    steps += timing_steps
    power_checks, power_steps = check_power_reply_contract(a64, blob, symbols)
    checks += power_checks
    steps += power_steps
    incremental_checks, incremental_steps = check_incremental_attach(a64, blob, symbols)
    checks += incremental_checks
    steps += incremental_steps
    opaque = {0: 0, 1: 255, 2: 0}

    # A valid EDID preferred DTD selects 1024x768; invalid/missing EDID keeps
    # the firmware-current 640x480 mode. The allocation dimensions remain the
    # actual geometry returned by firmware, not merely the requested timing.
    valid_edid = make_test_edid(1920, 1080)
    for test_case, wanted in (
        (FirmwareCase("edid_valid", width=1920, height=1080,
                      current_width=1920, current_height=1080,
                      edid=valid_edid, edid_status=0), (1920, 1080)),
        (FirmwareCase("edid_invalid", edid=make_test_edid(1024, 768, bad_checksum=True),
                      edid_status=0), (640, 480)),
        (FirmwareCase("edid_absent", edid_status=1), (640, 480)),
    ):
        edid_cpu, count = init_case(a64, blob, symbols, test_case, "none",
                                    success=True, complete_success=False)
        steps += count
        assert edid_cpu.requested_modes[-1] == wanted
        if test_case.mode == "edid_valid":
            # Exact firmware KMS timing payload: u8/u8/u16, u32,
            # 12*u16, u32 = 36 bytes inside a 60-byte property envelope.
            assert len(edid_cpu.timing_payload or b"") == 36
            payload = edid_cpu.timing_payload
            assert payload is not None
            assert payload[0:4] == bytes((2, 0, 0, 0))
            assert int.from_bytes(payload[4:8], "little") == 148_500
            assert tuple(int.from_bytes(payload[offset:offset + 2], "little")
                         for offset in range(8, 32, 2)) == (
                             1920, 2008, 2052, 2200, 0,
                             1080, 1084, 1089, 1125, 0, 60, 0)
            assert int.from_bytes(payload[32:36], "little") == 3
            assert edid_cpu.events.index("set_timing_mailbox") < \
                   edid_cpu.events.index("get_timing_mailbox") < \
                   edid_cpu.events.index("framebuffer_mailbox")
            assert "edid_mailbox" not in edid_cpu.events
            checks += 7
        checks += 2

    # Matching framebuffer dimensions cannot conceal a refused output mode:
    # exact GET_TIMING readback must agree before any allocation request.
    mismatch, count = init_case(
        a64, blob, symbols,
        FirmwareCase("timing_mismatch", width=1920, height=1080,
                     current_width=1920, current_height=1080,
                     edid=valid_edid, edid_status=0),
        "mailbox")
    steps += count
    assert "set_timing_mailbox" in mismatch.events
    assert "get_timing_mailbox" in mismatch.events
    assert "framebuffer_mailbox" not in mismatch.events
    checks += 4

    # Each VideoCore alias must identify the same ARM allocation.  Alpha 2 is
    # repeated intentionally here; modes 0/1 are independently covered below.
    for alias in (0, 0x40000000, 0x80000000, 0xC0000000):
        cpu, count = init_case(a64, blob, symbols,
                               FirmwareCase("valid", alias=alias, alpha=2),
                               "none", success=True,
                               complete_success=(alias == 0xC0000000))
        steps += count
        colour, count = call(cpu, symbols, "Pi3FbPack", 0x12, 0x34, 0x56,
                             limit=10_000)
        steps += count
        assert colour & 0xFFFFFFFF == 0x00563412
        checks += 4
    # Firmware may report either 32-bit byte order; preserve the selected
    # channel order in exact packed words.
    for order, expected_word in ((1, 0x00563412), (0, 0x00123456)):
        cpu, count = init_case(a64, blob, symbols,
                               FirmwareCase("valid", pixel_order=order),
                               "none", success=True, complete_success=False)
        steps += count
        colour, count = call(cpu, symbols, "Pi3FbPack", 0x12, 0x34, 0x56,
                             limit=10_000)
        steps += count
        assert (colour & 0xFFFFFFFF) == expected_word, (order, hex(colour))
        checks += 2

    # A non-default stride is honored for every explicit clear, with padding
    # bytes left untouched; short/unaligned/over-limit replies are refused.
    padded, count = init_case(
        a64, blob, symbols, FirmwareCase("valid", width=64, height=32,
                                         current_width=64, current_height=32,
                                         pitch=320),
        "none", success=True, complete_success=False)
    steps += count
    _, count = call(padded, symbols, "Pi3FbClear", 0xA1B2C3D4,
                    limit=1_000_000)
    steps += count
    assert len(padded.framebuffer_writes) == 64 * 32
    expected = [FRAMEBUFFER + y * 320 + x * 4
                for y in range(32) for x in range(64)]
    assert [address for address, _, _ in padded.framebuffer_writes] == expected, \
        "framebuffer clear touched stride padding"
    assert all(size == 4 for _, _, size in padded.framebuffer_writes)
    checks += 2

    # Pixel stores use the returned pitch and reject all four outside edges.
    padded.framebuffer_writes.clear()
    for x, y, expected_rc in ((0, 0, 1), (63, 31, 1), (-1, 0, 0),
                              (64, 0, 0), (0, -1, 0), (0, 32, 0)):
        result, count = call(padded, symbols, "Pi3FbPixel", x, y, 0xA1B2C3D4,
                             limit=10_000)
        steps += count
        assert result == expected_rc, (x, y, result)
    assert [address for address, _, _ in padded.framebuffer_writes] == [
        FRAMEBUFFER, FRAMEBUFFER + 31 * 320 + 63 * 4]
    checks += 7

    # The mailbox context accepts EL3 with M/C clear and rejects either bit
    # before any property request. This matches the direct cold-start phase.
    for sctlr, expected in ((0, 1), (1, 0), (4, 0), (5, 0)):
        context_cpu = make_machine(a64, blob, symbols,
                                   FirmwareCase("valid", sctlr=sctlr), el=3)
        result, count = call(context_cpu, symbols, "Pi3MailboxContext", limit=10_000)
        steps += count
        assert result == expected, (sctlr, result)
        assert not context_cpu.requests
        checks += 2

    for alpha in (0, 1):
        cpu, count = init_case(a64, blob, symbols,
                               FirmwareCase("valid", alpha=alpha),
                               "none", success=True, complete_success=False)
        steps += count
        colour, count = call(cpu, symbols, "Pi3FbPack", 0x12, 0x34, 0x56,
                             limit=10_000)
        steps += count
        assert (colour >> 24) & 0xFF == opaque[alpha]
        checks += 4

    for mode, expected in (
        ("mailbox", "mailbox"),
        ("tag_reply", "tag_reply"),
        ("geometry", "geometry"),
        ("pixel_order", "pixel_order"),
        ("alpha_mode", "alpha_mode"),
        ("allocation", "allocation"),
        ("size_short", "allocation"),
        ("pitch_unaligned", "allocation"),
        ("pitch_over", "allocation"),
        ("vc_range", "vc_range"),
        # A DTB-address allocation now fails the stronger VC-range ownership
        # proof before the later overlap classification.
        ("overlap", "vc_range"),
    ):
        _, count = init_case(a64, blob, symbols, FirmwareCase(mode), expected)
        steps += count
        checks += 5

    # Ownership is refused before a property request, and the first allocation
    # remains live.  This also challenges the exact distinct ownership code.
    cpu = make_machine(a64, blob, symbols, FirmwareCase("valid"))
    set_global(cpu, symbols, "pi3_fb_attempted", 1)
    set_global(cpu, symbols, "pi3_fb", FRAMEBUFFER)
    result, count = call(cpu, symbols, "Pi3FbInit", DTB, DTB_END, 0x80000, 0x3F000000)
    steps += count
    assert result == 0 and error(cpu, symbols) == EXPECTED_ERRORS["ownership"]
    assert get_global(cpu, symbols, "pi3_fb") == FRAMEBUFFER
    assert not cpu.requests and not cpu.framebuffer_writes
    checks += 4
    return checks, steps


def check_native_ddc(a64, blob, symbols):
    """Exercise emitted BSC2 DDC transfer code, not a Python EDID substitute."""
    checks = 0
    steps = 0
    chain = make_edid_chain(1024, 768, 2)
    good = make_machine(a64, blob, symbols,
                        FirmwareCase("ddc", edid=chain,
                                     ddc_mode="nack_segment_zero"), el=3)
    result, count = call(good, symbols, "Pi3FbReadEdid", 400_000_000,
                         limit=2_000_000)
    steps += count
    assert result == 1
    assert call(good, symbols, "Pi3FbEdidStatus", limit=1_000)[0] == 1
    assert call(good, symbols, "AnvilEdidValid", limit=1_000)[0] == 1
    assert call(good, symbols, "AnvilEdidBlockCount", limit=1_000)[0] == 3
    assert (call(good, symbols, "AnvilEdidPreferredWidth", limit=1_000)[0],
            call(good, symbols, "AnvilEdidPreferredHeight", limit=1_000)[0]) == (1024, 768)
    starts = good.ddc_transactions
    assert starts == [
        (0x50, 1, 0), (0x50, 128, 1),
        (0x50, 1, 0), (0x50, 128, 1),
        (0x30, 1, 0), (0x50, 1, 0), (0x50, 128, 1),
    ], starts
    assert 0x30020 not in good.mailbox_tags
    assert "edid_mailbox" not in good.events
    assert not good.mailbox_tags and not good.requests, \
        "Pi3FbReadEdid itself must not call the firmware mailbox"
    assert [value & 255 for address, value in good.ddc_writes
            if address == DDC + I2C_FIFO] == [0, 128, 1, 0]
    assert any(address == DDC + I2C_DIV and value == 4000
               for address, value in good.ddc_writes)
    checks += 10

    for mode in ("nack", "timeout", "fifo_timeout", "short_read"):
        failed = make_machine(a64, blob, symbols,
                              FirmwareCase(mode, edid=chain, ddc_mode=mode), el=3)
        result, count = call(failed, symbols, "Pi3FbReadEdid", 400_000_000,
                             limit=1_000_000)
        steps += count
        assert result == 0, (mode, result)
        assert call(failed, symbols, "Pi3FbEdidStatus", limit=1_000)[0] == 5, mode
        assert 0x30020 not in failed.mailbox_tags
        checks += 3

    # An already active firmware transaction is not stolen or reset.
    busy = make_machine(a64, blob, symbols,
                        FirmwareCase("busy", edid=chain, ddc_busy=True), el=3)
    result, count = call(busy, symbols, "Pi3FbReadEdid", 400_000_000,
                         limit=10_000)
    steps += count
    assert result == 0
    assert call(busy, symbols, "Pi3FbEdidStatus", limit=1_000)[0] == 5
    assert not busy.ddc_writes and not busy.ddc_transactions
    checks += 4
    return checks, steps


def check_dma_scroll(a64, blob, symbols):
    """Run the emitted bounded scroll against modeled BCM2835 DMA registers."""
    checks = 0
    steps = 0

    def make_scroll(mode: str, *, width=160, height=128, pitch=640,
                    lines=64, preset_busy=False):
        size = pitch * height
        case = FirmwareCase("dma", width=width, height=height, pitch=pitch,
                            size=size, dma_mode=mode)
        cpu = make_machine(a64, blob, symbols, case, el=3)
        for name, value in (
            ("pi3_fb", FRAMEBUFFER), ("pi3_fb_scanout", SCANOUT),
            ("pi3_fb_pitch", pitch),
            ("pi3_fb_size", size), ("pi3_fb_width", width),
            ("pi3_fb_height", height), ("pi3_fb_dma_state", 0),
            ("pi3_fb_dma_active", 0), ("pi3_fb_attached", 1),
        ):
            set_global(cpu, symbols, name, value)
        write32(cpu, symbol(symbols, "global_pi3_fb_message"), 176)
        for y in range(height):
            row_byte = (y * 13 + 7) & 255
            cpu.memory.update({FRAMEBUFFER + y * pitch + x: row_byte
                               for x in range(pitch)})
        if preset_busy:
            cpu.dma_regs[DMA_CH] = DMA_CS_ACTIVE
            cpu.dma_regs[DMA_CH + 4] = 0x12340000
        write32(cpu, 0x06000000, 12)
        write32(cpu, 0x06000008, lines)
        write32(cpu, 0x06000010, 0xA1B2C3D4)
        return cpu, size, lines

    def assert_scroll_result(cpu, size, lines, *, dma: bool):
        pitch = cpu.case.pitch
        height = cpu.case.actual_height
        keep = height - lines
        for y in range(keep):
            expected = (y + lines) * 13 + 7 & 255
            row = bytes(cpu.memory.get(FRAMEBUFFER + y * pitch + x, 0)
                        for x in range(pitch))
            assert row == bytes((expected,)) * pitch, ("copy row", y, expected, row[:8])
        fill = (0xA1B2C3D4).to_bytes(4, "little") * (pitch // 4)
        for y in range(keep, height):
            row = bytes(cpu.memory.get(FRAMEBUFFER + y * pitch + x, 0)
                        for x in range(pitch))
            assert row == fill, ("fill row", y)
        assert get_global(cpu, symbols, "pi3_fb_dma_state") == (1 if dma else 2)

    dma_cpu, size, lines = make_scroll("ok", width=160, height=128,
                                      pitch=672, lines=64)
    result, count = call(dma_cpu, symbols, "Pi3FbScrollUp", lines,
                         0xA1B2C3D4, limit=8_000_000)
    steps += count
    assert result == 1
    control_base = (symbol(symbols, "global_pi3_fb_message") + 31) & ~31
    assert dma_cpu.dma_operations == [
        (FRAMEBUFFER + 64 * 672, FRAMEBUFFER, 672, 64),
        (control_base + 32, FRAMEBUFFER + 64 * 672, 672, 64),
    ], dma_cpu.dma_operations
    assert [length >> 16 for length in dma_cpu.dma_lengths] == [63, 63]
    assert dma_cpu.dma_row_starts[0] == [
        (FRAMEBUFFER + (64 + row) * 672, FRAMEBUFFER + row * 672)
        for row in range(64)
    ]
    assert dma_cpu.dma_tis[0] & (DMA_TDMODE | DMA_SRC_INC | DMA_DEST_INC) == (
        DMA_TDMODE | DMA_SRC_INC | DMA_DEST_INC)
    assert dma_cpu.dma_tis[1] & (DMA_TDMODE | DMA_DEST_INC) == (
        DMA_TDMODE | DMA_DEST_INC)
    assert all(ti & (DMA_S_WIDTH | DMA_D_WIDTH | DMA_BURST_SIZE2) ==
               (DMA_S_WIDTH | DMA_D_WIDTH | DMA_BURST_SIZE2)
               for ti in dma_cpu.dma_tis)
    assert [read32(dma_cpu, control_base + 32 + offset)
            for offset in range(0, 48, 4)] == [0xA1B2C3D4] * 12, (
                "fixed-source 128-bit burst-2 fill must seed all 48 source bytes")
    message_base = (symbol(symbols, "global_pi3_fb_message") + 15) & ~15
    assert control_base + 32 + 48 <= message_base + 176, (
        "48-byte fill tile must remain inside the DMA-owned message-buffer reservation")
    assert not dma_cpu.framebuffer_writes
    assert_scroll_result(dma_cpu, size, lines, dma=True)
    assert dma_cpu.dma_written_bytes == size, (dma_cpu.dma_written_bytes, size,
                                               dma_cpu.dma_operations)
    assert dma_cpu.dma_outside_writes == 0, dma_cpu.dma_outside_writes
    checks += 6

    fill_dma, fill_size, _ = make_scroll("ok", width=160, height=128,
                                        pitch=672, lines=1)
    write32(fill_dma, 0x06000000, 13)
    fill_rect = (3, 2, 140, 64, 0xA1B2C3D4)
    for address, value in zip((0x06000018, 0x06000020, 0x06000028,
                               0x06000030, 0x06000038), fill_rect):
        write32(fill_dma, address, value)
    result, count = call(fill_dma, symbols, "Main", limit=2_000_000)
    steps += count
    assert result == 1 and not fill_dma.dma_operations, (
        result, fill_dma.dma_operations,
        get_global(fill_dma, symbols, "pi3_fb_attached"),
        get_global(fill_dma, symbols, "pi3_fb_dma_active"),
        get_global(fill_dma, symbols, "pi3_fb_present_pending"))
    for y in range(128):
        for x in range(672):
            actual = fill_dma.memory.get(FRAMEBUFFER + y * 672 + x, 0)
            inside = 2 <= y < 66 and 3 * 4 <= x < (3 + 140) * 4
            expected = (0xA1B2C3D4 >> (((x & 3) * 8))) & 255 if inside else ((y * 13 + 7) & 255)
            assert actual == expected, ("DMA rect", x, y, actual, expected)
    assert len(fill_dma.framebuffer_writes) == 140 * 64
    assert not fill_dma.scanout_cpu_writes
    checks += 4

    # Partial-width multirow present must issue the actual scanout copy using
    # matching signed source/destination pitch gaps; a direct CPU write to
    # firmware scanout is forbidden.
    present, present_size, _ = make_scroll("ok", width=160, height=128,
                                          pitch=672, lines=1)
    set_global(present, symbols, "pi3_fb_scanout", SCANOUT)
    set_global(present, symbols, "pi3_fb_dirty", 1)
    set_global(present, symbols, "pi3_fb_dirty_left", 3)
    set_global(present, symbols, "pi3_fb_dirty_top", 2)
    set_global(present, symbols, "pi3_fb_dirty_right", 143)
    set_global(present, symbols, "pi3_fb_dirty_bottom", 66)
    for y in range(128):
        present.memory.update({FRAMEBUFFER + y * 672 + x: (x + y) & 255
                               for x in range(672)})
    result, count = call(present, symbols, "Pi3FbPresentBegin", limit=100_000)
    steps += count
    assert result == 1
    assert present.dma_operations == [
        (FRAMEBUFFER + 2 * 672 + 3 * 4, SCANOUT + 2 * 672 + 3 * 4, 140 * 4, 64),
    ], present.dma_operations
    assert present.dma_lengths == [((64 - 1) << 16) | (140 * 4)]
    gap = 672 - 140 * 4
    control_base = (symbol(symbols, "global_pi3_fb_message") + 31) & ~31
    assert read32(present, control_base + 16) == (gap | (gap << 16))
    assert not present.scanout_cpu_writes
    assert present.dma_written_bytes == 140 * 4 * 64
    assert present.dma_outside_writes == 0
    checks += 4

    # A genuinely in-flight present freezes the render buffer until its poll;
    # callers cannot modify pixels that the DMA engine may still be reading.
    inflight, _, _ = make_scroll("timeout_safe", width=160, height=128,
                                 pitch=672, lines=1)
    set_global(inflight, symbols, "pi3_fb_scanout", SCANOUT)
    for name, value in (("pi3_fb_dirty", 1), ("pi3_fb_dirty_left", 0),
                        ("pi3_fb_dirty_top", 0), ("pi3_fb_dirty_right", 16),
                        ("pi3_fb_dirty_bottom", 16)):
        set_global(inflight, symbols, name, value)
    result, count = call(inflight, symbols, "Pi3FbPresentBegin", limit=100_000)
    steps += count
    assert result == 1 and get_global(inflight, symbols, "pi3_fb_present_pending") == 1
    before = len(inflight.framebuffer_writes)
    result, count = call(inflight, symbols, "Pi3FbPixel", 0, 0, 0xFFFFFFFF,
                         limit=2_000)
    steps += count
    assert result == 0 and len(inflight.framebuffer_writes) == before
    assert not inflight.scanout_cpu_writes
    checks += 3

    fill_cpu, fill_size, _ = make_scroll("disabled", width=64, height=16,
                                         pitch=272, lines=1)
    write32(fill_cpu, 0x06000000, 13)
    fill_rect = (5, 1, 7, 2, 0x11223344)
    for address, value in zip((0x06000018, 0x06000020, 0x06000028,
                               0x06000030, 0x06000038), fill_rect):
        write32(fill_cpu, address, value)
    result, count = call(fill_cpu, symbols, "Main", limit=200_000)
    steps += count
    assert result == 1 and not fill_cpu.dma_operations
    for y in range(16):
        for x in range(272):
            actual = fill_cpu.memory.get(FRAMEBUFFER + y * 272 + x, 0)
            inside = 1 <= y < 3 and 5 * 4 <= x < 12 * 4
            expected = (0x11223344 >> ((x & 3) * 8)) & 255 if inside else ((y * 13 + 7) & 255)
            assert actual == expected, ("CPU rect", x, y, actual, expected)
    checks += 3

    before = bytes(fill_cpu.memory.get(FRAMEBUFFER + offset, 0)
                   for offset in range(fill_size))
    for bad_rect in ((63, 0, 2, 1, 0xFFFFFFFF), (0, 0, 0, 1, 0xFFFFFFFF),
                     (0, -1, 1, 1, 0xFFFFFFFF)):
        write32(fill_cpu, 0x06000000, 13)
        for address, value in zip((0x06000018, 0x06000020, 0x06000028,
                                   0x06000030, 0x06000038), bad_rect):
            write32(fill_cpu, address, value)
        result, count = call(fill_cpu, symbols, "Main", limit=2_000)
        steps += count
        assert result == 0
        assert bytes(fill_cpu.memory.get(FRAMEBUFFER + offset, 0)
                     for offset in range(fill_size)) == before
        checks += 2

    fallback, size, lines = make_scroll("disabled", width=64, height=200,
                                        pitch=272, lines=1)
    result, count = call(fallback, symbols, "Pi3FbScrollUp", lines,
                         0xA1B2C3D4, limit=8_000_000)
    steps += count
    assert result == 1
    assert get_global(fallback, symbols, "pi3_fb_dma_state") == 2
    # This smaller fixture exercises the bounded CPU path after DMA cannot be
    # enabled without turning a multi-megabyte framebuffer copy into a gate.
    for y in range(199):
        row = bytes(fallback.memory.get(FRAMEBUFFER + y * 272 + x, 0)
                    for x in range(272))
        wanted = ((y + 1) * 13 + 7) & 255
        assert row == bytes((wanted,)) * 272, (y, wanted, row[:8])
    assert not fallback.dma_operations
    checks += 3

    busy, busy_size, _ = make_scroll("busy", preset_busy=True)
    before = bytes(busy.memory.get(FRAMEBUFFER + offset, 0)
                   for offset in range(busy_size))
    result, count = call(busy, symbols, "Pi3FbScrollUp", 64, 0xA1B2C3D4,
                         limit=100_000)
    steps += count
    after = bytes(busy.memory.get(FRAMEBUFFER + offset, 0)
                  for offset in range(busy_size))
    assert result == 0xFFFFFFFFFFFFFFFF and before == after, (result, before[:16], after[:16],
                                               get_global(busy, symbols, "pi3_fb_dma_state"),
                                               busy.dma_regs)
    assert get_global(busy, symbols, "pi3_fb_dma_state") == 3
    pixel, count = call(busy, symbols, "Pi3FbPixel", 0, 0, 0xFFFFFFFF,
                        limit=2_000)
    steps += count
    assert pixel == 0 and before == bytes(
        busy.memory.get(FRAMEBUFFER + offset, 0) for offset in range(busy_size))
    checks += 4

    timed, size, lines = make_scroll("timeout_safe", width=64, height=200,
                                     pitch=256, lines=1)
    result, count = call(timed, symbols, "Pi3FbScrollUp", lines, 0xA1B2C3D4,
                         limit=12_000_000)
    steps += count
    assert result == 1 and get_global(timed, symbols, "pi3_fb_dma_state") == 2
    assert timed.dma_operations == [], "timed-out transfer must not be marked complete"
    assert timed.dma_regs.get(DMA_CH, 0) & (DMA_CS_ACTIVE | DMA_WAITING_WRITES) == 0
    cb = (symbol(symbols, "global_pi3_fb_message") + 31) & ~31
    cb_bus = (cb & 0x3FFFFFFF) | 0xC0000000
    assert (get_global(timed, symbols, "pi3_fb_dma_fail_cs") & 0xFFFFFFFF) & DMA_CS_ACTIVE
    assert (get_global(timed, symbols, "pi3_fb_dma_fail_conblk") & 0xFFFFFFFF) == cb_bus
    assert get_global(timed, symbols, "pi3_fb_dma_fail_length") == ((198 << 16) | 256)
    assert (get_global(timed, symbols, "pi3_fb_dma_fail_dst") & 0xFFFFFFFF) == ((FRAMEBUFFER & 0x3FFFFFFF) | 0xC0000000)
    assert get_global(timed, symbols, "pi3_fb_dma_fail_current_length") == ((198 << 16) | 256)
    assert (get_global(timed, symbols, "pi3_fb_dma_fail_current_dst") & 0xFFFFFFFF) == ((FRAMEBUFFER & 0x3FFFFFFF) | 0xC0000000)
    assert get_global(timed, symbols, "pi3_fb_dma_fail_elapsed_us") > 0
    assert get_global(timed, symbols, "pi3_fb_dma_submissions") == 1
    assert get_global(timed, symbols, "pi3_fb_dma_completions") == 0
    assert_scroll_result(timed, size, lines, dma=False)
    checks += 11

    unsafe, size, lines = make_scroll("abort_unsafe", width=64, height=200,
                                      pitch=256, lines=1)
    before = bytes(unsafe.memory.get(FRAMEBUFFER + offset, 0)
                   for offset in range(size))
    result, count = call(unsafe, symbols, "Pi3FbScrollUp", lines, 0xA1B2C3D4,
                         limit=4_000_000)
    steps += count
    assert result == 0xFFFFFFFFFFFFFFFF and get_global(unsafe, symbols, "pi3_fb_dma_state") == 3
    assert before == bytes(unsafe.memory.get(FRAMEBUFFER + offset, 0)
                           for offset in range(size))
    assert unsafe.dma_regs.get(DMA_CH, 0) & DMA_CS_ACTIVE
    checks += 3

    edge, edge_size, _ = make_scroll("ok", width=64, height=16,
                                     pitch=272, lines=1)
    edge_before = bytes(edge.memory.get(FRAMEBUFFER + offset, 0)
                        for offset in range(edge_size))
    for invalid_lines in (0, 16):
        result, count = call(edge, symbols, "Pi3FbScrollUp", invalid_lines,
                             0xA1B2C3D4, limit=2_000)
        steps += count
        assert result == 0
        assert bytes(edge.memory.get(FRAMEBUFFER + offset, 0)
                     for offset in range(edge_size)) == edge_before
        assert get_global(edge, symbols, "pi3_fb_dma_state") == 0
        checks += 2

    # The status row remains outside the console's scroll rectangle. Model a
    # nonzero origin, padding on every row, and untouched pixels below it.
    region, region_size, _ = make_scroll(
        "ok", width=160, height=128, pitch=640, lines=52)
    region_before = bytes(region.memory.get(FRAMEBUFFER + offset, 0)
                          for offset in range(region_size))
    top, region_height, delta = 3, 108, 52
    result, count = call(region, symbols, "Pi3FbScrollRegionUp",
                         top, region_height, delta, 0x11223344,
                         limit=8_000_000)
    steps += count
    assert result == 1
    assert len(region.dma_operations) == 2, (
        "region scroll should DMA-copy and DMA-fill: "
        + repr(region.dma_operations))
    row_bytes = region.case.pitch
    expected = bytearray(region_before)
    for row in range(top, top + region_height - delta):
        source_row = row + delta
        expected[row * row_bytes:(row + 1) * row_bytes] = \
            region_before[source_row * row_bytes:(source_row + 1) * row_bytes]
    packed = (0x11223344).to_bytes(4, "little")
    for row in range(top + region_height - delta, top + region_height):
        expected[row * row_bytes:(row + 1) * row_bytes] = packed * (row_bytes // 4)
    region_after = bytes(region.memory.get(FRAMEBUFFER + offset, 0)
                         for offset in range(region_size))
    assert region_after == bytes(expected), "region scroll damaged status/bottom rows or row padding"
    assert region.dma_operations[0] == (
        FRAMEBUFFER + (top + delta) * row_bytes,
        FRAMEBUFFER + top * row_bytes,
        row_bytes,
        region_height - delta,
    )
    assert [length >> 16 for length in region.dma_lengths] == [
        region_height - delta - 1, delta - 1]
    assert region.dma_outside_writes == 0
    checks += 4

    # The scheduled console path uses asynchronous start/poll rather than the
    # legacy synchronous helper. Assert that start returns immediately, an
    # active DMA poll performs no scanout stores, and copy->fill progresses
    # in separate bounded calls.
    async_fb, async_size, _ = make_scroll(
        "ok", width=160, height=128, pitch=640, lines=52)
    async_before = bytes(async_fb.memory.get(FRAMEBUFFER + offset, 0)
                         for offset in range(async_size))
    for address, value in ((0x06000000, 15), (0x06000008, top),
                           (0x06000010, region_height), (0x06000018, delta),
                           (0x06000020, 0x11223344)):
        write32(async_fb, address, value)
    result, count = call(async_fb, symbols, "Main", limit=10_000)
    steps += count
    assert result == 1 and count < 10_000, (result, count)
    assert len(async_fb.dma_operations) == 1
    assert get_global(async_fb, symbols, "pi3_fb_dma_active") == 1
    assert get_global(async_fb, symbols, "pi3_fb_scroll_phase") == 1
    # Hold the simulated engine active to model a real descriptor in flight.
    async_fb.dma_regs[DMA_CH] = DMA_CS_ACTIVE
    async_fb.dma_regs[DMA_CH + 4] = 0x12340000
    write32(async_fb, 0x06000000, 16)
    result, count = call(async_fb, symbols, "Main", limit=10_000)
    steps += count
    assert result == 0 and count < 10_000, (result, count)
    assert len(async_fb.dma_operations) == 1
    assert not async_fb.framebuffer_writes
    assert get_global(async_fb, symbols, "pi3_fb_scroll_phase") == 1
    # Complete copy. Poll schedules the fill descriptor and returns pending.
    async_fb.dma_regs[DMA_CH] = DMA_CS_END
    async_fb.dma_regs[DMA_CH + 4] = 0
    result, count = call(async_fb, symbols, "Main", limit=10_000)
    steps += count
    assert result == 0 and count < 10_000, (result, count)
    assert len(async_fb.dma_operations) == 2
    assert get_global(async_fb, symbols, "pi3_fb_scroll_phase") == 2
    result, count = call(async_fb, symbols, "Main", limit=10_000)
    steps += count
    assert result == 1 and count < 10_000, (result, count)
    assert get_global(async_fb, symbols, "pi3_fb_scroll_phase") == 0
    expected = bytearray(async_before)
    row_bytes = async_fb.case.pitch
    for row in range(top, top + region_height - delta):
        expected[row * row_bytes:(row + 1) * row_bytes] = \
            async_before[(row + delta) * row_bytes:(row + delta + 1) * row_bytes]
    packed = (0x11223344).to_bytes(4, "little")
    for row in range(top + region_height - delta, top + region_height):
        expected[row * row_bytes:(row + 1) * row_bytes] = packed * (row_bytes // 4)
    assert bytes(async_fb.memory.get(FRAMEBUFFER + offset, 0)
                 for offset in range(async_size)) == bytes(expected)
    checks += 9
    return checks, steps


def check_queue_overflow(a64, blob: bytes, symbols: dict[str, int]):
    """Prove screen producer overflow remains bounded and never renders."""
    fixture = (ROOT / "RaspberryPi3" / "Tests" / "framebuffer_contract.pi3").read_text()
    cpu = make_machine(a64, blob, symbols, FirmwareCase("geometry"), el=3)
    for name, value in (("pi3_screen_head", 0), ("pi3_screen_tail", 0),
                        ("pi3_screen_dropped", 0)):
        set_global(cpu, symbols, name, value)
    ring = symbol(symbols, "global_pi3_screen_ring")
    write32(cpu, 0x06000000, 17)
    result, steps = call(cpu, symbols, "Main", limit=1_000_000)
    assert result == 2, ("drop counter", result)
    assert get_global(cpu, symbols, "pi3_screen_head") == 1
    assert get_global(cpu, symbols, "pi3_screen_tail") == 2
    assert get_global(cpu, symbols, "pi3_screen_dropped") == 2
    assert cpu.load(ring, 1) == 0
    assert cpu.load(ring + 2, 1) == 2
    assert cpu.load(ring + 8191, 1) == 255
    assert not cpu.framebuffer_writes and not cpu.dma_operations

    stubs = (ROOT / "RaspberryPi3" / "Board" / "pi3stubs.pi3").read_text()
    def body(source: str, name: str) -> str:
        match = re.search(
            rf"(?ims)^Procedure(?:\.i)?\s+{re.escape(name)}\b.*?^EndProcedure\s*$",
            source)
        if not match:
            raise AssertionError(f"missing {name}")
        lines = [line.split(";", 1)[0].strip().lower()
                 for line in match.group(0).splitlines()]
        return re.sub(r"\s+", "", "\n".join(line for line in lines if line))
    assert body(stubs, "Pi3ScreenMirrorByte") == body(fixture, "Pi3ScreenMirrorByte"), (
        "fixture producer diverged from production")
    return 9, steps


def check_serial_display_separation() -> int:
    """Keep PL011's producer path enqueue-only and screen work poll-bounded."""
    stubs = (ROOT / "RaspberryPi3" / "Board" / "pi3stubs.pi3").read_text()
    uart = (ROOT / "RaspberryPi3" / "Lib" / "pl011_console.pi3").read_text()
    framebuffer = (ROOT / "RaspberryPi3" / "Lib" / "framebuffer.pbi").read_text()

    def body(source: str, name: str) -> str:
        match = re.search(
            rf"(?ims)^Procedure(?:\.i)?\s+{re.escape(name)}\b.*?^EndProcedure\s*$",
            source,
        )
        if not match:
            raise AssertionError(f"missing procedure {name}")
        return match.group(0).lower()

    mirror = body(stubs, "Pi3ScreenMirrorByte")
    forbidden = ("pi3screenattach", "pi3screendrain", "pi3screendrawglyph",
                 "pi3fbpresent", "pi3fbfillrect", "pi3fbscroll", "pi3fbdma")
    if any(token in mirror for token in forbidden):
        raise AssertionError("Pi3ScreenMirrorByte does rendering, scanout or DMA work")
    compact_mirror = re.sub(r"\s+", "", mirror)
    if "pi3_screen_dropped=pi3_screen_dropped+1" not in compact_mirror:
        raise AssertionError("display queue overflow is not counted")
    if "pi3_screen_ring.a[8192]" not in stubs.lower():
        raise AssertionError("display queue is no longer fixed-capacity")
    write = body(uart, "UartWrite")
    if write.find("pi3uartwrite") < 0 or write.find("pi3screenmirrorbyte") < write.find("pi3uartwrite"):
        raise AssertionError("screen mirror is not downstream of accepted UART output")
    drain = body(stubs, "Pi3ScreenDrain")
    compact_drain = re.sub(r"\s+", "", drain)
    if "pi3fbscrollpoll" not in drain or "processed<32" not in compact_drain or "now-start>=1500" not in compact_drain:
        raise AssertionError("screen service no longer polls async scroll and caps each turn")
    if "pi3fbscrollregionup" in drain:
        raise AssertionError("screen service regressed to synchronous full scroll")
    if "pi3_screen_scroll_pending<>0" not in drain:
        raise AssertionError("screen service does not yield while scroll DMA is pending")
    pending = body(stubs, "ScreenWorkPending")
    compact_pending = re.sub(r"\s+", "", pending)
    if "pi3fbready()<>0and(pi3_screen_tail<>pi3_screen_headorpi3_screen_attached=0orpi3_screen_initialized=0orpi3_screen_scroll_pending<>0orpi3fbpresentpending()<>0orpi3_fb_clear_pending<>0)" not in compact_pending:
        raise AssertionError("unavailable framebuffer would keep the scheduler busy")
    usage = body(stubs, "Pi3ScreenUsageTick")
    if "pi3_screen_initialized=0" not in usage or "pi3fbpresentbegin()" not in usage:
        raise AssertionError("CPU0 update can overlap banner draw or fail to present its damage")
    redraw = body(stubs, "Pi3DisplayRedraw")
    present_done = redraw.find("pi3fbpresentpending()")
    power_begin = redraw.find("pi3fbpowerbegin(1)")
    power_poll = redraw.find("pi3fbpowerpoll()")
    unblank = redraw.find("pi3fbblankbegin(0)")
    if min(present_done, power_begin, power_poll, unblank) < 0 or not (
            present_done < power_begin < power_poll < unblank):
        raise AssertionError("redraw must finish first DMA, validate POWER1, then unblank")
    dma_init = re.sub(r"\s+", "", body(framebuffer, "Pi3FbDmaInit"))
    if "messagebase=((@pi3_fb_message[0]+15)&~15)" not in dma_init or "pi3_fb_message[0]<>0" in dma_init:
        raise AssertionError("DMA scratch must be carved from the actual aligned property-buffer address")
    return 10


def check_board_mailbox_nc_alignment() -> int:
    """Prove aligned firmware spans, including the live raw-base+8 case."""
    board = (ROOT / "RaspberryPi3" / "Board" / "board.pi3").read_text()
    compact = re.sub(r"\s+", "", board.lower())
    required = (
        "propertybuffer=((@pi3_property[0]+15)>>4)<<4",
        "framebufferbuffer=((@pi3_fb_message[0]+15)>>4)<<4",
        "mmuaddnc(propertybuffer,propertybuffer+127)",
        "mmuaddnc(framebufferbuffer,framebufferbuffer+175)",
    )
    if any(item not in compact for item in required):
        raise AssertionError("board must register aligned property-message spans")

    checks = 4
    # Global Dim x.l[N] owns N+1 longs. Exercise every possible raw-address
    # alignment, with special emphasis on the observed Build44 raw+8 case.
    for raw_mod in range(16):
        raw = 0x10000000 + raw_mod
        aligned = (raw + 15) & ~15
        for owned_bytes, message_bytes in ((41 * 4, 128), (49 * 4, 176)):
            assert aligned + message_bytes <= raw + owned_bytes
            registered_lo, registered_hi = aligned, aligned + message_bytes - 1
            assert aligned >= registered_lo
            assert aligned + message_bytes - 1 <= registered_hi
            assert not (aligned + message_bytes <= registered_hi)
            checks += 4
    return checks


def check_uart_before_framebuffer_failure(a64, kernel: Path):
    blob = kernel.read_bytes()
    sym_path = Path(str(kernel) + ".sym")
    if not sym_path.is_file():
        raise SystemExit(f"fresh Pi3 kernel symbol map is missing: {sym_path}")
    symbols = {key.lower(): int(value, 0) for key, value in
               (line.split("=", 1) for line in sym_path.read_text().splitlines() if "=" in line)}
    board_load = 0x200000
    cpu = make_machine(a64, blob, symbols, FirmwareCase("geometry"),
                       base=board_load, el=3)
    # Valid minimal FDT outer header, as consumed by Pi3BootMemory.
    header = (0xD00DFEED).to_bytes(4, "big") + (4096).to_bytes(4, "big") + bytes(32)
    cpu.memory.update({DTB + index: byte for index, byte in enumerate(header)})

    # Board Main also asks ARM memory and UART clock.  Extend the modeled
    # mailbox response without weakening the framebuffer sequence checker.
    original_store = cpu.store

    def store(address, value, size):
        if address == 0x3F00B8A0:
            request = value & 0xFFFFFFFF
            buffer = request & 0x3FFFFFF0
            first_tag = read32(cpu, buffer + 8)
            if first_tag in (0x00010002, 0x00010005, 0x00030002, 0x00038041):
                cpu.events.append(f"mailbox_{first_tag:08x}")
                cpu.request = request
                write32(cpu, buffer + 4, 0x80000000)
                tag_size = read32(cpu, buffer + 12)
                write32(cpu, buffer + 16, 0x80000000 | tag_size)
                if first_tag == 0x00010002:
                    write32(cpu, buffer + 20, 0x00A02082)  # Pi 3 Model B, 1 GiB
                elif first_tag == 0x00010005:
                    write32(cpu, buffer + 20, 0)
                    write32(cpu, buffer + 24, 0x08000000)
                elif first_tag == 0x00030002:
                    write32(cpu, buffer + 24, 48000000)
                elif first_tag == 0x00038041:
                    write32(cpu, buffer + 20, 0)
                return
        return original_store(address, value, size)

    cpu.store = store
    cpu.pc = board_load
    cpu.sp = STACK
    cpu.x[0] = DTB
    # Stop as soon as the framebuffer refusal is reported. This reuses the
    # monitor artifact rather than compiling a second full board image.
    for steps in range(20_000_000):
        if b"framebuffer unavailable" in bytes(cpu.uart).lower():
            break
        cpu.step()
    else:
        raise AssertionError("board did not report framebuffer failure on UART; captured: "
                             + bytes(cpu.uart).decode("ascii", errors="replace"))
    text = bytes(cpu.uart)
    assert text, "no UART diagnostic was reachable before framebuffer failure"
    assert b"Framebuffer" in text or b"framebuffer" in text, text
    # At least one UART byte must precede the framebuffer request.  UART init
    # failure is deliberately non-fatal to display bring-up, but this modeled
    # UART is available, so diagnostic reachability is exact and observable.
    first_uart = cpu.events.index("uart")
    framebuffer_mailbox = cpu.events.index("framebuffer_mailbox")
    assert first_uart < framebuffer_mailbox
    return 3, steps, hashlib.sha256(blob).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True,
                        help="unified PureMetal Forge IDE executable for the isolated fixture")
    parser.add_argument("--fixture-only", action="store_true",
                        help="compatibility no-op; the gate is always hardware-free")
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    a64 = load_interpreter()
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-fb-contract-") as temporary:
        work = Path(temporary)
        blob, symbols = compile_image(compiler, work, SOURCE, "pi3-framebuffer-contract")
        missing = [name for name in (
            "pi3fbinit", "pi3fbpack", "pi3fbpixel", "pi3mailboxcontext",
        "pi3fberror", "global_pi3_fb_error"
        ) if name not in symbols]
        if missing:
            raise SystemExit("compiler omitted framebuffer symbols: " + ", ".join(missing))
        checks, steps = check_direct_contract(a64, blob, symbols)
        native_checks, native_steps = check_native_ddc(a64, blob, symbols)
        checks += native_checks
        steps += native_steps
        dma_checks, dma_steps = check_dma_scroll(a64, blob, symbols)
        checks += dma_checks
        steps += dma_steps
        queue_checks, queue_steps = check_queue_overflow(a64, blob, symbols)
        checks += queue_checks
        steps += queue_steps
        checks += check_serial_display_separation()
        checks += check_board_mailbox_nc_alignment()
        # The former board-image probe waited for a cold framebuffer failure.
        # Cold allocation is intentionally gone; the emitted integration path
        # above is now the authoritative hardware-free lifecycle proof.
        board_checks = board_steps = 0
    print(
        f"PASS: {checks + board_checks} Pi3 emitted framebuffer assertions; "
        f"{steps + board_steps:,} A64 instructions"
    )
    print("  exact 176-byte Linux-style tag list and response shapes")
    print("  aliases 0/40000000/80000000/C0000000 -> identical ARM address")
    print("  alpha modes, RGB/BGR packing, padded pitch, pixel bounds and reply refusals")
    print("  every invalid reply refused before framebuffer writes")
    print("  native BSC2: segment/offset sequence, multi-block EDID, no EDID mailbox request")
    print("  native BSC2: NACK, bounded timeout, FIFO stall, short-read and busy-owner refusals")
    print("  Pi 3 DMA: 2D overlap-safe scroll/fill, disabled-channel CPU fallback, busy-owner quarantine, timeout stop cases")
    print("  serial/display: 8192-byte bounded ring drops/counts oldest display bytes; producer never renders; async DMA scroll")
    print("  lifecycle: headless reserve; one-shot cold inherited mode adoption; replug stays retryable")
    print("  property ownership: HPD lane isolation; pending blank/present and timeout/detach races")
    print("Compiler SHA256:", hashlib.sha256(compiler.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
