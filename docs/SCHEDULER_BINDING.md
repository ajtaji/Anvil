# Scheduler hardware binding

Status: explicit Pi 4 EL3 binding implemented with emitted-code desk proof;
it is not enabled during boot. This document does not authorize a board run or
claim silicon acceptance or preempt-safe monitor services.

## Existing ownership that must be preserved

The Pi 4 board's `HwExceptionPrepare` installs the ordinary exception vectors and
`HwInterruptPrepare` initializes GIC-400 against that exact VBAR. The GIC driver's
`InterruptContext` rejects a changed VBAR. Installing scheduler vectors after
that initialization therefore invalidates the old dispatcher: a second
initialization is not a safe way to transfer ownership.

The GIC driver saves controller enable and priority-mask state. Its explicit
`InterruptCanTransfer(expected)` and `InterruptTransfer(expected,replacement)`
operations transfer an empty controller's vector lease without reinitializing
hardware. A scheduler binding must not shut down somebody else's interrupts.
The initial integration admits an exclusive, empty controller only; refusal
must occur before any vector or timer changes when another handler owns a line.
Both calls reject enabled peripheral lines, pending or active interrupts and
software owners. SGI enable bits, which are permanently enabled, are excluded
from the enable test; pending/active SGIs still prevent transfer. Bindings never
edit the driver's private `ig_vbar` variable.

`RaspberryPi4/Lib/timer.pi4` provides counter reads and delays, not ownership of
the architectural physical timer's interrupt comparator. The Pi 3 timer driver
is explicitly EL2/non-secure physical timer plus the BCM2837 local controller.
It cannot be attached to the current EL3 scheduler or to the Pi 4 GIC by changing
an interrupt number. Counter reads used by existing polling drivers may continue;
the comparator, control register and interrupt line need an exclusive owner.

## Required transaction

1. Validate primary core, EL3h, masked DAIF, FP permission, interval and callback
   addresses, expected VBAR and empty GIC ownership before writes.
2. Confirm the selected timer comparator is disabled and no other owner has
   reserved it. Preserve the disabled comparator/control configuration.
3. After `InterruptCanTransfer`, install scheduler vectors and transfer the
   empty GIC lease against the new actual VBAR. Claim only the verified timer.
4. Install a bounded timer acknowledgment callback and a bounded fatal reporter.
   Preparation must leave both the comparator and CPU IRQ delivery disabled.
5. Only an explicit scheduler run arms the comparator; task exception return
   unmasks IRQ. Stop disables the comparator before releasing its interrupt.
6. Teardown requires all tasks reaped. Restore timer state and interrupt priority,
   release the timer line, restore vectors, then reverse-transfer the empty GIC
   lease. Every failed step rolls back in reverse order. A rollback
   failure is a retained diagnostic state, never reported as successful teardown.

The binding uses `CNTPS_*_EL1`, INTID29 and requires the stub's exact SCR0x5B1
configuration, the GIC driver's secure Group1 checks, primary core and EL3h.
EL2 refuses before timer access. Arm's [Generic Timer guide](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Generic%20Timer.pdf)
identifies CNTPS as the EL3 physical timer. The [Pi device tree](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/arch/arm/boot/dts/broadcom/bcm2711.dtsi)
lists PPI13 first, and the [timer binding](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/Documentation/devicetree/bindings/timer/arm%2Carch_timer.yaml)
identifies that position as secure physical timer. PPI13 is INTID29.

## Fatal report contract

`HwExceptionReport` reads the ordinary exception frame (slot at 256, ESR at 264,
ELR at 280). The scheduler frame instead stores ELR at 256 and SPSR at 264.
Calling the old reporter directly would print plausible but false evidence.

The scheduler has a separate first-failure raw record, a dedicated emergency stack
and a once-only reporter entry. Unexpected vector entries do not necessarily
have a captured task frame; their report must explicitly distinguish raw current
exception registers from a valid saved task context. Do not label a previously
saved task PC as the current fault PC. A second fault must park without erasing
the first record or recursively invoking the reporter.

The board already has bounded raw PL011 byte/text/hex writers. `report_pi4.pbi`
reuses those formatting primitives for a scheduler-specific record without using
`ExceptionFrame` or reentering the normal display/network console. The reporter
must not allocate, acquire application locks, schedule, or assume the faulting
stack is intact. No automatic restart or recovery is promised. All raw ESR/ELR
values are explicitly labeled potentially predating the stop. The current
record does not claim a decoded fault slot or a validated task exception frame.

## Entry points and proofs

`AbPrepare(periodTicks,codeBase,codeBytes,reporter)` obtains the empty controller
lease and installs the timer adapter and fatal reporter without starting tasks.
Use `ApCreate`/`ApRun` explicitly. Reap all task contexts before `AbRollback`.
`ab_state` preserves a failed rollback stage (1 vectors,2 transferred lease,
3 timer owned,4 original vectors restored but lease return pending), so failure
cannot be mistaken for detached state0. An invalid reporter is refused.

`AtAcknowledge` returns1 only when its timer handler ran,2 for a controller
spurious acknowledgment and0 for failure. `ApOnTick` validates guards on both
successful paths but does not increment ticks or schedule on2.

Desk commands use the unified IDE via the `--compiler` option:

- `tools/scheduler_context_binding_check.py`: two nonyielding FP tasks through
  CNTPS and actual modeled GIC IAR/EOI;18 assertions,306 acknowledged timer
  interrupts, one spurious IRQ with no tick, completion and restored lease.
  Invalid reporter and timer-group acquisition failures roll back to state0.
- `tools/scheduler_context_timer_check.py`:14 timer/restore/refusal checks.
  Refused pending/group/SCR/EL cases issue no GIC or timer-register writes.
- `tools/scheduler_context_fatal_check.py`: broken SP abandoned for aligned
  emergency stack, one reporter call, recursive stop parked, first raw PC retained.
- `tools/a64/interrupts_emitted_check.py`: transfer/rollback and busy-state
  refusals alongside the existing18 dispatch,13 identity and14 rollback cases.

These execute generated native instructions against explicit device models.
They are not boot, interrupt-polarity, UART-delivery or physical-board proof.
The core's45 refusal checks also inject failed vector installation, failed
installation rollback and failed thread-register restoration:
new runs/contexts are refused until explicit uninstall retry succeeds. This
does not assert fault injection coverage for every possible hardware failure.
If installation fails and restoring VBAR/thread state also fails, the core
retains `ap_installed` and `ap_restore_pending`; the binding retains state1.
It records the observed recovery VBAR, permitting an explicit retry only from
that observed state or the known old/new vector states. A subsequent unrelated
vector change remains a refusal. A return value0 never silently discards this
partial ownership. The binding gate verifies failure/state1/retry/state0 before
running the native asynchronous tasks.

## Acceptance before a board slot

- Refused occupied GIC, active comparator, foreign core, changed vector and
  unmasked context make no ownership-changing writes.
- Fault injection at every acquisition boundary restores the previous lease;
  failed restoration remains observable and prevents starting another run.
- The timer model delivers through actual GIC acknowledge/EOI, not a callback
  invoked directly by the test. Spurious acknowledgments do not fabricate ticks.
- Two nonyielding tasks retain independent integer and FP state, complete, stop
  their timer and return to the original kernel context.
- A fatal entry with a corrupt task stack still writes a bounded first report;
  recursive reporter failure does not overwrite it.
- Existing polling-counter callers and ordinary exception gates still pass.

This binding is separate from preemptive safety of network, graphics, allocator
and compiler hidden runtime state. Until those resources have ownership-safe
interfaces, preempted tasks cannot call arbitrary existing monitor services.
