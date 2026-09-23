# The screen comes up first, and the boot log paints as it is printed

## The order, before and after

Before, in `RaspberryPi4/Board/board.pi4`:

```text
ScreenEarlyLogStart()      mirror on; nothing can paint yet
Banner()
BootConfigUp()             PCIe, xHCI, USB devices, boot medium, SETTINGS.TXT
TimeBoot() / NtpServiceBoot()
ScreenUp()                 the glass exists from here
TouchBoot()
V3dConAutoStart()
ScreenEarlyLogFinish()     the queued lines are painted, all at once
BootNetUp()                the radio
```

After:

```text
BootTimingBegin()          the retained record starts
ScreenEarlyLogStart()      mirror on, transcript armed, live painting armed
Banner()
ScreenDsiEarlyCacheArm()
ScreenUp()                 THE GLASS EXISTS HERE, on the defaults
TouchBoot()
ScreenServiceTick()        paint whatever the pre-screen lines queued
BootConfigUp()             PCIe, xHCI, USB, boot medium, SETTINGS.TXT - ON THE PANEL
ScreenApplyStoredGeometry() the store exists now; correct the geometry in place
TimeBoot() / NtpServiceBoot()
V3dConAutoStart()
ScreenEarlyLogFinish()     transcript frozen, live painting off
BootNetUp()                the radio
```

## The argument the old order made, and why it no longer holds

`boot.pi4`'s header put the configuration first and said so plainly: the screen
is configured hardware, so a screen brought up before the settings store exists
could only come up in a default and would have to be **torn down and rebuilt**
when the real answer arrived - "erasing the boot log it was brought up early to
carry." It also stated the cost it accepted: "the USB and boot-medium lines now
reach the wire before the glass exists, so they are not on the panel."

Every clause of that is true. The conclusion followed from two facts that are no
longer facts:

1. **A geometry change is no longer a teardown.** `ScrDsiReadoptBegin` writes a
   complete display list into the HVS's other fixed slot and re-installs the
   drawing surface. No panel power, no reset, no DSI host setup, no clock, no
   pixel valve, no allocation - the panel never stops scanning. See
   `SCREEN_DSI_READOPTION.md`.
2. **The boot log no longer lives only on the glass.**
   `Anvil/Core/boot_transcript.pbi` retains the byte stream the console was
   built from, so a grid rebuilt at a new geometry is restored from WHAT WAS
   SAID rather than from pixels that are the wrong shape.

So the cost that paragraph accepted is paid back: USB enumeration and the boot
medium are the longest thing before the radio, and their lines are now on the
panel as they happen.

**The network is still last**, which is what the original ordering really
existed for: it is the long, hang-prone half, and a board that stalls in the
radio says so on the glass.

## The common case costs nothing

`SETTINGS.TXT` on this bench names no rotation, so `ScrRotWanted` answers the
default the screen already came up with, `ScrScaleWanted` answers the computed
magnification the screen already came up with, and
`ScreenApplyStoredGeometry()` returns having touched nothing: no display list,
no grid rebuild, no replay, no print.

## Progress is painted as it is printed

`uart.pi4` calls the registered mirror drain at a line boundary and at the
ring's high-water mark. For the whole life of the board after boot that has to
be a pure drain - a long synchronous command produces far more than the 8 KiB
staging ring, and painting per line would repaint the console once per line of a
screenful, which is exactly what `ScreenPump` exists to avoid.

During the boot log the opposite is required, and it was asked for in those
words: the earliest possible screen with live progress on it. A boot that
collects sixty lines and shows them when the prompt arrives is a board that
looks hung for the time it takes to enumerate USB.

`ConMirrorDrain` (`RaspberryPi4/Board/console.pi4`) is the one place that
decides, the window is opened by `ScreenEarlyLogStart` and closed by
`ScreenEarlyLogFinish`, and outside it the behaviour is byte for byte what it
was. The callback runs INSIDE `UartWrite`, so it carries a re-entry guard: a
renderer that printed a refusal would otherwise come straight back into it.

**What this costs is measured, not assumed.** Painting per line during boot is
work the old order did once at the end, and on a turned panel a scroll is a full
repaint. That is precisely what the retained timing record is for: the delta
between `console live` and `network started` is the price of live progress, and
`BOOT_TIMING_RECORD.md` says how to read it.

## Restoring from retained state, never from stale pixels

`ScreenRebuildAtGeometry` is the shared composition tail. It re-binds the
blitter, clears, draws the banner, sizes the console rectangle, rebuilds the
grid, registers the CPU/DMA renderer, walks `BootTranscriptAt(0 .. Count-1)`
straight into `ConGridPutc`, resets the keyboard's layout, and presents the
whole surface once.

- **The replay goes into the grid, not through the ring.** The transcript is
  taken in `ConDrainRing`, which is below `ConGridPutc`, so replayed bytes are
  not captured a second time and a later geometry change cannot double the log.
- **There is no cursor to resume from.** Replay starts at byte zero every time,
  so a rebuild that failed half way clears the grid and walks again.
- **The whole surface is presented once.** The banner band is not part of the
  grid, so a per-row present would leave the anvil dark.
- **The keyboard's rectangles are invalidated.** They were derived from the old
  surface and every one of them is now a guess - the same statement
  `TouchKeyboardPayloadResume` makes about a surface a payload had.

## The two screens are different contracts

| | DSI panel | HDMI |
| --- | --- | --- |
| who owns the surface | this monitor - fixed addresses it chose | the firmware |
| rotation | 0/90/180/270, stored, default 90 | always 0; `ScrRotPick` says so whatever the store says |
| how a stored geometry is applied | `ScrDsiReadoptBegin` re-points the HVS at its other fixed display list; two-phase, because the block latches at a frame boundary | `ScreenHdmiRescale`: `DisplayScale` and a redraw. No display list, no re-adoption, no transpose |
| what may not appear in its path | `DisplayInit`, `DisplaySelect`, `DisplayStandardTags`, `ScreenPixelOrder`, `DisplayCount` | `HvsFlip*`, `ScrTranspose`, `#MON_FB_*`, `DisplayAdopt` |

A stored rotation that reaches the HDMI path is refused with a full sentence and
the magnification is still applied, because the two are separate statements and
dropping the second would be a silent half-refusal.

`tools/screen_composition_check.py` enforces the table above, both directions,
with mutants.

## When the display controller does not take the list

The HVS latches a newly selected display list at a frame boundary, so at this
panel's 60 Hz the answer is due within about 17 ms. The boot path waits 500 ms -
thirty frames - and then gives up loudly.

**Giving up cannot mean forgetting.** `SCALER_DISPLIST0` has been written and
the block may latch the staged slot at any later frame. So `HvsFlipAbandon`
rewrites the staged slot to describe exactly what the ACTIVE slot describes -
same framebuffer, same size, same mirror bits - which makes the two slots
identical and the outcome of a late latch irrelevant. Nothing is rolled back,
because there is nothing the hardware would let us roll back, and DISPLIST is
deliberately not pointed back at the old slot: that would be a second request
racing the first.

The software geometry was never changed while pending, so putting the old
renderer back is putting the console back to what the panel is actually
scanning.

## Validation

```text
python tools/boot_display_order_check.py
python tools/boot_v3d_order_check.py
python tools/screen_composition_check.py
python tools/display_pipeline_check.py
PMF_COMPILER=... PMF_A64_INTERP=... python tools/screen_restore_emitted_check.py
PMF_COMPILER=... PMF_A64_INTERP=... python tools/boot_timing_emitted_check.py
PMF_COMPILER=... PMF_A64_INTERP=... python tools/boot_transcript_emitted_check.py
PMF_COMPILER=... PMF_A64_INTERP=... python tools/screen_readopt_emitted_check.py
python tools/screen_readopt_check.py
```

The first four and `screen_readopt_check` are structural source proofs. The rest
compile and execute the shipped bodies on the project's A64 model with counting
stubs for the surface, the renderer, the HVS and the timing record.

**None of this is a physical display proof.** What is still owed on the board:
the first-paint and console-live times read out of the record, the visual check
that the boot log scrolls on the panel as it is produced, and a `screen rotate`
at the prompt to exercise the re-adoption path with a person watching.
