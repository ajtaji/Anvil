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

Next are complete board startup/vector ownership, storage backends,
the remaining runtime/compiler facilities and production payload/service ABI.
ROM must load Anvil, and Anvil must then reach the shared prompt and load
applications. The built-in Forge must ultimately target Zentaji itself only.
