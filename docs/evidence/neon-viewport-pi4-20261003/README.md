# Neon fixed-canvas viewport math

`Anvil/Graphics/Vulkan/neon_vk_viewport.pbi` provides board-neutral viewport
planning and inverse pointer mapping for an eventual Neon application host.
It follows the desktop source's float32 order: fit width, switch to a height
fit if needed, calculate centered offsets from the unrounded target, then
convert offset and size independently to pixels. Its pointer result separates
content from letterbox bars and returns signed Q16 canvas coordinates. The
module owns no display, Vulkan object or input device.

The returning gate covers a 1280×720 canvas on a 1280×800 screen with 40-pixel
bars, a height fit, fractional offsets, two layouts where exact-rational
rounding differs from the source's float32 result, inverse pointers, bars,
outside-screen coordinates and invalid-plan poisoning. It desk-compiled for
Pi 3, Pi 4 and Pi 5. The Pi 4 PMFBOOT SHA-256 was
`E93BAE522C5773847AAE3EF0D3CD24D1393A085BC41F125290CC89952995FFA4`.
On resident Pi 4 Anvil build 244 it uploaded with a matching board digest at
`0x00800000`, ran under a confirmed 15-second deadman, and returned the
expected report pointer `x0 = 0x02000000` in 0.9 seconds. The report oracle
passed. The resident image and display were unchanged.

Saved [report](report.bin) SHA-256
`32371185DCBA572BBFCEDF585038850367C314A7497E1BD841041334DE98F6DB`.
From the repository root, check it with
`RaspberryPi4/Examples/Diagnostics/vulkanNeonViewportGate.oracle.ps1 docs/evidence/neon-viewport-pi4-20261003/report.bin`.

This proves viewport math on Pi 4. It does not yet render a Neon-authored
scene through a letterboxed Vulkan present path or deliver input events to
an application. Pi 3 and Pi 5 have compile evidence only.
