# Pi 4 DSI cache-map ownership

`CacheEnable()` now maps the complete board-reserved
`#MON_FB_LO .. #MON_FB_HI` DSI window as Normal Non-Cacheable before building
the page tables. This is independent of the adopted drawing surface: the HVS
scan surface and the sideways draw surface therefore remain coherent with CPU,
DMA, and V3D access at every rotation and through display-source changes.

The existing adopted `DisplayBase()/DisplaySize()` mapping remains in place for
the firmware-owned HDMI framebuffer. The GENET RX mapping and cache-enable boot
timing are unchanged.

`tools/cache_map_emitted_check.py` compiles and executes the real
`CacheEnable()` mapping path and `MmuBuildTables()`. Its isolated fixture stubs
the buildability predicate, aligned table-base provider, three display accessors,
and final hardware-enable operation; the mapping policy and table builder are
the product procedures. It checks all four emitted 2 MiB DSI descriptors,
immediate neighboring ordinary RAM, GENET, and an initially selected HDMI
framebuffer across rotations 0/90/180/270. A same-execution DSI rebind calls
`CacheEnable()` again while `gCacheOn` remains set and verifies both surfaces
remain NC after the real idempotent no-op. Dynamic HDMI rebinding while caches
are already enabled is not claimed or tested by this correction. Six
memory/fetch guard teeth use the exact linker-reported BSS extent. A separately
compiled scan-only mutation must fail,
proving the second fixed surface is not covered accidentally by the current
adopted display.

This is desk-only evidence. It does not prove cache, DMA, HVS, V3D, or display
behavior on BCM2711 silicon; no board operation or deployment was performed.
