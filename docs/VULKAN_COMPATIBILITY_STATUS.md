# Vulkan compatibility status

Anvil's objective is full Vulkan compatibility on bare metal, with core 1.0 as
the first implementation baseline. Vulkan examples should be translatable to
PureMetal without replacing Vulkan's object, command, resource, shader, memory,
or synchronization model. This is not a claim that
Anvil currently implements Vulkan 1.0, passes the Vulkan CTS, or may be
described as a conformant Vulkan implementation.

The prerequisite for honest non-native image extents is implemented and
silicon-proved in `docs/VULKAN_DYNAMIC_RENDER_GEOMETRY_DESIGN.md`. The public
image-format query derives its limits from that same geometry and pitch owner.

The schema target is `VK_API_VERSION_1_0`. Names and layouts are pinned to the
official Khronos `Vulkan-Headers` tag `v1.4.350`, commit
`8864cdc896bbc2a9b6eb36b3218fc9ef57908d77`. The pinned `registry/vk.xml` has
SHA-256
`50BD8C0F316EABF73D1C5FE3ADD2D89EAA480DBDA9282C12C289E80E9D081E08`.
The pin defines the generated vocabulary; it does not imply support for Vulkan
1.4 or even complete Vulkan 1.0 behavior. The registry-derived material retains
the Khronos MIT notice in `licenses/Khronos-Vulkan-Registry-MIT.txt`.

The complete physical-device properties ABI is exposed and checked.
`vkGetPhysicalDeviceProperties` reports the backend's bounded 2D capability
and leaves unsupported 1D/3D limits at zero rather than inventing image
support. Core Vulkan's required limits include 4096 for 1D/2D and 256 for 3D;
the current Pi 4 image bound derives from the active Neon surface capacity.
This truthful query describes an incomplete device, not Vulkan 1.0
conformance. The image capability contract still needs those dimensions and
limits before a conformance claim is possible.

## Latest installed checkpoint - 29 October 2026

Anvil 391 is installed and verified by its running-image SHA-256, with a
verified 390 rollback image retained. The final CRT pass now writes the
completed scene without blending its alpha a second time; ordinary primitives
retain their original blending. Forum issue 1518 is fixed and closed with
physical Pi 4 evidence. Issue 1519, an incorrect grayscale assumption in the
placeholder-text checker, is also fixed and closed.

Capture 101 validates the full composed resident CRT scene: 90 frames,
65 state assertions and 169 transformed geometry, particle and PNG probes,
plus sprite, line and text coverage. The original checker refusal is retained;
the corrected palette evaluation of the same capture passes and rejects 147
damaged controls. Native input was open with zero observed events; this does
not establish physical interaction. CRT averaged 29.72 FPS with a slowest
work frame of 47.8 ms, so consistent 30 FPS remains unfinished.

Normal-mode capture 102 passes its full rendering checks and 65 assertions
over 90 frames, meeting the 30 FPS target with a 32.85 ms maximum work frame.
Both runs returned normally with healthy cores, fonts and Vulkan, no display
timeouts, and the watchdog off. Evidence is retained in
`docs/evidence/composed-crt102-20261029`. The earlier 64 MiB resident heap
and scripted curved-input proof retain their separate scope.

The latest architecture review has 67 remaining findings; the provenance
inventory passes 1,411 checks. Source publication remains refused by the
architecture gate. The complete interactive engine and broader Vulkan
qualification remain unfinished. The numbered checkpoints below are historical
evidence, not current totals.

The initial reduction from 101 to 100 corrects a gate false positive: split SHA-512 constants
were mistaken for SHA-256 constants. Complete high/low pairs now have a distinct
ownership fingerprint; standalone SHA-256 code is still checked even inside
the SHA-512 owner. Five additional self-test cases pass. The ratchet was not
expanded, and that review still refused publication. Forum 1520
records the correction; evidence is in `docs/evidence/layering-sha-20261029`.
The subsequent reduction to 99 documents the missing HAL contract for
`HwPmfStackAllowed`, already implemented by the Pi 3, Pi 4 and Arduino Q
memory-policy owners. Executable tokens are unchanged; a focused declaration
test still rejects a similarly named undeclared helper. Evidence is in
`docs/evidence/pmf-stack-seam-20261029`. Publication remains refused.
HMAC and HKDF now have shared `Anvil/Crypto` owners, with compatibility includes
at their original Pi 4 paths. Executable tokens and the focused compiled image
are identical before/after relocation; provenance passes 1,404 checks and the
architecture refusal remains at 99 findings. This is dependency ownership
work, not new cryptographic or other-board runtime qualification. Evidence:
`docs/evidence/shared-kdf-20261029`.
AES-GCM and the TLS 1.3 record layer likewise now have shared owners and
compatibility includes. Their focused composition is byte-identical before
and after relocation, preserving authentication/refusal code. Provenance
still passes 1,404 checks; architecture remains refused with 99 findings.
The handshake dependencies remain unfinished. Evidence:
`docs/evidence/shared-record-20261029`.
The certificate/key-exchange dependency group now has shared owners as well,
with byte-identical implementation files and compatibility includes. A linked
certificate-verification/X25519 composition produces identical compiled bytes;
source-reading test tools use the new owners. The trust-store downward calls
are removed, reducing findings from 99 to 96. Provenance passes 1,404 checks.
No new runtime/cryptographic qualification is claimed. Evidence:
`docs/evidence/shared-certificates-20261029`.

The subsequent presentation-paced CRT run (capture 104, same installed 391)
removes the extra application timer that drifted against synchronized display
refresh. All 89 warm completion intervals lie between 33.285 and 33.303 ms,
about 30.029 FPS, with the full state and image checks passing. The explicit
`--present-paced --retro` mode retains display synchronization and ownership;
the default timer-paced test remains available. First-frame setup still takes
47.125 ms. This resolves the recurring pacing hitch, not rendering throughput
or full performance qualification. The cadence checker rejects the earlier
49.951 ms gap. Evidence: `docs/evidence/composed-crt-pacing104-20261029`.

## Earlier resident-target checkpoint (380) - 28 October 2026

Anvil 380 is installed and verified by its running-image SHA-256. Wi-Fi/DHCP
and console responses work; post-hash CPU samples are 5.96-12.55 percent.
The 378 startup regression came with an unsafe cold-cache declaration:
cache-off alone was treated as proof of prior dirty-line retirement. The owner
now grants the V3D skip only after its completed flush and revokes it before
enabling caches. The original 375 backup, failed 378 image and recovery records
are retained. Controlled CPU testing finds eight violations in the old owner
bodies and none in the candidate; the callbacks do not execute MMU operations.
The real 379/380 boots provide the separate monitor execution evidence.

The resident opaque-target client passes 108 exact rows, eight color/filter/
camera probes and filtered text coverage. It checks sixteen targets, context
reuse, bound close, resize, abort preservation, stale handles and loader-owned
final cleanup. A legacy preparation defect was also corrected: line height
contains spacing and differs from the glyph raster size. The original 379
failure and fixture capture/oracle refusals remain evidence, not passes.
The existing composed native-input/assets application passes 65 checks and
90 frames on 380, with no physical input records. See the
[canvas contract](NEON_VK_CANVAS.md) for qualified shapes and remaining work.

Native captures 545/546 and CPU absence 547 keep their earlier scope. UnoQ
root 98 is compile-only with no GPU capability. Source publication, complete
engine/effects/input behavior and general Vulkan remain unfinished. Older
dated checkpoints below retain their original scope.

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

## Earlier shared-boundary checkpoint (371)

The latest shared-boundary review removes 10 architecture finding keys,
leaving 107 architecture findings and 98 unchanged provenance omissions.
Byte-order and prompt-counter ownership now use shared or published owners;
the exact declared runtime-hook rule has regression coverage. Pi4 capture
499 passes 99 standalone DNS/byte-order/counter checks, including a corrected
terminal-dot DNS wire format. Normal Anvil 371 compiles but is not installed;
370 remains resident. This is publication prerequisite work, not a new Vulkan
rendering capability. See [the qualification](PUBLIC_NETWORK_CLOCK.md).

The current shared-module review refuses 117 new/grown architecture keys and
98 provenance omissions. Eight Neon renderer/adapter modules
now have shared .pbi owners. The prepared-lifecycle installer is an explicit
shared integration header, preserving its implementation and Pi4 callable API.
The actual UnoQ core/file-seam composition compiles Chrome with the absent
backend. All 233 implementation bodies, the complete Pi4 composition, scene
proof and native-transition proof retain exact executable/container identity.
The last two therefore link to the already recorded physical captures 362/364;
no fresh GPU run is claimed for file ownership changes. A fresh read-only Pi
check confirms build354, healthy cores, active Vulkan and zero present timeouts.
See [shared-module evidence](evidence/neon-shared-modules-20261027/README.md).
A separate controlled-provider binder regression passes18 exact fields on Pi4
and compiles on UnoQ;22 checker-only corruptions are refused. The ordinary binder
keeps its public-provider contract without importing the prepared bridge.
The full Neon port, wider Vulkan implementation and source publication remain
unfinished.

The earlier shared Neon primitive dispatch review refused 130 new/grown architecture
keys. Public primitive wrappers now have a shared owner with independently bound
native fallback and optional external families. Actual Pi4 tests pass 96 dispatch
assertions, 38 ordered callback events, all 245760 current-contract scene bytes
and 124 widget checks. Native frames around real Vulkan creation/render/teardown
are byte-identical with checked counters and pixel probes. The native runtime
stays board-owned; UnoQ receives a compile-only shared-contract check. See
[dispatch evidence](evidence/neon-primitive-dispatch-20261027/README.md).
Source publication remains unaccepted and the full port is unfinished.

The earlier GPU ownership and explicit backend composition review refused 140 new/grown architecture keys and 98 provenance omissions across 991 sources. Pi4 GPU runtime modules are in their board library; typed IR lowering remains shared as .pbi. The selector validates an explicitly supplied implementation. Five representative programs across four targets and the GPU proof preserve exact executable bytes; the latest 15-scene physical Pi run passes all 245760 current-contract pixel bytes and 124 widget checks. The corrected software smoke also passes on Pi4 as CPU execution. See [GPU ownership evidence](evidence/vulkan-gpu-owner-20261027/README.md). Source publication remains unaccepted; older phase counts below are historical.

The earlier board-test ownership review refused 199 architecture findings and 98 provenance omissions across 991 sources. Sixty-one board-specific test/fixture sources moved to the proper board trees, with five compiled programs byte-identical across four targets. Removing shared mock owners exposed real production-to-board dependencies; these are recorded, not waived. See [ownership evidence](evidence/vulkan-board-test-ownership-20261026/README.md). Source publication remains unaccepted. Earlier phase counts below are historical.

Bitmap fallback text now supports source-canvas scaling and camera mapping through the shared Neon Vulkan atlas, including source-space alignment and same-frame refusal/retry. The final24-frame/four-rotation GPU proof and existing15-scene regression pass; see [mapped bitmap evidence](evidence/neon-bitmap-mapped-pi4-20261026/README.md). This is Anvil implementation work, not desktop Vulkan or full-engine completion.

The float Neon geometry adapter now derives line and polygon capacities from the shared native point budget. Physical boundary/callback tests and twelve actual GPU frames across all four rotations pass beyond its old4096-point/2048-side guards. This closes adapter capacity guards, not full port or throughput qualification; see [the evidence](evidence/neon-float-port-capacity-pi4-20261026/README.md).

The five surface commands use the standard C ABI and public query semantics. The final state-only physical proof covers 24 cases / 192 observations plus a 167-check core-dispatch regression. The full pinned-registry rerun remains unverified this phase; see the exact evidence scope below.

Current Pi4 monitor 354 enables VK_KHR_surface revision 25 and validates its real DSI main/banner metadata through the public queries. The earlier 353 geometry/renderer-return matrix passes with WSI completion and public target-check counters. Build 354 additionally passes automatic Vulkan startup and native/Vulkan selection with fresh captures; see the shared dispatch evidence. VK_KHR_swapchain/device extensions, blocking acquire, HDMI and real hardware-fault recovery remain incomplete. See `docs/evidence/vulkan-public-surface-pi4-20261026/README.md`.

The normal Pi 4 build starts the resident Vulkan/Neon console after the
framebuffer and shared grid are established. A clean startup failure tries the
native V3D console, then leaves the DMA/CPU framebuffer renderer in place if
the GPU is unavailable. An unsafe GPU handoff failure quarantines the screen
rather than transferring ownership. The explicit `screen vulkan`, `screen v3d`,
`screen dma`, and `screen cpu` commands remain available. Historical build244 was
installed on the Pi4 and reached a real prompt over Wi-Fi after reset, with
the Vulkan console selected before USB/storage setup. A live 1280x800 capture
shows its TrueType banner and clock, CPU, temperature, and fan caption; the
caption layout is initialized before Vulkan's first frame instead of depending
on a skipped CPU banner draw. This verifies the measured Pi 4 boot and screen,
not recovery on every display or network failure. Before/after screenshots,
checksums, and the boot-file verification are in
`docs/evidence/pi4-build244-banner-20261003/README.md`.

The Pi 5 full Anvil monitor is built from `RaspberryPi4/Board/board.pi4` under
its BCM2712 branches, not from the older `RaspberryPi5/Boot/board.pi4` entry
probe. The 2026-09-27 Pi 5 run reached an EL3 prompt from commit `f385c7b`.
Current source still disables both V3D and Vulkan console startup for BCM2712:
`V3dBinSubmit`, `V3dRenderSubmit`, and ownership reset refuse unported V3D 7.1
work. The shared Vulkan dispatch and backend-selection seam exists, but its
V3D implementation and shader records remain Pi 4/V3D 4.2. There is no Pi 5
Vulkan hardware-acceleration claim; the current tree has not been rerun on
Pi 5 silicon during this work.

On Pi 4, the Neon Vulkan adapter accepts separately allocated sampled BGRA8
sprite images at IDs 1 through 16 beside its shared TrueType/sprite atlas.
The unindexed calls still select ID 1. RGBA input is converted; already-BGRA
input uses a checked CPU word copy before hardware upload. Returning RAM
proofs on resident build 242 verified the original image replacement path,
including odd-width half-alpha BGRA pixels. A further RAM proof drew the atlas
and separate IDs 1 and 16 together, verified both slots' pixels and handles
after an oversized replacement refusal, replaced ID 16 without changing ID 1,
and checked clear and repeated teardown. A further Pi 4 RAM proof loaded all
16 separate IDs simultaneously as small distinct BGRA images beside the atlas,
checked pairwise-distinct live image and descriptor handles, drew all 16 in
one ordered frame, refused invalid ID 17, matched every output pixel and
verified teardown. This proves the 1Ã—1 shape, not aggregate capacity for
large images. Indexed
separate-image drawing now uses the same rotation, camera, zoom, crop and tint
geometry as atlas sprites, while binding each image's descriptor. A Pi 4 RAM
proof checked rotated ID 16 quadrants, a cropped/tinted camera-zoomed draw,
atlas and ID 1 coexistence, and extreme-coordinate refusal before draw-record
mutation. The original atlas transform passed its full pixel-oracle regression.
See `docs/evidence/neon-multi-image-transform-pi4-20261003/` and
`docs/evidence/neon-sixteen-images-pi4-20261003/`. Other boards have
no hardware proof for this path. The full Pi 4 monitor desk-compiles with this
source but has not been installed; the latest image reaches `$70214F`. A future RAM
payload at `$700000` would overlap it. Use the running monitor's `map` output
for staging.
Evidence is in
`docs/evidence/neon-separate-sprite-pi4-20261002/`,
`docs/evidence/neon-sprite-bgra-pi4-20261003/`, and
`docs/evidence/neon-multi-image-pi4-20261003/`.

The Pi 4 Neon adapter's TrueType cache lookup now uses a bounded 1,024-slot
index over at most 512 cached glyphs, with full font slot, generation, pixel
height and glyph identity checks. A returning RAM diagnostic on resident build
242 passed a deliberately colliding 512-key lookup, miss, full-table refusal,
reset and teardown oracle. The unchanged sixteen-image atlas/GPU pixel proof
also passed after recompilation against the indexed adapter. These checks do
not re-prove real TrueType glyph raster pixels or show a measured frame-rate
gain. See `docs/evidence/neon-tt-index-pi4-20261003/`. This change was
desk-compiled before installation and is part of the later installed build
244; the returning cache diagnostic remains the specific silicon proof.

The Pi 4 Neon adapter now batches new TrueType atlas texels into one bounded,
source-aligned dirty rectangle (at most 256 UIF tiles) instead of uploading
the full 512Ã—1024 BGRA atlas for each new glyph. Full uploads remain for cache
reset, bitmap revision changes and larger unions. The partial path requires
`BUFFER_TRANSFER`, `LINEAR_TRANSFER` and `BUFFER_TO_TILED_RECT_COPY`; a
backend lacking those capabilities selects the full path. A returning RAM
proof on build 242 passed exact GPU pixel and untouched-atlas checks for
4Ã—8 and 4Ã—4 uploads, with guarded DMA operations 2 and 1 versus a
complete 2,097,152-byte upload. The unchanged all-16 image/atlas GPU
regression also passed after recompilation. These are synthetic staging pixels,
not a repeat of real TrueType rasterization, measured bus traffic or frame
rate, and only Pi 4 was run on hardware. See
`docs/evidence/neon-tt-partial-pi4-20261003/`. The updated full Pi 4 monitor desk-compiled with `--no-bump` as a
5,251,408-byte image, SHA-256
`F69BB278AB44B768A373A2773882CC80D85A2EFEABF1903D0C39A99D0E349DAF`,
linked at `$200000..$70214F`; that particular image was not installed.
The later installed build 244 includes the source change and has the same
image extent. Any future RAM stage must use the running monitor's live `map`.
The production Pi 4 backend's physical-device properties query also passed a
returning RAM payload on 2026-09-26. Its report returned status zero with an
integrated-GPU device type, 1280-pixel 2D/framebuffer maxima, a 16-byte
uniform range, one bound descriptor set, 64-byte copy-source alignment and
zero compute capacity. The committed diagnostic returned `x0=0`, produced fresh capture 32,
and left the monitor at its prompt with the deadman off. The normal image's
boot-default selection remains a separate untested boot path.

The full native/Vulkan Neon pixel oracle now passes on Pi 4: one returning
RAM-only Vulkan producer rendered all 15 scenes, and all 245,760 BGRA bytes
matched the native V3D capture. Scene 14's zero-width rebind was refused as
expected before a valid rebind; the normal widget frame then rendered with
47 draws and 654 vertices. The build-210 board run used a 15-second deadman,
returned after 12.3 seconds, produced fresh capture 27 and was released with
the deadman off and all core leases zero. Its source, raw pixels, report,
capture and SHA-256 manifest are in
`docs/evidence/vulkan-paired-all15-20260926/`. This is a bounded Neon
compatibility proof, not Vulkan 1.0 conformance or CTS coverage.

On 2026-09-26, the resident Neon adapter gained an explicit `Neon_TextTex`
callback. It preflights the visible glyph run, retains the public bitmap font
metrics and clipping rules, and emits one atlas-sampled Vulkan draw. Selecting
a font now advances the CPU atlas revision even when its bitmap address is
reused. A quiescent Vulkan frame refreshes the bitmap columns before recording
and publishes the new revision only after the upload completes; an uncertain
upload poisons the adapter until recreation. This is a fail-closed in-place
refresh, not the separate-image transactional replacement described in
`docs/NEON_VULKAN_RESOURCE_LIFETIME_DESIGN.md`.

The native 15-scene oracle passed on Pi 4 build 210 with its full 245,760-byte
capture saved in `docs/evidence/neon-texttex-20260926/`. A separate real Vulkan
widget frame using `Neon_TextTex` passed 129 report and rotated-pixel checks.
These were distinct early proofs: the 15-scene Vulkan producer and native/Vulkan
pixel comparison were still outstanding at that stage. Its capacity scene would request
4,687 Vulkan draws through one-call/one-draw lowering, above the shared
4,096-record ceiling. An opt-in same-tint/same-scissor box batch now lowers
its 3,505 consecutive boxes to one ordered draw; the 19-assertion emitted
gate proves that exact count, capacity refusal, and colour mismatch on the
desk. The paired producer must use `NeonVkChromeCreateWithCapacities` to
reserve at least 6,373 vertex quads as well as the separate draw budget.
The box batch now also passes a real Pi 4 Vulkan frame: 3,505 boxes lower to
one draw and 21,030 vertices, followed by the established widget frame with
47 draws and 654 vertices. The final widget capture passed 212 independent
report and rotated-pixel checks under a 15-second deadman; see
`docs/evidence/vulkan-box-batch-20260926/`. The first larger-buffer attempt
correctly refused allocation within the diagnostic's 8 MiB Vulkan window;
the passing run used 12 MiB within its mapped RAM span. The subsequent paired
producer and pixel comparison are recorded above and scene by scene below.

The next Pi 4 RAM diagnostic rendered native oracle scene 1 (three ordered
boxes, including source-over alpha and a clipped negative-origin box) through
the resident Vulkan adapter before the unchanged widget frame. A CRC-checked
readback of the completed GPU attachment matched all 16,384 BGRA bytes of the
saved native scene exactly. The returning build-210 run used a 15-second
deadman, returned its expected report pointer, and produced fresh capture 8;
the widget frame passed 133 report and rotated-pixel checks. Evidence is in
`docs/evidence/vulkan-paired-boxes-20260926/`. This first pair uses the
top-left 64x64 region of an 800x1280 attachment. It does not yet exercise
Vulkan rebind, odd extents, rotated targets, glyph parity, or the remaining
14 native scenes.

Native oracle scene 2 now also has a Pi 4 Vulkan pixel pair. Its first run
identified 100 missing ink pixels in the bold flat face: every missing pixel
sat immediately right of existing ink. The adapter now stages Neon's
one-pixel emboldened bitmap in reserved atlas columns 16..31 and selects it
for the bold flat-text face. The final GPU readback matches all 16,384 bytes
of the native 256x16 scene, which includes four flat-font calls and three
textured-font calls covering printable ASCII. The same run returned cleanly
under a 15-second deadman, produced fresh capture 10, and passed 133 widget
report/pixel checks. See `docs/evidence/vulkan-paired-glyphs-20260926/`.
The current selection follows the default bold face index; altered bold
settings through `NeonFontSetup` still need a renderer-neutral state query.
The paired text proof uses a 256x16 scissor on the existing 800x1280 target,
so target rebind and the remaining 13 native scenes still need proof.

Native oracle scene 3 now passes the same full-pixel Pi 4 comparison: two
nested scissors and a final zero-size clip leave exactly the native 16,384
BGRA bytes. The RAM payload returned under the 15-second deadman with fresh
capture 11, and the established widget frame still passed 133 checks. Its
report, raw clip pixels and capture are in
`docs/evidence/vulkan-paired-clips-20260926/`. Three native scenes are now
paired; the Vulkan producer still uses one oversized attachment rather than
the oracle's changing target extents.

Native oracle scene 7 now passes a full-pixel Pi 4 Vulkan comparison as well:
two overlapping half-alpha boxes yield exactly the native 16,384 BGRA bytes.
The returning build-210 RAM payload used a 15-second deadman, produced fresh
capture 12, and the established widget frame passed 133 report/pixel checks.
Evidence is in `docs/evidence/vulkan-paired-alpha-20260926/`. Four native
scenes are paired; the remaining 11 scenes and changing target extents still
need proof. The first alpha candidate was safely refused before entry because
its linked address overlapped the monitor; the successful image was rebuilt
for the board's `00600000` RAM window.

Native oracle scenes 4 and 5 now also have exact Pi 4 Vulkan pixel pairs.
The adapter centres its triangle-strip lowering on the integer line path;
the earlier one-sided strip missed 53 fan-outline pixels. The corrected
four-point fan outline with alpha fill matched all 16,384 native BGRA bytes
in scene 4. A separate crossing-diagonal line list with a degenerate point
matched all 16,384 bytes in scene 5. Both returning RAM payloads used a
15-second deadman and produced fresh capture 16 from the final source. The board was
released with the deadman off and all core leases zero. See
`docs/evidence/vulkan-paired-lines-20260926/` for both reports, readbacks,
captures, and SHA-256 manifests. Six native scenes are paired; the other
nine and changing target extents remain to be tested.

Native oracle scene 6 also matches exactly on Pi 4: an opaque box, textured
text inside a scissor, and a diagonal line after clearing that scissor kept
the native draw order and all 16,384 BGRA bytes. The RAM payload returned
under a 15-second deadman with fresh capture 17; the board was released with
deadman off and core leases zero. See
`docs/evidence/vulkan-paired-order-20260926/`. Seven native scenes are now
paired, with eight scenes and changing target extents still outstanding.

Native oracle scene 8 now matches the 16,384-byte Pi 4 Vulkan crop too:
single pixels at both corners survive, and the box starting at (64,64)
does not affect the captured 64x64 region. A first crop-only run used the
800x1280 attachment. The final run instead created a separate 64x64 image,
view and framebuffer, rebound the adapter to that exact target, then restored
the 800x1280 widget target. Its render-area, viewport and framebuffer extent
therefore matched the native target. The RAM payload returned under the
15-second deadman with fresh capture 22, and the board was released cleanly.
See `docs/evidence/vulkan-paired-edges-20260926/`. This brought the paired
count to eight before the rotated targets below.

Native oracle scenes 9..12 now match on Pi 4 too. Each has a 63x47 logical
target; the adapter used separate exact-size images and framebuffers for
physical extents 63x47 or 47x63 at rotations 0, 90, 180 and 270 degrees.
All four complete 16,384-byte scene buffers, including the native A5 guard
area outside the active rows, matched byte-for-byte. The returning RAM
payload used a 15-second deadman, produced fresh capture 23, restored the
800x1280 widget frame, and left the board free with no core leases. Evidence:
`docs/evidence/vulkan-paired-rotations-20260926/`. Twelve of the 15 native
scenes are paired; scenes 0, 13 and 14 remain.

Scene 0's clear-only render pass now matches the native 64x64 frame across
all 16,384 bytes on a separate exact-size Vulkan target. The returning Pi 4
RAM payload produced fresh capture 24 under the 15-second deadman and
restored the widget frame; the board was released cleanly. See
`docs/evidence/vulkan-paired-clear-20260926/`. Thirteen native scenes are
paired; the stress-capacity scene 13 and rebind/error scene 14 remain.

Scene 13 now matches all 16,384 native bytes on an exact-size Vulkan target.
Its 3,505 boxes used one ordered same-colour batch, followed by 1,182 flat
and textured text draws. The adapter reserved exactly 1,183 draws and 6,373
vertex quads; the earlier 47-draw widget reservation correctly refused the
stress load instead of overrunning. The returning Pi 4 RAM payload completed
in 12.2 seconds under the board's 15-second deadman, produced fresh capture
26, restored the widget frame and released the board cleanly. Evidence:
`docs/evidence/vulkan-paired-stress-20260926/`. Fourteen native scenes are
paired; scene 14's rebind and expected-error behavior remains.

The final Pi 4 run added scene 14's invalid zero-width rebind check, a valid
rebind to the same exact 64x64 target, and its `GEN2` flat and textured text
frame. All 15 scenes were read back from that one run and compared in native
scene order, with zero differing bytes across 245,760. The full report still
shows a successful restored widget frame. See
`docs/evidence/vulkan-paired-all15-20260926/` for the complete corpus.

Updated 2026-09-11, when the SPIR-V front end and the first graphics
pipeline landed, and again the same day when three things followed it: a real
interpolated gradient, a second vertex input binding, and the first descriptor
type. Updated 2026-09-12 when that descriptor stopped being copied by the CPU
and gained a V3D 4.2 TMU general-load lowering. Updated 2026-09-13 when dynamic
render geometry and the matching public image-format-properties query passed
their desk and Pi 4 silicon gates, and again when the bounded optimal-image
copy and greater-than-one-texel sampled path passed desk and silicon gates.
Updated 2026-09-16 when command buffers gained bounded ordered draw lists and
the Pi 4 backend began lowering a whole list through one V3D frame transaction,
then when public per-draw dynamic scissor, one-barrier cache batching, and the
atlas/chrome acceptance scene closed the remaining prerequisites for starting
the Neon-to-Vulkan adapter. Updated 2026-09-17 when bounded UINT16/UINT32
indexed triangle-list recording, submission validation and V3D 4.2 packet
lowering passed their emitted desk gates. The bounded UINT16 indexed board
diagnostic passed on Pi 4 silicon on 2026-09-26; see
`docs/VULKAN_INDEXED_DRAW_2026-09-17.md`. The bounded UINT32 diagnostic also passed on Pi 4 silicon on 2026-10-01; see `docs/evidence/vulkan-indexed-uint32-pi4-20261001/README.md`.
The bounded public buffer-copy/fill/update stream passed a Pi 4 RAM diagnostic
on 2026-09-26; see `docs/VULKAN_BUFFER_TRANSFER_PI4_2026-09-26.md`. The
65,536-byte update limit also passed on Pi 4 silicon through DMA. The production Pi 4
backend now performs these transfers by DMA. A follow-up RAM diagnostic
proved five DMA operations, exact destination bytes, and restoration of a
non-Vulkan DMA write bound; see the same hardware record.
The Pi 4 V3D backend advertises buffer and linear-image transfer capabilities
only when its board DMA seam is linked. The public recorder refuses buffer
copy/fill/update and DMA-dependent image commands without that capability;
submission rechecks a recorded stream before claiming resources or starting
backend work. Complete optimal-image TFU uploads and optimal-to-optimal copies
remain independent. There is no processor byte-loop fallback. The desk test
backend retains its explicit byte oracle.
The graphics triangle diagnostic now creates a live same-device pipeline cache,
reads its 32-byte header, and passes the cache to both graphics-pipeline
creations. The committed source at `5f9172d` ran on Pi 4 silicon from RAM on
2026-09-26: the board verified the 901,364-byte container with SHA-256
`D292F08CC1EB10CC8097A62F0A637137EFE6F1B96A1FC4AA95EFB287E176DD26`,
the report at `$00AD46E0` had zero status in slots 1 and 4, exact red/green
triangle and background probes, and the monitor took fresh capture 34. Evidence
is in `runs/vulkan-cache-triangle-20260926/run2/`. This proves pipeline
creation and drawing with a non-null cache; it does not prove binary reuse or
booting the newer Vulkan-default monitor image. Its presentation step used
the CPU `DisplayBlit` path, so the capture did not prove accelerated transfer
to the scanout surface. The triangle diagnostic now links the display DMA
path for every variant and requires one completed DMA operation to pass.
The corrected 921,752-byte RAM payload with SHA-256
`F94E41DB97C984F20211E48B30484DE79BD83614D6EEE300F9495C1692E683B4`
returned zero status on the same Pi 4 on 2026-09-26. Its report at `$00AE4A20`
recorded two new V3D bin jobs, two render jobs, one completed display DMA
operation, and fresh capture 36. Evidence is in
`runs/vulkan-cache-triangle-20260926/dma2/`.

The Pi 4 Vulkan console once copied its finished V3D raster to scanout row by
row on the CPU and retained separately painted banner and keyboard bands.
The current console renders its banner, text, cursor and keyboard in the
Vulkan/Neon frame, then presents the complete image through bounded display
DMA. A refused transfer causes Vulkan presentation failure and renderer
failover rather than a silent CPU copy within the Vulkan tier. Build 242 has
booted with this renderer selected and reached a prompt over Wi-Fi; that boot
does not establish a measured live frame rate or every display-mode path.

### The implemented public entry points

These are callable `vk*` names with the registry's own parameter lists and
return types. Everything else in core 1.0 does not exist and a caller linking
one gets a compile-time refusal naming it.

| Entry point | Status |
|---|---|
| `vkCreateInstance` / `vkDestroyInstance` | Supports VK_KHR_surface instance enablement; unknown extensions and layers refuse. Permission resets on slot reuse. Destruction refuses live child devices/surfaces and retains its original diagnostic. |
| `vkEnumeratePhysicalDevices` | Implemented, including the two-call `pPhysicalDeviceCount` form and `VK_INCOMPLETE`. |
| `vkEnumerateInstanceLayerProperties` / `vkEnumerateInstanceExtensionProperties` / `vkEnumerateDeviceLayerProperties` / `vkEnumerateDeviceExtensionProperties` | Layer/device-extension lists are empty. Instance extension discovery reports VK_KHR_surface revision 25 with proper count/capacity and VK_INCOMPLETE behavior. Named-layer queries refuse. |
| `vkGetPhysicalDeviceMemoryProperties` | Implemented. One heap, backend-reported. |
| `vkGetPhysicalDeviceFormatProperties` | Implemented. Linear `B8G8R8A8_UNORM` reports `SAMPLED_IMAGE`; a draw-capable backend additionally reports `COLOR_ATTACHMENT`, and a backend with the independent exact source-over capability additionally reports `COLOR_ATTACHMENT_BLEND`. A backend with the optimal-image planner reports optimal `SAMPLED_IMAGE`; buffers and unsupported formats report zero. Storage, depth/stencil and blit support are not advertised. |
| `vkGetPhysicalDeviceImageFormatProperties` | Implemented for the exact combinations `vkCreateImage` accepts: bounded 2D `B8G8R8A8_UNORM`, flags zero, one mip/layer/sample, with linear usage within transfer/sample/attachment rules and optimal usage limited to transfer source/destination plus sampled. It reports backend-derived maxima and resource size; every other combination returns `VK_ERROR_FORMAT_NOT_SUPPORTED`. |
| `vkGetPhysicalDeviceSparseImageFormatProperties` | Implemented. Sparse residency is not supported, so the query returns zero properties and leaves supplied property storage untouched. |
| `vkGetPhysicalDeviceQueueFamilyProperties` | Implemented. One family always advertises `VK_QUEUE_TRANSFER_BIT`; it also advertises `VK_QUEUE_GRAPHICS_BIT` exactly when the linked backend has the draw capability. A transfer-only backend remains transfer-only. Compute is not advertised. |
| `vkGetPhysicalDeviceFeatures` | Implemented. The complete 55-member core-1.0 structure is written and every member currently reports `VK_FALSE`. |
| `vkGetPhysicalDeviceProperties` | Implemented for the complete core-1.0 ABI record. It clears every member, then reports backend-derived 2D/framebuffer extent and copy alignment plus the bounded descriptor, allocation, sampler, single-sample and one-queue graphics limits the implementation owns. Unsupported dimensions, shader stages and features remain zero; some values are below Vulkan 1.0 conformance minima, so this is a truthful capability query, not a conformance claim. Invalid handles leave caller storage untouched. |
| `vkCreateDevice` / `vkDestroyDevice` / `vkGetDeviceQueue` | Implemented for one queue of family 0. Device extensions and any true feature bit are refused; a null or non-null all-false `pEnabledFeatures` is accepted. Teardown retires quiescent generation-matched semaphores while the device is still live and refuses atomically if a reservation or submission remains pending. |
| `vkCreateImage` / `vkDestroyImage` | Implemented for bounded 2D `VK_FORMAT_B8G8R8A8_UNORM`, one mip, one layer, one sample and exclusive sharing. Linear usage is bounded to the implemented transfer/sample/attachment rules. Optimal usage is exactly the backend-planned transfer-destination/sampled subset. Unsupported combinations are refused with a real code. A framebuffer attachment must carry `COLOR_ATTACHMENT`; a transfer bit does not substitute for it. |
| `vkGetImageMemoryRequirements` | Implemented. Size, alignment and `memoryTypeBits` come from the backend. |
| `vkGetImageSparseMemoryRequirements` | Implemented. Every accepted image is non-sparse, so a live image returns zero requirements without writing the supplied array. Null count, stale handles and wrong-device ownership leave caller output untouched and record a fault. |
| `vkGetImageSubresourceLayout` | Implemented for the color aspect, mip zero and layer zero of a linear image. It reports the backend's image size and row pitch; array and depth pitch have no defined meaning for this 2D non-array image. |
| `vkAllocateMemory` / `vkFreeMemory` | Implemented over one backend heap, first-fit with real reuse of freed holes and a real `VK_ERROR_OUT_OF_DEVICE_MEMORY`. |
| `vkMapMemory` / `vkUnmapMemory` | Implemented for one active mapping of a `HOST_VISIBLE` allocation, flags zero, an overflow-safe positive subrange or `VK_WHOLE_SIZE`. The returned pointer includes the requested offset; wrong owner, duplicate map, invalid range, non-visible type, unbalanced unmap and free-while-mapped are refused. Pi 4 reports this heap `HOST_COHERENT` because mandatory submission/completion cache maintenance supplies the observable promise. |
| `vkFlushMappedMemoryRanges` / `vkInvalidateMappedMemoryRanges` | Implemented for valid mapped ranges of a `HOST_COHERENT` allocation. The complete input array is validated; coherent memory needs no extra host cache operation. Non-coherent types remain unsupported. |
| `vkBindImageMemory` | Implemented, with alignment, range, double-bind, wrong-parent and memory-type rules enforced. |
| `vkCreateCommandPool` / `vkDestroyCommandPool` / `vkResetCommandPool` | Implemented. |
| `vkAllocateCommandBuffers` / `vkFreeCommandBuffers` | Implemented for multiple command buffers per call. Allocation initializes every output to null, unwinds all partial allocations on failure, and frees arrays after validating every non-null handle and owner. |
| `vkBeginCommandBuffer` / `vkEndCommandBuffer` / `vkResetCommandBuffer` | Implemented. A recording error moves the buffer to invalid and `vkEndCommandBuffer` reports it, as the specification requires. |
| `vkCmdPipelineBarrier` | Implemented with its exact ten-parameter registry signature. Accepts an execution-only dependency, up to two image barriers for distinct images, and up to eight global plus eight buffer barriers scoped to the ordered coherent buffer-transfer path. It validates structure headers, access/stage scopes, buffer ranges and queue ownership. Recorded buffer barriers retain and revalidate their resources at submission. Shader/graphics memory scopes and render-pass global/buffer barriers are refused. The final count and pointer travel through the AArch64 stack argument area and are exercised through emitted code. |
| `vkCmdClearColorImage` | Implemented with its exact registry signature, for one whole-image range. |
| `vkCmdCopyBufferToImage` | Implements one to 32 2D BGRA8 regions from a transfer-source buffer into a bound linear transfer-destination image. Each nonempty rectangle may have an in-bounds XY offset, a source offset aligned to the Pi 4 backend's published 64-byte requirement, and tight or explicitly padded source rows. `bufferImageHeight` is zero or at least the region height. The complete array is validated before recording and rechecked before DMA, including source/destination and destination/destination overlap across regions and aliased allocations. Pi 4 lowers a tight full-width region to one guarded DMA transfer and other rectangles to one 2D DMA submission when hardware row geometry fits, with guarded DMA row copies for larger gaps. Tight and padded 17Ã—13 uploads passed on Pi 4 silicon with exact copied/untouched pixels; see `docs/VULKAN_LINEAR_UPLOAD_PI4_2026-09-27.md` and `docs/VULKAN_STRIDED_IMAGE_PI4_2026-09-27.md`. A two-region tight/padded upload returned `x0=0` on Pi 4 with eight DMA rows and exact whole-image bytes; see `docs/VULKAN_IMAGE_UPLOAD_ARRAY_DMA_PI4_2026-09-27.md`. Separate linear upload calls in one otherwise isolated command buffer execute in recorded order through guarded DMA; two calls passed on Pi 4 with eight rows and exact 1,024-pixel destination bytes (`docs/VULKAN_MULTI_CALL_UPLOAD_DMA_PI4_2026-09-27.md`). An optimal-tiled destination keeps one complete-image TFU transaction and the same 64-byte source alignment. It accepts tight or explicitly padded source rows through the TFU raster-stride register; an 8x8 padded atlas was sampled by V3D on Pi 4 with exact pixels (`docs/VULKAN_OPTIMAL_STRIDE_TFU_PI4_2026-09-27.md`). Multiple optimal regions remain unsupported. Buffer-to-image uploads and image-to-image copies may be interleaved in one transfer-only command buffer and execute in recorded order after whole-stream preflight; the Pi 4 TFU/V3D proof is in `docs/VULKAN_MIXED_IMAGE_TFU_PI4_2026-09-27.md`. Recording retains generation-tagged handles and immutable region state; submission revalidates live owners, bindings, usage, ranges and layouts, then publishes the final layout only after backend success. A separate partial optimal buffer-to-image path accepts up to two separate one-region calls per command buffer, targeting the same distinct optimal BGRA8 image. Each source buffer offset follows the Pi 4 64-byte alignment; tight or padded `bufferRowLength` uses the exact span `(height - 1) * pitch + width * 4`, explicit `bufferImageHeight` is validated, and destination offsets/extents align to 4Ã—4 utiles. The combined tile limit is 256; destination rectangles and source byte spans must be disjoint. The whole command stream is preflighted before guarded DMA dispatch, and calls execute in recorded order behind `BUFFER_TO_TILED_RECT_COPY`. Desk checks prove a 257-tile aggregate is refused before backend work; the exact 256-tile aggregate passed a separate Pi 4 RAM proof on 2026-10-01. The 2026-09-30 Pi 4 proof replaced 32 destination texels and preserved 224, with 288 source words including 48 source-padding words, 64 readback-padding words and 128 guard words checked. TFU stayed at 1, DMA advanced 0â†’2 and jobs 1â†’3; a later readback advanced DMA 2â†’18. A misaligned second operation was refused with `-20005` during recording before submit or DMA. See `docs/evidence/vulkan-two-partial-optimal-uploads-pi4-20260930/README.md`. The full-image TFU upload remains unchanged; other backends do not advertise this capability. Edge-tail extension: destination XY remains 4-aligned; a width or height not divisible by four is accepted only when that rectangle reaches the matching image right or bottom edge. The backend clamps each 4Ã—4 UIF tile to its valid columns and rows, issuing guarded DMA for only `validColumns * 4` bytes across `validRows`; this preserves neighboring texels and padded storage. It requires both `BUFFER_TO_TILED_RECT_COPY` and the separate `BUFFER_TO_TILED_TAIL_COPY` capability. Up to two calls remain allowed, with disjoint rectangles and source spans and a cumulative limit of 256 `ceil(width/4) * ceil(height/4)` tiles. Source bounds remain `(height - 1) * pitch + width * 4`, with DMA row-skip bounds checked for the smallest tail row. The complete stream and every tile address/span are preflighted before DMA. Full-image TFU uploads remain unchanged; other boards fail closed. The 2026-09-30 Pi 4 proof changed 25 texels, left 196 valid texels untouched, and preserved 291 padded UIF backing words outside the copy. It checked 246 source words including 54 source-padding words, 91 readback-padding words and 92 guards. TFU stayed at 1, DMA advanced 0â†’4 and jobs 1â†’2; later readback advanced DMA 4â†’24. A non-edge 5Ã—5 request returned `-20005` during recording before more DMA. MMU, OOM and native faults were zero, with one intentional validation fault. Submit-time malformed-stream preflight remains desk-gate evidence. See `docs/evidence/vulkan-optimal-upload-edge-tail-pi4-20260930/README.md`. One-utile micro upload: a separate guarded-DMA shape accepts a 1â€“4 by 1â€“4 BGRA8 rectangle wholly contained in one 4Ã—4 UIF utile, including an unaligned interior pixel origin. It writes only the requested row bytes and rows, preserving the other texels in that utile. It requires both `BUFFER_TO_TILED_RECT_COPY` and `BUFFER_TO_TILED_MICRO_COPY`; a micro upload is isolated from other buffer-to-image operations in its command buffer. Buffer offsets remain 64-byte aligned, source bounds use `(height - 1) * pitch + width * 4`, and source/image alias, row-stride, utile and guarded-window bounds are preflighted before DMA. Other boards do not advertise this capability. The 2026-09-30 Pi 4 proof changed six requested texels and preserved 250, including ten same-utile neighbors; checks covered 272 source words (262 payload and ten padding words), 64 readback-padding words and 96 guards. TFU stayed at 1, DMA advanced 0â†’1 and jobs 1â†’2. A crossing-utile request returned `-20005` during recording. MMU, OOM and native fault counts were zero. See `docs/evidence/vulkan-buffer-optimal-microrect-pi4-20260930/README.md`. Submit-time malformed-stream preflight remains desk-gate evidence. A separate two-call Pi 4 proof used a 13Ã—13 target: 17 texels changed, 152 valid texels remained unchanged, and 343 padded UIF backing words outside the copies were preserved. It checked 186 source words including 58 source-padding words, 39 readback-padding words and 112 guards. TFU stayed at 1, DMA advanced 0â†’2 and jobs 1â†’3; later readback advanced DMA 2â†’18. A non-edge second call returned `-20005` during recording before DMA. Submit-time malformed-second preflight is proven by signed desk regression only. See `docs/evidence/vulkan-optimal-upload-edge-tail-pi4-20260930/README.md` (`two-call-report.bin`). Mips, layers and format conversion remain unsupported. |
| `vkCmdCopyImage` | Implements a bounded array of one to 32 nonempty rectangular colour regions between linear BGRA8 images, including different image dimensions and XY offsets. A disjoint copy within the same image uses `GENERAL` for both layouts. It validates the complete region array before recording and all rows before submission, refusing source/destination and destination/destination overlap within the call, including aliased allocations. Generation-tagged references retain the allocations through submission. Pi 4 executes tight regions in one guarded DMA operation and supported strided rectangles in one 2D DMA submission, with guarded DMA row copies when the hardware row geometry does not fit. A 17Ã—13 copy between different image sizes passed on Pi 4 silicon; see `docs/VULKAN_IMAGE_RECTANGLE_PI4_2026-09-26.md`. A disjoint 8Ã—8 same-image copy and then a two-region same-image array passed on Pi 4 silicon, with exact copied/untouched pixels and eight DMA operations for each respective test; see `docs/VULKAN_SELF_IMAGE_DMA_PI4_2026-09-27.md` and `docs/VULKAN_IMAGE_ARRAY_DMA_PI4_2026-09-27.md`. Overlap and malformed later-region refusals are desk-proved. Two separate image-copy calls in one command buffer passed on Pi 4 with eight DMA rows and exact whole-image bytes; see `docs/VULKAN_MULTI_CALL_IMAGE_DMA_PI4_2026-09-27.md`. One full level-zero BGRA8 optimal-to-optimal region between distinct equal-size images is also supported through a Pi 4 TFU job; the copied atlas passed exact V3D sampling checks (`docs/VULKAN_OPTIMAL_COPY_TFU_PI4_2026-09-27.md`). A complete equal-size linear-to-optimal image copy takes the source image's actual row pitch through TFU; a fresh optimal destination passed V3D pixel checks (`docs/VULKAN_LINEAR_OPTIMAL_TFU_PI4_2026-09-27.md`). A separate partial linear-to-optimal path accepts one region per command buffer between distinct equal-size level-zero BGRA8 images, with arbitrary in-bounds linear source offsets and actual source pitch; destination offsets and extents align to 4Ã—4 utiles, up to 256 utiles. The shared stream is preflighted before Pi 4 guarded DMA behind a dedicated capability. The 2026-09-30 Pi 4 proof copied 16 exact texels, preserved 240 untouched texels and matched all 256 source texels; 64 padding and 96 guard checks passed. TFU stayed at 1, DMA advanced 0â†’1 and backend jobs 1â†’2. A later readback advanced DMA 1â†’17. A misaligned destination returned `-20005` before readback; MMU, OOM and native fault counts were zero, with one intentional validation fault. The full-image TFU path is unchanged; other boards do not advertise this path. See `docs/evidence/vulkan-partial-linear-optimal-pi4-20260930/README.md`. The supported image-copy and buffer-to-image upload calls can be interleaved in one transfer-only command buffer, with all calls revalidated before the first hardware job (`docs/VULKAN_MIXED_IMAGE_TFU_PI4_2026-09-27.md`). A complete equal-size optimal-to-linear image copy detiles through guarded 2D DMA in 4Ã—4 utiles; an 8Ã—8 atlas and a 37Ã—13 odd-extent pattern passed exact Pi 4 checks (`docs/VULKAN_TILED_READBACK_DMA_PI4_2026-09-27.md`). The implementation also accepts a bounded optimal-to-linear partial region between distinct equal-size level-zero BGRA8 images: source offsets align to 4Ã—4 utiles, and width/height tails are allowed only at the corresponding source edge. The 2026-09-30 Pi 4 proof copied a `(32,8)` `5Ã—5` region from a 37Ã—13 image, matching 25 texels and preserving 456 other texels and 32 guard words; the 148-byte destination pitch leaves no padding words. DMA advanced 0â†’4, TFU 0â†’1, and backend jobs 1â†’2. A same-sized non-edge tail returned `-20005` without more transfer work. See `docs/evidence/vulkan-partial-optimal-linear-pi4-20260930/README.md`. Mips, layers, format conversion and other partial shapes remain unsupported. A separate partial optimal-to-optimal subset is implemented for at most one region per command buffer between distinct equal-size level-zero BGRA8 UIF images, with source/destination offsets and extents aligned to 4Ã—4 utiles and a 256-utile maximum. Pi 4 executes it through guarded DMA under a dedicated backend capability. The 2026-09-30 Pi 4 proof copied 16 exact texels, preserved 240 untouched texels, and passed 64 padding and 96 guard checks. TFU remained at 2, DMA advanced 0â†’1, and backend jobs advanced 2â†’3. A later full readback advanced DMA 1â†’17. An unaligned request returned `-20005` without extra transfer work; MMU, OOM and native fault counts were zero, with one intentional validation fault. See ``docs/evidence/vulkan-partial-optimal-copy-pi4-20260930/README.md`. The whole-image optimal-to-optimal TFU route is unchanged. The 2026-09-30 Pi 4 proof matched all 16 copied texels, preserved 240 untouched texels, and passed 64 padding and 96 guard checks. TFU stayed at 2, DMA advanced 0â†’1 and backend jobs 2â†’3; a later full readback advanced DMA 1â†’17. An unaligned request returned `-20005` without extra transfer work. See ``docs/evidence/vulkan-partial-optimal-copy-pi4-20260930/README.md`. |
| `vkCmdCopyImageToBuffer` | Implements a bounded array of one to 32 nonempty rectangular linear BGRA8 image readbacks into a transfer-destination buffer at four-byte-aligned offsets. Buffer rows may be tight or use an explicit `bufferRowLength` at least as wide as the region; `bufferImageHeight` is zero or at least the region height. Recording validates the complete array and captures its image and buffer ranges; submission revalidates every row, refuses source/destination and destination/destination overlap, including aliased allocations, and retains both allocations. Pi 4 executes through guarded DMA, using one operation for each tight full-width region or one 2D DMA submission for a supported strided rectangle; larger row gaps retain guarded DMA row copies. Whole, rectangular, padded-row and two-region readbacks passed on Pi 4 silicon with exact copied/untouched bytes and DMA counters; see `docs/VULKAN_IMAGE_READBACK_PI4_2026-09-26.md`, `docs/VULKAN_IMAGE_RECT_READBACK_PI4_2026-09-27.md`, `docs/VULKAN_STRIDED_IMAGE_PI4_2026-09-27.md`, and `docs/VULKAN_IMAGE_READBACK_ARRAY_DMA_PI4_2026-09-27.md`. Separate readback calls in one otherwise isolated command buffer execute in recorded order through guarded DMA; each call retains its own complete-array validation. Two calls passed on Pi 4 with eight DMA rows and an exact 16,512-byte destination check; see `docs/VULKAN_MULTI_CALL_READBACK_DMA_PI4_2026-09-27.md`. A buffer-to-linear-image upload followed by an image barrier and image-to-buffer readback in the same stream passed on Pi 4 with two guarded DMA operations and exact bytes (`docs/VULKAN_MIXED_READBACK_DMA_PI4_2026-09-27.md`). Optimal BGRA8 image-to-buffer readback uses guarded 2D DMA on Pi 4. The full-image path accepts odd extents; its 37x13 RAM payload verified all 481 texels, untouched padding and 40 DMA operations. The bounded partial path requires 4Ã—4-utile-aligned source offsets; width and height must be multiples of four unless that dimension reaches the corresponding image edge. R2 on 2026-09-30 checked 16 exact texels, 16 padding words and 32 guard words with one DMA and refused an unaligned request with `-20005`. R3 checked a right-and-bottom edge tail at `(32,8)` with extent `5Ã—5` on a 37Ã—13 image: all 25 texels matched, 15 padding words and 32 guard words remained intact, with four DMA operations; the non-edge `(28,4)` `5Ã—5` request returned `-20005` without extra work. The R3 trace is `docs/evidence/vulkan-optimal-edge-tail-pi4-20260930/report.bin`. Mips, layers, format conversion, and other non-aligned edge shapes remain unsupported. See `docs/VULKAN_OPTIMAL_IMAGE_BUFFER_DMA_PI4_2026-09-27.md`. |
| `vkCmdCopyBuffer` | Implements multiple disjoint `VkBufferCopy` regions per call and multiple ordered buffer-copy commands per submission on the coherent buffer heap. Recording validates an entire region array before appending it, captures both handles and offsets, and rejects overlapping source/destination or destination/destination regions within one call. Submission preflights every copy's live same-device bindings, usage, bounds and source/destination overlap before any write, retains both buffers and allocations, then copies the requested bytes in recording order. Buffer transfers may interleave with supported image uploads and copies in one transfer-only command buffer; the entire stream is preflighted and executed in order through DMA and TFU (`docs/VULKAN_DMA_TFU_STREAM_PI4_2026-09-27.md`). A mix with a draw or clear is refused before work begins; the pool bounds the number of recorded regions. |
| `vkCmdFillBuffer` | Implements a four-byte aligned transfer-destination fill with a repeated host-endian `uint32_t` and `VK_WHOLE_SIZE` rounding down to whole words. It records a generation-tagged buffer handle and value, revalidates the entire mixed copy/fill stream before any write, retains buffer and allocation during submission, and executes fills and copies in recording order. Draws and image clears remain separate submissions; supported image uploads, copies and linear readbacks may follow or precede the fill in the same transfer-only stream. |
| `vkCmdUpdateBuffer` | Implements the full core-1.0 65536-byte maximum with four-byte alignment and transfer-destination usage. The caller's bytes are copied into one of 32 private 64 KiB command-pool slots (2 MiB fixed BSS) at recording time, then revalidated and retained with the other ordered buffer transfers before submission. The emitted maximum-size gate verifies every destination byte after the caller changes its source. A Pi 4 run used DMA to update staging data before TFU uploaded and copied an atlas in one command buffer (`docs/VULKAN_DMA_TFU_STREAM_PI4_2026-09-27.md`). |
| `vkCreateEvent` / `vkDestroyEvent` / `vkGetEventStatus` / `vkSetEvent` / `vkResetEvent` | Implemented for host-owned events on a graphics-capable device. New events start reset; repeated set/reset is idempotent. Typed generations and parent checks reject stale and wrong-device handles. GPU event commands remain unavailable. |
| `vkCreateFence` / `vkDestroyFence` / `vkResetFences` / `vkGetFenceStatus` / `vkWaitForFences` | Implemented for finite waits. `UINT64_MAX` succeeds immediately when the requested fence condition is already true; an unsatisfied unlimited wait returns `ANVIL_VK_ERR_UNSUPPORTED` until host calls are reentrant. It is never disguised as a bounded `VK_TIMEOUT`. |
| `vkCreateSemaphore` / `vkDestroySemaphore` | Implemented for core-1.0 binary semaphores. Handles retain device slot and generation; destruction refuses reserved or pending payloads. Timeline and host signal/wait operations are not claimed. |
| `vkQueueSubmit` | Implemented for one `VkSubmitInfo`, at most one command buffer, and at most sixteen binary wait/signal operations in total. All waits are ordered before all signals; unsatisfied waits, duplicate roles, stale/cross-device handles and stage bits the active backend does not execute are refused before submission. State is committed only after resource/fence preflight, published at real immediate or polled completion, and rolled back atomically on a backend fault. Multiple `VkSubmitInfo` records and multiple command buffers remain refused. |
| `vkDeviceWaitIdle` / `vkQueueWaitIdle` | Implemented. Anvil exposes one queue per device; queue wait validates the generation-tagged queue handle and uses the existing bounded device-idle polling path. |

### The graphics pipeline entry points, added 2026-09-11

| Entry point | Status |
|---|---|
| `vkCreateShaderModule` / `vkDestroyShaderModule` | Implemented. Creation walks and verifies the accepted SPIR-V subset, then retains an immutable exact-word image and typed IR owned by the shader-module generation. Pipeline creation consumes that verified IR synchronously and copies its executable metadata, so a compiled pipeline survives later module destruction and slot reuse. Modules outside the accepted subset are refused with a whole sentence before publication. |
| `vkCreateBuffer` / `vkDestroyBuffer` / `vkGetBufferMemoryRequirements` / `vkBindBufferMemory` | Implemented for `VK_BUFFER_USAGE_VERTEX_BUFFER_BIT`, `VK_BUFFER_USAGE_INDEX_BUFFER_BIT`, `VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT` and the two transfer bits, exclusive sharing, page-granular alignment. |
| `vkCreateImageView` / `vkDestroyImageView` | Implemented for `VK_IMAGE_VIEW_TYPE_2D`, `VK_FORMAT_B8G8R8A8_UNORM`, identity swizzle, the whole colour subresource. |
| `vkCreateSampler` / `vkDestroySampler` | Implemented as a typed, device-owned object for normalized 2D sampling with nearest or linear min/mag filters, nearest mip mode at LOD zero, clamp-to-edge on all coordinates, and no anisotropy or comparison. It is retained by the bounded combined-image-sampler descriptor and consumed by both the measured linear one-texel path and the bounded optimal-image path. |
| `vkCreateRenderPass` / `vkDestroyRenderPass` | Implemented for one colour attachment, one subpass, no dependencies, `loadOp` CLEAR and `storeOp` STORE. |
| `vkGetRenderAreaGranularity` | Implemented for a live, same-device render pass. The Pi 4 V3D backend derives 64Ã—64 from its one-target, 32-bpp, no-MSAA tile planner; the no-GPU test backend reports 1Ã—1. Invalid handles leave the output untouched. This is an optimal-area hint; accepted render areas remain limited to the whole framebuffer. |
| `vkCreateFramebuffer` / `vkDestroyFramebuffer` | Implemented for one attachment at the image's own extent, one layer. |
| `vkCreatePipelineLayout` / `vkDestroyPipelineLayout` | Implemented for zero or one descriptor set layout and at most one push constant range: fragment stage, offset 0, 16 bytes. Creation consumes and copies the set layout's immutable dense binding schema; later source-layout destruction or slot reuse cannot substitute another schema. Nonzero create flags and cross-device set layouts are refused before publication. |
| `vkCreateDescriptorSetLayout` / `vkDestroyDescriptorSetLayout` | Implemented for one or two dense bindings numbered 0..n-1, each either `VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER` or `VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER`; every binding has `descriptorCount` 1 at `VK_SHADER_STAGE_FRAGMENT_BIT`. A mixed UBO-plus-sampler layout is supported in either binding order. Every other descriptor type, sparse numbering and duplicate binding are refused before publication. Sets consume and copy the schema at allocation, so the source layout may subsequently be destroyed or reused without changing them. |
| `vkCreateDescriptorPool` / `vkDestroyDescriptorPool` / `vkResetDescriptorPool` | Implemented for arbitrary input rows containing the two supported descriptor types. Duplicate rows of the same type are summed with checked overflow into independent per-type capacities. `VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT` is accepted; reset and destroy are refused while a submission is in flight. |
| `vkAllocateDescriptorSets` | Implements arrays of one to four sets per call, bounded by the global set table. It preflights every layout, the pool's `maxSets`, both descriptor-type capacities, and global free slots before publishing any set. On failure every output is null and no set or pool counter changes. `VK_ERROR_OUT_OF_POOL_MEMORY` reports an absent or exhausted pool budget; global table exhaustion reports `VK_ERROR_TOO_MANY_OBJECTS`. Each allocated set copies its layout's immutable schema. |
| `vkFreeDescriptorSets` | Implemented for a pool created with `VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT`. It preflights a bounded array, permits null entries, rejects stale, duplicate, foreign and wrong-pool handles without partial freeing, and returns each freed set's per-type descriptor and set capacity. In-flight submission is conservatively refused. Reallocation gets a new generation, and submit preflight rejects recorded draws naming a freed set. |
| `vkUpdateDescriptorSets` | Implements up to sixteen ordered writes followed by up to sixteen ordered copies per call. A failed later operation restores every earlier destination in that call. Each write addresses one descriptor at array element zero and validates the destination's copied layout schema. Uniform-buffer writes need a live same-device bound uniform buffer at a sixteen-byte-aligned offset and range of at least sixteen (`VK_WHOLE_SIZE` accepted); subtraction-based bounds validation prevents `offset + range` wrap. Combined-image-sampler writes need a live same-device sampler and full image view, a bound BGRA8 image created with `SAMPLED`, and `SHADER_READ_ONLY_OPTIMAL`. Copies support one or two consecutive whole bindings; source and destination types must match and consecutive bindings must have homogeneous type and stage flags. Undefined source descriptors can be copied; overlapping self-copies are refused. Resolution rechecks live resource handles and image layout. Destination updates are refused while a submission is in flight. |
| `vkCmdBindDescriptorSets` | Implemented for one set at index 0, no dynamic offsets and `VK_PIPELINE_BIND_POINT_GRAPHICS`. Device ownership and the copied binding-count/type/stage schema must match the command buffer's pipeline layout; compatible schemas from distinct source layout handles are accepted. |
| `vkCreatePipelineCache` / `vkDestroyPipelineCache` / `vkGetPipelineCacheData` / `vkMergePipelineCaches` | Implements generation-checked, device-owned empty cache objects. A cache exports a stable 32-byte version-one header and accepts imported bytes as a hint; the compiler does not store reusable pipeline binaries. Data-size queries, truncated reads with `VK_INCOMPLETE`, and validated empty merges are supported. |
| `vkCreateGraphicsPipelines` / `vkDestroyPipeline` | Accepts multiple independent `VkGraphicsPipelineCreateInfo` entries per call and either a null or same-device live empty cache. It attempts every entry, leaves failed outputs null, and preserves successful handles when another entry fails. The cache does not accelerate compilation. See the state table below for the supported pipeline state. |
| `vkCmdBeginRenderPass` / `vkCmdEndRenderPass` | Implemented for `VK_SUBPASS_CONTENTS_INLINE`, one clear value, a render area that is the whole framebuffer. |
| `vkCmdClearAttachments` | Implements one colour attachment, one in-bounds rectangle and one layer in the active render pass. A full-frame clear before the first draw is folded into the load clear, including on odd-sized targets. Pi 4 also executes bounded partial rectangles in recorded order with draws through V3D, but only for even framebuffer dimensions; a 64Ã—64 hardware run verified two clears and two draws in one bin/render transaction and all 4,096 pixels. An out-of-bounds x=60, width=8 rectangle returned `-20001` before jobs. Arrays, depth/stencil and unsupported shapes remain refused. See `docs/evidence/vulkan-clear-attachments-pi4-20260930/README.md`. |
| `vkCmdBindPipeline` | Implemented for `VK_PIPELINE_BIND_POINT_GRAPHICS`. |
| `vkCmdBindVertexBuffers` | Implemented for a range of bindings inside 0..3, bound one at a time, so one call binding two buffers and two calls binding one each leave the same state. |
| `vkCmdBindIndexBuffer` | Implemented for one live, same-device, bound buffer carrying `VK_BUFFER_USAGE_INDEX_BUFFER_BIT`, at an element-aligned offset, with `VK_INDEX_TYPE_UINT16` or `VK_INDEX_TYPE_UINT32`. The generation-tagged binding is re-resolved at submit. |
| `vkCmdPushConstants` | Implemented for the whole sixteen-byte fragment-stage block at offset 0. |
| `vkCmdSetScissor` | Implemented for `firstScissor` zero and one `VkRect2D`. A pipeline may declare dynamic scissor alone or with dynamic viewport; reset clears the supplied state, a nonempty draw requires it, and each draw snapshots its rectangle so later changes cannot alter earlier records. Signed offsets and unsigned extents are normalized without overflow by the backend; empty and wholly out-of-bounds rectangles become a zero-size clip. |
| `vkCmdSetViewport` | Implemented for one nonnegative whole-pixel viewport with depth range exactly zero to one. Dynamic viewport and scissor may be declared independently; every draw snapshots the effective state. The viewport must fit its active framebuffer and its centre must fit V3D's u14.8 offset field; QPU scale and V3D clipper/offset follow each draw. Pyramid captures 99â€“103 show scissor clipping, smaller and translated viewport mapping, and independent static scissor on Pi 4; see `docs/VULKAN_DYNAMIC_VIEWPORT_SCISSOR_PI4_2026-09-27.md` and `docs/VULKAN_STATIC_SCISSOR_PI4_2026-09-27.md`. |
| `vkCmdDraw` | One instance is verified on Pi 4. The source now records `instanceCount` and `firstInstance`, checks each vertex- or instance-rate binding, and emits V3D's instanced packet; multiple instances still await a distinct-pixel Pi 4 proof. A zero vertex or instance count consumes no draw slot. A command buffer snapshots up to 6,144 ordered draws, including the active pipeline, bindings, push data and generation-safe resource ledger. `TRIANGLE_LIST` discards an incomplete final triangle. `TRIANGLE_STRIP` filled both halves of a square on Pi 4 in capture 106. |
| `vkCmdDrawIndexed` | One instance with `firstInstance = 0` is verified on Pi 4. The source now carries multiple instances and base instance through the indexed V3D packet path, pending a Pi 4 pixel proof. `vertexOffset` remains zero; UINT16/UINT32 indices and triangle-list or triangle-strip topology are supported. Submit scans coherent indices, bounds vertex and instance fetches, includes exact index and input ranges in cache maintenance, and retains resources through completion. Capture 107's indexed strip was pixel-identical to capture 106's array strip. |

The fixed-function state a pipeline may declare: one to four vertex input
bindings numbered 0..n-1, each at vertex or instance rate with a stride
that is a positive multiple of four, and each read by at least one attribute -
a binding nothing reads is refused rather than ignored; attributes at locations
0..n-1 (n <= 4) in `R32G32_SFLOAT`, `R32G32B32_SFLOAT` or
`R32G32B32A32_SFLOAT`, each naming one of those bindings and fitting inside
THAT binding's stride; `VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST` or
`VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP`, with no primitive restart; one
viewport and one scissor. The viewport has a nonnegative whole-pixel origin and
whole-pixel extents. Viewport and scissor may independently be static or
dynamic; the viewport must fit inside the active framebuffer. Fill mode, no
culling, no depth bias, no depth clamp, no rasteriser discard; one sample;
`pSampleMask` either null (sample zero enabled) or naming one word whose bit
zero controls that sample; every channel written, with blending either disabled
or exact straight source-over (`SRC_ALPHA`, `ONE_MINUS_SRC_ALPHA`, `ADD`) for
both colour and alpha; no depth-stencil state and no other dynamic state.
Everything else is refused with a code and a sentence. A 2026-10-01 Pi 4
run proved the zero-bit single-sample case against a full-image oracle: three
public draw records, two emitted primitives, and one bin/render job pair. The
backend validates and elides the zero-coverage draw; this is not a V3D
sample-mask packet claim. See
`docs/evidence/vulkan-sample-mask-pi4-20261001/README.md`.

`vkCmdPipelineBarrier`'s ten-parameter problem is closed. Compiler revision
`a9f412a6` added aligned AArch64 stack arguments, so Anvil now exposes the
registry prototype directly and no longer carries an argument-record adapter.
The resource gate executes the real call: argument nine is the image-barrier
count and argument ten is its pointer, making both the caller and callee sides
observable.

### The layers

| Area | Implemented and checked | Not implemented or not claimed |
|---|---|---|
| Registry and ABI | A PureBasic generator verifies the pinned registry hash and emits a selected core-1.0 slice. The checked-in vocabulary covers 83 naturally aligned AArch64 structures with registry member names, order and widths. The complete 55-member `VkPhysicalDeviceFeatures` record, `VkFormatProperties`, `VkImageFormatProperties`, `VkSamplerCreateInfo`, `VkSemaphoreCreateInfo`, `VkBufferCopy` and `VkPipelineDynamicStateCreateInfo`, and the complete nested `VkPhysicalDeviceProperties` / `VkPhysicalDeviceLimits` / `VkPhysicalDeviceSparseProperties` ABI are among them. The properties query now writes its complete record and reports bounded limits; unsupported capabilities remain zero, including values that core-1.0 conformance would require to be nonzero. The foundation gate compares its registry-owned structures and executes exact size and `OffsetOf` fixtures; the independent complete ABI inventory covers all 83 structures and reports 127 of 281 core declaration categories present: 32 enums, 12 bitmasks and 83 structures. Another 152 categories remain missing and the two core unions remain deliberately unrepresentable. | The complete core-1.0 enum, bitmask, alias, handle, union, callback, command prototype, platform guard, optionality and valid-usage vocabulary is not generated. `VkClearColorValue` is a union and is deliberately not declared â€” PureMetal has no union, so the adapter reads the caller's sixteen bytes as the `float32` arm and says so. No other target ABI is declared equivalent merely because AArch64 layout passes. |
| Public API | The entry points in the table above validate `sType`, `pNext`, flags, counts, pointers, parents and host-synchronization rules before entering the object engine. Invalid usage that core Vulkan leaves undefined returns an Anvil code far outside `VkResult`'s range, with a whole sentence naming the code and the next thing to check; void commands record that sentence and, where the specification allows, invalidate the command buffer. Byte-exact, case-sensitive `vkGetInstanceProcAddr` and `vkGetDeviceProcAddr` lookup exposes 102 audited core command names in their registry dispatch domains. The independent inventory finds 102 declared-callable core commands and 35 missing across all 137 core-1.0 commands. | There is no platform loader integration, layer interface, extension negotiation or `VkAllocationCallbacks` support. Host allocation callbacks are refused rather than ignored. `AnvilVkImageAddress` remains a diagnostic oracle, not an application API; applications can now use `vkMapMemory`. Concurrent host calls are still unsafe â€” see the prerequisites. |
| Instance and device discovery | Generation-tagged ownership and one enabled instance extension, VK_KHR_surface revision 25. Empty layer/device-extension lists and bounded count/capacity discovery are explicit. | Device extensions, including VK_KHR_swapchain, remain unavailable; no conformance claim. |
| Command lifecycle | Pools and primary/secondary buffers across initial, recording, executable, pending, invalid, reset, free and destroy. Resources a submission references are retained until it completes, and reset, free, pool reset and pool destroy all refuse while a buffer is pending. Exactly one submission may be outstanding. A command buffer is either a transfer or a render pass and never both; a render pass holds a bounded ordered list of up to 4,096 draws. Each nonempty draw copies the current static or dynamic scissor into its immutable record; reset clears dynamic state and a draw before `vkCmdSetScissor` is refused. A render pass left open at `vkEndCommandBuffer` is refused. Whole-list preflight completes before mutation, and every abandon path discards the prepared generation ledger. | Secondary execution and inheritance, simultaneous use, externally synchronized host access, and the rest of the command set are absent. |
| Pi 4 V3D backend | `vk_v3d_backend.pi4` lowers validated whole-image clears and accepted draw lists through transactional `NeonRebindSurface` + `NeonFrameBegin` + `NeonFrameEnd`. A complete list uses one rebind/frame/restore transaction and one bin/render submission, with transition-cached viewport, scissor, blend and varying packets. Signed scissor rectangles are intersected with the framebuffer before a `CLIP_WINDOW` packet is emitted, and repeated normalized rectangles emit no redundant packet. Per-draw shader records live in private 640-byte slots while immutable pipeline metadata is built and cleaned once. Vertex, uniform, sampled-image and slot cache ranges are overflow-checked, physically sorted and coalesced; the cache subsystem maintains all accepted ranges and issues one final barrier for the transaction. It submits real V3D jobs, maintains both cache domains, restores the complete display geometry, and maps the closed disabled/source-over blend mode to exact V3D 4.2 state. It refuses the scanout buffer and reports native failure as `VK_ERROR_DEVICE_LOST`. There is no processor-side or DMA image fallback in rendering. The completed attachment is presented through the display subsystem's DMA path, with the CPU copy retained only as a refusal fallback. The 2026-09-13 silicon runs proved native, smaller non-square and partial-tile images, the over-capacity refusal, an ordinary display frame, and three consecutive descriptor/varying jobs. The 2026-09-15 blend proof produced exact raw alpha/colour probes and a fresh teal-on-blue screenshot. The 2026-09-16 list proof executed six ordered draws as one bin/render job and one DMA presentation. The final 2026-09-16 atlas/chrome proof executed one TFU advance, one bin/render pair and one display-DMA presentation, returned its exact report, passed 211 report/pixel checks and produced a clean rotated 800x1280 capture. The bounded dynamic viewport/scissor pair is desk-proved, including private per-draw scale records and atomic geometry refusal; Pi 4 captures 99â€“101 show clipped, origin-zero smaller, and positively translated GPU pyramid draws. Pi 4 capture 105 alternated separate 799Ã—1279 and 400Ã—640 attachments with one pipeline, returned twelve GPU draws and DMA presentations, and matched the small target pixel-for-pixel to capture 100; see `docs/VULKAN_FRAMEBUFFER_RESIZE_PI4_2026-09-27.md`. A physical panel rotation change during rendering remains unproved. | Render areas smaller than the framebuffer, multiple render targets, mip levels, layers, MSAA and formats beyond linear BGRA8 remain unsupported. Submission is synchronous. Zero sample-mask draw suppression passed a Pi 4 pixel-oracle silicon proof; see `docs/evidence/vulkan-sample-mask-pi4-20261001/README.md`. |
| Pi 4 renderer | The existing Pi driver initializes V3D 4.2, GPU page tables, QPU encoding, bin/render control lists, TFU and CSD submission, bounded waits, cache maintenance, OOM handling, and fault evidence. Neon builds fixed UI shaders and geometry for boxes, lines, glyphs, textures, clipping, rotation, and console chrome. The console has exercised the underlying V3D bin/render path on hardware. | Neon is an engine API, not Vulkan fixed-function state. Its built-in shaders are not SPIR-V, shader modules, descriptor-backed programs, or general graphics/compute pipelines. Direct polling and single-owner global arenas are not a Vulkan queue scheduler. A working console does not prove arbitrary Vulkan commands or shaders. |
| Memory and resources | One heap, taken whole from the backend and suballocated first-fit with page-granular alignment. `VkDeviceMemory`, `VkImage`, `VkBuffer` and the bounded `VkSampler` subset are real typed objects with generations and owners; memory-backed resources also carry bind and in-flight counts. A compiled pipeline's shaders take an INTERNAL allocation from the same heap that no handle names and `vkFreeMemory` cannot reach. Row pitch and image size come from the backend's rule; optimal images expose no fake row pitch. A host-visible allocation supports one checked `vkMapMemory` range, including `VK_WHOLE_SIZE`, and must be unmapped before free. Pi 4's identity-mapped window is advertised `HOST_COHERENT` because submission/completion own mandatory cache maintenance. A combined-image-sampler descriptor resolves to one closed live record only while its image is bound, carries `SAMPLED`, and remains in `SHADER_READ_ONLY_OPTIMAL`. The bounded optimal BGRA8 path records and retains one whole-image buffer copy and reaches `UIF_NO_XOR` through TFU. UINT16/UINT32 index buffers are retained like vertex buffers and scanned at submit to close the selected vertex range. | There are no buffer views, mip levels, array layers, general tilings, aliasing, dedicated allocations, sparse memory, 8-bit indices, storage buffers, or formats other than `B8G8R8A8_UNORM`. Linear sampled images remain limited to 1x1. Optimal images remain limited to the planner's level-zero one-layer/one-sample BGRA8 shape and whole-image TFU uploads with tight or padded raster source rows or a disjoint optimal-image source; partial regions and format conversion are refused. There is one queue family, so queue-family ownership transfer is refused rather than implemented. |
| Synchronization | `VkFence` with its two states and its one owner, plus core-1.0 binary semaphores with generation ownership, ordered single-consumption, pending references and failure-atomic reserve/commit/complete/rollback. `vkWaitForFences` honours finite timeouts and is bounded twice. An already-satisfied `UINT64_MAX` wait succeeds; an unsatisfied one is explicitly refused. Image memory barriers carry layout tracking checked at record and submit. Transfer-scoped global and buffer barriers use the ordered coherent buffer stream, with live bound buffer ranges checked again before submission. The test backend proves both immediate and later-polled semaphore completion and later-polled device-loss rollback; the current V3D backend completes inside `NeonFrameEnd`. | There are no GPU event commands or event-based queue waits, timeline semaphores, host semaphore signal/wait/reset, shader/graphics global or buffer memory barriers, multi-`VkSubmitInfo` batches, or concurrent queues. An unsignaled wait cannot park the single-owner queue and is refused loudly. A genuinely unlimited host wait that another thread could satisfy still needs reentrant call frames. |
| Shaders and pipelines | A SPIR-V front end parses a module, validates it against the Vulkan environment and retains exact records as immutable typed SSA IR. The accepted vertex path includes pass-through and a bounded scalar `FAdd`/`FSub`/`FMul` position graph: at most sixteen live arithmetic nodes and fourteen input words, with fixed clip Z/W. The fourteen-word path reuses VPM input-index registers after fetch and is restricted to at most four varying components whose source words remain live through output. A four-attribute rotating pyramid uses V3D for both three-component XY transform rows and the per-vertex perspective-scale multiply; see `docs/VULKAN_PYRAMID_DEMO_PI4_2026-09-27.md`. The CPU still computes frame coefficients, reciprocal scale and face order. The fragment path supports scalar and two-, three- or four-component binary32 values, straight-line `FAdd`/`FSub`/`FMul`, fragment `Dot` and `VectorTimesScalar`, live input loads, one push-constant block, one uniform-block member, and one combined `sampler2D` implicit-LOD lookup; dead declared inputs, outputs and loads do not change the live interface. The V3D 4.2 lowerer reserves resource registers from live dependencies, emits QPU programs and a uniform stream transactionally, and publishes exact patch metadata only after complete validation. Uniform-buffer and sampled-image descriptors keep GPU-visible addresses in those streams; the backend proves each range mapped and cleans it before submission. Pipelines copy executable shader metadata, the immutable descriptor/push compatibility signature, and a normalized disabled or exact straight source-over blend mode. | There is no general control flow, phi, loop, function-call, integer arithmetic, conversion, comparison, storage buffer, dynamic descriptor, descriptor array, push descriptor, specialization constant, reusable pipeline binaries, derivative pipeline, compute pipeline, second subpass, depth attachment or general blend equation. Sampled SPIR-V remains restricted to one combined 2D image at set zero, binary32 `vec2` coordinates from the supported typed graph, implicit LOD, no image operands and a `vec4` sample result. The supported fragment graph may combine at most one live push load, one live UBO load and one live sample. The lowerer is serialized and uses bounded scratch storage; it is not a general optimizer or scheduler. Linear sampling remains bounded to one texel; the optimal path is the separately proved level-zero BGRA8 whole-image transfer shape. |
| Presentation | Public VK_KHR_surface queries, enabled-instance lookup and native Anvil provider binding are implemented. Private DSI main/banner source ownership completes after confirmed HVS adoption; build353 checks actual public metadata during geometry/renderer transitions. | No public swapchain/device or OS platform extension, blocking acquire, general async queue, HDMI validation or actual GPU/display/DMA-fault recovery claim. |
| Driver modules | PMFMOD v1 validates, relocates, zeroes, cache-synchronizes, and records an AArch64 module image in a board-provided arena. | Neither board wires a module arena or file discovery. The engine does not call module probe/init/quiesce entries, bind services, install stable dispatch trampolines, account for in-flight calls, or reload. The Vulkan backend is statically composed, which the layering permits. |

### What the gates prove, and what they do not

| Gate | Result | What it proves |
|---|---|---|
| `Anvil/Graphics/Vulkan/Tests/vulkan_foundation_check.py` / `tools/vulkan_core10_abi_inventory_check.py` | PASS â€” pinned registry compared, 280 emitted ABI and lifecycle checks over 5,770,862 interpreted A64 instructions; the complete inventory adds 37 checks and reports 127/281 declaration categories present. The queue mutant, all three feature mutants and the format/image-format mutation families are RED on their recorded runs. | Vocabulary against the pinned `vk.xml`, exact AArch64 layout including `VkBufferCopy`, `VkSemaphoreCreateInfo`, `VkPipelineDynamicStateCreateInfo`, `VkRect2D` and all 18 members of `VkSamplerCreateInfo`, and that a build with no backend enumerates no device. The feature properties poison then query the complete record, accept a non-null all-false record, and turn on each of its 55 members separately. Format properties require exactly proved linear BGRA8 feature bits. Image-format properties require the shared create/query combination owner, backend-derived geometry and pitch-derived maximum bytes, one mip/layer/sample, stale-handle and caller-output safety, and refusal of every unsupported input. The queue properties prove an ordinary graphics-family scan selects family zero for a draw-capable backend and finds no graphics family for a transfer-only backend. Every checked structure member name, order and type is compared against both the registry and `vk_core_1_0.pbi`, so the two transcriptions have to agree. |
| `tools/vulkan_semaphore_check.py` | PASS â€” 266 registry/source/emitted checks, 214 emitted rows and 806,652 interpreted A64 instructions; all 20 hostile mutations are RED. | Exact core-1.0 create/destroy prototypes and ABI, ordered wait/signal adaptation, generation-safe reserve/commit/complete/rollback, immediate and later-polled completion, deferred device-loss propagation, dispatch exposure and atomic device teardown. The whole baseline-plus-mutation campaign holds the shared Vulkan checker lock and stages every mutant outside the repository. |
| `tools/vulkan_dispatch_check.py` / `tools/vulkan_dispatch_inventory_check.py` | Historical PASS â€” 592 registry/source/emitted checks, 166 emitted rows and 5,121,211 interpreted A64 instructions. The complete inventory validates all 137 core-1.0 commands: 102 declared-callable and 35 missing, with all 102 declared-callable names exposed through the resolvers. | Exact registry prototypes, aliases and command domains; case-sensitive bounded lookup; null-instance/global, instance and device query rules; zero-count layer/extension, sparse-image format and sparse-image memory requirement enumeration plus linear-image row-pitch reporting and coherent mapped-range validation with caller-output safety; physical-device property limits and stale-handle caller-output safety; queue-idle lookup and live/stale handle behavior; public `vkCmdCopyBuffer`, `vkCmdFillBuffer`, `vkCmdUpdateBuffer`, `vkCmdSetScissor`, `vkCmdBindIndexBuffer`, `vkCmdDrawIndexed`, `vkFreeDescriptorSets` and `vkGetRenderAreaGranularity`. |
| `tools/vulkan_render_granularity_check.py` | PASS â€” 16 public-entry checks over 4,018,375 interpreted A64 instructions, with an MMIO hard stop. | The no-GPU state backend reports 1Ã—1; null, stale and invalid requests preserve the output; global, instance and device resolver domains expose the exact command. |
| `tools/vulkan_descriptor_free_check.py` | PASS â€” 38 public-entry and pool-state checks over 4,001,221 interpreted A64 instructions, with an MMIO hard stop. Focused quota-leak and duplicate-free mutations are RED. | Free-capable pool creation, mixed UBO/sampler quota recovery, all-or-nothing invalid and duplicate arrays, wrong-pool and stale generations, null entries, zero-count refusal, in-flight refusal, reset, and the non-free pool boundary. |
| `tools/vulkan_descriptor_update_check.py` | PASS â€” 43 public-entry checks over 4,056,600 interpreted A64 instructions, with an MMIO hard stop. Offset-loss and missing-copy-rollback mutations are RED. | Ordered multi-write and multi-copy updates, writes before copies, later-error rollback, duplicate destination last-write-wins, non-overlapping self-copies, mixed-type crossing refusal and in-flight refusal. |
| `tools/vulkan_resource_check.py` | PASS â€” 771 independent property checks over 6,845,105 executed A64 instructions. The earlier complete mutation run rejects all 30 prior mistakes; the two focused `UINT64_MAX` mutants, all ten focused map-memory mutants and the focused transfer-only attachment mutant are RED. The suite now has 44 mutants after the obsolete semaphore-refusal mutant was removed; a fresh complete run of all 44 has not been claimed. | The resource, layout, fence, retention, mapping, format-capability, submission and error-reporting contracts, executed through the public entry points, with an MMIO hard stop armed; and that every byte of the bound image still held its poison, so no processor-side image clear exists anywhere in the path; buffer fills explicitly write the coherent buffer heap. The buffer-copy section requires exact copied and untouched bytes for one or several regions, rejects within-call source/destination and destination/destination overlap, proves separate copies execute in order, proves a stale later transfer prevents an earlier write, and rejects a destroyed destination handle. It checks exact fill words and untouched bytes, `VK_WHOLE_SIZE` including the final partial-word rounding case, alignment and size refusal, and ordered copy/fill/update execution and recording-time source capture. Its mapping properties use the public entry points to distinguish host-visible/non-visible types, owner, live/stale handle, duplicate/unbalanced state, flags, exact/whole ranges and returned pointer, then use the mapping to poison the image. Its format property refuses colour-attachment image creation when the backend advertises no graphics draw path while the shared combination owner still accepts transfer-only and sampled-only usage. Its wait properties distinguish an unsignalled unlimited wait (explicitly unsupported) from an already-satisfied unlimited wait (success). |
| `tools/vulkan_update_boundary_check.py` | PASS â€” 14 emitted setup, submit and byte-integrity checks over 11,998,766 interpreted A64 instructions, with an MMIO hard stop. | The full 65536-byte `vkCmdUpdateBuffer` payload is captured at record time; every destination byte matches after the caller changes its source before submit. |
| `tools/vulkan_v3d_backend_check.py` | PASS â€” 92 property checks over 4,405,988 executed A64 instructions; all eight listed board diagnostics, including `vulkanImageReadbackProof.pi4`, build real images. The recorded mutation run rejects all 16 desk-reachable mistakes and names 2 board-only rules it cannot reach. | That the whole closure links against the real display, V3D, QPU and Neon implementation; that a build with the engine down enumerates no device without MMIO; that the render-area hint equals the 64Ã—64 one-target tile planner; that geometry is planned before mutation, every arena/range/in-frame boundary is checked, and a failed rebind preserves the prior surface. It also requires full geometry restoration and the descriptor TMU mapped-range/cache-clean contracts. The source contract requires guarded DMA for buffer copies and fills, with refusal if DMA is absent; image clear and draw also have no CPU or DMA fallback. It requires the pipeline/vertex/index/descriptor cleans before submission and the GPU clean plus target clean/invalidate before completion, giving the `HOST_COHERENT` advertisement teeth. |
| `tools/vulkan_spirv_check.py` | PASS â€” 486 checks over 11,639,888 executed A64 instructions across 58 assembled modules. | The legacy accepted and refused SPIR-V vocabulary is unchanged after exact-record retention: modules are assembled word by word from specification opcode numbers, walked without mutation, and either published only after complete validation or refused with a whole sentence naming the unsupported semantic. |
| `tools/vulkan_spirv_ir_adapter_check.py` | PASS â€” 8,704 properties over 57,196,054 interpreted A64 instructions; all 7 focused mutations are RED. | Exact immutable raw words, every retained semantic record field/order/offset, typed IR types and nodes, publish-last invalidation, self-use dominance refusal, poisoned-output clearing, and all six embedded pointer rebindings. |
| `tools/vulkan_ir_v3d42_check.py` | PASS â€” 65 emitted checks, 734 independently decoded QPU instructions and 23,444,775 interpreted A64 instructions; all 39 causal mutations are RED with infrastructure failures separated from semantic rejection. | Transactional straight-line typed-IR lowering, binary32 `FAdd`/`FMul`, dependency-driven register reservations, split resource lifetimes, exact uniform metadata, dead-SSA behavior, range/overlap checks and publish-last failure atomicity. |
| `tools/vulkan_qpu_emitted_check.py` | Baseline PASS â€” 15 emitted programs containing 423 independently decoded V3D 4.2 instructions over 44,342,506 A64 setup instructions. | Independent decoding of coordinate, vertex and fragment programs for varying, push-constant, split-binding, uniform-buffer, sampled-image and typed arithmetic paths. |
| `tools/vulkan_draw_pool_check.py` | PASS â€” 89 properties over 15,033,844 interpreted A64 instructions. | The 184-byte, 4,096-record bounded pool, immutable indexed/non-indexed draw snapshots, reset semantics, and the rule that dynamic-scissor state belongs to a command buffer and is copied into each nonempty draw rather than referenced later. |
| `tools/vulkan_pipeline_check.py` | PASS â€” 813 property checks over 204,184,757 executed A64 instructions, including padded optimal-image source rows, ordered mixed buffer/image transfers and linear image readback, and two-dimensional DMA row-submission calls. The current portable draw-list/scissor gate separately passes 61 properties over 3,950,304 instructions and rejects all four focused scissor mutations. The compact mixed-descriptor gate, focused dead-I/O wrapper, optimal-copy, lifetime-alias and sampled-state families remain red where expected. | The public path through resource creation, transfer, immutable descriptor schemas, mixed UBO-plus-sampler binding, typed fragment lowering, ordered draw-list capture, dynamic-scissor snapshotting, transactional submission and exact backend observation. It proves all nine mixed uniform words, six descriptor dependencies plus the attachment view, dual-role view retention, compatible schema handles, slot reuse safety, per-type pool atomicity, cross-device refusals, dead-interface liveness and failure-atomic release. The test backend writes no pixels or MMIO; real GPU execution is paired only with the explicit Pi 4 runs below. Each checker owns unique artifacts and a whole-run OS lock prevents compilation through another process's hostile mutation. |
| `tools/vulkan_v3d_draw_slot_check.py` | PASS â€” 58 independent properties over 561,669 executed A64 instructions; all 8 hostile ABI mutations are RED. | Immutable pipeline metadata, private 640-byte draw slots, a 292-byte maximum live record, exact 28-byte fragment-shader cloning for the measured fixture, overflow refusal, and exact coalesced cache ranges. |
| `tools/vulkan_v3d_backend_list_check.py` | PASS â€” 142 property checks over live 1-, 3- and 3,505-draw lists plus admission-only 4,096, executing 32,634,045 A64 instructions. Its earlier 10 causal mutants remain RED and all 3 scissor normalization/transition/preflight mutants are RED. | Whole-list atomic preflight, one frame transaction, exact indexed/non-indexed triangle-list and triangle-strip primitive modes, draw counts, transition-cached viewport/scissor/blend/varying state, signed/unsigned overflow-safe clip normalization, rollback, physical vertex/index cache-range union and a stable last-record diagnostic snapshot. The indexed row observes setup base/byte size, hardware index type, byte offset, maximum-index vertex bound and pre-frame refusals. The 3,505-draw case is live; only the 4,096 admission boundary uses a zero sample mask. |
| `tools/vulkan_indexed_draw_check.py` | PASS â€” baseline: 32 public-path cells, 12 encoder results and 46 exact packet/refusal bytes over 5,881,227 emitted A64 instructions with the signed compiler. The separate long `--mutate` run was stopped without a result; no mutation-pass claim is made for that run. | UINT16/UINT32 binding and recording, `firstIndex` applied once, maximum-index vertex bounds, stale/range/alignment refusals before counters move, in-flight index lifetime, and byte-exact V3D 4.2 `INDEX_BUFFER_SETUP` plus `INDEXED_PRIM_LIST` emission. The bounded UINT16 diagnostic passed on Pi 4 on 2026-09-26; the bounded UINT32 diagnostic passed on Pi 4 on 2026-10-01. The dedicated `tools/vulkan_indexed_uint32_proof_check.py` passes against the saved report, BCL and index bytes, with ten hostile mutations caught; see `docs/evidence/vulkan-indexed-uint32-pi4-20261001/README.md`. |
| `tools/v3d_cache_batch_emitted_check.py` | PASS â€” 38 exact checks over 1,961 interpreted A64 instructions; all 6 hostile mutations are RED. | `V3dCacheBatchBegin`, `V3dCacheBatchRange` and `V3dCacheBatchEnd` retain several validated aligned ranges and issue one final barrier. Overflow, negative/full-width addresses, zero length, misuse, poisoning and the legacy single-range API are independently exercised. |
| `tools/vulkan_atlas_chrome_acceptance_check.py` | BOARD PASS â€” 213 exact source/report/pixel-oracle checks against the current Pi 4 run. The returning diagnostic is a 1,094,336-byte PMF container with SHA-256 `9ca7480b29d7868a8a9e2f4d5719f68290d5844de3a3ac1a4c89fbb3e75dd8a3`. | One public render pass containing eight ordered six-vertex quads; an 8x8 optimal atlas copied from 16-texel-stride poison-padded rows through the TFU; UV sampling; descriptor-bound `sample * push + UBO`; tint and source-over blend; eight `vkCmdSetScissor` snapshots; exact solid/transparent/covered/clipped pixel regions; one TFU advance, one bin/render pair and one display-owner DMA presentation. Build 210 returned exact `x0=0x8208C8` with report slot 128 equal to zero, then returned to its prompt with the deadman off and no core leases; capture 57 and the 960-byte report are preserved in `docs/evidence/vulkan-optimal-stride-20260927/`. |
| `tools/neon_atlas_contract_emitted_check.py` | PASS â€” 26 source checks and 41 emitted assertions over 3,118,073 interpreted A64 instructions; all 5 hostile mutations are RED. | The existing Neon font builder publishes one borrowed read-only linear RGBA8 raster, exact dimensions/bytes, copied ASCII 32..126 glyph UVs and one copied opaque-white texel rectangle only after a successful current-font ensure. Font changes invalidate every query; CPU-only ensure does no TFU/V3D work and does not publish the private tiled-atlas state early. |
| `tools/neon_vk_chrome_acceptance_check.py` | DESK PASS â€” 267 production-adapter source checks, 27 emitted contract assertions, 58 hook source checks plus 44 emitted hook assertions, 45 emitted production-geometry assertions, and all 8 hostile traces RED. | `neon_vk_chrome.pbi` owns persistent pipeline, atlas, descriptors, command buffer, fence and coherent vertex storage; installs the complete box/text/scissor/fan/outline/line hook family only after successful creation; and atomically lowers bounded fans and one-pixel lines into Vulkan triangle lists. The exact emitted production procedures cover a convex fan, closed outline, horizontal/vertical/diagonal/zero-length lines, cursor preservation, overflow and safe reset. The real existing Neon panel/menu/list/text scene records 109 quads, 47 draws, 654 vertices and five expected scissor states. A current-tree short Pi 4 run on 2026-10-01 passed 47 draws, 654 vertices, 35 box calls, 12 text calls, 74 glyph quads, four expected scissor calls, one display-DMA operation, zero fallback/refusal/pending presentation/backend error, and 12 pixel probes; the report field is an expected-call count, not an independent measurement of the five states and this run produced no screenshot. See `docs/evidence/vulkan-neon-widget-short-pi4-20261001/README.md`. The 2026-09-26 all-15-scene board proof at commit `a6b9a93` includes paired fan/line frames and capture 27, but covers that historical source only. A separate current-tree mode-2 Pi 4 run on 2026-10-01 passed the production fan/outline and line scenes: both full 64Ã—64 BGRA captures matched the pinned native golden segments byte-for-byte, with all 12 report probes passing. CPU work only copied completed GPU attachment bytes into RAM for comparison. See `docs/evidence/vulkan-neon-fan-line-pi4-20261001/README.md`; a fresh current-tree all-15-scene run now matches the full native corpus byte-for-byte (see `docs/VULKAN_NEON_ALL15_CURRENT_PI4.md`). |
| `tools/vulkan_neon_fan_line_proof_check.py` | BOARD PASS â€” 32,848 checks over the mode-2 report and both complete RAM captures; both 16,384-byte captures matched pinned native golden segments with zero differing bytes. | Current-tree Pi 4 fan/outline and line scenes ran through the production Vulkan adapter. The diagnostic copied completed GPU attachment bytes into RAM for comparison; no CPU pixel rendering is used. Evidence: `docs/evidence/vulkan-neon-fan-line-pi4-20261001/README.md`. The historical all-15-scene result remains scoped to its earlier source. |
| `tools/vulkan_interp_check.py` | PASS â€” 395 property checks over 372,292 executed A64 instructions; `--mutate` rejects all 14 plausible mistakes | That `vk_interp_expect.pbi` â€” the module the board diagnostic asks what colour a pixel should be â€” gives the same answers as a second implementation of the same stated rule written in Python: the clip-to-screen transform, twice the signed area, the three barycentric numerators, the strict inside test, the four channels and the packed B8G8R8A8 word, over eight triangles and thirty-three probe pixels. The weights at every covered probe sum to twice the area, and each corner probe is dominated by its own vertex by more than three tolerances â€” which is what makes a board run able to tell a gradient from a flat fill. It owns no hardware and makes no MMIO access |

None of these desk gates prove GPU execution, displayed output, concurrency,
memory visibility, WSI, shader correctness or conformance. Only a board run can.
The recorded Pi 4 runs now prove execution of clears, graphics pipelines,
interpolated varyings, a second vertex input binding, a uniform-buffer
descriptor fetched by the TMU, host-visible memory and presentation. They do
not prove any unlisted shader instruction, descriptor type, format or WSI.

### Board runs

The 2026-10-01 Pi 4 transfer-scoped global and buffer barrier RAM proof
passed an ordered fill/update/barrier/copy stream. It checked 64 buffer words,
256 guards, and three guarded DMA operations/backend jobs. A later out-of-range
buffer barrier invalidated its command buffer and added no DMA or backend work.
See `docs/evidence/vulkan-transfer-barrier-pi4-20261001/README.md`. Shader and
graphics memory scopes remain unsupported.

The 2026-10-01 Pi 4 ordered draw-list scale proof passed 64, 256 and 1,024
distinct `vkCmdDraw` calls in one render pass and submit per run. Every stage
produced all 16,384 expected pixels in a private 128Ã—128 attachment, advanced
bin/render once, preserved memory guards, and reported zero native/MMU/OOM/
fence faults. Monitor execution took 3.0, 3.1 and 3.6 seconds respectively
under a 15-second deadman. See
`RaspberryPi4/Examples/Diagnostics/vulkanDrawListScaleProof.md` and
`docs/evidence/vulkan-drawlist-scale-pi4-20261001/manifest.json`. This proves
1,024 hardware draws, not the 4,096-record admission ceiling.

A separate **2026-10-01 Pi 4 standalone 1024Ã—768 `vkCmdClearColorImage` run passed**. The offscreen diagnostic cleared all 786,432 pixels to `$FF3380B2` at 4,096-byte pitch; every pixel matched and the adjacent native guard checksum was unchanged. Bin and render completions each advanced 0â†’1; OOM, MMU, native and validation faults were zero. The two raw `ERR_STAT` values were `$1000`, the read-only VCDI idle status bit. An initial checker that required raw zero rejected those two fields; the corrected checker rejects other error bits and passes the exact saved report plus 45 hostile mutations. No presentation or other-board behavior was tested. See `docs/evidence/vulkan-clear-extent1024-pi4-20261001/README.md`.

**2026-09-11, run 1 â€” no GPU result.** `vulkanClearProof.pi4` (container
`3a6cde76â€¦`) returned in 1.16 s with status `#VCP_ERR_DISPLAY`, detail `-19`
(`#DSP_ESEND`). It never reached V3D. The cause was in the diagnostic, not in
the driver and not in the display library: it called `DisplayInit`, which
**asks the firmware for a display**, and on this bench the firmware has none â€”
the DSI panel is brought up and driven by the monitor, which installs its
framebuffer with `DisplayAdopt` instead. The nine-tag property transaction had
nothing to allocate against and failed. The console restored cleanly.

That run also exposed a structural fault worth more than the bug: the GPU proof
had been made to **depend** on taking the screen, so a display refusal reported
nothing at all about V3D. The diagnostic now runs the whole GPU proof in memory
the payload owns â€” no display, no firmware, no framebuffer â€” and presentation is
a separate step with its own verdict. A present that cannot happen can no longer
hide a GPU result that did.

**2026-09-11, run 2 â€” PASSED. V3D executes a Vulkan colour clear.** Container
`a06b43e5â€¦`, `screen dma` first, returned in 12.25 s with the report at
`$0058EB00`, magic `564B4350`, **slot 1 = 0**.

What that verdict is computed from, and therefore what it asserts:

- **Every pixel.** 1,024,000 words of an 800x1280 `VK_FORMAT_B8G8R8A8_UNORM`
  image, each compared against `$FF3380B2`: slot 14 mismatches = **0**, slot 15
  first-bad-offset = **-1** (the never-set sentinel), slots 12 and 13 (the first
  and last words) both `$FF3380B2`, equal to slot 11, which the driver computed
  rather than the test. Every one of those words held `$00CC7F4D` before the
  submit. The clear value went in as four binary32 patterns
  (`0.2f, 0.5f, 0.7f, 1.0f`), through the integer UNORM conversion, into the
  packed word, into the tile store, and came back as the B, G, R, A byte order
  this format requires â€” **the whole colour path is correct on silicon**.
- **The GPU did it.** The verdict returns `#VCP_ERR_NO_JOBS` unless both the bin
  and the render completion counters advanced, and `#VCP_ERR_V3D_FAULT` on any
  binner OOM or V3D MMU fault. Status 0 means both jobs ran and neither faulted.
  There is no processor-side or DMA fallback anywhere under this path.
- **It wrote nowhere else.** The verdict returns `#VCP_ERR_GUARD_CHANGED` unless
  the screen-sized guard buffer below the image is byte-identical afterwards. It
  was. The backend's save and restore of the engine's previous render target
  works on hardware.
- **The fence and the layout.** Status 0 requires the wait to have succeeded and
  the image's layout to have advanced to `VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL`.
- **A production Pi build enumerated a real GPU device for the first time**:
  slot 42 (`AnvilVkBackendIsGpu`) = 1.
- **Not one validation fault in the whole run**: slot 44 = 0. Every public `vk*`
  call on the path succeeded; no refusal was taken.
- Presented: slot 47 = 1, slot 45 = `#DSP_OK`. `DisplayAdopt` on the scanout
  buffer, one `DisplayBlit`, and a person saw the colour.
- Measured: 115.2 ms to submit and complete the clear, 867.4 ms to read
  4,096,000 bytes back and compare them. The engine needed 10.52 MiB of its
  16 MiB arena (slot 46).

**What run 2 does NOT prove, and none of it may be inferred from the pass:**

- **No shader.** No SPIR-V, no `VkShaderModule`, no pipeline, no QPU program was
  compiled or run. A tile clear and a tile store are fixed-function; the frame
  was submitted with **no draws**. Internal clear lowering is not a shader
  compiler.
- **No draw.** Zero primitives were binned. Nothing about vertices, geometry,
  rasterisation or the QPU path is touched by this result.
- **One geometry only.** 800x1280 at pitch 3200 â€” the render geometry `NeonInit`
  was given. No other extent, format, tiling, mip level, array layer or sample
  count has ever reached the GPU.
- **The two refusal rules were exercised only in the accepting direction** by
  this run. Board run 3 below closed that.
- **No asynchrony.** `NeonFrameEnd` waits for both jobs, so the fence was already
  signalled when `vkQueueSubmit` returned. The pending command-buffer state has
  never been observed on hardware.
- **One run, one cache state.** No repeat, no soak, no caches-on/caches-off pair,
  and no fault injection: an unmapped address requiring a bounded fault rather
  than a hang is still owed. Resource reuse across submissions was not exercised
  either â€” only one submission happened.

**2026-09-11, run 3 â€” PASSED. The two refusal rules, in the direction that
matters.** `vulkanClearRefusals.pi4`, container `504bd049â€¦`, `screen dma` first,
returned in 5.8 s with the report at `$00581868`, magic `564B4352`,
**slot 1 = 0**. It submits nothing: every refusal here happens at record time,
inside `vkCmdClearColorImage`, so `avkBackendSubmitClear` is never reached.

`avkBackendClearSupported` checks in a fixed order â€” engine ready, base and size
sane, inside the window, extent, pitch, size against the extent, and last the
scanned-buffer rule. A request that trips two proves only the earlier one, so
each request was built to trip exactly one, which needed a Vulkan window
spanning both screens:

| Rule | The request | Result |
|---|---|---|
| refuses the buffer the display is scanning out | an 800x1280 image at pitch 3200 â€” *exactly* the render geometry â€” placed at the surface base `$06000000`, so every earlier check passes and only this rule can answer | slot 2 = 1, slot 3 = **-8** (`VK_ERROR_FEATURE_NOT_PRESENT`) |
| refuses any extent but the render geometry | a 640x480 image at `$063E8000`, which is *not* the surface base, so the scanned-buffer rule cannot be what answers | slot 4 = 1, slot 5 = **-8** |
| the refusals discriminate | an 800x1280 image at `$063E8000` â€” right extent, not the scanned buffer | slot 9 = 1, slot 10 = `VK_SUCCESS`; recorded and thrown away unsubmitted |

Also settled by the same run, each of which needs a live engine:

- **The live row pitch.** `avkBackendRowPitchFor(800)` = 3200, the surface's own
  pitch; `(640)` = 2560, the tight pitch. Slot 6 = 1. This is what makes run 2's
  slot 17 mean something.
- **The live capability answer.** Slot 12 = **7** â€” `DEVICE | CLEAR_COLOR | GPU`.
  A desk run can only ever prove 0.
- **The backend's microsecond clock is real.** `V3dCounterHz()` = 54,000,000 and
  the counter advanced across the run. Slot 13 = 1. That clock is what bounds
  `vkWaitForFences`; a stalled one would leave only the poll cap between a dead
  device and a hang during a finite wait. An unsatisfied `UINT64_MAX` wait is
  explicitly withheld until host calls are reentrant; the poll cap is not
  presented as Vulkan's unlimited wait.
- **Allocator reuse on silicon.** Freeing the 640x480 allocation and placing a
  full-geometry image in the hole it left returned the same address,
  `$063E8000`. Slot 27 = 1. Run 2 never exercised reuse.
- **Nothing reached the GPU.** Slot 16 = 1: `V3dBinJobs`, `V3dRenderJobs`,
  `V3dTfuJobs` and `avkBackendJobs` all still 0, and both screen-sized buffers
  byte-identical to the pattern they were filled with (slot 31 delta = 0).
- Exactly two validation faults recorded (slot 34), which is the two refusals
  and nothing else. The engine needed the same 10.52 MiB arena.

**With run 3, both rules `tools/vulkan_v3d_backend_check.py` lists as
desk-unreachable are proven on silicon in both directions**, and that gate now
prints them as `BOARD` with their containers rather than as `OWED`. A rule added
to that list in future without a board proof prints `OWED` and fails the gate.

**Still owed after run 3, and unchanged by it:** no shader, no draw, no other
format or tiling or mip or layer or sample count, no asynchrony, no concurrency,
no caches-on/caches-off pair, no fault injection, and no repeat or soak.

**2026-09-11, run 4 â€” TAKEN, AND NOT MEASURED.** The payload ran, returned in
12.4 s with `x0` inside its own BSS, faulted nothing and left the console clean.
Its report was then read at the wrong offsets: the block was sixty-four 64-BIT
slots and the monitor's dump has no 64-bit width and counts bytes, so slot N
appears at word 2N. Twelve dumped words decode exactly as slots 9 to 14 - an
image size of 4,096,000, a pitch of 3200, a vertex array at `$067D0000` and two
pipeline bases 8 KiB apart - and were read as slots 17 to 28, which is where the
pixel readbacks live. Under the same doubling the two verdicts sit at words 2
and 8; the values read as "slot 1" and "slot 4" were the zero halves of the
magic and of a detail slot, and "slot 47" was the zero half of slot 23.

**Neither verdict, and no pixel readback, was read. Run 4 established nothing
about whether the triangles rendered** - not a pass and not a failure. The
diagnostic's own header was the cause: it said to read the block with a bare
`memory <that> 64`, which is sixty-four BYTES.

The report is 32-bit words now, one slot to one word, with the step it reached
in slot 61 and a tail magic in slot 63 so a short dump says so (Anvil
`338ea23`). The two clear proofs carry the same wrong instruction, corrected in
place; their numbering is unchanged because runs 2 and 3 are recorded against
it.

**2026-09-11, run 5 â€” PASSED. V3D executes a Vulkan graphics pipeline.**
`vulkanTriangleProof.pi4` at Anvil `338ea23`/`5b55574`, container `2c7b6b71â€¦`,
463,548 bytes, compiler `890f1ba4â€¦`, on the build-55 monitor with `screen dma`
and `deadman 15`. Returned in 12.4 s with `x0 = $58FB70`, read as 32-bit words:
magic `564B5452`, tail `52544B56`, **highest step 10**, uniform verdict 0,
per-vertex verdict 0, pass-one pixels `FFFF0000` inside x3 and `FF3380B2`
outside x3, pass-two `FF00FF00` inside x3 and `FF3380B2` outside x3, submit and
wait 0 for both, draws 2, binner overflow 0, MMU faults 0, **present 1**.

That settles the three things the desk could not:

- **`FTOIN`** â€” the viewport transform's rounding executes, and the triangle
  landed where the arithmetic said it would.
- **The VPM output segment size** â€” the emitter's extra sector for varyings is
  on the right side of the line; no vertex was corrupted.
- **The varying path** â€” `LDVARY` + delay + `FADD` against `r5` with the
  non-perspective flag packet carried a four-component colour to the fragment
  shader.

**What run 5 did NOT settle, and why the next run exists:** its second pass
gives all three vertices the SAME colour on purpose, so its expected pixel is
exact whatever the interpolator's precision is. It proves the varying PATH and
says nothing about interpolation. A shader that read the varying and ignored the
weights would have passed it.

**2026-09-12, run 6 â€” FAILED at the descriptor/TMU render.**
`RaspberryPi4/Examples/Diagnostics/vulkanVaryingProof.pi4` was finally run on
a clean-reset V3D under monitor build 101. The exact untouched-`d8e5f52`
container was 553,576 bytes, SHA-256
`773b6678d90693bed4d2917fc3a407bb37c23b0b9f8445dcbf9ae9cd23a5f46a`;
only its display hold was reduced from six seconds to one so the complete run
fit under the monitor's 15-second hardware-deadman ceiling. It returned in
13.74 seconds with the complete magic/tail report and highest step 12, but
slots 1, 2 and 3 were all 21 (`VVP_ERR_SUBMIT`), submit slots 89, 91 and 93
were `VK_ERROR_DEVICE_LOST`, and native slot 95 was 13
(`NEON_ERR_RENDER`). At that point no gradient or descriptor-backed colour was
accepted on silicon, and the descriptor/TMU path became a known RED silicon
gate. Run 8 below closes it. A renderer timeout can leave later V3D payloads
dirty until a monitor reset; every isolation run after this failure therefore
began with a fresh reset.

> **The build line**, with the toolchain lane's own mechanism (this is the
> direct form):
> ```
> PureMetalForge.exe --compile >     RaspberryPi4/Examples/Diagnostics/vulkanVaryingProof.pi4 -t pi4 >     --load-addr 0x500000 --stack-addr 0x4F00000 --entry-returns >     -o vulkanVaryingProof.img
> ```
> Built at the desk on 2026-09-11 with a snapshot of `PureMetalForge.exe`
> `890f1ba477f1d68f46a61a668a3daa9eec194b593782d9447cf64aeb193146a3`:
> container **545,176 bytes, sha256
> `529949ed932ab85e122e79e2708123f2379fa1d5b2d42195ec56f3c50b424478`**, image
> 545,080 bytes occupying `$500000..$585137`, BSS `$590000..$5B411F`. Rebuild
> before staging and compare â€” a container built with a different compiler is
> not this one. This is a PAYLOAD and not a monitor build, so it does not move
> the board's build number.
>
> **Before the run**: `screen dma`. The payload initialises the graphics engine
> itself and uses the same 16 MiB arena at `$0A000000` the V3D console owns.
>
> **Run**: load at `$500000`, `deadman 15` â€” three passes plus a one-second
> display of the result. Fifteen seconds is the monitor's hardware ceiling.
>
> **READ IT WITH `md.l <x0> 200`** â€” one hundred and twenty-eight 32-bit words,
> one per slot, the count in hex because every argument of that command is. A
> bare `md` counts BYTES and groups by one; that is what went wrong on run 4.
>
> **Expected**: slot 0 = `$59524156` and slot 127 = `$56415259`; slot 125 = 12;
> slots 1, 2 and 3 all 0. Pass A's slots 37, 38, 39 = `$FFFF00FF` and 40, 41,
> 42 = `$FF3380B2`. Pass B's slots 43 to 49 each within TWO 8-bit steps per
> channel of the expectation in slots 30 to 36 â€” slot 53 (worst distance) at
> most 2 and slot 54 (probes over tolerance) 0 â€” and slots 50, 51, 52 =
> `$FF3380B2`. Pass C the same, in slots 55 to 61 against the same expectations,
> with slot 67 at most 2, slot 68 = 0, slots 62, 63, 64 = `$FF3380B2`, and
> **slot 69 = 0**: every probe the same word pass B produced. Slots 70, 72, 74
> and 76 all NON-ZERO â€” the four refusals were exercised live and every one
> refused. Slot 79 > 78 and 81 > 80, slots 82 and 85 = 0, slot 88 = slot 87,
> slot 98 = 1. Slots 115, 116, 117, 118, 119 = 8, 16, 0, 1, 2. The
> descriptor-lowering evidence is slots 120..124 = 144, the uniform-buffer
> address from slot 15, `$FFFFFF7C`, `$FFFFFFFF`, 1.
>
> **On the glass**: a triangle, apex up, on a blue-grey ground, RED at the apex
> (400, 320), GREEN at the lower left (200, 960) and BLUE at the lower right
> (600, 960), blending smoothly through grey at the centroid. A SOLID MAGENTA
> triangle means pass B and pass C did not happen and slot 125 says which step
> stopped it; a solid triangle of any one colour where a gradient was expected
> is the defect this run exists to find.
>
> **If a verdict is not 0**: slot 125 says which step, slot 4 carries a detail,
> slot 97 a whole sentence and slot 109 the command buffer's own. The codes are
> in the diagnostic's header; the ones that matter most are 19 (a pipeline was
> refused â€” slots 111 and 112 name the emission step and the encoder's code),
> 23 and 24 (the pixels), 28 (the descriptor path), 29 (the expectation module
> refused its own probes), 30 (the split changed the picture), 31 (a refusal
> did not refuse) and 32 (the submitted descriptor stream is not the TMU
> general-load stream the desk gate decoded).
>
> **Recovery**: the console repaints over the presented picture by itself;
> `screen on` forces it and `screen v3d` brings the accelerated console back.
> Neither needs a reset. `NeonShutdown()` hands the V3D MMU back before the
> payload returns. Nothing writes a core spin slot, releases a core, or touches
> the monitor, its variables, the DSI control registers, the GENET ring or the
> driver-module region. It renders the same triangle into the same 800x1280 image
three times and asks three different questions:

- **a uniform buffer feeds the fragment colour**, through
  `vkCreateDescriptorSetLayout`, `vkCreatePipelineLayout` with it,
  `vkCreateDescriptorPool`, `vkAllocateDescriptorSets`,
  `vkUpdateDescriptorSets` with a `VkDescriptorBufferInfo` and
  `vkCmdBindDescriptorSets`, with the fragment module reading member 0 of a
  `Block`-decorated `OpTypeStruct` in the Uniform storage class;
- **a real gradient** - red at the apex, green at the lower left, blue at the
  lower right - with seven probe pixels whose expected colours are computed on
  the board by `vk_interp_expect.pbi` from the barycentric weights at each
  probe's own pixel centre, compared within two 8-bit steps per channel;
- **the same gradient out of two vertex buffers**, position at a stride of
  eight and colour at a stride of sixteen, with the verdict including that every
  probe is the same word as the one-buffer pass produced.

That run failed before producing any of the three pictures. At that point the
gradient, split binding layout and descriptor path remained proved at a desk
and nothing more. Run 8 below closes those three gates. The tolerance, probe
placement and the reason each probe is strictly inside the triangle are in the
diagnostic's own header and in `vk_interp_expect.pbi`.

**2026-09-12, run 7 â€” PASSED. Format query, host mapping, cache visibility,
fences and drawing on silicon.** The ordinary triangle diagnostic was extended
at the source-owned API boundary to require the exact
`vkGetPhysicalDeviceFormatProperties` answer for linear
`B8G8R8A8_UNORM`, and to populate both the colour image and vertex allocation
through `vkMapMemory`/`vkUnmapMemory`. There is deliberately no flush call:
the vertex fetcher's correct pixels give the Pi 4 backend's advertised
`HOST_COHERENT` promise a board-visible consequence. The exact container was
514,072 bytes, SHA-256
`54f033c86e20b3a66b3d695571aae3edc772d915e432b1239d677d40a401f22a`,
run under monitor build 101 after a clean reset. The complete report returned
in 11.92 seconds: both verdicts zero; both submit and wait pairs zero; bin and
render jobs each advanced twice; no OOM, MMU fault, or guard change; exact red
then green interior pixels and exact clear exterior pixels; present verdict 1;
highest step 10 and both magics present. This accepts those APIs and their
vertex/render cache path at the one proven 800x1280 geometry. It does not make
the failed descriptor/TMU run green.

The generic `tools/board_run.py` wrapper now accepts an explicit unsigned
`--expect-x0` value, validates it before any board side effect, and records the
expectation in its JSON evidence. A mismatch remains a failure after trace and
screenshot preservation. Its fatal-exception path validates the requested
trace range before boot, retains every accepted exception datagram through a
quiet prompt/reset boundary, and never sends trace or screenshot commands as
though a faulting payload had returned. Focused fake-console gates cover normal
return, expected nonzero return, mismatch, complete and incomplete exception
records, timeouts, malformed ranges and the no-transmit-on-fatal rule.

**2026-09-13, run 8 â€” PASSED. Uniform-buffer descriptor, interpolation and
split vertex bindings on silicon.** This was the first candidate after a safe
monitor reset, so it did not inherit the V3D state left by run 6's timeout. The
567,436-byte returning container had SHA-256
`44bdfed7d9f7bbc96e474e9954dce146938df3b0f5827c2306cb605f7be61ee4` and ran
under monitor build 101 with a 15-second hardware deadman. It returned normally
with report address `$00595FA0`.

All three verdicts were zero. Pass A's three interior probes were exact
magenta and all outside probes kept the clear colour. Pass B's seven gradient
probes exactly matched the independent expectation; pass C matched those same
seven words exactly while reading position and colour from separate bindings.
Both worst-distance values, both over-tolerance counts and the B/C difference
count were zero. Bin and render job counters each advanced from 0 to 3;
all six submit/wait results and the backend native error were zero; OOM and MMU
fault counts were zero; the guard sum remained `$C0E6C000`; presentation and
display verdicts were one; layout ended at `TRANSFER_SRC_OPTIMAL`; three draws
ran; cleanup was reached; step 12 and both report magics were present.

The submitted shader record was `$067D5000`. Its 144-byte fragment program
read a three-word stream at `$067D3000`: descriptor address `$067D3000`, TMU
configuration `$FFFFFF7C`, then TLB configuration `$FFFFFFFF`. The diagnostic's
independent lowering verdict was one. The validation-fault count was five by
design: it counts the deliberate hostile calls that the diagnostic requires the
API to refuse, not V3D or MMU faults. The nonzero `x0` and stale-capture warning
from the generic wrapper are likewise not failures; this diagnostic returns its
report address, and the payload itself came back to the monitor prompt.

The evidence is under `_work/vulkan-tmu-20260913/clean-v3d/`. If any V3D render
candidate times out, reset the monitor/board before judging a later candidate:
shutdown cannot prove it repaired an engine that did not complete, and a later
red result from inherited state is not independent evidence.

**2026-09-13, run 9 â€” PASSED. Sampled-state integration preserves the visible
V3D path.** The final returning container was built from public main through
`4e24052`, was 575,804 bytes, and had SHA-256
`177c3c3f4d17437f7cdf568b3df0707786c0c54a12eb11cf6f34fa04443c3c7f`.
Monitor build 101 received and independently hashed those exact bytes at
`$00500000`; the run used the DMA console, a 15-second hardware deadman and a
fresh screenshot. The report at `$00596000` had both magics and step 12.

All three diagnostic verdicts were zero. The format feature word was `$81`
(`SAMPLED_IMAGE | COLOR_ATTACHMENT`), five allocations were populated through
`vkMapMemory`, all three submits and waits were zero, bin/render jobs advanced
from 0 to 3, native error/OOM/MMU counts were zero, the guard remained
`$C0E6C000`, and all pixel distances and over-tolerance counts were zero. The
captured 1280x800 frame visibly contains the complete interpolated triangle;
its pixel SHA-256 is
`715531a2bbd059308f3e6b5dd9fef4226891632c1ef2d88065222e965cc3add2`.

Two earlier attempts in this same slot were honest RED diagnostic controls,
not GPU failures: first the diagnostic still expected the old format-feature
word and stopped before submission, then its deliberately unsupported
descriptor case still named combined image sampler after that type became the
accepted bounded state. Those consumers were updated to the new contract; the
final diagnostic instead refuses `STORAGE_IMAGE`, and its five intended
validation refusals all remained present. This run proves integration and no
regression of the existing visible V3D/TMU path. The new combined-image-sampler
record itself remains desk-only state until SPIR-V texture instructions and a
V3D texture fetch consume it; no sampled pixel is claimed by that run.

**2026-09-13, run 10 â€” PASSED. One sampled pixel, through the real V3D TMU.**
Public commit `85c2db8` produced a 636,380-byte flat payload with SHA-256
`46A07A9F7B943F60BD5E3FCAC19E25F510DD2837F8283D6225929DF4C27D051F` and a
636,508-byte PMF container with SHA-256
`F7E32E54EF59952868859B629EACA64F3D3BDE85C78790353E8EE18DD0146352`.
Monitor build 101 received and independently verified that container, verified
the inner image at `$00500000`, armed a 15-second deadman and returned normally
in 8.63 seconds. The nonzero x0 is intentionally the report pointer
`$005A6000`, not a payload error.

The 160-word report had A/B/C/D verdicts all zero, step 13 and both magics.
The sampled submit and wait were zero; all three inside probes were exactly
`$FFFFC020` and all three outside probes exactly `$FF3380B2`. The submitted
texture state held source `$067DA000`, width `$04000000`, height `$00400100`
and format/swizzle `$00A9C040`. Bin and render jobs each moved from 3 to 4;
MMU faults, bin OOM, native backend error and detail were all zero. The returned
1280x800 screenshot has SHA-256
`B8D535126FFD61C82E194D196C83F24A5B4AFBCDF01936C70D1DD0C20F7902A62`.

The first control run measured the old identity-swizzle defect exactly: source
`$FFFFC020` became `$FF20C0FF` at all three inside probes while the clear,
submission, counters and fault state remained correct. The source owner now
uses Mesa's BGRA8 Z,Y,X,W format-table swizzle; the gate mutates it back to
identity and turns red. This proves only the declared one-texel linear subset;
run 11 below closes the next bounded optimal-image transaction without changing
the scope of this older run.

**2026-09-13, run 11 â€” PASSED. A 4x4 optimal image copied by TFU and sampled
by the TMU.** The final 670,884-byte PMF container had SHA-256
`B1989D9D9E70FE5F01D8CD527DE09D987767E525CE30DA58DB0F16125512CF67`;
its 670,756-byte flat image had SHA-256
`3A3FBDF3F71D3A148600CF667352A49BBA5BB989BD76E5D5E016A29C0129243C`.
Monitor build 101 independently verified the staged container at `$00500000`,
armed a 15-second deadman, returned normally with report pointer `$005B6090`,
and captured a new 1280x800 frame (sequence 8 to 9).

The 176-word report had all four pass verdicts zero, step 13, length 704 and
both magics. The transfer source was a 128-byte buffer using memory type 0,
selected by scanning the physical memory properties: `memoryTypeBits=1`, one
reported type, flags 7 (`DEVICE_LOCAL | HOST_VISIBLE | HOST_COHERENT`), correct
allocation `sType`, and result zero. The optimal image required 1,024 padded
bytes and reported row pitch zero. Copy submit/wait were zero, TFU jobs moved
0 to 1, the published layout was `SHADER_READ_ONLY_OPTIMAL`, and the sampled
draw moved bin/render counters 3 to 4. The texture state was base `$067DA000`,
width `$10000000`, height `$00400400`, format/swizzle `$00A9C840`; nearest
sampler words were `$83` and `$00090000`.

The three inside probes were exactly green `$FF00FF00`, blue `$FF0000FF` and
red `$FFFF0000`; all three outside probes remained `$FF3380B2`. MMU, OOM,
native backend and detail faults were zero. The captured pixel SHA-256 is
`22724024624AF20F645590647A69F4B7B7D9EE16027241B1793BE86D61AD6B0B`;
the PNG file SHA-256 is
`F6552765902480625D7953E98E7A7AFCD45FB3ACE034E32EAD9853623B0C3B03`.

This is not general texture support. It proves one two-dimensional BGRA8
image, one mip, one layer, one sample, a single tightly packed whole-image
region at a 64-byte-aligned source offset, level-zero `UIF_NO_XOR`, and the
current normalized nearest-filter sample path. Other formats, partial copies,
row-length/image-height overrides, mips, layers, scaling and conversion remain
refused.

**2026-09-15, run 12 â€” PASSED. One fragment executes sampled-image, push and
UBO arithmetic on silicon.** Monitor build 101 verified the exact 874,740-byte
container, SHA-256
`6405122BD5F7BE41BB79B56CDCB770D0499AA1A7E6E602AAE17C42F7419B9D85`,
at `$00500000`, armed the 15-second deadman and returned normally in 9.81
seconds with `x0=$005E7E78`. The flat 874,612-byte image has SHA-256
`C942FDF52697C80DBC3ACC56850431366C04ADDBAA050FC840ECAC3FB965922A`.
The checker recovered all 240 report words and required both magics, length
960, final step 13, four zero pass verdicts, zero submit/wait results and zero
MMU, OOM and native-backend faults.

The fragment computes `sample * push + UBO`. The retained typed IR and V3D
lowerer published nine distinct runtime indices: push RGBA 4..7, UBO
address/config 2/3, texture/sampler 0/1 and TLB 8. The returned shader record
proved that all nine values were patched through those indices, including UBO
address `$067D3000`, vec4 TMU configuration `$FFFFFF7C`, texture/sampler
pointers `$067DD20F`/`$067DD301`, and TLB word `$FFFFFFFF`. The three inside
pixels were exactly `$FF808000`, `$FF800080`, `$FFFF0000`; all outside probes
kept `$FF3380B2`. TFU, bin and render counters each advanced exactly once.
Module and pipeline-layout source slots were destroyed and reused without
altering the compiled pipeline, and all nine retained resource counters were
zero after completion. The five deliberate hostile validation probes remained
a cumulative count of 5 before, during and after the mixed draw while the
current fault code was zero on both sides, proving the draw added no fault.

The fresh DMA capture was sequence 2, 1280x800, with pixel SHA-256
`D1F98B232832C919E8FC96F4EC1EF8144240063B0BF76B05A3B4DC7C44D51A18`;
the triangle was inspected and clean. The board returned healthy to the build
101 prompt. This accepts only the current one-sample, one-push-load,
one-UBO-load straight-line binary32 graph. It is not general shader, descriptor,
texture, scheduling or Vulkan-conformance proof.


## Required architecture

The compatibility work should keep five boundaries explicit:

1. **Registry-facing API.** Generate exact public names, constants, structures,
   handles, prototypes and dispatch metadata from the pinned registry. Public
   `vk*` adapters validate `sType`, `pNext`, flags, counts, pointers, parents,
   allocator ownership, and host-synchronization rules before entering the
   object engine. Feature exposure and command availability must follow the
   advertised version and extensions. Preserve each command's actual return
   type and permitted results: do not invent a return error for a void command.
   An incomplete development surface must stay explicitly non-production;
   unsupported work must never be represented as successfully executed.
2. **Target-neutral object and command engine.** Portable `.pbi` source owns
   handles, lifetime graphs, reference retention, command streams, resource
   states, synchronization objects, capabilities, and deterministic errors. It
   contains no V3D register, packet, address, tiling, or display assumptions.
3. **Hardware backend seam.** A backend reports real limits and implements
   memory allocation/binding, cache-domain transitions, command lowering, job
   dependencies, submission, interrupt or bounded-poll completion, fault
   attribution, reset, and recovery. Pi `.pi4` code may lower to V3D; a future
   UNO Q `.unoq` backend may target its own GPU. A target with no backend must
   enumerate no usable physical device.
4. **Shader toolchain.** A native front end validates the SPIR-V module and the
   Vulkan environment, builds typed SSA/control-flow IR, links stage interfaces
   and resource decorations, then legalizes, schedules, allocates and encodes
   per backend. QPU encoding is the final Pi step, not the portable IR.
5. **WSI provider.** Platform-neutral surface and swapchain state binds to a
   board display provider. The Pi provider may use existing HDMI/DSI surfaces;
   UNO Q has no present provider today. Acquire, render ownership, cache state,
   presentation, rotation, loss, and retirement must be explicit.

This layering permits the public object and shader semantics to be shared even
when Pi V3D and a future UNO Q GPU have unrelated packet formats. It also keeps
headless compute or transfer support independent of a display.

## Accelerated draw-list presentation â€” Pi 4 acceptance, 2026-09-16

`vulkanDrawListProof.img.pmf` records six ordered Vulkan draws into one render
pass: overlapping opaque push colours, two exact source-over draws, one
varying-colour draw and a final opaque top layer. On Anvil build 148 the
849,648-byte artifact, SHA-256
`31c848b67deedb2d5d96f7de8e4acb303b51b5c143e50dcb972312ba888c50af`,
was verified on the board, run from `$500000` under a 15-second deadman and
returned normally with its report at `x0=$90BD00`.

The report proves six backend draws but exactly one V3D bin job and one render
job. Its transition counts are one viewport, three blend and three varying
changes; the source-over attachment words are exactly `$BF007F80` and
`$9F803F40`. Both verdicts are zero, the render-target guard is unchanged,
there is no MMU/OOM/fault state, teardown completed, and the display owner
records exactly one DMA operation for presentation. `DisplayBlit` now sends an
arbitrary clipped native-format source rectangle through `DmaCopy2D`, with
explicit source and destination cache ownership; the original CPU pixel loop
is only the safe fallback when DMA policy or validation refuses the request.

Capture sequence 5 advanced to 6. The fresh 800x1280 BGRA scanout has SHA-256
`9edf1bb8ca7ea5937a96997b53c0def59d8e2b68f3efa1da7f9e2a6f5a7d85c9`
and is pixel-identical to the earlier CPU-presented reference. The independent
acceptance checker verified the complete 64-word report and eight separate 5x5
screen regions: 262 exact checks. The monitor stopped the deadman and returned
to its real build-148 `pmf>` prompt.

## Dynamic scissor and atlas/chrome tranche â€” current boundary, 2026-09-16

The portable pipeline now accepts exactly one dynamic state:
`VK_DYNAMIC_STATE_SCISSOR`. `vkCmdSetScissor(commandBuffer, 0, 1, rect)` is a
public, dispatch-visible core command. A nonempty draw through a dynamic
pipeline requires a supplied rectangle; command-buffer reset clears it; and
each draw copies it into the draw record. The V3D backend intersects signed
offsets and unsigned extents with the framebuffer without wrapping, converts
empty or wholly exterior rectangles into a zero-size clip, and emits
`CLIP_WINDOW` only when the normalized result changes.

The cache owner now accepts several checked, aligned ranges between
`V3dCacheBatchBegin()` and `V3dCacheBatchEnd()` and issues one final barrier.
The old one-range operation remains valid. This removes the thousands of
per-range barriers formerly paid by the 3,505-draw fixture without moving
range validation or cache ownership into the Vulkan layer.

`RaspberryPi4/Examples/Diagnostics/vulkanAtlasChromeProof.pi4` is the next
returning acceptance instrument. Through public calls it copies an 8x8
optimal BGRA8 atlas, binds the mixed sampled-image/UBO descriptor, supplies UV
vertices and push tints, enables exact source-over blending, records eight
six-vertex quads and eight dynamic scissor snapshots in one render pass, and
presents once through display DMA. Its independent checker has exact 5x5
pixel regions for the solid panel, later toolbar, a transparent atlas texel, a
covered tinted texel, and covered texels on both sides of the final clip edge.

The corrected build-148 RAM-only run loaded the 976,956-byte PMF at `0x500000`
and returned exact `x0=0x6C85A0` in 10.2 seconds. Report slot 128 was zero. The
report records one TFU advance, one bin/render pair and one display-DMA
presentation, and its exact report and pixel oracle pass all 211 checks. Fresh
capture sequence 8 is a 1280x800 PNG representing the rotated 800x1280 target.
The monitor returned to the build-148 prompt with the deadman explicitly off
and no core leases; the run performed no flash, reset or persistent write.
`VULKAN_IDE_CHROME_ACCEPTANCE_2026-09-16.md` pins the artifacts, hashes and
acceptance boundary.

The later read-only Neon atlas and renderer-hook work refactored the common CPU
raster owner, so the current tree has different exact bytes: 977,076-byte PMF,
SHA-256
`c4b43f94547343ef2b01232a81a549f3444f66b4e29c3d90197a2b887fca147b`,
expected report pointer `0x6C85C8`. It compiles and its atlas/display desk gates
pass. The current post-refactor source has since passed a bounded widget-only Pi 4
run on 2026-10-01. Its 1,408,064-byte PMF had SHA-256
`419DC48FA8688894BA49C425BF536C8ABFC2B419CA176DD2194DE32FC5E918DE`; build
223 used CRC `5BC668D0`, returned `x0=0x9C6F38`, and completed the payload in
2.4 seconds under a 15-second deadman. The short run covers one widget frame,
not the 15-scene corpus or paired fan/line frames, and it did not produce a
screenshot. The earlier all-15-scene run remains historical evidence for the
source at commit `a6b9a93`. A separate current-tree mode-2 run covers the
paired fan and line frames with full 64Ã—64 BGRA comparisons. The current-tree
mode-0 payload has now completed all 15 scenes on Pi 4 build 223: its report
passes 124 checks and all 245,760 canonical scene bytes match the pinned
native golden. The full payload returned in 11.185 seconds under a 15-second
deadman. `VULKAN_NEON_ALL15_CURRENT_PI4.md` pins the source, capture, checker,
hashes, and proof boundary. Its 3,505 capacity boxes are batched into one
Vulkan draw, so ordered draw-list scale remains a separate hardware question.

The first real implementation step is now in the tree rather than another
synthetic primitive. `neon_vk_chrome.pbi` maps persistent box, atlas-text,
fan, outline, line-list and scissor resources onto these public paths and the
existing Neon widget layer selects it through one all-or-none primitive hook.
The desk scene calls the real panel, menu, list and text procedures unchanged
and proves 109 quads, 47 draws, 654 vertices, five scissor states, one submit
intent and one display-DMA call with no processor pixel fallback. The emitted
geometry gate additionally proves exact bounded triangle-list lowering. The current-tree widget frame and separate fan/line scenes have bounded Pi 4
proofs. A current-tree all-15-scene run now passes the exact native corpus.
Screenshot coverage and clean HDMI/DSI/rotation/resize coverage remain.

## Prerequisites and hard gaps

- The explicit natural AArch64 structure layout, nested members, fixed arrays,
  and nested `OffsetOf` support are suitable for expanding the public ABI.
  Every generated layout still needs an independent registry-derived fixture;
  default packed structures must not be used accidentally.
- Ordinary generated A64 procedures currently place parameters and locals in
  shared static BSS. Vulkan permits concurrent host calls except where the
  specification assigns external synchronization, so general compatibility
  requires reentrant per-invocation frames before advertising thread-safe
  entry points or concurrent callbacks. A backend may serialize its hardware,
  but the current calling convention can collide in static argument/local
  storage before an internal lock could protect an entry; it is not a safe
  substitute for reentrant public call frames.
- The module format can carry relocatable AArch64 code, but its lifecycle and
  dispatch portions are deliberately inactive. Dynamic backend loading must
  wait for board-owned arenas, discovery, service binding, stable trampolines,
  in-flight accounting, and quiescence; the first backend can remain statically
  composed without changing public API semantics.
- Host allocation callbacks require exact lifetime and same-calling-thread
  behavior. Fixed internal arrays are useful for tests but cannot silently
  replace `VkAllocationCallbacks` or Vulkan's documented allocation failures.
- The Pi backend needs a real resource manager above today's single-owner V3D
  arenas: per-object GPU virtual ranges, residency, retained job references,
  cache ownership, dependency tracking, and bounded recovery. Linux DRM is not
  a runtime dependency, but the services it normally supplies cannot simply be
  omitted on bare metal.

## Compatibility path

The order below is dependency order, not a schedule:

1. Complete and continuously diff the core-1.0 registry vocabulary and public
   ABI. Add exact callable `vk*` adapters only for semantics that exist, while
   production still enumerates no device.
2. Implement host allocation, device memory, buffer/image, and synchronization
   object kernels plus a backend operation seam. Retain every resource used by
   a pending command buffer until completion.
3. Turn the existing offscreen clear into one resource-backed, fence-observable
   transfer path. Keep it an explicitly enabled development backend until the
   mandatory device surface is present.
4. Build SPIR-V parsing and Vulkan-environment validation, then a target-neutral
   typed IR. Start with one tightly declared vertex/fragment capability set;
   reject every capability, execution model, decoration, type, instruction, or
   precision behavior that is not implemented.
   **Parsing, validation, exact-record retention and the first typed IR are
   done.** The immutable IR represents the declared single-function,
   single-block vertex/fragment subset, including straight-line binary32
   `FAdd`/`FMul`; unsupported capabilities and operations remain explicit
   refusals. It is a bounded shader compiler path, not a general SPIR-V
   implementation.
5. Add pipeline layouts, descriptors, render passes, fixed-function state and
   V3D QPU lowering. Differential shader tests and independent packet/QPU
   decoders precede broader instruction coverage.
   **Pipeline layouts, one render pass, the fixed-function state listed above,
   typed QPU lowering, uniform-buffer descriptors and bounded combined image
   samplers are implemented.** A dense two-binding set may carry both resource
   types; copied schemas, per-type pool accounting, device ownership and
   submission lifetimes are independently gated. The QPU checker decodes 423
   V3D 4.2 instructions across all 15 emitted programs. Historical UBO and
   sampled-image silicon runs remain valid, and the 2026-09-15 recovered and
   graded board report now proves the first bounded three-source arithmetic
   fragment (`sample * push + UBO`) on V3D 4.2. Ordered multi-draw recording,
   exact source-over blend, per-draw dynamic scissor and one-barrier cache
   batching are now joined by the final 2026-09-16 atlas/chrome Pi 4 pass. The
   persistent Neon box/text/scissor/fan/outline/line adapter and real-widget
   frame are desk green; their exact Pi 4 screenshot and return proof remain.
6. Add the bare-metal surface/swapchain extension over the existing display
   provider, preserving separate HDMI and DSI ownership and rotations.
7. Expand features only with a machine-readable coverage matrix, negative
   tests, cache-on/off silicon checks, fault injection, and CTS results. No API
   version or conformance claim precedes the mandatory coverage and formal
   Khronos process.

## First implementable slice: resource-backed transfer submission

The next bounded slice should replace development-only attached metadata with
one real Vulkan-shaped transfer path, without claiming a production device.
Under an explicit development-backend build only, implement the exact
core-1.0 vocabulary and public adapters needed for:

- instance/device/one transfer-capable queue discovery;
- `vkGetPhysicalDeviceMemoryProperties`;
- one host-visible development heap and `vkAllocateMemory`/`vkFreeMemory`;
- `vkCreateImage`, `vkGetImageMemoryRequirements`, `vkBindImageMemory`, and
  `vkDestroyImage` for one linear, single-mip, single-layer
  `VK_FORMAT_B8G8R8A8_UNORM` image;
- command pool/buffer creation, `vkBeginCommandBuffer`, one qualifying
  `vkCmdPipelineBarrier`, one full-range `vkCmdClearColorImage`, and
  `vkEndCommandBuffer`;
- `vkCreateFence`, one-command-buffer `vkQueueSubmit` with no semaphores,
  `vkWaitForFences`, fence reset/destruction, and ordered teardown.

The portable layer owns every object, bound range, layout, reference and state
transition. A small backend operation record receives validated physical
resource metadata and a closed transfer command. The Pi implementation lowers
only that command to the existing Neon/V3D offscreen clear. The test backend
executes state only. UNO Q compiles the portable surface and reports no device;
it must neither reference Pi symbols nor claim a synthetic GPU in production.
Shaders, drawing, descriptors, WSI, semaphores, events, multiple queues and
general formats remain loudly unsupported.

Required proof gates:

- regenerate every added value/member/prototype from the pinned registry and
  execute exact AArch64 size, alignment, offset, pointer-array and `pNext`
  refusal fixtures;
- execute public entry calls, not private shortcuts, for creation, binding,
  record, submit, fence completion, teardown, stale handles, wrong parents,
  overlap, range overflow, double bind, use-after-free, destroy-while-pending,
  and allocation refusal;
- mutation-test command order, layout/access masks, retained references, fence
  signal order, failure rollback, target restoration, and the rule that an
  unsupported operation never reaches the backend;
- record the backend call stream independently and prove that the host test
  performs no CPU image clear while still avoiding MMIO;
- build a production Pi probe and an UNO Q probe that both enumerate zero
  devices when development registration is absent;
- in a separately authorized Pi hardware test, poison an offscreen allocation,
  submit the public path, require bin/render counters to advance, require clean
  fault/OOM/error state, compare every pixel and both guards, and repeat with
  caches off and on while proving the active HDMI/DSI target is unchanged.

Passing this slice would establish one honest Vulkan-shaped transfer path. It
would not establish Vulkan 1.0 implementation, shader support, presentation,
general resource behavior, concurrency, or conformance.

## Primary specifications

- [Khronos Vulkan Registry](https://registry.khronos.org/vulkan/) explains that
  `vk.xml` is the source for API declarations and validity metadata.
- [Pinned Vulkan-Headers registry](https://github.com/KhronosGroup/Vulkan-Headers/tree/8864cdc896bbc2a9b6eb36b3218fc9ef57908d77/registry)
  is the exact vocabulary source used by this tree.
- [Vulkan fundamentals](https://docs.vulkan.org/spec/latest/chapters/fundamentals.html),
  [command buffers](https://docs.vulkan.org/spec/latest/chapters/cmdbuffers.html),
  [memory allocation](https://docs.vulkan.org/spec/latest/chapters/memory.html),
  and [synchronization](https://docs.vulkan.org/spec/latest/chapters/synchronization.html)
  define the object, host-threading, command, resource and dependency behavior
  that an implementation must preserve.
- [Vulkan shaders](https://docs.vulkan.org/spec/latest/chapters/shaders.html),
  the [Vulkan environment for SPIR-V](https://docs.vulkan.org/spec/latest/appendices/spirvenv.html),
  and the [SPIR-V Registry](https://registry.khronos.org/SPIR-V/) define the
  shader input and validation boundary.
- [Window System Integration](https://docs.vulkan.org/spec/latest/chapters/VK_KHR_surface/wsi.html)
  defines the surface/swapchain separation from core execution.
- [Khronos Vulkan CTS guidance](https://github.khronos.org/Vulkan-Site/guide/latest/vulkan_cts.html)
  describes the distinction between development testing and a conformant
  implementation.

The current V3D code cites Mesa for packet and job-sequencing research. Mesa is
not a runtime dependency, and this document does not relicense or clear the
provenance of any translated driver expression. The public-source provenance
hold remains in effect: future work must use the Khronos material under its
retained terms and independently document any hardware-driver source used,
without copying GPL driver code into MIT-labeled Anvil source.

## Dynamic render geometry â€” Pi 4 acceptance, 2026-09-13

The V3D layer now has one pure geometry planner used by the live packet path.
Neon carves tile pools and coordinate tables for a declared pre-init capacity,
validates the already mapped target span, and rebinds the complete geometry as
one transaction.  Vulkan saves and restores the full display surface around a
clear or draw; its linear BGRA8 row pitch is now derived from the image width,
not copied from the display.

The returning RAM diagnostic
`RaspberryPi4/Examples/Diagnostics/vulkanDynamicGeometryProof.pi4` passed on
build 101 with PMFBOOT SHA-256
`275fdb26db7fe3065b4e7f61f4eb303441dec4d1d71e96f414c44c00a6b74767`.
At 800x1280, 640x360 and 257x193, each public Vulkan clear mapped, submitted,
completed its fence, advanced one bin and render job, and produced exact
`$FF3380B2` pixels with no mismatch or new V3D fault/OOM.  1281x64 was refused
before either job counter moved.  A subsequent ordinary 800x1280 engine frame
advanced both counters and produced exact `$FF2060A0`, proving the restored
geometry remained operational.  The payload returned zero and shut down the
V3D MMU.

The detailed report and capture are recorded in
`docs/VULKAN_DYNAMIC_RENDER_GEOMETRY_DESIGN.md`.  This proves the prerequisite
for an honest image-format-properties query; it does not itself add or claim
that entry point.

### One-utile optimal-to-optimal microcopy

A separate Pi 4 capability copies one 1â€“4 by 1â€“4 BGRA8 rectangle between distinct equal-size level-zero optimal images. Source and destination offsets are independent; each rectangle must fit within one 4Ã—4 UIF utile, and each imageâ€™s other texels are preserved. The route requires both `TILED_RECT_COPY` and dedicated `TILED_MICRO_COPY`; it is isolated as the sole copy/transfer/draw operation in its command buffer. Shared recording and submit validation recheck capability, resource/layout generations, extents and allocation aliasing before dispatch. Pi 4 lowers only the requested row bytes with guarded DMA at a 16-byte row stride; it does not use CPU pixels or TFU. Other backends fail closed. The 2026-09-30 proof changed four destination texels and preserved 252 (including twelve same-utile neighbors); all 256 source texels remained unchanged. Each readback checked 64 padding words and 128 guards. TFU stayed at 2, DMA advanced 0â†’1 and jobs 2â†’3; a source utile-crossing request returned `-20005` during recording. MMU, OOM and native fault counts were zero. See `docs/evidence/vulkan-optimal-optimal-microrect-pi4-20260930/README.md`. Submit-time malformed-stream preflight remains desk-gate evidence.

### One-utile optimal-image buffer readback

A separate Pi 4 DMA capability supports one interior `vkCmdCopyImageToBuffer` region of 1â€“4 by 1â€“4 BGRA8 texels, wholly inside one source 4Ã—4 UIF utile. Destination offset remains four-byte aligned; tight or padded rows are checked against the exact last-row span `(height - 1) * pitch + width * 4`. The shared API requires both ordinary linear-transfer support and dedicated `TILED_MICRO_READBACK`; it rejects image/buffer aliasing and verifies capability, resource lifetime, bounds and destination stride before any DMA. The Pi 4 backend reads from the source's independent local UIF offset with guarded DMA; other backends fail closed. The 2026-10-01 proof matched four requested texel words, passed twelve row-padding checks, left all 256 source texels unchanged (including twelve same-utile neighbors), and passed 64 full-readback-padding, 16 stage-spare and 128 guard checks. TFU stayed at 1, DMA advanced 0â†’1 and jobs 1â†’2. A crossing-utile request returned `-20005` during recording; MMU, OOM and native faults were zero. See `docs/evidence/vulkan-optimal-buffer-microreadback-pi4-20261001/README.md`. Submit-time malformed-stream preflight remains desk-gate evidence. Other backends do not advertise this capability.

### Optimal-to-linear one-utile microcopy

The shared image-copy command has a separate one-operation microcopy shape, requiring `LINEAR_TRANSFER` and `TILED_TO_LINEAR_MICRO_COPY`. One 1â€“4 by 1â€“4 BGRA8 rectangle must fit wholly within one source 4Ã—4 UIF utile and target a distinct, equal-size linear image. Pi 4 performs guarded DMA only for the requested rows, after checking destination pitch/span, live resources, layout and aliasing; no CPU pixel or TFU path is used. Other backends fail closed. The 2026-10-01 Pi 4 trace changed four destination texels, preserved 252, and left all 256 source texels unchanged, including twelve same-utile neighbors. The measured destination pitch was 64 bytes, giving zero row padding; separate checks covered 64 padded oracle words and 96 guards. DMA advanced 0â†’1, jobs 1â†’2, TFU remained 1; a crossing-utile request returned `-20005` at recording. Submit-time whole-stream preflight is desk-gate evidence only. See `docs/evidence/vulkan-optimal-linear-microcopy-pi4-20261001/README.md`.

### Linear-to-optimal one-utile microcopy

The shared image-copy command has a separate one-operation microcopy shape, requiring `LINEAR_TRANSFER`, `LINEAR_TO_TILED_RECT_COPY`, and dedicated `LINEAR_TO_TILED_MICRO_COPY`. One 1â€“4 by 1â€“4 BGRA8 rectangle must fit wholly within one destination 4Ã—4 UIF utile and target a distinct, equal-size optimal image. Pi 4 uses the live linear source pitch and guarded DMA only after validating the source span, destination tile window, live resources/layout and allocation separation; no CPU pixel or TFU path is used. Other backends fail closed. The 2026-10-01 Pi 4 proof changed four destination texels and preserved 252, including twelve same-utile neighbors; all 256 source texels remained unchanged. Source pitch was 64 bytes with zero row padding, source offset/span were 332/72 bytes, and the destination UIF offset was 1,316 bytes. Separate checks covered 64 padded oracle words and 96 guards. TFU stayed at 1, DMA advanced 0â†’1, jobs 1â†’2; a crossing-utile request returned `-20005` at recording before DMA. Submit-time whole-stream preflight is desk-gate evidence only. See `docs/evidence/vulkan-linear-optimal-microcopy-pi4-20261001/README.md`.

### Two-by-two UIF grid optimal-image upload

The shared `vkCmdCopyBufferToImage` command has a separate one-region path for a destination rectangle intersecting at most two adjacent UIF columns and rows. It requires `BUFFER_TRANSFER`, `LINEAR_TRANSFER`, the base `BUFFER_TO_TILED_RECT_COPY`, and dedicated `BUFFER_TO_TILED_GRID_COPY`. The command retains its 64-byte buffer offset, tight/padded row pitch and exact accessed source span; every tile intersection and source/destination window is preflighted before guarded DMA. It is isolated as the command buffer's sole transfer or draw operation. Pi 4 passed destination `(3,3)` extent `5Ã—5`, with four measured intersections of `1Ã—1`, `4Ã—1`, `1Ã—4`, `4Ã—4`; 25 texels changed and 231 remained unchanged, including 39 neighbors inside the touched tile grid. Source checks covered 25 exact words plus 327 sentinels, including 15 source-padding words; oracle padding and guards covered 64 and 96 words. TFU stayed at 1, DMA advanced 0â†’4 and jobs 1â†’2; later oracle readback advanced DMA 4â†’20. The recorded `6Ã—6` refusal was tested with only the original â‰¤2Ã—2 grid cap, before the extended cap existed. With `BUFFER_TO_TILED_GRID_4X4_COPY` enabled, an otherwise-valid `6Ã—6` region can be admitted; that exact size has not been silicon-tested. Submit-time malformed-stream preflight is desk-only. Other backends fail closed; the full-image TFU upload is unchanged. See `docs/evidence/vulkan-buffer-optimal-grid-pi4-20261001/README.md`.

### Extended optimal-image UIF grid upload

The shared `vkCmdCopyBufferToImage` path has a distinct extended route for one region intersecting three or four adjacent UIF columns or rows (maximum four-by-four). This does not widen the existing â‰¤2Ã—2 `BUFFER_TO_TILED_GRID_COPY`/tag-3 promise: tag 4 requires `BUFFER_TO_TILED_GRID_4X4_COPY` plus `BUFFER_TRANSFER`, `LINEAR_TRANSFER` and `BUFFER_TO_TILED_RECT_COPY`. It retains the exact buffer-offset, row-pitch and source-span validation; the full set of tile intersections is preflighted before guarded DMA. The Pi 4 proof copied 81 texels from `(3,3)` extent `9Ã—9` on a 16Ã—16 image, with 420-byte span and 48-byte pitch, across nine intersections (`1Ã—1`, `4Ã—1`, `4Ã—1`, `1Ã—4`, `4Ã—4`, `4Ã—4`, `1Ã—4`, `4Ã—4`, `4Ã—4`). It preserved 175 texels including 63 in the touched 12Ã—12 grid; source checks covered 81 exact words plus 271 sentinels (27 padding), with 64 oracle-padding words and 96 guards. TFU stayed at 1, DMA advanced 0â†’9, jobs 1â†’2, and later oracle readback advanced DMA 9â†’25. All status slots/helper and MMU/OOM/native/validation-fault counts were zero. Fifth-row/column and malformed-submit refusals are desk-gate evidence only. Other backends fail closed. See `docs/evidence/vulkan-buffer-optimal-grid4-pi4-20261001/README.md`.

A separate maximum-boundary Pi 4 proof exercised all sixteen 4Ã—4-grid intersections with one 13Ã—13 buffer upload at `(3,3)` into a 16Ã—16 image. The row-major texel counts were `[1,4,4,4]` followed by `[4,16,16,16]` for each remaining row. It changed 169 texels and preserved 87; buffer offset/pitch/span were 64/64/820 bytes. Checks covered 169 source words, 39 row-padding words, 183 total sentinels, 64 readback-padding words and 96 guards. Partial upload DMA advanced by 16 in one backend job while TFU stayed unchanged; the full-image readback advanced DMA by another 16. Status, MMU, OOM, native and validation-fault counts were zero. The evidence is `docs/evidence/vulkan-buffer-optimal-grid4-max-pi4-20261001/README.md`. This exercises the upper 4Ã—4 boundary on Pi 4 only; other backends remain fail-closed and full-image TFU behavior is unchanged.

### Bounded partial optimal-to-optimal edge-tail copy

The shared `vkCmdCopyImage` API supports one partial region per command buffer between distinct, equal-size level-zero BGRA8 `UIF_NO_XOR` images. Source and destination XY offsets remain 4-texel aligned. Width or height may end with a short UIF tile only when that dimension reaches the right or bottom edge in both images; the ceil-divided tile count is capped at 256. This shape requires `TILED_RECT_COPY` plus the separate `TILED_EDGE_TAIL_COPY` capability. Whole-image copies retain their TFU path, aligned full-utile rectangles retain the rectangle path, and one-utile microcopies retain their separate path. The Pi 4 backend preflights all clamped tile windows and performs guarded DMA for valid texel rows only, preserving source data, untouched destination texels and padded UIF storage. Other backends fail closed.

The 2026-10-01 Pi 4 proof copied a `(8,8)` `5Ã—5` region between distinct 13Ã—13 images: 25 destination texels changed, 144 stayed unchanged, and all 169 source texels were unchanged. The report checked 338 exact staging words plus 78 staging-padding words, 91 readback-padding words in each full readback, and 160 guard checks. TFU stayed at 2, partial DMA advanced 0â†’4 and jobs 2â†’3; the oracle readbacks advanced DMA 4â†’20â†’36. A non-edge `(4,4)` `5Ã—5` request returned `-20005` during `vkEndCommandBuffer` before further DMA. Status slots were zero; MMU, OOM and native faults were zero, with one intentional validation fault. The measured trace is `docs/evidence/vulkan-optimal-optimal-edge-tail-pi4-20261001/report.bin`; the PMF SHA-256 is `8594C760D6E3206CFDC5DEAE41DBAAF6C0A770EDDA5FB5A369EBC3AA40ED027F`.

A separate Pi 4 right-edge-only `5Ã—4` proof copied from source `(8,4)` to destination `(8,8)` in distinct 13Ã—13 optimal images. Its full-image oracles matched 20 copied and 149 untouched destination texels, including five immediately below the rectangle; all 169 source texels remained unchanged. The partial copy advanced guarded DMA 0â†’2 and backend jobs 2â†’3 while TFU stayed at 2. Both full-image readbacks then advanced DMA 2â†’18â†’34. Staging, readback padding and 160 guards passed; all status, MMU, OOM and native-error slots were zero. A nonedge source `(4,4)` request returned `-20005` during recording without another DMA operation. The measured report is `docs/evidence/vulkan-optimal-optimal-right-edge-pi4-20261001/report.bin` (SHA-256 `B8B121A0578237D93DD3D0DB8B7571253A27C8AC3B7958703A22C21B343D9D5B`). This adds no capability claim for other boards.

A separate Pi 4 bottom-edge-only `4Ã—5` proof copied from source `(4,8)` to destination `(8,8)` in distinct 13Ã—13 optimal images. Its full-image oracles matched 20 copied and 149 untouched destination texels, including five immediately right of the rectangle; all 169 source texels remained unchanged. The partial copy advanced guarded DMA 0â†’2 and backend jobs 2â†’3 while TFU stayed at 2. Both full-image readbacks then advanced DMA 2â†’18â†’34. Staging, readback padding and 160 guards passed; all status, MMU, OOM and native-error slots were zero. A nonedge source `(4,4)` request returned `-20005` during recording without another DMA operation. The measured report is `docs/evidence/vulkan-optimal-optimal-bottom-edge-pi4-20261001/report.bin` (SHA-256 `E52AAB7AD6905E56EDACBD98A89DF2EBA4EC51467D5C39EBCDDB6DE48511F77D`). This adds no capability claim for other boards.

The direct buffer-fill route has a bounded Pi 4 silicon proof. A 16-word `vkCmdFillBuffer` changed only the requested range of a 256-byte buffer; the other 48 words and alignment-derived prefix/suffix guards remained intact. Guarded DMA and backend-job counters each advanced once while TFU, V3D bin/render and display counters stayed unchanged. An offset-2 request returned `-20001` without extra DMA. Evidence: `docs/evidence/vulkan-buffer-fill-pi4-20261001/README.md`. This proof does not extend GPU-backend support to other boards.

### Compact-particle compute expansion on Pi 4

A returning Pi 4 V3D CSD diagnostic used two hardware workgroups of 16 lanes to expand 32 distinct compact particle records into 192 ordered Vulkan-format vertices. Its exact 1,152-word output oracle, group-boundary markers, input/canaries, output guards, and V3D fault checks passed; completion advanced 0â†’1 in 210 microseconds. The first one-group test also passed its 16-record oracle. See `docs/evidence/neon-particle-csd-two-group-pi4-20261003/README.md`. Later proofs placed that output in a live Vulkan vertex buffer and rendered it. The current-source moving 10,000-particle comparison passed four frames on Pi 4: the CPU path measured 454,115 Âµs and the CSD path 389,334 Âµs per frame median, with every cell's green/black pixel probes, bin/render jobs, fault checks, and teardown passing. See `docs/evidence/neon-particle-dynamic-current-pi4-20261004/README.md`. The CSD route is opt-in, is not public `vkCmdDispatch`, and has no hardware evidence on another board.

The Anvil-only Neon port adapter also passed a Pi 4 offscreen Vulkan frame with a filled polygon, outlined polygon, static line, and two ordered sprites: five draws, 54 vertices, expected pixel probes and color counts, and clean teardown. See `docs/evidence/neon-vk-port-geometry-pi4-20261003/README.md`. This is an application-level library proof; the new adapter is not part of the resident Pi 4 monitor's command path, and it does not establish full Neon application parity.

### Exact 256-tile partial optimal-image upload on Pi 4

Four bounded Pi 4 RAM runs exercised two ordered `vkCmdCopyBufferToImage` calls into one 72Ã—64 optimal BGRA8 image at aggregate budgets 64, 128, 192 and 256 complete UIF utiles. TFU initialization and an independent mapped UIF oracle established all 4,608 baseline texels before the partial work. The maximum run changed 4,096 texels and preserved 512 in the center gap, the checksum of all 1,536 padded UIF texels, 128 image guards and 64 source guards. Guarded DMA advanced 0â†’256 and backend jobs 1â†’3, while TFU stayed at one job after initialization; all error and fault checks passed. The full payload took 1.233617 seconds, with about 1.4 seconds observed by the monitor under a 15-second deadman and no flash. This measured bound applies to Pi 4 only; other backends remain fail-closed. See `docs/evidence/vulkan-two-partial-optimal-aggregate-pi4-20261001/README.md`.

\n


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


## Current line placement at four rotations - 25 October 2026

The independent Pi 4 line proof matches all 131,072 logical BGRA bytes from
eight frames: both immediate and bulk line paths at 0, 90, 180 and 270 degrees.
Horizontal/vertical lines with reversed endpoints, a degenerate pixel, shallow
and steep diagonals match a rational pixel-center oracle. The chosen inputs
avoid rasterizer edge ties; arbitrary clipped lines and outline joins are
outside this proof. Twenty corrupted reports/captures are rejected. The
public builder emits the exact whole PMF used on hardware. Historical native
line/outline scenes remain preserved, with their prior differences explicit.
See `docs/evidence/neon-line-contract-pi4-20261025/README.md`.


## Combined draw-record capacity - 25 October 2026

The shared command pool, private V3D slots and configurable Chrome ceiling
now hold 6,144 records. A physical Pi 4 frame accepted 4,096 boxes plus 2,048
text calls, refused the next call without cursor/guard changes, rendered exact
pixels, and freed every row. Recreating with a two-draw limit preserved that
limit and rendered a fresh exact frame. All 32,768 GPU bytes match; 31 checker
mutations are rejected. The final unmodified-renderer payload used bounded
watchdog progress checkpoints and returned in 21.5 seconds; the earlier
15-second whole-payload attempt failed with a watchdog restart. Separate
family vertex budgets and maximum vertex workloads remain open. Evidence:
`docs/evidence/neon-combined-draws-pi4-20261025/README.md`.


## Pi 4 variable-region guard corrected in source - 25 October 2026

Monitor variables now grow their Pi 4 map/guard reservation from the linked
ordinary-plus-preserved end rather than stopping at the 16 MiB minimum.
Safe relocated silicon fixtures on both sides of that minimum pass 18 native
checks and match PMF/linker extents; 13 corrupted proofs are rejected. Normal
build 331 compiles and derives reservation 0D000000..0E6FFFFF, but is not
installed. Resident 328 still uses the older map. Topic 1249 remains open
pending deployment acceptance. Pi 5 layout is unchanged. Evidence:
`docs/evidence/pi4-linked-variables-20261025/README.md`.


## Direct triangle fans - 25 October 2026

The shared pipeline validator accepts TRIANGLE_FAN only with the separate
backend capability, now advertised by Pi 4. Neon stores n original points
instead of 3*(n-2) expanded vertices and restores its ordinary pipeline after
the draw. Capability-masked fallback retains triangle-list lowering. The
selected non-indexed four-rotation hardware tests match 262,144 GPU bytes,
check tight-buffer refusal and full retirement, and reject a physical stale-
topology control. All 245,760 current baseline scene bytes and 124 widget
checks remain exact. Native family budgets, maximum point/vertex workloads,
indexed/instanced fan hardware evidence and full port completion remain open.
See `docs/evidence/neon-triangle-fan-pi4-20261025/README.md`.


## Neon bulk range preflight - 25 October 2026

Bulk reservations check remaining capacity before multiplying and bulk draws
validate their full span against reserved storage before recording. Physical
Pi 4 before/after evidence records five wrapped-count admissions and four
invalid-draw admissions in the old implementation; the corrected implementation
refuses them without cursor, free-row, fault or buffer changes. Valid exact-
capacity subranges match all 16,384 GPU bytes, with zero final allocations.
The strict oracle rejects 65 corrupted proofs and the old report. Evidence:
`docs/evidence/neon-bulk-range-pi4-20261025/README.md`. Separate family budgets,
maximum native workloads, desktop integration and the broader goal remain open.


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
All245760 current15-scene bytes and 124 widget checks remain exact, with blank
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
complete current15-scene PMF still matches the physical regression and all 245760
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
across245760 bytes and 124 widget checks under the larger variable layout.

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
15 scenes retain245760 bytes and 124 widget checks. Build338 compiles, notinstalled.
Evidence: `docs/evidence/vertex-shared-vpm-pi4-20261026/README.md`.

Compact32-byte line records work in the isolated public Vulkan proof; production
Neon still uses its prior144-byte lowering. Full native line/outline capacity
and integration remain open, as does the wider high-register stage/mode issue.
No throughput or full engine/Vulkan completion claim follows from this proof.


## 26 October 2026: shared contracts and native ownership

Current work keeps one shared Vulkan API/object/memory/synchronization engine
for Anvil targets. The explicit unlaunched draw-admission result and portable
reservation rollback are in that shared engine; the Pi 4 backend supplies the
hardware-specific refusal classification. Unqualified backend failures retain
the existing conservative quarantine behavior. The separate native clear-rectangle
ownership change belongs to Pi 4's renderer and does not add a Pi 4 dependency
to the shared API.

The shared clear-attachment state composition compiles for Pi 3, Pi 4, Arduino Q
and Rock Pi 4C with target-validated memory layouts. Its Pi 4 image also passes
on the board using the explicit state backend, which submits no GPU work and
writes no target pixels. The other images are compile-only. These checks do
not establish hardware drivers or Vulkan conformance on those boards. The
existing unsupported capabilities remain withheld.

Current evidence is in `docs/evidence/neon-draw-admission-pi4-20261026/` and
`docs/evidence/neon-clear-owner-pi4-20261026/`. Counted monitor 341 compiles
the cumulative changes but remains uninstalled; verified 338 is the resident
Pi 4 build. Earlier installed-build paragraphs above describe their historical
proofs. Source publication awaits the mandatory architecture and provenance
gates; no complete-port or conformance claim is made.


The later shared-state contract evidence in
`docs/evidence/vulkan-state-contracts-20261026/` adds six CPU-executed refusal,
retry and quarantine cases plus an executed stale-classification negative.
This is independent of V3D execution. The prospective proof layouts now include
target-specific report memory and avoid known Pi 3/Rock monitor reservations;
older off-board compile images must not be run with their obsolete layouts.
Both admission and clear-state compositions compile for all four named targets,
with Pi 4 execution only. Live maps and hardware drivers remain separate work.


The clear-state fixture ownership update is recorded in
`docs/evidence/vulkan-clear-fixture-ownership-20261026/`. Its shared body is
separate from the Pi 4 entry point. Ten rebuilt complete containers are identical
to earlier references; no additional hardware execution or capability is claimed.
The mandatory architecture gate remains red at 286 new or grown keys.


The later shared CPU font-atlas owner is recorded in
`docs/evidence/neon-atlas-shared-pi4-20261026/`. It removes ten downward-call
keys without moving native TFU tiling. A shared-only Pi 4 contract verifies the
complete raster and UV bytes; three other target compositions compile only.
Current-source hardware Vulkan integration retains all fifteen scene captures
and 124 widget checks, including the earlier clear and admission changes.
Normal monitor 342 builds but is not installed; resident 338 remains in use.
The mandatory architecture gate is still red at 276 new or grown keys, and
broader compatibility/conformance and source publication remain incomplete.


The current task is explicitly the Neon port within Anvil and Anvil Vulkan;
desktop Vulkan integration is outside its acceptance requirements. Later
fallback evidence is in `docs/evidence/neon-fan-fallback-lifetime-pi4-20261026/`:
three frames prove distinct fan ranges, abort/reuse and atomic refusal; a separate
full mixed case covers 262,144 outline/fill points plus 98,304 textured vertices.
The latter needs a larger explicit diagnostic heap and retains the earlier clean
out-of-memory attempt as a failed case. No production heap, renderer, capability
advertisement or monitor installation changed. Capability-masked Pi 4 execution
does not prove another board's hardware driver. Source publication remains pending.


The public font-binding wrapper now has the shared frontend as its owner.
`docs/evidence/neon-font-binding-shared-pi4-20261026/` records the direct public
API's 50-check CPU contract, complete raster/UV oracle, four-target compilation
and current-source fifteen-scene Anvil GPU regression. Native lifecycle guards
remain intact. Normal monitor 343 builds but is not installed; resident 338
remains. The architecture gate still fails at 274 new or grown keys, with no
gate or ratchet change. Earlier atlas reports retain their exact historical
46-check schema through the checker's explicit selection flag.


The shared lifecycle/native-provider split is recorded in
`docs/evidence/neon-lifecycle-shared-pi4-20261026/`: 409 controlled-provider
observations, an executed missing-frame-guard negative, a separate real prepared
Vulkan handoff/render/release proof, and the fifteen-scene regression. All physical
payload tests here used resident 338; other-target controlled-provider builds are
compile-only. The exact six native operations are a functional contract; no gate
algorithm or ratchet changed. The architecture gate still fails at 270 keys.

Normal build 344 was written to the boot medium with a verified 338 backup and
whole-file digest checks. One reset command was sent, but the planned network
startup check received zero bytes. Running version/map/console state are
UNCONFIRMED, and board-command access is on hold pending the required console
check. There is no successful-boot or isolated-runtime-defect claim. Later recovery
must have its own evidence; source publication and full Anvil Vulkan remain open.


Async completion and teardown candidates newer than boot-file 344 are documented
in `docs/evidence/neon-async-teardown-candidates-20261026/`. Failed fence waits
retain submitted-frame state. A new status-bearing Chrome teardown preserves
failure through both lifecycle callbacks and resident console ownership; the
legacy void API delegates to it. Successful release resets pending-frame state.
Topics 1453 and 1454 remain OPEN: four-target controlled-provider compilation,
synthetic checker tests and a Pi4 real-Vulkan composition compile do not establish
runtime/GPU acceptance. No new board command or installation occurred. The
architecture gate remains refused at 270 keys. The full source/emitted adapter
acceptance gate is NOT RUN: its source-only leg stops at an older bitmap-plan
spelling assertion; no emulator was loaded. Earlier 338 pixels do not validate
these later candidates. Console reconciliation and physical validation remain
required; there is no new running-build or complete-Vulkan claim.


The stale adapter source assertion is now superseded by the source-only repair
in `docs/evidence/neon-acceptance-source-repair-20261026/`: 62 hook, 396 adapter
and five scene checks, with 39 hostile source faults rejected. The tool reads
five exact owners, follows shared callbacks and compact/indexed geometry, and
records full/emitted/GPU acceptance as NOT RUN. This phase changes validation
tools only. The emitted geometry fixture retains obsolete expansion expectations
and still requires reconciliation; no compiler, emulator or board execution was
used here. Topic 1455 remains open. Earlier evidence snapshots retain their
historical failures. Pending async/teardown hardware acceptance, architecture
publication and the unknown post-reset 344 state are not resolved by this pass.


The earlier stale emitted-fixture composition is superseded by compile-only
current fixtures in `docs/evidence/neon-current-emitted-candidates-20261026/`:
1,200 planned current-geometry observations, canonical hook include closure,
28 box assertions using current clipping/budget helpers, and separate returning
Pi CPU candidates for hooks/box/oracle baseline. Geometry also compiles for
three other CPU targets. No fixture executed; full emitted/GPU acceptance remains
NOT RUN. Host-gate LOAD00400000 images overlap the monitor and are never eligible
for direct upload. Returning candidates still require the current map/ownership
review after the console check. Positive and explicit source-negative checker
self-tests each reject 2,412 synthetic corruptions, not production execution.
Topic 1455 remains open. Architecture publication is still refused at 270 keys,
and the post-reset 344 version/map/console and board hold are unchanged.


The shared ABI/fixture ownership move is documented in
`docs/evidence/neon-shared-owner-placement-20261026/`: one twelve-check AArch64
body, four target entries in their board test areas, three shared CPU templates
and the native hook composition in the Pi test area. Four full compiled ABI
containers and the three existing generated fixture programs remain unchanged.
The architecture gate is still refused at 264 keys, with no gate/ratchet change.
The provenance analyzer reports no moved-file findings but still refuses wider
unclassified citations. Compilation preservation and source-only checks are not
runtime/GPU or publication acceptance. No board command, emulator or monitor
update occurred; the post-reset 344 state and console-check hold are unchanged.


Public line-height and text-width queries now have a shared frontend owner.
Their callback/fallback semantics and existing width scan are preserved; the
height fallback delegates to the equivalent public raw bitmap getter. The
shared-only 79-observation composition compiles for four CPU targets and the
Pi4 prepared Vulkan composition compiles, as recorded in
`docs/evidence/neon-shared-text-metrics-20261026/`. None has executed. Synthetic
checker tests and source body preservation do not replace runtime/GPU proof.
The architecture gate still refuses 264 keys, wider provenance omissions remain,
and source publication and the unknown post-reset 344 board state are unresolved.


Target rebind now refuses submitted or abort-required frames; WSI attachment
also refuses an open frame. This prevents target identity changes before async
completion and attachment to an already-owned frame. Only two guards change.
The focused 214-observation proof and old-guard negative compile, along with
four CPU targets and the Pi4 Vulkan composition, but none has executed. See
`docs/evidence/neon-target-ownership-candidate-20261026/`. Topic1456 remains
open; hardware validation, publication gates and the post-reset344 console
state remain unresolved. This is an Anvil-only candidate, not a GPU pass.


Resource mutation paths now refuse submitted and abort-required frames before
cache eviction, glyph lookup/raster work, upload recording or sprite mutation.
This prevents a warm upload from reusing the frame command buffer/fence before
Finish. Nine entry guards change; 156 other adapter procedure bodies remain
unchanged. Source checking now includes 33 frame-ownership assertions across
these entries and the prior target guards. Its 72 hostile source cases are
rejected. The actual Pi4 Vulkan composition compiles, but emitted and GPU
acceptance remain NOT RUN. See
`docs/evidence/neon-async-resource-candidate-20261026/`. Topic1457 stays open.
The post-reset344 console check, publication gates and full Vulkan work remain
unresolved. This candidate has not been installed.


The renderer-neutral Vulkan lifecycle binder has a shared implementation owner
and a compatibility include for the existing Pi4 path. One shared controlled
binder proof now compiles for four CPU targets without a native renderer;
none executed. Two proof consumers use the public shared float conversion APIs
instead of exact native forwarding aliases. The current shared-VPM Vulkan
composition compiles, without a new GPU result. Architecture publication still
refuses 261 keys (three fewer), with no architecture-gate or ratchet change.
The compatibility extension finding remains counted; wider provenance and
post-reset344 console/hardware acceptance are unresolved. Evidence:
`docs/evidence/neon-shared-graphics-proof-20261026/`.


Failed external initialization and teardown now retain a shared cleanup
obligation. Shutdown retries the same callback even when readiness is zero;
initialization, callback replacement, native selection and new frame work refuse
until cleanup succeeds. The Vulkan binder leaves failed creation for this
checked shutdown path. After successful cleanup, reconfigure before retrying.
The 477-observation lifecycle composition and binder composition compile for four
CPU targets, and the Pi4 Vulkan composition compiles; none executed. Historical
409-observation captures require --legacy-409 and cannot validate this change.
Evidence: `docs/evidence/neon-init-cleanup-candidate-20261026/`. Topic1458 remains
open. Architecture publication still refuses 261 keys; wider provenance and the
post-reset344 console/hardware acceptance remain unresolved.


Target rebind now requires a read-only framebuffer-owner preflight before any
adapter target field or generation changes. It checks live dependencies,
ownership, bound span, exact linear BGRA8 geometry/pitch and target use state.
Caller synchronization and submission validation remain required. The 67-object
and 235-adapter planned-observation compositions compile for four CPU targets;
none executed. The actual Pi4 Vulkan composition also compiles, without a new
GPU result. Initial adapter creation remains unchanged. See
`docs/evidence/neon-framebuffer-target-candidate-20261026/`. Topic1459 stays
open. Architecture publication still refuses 261 keys; wider provenance and the
post-reset344 console/hardware acceptance remain unresolved.


Initial adapter creation now gets the validated framebuffer row pitch before
changing target metadata or allocating resources. It no longer assumes packed
width-times-four rows. A shared read-only pitch query delegates the complete
target check and returns a positive pitch or explicit error. The 81-observation
object-engine proof includes a 31-pixel row with 124 pixel bytes and 128 planned
pitch; four CPU targets and the Pi4 Vulkan composition compile, but none
executed. See `docs/evidence/neon-initial-target-pitch-candidate-20261026/`.
Topic1460 stays open. Source checks pass 62/436/5 and reject 81 source mutants;
these do not execute the constructor. Architecture publication still refuses 261
keys, with wider provenance and post-reset344 console/hardware acceptance owed.


Checked adapter teardown now stops recording, confirms device idle, and requires
successful WSI rollback before clearing the present record/callback ownership,
unmapping or releasing resources. Refusal retains those resources for cleanup
retry while readiness stays stopped. The controlled 360-observation/18-case proof
and real Pi4 Vulkan composition compile; none executed. Source checks pass 62/442/5
and reject 88 hostile source cases; they do not prove GPU recovery. See
`docs/evidence/neon-wsi-teardown-candidate-20261026/`. Topic1461 remains open.
Architecture publication still refuses 261 keys, with wider provenance and the
post-reset344 console/hardware acceptance unresolved.


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


## Shared float math dependency, 26 October

The Neon float adapter now uses Anvil/Math/float32.pbi; the old Pi4 path remains
a compatibility include. All 52 math procedures and implementation data are
unchanged. A complete Pi4 UI composition has identical raw and PMF bytes;
four AArch64 interface probes compile and dual includes deduplicate. These are
compile/equivalence checks, not numeric, performance or GPU runtime measurements.
The monitor is unchanged. Architecture still refuses254 keys and expanded
provenance98 omissions. Exact scope and identities:
docs/evidence/neon-shared-float-math-20261026/README.md.


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

This replaces busy polling with an optional qualified wait for banner presentation; it does not reduce display refresh latency. No numerical CPU reduction or speed gain is claimed: elapsed frame statistics include waiting. No WSI extension, FIFO queue or full-port completion claim. HDMI, real fault recovery, actual WSI provider registration and other Vulkan capabilities remain open. Publication checks still refuse254architecture findings and 98provenance omissions. No source publication or gate relaxation.

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

Public WSI surface/swapchain API, negotiation/dispatch, blocking acquisition and broader Vulkan capabilities remain unfinished. HDMI and actual hardware-fault recovery remain unproved. Mandatory publication checks still refuse254architecture findings and 98provenance omissions across986sources. No source publication or gate/license relaxation.

Evidence: docs/evidence/vulkan-parent-lifetime-pi4-20261026/. Topic1471 remains open.


## Public surface queries and instance enablement - 2026-10-26

The public API advertises VK_KHR_surface revision 25 as its one instance extension, validates enablement and resets permission on instance-slot reuse. All five standard surface commands are callable with C-compatible52-byte capabilities and8-byte format records. Counts, modes and VkBool32 use32-bit outputs. Format/mode discovery follows count-query, caller-capacity and VK_INCOMPLETE semantics. Capability conversion preflights every word before output; malformed/unrepresentable metadata refuses rather than truncating. Disabled, stale, foreign and lost owners do not mutate query output.

AnvilVkSurfaceCreate binds an explicitly registered native provider and key under an enabled instance. This is an Anvil integration function, not a fabricated OS/platform extension. The private non-extension constructor remains for existing internal callers. GIPA resolves the five commands only for a current enabled instance; null-instance and device lookup do not disclose their addresses. One bounded name matcher is shared by the core dispatcher and extension negotiation; the dispatcher still chooses its original128-byte cap. VK_KHR_swapchain/device extensions, platform window extensions, blocking acquisition and general asynchronous presentation remain unavailable.

Physical returning tests use actual API/core/state code with the explicit state-only GPU backend. Final24cases/192state observations cover all13 distinct capabilities words, exact layouts/offsets, output/count canaries, unsignedUINT32_MAX capacity, truncated enumeration, all five lookup permissions, unsupported extension, foreign/disabled/stale owners, loss and slot reuse. The strict oracle rejects203 synthetic corruptions. The earlier23-case version is retained separately. Parent lifetime11-case/132word regression also passed. UNOQ/QCM2290 compiles the final fixture using its canonical layout; compile-only, no other-board hardware claim.

The legacy core dispatch gate was updated for a correctly sized260-byte extension property output instead of a four-byte sentinel. Its first physical run returned0/167checks/0failures, but native-width result stores left upper halves in its eight-byte report slots untouched. The host correctly refused that report. Explicit integer-width stores fixed the fixture, and the returning Pi run passed all167 exact records. The initial30-second watchdog argument was rejected before upload/run; the valid15-second deadman was used for the actual run. No emulator was started.

The extension inventory audit now selects the exact VK_KHR_surface commands from its pinned registry, requires the complete callable family and checks arity/return shape; arbitrary extra commands still refuse. Its selected synthetic parser/source models pass and reject four malformed models. The full pinned-registry audit was NOT rerun: the exact raw pin URL returned404 and no local registry path was recorded. No checksum was weakened or replaced. The old emulator-backed dispatch command was also not run; the actual core gate was executed as a bounded returning program on the Pi instead.

Monitor353 enables the surface extension for its DSI instance and validates both real main/banner sources through support/capability/format/mode queries before use. Boot reported272confirmed frame switches=272privateWSIcompletions and2real public target checks withzeroerrors/timeouts. The physical geometry/keyboard/scale/DMA-return matrix passes with fresh public-query checks after rebinding; nativeV3D return also passes. Defaults restored; cores healthy; deadmanoff. These normal display tests do not inject real stopped-controller/DMA/GPU faults. No Bluetooth or desktop Vulkan change.

The new Khronos specification/interface citation is classified consulted in both provenance records, with existing MIT election/notices retained. Initial99omissions return to the prior98 after adding that owned citation; no gate/ratchet/license text was relaxed. Architecture still refuses254findings and provenance98across988sources; source publication remains unaccepted. This is surface-query/enablement support, not swapchain API completion or Vulkan conformance.

Contracts: https://docs.vulkan.org/refpages/latest/refpages/source/VK_KHR_surface.html ; VkSurfaceCapabilitiesKHR, VkSurfaceFormatKHR, surface query and GIPA reference pages from the same official documentation. No third-party implementation code was consulted.

Evidence: docs/evidence/vulkan-public-surface-pi4-20261026/. Topic1472 remains open.


Retained control layer (2026-10-27): shared state/input passes89 checks and57
ordered renderer calls on actual Pi4/Anvil354, and compiles for UnoQ. The real
bitmap Vulkan scene passes two65-draw frames,56 interior probes and20224 text
pixels. Fresh whole-frame SHA matches prove the faster poisoned/word-copy path
preserves all8192000 capture bytes; returning time falls13.5s to8.6s. Old parent
handles are rejected after teardown, glyph frame work/faults are zero, Vulkan is
restored and deadman off. No monitor update/reset. Retained TrueType and wider
application acceptance remain open; see docs/NEON_RETAINED_UI.md. These are not
full-engine completion or source-publication claims.

Mixed retained TrueType (2026-10-27): Anvil354/Pi4 now passes two prepared
mixed-face/four-size/Unicode GPU frames,39 setup assertions,65draws each and
720/708vertices. Independent FontTools/MuPDF8x boundary-aware checks pass56
geometry probes and28text runs (6921solid/16929exterior pixels,1channel-unit
tolerance). Current shared controller passes101assertions/57orderedcalls,
including handled callback-mutation refusal without draw truncation. Final
bitmap whole-image equality also passes. Every frame has zero glyph raster/
upload work, clean retirement and restored Vulkan/deadmanoff. A portable full
checksum validation loop is5.9times faster on the539-check workload; this is
not an overall renderer speedup. Shared state/checksum compile for UnoQ; the
full no-device retained canvas composition still refuses missing lifecycle
providers, with no dummy GPU/native implementation. Live retained DSI/application
acceptance and mandatory source publication remain open. Evidence:
docs/evidence/neon-retained-truetype-20261027/.


## Current Neon application qualification — 27 October 2026

The dated results above retain their original limits. Subsequent Anvil361 Pi4
work now qualifies resident sprite/particle/font ownership, mapping/scissors,
menus/tabs/editor/list/scroll, a composed application and shared chrome styling.
The composed application434/435 and its style regression439 each complete90actual
End calls and43pointer/transport checks, with an explicit scripted mode and a
separate no-injection mode. Device touch records were0; native keyboard and finger
actuation remain unqualified. Frame timing includes presentation waits. Latest439
has one37430us frame against33333us, so strict all-frame deadline success and
spare-workload headroom are not claimed. See docs/NEON_RETAINED_UI.md and immutable
neon-composed-application-20261027 / neon-chrome-style-20261027 evidence folders.

Shared neon_collision.pbi now implements the desktop math-operation group without
renderer/device/allocation ownership: box/circle/line queries, cubic curves,
alpha-mask sampling, hull generation and convex SAT. It uses caller-owned buffers
and explicit refusals/work budgets. The final361 returning proof443 passes511
assertions,21curvepoints/eighthullscenes, sparse and rotated/scaled masks plus
native generated-hull/curve geometry. Six image probes,671hull/409curve pixels and
1860title pixels pass; the verifier rejects1181 corruptions. UnoQ compiles only.
This is bounded binary32 geometry qualification, not maximum-capacity timing or
full application-input acceptance. See docs/NEON_RETAINED_UI.md and
neon-collision-geometry-20261027 evidence.

The formerly unavailable registry pin is now recovered from the official
Vulkan-Headers v1.4.350 source at commit8864cdc896bbc2a9b6eb36b3218fc9ef57908d77;
vk.xml SHA25650bd8c0f316eabf73d1c5fe3add2d89eaa480dbda9282c12c289e80e9d081e08.
Recovery alone does not establish a newly passed full registry/type audit.

Build361 remains installed, original Lato preserved, cores healthy, Vulkan
restored and display timeouts0/deadmanoff after443. No monitor update/reset,
storage write or Bluetooth was needed for geometry. Mandatory source publication
still REFUSES122architecture/98provenance with unchanged failure keys across1072
runtime sources. No Anvil source commit or gate-policy change was made. Remaining
engine formats/effects/animation/hot-zone/native-input work, wider Vulkan object/
shader/platform/presentation/recovery functionality and publication are still
open. Full Neon/Vulkan completion or conformance is not claimed.


Keyed chrome easing and hover maps (2026-10-27): new shared caller-owned modules
implement the desktop keyed-easing and redraw-region behavior. Prepared widgets
register clipped visible regions during Draw; a successful frame publishes the
candidate map, while failures preserve the old map. Opaque menu panels block
covered controls. Final361 captures446/447/448 pass396/402/405 assertions and60
frame-end calls/easing samples each, including close/overflow and both scrollbar
axes; style449 passes its unchanged188checks with tracking unbound. All images
were inspected. UnoQ overflow compiles only. The registered map covers chrome,
not all retained/custom application input. These results do not add physical
keyboard/touch qualification, a sprite-sheet player or full engine/Vulkan parity.
Cores/Vulkan/Lato/timeouts remain healthy; no monitor update/reset. See
NEON_RETAINED_UI.md and neon-chrome-motion-regions-20261027 evidence. Mandatory
publication still refuses the same122architecture/98provenance entries.


## Later Neon chrome button qualification (27 October)

Prepared shared chrome buttons and Glow/Frame helpers now pass on resident
Anvil361, captures452/453. Both final modes pass143 assertions,28 fake plus28
native complete callback records,340992 independently emitted reference pixels
(maximum channel difference0) and seven probes. Each checker rejects4981 planted
report/image corruptions. UnoQ compiles only. Caller scissor is preserved;
preparation stays outside Draw. No physical input or frame-rate claim is made.
See docs/NEON_RETAINED_UI.md for the bounded contracts and evidence history.

The API audit reads the six recorded desktop reference files and seven recorded
Anvil owners; it is not a whole-drive search or proof of global API absence.
Immediate button/Glow/Frame are now implemented. Remaining work includes panel
and text-layout helper equivalence, image formats beyond qualified BMP24/32,
legacy PNG loading convenience, optional existing postprocessing effects, font policy/
column helpers and native input qualification. The current Anvil font wrapper
already has right/centre text helpers and the concrete renderer has viewport
control; neither is incorrectly listed as wholly absent. Desktop OS/GL context
entry points require Anvil lifecycle equivalents, not desktop Vulkan work.
Broader registry/types, shader/control-flow, resource/format/synchronization,
WSI/HDMI and fault-recovery qualification remain separate unfinished Vulkan work.

A read-only preflight shot-status loss was recovered without upload/reset. The
tool now bounds recovery for three exact safe queries; a deliberately injected
reply-loss replay booted once. This is not a general UDP completeness fix. Full
Neon/Vulkan completion and source publication are not claimed.


## Later compressed asset prerequisite (27 October)

Shared raw DEFLATE/zlib decoding is physically qualified on Anvil361 capture455:
69cases/93assertions,306945 exact output bytes and294912 native sprite pixels.
All length/distance boundaries,32KiB history, malformed-stream/argument refusals
and native copied texture presentation are covered. UnoQ compiles only.
[Decoder contracts](NEON_PNG_DECODING.md) distinguish this from PNG support: PNG
container/filter/sample/interlace and asset dispatch integration remain open.
No driver/service ABI or firmware update was required. Full Neon/Anvil Vulkan
completion and mandatory source publication remain unfinished.


## Later PNG asset qualification (27 October)

Shared PNG decoding and explicit resident memory/file loaders now pass on
Anvil361 capture458:81cases/209assertions, all15 legal colour/depth pairs in
ordinary/Adam7 form,20752 exact RGBA bytes/5188 mask bytes and eight native images
with164736 compared pixels. The real file-handle path reads a943-byte PNG from
the Pi drive. The verifier rejects3771 planted faults. UnoQ compiles only.
[PNG contracts](NEON_PNG_DECODING.md) state scratch/transactionality,16-to8-bit
conversion, ignored ancillary colour management/default-image-only scope and
legacy BMP-only API limitations. This supersedes the earlier stream-only status,
not the broader unfinished Neon/Vulkan goal or mandatory source publication hold.


## VPM diagnostic ownership and returning-layout repair (27 October)

The V3D shader-record/VPM proof now lives under
RaspberryPi4/Tests/Vulkan/vertex_shared_vpm_proof.pbi. Its builder follows that
owner. The ownership-only step preserved the complete generated source and PMF
bytes; it removes three downward-call architecture failures without changing
the ratchet or exposing board details through a shared fake interface. The
current architecture gate refuses119 entries; provenance still refuses98.

The base all15 diagnostic lacked EnableFloatingPoint after shared float code
was introduced. That declaration is repaired. The returning builder also places
surface/window, banners and native GPU arena in ordinary payload windows rather
than assuming the standalone example's arena is a monitor reservation. Every
used range is checked against the fresh board map before entry. No compiler heap
allocation calls occur in the63-file literal include superset; the implicit heap
is not borrowed for image storage in the repaired layout.

First safe replay459 returned205: its purported triangle reference invoked the
now-compact production LinesBegin/End API while still expecting48 triangle
vertices. The reference now reserves eight explicit quads and fills/draws their
triangles through existing APIs. The expected48/11 vertex counts, full pixel
oracle, raw shader checks and sizing limits are retained, not weakened.

Final Anvil361 capture460 returns0/7.5hostseconds and passes the unchanged checker:
eight GPU64x64 frames/four rotations/131072 exact BGRA bytes,510 VPM sizing cases,
sixteen arithmetic nodes rendered/seventeen refused, and zero live allocations
after teardown. Forty-one corrupt proofs refuse. The eight-frame readback preview
and return screenshot were inspected. The return screenshot is CPU tier and is
not new DSI presentation qualification for those offscreen VPM frames. Cores,
Vulkan, original Lato and zero display timeouts are healthy/deadmanoff. No firmware
update/reset/storage/Bluetooth. Broader Neon/Vulkan and source publication remain
unfinished; the refusing source gates are not passes.


## Public coordinate-cache qualification (27 October)

The CPU-side Pi4 coordinate-cache probe now builds, reuses and restores tables
through NeonRebindSurface rather than calling private table procedures. The
existing public coordinate reset and arena reset remain covered. No private
runtime routine is exposed and no renderer implementation changed. This removes
two private-namespace failure keys: architecture117, provenance98 still refuse.

Its old standalone/fictitious ranges have been replaced by disjoint payload RAM.
The rejected 1 MiB stride uses eight rows in an actual8MiB declared descriptor
span, so the rollback test no longer pretends1.25GiB is mapped across kernel
reservations. The fixture seeds CPU descriptors; it does not initialize the GPU,
change its MMU, touch a framebuffer or submit work. This is not GPU qualification.

Physical Anvil361 capture461 returns0/1.74hostseconds. An independent rational
binary32 oracle matches all56475 coordinate words and all655360 report bytes,
including guards, unused padding, ten state records, three builds/four reuses,
logical rotation with a fixed physical key, oversized4097x8 recovery, unmapped
preflight refusal, post-begin stride refusal/complete descriptor rollback and
arena cache invalidation.385 planted report corruptions/truncations refuse.
The CPU-tier return screenshot was inspected. Cores/Vulkan/Lato/timeouts0 remain
healthy, deadmanoff, leaseFREE; no firmware/reset/storage/Bluetooth operation.

The official v1.4.350 registry URL was rechecked online and the existing local
copy again matches the pinned SHA above. This does not claim a new registry audit.
Source publication and the full Neon/Anvil Vulkan implementation remain open.


## Procedural rope asset qualification (27 October)

Shared NeonSpriteCreateRope and NeonServiceSpriteCreateRope now implement the
desktop engine's32x64 rope composition with explicit caller storage and existing
resident sprite ownership. No device, allocator or renderer dependency is added
to the generator, and no service ABI/resident firmware changes are required.
See NEON_RETAINED_UI.md for buffer/rounding/refusal/ownership contracts; the
defined integer source-over rounding is not a platform image-library bit-parity
claim. Existing BMP/PNG loaders are unchanged.

Final physical Anvil361 capture463 passes76 assertions,16384 exact RGBA bytes,
2048 mask bytes, all output guards/padding and98304 native pixels across normal,
scaled and cropped copies. CPU buffers are erased after upload and a refused
replacement leaves the old handle drawable.125 damaged reports/images refuse.
UnoQ compiles only. The image was inspected; whole-fixture1.5hostseconds is not
FPS/headroom. Historical462 was correctly refused for undersized test guard
arrays; those counts alone were repaired before463, with all expectations kept.
All postchecks healthy, no firmware/reset/storage/audio. Broader Neon, Vulkan
and mandatory source-publication closure remain unfinished.


Measured UTF8 fitting qualification

The new shared measured-text helper supplies bounded UTF8 fitting with explicit
caller scratch, transactional output and caller-selected ellipsis/dots. It uses
existing scalar/combining/selector/joiner boundary rules and the actual prepared
font width callback. Font glyph availability policy remains the application's
responsibility; full grapheme shaping is not claimed. See NEON_RETAINED_UI.md for
API, capacities, errors and callback contracts. Existing widget fitters remain.

Anvil361 capture464 passes95 assertions/64 cases plus an independent native-font
enumeration of39 prefixes. Fitted/reference text matches35840 pixels exactly;
683 damaged reports/images refuse. The image was inspected; UnoQ compiles only.
Initial recursion-test compilation refused before upload; legal nonrecursive
binding checks replaced it without weakening compiler policy. All postchecks
healthy/no firmware/reset/storage/audio. Full Neon/Anvil Vulkan remains open.


Unicode uppercase title preparation

Shared NeonTextUpperBytes/NeonTextUpper now provide locale-independent Unicode17
default full uppercase with explicit caller storage and transactional output.
This is a prerequisite for the panel title behavior, not the completed panel.
All1580 changed mappings are pinned to official UnicodeData/SpecialCasing;1525
also cross-check host Unicode15.1. Unicode-3.0 data notice/license and the new
source inventory are retained; no existing classification or policy changed.
No OS-specific UCase parity, locale tailoring, normalization or font fallback
claim is made. See NEON_RETAINED_UI.md for capacities/errors/ownership.

Anvil361 capture466 passes67 checks/14cases and13735 exact output bytes. Converted
and reference labels match35840 pixels exactly;236 damaged proofs refuse. UnoQ
compiles only. Capture467 also passes the unchanged95-check fitting regression,
whose complete PMF bytes remain identical with the extended UTF8 header. Images
were inspected. Historical465 refused an incorrect padded-label length in its
fixture; only encoded length constants changed before466. All postchecks healthy,
no firmware/reset/storage/audio. Full Neon/Vulkan and source publication remain open.


Prepared panel composition

The new shared prepared panel and resident service adapter now implement the
desktop body/header/accent/divider/uppercase-title/four-border composition.
Titles are copied and prepared before Draw; cached geometry/accent updates do
not reprepare glyphs. Shared palette revisions drive redraw. Caller clip, frame
and input ownership remain intact. Untitled and zero-header cases preserve the
original nondegenerate drawing behavior. See NEON_RETAINED_UI.md for caller
storage, Unicode policy, coordinates, errors, callbacks and lifetime contracts.

Anvil361 capture468 passes131 assertions,30 complete ordered callback records,
title guards and358400 native/reference pixels with zero channel difference.
Default/custom themes and caller scissor retention are covered; allthree title
windows contain visible text.1681 damaged reports/images refuse. The image was
inspected; UnoQ compiles only. This is panel qualification, not full engine/input/
font-policy/Vulkan completion or an FPS/headroom claim. All postchecks healthy;
no firmware/reset/storage/audio. Mandatory source-publication gates still apply.


Scalar caret column mapping

Shared UTF8 column-to-x and x-to-nearest-column helpers now use prepared renderer
prefix metrics, with explicit matching fixed-cell advance when selected. Columns
count Unicode scalars; supplementary characters count once. Midpoint ties choose
the later edge. Caller scratch/result storage is explicit; every refusal preserves
the result. Metrics and UTF8/span/range/alias errors refuse. Measurements stay
outside Draw, with no allocation, glyph preparation or frame ownership. This does
not add grapheme shaping, bidi, multiline policy or migrate existing widget code.

Anvil361 capture469 passes150assertions/91cases plus14 pointer/range refusals.
Independent literal native prefixes check12boundaries/11midpoints; four carets
and text match44800pixels exactly/max0, with visible text/caret probes.1058 damaged
reports/images refuse. Image inspected; UnoQcompile-only. Wholefixture1.4hostseconds
is not FPS/headroom. Postchecks healthy/no firmware/reset/storage/audio. Full Neon/
Vulkan and mandatory source publication remain unfinished. See NEON_RETAINED_UI.


Fixed TrueType layout prerequisite

Shared layout adds explicit Q16 fixed cells without pair positioning. UTF8,
CRLF, wrapping, alignment and original proportional behavior stay in one owner.
This is a prerequisite: Vulkan font references, cache/draw policy, snap and
controls remain open.

Physical original-owner470 and extended-owner471 agree on16 proportional cases.
48 fixed cases and5 refusals pass;1318 corruptions refuse. CPU layout only, no
glyph-rendering/FPS/headroom claim. Wholefixtures4.3/4.0hostseconds; UnoQcompile-
only. Postchecks healthy; no firmware/reset/storage/audio. Full Neon/Vulkan and
mandatory source publication remain unfinished.


Resident per-font fixed spacing

Installed Anvil362 adds optional graphics protocol1.5 fixed spacing. Registered
references carry their own Q16 advance; measurement and drawing pass it explicitly,
and short-run layout cache identity includes it. Legacy/default calls stay
proportional. Native source callers must rebuild for40-byte font references.
Pixel snap and control display remain open; direct native qualification follows below.

Capture472 passes92checks and161280 exact native/reference pixels across6
alternating proportional/fixed/fractional rows;114 corruptions refuse. A separate
comparison with Anvil361 capture469 matches35840 default pixels and exact width.
Image inspected; UnoQ service-client compile-only. The verified362 boot update
has a reloaded/hash-checked361 backup and one restart with90 quiet boot seconds.
All postchecks healthy. Wholefixture1.4hostseconds is not FPS/headroom evidence.
Full Neon/Anvil Vulkan and source publication remain unfinished.


Direct native fixed-font qualification

Capture475 on Anvil362 passes124checks and46080 exact GPU attachment pixels for
native setters/getter, proportional/fixed/fractional text, retained font spacing
and right/centre alignment. Zero in-frame raster/upload work and exact stale-owner
refusals pass.219 damaged reports/pixel buffers refuse. The montage was inspected.

This is a returning native Vulkan composition in payload-owned RAM, with an
independent positioned-glyph reference; it does not adopt a display target.
Historical473/474 fixture setup/count refusals are retained. Production code and
pixel expectations were unchanged. The retained pointer still submits one compact
fan outside the viewport, included in58draws/738vertices. Wholefixture7.9hostseconds
is not FPS/headroom. All postchecks healthy; no firmware/reset/storage/audio.
Pixel snap, visible controls, application acceptance, source publication and
broader Anvil Vulkan remain open.


Per-font pixel snapping on Anvil

Anvil363 adds optional resident protocol1.6/flag128/op35 and a pure
NeonServiceFontSetSnapToPixel client. Native fonts expose SetSnapToPixel and
SnapToPixel; the retained registry exposes its own setter. Exact0/1 only; idle
mutation only; default1 preserves existing Anvil snapping. Source references
are48bytes: rebuild native callers and query retained storage size.

Snap-off retains fractional Q16 ink origins through camera/canvas transforms.
Snap-on rounds each glyph before mapping. Text widths, layout and raster caches
stay valid; no in-frame preparation is introduced.476passes97direct checks/
46080exact attachment pixels and192corruption refusals, including actual retained
and right/centre drawing.478passes82resident checks/46080exact native pixels;
88damaged reports refuse. Shared client compiles for UnoQ; physical GPU tests
are Pi4 only.477's deliberate Close restored the console before capture, so its
image check refused despite passing API checks; exact original evidence remains.

363raw6004264B SHA8eb4ac7bba9878b4059e048ad529ad791b4a167c81463e147ebecd7ddff6575c;
code00200000..007B9E27/BSS0D000000..0EE4760F. Verified362backup/candidate/boot
readback, one authorized reset and90quiet boot seconds precede live postchecks.
Visible controls, full application acceptance, publication and broader Vulkan
remain unfinished. No FPS/headroom/another-GPU claim.

Default regression capture479 on363 additionally passes124checks. All368672
fresh crop/guard bytes are identical to the old475 result, proving the historical
snapped default across proportional/fixed/fractional, retained and aligned text.
The current fixture uses48byte references. Cores/Vulkan/Lato healthy;DSItimeouts0,
deadmanoff/leaseFREE. The full Neon/Anvil Vulkan goal remains active.


Visible controls in Anvil fonts

Anvil364 adds optional protocol1.7/flag256/op36 and a pure resident font-controls
client. Native/retained fonts expose SetControlMode and SetShowControls. Legacy0
preserves existing CR/LF layout; hidden1 drops C0/DEL; visible2 draws one common
box per control, including CR/LF separately. Desktop-style ShowControls false/true
selects hidden/visible. Native references are now56bytes; rebuild source callers
and query retained storage size.

Width, preparation, layout cache and drawing share the same mode. A shared strict
decoder validates before writing; a bounded pure raster owns visible-box coverage.
The atlas admits controls before a frame. Pixel snapping remains independent.
480passes244checks/46080exact attachment pixels, including independent box
references and a completely empty hidden-control crop. In-frame raster/upload
deltas are0;339corruptions refuse.481passes78resident checks/46080native pixels;
84damaged reports refuse. Shared client compiles for UnoQ; physical GPU evidence
is Pi4 only. The actual montage and resident screenshot were inspected.

482's69layout cases produce the same65536report bytes as471.483's124native checks
produce the same368672crop/guard bytes as479. The installed364 image has a verified
363backup, candidate and boot readback; one authorized reset and90quiet boot
seconds precede live version/map/core/Vulkan checks. Final original font/cores/
Vulkan healthy, display timeouts0, deadmanoff. Full application/input acceptance,
remaining image paths/effects, publication and broader Vulkan remain unfinished.


Composed drive assets on Anvil

Anvil366 adds optional graphics protocol1.8/flag512/op37 for independent
references to one loaded font face. NeonServiceFontDerive(parent,role,pixels)
copies spacing/snap/control policies, then setters vary them independently.
No second face allocation is required; unloading the owning face invalidates
all references. Native references remain56bytes. Shared signed span checks
reject overflow before dereferencing; the original failing boundary is retained.

Native484 passes164checks/46080exact GPU attachment pixels,259corruptions refuse.
Composed485 reads an actual font and RGBA16 Adam7 PNG from board storage, erases
caller buffers and runs90frames of menus/tabs/editor/list/retained controls,
sprites/particles/lines.65checks,5148PNGpixels(tolerance1),14400exact font-policy
pixels;99corruptions refuse. Cleanup retires the owning face and derived refs.
Screenshots inspected. UnoQ compiles only; physical execution is Pi4.

Measured29.932FPS,25.724ms mean work,40.072ms worst;89of90frames meet33.333ms.
The late menu-opening frame spends34.207ms in submit/present, not preparation.
Strict30FPS worst-case is not met; further present-stage diagnosis remains.
Input is scripted with real polling and no physical contacts. Native-input
acceptance and the full engine/Vulkan completion are not claimed.

366raw6014504B SHA945510a517cda8f8852c5463ac2f97ac530bd567762f529d3a16d68509e4e137.
Verified365backup/candidate/boot,one reset,90quiet boot seconds,live version/map.
Final cores/original font/Vulkan healthy,timeouts0,deadmanoff. The host tool
allows one fresh read-only pre-boot status recovery; mutations never replay.


Resident frame-end timing and DMA visibility

Anvil 368 extends vkstat with the latest resident application's End count,
failures, aggregate stage ticks and worst End call. It separates submission/
completion, DMA, extra cleaning, display publication and other overhead.
Counts reset on Open and survive Close; no payload or graphics ABI changes.

The DMA helper already completes destination maintenance and a visibility
barrier. The following duplicate whole-frame clean is removed from the DMA
application/console presentation paths. DMA maintenance, CPU-rendered flushing
and display ownership/error handling remain. The duplicate cost about 2.155 ms
per frame; display-wait phase also affects the observed total reduction.

Capture 487 on 368 passes all 65 checks in the same 90-frame composed asset
application. Every frame meets 33.333 ms: mean work 23.343 ms, worst 24.763 ms,
measured 30.0003 FPS. All 1,024,000 final pixels match the instrumented baseline.
Raw stage sums and the independent application timer agree. The restored
Vulkan console was separately captured and inspected. This proves the measured
Pi4 DSI fixture, not HDMI actuation or a universal performance guarantee.

The 368 boot file/candidate and 367 backup were reloaded and SHA-verified
before one reset and 90 quiet boot seconds. Final cores/font/Vulkan healthy,
display timeouts zero and deadman off. Physical input and full engine/Vulkan
completion remain open, as do mandatory source publication gates.


Earlier input broker qualification (Anvil 368)

Portable input is CPU-qualified but not yet a resident endpoint. Anvil 368/
service-table ABI1.8 remain installed. A shared48-byte event carries typed
text, named navigation, pointer/wheel/cancellation and separate physical-key
edges for games. The existing normalized vocabulary has one owner; its
original numbers, CRLF handling and Ctrl+C behavior are preserved.

Payload focus owns the original typed queue plus a bounded device lane.
Ready lanes alternate. Focus/screen changes and overflow cancel before fresh
input, preventing stale clicks or keys from crossing into another screen.
Failed service cleanup retains ownership and blocks reuse until recovery.

The final controlled-producer CPU test passes267checks on Pi4;541damaged
reports/truncations refuse. Wrapped FIFO order, releases, modifiers, focus
handoffs, overflow and legacy bytes are covered. UnoQ compiles only. No
physical input or resident integration is claimed: driver producers, payload
client, lifetime hooks and application adapter remain to wire. No monitor
update/reset was performed; cores/font/Vulkan remain healthy, deadman off.


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

## Public console font metrics - 28 October 2026

The console now calls `AnvilTrueTypeScaleMetric(value, pixels, unitsPerEm,
resultOut)` instead of reaching into the layout implementation. On Anvil's
64-bit targets this converts signed 32-bit font units to signed 16.16 pixels,
truncating toward zero. Accepted pixel sizes are 1 through 512 and units per em
are 1 through 65535. The caller owns an aligned, writable eight-byte destination.
The function returns 1 on success; invalid scalar arguments or a null, negative,
or misaligned destination return 0 without writing output. It does not select
a face or modify layout state. It cannot validate arbitrary caller memory ownership.

The glyph cache propagates conversion failure. Pair adjustment failure retains
the measured advance and increments the existing error counter. Public API
limits keep intermediate multiplication within signed 64-bit arithmetic.

Physical Pi 4 tests passed 51 signed arithmetic/refusal cases and 38 console
consumer cases covering cache reuse, slot/generation/size invalidation, no-match
pair values, malformed adjustment fallback and failed cache rebuild recovery.
The latter uses exact production consumers with a controlled font-provider test
double; it does not claim font-parser coverage. The portable arithmetic proof
also compiles for UnoQ (not a physical UnoQ execution claim).

Installed Anvil 386 passed verified boot/live hashes and the resident preserved
render-target regression, with healthy network, fonts, cores and Vulkan after
return. Forum 1500 tracks this specific architecture correction. Broader Neon
and Vulkan completion and the remaining architecture publication gate are open.
## Shared incremental font ownership - 28 October 2026

AnvilFontFileBegin(slot, path, pathBytes, maxBytes) starts a bounded load into an
empty, unselected slot and returns a positive request token, or zero on refusal.
The shared owner copies the caller's path and tracks buffer, progress and slot
generation. AnvilFontFileStep(slot, token, maxChunk) reads at most one chunk of
1..4096 bytes, closes the file, and returns 1 pending, 2 committed or 0 failed.
The final step validates the font and can take longer than an ordinary read.
AnvilFontFileCancel cancels only a matching pending token; it unloads no face.

Stale tokens and invalid chunk limits leave the active request intact. Storage,
short-read, changed-size and parser failures cancel it. The selected face is not
overwritten. The source file must remain stable during the request; size checks
are not a filesystem snapshot guarantee. Memory and synchronous loaders refuse
a slot reserved by an incremental request. The synchronous loader retains its
single-open read loop. Pi 3 startup now calls this interface and retains policy
for font selection, defaults and settings after commitment.

The optional embedded-face initializer is a separate shared composition module,
font_boot_embedded.pbi. Pi 4 includes it with its image font; file-only targets
can include the common font owner without requiring image-font symbols.

Tests passed 55 controlled storage/slot cases on physical Pi 4 and another 26
checks using the actual parser, embedded font bytes and a memory-backed storage
provider. The latter checks exact copying, parser metrics, and preservation of
the selected face after rejecting corrupt data; it does not test a storage device.
Complete Pi 3 build 46 and Pi 4 build 387 compile successfully. Pi 3 execution is
not claimed. Forum topics 1502 and 1503 track these two corrections.
Installed Anvil 387 has matching verified boot/live hashes and a verified 386
backup. Its resident target/text regression passes with healthy fonts, cores,
network and Vulkan on return. Topics 1502 and 1503 are resolved within those
scopes. Architecture still refuses 102 findings; provenance passes 1,401 checks.


## 28 October 2026: subtraction and fragment register scheduling

Returning candidates on installed Anvil 388 now qualify binary32 FSub in
the retained SPIR-V/typed IR path and V3D 4.2 emission. Capture 39 validates
scalar and vec2/vec3/vec4 live subtraction, retained ownership after source
overwrite, type/order/dominance refusals and independently decoded FSUB
operands. All 142 corrupted report/code/uniform controls reject. Capture 40
executes subtraction in both vertex coordinates and fragment colours: all
45 filtering, 142 idle-scope, 164 target-pool and 297 scripted UI checks,
24,511 parent pixels and the exact scanout comparison pass. Cores, fonts and
Vulkan restore, zero display timeouts and watchdog off. The original host
decoder-contract and after-Return expectation corrections are retained.

This work exposed and corrected unconditional four-way fragment scheduling
for programs using more than RF0..31. Register usage is now published with
the compiled program, selecting two-way mode when RF32..63 are required;
shorter programs retain four-way mode. Separate capture 38 verifies metadata
at 28/32/36/64 registers and a transactional refusal beyond 64 registers.
That boundary proof runs the lowerer on the CPU, not each shader on the GPU.

The original CRT effect still needs extended operations, computed texture
coordinates and conditional behavior. This is not full shader or Vulkan
conformance. Shared parser/IR semantics are target-neutral; physical GPU
qualification covers V3D 4.2. Installed monitor 388 is unchanged, and source
publication still requires resolution of the architecture gate findings.

### Computed sampling coordinates — 28 October 2026

The typed SPIR-V path accepts ordered binary32 vec2 coordinate values, including
arithmetic, reconstruction and constants. Legacy direct-input summaries remain
available only for direct loads; computed graphs retain typed dependencies.
Scalar, vec3, undefined and self-dependent coordinates refuse. The V3D texture
configuration is emitted immediately before the sample request, after any UBO
load used to compute its coordinates. Emitting that configuration in the shader
prologue let an earlier memory request consume it; the first GPU draw failed.

Physical Anvil388 capture44 validates uniform offsets +0.5, -0.5 and zero against
six independently expected red/blue texels, plus 25 API checks and the existing
filter/idle/target/UI and scanout oracles. The initial captures41/43 failed safely
and are retained. CPU captures42 and45 separately proves four coordinate forms through
retained records, typed verification and decoded instructions. These are candidate
payloads; installed388 is unchanged. Full CRT and general Vulkan remain incomplete.


### Fragment dot product — 28 October 2026

OpDot retains two ordered, identically typed binary32 vec2/vec3/vec4 operands
and a scalar result of their component type. The typed verifier rejects shape,
result-type and dominance errors. V3D fragment emission multiplies each lane,
then adds products in lane order without fused contraction. The bounded vertex
position planner does not yet support dot products.

Physical CPU capture47 validates all three widths, a negative case, source
retention after caller-memory destruction, invalid modules and typed mutations.
The decoder checks multiplication operands/destinations, exact FADD encoding and
accumulation order. All105 damaged report/instruction/uniform controls reject.
The first candidate refused vec4 because five registers were requested through
a four-component allocator; products and accumulator now allocate separately.

GPU capture49 validates dot((x,0.5),(0.5,0.25)) for x=+0.5/-0.5, and zero input,
producing coordinate shifts +0.375/-0.125/0.0. Fifteen texel probes distinguish
missing terms and wrong scale from the correct result. Existing filter, target,
idle-scope and scripted UI oracles remain passing. CPU capture47 covers emitted
instructions for all widths; numerical GPU coverage here is vec2. Both are
returning candidates on unchanged Anvil388. Full CRT remains incomplete.

Semantics: https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#OpDot


### Fragment vector scaling — 28 October 2026

OpVectorTimesScalar is retained as a distinct typed operation: its binary32
vec2/vec3/vec4 result matches its vector operand, and the multiplier is the
same scalar component type. The V3D fragment lowerer multiplies each selected
vector register by the one scalar register. Existing componentwise arithmetic
keeps its own lane selection. The bounded vertex-position planner remains
unchanged and does not claim this new operation.

Physical CPU capture50 validates all widths with alternating vector components,
a negative-value case, retained ownership after destroying caller words,
malformed modules and typed operand/dominance mutations. An independent decoder
checks each multiplication's operands, destination, scalar broadcast and uniform
words;131 damaged report/instruction/uniform controls reject.

Physical GPU capture51 composes scaling with dot product and texture sampling:
dot(2*(x,0.5),(0.5,0.25)) produces +0.75/-0.25 for x=+0.5/-0.5;
zero input produces zero. Fifteen expected texels detect omitted scaling and
incorrect lane use. Existing filter, idle, target, UI and full scanout comparisons
pass. CPU/emitted instruction coverage includes all widths; numerical GPU coverage
is vec2. Installed Anvil388 is unchanged. Full CRT remains incomplete.


### Composed CRT curvature — 28 October 2026

The original radial coordinate equation is composed from the shared typed
arithmetic path, including the original 0.015 strength. A zero coefficient and
negative coefficient provide controls; the production Chrome source is unchanged.
The generated fragment uses centered UV, dot(uv,uv), two vector scalings, the
radial addition, and conversion back to texture coordinates before sampling.

Physical Pi4 capture52 returned zero in14.0s on unchanged Anvil388. A64-column
striped texture rendered to256x256 gives18 independently predicted texels at
six positions for +0.015,-0.015,0. The sameX at differentY distinguishes both
squared terms of the radial expression. All25APIchecks and existing filter,
idle,target,UI,parentpixel and fullscanout oracles pass. All71changed API/pixel
records refuse. This proves coordinate curvature, not scanlines, vignette,
outside-bounds black output or the completeCRT effect.

The original vignette uses reversed smoothstep edges(0.8,0.3), which the GLSL
extended-instruction specification leaves undefined/poison. Its intended
center-bright, edge-dark transition will be expressed with ordered edges as
1-smoothstep(0.3,0.8,distance), preserving the cubic interpolation and thresholds.
That path is not yet implemented or qualified.
See https://registry.khronos.org/SPIR-V/specs/unified1/GLSL.std.450.html .


### Sine numerical GPU qualification (28 October 2026)

Physical Pi 4 capture 55 on Anvil 388 returned zero in 14.1 seconds. The typed
fragment path evaluates a mixed vec4 of radians, with independently predicted
RGB output on a mid-gray texture. Eighteen channel samples include zero,
positive/negative extrema, pi boundaries, multiple periods, +/-800 radians,
and nearby extrema. The maximum error against the reference was 0.418 of an
8-bit channel step (allowed one step). This is sampled UNORM output evidence,
not exhaustive binary32 accuracy. All 40 API calls, 45 filter, 142 idle-scope,
164 target, scripted UI, 24511 parent pixels and full scanout comparisons pass.
All 67 damaged GPU report controls reject. The existing rendering is preserved
when the sine input is zero. CPU capture 54 covers all scalar/vector widths.

The original time-dependent scanline expression is not yet composed and the
complete CRT port remains unfinished. Forum 1513 remains open for that work;
installed Anvil 388 is unchanged. Publication still requires architecture-gate
corrections. No vertex-position Sin support is claimed.


### Original scanline composition qualified

Capture 56 on physical Pi 4, Anvil 388, returned zero in 14.1 seconds.
The shader evaluates `sin(uv.y*800-time*10)*.04` and subtracts that scalar
from RGB only. Six normalized image rows at times 0, 0.125 and 12.5 seconds
produce all eighteen expected pixels; alpha remains 255. Maximum channel
error is 0.376 of an 8-bit step. All 25 API calls and baseline filtering,
target, idle, UI and scanout comparisons pass. All 100 damaged report controls
reject. The source image uses its own normalized coordinates rather than an
atlas rectangle. Baseline rendering sets the effect enable to zero.

This closes the missing fragment sine prerequisite (forum 1513). Curvature
and scanlines are qualified separately; the combined CRT pipeline, vignette
and outside-black conditional still require implementation and verification.
Installed monitor unchanged. Source publication remains blocked by the
architecture gate; vertex-position Sin is not claimed.


### Curvature and scanlines composed

Pi 4 capture 57 on Anvil 388 returned zero in 14.2 seconds. The original .015
radial warp feeds both texture coordinates and the vertical coordinate of
`sin(uv.y*800-time*10)*.04`. Alternating gray source columns distinguish warped
sampling from unchanged sampling; six points at three times distinguish the
warped scanline phase. All eighteen pixels match within one UNORM step
(maximum error 0.547), with alpha preserved. All 25 API calls and baseline
filter/target/idle/UI/scanout checks pass; 100 corrupted report controls reject.
The graph fits the existing register/code bounds without bypasses or ID-based
special cases. The production Chrome shader is unchanged. Vignette and
outside-black behavior remain absent; this is not the complete CRT port.


### Fragment Distance qualified on Pi 4

GLSL.std.450 Distance (67) retains two matching binary32 scalar or vector
operands and a scalar component result. Import identity, type, arity and
dominance checks precede lowering. The fragment backend subtracts components,
squares and sums them, then computes reciprocal of reciprocal square root,
with explicit SFU dependency spacing. The vertex planner is unchanged.

CPU capture 58 on Anvil 388 covers scalar through vec4, eight malformed calls,
retained semantics and emitted register/uniform operands. GPU capture 59
returned zero in 14.0 seconds: six vectors include zero distance, signs and
changes confined to the last two components. Eighteen RGB channel observations
match independent Euclidean-distance predictions within one UNORM step;
maximum error is 0.380 step and alpha stays 255. All 40 API results and existing
filter, target, idle, UI, parent-pixel and scanout comparisons pass. There are
149 rejected CPU and 67 rejected GPU report corruption controls.

This is sampled display-output evidence, not exhaustive binary32 accuracy.
Cores, fonts and Vulkan returned healthy, timeouts zero and watchdog off.
Installed Anvil 388 is unchanged. SmoothStep, the complete vignette and
outside-black behavior remain; the overall Neon work is still open. Source
publication remains subject to the architecture gate.


### Fragment SmoothStep qualified on Pi 4

GLSL.std.450 SmoothStep (49) now retains edge0, edge1 and x, verifies matching
binary32 scalar/vector types, and lowers the clamped cubic interpolation per
component. The vertex planner is unchanged. Ordered edges are required for
defined results; the intended Neon fade will use one minus SmoothStep(.3,.8,x).

CPU capture 61 on Anvil 388 covers scalar through vec4, eight malformed calls,
typed arity/dominance refusals and decoded instructions. The first fixture
(capture 60) did not consume results for widths below four; dead-code removal
correctly skipped those operations. The corrected fixture consumes each result.
Its initial host check also assumed sequential constant-register placement and
separate FMin/FMax decode names; the recorded bytes passed after these checking
assumptions were corrected, without changing or rerunning the payload.
All 235 corrupted CPU report/register/uniform controls reject.

GPU capture 62 returned zero in 14.2 seconds. Six mixed input vectors exercise
both endpoints, outside values and interior interpolation. All eighteen RGB
channels agree with independent predictions within one UNORM step (maximum
error 0.440); alpha remains 255. All 40 API results and existing filtering,
target, idle, UI, parent-pixel and full scanout checks pass. All 67 damaged GPU
report controls reject. This is sampled numeric output, not exhaustive binary32
verification. Cores/fonts/Vulkan returned healthy, timeouts zero and watchdog
off. Installed Anvil 388 is unchanged. The complete vignette composition and
outside-black behavior remain; source publication awaits architecture checks.


### Fragment register reuse candidate — rendering regression remains

The full curvature/scanline/vignette graph exhausted the monotonic allocator
at Distance result 76 (Pi capture 63, range error -23405 at allocation stage4).
A general free-register allocator now reclaims dead values and scratch at SSA
operation boundaries, protects future operands and aliases, keeps constants
and deferred output, and reserves fixed resource registers. CPU capture65
passes25 focused alias/lifetime/exhaustion checks;53 damaged controls reject.
The graph passes pipeline creation with the candidate, but capture64 fails
cross-target image checks55/57: expected red/green both read opaque black.
This candidate is NOT qualified; the composed vignette and forum1516 remain
open. No hardware bound increase, source-ID exception or monitor installation.
All runs returned healthy on Anvil388, timeouts0 and watchdog off.


### Fragment reuse and composed vignette qualified

Capture66 traced the black output to Dot writing first+lanes rather than its
allocated accumulator, overwriting cached constant1.0 in RF21. Dot now uses
the returned register. Reclamation also retains cached input maps for later
loads, avoiding another varying FIFO read. CPU69 passes36 lifetime, alias,
input-cache, noncontiguous-accumulator and refusal checks;78 damaged controls
reject. GPU70 returns zero13.2s with all18 composed curvature/scanline/vignette
pixels matching within1UNORMstep (maxerror0.486),25API calls and the existing
filter/target/idle/UI/parent-pixel/scanout checks passing.125 damaged GPU
controls reject. Captured code944bytes,24uniformwords,39registers; Dot uses
RF24 while cachedRF21 survives. The trace check rejects the broken capture66.
No hardware limit change or shader-ID exception. Earlier candidate warnings
above are superseded by this qualification. Installed388 unchanged and healthy;
timeouts0, watchdog off. Outside-black behavior and full engine integration
remain; source publication still awaits architecture checks.


### Boolean IR validation — 29 October 2026

The target-neutral IR now represents logical scalar/vector types, true/false
constants, ordered binary32 less/greater comparisons, logical OR and selection
of represented scalar/vector float32, int32 and Boolean values. The verifier
checks exact operand types, result/condition shape, dominance, constant encoding,
and the pre-1.4 per-component selection restriction.

Physical Pi 4 CPU capture 72 passes 68 positive/refusal checks across widths
1–4; this validates the shared verifier, not GPU comparison execution. The
SPIR-V parser and V3D lowerer still refuse these operations pending integration.
The outside-border regression (capture 71) therefore remains failing: 12 corner
samples are gray instead of opaque black, while all six interior samples pass.
Neither result establishes complete Neon application integration.


### Boolean SPIR-V retention — 29 October 2026

The typed parser path now validates and retains Boolean types/constants,
ordered float less/greater comparisons, logical OR, and scalar/vector selection.
The adapter maps each operation and its original operand order into shared IR.
Physical CPU capture 73 passes 91 checks across widths 1–4, including malformed
arity, types, IDs, use after return, SPIR-V selection-version rules and copied
IR remaining valid after a failed parse. The legacy plan path still refuses
Boolean modules. GPU emission remains unimplemented; the outside-border
regression is still failing and the full Neon port remains incomplete.


### Boolean GPU emission and outside border qualified — 29 October 2026

The fragment lowerer emits ordered less/greater comparisons, logical OR and
integer-move selection. GPU capture 74 passes 18 RGB checks including signed
zero, both infinities and positive/negative quiet and signaling NaNs. Capture
76 passes 18 more channels at exact 0/1 bounds and adjacent values. Each report
checker rejects 29 damaged controls. This is sampled fragment verification;
vertex logical operations and arbitrary structured control flow remain outside
this qualification.

The composed curvature, scanline, vignette and opaque outside-border shader
passes GPU capture 75: all 12 outside samples are black and six interior samples
match within one UNORM step across three times. All 77 damaged controls reject.
The 1160-byte program uses 24 uniform words and 39 registers. Code slots expand
from 1 KiB to 2 KiB, coordinated with scratch arrays and shader-record offsets
inside the same 8 KiB pipeline allocation; hardware register limits are unchanged.
All three runs return normally with cores, fonts and Vulkan healthy, zero
display timeouts and watchdog off. Installed Anvil 388 remains unchanged.

The original outside-border regression now passes in the generated shader
fixture. Production Chrome and full Neon engine integration remain incomplete;
this does not close the overall application topic. Source publication remains
blocked by architecture findings.


### Optional public CRT draw path — 29 October 2026

`neon_vk_retro.pbi`, included after Chrome, supplies `NeonVkChromeRetroPrepare`
and `NeonVkChromeRetroDrawId`. Preparation creates a separate pipeline while
idle. A draw samples the complete image, uses its own push constants for time
and effect parameters, and restores the ordinary pipeline. Chrome teardown
owns the optional pipeline. Ordinary images keep the existing shader. The
standard and optional paths share pipeline construction.

Physical Pi 4 capture 80 passes all twelve outside-black samples and six
interior samples across three times, plus the existing filtering, target,
parent restoration and UI checks. The checker rejects 77 damaged controls.
The initial wrapper selected the older fixture (capture 77); after that was
corrected, captures 78/79 exposed an obsolete unread UBO declaration in the
new shader. Removing that declaration produced capture 80. These earlier
runs are failures, not qualification of the effect API. All returned with
healthy cores/fonts/Vulkan, zero display timeouts and watchdog off on unchanged
Anvil 388.

Canvas-level effect selection, warped input mapping, mixed timed effect draws
within one frame and complete engine presentation remain unqualified. This is
not completion of the Neon application port. Architecture findings continue
to block source publication.


### Mixed timed CRT and ordinary draws — 29 October 2026

Physical Pi 4 capture 81 records two 256x256 CRT draws at times 0 and .125,
then an ordinary striped image and a red box, all in one frame. Twelve CRT
samples pass the independent curvature/scanline/vignette/border oracle;
three ordinary pixels match exactly. This checks per-draw time snapshots
and restoration of the ordinary pipeline. All 18 API results and existing
filtering, target restoration and UI checks pass; 65 damaged controls reject.
The payload returns zero in 14.2 seconds with healthy cores/fonts/Vulkan,
zero display timeouts and watchdog off. Installed Anvil 388 is unchanged.
Canvas-level effect selection and curved input mapping remain incomplete.


### Canvas CRT composition and curved pointer coordinates — 29 October 2026

The optional `neon_vk_canvas_retro.pbi` interface prepares and draws a canvas
with the existing aspect-fit viewport and checks owner state, completed content,
target generation and sampled-image generation. It also exposes curved pointer
mapping. The shared `neon_canvas_retro.pbi` helper follows the shader's .015
radial mapping using bounded Q24 intermediates and returns Q16 canvas coordinates.
Letterbox and opaque-border points preserve the output and return outside.

Physical CPU capture 82 passes sixteen center, interior, border, letterbox and
maximum-8192-size cases against a separate continuous-coordinate oracle, within
1/1024 canvas pixel. The checker rejects 69 damaged controls. This qualifies the
shared arithmetic on these samples, not interactive clicks or every refusal path.

GPU capture 84 uses the public canvas preparation/draw interface at a 600x600
aspect-fit size inside an 800x600 target. All twelve outside and six interior
samples pass across three times, along with 29 API results and the surrounding
filter/target/UI checks; 77 damaged controls reject. Capture 83 correctly refused
the fixture's attempt to retarget during an active frame. The corrected fixture
selects its temporary target while idle and restores the parent afterward.
An earlier compile-only report layout overlapped one result slot with pixels;
that layout was corrected before upload and was never run.

Both successful proofs return on unchanged Anvil 388 with healthy cores/fonts/
Vulkan, zero display timeouts and watchdog off. Interactive curved hit-testing,
canvas-wrapper mapping refusals and full engine presentation remain. Source
publication remains blocked by architecture findings.


### CRT canvas state contract qualified — 29 October 2026

Physical Pi 4 capture 85 passes 24 checks for the public canvas CRT interface:
missing content and closed owners, mapping the center, preserving output for
letterbox points and stale images, null/misaligned/overlapping outputs, malformed
viewport state, drawing before preparation, preparation during an active frame,
and nonfinite time rejection. Stale-image cases deliberately perturb and restore
the fixture's generation field. Valid aspect-fit drawing still passes afterward.
The host checker rejects 51 altered trace header/result fields.

The initial host check incorrectly required unwritten trace padding to be zero.
Only the 24-byte header and 24 result pairs are owned by this fixture; the checker
now validates those fields exactly, with the initial failed check preserved.
The payload itself returned zero in 14.4 seconds. All normal rendering checks,
cores/fonts/Vulkan, zero display timeouts and watchdog-off checks passed on
unchanged Anvil 388. This does not prove interactive event integration: the
existing canvas event adapter still maps pointers without the CRT curve.


### Resident CRT integration in progress — 29 October 2026

The standalone curved canvas and its real text-field scene passed captures
86–92, including 297 widget/render/scanout checks. The latest shared service
source adds an optional minor-12 target CRT capability: idle preparation and
full aspect-fit target drawing during a window frame. Target tokens remain
context-owned. The client checks version, dependent target capability, phase,
and finite time; the provider checks request size, reserved fields and tokens.

Physical CPU capture 93 passes 17 client transport/version/phase assertions
against a synthetic provider; 19 damaged controls reject. This does not qualify
the resident GPU implementation. Installed Anvil 388 remains minor 11 and has
not been updated. Provider rendering, monitor build and installed-client proof
are still required before this extension is considered available.


### Installed resident CRT qualification - 29 October 2026

The minor-12 extension described above is now installed in Anvil 389. The
native dispatcher rejects bad context, request size, stale tokens, premature
preparation/drawing, reserved fields and nonfinite time; its valid result
matches the independently calculated curved/scanline/vignette image. The
installed pure client creates and fills an offscreen target, unbinds it,
prepares the CRT pipeline while idle, then draws it in a window frame.
The loader captures the result and retires the application graphics context.

Capture 95 returned zero in 1.3 seconds. Both physical runs finished with all
cores and fonts healthy, Vulkan active, zero display timeouts, and the watchdog
off. This establishes resident rendering, not physical input actuation or
completion of the whole Neon port. Evidence is retained in
`docs/evidence/resident-retro95-20261029`.


### Resident canvas capacity and editing - 29 October 2026

On Anvil 389, the 800x600 application canvas returned renderer capacity error
-21203 (captures 96 and 97), while the small resident target had passed. The
resident console, vertex buffer, persistent atlas resources, target attachment,
sampled copy and temporary staging could not fit the reserved 16 MiB heap.
Anvil 390 reserves 64 MiB at 0x10000000 through 0x13FFFFFF on Pi 4; the live
map proves it is disjoint from all other reservations. Other board maps keep
their existing allocations. Shared allocation and range checks are unchanged.

The byte-identical application payload now passes capture 98 in 1.6 seconds:
80 assertions, five frames, final text ABZ, one submission and no final focus.
The output checker verifies curved background and patch colors, black bars
and corners, and text ink. Cores, fonts and Vulkan remain healthy, with zero
display timeouts and the watchdog off. This fixes the demonstrated capacity
failure, not every possible combination of target allocations. Evidence:
`docs/evidence/resident-heap98-20261029`; forum topic 1517.


### Shared TLS handshake and DRBG ownership - 29 October 2026

The handshake implementation moved byte-for-byte to Anvil/Crypto. The DRBG
algorithm now has a shared owner; hardware auto-seeding stays in its Pi adapter.
All thirteen DRBG procedure bodies are unchanged. A hardware-auto-seeding,
reseeding and ClientHello composition produces an identical 52,996-byte PMF
before and after. A second composition compiles with only shared cryptographic
includes and supplied seed bytes. Neither is new runtime qualification.

Eleven downward-dependency findings are removed, with none added. The gate
still refuses publication with 85 remaining findings. Provenance passes 1,409
checks after classifying the retained standards citation. RFC test source
paths now read the shared owners; emulator checks were not run. Installed
Anvil 391 is unchanged. Evidence: docs/evidence/shared-handshake-20261029.


### Hardware entropy boundary qualified - 29 October 2026

DRBG automatic seeding is shared over HwEntropyAvailable/HwEntropyRead. The
board provider initializes, performs bounded warm-up and gathers hardware
entropy; shared code owns staging, seed validation, wiping and DRBG state.
The Pi provider preserves the existing already-initialized behavior and raw
failure status. No TLS-specific HAL exemption was added.

Capture 105 passes 47 failure/state/wipe checks and 96 independently calculated
HMAC-DRBG output bytes. Capture 106 passes nine checks against the real hardware
RNG. Both return zero in 1.4/1.3 seconds with healthy cores, fonts and Vulkan,
zero display timeouts and watchdog off. This does not qualify other-board
providers or end-to-end TLS interoperability. Installed Anvil 391 is unchanged.

The two TLS auto-seeding downward dependencies are removed. Publication remains
refused with 83 findings; provenance passes 1,411 checks after archiving. Prior
handshake source snapshots now use .txt suffixes so they remain evidence rather
than additional compiled-source inventory; their bytes/hashes are unchanged.
Evidence: docs/evidence/shared-entropy-20261029.


### Shared TCP and link-policy ownership - 29 October 2026

Anvil/Network now owns TCP and link selection/pumping. Both implementations
moved byte-for-byte behind compatibility includes. A composition using the
real protocol and policy with fixture hardware links connection setup, send,
input, poll, tick and close into the identical 92,128-byte PMF before and after.
This establishes relocation/compile equivalence, not new runtime qualification.
Nine fixture/source-reading tools now use the shared owners; syntax checks pass.

Nine downward-dependency findings are removed, while six existing duplicate
Pi 3/Arduino Q definitions are exposed. Those composition/fallback definitions
remain unresolved. The architecture gate refuses publication with 80 findings;
provenance passes 1,411 checks. No emulator or board test was run for this move.
Installed Anvil 391 is unchanged. Evidence: docs/evidence/shared-transport-20261029.


### Shared TCP service dispatch - 29 October 2026

The optional TCP input/scheduler boundary has one shared owner. Unregistered
services keep input unhandled and ticking idle. TcpInit installs the actual
engine after initialization; partial registration is rejected without changing
the active pair. Pi 3/Arduino Q include the dispatcher instead of separate stubs.
The protocol statements are unchanged apart from provider naming and binding.

Physical capture 107 passes 25 checks and 53 corrupted-report refusals, returning
zero in 1.4 seconds with healthy cores, fonts and Vulkan, zero display timeouts
and watchdog off. This qualifies the dispatch boundary, not TCP interoperability.
Canonical complete monitor builds pass: Pi 4 392, Pi 3 47, Arduino Q 99. None
of those new monitor images was booted; installed Pi 4 firmware remains 391.
Architecture remains refused with 78 findings; provenance passes 1,411 checks.
Evidence: docs/evidence/tcp-dispatch-20261029.


### Pi 3 shared link policy integration - 29 October 2026

The Pi 3 composition now uses the shared link policy. Address binding/loss
selects the preferred usable interface before rearming the console. The board's
LinkPin stub and three duplicate send/limit wrappers are removed; all hardware
provider executable lines are unchanged.

Physical Pi 4 capture 108 passes 32 software-integration checks through an exact
copy of the Pi 3 adapter with simulated radio I/O, including byte-exact staged
frame copying, interface/readiness refusal and address loss/rebinding. The
checker rejects 67 damaged fields. This is not Pi 3 radio qualification. The
return was zero in 1.4 seconds, with healthy cores, fonts and Vulkan, zero
display timeouts and watchdog off. Complete Pi 3 monitor build 48 passes but
was not booted. Installed Pi 4 firmware remains 391; candidate 392 is uninstalled.
Architecture publication remains refused with 74 findings; provenance passes
1,411 checks. Evidence: docs/evidence/pi3-shared-link-20261029.


### Pi 3 shared DHCP candidate - runtime qualification pending

The Pi 3 composition includes the existing shared DHCP server implementation
instead of four local stubs. It remains inactive by default, refuses the radio
server role, and has no start command in this composition. Shared protocol
code is unchanged. Complete Pi 3 monitor build 49 passes. Architecture still
refuses publication with 70 findings; provenance passes 1,411 checks.

The compiled 23-check inactive-service fixture has NOT run: Pi 4 readiness
received no console replies, and the PC had no resolved MAC for its recorded
address. No upload, boot or reset was attempted. The last confirmed healthy
checkpoint remains Anvil 391/capture 108. This candidate is not runtime-qualified.
Evidence: docs/evidence/pi3-shared-dhcp-candidate-20261029.


### Clear-value array acceptance - candidate, 29 October 2026

The shared recorder now accepts extra clear values for a single CLEAR
attachment. It consumes entry zero and still refuses a missing value or null
array. This follows VUID-VkRenderPassBeginInfo-clearValueCount-00902.
The public regression compiles and covers both refusals, reset/retry, two
distinct clear values and all 24,511 attachment pixels. Hardware execution
is pending; the host checker alone rejects 44 synthetic corruptions.
No firmware was installed. Forum 1483 post 4178 records the candidate and
its qualification limit. Evidence: docs/evidence/vulkan-clear-value-count-20261029.


### Clear-value acceptance verified - capture 109, 29 October 2026

The preceding candidate passes on physical Anvil 391 without a firmware
update. All 13 public checks pass: missing values and null arrays are refused,
reset/retry succeeds, and two distinct clear values yield the first value
across all 24,511 attachment pixels. The retained regression passes 48 native
load checks, 164 target checks and 297 scripted keyboard checks, including
an exact 4,096,000-byte scanout comparison. Forty-four corruptions of the
actual report are rejected. The payload returns zero in 12.1 seconds; cores,
fonts and Vulkan recover, display timeouts remain zero and watchdog is off.

Forum defect 1521 is fixed and closed; topic 1483 post 4180 links its evidence.
This qualifies the shared fix on Pi 4, not other-board execution, physical
input, complete Vulkan conformance or a published release. The architecture
gate still prevents source publication. Evidence:
`docs/evidence/vulkan-clear-value-count109-20261029`.


### Shared DHCP qualification completed - 29 October 2026

The previously pending Pi 3 composition check ran on physical Pi 4. Capture
110 exposed a shared DHCP start path accepting a wired interface absent from
the board. DhcpdStart now checks HwLinkHas before reserving an alias/listener.
Capture 111 passes the original 23 checks with the exact Pi 3 adapter and
simulated radio. Capture 112 passes 40 checks with controlled hardware
presence, including successful wired start/stop, cleanup and active-client
refusal. Host checkers reject 49 and 83 damaged reports respectively.
This is CPU integration evidence, not Pi 3 radio or wire-DHCP qualification.

Both corrected runs return zero in 1.3 seconds with healthy cores/fonts/Vulkan,
zero display timeouts and watchdog off. Complete Pi 3 build 50 and Pi 4 build
393 compile but were not installed; the Pi remains on 391. Defect 1522 is
fixed and closed, linked from topic 1483 post 4182. Architecture still reports
70 findings and refuses source publication; provenance passes 1,411 checks.
Evidence: `docs/evidence/dhcp-capability112-20261029`.


### Shared HTTP polling owner - 29 October 2026

One shared polling boundary replaces the duplicate Pi 3 no-op. An absent
service has no callback; the Pi 4 composition installs its HTTP monitor
callback during initialization. Registration opens no listener. Stop leaves
polling active to preserve transport retirement. The four existing monitor
procedure bodies remain unchanged apart from the internal poll name.

Physical Pi 4 capture 113 passes 30 dispatch/lifecycle checks with controlled
TCP and engine providers; 63 damaged reports are rejected. Host command
checks pass 52 cases. The payload returns zero in 1.3 seconds with healthy
cores, fonts and Vulkan, zero display timeouts and watchdog off. Complete
Pi 3 build 51 and Pi 4 build 394 compile but were not installed. This does
not qualify a new monitor boot or HTTP wire traffic. Architecture findings
fall from 70 to 69; publication remains refused and provenance passes 1,411
checks. Forum 1483 post 4183 records the scope. Evidence:
`docs/evidence/http-poll113-20261029`.


### Shared address callbacks - 29 October 2026

Address binding/loss now have a single shared owner. Both common callback
bodies moved unchanged; wired compatibility state has one shared owner too.
Pi 3 preferred-link selection now runs inside its existing address-notification
adapter, after updating its latch and before console rearming.

Capture 115 passes 23 checks with the exact Pi 3 adapter; capture 116 passes
50 checks with controlled wired-presence/MAC providers. They cover lease/DNS
metadata, saved and lost addresses, interface selection, console rearming,
wired-only compatibility fields, link-local replacement and matching DHCP
server-role shutdown. Checkers reject 49/103 damaged reports. Both return zero
in 1.3 seconds with healthy cores/fonts/Vulkan and watchdog off. These are
physical Pi 4 CPU tests with simulated network providers, not Pi 3 radio tests.

Failed capture 114 is retained: its fixture incorrectly requested a wired
lease through the Wi-Fi-only MAC provider. Complete Pi 3 build 52 and Pi 4
build 395 compile, neither installed. Architecture findings drop to 67,
provenance passes 1,411 checks, and source publication remains refused.
Forum 1483 post 4184 and `docs/evidence/net-address116-20261029` record the scope.


### CLEAR with a defined initial layout - 29 October 2026

The shared render-pass owner now accepts supported defined initial color layouts
for CLEAR. A defined layout becomes a submission precondition even though CLEAR
replaces the contents; UNDEFINED retains its discard behavior. LOAD still
requires a defined layout and its existing backend capability.

Capture 117 on unchanged Anvil 391 passes 43 checks for GENERAL and
TRANSFER_SRC_OPTIMAL: establish the layout, refuse a mismatched clear before
changing any pixels, reset, and clear successfully with the matching layout.
The four full-image comparisons cover 98,044 pixels. The retained native load,
target lifecycle and scripted keyboard regressions pass. The payload returns
zero in 12.2 seconds with healthy cores/fonts/Vulkan, zero display timeouts and
watchdog off. The checker rejects 134 damaged synthetic reports.

COLOR_ATTACHMENT_OPTIMAL entry is accepted by the shared source but is not
runtime-qualified by this case. No firmware replacement, other-board execution,
physical interaction or conformance is claimed. Forum 1523 is fixed and closed;
the wider topic 1483 remains open. Architecture still refuses publication with
67 findings; provenance passes 1,411 checks. Evidence:
`docs/evidence/vulkan-clear-initial-layout117-20261029`.


### Color attachment final layout and continuation - 29 October 2026

Shared render-pass creation now accepts COLOR_ATTACHMENT_OPTIMAL as a final
color layout. The existing queue owner commits the final layout after successful
completion; no synchronization or ownership checks were removed. The canvas
copy service retains its separate readback-layout requirements.

Physical capture 118 on unchanged 391 passes 76 checks. It extends the preceding
defined-entry tests to COLOR_ATTACHMENT_OPTIMAL, then follows a completed target
in that layout with a LOAD pass and verifies that every red pixel survives.
UNDEFINED and PREINITIALIZED final layouts still refuse with null handles.
The seven full-image comparisons cover 171,577 pixels. All retained native load,
target lifecycle and scripted keyboard checks pass. Return time is 12.4 seconds,
cores/fonts/Vulkan remain healthy, display timeouts are zero and watchdog is off.
The report checker rejects 233 synthetic corruptions.

This closes the preceding COLOR_ATTACHMENT_OPTIMAL entry qualification gap.
It proves serialized separate passes, not multiple subpasses, asynchronous
rendering, physical interaction, other-board execution or conformance. Forum
1524 is fixed and closed; main topic 1483 remains open. Architecture still has
67 publication-blocking findings; provenance passes 1,411 checks. Evidence:
`docs/evidence/vulkan-color-final-layout118-20261029`.
