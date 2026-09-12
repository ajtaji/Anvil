# Portable application scheduling

Status: lifecycle, cooperative contexts and a separate EL3 asynchronous
backend execute under emitted-code gates. Two nonyielding FP loops are
preempted by modeled timer IRQs. **No production timer binding, whole-runtime
preemption safety or board acceptance yet**. This is a
foundation for running a native forum alongside other Anvil applications,
not a claim that the existing monitor can already do so.

## What exists

`Anvil/Kernel/Scheduler/scheduler.pbi` owns 32 fixed task slots, generation
handles, FIFO ready and waiting queues and one logical RUNNING slot.
No allocation, hardware register, callback, busy wait or architecture name
appears in the production implementation. All queue operations are bounded
by 32 slots; wake/timeout queue compaction is bounded O(32 squared).

| API | Result and ownership |
| --- | --- |
| `SchedCreate()` | New READY handle; 0 when all slots are occupied/retired. |
| `SchedNext()` | READY head becomes RUNNING; 0 when idle or another task still owns RUNNING. Does not execute it. |
| `SchedYield(handle)` | Current RUNNING task joins ready tail. |
| `SchedWait(handle,key,deadline)` | Current RUNNING task joins wait tail. Key 0 is timer-only; deadline 0 has no timeout. Both zero is refused. An already elapsed deadline immediately readies the task. |
| `SchedWake(key,maximum)` | Wake up to maximum matching waiters in wait-arrival order; count returned. This is notification, not a retained/counting semaphore. |
| `SchedAdvance(now)` | Wake elapsed deadlines in wait-arrival order. Returns count; backward time returns -1 without mutation. |
| `SchedFinish(handle)` | Current task becomes DONE. Does not release application resources. |
| `SchedCancel(handle)` | READY or WAITING becomes CANCELLED; RUNNING cancellation is refused until safe-point/context support exists. |
| `SchedReap(handle)` | DONE/CANCELLED slot becomes FREE. Caller must first finish resource/context cleanup. |
| `SchedState(handle)` | State value or -1 for invalid/stale handle. |

Transition operations return 1 on success, 0 on refusal. Wake returns -1 for
invalid key/count. Terminal handles remain valid until reaped; every reuse
increments generation. Generation exhaustion retires a slot rather than
wrapping into a stale handle. No public reset silently destroys live tasks.

Time uses one caller-provided, nonnegative, monotonic integer domain. It is
not wall clock and does not change with time zone. Tick units and conversion
belong to the timer backend; it must reject a deadline that cannot fit this
integer domain. Wrap-around is not supported by this initial contract. A
32-bit target needs a proven clock-extension/representation decision before
integration, not a reinterpretation of signed overflow as elapsed time.

The shared `sched_*` storage and internal enqueue/remove helpers are kernel
implementation details. Application code must never write them directly.

## Required serialization and service boundaries

This component requires a **single serialized kernel owner**. It contains
no lock and is not SMP-safe or callable from IRQ handlers. Device IRQ handlers
must acknowledge hardware and publish bounded completion records through a
separately verified IRQ-safe queue. The kernel drains those records and calls
Wake/Advance. Overflow needs explicit backpressure/error accounting; dropping
a completion and hoping for another interrupt is not acceptable.

The event condition check and transition to WAITING must be performed under
the same ownership as event publication/draining. Wake is not latched: without
that contract a completion between the check and sleep is a lost wakeup.

Existing networking is **single-owner**. The current TCP implementation has
a selected-socket global and shared packet/work state. Application tasks must
submit requests to one network service rather than preemptively reentering
socket selection/send routines. Give each request an owner generation,
completion token and timeout; cancellation must invalidate late completions.
Bounded service work per dispatch is required so a busy forum cannot starve
input, storage or another application's network request.

Future kernel locking must be explicit: tiny IRQ-save critical sections around
queue ownership, no sleeping/allocation/device polling while held, fixed lock
ordering, and no application callback under a kernel lock. Sleeping mutexes
and priority inversion handling are separate objects, not spins that freeze
the scheduler. SMP run queues and interprocessor wakeups come after a proven
single-core preemptive implementation.

## Architecture backend contract still to implement

### Cooperative A64 backend

`cooperative_a64.pbi` now supplies real stackful execution, not repeated
callbacks pretending to resume a procedure. It is initially **EL3 only**, on
one bound core, with FP/SIMD access already enabled in CPTR_EL3. It refuses
EL1/EL2 because permission at a higher exception level cannot be proved from
there without a trusted handoff contract. It is privileged code and must never
be called from EL0. Pi 3's EL2 boot is therefore not integrated with this backend.

Call `ScConfigure(codebase,codesize)` once with the mapped executable interval,
then `ScCreate(entry,argument)`. Entry is an aligned address in that interval
of a parameterless integer-returning procedure; `ScArgument()` retrieves its
argument. The range admission is not executable-page validation or proof that
an arbitrary instruction address is a procedure. Composition owns that trust.
Each task has a fixed 16 KiB private stack and generation-bound saved context.

`ScRunOne()` dispatches one READY context and returns its handle only after it
yields, waits or finishes. `ScYield()` and `ScWait(key,deadline)` resume at their
original call site and return 1; invalid calls return 0. Existing Wake/Advance
make waiting tasks ready. Entry return records `ScResult(handle)` and finishes
the task. `ScReap(handle)` releases terminal ownership and clears context and
stack from the kernel stack, never from the stack being released. Application
resource cleanup must precede reaping; this does not run arbitrary destructors
for a cancelled task. Do not mix independent SchedCreate/dispatch calls with
this backend's context ownership.

Both stack ends carry canaries; saved SP is checked for alignment and bounds
before resume and after suspension. Failure marks a terminal/cancelled task
with result -1. This detects damage at safe points, not memory isolation or a
guarantee against a task overflowing through a canary between checks.

The switch stores x18-x30, SP, every 128-bit SIMD register, FPCR/FPSR and DAIF.
Public calls retain the normal AAPCS64 caller-clobber rules: x0-x17 and NZCV
cannot carry live values across Yield/Wait, and callers must not infer extra
public preservation guarantees from the wider internal save. Return values
arrive in x0. This follows the register/stack constraints in
[Arm AAPCS64](https://github.com/ARM-software/abi-aa/blob/main/aapcs64/aapcs64.rst).
No SVE/SME, address-space, exception-level or thread-pointer switch is supplied.

Focused gate:

```text
python tools/scheduler_context_check.py --compiler <PureMetalForge executable>
```

It executes two instances of one procedure with independent persistent locals,
FIFO yield, event and timeout waits, actual return/cleanup, stale handles and
stack-canary failure. A naked ABI witness checks callee GPRs and SIMD values
across Yield. Environment refusal and FP state cases are separate from physical
hardware proof. The cooperative backend is not wired into boot or IRQ handling.

Common policy must not write target-specific saved registers. A backend owns:

1. Task context allocation, aligned private stacks, guard/canary checking,
   entry/argument/exit trampoline and address-space identity where supported.
2. Full context save/restore at asynchronous preemption boundaries: integer
   registers, SP, PC, status flags/masks, FP/SIMD state and relevant control
   state. A normal procedure call preserves less than an interrupt switch.
3. A monotonic timer and bounded quantum interrupt. IRQ entry saves the
   interrupted context before common policy selects another runnable task;
   the epilogue restores that task rather than the interrupted one.
4. A valid kernel context for idle, wait and termination. A task may not free
   its own active stack, and cleanup must finish before Reap reuses its slot.
5. Safe cancellation checkpoints and pending-cancel status for RUNNING tasks.
   Do not abort an arbitrary instruction while it owns a device or allocator.
6. Correct exception level and vector ownership. The present Pi 4 exception
   return path is not automatically a task context switch. Pi 3 needs its own
   timer/interrupt backend; no Pi 4 GIC address belongs in portable policy.

Compiler procedure frames are necessary but not sufficient. Audit emitted
hidden runtime storage, string temporaries, allocation/error/formatting state,
inline assembly and service scratch for reentrancy before preemption. Either
make state task-owned or expose a serialized service. Passing a frame test
does not establish whole-language preemption safety.

## Delivery phases and proof

1. **Lifecycle foundation (implemented):** generation validation, capacity,
   FIFO rotation/wake order, deadlines, terminal cleanup and refusals.
2. **Real cooperative contexts (A64 EL3 desk implementation):** distinct stacks and persistent locals;
   two actual applications yield/wait/resume without losing state. This is
   useful bring-up, but an application that never yields can still starve all
   others, so it is not sufficient for the requested forum deployment.
3. **Preemptive fairness:** timer-enforced quanta and bounded kernel/service
   latency. Prove progress for input and a second application while forum
   work is CPU-bound and never voluntarily yields. Measure response latency,
   not just changing counters. Preempt FP/SIMD-heavy tasks and verify results.
4. **Resource safety:** timeout/cancel/disconnect, late-completion generations,
   stack exhaustion, allocation pressure, storage transactions and fault
   containment. Privileged same-address-space tasks are not isolated processes;
   do not promise that one bad application cannot corrupt another.
5. **Hardware and target acceptance:** first one core, then SMP only after
   cache/atomic/lock proofs. Run on the intended Pi 3 hardware with networking
   and storage active. Portable source is not evidence that every target runs.

Current focused gate, from the checkout:

```text
python tools/scheduler_lifecycle_check.py --compiler <PureMetalForge executable>
```

It compiles an isolated fixture through the unified compiler and executes
the actual emitted lifecycle procedures under the A64 interpreter. The fixture
asserts capacity/refusal, generation reuse, stale cancellation, ready FIFO,
wait FIFO, timeout boundaries, backward-time rejection and terminal reaping.
It is not a monitor build and touches no board. The separate context gate
proves cooperative continuations in emitted instructions. Hardware, interrupt
races, memory isolation, whole-runtime reentrancy and preemptive fairness
remain explicitly unproven.

## Asynchronous EL3 backend

`preempt_a64.pbi` is separate from the cooperative backend; do not combine
their context ownership in one lifecycle instance. Its IRQ path saves all
31 integer registers, all 32 128-bit SIMD registers, SP, ELR_EL3, SPSR_EL3,
FPCR and FPSR before running policy on a guarded 16 KiB IRQ stack. ERET
restores the chosen task's interrupted PC and status, including NZCV and masks.
Applications need not yield for the timer to switch them. SVE/SME, SMP,
address-space changes and whole-runtime preemption safety are not supplied.

`ApInstall(expectedVbar,ack,arm,stop,codebase,codesize)` requires EL3h, all
DAIF masks set and CPTR_EL3 allowing FP/SIMD. It compares VBAR, reserves a
previously zero TPIDR_EL3 for entry scratch, and installs its vector table
with readback. It does not start the timer or unmask IRQ. Only current-EL
SPx IRQs are resumable. Lower privileged ELs refuse before EL3-only reads;
EL0 calls are outside this privileged contract.

The three timer callbacks are parameterless integer-returning procedures
in the admitted code interval. `arm()` starts/rearms a quantum; `stop()`
stops the source; `ack()` verifies the expected IRQ, acknowledges the actual
interrupt controller and rearms. Return 1 only after success. Callbacks must
remain on the same core/EL, keep IRQ masked, never sleep/reenter the scheduler,
perform bounded work and not leave a partially enabled source on failure.
These are native adapter contracts, not deployed Pi hardware bindings. The
Pi 3 local-controller timer is EL2 and needs a separate compatible backend.

`ApCreate(entry,argument)` allocates a private 16 KiB stack and generation-bound
context. Entry is parameterless and integer-returning; `ApArgument()` retrieves
its argument. `ApRun()` launches tasks and returns to the original kernel
context when all finish. Timer IRQs rotate FIFO ownership. Entry return records
`ApResult(handle)`. `ApReap(handle)` clears terminal stack/context ownership;
only then can `ApUninstall()` restore the vector/thread lease. Saved SP, PC,
mode and canaries are validated. This detects damage, not memory isolation.

The fatal path is currently a diagnostic fail-stop, **not a wired Anvil panic
reporter/recovery path**. Bind that path and native timer ownership before
board use. Live-task waits/cancellation, application resource cleanup and
serialized services also remain integration work. Preserving registers does
not make shared compiler runtime or device scratch reentrant.

```text
python tools/scheduler_context_arch_check.py
python tools/scheduler_context_preempt_check.py --compiler <PureMetalForge executable> --mutate
```

The architectural gate checks IRQ-entry/ERET state, masks, stack banks, nested
entry and invalid returns against
[Arm's exception model, sections 5 and 6](https://documentation-service.arm.com/static/67ac57fb091bfc3e0a9479cc).
The execution gate runs two actual nonyielding FP32 loops. A test-only counter
comparator routes IRQs to EL3; no task progress or results are manufactured.
The initial run passes 18 execution assertions under 26 IRQs, 26 ownership
refusals and two corrupt-context source mutations. Interpreter instruction
ticks are not a silicon frequency or latency measurement.
