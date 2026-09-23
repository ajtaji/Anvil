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
Neon_Box's flat vertex-capacity preflight; it is not a universal native
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
vertex-capacity preflight refusal cannot partially advance geometry or its
box/draw/vertex counters. Native record overflow can currently leave prior
geometry and counters advanced (`neon.pi4:3069-3072` before
`neon_Draw`'s record check at `neon.pi4:2988`); flat text can leave partial
geometry and run/glyph counters (`neon.pi4:3809-3813`); and textured text can
leave prior textured vertices/glyph counters before submitting a partial run
(`neon.pi4:4458-4489`, with record refusal at `neon.pi4:4347-4356`). These
are an open production compatibility blocker for any universal transactional
refusal claim.

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
- Neon_Box flat vertex-capacity refusal, plus the currently open native
  record/flat-text/textured-text partial-overflow blocker;
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
