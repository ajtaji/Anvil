"""Exercise live Windows radio commands through the real Zentaji ROM and UART."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from zentaji_package import catalog, digest, signatures

ROOT = Path(__file__).resolve().parents[1]


def host_reference():
    # Inspect the active WLAN directly from a separate process, without querying keys.
    wlan = ctypes.WinDLL("wlanapi")
    handle, table = wintypes.HANDLE(), ctypes.c_void_p()
    version = wintypes.DWORD()
    rc = wlan.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle))
    if rc:
        raise OSError(rc, "WlanOpenHandle")
    try:
        assert wlan.WlanEnumInterfaces(handle, None, ctypes.byref(table)) == 0
        count = ctypes.c_uint32.from_address(table.value).value
        entries = [table.value + 8 + 532 * i for i in range(count)]
        iface = next((p for p in entries if ctypes.c_uint32.from_address(p + 528).value == 1), None)
        assert iface, "Live qualification needs a connected Windows Wi-Fi adapter"
        name = ctypes.wstring_at(iface + 16)
        available = ctypes.c_void_p()
        rc = wlan.WlanGetAvailableNetworkList(handle, ctypes.c_void_p(iface), 0, None, ctypes.byref(available))
        if available:
            wlan.WlanFreeMemory(available)
        return name, rc
    finally:
        if table:
            wlan.WlanFreeMemory(table)
        wlan.WlanCloseHandle(handle, None)


def host_bond(address):
    bt = ctypes.WinDLL("bthprops.cpl")
    bt.BluetoothFindFirstRadio.restype = wintypes.HANDLE
    size, radio = wintypes.DWORD(4), wintypes.HANDLE()
    finder = bt.BluetoothFindFirstRadio(ctypes.byref(size), ctypes.byref(radio))
    if not finder:
        return False
    try:
        data = ctypes.create_string_buffer(560)
        ctypes.c_uint32.from_buffer(data).value = len(data)
        ctypes.c_uint64.from_buffer(data, 8).value = int(address.replace(":", ""), 16)
        rc = bt.BluetoothGetDeviceInfo(radio, ctypes.byref(data))
        return rc == 0 and ctypes.c_uint32.from_buffer(data, 28).value != 0
    finally:
        ctypes.windll.kernel32.CloseHandle(radio)
        bt.BluetoothFindRadioClose(wintypes.HANDLE(finder))


def run(args):
    sys.path.insert(0, str(args.zen_tools))
    from zen_console import Console
    args.keep.mkdir(parents=True)
    image = ROOT / "build/zentaji/anvil.zex"
    assert digest(image) == json.loads(Path(str(image) + ".boot.json").read_text())["image_sha256"]
    signatures("pwsh", args.sign_script, executables=[args.exe])
    adapter, windows_scan_rc = host_reference()
    result = {"image_sha256": digest(image), "emulator_sha256": digest(args.exe)}
    proofs = []
    for mode in ("absent", "host", "manage"):
        folder = args.keep / mode
        folder.mkdir()
        local_image = folder / "anvil.zex"
        shutil.copyfile(image, local_image)
        config = folder / "machine.txt"
        lines = ["machine $08000000 2 1000 1", "display 1024 768 60000",
                 "hostfile 0 anvil.zex anvil.zex", "net", "bootsource 0 0"]
        if mode != "absent":
            lines.append("radios " + mode)
        config.write_text("\n".join(lines) + "\n")
        inputs = folder / "inputs.cat"
        signatures("pwsh", args.sign_script, catalogs=[catalog(inputs, [config, local_image], True)])
        log = folder / "run.log"
        with log.open("wb") as writer:
            process = subprocess.Popen([args.exe, config, "--headless", "--live", "--fast", "--serial-listen", "0",
                                        "--live-seconds", "180", "--max", "14000000000"], stdout=writer, stderr=writer)
            client = None
            try:
                until = time.monotonic() + 35
                while True:
                    with log.open("rb") as stream:
                        match = re.search(rb"SERIAL_LISTEN 127\.0\.0\.1 (\d+) UART0", stream.read(1024))
                    if match:
                        break
                    if process.poll() is not None or time.monotonic() > until:
                        raise RuntimeError("Missing live UART in " + str(folder))
                    time.sleep(0.08)
                client = Console(int(match[1]), 45)
                assert b"Zentaji boot ROM" in client.prompt()

                def command(line):
                    def read_reply(request):
                        reply = client.command(request).decode("ascii")
                        with (folder / "uart.log").open("a", encoding="ascii") as transcript:
                            transcript.write(reply)
                        return reply
                    reply = read_reply(line)
                    limit = time.monotonic() + 40
                    while "operation pending." in reply:
                        if time.monotonic() > limit:
                            raise TimeoutError("Radio operation did not complete")
                        time.sleep(0.2)
                        reply = read_reply(line.split()[0] + " result")
                    return reply

                if mode == "absent":
                    assert "unavailable" in command("wifi status")
                    assert "unavailable" in command("bt devices")
                    result["absent_refused"] = True
                elif mode == "host":
                    assert adapter in command("wifi status")
                    assert "Bluetooth radio:" in command("bt status")
                    assert "radios manage" in command("wifi join Test")
                    assert "radios manage" in command("bt pair 00:00:00:00:00:00")
                    result["discovery_only_control_refused"] = True
                else:
                    status = command("wifi status")
                    assert adapter in status and "Wi-Fi link: connected." in status
                    profile = re.search(r"(?m)^Current profile: (.+?)\r?$", status)
                    profiles = command("wifi profiles")
                    assert "Saved Wi-Fi profiles:" in profiles
                    scan = command("wifi scan")
                    if windows_scan_rc == 5:
                        assert "Windows 5" in scan
                        result["wifi_scan"] = "Windows location access denied; confirmed by independent WLAN API"
                    else:
                        assert re.search(r"(?m)^Wi-Fi scan: \d+ available network", scan), "Scan failed; see local UART"
                        result["wifi_scan"] = "active scan completed"
                    assert "Windows 1168" in command("wifi join __Anvil_Absent_Profile_813C86BC__")
                    if args.join_current:
                        assert profile, "Windows withheld current profile; live join is unverified"
                        target = profile[1]
                        assert target in profiles
                        assert "Wi-Fi joined profile: " + target in command("wifi join " + target)
                        result["joined_current_profile"] = True
                    assert "Use bt" in command("bt pair")
                    assert "Windows 87" in command("bt pair 00:00:00:00:00:00")
                    devices = command("bt devices")
                    assert "Bluetooth Classic known devices:" in devices
                    inquiry = command("bt scan")
                    assert "Bluetooth Classic inquiry" in inquiry and "failed (Windows" not in inquiry
                    bond = re.search(r"(?m)^([0-9A-F:]{17}) [^\r\n]*\[paired\]", devices)
                    if args.existing_bond:
                        assert bond, "No existing Classic bond available"
                        assert host_bond(bond[1]), "Windows disagrees with the guest bond status"
                        assert "already paired" in command("bt pair " + bond[1])
                        result["existing_bond_verified"] = True
                    assert "There is no result for this radio." in command("wifi result")
                    assert "Lease accepted" in command("dhcp")
                    result["bt_classic_inquiry"] = True
                    result["ethernet_dhcp_after_radio_use"] = True
                client.socket.sendall(b"halt\r")
                assert process.wait(timeout=40) == 0
            finally:
                if client:
                    client.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
        proof = args.keep / (mode + ".cat")
        signatures("pwsh", args.sign_script, catalogs=[catalog(proof, [inputs, log, folder / "uart.log"], True)])
        proofs.append(proof)
    report = args.keep / "result.json"
    report.write_text(json.dumps(result, indent=2) + "\n")
    signatures("pwsh", args.sign_script, catalogs=[catalog(args.keep / "results.cat", [*proofs, report], True)])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--keep", type=Path, required=True)
    parser.add_argument("--sign-script", type=Path, required=True)
    parser.add_argument("--join-current", action="store_true")
    parser.add_argument("--existing-bond", action="store_true")
    run(parser.parse_args())
