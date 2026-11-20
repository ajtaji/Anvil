"""Boot the extracted Linux tester ZIP and exercise returning network programs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib

from zentaji_web_peer import check_payload_peers, web_test_identity, web_test_peer


def verify(archive, probe, evidence):
    from pmfshot import decode, png
    from zentaji_package_check import screen_check_bgra

    evidence.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="zentaji tester ", dir=Path.home()) as temporary:
        root = Path(temporary)
        # Python's extractor does not apply Unix permissions from ZIP metadata.
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                path = Path(member.filename)
                assert len(path.parts) == 2 and not path.is_absolute() and ".." not in path.parts
                mode = member.external_attr >> 16
                assert member.create_system == 3 and mode in (0o100755, 0o100644)
                extracted = Path(zipped.extract(member, root))
                extracted.chmod(mode & 0o777)
        folder, = root.iterdir()
        build = int(re.fullmatch(r"Zentaji-Anvil(\d+)-linux-x86_64", folder.name)[1])
        sys.path.insert(0, str(folder))
        from zen_console import Console

        result = {"build": build, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                  "image_sha256": hashlib.sha256((folder / "anvil.zex").read_bytes()).hexdigest()}
        env = os.environ.copy()
        if env.get("WSL_DISTRO_NAME") and Path("/dev/dxg").exists():
            env.setdefault("GALLIUM_DRIVER", "d3d12")
        info = subprocess.check_output([folder / "zenwin", folder / "machine.txt", "--gpu-info"], env=env, text=True, timeout=60)
        (evidence / "gpu-info.log").write_text(info)
        assert "hardware=1" in info and "compute=1 int64=1 fp64=1" in info, info
        result["renderer"] = re.search(r"(?m)^renderer=(.+)$", info)[1]
        for boot in ("first", "restart"):
            output = evidence / (boot + ".log")
            console = None
            with output.open("wb") as log, (evidence / (boot + "-uart.log")).open("wb") as transcript:
                launch = [folder / "start-zentaji.sh"]
                if boot == "first":
                    launch.append("--headless")
                process = subprocess.Popen(launch, cwd=folder,
                                           stdout=log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 60
                    while True:
                        with output.open("rb") as src:
                            port = re.search(rb"SERIAL_LISTEN 127\.0\.0\.1 (\d+) UART0", src.read(2048))
                        if port:
                            break
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError("The extracted launcher did not announce its UART")
                        time.sleep(0.1)
                    console = Console(int(port[1]), 90)
                    startup = console.prompt()
                    transcript.write(startup)
                    assert b"Zentaji boot ROM" in startup and f"build {build} ".encode() in startup

                    def command(line, expected):
                        reply = console.command(line)
                        transcript.write(reply)
                        transcript.flush()
                        assert expected.encode() in reply, (line, reply[-1200:])
                        return reply.decode("ascii")

                    command("dhcp", "Lease accepted")
                    command("dns localhost", "10.0.2.2")
                    if boot == "first":
                        stage = int(re.search(r"stage a file at\s+([0-9A-F]+)", command("map", "stage a file at"))[1], 16)

                        def store(name, raw):
                            line = f"receive {stage:X} {len(raw):X} {zlib.crc32(raw):08X}\r"
                            console.socket.sendall(line.encode("ascii"))
                            reply = bytearray()
                            while b"rdy\r\n" not in reply:
                                chunk = console.socket.recv(4096)
                                if not chunk or reply.endswith(b"pmf> "):
                                    raise RuntimeError("Guest refused serial upload")
                                reply.extend(chunk)
                            console.socket.sendall(raw)
                            assert f"Received all {len(raw)} bytes".encode() in console.prompt()
                            command(f"save {name} {stage:X} {len(raw):X}", "Saved")

                        keys = root / "peer"
                        keys.mkdir()
                        ca = web_test_identity(keys / "good", "localhost")
                        web_test_identity(keys / "untrusted", "localhost")
                        store("PAYNET.PMF", probe.read_bytes())
                        store("ROOTS.PEM", ca)
                        result["payload_network"] = check_payload_peers(command, keys)
                        screen_reply = console.command("screenshot")
                        width, height, rows = decode(screen_reply.decode("ascii"))
                        picture = evidence / "screen.png"
                        picture.write_bytes(png(width, height, rows))
                        assert (width, height) == (1024, 768)
                        rgb = b"".join(rows)
                        bgra = bytearray(b"\xff" * (width * height * 4))
                        bgra[0::4], bgra[1::4], bgra[2::4] = rgb[2::3], rgb[1::3], rgb[::3]
                        result["sparkle_phase"] = screen_check_bgra(bgra)
                    else:
                        token = secrets.token_bytes(4)
                        with web_test_peer(token) as server:
                            command(f"settings set test.network P{server.server_port}", "Set test.network")
                            command("boot PAYNET.PMF", "$4E455400" + token.hex().upper())
                            assert server.requests == [("/payload", "localhost", "HTTP")]
                        result["persistent_network_program"] = True
                    console.socket.sendall(b"halt\r")
                    console.socket.settimeout(30)
                    stopped = bytearray()
                    while b"Anvil stopped." not in stopped:
                        chunk = console.socket.recv(4096)
                        if not chunk:
                            break
                        stopped.extend(chunk)
                    transcript.write(stopped)
                    assert b"Anvil stopped." in stopped, stopped
                    assert process.wait(timeout=60) == 0
                finally:
                    if console:
                        console.close()
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=20)
            text = output.read_text(errors="replace")
            assert re.search(r"^END steps=\d+ exit=0 powered=1 ", text, re.M)
            assert "HOST_GPU_REFUSED" not in text and "HOST_GPU_ERROR" not in text
            if boot == "first":
                serial_hex = re.search(r"^SERIAL0 ([A-F0-9]+)$", text, re.M)[1]
                assert screen_reply in bytes.fromhex(serial_hex)
            else:
                result["windowed_restart"] = True
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "probe", "evidence"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    verify(args.archive.resolve(), args.probe.resolve(), args.evidence.resolve())
