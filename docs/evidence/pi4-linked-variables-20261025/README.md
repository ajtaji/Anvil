# Pi 4 linked-variable reservation - 25 October 2026

Pi 4 monitor region 1 now covers the actual linked end of ordinary and
preserved variable storage, rounded up to the existing 1 MiB grain. The
original 16 MiB reservation remains a minimum. A NoClear anchor guarantees
that the compiler's final preserved-storage label exists. Its value is never
read. The address bridge follows the existing image-end bridge and adds no
compiler intrinsic or compiler change.

Two returning physical tests use a safe private data placement at 02000000.
Only the copied map's data-base/minimum constants move; the production map
and core guard procedures execute unchanged. The small fixture has 64 KiB
of ordinary test padding and retains the minimum end 02FFFFFF. The large
fixture has 17 MiB and extends the end to 031FFFFF. Both include a preserved
variable beyond the zeroed range. The returned end agrees with both the
actual linker symbols and PMF header, including preserved storage.

Each fixture passes nine native checks: linked extent covers the variables,
rounding/minimum hold, first/last/rounded-edge bytes are protected, a crossing
range is refused, the next free byte is accepted, and payload admission
respects the exclusion. Native return is zero in 2.2 seconds (large) and
1.5 seconds (small), captures 121/122. Thirteen damaged reports, container
extents or symbols are rejected. The public large builder produces the
exact complete PMF run on hardware. No emulator was executed.

```text
python tools/build_pi4_linked_variables_proof.py --variant large --compiler <PureMetalForge.exe> --out <directory>
python tools/pi4_linked_variables_proof_check.py --report docs/evidence/pi4-linked-variables-20261025/large-report.bin --container docs/evidence/pi4-linked-variables-20261025/large.pmf --symbols docs/evidence/pi4-linked-variables-20261025/large.sym --self-test
```

The normal returning runner stages at 01000000, uses stack 04F00000 and a
15-second deadman. Main returns zero; the complete report is E1C00000:256.
The large fixture's BSS ends at 0310818F, within the low payload window and
clear of the resident monitor. No monitor-owned variables at 0D000000 are
written by the test. Prompt/cores were healthy, Vulkan restored, watchdog off
and the lease released after each phase. No reset or firmware replacement.

Normal counted build 331 compiles with variables 0D000000..0E60D92F. Its
PMF end equals the final preserved-storage symbol; the corrected reservation
therefore ends at 0E6FFFFF. The source layout gate now uses this linked extent
and includes preserved storage instead of comparing against the fixed minimum.
That broad gate was NOT RUN because it executes an emulator and a physical
Pi 4 is available; the focused silicon proofs and metadata checks above are
the evidence here. Pi 5 retains its separate fixed reservation because its
records and stack immediately above it need a separate layout solution.

Build 331 is not installed. Resident build 328 still publishes the older map.
Topic 1249 stays open pending deployment acceptance; these results establish
the corrected Pi 4 source guard and its safe relocated physical execution,
not an in-place monitor update or completion of the Vulkan port.
