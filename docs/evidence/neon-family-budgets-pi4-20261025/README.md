# Independent Neon family budgets on Pi 4 - 25 October 2026

The adapter now enforces native flat limits of 4096 draw records and 262144
input vertices independently of textured limits of 2048 records and 98304
vertices. Shared Vulkan command rows, caller-configured total draw capacity,
and actual emitted vertex storage remain additional independent constraints.
Begin, Abort and successful Destroy reset both logical families. This is
default accounting, with no optional mode needed to protect the limits.

Boxes and flat/angled bitmap text use the flat family; flat bitmap vertex
cost is six per native vertically merged bit rectangle, not per atlas glyph.
The font row source remains authoritative. Accepted fan/line input points
are charged once; repeated outline/fill draws reuse those units while their
actual lowered geometry still consumes storage. Raw bulk reservation exposes
GPU triangles, so it charges six actual flat vertices per reserved quad;
it does not pretend to be the native endpoint-only line API. TrueType flat
text charges emitted ink quads. Bitmap textured text, atlas/separate sprites,
retained sprite batches, grids and both particle paths use the textured
family with six vertices per emitted quad. Retained groups preflight their
aggregate family cost. Grid reservation is a conservative preflight and does
not advance counters; appends charge vertices and flushes charge draws.

Bitmap calls plan complete visible strings and mapped UVs before charging
or writing. Blank flat glyphs advance without geometry; textured spaces
retain their native cell cost. Alpha-zero and clipped flat calls are no-ops.
The active physical scissor is inverted to logical coordinates for all four
rotations. Box clipping avoids caller x+width overflow. A backend-only
transparent sentinel in a clear-only frame consumes no logical family quota.
Native public statistics ownership remains a separate audit; these new
internal logical counters do not yet make the native getters renderer-neutral.

## Physical evidence

The final returning payload fills all 4096 flat and 2048 textured records
in one command buffer, proves refusal atomicity and aborts it before GPU
submission. The reverse exhaustion order also leaves the other family usable.
It fills 262144 flat input units and 98304 textured vertices separately,
checks whole-string and point refusal, then records work in the other family.
Snapshots include both family ledgers, actual vertex/draw cursors, free command
rows, fault status and a 16-byte next-vertex guard. Abort restores all 6144 rows.
Large maximum-load phases are recording tests, not GPU throughput claims.

190 glyph/font cases compare the read-only cost with the native rectangle
emitter itself. Four real GPU frames combine clipped boxes, flat/textured
text, reused outline/fill points and native lines at every rotation. A fifth
clear-only frame verifies the private sentinel. All 81920 GPU bytes match an
independent complete glyph/rectangle/axis-line oracle. The two flat spaces
in the widget scene now emit no quads: its 47 draws remain, physical vertices
become 642 from 654. Its glyph corpus similarly drops one flat space (1134
from 1140); original pixel goldens are unchanged.

Seven additional refusal cases seed only private diagnostic ledger values
to exercise atlas/transformed/separate sprites, prepared particles, aggregate
retained sprites, raw bulk reserve and angled text. The same paths then
record successfully with expected family charges. These seeded cases do not
claim another full maximum workload or GPU execution of those extension
commands; their command buffer is aborted. External-particle and TrueType
grid-specific quota boundaries still need dedicated physical coverage.

The full 15-scene regression matches all 245760 pre-change current bytes and
passes all 124 widget report checks. Historical line/outline scene differences
from the older native golden remain explicit. The strict family checker
rejects 59 report/pixel/truncation mutants. The public builder produces the
exact complete PMF used for the final physical test.

```text
python tools/build_neon_family_budget_proof.py --compiler <PureMetalForge.exe> --out <directory>
python tools/neon_family_budget_proof_check.py --report docs/evidence/neon-family-budgets-pi4-20261025/report.bin --pixels docs/evidence/neon-family-budgets-pi4-20261025/pixels.bgra --self-test
```

Final test: stage01000000, stack04F00000, BSS011C0000..0200163F,
surface06000000, heap063E8000..077E7FFF (20 MiB), mapped span017E8000,
reportE1C00000:8192 and five capturesE2400000:81920. The initial 16 MiB
heap was insufficient when target, 9 MiB vertex buffer, atlas and staging
coexisted; it returned291 at creation and cleaned up, without running the
budget phases. That failed setup is retained separately. The corrected
preliminary run passed at 23.5 seconds; the final extended run returned0
in25.0 seconds, with finite forward-progress watchdog pets between phases.
No claim of a whole15-second test is made. Full scene regression returned0
in12.7 seconds. Captures131(failed setup),132(preliminary),133(all15),134(final).
Every phase restored a healthy prompt/cores, Vulkan, watchdog-off and FREE.
No reset, flash or emulator. Counted normal build334 compiles but is not
installed; resident328 remains. Exact identities are in manifest.json.

Full native maximum point/storage workloads, renderer-neutral public counters,
desktop frontend and the presentation/recovery matrix remain open. Separate
quota enforcement is not a claim that the entire port or Vulkan is complete.
