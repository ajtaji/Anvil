# Pi 4 Vulkan descriptor/TMU proof — 2026-09-13

## Result

The Pi 4 V3D backend now fetches a fragment colour from a Vulkan uniform-buffer
descriptor on silicon. The same run also proves the interpolated varying and a
second vertex-buffer binding. This closes the red descriptor/TMU gate recorded
in forum bug topic 790. It does not claim any descriptor type, shader operation
or format outside the compatibility table.

## Defect and owning-layer repair

The previous fragment program encoded the general-load configuration as if the
regular operation were zero, added `WRTMUC` to the address launch, and placed
the thread switch on a following instruction. The first descriptor render then
timed out while an ordinary varying shader continued to work.

The repair is in the V3D shader emitter, where the protocol is owned:

- the configuration is `$FFFFFF00 | (15 << 3) | 4 = $FFFFFF7C`, selecting a
  regular per-quad vec4 load;
- the address launch is the ADD-side OR-move from `rf8` to `TMUAU`;
- that launch instruction itself carries `THRSW`;
- two architectural delay slots precede four `LDTMU` reads; and
- no `WRTMUC` signal is added, because `TMUAU` consumes the configuration
  sideband and a second consumer would displace the following TLB word.

Mesa's `ntq_emit_tmu_general()` and `emit_tmu_general_address_write()` were the
primary semantic witnesses for the operation field and the TMUAU sideband.
py-videocore6's independently assembled, silicon-used general-vector load was
the encoding witness for the ADD-side TMUAU move with `THRSW` on the launch.
The desk gate compares the complete 64-bit launch word against
`$3C20318DB6836200`; it does not trust the production emitter to decode itself.

This is an emission-site fix. There is no peephole or post-generation rewrite.

## Desk gates

The baseline pipeline gate passes 183 properties over 9,359,319 interpreted
A64 instructions with MMIO stopped. It independently checks the eighteen QPU
instructions, shader record and three-word fragment stream. Focused mutants
must turn the gate red when either:

- the TMU configuration omits the regular-operation field; or
- the launch incorrectly adds `WRTMUC` as another uniform-sideband consumer.

The Pi 4 diagnostic is also built by that gate. It captures the exact shader
record and stream even when the first submit fails, so a future timeout keeps
its owning evidence.

## Silicon gate

Monitor: build 101, reached through the UDP console at the wired bench link.
The monitor was safely rebooted before this run so the candidate began with
clean V3D state.

Returning payload:

- file size: 567,436 bytes
- SHA-256: `44bdfed7d9f7bbc96e474e9954dce146938df3b0f5827c2306cb605f7be61ee4`
- compiler SHA-256:
  `bf5fde44797d3f561aa8cc442493fd2a938d01f046f2c02cd1001167c993e01e`
- load address: `$00500000`
- hardware deadman: 15 seconds
- report: 512 bytes at `$00595FA0`
- evidence: `_work/vulkan-tmu-20260913/clean-v3d/`

The complete report proved:

- status A/B/C: 0, 0, 0;
- exact magenta descriptor colour for pass A;
- exact expected gradients for passes B and C;
- pass B/C worst distance, over-tolerance and difference counts: all zero;
- bin jobs 0 to 3 and render jobs 0 to 3;
- all submit and wait results: zero;
- backend native error, OOM count and MMU fault count: zero;
- guard sum before/after: `$C0E6C000` / `$C0E6C000`;
- present and display verdicts: one;
- final layout: `TRANSFER_SRC_OPTIMAL`;
- draw count: 3 and shutdown reached: 1;
- shader record: `$067D5000`, fragment-program length: 144 bytes;
- fragment stream: `$067D3000`, `$FFFFFF7C`, `$FFFFFFFF`;
- descriptor-lowering verdict: 1; and
- highest step: 12, report length: 512, both end magics intact.

Report slot 96 is 5 by design. It counts the deliberate invalid API calls that
the diagnostic requires to be refused; it is not a V3D or MMU fault counter.
The four named refusal slots are all nonzero. The generic board runner also
labels the nonzero `x0` as a process failure, but this diagnostic deliberately
returns its report address in `x0`; the payload returned normally and the
monitor prompt survived. Its screenshot warning is the separately recorded
capture-sequence defect, not a renderer failure.

## Recovery rule

After any V3D render timeout, do not evaluate another candidate in the same
engine lifetime. Reboot through the monitor and confirm the monitor version and
prompt before staging exactly one new candidate. `NeonShutdown()` cannot prove
it restored an engine whose control list never completed, so a later result
without a reset is contaminated evidence.

The retained recovery image is
`_work/anvil-usb-detail-20260912/anvil-build55-known-good.img`, 2,700,352 bytes,
SHA-256
`5378ce4d1737157ce4285687da6506b35182431cabcfcc4e3b85804f9d270408`.
This tranche did not flash or replace the monitor image.
