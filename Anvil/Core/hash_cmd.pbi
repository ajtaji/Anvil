
; ======================================================================
;  sha1sum / sha256sum  -  a cryptographic checksum over a range
; ======================================================================
;  U-Boot's hash family (cmd/hash.c, table entries sha1sum / sha256sum
;  gated by CONFIG_SHA1SUM / CONFIG_SHA256SUM). Anvil already has crc32,
;  which proves a transfer against tools/anvil.py; these prove a range
;  against ANY tool - sha1sum and sha256sum on a PC are on every bench -
;  and a SHA is what a published image's checksum actually is, so this is
;  how you check that the bytes on the stick are the bytes upstream
;  published, not merely the bytes the wire delivered.
;
;  BOTH ALGORITHMS ALREADY EXIST, verified against silicon, in
;  RaspberryPi4/Lib/sha1.pi4 and Anvil/Core/sha256.pbi, with the
;  same streaming shape crc32 uses: Begin / Update(src, len) / End(dst).
;  This file is the console wiring over them and holds no cryptography of
;  its own - the "documented once" rule the 2.0 header states.
;
;  IT FOLLOWS crc32'S RULINGS, because it is the same job with a
;  different function underneath:
;
;    * NO AddBase. do_mem_crc does not add base_address and neither does
;      the hash family; said out loud when a base is set, because it is
;      the exception.
;    * NO CLAMP but the #LEN_MAX arithmetic guard - a whole boot image is
;      the point, and #LEN_MAX only stops the address sum from wrapping.
;    * ANY KEY STOPS IT and a stopped one prints NO DIGEST. A hash of
;      part of a range is a plausible-looking value that is wrong, which
;      is the one failure this project refuses hardest.
;    * the digest is LOWERCASE hex, because that is what sha1sum and
;      sha256sum print on every other machine and a checksum you have to
;      case-fold before comparing is a checksum with a trap in it.
; ======================================================================

; The command name, printed directly. A pointer to a string LITERAL is
; not something `@` can take in this language (it wants a variable, field
; or array element), so the name is printed with Print rather than held
; as a pointer and passed to UartWriteStr.
Procedure PutAlgoName(algo.i)
  If algo = 2
    Print("sha256sum")
  Else
    Print("sha1sum")
  EndIf
EndProcedure

; PutHexLower2 - one digest byte in LOWERCASE hex - used to live here and
; now lives in Anvil/Core/format.pbi beside PutHex2, which is the same job
; in the other case. It moved because Anvil/Core/pmfboot.pbi prints a
; SHA-256 too, when it verifies a payload container, and a board that
; builds the bootloader without building this command would otherwise be
; missing the one procedure that prints a digest byte.

; algo: 1 = SHA-1 (20-byte digest), 2 = SHA-256 (32-byte digest).
Procedure HashRange(algo.i)
  Define a.i
  Define n.i
  Define done.i
  Define chunk.i
  Define dlen.i
  Define i.i

  If algo = 2
    dlen = 32
  Else
    dlen = 20
  EndIf

  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was computed.")
      ProcedureReturn
    EndIf
    PutAlgoName(algo)
    PrintN(" <address> <count>")
    PrintN("  a cryptographic checksum of a block of memory. Both hex, count in")
    PrintN("  bytes. There is no size limit - a whole boot image is what it is for.")
    PrintN("  Any keystroke stops it, and a stopped one prints no digest at all.")
    PrintN("  The digest is lowercase hex, the same as the sha1sum / sha256sum")
    PrintN("  tools on any other machine, so the two can be compared directly.")
    ProcedureReturn
  EndIf
  n = ParseHex()
  If gParseOk = 0
    PrintN("!! a byte count is required, in hex.")
    ProcedureReturn
  EndIf
  If n <= 0
    PrintN("!! a count of zero bytes has no checksum worth printing.")
    PrintN("   Give a byte count in hex.")
    ProcedureReturn
  EndIf
  If n > #LEN_MAX
    PrintN("!! that is more than a gigabyte, which is more DRAM than the address")
    PrintN("   arithmetic here will stay honest over. Nothing was computed.")
    ProcedureReturn
  EndIf

  ; U-Boot's hash family, like crc32, takes an optional third argument
  ; that stores the digest in memory. Refused by name for the same reason
  ; crc32's is: the store format lives in lib/hash.c, which is not in this
  ; repository, and a guessed-at compatibility is worse than none.
  SkipSpace()
  If gLine[gPos] <> 0
    PutAlgoName(algo)
    PrintN(" here takes exactly two arguments, an address and a count.")
    PrintN("   U-Boot's has a third that stores the digest in memory; it is not")
    PrintN("   implemented, because the byte order it stores is decided in")
    PrintN("   lib/hash.c, which is not in this repository. Nothing was computed.")
    ProcedureReturn
  EndIf

  ; NO AddBase - the hash family does not add base_address, the same as
  ; crc32. Said out loud when a base is set, because it is the exception.
  If gBase <> 0
    PutAlgoName(algo)
    Print(" does NOT add the default address ")
    PutAddr(gBase)
    PrintNl()
    PrintN("  - the address used is the one you typed.")
  EndIf

  ; THE BOARD IS ASKED, before the "... over N bytes ..." line, so a
  ; refused range never announces a hash it did not begin. The command
  ; word is passed as a literal per algorithm rather than through
  ; PutAlgoName, because AddrAllowed takes a POINTER to print with
  ; UartWriteStr and PutAlgoName is a printer, not a name.
  If algo = 2
    If AddrAllowed(a, a + n - 1, 0, "sha256sum", "computed") = 0
      ProcedureReturn
    EndIf
  Else
    If AddrAllowed(a, a + n - 1, 0, "sha1sum", "computed") = 0
      ProcedureReturn
    EndIf
  EndIf

  PutAlgoName(algo)
  Print(" over ")
  PrintDec(n)
  Print(" bytes, ")
  PutAddr(a)
  Print(" .. ")
  PutAddr(a + n - 1)
  PrintN(" ...")
  UartDrain()

  If algo = 2
    Sha256Begin()
  Else
    Sha1Begin()
  EndIf

  done = 0
  While done < n
    If OutBreak() <> 0
      PrintN("   stopped part way, so NO DIGEST IS PRINTED. A hash of part of a")
      PrintN("   range looks exactly like a hash of all of it and is not one.")
      ProcedureReturn
    EndIf
    chunk = n - done
    If chunk > 65536
      chunk = 65536                ; 64 KiB between break checks, as crc32
    EndIf
    If algo = 2
      Sha256Update(a + done, chunk)
    Else
      Sha1Update(a + done, chunk)
    EndIf
    done = done + chunk
  Wend

  If algo = 2
    Sha256End(@gHashOut[0])
  Else
    Sha1End(@gHashOut[0])
  EndIf

  Print("The ")
  PutAlgoName(algo)
  Print(" is ")
  i = 0
  While i < dlen
    PutHexLower2(gHashOut[i] & $FF)
    i = i + 1
  Wend
  PrintNl()
  Print("  ")
  PutAlgoName(algo)
  PrintN(" of the same bytes on any other machine gives the same digest, so a")
  PrintN("  match proves this range is byte-for-byte what that machine has.")
EndProcedure

Procedure CmdSha1sum()
  HashRange(1)
EndProcedure

Procedure CmdSha256sum()
  HashRange(2)
EndProcedure
