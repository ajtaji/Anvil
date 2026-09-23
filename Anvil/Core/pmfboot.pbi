; ======================================================================
;  pmfboot.pi4 - THE PAYLOAD CONTAINER ENGINE.
;
;  This file and Anvil/Core/bootfile_cmd.pbi are together what turns Anvil
;  from a monitor that can run a payload into a BOOTLOADER: something that
;  boots a program other than itself, from a setting that survives a power
;  cycle, without anybody typing an address, and without ever jumping into
;  an image it has not proved.
;
;  THIS half is the engine - parse a container header, judge it, place the
;  image, prove its hash, enter it. The `boot` command, the four settings
;  and the start-up countdown are the other half. See the note at the foot
;  of this file for why the boundary is there and what it buys.
;
;  It is CORE. It names no chip and touches no register. Storage reaches
;  it through the HwFile* seam (Anvil/Hal/hal.pbi), the jump through the
;  board's RunAt(), and the hash through Anvil/Core/sha256.pbi. Both
;  boards get all of it.
;
; ----------------------------------------------------------------------
;  WHY A CONTAINER, AND WHY NOT FIT
; ----------------------------------------------------------------------
;  The U-Boot inventory (Raspberry Pi 4/U-Boot command and feature
;  inventory.md, S5.6) put this exactly right and the design follows it:
;
;      FIT is a device tree because U-Boot already had a device tree
;      parser and needed arbitrary extensibility. We need "kernel or
;      payload, optional DTB, hash, entry point, signature" - about 64
;      bytes of fixed header. We can have FIT's actual benefits for 1% of
;      FIT's code.
;
;  Anvil has no FDT parser and is not getting one (S3.5). A fixed header
;  needs none: it is read with six PeekA-built integers and a memcmp.
;
;  And S5.1 states the principle the whole thing exists to serve:
;
;      the compiler knows the load address, the entry point, the BSS
;      extent and the image hash. The host should never have to be told
;      any of them.
;
;  That is why `boot APP.PMF` takes no address. It is not a convenience -
;  it removes the class of mistake that produces a board which almost
;  works. An image built for $00200000 and loaded at $00400000 does not
;  fail loudly; it runs until the first absolute reference and then does
;  something inexplicable. The compiler already knew the right number and
;  the operator was being asked to retype it from memory.
;
; ----------------------------------------------------------------------
;  THE HEADER, AS EMITTED BY THE COMPILER INTO <image>.pmf
; ----------------------------------------------------------------------
;  A .pmf file is a fixed header followed immediately by the flat image
;  bytes. Every multi-byte field is LITTLE-ENDIAN. Version 2 deliberately
;  leaves the complete 96-byte version-1 prefix unchanged, including the
;  image digest at offset 64, then appends compiler-owned provenance. An
;  old container therefore remains unambiguous; it is read by its exact
;  version-1 contract, not treated as a short version-2 container.
;
;    offset  size  field
;    ------  ----  ---------------------------------------------------
;      0      8    magic     the eight bytes "PMFBOOT" and a NUL
;      8      4    version   header format version. 1 or 2.
;     12      4    hdrlen    96 for version 1, 128 for version 2
;     16      8    load      where the image bytes must be placed
;     24      8    entry     where to branch once they are placed
;     32      8    imglen    how many image bytes follow the header
;     40      8    bssbase   start of the payload's zero-init region
;     48      8    bsslen    its length in bytes, 0 if it has none
;     56      4    flags     bit 0 the payload returns to the monitor
;                            bit 1 the payload expects a device tree
;                            bit 2 the payload expects the service table
;     60      4    reserved  written 0; v2 requires it to remain 0
;     64     32    sha256    the digest of the imglen image bytes
;    ------  ----  ---------------------------------------------------
;    Version 1 ends here (96 bytes total), and then the image.
;
;     96      4    arch      compiler architecture ID: 1 = AArch64
;    100      4    target    compiler target ID: BCM2837=2837,
;                            BCM2711=2711, QCM2290=2290
;    104      8    stack     initial stack top compiled into the image
;    112     16    reserved  written 0 and required 0 on read
;    ------  ----  ---------------------------------------------------
;    Version 2 ends here (128 bytes total), and then the image.
;
;  WHY 96 AND NOT THE 64 THE INVENTORY GUESSED AT. Because a SHA-256
;  digest is 32 bytes on its own and this machine's addresses are 64 bits.
;  Load, entry, image length, BSS base and BSS length are five 64-bit
;  numbers - forty bytes - and with the magic, version, header length and
;  flags that is sixty-four before the digest has a single byte. The
;  inventory's "about 64 bytes" was an estimate of the SHAPE, not a
;  measurement, and the shape is what it got right. Rounding the fixed
;  part up to 64 puts the digest at offset 64, 32-byte aligned, with the
;  image starting at 96 - and every field lands on its natural alignment,
;  which is worth more than matching a number in a note.
;
;  WHY THE MAGIC DOES NOT CARRY THE VERSION. "PMFBOOT1" would have been
;  one field instead of two and it would have been a mistake: a version 2
;  header would then fail the MAGIC test, and this monitor would tell an
;  operator holding a perfectly good newer container that it was not a
;  container at all. Wrong version and wrong file are different mistakes
;  with different fixes, so they get different refusals.
;
;  WHY THE FLAT IMAGE IS STILL EMITTED, unchanged, beside the .pmf. So
;  that nothing that exists today changes. `load APP.IMG` - which defaults to the staging address - then
;  `run` still works exactly as it did, `save` still writes a flat image,
;  and the container is an ADDITIONAL output for the path that wants the
;  numbers carried with the bytes.
;
; ----------------------------------------------------------------------
;  WHAT IS CHECKED BEFORE ANYTHING IS ENTERED, AND WHY EACH ONE IS THERE
; ----------------------------------------------------------------------
;  RULES.md rule 3 - loud errors beat silent wrong answers - has no
;  sharper application anywhere in this program than here, and the boot
;  command's guard list is deliberately the same shape as booti's: every
;  path that would hand the machine over is refused first, in a whole
;  sentence, having done nothing.
;
;    1. THE FILE IS BIG ENOUGH TO HOLD A HEADER. Under 96 bytes there is
;       nothing to parse and the parse would read past the file.
;    2. THE MAGIC. Not a container.
;    3. THE VERSION. A container this monitor does not know how to read.
;       Refused BY NUMBER, both numbers printed, rather than read anyway
;       on the hope the fields did not move.
;    4. THE HEADER LENGTH matches what this version means. A header that
;       claims a different size than the version implies is inconsistent
;       with itself and nothing in it can be trusted.
;    5. THE IMAGE LENGTH matches the file. header + imglen must be the
;       file size exactly. A short file means a truncated transfer; a long
;       one means something is appended that this monitor does not
;       understand. Either way the digest would be over the wrong bytes.
;    6. THE PLACEMENT IS LEGAL. The image range, and the BSS range, must
;       each lie inside a payload window and must not touch the monitor's
;       code or its data. This is HitsMonitor() and InPayload() - the same
;       two tests `load`, `receive` and `autoboot` use, over the same
;       constants - because "where may a payload live" is one question and
;       must not have two answers.
;    7. THE ENTRY IS INSIDE THE IMAGE. An entry outside the bytes just
;       placed is a branch into memory this container did not fill and
;       cannot vouch for, which is the exact thing the hash was computed
;       to prevent.
;    8. THE HASH. Mandatory, over the bytes AS PLACED, compared against
;       the digest the compiler put in the header. This is the check the
;       inventory called for twice (S3.8, S5.5) and it is the last one
;       before the jump.
;
;    9. THE FLAGS ARE NOT SELF-CONTRADICTORY. Bit 1 says "put a device
;       tree in x0" and bit 2 says "put the service table in x0", and
;       there is one x0. A container that sets both is refused, naming
;       both flags, having done nothing. IT RUNS EARLY - after guard 4
;       and before guard 5 - because it costs two register tests, it
;       needs nothing off the medium, and a container this confused about
;       what it wants should never reach the hash. See PmfCheckFlags.
;
;  ONLY THEN is the entry point taken.
;
;  NUMBERED IN THE ORDER THEY WERE WRITTEN, NOT THE ORDER THEY RUN. The
;  ninth arrived on 2026-09-04 with the payload ABI and slots into the
;  sequence between the fourth and the fifth; renumbering the other eight
;  to match would have broken every reference to "guard 6" in this tree
;  and in the vault, for nothing.
;
;  THE HASH IS COMPUTED AFTER PLACEMENT, NOT BEFORE. It would have been
;  easy to hash the bytes on their way past and save a second pass, and it
;  would have proved the wrong thing. What must be true is that the bytes
;  AT THE ADDRESS THE PROCESSOR WILL EXECUTE FROM are the compiler's
;  bytes. Hashing them in flight proves the medium delivered them; hashing
;  them where they landed proves that AND that the write went where it was
;  supposed to, that nothing overlapped them, and that the memory holds
;  what was written to it. On a board where a payload window can be
;  aliased or a DMA engine is still running, those are not the same claim.
;
; ----------------------------------------------------------------------
;  THE REBOOT-LOOP GUARD
; ----------------------------------------------------------------------
;  A bootloader that automatically enters a payload has invented a new way
;  to lose a board: a payload that hangs, or resets, is re-entered on
;  every boot, and there is never a prompt long enough to type the fix at.
;  The inventory names this twice (S2.10, S5.5) and names the deadman as
;  the thing that CREATES it.
;
;  So `boot.fails` is incremented AND WRITTEN TO THE MEDIUM BEFORE the
;  attempt, not after it. That ordering is the whole guard and it is the
;  only ordering that works: a counter written after a successful boot
;  never gets written at all when the boot hangs, which is precisely the
;  case it exists to detect. A payload that reaches its own steady state
;  clears the count with `boot ok`; one that never does leaves the count
;  standing, and after `boot.maxfails` attempts Anvil stops trying and
;  says why.
;
;  IT COSTS A WRITE TO THE BOOT MEDIUM ON EVERY AUTOMATIC BOOT, and that
;  is a real cost recorded here rather than discovered: a few hundred
;  bytes rewritten per boot, on a stick or an ESP. It is not free and it
;  is worth it, because the alternative is a board that can only be
;  rescued by pulling the medium and editing it on another computer -
;  which is exactly the dependency `save` was written to remove.
;
;  THE ESCAPE HATCH IS ALWAYS THERE, and that is a separate promise from
;  the counter. Every automatic boot counts down first and ANY KEYSTROKE
;  stops it, exactly as `autoboot` has always done. The counter is for the
;  case where nobody is watching; the countdown is for the case where
;  somebody is.
; ======================================================================

; ---- the container, as constants -------------------------------------
#PMF_HDR_LEN_V1 = 96           ; exact v1 header, retained indefinitely
#PMF_HDR_LEN_V2 = 128          ; v1 prefix plus compiler provenance
#PMF_HDR_LEN    = #PMF_HDR_LEN_V1 ; legacy/minimum-header alias
#PMF_VERSION_V1 = 1
#PMF_VERSION_V2 = 2
#PMF_VERSION    = #PMF_VERSION_V2 ; newest version this monitor reads
#PMF_DIGEST    = 32            ; SHA-256, in bytes
#PMF_PROGRESS_CHUNK = 65536    ; completed file/hash work between services

; Compiler-owned, append-only identifiers. These are metadata values,
; not board names guessed from a filename or source suffix.
#PMF_ARCH_AARCH64  = 1
#PMF_TARGET_BCM2837 = 2837
#PMF_TARGET_BCM2711 = 2711
#PMF_TARGET_QCM2290 = 2290

; Field offsets. Named, so a reader can check each against the table in
; the header above and so the parser reads as a list of facts.
#PMF_OFF_MAGIC   = 0
#PMF_OFF_VERSION = 8
#PMF_OFF_HDRLEN  = 12
#PMF_OFF_LOAD    = 16
#PMF_OFF_ENTRY   = 24
#PMF_OFF_IMGLEN  = 32
#PMF_OFF_BSSBASE = 40
#PMF_OFF_BSSLEN  = 48
#PMF_OFF_FLAGS   = 56
#PMF_OFF_RESERVED = 60
#PMF_OFF_SHA     = 64
#PMF_OFF_ARCH    = 96
#PMF_OFF_TARGET  = 100
#PMF_OFF_STACK   = 104
#PMF_OFF_EXTRES  = 112
#PMF_EXTRES_LEN  = 16

; The flags, as bit VALUES rather than bit numbers, because that is how
; they are tested.
#PMF_FLAG_RETURNS  = 1         ; the payload returns to the monitor
#PMF_FLAG_WANTS_DTB = 2        ; the payload expects a device tree in x0
#PMF_FLAG_WANTS_SERVICES = 4   ; the payload expects the SERVICE TABLE in x0
                               ; (Anvil/Hal/abi.pbi). Bit 2. MUTUALLY
                               ; EXCLUSIVE WITH BIT 1 - see PmfCheckFlags.
#PMF_STACK_ABI_BYTES = 16      ; AAPCS64 initial SP must address aligned memory

; The setting names, in one place. Every one of them is read in exactly
; one procedure below, and having the strings here rather than inline
; means a typo is a compile-time-visible fact and not a setting that
; silently never matches.
;
; A LITERAL CANNOT BE @'d IN THIS LANGUAGE - it wants a variable, field or
; array element - so these are procedures returning the literal's address,
; the same shape SettingsFileName() uses in Anvil/Core/settings.pbi.
Procedure.i PmfKeyFile()
  ProcedureReturn "boot.file"
EndProcedure
Procedure.i PmfKeyDelay()
  ProcedureReturn "boot.delay"
EndProcedure
Procedure.i PmfKeyFails()
  ProcedureReturn "boot.fails"
EndProcedure
Procedure.i PmfKeyMaxFails()
  ProcedureReturn "boot.maxfails"
EndProcedure

#PMF_DELAY_DEFAULT    = 2      ; seconds of countdown when boot.delay is unset
#PMF_MAXFAILS_DEFAULT = 3      ; attempts before the guard stops autobooting
#PMF_DELAY_MAX        = 60     ; a countdown longer than a minute is a hang

; ---- the parsed header, and the buffer it was parsed out of ----------
;
; IN THE MONITOR'S OWN BSS, and that is load-bearing rather than tidy: the
; header is read off the medium BEFORE anything about it has been
; believed, so it must land somewhere that a lying load address cannot
; reach. Reading it into the payload window it claims to want would mean
; trusting the number before checking it.
Global Dim gPmfHdr.b[128]
Global Dim gPmfWant.b[64]      ; the digest read out of the header
Global Dim gPmfGot.b[64]       ; the digest computed over the placed image

Global gPmfLoad.i
Global gPmfEntry.i
Global gPmfImgLen.i
Global gPmfBssBase.i
Global gPmfBssLen.i
Global gPmfFlags.i
Global gPmfVersion.i
Global gPmfHdrLen.i
Global gPmfArchitecture.i
Global gPmfTarget.i
Global gPmfStack.i
Global gPmfReserved.i
Global gPmfExtReservedOk.i

; The name of the file being booted, copied out of the line editor's
; buffer. gLine is overwritten by the next ReadLine, and the settings
; store hands back a pointer into its own table which a later SettingsSet
; would move, so neither may be held across the load.
Global Dim gPmfName.b[32]

; ======================================================================
;  Small readers. Byte at a time with PeekA, never a wide Peek.
;
;  The header may sit at any address - it is read into an array here, but
;  the boot-from-memory path parses one wherever the operator put it - and
;  a wide Peek of an unaligned address on this part is an alignment abort
;  with no console message at all. DumpMem in Anvil/Core/memcmd.pbi gives
;  the same reasoning at length; this is it applied once more.
;
;  PeekA AND NOT PeekB. PeekB sign-extends on this target, so a byte of
;  $EF read as -17 would poison every shift it took part in. fat.pi4:260
;  documents the trap and settings.pi4 repeats it; this is the third file
;  that would have been bitten by it.
; ======================================================================
Procedure.i PmfRd32(a.i)
  ProcedureReturn PeekA(a) | (PeekA(a + 1) << 8) | (PeekA(a + 2) << 16) | (PeekA(a + 3) << 24)
EndProcedure

Procedure.i PmfRd64(a.i)
  ProcedureReturn PmfRd32(a) | (PmfRd32(a + 4) << 32)
EndProcedure

; Zero means an unknown version. Keeping this mapping in one procedure
; makes every file-length and image-offset decision use the same contract.
Procedure.i PmfHeaderLengthForVersion(version.i)
  Select version
    Case #PMF_VERSION_V1
      ProcedureReturn #PMF_HDR_LEN_V1
    Case #PMF_VERSION_V2
      ProcedureReturn #PMF_HDR_LEN_V2
  EndSelect
  ProcedureReturn 0
EndProcedure

; ======================================================================
;  PmfParseAt(h) - read the header at address h into the globals above.
;
;  It PARSES ONLY. Every judgement about whether the numbers are sane
;  belongs to PmfCheckHeader and PmfCheckPlacement below, so that the
;  boot-from-file and boot-from-memory paths cannot drift apart in what
;  they check.
; ======================================================================
Procedure PmfParseAt(h.i)
  Define i.i
  gPmfVersion = PmfRd32(h + #PMF_OFF_VERSION)
  gPmfHdrLen  = PmfRd32(h + #PMF_OFF_HDRLEN)
  gPmfLoad    = PmfRd64(h + #PMF_OFF_LOAD)
  gPmfEntry   = PmfRd64(h + #PMF_OFF_ENTRY)
  gPmfImgLen  = PmfRd64(h + #PMF_OFF_IMGLEN)
  gPmfBssBase = PmfRd64(h + #PMF_OFF_BSSBASE)
  gPmfBssLen  = PmfRd64(h + #PMF_OFF_BSSLEN)
  gPmfFlags   = PmfRd32(h + #PMF_OFF_FLAGS)
  gPmfReserved = PmfRd32(h + #PMF_OFF_RESERVED)
  gPmfArchitecture = 0
  gPmfTarget = 0
  gPmfStack = 0
  gPmfExtReservedOk = 1
  i = 0
  While i < #PMF_DIGEST
    gPmfWant[i] = PeekA(h + #PMF_OFF_SHA + i)
    i = i + 1
  Wend

  ; Do not even read the extension for v1. A boot-from-memory v1 image is
  ; allowed to have its first image bytes immediately at offset 96; those
  ; bytes are image data, not provenance and not reserved space.
  If gPmfVersion = #PMF_VERSION_V2 And gPmfHdrLen = #PMF_HDR_LEN_V2
    gPmfArchitecture = PmfRd32(h + #PMF_OFF_ARCH)
    gPmfTarget = PmfRd32(h + #PMF_OFF_TARGET)
    gPmfStack = PmfRd64(h + #PMF_OFF_STACK)
    i = 0
    While i < #PMF_EXTRES_LEN
      If PeekA(h + #PMF_OFF_EXTRES + i) <> 0
        gPmfExtReservedOk = 0
      EndIf
      i = i + 1
    Wend
  EndIf
EndProcedure

; PmfMagicOk(h) - the eight magic bytes, compared one at a time against
; the characters spelled out. They are written as decimal codes rather
; than as a string literal because comparing eight bytes against a
; literal would mean a string compare against something that may not be
; NUL-terminated, and the whole point of this test is that the bytes
; might be anything at all.
Procedure.i PmfMagicOk(h.i)
  If PeekA(h + 0) <> 80  : ProcedureReturn 0 : EndIf     ; P
  If PeekA(h + 1) <> 77  : ProcedureReturn 0 : EndIf     ; M
  If PeekA(h + 2) <> 70  : ProcedureReturn 0 : EndIf     ; F
  If PeekA(h + 3) <> 66  : ProcedureReturn 0 : EndIf     ; B
  If PeekA(h + 4) <> 79  : ProcedureReturn 0 : EndIf     ; O
  If PeekA(h + 5) <> 79  : ProcedureReturn 0 : EndIf     ; O
  If PeekA(h + 6) <> 84  : ProcedureReturn 0 : EndIf     ; T
  If PeekA(h + 7) <> 0   : ProcedureReturn 0 : EndIf     ; NUL
  ProcedureReturn 1
EndProcedure

; One digest, lowercase hex, on the current line. Lowercase because that
; is what sha256sum prints on every other machine, and a digest you have
; to case-fold before comparing is a digest with a trap in it - the same
; ruling Anvil/Core/hash_cmd.pbi records. PutHexLower2 lives there.
Procedure PmfPutDigest(*d)
  Define i.i
  i = 0
  While i < #PMF_DIGEST
    PutHexLower2(PeekA(*d + i))
    i = i + 1
  Wend
EndProcedure

; ======================================================================
;  PmfCheckFlags() - THE NINTH GUARD. Do the flags contradict each other?
;
;  Bit 1 (#PMF_FLAG_WANTS_DTB) asks for a device-tree pointer in x0. Bit 2
;  (#PMF_FLAG_WANTS_SERVICES) asks for the service table in x0. There is
;  one x0, so a container that sets both has asked for two different
;  things in one register and there is no honest way to serve it.
;
;  WHY REFUSE RATHER THAN PICK ONE. Picking either would enter the payload
;  with a pointer to something it may not be expecting, and a payload that
;  dereferences a device tree as a service table takes a wild branch
;  through whatever the fifth word of the DTB happens to be. That is a
;  crash with no message, at an address nothing can explain, in a program
;  the monitor has already handed the machine to. The two flags are also
;  not close in meaning: bit 1 is for a Linux Image handed over by booti
;  and bit 2 is for a program that calls back INTO this monitor, so a
;  container setting both is not a preference to be resolved - it is a
;  build mistake, and the fix is one line in the source that made it.
;
;  IT RUNS BEFORE THE IMAGE LENGTH IS CHECKED and therefore before a byte
;  is read off the medium or written anywhere. Two register tests, no I/O,
;  and nothing has been done when it refuses.
;
;  Returns 1 when the flags are usable, 0 having printed the refusal.
; ======================================================================
Procedure.i PmfCheckFlags()
  Define wantsDtb.i
  Define wantsSvc.i

  wantsDtb = 0
  wantsSvc = 0
  If (gPmfFlags & #PMF_FLAG_WANTS_DTB) <> 0
    wantsDtb = 1
  EndIf
  If (gPmfFlags & #PMF_FLAG_WANTS_SERVICES) <> 0
    wantsSvc = 1
  EndIf

  If wantsDtb <> 0 And wantsSvc <> 0
    PrintN("!! this container asks for BOTH a device tree and the service table in")
    PrintN("   x0, and there is only one x0. Nothing was loaded and nothing was")
    PrintN("   entered.")
    Print("   Its flags word is ")
    PutHex8(gPmfFlags)
    PrintN(", which has bit 1 (expects-DTB) and bit 2")
    PrintN("   (wants-services) both set.")
    PrintN("   Bit 1 is for a Linux Image handed over by booti, which is given a")
    PrintN("   device-tree pointer. Bit 2 is for a payload that calls back into this")
    PrintN("   monitor through the service table. A program needs one or the other,")
    PrintN("   never both, and this monitor will not guess which one was meant -")
    PrintN("   entering with the wrong pointer would take a wild branch through")
    PrintN("   whatever the other structure happens to hold, with the machine")
    PrintN("   already handed over and no prompt to say so at.")
    PrintN("   Rebuild the payload with one flag.")
    ProcedureReturn 0
  EndIf

  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PmfCheckV2Metadata() - validate compiler provenance, for v2 only.
;
;  Version 1 had no architecture, target or stack provenance and remains
;  readable under that exact historical contract. Version 2 does carry
;  those facts, so accepting zero, an unknown ID or nonzero reserved bytes
;  would discard the very guarantee for which the extension was added.
;  A board-specific slot loader may impose a narrower target requirement
;  after this common format check (for example BCM2837 for a Pi 3 slot).
; ======================================================================
Procedure.i PmfCheckV2Metadata()
  Define knownTarget.i
  Define expectedTarget.i

  If gPmfReserved <> 0 Or gPmfExtReservedOk = 0
    PrintN("!! this version-2 container has nonzero reserved metadata bytes.")
    PrintN("   They are required to be zero, so the header is damaged or belongs")
    PrintN("   to a format this monitor does not know. Nothing was loaded.")
    ProcedureReturn 0
  EndIf

  If gPmfArchitecture <> #PMF_ARCH_AARCH64
    Print("!! this version-2 container names architecture ID ")
    PrintDec(gPmfArchitecture)
    PrintN(", but this")
    Print("   monitor accepts AArch64 architecture ID ")
    PrintDec(#PMF_ARCH_AARCH64)
    PrintN(". Nothing was loaded.")
    ProcedureReturn 0
  EndIf

  knownTarget = 0
  Select gPmfTarget
    Case #PMF_TARGET_BCM2837
      knownTarget = 1
    Case #PMF_TARGET_BCM2711
      knownTarget = 1
    Case #PMF_TARGET_QCM2290
      knownTarget = 1
  EndSelect
  If knownTarget = 0
    Print("!! this version-2 container names unknown target ID ")
    PrintDec(gPmfTarget)
    PrintN(".")
    PrintN("   This monitor will not guess a board from a filename. Nothing was")
    PrintN("   loaded; rebuild the payload with a supported compiler target.")
    ProcedureReturn 0
  EndIf

  expectedTarget = HwPmfTargetId()
  If gPmfTarget <> expectedTarget
    Print("!! this version-2 container was compiled for target ID ")
    PrintDec(gPmfTarget)
    PrintN(", but this")
    Print("   board requires target ID ")
    PrintDec(expectedTarget)
    PrintN(". Nothing was loaded. The image may be valid for its own board,")
    PrintN("   but relabelling or copying it here cannot make its generated MMIO,")
    PrintN("   memory map and startup code belong to this machine.")
    ProcedureReturn 0
  EndIf

  If gPmfStack <= 0 Or (gPmfStack & 15) <> 0
    Print("!! this version-2 container names stack top ")
    PutAddr(gPmfStack)
    PrintN(", which is zero")
    PrintN("   or not 16-byte aligned as the AArch64 ABI requires. Nothing was")
    PrintN("   loaded; rebuild the payload rather than guessing a stack address.")
    ProcedureReturn 0
  EndIf

  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PmfCheckHeader(fileLen) - is this a container this monitor can read?
;
;  fileLen is the total size of the .pmf, header included, or 0 for the
;  boot-from-memory path where there is no file and therefore no total to
;  check against. Prints a whole sentence and returns 0 on any refusal.
; ======================================================================
Procedure.i PmfCheckHeader(fileLen.i)
  Define expectedHdr.i

  expectedHdr = PmfHeaderLengthForVersion(gPmfVersion)
  If expectedHdr = 0
    PrintN("!! this is a payload container, but of a version this monitor cannot")
    Print("   read: it says version ")
    PrintDec(gPmfVersion)
    Print(" and this monitor reads versions ")
    PrintDec(#PMF_VERSION_V1)
    Print(" and ")
    PrintDec(#PMF_VERSION_V2)
    PrintN(".")
    PrintN("   Nothing was loaded and nothing was entered. The fields may have")
    PrintN("   moved between versions, so reading it anyway and hoping would be a")
    PrintN("   guess about where the load address is - and a wrong load address is")
    PrintN("   the one mistake this container format exists to make impossible.")
    PrintN("   Rebuild the payload with this compiler, or use load and run with")
    PrintN("   the flat image and an address you supply yourself.")
    ProcedureReturn 0
  EndIf

  If gPmfHdrLen <> expectedHdr
    Print("!! this container says its header is ")
    PrintDec(gPmfHdrLen)
    PrintN(" bytes long, and a version")
    Print("   ")
    PrintDec(gPmfVersion)
    Print(" header is ")
    PrintDec(expectedHdr)
    PrintN(" bytes. It disagrees with itself, so no field")
    PrintN("   in it can be trusted and nothing was loaded. The file is damaged or")
    PrintN("   was written by something that is not this compiler.")
    ProcedureReturn 0
  EndIf

  If fileLen > 0 And fileLen < gPmfHdrLen
    Print("!! this version-")
    PrintDec(gPmfVersion)
    Print(" container is only ")
    PrintDec(fileLen)
    Print(" bytes long, but its")
    Print(" header requires ")
    PrintDec(gPmfHdrLen)
    PrintN(" bytes. Nothing was loaded.")
    ProcedureReturn 0
  EndIf

  If gPmfVersion = #PMF_VERSION_V2
    If PmfCheckV2Metadata() = 0
      ProcedureReturn 0
    EndIf
  EndIf

  ; THE NINTH GUARD, HERE. After the header length (guard 4) and before
  ; the image length (guard 5), which is where it was specified to go and
  ; where it belongs: the flags word has only just been proved to be AT
  ; the offset this version puts it at, and everything below this line
  ; starts reasoning about bytes on the medium.
  If PmfCheckFlags() = 0
    ProcedureReturn 0
  EndIf

  If gPmfImgLen <= 0
    Print("!! this container says its image is ")
    PrintDec(gPmfImgLen)
    PrintN(" bytes long, which is not a")
    PrintN("   length. There is nothing to place and nothing to enter, so nothing")
    PrintN("   was done.")
    ProcedureReturn 0
  EndIf

  If gPmfImgLen > #LEN_MAX
    PrintN("!! this container says its image is more than a gigabyte, which is more")
    PrintN("   than the address arithmetic in these range checks stays honest over.")
    PrintN("   Nothing was loaded. A payload that size is not something this monitor")
    PrintN("   was built to place.")
    ProcedureReturn 0
  EndIf

  If gPmfBssLen < 0 Or gPmfBssLen > #LEN_MAX
    PrintN("!! this container states a zero-init region that is either negative or")
    PrintN("   bigger than a gigabyte, so it is not a length this monitor will act")
    PrintN("   on. Nothing was loaded.")
    ProcedureReturn 0
  EndIf

  If fileLen > 0
    If (gPmfHdrLen + gPmfImgLen) <> fileLen
      Print("!! this container says it holds ")
      PrintDec(gPmfImgLen)
      PrintN(" image bytes, which with its")
      Print("   ")
      PrintDec(gPmfHdrLen)
      Print("-byte header makes ")
      PrintDec(gPmfHdrLen + gPmfImgLen)
      PrintN(" bytes - but the file on the")
      Print("   medium is ")
      PrintDec(fileLen)
      PrintN(" bytes. Nothing was loaded.")
      If fileLen < (gPmfHdrLen + gPmfImgLen)
        PrintN("   The file is SHORTER than its own header says it should be, which is")
        PrintN("   what a transfer that stopped part way leaves behind. Copy it again.")
      Else
        PrintN("   The file is LONGER than its own header says it should be. Something")
        PrintN("   is appended to it that this monitor does not understand, and the")
        PrintN("   hash below would have been computed over the wrong bytes.")
      EndIf
      ProcedureReturn 0
    EndIf
  EndIf

  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PmfCheckPlacement() - may these bytes go where this container says?
;
;  TWO RANGES ARE CHECKED, NOT ONE, and the second is the one that would
;  have been forgotten. The image is obvious. The BSS is a region the
;  payload will write to the moment it starts, and on this project's own
;  Pi 4 build it is nowhere near the image - Anvil itself loads at
;  $00200000 and puts its BSS at $0D000000, above the monitor-owned Vulkan
;  heap. Sharing one window would let a payload erase the monitor's globals. A
;  container whose image is placed legally and whose BSS lands on top of
;  the monitor's globals would run for exactly as long as it took the
;  payload to zero them.
;
;  IT USES HitsMonitor AND InPayload AND NOTHING ELSE. Those are the same
;  two tests `load`, `receive`, `save` and `autoboot` use, over the same
;  board constants. "Where may a payload live" is one question; a second
;  implementation of the answer here would be a second answer, and the two
;  would diverge the first time a board's memory map changed.
; ======================================================================
Procedure.i PmfCheckRange(lo.i, hi.i, *what)
  If HitsMonitor(lo, hi) <> 0
    Print("!! the ")
    UartWriteStr(*what)
    Print(" this container asks for, ")
    PutAddr(lo)
    Print(" to ")
    PutAddr(hi)
    PrintN(",")
    Print("   runs over the monitor itself, which lives at ")
    PutAddr(gMonHitLo)
    Print(" to ")
    PutAddr(gMonHitHi)
    PrintN(".")
    PrintN("   Nothing was loaded and nothing was entered. Placing a payload there")
    PrintN("   would overwrite the code that is reading this file, or the working")
    PrintN("   storage it is reading it with, and the board would stop with no")
    PrintN("   prompt to type the fix at.")
    PrintN("   This is the payload's own stated address, not one you typed, so the")
    PrintN("   payload was built for a different memory map than this board has.")
    PrintN("   Rebuild it for one of these windows:")
    PutWindows()
    ProcedureReturn 0
  EndIf
  If InPayload(lo, hi) = 0
    Print("!! the ")
    UartWriteStr(*what)
    Print(" this container asks for, ")
    PutAddr(lo)
    Print(" to ")
    PutAddr(hi)
    PrintN(",")
    PrintN("   is not inside either payload window, so nothing was loaded. A range")
    PrintN("   that straddles the gap between the two windows fails this test whole")
    PrintN("   rather than having the half that lands in memory written.")
    PutWindows()
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i PmfCheckPlacement()
  Define imageHi.i
  Define bssHi.i
  Define stackLo.i
  Define stackHi.i

  imageHi = gPmfLoad + gPmfImgLen - 1
  If PmfCheckRange(gPmfLoad, gPmfLoad + gPmfImgLen - 1, "image") = 0
    ProcedureReturn 0
  EndIf

  ; THE ZERO-INIT REGION, when there is one. A payload with no BSS states
  ; a length of 0 and there is no range to check - testing an empty range
  ; would compute hi = base - 1 and compare backwards.
  If gPmfBssLen > 0
    bssHi = gPmfBssBase + gPmfBssLen - 1
    If PmfCheckRange(gPmfBssBase, bssHi, "zero-init region") = 0
      ProcedureReturn 0
    EndIf
    If gPmfBssBase <= imageHi And bssHi >= gPmfLoad
      PrintN("!! this container's image and zero-init region overlap. The monitor")
      PrintN("   would erase part of the image while clearing BSS, or BSS would")
      PrintN("   overwrite code when the payload starts. Nothing was loaded.")
      ProcedureReturn 0
    EndIf
  Else
    bssHi = gPmfBssBase - 1
  EndIf

  ; PMF v2 records a stack top, not an extent. Prove the ABI-required first
  ; 16 bytes below that top are in a payload stack window, then reject any
  ; overlap with image or BSS. This prevents an invalid initial SP from
  ; targeting monitor-owned or unmapped bytes; it does not claim to bound
  ; later stack growth, which the current PMF format cannot describe.
  If gPmfVersion = #PMF_VERSION_V2
    If gPmfStack < #PMF_STACK_ABI_BYTES
      PrintN("!! this container's stack top is too low for the required aligned")
      PrintN("   AArch64 stack area. Nothing was loaded.")
      ProcedureReturn 0
    EndIf
    stackLo = gPmfStack - #PMF_STACK_ABI_BYTES
    stackHi = gPmfStack - 1
    If HwPmfStackAllowed(stackLo, stackHi) = 0
      Print("!! this container's initial 16-byte stack area, ")
      PutAddr(stackLo)
      Print(" to ")
      PutAddr(stackHi)
      PrintN(", is not in a payload stack window. Nothing was loaded.")
      PutWindows()
      ProcedureReturn 0
    EndIf
    If stackLo <= imageHi And stackHi >= gPmfLoad
      PrintN("!! this container's stack range overlaps its image. Nothing was")
      PrintN("   loaded; the payload stack would overwrite executable bytes.")
      ProcedureReturn 0
    EndIf
    If gPmfBssLen > 0 And stackLo <= bssHi And stackHi >= gPmfBssBase
      PrintN("!! this container's stack range overlaps its zero-init region.")
      PrintN("   Nothing was loaded; stack use could corrupt payload data.")
      ProcedureReturn 0
    EndIf
  EndIf

  ; THE ENTRY MUST BE INSIDE THE IMAGE. Not merely legal - INSIDE. The
  ; hash proves the image bytes; an entry outside them is a branch into
  ; memory this container never described, and the hash says nothing at
  ; all about what is there.
  If gPmfEntry < gPmfLoad Or gPmfEntry > (gPmfLoad + gPmfImgLen - 1)
    Print("!! this container's entry point, ")
    PutAddr(gPmfEntry)
    PrintN(", is outside the image it")
    Print("   describes, which runs ")
    PutAddr(gPmfLoad)
    Print(" to ")
    PutAddr(gPmfLoad + gPmfImgLen - 1)
    PrintN(".")
    PrintN("   Nothing was loaded and nothing was entered. The hash in this header")
    PrintN("   proves the IMAGE bytes and says nothing whatever about memory outside")
    PrintN("   them, so entering there would be a jump into something unverified -")
    PrintN("   which is the one thing this whole command exists to refuse.")
    ProcedureReturn 0
  EndIf

  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PmfVerifyPlaced() - the mandatory hash, over the bytes as placed.
;
;  ANY KEYSTROKE STOPS IT AND A STOPPED ONE VERIFIES NOTHING. hash_cmd.pi4
;  makes the same ruling for sha256sum and gives the reason: a hash of
;  part of a range looks exactly like a hash of all of it. Here the stakes
;  are higher, because the value is not printed for a human to compare -
;  it decides whether the machine changes hands. So a stopped hash is a
;  REFUSAL, not a pass.
;
;  Returns 1 only when the digest matches. Prints the digest either way,
;  because "which hash did it actually get" is the first question anybody
;  asks when a verify fails, and making them re-run it by hand to find out
;  is making them do the monitor's job.
; ======================================================================
Procedure.i PmfVerifyPlaced()
  Define done.i
  Define chunk.i
  Define i.i
  Define bad.i

  Print("Verifying ")
  PrintDec(gPmfImgLen)
  Print(" bytes at ")
  PutAddr(gPmfLoad)
  PrintN(" against the container's SHA-256 ...")
  UartDrain()

  Sha256Begin()
  done = 0
  While done < gPmfImgLen
    If OutBreak() <> 0
      PrintN("!! stopped part way through the hash, so NOTHING WAS ENTERED. A hash")
      PrintN("   of part of an image looks exactly like a hash of all of it and is")
      PrintN("   not one, and this digest is what decides whether the board changes")
      PrintN("   hands. The image is in memory; nothing has been run.")
      ProcedureReturn 0
    EndIf
    chunk = gPmfImgLen - done
    If chunk > #PMF_PROGRESS_CHUNK
      chunk = #PMF_PROGRESS_CHUNK ; 64 KiB between break/service checks
    EndIf
    Sha256Update(gPmfLoad + done, chunk)
    done = done + chunk
    ; Sha256Update has returned: no compression round or partial block copy
    ; is live across this cooperative display boundary.
    ScreenServiceTick()
  Wend
  Sha256End(@gPmfGot[0])

  bad = 0
  i = 0
  While i < #PMF_DIGEST
    If (gPmfGot[i] & $FF) <> (gPmfWant[i] & $FF)
      bad = 1
    EndIf
    i = i + 1
  Wend

  Print("  computed ")
  PmfPutDigest(@gPmfGot[0])
  PrintNl()

  If bad <> 0
    Print("  expected ")
    PmfPutDigest(@gPmfWant[0])
    PrintNl()
    PrintN("!! THE HASH DOES NOT MATCH, so nothing was entered. The bytes now in")
    PrintN("   memory are not the bytes the compiler put in this container. That is")
    PrintN("   a damaged file, a medium that returned something other than what was")
    PrintN("   written to it, or a container somebody has altered - this check does")
    PrintN("   not tell the three apart and does not need to, because the answer to")
    PrintN("   all three is the same: do not run it.")
    PrintN("   The image HAS been written into memory, so what is at that address")
    PrintN("   now is a corrupted payload. Do not type run. Load something else")
    PrintN("   over it, or copy the file again and boot it again.")
    ProcedureReturn 0
  EndIf

  PrintN("  the digest matches the one the compiler put in the container.")
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PmfZeroBss() - clear the payload's zero-init region.
;
;  WHY THE MONITOR DOES THIS AND DOES NOT LEAVE IT TO THE PAYLOAD. Because
;  a flat image has no loader of its own. On silicon, a built payload
;  reaches _start with its BSS holding whatever the last program left
;  in that DRAM, and every uninitialised global reads as that. The one
;  thing a container carrying a BSS extent is FOR is that somebody can
;  act on it, and the monitor is the only somebody in the room.
;
;  IT IS SKIPPED WHEN THE PAYLOAD SAYS IT HAS NONE, and the range has
;  already been proved legal by PmfCheckPlacement - this procedure does no
;  checking of its own on purpose, so that there is exactly one place
;  where "may this memory be written" is decided.
; ======================================================================
Procedure PmfZeroBss()
  Define a.i
  Define e.i
  If gPmfBssLen <= 0
    ProcedureReturn
  EndIf
  Print("Clearing ")
  PrintDec(gPmfBssLen)
  Print(" bytes of zero-init memory at ")
  PutAddr(gPmfBssBase)
  PrintN(".")
  a = gPmfBssBase
  e = gPmfBssBase + gPmfBssLen
  While a < e
    PokeB(a, 0)
    a = a + 1
  Wend
EndProcedure

; ======================================================================
;  PmfEnter() - hand the board over.
;
;  Everything above has passed. This arms the monitor's entry point so
;  that a payload which returns leaves `run` pointing at the right place,
;  says what is about to happen, and calls the board's RunAt() - the ONE
;  place in this program a payload is entered, shared with `run` and with
;  `autoboot`, so the three cannot drift apart in what they flush, what
;  they stop and what they print.
; ======================================================================
Procedure PmfEnter()
  gEntry = gPmfEntry
  gHaveEntry = 1
  If (gPmfFlags & #PMF_FLAG_WANTS_DTB) <> 0
    PrintN("Note: this payload's header says it expects a device tree pointer. This")
    PrintN("  command enters a payload the way run does and passes it nothing, so")
    PrintN("  it will not get one here. booti is the command that passes a device")
    PrintN("  tree, and it takes a Linux Image rather than a container.")
  EndIf
  If (gPmfFlags & #PMF_FLAG_RETURNS) <> 0
    PrintN("This payload was built to return to the monitor, so the prompt should")
    PrintN("come back when it is finished.")
  EndIf

  ; ------------------------------------------------------------------
  ;  THE HANDOVER. The one place in this monitor a payload is given
  ;  anything in x0 at all.
  ;
  ;  THE TABLE IS BUILT HERE AND NOT AT START-UP, and that is worth a
  ;  line. BuildServiceTable() fills 184 pointers into the monitor's own
  ;  BSS; doing it once per boot at Main() would spend the work on every
  ;  session that never loads a payload, and - much more to the point -
  ;  would leave a table standing for the whole life of the prompt that
  ;  nothing has any business reading. Filling it immediately before the
  ;  jump means the pointers in it are the ones this monitor has right
  ;  now, and it is cheap: 184 stores.
  ;
  ;  It is idempotent, so a second container in the same session refills
  ;  it rather than accumulating anything.
  ;
  ;  RunAt() CLEARS gGoX0 ON THE WAY BACK OUT, so a plain `run` after
  ;  this one is not handed a stale pointer. See RaspberryPi4/Board/cache.pi4.
  ; ------------------------------------------------------------------
  ; What SvcReturn is allowed to do. Anvil/Hal/abi.pbi is included before
  ; this file - it has to be, because this procedure calls
  ; BuildServiceTable - so it cannot read #PMF_FLAG_RETURNS itself. One
  ; assignment here, from the container's own flags word, is the whole
  ; coupling and there is no second spelling of bit 0 to drift.
  gSvcMayReturn = 0
  If (gPmfFlags & #PMF_FLAG_RETURNS) <> 0
    gSvcMayReturn = 1
  EndIf

  If (gPmfFlags & #PMF_FLAG_WANTS_SERVICES) <> 0
    BuildServiceTable()
    gGoX0 = SvcTableAddr()
    Print("This payload asked for the service table, so it is entered with x0 = ")
    PutAddr(gGoX0)
    PrintNl()
    Print("  (ABI ")
    PrintDec(#SVC_ABI_MAJOR)
    Print(".")
    PrintDec(#SVC_ABI_MINOR)
    Print(", ")
    PrintDec(#SVC_SLOT_COUNT)
    PrintN(" slots). It can call back into this monitor.")
  Else
    gGoX0 = 0
  EndIf

  ; RunAt may never return. All validation, digest and ABI prose is complete,
  ; so present it now rather than waiting for a prompt a healthy payload is
  ; not required to give back.
  ScreenServiceTick()
  RunAt(gPmfEntry)
EndProcedure

; ======================================================================
;  PmfBootAt(container) - verify and boot a container ALREADY IN MEMORY.
;
;  The whole flow for the case where the bytes are already here: parse,
;  check, copy the image to its load address, hash it there, enter.
;
;  WHY THIS EXISTS AS A REAL COMMAND AND NOT ONLY AS A TEST HOOK. Anvil's
;  own delivery path is `receive` and `wb` - a container arrives over the
;  wire or over the air, into a payload window, and there is no medium
;  involved at any point. Making that path go through a file would mean
;  writing the container to the boot medium in order to read it back,
;  which is slower, wears the medium and adds a failure mode. It is also
;  the only form of this flow that can be exercised without storage, and
;  that is what makes the whole verify-and-place path testable under an
;  emulator with no filesystem in it.
;
;  THE COPY MAY OVERLAP, and that is handled rather than forbidden. A
;  container received at $00400000 whose image loads at $00400060 is a
;  perfectly reasonable thing for a host to arrange, and the source and
;  destination then overlap with the destination HIGHER, so a forward copy
;  would eat its own tail. The direction is chosen from the addresses, the
;  same decision Anvil/Core/memcmd.pbi's CmdCopy makes and for the same
;  reason.
; ======================================================================
Procedure.i PmfBootAt(container.i)
  Define src.i
  Define dst.i
  Define n.i
  Define i.i

  If PmfMagicOk(container) = 0
    Print("!! there is no payload container at ")
    PutAddr(container)
    PrintN(": the first eight bytes")
    PrintN("   are not the container magic (they should read 50 4D 46 42 4F 4F 54")
    PrintN("   00, which is 'PMFBOOT' and a NUL). Nothing was loaded and nothing")
    PrintN("   was entered - entering memory that is not a payload is the one thing")
    PrintN("   this command must never do.")
    PrintN("   A flat image without a container header is run with load and run,")
    PrintN("   giving the address yourself. A container is the .pmf file the")
    PrintN("   compiler writes beside it.")
    ProcedureReturn 0
  EndIf

  PmfParseAt(container)
  If PmfCheckHeader(0) = 0
    ProcedureReturn 0
  EndIf
  If PmfCheckPlacement() = 0
    ProcedureReturn 0
  EndIf

  src = container + gPmfHdrLen
  dst = gPmfLoad
  n   = gPmfImgLen

  Print("Placing ")
  PrintDec(n)
  Print(" bytes at ")
  PutAddr(dst)
  Print(", the address the payload was built for")
  PrintNl()
  Print("  (from the container at ")
  PutAddr(container)
  PrintN(").")
  UartDrain()

  If dst > src
    ; Backwards. The destination is above the source, so a forward copy
    ; would overwrite bytes it has not read yet when the two overlap.
    i = n - 1
    While i >= 0
      PokeB(dst + i, PeekA(src + i))
      i = i - 1
    Wend
  Else
    i = 0
    While i < n
      PokeB(dst + i, PeekA(src + i))
      i = i + 1
    Wend
  EndIf

  If PmfVerifyPlaced() = 0
    ProcedureReturn 0
  EndIf

  PmfZeroBss()
  PmfEnter()
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PmfBootFile(*name) - the main event: verify and boot a container from
;  a named file on the boot medium.
;
;  THE HEADER IS READ FIRST, ON ITS OWN, INTO THE MONITOR'S MEMORY. Only
;  once its load address has been checked is a single image byte read, and
;  it is then read STRAIGHT TO THAT ADDRESS. There is no staging buffer,
;  and not having one is the point: a staging buffer big enough for any
;  payload would have to be a payload window, so staging would mean
;  writing the image somewhere it was not asked to go before writing it
;  where it was - twice the traffic and an extra range to prove safe.
;
;  Returns 1 only if the payload was entered AND returned. It does not
;  return at all for a payload that does not.
; ======================================================================
Procedure.i PmfBootFile(*name)
  Define fileLen.i
  Define got.i
  Define part.i
  Define chunk.i
  Define i.i

  If HwStorageUp() = 0
    PrintN("!! nothing was booted, because no medium came up and the container")
    PrintN("   could not be read. Memory is untouched.")
    ProcedureReturn 0
  EndIf

  If HwFileOpen(*name) = 0
    Print("!! the container ")
    UartWriteStr(*name)
    PrintN(" could not be opened, so nothing was")
    PrintN("   loaded and memory is untouched.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())    ; a POINTER - never Print, see hal.pi4
    PrintNl()
    PrintN("   The name has to be a short 8.3 name on the boot medium; case does")
    PrintN("   not matter. Type fatls to see what is there.")
    ProcedureReturn 0
  EndIf

  fileLen = HwFileSize()
  If fileLen < #PMF_HDR_LEN
    Print("!! ")
    UartWriteStr(*name)
    Print(" is ")
    PrintDec(fileLen)
    PrintN(" bytes long, and a payload container")
    Print("   header alone is ")
    PrintDec(#PMF_HDR_LEN)
    PrintN(" bytes. There is not even a header there to")
    PrintN("   read, so nothing was loaded. This is a flat image or a truncated")
    PrintN("   file, not a container.")
    HwFileClose()
    ProcedureReturn 0
  EndIf

  ; Clear the entire maximum header first. This makes a short v2 header
  ; deterministic and, more importantly, prevents metadata from a prior
  ; boot attempt surviving into the next parse.
  i = 0
  While i < #PMF_HDR_LEN_V2
    gPmfHdr[i] = 0
    i = i + 1
  Wend

  ; Read the common v1 prefix first. Only an exact v2/128 declaration is
  ; allowed to make us read the extension; for a v1 file, offset 96 is
  ; already image data and must never be mistaken for provenance.
  got = HwFileReadAt(0, @gPmfHdr[0], #PMF_HDR_LEN_V1)
  If got <> #PMF_HDR_LEN_V1
    PrintN("!! the container's header could not be read off the medium, so nothing")
    PrintN("   was loaded and memory is untouched.")
    Print("   The medium said: ")
    UartWriteStr(HwFileErrorText())
    PrintNl()
    HwFileClose()
    ProcedureReturn 0
  EndIf

  If PmfMagicOk(@gPmfHdr[0]) = 0
    Print("!! ")
    UartWriteStr(*name)
    PrintN(" is not a payload container: its first eight")
    PrintN("   bytes are not the container magic (50 4D 46 42 4F 4F 54 00, which is")
    PrintN("   'PMFBOOT' and a NUL). Nothing was loaded and memory is untouched.")
    PrintN("   A flat image is loaded with load and started with run, giving the")
    PrintN("   address yourself. The container is the .pmf file the compiler writes")
    PrintN("   beside the flat image, and it is the one that knows its own address.")
    HwFileClose()
    ProcedureReturn 0
  EndIf

  ; Inspect only the two common-prefix fields needed to decide whether a
  ; tail exists. PmfCheckHeader below still owns all judgement and prints
  ; the precise refusal for an unknown version or inconsistent length.
  If PmfRd32(@gPmfHdr[0] + #PMF_OFF_VERSION) = #PMF_VERSION_V2 And PmfRd32(@gPmfHdr[0] + #PMF_OFF_HDRLEN) = #PMF_HDR_LEN_V2
    If fileLen >= #PMF_HDR_LEN_V2
      got = HwFileReadAt(#PMF_HDR_LEN_V1, @gPmfHdr[0] + #PMF_HDR_LEN_V1, #PMF_HDR_LEN_V2 - #PMF_HDR_LEN_V1)
      If got <> (#PMF_HDR_LEN_V2 - #PMF_HDR_LEN_V1)
        PrintN("!! the container's version-2 metadata could not be read off the")
        PrintN("   medium, so nothing was loaded and memory is untouched.")
        Print("   The medium said: ")
        UartWriteStr(HwFileErrorText())
        PrintNl()
        HwFileClose()
        ProcedureReturn 0
      EndIf
    EndIf
  EndIf

  PmfParseAt(@gPmfHdr[0])
  If PmfCheckHeader(fileLen) = 0
    HwFileClose()
    ProcedureReturn 0
  EndIf
  If PmfCheckPlacement() = 0
    HwFileClose()
    ProcedureReturn 0
  EndIf

  ; --- only NOW does a byte of image touch memory ----------------------
  Print("Loading ")
  PrintDec(gPmfImgLen)
  Print(" bytes to ")
  PutAddr(gPmfLoad)
  PrintN(", the address the payload was built")
  Print("for, with entry at ")
  PutAddr(gPmfEntry)
  PrintN(".")
  UartDrain()

  ; Show the phase before entering the first potentially long medium read.
  ScreenServiceTick()
  got = 0
  While got < gPmfImgLen
    chunk = gPmfImgLen - got
    If chunk > #PMF_PROGRESS_CHUNK
      chunk = #PMF_PROGRESS_CHUNK
    EndIf
    part = HwFileReadAt(gPmfHdrLen + got, gPmfLoad + got, chunk)
    If part < 0
      If got = 0
        got = part
      EndIf
      Break
    EndIf
    If part = 0
      Break
    EndIf
    got = got + part
    ; HwFileReadAt is an offset transaction and has returned. No medium or
    ; file backend scratch is live when the display service runs.
    ScreenServiceTick()
    If part <> chunk
      Break
    EndIf
  Wend
  HwFileClose()

  If got <> gPmfImgLen
    Print("!! the image stopped part way through, after ")
    PrintDec(got)
    Print(" of ")
    PrintDec(gPmfImgLen)
    PrintNl()
    PrintN("   bytes had already been written into memory. Nothing was entered, and")
    PrintN("   what is at that address now is the beginning of a payload with")
    PrintN("   whatever was there before underneath it. Do not run it.")
    If got >= 0
      Print("   The medium said: ")
      UartWriteStr(HwFileErrorText())
      PrintNl()
    EndIf
    ProcedureReturn 0
  EndIf

  If PmfVerifyPlaced() = 0
    ProcedureReturn 0
  EndIf

  PmfZeroBss()
  PmfEnter()
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  WHAT IS NOT IN THIS FILE, and why the split is here rather than
;  nowhere.
;
;  Everything above is the CONTAINER ENGINE: parse a header, judge it,
;  place an image, prove it, enter it. It reads no command line, touches
;  no settings store and prints no help. Its whole dependency list is the
;  memory-range checks, the formatter, SHA-256, the HwFile* seam and the
;  board's RunAt.
;
;  The console side - the `boot` command word, its sub-commands, the four
;  settings and the start-up countdown - lives in
;  Anvil/Core/bootfile_cmd.pbi, and it needs the line editor and the
;  settings store on top of all of that.
;
;  THE SPLIT IS NOT TIDINESS. It is what lets the engine be TESTED. The
;  gate for this code, RaspberryPi4/Examples/Diagnostics/pi4BootContainerSelfTest.pi4,
;  stages three containers in memory and runs the real verify-place-enter
;  path over them under the A64 oracle. To do that it must build the
;  engine WITHOUT the line editor, because the line editor reaches for a
;  USB keyboard, a mouse tick and a Wi-Fi console - none of which exist in
;  a diagnostic, and all of which would have to be faked to prove
;  something about a hash. One include boundary in the right place is the
;  difference between a testable bootloader and one that is only ever
;  exercised by hand on a board.
;
;  It is the same boundary Anvil/Core/hash_cmd.pbi draws over
;  Anvil/Core/sha256.pbi: the algorithm is a file, the command is a file,
;  and the command is the disposable half.
; ======================================================================
