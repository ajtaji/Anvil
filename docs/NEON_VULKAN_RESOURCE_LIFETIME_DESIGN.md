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

# Future owning files

The exact implementation ownership is frozen as follows:

| File | Ownership |
| --- | --- |
| `Anvil/Graphics/Vulkan/neon_vk_chrome.pi4` | Neon operation lowering, resource orchestration, atlas/target generation publication, and present-record production |
| `Anvil/Graphics/Vulkan/neon_vk_resources.pi4` (proposed) | Focused resident resource lifetime, atlas retirement, attachment/framebuffer replacement, and recovery ledger if split from the adapter |
| `Anvil/Graphics/Vulkan/vk_wsi.pbi` | Target-neutral provider/image/present state and generation validation; shared changes require serialized integration |
| `RaspberryPi4/Board/screen_source.pi4` | HDMI/DSI display adoption, draw/scan ownership, DMA/CPU presentation, and present-record consumption |
| `Anvil/Graphics/Vulkan/neon_vk_display.pi4` (proposed) | Pi-specific bridge that translates a completed Vulkan record into the display-owner seam |
| `Anvil/Graphics/Vulkan/vk_foundation.pbi` | Shared Vulkan object/resource primitives; changes require serialized integration |
| `Anvil/Graphics/Vulkan/vk_pipeline.pbi` | Shared pipeline and dynamic viewport integration; changes require serialized integration |
| `Anvil/Graphics/Vulkan/vk_command.pbi` | Shared command recording/submission integration; changes require serialized integration |
| `Anvil/Graphics/Vulkan/vk_v3d_backend.pi4` | Shared V3D resource, cache, completion, and recovery seam; changes require serialized integration |

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
