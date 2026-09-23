# Initial xHCI readiness: desk finding, not a proven cold-hang cause

The running board's successful boot and the intermittent failure are separate
observations. A successful 13.7-second USB/settings interval includes PCIe,
xHCI initialization, HID/device enumeration, mass-storage readiness, FAT and
settings. It does not locate the failed operation. No reset or board write was
performed by this desk lane.

## Reproduced source violation

Before this change, `xh_Reset()` called `xh_Halt()` and wrote HCRST without
waiting for the controller's **incoming** USBSTS.CNR to clear. Its CNR wait was
only after that reset. An emitted fixture with initial HCHalted=1 and CNR=1
recorded one premature USBCMD write (870 instructions). This violates the
initialization rule in [xHCI 1.2 section 4.2](https://cdrdv2-public.intel.com/625472/625472_xHCI_Rev1_2b.pdf).

The source now gates `xh_Halt()` through `xh_WaitReady()`, using the existing
counter-based 250 ms reset timeout and `XHCI_ERR_CNR` refusal. `XhciStop()` also
honors reset failure before accessing runtime registers; otherwise cleanup
could issue the write which initialization just refused. It clears software
ready state on entry. No watchdog, forced retry or silent reset substitution
was added.

## Evidence

`python tools/xhci_initial_readiness_check.py --compiler <pinned-unified-IDE>`
executes the actual deadline, expiration, initial-ready, halt, reset and stop
procedures. Only counter ticks and register responses/writes are modeled.

- Never-ready: bounded failure, CNR error, **zero register writes**, not ready.
- Delayed-ready: readiness clears before the first operational write; succeeds.
- Initially ready: normal reset/stop succeeds.
- Deleting the initial gate and ignoring cleanup failure are both rejected
  mutants, preserving the original defect as a regression case.

PASS: 81,837 emitted instructions, three cases and two rejected mutants.
Pinned compiler SHA256:
`f6dd60b332a4eab4150bc45ff7cd825dbf6ad0757015ce10535dfe61640773d0`.
This does not model a stalled PCIe read, physical link training or an actual
VL805's initial CNR. It proves the software's readiness ordering, not that
this caused the reported intermittent hang.

## Separate unresolved concern

The adopt path rewrites the inbound PCIe DMA offset before halting the former
controller owner. If firmware left active bus-master transfers, their addresses
could be interpreted under a new window before quiescence. The current source
does not prove that the prior owner was stopped. This is an audit concern,
not a confirmed board condition or an implemented fix.

## Integrated build boundary

The current tree including HTTP and screenshot support built successfully
**before** this readiness fix, through `tools/build.py` and central counting:
ledger build 83, 2,752,748 bytes, SHA256
`cc037774593b3c8cdaa88c0e37776121728b708b871e5381a5b7fcdd2038cde3`,
compiler `171afd49dc7c964bdfca86de3c4e11e1d02458a16b13961d533368e47fc492e7`.
That artifact does **not** contain this later xHCI change. No new full-image
build or deployment was made for the fix; only the owning emitted fixture.
