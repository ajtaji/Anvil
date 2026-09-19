# BCM2711 combined-transfer receive qualification

`I2cWriteRead` changes an active BSC write into a read by programming the new
DLEN and queuing `READ|ST`. Its receive loop services FIFO only when status is
read-qualified: RXR during an active read, or DONE for the tail. RXD by itself
is deliberately insufficient at that one direction boundary. Ordinary
`I2cXfer` reads still service RXD directly because they start as reads and do
not turn the FIFO around.

This is narrower than saying that polling RXD is prohibited. The BCM2711
manual says RXD means the 16-byte data FIFO contains at least one byte and
permits reads when it is set. It describes RXR as occurring during a read
transfer, however. On build 34 hardware the Goodix transaction reported RXD
about 3.4 microseconds after the first TX milestone and about 1.1 microseconds
after `READ|ST` was queued. At 100 kHz that cannot be a newly addressed read
byte. A shared-FIFO turnaround is therefore the working explanation, not a
claim that the outgoing byte was directly observed.

The same physical trace ended with TA still set and recovery had timed out.
Its END `DLEN=6` is therefore not an idle-controller recall that can be
dismissed as harmless; it is only a post-recovery snapshot from a controller
that remained active. The pre-cleanup FAULT `DLEN=2` is the meaningful
in-transfer remaining count.

The Linux BCM2835 controller driver supplies the independent production
precedent: after its TXW-driven repeated-start switch, it drains receive FIFO
on RXR and on DONE. Anvil follows that event ordering in polling code; no GPL
implementation text is copied.

DONE validates both sides of the requested length. Too few bytes or residual
RXD is reported with the driver's existing `I2C_TIMEOUT` length-failure policy.
RXR without RXD is not progress and cannot reset the elapsed-time or spin
backstop. NACK and clock-stretch timeout remain higher-priority failures.

The emitted-code gate in `tools/a64/touch_emitted_check.py` executes the real
`I2cWriteRead` body. Its new focused cases check exact identity output through
a bounded transient unqualified RXD, reject a mutant that restores generic
RXD service, and exercise bounded RXR-without-RXD timeout. The surrounding
existing suite covers DONE-tail and RXR-threshold reads, NACK and timeout paths;
the separate boot-trace gate retains trace-on/off transaction equivalence.
These are desk fixtures, not physical touch acceptance; no reset, pin, panel,
or protocol change is implied.

Primary references:

- *BCM2711 ARM Peripherals*, Chapter 3, especially the C, S, DLEN and FIFO
  register descriptions and the repeated-start recipe in section 3.3.2.
- Linux `drivers/i2c/busses/i2c-bcm2835.c`, repeated-start state machine and
  ISR receive handling.
