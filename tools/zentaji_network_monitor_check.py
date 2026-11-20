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


def check_crypto_vectors(client, log):
    """Keep the last guest output even if a long-running vector fails to return."""
    deadline = time.monotonic() + 1750
    client.socket.sendall(b"crypto vectors\r")
    reply = bytearray()
    with log.open("xb", buffering=0) as evidence:
        while not reply.endswith(b"\npmf> "):
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"The crypto vector run did not return to the prompt. See {log}")
            client.socket.settimeout(left)
            part = client.socket.recv(65536)
            if not part:
                raise ConnectionError(f"The crypto vector run lost its UART. See {log}")
            evidence.write(part)
            reply.extend(part)
            if len(reply) > 16 << 20:
                raise ValueError(f"The crypto vector transcript exceeded 16 MiB. See {log}")
    text = reply.decode("ascii")
    assert "crypto: 273 of 273 vectors PASS" in text, text[-4000:]
    assert "forged GCM tags REFUSED" in text and "negatives REFUSED" in text, text[-4000:]
    return text


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


def seed_mouse_motion(fixture):
    # The native input device consumes display pixels and reports wheel markers.
    # Repeat to admit a session at any phase of the scripted hand movement.
    for cycle in range(40):
        tick = cycle * 125_000_000
        for offset, wheel in ([(0, 1)] + [(i, 0) for i in range(1, 17)] +
                              [(16, 2)] + [(i, 0) for i in range(15, -1, -1)] + [(0, 3)]):
            tick += 250000
            fixture.input_feed(tick, "mouse", 300 + offset, 200 - offset, 0, wheel)


def check_mouse(command):
    command("mouse", "100%")
    reports = {}
    for percent in (100, 150, 50):
        command(f"mouse {percent}", f"now {percent}%")
        reply = command("boot MOUSE.PMF", "The payload returned, r1 =")
        word = int(re.search(r"r1 = \$([0-9A-F]{16})", reply)[1], 16)
        x, y = word >> 48, (word >> 32) & 65535
        extent = 16 * percent // 100
        # At half gain exactly eight of sixteen single-pixel movements advance
        # on each leg. The payload also requires the final position to match.
        moves = min(16, extent)
        expected = bytes([128 + extent, 128 - extent, moves, moves])
        assert (word & 0xffffffff).to_bytes(4, "big") == expected, (percent, reply)
        assert (x, y) == (300, 200), (percent,x,y)
        reports[str(percent)] = dict(start=[x, y], delta=[extent, -extent], moves=moves)
    command("mouse 9", "now 10%")
    command("mouse 1001", "now 1000%")
    command("mouse nope", "Nothing")
    command("mouse", "1000%")
    command("mouse 100", "now 100%")
    return reports


def check_gnss(command):
    from concurrent.futures import ThreadPoolExecutor
    from gnss_read_check import SENTENCE

    def send_fix(server, payload, release, gpsd=False):
        server.settimeout(15)
        with server.accept()[0] as peer:
            if gpsd:
                expected = b'?WATCH={"enable":true,"nmea":true}\n'
                request = bytearray()
                peer.settimeout(15)
                while len(request)<len(expected):
                    chunk=peer.recv(len(expected)-len(request))
                    if not chunk:
                        raise ConnectionError("GNSS client closed before its gpsd WATCH")
                    request.extend(chunk)
                assert request==expected,request
            # Split the checksum from its sentence across writes.
            peer.sendall(payload[:-4])
            peer.sendall(payload[-4:])
            release.wait(30)

    # Two independent receivers also test changing ports while a source is open.
    with socket.create_server(("127.0.0.1",0)) as first, socket.create_server(("127.0.0.1",2947)) as second:
        with ThreadPoolExecutor(max_workers=2) as pool:
            released = threading.Event()
            try:
                sent = pool.submit(send_fix, first, SENTENCE.replace(b"*47", b"*00") + SENTENCE, released)
                command(f"gnss source network 10.0.2.2:{first.getsockname()[1]}", "GNSS source: network")
                fix = command("gnss watch 2", "3D fix  48.1173000, 11.5166667")
                assert "alt 545 m" in fix and "sats 8" in fix and "12:35:19 UTC" in fix, fix
                assert "1 good frames, 1 bad" in fix, fix
                command("gnss source usb", "no USB serial receiver transport")
                command("boot GNSS.PMF", "$00000000474E5353")
                sent2 = pool.submit(send_fix, second, SENTENCE, released, True)
                command(f"gnss source network 10.0.2.2:{second.getsockname()[1]}", "GNSS source: network")
                raw = command("gnss raw 2", SENTENCE.decode("ascii").strip())
                assert "1 good frames, 0 bad" in raw, raw
            finally:
                released.set()
            sent.result(timeout=5)
            sent2.result(timeout=5)
    return dict(latitude_e7=481173000, longitude_e7=115166667, altitude_mm=545400,
                satellites=8, bad_checksums=1, receiver_ports=2, gpsd_watch=True, service_return="474E5353")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    parser.add_argument("--exchange", action="store_true", help="Exercise block upload and TCP send/receive")
    parser.add_argument("--sign-script", type=Path, help="Sign the generated input catalogs before running the native machine")
    parser.add_argument("--screenshot", action="store_true", help="Retrieve and verify the live header using the shared UDP screenshot tool")
    parser.add_argument("--crypto", type=Path, metavar="COMPILER", help="Build a Zentaji entropy ABI probe and check the shared crypto vector suite")
    parser.add_argument("--readonly-disk", action="store_true",
                        help="Check native raw block reads and write refusal on a read-only disk")
    parser.add_argument("--gnss", type=Path, metavar="COMPILER", help="Check network NMEA and the shared payload fix ABI")
    parser.add_argument("--mouse", type=Path, metavar="COMPILER",
                        help="Check native pointer movement through a separately compiled input client")
    parser.add_argument("--kept-shot", type=Path, metavar="COMPILER",
                        help="Capture a returning Neon payload over UART and acknowledged UDP")
    parser.add_argument("--cores", action="store_true", help="Exercise native secondary core launch, results and ownership")
    parser.add_argument("--trail", action="store_true",
                        help="Check the boot trail through two ROM resets and preserve foreign NVRAM")
    parser.add_argument("--web", action="store_true",
                        help="Check HTTP in both directions, verified TLS 1.3 and guest trust refusals")
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

    def compile_probe(compiler, source, name):
        output.mkdir(parents=True, exist_ok=True)
        probe_image = output / name
        stage = (json.loads(Path(str(image) + ".boot.json").read_text())["image_end"] + 4095) & -4096
        if args.sign_script:
            from zentaji_package import signatures
            signatures("pwsh.exe", args.sign_script.resolve(), executables=[compiler.resolve()])
        subprocess.run([str(compiler.resolve()), "--compile", str(ROOT / source),
                        "--entry-returns", "--wants-services", "--load-addr", hex(stage + 8),
                        "--stack-addr", hex(stage + 0x200000), "-o", str(probe_image)],
                       cwd=ROOT, env=dict(os.environ, PMF_ROOT=str(ROOT)), check=True, timeout=120)
        return Path(str(probe_image) + ".pmf").read_bytes()

    probe = compile_probe(args.crypto, "Zentaji/Tests/entropy_service.zentaji", "entropy-probe.zex") if args.crypto else None
    shot_probe = compile_probe(args.kept_shot, "Zentaji/Tests/kept_frame.zentaji", "kept-frame.zex") if args.kept_shot else None

    gnss_probe = compile_probe(args.gnss, "Zentaji/Tests/gnss_service.zentaji", "gnss-service.zex") if args.gnss else None
    mouse_probe = compile_probe(args.mouse, "Zentaji/Tests/mouse_motion.zentaji", "mouse-motion.zex") if args.mouse else None

    def boot(attached, no_entropy=False):
        label = "no-entropy" if no_entropy else ("nat" if attached else "disconnected")
        live_entropy = attached and not no_entropy and (probe is not None or args.web)
        folder = output / label
        if args.sign_script and folder.exists() and any(folder.iterdir()):
            raise ValueError(f"Choose a fresh directory for signed fixture evidence: {folder}")
        cores = 2
        if args.cores:
            cores = 1 if not attached else (2 if no_entropy else 4)
        fixture = Fixture(ram_size=128 << 20, cores=cores,
                          hostfiles=[["anvil.zex", bytearray(raw), False]],
                          display_modes=[(1024, 768, 60000)])
        fixture.net_attached = attached
        readonly = args.readonly_disk and not attached
        mouse_case = mouse_probe is not None and not attached
        if mouse_case:
            seed_mouse_motion(fixture)
        if attached or probe is not None or readonly or mouse_case:
            with tempfile.TemporaryDirectory(prefix="zentaji-net-") as temporary:
                seed = Path(temporary) / "source"
                seed.mkdir()
                (seed / "main.zen").write_bytes(SOURCE)
                if probe is not None:
                    (seed / "ENTROPY.PMF").write_bytes(probe)
                if gnss_probe is not None:
                    (seed / "GNSS.PMF").write_bytes(gnss_probe)
                if mouse_case:
                    (seed / "MOUSE.PMF").write_bytes(mouse_probe)
                if shot_probe is not None:
                    (seed / "FRAME.PMF").write_bytes(shot_probe)
                if args.web:
                    (seed / "ROOTS.PEM").write_bytes(web_root)
                disk = Path(temporary) / "data.img"
                build_image(disk, 2 << 20, seed)
                disk_bytes = disk.read_bytes()
                fixture.disks[0] = (disk_bytes, readonly)
        if attached:
            if live_entropy:
                fixture.directives.append("entropy host")
            if args.web and not no_entropy:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
                    reservation.bind(("127.0.0.1", 0))
                    http_port = reservation.getsockname()[1]
                fixture.directives.append(f"forward tcp {http_port} 8080 127.0.0.1")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reserved:
                reserved.bind(("127.0.0.1", 0))
                port = reserved.getsockname()[1]
            fixture.directives.append(f"forward udp {port} 5555 127.0.0.1")
        if args.trail:
            # A different owner uses the low half. In the attached case it also
            # holds a byte in the proposed trail region.
            nvram = bytearray(256)
            nvram[:128] = bytes(range(128))
            if attached:
                nvram[248] = 0xAD
            fixture.directives.append("nvram rtc.bin")
        fixture.power_on(0, 0)
        if args.cores and no_entropy:
            fixture.cores[1].state = "HALTED"
        config = fixture.write(folder)
        if args.trail:
            (folder / "rtc.bin").write_bytes(nvram)
        if args.sign_script:
            from zentaji_package import signatures, catalog
            inputs = [path for path in folder.iterdir() if path.is_file()]
            signatures("pwsh.exe", args.sign_script.resolve(), executables=[executable],
                       catalogs=[catalog(folder / "inputs.cat", inputs, True)])
        run_mode = ["--fast"] if mouse_case or args.exchange or args.screenshot or args.crypto or args.web else []
        budget = "300000000000" if args.crypto or args.web else ("4000000000" if args.screenshot else "2000000000")
        if mouse_case:
            budget = "30000000000"
        process = subprocess.Popen(
            [str(executable), str(config), *run_mode, "--headless", "--live", "--max", budget,
             "--live-seconds", "1800" if args.crypto or args.web else "180", "--serial-listen", "0"],
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

            if mouse_case:
                result["mouse"] = check_mouse(command)
            if args.cores:
                command("coretest run extra", "coretest takes exactly")
                command("coretest status", f"coretest fitted={cores} owned=0")
                if cores == 1:
                    command("coretest run", "needs a fitted secondary core")
                    result["coretest_single_refused"] = True
                elif no_entropy:
                    before = command("mmio FFFF000000030140 7", "FFFF000000030140: 0000000000000003")
                    command("coretest run", "occupied or staged secondary")
                    command("coretest stop", "owned=0")
                    assert command("mmio FFFF000000030140 7", "pmf> ") == before
                    result["coretest_foreign_preserved"] = True
                else:
                    def check_cores(round_no):
                        text = command("coretest run", f"16 challenge rounds on {cores-1} secondary")
                        rows = re.findall(r"core=(\d+) state=(\d+) argument=([0-9A-F]{16}) exit=([0-9A-F]{16})", text)
                        assert len(rows) == cores - 1, text
                        for expected_core,(core,state,argument,response) in enumerate(rows,1):
                            arg = round_no * 257 + expected_core * 17
                            assert (int(core),int(state),int(argument,16),int(response,16)) == (expected_core,3,arg,arg*3+expected_core)
                    check_cores(16)
                    command("coretest stop", "owned=0")
                    for core in range(1,cores):
                        address = 0xFFFF000000030100 + core * 64
                        words = re.findall(r"(?m)^[0-9A-F]{16}: ([0-9A-F]{16})\r?$",command(f"mmio {address:X} 7", "pmf> "))
                        assert words == ["0"*16]*7, words
                    check_cores(32)
                    result["coretest_challenge_rounds"] = 32
                    result["coretest_secondaries"] = cores-1
            if args.trail:
                def rtc_bytes(addr, count):
                    reply = command(f"mmio {addr:X} {count:X}", "pmf> ")
                    values = re.findall(r"(?m)^([0-9A-F]{16}): ([0-9A-F]{16})\r?$", reply)
                    assert [int(a,16) for a,_ in values] == list(range(addr,addr+8*count,8))
                    return b"".join(int(v,16).to_bytes(8,"little") for _,v in values)

                if attached:
                    command("trail", "NVRAM trail area is occupied")
                    assert rtc_bytes(0xFFFF000000060100,32) == nvram
                    result["trail_foreign_preserved"] = True
                else:
                    def entries(text, which):
                        rows = re.findall(rf"(?m)^TRAIL {which} ([0-9A-F]{{4}}) (\d+) ms  (.+?)\r?$", text)
                        return [(int(code,16),int(ms),name) for code,ms,name in rows]

                    previous = []
                    for generation in (1,2,3):
                        if generation > 1:
                            command("reset", "Zentaji boot ROM v1")
                        reply = command("trail", f"This boot (boot {generation}), TRAIL 0")
                        rows = entries(reply,0)
                        assert [e[0] for e in rows] == list(range(0x5A01,0x5A08)), reply
                        times = [e[1] for e in rows]
                        assert times == sorted(times) and times[-1] > times[0], times
                        assert rows[-1][2] == "Monitor ready"
                        assert entries(reply,1) == previous
                        if previous:
                            assert f"The previous boot (boot {generation-1}) FINISHED" in reply
                        else:
                            assert "no record of a previous boot" in reply
                        previous = rows
                    assert rtc_bytes(0xFFFF000000060100,16) == nvram[:128]
                    result["trail_reset_generations"] = 3
            if readonly:
                from anvil import read_map
                from anvil_readback import parse_readback

                stage_addr = read_map(command("map", "stage a file at")).stage
                command("disk info", "native virtual disk")
                command(f"disk write 0 {stage_addr:X}", "read-only. No blocks were written")
                command(f"mmc read 0 {stage_addr:X}", "512 bytes read")
                reply = command(f"readback {stage_addr:X} 200", "readback end")
                assert parse_readback(reply, stage_addr, 512) == disk_bytes[:512]
                result["readonly_sector_sha256"] = hashlib.sha256(disk_bytes[:512]).hexdigest()
            if probe is not None:
                expected = 0xA1 if live_entropy else 0xA0
                command("boot ENTROPY.PMF", f"The payload returned, r1 = ${expected:016X}")
                result["entropy_" + label] = expected
                if attached and not no_entropy:
                    vectors = check_crypto_vectors(client, folder / "crypto-vectors.log")
                    transcript.append(vectors)
                    result["crypto_vectors"] = 273
            if no_entropy:
                command("dhcp", "Lease accepted")
                command("settings set tls.roots 1:/ROOTS.PEM", "pmf> ")
                command("tls reload", "1 roots registered")
                with web_test_peer(web_body, keys / "good") as peer:
                    text = command(f"https get https://localhost:{peer.server_port}/unseeded", "FAILED")
                    assert "random generator" in text and not peer.requests
                result["tls_without_entropy_refused"] = True
            elif attached:
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
                if args.cores:
                    command("coretest", f"coretest fitted={cores} owned=0")
                    result["coretest_released_on_payload"] = True

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
                if args.kept_shot:
                    from unittest.mock import patch
                    from board_run import parse_shot_header
                    from pmfshot import decode, png
                    import pmfshot_wifi

                    command("shot status","holds no picture")
                    command("shot now","picture number 1")
                    command("shot arm","ONE run")
                    command("boot FRAME.PMF","$123456780000002A")
                    status = command("shot status","not armed")
                    assert parse_shot_header(status)["seq"] == 2, status
                    command("boot answer.pmf","$000000000000002A")
                    text = command("shot","END ")
                    header = parse_shot_header(text)
                    assert header and header["seq"] == 2 and header["who"] == 1
                    assert header["src_name"] == "zentaji" and header["tier_name"] == "vulkan"
                    assert header["x0"] == 0x123456780000002A
                    w,h,rows = decode(text)
                    assert (w,h) == (1024,768) and header["bytes"] == 4*w*h
                    green, red = bytes((0,255,0)),bytes((255,0,0))
                    normal = green*w
                    marked = green*128 + red*128 + green*(w-256)
                    for y,row in enumerate(rows):
                        assert row == (marked if 96<=y<160 else normal), f"kept frame mismatch in row {y}"
                    (folder/"kept.png").write_bytes(png(w,h,rows))
                    with patch.object(pmfshot_wifi,"PORT",port):
                        other,udp_rows=pmfshot_wifi.grab_kept_reliable("127.0.0.1",timeout=90)
                    assert udp_rows==rows and all(header[k]==v for k,v in other.items()), other
                    transcript.append(client.prompt().decode("ascii"))
                    command("shot arm","ONE run")
                    command("boot answer.pmf","No new picture")
                    assert parse_shot_header(command("shot status","not armed"))["seq"] == 2
                    result["kept"] = dict(sequence=2, return_register=header["x0"], bytes=header["bytes"],
                                          rgb_sha256=hashlib.sha256(b"".join(rows)).hexdigest())
                if gnss_probe is not None:
                    result["gnss"] = check_gnss(command)
                if args.web:
                    result["web"] = check_web_peers(command, http_port, keys, web_body)
                command("echo UART-AFTER-UDP", "UART-AFTER-UDP")
            else:
                command("net", "Zentaji Ethernet is disconnected.")
                command("dhcp", "the machine description has no net attachment")
                command("echo UART-AFTER-NO-LINK", "UART-AFTER-NO-LINK")

            client.socket.sendall(b"halt\r")
            stop_reply = bytearray()
            stop_deadline = time.monotonic() + 30
            while b"Anvil stopped." not in stop_reply:
                client.socket.settimeout(max(0.1, stop_deadline - time.monotonic()))
                chunk = client.socket.recv(4096)
                if not chunk:
                    break
                stop_reply.extend(chunk)
                if b"\npmf> " in stop_reply or time.monotonic() >= stop_deadline:
                    break
            transcript.append(stop_reply.decode("utf-8", errors="replace"))
            assert b"Anvil stopped." in stop_reply, stop_reply
            assert process.wait(timeout=90 if mouse_case else 30) == 0
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

    if args.web:
        from zentaji_web_peer import check_web_peers, web_test_identity, web_test_peer
        with tempfile.TemporaryDirectory(prefix="zentaji-tls-") as private_keys:
            keys = Path(private_keys)
            web_root = web_test_identity(keys / "good", "localhost")
            web_test_identity(keys / "untrusted", "localhost")
            web_body = ("Zentaji peer " + os.urandom(16).hex()).encode("ascii")
            boot(False)
            boot(True, no_entropy=True)
            boot(True)
    else:
        boot(False)
        boot(True)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.sign_script:
        from zentaji_package import signatures, catalog
        catalogs = []
        labels = ["nat", "disconnected"]
        if args.web:
            labels.append("no-entropy")
        for label in labels:
            folder = output / label
            evidence = [folder / "run.log", folder / "transcript.log"]
            if label == "nat" and args.screenshot:
                evidence.append(folder / "pr.png")
            if label == "nat" and args.kept_shot:
                evidence.append(folder / "kept.png")
            if label == "nat" and args.crypto:
                evidence.append(folder / "crypto-vectors.log")
            catalogs.append(catalog(folder / (label + ".cat"), evidence, True))
        catalogs.append(catalog(output / "results.cat", [output / "result.json"], True))
        signatures("pwsh.exe", args.sign_script.resolve(), catalogs=catalogs)
    print("PASS Zentaji ROM monitor disconnected Ethernet, DHCP, DNS, ICMP, payload return and UDP console")
    if args.exchange:
        print("PASS network block upload with UART readback and bidirectional TCP")


if __name__ == "__main__":
    main()
