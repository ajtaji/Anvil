# The retained boot-timing record

On a Pi monitor containing this feature, type `screen timing` to read back what
the boot this monitor is running spent its milliseconds on. The command takes no
arguments. It touches no hardware at all: no mailbox, no panel, no display list,
no I2C, no framebuffer write. It is safe with the screen off and safe while a
payload's result is still in DRAM.

The record is also readable from a host with the memory command, which is the
path that works when the console is the thing being debugged:

```text
m 91FF000 2112
```

## Why it exists

"The banner was slow" is not a measurement. The record is a fixed table of
`(event, tick)` rows written as the boot happens and left in DRAM afterwards, so
the question "where did the seconds go" is answered by reading the board rather
than by watching it. A board that hangs in the radio still carries the complete
record of everything up to the hang.

**Painting into memory and presenting to the panel are separate rows.** On an
HDMI display, and on the panel at 0 and 180 degrees, the buffer drawn into IS
the one being scanned and the gap between the two is nothing. At 90 and 270 the
gap is the transpose. Reporting one and calling it the other is how "first
paint" gets claimed for a picture nobody could see.

## Where it is, and why that address is safe

`$091FF000`, the last 4 KiB page of the 8 MiB DSI framebuffer window
`#MON_FB_LO .. #MON_FB_HI` that `RaspberryPi4/Board/memmap.pi4` reserves. That
window holds two 4,096,000-byte surfaces and 96 KiB of documented slack:

| range | owner |
| --- | --- |
| `$08A00000 .. $08DE7FFF` | `#MON_FB_SCAN`, what the HVS scans |
| `$08E00000 .. $091E7FFF` | `#MON_FB_DRAW`, what a turned console draws into |
| `$091E8000 .. $091FFFFF` | spare - the record's page is the last 4 KiB of it |

Every requirement a retained record has is already true of that page, and true
because the DISPLAY owns the window:

- **The address cannot move.** It is arithmetic on a constant in `memmap.pi4`,
  not on the image size and not on a BSS layout. A NoClear global's address
  moves whenever anything above it changes size, so a host reading a record back
  after a reflash would read the wrong address, silently.
- **`_start` cannot erase it.** It is not BSS.
- **A payload cannot land on it.** The window is outside both payload windows,
  so `InPayload()` refuses it.
- **`w`, `fill` and `copy` refuse it.** `HwMonRegion` 3 already names the whole
  window, so no new reserved region had to be declared for this.
- **Nothing else writes it.** `BootTimingClearOfSurfaces()` is that claim as
  arithmetic rather than as a sentence, and the gate executes it.
- **It is non-cacheable by construction.** `CacheEnable()` maps the whole window
  Normal Non-Cacheable in one range for the display's sake, and this page is
  inside it; before `CacheEnable()` the D-cache is off entirely. A mark is in
  DRAM the instant the store retires, MMU on or off.

The clean to the point of coherency is still done, through the same primitive
the autoboot record uses. If the page ever stops being covered by `CacheMapNc`,
the record goes on being correct instead of going quietly stale - and a stale
timing record is worse than none, because it looks like a measurement.

## The layout

All fields are 64-bit little-endian.

### Header, 64 bytes at `#BTM_BASE`

| offset | field |
| --- | --- |
| 0 | magic `$454D4954544F4F42` - "BOOTTIME" |
| 8 | layout version, currently 1 |
| 16 | architectural counter frequency in Hz (54,000,000 on this part) |
| 24 | rows written |
| 32 | rows the table can hold (64) |
| 40 | rows refused because the table was full |
| 48 | guard: `magic XOR count XOR hz` |
| 56 | the tick the header itself was stamped at |

A reader must check the magic, the version, the row capacity, the count range
AND the guard. A magic on its own is met by any DRAM that happens to hold eight
bytes, and by a half-written record carrying the previous boot's count.

**The zero every row is measured from is row 0's own tick**, not offset 56 -
offset 56 is stamped a few instructions earlier, while the header is being
written, and is there so a host can see what writing the header cost.

### Rows, 32 bytes each, starting at `#BTM_BASE + 64`

| offset | field |
| --- | --- |
| 0 | event id |
| 8 | architectural counter tick |
| 16 | value 1 |
| 24 | value 2 |

**The row is written and flushed before the count that names it.** The other
order publishes a count for bytes that have not reached DRAM, which a host reads
as a row of stale memory.

**A full table counts what it refused rather than wrapping.** A wrapped table of
a boot's first seconds is a table of its last seconds wearing the same header;
the beginning is the half worth keeping, because that is where a hang shows.

### The event ids

These are a wire format. Add at the end; never renumber.

| id | event | values |
| --- | --- | --- |
| 1 | monitor entered; port adopted, ARM clock raised, counter proven moving | v1 = measured ARM Hz |
| 2 | screen bring-up entered | |
| 3 | which screen decided | v1 = source |
| 4 | DSI panel lit and scanning (DSI only) | |
| 5 | firmware handed over a framebuffer (HDMI only) | v1 = width, v2 = height |
| 6 | drawing surface installed | v1 = base, v2 = pitch |
| 7 | cached MMU on over it | v1 = 1 when the caches came on |
| 8 | blitter bound | v1 = 1 when the DMA engine started |
| 9 | **INTO RAM**: whole surface cleared | |
| 10 | **INTO RAM**: banner drawn | |
| 11 | **ON THE PANEL**: first whole-surface present returned | v1 = rotation, v2 = magnification |
| 12 | console live; every later boot line paints as it is printed | v1 = columns, v2 = lines |
| 13 | USB, boot medium and settings started | |
| 14 | USB, boot medium and settings done | v1 = boot medium mounted |
| 15 | stored geometry differs from the default; moving to it | v1 = rotation, v2 = magnification |
| 16 | stored geometry live and the boot log replayed | v1 = bytes replayed, v2 = bytes lost |
| 17 | touch controller done | |
| 18 | GPU console activation done | v1 = 1 when the GPU owns the console |
| 19 | network started | |
| 20 | network done | |
| 21 | first prompt | |

Ids 15 and 16 appear only when `SETTINGS.TXT` names a rotation or a
magnification that the default bring-up did not use. On this bench the store
names neither, so they are normally absent - and their absence is the statement
that the default was already right.

## Validation and limits

```text
PMFC=<pmfc> PMF_A64_INTERP=<a64_interp.py> python tools/boot_timing_emitted_check.py
```

It compiles and EXECUTES the shipped bodies on the project's A64 model, with the
DSI window constants taken from `memmap.pi4` so the address under test is
derived the way the product derives it. 46 assertions and ten separately
compiled mutants: the record landing on a scanout surface, a count published
before its row, a guard that stops tracking the count, a table that wraps,
uncounted overflow, a mark appended to a record that was never started, a row
past the count read as data, a changed row stride, a foreign layout version
accepted, and a prompt recorded on every command line.

The cache clean, the architectural counter and the printing leaves are stubs.
This is emitted execution, not a physical timing measurement: it proves the
record is a truthful container, not that any particular boot is fast.
