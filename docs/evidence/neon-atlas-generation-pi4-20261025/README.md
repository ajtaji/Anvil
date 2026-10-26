# Pi 4 transactional Neon atlas generations - 25 October 2026

The production Neon Vulkan adapter now prepares a new atlas image, memory,
view and descriptor without publishing them. It uploads and waits before
replacing the active handles, then retires the prior generation. Ordinary
TrueType dirty-region uploads retain their existing partial/full path.

The physical prior-source reproduction fills all 27 remaining memory rows.
Its in-place refresh succeeds and changes 230 words of the resident atlas;
status 191 identifies this controlled negative, not an accepted implementation.
The candidate instead returns capacity error -21203 while retaining every
active handle/generation and all 2,097,152 old atlas bytes. After the held
allocations are freed, three font swaps and mixed bitmap-text/separate-sprite
frames complete with identical live memory counts. Every one of 49,152 GPU
pixel bytes matches an independent host oracle built from the two input
glyphs, known clear colour and opaque white/green draw rectangles. The repeated
font produces the same complete frame again. Nine report/pixel mutations
are rejected by the standalone checker.

The uncertain-completion diagnostic performs a real successful GPU upload,
then injects a failure result and a refused idle check in its private test
copy. It does not hang the GPU. The owner retains both active and candidate
resources, stops accepting draws, and later retires them only after real
device-idle confirmation. One caller-owned target allocation remains after
adapter teardown; caller teardown then leaves zero memory allocations.
This is fault-injection evidence for retention, not a naturally occurring
GPU failure or an asynchronous-driver completion proof.

The complete 15-scene regression matches all 245,760 bytes of the current
pre-change baseline, and all 124 widget/report checks pass. Thirteen scenes
also retain the old native corpus exactly. Historical scenes 4/5 already
differed before this change after the 14 October line pixel-placement change;
the old corpus remains unchanged. No all 15 historical-native identity claim
is made. The existing TrueType partial/full upload diagnostic also passes its
unchanged transfer-count, GPU-pixel and untouched-atlas oracle.

Build the focused physical diagnostic through the unified compiler:

```text
python tools/build_neon_atlas_generation_proof.py --compiler <PureMetalForge.exe> --out <directory>
```

Run its returning image at 01000000 under a 15-second deadman using the normal
board runner. Main returns 0; read E1C00000:8192 and E2400000:49152 with bounded
readback chunks. The injected variant adds `--inject-uncertain`. To check the
committed physical data:

```text
python tools/neon_atlas_generation_proof_check.py --report docs/evidence/neon-atlas-generation-pi4-20261025/candidate-report.bin --pixels docs/evidence/neon-atlas-generation-pi4-20261025/candidate-pixels.bgra --self-test
python tools/neon_atlas_generation_proof_check.py --report docs/evidence/neon-atlas-generation-pi4-20261025/uncertain-report.bin --pixels docs/evidence/neon-atlas-generation-pi4-20261025/uncertain-pixels.bgra --injected-uncertain
```

All returning runs used resident build 328, completed below the armed 15-second
deadman, and restored a healthy prompt/cores and Vulkan console with the
watchdog off. No reset, firmware replacement or boot-selection change occurred.
The full monitor compiles as automatically counted build 329, but was not
installed: the separately tracked variable-reservation problem in topic 1249
still requires correction before current-monitor deployment. These results
close this atlas lifecycle slice, not the entire Neon port or Vulkan 1.0.
