# Public Neon state belongs to its renderer - 25 October 2026

Bug 1440: a real Vulkan frame had two flat draws / 162 native input vertices
and one textured draw / 18 vertices, while all nine public counters returned
zero before and after submission. A rejected clip change inside a box batch
left the real clip unchanged but reported the proposed clip as active and
hid its error. The before-source physical witness is retained, including its
successful rendering/teardown; it is a failed state-query result.

The native library now offers optional `NeonStateBackendInstall(query,error)`
with two typed procedure addresses. Query is read-only and returns the active
owner's nine counters, clip enable, error and readiness. The separate error
writer forwards frontend validation errors to that same owner; delegated
public hardware wrappers also forward failures. Both callbacks must be supplied
together. An invalid installation retains the old binding. `(0,0)`, complete
draw-family replacement and draw-backend removal clear both borrowed addresses.
Without an installed state pair, existing getters use the native fields.
This preserves stateless/legacy backends without inventing their statistics.

Vulkan installs the pair as part of successful resource publication and
removes it through the existing draw-owner teardown. Destroy clears the drawing/query hooks before its idle wait; if idle refuses,
resources remain retained and getters have already returned to native fallback.
No failed-idle recovery result is claimed by this proof. Native GPU internals now use `NeonHardwareReady`, not the external owner's
public readiness. This prevents shared hardware work from being confused with
the public frame owner. No counter mirroring into the hardware engine is used.

Flat/textured draw and vertex getters use the independent native-unit ledgers.
Accepted boxes count once even in a box batch. Flat bitmap glyphs include
considered visible blanks, while rectangle runs count the font's merged bit
rectangles. Textured text counts emitted cells including spaces. Clipped boxes
(including zero-alpha boxes) and whole-row bitmap text rejections follow native
counter conventions; zero-sized boxes and horizontally rejected text do not
increment the clipped counter. Refused geometry changes no counter. Begin and
Abort reset statistics; successful submissions retain them until the next
frame. The clear-only private sentinel contributes no public counter. TrueType
flat layout counts considered layout glyphs and emitted ink quads as runs;
grid glyphs count emitted ink cells, while sprites/particles add no glyph count.
Timing, arena and raw-address accessors retain their existing hardware meaning;
this change does not claim per-owner timing parity or full Neon completion.

## Physical evidence

Nine public values `(2,1,3,26,162,1,3,18,0)` match before and after GPU submission
and after a whole-string capacity refusal. Cursors, free rows and a 16-byte
next-vertex guard stay unchanged on refusal. The rejected batch clip reports
`(off,800,-21202,-21202)` for public enable, real width, public error and owner
error. All 16384 GPU bytes match the complete independent glyph/box oracle and
the before-source image exactly.

Six contract groups additionally check no-op/clip conventions, Abort reset,
frontend font/configuration/delegated-surface errors, chronological owner error
updates, read-only invalid selectors, partial callback refusal, separate owner
and hardware readiness, native fallback with independent marked fields,
draw-family replacement, callback removal on Destroy and installation refusal
without a draw backend. Readiness flags and fallback counters are changed only
in private diagnostic state, with no GPU work while flags are staged; flags
are restored before returning. Native fallback values101..109 remain distinct
from the owner ledger. The strict checker rejects 93 corrupted proofs and the
unchanged-source report.

The complete 15-scene regression still matches245760 prior-current GPU bytes
and passes124 widget checks. After the last wrapper-error forwarding edit,
the rebuilt complete regression PMF is byte-identical to that physical run:
those additional frontend error paths are not reached by that corpus, and are
separately exercised in the final state proof. No redundant board run or
changed pixel baseline is substituted for that identity check.

```text
python tools/build_neon_public_state_proof.py --compiler <PureMetalForge.exe> --out <directory>
python tools/neon_public_state_proof_check.py --report docs/evidence/neon-public-state-pi4-20261025/candidate-report.bin --pixels docs/evidence/neon-public-state-pi4-20261025/candidate-pixels.bgra --self-test
```

The public builder produces the exact final physical PMF. Stage01000000,
stack04F00000, BSS011B0000..01FF164F, reportE1C00000:8192 and captureE2400000:16384.
The shared fixture uses a declared20MiB heap063E8000..077E7FFF and native map
span017E8000; no slab at07000000 is used by this mode. Before/candidate return0
in7.3/7.1seconds, captures135/139; intermediate136/137 also pass and remain
workspace evidence. Full corpus0/12.9seconds,capture138. Every phase restored
healthy prompt/cores, Vulkan, watchdog-off and FREE. No reset, flash or emulator.
Normal counted336 compiles but is not installed; resident328 remains.

Maximum native point/storage workloads, dedicated external/grid quota cases,
desktop integration and wider presentation/recovery/Vulkan work remain open.
