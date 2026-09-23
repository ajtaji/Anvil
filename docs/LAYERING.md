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
| `generic-timer-read` — `mrs …, cntpct_el0` / `cntfrq_el0` | `RaspberryPi4/Lib/timer.pi4` | 47 in 25 files |
| `aarch64-mmu-attributes` — MAIR `$FF440C0400`, `$401`, `$70D`, `$711` | `RaspberryPi4/Lib/mmu.pi4` | 5 |

`crc.pbi` takes `#CRC_POLY` from the includer on purpose and says so in its
header, so a line that defines exactly `#CRC_POLY` is exempt. Any other
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

### 5. One definition per name

Two files that can be linked into the same image may not both define a name.
Two board folders cannot share an image, so the same console on three boards
is not a collision. Neither is a stub inside a `Tests/` or `Examples/`
composition, which is its own program. Neither is a pair of definitions in
exclusive `CompilerIf` branches — the gate tracks compiler-conditional
definitions and does not count them against each other.

45 names remain, and they fall into three classes:

- **28 `avkBackend*`** — the Vulkan link-time backend seam, three
  implementations, one chosen per image. This is the model seam and it is
  working as designed.
- **13 `NetConsole*`, `NetDhcpTick` and `HwDir*`** — a shared implementation
  and the board stub sets that replace it. Legal alternatives; they are here
  because the seam is not fully named in `hal.pbi` yet.
- **4 genuine duplicates inside one board**: `Pi3ReadBe32`, `Pi3Park`,
  `Pi3BootMemory` and `Pi3BootMaxCoreClock`, each written twice in
  `RaspberryPi3/Board/`. These are real and should go.

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
