# Bulk geometry range preflight on Pi 4 - 25 October 2026

`NeonVkChromeLinesReserve` now compares its requested quad count against the
remaining capacity before multiplication. Positive 64-bit counts whose
six-vertex extent wraps can no longer become accepted negative or tiny spans.
`NeonVkChromeLinesDraw` requires a live frame without an active box/grid/path
builder, rejects negative arguments, and validates the complete draw span
against vertices already reserved in that frame before recording anything.
Valid subranges and a zero-length draw at the reserved end remain supported.
The raw vertex address/writer APIs remain caller-owned memory operations.

The before-source physical diagnostic accepted five overflowing reservations
and all four invalid draw spans: a negative start, start beyond storage,
range crossing the reserved end and overflowing count. It restores its private
cursor after each arithmetic observation and aborts the diagnostic command
before submitting anything to the GPU. It never writes an invalid address or
asks the GPU to read one. Those failures are preserved as negative evidence.

The corrected run refuses eight reservations (zero, negative, over-capacity
and five wrapping counts) and four draw spans. It checks unchanged vertex
and draw cursors, free command rows and Vulkan fault state. All 592 bytes
of marked storage/guard remain unchanged. Additional checks cover inactive
frame, active box batch, negative draw count and an empty end-range draw.
The next frame exactly fills its configured 24-vertex capacity, draws two
valid subranges and matches all 16,384 GPU bytes in an independently
constructed 64x64 BGRA oracle. Final teardown leaves zero memory allocations.
The strict checker rejects 65 report/pixel/truncation mutations and rejects
the unchanged-source report. This is bounded range validation, not evidence
of separate native flat/textured budgets or full Neon/Vulkan completion.

```text
python tools/build_neon_bulk_range_proof.py --compiler <PureMetalForge.exe> --out <directory>
python tools/neon_bulk_range_proof_check.py --report docs/evidence/neon-bulk-range-pi4-20261025/after-report.bin --pixels docs/evidence/neon-bulk-range-pi4-20261025/after-pixels.bgra --self-test
```

The public builder produces the exact complete PMF used for the corrected
physical run. Stage 01000000, stack 04F00000, BSS 011A0000..01FB95DF,
report E1C00000:8192, capture E2400000:16384. Main returns zero. Both physical
runs returned in 7.2 seconds with a 15-second deadman. Captures 129 and 130;
resident monitor build 328. Healthy prompt/cores, Vulkan restored, watchdog
off and board lease released after each phase. No reset, flash or emulator.
Normal counted build 333 compiles but is not installed. Payload identities
and exact artifact/source hashes are in manifest.json. Forum bug topic 1439.
