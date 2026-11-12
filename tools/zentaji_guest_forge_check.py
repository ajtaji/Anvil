"""Exercise the built-in Forge on the real ROM-booted Zentaji monitor."""
import argparse
import hashlib
import json
import queue
import re
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import zentaji_exfat_oracle as exfat

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    "Procedure.q Main()\r\n"
    "  Protected base.q = 7 ; case-insensitive lookup\r\n"
    "  Base = (base + 1) * 6\r\n"
    "  ProcedureReturn base - 6\r\n"
    "EndProcedure"
).encode("ascii")


def check_container(container, encode):
    magic, version, header, load, entry, size, bss, bss_size, flags, reserved = (
        struct.unpack_from("<8sIIQQQQQII", container)
    )
    code = container[header:]
    assert (magic, version, header, size) == (b"PMFBOOT\0", 2, 128, len(code))
    assert (load % 8, entry, bss, bss_size, flags, reserved) == (0, load, load + size, 0, 1, 0)
    assert hashlib.sha256(code).digest() == container[64:96]
    arch, target, stack, extension = struct.unpack_from("<IIQ16s", container, 96)
    assert (arch, target, stack, extension) == (2, 1, ((load + size + 15) & -16) + 16384, bytes(16))
    # A separately assembled sequence verifies each emitted instruction.
    words = [
        encode("LIQ", rd=48), 7,
        encode("ADD", rd=16, ra=48, rb=0),
        encode("ADD", rd=48, ra=16, rb=0),
        encode("LIQ", rd=49), 1,
        encode("ADD", rd=48, ra=48, rb=49),
        encode("LIQ", rd=49), 6,
        encode("MUL", rd=48, ra=48, rb=49),
        encode("ADD", rd=16, ra=48, rb=0),
        encode("ADD", rd=48, ra=16, rb=0),
        encode("LIQ", rd=49), 6,
        encode("SUB", rd=48, ra=48, rb=49),
        encode("ADD", rd=1, ra=48, rb=0),
        encode("JR", ra=254),
    ]
    assert code == struct.pack(f"<{len(words)}Q", *words)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    args = parser.parse_args()
    tools = args.zen_tools.resolve()
    out = args.keep.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(tools))
    from zen_native_fixture import Fixture
    from zen_console import Console
    from opcodes import encode

    image = ROOT / "build/zentaji/anvil.zex"
    raw = image.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    metadata = json.loads(Path(str(image) + ".boot.json").read_text())
    assert digest == metadata["image_sha256"]

    disk = exfat.build(4096)
    exfat.seed_file(disk, SOURCE, "SOURCE.ZEN")
    fixture = Fixture(
        ram_size=128 << 20,
        cores=2,
        hostfiles=[["anvil.zex", bytearray(raw), False]],
        disks={0: (disk, False)},
        display_modes=[(1024, 768, 60000)],
    )
    fixture.power_on(0, 0)
    machine = fixture.write(out)
    machine.write_text(machine.read_text().replace("disk-memory 0 ", "disk 0 "), encoding="utf-8")

    executable = tools / ("zenwin.exe" if sys.platform == "win32" else "zenwin")
    process = subprocess.Popen(
        [str(executable), str(machine), "--headless", "--live", "--max", "2000000000",
         "--live-seconds", "150", "--serial-listen", "0", "--screenshot", str(out / "frame.png")],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    listener = queue.Queue()
    lines, transcript = [], []
    client = None

    def collect():
        for line in process.stdout:
            lines.append(line)
            if line.startswith("SERIAL_LISTEN "):
                listener.put(line)
        listener.put("")

    def command(text, expected, prompt=b"pmf> "):
        if prompt == b"pmf> ":
            reply = client.command(text).decode("ascii")
        else:
            client.socket.sendall(text.encode("ascii") + b"\r")
            deadline = time.monotonic() + client.timeout
            data = bytearray()
            while not data.endswith(b"\n" + prompt):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Forge prompt did not return for {text!r}")
                client.socket.settimeout(remaining)
                part = client.socket.recv(65536)
                if not part:
                    raise ConnectionError(f"UART closed while waiting for {text!r}")
                data.extend(part)
            reply = data.decode("ascii")
        transcript.append(reply)
        if expected:
            assert expected in reply.splitlines(), reply
        return reply

    thread = threading.Thread(target=collect, daemon=True)
    thread.start()
    try:
        port = int(re.fullmatch(r"SERIAL_LISTEN 127\.0\.0\.1 (\d+) UART0\n",
                                listener.get(timeout=30))[1])
        client = Console(port, 40)
        startup = client.prompt().decode("ascii")
        assert "Zentaji boot ROM v1" in startup
        transcript.append(startup)
        command("forge print 2+2*3", "Forge result 8")
        command("forge print -(2+3)*--4", "Forge result -20")
        command("forge print $7FFFFFFFFFFFFFFF+1", "Forge result -9223372036854775808")
        command("forge print -9223372036854775808", "Forge result -9223372036854775808")
        command("forge print $FEDCBA9876543210", "Forge result -81985529216486896")
        for expression in ("(1+2", "2(3)", "missing", "9223372036854775808"):
            reply = command("forge print " + expression, None)
            assert "!! Forge line 1," in reply and "Forge result" not in reply, reply

        command("forge", "Zentaji PureMetal Forge. Type help for commands.", b"forge> ")
        for line in ("Procedure.q Main()", "  Protected test.q = 7", "  test = test * 6",
                     "  ProcedureReturn test", "EndProcedure"):
            command(line, None, b"forge> ")
        command("run", "Forge result 42", b"forge> ")
        command("save SAVED.ZEN", "Forge source saved", b"forge> ")
        command("new", None, b"forge> ")
        command("exit", None)
        command("forge load SOURCE.ZEN", f"Forge loaded {len(SOURCE)} bytes")
        command("forge add ; appended after a source with no final newline", None)
        listing = command("forge list", None).splitlines()
        assert "  ProcedureReturn base - 6" in listing
        assert listing[-3:-1] == ["EndProcedure", "; appended after a source with no final newline"], listing
        command("forge run", "Forge result 42")
        reply = command("forge load MISSING.ZEN", None)
        assert "!! Forge storage:" in reply, reply
        command("forge run", "Forge result 42")
        assert "Forge wrote " in command("forge compile OUT.PMF", None)
        command("forge new", None)
        assert "!! Forge line 1," in command("forge compile OUT.PMF", None)
        assert "LASTRUN 00000000 00 00 00" in command("last run", None)
        command("boot OUT.PMF", "The payload returned, r1 = $000000000000002A")

        client.socket.sendall(b"halt\r")
        assert process.wait(timeout=30) == 0
        thread.join(timeout=3)
        log = "".join(lines)
        assert "HOST_GPU_REFUSED" not in log and "HOST_GPU_ERROR" not in log
        serial = bytes.fromhex(re.search(r"^SERIAL0 ([0-9A-Fa-f]+)$", log, re.M)[1])
        assert b"Anvil stopped." in serial
        files = exfat.root_files((out / "disk0.img").read_bytes())
        assert files["SOURCE.ZEN"] == SOURCE
        assert files["SAVED.ZEN"] == (
            b"Procedure.q Main()\n  Protected test.q = 7\n  test = test * 6\n"
            b"  ProcedureReturn test\nEndProcedure\n"
        )
        check_container(files["OUT.PMF"], encode)
        (out / "guest-built.pmf").write_bytes(files["OUT.PMF"])
        (out / "result.json").write_text(json.dumps(
            dict(image_sha256=digest, compiler="guest", returned=42, transcript=transcript),
            indent=2,
        ) + "\n")
        print("PASS built-in Zentaji Forge immediate expressions, editor, source disk I/O, and native PMF output")
    finally:
        if client:
            client.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        thread.join(timeout=3)
        (out / "run.log").write_text("".join(lines))
        (out / "transcript.txt").write_text("\n".join(transcript), encoding="utf-8")


if __name__ == "__main__":
    main()
