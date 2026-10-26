# Native point boundary through Vulkan on Pi 4 - 26 October 2026

Bug 1441: the adapter stopped a native-sized fan at 4,096 input points even with
262,146 GPU vertex slots and a 262,144 native flat input budget. End refused
before recording. Abort followed by a four-point fan rendered correctly.
The unchanged-source physical report is retained and the strict checker rejects
it as a full-boundary result, despite its correct fallback image.

The staging limit now derives from #NEON_MAX_VERTS (262,144), rather than an
unrelated 4,096 constant. Two signed coordinate arrays grow by 4,128,768 bytes
(3.9375 MiB). Actual GPU vertex capacity and independent flat/textured quotas
remain unchanged. This allows the full native input boundary without hiding
line/outline output expansion behind an arbitrary input cutoff.

The candidate accepts 262,144 points and emits all 262,144 vertices through its
real advertised triangle-fan pipeline. Every early triangle is degenerate;
only the final two triangles form the 24x24 rectangle. Thus the complete pixel
oracle catches truncation at 65,535 or any other earlier vertex boundary, rather
than merely trusting the reported count. This is maximum input/addressing
coverage, not a worst-case overdraw, binning-load or frame-rate claim.

An additional point after the full budget refuses without changing existing
vertices, records, free rows, input data or a 16-byte next-vertex guard. All 16,384
GPU bytes match the independent rectangle oracle and the four-point before
image. Teardown leaves zero live allocations. The public builder produces
the exact complete PMF run on hardware; 38 corrupt report/pixel/truncation
mutations are rejected.

The same input arrays now accept 131,072 two-point lines (262144 points). Their
current quad lowering would need 786,432 actual vertices, exceeding even the
adapter's maximum 393,216-slot buffer. End explicitly refuses before writing
any vertex or record, preserves its16-byte buffer guard and is followed by
clean Abort. That separate line/outline storage requirement remains OPEN;
this result is not described as complete native capacity parity.

The larger variable layout also passes the full current 15-scene regression:
all 245,760 GPU bytes and 124 widget checks remain exact. Historical line/outline
differences from the older native golden remain preserved and explicit.

```text
python tools/build_neon_native_points_proof.py --compiler <PureMetalForge.exe> --out <directory>
python tools/neon_native_points_proof_check.py --report docs/evidence/neon-native-points-pi4-20261026/candidate-report.bin --pixels docs/evidence/neon-native-points-pi4-20261026/candidate-pixels.bgra --self-test
```

Before returns 0 in 8.3 seconds, capture 140; final candidate returns 0 in 12.3 seconds, capture 142.
The preliminary fan-only candidate also passed in 11.4 seconds, capture 141; it is
workspace evidence, not the final line-staging/refusal proof. Finite watchdog
checkpoints separate staging, emission and submission phases; no whole 15-second
acceptance claim. Full regression returns 0 in 13.0 seconds, capture 143. Stage 01000000,
stack 04F00000, candidate BSS 011A0000..023D164F,report E1C00000:8192,
capture E2400000:16384. The mode 1 fixture's 20 MiB heap 063E8000..077E7FFF and
mapped span 017E8000 remain in the recorded safe low-memory window; no slab
at 07000000 is used. Prompt/cores healthy,Vulkan restored,watchdog off, FREE.
No reset, flash or emulator. Counted build 337 compiles but is not installed;
resident 328 remains. The linked reservation covers the expanded variables.

The port target is Neon through Vulkan on Pi 4/Anvil. Desktop OpenGL sources
provide behavior references; this proof does not add a desktop Vulkan backend.
Broader line/outline geometry storage, resource/presentation recovery and
remaining Vulkan implementation stay open. No complete-port/conformance claim.
