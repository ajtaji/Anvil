; ----------------------------------------------------------------------
;  #LINE_MAX WAS 72 UNTIL 2026-08-26 AND THAT WAS A SILENT AMPUTATION.
;
;  A WPA2 passphrase is up to 63 characters (#SET_WIFI_PASS_MAX,
;  Lib/settings.pi4:1705, itself copied from #CYW43_PASS_MAX,
;  RP2350/Lib/cyw43.pico2:460). The command that carries one is
;
;      wifi password <passphrase>
;
;  and "wifi password " is FOURTEEN characters before the passphrase
;  starts. 14 + 63 = 77. At #LINE_MAX = 72 the longest legal passphrases
;  simply could not be typed - and ReadLine() does not refuse an
;  over-long line, it stops echoing and DROPS the rest (see the
;  `If n < #LINE_MAX` below). The operator would have watched the last
;  five characters of their password not appear, pressed Enter, and been
;  told the passphrase was 58 characters long. A wrong answer with no
;  diagnostic, which is the failure mode this project exists to refuse.
;
;  96 left 82 for the passphrase, which is 19 characters of slack, and
;  it covered the longest `settings set` line then worth typing:
;  "settings set " is 13, the longest key is 31 (#SET_KEY_MAX,
;  Lib/settings.pi4:500), so 13 + 31 + 1 = 45 and a 51-character value
;  fitted. It did NOT cover a 95-character value (#SET_VAL_MAX,
;  Lib/settings.pi4:502) set by hand, and Help() said so rather than
;  letting it be discovered.
;
;  AND 96 WAS STILL TOO SHORT, WHICH THE WI-FI SLOTS MADE UNARGUABLE.
;  ------------------------------------------------------------------
;  Lib/settings.pi4 now keeps four numbered networks under
;  wifi.N.ssid and wifi.N.password.plaintext, and the second of those
;  is a TWENTY-FIVE character key name. So the line that sets a
;  maximum-length passphrase by hand is
;
;      settings set wifi.4.password.plaintext <63 characters>
;      13          + 25                      +1+ 63           = 102
;
;  which is SIX CHARACTERS over 96. Measured, not guessed. At 96 that
;  line was silently amputated by ReadLine and the operator would have
;  stored a 57-character passphrase, which is exactly the defect the
;  first half of this comment was written about. It was still true, in
;  a new place, three weeks later.
;
;  SO #LINE_MAX IS 144 AND THE WHOLE CLASS IS GONE, rather than being
;  moved along by six. The longest line this monitor can legally be
;  asked to accept is the longest `settings set`:
;
;      "settings set " 13 + #SET_KEY_MAX 31 + " " 1 + #SET_VAL_MAX 95
;      = 140
;
;  144 covers it with four characters to spare, and there is no longer
;  any legal settings line that has to be set by editing the file. The
;  caveat in Help() went with it.
;
;  WHY NOT JUST 104, OR 108. Because each of those is the same decision
;  taken again with a slightly different number, and the evidence is
;  now two for two that the number chosen to cover today's longest
;  command is too small for next month's. 140 is not a guess about
;  usage; it is the arithmetic ceiling of two constants that live in
;  another file and are cited above. Forty-four more bytes of DRAM on a
;  board with four gigabytes is not a cost worth a third round of this.
;
;  WHY NOT REMOVE THE LIMIT. The truncation flag and its message are
;  the belt to these braces and they stay: a bound that can be reached
;  must say so out loud, and #LINE_MAX being generous is not the same
;  as it being absent.
;
;  gLine below is #LINE_MAX + 8, not #LINE_MAX + 1: the eight is the
;  slack the original 72/80 pair had and it costs nothing.
; ----------------------------------------------------------------------
#LINE_MAX  = 1100              ; input line, minus room for the NUL.
                               ; exFAT permits a 1023-byte UTF-8 path;
                               ; the remainder holds a command, quotes,
                               ; address and length without truncation
#REC_MAX   = 260               ; an S-record body cannot exceed 254
#HEX_MAX   = 16                ; hex digits accepted in one number - a
                               ; full 64-bit address, and refused beyond
                               ; rather than silently wrapped
#DEC_MAX   = 19                ; decimal digits accepted - what a signed
                               ; 64-bit .i holds. `c` is the only caller
                               ; and a clock rate is ten.
#BLK       = 1024              ; b: bytes between acks. MUST equal
                               ; RAW_CHUNK in tools/ubsend.py.
; ----------------------------------------------------------------------
;  THE CEILING ON A LENGTH ARGUMENT, for the memory family.
;
;  ONE GIGABYTE. Not a policy about how much memory anybody should be
;  allowed to touch - the board has four - but an ARITHMETIC guard. The
;  range checks in fill and copy compute "addr + length - 1", and a
;  length typed as sixteen hex digits makes that sum wrap round past the
;  top of a signed .i. A wrapped sum makes HitsMonitor() return 0 for a
;  range that covers the monitor, which is the one refusal in those
;  commands that actually protects the prompt.
;
;  So a length above this is REFUSED AND SAID, rather than clamped. A
;  clamp would do a smaller thing than was asked for and report success,
;  which is the defect this monitor's whole output style exists to stop.
;  Nobody has a legitimate one-gigabyte fill at this prompt; anybody who
;  does can type four.
; ----------------------------------------------------------------------
#LEN_MAX   = $40000000         ; 1 GiB, in bytes
#CRC_POLY  = $EDB88320         ; IEEE 802.3, reflected
#BOOT_MS   = 2000              ; autoboot countdown
#BOOT_DOT  = 250               ; ... and how often it prints a dot

Global Dim gLine.b[#LINE_MAX + 8] ; the command line being edited, plus
                               ; the same eight-byte safety slack
                               ; #LINE_MAX for why both numbers grew on
                               ; 2026-08-26 and again when the numbered
                               ; Wi-Fi slots gave `settings set` a
                               ; twenty-five character key name.
Global Dim gRec.b[260]         ; one S-record, held until its checksum
                               ; proves it - nothing is poked before

Global gLineLen.i
Global gLineTrunc.i            ; 1 if ReadLine had to DROP characters
                               ; because the line was longer than
                               ; #LINE_MAX. See ReadLine.
Global gLineCtrlC.i            ; 1 if the line ReadLine just returned was
                               ; ended by Ctrl-C rather than Enter. Both
                               ; produce an EMPTY line - the main loop
                               ; treats either as "do nothing" and never
                               ; reads this - but the mm/nm sub-prompt in
                               ; memcmd.pi4 needs to tell a deliberate
                               ; Ctrl-C abort apart from a blank Enter
                               ; that means keep-and-advance, and forking
                               ; the shared line editor for that one bit
                               ; would be far worse than one flag. Reset
                               ; at the top of every ReadLine (parse.pi4).
Global gPos.i                  ; parser cursor into gLine
Global gParseOk.i
Global gParseOver.i            ; the number had more than the digit cap

Global gToTicks.i              ; receive timeout, in counter ticks

Global gRecs.i                 ; last load: records (or chunks) accepted
Global gBytes.i                ;            bytes written
Global gBad.i                  ;            records REJECTED
Global gFail.i                 ;            the transfer itself failed
                               ;            (timed out or was aborted),
                               ;            which is not the same thing
                               ;            as a rejected record
Global gLoLo.i                 ;            lowest address written
Global gHiHi.i                 ;            highest address written
Global gEntry.i                ;            entry point
Global gHaveEntry.i

Global gGoAddr.i               ; in  to CallAddr
Global gGoRc.i                 ; out of CallAddr - x0 at return
Global gSp.i                   ; monitor sp saved across the payload

; WHAT THE PAYLOAD FINDS IN x0 AT ITS FIRST INSTRUCTION.
;
; Zero for everything this monitor has ever entered up to now - `run`,
; `autoboot`, a flat image, a container without the wants-services flag -
; and that zero is a GUARANTEE the payload ABI makes (Anvil/Hal/abi.pbi,
; the entry contract), not an accident of what happened to be in the
; register. The one caller that sets it non-zero is PmfEnter() in
; Anvil/Core/pmfboot.pbi, for a container that declared
; #PMF_FLAG_WANTS_SERVICES, and the value is then the address of the
; service table.
;
; IT IS A GLOBAL AND NOT A PARAMETER TO RunAt, for the reason CallAddr's
; own header gives about gGoAddr: everything crosses into that asm in BSS
; globals, because the stack is the one thing a payload is guaranteed to
; disturb. RunAt() clears it on every entry and the caller sets it after,
; so a value left over from a previous boot cannot leak into a payload
; that asked for nothing.
Global gGoX0.i                 ; in  to CallAddr - what x0 holds at entry

; ----------------------------------------------------------------------
;  THE MEMORY-FAMILY WIDTH SUFFIX  -  U-Boot's .b / .w / .l
;
;  U-Boot puts the object size on the command word itself: md.b, md.w,
;  md.l, mw.l and so on, and cmd_get_data_size(argv[0], 4) reads it back
;  off argv[0] (v2025.01_cmd_mem.c:143, :258, :321). This monitor matches
;  whole words, so the suffix is stripped off the command word ONCE, in
;  the main loop, before dispatch - see the SUFFIX block there - and the
;  width it named is left here for the handler that runs next.
;
;  1 = byte (.b), 2 = 16-bit (.w), 4 = 32-bit (.l). It is RESET TO ZERO
;  at the top of every command so a width can never leak from one command
;  into the next, and a handler reads it as "0 means the default for this
;  command", which for `memory` is byte grouping - the grouping it has
;  always used - so a bare `md` or `memory` is byte for byte what it was.
;
;  THE COUNT STAYS IN BYTES whatever the suffix says, and that is the
;  same ruling the memory family was built on (see memcmd.pi4's header):
;  U-Boot's count is in OBJECTS and changes meaning with the suffix, and
;  two counts in one monitor that mean different things is the trap. Here
;  the suffix changes only how the bytes are GROUPED on the line, never
;  how many of them there are. Said out loud by the commands that take it.
; ----------------------------------------------------------------------
Global gMemWidth.i             ; 0 none, 1 .b, 2 .w, 4 .l  (see above)

; A scratch buffer for a hash digest - SHA-1 is 20 bytes, SHA-256 is 32,
; so 64 is generous and leaves room for anything wider later. It is in
; the monitor's own BSS, so writing into it can never touch a payload.
; Used by sha1sum / sha256sum (Anvil/Core/hash_cmd.pbi).
Global Dim gHashOut.b[64]

; A UTF-8 path copied out of gLine, for core storage commands that take a
; filename as an argument rather than reading it from the settings store:
; CmdSave in Anvil/Core/fs_cmd.pbi. It is copied rather than pointed at
; because gLine is the line editor's buffer and the parse continues past
; the name to read the address and the length.
;
; IT LIVED IN RaspberryPi4/Board/display_globals.pi4 UNTIL THE BOOTLOADER
; PASS, which is where it was put when `save` was a Pi 4 command in a Pi 4
; file. fs_cmd.pi4 is core now and builds for the Arduino UNO Q, which
; does not include that file at all - so a core command was reaching for a
; global declared in one board's hardware header. The native exFAT layer
; accepts up to 1023 UTF-8 bytes, plus the terminating NUL.
Global Dim gName.a[1024]

; A scratch buffer for one formatted number - setexpr's result, on its
; way into the settings store. Sixteen hex digits plus a NUL is the most
; a 64-bit value needs; 32 is generous. See CmdSetexpr in flow_cmd.pi4.
Global Dim gNumBuf.b[32]

; A scratch buffer for the `i2c` command's bytes - the register pointer
; plus the data of a write, or the bytes read back. In the monitor's own
; BSS, so it can never touch a payload. #I2C_CMD_MAX below is its usable
; size; the [+8] is the same slack gLine keeps. See Anvil/Core/i2c_cmd.pbi.
#I2C_CMD_MAX = 256
Global Dim gI2cBuf.b[264]
