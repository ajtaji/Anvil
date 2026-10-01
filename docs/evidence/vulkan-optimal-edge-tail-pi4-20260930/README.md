# Pi 4 optimal-image readback edge-tail proof

The 1,056-byte `report.bin` has SHA-256 `E6F23C73A931429506A2121103D3C72445EB46EF1383F9C4613FAE4548721D91`. The executed PMF container had SHA-256 `5EE40B4904EC4AA72B9FA0DFF010CA80A9659A4C49F53D97A3E5444C066FF540`.

The returning payload reported `x0=0x9488D0` in 8.4 seconds. It uploaded a 37×13 optimal BGRA8 image through TFU (counter 0→1), then read the `(32,8)` region of extent `5×5` into a padded destination. All 25 requested texels matched; 15 padding words and 32 guard words remained intact. DMA advanced 0→4, backend jobs 4→5, and an inherited aligned-region readback passed. TFU advanced 1→7 and the V3D bin/render counters advanced 3→4. A non-edge `(28,4)` `5×5` request returned `-20005` without additional work. No MMU, out-of-memory or native faults were reported.

This is Pi 4 evidence for this bounded right-and-bottom edge-tail shape. Source offsets remain 4×4-utile aligned; each short width or height must terminate at its corresponding image edge. It does not prove aliasing or support on other boards.
