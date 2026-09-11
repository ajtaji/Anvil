# The xHCI step says which part of itself is running

`USB host (xHCI) .....` is one line in the boot log and seven pieces of work
behind it. Three of those touch a bus that can stall rather than answer. Until
2026-09-11 all seven produced the same picture when something went wrong in a
way the driver could not describe: a label, its dots, and no result.

This document is what the phase markers are, why a driver carries them at all,
and what the words mean on a panel.

## Why a driver that refuses properly still needs them

`RaspberryPi4/Lib/xhci.pi4` bounds every wait it makes. The halt, the reset, the
Controller Not Ready wait, the run, every event-ring wait: each takes a deadline
from `CNTPCT_EL0` and returns `xh_Fail(<code>)` when it passes. Every failure the
file can have is therefore a code with a sentence behind it
(`XhciErrorText()`), and the boot log prints that sentence.

So a board that stops inside `XhciInit()` **with no sentence** is not a failure
this file can describe. It is the machine wedging on an access - and the only
thing that can say where is a marker set *before* the access, never a code
returned after it.

The accesses that can do that, in order:

| phase word | what is running | can it stall? |
|---|---|---|
| `clock` | `CNTFRQ_EL0`, before anything that waits | no |
| `arena` | the ring arena's base, and the 3 GiB reachability test | no |
| `config` | PCI config space: the id, bus master, BAR0 | yes - the config window |
| `registers` | **the first read through the PCIe outbound window** | yes - a read with no completion stalls here rather than aborting |
| `reset` | halt, HCRST, Controller Not Ready | yes - all three are MMIO on that window |
| `slots` | the enabled device slot count | on the same window |
| `rings` | rings, contexts, ERST, scratchpad - DRAM only | no |
| `run` | `CMD_RUN` and the wait for HCHalted to clear | on the same window |

A completed step reads as one line:

```
  USB host (xHCI) ...... clock arena config registers reset slots rings run ok
```

A wedged one ends at the word for the piece it was doing, with no `ok`. That is
the whole point: the last word on the panel names the access.

## The shape, and why it is this shape

`xhci.pi4` carries a file-scope phase marker and an optional hook:

```
XhciPhase()            the phase, as a #XHCI_PH_* code
XhciPhaseText(p)       the word for one
XhciSetPhaseHook(*fn)  install a handler, get the old one back; 0 removes it
```

`RaspberryPi4/Board/cursor_input.pi4` installs `UsbPhaseWord` for the duration of
the boot step and removes it immediately afterwards, so nothing prints on the
lazy path a `usb` command takes later.

**The hook takes no argument.** That is `genet.pi4`'s progress-hook shape, which
this tree has run on silicon; the handler reads the phase back through
`XhciPhase()`. An indirect call with arguments is newer ground and a boot
instrument is not the place to break it in.

**The marker is file-scope storage, not a local**, and that is the rule this
whole area is now written under. Automatic storage lives in the invocation's
frame as of 2026-09-11: it is gone when the call returns and zero when the call
is entered. A marker whose entire job is to survive the call that set it - and
to be readable by a hook running underneath it - has to live on a layer that
outlives the frame. Same rule, same reason, as the cache walk's bounds in
`dma.pi4` (`docs/DMA_CACHE_WALK.md`).

## The frame rule, for this whole path

Four shapes that used to work became defects on 2026-09-11, and the USB host
bring-up is where they would hurt most because it is the one part of the monitor
that hands addresses to a bus master:

1. **A local's address handed to the controller.** A ring, a TRB, a descriptor
   or a command block built in a frame and given to hardware. The CPU-side view
   stays perfect; the controller reads or writes memory the next call has
   already taken back.
2. **Inline assembly naming a local.** The name would mean a different place on
   every call. The compiler refuses this outright, so it is a build failure and
   not a silent one.
3. **A local read before it is written.** It used to hold the previous call's
   value and now holds zero - a retry counter, a "have I done this" flag or a
   cached classification kept that way changes behaviour without changing
   source.
4. **Recursion.** It used to overwrite one set of static slots; it now costs a
   frame per level, which is a stack budget somebody has to have made.

`tools/usb_frame_safety_check.py` refuses all four over the real sources, and -
given a `-S` listing - proves three facts about every frame in the image: each
slot lies inside its own frame, each frame is 16-byte aligned, and no loop
leaks the stack it pushes. It carries three negative controls.

The path it covers is `xhci.pi4`, `hid.pi4`, `pcie.pi4`, `usbmsc.pi4`,
`mailbox.pi4`, `dma.pi4`, `cursor_input.pi4` and `hw_usb.pi4`.

### One distinction the gate encodes on purpose

`usbmsc.pi4` builds its sixteen-byte CDB in a procedure-local array and passes
`@cdb[0]` to `msc_Command()`. That is **not** a defect, and the gate says so by
listing the sinks rather than banning the address: `msc_Command()` copies those
bytes into the file-scope CBW before any transfer starts, so nothing outside the
CPU ever sees the frame. A call that forwarded the pointer to `XhciBulkOut()`
instead would be the real thing, and the gate refuses that.

## What only the board can settle

The words themselves. Everything above is structure and simulation; which word
the panel stops on is a fact about silicon and it takes one boot to get.
