# Ordered optimal-image TFU uploads on Pi 4

`vkQueueSubmit` now preflights every complete optimal BGRA8 buffer-to-image copy before beginning the transfer sequence. The Pi 4 backend validates the mapped source, padded destination, alignment, overlap, timeout, and UIF layout metadata before touching TFU registers. The queue then executes each recorded upload in order, waiting for each TFU job before starting the next and publishing the final image layout only after all jobs complete. Linear-image uploads in the same transfer command buffer continue through DMA. A backend that holds an asynchronous image job refuses a multi-copy submission before any transfer starts.

The diagnostic records two uploads of the same 8×8 optimal atlas in one command buffer, then samples it in eight V3D draws. The board report records two TFU jobs and the checker verifies 213 exact report and pixel conditions. This proves the repeated transfer stays on the TFU and the subsequent render stays on V3D; there is no processor-side image-copy fallback in this path.

- Pi 4 resident build 210, RAM-only payload linked at `$600000`; board run returned report pointer `$8208C8`, fresh capture 61. The first `$500000` build was rejected by the monitor before entry because its range overlapped the resident monitor; it did not execute.
- PMFBOOT SHA-256: `50288A63969033A261B6D0FF8281C820275D9EEE7D9563F566FF922086DFBFFD`.
- [Board report](evidence/vulkan-ordered-tfu-20260927/board-report.bin) SHA-256: `47721F949E5789891AD612CB07DAA4EA259EEC68895B486673396B8FB1578437`.
- [Board capture](evidence/vulkan-ordered-tfu-20260927/board-capture.png) SHA-256: `F71F38F67389BA2EDB41A662402797B93DF510931092348FFAEE343EFA8B0E86`.
- [Verified raw BGRA capture](evidence/vulkan-ordered-tfu-20260927/atlas-verified.bgra.gz) is the board PNG rotated back into the logical 800×1280 coordinates expected by the pixel oracle.
- [Board run record](evidence/vulkan-ordered-tfu-20260927/board-run.json) includes verified transfer and fresh capture metadata.

The isolated texture gate passed 53 checks over 42,230 interpreted instructions; the production backend gate passed 85 checks over 4,404,360 instructions. The normal Pi 4 image compiled to 4,332,228 bytes. The public pipeline gate passed 779 checks over 203,822,909 interpreted instructions, including two optimal uploads reaching the backend in one submission and leaving the image in shader-read layout.

This is bounded Vulkan functionality. It does not imply general optimal-image subrectangles, arbitrary formats, or completion of Vulkan 1.0.
