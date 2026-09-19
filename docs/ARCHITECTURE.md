# Architecture

Anvil has one portable monitor core and one hardware composition per target.
The top-level board entry chooses the target drivers and includes them in the
order required by the compiler.

## Layers

| Layer | Location | Responsibility |
|---|---|---|
| Portable core | `Anvil/Core/*.pbi` | Command loop, parsing, settings, transfer and boot logic, hashes, network orchestration, and hardware-independent commands |
| Hardware contract | `Anvil/Hal/*.pbi` | Named `Hw*` entry points and the versioned service-table ABI |
| Architecture | `Anvil/Kernel/*.pbi` | AArch64 facts that belong to no chip: the EL2/EL3 exception vectors and the scheduler's contexts |
| Filesystems | `Anvil/Storage/*.pbi` | FAT32, exFAT, and the one path and partition layer over them. A board supplies a block reader and writer by pointer and nothing else |
| File seam | `Anvil/Storage/hwfile.pbi` | The `HwFile*` / `HwDir*` families over those filesystems, for **any** board with a block device. The board sets three values - mounted, writable, and the ranged writer - and writes no file code of its own. A board without a block device answers the same seam differently; the UNO Q does it through UEFI |
| A/B records | `Anvil/Storage/ab_record.pbi` | The two-slot boot-control record: layout, checksum, state machine and handoff page, driven by two caller-supplied callbacks. No filesystem and no chip in it, so a board reaches its records by name through the shared layer rather than by walking a cluster chain |
| Graphics experiments | `Anvil/Graphics/Vulkan/*` | Architecture-neutral Vulkan-compatible vocabulary and lifecycle foundation; no production physical device is exposed |
| Pi 4 composition | `RaspberryPi4/Board/*.pi4` | BCM2711 memory map, boot order, HAL implementations, console, storage, display, and board policy |
| Pi 4 drivers | `RaspberryPi4/Lib/*.pi4` | BCM2711 and attached-device implementations |
| UNO Q composition | `ArduinoQ/Board/*.unoq` | QCM2290/UEFI memory map, console, file services, and HAL implementations |
| UNO Q drivers | `ArduinoQ/Lib/*.unoq` | QCM2290 hardware implementations currently used by the board entry |

Two of those portable name sets were real, working, three-board seams that
were written down nowhere until 2026-09-18: **the console bytes** (the
`Uart*` set, the `UartMessage*` bracket, and the three lowercase names the
compiler's `Print` router resolves) and **the time** (`Ticks`, `TickHz`,
`TimerInit`, `Micros`, `millis`, `delayMicroseconds`, `delay`). Roughly
1,400 calls under `Anvil/` resolve to the first and about 150 to the second.
Both are now declared in `Anvil/Hal/hal.pbi` beside every other seam, with
their contracts and their two deliberate oddities: renaming one of the
print-router names produces a confusing front-end message rather than a link
error, and `delay(0)` answers 1 while `delayMicroseconds(0)` answers 0 on
every part in the fleet.

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

The prompt spin also takes the part's temperature once a second, armed fan or
not, and publishes it for anything that only wants to show one. A reader on a
paint path cannot ask a seam: a seam call is a call through the service table,
so the compiler must assume it reaches everything in that table, and the screen
service is reached from the boot walk. See
[BANNER_STATUS_ROW.md](BANNER_STATUS_ROW.md).

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
next boundary. The board currently enumerates nine monitor-owned regions for
the shared address guard:

1. the live, rounded image extent;
2. the 16 MiB BSS/data window at `$0D000000..$0DFFFFFF`, immediately above
   the separately protected Vulkan heap at `$0C000000..$0CFFFFFF`;
3. the reserved autoboot page at `$001FF000..$001FFFFF`;
4. the DSI framebuffer at `$08A00000..$091FFFFF`;
5. reserved raw-secondary stacks;
6. the module arena and staging window;
7. the boot phase record;
8. the screenshot capture area;
9. the Vulkan device-memory heap.

`HitsMonitor()` walks that board-owned list. This keeps the portable core free
of Pi addresses while refusing writes into code, variables, the persistent
autoboot cell, display scanout/draw buffers, module arena, capture, and Vulkan
heap. The image gate checks emitted BSS bounds against the data reservation;
the screenshot gate checks its window against the other named regions.

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

The touch keyboard's draw list is a consequence of that separation: an item is a
label and a box, and the renderer picks the face and centres what it draws. Key
labels are set in an anti-aliased face on both tiers, falling back to the cell
font only where that face does not fit the box. On the GPU tier the band is
composed by the CPU in logical coordinates and presented through the one
transpose, and each GPU frame carries the presented band back into its render
target - the same arrangement that puts the banner's photo and smooth title on
that tier. See [TOUCH_KEYBOARD_LABELS.md](TOUCH_KEYBOARD_LABELS.md).

`Anvil/Graphics/Vulkan/` builds above that separation. It currently provides a
partial registry-derived core-1.0 vocabulary, native object and command-buffer
state, and an explicitly named V3D development clear path. Production device
enumeration remains empty. Memory objects, synchronization, SPIR-V, pipelines,
WSI, fault recovery, and conformance are future layers; see
[`COVERAGE.md`](../Anvil/Graphics/Vulkan/COVERAGE.md).

## Source extensions, and why they decide what can be shared

Shared includes use `.pbi`, which carries no target identity. Pi 4 hardware
uses `.pi4`; UNO Q hardware and its entry use `.unoq`. The external command-line
compiler already maps `.unoq` to the UNO Q target. See
[PORTABILITY.md](PORTABILITY.md) for the current IDE limitation.

**A library exists once. Boards differ in the interface under it.** Where a
file contains no chip knowledge it belongs in a shared folder under a `.pbi`
name, and every board includes that one file.

The extension is not a label. The compiler refuses a cross-chip include by
name, at the first one it meets, rather than letting a board collapse into
undeclared-register errors inside a library nobody meant to pull in. That
refusal is correct, and it has a consequence worth stating: **a file with no
chip in it is still unreachable from another board while it carries a board's
extension.** Architecture-neutral code has to be moved and renamed before it
can be shared at all, and a file left where it is guarantees that the next
board writes its own copy.

**`tools/layering_check.py` is the gate that keeps this true**, and it works
by resolving names rather than walking includes, because the include model is
flat: a shared file calls a board procedure with no include edge at all, so a
single non-test downward include sits in front of 929 downward calls. It
refuses a shared file that calls a name only one board defines unless that
name is declared as a seam in `Anvil/Hal/hal.pbi`, refuses a downward include
or a new board-extension file under `Anvil/`, refuses a second implementation
of a protocol the tree already owns somewhere, refuses a call into another
file's lower-case private namespace, and refuses one name defined twice in
files that can be linked into one image. Today's findings are recorded in
`tools/layering_ratchet.json` as a ratchet that may only shrink. Run
`python tools/layering_check.py` before committing; see
[LAYERING.md](LAYERING.md) for the rules, the measured counts and the list of
what the parser cannot see.

`Anvil/Kernel/exceptions.pbi` is the first library moved on that reasoning.
It was `RaspberryPi4/Lib/exceptions.pi4` and contained no reference to any
BCM2711 address, register or peripheral - only AArch64 EL2 and EL3 vector
tables and the frame they save. The move changed one include line in each of
its five dependents and the Pi 4 image came out **byte-identical**, which is
the standard a move of this kind has to meet.
