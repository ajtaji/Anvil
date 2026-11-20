"""Check relocated package boot, guest commands and cold-boot disk persistence.

This is a correctness check. It records no performance measurements and runs
no host compiler or Python CPU/device model.
"""
import argparse
import ctypes
from ctypes import wintypes
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import zipfile

from anvilfs_image import read_entries
from zentaji_package import FILES, catalog, digest, signatures
from zentaji_graphical_boot_check import assert_logo


class Child:
    """Hold the specific process started by this check, never a reused PID."""
    def __init__(self, pid):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.OpenProcess(0x100000 | 0x1000 | 1, False, pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "Package emulator exited before observation")

    def alive(self):
        result = self.api.WaitForSingleObject(self.handle, 0)
        if result not in (0, 258):
            raise OSError(ctypes.get_last_error(), "Cannot observe package emulator")
        return result == 258

    def wait(self, seconds):
        if self.api.WaitForSingleObject(self.handle, int(seconds * 1000)) != 0:
            raise TimeoutError("Package emulator did not halt")
        code = wintypes.DWORD()
        if not self.api.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise OSError(ctypes.get_last_error(), "Cannot read emulator exit status")
        assert code.value == 0, code.value

    def close(self):
        if self.alive():
            self.api.TerminateProcess(self.handle, 1)
            self.api.WaitForSingleObject(self.handle, 10000)
        self.api.CloseHandle(self.handle)


def screen_check(path):
    from PIL import Image
    frame = Image.open(path).convert("RGBA")
    assert frame.size == (1024, 768), frame.size
    raw = frame.tobytes("raw", "BGRA")
    for phase in range(8):
        try:
            assert_logo(raw, 1024, phase)
            break
        except AssertionError:
            continue
    else:
        raise AssertionError("Package did not present the shared Anvil logo")
    assert all(raw[(114 * 1024 + x) * 4:(114 * 1024 + x + 1) * 4] ==
               bytes((48, 148, 255, 255)) for x in range(24, 1000)), "Missing header rule"
    return phase


def check_screenshot(client, keep, transcript):
    from pmfshot import decode, png

    picture = client.command("screenshot").decode("ascii")
    transcript.append(picture)
    width, height, rows = decode(picture)
    assert (width, height) == (1024, 768)
    capture = keep / "guest-screenshot.png"
    capture.write_bytes(png(width, height, rows))
    return screen_check(capture)


def check_automation(client, transcript, container):
    from anvil_readback import parse_readback

    def command(line):
        reply = client.command(line).decode("ascii")
        transcript.append(reply)
        return reply

    listing = command("programs")
    assert re.search(r"^  SAVED +[0-9]+ bytes +1:/SAVED\.PMF\r?$", listing, re.M), listing
    launched = command("sAvEd")
    assert "Running 1:/SAVED.PMF" in launched and "r1 = $000000000000002A" in launched, launched
    loaded = command("load SAVED.PMF")
    match = re.search(r"Loaded ([0-9]+) bytes into memory, filling ([0-9A-F]+)", loaded)
    assert match and int(match[1]) == len(container), loaded
    address = int(match[2], 16)
    reply = command(f"readback {address:X} {len(container):X}")
    assert parse_readback(reply, address, len(container)) == container
    # Cross the shared encoder's 720-byte block and exercise final padding.
    count = 725
    assert "!!" not in command(f"fill.b {address:X} A5 {count:X}")
    reply = command(f"readback {address:X} {count:X}")
    assert parse_readback(reply, address, count) == bytes([0xA5]) * count
    assert "nothing was read" in command(f"readback {address:X} 0").lower()
    assert "AUTOMATION-DONE" in command("echo AUTOMATION-DONE").splitlines()
    print("PASS program discovery and launch, verified binary readback, guest screenshot and prompt", flush=True)
    return dict(payload_readback_bytes=len(container), multiblock_bytes=count)


def check_machine_diagnostics(client, transcript):
    def command(line):
        reply = client.command(line).decode("ascii")
        transcript.append(reply)
        return reply

    table = command("mmio FFFF000000010018")
    assert "FFFF000000010018: 0000000010000000" in table, table
    uart = command("mmio FFFF000000100000 2")
    assert "FFFF000000100000: 0000000000010011" in uart, uart
    assert "FFFF000000100008: " in uart, uart
    for bad, refusal in (("1", "eight-byte-aligned"), ("100000", "outside a fitted device"),
                         ("FFFF00000010FFF8 2", "outside a fitted device"),
                         ("FFFF000000100000 41", "count"), ("FFFF000000100000 1junk", "count")):
        assert refusal in command("mmio " + bad)

    capability = command("mmio FFFF000000090060")
    assert "FFFF000000090060: 0000000000000001" in capability, capability

    old = int(re.search(r"UART0 baud: (\d+)", command("baud"))[1])
    rate = 1500000 if old != 1500000 else 3000000

    def confirm(value):
        client.socket.sendall(f"baud {value}\r\r".encode("ascii"))
        reply = client.prompt().decode("ascii")
        transcript.append(reply)
        assert f"UART0 baud kept: {value}" in reply, reply

    confirm(rate)
    assert f"FFFF000000100060: {rate:016X}" in command("mmio FFFF000000100060")
    assert f"UART0 baud restored: {rate}" in command(f"baud {old}")
    assert f"UART0 baud: {rate} " in command("baud")
    confirm(old)
    assert "!!" in command("baud 15")
    assert f"UART0 baud: {old} " in command("baud")
    # A plain payload gives up the scanout lease. The new lease starts its
    # count at zero, and the first returned prompt can precede the GPU latch.
    deadline = time.monotonic() + 30
    while True:
        reply = command("vkstat")
        assert "Display: 1024x768, buffers: " in reply and "error: 0, lost: 0" in reply, reply
        assert int(re.search(r"Native Vulkan queue sequence: (\d+)", reply)[1]) > 0, reply
        presents = int(re.search(r"Completed presents: (\d+)", reply)[1])
        if presents:
            break
        if time.monotonic() >= deadline:
            raise AssertionError("The returned monitor never latched a frame: " + reply)
        time.sleep(0.5)
    assert "Screen on: 1024x768 native Vulkan" in command("screen status")
    assert "Screen off." in command("screen off")
    assert "FFFF0000000C0010: 0000000000000000" in command("mmio FFFF0000000C0010")
    assert "Screen off: " in command("screen")
    assert "!!" in command("screenshot")
    assert "Screen on." in command("screen on")
    assert "FFFF0000000C0010: 0000000000000001" in command("mmio FFFF0000000C0010")
    return dict(screen_power_cycle=True, confirmed_baud=rate, restored_baud=old, completed_presents=presents)


def check_serial_loaders(client, transcript):
    from anvil_readback import parse_readback
    import zlib

    def command(line):
        reply = client.command(line).decode("ascii")
        transcript.append(reply)
        return reply

    def transfer(line, ready, payload):
        client.socket.sendall(line.encode("ascii") + b"\r")
        first = bytearray()
        deadline = time.monotonic() + client.timeout
        while ready not in first:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for {ready!r}")
            client.socket.settimeout(remaining)
            packet = client.socket.recv(4096)
            if not packet:
                raise ConnectionError("UART closed before transfer")
            first.extend(packet)
            if first.endswith(b"pmf> "):
                raise AssertionError(first.decode("ascii"))
        client.socket.sendall(payload)
        reply = (first + client.prompt()).decode("ascii")
        transcript.append(reply)
        return reply

    info = command("board")
    for text in ("RAM bytes: 268435456", "CPU cores: 2", "Current core: 0", "Boot source: host file"):
        assert text in info, info
    assert "Nominal machine clock: 100000000 Hz" in command("clock")
    assert "read-only" in command("clock 48000000")
    loaded = command("load SAVED.PMF")
    address = int(re.search(r"filling ([0-9A-F]+)", loaded)[1], 16)
    data = bytes((i * 79) & 255 for i in range(1031))
    header = f"receive {address:X} {len(data):X} {zlib.crc32(data):08X}"
    reply = transfer(header, b"rdy\r\n", data)
    assert "Received all 1031 bytes" in reply and "ok" in reply.splitlines(), reply
    assert parse_readback(command(f"readback {address:X} {len(data):X}"), address, len(data)) == data

    def record(kind, target, data):
        raw = bytes([len(data) + 5]) + target.to_bytes(4, "big") + data
        return f"S{kind}{raw.hex()}{(~sum(raw)) & 255:02x}".upper().encode()

    fragment = b"ANVIL\0UART\xff"
    # S7 terminates immediately. No trailing newline should be offered as a command.
    stream = record(3, address, fragment) + b"\r\n" + record(7, address, b"")
    reply = transfer("loads", b"abandons it.\r\n", stream)
    assert f"{len(fragment)} bytes in all" in reply and "!!" not in reply, reply
    assert parse_readback(command(f"readback {address:X} {len(fragment):X}"), address, len(fragment)) == fragment
    return dict(block_bytes=len(data), srecord_bytes=len(fragment))


def check_memory_commands(client, transcript, container):
    import hashlib
    from anvil_readback import parse_readback

    def command(line):
        reply = client.command(line).decode("ascii")
        transcript.append(reply)
        return reply

    loaded = command("load SAVED.PMF")
    address = int(re.search(r"filling ([0-9A-F]+)", loaded)[1], 16)
    for name, algorithm in (("sha1sum", hashlib.sha1), ("sha256sum", hashlib.sha256)):
        reply = command(f"{name} {address:X} {len(container):X}")
        assert f"The {name} is {algorithm(container).hexdigest()}" in reply, reply

    # These two commands own the input line until the operator explicitly quits.
    for name, values, expected in (("mm", ("3C", "4D"), b"\x3c\x4d"),
                                    ("nm", ("7A", "A5"), b"\xa5\x4d")):
        client.socket.sendall(("\r".join([f"{name}.b {address:X}", *values, "q"]) + "\r").encode("ascii"))
        reply = client.prompt().decode("ascii")
        transcript.append(reply)
        assert "Left interactive modify." in reply, reply
        assert parse_readback(command(f"readback {address:X} 2"), address, 2) == expected

    assert "!!" not in command(f"fill.b {address+32:X} CC 8")
    reply = command(f"mtest {address:X} {address+31:X} 12345678 1")
    assert "mtest passed: 1 iteration over 8 words, no errors found." in reply, reply
    after = parse_readback(command(f"readback {address:X} 20"), address, 32)
    assert after == bytes.fromhex("78563412") * 8
    assert parse_readback(command(f"readback {address+32:X} 8"), address+32, 8) == bytes([0xCC]) * 8
    assert "Nothing was tested" in command(f"mtest {address:X} {address-1:X}")
    return dict(sha1=hashlib.sha1(container).hexdigest(), sha256=hashlib.sha256(container).hexdigest(),
                mtest_words=8, interactive_modes=["mm.b", "nm.b"])


def check_file_transfer(client, transcript, keep):
    """Run against an independent TFTP server (pip install tftpy==0.8.7)."""
    from concurrent.futures import ThreadPoolExecutor
    import tftpy
    from anvil_readback import parse_readback

    def command(line):
        reply = client.command(line).decode("ascii")
        transcript.append(reply)
        return reply

    root = keep / "tftp-root"
    root.mkdir()
    # Two full blocks require a third, empty DATA packet to finish each direction.
    payload = bytes((index * 53 + index // 256) & 255 for index in range(1024))
    (root / "FROMHOST.BIN").write_bytes(payload)
    (root / "EMPTY.BIN").write_bytes(b"")
    server = tftpy.TftpServer(str(root))
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(server.listen, "127.0.0.1", 69, 1)
        try:
            if not server.is_running.wait(3):
                worker.result(timeout=1)
                raise RuntimeError("The loopback TFTP server failed to start")
            assert "Set net.server to 10.0.2.2" in command("settings set net.server 10.0.2.2")
            fetched = command("get FROMHOST.BIN")
            location = re.search(r"Fetched 1024 bytes into memory, filling ([0-9A-F]+)", fetched)
            assert location, fetched
            address = int(location[1], 16)
            assert parse_readback(command(f"readback {address:X} 400"), address, 1024) == payload
            assert "Saved" in command(f"save ROUND.BIN {address:X} 400")
            assert "!!" not in command(f"fill.b {address:X} 00 400")
            assert "Loaded 1024 bytes" in command(f"load ROUND.BIN {address:X}")
            sent = command(f"put TOHOST.BIN {address:X} 400")
            assert "Sent 1024 bytes" in sent, sent
            assert (root / "TOHOST.BIN").read_bytes() == payload
            for reply in (fetched, sent):
                tid = re.search(r"The server answered from port (\d+)", reply)
                assert tid and int(tid[1]) != 69, reply
            assert "is EMPTY" in command("get EMPTY.BIN")
            assert "server refused" in command("get MISSING.BIN")
            assert "TRANSFER-DONE" in command("echo TRANSFER-DONE").splitlines()
        finally:
            server.stop(now=True)
        worker.result(timeout=5)
    print("PASS host-to-disk-to-host TFTP transfer, exact bytes, empty and missing files", flush=True)
    return dict(bytes=len(payload), sha256=digest(root / "TOHOST.BIN"))


def check(archive, keep, signer, powershell, automation=False, transfers=False, memory=False, loaders=False, diagnostics=False, autoboot=False):
    archive, keep, signer = (Path(p).resolve() for p in (archive, keep, signer))
    if keep.exists():
        raise ValueError("Choose a new evidence directory; existing disks must be preserved")
    signatures(powershell, signer, catalogs=[catalog(Path(str(archive) + ".cat"), [archive])])
    # The odd pathname proves that neither repository-relative paths nor shell
    # quoting assumptions are needed by the tester launcher.
    folder = keep / "Relocated O'Brien & tester"
    folder.mkdir(parents=True)
    with zipfile.ZipFile(archive) as zipped:
        expected = set(FILES) | {"package.cat"}
        assert len(zipped.namelist()) == len(expected) and set(zipped.namelist()) == expected
        for name in (*FILES, "package.cat"):
            with zipped.open(name) as src, (folder / name).open("xb") as dst:
                shutil.copyfileobj(src, dst)
    immutable = [folder / name for name in FILES]

    def verify():
        signatures(powershell, signer, executables=[folder / "zenwin.exe"],
                   catalogs=[catalog(folder / "package.cat", immutable)])

    verify()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ram_bytes"] == 256 << 20 and manifest["cores"] == 2
    assert not (folder / "data.img").exists()
    spec = importlib.util.spec_from_file_location("package_console", folder / "zen_console.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = dict(archive_sha256=digest(archive), anvil_build=manifest["anvil_build"],
                  performance_measured=False, boots=[])

    def boot(label, commands):
        verify()
        # A detached Windows child can retain inherited pipe handles. Observe
        # the launcher's process exit, not EOF on a pipe the emulator may own.
        launch_log = keep / (label + "-launcher.log")
        with launch_log.open("wb") as output:
            run = subprocess.run(["cmd.exe", "/d", "/c", "Start-Zentaji.cmd", "--headless"],
                                 cwd=folder, stdout=output, stderr=subprocess.STDOUT,
                                 timeout=30, creationflags=0x08000000)
        assert run.returncode == 0, launch_log.read_text(errors="replace")
        child = Child(int((folder / "zentaji.pid").read_text()))
        client, transcript = None, []
        try:
            deadline = time.monotonic() + 60
            while True:
                log = (folder / "zentaji.log").read_text(encoding="utf-8", errors="replace")
                match = re.search(r"^SERIAL_LISTEN 127\.0\.0\.1 (\d+) UART0$", log, re.M)
                if match:
                    break
                assert child.alive(), log
                if time.monotonic() >= deadline:
                    raise TimeoutError("Package UART listener did not appear")
                time.sleep(0.1)
            client = module.Console(int(match[1]), 90)
            startup = client.prompt().decode("utf-8")
            transcript.append(startup)
            assert "Zentaji boot ROM v1" in startup and "Type help for the available commands." in startup
            assert f"build {manifest['anvil_build']} " in startup
            if label == "autostart":
                assert "Booting SAVED.PMF in " in startup and "The payload returned, r1 = $000000000000002A" in startup, startup
            elif label == "cleared":
                assert "Booting SAVED.PMF" not in startup and "The payload returned" not in startup, startup
            if automation and label == "second":
                result["guest_sparkle_phase"] = check_screenshot(client, keep, transcript)
            for command, expected in commands:
                reply = client.command(command).decode("utf-8")
                transcript.append(reply)
                assert expected in reply, (command, reply)
                if command.startswith("echo "):
                    assert expected in reply.splitlines(), (command, reply)
                if command in ("uptime", "up"):
                    assert re.search(r"^uptime [0-9]+ boots \?\r?$", reply, re.M), (command, reply)
                assert "!!" not in reply, (command, reply)
                print(label + ": " + command + " PASS", flush=True)
            if transfers and label == "first":
                result["file_transfer"] = check_file_transfer(client, transcript, keep)
            if diagnostics and label == "second":
                result["machine_diagnostics"] = check_machine_diagnostics(client, transcript)
            if loaders and label == "second":
                result["serial_loaders"] = check_serial_loaders(client, transcript)
            if memory and label == "second":
                result["memory"] = check_memory_commands(client, transcript, container)
            if automation and label == "second":
                result["automation"] = check_automation(client, transcript, container)
            if label == "arm":
                for line, expected in (("autoboot file ABSENT.PMF", "could not be opened"),
                                       ("autoboot file SAVED.ZEN", "too short")):
                    reply = client.command(line).decode("ascii")
                    transcript.append(reply)
                    assert expected in reply, reply
                status = client.command("autoboot status").decode("ascii")
                transcript.append(status)
                assert "SAVED.PMF" in status, status
            client.socket.sendall(b"halt\r")
            # Guest shutdown precedes the host's hex dump of the complete UART
            # transcript. Keep the guest deadline independent of report size.
            if automation and label == "second":
                deadline = time.monotonic() + 45
                while child.alive():
                    if re.search(rb"(?m)^END steps=\d+ exit=0 powered=1 ",
                                 (folder / "zentaji.log").read_bytes()):
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Anvil did not report a clean halt")
                    time.sleep(0.2)
                child.wait(300)
            else:
                child.wait(45)
        finally:
            if client:
                client.close()
            child.close()
            (keep / (label + "-transcript.log")).write_text("".join(transcript), encoding="utf-8")
            for name in ("zentaji.log", "zentaji-errors.log", "screen.png"):
                if (folder / name).is_file():
                    shutil.copyfile(folder / name, keep / (label + "-" + name))
        log = (folder / "zentaji.log").read_text(encoding="utf-8")
        assert "HOST_GPU_ERROR" not in log and "HOST_GPU_REFUSED" not in log
        assert re.search(r"^END steps=\d+ exit=0 powered=1 ", log, re.M), log[-1500:]
        result["boots"].append(dict(label=label, commands=len(commands),
                                    halted=True))

    source = b"Procedure.q Main()\nProcedureReturn 42\nEndProcedure\n"
    boot("first", [("uptime", "boots ?"),
                   ("up", "boots ?"),
                   ("forge print 2+2", "Forge result 4"),
                   ("forge new", "pmf> "),
                   ("forge add Procedure.q Main()", "pmf> "),
                   ("forge add ProcedureReturn 42", "pmf> "),
                   ("forge add EndProcedure", "pmf> "),
                   ("forge save SAVED.ZEN", "Forge source saved"),
                   ("forge compile SAVED.PMF", "Forge wrote "),
                   ("boot SAVED.PMF", "The payload returned, r1 = $000000000000002A"),
                   ("net", "Zentaji Ethernet is attached."),
                   ("dhcp", "Lease accepted on Zentaji Ethernet"),
                   ("dns localhost", "localhost resolves to 10.0.2.2")])
    disk_hash = digest(folder / "data.img")
    assert disk_hash != digest(folder / "data-seed.img"), "The runtime disk did not change"
    with (folder / "data.img").open("rb") as disk:
        entries = read_entries(disk)
        if transfers:
            _, offset, size = entries["ROUND.BIN"]
            disk.seek(offset)
            assert disk.read(size) == (keep / "tftp-root" / "FROMHOST.BIN").read_bytes()
        _, offset, size = entries["SAVED.ZEN"]
        disk.seek(offset)
        assert disk.read(size) == source
        _, offset, size = entries["SAVED.PMF"]
        disk.seek(offset)
        container = disk.read(size)
        assert container[:8] == b"PMFBOOT\0"
        (keep / "guest-built.pmf").write_bytes(container)
    # The first boot produced the next boot's input. Sign it before executing.
    signatures(powershell, signer, catalogs=[catalog(keep / "cold-boot-input.cat",
                [folder / "data.img", keep / "guest-built.pmf"], True)])
    boot("second", [("forge load SAVED.ZEN", f"Forge loaded {len(source)} bytes"),
                    ("forge run", "Forge result 42"),
                    ("boot SAVED.PMF", "The payload returned, r1 = $000000000000002A"),
                    ("echo RESTARTED", "RESTARTED")])
    assert digest(folder / "data.img") == disk_hash, "The launcher replaced or changed the saved disk"
    verify()
    # A graceful Anvil halt releases/disables the display, so its final PNG is
    # correctly black. Observe the live resident prompt separately, using the
    # identical packaged machine. This deadline is only the capture trigger;
    # there is no throughput/frame-count acceptance or profiling option.
    print("Checking the live package header before monitor shutdown.", flush=True)
    graphics = subprocess.run(
        [str(folder / "zenwin.exe"), "machine.txt", "--headless", "--live", "--fast",
         "--live-seconds", "60", "--max", "4000000000", "--screenshot", str(keep / "live-screen.png")],
        cwd=folder, capture_output=True, text=True, timeout=90, creationflags=0x08000000)
    live_log = graphics.stdout + graphics.stderr
    (keep / "live.log").write_text(live_log, encoding="utf-8")
    assert graphics.returncode == 2, live_log[-1500:]
    errors = [line for line in live_log.splitlines() if line.startswith("error:")]
    assert errors == ["error: the live session did not finish within 60 s of host time."], errors
    assert "HOST_GPU_ERROR" not in live_log and "HOST_GPU_REFUSED" not in live_log
    serial = bytes.fromhex(re.search(r"^SERIAL0 ([0-9A-Fa-f]+)$", live_log, re.M)[1])
    assert b"Type help for the available commands." in serial and serial.endswith(b"pmf> ")
    result["live_header_logo"] = True
    result["live_sparkle_phase"] = screen_check(keep / "live-screen.png")
    assert digest(folder / "data.img") == disk_hash
    if autoboot:
        def sign_boot_disk(label):
            signatures(powershell, signer, catalogs=[catalog(keep / (label + "-input.cat"), [folder / "data.img"], True)])
        sign_boot_disk("arm")
        boot("arm", [("autoboot file SAVED.PMF", "Autoboot target saved: SAVED.PMF"),
                     ("autoboot status", "SAVED.PMF")])
        sign_boot_disk("autostart")
        boot("autostart", [("autoboot clear", "The boot target is cleared")])
        sign_boot_disk("cleared")
        boot("cleared", [("echo AUTOBOOT-CLEARED", "AUTOBOOT-CLEARED")])
        result["file_autoboot"] = dict(file="SAVED.PMF", return_value=42, cleared=True)
    result.update(persistent_source=True, persistent_payload_return=42,
                  immutable_package_valid=True, disk_sha256=digest(folder / "data.img"))
    report = keep / "result.json"
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    evidence = [report, keep / "guest-built.pmf", keep / "live-screen.png", keep / "live.log"]
    if transfers:
        evidence.extend(keep / "tftp-root" / name for name in ("FROMHOST.BIN", "TOHOST.BIN"))
    if automation:
        evidence.append(keep / "guest-screenshot.png")
    for label in [item["label"] for item in result["boots"]]:
        evidence += [keep / (label + "-" + suffix) for suffix in
                     ("launcher.log", "transcript.log", "zentaji.log", "zentaji-errors.log", "screen.png")]
    signatures(powershell, signer, catalogs=[catalog(keep / "results.cat", evidence, True)])
    print("PASS relocated package, two real ROM boots, exact graphical header/logo, guest Forge, NAT and persistent source/payload")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    parser.add_argument("--sign-script", type=Path, required=True)
    parser.add_argument("--powershell", default="pwsh.exe")
    parser.add_argument("--automation", action="store_true", help="Exercise programs, readback and screenshot over UART")
    parser.add_argument("--transfers", action="store_true", help="Check host file exchange over loopback TFTP (tftpy==0.8.7 and a free UDP port 69)")
    parser.add_argument("--memory", action="store_true", help="Check interactive memory edits, range testing and hashes on Zentaji")
    parser.add_argument("--autoboot", action="store_true", help="Select a file, cold-boot it, and clear the persistent boot selection")
    parser.add_argument("--diagnostics", action="store_true", help="Check native UART baud, register inspection and GPU presentation status")
    parser.add_argument("--loaders", action="store_true", help="Check serial block and S-record loading, board identity and timer frequency")
    args = parser.parse_args()
    print(json.dumps(check(args.archive, args.keep, args.sign_script, args.powershell, args.automation, args.transfers, args.memory, args.loaders, args.diagnostics, args.autoboot), indent=2))


if __name__ == "__main__":
    main()
