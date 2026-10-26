# Current Neon line contract on Pi 4 - 25 October 2026

Eight physical GPU frames exercise the immediate and bulk line paths at 0,
90, 180 and 270 degrees. Each contains eight opaque white segments over a
known clear: horizontal and vertical lines in both endpoint orders, a
single-pixel degenerate line, shallow and steep diagonals, and a reversed
diagonal. All 131,072 captured BGRA bytes match the independent rational
pixel-center oracle. Each logical frame contains 173 white pixels. Twenty
report/pixel/truncation mutations are rejected by the checker.

The oracle specifies a line's width as the named pixel: a horizontal line
at y covers row y and excludes its far endpoint, a steep line analogously
covers column x, and a degenerate line covers one pixel. Rational arithmetic
intersects pixel centers with the specified strip, independently of clip
coordinates, triangle emission, lookup tables and the GPU output. These
inputs avoid rasterizer boundary ties. This proves these eight inputs and
both paths at every rotation, not all possible clipped lines or outline
joins. No production renderer was changed for this proof.

The older native golden remains untouched. Its two line/outline scenes
predate the intentional 14 October pixel-placement change, so their prior
mismatch remains recorded rather than relabeled as native parity.

Build using the unified compiler:

```text
python tools/build_neon_line_contract_proof.py --compiler <PureMetalForge.exe> --out <directory>
```

The normal returning board runner stages the whole hash-verified PMF at
01000000, uses stack 04F00000 and a 15-second deadman. Main returns zero.
Read E1C00000:8192 and E2400000:131072 with at most 16 KiB per read.
The public builder produced the exact same whole PMF as the hardware run.

```text
python tools/neon_line_contract_proof_check.py --report docs/evidence/neon-line-contract-pi4-20261025/report.bin --pixels docs/evidence/neon-line-contract-pi4-20261025/pixels.bgra --self-test
```

Resident monitor build 328 returned in 6.5 seconds. Prompt and cores were
healthy after the run, the Vulkan console was restored, the watchdog was
disarmed and the board lease released. No reset, flash, monitor replacement
or emulator occurred. Initial checker authoring incorrectly expected zero
from DisplayLastError; the documented #DSP_OK value is one. The corrected
checker checks that actual success code; no payload or captured data changed.
This is a Neon proof milestone, not completion of the entire port or Vulkan.
