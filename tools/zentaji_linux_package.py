"""Bundle a WSL-built x86-64 Zentaji runner with a counted Anvil tester image."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

from zentaji_package import catalog, digest, signatures


LAUNCH = """#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
case "${1:-}" in
  '') mode=(--quit) ;;
  --headless) mode=(--headless --live --live-seconds 600 --max 300000000000) ;;
  *) echo 'Usage: ./start-zentaji.sh [--headless]' >&2; exit 2 ;;
esac
(( $# <= 1 )) || exit 2
sha256sum --check --status SHA256SUMS || { echo 'Package integrity check failed.' >&2; exit 1; }
exec 9>.zentaji.lock
flock -n 9 || { echo 'This disk is already in use by another launch.' >&2; exit 1; }
if [[ ! -e data.img ]]; then
  temp=$(mktemp .data.img.XXXXXX)
  trap 'rm -f -- "$temp"' EXIT
  cp -- data-seed.img "$temp"
  mv -- "$temp" data.img
  trap - EXIT
fi
if [[ -e /dev/dxg && -n "${WSL_DISTRO_NAME:-}" ]]; then
  export GALLIUM_DRIVER="${GALLIUM_DRIVER:-d3d12}"
fi
exec ./zenwin machine.txt --fast --window-size 1024x768 --serial-listen 0 "${mode[@]}"
"""


def package(windows, runner, build_catalog, output, signer):
    with zipfile.ZipFile(windows) as archive:
        signatures("pwsh", signer, catalogs=[catalog(Path(str(windows) + ".cat"), [windows])])
        manifest = json.loads(archive.read("manifest.json"))
        hashes = {item["name"]: item["sha256"] for item in manifest["files"]}
        number = int(manifest["anvil_build"])
        target = output / f"Zentaji-Anvil{number}-linux-x86_64"
        target.mkdir(parents=True, exist_ok=False)
        for name in ("anvil.zex", "data-seed.img", "zen_console.py"):
            path = target / name
            with archive.open(name) as src, path.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            assert digest(path) == hashes[name], name
    signatures("pwsh", signer, catalogs=[catalog(build_catalog, [runner, runner.parent / "sources.json",
                                                                 runner.parent / "build.log"])])
    with runner.open("rb") as stream:
        header = stream.read(20)
    if header[:6] != b"\x7fELF\x02\x01" or int.from_bytes(header[18:20], "little") != 62:
        raise ValueError("Expected a little-endian x86-64 ELF runner")
    shutil.copyfile(runner, target / "zenwin")
    (target / "start-zentaji.sh").write_text(LAUNCH, encoding="ascii", newline="\n")
    (target / "machine.txt").write_text(
        "machine $08000000 2 1000 1\ndisplay 1024 768 60000\nhostfile 0 anvil.zex anvil.zex\n"
        "disk 0 0 data.img\nnet\nentropy host\nbootsource 0 0\n", encoding="ascii", newline="\n")
    (target / "START-HERE.txt").write_text(f"""Zentaji with Anvil build {number} for Linux x86-64

In WSL Ubuntu with WSLg, unzip the archive into your Linux home directory.
Open the extracted Zentaji-Anvil{number}-linux-x86_64 directory and run
  ./start-zentaji.sh
If your extractor lost the executable bits, run chmod +x zenwin start-zentaji.sh.
The launcher starts the machine ROM, which loads the included Anvil image.
Type dhcp at the pmf> prompt to configure the emulated Ethernet interface.
Programs that request Anvil services can then use DNS, TCP and authenticated
TLS over IPv4. Windows host Wi-Fi and Bluetooth management are platform-specific.

The initial window is 1024x768. This profile has two cores, 128 MiB RAM and a
64 MiB persistent data.img. Type halt at the prompt before copying your disk.
The launcher creates data.img on the first run. Keep it to preserve your work.

Automation can use ./start-zentaji.sh --headless. The terminal prints
SERIAL_LISTEN with the allocated loopback port. From a second Linux terminal:
  python3 zen_console.py --port PORT --command "version"
The headless session has a 600-second limit. Ordinary window runs use halt.

The native runner requires x86-64 Linux, GTK 3, X11 and hardware OpenGL compute
with 64-bit integer and floating-point support. WSLg on this laptop uses Mesa
D3D12. Run ldd ./zenwin to identify missing runtime libraries. Bash, flock and
GNU coreutils are used by the launcher. Python is optional for automation.
The runner and Anvil are supplied prebuilt.
""", encoding="ascii", newline="\n")
    members = sorted(p.name for p in target.iterdir())
    (target / "SHA256SUMS").write_text(
        "".join(f"{digest(target / name)}  {name}\n" for name in members), encoding="ascii", newline="\n")
    members.append("SHA256SUMS")
    signatures("pwsh", signer, catalogs=[catalog(target / "package.cat", [target / n for n in members], True)])
    zip_path = target.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in [*members, "package.cat"]:
            info = zipfile.ZipInfo.from_file(target / name, target.name + "/" + name)
            info.create_system = 3
            mode = 0o755 if name in ("zenwin", "start-zentaji.sh") else 0o644
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with archive.open(info, "w") as dst, (target / name).open("rb") as src:
                shutil.copyfileobj(src, dst)
    signatures("pwsh", signer, catalogs=[catalog(Path(str(zip_path) + ".cat"), [zip_path], True)])
    print(zip_path, digest(zip_path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("windows", "runner", "build-catalog", "output", "signer"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    package(args.windows.resolve(), args.runner.resolve(), args.build_catalog.resolve(),
            args.output.resolve(), args.signer.resolve())
