# Neon sprite rotation and camera mapping on Pi 4

On 2026-10-02, a returning RAM payload on Raspberry Pi 4 Anvil build 242
rendered three transformed RGBA sprites through `NeonVkChrome` and the V3D
Vulkan backend. The second frame checked a clockwise quarter-turn about the
sprite center, camera translation with 2× zoom, and an ignored-camera draw.
Its asymmetrical 2×2 source had opaque red, half-alpha green, transparent blue
and opaque white texels. Eleven BGRA probes matched their exact expected
values, including cleared areas. A deliberately extreme X coordinate was
refused before fixed-point multiplication and did not add a draw. The first
frame repeated the earlier crop/scale/tint checks as a regression guard.

The final 1,309,236-byte `.pmf` container had SHA-256
`05dad50391751108c13256bd39e3654b4508baf208c369a9cf6b7fb7ea590d38`.
The board verified the transfer digest, ran it from `$700000`, and returned
report pointer `$00D882C8` in 4.1 seconds under a 15-second deadman. The
128-byte report recorded status zero, three transform draws, 18 vertices,
one present intent and zero native faults. Anvil then answered at a real
`pmf>` prompt over Wi-Fi with build 242, and the deadman was explicitly
turned off. No monitor image, storage or boot medium was written. This test
used a 64×64 offscreen attachment, so its output was verified by raw pixel
readback rather than a display screenshot.

The transform follows the desktop Neon sprite's center rotation and
top-left camera/zoom formulas, expressed as bounded Q16 angle/zoom and Q8
vertex coordinates. GPU sampling and blending remain in the existing Vulkan
path; the processor prepares vertex positions. This proof covers the tested
angles and coordinates, not arbitrary precision equivalence to desktop
floating-point math. Multiple simultaneous image registrations, animation
batching and a desktop Neon Vulkan backend remain open.

The saved [report.bin](report.bin) is checked independently with:

```text
python tools/vulkan_neon_sprite_transform_proof_check.py docs/evidence/neon-sprite-transform-pi4-20261002/report.bin
```

The checker also rejected a deliberately changed rotated pixel. The complete
Pi 4 monitor and the unchanged 15-scene diagnostic compiled with this adapter,
but resident build 242 was not replaced. Source, report and payload digests
are in [manifest.json](manifest.json).
