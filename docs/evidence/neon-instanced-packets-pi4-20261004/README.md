# Pi 4 V3D instanced packet encoding

`RaspberryPi4/Lib/v3d.pi4` now emits the V3D 4.2 non-indexed instanced,
indexed instanced, and base-vertex/base-instance packets. The field layout
follows the local Mesa `v3d_packet.xml` packets 38, 34, and 43; the call
order follows Mesa `v3dx_draw.c`.

`RaspberryPi4/Examples/Diagnostics/pi4V3dInstancedPackets.pi4` checks the
37 emitted bytes, a guard byte after them, and refusal of a zero instance
count. It does not submit a GPU list. The first checker used unaligned
32-bit loads on byte-packed fields and faulted at `0x650002`; the final
checker assembles those fields from bytes. This distinguishes a checker
fault from a packet or GPU result.

The final payload was compiled for Pi 4 at `0x800000`, transferred to
resident build 244 over Wi-Fi, verified by the board's SHA-256, and run
under a confirmed 15-second deadman. It returned `x0=15`, matching all
15 checks. The monitor captured sequence 34 at 1280×800, returned to its
prompt, and reported the deadman off. The [run report](report.json) and
[screen capture](screen.png) are preserved here.

This establishes packet bytes on Pi 4 silicon only. Vulkan
`vkCmdDraw`/`vkCmdDrawIndexed` still reject multiple instances and
`VK_VERTEX_INPUT_RATE_INSTANCE`; the packet additions do not make
Neon's instanced particle renderer available or accelerated yet. A GPU
pixel proof with distinct per-instance data is still required.
