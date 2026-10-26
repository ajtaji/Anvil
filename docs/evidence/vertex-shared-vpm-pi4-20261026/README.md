# Shared VPM inputs and bounded vertex graphs on Pi 4

The renderer's shared vertex memory reservation previously followed output
rows alone. A twelve-input-row shader with six coordinate outputs and four
vertex outputs received only one eight-row sector in each program. Reserving
the larger input/output requirement fixes the measured blank frames. The
existing extra sector for varying programs is preserved.

The before and candidate contain byte-identical coordinate and vertex code.
Their captured VPM reservation word changes from `01010101` to `01020102`.
Before, all four reference frames match and all four compact frames are clear.
After, all eight complete 64x64 BGRA frames match the independent rational
line oracle: 131,072 bytes, four rotations, reversed endpoints, diagonals
and a single-pixel point. Candidate teardown leaves zero live allocations.

The vertex planner now accepts at most sixteen scalar arithmetic operations.
For large input layouts it reuses input-index registers after input fetch;
coordinate output indices remain live and untouched. Its scratch allocation
is bounded by the current four-way RF0..31 budget. The captured programs
contain eight scalar products and eight additions, plus two viewport
multiplications, and stay within that register budget. A seventeen-operation
public pipeline refuses -8 before publishing a handle. The independent raw
decoder checks the actual code without executing an emulator. A compiled
510-case table checks shared segment boundaries; 41 damaged proofs refuse.

The final proof uses public Vulkan pipelines and four-vertex, eight-instance
draws. It stores four exact corners in 32 bytes per line rather than the
production triangle path's 144 bytes. This is an isolated working prototype,
not a production Neon integration, a throughput result, or a full native
capacity proof. Mutable/repeated outlines and mixed draws still need work.

The full existing 15-scene regression retains all 245,760 GPU bytes and passes
124 widget checks. No old native line golden was changed. Historical line
scenes 4/5 predate the intentional current pixel-placement contract.

Build and check (the builder never boots a board):

```text
python tools/build_vertex_shared_vpm_proof.py --compiler <PureMetalForge.exe> --out <directory>
python tools/vertex_shared_vpm_proof_check.py --report docs/evidence/vertex-shared-vpm-pi4-20261026/candidate/report.bin --pixels docs/evidence/vertex-shared-vpm-pi4-20261026/candidate/pixels.bgra --before-report docs/evidence/vertex-shared-vpm-pi4-20261026/before/report.bin --before-pixels docs/evidence/vertex-shared-vpm-pi4-20261026/before/pixels.bgra --self-test
```

The complete hash-verified returning PMF stages at 01000000, stack04F00000.
Read report E1C00000:8192 and pixels E2400000:131072 in chunks no larger than
16 KiB. Final proof capture156 returned0 in7.3s; complete regression capture157
returned0 in13.1s. The board remained on resident328; counted338 compiles,
not installed. Every phase finished at a healthy prompt with healthy cores,
the Vulkan console restored, the watchdog off and the lease free. No reset,
flash or emulator was used. Two earlier readbacks needed a new read-only
connection after confirmed return; no payload was rerun for those transfers.

The investigation also found a high-register/four-way record mismatch.
Changing that flag alone did not fix the blank frames. That broader mode
issue, including fragment stages, stays open in topic1444. This proof uses
low-register code throughout. Topics1443 and1445 cover the bounded graph and
shared-memory fixes; topic1442 retains production line-capacity work.

The shared-segment rule was checked against the primary Mesa VPM description:
[vertex program data](https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/be00f53d4d50b87a87f83e8fa243b77e614eb0b8/src/broadcom/compiler/vir.c).
Only the hardware allocation fact was consulted; no implementation was copied.
The manifest records exact sources, containers and captured evidence.
