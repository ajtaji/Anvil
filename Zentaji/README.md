# Zentaji backend bring-up

The machine has a real clock, bounded prompt-idle backend and serial console transport. This is not yet
a full Anvil monitor image, a ROM boot proof, or a self-hosted Forge build.
The shared monitor remains the source of scheduler and command policy.

`Board/clock.pbi` supplies `Ticks()` from the CPU's TIME register and `TickHz()`
from the timer device's read-only frequency. `Board/prompt_idle.pbi` selects the
Zentaji CPU runtime and implements the three prompt-idle HAL methods. The
runtime in `Anvil/Kernel/Zentaji/zen_cpu.pbi` is the byte-identical shipped
guest library, with its source revision and hash in `PROVENANCE.json`.

The board's interrupt owner must reserve the calling core's timer and configure
line 1 as a level source, enabled above that core's interrupt threshold. Anvil
must already be running in its required supervisor context. Then call
`ZentajiPromptIdlePrepare(maxMicroseconds)` with a 50–2000 microsecond deadline.
It refuses an active timer, a nonzero period or pending timer status, an
inadmissible interrupt, a busy interrupt context, or a second reservation.
It reads the machine frequency and rounds the interval down; an interval
smaller than one machine tick is refused.

The backend uses the calling-core MMIO aliases. It never changes global timers,
other cores' timers, line configuration/routing, interrupt enables or thresholds.
Before each wait it rechecks its reservation and interrupt admission, masks
delivery, and rechecks again. It arms one bounded timer and executes actual
`WFI`. WFI wakes with delivery masked; another enabled pending source can return
early. The backend disarms its timer, clears only its FIRED reason, restores the
inactive compare value, then restores the original STATUS. It does not consume
another interrupt or require an idle-timer handler. Timer history counters reflect
the use of this reserved resource.

`ZentajiPromptIdleRelease()` unregisters an inactive, unchanged reservation.
It can release after the board disables interrupt admission, but refuses a
foreign timer configuration rather than overwriting it. The board owns timer
and interrupt-controller configuration before registration and after release.
The monitor serializes prepare/release and keeps one prompt registration at a
time. Other code must not use that timer while it is reserved. The deadline bounds
hardware timer scheduling; host scheduling latency and service execution are
separate from that interval.

The actual `Anvil/Core/prompt_scheduler.pbi` decides whether work, queued input
or software PWM allows sleeping. `HwPromptBoardService()` currently has no
additional board maintenance hook.

Run the focused proof with the current external Forge and matching Zentaji tools:

```text
python tools/zentaji_idle_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

The check compiles the production backend and shared scheduler, compares complete
image bytes with independent assembly, and executes 32 native/twin CPU-state and
RAM cases on cores 0 and 1. It exercises reservation and admission failures,
timer preservation, input admission, early interrupt wake and STATUS preservation.
Only unrelated service lanes and queued-input providers are adapters. Timer,
CPU, clock and interrupt behavior use actual emulated hardware. A two-second
headless live run keeps service lanes active and verifies startup-adjusted CPU
use below 20%, with exact recorded native/twin replay. This is currently a
Windows execution proof; Linux execution and visible input remain unverified.

`Board/console.pbi` adopts serial port 0 without resetting it, draining RX,
changing baud or clearing counters. The monitor must exclude block/DMA users;
adoption refuses active TX/RX block transfers. Reads preserve all byte values,
including NUL and 255. Read readiness never consumes input. Healthy blocking
input uses the qualified timer/WFI backend above; missing idle admission or
lost transport ownership returns -1 and records a fault instead of spinning.

Transmit pressure, bounded polling and drain have a 4096-probe ceiling and a
100 ms machine-time deadline. These ceilings are upper bounds, not promised
wait durations; a fast polling loop may exhaust its probes earlier. Drain checks
actual timed TX completion. Baud changes require an empty, unowned transmitter;
zero selects the machine's unpaced mode. Logical detach preserves configuration
and queued bytes. Drop reporting combines rejected writes with the hardware
counter delta for the attachment, frozen at detach.

`Anvil/Core/console_bytes.pbi` owns the existing byte-string and CRLF output
helpers shared by all four transports. `Anvil/Core/input_byte_state.pbi` owns
CRLF normalization state used by the shared input queue. The existing ARM
board-global compositions include this guarded state at their original position.
The Zentaji console proof compiles the actual shared input queue and line editor;
it dispatches their events without duplicating their implementation.

```text
python tools/zentaji_console_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

Twenty native/twin full-state, RAM and exact-output cases cover byte/UTF8
output, nonconsuming readiness, editing/cancel and cross-line CRLF, pressure,
drain, adoption/detach, baud validation, DMA ownership and timer-backed input.
They also check nested/partial/newline message diversion, unbound output,
drop-newest overflow, FIFO wrap, fatal abandon and unregister/register behavior.
A two-second headless live input wait also has exact recorded native/twin replay
and checks startup-adjusted host CPU below 20%. This is a Windows component
proof. `Anvil/Core/console_messages.pbi` now owns background-message byte
routing once for all four transports. A registered drain receives bracketed
output; ordinary console bytes stay on the wire. With no drain, brackets do
not divert anything. A concrete unbound callback target plus a separate bound
flag makes this optional service compile in standalone diagnostics without
claiming that a log has been installed. Registration/writes remain serialized;
the drain must not print, and callback entry is guarded against reentry.

The console supplies `PrintChar` over `UartWrite` and selects the existing
`Shared/A64/string_out.pmi` guest formatters unchanged. Despite the historical
folder name, those procedures contain no CPU instructions or hardware access.
Their revision and byte hash are recorded in `PROVENANCE.json`. Forge routes
Print/PrintN to ordinary formatter calls before shared call analysis, so those
edges also participate in recursion and callback checking. Dynamic `.s` runtime
operations and floating conversion-to-text libraries remain separate work.

```text
python tools/zentaji_prompt_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

This compiles the complete production `parse.pbi`/ReadLine, input queue, editor,
message log and scheduler with the real Zentaji console/timer backend. Five
native/twin full-state/RAM/exact-output cases cover editing, cross-line CRLF,
case-insensitive words, full-width hex parsing, Ctrl-C, normalized keyboard Tab
refusal in the log, line truncation and fair background service. Serial Tab is
intentionally ignored by the existing byte translator; the refusal case feeds
a normalized key event through the real event API. A two-second live ReadLine
wait keeps service lanes and message routing active, checks CPU below 20%, and
has exact recorded native/twin replay. Providers for unavailable display, mouse,
network, radio maintenance and log-file notification are counted test adapters.
They are not implemented Zentaji devices. This is still a component composition,
not a complete monitor image, command dispatcher, ROM boot or physical input proof.

## Owned privileged entry and ROM handoff

`Anvil/Kernel/Zentaji/startup.zen` now establishes Anvil's supervisor entry.
It runs before an ordinary compiled frame and uses no incoming stack. It checks
core 0, reset STATUS, disabled page protection, the documented device table and
boot source, actual RAM and image/stack separation. Successful entry installs
a 4 KB-aligned table for all 64 causes and a private stack below the ROM's top 1 MB
workspace. Other cores stay parked. Interrupt delivery stays masked; the board
still owns routing and the later idle-timer reservation.

Compiled entry receives r1=device table, r2=boot source and r3=context, with
r4..r15 zero and a valid return link. Callable `--entry-returns` startup
may return its result to a final halt; ordinary Forge startup halts itself.
The 128-byte version1 context records the incoming stack, actual RAM,
owned stack bounds, vectors and image extent. `boot_context.pbi` supplies the
field constants and bounded validation for the compiled monitor. Default stack
size is64 KB; the packer accepts aligned sizes 16 KB..1 MB and startup checks that
the selected size fits the actual machine. At least 2 MB RAM is required.

Every unhandled cause reports cause/PC/info on serial0 and halts. Causes 13..15
use NEPC/NEINFO; other causes use EPC/EINFO. The report has no stack dependency
and bypasses ordinary console/message state. Raw output skips an active TX block
transfer and has a finite 4096-probe budget per byte under FIFO pressure. This is
best-effort fail-stop reporting, not trap resumption, page-protection recovery,
payload return recovery or secondary-core startup.

Wrap a Forge result and its matching compiler source map:

```text
python tools/zentaji_boot_image.py compiled.zex anvil-entry.zex --zasm <zasm executable>
```

The original payload stays at its original addresses, without relocation. BSS
becomes zero bytes at its original addresses before the appended startup slab.
The output is a supervisor ZEX with a new entry and CRC; input flags/reserved
fields, extents and CRC are checked, with a 64 MB input payload/BSS pack limit.
The tool emits `.boot.json`, `.asm` and `.zmap` beside the image and publishes
all four as one rollback transaction. It refuses collisions with its compiler
inputs, input source map or startup source. This tool supplies architecture
entry, not a board composition or PMFBOOT architecture identifier.

The merged map retains the compiler's exact instruction rows and source hashes.
New startup rows come from the production ASM assembler, rebound to the actual
startup file and physical lines. Embedded guest data, padding and LIQ trailing
words acquire no synthetic breakpoints. The map hashes the final wrapped image;
invalid input identity, rows or merged limits refuse before publication.

```text
python tools/zentaji_startup_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

Twenty real native/twin full-state/RAM cases check direct entry, RAM rounding,
owned SP/EVEC/context, rejected table/status/core/source/protection/size/overlap,
original BSS, minimum stack, callable entry return, damaged-SP BRK and raw TX-block exclusion, NMI and
watchdog reporting. All64 vector slots are independently checked. Both actual
ROM boot routes load the compiled entry and then also reach the complete shared
ReadLine composition with timed serial input and service/message activity.
The latter still uses the previously documented counted adapters for unavailable
hardware. Native source break/step reaches startup and original language source;
publication rollback, input collisions and damaged maps are checked too.
Actual host MCHECK injection, visible input and Linux remain unverified.

Next are the production monitor command composition and startup integration,
storage facade integration and durable host disk backing,
the remaining runtime/compiler facilities and production payload/service ABI.
ROM must load Anvil, and Anvil must then reach the shared prompt and load
applications. The built-in Forge must ultimately target Zentaji itself only.


## Block storage and shared FAT32

`Zentaji/Board/disk.pbi` supplies the existing filesystem range callbacks over
Zentaji's 4096-byte block device. Register `ZentajiDiskRead`, `ZentajiDiskWrite`
and `ZentajiDiskFlush` with `FatSetRangeReader`, `FatSetRangeWriter` and
`FatSetBlockFlusher`. The shared filesystem continues to use 512-byte sectors;
partial physical-block writes use read/modify/write. There is one serialized
controller owner on one core and one outstanding command. Other medium writers
must be excluded for the entire acquisition, including read/modify/write.

The board first establishes normal supervisor context with masked delivery,
configures its bounded idle timer, then calls `ZentajiDiskOpen(instance)`.
Acquisition requires exclusive ownership and a quiesced previous owner; disabled
registers do not prove that old DMA has finished. The driver checks the device
table before accessing a disk instance, refuses enabled or dirty controllers,
and retains the old disabled ring configuration and IRQ enable for close.
It does not configure INTC or reserve another timer. A routed disk IRQ can wake
it early; otherwise the reserved per-core timer bounds each sleep.

`ZentajiDiskRead(lba,count,buffer)` and `ZentajiDiskWrite(lba,count,buffer)` use
512-byte units and return 1 on success, 0 on refusal or failure. Zero-length
requests are allowed after state/range validation. RAM extents and overlap with
private driver storage are checked. `ZentajiDiskSectors()` reports capacity in
512-byte sectors. `ZentajiDiskTimeoutUs(us)` selects a representable 1..2000000 us
deadline; the default is two seconds, with an additional finite probe budget.
`ZentajiDiskLastError()`, `ZentajiDiskErrorText()` and
`ZentajiDiskDeviceStatus()` distinguish admission, device and completion errors.

Every DMA uses private aligned rings and a private bounce buffer. A timeout
quarantines them until a matching completion actually retires. Caller RAM can be
reused after a failed call returns. A timed-out write can still modify the medium
later; failure is not rollback or a multi-sector transaction. `ZentajiDiskClose()`
is nonblocking and refuses while DMA is pending or ownership/completion identity
is uncertain. Successful close restores the acquired disabled configuration and
resets the emptied private queue indices. Mode 0 is closed, 1 ready, 2 quarantined.

Persistent emulator `disk` bindings now sync FUA writes and FLUSH to the host
image before successful completion. A host I/O failure returns status4 and raises
MCHECK on the latched queue producer core; partial host writes may have occurred.
Use exclusive ownership of the image. Explicit `disk-memory` bindings isolate
writes for debugger snapshots/history. Recordings preserve initial disk bytes
in separate sidecars and persistence outcomes; replay never writes source images.
Linux execution and physical power-loss behavior remain unverified. The ROM now resets its empty owned queues after both boot READs
complete, then disables and clears their descriptors before entry. The driver can
therefore acquire that same boot disk without treating disable as cancellation.

```text
python tools/zentaji_disk_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

Twenty actual Forge/reference-assembly/native/twin cases compare complete state,
RAM and independently expected medium bytes. They cover unaligned and cross-4KB
I/O, full and partial writes, phase wrap, read-only/bounds/context/ownership
refusals, flush, device errors, timeout quarantine, late DMA, caller-buffer reuse,
corrupt completions and actual core1 execution. Scenario6 uses an actual persistent binding and requires the complete host image
to equal the independent expected medium after FUA writes and FLUSH. Other
transport cases use explicit private memory bindings.

A further case compiles the unchanged full `Anvil/Storage/fat32.pbi`, binds these
real disk callbacks, and runs under Anvil's owned supervisor startup, stack and
vectors. It mounts an MBR partition, walks root/allocation metadata with expected
corrupt-chain refusals, reads a fragmented file, rewinds, reads chunks and checks
EOF/not-found behavior. Native/twin state and RAM match, independent expected file
bytes match, and the read-only medium stays unchanged. This is a component proof
with direct owned startup, not the full storage facade, exFAT,
a writable filesystem transaction proof or the complete monitor command loop.


```text
python tools/zentaji_disk_boot_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

This boots the compiled driver through the actual ROM on disk0 and disk15, enters
Anvil's owned supervisor startup, and reacquires the same disk. It reads the boot
header and payload using 512-byte range callbacks, refuses a read-only write,
closes, reopens and reads again. Full native/twin state and RAM match; independent
header/payload bytes match; final queues are empty and disabled; host images stay
unchanged. The fixture uses the production Forge startup (including its global
initialization) and a bounded one-million-instruction allowance. The native tools
must include the ROM queue-reset fix. This closes boot-disk reuse; it does not link the complete monitor/storage
composition. Durable writable backing is covered separately by the persistence
and actual driver checks.


## Shared file services and portable clock policy

```text
python tools/zentaji_storage_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

This composes the complete unchanged FAT32, exFAT, filesystem dispatch and
HwFile/HwDir libraries with the actual Zentaji queue driver, supervisor startup,
HAL vocabulary, console and portable wall clock. The executed volume is FAT32;
exFAT is compiled and participates in detection/fallback, but an actual exFAT
volume remains a separate proof. The fixture assigns the documented mounted,
writable and writer values after mounting; it does not introduce a second file
implementation or claim a production board composition.

The guest creates a file, reads sequential and random offsets, shrinks it,
creates a folder, renames into a long path, grows the file, creates/removes an
empty folder and deletes another file. It verifies writer disarming, read-only
admission without disk submission, not-found, cross-volume rename refusal and
refused partition switching while a file is open. Directory enumeration and
allocation/root walks use their real APIs and callbacks. Each write uses an
ordinary persistent host disk binding. Full native/twin state and RAM and the
host image match. An independent byte-level oracle checks MBR/BPB, both FATs,
LFN ordering/checksum, dot links, exact file bytes, six reachable allocations
without leaks, FSInfo free count, clean status and the UTC write timestamp.
This is a component proof, not the complete monitor, a ROM-launched file command
or physical power-loss test.

The shared wall clock now admits RTC provenance through
`WallClockRtcAdmit(0|1)`, explicitly controlled by a validated hardware provider.
All compositions start with RTC admission off. Revocation makes an existing RTC
anchor untrusted while retaining its value/provenance for inspection. Manual and
SNTP provenance remain independent. Init/Clear do not unregister hardware. The
Pi5 provider registers after validating its RTC reading; the shared core no
longer selects RTC policy by ARM chip ID. The Zentaji fixture exercises admission,
invalid registration and revocation as policy tests; it does not claim to seed
wall time from a validated Zentaji RTC. `HwMicros()` now derives bounded signed
microseconds from hardware TIME/TIME_HZ for shared services and profiling, with
checked arithmetic; the fixture checks it against independent tick brackets.

The compiler prerequisites are natural scalar record alignment and static
DataSection integer/fixed-text tables, including ordinary `?label` addresses.
They preserve the shared libraries' table definitions. Large generated assembly
uses a linear line reader and dense source metadata; all original include paths,
lines and hashes remain represented in instruction maps. General managed strings,
compound record fields, floating Data and Read/Restore remain distinct compiler
work. Board storage lifecycle, actual exFAT execution and full monitor/command
composition remain unfinished.
