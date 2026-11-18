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


def check(archive, keep, signer, powershell):
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
            client.socket.sendall(b"halt\r")
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
    result.update(persistent_source=True, persistent_payload_return=42,
                  immutable_package_valid=True, disk_sha256=disk_hash)
    report = keep / "result.json"
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    evidence = [report, keep / "guest-built.pmf", keep / "live-screen.png", keep / "live.log"]
    for label in ("first", "second"):
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
    args = parser.parse_args()
    print(json.dumps(check(args.archive, args.keep, args.sign_script, args.powershell), indent=2))


if __name__ == "__main__":
    main()
