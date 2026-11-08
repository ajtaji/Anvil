# Zentaji backend bring-up

The counted Zentaji board now boots Anvil through the machine ROM and owned
supervisor startup. It uses the shared command loop, serial console, clock,
settings and FAT32/exFAT storage code. Ordinary PMFBOOT applications now load
from files or memory and return. Service-table integration and self-hosted Forge
remain unfinished. The shared monitor owns scheduler and command policy.

`Board/clock.pbi` supplies `Ticks()` from the CPU's TIME register and `TickHz()`
from the timer device's read-only frequency. `Board/prompt_idle.pbi` selects the
Zentaji CPU runtime and implements the three prompt-idle HAL methods. The
runtime in `Anvil/Kernel/Zentaji/zen_cpu.pbi` is the byte-identical shipped
guest library, with its source revision and hash in `PROVENANCE.json`.

The board's interrupt owner must reserve the calling core's timer and configure
line 1 as a level source, enabled above that core's interrupt threshold. Anvil
must already be running in its required supervisor context. Then call
`ZentajiPromptIdlePrepare(maxMicroseconds)` with a 50-2000 microsecond deadline.
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
The 128-byte version2 context records the incoming stack, actual RAM,
owned stack bounds, vectors and image extent. `boot_context.pbi` supplies the
field constants and bounded validation for the compiled monitor. Version1 stays
readable with its final reserved word zero; version2 publishes the owned CPU
payload-call address there. Default stack
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
the remaining runtime/compiler facilities and production payload/service ABI.
Durable disk backing and the shared file-service lifecycle are implemented below.
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
HAL vocabulary, console and portable wall clock. `Board/storage.pbi` owns disk
selection, mount admission, the shared seam's mounted/writable/writer values,
and clean shutdown. It does not introduce a second file implementation.

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
work. Full monitor/command composition remains unfinished.


The exFAT path can also start at the real ROM rather than injecting the image:

```text
python tools/zentaji_storage_check.py --filesystem exfat --boot-disk 15 --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

The boot fixture places the selected Anvil executable in the disk boot area and
an MBR exFAT partition at sector 4096. The ROM loads Anvil and hands over disk 15;
the production lifecycle adopts that instance, mounts the partition, executes
the same writable file operations, cleanly releases storage and reopens the
persisted file. Native/twin full state, RAM and host image match. An independent
oracle checks boot-region checksums and clean flags, unchanged backup and boot
payload, file entry-set/name hashes, upcase-table checksum, exact file bytes,
eight reachable bitmap allocations without leaks/crosslinks and UTC timestamps.
FAT32 allocation walks run normally; exFAT explicitly refuses those two APIs
until its format-specific corruption-safe walker exists. That limit is checked,
not silently treated as successful enumeration.

FAT32 also passes the complete writable proof using the production lifecycle,
including invalid/unconfigured selection, repeated bring-up without disk
submission, refusal to reconfigure an acquired medium, refusal to shut down an
open file, clean shutdown, repeated shutdown and reopen. These are component
compositions with actual device queues; no monitor command parser is substituted.

## Board storage lifecycle

Include `Board/storage.pbi` after the boot-context, console, disk, HAL and wall
clock backends. `ZentajiStorageConfigure(disk, partition)` explicitly chooses
instance 0..15 and partition 1..4. `ZentajiStorageFromBoot(context, partition)`
uses the ROM-selected disk from a validated Anvil boot context; host-file boot
requires explicit selection instead. Neither silently chooses another disk.
The board must already have established normal supervisor context, serialized
access and the qualified timer/WFI idle backend.

`HwStorageUp()` acquires the selected queue driver and mounts through the shared
filesystem facade. Its low-level counterpart `ZentajiStorageUp()` retains an
error code/text without printing; the HAL entry prints the reason on failure.
Repeated successful calls retain open files, mount jobs, current partitions and
caches. The hardware read-only flag controls file-write admission. Shared
HwFile operations arm the writer only around a change and disarm it afterwards.
`HwStorageReport()` reports the selected device and currently mounted format.

`ZentajiStorageDown()` refuses open files or a pending mount, explicitly flushes
before unmounting, and releases the queues only after success. A failed flush
retains ownership for diagnosis/retry. It clears file admission and callbacks
after release, keeps the selection for reopening, and accepts repeated shutdown.
Changed queue ownership disarms the file service and produces an explicit error;
it does not reset a foreign owner or cancel quarantined DMA. Direct driver and
filesystem clients must not bypass this lifecycle while it owns the medium.

The component proof still does not link the full monitor command dispatcher or
load and execute an application through Anvil's payload ABI.


```text
python tools/zentaji_storage_lifecycle_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

Four focused native/twin cases check invalid/non-disk boot contexts, a missing
selected disk, refusal to adopt or close another queue owner, an invalid volume
with an acquired disk retained for clean release, and a hardware read-only
volume. Read-only writes fail before any command submission; pending mount jobs
block shutdown and survive repeated bring-up until their owner cancels them.
Each case compares complete state/RAM, an unchanged persistent host image and
exact serial output. Report output distinguishes a mounted volume, a pending
mount and no mounted partition after a failed switch. This does not prove
physical power-loss behavior or the final monitor/payload integration.


## Live memory layout and shared file commands

`Board/memory.pbi` binds once to the validated owned-startup context. The payload
window starts at the next 4 KB page after the complete loaded image/BSS/vector
slab and ends before Anvil's supervisor stack. Three enumerated exclusions
protect the low prefix and image, the complete stack, and the ROM's top 1 MB
workspace. Addresses derive from the actual image and fitted RAM; no ARM memory
map or fixed Anvil image-size allowance is used. A composition without a valid
binding admits no payload window. The stage address is the window's first byte.

The unchanged shared `memrange.pbi` walks those windows/exclusions. The address
backend admits ordinary fitted RAM for raw inspection, classifies positive
addresses beyond fitted RAM as absent, and leaves MMIO/ROM apertures unknown.
The shared `addrsafe.pbi` retains its deliberate one-address force policy; that
does not turn a device aperture into an admitted file-load payload window.

```text
python tools/zentaji_memory_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
python tools/zentaji_commands_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

The memory gate executes real owned startup with 2 MB, 4 MB and uneven RAM sizes,
and through the actual ROM on disk 15. Native/twin full state and RAM agree.
Independent extents from the packed image and actual RAM check every reported
region/window edge; shared policy refuses negative, reversed, crossing and
monitor/stack/ROM-workspace intervals. The gate writes and checks both admitted
window endpoints and verifies the shared map's output.

The command gate boots from the actual ROM on disk 15 into the owned supervisor
startup, binds the live memory/storage backends and runs the real shared
ReadLine/editor/parser, settings store and file-command implementation. Typed
commands create a folder, save 1800 staged bytes to a quoted long path, clear the
stage and load the file back, list its folder, report a missing file, and refuse
a load over the running monitor. The independent oracle verifies the complete
persisted exFAT result, allocation accounting, hashes and timestamps; the staged
RAM bytes and monitor instruction bytes are independently checked. Native/twin
full state, RAM and host disk match, with expected command echoes/results.

`DispatchStorageCommand()` in `Anvil/Core/fs_cmd.pbi` now owns the storage word
and alias policy used by Pi4, Pi3, Arduino Q and this Zentaji composition:
`mount/load/fatload/f`, `save`, `mkdir`, `rmdir`, `rm/del`, `rename/mv`,
`fatls/ls/dir`, and `cat`. Unknown words return 0 so the next family can try.
This preserves the old aliases and makes `dir` available on Pi4 and `mount`/`cat`
available on Pi3 and Arduino Q through their existing file backends.

This remains a component command composition, not the complete production
monitor. It now uses the production optional-service registration with no
registered display, mouse, keyboard, network, radio-maintenance or file-log
provider. No counted service adapters remain in this command image. The real
`rxbreak.pbi` supplies output cancellation. The test operator sends each line
after observing the prompt and replays that same timed UART schedule natively;
pipelining a later command through an interruptible listing correctly cancels it.
The shared file handlers and filesystem implementation have no test substitutes.
The top-level production board entry, remaining command families, settings at
boot and the Zentaji application/service ABI remain unfinished.


## Optional prompt services

`Anvil/Core/prompt_services.pbi` supplies explicit synchronous registration for
background work (`AnvilPromptServicesBind`), optional input/console ownership
(`AnvilPromptInputsBind`), and the transport pump (`AnvilPromptPumpBind`). A zero
provider unregisters that part. Unbound work and pump calls do nothing; optional
keyboard input reports no byte (0), and network input reports no byte (-1).
Presence getters describe registration, not hardware discovery or capabilities.
Serial input, input events, the editor, message log, clock accounting and the
qualified timer/WFI backend remain real shared/board implementations.

Pi4, Pi3 and Arduino Q register their existing services inside Main after the
firmware-entry capture, before the prompt. Pointer/touch service, display,
DHCP/NTP, fan/temperature and network maintenance retain their scheduler lanes.
The input provider retains keyboard admission and local/remote console ownership.
The pump has a separate callable target because cancellation during a networking
service must not recursively reenter link-local/DHCP or generic maintenance.
Input can be read while work or pumping is active; provider registration cannot
change during any callback. Each dispatcher refuses recursive entry, and invalid
operation IDs report `APS_ERR_OPERATION`; active-entry/rebinding refusals report
`APS_ERR_ACTIVE` through `AnvilPromptServicesLastError()`.

Wi-Fi maintenance and the message log's optional file notification also have
concrete unbound call targets. Their raw registration pointers remain zero when
unregistered, and no connection or file-copy capability is invented. The message
log still keeps and exposes its lines with no file sink.

```text
python tools/zentaji_prompt_services_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

This checks absent defaults, registered work/input/pump routing, input during
work/pumping, active rebinding refusal, independent unregister and invalid IDs.
It also executes the real UART cancellation code: any-byte and Ctrl-C behavior,
sticky abort without consuming extra bytes, rearm and exact output. A real
unbound ReadLine wait checks startup-adjusted host CPU below 20% of one core over
two seconds, with exact recorded native/twin state/RAM replay and a real message
log with no file hook. The qualified timer/WFI wake path is unchanged. This is a
Windows headless execution proof; visible device input and Linux are still owed.
The existing registered-adapter prompt and idle gates remain separate regressions.


## Shared command loop

`Anvil/Core/command_loop.pbi` now owns `AnvilCommandLoop()` and the
single-iteration `AnvilCommandStep()`. Pi4, Pi3 and Arduino Q call that same loop;
the Zentaji ROM command composition calls its step. Prompt bytes stay exactly
`pmf> ` with the trailing space and no newline. Shared preparation arms output
cancellation after input, parses the word, handles `measure`, resets memory
width, ages the one-command force override and strips supported width suffixes.
The shared loop supplies timing reports and the bounded unknown-command reply.

A board implements the two declared HAL entries `HwCommandDispatch(c)` and
`HwCommandLoopHook(phase)`. Dispatch tries its included command families and
returns 0 for the shared unknown-word reply. The hook brackets prompt styling,
output/console-owner flushing, input admission and command completion. It returns
0 to stop the session. A stop after input suppresses dispatch and preparation,
which preserves firmware/deadman exit behavior. Board hooks retain Pi3 foreground
flags and Arduino Q typing, prompt-attribute and transcript-flush behavior;
firmware argument capture and shutdown stay in each board's Main.

```text
python tools/zentaji_command_loop_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

Three real-UART native/twin cases check `.B/.W/.l` handling and reset, exact
one-command force expiry, `measure` and its bare/nested refusals, empty input,
unknown words and 24-byte display cap, all hook phases in order, and stopping
before the prompt or after input without dispatch or state preparation. The
ROM file-command gate also passes using the shared step and its existing
independent RAM/disk oracle. These are bounded component proofs. A counted
production Zentaji board entry is now available below; payload integration is
still unfinished.


## Counted Zentaji monitor image

`Board/board.zentaji` is the production composition. Build it explicitly:

```text
python tools/build.py zentaji --compiler <Forge executable>
```

The usual board build reservation and ledger apply. Forge compiles the actual
board with the Zentaji backend and callable entry; the external native ASM
assembler wraps the owned supervisor startup. The six published files are
`build/zentaji/anvil.zex`, its `.boot.json`, `.asm` and `.zmap`, plus
`.compiled.zex` and `.compiled.asm`. Publication and build identity roll back
together on failure. The experimental target is explicit; `all` retains its
existing ARM target selection. The multi-target host Forge build is unchanged.

The ROM loads this ZEX as the chosen Anvil bootloader. A disk boot adopts the
exact selected disk from the validated context; a host-file boot explicitly
tries disk0. Missing storage reports its real failure and leaves the prompt
usable. Settings and the saved clock floor use the shared file implementation.
`halt` requires successful storage shutdown before releasing the idle timer and
serial attachment. Build1 requires at least 2,410,016 RAM bytes, as recorded in
its boot metadata; use the 8 MiB profile for these checks.

The command set includes version, map, echo, sleep, messages, file commands,
settings/environment, time and force. Help lists the admitted commands.
Service-table applications, raw execution, display, touch and networking are not
admitted by this board yet. The shared PMFBOOT reader and persisted boot-file
policy are now connected below; services remain further work.

Identity presentation is a HAL seam: ARM keeps its AArch64/exception-level
report; Zentaji reports the actual CPU status and supervisor context. The shared
map command uses the live image/stack/ROM boundaries without importing raw-run
commands. Zentaji refuses a file-equivalent content CRC because the loaded
image includes mutable runtime storage; its published artifacts and source map
still have exact file hashes.

The shared `sleep` command now services the prompt scheduler and calls the
qualified idle backend while waiting, with real UART cancellation. On Zentaji
that means bounded timer deadlines and WFI rather than a busy poll.

```text
python tools/zentaji_monitor_check.py --zen-tools <tools/zentaji directory>
python tools/zentaji_monitor_live_check.py --zen-tools <tools/zentaji directory>
python tools/zentaji_build_rollback_check.py --compiler <Forge executable>
```

These gates consume the counted published image. They verify source-map identity
and independent assembly, ROM disk15 and host-file boot, actual version/layout,
time/sleep and file commands, clean halt, full native/twin state and RAM, and an
independent exFAT allocation/content/timestamp oracle. The host-file case has no
disk and verifies honest storage refusal. The publication test performs a real
second compile and injects a failure at the third artifact rename, requiring all
six previous artifacts, the board stamp and ledger to survive byte-for-byte.

The Windows headless live proof compares six-second sessions using `sleep 0`
and `sleep 2`, including ROM startup, real timer wakes and halt. Both consumed
0.15625 seconds of host CPU in this run; the incremental cost was below the host
accounting resolution. Recorded clock/work samples replay exactly through the
native emulator and independent twin. This is not a Linux or physical-input
proof, nor instruction-cost calibration.

The shared FAT32 walker also has typed refusal targets for absent callbacks;
public null callbacks still refuse before disk I/O. Real callbacks retain their
range, visit and prune results. The focused FAT driver check and writable FAT32
storage lifecycle gate cover the actual compiled library; no board-specific
dummy visitors are needed by the production composition.


## Zentaji CPU payload boundary

`Anvil/Kernel/Zentaji/payload_call.pbi` now validates and calls the CPU trampoline
published by startup context version2. It takes the explicit context, entry,
argument, stack top and stack extent. The selected memory HAL must describe that
same context and admit the code and entire stack. Version1 contexts remain valid
for the monitor but report that this call mechanism is unavailable.

The trampoline is standalone startup assembly. Forge's naked leaf procedures
still cannot contain calls or computed dispatch; no compiler rule was relaxed.
The context and `.boot.json` record the call address, and startup/source maps
retain its actual instructions. Saved CPU state belongs to the monitor image,
including its protected extent in the shared staging policy.

Entry receives r1=argument, r2..r15=0, the admitted 16-byte-aligned stack with at
least 16KB available, and clean FPCR/FPSR. Only core0 in ordinary supervisor mode
with protection disabled and the owned vectors may enter. Nested entry refuses
before replacing saved state. The full-width result survives return; Anvil's
SP/link, scalar kept registers, kept vectors, mask registers, FP state and vector
base are restored without trusting the payload's returned SP or frame pointer.
Interrupt delivery stays masked. An unsafe exception context or enabled page
protection at return halts with explicit exit code $5A01 or $5A02 respectively.

```text
python tools/zentaji_payload_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
```

The 25 native/twin full-state/RAM cases use the actual compiled admission code
and packed startup trampoline. Independent raw guest assembly deliberately
clobbers kept registers, vectors, masks, FP state, EVEC and SP. Read-only twin
observers check entry and restored CPU state; native replay must agree exactly.
Repeated launches receive distinct arguments, including zero. Nested calls,
alignment/range/ownership/context refusals, v1 unavailability, malformed contexts
and unsafe-return fail-stop are covered, with actual ROM host-file boot cases.
The test avoids the ROM's destructive RAM-count word at each 64KB boundary.

This section describes the CPU mechanism. The board now uses it for shared
PMFBOOT entry as described below; service-table integration remains unfinished. Same-level
payloads are trusted programs; CPU-state restoration does not sandbox writes to
monitor memory, recover arbitrary traps, or protect against an earlier foreign
interrupt handler. Applications must return in the required supervisor context,
with protection disabled and interrupts masked.


The counted production image carries the same version2 startup. Build3 is
1,300,896 bytes and requires at least 2,419,040 RAM bytes; its call address and
context version are recorded in `.boot.json`. ROM disk15/file commands and the
no-disk host-file route pass against that published image. The version2 startup
also passed the full startup/vector/fault-reporting regression. The live sleep
comparison on build2 consumed 0.140625s versus0.156250s CPU over 6.2s wall time;
that result covers the unchanged timer/WFI path, not payload device recovery.


## Placed compiler images

Forge now accepts explicit Zentaji `--load-addr` and `--stack-addr`. An explicit
stack emits a PMFBOOT v2 sidecar through the existing shared writer: ISA2 is
Zentaji and target1 is the configurable Zentaji machine family. The PMF contains
the loadable bytes after the64-byte ZEX header, with their exact SHA-256, inline
zero storage, no separate BSS, stack top and return/service flags. Returning
startup preserves loader arguments, uses its own stack and restores caller
SP/FP/link with the full-width result in r1.

```text
PureMetalForge --compile app.zentaji --load-addr 0x280008 --stack-addr 0x2F0000 --entry-returns -o app.zex
```

Default builds retain origin$1000 and caller-stack behavior. Services require an
explicit stack for v2 provenance. Source placement directives and raw assembly
CLI placement remain explicit refusals. Runtime fitted RAM/ownership is the
loader's admission decision; compilation does not assume a fixed machine size.
The normal host Forge C build is retained; native Zentaji tools stay ASM-only.

The payload gate now additionally compiles a real placed returning application,
checks its PMF body/hash/ISA/target/flags/stack against independent assembly, and
calls those exact bytes twice through the actual admission/startup boundary.
Direct and ROM host-file cases check argument changes, full-width results,
restored caller CPU state and unchanged compiled image bytes, with exact full
native/twin state/RAM agreement. The harness places that PMF body; it does not
substitute a product PMF reader or claim public boot-command integration.

The production monitor now admits ordinary and service-backed PMFBOOT
applications through the actual shared ABI. See [ABI_ZENTAJI](../docs/ABI_ZENTAJI.md)
for its native calling convention and current device providers.


## Shared bootloader and ordinary payloads

The counted Zentaji board now includes the actual shared `pmfboot.pbi`, SHA-256
and `bootfile_cmd.pbi`. `boot APP.PMF` reads the real selected filesystem;
`boot mem <address>` uses an already loaded container. Both validate version,
ISA/target, flags, image/BSS/stack windows, native instruction alignment and a
complete entry instruction, place the image, hash those placed bytes and enter
through the same CPU boundary. Zentaji admits ISA2/target1 and refuses untagged
legacy v1. Memory boot also proves the version-specific header and whole source
range before the copy. Raw `run` is still outside this board's command set.

The container engine no longer names the service table's private globals or
file-handle implementation. `HwPayloadServicesReady/Open/Close` belongs to the
selected composition. Both existing ARM boards and Zentaji use the real shared
ABI owner. Zentaji service-backed apps retain resident serial/timer/storage
ownership and receive all 208 actual shared slots, with unchanged error and
capability policy. Entry returns an explicit success/refusal result; ARM marks actual CPU
entry at its branch, preventing a board refusal from being reported as a boot.

For ordinary trusted supervisor code, the board flushes/releases its selected
storage, drains/detaches serial and releases the idle timer before entry.
After CPU-state restoration it checks the owned timer/interrupt configuration,
re-adopts serial/timer and reacquires the same storage. A changed timer or
foreign disk owner stops the machine with a bounded raw-serial sentence and
exit0x5B02/0x5B03. It does not overwrite live foreign hardware to manufacture a
successful return. Payloads must leave devices they touch quiesced. This is not
arbitrary DMA cancellation or isolation from malicious supervisor code.
Service-backed apps instead retain the resident owners and must use the shared
services. Return verifies the owned hardware and closes every service file handle;
a subsequent app receives a fresh scope. Optional hardware and module providers
remain unavailable rather than fabricated.

`boot status/ok/clear` and the boot.file/boot.delay settings use the existing
shared settings/countdown/reboot-loop policy. Configure the saved target with
`setenv` and persist it with `saveenv`. Countdown now services bounded work and
calls qualified timer/WFI idle, with real input cancellation. The attempt counter
is persisted before automatic entry. A returned application is acknowledged by
`boot ok`; return alone does not silently erase the guard.

```text
python tools/zentaji_boot_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
python tools/zentaji_boot_check.py --only services --compiler <Forge executable> --zen-tools <tools/zentaji directory>
python tools/zentaji_autoboot_check.py --compiler <Forge executable> --zen-tools <tools/zentaji directory>
python tools/zentaji_board_ram_check.py --zen-tools <tools/zentaji directory>
```

The boot gate consumes the counted image and a real compiler PMF. It exercises
actual ROM disk15 -> command -> shared file/memory/hash/entry paths, repeated
return, metadata/stack/alignment/length/digest refusals, real service-table calls, truncated memory
source bounds and unsafe hardware return. It compares complete native/twin CPU
state, RAM, exact persisted medium and immutable monitor instructions. The
power-cycle gate provisions settings through real commands, then checks automatic
entry, the persisted failure guard, acknowledgement and cancelled countdown with
an independent SETTINGS.TXT reader. These are Windows headless proofs; physical
boards, visible input and Linux execution remain separate requirements.

Use the 8MiB profile for the application proofs. Counted board metadata now
records `minimum_ram_bytes` including a full 4KB page after the rounded monitor
extent; `startup_minimum_ram_bytes` retains the generic architecture floor.
The exact board minimum admits the prompt/staging window, not every application:
each PMF must also fit its own image and initial stack. Below the board floor,
startup reports 0x5B04 and stops instead of claiming a usable prompt.
