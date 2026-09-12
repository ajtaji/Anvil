# The boot says which part of itself is running, on the panel and in DRAM

`PCI Express .....` and `USB host (xHCI) .....` are two lines in the boot log
and about twenty distinct pieces of work behind them. Several touch a bus that
can stall rather than answer. Until 2026-09-11 all of them produced the same
picture when something went wrong in a way the driver could not describe: a
label, its dots, and no result.

This document is what the phase markers are, why they also go to a fixed
address in DRAM, and how to read one back.

## Why a driver that refuses properly still needs them

`RaspberryPi4/Lib/xhci.pi4` bounds every wait it makes, on `CNTPCT_EL0`, and
every failure it can have is a code with a sentence behind it
(`XhciErrorText()`). `pcie.pi4` does the same. So a board that stops inside
either **with no sentence** is not a failure those files can describe. It is the
machine wedging on an access - and the only thing that can say where is a marker
set *before* the access, never a code returned after it.

## What the RAM twin proved, and what it could not

A build-75 twin entered into DRAM from a running build 55 reached the last xHCI
phase and answered its own console. So nothing a second monitor can reach is
broken. What a twin **cannot** reach is everything a cold flash boot does and it
does not:

- **The PCIe cold path.** A twin finds the link already trained and adopts it -
  three register writes and out. A cold boot may take the full sequence: PERST,
  the SerDes out of IDDQ, the control registers, the inbound BAR, MSI masked,
  PERST released, and up to 100 ms of link polling.
- **The whole screen service.** The firmware would not give the twin the DSI
  power domain, so `gScreen` was 0 and `BannerClockTick`, `ScreenPump` and the
  keyboard composer all returned at their first line. That matters because
  **`BootStep()` calls `ScreenServiceTick()` after printing its label and before
  the work the label names** - so a board that wedges in that tick shows a label
  with no result, which is exactly what a board that wedges in the work shows.
- The firmware-handed entry state, and DRAM that no previous program has
  touched.

The markers cover all three, and the record separates the screen service from
the work.

## The phases

| group | code | meaning |
|---|---|---|
| configuration half | `$0001` / `$0002` | begun / finished |
| boot step | `$02nn` | step *nn* printed its label |
| boot step | `$07nn` | step *nn* is inside `ScreenServiceTick` |
| boot step | `$04nn` | step *nn* is doing the work its label names |
| PCI Express | `$05pp` | `canary probe adopt inbound perst serdes control train window up busnum endpoint ok` |
| USB host | `$06pp` | `clock arena config registers reset slots rings run ok` |

The xHCI words in order, and which can wedge:

| word | what is running | can it wedge? |
|---|---|---|
| `clock` | `CNTFRQ_EL0` | no |
| `arena` | arena base and the 3 GiB reachability test | no |
| `config` | PCI config: id, bus master, BAR0 | yes, the config window |
| `registers` | **the first read through the PCIe outbound window** | yes - a read with no completion stalls rather than aborting |
| `reset` | halt, HCRST, CNR | yes, same window |
| `slots` | the enabled slot count | same window |
| `rings` | rings, contexts, ERST, scratchpad - DRAM only | no |
| `run` | `CMD_RUN`, wait for HCHalted to clear | same window |

A completed step reads as one line:

```
  PCI Express ......... canary probe adopt inbound up busnum endpoint ok
  USB host (xHCI) ..... clock arena config registers reset slots rings run ok
```

A wedged one ends at the word for the piece it was doing.

## The record that survives the reset

A word on the panel needs the panel to still be serviced and somebody watching;
it survives nothing. So every marker also goes to a fixed address.

**`$001FB000`, one 64-byte line**, declared in `RaspberryPi4/Board/memmap.pi4`
and argued there against the same four tests the autoboot record at `$001FF000`
is placed by: no image size can reach it (the image grows up from `$00200000`),
the monitor's stack cannot reach it (`#MON_STACK` is `$00100000` and grows
*down*), `_start` cannot erase it (it is not BSS - BSS is at `$08200000`), and
its address does not move, which is the whole requirement a record read by a
*different* image has. It is the page below a band that is already spoken for -
`$001FC000..$001FEFFF` is the raw-secondary stack reserve, `$001FF000` the
autoboot record - so it extends a reserved run downwards instead of planting a
lone page in the free band. It is region 6 in `HwMonRegion*()`, so `w`, `fill`
and `copy` refuse it.

```
+0   magic "ANVPHASE" ($414E565048415345), written once per boot
+8   the phase this boot has reached
+16  the phase the PREVIOUS boot reached, carried across at MonPhaseBegin()
+24  how many boots have written this record
```

`MonPhaseMark()` does one store and one `dc civac` and nothing else: an
instrument must not be able to become the fault it is looking for. The
maintenance is not optional - this monitor can run with caches on, and a record
still sitting in the D-cache when the machine wedges never reaches DRAM.

**DRAM survives a reset and does not survive a power cut**, and the record says
which happened rather than leaving the reader to guess: a missing magic means
the contents are not a previous boot's.

### Reading it back

The next boot does it for you. `MonPhaseReport()` runs at the top of
`BootConfigUp()` - after the screen and touch are up, before anything that can
wedge - and prints

```
!! the previous boot did not finish this half. It stopped at: USB host: registers
   (phase record at $001FB000; 3 boots have written it)
```

It is **silent** when the magic is absent (a power cut, or a first boot), when
there is no previous phase, and when the previous boot finished - three
silences, each a real answer rather than noise on every cold boot.

By hand, from any monitor:

```
m 1fb000 32
```

Thirty-two bytes, little-endian: the magic reads `ESAHPVNA` in the ASCII column,
then this boot's phase, the previous boot's, and the boot count.

## The frame rule, for this whole path

Four shapes that used to work became defects on 2026-09-11, and this path is
where they would hurt most because it is the one part of the monitor that hands
addresses to a bus master:

1. **A local's address handed to the controller.** A ring, a TRB, a descriptor,
   a mailbox property buffer or a command block built in a frame and given to
   hardware. The CPU-side view stays perfect; the controller reads or writes
   memory the next call has already taken back.
2. **Inline assembly naming a local.** The compiler refuses this outright.
3. **A local read before it is written.** It used to hold the previous call's
   value and now holds zero.
4. **Recursion.** It used to overwrite one set of static slots; it now costs a
   frame per level.

`tools/usb_frame_safety_check.py` refuses all four over the ten files of the
path and - given a `-S` listing - proves three facts about every frame in the
image: each slot lies inside its own frame, each frame is 16-byte aligned, and
no loop leaks the stack it pushes. Three negative controls.

The path is `xhci.pi4`, `hid.pi4`, `pcie.pi4`, `usbmsc.pi4`, `mailbox.pi4`,
`dma.pi4`, `cursor_input.pi4`, `hw_usb.pi4`, and - because the record exists to
be read by a different image after a reset, where a marker in a frame would be
wrong in the one direction nobody could check - `memmap.pi4` and `boot.pi4`.

### Two distinctions the gate encodes on purpose

`usbmsc.pi4` builds its sixteen-byte CDB in a procedure-local array and passes
`@cdb[0]` to `msc_Command()`, which **copies** those bytes into the file-scope
CBW before any transfer starts. Nothing outside the CPU ever sees the frame, so
that is correct; a call that forwarded the pointer to `XhciBulkOut()` would be
the real defect, and the gate lists the sinks so it can tell the two apart.

`mailbox.pi4`'s property buffer is `mbxBuf`, file-scope, and always was - which
is why the VideoCore may hold its address across a call. A property buffer built
in a local would now be a frame the firmware reads after the call that made it
has returned. **Anvil issues no VL805 firmware load of its own**: the VideoCore
firmware loads it before Anvil runs, and `RPI_FIRMWARE_NOTIFY_XHCI_RESET`
appears in this tree only in a comment.

## What only the board can settle

Which word it stops on. Everything here is structure and simulation.
