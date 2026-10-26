# Combined Neon draw capacity on Pi 4 - 25 October 2026

The shared recorded-draw pool, private V3D draw slots and adapter ceiling now
accept 6,144 records, matching the sum of native Neon's 4,096 flat and 2,048
textured records. Existing callers retain their requested smaller ceiling.
The shader emitter keeps its standalone constant rather than gaining a new
command-layer include dependency. No compiler or emulator was used to render
pixels; all frames came from the physical V3D through public Vulkan calls.

One frame records 4,096 opaque red one-pixel boxes and 2,048 bitmap-text
calls. The final glyph is green, preserving observable draw order. It fills
all 6,144 shared recording rows with 36,864 vertices. The next adapter draw
returns -21203 without changing draw/vertex cursors, the free-row count, or a
16-byte guard at the unused next vertex. The complete 64x64 GPU capture
matches an independent opaque-colour/input-glyph oracle.

Destroy returns all 6,144 rows. Recreating with a two-draw limit accepts two
boxes, refuses text as the third draw with the same atomicity checks, and
renders a fresh exact 64x64 capture. Final caller/adapter teardown leaves
zero memory allocations and all draw rows free. The checker matches every
one of 32,768 pixel bytes and rejects 31 damaged reports, captures or lengths.
This proves the combined record capacity and smaller-limit behavior. Separate
flat/textured budget accounting, native vertex units for expanded lines/fans,
and maximum vertex workloads remain open; this is not full native parity.

The first 15-second run (744) hit the watchdog after recording the whole
frame. It FAILED and caused one watchdog restart; its result is not counted
as a pass. The monitor answered its own prompt/last-run check afterwards,
and a read-only recovery phase confirmed healthy cores and restored Vulkan.
A requested 60-second watchdog was correctly refused before any upload,
because the hardware supports at most 15 seconds.

A private diagnostic with timing stores and bounded progress feeds completed
and showed about 1.73 seconds recording boxes, 1.12 seconds recording text
and checking refusal, 11.51 seconds inside End, and 0.017 seconds destroying
the large adapter. It did not change rendering behavior. The final proof uses
the UNMODIFIED production renderer and feeds the 15-second watchdog only
between its bounded phases. It returned zero in 21.5 seconds, capture 120,
with healthy cores, Vulkan restored, watchdog off and the lease released.
The total is not a 15-second whole-payload pass or a frame-rate claim.

Build and check using the unified compiler:

```text
python tools/build_neon_combined_draws_proof.py --compiler <PureMetalForge.exe> --out <directory>
python tools/neon_combined_draws_proof_check.py --report docs/evidence/neon-combined-draws-pi4-20261025/report.bin --pixels docs/evidence/neon-combined-draws-pi4-20261025/pixels.bgra --self-test
```

The public builder emits the exact complete PMF used in the final physical
run. It stages at 01000000 with stack 04F00000 and an explicit 16 MiB heap
063E8000..073E7FFF, mapped through the existing native surface boundary.
Main returns zero. Read E1C00000:8192 and E2400000:32768 in chunks no larger
than 16 KiB. It is a returning RAM test, with no flash or boot-selection
change. Resident monitor 328 remains installed. The separately tracked
monitor variable-reservation problem must be resolved before deployment.

The normal automatically counted build 330 compiles successfully. Its BSS
ends at 0E60D90F, beyond the old 16 MiB variable reservation in topic 1249.
It was not installed; compilation is not a deployment acceptance claim.
