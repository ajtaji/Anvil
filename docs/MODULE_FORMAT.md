# PMFMOD v1 format and placement boundary

PMFMOD v1 is a little-endian AArch64 container. The fixed 160-byte header is
followed by image bytes, zero padding to an eight-byte boundary, fixed 16-byte
relocation records, and one to eight fixed 64-byte compatible-id records. The
canonical constants are in `Anvil/Hal/module_format.pbi`; compiler writers and
loaders must consume a byte-identical copy of that file rather than maintaining
their own numeric tables.

The SHA-256 digest covers the complete container except header bytes 96..127,
which hold the digest itself. This detects accidental or malicious damage in
transit. It does not authenticate a publisher, establish trust, or sandbox
native code.

Compatible IDs contain 1..63 printable ASCII bytes followed by NUL and an
all-zero tail. Space is allowed; slash and backslash are forbidden so an ID
cannot be interpreted as a path. IDs in one container must be unique.

The current engine validates exact layout, ABI/architecture/flags/reserved
fields, entries, matches, relocation sites/targets/opcodes/ranges, and digest
before it changes the arena. CALL26 targets must be aligned instructions inside
the emitted image; data relocations may target image or BSS but not the gap
between them. Relocation destination spans may not overlap.

## Board-owned placement contract

Before including `Anvil/Core/mod_arena.pbi`, a board composition must provide:

```text
HwModArenaBase()            ; 4 KiB-aligned first byte, or 0 for "no arena here"
HwModArenaBytes()           ; byte length of a reserved, guarded range
HwModArenaRegion()          ; which HwMonRegion* index IS the arena, or -1
HwModStageAddr()            ; where one container is read and judged
HwModStageBytes()           ; the largest container this board accepts
HwModCodeSync(base, bytes)  ; clean D-cache/invalidate I-cache; return 1
```

The range must be disjoint from the live image, BSS/data, payload/staging
windows, DMA/display buffers, firmware reservations, and every other owner.
`ModArenaInit()` now **checks that rather than trusting it**: it walks the
board's own `HwMonRegion*()` list and `HwPay*()` windows and refuses an arena
that overlaps one, skipping only the index the board names as the arena's own
region. The obsolete Pi range `$08A00000..$091FFFFF` is the DSI framebuffer and
is rejected by that check, not only by a paragraph. A board that offers no
arena answers 0 and gets `#MOD_ERR_NOARENA`, which is a different sentence from
a misaligned one.

`ModArenaInit()` is cold-start-only; calling it again is refused because
forgetting READY records would amount to an unsafe unload.

Loading is transactional with respect to allocator and record state: all
preflight/allocation/source-overlap checks happen before destination mutation,
and a relocation or cache-sync failure commits no bump pointer or READY row.
An uncommitted destination span can be written and then cleared during such a
failure, so it must remain private arena memory.

## The board also declares its devices

A module states what it is FOR, in digest-covered compatible ids. The board
states what is PRESENT:

```text
HwDevCount()        how many devices the board will name
HwDevIdAddr(i)      a NUL-terminated ASCII compatible id
HwDevSeam(i)        the #SVCCAP_* group it belongs to
HwDevToken(i)       the handle a driver needs - a register base, on a
                    memory-mapped part
HwDevSay(i)         prints the device's own name, in the board's words
HwSeamCore(id)      does the core reach this seam with no module at all
HwSeamPossible(id)  is the hardware here, whether or not anything reaches it
```

Matching an id against that table is core arithmetic and carries no board
knowledge. The token is what removes the last hard-wired address from a
converted driver: the module reads its registers from what it was handed.

## What the loader does now

Discovery, matching, lifecycle and service publication are implemented; see
`docs/MODULE_PIPELINE.md` for the states, the refusals and what is proven.
Reload is still unsupported, and unload strands the arena it used: the
allocator has no free list, and handing that memory to a later module would
put it where a stale pointer still names. A future reload design requires
stable core trampolines, in-flight call accounting, driver quiescence, and an
atomic group swap; changing a record pointer is not safe when callers may
retain function pointers.
