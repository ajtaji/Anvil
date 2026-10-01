# Maximum 4×4 UIF-grid buffer upload proof

The 2026-10-01 Pi 4 run exercised the maximum sixteen-intersection shape of the dedicated `BUFFER_TO_TILED_GRID_4X4_COPY` route. A single `vkCmdCopyBufferToImage` region copied 13×13 BGRA8 texels at destination `(3,3)` into a 16×16 optimal image, reaching the right and bottom edges. The source buffer offset was 64 bytes, row length 16 texels, pitch 64 bytes, and exact accessed span 820 bytes. The four intersection rows were `[1,4,4,4]`, then `[4,16,16,16]` for each of the next three rows.

The full-image readback found 169 changed texels and 87 unchanged texels. It checked all 169 source payload words, 39 per-row padding words and 183 total sentinels; readback padding was 64 words and combined stage/readback/image allocation guards were 96 words. The upload issued 16 DMA operations in one backend job with no partial-upload TFU increment; the later full readback issued 16 DMA operations. Status slots, MMU faults, bin OOM, native errors and validation-fault count were zero.

`report.bin` is the exact 1,056-byte returning report. SHA-256: `29BCB1E42C882889328665521A54230107A70DED73D33131B298C3D35F36F2D6`. The frozen signed PMF was 796,956 bytes with SHA-256 `E6612CC343F7459231667E2FE51ACF21603BD7FA5980870A4C5E10656B8C7DE9`. The independent `tools/vulkan_buffer_tiled_grid4_max_proof_check.py` report checker validates all sixteen tile counts and transfer deltas.

This proves the maximum 4×4 grid shape on Pi 4 only. The earlier ≤2×2 `BUFFER_TO_TILED_GRID_COPY` capability remains separately bounded; non-Pi 4 backends fail closed, and the complete-image TFU upload is unchanged. The board was restored and the lease released after the run.
