# Pi 4 Vulkan triangle strips — 2026-09-27

The Pi 4 Vulkan graphics-pipeline slice now accepts `TRIANGLE_STRIP` as well
as `TRIANGLE_LIST`, with primitive restart disabled. Pipeline creation records
the topology; whole-list backend preflight rejects an unknown mode before a
frame starts; array and indexed draws then emit the corresponding V3D 4.2
primitive packet. The supported indexed path retains its existing UINT16 and
UINT32 validation, bounds and cache handling. This does not add point, line,
fan or primitive-restart support.

Two returning RAM diagnostics use the public Vulkan calls and GPU-transformed
vertices to draw the same four-corner magenta square. The array diagnostic
uses `vkCmdDraw(..., 4)`. The indexed diagnostic binds a UINT16 buffer at byte
offset four, then draws four indices with `firstIndex = 1`. A triangle-list
packet would leave one half of the square empty. On the Pi 4 at
`192.168.1.111`, both payloads returned `x0=0` and produced pixel-identical
1280×800 screenshots: 367,393 fill-colour pixels and filled probes in both
halves. Capture numbers are 106 and 107. Both runs were RAM-only; the monitor
was not reset or flashed.

The production backend gate passed 142 property checks over 32,634,045
interpreted A64 instructions, including exact array/indexed primitive modes
and an atomic refusal for a hostile topology. The broad public pipeline gate
passed 813 checks over 204,184,757 instructions. Normal Pi 4 build 220
compiled at 4,366,564 bytes; its image SHA-256 is
`b1dc9bfeb8db6dfeb059fa5b227b3d9284c8910a8a3e32ed0c3bc99b38ac4168`.

The exact PMFBOOT payloads, screenshots, board metadata, compressed console
transcripts, build-220 image and a standalone pixel oracle are in
`docs/evidence/vulkan-triangle-strip-20260927/`. Run
`py docs/evidence/vulkan-triangle-strip-20260927/verify_capture.py` to repeat
the screenshot comparison with Python's standard library.

This proves the bounded Pi 4 V3D topology path; it is not a Vulkan 1.0
conformance claim. Primitive restart and other topologies remain unsupported.
