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


def check_exchange(command, client, port, folder):
    from unittest.mock import patch
    from anvil import read_map
    from anvil_readback import parse_readback
    import anvil_wifi_update

    address = read_map(command("map", "stage a file at")).stage
    data = bytes((i * 71 + i // 256) & 255 for i in range(1537))
    upload = folder / "from-host.bin"
    upload.write_bytes(data)
    with patch.object(anvil_wifi_update, "PORT", port):
        assert anvil_wifi_update.main(["--receive-only", "127.0.0.1", str(upload)]) == 0
    # The map and upload prompts can share a single UART read.
    mirrored = client.prompt()
    if mirrored.count(b"pmf> ") < 2:
        client.prompt()
    answer = command(f"readback {address:X} {len(data):X}", "pmf> ")
    assert parse_readback(answer, address, len(data)) == data

    with socket.create_server(("127.0.0.1", 0)) as server:
        server.settimeout(10)
        command(f"tcp connect 10.0.2.2 {server.getsockname()[1]}", "SYN sent")
        with server.accept()[0] as connection:
            connection.settimeout(10)
            deadline = time.monotonic() + 10
            while "ESTABLISHED" not in command("tcp status", "pmf> ").upper():
                if time.monotonic() >= deadline:
                    raise TimeoutError("Guest TCP connection did not reach ESTABLISHED")
            command("tcp send TCP-TO-HOST", "Sent 13 bytes")
            incoming = bytearray()
            while len(incoming) < 13:
                part = connection.recv(13 - len(incoming))
                if not part:
                    raise ConnectionError("Guest closed TCP before sending its line")
                incoming.extend(part)
            assert incoming == b"TCP-TO-HOST\r\n"
            connection.sendall(b"HOST-TO-TCP")
            deadline = time.monotonic() + 10
            while "HOST-TO-TCP" not in command("tcp recv 11", "pmf> "):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Guest did not receive the host TCP message")
            command("tcp close", "pmf> ")
    return {"wb_bytes": len(data), "wb_sha256": hashlib.sha256(data).hexdigest(),
            "tcp_sent": len(incoming), "tcp_received": 11}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    parser.add_argument("--exchange", action="store_true", help="Exercise block upload and TCP send/receive")
    parser.add_argument("--sign-script", type=Path, help="Sign the generated input catalogs before running the native machine")
    parser.add_argument("--screenshot", action="store_true", help="Retrieve and verify the live header using the shared UDP screenshot tool")
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
        if args.sign_script and folder.exists() and any(folder.iterdir()):
            raise ValueError(f"Choose a fresh directory for signed fixture evidence: {folder}")
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
        if args.sign_script:
            from zentaji_package import signatures, catalog
            inputs = [path for path in folder.iterdir() if path.is_file()]
            signatures("pwsh.exe", args.sign_script.resolve(), executables=[executable],
                       catalogs=[catalog(folder / "inputs.cat", inputs, True)])
        run_mode = ["--fast"] if args.exchange or args.screenshot else []
        process = subprocess.Popen(
            [str(executable), str(config), *run_mode, "--headless", "--live", "--max", "4000000000" if args.screenshot else "2000000000",
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
                    peer.sendto(b"echo ZENTAJI-NAT-UDP\r", ("127.0.0.1", port))
                    output_bytes = bytearray()
                    while not output_bytes.endswith(b"pmf> "):
                        packet = peer.recv(65536)
                        output_bytes.extend(packet)
                        assert len(output_bytes) <= 16384, output_bytes
                    assert b"\nZENTAJI-NAT-UDP\r\n" in output_bytes, output_bytes
                    transcript.append(output_bytes.decode("utf-8"))
                    if args.exchange:
                        client.prompt()  # echo also mirrored its prompt to the UART
                        result["exchange"] = check_exchange(command, client, port, folder)
                # The network command's prompt is mirrored over serial too.
                if not args.exchange:
                    client.prompt()
                if args.screenshot:
                    from unittest.mock import patch
                    from pmfshot import png
                    from zentaji_package_check import screen_check
                    import pmfshot_wifi
                    with patch.object(pmfshot_wifi, "PORT", port):
                        frame = pmfshot_wifi.grab_reliable("127.0.0.1", timeout=90)
                    assert frame is not None, "No CRC-verified UDP screenshot"
                    width, height, rows = frame
                    assert (width, height) == (1024, 768)
                    capture = folder / "pr.png"
                    capture.write_bytes(png(width, height, rows))
                    result["udp_screenshot_phase"] = screen_check(capture)
                    transcript.append(client.prompt().decode("utf-8"))
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
    if args.sign_script:
        from zentaji_package import signatures, catalog
        catalogs = []
        for label in ("nat", "disconnected"):
            folder = output / label
            evidence = [folder / "run.log", folder / "transcript.log"]
            if label == "nat" and args.screenshot:
                evidence.append(folder / "pr.png")
            catalogs.append(catalog(folder / (label + ".cat"), evidence, True))
        catalogs.append(catalog(output / "results.cat", [output / "result.json"], True))
        signatures("pwsh.exe", args.sign_script.resolve(), catalogs=catalogs)
    print("PASS Zentaji ROM monitor disconnected Ethernet, DHCP, DNS, ICMP, payload return and UDP console")
    if args.exchange:
        print("PASS network block upload with UART readback and bidirectional TCP")


if __name__ == "__main__":
    main()
