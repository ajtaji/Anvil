# Neon RGBA sprite through Vulkan on Pi 4

On 2026-10-02, a returning RAM payload on a Raspberry Pi 4 running Anvil
build 242 rendered four sprites through the shared `NeonVkChrome` adapter and
the V3D Vulkan backend. The 2×2 source image carried opaque red, half-alpha
green, transparent blue and opaque white texels. The four draws exercised a
scaled full image, two cropped texels, and a tinted texel. The returned
64-byte report passed the six exact BGRA pixel checks, four-draw/24-vertex
checks, and zero native-fault checks. A separate host checker accepted the
saved report and rejected a deliberately changed green pixel.

The final 1,294,604-byte `.pmf` container was SHA-256
`c84f3f062ce476154638a6445fe7229e55e5ca99d07a0396135dbb78f3aaf68d`.
The board verified the full transfer digest, ran the payload from `$700000`,
and returned report pointer `$00D88248` in 4.0 seconds under its 15-second
deadman. After the run it answered at a real `pmf>` prompt on Wi-Fi; the
deadman was explicitly turned off. No monitor image, storage, or boot medium
was written. This was an offscreen 64×64 attachment, so the proof uses pixel
readback instead of a display screenshot.

The half-alpha green probe was `0xBF008000`: this adapter uses
`SRC_ALPHA`/`ONE_MINUS_SRC_ALPHA` for both color and alpha, matching its
existing pipeline. The saved report makes that exact blend result reviewable.

The first three RAM runs returned safely and exposed diagnostic setup errors:
the 64×64 test surface advertised insufficient image capacity for the
512×1024 atlas, then the payload's own comparison treated high-bit BGRA
words as signed integers. The final run declares the atlas capacity before
Neon initialization and masks report words before comparison. Its exact
report is [report.bin](report.bin); recheck it with:

```text
python tools/vulkan_neon_sprite_proof_check.py docs/evidence/neon-sprite-pi4-20261002/report.bin
```

This establishes one registered RGBA image up to 480×256, cropped and scaled
with tint. It does not establish desktop Neon Vulkan support, sprite rotation,
camera mapping, multiple simultaneous images, or acceleration on other boards.
The existing RGB logo path and the earlier 15-scene widget proof compile with
the same adapter source. The complete Pi 4 monitor also compiled from this
source; no resident monitor was replaced for this test.

Exact source, report, compiler and container digests are in
[manifest.json](manifest.json).
