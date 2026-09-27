# Pi 4 vertex register-placement diagnostic

Each PMFBOOT v2 payload below ran from RAM at `$600000` on monitor build 210,
returned `x0=0` after 9.2 seconds, and produced the accompanying captured
PNG and board-run JSON. A 15-second deadman guarded every run; none wrote to
the boot medium or reset the board.

| Capture | Payload | Arithmetic | Input words | Temporary placement | Visual result |
|---|---|---:|---:|---|---|
| 92 | `tenops12.img.pmf` | 10 | 12 | Above input registers | Clean |
| 93 | `tenops14.img.pmf` | 10 | 14 | Above input registers | Sparse black pixels |
| 94 | `reuse-vpm.img.pmf` | 10 | 14 | RF10..13 after input fetch | Clean |
| 95 | `inplace.img.pmf` | 10 | 14 | RF10..13; dying operands reused in place | Clean |

The ten-operation shader in these trials adds an exact zero to the Y result;
that extra operation does not change the geometry. Capture 93 uses the same
calculation as 94 and 95. The runs isolate register placement as the source
of the visual artifact. The final twelve-operation three-coordinate shader is
saved one directory above, with clean capture 97.
