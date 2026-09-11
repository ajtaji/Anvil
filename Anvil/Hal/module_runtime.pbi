; ======================================================================
;  PMFMOD RUNTIME VOCABULARY - THE LOADER'S HALF, NOT THE PRODUCER'S
; ----------------------------------------------------------------------
;  Anvil/Hal/module_format.pbi is CONSUMED BYTE-IDENTICALLY by the
;  compiler that writes containers and by the monitor that loads them.
;  Its SHA-256 is recorded in the vault, and a producer that carries a
;  different copy of a header offset is exactly the divergence the shared
;  file exists to prevent - so nothing that only one side needs may be
;  added to it.
;
;  Everything below is only ever needed by the side that LOADS: the
;  lifecycle states a record passes through after it is placed, the
;  refusal codes for the steps that happen after parsing, and the limits
;  of the seam registry. A container writer has no use for any of it.
;
;  It is constants only, it defines no procedure and no global, and it
;  is included immediately after module_format.pbi.
; ======================================================================

; ----------------------------------------------------------------------
;  LIFECYCLE STATES. #MOD_STATE_EMPTY and #MOD_STATE_READY are declared
;  in module_format.pbi because the arena engine that owns them is the
;  half the producer's test fixtures are written against. The states
;  below continue that numbering and must never renumber those two.
;
;  READY means verified, placed, zeroed, relocated and cache-synchronised
;  and NOTHING MORE - not matched, not probed, not initialised, not
;  publishing a service. Every state above it is a claim about the
;  DRIVER rather than about the bytes, and each is entered by exactly
;  one transition so a record can never be half-advanced.
;
;    READY     -> MATCHED    a device the board declares answers one of
;                            the container's compatible ids
;    MATCHED   -> PROBED     the module's probe accepted the device. A
;                            probe is side-effect-free by contract and
;                            may not fill a seam; the registry refuses a
;                            fill outside init for that reason.
;    PROBED    -> ACTIVE     init returned 0 and filled at least one of
;                            the seams its header declared
;    any       -> FAILED     an activation step refused. Every seam the
;                            module managed to fill is released again
;                            before the state is written.
;    ACTIVE    -> QUIESCED   unloaded: no binding held the seam, quiesce
;                            returned, the seams were released. The BYTES
;                            stay where they are - the allocator has no
;                            free list - and `mod list` says stranded.
; ----------------------------------------------------------------------
#MOD_STATE_MATCHED  = 2
#MOD_STATE_PROBED   = 3
#MOD_STATE_ACTIVE   = 4
#MOD_STATE_FAILED   = 5
#MOD_STATE_QUIESCED = 6

; ----------------------------------------------------------------------
;  REFUSAL CODES FOR THE STEPS AFTER PARSING. module_format.pbi stops at
;  #MOD_ERR_SYNC = 20, which is the last thing that can go wrong before
;  a record is READY. These are the ones that can only go wrong after it.
; ----------------------------------------------------------------------
#MOD_ERR_NOMATCH   = 21   ; no device this board declares answers an id
#MOD_ERR_PROBE     = 22   ; the module's own probe declined the device
#MOD_ERR_BOUND     = 23   ; a consumer still holds the seam; unload refused
#MOD_ERR_STATE     = 24   ; the record is not in a state this step allows
#MOD_ERR_MANIFEST  = 25   ; a manifest line could not be acted on
#MOD_ERR_REGION    = 26   ; the arena overlaps a region the board reserves
#MOD_ERR_SEAM_ID   = 27   ; a seam id outside the published vocabulary
#MOD_ERR_NOSERVICE = 28   ; the seam is declared but no function is filled
#MOD_ERR_QUIESCE   = 29   ; the driver refused to put its hardware down
#MOD_ERR_NOARENA   = 30   ; this board offers no module arena at all

; ----------------------------------------------------------------------
;  THE SEAM REGISTRY'S SHAPE.
;
;  #MOD_SEAM_MAX is the highest #SVCCAP_* id the registry has a row for.
;  It is ONE NUMBER HERE rather than a reference to abi.pbi's
;  #SVCCAP_MAX, because the registry is included long before the service
;  table is - it has to be, since drivers that fill seams are read by
;  code that runs before the table is built - and a registry sized from
;  a constant it cannot see would be sized from nothing. The two are
;  checked against each other by tools/module_pipeline_check.py, which
;  reads both files, so they cannot drift silently.
;
;  #MOD_SEAM_FNS is how many functions one seam may publish. Four is what
;  the widest seam shape in this tree needs (a link seam: up, down, send,
;  poll); a seam wanting more is a seam that should be two.
;
;  #MOD_BIND_MAX is how many durable consumer bindings may exist at once
;  across every seam. A binding is a consumer saying "I will keep calling
;  this" - it is what makes `mod unload` refusable instead of a coin
;  toss - and eight is generous for a monitor that has one binder per
;  service.
; ----------------------------------------------------------------------
#MOD_SEAM_MAX  = 15
#MOD_SEAM_FNS  = 4
#MOD_BIND_MAX  = 8

; A seam function index that means "the seam itself", used by callers
; that only ask whether anything fills it.
#MOD_SEAM_FN_PRIMARY = 0

; The thermal seam's no-reading sentinel lives in Anvil/Hal/seams.pbi
; and not here. It is part of the PUBLISHED contract a driver module is
; built against, and a module must be able to reach it without including
; the loader's own vocabulary.
