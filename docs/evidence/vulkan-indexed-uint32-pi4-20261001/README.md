# Pi 4 UINT32 indexed-draw proof — 2026-10-01

The bounded `vkCmdDrawIndexed` diagnostic passed on Pi 4 silicon using a UINT32 index buffer. The selected indices are words 1–3 of the guarded buffer (`2, 0, 1`): the public bind uses byte offset 8 and `VK_INDEX_TYPE_UINT32`, while `firstIndex = 1` becomes byte offset 4 in the V3D indexed-primitive packet. The exact adjacent packet pair is present at BCL byte offset 138:

`2c08f07c061800000020840300000004000000`

The board returned report pointer `0xC4D2D0` in 5.5 seconds; the runner completed in 7.218 seconds. The 256-byte report records successful display presentation and teardown, two bin jobs and two render jobs, zero pixel-oracle mismatches, and zero reported faults. The index capture is 32 bytes and retains all six payload words plus both surrounding sentinel words.

Artifacts and SHA-256:

- `report.bin` — `A7F72DF20D2B56960898BD75EC41E4C1896F9636C8B67C04976A0C346AD28FDD`
- `bcl.bin` — `E96E207F59439988FDAA9014303046934684652E422087F6518DB4ED6FD2E6DF`
- `index-buffer.bin` — `34F6332E7D887D48BE0ADB47C50A08F13AD263EE9EEA12B725E80341E0E03BA7`
- Signed PMF — `C2694F0B110A527958CC7493FF5B9EF576A4B1CECB36D09DAEF1102F479F85C8`

The checker passes against these public artifacts and catches ten hostile mutations. Its slot-48 expectation is `1`, matching `#DSP_OK` in the display driver. The separate long emitted `--mutate` run was stopped without a result; no pass is claimed for it. This proves the bounded UINT32 diagnostic shape on Pi 4 only, not general Vulkan conformance or other-board GPU support.
