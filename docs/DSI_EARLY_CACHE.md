# DSI first-paint cache policy

The boot path arms exactly its next `ScreenUp()` call. `ScreenUpOn()` consumes
that arm at entry, before any early return, so a failed/no-display boot cannot
leave permission for a later manual command. After the fixed DSI surface is
adopted, the armed call enables normal code and data caching before DMA setup
and the first visible clear/banner. Both fixed
DSI buffers are already mapped Normal Non-Cacheable by the board cache map.
No panel power, reset, DSI-host, HVS, PixelValve, or DMA algorithm changed.

HDMI deliberately skips this early policy. Its firmware framebuffer may be
reallocated by the later V3D double-buffer attempt, so the existing late cache
mapping remains authoritative there. V3D failure on DSI retains the existing
DMA/CPU fallback with caches enabled under the same coherency policy.
Later manual screen changes are unarmed and therefore respect an explicit
`cache off`.

This changes the later `TouchBoot()` observation from the preserved build-32
cache-off baseline to cache-on execution. A subsequent trace is therefore not
timing-equivalent to that baseline and cannot by itself claim touch success or
a protocol correction. It adds no touch transaction, reset, pin operation, or
delay.

`tools/screen_early_cache_check.py` executes the actual emitted policy helper
with `CacheEnable()` replaced by a counting leaf, proving unarmed calls and
armed NONE/HDMI do not enable while armed DSI calls it once, with the V3D
feature constant both disabled and enabled. Its structural half proves adoption precedes caching,
which precedes DMA, clear and banner, and rejects three ordering/removal
mutations. This is not hardware speed evidence; the next normal build and
visual/trace observation are separately root-owned.
