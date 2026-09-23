# Driver modules: discovery, activation and service publication

Not every board has the same hardware. A driver that is not on the path that
loads modules does not have to be compiled into the monitor: it can be a
`.MOD` file on the boot medium, verified against its own digest, placed in a
reserved arena, matched to a device the board declares, and asked to publish
the service it implements.

This document is the loader's half. `docs/MODULE_FORMAT.md` is the container's.

## The states, and what each one proves

A record is one module. It advances through exactly these states, each entered
from exactly one place, so a record can never be half-advanced.

| state | what it means | what it does **not** mean |
|---|---|---|
| `READY` | verified, placed, zeroed, relocated, cache-synchronised | nothing has looked at hardware |
| `MATCHED` | a device the board declares answers one of the container's compatible ids | the device is actually responding |
| `PROBED` | the driver looked at that device and accepted it, changing nothing | it has acquired anything |
| `ACTIVE` | init returned 0 and published at least one service | it is being used |
| `FAILED` | a step refused; everything it had published was withdrawn first | the bytes went away |
| `STRANDED` | unloaded cleanly; the arena it used is not reusable until a reset | the memory is free |

`READY` is the state the earlier checkpoint stopped at, and the distinction is
the point: verified bytes and a working driver are two different claims.

## The order, and why each step is where it is

1. **Read the manifest.** `MODULES.TXT` in the root of the boot medium, beside
   `SETTINGS.TXT`, read through the storage seam with the same rules the
   settings store uses: a UTF-8 BOM skipped at offset 0 and nowhere else,
   CR LF counted as one ending so a line number in a refusal is the line number
   an editor shows, `#` or `;` starting a comment. A line is a file name and an
   optional seam name. **A refused line stops the walk** and the lines after it
   are not read - acting on half a file is the confident wrong answer.

2. **Read one container into staging, never into the arena.** The digest covers
   the header, and the relocation table and the compatible ids sit after the
   image, so nothing in the file can be believed until all of it is present.
   Writing unverified bytes into the range live drivers occupy would do the
   damage the refusal was about to prevent.

3. **Validate everything before one arena byte moves.** Magic, version, ABI
   major and minor, architecture, flags, reserved words, exact layout, every
   entry offset, every compatible id, every relocation - site bounds, site
   alignment, target range, destination-span overlap, the opcode at the site -
   and only then the digest. A digest is never a substitute for structural
   validation: it proves the bytes are the ones somebody produced, not that
   what they produced is safe to place.

4. **Place it.** The arena is board-declared and **checked against the board's
   own reserved map**: `ModArenaInit()` walks `HwMonRegion*()` and `HwPay*()`
   and refuses an arena overlapping either. Allocation is a 4 KiB-aligned bump;
   the span is zeroed, the image copied, relocations applied, and the code
   caches synchronised unconditionally - the bytes arrived as a data copy, and
   that they needed no patching says nothing about which cache they sit in. Any
   refusal in this step commits no bump pointer and no record.

5. **Match.** Each compatible id in the container against each device the board
   declares, with the device's seam required to be one the module is still
   enabled for. No hardware is touched: comparing strings the board already
   holds is the whole of it.

6. **Probe, side-effect-free by contract and by enforcement.** The driver is
   handed the service table and the device's handle and answers positive to
   claim it. It **cannot** publish a service here: the registry's publish window
   is shut outside an init call, so a probe that tried would be refused and the
   driver would see its own failure. Declining is normal - an id that matched
   and silicon that is not answering is exactly what a probe is for.

7. **Initialise, exactly once.** The publish window opens for the duration of
   one init call. Init publishes through `SvcSeamFill` and returns 0. A second
   activation of an ACTIVE record is **refused without calling anything**, and
   the init count in `mod info` is what proves it: a loader that answered OK and
   did nothing would make a manifest listing a module twice look correct.

8. **Publish.** `SvcSeamFill(seam, index, fn)` refuses a seam the container's
   digest-covered header does not declare, a seam another module owns, a
   function index outside the seam's shape, and a null function. The header's
   seam list is therefore enforced rather than documentation.

9. **Use.** A consumer asks the registry for the function and calls it,
   bracketed by `ModSeamEnter`/`ModSeamLeave`. A consumer that intends to keep
   calling takes a **binding**, and supplies with it the procedure that releases
   it again.

## Unload, and why it is refusable rather than impossible

A filled pointer may have been copied anywhere and nothing is reference
counted, so the two easy answers are both wrong: "never unload" makes the
feature useless, and "always unload" strands live callers on memory about to
be reused.

The binding is the third answer. `mod unload` is refused while any binding is
held or while a call is on the stack inside the driver, and the refusal names
the seam, the count and the owners. `mod detach <seam>` closes the seam to new
use until its module is unloaded, then asks each owner to let
go - each falls back to whatever it used before the module was loaded - and
then the unload can act. Quiesce is allowed to say no: a driver that cannot put
its hardware into a safe state refuses, and the unload refuses with it, because
tearing a driver out over its own objection leaves silicon mid-transaction.

**The bytes stay put.** The allocator is a bump pointer with no free list, and
`mod` reports the record as stranded until a reset. Reload is not supported and
is not pretended: it needs stable core trampolines, in-flight accounting and an
atomic group swap.

## The failure paths all unwind

Every refusal after placement puts back what it took, in one order: the
permissions, then the published functions, then the state. Nothing can observe
a seam owned by a record that is not ACTIVE. The case that matters is a driver
whose init publishes a function and *then* fails: if the unwind is wrong, the
seam keeps answering, the consumer keeps calling a driver that said it could
not run, and nothing anywhere reports a fault. That exact case is a gate.

An init that returns 0 and publishes nothing is also a failed activation: every
later caller would find the seam empty and quietly fall back, so the module
would read ACTIVE and do nothing.

## The ABI, at 1.1

Core slots 14 and 15 were filled - `SvcSeamFill` and `SvcSeamGet` - and
`#SVCCAP_PWM` (14, reserved) and `#SVCCAP_THERMAL` (15) appended. The core group
had reserved sixteen slots and used fourteen, so `entry_count` is still 184 and
no existing slot changed meaning; that is what an `abi_minor` bump is defined
to be. A payload built at 1.0 finds every slot where it left it.

A module is refused by the loader before init if its major differs at all or
its minor is higher than the monitor publishes. A lower minor loads.

`Anvil/Hal/seams.pbi` is the published contract: the seam ids, the
function-index vocabulary per seam, the two slot numbers, and nothing else. A
module includes that file and no other Anvil file. If a module ever needs a
second one, the contract has leaked.

## The first converted driver

`RaspberryPi4/Modules/thermal_avs.pi4` is the BCM2711's own temperature
monitor. It matches `brcm,bcm2711-thermal`, fills the thermal seam's read
function, and **contains no address of its own** - the board hands it the
block's base as its second argument. The register facts, their device-tree
citations and the negative-slope trap moved with it out of
`RaspberryPi4/Lib/thermal.pi4`, which now asks the seam first and falls back to
the firmware property interface.

Build and install it:

```text
PureMetalForge.exe --compile RaspberryPi4/Modules/thermal_avs.pi4 -t pi4 --module -o THERMAL.MOD
```

then copy `THERMAL.MOD` to the root of the boot medium and add a line naming it
to `MODULES.TXT` (see `RaspberryPi4/Modules/MODULES.TXT`).

With it loaded, `fan` reports the temperature as coming from a sensor register
the board reads directly. Without it, the same command reports the firmware
property interface and everything still works - which is the property that made
the conversion safe to do with no board attached.

## What is proven, and where

`tools/module_pipeline_check.py` compiles the real driver with
`--compile --module`, mutates copies of the resulting container into the negative
cases, compiles the real Core and Hal sources against a modelled board and
medium, and runs the emitted A64 in the project's instruction interpreter.

It refuses: bad magic, an ABI minor too high, an integrity mismatch, an
overlapping relocation, an out-of-range relocation, an arena inside a reserved
region, an arena inside a payload window, no arena at all, a cache-sync
failure, a publish from outside an init, a manifest line narrowing to an
undeclared seam, and a second owner of a seam.

It proves: manifest discovery, device matching, a probe declining invalid
silicon, init exactly once, publication, use by the shipped consumer, unload
refused while bound, detach, clean unload, fallback after unload, failed-init
unwind, and the same container answering from two arena bases.

`tools/module_engine_check.py` remains the container/relocator gate and covers
all eight relocation kinds at two placements.

**Neither is a hardware claim.** There is no MMU, no cache, no DMA and no
firmware in either; the device register is interpreter RAM and cache
maintenance is a stub. Silicon acceptance is a separate, board-slot claim.
