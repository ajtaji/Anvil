# Resident cell-text service

Anvil ABI **1.16** appends eight slots at208..215; slot208 is
`SvcNativeText(operation, context, request, bytes)`. Earlier slots and signatures
stay in place. The table now has216 entries. Check the ANVS magic, major1,
minor>=16 and entry_count>=216 before reading slot208. Slots209..215 remain
reserved and answer ENOSYS. An older monitor or a target without a registered
text provider answers ENOSYS; a text grid does not advertise pixel CAP_CONSOLE.

The protocol declarations in `Anvil/Hal/text_service_api.pbi` are shared across
CPUs. All requests use eight-byte-aligned addresses in admitted payload memory,
native little-endian64-bit integer/pointer fields and the exact declared size.
Calls are synchronous, on the entry core, outside interrupt handlers, with one
caller. Anvil never calls back into the application. Managed strings, fixed
kernel addresses and raw device register addresses are not part of this API.

`QUERY(0, request, 40)` fills `NativeTextApi`: four u32 fields (magic NTX1,
major1, minor0, structure bytes40), followed by format1, maximum write/fill
cells4096, and the resident dispatch pointer. That pointer has the same four
arguments and lifetime guards as slot208. The query is also allowed outside an
active payload scope; all other operations require a services-backed payload.

Format1 cells are little-endian u32: a BMP code point in bits0..15, foreground
xterm256 index in16..23, background index in24..31. Palette indices use the
standard16 VGA colours,6x6x6 colour cube and24 greys. Missing glyphs draw the
device's replacement box. Cell coordinates start at zero. These are cells,
not pixels; query/open report the actual metrics. No device RAM or protected
monitor-buffer pointer is exposed.

| Operation | Context | Request fields (all64-bit) | Result |
|---|---|---|---|
| OPEN1 | 0 | output: columns, rows, cellWidth, cellHeight (32B) | positive session handle |
| WRITE2 | handle | x, y, width, height, cells, stride (48B) | 0 |
| FILL3 | handle | x, y, width, height, cell (40B) | 0 |
| CURSOR4 | handle | x, y, style (24B) | 0 |
| SCROLL5 | handle | top, bottom, lines, cell (32B) | 0 |
| PRESENT6 | handle | null, bytes0 | 0 after a new composed frame |
| CLOSE7 | handle | null, bytes0 | 0 |

OPEN clears the whole protected text capacity and hides the cursor. There is one session per payload
scope, and handles are never reused during that monitor boot. It is valid to
open input and text together. Monitor diagnostic output continues on serial
while the application owns text; it does not overwrite the application's grid.

WRITE copies a rectangle from a row-major payload cell array. Stride is in
cells and must be at least width. The complete source span, including row
padding, must fit admitted payload memory and be four-byte aligned. WRITE and
FILL each admit at most4096 cells; split larger updates into rectangles. The
whole request, rectangle and source span are validated before the first write.
Invalid requests fail, with no clipping or partial update. FILL/SCROLL cell
fields must fit unsigned32 bits. A cursor never advances as a side effect of
WRITE/FILL/SCROLL.

CURSOR style bits0..1 are hidden0, underline1, block2 or bar3; bit8 enables
blink, bits16..23 choose its half-period in display frames (zero means30).
All other bits must be zero. Coordinates must be inside the grid even for a
hidden cursor. SCROLL moves full-width rows in `[top,bottom)`, positive lines
up and negative down; uncovered cells receive the supplied cell. Lines must be
within plus/minus the grid height. Zero is a valid no-op. Temporary scroll
region/fill registers are restored before return; no font/mode/palette setter
or raw register access is supplied.

PRESENT waits for one new display frame using the qualified monitor timer/WFI
backend. It refuses an unavailable idle owner and is bounded by both250ms and
256 wakes. It does not consume keyboard events. An editor can poll native input,
apply its updates and call PRESENT, allowing the host to sleep between frames.
No unsupported vertical refresh rate is silently reported as success.

Changes to columns, rows or cell metrics return GEOMETRY on drawing/presentation.
Close and reopen to obtain the new layout. CLOSE remains available after such a
change. CLOSE and payload return clear the whole protected text capacity, home the cursor,
restore the monitor cursor and retire the session. Clearing the capacity, including
rows hidden by a display shrink, prevents old application text reappearing when
the grid grows. Requests using an old handle
fail STATE. An unreleased/corrupt hardware owner is quarantined; Zentaji stops
with0x5B05 before reusing foreign text/display state or printing a false prompt.
This remains a trusted supervisor ABI, not a malicious-code sandbox.

| Status | Meaning |
|---|---|
| -22500 ARGS | invalid operation/request/bounds/style |
| -22501 STATE | no scope/session or stale handle |
| -22502 BUSY | nested use or another live session |
| -22503 PROVIDER | hardware ownership or idle provider unavailable |
| -22504 GEOMETRY | current metrics differ from the session |
| -22505 UNBOUND | direct protocol dispatch has no bound provider |
| -22506 TIMEOUT | no new frame within the presentation budget |

The outer service slot maps an absent provider to the existing SVC_ENOSYS(-100).
Queries include no invented pixel capability. Current qualification uses the
real Zentaji backend with independent cell/status oracles, native/twin complete
RAM/CPU comparison, exact headless frames and actual booted PMF applications.
Other architecture backends can register this same contract; the existing ARM
compositions remain honestly unbound.
