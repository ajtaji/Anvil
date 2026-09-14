# Vulkan sampled-state integration proof — 2026-09-13

Public main commit `9aad9ea` adds one bounded combined-image-sampler state
record. Commits `a97c6f9` and `4e24052` update the two board diagnostics to the
new format capability and keep their deliberately unsupported descriptor case
hostile by using `STORAGE_IMAGE`.

## Desk proof

- Foundation: 184 checks, 144,184 interpreted A64 instructions, no MMIO; every
  format/image-format mutation in the focused run was red.
- Resources: 479 checks, 829,445 interpreted A64 instructions, no MMIO and no
  hidden processor clear.
- SPIR-V: 404 checks, 4,755,621 interpreted A64 instructions.
- Pipeline: 216 checks, 9,410,512 interpreted A64 instructions; all twelve
  sampled-state mutants were red.

The focused batch covers descriptor type and layout shape, pool type, write
type, sampled usage, descriptor layout, live image layout, record pitch/filter,
sampled image creation, and empty mip/layer image-view ranges.

## Pi 4 proof

The final candidate was built by the canonical command-line compiler from
public main through `4e24052`:

- container: 575,804 bytes;
- SHA-256:
  `177c3c3f4d17437f7cdf568b3df0707786c0c54a12eb11cf6f34fa04443c3c7f`;
- monitor: build 101, EL3, staging address `$00500000`;
- report: `$00596000`, both magics present, highest step 12;
- screenshot: 1280x800, capture sequence 4, DMA console, pixel SHA-256
  `715531a2bbd059308f3e6b5dd9fef4226891632c1ef2d88065222e965cc3add2`.

All three visible-draw verdicts were zero. The diagnostic reported format
features `$81`, five mapped allocations, three successful submits and waits,
three bin and render jobs, no native error, no OOM, no MMU fault, an unchanged
guard, exact expected pixels, successful presentation and cleanup. The monitor
received and independently hashed the exact container, and returned to the
build-101 prompt. It was not flashed or reset.

The generic board runner still calls a nonzero returned `x0` a failure. This
diagnostic intentionally returns its report address in `x0`; its complete
magic/tail report and zero verdicts are the result.

## Claim boundary

This run proves that the sampled-state changes integrate without regressing the
existing V3D pipeline, uniform-buffer TMU lookup, mapping, fences, cache
visibility or visible presentation. It does not prove texture sampling. The
SPIR-V sampled-image types/instructions and V3D texture request are still
refused/not emitted and must be implemented and proved together.
