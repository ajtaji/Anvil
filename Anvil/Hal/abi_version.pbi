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
#SVC_ABI_MINOR   = 2
#SVC_SLOT_COUNT  = 184         ; slots at 1.0; the boot code sizes its check by it
