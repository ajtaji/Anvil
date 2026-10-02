# Pi 4 Neon/Vulkan banner evidence (2026-10-02)

The same Pi 4 banner composer used by the monitor was exercised in two
returning RAM payloads against Anvil build 223 (running-image CRC32
`5BC668D0`). The payloads rendered into an off-screen Vulkan image and
copied only the banner strips into disjoint RAM buffers. No monitor image was
installed, no boot medium was written, and neither payload reset the board.

Mode 3 used the built-in bitmap face and the repository's RGB logo. Its
signed PMF SHA-256 was
`3197E1D9055B441686D4DA98D5D4D295F533C55C7671FF9ED7533BC8D2BB00BF`.
It returned with status zero under a 15-second deadman. The three physical
BGRA strips at 0, 90 and 270 degrees passed 16,914 checks, including every
logo pixel and the banner geometry.

Mode 4 selected an original, two-glyph TrueType fixture before rendering.
Its signed PMF SHA-256 was
`24C6BA4138EAD77CCEE2DF41D57726A01456015F0EC2D6CE9158711C24A88042`.
It returned with status zero under the same deadman. The font rasterized four
times during prewarm, had zero in-frame rasterizations and uploads, and
measured the title at 485 pixels versus the bitmap face's 360. Four
CRC-verified strips covered 0, 90 and 270 degrees, plus a second 0-degree
frame with a longer clock caption and a moved glint. The changed frame
differs in 108 clock pixels and 10 glint pixels, with no other changed
pixels. The strict checker passed 22,663 checks.

Run the saved evidence checks from the repository root:

```text
python tools/vulkan_neon_banner_check.py --report docs/evidence/vulkan-neon-banner-pi4-20261002/mode3-report.bin --capture0 docs/evidence/vulkan-neon-banner-pi4-20261002/mode3-capture0.bgra --capture90 docs/evidence/vulkan-neon-banner-pi4-20261002/mode3-capture90.bgra --capture270 docs/evidence/vulkan-neon-banner-pi4-20261002/mode3-capture270.bgra
python tools/vulkan_neon_banner_check.py --mode4 --report docs/evidence/vulkan-neon-banner-pi4-20261002/mode4-report.bin --capture0 docs/evidence/vulkan-neon-banner-pi4-20261002/mode4-capture0.bgra --capture90 docs/evidence/vulkan-neon-banner-pi4-20261002/mode4-capture90.bgra --capture270 docs/evidence/vulkan-neon-banner-pi4-20261002/mode4-capture270.bgra --capture-changed docs/evidence/vulkan-neon-banner-pi4-20261002/mode4-capture-changed.bgra
```

The captures prove off-screen Vulkan composition, atlas RGB ordering,
rotation, TrueType selection and dynamic banner updates. They do not prove
the uninstalled monitor's on-screen presentation, touch-keyboard interaction
or idle CPU usage. A real configured TrueType face is needed for smooth
text at boot; without one, the GPU path uses the built-in bitmap fallback.
