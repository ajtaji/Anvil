# Pi 4 simultaneous sampled sprite images — 2026-10-03

The Neon Vulkan adapter now accepts separately allocated sampled images at
IDs 1 through 16. Its original unindexed replace, draw, generation and clear
calls still select ID 1. Each ID has its own image, memory, view, descriptor,
dimensions and generation. The atlas remains independent. A replacement is
published only after its upload, view and descriptor succeed; a refused
replacement leaves every resident ID unchanged.

A returning RAM diagnostic on resident Pi 4 build 242 drew the shared atlas
and image IDs 1 and 16 in one Vulkan frame. A 1024×1024 replacement was
refused for capacity, and the report checked that both resident images and
descriptor handles were unchanged and their sampled pixels still matched.
ID 16 then accepted a new image while ID 1 remained unchanged. Clearing ID 16
twice preserved its generation after the first clear, and destroying the
adapter twice left no live slot handles.

The signed PMF container was 1,327,812 bytes, SHA-256
`79e9e08f1c20999251e712bb1e9b689a181e2754584f80adbf63de0d9e64fe35`.
It was linked and entered at `$00700000`; the board verified the transfer
hash, armed a 15-second deadman, and returned `x0=$00D4CC38` after 4.3
seconds. The saved 192-byte [report](report.bin) has SHA-256
`e665e351cd5601a383ec28ff157fcbe4f3d8087183dde644b37e9da9a68e6747`.
The [oracle](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonMultiImageProof.oracle.ps1)
passed with stage 9, status zero and no Vulkan faults. The board returned to
`pmf>`, `last run` reported a clean return, and the deadman was explicitly
disabled. No boot image, flash or filesystem was changed.

This verifies two simultaneous separate images on Pi 4, including the highest
supported ID. The code has capacity for 16 IDs, but all 16 have not been
loaded simultaneously on hardware. The indexed image draw currently covers
untransformed rectangles; transformed sprite drawing still samples the atlas.
Other boards have no hardware proof for this path.
