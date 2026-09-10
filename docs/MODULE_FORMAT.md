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
HwModArenaBase()            ; 4 KiB-aligned first byte
HwModArenaBytes()           ; byte length of a reserved, guarded range
HwModCodeSync(base, bytes)  ; clean D-cache/invalidate I-cache; return 1
```

The board must prove the range is disjoint from the live image, BSS/data,
payload/staging windows, DMA/display buffers, firmware reservations, and every
other owner. The obsolete Pi range `$08A00000..$091FFFFF` is the DSI framebuffer
and is explicitly forbidden. `ModArenaInit()` is cold-start-only; calling it
again is refused because forgetting READY records would amount to an unsafe
unload.

Loading is transactional with respect to allocator and record state: all
preflight/allocation/source-overlap checks happen before destination mutation,
and a relocation or cache-sync failure commits no bump pointer or READY row.
An uncommitted destination span can be written and then cleared during such a
failure, so it must remain private arena memory.

## Deliberately outside this phase

This engine does not read files or manifests, discover devices, choose a module
for hardware, execute probe/init/quiesce wrappers, initialize module globals,
or publish service functions. Reload remains unsupported. A future reload
design requires stable core trampolines, in-flight call accounting, driver
quiescence, and an atomic group swap; changing a record pointer is not safe
when callers may retain function pointers.
