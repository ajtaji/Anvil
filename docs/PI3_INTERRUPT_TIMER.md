# Pi 3 architectural timer: desk-tested backend

`RaspberryPi3/Lib/interrupt_timer.pbi` owns core 0's non-secure physical
timer at EL2. This is not the BCM system timer, the separate QA7 local
countdown timer, or a GIC driver. It does not install vectors or unmask IRQs.
Cold boot does not call it yet.

Call `Pi3IrqTimerInit(periodTicks)` with a positive signed-32-bit period,
then `Pi3IrqTimerArm()`. `Pi3IrqTimerFrequency()` reports firmware's
CNTFRQ value, not a measured clock calibration. The caller must provide a
running architectural counter and identity/device-mapped local MMIO.
All operations require core 0, EL2 and DAIF.I masked, including calls from
an exception handler. Other cores and EL3 are deliberately refused.

`Pi3IrqTimerHandle()` takes no arguments and returns 1 only after the sole
reported IRQ is this timer and a future TVAL is programmed. Return 0 means
unrecognized, mixed, or unavailable IRQ: the exception dispatcher must not
pretend it acknowledged another device. `Pi3IrqTimerPending()` only inspects
state. Neither routine calls the scheduler. Late ticks coalesce into one
relative rearm; no unbounded catch-up loop is used. Very short periods can
expire again before handler return; choose a period exceeding service cost.

`Pi3IrqTimerStop()` disables the timer, clears only its IRQ route, and
releases ownership. Initialization refuses an already enabled timer or its
occupied IRQ/FIQ route; later route changes are not overwritten. This is
single-owner composition, not arbitration against concurrent raw MMIO users.

`Pi3IrqTimerError()` values: 1 wrong context; 2 invalid period; 3 busy;
4 unavailable frequency; 5 not initialized; 6 route ownership changed.

## Proof and remaining integration

Run `python tools/pi3_interrupt_check.py --compiler <unified-IDE-executable>`.
It compiles the actual Pi3 source and executes emitted A64 instructions with
explicit timer-register and local-MMIO models. The 57 checks cover routing,
rearm, stop, mixed IRQ refusal, ownership, invalid periods and unsupported
contexts. A wrong-routing mutation must fail. No board was accessed.
This does not prove interrupt electrical delivery, firmware counter setup,
vector/context-switch composition, or multicore scheduling on silicon.

## Architectural sources

The [BCM2836 QA7 specification](https://datasheets.raspberrypi.com/bcm2836/bcm2836-peripherals.pdf)
sections 4.6 and 4.10 define core-0 routing at 0x40000040 and source status
at 0x40000060: non-secure physical timer IRQ uses bit 1; FIQ bit 5 overrides
it. The [Arm register reference](https://documentation-service.arm.com/static/6166bf63e4f35d248467c9c0)
defines CNTP_CTL_EL0 and CNTP_TVAL_EL0. Writing a future timer value removes
the timer condition; the source register is not an EOI register.
