"""Use the ROM-booted Anvil command line to edit and reopen an AnvilFS disk."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading

from anvilfs_image import build_image, read_entries


ROOT = Path(__file__).resolve().parents[1]
NOTE = b"AnvilFS data survives a cold boot.\n"
PROGRAM = b"Procedure.q Main()\n  ProcedureReturn 42\nEndProcedure\n"
LONG_NAME = "a file with a long name.txt"
UNICODE_NAME = "notes \u03c0.txt"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    parser.add_argument("--storage-only", action="store_true",
                        help="Test the disk and Forge output without entering the payload")
    args = parser.parse_args()
    tools, work = args.zen_tools.resolve(), args.keep.resolve()
    work.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(tools))
    from zen_console import Console
    from zen_native_fixture import Fixture

    image = ROOT / "build/zentaji/anvil.zex"
    raw = image.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    meta = json.loads(Path(str(image) + ".boot.json").read_text())
    assert digest == meta["image_sha256"]
    stage = (meta["image_end"] + 4095) & -4096

    with tempfile.TemporaryDirectory(prefix="anvilfs-monitor-") as temp:
        seed = Path(temp) / "seed"
        (seed / "projects").mkdir(parents=True)
        (seed / "projects" / LONG_NAME).write_bytes(NOTE)
        (seed / "projects" / UNICODE_NAME).write_bytes(b"UTF-8 name\n")
        (seed / "projects" / "main.zen").write_bytes(PROGRAM)
        original = Path(temp) / "seed.img"
        build_image(original, 2 << 20, seed)
        medium = original.read_bytes()
    executable = tools / ("zenwin.exe" if os.name == "nt" else "zenwin")
    transcript = []

    def boot(label, disk, commands, readonly=False):
        folder = work / label
        transcript_start = len(transcript)
        fixture = Fixture(ram_size=128 << 20, cores=2,
                          hostfiles=[["anvil.zex", bytearray(raw), False]],
                          disks={0: (disk, readonly)}, display_modes=[(1024, 768, 60000)])
        fixture.power_on(0, 0)
        config = fixture.write(folder)
        config.write_text(config.read_text().replace("disk-memory 0 ", "disk 0 "), encoding="ascii")
        proc = subprocess.Popen(
            [str(executable), str(config), "--headless", "--live", "--max", "2000000000",
             "--live-seconds", "150", "--serial-listen", "0"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        lines, listeners = [], queue.Queue()

        def collect():
            for line in proc.stdout:
                lines.append(line)
                if line.startswith("SERIAL_LISTEN "):
                    listeners.put(line)
            listeners.put("")

        thread = threading.Thread(target=collect, daemon=True)
        thread.start()
        client = None
        try:
            listener = listeners.get(timeout=30)
            port = int(re.fullmatch(r"SERIAL_LISTEN 127\.0\.0\.1 (\d+) UART0\n", listener)[1])
            client = Console(port, 40)
            startup = client.prompt().decode("utf-8")
            assert "Zentaji boot ROM v1" in startup
            transcript.append(startup)
            for command, expected in commands:
                if args.storage_only and command.startswith("boot "):
                    continue
                try:
                    reply = client.command(command).decode("utf-8")
                except (ConnectionError, TimeoutError) as error:
                    raise RuntimeError(f"{label} stopped during {command!r}") from error
                transcript.append(reply)
                assert expected in reply, (command, reply)
            client.socket.sendall(b"halt\r")
            assert proc.wait(timeout=30) == 0
        finally:
            if client:
                client.close()
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)
            thread.join(timeout=3)
            (folder / "run.log").write_text("".join(lines), encoding="utf-8")
            (folder / "transcript.log").write_text("".join(transcript[transcript_start:]), encoding="utf-8")
        log = "".join(lines)
        assert "HOST_GPU_ERROR" not in log and "HOST_GPU_REFUSED" not in log
        return (folder / "disk0.img").read_bytes()

    source = f'projects/{LONG_NAME}'
    disk = boot("write", medium, [
        ("mount", "Mounted partition 1 uses AnvilFS"),
        ("ls projects", UNICODE_NAME),
        (f'cat "{source}"', NOTE.decode().strip()),
        ("mkdir projects/session", "Made the directory projects/session"),
        ("rmdir projects", "AnvilFS: directory is not empty"),
        ("rename projects projects/session/inside", "AnvilFS: cannot move a directory into its descendant"),
        (f'load "{source}"', "bytes"),
        (f'save projects/session/copied.txt {stage:X} {len(NOTE):X}', "Saved projects/session/copied.txt"),
        ("rename projects/session moved", "Renamed projects/session to moved."),
        ("cat moved/copied.txt", NOTE.decode().strip()),
        ("forge load projects/main.zen", f"Forge loaded {len(PROGRAM)} bytes"),
        ("forge compile moved/answer.pmf", "Forge wrote"),
        ("boot moved/answer.pmf", "The payload returned, r1 = $000000000000002A"),
        (f'cat "{source.upper()}"', "AnvilFS: path not found"),
        ("mkdir discard", "Made the directory discard"),
        ("rmdir discard", "Removed the directory discard."),
        (f'save disposable.txt {stage:X} {len(NOTE):X}', "Saved disposable.txt"),
        ("rm disposable.txt", "Removed disposable.txt."),
    ])
    reopened = boot("read-only-reboot", disk, [
        ("mount", "the medium is read-only"),
        ("ls moved", "copied.txt"),
        ("cat moved/copied.txt", NOTE.decode().strip()),
        ("boot moved/answer.pmf", "The payload returned, r1 = $000000000000002A"),
        ("cat disposable.txt", "AnvilFS: path not found"),
        ("mkdir forbidden", "No writer was armed"),
    ], readonly=True)
    assert reopened == disk
    with io.BytesIO(reopened) as contents:
        files = read_entries(contents)
        assert set(files) == {"projects", source, f"projects/{UNICODE_NAME}", "projects/main.zen",
                              "moved", "moved/copied.txt", "moved/answer.pmf"}
        kind, offset, length = files["moved/copied.txt"]
        contents.seek(offset)
        assert kind == 1 and contents.read(length) == NOTE
        kind, offset, length = files["moved/answer.pmf"]
        contents.seek(offset)
        payload = contents.read(length)
        assert kind == 1 and length > 128 and payload[:8] == b"PMFBOOT\0"
    (work / "result.json").write_text(json.dumps(
        dict(image_sha256=digest, disk_sha256=hashlib.sha256(disk).hexdigest(),
             payload_sha256=hashlib.sha256(payload).hexdigest(),
             payload_executed=not args.storage_only, transcript=transcript), ensure_ascii=False, indent=2,
    ) + "\n", encoding="utf-8")
    print("PASS ROM-booted Anvil commands and read-only restart on AnvilFS")


if __name__ == "__main__":
    main()
