"""Exercise Anvil's Zentaji Ethernet path against the native host NAT."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time

from anvilfs_image import build_image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = b"Procedure.q Main()\n  ProcedureReturn 42\nEndProcedure\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    args = parser.parse_args()
    tools, output = args.zen_tools.resolve(), args.keep.resolve()
    sys.path.insert(0, str(tools))
    from zen_console import Console
    from zen_native_fixture import Fixture

    image = ROOT / "build/zentaji/anvil.zex"
    raw = image.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == json.loads(Path(str(image) + ".boot.json").read_text())["image_sha256"]
    executable = tools / ("zenwin.exe" if os.name == "nt" else "zenwin")
    result = {"image_sha256": digest}

    def boot(attached):
        label = "nat" if attached else "disconnected"
        folder = output / label
        fixture = Fixture(ram_size=128 << 20, cores=2,
                          hostfiles=[["anvil.zex", bytearray(raw), False]],
                          display_modes=[(1024, 768, 60000)])
        fixture.net_attached = attached
        if attached:
            with tempfile.TemporaryDirectory(prefix="zentaji-net-") as temporary:
                seed = Path(temporary) / "source"
                seed.mkdir()
                (seed / "main.zen").write_bytes(SOURCE)
                disk = Path(temporary) / "data.img"
                build_image(disk, 2 << 20, seed)
                fixture.disks[0] = (disk.read_bytes(), False)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reserved:
                reserved.bind(("127.0.0.1", 0))
                port = reserved.getsockname()[1]
            fixture.directives.append(f"forward udp {port} 5555 127.0.0.1")
        fixture.power_on(0, 0)
        config = fixture.write(folder)
        process = subprocess.Popen(
            [str(executable), str(config), "--headless", "--live", "--max", "2000000000",
             "--live-seconds", "180", "--serial-listen", "0"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        lines, listeners = [], queue.Queue()

        def collect():
            for line in process.stdout:
                lines.append(line)
                if line.startswith("SERIAL_LISTEN "):
                    listeners.put(line)
            listeners.put("")

        thread = threading.Thread(target=collect, daemon=True)
        thread.start()
        client = None
        transcript = []
        try:
            listener = listeners.get(timeout=30)
            uart = int(re.fullmatch(r"SERIAL_LISTEN 127\.0\.0\.1 (\d+) UART0\n", listener)[1])
            client = Console(uart, 40)
            startup = client.prompt().decode("utf-8")
            assert "Zentaji boot ROM v1" in startup
            transcript.append(startup)

            def command(text, expected):
                reply = client.command(text).decode("utf-8")
                transcript.append(reply)
                assert expected in reply, (text, reply)
                return reply

            if attached:
                command("net", "Zentaji Ethernet is attached.")
                lease = command("dhcp", "Lease accepted on Zentaji Ethernet")
                for expected in ("10.0.2.15", "255.255.255.0", "10.0.2.2", "10.0.2.3"):
                    assert expected in lease, lease
                command("net", "IPv4 10.0.2.15")
                command("dns localhost", "localhost resolves to 10.0.2.2")
                client.socket.sendall(b"ping 10.0.2.2\r")
                reply = bytearray()
                deadline = time.monotonic() + 20
                while b"reply from 10.0.2.2: seq" not in reply:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(bytes(reply))
                    client.socket.settimeout(remaining)
                    chunk = client.socket.recv(65536)
                    if not chunk:
                        raise ConnectionError(bytes(reply))
                    reply.extend(chunk)
                client.socket.sendall(b"\x03")
                reply.extend(client.prompt())
                assert b"received" in reply
                transcript.append(reply.decode("utf-8"))

                command("forge load main.zen", f"Forge loaded {len(SOURCE)} bytes")
                command("forge compile answer.pmf", "Forge wrote")
                command("boot answer.pmf", "The payload returned, r1 = $000000000000002A")
                command("dns localhost", "localhost resolves to 10.0.2.2")

                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
                    peer.settimeout(20)
                    peer.connect(("127.0.0.1", port))
                    peer.send(b"echo ZENTAJI-NAT-UDP\r")
                    output_bytes = bytearray()
                    while not output_bytes.endswith(b"pmf> "):
                        packet = peer.recv(65536)
                        output_bytes.extend(packet)
                        assert len(output_bytes) <= 16384, output_bytes
                    assert b"\nZENTAJI-NAT-UDP\r\n" in output_bytes, output_bytes
                    transcript.append(output_bytes.decode("utf-8"))
                # The network command's prompt is mirrored over serial too.
                client.prompt()
                command("echo UART-AFTER-UDP", "UART-AFTER-UDP")
            else:
                command("net", "Zentaji Ethernet is disconnected.")
                command("dhcp", "the machine description has no net attachment")
                command("echo UART-AFTER-NO-LINK", "UART-AFTER-NO-LINK")

            client.socket.sendall(b"halt\r")
            assert process.wait(timeout=30) == 0
        except ConnectionError:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            raise
        finally:
            if client:
                client.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            thread.join(timeout=3)
            (folder / "run.log").write_text("".join(lines), encoding="utf-8")
            (folder / "transcript.log").write_text("".join(transcript), encoding="utf-8")
        log = "".join(lines)
        assert "HOST_GPU_ERROR" not in log and "HOST_GPU_REFUSED" not in log
        assert re.search(r"^END steps=\d+ exit=0 powered=1 ", log, re.M), folder / "run.log"
        result[label] = True

    boot(False)
    boot(True)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PASS Zentaji ROM monitor disconnected Ethernet, DHCP, DNS, ICMP, payload return and UDP console")


if __name__ == "__main__":
    main()
