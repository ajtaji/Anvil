; ======================================================================
;  THE DRIVER LIFECYCLE - MATCH, PROBE, INIT ONCE, PUBLISH, UNLOAD
; ----------------------------------------------------------------------
;  DEPENDENCIES, included by the composition before this file:
;    Anvil/Hal/module_format.pbi      the container vocabulary
;    Anvil/Hal/module_runtime.pbi     the loader's own vocabulary
;    Anvil/Core/mod_registry.pbi      where a published service lands
;    Anvil/Core/sha256.pbi
;    Anvil/Core/mod_container.pbi     parse and relocate
;    Anvil/Core/mod_arena.pbi         place and record
;    Anvil/Hal/abi.pbi                SvcTableAddr()
;    RaspberryPi4/Lib/uart.pi4        PrintDec / PrintNl
;
;  REQUIRED BOARD CONTRACT - THE DEVICES THIS BOARD HAS:
;    HwDevCount()        how many devices the board is willing to name
;    HwDevIdAddr(i)      a NUL-terminated ASCII compatible id for one
;    HwDevSeam(i)        the #SVCCAP_* group that device belongs to
;    HwDevToken(i)       the handle a driver for it needs, which on a
;                        memory-mapped part is the block's base address
;    HwDevSay(i)         prints the device's own name, in the board's
;                        own words
;
;  WHY THE BOARD OWNS THE DEVICE LIST AND NOT THIS FILE. A module states
;  what it is FOR - one or more compatible ids, in its digest-covered
;  header - and the board states what is PRESENT. Matching the two is
;  arithmetic on strings and belongs in the core; knowing that this
;  particular part puts its temperature monitor at one address and not
;  another is board knowledge and may not leak upward. That split is what
;  lets the identical core run on a board whose devices are enumerated by
;  UEFI instead of written down.
;
;  IT ALSO REMOVES THE LAST HARD-WIRED ADDRESS FROM THE DRIVER. The
;  module is handed HwDevToken() as its second argument and reads its
;  registers from there, so a converted driver contains no address of its
;  own at all - which is both the portability claim and a real check,
;  because a module that ignored the token and kept a constant would
;  still work on this board and fail the first time the board moved.
;
;  THE ORDER OF THE STATES IS THE ORDER OF WHAT EACH ONE PROVES, and each
;  is entered from exactly one place:
;
;    READY    the bytes are verified, placed, zeroed, relocated, synced
;    MATCHED  a device the board names answers one of the header's ids
;    PROBED   the driver looked at that device and accepted it, WITHOUT
;             changing anything - the registry refuses a service fill
;             outside init, so "side-effect-free probe" is enforced and
;             not merely asked for
;    ACTIVE   init returned 0 and published at least one service
;    FAILED   a step refused; every service it managed to publish was
;             withdrawn before the state was written
;    QUIESCED unloaded cleanly. The bytes are stranded, and `mod` says so
;
;  LIFECYCLE CALLS ARE SERIALISED BY CONSTRUCTION. This monitor runs one
;  flow of control and the compiler gives a procedure static storage for
;  its locals, so two calls into one driver at once would be wrong for
;  reasons no counter here could fix. Nothing in this file starts a
;  second flow, and nothing in it may be called from an interrupt.
; ======================================================================

#MOD_NAME_MAX = 16            ; an 8.3 name, its NUL, and room to spare

; Per-record driver facts. The arena owns where the bytes are; this owns
; what the driver is. Parallel arrays indexed by the same record number,
; because one record is one driver in both files.
Global Dim gModRecName.a[#MOD_RECORD_MAX * #MOD_NAME_MAX]
Global Dim gModRecDevice.i[#MOD_RECORD_MAX]      ; the matched device, or -1
Global Dim gModRecToken.i[#MOD_RECORD_MAX]       ; what was handed to it
Global Dim gModRecMatched.i[#MOD_RECORD_MAX]     ; which of its ids matched
Global Dim gModRecInitCalls.i[#MOD_RECORD_MAX]   ; how many times init ran
Global Dim gModRecInitResult.i[#MOD_RECORD_MAX]  ; what it answered last
Global Dim gModRecSeamUse.i[#MOD_RECORD_MAX * #PMFMOD_SEAM_MAX]

; The record the last refusal was about, so a caller that did not pass a
; record number can still name the module.
Global gModErrorRecord.i = -1

Procedure ModLifecycleReset()
  Define i.i
  i = 0
  While i < #MOD_RECORD_MAX * #MOD_NAME_MAX
    gModRecName[i] = 0
    i = i + 1
  Wend
  i = 0
  While i < #MOD_RECORD_MAX
    gModRecDevice[i] = -1
    gModRecToken[i] = 0
    gModRecMatched[i] = -1
    gModRecInitCalls[i] = 0
    gModRecInitResult[i] = 0
    i = i + 1
  Wend
  i = 0
  While i < #MOD_RECORD_MAX * #PMFMOD_SEAM_MAX
    gModRecSeamUse[i] = 0
    i = i + 1
  Wend
  gModErrorRecord = -1
EndProcedure

Procedure.i ModRecNameAddr(rec.i)
  If rec < 0 Or rec >= #MOD_RECORD_MAX
    ProcedureReturn 0
  EndIf
  ProcedureReturn @gModRecName[rec * #MOD_NAME_MAX]
EndProcedure

; Copy a NUL-terminated name into a record, truncating at the array and
; always terminating. The name is the one the OPERATOR typed or the one
; the manifest carries, and it is what every refusal is phrased around -
; a module can only be discussed by the name the person used for it.
Procedure ModRecSetName(rec.i, src.i)
  Define i.i
  Define c.i
  Define dst.i
  dst = ModRecNameAddr(rec)
  If dst = 0
    ProcedureReturn
  EndIf
  i = 0
  While i < #MOD_NAME_MAX - 1
    c = 0
    If src <> 0
      c = PeekA(src + i) & 255
    EndIf
    If c = 0
      Break
    EndIf
    PokeB(dst + i, c)
    i = i + 1
  Wend
  While i < #MOD_NAME_MAX
    PokeB(dst + i, 0)
    i = i + 1
  Wend
EndProcedure

Procedure ModSayName(rec.i)
  Define *p
  *p = ModRecNameAddr(rec)
  If *p = 0 Or (PeekA(*p) & 255) = 0
    Print("an unnamed module")
    ProcedureReturn
  EndIf
  UartWriteStr(*p)
EndProcedure

; ----------------------------------------------------------------------
;  ModIdSame(a, b) - two NUL-terminated ASCII compatible ids.
;
;  A byte comparison and deliberately NOT a case-insensitive one. A
;  compatible id is an identifier, not prose; the container's validation
;  already refuses anything outside printable ASCII and anything holding
;  a path separator, and a matcher that folded case would make two ids
;  that differ in the file the same id at run time.
; ----------------------------------------------------------------------
Procedure.i ModIdSame(a.i, b.i)
  Define i.i
  Define ca.i
  Define cb.i
  If a = 0 Or b = 0
    ProcedureReturn 0
  EndIf
  i = 0
  While i < #PMFMOD_MATCH_BYTES
    ca = PeekA(a + i) & 255
    cb = PeekA(b + i) & 255
    If ca <> cb
      ProcedureReturn 0
    EndIf
    If ca = 0
      ProcedureReturn 1
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i ModRecUsesSeam(rec.i, sid.i)
  Define i.i
  i = 0
  While i < gModRecSeamCount[rec]
    If gModRecSeams[rec * #PMFMOD_SEAM_MAX + i] = sid And gModRecSeamUse[rec * #PMFMOD_SEAM_MAX + i] <> 0
      ProcedureReturn 1
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure.i ModRecEnabledSeams(rec.i)
  Define i.i
  Define n.i
  n = 0
  i = 0
  While i < gModRecSeamCount[rec]
    If gModRecSeamUse[rec * #PMFMOD_SEAM_MAX + i] <> 0
      n = n + 1
    EndIf
    i = i + 1
  Wend
  ProcedureReturn n
EndProcedure

; Every seam the header declared is used unless a manifest line narrows
; it. Called by the loader the moment a record commits, so a record is
; never in a state where nothing has decided.
Procedure ModRecUseAllSeams(rec.i)
  Define i.i
  i = 0
  While i < #PMFMOD_SEAM_MAX
    If i < gModRecSeamCount[rec]
      gModRecSeamUse[rec * #PMFMOD_SEAM_MAX + i] = 1
    Else
      gModRecSeamUse[rec * #PMFMOD_SEAM_MAX + i] = 0
    EndIf
    i = i + 1
  Wend
EndProcedure

; Narrowing: keep only `seam`, and refuse a seam the header never
; declared. A manifest line may only ever subtract - widening a module
; past what its digest-covered header claims is the one thing the seam
; list exists to prevent.
Procedure.i ModRecNarrowToSeam(rec.i, sid.i)
  Define i.i
  Define found.i
  found = 0
  i = 0
  While i < gModRecSeamCount[rec]
    If gModRecSeams[rec * #PMFMOD_SEAM_MAX + i] = sid
      found = 1
    EndIf
    i = i + 1
  Wend
  If found = 0
    ProcedureReturn ModFail(#MOD_ERR_SEAM_UNDECLARED, rec, sid)
  EndIf
  i = 0
  While i < gModRecSeamCount[rec]
    If gModRecSeams[rec * #PMFMOD_SEAM_MAX + i] <> sid
      gModRecSeamUse[rec * #PMFMOD_SEAM_MAX + i] = 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn #MOD_OK
EndProcedure

; ----------------------------------------------------------------------
;  ModMatchDevice(rec) - the first device this board declares that answers
;  one of the container's compatible ids AND belongs to a seam this
;  module is still enabled for.
;
;  THE SEAM HAS TO AGREE AS WELL AS THE ID. Without that test a module
;  narrowed by the manifest to one of its two seams would still bind to
;  the device belonging to the other one, and the narrowing would be
;  advice rather than a rule.
;
;  Answers the device index, or -1. It touches no hardware: comparing the
;  strings the board already holds is the whole of it, which is what lets
;  matching happen before a probe rather than as part of one.
; ----------------------------------------------------------------------
Procedure.i ModMatchDevice(rec.i)
  Define d.i
  Define m.i
  Define n.i
  Define *id
  Define *want
  n = HwDevCount()
  d = 0
  While d < n
    If ModRecUsesSeam(rec, HwDevSeam(d)) <> 0
      *id = HwDevIdAddr(d)
      m = 0
      While m < gModRecMatchCount[rec]
        *want = ModRecordMatchAddr(rec, m)
        If ModIdSame(id, want) <> 0
          gModRecMatched[rec] = m
          ProcedureReturn d
        EndIf
        m = m + 1
      Wend
    EndIf
    d = d + 1
  Wend
  ProcedureReturn -1
EndProcedure

; ----------------------------------------------------------------------
;  ModActivate(rec) - the whole of turning placed bytes into a driver.
;
;  IT REFUSES A SECOND ACTIVATION OF AN ACTIVE RECORD WITHOUT CALLING
;  ANYTHING. That is the "initialised exactly once" guarantee, and the
;  reason it is a refusal rather than a silent success is that the two
;  are indistinguishable to the caller otherwise: a loader that answered
;  OK and did nothing would make a manifest listing a module twice look
;  correct while the second line did not mean what it said.
;
;  EVERY FAILURE PATH UNWINDS BEFORE IT RETURNS. The permissions, the
;  published functions and the state are put back in that order, so no
;  caller can observe a seam owned by a record that is not ACTIVE.
; ----------------------------------------------------------------------
Procedure.i ModActivate(rec.i)
  Define dev.i
  Define token.i
  Define *fn
  Define r.i
  Define i.i
  Define sid.i
  Define fills.i
  Define services.i

  gModErrorRecord = rec
  If rec < 0 Or rec >= gModRecordCount
    ProcedureReturn ModFail(#MOD_ERR_STATE, rec, -1)
  EndIf
  If gModRecState[rec] <> #MOD_STATE_READY
    ProcedureReturn ModFail(#MOD_ERR_STATE, rec, gModRecState[rec])
  EndIf
  If ModRecEnabledSeams(rec) = 0
    gModRecState[rec] = #MOD_STATE_FAILED
    ProcedureReturn ModFail(#MOD_ERR_NOSERVICE, rec, 0)
  EndIf

  dev = ModMatchDevice(rec)
  If dev < 0
    gModRecState[rec] = #MOD_STATE_FAILED
    ProcedureReturn ModFail(#MOD_ERR_NOMATCH, rec, gModRecMatchCount[rec])
  EndIf
  token = HwDevToken(dev)
  gModRecDevice[rec] = dev
  gModRecToken[rec] = token
  gModRecState[rec] = #MOD_STATE_MATCHED

  ; The seam permissions, BEFORE the probe. A collision with another
  ; module is knowable from two headers, so it is answered from two
  ; headers rather than after a driver has begun looking at hardware.
  i = 0
  While i < gModRecSeamCount[rec]
    If gModRecSeamUse[rec * #PMFMOD_SEAM_MAX + i] <> 0
      sid = gModRecSeams[rec * #PMFMOD_SEAM_MAX + i]
      r = ModSeamAllow(rec, sid)
      If r <> #MOD_OK
        ModSeamAllowClear(rec)
        gModRecState[rec] = #MOD_STATE_FAILED
        ProcedureReturn ModFail(r, rec, sid)
      EndIf
    EndIf
    i = i + 1
  Wend

  services = SvcTableAddr()

  ; THE PROBE. Side-effect-free by contract, and the contract is kept by
  ; the registry rather than by trust: the fill window is shut, so a
  ; probe that tried to publish a service would be refused by
  ; #MOD_ERR_STATE and the driver would see its own failure.
  ;
  ; A POSITIVE ANSWER CLAIMS THE DEVICE. Zero and negative both decline,
  ; and both are normal - a driver looking at a device id it recognises
  ; and silicon that does not answer is exactly the case a probe is for.
  *fn = gModRecProbe[rec]
  If *fn <> 0
    r = fn(services, token)
    If r <= 0
      ModSeamAllowClear(rec)
      gModRecState[rec] = #MOD_STATE_FAILED
      ProcedureReturn ModFail(#MOD_ERR_PROBE, rec, r)
    EndIf
  EndIf
  gModRecState[rec] = #MOD_STATE_PROBED

  ; INIT, EXACTLY ONCE, WITH THE PUBLISH WINDOW OPEN FOR ITS DURATION.
  *fn = gModRecInit[rec]
  If *fn = 0
    ModSeamAllowClear(rec)
    gModRecState[rec] = #MOD_STATE_FAILED
    ProcedureReturn ModFail(#MOD_ERR_STATE, rec, 0)
  EndIf
  gModRecInitCalls[rec] = gModRecInitCalls[rec] + 1
  ModSeamFillOpen(rec)
  r = fn(services, token)
  fills = ModSeamFillClose()
  gModRecInitResult[rec] = r

  If r <> 0
    ; THE UNWIND. Whatever it published before it gave up is withdrawn,
    ; then its permissions, then the state. A driver that failed halfway
    ; leaves nothing callable behind it.
    ModSeamReleaseOwner(rec)
    gModRecState[rec] = #MOD_STATE_FAILED
    ProcedureReturn ModFail(#MOD_ERR_INIT, rec, r)
  EndIf
  If fills = 0
    ; Init said it succeeded and published nothing. Every later caller
    ; would find the seam empty and fall back, so the module would be
    ; loaded, ACTIVE and doing nothing - the quiet wrong answer.
    ModSeamReleaseOwner(rec)
    gModRecState[rec] = #MOD_STATE_FAILED
    ProcedureReturn ModFail(#MOD_ERR_NOSERVICE, rec, 0)
  EndIf

  ModSeamAllowClear(rec)
  gModRecState[rec] = #MOD_STATE_ACTIVE
  gModError = #MOD_OK
  ProcedureReturn #MOD_OK
EndProcedure

; ----------------------------------------------------------------------
;  ModUnloadBlocker(rec) - the first seam this record owns that something
;  is still holding, or -1.
;
;  Two different holds and both refuse. A DEPTH means a caller is on the
;  stack inside the driver right now, which is the console command issued
;  from inside a driver callback. A BINDING means a consumer has taken
;  the service as its source and has not given it back. Neither is an
;  error; both are reasons the answer to `mod unload` is no.
; ----------------------------------------------------------------------
Procedure.i ModUnloadBlocker(rec.i)
  Define sid.i
  sid = 0
  While sid <= #MOD_SEAM_MAX
    If ModSeamOwner(sid) = rec
      If ModSeamDepth(sid) > 0 Or ModSeamBindCount(sid) > 0
        ProcedureReturn sid
      EndIf
    EndIf
    sid = sid + 1
  Wend
  ProcedureReturn -1
EndProcedure

; ----------------------------------------------------------------------
;  ModUnload(rec) - put the hardware down, withdraw the services, and say
;  what is left behind.
;
;  THE BYTES STAY WHERE THEY ARE. The allocator is a bump pointer with no
;  free list, so the arena a module occupied is not reusable and is not
;  pretended to be; `mod` reports the record as stranded and the memory
;  is recovered by a reset. That is a deliberate limit, not an oversight:
;  a free list would let a later module land on memory a stale pointer
;  still names, which is precisely the hazard the binding count exists to
;  refuse.
;
;  QUIESCE IS ALLOWED TO SAY NO. A driver that cannot put its hardware
;  into a safe state - a transfer in flight, a channel still driving -
;  refuses, and the unload refuses with it, leaving the record ACTIVE.
;  Tearing a driver out over its own objection is how silicon is left
;  mid-transaction.
; ----------------------------------------------------------------------
Procedure.i ModUnload(rec.i)
  Define *fn
  Define r.i
  Define blocked.i

  gModErrorRecord = rec
  If rec < 0 Or rec >= gModRecordCount
    ProcedureReturn ModFail(#MOD_ERR_STATE, rec, -1)
  EndIf
  If gModRecState[rec] <> #MOD_STATE_ACTIVE And gModRecState[rec] <> #MOD_STATE_FAILED
    ProcedureReturn ModFail(#MOD_ERR_STATE, rec, gModRecState[rec])
  EndIf

  blocked = ModUnloadBlocker(rec)
  If blocked >= 0
    ProcedureReturn ModFail(#MOD_ERR_BOUND, rec, blocked)
  EndIf

  *fn = gModRecQuiesce[rec]
  If *fn <> 0 And gModRecState[rec] = #MOD_STATE_ACTIVE
    r = fn(SvcTableAddr(), gModRecToken[rec])
    If r <> 0
      ProcedureReturn ModFail(#MOD_ERR_QUIESCE, rec, r)
    EndIf
  EndIf

  ModSeamReleaseOwner(rec)
  gModRecState[rec] = #MOD_STATE_QUIESCED
  gModError = #MOD_OK
  ProcedureReturn #MOD_OK
EndProcedure

; ======================================================================
;  THE REFUSALS.
;
;  Every one is a complete sentence that keeps its numeric code, says
;  what it means, says what was NOT done, and names the first thing to
;  check - the project's error rule, and pmfboot.pbi's tone: `!!` and
;  the sentence, three-space continuations.
;
;  NO SENTENCE HERE NAMES A PIECE OF HARDWARE. The shared-core finding
;  (forum 575) is that one board's facts stated as literal prose in the
;  core is how a shared file comes to lie on the second board. So these
;  print the module's FILE name, which the operator typed, and the
;  seam's PORTABLE name from the published vocabulary. A hardware noun
;  phrase comes back from the board through HwDevSay() or from the driver
;  itself, never from a string in Anvil/Core.
; ======================================================================
Procedure ModSaySeam(sid.i)
  Select sid
    Case #SVCCAP_STORAGE  : Print("storage")
    Case #SVCCAP_NET      : Print("net")
    Case #SVCCAP_GPIO     : Print("gpio")
    Case #SVCCAP_I2C      : Print("i2c")
    Case #SVCCAP_MMC      : Print("mmc")
    Case #SVCCAP_USB      : Print("usb")
    Case #SVCCAP_BOOT_EL1 : Print("bootel1")
    Case #SVCCAP_TOUCH    : Print("touch")
    Case #SVCCAP_GNSS     : Print("gnss")
    Case #SVCCAP_VEHLINK  : Print("vehlink")
    Case #SVCCAP_SPI      : Print("spi")
    Case #SVCCAP_UART     : Print("uart")
    Case #SVCCAP_RTC      : Print("rtc")
    Case #SVCCAP_CONSOLE  : Print("console")
    Case #SVCCAP_PWM      : Print("pwm")
    Case #SVCCAP_THERMAL  : Print("thermal")
    Default
      Print("seam ")
      PrintDec(sid)
  EndSelect
EndProcedure

; ----------------------------------------------------------------------
;  ModTokenIs(p, n, name) - a COUNTED run of bytes against a literal,
;  case-insensitively, whole-token.
;
;  parse.pbi's WordIs() answers the same question about the command word
;  and cannot be reused: it reads gLine at gWordAt, and the manifest's
;  seam column is in a file buffer, not on the command line. The folding
;  rule is copied deliberately rather than shared, because the two live
;  on opposite sides of the console/medium boundary and a shared helper
;  would have to reach across it.
; ----------------------------------------------------------------------
Procedure.i ModTokenIs(p.i, n.i, name.i)
  Define i.i
  Define a.i
  Define b.i
  i = 0
  While i < n
    b = PeekA(name + i) & 255
    If b = 0
      ProcedureReturn 0
    EndIf
    a = PeekA(p + i) & 255
    If a >= 65 And a <= 90
      a = a + 32
    EndIf
    If b >= 65 And b <= 90
      b = b + 32
    EndIf
    If a <> b
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ; The token ran out; the name must have run out with it, or "net"
  ; would match "network".
  If (PeekA(name + n) & 255) <> 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; The seam id for a name, or -1. The manifest's narrowing column and the
; `mod` command both take the same words the refusals print, so an
; operator can copy one into the other.
Procedure.i ModSeamIdOfName(p.i, n.i)
  If n <= 0
    ProcedureReturn -1
  EndIf
  If ModTokenIs(p, n, "storage") : ProcedureReturn #SVCCAP_STORAGE  : EndIf
  If ModTokenIs(p, n, "net")     : ProcedureReturn #SVCCAP_NET      : EndIf
  If ModTokenIs(p, n, "gpio")    : ProcedureReturn #SVCCAP_GPIO     : EndIf
  If ModTokenIs(p, n, "i2c")     : ProcedureReturn #SVCCAP_I2C      : EndIf
  If ModTokenIs(p, n, "mmc")     : ProcedureReturn #SVCCAP_MMC      : EndIf
  If ModTokenIs(p, n, "usb")     : ProcedureReturn #SVCCAP_USB      : EndIf
  If ModTokenIs(p, n, "bootel1") : ProcedureReturn #SVCCAP_BOOT_EL1 : EndIf
  If ModTokenIs(p, n, "touch")   : ProcedureReturn #SVCCAP_TOUCH    : EndIf
  If ModTokenIs(p, n, "gnss")    : ProcedureReturn #SVCCAP_GNSS     : EndIf
  If ModTokenIs(p, n, "vehlink") : ProcedureReturn #SVCCAP_VEHLINK  : EndIf
  If ModTokenIs(p, n, "spi")     : ProcedureReturn #SVCCAP_SPI      : EndIf
  If ModTokenIs(p, n, "uart")    : ProcedureReturn #SVCCAP_UART     : EndIf
  If ModTokenIs(p, n, "rtc")     : ProcedureReturn #SVCCAP_RTC      : EndIf
  If ModTokenIs(p, n, "console") : ProcedureReturn #SVCCAP_CONSOLE  : EndIf
  If ModTokenIs(p, n, "pwm")     : ProcedureReturn #SVCCAP_PWM      : EndIf
  If ModTokenIs(p, n, "thermal") : ProcedureReturn #SVCCAP_THERMAL  : EndIf
  ProcedureReturn -1
EndProcedure

Procedure ModSayState(rec.i)
  Select gModRecState[rec]
    Case #MOD_STATE_EMPTY    : Print("EMPTY")
    Case #MOD_STATE_READY    : Print("READY")
    Case #MOD_STATE_MATCHED  : Print("MATCHED")
    Case #MOD_STATE_PROBED   : Print("PROBED")
    Case #MOD_STATE_ACTIVE   : Print("ACTIVE")
    Case #MOD_STATE_FAILED   : Print("FAILED")
    Case #MOD_STATE_QUIESCED : Print("STRANDED")
    Default                  : Print("?")
  EndSelect
EndProcedure

Procedure ModSayCode(code.i)
  Print(" [mod ")
  PrintDec(code)
  Print("]")
EndProcedure

Procedure ModSayRefusal()
  Define rec.i
  Define code.i
  rec = gModErrorRecord
  code = gModError
  Print("!! ")
  ; #MOD_RECORD_MAX and not gModRecordCount: a file refused BEFORE its
  ; record committed still has its name written into the next free slot,
  ; because a refusal that cannot name the thing it refused is the
  ; failure the whole error convention exists to avoid.
  If rec >= 0 And rec < #MOD_RECORD_MAX
    ModSayName(rec)
    Print(" ")
  EndIf
  Select code
    Case #MOD_ERR_MAGIC
      Print("is not a driver module: its first eight bytes are not the module")
      PrintNl()
      Print("   magic. Nothing was loaded, and nothing was initialised. If this is a")
      PrintNl()
      Print("   payload rather than a driver, `boot` is the command for it.")
    Case #MOD_ERR_VERSION
      Print("is container format version ")
      PrintDec(gModErrorValue)
      Print("; this Anvil reads version ")
      PrintDec(#PMFMOD_VERSION)
      Print(".")
      PrintNl()
      Print("   Nothing was loaded. Rebuild it with a compiler of this generation.")
    Case #MOD_ERR_ABI_MAJOR
      Print("was built against service table major ")
      PrintDec(gModErrorValue)
      Print(", and this Anvil")
      PrintNl()
      Print("   publishes major ")
      PrintDec(#SVC_ABI_MAJOR)
      Print(". A major difference means a slot changed meaning, so it")
      PrintNl()
      Print("   cannot be loaded at all and nothing was initialised. Rebuild it")
      PrintNl()
      Print("   against this Anvil's seam header.")
    Case #MOD_ERR_ABI_MINOR
      Print("needs service table minor ")
      PrintDec(gModErrorValue)
      Print(", and this Anvil publishes ")
      PrintDec(#SVC_ABI_MINOR)
      Print(".")
      PrintNl()
      Print("   It would ask for slots this monitor does not fill, so nothing was")
      PrintNl()
      Print("   initialised. Update Anvil, or rebuild the module against this one.")
    Case #MOD_ERR_HASH
      Print("does not match its own digest, so nothing was initialised.")
      PrintNl()
      Print("   The bytes were refused before the arena was touched. Copy the file")
      PrintNl()
      Print("   to the card again; a short write is the usual cause.")
    Case #MOD_ERR_SEAM_TAKEN
      Print("wants the ")
      ModSaySeam(gModErrorValue)
      Print(" seam, which is already filled.")
      PrintNl()
      Print("   Two owners of one piece of hardware is how a board hangs, so nothing")
      PrintNl()
      Print("   was initialised. `mod` lists what is loaded; remove one of them from")
      PrintNl()
      Print("   the manifest, or narrow one with a seam column.")
    Case #MOD_ERR_SEAM_UNDECLARED
      Print("was asked for the ")
      ModSaySeam(gModErrorValue)
      Print(" seam, which its header does not")
      PrintNl()
      Print("   declare. A manifest line can only ever narrow a module, never widen")
      PrintNl()
      Print("   it. Nothing was initialised. `mod info` prints what the header claims.")
    Case #MOD_ERR_ARENA_FULL
      Print("does not fit: the module arena has ")
      PrintDec(gModArenaEnd - gModArenaNext)
      Print(" bytes left")
      PrintNl()
      Print("   and this needs ")
      PrintDec(gModErrorValue)
      Print(". Nothing was loaded. Modules unloaded during this")
      PrintNl()
      Print("   power cycle are stranded until a reset; `mod` shows them.")
    Case #MOD_ERR_RELKIND
      Print("carries relocation entry ")
      PrintDec(gModErrorIndex)
      Print(" of kind ")
      PrintDec(gModErrorValue)
      Print(", which this")
      PrintNl()
      Print("   Anvil cannot apply. It was built by a newer compiler than this")
      PrintNl()
      Print("   monitor. Nothing was placed and nothing was initialised.")
    Case #MOD_ERR_ALIGN
      Print("asks to be placed at an alignment of ")
      PrintDec(gModErrorValue)
      Print(" bytes, which")
      PrintNl()
      Print("   the arena cannot give. Nothing was loaded.")
    Case #MOD_ERR_INIT
      Print("failed to initialise: its own code answered ")
      PrintDec(gModErrorValue)
      Print(".")
      PrintNl()
      Print("   Every service it had published was withdrawn again, so nothing calls")
      PrintNl()
      Print("   into it. The bytes are in the arena and the record reads FAILED.")
    Case #MOD_ERR_FILE
      Print("could not be read from the medium.")
      PrintNl()
      Print("   Nothing was loaded. `ls` shows what the card actually holds.")
    Case #MOD_ERR_HEADER
      Print("has a header this Anvil will not accept (field value ")
      PrintDec(gModErrorValue)
      Print(").")
      PrintNl()
      Print("   Nothing was loaded. `mod info` cannot help - the header is what")
      PrintNl()
      Print("   failed. Rebuild the module.")
    Case #MOD_ERR_RANGE
      Print("states a length or an offset that does not fit the file it")
      PrintNl()
      Print("   is in (value ")
      PrintDec(gModErrorValue)
      Print("). Nothing was loaded. The file is truncated or")
      PrintNl()
      Print("   was built by a producer this Anvil does not agree with.")
    Case #MOD_ERR_MATCH
      Print("carries a compatible id this Anvil will not accept, at index ")
      PrintDec(gModErrorIndex)
      Print(".")
      PrintNl()
      Print("   An id is 1 to 63 printable bytes with no slash, and no two may be")
      PrintNl()
      Print("   the same. Nothing was loaded.")
    Case #MOD_ERR_RELOC
      Print("carries relocation entry ")
      PrintDec(gModErrorIndex)
      Print(" that this Anvil refused")
      PrintNl()
      Print("   (value ")
      PrintDec(gModErrorValue)
      Print("): it is out of range, overlaps another, or does not")
      PrintNl()
      Print("   describe the instruction at its site. Nothing was placed.")
    Case #MOD_ERR_ARCH
      Print("was built for architecture ")
      PrintDec(gModErrorValue)
      Print(" and this Anvil runs ")
      PrintDec(#PMFMOD_ARCH_AARCH64)
      Print(".")
      PrintNl()
      Print("   Nothing was loaded.")
    Case #MOD_ERR_RECORDS_FULL
      Print("cannot be recorded: all ")
      PrintDec(#MOD_RECORD_MAX)
      Print(" module records are in use.")
      PrintNl()
      Print("   Nothing was loaded. Reset the board to clear stranded records.")
    Case #MOD_ERR_OVERLAP
      Print("would be placed on top of the buffer it is being read from.")
      PrintNl()
      Print("   Nothing was written. Stage the file somewhere outside the arena.")
    Case #MOD_ERR_SYNC
      Print("was placed but the code caches could not be synchronised, so")
      PrintNl()
      Print("   it was NOT initialised and the arena bytes were cleared again.")
      PrintNl()
      Print("   This is a fault in the board's cache maintenance, not in the module.")
    Case #MOD_ERR_NOMATCH
      Print("matches no device this board declares.")
      PrintNl()
      Print("   It was verified and placed but nothing was initialised. `mod devices`")
      PrintNl()
      Print("   lists what is here and `mod info` lists what the module is for.")
    Case #MOD_ERR_PROBE
      Print("looked at the device it matched and declined it, answering ")
      PrintDec(gModErrorValue)
      Print(".")
      PrintNl()
      Print("   Nothing was initialised and nothing was changed - a probe may not")
      PrintNl()
      Print("   have side effects. Check that the hardware is powered and present.")
    Case #MOD_ERR_BOUND
      Print("is still in use and was NOT unloaded.")
      PrintNl()
      Print("   The ")
      ModSaySeam(gModErrorValue)
      Print(" seam has ")
      PrintDec(ModSeamBindCount(gModErrorValue))
      Print(" binding(s) held by ")
      ModSeamSayBinders(gModErrorValue)
      Print(".")
      PrintNl()
      Print("   `mod detach ")
      ModSaySeam(gModErrorValue)
      Print("` asks them to let go first; everything that")
      PrintNl()
      Print("   uses it falls back to whatever it used before the module was loaded.")
    Case #MOD_ERR_STATE
      Print("is not in a state that allows that (state ")
      PrintDec(gModErrorValue)
      Print(").")
      PrintNl()
      Print("   Nothing was done. A module initialises exactly once: `mod` shows")
      PrintNl()
      Print("   what state each record is in and `mod unload` is what ends an active one.")
    Case #MOD_ERR_MANIFEST
      Print("could not be acted on: the manifest line is not one this Anvil")
      PrintNl()
      Print("   understands (line ")
      PrintDec(gModErrorIndex)
      Print("). The modules after it were NOT loaded.")
      PrintNl()
      Print("   A line is a file name and an optional seam name.")
    Case #MOD_ERR_REGION
      Print("cannot be loaded: this board's module arena at $")
      PutHex8(gModErrorValue)
      PrintNl()
      If gModRegionKind = 0
        Print("   overlaps region ")
        PrintDec(gModErrorIndex)
        Print(" of its own reserved map - ")
        HwMonRegionSay(gModErrorIndex)
        Print(".")
      Else
        Print("   overlaps payload window ")
        PrintDec(gModErrorIndex)
        Print(", where a `boot` would land on it.")
      EndIf
      PrintNl()
      Print("   No module was loaded. This is a fault in the board's memory map and")
      PrintNl()
      Print("   `map` prints the ranges it is claiming.")
    Case #MOD_ERR_SEAM_ID
      Print("asked for a seam id outside the published vocabulary (")
      PrintDec(gModErrorValue)
      Print(").")
      PrintNl()
      Print("   Nothing was initialised. The module is built against a seam header")
      PrintNl()
      Print("   this Anvil does not publish.")
    Case #MOD_ERR_NOSERVICE
      Print("initialised without publishing a single service.")
      PrintNl()
      Print("   Every caller would find the seam empty and quietly fall back, so the")
      PrintNl()
      Print("   activation was unwound and the record reads FAILED. The module's init")
      PrintNl()
      Print("   has to fill at least one of the seams its header declares.")
    Case #MOD_ERR_QUIESCE
      Print("refused to put its hardware down, answering ")
      PrintDec(gModErrorValue)
      Print(".")
      PrintNl()
      Print("   It was NOT unloaded and it is still active, which is the safe half:")
      PrintNl()
      Print("   a driver torn out over its own objection leaves silicon mid-transaction.")
    Case #MOD_ERR_NOARENA
      Print("cannot be loaded: this board declares no module arena.")
      PrintNl()
      Print("   Driver modules are not available here yet - the board has to")
      PrintNl()
      Print("   reserve a range for them and prove it is disjoint from everything")
      PrintNl()
      Print("   else it owns. `map` prints what it does reserve. Nothing was done.")
    Default
      Print("was refused by the module loader.")
  EndSelect
  ModSayCode(code)
  PrintNl()
EndProcedure
