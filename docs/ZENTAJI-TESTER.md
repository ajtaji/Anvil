# Local Zentaji tester bundle

`tools/zentaji_package.py` packages an existing counted Anvil image and signed
ASM `zenwin.exe`. It does not compile either program. Supply the current native
tools directory and the existing signing script explicitly:

```text
python tools/zentaji_package.py --zen-tools <tools/zentaji> --output <new-folder> --archive <new-zip> --sign-script <signing/sign.ps1>
```

Run this recipe on Windows with PowerShell 7 available as `pwsh.exe`. It verifies
the emulator signature, the monitor's six-file signed catalog, image metadata
and source hashes. It refuses existing output paths. The package and archive
receive signed catalogs, verified with the existing signing identity. It never
installs certificates or modifies trust settings. Keep tester bundles local
unless publication is explicitly requested.

Extract the archive into a writable folder and double-click `Start-Zentaji.cmd`.
The ROM loads the included Anvil image. The initial window is 1024x768 and
remains resizable. The visible machine seeds its RTC from host UTC and uses the
existing host GPU, idle waits and NAT. Python and the host compiler are not
needed for ordinary interactive use.

The first launch copies the immutable `data-seed.img` into `data.img` without
overwriting an existing file. AnvilFS stores guest files on this persistent
64 MiB disk. Preserve `data.img` when upgrading or backing up a tester machine.
Run only one emulator per folder and use `halt` before copying the disk.

The existing `zen_console.py` client is included for optional Python 3
automation. The loopback UART port appears in `zentaji.log`. The launcher also
accepts `--headless` for package correctness checks; it uses the same machine
configuration with a five-minute observation limit. Headless operation retains
the fixture RTC epoch, unlike visible host-clock seeding.

The immutable catalog includes the seed, executable, monitor, configuration,
launcher, client, instructions and manifest. Runtime disk/log/PID/screenshot
files are excluded. No source tree, game, model or unrelated project is copied.
The current monitor includes the integer-core guest Forge. Full language
coverage and composed graphics performance remain unfinished.

Validate a newly built archive without opening a desktop window:

```text
python tools/zentaji_package_check.py --archive <new-zip> --keep <new-proof-folder> --sign-script <signing/sign.ps1>
```

The check verifies signatures before extraction/use and boots the package from
a path containing spaces, an apostrophe and an ampersand. It saves and compiles
guest source, exercises NAT, halts, then cold-boots the same disk and executes
the saved payload. A separate resident-prompt capture verifies the exact shared
header/logo before shutdown; a graceful `halt` deliberately disables scanout.
The capture deadline is an observation bound, not a performance measurement.
Logs, PNGs, the guest-built payload and results receive a verified catalog.
