# Pi 4 four-corner CSD-to-VkBuffer diagnostic

This returning RAM payload tests a GPU **vertex expansion** step. The existing Chrome particle geometry code first transforms 32 source particles into four camera/rotation-aware Q8 corners, converts them to exact clip-float words, and uploads one 48-byte record per particle. Two 16-lane V3D CSD groups then emit six 24-byte vertices per record directly into a live, bound Vulkan vertex buffer. The draw uses Chrome's particle palette descriptor and one non-indexed draw. This does not move camera, rotation, clip conversion, palette upload, or particle staging onto the GPU, and it does not establish a production speedup.

The record words are `x0,y0,x1,y1,x2,y2,x3,y3,u,v,canary0,canary1`. Vertices are emitted in Chrome's exact `0,2,3,0,3,1` triangle order, each with `x,y,u,v,1,1`. The 32 cases include unrotated/camera-ignored, rotated, camera-panned, and camera-zoomed plus rotated quads. All particles have distinct opaque palette colors and disjoint 32×16 pixel cells. The input occupies 1,536 of 4,096 mapped bytes; the output occupies 4,608 of 8,192 bytes. The byte oracle independently rebuilds Chrome's CPU corner/UV bits from original particles, compares all 1,152 emitted vertex words, then checks every output guard word, input record word, and input-tail word. The pixel oracle checks 32 centers, 32 black gaps, four named palette samples, and the clear corner.

This file only runs under the Pi 4 board supervisor with a 15-second deadman armed before payload entry. It is linked at `$800000` and returns the address of a 256-byte little-endian report in `x0`. The supervisor must confirm the installed monitor map leaves the image and BSS ranges free, then check the PMF container's entry, body hash, and map before a single boot. A failed or uncertain CSD/Vulkan submission, wait, or device-idle check enters `ngpUnsafe` and stays inside the payload until the deadman resets the board; it never returns to a monitor that might reuse live GPU resources. Successful or cleanly rejected paths wait for verified idle before releasing Chrome, allocations, Neon, and MMU ownership.

The proof maps Neon's surface at `$06000000` and the 12 MiB Vulkan window `$063E8000..$06FE7FFF`; the arena is `$0A000000..$0AFFFFFF`. The render target is 128×128 with a 512-byte row pitch. The image, live vertex buffer, CSD code, uniforms, and input are allocated by the Vulkan backend, checked for 4 KiB alignment, checked inside the window, and checked pairwise for overlap before CSD dispatch. The CSD grid is exactly `(2,1,1)` with 16 lanes per group, so input reads stop at byte 1,536 and output writes stop at byte 4,608. The known-good implicit uniform contract supplies the packed workgroup ID in `r0[15:0]`, which the shader masks and combines with `EIDX`; the earlier two-group and 625-group diagnostics exercised that addressing on silicon.

The report has marker words 0/63, status word 1, phase word 2, addresses in words 4/6/7/8/44, CSD results in 11–15 and 34–36, exact byte mismatch counts in 16–18, first vertex mismatch in 19–21, draw results in 22–24 and 31–33, and pixel mismatch count in 30. Word 43 records palette preparation. Setup, CSD submit/wait, byte validation, Vulkan End, and total time through pixels are words 37, 48, 61, 49, and 62. Elapsed gates reject further work after 7 s before CSD, 10 s after byte validation, 12 s after Vulkan End, and 13 s after pixels. The CSD wait itself is bounded to 100 ms. The checker rejects nonzero status, mismatch, fault, and unsafe flags, invalid sample colors, overlapping resources, bad timing, and invalid report markers.

From the repository root, compile to a chosen local output path with:

```text
PureMetalForge --compile RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdFourCornerProof.pi4 --entry-returns --load-addr 8388608 -o <output>.img
```

The PMF container is `<output>.img.pmf`. After a supervised run captures exactly 256 report bytes, check them with:

```text
python RaspberryPi4/Examples/Diagnostics/vulkanNeonParticleCsdFourCornerProofCheck.py <report>.bin
```

The checker has desk-only positive and mutation tests in `vulkanNeonParticleCsdFourCornerProofCheckTest.py`. The supervised Pi 4 run passed the silicon byte and pixel oracle; its saved [report](../../../docs/evidence/neon-particle-csd-four-corner-pi4-20261003/README.md) records the exact result.
