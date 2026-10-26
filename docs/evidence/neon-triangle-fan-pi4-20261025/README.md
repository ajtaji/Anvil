# Neon triangle fans through Vulkan on Pi 4 - 25 October 2026

The shared pipeline validator now accepts TRIANGLE_FAN only when the backend
advertises the separate TRIANGLE_FAN capability. Pi 4 advertises it and emits
V3D primitive mode 6. The existing bounded shaders, resource validation,
recording, draw-list submission and retirement remain the execution path.
Primitive restart remains unsupported. The topology semantics follow the
[Khronos definition](https://docs.vulkan.org/refpages/latest/refpages/source/VkPrimitiveTopology.html).

Neon owns an additional compatible fan pipeline on capable backends. A fill
stores its original n points rather than 3*(n-2) triangle-list vertices,
then restores the triangle-list pipeline for later drawing. Creation failure
uses the existing owner teardown; successful destroy retires both pipelines.
A backend without the capability keeps the original triangle-list lowering
and one pipeline. This is useful for the general Vulkan draw path as well as
Neon's capacity work. Separate family quotas and native maximum point/vertex
workloads remain to implement and prove.

The final candidate renders mixed and tight-buffer frames at all four
rotations. A five-point rectangular fan uses five vertices in a six-vertex
buffer; adding a second fan is refused before changing recorded cursors,
free rows or a 16-byte next-vertex guard. The mixed frame has a preceding
red box and a following batch of two separated blue boxes. Every one of
131,072 observed GPU bytes matches the independent complete rectangle oracle.
Each recreated owner is destroyed; final caller teardown leaves zero live
memory and pipeline objects. Twenty-eight corrupted proofs are rejected.

The capability-masked diagnostic changes only a private advertisement on
the same Pi 4. Its shared validator refuses fan topology with -20005, and
Neon successfully uses the nine-vertex triangle-list fallback in a twelve-
vertex buffer. Its eight frames match another 131,072 exact GPU bytes. The
one validation fault is intentional and required. This proves the fallback
code path on Pi 4, not another board's graphics backend.

The two separated boxes are intentional: one rectangle alone can happen to
look right under either topology. A real physical negative control omits
restoration in a private adapter copy. The payload returns and cleans up,
but the host oracle rejects 576 incorrect GPU bytes bridging the boxes.
That control is not a passing renderer result. Production source is never
mutated by the builder's fault flags.

The full 15-scene regression also matches all 245,760 pre-change current
baseline bytes and all 124 widget checks. The two older native line/outline
scene differences remain historical; that old golden was not replaced.
The selected hardware fan tests are non-indexed, single-instance draws.
They do not establish indexed/instanced fan coverage, every rasterizer edge
case, the entire Neon port, or Vulkan conformance.

```text
python tools/build_neon_fan_topology_proof.py --compiler <PureMetalForge.exe> --out <directory>
python tools/neon_fan_topology_proof_check.py --report docs/evidence/neon-triangle-fan-pi4-20261025/candidate-report.bin --pixels docs/evidence/neon-triangle-fan-pi4-20261025/candidate-pixels.bgra --self-test
```

The optional --mask-fan-capability build uses --masked on the checker.
The optional --omit-restoration build MUST fail the pixel checker. These
fault flags are mutually exclusive. The public candidate builder produced
the exact complete PMF run on hardware. Stage 01000000, stack 04F00000,
report E1C00000:8192 and eight captures E2400000:131072; bounded readback
chunks at most 16 KiB. Main returns zero. No CPU raster or private GPU draw
shortcut exists in the diagnostic.

Final candidate/fallback/control runs returned in 19.0/18.8/18.9 seconds,
with a 15-second watchdog fed only at eight finite forward-progress phase
boundaries. The full scene regression returned in 12.4 seconds without those
extra checkpoints. All phases restored a healthy prompt/cores, Vulkan and
watchdog-off state, then released the board. No reset, flash or emulator.
Normal counted build 332 compiles, but was not installed; resident build 328
is unchanged. The broader emulator-based gates were not run on this bench.
