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
FRAMEBUFFER = 0x01000000
PITCH = 2560
HEIGHT = 480
FB_SIZE = PITCH * HEIGHT
DTB = 0x00300000
DTB_END = DTB + 4096

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


def symbol(symbols: dict[str, int], name: str) -> int:
    value = symbols[name.lower()]
    return value if name.lower().startswith("global_") else LOAD + value


def write32(cpu, address: int, value: int) -> None:
    for index, byte in enumerate((value & 0xFFFFFFFF).to_bytes(4, "little")):
        cpu.memory[address + index] = byte


def read32(cpu, address: int) -> int:
    return sum(cpu.memory.get(address + index, 0) << (8 * index) for index in range(4))


def read_tag_list(cpu, address: int):
    total = read32(cpu, address)
    if total != 176:
        raise AssertionError(f"property buffer size {total}, expected 176")
    if read32(cpu, address + 4) != 0:
        raise AssertionError("property request code is not zero")
    tags = []
    offset = 8
    while True:
        tag = read32(cpu, address + offset)
        if tag == 0:
            if offset != 172:
                raise AssertionError(f"end tag at {offset}, expected 172")
            break
        size = read32(cpu, address + offset + 4)
        code = read32(cpu, address + offset + 8)
        if code != 0:
            raise AssertionError(f"tag {tag:#x} request code is {code:#x}, expected zero")
        values = tuple(read32(cpu, address + offset + 12 + n) for n in range(0, size, 4))
        tags.append((tag, size, values))
        offset += 12 + ((size + 3) & ~3)
    if tuple(tags) != TAGS:
        raise AssertionError(f"property tag sequence/shape differs:\n{tuple(tags)!r}\n!=\n{TAGS!r}")
    return tags


class FirmwareCase:
    def __init__(self, mode: str, alias: int = 0xC0000000,
                 alpha: int = 2, pixel_order: int = 1):
        self.mode = mode
        self.alias = alias
        self.alpha = alpha
        self.pixel_order = pixel_order


def make_machine(a64, blob: bytes, symbols: dict[str, int], case: FirmwareCase):
    class Machine(a64.A64):
        def __init__(self):
            super().__init__()
            self.tick = 0
            self.request = 0
            self.requests: list[tuple] = []
            self.framebuffer_writes: list[tuple[int, int, int]] = []
            self.uart = bytearray()
            self.events: list[str] = []
            self.fb_candidate = DTB if case.mode == "overlap" else FRAMEBUFFER

        def load(self, address, size):
            if address == 0x3F003008:
                return 0
            if address == 0x3F003004:
                self.tick += 1000
                return self.tick
            if address == 0x3F00B8B8:  # mailbox FULL
                return 0
            if address == 0x3F00B898:  # mailbox EMPTY
                return 0
            if address == 0x3F00B880:
                return self.request
            if address == 0x3F201018:  # PL011 FR
                return 0
            if address == 0x3F200004:  # GPIO GPFSEL1
                return 0
            return super().load(address, size)

        def store(self, address, value, size):
            if self.fb_candidate <= address < self.fb_candidate + FB_SIZE:
                self.framebuffer_writes.append((address, value & 0xFFFFFFFF, size))
                return
            if address == 0x3F201000:
                self.uart.append(value & 0xFF)
                self.events.append("uart")
                return
            if address == 0x3F00B8A0:
                self.events.append("framebuffer_mailbox")
                self.request = value & 0xFFFFFFFF
                buffer = self.request & 0x3FFFFFF0
                tags = read_tag_list(self, buffer)
                self.requests.append(tuple(tags))
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
                for off, val in ((20, 640), (24, 480), (40, 640), (44, 480),
                                 (60, 32), (76, 0), (80, 0)):
                    write32(self, buffer + off, val)
                write32(self, buffer + 96, FRAMEBUFFER | case.alias)
                write32(self, buffer + 100, FB_SIZE)
                write32(self, buffer + 116, PITCH)
                write32(self, buffer + 132, case.pixel_order)
                write32(self, buffer + 148, case.alpha)
                write32(self, buffer + 164, 0)
                write32(self, buffer + 168, 0x3F000000)
                if case.mode == "tag_reply":
                    write32(self, buffer + 8 + 8, 0x80000004)
                elif case.mode == "geometry":
                    write32(self, buffer + 20, 639)
                elif case.mode == "pixel_order":
                    write32(self, buffer + 132, 7)
                elif case.mode == "alpha_mode":
                    write32(self, buffer + 148, 3)
                elif case.mode == "allocation":
                    write32(self, buffer + 116, PITCH - 4)
                elif case.mode == "vc_range":
                    write32(self, buffer + 164, 0x02000000)
                    write32(self, buffer + 168, 0x00100000)
                elif case.mode == "overlap":
                    write32(self, buffer + 96, 0x00300000 | case.alias)
                return
            if 0x3F000000 <= address < 0x40000000:
                return
            return super().store(address, value, size)

    cpu = Machine()
    cpu.memory.update({LOAD + index: byte for index, byte in enumerate(blob)})
    cpu.enable_system_registers(el=2, preset={0xD51C1000: 0})  # SCTLR_EL2
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
        begin_call(cpu, symbols, "Pi3FbInit", DTB, DTB_END)
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
        result, steps = call(cpu, symbols, "Pi3FbInit", DTB, DTB_END)
    assert (result == 1) == success, (case.mode, result)
    assert error(cpu, symbols) == EXPECTED_ERRORS[expected_error], (
        case.mode, error(cpu, symbols), expected_error)
    if success:
        assert get_global(cpu, symbols, "pi3_fb") == FRAMEBUFFER
        assert get_global(cpu, symbols, "pi3_fb_pitch") == PITCH
        assert get_global(cpu, symbols, "pi3_fb_size") == FB_SIZE
        if complete_success:
            assert len(cpu.framebuffer_writes) == 640 * HEIGHT
        else:
            assert not cpu.framebuffer_writes
    else:
        assert not cpu.framebuffer_writes, f"{case.mode} wrote untrusted framebuffer"
        assert get_global(cpu, symbols, "pi3_fb") == 0
        assert get_global(cpu, symbols, "pi3_fb_pitch") == 0
        assert get_global(cpu, symbols, "pi3_fb_size") == 0
    return cpu, steps


def check_direct_contract(a64, blob, symbols):
    checks = 0
    steps = 0
    opaque = {0: 0, 1: 255, 2: 0}
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
        ("vc_range", "vc_range"),
        ("overlap", "overlap"),
    ):
        _, count = init_case(a64, blob, symbols, FirmwareCase(mode), expected)
        steps += count
        checks += 5

    # Ownership is refused before a property request, and the first allocation
    # remains live.  This also challenges the exact distinct ownership code.
    cpu = make_machine(a64, blob, symbols, FirmwareCase("valid"))
    set_global(cpu, symbols, "pi3_fb_attempted", 1)
    set_global(cpu, symbols, "pi3_fb", FRAMEBUFFER)
    result, count = call(cpu, symbols, "Pi3FbInit", DTB, DTB_END)
    steps += count
    assert result == 0 and error(cpu, symbols) == EXPECTED_ERRORS["ownership"]
    assert get_global(cpu, symbols, "pi3_fb") == FRAMEBUFFER
    assert not cpu.requests and not cpu.framebuffer_writes
    checks += 4
    return checks, steps


def check_uart_before_framebuffer_failure(a64, compiler, work):
    blob, symbols = compile_image(compiler, work, BOARD, "pi3-board-uart-order")
    cpu = make_machine(a64, blob, symbols, FirmwareCase("geometry"))
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
            if first_tag in (0x00010005, 0x00030002, 0x00038041):
                cpu.events.append(f"mailbox_{first_tag:08x}")
                cpu.request = request
                write32(cpu, buffer + 4, 0x80000000)
                tag_size = read32(cpu, buffer + 12)
                write32(cpu, buffer + 16, 0x80000000 | tag_size)
                if first_tag == 0x00010005:
                    write32(cpu, buffer + 20, 0)
                    write32(cpu, buffer + 24, 0x08000000)
                elif first_tag == 0x00030002:
                    write32(cpu, buffer + 24, 48000000)
                elif first_tag == 0x00038041:
                    write32(cpu, buffer + 20, 0)
                return
        return original_store(address, value, size)

    cpu.store = store
    cpu.pc = LOAD
    cpu.sp = 0
    cpu.x[0] = DTB
    # Stop as soon as the framebuffer refusal reaches the diagnostic park.
    park = symbol(symbols, "Pi3Park")
    for steps in range(20_000_000):
        if cpu.pc == park or cpu.pc == symbol(symbols, "pi3_cold_park"):
            break
        cpu.step()
    else:
        raise AssertionError("board did not reach framebuffer diagnostic park")
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
                        help="unified PureMetal Forge IDE executable")
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    if not compiler.is_file():
        raise SystemExit(f"compiler not found: {compiler}")
    a64 = load_interpreter()
    with tempfile.TemporaryDirectory(prefix="anvil-pi3-fb-contract-") as temporary:
        work = Path(temporary)
        blob, symbols = compile_image(compiler, work, SOURCE, "pi3-framebuffer-contract")
        missing = [name for name in (
            "pi3fbinit", "pi3fbpack", "pi3fberror", "global_pi3_fb_error"
        ) if name not in symbols]
        if missing:
            raise SystemExit("compiler omitted framebuffer symbols: " + ", ".join(missing))
        checks, steps = check_direct_contract(a64, blob, symbols)
        board_checks, board_steps, board_sha = check_uart_before_framebuffer_failure(
            a64, compiler, work)
    print(
        f"PASS: {checks + board_checks} Pi3 emitted framebuffer assertions; "
        f"{steps + board_steps:,} A64 instructions"
    )
    print("  exact 176-byte Linux-style tag list and response shapes")
    print("  aliases 0/40000000/80000000/C0000000 -> identical ARM address")
    print("  alpha 0/1/2 opaque bytes 00/FF/00; nine precise result codes")
    print("  every invalid reply refused before framebuffer writes")
    print("  early UART diagnostic reached before framebuffer refusal")
    print("Compiler SHA256:", hashlib.sha256(compiler.read_bytes()).hexdigest())
    print("Board fixture SHA256:", board_sha)


if __name__ == "__main__":
    main()
