# The Anvil build number

`version` on the board prints `#ANVIL_BUILD`, and it exists so that a person
watching a board can tell one image from another without hashing anything.

## The ruling

2026-09-11: *"from now on if you build anvil the build number needs to be
increased"*, after three images went to a Pi 4 in one night all announcing
themselves as build 41 and nothing on the board could say which one was
running. Later the same day, on learning that the gate set compiles the whole
monitor about ten times per run from temporary copies and that none of those
builds moved the number: *"gate builds do count"* and *"I want real build
tracking, not estimated"*.

So: **every build of a board file raises that board file's number by exactly
one.** Not the builds that happen to be made one particular way - every one.

## Where the number lives

Two files, and nothing else in this repository has a build number:

| Target | File |
|---|---|
| pi4 | `RaspberryPi4/Board/board.pi4` |
| unoq | `ArduinoQ/Board/board.unoq` |

Each board file is its own project and counts its own builds. The shared core
in `Anvil/Core` carries no marker: a library is built into many projects, and a
number raised by all of them counts nothing. The compiler refuses a marker in
an included file by name (PMF-BLD-003).

The marked lines look like this, and the marker is an ordinary trailing
comment, so the language is unchanged and the source still compiles on a
toolchain that has never heard of one:

```
#ANVIL_BUILD = 57        ; pmf:build
#ANVIL_BUILD_DATE = 20260911   ; pmf:builddate
#ANVIL_BUILD_TIME = 213307     ; pmf:buildtime
```

`; pmf:build off` freezes the number - for a release, where the number is meant
to stand still. A frozen build is still recorded (see the ledger below); it is
the number that stops, not the evidence.

The full marker contract - what is and is not a marked line, and every refusal
it can produce - is the compiler's, written up in the header of
`BuildNumber.pbi` in the compiler tree. `tools/build_count.py` implements the
same contract against the same PMF-BLD codes, so a refusal from a gate and a
refusal from the IDE are the same refusal.

## The mechanism, and there is only one

`tools/build_count.py` owns the sentence "a board file was built". Every tool
in `tools/` that compiles calls it after a compile it has already proven
succeeded:

```python
build_count.record_build(source, target, image,
                         by="tools/<this tool>.py", compiler=pmfc)
```

It is handed the path that was compiled - the real board file, or a copy of it
in a temporary directory - and it

1. identifies which **real** board file in this repository that compile was a
   build of, and answers "not a board file" for a fixture, which is most of
   what the gates compile;
2. raises that file's `; pmf:build` number by exactly one and stamps the date
   and time siblings, byte for byte: only the digits of those three values are
   replaced, and all three land in one atomic write;
3. honours `off`;
4. appends one line to the ledger.

**Why not `pmfc --bump-build`.** The compiler's own bumper raises the marker in
**the file it was handed**. For `tools/build.py` that is the real board file,
so it worked; for a gate it is a copy in a temporary directory that is deleted
seconds later, so ten monitor builds a gate run were never counted. That is
what "not estimated" was about. Nothing in `tools/` passes `--bump-build` any
more - one mechanism, one lock, one ledger. Two bumpers would double-count an
ordinary build, still miss the gate builds, and take two different locks over
one file. The compiler's bumper is untouched and is still what the IDE's build
action uses; this repository simply does not ask for it.

**There is no way to build without counting.** `--no-bump` is gone. A build
made to verify something is still a build of the monitor, and the number moving
is how anyone can tell later that it happened.

**The refusals.** `PMF-BLD-nnn` are the compiler's codes for the marker
contract and mean here exactly what they mean there: `-001` a marker on
something that is not a whole-number constant, `-002` two markers of one kind,
`-005` the constant's ceiling, `-006` no marker at all, `-009` a word after the
marker that is neither `on` nor `off`. What this module asks for on top of that
contract - a named compiler - is Anvil's own requirement and carries
`ANVIL-BLD-001`. One code never means two things.

**A failed build never counts.** The call sites are after the compile and after
the check that it produced what it asked for.

**Two workers may run gates at once.** Every read-add-write of a board file and
every ledger append happens while holding `build/BUILDS.lock`, so two
concurrent builds count two: 56 to 57 to 58, never 56 to 57 twice.

**One compile is counted once.** Each call fingerprints the compile by the
artifact it produced - path, size, modification time in nanoseconds and sha256 -
and that fingerprint is in the ledger line. The same artifact offered twice is
one build. Two real builds that produce identical bytes are still two builds.

## The ledger

`build/BUILDS.log`, one line per recorded build:

```
2026-09-11T21:33:07Z target=pi4 build=57 stamp=20260911-213307 board=RaspberryPi4/Board/board.pi4 source=<compiled path> image=<artifact> sha256=<64 hex> pmfc=<64 hex> by=tools/build.py compile=<16 hex>
```

The leading timestamp is UTC so two workers' lines sort against each other;
`stamp` is the local date and time written into the board file, which is what
the board prints. A frozen build carries a trailing `frozen=yes`.

`pmfc=` is the sha256 of the compiler that produced the image, and a counted
build that does not name one is refused. The compiler is rebuilt on this bench
while gates are running - it was rebuilt in the middle of the first sweep this
mechanism ever ran - so "build 58 of board.pi4" is only half an identity; the
other half is which compiler emitted it, and that is not recoverable after the
fact. A gate stages a copy of `pmfc` beside this repository's board profiles,
and a copy hashes the same as the original, so what is recorded is the compiler
and not the path it was run from.

**It is gitignored, deliberately.** The durable, shareable count is the marker
line in the board file, and that **is** committed: it travels with the source,
shows up in a diff, and is what the image announces. The ledger is the local
evidence behind it - what this machine built, out of which temporary directory,
and what the bytes hashed to. Tracked, it would conflict on every concurrent
gate run between two workers and would carry one machine's temporary paths into
everybody else's clone. It sits in `build/` rather than `_work/` because the
artifacts these lines hash are already in `build/`, so the evidence sits beside
what it is evidence of.

To read the current state:

```sh
python tools/build_count.py
```

## Who counts

| Tool | Builds |
|---|---|
| `tools/build.py` | the image that gets flashed, pi4 and unoq |
| `tools/memcmd_width_emitted_check.py` | both board files, end to end, per run |
| `tools/payload_lifecycle_check.py` | `board.pi4`, for its emitted A64 |
| `tools/dsi_diag_read_safety_check.py` | `board.pi4`, for its emitted A64 |
| `tools/build_count_check.py` | one real `tools/build.py pi4`, unless `--fast` |

Other gates compile fixtures - a few lifted procedures around a probe - and
call `record_build` anyway, which answers "not a board file" and moves nothing.
That is on purpose: the decision about what is a build of the monitor belongs
to one module, not to each gate's reading of its own fixture, so the day a gate
starts compiling a board file the count follows it with nobody having to
remember.

## The gate

`tools/build_count_check.py` proves the mechanism on temporary copies: raising
by exactly one and by nothing else in the file, the date and time stamp, the
ledger line and its image hash, every caller's own call shape, `off`, each
malformed marker refused by its own code with the file left alone, six
concurrent builds counting six, the lock actually blocking a second process,
and one compile counted once. Six mutations of `build_count.py` - drop the
lock, drop the stamp, bump by two, forget that a compile was already counted,
bump a frozen marker, ignore a malformed one - must each be rejected by the
check that owns that property.

It also proves the wiring: every tool that runs the compiler and holds a board
file as a path calls `record_build` after its own success guard, nothing asks
for `--bump-build`, and nothing offers `--no-bump`.

```sh
PMFC=<path-to-pmfc> python tools/build_count_check.py        # with the real compile
python tools/build_count_check.py --fast                     # mechanism and wiring only
```
