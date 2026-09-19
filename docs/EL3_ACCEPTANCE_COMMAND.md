# Explicit EL3 acceptance command

`el3test` is an opt-in silicon diagnostic. It is never run during boot. It
briefly enables the secure physical timer IRQ and then executes one tightly
qualified BRK to prove exception entry and return.

## Requirements and ownership

The command requires core 0, measured EL3, all DAIF bits masked, the installed
exception VBAR and an available GIC/watchdog acceptance lease pair. It refuses
before mutation when those conditions do not hold or resident multicore owns
the pair. An unknown firmware watchdog owner remains a physical precondition;
the software lease can describe only Anvil's ownership.

Existing production GIC initialization is accepted only when the installed
context and handlers match. Unrelated disabled pending device lines are
preserved; enabled or active foreign ownership is refused. The secure timer's
own INTID29 claim remains exact.

## Timer proof

The timer half programs CNTPS and INTID29, admits exactly one interrupt through
the normal GIC dispatcher, stops the source in the accepted handler, then
observes long enough to reject a repeated-source storm. Counter and instruction
ceilings prevent an apparent success when time stops. Handler, comparator,
control, priority, claim and controller state are restored before the watchdog
and leases are released.

On builds 98 and 99 this delivered exactly one interrupt. The original boot state had
`SCR_EL3 = 0x5B1`, so INTID29 became pending and `HPPIR` reported 29 but IRQ
never reached EL3. The boot layer now masks DAIF first and retains
`SCR_EL3 = 0x5B3`. A binary gate checks both the route bit and ordering.

## Fault proof

The temporary vector accepts only slot 4, BRK immediate `0x531`, the exact PC,
AArch64 EL3h and all four exception masks under SPSR mask `0x3DF`. It consumes a
single-use token, records EL/slot/ESR/PC, advances only that known instruction
by four bytes and returns with ERET. Any mismatched slot, syndrome, PC, mode,
mask or replay remains fatal under watchdog recovery.

Build 98 recorded slot 4 and `ESR_EL3 = 0xF2000531`, restored the original
VBAR/DAIF and passed the complete command three times across warm resets and
once after a witnessed physical power cycle. Build 99 repeated the command
successfully after deployment.

## Results and regression gate

The two internal halves return 1 on success and negative values for unsafe
entry, occupied ownership, setup failure, failed proof or restoration failure.
Cleanup failure deliberately retains watchdog/lease ownership for controlled
restart.

```text
python tools/el3_acceptance_check.py --compiler <PureMetalForge executable>
```

The emitted fixture covers delivery, missing/frozen timers, storms, spurious
interrupts, production-like preinitialized GIC state, restoration failures,
bad fault evidence, token replay, SP and x19-x29 preservation, ownership and
negative code mutations. Device delivery in that fixture is modeled; builds 98
and 99 provide the corresponding silicon proof.

Builds 98 and final build 99 both have witnessed physical cold-power-cycle
acceptance. Build 99 returned with exact CRC, EL3 and cold/zero leases before
passing this command again.
