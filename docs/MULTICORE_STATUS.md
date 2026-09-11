# Multicore status — Raspberry Pi 4 (BCM2711, Cortex-A72)

Desk report, 2026-09-10. **No board was contacted while this was written.**
Every number below is either read out of the source in this repository, taken
from a dated board record, or produced by building and executing something at
this desk. Where a claim is reasoning rather than a measurement it says so on
the line that makes it.

---

## 1. What the board boots today, and the evidence

**The Raspberry Pi 4 on this bench boots at EL2, under the firmware's own
stub. Anvil's EL3 stub has never been written to the boot medium.**

| Question | Answer | How it is known |
|---|---|---|
| What is on `KERNEL8.IMG` | Anvil 41 — 2,465,268 bytes, linked `$00200000..$00459DF3` | The board answered `version` over the wired UDP console on 2026-09-10; recorded in the Pi 4 board lock |
| Which stub runs it | **The firmware's default `armstub8-64.bin`** | `CONFIG.TXT` on the stick is the original plus exactly ONE line, `dtoverlay=vc4-kms-dsi-waveshare-panel-v2,10_1_inch_a`; `CONFIG.BAK` beside it is the byte-exact original. **There is no `armstub=` line.** No deployment since has changed it: the build-24 record states "Deployment changed no boot stub, configuration, settings, or model file" |
| Which exception level | **EL2** | Direct board record, 2026-09-10 02:20 UTC: "Build 23 is still running **at EL2** with caches on and the V3D console active". Nothing since has changed the stub, and the stock stub's only exit is an `eret` to EL2 |
| Were cores released | **No.** Every board checkpoint through 2026-09-10 says so explicitly — "EL3/multicore inactive", "no secondary cores or EL3 stub will be activated overnight", "No EL3/core activation" |

**Our EL3 stub exists and is exact, and it is not installed.**
`RaspberryPi4/Board/armstub8.asm` rebuilds at this desk to **512 bytes,
SHA-256 `135db99456f65bf3c4f48383125f5b57842409eeaee137dcce7fc85eab35fd16`** —
reproducing the figure recorded on 2026-09-07 and again on 2026-09-10 exactly.
`tools/a64/a64_el3_check.py` **PASSES** on current `main`. The 2026-09-07 flash
log's own entry still reads *Files written: **none***.

**The multicore library is not in the monitor.** `RaspberryPi4/Lib/core_worker.pi4`
and `RaspberryPi4/Lib/mmu_secondary.pi4` appear in no `XIncludeFile` line of
`RaspberryPi4/Board/board.pi4`; the only files that include them are the test
fixtures under `RaspberryPi4/Tests/`. The shipped monitor therefore contains no
code that can release a core, and would refuse to if it did — see §2.

### What this means for every other line in this report

At EL2, `CoreRawPrepare()` refuses with `#CORE_RAW_ERR_EL` before it touches a
cold record, a control row, a cache line or a spin slot; and the raw secondary
entry parks at its first check. **On the board as it stands, a core release is
not merely unwise — it is unreachable.** That is a good property and it is now
executed rather than asserted (§3).

---

## 2. The desk check of the saved bootstrap

### 2.1 Parameterless and naked — holds

`CoreRawSecondary()` and `MmuSecondaryJoinRaw()` are both
`ProcedureNaked …()` with no declared parameters, one audited ASM block each,
no BSS reference inside the join, and exactly one call between them (the
secondary's `bl MmuSecondaryJoinRaw`). This matters because of the compiler
contract in §4: a declared parameter on an A64 procedure becomes a spill to a
fixed BSS word, and `ProcedureNaked` **does not** suppress that spill.

### 2.2 Private versus cluster-shared cache ownership — holds, and the reason is not the one the comment gives

The join invalidates the core-private L1 data cache and never the A72's
cluster-shared L2, which can hold the running primary's dirty lines. Two
independent mechanisms keep it there, and only one of them was documented:

* `CSSELR_EL1` is set to 0 and `CLIDR_EL1` is never read, so no level
  enumeration exists to walk up to L2. This is what the source comment
  describes.
* **The `DC ISW` operand's level field (bits 3:1) is structurally zero**, because
  the operand is only `(way << wayShift) | (set << log2(lineBytes))` and
  `log2(lineBytes) >= 4`. *This* is what actually decides which cache the
  instruction reaches. CSSELR only selects which geometry `CCSIDR_EL1` reports.

Both are now pinned by separate mutants in
`tools/multicore_reservation_check.py`. Worth knowing before anyone "improves"
the routine: restoring a CLIDR/LoC walk *and* an operand level field is what
would make the shared L2 reachable, and either change alone looks harmless.

The set/way walk itself is complete and geometry-independent: the gate executes
it against the A72's real geometry (64-byte lines, 2 ways, 256 sets) and against
a deliberately different one (128-byte lines, 4 ways, 128 sets) and requires the
executed operands to be exactly the way/set product in both.

### 2.3 Publication ordering — holds, decoded from the image

Proven by decoding the instruction words the interpreter fetches out of the
built image, not by reading the compiler's assembly listing. (The house rule
"trust the disassembled hex, not the listing" exists because the listing once
showed frame prologues the binary did not contain.)

**Primary release, in executed order:**

```
dc cvac x4 (the four cold-record lines)   dsb; isb
dc cvac x4 (the four control-row lines)   dsb; isb
str  <entry>, [spin slot]
dc cvac    (the slot's line)
dsb; isb                                  (MmuCleanRange's own barrier)
dsb; isb                                  (a64_barrier)
sev
```

and nothing writes the cold record or the control row after the slot is armed.

**Secondary join and publication, in executed order:**

```
currentel / sctlr_el3 / cpuectlr_el1 guards   (registers only, before any DRAM)
dc isw  x (ways*sets), level 0 only
dsb; isb; ic iallu; tlbi alle3; dsb; isb
msr ttbr0_el3 / tcr_el3 / mair_el3
dsb; isb
msr sctlr_el3; isb
readbacks
nine witness stores to row+8 .. row+72
stlr  READY, [row+0]          <- exactly one store-release, and no plain store
dsb; sev; wfe
```

The primary consumes the state word with `ldar`.

### 2.4 Exact stack reservations — hold, and are now checked as arithmetic

`$001FC000..$001FEFFF`, three exact 4 KiB pages, one per secondary. The
previous gate checked this by asserting the literal text `$001FC000` in the
board file. That cannot notice the autoboot page moving down, the measured
monitor extent growing into the band, or the low payload window's computed
floor dropping. The new gate executes the board's own accessors and recomputes,
for whatever the board answers:

* each core gets exactly one 4 KiB page, page-aligned;
* the three pages are distinct, non-overlapping and contiguous;
* **exactly one declared monitor region IS the band** — not wider (which would
  refuse memory nobody reserved) and not narrower (which would leave a page
  unprotected);
* the band is disjoint from **every other** declared monitor region and from
  **every** payload window, however many the board declares;
* the byte above the band — the highest stack's initial SP — is owned by
  something declared, so the first push cannot land in unclaimed memory (it is
  the autoboot page, which is refused in its own right);
* the shipped `HitsMonitor()` refuses all three pages and names the right
  region, and refuses neither the byte below nor anything outside.

### 2.5 Refusal of unsupported exception and cache states — holds, executed

One image, run at five machine states, verdicts read out of memory:

| State | Verdict |
|---|---|
| EL2 | `CoreRawPrepare` refuses `#CORE_RAW_ERR_EL`; no cache maintenance, no SEV, core not marked prepared, release then refuses `#CORE_RAW_ERR_STATE` |
| EL3, SCTLR M/C/I clear | refuses `#CORE_RAW_ERR_MMU` |
| EL3, M/C/I set | accepted; eight record/row line cleans, one slot clean, one SEV |
| secondary arriving below EL3 | parks before reading `CPUECTLR_EL1` and before deriving any DRAM address |
| secondary arriving warm (any of M, C, I already set) | parks before the destructive set/way walk |

### 2.6 What does NOT hold, and is owed

* **The bounded wait is a spin count, not a deadline.**
  `CoreRawWaitReady(core, spins)` counts iterations. The same loop with the
  caches off is orders of magnitude slower than with them on, so one constant
  cannot mean one time — this is the shape forum 726 already records against the
  I2C driver. The witness in §5 carries a wall-clock replacement built on
  `CNTPCT_EL0`/`CNTFRQ_EL0` with a loud refusal when `CNTFRQ_EL0` is not
  positive. **Moving it into `RaspberryPi4/Lib/core_worker.pi4` is owed to that
  file's owner; this lane's file boundary does not include it.**
* **A READY word is not a witness of this run.** Nothing in the state word ties
  it to the run that armed the core, so a row left READY by an earlier run in
  memory nothing cleared is indistinguishable from a core that has just come up.
  The witness carries the fix — a per-run nonce the publisher must echo, read
  after the acquire — and the same note applies: it belongs in `core_worker.pi4`.
* **`CoreRawPrepare()` cannot be correctly called from a payload.** Its
  running-image overlap guard asks `HwMonLo()`/`HwMonHi()`, and those are derived
  from `__image_start__`/`__image_end__` **of the image that contains them**.
  Called from a payload it measures the payload and reports that a secondary
  stack clear of the payload is clear of the monitor too. That is a confident
  wrong answer with no symptom, and it is why the witness in §5 does not call it.
* **A released core parks in the code that released it.** The park loop is two
  instructions inside the released routine. From a payload, that memory is where
  the monitor stages the *next* payload — and the core cannot be recalled. The
  permanent worker belongs in the resident monitor, which is what
  `core_worker.pi4`'s own header already says; it is repeated here because it is
  the single fact that decides the shape of every board step below.

---

## 3. The new gates

Both are new in this lane. Neither replaces `tools/a64/a64_core_worker_check.py`;
they cover axes it does not.

### `tools/multicore_reservation_check.py`

```
multicore_reservation_check: PASS - 1132 decoded-image, executed-refusal and
reservation checks; 18 of 18 mutants killed
```

Adds, over the existing gate: grading the **decoded image** rather than the
assembly listing; **arithmetic** on the board's own answers rather than literal
text; the machine-state refusals **executed** at EL2 and at a cold EL3; and the
proof that the bounded wait **times out** when no secondary exists.

Every one of the eighteen mutants is killed by its intended check, and `--verbose`
prints which check killed which — a mutant killed by the wrong check is a gate
that has quietly stopped watching what it claims to watch, and a count cannot
tell the two apart. The mutants cover: an under-covering region edge, two cores
aliased onto one page, the band moved into a payload window, the band no longer
being a declared region, a missing slot clean, a missing release barrier, a
missing event, the record written after release, READY published with a plain
store, READY published early, the `DC ISW` level field naming the shared L2, a
restored CLIDR walk, `tlbi alle2` for `alle3`, `SCTLR_EL3` enabled without an
`isb`, a way-shift hard-coded to the A72's geometry, prepare accepting a
non-EL3 primary, prepare accepting a cold primary, and a wait that accepts a
stale row.

### `tools/multicore_witness_check.py`

```
multicore_witness_check: PASS - 122 executed checks over six machine states;
11 of 11 mutants killed
```

Runs the real witness image (§5) at EL2 under the stock-stub SCTLR, at EL2 with
caches on, at EL3 cold, at EL3 without SMPEN, at EL3 with everything, and with
`CNTFRQ_EL0` zero. It proves by execution that the witness never stores below
`0x1000`, never executes `SEV` or `WFE`, never reads `CPUECTLR_EL1` below EL3,
consumes its state word with `ldar`, leaves no READY word behind, and that its
deadline follows the counter frequency rather than a loop count.

### An existing gate is RED on `main`, and it is not this work

```
a64_core_worker_check: FAIL after 111 checks: board stack reservation missing
ProcedureReturn 5
```

`tools/a64/a64_core_worker_check.py` asserts the literal text
`ProcedureReturn 5` in `RaspberryPi4/Board/memmap.pi4`. Commit `04f7973` (the
driver-module lane) declared the module arena as a sixth monitor region, so
`HwMonRegions()` now answers **6**. The reservation itself is untouched and
correct; the gate is counting.

Three sites need it, at `tools/a64/a64_core_worker_check.py` lines **183**,
**547** and **880**. The correct repair is not to change 5 to 6 — that puts the
same trap back one commit later. It is to drop the count assertion entirely and
keep the two `Case 4 : ProcedureReturn #CORE_RAW_STACK_LO/HI` tokens already
being checked, replacing the `("monitor reservation", …)` mutant with one that
points region 4's edges elsewhere. That is the shape
`tools/multicore_reservation_check.py` uses, for exactly this reason.

**Not fixed here: that file is outside this lane's boundary.** It is owed to the
raw-core gate's owner, and it is red on `main` now.

---

## 4. Compiler reentrancy — REPORT ONLY

Nothing in the compiler was changed. File and line references below are into the
private compiler tree (not part of this repository).

**The procedures a secondary core executes today are the two naked ASM blocks in
§2.1, and neither is affected by anything below.** This section is the contract
that has to exist before *any* ordinary generated procedure can be called by a
second core — and before the raw worker may ever `bl` into one.

### What makes a generated A64 procedure non-reentrant

| # | Where | What |
|---|---|---|
| 1 | `RaspberryPi4\IRCore_A64.pbi:2578-2585`, `:2592-2593` | The recursion check's own comment: parameters and locals are static BSS slots, one per `(procedure, name)`; and the allocator has no notion of call-clobbering. Two independent defects, both still true. |
| 2 | `RaspberryPi4\IRCore_A64.pbi:3299`, `:3326-3329` | The parameter receiver stores incoming `a0..a7` (`x0..x7`) into one fixed BSS word per `(procedure, parameter)`. |
| 3 | `RaspberryPi4\EmitCore_A64.pbi:969-970`, `:954-956` | The procedure frame is `sub sp, sp, #16` / `str x30, [sp, #8]` and its inverse. It owns **only** `x30` — so a per-core SP buys nothing, because no mutable state is on the stack. |
| 4 | `RaspberryPi4\EmitCore_A64.pbi:1283`, `:1318-1321` | The BSS emitter walks the whole symbol table with no owner or storage-class filter, so a procedure-owned local gets a `.space` label exactly like a Global. |
| 5 | `RaspberryPi4\IRCore_A64.pbi:5174`, `:5217-5238`, `:5378-5422` | The allocator pool is **eleven caller-saved registers — `x2..x7` *and* `x11..x15`**, with `x9`/`x10` pinned. `x0`/`x1` are excluded. **`x29` is neither allocated nor reserved: it is simply never used**, and `A64RegNum` has no mapping for the callee-saved bank at all, so it is unreachable from IR. The liveness loop kills nothing at a call. |
| 6 | `SemanticCore.pbi:7631-7636`, `:7869-7882` | Value-form string calls are rewritten through `__strtmp_N`, 32-byte buffers declared at **program scope**. `p = Left(s,4)` inside a procedure writes a file-scope buffer. |
| 7 | `IRCore.pbi:359-362` | `__cattmp_N` concatenation temporaries: one buffer per concatenation **site**, program-wide. (Separately: `IRCore_A64.pbi` never calls `NewConcatTemp()` at all — a different defect, worth its own look.) |
| 8 | `SemanticCore.pbi:6438-6439`, `:6450-6451` | `__swaptmp<N>` is a compiler-invented `#AST_VAR_DECL`, so on A64 it becomes a BSS slot. |
| 9 | `RaspberryPi4\IRCore_A64.pbi:1824-1836`, `:1249-1250`, `:1265-1269` | The `Read`/`Restore` data cursor `__data_ptr` is **deliberately** forced to global scope and is a read-modify-write of one absolute word with no atomic. Two cores reading the same `DataSection` lose and duplicate records. |
| 10 | `RaspberryPi4\IRCore_A64.pbi:3260`, `:3269-3272` | A `.s` parameter is a 32-byte buffer at a fixed address that entry code copies into. |
| 11 | `SemanticCore.pbi:5954`, `:5911-5912`, `:5994` | `HoistStatics` renames `Static` to `__st_<proc>_<name>` at file scope. Correct by language semantics, shared by definition — but that must become a stated guarantee rather than an accident of layout. |
| 12 | `RaspberryPi4\EmitCore_A64.pbi:521`, `:562-563`, `:578`, `:597-607`, `:703-715` | `_start` is single-entry: one SP from `A64StackTop`, one DAIF mask, one BSS zeroing pass, one `CPTR_EL2`/`FPCR` write. A second core entering the image would re-zero live BSS; a second core that *skips* `_start` never gets its FP gate opened, so `.f` code traps or rounds differently there. |
| 13 | `RaspberryPi4\A64Assembler.pbi:189-191` | `#A64_STACK_TOP_DEFAULT = $08000000`, one number for the whole image. **No per-procedure stack size and no stack budget is emitted anywhere** — a repo-wide search for stack metadata finds only `A64FramePlan.pbi`'s own disclaimer. A second core has no stack, and the toolchain cannot say how much it would need. |

### Two findings that are new, and both are sharper than the list above

**The mutual-recursion refusal is escapable by an indirect call.**
`CheckMutualRecursion` (invoked at `RaspberryPi4\IRCore_A64.pbi:2598`,
implemented at `Atmel328pAndRelated\IRCore_AVR.pbi:969`, refusal text at `:992`)
builds its call graph in `PMCollectCalls` (`IRCore_AVR.pbi:627`) and records an
edge **only** when the callee name is a declared procedure. An indirect call is
an `#AST_FUNC_CALL` whose value names a *variable*
(`IRCore_A64.pbi:5040-5042`), so the lookup misses, no edge exists, no cycle is
found, and it lowers to `blr` (`EmitCore_A64.pbi:933`). `sink = @Fac : sink(5)`
compiles clean and reproduces the exact BSS clobber the refusal exists to
prevent. A reentrant-frame contract that an indirect call can bypass is not a
contract.

**`ProcedureNaked` with declared parameters is not refused — it is silently
miscompiled.** Naked suppresses exactly two things
(`EmitCore_A64.pbi:951-952`, `:966-967`): the prologue and the epilogue. It does
**not** suppress the parameter receiver spills (the loop at
`IRCore_A64.pbi:3258` has no naked guard anywhere) and it does **not** suppress
the BSS slots for declared locals. So a naked procedure with a parameter emits a
write through `x9` into BSS *before the programmer's hand-written prologue runs*
— on an exception-vector entry point, which is the documented use for Naked,
that is state corruption before the handler has saved anything. Nothing in
`SemanticCore.pbi` checks arity against naked-ness. **This is why the raw worker
contract's "no declared parameters" rule is load-bearing and must stay a rule
the gate enforces, since the compiler will not.**

Parameters are capped at 8 and beyond that are a hard frontend error
(`IRCore_A64.pbi:3279`, `:3295-3296`, `:5111`, `:5122-5123`) — no silent drop.

### Citations from the 2026-09-09 audit that have drifted

Said plainly, because a stale citation is read as a current fact:

* **`EmitCore_A64.pbi:352-582` is not the `_start` preamble.** `:340-368` is
  inside `A64ModuleWrapper()`. `_start` is emitted at **`:521`**.
* **`EmitCore_A64.pbi:569-582` is not the floating-point gate.** Those lines are
  the `--entry-returns` loader save. The gate is now at **`:703-715`**.
* `IRCore_A64.pbi:3239-3327` for the parameter receiver: the loop opens at
  `:3258` and the stores are at `:3326-3329`. Also, the receiver's addresses are
  **not "absolute"** in the encoding sense — they lower to `adrp`/`add`
  (`EmitCore_A64.pbi:767-768`). One fixed address, PC-relative encoding; the
  reentrancy consequence is identical but the wording was wrong.
* `IRCore_A64.pbi:5338-5421` for the call-clobber defect points at the liveness
  loop; the substantive evidence is the pool note at `:5174` and `:5195-5200`.
  The conclusion stands, the citation pointed at the wrong half.
* `SemanticCore.pbi` already computes `Symbol\Size`, `Symbol\StackOffset` and
  `ProcStackSizes` (`:43-44`, `:356`, written at `:1190-1191`, `:3889`) — and
  **nothing on the A64 path consumes either**. The file says so itself at
  `:118-119`.

### The minimal compiler contract change

As a list of required guarantees, in dependency order:

1. Every parameter and every non-`Static` local is addressed relative to a
   per-activation frame register, never by symbol — and the BSS emitter skips
   those symbols.
2. The prologue reserves and the epilogue releases `LocalBytes`, driven by one
   carried predicate at both sites.
3. The parameter receiver — including the `.s` parameter's 32-byte buffer —
   stores into frame slots.
4. The allocator gains a call-clobber kill set, so a vreg live across a call is
   spilled to that frame or allocated from a callee-saved bank (which is
   currently unreachable from IR at all).
5. Every compiler-created temporary that is file-scope today becomes
   frame-allocated: `__strtmp_N`, `__cattmp_N`, `__swaptmp_N`.
6. Shared runtime state is made explicitly shared **and its concurrency rule
   stated**: at minimum `__data_ptr` becomes per-core or an atomic cursor, or
   `Read` is refused off the boot core. `Static` and `Global` stay shared by
   definition — as a documented guarantee, not as a layout accident.
7. The recursion refusal is replaced, **and the indirect-call hole is closed in
   the same change.**
8. Per-core stack provisioning becomes a build-time artifact: per-procedure
   `LocalBytes`, a whole-program worst-case depth, and a second stack region.
9. `_start` is split into "initialise the image once" and "initialise this core".
10. `ProcedureNaked` with declared parameters is refused.

### What the committed frame planner does and does not provide

`RaspberryPi4\A64FramePlan.pbi` is **inactive**: its only `XIncludeFile` in the
whole tree is `tools\Diagnostics\a64_frame_plan_check.pb:36`, a standalone host
harness. It changes zero bytes of any emitted image. Activating it needs
`IRCore.pbi` to include it before line 1108, plus `pmfc.pb:141` and
`PureMetalForge.pb:816` for the emitter side.

It **provides** the inputs to guarantees 1 and 2 — deterministic per-symbol slot
sizing and alignment, per-procedure `LocalBytes` rounded to 16, correct
parameter and naked identification from the AST, and owner-explicit symbol
identity that does not split flattened names. It **provides none of** guarantees
1 and 2 *in effect* (it explicitly does not touch `SymbolTable()` or BSS
layout), and none at all of 4 (call-clobber — the second of the two independent
causes, untouched), 5, 6, 7, 8 or 9.

---

## 5. The witness — `RaspberryPi4/Examples/Diagnostics/pi4CoreWitness.pi4`

Diagnostic. It does not ship (rule 19).

### What it is

A returning payload that **releases no core**. There is no path in it that does:
it never stores below `0x1000`, never executes `SEV`, and never calls
`CoreRawPrepare` or `CoreRawRelease` — all four proven by execution in
`tools/multicore_witness_check.py`, not by reading it. The three reasons it must
not release are in §2.6 and repeated in the file's own header.

It writes a report block into its own BSS and returns that block's **address** in
`x0`, because there is no serial adapter on this bench and the monitor prints a
returning payload's `x0`. The first and last words of the block are the magic
`$4357495441424C45`; if they are not there, the block was not written and
nothing between them is this program's.

### What it proves on the silicon

* the exception level the monitor is actually at, and **the SCTLR of that
  level** — at EL3 an `mrs sctlr_el2` is legal and answers a register the
  processor is not using, so reading the wrong one gives a plausible number and
  no fault;
* `CPUECTLR_EL1.SMPEN`, **read only at EL3** and behind a runtime branch on the
  measured level, because it is implementation-defined, may trap below EL3, and
  this board installs no exception vector — a trap here is a silent hang;
* the four firmware spin slots at `$D8/$E0/$E8/$F0`, read. Nothing in this tree
  has ever reported what the stock stub leaves in them on this board;
* that the three board-reserved secondary stack pages are readable, and what
  they hold;
* **the primary-side wait contract, against the real counter**: a wall-clock
  deadline off `CNTPCT_EL0`/`CNTFRQ_EL0`, an acquire load of the state word, and
  a per-run nonce the publisher must echo. Three self-tests drive it against the
  program's own word — one that never becomes ready (must time out), one ready
  with this run's nonce (must succeed), and one ready carrying **another run's
  nonce** (must refuse). The third is the stale-word refusal, executed.

### What it does not prove, and the list is the point

Nothing about a second core. Not that one exists, not that one is parked, not
that one can be woken, not cache coherency, not WFE/SEV, not the publication
ordering as the hardware observes it, not parallelism, not the EL3 stub. **This
is the precondition half.** It is not a scheduler, it is not a job API, and a
single READY flag would not have been completion even if one had been raised.

### Expected result on the board as it stands

**Status 1, `#CW_ERR_NOT_EL3`.** The board boots at EL2 (§1), so the witness
reports the level, reports `-1` for the unread `CPUECTLR_EL1` (which is a
different fact from "read as zero"), passes its three wait self-tests, and says
so. That is a measurement, not a failure.

### The image

| | |
|---|---|
| Source | `RaspberryPi4/Examples/Diagnostics/pi4CoreWitness.pi4` |
| Build | `pmfc RaspberryPi4/Examples/Diagnostics/pi4CoreWitness.pi4 -t pi4 --load-addr 0x500000 --stack-addr 0x4F00000 --entry-returns -s -o pi4CoreWitness.img` |
| Raw image | **4,768 bytes**, SHA-256 `15b1e361b93689ef2edd38e72fa842a91c3266ce23ca8a9ce6baf54f80c17179` |
| Container | **4,864 bytes**, SHA-256 `91b645502eeb6b271c2fa40d3c501b2f0f2c711a2e731f06a8495d6c2ca92a75` |
| Code | `$00500000..$0050129F` |
| BSS | `$00580000..$0058023F` |
| Report block | `$005800E0` (also returned in `x0`) |
| Stack top | `$04F00000`, growing down, clear of both |

Rebuild it from source rather than trusting a copy; the two gates do exactly
that on every run and the numbers must come out the same. A built copy sits in
`_work/multicore-witness/` (gitignored, never committed) alongside a freshly
rebuilt `armstub8.bin` at the recorded 512 bytes — both are conveniences, and
the hashes above are the contract.

### The board slot this needs

Not taken. Requested from the board owner, to be run by them:

1. `map` first — confirm the low payload window's current base. If it is not
   `$00500000`, rebuild with that `--load-addr` and re-hash; the source is
   unchanged and the container is the only thing that moves.
2. Confirm the image is clear of the resident ONNX assets
   (`$40000000..$5359BFFF`, `$54000000..$56080000`, `$60000000+`). At
   `$00500000` with BSS at `$00580000` it is, by three orders of magnitude.
3. `deadman 15`, then upload to **RAM only** and `boot mem` / `run` at the
   staged address. **Never `--to card`. `KERNEL8.IMG` is not touched.**
4. Expected: it returns in a few milliseconds with `x0` = the report address.
5. `memory <that address> 100` and record all 32 words.
6. Expected verdict word (report word 2) is **1** — not at EL3.

**Risk:** the payload executes no store below `0x1000`, no `SEV`, no `WFE`, no
device access, and no call into the monitor; it reads five system registers,
four spin-table words and six words of reserved DRAM, and returns. Its longest
loop is one 5 ms deadline; the other two self-tests find their word already set
and return at once.
**Recovery:** none should be needed, and the deadman covers the case where that
is wrong. Nothing on the boot medium changes, so a power cycle returns the board
exactly as it was. The monitor in RAM is not replaced; only the staging window
is written.

---

## 6. Proven versus reasoned

**Proven by execution at this desk** (and only that — the interpreter has no
cache, no TLB, no store buffer, no WFE/SEV timing and no simultaneous
execution): the reservation arithmetic against the board's own answers; the
monitor's refusal of all three pages through the shipped predicate; the
prepare/release refusals at EL2 and at a cold EL3; the release ordering and the
join's maintenance ordering, decoded from image bytes; private-L1-only cache
ownership by two independent mechanisms; a complete set/way walk at two
geometries; the secondary's publication ordering and single store-release; the
bounded wait timing out with no secondary; the witness's wall-clock deadline,
acquire load and nonce refusal; and 29 negative mutants across the two new
gates, each killed by its intended check.

**Proven by rebuilding from source:** the EL3 stub is 512 bytes with SHA-256
`135db994…b35fd16`, reproducing the recorded figure exactly.

**Established from dated board records, not re-measured here:** that the stick
boots Anvil 41 under the firmware's default stub at EL2, with no `armstub=` line
in `CONFIG.TXT` and no core ever released.

**Reasoned, not measured:** everything about what a second core would actually
do. Cache coherency between a joined secondary and the primary; whether `WFE`/
`SEV` wake a parked core on this part; whether the firmware's stock stub has in
fact left cores 1–3 parked and its spin slots zero; whether the release ordering
is sufficient as the A72 observes it; and every claim in §4 about what would
happen if two cores entered one generated procedure — that last is derived from
the emitted code and the compiler source, and has never been run on two cores
because no two cores have ever run.

**Not started:** the job/ownership API. `Anvil/Core/jobs.pbi` does not exist and
must not until §2.6 and §4 are closed. Bounded queues, isolated or synchronised
resources, and a cancellation that does not pretend an executing core has
stopped are all downstream of a compiler contract that does not exist yet.
