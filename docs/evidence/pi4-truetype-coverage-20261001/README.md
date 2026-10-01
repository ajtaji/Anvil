# Pi 4 TrueType coverage conversion

The signed Pi 4 RAM payload exercises `AnvilTrueTypeCoverageCountsToAlphaNeon` with 35 coverage counts at byte alignment residues 8, 0, and 1. Each conversion spans two 16-byte NEON blocks and a three-byte tail. It checks the exact alpha bytes, guards, return values, and rejection of an invalid final count without modifying the input.

Resident Anvil build 223 returned the expected report pointer at `$00800080` in 0.67 seconds. The 128-byte [report](report.bin) has SHA-256 `1C16047FF301CAB2930E2B542A744791435F0694CAD34A89592291D0392994F9` and passes `python tools/a64/a64_truetype_coverage_check.py --self-test docs/evidence/pi4-truetype-coverage-20261001/report.bin`.

The payload was linked at `$00700000`, with BSS `$00800000..$0080011F` and stack `$04F00000`. It used a confirmed 15-second deadman. The monitor returned to its prompt with the Vulkan screen restored. No boot image or storage was changed.

The diagnostic source is `RaspberryPi4/Examples/Diagnostics/pi4TrueTypeCoverageNeon.pi4`; the corrected converter is `Anvil/Graphics/truetype_raster_neon.pbi`. This proof covers Pi 4 execution of the converter, not a full-monitor boot of the newly compiled image.
