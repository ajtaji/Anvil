# Neon text caret port audit

The initial audit found that the original engine exposes `GLTextXForColumn` and `GLTextColumnForX` in
`GlUtilities.pbi`. At that checkpoint, Anvil `neon_vk_font_port.pbi` exposed width and
alignment, fixed advance, snap and control policies, but no equivalent caret
queries. Existing widget byte-offset editing was not evidence of these engine
APIs. The implementation checkpoints below supersede that interface gap;
resident service and physical interaction qualification remain incomplete.

## Source contract and differences

The original API documents zero-based Unicode codepoint columns. Its
proportional path walks codepoints and sums glyph advances; X-to-column selects
the nearest boundary, choosing the right boundary at an exact midpoint.
Hidden C0/DEL controls consume a source column but have zero advance.

Two original fixed-spacing shortcuts require explicit handling during the port:
X-for-column extrapolates beyond the end of the text, while column-for-X clamps
to its character count. The latter counts UTF-16 units in its fixed-spacing
branch, despite the documented codepoint contract. Anvil's UTF-8 interface must
count a supplementary scalar once; copying that UTF-16 behavior would violate
the documented contract. No desktop source is being changed by this work.

Anvil rendering already has additional layout semantics: pair positioning,
fixed-cell advance, hidden/visible controls, and legacy CR/LF line breaks. A
caret implementation must use the same adjusted advances as drawing. Summing
individually measured prefixes is insufficient because a pair crossing the
prefix boundary can change its preceding glyph's advance. Glyph placement
offsets and raster bearings also must not be mistaken for pen advance.

`anvil_ttl_Layout` is the existing shared owner. It computes adjusted advances
but its drawable arrays omit hidden controls and legacy line breaks. Their
indices cannot serve directly as original source columns. The missing input
is an explicit source-scalar-to-layout boundary mapping. The current layout
cache similarly stores glyph positions and advances, not that mapping.

## Required implementation and evidence

1. Retain source scalar boundaries through the shared decoder/layout path,
   including omitted controls, supplementary scalars and CRLF handling. Keep
   existing glyph placement, wrapping and width results unchanged.
2. Expose caret positions from that layout owner, then add font-reference
   wrappers that honor generation, fixed advance and control policy. Do not
   introduce a second font-metric or pair-positioning implementation.
3. Define line selection for the existing legacy multiline mode explicitly;
   an X coordinate alone cannot distinguish repeated positions on two lines.
   Preserve the original single-line engine interface and provide an explicit
   line-aware operation for multiline text rather than silently choosing a line.
4. Test proportional and fixed text, fractional advances, pair adjustments,
   zero-advance glyphs, hidden/visible controls, supplementary UTF-8, exact
   midpoint ties, empty text, beyond-end positions and invalid input. Test stale
   references, bounded capacity, output preservation on refusal and calls during
   a frame without rasterization or texture upload.
5. Physically validate caret markers against rendered text and actual hit-test
   results. CPU-only mapping tests do not qualify the visual alignment or input
   routing. Keep this scope separate from full physical keyboard/pointer testing.

The bounded source audit is in `evidence/neon-caret-audit-20261029/audit.json`.
It records exact source hashes and procedure declarations. It is evidence of
the missing interface and existing layout constraints, not runtime evidence or
a substitute for implementing the operations above.

## Shared layout implementation checkpoint

`AnvilTrueTypeLayoutCaretUtf8` now runs the existing layout with an opt-in
source-boundary snapshot. `AnvilTrueTypeCaretCount`, `AnvilTrueTypeCaretPoint`
and `AnvilTrueTypeCaretColumnForX` expose it. Points contain Q16 pen X,
baseline-relative Y and original UTF-8 byte offset; columns count Unicode
scalars, including hidden controls. CRLF has two source columns and one line
break. A wrapped boundary belongs to the next line. Hit testing selects an
explicit zero-based line and chooses the later column on equal distance,
including coincident hidden-control boundaries.

The snapshot is limited to 2048 source scalars and invalidated by every layout
attempt. Callers must serialize parser use and consume/copy the snapshot before
another layout. Point output requires three distinct aligned caller-owned
words; refusal leaves them untouched. Ordinary layout does not build a caret
snapshot or perform the additional source validation. The new path uses the
existing adjusted advances, without rasterization or atlas uploads.

This is the shared layout prerequisite, not the completed engine interface.
At this checkpoint, font-reference wrappers, resident service integration, explicit single-line
compatibility behavior and rendered marker/input qualification remain required.


Physical capture 120 passes 135 CPU API checks using the loaded Lato face;
132 expected values are fixed and three compare against the layout's actual
adjusted advances. The checker rejects 275 corrupted reports. Capture 119's
incorrect hidden-tab midpoint expectation is retained; only the fixture was
corrected before 120. Captures 121/122 run the original/updated ordinary layout:
all 69 cases pass and their complete 65,536-byte reports are identical.
Evidence: `evidence/neon-caret-layout122-20261029`. These checks do not establish
rendered caret alignment, font-wrapper behavior or physical input routing.

## Font-reference integration, capture 123

The font port now exposes single-line X/column queries and explicit multiline
point/line-hit-test queries. They revalidate font generations and use the shared
caret snapshot, with no alternate metric implementation. Single-line calls
refuse multiline legacy text. Fixed spacing extrapolates after the final pen;
hidden controls within the source still follow actual zero-width layout.

The Pi passes 78 wrapper checks and a complete 30,720-byte crop comparison
between text/caret markers and an independently positioned fixed-cell reference.
All seven markers have the expected coordinates and color. Frame raster and
upload deltas remain zero despite in-frame queries. The checker rejects 177
damaged reports/pixel buffers. Source and evidence are in
`evidence/neon-font-caret123-20261029`.

At capture 123, proportional rendered alignment and broader hostile arguments
remained unqualified. Capture 124 below extends that evidence. Resident service
exposure and physical input routing remain required.
The full Neon engine port is not complete.


## Proportional rendering, capture 124

The expanded fixture passes 141 checks on Anvil 391. Its proportional AVATAR
reference uses the embedded DejaVu Sans Bold face, independently read with
fontTools from hmtx and GPOS latn kerning lookups 13/14. Pair adjustments are
-139, -139, -159, -159, 0 font units. The checked-in oracle records the font
digest, advances and all seven Q16 boundary positions. It does not derive
expected positions from Anvil's layout or caret queries.

Complete fixed and proportional text/marker crops match their references over
61,440 bytes, with 14 explicitly checked markers. Midpoint ties and the points
immediately before them are checked for each proportional cell. Additional
refusals cover oversized coordinates/columns, an unterminated 4096-byte string
and more than 2048 hidden source scalars. Queries add no frame rasterizations
or texture uploads. The checker rejects 328 damaged reports/pixel buffers.

Capture 124 returns zero in 8.0 seconds with healthy cores, fonts and Vulkan,
zero display timeouts and watchdog off. Evidence is retained in
`evidence/neon-font-caret-proportional124-20261029`. This qualifies those two
rendered rows and their API cases; it does not qualify resident service routing
or physical interaction. The full port remains incomplete.


## Resident protocol candidate, capture 125

Protocol 1.13 adds FONT_CARETS (16384) with operations 48..51 for exact points,
explicit-line hit testing and the single-line X/column operations. Its 80-byte
record carries an opaque font handle, borrowed UTF-8 pointer and exact byte count
including NUL, column/line/X inputs, and four result words. No font/parser
pointer is returned. Text must contain exactly one terminal NUL within 4096
bytes. Results are published only on success; unused result words are zero.
Exact point/line operations preserve Q16 positions. Single-line operations keep
the existing float32 compatibility semantics, represented as Q16 in the ABI.

The shared renderer adapter resolves layout through the existing font wrappers.
The Pi provider checks context, frame state, opaque reference and payload-owned
record/text ranges before entering it. A pure application client uses a local
record copy, so even a provider that writes results before returning failure
cannot alter caller result fields. Old protocol/capability combinations refuse.

Physical capture 125 passes 180 checks, including 39 new shared-adapter and
controlled-client checks. Both rendered crop pairs remain equal over 61,440
bytes; queries still cause zero raster/upload work. The oracle rejects 406
damaged buffers. These checks run payload-owned code on unchanged Anvil 391:
they do NOT exercise the installed resident provider or its payload-range
guard. Anvil 396 compiled with the new provider wiring but is not installed.
Its installation and pure-client qualification are next; physical interaction
and full engine qualification remain outstanding. Evidence:
`evidence/neon-service-caret125-20261029`.


## Installed resident qualification, capture 126

Anvil 396 is now installed on the Pi 4. The 391 rollback, candidate boot file
and running image were verified by complete SHA-256 reads, with one restart
and a 90-second quiet boot interval. Network, cores, fonts and Vulkan passed
post-boot checks. The rollback is `1:/B391V396.IMG`.

A 30,384-byte pure application (no renderer or font layout implementation)
passes 62 checks through the actual resident dispatch. It covers all four
caret operations, hidden controls/supplementary UTF-8 offsets, queries during
a rendered frame, malformed record sizes/alignment, monitor-memory and
overflowing pointers, wrong contexts, stale font tokens, text bounds and
output preservation. Close/reopen rejects the old context and font token.
The payload returns zero in 1.7 seconds; the console renderer and original
font return healthy with no display timeouts and watchdog off. The host
checker rejects 131 damaged reports.

Evidence: `evidence/neon-resident-caret126-20261029`. This proves the installed
service path and tested memory guards, not physical keyboard/pointer routing
or an exact screenshot comparison. The edit widget still measures a truncated
prefix in `NeonChromeEditSeal`; it must use whole-text caret positions to retain
pair adjustments across its caret boundary. That integration is next.


## Registered-font edit integration, capture 127

The shared editor accepts an optional whole-text caret callback with an explicit
UTF-8 byte offset. Reinstalling its base renderer clears that callback. Seal uses
it when bound and retains the existing metrics/error validation. The resident
adapter translates a validated byte boundary into a scalar column, queries the
whole text through protocol 1.13 and checks the returned byte offset and line.
It does not silently fall back to prefix measurement for registered fonts when
the query fails; Seal refuses and leaves the editor unready.

Capture 127 passes 102 checks on unchanged Anvil 396, including 40 new editor
checks. All seven AVATAR positions match the independent hmtx/GPOS oracle. The
test also measures the isolated A prefix: 608640 Q16 versus the correct 555264
Q16 boundary in AVATAR, demonstrating the lost pair adjustment. Supplementary
UTF-8 offsets, continuation-byte refusal, old-ABI refusal/recovery and callback
invalidation on renderer replacement pass. The checker rejects 211 damaged
reports. The payload returns zero in 1.7 seconds with healthy post-run state.

This fixes registered-font editor measurements. Role fonts 0..3 still use their
legacy prefix metrics because protocol 1.13 only exposes opaque font references;
the shared callback's legacy renderer path likewise remains available. Extending
the resident role-font query is still required. This run verifies editor Seal
results, not a pixel-level widget comparison or physical interaction. Evidence:
`evidence/neon-edit-caret127-20261029`.


## Role-font protocol candidate, capture 128

Protocol 1.14 adds ROLE_CARETS (32768), dependent on FONT_CARETS and FONT_REFS.
For font values 0..3, the provider uses the current selected face and the same
role-size resolver as drawing. It does not allocate a temporary font reference
or write a role-height override. Registered references still validate their
generation and policies. Both paths prepare one serialized layout snapshot;
the single-line compatibility operations share the prepared-snapshot helpers.

The client requires the new capability/version only for role queries. The
resident editor adapter no longer has a prefix-measurement branch. On an older
monitor, role Seal now refuses rather than using incorrect metrics; registered
references retain protocol 1.13 compatibility. The provider's role TrueType
path refuses when no selected/parser-bound face exists; bitmap-only caret
behavior is not qualified by this extension.

Capture 128 passes 225 payload-owned adapter/client checks on Anvil 396. The
four roles each pass point, explicit-line hit, single-line X and column queries
at 12 pixels, and retain their pixel sizes. Existing fixed/proportional crops
remain identical over 61,440 bytes with no frame raster/upload work. The oracle
rejects 496 damaged buffers. Anvil 397 compiled with resident role support but
is not installed: actual resident role/editor qualification remains next.
Evidence: `evidence/neon-role-caret128-20261029`.


## Installed role/editor and composed regression, captures 129/130

Anvil 397 is installed, with the complete 396 rollback verified at
`1:/B396V397.IMG`. Candidate, boot file and running image hashes match. One
restart followed a 90-second quiet boot interval; network, cores, fonts and
Vulkan passed post-boot and post-payload checks.

Capture 129 passes 261 checks through the resident service. All four roles are
configured through ordinary font references at 12, 16, 20 and 24 pixels, then
queried by their role values. Each editor Seal matches all seven independent
AVATAR positions, with the role's size retained. Point/line-hit/single-X/single-
column calls and in-frame queries pass. Protocol-13 role Seal refuses, and
restoring protocol 14 recovers. Registered-font and prior hostile-service cases
remain green. The checker rejects 529 damaged reports. Return time is 1.8 s.

Capture 130 runs the full composed resident CRT scene with native input enabled
and file-loaded assets. Its 90 frames pass 65 state assertions and 169 raster
probes, including sprites, particles, static lines, text and placeholder ink.
Warm presentation intervals are 33,285..33,303 us (30.0293 FPS). The first frame
takes 54,367 us; whole-run measured rate is 29.8172 FPS, so the all-frame 30 FPS
target is not met. No physical input records occurred. The composed checker
rejects 234 damaged results. The scene's binding and build identity now require
protocol 1.13 for its registered-font editor, instead of understating that
dependency as 1.12. Initial compiled artifacts with stale metadata are retained
but were never run. Evidence: `evidence/neon-resident-role130-20261029`.

This establishes resident TrueType role/reference caret integration and the
stated composed regression. It does not establish bitmap-only caret support,
physical interaction, complete paired native/Vulkan performance or endurance,
nor completion of the wider port.
