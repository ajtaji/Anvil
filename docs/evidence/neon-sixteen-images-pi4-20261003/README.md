# Pi 4 sixteen-image capacity proof — 2026-10-03

The returning [RAM diagnostic](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonSixteenImageProof.pi4)
loaded all sixteen separate BGRA sampled-image IDs simultaneously beside the
atlas. Each image contained a distinct opaque pixel. One Vulkan frame drew
all sixteen as ordered 4×4 patches and drew an atlas sprite. The payload
checked each live image handle and descriptor against all earlier IDs using
full-width values. Both a replacement and a draw for invalid ID 17 were
refused without changing the 17-draw, 102-vertex frame. After exact pixel
readback, adapter destruction left no live image or descriptor handles.

The 256-byte [report](report.bin), SHA-256
`89164efb8751eea2c0d663072c477ba132c9dc69fe9a3f0c9816e3934cb62a8c`,
passed the independent
[oracle](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonSixteenImageProof.oracle.ps1).
Its sixteen image pixel words are all distinct, the atlas and background
probes match, and no Vulkan fault was recorded. The oracle's synthetic
acceptance case passed; mutated pixel and aliased-handle cases were rejected.

The signed PMF container was 1,319,508 bytes, SHA-256
`287be3131f9c69370e83e9a28f1de4e01b63fc4c87f369677147d5ef48190121`.
It was linked and staged at `$00700000`, verified on the board, and returned
`x0=$00D4CC38` after 4.3 seconds under a 15-second deadman. Resident
build 242 reached a real `pmf>` prompt; `last run` 18 reported a return and
the deadman was explicitly disabled. No boot image, flash or board filesystem
was changed.

This proves sixteen simultaneous separate sampled images on Pi 4 for the
small 1×1 BGRA shape, their independent live handles, ordered draw and atlas
coexistence. Larger images, aggregate memory-pressure limits, other boards and
installation of an updated full monitor remain separate work.
