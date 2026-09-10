# DMA cache-maintenance loop

The DMA library now keeps the per-line cache walk in registers. It loads its
rounded start and exclusive end once, then issues `DC CIVAC`, advances by 64,
compares and branches. It no longer writes a shared scratch global or calls
`DmaCacheLine` for every line. The old single-line helper remains compatible;
the range walk no longer uses it.

This is an implementation-site optimization, not an assembler peephole.
Addresses and bounds remain 64-bit. Callers still supply positive physical
addresses with a non-overflowing exclusive end. Start rounding, partial tail
coverage, clean-and-invalidate semantics and caller-owned barriers are
unchanged. The Cortex-A72 data-cache line is 64 bytes; see the
[Arm Cortex-A72 Technical Reference Manual, memory-system and cache-maintenance sections](https://documentation-service.arm.com/static/60368ce38f952d2e4134dc2e).
The library does not guess that cache maintenance is unnecessary from a
caller's MMU state.

The two ASM bound loads refer to this compiler's existing static-BSS local
labels. They remain valid under the current ABI and scoped-identity repair
must preserve these unambiguous names. Future stack-frame activation must
explicitly migrate or refuse such local-address ASM references; blindly
removing their BSS slots would invalidate this and other existing libraries.

Run the independent emitted-code check:

```powershell
python tools/dma_cache_walk_emitted_check.py --pmfc C:\path\to\pmfc.exe
```

The check extracts the four actual maintenance procedures and compiles both
the candidate and the recorded pre-fix loop. It observes the exact SYS
operation/address stream and final barrier order over 25 cases: aligned and
unaligned spans, leading/trailing partial lines, addresses above 4 GiB,
zero/negative lengths, contiguous rectangles, strided and overlapping rows,
and empty rectangles. Range-with-zero still issues its existing barrier;
empty rectangles still return without one.

Only the exact compiled image, exact linker BSS and a bounded private stack
are admitted for memory access. Fetches are image-only. Six deliberate guard
violations must fail for each body. Calls preserve SP, x19..x29 and a stack-low
canary. Five separately compiled mutations change the operation, stride,
address width, tail boundary or final range barrier; each must fail on an
actual trace mismatch, not a compiler refusal or unrelated exception.

Root's initial result is 25 cases on both bodies, all guards and mutations
passing. The 100-line inner-walk call drops from 3,446 to 446 decoded
instructions (87.1% fewer); all cases combined drop from 10,392 to 3,072.
These are instruction counts, **not elapsed time or hardware speedup**.
The interpreter observes maintenance instructions but models no physical
cache, DMA engine, coherency, panel or bus contention.

The early display already binds DMA before its first clear, while V3D and
cached execution start later. This loop removes one identified cost; it does
not establish the complete cause of early DSI slowness. The historical
`ScreenFastScroll` workaround remains until a physical comparison of ordinary
`DisplayScroll` under the actual cacheability/presentation policy justifies
its removal. No board reset or display experiment was used for this change.
