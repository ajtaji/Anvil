# Retained Neon UI on Anvil

The shared retained layer supplies labels, breadcrumbs, buttons, sliders,
toggles, meters, DIP banks and carousels. Current shared state/input passes 115
checks under Anvil 355, with a real resident application loop on the Pi4.
Earlier bitmap and mixed TrueType GPU qualifications used Anvil 354. Shared
state also compiles for UnoQ; no UnoQ runtime result is claimed. This is an optional layer,
not the default monitor screen or a claim of full desktop engine parity.

## Ownership and composition

EnableFloatingPoint before including Anvil/Graphics/neon_retained_ui.pbi.
The caller supplies an aligned arena, control capacity and per-control UTF8 byte
budget including NUL. NeonRetainedRequiredBytes computes its minimum size.
Text is copied; exhausted capacity, unterminated/oversize text and derived
coordinate overflow refuse before a record is published. Handles carry a
generation: Reset/Configure invalidate old handles. Get returns a borrowed
read-only record valid until mutation. DIP banks support 1 to 64 switches.

Install a complete typed renderer family, set the font and logical viewport,
configure storage and add controls. Each control captures the active font;
a captured -1 falls back to the active font when drawn. Viewport maps caller-
transformed target coordinates to the virtual canvas. MouseDown is held state;
mouseReleased and action are edge inputs supplied by the caller. Focus navigation
skips noninteractive entries and remains bounded for empty/labels-only screens.
Focus pulse wraps each frame for indefinite sessions; elapsed time is reduced
before multiplication, keeping the shared sine function within its valid domain.
Calls are serialized; concurrent access is not supported.

EventHandlerInstall accepts a typed callback receiving control ID, event type 1
and application tag. A nonzero tag enables automatic callback delivery. EventGet
can poll the most recent event; it is a single slot, not an unbounded queue.
A callback may clear/rebuild the UI; input immediately returns without touching
old records afterward. Input, drawing and preparation reentry are forbidden.
The compiler also refuses a callback that statically recurses into input.
Renderer callbacks may not mutate the retained collection.

Compose Anvil/Graphics/Vulkan/neon_vk_retained_ui.pbi after the shared Neon
frontend, Chrome and their concrete dependencies. Create Chrome, configure
NeonVkPortCanvas, install NeonVkRetainedInstall and configure retained storage.
NeonRetainedPrepare belongs before the caller-owned Begin. It prepares carousel
options/arrows and DIP numbers as well as labels. DrawUI belongs inside the
caller-owned frame; abort that frame on a negative result. The UI does not create,
nest, end or destroy a device/frame. After Chrome recreation, install/prepare
again. Both bitmap and prepared mixed TrueType frames are physically checked.

For independent faces/sizes, provide an aligned font-reference arena, configure
NeonVkRetainedFontsConfigure and register already loaded slots with
NeonVkRetainedFontRegister(slot, role, pixelHeight). FontBytes computes storage;
registration returns zero on failure and FontError reports the reason. Controls
capture the registered handle through NeonRetainedFontSet. References retain slot
generation, role and pixel height. Reconfiguring the registry or replacing a
slot invalidates old references; the caller owns stable arenas and font bytes.
Legacy roles 0..3 retain active-face semantics. FontStatus validates a reference.
FontTextWidth/FontLineHeight provide its metrics; FontWarm prepares extra runs
outside a frame. ChromeFontSelect is the shared validated activation path.

NeonRetainedGadgetFontSet changes a live control's reference without recomputing
its geometry. Rebuild the collection if new metrics require different bounds.
It refuses stale controls, values below -1 and mutation during rendering.
A renderer callback may handle a refused mutation and return success: its last-
error diagnostic no longer silently truncates drawing. Actual negative renderer
results still stop drawing and reach the caller. Preparation already uses its
callback return values in the same way.

Two earlier mixed-font attempts reached the 15-second watchdog during repeated
font validation. The shared sfnt checksum loop now processes complete words with
portable byte loads, retaining every table checksum, final-word padding and the
head.checkSumAdjustment rule. All 539 checksum checks pass on the Pi. The same
workload takes 2,253,658 us with the original loop and 380,113 us with the new
loop (about 5.9 times faster). These are on-board counter measurements of this
checksum workload, not an overall renderer speedup. The public checksum builder
produces a byte-identical PMF to the physically checked program. UnoQ remains
compile-only for shared state/checksum proofs. A full retained canvas composition
on its no-device Chrome test still refuses missing NeonFrameBegin/End lifecycle
providers; no dummy provider or UnoQ GPU result is claimed.

## Verification

| Check | Physical result |
| --- | --- |
| Earlier shared CPU state/input/renderer proof | 101 assertions and 57 ordered drawing calls; x0=0, capture 378 |
| Current shared CPU state/input/renderer proof | 115 assertions and 57 ordered drawing calls; x0=0, capture 391 |
| Bitmap Vulkan controls, two frames | 65 draws each, 810/798 vertices; zero frame glyph work; x0=0, capture 370 |
| Independent pixel expectations | 56 interior probes and 20,224 pixels across 28 full text runs passed |
| Faster capture path | 8.6s versus 13.5s; capture 371; both complete 4,096,000-byte destinations match capture 370 by board SHA256 |
| Mixed TrueType controls | Two faces, four sizes, Unicode; 39 setup assertions, 65 draws/frame and 720/708 vertices; capture 379 |
| Independent TrueType pixel expectations | 56 geometry probes, 28 runs, 6,921 solid ink and 16,929 exterior pixels; both full attachment hashes match capture 375 |
| Current bitmap regression | Capture 380 returns x0=0; both full attachment hashes match capture 370 |
| Ownership after teardown |Old instance/device rejected through public calls; count sentinel unchanged; Chrome/Neon/external dispatch inactive; zero faults |

The CPU fixture checks callback rebuilding, copied text, stale handles, width
recentering, viewport mapping, slider/toggle/DIP/carousel state, capacity/text/
busy/provider refusals, the 64th DIP bit, derived overflow, 5,000 seconds of focus
and the largest finite elapsed value. Its independent numeric oracle validates
coordinates, sizes, RGBA, text leading bytes, polygon sides and unused bytes.
Its checker separately rejects 127 synthetic corruptions.

The GPU fixture changes slider/toggle/DIP/carousel values between two frames.
The pixel checker uses reference widget formulas and the independently read,
pinned 1,520-byte 8x16 font input. One-unit channel quantization is allowed. It
checks geometry interiors and complete text cells, not every frame pixel or
TrueType in this bitmap profile. Both attachment PNGs have also been visually inspected.

Capture originally used a byte loop and took 13.5s for the returning program.
The revised path poisons each whole destination, then copies aligned native
words. Schema 2 records 8,192,000 bytes poisoned and copied in total, 4,096,000
copied per frame. Whole-range SHA256 on the board proves both fresh destinations
exactly equal the earlier physical attachments. This lets the same independent
pixel checks apply to those exact bytes without re-streaming 8 MiB. The faster
verification path takes 8.6s under the 15-second deadman. It changes test readback,
not the production drawing algorithms. The current GPU checker rejects 89
synthetic invalid reports/inputs in a separate self-test.

Frame records require zero glyph raster/upload deltas, one pending/consumed
completed-frame token and no remaining pending frame. Post-teardown public calls to the
old device/instance return -20002; the enumeration sentinel remains 12345. This
checks parent invalidation and reported owner state, not every allocator registry.

## Reproduction and ranges

Use the unified compiler application through:

```
py tools/build_neon_retained_ui_proof.py --target pi4 --compiler <PureMetalForge.exe> --out <new-output>
py tools/build_neon_retained_ui_proof.py --target unoq --compiler <PureMetalForge.exe> --out <new-output>
py tools/build_neon_retained_ui_gpu_proof.py --compiler <PureMetalForge.exe> --out <new-output>
py tools/neon_retained_ui_gpu_proof_check.py --report <report.bin> --frame0 <frame0.bgra> --frame1 <frame1.bgra>
```

The builder compiles only; it never boots or emulates a board. It hashes the profile-specific literal
include graph before/after compilation and also records the canonical diagnostic
fingerprint (currently 67 bitmap or 69 mixed-font input records). Owner-relative includes are resolved
without directory enumeration. Linked code/BSS/stack/report, surface, GPU window,
two captures and explicit Neon arena are pairwise checked. The unused generic
CPU-proof heap annotation is omitted from this GPU profile. A live board map,
lease, range validation, verified upload and bounded deadman are still required.

The 4,096-byte report starts at E1C00000. The original 256-byte diagnostic is first;
the versioned scene record occupies 512 bytes at E1C00200. Two 4,096,000-byte BGRA
attachments start at 07000000 and 07400000, pitch 3200, extent 800x1280. These are
completed GPU image readbacks, not CPU drawing. The arena is 0A000000..0AFFFFFF;
it is explicitly checked against live reservations and is not an upload address.

Evidence: docs/evidence/neon-retained-ui-acceptance-20261027. The initial prompt
failure occurred before any upload/reset. A later bounded fresh console check
confirmed healthy 354; it was not evidence of a wedged or reset board. No reset
or firmware update was needed. Final prompt/cores are healthy, the resident
Vulkan console is selected and deadman is off.

Remaining work includes wider interactive/application acceptance, full no-device
canvas/lifecycle composition, optional CRT/postprocess and the rest of the engine/
Vulkan core, SPIRV, platform and recovery scope. Mandatory source publication
gates remain unaccepted. The overall port is not complete.

Those scene qualifications render to offscreen Vulkan attachments. Their frame
PNGs are decoded attachment readbacks; record.png is the monitor's return
screenshot. Their scope is state/input and offscreen bitmap/mixed TrueType
rendering. The later resident application/loop qualifications below cover DSI
presentation. Physical finger actuation and wider engine acceptance remain open.

The mixed-font oracle independently parses FontTools outlines and Latin GPOS,
then scan-converts with MuPDF. An 8x mask and 1/8-pixel halo exclude the documented
curve-approximation boundary; solid ink and distant exterior compare within one
channel value. A 1x reference had incorrectly classified a few edge pixels as
solid. Its original refusal is retained alongside the corrected reference result;
the production blend settings were not changed. The checker rejects 266 synthetic
corruptions, including an ink and exterior pixel in each of all 28 text runs.
Both complete physical attachments were visually inspected. See
`docs/evidence/neon-retained-truetype-20261027/` for the exact scope and artifacts.


## Application service bridge candidate

The hybrid-kernel contract keeps device drivers in Anvil and pure scene/UI code
in applications. The existing GPU diagnostics are separate hardware proofs;
they are not the application-side integration. The pure files
`Anvil/Hal/neon_service_api.pbi`, `neon_service_client.pbi` and
`neon_service_retained.pbi` now provide the candidate application boundary.
A single dispatcher exchanges sized request records, float32 coordinates and
integer status/handle/Q16 metric results. Open/Close and Begin/End/Abort track
ownership: failed presentation or cleanup retains its context, and failed Close
blocks further drawing. Callback-driven binding changes refuse while a call is
active. A rejected API replacement preserves the previous complete binding.

A controlled provider proof passes 82 assertions on actual Anvil 354/Pi4 and
compiles for UnoQ. Its independent oracle checks the operation ledger and exact
box/text/polygon/clear request values, including a retained label and button.
The oracle rejects 514 synthetic report corruptions. No device driver or Vulkan
backend is included in this client proof, and it does not present a UI.

The controlled-client qualification used Anvil 354/ABI 1.7, which correctly
refused before querying the proposed slot 38. Its historical evidence is in
`docs/evidence/neon-service-client-20261027/`.

## Resident application on Anvil 355

Anvil 355 implements console slot 38 at service ABI 1.8. Existing indices and
the 200-slot table retain their meanings. The pure contract now lives in
`Anvil/Hal/neon_service_api.pbi`; relocating it produces byte-identical complete
client proof containers for Pi4 and UnoQ. `graphics_service.pbi` owns common
registration and payload scope. Targets without a registered renderer return
ENOSYS instead of claiming a graphics device.

The Pi4 provider uses the existing resident Vulkan console resource owner.
It provides loaded-font references, metrics, prewarming, boxes, text, polygons
and checked frame lifetime. End validates the completed source, copies the full
frame to the inactive physical display buffer, waits for publication and then
consumes the source. Failed presentation retains ownership. Application return
captures the confirmed front buffer before checked owner cleanup and the
existing cache/DMA/console recovery. Failed cleanup latches ownership and the
Pi4 return path resets rather than reusing a potentially active bus master.

`Anvil/Graphics/Tests/neon_service_resident_app.pbi` includes only pure UI/math
and service binding. Two actual Pi4 runs pass 22 application checks, including
unsubmitted-frame abort, loaded font metrics and a retained label/button. Fresh
captures 382 and 383 pass independent shape/background/text checks. Contexts
advance from 1 to 2 even though the application intentionally leaves its owner
open for kernel cleanup. Both runs return zero and restore the Vulkan console;
the display reports zero timeouts and the core status is healthy. The same
application and UnoQ monitor build 84 compile, without claiming a UnoQ renderer.

This is the initial live resident application, not full Neon engine acceptance.
Physical input actuation, application font/asset loading, wider engine APIs and
broader Vulkan conformance/recovery work remain open. Source publication gates also
remain mandatory. Build using `tools/build_neon_service_resident_app.py` and
check returned report/display evidence with `tools/neon_service_resident_app_check.py`.

## Resident loop and touch adapter

`neon_service_touch.pbi` is a pure adapter over the existing Anvil touch service.
The portable 32-byte `AnvilTouchEvent` type and state constants now belong to
`Anvil/Hal/touch_event.pbi`; coordinates already describe the logical screen.
Bind flushes the previous screen's queued events before publishing callbacks.
Drain processes a bounded number of records per frame. One contact owns the
pointer until release/cancel; other IDs, unmatched releases and older contact
timestamps cannot produce a click. A press captures the topmost control's epoch
handle, so release on a different/rebuilt control or a press begun on the
background is cancelled. Cancellation clears touch hover without a release.

The shared controller now changes DIP switches and carousels on a fresh press,
while sliders retain held-pointer behavior. Topmost hit testing agrees with draw
order. The current controlled state/drawing proof passes 115 checks on Pi4,
including repeated holds and overlapping controls, and retains its 57 ordered
drawing packets. Earlier 101/106-check artifacts are historical snapshots.

`tools/build_neon_service_loop_app.py` builds a bounded 90-frame application.
It opens resident Vulkan, binds an already-loaded font, polls touch, prepares
text outside frames, animates a box and returns through kernel cleanup. It
injects no events by default. `--scripted` explicitly enables contact records
for cancellation, foreign IDs, an unmatched release, background-to-control
release and one valid button click that changes Start to Started.

Final actual Anvil 355/Pi4 captures 394 (scripted) and 395 (no injection) each
complete 90 physical End calls at 33,333 us intervals. Their measured frame work
averages 25,554 us and 26,336 us, with maxima 30,486 us and 30,158 us respectively;
this includes CPU preparation, GPU and display waits for this small UI. Fresh
display probes and label/button ink checks pass. No finger was on the panel:
real touch records are zero, so physical actuation is not claimed. Both restore
Vulkan with healthy core status, zero display timeouts and the deadman off.
The same loop compiles for UnoQ, Pi3 and RockPi4C; no execution there is claimed.

Pure HAL scope includes also make cleanup available in isolated boot/cache
compositions. The boot-container diagnostic compiles again; its file-handle reset
stub loudly reports an unexpected services path rather than simulating handles.
Normal Pi4 monitor 356 and UnoQ monitor 85 builds pass; they are compile-only
candidates in this phase, while the physical board remains on 355. Engine asset
and font loading, remaining input devices/APIs and broader Vulkan work remain.


## Resident sprite assets (graphics protocol 1.1)

Anvil 357 on Pi4 adds the SPRITES capability to the existing resident graphics
service. Service-table ABI 1.8, slot 38 and the 48-byte query prefix stay intact.
Basic vector/font clients still accept graphics protocol 1.0; a sprite client
requires protocol minor 1 and the advertised SPRITES flag. Include the HAL
contract, float32, neon_service_client.pbi and neon_service_sprite.pbi. The
application links no Vulkan driver.

SpriteLimitsGet reports 16 slots, dimensions up to 2048, a 16 MiB input limit
and 128 items per batch. Device-memory capacity can refuse smaller requests.
SpriteUpload takes a slot, bounded pixel pointer/byte count, width, height and
RGBA/BGRA selector. It copies tightly packed pixels before returning an opaque
positive handle; failure returns zero and leaves a detailed error. A successful
replacement invalidates the previous handle. Failed replacement preserves the
old texture. SpriteClear rejects stale handles. Upload/clear require an idle
frame; source pixels must lie within a current payload memory window.

Sprite draws use top-left coordinates, a centre rotation in radians, scale,
straight RGBA tint, integral source crop and an explicit camera bypass. Camera
sets translation and zoom. BatchBegin fixes a texture; BatchAdd uses explicit
window-space width/height and captures the current camera per item. BatchEnd
flushes in order. Immediate draws between additions precede that deferred flush.
Nested batches and End with an unfinished batch refuse. Abort or successful
checked Close retires the adapter batch metadata. A failed flush/cleanup retains
ownership for explicit recovery; it never silently frees an uncertain GPU owner.

Physical Pi4 capture 399 passes 182 application assertions and 4,806 interior
pixel checks across 534 squares. It covers all 16 slots, replacement/stale
handles, short and unsafe input refusal, empty/nested/unfinished batches,
Abort/Close/reopen, RGBA/BGRA copied input, crop, tint, alpha, quarter rotation,
camera and 128 ordered sprites. A backed 2048-square upload exceeds the device
heap and refuses; the final screenshot verifies the previous texture survived.
The monitor captures before scoped cleanup, then restores Vulkan with healthy
cores and zero display timeouts. The same pure application compiles for UnoQ;
no UnoQ GPU execution is claimed. A separate controlled client passes 50 checks
and an independent exact packet oracle on Pi4; 514 corrupted-report cases refuse.

Build with tools/build_neon_service_sprite_app.py and check with
tools/neon_service_sprite_app_check.py. The controlled counterparts use
build_neon_service_sprite_proof.py and neon_service_sprite_proof_check.py.
Raw pixels are implemented here. Encoded/file asset decoding through the pure
service, application font bytes, particles, remaining engine APIs and broader
Anvil Vulkan work remain open. Mandatory source-publication gates still apply.


## Encoded assets and file-handle client

The pure neon_sprite_decode.pbi module now owns the bounded RGBA/Windows BMP
algorithms used by both the native asset bridge and applications. BMP24 handles
bottom-up padded rows; BMP32 also handles top-down rows and straight alpha.
Color keys use $00BBGGRR and turn matches into transparent black. An optional
one-byte mask marks alpha greater than zero. Decode outputs and metadata belong
to the caller. The decoder checks dimensions, truncation, capacity, pointer
arithmetic and overlapping ranges before decoding. Dimensions publish only on
success. It supports uncompressed BMP24/32 up to 1024 square; PNG/JPEG, palettes,
RLE and bitfields are not implemented. Native LoadRGBA/Memory/File names remain;
their CPU decoding delegates to this shared owner.

neon_service_asset.pbi adds SpriteLoadRGBA, SpriteLoadMemory and SpriteLoadFile.
These decode into caller buffers, then upload through the resident sprite owner.
Only a successful resident upload publishes a new opaque texture handle. Input
and decoded bytes may be reused after return. The file form uses the independent
Anvil/Hal/file_service_client.pbi, which binds the existing ABI 1.4 slots
192..195. This is a reusable file client, with no hardware or graphics owner.
ReadWhole loops on partial reads, rejects zero progress and oversized counts,
and closes after size/read errors. A failed Close retains its handle and blocks
another ReadWhole; AnvilFileRetainedHandle identifies the explicit retry through
AnvilFileClose. Rebinding/unbinding while handles are owned refuses.

Physical Anvil 357 capture 401 reads 1:/NS24A.BMP from the Pi drive through actual
file services, decodes it, uploads it and presents it through resident Vulkan.
The owned 78-byte fixture was newly created, reloaded and full-SHA verified.
The application passes 133 checks, 40 independently checked decoded bytes,
10 mask bytes and 300 display pixels. Controlled file callbacks additionally
exercise partial reads, failed/positive Close, retained cleanup, reentry, EOF,
read errors and oversized counts. Malformed/truncated/capacity/overlap/overflow
images refuse. The application wipes source/decoded buffers before drawing.
The monitor restores Vulkan with healthy cores and zero display timeouts.
The same pure application compiles for UnoQ; no GPU execution there is claimed.
The oracle rejects 199 report/image corruptions. Build/check with
build_neon_service_asset_app.py and neon_service_asset_app_check.py.

This phase needs no monitor update beyond installed 357. Native compatibility
wrappers were refactored to delegate decoding. All three entry points also
compile with the complete Pi4 root when their addresses force emitted code;
no separate execution of their
HwFile-based path is claimed. Application font bytes and additional image formats,
particles, remaining engine APIs and broad Vulkan work remain unfinished.
Mandatory source publication gates continue to apply.


## Application font bytes (graphics protocol 1.2)

Anvil 358 adds the FONT_BYTES capability (bit 8) and graphics protocol minor 2.
Service-table ABI 1.8, slot 38, the 48-byte query and basic protocol 1.0 remain
compatible. Optional font load/unload operations append at 22/23; their request
records are 32/8 bytes. The pure neon_service_font.pbi client provides
FontLoadMemory, FontLoadFile and FontUnload. Load returns a positive font handle
or zero with a detailed error; source bytes are borrowed only during that call.
The file helper uses the separate pure file client and a caller-owned buffer.

Core's public AnvilFontLoadMemory copies a bounded TrueType face into an EMPTY
existing font buffer, validates it, and returns a generation token. Four command
slots each have a 1 MiB upper limit; preexisting faces reduce available capacity.
AnvilFontReleaseMemory accepts only a matching memory-owned generation. It cannot
release a file-loaded or subsequently replaced face. The boot slot is excluded.
A final generation increment is reserved for unload. No extra font-sized BSS
allocation, caller memory pointer or independent parser owner is introduced.

The resident service chooses a free slot and binds its generation/role/size.
Loads and explicit unloads require idle frames. Out-of-payload source pointers,
invalid byte counts/roles/sizes and malformed fonts refuse. Full capacity refuses
without replacing a preexisting face. After successful GPU/device teardown,
Close restores the prior selected parser face and releases only application-owned
generations. Failed teardown, restore or release retains the context and any
remaining owned generations for explicit recovery. Explicit unload also restores
the prior face if the owned face is selected. References to retired generations
refuse; prewarm runs before Begin as for existing font references.

Physical Pi4 build 358 capture 403 passes 53 checks. The test reads the existing
2:/fonts/Lato-Regular.ttf (656,568 bytes), with its original slot 0 loaded and
selected. It fills only the three empty slots, tests capacity/format/unsafe
source refusals, erases its entire 1 MiB input buffer, measures and renders from
copied bytes, unloads a selected face, rejects stale references, reloads it,
closes/reopens and fills all three slots again. The application raster exactly
matches the independent preexisting Lato raster (2,117 ink pixels each) and differs
from the embedded boot face (3,899 ink pixels; 4,558 different pixels). Return
cleanup leaves slots 1..3 empty and preserves slot 0's 656,568 bytes, generation 1,
selection and path. Vulkan restores with healthy cores and zero display timeouts.
The same pure application and the shared Core changes compile for UnoQ (monitor
86); execution is only claimed on Pi4. The oracle rejects 63 ledger/image faults.

Use tools/build_neon_service_font_app.py and neon_service_font_app_check.py.
This proves owned TrueType loading for the tested file, not every font format or
full engine acceptance. Additional image formats, particles, remaining engine
APIs/input and broader Vulkan conformance/recovery remain open, along with the
mandatory source publication gates.


## Resident float32 particle batches (graphics protocol 1.3)

Anvil 359 adds PARTICLES bit 16 and protocol minor 3, preserving service ABI
1.8, slot 38 and existing records. Operations 24/25/26 query limits, prepare a
list and draw its prepared snapshot. Limit/prepare packets are 24 bytes. Inputs
are caller-owned 32-byte records: centre X/Y, size, radians and RGBA as float32.
The pure neon_particle_list.pbi supplies bounded Configure/Clear/Add over caller
memory; neon_service_particles.pbi sends the list without linking a driver.
Limits report 10,000 records and eight fractional coordinate bits. Colour inputs
are finite in 0..1. Centres are bounded to +/-20,000, size to (0,4096],
radians to +/-100.53, camera translation to +/-16,384 and zoom to (0,16].
Transformed Q8 corners must stay within +/-1,500,000 Q8 units. These bounds
refuse before publication.

Preparation runs outside a frame, copies the colour/geometry snapshot into the
existing resident owner and uploads its ordered palette. The source can then be
reused. DrawPrepared runs inside a frame and uses one ordered native draw for
the list. A changed camera refuses stale geometry; preparing again is required
for a different current camera. Empty snapshots draw nothing. Bad pointers,
counts, truncated arrays and NaN records refuse. Close and returning-scope cleanup
retire the same checked resource owner used by all other resident rendering.

The new float path preserves fractional centres, sizes and camera coordinates
until final Q8 corners. It shares validation, palette creation/upload/reuse and
publication with the existing native integer/Q16 API; that API keeps its record
layout and wrapper. Separate integer external producers cannot consume a float
snapshot. No second driver or 800 KiB duplicate kernel input array is added.
The native route renders coloured quads. This is not a new claim of circular
fragment effects or general instanced-shader conformance.

Physical build 359 established a 39,404 us warm preparation baseline for 10,000
records. Build 360 adds portable MathFToI32 with existing Int()'s symmetric
+/-2147483647 saturation and NaN-zero policy, and hoists frame-wide constants.
The unchanged full-width software reference remains in place. The new function
passes 67,584 real Pi4 comparisons and 32 independently pinned host patterns,
including signed zeros, subnormals, bounds, infinities and NaNs. Its first draft
used the conventional negative endpoint; comparison caught that mismatch and
only the new helper was corrected to the existing project policy.

Final Pi4 capture 409 checks all 1,024,000 pixels of the 10,000-quad image and
39 application assertions. The complete application PMF is byte-identical to the
baseline. Warm preparation falls to 13,956 us (about 2.8 times faster); first
preparation is 14,535 us, draw construction 4,954 us and the prepared frame
including GPU/display waits 28,946 us. List building adds 7,113 us. Thus a fully
rebuilt dynamic 10,000-particle frame is roughly 50 ms in this test, not a 30/60
FPS claim. Preparation and presentation remain optimization targets.

Capture 410 passes 58 checks and 113,222 independent screen samples for fractional
camera placement, rotation, ordered alpha, clipping and a harmless degenerate
particle. Source records are erased before drawing. Warm preparation is 13,988 us
and the mixed list prepares in 451 us. Both final images were visually inspected;
return cleanup preserves the existing Lato font and restores Vulkan with healthy
cores and zero display timeouts. The pure mixed app and conversion proof compile
for UnoQ; execution is only claimed on Pi4. Oracles reject 48 dense, 67 mixed and
69 conversion report/image mutations. Use build_neon_service_particle_app.py,
neon_service_particle_app_check.py, build_float32_convert_proof.py and
float32_convert_proof_check.py. Additional image formats, effects, engine APIs
and broad Vulkan completion/publication are still open.

## Resident virtual canvas, clipping and mapped drawing

Graphics protocol 1.4 adds MAPPING bit 32 and operations 27..33. The original
48-byte query, 40-byte surface, service ABI 1.8 and slot 38 remain unchanged.
Canvas(width,height) accepts 1..8192 while idle, resets the camera and invalidates
prepared particle readiness. Width/Height still report the logical target size.
ScissorSet/Clear operate during a frame, in virtual-canvas coordinates, ignoring
the camera. Set replaces the current rectangle; it is not a push/pop stack.
Empty or negative spans clip everything. Begin clears an earlier frame's clip.

The optional pure neon_service_mapping.pbi adds BoxMapped, PolygonMapped and
TextMapped with explicit 0/1 Scaled and IgnoreCamera flags, plus immediate
StaticLines over borrowed interleaved float32 XY pairs. Static lines always use
the virtual canvas and ignore the camera, matching DrawGLStaticLines. They accept
up to 262144 vertices; a positive limit restricts drawing and an unmatched last
vertex is ignored. The provider validates the complete declared source span,
alignment and finite bounded coordinates before entering the native line path.
No persistent mesh handle or extra renderer is introduced. Mapped text accepts
the existing font roles and registered owned/preexisting face references.

Anvil 361 physically passes capture 413: 59 application assertions, 44564
independent raster samples, a 250-pixel static line and matching camera/virtual
text runs (1620 ink pixels each). Replaced scissors yield matching clipped text
runs with 1024 ink pixels, and no ink escapes either rectangle. The scene combines
world polygons, both coordinate spaces, clipped sprites, text and vector drawing.
It checks malformed sizes, flags, NaN/infinity, unsafe/truncated line sources,
phase and active-batch refusals, particle invalidation and Abort/reopen behavior.
The Pi returns successfully in 1.6 host seconds; this is not a frame-rate metric.
The final PNG was visually inspected. All cores remain healthy, Vulkan is restored,
DSI timeouts stay zero, and the existing Lato font is preserved. The same final
application compiles for UnoQ; execution is only claimed on Pi4.

Use build_neon_service_mapping_app.py and neon_service_mapping_app_check.py.
The first scene refused an invalid zero-sized sprite crop; its failure remains
recorded. The corrected scene uses the existing whole-image sentinel. A separate
host-ledger indexing mistake was corrected against the explicit application
sequence; the successful 412 capture is preserved without rerunning it solely
for that oracle correction. Final 413 includes additional real text-clip/world
polygon checks. Full engine API/effects/format coverage and broader Vulkan
conformance, recovery and source publication remain unfinished.

## Immediate chrome scrollbars

Anvil/Graphics/neon_chrome_scroll.pbi supplies the desktop chrome layer's
vertical/horizontal scrollbar behavior separately from the retained widgets.
Its renderer-neutral CPU state owns no device or frame. One explicitly installed
typed box renderer is shared by the application; caller-owned 80-byte state
records separate input and drag ownership for different UI contexts. Initialize
records to zero, Configure(scale), and call Input once per input frame with
virtual-canvas coordinates and held mouse/touch state. Use stable nonzero IDs
unique within a context. The renderer and input calls are serialized.

NeonServiceChromeScrollInstall binds the existing resident Box service after
Open. Drawing BarV/BarH belongs inside the caller's frame; a negative result
requires frame abort. Their return is 1 for a changed active offset, 0 otherwise,
or a negative refusal. Pass an aligned native-width .i offset address. The
inert case resets its offset to zero and returns 0, matching desktop semantics.
Counts accept 0..2147483647; dimensions are greater than 4 and at most 8192 canvas
units; scale is (0,64]. These bounded APIs do not claim every desktop input size.

Thumb press retains the grab point; holding moves it continuously and clamps at
either end. Clicking the track pages by Visible once per press, while holding
does not repeat. An inert bar releases only its own drag. Input release clears
the owner even if that widget is omitted. A minimum thumb is capped to the track,
so a short bar cannot draw outside itself. Background/thumb draw failures retain
the prior offset and drag owner; unexpected positive renderer status is refused.
Renderer callbacks cannot reenter input, configure another context or replace
the renderer mid-draw. Public getters remain available during rendering.

Physical Anvil 361 capture 416 passes 90 assertions, two exact callback packets
and an exact comparison of all 1024000 image pixels. Scripted input checks vertical
and horizontal dragging, page edges, held presses, clipping, inert owners, clamped
and short tracks, invalid values, renderer failure/retry and callback reentry.
The final GPU frame contains vertical, horizontal and inert bars, with the first
bar clipped by the resident scissor and a short track checked for escaped thumb pixels. All cores remain healthy, Vulkan is restored,
DSI timeouts stay zero and the original Lato font is preserved. No firmware
update or reset was needed. The same final application compiles for UnoQ; no
execution there. This scripted qualification is not a physical-finger or FPS claim.

Use build_neon_chrome_scroll_app.py and neon_chrome_scroll_app_check.py. The
oracle rejects 216 report/callback/image mutations. The initial 414 run passed
87 checks; 415 adds cross-context and renderer-install reentry checks; final 416
adds the actual short-track raster, whose bounds were not proven by its earlier
state-only assertion.
Full chrome menus, tabs, text entry, animation/theme integration, additional
formats/effects and broad Vulkan completion/publication remain open.

## Prepared chrome menus and submenus

Anvil/Graphics/neon_chrome_menu.pbi supplies copied, bounded menu models and
renderer-neutral input/layout/drawing. The resident adapter installs the existing
Box/Text/metrics/Prepare/scissor callbacks. There is no new driver, service ABI or
firmware requirement beyond graphics protocol 1.4. This is a target-specific
application API adaptation of the desktop chrome behavior: model construction
and glyph preparation happen before the frame, rather than lazy font upload
inside an immediate-mode draw. Current root geometry is complete before input,
so a root transfer cannot paint both the old and new drop-down.

Configure zeroed caller-owned state with an aligned arena, node capacity,
per-label/per-shortcut UTF8 byte budget, canvas, scale and two font references.
RequiredBytes = capacity * (88 + 2 * textBytes) on the current 64-bit targets.
Limits are 1..1024 nodes, 1..512 bytes per text including NUL, 32 roots and one
submenu level, matching the desktop submenu-depth policy. Canvas bounds are
32..8192 and scale (0,16]; enough vertical space must remain for arrow strips.
AddRoot/AddSubmenu/AddItem/AddSeparator copy strings; IDs are positive and unique
except separators. Parents must already exist. Deeper submenus, duplicate IDs,
capacity/text exhaustion and malformed geometry refuse before node publication.

Seal measures all rows and warms all captions, shortcuts and arrows outside the
frame. Failure leaves the model unready; Draw refuses that incomplete model.
There are no measurement or preparation callbacks in Draw. BeginBuild permits
reconstruction and retains matching open root/submenu IDs and scroll positions;
missing or reparented owners close. ItemState changes enabled/checked flags
without requiring new glyph preparation. Get returns borrowed read-only node
metadata valid only until mutation. Use the same canvas as the resident service.

Input takes virtual coordinates, held down state, wheel and Escape before Draw.
Root clicks toggle, moving along an open bar transfers ownership, enabled item
presses emit their ID once and close the menu, and disabled rows never activate.
EventGet consumes the single pending ID. Checked rows use seven-column geometry;
shortcuts are display labels, with application keyboard bindings remaining the
host's responsibility. Submenus open on hover, flip left at the right edge and
shift upward near the bottom. Long panels clip their rows and support wheel and
hover-arrow scrolling. NeedsRedraw requests another pass while scrolling moves.
BlocksMouse is latched for the input frame, including an outside dismissal or
item selection, so that closing the menu does not pass the same click underneath.

Draw belongs inside the caller-owned frame and clears its scissor on exit.
It draws the bar, the selected root and its selected submenu in that order,
escaping the parent clip for the child. It does not restore a caller's old clip.
After any negative draw result, abort the caller's frame. Logical selection stays
available for retry. Cleanup is still attempted after a renderer refusal; the
state's cleanupError records a refused final clear. Public input/model mutation
and renderer replacement refuse callback reentry, including another context.
The initial desktop palette and glow/check geometry are present; shared theme
and animation controls remain separate unfinished integration work.

Physical Anvil 361 captures 417/418/419 pass 95/95/96 assertions respectively.
Each validates 49 exact 80-byte callback records: operation/font, float geometry
and RGBA, text length and leading eight UTF8 bytes. Native scenes check 51/83/52
geometry probes and each compares a 6720-pixel menu label cell with independently
issued resident text (one channel-unit tolerance). They show normal root/submenu,
a scrolled 40-item panel and a right-edge submenu flipped left. Tick geometry,
disabled text colour/ink and fresh root ownership are checked. The CPU path also
checks near-bottom submenu placement, copied labels, dismissals, failure/retry,
metrics-free drawing and callback refusal. All final PNGs were visually inspected.
These are scripted-input qualifications, not physical-finger or frame-rate claims.

All three runs return zero in 1.4..1.5 host seconds, preserve the original Lato
font, restore Vulkan with healthy cores and zero display timeouts, and leave the
deadman off. No firmware update or reset was required. The shared edge application
compiles for UnoQ; execution is only claimed on Pi4. The oracles reject 912/912/914
report/callback/image mutations. In the scroll scene, unused Open/shortcut metric
fields are checked for valid bounds rather than an arbitrary diagnostic value.
Use build_neon_chrome_menu_app.py --scene menu|scroll|edge and
neon_chrome_menu_app_check.py. Full theme/animation integration,
additional formats/effects and broad Vulkan completion/publication remain open.


Prepared tab strips
-------------------

Graphics/neon_chrome_tabs.pbi is renderer-neutral; install the resident callbacks
with NeonServiceChromeTabsInstall after Open. It requires no new firmware or ABI.
Configure zeroed caller-owned state, aligned arena, geometry, scale and UI/Small
font references; an optional alternate font reference represents italic style.
RequiredBytes is capacity * (88 + 2 * textBytes) + 16 on current 64-bit targets.
Capacity is 1..1024, textBytes 4..512 including NUL, width/height at most 8192,
height greater than 1 and scale (0,16]. IDs are positive and unique. Add copies
literal UTF8 labels, including bars; there is no delimiter-encoded label list.
Pinned tabs reserve their close space but emit pin events rather than close.

Seal measures and prepares glyphs outside the caller-owned frame. Failure leaves
the strip unready. Oversized labels use a copied tail (default ASCII "...", at
most 15 bytes); no automatic font-glyph query chooses a Unicode ellipsis. Fitting
preserves UTF8 scalar boundaries and limited combining/variation/ZWJ joins, not
full Unicode grapheme segmentation. Invalid UTF8 or impossible geometry refuses.
Draw has no metric/preparation calls. BeginBuild retains selection and scroll;
Seal clears a removed selection and clamps scroll to the rebuilt row.

Input receives virtual coordinates, held press state, wheel, blocked flag and
delta time. TabAt returns a stable ID or zero, excluding arrow strips and the
bottom hairline. CloseGet/PinGet report this input's event ID: consume before the
next Input, which resets them. The host implements closing and dirty prompts.
Selection can reveal its tab, including the initial selected ID. Wheel advances
one tab per notch (bounded to eight); arrow presses reveal adjacent clipped tabs.
Hover and active-indicator easing use shared math and NeedsRedraw until settled.
Draw clears scissor on exit rather than restoring the caller's prior clip. Abort
the caller's frame after a negative result; logical state remains retryable and
cleanupError records a refused final clear. Mutation/renderer replacement refuses
callback reentry, including another context. The initial palette is fixed;
shared theme integration remains open.

Physical Anvil 361 captures 420/421 pass 93 assertions each and 17 exact 128-byte
callback records, including complete text fields. Basic/overflow scenes check
8/6 geometry probes and 3328/11544 reference-cell pixels within one channel unit.
Both PNGs were inspected. CPU checks cover copied labels, pin/close/selection,
clipped hits, wheel/left-arrow behavior, reveal, easing, failure/retry, metrics-free
Draw and callback refusal. The alternate font dispatch is tested; the physical
scene uses Lato-Regular for all roles, so no distinct italic-face claim is made.
Native overflow shows a left arrow; a separate native right-arrow scene and
exhaustive Unicode grapheme coverage are not claimed. Scripted input is not a
physical-finger or frame-rate qualification.

Each run returns zero in 1.5 host seconds, preserves Lato slot zero, restores
Vulkan with healthy cores and zero display timeouts, and leaves the deadman off.
No reset or firmware update was needed. UnoQ compiles only. The independent
checker rejects 2401 report/callback/image corruptions per scene; descriptive
fields are bounded, not all pinned to arbitrary values. Use
build_neon_chrome_tabs_app.py --scene basic|overflow and
neon_chrome_tabs_app_check.py. Themes, remaining effects/formats and
combined real-engine acceptance remain unfinished, as does broader Anvil Vulkan.


Single-line text entry
----------------------

Graphics/neon_chrome_edit.pbi provides the desktop field's single-line editing
behavior through an explicit input record and prepared renderer. Install
NeonServiceChromeEditInstall after resident Open. There is no new provider, ABI
or firmware requirement. Configure zeroed state, an aligned caller arena and
NeonChromeEditConfig (56 bytes): unique positive ID, font, copied initial text and
placeholder, geometry and scale. RequiredBytes is capacity * 5; capacity is
4..4096 UTF8 bytes including NUL. Width/height are greater than 2 and at most
8192; scale is (0,16]. The five buffers hold text, placeholder, edit work, paste
work and clipboard output. Public getters return borrowed read-only pointers;
do not mutate state or buffers directly. SetText copies external text and rejects
aliases into its state/arena. Config strings must not alias the destination.

Focus is one shared ID, matching the desktop chrome ownership model. The host
must use distinct IDs, dispatch the same pointer state to participating fields,
and consume keyUsed/charUsed before forwarding a key to another field. Input
(72-byte record) supplies virtual pointer coordinates, held down, blocked, key,
Ctrl, Unicode scalar, external paste pointer/budget and delta time. Translate
host key codes to NCE_BACK/DELETE/LEFT/RIGHT/HOME/END/RETURN/ESCAPE/A/C/X/V.
Press edges focus/dismiss; held movement does not refocus. Blocked input cannot
edit. Caret is a UTF8 byte offset on a scalar boundary; left/right/back/delete
move or erase one scalar, not a full grapheme. There is no partial-range selection
or IME integration: select-all matches the desktop field. Ctrl+A selects all;
printable text replaces it, and Back/Delete remove it. Return emits submitted;
Escape blurs. No horizontal scroll is added: long text/caret are clipped as in
the desktop field. Clipboard OS access remains the host's responsibility.

Ctrl+C copies the whole field; Ctrl+X cuts only when all is selected. A borrowed
clipboard string and clipboardEvent (1 copy, 2 cut) let the host update its actual
clipboard. Ctrl+V receives a bounded NUL-terminated UTF8 string (budget 1..65536),
uses its first line and normalizes tabs to spaces. The complete supplied string
must validate as UTF8, including its discarded tail. Other C0/DEL controls before
the line break refuse. Initial text/SetText/placeholder must be single-line text.
Capacity or text refusal preserves the published text/caret/selection; scratch
may change. Successful Input resets submitted/changed/clipboardEvent/keyUsed/
charUsed, so consume these outputs immediately. Invalid event records return
before that reset. SetText/Caret and edits invalidate prepared metrics.

Seal prepares text/placeholder and caches height, text width and caret-prefix
width before Begin. Failure leaves the field unready. Draw measures/prepares
nothing and belongs inside the caller-owned frame. Input advances the blink
clock with delta time clamped to 0.05 seconds; NeedsRedraw remains true while
focused, and otherwise clears after a successful draw until state/hover changes.
The default desktop background, frame, text, faint and accent colours are used;
shared theme configuration remains unfinished. Draw clears scissor on entry and
exit, rather than restoring a previous clip. Abort the caller's frame after a
negative result. Cleanup is attempted, cleanupError retains its result, and
logical text stays available for retry. Renderer/model/input mutation refuses
callback reentry, including another context. Clipboard, keyboard and text input
transport are host integration responsibilities, not implicit device polling.

Physical Anvil361 captures 423/424 pass 119 assertions each and 11 exact 128-byte
callback records with complete text. Both scenes compare 80240 field/reference
pixels within one channel unit plus seven geometry probes. Focus/caret, unfocused
placeholder, long-text clipping and native selection highlight were rendered;
both PNGs were visually inspected. Scripted checks cover copied/erased sources,
multibyte insertion/movement/deletion, invalid scalar/boundary/UTF8, select-all,
copy/cut/first-line paste, atomic capacity refusal, blocked input, held edges,
submit/blur, preparation failure and renderer/busy/cleanup failure retry. Native
keyboard, IME, full grapheme editing and physical-finger acceptance are not claimed.
The earlier capture422 passed its initial108-check fixture before the copied-text
and capacity assertions, selection scene and exact default palette were added.

Final runs return zero in 1.3/1.4 host seconds, preserve Lato slot zero, restore
Vulkan with healthy cores/zero display timeouts and leave deadman off. No firmware
update/reset/storage/Bluetooth operation. The same selection fixture compiles for
UnoQ; execution is only claimed on Pi4. The independent oracle rejects 1675
report/callback/image corruptions per scene. Native height is checked for valid
bounds rather than pinned to a diagnostic constant. Use
build_neon_chrome_edit_app.py --scene basic|selection and
neon_chrome_edit_app_check.py. Combined engine input/application, themes, remaining
chrome/effects/formats and broader Anvil Vulkan completion/publication remain open.


Prepared list/tree panes and split scroll phases
-----------------------------------------------

Graphics/neon_chrome_list.pbi ports the desktop list pane to a prepared model.
The application supplies the visible, flattened tree rows, expansion policy,
selection flags and stable positive row IDs. Group rows use heading colours and
still emit click IDs; there is no hidden filesystem traversal or automatic tree
expansion. Labels, depth indentation, selected accent bars, hover easing,
right-aligned details, partial-row clipping, wheel and draggable scrollbar are
provided. The label gets available width first; the detail fits only the space
left after the label and its gap. Model construction, fitting, measurement and
glyph preparation happen before the frame. Current row count is known at Seal,
so the port does not need the desktop immediate pane's previous-frame count.

Configure zeroed caller state, aligned arena and NeonChromeListConfig (56 bytes).
Rows are 112 bytes; RequiredBytes = capacity * (112 + 4 * textBytes) + 16 on current
64-bit targets. Capacity is 1..4096 rows and textBytes 4..512 including NUL.
List ID is 1..2146583647, giving its scrollbar ID +900000 a valid range. Host IDs
must be distinct across the shared scroll UI. Width is greater than 24*scale and
at most 8192; height is greater than 4 and at most 8192; row height is 1..height;
scale is (0.4,16]. The caller supplies a configured shared NeonChromeScrollState
with matching scale. The minimum scale reflects the shared scrollbar's track
geometry bounds. Input coordinates must use the same virtual canvas.

Add copies labels/details, depth 0..4096 and selected/group booleans. Positive
row IDs must be unique. Text/source capacity and aliases into the destination
state/arena refuse before publishing a row. Get returns borrowed read-only row
metadata. ItemState changes selection/group flags without remeasuring. Multiple
selected rows are permitted, matching the desktop call's per-row Selected flag.
BeginBuild clears rows/events/hover while retaining top; successful Seal clamps
top for the new collection. ScrollTo also clamps. A failed Seal leaves unready
state. A copied tail defaults to ASCII three dots (at most 15 bytes); fitting
uses valid UTF8 scalar boundaries and the shared limited joining ranges, not
full Unicode grapheme segmentation or automatic font-glyph ellipsis selection.

Call NeonChromeScrollInput exactly once per UI frame, then each participating
ListInput before Begin. Wheel moves three rows per notch; accepted range is
-128..128. wheelRemaining reports whether that pane consumed it. A blocked pane
does not edit top or emit row events. Shared release still clears drag ownership
even when a widget is omitted or blocked. ListAt returns a stable ID or zero,
excluding the scrollbar and outside clip; partial visible rows can be clicked.
Input's single event ID is reset each successful Input; EventGet consumes it.
The application applies selection/expansion. Hover easing runs at speed20 with
delta clamped to0.05; NeedsRedraw stays true until it settles. Draw has no text
metrics/preparation calls and does not change top or drag ownership.

The shared neon_chrome_scroll.pbi now exposes UpdateV/H and PaintV/H. Update
performs the existing layout/input calculation and commits offset/drag without
any renderer calls. Paint performs rendering without committing offset/drag.
The original BarV/H retain their combined behavior and renderer-failure atomicity.
Feed shared input once, update outside the frame, paint inside it. The list's
renderer install also installs its box bridge for this shared scrollbar family;
renderer families and callers are serialized. Paint requires inputReady and a
renderer; Update does not need a renderer. A direct Paint clamps its visual
position for invalid supplied offsets without publishing that clamp.

List Draw uses the caller's frame, clears scissor on entry/row completion/exit,
and paints the scrollbar after leaving the row clip. It does not restore an old
caller clip. Abort the caller frame after any negative result. Logical model and
already-applied input stay available for retry; cleanupError records the final
clear result. Model/input/renderer mutation refuses callback reentry, including
another list. Default desktop palette is provided; shared theme controls and
host hot-zone/input composition remain separate unfinished integration work.

Physical Anvil361 captures427/428 pass103 assertions each, fifteen exact128-byte
callback records including complete text,85000 pane/reference pixels within one
channel unit and seven geometry probes. Basic and scrolled scenes were inspected.
The CPU path verifies copied/erased labels, invalid UTF8/depth/duplicate IDs,
label-priority/detail fitting, partial-row hit exclusion of the scrollbar,
click/held/blocked/wheel events, top clamping/rebuild, track page/drag/release,
no draw calls during update, unchanged top/drag during paint, split horizontal
refusal atomicity, hover redraw settling, state flags and prep/render/busy/cleanup
failure retry. Reference rendering independently composes row geometry and style
but reuses the prepared fitted strings/widths; the fake-metric trace separately
pins fitting. Native height/label width are bounded diagnostics, not fixed values.
The verifier rejects2152 report/callback/image mutations per scene.

Shared scrollbar regression capture426 passes the unchanged90-check fixture,
two exact callback packets and the entire1024000-pixel expected raster. Historical
capture425 passed the earlier95-check list fixture before the redraw-settling
assertions were added; current final checker is for427/428. Final list runs return
zero in1.4hostseconds; scrollbar regression1.3seconds. Healthy cores, restored
Vulkan, zero display timeouts, preserved Lato and deadmanoff after each run.
No firmware update/reset/storage/Bluetooth operation. Same final scrolled list
compiles for UnoQ; execution is only claimed on Pi4. No physical-finger, native
keyboard, full grapheme or frame-rate claim. Use build_neon_chrome_list_app.py
--scene basic|scrolled and neon_chrome_list_app_check.py. Combined real-engine
application/input, themes and remaining effects/formats/math/collision and broader
Anvil Vulkan completion/publication remain unfinished.


Composed resident application and shared pointer ownership
---------------------------------------------------------

Graphics/Tests/neon_service_composed_app.pbi combines the resident components in
one returning 90-frame application: menus, tabs, single-line text entry, list
pane, retained button/toggle/slider, two sprite batch entries, 32 particles and
static lines. The running preview responds to Pause, Speed and the particle
toggle/menu item. Tab and list selection are represented by their own models.
Closing a tab rebuilds the copied tab model; pinned tabs emit a separate event.
This is an integration application and qualification fixture, not a replacement
for a complete downstream game or proof of every remaining engine feature.

Build with tools/build_neon_service_composed_app.py --target pi4 --compiler EXE
--out NEW. Default mode polls real touch without injecting input. --scripted
adds explicitly labelled touch records, wheel and Unicode editing calls while
still polling the device. The deterministic checker expects no concurrent real
touch records; it never presents scripted events as physical finger actuation.
The builder follows only literal includes from the named entry and pins every
compiled dependency. It does not enumerate directories. UnoQ compiles the same
scripted source; no UnoQ graphics/input execution is claimed.

Graphics/neon_pointer.pbi is now the common single-contact tracker. Configure
zeroed aligned NeonPointerState with source logical-screen and virtual-canvas
sizes in1..8192. Its current64-bit layout is104bytes. Feed accepts the portable
32-byte AnvilTouchEvent, maps coordinates once and exposes down/pressed/released/
cancelled/changed plus the active ID and timestamp. One contact owns the pointer;
foreign releases, repeated downs and older moves/releases/per-contact cancels do
not steal it or create a click. Cancel ID-1 is unconditional cancellation.
Validation rejects malformed state/pressure/reserved data, negative timestamps,
negative/nonbounded coordinates and derived positions outside +/-1000000.
A new press establishes its own timestamp baseline. Invalid Feed returns before
resetting prior edge outputs: ignore those outputs on failure. Idle clears only
edge/changed outputs, retaining held position. Process each accepted event before
polling another, so a down/up pair drained in one frame cannot lose its click.

neon_service_pointer.pbi binds the existing poll/flush service slots, flushes the
new queue before publishing its binding and has one active consumer. Poll from a
superseded/unbound state refuses instead of consuming another screen's queue.
Rebinding while a contact is held refuses. Candidate configuration remains local
until flush succeeds, preserving the old state/binding on failure. Poll returns
0 for no raw record,1 for a record (changed can still be0 for an ignored contact),
or a negative error. Malformed provider replies cancel the held pointer. Unbind
cancels and removes the binding. State storage must remain alive while bound.
No controller/bus/display implementation is copied into the client.

The compatibility neon_service_touch.pbi now delegates tracking and transport to
this owner, retaining its public retained-only API and epoch capture policy.
Identity mapping preserves its logical-screen coordinates and its historical
error families. Stale per-contact cancellation and negative timestamps now follow
the common validation policy. It clears touch hover after a valid release and
never converts cancellation/background-to-control/outside release into a click.
The compatibility builder now pins its new literal dependencies as well.

The composed application's host router chooses an owner on press, processes the
menu first and keeps its dismissal mask for the held contact. Retained releases
must match their captured epoch handle; a background press cannot release onto a
button. The router passes normalized virtual coordinates to widgets, with a
matching retained viewport. Glyph preparation remains outside Begin. Sprite
batches and particle records use target/window coordinates, so the application
explicitly converts its preview geometry; virtual boxes/scissors/static lines use
the canvas APIs. Batch sprite positions are top-left with centre rotation, while
particle records carry centres. These are existing desktop-compatible contracts.
The source RGBA upload buffer is erased after upload and its texture is explicitly
cleared after the final retired frame. Pointer transport is explicitly unbound;
the kernel captures the final attachment before scope cleanup restores its owner.

Final Anvil361 captures434(scripted)/435(no injection) each complete90 actual End
calls and43 pinned pointer/transport assertions. Every frame's tab/top/run/menu
state is checked against the input schedule. Ten last-frame retained box records
pin geometry/RGBA/padding; focused glow alpha is finite/bounded rather than fixed
to an arbitrary diagnostic. Per-frame input/preparation/recording/submit-present
and total intervals have independent consistency checks. Native integration
checks include26/27 geometry/particle probes, primary sprite placement/colour
counts,2151 static-line pixels and surviving list/editor ink. These are selective
integration probes, not a full-image oracle for the animated composition. Both
PNGs were inspected. The checker rejects1674 report/trace/timing/image mutations
per mode. Independent component raster proofs remain separate evidence.

Final timing, including synchronization waits:

| Mode | Input mean | Prepare mean | Command recording mean | Submit/present mean | Total mean | Total maximum |
| --- | --- | --- | --- | --- | --- | --- |
| Scripted434 |553us|141us|2795us|28425us|31914us|33347us|
| No injection435 |537us|134us|2724us|28519us|31914us|33429us|

Measured pacing is30.0001/29.9993FPS. Each first frame exceeds the33333us budget by
14/96us; each remaining89-frame maximum is33295us, with no later misses. The
strict all-frames deadline flag is therefore false in both reports. Submit/present
includes GPU execution and display synchronization; it is not a GPU-only or CPU
occupancy measurement. Earlier22ms/31ms aggregate variation suggests presentation
phase effects, not an established change in widget CPU cost. No extra workload
headroom,60FPS, physical actuation or live keyboard transport is claimed.

Compatibility regression capture433 passes the unchanged retained-loop checker:
90 actual End calls, one explicitly injected valid click, rejected cancellation/
foreign/background/outside sequences, six display probes and label/button ink.
It reports zero real touch records and25754us mean/27171us maximum frame work.
All final/compatibility runs return zero, restore Vulkan with healthy cores/zero
display timeouts, preserve original Lato and leave deadmanoff. No firmware update,
reset, storage or Bluetooth operation was required.

Historical429 caught an application coordinate-contract mistake and an incorrect
menu probe; no native renderer defect was established. Historical430 passes its
preserved verifier after correcting the minimum90-frame duration to90*33333us,
rather than exactly3000000us. Historical431/432 qualify functional controls before
the final recording/present split. Original reports/checks remain unchanged and
later verifier reviews have their own files. Compiler refusals for multi-value
Case, an untyped local function pointer and a conservative callback cycle were
resolved before upload; no recursion or compiler-policy bypass was added.

Shared themes/animation controls, live keyboard transport, remaining formats/
effects/math/collision, broader target/runtime/physical-input qualification and
Anvil Vulkan types/SPIRV/formats/WSI/recovery/publication remain open. This combined
application is progress toward full Neon parity, not full Neon/Vulkan completion.


The checkpoint's measured progress is published in the existing [Anvil graphics
service topic](https://forum.ajtaji.com/post/4024), which remains open. It explicitly
labels this as unreleased local validation: architecture/provenance publication
gates still refuse the same122/98 entries. No Anvil source commit or policy bypass
was attempted. The compiled dependency closure and complete PMF bytes remain
pinned. A local callback-name collision in the source gate was resolved with an
unambiguous name; the final five Pi4/UnoQ re-exports are byte-identical to their
qualified/compile-only counterparts. See
`docs/evidence/neon-composed-application-20261027` for the immutable checkpoint.


### Shared chrome palette and motion policy

`Anvil/Graphics/neon_chrome_style.pbi` now owns a copied palette shared by menus,
tabs, text entry, lists and scrollbars. `NeonChromeStyleDefaults(out)` fills caller
storage; `PaletteGet(out)` copies the current value; `PaletteSet(in)` validates all
45 finite RGB fields in [0,1] before publishing. These two abbreviated names use
the full `NeonChromeStyle` prefix. Fifteen semantic RGB roles occupy180bytes with
four-byte alignment on the qualified64bit targets. Widget alpha/blend factors
remain widget-owned. The default12 chrome roles match desktop GlUIChrome.pbi;
list/field backgrounds and resting scrollbar thumb also have named roles. This
is chrome styling; retained arcade controls retain their own existing styling.

Input/output buffers must cover the complete palette and remain valid for the
call. Null/misaligned/wrapping/internal-overlap addresses refuse. Source storage
can change after Set returns. Invalid input leaves the published palette and
revision unchanged; setting identical bits does not advance the revision.
Defaults fills caller storage without publishing it. Palette changes affect only
colour, not geometry, glyph metrics, text preparation or input ownership.

`NeonChromeStyleAnimationsSet(0|1)` controls tab hover/indicator/arrow and list
hover transitions and the text caret blink. Disabled transitions snap on the next
input update, even at zero delta time; the focused caret stays visible. Reenable
continues from current values. Default enabled easing retains desktop speeds and
50ms delta-time clamp. Retained arcade motion and arbitrary application animation
are outside this control. `AnimationsGet()` returns the policy.

`NeonChromeStyleRevision()` starts at1 and changes after effective palette/policy
updates (wrapping to1 beyond2147483646). Menu/tab/editor/list NeedsRedraw also
compares each context's last successfully drawn revision, so resting widgets do
not miss a theme change. Failed Draw does not acknowledge it. Standalone scrollbar
hosts use the shared revision to invalidate their frame. Apply preferences between
frames and keep widget APIs serialized. Draw holds a synchronous mutation/readback
guard across callbacks, including nested list-to-scroll drawing; Set/Get/Defaults/
AnimationsSet return NSTY_ERR_BUSY there. This is callback protection, not a
multithreaded synchronization primitive. No driver/service ABI change is needed.

The builder/checker are tools/build_neon_chrome_style_app.py and
neon_chrome_style_app_check.py. Final Anvil361 capture438 passes188 independently
pinned assertions,88 complete64byte callback records,45 palette fields, a310canvas
unit translated geometry comparison, seven native colour probes and200 fully
coloured field-text pixels. Both default and custom callback scenes are checked;
only the final custom scene/default reference swatches are captured. Native image
viewed. The verifier rejects2771 report/image corruptions. Historical437 predates
redraw-revision tracking and passed180 checks; its original result is preserved.

Final composed regression439 passes the unchanged90frame/43pointer checker after
all style changes; real touch records remain0. Historical436 also passed the
functional oracle but its first post-return core-status reply was incomplete;
a separate bounded read-only postcheck confirmed healthy cores/fonts/Vulkan and
no pending payload. No upload/reset was repeated. Its one late frame is retained
as measured, not presented as zero jitter. Current439 timing is recorded separately
in its report. Style changes make no GPU/headroom guarantee.

Pi4 final proofs restore Vulkan/healthy cores, preserve original Lato and report
zero display timeouts/deadmanoff. UnoQ style client compiles only. No monitor
update/reset/storage/Bluetooth operation was needed. Shared global palette and
transition preference are implemented; native keyboard/physical actuation,
remaining engine effects/formats/math/collision and broader Anvil Vulkan remain
open. Architecture/provenance publication gates still apply independently.


### Shared collision and geometry math

`Anvil/Graphics/neon_collision.pbi` ports the GlMath operation group without a
renderer, device or allocator dependency. Enable floating point before including
it. Public results are0/1 for collision queries, negative errors for refused
arguments/geometry/capacity/work budget. Check for negative before treating a
result as true. All geometry is binary32; near-degenerate cases follow binary32
arithmetic, not an exact robust-geometric predicate.

| Desktop operation | Anvil shared API | Boundary rule |
| --- | --- | --- |
| CheckCollisionAABB | NeonCollisionAABB | Positive-area overlap; edge contact and zero area are false |
| CheckCollisionCircle | NeonCollisionCircle | Closed circles; tangency counts |
| CheckCollisionLineLine | NeonCollisionLineLine | Strict segment interiors; parallel/collinear and endpoint-only contact are false |
| CheckCollisionLineCircle | NeonCollisionLineCircle | Closed segment/circle; point segment supported |
| Math_CalculateBezierCubic | NeonCollisionBezier | t in[0,1], caller point output |
| GenerateSpriteHull | NeonCollisionHull | Convex hull of solid texel-index points |
| CheckCollisionSAT | NeonCollisionSAT | Convex polygons, translated offsets; touching counts |
| CheckCollisionPixelPerfect | NeonCollisionPixel | Shared world pixel-centre samples, positive scale and radians |

Scalar arguments/point coordinates are finite with absolute value at most1000000;
radii/dimensions cannot be negative. Point outputs are four-byte aligned8byte
NeonCollisionPoint records. LineLine allows a null hit output and changes a
provided point only on an intersection. Bezier writes only after validation.
These names deliberately use the Anvil namespace; the desktop engine stays a
read-only semantic reference.

A NeonCollisionMask borrows byte storage, dimensions and row stride. MaskBind is
transactional and requires aligned descriptor storage, width/height1..4096,
stride width..65536, and enough bytes through the last pixel (up to268435456).
Descriptor/source overlap refuses. MaskFromRGBA reads RGBA bytes with explicit
source pitch and writes0/1 only to mask pixels; any nonzero alpha is solid, as in
the desktop loader. Source/destination/descriptor alias refuses; row padding and
surrounding bytes remain untouched. Mask storage must stay alive; no GPU image
readback, texture handle or hidden alpha cache is involved. The descriptor is40
bytes on qualified64bit targets; copying uses bytes rather than a word-size stride.

Pixel takes two descriptors/transforms and maxSamples1..16777216. Transform x/y is
the scaled sprite's top-left before centre rotation; scale[1/1024,1024] is positive
and angle is radians. Rotated quad bounds conservatively intersect before an
inverse transform tests each candidate world pixel centre. Any nonzero mask byte
is solid. Candidate bounding-grid area above the explicit budget returns
NCO_ERR_BUDGET before sampling. A refusal is never reported as no collision.
This is raster-sample overlap, not continuous subpixel coverage or filtered-alpha
collision. Camera/world-coordinate mapping belongs to the caller.

The desktop broad phase uses max(width,height)/2 as a radius, which is not a
conservative bound around square corners; two solid8x8 masks at(0,0)/(6,6) overlap
but that circle test rejects them. The Anvil implementation uses rotated bounds
instead. It also avoids truncating negative local coordinates into texel0 and
uses the actual intersection rather than the desktop scan window. No desktop
source was changed. Sparse masks, scale/rotation and the corner case are checked
independently against a full-grid reference.

HullScratchBytes(width) returns(6*width+2)*8 bytes, aligned4. Hull takes output
capacity3..8192 and caller scratch. All source/descriptor/output/scratch overlap
refuses. It finds top/bottom solid pixels per column and runs a monotone chain;
these extrema contain the same hull as the complete set. Points use integer
texel indices minus half the sprite extent, matching desktop local coordinates;
they are not the outer continuous boundaries of the solid texel squares. Empty,
point and collinear masks return0; successful returns are vertex counts. Output
is unchanged for degeneracy or refusal; scratch may change. Exact capacity is
checked before publishing. No collinear interior points or repeated closing point
are emitted. PolygonValidate checks3..8192 finite points, all duplicates and every
vertex against every edge halfplane, accepting either winding and refusing
concavity, self-crossing/star ordering and zero area. SAT validates both polygons
then tests both sets of axes; normalization is unnecessary for separation. Hull
work is bounded by mask dimensions; polygon validation is quadratic in vertices.
No broad real-time timing claim is made for maximum capacities.

Final Anvil361 capture443 passes511 pinned assertions,21 cubic points, eight hull
scenes including irregular/empty/collinear masks,24 sparse plus36 solid transformed
pixel cases, RGB-alpha conversion and padding/guard/capacity/alias checks. The
native view uses returned hull/curve geometry and passes six colour probes,
671 hull-line pixels,409 curve pixels and1860 title pixels. Image inspected.
The independent verifier rejects1181 corrupted reports/images. Earlier440 passed
472 checks;441506;442511 before the final width-independent descriptor copy.
Original results/source versions remain separate. Final source also compiles for
UnoQ; runtime qualification is Pi4 only. No32bit execution, maximum-shape timing,
physical input or full engine/Vulkan completion is implied.

Build/check tools are build_neon_collision_app.py/neon_collision_app_check.py.
Returning proofs preserve original Lato, healthy cores, Vulkan and zero display
timeouts; deadman is off. No monitor update/reset/storage/Bluetooth was required.
Remaining native input, engine formats/effects/animation and wider Anvil Vulkan
work and mandatory source publication gates remain separate unfinished work.


### Keyed chrome easing and draw-owned hover regions

`neon_chrome_animation.pbi` ports the implemented Neon_Animate behavior from
GlUIChrome. The recorded desktop sprite modules declare GLAnimation data but
supply no player routine; this change does not invent a sprite-sheet player.
Animation storage is caller-owned: AnimationBytes(capacity,keyBytes) gives
capacity*(32+keyBytes) on qualified64bit targets, capacity1..4096/keyBytes4..256
includingNUL. Configure initializes zeroed/aligned context and nonoverlapping
arena. UTF8 keys are copied exactly, including the empty key. No truncation,
automatic eviction or heap allocation occurs. Forget, outside a frame, releases a
key; Configure clears the collection. Exhaustion refuses without changing output
or the refused key. The caller keeps valid storage alive and treats fields as
read-only. APIs use the full NeonChromeAnimation prefix.

Begin clamps finite delta time to[0,.05] and resets the active latch. Step takes
key,target,speed,initial,useInitial and an aligned16byte value/moving output.
The explicit initial flag replaces the desktop optional sentinel: a new key
starts at target when false, otherwise initial. Subsequent steps use stored
value, current+(target-current)*(1-exp(-speed*dt)), snapping within.002. Speeds
are finite[0,1000], values/initial have absolute magnitude<=1000000. Invalid
keys/args/aliases preserve published key/value/output; earlier successful steps
in that frame remain. End closes input accumulation without owning a GPU frame.
Active reports whether any step in the last Begin/End interval was still moving.
The shared chrome reduced-motion preference snaps Step to target at once.
Calls are serialized; nested Begin/configure/Forget during an open interval
refuse. This is neither a background scheduler nor a display/clock owner.

`neon_chrome_hotzones.pbi` supplies two caller-owned region arrays. HotBytes is
80*capacity on qualified64bit targets, capacity1..4096 (desktop used512). A region
is40bytes: full-width family/owner/item identity plus canvas x/y/w/h. Identity is
a tuple instead of desktop bit packing, preserving full owner and item values.
HotAt returns0/1 and optional24byte identity; HotChanged compares identities at
two points for redraw decisions. Half-open rectangles, last-registered-wins and
repeated same-identity regions match desktop hover semantics. Finite coordinates/
extents have absolute magnitude<=1000000; extents cannot be negative. Zero-area
regions are ignored. Public families are positive; owner is nonzero/item>=0.
The caller provides valid aligned buffers and keeps a bound context alive.
APIs use the full NeonChromeHot prefix.

Bind is optional and does not poll input. Begin starts a candidate map while
queries still read the previous committed one. Menus/tabs/editor/list/scroll
register their own visible hover geometry from Draw, including clipped partial
rows, close boxes, overflow arrows and horizontal/vertical thumbs. The host never
keeps a parallel layout model. Opaque menu panels also register internal blocking
regions: disabled rows/borders do not expose hover regions of covered tabs.
There is no new service/driver/input ABI. Retained arcade controls and any custom
application geometry still have their own input/redraw policies.

After the graphics End succeeds, Commit swaps maps. Abort discards staging after
a failed frame. Add capacity/geometry failures latch a refusal, so Commit cannot
publish a partial map; Abort is then required. Draw propagates registration
failures as negative results. Public bind/configure/begin/commit/abort/add attempts
inside renderer callbacks refuse while the common draw guard is held. Queries
remain valid against the previous immutable map. This protects synchronous
callbacks, not concurrent threads. Unbind before releasing context storage.
Default unbound drawing preserves existing renderer behavior.

Final Anvil361 captures446/447/448 (ordinary/open-menu/narrow-tabs+horizontal
scrollbar) pass396/402/405 assertions. Each completes60 successful frame-end
calls and records60 independently checked easing values/activity/region counts.
Published maps contain10/12/13 regions. Final-frame callback streams contain
44/66/51 records checked for type/font, finite values, basic geometry and zero
padding; RGB fields are not all pinned to an independent full raster oracle.
Region identities/clipping/placement are checked independently, with font-derived
tab widths bounded and related to adjacent regions. Five native probes and716
field-text pixels pass per mode; all images inspected. Corruption selftests
reject2239/2793/2446 reports/images. Maximum measured frame work was19412/21524/
31150us in these scenes; pacing targeted33333us. This does not prove CPU occupancy,
spare-workload headroom or general zero-jitter performance.

The canonical ordinary export pins current sources and is byte-identical to
qualified446; the earlier current menu export also preserves complete bytes.
UnoQ final overflow client compiles only. Compatibility449 passes the unchanged
188-assertion/88-record style verifier with hot tracking unbound. Cores, Vulkan,
Lato and display timeouts remain healthy/deadmanoff. No monitor update/reset,
storage or Bluetooth operation was required. No physical pointer/keyboard input
was supplied; targeted synthetic queries are explicit.

Historical444 returned0/383checks but its initial host verifier refused an omitted
eight-pixel menu-bar padding expectation. The source contract corrected the
verifier; its later acceptance has a separate record. Historical445 passed389
checks before callback-busy assertions. Compiler name errors from a fixture
replacement and a stage variable/procedure collision were resolved before upload.
Neither was a renderer/compiler defect. Original logs and results remain separate.
Full engine formats/effects/immediate chrome button/native input and wider Vulkan
work remain unfinished; mandatory source publication gates still apply.


## Prepared chrome button, glow and frame

`neon_chrome_button.pbi` implements the existing Neon immediate chrome button
appearance as a prepared controller. It owns no GPU frame or input transport.
Configure copies a validated UTF8 label into caller storage (4..512 bytes including
NUL). On qualified 64-bit targets Config is56 bytes and State144 bytes, aligned8.
Positive IDs, nonnegative font IDs, finite coordinates within absolute1000000 and
positive dimensions up to8192 are required. Geometry includes the four-unit glow
margin. Invalid/aliased/oversize labels refuse without replacing stored text.

Install the box/text/width/height/prepare callback family, or use
NeonServiceChromeButtonInstall with the existing resident service. Seal prepares
glyphs and caches metrics outside the graphics frame. LabelSet invalidates that
preparation; FlagsSet changes lit/enabled state. Draw only submits cached geometry
and text, acknowledges a successful style revision, and propagates callback errors.
It neither truncates the label nor changes the caller's scissor. The host retains
clip and input policy; enabled hot-map regions use the full button rectangle.

Input takes a shared host press EDGE, pointer coordinates, blocked flag and dt.
It uses half-open bounds, suppresses blocked/disabled presses and EventGet consumes
the result. Supplying held-down state instead of an edge repeats activation.
Call Input each UI frame while easing: speed18, dt clamped to0.05, snap below0.002.
Shared reduced motion snaps hover. NeedsRedraw includes active easing and changed
style revision. Disabled buttons have no published hot region. Hot capacity errors
propagate and prevent committing a partial map. The default palette, lit colours,
disabled text, glow and top/bottom edges match the desktop contract. Hovered body
channels clamp to[0,1] before opaque output, including saturated custom palettes.

NeonChromeGlow draws four outward boxes, alpha strength/(1.5*i), i1..4.
NeonChromeFrame draws four one-unit border boxes. Both validate geometry/colour,
preserve clipping, share renderer refusal and synchronous callback guards, and
own no frame. All these APIs are serialized, not concurrent-thread primitives.

Final physical Anvil361 captures452/453 pass143 pinned assertions each, including
the direct resident adapter frame before the recorded/reference frame. Four
button states, helper decoration and caller scissor preservation are covered.
The verifier pins all28 fake and28 native callback records, including colours,
font/text/padding. Known fake metrics independently fix text centering; the native
reference uses cached native font metrics. Each native scene compares340992 pixels
against an independently emitted adjacent reference with maximum channel error0,
and passes seven probes. The verifier rejects4981 corrupted reports/images per
scene. Both final images were visually inspected. UnoQ final eased export compiles
only; no runtime/GPU qualification there. These are synthetic input, single-scene
checks, not physical keyboard/touch or application-FPS measurements.

Historical450/451 passed137 checks before direct-adapter assertions. A later eased
attempt lost its read-only capture-status reply BEFORE upload/boot; the preserved
capture remained452. Host tooling now retries only exact version/map/shot status
queries once on a fresh socket after a prompt check. It never retries mutations.
Capture453 deliberately injects that client-side status loss, recovers and boots
exactly once. Seven mocked-I/O recovery checks pass; legacy fallback preservation
is unit-tested, not a legacy-firmware physical qualification. This does not prove
every truncated UDP response is detected. All final runs return0, keep cores,
Vulkan, original Lato and zero display timeouts healthy, and leave deadmanoff.
No monitor update/reset, storage or Bluetooth operation was needed.

Remaining engine formats/effects/native input and wider Anvil Vulkan are open.
Mandatory architecture/provenance publication gates still govern source commits.


## PNG compressed-stream prerequisite

The shared neon_inflate.pbi decoder now passes69 cases/93 assertions on Anvil361,
including306945 exact decoded bytes and294912 native sprite pixels. See
[PNG decoding progress](NEON_PNG_DECODING.md) for ownership, error, format, bounds
and qualification contracts. PNG chunks/filters/interlace/service dispatch are
still unfinished; existing encoded asset loading remains BMP24/32.


## PNG memory and file assets

The stream prerequisite above is now connected to explicit NeonPngInspect/Decode
and NeonServiceSpriteLoadPNGMemory/File APIs. Capture457 qualifies75cases/197
assertions, all15 legal colour/depth pairs with/without Adam7,20752 exact RGBA
bytes/5188 mask bytes and164736 pixels from eight resident textures. One image is
loaded from a real943-byte Pi-drive PNG. Caller outputs remain unchanged on
refusal; scratch is explicit. See [PNG contracts](NEON_PNG_DECODING.md), including
format/colour/sample limits and the unchanged BMP-only legacy signatures.


## VPM qualification tool maintenance

The board-specific VPM proof has moved to RaspberryPi4/Tests/Vulkan, removing
three architecture failures (119 remain). Its returning builder uses validated
payload RAM, the base diagnostic declares floating-point use, and the reference
path now emits actual triangle quads rather than calling the compact line path.
Final Anvil361 capture460 still passes the unchanged eight-frame/131072-byte/
510-case/raw-shader oracle and41 damaged-proof refusals. This repairs qualification
tools, not a new renderer feature or full Neon completion. See compatibility status
for layout, historical refusals, ownership-only identity and presentation limits.


Public coordinate-cache and rollback probe

The returning Pi4 CPU probe uses NeonRebindSurface for initial build, alternating
cache reuse, rotation and recovery from an oversized4097x8 surface. Private table
procedures are no longer called from tests. Payload-owned ranges replace legacy
addresses; an eight-row rejected stride preserves rollback coverage within8MiB.
CPU descriptor state is seeded deliberately: no GPU initialization, MMU change,
framebuffer write or job submission occurs in this fixture.

Capture461 on Anvil361 returns0/1.74hostseconds. All56475 captured coordinate words
and655360 report bytes match the independent rational oracle, including cache
counters, full descriptor rollback, guards, padding and reset state.385 damaged
reports refuse. The CPU-tier return screenshot was inspected; postchecks healthy.
This removes two source-architecture failures (117 remain); provenance98 still
refuses. It is qualification-tool maintenance, not new GPU or full-port support.


## Procedural rope sprite

Include neon_sprite_rope.pbi for NeonSpriteCreateRope(info,rgba,capacity,mask,
maskCapacity). It generates the desktop engine's fixed 32x64 rope composition:
orange base, yellow central highlight, three-pixel dark borders and two-row
translucent ridges every eight rows. The final ridge at row64 is clipped. Each
ridge channel uses source-over onto an opaque base, rounded to the nearest byte;
output alpha is255. This explicit integer contract does not claim bit identity
with every platform's desktop image-drawing implementation.

The caller supplies 8192 RGBA bytes and optionally 2048 one-byte mask entries.
The opaque mask is all1. Info is the existing16-byte/aligned8 NeonSpriteAssetInfo
on qualified64bit targets; its width/height publish32/64 only on success. RGBA and
mask storage may be byte-aligned. All used spans must be representable and
disjoint, including metadata. A missing mask ignores maskCapacity. Insufficient
capacity returns NEON_ASSET_ERR_CAPACITY; null/misaligned metadata, null output,
invalid spans or overlap return NEON_ASSET_ERR_ARGUMENT. Every refusal preserves
metadata, RGBA and mask. No hidden allocation, file, renderer or device access.

Include neon_service_rope.pbi after the service/sprite clients for
NeonServiceSpriteCreateRope(slot,rgba,capacity,mask,maskCapacity). Bind/open the
existing service first and create outside a frame. It returns an opaque resident
handle or0 with NeonServiceError. Upload copies the generated pixels; source
buffers may then be reused. A generation/upload refusal preserves the old
resident texture. Successful generation may modify caller buffers even if the
later service upload refuses. Clear/close ownership follows the existing sprite
client; no new provider/service ABI or resident firmware update is introduced.

Anvil361 capture463 returns0/1.5hostseconds and passes76 assertions,13 generator
argument/capacity refusals and three service refusals. All16384 generated RGBA
bytes,2048 mask bytes, optional-mask preservation, metadata, guards and report
padding match an independent Pillow composition. Two resident textures remain
correct after CPU-buffer erasure and a refused replacement: normal,3x scaled
and cropped4x draws pass98304 pixels plus four background probes. Native colour
tolerance is one byte; CPU bytes are exact. The image was inspected. The checker
rejects125 corrupted reports/images or truncations. UnoQ compiles only. Whole
fixture timing is not throughput/FPS or spare-workload qualification.

Historical462 returned0 but its host checker refused: the new fixture allocated
guard arrays one element short by treating a count as an upper index. Only those
two counts changed before463; guard/byte/pixel expectations stayed unchanged.
Original reports and payloads are retained, and462 is not a passing proof.
Cores/Vulkan/Lato/timeouts0 remain healthy, deadmanoff/leaseFREE. No firmware,
reset, storage or audio operation was needed. Full Neon/Anvil Vulkan and source
publication remain unfinished; mandatory gates still apply.


## Measured UTF8 text fitting

neon_text_fit.pbi provides NeonTextFitBind(measure), NeonTextFitUnbind and
NeonTextFit(output,capacity,scratch,scratchCapacity,source,sourceBudget,marker,
markerBudget,font,room). The measurement callback has signature .f(font,text).
Bind a prepared font's width function, then fit before Draw. The service adapter
NeonServiceTextFitInstall binds the existing resident width API. Prepare source
and marker glyphs first. The application selects U+2026 when supported or three
dots; this API does not guess font glyph availability or change font policy.

Return is the output byte count excluding NUL, or negative error. Source/marker
budgets include NUL and are bounded1..4096/1..16. Font IDs are nonnegative; room
must be finite0..1000000. Widths must be finite0..16777216 with nonnegative
advances, matching the desktop helper's monotonic-prefix assumption. A string
that fits is copied unchanged. Otherwise a bounded binary search selects the
longest fitting prefix and marker; no fitting marker yields empty text. Trailing
ASCII spaces at a cut are removed. Existing NeonUtf8Prefix preserves scalars,
U+0300..036F combining marks, U+FE00..FE0F selectors and joiner sequences. These
are the engine's boundary rules, not a full Unicode grapheme/shaping claim.

Caller-owned scratch needs sourceLength+markerLength+1 bytes and is disposable.
Output and scratch must be valid disjoint spans, each disjoint from both borrowed
input budgets; the two read-only inputs may overlap. No allocation or frame
ownership occurs. All refusal paths preserve output. Error codes ARGS-23100,
TEXT-23101, CAPACITY-23102, METRICS-23103, BUSY-23104, UNBOUND-23105. Capacity does
not silently shorten the requested result. Invalid metric callbacks refuse;
binding changes during callbacks refuse. Calls are serialized, not thread-safe.

Anvil361 capture464 passes95 assertions/64 UTF8 cases, including malformed input,
combining/selectors/joiners, empty/full/marker-only output and capacity/refusal
preservation. An independent native-font linear enumeration checks39 prefixes;
the fitted label and reference match35840 pixels exactly with1616 ink pixels.
The image was inspected.683 damaged reports/images/truncations refuse. UnoQ
compiles only. Whole-fixture1.5hostseconds is not frame-rate/headroom evidence.
An initial recursive callback test was compiler-refused before any upload; it
was replaced by legal nonrecursive bind/unbind refusal checks. No compiler guard
was weakened. Runtime source was unchanged after the accepted build. Existing
widget-specific fitting has not been migrated to this new public helper.
All postchecks healthy; no firmware/reset/storage/audio. Full Neon/Vulkan and
mandatory source publication remain open.


## Unicode uppercase title preparation

The desktop panel uppercases its title before drawing. Shared neon_text_upper.pbi
now supplies that preparation step through NeonTextUpperBytes(source,budget) and
NeonTextUpper(output,capacity,source,budget). The former returns the required UTF8
byte count excluding NUL; the latter publishes that many bytes plus NUL and
returns the count. Caller storage is explicit. Source budget includes NUL and is
bounded1..65536. Mutable output must be a representable disjoint span from the
borrowed source budget. Input remains immutable through the two-pass operation.
Every refusal preserves output. ARGS-23200, TEXT-23201 and CAPACITY-23202 identify
bad arguments/spans/overlap, malformed or unterminated UTF8, and insufficient
output capacity. A null output is an argument error; zero capacity refuses.

Conversion is pinned Unicode17.0.0 default full uppercase, including expansions
such as sharp-s to SS, ligatures, Greek and supplementary-plane letters. Unmapped
scalars remain byte-identical. No locale/context tailoring or normalization is
performed. This explicit locale-independent policy is not a claim of byte parity
with every desktop operating system's UCase behavior. Glyph availability and
font fallback remain separate. The prepared panel API below uses this converter.

Generated data includes1580 changed mappings/4691 mapped UTF8 bytes from official
UnicodeData and unconditional SpecialCasing properties. The generator pins both
input SHA256 values and cross-checks1525 mappings against host Unicode15.1;55
newer mappings remain checked against the pinned official source. The data is
Unicode-3.0, with its original license/notice retained separately from MIT code.
PROVENANCE records this new data source and three new consulted factual records;
existing classifications, definitions and refusal policy are unchanged. No
third-party implementation program was imported.

NeonUtf8ScalarAt(text,bytes,index) is a new public scalar decoder returning a
codepoint or the existing UTF8 error. It validates the selected sequence/start,
index and span, not unrelated sequences elsewhere in the buffer. Existing four
UTF8 procedures retain identical bodies. The new uppercase converter needs no
allocator, renderer, callback or device; generated rows use byte reads to avoid
alignment assumptions. Existing fitting code compiles to exactly the same full
PMF bytes when the new scalar API is unused.

Physical Anvil361 capture466 passes67 assertions/14 cases, every1580 changed
mapping, idempotency, fallback samples, malformed/truncated input, query sizing,
capacity/alias/refusal preservation and scalar-decoder edges. All13735 converted
bytes plus complete output guards/report padding match. Converted and reference
labels match35840 pixels exactly/2296 ink pixels.236 damaged reports/images or
truncations refuse. Native text includes STRASSE, CAFÉ and expanded FI. UnoQ
compiles only. A separate capture467 passes the unchanged95-check/64-case text
fitting proof and35840 native pixels with the extended UTF8 header. Both images
were inspected. Whole-fixture3.0/1.5hostseconds are not FPS/headroom benchmarks.

Historical465 returned61: its test used a data-label address difference that
included alignment padding, expecting23 instead of the actual21 output bytes.
Only the native source budget and expected byte count were corrected to actual
encoded lengths before466. Mapping code, data and host expectations were not
changed;465 remains refused. Cores/Vulkan/Lato/timeouts0 healthy/deadmanoff/leaseFREE;
no firmware/reset/storage/audio. Full Neon/Anvil Vulkan and source publication
remain unfinished.


## Prepared titled panels

neon_chrome_panel.pbi provides NeonChromePanelConfigure, TitleBytes, TitleSet,
GeometrySet, AccentSet, Seal, Draw, NeedsRedraw, Title and Error, with
NeonChromePanelRendererInstall(box,text,prepare). The service adapter
NeonServiceChromePanelInstall binds the existing resident box/text/prepare APIs
after Bind/Open. There is no new provider, driver or service ABI. The panel is
decorative: frame, clip, input blocking and event ownership remain with the host.

Config is56 bytes and state104 bytes/aligned8 on qualified64bit targets. Config
supplies font ID, UTF8 title/source budget, x/y/w/h/headerH and accentRGB. Set
headerH to NEON_PANEL_HEADER_HEIGHT (26) for the desktop default. Body dimensions
are positive and at most8192; header height is0..8192 independently of body height,
so taller headers are not clamped. Geometry inputs, extents and header/title
origins are finite/bounded to absolute1000000. Accents are finite0..1. Font ID
is nonnegative and its availability is the renderer's responsibility.

TitleBytes returns required copied uppercase storage INCLUDING NUL. Source
budget includes NUL and follows the existing uppercaser's1..65536 bound. Arena
capacity is1..196608, disjoint from state/config and source. Configure validates
before replacing state or title; refusals preserve both. TitleSet requires an
external immutable source and preserves the cached title/readiness on refusal
(its error field updates). Successful title changes invalidate readiness until
Seal. Title returns a borrowed read-only arena pointer. Keep state and arena
alive while used and through frame completion. Uppercasing follows the qualified
locale-independent Unicode policy, not arbitrary OS-specific UCase behavior.

Seal prepares the copied title outside a frame; an empty title needs no glyph
preparation. GeometrySet and AccentSet preserve readiness and update cached
values without glyph preparation. Draw uses the current shared palette and
cached title only: panel body, optional header/accent strip/divider/title, then
four hairline borders in the original order. Zero-height header fill/strip are
no-ops; divider, title and frame remain. Untitled panels draw body/frame only.
The caller's clip/frame remain active. No width query, uppercase work or glyph
preparation occurs in Draw. Palette revision and model changes drive NeedsRedraw;
panel accents remain explicit per-panel values. No automatic text fitting occurs.

Public errors ARGS-23300, STATE-23301, BUSY-23302, CAPACITY-23303, RENDERER-23304
and TEXT-23305 identify refusals. Positive callback results normalize to RENDERER;
negative renderer errors propagate. Drawing stops after the first callback
failure; the caller handles abort/retry of its partial frame. Shared synchronous
draw guards refuse model, binding and palette mutations during callbacks.
Calls are serialized, not thread-safe.

Physical Anvil361 capture468 passes131 assertions, all30 ordered callback records
(27 boxes/3 texts), copied-title guards and report padding. Default/custom themes,
untitled/zero-header panels, uppercase expansion, copied input erasure, failed
configuration preservation, title/readiness/error lifecycle, cached geometry/
accent changes, callback refusals and palette redraw are covered. The actual
service adapter renders four panels beside an independent direct composition:
358400 pixels match with maximum channel error0. Six probes check body colours,
background and clip retention; three caption windows contain2256/1584/1432 ink
pixels. Frame-open state remains owned by the caller, and observed preparation
inside Draw is0. The inspected image and1681 planted-fault refusals qualify this
bounded composition, not full engine, input, font policy or Vulkan completion.
UnoQ compiles only. Whole-fixture1.4hostseconds is not FPS/headroom evidence.
All postchecks healthy; no firmware/reset/storage/audio operation was needed.


## Scalar caret columns

neon_text_column.pbi provides NeonTextColumnBind(measure), Unbind,
NeonTextXForColumn(result,scratch,capacity,source,budget,font,column,fixedAdvance)
and NeonTextColumnForX(result,scratch,capacity,source,budget,font,x,fixedAdvance).
The service adapter NeonServiceTextColumnInstall binds resident TextWidth after
Open. Prepare source glyphs first and call outside Draw. No allocation, frame,
font selection or glyph preparation occurs here. The callback has .f(font,text)
signature and measures prepared immutable UTF8 prefixes. Proportional positions
therefore include the selected renderer's prefix metrics, including kerning;
they are not a second per-glyph advance implementation.

Each call returns0 or a negative error and publishes the16-byte/aligned8
NeonTextColumnResult: column.i, x.f, reserved.l=0. Every refusal preserves the
result. Scratch is disposable, needs UTF8 byte length+1, and must be disjoint
from result and the borrowed immutable source budget. That budget includes NUL
and is1..4096. All spans must be positive and representable. Font is nonnegative.
Column requests are0..65535; x is finite within absolute16777216. fixedAdvance
is finite0..8192;0 selects proportional measurements. Prefix widths must be
finite0..16777216 and nondecreasing. A decreasing sequence refuses rather than
silently producing an invalid hit test. Results also stay within that metric bound.

Columns count Unicode scalars, including a supplementary character as one, not
UTF8 bytes, UTF16 units or grapheme clusters. Combining marks may occupy separate
zero-width columns; no shaping, bidi, grapheme movement or multiline policy is
added. A proportional XForColumn request beyond the text clamps to its end.
An explicit positive fixed advance extrapolates XForColumn beyond text, matching
the desktop fixed-cell coordinate behavior. Fixed ColumnForX clamps at the scalar
count, avoiding the desktop UTF16-unit clamp inconsistency for astral characters.
The caller must use a fixed advance that matches its renderer. Negative/zero x
selects column0. Midpoint ties select the later scalar; zero-width boundaries
are skipped for positive x. Proportional queries enumerate measured prefixes;
cache results outside Draw as appropriate. No constant-time preparation claim.

Errors ARGS-23400, TEXT-23401, CAPACITY-23402, METRICS-23403, BUSY-23404 and
UNBOUND-23405 distinguish refusal causes. Bind/Unbind mutations during a
measurement callback refuse. Fixed mode needs no bound measurement callback.
Calls are serialized, not thread-safe; input mutation during a callback is invalid.
Existing editor widget-specific hit-testing has not yet been migrated.

Physical Anvil361 capture469 passes150 assertions and91 corpus cases: empty,
ASCII, accented/supplementary/combining/control characters, proportional kerning,
zero-width advances, fixed extrapolation/clamping, negative x and midpoint ties,
malformed/unterminated UTF8, unbound/failed/decreasing/nonfinite/excessive metrics,
reentrant binding changes and14 additional pointer/span/alignment/alias/range
refusals. Published results, source bytes, guard bytes and report padding match
the independent host model. An independent literal-prefix native enumeration
checks12 scalar boundaries and11 midpoint queries. Four generated caret lines
and the full text match the reference across44800pixels with max channel error0,
1136 text ink pixels and192 caret pixels. The image was inspected;1058 damaged
reports/images or truncations refuse. UnoQ compiles only. Whole fixture1.4host
seconds is not an FPS/headroom claim. All postchecks healthy; no firmware/reset/
storage/audio. Full Neon/Anvil Vulkan and source publication remain unfinished.


## Fixed TrueType layout prerequisite

The shared truetype_layout.pbi owner adds AnvilTrueTypeLayoutUtf8Fixed with the
same arguments as AnvilTrueTypeLayoutUtf8 followed by fixedAdvanceQ16. Zero uses
the original proportional metrics and pair positioning. Positive Q16 advances
through536870912 (8192 pixels) use equal cells without kerning or GPOS pair
offsets. Glyph ink is not stretched or clipped. UTF8 decoding, CR/LF handling,
glyph-boundary wrapping, line alignment and baseline calculation remain in the
same layout owner. The original public entry delegates with advance0.

The existing parser must have metrics/cmap/kern/GPOS open. Capacity remains
bounded by2048 glyphs; caller supplies all output arrays and result pointers.
Coordinates/advances are signed Q16. Existing success/error/partial-output
contracts remain: return1 on success or0 with AnvilTrueTypeLayoutError. This
change does not add transactional output, pointer-span validation, thread
safety, control-character display or pixel-snapping policy to the old API.

Physical Anvil361 capture470 runs the saved original owner for16 proportional
cases, loading the existing Lato file through the real file service into the
application's own parser. Capture471 runs the extended owner: those16 cases
are byte-identical across every glyph/coordinate/advance, guards and padding.
An independent host cell model checks48 fixed cases covering ASCII, accents,
supplementary/combining glyphs, empty text, CRLF/trailing breaks, wrapping,
left/center/right alignment and fractional7.5-pixel advances. Five invalid
advance/capacity/UTF8 requests refuse. Seven setup assertions pass. Full65536-byte
reports are checked, and1318 damaged reports or truncations refuse.

Both are CPU layout proofs, not glyph-rendering or Vulkan font-policy proofs.
The CPU-tier return screenshot was inspected. Whole fixtures return0 in about
4.3/4.0hostseconds, not renderer timing/headroom. UnoQ compiles only. Cores,
original resident Lato, Vulkan restoration, zero display timeouts and deadmanoff
remain healthy. No reset, firmware update, storage write or audio operation.

Next is connecting per-font fixed advance to the actual Vulkan font reference,
measurement, layout-cache key and drawing path. Pixel snap and visible-control
policies also remain open. The installed361 firmware is unchanged and does not
yet expose this new font policy. Full Neon/Anvil Vulkan/source publication remain
unfinished; this is a shared layout prerequisite, not completed font parity.


## Resident per-font fixed spacing (protocol1.5)

Anvil362 connects the fixed-layout prerequisite to actual resident Vulkan
measurement, layout caching and drawing. Include neon_service_font_spacing.pbi
after the standard float32, HAL contract and service client. Optional flag64
FONT_SPACING/minor5 appends operation34 and a16-byte {font.i,advanceQ16.i}
request. Query/surface records and slot38/service ABI1.8 stay unchanged.
Existing basic clients still require minor0; requesting spacing checks minor5
at binding and invocation. An older provider refuses the optional feature.

NeonServiceFontSetFixedAdvance(font,advance.f) accepts registered positive font
references, idle only. Zero restores proportional spacing. A positive finite
advance through8192 source pixels rounds to nearest Q16; a positive value rounding
to zero refuses. Legacy roles0..3 cannot be mutated by this operation. Invalid
arguments produce the existing service ARGS error; active-frame mutation produces
STATE. Other native errors propagate. Refused requests retain the old spacing.
No raster rebuild is required: glyph ink/atlas entries are independent of spacing.
The request's Q16 value is passed directly to the native integer setter, without
a lossy float round trip.

Native NeonVkPortFontRef is now40 bytes on qualified64bit targets, adding
fixedAdvanceQ16 after the existing four fields. Bind initializes0. This is a
source-level native structure change; rebuild native callers/arenas. Opaque
resident handles and their epochs retain the existing protocol contract.
Native Q16/float setters, a float getter and retained registry setter are supplied.
Capture472 qualified the integer setter's resident call path. The later
native attachment proof below separately qualifies the direct float/getter and
retained setter paths it exercises. Retained arena sizing follows SizeOf(ref); its older GPU fixture
was updated from256 to320 bytes for8 references, without claiming a new replay.
Reprepare/rebuild controls when new metrics require changed layout.

Advance is passed explicitly from each reference through width and drawing to
the shared layout owner. No global role policy is changed. Legacy/direct calls
pass0, so a fixed reference cannot leak its policy to another reference or role.
The16-entry short-run layout cache includes Q16 advance in addition to exact text
bytes, slot generation, slot and size. Glyph raster cache identity is unchanged.
Fixed cells omit pair positioning and preserve glyph ink. Pixel snapping and
visible controls remain separate unfinished policies.

Physical Anvil362 capture472 passes92 assertions and6 alternating proportional/
14-pixel/7.5-pixel rows of identical text. All161280 native/reference pixels
match with zero channel difference; each row has1136 visible ink pixels. Fixed
references are compared with independently positioned single-glyph draws using
the proportional reference. Repeating policies with the same text/face/size
exercises cache reuse and isolation. Protocol4 refusal, invalid/short/raw request,
stale-like invalid handle, nonfinite/negative/tiny advances and in-frame mutation
are covered. Widths154/82.5 match cells; all four proportional measurements remain
80.66099548339844, including restoration to0 and legacy role use.

The current image was inspected, and114 damaged reports/images or truncations
refuse. A separate comparison with physical Anvil361 capture469 matches35840
default-text pixels and the exact old width, across both current proportional
rows. The same pure service application compiles for UnoQ; it does not qualify
another GPU backend or all direct native entry points. Whole fixture1.4host
seconds is not FPS/headroom evidence. Cores/Vulkan/Lato/timeouts0/deadmanoff healthy.

The counted362 image was saved/reloaded/hash-verified, with a verified361 backup,
then restarted once and allowed90 quiet boot seconds before successful version/
map/core/Vulkan checks. Installed raw6002216B SHA
1264541e2d39e6afa196bef902c1c3750857ed819e5a3e41473657b5bdc8c624,
code00200000..007B9627, BSS0D000000..0EE4750F within reserved0EEFFFFF.
No further reset or Bluetooth operation was needed. Full Neon/Vulkan and mandatory
source publication remain unfinished.


## Direct native fixed-font qualification

The returning native Vulkan proof now exercises NeonVkPortFontSetFixedAdvance,
SetFixedAdvanceQ16, FixedAdvance, TextWidth, Warm, Text, TextRight and TextCentre,
plus the retained registry setter and actual retained label drawing. It links
the production parser, font port, retained adapter and Vulkan backend. This is
separate from the protocol1.5 resident-client proof above.

Scaled native width queries require the configured port canvas. Prepare font
runs before Begin. Native setters refuse mutation during a frame; stale-generation
setters/getters refuse. Registered retained fonts accept fixed advance without
changing unrelated references. Zero restores the original proportional width.
That historical native proof used the40-byte font-reference layout on qualified
64bit targets; the later snap extension below supersedes that source layout. This phase adds qualification tools, not new production behavior.

Anvil362 capture475 passes124 assertions. Its six rows cover proportional,
16-pixel cells,7.5-pixel cells,12.5-pixel retained text, right alignment and centre
alignment, using the embedded boot face at20pixels. Fixed reference rows are
independently emitted single-glyph draws, not a second use of fixed layout.
The narrow7.5-pixel cells deliberately overlap wide glyph ink instead of scaling
it. All46080 paired attachment pixels match with zero channel difference, and
all rows have positive ink; retained text includes1048 gold pixels.

The frame records58draws/738inputvertices:57text draws/720textvertices plus the
retained layer's unconditional sixteen-side pointer fan (centre+rim+closure,
18vertices in one draw), even when its pointer is outside the viewport. Glyph
raster and atlas-upload deltas are both0. Complete copied/poisoned counts and
sixteen-byte guards prove fresh368640byte crops. After checked destruction, both
old device and instance calls return the exact handle error -20002; the count
output remains12345. These owner APIs return the error directly without increasing
the diagnostic fault counter.219 damaged reports/pixel buffers/truncations refuse.

This proof creates its own Vulkan attachment in validated payload RAM. It does
not draw through the resident service or adopt a display target. The GPU crop
montage was inspected. The CPU return screenshot contains old console history;
current success is established by the fresh return record/report and GPU memory
readback, not the earlier return text visible in that console screenshot.
Whole fixture7.9hostseconds includes setup/teardown/copy, not an FPS benchmark.
Only Pi4 native GPU execution is claimed; shared runtime code was unchanged.

Historical473 refused because the fixture queried scaled metrics before Canvas
and omitted the retained pointer in its expected counts.474 fixed setup but
still assumed an off-screen pointer would be CPU-culled. The source actually
submits a compact fan for GPU clipping; the final expectation was derived from
that public fan path. The original checks/images/reports are preserved. No
production code or glyph/pixel expectations were changed to accommodate a failure.

The returning builder places arena05000000..05FFFFFF, surface03000000..033E7FFF,
Vulkan window033E8000..03FE7FFF and prospective banners04000000..041FDBFF in
payload windows. The old standalone example's0A arena is not authorized by the
live monitor map and is overridden by this builder. Code/BSS/stack/report/crops
are pairwise disjoint and checked against a fresh map before each run. No firmware,
reset, storage or Bluetooth action was needed. Cores/Vulkan/Lato/timeouts0 healthy,
deadmanoff/leaseFREE. Configurable pixel snap, visible controls, full application
acceptance, source publication and broader Anvil Vulkan remain unfinished.


## Per-font pixel snapping

NeonVkPortFontSetSnapToPixel(reference,enabled) now accepts exactly0 or1 while
idle. NeonVkPortFontSnapToPixel returns that per-reference value, or-1 for an
invalid/stale reference. Registered retained fonts expose
NeonVkRetainedFontSetSnapToPixel. The source reference is now48bytes on these
64bit targets; allocate retained storage with NeonVkRetainedFontBytes rather
than a historical literal size. Rebuild native source callers after this change.

The historical Anvil default remains1. Setting0 retains fractional Q16 glyph
ink origins through camera and canvas mapping; setting1 rounds each positioned
origin before those transforms. Width, advances, pair layout, raster cache and
layout-cache identity are independent of this geometry policy. It adds no
preparation inside a frame. Bitmap fallback refuses unsupported unsnapped mode
instead of silently discarding the setting. Normal/right/centre text and retained
labels use the same explicit per-reference setting.

The optional pure resident client is neon_service_font_snap.pbi:
NeonServiceFontSetSnapToPixel(font,enabled). Protocol1.6/flag128/op35 carries a
16byte font+enabled request. Existing basic clients still require minor0.
Both client binding and extension dispatch check the advertised feature minor;
the provider validates exact record size, registered ownership, boolean and idle
phase. A refused BindApi leaves the previous accepted dispatcher unchanged.

Anvil363 is installed on Pi4, built20261028-062400. Its raw6004264byte image
SHA256 is8eb4ac7bba9878b4059e048ad529ad791b4a167c81463e147ebecd7ddff6575c.
Code00200000..007B9E27 and BSS0D000000..0EE4760F fit the live reservations.
The previous362 image is verified at1:/B362V363.IMG; candidate1:/V363NEW.IMG and
boot1:/KERNEL8.IMG were saved, reloaded and SHA-verified before one authorized
reset. The restart waited90quiet seconds, then verified running identity/map,
healthy cores and Vulkan. Do not replay those completed install/reset helpers.

Direct native capture476 on362 passes97checks with the new production geometry
path and48byte reference. Six rows cover snapped default, fractional unsnapped,
integer equivalence, retained label, right and centre text. Whole text is paired
with independently positioned scalar draws. All46080 paired GPU attachment
pixels match exactly; fractional snap-off differs from snap-on after2x canvas
mapping, while exact integer positions remain identical.43draws/450vertices
include the retained pointer fan. In-frame raster/upload deltas are0;192damaged
reports/pixels/truncations refuse. The actual GPU montage was visually inspected.

Resident capture478 on363 passes82checks and46080 paired native pixels, including
raw short/bad/stale request refusals, minor5 refusal of the optional minor6 feature,
in-frame mutation refusal, unchanged source width and preserved dispatch after a
refused bind. It uses resident Lato at12pixels and actual text-mapped calls.
All rows contain656ink pixels.88damaged reports/truncations refuse. The shared
client also compiles for UnoQ; no non-Pi4 GPU execution is claimed.

Capture477 returned0 and passed84APIchecks, but correctly failed its image oracle:
the test explicitly closed the resident service before return capture, restoring
the console. That source/report/image remains historical evidence. The corrected
fixture preserves the final GPU frame and lets the loader perform return cleanup;
no production or glyph/pixel oracle change was made to accommodate that refusal.
The correction also added a refused-bind dispatcher-preservation check.

Visible controls, full application/input acceptance, legacy image convenience
paths, remaining formats/effects, source publication and broader Anvil Vulkan
remain open. These are correctness tests, not FPS or map-headroom measurements.

Default regression capture479 on363 additionally passes124checks. All368672
fresh crop/guard bytes are identical to the old475 result, proving the historical
snapped default across proportional/fixed/fractional, retained and aligned text.
The current fixture uses48byte references. Cores/Vulkan/Lato healthy;DSItimeouts0,
deadmanoff/leaseFREE. The full Neon/Anvil Vulkan goal remains active.


## Visible controls in native and resident fonts

NeonVkPortFontSetControlMode(reference,mode) selects legacy0, hidden1 or visible2.
NeonVkPortFontSetShowControls(reference,enabled) accepts exactly0/1 and selects
hidden/visible respectively. NeonVkPortFontControlMode returns the mode or-1 for
an invalid/stale reference. The retained registry exposes SetControlMode and
SetShowControls too. Changes are idle-only and per reference. Historical Anvil
binding defaults to legacy0, retaining its existing CR/LF behavior; a caller
porting a desktop ShowControls flag explicitly sets false/true. References now
occupy56bytes on the qualified64bit targets. Rebuild native source callers and
use NeonVkRetainedFontBytes for caller-owned storage.

Hidden mode removes C0(codepoints0..31) and DEL127 from measurement, prewarming
and drawing. Visible mode emits a common outlined box for each, including CR
and LF separately; it does not break the line. C1 and ordinary missing Unicode
glyphs still go through the selected face's cmap. Native strings remain
NUL-terminated, so embedded NUL is available only to counted core decoding/layout
APIs. The box guarantees visible ink even when the font's .notdef glyph is blank;
this is not an OS-dependent glyph or a separately labeled tab/return symbol.

Shared truetype_controls.pbi owns classification, dimensions, advance and
coverage. At height20 the box is12x20, advance13; dimensions are bounded1..512
with minimum3x3 ink. Its raster API writes only width*height bytes, preserves
the tail, and refuses invalid/short/unrepresentable spans without writing.
The existing strict UTF8 decoder is the single validation owner, extended with
an explicit control mode. It validates all input and counts displayed glyphs
before writes, so hidden input may fit a smaller output or become empty.
Legacy decoder/layout entry points delegate mode0. Layout skips pair positioning
across the virtual control glyph; fixed cells still use the requested advance.
Core layout serialization and existing partial-output/font-error contracts
otherwise remain unchanged.

Native width, warm and draw receive the same explicit mode. Preparation admits
the virtual glyph into the normal slot/generation/size atlas cache outside the
frame. Short-run layout identity now also includes control mode, preventing a
visible run from being reused for a hidden one. Pixel snap remains an independent
per-reference geometry policy. No rasterization or upload is added inside Draw.

The pure resident client neon_service_font_controls.pbi offers
NeonServiceFontSetControlMode and NeonServiceFontSetShowControls. Optional
protocol1.7/flag256/op36 carries a16byte font+mode request; basic minor0 clients
remain valid. Both required-feature binding and dispatch check minor7. The
provider validates record size, registered font ownership, mode and idle phase.
Anvil364 is installed on Pi4, stamp20261028-064453, raw6012456bytes SHA256
c0a0afb7cdfc1e4006d6aa5dfaaad727a248d69066146133be4b7100d0e5f75f.
Code00200000..007BBE27/BSS0D000000..0EE4778F fit the live reservations. Previous
363backup1:/B363V364.IMG, candidate1:/V364NEW.IMG and boot1:/KERNEL8.IMG were
saved, reloaded and SHA-verified before one authorized reset.90quiet boot seconds
preceded live version/map/core/Vulkan checks. Completed install/reset helpers
must not be replayed.

Native capture480 passes244checks and46080paired GPU attachment pixels. It
tests the complete C0/DEL classifier, C1/count-NUL behavior, hidden capacity and
strict input refusals, legacy CRLF layout, fixed/proportional control advances,
min/normal/max raster bytes and guards/tails, setter modes/stale generations,
retained text, and hidden/visible reuse of the same source. Independent flat
rectangle outlines check visible boxes; plain literal strings check hidden text.
The all-hidden crop is entirely background.30draws/306vertices include the retained
pointer; in-frame glyph/atlas deltas are0.339damaged reports/pixels/truncations
refuse. The actual GPU montage was visually inspected.

Resident capture481 on364 passes78checks and46080paired native pixels using
Lato12. It checks older feature-version refusal, preserved dispatcher after a
refused bind, short/invalid/stale/legacy raw requests, idle/in-frame policy,
source widths and actual mapped drawing.84damaged reports/truncations refuse.
The actual resident screenshot was inspected. Shared client UnoQ compilation
also passes; only Pi4 GPU execution is claimed.

Legacy regression482 repeats69layout cases plus7setup checks, covering original
proportional behavior, wrapping/alignment/CRLF/fixed cells and refusals. The whole
65536byte report is identical to471. Default native regression483 passes124checks
and all368672crop/guard bytes remain identical to479(and475). Original font metrics
and pixels are preserved. All runs returned0, cores/Vulkan/original resident
Lato remained healthy, display timeouts0, deadmanoff/leaseFREE. No Bluetooth.
These correctness fixtures are not frame-rate or map-headroom benchmarks.

Full application/native-input acceptance, font-cache/application policy
integration, legacy image convenience paths, remaining formats/effects, source
publication and broader Anvil Vulkan remain open.


## Composed drive assets and independent font references

NeonVkPortFontDerive(out,source,role,pixels) creates a separate 56-byte reference
to the same loaded slot/generation. It copies spacing, pixel-snap and control
policy; subsequent setters are independent. It does not load a second face or
acquire ownership. Unloading/replacing the face invalidates every derived
reference. The call is idle-only and refuses invalid roles/heights, alignment,
unrepresentable byte spans, stale generations and overlapping storage before
writing the destination. Shared signed NeonByteSpan/NeonByteOverlap checks
replace typed-pointer end comparisons after a boundary fixture exposed a
processor exception. This shared native owner applies across Vulkan backends.

The pure resident NeonServiceFontDerive(parent,role,pixels) returns a new
context-owned handle or zero with NeonServiceError. Optional graphics protocol
1.8, flag512, op37 uses a 24-byte parent/role/pixels request. Required-feature
binding checks minor8 before publishing the dispatcher. The provider admits
only registered parents while idle and stays within the existing32-reference
capacity. Derived handles do not own extra face allocations. The payload
service-table ABI remains1.8/200 slots; the optional graphics protocol is a
separate contract.

The existing composed application builder now offers --assets in addition to
--scripted. Its asset profile reads Lato from2:/fonts/Lato-Regular.ttf, loads
one owned face and derives smaller/fixed/unsnapped/control-policy references.
It reads1:/NPNG457.PNG, decodes the13x11 RGBA16 Adam7 fixture and uploads it.
All caller font/encoded-image/RGBA buffers are erased before rendering, proving
the resident resources survive independently. Existing menus, tabs, editor,
list, retained controls, sprite batches,32particles and static lines remain.
The final cleanup clears textures and unloads the owning face; derived width
and derivation calls then refuse stale references.

Pi4 capture484 passes164 native checks and46080 exact paired GPU attachment
pixels. It retains the original failing7FFFFFFFFFFFFFE0 source test and checks
destination preservation, overlap, alignment, stale source, copied policies
and independent mutations.58draws/738vertices and original proportional width
139.716796875 remain; in-frame raster/upload deltas are0.259corruptions refuse.
The actual GPU crop montage was inspected.

Anvil366 is installed, stamp20261028-080217, raw6014504bytes SHA256
945510a517cda8f8852c5463ac2f97ac530bd567762f529d3a16d68509e4e137.
Boot/candidate1:/V366NEW.IMG/previous365backup1:/B365V366.IMG were reloaded and
SHA-verified before one reset and90quiet boot seconds. Code00200000..007BC627,
BSS0D000000..0EE4778F remain within the live reservations. Completed install
and reset helpers must not be replayed.

Capture485 runs the composed asset profile for90frames on366:65checks,
5148PNG pixels within1channel unit and14400 exact paired font-policy pixels.
Actual screenshot inspected.99 damaged reports/images/truncations refuse.
The same pure application compiles for UnoQ; only Pi4 execution is claimed.
Input is27scripted records with real touch polling but0physical contacts,
so this is not physical keyboard/mouse/touch acceptance.

Measured25.724ms mean work,40.072ms maximum,29.932FPS;89of90frames stay within
33.333ms. Frame80 reopening the menu spends34.207ms in submit/present,
5.175ms recording,0.128ms preparation and0.562ms input. A strict30FPS worst-case
claim is not met. The present-stage timing needs further separation; this
measurement does not identify a GPU/DSI root cause by itself. Final cores,
original resident Lato,Vulkan and display remain healthy,timeouts0,deadmanoff.

The host runner now permits one fresh-socket recovery for the read-only
pre-boot last-run query, matching its existing status-query handling. A lost
query before boot records nothing booted; mutations are never automatically
replayed. Eleven controlled-socket checks pass. The earlier lost pre-boot
reply and later actual native exception are preserved as distinct evidence.

Full native-input acceptance, remaining engine image/effect paths, source
publication gates and broader Anvil Vulkan remain open.


## Resident frame-end timing and DMA visibility

Anvil 368 adds a diagnostic breakdown to vkstat for the latest resident Neon
application. It reports frame/failed counts, counter frequency, aggregate raw
ticks and the worst End call's sequence/result. Stages are command finalization,
submission, fence wait and source publication together (gpu); synchronous
DMA plus its cache maintenance (dma); additional cleaning (clean); display
publication including the boundary wait (publish); remaining overhead; total.
The gpu field is not pure hardware execution time. Counts reset on application
Open and survive Close and vkstat. The payload and graphics ABIs are unchanged.

The measured DMA presentation path already completes destination cache
maintenance and its visibility barrier inside avcDmaCopyRect. No CPU pixel
stores follow that handoff. Its subsequent whole-frame MmuCleanRange repeated
the work, costing about 2.155 ms per frame in the instrumented baseline. That
duplicate clean is removed from full application presentation and the console
path that copies the frame and restores the banner/keyboard with DMA. All
pre/post DMA maintenance and barriers remain, as do CPU-rendered pixel flushing
and display-request ownership/timeout handling. This is display-owner work,
not a model-specific change or a bypass of the shared Vulkan API.

| Composed asset run | Mean work | Worst work | Frames within 33.333 ms |
| --- | ---: | ---: | ---: |
| Instrumented Anvil 367, capture 486 | 31.938 ms | 35.799 ms | 89/90 |
| Updated Anvil 368, capture 487 | 23.343 ms | 24.763 ms | 90/90 |

Both use the exact same returning payload and pass all 65 application checks.
The final 1280x800 images match in every one of 1,024,000 pixels, including all
widgets, text and drive assets. The fresh visible Vulkan console was captured
separately and inspected after restoration. Physical execution is DSI/Pi4 only;
HDMI and other targets are not claimed tested by this run. CPU display regions
retain their owners' existing flush paths.

On 368, mean End components are 6.239 ms submission/completion, 7.992 ms DMA,
0.000025 ms additional clean, 3.596 ms display publication and 0.00225 ms other.
All 90 End calls are accounted for; aggregate and worst components sum
exactly in raw ticks and cross-check against the application's End timer.
There are no failed End calls. Average End is 17.830 ms, worst 19.152 ms.
The larger observed end-to-end reduction also reflects a changed display-wait
phase; it is not an 8.6 ms guaranteed compute saving. The 90-frame fixture
meets its 30 FPS budget with about 8.57 ms worst-frame margin, not a universal
engine performance guarantee. Input remains explicitly scripted.

The initial 367 diagnostic passed an integer label to Print and displayed its
address numerically. Raw values and sums were retained for analysis, but that
diagnostic output was not accepted as finished. 368 prints literal labels and
passes the independent stage cross-check. One generated 368 installation recipe
retained an old expected build; it refused immediately after read-only version.
No disk operation or reset occurred in that refused attempt. The corrected
recipe uses a separate install-fixed journal and the archived 367 identity.

Installed 368: stamp 20261028-082452, raw 6,016,736 bytes, SHA256
b95e09439d868ac4a719317b841e2b0859d091e7217875ceca15a4990947d7f7.
Code 00200000..007BCEDF and BSS 0D000000..0EE4782F fit the live reservations.
The 367 backup, 368 candidate and boot file were reloaded and SHA-verified
before one reset and 90 quiet boot seconds. Final cores, original resident font,
Vulkan and display are healthy, timeouts zero and deadman off.

Physical input routing, remaining engine image/effect paths, source publication
and broader Anvil Vulkan remain open.


## Earlier input broker qualification (Anvil 368)

The portable input prerequisite is implemented and CPU-qualified. It is not yet
installed as a resident keyboard/mouse endpoint. Anvil 368 and service-table
ABI 1.8 remain installed; this change has not assigned or populated another
service slot. Native HID/touch producers, the payload client, lifetime entry/
return integration and the composed application's input adapter remain to wire.

Anvil/Hal/input_codes.pbi is now the single owner of the existing normalized
kind, source, named-key, modifier and cancellation vocabulary used by
input_events.pbi. Existing numbers stay unchanged. Up/Down/PageUp/PageDown/
Insert append after the original ten keys. Alt/GUI modifier bits and a
device-loss cancellation reason are added. Existing byte normalization, CRLF
suppression and Ctrl+C behavior still use the original implementation.

The candidate input protocol defines a 32-byte API descriptor, a 40-byte Open
request and a 48-byte NativeInputEvent. Typed text, named key-down/up and
cancellation keep the normalized vocabulary. Pointer and wheel events add
logical-screen coordinates and absolute buttons. Mouse contact0 and shifted
touch ids stay distinct. A separate physical-key event carries HID usage and
down/up edges, including modifier-only keys; games can track held letter keys
without treating editor text as a key release protocol. Text remains the
existing normalized ASCII channel; UTF8 graphic strings are a separate API.

NativeInputEventValid checks shape, source/kind combinations, scalar bounds,
reserved fields, generation, timestamp, pointer states/button levels and
physical-key edges. It checks positive aligned representable storage before
reading fields. This does not establish that an arbitrary address is mapped;
the eventual resident provider must additionally enforce payload memory ranges.

Anvil/Core/input_ui.pbi owns payload focus over the existing typed queue and a
bounded 64-record device lane. InputUiBegin changes focus and cancels queued
old input. InputUiDevicePush accepts pointer, wheel and physical-key records,
checking full-width producer arguments before narrowing wire fields.
InputUiPop alternates ready typed/device lanes so repeated text cannot starve
pointer releases. Screen/focus changes and either queue's overflow deliver one
cancellation before fresh device records are admitted. Queued stale records
and device overflow are counted. Focus loss retires the UI consumer without
draining the new CLI owner's text. Close is idempotent and leaves no CLI focus
to execute payload-era input. The next line editor explicitly takes its focus.

The pure input_service.pbi registry is independent of graphics. It permits one
registered provider, one payload scope and one positive context. Failed Close
retains ownership; failed scope cleanup quarantines it and blocks the next
Enter until explicit checked recovery. Unexpected positive statuses are refused.
Query is available outside payload scope; ownership-changing calls are not.
This registry is currently qualified with controlled callbacks, not HID drivers.

Pi4 CPU captures488/489/490 return zero with222,228 and267 checks respectively.
The final fixture covers focus handoffs, stale CLI text, down/up ordering,
typed/device fairness, cancellation admission, both queue overflow paths,
two complete wrapped FIFO transfers, full-width refusal before narrowing,
wheel/touch/physical letter/modifier events, legacy bytes and scope quarantine/
recovery. The final full8192-byte report matches independent literal expected
values. Its checker rejects541 damaged reports/truncations.

All three tests use a deterministic clock and controlled event producers.
They execute the actual shared input algorithms on Pi4; they are not physical
keyboard/mouse/touch actuation or resident integration evidence. The final
shared fixture also compiles for UnoQ, with no execution claim there. The
initial test callback was correctly refused as recursive by the compiler;
it was corrected to check scope-entry busy behavior without recursion. No
compiler rule or production busy guard was weakened.

Final Pi4 cores, resident Lato, Vulkan and display remain healthy, with zero
display timeouts and deadman off. No monitor installation, reset or Bluetooth
operation was performed in this input-prerequisite phase. The remaining native
producer/client/application wiring is required before input is called complete.


### Resident input endpoint: Anvil 370

Anvil 370 now exposes service-table ABI 1.9 slot 39, retaining the 200-entry
table and all existing signatures. A portable client validates old tables,
capabilities and complete events before publishing them to the caller.
Failed Open descriptor validation retains the acquired context for checked
Close. Failed Close preserves ownership. Targets without a registered
provider answer ENOSYS; no unsupported device is advertised as attached.

The Pi4 adapter uses the existing HID and touch drivers. It does not reset
or enumerate USB while opening a payload. It separates physical key edges,
named navigation and printable text, tracks modifier-only changes, and
provides bounded key repeat. Mouse coordinates retain one position owner;
the monitor cursor does not paint over payload graphics. Touch has one
consumer and rearms only after a fresh validated empty frame. Devices held
before Open, cancellation or return cannot become a new press by replay.
Raw touch consumers refuse while native input owns the stream.

Input scope retires before console restoration, with the existing shared
quarantine/recovery policy for failed cleanup. Pi4 CPU capture 491 passes 88
portable-client checks with a controlled provider; 183 damaged reports refuse.
The same client compiles for UnoQ, with no execution claim there.

Actual resident captures 492 and 493 each pass 38 boundary/lifetime checks.
The first deliberately returns with input still open; the next payload
successfully opens again, proving return cleanup. The report checker rejects
93 corruptions/truncations and invalid telemetry values. The observed live
capability mask is 4 (touch), at 1280x800. No physical events were generated.
Keyboard/mouse hardware actuation and the Neon application adapter remain
unverified; neither the full port nor interactive acceptance is complete.

Build 370 was installed with a verified 368 backup and reloaded SHA-256 checks
of the candidate and boot file, followed by one authorized reset and 90 quiet
boot seconds. Cores, resident font and Vulkan remain healthy, with zero
display timeouts and deadman off. Mandatory source publication gates and the
remaining image/effect and broader Vulkan work are still open.


### Native input in the composed application

The shared Neon native-input adapter now connects resident events to pointer
hover, left-button dragging, wheel input, named editor navigation and text.
It translates Ctrl+A/C/X/V from physical key edges once. The composed
application copies editor clipboard output into its own bounded buffer for
paste input. Cancellation clears captures; generation changes require a
cancel barrier. Held touch and mouse cannot steal each other's contact.
Right or middle button changes do not become left clicks.

The composed application builder selects this with --native-input. Scripted
injection remains explicit and mutually exclusive. Native mode uses slot 39
and never drains the raw touch service. Idle hover retains its position;
the input queue drains before drawing, with transient actions consumed once.

Pi4 capture 494 passes 125 controlled-record translation checks; 257 corrupted
reports/truncations refuse. Capture 495 runs the actual native input service
with the composed Vulkan application and drive-loaded PNG/derived fonts.
All 65 existing integration checks and all 90 frames pass, at 30.0003 FPS.
Mean frame work is 22.102 ms, maximum 23.523 ms; input averages 0.546 ms.
This is an idle-input render fixture: capability 4 (touch), zero physical
events. Hand-actuated controls, visible mouse cursor behavior and first-tap
rearming remain unverified. No interactive completion claim follows from it.
The same pure composed application compiles for UnoQ only. After returning,
cores, resident font and Vulkan are healthy, display timeouts 0, deadman off.


## Automatic PNG/BMP selection in legacy loaders

The existing SpriteLoadMemory/File service and native signatures now use a
shared decoder selector. The default remains the original BMP24/32 decoder.
Include neon_sprite_decoder_png.pbi after the existing Core CRC owner and
install an aligned caller-owned workspace with NeonSpriteDecoderPngInstall.
The unchanged legacy calls then select PNG or BMP from the encoded content.
NeonSpriteDecoderPngReset restores BMP. Explicit PNG APIs remain available.
JPEG, GIF, other image codecs and allocating convenience wrappers are not
implemented by this change.

NeonSpriteDecoderInstall accepts the same eight-argument decode contract
and a file-source byte limit, allowing further decoders without copying
upload or file code. Installation, reset and nested decoding refuse while
the decoder is active. Refused installation preserves the selected decoder
and workspace. Unexpected positive decode status becomes a provider error.
Installed code and scratch must remain valid; callers serialize operations.
Busy is -21325; an invalid positive provider status becomes -21326.
Custom providers must retain the decoder's validation and transactional
output contract; registration is not a hostile-code sandbox.

PNG uses its existing explicit workspace requirements and decode limits.
Install requires an aligned, representable span of at least 8192 bytes;
NeonPngInspect gives the exact image-specific workspace size. Too little
workspace refuses before publishing outputs. The installed file limit is
16 MiB; BMP's internal limit remains 4194432 bytes. Legacy file helpers query
the active decoder's limit. The native helper also refuses an oversized
read count and validates its encoded destination span before file access.

Pi4 capture 497 passes the unchanged 133 BMP/file checks plus 43 new registry/
PNG integration checks. It loads 1:/NPNG457.PNG using legacy SpriteLoadFile,
uploads the same encoded PNG using legacy SpriteLoadMemory, resets decoding
to BMP and successfully loads another BMP. It erases caller image/encoded/
scratch buffers before drawing. Independent readback checks 572 PNG RGBA
bytes, 143 mask bytes, 18304 PNG display pixels and 300 existing BMP pixels.
The checker rejects 109 changed reports/images. The source and PNG decoding
algorithm are reused; this is loader integration evidence, not a new codec
conformance or maximum-image performance claim.

An earlier capture496 used the original fixture helper names. The final
fixture has its own names; its changed binary was physically retested rather
than assumed equivalent. Both complete images are byte-identical.

The same pure application compiles for UnoQ only. The complete Pi4 native
composition also compiles with all three native entry points and the PNG
installer referenced so their code is emitted. That diagnostic was neither
installed nor executed; native HwFile-wrapper runtime remains unverified.
Anvil 370 remains installed, with healthy cores/font/Vulkan, zero display
timeouts and deadman off. No boot-image update, reset or storage write was
needed. Full engine effects/physical input and broad Vulkan remain open.


## GPU image updates for an offscreen canvas

NeonVkChromeImageSpriteCopyId(id, sourceImage, sourceLayout) updates an already
allocated sprite from a completed Vulkan image. NeonVkChromeImageSpriteCopy
selects ID 1. Initialize each destination once through the existing sprite
replacement API at the required size. Repeated copies reuse its allocation,
image view and descriptor; no host pixel readback or re-upload occurs.

The source must be a bound image on the same device, with TRANSFER_SRC usage,
the destination's exact extent, and GENERAL or TRANSFER_SRC_OPTIMAL layout.
The existing Vulkan copy owner validates its handle, device, bounds, layout
and non-aliasing rules. Source ownership and layout remain with the caller.
The call waits for completion and advances only that sprite's generation,
so a retained batch holding the old generation becomes stale.

Call between frames, after consuming the preceding presentation intent.
An active/pending frame, unconsumed present, unallocated slot or exhausted
generation refuses. A recording refusal preserves pixels and generation.
This update is in place: a failed submission poisons the renderer because
its previous pixels cannot be guaranteed. DestroyChecked must establish
device idle before resources are retired and the renderer is recreated.
Hardware submission-failure recovery has not been induced by this test.

Pi4 capture 500 passes 45 literal checks and 40960 exact sampled display-image
pixels. It renders a 64x32 red/green attachment on the GPU, copies it into
slots 1 and 16, changes the source to blue/yellow, then samples both old
copies. Updating slot 1 gives blue/yellow there while slot 16 stays red/green.
The source is not read back or re-uploaded; only the final sampled attachment
is copied into the independent host oracle. Clear-region pixels, generation
changes, stale-source refusal and subsequent valid rendering are checked.
The checker rejects 153 altered reports/pixel buffers. All 173 existing
Chrome procedure bodies are unchanged; two new public procedures are added.

The actual UnoQ monitor composition compiles both new entry points with the
absent backend, as counted build 88. This is compile evidence only. The first
wrapper attempt lacked EnableFloatingPoint and refused; the build transaction
restored its number before the corrected compile. No UnoQ execution or GPU
capability is claimed. Pi4 remains on Anvil 370, with healthy cores/font/Vulkan,
zero display timeouts and deadman off. No firmware write or reset was needed.

This supplies the GPU copy needed between the engine's offscreen rendering
and final sampled pass. A complete virtual-canvas owner, aspect-correct final
presentation/input inverse and optional CRT shader remain unfinished. The
64x32 fixture does not qualify maximum sizes or presentation throughput.


## Fixed canvas owner and aspect-correct final pass

The native Chrome canvas owner now creates its Vulkan attachment/view/
framebuffer, retains a sampled sprite, renders into the fixed canvas, copies
the completed image and restores the caller's display target. Its passthrough
draw fits the canvas to that target while preserving aspect ratio. The same
viewport record supplies inverse logical input coordinates in Q16 form.
The caller owns the final frame clear, completion and display transfer.

Canvas ownership prevents Chrome destruction until Close. Close can abort its
own source frame; it refuses to abort or consume a caller's final frame. Target
generation changes require explicit Retarget. Initialization and point output
cannot overlap live canvas state. Asynchronous source frames are joined before
copying; the caller's asynchronous final-frame setting is preserved.

Canvas presentation selects linear min/mag sampling, matching the original
engine's filter choice, through a new per-image Chrome filter operation.
Ordinary sprites and the atlas retain their nearest-filter defaults. One lazy
linear sampler lives until Chrome teardown. Sampling changes advance that
image's generation. This implementation uses clamp-to-edge addressing; no
general OpenGL texture-state parity or repeat-wrap support is claimed.

Pi4 capture 504 passes 161 checks and all 307200 final-image pixels across
0/90/180/270 degrees. The independent bilinear oracle allows one UNORM level
only in red/green channels at the 2240 interpolated boundary pixels; the other
pixels and all letterbox bytes are exact. A nearest-filter image fails this
oracle. It rejects 401 damaged reports/images. Earlier nearest captures 501/502
qualified 153/156 checks respectively; alias guards were added before 502.

Controlled CPU capture 503 passes 32 retirement checks using the exact current
producer-detach body with a controlled device-idle callback; 74 corruptions
refuse. A producer can now retire after render readiness is lost, once device
idle succeeds. A failed idle call retains ownership. This is not a physically
induced GPU fault. Final source also compiles with Anvil's actual UnoQ root and
absent backend, as counted build 90; no UnoQ execution is claimed.

See NEON_VK_CANVAS.md for APIs, ownership, initial scratch/heap costs and the
remaining physical display, application/input integration and CRT limitations.
Pi4 remains on Anvil 370, with healthy cores/font/Vulkan, zero display timeouts
and deadman off. No firmware write, reset, storage write or Bluetooth was used.
The full Neon port and broad Vulkan implementation remain unfinished.
