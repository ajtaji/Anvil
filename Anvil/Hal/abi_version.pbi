; ======================================================================
;  abi_version.pi4 - THE PAYLOAD ABI VERSION AND THE TABLE'S SHAPE, NOTHING ELSE
;
;  Three constants in their own file so that the boot code (pmfboot.pi4),
;  the service table (abi.pi4) and any probe that includes the boot code
;  WITHOUT a service table all read the same number. The boot-container
;  self-test builds a monitor with no service table on purpose; before
;  this file existed it either did not build (the constant lived in
;  abi.pi4) or carried its own copy, which is the number that drifts the
;  day the ABI is bumped. Forum 686, 2026-09-07.
;
;  Include it ahead of abi.pi4 and ahead of pmfboot.pi4. It defines no
;  procedure and no global, so it costs nothing where the table is absent.
; ======================================================================
#SVC_ABI_MAJOR   = 1

; ----------------------------------------------------------------------
;  1.1 - 2026-09-10. THE MODULE HALF OF THE TABLE.
;
;  Core slots 14 and 15 - SvcSeamFill and SvcSeamGet - were filled, and
;  #SVCCAP_PWM (14, reserved) and #SVCCAP_THERMAL (15) were appended to
;  the capability ids in Anvil/Hal/seams.pbi.
;
;  IT IS A MINOR BUMP BECAUSE NOTHING EXISTING CHANGED MEANING. The core
;  group had reserved sixteen slots and used fourteen; the two that were
;  filled were already pointing at SvcUnimplemented, so a payload built
;  at 1.0 finds every slot it knows exactly where it left it, and one
;  built at 1.1 running on a 1.0 monitor gets #SVC_ENOSYS from the two
;  new ones and 0 from the two new capability ids - both honest answers.
;  #SVC_SLOT_COUNT does not move: the slots existed, they were empty.
;
;  A MODULE IS CHECKED THE OTHER WAY ROUND from a payload. A payload
;  refuses ITSELF on entry, because it runs with the machine handed over
;  and nothing is left to refuse it. A module is refused BY THE LOADER,
;  before init, because the code that loads it is still in charge: a
;  different major at all, or a minor HIGHER than this monitor
;  publishes. A lower minor loads - within a major, slots are only ever
;  appended.
; ----------------------------------------------------------------------
; ----------------------------------------------------------------------
;  1.2 - 2026-09-11. THE SCREENSHOT SLOT.
;
;  Console slot 13 - SvcScreenCapture - was filled. It keeps the frame the
;  screen is showing somewhere a repaint cannot reach, which is the only
;  way a payload's last picture can survive its own return: the monitor's
;  first printed line on the way back is painted over the surface the
;  payload left.
;
;  IT IS A MINOR BUMP FOR THE SAME REASON 1.1 WAS. The console group
;  reserved sixteen slots and used thirteen; the one that was filled was
;  already pointing at SvcUnimplemented, so a payload built at 1.0 or 1.1
;  finds every slot it knows exactly where it left it, and one built at
;  1.2 running on an older monitor gets #SVC_ENOSYS from it - the honest
;  answer for "this Anvil cannot keep a picture for you".
;  #SVC_SLOT_COUNT does not move: the slot existed, it was empty.
; ----------------------------------------------------------------------
; ----------------------------------------------------------------------
;  1.3 - 2026-09-15. FOUR CORES, AND THE FIRST GROUP ADDED SINCE 1.0.
;
;  Group 15 - parallel execution - opens at base 184 with eight reserved
;  slots and three used: SvcParallelCores, SvcParallelRun and
;  SvcParallelStatus. A payload hands one entry procedure and N argument
;  blocks; the monitor runs them on cores 0..3, waits inside a bounded
;  deadline, and returns.
;
;  #SVC_SLOT_COUNT MOVES FOR THE FIRST TIME, 184 -> 192, AND THAT IS WHY
;  THIS IS STILL A MINOR BUMP. 1.1 and 1.2 filled slots that already
;  existed, so the count did not move; here the core group was FULL - 16
;  of 16 since 1.1 put SvcSeamFill and SvcSeamGet in its last two - and
;  the versioning rule in abi.pbi says a group that fills its block gets a
;  new block at the end rather than a renumbering. Nothing existing is
;  reordered and no slot changes meaning, so a payload built at 1.0, 1.1
;  or 1.2 finds every slot it knows exactly where it left it.
;
;  THE OTHER DIRECTION IS THE ONE THAT MATTERS HERE. A payload built at
;  1.3 running on a 1.2 monitor reads entry_count, sees 184, and knows the
;  block is absent - which is the same answer SvcParallelCores gives when
;  the block is present and the board has no secondary-core owner. Both
;  are "one core", so a payload has ONE fallback path rather than two, and
;  that path is the single-core code it already had.
;
;  #SVCCAP_PARALLEL = 16 was appended in Anvil/Hal/seams.pbi and
;  #SVCCAP_MAX raised to 16, which is the same append this file's 1.1 note
;  describes for #SVCCAP_THERMAL.
; ----------------------------------------------------------------------
#SVC_ABI_MINOR   = 3
#SVC_SLOT_COUNT  = 192         ; 184 at 1.0-1.2; group 15 appended at 1.3.
                               ; The boot code sizes its check by it.
