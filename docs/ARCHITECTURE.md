# Architecture

Anvil has one portable monitor core and one hardware composition per target.
The top-level board entry chooses the target drivers and includes them in the
order required by the compiler.

## Primary development machine

Zentaji is Anvil's primary development machine. Keep new Anvil commands,
protocols and policy in the shared core so the same source can be built for
Raspberry Pi 4, Pi 5, Pi 3 and other targets. Keep register access, hardware
queues, interrupts and device discovery in the board or architecture backend.
Develop and exercise shared behavior on Zentaji, then qualify each physical
board's backend against the same contract when porting it.

The journaled filesystem belongs in shared storage code behind the block
read, write and flush interface. Zentaji supplies the disk queue adapter.
The existing FAT32 and exFAT drivers remain useful for interchange. Raw
Ethernet on Zentaji uses Anvil's shared network stack through the board's
link interface. The host-socket device is a separate transport. Keep its
registers and rings in the Zentaji backend and use the shared interfaces
where their semantics match.

Zentaji's built-in PureMetal Forge emits code for the Zentaji ISA. Its
editor uses Anvil's shared console and storage services.

## Architecture and privileged execution contract

Anvil supports different CPU architectures. Shared command, scheduler, storage
and boot policy must not contain an ISA instruction, a CPU register name, or an
assumption that every machine has ARM exception levels. Each architecture
backend supplies context entry/return, interrupts, bounded idle, code-cache
synchronization and its payload calling convention; each board supplies its
memory map and devices. A payload's architecture must be validated before
loading or execution. Adding a machine never makes incompatible payload code
executable on it.

**For the existing AArch64 targets, EL3 remains mandatory.** This covers the
firmware-to-compiled-entry handoff, `Main`, the monitor's ordinary services,
and return from a payload. An EL3 stub that executes `ERET` to EL2 or EL1 before
entering Anvil is not compliant. Every board entry must preserve and verify
CurrentEL=EL3; a lower-level entry must fail closed rather than silently run a
second runtime mode.

An existing lower-level firmware or bootloader path is not an exception. Do
not select EL2/EL1 for convenience or because a current stub, UEFI application,
test, or driver already uses it. If a board truly cannot provide EL3 entry,
document the hardware/firmware contract and evidence that rules it out, then
bring the proposed exception to the user before changing the design. There is
no approved lower-level exception by default. A non-Anvil payload may have a
separate deliberate handoff contract, but Anvil itself must remain at EL3 and
resume there.

EL3 entry checks must cover the compiled `_start` and `Main`, an aligned
EL3-selected stack, firmware arguments, DAIF, CPTR_EL3/FP access, VBAR_EL3,
and EL3 MMU/cache state. The board owns those transitions; shared code must
not assume an EL2 bank or downshift privilege for convenience. See the
per-board gaps below before treating any target as compliant.

Zentaji instead requires its documented supervisor mode and ROM-to-image
handoff. It has no ARM EL3. Its boot path is ROM -> Anvil -> payloads; the
`.zex` envelope used by ROM and Anvil's application payload container are
separate contracts. A future architecture must name and verify its own required
privileged context. This does not authorize lowering the existing ARM targets.

This status snapshot distinguishes hardware-verified EL3 paths from open
entry gaps. A lower-level path remains a gap, not an approved exception:

| Board | Observed source entry path | Status under this rule |
|---|---|---|
| Raspberry Pi 3 | The custom Pi 3 stub remains at EL3; the direct monitor captures `x0`, installs EL3 vectors, and refuses a non-EL3 handoff. | Hardware verified on a Pi 3 Model B v1.2 through Build 35: EL3 boot, automatic Wi-Fi/DHCP, TrueType before banner, CRC-checked wireless transfer, and a VideoCore IV offscreen clear. The clear does not establish a Vulkan or scanout backend. |
| Raspberry Pi 4 | `RaspberryPi4/Board/armstub8.asm` retains EL3 and the monitor verifies EL3 at runtime. The supported card configuration must select the custom `armstub8.bin`; stock-stub EL2 is refused. | EL3 hardware acceptance exists from Build 99 onward. Live build 242 also booted with the resident Vulkan/Neon console, Wi-Fi and saved TrueType settings; the packaged image remains older than this live build. |
| Rock Pi 4C | The direct-SD BL3X trust image enters Anvil at EL3. `RockPi4C/Board/board.rockpi4c` captures EL3 state, checks the entry contract and initializes timer/UART before display and storage. | Build 147 boots Anvil at EL3 on the original 4C v1.2. HDMI, SD/exFAT and eMMC file operations are documented in `RockPi4C/README.md`; production Vulkan/Mali rendering remains open. The older U-Boot EL2 route is not the current direct-SD path. |
| Arduino UNO Q | Current board composition is a UEFI application entered at EL1. | Experimental port; EL3 entry is pending. Preserve the existing port while replacing the entry contract; UEFI's current launch level is not evidence that EL3 is impossible. |
| Raspberry Pi 5 | `RaspberryPi5/Board/armstub8-2712.asm` retains EL3. The shared `RaspberryPi4/Board/board.pi4` composition has BCM2712 branches, links at `$80000` and validates the Pi 5 boot placement. `RaspberryPi5/Boot/board.pi4` is an older serial-only probe. | Hardware boot from commit `f385c7b` reached Anvil's `pmf>` at EL3 with HDMI console, caches and board services. PCIe/RP1 inbound-window adoption blocked USB, storage and Ethernet on that boot; later fixes and GPU work require separate validation. |

The Pi 3, Pi 4, Pi 5 and ROCK Pi 4C direct-SD EL3 paths have hardware boot
evidence. UNO Q remains below the required level. Do not resolve that gap by
changing the rule or treating current firmware behavior as an exception.

## Layers

| Layer | Location | Responsibility |
|---|---|---|
| Portable core | `Anvil/Core/*.pbi` | Command loop, parsing, settings, transfer and boot logic, hashes, network orchestration, and hardware-independent commands |
| Hardware contract | `Anvil/Hal/*.pbi` | Named `Hw*` entry points and the versioned service-table ABI |
| Architecture | `Anvil/Kernel/` | CPU-specific entry, exceptions, contexts and idle mechanisms; AArch64 implementations do not define the contract of other ISAs |
| Filesystems | `Anvil/Storage/*.pbi` | FAT32, exFAT, and the one path and partition layer over them. A board supplies a block reader and writer by pointer and nothing else |
| File seam | `Anvil/Storage/hwfile.pbi` | The `HwFile*` / `HwDir*` families over those filesystems, for **any** board with a block device. The board sets three values - mounted, writable, and the ranged writer - and writes no file code of its own. A board without a block device answers the same seam differently; the UNO Q does it through UEFI |
| A/B records | `Anvil/Storage/ab_record.pbi` | The two-slot boot-control record: layout, checksum, state machine and handoff page, driven by two caller-supplied callbacks. No filesystem and no chip in it, so a board reaches its records by name through the shared layer rather than by walking a cluster chain |
| Graphics experiments | `Anvil/Graphics/Vulkan/*` | Shared Vulkan object and command layer with a bounded Pi 4 V3D physical device; other board monitor paths have no production Vulkan hardware backend |
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

Display connection policy is also shared: boards claim one bounded action and
return its result without placing hardware calls in the portable core. The Pi 3
HDMI backend currently adopts that lifecycle; other board compositions compile
it inert until they register their own backend. See
[DISPLAY_CONNECTION.md](DISPLAY_CONNECTION.md) for states, limits, and gates.

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

## Prompt scheduler architecture boundary (2026-11-07)

`Anvil/Core/prompt_scheduler.pbi` owns cooperative service ordering, queued-input
and software-PWM admission, and elapsed idle accounting using 64-bit ticks.
`Anvil/Core/parse.pbi` includes that shared policy. Board compositions select
the implementation of `HwPromptIdleReady()`, `HwPromptIdleWait()` and the
bounded `HwPromptBoardService()` step before
including the parser; the exact contract is `Anvil/Hal/prompt_idle.pbi`.

The three existing compositions using the shared parser select
`Anvil/Kernel/AArch64/prompt_idle.pbi`. It retains their counter-event setup,
EL3 checks, Pi-specific qualification and bounded WFE behavior. The shared core
contains none of those instructions. A non-ARM backend supplies the same two
operations using that CPU's timer/event facilities.

`python tools/prompt_scheduler_check.py --compiler <PureMetalForge.exe>
--zenemu <zenemu.exe>` compiles and executes the actual shared scheduler on
Zentaji with deterministic service adapters. It checks input/PWM refusal,
service fairness, idle utilization and a clock above 32 bits, then compile-checks
the policy and real idle mechanism for AArch64. Current Wi-Fi maintenance
and optional ARM board idle callbacks are preserved. This is a portability proof of
the scheduler, not an Anvil boot or hardware wake proof. The pinned checkout now carries the shipped `Shared/A64/string.pmi` runtime
required by current Forge. Full Pi 4 build 492 compiles the complete composition
with the extracted scheduler/backend; that is compile proof, not new hardware
acceptance. Runtime origin and digest are recorded in `PROVENANCE.json`.

Remaining architecture work includes payload architecture IDs and calling
conventions, relocation handling, privilege/context entry and return, exception
frames, multicore coordination, and the real Zentaji hardware backend. The
existing AArch64-only checks inside PMFBOOT/module validation must move behind
explicit architecture contracts without accepting another ISA's image.

## Payload architecture admission (2026-11-07)

PMFBOOT v2 admission now obtains the required ISA identity, stack alignment
and initial stack extent from the selected backend. The shared
`Anvil/Core/payload_identity.pbi` validates those values and requires the
container's architecture and target to match the independently selected
architecture and board. Its decision code contains no CPU/board enumeration.
`Anvil/Kernel/AArch64/payload_contract.pbi` preserves the existing ID 1,
16-byte stack alignment and initial extent for the current ARM compositions.

PMFBOOT v1 has no architecture field. `HwPmfLegacyV1Allowed()` makes accepting
that historic executable ABI explicit; a new ISA must not inherit ARM v1
acceptance merely because it can parse a header. Reserved-byte, image range,
BSS, digest and placement checks remain in the common engine. No new compiler
architecture ID is allocated by this refactor, and a test-only identity does
not advertise a production backend.

The initial stack-window check uses the backend's extent, rather than a
literal 16 bytes. This proves the first required area only; PMFBOOT still has
no field describing the maximum later stack growth. The service-table calling
convention, payload entry/return code, module ISA/relocation handling and
exception-frame/context code still require architecture backends.

`tools/payload_identity_check.py` executes 24 explicit identity/stack outcomes
and 11 geometry cases on Zentaji. The production-reader fixture exercises
backend-specific alignment, extent and legacy refusal as well as the existing
v1/v2 and placement checks. Pi 4/Pi 5 admission remains mutually exclusive;
a mutant that substitutes the container's target for the board's fails six
cases. The existing full boot-container test still executes a valid ARM
payload and refuses corrupted/overlapping/conflicting-pointer containers.
These desk proofs are separate from physical boot acceptance.

## Payload entry and recovery boundary (2026-11-07)

The common PMFBOOT engine calls `HwPayloadRun(entry, argument)` after validation
and owner preparation. It supplies the service-table address or zero as a local
value; it no longer reads or writes the ARM trampoline's `gGoX0` staging global.
The architecture/board backend owns the register mapping and transition.

The selected ARM gateway retains each board's existing `RunAt` quiesce,
watchdog and return behavior. It clears its staged argument after every return,
including a refusal before RunAt reaches its ordinary cleanup. This prevents
a refused table-bearing launch from leaking that pointer to a later plain run.

Pi 3 and UNO Q now select `Anvil/Kernel/AArch64/payload_call.pbi` explicitly.
The old `Anvil/Kernel/payload_call.pbi` is a compatibility include for that ARM
implementation, not an architecture selector for new machines. The ARM helper
retains register clearing, the full return value, monitor SP recovery and
interrupt masking before the board's recovery hook. If the hook reports failure,
it now remains masked in a wait loop instead of restoring interrupts through
unknown exception state. A failed recovery cannot safely return to normal work.
Pi 4 retains its existing board-specific trampoline and its own fail-stop policy;
unifying those two ARM implementations is separate work.

`tools/payload_boundary_check.py` executes the real gateway on Zentaji with a
controlled board adapter, the exact common PmfEnter procedure on emitted ARM
with controlled owner providers, and the actual ARM trampoline. It checks
zero/table arguments, preparation/refusal/cleanup, poisoned registers, a
full-width result, destroyed-SP recovery, masked callback entry and a failed
recovery park. A private copy restoring the old ignored-recovery bug must fail.
This is bounded desk proof, not physical entry/recovery acceptance and not a
Zentaji Anvil boot. A real Zentaji transition, its callable payload startup,
service-table calling convention, exception/context code and module relocation
backend remain to be implemented.

## Architecture-owned payload state (2026-11-07)

Common state owns the selected payload entry and returned value. AArch64's
saved monitor stack and x0 staging slots now live in
`Anvil/Kernel/AArch64/payload_state.pbi`. Pi 4 selects this state explicitly;
the common ARM trampoline and gateway select it through a guarded include.
This lets another CPU use `Anvil/Core/state.pbi` without adopting ARM's
register staging or stack-recovery storage. The focused boundary fixtures
include that production state rather than redeclaring copies of its globals.

The service ABI's entry section now states architecture-neutral requirements.
[ABI_AARCH64.md](ABI_AARCH64.md) owns the existing register/stack/interrupt
contract, including the mandatory EL3 requirement and the unresolved UNO Q
entry gap. The old common ABI prose describing EL2 entry and a future
privilege downshift was stale; it does not override the current architecture
rule. No slot, signature, ABI version or trampoline instruction changed.
Other remaining architecture dependencies in service diagnostics, modules and
context handling still need their own CPU backends.

The updated boundary check also compiles and executes the **actual complete**
`Anvil/Core/state.pbi` closure on Zentaji with no architecture adapter selected.
It checks zeroed independent buffers, full-width entry/result values and the
real display connection policy through attach, redraw, spaced absence probes
and detach. The ARM entry/recovery fixture includes the real private state
file and still kills the old ignored-recovery mutant. Full monitor compilations
passed for Pi 4 build495, Pi 3 build105 and UNO Q build103 using production
Forge; these are desk artifacts, not new physical acceptance or staged card
releases. Full Anvil/Zentaji boot remains open.

## Zentaji clock and bounded idle backend (2026-11-07)

`Zentaji/Board/prompt_idle.pbi` now implements the common idle HAL over real
per-core timer MMIO and the shipped Zentaji CPU runtime, preserved verbatim
in `Anvil/Kernel/Zentaji/zen_cpu.pbi`. The board explicitly reserves its
calling-core timer and owns line1 admission; the backend does not reconfigure
global timers or interrupt-controller routing. It masks delivery around WFI,
which still wakes on an admitted interrupt, clears its timer reason and restores
the prior STATUS before returning. The shared scheduler continues to own work,
input and utilization policy. See [the Zentaji bring-up contract](../Zentaji/README.md)
for registration, bounds, resource ownership and proof scope.

The actual backend and shared scheduler pass32 native/twin full-state/RAM cases
on cores0/1, plus a two-second headless live run with active service lanes and
recorded replay. Initial measured startup-adjusted CPU was0.015625s over1.994336s
wall. No complete Zentaji monitor is linked yet; ROM boot, vectors, remaining
board devices/runtime and the production payload ABI are still open.


## Shared console byte policy and Zentaji transport (2026-11-07)

The byte-string and CRLF output procedures formerly repeated in Pi 4, Pi 3
and UNO Q now live once in `Anvil/Core/console_bytes.pbi`. Each existing
transport includes those unchanged bodies. Byte-input CRLF state similarly
belongs to `Anvil/Core/input_byte_state.pbi`, included at the original board
positions and by the shared input queue. This keeps normalization state alive
across command lines without requiring a new machine to declare board globals.

`Zentaji/Board/console.pbi` supplies actual serial-0 MMIO transport, preserving
hardware state on adoption and detach. It refuses conflicting DMA ownership,
bounds transmit pressure and drain, and uses the qualified timer/WFI backend
for healthy blocking input. The focused console check executes the production
transport plus the existing shared input queue and line editor. Fourteen exact
output/full-state/RAM cases and a two-second live timed-input wake pass against
native and independent twin execution. See the Zentaji contract for limits,
resource ownership and the still-open Print/background-message/full-prompt work.


The extraction preserves both helper procedure bodies exactly across all three
existing ARM transports. Counted full monitor builds pass with signed production
Forge `7d68c0c3d`: Pi 4 build496, Pi 3 build106 and UNO Q build104. These are desk
compilation proofs; no physical deployment or card release was performed.


## Shared message routing and actual Zentaji ReadLine (2026-11-07)

`Anvil/Core/console_messages.pbi` owns the background-message byte ring and
nested bracket policy previously repeated by the three ARM transports. All
four consoles now use it. Registration is separate from the concrete unbound
callback target: absent registration preserves ordinary diagnostic output.
Overflow drops newest and counts it; line/high-water and outermost-close drains,
fatal abandon and callback guards retain the existing policy. CPU/device output
is still the selected transport's responsibility.

Zentaji selects the shipped pure-source 64-bit formatters in
`Shared/A64/string_out.pmi` over its PrintChar sink. There are no ARM instructions
in that library; standalone provenance records its exact origin and digest.
Forge's Zentaji Print/PrintN routing creates ordinary calls before shared
recursion/callback analysis, including the newline call. The compiler does not
choose a device or format bytes internally.

The actual complete shared parse/ReadLine, event queue, editor, scheduler and
message log now execute together on Zentaji. Five native/twin full-state/RAM
cases verify editing, parsing, CRLF, Ctrl-C, normalized keyboard Tab refusal,
truncation and forced service turns during sustained input. The two-second live
ReadLine proof uses actual serial/timer/WFI hardware and measured additional
CPU0.078125s over1.998580s wall, with exact recorded native/twin replay. Only
unavailable service/device providers are counted test adapters. This is neither
a full Anvil image nor a ROM-to-monitor boot proof.

Counted full ARM monitor builds pass with signed production Forge `2f134c743`:
Pi4 build497, Pi3 build107 and UNO Q build105. These are desk artifacts, not
physical deployments or card releases. Startup/vectors, storage, the command
composition and production payload/service ABI still block full Zentaji boot.


## Zentaji startup ownership and wrapped guest maps (2026-11-07)

`Anvil/Kernel/Zentaji/startup.zen` is architecture entry before compiled code,
with supervisor/reset handoff validation, a stack below the ROM's reserved 1 MB,
all 64 fail-stop vectors and a versioned context in r3. Boot table/source stay
in r1/r2 and interrupts stay masked. `boot_context.pbi` owns the context fields
and validation. No ARM privilege model or register contract is imposed on this
backend. Recovery/resumption, secondary startup and the production payload ABI
remain separate work.

`tools/zentaji_boot_image.py` keeps compiled bytes/addresses and original BSS
positions fixed, appends aligned startup/vectors and publishes ZEX plus source
map, assembly and metadata as a rollback transaction. Native assembler rows
supply the startup locations; original language rows/hashes remain unchanged.
All are bound to the final image. An actual native debugger break/step checks
both sides. The packer does not assign a Zentaji PMFBOOT identity or pretend to
supply the rest of the monitor composition.

Twenty native/twin full-state/RAM cases cover successful/refused entry, owned
resources, BSS, damaged-SP BRK, TX-block ownership, NMI/watchdog and both real ROM
boot routes. Both routes also reach the actual shared ReadLine/input/editor/
scheduler/messages over the hardware backend, with timed input. Unavailable
service/device providers remain counted adapters. This is the ROM/startup/core
composition proof; a production command composition, storage and payload/service
ABI are still required for a complete Anvil image. No ARM source or native
compiler/emulator executable changed, so unchanged monitor builds were not rerun.
