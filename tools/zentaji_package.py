"""Build a signed, local Windows tester bundle from existing Zentaji artifacts.

No compiler runs here. Only explicitly named files enter the bundle; existing
destinations and writable tester disks are never replaced.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from anvilfs_image import build_image

ROOT = Path(__file__).resolve().parents[1]
THUMBPRINT = "87C124533A339D992796C7026901766D74FF1252"
FILES = ("zenwin.exe", "anvil.zex", "data-seed.img", "machine.txt",
         "Start-Zentaji.cmd", "zen_console.py", "START-HERE.txt", "manifest.json")
MACHINE = """# Zentaji with Anvil selected by the machine boot ROM.
machine $10000000 2 1000 1
display 1024 768 60000
hostfile 0 anvil.zex anvil.zex
disk 0 0 data.img
net
entropy host
bootsource 0 0
"""

# Paths travel through an environment variable, never through PowerShell source
# interpolation. File.Copy(overwrite=false) cannot replace an existing disk.
# The headless option runs the same configuration for package acceptance.
LAUNCH_PS = """$ErrorActionPreference='Stop';
$p=$env:ZENTAJI_PACKAGE;
$mode=[string]$env:ZENTAJI_MODE;
if ($mode -notin @('', '--headless')) { throw 'Use Start-Zentaji.cmd [--headless]' };
$m=Get-Content -LiteralPath (Join-Path $p 'manifest.json') -Raw | ConvertFrom-Json;
$sha=[Security.Cryptography.SHA256]::Create();
try {
  foreach ($f in $m.files) {
    $stream=[IO.File]::OpenRead((Join-Path $p $f.name));
    try { $h=[BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','') } finally { $stream.Dispose() };
    if ($h -ne $f.sha256) { throw ('Package file changed: '+$f.name) }
  }
} finally { $sha.Dispose() };
$disk=Join-Path $p 'data.img';
if (-not [IO.File]::Exists($disk)) { [IO.File]::Copy((Join-Path $p 'data-seed.img'),$disk,$false) };
$a=@('machine.txt','--fast','--window-size','1024x768','--serial-listen','0');
if ($mode -eq '--headless') {
  $a+=@('--headless','--live','--live-seconds','300','--max','4000000000','--screenshot','screen.png')
};
$child=Start-Process -FilePath (Join-Path $p 'zenwin.exe') -WorkingDirectory $p -ArgumentList $a -WindowStyle Hidden -RedirectStandardOutput (Join-Path $p 'zentaji.log') -RedirectStandardError (Join-Path $p 'zentaji-errors.log') -PassThru;
[IO.File]::WriteAllText((Join-Path $p 'zentaji.pid'),[string]$child.Id);
"""
LAUNCHER = ('@echo off\nsetlocal\nset "ZENTAJI_PACKAGE=%~dp0"\n'
            'set "ZENTAJI_MODE=%~1"\n'
            'powershell.exe -NoProfile -Command "' +
            " ".join(row.strip() for row in LAUNCH_PS.splitlines()) +
            '"\nexit /b %errorlevel%\n')

INSTRUCTIONS = """ZENTAJI / ANVIL - WINDOWS TESTER BUILD

Extract the entire archive to a writable folder. Double-click Start-Zentaji.cmd.
The machine boot ROM loads Anvil and its graphical pmf> prompt. Python, a host
compiler and the source repositories are not needed for ordinary use.

The initial window is 1024x768 and can be resized. The visible machine takes its
date/time from the host. Its two CPU cores use 256 MiB of guest RAM. Idle waits
sleep; production graphics uses the host GPU. A Windows x64 host with hardware
OpenGL compute, shader int64 and fp64 support is required. Unsupported hardware
is refused; there is no automatic software renderer.

DATA
On first launch, data-seed.img is copied to data.img. This writable AnvilFS disk
holds guest files across launches. Keep data.img when moving or backing up your
machine. Never replace it with the seed to upgrade Anvil. Run one instance per
folder. Type halt at the Anvil prompt for a graceful shutdown. Wait for the
emulator to exit before copying the writable disk.

TRY
  help
  forge print 2+2
  net
  dhcp
  dns localhost

HOST FILE TRANSFERS
Start a TFTP server on the host at 127.0.0.1, UDP port 69, with a directory
containing your files. Enable uploads there if you want to use put. In Anvil:
  settings set net.server 10.0.2.2
  get INPUT.BIN
The guest prints its destination address and byte count. Addresses and lengths
in commands are hexadecimal. For example, for a 1024-byte file, substitute
the printed address for ADDR:
  save INPUT.BIN ADDR 400
  load INPUT.BIN ADDR
  put OUTPUT.BIN ADDR 400
The server directory now contains OUTPUT.BIN. To keep the server selection
across boots, type settings save.

The resident Forge supports the integer PureMetal core; full language coverage
and composed-desktop performance are still in development. This bundle does
not claim completed performance acceptance.

AUTOMATION (optional Python 3 client)
zentaji.log reports SERIAL_LISTEN 127.0.0.1 PORT UART0. Use that PORT:
  python zen_console.py --port PORT --command "echo READY" --expect-line READY
The listener accepts one local client at a time. No network port is forwarded
to other computers. NAT is attached for guest networking commands.
Start-Zentaji.cmd --headless uses the same machine without opening its window;
it stops after five minutes if the guest has not halted. Its RTC retains the
headless fixture epoch; host UTC seeding belongs to visible launches.

VERIFICATION AND DIAGNOSTICS
The package.cat catalog covers immutable distribution files, including the
blank seed. data.img, logs, screen.png and zentaji.pid are runtime files and
are deliberately outside that catalog. The launcher checks immutable file
hashes before starting. The archive and executable carry the project's signing
identity; packaging installs no certificates or trust settings.
If startup fails, inspect zentaji.log and zentaji-errors.log. Include those logs
and manifest.json when reporting a problem. The manifest identifies the exact
monitor and emulator bytes without requiring local source paths.
"""

SIGN_PS = r"""param([string]$Request)
$ErrorActionPreference='Stop'
$r=Get-Content -LiteralPath $Request -Raw | ConvertFrom-Json
function Assert-Signature([string]$path) {
  $s=Get-AuthenticodeSignature -LiteralPath $path
  if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Thumbprint -ne $r.thumbprint) {
    throw ('Signature verification failed: '+$path)
  }
}
foreach ($exe in $r.executables) { Assert-Signature $exe }
foreach ($group in $r.catalogs) {
  if ($group.create) {
    New-FileCatalog -Path @($group.files) -CatalogFilePath $group.path -CatalogVersion 2 | Out-Null
    $global:LASTEXITCODE=0
    & $r.sign_script -Path $group.path
    if ($LASTEXITCODE -ne 0) { throw ('Catalog signing failed: '+$group.path) }
  }
  Assert-Signature $group.path
  if ((Test-FileCatalog -Path @($group.files) -CatalogFilePath $group.path) -ne 'Valid') {
    throw ('Catalog content verification failed: '+$group.path)
  }
}
"""


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def signatures(powershell, sign_script, *, executables=(), catalogs=()):
    """Use only the supplied existing signer; never change certificate stores."""
    with tempfile.TemporaryDirectory(prefix="zentaji-package-sign-") as directory:
        directory = Path(directory)
        script, request = directory / "verify.ps1", directory / "request.json"
        script.write_text(SIGN_PS, encoding="utf-8")
        request.write_text(json.dumps(dict(
            thumbprint=THUMBPRINT, sign_script=str(sign_script),
            executables=[str(p) for p in executables], catalogs=catalogs,
        )), encoding="utf-8")
        subprocess.run([powershell, "-NoProfile", "-File", str(script), str(request)], check=True)


def catalog(path, files, create=False):
    return dict(path=str(path), files=[str(p) for p in files], create=create)


def package(image, zen_tools, output, archive, sign_script, powershell="pwsh.exe"):
    if os.name != "nt":
        raise ValueError("This package recipe verifies Windows signatures on Windows")
    image, zen_tools, output, archive, sign_script = (
        Path(p).resolve() for p in (image, zen_tools, output, archive, sign_script)
    )
    if output.exists() or archive.exists() or Path(str(archive) + ".cat").exists():
        raise ValueError("Choose new output/archive paths; existing packages and disks are never overwritten")
    if archive.is_relative_to(output):
        raise ValueError("The archive must be outside the package folder")
    exe, client = zen_tools / "zenwin.exe", zen_tools / "zen_console.py"
    sidecars = [Path(str(image) + suffix) for suffix in
                ("", ".boot.json", ".asm", ".zmap", ".compiled.zex", ".compiled.asm")]
    signatures(powershell, sign_script, executables=[exe],
               catalogs=[catalog(Path(str(image) + ".cat"), sidecars)])
    metadata = json.loads(sidecars[1].read_text(encoding="utf-8"))
    mapping = json.loads(Path(str(image) + ".zmap").read_text(encoding="utf-8"))
    if digest(image) != metadata["image_sha256"] or digest(image) != mapping["image"]:
        raise ValueError("Anvil image does not match its metadata and source map")
    if metadata["architecture"] != "Zentaji" or metadata["minimum_ram_bytes"] > 256 << 20:
        raise ValueError("The counted image does not fit this Zentaji profile")
    build = None
    for source in mapping["sources"]:
        path = Path(source["path"]).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError(f"Anvil source outside this repository: {path}")
        raw = path.read_bytes().replace(b"\r", b"")
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError(f"Anvil source changed since its counted build: {path}")
        if path == ROOT / "Zentaji/Board/board.zentaji":
            match = re.search(rb"^#ANVIL_BUILD\s*=\s*(\d+)\s*;", raw, re.M)
            if match:
                build = int(match[1])
    if build is None:
        raise ValueError("Counted Zentaji board is absent from the image source map")
    # Explicit named copies: never traverse a source or project directory.
    output.mkdir(parents=True, exist_ok=False)
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(exe, output / "zenwin.exe")
    shutil.copyfile(image, output / "anvil.zex")
    shutil.copyfile(client, output / "zen_console.py")
    build_image(output / "data-seed.img", 64 << 20)
    for name, text in (("machine.txt", MACHINE), ("Start-Zentaji.cmd", LAUNCHER),
                       ("START-HERE.txt", INSTRUCTIONS)):
        (output / name).write_text(text, encoding="utf-8", newline="\r\n")
    manifest = dict(schema=1, anvil_build=build, architecture="Zentaji",
                    ram_bytes=256 << 20, cores=2, initial_window=[1024, 768],
                    boot="machine ROM selects bundled Anvil host file",
                    files=[dict(name=name, sha256=digest(output / name))
                           for name in FILES if name != "manifest.json"],
                    mutable_files=["data.img", "zentaji.log", "zentaji-errors.log",
                                   "zentaji.pid", "screen.png"])
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    signatures(powershell, sign_script, executables=[output / "zenwin.exe"], catalogs=[
        catalog(output / "package.cat", [output / name for name in FILES], True)])
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for name in (*FILES, "package.cat"):
            zipped.write(output / name, name)
    archive_catalog = Path(str(archive) + ".cat")
    try:
        signatures(powershell, sign_script, catalogs=[catalog(archive_catalog, [archive], True)])
    except BaseException:
        # Both paths were absent at entry and were created by this invocation.
        # Keep the already verified folder, but never leave an unsigned archive.
        archive_catalog.unlink(missing_ok=True)
        archive.unlink()
        raise
    return dict(package=str(output), archive=str(archive), anvil_build=build,
                image_sha256=digest(output / "anvil.zex"),
                executable_sha256=digest(output / "zenwin.exe"), archive_sha256=digest(archive))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=ROOT / "build/zentaji/anvil.zex")
    parser.add_argument("--zen-tools", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sign-script", type=Path, required=True)
    parser.add_argument("--powershell", default="pwsh.exe")
    args = parser.parse_args()
    try:
        result = package(args.image, args.zen_tools, args.output, args.archive,
                         args.sign_script, args.powershell)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Package not published: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
