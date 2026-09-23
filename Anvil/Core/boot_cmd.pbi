; ======================================================================
;  boot_cmd.pi4 - the `booti` and `bootm` commands. Boot an operating
;  system from memory: an arm64 Linux `Image` (booti) or a boot container
;  (bootm).
;
;  This file is CORE: it names no chip and touches no register. It validates
;  the image in memory, chooses the device tree, prints exactly what it is
;  about to do, and then calls the board's HwBootToEl1 seam (declared in
;  Anvil/Hal/hal.pbi, implemented for the Pi 4 in RaspberryPi4/Board/hw_boot.pi4)
;  which drops to EL1 and branches into the kernel. A board that cannot reach
;  EL1 declares #CAP_BOOT_EL1 = 0 and both commands refuse cleanly through
;  RequireCap - the same degrade the `gpio` demonstrator shows.
;
;  THE PRIME RULE APPLIES HERE MORE THAN ANYWHERE. "Loud errors beat silent
;  wrong answers" (RULES.md rule 3), and the loudest possible wrong answer is
;  jumping into memory that is not a kernel. So every path that would hand the
;  machine over is guarded first: the load must have arrived cleanly, the
;  arm64 Image magic must be right, a device tree must exist and must itself
;  begin with the FDT magic. Any of those failing prints a whole sentence and
;  boots nothing.
;
;  SOURCES. The arm64 Image header layout and magic are U-Boot's, read from
;  RaspberryPi4/Reference/v2025.01_image.c (booti_setup, struct Image_header).
;  The minimum-viable path - load Image, keep the firmware's DTB, set x0, drop
;  to EL1, branch - is the one the inventory prescribes (Raspberry Pi 4/U-Boot
;  command and feature inventory.md S2.4, S3.5). The EL2->EL1 register set-up
;  and its citations live with the board backend, RaspberryPi4/Board/hw_boot.pi4.
;
;  COMPILE-VERIFIED ONLY. No silicon is on this bench and no emulator models
;  the EL2->EL1 handoff, so a real Linux boot has never run here. The header
;  parsing and every refusal path are ordinary code and could be exercised;
;  the handoff itself is owed a Pi 4.
; ======================================================================

; The arm64 Image magic - "ARM\x64", i.e. bytes 41 52 4D 64, which read as
; the little-endian word $644D5241, at offset 56 (v2025.01_image.c:15,42).
#ARM64_IMAGE_MAGIC = $644D5241

; The flat-device-tree magic, 0xd00dfeed, stored BIG-endian at the DTB.
#FDT_MAGIC = $D00DFEED

; Legacy U-Boot uImage header (v2025.01, include/image.h): a 64-byte header
; whose first word is this magic, big-endian.
#UIMAGE_MAGIC = $27051956
; The one os/arch/type/comp combination this monitor will boot: an
; uncompressed arm64 Linux kernel (image.h IH_* enumerations).
#IH_OS_LINUX    = 5
#IH_ARCH_ARM64  = 22
#IH_TYPE_KERNEL = 2
#IH_COMP_NONE   = 0

; ----------------------------------------------------------------------
;  Little-endian multi-byte reads, assembled a byte at a time with PeekA so
;  an unaligned image base cannot fault - the same reasoning DumpMem gives
;  (Anvil/Core/memcmd.pbi): a wide Peek of an unaligned address is an
;  alignment abort with no console message, and the image base is whatever
;  the operator typed.
; ----------------------------------------------------------------------
Procedure.i BootReadLE32(a.i)
  ProcedureReturn PeekA(a) | (PeekA(a + 1) << 8) | (PeekA(a + 2) << 16) | (PeekA(a + 3) << 24)
EndProcedure

Procedure.i BootReadLE64(a.i)
  ProcedureReturn BootReadLE32(a) | (BootReadLE32(a + 4) << 32)
EndProcedure

; ----------------------------------------------------------------------
;  BootResolveDtb - pick the device tree and prove it is one.
;
;  Explicit fdt argument wins; otherwise the firmware's DTB that Anvil holds
;  (HwFirmwareDtb -> gBootDtb, captured from x0 at entry). Returns the DTB
;  address, or 0 after printing a whole-sentence refusal - never a silent 0.
; ----------------------------------------------------------------------
Procedure.i BootResolveDtb(haveFdt.i, fdtArg.i)
  Define dtb.i
  Define fdtmagic.i
  If haveFdt <> 0
    dtb = fdtArg
  Else
    dtb = HwFirmwareDtb()
  EndIf
  If dtb = 0
    PrintN("!! no device tree is available: this board handed Anvil no firmware")
    PrintN("   DTB and none was given, so there is nothing to pass the kernel in")
    PrintN("   x0. An arm64 kernel needs a device tree, so nothing was booted.")
    PrintN("   Give one as the third argument: booti <addr> - <fdt>.")
    ProcedureReturn 0
  EndIf
  ; The DTB must start with the FDT magic (big-endian d00dfeed). This catches
  ; a stale or wrong pointer before it is handed to the kernel.
  fdtmagic = (PeekA(dtb) << 24) | (PeekA(dtb + 1) << 16) | (PeekA(dtb + 2) << 8) | PeekA(dtb + 3)
  If fdtmagic <> #FDT_MAGIC
    Print("!! the device tree at ")
    PutAddr(dtb)
    PrintN(" does not begin with the flat-device-tree")
    PrintN("   magic (d00dfeed), so it is not a DTB. Nothing was booted rather than")
    PrintN("   handing the kernel a pointer to something that is not a device tree.")
    ProcedureReturn 0
  EndIf
  ProcedureReturn dtb
EndProcedure

; ----------------------------------------------------------------------
;  BootDirty - the same guard `run` uses: never boot a half-arrived image.
;  Returns 1 (and prints) when the last load was dirty, 0 when it is clean.
; ----------------------------------------------------------------------
Procedure.i BootDirty()
  If gBad > 0 Or gFail <> 0
    PrintN("!! the last image did not arrive cleanly, so nothing was booted. What")
    PrintN("   is in memory is part of a program and part of whatever was there")
    PrintN("   before, and booting that is how a board wedges with no explanation.")
    PrintN("   Load the image again, all the way through, first.")
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; gBootAddrOk - set by BootDefaultAddr: 1 if the address is usable, 0 if the
; number was too long (in which case BootDefaultAddr has already printed and
; the caller must return). A global rather than a by-reference argument
; because this language has no .Integer structure pointer; gParseOver next to
; it is a global for the same reason.
Global gBootAddrOk.i

; ----------------------------------------------------------------------
;  BootDefaultAddr - the address argument, or its default: the entry point of
;  the last load if we have one, else the base of the low payload window -
;  exactly what `run` defaults to (Anvil/Core/memcmd.pbi CmdGo). Returns the
;  address; sets gBootAddrOk to 0 (and prints) only on a too-long number.
; ----------------------------------------------------------------------
Procedure.i BootDefaultAddr()
  Define a.i
  gBootAddrOk = 1
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was booted.")
      gBootAddrOk = 0
      ProcedureReturn 0
    EndIf
    If gHaveEntry <> 0
      a = gEntry
    Else
      ; THE BOARD'S STAGING ADDRESS, NOT #PAY0_LO - 2026-09-08. It is the
      ; same address on this board today; what changed is that it FOLLOWS
      ; THE MONITOR'S SIZE instead of being a constant, so a default that
      ; read the constant would one day name an address inside the
      ; monitor. HwStageAddr() is the one place that answer is worked out.
      a = HwStageAddr()
    EndIf
  EndIf
  ProcedureReturn a
EndProcedure

; ======================================================================
;  booti - boot an arm64 Linux `Image`.
;
;    booti [addr [initrd [fdt]]]
;
;  addr    where the Image is, hex. Default: last load's entry, else the low
;          payload window (like run).
;  initrd  an initrd address, hex, or - to skip it. ACCEPTED for U-Boot
;          compatibility but NOT used yet: this path passes no initrd to the
;          kernel. Said out loud below when one is given.
;  fdt     an explicit device-tree address, hex. Default: the firmware's DTB
;          that Anvil holds. To give an fdt without an initrd, use a dash:
;          booti <addr> - <fdt>  (U-Boot's own convention).
; ======================================================================
Procedure CmdBooti()
  Define addr.i
  Define dtb.i
  Define fdtArg.i
  Define haveFdt.i
  Define haveInitrd.i
  Define magic.i
  Define imgsize.i
  Define textoff.i

  ; the dirty-load guard, first.
  If BootDirty() <> 0
    ProcedureReturn
  EndIf

  ; the capability gate (Anvil/Hal/hal.pbi). #CAP_BOOT_EL1 is 1 on the Pi 4;
  ; a board that cannot reach EL1 declares 0 and this refuses cleanly.
  If RequireCap(#CAP_BOOT_EL1, "booti", "it has no way to hand a kernel off at EL1") = 0
    ProcedureReturn
  EndIf

  ; --- the address argument (or its default) ---
  addr = BootDefaultAddr()
  If gBootAddrOk = 0
    ProcedureReturn
  EndIf

  ; --- initrd slot (arg 2): a dash skips it, an address is consumed and
  ;     noted as unused, nothing leaves it for the fdt slot. ---
  haveInitrd = 0
  SkipSpace()
  If gLine[gPos] = 45                       ; 45 = '-'
    gPos = gPos + 1
  Else
    ParseHex()
    If gParseOk <> 0
      haveInitrd = 1
    EndIf
  EndIf

  ; --- fdt slot (arg 3) ---
  fdtArg = ParseHex()
  haveFdt = gParseOk

  ; --- validate the arm64 Image header (v2025.01_image.c) ---
  magic = BootReadLE32(addr + 56)
  If magic <> #ARM64_IMAGE_MAGIC
    Print("!! there is no arm64 Linux Image at ")
    PutAddr(addr)
    PrintN(": the four bytes at offset 56")
    PrintN("   are not the Image magic (they should read 41 52 4D 64, 'ARM' then")
    PrintN("   0x64). Nothing was booted - jumping into memory that is not a kernel")
    PrintN("   is the one thing this command must never do. Load an Image first, or")
    PrintN("   give the right address. For a raw payload use run, not booti.")
    ProcedureReturn
  EndIf

  ; image_size @16, text_offset @8 (v2025.01_image.c:18-28). A zero image_size
  ; is an older image whose size field is absent - assume 16 MiB and the fixed
  ; 0x80000 text_offset (image.c:52-55).
  imgsize = BootReadLE64(addr + 16)
  textoff = BootReadLE64(addr + 8)
  If imgsize = 0
    imgsize = 16 * 1024 * 1024
    textoff = $80000
  EndIf

  ; --- the device tree, proven to be one ---
  dtb = BootResolveDtb(haveFdt, fdtArg)
  If dtb = 0
    ProcedureReturn
  EndIf

  ; --- what we are about to do, in full ---
  PrintN("Booting an arm64 Linux Image.")
  Print("  Image at    ")
  PutAddr(addr)
  PrintNl()
  Print("  image size  ")
  PutAddr(imgsize)
  PrintN(" bytes")
  Print("  text offset ")
  PutAddr(textoff)
  PrintNl()
  Print("  device tree ")
  PutAddr(dtb)
  If haveFdt = 0
    PrintN(" (the firmware's, in x0)")
  Else
    PrintN(" (given, in x0)")
  EndIf
  Print("  entry       ")
  PutAddr(addr)
  PrintNl()
  If haveInitrd <> 0
    PrintN("  note: an initrd address was given but this monitor does not pass an")
    PrintN("        initrd to the kernel yet, so it was ignored.")
  EndIf

  ; The arm64 protocol wants the Image at a 2 MiB-aligned base; we boot in
  ; place (no relocation), so `addr` is that base. Warn, do not refuse - the
  ; address is the operator's explicit choice, but a misaligned base is the
  ; usual reason a kernel dies silently on entry.
  If (addr & $1FFFFF) <> 0
    PrintN("  !! this address is not 2 MiB-aligned. The arm64 boot protocol")
    PrintN("     requires a 2 MiB-aligned Image base; booting here anyway because")
    PrintN("     you asked, but a misaligned kernel usually just dies on entry.")
  EndIf

  PrintN("Dropping from EL2 to EL1 with x0 = the device tree. Control leaves the")
  PrintN("monitor now and does not come back - a booted kernel never returns.")

  ; hand the machine over - does not return.
  HwBootToEl1(addr, dtb)

  ; Reached only if the seam refused (it should not). Say so rather than
  ; falling through to the prompt as if nothing happened.
  PrintN("!! the EL1 handoff returned, which it never should. Nothing was booted.")
EndProcedure

; ======================================================================
;  bootm - boot a container image from memory.
;
;    bootm [addr [initrd [fdt]]]
;
;  WHAT IS SUPPORTED, AND WHAT IS REFUSED - honestly, because a container
;  format silently mis-handled is exactly the trap rule 3 exists to stop:
;
;    * A legacy U-Boot uImage (magic 0x27051956) holding a SINGLE,
;      UNCOMPRESSED, arm64 Linux kernel: BOOTED, via the same EL1 handoff as
;      booti. Any other os/arch/type, or any compression, is REFUSED by name.
;    * A FIT / .itb (flat-image-tree, magic 0xd00dfeed): REFUSED loudly.
;      Anvil has no device-tree parser, so it cannot read a FIT's components,
;      configurations or hashes (inventory S3.5, S5.6). Unpack and use booti.
;    * A bare arm64 Image (not a container): the operator is pointed at booti.
;    * Anything else: refused as unrecognised.
;
;  This is the honest subset the task allows: detect the format, boot the
;  single-kernel case, refuse the rest LOUDLY - never silently mis-handle.
;  The multi-component FIT path is deliberately NOT built; it is N/A for a
;  board that would only ever produce such a file for itself (inventory S3.5).
; ======================================================================

; ----------------------------------------------------------------------
;  BootLegacyUimage - the single-kernel uImage case. addr points at the
;  64-byte legacy header (v2025.01 include/image.h, image_header):
;    ih_magic @0  ih_hcrc @4  ih_time @8  ih_size @12  ih_load @16
;    ih_ep @20    ih_dcrc @24 ih_os @28   ih_arch @29  ih_type @30
;    ih_comp @31  ih_name @32 (32 bytes).  All multi-byte fields big-endian.
;
;  NOT CHECKED: ih_hcrc / ih_dcrc. This monitor's own `b`/`wb` transfer
;  already CRC32s the whole image on the way in (gBad/gFail, guarded above),
;  so the bytes in memory are the bytes that were sent; a second CRC of the
;  same bytes against a field inside them proves less than that already does.
;  Said here rather than hidden.
; ----------------------------------------------------------------------
Procedure BootLegacyUimage(addr.i)
  Define os.i
  Define arch.i
  Define typ.i
  Define comp.i
  Define load.i
  Define ep.i
  Define size.i
  Define payload.i
  Define dtb.i
  Define fdtArg.i
  Define haveFdt.i

  os   = PeekA(addr + 28)
  arch = PeekA(addr + 29)
  typ  = PeekA(addr + 30)
  comp = PeekA(addr + 31)
  ; big-endian 32-bit fields
  size = (PeekA(addr + 12) << 24) | (PeekA(addr + 13) << 16) | (PeekA(addr + 14) << 8) | PeekA(addr + 15)
  load = (PeekA(addr + 16) << 24) | (PeekA(addr + 17) << 16) | (PeekA(addr + 18) << 8) | PeekA(addr + 19)
  ep   = (PeekA(addr + 20) << 24) | (PeekA(addr + 21) << 16) | (PeekA(addr + 22) << 8) | PeekA(addr + 23)

  ; --- only the single uncompressed arm64 Linux kernel case is supported ---
  If arch <> #IH_ARCH_ARM64
    PrintN("!! this uImage is not for arm64, so it was not booted. Anvil boots only")
    PrintN("   an arm64 kernel here.")
    ProcedureReturn
  EndIf
  If os <> #IH_OS_LINUX
    PrintN("!! this uImage is not a Linux image, so it was not booted. Anvil's")
    PrintN("   bootm handles a single Linux kernel only.")
    ProcedureReturn
  EndIf
  If typ <> #IH_TYPE_KERNEL
    PrintN("!! this uImage is not a single kernel (it is a multi-file, ramdisk, or")
    PrintN("   other type), so it was not booted. bootm here handles one kernel")
    PrintN("   only; unpack it or use booti on the Image.")
    ProcedureReturn
  EndIf
  If comp <> #IH_COMP_NONE
    PrintN("!! this uImage is compressed, and Anvil does not decompress. It was not")
    PrintN("   booted. Provide an uncompressed kernel, or decompress it and use booti.")
    ProcedureReturn
  EndIf

  ; The kernel data follows the 64-byte header. We boot in place, so the data
  ; must already sit where the header says it runs (ih_load). Relocation is
  ; not implemented; refuse loudly with the numbers rather than copying.
  payload = addr + 64
  If load <> payload
    Print("!! this uImage wants its kernel at ")
    PutAddr(load)
    PrintN(", but its data is at")
    Print("   ")
    PutAddr(payload)
    PrintN(" (right after the 64-byte header). Anvil boots a uImage")
    PrintN("   in place and does not relocate, so load it so the header sits 64")
    Print("   bytes before ")
    PutAddr(load)
    Print(" (at ")
    PutAddr(load - 64)
    PrintN("), or use booti on the raw Image.")
    ProcedureReturn
  EndIf

  ; --- device tree: same rules as booti (fdt arg, else firmware DTB) ---
  fdtArg = ParseHex()
  haveFdt = gParseOk
  dtb = BootResolveDtb(haveFdt, fdtArg)
  If dtb = 0
    ProcedureReturn
  EndIf

  PrintN("Booting a legacy uImage (single uncompressed arm64 Linux kernel).")
  Print("  kernel at   ")
  PutAddr(payload)
  PrintNl()
  Print("  data size   ")
  PutAddr(size)
  PrintN(" bytes")
  Print("  device tree ")
  PutAddr(dtb)
  PrintNl()
  Print("  entry       ")
  PutAddr(ep)
  PrintNl()
  PrintN("Dropping from EL2 to EL1 with x0 = the device tree. Control leaves the")
  PrintN("monitor now and does not come back.")

  HwBootToEl1(ep, dtb)
  PrintN("!! the EL1 handoff returned, which it never should. Nothing was booted.")
EndProcedure

Procedure CmdBootm()
  Define addr.i
  Define be.i

  If BootDirty() <> 0
    ProcedureReturn
  EndIf
  If RequireCap(#CAP_BOOT_EL1, "bootm", "it has no way to hand a kernel off at EL1") = 0
    ProcedureReturn
  EndIf

  addr = BootDefaultAddr()
  If gBootAddrOk = 0
    ProcedureReturn
  EndIf

  ; identify the container by its first big-endian word.
  be = (PeekA(addr) << 24) | (PeekA(addr + 1) << 16) | (PeekA(addr + 2) << 8) | PeekA(addr + 3)

  If be = #FDT_MAGIC
    PrintN("!! that is a FIT (flat-image-tree, .itb) container. Anvil has no")
    PrintN("   device-tree parser, so it cannot read a FIT's kernel, device tree,")
    PrintN("   configurations or hashes. Unpack the kernel Image from it and boot")
    PrintN("   that with booti instead. bootm here handles only a legacy uImage.")
    ProcedureReturn
  EndIf

  If be = #UIMAGE_MAGIC
    BootLegacyUimage(addr)
    ProcedureReturn
  EndIf

  ; a bare arm64 Image is not a bootm container - point at booti.
  If BootReadLE32(addr + 56) = #ARM64_IMAGE_MAGIC
    Print("!! that is a bare arm64 Image, not a bootm container. Boot it with")
    Print("   booti ")
    PutAddr(addr)
    PrintN(" instead.")
    ProcedureReturn
  EndIf

  Print("!! the bytes at ")
  PutAddr(addr)
  PrintN(" are not a boot container this monitor")
  PrintN("   recognises. bootm handles a legacy uImage (magic 27051956); a FIT")
  PrintN("   (d00dfeed) is refused because there is no device-tree parser; and a")
  PrintN("   bare arm64 Image is booted with booti, not bootm. Nothing was booted.")
EndProcedure
