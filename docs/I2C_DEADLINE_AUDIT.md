# I2C deadlines and the cold-boot investigation

Desk result: a timing-policy defect is corrected in `RaspberryPi4/Lib/i2c.pi4`.
This is **not an established fix for the intermittent USB bring-up hang**.

Previously four waits expired on either an iteration budget or a wall-clock
deadline. That allowed CPU/loop cost to decide an earlier timeout despite a
usable counter. `I2cWaitExpired` now uses only the deadline when available;
the finite iteration fallback applies when CNTFRQ was unavailable. A nonzero
but stopped counter is outside this clock contract and needs an independent
clock to diagnose. The conversion now rounds `frequency * microseconds`
up after division, rather than discarding fractional MHz first. At 19.2 MHz,
20 ms is 384,000 ticks, not 380,000.

Error codes are unchanged. Recovery still disables the controller and
returns failure when TA remains active. `I2cEnsureIdle` refuses a new START
after failed recovery. No optimistic-ready fallthrough was found here.

## Reproducible desk proof

Run `python tools/a64/i2c_deadline_check.py --compiler <unified-IDE-executable>`.
The actual emitted source passes 48 assertions: exact boundaries at 19.2 MHz,
54 MHz and 32,768 Hz; exhausted iteration budgets before valid deadlines;
missing-frequency fallback; recovery at two model instruction costs; stuck
TA refusal without START. Restoring the old count-first policy is detected.
The existing `touch_emitted_check.run_timeout` regression also passes its
six checks, including unchanged timeout/NACK distinction and no escaped
read phase. Model instruction costs are not measured silicon timings.

## Why this does not identify the USB hang

`BootStep` and each USB phase callback call `ScreenServiceTick` after printing
their label. That service reads touch readiness from cached `gTouchUp`, not
the I2C bus. Its remaining work drains the console, draws the keyboard/clock
and animates the banner. Display rendering can perform DMA and framebuffer
cache maintenance, so a last visible USB label alone cannot distinguish
display work from the following PCIe/xHCI access. The existing phase marker
is written before the callback's rendering work.

An additional review finding, **not changed by this lane**: `DmaAbort` writes
ABORT and RESET without checking ACTIVE afterward, unlike `DmaChannelReset`.
A timeout therefore does not prove DMA has stopped before CPU fallback.
That is a separate safety gap, not evidence it caused this cold hang.
No board reset, flash or hardware test was performed by this lane.
