; ======================================================================
; settings.pi4 - Anvil's persistent settings, on the Raspberry Pi 4.
; A KEY=VALUE store in DRAM, backed by ONE PLAIN TEXT FILE on the boot
; medium. Library, not a compiler builtin.
; ----------------------------------------------------------------------
; This is the thing U-Boot has that Anvil did not: a place to put a value
; and find it again after the power has been off.
;
;     setenv wifi_ssid Workshop
;     saveenv
;     printenv
;
; becomes
;
;     SettingsSet("wifi.network", "Workshop")
;     SettingsSave()
;     SettingsCount() / SettingsKeyAt(i) / SettingsValueAt(i)
;
; THE FIRST TWO CONSUMERS ARE THE WI-FI CREDENTIALS, and the bench owner
; asked for those and not for this. The general store was built anyway,
; because a Wi-Fi-shaped hole in a monitor is a Wi-Fi-shaped hole
; forever, and the next four things that want to persist - the console
; baud rate, the autoboot filename, whether the screen comes up, a static
; IP address - are all the same shape and would each have arrived as
; their own little hack. It is thirty-two keys and a text file. It is
; not a database and it must not become one.
;
; ======================================================================
; USE - this file names no other file (house rule: a library never
; includes a library). It calls the HwFile* STORAGE SEAM by name, so the
; MAIN program must list the seam's declarations and its board's backend
; FIRST:
;
;     XIncludeFile "RaspberryPi4/Lib/uart.pi4"     ; to PRINT the reason
;     ... the board's own hardware includes ...
;     XIncludeFile "Anvil/Hal/hal.pbi"             ; the #HW_FILE_* codes
;     XIncludeFile "Anvil/Storage/hwfile.pbi"   ; THIS BOARD's backend
;     XIncludeFile "Anvil/Core/settings.pbi"       ; MUST come after both
;
;     ; read the settings. Absent is NORMAL and is its own code, and the
;     ; backend brings whatever medium it has up for itself.
;     If SettingsLoad() = 0
;       If SettingsLastError() <> #SET_ERR_NO_FILE
;         PutS(SettingsErrorText())
;       EndIf
;     EndIf
;
;     ; ... change something ...
;     SettingsSet("wifi.network", "Workshop")
;
;     ; and put it back. Nothing to arm and nothing to disarm: the board's
;     ; backend does that around its own one write. See SAFETY.
;     SettingsSave()
;
; WHY IT TAKES A SEAM NOW, WHEN THE PARAGRAPH HERE USED TO ARGUE AGAINST
; ONE. It said, correctly at the time, that fat.pi4's block-reader seam
; exists because the block SOURCE genuinely varies - SD card, USB stick,
; a fabricated array in a test - whereas there was exactly one filesystem
; in this repository and no second candidate, so a function-pointer table
; here would be machinery abstracting over a set with one member.
;
; A second candidate arrived. The Arduino UNO Q reaches no block device
; from inside Anvil at all: it runs as a UEFI application with boot
; services up, and the firmware opens files for it by name over
; EFI_SIMPLE_FILE_SYSTEM_PROTOCOL. There is no sector, no partition table
; and no FAT of ours in that path. The set has two members and they do not
; even meet at the same LEVEL - one is blocks-plus-a-filesystem, the other
; is files - which is why the seam is defined at the level this file
; actually needs (open by name, size, read at an offset, write the whole
; thing) rather than at either board's natural one.
;
; And it is NOT a function-pointer table, which is the part of the old
; objection that still stands: the arity of an indirect call is unchecked
; on this backend (fat.pi4:134), so six pointers would be six unchecked
; signatures. These are ordinary named procedures, resolved at compile
; time, one set per board, exactly as every other Hw* group in
; Anvil/Hal/hal.pbi is.
;
; THE COST OF THAT DECISION, stated rather than glossed: this file cannot
; be compiled without fat.pi4 beside it, and its I/O half cannot be
; tested without a medium fat.pi4 will mount. The gate therefore
; fabricates a FAT32 volume - see WHAT WAS ACTUALLY PROVEN below. The
; PURE half (the table, the parser, the serialiser) was deliberately kept
; free of every Fat call so that it can be tested with no volume at all,
; and that split is why SettingsParse and SettingsSerialise are public.
;
; ======================================================================
; WHERE IT PERSISTS, AND WHY THERE
; ======================================================================
; ONE FILE, IN THE ROOT OF PARTITION 1 OF WHATEVER MEDIUM IS MOUNTED,
; CALLED SETTINGS.TXT.
;
; THE MEDIUM. It is not chosen here. This file calls FatOpen and
; FatCreate and gets whatever the main program mounted - the USB stick
; on this bench, the SD card if that is what answered. That is right:
; the settings belong to the medium Anvil booted from, so a stick moved
; to another board carries its own settings with it, and a board handed
; a different stick gets that stick's settings. Neither is a surprise.
;
; THE NAME. Eight-point-three, because fat.pi4 has no long filenames and
; refuses a name it cannot express (fat.pi4:198-201). SETTINGS.TXT is
; 8 + 3 exactly. ".TXT" IS A DELIBERATE CHOICE AND NOT A DEFAULT: it is
; what makes the file open in a text editor on every operating system the
; owner might plug this stick into, with no tool and no knowledge. That
; is the recovery story. A board that will not boot because of something
; in its settings is fixed by pulling the stick, double-clicking a file
; and deleting a line - not by finding another Pi.
;
; THE FORMAT. Plain ASCII, one KEY=VALUE to a line, for exactly the same
; reason. Every alternative considered was worse:
;
;   * A PACKED BINARY RECORD would be smaller and would need no parser.
;     Rejected: it cannot be read or repaired without this monitor, which
;     is precisely the situation the file exists to get out of. And the
;     parser it saves is two hundred lines that are testable with no
;     hardware, which is the cheapest kind of code in this project.
;   * A SECTOR AT A FIXED LBA, the way U-Boot's raw-MMC environment
;     works. Rejected hard, and this is the important one: fat.pi4's
;     write fence (fat_LbaWritable, fat.pi4:1612) refuses every sector
;     outside the FSInfo sector, the FAT and the data region. A fixed LBA
;     would mean either writing OUTSIDE the filesystem - where nothing
;     protects the boot image and the fence would have to be opened up -
;     or writing inside it, into space the filesystem believes is free
;     and will hand to the next file created. Both are ways to lose the
;     boot image. The fence is the single best safety property this
;     project has and nothing here is worth weakening it for.
;   * ONE FILE PER KEY. Rejected: thirty-two directory entries where one
;     will do, thirty-two 8.3 names to invent, and the root directory of
;     a Pi boot partition is not a place to be generous with.
;
; WHAT HAPPENS WHEN THE STICK IS ABSENT, UNWRITABLE, OR HAS NO SUCH FILE.
; Nothing bad, and nothing silent:
;
;   * NO MEDIUM AT ALL - HwFileOpen answers #HW_FILE_NOMEDIUM and this
;     file reports #SET_ERR_FAT with the seam's code kept in
;     SettingsFatError(). The table stays empty and Anvil runs.
;   * MOUNTED, NO SETTINGS.TXT - this is the NORMAL first boot and it has
;     ITS OWN CODE, #SET_ERR_NO_FILE, precisely so a caller can tell "you
;     have not saved any settings yet" from "your medium is broken". A
;     store that reported those two the same way would have every new
;     owner looking for a fault.
;   * READABLE BUT NOT WRITABLE - SettingsSave asks HwFileWritable()
;     BEFORE it touches the file, gets 0, and reports #SET_ERR_FAT with
;     #HW_FILE_READONLY in SettingsFatError(). Nothing was opened, created
;     or truncated. On the Pi 4 this is what a board that came up on the
;     SD card answers, because writing is implemented for USB only. See
;     SAFETY.
;   * THE FILE IS THERE AND IS RUBBISH - see THE STRICT PARSE below. The
;     load stops at the offending line, names it, and REFUSES TO SAVE
;     afterwards until told to, so a monitor cannot quietly delete the
;     part of the file it failed to read.
;
; In every one of those, Anvil comes up. Nothing in this file is on the
; path to a prompt.
;
; ======================================================================
; THE PASSWORD. READ THIS ONE PROPERLY.
; ======================================================================
; A Wi-Fi password stored by this file is stored IN PLAIN TEXT and can be
; read by anyone who plugs the stick into any computer. That is the
; recommendation, it was not arrived at lazily, and the whole of the
; reasoning is here so that it can be argued with.
;
; THREE OPTIONS WERE ON THE TABLE.
;
;   1. OBFUSCATE IT - XOR with a constant, base64, a "scrambler". THIS IS
;      THEATRE AND IT IS THE WORST OF THE THREE. The key would have to be
;      in the Anvil image, and the Anvil image is a file on the SAME
;      STICK: anyone who can read SETTINGS.TXT can read ANVIL.IMG and
;      recover the key from it. It buys nothing at all against the actual
;      attacker and it buys something real against US - a value that
;      LOOKS protected stops people asking whether it is, and the first
;      person to see base64 in a config file will assume somebody thought
;      about this. Rejected, and named as theatre here so that nobody
;      proposes it again as a small improvement.
;
;   2. STORE THE WPA2 PSK INSTEAD OF THE PASSPHRASE. This is the good
;      idea, and it is the one worth killing carefully rather than
;      dismissing. The PSK is the 32 bytes the radio actually needs;
;      it is derived from the passphrase and the network name and cannot
;      be turned back into the passphrase, so a passphrase the owner has
;      reused on some website would not be sitting on the stick. It is
;      still a credential and still sufficient to join - the gain is
;      narrow, but it is real.
;
;      IT IS REFUSED FOR TWO REASONS, EITHER OF WHICH IS ON ITS OWN
;      SUFFICIENT, AND BOTH WERE CHECKED IN THIS REPOSITORY RATHER THAN
;      ASSUMED.
;
;      (a) WE CANNOT COMPUTE IT. WPA2's derivation is
;          PBKDF2-HMAC-SHA1(passphrase, network name, 4096 iterations,
;          256 bits). SHA-**1**. The brief lists sha256.pi4, hmac.pi4 and
;          hkdf.pi4 as the PBKDF2 ingredients and they very nearly are -
;          but hmac.pi4 is HMAC-SHA-**256** and says so in its own first
;          line (hmac.pi4:2), and a search of every .pi4, .pico and
;          .pico2 in the tree on 2026-08-26 for SHA-1 found it mentioned
;          only as an algorithm identifier inside x509.pico. THERE IS NO
;          SHA-1 IMPLEMENTATION IN THIS PROJECT. Writing one, plus
;          PBKDF2, plus its test vectors, is a real piece of crypto work
;          whose entire benefit is the narrow one above.
;
;      (b) THE RADIO WOULD NOT TAKE IT IF WE HAD IT. The driver the Pi 4
;          will get is a port of RP2350/Lib/cyw43.pico2, which is
;          bench-proven through a WPA2 join. Its Cyw43SetPmk
;          (cyw43.pico2:4685) sends ioctl 268 with flags = 1, which is
;          BRCMF_WSEC_PASSPHRASE: "the RAW ASCII passphrase" and the
;          firmware runs PBKDF2 itself (cyw43.pico2:4645-4650). The
;          flags = 0 path, where the field holds a 32-byte binary PMK, is
;          documented there as "NEITHER DRIVER EVER SETS 0, SO THAT PATH
;          IS UNVERIFIED AND THIS DRIVER DOES NOT IMPLEMENT IT"
;          (cyw43.pico2:4652-4656), and a 64-character key is refused
;          outright by #CYW43_PASS_MAX = 63 (cyw43.pico2:460) exactly so
;          that a hex PSK cannot silently take the passphrase path.
;
;      (c) MEASURED ON THIS PART, 2026-08-27, AND IT IS STRONGER THAN
;          (b) PREDICTED. Everything in (b) is reasoning from the
;          RP2350's driver about a Pi 4 radio nobody had asked yet. The
;          CYW43455 on this board was then asked, four ways:
;
;              sup_wpa existence probe          status -23
;              bsscfg:sup_wpa = 1               status -23
;              bsscfg:sup_wpa2_eapver           status -23
;              WLC_SET_WSEC_PMK, 68 and 132 B   status  -2 BCME_BADARG
;
;          -23 is BRCMF_FW_UNSUPPORTED, and brcmfmac's own rule
;          (feature.c:184-201, wired at :341) is that anything else
;          would enable BRCMF_FEAT_FWSUP. THIS FIRMWARE HAS NO
;          SUPPLICANT. The bare probe was not trusted alone - the iovar
;          a driver WRITES is the per-interface bsscfg:sup_wpa, and a
;          firmware could know one and not the other; both refused. The
;          PMK ioctl answered BADARG rather than UNSUPPORTED, so it
;          EXISTS and only the argument was wrong, and both documented
;          struct sizes were tried.
;
;          THE CONSEQUENCE FOR THIS FILE. 802.11 authentication and
;          association need no supplicant and DO succeed here; the
;          four-way handshake that follows is RSN key management and
;          nothing on either side can run it, so no pairwise key exists
;          and NO DATA FRAME CAN PASS. Storing the passphrase is still
;          right, because it is what the join path consumes - but do not
;          read (b) as saying the passphrase produces a working link on
;          this part. It does not, yet, and the reason is in the radio's
;          firmware rather than in this store.
;
;      So the plaintext passphrase has to reach the radio. Storing
;      anything else would mean storing a form we cannot produce, to feed
;      an interface that will not accept it.
;
;   3. STORE IT PLAINLY AND SAY SO, LOUDLY, IN EVERY PLACE IT CAN BE SAID.
;      CHOSEN.
;
; AND "SAY SO" IS NOT A DOCUMENTATION PROMISE. It is built into the data,
; because a warning that lives anywhere else gets separated from the
; value the first time somebody copies the file:
;
;   * THE KEY IS CALLED "wifi.password.plaintext". The warning is IN THE
;     KEY NAME. It survives being opened in Notepad, being pasted into a
;     chat window, being printed by "settings show", and being read by
;     somebody who has never seen this file.
;   * EVERY SAVE WRITES A BANNER COMMENT at the top of SETTINGS.TXT
;     saying it in a sentence - see set_banner below. Rewritten every
;     time, so it cannot be deleted permanently by editing the file.
;   * THE MONITOR MUST SAY IT AT THE MOMENT OF SETTING. The wiring
;     specification hands over the exact sentence. That is the one moment
;     the operator is making the decision.
;
; SHOULD "settings show" MASK IT? YES, BY DEFAULT, AND FOR A REASON THIS
; BOARD MAKES CONCRETE. Anvil's output does not go only to a serial
; terminal in front of the person typing: it also goes to an HDMI console
; on a screen in a room, and this monitor has a "screenshot" command that
; sends that framebuffer over the wire. A default that puts the password
; on glass, and into the next screenshot anybody takes for an unrelated
; bug, is wrong. So SettingsIsSecret() reports which keys are secret, the
; monitor prints eight asterisks and the true character count - the count
; because "did it take all twenty characters" is a real question and it
; is the operator's own console - and there is a separate, explicit
; command that prints the value. Revealing a secret should cost a
; deliberate keystroke.
;
; THE RULE FOR WHICH KEYS ARE SECRET IS GENERIC, not a list with
; "wifi.password.plaintext" in it: a key is secret if its name contains
; "password" or "secret". Future keys inherit the masking by being named
; sensibly, which is the only way this stays true.
;
; WHAT THIS DESIGN DOES NOT DEFEND AGAINST, so nobody thinks it does:
;
;   * ANYONE HOLDING THE STICK. That is the whole threat and no on-board
;     scheme changes it. The real mitigation is not code: give the board
;     a guest network or an IoT VLAN, and do not use the household
;     password. That advice is free and it is worth more than everything
;     above.
;   * THE MONITOR'S OWN "memory" COMMAND. The value sits in this file's
;     table in DRAM for the whole session and a hex dump will show it.
;   * A WARM RESET. DRAM keeps its contents across one, so the bytes are
;     still there for the next thing that runs.
;   * WIPING AFTER USE. There is no SettingsWipe. The radio needs the
;     passphrase again on every reconnect, so a store that erased it
;     would only force a reload from the same plaintext file. cyw43's own
;     wipe of its transmit buffers (cyw43.pico2:4707-4718) is a different
;     and worthwhile thing - it clears the copy in a buffer a diagnostic
;     dump might print - and it stays that driver's job.
;
; ======================================================================
; THE STRICT PARSE, AND THE SAVE IT REFUSES TO DO
; ======================================================================
; A settings file is hand-editable by design, so it WILL be hand-edited
; wrongly. Two behaviours were possible and only one of them is safe.
;
;   SKIP THE BAD LINE AND CARRY ON. Rejected. The key on the bad line
;   keeps whatever value it had before - usually none - and the operator
;   is told nothing. "wifi.network is not set" when the file plainly
;   contains it is the worst report available.
;
;   STOP AT THE BAD LINE, NAME IT, AND REMEMBER. Chosen. SettingsParse
;   returns 0, SettingsErrorLine() is the line number counting from 1,
;   and everything before it IS in the table. The load is then marked
;   PARTIAL.
;
; AND A PARTIAL LOAD BLOCKS THE NEXT SAVE. This is the part that matters.
; SettingsSave rewrites the whole file from the table; after a partial
; load the table does not contain the lines past the failure, so saving
; would DELETE THEM - silently, permanently, and as a side effect of an
; unrelated command. SettingsSave refuses with #SET_ERR_UNSAFE_SAVE until
; SettingsDiscardLoad() is called, which is the operator saying "yes, I
; know, throw the rest away". Nothing else clears it.
;
; ======================================================================
; SAFETY - WHAT THIS FILE CAN AND CANNOT DAMAGE
; ======================================================================
; A settings write must never make this board unbootable. Writing to the boot
; (NOT 'bricked' - the boot image is on a REMOVABLE stick, so the worst
; case here is pulling it and rewriting it on a PC. Nothing in this
; project can reach the SPI bootloader EEPROM, which is the only part
; that could genuinely be unrecoverable. Saying 'brick' overstates it,
; and an overstated risk gets discounted the third time it is read.)
; stick is how this board replaces its own boot image, so a settings
; writer that can corrupt the filesystem is a serious hazard and the
; claims below are deliberately narrow.
;
; WHAT IT CANNOT DAMAGE, and the reasons are structural, not careful:
;
;   * THE MBR, THE VOLUME BOOT SECTOR, THE BACKUP BOOT SECTOR, AND
;     EVERYTHING OUTSIDE THE PARTITION. Not because this file avoids
;     them - it never computes a sector number at all. Every write it
;     causes goes through fat.pi4's fat_WriteRaw, which refuses any LBA
;     outside the FSInfo sector, the FAT region and the data region
;     (fat_LbaWritable, fat.pi4:1612-1642). There is no path from here
;     to a raw sector.
;   * ANVIL.IMG, KERNEL8.IMG, OR ANY OTHER FILE. The only name this file
;     ever passes to HwFileOpen or HwFileWriteAll is SETTINGS.TXT, from
;     one place - SettingsFileName - and there is no call that takes a
;     name from the caller. A settings store with a configurable filename
;     stored inside the file it names is a joke, and this is the other
;     reason not to have one.
;   * THE MEDIUM AT ALL, EXCEPT THROUGH THE ONE WRITE CALL. This file
;     NEVER calls FatSetRangeWriter - it does not know that such a thing
;     exists. On the board that has one, HwFileWriteAll arms it around its
;     own single write and disarms it on every path out, which is exactly
;     the pattern the monitor's own save command has always used and for
;     the reason stated there: leaving it set all the time would mean any
;     later bug in the monitor could reach the medium. Moving that
;     bracket into the backend made it one place instead of three, and
;     three places that must each remember to disarm on four exits is
;     twelve chances to forget.
;
; WHAT IT CAN DAMAGE, stated plainly:
;
;   * SETTINGS.TXT ITSELF. A save replaces its whole contents. If a file
;     of that name already existed on the stick and was something else,
;     it is gone. That is the one file this library will destroy.
;   * A SAVE INTERRUPTED BY POWER LOSS leaves SETTINGS.TXT part old and
;     part new, or leaves lost clusters. Both are things fat.pi4's
;     ordering rule bounds to exactly that (fat.pi4:405-443): the volume
;     still mounts and the board still boots. The next load either
;     succeeds, or fails the strict parse and says which line.
;   * A TYPO IN A KEY NAME creates a new key rather than failing. Thirty
;     two of those and the table is full and reports #SET_ERR_FULL. Both
;     are visible in "settings show", which is why that command exists.
;
; ======================================================================
; WHAT WAS ACTUALLY PROVEN, AND WHAT IS UNVERIFIED
; ======================================================================
; THIS FILE HAS RUN ON SILICON, AND THE RADIO JOINED AN ACCESS POINT
; USING CREDENTIALS IT READ OFF THE STICK.
;
; This heading used to say "NOTHING IN THIS FILE HAS RUN ON SILICON. It
; was written on 2026-08-26 and no board has executed it." That was true
; for about a day.
;
; ---- WHAT RAN ON THE BOARD ------------------------------------------
;
;   * REAL KEYS OFF REAL MEDIA, 2026-08-27.
;     RaspberryPi4/Examples/Diagnostics/pi4WifiJoin.pi4 includes
;     fat.pi4 and this file, reads FOUR credential slots -
;     wifi.N.ssid / wifi.N.password.plaintext, slot number equals
;     preference - out of SETTINGS.TXT on the boot stick, and hands them
;     to cyw43.pi4. The CYW43455 then ASSOCIATED on 2.4 GHz, with the
;     BSSID read back off the firmware and compared byte for byte
;     against the one selected: 04:42:1A:A5:BC:90, SSID matching,
;     channel 2, RSSI -35 dBm against the scan's -33. So the parser, the
;     table, the slot numbering and the preference order all executed on
;     hardware, against a file a human typed on another machine.
;
;   * BOTH BRANCHES OF THE PREFERENCE RULE WERE EXERCISED ON SILICON,
;     which matters because the rule is the part of this file with a
;     policy in it rather than a format.
;
;   * ANVIL CARRIES THE STORE AT EVERY BOOT. RaspberryPi4/Monitor/
;     anvil.pi4 includes this file; `settings show`, `settings save` and
;     `settings load` are monitor commands, and the four net.* keys
;     (net.address / net.netmask / net.gateway / net.server) live here
;     beside the Wi-Fi ones.
;
;   * AND IT FLUSHED OUT A REAL DEFECT ONE LEVEL UP. `settings set
;     wifi.4.password.plaintext <63 chars>` is 102 characters against
;     what was then a 96-byte command buffer. That was the SECOND time
;     that amputation had been found, so #LINE_MAX went to 144 rather
;     than to 104: 140 is the arithmetic ceiling of the longest legal
;     command, so the CLASS is gone rather than moved along. The buffer
;     is in anvil.pi4 and not here, but this file's key names are what
;     make the longest line, so it is recorded on both sides.
;
; ---- WHAT THE UNVERIFIED LIST STILL GETS RIGHT ----------------------
;
;   The Wi-Fi keys are NO LONGER "storage only" - see the join above -
;   and the entry that said so has been corrected in place. Everything
;   else in WHAT IS UNVERIFIED below stands. Read it; it is the honest
;   half, and the medium half of it is fat.pi4's list, not a new one.
;
; WHAT WAS PROVEN BEFORE ANY BOARD SAW IT, by execution on the A64 oracle
; (tools/a64/a64_interp.py), by tools/a64/a64_settings_check.py.
; 177 ASSERTIONS, ALL PASSING, in 3,307,129 interpreter steps, and 12
; deliberate defects each watched turning the gate RED:
;
;   * the table: set, get, overwrite, remove, the case fold, the key
;     character set, every length limit, and the full table refusing
;   * the parser against a fabricated file carrying comments in both
;     spellings, blank lines, CRLF and lone-CR line endings, a UTF-8
;     byte-order mark, leading and trailing blanks, a value containing
;     its own '=' characters, and a duplicate key
;   * the parser REFUSING a line with no '=', an empty key, an
;     over-length key and an over-length value, each by its own code and
;     with the right line number
;   * round trip: serialise the table, parse the bytes back, and compare
;     every key and value - which is the property that actually matters,
;     because it is what a save followed by a reboot does
;   * the I/O half against a FAT32 volume fabricated in memory, the same
;     way fat.pi4's own gate does it: create SETTINGS.TXT where none
;     exists, load it back, change a value, save over it, and load again
;   * that a partial load blocks a save, and that SettingsDiscardLoad
;     unblocks it
;   * that with no block writer installed the save is refused and NOT ONE
;     SECTOR IS WRITTEN - and, separately, that a save with the writer
;     armed never touches a sector outside fat.pi4's writable regions,
;     compared byte for byte by the harness against what it fabricated
;   * that ANVIL.IMG, sitting in the same root directory throughout, is
;     still there and still untouched afterwards
;
; AND TWO OF THE TWELVE MUTATIONS GOT THROUGH ON THE FIRST ATTEMPT,
; which is worth more than the ten that did not. Both were holes in the
; GATE rather than in this file, and both are the same shape - a
; property that is real but that nothing was looking at:
;
;   "A CR LF PAIR COUNTED AS TWO LINE ENDINGS" came out GREEN. Every
;   fixture whose ERROR LINE NUMBER was checked used bare LF endings, and
;   the one fixture with CRLF in it was only checked for its keys and
;   values. So the whole of the CRLF rule was untested, on a file format
;   whose normal case is a Windows text editor. The fix was to give the
;   line-number fixture CRLF endings.
;
;   "THE SERIALISER'S BOUNDS CHECK REMOVED" came out GREEN, and this one
;   is the better lesson. The gate asked for a serialisation into a
;   64-byte destination and asserted the return was -1. It WAS -1: with
;   set_Emit's check gone, set_EmitByte's own check still fired one line
;   later and reported the overflow correctly. By then it had written
;   sixty bytes past the end of the caller's buffer. A refusal that
;   arrives after the damage is not a refusal, and no return value can
;   show the difference. The fix was to zero a buffer with slack after
;   the limit and assert the slack is still zero.
;
;   The lesson generalises past this file, and it is the same one
;   fat.pi4 records at its own gate (fat.pi4:800-802): a test that
;   watches the RESULT can only see defects that change the result.
;   State the property - "nothing past `max` was written" - and it does
;   not matter how the code arrives at it.
;
; WHAT IS UNVERIFIED:
;
;   * ~~everything below fat.pi4's block-writer seam on real media~~ -
;     SUPERSEDED 2026-08-26/27. fat.pi4 has read AND written the real
;     USB boot stick on silicon, and this file's own keys came off it.
;     What is still unverified below that seam is fat.pi4's shorter
;     remaining list - durability, interrupted writes, exotic geometry -
;     and it is still fat.pi4's list and not a new one.
;   * ~~the Wi-Fi keys are STORAGE ONLY. No radio has ever read them.~~
;     SUPERSEDED 2026-08-27: a radio read four slots out of this store
;     and associated with the access point they named. What remains
;     unverified is the LENGTH LIMITS - they are copied from
;     cyw43.pico2:459-466 and are that file's gate, itself marked
;     UNVERIFIED there, and nothing has yet stored a maximum-length
;     value and joined with it.
;   * THE NUMBERED SLOTS came later than the 177 assertions above and
;     are not in that count. They are covered by
;     Examples/Diagnostics/pi4SettingsSelfTest.pi4 (PhaseWifiSlots),
;     which compiles and asserts against the same res[] discipline as
;     everything else, but the A64 oracle run that produced the 177 has
;     not been repeated with them in it. The claim here is COMPILED AND
;     ASSERTED, not ORACLE-PROVEN, and the difference is stated rather
;     than allowed to blur into the sentence above it.
;   * ~~THE PREFERENCE ORDER IS STORAGE ONLY TOO. Nothing scans,~~
;     ~~nothing chooses, nothing joins.~~ SUPERSEDED 2026-08-27: there
;     is a caller, it scans, it chooses and it joins - prefer 5 GHz
;     unless below the join floor, else 2.4 GHz, ties breaking on stored
;     slot before RSSI before BSSID so no path depends on scan order.
;
;     AND THE RULE HAS A KNOWN HOLE, found by reproducing it rather than
;     by reasoning: with all four credentials stored, the prefer-5 GHz
;     rule correctly picks the 5 GHz network, which then CANNOT
;     associate on this bench (the AP answers reason 43, AKMP_NOT_VALID
;     - it will not accept plain WPA2-PSK). THE RULE MAKES ONE CHOICE
;     AND HAS NO RETRY, so a correct selection ends in no link at all. A
;     ladder that falls through to the next candidate on an association
;     refusal is the fix and was deliberately not written at the end of
;     a session. That is a selection-policy defect, and this file owns
;     the ordering the policy walks.
;   * behaviour with a value containing a byte above 126. It is REFUSED,
;     which means a network name that is not ASCII cannot be stored.
;     802.11 permits an SSID of arbitrary bytes; this store does not, and
;     that is a real limitation rather than an oversight - see
;     set_CheckValue.
;
; ======================================================================
; DELIBERATELY LEFT OUT - the full list, so nobody assumes
; ======================================================================
;  * COMMENTS ARE NOT PRESERVED. A save rewrites the file from the table
;    and every hand-written comment in it is lost. Keeping them would
;    mean holding the original text and splicing, which is a text editor.
;    The banner is rewritten each time so the file always explains
;    itself; anything else the owner writes in there is theirs to lose.
;    THE MONITOR MUST SAY THIS when it saves.
;  * ORDERING. Keys come out in the order they were first set, which for
;    a loaded file is file order. There is no sort.
;  * TYPES. Every value is text. A caller that wants a number parses it.
;  * NESTING, SECTIONS, ARRAYS, INCLUDES, VARIABLE SUBSTITUTION. This is
;    not an INI file and it is certainly not U-Boot's scripting.
;  * A SECOND FILE, OR A BACKUP COPY. Considered - write SETTINGS.NEW,
;    then rename - and rejected because fat.pi4 has no rename
;    (fat.pi4:833) and the delete-then-create dance has a worse window
;    than the overwrite does.
;  * ENCRYPTION. See THE PASSWORD above.
;  * A CONFIGURABLE FILENAME. See SAFETY above.
;  * WATCHING FOR CHANGES, or reloading when the medium is swapped.
;    SettingsLoad happens when the caller asks and never otherwise.
;
; ======================================================================
; THE WHOLE API, IN ONE PLACE
; ======================================================================
;   the table
;     SettingsReset()             empty it. Does not touch the medium
;     SettingsCount()             how many keys are in it
;     SettingsKeyAt(i)            address of key i's NUL-terminated name
;     SettingsValueAt(i)          address of key i's NUL-terminated value
;     SettingsSet(*key, *value)   add or replace. 1 on success
;     SettingsGet(*key)           address of the value, or 0
;     SettingsHas(*key)           1 or 0, and never sets an error
;     SettingsLength(*key)        the value's length in bytes, or -1
;     SettingsRemove(*key)        1 on success
;     SettingsDirty()             1 if the table changed since load/save
;     SettingsKeySame(*a, *b)     1 when two SPELLINGS name the same key.
;                                 THE definition of that, and the only
;                                 one - anything outside this file that
;                                 has to decide whether a caller-supplied
;                                 name is a particular key asks this and
;                                 does not write its own comparison. See
;                                 THE KEY, below.
;
;   secrets
;     SettingsIsSecret(*key)      1 if the name contains password/secret
;     SettingsMaskText()          the eight asterisks to print instead
;
;   the file
;     SettingsFileName()          "SETTINGS.TXT" - the only name used
;     SettingsLoad()              read and parse it. 1 on success
;     SettingsSave()              serialise and write it. 1 on success
;     SettingsLoadState()         0 never, 1 clean, 2 PARTIAL
;     SettingsDiscardLoad()       accept losing the unread tail, and
;                                 allow a save again
;
;   the text, with no medium involved - this is what the gate tests
;     SettingsParse(*buf, len)    replace the table from KEY=VALUE text
;     SettingsSerialise(*buf,max) write the table out. Bytes, or -1
;     SettingsTextBuffer()        this file's own buffer, and
;     SettingsTextMax()           how big it is
;     SettingsDuplicates()        keys the last parse saw twice
;
;   Wi-Fi, the ONE-NETWORK pair. Kept forever, because a stick written
;   by an older build must keep working - see WHERE THE LEGACY FLAT PAIR
;   SITS, down beside the slots
;     SettingsWifiNetworkKey()    "wifi.network"
;     SettingsWifiPasswordKey()   "wifi.password.plaintext"
;     SettingsWifiNetwork()       the value, or 0
;     SettingsWifiPassword()      the value, or 0. PLAIN TEXT
;     SettingsSetWifiNetwork(*s)  1..32 bytes
;     SettingsSetWifiPassword(*s) 8..63 bytes
;
;   Wi-Fi, the NUMBERED SLOTS. wifi.N.ssid and wifi.N.password.plaintext
;   for N in 1..SettingsWifiSlots(). THE NUMBER IS THE PREFERENCE ORDER.
;   The flat pair above answers to SettingsWifiLegacySlot(), which is one
;   past the last real slot, so it is read by the same walk and is read
;   LAST
;     SettingsWifiSlots()             the highest real slot number
;     SettingsWifiLegacySlot()        the pseudo-slot the flat pair is
;     SettingsWifiSlotSsidKey(n)      "wifi.n.ssid", built at run time
;     SettingsWifiSlotPasswordKey(n)  "wifi.n.password.plaintext"
;     SettingsWifiSlotSsid(n)         the value, or 0 if the slot is empty
;     SettingsWifiSlotPassword(n)     the value, or 0. PLAIN TEXT
;     SettingsSetWifiSlotSsid(n,*s)   1..32 bytes. Real slots only
;     SettingsSetWifiSlotPassword(n,*s)  8..63 bytes. Real slots only
;     SettingsRemoveWifiSlot(n)       both keys. 1 if anything went
;     SettingsWifiSlotUsed(n)         1 if the slot has an SSID
;     SettingsWifiNextSlot(after)     walk the populated slots in
;                                     preference order. 0 at the end
;     SettingsWifiSlotCount()         how many are populated
;     SettingsWifiFindSsid(*ssid)     which slot holds that name, or 0.
;                                     BYTE-EXACT: no fold, no normalising
;
;   why it refused
;     SettingsLastError()         one of the #SET_ERR_ codes
;     SettingsErrorText()         a NUL-terminated English sentence
;     SettingsErrorLine()         which line of the file, counting from 1
;     SettingsFatError()          the storage seam's #HW_FILE_ code, for
;                                 #SET_ERR_FAT
; ======================================================================

EnableExplicit

; ----------------------------------------------------------------------
; Geometry. Bare literals - a constant initialiser on this compiler
; cannot contain arithmetic (fat.pi4:359-363) - with the arithmetic in
; the comment beside each one.
;
; THIRTY-TWO KEYS is the size of the whole idea. Two are Wi-Fi, four more
; are named in the header as likely, and twenty-six spare is generous for
; a bootloader. A store that grew past this wants a different design, not
; a bigger number here.
; ----------------------------------------------------------------------
#SET_MAX_KEYS    = 32
#SET_KEY_MAX     = 31    ; bytes of name, NOT counting the NUL
#SET_KEY_STRIDE  = 32    ; 31 + 1, so a key record is a round 32 bytes
#SET_VAL_MAX     = 95    ; bytes of value, NOT counting the NUL. A WPA2
                         ; passphrase is at most 63 (cyw43.pico2:460) and
                         ; a network name at most 32 (cyw43.pico2:466);
                         ; 95 leaves room for a path or an address
#SET_VAL_STRIDE  = 96    ; 95 + 1
#SET_KEY_BYTES   = 1024  ; 32 * 32
#SET_VAL_BYTES   = 3072  ; 32 * 96

; The text buffer, used for BOTH the load and the save. One buffer,
; because they never happen at the same time and this runs before there
; is a heap - the same argument fat.pi4 makes for its two sector buffers
; (fat.pi4:1319-1331).
;
; 6144 is the worst case with room to spare: 32 keys at 32 + 1 + 95 + 1
; = 4096 bytes of records, plus the banner, which is under 700.
#SET_TEXT_MAX    = 6144

#SET_MASK_STARS  = 8     ; how many asterisks a masked value prints as.
                         ; FIXED, and deliberately not the value's own
                         ; length - see THE PASSWORD in the header

; ----------------------------------------------------------------------
; ASCII. THIS LANGUAGE HAS NO CHARACTER LITERALS, so every byte compared
; in this file is a number with the character named beside it. That rule
; bites hardest in a KEY=VALUE parser, where the three bytes that carry
; all the meaning are exactly the three that would normally be written
; as characters.
; ----------------------------------------------------------------------
#SET_CH_TAB      = 9     ; a tab
#SET_CH_LF       = 10    ; newline - the line separator this file WRITES
#SET_CH_CR       = 13    ; carriage return - tolerated on read, never
                         ; written. See set_ParseLine
#SET_CH_SPACE    = 32    ; a space
#SET_CH_HASH     = 35    ; #  - a comment, and what the banner uses
#SET_CH_STAR     = 42    ; *  - the mask character
#SET_CH_DASH     = 45    ; -  - legal in a key
#SET_CH_DOT      = 46    ; .  - legal in a key, and the separator this
                         ; file's own key names use: wifi.network
#SET_CH_DIGIT0   = 48    ; 0
#SET_CH_DIGIT9   = 57    ; 9
#SET_CH_SEMI     = 59    ; ;  - also a comment. Two spellings because
                         ; both are what people type in config files
#SET_CH_EQUALS   = 61    ; =  - THE separator
#SET_CH_UPPER_A  = 65    ; A
#SET_CH_UPPER_Z  = 90    ; Z
#SET_CH_UNDER    = 95    ; _  - legal in a key
#SET_CH_LOWER_A  = 97    ; a
#SET_CH_LOWER_Z  = 122   ; z
#SET_CH_PRINT_LO = 32    ; the lowest byte a VALUE may contain (a space)
#SET_CH_PRINT_HI = 126   ; and the highest (a tilde)
#SET_CASE_GAP    = 32    ; 'a' - 'A'. The fold, written once

; THE UTF-8 BYTE ORDER MARK. Notepad on Windows will happily add these
; three bytes to the front of a file somebody edits and saves as UTF-8,
; and without this the first key comes back named with three invisible
; bytes on the front of it - which then does not match "wifi.network" and
; presents as "I set it and it did not take". It is skipped by name at
; the very start of the buffer and NOWHERE ELSE; a BOM in the middle of a
; file is not a BOM, it is a bad value byte, and is refused as one.
#SET_BOM0        = $EF
#SET_BOM1        = $BB
#SET_BOM2        = $BF

; ----------------------------------------------------------------------
; Why a call refused. One code per distinct failure - the same shape
; fat.pi4 and display.pi4 use, and for the same reason: a report that
; says "settings failed" sends somebody to look at the stick when the
; answer was that they typed a key name with a space in it.
; ----------------------------------------------------------------------
#SET_ERR_NONE         =  0
#SET_ERR_NULL         =  1  ; a null pointer where a string was wanted
#SET_ERR_NO_KEY       =  2  ; an empty key - "=value" with nothing left
                            ; of the '=', or SettingsSet("", ...)
#SET_ERR_KEY_LONG     =  3  ; the key is longer than #SET_KEY_MAX
#SET_ERR_KEY_CHAR     =  4  ; the key contains something outside
                            ; a-z 0-9 . - _ (after the case fold)
#SET_ERR_VALUE_LONG   =  5  ; the value is longer than #SET_VAL_MAX
#SET_ERR_VALUE_CHAR   =  6  ; the value contains a byte outside 32..126.
                            ; A tab, a control code, or anything above
                            ; ASCII - none of which survive a round trip
                            ; through a text file this file can promise
#SET_ERR_VALUE_EDGE   =  7  ; the value begins or ends with a space or a
                            ; tab. REFUSED rather than trimmed - see
                            ; set_CheckValue, this is the one that will
                            ; catch somebody out and it is deliberate
#SET_ERR_FULL         =  8  ; all #SET_MAX_KEYS slots are taken
#SET_ERR_NOTFOUND     =  9  ; no such key
#SET_ERR_SYNTAX       = 10  ; a line with no '=' on it at all.
                            ; SettingsErrorLine() says which
#SET_ERR_TEXT_LONG    = 11  ; the file is bigger than #SET_TEXT_MAX, or
                            ; the serialised table does not fit the
                            ; buffer it was given
#SET_ERR_NO_FILE      = 12  ; SETTINGS.TXT is not on the medium. THIS IS
                            ; NORMAL ON A FIRST BOOT and has its own code
                            ; so that a caller can say so
#SET_ERR_FAT          = 13  ; the storage seam refused. SettingsFatError()
                            ; holds its #HW_FILE_ code and
                            ; HwFileErrorText() its sentence. The name
                            ; still says FAT because renaming it would
                            ; touch eleven places to buy a tidier word -
                            ; see set_FailFat
#SET_ERR_READ_SHORT   = 14  ; the read delivered fewer bytes than the
                            ; medium said the file holds
#SET_ERR_UNSAFE_SAVE  = 15  ; the last load stopped part way and saving
                            ; now would delete the lines it never read.
                            ; SettingsDiscardLoad() is the way past it
#SET_ERR_BAD_LEN      = 16  ; a negative length
#SET_ERR_WIFI_NETWORK = 17  ; a network name outside 1..32 bytes
#SET_ERR_WIFI_PASS    = 18  ; a passphrase outside 8..63 bytes
#SET_ERR_WIFI_SLOT    = 19  ; a Wi-Fi slot number outside the range the
                            ; store keeps. Its own code and not
                            ; #SET_ERR_NOTFOUND, because "there is no
                            ; slot 9" and "slot 3 is empty" are
                            ; different sentences and the operator can
                            ; act on only one of them

; ----------------------------------------------------------------------
; State. All of it readable through an accessor; none of it meant to be
; poked at from outside.
;
; The table is TWO PARALLEL ARRAYS rather than one array of records,
; because a record type would need a Structure and the two arrays are
; addressed by the same index anyway. set_keys[i * #SET_KEY_STRIDE] is
; key i's NUL-terminated name; set_vals[i * #SET_VAL_STRIDE] is its
; NUL-terminated value. Both are always NUL-terminated, which is what
; lets SettingsGet hand a caller an address it can print directly.
; ----------------------------------------------------------------------
Global Dim set_keys.a[#SET_KEY_BYTES]
Global Dim set_vals.a[#SET_VAL_BYTES]
Global set_count.i = 0

Global set_err.i     = #SET_ERR_NONE
Global set_errLine.i = 0     ; which line of the file, counting from 1
Global set_fatErr.i  = 0     ; fat.pi4's code, when set_err = #SET_ERR_FAT
Global set_dirty.i   = 0     ; 1 when the table differs from the file
Global set_dupes.i   = 0     ; keys the last parse saw more than once

; 0 = never loaded, 1 = loaded clean, 2 = PARTIAL - the load stopped at a
; bad line and the table does not hold what the file holds. 2 is what
; SettingsSave refuses on. See THE STRICT PARSE in the header.
Global set_loadState.i = 0
Global set_wifiRevision.i = 0
Global set_wifiBatchDepth.i = 0
Global set_wifiBatchChanged.i = 0

; The key the caller asked for, folded and validated by set_MakeKey.
; SAME PATTERN AS fat.pi4's fat_wantName (fat.pi4:1338) and for the same
; reason: parameters lower to fixed global slots on this target, so the
; validated form is put somewhere stable and the search reads it from
; there rather than being handed a pointer that may have moved.
Global Dim set_wantKey.a[#SET_KEY_STRIDE]

; The file's text, both directions. See the note at #SET_TEXT_MAX.
Global Dim set_text.a[#SET_TEXT_MAX]

; Scratch for one line's key and value while the parser assembles them.
; They cannot be built in place in set_text because they need a NUL and
; the byte after the field is part of the file.
Global Dim set_lineKey.a[#SET_KEY_STRIDE]
Global Dim set_lineVal.a[#SET_VAL_STRIDE]

; The mask. Built once at first use rather than written as a literal so
; that #SET_MASK_STARS is the only place the count lives.
Global Dim set_mask.a[16]
Global set_maskBuilt.i = 0

; ======================================================================
;  Failure bookkeeping. One place, so every refusal is recorded the same
;  way - fat.pi4's fat_Fail (fat.pi4:1346), same shape, same reason.
; ======================================================================

Procedure.i set_Fail(code.i)
  set_err = code
  ProcedureReturn 0
EndProcedure

; Record a STORAGE SEAM refusal as ours, keeping ITS code so the caller
; can print HwFileErrorText() as well. Losing the underlying code here
; would turn "the medium has no free cluster" into "settings could not
; save", which is the exact failure mode the error-code discipline exists
; to prevent.
;
; THE NAME KEPT THE WORD "Fat" ON PURPOSE. This used to read FatLastError()
; and it now reads HwFileLastError(), which is a #HW_FILE_* code and not a
; #FAT_ERR_* one. Renaming set_FailFat, set_fatErr, SettingsFatError() and
; #SET_ERR_FAT to match would touch eleven places across three files and
; the one thing it would buy is a tidier word - while every existing note,
; gate and diagnostic that names #SET_ERR_FAT would silently stop matching
; the code. The names are internal, the meaning is one line away, and
; churn across a store that holds a boot configuration is not free.
Procedure.i set_FailFat()
  set_fatErr = HwFileLastError()
  set_err = #SET_ERR_FAT
  ProcedureReturn 0
EndProcedure

; ======================================================================
;  Small string work. This file does NOT include string.pi4 - a library
;  never includes a library - and it needs three things, so it has three
;  things. All of them treat a string as NUL-terminated bytes read with
;  PeekA, which is the UNSIGNED spelling; PeekB sign-extends on this
;  target (fat.pi4:260-268) and a byte of $EF read as -17 would compare
;  wrong against every limit below.
; ======================================================================

Procedure.i set_Len(*s)
  Define n.i
  If *s = 0
    ProcedureReturn 0
  EndIf
  n = 0
  While PeekA(*s + n) <> 0
    n = n + 1
    ; A bound, because an unterminated string here would walk DRAM until
    ; something faulted. Nothing this file stores can exceed the value
    ; stride, and a caller's string longer than that is refused on
    ; length anyway - so stopping here loses nothing and cannot hang.
    If n > #SET_TEXT_MAX
      ProcedureReturn n
    EndIf
  Wend
  ProcedureReturn n
EndProcedure

; Copy n bytes and add a NUL. The destination is always one of this
; file's own fixed arrays and the caller has already checked n against
; that array's limit.
Procedure set_CopyZ(*dst, *src, n.i)
  Define i.i
  i = 0
  While i < n
    PokeA(*dst + i, PeekA(*src + i))
    i = i + 1
  Wend
  PokeA(*dst + n, 0)
EndProcedure

; Exact association-selection allow-list. Cached PMK bookkeeping does not
; match and therefore cannot restart a live owner.
;
; THE EXACT COMPARISON IS CORRECT HERE AND ONLY BECAUSE OF WHERE IT SITS.
; Both callers hand it a key that has ALREADY been through the fold - the
; freshly made set_wantKey, or a name read back out of the table, which
; was folded when it went in - so there is no unfolded spelling to miss.
; It is a private helper for that reason and must stay one: called on a
; name straight from a caller it would answer the question the fold
; exists to settle, and answer it wrongly. Anything outside this file
; asks SettingsKeySame().
Procedure.i set_WifiSelectionKey(*key)
  Define n.i
  Define d.i
  If *key = 0 : ProcedureReturn 0 : EndIf
  n = set_Len(*key)
  If n = 12 And set_Contains(*key, "wifi.network") <> 0 : ProcedureReturn 1 : EndIf
  If n = 23 And set_Contains(*key, "wifi.password.plaintext") <> 0 : ProcedureReturn 1 : EndIf
  If n = 11 Or n = 25
    If PeekA(*key) = 119 And PeekA(*key + 1) = 105 And PeekA(*key + 2) = 102 And PeekA(*key + 3) = 105 And PeekA(*key + 4) = 46 And PeekA(*key + 6) = 46
      d = PeekA(*key + 5)
      If d >= 49 And d <= 52
        If n = 11 And set_Contains(*key + 7, "ssid") <> 0 : ProcedureReturn 1 : EndIf
        If n = 25 And set_Contains(*key + 7, "password.plaintext") <> 0 : ProcedureReturn 1 : EndIf
      EndIf
    EndIf
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure set_WifiChanged()
  If set_wifiBatchDepth <> 0
    set_wifiBatchChanged = 1
  Else
    set_wifiRevision = (set_wifiRevision + 1) & $FFFFFFFF
  EndIf
EndProcedure
Procedure set_WifiBatchBegin() : set_wifiBatchDepth = set_wifiBatchDepth + 1 : EndProcedure
Procedure set_WifiBatchEnd()
  If set_wifiBatchDepth > 0 : set_wifiBatchDepth = set_wifiBatchDepth - 1 : EndIf
  If set_wifiBatchDepth = 0 And set_wifiBatchChanged <> 0
    set_wifiBatchChanged = 0
    set_wifiRevision = (set_wifiRevision + 1) & $FFFFFFFF
  EndIf
EndProcedure
Procedure.i SettingsWifiRevision() : ProcedureReturn set_wifiRevision : EndProcedure

; 1 if the NUL-terminated *needle appears anywhere in the NUL-terminated
; *hay. Used only by SettingsIsSecret, on a key name that is at most 31
; bytes, so the naive double loop is the right amount of machinery.
Procedure.i set_Contains(*hay, *needle)
  Define hl.i
  Define nl.i
  Define i.i
  Define j.i
  Define ok.i
  hl = set_Len(*hay)
  nl = set_Len(*needle)
  If nl = 0
    ProcedureReturn 0
  EndIf
  If nl > hl
    ProcedureReturn 0
  EndIf
  i = 0
  While i <= (hl - nl)
    ok = 1
    j = 0
    While j < nl
      If PeekA(*hay + i + j) <> PeekA(*needle + j)
        ok = 0
        Break
      EndIf
      j = j + 1
    Wend
    If ok = 1
      ProcedureReturn 1
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 0
EndProcedure

; ======================================================================
;  THE KEY. Folded to lower case and validated into set_wantKey.
;
;  KEYS ARE CASE-INSENSITIVE AND THEIR CANONICAL FORM IS LOWER CASE.
;  "WiFi.Network" and "wifi.network" are the same key and the file always
;  holds the lower-case spelling. That is not a convenience: a store
;  where two spellings of a name are two different keys is a store where
;  a value can be set and then not found, and the operator has no way to
;  see the difference on a screen.
;
;  THE CHARACTER SET IS DELIBERATELY NARROW: a-z, 0-9, dot, dash,
;  underscore, and nothing else. In particular a key may not contain '='
;  (which would make the line ambiguous), a space (which would make it
;  ambiguous to the eye), or anything above ASCII. Refused by name with
;  #SET_ERR_KEY_CHAR rather than silently mangled.
; ======================================================================

; THE FOLD, AS A PROCEDURE, SO THERE IS EXACTLY ONE OF IT.
;
; Every place that decides whether two spellings are the same key goes
; through this byte-for-byte - set_MakeKey on the way in, SettingsKeySame
; for callers outside this file. A second copy of "add 32 if it is A..Z"
; is a second thing that can be got wrong, or left behind when this one
; changes, and the failure it produces is two names that the store treats
; as one and some caller treats as two.
Procedure.i set_FoldByte(c.i)
  If c >= #SET_CH_UPPER_A And c <= #SET_CH_UPPER_Z
    ProcedureReturn c + #SET_CASE_GAP
  EndIf
  ProcedureReturn c
EndProcedure

Procedure.i set_MakeKey(*key)
  Define i.i
  Define c.i
  Define n.i

  If *key = 0
    ProcedureReturn set_Fail(#SET_ERR_NULL)
  EndIf

  n = set_Len(*key)
  If n = 0
    ProcedureReturn set_Fail(#SET_ERR_NO_KEY)
  EndIf
  If n > #SET_KEY_MAX
    ProcedureReturn set_Fail(#SET_ERR_KEY_LONG)
  EndIf

  i = 0
  While i < n
    c = PeekA(*key + i)
    ; The fold, before the check, so an upper-case name is legal and
    ; lands as its lower-case self.
    c = set_FoldByte(c)
    If c >= #SET_CH_LOWER_A And c <= #SET_CH_LOWER_Z
      ; a-z, fine
    ElseIf c >= #SET_CH_DIGIT0 And c <= #SET_CH_DIGIT9
      ; 0-9, fine
    ElseIf c = #SET_CH_DOT
      ; . fine
    ElseIf c = #SET_CH_DASH
      ; - fine
    ElseIf c = #SET_CH_UNDER
      ; _ fine
    Else
      ProcedureReturn set_Fail(#SET_ERR_KEY_CHAR)
    EndIf
    set_wantKey[i] = c
    i = i + 1
  Wend
  set_wantKey[n] = 0
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  SettingsKeySame(*a, *b) - 1 when these two SPELLINGS name the same
;  key, which is the store's own answer and not an approximation of it.
;
;  WHY THIS IS PUBLIC AND WHY ANYTHING OUTSIDE THIS FILE MUST USE IT.
;  Keys are case-insensitive (see THE KEY, above): the store folds a name
;  before it writes one and before it looks one up, so "BOOT.FAILS",
;  "Boot.Fails" and "boot.fails" are one key holding one value. Any code
;  elsewhere that has to ask "is the name this caller handed me THAT key"
;  - a guard, an allow-list, a special case - is asking a question only
;  this file can answer correctly, because only this file knows what the
;  store does to a name before it uses it.
;
;  A comparison written anywhere else is a SECOND opinion about key
;  identity, and the two only have to disagree once. An exact byte
;  comparison standing in for this one recognises FEWER names than the
;  store treats as one - it misses every spelling but the folded one - so
;  a guard built on it refuses the spelling it was shown and admits every
;  other spelling of the same key, which then lands on that key anyway.
;  The hole is exactly one capital letter wide.
;
;  IT COMPARES FOLDED BYTES AND DOES NOT VALIDATE. Length and character
;  rules belong to set_MakeKey and are enforced when a key is actually
;  used; a name too long or carrying an illegal byte simply is not equal
;  to any legal key, which is the truthful answer to the question asked.
;  It touches set_wantKey and set_err not at all, so it is safe to call
;  from inside an operation that is part way through using them.
; ======================================================================
Procedure.i SettingsKeySame(*a, *b)
  Define i.i
  Define x.i
  Define y.i
  If *a = 0 Or *b = 0
    ProcedureReturn 0
  EndIf
  i = 0
  While 1
    x = set_FoldByte(PeekA(*a + i))
    y = set_FoldByte(PeekA(*b + i))
    If x <> y
      ProcedureReturn 0
    EndIf
    If x = 0
      ProcedureReturn 1
    EndIf
    i = i + 1
  Wend
EndProcedure

; Where set_wantKey is in the table, or -1. Takes no argument for the
; same reason fat_FindEntry does not (fat.pi4:2703): the thing being
; looked for is already in a stable place.
Procedure.i set_FindWant()
  Define i.i
  Define j.i
  Define *k
  Define a.i
  Define b.i
  Define same.i
  i = 0
  While i < set_count
    *k = @set_keys[0] + (i * #SET_KEY_STRIDE)
    same = 1
    j = 0
    While j < #SET_KEY_STRIDE
      a = PeekA(*k + j)
      b = set_wantKey[j]
      If a <> b
        same = 0
        Break
      EndIf
      If a = 0
        Break            ; both ran out at the same byte
      EndIf
      j = j + 1
    Wend
    If same = 1
      ProcedureReturn i
    EndIf
    i = i + 1
  Wend
  ProcedureReturn -1
EndProcedure

; ======================================================================
;  THE VALUE, and the one rule in this file most likely to surprise
;  somebody.
;
;  A VALUE MAY NOT BEGIN OR END WITH A SPACE OR A TAB, and that is a
;  REFUSAL rather than a trim.
;
;  Here is why. The file format has to allow blanks around the '=', or
;  "wifi.network = Workshop" - which is what a person types - would store
;  a value of " Workshop". So the parser trims. But a parser that trims
;  and a setter that accepts edge spaces disagree: SettingsSet("k", " x")
;  would save as "k= x" and load back as "x", and the value would change
;  by itself across a reboot. For a Wi-Fi password that is a board that
;  joins today and does not join tomorrow, with nothing on the console to
;  explain it.
;
;  So the two are made to agree by construction: what the parser can
;  produce is exactly what the setter accepts. The cost is stated
;  honestly in the header and in the error text - A WI-FI PASSWORD THAT
;  BEGINS OR ENDS WITH A SPACE CANNOT BE STORED BY ANVIL TODAY. Fixing
;  that means a quoting rule, which is a second parser, and it is not
;  worth it for a case nobody has hit. The refusal is loud, so the day
;  somebody does hit it they get a sentence and not a mystery.
;
;  THE PRINTABLE RANGE, 32..126, is the other half of the same promise:
;  a byte outside it does not survive a text file the owner may open in
;  an editor that normalises line endings, re-encodes, or strips control
;  codes. An SSID is permitted by 802.11 to be arbitrary bytes and this
;  store cannot hold one of those. Named in the header under UNVERIFIED.
; ======================================================================

Procedure.i set_CheckValue(*val)
  Define i.i
  Define c.i
  Define n.i

  If *val = 0
    ProcedureReturn set_Fail(#SET_ERR_NULL)
  EndIf

  n = set_Len(*val)
  If n > #SET_VAL_MAX
    ProcedureReturn set_Fail(#SET_ERR_VALUE_LONG)
  EndIf

  ; An EMPTY value is legal. "key=" is a key that exists and holds
  ; nothing, which is a different statement from the key being absent -
  ; and both are things an operator may want to express.
  If n = 0
    ProcedureReturn 1
  EndIf

  c = PeekA(*val)
  If c = #SET_CH_SPACE Or c = #SET_CH_TAB
    ProcedureReturn set_Fail(#SET_ERR_VALUE_EDGE)
  EndIf
  c = PeekA(*val + n - 1)
  If c = #SET_CH_SPACE Or c = #SET_CH_TAB
    ProcedureReturn set_Fail(#SET_ERR_VALUE_EDGE)
  EndIf

  i = 0
  While i < n
    c = PeekA(*val + i)
    If c < #SET_CH_PRINT_LO Or c > #SET_CH_PRINT_HI
      ProcedureReturn set_Fail(#SET_ERR_VALUE_CHAR)
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  THE TABLE
; ======================================================================

Procedure SettingsReset()
  Define i.i
  Define changed.i
  changed = 0
  i = 0
  While i < set_count
    If set_WifiSelectionKey(@set_keys[0] + (i * #SET_KEY_STRIDE)) <> 0
      changed = 1
      Break
    EndIf
    i = i + 1
  Wend
  ; The KEY bytes are zeroed, which is what empties the table - a slot
  ; whose name is the empty string can never match anything, because
  ; set_MakeKey refuses an empty key before a search ever happens.
  ;
  ; THE VALUE BYTES ARE ZEROED TOO, and that is not tidiness. One of the
  ; values is a Wi-Fi password. Leaving it in DRAM after a reset, where
  ; the monitor's own "memory" command would print it, is a worse default
  ; than the two milliseconds this costs. It does NOT make the password
  ; safe - see THE PASSWORD in the header, it is still in the file and
  ; still in the transmit buffers of whatever last used it - it just
  ; declines to leave an extra copy lying about for free.
  i = 0
  While i < #SET_KEY_BYTES
    set_keys[i] = 0
    i = i + 1
  Wend
  i = 0
  While i < #SET_VAL_BYTES
    set_vals[i] = 0
    i = i + 1
  Wend
  set_count = 0
  set_dirty = 0
  set_err = #SET_ERR_NONE
  set_errLine = 0
  set_dupes = 0
  If changed <> 0 : set_WifiChanged() : EndIf
EndProcedure

Procedure.i SettingsCount()
  ProcedureReturn set_count
EndProcedure

Procedure.i SettingsKeyAt(i.i)
  If i < 0 Or i >= set_count
    ProcedureReturn 0
  EndIf
  ProcedureReturn @set_keys[0] + (i * #SET_KEY_STRIDE)
EndProcedure

Procedure.i SettingsValueAt(i.i)
  If i < 0 Or i >= set_count
    ProcedureReturn 0
  EndIf
  ProcedureReturn @set_vals[0] + (i * #SET_VAL_STRIDE)
EndProcedure

; ----------------------------------------------------------------------
;  SettingsSet - add a key or replace its value. 1 on success.
;
;  Order of business matters here: the key is validated FIRST and the
;  value SECOND, so that "the key name is wrong" is reported for a call
;  that gets both wrong. A caller fixing one error at a time should be
;  told about the one that makes the call meaningless.
;
;  NOTHING IS CHANGED UNTIL BOTH CHECKS HAVE PASSED. A partially applied
;  set - the key created and the value refused - would leave a key
;  holding the empty string, which is a different and legal state, and
;  the caller would have no way to tell it from success.
; ----------------------------------------------------------------------
Procedure.i SettingsSet(*key, *value)
  Define idx.i
  Define n.i
  Define i.i
  Define same.i

  set_err = #SET_ERR_NONE

  If set_MakeKey(*key) = 0
    ProcedureReturn 0
  EndIf
  If set_CheckValue(*value) = 0
    ProcedureReturn 0
  EndIf

  idx = set_FindWant()
  same = 0
  If idx >= 0
    same = 1
    i = 0
    While i < #SET_VAL_STRIDE
      If set_vals[(idx * #SET_VAL_STRIDE) + i] <> PeekA(*value + i)
        same = 0
        Break
      EndIf
      If PeekA(*value + i) = 0 : Break : EndIf
      i = i + 1
    Wend
  EndIf
  If idx < 0
    If set_count >= #SET_MAX_KEYS
      ProcedureReturn set_Fail(#SET_ERR_FULL)
    EndIf
    idx = set_count
    n = set_Len(@set_wantKey[0])
    set_CopyZ(@set_keys[0] + (idx * #SET_KEY_STRIDE), @set_wantKey[0], n)
    set_count = set_count + 1
  EndIf

  n = set_Len(*value)
  set_CopyZ(@set_vals[0] + (idx * #SET_VAL_STRIDE), *value, n)
  set_dirty = 1
  If same = 0 And set_WifiSelectionKey(@set_wantKey[0]) <> 0
    set_WifiChanged()
  EndIf
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  THE SETTINGS SIDE - reading numbers out of a store that holds strings.
; ======================================================================

; PmfDecOf(*s, dflt) - a NUL-terminated decimal string as a number, or
; dflt when the string is absent, empty, or has anything in it that is not
; a digit.
;
; IT REFUSES A PARTIAL PARSE RATHER THAN TAKING THE DIGITS IT LIKED.
; "2x" is not 2. A setting somebody fat-fingered must fall back to the
; documented default and be visible as wrong, not quietly become a
; different number that happens to be a prefix of what they typed - which
; is how "boot.delay 30x" would silently become a three-second wait.
Procedure.i PmfDecOf(*s, dflt.i)
  Define v.i
  Define n.i
  Define c.i
  If *s = 0
    ProcedureReturn dflt
  EndIf
  v = 0
  n = 0
  Repeat
    c = PeekA(*s + n)
    If c = 0
      Break
    EndIf
    If c < 48 Or c > 57
      ProcedureReturn dflt
    EndIf
    If n >= 9
      ; Nine digits is 999,999,999, and every number this reads is a
      ; small count or a number of seconds. Longer than that is not a
      ; setting, it is a mistake, and it takes the default.
      ProcedureReturn dflt
    EndIf
    v = v * 10 + (c - 48)
    n = n + 1
  ForEver
  If n = 0
    ProcedureReturn dflt
  EndIf
  ProcedureReturn v
EndProcedure

; PmfPutDec(v, *dst) - a non-negative number as a NUL-terminated decimal
; string at *dst, for handing to SettingsSet. Written backwards into the
; buffer and then reversed, which is the shortest correct way to do it
; without a second pass to count the digits.
Procedure PmfPutDec(v.i, *dst)
  Define tmp.i
  Define n.i
  Define i.i
  Define c.i
  If v < 0
    v = 0
  EndIf
  n = 0
  If v = 0
    PokeB(*dst, 48)
    PokeB(*dst + 1, 0)
    ProcedureReturn
  EndIf
  tmp = v
  While tmp > 0
    PokeB(*dst + n, 48 + (tmp % 10))
    tmp = tmp / 10
    n = n + 1
  Wend
  PokeB(*dst + n, 0)
  i = 0
  While i < (n / 2)
    c = PeekA(*dst + i)
    PokeB(*dst + i, PeekA(*dst + n - 1 - i))
    PokeB(*dst + n - 1 - i, c)
    i = i + 1
  Wend
EndProcedure

; The address of the value, or 0. The address points INTO the table, so
; it is stable until the key is removed or the table is reset - which is
; the whole point: a caller prints it, or hands it to a radio, without
; needing a buffer of its own.
Procedure.i SettingsGet(*key)
  Define idx.i
  set_err = #SET_ERR_NONE
  If set_MakeKey(*key) = 0
    ProcedureReturn 0
  EndIf
  idx = set_FindWant()
  If idx < 0
    set_err = #SET_ERR_NOTFOUND
    ProcedureReturn 0
  EndIf
  ProcedureReturn @set_vals[0] + (idx * #SET_VAL_STRIDE)
EndProcedure

; 1 or 0, AND IT NEVER SETS AN ERROR. A caller asking whether a key
; exists is not making a mistake when it does not, and leaving
; #SET_ERR_NOTFOUND behind would poison the next SettingsErrorText() the
; monitor happened to print.
Procedure.i SettingsHas(*key)
  Define idx.i
  Define save.i
  save = set_err
  If set_MakeKey(*key) = 0
    set_err = save
    ProcedureReturn 0
  EndIf
  idx = set_FindWant()
  set_err = save
  If idx < 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

; The value's length in bytes, or -1 if there is no such key. This is
; what lets a caller print "20 characters, hidden" for a masked value.
Procedure.i SettingsLength(*key)
  Define *v
  *v = SettingsGet(*key)
  If *v = 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn set_Len(*v)
EndProcedure

; ----------------------------------------------------------------------
;  SettingsRemove - take a key out.
;
;  The tail is SHIFTED DOWN rather than the last entry being swapped into
;  the hole. Swapping is one copy instead of many and it is wrong here:
;  it reorders the file, so removing one key would shuffle an unrelated
;  line to a different place and a diff of two saved files would show
;  changes nobody made. Thirty-two entries of 128 bytes is nothing.
; ----------------------------------------------------------------------
Procedure.i SettingsRemove(*key)
  Define idx.i
  Define i.i
  Define j.i
  Define wifiChanged.i

  set_err = #SET_ERR_NONE
  If set_MakeKey(*key) = 0
    ProcedureReturn 0
  EndIf
  idx = set_FindWant()
  If idx < 0
    ProcedureReturn set_Fail(#SET_ERR_NOTFOUND)
  EndIf
  wifiChanged = set_WifiSelectionKey(@set_wantKey[0])

  i = idx
  While i < (set_count - 1)
    j = 0
    While j < #SET_KEY_STRIDE
      set_keys[(i * #SET_KEY_STRIDE) + j] = set_keys[((i + 1) * #SET_KEY_STRIDE) + j]
      j = j + 1
    Wend
    j = 0
    While j < #SET_VAL_STRIDE
      set_vals[(i * #SET_VAL_STRIDE) + j] = set_vals[((i + 1) * #SET_VAL_STRIDE) + j]
      j = j + 1
    Wend
    i = i + 1
  Wend

  ; Clear the slot that has just been vacated, values included - same
  ; argument as in SettingsReset: one of these may have been a password.
  j = 0
  While j < #SET_KEY_STRIDE
    set_keys[((set_count - 1) * #SET_KEY_STRIDE) + j] = 0
    j = j + 1
  Wend
  j = 0
  While j < #SET_VAL_STRIDE
    set_vals[((set_count - 1) * #SET_VAL_STRIDE) + j] = 0
    j = j + 1
  Wend

  set_count = set_count - 1
  set_dirty = 1
  If wifiChanged <> 0 : set_WifiChanged() : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i SettingsDirty()
  ProcedureReturn set_dirty
EndProcedure

; ======================================================================
;  SECRETS. Which keys are masked, and what to print instead.
;
;  THE RULE IS ON THE NAME, NOT ON A LIST OF KEYS. A key is secret if its
;  name contains "password", "passphrase" or "secret". A list of secret
;  KEY NAMES would be a second place to remember, and the day somebody
;  adds "http.auth.secret" and forgets the list, a credential prints
;  itself on the HDMI console. Naming a key sensibly is the only thing
;  anybody has to remember.
;
;  THREE WORDS AND NOT ONE. "pass" alone would have covered the first two
;  in one test and also covered "bypass" and "compass", and a rule that
;  masks a value nobody meant to hide is a rule people turn off.
;
;  It follows that a key called "wifi.password.plaintext" is masked
;  BECAUSE OF THE WORD "password" IN IT, and would still be masked if the
;  ".plaintext" suffix were dropped. The suffix is there for the human
;  reading the file, not for this rule.
; ======================================================================

Procedure.i SettingsIsSecret(*key)
  Define save.i
  save = set_err
  If set_MakeKey(*key) = 0
    set_err = save
    ProcedureReturn 0
  EndIf
  set_err = save
  If set_Contains(@set_wantKey[0], "password") = 1
    ProcedureReturn 1
  EndIf
  If set_Contains(@set_wantKey[0], "passphrase") = 1
    ProcedureReturn 1
  EndIf
  If set_Contains(@set_wantKey[0], "secret") = 1
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; The eight asterisks a masked value prints as. A FIXED count, not the
; value's own length - see THE PASSWORD in the header. The true length is
; available from SettingsLength() and the monitor prints it as a number,
; which is the useful half.
Procedure.i SettingsMaskText()
  Define i.i
  If set_maskBuilt = 0
    i = 0
    While i < #SET_MASK_STARS
      set_mask[i] = #SET_CH_STAR
      i = i + 1
    Wend
    set_mask[#SET_MASK_STARS] = 0
    set_maskBuilt = 1
  EndIf
  ProcedureReturn @set_mask[0]
EndProcedure

; ======================================================================
;  THE PARSER
;
;  One pass over a byte buffer. It never allocates, never looks past
;  `len`, and never calls into fat.pi4 - which is what makes the whole of
;  it testable with no medium at all.
;
;  LINE ENDINGS. LF, CRLF and a lone CR are all accepted as one line
;  ending; LF alone is what this file WRITES. Three spellings on the read
;  side because the file is meant to be edited on a PC and all three are
;  what a PC produces. One spelling on the write side because a file
;  written two ways is a file that diffs against itself.
;
;  THE FIRST '=' SPLITS THE LINE and every later one belongs to the
;  value. That is not an arbitrary pick: a base64 value ends in '=' and a
;  Wi-Fi password may contain one, while a key may not contain one at all
;  (set_MakeKey refuses it), so "first" is the only rule that can never
;  be wrong.
; ======================================================================

; One line, given as the half-open byte range [ls, le) inside *buf.
; Returns 1 if the line was consumed - INCLUDING a blank or a comment,
; which are consumed by being ignored - and 0 if it is malformed, with
; set_err already set. The caller adds the line number.
Procedure.i set_ParseLine(*buf, ls.i, le.i)
  Define k.i
  Define eq.i
  Define ke.i
  Define vs.i
  Define ve.i
  Define c.i
  Define i.i

  ; --- leading blanks -------------------------------------------------
  k = ls
  While k < le
    c = PeekA(*buf + k)
    If c <> #SET_CH_SPACE And c <> #SET_CH_TAB
      Break
    EndIf
    k = k + 1
  Wend

  ; --- blank line -----------------------------------------------------
  If k >= le
    ProcedureReturn 1
  EndIf

  ; --- a comment, in either spelling ----------------------------------
  c = PeekA(*buf + k)
  If c = #SET_CH_HASH Or c = #SET_CH_SEMI
    ProcedureReturn 1
  EndIf

  ; --- the FIRST '=' --------------------------------------------------
  eq = -1
  i = k
  While i < le
    If PeekA(*buf + i) = #SET_CH_EQUALS
      eq = i
      Break
    EndIf
    i = i + 1
  Wend
  If eq < 0
    ProcedureReturn set_Fail(#SET_ERR_SYNTAX)
  EndIf

  ; --- the key: [k, ke), trailing blanks removed ----------------------
  ke = eq
  While ke > k
    c = PeekA(*buf + ke - 1)
    If c <> #SET_CH_SPACE And c <> #SET_CH_TAB
      Break
    EndIf
    ke = ke - 1
  Wend
  If ke <= k
    ProcedureReturn set_Fail(#SET_ERR_NO_KEY)
  EndIf
  If (ke - k) > #SET_KEY_MAX
    ProcedureReturn set_Fail(#SET_ERR_KEY_LONG)
  EndIf
  set_CopyZ(@set_lineKey[0], *buf + k, ke - k)

  ; --- the value: [vs, ve), blanks removed at both ends ---------------
  ; The trim is what makes "key = value" work, and it is the reason
  ; set_CheckValue REFUSES a value with edge blanks. See the essay there.
  vs = eq + 1
  While vs < le
    c = PeekA(*buf + vs)
    If c <> #SET_CH_SPACE And c <> #SET_CH_TAB
      Break
    EndIf
    vs = vs + 1
  Wend
  ve = le
  While ve > vs
    c = PeekA(*buf + ve - 1)
    If c <> #SET_CH_SPACE And c <> #SET_CH_TAB
      Break
    EndIf
    ve = ve - 1
  Wend
  If (ve - vs) > #SET_VAL_MAX
    ProcedureReturn set_Fail(#SET_ERR_VALUE_LONG)
  EndIf
  set_CopyZ(@set_lineVal[0], *buf + vs, ve - vs)

  ; --- a key seen twice: the LAST one wins, and it is counted ---------
  ; Last-wins is what a shell environment file does and what anybody
  ; hand-editing expects: they add a corrected line at the bottom rather
  ; than finding the old one. Silently, though, it would hide a genuine
  ; mistake, so the count is kept and the monitor reports it.
  If SettingsHas(@set_lineKey[0]) = 1
    set_dupes = set_dupes + 1
  EndIf

  ProcedureReturn SettingsSet(@set_lineKey[0], @set_lineVal[0])
EndProcedure

; ----------------------------------------------------------------------
;  SettingsParse - replace the whole table from KEY=VALUE text.
;
;  THE TABLE IS EMPTIED FIRST. A parse that merged into what was already
;  there would make the result depend on what happened earlier in the
;  session, and "load the file" has to mean the file.
;
;  On a malformed line it STOPS, sets set_errLine, and leaves the table
;  holding everything up to that point with the load marked PARTIAL - see
;  THE STRICT PARSE in the header for why that is safer than skipping.
; ----------------------------------------------------------------------
Procedure.i SettingsParse(*buf, len.i)
  Define i.i
  Define ls.i
  Define le.i
  Define line.i
  Define c.i
  Define result.i

  set_WifiBatchBegin()
  SettingsReset()
  set_loadState = 0

  If *buf = 0
    result = set_Fail(#SET_ERR_NULL)
    set_WifiBatchEnd()
    ProcedureReturn result
  EndIf
  If len < 0
    result = set_Fail(#SET_ERR_BAD_LEN)
    set_WifiBatchEnd()
    ProcedureReturn result
  EndIf

  i = 0

  ; THE UTF-8 BYTE ORDER MARK, skipped at the very start and nowhere
  ; else. See the constants for what this costs when it is missing.
  If len >= 3
    If PeekA(*buf) = #SET_BOM0
      If PeekA(*buf + 1) = #SET_BOM1
        If PeekA(*buf + 2) = #SET_BOM2
          i = 3
        EndIf
      EndIf
    EndIf
  EndIf

  line = 0
  While i < len
    line = line + 1
    ls = i

    ; Find the end of the line WITHOUT reading past len. The test is
    ; written as an explicit Break rather than as a compound While
    ; condition because a compound condition would evaluate PeekA at
    ; offset len on the last line, and reading one byte past a buffer
    ; the caller supplied is not something to do on the strength of an
    ; assumption about which operand is evaluated first.
    While i < len
      c = PeekA(*buf + i)
      If c = #SET_CH_LF Or c = #SET_CH_CR
        Break
      EndIf
      i = i + 1
    Wend
    le = i

    ; Step over the terminator. CR LF is ONE ending, not two - counted
    ; as two, every line number in every error message would be wrong on
    ; a file saved by a Windows editor, which is most of them.
    If i < len
      c = PeekA(*buf + i)
      If c = #SET_CH_CR
        i = i + 1
        If i < len
          If PeekA(*buf + i) = #SET_CH_LF
            i = i + 1
          EndIf
        EndIf
      Else
        i = i + 1
      EndIf
    EndIf

    If set_ParseLine(*buf, ls, le) = 0
      set_errLine = line
      set_loadState = 2
      set_WifiBatchEnd()
      ProcedureReturn 0
    EndIf
  Wend

  ; A parse is not a change. The table now matches the text it came
  ; from, so nothing is pending.
  set_dirty = 0
  set_errLine = 0
  set_loadState = 1
  set_err = #SET_ERR_NONE
  set_WifiBatchEnd()
  ProcedureReturn 1
EndProcedure

Procedure.i SettingsDuplicates()
  ProcedureReturn set_dupes
EndProcedure

; ======================================================================
;  THE SERIALISER
; ======================================================================

; The banner. Written at the top of SETTINGS.TXT on EVERY save, so it
; cannot be permanently removed by editing the file, and so that the file
; explains itself to somebody who finds it on a stick with no idea what
; Anvil is.
;
; It is a procedure returning literals rather than one long constant
; because each line is emitted through the same bounds-checked writer as
; everything else - see set_Emit. A banner that could overrun the buffer
; while warning about safety would be a poor joke.
Procedure.i set_BannerLine(n.i)
  Select n
    Case 0
      ProcedureReturn "# Anvil settings. One KEY=VALUE to a line; keys are lower case."
    Case 1
      ProcedureReturn "# Lines beginning # or ; are comments. THEY ARE NOT KEPT: Anvil"
    Case 2
      ProcedureReturn "# rewrites this whole file from memory every time it saves."
    Case 3
      ProcedureReturn "#"
    Case 4
      ProcedureReturn "# THE WI-FI PASSWORD BELOW IS STORED IN PLAIN TEXT. Anyone who can"
    Case 5
      ProcedureReturn "# plug this stick into a computer can read it. That is deliberate:"
    Case 6
      ProcedureReturn "# the radio needs the passphrase itself, and hiding it on a disk"
    Case 7
      ProcedureReturn "# whose reader also holds the key would only look like protection."
    Case 8
      ProcedureReturn "# Use a guest network if that matters to you."
  EndSelect
  ProcedureReturn 0
EndProcedure

#SET_BANNER_LINES = 9

; Append a NUL-terminated string to *buf at set_emitPos, if it fits.
; set_emitFit goes to 0 the first time something does not, and stays
; there - so the caller checks once at the end instead of after every
; line, and a truncated buffer can never be mistaken for a complete one.
Global set_emitPos.i = 0
Global set_emitFit.i = 1

Procedure set_Emit(*buf, max.i, *s)
  Define n.i
  Define i.i
  If set_emitFit = 0
    ProcedureReturn
  EndIf
  n = set_Len(*s)
  If (set_emitPos + n) > max
    set_emitFit = 0
    ProcedureReturn
  EndIf
  i = 0
  While i < n
    PokeA(*buf + set_emitPos + i, PeekA(*s + i))
    i = i + 1
  Wend
  set_emitPos = set_emitPos + n
EndProcedure

Procedure set_EmitByte(*buf, max.i, v.i)
  If set_emitFit = 0
    ProcedureReturn
  EndIf
  If (set_emitPos + 1) > max
    set_emitFit = 0
    ProcedureReturn
  EndIf
  PokeA(*buf + set_emitPos, v)
  set_emitPos = set_emitPos + 1
EndProcedure

; ----------------------------------------------------------------------
;  SettingsSerialise - the table as text. Returns the number of bytes
;  written, or -1 with an error code set.
;
;  NO TRAILING NEWLINE IS OMITTED: every line, including the last, ends
;  with one. A file whose last line has no ending is a file that gains a
;  blank line the first time an editor saves it, and then differs from
;  what Anvil wrote for no reason anybody can see.
;
;  There is no space around the '=' on the way out. The parser accepts
;  spaces because people type them; the writer does not add them because
;  the tighter form is unambiguous and every byte here is a byte on a
;  boot medium.
; ----------------------------------------------------------------------
Procedure.i SettingsSerialise(*buf, max.i)
  Define i.i

  set_err = #SET_ERR_NONE

  If *buf = 0
    set_err = #SET_ERR_NULL
    ProcedureReturn -1
  EndIf
  If max < 0
    set_err = #SET_ERR_BAD_LEN
    ProcedureReturn -1
  EndIf

  set_emitPos = 0
  set_emitFit = 1

  i = 0
  While i < #SET_BANNER_LINES
    set_Emit(*buf, max, set_BannerLine(i))
    set_EmitByte(*buf, max, #SET_CH_LF)
    i = i + 1
  Wend
  set_EmitByte(*buf, max, #SET_CH_LF)

  i = 0
  While i < set_count
    set_Emit(*buf, max, @set_keys[0] + (i * #SET_KEY_STRIDE))
    set_EmitByte(*buf, max, #SET_CH_EQUALS)
    set_Emit(*buf, max, @set_vals[0] + (i * #SET_VAL_STRIDE))
    set_EmitByte(*buf, max, #SET_CH_LF)
    i = i + 1
  Wend

  If set_emitFit = 0
    set_err = #SET_ERR_TEXT_LONG
    ProcedureReturn -1
  EndIf
  ProcedureReturn set_emitPos
EndProcedure

Procedure.i SettingsTextBuffer()
  ProcedureReturn @set_text[0]
EndProcedure

Procedure.i SettingsTextMax()
  ProcedureReturn #SET_TEXT_MAX
EndProcedure

; ======================================================================
;  THE FILE. The only part of this library that touches a medium at all.
;
;  IT TALKS TO THE HwFile* SEAM AND NOT TO fat.pi4 ANY MORE, and the
;  change is worth a paragraph because everything else in this file is
;  untouched by it.
;
;  This store was written on the Pi 4, where the medium is a block device
;  and RaspberryPi4/Lib/fat.pi4 is our own filesystem on top of it, so it
;  called FatOpen / FatSize / FatRead / FatCreate / FatOverwrite / FatClose
;  directly. That was correct for one board and became wrong the moment a
;  second one arrived: the Arduino UNO Q has no block device Anvil can
;  reach and no FAT of ours anywhere in the picture - it runs as a UEFI
;  application and the firmware opens files for it by name. There is no
;  sector to read.
;
;  So those calls became calls into the seam Anvil/Hal/hal.pbi defines -
;  HwFileOpen / HwFileSize / HwFileReadAt / HwFileClose to read,
;  HwFileWritable / HwFileWriteAll to write - and each board answers them
;  with its own machinery. The Pi 4's backend (Anvil/Storage/hwfile.pbi)
;  is those same Fat* calls in the same order, so this board's behaviour
;  is unchanged; the Q's (ArduinoQ/Board/hw_file_q.unoq) is UEFI. That is
;  why this file also moved out of RaspberryPi4/Lib and into Anvil/Core:
;  Anvil/ARCHITECTURE.md already listed the settings store as core logic
;  riding a board-supplied backend, and it was only living under a board's
;  directory because at the time there was only one board.
;
;  THE SAFETY CLAIMS IN THE HEADER ALL STILL HOLD, and two of them are now
;  held in a better place:
;    * it still passes exactly ONE name, from the one procedure below, so
;      "this cannot damage any other file" is still checkable by reading
;      three lines.
;    * the block writer is still armed around exactly one call and
;      disarmed on every path out - but that now happens inside
;      HwFileWriteAll on the board that has a block writer, rather than
;      being a rule each calling command had to remember.
;    * SettingsSave still serialises into the buffer FIRST and only then
;      goes near the medium, so a refused save leaves the file byte for
;      byte as it was.
; ======================================================================

; THE ONLY NAME THIS LIBRARY EVER PASSES TO THE STORAGE SEAM. One place,
; so the safety claim in the header - that this file cannot damage any
; other file - is checkable by reading three lines rather than by
; trusting a sentence.
;
; WHERE THAT NAME LANDS IS THE BOARD'S BUSINESS, not this file's. On the
; Pi 4 it is the root directory of the boot medium. On the Q it is
; \EFI\anvil on the EFI System Partition, because the root of that volume
; belongs to the firmware and to Debian. Either way this file says
; SETTINGS.TXT and stops.
Procedure.i SettingsFileName()
  ProcedureReturn "SETTINGS.TXT"
EndProcedure

; ----------------------------------------------------------------------
;  SettingsLoad - read SETTINGS.TXT and parse it.
;
;  "NOT THERE" IS NOT A FAILURE OF THE MEDIUM and gets its own code. On a
;  first boot there is no file and there should not be; a caller that
;  printed "settings: the block reader failed" at that moment would send
;  a new owner looking for a fault in their stick.
; ----------------------------------------------------------------------
Procedure.i SettingsLoad()
  Define n.i
  Define got.i

  set_err = #SET_ERR_NONE
  set_fatErr = #HW_FILE_OK

  If HwFileOpen(SettingsFileName()) = 0
    If HwFileLastError() = #HW_FILE_NOTFOUND
      ; The table is emptied even so. A load that fails must not leave
      ; the previous medium's settings in place looking like this one's.
      set_WifiBatchBegin()
      SettingsReset()
      set_WifiBatchEnd()
      set_loadState = 0
      ProcedureReturn set_Fail(#SET_ERR_NO_FILE)
    EndIf
    ProcedureReturn set_FailFat()
  EndIf

  n = HwFileSize()
  If n > #SET_TEXT_MAX
    HwFileClose()
    ProcedureReturn set_Fail(#SET_ERR_TEXT_LONG)
  EndIf

  got = 0
  If n > 0
    got = HwFileReadAt(0, @set_text[0], n)
  EndIf
  HwFileClose()

  If got < 0
    ProcedureReturn set_FailFat()
  EndIf
  If got <> n
    ProcedureReturn set_Fail(#SET_ERR_READ_SHORT)
  EndIf

  ProcedureReturn SettingsParse(@set_text[0], got)
EndProcedure

; ----------------------------------------------------------------------
;  SettingsSave - write the table back to SETTINGS.TXT.
;
;  THE BOARD ARMS ITS OWN WRITER, AND THIS FILE STILL NEVER DOES. The
;  paragraph this replaced said the caller had to install fat.pi4's block
;  writer first, and that with none installed fat.pi4 refused with
;  #FAT_ERR_NO_WRITER - the right default for a library living beside a
;  boot image. The guarantee is unchanged and its enforcement moved one
;  layer down: HwFileWriteAll on the Pi 4 arms the writer around exactly
;  its own one call and disarms it on every path out, so nothing else in
;  the monitor can reach the medium between saves. This file passes a
;  name and some bytes and knows nothing about sectors, which is the
;  whole point of the seam.
;
;  THE ORDER: serialise into the buffer FIRST, and only then go near the
;  medium. A serialisation that fails - the table too big for the buffer
;  - must not have already opened, created or truncated anything. As
;  written, a refused save leaves SETTINGS.TXT byte for byte as it was.
;
;  THE WRITE GATE IS ASKED BEFORE THE FILE IS TOUCHED. HwFileWritable()
;  answers whether this board can write at all right now - on the Pi 4,
;  0 when it came up on the SD card, because writing there is not
;  implemented. Asking first turns "the save failed half way" into "the
;  save was refused and nothing was touched", which is the difference
;  between a settings file and half a settings file.
; ----------------------------------------------------------------------
Procedure.i SettingsSave()
  Define n.i

  set_err = #SET_ERR_NONE
  set_fatErr = #HW_FILE_OK

  ; The partial-load guard. See THE STRICT PARSE in the header - this is
  ; the whole reason set_loadState exists.
  If set_loadState = 2
    ProcedureReturn set_Fail(#SET_ERR_UNSAFE_SAVE)
  EndIf

  n = SettingsSerialise(@set_text[0], #SET_TEXT_MAX)
  If n < 0
    ProcedureReturn 0            ; SettingsSerialise set the code
  EndIf

  If HwFileWritable() = 0
    set_fatErr = #HW_FILE_READONLY
    ProcedureReturn set_Fail(#SET_ERR_FAT)
  EndIf

  ; ONE CALL. The backend creates the file when it is not there, replaces
  ; the contents when it is, and resizes it to match - so nothing here
  ; pads and nothing here truncates by hand. On the Pi 4 that is
  ; FatCreate/FatOverwrite in fat.pi4's own ordering, which bounds an
  ; interrupted save to lost clusters rather than to a volume that will
  ; not mount; on the Q it is a delete-then-create, because UEFI's
  ; Open(CREATE) does not truncate and a shorter write would otherwise
  ; leave the tail of the previous file behind.
  If HwFileWriteAll(SettingsFileName(), @set_text[0], n) = 0
    ProcedureReturn set_FailFat()
  EndIf

  set_dirty = 0
  set_loadState = 1
  ProcedureReturn 1
EndProcedure

Procedure.i SettingsLoadState()
  ProcedureReturn set_loadState
EndProcedure

; The operator saying "yes, throw away the part of the file that was
; never read". The ONLY thing that clears a partial load, and the only
; way past #SET_ERR_UNSAFE_SAVE. Deliberately not called by anything in
; this file.
Procedure SettingsDiscardLoad()
  If set_loadState = 2
    set_loadState = 1
    set_dirty = 1
  EndIf
  set_err = #SET_ERR_NONE
  set_errLine = 0
EndProcedure

; ======================================================================
;  WI-FI. Two named keys and the 802.11 limits that go with them.
;
;  THIS IS NOT A MECHANISM. It is six short procedures over the general
;  store, and they exist for one reason: the limits belong in ONE place
;  and the monitor is not it. A command that invented "8 to 63" from
;  memory would be a second copy of a number whose only real home is
;  RP2350/Lib/cyw43.pico2, and the day the driver's gate changes, one of
;  the two copies would not.
;
;  BOTH LIMITS ARE CITED AND NEITHER IS INVENTED HERE:
;    network name 1..32   #CYW43_SSID_MIN / #CYW43_SSID_MAX,
;                         RP2350/Lib/cyw43.pico2:465-466
;    passphrase   8..63   #CYW43_PASS_MIN / #CYW43_PASS_MAX,
;                         RP2350/Lib/cyw43.pico2:459-460
;
;  And that file is honest that the minimum is ITS gate rather than
;  something either reference driver enforces (cyw43.pico2:454-458), so
;  this is a copy of a rule that is marked UNVERIFIED at its source. Said
;  here so it is not laundered into fact by being repeated.
; ======================================================================

#SET_WIFI_NET_MIN  = 1    ; #CYW43_SSID_MIN, cyw43.pico2:465
#SET_WIFI_NET_MAX  = 32   ; #CYW43_SSID_MAX, cyw43.pico2:466
#SET_WIFI_PASS_MIN = 8    ; #CYW43_PASS_MIN, cyw43.pico2:459
#SET_WIFI_PASS_MAX = 63   ; #CYW43_PASS_MAX, cyw43.pico2:460

Procedure.i SettingsWifiNetworkKey()
  ProcedureReturn "wifi.network"
EndProcedure

; THE WARNING IS IN THE NAME, ON PURPOSE. See THE PASSWORD in the header:
; a warning anywhere else gets separated from the value the first time
; the file is copied, and this one cannot be.
Procedure.i SettingsWifiPasswordKey()
  ProcedureReturn "wifi.password.plaintext"
EndProcedure

Procedure.i SettingsWifiNetwork()
  ProcedureReturn SettingsGet(SettingsWifiNetworkKey())
EndProcedure

Procedure.i SettingsWifiPassword()
  ProcedureReturn SettingsGet(SettingsWifiPasswordKey())
EndProcedure

Procedure.i SettingsSetWifiNetwork(*s)
  Define n.i
  set_err = #SET_ERR_NONE
  If *s = 0
    ProcedureReturn set_Fail(#SET_ERR_NULL)
  EndIf
  n = set_Len(*s)
  If n < #SET_WIFI_NET_MIN Or n > #SET_WIFI_NET_MAX
    ProcedureReturn set_Fail(#SET_ERR_WIFI_NETWORK)
  EndIf
  ProcedureReturn SettingsSet(SettingsWifiNetworkKey(), *s)
EndProcedure

Procedure.i SettingsSetWifiPassword(*s)
  Define n.i
  set_err = #SET_ERR_NONE
  If *s = 0
    ProcedureReturn set_Fail(#SET_ERR_NULL)
  EndIf
  n = set_Len(*s)
  If n < #SET_WIFI_PASS_MIN Or n > #SET_WIFI_PASS_MAX
    ProcedureReturn set_Fail(#SET_ERR_WIFI_PASS)
  EndIf
  ProcedureReturn SettingsSet(SettingsWifiPasswordKey(), *s)
EndProcedure

; ======================================================================
;  WI-FI, MORE THAN ONE NETWORK. THE NUMBERED SLOTS.
; ======================================================================
;  The two keys above hold ONE network. A board that moves - a bench, a
;  bag, somebody's kitchen - needs several, and it needs to be told
;  which to prefer. So there is a second, numbered spelling beside the
;  flat pair:
;
;      wifi.1.ssid               wifi.1.password.plaintext
;      wifi.2.ssid               wifi.2.password.plaintext
;      wifi.3.ssid               wifi.3.password.plaintext
;      wifi.4.ssid               wifi.4.password.plaintext
;
;  THE NUMBER IS THE PREFERENCE ORDER AND THAT IS THE WHOLE POINT OF IT.
;  Slot 1 is tried first, slot 2 second, and so on. It is NOT an
;  arbitrary handle and it is NOT a hash bucket. A joiner walks
;  SettingsWifiNextSlot() from 0 and takes the first network it can see
;  on the air; the operator expresses "prefer the workshop AP over the
;  house one" by putting the workshop AP in the lower-numbered slot and
;  by no other means. Nothing else in this store carries an ordering, so
;  it is said here, in the key names, and again in the monitor's help,
;  because an ordering that is only in one person's head is not one.
;
;  WHY "wifi.N.ssid" AND NOT "wifi.N.network"
;  ------------------------------------------
;  The flat key is "wifi.network" and consistency argues for
;  "wifi.N.network". It was rejected. "network" is the word this file
;  chose in a context where there was exactly one of them and the
;  sentence being written was "the Wi-Fi network"; with four of them the
;  same word starts to read as "network number 3" - the whole
;  connection, address and all - rather than as the name being
;  broadcast. "ssid" is the term on every router's own label, in every
;  phone's settings screen and in 802.11 itself, it is what somebody
;  reading SETTINGS.TXT on a stick will be looking for, and it is four
;  characters against seven in a key name with #SET_KEY_MAX bytes to
;  spend. The flat key keeps its old spelling forever - renaming it
;  would be exactly the silent credential loss this section exists to
;  prevent - so the two spellings sit side by side and the mismatch is
;  documented rather than smoothed over.
;
;  THE PASSPHRASE KEY KEEPS THE FULL "password.plaintext" TAIL, and that
;  is not laziness about symmetry. The warning is IN THE KEY NAME (see
;  THE PASSWORD in the header) and it has to survive being read on a
;  stick by somebody who has never seen this file. Shortening it to
;  "wifi.N.pass" to match "ssid" would have traded the one piece of
;  protection this design actually has for four characters. It also
;  keeps SettingsIsSecret working by the same generic substring rule it
;  always used - "wifi.4.password.plaintext" contains "password" - with
;  no list of names to maintain anywhere.
;
;  KEY LENGTH, CHECKED RATHER THAN ASSUMED
;  ---------------------------------------
;  #SET_KEY_MAX is 31 bytes (settings.pi4:500). The longest key this
;  scheme can generate is the passphrase one:
;
;      "wifi." 5 + two digits 2 + "." 1 + "password.plaintext" 18 = 26
;
;  so even a two-digit slot fits with five bytes to spare, and a
;  one-digit slot - every slot that exists today - is 25. The SSID key
;  is 5 + 2 + 1 + 4 = 12 at worst. Nothing here is close to the limit
;  and set_WifiKey checks anyway, BEFORE it writes a byte, because a
;  refusal that arrives after the damage is not a refusal - that is the
;  lesson the serialiser's own gate mutation taught this file and it is
;  recorded in the header under WHAT WAS ACTUALLY PROVEN.
;
;  WHERE THE LEGACY FLAT PAIR SITS IN THE ORDER, AND WHY
;  -----------------------------------------------------
;  "wifi.network" and "wifi.password.plaintext" ARE STILL READ. A stick
;  written by the build before this one keeps working and nobody's saved
;  passphrase disappears on upgrade. That is a hard requirement and it
;  is the only reason the flat pair still exists.
;
;  THEY ARE CONSULTED LAST - AFTER slot #SET_WIFI_SLOTS - as pseudo-slot
;  #SET_WIFI_LEGACY. Three reasons, and the first decided it:
;
;    * THE NUMBERED SLOTS ARE THE OPERATOR'S STATED PREFERENCE AND THE
;      FLAT PAIR IS NOT A PREFERENCE AT ALL. Somebody who types
;      `wifi ssid 1 Workshop` has said, in the only way this store
;      offers, "try this one first". If the flat pair outranked it, that
;      instruction would be silently ignored on every board that had
;      ever run the old build - which is every board that has
;      credentials worth keeping - and there would be nothing on the
;      console to explain why slot 1 was never tried. A feature that is
;      inert on exactly the machines it was built for is not a feature.
;    * THE GUARANTEE BEING MADE IS A FLOOR, NOT A RANKING. "Your saved
;      network still joins" is delivered in full by a last-resort
;      position: if none of the numbered slots is on the air, the old
;      credentials are used and the board comes up as it did yesterday.
;      Putting them first would buy nothing on top of that.
;    * IT SELF-HEALS AND IT IS VISIBLE. The moment slot 1 holds
;      something reachable the flat pair stops mattering, and until then
;      `wifi` prints it, labelled, at the bottom of the list where its
;      position in the order can be read off the screen.
;
;  THE ALTERNATIVE THAT LOOKS RIGHT AND IS NOT: MIGRATE THE FLAT PAIR
;  INTO SLOT 1 ON LOAD and delete the old keys. Rejected twice over. A
;  load must not change the table behind the operator's back - the whole
;  of THE STRICT PARSE in the header is about the table meaning the
;  file - and a migration on load followed by any later save would
;  rewrite SETTINGS.TXT, deleting two keys nobody asked to lose, as a
;  side effect of an unrelated command. It would also move a value out
;  from under SettingsWifiNetwork()'s existing callers. Migration is the
;  operator's to ask for, one command at a time, and it is nothing more
;  than typing the pair into a slot and then `wifi forget`.
;
;  ALSO REJECTED: PUTTING THE FLAT PAIR FIRST for least surprise - "it
;  worked yesterday in this order, it works today in the same order".
;  There was no order yesterday; a one-element list has nothing to be
;  ahead of. The surprise being avoided is imaginary and the surprise it
;  creates is real.
;
;  WHAT IS NOT HERE
;  ----------------
;    * NO BSSID, NO CHANNEL, NO SECURITY TYPE, NO PRIORITY FIELD. The
;      slot number IS the priority and a second way to say the same
;      thing is a way for the two to disagree. The rest is what the
;      radio discovers by scanning.
;    * NO "LAST USED" OR "AUTO-REORDER". A store that shuffles its own
;      preference order writes to the medium on its own initiative,
;      which this library refuses to do at all (see SAFETY), and it
;      makes the order stop matching what the operator typed.
;    * NO DUPLICATE-SSID CHECK ON SET. Two slots may legitimately hold
;      the same SSID with different passphrases - a network whose key
;      was changed, kept in both spellings until the new one is known
;      good, is an ordinary thing to want. SettingsWifiFindSsid returns
;      the FIRST, which is the preferred one, which is correct.
; ======================================================================

; Bare literals with the arithmetic in the comment - a constant
; initialiser on this compiler cannot contain arithmetic
; (fat.pi4:359-363), the same rule the geometry block at the top of this
; file obeys.
;
; FOUR SLOTS. The budget is #SET_MAX_KEYS = 32 (settings.pi4:499) and
; the arithmetic against it is:
;
;     4 slots * 2 keys each        =  8
;   + the legacy flat pair         =  2   (wifi.network + the passphrase)
;   + the four keys the header
;     names as likely next         =  4   (console baud, autoboot file,
;                                          screen on/off, static IP)
;                                  = 14 of 32, leaving 18 spare
;
; The ceiling, if every other key were given up, would be
; (32 - 2) / 2 = 15 slots. Four is not that number and is not meant to
; be: four is what was asked for, it is a plausible number of networks
; for one board to move between, and eighteen spare keys is the slack
; this store was designed to have. A board that needs fifteen wants a
; different design and not a bigger number here - the same sentence the
; header writes about #SET_MAX_KEYS itself.
#SET_WIFI_SLOTS  = 4

; The pseudo-slot the legacy flat pair answers to: #SET_WIFI_SLOTS + 1,
; so 4 + 1 = 5. It is a slot number so that ONE walk covers everything
; and no caller has to remember to check the old keys afterwards - the
; forgotten-afterthought is precisely how a saved passphrase goes
; missing on upgrade. It is also, by being the highest number, LAST in
; the preference order for free: see the essay above.
;
; It is the highest slot number any read accepts. Writes stop at
; #SET_WIFI_SLOTS - see SettingsSetWifiSlotSsid.
#SET_WIFI_LEGACY = 5

; The two key names are assembled at run time, so they need somewhere to
; live. TWO buffers and not one, because a caller printing both names in
; one sentence - which the monitor does - would otherwise have the
; second call overwrite the first name while its address was still being
; held. One shared buffer would work for every caller that uses one at a
; time and fail for the one that does not, which is the worst kind of
; sharing.
;
; #SET_KEY_STRIDE is 32 (settings.pi4:501) and the longest name built
; here is 26 bytes plus a NUL - see KEY LENGTH above.
Global Dim set_wifiSsidKey.a[#SET_KEY_STRIDE]
Global Dim set_wifiPassKey.a[#SET_KEY_STRIDE]

; ----------------------------------------------------------------------
;  set_WifiKey - assemble "wifi." + the slot number + "." + *tail into
;  *dst, and return *dst. 0 if it would not fit.
;
;  THE FIXED PARTS ARE STRING LITERALS AND THE DIGITS ARE NUMBERS. This
;  language has no character literals (see the ASCII block at the top of
;  this file), so the one byte that cannot come from a literal - the
;  digit - is computed from #SET_CH_DIGIT0, which is 48 and is named
;  there as '0'.
;
;  TWO DIGITS ARE HANDLED even though #SET_WIFI_SLOTS is 4 and only one
;  is ever produced today. Not speculation: the constant above is the
;  only thing that decides how many slots there are, and a key builder
;  that quietly produced "wifi.1.ssid" for slot 11 would turn raising it
;  into a silent collision between two slots rather than a compile-time
;  or a run-time refusal. Nine lines to make the constant genuinely the
;  only place the number lives.
;
;  THE LENGTH IS CHECKED BEFORE ANY BYTE IS WRITTEN. The destination is
;  one of this file's own 32-byte arrays and the worst case is 26, so
;  this can never fire - which is exactly why it is here rather than
;  after the copy. A bounds check that runs after the write reports the
;  overflow correctly and has already caused it; that mutation escaped
;  this file's gate once and the header records it.
; ----------------------------------------------------------------------
Procedure.i set_WifiKey(*dst, slot.i, *tail)
  Define at.i
  Define n.i
  Define i.i
  Define d.i
  Define *head

  ; The head is a literal rather than five numbers, because the house
  ; rule bans CHARACTER literals and this file already spells its key
  ; names as strings - SettingsWifiNetworkKey returns "wifi.network".
  ; Its length is measured rather than written as 5, so the two can
  ; never disagree.
  *head = "wifi."

  ; head + the dot after the number + the tail, plus one or two digits.
  ; Worked out first, against #SET_KEY_MAX, and refused here rather than
  ; part way through the copy.
  n = set_Len(*head) + 1 + set_Len(*tail)
  If slot >= 10
    n = n + 2
  Else
    n = n + 1
  EndIf
  If n > #SET_KEY_MAX
    ProcedureReturn 0
  EndIf

  at = 0
  n = set_Len(*head)
  i = 0
  While i < n
    PokeA(*dst + at + i, PeekA(*head + i))
    i = i + 1
  Wend
  at = at + n

  If slot >= 10
    d = slot / 10
    PokeA(*dst + at, #SET_CH_DIGIT0 + d)   ; 48 = '0', named at the top
    at = at + 1
  EndIf
  d = slot % 10
  PokeA(*dst + at, #SET_CH_DIGIT0 + d)
  at = at + 1

  PokeA(*dst + at, #SET_CH_DOT)            ; 46 = '.', named at the top
  at = at + 1

  i = 0
  n = set_Len(*tail)
  While i < n
    PokeA(*dst + at + i, PeekA(*tail + i))
    i = i + 1
  Wend
  at = at + n

  PokeA(*dst + at, 0)
  ProcedureReturn *dst
EndProcedure

; The maximum slot number - the named constant and nothing else, so no
; caller ever writes 4.
Procedure.i SettingsWifiSlots()
  ProcedureReturn #SET_WIFI_SLOTS
EndProcedure

; The pseudo-slot the legacy flat pair answers to, and the highest
; number a read or a walk will visit. See the essay above for why it is
; the highest and not the lowest.
Procedure.i SettingsWifiLegacySlot()
  ProcedureReturn #SET_WIFI_LEGACY
EndProcedure

; ----------------------------------------------------------------------
;  The two key names for a slot. 0 for a slot number this store does not
;  keep.
;
;  #SET_WIFI_LEGACY RETURNS THE FLAT NAMES, not a built one. That is the
;  whole trick that makes the old pair a slot: every reader below goes
;  through these two procedures, so the legacy keys are read by the same
;  code path as the numbered ones and there is no second path to forget
;  about.
; ----------------------------------------------------------------------
Procedure.i SettingsWifiSlotSsidKey(slot.i)
  If slot = #SET_WIFI_LEGACY
    ProcedureReturn SettingsWifiNetworkKey()
  EndIf
  If slot < 1 Or slot > #SET_WIFI_SLOTS
    ProcedureReturn 0
  EndIf
  ProcedureReturn set_WifiKey(@set_wifiSsidKey[0], slot, "ssid")
EndProcedure

Procedure.i SettingsWifiSlotPasswordKey(slot.i)
  If slot = #SET_WIFI_LEGACY
    ProcedureReturn SettingsWifiPasswordKey()
  EndIf
  If slot < 1 Or slot > #SET_WIFI_SLOTS
    ProcedureReturn 0
  EndIf
  ; The tail keeps the word "password" in it on purpose. SettingsIsSecret
  ; masks on that substring (settings.pi4:1146-1170) and this is what
  ; makes every numbered passphrase inherit the masking with no list of
  ; key names anywhere.
  ProcedureReturn set_WifiKey(@set_wifiPassKey[0], slot, "password.plaintext")
EndProcedure

; ----------------------------------------------------------------------
;  Reading a slot. The address of the value, or 0 when the slot is empty
;  or does not exist.
;
;  AN EMPTY SLOT IS NOT AN ERROR AND MUST NOT LEAVE ONE BEHIND. Walking
;  four slots to find the two that are populated is the normal use of
;  this API, and #SET_ERR_NOTFOUND left in set_err by the two misses
;  would poison the next SettingsErrorText() the monitor happened to
;  print - the same argument SettingsHas makes at settings.pi4:1035.
;  So the error is saved and put back, and the ONLY thing these two set
;  is #SET_ERR_WIFI_SLOT, for a slot number that does not exist, which
;  IS a caller mistake and is worth a sentence.
; ----------------------------------------------------------------------
Procedure.i SettingsWifiSlotSsid(slot.i)
  Define save.i
  Define *k
  Define *v
  *k = SettingsWifiSlotSsidKey(slot)
  If *k = 0
    ProcedureReturn set_Fail(#SET_ERR_WIFI_SLOT)
  EndIf
  save = set_err
  *v = SettingsGet(*k)
  set_err = save
  ProcedureReturn *v
EndProcedure

Procedure.i SettingsWifiSlotPassword(slot.i)
  Define save.i
  Define *k
  Define *v
  *k = SettingsWifiSlotPasswordKey(slot)
  If *k = 0
    ProcedureReturn set_Fail(#SET_ERR_WIFI_SLOT)
  EndIf
  save = set_err
  *v = SettingsGet(*k)
  set_err = save
  ProcedureReturn *v
EndProcedure

; ----------------------------------------------------------------------
;  Writing a slot. THE NUMBERED SLOTS ONLY - #SET_WIFI_LEGACY IS READ
;  ONLY THROUGH THIS API.
;
;  The flat pair can still be written, by SettingsSetWifiNetwork and
;  SettingsSetWifiPassword, which are untouched and which existing
;  callers use. What must not happen is this API MANUFACTURING a legacy
;  key: a monitor command that let somebody type `wifi ssid 5 Whatever`
;  would create the old flat key on a stick that never had one, put it
;  last in the preference order, and leave it there for the next person
;  to wonder about. New credentials belong in numbered slots.
;
;  THE LIMITS ARE #SET_WIFI_NET_MIN/MAX AND #SET_WIFI_PASS_MIN/MAX - the
;  same four constants SettingsSetWifiNetwork and SettingsSetWifiPassword
;  use (settings.pi4:1702-1705, themselves cited to cyw43.pico2:459-466).
;  Retyping "1..32" and "8..63" here would be a second copy of a number
;  whose only real home is the driver's gate, and the day that gate moves
;  one of the two copies would not - which is the entire argument the
;  WI-FI section above makes for these procedures existing at all.
; ----------------------------------------------------------------------
Procedure.i SettingsSetWifiSlotSsid(slot.i, *s)
  Define n.i
  set_err = #SET_ERR_NONE
  If slot < 1 Or slot > #SET_WIFI_SLOTS
    ProcedureReturn set_Fail(#SET_ERR_WIFI_SLOT)
  EndIf
  If *s = 0
    ProcedureReturn set_Fail(#SET_ERR_NULL)
  EndIf
  n = set_Len(*s)
  If n < #SET_WIFI_NET_MIN Or n > #SET_WIFI_NET_MAX
    ProcedureReturn set_Fail(#SET_ERR_WIFI_NETWORK)
  EndIf
  ProcedureReturn SettingsSet(SettingsWifiSlotSsidKey(slot), *s)
EndProcedure

Procedure.i SettingsSetWifiSlotPassword(slot.i, *s)
  Define n.i
  set_err = #SET_ERR_NONE
  If slot < 1 Or slot > #SET_WIFI_SLOTS
    ProcedureReturn set_Fail(#SET_ERR_WIFI_SLOT)
  EndIf
  If *s = 0
    ProcedureReturn set_Fail(#SET_ERR_NULL)
  EndIf
  n = set_Len(*s)
  If n < #SET_WIFI_PASS_MIN Or n > #SET_WIFI_PASS_MAX
    ProcedureReturn set_Fail(#SET_ERR_WIFI_PASS)
  EndIf
  ProcedureReturn SettingsSet(SettingsWifiSlotPasswordKey(slot), *s)
EndProcedure

; ----------------------------------------------------------------------
;  SettingsRemoveWifiSlot - take a whole slot out. 1 if anything was
;  actually removed, 0 if the slot was already empty or does not exist.
;
;  BOTH KEYS GO, and the passphrase is removed even when the SSID was
;  the only thing set, and the other way round. A half-removed slot -
;  a passphrase with no name against it - is a credential sitting in the
;  file for a network nobody can see is being kept.
;
;  IT ACCEPTS #SET_WIFI_LEGACY. Removing is not manufacturing: this is
;  how an operator who has copied the old pair into a numbered slot gets
;  rid of it, and refusing them that would leave the only migration path
;  running through `settings remove` and two key names typed by hand.
; ----------------------------------------------------------------------
Procedure.i SettingsRemoveWifiSlot(slot.i)
  Define did.i
  Define *k

  set_err = #SET_ERR_NONE
  If slot < 1 Or slot > #SET_WIFI_LEGACY
    ProcedureReturn set_Fail(#SET_ERR_WIFI_SLOT)
  EndIf

  did = 0

  *k = SettingsWifiSlotSsidKey(slot)
  If SettingsHas(*k) = 1
    If SettingsRemove(*k) = 1
      did = 1
    EndIf
  EndIf

  ; The key is rebuilt rather than held from above, because
  ; SettingsWifiSlotSsidKey and SettingsWifiSlotPasswordKey write into
  ; two DIFFERENT buffers and holding one across a call to the other is
  ; the exact mistake the two-buffer decision was made to prevent. It is
  ; free here and it keeps the rule true everywhere.
  *k = SettingsWifiSlotPasswordKey(slot)
  If SettingsHas(*k) = 1
    If SettingsRemove(*k) = 1
      did = 1
    EndIf
  EndIf

  ; SettingsRemove leaves #SET_ERR_NOTFOUND behind on a miss and no miss
  ; here is a caller mistake - an empty half of a slot is an ordinary
  ; thing to find. Cleared, so it cannot poison the next
  ; SettingsErrorText() the monitor prints. Every path that reaches this
  ; line has a legal slot number, so there is no code worth keeping.
  set_err = #SET_ERR_NONE

  ProcedureReturn did
EndProcedure

; ----------------------------------------------------------------------
;  A SLOT IS POPULATED WHEN IT HAS AN SSID. Not when it has a
;  passphrase: a passphrase with no network name against it names no
;  network and a joiner cannot do anything with it. An open network with
;  a name and no passphrase is a real thing and this store can hold it,
;  so the SSID is the one that decides.
; ----------------------------------------------------------------------
Procedure.i SettingsWifiSlotUsed(slot.i)
  Define save.i
  Define r.i
  save = set_err
  r = 0
  If SettingsWifiSlotSsid(slot) <> 0
    r = 1
  EndIf
  set_err = save
  ProcedureReturn r
EndProcedure

; ----------------------------------------------------------------------
;  SettingsWifiNextSlot - walk the populated slots IN PREFERENCE ORDER.
;
;      s = SettingsWifiNextSlot(0)
;      While s <> 0
;        ... SettingsWifiSlotSsid(s) ...
;        s = SettingsWifiNextSlot(s)
;      Wend
;
;  Returns the lowest populated slot strictly greater than `after`, or 0
;  when there are no more. Starting from 0 therefore walks the whole
;  list, and #SET_WIFI_LEGACY comes out last because it is the highest
;  number - see WHERE THE LEGACY FLAT PAIR SITS above.
;
;  A CURSOR AND NOT AN ARRAY. The alternative was to fill a caller's
;  buffer with the populated slot numbers in one call. Rejected: it
;  needs a buffer and a maximum at every call site, it goes stale the
;  moment anything is set, and it says nothing this does not. A cursor
;  reads the table each time, so a caller that sets something mid-walk
;  sees the table as it now is rather than as it was.
; ----------------------------------------------------------------------
Procedure.i SettingsWifiNextSlot(after.i)
  Define s.i
  s = after + 1
  If s < 1
    s = 1
  EndIf
  While s <= #SET_WIFI_LEGACY
    If SettingsWifiSlotUsed(s) = 1
      ProcedureReturn s
    EndIf
    s = s + 1
  Wend
  ProcedureReturn 0
EndProcedure

; How many slots hold an SSID, legacy pseudo-slot included. For a
; monitor that wants to print "3 networks stored" before the list.
Procedure.i SettingsWifiSlotCount()
  Define n.i
  Define s.i
  n = 0
  s = SettingsWifiNextSlot(0)
  While s <> 0
    n = n + 1
    s = SettingsWifiNextSlot(s)
  Wend
  ProcedureReturn n
EndProcedure

; ----------------------------------------------------------------------
;  set_SameZ - two NUL-terminated strings, BYTE FOR BYTE, length
;  included. 1 if they are the same.
;
;  THIS IS NOT set_MakeKey's COMPARISON AND MUST NOT BECOME IT. Keys are
;  case-folded because a key is a name this project chose and two
;  spellings of it are a bug. An SSID is a name somebody else chose, off
;  a router label, and the bytes are the whole of it.
; ----------------------------------------------------------------------
Procedure.i set_SameZ(*a, *b)
  Define i.i
  Define x.i
  Define y.i
  If *a = 0 Or *b = 0
    ProcedureReturn 0
  EndIf
  i = 0
  While i <= #SET_VAL_MAX
    x = PeekA(*a + i)
    y = PeekA(*b + i)
    If x <> y
      ProcedureReturn 0
    EndIf
    If x = 0
      ProcedureReturn 1      ; both ended at the same byte
    EndIf
    i = i + 1
  Wend
  ; Neither string terminated inside #SET_VAL_MAX + 1 bytes. Nothing
  ; this store holds can do that - set_CheckValue refuses a longer
  ; value - so the only way here is a caller's unterminated buffer, and
  ; "not equal" is the safe answer to give it.
  ProcedureReturn 0
EndProcedure

; ----------------------------------------------------------------------
;  SettingsWifiFindSsid - which slot holds this network name. The slot
;  number, or 0 if no slot does.
;
;  THE COMPARISON IS BYTE-EXACT, INCLUDING LENGTH. It does NOT case-fold
;  and it does NOT normalise anything - no trimming, no stripping of a
;  band suffix, no Unicode anything. That is a deliberate refusal and it
;  is the single most important line in this section, because the real
;  networks this board sits among are distinguished from each other by
;  exactly the differences a "helpful" comparison would erase:
;
;    * TWO OF THE SAVED PROFILES DIFFER BY ONE LETTER. Fold or fuzz the
;      comparison and the board joins the wrong one of them, with the
;      right passphrase for the other, and reports a passphrase failure
;      against a network name that is on the screen and looks correct.
;    * ONE DIFFERS FROM ANOTHER ONLY BY A "2.4ghz" SUFFIX. Those are two
;      radios, usually two bands of the same access point, and they are
;      not interchangeable - a board with no 5 GHz radio that is handed
;      the 5 GHz profile because a suffix was stripped will scan forever
;      and never see it.
;
;  802.11 itself treats an SSID as an opaque byte string and says
;  nothing about case, so byte-exact is also simply the correct reading
;  of the standard. Both halves of that are worth having written down:
;  the correctness argument is why this will not be changed on a whim,
;  and the two concrete networks above are why it would hurt if it were.
;
;  THE FIRST MATCH WINS, and because the walk runs 1, 2, ... and then
;  #SET_WIFI_LEGACY, "first" means "most preferred". Two slots holding
;  the same SSID with different passphrases is legal (see WHAT IS NOT
;  HERE above) and this is the half of that decision that makes it
;  useful.
;
;  IT SETS NO ERROR, for the same reason SettingsHas sets none: asking
;  whether a network is known is not a mistake when it is not.
; ----------------------------------------------------------------------
Procedure.i SettingsWifiFindSsid(*ssid)
  Define save.i
  Define s.i
  Define *v
  Define found.i

  save = set_err
  found = 0

  If *ssid <> 0
    s = 1
    While s <= #SET_WIFI_LEGACY
      *v = SettingsWifiSlotSsid(s)
      If *v <> 0
        If set_SameZ(*v, *ssid) = 1
          found = s
          Break
        EndIf
      EndIf
      s = s + 1
    Wend
  EndIf

  set_err = save
  ProcedureReturn found
EndProcedure

; ======================================================================
;  WHY IT REFUSED
; ======================================================================

Procedure.i SettingsLastError()
  ProcedureReturn set_err
EndProcedure

Procedure.i SettingsErrorLine()
  ProcedureReturn set_errLine
EndProcedure

Procedure.i SettingsFatError()
  ProcedureReturn set_fatErr
EndProcedure

; ======================================================================
;  SettingsErrorText - the address of a NUL-terminated English sentence
;  for SettingsLastError().
;
;  Print it with whatever PutS the MAIN file's UART library provides.
;  Full sentences, whole words, no codes in the text - the bench's
;  style directive of 2026-08-26 - and the text names WHAT WAS FOUND
;  rather than what to do about it, which is fat.pi4's rule
;  (fat.pi4:4336-4339) and is right for the same reason: a library that
;  guessed at fixes in a string would be wrong out loud.
;
;  The one exception is #SET_ERR_UNSAFE_SAVE, which DOES name the way
;  past it, because the way past it is a command that exists only for
;  that purpose and there is no other way anybody would find it.
; ======================================================================
Procedure.i SettingsErrorText()
  Select set_err
    Case #SET_ERR_NONE
      ProcedureReturn "settings: ok"
    Case #SET_ERR_NULL
      ProcedureReturn "settings: a null pointer was given where a name or a value was expected"
    Case #SET_ERR_NO_KEY
      ProcedureReturn "settings: there is no name to the left of the equals sign"
    Case #SET_ERR_KEY_LONG
      ProcedureReturn "settings: that name is longer than thirty-one characters"
    Case #SET_ERR_KEY_CHAR
      ProcedureReturn "settings: a name may only contain letters, digits, a dot, a dash and an underscore"
    Case #SET_ERR_VALUE_LONG
      ProcedureReturn "settings: that value is longer than ninety-five characters"
    Case #SET_ERR_VALUE_CHAR
      ProcedureReturn "settings: a value may only contain ordinary printable characters, and that one does not"
    Case #SET_ERR_VALUE_EDGE
      ProcedureReturn "settings: a value may not begin or end with a space, because a space there would be lost when the file is read back"
    Case #SET_ERR_FULL
      ProcedureReturn "settings: all thirty-two slots are in use - remove a setting before adding another"
    Case #SET_ERR_NOTFOUND
      ProcedureReturn "settings: there is no setting by that name"
    Case #SET_ERR_SYNTAX
      ProcedureReturn "settings: that line has no equals sign on it, so it is neither a comment nor a setting"
    Case #SET_ERR_TEXT_LONG
      ProcedureReturn "settings: the settings file is larger than this monitor will read"
    Case #SET_ERR_NO_FILE
      ProcedureReturn "settings: there is no settings file on this medium yet, which is normal until the first save"
    Case #SET_ERR_FAT
      ProcedureReturn "settings: the filesystem refused - the next line says what it found"
    Case #SET_ERR_READ_SHORT
      ProcedureReturn "settings: the settings file ended before the directory said it would"
    Case #SET_ERR_UNSAFE_SAVE
      ProcedureReturn "settings: the last load stopped at a bad line, so saving now would delete every line after it. Discard the rest of that file first if that is what you want"
    Case #SET_ERR_BAD_LEN
      ProcedureReturn "settings: a negative length"
    Case #SET_ERR_WIFI_NETWORK
      ProcedureReturn "settings: a Wi-Fi network name must be between one and thirty-two characters"
    Case #SET_ERR_WIFI_PASS
      ProcedureReturn "settings: a Wi-Fi password must be between eight and sixty-three characters"
    Case #SET_ERR_WIFI_SLOT
      ; The two numbers are spelled out and the sentence names WHAT WAS
      ; FOUND rather than what to do, which is this file's rule. It has
      ; to mention that the last one is the old single-network pair,
      ; though, because a slot number one past the end that reads and
      ; will not be written to is otherwise inexplicable.
      ProcedureReturn "settings: Wi-Fi networks are kept in slots numbered one to four, and slot five is the older single-network pair, which can be read and removed but not set"
  EndSelect
  ProcedureReturn "settings: unknown error code"
EndProcedure
