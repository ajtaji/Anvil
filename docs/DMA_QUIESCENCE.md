# Legacy DMA completion and quarantine

Desk-tested correction; no hardware run or cold-boot causality claim.

## Architectural finding

BCM2711 ARM Peripherals Table 38 describes CS.WAIT_FOR_OUTSTANDING_WRITES:
with a zero next control block, ACTIVE can clear while final write responses
are pending. END is deferred until the responses arrive. Table 45 DEBUG bits
7:4 count outstanding responses, but **RESET clears that count**. Thus neither
ACTIVE alone nor a zero counter observed only after reset proves safe reuse.

This applies to the legacy full-feature channels this library supports
(0, 2, 4, 5, 6). LITE and DMA4 are not silently treated as this engine.
Primary reference: [BCM2711 manual](https://datasheets.raspberrypi.com/bcm2711/bcm2711-peripherals.pdf),
Tables 38/45 and section 4.4. The [Linux driver](https://github.com/torvalds/linux/blob/master/drivers/dma/bcm2835-dma.c)
also pauses and waits for outstanding writes before reset. Implementation is
original; no Linux code was copied.

## Contract

`DmaWait` succeeds only with END, no ACTIVE/WAITING and no outstanding writes.
Hardware errors and timeouts take checked recovery. Invalid public durations
(outside 1..2147483647 microseconds) also recover before returning failure.
The duration multiplication uses the 32-bit frequency range without overflow.
A working nonzero architectural counter owns the deadline; unavailable clock
uses the finite spin fallback. A stopped but nonzero counter remains outside
this clock contract.

`DmaAbort` and `DmaChannelReset` pause the selected channel, prove its writes
drained, reset, then verify quiescence before clearing sticky flags. A failed
drain does not reset away the evidence. Failure latches `DmaQuarantined()` and
error -20, clears ready, and prevents configuration rebinding or submission.
Only explicit successful checked recovery releases that latch; `DmaInit`
does not silently release it. `DmaQuiescent()` is a current status query, not
a replacement for the sticky ownership state.

Display CPU fallback cannot bypass quarantine by disabling acceleration.
Framebuffer drawing/readback/cache-flush paths refuse; readback preserves its
-1 error sentinel. Presentation, overlay and cursor boundaries are guarded.
Payload-return reset failure suspends mirroring/rendering instead of claiming
CPU drawing is safe. The serial console reports the condition.

The contract covers this selected-channel library and cooperating display
callers. It cannot constrain arbitrary code holding raw pointers, another
bus master, an unresponsive MMIO bus, or a hostile payload programming DMA
to overwrite unrelated RAM. No claim of whole-machine recovery is made.

## Desk proof

`python tools/dma_quiescence_check.py --compiler <unified-IDE-executable>`
compiles the actual library and display include closure. An independent MMIO
timeline presents ACTIVE low before final write completion, stuck ACTIVE,
stuck outstanding responses, hardware error and failed reset. It checks
quarantine, rebinding refusal, invalid timeouts, blocked display operations,
explicit recovery and a positive CPU drawing control. Restoring ACTIVE-only
completion must violate the modeled final-response boundary.

No full monitor build or board reset was performed by this lane. Board-level
integration and silicon acceptance remain separate gates.
