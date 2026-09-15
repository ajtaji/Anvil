# Anvil

**A portable bare-metal mini-kernel, bootloader, and recovery monitor written
in PureMetal.**

[MIT licensed](LICENSE) · [Architecture](docs/ARCHITECTURE.md) ·
[Portability](docs/PORTABILITY.md) ·
[PureMetal Forge](https://puremetalforge.ajtaji.com/) ·
[Forums](https://forum.ajtaji.com/category/18/puremetal-forge) ·
[Anvil forum](https://forum.ajtaji.com/category/116/anvil) ·
[Issue tracker](https://github.com/ajtaji/Anvil/issues)

Anvil keeps one hardware-independent monitor core and composes it with the
drivers for a selected board. It remains resident while a payload runs, owns
the machine's physical services, and exposes a versioned service-table ABI to
payloads instead of making each payload bring a second hardware stack.

> [!IMPORTANT]
> Anvil is active development software for direct hardware access. It is not a
> finished distribution or a Vulkan-conformant implementation. Keep a known
> recovery path before installing a new image, and do not derive upload
> addresses from examples or previous builds. On the Pi, query and validate the
> running monitor's `map` response for every update.

## Target status

| Target | Boot model | Current status |
|---|---|---|
| Raspberry Pi 4 / BCM2711 / Cortex-A72 | Bare-metal AArch64 image | Most mature target. A recent hardware build booted with caches enabled, HDMI and native 1280×800 landscape DSI output, DMA-backed console rendering, and wired/Wi-Fi console access. A 2.2 MB RAM transfer was verified over Ethernet at approximately 10.97 MiB/s. The current tree contains newer display, network, and touch integration that still requires a complete on-board release pass. |
| Arduino UNO Q / QCM2290 / Cortex-A53 | AArch64 UEFI application | Early target. UEFI console and file access are in use, and GPIO has been exercised on hardware. Most native QCM2290 drivers, networking, display acceleration, and the Adreno path remain development work. |

Host builds and emitted-code tests are valuable gates, but they are not a
substitute for hardware proof. Exact status and known boundaries are recorded
in [the architecture guide](docs/ARCHITECTURE.md).

## What is in the tree

```text
Anvil/
  Core/                 portable monitor, boot, transfer and network policy
  Hal/                  hardware contract and payload/module ABIs
  Graphics/Vulkan/      experimental Vulkan-compatible foundation
RaspberryPi4/
  Board/                BCM2711 composition and board policy
  Lib/                  Pi drivers, display, V3D/Neon and networking
  Monitor/              source-native banner fonts and artwork
  Tests/                focused source and emitted-code probes
ArduinoQ/
  Board/                QCM2290 UEFI composition
  Lib/                  current native UNO Q drivers
Boards/                  external-compiler target profile
Firmware/CYW43455/       Pi radio firmware (separately licensed)
licenses/                retained third-party license texts
docs/                    architecture, provenance, notices and formats
tools/                   build, verification and development gates
```

Shared code uses `.pbi`, Raspberry Pi hardware code uses `.pi4`, and UNO Q
hardware code uses `.unoq`. Target-specific names do not leak into the portable
HAL contract.

## Build

The PureMetal application (`PureMetalForge.exe`, or `PureMetalForge.linux` on
Linux) is an external dependency and is not included; it is free to download
from the [PureMetal Forge website](https://puremetalforge.ajtaji.com/). The editor and the
compiler are one program: `--compile` builds from the command line with no
window, and there is no separate console compiler. Python 3 is used by the
repository wrapper and host checks; those scripts use only the standard
library.

Put `PureMetalForge` on `PATH`, set the `PMF_COMPILER` environment variable, or
pass it directly:

```sh
python3 tools/build.py all --compiler /path/to/PureMetalForge.exe
python3 tools/build.py pi4
python3 tools/build.py unoq
```

On PowerShell, use `python` if that is how Python is installed:

```powershell
$env:PMF_COMPILER = "C:\PureMetal\PureMetalForge.exe"
python tools/build.py all
```

Outputs are written under the ignored `build/` directory. The wrapper pins
`PMF_ROOT` to this checkout and stages the external compiler with this
repository's board profile in a temporary directory. Missing includes
therefore fail instead of being borrowed from another installation.

Target entries are
[`RaspberryPi4/Board/board.pi4`](RaspberryPi4/Board/board.pi4) and
[`ArduinoQ/Board/board.unoq`](ArduinoQ/Board/board.unoq).

### Experimental EL3 firmware stub

The optional Pi 4 stub has a separate, explicit build using a compiler with
`--armstub` support:

```sh
python3 tools/build.py armstub --compiler /path/to/PureMetalForge.exe
python3 tools/a64/a64_el3_check.py --compiler /path/to/PureMetalForge.exe
python3 tools/a64/el3_runtime_emitted_check.py --compiler /path/to/PureMetalForge.exe
```

This produces `build/pi4/armstub8.bin`; it is not part of `all` and is **not
installed automatically**. Build 98 and the checked stub passed a witnessed
physical power cycle on Pi 4: EL3 entry, the secure timer, controlled fault,
USB/storage and DMA/V3D display all passed. The final cleanup build 99 then
passed EL3, one 16-round run on all three secondary cores, stop acknowledgements
and the same peripheral checks after deployment. Build 99 then passed its exact
physical cold-power-cycle run, including cold leases, touch and Wi-Fi. The
EL3-to-EL1 handoff remains incomplete, so do not
change boot configuration without physical recovery access. Exact
artifacts and the remaining boundary are recorded in
[`docs/EL3_BOOT_ACCEPTANCE.md`](docs/EL3_BOOT_ACCEPTANCE.md). The stub retains
its upstream [BSD-3-Clause notice](RaspberryPi4/Board/armstub8.asm).

### Live time and returning applications

The common wall clock supports UTC, named U.S. Central time with daylight-saving
rules, and fixed offsets. On a network-capable board, synchronization runs as
bounded background work; an unreachable time server does not hold the prompt.
An unset clock or saved time floor is visibly unsynchronized, never presented
as a running battery-backed RTC.

```text
time
time sync
time zone America/Chicago
settings save
```

`time sync` is available only with a network backend. UNO Q currently supports
the common manual clock and zone commands, not network synchronization.
See [wall-clock commands and trust boundaries](docs/WALL_CLOCK.md).

The [panel/touch boot trace](docs/BOOT_I2C_TRACE.md) explains `touch trace`,
which reads retained failure evidence without initiating another hardware probe.

Returning applications have an explicit
[hardware ownership and Ethernet recovery contract](docs/PAYLOAD_LIFECYCLE.md).
The monitor stops active Ethernet DMA before entry and rebuilds the previously
active controller after return without erasing another interface or an
unexpired lease. These new service paths have desk gates; their remaining
silicon checks are documented separately from a completion claim.

### Boot and runtime assets

- The Pi build produces `build/pi4/anvil.img`, a raw bare-metal image. Vendor
  boot firmware, a complete boot partition, and board-specific display
  configuration are intentionally not bundled.
- The UNO Q build produces `build/unoq/anvil.img`. Wrap it as an AArch64 UEFI
  executable when needed:

  ```sh
  python3 tools/unoq_efi_wrap.py build/unoq/anvil.img build/unoq/anvil.efi --load-addr 0x70000000
  ```

- Pi 4 Wi-Fi requires the two CYW43455 binaries under `Firmware/CYW43455/`
  plus a board-appropriate NVRAM file that is deliberately not bundled. See
  [the licensing and asset guide](docs/LICENSING.md) for boot-media names and
  redistribution conditions.

## Verification

Before staging a release candidate, verify the complete non-ignored working
tree:

```sh
python3 tools/verify_export.py --working-tree
```

After selecting files with Git, verify the exact tracked public set:

```sh
python3 tools/verify_export.py
```

The verifier checks repository boundaries, required notices, source include
closures, and whether every dependency of both board entries is part of the
selected public tree. Git is the content-addressed manifest for the current
tree; `PROVENANCE.json` separately preserves the original migration mapping.

Focused development gates live under `tools/`, `RaspberryPi4/Tests/`, and
`Anvil/Graphics/Vulkan/Tests/`. Emitted AArch64 gates require the external
compiler and an interpreter supplied through `PMF_A64_INTERP` or the documented
repository-local path. The module gate, for example, is:

```sh
python3 tools/module_engine_check.py
```

The interpreter's lazy floating-point dependency has its own isolated host
gate, so a private installation cannot hide a missing exported helper:

```sh
python3 tools/a64/interpreter_dependency_check.py
```

The matching differential diagnostic sources are under
`RaspberryPi4/Examples/Diagnostics/`. They are not installed or run by a normal
build. Follow their hardware-state and recovery prerequisites before any
on-board use.

## Deliberately incomplete work

- **Driver modules:** PMFMOD v1 validation, relocation, and transactional arena
  records exist and have executable tests. Neither board activates the engine
  yet; discovery, loading, service binding, and safe reload are not present.
- **Vulkan compatibility:** the tree contains a pinned core-1.0 vocabulary
  slice, native object/command-buffer lifecycle work, and an explicitly named
  V3D development clear path. Production exposes no Vulkan physical device.
  Complete API vocabulary, memory and synchronization semantics, SPIR-V,
  pipelines, WSI, fault recovery, and CTS remain on the roadmap.
- **Current Pi integration:** lossless high-volume console modeling, rotated
  capture, banner activity, touch, and ongoing network changes must pass an
  integrated hardware run before they are described as released behavior.

See [the module format](docs/MODULE_FORMAT.md),
[Vulkan coverage](Anvil/Graphics/Vulkan/COVERAGE.md), and the
[Vulkan roadmap](Anvil/Graphics/Vulkan/ROADMAP.md) for exact boundaries.
The [compatibility inventory](docs/VULKAN_COMPATIBILITY_STATUS.md) maps the
implemented layers, missing prerequisites, and next resource-backed transfer
slice without claiming a production Vulkan device.

## Safety and support

Anvil can read and write physical memory and can replace a running monitor.
Treat images and addresses as build-specific. The Pi image measures its live
extent, guards monitor-owned memory, and reports the next staging window at
runtime; host tools should refuse an update when that report cannot be
validated unless an operator supplies an independently checked override.

Use the [GitHub issue tracker](https://github.com/ajtaji/Anvil/issues) for
reproducible defects and the [PureMetal forum](https://forum.ajtaji.com/) for
design and hardware discussion. Include the target, source revision, build
command, and a redacted transcript. Never post credentials, NVRAM calibration,
private keys, or machine-specific paths.

## License

Original Anvil source and documentation are available under the [MIT
License](LICENSE). Third-party material is not relicensed. This includes
CYW43455 firmware (redistributed under its own terms), vocabulary taken from
the Khronos Vulkan Registry, and glyph tables generated from DejaVu faces. The
cryptography is original code; BearSSL was read for its constant-time designs
and its licence text is kept as an acknowledgment. See the [licensing guide](docs/LICENSING.md)
and [third-party map](docs/THIRD_PARTY_NOTICES.md).
