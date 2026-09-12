# Adopted PCIe DMA ownership audit

Started as a desk-only audit on 2026-09-12. The ownership correction and the
ordered-MMIO access layer were subsequently built and exercised on the Pi 4.
See `docs/USB_HOST_BOOT_HANG_20260912.md` for the pinned upstream sources,
image hashes, emitted gates and five clean controlled resets.

## Original ordering (baseline f3d6ebb)

`RaspberryPi4/Board/cursor_input.pi4` calls `PcieInit`, `PcieEnumerate`, then
`XhciInit`. The trained-link branch of `RaspberryPi4/Lib/pcie.pi4:PcieInit`
programs the outbound window and changes RC BAR2's inbound DMA offset to zero.
It preserves the size encoding, but does not establish that the former DMA
owner has stopped. `PcieEnumerate` subsequently relocates the endpoint BAR and
enables memory decode and bus mastering. The first xHCI halt is later, inside
`XhciInitAt -> xh_Reset -> xh_Halt`.

A valid trained link is not evidence that the endpoint is idle. Changing the
translation while an old owner is active can change the destination of its
transfers. Whether the actual firmware leaves such an owner active remains
unmeasured.

## Executable reproduction

Run from the repository root:

```text
python tools/pcie_adopt_dma_order_check.py --compiler _work/xhci-gate-compiler/PureMetalForge.exe
```

The test extracts and compiles the real `PcieInit` and `PcieProgramWindow`
procedures. Fake RC registers provide a trained link and an existing nonzero
inbound offset. The two environments differ only in modeled former-owner
liveness; this is an explicit environmental input, not a hardware observation.

| Former owner | Return | Mapping changed while active | RC writes | Instructions |
| --- | --- | --- | --- | --- |
| Inactive control | Success | No | 7 | 945 |
| Active | Success | Yes | 7 | 957 |

The pinned baseline regression deliberately exits **1**, reporting the missing
quiescence proof. Compiler SHA256:
`f6dd60b332a4eab4150bc45ff7cd825dbf6ad0757015ce10535dfe61640773d0`.

## Required ordering proposal

1. Inspect the adopted configuration before modifying DMA translation or the
   endpoint BAR. Validate the existing BAR and bridge routing. Establish CPU
   access to that BAR without relocating the endpoint or changing its inbound
   DMA mapping. Refuse unsupported routing instead of guessing.
2. Wait for initial xHCI CNR to clear before operational-register writes. Clear
   Run/Stop and wait for HCHalted with a deadline. If readiness or halt fails,
   do not reprogram the inbound DMA mapping.
3. Only after HCHalted is observed, disable PCI bus mastering and verify the
   command state. Preserve unrelated command bits; do not accidentally write
   back RW1C status bits in the upper half of the configuration dword.
4. Once the old owner is halted and BME is read back clear, cross the ownership
   boundary through the BCM2711 bridge/PERST reset and link-retrain sequence.
   Invalidate every old BAR and DMA cache before publishing a new mapping.
5. After verified halt and completed remapping, restore bus mastering before
   controller reset/readiness. Install the monitor-owned DMA arena and rings
   before setting Run. Do not enable BME merely to discover the old BAR.

Use explicit takeover phases owned by the board orchestration or a narrowly
defined hardware-takeover layer; avoid introducing recursive PCIe/xHCI
initialization. The non-adopted cold-link path needs its own contract as well.
The implementation below follows these phases. A CPU load stalled by a fabric
transaction is not made bounded merely by putting a software timer around it;
the eventual correction was to use the ordered MMIO access contract present in
the upstream drivers.

## Primary evidence

[Intel xHCI Requirements Specification 1.2b](https://cdrdv2-public.intel.com/625472/625472_xHCI_Rev1_2b.pdf):

- Section 4.21.2, page 307: halt the xHC and verify HCHalted before clearing PCI
  Bus Master Enable. Clearing BME on a running controller can cause HCE.
- Section 5.4.1, page 358: HCHalted denotes completion of pending pipelined
  transactions and stopped state; do not assert host-controller reset while
  HCHalted is clear.
- Section 4.2, page 68: initial CNR must clear before operational or runtime
  register writes.

Therefore simply clearing BME first is **not** the proposed correction. These
requirements establish the xHCI ownership boundary; they do not establish
the actual firmware state on the user's board. No external implementation
code was copied.

## Implemented desk fix and proof

PcieInit on an adopted link validates the existing xHCI class, memory BAR,
bridge routing/decode and CPU window readback before exposing the temporary
register address. It preserves inbound DMA mapping. XhciQuiesceAdopted uses
local register addresses, waits for CNR and HCHalted, and only then disables
and verifies BME through PcieAdoptHalted. Failed readiness/halt/BME verification
does not permit reset or remapping. PcieEnumerate guards ownership, performs a
full bridge/PERST reset and retrain, then enumerates and verifies a fresh BAR,
the outbound window and bridge routing while programming the inbound window.
New controller bus mastering is
restored before the new driver's halt/HCRST path, matching U-Boot's xHCI PCI
probe. Run remains clear until the monitor's new rings are installed. Ordered
MMIO accessors provide an ordered Arm device-I/O contract. They are stronger
than U-Boot's minimum barriers: reads have a post-read barrier and writes have
both pre- and post-write barriers.

Both production callers, cursor_input.pi4 and storage.pi4, explicitly perform
handover. Boot output separates link, firmware handover and mapping; retained
xHCI phases distinguish old-register access, CNR, halt and DMA ownership.
No restart/watchdog was added by this ownership correction. Later diagnostic
images used a watchdog only to preserve the otherwise invisible stall phase.

Run tools/pcie_takeover_check.py with --compiler pointing to the pinned
compiler above: PASS seventeen emitted cases (ready, delayed ready, never ready,
never halted, failed BME readback, invalid routing with zero MMIO reads,
unguarded enumeration refusal, owned cold-path enumeration, explicit DMA-enable
error 44, adopted final-window write refusal, and direct cold-window helper
write refusal, three unsupported-BDF early refusals and valid-BDF acceptance).
Two added cases execute the actual InitAt reset-phase fragment with an explicit
controller model requiring BME before reset; removing the early BME enable
is rejected. This proves the ordering, not that disabled BME caused the board
hang. The BDF checks execute the actual initialization prefix, before driver/hardware
mutation. The cold-path case
models the post-cold-link state, **not physical link training**. Checks cover
premature DMA mapping/BAR probing/BME disable and status RW1C writes.

For the historical audit revision, the existing
tools/xhci_initial_readiness_check.py gate passed 84,581
instructions with three rejected mutants. RaspberryPi4/Tests/usb_takeover_compile.pi4
compiles all three complete libraries and the call sequence, producing a
43,780-byte fixture including the then-current firmware-notify integration,
SHA256 a615eb8bcd56dcbb9500918c6ee7565e48265be4c3eb4f9d732cd35fa757a7fe;
never execute this compile-only fixture on hardware. PcieProgramWindow itself
now verifies all five outbound fields and returns status; both production
callers check it. BME handover refusal reports error45, distinct from error44
when enabling the monitor's new DMA ownership fails.
A full-image comparison and five-reset silicon pass followed; see
`USB_HOST_BOOT_HANG_20260912.md`. A power-removal cold cycle remains owed.

## Reference-backed BME timing correction

The first takeover patch deferred BME until after reset and memory setup.
That differed from both the working earlier source and reference drivers.
The correction retains the protected mapping interval but restores BME before
the new driver's halt/reset path. U-Boot v2025.01 enables it in xhci_pci_init
before xhci_register, which calls the generic halt/reset path; Linux v6.12 sets
bus mastering before usb_add_hcd.
Sources: https://raw.githubusercontent.com/u-boot/u-boot/v2025.01/drivers/usb/host/xhci-pci.c
and https://raw.githubusercontent.com/u-boot/u-boot/v2025.01/drivers/usb/host/xhci.c
and https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/usb/core/hcd-pci.c .
No external implementation code was copied. This does not explain the earlier
build79 intermittent failure, which predates the BME timing change.
