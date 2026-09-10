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
#SVC_ABI_MINOR   = 0
#SVC_SLOT_COUNT  = 184         ; slots at 1.0; the boot code sizes its check by it
