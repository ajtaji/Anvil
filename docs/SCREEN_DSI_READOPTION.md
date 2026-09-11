# DSI live geometry re-adoption

`ScrDsiReadoptBegin` changes only the drawing-surface geometry and the HVS
plane mirrors of an already scanning DSI pipeline. It never repeats panel
power, reset, initialization, DSI host setup, pixel-valve setup, or allocation.
HDMI continues through its single firmware allocation path; it has no
re-adoption at all, because the firmware owns its surface and only the
magnification can differ (see `EARLY_DISPLAY_BOOT.md`).

The HVS update is deliberately two-slot. Linux builds a new display list,
writes `SCALER_DISPLISTX`, and recognizes completion only after
`SCALER_DISPLACTX` names that list (`rpi-6.12.y_vc4_hvs.c:1151-1174,
1248-1345`; `rpi-6.12.y_vc4_crtc.c:838-861`). A bounded timeout is therefore
PENDING, not rollback: the HVS may still adopt the requested slot later. Both
fixed slots remain immutable and screen rendering remains suspended until
`ScrDsiReadoptResolve` observes the candidate active.

Rotation 180 uses both HVS mirror bits and continues to scan the fixed
800-by-1280 `MON_FB_SCAN` surface. Its logical drawing surface is also SCAN;
the renderer applies no second rotation, while the established touch inverse
accounts for the scan-out mirror. Rotations 90 and 270 draw into `MON_FB_DRAW`
and use the existing transpose presenter. Every transition away from 180
explicitly clears both mirror bits.

The requested adopted tuple is validated before DISPLIST is changed.
`DisplayAdopt` and the preflight call share `DspValidate`, so the post-confirm
install applies the same immutable tuple and cannot acquire a new external
failure.

## Giving up, and why it is not a cancellation

A bounded caller that runs out of patience cannot simply forget the request:
`SCALER_DISPLIST0` has already been written and the block may latch the staged
slot at any later frame. Forgetting it would leave a picture that can change
shape on its own, minutes later, with nothing in the software describing why.

`HvsFlipAbandon` therefore REWRITES the staged slot to say exactly what the
active slot says - same framebuffer, same size, same mirror bits. The two slots
become identical and it stops mattering which of them the hardware ends up on.
Nothing is rolled back, because there is nothing the hardware would let us roll
back, and DISPLIST is deliberately NOT pointed back at the old slot: that would
be a second request racing the first, and the block would still be free to latch
either.

`ScrDsiReadoptAbandon` clears the pending flag and returns what the HVS half
returned, so a caller that cannot even do this much hears about it. The software
geometry was never changed while pending, so `ScreenDsiReadoptAbandon` putting
the old renderer, drain and pointer back is putting the console back to what the
panel is actually scanning.

## The integration

`ScreenApplyStoredGeometry` (`RaspberryPi4/Board/screen_cmd.pi4`) is the one
caller. It is invoked from `Main` immediately after `BootConfigUp`, which is
where the settings store first exists, and it returns having touched nothing
when the store names the geometry the screen already came up with - the normal
case on a board whose `SETTINGS.TXT` says nothing about the screen.

When it does act, `ScreenDsiReadoptService` rebuilds an empty grid at the final
geometry through the shared `ScreenRebuildAtGeometry` tail, which replays the
retained boot transcript into that grid and presents the whole surface once.
V3D activation is after the replay, for a reason a gate enforces: a geometry
correction re-installs the CPU/DMA renderer, so a GPU that took ownership first
would be detached again one line later.

## Validation

```text
python tools/screen_readopt_check.py
python tools/screen_composition_check.py
PMF_COMPILER=... PMF_A64_INTERP=... python tools/screen_readopt_emitted_check.py
PMF_COMPILER=... PMF_A64_INTERP=... python tools/screen_restore_emitted_check.py
```

The first two are structural. The third executes the actual mirror/pending/
late-adoption bodies and all sixteen surface transitions; the fourth executes
the restoration paths against the shipped transcript, with fourteen mutants
covering an unreplayed log, a resumed replay, an unrebuilt grid, an unpresented
surface, a stale keyboard layout, painting across a pending switch, a forgotten
display list, a console left without a renderer, and both directions of the
DSI/HDMI contract crossing.

None of these is a physical display proof.
