# Rotating Vulkan pyramid on Raspberry Pi 4

`RaspberryPi4/Examples/Diagnostics/vulkanPyramidDemo.pi4` is a returning RAM
payload. It rotates a square pyramid through 12 angles over one revolution.
Each frame updates five projected 3D points and back-to-front face order on
the CPU, then records one public Vulkan render pass with a 12-vertex triangle
draw. V3D fetches and shades the vertices and rasterizes the four coloured
faces. A guarded display DMA transfer presents the completed attachment on
each frame. The payload checks for V3D faults and verifies 12 completed draws
and 12 DMA presentations before returning zero.

The production Pi 4 backend currently accepts two-dimensional position and
colour attributes. The CPU projection is five points per frame; none of the
triangle pixels are drawn by a CPU fallback. GPU matrix transform and a depth
attachment need additional vertex-shader and pipeline support before this
demo can move its transform and visibility calculation to V3D.

The final PMFBOOT v2 container is
`docs/evidence/vulkan-pyramid-demo-20260927/vulkanPyramidDemo.img.pmf`.
It is 990,468 bytes with SHA-256
`3abca7dbdfdd5a87083eaf439f064c91865b92ad5313cff374413eb635c86d10`.
It loads at `$600000`, uses stack `$4F00000`, and returns to the resident
monitor. On build 210, the monitor verified the upload digest, ran the payload
for 10.1 seconds under a 15-second deadman, received `x0=0`, and saved fresh
capture 74. The capture shows the last GPU-rendered pyramid frame. The
resident Vulkan console was restored afterward, the deadman and capture were
disarmed, coretest leases were zero, and the board was released. No flash,
reset, or boot-medium write occurred.

The evidence directory includes the exact runnable container, capture,
board-run metadata, and compressed console transcript. The preceding two
prototype runs returned diagnostic reports: the first reset an initial
command buffer, and the second used a fence before creating it. Those setup
errors were corrected before the successful third run. The saved container
and capture are from the successful source only.

The production V3D backend gate passed 92 checks, including compilation of the
existing board diagnostics. The normal Pi 4 image compiled to 4,342,248
bytes, and its generated source stamp was restored.

The demo shares `vulkanTriangleProofBody.pbi` with the existing GPU triangle
diagnostics under a compile-time branch. The normal Pi 4 image contains no
demo frame loop. To run the saved payload again, acquire the Pi 4 board lease
and use `tools/board_run_leased.py` with `--addr 0x600000`, `--tier dma`, a
15-second deadman, and `--expect-x0 0`; the board tool takes a fresh capture.

## GPU perspective-scale follow-up

The vertex front end and V3D 4.2 vertex-pair lowerer now accept a bounded
`gl_Position = vec4(position.x * scale.x, position.y * scale.y, 0, 1)`
shape from two distinct `vec2` vertex inputs. The coordinate and vertex QPU
programs multiply those components before viewport conversion. The pyramid
places the unscaled rotated XY numerator and perspective scale in separate
attributes, so its final per-vertex projection multiply runs on V3D.
Rotation, reciprocal scale calculation, face ordering, and vertex-buffer
updates still run on the CPU. A general matrix transform, nonconstant clip Z/W,
and depth attachment remain future work.

The final-source RAM payload and capture are in
`docs/evidence/vulkan-pyramid-gpu-scale-20260927/`. The PMFBOOT v2 container is
998,880 bytes, SHA-256
`15ef01d3012a337a19cef5475fe59cc38351d3c1e9c7086ab36ae64d68af9387`.
On monitor build 210, the board verified the upload, returned `x0=0` after
10.1 seconds, and produced fresh capture 76. The V3D console was restored;
the deadman and capture were off and coretest leases were zero. No reset,
flash, or boot-medium write was made.
