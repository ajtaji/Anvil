
; ======================================================================
;  g - jump
; ======================================================================

Procedure CmdGo()
  Define a.i
  If gBad > 0 Or gFail <> 0
    PrintN("!! the last image did not arrive cleanly, so nothing was run. What is")
    PrintN("   in memory is part of a program and part of whatever was there")
    PrintN("   before, and jumping into that is how a board wedges with no")
    PrintN("   explanation. Load the image again, all the way through, first.")
    ProcedureReturn
  EndIf
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was run.")
      ProcedureReturn
    EndIf
    ; No address given: the entry point of the last load if we have one,
    ; else the address this board stages files at, which is the base of
    ; the low payload window and moves with the monitor's size.
    If gHaveEntry <> 0
      a = gEntry
    Else
      a = HwStageAddr()
    EndIf
  EndIf
  RunAt(a)
EndProcedure

; ======================================================================
;  m - memory display     w - memory write
; ======================================================================

; ======================================================================
;  AddBase - U-Boot's base_address, applied and ANNOUNCED.
;
;  U-Boot adds base_address to an address argument in silence
;  (cmd_mem.c:94, :149, :263, :266, :326, :329). That is fine in a
;  loader whose every command is one line of output anyway, and it is
;  not fine here: the whole complaint that produced the 2026-08-26 style
;  directive was commands that did something other than what the words
;  said and did not mention it. So the addition is printed, every time
;  it actually happens.
;
;  WHEN gBase IS ZERO - which is where it starts, and where it stays
;  unless somebody types `base` - this prints nothing and returns the
;  address unchanged, so no existing behaviour moves.
; ======================================================================
Procedure.i AddBase(a.i)
  If gBase = 0
    ProcedureReturn a
  EndIf
  Print("  the default address ")
  PutAddr(gBase)
  Print(" is being added, so ")
  PutAddr(a)
  Print(" means ")
  PutAddr(a + gBase)
  PrintNl()
  ProcedureReturn a + gBase
EndProcedure

; ======================================================================
;  THE WIDTH TABLE - what .b / .w / .l does, written down ONCE.
;  Forum 585.
; ======================================================================
;  585 was a help sentence that was wrong about this command. The summary
;  paragraph in `help` said the width suffix "changes what the count
;  counts (bytes, halfwords or words)" and that "every command prints the
;  byte count it worked out". Neither was true of the memory dump: it
;  counts BYTES whichever width you pick - only the grouping changes -
;  and it printed no total at all. Someone typing `md.l <addr> 100`
;  expecting a kilobyte got 256 bytes and no line telling them so.
;
;  The reference contradicted ITSELF, which is the tell: the per-command
;  entry for the dump was already correct and the summary above it was
;  not. Two English sentences describing one rule is one sentence too
;  many, and the wrong one is always the one nobody re-reads when the
;  behaviour changes.
;
;  SO THE RULE IS DATA NOW, AND BOTH READERS READ THE DATA. This table is
;  the only statement of it. The COMMANDS take their default object size
;  from WtDefSize(); HELP generates its sentence by walking the same rows
;  (PutWidthRule() in Anvil/Core/help.pbi). Neither can drift from the
;  other, because there is nothing to drift from - and
;  tools/a64/a64_anvil_check.py executes both halves and diffs them, so a
;  row that says one thing while the command does another is red.
;
;  THE TWO KINDS OF SUFFIX, AND WHY THEY ARE BOTH RIGHT
;  ----------------------------------------------------
;  WtScales() = 0  the suffix only GROUPS. The dump shows the same
;                  sixteen bytes a line as 8, 16 or 32-bit values; the
;                  count stays in bytes. Two counts that meant different
;                  things in one monitor would be the trap, and `memory
;                  <addr> <count>` has counted bytes since it existed.
;  WtScales() = 1  the suffix SIZES THE OBJECT the count counts, which is
;                  U-Boot's cmd_get_data_size(argv[0], N) read off the
;                  command word (v2025.01_cmd_mem.c:143 mw, :256 cmp,
;                  :322 cp). bytes = count * size.
;
;  WtDefSize() is what a BARE command uses, and every one of them
;  reproduces byte-for-byte what that command did before the suffix
;  existed: a bare fill counts 32-bit words (mw's default size 4), a bare
;  copy and compare count bytes (Anvil's long-standing choice), mm and nm
;  step a word, and the dump groups by one.
;
;  ADDING A COMMAND: add a row, raise #WT_N, and call WtDefSize() from
;  the command. The help sentence picks it up with no second edit - that
;  is the whole reason this is a table and not six constants.
; ======================================================================
#WT_MD      = 0
#WT_FILL    = 1
#WT_COPY    = 2
#WT_COMPARE = 3
#WT_MM      = 4
#WT_NM      = 5
#WT_N       = 6

Procedure.i WtName(i.i)
  ; The command word as the operator types it. `md` and not `memory`:
  ; the suffix is written on the U-Boot spelling in every example, in
  ; U-Boot's own documentation and in this monitor's help.
  If i = #WT_MD
    ProcedureReturn "md"
  ElseIf i = #WT_FILL
    ProcedureReturn "fill"
  ElseIf i = #WT_COPY
    ProcedureReturn "copy"
  ElseIf i = #WT_COMPARE
    ProcedureReturn "compare"
  ElseIf i = #WT_MM
    ProcedureReturn "mm"
  ElseIf i = #WT_NM
    ProcedureReturn "nm"
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i WtDefSize(i.i)
  ; The object size a BARE command uses, in bytes.
  If i = #WT_MD
    ProcedureReturn 1              ; group one byte at a time
  ElseIf i = #WT_FILL
    ProcedureReturn 4              ; mw's default size 4, cmd_mem.c:143,:162
  ElseIf i = #WT_COPY
    ProcedureReturn 1              ; bytes - see the memcmd header
  ElseIf i = #WT_COMPARE
    ProcedureReturn 1              ; bytes - see the memcmd header
  ElseIf i = #WT_MM
    ProcedureReturn 4              ; U-Boot's default, cmd_mem.c:1170
  ElseIf i = #WT_NM
    ProcedureReturn 4
  EndIf
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  MemSize(defSize) - the object size THIS command line asked for.
;
;  The width suffix if one was given (gMemWidth, set by the SUFFIX block
;  in the main loop and reset every command), otherwise the default the
;  caller passes - which every caller takes from WtDefSize() above, so
;  the default is written down once and help reads the same number.
; ----------------------------------------------------------------------
Procedure.i MemSize(defSize.i)
  If gMemWidth = 1 Or gMemWidth = 2 Or gMemWidth = 4
    ProcedureReturn gMemWidth
  EndIf
  ProcedureReturn defSize
EndProcedure

Procedure.i WtScales(i.i)
  ; 1 the suffix scales the COUNT, 0 it only regroups what is shown.
  ; The dump is the only 0 in the table, and it is the row 585 was about.
  If i = #WT_MD
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  DumpMem - the hex+ASCII dump, grouped by 1, 2 or 4 bytes.
;
;  WIDTH is U-Boot's .b / .w / .l for md (v2025.01_cmd_mem.c:66-115,
;  table :1313-1317). 1 groups the sixteen bytes of a line one at a time,
;  which is what this monitor has ALWAYS done and is still the default; 2
;  groups them as eight 16-bit values; 4 as four 32-bit values. The count
;  n is in BYTES in every case - see the note on gMemWidth in state.pi4
;  and the memory family's header below - so a line is always sixteen
;  bytes wide and only the grouping of them changes.
;
;  VALUES ARE LITTLE-ENDIAN, assembled a byte at a time rather than read
;  with PeekU/PeekN, because md must be able to look at an unaligned
;  device register block and a wide Peek of an unaligned address is an
;  alignment fault with no console message - the same trap `write`
;  guards against. Byte assembly reads the same little-endian value the
;  ARM would at an aligned address and simply cannot fault.
; ----------------------------------------------------------------------
;
;  IT RETURNS HOW MANY BYTES IT ACTUALLY PRINTED, which is not always n:
;  a keystroke ends it at a row boundary. The caller prints the byte
;  total (forum 585) and a total that said n after a stopped dump would
;  be a lie of exactly the kind the OutBreak message exists to prevent.
; ----------------------------------------------------------------------
Procedure.i DumpMem(a.i, n.i, width.i)
  Define i.i
  Define j.i
  Define k.i
  Define row.i
  Define b.i
  Define wide.i
  Define v.i
  Define ok.i
  If width <> 2 And width <> 4
    width = 1                     ; 0 (no suffix) and anything odd is byte
  EndIf
  ; THE ADDRESS COLUMN WIDTH IS DECIDED ONCE, for the whole dump, from
  ; its highest address - not per line. Deciding per line would make the
  ; columns jump by eight characters in the middle of a dump that
  ; happens to cross $100000000, and a dump you cannot read down is
  ; worse than one that is eight characters wider than it needs to be.
  wide = 8
  If a < 0 Or (a + n - 1) > $FFFFFFFF
    wide = 16
  EndIf
  i = 0
  While i < n
    ; ONE CHECK PER LINE. See STOPPING A LONG PRINT. The check goes at
    ; the TOP of the line, not the bottom, so an abort can never leave
    ; half a row of hex on the wire or half a row of glyphs on the
    ; screen - the console's cursor is at column 0 here and stays there.
    If OutBreak() <> 0
      ProcedureReturn i            ; the whole rows that did print
    EndIf
    row = n - i
    If row > 16
      row = 16
    EndIf
    PutHexN(a + i, wide)
    Print(": ")
    ; The hex area, in items of `width` bytes across the sixteen columns.
    j = 0
    While j < 16
      ok = 1
      k = 0
      While k < width
        If (j + k) >= row
          ok = 0
        EndIf
        k = k + 1
      Wend
      If ok <> 0
        ; Little-endian: the byte at the lowest address is the low byte,
        ; so it prints RIGHTMOST, which is how U-Boot and every hex tool
        ; show a word.
        v = 0
        k = width - 1
        While k >= 0
          v = (v << 8) | PeekA(a + i + j + k)
          k = k - 1
        Wend
        PutHexN(v, width * 2)
      Else
        ; Missing or partial item at the tail of a short last line.
        k = 0
        While k < width
          Print("  ")
          k = k + 1
        Wend
      EndIf
      UartWrite(32)
      j = j + width
    Wend
    UartWrite(124)
    j = 0
    While j < row
      b = PeekA(a + i + j)
      If b < 32 Or b > 126
        b = 46
      EndIf
      UartWrite(b)
      j = j + 1
    Wend
    UartWrite(124)
    PrintNl()
    i = i + 16
  Wend
  ProcedureReturn n
EndProcedure

Procedure CmdMem()
  Define a.i
  Define n.i
  Define width.i
  Define got.i
  ; THE WIDTH SUFFIX, off the command word. gMemWidth was set by the main
  ; loop's SUFFIX block when the word was md.b / md.w / md.l (or the same
  ; on memory / dump / m), 0 when there was none. MemSize() falls back to
  ; this command's own row in the width table (#WT_MD), which is 1 - byte
  ; grouping, what this command has always done - so a bare md is
  ; unchanged and the default is stated in ONE place that help reads too.
  width = MemSize(WtDefSize(#WT_MD))
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was dumped.")
    Else
      PrintN("!! memory needs an address to start at, in hexadecimal, and it is")
      PrintN("   missing or is not a hex number. Nothing was dumped.")
      PrintN("   memory <address> <count>, both hex, and the count is in bytes.")
      PrintN("   Leave the count out and you get 64 bytes.")
      PrintN("   md.b, md.w and md.l group the SAME bytes as 8, 16 or 32-bit")
      PrintN("   values; the count is still bytes whichever you pick.")
    EndIf
    ProcedureReturn
  EndIf
  n = ParseHex()
  If gParseOk = 0
    n = 64
  EndIf
  If n <= 0
    ; NOT SILENT. "memory 400000 0" used to run DumpMem with a count of
    ; zero, whose loop body never executes, and the command returned to
    ; the prompt having printed nothing whatsoever. A command that says
    ; nothing is indistinguishable from a monitor that has crashed.
    PrintN("!! a count of zero bytes dumps nothing, so nothing was dumped. Give a")
    PrintN("   count in hexadecimal bytes, or leave it out entirely and you get 64.")
    ProcedureReturn
  EndIf
  If n > 4096
    ; SAY THAT IT WAS CLAMPED. This used to clamp in silence, so asking
    ; for 10000 bytes gave you 4096 of them and a dump that looked whole.
    ; A short answer that looks complete is the failure this project
    ; refuses everywhere else.
    Print("Only the first 4096 bytes are dumped, so the ")
    PutHex8(n)
    PrintN(" bytes you asked")
    PrintN("for have been cut down to that. Dump the rest in further pieces.")
    n = 4096
  EndIf
  ; U-Boot's md does `addr += base_address` (cmd_mem.c:94) and so does
  ; this. With no `base` command ever typed gBase is 0 and this is a
  ; no-op that prints nothing.
  a = AddBase(a)
  ; ==================================================================
  ;  NO SIZE WARNING, AND NO AUTOMATIC "screen off". ARGUED, NOT
  ;  OVERLOOKED - it was asked for after the 2026-08-26 hang and the
  ;  answer is no, for three reasons.
  ;
  ;  FIRST, THE COST NO LONGER SCALES WITH THE DUMP. The screen console
  ;  is fed from an 8192-byte mirror ring and ScreenPump() now skips
  ;  everything it would only scroll away, so a 4096-byte dump and a
  ;  64-byte dump cost the SCREEN the same: at most one clear and one
  ;  screenful. A threshold would be defending against a cost that is
  ;  no longer there, and a threshold that fires when nothing bad
  ;  happens is how people learn to ignore warnings.
  ;
  ;  SECOND, TURNING THE SCREEN OFF BY ITSELF IS A SILENT STATE CHANGE.
  ;  The operator would come back to a monitor whose screen stopped
  ;  working and no memory of having asked for that. The one thing this
  ;  project will not do is quietly change the answer; `screen off` is
  ;  a command and it stays one.
  ;
  ;  THIRD, THE HAZARD IS ALREADY CLOSED at the other end. Any byte on
  ;  the wire stops the print now - see STOPPING A LONG PRINT - so the
  ;  worst a surprising dump can do is waste a line of output and a
  ;  keystroke. That is a better guarantee than a warning, because it
  ;  covers the commands nobody thought to put a warning on.
  ;
  ;  The 4096-byte clamp above still stands. It is not a safety rail
  ;  against the console; it is what stops a mistyped count from
  ;  reading half of DRAM.
  ; ==================================================================
  ;
  ; m IS NOT WINDOW-CHECKED. It is read-only, and being able to point it
  ; at anything is most of its value - "m FE201000 20" reading the PL011
  ; block is how the mini-UART routing bug was cornered.
  ;
  ; IT IS BOARD-CHECKED, THOUGH, AND THAT IS NEW. The paragraph above
  ; used to end "reading an address with no device behind it can hang the
  ; bus; that is a real risk and it is accepted, because the alternative
  ; is a debugger that refuses to look at the thing you are debugging."
  ; The first half of that turned out to be an understatement on the
  ; second target - the access does not fault, it stalls the processor on
  ; the bus and the board has to be unplugged - and it happened to
  ; somebody, twice, from this exact command.
  ;
  ; The sentence is still right about the alternative, which is why the
  ; guard REFUSES rather than forbids: the board says what it knows, the
  ; refusal names the block, and `force` goes ahead anyway on a
  ; deliberate second line. What is gone is only the silence. See
  ; Anvil/Core/addrsafe.pbi.
  If AddrAllowed(a, a + n - 1, 0, "memory", "dumped") = 0
    ProcedureReturn
  EndIf
  got = DumpMem(a, n, width)

  ; ==================================================================
  ;  THE BYTE TOTAL.  Forum 585, the second half of it.
  ;
  ;  This command printed no total at all, while fill, copy and compare
  ;  all ended with "N words - M bytes". So the one command in the family
  ;  whose count does NOT follow the suffix was also the one that never
  ;  told you what it had actually done, and somebody typing `md.l <addr>
  ;  100` for a kilobyte got 256 bytes with nothing on the screen to
  ;  contradict them.
  ;
  ;  It says the GROUPING as well as the count, in the same line, because
  ;  those are the two things the suffix decides and printing one without
  ;  the other is how the misunderstanding survives.
  ;
  ;  `got`, NOT `n`. A keystroke ends a dump at a row boundary and
  ;  DumpMem returns how much really reached the console; a total that
  ;  said n after a stopped dump would be exactly the confident wrong
  ;  answer the stop message exists to prevent.
  ; ==================================================================
  If got <= 0
    ; Stopped before the first row printed. There is no range to name,
    ; and naming one would put a - 1 on the screen.
    Print("Dumped 0 bytes of the ")
    PrintDec(n)
    PrintN(" asked for, because a key was pressed first.")
    ProcedureReturn
  EndIf
  Print("Dumped ")
  PrintDec(got)
  Print(" bytes, ")
  PutAddr(a)
  Print(" .. ")
  PutAddr(a + got - 1)
  Print(", grouped as ")
  PrintDec(width * 8)
  PrintN("-bit values.")
  If got < n
    Print("  You asked for ")
    PrintDec(n)
    PrintN(" and this stopped early, so that is PART of the range.")
  EndIf
  PrintN("  The count is in bytes whichever grouping you choose; the suffix moves")
  PrintN("  the columns, not the amount. Type help for the whole rule.")
EndProcedure

Procedure CmdWrite()
  Define a.i
  Define v.i
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was written.")
    Else
      PrintN("!! write needs an address to write to, in hexadecimal, and it is")
      PrintN("   missing or is not a hex number. Nothing was written.")
      PrintN("   write <address> <value>, both hex. The value is one 32-bit word")
      PrintN("   and the address must be a multiple of four.")
    EndIf
    ProcedureReturn
  EndIf
  v = ParseHex()
  If gParseOk = 0
    PrintN("!! write needs a value as well as an address, and it is missing or is")
    PrintN("   not a hex number. Nothing was written - in particular the address")
    PrintN("   you gave has NOT been set to zero.")
    PrintN("   write <address> <value>, both hex. The value is one 32-bit word.")
    ProcedureReturn
  EndIf
  ; U-Boot's mw - the command this one is the single-word case of - does
  ; `addr += base_address` (cmd_mem.c:149). Same here, and announced.
  a = AddBase(a)
  If HitsMonitor(a, a + 3) <> 0
    Print("!! that address is inside the monitor itself, which lives at ")
    PutAddr(gMonHitLo)
    PrintNl()
    Print("   to ")
    PutAddr(gMonHitHi)
    PrintN(". Writing there would change the running monitor's")
    PrintN("   own code or data and take this prompt with it, so nothing was")
    PrintN("   written. Every other address on the board is allowed.")
    ProcedureReturn
  EndIf
  If (a & 3) <> 0
    ; Not pedantry. A 32-bit store to an unaligned address in a device
    ; aperture is an alignment fault, not a slow write, and the fault
    ; arrives with no console message.
    Print("!! ")
    PutAddr(a)
    PrintN(" is not a multiple of four, and a 32-bit write has to")
    PrintN("   be. This is not fussiness: an unaligned 32-bit store into a device")
    PrintN("   register block is an alignment fault, not a slow write, and it")
    PrintN("   arrives with no message at all. Nothing was written.")
    Print("   Round the address down to ")
    PutAddr(a - (a & 3))
    PrintN(" and try again.")
    ProcedureReturn
  EndIf
  ; AND THE BOARD IS ASKED, before the store and before the read-back.
  ; Both halves of this command touch the bus, so a block that cannot
  ; answer takes the machine down on either one.
  If AddrAllowed(a, a + 3, 1, "write", "written") = 0
    ProcedureReturn
  EndIf
  ; PokeN / PeekN, the UNSIGNED 32-bit pair. PokeL would store the same
  ; four bytes but PeekL would read them back SIGNED, so a register
  ; holding $80000000 would print as a sixteen-digit negative.
  PokeN(a, v)
  Print("Wrote ")
  PutHex8(v)
  Print(" to ")
  PutAddr(a)
  Print(". Reading it straight back gives ")
  PutHex8(PeekN(a))
  PrintN(".")
  PrintN("  A different value coming back is not necessarily a fault. Write-only,")
  PrintN("  write-one-to-clear and latching registers all disagree with what was")
  PrintN("  written, and they are right to. This line reports what the device")
  PrintN("  says when it is asked, not a verdict on the write.")
  ; THE READ-BACK IS NOT A VERDICT and the monitor does not offer one.
  ; Write-only, write-one-to-clear and latching registers all disagree
  ; with what was written, correctly. What this line reports is what the
  ; device says when asked.
EndProcedure

; ======================================================================
;  THE MEMORY FAMILY - base, fill, copy, compare, crc32
; ======================================================================
;  Added 2026-08-26, FROM THE REAL U-BOOT SOURCE rather than from
;  memory of it. The table these match is
;  RaspberryPi4/Reference/v2025.01_cmd_mem.c, in this repository, and
;  every signature and default below cites a line in it. Until that file
;  was downloaded the roadmap's U-Boot rows were general knowledge and
;  were marked "good enough to plan against and not good enough to
;  implement against"; they no longer are.
;
;  WHAT WAS IMPLEMENTED, AND WHAT WAS DELIBERATELY NOT
;  ---------------------------------------------------
;  IMPLEMENTED, because each does something Anvil could not do at all:
;
;    base      cmd_mem.c:510-522, table :1382-1387. A default address.
;    fill      U-Boot `mw`, cmd_mem.c:129-181, table :1331-1335. Anvil's
;              `write` does ONE word; this fills a range.
;    copy      U-Boot `cp`, cmd_mem.c:310-368, table :1337-1341.
;    compare   U-Boot `cmp`, cmd_mem.c:241-308, table :1343-1347.
;    crc32     cmd_mem.c:1244-1265, table :1359-1362. THIS IS THE ONE
;              THAT EARNS ITS PLACE. `save` replaces Anvil's own boot
;              image and there has never been a way to check an image
;              before or after writing it. tools/anvil.py already CRCs
;              every transfer with the same polynomial, so host and
;              board can now compute the answer independently and
;              compare - which is a different and much stronger claim
;              than "the transfer said ok".
;
;  NOT IMPLEMENTED, and these are rulings rather than omissions:
;
;    md        cmd_mem.c:66-115. Anvil's `memory` IS md, it has been
;              here longer, its count is in BYTES rather than in
;              objects, and it stops on any keystroke. A second name
;              for it that counted differently would be worse than not
;              having one. `md` is named in the help text so somebody
;              arriving from U-Boot finds `memory`.
;    mm, nm    cmd_mem.c:117-127, both of which call mod_mem and open an
;              INTERACTIVE sub-prompt that reads one value per address
;              off the line editor. That needs a second mode in
;              ReadLine() with its own escape, and "how do I get out of
;              mm" is the question U-Boot generates most. `write`
;              covers the one-off case and `fill` covers the range.
;    loop      cmd_mem.c:524-614, and `loopw` :616. The help text is
;              "infinite loop on address range" and it means it: there
;              is no exit but a reset. On a board whose entire recovery
;              story is "the prompt is still there", a command that
;              cannot return is a hang you asked for politely.
;    mtest     cmd_mem.c:1066-1242. A RAM test needs a region nothing
;              owns, and every region here is owned - by this monitor,
;              by U-Boot underneath it, or by the payload. `fill` then
;              `compare` then `crc32` does the honest ad-hoc version
;              over a range the operator has chosen on purpose.
;    ms        The search command, cmd_mem.c:370. Not asked for and not
;              needed yet.
;
;  WHERE ANVIL'S NAME IS BETTER, ANVIL'S NAME WINS, and the U-Boot
;  spelling is accepted as an alias so a transcript from U-Boot still
;  works: compare/cmp, copy/cp, fill/mw. `base` and `crc32` keep their
;  U-Boot names because those are already whole words - "crc32" is the
;  name of the algorithm, not an abbreviation of one.
;
;  COUNTS ARE IN BYTES HERE AND IN OBJECTS THERE, AND THAT IS ON
;  PURPOSE. U-Boot's cmp/cp/mw take a count of objects whose size comes
;  from a `.b`/`.w`/`.l` suffix on the command word, defaulting to 4
;  (cmd_get_data_size(argv[0], 4), cmd_mem.c:143, :258, :321). Anvil has
;  no suffix machinery and `memory <addr> <count>` has counted BYTES
;  since it existed. Two commands in one monitor whose count means
;  different things is the trap, so copy and compare count bytes.
;  `fill` is the one exception - it counts 32-bit WORDS, because it
;  writes words and because that is exactly mw's default (size 4, count
;  1, cmd_mem.c:143-162) - and it prints the byte count it worked out
;  every single time, so nobody is confused for longer than one command.
; ======================================================================

Procedure CmdBase()
  Define a.i
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. The default address is unchanged.")
      PrintN("   base <address> sets it, in hex; base on its own shows it; base 0")
      PrintN("   turns it off.")
      ProcedureReturn
    EndIf
    ; No argument at all is the REPORT form, not an error. U-Boot's
    ; do_mem_base does the same: it only assigns when argc > 1, and
    ; prints either way (cmd_mem.c:512-520).
  Else
    gBase = a
  EndIf

  Print("The default address is ")
  PutAddr(gBase)
  PrintNl()
  If gBase = 0
    PrintN("  Nothing is added to the addresses you type. This is where it starts,")
    PrintN("  and it is what U-Boot starts at too.")
    PrintN("  Type base <address> to set it, in hex.")
  Else
    PrintN("  It is added to the address arguments of memory, write, fill, copy,")
    PrintN("  compare, mm and nm, and each of those says so when it does it.")
    PrintN("  It is NOT added by crc32, mtest, load, save, run or autoboot. crc32")
    PrintN("  is the surprising one and it is deliberate: U-Boot's crc32 does not")
    PrintN("  add it either (v2025.01_cmd_mem.c:1244-1265).")
    PrintN("  Type base 0 to turn it off again.")
  EndIf
EndProcedure

; ======================================================================
;  THE WIDTH-SUFFIX HELPERS - shared by fill, copy, compare, mm and nm.
; ======================================================================
;  Added 2026-09-01. The mm/nm/mtest declines were re-opened, and the ask
;  was for the .b/.w/.l width suffix on fill, copy and compare as well
;  as md (the 2026-09-01 DECISION block in "U-Boot command and feature
;  inventory.md"). md already honours the suffix by GROUPING (see the
;  gMemWidth note in state.pi4); these commands honour it by SIZING THE
;  OBJECT the count counts, which is what U-Boot does -
;  cmd_get_data_size(argv[0], 4), read off the command word
;  (v2025.01_cmd_mem.c:143 mw, :256 cmp, :322 cp).
;
;  THE COUNT-UNIT RULE, STATED ONCE AND OBEYED EVERYWHERE BELOW
;  -----------------------------------------------------------
;  This is the exact trap the memcmd header above warns about - two
;  counts in one monitor that mean different things - so it is closed
;  here rather than reopened. Each command has a DEFAULT object size that
;  reproduces byte-for-byte what a bare (no-suffix) command did before
;  today, and a suffix OVERRIDES that default:
;
;    bare fill     = .l : the count is 32-bit WORDS  (mw's default size
;                         4, cmd_mem.c:143,:162 - and what CmdFill has
;                         counted since it existed)
;    bare copy     = .b : the count is BYTES         (Anvil's long-
;    bare compare  = .b : the count is BYTES          standing choice;
;                         U-Boot's bare cp/cmp count 32-bit words, and
;                         the memcmd header says why Anvil does not)
;
;  With a suffix the count is a number of OBJECTS OF THAT WIDTH, exactly
;  U-Boot's rule, and bytes = count * size. So `copy.b n` and bare
;  `copy n` move the same n bytes; `copy.l n` moves n words = 4n bytes;
;  and `fill.l` is byte-for-byte the bare `fill`. THE RESOLVED BYTE
;  COUNT IS PRINTED EVERY TIME (the file's established "N words - M
;  bytes" pattern), so the unit is never left to be guessed.
; ----------------------------------------------------------------------
; MemSize() USED TO LIVE HERE. It moved up beside the width table, above
; the first command that calls it, because every reader of the table now
; needs it - the memory dump included, and that one is defined long
; before this point in the file.

Procedure PutUnit(size.i)
  ; The plural object-unit name - U-Boot's own words (cmd_mem.c:258-260).
  If size = 1
    Print("bytes")
  ElseIf size = 2
    Print("halfwords")
  Else
    Print("words")
  EndIf
EndProcedure

Procedure PutUnit1(size.i)
  If size = 1
    Print("byte")
  ElseIf size = 2
    Print("halfword")
  Else
    Print("word")
  EndIf
EndProcedure

Procedure.i MaskTo(v.i, size.i)
  ; v truncated to the low `size` bytes, the value U-Boot actually stores
  ; ((u8)/(u16)/(u32) writeval, cmd_mem.c:170-176). Used for DISPLAY; the
  ; store primitives below already keep only the low bits.
  If size = 1
    ProcedureReturn v & $FF
  ElseIf size = 2
    ProcedureReturn v & $FFFF
  EndIf
  ProcedureReturn v & $FFFFFFFF
EndProcedure

Procedure StoreWidth(a.i, v.i, size.i)
  ; One write of `size` bytes, low bytes of v, little-endian.
  If size = 1
    PokeB(a, v & $FF)
  ElseIf size = 2
    PokeW(a, v & $FFFF)
  Else
    PokeN(a, v & $FFFFFFFF)
  EndIf
EndProcedure

Procedure.i ReadWidth(a.i, size.i)
  ; One read of `size` bytes, ASSEMBLED A BYTE AT A TIME, little-endian -
  ; the same reason DumpMem does it: a wide Peek of an unaligned device
  ; register is an alignment fault with no console message, and mm/nm
  ; must be able to show the current value of anything the operator
  ; points them at. Returns an unsigned value in the low `size` bytes.
  Define v.i
  Define k.i
  v = 0
  k = size - 1
  While k >= 0
    v = (v << 8) | (PeekA(a + k) & $FF)
    k = k - 1
  Wend
  ProcedureReturn v
EndProcedure

; ----------------------------------------------------------------------
;  fill - U-Boot's mw. A range set to one value of the chosen width.
;
;  ARGUMENT ORDER IS mw's: address, then value, then count
;  (cmd_mem.c:147-162 and the table entry at :1331-1335). The count
;  DEFAULTS TO 1 there and defaults to 1 here, so `fill <addr> <value>`
;  is exactly `write <addr> <value>` - which is a little redundant and
;  is kept anyway, because a person who learned mw should not have to
;  discover that Anvil spells the one-word case differently.
;
;  WIDTH: a bare fill writes 32-BIT WORDS and counts them, which is mw's
;  default (size 4) and is exactly what this command has always done - so
;  `fill.l` is byte-for-byte the bare `fill`. fill.b and fill.w write a
;  byte or a halfword and count THOSE. See the width-suffix helpers above
;  for the whole count-unit rule; the resolved byte count is printed
;  every time.
; ----------------------------------------------------------------------
Procedure CmdFill()
  Define a.i
  Define v.i
  Define n.i
  Define i.i
  Define bytes.i
  Define size.i

  size = MemSize(WtDefSize(#WT_FILL))   ; bare fill = .l (32-bit words), which is
                                 ; mw's default size 4 (cmd_mem.c:143,:162)
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was written.")
      ProcedureReturn
    EndIf
    PrintN("fill <address> <value> [count]      known to U-Boot as mw")
    PrintN("  set a range of memory to one value. All three are hex.")
    PrintN("  A bare fill writes 32-BIT WORDS and count defaults to 1, which is")
    PrintN("  what U-Boot's mw does. fill.b, fill.w and fill.l set the object to")
    PrintN("  a byte, a halfword or a word, and then the count is a number of")
    PrintN("  THOSE. The byte count worked out is always printed.")
    ; The example uses this board's own staging address rather than the
    ; literal 400000 it used to: on a monitor whose extent is its image,
    ; that address can be inside the monitor, and an example of a fill
    ; that would be refused is not an example.
    Print("  fill ")
    PutAddr(HwStageAddr())
    Print(" 0 1000 clears 4096 words - 16384 bytes - at ")
    PutAddr(HwStageAddr())
    PrintN(".")
    ProcedureReturn
  EndIf
  v = ParseHex()
  If gParseOk = 0
    PrintN("!! a value is required, in hex. A bare fill writes it as a 32-bit")
    PrintN("   word; fill.b / fill.w write only its low byte or halfword.")
    PrintN("   fill <address> <value> [count]")
    ProcedureReturn
  EndIf
  n = ParseHex()
  If gParseOk = 0
    n = 1                        ; mw's default, cmd_mem.c:158-162
  EndIf
  If n <= 0
    Print("!! a count of zero ")
    PutUnit(size)
    PrintN(" writes nothing, so nothing was written.")
    PrintN("   Leave the count out entirely if you meant one.")
    ProcedureReturn
  EndIf
  ; The ceiling is arithmetic: bytes = count * size must not run past the
  ; range check's honesty. See the note on #LEN_MAX in state.pi4. For a
  ; bare fill (size 4) this is exactly the old quarter-of-#LEN_MAX guard.
  If n > (#LEN_MAX / size)
    Print("!! that is more than a gigabyte of ")
    PutUnit(size)
    PrintN(", and the range check below")
    PrintN("   cannot be trusted for a length that large. Nothing was written.")
    PrintN("   Fill it in pieces.")
    ProcedureReturn
  EndIf

  a = AddBase(a)

  ; A wide store to an unaligned address in a device aperture is an
  ; alignment fault, not a slow write, and it arrives with no console
  ; message - the same trap `write` guards. A byte fill cannot be
  ; misaligned, so it needs no check.
  If size = 4 And (a & 3) <> 0
    PrintN("!! the address must be 4-byte aligned for 32-bit writes.")
    PrintN("   Round it down to a multiple of 4 and try again.")
    ProcedureReturn
  ElseIf size = 2 And (a & 1) <> 0
    PrintN("!! the address must be 2-byte aligned for 16-bit writes.")
    PrintN("   Round it down to a multiple of 2 and try again.")
    ProcedureReturn
  EndIf

  bytes = n * size
  If HitsMonitor(a, a + bytes - 1) <> 0
    Print("!! that range runs into the monitor itself, which lives at ")
    PutAddr(gMonHitLo)
    PrintNl()
    Print("   to ")
    PutAddr(gMonHitHi)
    PrintN(". Nothing was written and the range is untouched.")
    PrintN("   Filling over the running monitor would take this prompt with it.")
    PrintN("   Fill somewhere inside one of the payload windows instead:")
    PutWindows()
    ProcedureReturn
  EndIf
  ; ... and then the board, which answers a different question: not
  ; "would this destroy the monitor" but "can this range answer a bus
  ; access at all". A fill is the worst command to find that out with,
  ; because it stalls somewhere in the middle of a range it has already
  ; part-written.
  If AddrAllowed(a, a + bytes - 1, 1, "fill", "written") = 0
    ProcedureReturn
  EndIf

  i = 0
  While i < n
    ; ONE CHECK EVERY 1024 OBJECTS, not every one. See STOPPING A LONG
    ; PRINT: the check costs a UART status read, and doing it per store
    ; would make a large fill several times slower than the stores it
    ; is protecting.
    If (i & 1023) = 0
      If OutBreak() <> 0
        Print("   stopped after ")
        PrintDec(i)
        Print(" of ")
        PrintDec(n)
        Print(" ")
        PutUnit(size)
        PrintN(".")
        If i = 0
          PrintN("   Nothing was written and the range is untouched.")
        Else
          PrintN("   The range is PART FILLED, not untouched and not whole.")
        EndIf
        ProcedureReturn
      EndIf
    EndIf
    StoreWidth(a + (i * size), v, size)
    i = i + 1
  Wend

  ; The destination may well be code about to be run - filling a landing
  ; zone with a known pattern before a load is the usual reason to do
  ; this - so the range is cleaned out of the D-cache and dropped from
  ; the I-cache, exactly as the loaders do after a transfer.
  CacheFlushRange(a, a + bytes - 1)

  Print("Filled ")
  PrintDec(n)
  Print(" ")
  PutUnit(size)
  Print(" - ")
  PrintDec(bytes)
  Print(" bytes - at ")
  PutAddr(a)
  Print(" with ")
  PutHexN(MaskTo(v, size), size * 2)
  PrintN(".")
  Print("  The first ")
  PutUnit1(size)
  Print(" reads back ")
  PutHexN(ReadWidth(a, size), size * 2)
  Print(" and the last reads back ")
  PutHexN(ReadWidth(a + bytes - size, size), size * 2)
  PrintN(".")
EndProcedure

; ----------------------------------------------------------------------
;  copy - U-Boot's cp. Argument order is cp's: source, target, count
;  (cmd_mem.c:324-332, table :1337-1341).
;
;  OVERLAPPING RANGES ARE SAFE, and that is not an extra: U-Boot's cp
;  ends in memmove (cmd_mem.c:355), which is defined to handle overlap,
;  so a copy that shifts an image down by a few bytes works there and
;  has to work here. The direction choice below is the whole of it.
;
;  WIDTH: a bare copy counts BYTES - Anvil's long-standing choice, and
;  what memory and compare do - so a suffix is not needed for the common
;  case. copy.b/.w/.l count bytes, halfwords or words (cmd_mem.c:322),
;  and the copy STILL MOVES BYTES underneath: the width only scales how
;  many. A byte move is unaligned-safe and overlap-safe, which a
;  size-wide store into a device aperture is not, so there is no reason
;  to make the engine wider. The byte count is printed either way.
; ----------------------------------------------------------------------
Procedure CmdCopy()
  Define src.i
  Define dst.i
  Define n.i
  Define bytes.i
  Define i.i
  Define size.i

  size = MemSize(WtDefSize(#WT_COPY))   ; bare copy = .b (BYTES); a suffix makes
                                 ; the count objects (cmd_mem.c:322)
  src = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that source address has more than sixteen hex digits, and sixteen")
      PrintN("   is all a 64-bit address can have. Nothing was copied.")
      ProcedureReturn
    EndIf
    PrintN("copy <source> <destination> <count>      known to U-Boot as cp")
    PrintN("  copy a block of memory. All three are hex. A bare copy counts")
    PrintN("  BYTES - U-Boot's cp counts 32-bit words - and copy.b/.w/.l count")
    PrintN("  bytes, halfwords or words. The byte count is printed either way.")
    PrintN("  Overlapping ranges are safe - the copy runs whichever way round")
    PrintN("  does not eat its own source.")
    ProcedureReturn
  EndIf
  dst = ParseHex()
  If gParseOk = 0
    PrintN("!! a destination address is required, in hex.")
    PrintN("   copy <source> <destination> <count>")
    ProcedureReturn
  EndIf
  n = ParseHex()
  If gParseOk = 0
    Print("!! a count is required, in hex - a number of ")
    PutUnit(size)
    PrintN(".")
    PrintN("   copy <source> <destination> <count>")
    ProcedureReturn
  EndIf
  If n <= 0
    ; U-Boot says "Zero length ???" and returns 1 (cmd_mem.c:333-336).
    ; Same refusal, in a sentence that says what to do about it.
    PrintN("!! a length of zero copies nothing, so nothing was copied.")
    Print("   Give a count in hex - a number of ")
    PutUnit(size)
    PrintN(".")
    ProcedureReturn
  EndIf
  If n > (#LEN_MAX / size)
    PrintN("!! that is more than a gigabyte, and the range check below cannot be")
    PrintN("   trusted for a length that large. Nothing was copied. Copy it in")
    PrintN("   pieces - see the note on #LEN_MAX in the source.")
    ProcedureReturn
  EndIf

  src = AddBase(src)
  dst = AddBase(dst)
  bytes = n * size

  If HitsMonitor(dst, dst + bytes - 1) <> 0
    Print("!! the destination runs into the monitor itself, which lives at ")
    PrintNl()
    Print("   ")
    PutAddr(gMonHitLo)
    Print(" to ")
    PutAddr(gMonHitHi)
    PrintN(". Nothing was copied and the destination is")
    PrintN("   untouched. Copying over the running monitor would take this prompt")
    PrintN("   with it. Copy into one of the payload windows instead:")
    PutWindows()
    ProcedureReturn
  EndIf
  ; THE SOURCE IS NOT WINDOW-CHECKED, on purpose and for the same reason
  ; `memory` is not: reading is the debugger's job and being able to
  ; point it at a device aperture is most of its value. Copying the
  ; PL011's registers somewhere is a strange thing to do and it is not
  ; this command's business to forbid it.
  ;
  ; BOTH ENDS ARE BOARD-CHECKED, though, and separately, because they are
  ; different questions with different answers: the source is read and
  ; the destination is written, and a board may allow one and not the
  ; other. The source goes first so that a copy which cannot even read
  ; its input says so before it says anything about where it was going.
  If AddrAllowed(src, src + bytes - 1, 0, "copy", "copied") = 0
    ProcedureReturn
  EndIf
  If AddrAllowed(dst, dst + bytes - 1, 1, "copy", "copied") = 0
    ProcedureReturn
  EndIf

  If dst = src
    PrintN("The source and the destination are the same address, so nothing")
    PrintN("was copied. That is not a failure, but it is probably not what")
    PrintN("you meant either.")
    ProcedureReturn
  EndIf

  ; THE DIRECTION. Forwards is wrong when the destination is above the
  ; source AND they overlap: byte 0 of the destination would land on a
  ; byte of the source that has not been read yet. Backwards is wrong in
  ; the mirror case. Choosing on "dst > src" alone is correct for both,
  ; because when they do NOT overlap either direction works. The loop is
  ; byte-granular whatever the width (see the header on this command).
  If dst > src
    i = bytes - 1
    While i >= 0
      If (i & 4095) = 0
        If OutBreak() <> 0
          ; The count is stated rather than "part way", and it is
          ; bytes-1-i BECAUSE THIS LOOP RUNS BACKWARDS. Saying "part
          ; copied" when the check fired on the very first iteration
          ; and nothing had been written would be a false alarm about
          ; a destination that is actually untouched.
          Print("   stopped after ")
          PrintDec(bytes - 1 - i)
          Print(" of ")
          PrintDec(bytes)
          PrintN(" bytes. The destination is PART COPIED - it holds the")
          PrintN("   TOP of the source and its own old contents underneath.")
          ProcedureReturn
        EndIf
      EndIf
      PokeB(dst + i, PeekA(src + i))
      i = i - 1
    Wend
  Else
    i = 0
    While i < bytes
      If (i & 4095) = 0
        If OutBreak() <> 0
          Print("   stopped after ")
          PrintDec(i)
          Print(" of ")
          PrintDec(bytes)
          PrintN(" bytes.")
          If i = 0
            PrintN("   Nothing was copied and the destination is untouched.")
          Else
            PrintN("   The destination is PART COPIED, not whole.")
          EndIf
          ProcedureReturn
        EndIf
      EndIf
      PokeB(dst + i, PeekA(src + i))
      i = i + 1
    Wend
  EndIf

  ; The destination may be code. Same maintenance the loaders do.
  CacheFlushRange(dst, dst + bytes - 1)

  Print("Copied ")
  If gMemWidth <> 0
    PrintDec(n)
    Print(" ")
    PutUnit(size)
    Print(" - ")
    PrintDec(bytes)
    Print(" bytes")
  Else
    PrintDec(bytes)
    Print(" bytes")
  EndIf
  Print(" from ")
  PutAddr(src)
  Print(" to ")
  PutAddr(dst)
  PrintN(".")
  Print("  The destination now runs ")
  PutAddr(dst)
  Print(" .. ")
  PutAddr(dst + bytes - 1)
  PrintN(", and its caches have been flushed, so it can be run.")
  PrintN("  compare, or crc32 on both ranges, will prove it if you want it proven.")
EndProcedure

; ----------------------------------------------------------------------
;  compare - U-Boot's cmp. Argument order is cmp's: addr1, addr2, count
;  (cmd_mem.c:262-268, table :1343-1347).
;
;  WHAT U-BOOT PRINTS, matched in substance and not in wording: on the
;  first difference it names the type, both addresses and both values
;  and STOPS (cmd_mem.c:288-296), and it always finishes with a count of
;  how many objects were the same (:305). Both facts are here; the
;  words are Anvil's, because the wording is the part the bench owner
;  asked to be sentences and no host tool parses it.
;
;  WIDTH: a bare compare counts BYTES (Anvil's choice, as memory and
;  copy do); compare.b/.w/.l count bytes, halfwords or words
;  (cmd_mem.c:256). The comparison is BYTE-EXACT whatever the width -
;  the width only scales how many bytes are looked at and reports the
;  first differing BYTE, which is strictly more precise than U-Boot's
;  first-differing-object and never gives a different yes/no answer. The
;  byte count is printed either way.
; ----------------------------------------------------------------------
Procedure CmdCompare()
  Define a1.i
  Define a2.i
  Define n.i
  Define bytes.i
  Define i.i
  Define b1.i
  Define b2.i
  Define size.i

  size = MemSize(WtDefSize(#WT_COMPARE)) ; bare compare = .b (BYTES); a suffix
                                 ; makes the count objects (cmd_mem.c:256)
  a1 = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that first address has more than sixteen hex digits, and sixteen")
      PrintN("   is all a 64-bit address can have. Nothing was compared.")
      ProcedureReturn
    EndIf
    PrintN("compare <first> <second> <count>      known to U-Boot as cmp")
    PrintN("  compare two blocks of memory and name the first byte that differs.")
    PrintN("  All three are hex. A bare compare counts BYTES - U-Boot's cmp")
    PrintN("  counts 32-bit words - and compare.b/.w/.l count bytes, halfwords")
    PrintN("  or words. The comparison is byte-exact and the byte count printed.")
    ProcedureReturn
  EndIf
  a2 = ParseHex()
  If gParseOk = 0
    PrintN("!! a second address is required, in hex.")
    PrintN("   compare <first> <second> <count>")
    ProcedureReturn
  EndIf
  n = ParseHex()
  If gParseOk = 0
    Print("!! a count is required, in hex - a number of ")
    PutUnit(size)
    PrintN(".")
    PrintN("   compare <first> <second> <count>")
    ProcedureReturn
  EndIf
  If n <= 0
    Print("!! a count of zero ")
    PutUnit(size)
    PrintN(" compares nothing, so nothing was compared.")
    Print("   Give a count in hex - a number of ")
    PutUnit(size)
    PrintN(".")
    ProcedureReturn
  EndIf
  If n > (#LEN_MAX / size)
    PrintN("!! that is more than a gigabyte. Nothing was compared - see the note")
    PrintN("   on #LEN_MAX in the source. Compare it in pieces.")
    ProcedureReturn
  EndIf

  a1 = AddBase(a1)
  a2 = AddBase(a2)
  bytes = n * size

  If a1 = a2
    Print("Both addresses are ")
    PutAddr(a1)
    PrintN(", so all of it is trivially the same.")
    PrintN("  That is almost certainly a typo - compare wants two ranges.")
    ProcedureReturn
  EndIf

  ; Both sides are read, so both sides are asked about. Separately, so
  ; the refusal names the one that is the problem rather than the pair.
  If AddrAllowed(a1, a1 + bytes - 1, 0, "compare", "compared") = 0
    ProcedureReturn
  EndIf
  If AddrAllowed(a2, a2 + bytes - 1, 0, "compare", "compared") = 0
    ProcedureReturn
  EndIf

  i = 0
  While i < bytes
    If (i & 4095) = 0
      If OutBreak() <> 0
        Print("   stopped after ")
        PrintDec(i)
        PrintN(" bytes. Everything up to there was the same; the rest is unknown.")
        ProcedureReturn
      EndIf
    EndIf
    b1 = PeekA(a1 + i)
    b2 = PeekA(a2 + i)
    If b1 <> b2
      Print("!! they first differ ")
      PrintDec(i)
      PrintN(" bytes in.")
      Print("   ")
      PutAddr(a1 + i)
      Print(" holds ")
      PutHex2(b1)
      Print("   and ")
      PutAddr(a2 + i)
      Print(" holds ")
      PutHex2(b2)
      PrintNl()
      Print("   The first ")
      PrintDec(i)
      Print(" of ")
      PrintDec(bytes)
      PrintN(" bytes were the same. Nothing past the difference was looked at.")
      ProcedureReturn
    EndIf
    i = i + 1
  Wend

  Print("All ")
  If gMemWidth <> 0
    PrintDec(n)
    Print(" ")
    PutUnit(size)
    Print(" - ")
    PrintDec(bytes)
    Print(" bytes")
  Else
    PrintDec(bytes)
    Print(" bytes")
  EndIf
  Print(" at ")
  PutAddr(a1)
  Print(" and ")
  PutAddr(a2)
  PrintN(" are the same.")
EndProcedure

; ----------------------------------------------------------------------
;  crc32 - a checksum over a range. cmd_mem.c:1244-1265, table :1359.
;
;  WHY THIS ONE MATTERS MORE THAN THE OTHER FOUR. `save` writes over
;  Anvil's own boot image, and until now the only evidence that the
;  bytes in DRAM were the bytes intended was the receive command's own
;  ok. That checks the wire and nothing else: it cannot see a payload
;  overwritten afterwards by a stray `fill`, and it cannot say anything
;  at all about a file that came off the medium with `load`. crc32 can,
;  and tools/anvil.py computes the same value on the host from the same
;  polynomial (#CRC_POLY, and RAW_CHUNK's CRC in tools/ubsend.py), so
;  the two answers are genuinely independent.
;
;  NO CLAMP ON THE COUNT, unlike `memory`'s 4096. A whole boot image is
;  the point of the command and 275 KB is a normal argument. That makes
;  it the longest-running thing at this prompt, so it checks OutBreak()
;  between chunks, and IT PRINTS NO CHECKSUM IF IT WAS STOPPED. A
;  partial CRC is a plausible-looking number that is wrong, which is the
;  single failure mode this project refuses hardest.
;
;  U-BOOT'S THIRD ARGUMENT IS REFUSED. The table says "address count
;  [addr]" and "[save at addr]" (cmd_mem.c:1359-1362), but do_mem_crc
;  hands the arguments straight to hash_command(), which lives in
;  lib/hash.c - and lib/hash.c is NOT in this repository. The byte order
;  that function stores the result in is therefore a guess, and a
;  guessed-at compatibility is worse than an honest refusal. If somebody
;  wants it: download lib/hash.c into RaspberryPi4/Reference/, read
;  store_result(), and add it with a citation.
; ----------------------------------------------------------------------
Procedure CmdCrc32()
  Define a.i
  Define n.i
  Define done.i
  Define chunk.i
  Define crc.i

  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was computed.")
      ProcedureReturn
    EndIf
    PrintN("crc32 <address> <count>")
    PrintN("  the IEEE 802.3 CRC32 of a block of memory. Both hex, count in bytes.")
    PrintN("  There is no size limit - a whole boot image is what it is for.")
    PrintN("  Any keystroke stops it, and a stopped one prints no checksum.")
    PrintN("  The same polynomial tools/anvil.py uses, so the host and the board")
    PrintN("  can work out the answer separately and compare them.")
    ProcedureReturn
  EndIf
  n = ParseHex()
  If gParseOk = 0
    PrintN("!! a byte count is required, in hex.")
    PrintN("   crc32 <address> <count>")
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

  ; The third argument U-Boot has and this does not. Refused by name,
  ; with the reason, rather than ignored - an ignored argument is how
  ; somebody comes to believe a checksum was stored somewhere.
  SkipSpace()
  If gLine[gPos] <> 0
    PrintN("!! crc32 here takes exactly two arguments, an address and a count.")
    PrintN("   U-Boot's crc32 has a third that stores the result in memory. It is")
    PrintN("   not implemented, because the byte order it stores is decided in")
    PrintN("   lib/hash.c, which is not in this repository, and a guessed-at")
    PrintN("   compatibility is worse than none. Nothing was computed.")
    ProcedureReturn
  EndIf

  ; NO AddBase HERE, and that is matching rather than forgetting.
  ; do_mem_crc (cmd_mem.c:1244-1265) never adds base_address. Said out
  ; loud whenever a base is set, because it is the one exception in the
  ; family and a silent exception is a trap.
  If gBase <> 0
    Print("  note: crc32 does NOT add the default address ")
    PutAddr(gBase)
    PrintNl()
    PrintN("  - U-Boot's crc32 does not either. The address used is the one typed.")
  EndIf

  ; Asked BEFORE the "crc32 over ... bytes ..." line prints, so a refused
  ; range never announces work it did not start.
  If AddrAllowed(a, a + n - 1, 0, "crc32", "computed") = 0
    ProcedureReturn
  EndIf

  Print("crc32 over ")
  PrintDec(n)
  Print(" bytes, ")
  PutAddr(a)
  Print(" .. ")
  PutAddr(a + n - 1)
  PrintN(" ...")
  UartDrain()

  crc = $FFFFFFFF
  done = 0
  While done < n
    If OutBreak() <> 0
      PrintN("   stopped part way, so NO CHECKSUM IS PRINTED. A CRC of part of a")
      PrintN("   range looks exactly like a CRC of all of it and is not one.")
      ProcedureReturn
    EndIf
    chunk = n - done
    If chunk > 65536
      chunk = 65536              ; 64 KiB between break checks. At
    EndIf                        ; 1.5 GHz that is a few milliseconds.
    crc = Crc32Part(crc, a + done, chunk)
    done = done + chunk
  Wend
  crc = crc ! $FFFFFFFF

  Print("The CRC32 is ")
  PutHex8(crc)
  PrintN(".")
  PrintN("  IEEE 802.3, reflected, polynomial EDB88320 - the same one the receive")
  PrintN("  command checks with and the same one tools/anvil.py computes, so a")
  PrintN("  matching value from the host means the two agree independently.")
EndProcedure

; ======================================================================
;  mm / nm - interactive memory modify. U-Boot's mm (auto-incrementing)
;  and nm (constant address), both do_mem_mm/do_mem_nm -> mod_mem
;  (v2025.01_cmd_mem.c:117-127, :1147-1240).
; ======================================================================
;  THE DECLINE THIS ANSWERS. memcmd.pi4's header declined mm/nm because
;  they "need a second mode in ReadLine() with its own escape, and 'how
;  do I get out of mm' is the question U-Boot generates most." That
;  was re-opened on 2026-09-01 with the instruction to SOLVE the named
;  problem, not skip the command. It is solved two ways at once:
;
;    * THE ESCAPE IS PRINTED ON EVERY LINE. U-Boot's sub-prompt is a
;      bare " ? " and the way out (type a non-number) is nowhere on the
;      screen - which is the whole of why the question gets asked. Here
;      every line ends "(Enter=keep, . or q=quit): ", so the answer to
;      "how do I get out" is in front of you the entire time.
;    * NO SECOND MODE IN THE LINE EDITOR. The sub-prompt reads through
;      the SAME ReadLine() the main loop uses - it already pumps the
;      mouse, keyboard and wireless console and handles backspace - so
;      there is no forked editor to get subtly wrong. The one bit
;      ReadLine could not carry, "was this Ctrl-C or a blank Enter", is
;      carried by gLineCtrlC (state.pi4), set in the one place that knows
;      (parse.pi4). Ctrl-C therefore aborts; a blank Enter keeps and
;      advances; "." or "q" quit. Three ways out, all visible or
;      conventional.
;
;  READS ARE BYTE-ASSEMBLED (ReadWidth) so displaying the current value
;  of a device register cannot fault; WRITES are refused inside the
;  monitor (HitsMonitor, the same guard write/fill/copy use) and require
;  the address be aligned to the width, checked once because mm advances
;  by the width and so stays aligned.
; ----------------------------------------------------------------------
Procedure ModMem(incr.i)
  Define size.i
  Define a.i
  Define v.i
  Define cur.i
  Define c0.i

  ; mm and nm share this body, so they share a default - and the table
  ; carries a row for each. Taking one row silently would let the other
  ; drift and never be noticed, so a64_anvil_check asserts the two rows
  ; agree; U-Boot's default is size 4 for both (cmd_mem.c:1170).
  size = MemSize(WtDefSize(#WT_MM))
  a = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that address has more than sixteen hex digits, and sixteen is all")
      PrintN("   a 64-bit address can have. Nothing was changed.")
      ProcedureReturn
    EndIf
    If incr <> 0
      PrintN("mm <address>      interactive memory modify, auto-incrementing")
    Else
      PrintN("nm <address>      interactive memory modify, constant address")
    EndIf
    PrintN("  U-Boot's mm and nm. Opens a sub-prompt showing one address and its")
    PrintN("  current value at a time. Type a hex value to write it, press Enter")
    PrintN("  alone to leave it unchanged, or type . or q (or Ctrl-C) to quit.")
    If incr <> 0
      PrintN("  mm advances to the next location after each line.")
    Else
      PrintN("  nm stays on the one address so you can watch it change.")
    EndIf
    PrintN("  A bare mm/nm works in 32-bit words (U-Boot's default); mm.b/.w/.l")
    PrintN("  and nm.b/.w/.l choose a byte, halfword or word.")
    ProcedureReturn
  EndIf
  a = AddBase(a)

  ; Align once; mm advances by the width, so it can never drift out of
  ; alignment after this. A wide store to an unaligned device register is
  ; an alignment fault with no message - the trap `write` guards too.
  If size = 4 And (a & 3) <> 0
    PrintN("!! the address must be 4-byte aligned for a 32-bit modify. Round it")
    PrintN("   down to a multiple of 4, or use mm.b / mm.w, and try again.")
    ProcedureReturn
  ElseIf size = 2 And (a & 1) <> 0
    PrintN("!! the address must be 2-byte aligned for a 16-bit modify. Round it")
    PrintN("   down to a multiple of 2, or use mm.b, and try again.")
    ProcedureReturn
  EndIf

  Print("Interactive modify in ")
  PutUnit1(size)
  If incr <> 0
    PrintN("s. Enter a value to write, blank to keep and")
    PrintN("move on, . or q or Ctrl-C to quit. The address advances each line.")
  Else
    PrintN("s. Enter a value to write, blank to keep,")
    PrintN(". or q or Ctrl-C to quit. The address stays where it is.")
  EndIf

  Repeat
    ; THE CHECK IS INSIDE THE LOOP, not before it, and that is the whole
    ; difference between this command and the others. mm ADVANCES: it can
    ; start in memory that answers and walk into a block that does not,
    ; one Enter at a time, and the read at the top of each line is the
    ; access that would stall. So every address is asked about as it is
    ; reached, and a refusal ends the sub-prompt rather than skipping the
    ; line - carrying on past a block that cannot answer would mean
    ; walking further into it.
    ;
    ; forWrite is 1 even though this line only READS to begin with,
    ; because the operator is at a modify prompt and the next thing they
    ; type is a value. Asking as a writer up front means the answer
    ; cannot change between the display and the store.
    If AddrAllowed(a, a + size - 1, 1, "modify", "changed") = 0
      PrintN("   Left interactive modify at that address. Nothing there was read")
      PrintN("   and nothing was written.")
      ProcedureReturn
    EndIf
    cur = ReadWidth(a, size)
    PutAddr(a)
    Print(": ")
    PutHexN(cur, size * 2)
    Print("   (Enter=keep, . or q=quit): ")
    ReadLine()
    If gLineCtrlC <> 0
      PrintN("Quit (Ctrl-C). Nothing further was written.")
      ProcedureReturn
    EndIf
    gPos = 0
    SkipSpace()
    c0 = gLine[gPos] & $FF
    If c0 = 0
      ; A blank line keeps this location. mm advances, nm holds.
      ; (U-Boot: <CR> means don't modify, move to next - cmd_mem.c:1195.)
      If incr <> 0
        a = a + size
      EndIf
    ElseIf c0 = 46 Or c0 = 113 Or c0 = 81      ; '.'  'q'  'Q'
      PrintN("Left interactive modify.")
      ProcedureReturn
    Else
      v = ParseHex()
      If gParseOk = 0
        PrintN("!! that is not a hex value, and not blank, . or q either. Nothing")
        PrintN("   was written here. Type a hex value, Enter to keep, or q to quit.")
        ; Stay on this address so the operator can try again or quit.
      ElseIf HitsMonitor(a, a + size - 1) <> 0
        Print("!! ")
        PutAddr(a)
        PrintN(" is inside the monitor itself, so it was NOT written -")
        PrintN("   writing there would take this prompt with it. Type Enter, . or q,")
        PrintN("   or (with mm) keep going to step past it.")
        ; Do not write and do not advance: let the operator decide.
      Else
        StoreWidth(a, v, size)
        CacheFlushRange(a, a + size - 1)
        ; The read-back is what the device says when asked, not a verdict
        ; on the write - the same honest claim `write` makes.
        Print("   wrote ")
        PutHexN(MaskTo(v, size), size * 2)
        Print(", reads back ")
        PutHexN(ReadWidth(a, size), size * 2)
        PrintNl()
        If incr <> 0
          a = a + size
        EndIf
      EndIf
    EndIf
  ForEver
EndProcedure

Procedure CmdMm()
  ModMem(1)
EndProcedure

Procedure CmdNm()
  ModMem(0)
EndProcedure

; ======================================================================
;  mtest - a DESTRUCTIVE RAM test. U-Boot's do_mem_mtest
;  (v2025.01_cmd_mem.c:1066-1139) and the mem_test_alt sub-tests
;  (:790-935); the pattern pass is mem_test_quick's shape (:1002-1058).
; ======================================================================
;  THE DECLINE THIS ANSWERS. memcmd.pi4's header declined mtest because
;  "a RAM test needs a region nothing owns, and every region here is
;  owned." That was re-opened on 2026-09-01: solve the ownership problem,
;  do not skip the command. It is solved by making the operator take
;  ownership of an explicit range and then guarding that range HARD:
;
;    * NO DEFAULT RANGE. U-Boot falls back to CONFIG_SYS_MEMTEST_START/
;      END (cmd_mem.c:1078-1079); those would be a guess, and a guessed
;      range on this board hits something owned. start and end are both
;      REQUIRED here.
;    * IT MUST LIE INSIDE A PAYLOAD WINDOW, and must not touch the
;      monitor. This reuses the exact checks the loaders use - HitsMonitor
;      refuses the monitor's code and its Globals (the prompt would go
;      with them), InPayload requires the range be wholly inside the low
;      or high window, and PutWindows names them. The payload windows are
;      the only RAM the operator is allowed to scribble on; everything
;      else is the monitor, U-Boot's leftovers, the payload stack, or a
;      device aperture, and a destructive write to any of those is the
;      trap the original ruling named. (This is the honest reading of the
;      brief's "reuse existing range checks + PutWindows": HitsMonitor to
;      refuse the monitor, InPayload to require a window you own.)
;    * IT SAYS IT IS DESTRUCTIVE before the first write, and promises no
;      restore, because a RAM test cannot put back what it overwrites.
;    * IT DOES NOT LOOP FOREVER. U-Boot with no iteration count runs
;      until Ctrl-C (cmd_mem.c:1107-1109); this defaults to ONE pass,
;      because "a command that cannot return is a hang you asked for
;      politely" is exactly why `loop` was refused. Give an explicit
;      iteration count for more, and any key stops it between and within
;      tests (OutBreak).
;
;  IT TESTS WHAT THE CPU SEES. With the D-cache off - the boot default,
;  see `cache` - that is DRAM, which is the point. With the D-cache on a
;  small test could sit entirely in cache and prove nothing about the
;  chips; this is stated in the help rather than worked around, because
;  turning the cache off underneath the operator would be a silent state
;  change, which this monitor does not do.
;
;  IT WORKS IN 32-BIT WORDS via PokeN/PeekN (PeekN is the unsigned 32-bit
;  read), Anvil's native memory unit, and reports the first failing
;  word's address, expected and actual value, then STOPS.
; ----------------------------------------------------------------------
Procedure MtestStopped()
  PrintN("   The range holds part of a test pattern now, not its old contents,")
  PrintN("   and the test did not finish. Run it again to complete it.")
EndProcedure

Procedure MtestFailedEnd(total.i)
  Print("mtest FAILED - ")
  PrintDec(total)
  PrintN(" error(s), stopped at the first failing word shown above.")
  PrintN("  This memory did not read back what was written, so it is not")
  PrintN("  reliable. The range holds a test pattern now, not its old contents.")
EndProcedure

; The walking-1's address-line test (cmd_mem.c:795-871). Catches address
; bits stuck high, stuck low, or shorted together. Returns the error
; count (0 on success), or -1 if a key stopped it.
Procedure.i MtestAddr(start.i, words.i)
  Define pat.i
  Define anti.i
  Define off.i
  Define toff.i
  Define t.i
  pat = $AAAAAAAA
  anti = $55555555
  ; Write the default pattern at each power-of-two word offset.
  off = 1
  While off < words
    PokeN(start + (off << 2), pat)
    off = off << 1
  Wend
  ; Stuck-high: put the anti-pattern at offset 0; every pot offset must
  ; still read the pattern.
  PokeN(start, anti)
  off = 1
  While off < words
    If (off & 4095) = 0
      If OutBreak() <> 0
        ProcedureReturn -1
      EndIf
    EndIf
    t = PeekN(start + (off << 2))
    If t <> pat
      Print("   FAIL address bit stuck high at ")
      PutAddr(start + (off << 2))
      Print(": expected ")
      PutHex8(pat)
      Print(", read ")
      PutHex8(t)
      PrintNl()
      ProcedureReturn 1
    EndIf
    off = off << 1
  Wend
  PokeN(start, pat)
  ; Stuck-low / shorted: put the anti-pattern at each pot offset in turn;
  ; every OTHER pot offset must still read the pattern.
  toff = 1
  While toff < words
    If OutBreak() <> 0
      ProcedureReturn -1
    EndIf
    PokeN(start + (toff << 2), anti)
    off = 1
    While off < words
      t = PeekN(start + (off << 2))
      If t <> pat And off <> toff
        Print("   FAIL address bit stuck low or shorted at ")
        PutAddr(start + (off << 2))
        Print(": expected ")
        PutHex8(pat)
        Print(", read ")
        PutHex8(t)
        PrintNl()
        PokeN(start + (toff << 2), pat)
        ProcedureReturn 1
      EndIf
      off = off << 1
    Wend
    PokeN(start + (toff << 2), pat)
    toff = toff << 1
  Wend
  ProcedureReturn 0
EndProcedure

; The moving-inversion read/write integrity test (cmd_mem.c:885-934).
; Every storage bit is written and read as a zero and as a one. Returns
; the error count (0 on success), or -1 if a key stopped it.
Procedure.i MtestMovInv(start.i, words.i)
  Define off.i
  Define expect.i
  Define t.i
  ; Fill with an incrementing pattern starting at 1.
  off = 0
  While off < words
    If (off & 4095) = 0
      If OutBreak() <> 0
        ProcedureReturn -1
      EndIf
    EndIf
    PokeN(start + (off << 2), (off + 1) & $FFFFFFFF)
    off = off + 1
  Wend
  ; Verify each word, then write its inverse.
  off = 0
  While off < words
    If (off & 4095) = 0
      If OutBreak() <> 0
        ProcedureReturn -1
      EndIf
    EndIf
    expect = (off + 1) & $FFFFFFFF
    t = PeekN(start + (off << 2))
    If t <> expect
      Print("   FAIL read/write at ")
      PutAddr(start + (off << 2))
      Print(": expected ")
      PutHex8(expect)
      Print(", read ")
      PutHex8(t)
      PrintNl()
      ProcedureReturn 1
    EndIf
    PokeN(start + (off << 2), (~expect) & $FFFFFFFF)
    off = off + 1
  Wend
  ; Verify the inverse, then zero.
  off = 0
  While off < words
    If (off & 4095) = 0
      If OutBreak() <> 0
        ProcedureReturn -1
      EndIf
    EndIf
    expect = (~((off + 1) & $FFFFFFFF)) & $FFFFFFFF
    t = PeekN(start + (off << 2))
    If t <> expect
      Print("   FAIL read/write at ")
      PutAddr(start + (off << 2))
      Print(": expected ")
      PutHex8(expect)
      Print(", read ")
      PutHex8(t)
      PrintNl()
      ProcedureReturn 1
    EndIf
    PokeN(start + (off << 2), 0)
    off = off + 1
  Wend
  ProcedureReturn 0
EndProcedure

; Fill the whole range with one 32-bit pattern and read it all back
; (mem_test_quick's shape, cmd_mem.c:1034-1056). Returns the error count
; (0 on success), or -1 if a key stopped it.
Procedure.i MtestPattern(start.i, words.i, pat.i)
  Define off.i
  Define t.i
  pat = pat & $FFFFFFFF
  off = 0
  While off < words
    If (off & 4095) = 0
      If OutBreak() <> 0
        ProcedureReturn -1
      EndIf
    EndIf
    PokeN(start + (off << 2), pat)
    off = off + 1
  Wend
  off = 0
  While off < words
    If (off & 4095) = 0
      If OutBreak() <> 0
        ProcedureReturn -1
      EndIf
    EndIf
    t = PeekN(start + (off << 2))
    If t <> pat
      Print("   FAIL data pattern at ")
      PutAddr(start + (off << 2))
      Print(": expected ")
      PutHex8(pat)
      Print(", read ")
      PutHex8(t)
      PrintNl()
      ProcedureReturn 1
    EndIf
    off = off + 1
  Wend
  ProcedureReturn 0
EndProcedure

Procedure CmdMtest()
  Define start.i
  Define endA.i
  Define pat.i
  Define iters.i
  Define havePat.i
  Define words.i
  Define it.i
  Define bit.i
  Define r.i
  Define total.i

  start = ParseHex()
  If gParseOk = 0
    If gParseOver <> 0
      PrintN("!! that start address has more than sixteen hex digits. Nothing was")
      PrintN("   tested.")
      ProcedureReturn
    EndIf
    PrintN("mtest <start> <end> [pattern [iterations]]      DESTRUCTIVE RAM test")
    PrintN("  writes and reads back every 32-bit word in start..end (inclusive,")
    PrintN("  hex), so everything in that range is OVERWRITTEN and is NOT")
    PrintN("  restored. There is no default range on purpose: every region here")
    PrintN("  is owned, so you must name one and it must lie inside a payload")
    PrintN("  window. It runs an address-line test, a moving-inversion integrity")
    PrintN("  test, and walking ones and zeros; a pattern argument adds one more")
    PrintN("  value to test with. iterations defaults to 1 - unlike U-Boot this")
    PrintN("  does not loop forever - and any key stops it.")
    PrintN("  It tests what the CPU sees, so it is a true DRAM test only with the")
    PrintN("  D-cache off, which is the boot default (see cache).")
    ProcedureReturn
  EndIf
  endA = ParseHex()
  If gParseOk = 0
    PrintN("!! an end address is required, in hex. mtest will not guess a range,")
    PrintN("   because a guessed range on this board hits something that is owned.")
    PrintN("   mtest <start> <end> [pattern [iterations]]")
    ProcedureReturn
  EndIf
  havePat = 0
  pat = ParseHex()
  If gParseOk <> 0
    havePat = 1
  EndIf
  iters = ParseHex()
  If gParseOk = 0
    iters = 1
  EndIf
  If iters <= 0
    PrintN("!! iterations must be one or more. mtest does not loop forever - give")
    PrintN("   a count, or leave it out for a single pass.")
    ProcedureReturn
  EndIf

  ; NO AddBase - do_mem_mtest does not add base_address either
  ; (cmd_mem.c:1082,:1086 read start/end with no += base_address). Said
  ; out loud when a base is set, because it is an exception in the family.
  If gBase <> 0
    Print("  note: mtest does NOT add the default address ")
    PutAddr(gBase)
    PrintNl()
    PrintN("  - U-Boot's mtest does not either. The range used is the one typed.")
  EndIf

  If endA < start
    ; U-Boot: "Refusing to do empty test" (cmd_mem.c:1097-1100).
    PrintN("!! the end address is below the start, so the range is empty or")
    PrintN("   backwards. Nothing was tested. Give the start first, then a")
    PrintN("   higher end.")
    ProcedureReturn
  EndIf
  If (start & 3) <> 0
    PrintN("!! the start address must be 4-byte aligned - mtest works in 32-bit")
    PrintN("   words. Round it down to a multiple of 4 and try again.")
    ProcedureReturn
  EndIf

  words = (endA - start + 1) >> 2
  If words < 4
    PrintN("!! that range is too small to test - it must hold at least four")
    PrintN("   32-bit words (16 bytes). Nothing was tested.")
    ProcedureReturn
  EndIf

  ; THE GUARD. Destructive, so refuse the monitor outright and require
  ; the range be inside a payload window - the memory you are allowed to
  ; scribble on. Same checks and window report the loaders use.
  If HitsMonitor(start, endA) <> 0
    Print("!! that range runs into the monitor itself, which lives at ")
    PutAddr(gMonHitLo)
    PrintNl()
    Print("   to ")
    PutAddr(gMonHitHi)
    PrintN(". A destructive test there would overwrite the running")
    PrintN("   monitor and take this prompt with it, so nothing was tested.")
    PrintN("   Test inside one of the payload windows instead:")
    PutWindows()
    ProcedureReturn
  EndIf
  If InPayload(start, endA) = 0
    PrintN("!! mtest is destructive, so it only runs inside a payload window -")
    PrintN("   the memory you are allowed to scribble on. The range you gave is")
    PrintN("   not wholly inside one, so nothing was tested. Choose a range in:")
    PutWindows()
    ProcedureReturn
  EndIf
  ; And the board, last of the three, because it is the only one of them
  ; that can answer "this range cannot take a bus access at all". On a
  ; board whose payload windows are simply "all of DRAM" that is not a
  ; theoretical distinction: the windows say the range is yours to
  ; scribble on and say nothing about whether it exists.
  If AddrAllowed(start, endA, 1, "mtest", "tested") = 0
    ProcedureReturn
  EndIf

  ; SAY IT IS DESTRUCTIVE, before a single write.
  Print("This is DESTRUCTIVE: every word in ")
  PutAddr(start)
  Print(" .. ")
  PutAddr(endA)
  PrintN(" will be")
  PrintN("overwritten and is NOT restored - a RAM test cannot put back what it")
  PrintN("deliberately scribbles on. Any payload loaded there is gone. Press")
  PrintN("any key to stop it once it is running.")
  Print("Testing ")
  PrintDec(words)
  Print(" words, ")
  PutAddr(start)
  Print(" .. ")
  PutAddr(endA)
  If havePat <> 0
    Print(", extra pattern ")
    PutHex8(pat)
  EndIf
  PrintN(" ...")
  UartDrain()

  total = 0
  it = 0
  While it < iters
    If OutBreak() <> 0
      MtestStopped()
      ProcedureReturn
    EndIf
    If iters > 1
      Print("Iteration ")
      PrintDec(it + 1)
      Print(" of ")
      PrintDec(iters)
      PrintN(".")
    EndIf

    r = MtestAddr(start, words)
    If r < 0
      MtestStopped()
      ProcedureReturn
    EndIf
    total = total + r
    If r > 0
      MtestFailedEnd(total)
      ProcedureReturn
    EndIf

    r = MtestMovInv(start, words)
    If r < 0
      MtestStopped()
      ProcedureReturn
    EndIf
    total = total + r
    If r > 0
      MtestFailedEnd(total)
      ProcedureReturn
    EndIf

    ; Walking ones, then walking zeros, one bit at a time.
    bit = 0
    While bit < 32
      r = MtestPattern(start, words, (1 << bit))
      If r < 0
        MtestStopped()
        ProcedureReturn
      EndIf
      total = total + r
      If r > 0
        MtestFailedEnd(total)
        ProcedureReturn
      EndIf
      r = MtestPattern(start, words, (~(1 << bit)) & $FFFFFFFF)
      If r < 0
        MtestStopped()
        ProcedureReturn
      EndIf
      total = total + r
      If r > 0
        MtestFailedEnd(total)
        ProcedureReturn
      EndIf
      bit = bit + 1
    Wend

    If havePat <> 0
      r = MtestPattern(start, words, pat)
      If r < 0
        MtestStopped()
        ProcedureReturn
      EndIf
      total = total + r
      If r > 0
        MtestFailedEnd(total)
        ProcedureReturn
      EndIf
    EndIf

    it = it + 1
  Wend

  Print("mtest passed: ")
  PrintDec(it)
  Print(" iteration")
  If it <> 1
    Print("s")
  EndIf
  Print(" over ")
  PrintDec(words)
  PrintN(" words, no errors found.")
  PrintN("  The range holds the last test pattern now, not its old contents.")
EndProcedure

; ----------------------------------------------------------------------
;  map - THE WHOLE MEMORY MAP, AS THE RUNNING IMAGE MEASURES IT
;
;  NEW 2026-09-08, with the ruling that this monitor is a kernel and has
;  no size cap. Before that ruling there was nothing for this command to
;  do: the map was a set of constants in a board source file, so the
;  answer could be read out of the tree and was the same on every build.
;  It is now a MEASUREMENT the image takes of itself - HwMonBytes() is
;  __image_end__ minus __image_start__ - and where the payload window
;  starts is arithmetic on that number. A measurement that nothing prints
;  is a measurement nobody can check, so this prints it, with the byte
;  count beside the addresses it produced.
;
;  IT IS CORE AND IT NAMES NO CHIP. Every line comes from the seam:
;  HwMonLo/HwMonHi/HwMonBytes, the region list, the payload windows and
;  HwStageAddr. The Arduino UNO Q answers the same questions from UEFI's
;  loaded-image protocol and gets its own numbers with no code here
;  knowing that is what happened.
;
;  WHY IT IS NOT PART OF `info`. `info` is the board describing its
;  hardware - what this computer is, what it can do. This is where the
;  software has put itself, and it is the answer to a different question
;  ("where may I put a payload, and why is that address not the one I
;  used last month"). It is also the thing an upload tool asks for, and a
;  command whose whole output is the map is easier to read on a wire than
;  a section of a page of hardware prose.
; ----------------------------------------------------------------------
Procedure CmdMap()
  PrintN("THE MEMORY MAP, AS THIS IMAGE MEASURES IT")
  PutMonitorMap()
  PrintNl()
  PrintN("Where a payload may go:")
  PutWindows()
  PrintN("  Nothing in this map is a constant this program was told. The")
  PrintN("  monitor's extent is the size of the image the firmware loaded, and")
  PrintN("  the low window begins above it, so both move when this program")
  PrintN("  does. There is no maximum size.")
  PrintN("ok")
EndProcedure
