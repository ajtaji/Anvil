# Zentaji backend bring-up

The machine has a real clock and bounded prompt-idle backend. This is not yet
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

Next are complete board startup/vector ownership, console/input/storage backends,
the remaining runtime/compiler facilities and production payload/service ABI.
ROM must load Anvil, and Anvil must then reach the shared prompt and load
applications. The built-in Forge must ultimately target Zentaji itself only.
