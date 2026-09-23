# Vulkan-backed Neon chrome adapter — 2026-09-16

## What exists

`Anvil/Graphics/Vulkan/neon_vk_chrome.pi4` is the first resident adapter from
the existing Neon widget layer to the public Vulkan-compatible path. It does
not duplicate the menu, panel, list or text widgets. `neon.pi4` exposes one
`NeonDrawBackend` structure containing an all-or-none primitive family for
boxes, text, scissors, fans, outlines and line lists. The adapter installs that
structure only after every Vulkan resource is ready; passing null to
`NeonDrawBackendInstall` restores the native Neon family.

The application lifecycle is separate from `NeonFrameBegin` and
`NeonFrameEnd`. The Vulkan V3D backend already owns that hardware frame, so
entering the native Neon frame from the adapter would recurse into the same
owner.

## Public lifecycle

1. Initialize Neon's surface, palette and font.
2. Call `NvwaPrime()` when using the acceptance scene so the real immediate
   menu can settle its next-frame measurements without opening a V3D frame.
3. Create the Vulkan instance, device, render pass, attachment and framebuffer.
4. Call `NeonVkChromeCreate(...)` once. It creates the persistent command
   buffer, fence, dynamic-scissor pipeline, optimal atlas, sampler,
   descriptors, uniform buffer and coherent vertex buffer, then installs the
   primitive family.
5. For each frame call `NeonVkChromeBegin`, call the existing Neon widgets,
   then call `NeonVkChromeEnd`.
6. A successful End publishes one presentation intent. The display owner
   consumes it once and performs the one DMA presentation.
7. Call `NeonVkChromeDestroy()` before destroying the caller-owned Vulkan
   objects. It removes the hook family installed by this adapter and releases
   its persistent resources.

Create refuses a second owner. A partial primitive family is refused. Box,
whole-text-run, fan, outline and line-list capacity are preflighted before any
vertex write or ordered cursor movement, so a refusal cannot leave half a
primitive in reusable storage. Fans become triangle-list wedges; closed
outlines and line lists become deterministic one-pixel triangle quads. An
outline preserves the staged fan exactly so the native outline-then-fill call
order remains valid, while End closes and resets the builder after success or
error.

## Atlas and colours

The adapter copies Neon's borrowed linear RGBA8 atlas into its own optimal
sampled image. Glyph UV rectangles come only from
`Neon_AtlasRasterGlyphUV`. Solid boxes use the separate opaque-white rectangle
from `Neon_AtlasRasterWhiteUV`; no glyph cell is assumed to be spare. Neon
colours remain logical `0xAARRGGBB` and are converted to four binary32 push
values independently of the attachment's byte order.

## Real-widget desk proof

`RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAcceptanceScene.pbi` calls
the existing Neon panel, text, clipped-list and menu procedures. It never
calls the adapter's box/text/scissor primitives directly and never opens a
native Neon frame. Its settled frame is exact:

- 35 box calls and 12 text calls;
- 74 glyph quads, 109 total quads, 47 ordered draws and 654 vertices;
- two scissor sets, two clears and five snapshotted scissor states;
- one partially clipped list row and one fully rejected hidden row;
- one consumed present intent and one display-owner DMA call.

`python tools/neon_vk_chrome_acceptance_check.py` passes 267 production source
checks, 27 emitted contract assertions, 58 hook source checks, 44 emitted hook
assertions, 45 emitted assertions over the exact production geometry-lowering
procedures, five scene ownership checks and all eight hostile traces. The
geometry gate covers a convex fan, its closed outline, horizontal, vertical,
diagonal and zero-length lines, atomic overflow and safe builder reset.

The atlas contract independently passes 26 source checks and 41 emitted
assertions over 3,118,073 interpreted A64 instructions; five hostile mutations
are rejected.

## Boundary

This tranche is desk-proved, not silicon-proved. Another lane held the shared
Pi 4, so no adapter payload, screenshot, reset, flash or persistent write was
performed. The next bounded run must render this exact real-widget scene,
capture the screen, prove one bin/render pair and one display-DMA operation,
and return to the monitor with its deadman and leases clear.

Silicon proof of the new fan/outline/line shapes, resize,
HDMI/DSI/rotation coverage, broader font handling and WSI remain after that
run. This work does not claim Vulkan conformance.
