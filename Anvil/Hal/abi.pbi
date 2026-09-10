; ======================================================================
;  abi.pi4 - THE PAYLOAD ABI. The service table Anvil hands a payload.
;
;  ELD/Phase A - Anvil payload ABI - implementation brief.md is the
;  specification this file is built against, as amended on 2026-09-04
;  (ELD/Ruling 2026-09-04 - Hardy does not hook to the engine port.md). Read the brief before changing anything here; the constants
;  below are a CONTRACT and not an implementation detail.
;
; ----------------------------------------------------------------------
;  THE PROBLEM THIS SOLVES, IN ONE PARAGRAPH
; ----------------------------------------------------------------------
;  PmfEnter() used to call RunAt(entry) and pass NOTHING. A payload
;  entered that way can compute and can scribble on memory, and that is
;  all - right for a diagnostic blob, useless for an application. Anvil
;  already owns a console, a filesystem, a radio, an IP stack, TLS, USB,
;  GPIO and I2C, all proven on silicon. The payload needs to reach them
;  WITHOUT LEARNING THE NAME OF A SINGLE CHIP, so that the same bytes run
;  on the Pi 4 today and on another board later.
;
;  The answer is one pointer, handed over in x0 at entry, behind a
;  versioned header, whose slots are procedure addresses into Anvil.
;
; ----------------------------------------------------------------------
;  THIS FILE NAMES NO CHIP AND TOUCHES NO REGISTER
; ----------------------------------------------------------------------
;  Every slot is either core Anvil or a call into the Hw* seam that
;  Anvil/Hal/hal.pbi defines and the board supplies. That is the same
;  discipline every command family in Anvil/Core/ already follows, and it
;  is why this file lives beside hal.pi4 rather than under a board.
;
;  WHERE A GROUP IS GATED BY CompilerIf, IT IS GATED ON THE BOARD'S OWN
;  #CAP_ DECLARATION and never on a board name. There is no "which board
;  is this" question anywhere in this file. A board that declares 0 for a
;  group simply does not get those procedures compiled, and its slots keep
;  pointing at SvcUnimplemented - which answers #SVC_ENOSYS, the honest
;  code for "this Anvil does not implement that slot".
;
;  THE DIFFERENCE BETWEEN #SVC_ENOSYS AND #SVC_ENOCAP IS LOAD-BEARING and
;  the two are not interchangeable:
;
;    #SVC_ENOSYS  this Anvil has no code for that slot at all. A newer
;                 payload asking an older monitor for a service that had
;                 not been invented gets this, and so does a payload on a
;                 board whose group was compiled out.
;    #SVC_ENOCAP  the code is here and the BOARD does not offer the
;                 hardware. The slot ran, asked RequireCap's question, and
;                 the answer was no.
;
;  A payload can act on the difference: the first means "upgrade the
;  monitor", the second means "this board cannot do it and never will".
;
; ----------------------------------------------------------------------
;  WHAT A PAYLOAD MAY ASSUME AT ITS FIRST INSTRUCTION - THE ENTRY CONTRACT
; ----------------------------------------------------------------------
;  Everything in this list is guaranteed. NOTHING ELSE IS. An Anvil worker
;  must not change any of it without raising #SVC_ABI_MAJOR.
;
;    x0        the address of this service table. NEVER 0 for a payload
;              that declared #PMF_FLAG_WANTS_SERVICES.
;    x1..x7    ZERO. Not "unspecified" - zero, so that a payload which
;              reads one gets a predictable value rather than whatever the
;              monitor happened to leave there. Kept by CallAddr() in
;              RaspberryPi4/Board/cache.pi4, in seven instructions,
;              because a guarantee that costs nothing to keep and is
;              documented as absent is a guarantee that becomes false
;              silently.
;    x8..x30   unspecified. The payload owns them.
;    SP        the payload's own stack, at the address its --stack-addr
;              declared, ALREADY SWITCHED. The payload's own prologue does
;              that switch and does it under #PMF_FLAG_RETURNS too.
;    EL        THE SAME LEVEL ANVIL RUNS AT, whatever that is. The payload
;              does NOT change it, and it MUST NOT hard-code a number.
;
;              This said "EL2, Non-secure" until 2026-09-07, and it was a
;              fact about one boot path being written down as a contract.
;              Anvil runs at EL2 when the firmware's own arm stub loads
;              it and at EL3 when RaspberryPi4/Board/armstub8.asm does,
;              and a payload is entered at whichever it is. At EL3 the
;              world is Secure, so "Non-secure" was wrong there too.
;
;              THIS IS NOT AN ABI BREAK AND DID NOT RAISE THE MAJOR, for
;              a reason worth stating rather than assuming: no slot's
;              signature changed and no payload can observe the level
;              except through SvcMmuState() and its own CurrentEL read,
;              both of which already answered truthfully. What changed is
;              this sentence, which promised more than the monitor knew.
;              A payload that BUILT IN the number 2 was relying on
;              something never guaranteed - the line above it says the
;              same about the MMU and the caches, and for the same
;              reason: ASK, do not assume.
;
;              PHASE 2 will drop the payload to EL2 or EL1 under an EL3
;              monitor, with an SMC gate in place of the direct function
;              pointers in this table - a lower level cannot call an EL3
;              address. That IS an ABI change and it will raise the
;              major. Phase 1 calls payloads at the monitor's own level
;              so that this table and every proof over it stay exactly
;              as they are.
;    MMU and   WHATEVER STATE ANVIL IS IN, which is not fixed and must not
;    caches    be assumed. SvcMmuState() answers; the payload ASKS rather
;              than guessing. (In practice RunAt hands over with the
;              caches off, but that is behaviour, not contract.)
;    IRQs      masked at DAIF. Anvil's fault vectors are installed and
;              stay installed.
;    image     placed at `load`, digest-verified AT THAT ADDRESS, BSS
;              zeroed - all by Anvil/Core/pmfboot.pbi before entry.
;    cores 1-3 parked. ABI 1.0 IS CORE-0 ONLY - see THE RE-ENTRANCY
;              CONSTRAINT below.
;    deadman   armed if the operator armed it. THE PAYLOAD CALLS SvcPet()
;              IN ITS OWN LOOP. Anvil never pets it on the payload's
;              behalf, because a monitor that petted a watchdog for a
;              program it is not running would have disarmed the one thing
;              that makes a bricked truck impossible.
;
;  CALLING CONVENTION for every slot: the standard one this backend
;  already emits. Arguments in x0-x7, return in x0, x19-x28 callee-saved.
;  A slot never writes the payload's stack below SP.
;
;  GETTING OUT, three ways, all explicit:
;    SvcReturn()  back to the prompt. Does not return. REQUIRES
;                 #PMF_FLAG_RETURNS; without it the call is a no-op that
;                 returns #SVC_EFLAG, so a mis-built payload finds out at
;                 the call rather than by vanishing.
;    SvcReboot()  reset the board. Does not return.
;    a hang       the deadman fires, boot.fails is already on the medium,
;                 three failures and the prompt comes back naming the
;                 guard. THIS IS THE PATH THAT MAKES A BRICKED TRUCK
;                 IMPOSSIBLE AND IT MUST NOT BE WEAKENED.
;
; ----------------------------------------------------------------------
;  THE RE-ENTRANCY CONSTRAINT, and it is the thing most likely to sink a
;  payload written against this ABI by somebody who has not read it.
; ----------------------------------------------------------------------
;  EVERY PROCEDURE PARAMETER IN THIS LANGUAGE IS A STATIC GLOBAL
;  (IRCore_A64.pbi:2315-2349). Locals are static .bss slots. NO PROCEDURE
;  IN THIS LANGUAGE IS RE-ENTRANT, and that is not a Pi 4 fact - it is a
;  compiler fact. It is why RaspberryPi4/Lib/sched.pi4 is cooperative
;  rather than pre-emptive, why per-task stacks would not have helped, and
;  why the GIC driver found no customer.
;
;  Three consequences, all of them constraints on this ABI:
;
;    * THE ABI IS CALL-AND-RETURN ONLY. ANVIL NEVER CALLS BACK INTO THE
;      PAYLOAD. No callbacks, no handlers, no "register a function and I
;      will call it". Where a future service seems to want one it wants a
;      QUEUE instead - which is exactly why SvcTouchPoll and SvcVehPoll
;      are polls and not callbacks.
;    * A SLOT MUST NOT BE CALLED FROM AN INTERRUPT HANDLER. The handler
;      would clobber the parameters of a call the main line is inside.
;      Interrupts are masked at entry and the payload has no reason to
;      unmask them.
;    * ABI 1.0 IS CORE 0 ONLY. RaspberryPi4/Lib/smp.pi4 can wake the other
;      three and a payload may use them for PURE COMPUTATION - but no slot
;      may be called from any core but the one that was entered.
;
;  The witness for this constraint is a FAILING-BY-DESIGN payload, kept so
;  that nobody later concludes the constraint was theoretical. It lives in
;  the Hardy repo under device/, with the negative controls.
;
; ----------------------------------------------------------------------
;  THE VERSIONING RULE - THE WHOLE CONTRACT
; ----------------------------------------------------------------------
;    * A SLOT'S MEANING IS FIXED FOR THE LIFE OF #SVC_ABI_MAJOR. Slots are
;      never reordered and never removed.
;    * NEW SERVICES ARE APPENDED INSIDE THEIR GROUP'S RESERVED BLOCK and
;      #SVC_ABI_MINOR rises. An old payload reads entry_count, sees fewer
;      slots than the newest Anvil has, and works - it simply does not
;      know about the new ones.
;    * #SVC_ABI_MAJOR RISES ONLY WHEN AN EXISTING SLOT CHANGES MEANING,
;      and that should approximately never happen.
;    * GROUPS HAVE RESERVED ROOM precisely so that appending a service
;      never pushes another group's slots along. A GROUP THAT FILLS ITS
;      BLOCK GETS A NEW BLOCK AT THE END, NOT A RENUMBERING.
; ======================================================================

; ----------------------------------------------------------------------
;  THE HEADER'S FOUR WORDS AND THE TABLE'S SHAPE
;
;    +0   u32  magic        'ANVS'
;    +4   u32  abi_major
;    +8   u32  abi_minor
;    +12  u32  entry_count
;    +16  ptr  slot 0
;    +24  ptr  slot 1
;         ...  entry_count pointers, 8 bytes each
;
;  Total at 1.0: 16 + 184*8 = 1488 bytes.
; ----------------------------------------------------------------------
#SVC_MAGIC       = $53564E41   ; 'ANVS' little-endian: bytes 41 4E 56 53
; #SVC_ABI_MAJOR / #SVC_ABI_MINOR live in Anvil/Hal/abi_version.pbi, included
; ahead of this file, so a probe with no service table reads the same number.
; #SVC_SLOT_COUNT (184 at 1.0) lives in abi_version.pi4 with the version.
#SVC_HDR_WORDS   = 2           ; header words, in 64-bit units (16 bytes)

; ----------------------------------------------------------------------
;  THE VERSION GATE - WHAT THE PAYLOAD CHECKS ON ENTRY, AND WHY IT IS
;  TWO DIFFERENT REFUSALS RATHER THAN ONE.
;
;  Ruling, 2026-09-04: the table carries major.minor, the payload records
;  what it was built against, and ON ENTRY it compares and refuses in a
;  full sentence with the code when this table is OLDER than it needs.
;  The code is #SVC_EABI.
;
;  MINOR OLDER, SAME MAJOR - "this Anvil is 1.0 and I need 1.4".
;  A minor bump only ever APPENDS slots inside a group's reserved block,
;  so every slot this older table DOES have still means what the payload
;  was told it means. The payload may therefore call slots, and it
;  refuses the way a payload should refuse: it draws the sentence itself,
;  through the console group, naming both versions. It does not proceed,
;  because the services it was written against are genuinely not there.
;
;  MAJOR DIFFERENT - "this Anvil is 1.x and I was built for 2.x".
;  THE PAYLOAD MUST NOT CALL A SINGLE SLOT, and this is the part that is
;  easy to get wrong. A major bump is defined as an existing slot
;  CHANGING MEANING, so a payload built for major 2 holds major 2's slot
;  numbers; calling slot 30 on a major 1 table reaches whatever major 1
;  put at 30, with the arguments major 2 specified. That is not a refusal,
;  it is a wrong call that returns - the worst failure this table can
;  have, and the one nothing downstream would catch.
;
;  SO THE ONLY THING GUARANTEED ACROSS A MAJOR IS THESE SIXTEEN HEADER
;  BYTES. Magic at +0, major at +4, minor at +8, entry_count at +12,
;  forever, in every major there will ever be. A payload that finds a
;  major it does not know reads those four words, writes its verdict
;  where the operator can read it, and returns without touching the
;  table - which on this monitor means Anvil's own "returned, x0 = N"
;  line and the payload's result block, printed by `md`. Anvil owns the
;  console again the moment the payload returns, and that is the right
;  place for a sentence the payload cannot safely draw.
;
;  A NEWER TABLE IS NOT AN ERROR. Same major, minor equal or higher: the
;  payload proceeds. It simply does not know about the slots that were
;  appended after it was built, which is the whole point of appending.
; ----------------------------------------------------------------------

; ----------------------------------------------------------------------
;  THE ERROR CONVENTION - full sentences, with the code, rendered by the
;  PAYLOAD.
;
;  House rule, 2026-09-03: every error a shipped program, library or tool
;  prints is a complete sentence that keeps the numeric code, says what it
;  means, and names the first thing to check
;  (Memories/errors-are-full-sentences-with-the-code.md).
;
;  BUT ANVIL MUST NOT PRINT HERE, and this is the one place the ABI
;  diverges from the monitor's own habits. RequireCap() prints with
;  UartWriteStr because the monitor owns the console. THE PAYLOAD OWNS THE
;  CONSOLE. If Anvil printed, the sentence would land on a framebuffer the
;  payload is half way through composing, or on a UART nobody is watching
;  in a truck.
;
;  So the seam is: ANVIL OWNS THE WORDING, THE PAYLOAD OWNS THE PIXELS.
;  SvcErrText(code) hands back the whole sentence; SvcErrDetail() hands
;  back a lowercase fragment naming what actually happened on THIS board;
;  the payload composes
;
;      <what it was doing> failed at <code> (<name>): <SvcErrText>.
;      <SvcErrDetail>. Check <first thing>, <second thing>.
;
;  which is the house shape exactly, with Anvil supplying the middle -
;  because only the payload knows the driver was trying to certify a log.
;
; ----------------------------------------------------------------------
;  THE NUMBERS: -100..-199, AND WHY THEY MOVED THERE. DECIDED 2026-09-04.
; ----------------------------------------------------------------------
;  The brief originally put these at -1..-9 and resolved the overlap with
;  #HW_I2C_NACK = -2 and its siblings BY DISCIPLINE: "a slot returns
;  either #SVC_* or its group's #HW_*, never both". It offered a worker
;  the option of moving to -100..-199 instead, before anything was
;  written. THAT OPTION IS TAKEN, and this is why.
;
;  THE DISCIPLINE COULD NOT ACTUALLY BE KEPT. The I2C, GPIO and USB groups
;  in this table are STRAIGHT RE-EXPORTS of HwI2c*, HwGpio* and HwUsb* -
;  so slot 116 returns #HW_I2C_* on a board that has the bus, AND MUST
;  RETURN #SVC_ENOCAP ON A BOARD THAT DOES NOT. One register, both
;  vocabularies, unavoidably. At -2 those are the same number, and a
;  payload on a board with no I2C at all would render "no device answered
;  at that address" - a sentence that sends the operator to check wiring
;  that is not there.
;
;  That is the exact defect shape this tree has already paid for twice:
;  the RP2350's IC_RAW_INTR_STAT read, which could not tell "no device"
;  from "not connected" and said the confident thing, and #HW_I2C_TIMEOUT's
;  old "(bus wedged)", which named a cause the code could not know and was
;  wrong every time on a bare Pi 4 (forum 584).
;
;  THE RULE THAT KEEPS IT TRUE, and tools/a64/a64_abi_check.py asserts it
;  by parsing both files:
;
;      NO #HW_* ERROR CODE ANYWHERE IN hal.pi4 MAY EVER BE MORE NEGATIVE
;      THAN -99, AND NO #SVC_* CODE LESS NEGATIVE THAN -100.
;
;  The day somebody adds #HW_SPI_BUSOFF = -101 the gate goes red, instead
;  of the sentence going quietly wrong.
;
;  THE ONE EXEMPTION, AND IT IS BY NAME. A few #HW_* constants are not
;  error codes: they are impossible VALUES, put far outside the
;  measurable range precisely so that no real reading can be confused
;  with them. #HW_TEMP_NONE is -273151 millidegrees - below absolute
;  zero - and it is what the part answers when it will not say how warm
;  it is. The floor is a rule about error vocabularies and does not
;  reach those, so the gate carries them in HW_VALUE_SENTINELS, listed
;  one by one. What it does NOT exempt them from is the RANGE: a
;  sentinel sitting in -199..-100 would mean two things exactly the way
;  an error code would, so that test binds every #HW_* constant without
;  exception. Adding a sentinel means naming it in the gate, which is
;  the deliberate act a pattern match would have hidden.
; ----------------------------------------------------------------------
#SVC_OK        =    0
#SVC_ENOSYS    = -100    ; this slot is not implemented in this Anvil
#SVC_ENOCAP    = -101    ; the board does not offer this capability group
#SVC_EARG      = -102    ; a bad argument
#SVC_EBUSY     = -103    ; the resource is in use
#SVC_ETIMEOUT  = -104    ; the operation did not complete in its bound
#SVC_EIO       = -105    ; the hardware answered, and answered badly
#SVC_EPERM     = -106    ; refused on purpose - see the note it comes with
#SVC_EFLAG     = -107    ; the container did not declare the flag this needs
#SVC_ESTATE    = -108    ; called in the wrong order
#SVC_EABI      = -109    ; this table is OLDER than the payload was built
                         ; against - see the version gate below

; The bounds the gate checks. Stated as constants so the gate reads them
; rather than transcribing them, and so a reader sees the reservation.
#SVC_ERR_LO    = -199    ; the #SVC_* range is -100 .. -199 inclusive
#SVC_ERR_HI    = -100
#HW_ERR_FLOOR  =  -99    ; no #HW_* ERROR code may be below this; the
                         ; named value sentinels above are exempt from
                         ; the floor and not from the range

; ----------------------------------------------------------------------
;  RUNTIME CAPABILITY IDS, AND THIS IS THE PART THAT IS EASY TO GET WRONG.
;
;  #CAP_GPIO and its siblings are COMPILE-TIME CONSTANTS IN THE BOARD'S
;  OWN board.pi4. The payload is a separately compiled image and CANNOT
;  SEE THEM. So the ABI defines its own stable enumeration here, and
;  SvcCapGet maps it onto whatever the board declared.
;
;  THESE NUMBERS ARE PART OF THE ABI and are as frozen as the slot
;  indices. SvcCapGet of an id this Anvil does not know returns 0, NOT an
;  error - "this board does not offer it" is the honest answer for a
;  capability that had not been invented when this Anvil was built, and it
;  is what lets a newer payload run on an older monitor.
;
;  ID 9 WAS #SVCCAP_CAN UNTIL 2026-09-04, when the engine port was moved
;  to a second unit and the group became the VEHICLE LINK. The
;  NUMBER did not move, and refusing to move it is the point: nothing had
;  shipped, so renumbering was free - and the habit of renumbering a
;  frozen id when it is free starts here or never.
; ----------------------------------------------------------------------
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
#SVCCAP_MAX      = 13     ; anything above this answers 0, not an error

; Informational board identity. SvcBoardId's answer. A PAYLOAD THAT
; BRANCHES ON IT HAS BROKEN THE WHOLE POINT and the gate looks for exactly
; that; it exists so a diagnostic can print what it is talking to.
#SVC_BOARD_UNKNOWN = 0
#SVC_BOARD_PI4     = 1
#SVC_BOARD_UNOQ    = 2

; ----------------------------------------------------------------------
;  THE SLOT MAP. Fixed group bases with spare room.
;
;  Every unused slot in a reserved block points at SvcUnimplemented, which
;  returns #SVC_ENOSYS. entry_count is 184.
;
;    base  group                 reserved  used at 1.0
;      0   Core and lifecycle        16        14
;     16   Clock                      8         5
;     24   Console                   16        12
;     40   Touch                      8         4
;     48   File and storage          16        12
;     64   Settings                   8         4
;     72   Net                       24        13
;     96   USB                       12         6
;    108   GPIO                       8         6
;    116   I2C                       12         8
;    128   SPI                        8         5
;    136   UART                       8         6
;    144   Vehicle link              12        11
;    156   GNSS                      12         7
;    168   Crypto and entropy        16         8
;    184   (next group starts here)
;
;  THE VEHICLE-LINK GROUP KEPT CAN'S BASE AND CAN'S BLOCK SIZE. The
;  2026-09-04 ruling swaps what the group IS; it does not renumber the
;  table. Base 144, twelve reserved, entry_count still 184 - so GNSS is
;  still at 156 and crypto still at 168. The block is now 11 of 12 used;
;  the twelfth service takes 155 and the THIRTEENTH OPENS A NEW BLOCK AT
;  184. It does not push GNSS along.
; ----------------------------------------------------------------------
#SVC_BASE_CORE    = 0
#SVC_BASE_CLOCK   = 16
#SVC_BASE_CONSOLE = 24
#SVC_BASE_TOUCH   = 40
#SVC_BASE_FILE    = 48
#SVC_BASE_SETTING = 64
#SVC_BASE_NET     = 72
#SVC_BASE_USB     = 96
#SVC_BASE_GPIO    = 108
#SVC_BASE_I2C     = 116
#SVC_BASE_SPI     = 128
#SVC_BASE_UART    = 136
#SVC_BASE_VEH     = 144
#SVC_BASE_GNSS    = 156
#SVC_BASE_CRYPTO  = 168

; ======================================================================
;  THE TABLE ITSELF.
;
;  A Global array of 64-BIT ELEMENTS AND NOT OF BYTES, and that is
;  correctness rather than taste: every store into it is eight bytes wide,
;  and a wide store to an unaligned address on this part is an alignment
;  abort with no console message at all (DumpMem in Anvil/Core/memcmd.pbi
;  gives the reasoning at length; pmfboot.pi4 repeats it). An element
;  array is naturally aligned by declaration; a byte array poked eight at
;  a time is a bug waiting for a link-order change.
;
;  The two header words carry four 32-bit fields, packed exactly as the
;  brief's table lays them out in memory:
;
;      word 0 = magic       | (abi_major   << 32)
;      word 1 = abi_minor   | (entry_count << 32)
;
;  IT IS IN ANVIL'S OWN BSS, and that is load-bearing: HitsMonitor()
;  therefore already protects it from every operator command that takes an
;  address, so `write`, `fill` and `copy` cannot scribble on the table a
;  running payload is calling through.
; ======================================================================
Global Dim gSvcTab.i[#SVC_HDR_WORDS + #SVC_SLOT_COUNT]
Global gSvcBuilt.i             ; 1 once BuildServiceTable has filled it

; The lowercase fragment SvcErrDetail() hands back, set by whichever slot
; last failed with something board-specific to add. 0 when there is
; nothing. VALID ONLY IMMEDIATELY AFTER THE FAILING CALL, and the comment
; on SvcErrDetail says so to the payload as well.
Global gSvcDetail.i

; 1 when the container being entered declared #PMF_FLAG_RETURNS. Set by
; PmfEnter() in Anvil/Core/pmfboot.pbi immediately before the jump; see
; SvcReturn for why it is a global rather than a direct read of the flags
; word.
Global gSvcMayReturn.i

; The measured cost of the last SvcFrameEnd, in microseconds.
Global gSvcFrameUs.i
Global gSvcFrameT0.i
Global gSvcFrameOpen.i

; The scissor rectangle SvcClip installs. w = 0 means "no clip", which is
; why the initial BSS zero is the right starting state and needs no
; explicit reset.
Global gSvcClipX.i
Global gSvcClipY.i
Global gSvcClipW.i
Global gSvcClipH.i

; ======================================================================
;  SvcTableAddr() - where the table is.
;
;  A procedure and not a constant, because the address is a link-time fact
;  the compiler owns and nothing in this tree should be spelling it out.
; ======================================================================
Procedure.i SvcTableAddr()
  ProcedureReturn @gSvcTab[0]
EndProcedure

; ======================================================================
;  SvcUnimplemented() - what every reserved slot points at.
;
;  IT RETURNS A CODE RATHER THAN FAULTING, and that is the whole reason
;  the reserved slots are filled at all instead of left as zeroes. A
;  payload built against a newer ABI that calls slot 41 on this monitor
;  gets #SVC_ENOSYS and can say so; the same payload against a table of
;  null pointers takes a branch to address 0 and the board stops with
;  nothing on the wire. The gate asserts that NO SLOT IS NULL for exactly
;  this reason.
; ======================================================================
Procedure.i SvcUnimplemented()
  gSvcDetail = 0
  ProcedureReturn #SVC_ENOSYS
EndProcedure

; ======================================================================
;  GROUP 0 - CORE AND LIFECYCLE, base 0
; ======================================================================

; Slot 0/1. REDUNDANT WITH THE HEADER ON PURPOSE: a payload that got the
; table pointer wrong reads plausible garbage out of the header and finds
; out here instead, because a call through a wrong pointer faults and a
; read through one does not.
Procedure.i SvcAbiMajor()
  ProcedureReturn #SVC_ABI_MAJOR
EndProcedure

Procedure.i SvcAbiMinor()
  ProcedureReturn #SVC_ABI_MINOR
EndProcedure

; Slot 2. INFORMATIONAL ONLY. A payload that branches on this has re-forked
; the thing the whole capability model prevents; ask SvcCapGet instead.
Procedure.i SvcBoardId()
  ProcedureReturn #SVC_BOARD_ID
EndProcedure

; Slot 3. A printable name, as a POINTER - never Print() it, for the
; reason hal.pi4's footer gives: Print picks its formatter from the
; argument TYPE and an untyped pointer is not a .s, so Print(p) prints the
; ADDRESS in decimal.
Procedure.i SvcBoardName()
  ProcedureReturn HwBoardName()
EndProcedure

; Slot 4. The runtime capability question. 1 or 0 for a #SVCCAP_* id.
;
; AN UNKNOWN ID ANSWERS 0 AND NOT AN ERROR. "This board does not offer it"
; is the honest answer for a capability that had not been invented when
; this Anvil was built, and it is what lets a newer payload run on an
; older monitor without a version check at every call site.
Procedure.i SvcCapGet(cap.i)
  If cap = #SVCCAP_STORAGE  : ProcedureReturn #CAP_STORAGE  : EndIf
  If cap = #SVCCAP_NET      : ProcedureReturn #CAP_NET      : EndIf
  If cap = #SVCCAP_GPIO     : ProcedureReturn #CAP_GPIO     : EndIf
  If cap = #SVCCAP_I2C      : ProcedureReturn #CAP_I2C      : EndIf
  If cap = #SVCCAP_MMC      : ProcedureReturn #CAP_MMC      : EndIf
  If cap = #SVCCAP_USB      : ProcedureReturn #CAP_USB      : EndIf
  If cap = #SVCCAP_BOOT_EL1 : ProcedureReturn #CAP_BOOT_EL1 : EndIf
  If cap = #SVCCAP_TOUCH    : ProcedureReturn #CAP_TOUCH    : EndIf
  If cap = #SVCCAP_GNSS     : ProcedureReturn #CAP_GNSS     : EndIf
  If cap = #SVCCAP_VEHLINK  : ProcedureReturn #CAP_VEHLINK  : EndIf
  If cap = #SVCCAP_SPI      : ProcedureReturn #CAP_SPI      : EndIf
  If cap = #SVCCAP_UART     : ProcedureReturn #CAP_UART     : EndIf
  If cap = #SVCCAP_RTC      : ProcedureReturn #CAP_RTC      : EndIf
  If cap = #SVCCAP_CONSOLE  : ProcedureReturn #CAP_CONSOLE  : EndIf
  ProcedureReturn 0
EndProcedure

; Slot 5. THE GATE, and the one place this ABI diverges from RequireCap().
;
; Same semantics - 1 when the capability is present - but it RETURNS THE
; SENTENCE INSTEAD OF PRINTING IT. RequireCap prints with UartWriteStr
; because the monitor owns the console; here the PAYLOAD owns the console,
; and a sentence printed by Anvil would land on a framebuffer the payload
; is mid-way through composing, or on a UART nobody is watching in a
; truck.
;
; So on a refusal this returns 0, sets the detail fragment to the caller's
; own *reason, and the payload renders SvcErrText(#SVC_ENOCAP) plus that
; fragment itself. The wording is RequireCap's wording minus the "type
; info / type help" tail, which means nothing on a touchscreen.
Procedure.i SvcRequireCap(cap.i, *name, *reason)
  If cap <> 0
    gSvcDetail = 0
    ProcedureReturn 1
  EndIf
  gSvcDetail = *reason
  ProcedureReturn 0
EndProcedure

; Slot 6. PET THE DEADMAN. The payload's own loop calls this; Anvil never
; pets it on the payload's behalf. See the entry contract above.
Procedure SvcPet()
  HwPet()
EndProcedure

;  ----------------------------------------------------------------
;   THE TWO SETTINGS A PAYLOAD MAY NOT TOUCH, in one place.
;
;   A LITERAL CANNOT BE @'d IN THIS LANGUAGE - it wants a variable, field
;   or array element - so these are procedures returning the literal's
;   address, the same shape SettingsFileName() and PmfKeyFile() use.
;
;   THEY ARE RESTATED HERE RATHER THAN TAKEN FROM pmfboot.pi4, and that
;   is not duplication for its own sake: this file is included BEFORE
;   pmfboot.pi4 (it has to be - PmfEnter calls BuildServiceTable), so
;   PmfKeyFails() does not exist yet at this point in the build. The gate
;   asserts the two spellings match, which is the check that keeps a
;   restatement honest.
;  ----------------------------------------------------------------
Procedure.i SvcKeyFails()
  ProcedureReturn "boot.fails"
EndProcedure

Procedure.i SvcKeyMaxFails()
  ProcedureReturn "boot.maxfails"
EndProcedure

; Compare a payload-supplied key against the two guarded names. Byte at a
; time and case-sensitively, because the settings store is case-sensitive
; and a guard that was laxer than the store it guards would be a guard
; with a hole in it exactly the width of one capital letter.
Procedure.i SvcKeyMatches(*key, *want)
  Define i.i
  Define a.i
  Define b.i
  i = 0
  While 1
    a = PeekA(*key + i)
    b = PeekA(*want + i)
    If a <> b
      ProcedureReturn 0
    EndIf
    If a = 0
      ProcedureReturn 1
    EndIf
    i = i + 1
  Wend
EndProcedure

Procedure.i SvcKeyIsGuarded(*key)
  If SvcKeyMatches(*key, SvcKeyFails()) <> 0
    ProcedureReturn 1
  EndIf
  If SvcKeyMatches(*key, SvcKeyMaxFails()) <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; Slot 7. Clear boot.fails.
;
; THE PAYLOAD CALLS THIS ONCE, WHEN IT REACHES ITS OWN STEADY STATE - NOT
; AT ENTRY. boot.fails is incremented and written to the medium BEFORE the
; boot is attempted, which is the only ordering that catches a payload
; that hangs; clearing it at entry would mean the counter never survives
; anything and the loop guard protects nothing at all.
;
; IT IS THE ONLY SANCTIONED WAY TO CLEAR THE COUNTER. SvcSettingSet
; refuses the key outright - see slot 65.
Procedure.i SvcBootOk()
  If SettingsSet(SvcKeyFails(), "0") = 0
    gSvcDetail = "the settings store would not accept the write"
    ProcedureReturn #SVC_EIO
  EndIf
  If SettingsSave() = 0
    gSvcDetail = "the settings store could not be written to the medium"
    ProcedureReturn #SVC_EIO
  EndIf
  gSvcDetail = 0
  ProcedureReturn #SVC_OK
EndProcedure

; Slot 8. Back to the prompt. DOES NOT RETURN - unless the container did
; not declare #PMF_FLAG_RETURNS, in which case it is a no-op that returns
; #SVC_EFLAG.
;
; THE REFUSAL IS THE POINT. A payload built without the flag was entered
; with BLR anyway (CallAddr uses BLR precisely so a returning payload can
; be reported), so a bare "ret" here would appear to work and then behave
; unpredictably the first time somebody built it for a board where it does
; not. Answering at the call means a mis-built payload finds out with its
; console still up, instead of by vanishing.
Procedure.i SvcReturn()
  ; THE FLAG IS READ OUT OF A GLOBAL AND NOT OUT OF gPmfFlags DIRECTLY,
  ; because this file is included BEFORE Anvil/Core/pmfboot.pbi - it has
  ; to be, since PmfEnter() is the one caller of BuildServiceTable() - so
  ; #PMF_FLAG_RETURNS does not exist yet at this point in the build.
  ; PmfEnter sets gSvcMayReturn from the container's own flags word
  ; immediately before the jump. One assignment, no restated constant, and
  ; no chance of the two spellings of bit 0 drifting apart.
  If gSvcMayReturn = 0
    gSvcDetail = "this payload's container did not set bit 0, the returns-to-monitor flag"
    ProcedureReturn #SVC_EFLAG
  EndIf
  ; ------------------------------------------------------------------
  ;  NOT IMPLEMENTED IN ABI 1.0, AND THIS IS THE HONEST REASON RATHER
  ;  THAN A PLAUSIBLE ONE.
  ;
  ;  The brief specifies SvcReturn as "back to the prompt, does not
  ;  return". Delivering that means a LONGJMP: restore the monitor's SP
  ;  from gSp and branch to the instruction after CallAddr's `blr x9`.
  ;  gSp is saved and available; THE LANDING ADDRESS IS NOT. `blr` puts
  ;  it in x30, which the payload owns and has certainly overwritten by
  ;  the time it calls this, and capturing it BEFORE the branch needs a
  ;  PC-relative constant or a label inside an inline-asm block - which
  ;  is hand-written assembly whose correctness no compiler check can
  ;  see, and RULES.md rule 9 is explicit about what that costs.
  ;
  ;  So this refuses, loudly, and says what to do instead. THE WORKING
  ;  PATH IS THE PAYLOAD RETURNING FROM ITS OWN ENTRY: CallAddr enters
  ;  with BLR precisely so that a payload built --entry-returns can `ret`
  ;  back to the monitor, which is proven on silicon (2026-08-25) and is
  ;  what pi4SvcProbe does.
  ;
  ;  Owed: a board seam HwReturnToMonitor(), saving the landing address
  ;  in CallAddr beside gSp. It is small and it is not Phase A item 1.
  ; ------------------------------------------------------------------
  gSvcDetail = "this monitor cannot unwind out of a payload from inside a service call; return from the payload's own entry point instead, which is what the returns-to-monitor flag is for"
  ProcedureReturn #SVC_ENOSYS
EndProcedure

; Slot 9. Reset the board. Does not return.
Procedure.i SvcReboot()
  HwReboot()
  ProcedureReturn #SVC_OK
EndProcedure

; Slot 10. ASK, DO NOT ASSUME.
;
; bit 0 MMU on, bit 1 D-cache on, bit 2 I-cache on. The payload asks
; because Anvil's own state is not fixed: `cache on` and `cache off` are
; operator commands, RunAt hands over with the caches flushed and off
; TODAY, and none of that is contract. A payload that assumed cached DRAM
; and got uncached memory is slow; one that assumed uncached and got
; cached writes a framebuffer nobody sees.
Procedure.i SvcMmuState()
  ProcedureReturn HwMmuState()
EndProcedure

; Slot 11. Monotonic microseconds since Anvil started. NEVER GOES
; BACKWARDS, NEVER JUMPS. Duplicated at slot 16 as SvcTicks because the
; clock group needs it too; both call the same code, so the two cannot
; drift.
Procedure.i SvcUptimeUs()
  ProcedureReturn HwMicros()
EndProcedure

; Slot 12. THE WHOLE SENTENCE for a code, keeping the number - as a
; POINTER. The number stays in the text so that an old thread, an old log
; line and an old screenshot still match.
Procedure.i SvcErrText(code.i)
  If code = #SVC_OK
    ProcedureReturn "the operation completed at code 0 (SVC_OK)"
  EndIf
  If code = #SVC_ENOSYS
    ProcedureReturn "this monitor has no code for that service at all, at code -100 (SVC_ENOSYS): the payload is asking for something newer than the Anvil it is running on"
  EndIf
  If code = #SVC_ENOCAP
    ProcedureReturn "this board does not offer that hardware group at code -101 (SVC_ENOCAP): the service exists in this monitor and the board it is running on cannot reach the hardware"
  EndIf
  If code = #SVC_EARG
    ProcedureReturn "one of the arguments was not usable at code -102 (SVC_EARG)"
  EndIf
  If code = #SVC_EBUSY
    ProcedureReturn "the resource is already in use at code -103 (SVC_EBUSY)"
  EndIf
  If code = #SVC_ETIMEOUT
    ProcedureReturn "the operation did not finish in its time bound at code -104 (SVC_ETIMEOUT)"
  EndIf
  If code = #SVC_EIO
    ProcedureReturn "the hardware answered, and answered badly, at code -105 (SVC_EIO)"
  EndIf
  If code = #SVC_EPERM
    ProcedureReturn "this monitor refused on purpose at code -106 (SVC_EPERM): it is not a fault, and the service that returned it says why"
  EndIf
  If code = #SVC_EFLAG
    ProcedureReturn "the payload's container did not declare the flag this service needs, at code -107 (SVC_EFLAG): rebuild it with that flag set"
  EndIf
  If code = #SVC_ESTATE
    ProcedureReturn "this service was called in the wrong order at code -108 (SVC_ESTATE): something has to be brought up first"
  EndIf
  If code = #SVC_EABI
    ProcedureReturn "this monitor's service table is older than the payload was built against, at code -109 (SVC_EABI): update the monitor, or rebuild the payload against the version this monitor offers - the two numbers are in the payload's own refusal"
  EndIf
  ProcedureReturn "this monitor has no sentence for that code, which means it did not come from the service table's own error set"
EndProcedure

; Slot 13. A LOWERCASE FRAGMENT naming what actually happened on THIS
; board, valid only immediately after the failing call. 0 when the board
; has nothing to add.
;
; IT IS DELIBERATELY NOT LATCHED. A detail that survived until the next
; failure would be attached to the wrong call exactly when somebody was
; reading it, which is the failure mode HwAddrReason() and
; HwI2cPinFunc() both carry the same warning about.
Procedure.i SvcErrDetail()
  ProcedureReturn gSvcDetail
EndProcedure

; ======================================================================
;  GROUP 1 - CLOCK, base 16
;
;  THERE IS NO SETTER, AND ITS ABSENCE IS A REQUIREMENT RATHER THAN AN
;  OMISSION. 49 CFR 395 Appendix A 4.3.1.5(a) requires an ELD to obtain
;  date and time "automatically without allowing any external input or
;  interference from a motor carrier, driver, or any other person". Anvil
;  sets its own clock from GNSS and the RTC. A PAYLOAD THAT COULD SET THE
;  CLOCK WOULD BE A PAYLOAD THAT COULD BE MADE TO LIE, so the slot does
;  not exist and there is nothing to refuse.
; ======================================================================

; NOBODY HAS TOLD THIS BOARD WHAT TIME IT IS, and on the Pi 4 that is a
; measured fact rather than an omission: THE PART HAS NO RTC. The gate
; re-checks the premise on every run by grepping the four device trees for
; an rtc@ node - five hits, all of them uartclk (Raspberry Pi 4/A wall
; clock and a task list 2026-08-28). #CAP_RTC = 1 on this board would mean
; a DS3231 is wired to I2C, and none is; #CAP_GNSS = 1 would mean a
; receiver is on a UART, and none is. So every cold boot starts
; #HW_CLK_UNSET and the ELD refuses to record until something
; authoritative arrives.
;
; A SEPARATE PROCEDURE, called by both slot 17 and slot 18, so that "what
; time is it" and "how much do you trust it" cannot answer differently.
Procedure.i SvcClockProv()
  ProcedureReturn #HW_CLK_UNSET
EndProcedure

; Slot 16. Monotonic microseconds since Anvil started. Wraps at 2^63 us,
; which is about 292,000 years.
Procedure.i SvcTicks()
  ProcedureReturn HwMicros()
EndProcedure

; Slot 17. Fill a seven-field record - year, month, day, hour, minute,
; second, millisecond - with UTC, as seven 32-bit fields.
;
; IT RETURNS A PROVENANCE CODE AND NOT A SUCCESS FLAG, because "what time
; is it" and "how much do you trust it" are one answer and splitting them
; is how a #HW_CLK_RESTORED floor gets logged as a measurement.
Procedure.i SvcUtc(*out)
  Define i.i
  If *out = 0
    gSvcDetail = "the record pointer was zero"
    ProcedureReturn #SVC_EARG
  EndIf
  ; THE RECORD IS ALWAYS FILLED, even when there is no time to put in it,
  ; so that a caller reading it back after a failure gets seven zeroes
  ; rather than whatever was in its buffer. Seven 32-bit fields: year,
  ; month, day, hour, minute, second, millisecond.
  i = 0
  While i < 28
    PokeB(*out + i, 0)
    i = i + 1
  Wend
  ProcedureReturn SvcClockProv()
EndProcedure

; Slot 18. The same code without filling anything.
Procedure.i SvcClockProvenance()
  ProcedureReturn SvcClockProv()
EndProcedure


; Slot 19. HOW FAR THE CLOCK COULD BE OFF RIGHT NOW, worst case, in
; milliseconds, given the provenance and the elapsed time since the last
; authoritative sync.
;
; THIS IS THE NUMBER THE ELD'S TIMING-COMPLIANCE MALFUNCTION (code T) IS
; COMPUTED FROM, so it must be derived from a written-down oscillator
; bound and never guessed. -1 means "there has never been an
; authoritative sync", which is not a large uncertainty - it is no
; measurement at all, and the caller must not treat it as a number.
Procedure.i SvcClockUncertaintyMs()
  If SvcClockProv() = #HW_CLK_UNSET
    ; -1 IS NOT A LARGE UNCERTAINTY. It is no measurement at all, and a
    ; caller that averaged it into a bound would be inventing a number.
    ProcedureReturn -1
  EndIf
  ProcedureReturn -1
EndProcedure

; Slot 20. SvcTicks() at the last authoritative sync, or -1 if never.
Procedure.i SvcUtcLastSyncTicks()
  ProcedureReturn -1
EndProcedure


; ======================================================================
;  GROUP 2 - CONSOLE, base 24
;
;  THE PAYLOAD OWNS THE PIXELS; ANVIL OWNS THE DEVICE. Everything here
;  rides the HwCon* seam the board supplies (on the Pi 4,
;  RaspberryPi4/Board/hw_con.pi4), so this file names no surface format
;  and no font.
;
;  THE CLIPPING IS DONE HERE AND NOT IN THE BACKEND, deliberately.
;  Intersecting two rectangles is arithmetic, not silicon, and doing it in
;  the core means it is the SAME arithmetic on every board and can be
;  proved by tools/a64/a64_abi_check.py with no board at all. The backend
;  still refuses a range it cannot draw - two checks on the one path that
;  would otherwise write outside the surface, which is the class of bug
;  that corrupts something else entirely and is diagnosed hours later.
;
;  Compiled only where the board declares #CAP_CONSOLE. Elsewhere these
;  slots keep pointing at SvcUnimplemented and answer #SVC_ENOSYS.
; ======================================================================
CompilerIf #CAP_CONSOLE = 1

Procedure.i SvcScreenWidth()
  ProcedureReturn HwConWidth()
EndProcedure

Procedure.i SvcScreenHeight()
  ProcedureReturn HwConHeight()
EndProcedure

; INFORMATIONAL. The payload draws the same either way; this is here so
; that a measured frame time can be read against the path that produced
; it rather than against an assumption.
Procedure.i SvcScreenTier()
  ProcedureReturn HwConTier()
EndProcedure

; Claim the surface. #SVC_OK, or #SVC_EIO when the board has no
; framebuffer to give - which is a real state on this part, because the
; mailbox can decline.
;
; IT REFUSES A SECOND BEGIN WITHOUT AN END. #SVC_ESTATE rather than a
; silent re-entry, because the frame cost measured across a nested pair
; would be the inner frame's and would be reported as the outer one's.
Procedure.i SvcFrameBegin()
  If gSvcFrameOpen <> 0
    gSvcDetail = "a frame is already open; end it before beginning another"
    ProcedureReturn #SVC_ESTATE
  EndIf
  If HwConFrameBegin() = 0
    gSvcDetail = "this board has no framebuffer to draw into"
    ProcedureReturn #SVC_EIO
  EndIf
  gSvcFrameOpen = 1
  gSvcFrameT0 = HwMicros()
  ; A NEW FRAME STARTS UNCLIPPED. A scissor left over from the previous
  ; frame is the bug where half the screen stops redrawing and nothing in
  ; the drawing code is wrong.
  gSvcClipW = 0
  gSvcClipH = 0
  gSvcDetail = 0
  ProcedureReturn #SVC_OK
EndProcedure

Procedure.i SvcFrameEnd()
  If gSvcFrameOpen = 0
    gSvcDetail = "no frame was open"
    ProcedureReturn #SVC_ESTATE
  EndIf
  HwConFrameEnd()
  ; MEASURED HERE, ACROSS THE WHOLE FRAME, because that is the number the
  ; ELD's phase-1 proof is stated in and a number measured over part of a
  ; frame looks exactly like one measured over all of it.
  gSvcFrameUs = HwMicros() - gSvcFrameT0
  gSvcFrameOpen = 0
  gSvcDetail = 0
  ProcedureReturn #SVC_OK
EndProcedure

; THE ONE PRIMITIVE THE WHOLE UI IS BUILT FROM. Clipped against the
; scissor here, then handed to the board.
Procedure SvcRect(x.i, y.i, w.i, h.i, argb.i)
  Define x2.i
  Define y2.i
  Define cx2.i
  Define cy2.i
  If w <= 0 Or h <= 0
    ProcedureReturn
  EndIf
  If gSvcClipW > 0 And gSvcClipH > 0
    x2 = x + w
    y2 = y + h
    cx2 = gSvcClipX + gSvcClipW
    cy2 = gSvcClipY + gSvcClipH
    If x < gSvcClipX : x = gSvcClipX : EndIf
    If y < gSvcClipY : y = gSvcClipY : EndIf
    If x2 > cx2 : x2 = cx2 : EndIf
    If y2 > cy2 : y2 = cy2 : EndIf
    w = x2 - x
    h = y2 - y
    If w <= 0 Or h <= 0
      ProcedureReturn
    EndIf
  EndIf
  HwConRect(x, y, w, h, argb)
EndProcedure

; y IS THE BASELINE. px is the height the caller WANTS; this board has one
; size and reports it through SvcTextHeight, so a caller that lays out
; against px rather than against what it got will draw outside its boxes.
; Said in the seam rather than discovered on a screen.
;
; NOT SCISSORED. The rasteriser underneath blends each glyph against a
; background colour without reading the surface, so a partial glyph cannot
; be composited correctly and half-drawing one would look like a font bug.
; A caller that needs clipped text draws the panel, then the text, and
; keeps the run inside the panel - which is what every screen in the ELD
; mockups already does.
Procedure.i SvcText(x.i, y.i, *utf8, argb.i, px.i, bg.i)
  ProcedureReturn HwConText(x, y, *utf8, argb, bg)
EndProcedure

Procedure.i SvcTextWidth(*utf8, px.i)
  ProcedureReturn HwConTextWidth(*utf8)
EndProcedure

; The single height this board draws text at. NOT in the brief's slot
; list and appended inside the console group's reserved block, which is
; what that room is for; abi_minor stays 0 because nothing has shipped.
Procedure.i SvcTextHeight()
  ProcedureReturn HwConTextHeight()
EndProcedure

; w = 0 CLEARS IT. That spelling is deliberate: the cleared state is the
; BSS zero, so a frame that never sets a scissor and a frame that cleared
; one are the same state and there is no third case to get wrong.
Procedure SvcClip(x.i, y.i, w.i, h.i)
  gSvcClipX = x
  gSvcClipY = y
  gSvcClipW = w
  gSvcClipH = h
EndProcedure

; THE DUTY-STATUS GRAPH GRID IS A LINE LIST AND NOTHING ELSE IN THE UI
; NEEDS ONE, which is why this earns a slot rather than being left to the
; payload to build out of rectangles.
;
; HORIZONTAL AND VERTICAL ONLY IN 1.0, and it refuses a diagonal rather
; than approximating one. Every line the grid draws is axis-aligned; a
; Bresenham walk that nothing calls is code that is never exercised and
; is therefore wrong when it finally is. The refusal is silent because
; this slot has no return value in the frozen signature - so the payload
; sees a line that did not appear, which is loud in the only channel a
; drawing primitive has.
Procedure SvcLine(x0.i, y0.i, x1.i, y1.i, argb.i, wpx.i)
  Define t.i
  If wpx <= 0
    wpx = 1
  EndIf
  If y0 = y1
    If x1 < x0
      t = x0 : x0 = x1 : x1 = t
    EndIf
    SvcRect(x0, y0, x1 - x0 + 1, wpx, argb)
    ProcedureReturn
  EndIf
  If x0 = x1
    If y1 < y0
      t = y0 : y0 = y1 : y1 = t
    EndIf
    SvcRect(x0, y0, wpx, y1 - y0 + 1, argb)
    ProcedureReturn
  EndIf
EndProcedure

; Microseconds the last SvcFrameEnd took. THE ELD'S PHASE-1 PROOF IS A
; MEASURED FRAME TIME AND THIS IS WHERE IT COMES FROM.
Procedure.i SvcFrameCostUs()
  ProcedureReturn gSvcFrameUs
EndProcedure

Procedure.i SvcBacklight(pct.i)
  If pct < 0 Or pct > 100
    gSvcDetail = "a backlight level outside 0 to 100"
    ProcedureReturn #SVC_EARG
  EndIf
  If HwConBacklight(pct) < 0
    gSvcDetail = "this board drives no backlight it can set - an HDMI monitor owns its own brightness"
    ProcedureReturn #SVC_ENOSYS
  EndIf
  ProcedureReturn #SVC_OK
EndProcedure

CompilerEndIf

; ======================================================================
;  GROUP 3 - TOUCH, base 40
;
;  A touch surface is not a mouse and the difference is the whole reason
;  this is its own group. THERE IS NO HOVER, THERE IS NO BUTTON, THERE IS
;  NO CURSOR, and there are up to ten simultaneous contacts. A UI written
;  against a mouse and handed touch events has a hover state that never
;  clears and a right-click that never comes.
;
;  THE SEAM IS WRITTEN, AND THESE ANSWER OVER IT - changed 2026-09-08.
;  Until then all four returned #SVC_ENOSYS on the one board that has
;  the hardware, which was the honest reading of "the board has a touch
;  controller and this monitor cannot offer it to you". The Raspberry
;  Pi 4's HwTouch* backend is RaspberryPi4/Board/hw_touch.pi4 over
;  Lib/touch_goodix.pi4, so that sentence is no longer true there.
;
;  A BOARD WITHOUT THE HARDWARE STILL ANSWERS #SVC_ENOCAP, and the pair
;  is still the point: "no touch surface here" sends an operator to
;  check wiring, "this monitor cannot offer you the one it has" sends
;  them to a release note. The seam is documented in Anvil/Hal/hal.pbi;
;  its 32-byte record layout is part of the portable vocabulary and the
;  BOARD fills it with SCREEN pixels, already turned and scaled, so no
;  payload ever learns which way up the panel is bolted.
;
;  THE CompilerIf IS ON THE CAPABILITY AND NOT ON A BOARD NAME. A board
;  that declares #CAP_TOUCH = 0 provides no HwTouch* backend at all -
;  there is nothing to link against - so the ENOSYS arm below is what
;  compiles there. The gate refuses first either way; this is what keeps
;  the file building on both boards.
; ======================================================================
CompilerIf #CAP_TOUCH = 1

Procedure.i SvcTouchPoll(*ev)
  Define r.i
  If SvcRequireCap(#CAP_TOUCH, "touch", "this board has no touch surface Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  If *ev = 0
    gSvcDetail = "a null pointer where the 32-byte touch event record was meant to go"
    ProcedureReturn #SVC_EARG
  EndIf
  ; THE CONTROLLER IS READ HERE AS WELL AS ON THE PROMPT'S SPIN. A
  ; payload that has taken the machine is not going round the monitor's
  ; line editor, so nothing else would ever poll the part - and a queue
  ; that only fills while somebody is typing is a queue that is always
  ; empty. HwTouchTick rate-limits itself, so a payload draining in a
  ; tight loop still costs one I2C frame every 17 ms.
  HwTouchTick()
  r = HwTouchPoll(*ev)
  If r < 0
    gSvcDetail = "the touch controller's event queue could not be read"
    ProcedureReturn #SVC_EIO
  EndIf
  ProcedureReturn r
EndProcedure

Procedure.i SvcTouchQueued()
  If SvcRequireCap(#CAP_TOUCH, "touch", "this board has no touch surface Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  HwTouchTick()
  ProcedureReturn HwTouchQueued()
EndProcedure

; A UI CALLS THIS ON EVERY SCREEN CHANGE. A tap that was queued against
; the previous screen and lands on the new one is the bug that makes a
; driver change duty status by accident.
Procedure.i SvcTouchFlush()
  If SvcRequireCap(#CAP_TOUCH, "touch", "this board has no touch surface Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  HwTouchFlush()
  ProcedureReturn #SVC_OK
EndProcedure

; HOW MANY CONTACTS THE CONTROLLER SAYS IT IS PROGRAMMED FOR, which is
; not the same as how many the part could do: its config block declares
; the number and a frame claiming more is refused against it.
;
; ZERO BEFORE ANYTHING HAS COME UP is not a third meaning of "no touch".
; #SVC_ENOCAP is how a board says it has none; a 0 here means the
; controller has not been asked yet, which this call then does.
Procedure.i SvcTouchMaxPoints()
  If SvcRequireCap(#CAP_TOUCH, "touch", "this board has no touch surface Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  If HwTouchReady() = 0
    HwTouchUp()
  EndIf
  ProcedureReturn HwTouchMaxPoints()
EndProcedure

CompilerElse

Procedure.i SvcTouchPoll(*ev)
  If SvcRequireCap(#CAP_TOUCH, "touch", "this board has no touch surface Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcTouchQueued()
  If SvcRequireCap(#CAP_TOUCH, "touch", "this board has no touch surface Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcTouchFlush()
  If SvcRequireCap(#CAP_TOUCH, "touch", "this board has no touch surface Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcTouchMaxPoints()
  If SvcRequireCap(#CAP_TOUCH, "touch", "this board has no touch surface Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

CompilerEndIf

; ======================================================================
;  GROUP 4 - FILE AND STORAGE, base 48
;
;  A straight re-export of the existing HwFile* seam. NO NEW SEMANTICS,
;  with the single exception of SvcFileAppend - see slot 55.
; ======================================================================
Procedure.i SvcStorageUp()
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwStorageUp()
EndProcedure

Procedure.i SvcFileOpen(*name)
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  If *name = 0
    gSvcDetail = "the name pointer was zero"
    ProcedureReturn #SVC_EARG
  EndIf
  ProcedureReturn HwFileOpen(*name)
EndProcedure

Procedure.i SvcFileSize()
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwFileSize()
EndProcedure

Procedure.i SvcFileReadAt(off.i, dst.i, n.i)
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  If off < 0 Or n < 0 Or dst = 0
    gSvcDetail = "a negative offset or length, or a zero destination"
    ProcedureReturn #SVC_EARG
  EndIf
  ProcedureReturn HwFileReadAt(off, dst, n)
EndProcedure

Procedure.i SvcFileClose()
  HwFileClose()
  ProcedureReturn #SVC_OK
EndProcedure

Procedure.i SvcFileWritable()
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwFileWritable()
EndProcedure

Procedure.i SvcFileWriteAll(*name, src.i, n.i)
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  If *name = 0 Or src = 0 Or n < 0
    gSvcDetail = "a zero name or source pointer, or a negative length"
    ProcedureReturn #SVC_EARG
  EndIf
  ProcedureReturn HwFileWriteAll(*name, src, n)
EndProcedure

; Slot 55. APPEND, AND IT IS NOT OPTIONAL.
;
; hal.pi4 deliberately offered only whole-file write, because "every
; writer the core has - the settings store - rewrites its file completely,
; and a partial write API would be a capability nothing uses and every
; board has to implement". THAT REASONING WAS CORRECT AND IT IS NOW OUT OF
; DATE: an ELD's log is append-only and grows to megabytes, and rewriting
; it on every duty-status change is O(n-squared) writes on flash and would
; burn the stick out.
;
; THE CONTRACT THAT MAKES IT SAFE: it appends ALL n bytes or NONE, and a
; board that cannot promise that answers #HW_FILE_READONLY from
; HwFileWritable() rather than appending unsafely.
;
; NOT YET IMPLEMENTED ON ANY BOARD. Phase A item 3 (fat.pi4 writes the
; data clusters first and the directory entry's size last, so a power cut
; mid-append leaves a file that is SHORT BUT NOT CORRUPT). Until then this
; answers #SVC_ENOSYS, which is the truth, rather than falling back to a
; read-modify-write that would silently be the O(n-squared) path this slot
; exists to avoid.
Procedure.i SvcFileAppend(*name, src.i, n.i)
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  If *name = 0 Or src = 0 Or n < 0
    gSvcDetail = "a zero name or source pointer, or a negative length"
    ProcedureReturn #SVC_EARG
  EndIf
  gSvcDetail = "no board in this Anvil implements an all-or-nothing append yet"
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcFileLastError()
  ProcedureReturn HwFileLastError()
EndProcedure

Procedure.i SvcFileErrText()
  ProcedureReturn HwFileErrorText()
EndProcedure

Procedure.i SvcFileCanList()
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwFileCanList()
EndProcedure

Procedure.i SvcDirOpen()
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwDirRewind()
EndProcedure

; Fills eleven raw bytes - eight of base and three of extension,
; space-padded, no dot stored - which is #HW_DIR_NAME_LEN and the shape
; hal.pi4 defines. Returns 1 when a name was written, 0 at the end.
Procedure.i SvcDirNext(*name11)
  If SvcRequireCap(#CAP_STORAGE, "storage", "this board offers Anvil no medium to read files from") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  If *name11 = 0
    gSvcDetail = "the name buffer pointer was zero"
    ProcedureReturn #SVC_EARG
  EndIf
  If HwDirNext() = 0
    ProcedureReturn 0
  EndIf
  HwDirName(*name11)
  ProcedureReturn 1
EndProcedure

Procedure.i SvcDirClose()
  ProcedureReturn #SVC_OK
EndProcedure

; ======================================================================
;  GROUP 5 - SETTINGS, base 64
; ======================================================================

; Slot 64. Bytes written into *buf, or negative.
Procedure.i SvcSettingGet(*key, *buf, n.i)
  Define src.i
  Define i.i
  Define c.i
  If *key = 0 Or *buf = 0 Or n <= 0
    gSvcDetail = "a zero key or buffer pointer, or a length of zero"
    ProcedureReturn #SVC_EARG
  EndIf
  src = SettingsGet(*key)
  If src = 0
    ProcedureReturn 0
  EndIf
  ; COPIED OUT AND NOT HANDED BACK BY POINTER, deliberately. SettingsGet
  ; returns a pointer INTO the store's own table, which a later
  ; SettingsSet moves - so a payload that held it across one write would
  ; be reading whatever landed there afterwards. pmfboot.pi4 copies the
  ; boot file name for exactly this reason and says so.
  i = 0
  While i < (n - 1)
    c = PeekA(src + i)
    If c = 0
      Break
    EndIf
    PokeB(*buf + i, c)
    i = i + 1
  Wend
  PokeB(*buf + i, 0)
  ProcedureReturn i
EndProcedure

; Slot 65. Persist a setting.
;
; IT REFUSES boot.fails AND boot.maxfails, and that refusal is the one
; thing standing between a bad update and a truck that needs a laptop. A
; payload that could clear its own failure counter could defeat the
; reboot-loop guard, and the guard is what turns "the new firmware hangs"
; from a dead board into a prompt that says why. THE PAYLOAD MAY set
; boot.file - that is how firmware update works - and it may clear the
; counter through SvcBootOk() at its own steady state, which is the whole
; point of that being a separate slot.
Procedure.i SvcSettingSet(*key, *val)
  If *key = 0 Or *val = 0
    gSvcDetail = "a zero key or value pointer"
    ProcedureReturn #SVC_EARG
  EndIf
  If SvcKeyIsGuarded(*key) <> 0
    gSvcDetail = "boot.fails and boot.maxfails are the reboot-loop guard, and a payload that could set them could defeat it; call the boot-ok service at steady state instead"
    ProcedureReturn #SVC_EPERM
  EndIf
  If SettingsSet(*key, *val) = 0
    gSvcDetail = "the settings store would not accept the write"
    ProcedureReturn #SVC_EIO
  EndIf
  gSvcDetail = 0
  ProcedureReturn #SVC_OK
EndProcedure

Procedure.i SvcSettingSave()
  If SettingsSave() = 0
    gSvcDetail = "the settings store could not be written to the medium"
    ProcedureReturn #SVC_EIO
  EndIf
  gSvcDetail = 0
  ProcedureReturn #SVC_OK
EndProcedure

Procedure.i SvcSettingDel(*key)
  If *key = 0
    gSvcDetail = "the key pointer was zero"
    ProcedureReturn #SVC_EARG
  EndIf
  If SvcKeyIsGuarded(*key) <> 0
    gSvcDetail = "boot.fails and boot.maxfails are the reboot-loop guard, and deleting one is the same defeat as setting it"
    ProcedureReturn #SVC_EPERM
  EndIf
  If SettingsRemove(*key) = 0
    ; NOT AN ERROR WHEN THE KEY WAS NEVER THERE. Deleting something that
    ; does not exist has already achieved what the caller asked for, and
    ; answering #SVC_EIO would send a payload looking for a medium fault
    ; that is not there - the same distinction #HW_FILE_NOTFOUND exists
    ; to make.
    gSvcDetail = 0
    ProcedureReturn #SVC_OK
  EndIf
  gSvcDetail = 0
  ProcedureReturn #SVC_OK
EndProcedure

; ======================================================================
;  GROUP 7 - USB, base 96
;
;  A straight re-export of HwUsb*, speaking the same #HW_USB_* vocabulary.
;  hal.pi4 is the authority for the contract and it is not repeated here;
;  what IS here is the slot numbering, which is frozen.
; ======================================================================
Procedure.i SvcUsbEnumerate()
  If SvcRequireCap(#CAP_USB, "usb", "this board exposes no USB host to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwUsbEnumerate()
EndProcedure

Procedure.i SvcUsbDevCount()
  If SvcRequireCap(#CAP_USB, "usb", "this board exposes no USB host to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwUsbTree()
EndProcedure

Procedure.i SvcUsbDevKind(i.i)
  If SvcRequireCap(#CAP_USB, "usb", "this board exposes no USB host to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwUsbDevKind(i)
EndProcedure

Procedure.i SvcUsbStorageReady()
  If SvcRequireCap(#CAP_USB, "usb", "this board exposes no USB host to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwUsbStorageReady()
EndProcedure

Procedure.i SvcUsbReadBlock(lba.i, *buf)
  If SvcRequireCap(#CAP_USB, "usb", "this board exposes no USB host to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  If *buf = 0 Or lba < 0
    gSvcDetail = "a zero buffer pointer or a negative block address"
    ProcedureReturn #SVC_EARG
  EndIf
  ProcedureReturn HwUsbReadBlock(lba, *buf)
EndProcedure

; Slot 100. WRITING A BLOCK. Reading one exists and writing one does not;
; 49 CFR 395 Appendix A's roadside transfer to an officer's stick requires
; it. NOT YET IMPLEMENTED: HwUsbWriteBlock does not exist in the HwUsb*
; seam, and adding it is Anvil work outside Phase A item 1. Answering
; #SVC_ENOSYS is the truth; answering #SVC_OK and doing nothing would be
; the failure this whole error convention exists to prevent.
Procedure.i SvcUsbWriteBlock(lba.i, *buf)
  If SvcRequireCap(#CAP_USB, "usb", "this board exposes no USB host to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  gSvcDetail = "no board in this Anvil can write a raw block to a mass-storage device yet"
  ProcedureReturn #SVC_ENOSYS
EndProcedure

; ======================================================================
;  GROUP 8 - GPIO, base 108. A straight re-export of HwGpio*.
; ======================================================================
Procedure.i SvcGpioCount()
  If SvcRequireCap(#CAP_GPIO, "gpio", "this board exposes no general-purpose I/O pins to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwGpioCount()
EndProcedure

Procedure.i SvcGpioModeGet(pin.i)
  If SvcRequireCap(#CAP_GPIO, "gpio", "this board exposes no general-purpose I/O pins to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwGpioModeGet(pin)
EndProcedure

Procedure.i SvcGpioLevelGet(pin.i)
  If SvcRequireCap(#CAP_GPIO, "gpio", "this board exposes no general-purpose I/O pins to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwGpioLevelGet(pin)
EndProcedure

Procedure.i SvcGpioPullGet(pin.i)
  If SvcRequireCap(#CAP_GPIO, "gpio", "this board exposes no general-purpose I/O pins to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwGpioPullGet(pin)
EndProcedure

Procedure.i SvcGpioMode(pin.i, mode.i)
  If SvcRequireCap(#CAP_GPIO, "gpio", "this board exposes no general-purpose I/O pins to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwGpioMode(pin, mode)
EndProcedure

Procedure.i SvcGpioWrite(pin.i, level.i)
  If SvcRequireCap(#CAP_GPIO, "gpio", "this board exposes no general-purpose I/O pins to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwGpioWrite(pin, level)
EndProcedure

; ======================================================================
;  GROUP 9 - I2C, base 116. A straight re-export of HwI2c*.
;
;  THESE SLOTS RETURN #HW_I2C_* CODES, WHICH ARE NEGATIVE, AND #SVC_ENOCAP
;  WHEN THE BOARD HAS NO BUS. That is the collision the -100 range exists
;  to make impossible - see the error-convention block at the top of this
;  file. Do not re-number either set.
; ======================================================================
Procedure.i SvcI2cDefaultBus()
  If SvcRequireCap(#CAP_I2C, "i2c", "this board exposes no I2C bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwI2cDefaultBus()
EndProcedure

Procedure.i SvcI2cUp(bus.i)
  If SvcRequireCap(#CAP_I2C, "i2c", "this board exposes no I2C bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwI2cUp(bus)
EndProcedure

Procedure.i SvcI2cProbe(bus.i, addr.i)
  If SvcRequireCap(#CAP_I2C, "i2c", "this board exposes no I2C bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwI2cProbe(bus, addr)
EndProcedure

Procedure.i SvcI2cRead(bus.i, addr.i, *buf, n.i)
  If SvcRequireCap(#CAP_I2C, "i2c", "this board exposes no I2C bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwI2cRead(bus, addr, *buf, n)
EndProcedure

Procedure.i SvcI2cWrite(bus.i, addr.i, *buf, n.i)
  If SvcRequireCap(#CAP_I2C, "i2c", "this board exposes no I2C bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwI2cWrite(bus, addr, *buf, n)
EndProcedure

Procedure.i SvcI2cSetSpeed(bus.i, hz.i)
  If SvcRequireCap(#CAP_I2C, "i2c", "this board exposes no I2C bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwI2cSetSpeed(bus, hz)
EndProcedure

Procedure.i SvcI2cGetSpeed(bus.i)
  If SvcRequireCap(#CAP_I2C, "i2c", "this board exposes no I2C bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwI2cGetSpeed(bus)
EndProcedure

Procedure.i SvcI2cPin(bus.i, which.i)
  If SvcRequireCap(#CAP_I2C, "i2c", "this board exposes no I2C bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn HwI2cPin(bus, which)
EndProcedure

; ======================================================================
;  GROUP 10 - SPI, base 128
;
;  THE TRANSPORT NOTHING IN THIS TREE HAS. There is no SPI library at all,
;  and the seam stays in Phase A after the 2026-09-04 ruling because LoRa
;  is a module on SPI and LoRa is the vehicle link's second transport.
;  Documented in hal.pi4; no board declares #CAP_SPI yet.
; ======================================================================
Procedure.i SvcSpiUp(bus.i, hz.i, mode.i)
  If SvcRequireCap(#CAP_SPI, "spi", "this board exposes no SPI bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcSpiSetSpeed(bus.i, hz.i)
  If SvcRequireCap(#CAP_SPI, "spi", "this board exposes no SPI bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcSpiGetSpeed(bus.i)
  If SvcRequireCap(#CAP_SPI, "spi", "this board exposes no SPI bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

; ONE FULL-DUPLEX TRANSFER WITH CS ASSERTED FOR THE WHOLE OF IT, and one
; call, deliberately: a register read that is command-then-data in a
; single CS assertion reads garbage on some parts and works on others if
; the seam drops CS between them.
Procedure.i SvcSpiXfer(bus.i, cs.i, *tx, *rx, n.i)
  If SvcRequireCap(#CAP_SPI, "spi", "this board exposes no SPI bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcSpiPin(bus.i, which.i)
  If SvcRequireCap(#CAP_SPI, "spi", "this board exposes no SPI bus to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

; ======================================================================
;  GROUP 11 - UART, base 136
;
;  THE CONSOLE UART IS ANVIL'S AND IS NOT THIS. This is the other port,
;  for the GNSS receiver. Every read and every write is NON-BLOCKING,
;  always: a blocking read in a cooperative single-stack scheduler is a
;  hang, and the payload's own loop is that scheduler.
; ======================================================================
Procedure.i SvcUartCount()
  If SvcRequireCap(#CAP_UART, "uart", "this board exposes no spare serial port to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcUartOpen(n.i, baud.i)
  If SvcRequireCap(#CAP_UART, "uart", "this board exposes no spare serial port to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcUartRead(n.i, *b, len.i)
  If SvcRequireCap(#CAP_UART, "uart", "this board exposes no spare serial port to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcUartWrite(n.i, *b, len.i)
  If SvcRequireCap(#CAP_UART, "uart", "this board exposes no spare serial port to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

; THE NUMBER THAT PROVES A GNSS RECEIVER IS NOT OVERRUNNING A FIFO RATHER
; THAN ASSUMING IT.
Procedure.i SvcUartRxOverrun(n.i)
  If SvcRequireCap(#CAP_UART, "uart", "this board exposes no spare serial port to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcUartClose(n.i)
  If SvcRequireCap(#CAP_UART, "uart", "this board exposes no spare serial port to Anvil") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

; ======================================================================
;  GROUP 12 - VEHICLE LINK, base 144
;
;  THE DECISION, 2026-09-04 evening: "hardy itself will not hook to the
;  engine port, there will be a device that hooks to that port which
;  communicates with hardy over wifi or lora". THIS GROUP WAS CAN UNTIL
;  THAT RULING. Hardy has no CAN transceiver, no J1939 stack and no
;  MCP2518FD; what it has is a radio link to a second unit that has all
;  three.
;
;  The seam is NOT a transport. It is the engine-data stream PLUS the
;  health of the path it arrives over, because for compliance those two
;  are inseparable: an odometer reading is only as good as the knowledge
;  of how old it is and which of the two hops was broken when it stopped
;  arriving.
;
;  THE TWO LOSS STATES ARE THE PART THAT IS A REQUIREMENT AND NOT A
;  CONVENIENCE. 49 CFR 395 Appendix A 4.3.1.1 makes more than thirty
;  minutes of lost ECM connectivity, aggregated over twenty-four hours, a
;  malfunction. With one box that was one measurement. With two boxes
;  there are two hops and they fail independently, so:
;
;    #HW_VEH_LOSS_ENGINE  THE UNIT LOST THE ENGINE. The radio is fine and
;                         the unit is telling us its own ECM connection is
;                         down. We know this POSITIVELY, from the unit.
;    #HW_VEH_LOSS_UNIT    HARDY LOST THE UNIT. The radio is down and we
;                         therefore DO NOT KNOW whether the engine is
;                         connected. This is not "engine present" and it
;                         is not "engine absent" - it is no measurement.
;
;  Both count toward 4.3.1.1 and they are recorded SEPARATELY, because
;  they have different causes and different fixes: the first is a
;  diagnostic-connector or J1939 fault in the truck, the second is a
;  radio, power or pairing fault. Collapsing them would produce a log that
;  cannot tell a mechanic which box to look at, and would let a Hardy that
;  has merely lost its radio report confidently about an engine it cannot
;  reach.
;
;  No board declares #CAP_VEHLINK yet, so every slot here answers
;  #SVC_ENOCAP over real code. hw_veh.pi4 is Phase A item 2a.
; ======================================================================
Procedure.i SvcVehUp()
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcVehDown()
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcVehState()
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #HW_VEH_DOWN
EndProcedure

Procedure.i SvcVehTransport()
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #HW_VEH_XPORT_NONE
EndProcedure

Procedure.i SvcVehPoll()
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcVehData(*rec)
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcVehLastHeardMs()
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i SvcVehLossState()
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ; NO LINK MEANS WE LOST THE UNIT, and that is the honest answer rather
  ; than _NONE. A board that cannot reach a unit has not established that
  ; the engine is fine; it has established nothing.
  ProcedureReturn #HW_VEH_LOSS_UNIT
EndProcedure

Procedure.i SvcVehEngineLostMs()
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ; -2, NOT A DURATION AND NOT -1. We cannot say, because we cannot hear
  ; the unit. A payload that treated this as a number would aggregate a
  ; made-up figure into a malfunction the regulation defines by duration.
  ProcedureReturn -2
EndProcedure

Procedure.i SvcVehDiag(which.i)
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn -1
EndProcedure

; READ AGAINST THE PAIRED IDENTITY IN THE SETTINGS STORE. A Hardy talking
; to the wrong truck's unit is a compliance failure that looks exactly
; like a working system, which is why the identity is a service and not an
; assumption.
Procedure.i SvcVehUnitId()
  If SvcRequireCap(#CAP_VEHLINK, "vehicle link", "this board has no link to an engine-port unit that Anvil can reach") = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 0
EndProcedure

; ======================================================================
;  GROUP 13 - GNSS, base 156
;
;  WHERE THE TRUCK IS, AND HOW MUCH TO TRUST IT. The fix record carries
;  the receiver's own horizontal accuracy estimate, which is the field
;  that makes 4.3.1.6(c) CHECKABLE RATHER THAN ASSUMED: a fix whose
;  reported accuracy is worse than half a mile is not a valid measurement
;  for the regulation's purposes and the ELD must treat it as no fix.
;
;  GNSS SPEED IS RECORDED AND NEVER USED FOR THE DRIVING DECISION -
;  4.3.1.2(b) requires speed from the ECM, and GNSS speed at a standstill
;  is noise, which is precisely how phantom driving events are made.
;
;  No board declares #CAP_GNSS yet. hw_gnss.pi4 is Phase A item 2b.
; ======================================================================
Procedure.i SvcGnssUp()
  If SvcRequireCap(#CAP_GNSS, "gnss", "this board has no satellite receiver Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcGnssPoll()
  If SvcRequireCap(#CAP_GNSS, "gnss", "this board has no satellite receiver Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcGnssFix(*fix)
  If SvcRequireCap(#CAP_GNSS, "gnss", "this board has no satellite receiver Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn #SVC_ENOSYS
EndProcedure

Procedure.i SvcGnssAgeMs()
  If SvcRequireCap(#CAP_GNSS, "gnss", "this board has no satellite receiver Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i SvcGnssPpsTicks()
  If SvcRequireCap(#CAP_GNSS, "gnss", "this board has no satellite receiver Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn -1
EndProcedure

Procedure.i SvcGnssSatsUsed()
  If SvcRequireCap(#CAP_GNSS, "gnss", "this board has no satellite receiver Anvil can reach") = 0
    ProcedureReturn #SVC_ENOCAP
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i SvcGnssErrText()
  ProcedureReturn "this board has no satellite receiver Anvil can reach, so there is no fix and no age to report"
EndProcedure

; ======================================================================
;  GROUP 14 - CRYPTO AND ENTROPY, base 168
;
;  SHA-256 IS ANVIL CORE and every board has it - it is what proves a
;  container's image before the machine changes hands. The rest of this
;  group is board-supplied and is compiled only where the board declares
;  it; on a board without it the slots keep pointing at SvcUnimplemented
;  and answer #SVC_ENOSYS.
; ======================================================================
Procedure.i SvcSha256(*in, n.i, *out32)
  If *in = 0 Or *out32 = 0 Or n < 0
    gSvcDetail = "a zero input or output pointer, or a negative length"
    ProcedureReturn #SVC_EARG
  EndIf
  Sha256Begin()
  Sha256Update(*in, n)
  Sha256End(*out32)
  ProcedureReturn #SVC_OK
EndProcedure

; ----------------------------------------------------------------------
;  THE SLOT INSTALLER.
;
;  BuildServiceTable() fills the header and all 184 pointers. Called by
;  PmfEnter() in Anvil/Core/pmfboot.pbi immediately before the jump, for a
;  container that declared #PMF_FLAG_WANTS_SERVICES, and nowhere else.
;
;  EVERY SLOT IS FILLED, and the empty ones are filled with
;  @SvcUnimplemented rather than left as the BSS zero. A null slot is a
;  branch to address 0 the first time an over-new payload reaches for it,
;  and a board that stops with nothing on the wire is exactly the outcome
;  this whole error convention exists to avoid. tools/a64/a64_abi_check.py
;  asserts that no slot is null and that every reserved slot is
;  @SvcUnimplemented specifically - not merely non-null, because a slot
;  filled with the wrong procedure passes a null check and returns
;  nonsense.
;
;  IT IS IDEMPOTENT. A second container in the same session refills the
;  table rather than accumulating anything.
;
;  THE SPARES ARE FILLED FIRST AND THE REAL SLOTS WRITTEN OVER THEM, in
;  that order, so that adding a service later is one line and cannot
;  leave a hole. The alternative - listing every spare index by hand -
;  is a list that goes stale the first time a group grows.
; ----------------------------------------------------------------------
Procedure BuildServiceTable()
  Define i.i

  gSvcTab[0] = #SVC_MAGIC | (#SVC_ABI_MAJOR << 32)
  gSvcTab[1] = #SVC_ABI_MINOR | (#SVC_SLOT_COUNT << 32)

  i = 0
  While i < #SVC_SLOT_COUNT
    gSvcTab[#SVC_HDR_WORDS + i] = @SvcUnimplemented
    i = i + 1
  Wend

  ; --- core and lifecycle, base 0 ------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  0] = @SvcAbiMajor
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  1] = @SvcAbiMinor
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  2] = @SvcBoardId
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  3] = @SvcBoardName
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  4] = @SvcCapGet
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  5] = @SvcRequireCap
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  6] = @SvcPet
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  7] = @SvcBootOk
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  8] = @SvcReturn
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE +  9] = @SvcReboot
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE + 10] = @SvcMmuState
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE + 11] = @SvcUptimeUs
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE + 12] = @SvcErrText
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CORE + 13] = @SvcErrDetail

  ; --- clock, base 16 -------------------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CLOCK + 0] = @SvcTicks
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CLOCK + 1] = @SvcUtc
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CLOCK + 2] = @SvcClockProvenance
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CLOCK + 3] = @SvcClockUncertaintyMs
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CLOCK + 4] = @SvcUtcLastSyncTicks

  ; --- console, base 24 -----------------------------------------------
  CompilerIf #CAP_CONSOLE = 1
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  0] = @SvcScreenWidth
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  1] = @SvcScreenHeight
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  2] = @SvcScreenTier
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  3] = @SvcFrameBegin
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  4] = @SvcFrameEnd
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  5] = @SvcRect
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  6] = @SvcText
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  7] = @SvcTextWidth
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  8] = @SvcClip
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE +  9] = @SvcLine
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE + 10] = @SvcFrameCostUs
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE + 11] = @SvcBacklight
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CONSOLE + 12] = @SvcTextHeight
  CompilerEndIf

  ; --- touch, base 40 -------------------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_TOUCH + 0] = @SvcTouchPoll
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_TOUCH + 1] = @SvcTouchQueued
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_TOUCH + 2] = @SvcTouchFlush
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_TOUCH + 3] = @SvcTouchMaxPoints

  ; --- file and storage, base 48 --------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  0] = @SvcStorageUp
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  1] = @SvcFileOpen
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  2] = @SvcFileSize
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  3] = @SvcFileReadAt
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  4] = @SvcFileClose
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  5] = @SvcFileWritable
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  6] = @SvcFileWriteAll
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  7] = @SvcFileAppend
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  8] = @SvcFileLastError
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE +  9] = @SvcFileErrText
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE + 10] = @SvcFileCanList
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE + 11] = @SvcDirOpen
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE + 12] = @SvcDirNext
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_FILE + 13] = @SvcDirClose

  ; --- settings, base 64 ----------------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_SETTING + 0] = @SvcSettingGet
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_SETTING + 1] = @SvcSettingSet
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_SETTING + 2] = @SvcSettingSave
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_SETTING + 3] = @SvcSettingDel

  ; --- net, base 72 ---------------------------------------------------
  ; DELIBERATELY EMPTY IN THIS BUILD, and the reason is a prerequisite
  ; outside Phase A rather than an oversight. It was settled on 2026-09-02
  ; that the two IP layers merge into one riding whichever link is up
  ; (Anvil todo 119); until that lands, the Ethernet-only stack cannot
  ; resolve a name over the Wi-Fi the bench actually has, and Ethernet RX
  ; is still silent. The brief says in as many words that "Phase A can
  ; ship with the seam correct and the plumbing incomplete; phase 5
  ; cannot."
  ;
  ; SO THE SLOTS STAY AT SvcUnimplemented AND ANSWER #SVC_ENOSYS. That is
  ; the truth. Installing a SvcNetUp that returned #SVC_OK over a stack
  ; that cannot reach the bench would be the plausible-stub failure this
  ; whole file's error convention exists to prevent, and the reserved
  ; block at base 72 is untouched so that filling it later is an
  ; abi_minor bump and nothing else.

  ; --- usb, base 96 ---------------------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_USB + 0] = @SvcUsbEnumerate
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_USB + 1] = @SvcUsbDevCount
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_USB + 2] = @SvcUsbDevKind
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_USB + 3] = @SvcUsbStorageReady
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_USB + 4] = @SvcUsbReadBlock
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_USB + 5] = @SvcUsbWriteBlock

  ; --- gpio, base 108 -------------------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 0] = @SvcGpioCount
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 1] = @SvcGpioModeGet
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 2] = @SvcGpioLevelGet
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 3] = @SvcGpioPullGet
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 4] = @SvcGpioMode
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GPIO + 5] = @SvcGpioWrite

  ; --- i2c, base 116 --------------------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_I2C + 0] = @SvcI2cDefaultBus
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_I2C + 1] = @SvcI2cUp
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_I2C + 2] = @SvcI2cProbe
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_I2C + 3] = @SvcI2cRead
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_I2C + 4] = @SvcI2cWrite
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_I2C + 5] = @SvcI2cSetSpeed
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_I2C + 6] = @SvcI2cGetSpeed
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_I2C + 7] = @SvcI2cPin

  ; --- spi, base 128 --------------------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_SPI + 0] = @SvcSpiUp
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_SPI + 1] = @SvcSpiSetSpeed
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_SPI + 2] = @SvcSpiGetSpeed
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_SPI + 3] = @SvcSpiXfer
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_SPI + 4] = @SvcSpiPin

  ; --- uart, base 136 -------------------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_UART + 0] = @SvcUartCount
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_UART + 1] = @SvcUartOpen
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_UART + 2] = @SvcUartRead
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_UART + 3] = @SvcUartWrite
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_UART + 4] = @SvcUartRxOverrun
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_UART + 5] = @SvcUartClose

  ; --- vehicle link, base 144 -----------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  0] = @SvcVehUp
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  1] = @SvcVehDown
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  2] = @SvcVehState
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  3] = @SvcVehTransport
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  4] = @SvcVehPoll
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  5] = @SvcVehData
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  6] = @SvcVehLastHeardMs
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  7] = @SvcVehLossState
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  8] = @SvcVehEngineLostMs
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH +  9] = @SvcVehDiag
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_VEH + 10] = @SvcVehUnitId

  ; --- gnss, base 156 -------------------------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GNSS + 0] = @SvcGnssUp
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GNSS + 1] = @SvcGnssPoll
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GNSS + 2] = @SvcGnssFix
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GNSS + 3] = @SvcGnssAgeMs
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GNSS + 4] = @SvcGnssPpsTicks
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GNSS + 5] = @SvcGnssSatsUsed
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_GNSS + 6] = @SvcGnssErrText

  ; --- crypto and entropy, base 168 -----------------------------------
  gSvcTab[#SVC_HDR_WORDS + #SVC_BASE_CRYPTO + 0] = @SvcSha256

  gSvcBuilt = 1
EndProcedure
