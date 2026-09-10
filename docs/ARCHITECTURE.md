# Architecture

Anvil has one portable monitor core and one hardware composition per target.
The top-level board entry chooses the target drivers and includes them in the
order required by the compiler.

## Layers

| Layer | Location | Responsibility |
|---|---|---|
| Portable core | `Anvil/Core/*.pbi` | Command loop, parsing, settings, transfer and boot logic, hashes, network orchestration, and hardware-independent commands |
| Hardware contract | `Anvil/Hal/*.pbi` | Named `Hw*` entry points and the versioned service-table ABI |
| Graphics experiments | `Anvil/Graphics/Vulkan/*` | Architecture-neutral Vulkan-compatible vocabulary and lifecycle foundation; no production physical device is exposed |
| Pi 4 composition | `RaspberryPi4/Board/*.pi4` | BCM2711 memory map, boot order, HAL implementations, console, storage, display, and board policy |
| Pi 4 drivers | `RaspberryPi4/Lib/*.pi4` | BCM2711 and attached-device implementations |
| UNO Q composition | `ArduinoQ/Board/*.unoq` | QCM2290/UEFI memory map, console, file services, and HAL implementations |
| UNO Q drivers | `ArduinoQ/Lib/*.unoq` | QCM2290 hardware implementations currently used by the board entry |

The core calls portable names. A board owns the choice of hardware and the
implementation behind those names. Payloads use the versioned service table
instead of taking a second copy of hardware with physical state.

## Bootloader and mini-kernel role

Anvil remains resident while a payload runs. It owns physical state such as
storage, interrupt control, clocks, console paths, network links, display, DMA,
and watchdogs. The payload container is verified before entry and may request
services through the ABI table. Pure computation can remain in a payload.

Returning payloads must preserve the resident monitor and devices they have
not claimed. Hardware controller lifetime is separate from logical interface
identity: a GENET restart rebuilds its registers and rings without clearing
addresses, lease deadlines, aliases or the radio's state. The return path
evaluates elapsed lease time before using a restored network console. See
[PAYLOAD_LIFECYCLE.md](PAYLOAD_LIFECYCLE.md) for the exact sequence and outstanding
hardware checks.

## Cooperative services and wall time

The prompt advances bounded services rather than running an unbounded network
operation in a clock callback. The common wall-clock core anchors UTC to a
monotonic hardware counter, with distinct unset, restored-floor, manual and
SNTP sources. Its network service validates the selected interface and reply
transaction, but plain SNTP is not cryptographically authenticated. Public
defaults use UTC; a named zone is an explicit saved setting, not an inference
from a server location. Boards without a network backend retain the common
manual clock and timezone interface. See [WALL_CLOCK.md](WALL_CLOCK.md).

On the Pi, `ScreenServiceTick` pumps pending output and bounded banner updates.
Boot and long radio phases invoke it at cooperative boundaries, outside the
character producer and cryptographic primitive internals. Early output is
retained until a scanning panel exists; that retained history is not described
as live presentation on a previously dark panel.

## Driver modules: format and placement engine only

`Anvil/Hal/module_format.pbi` is the canonical numeric definition of the
PMFMOD v1 container. `Anvil/Core/mod_container.pbi` validates the complete
container, integrity digest and AArch64 relocations before mutation.
`Anvil/Core/mod_arena.pbi` then obtains an arena from board-owned `HwMod*`
functions, copies and relocates the image, zeroes padding/BSS, performs a
mandatory code-cache synchronisation, and commits a READY record last.

The engine is load-once placement infrastructure, not a working driver loader.
READY means verified, relocated, zeroed and cache-synchronised only. The files
are not wired into either board composition and no board currently supplies a
module arena. See [MODULE_FORMAT.md](MODULE_FORMAT.md) for the pinned binary
contract and current HAL seam.

None of these are implemented in this export:

- board arena reservation or module-file ingestion
- `MODULES.TXT` parsing
- hardware discovery and compatible-id matching
- module global-initializer, probe, init, quiesce, or service binding calls
- `mod list`, `mod info`, `mod load`, or `mod reload`
- stable service trampolines, in-flight accounting, or transactional reload

The planned first conversions are the PWM fan, Goodix touch, DSI panel
power/backlight controller, and CYW43455 radio. Until the loader lands, they
remain compiled into the Pi 4 image where included.

An earlier module design reserved `$08A00000..$091FFFFF` as a fixed arena.
That range is now occupied by the DSI framebuffer and must not be implemented
as written. A future board implementation must supply a newly reserved,
non-overlapping range through the module-arena HAL and retain it in the board's
address-safety policy. The core engine contains no fallback address.

## Runtime memory ownership

The Pi image reads its emitted `__image_start__`/`__image_end__` symbols at
runtime. Its code reservation is the live image rounded up to a one-megabyte
boundary; the first low payload window and host staging address begin at the
next boundary. The board currently enumerates four monitor-owned regions for
the shared address guard:

1. the live, rounded image extent;
2. the BSS/data window at `$08200000..$089FFFFF`;
3. the reserved autoboot page at `$001FF000..$001FFFFF`;
4. the DSI framebuffer at `$08A00000..$091FFFFF`.

`HitsMonitor()` walks that board-owned list. This keeps the portable core free
of Pi addresses while refusing writes into code, variables, the persistent
autoboot cell, and display scanout/draw buffers. The current host proof checks
all four regions and confirms that the computed staging page remains clear.

The UNO Q obtains the UEFI-loaded image base and byte count from the loaded
image protocol, rather than trusting its link address. Its BSS is placed at
`$70800000`, eight megabytes above the nominal `$70000000` link base.

A recent Pi hardware build proved the dynamic map, cache-enabled boot, native
DSI scanout, HDMI, DMA-backed console, and both wired and wireless console
paths. The current source tree is ahead of that build: later display, touch,
and network integration still needs a complete supervised hardware pass. It is
therefore not hardware-release-approved. Host update tools must parse a
validated `map` response from the running monitor and refuse unknown or
malformed output unless an operator supplies an independently validated
address override.

The UNO Q target currently runs as a UEFI application. UEFI console and file
services and GPIO have been exercised on hardware; most native peripheral,
network, and accelerated-display work remains incomplete.

## Rendering boundary

The Pi display composition keeps display ownership separate from rendering.
HDMI and DSI are presentation surfaces; Neon/V3D is an optional rendering
tier, and CPU/DMA paths remain valid fallbacks. Logical console geometry and
physical scanout orientation are distinct so landscape text, capture, cursor,
and touch can share one mapping contract.

`Anvil/Graphics/Vulkan/` builds above that separation. It currently provides a
partial registry-derived core-1.0 vocabulary, native object and command-buffer
state, and an explicitly named V3D development clear path. Production device
enumeration remains empty. Memory objects, synchronization, SPIR-V, pipelines,
WSI, fault recovery, and conformance are future layers; see
[`COVERAGE.md`](../Anvil/Graphics/Vulkan/COVERAGE.md).

## Source extensions

Shared includes use `.pbi`, which carries no target identity. Pi 4 hardware
uses `.pi4`; UNO Q hardware and its entry use `.unoq`. The external command-line
compiler already maps `.unoq` to the UNO Q target. See
[PORTABILITY.md](PORTABILITY.md) for the current IDE limitation.
