# Pi 4 partial TrueType-atlas upload proof — 2026-10-03

The Neon Vulkan adapter now tracks one dirty rectangle while adding glyphs to
its persistent 512×1024 BGRA atlas. When the rectangle can be rounded to a
source-aligned, 4×4-tile-aligned region of at most 256 tiles, one Vulkan
buffer-to-image transfer updates only that region before the next frame.
Cache reset, bitmap-font revision refresh and larger glyph unions use the
existing complete-atlas transfer. A transfer failure quarantines the atlas;
dirty state is cleared only after a successful submission.

The partial path requires `BUFFER_TRANSFER`, `LINEAR_TRANSFER`, and
`BUFFER_TO_TILED_RECT_COPY` backend capabilities. If a board does not
advertise them, the adapter chooses the existing complete-atlas upload.
The missing-capability planner fallback was checked at the desk; only the
capable Pi 4 route was exercised on hardware.

The returning [RAM diagnostic](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonTTPartialUploadProof.pi4)
placed synthetic pixels in nonadjacent rows of the staging atlas. Its first
4×8 update copied 128 logical rectangle bytes from a 512-texel source stride
and took two guarded DMA tile operations. A second 4×4 update copied 64
logical rectangle bytes and took one operation. A full-key cache hit caused
no additional transfer. A large dirty union and cache reset each took the
complete 2,097,152-byte upload path. GPU rendering matched the updated
pixels in multiple source rows and preserved a separate atlas logo and an
untouched transparent texel. The checked byte counts describe requested
pixel rectangles, not measured bus traffic.

The 128-byte [report](report.bin), SHA-256
`8C59656C535F6FB04FED48DCC21F7E6BDC1DDEF9F347FB6A05895F0DDF88B5E1`,
passed the strict [oracle](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonTTPartialUploadProof.oracle.ps1).
The oracle accepted a synthetic valid report and rejected a one-pixel
mutation. The signed PMF container was 1,319,916 bytes, SHA-256
`1A493BB91C403A6FDE7FA114D56D8DFAFC6BDEC7D4396BCF3FDE86FE1F6BDE16`.
It was linked and staged at `$00700000`, verified on the board, and returned
`x0=$00D4CC48` after 4.7 seconds of host observation under a 15-second
deadman. Resident build 242 reached a real `pmf>` prompt; `last run` 24
reported a return after 2.6 seconds and the deadman was explicitly disabled.

The unchanged [sixteen-image diagnostic](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonSixteenImageProof.pi4)
was recompiled against the updated atlas code and rerun as a GPU regression.
Its 256-byte [report](sixteen-image-regression.bin), SHA-256
`89164EFB8751EEA2C0D663072C477BA132C9DC69FE9A3F0C9816E3934CB62A8C`,
passed the [pixel/handle oracle](../../../RaspberryPi4/Examples/Diagnostics/vulkanNeonSixteenImageProof.oracle.ps1).
The PMF container was 1,324,380 bytes, SHA-256
`0D35F26BDAF6DC90552E4CAA785BEF3CEEEEAF8CCA4AD803C897270C79DB403D`;
it returned `x0=$00D4CC48` after 4.3 seconds of host observation. `last run`
25 reported a return after 2.1 seconds. The real prompt remained healthy and
the deadman was explicitly disabled. Neither run changed the boot image,
flash or board filesystem.

This validates the bounded partial-copy geometry and atlas pixel isolation
using synthetic staging pixels. It does not re-prove TrueType font parsing,
glyph rasterization, a measured frame-rate gain or other boards. The latest full Pi 4 monitor source desk-compiled with the signed IDE compiler
and `--no-bump`: a 5,251,408-byte image, SHA-256
`F69BB278AB44B768A373A2773882CC80D85A2EFEABF1903D0C39A99D0E349DAF`,
linked at `$200000..$70214F`. It was not installed. If installed, its
extent would overlap the former `$700000` RAM payload staging address;
future staging must use the live `map`.
