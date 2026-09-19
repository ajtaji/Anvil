# Vulkan IDE-chrome acceptance — 2026-09-16

## Result

The bounded public Vulkan path needed to begin the Neon IDE-chrome adapter is
accepted on the Raspberry Pi 4. The final returning, RAM-only build-148 run:

- loaded the diagnostic at `0x500000` and returned exact
  `x0=0x00000000006C85A0` in 10.2 seconds;
- left report slot 128 at zero;
- advanced the TFU exactly once, submitted one V3D bin/render pair, and used
  one display-owner DMA presentation;
- passed all 211 independent source, report and pixel-oracle checks;
- produced fresh capture sequence 8, a 1280x800 PNG representing the rotated
  800x1280 target; and
- returned to the real build-148 prompt with the deadman explicitly off and no
  core leases.

The run did not flash, reset or write persistent storage.

## Exact artifacts

The evidence directory is:

`runs/vulkan-atlas-chrome-acceptance-20260916-r2/`

| Artifact | Exact identity |
|---|---|
| PMF container | 976,956 bytes; SHA-256 `485d21a7c1ddb11b87b36220f8e339bc4cd33eeff696b9577fc754841ee73e9a` |
| Returned report | `vulkan-atlas-chrome.report.bin`; 960 bytes; SHA-256 `d8344fe34b86dde9b4b56fae812d0a61a5514f92caa1fc9dba82d9ac94d43179` |
| Raw capture | `vulkan-atlas-chrome.bgra`; 4,096,000 bytes; the oracle reads it as the logical 800x1280 BGRA target |
| Displayable capture | `vulkan-atlas-chrome.png`; 1280x800; SHA-256 `f71f38f67389ba2edb41a662402797b93df510931092348ffaee343efa8b0e86` |
| Run ledger | `vulkan-atlas-chrome.json`; build, timing, transfer, return pointer and capture metadata |
| Console transcript | `vulkan-atlas-chrome.txt`; commands, transfer identity, return and capture stream |

The final V3D-list desk gate also passes 80 properties over 25,462,126
interpreted A64 instructions. The emitted cache-batch gate passes 38 exact
checks over 1,961 instructions, with all six hostile mutations red.

## Reproduce the desk and evidence checks

From the repository root, the canonical source build is:

```text
PureMetalForge.exe --compile RaspberryPi4/Examples/Diagnostics/vulkanAtlasChromeProof.pi4 -t pi4 --load-addr 0x500000 --stack-addr 0x4F00000 --entry-returns -o vulkanAtlasChromeProof.img
```

The checker has an entirely synthetic desk mode:

```text
python tools/vulkan_atlas_chrome_acceptance_check.py --self-test
```

The final board evidence is graded independently with:

```text
python tools/vulkan_atlas_chrome_acceptance_check.py --report runs/vulkan-atlas-chrome-acceptance-20260916-r2/vulkan-atlas-chrome.report.bin --screenshot runs/vulkan-atlas-chrome-acceptance-20260916-r2/vulkan-atlas-chrome.bgra
```

Both commands report 211 exact checks. The board run itself used the monitor's
bounded returning route: receive the PMF at `0x500000`, arm the 15-second
deadman, and execute `boot mem 500000 shot`. The transcript proves that the
payload returned, the deadman stopped, `x0` identified the report, and capture
sequence 8 was taken on return.

## What this accepts

The diagnostic renders through public Vulkan calls rather than a private V3D
shortcut. In one render pass it proves:

- an 8x8 optimal BGRA8 atlas copied through `vkCmdCopyBufferToImage` and the
  real TFU path;
- UV vertex attributes and combined-image-sampler descriptor use;
- the bounded mixed fragment graph `sample * push + UBO`;
- per-draw push tint and exact source-over blending;
- eight ordered six-vertex quads;
- eight public `vkCmdSetScissor` snapshots, including a final clip edge;
- overflow-safe clip normalization and transition-cached `CLIP_WINDOW` state;
- solid background and toolbar pixels, transparent and fully covered atlas
  texels, and covered texels on both sides of the clip edge;
- all coalesced cache-range maintenance in one merged cache transaction with
  one final barrier; and
- one V3D bin/render pair followed by one display-owner DMA presentation.

The corrected report's six exact colour probes agree with the corresponding
5x5 raw-capture regions. The surface guard is unchanged, the optimal image has
the exact 8x8 texture shape, no Vulkan/native fault status is present, and the
image finishes in `VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL`.

## Acceptance boundary

This is acceptance of the deliberately bounded Pi 4 implementation, not a
Vulkan conformance claim. It does not add or prove swapchains, WSI, dynamic
viewports, smaller render areas, multiple render targets, mip levels, array
layers, MSAA, general texture formats, general SPIR-V, asynchronous submission
or concurrent host access. Sample-mask suppression still has only desk proof.

The proof does not claim that the later existing-widget adapter has run on the
board. Its first porting prerequisite is complete: Neon now exposes a
font-generation-safe, borrowed read-only CPU RGBA8 atlas, copied glyph UV
records and one reserved opaque-white sample for Vulkan staging, without
exposing its private tiled atlas or doing TFU/V3D work during a CPU-only
ensure. This proof establishes that the public Vulkan substrate can express
and execute the required box, atlas-text, tint, blend and clip shapes without
processor pixel drawing or a private renderer bypass.

## Post-proof source delta

The read-only atlas prerequisite and renderer-neutral primitive hook refactor
the common Neon path after the board-proven image above. The exact current-tree
build is a 977,076-byte PMF with SHA-256
`c4b43f94547343ef2b01232a81a549f3444f66b4e29c3d90197a2b887fca147b`
and expected report pointer `0x6C85C8`. It compiles, its focused atlas gate and
the existing four-rotation display gate pass, but it has not been sent while a
different lane owns the shared Pi 4. The earlier board result is therefore not
claimed as proof of these new exact bytes; the same bounded returning run is
owed when the lease is free.

## Adapter state and next silicon step

The persistent Vulkan-backed Neon adapter is now desk-green. It:

1. creates the shared solid/atlas-text pipeline, descriptor sets, the atlas image and
   reusable vertex buffers once rather than rebuilding them every frame;
2. translates Neon boxes, atlas glyphs, fans, closed outlines, line lists and
   clip changes into ordered public Vulkan triangle-list draws;
3. updates only dynamic text/geometry/tint data while retaining valid resource
   ownership and submission lifetimes;
4. submits once, publishes one consumable presentation intent, and leaves the
   one display-DMA operation with the display owner.

The real-widget scene reuses the existing panel, menu, list and text procedures
unchanged and records 109 quads, 47 draws, 654 vertices and five scissor
states. The next proof is that exact scene plus the new primitive shapes on the
Pi 4 with a fresh screenshot, one bin/render pair, one display-DMA presentation
and a clean return. Resize, HDMI/DSI and rotation coverage follow that bounded
run.
