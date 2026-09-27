# Pi 4 Vulkan image-to-buffer region array through DMA

The public `vkCmdCopyImageToBuffer` command now accepts one bounded array of
one to 32 colour regions from a bound linear BGRA8 image. Each region may
choose its own image offset, extent, aligned destination-buffer offset and
row pitch. Recording validates every region and pair of regions before it
appends an operation. Submission revalidates the live image and buffer,
source/destination aliasing and destination/destination overlap across the
whole array before starting DMA. An accepted tightly packed full-width
rectangle uses one guarded DMA transfer; other rectangles use one guarded
transfer per row. No CPU pixel-copy fallback is used.

The desk pipeline gate exercises a two-region array with one padded
destination row pitch. Its oracle checks the copied bytes, row padding and
untouched buffer guards. It also requires malformed later regions, overlapping
destinations and counts above the 32-operation capacity to refuse the whole
command. The first expanded run reached successful submit and fence
completion but exhausted the old 180-million-instruction test ceiling while
scanning the full destination buffer. The finite ceiling was raised to 220
million; the complete gate passed 748 checks over 183,246,755 interpreted
AArch64 instructions. The production V3D backend gate passed 85 properties,
the resource gate passed 724, and the dispatch gate passed 604. The normal Pi 4
image compiled at 4,291,848 bytes; its generated source stamp was restored.

The returning Pi 4 RAM diagnostic at
`RaspberryPi4/Examples/Diagnostics/vulkanImageReadbackProof.pi4` first clears
a 64×64 image through V3D, then performs its established one-region DMA
checks, same-image copy and two-region image copy. Its final command reads
two disjoint 4×4 source rectangles into separate ranges of one buffer. The
second range has a six-texel row pitch. It checks every buffer byte against
either the expected V3D clear colour or the untouched guard value, then
requires exactly eight guarded DMA row operations, DMA quiescence and
restoration of the prior DMA write bounds.

On 2026-09-27 the Pi 4 monitor at `192.168.1.111` verified the 645,328-byte
PMFBOOT v2 payload, SHA-256
`5d295a4bde461f5eb69dec5bb54ea967bd12a27a66b4644f7012647c930495f9`.
The RAM-only diagnostic returned `x0=0`; the board's last-run record reports
the payload itself returned after 0.6 seconds. The monitor took fresh capture
48 (1280×800, DMA screen tier); its PNG SHA-256 is
`a55755e6d69a69b148b15d2b1ada62b641284f49ff3427b9513c9ca7d0b71e19`.
The deadman was turned off, capture disarmed and `coretest status` reported
zero secondary, GIC and watchdog leases before the shared board lease was
released. No flash, reset or boot-medium write was used.

The machine-readable run, fresh screenshot and compressed console transcript
are in `runs/vulkan-readback-array-20260927/`. This proves the exact two-region
shape on Pi 4 silicon; it does not prove optimal-tiled readback, layers, mips,
separate readback calls in one command buffer or general Vulkan 1.0
conformance. The Vulkan rule for region arrays and non-overlapping accessed
locations is in the [official `vkCmdCopyImageToBuffer` reference](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdCopyImageToBuffer.html).
