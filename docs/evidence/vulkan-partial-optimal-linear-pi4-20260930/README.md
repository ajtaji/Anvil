# Pi 4 bounded partial optimal-to-linear image copy

The 2026-09-30 Pi 4 run exercised the bounded optimal-to-linear
`vkCmdCopyImage` path on a 37×13 BGRA8 image. The `(32,8)` region with
extent `5×5` copied all 25 expected texels; 456 other image texels and
32 guard words remained unchanged. The 148-byte destination row pitch
leaves no row-padding words in this case. The run advanced TFU from 0 to
1, DMA from 0 to 4 and backend jobs from 1 to 2. A same-sized non-edge
tail was refused with `-20005` before additional transfer work. The
intentional refusal accounts for one validation fault; MMU, OOM and
native fault counts remained zero. The report pointer returned in `x0`
was `0x8C88D0`.

The trace is `report.bin`, 1,056 bytes, SHA-256
`AE85D27F155F4424FAB11D5AF432AEF652EB5E0B6E7D4BA03D67BD6C69AD70AF`.
The tested payload SHA-256 was
`D5C1DCC47F042F251F72E494D0A8255952B2D999603086AAFD8986820645FCC9`.

This evidence proves only the stated Pi 4 shape. It does not establish
support for other boards, optimal-to-optimal partial copies, other edge
shapes, mips, layers or format conversion.
