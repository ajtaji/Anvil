# Optimal-image upload edge tails on Pi 4

The 1,056-byte report is `report.bin`, SHA-256 `238356D12E2557D929B6762E0289A3D0AA73288DAD2804413AAD612A2DF43B29`. The frozen PMF payload SHA-256 is `F14B87C3FBAD9BAD854C24FAC5C572E011D0DEFB4F742FC98312703C28A4DCAE`.

The returning report pointer was `x0=0x8D90D0`; runtime was 2.8 seconds. The edge-tail upload changed 25 texels and left 196 valid texels untouched. It also preserved 291 padded UIF backing words outside the copy. The checks covered 246 source words, including 54 source-padding words, 91 readback-padding words and 92 guard words. For the isolated operation, TFU remained at 1, DMA advanced from 0 to 4 and backend jobs advanced from 1 to 2. A later readback advanced DMA from 4 to 24.

A non-edge 5×5 request returned `-20005` during recording before additional DMA. MMU, OOM and native fault counts were zero; one validation fault was intentional. Submit-time malformed-stream preflight remains desk-gate evidence, not a silicon result.

The first hardware run proves one bounded Pi 4 edge-tail upload: destination XY remains 4-aligned; short width or height is accepted only at the matching right or bottom image edge; the last UIF utile writes only its valid rows and bytes. It does not establish capability on another board.

## Two-call tiny-tail run

The second 1,056-byte trace is `two-call-report.bin`, SHA-256 `9714947846D3BB3512A5FE3CBBC59329AC00E710F5B251EE33A5BB18E75E42A7`. Its frozen PMF payload SHA-256 is `2BB6997FD6DC10DD0FEA60C6AEACACEFCFD47E6B79CAB050F636610D9E2C8604`.

The returning report pointer was `x0=0x8D90D0`; runtime was 2.7 seconds. Two ordered partial calls on a 13×13 image changed 17 texels and left 152 valid texels unchanged. The run preserved 343 padded UIF backing words outside the copied areas. It checked 186 source words, including 58 source-padding words, plus 39 readback-padding words and 112 guards. TFU stayed at 1, DMA advanced from 0 to 2, and backend jobs advanced from 1 to 3. A later readback advanced DMA from 2 to 18.

A non-edge second call returned `-20005` during recording before DMA. MMU, OOM, and native fault counts were zero; one validation fault was intentional. The malformed-second-call submit-preflight refusal is covered by the signed desk regression only, not by either silicon trace.
