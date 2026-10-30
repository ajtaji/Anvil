# The layering gate

A library exists once. Boards differ in the interface under it.

`tools/layering_check.py` is the mechanical half of that rule. It reads the
tracked sources, resolves names, and refuses a shared file that has taken a
dependency on one board. It compiles nothing, needs no board, needs no
third-party package, and finishes in a few seconds.

Run it before you commit:

```sh
python tools/layering_check.py
```

Exit `0` is a pass, exit `1` is a refusal. `--self-test` builds a throwaway
tree with one violation of every rule planted in it and proves each rule goes
red on its own plant; run that if you change the tool.

## Why it resolves names instead of walking includes

This language's include model is flat. A board composition includes the
shared files and the board files into one list, in order, and from then on
every name is in scope. So a shared file calls a board procedure with **no
include edge to find** — the name is simply there.

The numbers say how badly an include walk would lie. At `f676ba8`, 42 files
under `Anvil/` make **929** calls to names that only a board folder defines,
and behind all of them there is exactly **one** non-test downward include in
the whole shared tree (`Anvil/Graphics/Vulkan/vk_ir_v3d42.pi4:13`, and it is
written as a relative path, `../../../RaspberryPi4/Lib/v3dqpu.pi4`). An
include-graph gate would have reported a clean tree.

Count the seam calls back in — the console bytes and the clock, which are
real three-board seams — and the raw figure is **2,937** downward calls. That
is the number the layering plan measured as 2,998 the same morning, before
three moves landed.

## The five rules

### 1. No downward call

Every `Procedure` / `ProcedureNaked` definition in the tree is indexed, in
every extension the compiler knows: `.pbi .pi4 .pi3 .unoq .rockpi4c .pb`.
Names are matched **case-insensitively**, because they are case-insensitive
in this language. A file under `Anvil/` is shared; a file under
`RaspberryPi3/`, `RaspberryPi4/`, `RockPi4C/` or `ArduinoQ/` is board.

A call from a shared file to a name that **only** board folders define is a
downward call. A name defined in a shared file as well is not — it resolves
upward.

**The seam is the exception, and it is modelled honestly.** A name declared
as a seam in `Anvil/Hal/hal.pbi` or `Anvil/Hal/seams.pbi` is a legal
upward-facing contract even though boards define it. That is what
`UartWriteStr`, `PrintDec`, `Ticks`, `millis` and the whole `HwGpio*` family
are. Everything else is a violation.

A seam is declared the way `hal.pbi` already declares one: the name **opens
its line** inside the contract comment, with its arguments, or opens a family
with a star, and several may share a line separated by `/`.

```
;                 UartDrain()            block, bounded, until the last
;                 HwLinkSend(kind, buf, n, ms)
;                 UartMessageBegin() / UartMessageEnd()
;    HwGpio*   (#CAP_GPIO)  general-purpose I/O
```

299 names and 21 `Hw*` families are declared that way today. A name that
merely appears inside an English sentence is **not** a declaration. The
reading is deliberately strict: a loose one silently forgives real downward
calls, and forgiving is the one failure a ratchet cannot recover from. If a
contract written some other way gets reported, reword the line — do not widen
the reader.

### 2. No downward include, and no board extension in the shared tree

A shared file may not `XIncludeFile` or `IncludeFile` a board path, in either
spelling: repo-root relative, or relative to the including file.

Separately, a `.pi4`, `.pi3`, `.unoq` or `.rockpi4c` file **under `Anvil/`**
is the directory lying about the file. 42 exist today: seven real V3D and
Neon back-end files in `Anvil/Graphics/Vulkan/`, and 35 gate compositions
under `Tests/`. The list is frozen; a new one is refused.

### 3. No second implementation of a protocol

A fingerprint table maps a constant, a magic word or a register signature to
the file that owns it, and the gate counts it everywhere else. Patterns are
matched against **code only** — comments and string literals are blanked
first — because a protocol named in a sentence is a reference and a protocol
written in an expression is an implementation.

| Fingerprint | Owner | Sites elsewhere, today |
|---|---|---|
| `crc32-polynomial` — `$EDB88320` in an expression | `Anvil/Core/crc.pbi` | 6 |
| `sha256-constants` — the initial hash and round words | `Anvil/Core/sha256.pbi` | 0 |
| `videocore-mailbox-registers` — the `…00B880`/`898`/`8A0`/`8B8` block | none yet | 5 in 2 files |
| `videocore-mailbox-request` — the channel-8 request word | none yet | 1 |
| `dtb-magic` — `$D00DFEED` | `Anvil/Core/boot_cmd.pbi` | 4 |
| `fat-dirent-longname` — the attribute byte against `$0F` | `Anvil/Storage/fat32.pbi` | 1 |
| `pmfboot-container-magic` — PMFBOOT / P3SLOT as a raw word | `Anvil/Core/pmfboot.pbi`, `Anvil/Storage/ab_record.pbi` | 2 |
| `generic-timer-read` — `mrs …, cntpct_el0` / `cntfrq_el0` | `Anvil/Hal/aarch64_counter.pbi` | migration in progress; legacy sites remain ratcheted |
| `aarch64-mmu-attributes` — MAIR `$FF440C0400`, `$401`, `$70D`, `$711` | `RaspberryPi4/Lib/mmu.pi4` | 5 |

`crc.pbi` includes the portable `crc_constants.pbi` owner of `#CRC_POLY`;
monitor state includes that same owner. A line defining exactly `#CRC_POLY`
is exempt. Any other
spelling of the polynomial — `#CRC32_POLY`, or the value folded straight into
a shift loop — is a second implementation and is counted.

An owner of "none yet" means the protocol has no single home in the tree at
all. Every site is recorded, and naming an owner is the work.

### 4. No private-namespace crossing

A procedure whose name begins with a lower-case word and an underscore
declares that word as a private namespace: `fat_`, `xh_`, `exfat_`, `cyw43_`,
`a64_`, `neon_`, `net_`, `pi3ut_`, `v3d_`, `sdio_`, `uart_`, `dhcpd_`,
`sntp_`. The list is **derived from the tree**, not written down here, so a
namespace invented next week is covered the day it appears. The files that
define names in a namespace own it; a call from anywhere else has reached
inside a library.

435 crossing sites in 53 files today. The two the layering plan named are
both here: `RaspberryPi3/Lib/update_ab.pbi` reaches into `fat32.pbi`'s
private namespace at **22** sites — not the nine the plan estimated: 11
`fat_ClusterValid`, 4 `fat_ClusterLba`, 4 `fat_NextCluster`, 2 `fat_U16`, 1
`fat_U32` — and `RaspberryPi4/Lib/usbmsc.pi4` calls the private `xh_Trace`
exactly **10** times.

A namespace that is meant to be public is in the wrong clothes: rename it
with a capital, or declare it as a seam.

An exact declared seam also permits a compiler-fixed legacy name such as
`str_print_at`. That permits calls and addresses of that name, not other
helpers with the same underscore prefix. The self-test includes both cases
and verifies that mentioning a name in prose does not declare a seam.

### 5. One definition per name

Two files that can be linked into the same image may not both define a name.
Two board folders cannot share an image, so the same console on three boards
is not a collision. Neither is a stub inside a `Tests/` or `Examples/`
composition, which is its own program. Neither is a pair of definitions in
exclusive `CompilerIf` branches — the gate tracks compiler-conditional
definitions and does not count them against each other.

The original baseline recorded 45 names in three classes. The Vulkan seam
is now explicitly declared; the remaining baseline classes still need review:

- **The `avkBackend` contract** — Vulkan's link-time executor seam, with
  absent, validation-only, software and hardware alternatives. Exactly one
  is selected per image. Its exact typed declarations are in
  `vk_foundation.pbi`; the names are now also explicitly documented in
  `hal.pbi`, so the gate recognizes these alternatives as a seam rather
  than counting them as duplicate implementations. No wildcard exemption
  covers backend-private helpers.
- **13 `NetConsole*`, `NetDhcpTick` and `HwDir*`** — a shared implementation
  and the board stub sets that replace it. Legal alternatives; they are here
  because the seam is not fully named in `hal.pbi` yet.
- **4 genuine duplicates inside one board**: `Pi3ReadBe32`, `Pi3Park`,
  `Pi3BootMemory` and `Pi3BootMaxCoreClock`, each written twice in
  `RaspberryPi3/Board/`. These are real and should go.

## Shared binary32 math owner, 26 October 2026

`Anvil/Math/float32.pbi` owns the binary32 math used by the Neon float adapter.
It contains no board calls or hardware accesses. The old Pi4 math path remains
a compatibility include; shared code includes the shared owner directly. The
caller still opts in with `EnableFloatingPoint`. All 52 procedure bodies and
implementation data are unchanged. A complete Pi4 Neon/Vulkan float UI composition
has identical raw and PMF bytes before and after. Including both paths emits the
same probe as the shared path alone. Four AArch64 target interface probes compile;
this is not a new numeric, performance or GPU runtime measurement. Evidence:
`docs/evidence/neon-shared-float-math-20261026/`.

The explicit review-index architecture result falls from 261 to 254 refused keys
through ownership changes. The remaining refusal is not waived; the ratchet and
gate are unchanged.

## What the parser does not see

This is a text analysis. Read this list before trusting a number above.

- **It does not expand macros.** A `Macro` body is scanned as text, so a call
  written inside a macro is counted once where the macro is *defined*, not
  once per expansion. Downward calls hidden behind a macro parameter — a
  procedure name passed in as an argument — are invisible.
- **It does not evaluate `CompilerIf`.** Both branches are read as live code
  for rules 1 to 4, so a downward call inside a branch that no board compiles
  is still counted. Rule 5 is the one exception: it tracks conditional
  definitions and excludes them.
- **It does not follow indirect calls.** A procedure reached through a
  function pointer — which is how `FsSetRangeReader`, `ConSetRenderer` and
  the scheduler's `ApInstall` deliberately work — has no call site with a
  name in it, and no rule here sees it. That is the *right* answer for a
  seam, and a blind spot for anything that abuses one.
- **It does not parse expressions.** `@Name` and `@Name()` are both taken as
  a reference to `Name`, but an address arithmetic expression that computes a
  procedure address some other way is not.
- **It cannot tell a call from a same-named variable, array or structure
  field** in the handful of places where one shadows a procedure name. It
  only considers identifiers that a `Procedure` somewhere actually defines,
  which removes almost all of that risk and every language keyword with it.
- **It does not read assembly.** `ASM` / `EndASM` blocks are scanned as text
  for rule 3's register fingerprints only. A `bl` to a label is not a call
  site to this gate.
- **Strings and comments are blanked before every rule except the include
  rule**, which needs the quoted path. A procedure name mentioned in an error
  message is correctly ignored — `fat32.pbi`'s one apparent downward call is
  inside the text `"call FatSetRangeReader(@SdReadBlocks) first"`.
- **It reads the working tree, not `HEAD`.** That is deliberate: the gate is
  run before a commit, so it must see what is about to be committed. It takes
  the *file list* from `git ls-files`, so an untracked file is not scanned
  until it is added.

## The ratchet

Every finding is recorded per site in `tools/layering_ratchet.json` — plain
JSON, sorted keys, one line per site, so a diff of it is readable.

- A **new** site, or a recorded count that **rises**, fails the gate.
- A count that **falls** passes, and the gate tells you to refresh the file.

```sh
python tools/layering_check.py --update
```

`--update` may only shrink. If anything grew it refuses and prints what, and
the only way past it is to say why:

```sh
python tools/layering_check.py --update --allow-growth "<reason>"
```

That prints a banner, records the reason in the file, and is meant to be
noticed in review. Use it when a move is in progress and a count genuinely
has to rise for one commit; do not use it to get a commit through.

The baseline was recorded at `f676ba8` and widened against an export of
`HEAD`, because five lanes were live in the working tree that day and none of
them should fail a gate for work that was already in flight. That is what
`--also DIR` does, and it is why the gate may report a handful of recorded
sites as already gone.

## Committing in a shared tree

Several lanes work in this one checkout at once, and `git add` writes to the
index they all share. One bare `git commit` published eighteen files another
lane had staged. Commit from a **private index** instead — and run the whole
sequence **in one shell call**:

```sh
export GIT_INDEX_FILE="$(git rev-parse --git-dir)/index-<yourlane>"
rm -f "$GIT_INDEX_FILE"
git fetch
git read-tree HEAD
git add -- <the files that are entirely yours>
git diff --cached --stat          # BEFORE: your paths and nothing else
git commit -m "..."
git show --stat HEAD              # AFTER: your paths and nothing else
git push
unset GIT_INDEX_FILE
git reset -q -- <the paths you committed>   # refresh the shared index only
```

**`git read-tree HEAD` and `git commit` must be in the same call.** If
another lane pushes between them, the private index is built on a stale HEAD
and the commit silently **reverts** their files — that rolled two build
counters backwards before it was caught. Read the `--stat` before the commit
and again after it. If the after-stat names anything that is not yours,
`git reset --mixed HEAD~1` and redo it, **before** pushing.

For a **shared document** another lane has uncommitted edits in, do not `git
add` it at all: write a blob holding `HEAD`'s content plus your change and
install that blob directly, which leaves the working copy alone.

```sh
git show HEAD:docs/FILE.md > base && <apply your change to base>
blob=$(git hash-object -w base)
git update-index --cacheinfo 100644,$blob,docs/FILE.md
```

Never `git add -A` in this tree.

This is part of how the ratchet stays honest. A commit that sweeps in another
lane's half-finished work lands sites nobody measured, and the next person to
run the gate is told their own commit caused them.

## Related

- [ARCHITECTURE.md](ARCHITECTURE.md) — the layers themselves.
- [PORTABILITY.md](PORTABILITY.md) — what each extension means to the
  compiler.
- `Anvil/Hal/hal.pbi` — where a seam is declared, and the only place the gate
  reads one from.


## Shared Neon ownership

Renderer-neutral code has a shared implementation rather than a new seam
exemption. `Anvil/Graphics/neon_frontend.pbi` owns callback binding, logical
query routing and fallback counter declarations; `neon_colour.pbi` owns packed
colour arithmetic, and `neon_bitmap_font.pbi` owns fixed bitmap state/metrics.
The native renderer includes those implementations and retains hardware
lifecycle guards, GPU ownership, packet emission and physical-resource queries.
Compatibility wrappers delegate to the shared code.

The frontend's private unbound callback targets use `nfc_`, not the native
renderer's `neon_` prefix. Moving a module must not make it an owner of every
unrelated native private helper merely by sharing that prefix. Tests exercise
typed fallback behavior or provide fixture-owned callbacks; they do not rely
on those private target names. No wildcard Neon seam or ratchet growth was
introduced by these moves. Other unresolved findings still fail the gate.


## Neon lifecycle native-provider boundary

The shared lifecycle owner selects native or external dispatch and owns logical
frame/prepared-return state. Exactly one provider supplies six concrete typed
operations: read-only native ownership/hardware-frame flags, coordinate-cache
reset, native initialization/shutdown and native frame begin/end. Their exact
declarations and contracts are in `neon_lifecycle.pbi` and `hal.pbi`. Native
initialization/shutdown tails and frame methods retain their previous bodies;
shared policy reads no board-private ownership or coordinate-cache field.
The two flag bits describe the existing owner and hardware-frame guards, not a
claim that all asynchronous-job or GPU-fault recovery cases are implemented.

A controlled CPU provider exercises the shared policy without GPU code, including
the guard matrix, partial-family refusal, failed callback/rollback retention and
native handback. A separate Pi 4 proof uses the real Vulkan prepared lifecycle.
This narrow provider boundary is not a wildcard over native renderer helpers.
Other-target controlled-provider compilation does not implement a hardware driver.
The mandatory gate still fails at 270 new or grown keys; its algorithm and
ratchet are unchanged. Current proof and boot-status scope are recorded in
`docs/evidence/neon-lifecycle-shared-pi4-20261026/`.


## Shared test bodies and target entry ownership

The AArch64 Vulkan ABI probe has one shared body at
`Anvil/Graphics/Vulkan/Tests/vulkan_alignc_abi.pbi`; the Pi 3, Pi 4, Arduino Q
and Rock Pi 4C entries are in their respective board test folders. Their target
markers and twelve checks are preserved, and the four complete compiled
containers are unchanged. Shared CPU templates use `.pbi`; a composition that
imports the native Pi libraries belongs under `RaspberryPi4/Tests/`.

The ownership move removes six new/grown keys, leaving 264 still refused.
It does not change the gate, ratchet or seam vocabulary. Compiled preservation
and the absence of provenance findings for these moved files do not establish
full runtime acceptance or publication clearance. Exact scope and path mapping:
`docs/evidence/neon-shared-owner-placement-20261026/`.


Public `Neon_LineHeight` and `Neon_TextWidth` now share the frontend owner with
their optional callbacks. Bitmap fallback uses the existing public raw-height
and character-width getters; shared queries read no board-private fields.
The width body and remaining native procedures are preserved. The shared-only
four-target compile proof demonstrates linkage without a native renderer,
while runtime/GPU acceptance remains pending. See
`docs/evidence/neon-shared-text-metrics-20261026/`.


The Vulkan lifecycle binder now has one renderer-neutral implementation in
`Anvil/Graphics/Vulkan/neon_vk_lifecycle.pbi`. Its preceding Pi4 path remains
an implementation-free compatibility include; its board-extension finding
is deliberately still counted. The controlled binder proof links shared
frontend/lifecycle/colour/float owners and controlled native callbacks rather
than the full Pi renderer. Public float conversion calls remove one downward
and two private keys across two graphics proofs. Publication still refuses
261 keys; see `docs/evidence/neon-shared-graphics-proof-20261026/`.


## Vulkan board test ownership - 26 October 2026

The unchanged gate/ratchet now sees board-specific Vulkan tests in their actual
board trees. This move covers 61 exact sources: 58 Pi4 compositions/fixtures and
one absent-backend program each for Pi3, UnoQ and Rock. Shared portable state
fixtures remain in the shared tree. The scope comes from exact gate findings,
existing ratchet paths, named docs/tools and literal source/import dependencies;
no directory enumeration is used for this review.

Five representative programs compile to identical raw bytes across all four
targets. Fifty-six sources were byte-identical at relocation; five only needed
relative include paths changed to root paths. Two old spy fixtures were then
updated separately for the current native-capacity and mapped-bitmap contracts.
The stale fixture's failed compile and failed physical assertion are retained;
the corrected standalone spy returned zero on Pi4.

New/grown findings fall from 254 to 199, with downward includes removed and new board
extension findings falling from 51 to 12. Downward-call keys rise from 75 to 118 because moving
test stubs removes false shared owners and reveals unchanged production coupling.
This is a corrected ownership observation, not a new runtime dependency or a gate
exception. The remaining dependencies still need real ownership/seam work. No
gate, ratchet, protocol, private namespace or licensing rule was weakened.


## Pi4 runtime and shared lowering - 27 October 2026

The Pi4 Vulkan backend, shader-record emitter, texture transfers and optional
CSD producer/canvas bridge now have a board library owner. Typed IR lowering
remains in the shared tree as .pbi because it uses only the shared pure encoder.
The shared selection header validates a program-supplied implementation identity
instead of importing a board driver. Its actual Pi4 and software callers were
updated, and the portable software smoke now belongs to the shared Tests tree.

No gate or ratchet was changed. Current new/grown keys fall from 199 to 140
(62 downward calls, 30 protocol, 32 private, 9 board extensions, 7 duplicates),
with no downward include. The remaining findings are still refusals. Provenance
retains its existing classifications and reasons with only source paths moved;
98 omissions across 991 sources remain. Evidence and exact scope are recorded in
docs/evidence/vulkan-gpu-owner-20261027/.


## Shared Neon primitive dispatch - 27 October 2026

The twelve public drawing wrappers now belong to neon_frontend.pbi. A complete,
immutable typed native callback family is bound by the Pi4 library before Main;
the optional external family retains its independent install/clear lifecycle.
Native clip mirroring precedes external scissor notification. Native bodies keep
their exact geometry/state work after the optional external branch is removed.
This removes ten real downward-call keys, taking current new/grown findings from
140 to 130 (52 calls, 30 protocol, 32 private, 9 board extension, 7 duplicate).
No gate, ratchet or blanket Neon-name exception changed. Publication still
refuses those findings and the remaining provenance omissions. Physical dispatch,
native/Vulkan/native and current scene evidence is in
`docs/evidence/neon-primitive-dispatch-20261027/`.


## Shared renderer and adapter modules - 27 October 2026

Eight pure Neon renderer/adapter implementations now use shared .pbi owners.
The redundant lifecycle .pi4 include is removed. A remaining optional native
prepared-lifecycle installer moved unchanged out of core Chrome into an explicit
shared integration header; canonical Pi4 compositions preserve its availability.
The actual UnoQ core/file composition now compiles core Chrome with the absent
backend. No mock hardware, native fallback removal or gate exception was added.
The named audit expanded through literal paths recorded in the one task vault
note to 738 files and found/corrected two additional callers. All old references
within that scope are resolved; historical missing paths are retained in the
report. Current new/grown findings fall from130 to122:52 downward calls,30
protocol,32 private,one board extension and seven duplicate keys. Publication
still refuses those findings and98 provenance omissions. Evidence:
`docs/evidence/neon-shared-modules-20261027/`.


## Read-status names and native keyboard keys - 28 October 2026

The Wi-Fi protocol library's local/read-result parameter name `ok` collided
with the monitor procedure `Ok` in the gate's conservative name inventory.
Those 60 code tokens now use `readSucceeded`; inverse-token comparison leaves
all code identical, and comments/strings are preserved. No procedure call,
argument type/order, branch or wire operation changes. This removes one
downward-call key (24 reported sites), taking new/grown findings from 107 to
106 without changing the gate or ratchet. The other findings remain refusals.

The native renderer's unchanged legacy key constants now have one shared
header and an explicit normalized-native-key conversion. The actual Pi4
Vulkan text-field proof and UnoQ composition qualify that bridge. This is
separate from the shared editor command domain and introduces no board
dependency into the shared input owner. Evidence:
`docs/evidence/neon-canvas-keyboard-20261028/`.

## Intrinsic declarations and test recorders - 28 October 2026

Private-name resolution distinguishes compiler intrinsics from test recorders
that deliberately use the same spelling. The checker reads complete intrinsic
ASM declarations from the exact compiler registry for each of the four targets
and checks its target marker. A board production caller does not acquire a
private-library dependency merely because all procedure definitions of that
builtin are test doubles in that same board's Tests directory.

This correction is deliberately narrow. Ordinary private names, any production
procedure definition with the same name, definitions in another board, test
callers and shared callers retain the existing checks. Missing, incomplete or
mismatched registries grant no exception. Shared code still needs a declared
HAL seam. The checker does not scan directories or infer builtins from names.

The controls cover 36 cases across all four target registries, and the existing
architecture self-test remains passing. No runtime barrier, test recorder,
intrinsic instruction, seam or ratchet baseline was changed. Forum 1501 records
the false dependency between HDMI and the keyboard barrier recorders.
## Shared EDID fixture composition - 28 October 2026

The EDID dispatch fixture is a shared .pbi module with caller-supplied control
and input addresses. Test compositions own the parser include, entry point and
storage. The existing driver retains explicit Pi 3 targeting and addresses;
the returning proof compiles for Pi 4 and UnoQ. Physical Pi 4 execution passed
65 parser/dispatch checks; Pi 3 and UnoQ claims are compile-only. No interpreter
was loaded or run. The production parser is unchanged. Removing the shared-tree
board extension takes remaining architecture findings from 102 to 101, without
a ratchet waiver. Forum 1504 is resolved for fixture portability, not physical
EDID transport or hotplug. Installed Anvil 387 is unchanged.

## USB serial service boundary

`Anvil/Services/usb_serial.pbi` owns the shared serial API. A board installs
one synchronous `(operation, argument, count)` provider with `UsbSerialBind`
before consumers open a device. Bind zero to remove it only after stopping
existing consumers. This is a monitor-internal contract, not a payload ABI.
The Pi host composition supplies `RaspberryPi4/Board/usb_serial_service.pi4`,
which delegates to its existing USB host driver. Other compositions may
provide their own adapter without adding a board dependency to GNSS.

Kind zero means no current device; nonzero kinds are provider identifiers.
Kind text is a borrowed NUL-terminated provider string. Reads and writes
return counts or -1; null buffers and nonpositive lengths are refused before
dispatch. An unbound service reports unavailable, no device, failed open,
and failed I/O. The existing GNSS error mapping and baud-search order are
unchanged. GNSS and its command now call this service instead of UsbSer*.

Pi capture 145 executes 47 checks against the production service and adapter
with driver doubles. It covers initial binding, absence, all operations,
argument routing, read failure, refusal without dispatch, untouched buffer
tail, replacement and removal. The host oracle rejects 102 damaged reports.
It does not exercise a physical receiver or qualify its USB transfers.
The architecture gate has 55 remaining findings, down from 67; no exemptions
or ratchet limits changed. It remains a publication blocker.

## Wi-Fi maintenance service boundary

`Anvil/Services/wifi_maintenance.pbi` owns the shared maintenance dispatch used
by the prompt and payload network service. A composition binds one synchronous
provider before either starts, and replaces or removes it only with callers
stopped. Tick advances the existing driver maintenance step; CheckNow schedules
its health check. Neither promises a connected radio or successful recovery.
An unbound service does nothing, matching compositions without radio maintenance.

The Pi adapter binds after its existing Wi-Fi driver. Polling order, message
brackets, recovery cadence and driver work remain unchanged. There is no new
payload ABI slot or blanket exemption for Wi-Fi names. Physical Pi capture166
checks binding, replacement, removal, operation routing and the existing payload
network regression fixture. All 4096 report bytes match, including guards;
21 damaged reports are rejected. Radio calls in this CPU proof are counted
doubles, not a Wi-Fi interruption experiment. Architecture findings fall from
44 to 42; publication remains blocked by the remaining findings.

## Addresses of storage versus procedures

The downward-call and private-namespace checks use the same scoped reference
extraction. A bare address of an explicitly declared local, parameter or global
is storage, even when a procedure on another board has the same spelling.
Declarations are resolved per procedure, with global storage visible throughout
the file. Calls in declaration initializers remain checked, and a local name
does not exempt a procedure address in another scope. Explicit calls remain
visible. The self-test covers these cases alongside the existing planted
violations. No name-specific exemption or increased ratchet limit is needed.
