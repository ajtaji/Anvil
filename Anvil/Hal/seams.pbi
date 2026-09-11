; ======================================================================
;  THE PUBLISHED SEAM HEADER - WHAT A DRIVER MODULE IS BUILT AGAINST
; ----------------------------------------------------------------------
;  THIS FILE IS THE CONTRACT AND IT CONTAINS NO MONITOR SOURCE. A driver
;  module is a separately compiled image: it never sees board.pi4, never
;  sees the service table's implementation, and cannot be linked against
;  either. What it needs is the vocabulary - which seam ids exist, which
;  function index means what inside a seam, and where in the service
;  table the two procedures that join a module to the monitor live - and
;  that is all of what is below.
;
;  A module includes this file and nothing else of Anvil's. If a module
;  ever needs a second Anvil file to build, the contract has leaked and
;  the leak is the defect, not the include.
;
;  THE IDS MOVED HERE FROM Anvil/Hal/abi.pbi ON 2026-09-10 and their
;  values did not change. They were declared beside the service table
;  because the table was their only consumer; a module loader gives them
;  two more - the seam registry, which is included near the top of a
;  board composition long before the table exists, and the module itself,
;  which must not include the table at all. A constant with three
;  consumers in three different layers belongs in a file of its own.
;
;  REQUIRED BY, in this order, in the main file:
;      Anvil/Hal/seams.pbi              <- here
;      Anvil/Hal/module_format.pbi
;      Anvil/Hal/module_runtime.pbi
;      Anvil/Core/mod_registry.pbi
;      ... the drivers, which may now ask whether a module fills a seam
;      Anvil/Hal/abi_version.pbi
;      Anvil/Hal/abi.pbi                <- the table, which reads these
;
;  THESE NUMBERS ARE PART OF THE ABI and are as frozen as the slot
;  indices. SvcCapGet of an id this Anvil does not know returns 0, NOT an
;  error - "this board does not offer it" is the honest answer for a
;  capability that had not been invented when this Anvil was built, and
;  it is what lets a newer payload run on an older monitor.
;
;  ID 9 WAS #SVCCAP_CAN UNTIL 2026-09-04, when the engine port was moved
;  to a second unit and the group became the VEHICLE LINK. The NUMBER did
;  not move, and refusing to move it is the point: nothing had shipped,
;  so renumbering was free - and the habit of renumbering a frozen id
;  when it is free starts here or never.
; ======================================================================

#SVCCAP_STORAGE  = 0
#SVCCAP_NET      = 1
#SVCCAP_GPIO     = 2
#SVCCAP_I2C      = 3
#SVCCAP_MMC      = 4
#SVCCAP_USB      = 5
#SVCCAP_BOOT_EL1 = 6
#SVCCAP_TOUCH    = 7
#SVCCAP_GNSS     = 8
#SVCCAP_VEHLINK  = 9      ; was _CAN; renamed 2026-09-04, id unchanged
#SVCCAP_SPI      = 10
#SVCCAP_UART     = 11
#SVCCAP_RTC      = 12
#SVCCAP_CONSOLE  = 13

; ----------------------------------------------------------------------
;  14 AND 15 ARE NEW AT ABI 1.1 AND ONLY ONE OF THEM IS IMPLEMENTED.
;
;  #SVCCAP_PWM = 14 IS A RESERVATION. The design note fixed the number
;  before two lanes could both reach for it, and reserving it costs
;  nothing: #CAP_TOUCH was once declared twice on two branches, meaning
;  two different things, and two meanings of one name is exactly the
;  collision a reserved id prevents. No slot block exists for it and
;  SvcCapGet answers whatever the board says; a module may not fill it
;  until a lane owns it.
;
;  #SVCCAP_THERMAL = 15 IS IMPLEMENTED. Raising #SVCCAP_MAX is an
;  APPEND, which is what an abi_minor bump is defined to be: no existing
;  id changes meaning, and an id this monitor does not know still
;  answers 0 rather than an error.
; ----------------------------------------------------------------------
#SVCCAP_PWM      = 14     ; RESERVED, not implemented - see above
#SVCCAP_THERMAL  = 15
#SVCCAP_MAX      = 15     ; anything above this answers 0, not an error

; ======================================================================
;  WHERE A MODULE FINDS THE TWO PROCEDURES THAT JOIN IT TO THE MONITOR
; ----------------------------------------------------------------------
;  A module is entered with the service table's address in its first
;  argument. The table is two 64-bit header words followed by
;  entry_count 64-bit slots, so slot n is at
;
;      table + #SVC_SEAM_HDR_BYTES + n * 8
;
;  and the module reads the pointer there and calls it. These two
;  numbers and that one line of arithmetic are the whole of the
;  mechanism; a module does not need the table's layout beyond them.
;
;  BOTH SLOTS ARE IN THE CORE GROUP, WHICH STARTS AT ZERO, so the slot
;  index and the core-group index are the same number and no group base
;  has to be published here.
;
;  #SVC_SEAM_SLOT_FILL  SvcSeamFill(seam, index, fn) -> 0 or a refusal
;
;      Publishes one function into one seam. LEGAL ONLY FROM INSIDE A
;      MODULE'S INIT, and only for a seam the module's own header
;      declares - the monitor refuses anything else, so a driver cannot
;      quietly take over a group it was not built for and cannot publish
;      anything from a probe. A probe is side-effect-free by contract and
;      that is the contract being enforced rather than requested.
;
;  #SVC_SEAM_SLOT_GET   SvcSeamGet(seam, index) -> a function or 0
;
;      Reads back what fills a seam. A module that needs another module's
;      service asks through this rather than being linked to it.
; ======================================================================
#SVC_SEAM_HDR_BYTES  = 16
#SVC_SEAM_SLOT_FILL  = 14
#SVC_SEAM_SLOT_GET   = 15

; ======================================================================
;  THE FUNCTION INDEX VOCABULARY, PER SEAM
; ----------------------------------------------------------------------
;  A seam publishes up to four functions and the index is what says which
;  is which. They are written here rather than in each driver so that the
;  monitor and the module cannot disagree about what index 0 means.
;
;  THE THERMAL SEAM, and it is deliberately one function.
;
;    index 0   fn() -> the part's temperature in MILLIDEGREES CELSIUS,
;              or #MOD_TEMP_NONE when the sensor did not produce a valid
;              reading. It takes no argument: the driver was handed its
;              device at init and is not asked again.
;
;  MILLIDEGREES CELSIUS AND NOT FAHRENHEIT, and that is the project rule
;  rather than an exception to it. Every temperature a person reads is
;  Fahrenheit; this is a number crossing an internal seam, and the
;  conversion happens once, at the edge, in Anvil/Hal/hal.pbi. A seam
;  carrying Fahrenheit would push a conversion into every driver that
;  fills it and make each one's arithmetic uncheckable against the
;  documents it was written from.
;
;  THE SENTINEL IS NOT ZERO AND NOT -1. Both are real temperatures. It is
;  #MOD_TEMP_NONE below, a millidegree value beneath absolute zero, so it
;  can never collide with a measurement.
; ======================================================================
#SEAM_THERMAL_READ = 0

; The no-reading sentinel, in millidegrees Celsius. It is here rather
; than in the loader's vocabulary because a module has to be able to
; return it, and a module includes this file and nothing else of
; Anvil's. Lib/thermal.pi4's #THERM_NONE and Anvil/Hal/hal.pbi's
; #HW_TEMP_NONE are the same number and are translated at each boundary
; rather than shared, so a future divergence is a compile-time question
; instead of a silent one.
#MOD_TEMP_NONE = -273151
