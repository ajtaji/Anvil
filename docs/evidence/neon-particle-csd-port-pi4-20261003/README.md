# Pi 4 Neon particle adapter through the Vulkan CSD producer

The explicit `NeonVkPortParticlesGpu*` route in
`Anvil/Graphics/Vulkan/neon_vk_particle_csd_port.pi4` connects Neon-style
particle adds and camera state to the Pi 4 CSD producer. The CPU adapter and
GPU routes share validation but carry distinct prepared-route tags; a draw
through the wrong route refuses. No Neon Arcade Engine source was changed.

`tools/neon_vk_particle_port_check.py` passed 556,687 interpreted A64 steps for
the existing CPU adapter and 573,931 steps for CPU/GPU route isolation. The
gate checked failed GPU preparation, stale camera state, route switching,
release invalidation, and compilation with the real Pi 4 CSD/Vulkan
composition. `tools/neon_vk_particle_csd_port_build.py` generated and compiled
the returning board payload from the existing CSD proof, replacing its direct
producer calls with the port API. The generator refuses changed source anchors.

On Pi 4 Anvil build 244, the final 1,394,524-byte PMFBOOT container had
SHA-256 `541E44120DF1494A0576A016B0DCE903F35452FB4FF5FBCF3DEF2A07F59497D9`.
The monitor verified the upload at `$00800000`, armed a 15-second deadman,
and the payload returned `x0=$02229D18` in 5.0 seconds. The report status is
zero. CSD expanded 32 compact particle items into 192 Vulkan-format vertices;
the payload compared every input and output word against its CPU geometry
oracle, checked guards and all item-center/background pixels, and observed
one V3D bin job and one render job. There were no reported Vulkan, MMU, or
unsafe-teardown faults. The eight mutation checks in
`tools/neon_vk_particle_csd_port_check.py` all rejected altered report fields.
Measured Prepare, CSD, Vulkan End, and total-to-pixels times were 23,382,
252, 35,243, and 1,807,678 microseconds. These are one offscreen run, not a
frame-rate result.

The saved [report](report.bin) has SHA-256
`00FE4D606FEF2CBF05B91401F6EDB40A59B6195A7271E308003A73F5ADB5CAF8`.
The fresh [monitor capture](monitor.png) has SHA-256
`EB823427FB602155799A45717ABE6C6D4597D651A76FF9C4D493C5612A240E6E`;
it shows the monitor on the physical display, while the GPU target was
offscreen. Capture sequence advanced 4 to 5. The monitor returned to a real
`pmf>` prompt and reported the deadman off. No boot image or storage file was
changed. The full run transcript and manifest are under
`runs/neon-particle-csd-port-pi4-20261003-r3/board/` in the local checkout.

This proof covers the adapter's small, quantized particle path on Pi 4 only.
It does not make CSD the default, move Chrome's geometry validation or compact
record staging off the CPU, demonstrate a resident Neon application, or prove
other boards' GPU paths.
