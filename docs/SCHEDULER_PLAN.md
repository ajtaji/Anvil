# Portable application scheduling

Status: task lifecycle and bounded queues implemented; **no executing
multitasking, preemption, timer binding or board acceptance yet**. This is a
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
2. **Real cooperative contexts:** distinct stacks and persistent locals;
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
It is not a monitor build and touches no board. Hardware, context switching,
interrupt races, stack isolation, compiler runtime reentrancy and preemptive
fairness remain explicitly unproven.
