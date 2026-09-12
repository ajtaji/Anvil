# A board run, and the picture it comes back with

## The ruling

2026-09-11, after a payload ran four times and came back clean every time
while nothing reached the panel, and then drew a garbled frame:

> *"omg thats a garbled mess, you should build screen shots into the tests"*

So **every board run of a payload comes back with a picture**, and nobody has
to be watching the panel for that to be true.

## Why a picture cannot be taken afterwards

When a payload returns, the monitor prints. Printing goes through the console
grid onto the surface the payload left behind, so the frame being asked about
is destroyed by the monitor's own report that the payload returned - before a
prompt exists to type `p` at.

The frame therefore has to be copied out of the way **while it still exists**,
and read back from the copy. That is what the capture area is.

## The capture area

`RaspberryPi4/Board/memmap.pi4` declares it and argues its address at length.
In short:

| | |
|---|---|
| the area | `$0B000000 .. $0BBFFFFF`, 12 MiB |
| the header | `$0B000000`, one 4 KiB page |
| the pixels | `$0B001000`, 12,578,816 bytes |
| the magic | `$414E5653484F5431`, "ANVSHOT1" |

It is the first round megabyte above the V3D arena, which was the highest
thing this board had claimed, so it extends the reserved run upwards rather
than planting a region in a gap two other owners may want to grow into. It is
outside both payload windows, outside BSS, outside the framebuffer window it
copies FROM, and it is region 7 in `HwMonRegion*()` - so `w`, `fill` and
`copy` refuse it, which matters because a corrupted capture is a garbled frame
that reads as a display fault.

The size is set by the biggest screen this monitor brings up and not by the
panel: the DSI panel is 800 x 1280 x 4 = 4,096,000 bytes, this bench's HDMI
console is 1824 x 984 x 4 = 7,179,264, and a 1920 x 1200 mode would be
9,216,000. A capture larger than the window is **refused**, not truncated - a
short capture decodes as a torn picture and looks like a fault.

### The header

64-bit words in the first two cache lines of the header page. The logical pair
is what the picture is STREAMED as (the console's own coordinates, the same
numbers `p` puts in its `PIC` line); the physical trio plus the rotation are
what the bytes actually are.

| offset | word |
|---|---|
| +0 | the magic - **written last, cleared first** |
| +8 | sequence number, rises on every completed capture, never reset |
| +16 | logical width |
| +24 | logical height |
| +32 | pitch, physical bytes per row of the copy |
| +40 | rotation: 0, 90, 180 or 270 |
| +48 | tier: 0 cpu, 1 dma, 2 v3d |
| +56 | the payload's x0 (a capture on return) |
| +64 | physical raster width |
| +72 | physical raster height |
| +80 | bytes per pixel - 4, or the capture was refused |
| +88 | source: 1 HDMI, 2 DSI |
| +96 | who took it: 0 the payload asked, 1 the monitor took it on return |
| +104 | pixel bytes copied |

The magic is written last so that a reader which finds it is looking at a
complete capture, and cleared first so that an interrupted or refused one
reads as "there is no picture here" rather than as the previous run's.

### What is copied

The **presented physical frame** - what the panel is scanning. On this bench
the console is normally at 90 degrees: it draws into a 1280 x 800 buffer the
panel never scans and `ScrPresent` transposes the damaged band into the
800 x 1280 buffer the HVS reads. A capture of the drawing buffer would be a
picture of an intention, the same size and different bytes. On the V3D tier
there is no second case: the GPU presents its finished physical frame into the
same scan buffer.

## Two ways it gets filled

**The payload asks.** ABI 1.2 fills console slot 13,
`SvcScreenCapture()` - `#SVC_OK`, or `#SVC_EIO` when there is nothing behind
the console to photograph. Call it after `SvcFrameEnd`; it copies and does not
present. This is the only way a payload's own picture can be kept, because the
payload's frame does not survive its return.

**The monitor takes it on the way back.** `shot arm` arms one capture for the
next payload entry, and `boot mem <addr> shot` arms and boots in one line. The
copy is the FIRST statement after the payload returns, before a single
character is printed. The arm is one-shot: an arm that stayed set would
overwrite the picture somebody was still reading with the next run's, and the
next run is the one nobody was watching. A refused jump does not spend the arm.

## The console commands

| | |
|---|---|
| `shot` | stream the kept picture: one `SHOT` header line, then the same `PIC`/runs/`END` format `p` uses |
| `shot arm` | keep the frame the next payload leaves behind |
| `shot disarm` | put it back |
| `shot now` | keep the screen as it is at this instant |
| `shot status` | whether a capture is armed, and what is kept |
| `p` | unchanged: the LIVE screen |

The `SHOT` line is deliberately **not** part of the `PIC` stream.
`tools/pmfshot.py`'s three regular expressions are anchored whole-line and
cannot match it, so an existing host decodes the picture and ignores the line.

```
SHOT <seq8> <w8> <h8> <pitch8> <rot8> <tier8> <x0:16> <panelW8> <panelH8> <bpp2> <src2> <who2> <bytes8>
```

Upper-case hex, single spaces, fixed widths, one line - the same discipline
the `PIC` header is written under and for the same reason.

## The whole run, from the host

```
python tools/board_run.py <payload.pmf> --console-ip <board> [--out DIR]
    [--name NAME] [--board-ip A] [--console-port N] [--port N] [--addr HEX]
    [--tier dma|v3d|cpu] [--deadman S] [--trace HEX[:LEN]] [--timeout S]
    [--shot-timeout S] [--settle S] [--twin] [--no-shot]
```

One run is: ask the board where to stage (`map`); arm a one-shot listener and
stream the container (`net recv`); **prove it landed** by comparing the
board's own length and SHA-256 of the memory against the file on disk; pick a
renderer if asked; arm the deadman if asked; note the capture sequence number
(`shot status`); `boot mem <addr> shot`; wait for the return line and its x0;
read the payload's trace if asked (`memory`); read the picture (`shot`).

It writes `<name>.png`, `<name>.json` (x0, timings, the header, the digest of
the decoded pixels, the transfer verdict) and `<name>.txt` (the whole console
transcript) into the output directory, and exits **non-zero** if x0 is not
zero or if no picture came back.

`--twin` is for a payload that never returns - a monitor twin. Nothing special
happens: the same run, without waiting for a return line, and the picture is
whatever the payload kept for itself through the ABI slot.

### The two checks that make a picture evidence

**The run count.** The board counts the runs it emitted and says so in `END`;
a lost datagram takes runs with it and the two numbers stop agreeing. A
decoder that ignored the count would write a plausible PNG of a picture with a
band missing.

**The sequence number.** The capture area keeps the last picture until
something overwrites it, so a run whose capture silently failed would stream
the PREVIOUS run's picture - perfectly well formed. `board_run.py` reads the
number before the run and fails a picture whose number did not move. This is
the one failure a magic number cannot catch.

## The gates

| gate | what it proves |
|---|---|
| `tools/screen_shot_emitted_check.py` | the SHIPPED capture, rotation map, tier report and the whole of `RunAt`, executed over a modelled turned panel on both tiers; the header; that the copy is of the scanned buffer and not the drawn one; that the frame is kept before the first character is printed. Plus the capture area's placement, size and protection against `memmap.pi4`'s own constants, and the slot against `abi.pbi` and the Pi 4's `HwCon` seam. Thirteen mutants must be rejected, including one that repaints first and one that captures the logical surface on the turned panel. |
| `tools/board_run_parse_check.py` | `board_run.py`'s decoders against recorded `p` and `shot` streams, including four that must be refused. The live and kept streams must decode to the same pixels. |

## What only the board can prove

The gates execute emitted code over a modelled panel. They cannot show that
the bytes at `#MON_FB_SCAN` are the bytes the glass is lit with, that a real
12 MiB region is free on real silicon, that a 4 MB copy fits in the window
between a payload returning and the console repainting, or that a picture
survives the trip over UDP 5555. Those are board facts and they are owed.
