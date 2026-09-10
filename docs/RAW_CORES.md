# Raw secondary cores on Raspberry Pi 4

Anvil now has a desk-gated, inactive first milestone for joining a BCM2711
secondary core to the monitor's cacheable address space. Nothing includes it
from the board entrypoint and nothing starts a core during boot.

This is intentionally smaller than a task runtime. The current A64 compiler
places ordinary procedure parameters and locals in fixed BSS slots, so two
cores cannot safely execute general generated procedures at the same time.
There is no `CoreStart(callback, argument)` promise, forced preemption,
interrupt delivery, scheduler, or generic callback in this milestone.

## Source boundary

`RaspberryPi4/Lib/mmu_secondary.pi4` owns the secondary-specific translation
join. This milestone accepts only the repository's pinned EL3 armstub contract;
the previously desk-modeled EL2 path was removed because an EL2 read of the
implementation-defined CPUECTLR can trap without an installed exception path.
Its no-parameter naked procedure accepts the complete register contract:

- `x19`: expected exception level, exactly 3;
- `x20`: the primary's live `TTBR0_EL3`;
- `x21`: the matching `TCR`;
- `x22`: the matching `MAIR`;
- `x23`: the complete matching `SCTLR`, with M, C and I required;
- `x0..x18`: scratch; `x19..x30` are preserved by the join.

Before any destructive maintenance, the join reads `SCTLR_EL3` and refuses
unless M, C and I are all clear, then reads back CPUECTLR_EL1.SMPEN bit 6 as a
required prerequisite. It never rewrites CPUECTLR or its unrelated bits. The
join selects only CSSELR cache level 0 and invalidates the core-private cold L1
data cache by set/way. It never enumerates CLIDR/LoC or selects the Cortex-A72's
cluster-shared L2, which can contain dirty authoritative data belonging to the
running primary. It then invalidates the I-cache and EL3 TLB, installs the EL3
register bank, enables the recorded `SCTLR`, and reads every register back. It
returns `x0=1` only when the live bank matches. It has no stack access, BSS
access, parameter spill, ordinary call, device access, or output.

The private-L1 algorithm is independently derived from the architected
CSSELR_EL1, CCSIDR_EL1 and DC ISW fields and the cache topology documented by
Arm Cortex-A72 TRM 100095 r0p3. No U-Boot-derived implementation was copied.
TF-A's permissively licensed A72 code is an independent safety cross-check:
core power-down performs level-1 maintenance, while level-2 maintenance
appears only in cluster power-down.

`RaspberryPi4/Lib/core_worker.pi4` owns the spin-table handoff and the permanent
raw state witness. Bootstrap records and result rows are separate
over-allocated BSS objects; both bases are rounded up to 256 bytes and each core
uses a distinct 256-byte stride. `RaspberryPi4/Board/memmap.pi4` owns one exact
4 KiB stack page per secondary: core 1 owns `$001FC000..$001FCFFF`, core 2 owns
`$001FD000..$001FDFFF`, and core 3 owns `$001FE000..$001FEFFF`. The complete
band is immediately below the autoboot page at `$001FF000`, above the primary
stack top at `$00100000`, and below the fixed linked-image base at `$00200000`.
It is independent of upward image growth and outside the BSS, framebuffer and
payload windows. The board monitor-map enumeration includes the complete band
as a protected region even while the raw-core library remains inactive.

The primary-only sequence is:

1. Refuse core 0, a non-primary caller, EL other than 3, an uncached primary,
   any stack other than the target core's exact board-owned page, a busy spin
   slot, a repeated preparation, or an exact page that overlaps the actual
   running monitor after a noncanonical link. The ownership and running-image
   checks precede every bootstrap/control-row write, cache operation and
   firmware spin-slot access.
2. Record an immutable per-core cold record containing stack, context, row,
   exception level and the primary's live EL-specific translation registers.
3. Initialise the separate control row to `PREPARED`, then clean the complete
   cold record and row to the point of coherency.
4. Store the permanent raw entry in the firmware spin slot, clean that slot to
   PoC, execute `dsb sy; isb`, then `sev`.
5. Poll for a bounded number of iterations using an acquire load. The primary
   never pets the watchdog while waiting and is the only core allowed to print
   or own the SoC watchdog.

Before calculating or reading any DRAM address, the secondary uses only
`CurrentEL` to reject every level other than EL3, then reads `SCTLR_EL3` and
CPUECTLR_EL1 to reject any as-found M/C/I bit or missing SMPEN. This order means
an EL2 arrival parks before the potentially trapping implementation-defined
register read. It then reads only its immutable cold record while still
uncached, installs its private stack, and makes one allowlisted call to the
MMU-owned naked join, which repeats the cold-state and SMPEN checks defensively.
Only after the translation-register readback succeeds does it set
the raw-worker ABI (`x0=context`, `x1=core`, `x2=result row`), write its mapping
witness, publish `READY` with `stlr`, order that publication before `sev`, and
park in `wfe`. A wrong EL, missing M/C/I or malformed record never publishes
`READY`; the primary reaches its bounded timeout.

The bootstrap record becomes immutable at release and the worker remains in
the resident Anvil image until reset. There is no recall or image-overwrite
contract yet.

## Desk gate

Run:

```text
python tools/a64/a64_core_worker_check.py --pmfc <path-to-pmfc>
```

The gate refuses Python `-O`, compiles the real fixture with emitted assembly,
and executes its `Main` entry in the A64 interpreter. That primary execution
admits only the exact flat image for instruction fetch, the emitted BSS, a
bounded 64 KiB primary stack and the four exact 64-bit firmware spin slots.
Seven active negative probes prove that reads, writes and fetches outside those
regions (including wrong-width and nearby low-memory spin accesses) are
rejected. After the generated entry's BSS clear and before `Main`, the host
poisons every byte of all four 256-byte boot records and control rows plus
core 1's spin slot. Each complete watched BSS extent is independently admitted
and checked for overlap. It then traces all five actual `CoreRawPrepare` calls:
all four ownership refusals must leave every poisoned byte and all ownership
metadata unchanged, issue no data-cache operation, read no spin slot and
perform no protected store; the
one valid route must publish the boot/row/stack metadata, leave release state
and spin slots alone, and execute exactly the eight cache-line cleans for the
two 256-byte regions. The returned entry stack and frame-pointer are also
checked. A second build links that same decoded fixture at `$001FC000`, inside
core 1's otherwise valid page; its fifth preparation must return the precise
range refusal without protected stores or cache operations. Removing the
running-image overlap check makes that relocated fixture take the success route
and is a required mutation kill. This is off-board control-flow evidence, not a
claim that a core was released.

The remaining gate checks that both raw procedures have no generated
frames or static-BSS access, allowlists the single raw MMU call, verifies the
EL3 register sequence, private-L1-only set/way operands, release/acquire and
spin-slot clean/barrier/event order, and checks that `READY` follows every
mapping witness. It verifies all three exact stack pages, the protected monitor
region, and refusal of wrong-core, partial, shared and unrelated ranges. Four independently
compiled ownership mutants remove the prepare guard, remove exact-pair matching,
remove the monitor region, or give two cores one page; their emitted programs
must fail at the expected assertion routes. Additional source mutations remove
cold-record cleaning, row cleaning, spin-slot cleaning, the barrier, event,
acquire, release, MMU join, cache invalidation, EL3 TLB invalidation, requested
M/C/I guard, the register-only pre-DRAM cold-state/SMPEN refusals and the join's
defensive refusals. They also inject CLIDR all-level discovery, premature READY,
a wrong row stride and a declared raw parameter. Every mutation must be killed.

Three independent interpreter instances then execute the emitted secondary
entry over one shared byte dictionary. They prove distinct core IDs, stacks and
rows; exact context and translation witnesses; the `x0/x1/x2` ABI; and refusal
to publish on wrong EL, missing requested coherency flags, an as-found EL3
SCTLR with any of M/C/I lit, or absent SMPEN. The EL1/EL2 checks trace both
system-register and memory reads and require that neither CPUECTLR nor the cold
DRAM record was touched. Every interpreted DC ISW operand is traced against a
modeled dirty private L1 and dirty shared L2: L1 must be invalidated and the
shared-L2 sentinel must remain dirty.

A second emitted/interpreter fixture substitutes a legal join that overwrites
every scratch register x0..x18 before returning success. The secondary retains
core ID in x27 and context/row in x25/x26, and the fixture requires the exact
core/context/row witness after that maximal clobber.

The model makes all stores instantly visible and treats cache maintenance,
barriers, TLB operations, WFE and SEV as instruction-level effects or no-ops.
It cannot prove cache coherency, ordering, real sleep/wake, firmware spin-table
behaviour, simultaneous execution, speed or any silicon result.

## Next bounded hardware boundary

After the board owner explicitly wires this inactive library and grants an
attended lease, the first proof should release one secondary only. Record the
fresh monitor map and verify that the reserved `$001FC000..$001FEFFF` band,
bootstrap record, row and firmware slot are disjoint and resident. Arm the
primary-owned deadman, prepare core 1 with only its `$001FC000` page, release
it, and use a bounded wait without petting the watchdog. Require `READY`, core
ID 1, the exact stack and row, EL matching the primary, and exact
TTBR/TCR/MAIR/SCTLR witnesses. A timeout is a failure, not permission to release
another core.

Only after cores 1, 2 and 3 pass one at a time should a later milestone add a
register-only disjoint-buffer worker and release/acquire ping-pong. Atomics,
interrupts, per-core vectors and ordinary source tasks remain later boundaries;
general parallel procedures require a compiler reentrant-frame contract first.

## Architectural references

- [Arm Cortex-A72 TRM 100095 r0p3](https://developer.arm.com/documentation/100095/0003/)
  documents the shared L2 topology on PDF page 17 and, in section 4.3.67 on
  PDF page 208, the CPUECTLR_EL1.SMPEN prerequisite before enabling caches/MMU
  or performing cache/TLB maintenance. Its cache-identification and set/way
  register definitions supply the operand fields used here.
- [TF-A Cortex-A72 CPU operations, pinned 38269bb7](https://github.com/ARM-software/arm-trusted-firmware/blob/38269bb73d34b4a31100adf208a27e4c28e7d611/lib/cpus/aarch64/cortex_a72.S)
  independently separates `cortex_a72_core_pwr_dwn` level-1 maintenance from
  level-2 maintenance in `cortex_a72_cluster_pwr_dwn`, and enables SMPEN in
  `cortex_a72_reset_func`.
