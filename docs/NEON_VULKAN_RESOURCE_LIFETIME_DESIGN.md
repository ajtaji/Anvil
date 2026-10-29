---
title: Neon Vulkan resource lifetime and presentation design
date: 2026-09-17
status: design contract
---

# Purpose

This note freezes the resource and display contract for the Vulkan renderer
that must accept the existing Pi 4 Neon workload. It describes ownership and
transaction boundaries; it does not claim that the implementation is present
or that Pi 4 HDMI/DSI presentation is already wired to Vulkan.

The native renderer remains the behavioral authority. Vulkan resources may be
laid out differently, but successful calls, refusal points, counters, target
geometry, atlas selection, and presentation state must retain the public Neon
meaning.

# Capacity and preflight

The adapter keeps separate limits for each public resource family:

| Resource family | Native-compatible limit |
| --- | ---: |
| Flat draw records | 4,096 |
| Flat vertices | 262,144 |
| Textured draw records | 2,048 |
| Textured vertices | 98,304 |
| Path points | The declared native path boundary |

The Vulkan vertex buffer and draw-record storage may be split into multiple
internal allocations, but public capacity is measured in the units above.
One shared quad limit is insufficient because a frame can fit one resource
dimension while exhausting another.

Every primitive is preflighted before it changes a cursor, writes vertices,
records a command, increments a public counter, or changes clip state. Text
preflights the complete string after applying the native character rejection,
clip, and advance rules. Fans, outlines, and line lists preflight their whole
lowered shape. A frame-level preflight is required where the caller declares a
bounded batch or where resource replacement could otherwise leave a partial
frame. A refusal leaves the public state and already recorded sequence intact.

The Vulkan object tables reserve 41 image slots, 37 image-view slots,
21 descriptor-set slots, 20 framebuffer slots and 50 memory-allocation slots. The added rows
reserve table room for sixteen sprite resources, one replacement generation,
one transient staging allocation and sixteen offscreen attachments above the
prior budgets of 8 images, 4 views, 4 sets and 16 allocations. The Pi 4 heap remains the byte window
supplied to `AnvilVkV3dWindow`; the table increase does not enlarge it.
Before a sprite transaction, the caller must query each
image's `vkGetImageMemoryRequirements`, include staging and existing resident
allocations, compare the required bytes with the reported heap size, and
still treat each allocation result as authoritative because alignment and
fragmentation can refuse a fit. `NeonVkChromeImageSpriteReplace` and
`NeonVkChromeImageSpriteDraw` now provide one separately allocated sampled
image beside the shared atlas. Replacement keeps the resident handles until
upload, view creation and descriptor writes succeed. A Pi 4 returning proof
checks a refused oversized replacement, resident pixels, two successful small
replacements and descriptor reuse; see
`docs/evidence/neon-separate-sprite-pi4-20261002/`. All sixteen sprite rows now have public registry operations; sixteen small
retained offscreen targets pass on Pi4. Actual heap admission remains required.

A bounded first separate-image path now lives in `neon_vk_chrome.pbi`.
`NeonVkChromeImageSpriteReplace` copies one RGBA8 source into a separately
allocated optimal-tiled image through `vkCmdCopyBufferToImage`, then publishes
its view and descriptor after the upload completes. The prior image remains
resident until that publication; a capacity refusal releases only candidate
objects. `NeonVkChromeImageSpriteDraw` binds the image's descriptor for its
draw, and atlas draws bind the atlas descriptor for theirs. Replace and clear
require a quiescent frame and consumed present intent. The public registry has sixteen separately allocated sprite slots. A canvas
retains one such slot plus its distinct color attachment. These row capacities
do not promise that sixteen maximum-size resources fit in the device heap.

# Atlas generations

The CPU atlas is a borrowed view owned by Neon. A Vulkan atlas resource owns
its image, memory, image view, sampler binding, and descriptor generation.
The resource records the source atlas dimensions, byte extent, font identity,
and raster generation observed when it was uploaded. Font use or setup that
invalidates the native raster makes the current Vulkan generation stale.

Replacement is transactional:

1. Ensure the current native raster and capture its generation and dimensions.
2. Create and upload a replacement image through the Vulkan transfer path.
3. Create the replacement view and descriptor state and validate all owners.
4. Publish the new generation only after upload completion and descriptor
   readiness succeed.
5. Retire the old image, view, memory, staging resources, and descriptor only
   after every submission that retained the old generation has completed.

If any step fails, the old generation remains active and drawable. The new
generation is discarded as one transaction. A successful frame records which
atlas generation it sampled so recovery and diagnostics can reject stale
present or resource references.

# Target generations and rebind

The render target record contains the display provider, target base or Vulkan
attachment identity, logical width and height, physical width and height,
pitch, format, rotation, mapped byte span, and a monotonically advancing
target generation. Invariant resources such as device, queue, command pool,
pipeline layout, sampler, and capacity-sized buffers survive a target change
when their compatibility requirements remain valid.

Rebind and retarget are failure-atomic. The implementation validates the new
surface, declared capacity, pitch, rotation, mapped span, attachment format,
and framebuffer extent before publishing anything. It then creates or adopts
the size-dependent attachment and framebuffer, updates dynamic viewport state,
and records the new target generation. Only after all steps succeed does it
swap the active target record and retire the previous size-dependent objects.
On failure, the previous target and generation remain active and no new frame
may reference a partially published target.

Rotation follows the existing screen geometry owner for 0, 90, 180, and 270
degrees. Vulkan logical coordinates are converted once at the vertex/scissor
boundary; the display owner remains responsible for scanout geometry and any
DSI transpose. Odd extents, partial tiles, double-buffer spans, and single-
buffer targets are valid within the declared capacity.

# Present record and WSI seam

The current one-bit present flag is replaced by a generation-tagged record.
The record contains:

- target/provider identity and provider generation;
- target generation and completed Vulkan image or attachment identity;
- logical and physical dimensions, pitch, format, and rotation;
- source draw buffer and destination scan buffer identity;
- frame sequence, atlas generation, and completion status.

The record is published only after the render submission has completed. It is
consumed exactly once by the display owner. Consumption validates provider,
target, image, and generation; stale, lost, retired, or out-of-date records
are rejected without presenting an earlier frame. The completed image remains
retained until consumption or explicit rollback.

`Anvil/Graphics/Vulkan/vk_wsi.pbi` is the state-machine authority for provider,
surface, swapchain/image ownership, resize epochs, loss, retirement, and
generation-tagged present transactions. It may be extended with the metadata
needed by the Neon seam, but it must remain target-neutral and must not call
HDMI, DSI, DMA, or CPU display routines.

The Pi display boundary belongs to `RaspberryPi4/Board/screen_source.pi4`.
It preserves the existing rules: HDMI and non-sideways DSI may scan the draw
surface directly; sideways DSI transposes from the draw buffer to the scan
buffer; DMA is preferred and the established CPU copy remains the correctness
fallback. Banner, cursor, and touch-keyboard preservation remain display-owner
operations around a completed frame. Vulkan publishes the completed image and
geometry; it does not become the display owner or issue a disguised swapchain
present.

# Recovery and teardown invariants

All resource transitions are owner- and generation-checked. A bounded submit
or wait failure leaves no pending present record, no published stale target,
and no leaked staging allocation. A device or target loss invalidates the
affected generation, rejects future use of its handles, and allows a fresh
target/resource transaction to recover without reusing stale attachments or
atlas descriptors.

Destroy and reset require quiescence or perform the documented bounded
retirement sequence. Before returning success, they must restore these
invariants:

- no mapped upload or vertex memory;
- no command, fence, descriptor, atlas, attachment, or framebuffer retained
  by an in-flight submission;
- no reserved, committed, or pending present transaction;
- no active present record;
- no installed Neon hook owned by a destroyed Vulkan resource set;
- no stale target or atlas generation visible through public state;
- resource high-water counts and display-owner ownership return to baseline.

Failure during creation, replacement, rebind, submit, wait, presentation, or
teardown is atomic at the owning boundary. The next valid frame must either
continue on the old generation or begin from a cleanly recovered generation.

# Owning files

The exact implementation ownership is frozen as follows:

| File | Ownership |
| --- | --- |
| `Anvil/Graphics/Vulkan/neon_vk_chrome.pbi` | Neon operation lowering, resource orchestration, atlas/target generation publication, and present-record production |
| `Anvil/Graphics/Vulkan/neon_vk_resources.pbi` (proposed) | Focused resident resource lifetime, atlas retirement, attachment/framebuffer replacement, and recovery ledger if split from the adapter |
| `Anvil/Graphics/Vulkan/vk_wsi.pbi` | Target-neutral provider/image/present state and generation validation; shared changes require serialized integration |
| `RaspberryPi4/Board/screen_source.pi4` | HDMI/DSI display adoption, draw/scan ownership, DMA/CPU presentation, and present-record consumption |
| `Anvil/Graphics/Vulkan/neon_vk_display.pbi` | Target-neutral completed-frame record; the display owner consumes it |
| `Anvil/Graphics/Vulkan/neon_vk_prepared_lifecycle.pbi` | Optional prepared-native lifecycle installer, linked explicitly by the composition |
| `RaspberryPi4/Board/screen_frame_present.pi4` | Pi4 HVS/DMA frame transaction and confirmed display completion |
| `Anvil/Graphics/Vulkan/vk_foundation.pbi` | Shared Vulkan object/resource primitives; changes require serialized integration |
| `Anvil/Graphics/Vulkan/vk_pipeline.pbi` | Shared pipeline and dynamic viewport integration; changes require serialized integration |
| `Anvil/Graphics/Vulkan/vk_command.pbi` | Shared command recording/submission integration; changes require serialized integration |
| `RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4` | Pi4 V3D runtime resources, cache, completion and recovery behind the shared backend seam; serialized integration required (ownership updated 2026-10-27) |

`RaspberryPi4/Lib/neon.pi4`, `RaspberryPi4/Board/v3d_console.pi4`,
`RaspberryPi4/Board/screen_geom.pi4`, and `Anvil/Core/input_events.pbi` remain
compatibility and integration authorities. Lifecycle dispatch, public status,
counter ownership, and input capture cancellation must be changed only through
the corresponding renderer-neutral contracts and their owning integration
files.

# Required evidence

Desk gates must exercise capacity separation, whole-primitive refusal,
font-generation replacement, stale target/present rejection, provider loss,
resize and rotation transitions, repeated create/render/destroy, and injected
allocation/submit/wait/presentation failures. The eventual Pi matrix must
cover HDMI and DSI, all available rotations, odd extents, draw/scan buffer
ownership, DMA presentation, single-buffer fallback, and recovery to a valid
next frame. Public counters and resource generations must be checked at every
transition.


## Transactional bitmap atlas generations - 25 October 2026

The adapter now creates an unpublished atlas image/view/descriptor, uploads
the prepared staging pixels, and waits before swapping active handles.
Preparation or capacity failure preserves the old generation and GPU bytes.
An uncertain completion retains candidate and active resources and disables
the owner until device-idle retirement; it never frees possibly referenced
memory speculatively. Existing TrueType partial/full glyph uploads are retained.

The physical Pi 4 proof preserves all 2 MiB of the old atlas under memory-table
exhaustion, then completes three generation swaps with exact text/sprite
pixels and unchanged live allocation count. A private diagnostic injects
unknown completion after a real upload and proves retention/idle teardown;
the GPU is not intentionally hung. The complete current 15-scene baseline and
existing partial-upload pixel/transfer oracle remain exact. Historical line
scenes 4/5 already differ from the old native corpus due to the 14 October line
placement contract; that golden is preserved. Evidence and repeatable tools:
`docs/evidence/neon-atlas-generation-pi4-20261025/README.md`.


## Separate Neon family accounting - 25 October 2026

Default flat4096/262144 and textured2048/98304 record/input-vertex limits
are now enforced independently of configured total commands and actual
emitted storage. All draw families are classified; native path points charge
once, bitmap flat glyphs count native bit rectangles, retained sprite groups
preflight as a whole. Bitmap planning preserves advance/clip/blank semantics.
Begin/Abort/Destroy own ledger resets; the private clear sentinel is uncharged.

Physical tests fill all four logical dimensions, retain the other family,
compare190native glyph/font costs, preserve refusal state/guards, and match
81920 GPU bytes at all rotations plus clear-only output. Seven seeded side-path
refusals and successful recording are separate from actual maximum loads.
All245760 current15-scene bytes and124widget checks remain exact, with blank
flat cells removed from physical vertex counts. Evidence and limits:
`docs/evidence/neon-family-budgets-pi4-20261025/README.md`. Native maximum
path/storage, public-counter ownership, external/grid quota-specific physical
cases, desktop integration and broad Vulkan completion remain open.


## Public renderer state ownership - 25 October 2026

The optional typed state-query/error-writer pair now makes public counters,
clip enable, error and readiness belong to the installed drawing owner.
Vulkan publishes its native-unit ledgers and ancillary counts. Native GPU
internals query hardware readiness independently. Replacement/removal clears
both callbacks; native fallback remains independent, and partial installation
refuses without changing the binding. Frontend errors forward to the owner.

Physical bug1440 before/after evidence checks nine counters before/after submit,
refusal and clip/error semantics, six contract groups, all16384 exact GPU bytes
and zero final allocations. Ninety-three corrupt proofs are rejected. The
complete current15-scene PMF still matches the physical regression and all245760
bytes /124widget checks pass. Evidence:
`docs/evidence/neon-public-state-pi4-20261025/README.md`. Hardware timing/address
accessors, maximum point/storage work, dedicated external/grid quota cases,
desktop integration and the broader completion goal remain outside this claim.


## Full native point staging and fan input - 26 October 2026

The staging boundary now follows the native262144 flat-input vertex limit.
The real Pi4 fan pipeline emits all262144 points; only the final vertices
form the checked rectangle, detecting high-index truncation. All16384 GPU
bytes match the independent oracle; refusal guards and teardown pass, with
38 corrupted proofs rejected. The full current15-scene corpus remains exact
across245760 bytes and124widget checks under the larger variable layout.

Line staging reaches the same boundary, but quad lowering still needs786432
vertices and refuses atomically; line/outline output storage remains open.
The extra staging arrays use3.9375MiB, covered by the linked monitor variable
reservation. Build337 compiles, notinstalled. Evidence:
`docs/evidence/neon-native-points-pi4-20261026/README.md`.

The immediate engine port targets Vulkan on Pi4/Anvil, as the original plan
records; desktop OpenGL is its behavior reference. A separate desktop Vulkan
backend is not established by these proofs. Wider recovery and Vulkan work
remain open; this is a point-boundary result, not full port completion.


## Shared vertex-memory inputs and sixteen-node transforms - 26 October 2026

The Pi4 shared VPM reservation now covers both input and output row counts,
retaining existing varying padding. A twelve-input/six-output compact shader
previously drew blank frames. With unchanged QPU code, larger shared segments
now match all131072 GPU bytes over four rotations. The bounded position planner
accepts sixteen scalar operations, reuses dead index registers for large input
layouts and refuses seventeen operations before publishing a pipeline.

The compiled510-case sizing table, independent instruction/register decoder,
41 damaged-proof refusals and zero-allocation teardown pass. The full current
15 scenes retain245760 bytes and124widget checks. Build338 compiles, notinstalled.
Evidence: `docs/evidence/vertex-shared-vpm-pi4-20261026/README.md`.

Compact32-byte line records work in the isolated public Vulkan proof; production
Neon still uses its prior144-byte lowering. Full native line/outline capacity
and integration remain open, as does the wider high-register stage/mode issue.
No throughput or full engine/Vulkan completion claim follows from this proof.


## Current rebind preflight candidate, 26 October

The shared framebuffer owner now exposes AnvilVkFramebufferTargetCheck for the
current single linear BGRA8 scanout contract. Rebind requires its successful
handle/dependency/owner, bound-span, extent/pitch and retention checks before
publishing any target state. The query is read-only and acquires no resource
lifetime; the caller still synchronizes object changes and recording/submission
still revalidate their references. The current engine requires exact render-pass
identity; this is not general Vulkan render-pass compatibility. This phase does
not change initial adapter creation. Controlled object/adapter compositions and
the Pi4 Vulkan composition compile only; runtime/GPU acceptance is pending.
Evidence: docs/evidence/neon-framebuffer-target-candidate-20261026/README.md.


The initial creation path now obtains its pitch through the shared validated
framebuffer-pitch query before any target publication or renderer allocation.
The image owner's planned pitch is authoritative even when it exceeds four
bytes times width. Invalid targets and unexpected zero results refuse; the
query is read-only and takes no lifetime. The preceding rebind-only limitation
is superseded by this source candidate. Four-target object compositions and
Pi4 Vulkan integration compile only; physical validation remains pending.
Evidence: docs/evidence/neon-initial-target-pitch-candidate-20261026/README.md.


The checked teardown candidate now quarantines adapter recording before device
idle, then requires WSI rollback success before discarding presentation or
callback ownership, unmapping or releasing resources. Idle/rollback refusal
retains handles, callbacks and mapping for retry; a pending WSI image is not
released while GPU completion is unknown. The WSI bridge/core is unchanged in
this phase. Controlled caller proofs and Pi4 Vulkan integration compile only;
physical recovery remains pending. Scope:
docs/evidence/neon-wsi-teardown-candidate-20261026/README.md.


## Later physical validation on running build 344, 26 October

Live version/map and a fresh Vulkan-console capture now confirm build 344 and
its enlarged variable reservation. The current Pi4 returning proofs pass 477
shared-cleanup, 360 checked-teardown, 81 framebuffer-target, 235 adapter-ownership
and 1200 geometry observations, plus the 18-word shared binder report. Controlled
CPU providers remain distinct from hardware failure recovery. Real Vulkan
prepared-owner handoff matches 16,384 bytes and finally releases every counted
object; the freshly rebuilt 15-scene composition matches 245,760 current-baseline
bytes and 124 widget checks. All accepted runs return zero, with healthy cores,
Vulkan restored and deadman off. A target-builder schema mismatch was corrected
without relaxing its oracle, then rerun successfully. No reset/install/emulator
was used in this phase. These results supersede preceding compile-only status
for the exact cases listed in docs/evidence/neon-current344-pi4-20261026/;
actual GPU-fault/WSI refusal recovery and other-board runtime remain unproved.
Architecture still refuses 261 keys; broader provenance/publication remains open.


## WSI recording ownership, 26 October

Begin now validates attached WSI recording ownership before atlas work, mapping
or command reset. It permits non-WSI frames and a matching acquired image, while
refusing other bridge/core states, foreign device, stale image identity or target
generation. Failed publication alone does not return an image to writable state.
The bridge and completed-frame record have shared .pbi implementation owners;
their former .pi4 include paths remain compatible. No display driver is changed.

The actual WSI state/bridge/record and extracted Begin composition passes 199
observations on Pi4; admitted Begin uses a rejecting atlas spy, while refusals
reach no resource work. Four CPU targets compile; only Pi4 executed. A separate
fresh real Vulkan regression matches all 245,760 current scene bytes and 124
widget checks. It does not establish hardware WSI scanout or GPU-fault recovery.
The installed monitor remains build344; these are returning RAM payloads. Source
checks pass 62/446/5 and reject 96 hostile cases. Architecture still refuses 261
keys and broader provenance remains open. Exact scope and identities:
docs/evidence/neon-wsi-recording-pi4-20261026/README.md. Topic1462 stays open.


## WSI surface freshness through consumption, 26 October

Commit revalidates every reserved item's surface before advancing any image or
ticket. The new read-only avkWsiPresentValidate query also checks all committed
items for live ownership, pending image state, current surface identity, loss
and resize epoch. The bridge matches the captured target/ticket/swapchain/image
identity before the record can be published or matched for consumption. Refusal
retains cleanup ownership; explicit invalidation and rollback remain possible.
Retirement alone still permits an acquired image's presentation.

The original commit gap has a 201-observation corrected capture. The later stale
record gap is reproduced with 30 expected failed observations; its final 334-row
state proof corrects the common cases and covers read-only batch queries and
captured identity mismatches. Four CPU targets compile; only Pi4 executes. The
fresh real Vulkan 15-scene regression matches 245,760 bytes and 124 widget checks.
These RAM tests do not establish hardware WSI scanout or actual display/GPU-fault
recovery. Display-copy completion ordering remains open. Monitor 344 is unchanged.
Architecture/provenance publication refusals remain. Exact scopes/identities:
docs/evidence/wsi-commit-revalidation-pi4-20261026/ and
docs/evidence/wsi-present-freshness-pi4-20261026/. Topic 1464 remains open.

## Resident display ownership and interactive geometry, 26 October

The console validates completed-frame ownership before display copying and
consumes it only after successful transfer. A failed copy retains the source
and possible DMA ownership; checked teardown requires DMA quiescence as well
as GPU completion. Banner retargeting follows successful consumption.

Build345 exposed a resident fallback during changing banner text. Build346
retained the original capacity error through teardown. Build347 warms current
clock/status glyphs before Begin, outside the render pass, and stayed in Vulkan
through startup and a follow-up live capture with zero retained errors. The
controlled ownership composition covers14cases/448words and a separate teardown
regression360observations; it is not real DMA fault injection.

The subsequent physical rotation matrix found that interactive rotation/scale
used an older detach/rebuild path that lost Vulkan selection. Both commands now
delegate to the existing checked stored-geometry owner. Installed build348 passes
DSI0/90/180/270, keyboard show/hide at each rotation, scale2/auto and explicit
DMA-to-Vulkan return. Live captures and error/health reports are retained. Original
default90, absent overrides and keyboarddown are restored. HDMI shares the source
transition but has no runtime result here. This is resident console acceptance,
not hardware WSI/FIFO presentation, injected-fault recovery or full port completion.

Evidence: docs/evidence/neon-present-order-pi4-20261026/ and
docs/evidence/neon-interactive-geometry-pi4-20261026/.
Architecture/provenance publication remains unaccepted. Topics1465/1466 stay open.


## Confirmed DSI display-buffer presentation, 26 October

Installed build349 copies Vulkan frames to the inactive fixed DSI buffer and
consumes completed-frame ownership only after HVS confirms the new list active.
Banner updates clone the front before changing the inactive buffer. Capture uses
the confirmed front; teardown restores ordinary scanout before DMA/native drawing.
Unknown flip completion retains ownership. The actual helper passes16controlled
cases/288words; physical349 passes all four DSI rotations, keyboard, scale and
DMA/native-V3D renderer return, with both front addresses observed and zero
timeouts. The matrix and native handoff retain14captures and healthy core reports.

The source capture change is limited to BCM2711; other controller capture behavior
is retained but not tested here. This does not connect or advertise the shared
WSI extension or establish stopped-controller/GPU fault recovery. Boundary polling
adds wait cost; no headroom gain is claimed. Source publication remains refused.
Exact scopes: docs/evidence/neon-dsi-frame-presentation-pi4-20261026/.


## Qualified DSI banner idle wait — 2026-10-26

The display owner accepts an optional idle callback without depending on prompt services. The resident Vulkan console supplies its existing qualified GPU-wait provider only around banner display presentation, and clears it before testing success or returning. Unqualified/non-banner callers retain polling. The provider sleeps only with the existing prompt WFE qualification, EL3 and software-PWM guards. The timeout still retains ownership and never abandons a pending hardware flip.

The physical Pi4 build349 executed the actual owner with controlled providers: 19 cases, 342 state words, including delayed adoption with/without the callback and timed-out adoption with callback. The strict oracle rejects353 synthetic corruptions. These are not real hardware-fault tests. Integration source checks cover19guards/13unsafe mutants. Monitor350 was then canonically built, verified on storage with349 backup and candidate, restarted once, and checked after90seconds. The physical display matrix covers four rotations, keyboard, scale and DMA-to-Vulkan return; captures and controller status are retained. No emulator or Bluetooth test.

This replaces busy polling with an optional qualified wait for banner presentation; it does not reduce display refresh latency. No numerical CPU reduction or speed gain is claimed: elapsed frame statistics include waiting. No WSI extension, FIFO queue or full-port completion claim. HDMI, real fault recovery, actual WSI provider registration and other Vulkan capabilities remain open. Publication checks still refuse254architecture findings and98provenance omissions. No source publication or gate relaxation.

Evidence: docs/evidence/neon-dsi-qualified-idle-pi4-20261026/. Topic1470 remains open.


## Private DSI WSI source integration - 2026-10-26

Monitor351 registers the real main and optional banner images in separate private, single-image source chains. After warming resources and binding the selected target, the owner acquires and attaches before recording. Existing Chrome End marks render-ready and commits a ticket. Display consumption completes that ticket only after the inactive-buffer transfer and HVS list adoption. A failed transfer retains the source. Checked Chrome rollback precedes chain/surface/provider destruction, which precedes freeing the physical targets. Cleanup refusal retains the remaining handles and prevents framebuffer fallback.

The reusable helper is target-neutral; the board opts in only for the qualified DSI path. It does not advertise public extensions or implement blocking acquire. The FIFO source contract is private and synchronous, with at most one outstanding image per target; this is not a new asynchronous multi-image presentation queue.

The first controlled physical test correctly rejected the negative image-index sentinel across the acquire API's 32-bit output and an integer-sized local slot. The caller now zero-initializes that slot and reads it only after successful acquisition. Fixed actual-body controlled tests passed17cases/170statewords, including partial creation, ordered/refused teardown, unavailable acquisition, wrong image identity, failed attach and failed release retaining ownership. The strict oracle rejects179 synthetic corruptions. These providers are opaque spies, not hardware-fault tests. The reusable builder reproduces the exact physically tested source. Integration guards and older display-order guards also pass.

Build351 was canonically compiled and installed with verified350 backup, candidate and boot-file reload. One reset and90seconds of quiet startup preceded live identity/map checks. Its actual DSI matrix passed all four rotations, keyboard, scale and DMA-to-Vulkan return with twelve captures, positive completed private WSI transactions and zero reported flip timeouts or retained console errors. Original settings/defaults restored, cores healthy, deadman off. No emulator, Bluetooth or desktop Vulkan work.

Public Vulkan extension negotiation/dispatch, blocking acquisition, broader WSI behavior, HDMI validation and actual stopped-controller/DMA/GPU recovery remain open. Architecture publication still refuses254findings and provenance98omissions across984sources; no source publication or gate relaxation. This is internal provider integration, not full Vulkan or Neon completion.

Evidence: docs/evidence/neon-dsi-wsi-provider-pi4-20261026/. Topic1470 remains open.


## Parent lifetime retained on refusal - 2026-10-26

The old instance path attempted device destruction, ignored refusal and invalidated the parent anyway. Device destruction also had no WSI child check. The exact actual core and WSI implementation reproduced these defects on physical Pi4 with a state-only backend: 11 cases,132 observations. Old report acceptance means reproduction of the defect, not successful runtime acceptance.

The foundation now offers optional read-only child guards. Valid WSI provider registration installs generation-aware checks before publishing extension objects. Device teardown refuses while a WSI chain belongs to the live device, before semaphore reset or other mutation. Instance teardown refuses while a live surface or device belongs to it, without cascading into device destruction. Public vkDestroyInstance retains the original refusal instead of replacing it with a stale-handle message. Explicit child-first cleanup succeeds. This does not replace the existing broader core-device cleanup policy with a universal child audit.

The same actual-core test passed the corrected11cases/132observations; strict old/fixed oracles reject each other and141synthetic corruptions. A separate physical core-only composition passed with optional guards absent, retained the parent on live device refusal and succeeded after explicit device destruction. Both payloads returned to resident351 with healthy prompt/cores. These tests manually create controlled outstanding state; no real GPU/display/DMA fault was injected.

The fixture procedures were namespaced to avoid the generic test name Source colliding with the architecture analyzer's cross-source call lookup. Recompilation produces a byte-identical257292-byte raw payload, so current fixture code retains the physically checked behavior. No analyzer/ratchet was relaxed. The generic full proof compiles for UNOQ/QCM2290 using the canonical target memory layout; compile-only, no other-board runtime claim.

Canonical352 is installed with verified351backup/candidate/boot reload, one reset and90seconds quiet startup. The physical DSI geometry/keyboard/scale/DMA-return matrix passes with private WSI transactions completing, zero flip timeouts and zero retained console errors. All display defaults restored; cores healthy; deadmanoff. No emulator, Bluetooth or desktop Vulkan changes.

Khronos lifetime contracts: https://docs.vulkan.org/refpages/latest/refpages/source/vkDestroyInstance.html and https://docs.vulkan.org/refpages/latest/refpages/source/vkDestroyDevice.html require explicit child-before-parent cleanup. These reference contracts guide the refusal; no implementation source was consulted.

Public WSI surface/swapchain API, negotiation/dispatch, blocking acquisition and broader Vulkan capabilities remain unfinished. HDMI and actual hardware-fault recovery remain unproved. Mandatory publication checks still refuse254architecture findings and98provenance omissions across986sources. No source publication or gate/license relaxation.

Evidence: docs/evidence/vulkan-parent-lifetime-pi4-20261026/. Topic1471 remains open.


## Public surface queries and instance enablement - 2026-10-26

The public API advertises VK_KHR_surface revision25 as its one instance extension, validates enablement and resets permission on instance-slot reuse. All five standard surface commands are callable with C-compatible52-byte capabilities and8-byte format records. Counts, modes and VkBool32 use32-bit outputs. Format/mode discovery follows count-query, caller-capacity and VK_INCOMPLETE semantics. Capability conversion preflights every word before output; malformed/unrepresentable metadata refuses rather than truncating. Disabled, stale, foreign and lost owners do not mutate query output.

AnvilVkSurfaceCreate binds an explicitly registered native provider and key under an enabled instance. This is an Anvil integration function, not a fabricated OS/platform extension. The private non-extension constructor remains for existing internal callers. GIPA resolves the five commands only for a current enabled instance; null-instance and device lookup do not disclose their addresses. One bounded name matcher is shared by the core dispatcher and extension negotiation; the dispatcher still chooses its original128-byte cap. VK_KHR_swapchain/device extensions, platform window extensions, blocking acquisition and general asynchronous presentation remain unavailable.

Physical returning tests use actual API/core/state code with the explicit state-only GPU backend. Final24cases/192state observations cover all13 distinct capabilities words, exact layouts/offsets, output/count canaries, unsignedUINT32_MAX capacity, truncated enumeration, all five lookup permissions, unsupported extension, foreign/disabled/stale owners, loss and slot reuse. The strict oracle rejects203 synthetic corruptions. The earlier23-case version is retained separately. Parent lifetime11-case/132word regression also passed. UNOQ/QCM2290 compiles the final fixture using its canonical layout; compile-only, no other-board hardware claim.

The legacy core dispatch gate was updated for a correctly sized260-byte extension property output instead of a four-byte sentinel. Its first physical run returned0/167checks/0failures, but native-width result stores left upper halves in its eight-byte report slots untouched. The host correctly refused that report. Explicit integer-width stores fixed the fixture, and the returning Pi run passed all167 exact records. The initial30-second watchdog argument was rejected before upload/run; the valid15-second deadman was used for the actual run. No emulator was started.

The extension inventory audit now selects the exact VK_KHR_surface commands from its pinned registry, requires the complete callable family and checks arity/return shape; arbitrary extra commands still refuse. Its selected synthetic parser/source models pass and reject four malformed models. The full pinned-registry audit was NOT rerun: the exact raw pin URL returned404 and no local registry path was recorded. No checksum was weakened or replaced. The old emulator-backed dispatch command was also not run; the actual core gate was executed as a bounded returning program on the Pi instead.

Monitor353 enables the surface extension for its DSI instance and validates both real main/banner sources through support/capability/format/mode queries before use. Boot reported272confirmed frame switches=272privateWSIcompletions and2real public target checks withzeroerrors/timeouts. The physical geometry/keyboard/scale/DMA-return matrix passes with fresh public-query checks after rebinding; nativeV3D return also passes. Defaults restored; cores healthy; deadmanoff. These normal display tests do not inject real stopped-controller/DMA/GPU faults. No Bluetooth or desktop Vulkan change.

The new Khronos specification/interface citation is classified consulted in both provenance records, with existing MIT election/notices retained. Initial99omissions return to the prior98 after adding that owned citation; no gate/ratchet/license text was relaxed. Architecture still refuses254findings and provenance98across988sources; source publication remains unaccepted. This is surface-query/enablement support, not swapchain API completion or Vulkan conformance.

Contracts: https://docs.vulkan.org/refpages/latest/refpages/source/VK_KHR_surface.html ; VkSurfaceCapabilitiesKHR, VkSurfaceFormatKHR, surface query and GIPA reference pages from the same official documentation. No third-party implementation code was consulted.

Evidence: docs/evidence/vulkan-public-surface-pi4-20261026/. Topic1472 remains open.


## Float geometry adapter capacities - 2026-10-26

The float adapter retained 2048-polygon-side and 4096-line-vertex guards after the Anvil Vulkan backend gained the shared native point budget. The limits now derive from NEON_MAX_VERTS: 262144 static-line endpoints, 262142 filled-polygon sides (centre plus closing point), and 131072 outlined edges (two endpoints each). Invalid oversized calls refuse before opening a path. Odd static-line counts discard their trailing endpoint after applying LimitVertices. Per-frame remaining native quotas, configured physical storage and command budgets remain independently enforced by the backend.

Physical Pi4 build353 reproduced the old adapter refusal and passed the corrected 19-case controlled-callback oracle. Cases include exact native boundaries, first over-boundary requests, null/negative input, signed integer maximum, odd counts and limited counts. Accepted maximum requests deliberately meet a callback that returns77 before reading a large input buffer or computing the polygon; this proves adapter admission, not full-size GPU execution. Separate emitted 4098-point and2049-side cases verify callback counts and closure. The complete4096-byte report oracle rejects1024 synthetic word corruptions across old/fixed shapes. Each oracle rejects the opposite actual physical report.

The production GPU test includes the complete shared float adapter, native frontend and Vulkan backend. Twelve frames across0/90/180/270 rotations execute4098-point static line lists and2049-side filled and outlined polygons, crossing both previous guards. All196608 independent terminal-geometry/clear pixel bytes and every draw/vertex counter match. Large polygons are deliberately fully clipped, followed by a visible box; these frames prove accepted production execution and subsequent binding state, not visible circle tessellation or full native maximum throughput. Static lines have a visible terminal segment following clipped predecessors. Full native backend capacity remains covered by its earlier dedicated backend proofs, not reasserted by these smaller wrapper frames.

Returning captures348(old),349(fixed),350(GPU) left healthy cores, deadmanoff and Vulkan active. The GPU program returned0 after41.2seconds using bounded watchdog-pet phases. Its console return line was lost inside the30-second wait; the existing runner recovered the successful RETURNED run record without resetting or rerunning. No new monitor image, reset, storage write, emulator, Bluetooth or desktop change occurred. Current monitor remains353.

Two initial controlled-fixture compiles failed before board access: the bit conversion spelling and missing EnableFloatingPoint. Both diagnostic logs are retained. One GPU host attempt stopped before board commands for missing source identity; the empty output folder was retained, and identity was recorded before the actual upload. Current public fixture names avoid duplicate callback/helper definitions. Recompilation verifies both namespaced raw images byte-identical to the physically tested images. The controlled shared float code also compiles for UNOQ/QCM2290 using its canonical layout; compile-only, no other-board runtime claim.

The three build/check tools and two fixtures are reusable without an emulator. This is a capacity compatibility correction, not performance qualification, full Neon completion, public swapchain completion or Vulkan conformance. Mandatory publication checks remain authoritative; no bypass or relaxation is accepted.

Evidence: docs/evidence/neon-float-port-capacity-pi4-20261026/. Topic1473 remains open.


## Mapped bitmap text - 2026-10-26

NeonVkPortText previously refused canvas scaling and camera zoom without a selected TrueType face. The fallback bitmap renderer now maps its existing atlas cells through the same source canvas and camera convention. Width remains in source units, preserving right/centre alignment. Bitmap origins snap to source pixels before camera mapping, matching the existing bitmap port convention. Ordinary unmapped bitmap text retains its old route. The actual TrueType draw, native bitmap draw, angled bitmap draw, metrics, glyph-cost and atlas-map procedure bodies remain unchanged; eight exact-body comparisons are recorded separately.

The implementation plans every visible cell, mapped Q8 rectangle and atlas coordinate before changing public counters, native quotas, physical vertices or recorded draws. Source glyph advances and merged-bit-rectangle logical costs remain unchanged; physical geometry remains one atlas quad per visible ink cell. Empty, transparent and clipped text does not consume geometry. Invalid mapping metadata, stale atlas state, incompatible batches and insufficient capacities refuse. Mapped dimensions remain bounded to 8192, zoom to 16x, source/camera coordinates to one million pixels and visible Q8 coordinates to the existing renderer limit. Native font metrics above 8192 refuse for mapped drawing. Up to 4096 source bytes follow the existing bounded bitmap-run convention; no new Unicode shaping claim is made for bitmap fonts.

The final production returning program passed 24 actual GPU frames across four rotations on Pi4 build353, all 393216 independent pixel bytes exact. The oracle derives glyph rows from the actual input bitmap, then applies independent nearest sampling, source metrics, scaling, clipping and colour. It covers 2x canvas enlargement, 0.5x reduction, 2x camera zoom and translation, bold glyphs, right/centre alignment, fractional centred-origin snapping and clipping. Source width remains 24 for A-space-A regardless of mapping. Every draw/native-vertex/physical-vertex/glyph/run counter matches.

Each rotation additionally verifies capacity refusal, invalid dimensions, excessive source coordinates, excessive zoom, stale atlas metadata, active grid batching, invalid UV on the second glyph after a valid first glyph, empty scissor and transparent colour. The checks preserve the unused 16-byte geometry guard, command free rows and all relevant public counters, then succeed on retry in the same frame. Atlas/batch/UV failures are controlled test state, not real hardware faults. The strict checker rejects 61 report/pixel corruptions. The earlier24-frame candidate and expanded-edge candidate are retained separately; final source-pixel snapping and fractional-origin coverage are in bitmap-mapped-final.

The final source also passed the existing 15-scene regression: all 245760 current-contract scene pixels exact and 124 widget checks. Historical line scenes 4/5 already differed before this change; the native golden corpus is not changed. Final mapped run returned 0 after 11.5 seconds at capture 353; the scene regression returned 0 after 13.9 seconds at capture 354. Earlier candidates were captures 351/352. All left healthy cores, Vulkan active and deadman off. Monitor and boot image remain 353; no new monitor build, reset, storage write, emulator, Bluetooth or desktop work. Shared implementation introduces no Pi4 register or hardware address; physical qualification is Pi4 only.

Publication gates remain red at 254 architecture findings and 98 provenance omissions across 991 sources. No source commit or publication accepted, and no gate/ratchet/license weakening. The existing approved PDF builder updates the guide; broader Neon completion, public swapchain/device extension support, hardware-fault recovery and full Anvil Vulkan remain unfinished. Forum 1474 remains open.

Evidence: docs/evidence/neon-bitmap-mapped-pi4-20261026/.

Final mapped-path review preserves the native clipped-row counter on whole-row rejection and projects constant row coordinates once. The final bitmap-mapped-rowcounter test supersedes the earlier mapped candidate; the unchanged native/TrueType bodies retain the preceding scene-regression evidence.


## Board-test ownership and valid spy contracts - 2026-10-26

61 exact board-specific Vulkan tests/fixtures moved into their owning board test trees: 58 Pi4 sources under RaspberryPi4/Tests/Vulkan, plus one absent-backend program each under RaspberryPi3, ArduinoQ and RockPi4C Tests/Vulkan. Portable shared state fixtures remain in the shared tree. The unrelated Pi3 EDID test is outside scope.

The source list comes from gate findings and exact unchanged ratchet paths. A bounded reference audit reads 470 named files from existing docs/vault and literal include dependencies; a separate local-import audit reads 99 named tool modules. Thirteen exact callers were updated. No directory enumeration or broad repository search was used. The audit does not claim coverage of unrecorded external clients or historical evidence snapshots.

56 sources were byte-identical at relocation; five only needed relative include directives changed to canonical root paths. Every destination include resolves. Five representative programs compile to identical raw images before/after across all four targets: Pi4 compute lowering, Pi4 UI Chrome composition, and the three absent-backend compositions. These are compile-only comparisons. 59 current implementations remain identical after include-path normalization; two stale spy fixtures were corrected separately. No production renderer/backend algorithm changed.

The canvas spy initially failed compilation for a missing native-capacity constant. After supplying that fixture configuration and updating bitmap mapping assertions, it returned 69 at capture 356 because an old 2049-side refusal assertion remained. That failed run is retained. The polygon and static-line overflow checks now use current limits. The corrected full canvas/sprite/text spy returned zero after 1.5 seconds at capture 357 on Pi4 Anvil 353. It uses controlled callbacks, not GPU/display execution. Healthy prompt/cores, Vulkan and deadmanoff were confirmed. The geometry companion has the capacity declaration repaired but is not separately claimed as executed.

New/grown architecture findings fall from 254 to 199: downward includes disappear and board-extension findings fall from 51 to 12. Downward-call keys rise from 75 to 118 because removing shared mocks exposes existing production-to-board dependencies. Protocol 30/private 32/one-definition 7 findings remain. Provenance still refuses 98 omissions across 991 sources. No gate/ratchet/license rule was changed; source publication remains unaccepted. No monitor build/update, reset, storage, Bluetooth, desktop or emulator work occurred.

The next ownership work must fix the real Pi4 GPU-driver and generic frontend coupling rather than restore shared mocks or add blanket seams. Forum 1475 covers the relocation and 1476 the stale fixture; both remain open. Full Neon and Anvil Vulkan completion is unfinished.

Evidence: docs/evidence/vulkan-board-test-ownership-20261026/.


## GPU owner and explicit implementation selection - 2026-10-27

Five Pi4 runtime modules now belong to RaspberryPi4/Lib/Vulkan: vk_v3d_backend.pi4, vk_v3d_shader.pi4, vk_v3d_texture.pi4, neon_vk_particle_csd.pi4 and neon_vk_particle_csd_port.pi4. The pure typed-IR lowerer remains shared as Anvil/Graphics/Vulkan/vk_ir_v3d42.pbi. It uses the shared encoder and contains no board runtime dependency. The software smoke program is now portable source at Anvil/Graphics/Vulkan/Tests/vk_backend_software_test.pbi.

The shared vk_backend_select.pbi imports no implementation. Programs explicitly include their chosen backend before selection validation; the implementation supplies ANVIL_VULKAN_BACKEND_PRESENT, which must match ANVIL_VULKAN_BACKEND. The Pi4 composition root and software smoke were updated together. After platform/API/DMA prerequisites, the GPU selection fragment is:

```text
#ANVIL_VULKAN_BACKEND = 1
XIncludeFile "RaspberryPi4/Lib/Vulkan/vk_v3d_shader.pi4"
XIncludeFile "RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_select.pbi"
```

Software programs select 2 and explicitly include vk_backend_software.pbi. The software smoke uses a large 64MiB heap plus core state; the actual Pi4 returning build uses load 01000000 and exclusive stack top 07F00000, outside linked BSS. The UnoQ compile uses load 80000000/stack 88000000. Its other-board runtime is not claimed.

A bounded audit reads 617 exact named files from prior gate/ratchet/docs/vault paths, literal includes, repository imports and literal source declarations in known tools. Six module paths and 47 caller/inventory documents were corrected, followed by the explicit selector/test changes. No directory enumeration or broad source-tree search was used. The normative design owner row was updated; the old IR path in the unchanged gate's historical explanation remains intentionally historical. Unrecorded external clients and frozen evidence snapshots are outside this reference audit.

All 323 implementation procedure bodies are unchanged. Five representative programs across four targets compile to identical raw images before/after the final ownership/selection work. The complete GPU proof remains byte-identical to the previously physical 24-frame/393216-byte result at capture 355, including when the explicit selector is inserted. Provenance values, classifications and reasons are unchanged except for moved path keys. No gate, ratchet, license election or protection was changed.

The old .pi4 suffix correctly blocked a UnoQ build of the pure IR lowerer. Its shared .pbi form now compiles there, and the Pi4 lowerer image stays byte-identical. The output ISA is V3D4.2; this is compile-only CPU-library portability, not an Adreno backend. The reused IR test still has a Pi4-specific report address and would need a suitable layout before another-board execution. The three absent-backend probes remain byte-identical; other-board hardware coverage is unchanged.

Selector validation compiles actual GPU/software positives, and rejects missing, mismatched and unknown selections. A moved Pi4 hardware import remains rejected on UnoQ. The first cross-chip negative supplied the Pi4 stack accidentally and stopped at the compiler memory guard; its log is retained separately. A corrected UnoQ stack proves the intended cross-chip refusal. No emulator was started.

The first physical software smoke returned 11 at capture 358 because its legacy fixture left instanceCount at zero. Its exact executable existed before the ownership changes; this was a stale test, not a relocation regression. The fixture now supplies one instance and checks that zero instances, multiple instances and nonzero firstInstance refuse while preserving all 256 target bytes and backend job/draw counters. The corrected actual CPU executor smoke returned 0 after 5.0 seconds at capture 359, including transfers, clears and a closed triangle draw. It explicitly checks that it does not advertise GPU execution. This does not claim a complete public Vulkan command-path test or GPU rendering.

The latest actual Pi4 GPU regression at capture 360 returned 0 after 13.9 seconds and matched all 245760 current-contract scene bytes plus 124 widget checks. Its compiled image is also byte-identical to the earlier full-scene program. Historical native line scenes 4/5 already differed before this phase; the golden corpus is unchanged. Prompt/cores are healthy, Vulkan active and deadmanoff. Monitor/boot remain 353; no normal monitor build/update, reset, storage, Bluetooth or desktop work occurred.

Publication still refuses 140 new/grown architecture keys (62 downward calls, 30 protocol, 32 private, 9 board extensions, 7 duplicates) and 98 provenance omissions across 991 sources. Source commit/publication is not accepted. Remaining generic frontend ownership, wider Vulkan features and hardware qualification remain unfinished. Forum 1477 covers ownership/selection and 1478 the stale software fixture; both remain open.

Evidence: docs/evidence/vulkan-gpu-owner-20261027/.


## Shared primitive dispatch and native fallback - 27 October 2026

The twelve public primitive wrappers now belong to neon_frontend.pbi. The Pi4
native implementation registers one complete, immutable typed callback family
before Main, independently of the optional external family. Shared clear removes
external/state/measurement callbacks while preserving native fallback. Scissor
calls retain native clip mirroring before external notification. All twelve native
bodies preserve their implementation after declaration renaming and removal of
their former external dispatch branch. No broad Neon-name seam was declared.

Physical Pi4 evidence includes 96 shared-contract assertions/38 ordered events,
245760 exact current scene bytes/124 widget checks and two native GPU frames
around real Vulkan rendering and complete adapter/object teardown. Both native
16384-byte crops and draw/glyph ledgers match; independent interior/ink probes
also pass. The shared contract compiles for UnoQ; no other-board runtime claim.

Anvil 354 is installed after full backup/candidate/boot-file SHA checks and one
reset followed by 90 quiet startup seconds. Automatic Vulkan startup and native
V3D/Vulkan selection pass with fresh captures365/366/367 and healthy core state.
It remains on Vulkan. Mandatory publication review still refuses130 new/grown
architecture keys and98 provenance omissions. This completes primitive dispatch
ownership, not all shared Neon ownership, full application/API qualification or
broader Vulkan functionality. See docs/evidence/neon-primitive-dispatch-20261027/.


## Portable renderer modules - 27 October 2026

Eight renderer/adapters now have shared .pbi owners and the lifecycle .pi4
compatibility include is removed. Core Chrome no longer pulls an optional native
lifecycle provider into targets without one. Its public prepared installer moved
unchanged to neon_vk_prepared_lifecycle.pbi; canonical Pi4 compositions link that
explicit integration header. The ordinary binder keeps its independent public-provider
contract and does not import concrete Chrome private state. Native fallback
and the prepared ownership contract remain available. All233 implementation
bodies retain their exact code. A full Pi4 composition, the current15scene proof
and native/Vulkan/native proof preserve complete raw/container bytes. The actual
UnoQ core/file composition compiles core Chrome against the absent backend,
without a mocked GPU or a new hardware claim. Missing atlas composition and the
initial prepared-lifecycle coupling refusals are retained as evidence.

The reference audit covers738 literal recorded sources/dependencies, including
paths in the one task vault note. It corrected two additional callers beyond
the earlier719-file scope and now has no old-module reference in that scope;
missing historical paths remain reported without drive searching. Publication
still refuses122 architecture keys and98 provenance omissions. Build354 remains
the actual running monitor; fresh read-only version/map/core/Vulkan checks pass.
No new GPU run, monitor install or reset is claimed for byte-identical ownership
changes. The remaining application/API behavior and broader Vulkan work remain
open. Evidence: docs/evidence/neon-shared-modules-20261027/.
