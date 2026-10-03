# Pi 4 separate sampled sprite image

On 2026-10-02, a returning RAM payload on Raspberry Pi 4 monitor build 242
used one independently owned RGBA8 image, memory allocation, view and
descriptor set alongside the existing shared TrueType/sprite atlas. The
separate image and atlas were sampled in the same Vulkan command stream.

The 12 MiB caller-supplied Vulkan heap window refused a 1024×1024 replacement
while the resident image remained published. A following frame reproduced six
exact BGRA probes from the resident image and atlas. Two small replacements
then succeeded, exercising descriptor-set reuse, and the final sampled pixel
matched the new image. The report recorded no native faults. This proves one
separate image and replacement path, not sixteen simultaneous separate
images.

The final 1,323,124-byte PMF container had SHA-256
`138e14f56307f80762dcf9c4f0c402688930efb13353cdb0dbc7ab06e83069be`.
The board verified the transferred digest, ran it from `$700000` under a
15-second deadman, and returned report pointer `$00D4CA98` in 4.3 seconds.
The [192-byte report](report.bin) passed the
[oracle](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonSeparateSpriteProof.oracle.ps1).
It rendered to a 64×64 offscreen attachment, so the pixels were read from that
attachment rather than from a monitor screenshot.

The full Pi 4 monitor compiled with the same source but was not installed. Its
compiled image reaches `$70014F`; after a future installation, RAM payloads
must use the live monitor's `map` output for a staging address rather than
assuming the `$700000` address used on resident build 242.
Resident build 242 answered at a real `pmf>` over Wi-Fi after the test, and
the deadman was explicitly turned off. No boot image or storage was written.
The image and buffer allocations are checked against the caller's heap size
before a replacement, and each Vulkan allocation can still refuse a layout
that fails to fit because of alignment or fragmentation.
