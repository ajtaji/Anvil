# Neon/Vulkan compatibility evidence contract

This document freezes the independent evidence required for the V3D/Neon
compatibility claim. It is an evidence contract, not an implementation claim.
A desk result may establish that a fixture and its oracle are internally
consistent; it does not become a Pi 4 result without a fresh board manifest,
report and capture from the same source artifact.

## Paired runs and trace identity

Every compatibility fixture is run twice from the same source scene and input
sequence: once with direct native Neon and once with the Vulkan renderer. The
pair records the source revision, compiler identity, fixture name and version,
surface provider, logical and physical extents, pitch, format, rotation,
draw-buffer identity, scan-buffer identity and font/atlas generation. Native
and Vulkan traces use the same operation vocabulary and sequence numbers.

The trace is machine-readable. Each frame records begin/end status, every
primitive accepted or refused, normalized clip and viewport state, font and
atlas generation, public counters, timings, job transitions, present intent,
present consumption and final error state. A refusal records the operation,
documented error, state/counter deltas and whether the following valid frame
completed. Backend-private fields may be additional evidence but cannot replace
the public Neon units.

The frozen scene set includes empty frames; boxes with negative, empty,
off-surface and boundary extents; alpha-zero and overlapping boxes; all 95
ASCII glyphs in every supported font slot and scale; flat and textured text;
scissor nesting and empty intersections; convex fans, closed outlines, normal,
diagonal and zero-length lines; mixed ordering of every primitive family;
menus, lists, scrolling, text input, touch-keyboard composition and the
production widget scene. It also includes the recorded stress workload of
3,505 boxes and 1,434 glyphs. The workload must exercise separate draw-record
and vertex capacities. The currently frozen atomic refusal is specifically
Neon_Box's flat vertex-capacity and draw-record-capacity preflights; it is not a universal native
transaction guarantee.

## Pixel oracle

Successful paired frames compare the complete canonical render target after
logical-to-physical rotation is applied. The comparison has zero tolerance:
every byte must match. No per-channel epsilon, perceptual metric or cropped
comparison is permitted. The oracle also checks poisoned and guard regions,
including regions outside the target and outside each clipped primitive.

The canonical image record includes width, height, pitch, format, rotation,
byte order, image hash and first mismatch offset/count. Native and Vulkan
captures are only comparable when these fields match. A one-channel rounding,
edge-ownership, blend, endpoint or rotation difference is a failure to fix in
the renderer or lowering algorithm.

## Required counters and manifest

Each successful frame manifest must include `Neon_Draws`, `Neon_Boxes`,
`Neon_Glyphs`, `Neon_Runs`, `Neon_Verts`, `Neon_Clipped`, all textured
counter equivalents, `Neon_Error`, readiness, capacity/refusal state, public
timings, V3D bin/render/TFU/DMA transitions, present sequence and consumed
sequence. It records resource generations, live/high-water counts, retained
references, cache ranges, fault/OOM/MMU fields, screenshot hash and final
prompt/deadman state for board runs.

For an equivalent ordinary frame, bin, render and presentation transitions
advance exactly once. TFU advances only when the atlas generation changes.
Counters retain their documented units. A successful frame cannot move a
capacity, refusal, fallback or fault counter. Neon_Box's flat
vertex-capacity and draw-record-capacity preflight refusals cannot partially
advance geometry or box/draw/vertex counters. Capture 131 reproduced the
record-capacity defect: six vertices, one box and 96 bytes changed despite
refusal. The corrected native box checks record capacity before those writes.
Capture 133 exercises the public Neon_Box API with a guarded vertex buffer,
checks unchanged public counters, and verifies empty boxes still succeed at
full record capacity. All 267 fixture checks and the following Vulkan caret
pixel checks pass; 580 damaged buffers are rejected by the host oracle.
The corrected native code was linked into the returning payload on Anvil 397;
the installed 397 monitor has not yet been rebuilt with this box fix.
Evidence: `evidence/neon-native-box133-20261029`.

Flat and textured text now use a count-only pass through the same glyph and
clipping walk before emitting geometry. Vertex and record capacity are checked
before writes; textured text also checks them before lazy atlas construction.
Capture 135 qualifies the refusal paths through public Neon_Text/Neon_TextTex:
467 total checks include full records, room for only one of three glyphs,
guarded geometry, unchanged counters/atlas state and empty/transparent no-ops.
The following Vulkan caret crops still match. The oracle rejects 980 damaged
buffers. Capture 134 returned successfully but its host report was rejected
because the fixture accidentally invoked the new tests twice; that duplicate
call was removed before capture 135. Evidence is preserved for both runs in
`evidence/neon-native-text135-20261029`.

Capture 136 qualifies successful native flat and textured text with a separate
multi-row bitmap oracle: eight frames cover ordinary draws, exact vertex
capacity, exact draw-record capacity and clipping. All 65,536 captured pixel
bytes match independently constructed glyph patterns, and all 534 report
checks pass. The oracle rejects 1,114 damaged report/caret buffers plus 20
damaged native pixel buffers. This is a bounded rendering qualification,
not the full-surface compatibility/performance contract above. Evidence:
`evidence/neon-native-text136-20261029`. Performance after the two-pass change
still requires measurement. The installed 397 monitor is unchanged. Capacity refusal
checks do not establish transactional behavior for later control-list or
hardware failures, nor complete native/Vulkan compatibility.


## Hostile mutation requirement

Every oracle gate must run deliberate mutations and require them to fail. The
minimum mutation set is:

- wrong colour packing, alpha equation or source-over order;
- swapped draw order and a missing draw;
- inclusive instead of half-open rectangle or clip edges, empty/negative clip
  normalization, and stale scissor snapshots;
- 0/90/180/270 rotation mapping, odd extents, pitch and draw/scan buffer
  identity;
- line endpoint movement, diagonal ownership and zero-length handling;
- fan winding, shared-edge ownership and outline closure;
- wrong glyph rejection, advance, tint, font slot, scale or atlas UV;
- atlas-generation replacement using a stale descriptor or image;
- stale, duplicated or lost-target present generation and double consumption;
- Neon_Box flat vertex and draw-record capacity refusals, plus the open
  flat/textured text capacity refusal and pending successful-draw qualification;
- processor pixel loop, direct native control-list shortcut or DMA rendering
  fallback hidden behind a successful Vulkan draw;
- changed public counter units, missing fault/reset state, or a second bin,
  render or present transition.

A green gate without red results for its targeted mutation is not evidence.
Mutation anchors and expected failure fields are versioned with the fixture so
that a silently weakened checker cannot pass after source drift.

## Recovery, repetition and performance evidence

The manifest format also covers init, rebind, retarget, resize, font-change,
rotation, target-loss, submit/wait/present fault, shutdown and reinitialization
sequences. Every injected lifecycle failure must leave no stale present and
permit the next valid frame. Resource and generation counts must return to
their starting values after teardown.

Performance evidence pairs native and Vulkan on the same scene and surface
after warm-up. It records at least 600 frames in three trials, median and p99
frame time, job/present counts, refusal/fallback/fault counts and resource
high-water marks. The compatibility regression limits are median no worse than
1.10x native and p99 no worse than 1.20x native; where native meets 16.67 ms,
Vulkan p99 must also meet it. Endurance evidence records 10,000 persistent
presented frames and the final resource, fault, guard and prompt state.

## Evidence boundary

Screenshots are supporting evidence. They never replace the complete pixel
oracle, trace, counters and manifest. Desk-only model output, emitted geometry,
one attractive screenshot, or an earlier binary with different bytes cannot be
borrowed for a later source revision. Native remains the reference backend
until the complete paired evidence set passes.


## Cached workload and installed build 398

Captures 137/138 measure 3,505 boxes and 1,434 glyphs per native frame,
with one warm-up and three samples for each text path. Capture 137 used the
loader's uncached entry state, so its 1,216.29 ms flat / 616.69 ms textured
median totals are not resident-renderer performance. Capture 138 builds
payload-owned page tables and directly records SCTLR M/C/I bits as
0 -> 0x1005 -> 0 around the measurement, with the GPU surface/window kept
noncacheable. Median cached totals are 23.42 ms flat and 13.80 ms textured;
text construction is 10.09 ms and 0.89 ms respectively. Box construction
is about 9.25 ms. Counts, timing sums and successful GPU completion are
checked. These are bounded native measurements, not paired Vulkan timings,
workload pixel parity, p99, sustained performance or endurance evidence.

All 535 report checks, prior native/caret pixel oracles and post-run health
pass. The report/caret checker rejects 1,116 damaged buffers; the workload
checker rejects 137, including changed cache-state and counter-frequency
fields. Source inspection confirms the loader disables caches; the older
version-1 workload report did not record SCTLR itself. The initial build
attempt used an unsupported modulo spelling, was corrected before any upload,
and produced no executable.

Build 398 contains the grouped native box/text capacity changes. Its boot
file and running hash were verified after a full 397 rollback was saved as
`1:/B397V398.IMG`. The 90-frame resident composed scene also passes its
state and raster checks after the update. Warm presentation is 30.03 FPS, but the first frame takes 53.3 ms and the whole-run rate is 29.83 FPS; the all-frame 30 FPS target remains unmet. Full engine completion and source
publication remain open; the architecture gate has 67 findings. Evidence:
`evidence/neon-native-workload398-20261029`.


## CRT preparation before the first canvas frame, build 399

The shared canvas CRT prepare operation no longer requires hasFrame. It only
builds a pipeline and does not sample image contents, so an owned idle canvas
with current target and texture generations may prepare before rendering.
Retro drawing and retro pointer mapping still require a completed source
frame. The ownership, generation and lifecycle checks remain in both paths.
Capture 140 checks fresh preparation, idempotence, unchanged hasFrame and
pipeline identity, unrendered draw/map refusal, unchanged map outputs and
stale/closed refusal. All 551 checks and existing native/Vulkan pixel checks
pass; the checker rejects 1,148 damaged buffers.

Build 399 is installed with verified 398 rollback, boot-file and running hashes.
The composed scene prepares its final pipeline during setup and reports that
time separately; compilation work is moved, not eliminated. Setup preparation
took 6.224 ms. First-frame unbind/prepare took 0.029 ms (previously 6.271 ms),
and maximum frame time is 54.827 ms (previously 53.282 ms). Warm rate is 30.029 FPS;
whole-run rate is 29.812 FPS. The all-frame 30 FPS target status is False.
The 90-frame state and raster checks pass. Physical interaction and broader
performance/endurance remain unqualified. Evidence:
`evidence/neon-retro-early399-20261029`.


## Contiguous display DMA, build 400

The DmaCopy2D library entry point now selects the existing checked linear
copy after rectangular validation when both pitches equal the row width.
Padded rows retain the rectangular transfer. Bounds, reachability, overlap,
cache ownership and display-latch confirmation are preserved. This applies
to all callers of this library, including native display and Vulkan callers.
The BCM2712 DMA40 implementation already coalesced contiguous rectangles;
no Pi 5 speed improvement is claimed. Physical measurements here are Pi 4.

Capture 142 compared the original rectangular and linear paths on a
4,096,000-byte frame: three warm samples after one warm-up gave medians
7.990 and 6.133 ms. Capture 143 tested the changed DmaCopy2D: 6.136 ms.
Each method verified all 1,024,000 destination words and outside guards.
Three padded cases (both pitches, only destination, only source) preserve
row contents and untouched padding; zero-width and zero-row calls refuse.
Execution records SCTLR M/C/I 0 -> 0x1005 -> 0, with buffers non-cacheable.
The host report checker rejects 28 damaged reports. These are DMA results,
not an application performance qualification.

Build 400 is installed with verified build 399 rollback B399V400.IMG and
matching boot-file/running hashes. Capture 144 reuses the byte-identical
resident application: 65 state checks, 169 raster probes and 90 frames pass.
The recorded mean display DMA decreases from 7.994 to 6.145 ms per scene
frame; publication wait increases from 2.251 to 4.110 ms. Warm rate remains
30.029 FPS. First/max frame is 52.635 ms versus 54.827 ms in build 399, and the
all-frame 30 FPS target remains false. No constant startup gain is claimed
from a single refresh phase. The source waits for confirmed HVS ownership;
it does not add an arbitrary delay that can safely be removed.

Network, cores, fonts and Vulkan return healthy, with no display timeout;
the watchdog is off. No physical input events were exercised. Architecture
still has 67 findings and blocks source publication; provenance passes
1,411 checks. Full engine performance, input and endurance remain open.
Evidence: docs/evidence/neon-dma-linear400-20261029.


## Publication prerequisite: USB serial boundary, build 401

The shared GNSS service and command no longer directly depend on the Pi USB
serial driver. A shared transport service owns provider binding; the board
adapter supplies the existing driver. This resolves 12 architecture findings
without changing the gate or ratchet. The remaining count is 55, so source
publication remains blocked. Provenance passes 1,411 checks.

Capture 145 passes 47 service/adapter routing and refusal checks with driver
doubles; 102 damaged reports are rejected. This is not a physical receiver
test. Build 401 compiles the production GNSS integration and is installed
with verified 400 rollback and matching running hash. Network, cores, fonts
and Vulkan return healthy. No unchanged graphics scene was replayed for this
transport-only change. The prior build 400 scene remains its rendering
evidence, not a new build 401 scene result. Full engine and wider Vulkan
completion remain open. Evidence: docs/evidence/neon-usb-service401-20261029.


## Publication prerequisite: console boundaries, build 402

Three more architecture findings are resolved (55 to 52). The message log
uses the existing HwStorageUp contract; the Pi implementation returns the
prior StorageUp result unchanged. Both HTTPS failure-print sites use the
public str_print_at interface with the same null guard previously provided
by the TLS client's private helper. Finally, the HAL now documents HwPet,
the existing backend of ABI slot 6, supported by the Pi 4 feed and the Pi 3
and Arduino Q no-op implementations. This last item corrects a missing
contract declaration; it is not a new watchdog implementation or ABI slot.
The gate algorithm and ratchet limits are unchanged.

Build 402 is installed with a verified 401 rollback and matching live hash.
The actual HTTPS command with port zero returns its original error before
any DNS, TCP or TLS work. Network console, cores and Vulkan remain healthy.
No TLS handshake, late connection failure, null-detail runtime case or
forced message-log write is claimed tested. These small substitutions were
checked against the original helper/wrapper bodies and the monitor build;
unchanged graphics tests were not replayed. Provenance passes 1,411 checks.
The remaining 52 architecture findings still block source publication; full
Neon and wider Anvil Vulkan completion remain open.
Evidence: docs/evidence/neon-console-boundaries402-20261029.


## Publication prerequisite: GNSS stream ownership, build 403

The GNSS raw-view command no longer calls the private source reader and
byte decoder. Public GnssRead reads a bounded chunk, decodes each byte once,
and returns the same bytes for display. Normal GnssPump uses that path too;
its fix-event return and baud-search scheduling stay in the polling layer.
Null/nonpositive buffers, read failures and counts above capacity are refused
without decoding. This cannot undo an out-of-bounds write by a broken provider;
providers must still honor the destination capacity. The service remains
single-caller and is not a new payload ABI operation.

Capture 147 exercises the actual framer and decoder on the Pi, using a
deterministic provider delivering a known 67-byte GGA sentence in seven-byte
chunks. Direct reads and normal polling produce identical 64-byte fix records,
checked independently for position, altitude, satellites and time. All 33
checks pass, including absent/idle/error/invalid/oversized-read handling and
zero network calls. The checker rejects 107 damaged reports. The repository
builder tools/build_gnss_read_probe.py reproduces the exact executed PMF.

The first fixture compile omitted the UART dependency required by HAL and
did not run. Capture 146 returned normally, but the independent checker
refused its 72-byte length: the fixture had included linker padding by
subtracting data labels. Capture 147 uses the explicit 67-byte wire length;
the failed evidence is retained, and the checker was not relaxed.

Build 403 is installed with verified 402 rollback and matching live image
hash. Network, cores, fonts and Vulkan return healthy. No physical receiver,
USB transfer, network stream or unchanged graphics scene is claimed tested.
Architecture findings decrease from 52 to 50, still blocking publication;
provenance passes 1,411 checks. Full engine and wider Vulkan work remain open.
Evidence: docs/evidence/neon-gnss-read403-20261029.


## Publication prerequisite: shared CRC ownership, 29 October

Six RockPi eMMC probes now use the shared Crc32 owner instead of independent
bitwise implementations. Initial accumulator, final inversion and 512-byte
sector length are unchanged. Nine sector arrays also used a 511-element
count for 512-byte transfers; the candidate corrects them to 512 elements.
The RK3399 clock and format payloads compile; no RockPi storage operation ran.
The buffer defect remains open for hardware validation and publication in
forum topic 1525. It is not a new observed board-corruption report.

Pi capture 148 exercises the actual shared CRC library in RAM: twelve zlib
oracle checks cover empty input, four sector patterns, split ranges, the
standard check string and a non-default accumulator seed. Guard bytes remain
unchanged. The checker rejects 258 damaged reports. The first fixture compile
correctly refused a too-small test array; the corrected fixture is the only
one executed. Anvil 403 returned healthy with the watchdog off. No monitor
update or unchanged graphics replay was required. Architecture findings are
44, still blocking publication; provenance passes 1,411 checks. These results
do not establish full engine input, performance, endurance or wider Vulkan
completion. Evidence: docs/evidence/neon-shared-crc-20261029.


## Paired full-target box baseline, capture 149

The same public Neon_Box loop draws 3,505 opaque gray boxes with a black
clear through native Neon and the Vulkan prepared lifecycle. Both run with
SCTLR M/C/I = 0x1005 and noncacheable GPU surfaces. Each path has one warm-up
and three samples. The complete 800x1280, 3200-byte-pitch targets match an
independent pixel oracle: 8,192,000 bytes, zero differences. This grayscale
scene does not establish color-channel packing, alpha, font or widget parity.
The report verifies box counts, errors and Vulkan completion consumption;
it is not the complete trace/counter/guard contract above.

Warm median total is 13.122 ms native versus 152.719 ms Vulkan (11.64x).
Typical construction/end split is 10.09/3.03 ms native and 35.19/117.53 ms
Vulkan. End includes CPU validation, shader-record setup, cache maintenance,
control-list construction and GPU execution; it must not be labeled GPU-only.
This is not sustained performance acceptance. Backend phase profiling is the
next step before choosing an optimization. No production renderer was changed.

The returning RAM payload completed in 6.6 seconds on unchanged Anvil 403.
The original 8 KB-chunk host reader was terminated at its five-minute bound;
the existing RAM images were read with 256 KB chunks in 21.4 seconds, without
a second payload execution. Post-run cores, fonts, active Vulkan, zero faults
and watchdog-off were verified. The checker rejects 28 meaningful corruptions;
a first mutation wrongly expected a one-tick timing change to fail, and that
invalid test was replaced with zero duration without relaxing the checker.
Forum topic 1483, post 4209 records the result. Architecture remains 44 findings,
source publication blocked; provenance passes 1,411 checks. Full engine,
physical input, performance/endurance and wider Vulkan remain incomplete.
Evidence: docs/evidence/neon-paired-boxes149-20261029.


## Vulkan cache-span reduction, captures 150–152

The same paired workload now records the existing backend phase timestamps.
Warm baseline medians in microseconds are validation 4,488; private-slot
preparation and range collection 40,175; cache sorting/maintenance 42,603;
control-list emission 4,105; GPU kick/wait 3,012. Frame end also contains work
outside these intervals. GPU execution is not the dominant measured cost.

The candidate collector merges only touching/overlapping incoming spans and
uses a 64-entry physical-span lookup. A hit verifies its index against the
current list count and compares both endpoints in that list. Stale entries
and collisions can only miss; no ownership or validation decision is cached.
The arbitrary-order sort, exact physical union and final barrier remain.
The optimization applies to backend draw lists without scene-specific rules.

Input intervals fall from 24,535 to 14,460 with the final union unchanged
at 14,023 spans. Cache phase falls to 24,683 us and total Vulkan frame median
from 153,334 to 134,913 us, about 12%. Preparation remains about 40,278 us.
All 8,192,000 target bytes still match the independent oracle. These three
warm samples are not the required sustained performance trials, and the
candidate remains far slower than native Neon.

Capture 152 executes the exact collector body in a RAM-only fixture, testing
115 range admissions and comparing the resulting physical union independently.
It covers overlaps, duplicates, upper-address boundaries, invalid inputs,
stale lookup indices after reset and a constructed full-capacity state.
The repository builder reproduces the executed PMF byte for byte. Host
mutations reject 141 damaged phase/collector reports. All three payloads
return normally and post-run core/font/Vulkan/deadman checks pass. The
candidate is linked into returning payloads; installed Anvil stays at 403.
Architecture remains 44 findings, publication blocked; provenance passes
1,411 checks. Forum topic 1483 post 4210 records the remaining throughput gap.
Evidence: docs/evidence/neon-cache-interval151-20261029.


## Attribute packing and preparation detail, captures 153–155

V3dAttrRecord uses four aligned 32-bit stores for its 16-byte record instead
of sixteen byte stores. Begin requires a 32-byte aligned base; the 36-byte
header and 16-byte attribute stride preserve word alignment. Low-bit packing,
default fields, zero divisor and refusal behavior remain unchanged.
Capture 153 verifies every byte of ten guarded cases in a 16 KB report,
including maximum count, wide/negative inputs and invalid indices/counts/
alignment. The repository builder reproduces the executed binary exactly;
135 corrupted reports are rejected.

Capture 154 preserves exact paired image equality. Preparation measures
39.26 ms and total Vulkan median 134.11 ms, versus the preceding 40.28 and
134.91 ms. This small difference is not sustained performance qualification.
Capture 155 adds clocks around allocation and private slot construction:
packet sizing/allocation 2.17 ms, slot construction 33.35 ms, cache-span
collection 3.61 ms. Eight subphase corruptions are rejected. All three
payloads return normally and pass post-run health checks. The explanatory
comment for the two new clocks was added after execution; code is unchanged.
The next target is repeated private-record construction, with validation and
per-draw resource ownership preserved. Installed Anvil remains 403; the
44 architecture findings and broader completion requirements remain open.
Forum: topic 1483, post 4211. Evidence:
docs/evidence/neon-attribute-words155-20261029.
