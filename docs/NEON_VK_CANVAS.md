# Native Neon Vulkan canvas

Include `Anvil/Graphics/Vulkan/neon_vk_canvas.pbi` after the native Chrome
renderer and its public Vulkan dependencies. The shared owner has no board
imports. It supports direct-framebuffer targets and scoped suspension of an
attached WSI parent. Idle and recorded-frame continuation have bounded physical
GPU and WSI-core coverage below; physical WSI transfer remains unqualified.
The resident target-service qualification below covers the small client fixture;
full engine and presentation qualification remain incomplete.

## Lifecycle

1. Keep the caller's device, render pass, Chrome renderer and display
   framebuffer alive. Initialize a `NeonVkCanvas` with `NeonVkCanvasInit`.
2. Call `NeonVkCanvasCreate(state, width, height, sprite, scratch, bytes)`
   between frames. The selected sprite ID 1..16 must be unused. Width/height
   are bounded by 2048 and the backend's authoritative image checks.
   Scratch supplies at least `width*height*4` initial texture bytes. It can
   be reused immediately after Create. Those initial pixels cannot be drawn
   through the canvas before a completed source frame replaces them.
3. `NeonVkCanvasBegin(state, clear)` selects the fixed attachment and begins
   its source frame. Clear is a valid, aligned 16-byte Vulkan colour value.
   Draw in canvas coordinates through the existing Neon/Chrome adapters.
4. `NeonVkCanvasEnd` completes/join the source frame, consumes its offscreen
   completion, copies it into the existing sprite and restores the caller's
   target and orientation. A source wait that has not completed is retryable.
5. Begin the caller's final Chrome frame with the desired letterbox clear.
   `NeonVkCanvasDrawPassthrough` records the aspect-fitted image. The caller
   ends/joins that final frame, transfers it through the display owner and
   consumes the final presentation intent. The canvas does not own that step.
6. `NeonVkCanvasClose` retires its attachment/view/framebuffer/memory and its
   matching sprite generation. The last target releases the group lifetime guard.
   Close is idempotent. It must precede Chrome/device/pass/display teardown.

Up to 16 canvases with distinct sprite slots can retain their resources,
subject to actual device heap limits. They share one renderer resource-lifetime
reference, independent of the compute-producer attachment. Every
registered state object, the context and code remain alive until all Close
calls succeed. Calls and source frames are serialized. Explicit continuation
can suspend and resume a parent frame; nested target scopes refuse.
The render pass must finish its colour attachment in GENERAL or
TRANSFER_SRC_OPTIMAL layout. No image handles or ownership cross the resident
application service boundary in this implementation.

## Target, input and filtering

`NeonVkCanvasRetarget` explicitly adopts a caller-rebound/resized target on the
same device and render pass. Unannounced target-generation changes refuse
Begin, drawing or idle Close; they cannot silently redirect a canvas frame.
The same source image can be fitted to the new target without reallocation.

`NeonCanvasFit` computes a centred integer rectangle from canvas and logical
target extents. An aspect ratio requiring less than one output pixel refuses.
Odd leftover pixels fall on the right/bottom. `NeonCanvasMapPoint` and the
owner's `NeonVkCanvasMapPoint` return 1 for inside, 0 for bars/outside, or a
negative refusal. Output is two Q16 coordinates. Logical input is already
adjusted for display rotation. Outside/refused output is untouched. This is
coordinate mapping, not complete captured-pointer/key-event routing.

The canvas defaults to linear min/mag sampling, as the original final pass
did. `NeonVkCanvasSetLinear(state, enabled)` selects nearest (0) or linear (1)
between frames. It updates the canvas generation only after the sampler
transaction succeeds and preserves that choice across resize. Active, bound,
suspended and stale-owner changes refuse. Invalid modes leave sampling and
generation unchanged. `NeonVkChromeImageSpriteLinearId(id, enabled)` also exposes the choice
to other native sprite consumers. Nearest remains the default for replacement
sprites and the shared glyph/sprite atlas. Changing sampling advances that
image's generation so retained batches become stale. The linear sampler is
created lazily once per renderer and retired with Chrome. Addressing remains
clamp-to-edge; repeat addressing/general OpenGL state parity is unqualified.

## Refusal and cleanup

Canvas state initialization, scratch and mapped-point outputs cannot overwrite
live owner state. An active source frame can be aborted by Close. A final frame
begun by the caller cannot be aborted or consumed by Close; finish/present it
first. A failed cleanup retains remaining handles for retry.

The renderer's resource-lifetime reference prevents premature Chrome destruction.
The last canvas releases it only after checked device idle; a failed idle call
retains ownership. Compute-producer attachment and its retirement remain separate. If an in-place copy submission fails, Chrome is
poisoned. After successful idle, canvas Close can retire its source resources
and release its lifetime reference. Renderer-owned texture/sampler resources remain for
`NeonVkChromeDestroyChecked`, followed by recreation. Physical GPU-fault
recovery has not been induced or qualified here.

Initial texture setup uses the existing upload/staging owner, so peak heap use
includes canvas attachment, sampled texture and temporary upload storage in
addition to Chrome's resident atlas and display attachment. Repeated source
frames reuse these resources. Maximum canvas sizes, large-heap fitting and
steady-state throughput have not been qualified by the small fixture.

## Evidence and remaining work

Actual Anvil 370 capture 504 passes 161 checks and 307200 pixels across four
rotations. The reference uses ideal bilinear weights; only red/green channels
at 2240 interpolated boundary pixels allow one UNORM level of rounding error.
Every other byte is exact. Nearest filtering fails, and 401 damaged reports/
images refuse. Captures 501/502 are earlier nearest-filter qualifications,
with 153/156 checks; 502 adds live-state alias guards.

CPU capture 503 passes 32 checks of the exact producer-detach guard with
controlled idle outcomes, including failed-idle retention and retry. Its
checker rejects 74 corruptions. It is not a real GPU-fault test. Counted UnoQ
build 90 compiles the actual monitor composition and shared owner with the
absent backend. No UnoQ execution or GPU capability is claimed.

Capture 510 adds the existing native menu/panel/list scene through an 800x600
canvas, aspect-fit final pass and real 800x1280 DSI DMA transfer. All 60 device
checks pass, including direct equality of all 4,096,000 attachment/scanout bytes.
All 1,024,000 captured RGB pixels match the pre-optimization hardware reference.
Three bounded frames replace an earlier 12-frame diagnostic whose checksum
verification exceeded its 15-second watchdog. No deadline was extended.

Shared Chrome retains two complete clip-coordinate dimension banks per axis,
adding 128 KiB BSS. Rebinding between canvas/display no longer rebuilds 16,384
ratios each time; exact conversion and out-of-table fallback remain unchanged.
All direct line readers select the published bank. Capture 508 passes 31,488
coordinate/line checks across repeated dimensions and all four rotations.
The Pi4 single-range cache owner now reuses its existing complete line walker
and retains one completion barrier, including declared-uncached positive ranges.
Cache operations are preserved; none are removed based on assumed mappings.

Matched profiling runs 506/509 reduce warm source/final/display time from
444/295/35 ms to 164/32/35 ms (about 3.4 times faster). Their complete captured
images are identical. In the final display acceptance, warm frames take about
278 ms; this is not smooth animation acceptance. The actual final GPU render
is about 3.1 ms, with remaining CPU recording, copy and cache costs still open.

Normal Pi4 build 372 and actual UnoQ composition 91 compile successfully. The
UnoQ wrapper forces shared Chrome/canvas emission with its absent backend;
no UnoQ execution/GPU capability is claimed. Pi4 remains on installed 370.
Complete application/input-event routing, physical input, CRT shader behavior,
maximum-size/performance acceptance and broader Vulkan conformance remain open.
The full Neon port is not established by these qualifications.


## Canvas-aware native input

Include `Anvil/Graphics/neon_canvas_input.pbi` for caller-owned routing of
logical-screen `NativeInputEvent` records through an aspect-fit viewport.
`NeonCanvasInput` contains the viewport, `pointer`, `input` and an internal
blocked-mouse latch. It owns no input device, service session, queue or heap.

Initialize zeroed state with
`NeonCanvasInputConfigure(@state, @canvas\viewport)`. Pass each accepted
resident input record to `NeonCanvasInputFeed(@state, @event)`. Pointer x/y
are canvas coordinates, while the existing native contact/generation and
keyboard translation remain in effect. Consume transient pointer/editor
outputs once per event; draining a queue and using only its last transient
would lose presses or commands. `NeonCanvasInputIdle` clears those transients
without ending capture, moving the cursor or clearing the blocked-mouse latch.
Use the wrapper for feeding/reconfiguration, rather than calling the underlying
native pointer functions on its embedded state.

Presses in letterbox bars do not capture. A mouse pressed in a bar remains
blocked after entering the canvas until its left button is released or input
is cancelled. Touch moves never invent a missing down. A captured contact may
move and release outside the viewport: signed coordinates are preserved and
the release reaches the caller, so capture ends without clamping an outside
release onto a widget. Wheel input in bars is suppressed. Another contact or
mouse cannot steal a touch drag. Focus cancellation clears the blocked latch;
stale releases cannot clear it. Typed text and editor commands use the existing
`NeonNativeInputState` vocabulary, not the legacy integer Chrome key codes.

Reconfiguration refuses an active contact or blocked mouse. After a display
target change, finish/cancel input, retarget the canvas, then configure the new
viewport before accepting events in its coordinates. The input context copies
the viewport; it does not silently follow later canvas changes. Invalid or
overlapping state/event/viewport buffers refuse without publishing a partial
update. A reconfiguration preserves focus generation and event time.

Pi4 capture 511 passes 79 controlled-record checks; the full report checker
rejects 166 corruptions. Capture 512 routes eight scripted mouse records to
real native Neon buttons drawn through Vulkan and physically transferred to
DSI: 155 device checks, two legitimate activations, ignored bar/held-entry
presses, and outside releases delivered. All 4,096,000 final attachment/scanout
bytes are equal. Its host checker rejects 317 report and five image corruptions.
The initial host text check wrongly expected a white label; the corrected
check uses the native theme's exact RGB(150,208,221), with 62 matching ink pixels.
The original refusal and separate read-only recheck are retained.

Warm frames in this small button scene are about 121 ms; that is a different
workload from the earlier menu/panel/list performance fixture. Pure input and
the counted actual UnoQ root/shared-renderer/input composition 92 compile only.
No UnoQ execution or hand-actuated touch/mouse/keyboard acceptance is claimed.
The existing resident input service is unchanged. Full application keyboard
integration, physical input, cursor/first-tap, and smooth rendering remain open.


## Legacy text-field keyboard routing

`Anvil/Graphics/neon_legacy_keys.pbi` owns the unchanged integer Chrome key
constants formerly embedded in the Pi4 native renderer. Its shared
`NeonLegacyKeyFromNative(key)` converts the normalized AIK named-key domain
into those legacy values. Call it for accepted AIE_KEY_DOWN records only;
typed text uses the independent scalar output. Unsupported named keys return
zero. An NCE editor command or raw HID usage is a different domain and must
not be passed as a normalized key. This bridge does not add legacy Ctrl
selection/clipboard behavior or page/insert commands that the field lacks.

Pi4 capture 513 passes 297 checks through a real `Neon_TextInput` drawn into
the Vulkan canvas and physically transferred to DSI. Thirteen controlled
records focus the field, move to End/Left, insert X, Backspace/Delete, move to
Home, insert Z, move Right, submit once, Escape, then attempt unfocused text.
Text, caret, focus and submission counts are checked at every step. Final
text is ZA, with one submission and no focus; subsequent typing is ignored.
The proof also checks all 15 normalized named keys plus invalid values, using
literal expected legacy values. All 4,096,000 final attachment/scanout bytes
are equal. The checker rejects 610 report and five image corruptions.

These are controlled event records, not a hand-actuated keyboard test. The
small text-field scene's warm frames take roughly 114-118 ms and do not prove
smooth performance for a full application. Physical keyboard/touch, cursor,
first-tap and complete menu/list/editor/retained application routing remain
open. The pure shared editor keeps its existing NCE vocabulary; it is not
renumbered to match the legacy field.


## Live input-client boundary and packet writes

Capture 520 opens the actual Anvil native-input service and routes its records
through the canvas owner to native buttons and a text field. It passes 41
checks, renders to DSI, polls for five seconds and closes the context. The
device advertises touch; zero records arrived. This proves idle integration,
not physical actuation, keyboard availability, first-tap or smooth animation.
It also exposed an AArch64 compiler entry bug: a top-level initializer call
overwrote the loader service pointer before automatic Main. The shared
compiler correction preserves incoming register arguments across initialization;
three physical control/global/explicit-call checks pass in captures 517-519.

Source-stage captures 521/522 retain the original 297 scripted keyboard and
pixel checks. They separate composition, source submission, texture conversion
and restoration. Source submission includes portable validation, private record
preparation, cache maintenance, list construction and hardware completion.
The later Finish call alone is not a measure of total GPU work.

The V3D word writers now admit a complete field once, use aligned 32-bit
stores where safe and retain byte stores for unaligned fields. Near capacity,
the existing byte writer preserves the partial prefix, cursor and first error.
Shader records still clear every byte, including partially populated records.
No cache operation, barrier, resource lifetime check or deadline is removed.
CPU captures 523/524 produce identical complete 16 KiB reports: 144 packet
cases, four record-word alignments and six initialization/refusal cases.
The host oracle rejects 931 damaged reports.

Matched canvas captures 522/525 preserve all 1,024,000 captured RGB pixels
exactly. Median warm frame time changes from 181.29 to 178.42 ms (about 1.6%);
record preparation changes from 10.06 to 9.20 ms and list construction from
11.15 to 10.16 ms. This instrumented comparison does not establish smooth
rendering and should not be compared directly with other historical fixtures.
Cache, texture conversion, display transfer and remaining submission costs
remain substantial.

Counted Pi4 composition 374 and actual UnoQ composition 94 compile only.
Neither is installed; the Pi remains on Anvil 370. The UnoQ absent backend
does not acquire a GPU capability. Full application event routing, physical
input, cursor/first-tap, remaining engine APIs and wider Vulkan support remain
open. Evidence: docs/evidence/neon-canvas-live-packet-20261028/.


## Native coordinate table selection

Native geometry cache hits now select the existing CPU table-bank addresses
instead of exchanging all table entries. Four addresses add 32 bytes of BSS;
no table allocation, GPU mapping, cache operation or barrier is removed.
Misses retain the original exact-ratio builder. Geometries above the bounded
BSS-bank limit use the capacity-sized arena, including recovery from a
previous bounded-bank hit.

Matched physical captures 528/529 retain all 61,788 coordinate words and
all 1,024,000 final RGB pixels exactly. The same 297 keyboard checks and
13 rendered frames pass. Median warm frame time falls from 179.25 to
139.42 ms (22.2 percent). Warm native rebinds fall from roughly 8.4-9.5 ms
to 0.11-0.13 ms. Cache misses remain expensive; 139 ms is not smooth.
Capture 527 separately measured native frame begin at roughly 1.35 ms.

Captures 530/531 check 123,813 coordinate words over 20 visits, including
4097-wide/high CPU geometries, rotation, reset and bank recovery. Unused
tail words in both bounded banks remain intact. These are in-bank tail
canaries, not allocated redzones. The GPU canvas remains 800 by 600;
these checks do not qualify a 4097-pixel GPU render target.

Counted Pi4 monitor 375 is installed after backup, full-file digest checks
and one restart. Raw image: 6,054,332 bytes, SHA-256
acb717316d4141a8186be7dbf31c5c6f1ed5ddf27fff1eac1ab46bca969708e2.
Actual UnoQ root composition 95 compiles only; no GPU capability is added.
The previous 374/94 paragraph above records that earlier test phase.

Capture 532 runs the full composed resident application on Anvil 375 with
stored PNG/font assets and the real input service. All 65 checks pass over
90 frames at 30.0003 FPS. Mean frame work is 23.77 ms, maximum 25.19 ms;
no frame exceeds 33.333 ms. This direct resident-service workload differs
from the offscreen fixed-canvas comparison above. Input advertises touch
and returns zero events; physical actuation is still unqualified. Vulkan,
fonts and cores are healthy after return, with zero display timeouts.

Evidence: docs/evidence/neon-native-coordinate-20261028/. Full engine
routing through the fixed canvas, physical input, remaining rendering APIs
and wider Vulkan support remain open.


## Explicit cold-cache owner policy

V3dSetCacheOff now accepts an explicit declaration from the MMU owner, like
DmaSetCacheOff. A true value means D-cache is disabled and dirty lines from
any previous cacheable state have been retired. The owner must clear this
before enabling caches. The default remains false; it does not guess the
hardware state. Only the line walk is skipped. Positive-range and batch
completion barriers remain unchanged, including batch refusal behavior.
Anvil's CacheDmaPolicy supplies its measured state to both libraries.

Captures 534/535 separated native record cleaning, binning and rendering.
The final native render interval included roughly 8.8 ms ARM target cache
walks before and after rendering; its GPU completion poll was about 3.1 ms.
The standalone returning diagnostic has private V3D/DMA globals and does
not inherit the resident cache policy. Capture 536 reads active SCTLR as
0x30c50830 before and after its scene: MMU and D-cache are off. Anvil hands
the payload cold, with old dirty lines retired. This does not establish a
safe skip for cacheable memory, nor a resident-renderer speed improvement.

Matched cache-state runs preserve all 61,788 coordinate words, all 297
keyboard checks and all 1,024,000 RGB pixels exactly. Old-code baseline
536 is 114.04 ms per median warm frame. New-code conservative default 538
is 113.97 ms with zero skipped walks. Explicit V3D and DMA cache-off policy
537 is 63.73 ms, about 44 percent lower. In its final render, target walks
drop to roughly 0.01/0.004 ms while GPU completion remains about 3.14 ms.
This combined policy result is not attributed solely to V3D. Its different
cache-state fixture is not a matched comparison with the earlier 139 ms
profile. About 64 ms per frame is still short of smooth animation.

Physical CPU capture 539 passes 29 checks covering conservative default,
nonzero normalization, no-op ranges, positive walks, reset, full/partial
uncached ranges, successful batches, poisoned batches and nested-begin
refusal. It runs cold only; cacheable dirty-data silicon qualification is
not claimed. The Range/BatchBegin/BatchRange/BatchEnd procedure bodies are
unchanged. The public fixture and builder are in Tests/Vulkan and tools.

Pi4 monitor 376 and actual UnoQ root 96 compile only. Neither is installed;
the Pi remains on verified Anvil 375. GPU execution is qualified only on
the physical Pi4; absent backends acquire no capability. Evidence:
docs/evidence/neon-cache-owner-20261028/. Resident offscreen service
support, complete engine render-target/routing behavior, physical input,
and wider Vulkan support remain open.


## Retained offscreen targets and resize

The native shared canvas owner now retains up to 16 targets, each using a
different existing sprite slot. Only one source frame can be active. Internal
target restoration propagates the new renderer generation only to peers
which captured that same caller target epoch. An external rebind still makes
old captures stale, even after another target is explicitly retargeted.
The shared resource-lifetime reference is released only when the last target
successfully closes. Caller state objects remain alive while registered.

NeonVkCanvasResize(state,width,height,scratch,bytes) validates arguments before
retiring the old image. Resize discards its contents, as the original engine
contract does. Invalid arguments preserve the old resources; once retirement
succeeds, allocation failure is reported with CLOSED or retained failed-cleanup
state. Drawing the resized image before its first completed source frame
refuses. No old contents are presented under the new dimensions.

The first physical test, capture 540, exposed a portable Vulkan capacity
defect: the fourth retained canvas returned VK_ERROR_TOO_MANY_OBJECTS.
The framebuffer table had four rows including the display, and the image,
view and memory budgets reserved sampled sprites without their separate
color attachments. The shared tables now reserve attachment rows from a
named 16-target budget. Heap admission, actual allocation sizes and lifetime
checks are unchanged; sixteen maximum-size targets are not promised to fit.

After correction, capture 541 passes 98 target checks. Captures 542/543 add
cross-target sampling, stale-epoch isolation and sampling after resize.
The repository builder build_neon_canvas_targets.py and neon_canvas_targets_check.py
then pass on the physical Pi4 in capture 544: 123 target checks plus the
original 297 keyboard checks over 13 final frames. The target proof retains
16 small targets; two differently sized targets render red/green, a third
samples both, and a resized target is sampled again with its new green data.
It also verifies live-frame refusal, invalid resize preservation, partial
retirement, full retirement and reuse. Three GPU-derived sampled color
checks pass. Every one of the final 1,024,000 RGB pixels matches the prior
keyboard scene. The host checker rejects 375 damaged reports.

Pi4 monitor 377 and actual UnoQ root 97 compile only; neither is installed.
The Pi remains on verified Anvil 375. The new owner is executed by returning
payloads; resident offscreen service operations are still absent. There is
no physical input-actuation, nested/mid-frame render-target or complete
engine/Vulkan qualification. Evidence:
docs/evidence/neon-canvas-targets-20261028/. Capacity finding remains open
in forum topic 1486 while source publication gates refuse.


## Blank creation, retained scopes and resident candidate

NeonVkCanvasCreateBlank(state,width,height,sprite) and
NeonVkCanvasResizeBlank(state,width,height) use zeroed bytes in the existing
checked upload staging allocation. They need no caller pixel buffer and add no
large static scratch array. The original scratch-taking APIs remain available.
Blank pixels are transparent, but drawing a target still requires a completed
source frame. Resize discards the prior image; invalid dimensions preserve it.

For preparation between binding and recording, call NeonVkCanvasBind(state),
prepare fonts or particles, then use Begin/End. End completes the offscreen
copy while leaving the scope selected. Multiple frames can use that scope.
NeonVkCanvasAbort discards an unsubmitted source frame and preserves the last
completed sampled image. NeonVkCanvasUnbind(state) restores the captured
caller target. Close can retire its own selected scope. An active caller frame,
nested scope or unannounced target epoch does not become a valid switch.

Physical Pi4 capture 545 passes 131 target checks and 297 keyboard/UI checks,
including transparent first and odd-tail texels. Capture 546 passes 163 target
checks and the same 297 UI checks. It renders a prepared floating-point
particle while targets remain retained, checks that abort preserves its yellow
pixels, and closes/reuses a selected target. All 4,096,000 attachment/scanout
bytes agree in the final UI scene. This is lifecycle and pixel evidence, not
smooth-animation acceptance or a real GPU-fault recovery test.

The additive resident graphics target family uses feature bit 1024 and minor 9;
the console service table contract remains ABI 1.8 at slot 38. Include the HAL
contract, base service client and optional neon_service_targets client.
Create returns a positive opaque token or zero with NeonServiceError.
Resize, Free, Bind, Unbind and Draw use that token. No device/image addresses
cross the API. Limits report 16 slots and a maximum dimension of 2048, subject
to backend validation and available heap. Ordinary sprite uploads cannot
replace a target-owned slot.

NeonServiceTargetBind(handle) enters an idle scope and reports that target's
Width/Height. Prepare fonts/particles, use ordinary Begin/End/Abort, then call
NeonServiceTargetUnbind(handle). Child End performs no display transfer.
Unbind restores parent surface and virtual-canvas dimensions; camera state,
including changes inside the scope, persists as in the original engine.
Create/Resize/Free refuse while a scope is bound. Self-sampling, an unfinished
source image, stale tokens, invalid scalar inputs and unsupported old providers
refuse explicitly. Close retires the active scope before other retained targets.

The resident path now passes its 35,372-byte pure-client test on Anvil 380:
108 exact report rows, eight color/filter/camera probes and 80 filtered white
text pixels. Explicit close while bound with sixteen targets and context reuse
are checked before the final scene. The final context remains owned until the
loader captures its frame, then normal scope cleanup retires it. A missing-text
image and a damaged report are rejected. The original refused runs are retained.
The composed native-input/assets application also passes 65 checks over 90
frames. Input remained idle; no physical input actuation is established.

Legacy role preparation now uses the existing font pixel-height query. Line
height includes two pixels of spacing and must not be used as a raster cache
key. The first 379 resident run exposed this mismatch: preparation succeeded,
then the text draw returned -21203. The corrected 380 draw and image pass.
The initial fixture also closed before capture; its console image is preserved.
The final text oracle checks filtered white coverage rather than requiring
fully white texels after two linear sampling stages.

Monitor 378 also exposed an unsafe startup cache assumption. D-cache disabled
does not certify that previous dirty lines were retired. The V3D skip now starts
conservative, becomes eligible only after a completed owner flush, and is revoked
before cache enable. Controlled exact old/new owner bodies execute on Pi4:
37 checks per version, eight old contract failures and zero candidate failures.
Those callbacks do not perform a real cache/MMU transition. Real 379/380 monitor
boots separately confirm working Wi-Fi/DHCP/console, matching live-image hashes,
healthy cores/fonts/Vulkan, zero display timeouts and watchdog off. Post-hash
CPU samples are 6.72-11.87 percent on 379 and 5.96-12.55 percent on 380.

The verified 375 USB rollback, failed 378 candidate and both later verified
updates are retained. The Pi now runs 380. UnoQ root 98 remains compile-only
with an absent native lifecycle; CPU capture 547's twelve absence checks do not
establish another board's GPU. Full application/input behavior, nested/mid-frame
targets, CRT effects, maximum-size/performance and wider Vulkan remain open.
Publication gates remain unresolved; no full port or conformance is claimed.


## Attachment preservation prerequisite - 28 October 2026

The original engine's independent render-target contract explicitly forbids
nesting. Nested targets are therefore not required for engine parity. Switching
to an offscreen target during a window frame and resuming prior window contents
still needs implementation. The shared public Vulkan render pass currently
accepts only CLEAR; this checkpoint does not advertise LOAD support there.

The Pi4 hardware owner now has an explicit raster RGBA8 color-load selection.
It emits packet 30 before END_OF_LOADS, preserving the existing attachment for
each tile. The packet retains alpha and uses byte stride. RenderBegin/Clear
reset the selection; ordinary native frame callers keep clearing. Existing
cache maintenance and GPU completion waits are unchanged. This board packet
implementation is a prerequisite beneath the portable Vulkan contract, not a
new target-independent hardware claim.

Physical capture 7 on unchanged Anvil 380 passes 48 packet/load/ownership
checks, 164 target checks and the original 297 scripted keyboard checks. All
79,968 attachment pixel comparisons pass over 193x127 and 65x33 images: seeded
color and alpha survive a no-draw pass, a partial replacement changes only its
rectangle, and the next ordinary frame clears every pixel. Each direct-driver
case restores all seven borrowed native surface fields before resize/retirement.
The kept keyboard frame and its scanout comparison pass. Cores/fonts/Vulkan
restore, display timeouts remain zero, and the watchdog is off.

The first packet oracle used an unaligned word read and stopped on a processor
alignment exception before GPU load testing. Its exact instruction and fault
address are retained. After byte-wise decoding, all 44 initial load checks
passed but the following scene correctly refused because the fixture had not
restored its temporary native surface. The final complete run fixes both
fixture defects; 152 host corruptions/originally refused reports are rejected.
No failed run is relabeled as a complete pass. Evidence is in
docs/evidence/neon-attachment-load-20261028/. Shared Vulkan LOAD, mid-frame
engine switching, effects, physical input and broader Vulkan remain unfinished.


## Shared Vulkan attachment LOAD checkpoint - 28 October 2026

The returning candidate now carries an explicit attachment-load selection
through shared render-pass objects, command recording and closed submission
records. LOAD requires a backend capability and a defined supported initial
layout; recording retains that layout claim for queue validation. A LOAD pass
does not dereference clear values. Whole-attachment clears before any draw
replace the entry operation with CLEAR. Ordinary transfer clears explicitly
select CLEAR. The backend interface carries the mode without shared code
calling a board driver. Pi4 and software implementations have preservation
paths; the state-only and absent backends do not advertise this capability.

Physical capture 8 on unchanged Anvil 380 passes 14 public Vulkan checks:
an empty LOAD pass with zero clear values preserves all 24,511 pixels of a
193x127 attachment, including alpha, and creation refuses initial UNDEFINED.
The same run passes all 48 native load checks, 164 target checks and 297
scripted keyboard checks, with an exact 4,096,000-byte scanout comparison.
It returns zero in 12.4 seconds under the 15-second watchdog. Cores, fonts
and Vulkan restore; zero display timeouts and watchdog off are confirmed.

This proves the public empty-pass path only. Public LOAD with drawing,
wrong-layout submission refusal, software execution and engine suspend/resume
still need their dedicated validation. Exact render-pass identity restrictions
also remain. No new monitor image was installed. The first compile attempt
refused optional-parameter syntax before producing an image; the explicit
seven-argument backend contract compiled and ran. Source publication remains
unaccepted while mandatory gates refuse. Full Neon and Vulkan are incomplete.
Evidence: docs/evidence/vulkan-attachment-load-20261028/manifest.json.


## Ordered LOAD and refusal proof - 28 October 2026

Capture 9 on unchanged Anvil 380 extends the shared Vulkan LOAD proof to
ordered rectangle commands. Two overlapping clears preserve all other pixels
of a seeded 194x128 attachment. A whole-target clear before the first ordered
command replaces LOAD, then the next reset command buffer restores LOAD.
Wrong-layout and destroyed-framebuffer submissions refuse before changing any
pixels; no submission remains outstanding. All 57 public checks and 148,671
public-path pixel comparisons pass. The same run passes the prior 48 native
checks, 164 target checks, 297 keyboard checks and complete scanout comparison.
It returns zero in 13.5 seconds under a 15-second watchdog. Cores, fonts and
Vulkan restore, display timeouts remain zero, and watchdog is off. Host oracle
controls reject 135 damaged or empty-only reports. No monitor update occurred.

Ordered rectangle commands use the GPU backend render stream. This does not
yet prove an application shader pipeline in a LOAD pass. Source review against
Vulkan's compatibility rules found an existing exact render-pass slot check
on pipelines and framebuffers, plus a live dependency on the framebuffer's
creation pass. Topic 1492 records this before correction. The next change must
capture immutable compatibility descriptions and retain/check the actual pass
recorded for execution, preserving framebuffer, view and image generation
checks. Engine suspend/resume and complete Vulkan remain unfinished. Evidence:
docs/evidence/vulkan-ordered-load-20261028/manifest.json.


## Compatible render-pass ownership - 28 October 2026

Pipelines and framebuffers now retain immutable compatibility descriptions
for the supported one-color, one-sample, one-subpass shape. Attachment format,
attachment flags and subpass flags remain significant; load/store operations
and initial/final/reference layouts do not bind an object to its creation
pass. Command buffers record the actual begun render-pass handle. Submission
revalidates that generation and retains the actual pass, framebuffer and live
attachment dependencies. Foreign-device and stale view/image guards remain.

Physical capture 10 on unchanged Anvil 380 passes 24 shader/ownership checks
and 49,664 full-pixel comparisons. An existing pipeline renders through a new
LOAD pass using a framebuffer whose creation pass was destroyed. Only the
scissored rectangle changes. Destroying the actual recorded pass makes a
later submission refuse without modifying pixels. The composed target and
keyboard regression also passes (164 and 297 checks, exact final scanout).
The run returns zero in 12.4 seconds; cores/fonts/Vulkan restore healthy.

Physical capture 11 passes 83 state-backend object checks in 2.0 seconds,
covering compatible/recreated passes, incompatible attachment flags, foreign
owners, stale framebuffer/view/image, memory and retention. Three expectations
that encoded the old identity restriction were corrected, not disabled. An
UnoQ build of this same state proof compiles; no UnoQ runtime or GPU claim.
Host oracle controls reject 78 damaged/other GPU reports and 178 synthetic
state reports. Both physical runs leave watchdog off and no display timeouts.

Forum defect 1492 is fixed and locked with evidence reply 4089. No monitor
image was installed, and source publication remains gated. Engine frame
suspend/resume, effects, physical input and general Vulkan remain incomplete.
Evidence: docs/evidence/vulkan-renderpass-compatibility-20261028/manifest.json.


## Parent frame continuation - 28 October 2026

Chrome now exposes Suspend, Resume, Suspended and CancelSuspended. Suspension
finishes a section synchronously without publishing a display token. The
target owner can render a child, consume its completed offscreen result,
restore the parent binding and resume through a compatible LOAD pass.
Render-pass metadata stays in its Vulkan owner; a shared creation helper
copies the supported compatibility shape and uses the source final layout
as both continuation initial and final layout.

Resume restores viewport, scissor, geometry counters, family budgets and
retained path points. Child outline caches are invalidated before reuse.
Independent target scopes cannot nest. Wrong-target resume and clearing the
suspended parent through ordinary Begin refuse. A suspend failure with
uncertain completion quarantines recording; checked destruction retains its
idle requirement. Empty sections no longer need a transparent dummy draw.
Suspension currently refuses an attached WSI owner; that integration remains
required, as does wiring the resident service and public engine scope.

Physical capture 12 on unchanged Anvil 380 passes 58 continuation checks,
49,664 pixel comparisons, 164 target checks, 297 scripted keyboard checks
and an exact 4,096,000-byte final scanout comparison. It returns zero in
12.9 seconds under the 15-second watchdog. Parent drawing survives child
rendering; viewport/scissor and draw counts restore; wrong-target/nested
operations refuse; repeated empty resumes preserve contents; cancelling an
unpublished parent emits no present token. No physical-input claim is made.
The first compile exposed a test declaration-order error and produced no
payload. The physical run already passed its assertions; its initial host
oracle used the wrong numeric Chrome state-error constant. Rechecking the
same saved report with the declared -21202 constant passes. Both results
are kept. No second board run was needed. Host controls reject 178 mutated
reports and two reports from other probes. Fonts, cores and Vulkan recover
healthy, with no display timeout and watchdog off. No monitor update.

Forum overall topic 1483 remains open with progress reply 4090. Full Neon,
general Vulkan and repository publication remain incomplete.
Evidence: docs/evidence/neon-chrome-continuation-20261028/manifest.json.


## Resident parent-frame continuation - 28 October 2026

Anvil 382 qualifies continuation through the resident provider and pure public
client. The additive capability is bit 2048 at minor 10; target capability 1024
and the service-table ABI 1.8 at slot 38 are unchanged. Bind during a recording
window frame suspends that parent, enters an idle child scope, and exposes the
child dimensions. Use ordinary Begin/End or Abort, then Unbind to restore the
parent binding, mapping and recording phase through LOAD. Only the final
window End presents. Child camera changes persist. Older providers refuse the
new operation explicitly. Independent scopes do not nest, matching the original
engine; nesting is not an outstanding parity requirement.

The shared canvas preflight rejects stale ownership before suspension. The
provider and client retain the parent phase, and failed mutations quarantine
readiness. Open batches refuse a switch. Close handles a suspended parent and
its child. It also aborts an unfinished, unsubmitted window recording before
retiring idle targets; this fixes forum 1494. Submitted GPU/display ownership
checks remain required. Arbitrary GPU/DMA fault recovery is not established.

Physical capture 15 on installed 382 returns zero in 1.9 seconds: 145 exact
state assertions, twelve pixel probes and 80 filtered white text pixels pass.
The test includes close/reopen without End, close while suspended with sixteen
targets, stale/nested refusal, child abort and resumed parent abort. Parent red
and blue boxes and the green/yellow child remain visible. Host controls reject
439 damaged reports, the prior 137-row report and the missing-parent image.
Cores, fonts and Vulkan recover healthy, no display timeout, watchdog off.

Earlier capture 13 returned successfully but its image correctly refused:
two fixture boxes used scaled canvas coordinates for physical-pixel probes.
The correction explicitly selects target coordinates; expectations stay fixed.
Capture 14 on unchanged 381 passes 137 assertions and the same image checks.
Forum 1493 is fixed/locked at reply 4092; 1494 at reply 4094. Overall 1483 stays
open with progress reply 4095. Source-publication gates remain unresolved.

Both complete monitor builds use the counted build helper and retain 311
literal source/binary inputs. Build 381's ledger caller label was corrected to
the actual wrapper; its original ledger bytes remain in evidence. Verified
backup, candidate, boot-file and live-image hashes precede qualification.
Build 382 is installed; 381 backup is 1:/B381V382.IMG. Saved paths increase BSS
by about 4 MiB; fresh dynamic reserved ranges were checked before each payload.
This is Pi 4 execution evidence for shared code, not other-board qualification.

Attached-WSI continuation, preserved child rendering without an implicit clear,
remaining full engine/input behavior, effects and wider Vulkan remain open.
Evidence: docs/evidence/neon-resident-continuation-20261028/manifest.json.


## Preserving a completed offscreen target - 28 October 2026

NeonServiceTargetBeginLoad() begins another drawing section without clearing
the selected target. It requires capability 4096 at minor 11, a bound target
and a previously completed target image. Use ordinary End or Abort afterward.
The existing Begin(r,g,b,a) still clears. Fresh and resized targets must first
complete a clear frame; an unbound or already recording target refuses LOAD.
The service table remains ABI 1.8 at slot 38; opcode 45 is additive.

The shared NeonVkCanvasBeginLoad and NeonVkChromeBeginLoad entries use the
existing compatible LOAD render pass. A saved parent's state must still be
restored through Resume, not a fresh BeginLoad. Canvas checks completed-content
validity and ownership before rebinding or recording. Pending completion and
display ownership guards remain unchanged. This preserves the original engine's
ability to add drawing to a target without an implicit clear.

The pure-client physical proof on installed Anvil 383 passes 156 state checks,
thirteen pixel probes and 80 filtered text pixels. Empty LOAD and aborted drawing
preserve earlier colors and glyphs. New yellow drawing coexists with old blue
pixels inside the child while its parent is suspended. A full 1,024,000-pixel
comparison with capture 15 differs only at the eight deliberately preserved
blue pixels. Host controls reject 472 damaged reports and the previous cleared
child image. The existing close/reopen and parent-continuation checks also pass.
Cores, fonts and renderer recover healthy, display timeouts zero, watchdog off.

The complete counted build 383 retains 311 literal inputs. Its boot file and
live image were hash-verified, with backup 382 at 1:/B382V383.IMG. Shared source
benefits other providers, but this execution evidence covers Pi 4 only. Forum
1495 records the gap and its physical resolution. Full engine/input behavior,
attached-WSI continuation, effects, wider Vulkan and source publication remain
unfinished. Evidence: docs/evidence/neon-target-load-20261028/manifest.json.


## Attached presentation and target continuation - 28 October 2026

Chrome Suspend now keeps an attached acquired image in a separate saved WSI
owner while the child records. Child completion cannot present or release the
parent. Resume verifies the saved device, image key, acquisition and surface
freshness before restoring the owner at the parent's new target generation.
Loss or resize refuses resume without discarding ownership. CancelSuspended
waits for idle and releases the held image; checked destruction also retires
saved ownership. Attaching another owner while a parent is suspended refuses.
The normal active-WSI Rebind guard remains in force.

The shared avkWsiAcquiredValidate query also protects new recording against
surface loss and resize. Retirement alone permits an already acquired image
to finish, as before. Canvas creation can retain an attached writable parent.
Idle canvas close skips an unnecessary rebind when the parent identity is
unchanged, preserving attachment ownership. Ordinary idle binding with an
attached parent still needs an explicit scope contract; it is not implied by
the mid-frame Suspend/Resume path.

Physical capture 18 on Anvil 383 passes 131 WSI/continuation assertions,
24,511 exact parent pixels, 164 target-lifecycle checks and 297 scripted UI
checks, returning zero in 12.3 seconds. The final 4,096,000 scanout bytes agree.
Cases include child rendering, restored parent pixels, same-size resize,
retirement, loss/resize refusal, safe cancellation, creating/freeing a target
while attached and refusing a fresh Begin after loss. Capture 17 retains the
earlier 110-check subset. Host controls reject 397 damaged reports and the
old report shape. The GPU test uses real shared WSI state with offscreen
provider image keys; it does not perform a physical WSI display transfer.

Counted complete monitor 384 is installed with verified backup 383 at
1:/B383V384.IMG and verified boot/live hashes. Its resident service passes the
existing 156-check preserving-target test. Cores, fonts and renderer recover
healthy, display timeouts zero and watchdog off. Forum 1496 records the fix.
Shared code is qualified on Pi 4; no other-board GPU claim is made. Physical
input, full application behavior, broader Vulkan, fault recovery and mandatory
source-publication checks remain unfinished.
Evidence: docs/evidence/neon-wsi-continuation-20261028/manifest.json.


## Idle attached target scopes - 28 October 2026

Explicit CanvasBind/Unbind and implicit CanvasBegin/End now retain an acquired
presentation parent without starting a parent drawing frame. ChromeSuspendIdle
records the exact parent identity and saves acquisition; ChromeResumeIdle
restores only that parent, revalidates surface freshness and leaves it idle.
ChromeSuspended returns 2 for this idle scope and 1 for a recording scope.
The active-attachment Rebind refusal remains in force.

Loss during child rendering refuses normal restoration and close while keeping
the child resources and parent acquisition. Whole-context target cleanup uses
CanvasCloseContextScope to explicitly discard the unpublished parent after GPU
idle. Ordinary target free does not silently discard a stale parent.

On physical Pi 4, capture 20 passes 107 idle-scope assertions and 24,511 exact
parent pixels, plus 164 target and 297 scripted UI checks. Capture 21 passes
the earlier 131-check mid-frame continuation regression. Both return zero in
12.2 seconds with exact final scanout agreement. The checker rejects 325
mutated reports. These use actual GPU rendering and shared WSI state with
offscreen provider image keys, not physical WSI display-transfer testing.

Anvil 385 is installed with verified backup 384, boot and live image hashes.
The resident preserving-target regression passes 156 checks; fonts, cores and
Vulkan recover healthy with zero display timeouts and watchdog off. Forum 1497
tracks this correction. Full application/input behavior, wider Vulkan and
mandatory source publication remain unfinished.

## Cancelled idle-parent cleanup regression - 28 October 2026

Whole-context close accepts an idle parent that the caller has already
successfully cancelled. A still-suspended idle parent is cancelled after
checked device idle; other suspension states still refuse. This matches
ordinary Close retry behavior and retains the selected-owner checks.

The old implementation fails the cancel-then-close row with canvas state error
-21342 and retains resources, subsequently refusing recreation and retarget.
The fixed shared implementation passes 142 idle-scope checks, 164 target checks,
297 scripted UI checks, 24,511 retained parent pixels and the exact 4,096,000-byte
scanout comparison on physical Anvil 387 (capture 31, zero return in 12.2 s).
All 426 single-cell corruptions of the idle-scope trace are rejected. Cores,
fonts and Vulkan remain healthy, with zero display timeouts and watchdog off.

This is a returning candidate; the installed 387 image is unchanged. The fix
is in shared canvas ownership, not a Pi 4 special case. Physical WSI transfer,
physical input and the whole engine remain unqualified. Source publication
continues to be refused by the 101 remaining architecture findings.


## Owned target filtering - 28 October 2026

Native canvas sampling now has an owner-safe selection. The resident target
service already exposed a creation-time choice; its private sampler/generation
workaround now calls the canvas owner. No service ABI change is needed.

Physical returning candidate capture 33 on unchanged Anvil 387 passes 37
filter checks plus the 142 idle-scope, 164 target and 297 scripted UI checks.
An 8x8 red/blue attachment magnified four times gives exact red/blue nearest
pixels; linear boundary pixels are AARRGGBB FF9F0060 and FF60009F (the oracle
allows one red/blue level of hardware rounding). Resize retains both policies;
invalid modes, active frames, bound owners and stale generations refuse.
All 115 damaged trace/pixel controls are rejected. The run returns zero in
12.8 seconds, with healthy cores/fonts/Vulkan and watchdog off.

The first tiny 2x2 rendering attempt returned VK_ERROR_FEATURE_NOT_PRESENT:
the current Pi4 backend's render-surface check requires width/height at least
8. Creation alone is not proof that all later rendering is supported. The
failure is retained; the filtering proof uses the supported extent, without
claiming tiny render targets work. Resident integration is compiled in counted Anvil 388; its installed-image
qualification is recorded separately below. Overall port and publication gates
remain open.


Installed Anvil 388 is verified by its complete running-image SHA-256
`4f75f9c9e8eaa4e49099f6314b315c9106cf87504cbe34a69ac01f0500f22972`.
The unchanged pure-client target regression passes 156 checks, 13 pixel probes
and 80 filtered text pixels (capture 34, zero return in 1.9 seconds). The boot
update retained a hash-verified 387 backup, used one reset and a 90-second
quiet boot interval. Network, cores, fonts and Vulkan are healthy; watchdog
off and zero display timeouts. Forum 1506 closes the filtering gap, while
full Neon/Vulkan and source publication remain unfinished.


## Positive render-target extents - 28 October 2026

The Pi4 backend and native Neon surface/rebind validation now accept positive
width and height down to one pixel, matching the existing V3D planner. Capacity,
mapped extent, pitch, output-format and display-ownership guards are retained.
For a one-pixel axis the native integer coordinate transform uses centre/scale
one instead of zero. That enclosing viewport still maps pixel coordinates
identically; the actual framebuffer extent, clipping and tile-store limits
remain one pixel. Larger geometries retain their previous transform.

A physical returning candidate on Anvil 388 passes 45 target/filter checks,
142 idle-scope checks, 164 target-pool checks and 297 scripted UI checks. It
renders and samples a 2x2 red/blue attachment with both nearest and linear
filtering, then renders a 1x1 green attachment and samples two magnified pixels.
All expected colors pass, including exact green FF00FF00 for the 1x1 image.
The existing 24,511 retained-parent pixels and 4,096,000-byte scanout equality
also pass. Capture 35 returns zero in 13.3 seconds with healthy monitor state,
zero display timeouts and watchdog off. All 141 corrupted trace/pixel controls
are rejected. The original 2x2 refusal remains in the previous evidence archive.

This changes the Pi4 hardware adapter and its native engine; the portable
Vulkan planner already accepted positive extents. Other hardware backends are
not changed or execution-qualified. The installed 388 image still predates
this candidate. This does not establish every format, extent, rotation or
presentation path, or full engine/Vulkan conformance.
