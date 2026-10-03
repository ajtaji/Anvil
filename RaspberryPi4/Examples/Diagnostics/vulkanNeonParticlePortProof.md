# Pi 4 Neon Vulkan particle adapter payload

This revised returning offscreen proof passed on Pi 4 build 244. Its preceding
image returned status 26 because the oracle expected opaque alpha for the two
translucent samples. The captured RGB, rotation, empty corner, draw count,
and vertex count all matched. The renderer blends alpha with the same
source-alpha factors as RGB, producing `0xBF` at those samples. The corrected
oracle and unchanged renderer then passed on the board; see the saved
[report](../../../docs/evidence/neon-vk-particle-port-pi4-20261003/README.md).
It exercises the Anvil particle adapter in this order: `Init(1)`, camera,
three `Add` calls, `Prepare` before the frame, then `DrawPrepared` within one
frame. The scene contains an opaque red square, a later translucent green
square that overlaps it, and a rotated opaque blue square. A camera offset
of (2,1) shifts all three. Six pixel probes check the red-only region, the
ordered red/green blend, green-only region, blue centre, rotated blue tip,
and an empty corner. The report also requires one Vulkan draw, 18 vertices,
one completed particle palette upload, zero faults, and clean teardown.

Build with `-t pi4 -s --entry-returns --load-addr 0x800000 --bss-addr
0x2000000 --stack-addr 0x4000000`. The `vulkanNeonParticlePortProof.img.pmf`
container is 1,344,132 bytes with SHA-256
`BF8428DFB11DF227A3BEE5B2111B694DD44A890C8E8A8FD105F9ECCCBEB3DF9D`.
Its 1,344,004-byte inner image has SHA-256
`08A21B25FF6EC2007C92AA815543E3D34354EC30CC57A92B583490068F390535`.
The source SHA-256 is
`2D2290F87A022784628AE331EE81D311FDFCA607BC601D4C1E0C98F9E356BE43`.

The image occupies `0x00800000..0x00948203`. BSS occupies
`0x02000000..0x02C27EBF`; stack starts at `0x04000000` and grows down.
The Neon surface occupies `0x06000000..0x063E7FFF`, the Vulkan window
`0x063E8000..0x06FE7FFF`, and the Neon arena
`0x0A000000..0x0AFFFFFF`. These regions are disjoint from the resident
monitor, display framebuffer, driver arena, and screenshot space in the
verified Pi 4 map. The image never writes a boot file or the scanout.

The returned x0 should be `global_nppreport` at `0x020002C8`. Read 128 bytes
there and pass the file to `vulkanNeonParticlePortProofCheck.py`. Run only
with the monitor's normal verified PMF upload and a 15-second deadman.
Every returning path checks `vkDeviceWaitIdle` before Chrome, Neon, or Vulkan
teardown. If GPU completion or Chrome's internal idle check fails, the
payload stays in a WFE loop without petting the deadman, allowing it to
reset the board instead of returning to a monitor with work in flight.
An absent return is a failure, not a passing report.
