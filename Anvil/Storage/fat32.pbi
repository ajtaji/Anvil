; ======================================================================
; FAT32 for the Raspberry Pi 4 - library, not a compiler builtin.
; READ AND WRITE.
; ----------------------------------------------------------------------
; This is the thing U-Boot does that the monitor could not: take a name
; off the boot medium and put its bytes in RAM.
;
;     fatload usb 0:1 0x200000 pmf.img
;
; becomes
;
;     FatSetBlockReader(@SdReadBlock)
;     FatMount(1)
;     FatOpen("PMF.IMG")
;     n = FatRead($200000, FatSize())
;     FatClose()
;
; and, since 2026-08-26, the other direction as well:
;
;     FatSetBlockWriter(@MscWriteBlock)
;     FatOpen("PMF.IMG")            ; or FatCreate("PMF.IMG")
;     FatOverwrite($200000, n)      ; ANY n. It resizes.
;     FatSetBlockWriter(0)          ; and then it cannot write again
;
; MBR partition, FAT32 boot sector, root directory, 8.3 short names,
; cluster chain, bytes out - and bytes in, cluster allocation, file
; extension and truncation, file creation, deletion and FSInfo. No
; subdirectories and no long filenames. Both of those absences are a
; refusal with its own error code, not a silent half-answer.
;
; THIS FILE WAS A LOADER AND IS NOW A FILESYSTEM. Read the WRITING
; section below before changing any of the second half: the read half's
; five traps are all still live, and the write half adds a rule about
; the ORDER of writes that is the only thing standing between an
; interrupted save and a volume that will not mount.
;
; ======================================================================
; USE - this file names no other file (house rule: a library never
; includes a library). The MAIN program lists what it needs:
;
;     XIncludeFile "RaspberryPi4/Lib/uart.pi4"     ; to PRINT the reason
;     XIncludeFile "RaspberryPi4/Lib/mailbox.pi4"  ; for the base clock
;     XIncludeFile "RaspberryPi4/Lib/emmc.pi4"     ; the blocks
;     XIncludeFile "RaspberryPi4/Lib/fat.pi4"
;
;     MailboxInit()
;
;     ; THE EMMC BASE CLOCK IS 250000000 Hz ON THIS BOARD - min = max =
;     ; 250 MHz, MEASURED from the VideoCore mailbox on real hardware on
;     ; 2026-08-25, not taken from a document and not guessed. emmc.pi4
;     ; refuses with #SD_ERR_BASECLK rather than inventing a number, and
;     ; SdSetBaseClockKhz() is how a caller supplies it. kHz, so 250000.
;     SdSetBaseClockKhz(250000)
;
;     If SdInit() = 0
;       PutS(SdErrorText()) : ProcedureReturn
;     EndIf
;
;     ; THE ONE LINE THAT JOINS THE TWO FILES. See "THE BLOCK READER"
;     ; below - fat.pi4 has no idea emmc.pi4 exists until this runs.
;     FatSetBlockReader(@SdReadBlock)
;
;     If FatMount(1) = 0
;       PutS(FatErrorText()) : ProcedureReturn
;     EndIf
;     If FatOpen("PMF.IMG") = 0
;       PutS(FatErrorText()) : ProcedureReturn
;     EndIf
;     got = FatRead($200000, FatSize())
;     If got < 0
;       PutS(FatErrorText()) : ProcedureReturn
;     EndIf
;     FatClose()
;
; ======================================================================
; THE BLOCK READER - THE SEAM, AND WHY IT EXISTS
; ======================================================================
; This file never calls SdReadBlock. It calls whatever address was
; handed to FatSetBlockReader(), through a variable:
;
;     Global *fat_reader                ; a procedure address, or 0
;     ok = fat_reader(lba, *buf)        ; an indirect call
;
; THE '*' IN THAT DECLARATION IS LOAD-BEARING AND IT COST A BUILD. The
; compiler refuses to compile a call through a plain ".i" variable
; unless it can SEE an "x = @Something" assignment somewhere - the guard
; that was added after a TLS bring-up wrote Tls13State() for a global
; and branched to address $3. That guard cannot see through
; FatSetBlockReader(), whose assignment is from a PARAMETER, so
; "Global fat_reader.i" stops the build with "is a VARIABLE, not a
; procedure". A name declared with '*' already holds an address by
; declaration and is exempt, which is the right exemption and the right
; spelling: this variable IS a pointer.
;
; The other half of that spelling, also learned the hard way: the call
; is written "fat_reader(...)" with NO star. "*fat_reader(lba, *buf)"
; compiles clean and means something else entirely - it DEREFERENCES
; the call's return value. It emitted an extra "ldr x12, [x11]" after
; the blr and turned a returned 1 into whatever is at address 1. Read
; the value as "*fat_reader"; call it as "fat_reader(...)".
;
; THE CONTRACT, and it is exactly SdReadBlock's so that @SdReadBlock can
; be passed with nothing in between:
;
;     Procedure.i Reader(lba.i, *buf)
;        reads ONE 512-byte block at logical block address lba into
;        *buf, which is 512 bytes long and 4-BYTE ALIGNED.
;        Returns 1 on success, 0 on failure.
;
; THREE REASONS IT IS BUILT THIS WAY, in order of how much they matter:
;
;   1. IT IS THE ONLY WAY THIS PARSER CAN BE TESTED. There is no SD card
;      in this machine and there never has been while any of this was
;      written; emmc.pi4's own header says no card has ever answered a
;      command. A filesystem parser wired directly to a driver that has
;      never moved a byte is a file that cannot be proven at all. With
;      the seam, a fabricated FAT32 image in memory is a first-class
;      medium and the parser gets a real test today. See "WHAT WAS
;      ACTUALLY PROVEN" below - that is not a footnote, it is the reason
;      the indirection is in the API rather than hidden inside.
;
;   2. THE BOOT MEDIUM ON THIS BENCH IS NOT THE SD CARD. The monitor is
;      replacing a U-Boot that loads from a USB stick - PCIe, XHCI, mass
;      storage. When a USB block source exists it becomes one more
;      procedure of the same shape and NOT ONE LINE OF THIS FILE
;      CHANGES. Hard-wiring SdReadBlock would have made the filesystem
;      an SD-only filesystem for no reason.
;
;   3. A LIBRARY NEVER INCLUDES A LIBRARY. Calling SdReadBlock by name
;      would mean fat.pi4 could only ever be compiled beside emmc.pi4.
;
; WHAT THE SEAM COSTS, stated plainly:
;
;   * THE ARITY OF AN INDIRECT CALL IS NOT CHECKED. The compiler checks
;     argument counts against a Procedure's declaration; a call through
;     a variable has no declaration to check against, so a reader with
;     the wrong signature is a silent wrong answer. There is one right
;     shape and it is written above.
;   * THE READER MUST NOT CALL BACK INTO THIS FILE. Parameters lower to
;     fixed global slots on this target - see [[Calling convention]] -
;     so re-entering a procedure that is already running overwrites its
;     own arguments. A reader that called FatRead would corrupt the read
;     that called it.
;   * FatMount() REFUSES with #FAT_ERR_NO_READER if no reader was set.
;     A default of "probably the SD card" is exactly the guess this
;     project keeps paying for.
;
; Indirect calls were CHECKED on this backend before the API was chosen,
; not assumed: a two-argument call through a variable, compiled for
; -t pi4 and executed under tools/a64/a64_interp.py, returned the same
; value as the direct call.
;
; ======================================================================
; FAT32 ONLY. FAT12 AND FAT16 ARE REFUSED BY NAME.
; ======================================================================
; A Pi boot partition is FAT32, so FAT32 is what this implements. The
; other two are not half-implemented and not silently mis-read: the type
; is DETERMINED, then FAT12 and FAT16 stop with #FAT_ERR_FAT12 and
; #FAT_ERR_FAT16, and FatType() still reports 12 or 16 so the caller can
; say what it found rather than "mount failed".
;
; HOW THE TYPE IS DETERMINED, and this is the one part of FAT that is
; most often got wrong: BY CLUSTER COUNT, NEVER BY THE TYPE STRING.
;
;     RootDirSectors  = ((RootEntCnt * 32) + (BytsPerSec - 1)) / BytsPerSec
;     FATSz           = FATSz16 if nonzero else FATSz32
;     TotSec          = TotSec16 if nonzero else TotSec32
;     DataSec         = TotSec - (RsvdSecCnt + NumFATs*FATSz + RootDirSectors)
;     CountofClusters = DataSec / SecPerClus
;
;     CountofClusters < 4085   -> FAT12
;     CountofClusters < 65525  -> FAT16
;     otherwise                -> FAT32
;
; That ladder is from the Microsoft FAT specification (fatgen103,
; "Determination of FAT type"), WHICH IS NOT ON THIS DISK - see "WHERE
; THE LAYOUT CAME FROM" below. The same document says in as many words
; that the "FAT32   " string at offset $52 of the boot sector, and the
; "FAT16   " string at $36, are for display only and must not be used to
; decide the type. This file therefore never reads either of them. The
; boundaries are OFF-BY-ONE TRAPS and they are asserted rather than
; reasoned about: 65525 clusters is FAT32 and 65524 clusters is FAT16,
; and the test builds one image of each.
;
; ======================================================================
; NO LONG FILENAMES, AND THAT IS ENOUGH FOR THE JOB
; ======================================================================
; The file the monitor wants is called something like PMF.IMG or
; KERNEL8.IMG. Both fit 8.3 exactly, which is what a boot partition has
; always used, so VFAT long-name support would buy nothing here and
; costs a UCS-2 decoder and a checksum.
;
; WHAT THIS FILE DOES ABOUT LFN, because ignoring it is not an option:
; a long name is stored as a run of entries with DIR_Attr = $0F sitting
; IMMEDIATELY BEFORE the real 8.3 entry, and their bytes are name
; fragments, not a directory entry. This file SKIPS every $0F entry, so
; a file with a long name is still found by its short name. What it
; cannot do is find it by the long one - FatOpen("verylongname.img")
; refuses with #FAT_ERR_NAME because that string is not expressible in
; 8.3, rather than searching and reporting "not found", which would send
; somebody looking for the file instead of for the feature.
;
; NAMES ARE UPPERCASED. 8.3 entries are stored uppercase; FatOpen
; accepts "pmf.img" and matches PMF.IMG. The NT lowercase-display flags
; at DIR_NTRes ($0C) are ignored, because they change how a name is
; PRINTED, not what it matches.
;
; ======================================================================
; THE FIVE THINGS THAT BITE, AND WHERE EACH ONE IS HANDLED
; ======================================================================
;
; 1. THE PARTITION OFFSET IS IN SECTORS AND EVERYTHING IS RELATIVE TO IT
;
;    Get this wrong and nothing fails - the boot sector is read from the
;    wrong place, the numbers in it are plausible, and the file comes
;    back as garbage that looks like corruption.
;
;    fat_partLba becomes an absolute sector number in exactly FOUR
;    places, all of them inside FatMount: the boot sector's own read,
;    fat_fatLba, fat_dataLba, and - since the write half landed -
;    fat_fsinfoLba, in fat_ReadFsInfo. After FatMount returns, nothing
;    in this file adds it to anything ever again. Every sector number
;    that leaves this file for the block reader OR THE BLOCK WRITER is
;    already absolute. That is the whole defence: a relative number and
;    an absolute number cannot be confused if only one kind exists past
;    the mount.
;
;    IT USED TO SAY THREE AND THE COUNT IS KEPT HONEST DELIBERATELY.
;    fat_fatBase, fat_fatEnd and fat_dataEnd - the write fence's posts -
;    are all DERIVED by subtraction and addition from the three that
;    already existed, specifically so that they would not become a fifth
;    and a sixth. FSInfo could not be: its sector number is relative to
;    the volume, like every other BPB field, so the addition is real.
;    Rewriting it as some derivation of fat_fatLba to keep the sentence
;    saying "three" would have been the kind of tidy that costs a
;    weekend.
;
;    The test's image deliberately puts the partition at LBA 63 rather
;    than at 0, and asserts FatFatLba(), FatDataLba() and the LBA the
;    reader was actually asked for when a read was made to fail. An
;    image whose partition began at 0 would pass with the addition
;    missing. Deleting the addition from fat_dataLba was run as a
;    negative control: 47 of 155 assertions fail, the file's first byte
;    among them.
;
; 2. THE FAT IS LITTLE-ENDIAN AND ITS FIELDS ARE NOT ALIGNED
;
;    EVERY multi-byte field in this file is assembled from single bytes,
;    little end first, by fat_U16 and fat_U32. There is not one 32-bit
;    load of on-disk data anywhere.
;
;    THIS IS NOT THEORETICAL. The MBR partition table starts at offset
;    $1BE, which is 2 modulo 4, so EVERY 32-bit field in EVERY partition
;    entry is at a 2-modulo-4 offset: the start LBA of partition 1 is at
;    $1C6 and its sector count at $1CA. A 32-bit load of either is
;    unaligned by construction, on a buffer whose own base says nothing
;    about it. Assembling from bytes removes the question instead of
;    answering it per-field.
;
;    AND THE BYTES ARE UNSIGNED. PeekB/PeekW/PeekL SIGN-EXTEND on this
;    target (ruled 2026-08-25); PeekA/PeekU/PeekN are the unsigned
;    spellings. Every byte read off a medium is raw data, so every read
;    in this file is PeekA. A PeekB on a byte of $F8 - which is what the
;    top byte of an end-of-chain marker is - would give -8, and -8
;    shifted left 24 and OR-ed into a cluster number puts that cluster
;    somewhere else entirely. PeekN is the right spelling for a 32-bit
;    field WHEN a 32-bit load is what you want; here it never is, for
;    the alignment reason above.
;
; 3. A CLUSTER CHAIN CAN LOOP
;
;    A corrupt - or hostile - filesystem can point cluster 5 at cluster
;    6 and cluster 6 back at cluster 5. Walking that is an infinite
;    loop, and an infinite loop in a bootloader is a board that has to
;    be power-cycled with no message.
;
;    EVERY chain walk in this file is bounded by fat_clusterCount, the
;    volume's own total cluster count, and refuses past it: a chain
;    longer than the number of clusters that exist must, by the
;    pigeonhole principle, have visited one twice. Two counters, because
;    there are two chains - fat_dirSteps for the root directory and
;    fat_fileSteps for the open file - refusing with #FAT_ERR_DIRLOOP
;    and #FAT_ERR_CHAINLOOP so the report says WHICH walk it was.
;
;    fat_fileSteps is cumulative across FatRead calls and is reset by
;    FatOpen, not by FatRead. A per-call bound would be no bound at all
;    for a caller that reads a file in small pieces.
;
;    BUT THE COUNT IS NOT THE WHOLE ANSWER, AND SAYING SO IS THE POINT.
;    The two walks are not equally exposed, and it is worth being exact
;    rather than reassuring:
;
;    THE DIRECTORY WALK REALLY CAN SPIN FOREVER. Nothing bounds it but
;    the chain itself: the scan stops at a $00 entry or at end of chain,
;    and a looping directory whose clusters contain no $00 entry has
;    neither. fat_dirSteps is the only thing between that volume and a
;    hung board. It is tested against a root directory that points at
;    itself.
;
;    THE FILE WALK CANNOT SPIN, and a counter alone would never fire on
;    it. FatRead stops at fat_fileSize, so the most hops it can ever
;    make is ceil(size / clusterBytes) - 1, which is always fewer than
;    the volume's cluster count for any entry the volume could hold. So
;    a looping file chain does not hang: IT RETURNS THE SAME CLUSTERS
;    OVER AND OVER AS THOUGH THEY WERE DIFFERENT DATA. That is a silent
;    wrong answer, which is worse than a hang, so it gets two defences
;    of its own:
;
;      * AT OPEN, an entry whose size needs more clusters than the
;        volume HAS is refused with #FAT_ERR_FILE_TOO_BIG. That is the
;        check that turns fat_clusterCount into a real bound on the work
;        a hostile directory entry can demand - without it, a corrupt
;        4 GB size on a 32 MB volume is a very long walk indeed.
;      * AT EVERY HOP, a next cluster equal to the CURRENT cluster, or
;        equal to the file's FIRST cluster, is refused with
;        #FAT_ERR_CHAINLOOP. Those are the two shapes corruption
;        actually takes and both are O(1) to spot.
;
;    WHAT IS STILL NOT DETECTED, stated rather than hidden: a cycle that
;    closes on a cluster in the MIDDLE of the chain - 5 -> 9 -> 12 -> 9
;    - is not caught. Catching an arbitrary cycle in O(1) memory needs a
;    tortoise-and-hare second walk, which doubles the FAT lookups on
;    every cluster of every load. That was considered and rejected: what
;    it prevents is duplicated data rather than a hang, and the price is
;    paid on every good image to catch a bad one. The hook is here to be
;    upgraded if a real medium ever produces one.
;
;    Every cluster number is ALSO range-checked to 2 .. count+1 before
;    it is used as an address, which catches the other corruption: a
;    chain that walks off the volume.
;
;    ALL OF THIS IS TESTED, not argued. The fabricated image carries a
;    root directory that loops to itself, a file whose chain is
;    20 -> 21 -> 20, a file whose chain is 22 -> 22, and a file claiming
;    four billion bytes on a volume that holds thirty-two million. Each
;    is asserted to be REFUSED, by its own code. A test that only checks
;    good images proves nothing about any of this.
;
; 4. .i IS EIGHT BYTES ON THIS TARGET
;
;    Sector and byte arithmetic here cannot overflow: the largest thing
;    computed is (cluster - 2) * SecPerClus + dataLba, and on a 2 TB
;    volume that is about 2^32, which is nothing to a 64-bit .i. So this
;    file does no width juggling and needs none.
;
;    WHAT IT DOES MEAN is that no 32-bit assumption may be copied in
;    from a 32-bit target's FAT code. In particular a value built from
;    four PeekA bytes is ALWAYS POSITIVE here - it cannot wrap into a
;    negative number the way it would in a 32-bit .i - so every
;    comparison in this file is an ordinary signed compare and is
;    correct. That is why .n and PeekN are absent: on a 64-bit target a
;    32-bit disk field zero-extended into an .i needs no unsigned
;    compare at all.
;
;    The one place the width is load-bearing is fat_fileSize, which is a
;    32-bit on-disk field holding up to 4294967295. In a 32-bit .i that
;    is negative and every "pos < size" test inverts. Here it is not.
;
; 5. A CONSTANT INITIALISER TAKES A BARE LITERAL
;
;    "#FAT_HALF = 512 / 2" is refused by this compiler. Every constant
;    below is a bare literal and the arithmetic that produced it is in
;    the comment beside it.
;
; ======================================================================
; WRITING - WHY IT IS HERE NOW, AND WHAT IT COST TO DO PROPERLY
; ======================================================================
; This file was read-only on purpose for as long as Anvil was loaded by
; U-Boot: updating Anvil meant updating a file on a stick that a second
; machine owned. Once Anvil boots the board, updating Anvil means
; writing to the medium Anvil booted from, and the only alternative is
; pulling the stick every single time.
;
; THE FIRST ATTEMPT DELIBERATELY STOPPED SHORT and it is worth recording
; what it was, because the caution behind it was right. FatOverwrite
; would replace a file's contents and nothing else: the length had to
; equal the file's own exact size, there was no allocation, no free-space
; scan, no directory change and nothing at all touching the FAT. The
; argument was that a bug in allocation corrupts a filesystem while a
; bug in overwriting corrupts one file that was going to be replaced
; anyway. That argument still holds.
;
; What removed the restriction was not deciding the risk was acceptable.
; It was paying for it:
;
;   * every write goes through ONE procedure, fat_WriteRaw, and that
;     procedure refuses any sector outside the FSInfo sector, the FAT
;     region and the data region - not merely outside the partition.
;     See fat_LbaWritable; the volume boot sector is inside the
;     partition and is exactly where a lost offset lands
;   * the ORDER of every multi-step change is fixed by one rule and
;     that rule is stated below
;   * every new walk carries the same loop bound the read walks do
;   * the gate does not check the finished image only. It records the
;     ORDER the sectors were written in and checks that too, because a
;     correct image comes out of the wrong order just as happily as out
;     of the right one - right up until the power goes off in the middle
;   * and the gate is watched going RED for thirteen deliberate defects,
;     including four that are invisible in a finished image
;
; The practical consequence is that a caller no longer pads its buffer
; to FatSize() before saving. Anvil's save command did, and can stop.
;
; ======================================================================
; THE ORDER OF WRITES. ONE RULE, AND EVERYTHING FOLLOWS FROM IT.
; ======================================================================
;
;     A DIRECTORY ENTRY MUST NEVER POINT AT A CLUSTER THE FAT CALLS
;     FREE.
;
; That is the whole of it, and the two halves of the file that look
; contradictory are both consequences:
;
;   GROWING  - the clusters must exist before the entry mentions them,
;              so the FAT is written first, then the DATA, and the
;              DIRECTORY LAST. Interrupted anywhere, the worst outcome
;              is clusters marked in use that nothing references: LOST
;              CLUSTERS, which every repair tool understands, and a
;              volume that still mounts.
;
;   SHRINKING - the entry must stop mentioning them before they are
;              released, so the DIRECTORY IS WRITTEN FIRST and the FAT
;              second. Same worst outcome: lost clusters.
;
;   DELETING - the $E5 goes down before the chain is freed, for exactly
;              the same reason as shrinking.
;
; Get the shrink or the delete backwards and an interruption leaves a
; LIVE directory entry whose chain runs through free space. The next
; file created is handed one of those clusters and two files own the
; same sector. That is the one FAT failure a repair tool cannot undo -
; it can only pick a loser.
;
; Get the grow backwards and an interruption leaves a directory entry
; promising bytes that were never written: a load that succeeds and
; delivers garbage, which is worse than a load that fails.
;
; WITHIN AN ALLOCATION there is a second ordering and it matters just as
; much: the new cluster is CLAIMED (its own entry set to end-of-chain)
; before the previous cluster is pointed at it. Reverse those two and a
; single FatWrite that needs three clusters gets the same cluster three
; times, because the allocator scans for zeros and the zero is still
; there. See fat_AllocCluster.
;
; ======================================================================
; TIMESTAMPS - THIS BOARD HAS NO CLOCK, AND SAYS SO
; ======================================================================
; The BCM2711 has no battery-backed real-time clock. Nothing in this
; machine knows what day it is at the moment a file is written, and
; nothing this library can reach will tell it.
;
; THREE OPTIONS WERE ON THE TABLE.
;
;   1. WRITE ZEROS. [FATGEN] permits 0 in the creation and last-access
;      fields for an implementation that does not support them. But a
;      date word of $0000 decodes as day 0 of month 0, which is not a
;      date; tools print it blank, or garbage, or flag it. And the
;      specification does NOT bless a zero in DIR_WrtDate, which it
;      describes as the last modification date without an opt-out.
;
;   2. COUNT FROM SOMETHING. The 54 MHz system counter is available and
;      monotonic, so a date could be derived from an assumed epoch plus
;      uptime. REJECTED, and this is the important one: that produces a
;      DIFFERENT WRONG DATE EVERY TIME, close enough to plausible that
;      nobody notices it is fiction. A wrong date that looks right is
;      worse than an obviously absent one, because somebody eventually
;      uses it to decide which of two files is newer.
;
;   3. A FIXED SENTINEL. CHOSEN.
;
; EVERY DATE THIS FILE WRITES IS 1980-01-01 AND EVERY TIME IS 00:00:00,
; on creation and on every modification, in DIR_CrtDate, DIR_WrtDate and
; DIR_LstAccDate alike. That is $0021 and $0000 - year 0 of the FAT
; epoch, month 1, day 1: the FIRST INSTANT THE FORMAT CAN EXPRESS. It is
; a legal encoding, so no tool objects to it, and it is a date no file
; written by a Raspberry Pi 4 could honestly carry, so nobody mistakes
; it for information. DIR_CrtTimeTenth is 0.
;
; AND THERE IS A SEAM, because "this board has no clock" is a fact about
; the board and not about every caller forever. FatSetTimestamp(date,
; time) takes [FATGEN]'s two packed words and every entry written
; afterwards carries them. A caller that has been handed the time - over
; the network, from a user, from a host tool - can supply it, and one
; that has not gets the sentinel. Out-of-range values are REFUSED rather
; than masked, because a year of 2200 masked into seven bits comes out
; as 2092, which is precisely the plausible-looking wrong date this
; whole decision exists to avoid.
;
; ======================================================================
; THE SECOND FAT - IT IS MIRRORED, AND HERE IS WHY
; ======================================================================
; A FAT32 volume normally carries two copies of the FAT. BPB_NumFATs
; says how many and [FATGEN]'s BPB_ExtFlags says whether they are all
; live: bit 7 clear means every copy is mirrored and a driver must
; maintain all of them, bit 7 set means only the copy named by bits 3:0
; is live and the rest are not maintained.
;
; THIS FILE HONOURS THAT FIELD IN BOTH DIRECTIONS. Mirroring on, every
; copy is written; mirroring off, only the active one is. The read path
; already honoured it - fat_activeFat and fat_fatLba have been doing so
; since the file was read-only - and a write path that ignored it would
; be the two halves disagreeing about which bytes are the filesystem.
;
; WRITING ONLY THE FIRST COPY WAS CONSIDERED AND IS WRONG, for a reason
; that is easy to talk yourself out of: nothing HERE reads the second
; copy, so a stale one is invisible. That is exactly the problem. It is
; invisible to this library and perfectly visible to fsck, to Windows,
; to a card reader, and to this same library on the day somebody sets
; ExtFlags bit 7. A stale mirror is a FAT that was correct at some point
; in the past, which is the worst kind of wrong: it is self-consistent,
; it passes casual inspection, and it describes files that have moved.
;
; WHAT MIRRORING COSTS, stated rather than glossed: every FAT entry
; change is NumFATs sector writes instead of one, and an interruption
; between them leaves the copies disagreeing. That second point is not
; made worse by mirroring - a volume with one stale copy is exactly what
; not mirroring produces on purpose - and copy 0 is written first, so
; the copy every tool actually reads is the one most likely to be
; complete.
;
; THE COPIES ARE DRAGGED TOGETHER, NOT MERGED. fat_SetEntry reads the
; sector from the ACTIVE copy, changes one entry, and writes that buffer
; to all of them. If the copies had already diverged, the active one
; wins - which is right, because the active one is by definition what
; this volume's own chains mean.
;
; ======================================================================
; FSINFO - A HINT, TREATED AS ONE
; ======================================================================
; [FATGEN] puts a free-cluster count and a "start looking here" hint in
; a sector of the reserved region, named by BPB_FSInfo, and says in as
; many words that neither value is necessarily correct.
;
; SO BOTH ARE RANGE-CHECKED AT MOUNT AND REBUILT WHEN THEY FAIL. A free
; count above the volume's cluster count, or a next-free outside
; 2..count+1, or the specification's own $FFFFFFFF "unknown" - any of
; those and the first allocation or free does a full pass over the FAT
; and writes the truth back. A count that passes the range check is
; BELIEVED, because that is what the hint is for: it turns an allocation
; on a 2 GB volume from 512 sector reads into one. FatRescanFree() is
; the "I do not believe it" call for a caller that wants certainty.
;
; THE SIGNATURES ARE A DIFFERENT MATTER AND ARE NOT A HINT. If the
; sector the BPB points at does not carry $41615252, $61417272 and
; $AA550000 in the right three places, THIS FILE WILL NOT WRITE THERE AT
; ALL. BPB_FSInfo is a 16-bit sector number and a wrong one is not
; distinguishable from a right one by anything else - and the BACKUP
; BOOT SECTOR lives in the same reserved region, conventionally at
; sector 6. Writing a free-cluster count over the backup boot sector
; would be a very quiet disaster. The mount still succeeds, reports
; #FAT_ERR_FSINFO, and counts free space from the FAT for the rest of
; its life.
;
; ======================================================================
; WHERE THE LAYOUT CAME FROM. IT IS NOT ON THIS DISK.
; ======================================================================
; Be exact about this, the way emmc.pi4 is.
;
; NOTHING in RaspberryPi4/Reference/ describes FAT. It was
; searched for "FAT32", "BPB_", "fatgen", "boot sector" and "partition
; table"; the hits are unrelated ("fatal", "format"). The BCM2711
; peripherals document and the Pi 4 datasheet describe a controller, not
; a filesystem.
;
; SO THE FOLLOWING ARE CITED FROM OUTSIDE THIS REPOSITORY:
;
;   [FATGEN]  Microsoft Extensible Firmware Initiative FAT32 File System
;             Specification, version 1.03 ("fatgen103"). The BPB field
;             offsets, the FAT type determination ladder, the reserved
;             top four bits of a FAT32 entry, the end-of-chain and bad
;             cluster markers, the directory entry layout, the $E5
;             deleted marker, the $05 substitution for a leading $E5,
;             the ATTR_LONG_NAME = $0F convention and the FirstDataSector
;             / FirstSectorOfCluster formulas all come from this
;             document AND IT IS NOT IN THIS REPOSITORY.
;
;   [MBR]     The IBM PC master boot record layout - $55 $AA at $1FE,
;             four 16-byte entries at $1BE, status/type/LBA/count at
;             +0/+4/+8/+12 - which predates and is independent of
;             [FATGEN], and is likewise not in this repository. The
;             partition TYPE BYTE values ($01/$04/$06/$0E FAT12 and
;             FAT16, $0B/$0C FAT32, $EE GPT protective) come from the
;             same tradition.
;
; WHY THE FILE WAS WRITTEN ANYWAY rather than stopping at "cannot cite":
; the alternative was no loader. What has been done instead is to make
; every uncited number CHECKABLE BY EXECUTION - the test fabricates
; images to the layout this file believes in and reads them back
; byte-for-byte, including images built to be WRONG - and to refuse,
; loudly and by name, everything that was not implemented.
;
; ONE CROSS-CHECK WAS AVAILABLE AND WAS USED. U-Boot was running on this
; bench when this file was written and its `fatload usb 0:1` is the
; behaviour being replaced, so the argument shape - device, partition
; number counting from 1, load address, name - was copied from something
; observed working rather than invented. FatMount(1) is `0:1`.
;
; PAST TENSE ON PURPOSE: U-Boot has not been on that stick since
; 2026-08-26. The firmware loads KERNEL8.IMG, which is Anvil itself, and
; there is no chainload path back - so U-Boot is no longer available as
; a cross-check, and any instruction anywhere in this tree that tells an
; operator to fall back to it is stale. Two such sentences were found
; and fixed in the monitor the same week; they survived a full prose
; sweep because they are perfectly grammatical English that happens to
; be false, which is exactly the kind a proofreading pass cannot catch.
;
; ======================================================================
; WHAT WAS ACTUALLY PROVEN, AND WHAT IS UNVERIFIED
; ======================================================================
; THIS FILE READS AND WRITES THE REAL BOOT MEDIUM. It is how Anvil
; loads KERNEL8.IMG, CONFIG.TXT, its own settings store and 609 KB of
; Wi-Fi firmware, and how `save` puts files back onto the stick.
;
; ---- WHAT THE BENCH PROVED, AND WHEN --------------------------------
;
;   READING A REAL VOLUME, 2026-08-26. Through MscReadBlock and a real
;   VL805 / xHCI / USB stick, at the monitor prompt:
;
;       pmf> f
;       mounted USB: Samsung  Flash Drive FIT   119 GB
;       medium    USB, 250626566 blocks of 512 bytes
;       volume    FAT32 on partition 1, cluster 4096 bytes
;
;       pmf> f CONFIG.TXT 500000
;       loaded    813 bytes  00500000..0050032C
;
;   and the bytes at $500000 are the boot partition's actual config.txt.
;   START4.ELF loads too, 2,298,048 bytes, which exercises a long
;   cluster chain rather than a one-cluster file.
;
;   WRITING A REAL VOLUME, 2026-08-26. Anvil's `save` allocates, extends
;   and CREATES on that stick - FatCreate had existed for a while and
;   `save` simply never called it, which is why the radio's three files
;   could not be put there without moving the stick to another machine.
;   EACH FILE IS VERIFIED TWICE AND THE SECOND TIME IS THE ONE THAT
;   COUNTS: `receive` CRCs the serial transfer, which proves the wire
;   was clean and proves NOTHING about what reached the FAT, so the file
;   is then loaded back off the stick INTO A DIFFERENT ADDRESS and
;   CRC'd again on the board. The names on the volume are 8.3 -
;   BRCMFW.BIN, BRCMNV.TXT, BRCMCLM.BLB - because this file writes short
;   directory entries only and generates no VFAT long-name chains.
;
;   A CROSS-CHECK FROM THE FAR END: the firmware image read back off the
;   stick and pushed across SDIO to the radio CRCs to $B8B12CED, which
;   is what the host computed for brcmfmac43455-sdio.bin before it was
;   ever sent. 609,309 bytes through this file, byte-exact, checked by
;   something that never saw the filesystem.
;
; ---- NO SD CARD HAS EVER BEEN READ BY THIS FILE ---------------------
;
; There is no SD card in the machine and there never has been, so
; everything below the SdReadBlock seam SPECIFICALLY - all of emmc.pi4 -
; is unproven. Read that file's header; it is honest about it, and it
; now separates "the code executes at every boot" from "a card has
; answered", which are two different claims.
;
; This block used to open: "NO REAL CARD HAS EVER BEEN READ BY THIS
; FILE. There is no SD card in the machine. Everything below the
; block-reader seam is unproven." The first two sentences are still
; true. The third stopped being true the day usbmsc.pi4 existed, and
; that is the whole shape of the error - THERE ARE TWO BLOCK SOURCES AND
; ONLY ONE OF THEM IS AN SD CARD. A sentence written when there was one
; seam was left standing after a second seam was plugged in and proven.
;
; WHAT WAS PROVEN BEFORE ANY MEDIUM, by execution, 2026-08-25. A FAT32
; volume was
; fabricated byte by byte inside a Dim array - MBR, boot sector, two
; FATs, root directory, file data - the test program pointed this file
; at it through FatSetBlockReader, and the whole thing was compiled for
; -t pi4 and RUN on the project's A64 oracle, tools/a64/a64_interp.py.
; 155 ASSERTIONS, ALL PASSING, in 680,900 interpreter steps:
;
;   * a real MBR is parsed, from a partition that starts at LBA 63 and
;     NOT at 0, and every derived number is asserted: partition type,
;     start, length, total sectors, bytes per cluster, cluster count,
;     FAT LBA, data LBA, root cluster
;   * the FAT type ladder lands on 32 at 65525 clusters and on 16 at
;     65524, out of the same code path, with the boundary volume built
;     to sit exactly on it - and both non-FAT32 volumes carry the $0C
;     FAT32 partition type AND the "FAT32   " string, so a reader that
;     trusted either would sail past
;   * a file is found in the root directory that is the SEVENTH entry,
;     behind the volume label, behind a deleted ($E5) entry and behind
;     a two-entry long-name ($0F) run
;   * its 2500 bytes come back EXACTLY, over the chain 5 -> 9 -> 6 ->
;     12 -> 8, which is neither contiguous nor in order, compared
;     byte-for-byte against what was fabricated - three times: whole,
;     in 100-byte pieces after a FatRewind, and into a destination
;     deliberately offset by one byte
;   * both read paths ran and were counted from OUTSIDE: four whole
;     sectors went DIRECT into the caller's buffer, and the unaligned
;     destination took the bounce for every one of its sectors. The
;     reader was never once handed a buffer that SdReadBlock's 4-byte
;     alignment rule would have refused
;   * a root directory chained to itself is REFUSED - that one really
;     does spin forever without the bound
;   * a file chain looping back to its start, a cluster pointing at
;     itself, a chain ending early, a defective-cluster marker, a
;     cluster off the volume, an entry with no cluster, and an entry
;     claiming four billion bytes are each refused BY THEIR OWN CODE
;   * every mount-time refusal above is reached by corrupting one or
;     two bytes of the fabricated medium and put back afterwards
;   * a mid-file medium failure returns -1 with the failing LBA
;
; AND THE GATE WAS WATCHED FAILING FIRST, five ways, because a test
; that has only ever passed proves nothing about itself:
;
;     the partition offset dropped from fat_dataLba   47 of 155 fail
;     PeekA changed to PeekB in fat_U8/U16/U32        93 of 155 fail
;     the directory scan stopping at a $E5 entry      45 of 155 fail
;     the FAT16/FAT32 boundary moved by one           the good volume
;                                                     mounts as FAT16
;     the file-chain loop check removed               LOOP.IMG returns
;                                                     3000 bytes of
;                                                     DUPLICATED data
;                                                     instead of -1
;
; That last one is the whole argument for the check, measured rather
; than asserted: without it the failure is not a hang, it is a silent
; wrong answer that looks exactly like a successful load.
;
; THE TEST IS IN THIS REPOSITORY NOW, and this paragraph used to say it
; was not. It was written under a brief that gave this file's author one
; file and one only, so the harness and the program were built outside
; the tree and the note was a request to adopt them. They were adopted:
;
;     tools/a64/a64_fat_check.py                        the gate
;     RaspberryPi4/Examples/Diagnostics/pi4FatSelfTest.pi4   the program
;
; The gate fabricates the volume and holds every expected value
; independently of the program - and, for the write half, reads the
; medium back afterwards and parses it without asking the program
; anything. Run it with --mutate to watch it go red.
;
; A self-test is an instrument, so it lives in Diagnostics/ and never
; ships.
;
; THE EMITTED ASSEMBLY WAS ALSO READ BACK for the one thing that cannot
; be seen from a passing test: every on-disk byte read in this file
; comes out as "ldrb w", which zero-extends, and there is not one sxtb
; or sxth anywhere in this file's code. That is PeekA doing what the
; 2026-08-25 signedness ruling says it does.
;
; WHAT IS UNVERIFIED. This used to say "and it is the whole lower half",
; which has not been true since the USB reader landed - the lower half
; is proven on one medium and untried on the other:
;
;   * that SdReadBlock ever returns a byte from a card. MscReadBlock
;     does, on every boot; the SD path does not exist on this bench.
;   * that a real card's boot sector matches the layout above - it is
;     believed from a specification that is not on this disk. The USB
;     stick's DID match, first time, MBR partition at a non-zero LBA and
;     all, which is one real volume rather than none but is still one.
;   * anything about media with 4096-byte physical sectors, about a
;     partition beyond 2 TB (an MBR cannot express one; GPT is refused
;     by name), or about a volume whose FAT is mirrored with the active
;     copy not being the first
;   * timing. This file has no timeouts of its own because it has no
;     hardware waits of its own: every wait belongs to the reader, and
;     emmc.pi4 bounds all of its own. If a reader can hang, this file
;     hangs with it, and that is the reader's contract to keep.
;
; AND WHAT IS UNVERIFIED ABOUT THE WRITE HALF SPECIFICALLY:
;
;   * ~~that MscWriteBlock, or any writer, has ever put a byte on a real
;     medium. The seam is proven; what is behind it on the bench is
;     not~~ - SUPERSEDED 2026-08-26. MscWriteBlock has put three files
;     on the real boot stick through this file's create/allocate/extend
;     path, each read back off the volume into a different address and
;     CRC-checked on the board. See the top of this section.
;
;     ONE INSTRUMENT LIED WHILE PROVING IT, and the lesson is about
;     parsers rather than about this file: the first readback reported
;     "READBACK CRC MISMATCH - want 2BDBDDF6, the stick holds
;     EDB88320". $EDB88320 is the reflected CRC-32 POLYNOMIAL, which
;     Anvil prints two lines below the answer, and the host-side parser
;     had taken the last hex-looking token in the output. The file was
;     perfect. Anchor a parser on the sentence that carries the answer.
;   * DURABILITY. A block writer that returns 1 has been told the sector
;     is written. Whether it has REACHED the flash, or is sitting in a
;     controller's cache that a power cut will drop, is not something
;     this file can know or ask - there is no flush in the contract. The
;     ordering rules above are therefore about the order sectors are
;     HANDED OVER, and they are only as good as the writer's honesty
;     about completion. A device that reorders writes internally can
;     defeat every one of them
;   * every ordering claim was measured under an interpreter, by
;     recording the sequence. Nothing has actually been interrupted
;     mid-write and inspected afterwards, on this or any medium
;   * a volume where BPB_ExtFlags disables mirroring has been mounted
;     by the gate but never WRITTEN to. The one-live-FAT branch of
;     fat_SetEntry is reasoned, not executed
;   * a volume that actually runs out of clusters. #FAT_ERR_NO_SPACE and
;     #FAT_ERR_DIR_FULL are reached by reading the code, not by filling
;     a 32 MB test volume 65525 clusters at a time
;
; ======================================================================
; WHAT THE WRITE HALF PROVED, 2026-08-26
; ======================================================================
; The same fabricated volume, the same seam - a second procedure of the
; same shape handed to FatSetBlockWriter - and the same A64 oracle. The
; gate went from 155 assertions to 383 and from 680,900 interpreter
; steps to 30,564,625, most of that the three full FAT passes a
; 65525-cluster volume costs when its FSInfo has nothing to offer. It
; makes 108 sector writes and not one of them lands outside the FAT and
; data regions.
;
; WHAT THE HARNESS CHECKS, and the important word is HARNESS: none of
; this is the program reporting on itself. The gate reads the medium
; back out of memory afterwards and parses the FAT, the directory and
; FSInfo the way a different implementation would.
;
;   * a file grown across a cluster boundary has the right chain and
;     the right directory size, and reads back byte for byte
;   * a truncated file's freed clusters read as 0 in the FAT - both
;     copies - and the surviving bytes are the original ones
;   * a created file is found by a FRESH FatOpen and reads back exactly
;     what was written, including one created into a root directory
;     that had to be EXTENDED by a cluster to hold it
;   * a deleted file's entry is $E5, its clusters are free, and a fresh
;     scan no longer finds the name
;   * FSInfo's free count and next-free hint agree with a full scan of
;     the FAT afterwards
;   * the two FATs are byte-identical over all 512 sectors
;   * NOTHING WAS EVER WRITTEN OUTSIDE THE FAT AND DATA REGIONS. Twice
;     over: every LBA the writer was handed is checked against the
;     allowed set, and every sector outside it is compared byte for
;     byte against what was fabricated
;   * the ORDER, three ways, none of them visible in a finished image:
;     the data reached the medium before the directory entry that
;     describes it; the directory released the tail before the tail was
;     freed; and after EVERY SINGLE WRITE, no FAT entry points at a
;     cluster whose own entry reads free
;   * the FSInfo sector was NOT written during the stretch when its
;     signatures were deliberately broken
;
; AND THE GATE WAS WATCHED FAILING, THIRTEEN WAYS:
;
;     the chain walk off by one
;     the directory size update forgotten
;     the directory written BEFORE the data
;     a cluster written before it is claimed in the FAT
;     the second FAT not mirrored
;     truncation freeing the tail before the directory releases it
;     a deleted file's clusters not freed
;     FSInfo never written back
;     the free count never rebuilt when FSInfo has none
;     the reserved top four bits zeroed on write
;     a new directory cluster linked in without being zeroed
;     the data-region offset dropped from fat_ClusterLba, FENCE INTACT
;     the same, with the fence removed as well
;
; THE LAST TWO ARE A PAIR AND THEY ARE THE ARGUMENT FOR THE FENCE. With
; the arithmetic broken and fat_LbaWritable in place, every write is
; refused and nothing outside the allowed regions is touched - the gate
; goes red on the results, and the medium is untouched. Remove the fence
; as well and the harness sees sectors change that no filesystem write
; should ever reach.
;
; AND ONE OF THE THIRTEEN GOT THROUGH ON THE FIRST ATTEMPT, which is
; worth more than the twelve that did not.
;
; "A CLUSTER IS WRITTEN TO BEFORE IT IS CLAIMED IN THE FAT" - the swap
; inside fat_AllocCluster that links prev at the new cluster before the
; new cluster's own entry says end-of-chain - came out GREEN. The gate
; was recording the SEQUENCE OF LBAs, and fat_SetEntry writes the same
; FAT sector twice in a row for those two steps, so both orders produce
; the identical pair of addresses. The finished image is identical too.
; Only the window in between differs, and nothing was looking at it.
;
; The fix was to keep the 512 BYTES of every write, not only its
; address, and to check the rule as an INVARIANT AFTER EVERY WRITE
; rather than as a sequence: no written FAT sector may leave a cluster
; pointing at a cluster whose own entry reads free. That is the actual
; rule; the ordering was only ever a way of achieving it.
;
; The lesson generalises past this file. An ordering test that watches
; addresses can only see orderings that MOVE something. State the
; property instead and it does not matter how the code arrives at it.
;
; ======================================================================
; DELIBERATELY LEFT OUT - the full list, so nobody assumes
; ======================================================================
;  * SUBDIRECTORIES. FatOpen searches the ROOT directory only. A name
;    containing '/' or '\' is refused with #FAT_ERR_NAME rather than
;    silently searched for as a flat name. The chain walk that would
;    make subdirectories work already exists - fat_NextCluster and the
;    directory scan are written against a cluster chain, not against a
;    fixed root region - so this is a scope decision, not a wall.
;  * LONG FILENAMES (VFAT). See above; $0F entries are skipped.
;  * SUBDIRECTORY LISTING. FatDirRewind / FatDirNext (added for `fatls`)
;    iterate the ROOT directory only, the same directory FatOpen searches.
;    There is still no descent into a subdirectory, for the same reason
;    FatOpen has none - see SUBDIRECTORIES above. A caller asking for one
;    is told no rather than shown the root.
;  * FAT12 and FAT16, refused by name.
;  * exFAT, which is a different filesystem that happens to share a
;    prefix. Its boot sector has no BPB in this shape, so it fails at
;    #FAT_ERR_SECSIZE or #FAT_ERR_SPC rather than being mis-read.
;  * GPT. A protective MBR (type $EE) is refused with its own code
;    rather than being read as a 2 TB FAT partition.
;  * MULTI-BLOCK READS. One 512-byte block per reader call, because that
;    is the only shape emmc.pi4 offers. A reader that could do more
;    would need a wider contract, and the contract is the API.
;  * CACHING beyond one FAT sector and one data sector. Two 512-byte
;    buffers, no more, because this runs before there is a heap.
;  * REAL TIMESTAMPS. There is no clock; see TIMESTAMPS above for the
;    sentinel and the seam.
;  * SETTING ATTRIBUTES. A created file is ARCHIVE and nothing else.
;    ATTR_READ_ONLY is HONOURED on entries that already carry it -
;    FatWrite, FatTruncate and FatDelete all refuse - but there is no
;    call to set or clear it, because a loader has no policy to express.
;  * RENAME. It would be two directory writes with a window in between
;    where the file exists twice or not at all, and nothing needs it.
;  * DELETING A DIRECTORY. Refused with #FAT_ERR_IS_DIR. Doing it means
;    recursing into a directory this file cannot read, so it would be
;    freeing a chain whose contents were never looked at.
;  * DEFRAGMENTATION, or any attempt to allocate contiguously. The
;    allocator takes the first free cluster from the hint. A file
;    written to a fragmented volume comes out fragmented.
;  * TWO OPEN FILES. There is one, which is all a loader needs and one
;    fewer thing to get wrong.
;  * SPARSE FILES. FatSeek refuses a position past the end, because the
;    bytes in the gap would be whatever the new clusters already held.
;  * THE BACKUP BOOT SECTOR at BPB_BkBootSec. It is never read and never
;    written. A volume whose primary boot sector is damaged is not
;    repaired here.
;
; ======================================================================
; THE WHOLE API, IN ONE PLACE
; ======================================================================
;   wiring, before anything else
;     FatSetBlockReader(addr)     addr is @SdReadBlock or equivalent
;     FatBlockReader()            what is set, 0 if nothing
;
;   mounting
;     FatMount(partition)         partition is 1..4, U-Boot's "0:N"
;     FatMounted()                1 after a successful FatMount
;     FatType()                   32, or 12 / 16 for what was refused,
;                                 or 0 if it never got that far
;
;   what was found (all valid after a successful FatMount)
;     FatPartitionType()          the MBR type byte
;     FatPartitionLba()           where the volume starts, in sectors
;     FatPartitionSectors()       how long the MBR says it is
;     FatBytesPerCluster()
;     FatClusterCount()           CountofClusters - the chain bound
;     FatFatLba()                 absolute LBA of the active FAT
;     FatDataLba()                absolute LBA of cluster 2
;     FatRootCluster()
;     FatTotalSectors()
;
;     FatFsInfoValid()            1 when FSInfo can be trusted and
;                                 written to
;     FatFsInfoLba()              where it is, or -1
;     FatMirrorsFats()            1 when every FAT copy is maintained
;     FatNumFats()
;     FatFatBase()                LBA of FAT copy 0
;     FatFatEnd()                 one past the last FAT sector
;     FatDataEnd()                one past the last data sector
;
;   the file
;     FatOpen(name)               "PMF.IMG" - 8.3, root directory
;     FatIsOpen()
;     FatSize()                   bytes, from the directory entry
;     FatFirstCluster()
;     FatAttributes()             the entry's DIR_Attr byte
;     FatRead(*dst, max)          bytes placed, 0 at EOF, -1 on error
;     FatTell()                   how far the position has got
;     FatSeek(pos)                0..FatSize(). Past the end is refused
;     FatRewind()                 back to byte 0 without reopening
;     FatClose()
;     FatDirEntryLba()            where the open entry lives, and
;     FatDirEntryOffset()         where in that sector
;
;   listing the root directory (no file need be open; shares fat_secBuf)
;     FatDirRewind()              cursor to the start of the root dir
;     FatDirNext()                1 entry current, 0 clean end, -1 error
;     FatDirName(*dst)            the 11 raw 8.3 name bytes of it
;     FatDirIsDir()               1 if it is a subdirectory
;     FatDirSize()                its size in bytes
;     FatDirAttr()                its raw DIR_Attr byte
;
;   writing - none of it does anything until a writer is installed
;     FatSetBlockWriter(addr)     @MscWriteBlock, or 0 to turn it off
;     FatBlockWriter()
;     FatWrite(*src, len)         at the current position, extending as
;                                 needed. Returns len, or -1
;     FatTruncate(len)            shorter or the same. Longer is refused
;     FatOverwrite(*src, len)     replace the whole file, ANY length
;     FatCreate(name)             a new empty file, left OPEN
;     FatDelete(name)             free the chain, mark the entry $E5
;
;   free space
;     FatFreeClusters()           -1 until something needs to know
;     FatNextFreeHint()
;     FatFreeScanned()            1 once a full FAT pass has happened
;     FatRescanFree()             force one, and write FSInfo back
;     FatSyncFsInfo()             write FSInfo back without scanning
;
;   the clock this board does not have
;     FatSetTimestamp(date, time) [FATGEN]'s two packed words
;     FatTimestampDate()          $0021 - 1980-01-01 - until set
;     FatTimestampTime()          $0000 - midnight - until set
;
;   why it refused
;     FatLastError()              one of the #FAT_ERR_ codes
;     FatErrorText()              a NUL-terminated English sentence
;     FatLastLba()                the LBA whose read or write failed,
;                                 for #FAT_ERR_READ_FAIL,
;                                 #FAT_ERR_WRITE_FAIL and
;                                 #FAT_ERR_LBA_RANGE
; ======================================================================

EnableExplicit

; ----------------------------------------------------------------------
; Geometry. Bare literals - a constant initialiser here cannot contain
; arithmetic - with the arithmetic in the comment.
; ----------------------------------------------------------------------
#FAT_SECTOR_SIZE     = 512   ; the only sector size handled, and the
                             ; only one emmc.pi4 offers
#FAT_DIRENT_SIZE     = 32    ; [FATGEN] directory entry, fixed forever
#FAT_DIRENTS_PER_SEC = 16    ; 512 / 32

; ----------------------------------------------------------------------
; MBR. [MBR] - not in this repository, see the header.
; ----------------------------------------------------------------------
#FAT_MBR_SIG_OFF   = $1FE  ; $55 at $1FE, $AA at $1FF
#FAT_MBR_PART0     = $1BE  ; first of four 16-byte entries.
                           ; $1BE is 2 modulo 4 - see trap 2 in the
                           ; header, this is WHY nothing is 32-bit loaded
#FAT_MBR_PART_SIZE = 16
#FAT_PE_STATUS     = 0     ; $00 inactive, $80 bootable, anything else
                           ; means this is not a partition table
#FAT_PE_TYPE       = 4
#FAT_PE_LBA        = 8     ; 32-bit, little endian, UNALIGNED
#FAT_PE_COUNT      = 12    ; 32-bit, little endian, UNALIGNED

; Partition type bytes. [MBR] tradition; the FAT32 pair is what a Pi
; boot partition carries.
#FAT_PT_EMPTY      = $00
#FAT_PT_FAT12      = $01
#FAT_PT_FAT16_S    = $04   ; FAT16 under 32 MB
#FAT_PT_FAT16      = $06   ; FAT16 CHS
#FAT_PT_FAT32_CHS  = $0B
#FAT_PT_FAT32_LBA  = $0C   ; what mkfs.vfat writes, and what a Pi has
#FAT_PT_FAT16_LBA  = $0E
#FAT_PT_GPT        = $EE   ; protective MBR - the disk is GPT

; ----------------------------------------------------------------------
; BPB, at the start of the volume's first sector. [FATGEN].
; ----------------------------------------------------------------------
#FAT_BPB_BYTSPERSEC = $0B  ; 16-bit
#FAT_BPB_SECPERCLUS = $0D  ; 8-bit, a power of two, 1..128
#FAT_BPB_RSVDSECCNT = $0E  ; 16-bit, >= 1; 32 is usual on FAT32
#FAT_BPB_NUMFATS    = $10  ; 8-bit, 2 in practice
#FAT_BPB_ROOTENTCNT = $11  ; 16-bit, MUST be 0 on FAT32
#FAT_BPB_TOTSEC16   = $13  ; 16-bit, 0 on FAT32
#FAT_BPB_MEDIA      = $15  ; 8-bit, $F8 fixed / $F0 removable
#FAT_BPB_FATSZ16    = $16  ; 16-bit, MUST be 0 on FAT32
#FAT_BPB_TOTSEC32   = $20  ; 32-bit
#FAT_BPB_FATSZ32    = $24  ; 32-bit, sectors in ONE FAT
#FAT_BPB_EXTFLAGS   = $28  ; 16-bit; bit 7 set = only one FAT is live,
                           ; bits 3:0 say which
#FAT_BPB_FSVER      = $2A  ; 16-bit, must be 0 - [FATGEN] says a driver
                           ; must refuse a version it does not know
#FAT_BPB_ROOTCLUS   = $2C  ; 32-bit, usually 2
#FAT_BPB_FSINFO     = $30  ; 16-bit, the sector number of the FSInfo
                           ; structure WITHIN THE RESERVED REGION, i.e.
                           ; relative to the volume's own first sector,
                           ; not to the disk. Usually 1. [FATGEN] says 0
                           ; and $FFFF both mean "there is no FSInfo".

; ----------------------------------------------------------------------
; FSInfo. [FATGEN], "FAT32 FSInfo Sector Structure and Backup Boot
; Sector". Everything in it is a HINT: the specification says in as many
; words that a driver must not trust FSI_Free_Count or FSI_Nxt_Free and
; must be prepared to compute the truth from the FAT. This file does
; exactly that - see fat_EnsureFreeInfo.
;
; The three signatures are not decoration. They are the only thing that
; distinguishes an FSInfo sector from whatever else a formatter left in
; the reserved region, and this file will not WRITE a sector whose
; signatures do not check out. See fat_ReadFsInfo for why that refusal
; is worth more than the free-space hint it costs.
; ----------------------------------------------------------------------
#FAT_FSI_LEADSIG_OFF  = $000  ; 32-bit
#FAT_FSI_STRUCSIG_OFF = $1E4  ; 32-bit
#FAT_FSI_FREE_COUNT   = $1E8  ; 32-bit, last known count of free clusters
#FAT_FSI_NXT_FREE     = $1EC  ; 32-bit, where to start looking for one
#FAT_FSI_TRAILSIG_OFF = $1FC  ; 32-bit
#FAT_FSI_LEADSIG      = $41615252   ; "RRaA" little-endian
#FAT_FSI_STRUCSIG     = $61417272   ; "rrAa" little-endian
#FAT_FSI_TRAILSIG     = $AA550000   ; $00 $00 $55 $AA
#FAT_FSI_UNKNOWN      = $FFFFFFFF   ; both hints use this for "no idea"

; ----------------------------------------------------------------------
; Directory entry. [FATGEN].
; ----------------------------------------------------------------------
#FAT_DIR_NAME       = 0    ; 11 bytes, 8 then 3, space padded, uppercase
#FAT_DIR_ATTR       = $0B
#FAT_DIR_NTRES      = $0C  ; lowercase DISPLAY flags - ignored here
#FAT_DIR_CRTTIMETNTH= $0D  ; 8-bit, hundredths of a second, 0..199
#FAT_DIR_CRTTIME    = $0E  ; 16-bit
#FAT_DIR_CRTDATE    = $10  ; 16-bit
#FAT_DIR_LSTACCDATE = $12  ; 16-bit
#FAT_DIR_FSTCLUSHI  = $14  ; 16-bit, high half of the first cluster
#FAT_DIR_WRTTIME    = $16  ; 16-bit
#FAT_DIR_WRTDATE    = $18  ; 16-bit
#FAT_DIR_FSTCLUSLO  = $1A  ; 16-bit, low half. NOTE the two halves are
                           ; six bytes apart with other fields between
#FAT_DIR_FILESIZE   = $1C  ; 32-bit

; ----------------------------------------------------------------------
; THE CLOCK THIS BOARD DOES NOT HAVE. Read "TIMESTAMPS" in the header
; before changing either of these.
;
; [FATGEN] packs a date as (year - 1980) << 9 | month << 5 | day, and a
; time as hour << 11 | minute << 5 | (second / 2). $0021 is therefore
; year 0, month 1, day 1 - the FIRST DAY THE FORMAT CAN EXPRESS, which
; is 1980-01-01. Time $0000 is midnight.
;
; A date of $0000 would be month 0, day 0: not a date at all. Some tools
; print it blank, some print garbage, and a repair tool is entitled to
; call it damage. $0021 is a LEGAL encoding that no file written by this
; board could honestly carry, which is exactly what a sentinel should be.
; ----------------------------------------------------------------------
#FAT_DATE_SENTINEL  = $0021  ; 1980-01-01
#FAT_TIME_SENTINEL  = $0000  ; 00:00:00

#FAT_ATTR_READ_ONLY = 1
#FAT_ATTR_HIDDEN    = 2
#FAT_ATTR_SYSTEM    = 4
#FAT_ATTR_VOLUME_ID = 8
#FAT_ATTR_DIRECTORY = 16
#FAT_ATTR_ARCHIVE   = 32
#FAT_ATTR_LONG_NAME = 15   ; $0F = READ_ONLY|HIDDEN|SYSTEM|VOLUME_ID.
                           ; [FATGEN]: an entry with EXACTLY this
                           ; attribute is a VFAT long-name fragment and
                           ; is not a directory entry at all

#FAT_DIRENT_FREE    = $E5  ; this entry is deleted - SKIP IT and keep
                           ; going, there are live entries after it
#FAT_DIRENT_END     = $00  ; this entry and every one after it has never
                           ; been used - STOP, do not keep scanning
#FAT_DIRENT_E5      = $05  ; a real leading $E5 is stored as $05 so it
                           ; cannot be mistaken for "deleted"

; ----------------------------------------------------------------------
; FAT entry values. [FATGEN]: the top four bits of a FAT32 entry are
; RESERVED and must be ignored when reading.
; ----------------------------------------------------------------------
#FAT_ENTRY_MASK  = $0FFFFFFF
#FAT_CLUS_RSVD   = $F0000000  ; the complement - the four bits a WRITE
                              ; must carry over from the old value.
                              ; [FATGEN] is explicit that a driver must
                              ; preserve them, not zero them
#FAT_CLUS_BAD    = $0FFFFFF7  ; the cluster is defective
#FAT_CLUS_EOC    = $0FFFFFF8  ; anything >= this ends the chain
#FAT_CLUS_EOC_W  = $0FFFFFFF  ; the end-of-chain value this file WRITES.
                              ; Reading accepts the whole $0FFFFFF8..
                              ; $0FFFFFFF band; writing picks one, and
                              ; $0FFFFFFF is the one [FATGEN]'s own
                              ; format description uses
#FAT_CLUS_FREE   = 0          ; a FAT entry of 0 means the cluster is
                              ; available. Cluster numbers 0 and 1 do
                              ; not name storage, so their entries are
                              ; NOT free space - see fat_SetEntry, which
                              ; refuses to write either of them

; ----------------------------------------------------------------------
; The FAT type boundaries. [FATGEN] "Determination of FAT type" -
; written as the LAST value in each band, because the spec's own test is
; "< 4085" and "< 65525" and an off-by-one here silently mis-reads a
; whole class of volume.
; ----------------------------------------------------------------------
#FAT_MAX_FAT12_CLUSTERS = 4084   ; 4085 - 1
#FAT_MAX_FAT16_CLUSTERS = 65524  ; 65525 - 1

; ----------------------------------------------------------------------
; 8.3 name geometry.
; ----------------------------------------------------------------------
#FAT_NAME_BASE_MAX = 8
#FAT_NAME_EXT_MAX  = 3
#FAT_NAME_LEN      = 11  ; 8 + 3, with no dot stored

; ----------------------------------------------------------------------
; Why FatMount(), FatOpen() or FatRead() refused. One code per distinct
; failure - the same shape emmc.pi4 uses, and for the same reason: a
; report that says "mount failed" sends somebody to look at the card
; when the answer was that the partition slot is empty.
; ----------------------------------------------------------------------
#FAT_ERR_NONE         =  0
#FAT_ERR_NO_READER    =  1  ; FatSetBlockReader was never called. There
                            ; is no default block source and there will
                            ; not be one
#FAT_ERR_NO_WRITER    = 40  ; FatSetBlockWriter was never called
#FAT_ERR_WRITE_FAIL   = 41  ; the block writer returned 0
#FAT_ERR_SIZE_MISMATCH = 42 ; RETIRED 2026-08-26 AND KEPT ON PURPOSE.
                            ; FatOverwrite used to demand a length equal
                            ; to the file's exact size, because nothing
                            ; here could change a directory entry. It
                            ; can now, so this is no longer raised by
                            ; anything. The NUMBER stays defined and the
                            ; sentence stays in FatErrorText because a
                            ; caller written against the old library may
                            ; still test for 42, and a code that quietly
                            ; becomes some OTHER failure's number is the
                            ; worst way to retire one.
#FAT_ERR_NO_SPACE     = 43  ; the FAT has no free cluster left
#FAT_ERR_DIR_FULL     = 44  ; the root directory has no free slot and
                            ; could not be extended
#FAT_ERR_EXISTS       = 45  ; FatCreate, and the name is already there.
                            ; NOT silently reused - see FatCreate
#FAT_ERR_READ_ONLY    = 46  ; the entry carries ATTR_READ_ONLY
#FAT_ERR_FSINFO       = 47  ; the BPB points at an FSInfo sector whose
                            ; signatures do not check out. Reported, and
                            ; the sector is then left ALONE
#FAT_ERR_BAD_LEN      = 48  ; a negative length to FatWrite/FatTruncate,
                            ; or a FatSeek past the end of the file
#FAT_ERR_LBA_RANGE    = 49  ; A WRITE WAS AIMED OUTSIDE THE PARTITION,
                            ; or outside the FAT and data regions inside
                            ; it. This is the last line of defence and
                            ; it should never fire; if it does, the
                            ; cluster arithmetic above it is wrong
#FAT_ERR_RESERVED_CLUS = 50 ; something tried to write the FAT entry of
                            ; cluster 0 or 1, or of a cluster past the
                            ; end of the volume
#FAT_ERR_NO_DIRENT    = 51  ; the open file's directory entry is not
                            ; where FatOpen left it - it no longer
                            ; carries the same name. Refused rather than
                            ; writing a size into somebody else's entry
#FAT_ERR_GROW_REFUSED = 52  ; FatTruncate was asked to make a file
                            ; BIGGER. It will not invent the new bytes
#FAT_ERR_READ_FAIL    =  2  ; the block reader returned 0. FatLastLba()
                            ; holds which sector; the reader's own error
                            ; accessor holds why
#FAT_ERR_NO_MBR       =  3  ; LBA 0 does not end $55 $AA
#FAT_ERR_PARTNUM      =  4  ; the partition number is not 1..4
#FAT_ERR_PART_STATUS  =  5  ; the entry's status byte is neither $00 nor
                            ; $80, so this is not a partition table
#FAT_ERR_PART_EMPTY   =  6  ; that slot's type byte is $00
#FAT_ERR_PART_GPT     =  7  ; type $EE - this is a GPT disk and its
                            ; partitions are not in the MBR
#FAT_ERR_PART_TYPE    =  8  ; the type byte is not a FAT32 type
#FAT_ERR_PART_GEOM    =  9  ; start LBA 0, or a sector count of 0
#FAT_ERR_NO_BOOTSEC   = 10  ; the volume's first sector has no $55 $AA
#FAT_ERR_SECSIZE      = 11  ; BPB_BytsPerSec is not 512
#FAT_ERR_SPC          = 12  ; BPB_SecPerClus is 0, over 128, or not a
                            ; power of two
#FAT_ERR_RESERVED     = 13  ; BPB_RsvdSecCnt is 0 - the boot sector is
                            ; itself inside the reserved region, so 0 is
                            ; impossible
#FAT_ERR_NUMFATS      = 14  ; BPB_NumFATs is 0
#FAT_ERR_FATSZ        = 15  ; both FAT size fields are 0
#FAT_ERR_TOTSEC       = 16  ; both total-sector fields are 0
#FAT_ERR_GEOMETRY     = 17  ; the metadata regions do not fit inside the
                            ; volume, or the volume does not fit inside
                            ; the partition
#FAT_ERR_FAT12        = 18  ; it is FAT12. Not implemented, refused
#FAT_ERR_FAT16        = 19  ; it is FAT16. Not implemented, refused
#FAT_ERR_ROOTENT      = 20  ; BPB_RootEntCnt is nonzero on a volume that
                            ; computes as FAT32 - the BPB contradicts
                            ; itself
#FAT_ERR_FATSZ16      = 21  ; BPB_FATSz16 is nonzero on a FAT32 volume,
                            ; likewise
#FAT_ERR_FSVER        = 22  ; BPB_FSVer is not 0 - an unknown FAT32
                            ; revision must be refused, not guessed at
#FAT_ERR_ROOTCLUS     = 23  ; the root cluster is outside 2..count+1
#FAT_ERR_ACTIVEFAT    = 24  ; BPB_ExtFlags names an active FAT that does
                            ; not exist
#FAT_ERR_BUF_ALIGN    = 25  ; this file's own sector buffers came out
                            ; misaligned. See fat_CheckBuffers - the
                            ; reader contract needs 4-byte alignment and
                            ; this is the only place it can be checked
#FAT_ERR_NOT_MOUNTED  = 26  ; an operation before a successful FatMount
#FAT_ERR_NAME         = 27  ; the name is not expressible in 8.3, or
                            ; contains a path separator. NOT "not found"
#FAT_ERR_NOTFOUND     = 28  ; no such entry in the root directory
#FAT_ERR_IS_DIR       = 29  ; the name matched, and it is a directory
#FAT_ERR_DIRLOOP      = 30  ; the root directory chain visited more
                            ; clusters than the volume has
#FAT_ERR_BADCLUS      = 31  ; a cluster number outside 2..count+1
#FAT_ERR_BADCLUS_MARK = 32  ; the chain reached $0FFFFFF7, the defective
                            ; cluster marker
#FAT_ERR_CHAINLOOP    = 33  ; the file chain visited more clusters than
                            ; the volume has - it loops
#FAT_ERR_SHORT_CHAIN  = 34  ; the chain ended before FileSize bytes had
                            ; been delivered. The directory entry and
                            ; the FAT disagree
#FAT_ERR_FILE_CLUSTER = 35  ; a nonzero file size with a first cluster
                            ; of 0, which cannot be read
#FAT_ERR_NO_FILE      = 36  ; FatRead or FatSize with no file open
#FAT_ERR_NULL_DST     = 37  ; FatRead into a null destination
#FAT_ERR_BAD_MAX      = 38  ; FatRead with a negative maximum
#FAT_ERR_FILE_TOO_BIG = 39  ; the entry's size needs more clusters than
                            ; the volume has. See trap 3 - this is what
                            ; keeps a corrupt size from becoming a very
                            ; long walk

; ----------------------------------------------------------------------
; State. All of it readable through an accessor; none of it meant to be
; poked at from outside.
; ----------------------------------------------------------------------
Global *fat_reader           ; the block reader's address, 0 = unset.
                             ; DECLARED WITH '*' ON PURPOSE - see the
                             ; header. A .i here does not compile.
Global *fat_writer           ; the block writer's address, 0 = unset.
                             ; Same '*' spelling for the same reason,
                             ; and the same "call it with no star" rule.
Global fat_err.i       = #FAT_ERR_NONE
Global fat_lastLba.i   = -1  ; the sector a failed read asked for

Global fat_mounted.i   = 0
Global fat_type.i      = 0   ; 12, 16, 32, or 0 for "not determined"

Global fat_partType.i  = 0
Global fat_partLba.i   = 0   ; SECTORS. Added exactly three times, all
                             ; inside FatMount - see trap 1
Global fat_partSecs.i  = 0

Global fat_bytesPerSec.i  = 0
Global fat_secPerClus.i   = 0
Global fat_clusterBytes.i = 0
Global fat_rsvdSecs.i     = 0
Global fat_numFats.i      = 0
Global fat_fatSecs.i      = 0
Global fat_totSecs.i      = 0
Global fat_rootClus.i     = 0
Global fat_clusterCount.i = 0  ; CountofClusters - and the chain bound
Global fat_activeFat.i    = 0

Global fat_fatLba.i    = 0   ; ABSOLUTE. Start of the active FAT
Global fat_dataLba.i   = 0   ; ABSOLUTE. Where cluster 2 lives

; ----------------------------------------------------------------------
; The write side's own geometry. Every one of these is DERIVED from the
; three above inside FatMount, so trap 1 in the header still holds: the
; only additions of fat_partLba are the ones FatMount makes.
;
; fat_fatBase is spelled as a SUBTRACTION from fat_fatLba rather than as
; "fat_partLba + fat_rsvdSecs" for exactly that reason. It is the same
; number either way and the subtraction keeps the count of places that
; add the partition offset where the header says it is.
; ----------------------------------------------------------------------
Global fat_fatBase.i   = 0   ; ABSOLUTE. Start of FAT copy 0
Global fat_fatEnd.i    = 0   ; ABSOLUTE. One past the last FAT sector
Global fat_dataEnd.i   = 0   ; ABSOLUTE. One past the last data sector
Global fat_mirrorFats.i = 1  ; 1 = every FAT copy is maintained, which
                             ; is what BPB_ExtFlags bit 7 clear means.
                             ; 0 = only fat_activeFat is live

; FSInfo, and the free-space bookkeeping it holds.
Global fat_fsinfoLba.i  = -1 ; ABSOLUTE, or -1 for "there is none"
Global fat_fsinfoOk.i   = 0  ; 1 only when all three signatures matched
Global fat_freeCount.i  = -1 ; -1 = not known yet
Global fat_nextFree.i   = 0  ; the allocation hint; 0 = none
Global fat_freeScanned.i = 0 ; 1 once a full FAT pass produced the count

; The open file.
Global fat_open.i      = 0
Global fat_fileSize.i  = 0
Global fat_firstClus.i = 0
Global fat_curClus.i   = 0   ; the cluster fat_pos currently sits in
Global fat_pos.i       = 0   ; byte offset into the file
Global fat_fileSteps.i = 0   ; chain hops since FatOpen - the loop bound
Global fat_dirSteps.i  = 0   ; the same, for the directory scan
Global fat_attr.i      = 0   ; the open entry's DIR_Attr

; ----------------------------------------------------------------------
; WHERE THE OPEN FILE'S DIRECTORY ENTRY LIVES. This is the whole reason
; the old FatOverwrite could not resize anything: FatOpen found the
; entry, took the size and the first cluster out of it, and threw the
; address away.
;
; It is stored as an ABSOLUTE sector number plus a byte offset inside
; that sector, because that is what a read-modify-write needs and
; because it cannot be confused with a cluster number.
;
; fat_entName is the eleven name bytes as they were when the entry was
; opened. fat_UpdateDirEntry compares them before it writes ANYTHING.
; That check is not paranoia for its own sake: FatDelete and FatCreate
; both move around the same directory, and writing a file size into the
; wrong entry is silent, permanent, and looks exactly like a formatter
; bug afterwards.
; ----------------------------------------------------------------------
Global fat_entLba.i    = -1
Global fat_entOff.i    = -1
Global Dim fat_entName.a[#FAT_NAME_LEN]

; Where fat_FindEntry / fat_FindFreeSlot left their answer. Kept apart
; from fat_entLba/fat_entOff so that a search made while a file is open
; - which is what FatDelete and FatCreate do - cannot quietly move the
; open file's entry pointer onto somebody else's entry.
Global fat_findLba.i   = -1
Global fat_findOff.i   = -1
Global fat_findZeroNext.i = 0 ; 1 when the slot came from the $00 end
                              ; marker and the FOLLOWING slot is in the
                              ; SAME sector, so the caller must zero it
                              ; in the same buffer, in the same write

; ----------------------------------------------------------------------
; THE ROOT-DIRECTORY ITERATOR'S CURSOR AND CURRENT ENTRY. This is the
; state FatDirRewind / FatDirNext keep between calls so a caller can walk
; the root directory one entry at a time - the read side of `fatls`. It
; rides the SAME walk fat_FindEntry does (see THE ROOT-DIRECTORY ITERATOR
; below); these globals are its position in that walk plus the fields of
; the entry it is currently sitting on, captured out of fat_secBuf on
; each step so an accessor never re-reads a buffer a later call may have
; evicted.
;
; It shares fat_secBuf with FatOpen/FatMount, so a listing and an open
; file cannot be interleaved. fat_lsEnd starts 1 - "ended" - so FatDirNext
; before a FatDirRewind returns a clean end rather than walking undefined
; state.
; ----------------------------------------------------------------------
Global fat_lsClus.i    = 0    ; cluster the cursor is in
Global fat_lsSec.i     = 0    ; sector within that cluster, 0..secPerClus-1
Global fat_lsEnt.i     = 0    ; entry within that sector, 0..15
Global fat_lsSteps.i   = 0    ; chain hops taken - the same loop bound
                              ; fat_FindEntry counts against fat_clusterCount
Global fat_lsEnd.i     = 1    ; 1 once the directory has ended
Global fat_lsAttr.i    = 0    ; DIR_Attr of the current entry
Global fat_lsSize.i    = 0    ; DIR_FileSize of the current entry
Global fat_lsFirst.i   = 0    ; first cluster of the current entry
Global Dim fat_lsName.a[#FAT_NAME_LEN]   ; its 11 raw name bytes, $E5-fixed

; The caller's clock, if it has one. See "TIMESTAMPS" in the header.
Global fat_wrDate.i    = #FAT_DATE_SENTINEL
Global fat_wrTime.i    = #FAT_TIME_SENTINEL

; ----------------------------------------------------------------------
; The two buffers, and nothing else. This runs before there is a heap.
;
; Both are cached by LBA so that a directory scan and a chain walk do
; not re-read the same sector for every entry. -1 means "holds nothing".
;
; A Dim array lands 8-byte aligned on this backend, which is more than
; the reader contract's 4 - but that is an OBSERVATION about today's
; emitter, not a promise, so fat_CheckBuffers asserts it at mount time
; rather than trusting it. An unaligned buffer would be refused by
; SdReadBlock with #SD_ERR_ALIGN, which would present as "the card
; failed" and send somebody to the wrong place entirely.
; ----------------------------------------------------------------------
Global Dim fat_secBuf.a[#FAT_SECTOR_SIZE]   ; MBR, boot sector, directory
Global Dim fat_fatBuf.a[#FAT_SECTOR_SIZE]   ; one sector of the FAT
Global fat_secLba.i = -1
Global fat_fatBufLba.i = -1

; The 11-byte 8.3 field FatOpen is looking for, built by fat_MakeName.
Global Dim fat_wantName.a[#FAT_NAME_LEN]

; ======================================================================
;  Failure bookkeeping. One place, so every refusal is recorded the same
;  way and a caller can always ask two questions: what went wrong, and
;  which sector was involved.
; ======================================================================

Procedure.i fat_Fail(code.i)
  fat_err = code
  ProcedureReturn 0
EndProcedure

; ======================================================================
;  LITTLE-ENDIAN, BYTE AT A TIME, UNSIGNED.
;
;  These three are the only way on-disk data enters this file. See trap
;  2 in the header for why they are not 32-bit loads and why they are
;  PeekA and not PeekB.
;
;  Every shift is parenthesised: on this compiler & | ! bind TIGHTER
;  than << >>, so "a | b << 8" would parse as "a | (b << (8))" only by
;  luck of the operand shapes and "1 << 16 | 512" parses as
;  "1 << (16 | 512)". Parentheses everywhere, no exceptions.
; ======================================================================

Procedure.i fat_U8(*p, off.i)
  ProcedureReturn PeekA(*p + off)
EndProcedure

Procedure.i fat_U16(*p, off.i)
  ProcedureReturn ((PeekA(*p + off + 1) << 8) | PeekA(*p + off))
EndProcedure

Procedure.i fat_U32(*p, off.i)
  Define lo.i
  Define hi.i
  lo = ((PeekA(*p + off + 1) << 8) | PeekA(*p + off))
  hi = ((PeekA(*p + off + 3) << 8) | PeekA(*p + off + 2))
  ProcedureReturn ((hi << 16) | lo)
EndProcedure

; ----------------------------------------------------------------------
;  The same three, going the other way. Byte at a time, little end
;  first, for exactly the reasons above: the MBR's 32-bit fields are at
;  2-modulo-4 offsets by construction, and a 32-bit store would be
;  unaligned on half of them. Nothing here ever stores into an MBR, but
;  a pair of helpers where one is byte-wise and the other is not is an
;  invitation, and this file has enough traps already.
;
;  Only the low bytes are taken. A caller that hands fat_PutU16 a value
;  above $FFFF has a bug, but the bug stays inside its own field instead
;  of walking into the next one.
; ----------------------------------------------------------------------
Procedure fat_PutU8(*p, off.i, v.i)
  PokeA(*p + off, v & $FF)
EndProcedure

Procedure fat_PutU16(*p, off.i, v.i)
  PokeA(*p + off,     v & $FF)
  PokeA(*p + off + 1, (v >> 8) & $FF)
EndProcedure

Procedure fat_PutU32(*p, off.i, v.i)
  PokeA(*p + off,     v & $FF)
  PokeA(*p + off + 1, (v >> 8) & $FF)
  PokeA(*p + off + 2, (v >> 16) & $FF)
  PokeA(*p + off + 3, (v >> 24) & $FF)
EndProcedure

Procedure fat_CopyBytes(*dst, *src, n.i)
  Define i.i
  i = 0
  While i < n
    PokeA(*dst + i, PeekA(*src + i))
    i = i + 1
  Wend
EndProcedure

; ======================================================================
;  THE SEAM. Every sector this file ever reads goes through here.
;
;  Returns 1, or 0 with fat_err and fat_lastLba set. A caller that
;  forgets to check gets a buffer full of the PREVIOUS sector, which is
;  why the two cache variables are invalidated BEFORE the read and set
;  only after it succeeds - a failed read can never leave a stale
;  sector looking fresh.
; ======================================================================

Procedure.i fat_ReadRaw(lba.i, *buf)
  Define ok.i
  If *fat_reader = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_READER)
  EndIf
  fat_lastLba = lba
  ok = fat_reader(lba, *buf)
  If ok <> 1
    ProcedureReturn fat_Fail(#FAT_ERR_READ_FAIL)
  EndIf
  ProcedureReturn 1
EndProcedure

; The general-purpose sector, cached: MBR, boot sector, directory.
Procedure.i fat_ReadSec(lba.i)
  If fat_secLba = lba
    ProcedureReturn 1
  EndIf
  fat_secLba = -1
  If fat_ReadRaw(lba, @fat_secBuf[0]) = 0
    ProcedureReturn 0
  EndIf
  fat_secLba = lba
  ProcedureReturn 1
EndProcedure

; One sector of the FAT, cached separately so that walking a chain does
; not evict the directory sector being scanned.
Procedure.i fat_ReadFatSec(lba.i)
  If fat_fatBufLba = lba
    ProcedureReturn 1
  EndIf
  fat_fatBufLba = -1
  If fat_ReadRaw(lba, @fat_fatBuf[0]) = 0
    ProcedureReturn 0
  EndIf
  fat_fatBufLba = lba
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  fat_CheckBuffers - the reader contract says 4-byte aligned, and this
;  is the one place that can be checked before a reader is handed a
;  buffer. See the note on the Dim declarations above.
; ======================================================================
Procedure.i fat_CheckBuffers()
  If (@fat_secBuf[0] & 3) <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_BUF_ALIGN)
  EndIf
  If (@fat_fatBuf[0] & 3) <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_BUF_ALIGN)
  EndIf
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  CLUSTERS
;
;  [FATGEN]: FirstSectorOfCluster = ((N - 2) * SecPerClus) + FirstDataSector
;  The "- 2" is not an off-by-one to be tidied away: cluster numbers 0
;  and 1 are reserved and never name storage, so the data region's first
;  sector IS cluster 2.
; ======================================================================

Procedure.i fat_ClusterValid(cl.i)
  If cl < 2
    ProcedureReturn 0
  EndIf
  If cl > (fat_clusterCount + 1)
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i fat_ClusterLba(cl.i)
  ProcedureReturn (fat_dataLba + ((cl - 2) * fat_secPerClus))
EndProcedure

; ======================================================================
;  fat_NextCluster - one hop along a chain.
;
;  Returns the next cluster, or 0 with fat_err set. A return of 0 is
;  never a valid next cluster (0 means "free" in a FAT), so the caller
;  cannot mistake a failure for data.
;
;  The entry is at byte (cl * 4) into the FAT. That offset is a multiple
;  of four, so a 32-bit load WOULD be aligned here - and it is still
;  read byte-wise, because the rule "on-disk data is assembled from
;  bytes" is worth more than the instruction it saves, and because the
;  moment somebody adds FAT16 support the assumption stops holding.
;
;  THE TOP FOUR BITS ARE RESERVED. [FATGEN] says a FAT32 entry is 28
;  bits and the high nibble must be masked off when reading. Skip the
;  mask and a formatter that leaves those bits set gives cluster numbers
;  that are enormous, fail the range check, and look like corruption.
; ======================================================================

Procedure.i fat_NextCluster(cl.i)
  Define byteOff.i
  Define secOff.i
  Define inSec.i
  Define v.i

  byteOff = cl * 4
  secOff  = byteOff / #FAT_SECTOR_SIZE
  inSec   = byteOff % #FAT_SECTOR_SIZE

  If fat_ReadFatSec(fat_fatLba + secOff) = 0
    ProcedureReturn 0
  EndIf

  v = fat_U32(@fat_fatBuf[0], inSec) & #FAT_ENTRY_MASK
  ProcedureReturn v
EndProcedure

; ======================================================================
;  THE WRITE SEAM, AND THE FENCE AROUND IT
; ======================================================================
;  FatSetBlockWriter is the exact mirror of FatSetBlockReader and takes
;  a procedure of exactly MscWriteBlock's shape:
;
;      Procedure.i Writer(lba.i, *buf)   -> 1 ok, 0 failed
;         writes ONE 512-byte block at logical block address lba from
;         *buf, which is 512 bytes long and 4-BYTE ALIGNED.
;
;  Everything the reader-seam header says applies here too - the arity
;  of an indirect call is not checked, the writer must not call back
;  into this file, and there is no default. Passing 0 turns writing off
;  again, which is what Anvil does the moment its save finishes:
;  a library that can write the boot medium should spend as little of
;  its life able to as possible.
;
;  SETTING A WRITER DOES NOT UNMOUNT. Setting a READER does, because a
;  new reader means a different medium and therefore a different boot
;  sector. A writer is the same medium seen from the other side; if it
;  is not, the caller has wired two different devices together and no
;  check here can rescue that.
; ======================================================================

Procedure FatSetBlockWriter(addr.i)
  *fat_writer = addr
EndProcedure

Procedure.i FatBlockWriter()
  ProcedureReturn *fat_writer
EndProcedure

; ======================================================================
;  fat_LbaWritable - THE FENCE. Read this before changing anything below
;  it.
;
;  This library writes to the medium the machine BOOTS FROM. A cluster
;  number that is one too large, a partition offset dropped from an
;  addition, a FAT sector index computed against the wrong FAT size -
;  every one of those produces a perfectly plausible sector number, and
;  the only thing standing between a plausible wrong sector number and
;  somebody's partition table is this procedure.
;
;  IT IS NOT A RANGE CHECK ON THE PARTITION. It is a whitelist of the
;  three places this file has any business writing:
;
;    * the FSInfo sector, and ONLY if its signatures checked out at
;      mount time
;    * anywhere inside the FAT region - all NumFATs copies of it
;    * anywhere inside the data region, cluster 2 through cluster
;      count+1
;
;  Everything else is refused, including sectors that are inside the
;  partition: the volume boot sector, the backup boot sector, the rest
;  of the reserved region, and the slack after the last cluster. None of
;  those is ever a legitimate destination for this file, so allowing
;  them would only widen what a bug can reach.
;
;  A range check against the partition alone was written first and then
;  replaced. It would have passed a write aimed at the boot sector,
;  which is the single most damaging sector on the volume and sits at
;  the partition's very first LBA - exactly where an arithmetic slip
;  that loses the metadata offset lands.
;
;  The gate proves this by mutation: fat_ClusterLba is broken so that it
;  forgets fat_dataLba, and with this fence in place NOTHING outside the
;  allowed regions is touched. Break the fence as well and the harness
;  sees the partition table change.
; ======================================================================

Procedure.i fat_LbaWritable(lba.i)
  If fat_mounted = 0
    ProcedureReturn 0
  EndIf
  ; Inside the partition first, because the two region tests below are
  ; only meaningful for a mounted volume and this one is meaningful
  ; always.
  If lba < fat_partLba
    ProcedureReturn 0
  EndIf
  If lba >= (fat_partLba + fat_partSecs)
    ProcedureReturn 0
  EndIf
  If fat_fsinfoOk = 1 And lba = fat_fsinfoLba
    ProcedureReturn 1
  EndIf
  If lba >= fat_fatBase And lba < fat_fatEnd
    ProcedureReturn 1
  EndIf
  If lba >= fat_dataLba And lba < fat_dataEnd
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

; ======================================================================
;  fat_WriteRaw - every byte this file ever puts on a medium goes
;  through here, and through the fence above it. Returns 1, or 0 with
;  fat_err and fat_lastLba set.
; ======================================================================

Procedure.i fat_WriteRaw(lba.i, *buf)
  Define ok.i
  If *fat_writer = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_WRITER)
  EndIf
  If fat_LbaWritable(lba) = 0
    fat_lastLba = lba
    ProcedureReturn fat_Fail(#FAT_ERR_LBA_RANGE)
  EndIf
  fat_lastLba = lba
  ok = fat_writer(lba, *buf)
  If ok <> 1
    ProcedureReturn fat_Fail(#FAT_ERR_WRITE_FAIL)
  EndIf
  ProcedureReturn 1
EndProcedure

; Write one of the two cached buffers back and keep its cache tag
; HONEST. After a successful write the buffer and the sector hold the
; same bytes, so the tag is valid and is set; after a failed one nobody
; knows what the medium has, so the tag is thrown away. A stale tag here
; would hand a later read the contents of a sector that was never
; written.
Procedure.i fat_WriteSecBuf(lba.i)
  fat_secLba = -1
  If fat_WriteRaw(lba, @fat_secBuf[0]) = 0
    ProcedureReturn 0
  EndIf
  fat_secLba = lba
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  fat_SetEntry - write one FAT entry, in every copy that is live.
;
;  THREE THINGS HERE ARE NOT OPTIONAL AND EACH ONE IS A DIFFERENT BUG IF
;  DROPPED.
;
;  1. CLUSTER 0 AND CLUSTER 1 ARE NOT STORAGE. Their FAT entries hold
;     the media descriptor and the dirty flags; writing a chain link
;     into either is not "allocating cluster 0", it is corrupting the
;     volume's header. Refused by name with #FAT_ERR_RESERVED_CLUS, and
;     so is any cluster past count+1.
;
;  2. THE TOP FOUR BITS ARE READ-MODIFY-WRITE. [FATGEN] says the high
;     nibble of a FAT32 entry is reserved and that a driver must
;     PRESERVE it on write, not just ignore it on read. So the sector is
;     read, the low 28 bits are replaced, and the high 4 are carried
;     over from whatever was there.
;
;  3. THE MIRRORS. See "THE SECOND FAT" in the header for the decision.
;     BPB_ExtFlags bit 7 clear means every copy is live and every copy
;     gets written; bit 7 set means only fat_activeFat is maintained and
;     the others are deliberately left alone.
;
;  The sector is read from the ACTIVE copy and written to all of them,
;  which means that if the copies had already diverged this drags them
;  back together toward the one the read path uses. That is the right
;  direction: the active FAT is by definition the truth on this volume.
; ======================================================================

Procedure.i fat_SetEntry(cl.i, val.i)
  Define byteOff.i
  Define secOff.i
  Define inSec.i
  Define old.i
  Define nv.i
  Define i.i
  Define lba.i

  If cl < 2 Or cl > (fat_clusterCount + 1)
    ProcedureReturn fat_Fail(#FAT_ERR_RESERVED_CLUS)
  EndIf

  byteOff = cl * 4
  secOff  = byteOff / #FAT_SECTOR_SIZE
  inSec   = byteOff % #FAT_SECTOR_SIZE
  If secOff >= fat_fatSecs
    ; The volume says its FAT is fat_fatSecs sectors long and this entry
    ; is past the end of it. That is a contradiction between BPB_FATSz32
    ; and the cluster count, and writing there would land in the second
    ; copy of the FAT.
    ProcedureReturn fat_Fail(#FAT_ERR_RESERVED_CLUS)
  EndIf

  If fat_ReadFatSec(fat_fatLba + secOff) = 0
    ProcedureReturn 0
  EndIf
  old = fat_U32(@fat_fatBuf[0], inSec)
  nv  = (old & #FAT_CLUS_RSVD) | (val & #FAT_ENTRY_MASK)
  fat_PutU32(@fat_fatBuf[0], inSec, nv)

  If fat_mirrorFats = 1
    i = 0
    While i < fat_numFats
      lba = fat_fatBase + (i * fat_fatSecs) + secOff
      fat_fatBufLba = -1
      If fat_WriteRaw(lba, @fat_fatBuf[0]) = 0
        ProcedureReturn 0
      EndIf
      i = i + 1
    Wend
  Else
    fat_fatBufLba = -1
    If fat_WriteRaw(fat_fatLba + secOff, @fat_fatBuf[0]) = 0
      ProcedureReturn 0
    EndIf
  EndIf

  ; The buffer now matches the ACTIVE copy on the medium, which is the
  ; only one fat_ReadFatSec ever reads.
  fat_fatBufLba = fat_fatLba + secOff
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  FSInfo
; ======================================================================
;  fat_ReadFsInfo - called once, at the end of FatMount, and never
;  again. It does not fail a mount: a volume with a damaged FSInfo is
;  still perfectly readable and still perfectly writable, because
;  everything in FSInfo is recoverable by reading the FAT.
;
;  What it CAN do is decide that the sector the BPB points at is not an
;  FSInfo sector, in which case this file will not write there. That
;  refusal is the point. BPB_FSInfo is a 16-bit field; a value of 6 -
;  which is where the BACKUP BOOT SECTOR conventionally lives - is not
;  distinguishable from a legitimate 1 by anything except the three
;  signatures, and rewriting the backup boot sector with a free-cluster
;  count would be a very quiet disaster.
; ======================================================================

Procedure.i fat_ReadFsInfo(fsiSec.i)
  Define *p
  Define fc.i
  Define nf.i

  fat_fsinfoLba   = -1
  fat_fsinfoOk    = 0
  fat_freeCount   = -1
  fat_nextFree    = 0
  fat_freeScanned = 0

  ; [FATGEN]: 0 and $FFFF both mean there is no FSInfo structure.
  If fsiSec = 0 Or fsiSec = $FFFF
    ProcedureReturn 1
  EndIf
  ; It has to be INSIDE the reserved region, and it cannot be the boot
  ; sector itself.
  If fsiSec < 1 Or fsiSec >= fat_rsvdSecs
    ProcedureReturn fat_Fail(#FAT_ERR_FSINFO)
  EndIf

  ; THE FOURTH AND LAST PLACE fat_partLba IS ADDED TO ANYTHING, and the
  ; header's trap 1 says so. It is here rather than derived because
  ; FSInfo's sector number is relative to the volume, like the BPB's own
  ; fields, and pretending otherwise to keep a count of three would be
  ; the sort of tidy that costs a weekend.
  If fat_ReadSec(fat_partLba + fsiSec) = 0
    ProcedureReturn 0
  EndIf
  *p = @fat_secBuf[0]

  If fat_U32(*p, #FAT_FSI_LEADSIG_OFF) <> #FAT_FSI_LEADSIG
    ProcedureReturn fat_Fail(#FAT_ERR_FSINFO)
  EndIf
  If fat_U32(*p, #FAT_FSI_STRUCSIG_OFF) <> #FAT_FSI_STRUCSIG
    ProcedureReturn fat_Fail(#FAT_ERR_FSINFO)
  EndIf
  If fat_U32(*p, #FAT_FSI_TRAILSIG_OFF) <> #FAT_FSI_TRAILSIG
    ProcedureReturn fat_Fail(#FAT_ERR_FSINFO)
  EndIf

  fat_fsinfoLba = fat_partLba + fsiSec
  fat_fsinfoOk  = 1

  ; The two hints. [FATGEN] calls them "not necessarily correct" and
  ; says a driver must range-check them, which is what these two tests
  ; are. $FFFFFFFF is the spec's own "unknown" and needs no special case
  ; - it fails both range tests on any volume smaller than 4 G clusters,
  ; and it is tested for by name anyway so that the reason is readable.
  fc = fat_U32(*p, #FAT_FSI_FREE_COUNT)
  nf = fat_U32(*p, #FAT_FSI_NXT_FREE)

  If fc <> #FAT_FSI_UNKNOWN And fc <= fat_clusterCount
    fat_freeCount = fc
  Else
    fat_freeCount = -1
  EndIf
  If nf <> #FAT_FSI_UNKNOWN And nf >= 2 And nf <= (fat_clusterCount + 1)
    fat_nextFree = nf
  Else
    fat_nextFree = 0
  EndIf

  ProcedureReturn 1
EndProcedure

; Push the two hints back out. Silently does nothing when there is no
; FSInfo sector to write - which is not a silent no-op of the kind this
; project bans, because there is nothing being asked for: a volume
; without FSInfo is complete without it, and [FATGEN] permits one.
Procedure.i fat_WriteFsInfo()
  Define v.i
  If fat_fsinfoOk = 0
    ProcedureReturn 1
  EndIf
  If fat_ReadSec(fat_fsinfoLba) = 0
    ProcedureReturn 0
  EndIf
  ; Read-modify-write, so the signatures and the two reserved runs come
  ; back exactly as they were. Only eight bytes of this sector are ours.
  If fat_freeCount < 0
    v = #FAT_FSI_UNKNOWN
  Else
    v = fat_freeCount
  EndIf
  fat_PutU32(@fat_secBuf[0], #FAT_FSI_FREE_COUNT, v)
  If fat_nextFree < 2
    v = #FAT_FSI_UNKNOWN
  Else
    v = fat_nextFree
  EndIf
  fat_PutU32(@fat_secBuf[0], #FAT_FSI_NXT_FREE, v)
  ProcedureReturn fat_WriteSecBuf(fat_fsinfoLba)
EndProcedure

; ======================================================================
;  fat_ScanFree - the rebuild. One pass over every FAT entry from
;  cluster 2 to cluster count+1, counting the zeros and remembering the
;  first one.
;
;  IT IS EXPENSIVE AND IT IS RUN AS SELDOM AS POSSIBLE. A FAT32 volume
;  has at least 65525 clusters by definition, so this reads at least 512
;  sectors and touches at least 65525 entries. It happens on the first
;  allocation or free after a mount whose FSInfo did not hand over a
;  usable free count, and then never again for that mount.
;
;  IT IS WALKED BY SECTOR, NOT BY CLUSTER. Calling fat_NextCluster once
;  per cluster would be the obvious spelling and would redo a divide, a
;  modulo, a cache compare and a procedure call for every one of 65525
;  entries. Reading a sector and then stepping four bytes at a time
;  through it is the same arithmetic done once per 128 clusters.
;
;  THE INNER LOOP DOES NOT CALL fat_U32 EITHER, and that is worth a
;  sentence because it looks like the rule being bent. It is not: the
;  bytes are still read one at a time, little end first and unsigned,
;  which is the whole content of the rule. What is skipped is the CALL,
;  and on the emulator the difference over 65525 entries was about six
;  to one - the gate went from 74 seconds to well under twenty. A rule
;  about how bytes are read is not a rule about calling a procedure to
;  read them.
;
;  It also does not ASSEMBLE the value, because it does not need it.
;  "Is this entry free" is "are the low 28 bits all zero", and OR-ing
;  three bytes together with the low nibble of the fourth answers that
;  without a single shift. The top four bits are reserved and MUST be
;  ignored here exactly as they are in fat_NextCluster - a formatter
;  that leaves them set on a free cluster would otherwise make the whole
;  volume look full.
; ======================================================================

Procedure.i fat_ScanFree()
  Define cl.i
  Define secOff.i
  Define inSec.i
  Define free.i
  Define first.i
  Define last.i
  Define *p

  free  = 0
  first = 0
  last  = fat_clusterCount + 1
  cl    = 2

  While cl <= last
    secOff = (cl * 4) / #FAT_SECTOR_SIZE
    If secOff >= fat_fatSecs
      ; The FAT is too short to hold an entry for a cluster the volume
      ; says it has. Same contradiction fat_SetEntry refuses, and it is
      ; refused here too rather than counted as free space.
      ProcedureReturn fat_Fail(#FAT_ERR_RESERVED_CLUS)
    EndIf
    If fat_ReadFatSec(fat_fatLba + secOff) = 0
      ProcedureReturn 0
    EndIf
    inSec = (cl * 4) % #FAT_SECTOR_SIZE
    *p    = @fat_fatBuf[0] + inSec
    While inSec < #FAT_SECTOR_SIZE And cl <= last
      If (PeekA(*p) | PeekA(*p + 1) | PeekA(*p + 2) | (PeekA(*p + 3) & $0F)) = 0
        free = free + 1
        If first = 0
          first = cl
        EndIf
      EndIf
      *p    = *p + 4
      inSec = inSec + 4
      cl    = cl + 1
    Wend
  Wend

  fat_freeCount   = free
  fat_nextFree    = first        ; 0 when the volume is completely full
  fat_freeScanned = 1
  ProcedureReturn 1
EndProcedure

; Make sure the free bookkeeping is trustworthy before it is used or
; changed. This is where "honour the hint when it is valid, rebuild it
; when it is not" actually happens.
Procedure.i fat_EnsureFreeInfo()
  If fat_freeScanned = 1
    ProcedureReturn 1
  EndIf
  If fat_freeCount >= 0
    ; FSInfo handed over a count that passed its range check. [FATGEN]
    ; says to believe it, and believing it is what makes an allocation
    ; on a 2 GB volume cost one sector read instead of 512.
    ;
    ; WHAT THIS CANNOT CATCH, said plainly: a count that is in range and
    ; simply wrong. Nothing short of the full scan can, and doing the
    ; full scan every mount would make the hint pointless. The scan is
    ; one call away for a caller that wants certainty - FatRescanFree().
    ProcedureReturn 1
  EndIf
  ProcedureReturn fat_ScanFree()
EndProcedure

; ======================================================================
;  fat_AllocCluster - find a free cluster, claim it, and link it on.
;
;  Returns the cluster number, or 0 with fat_err set. 0 can never be a
;  real answer, because cluster 0 is not storage.
;
;  prev is the cluster to link FROM, or 0 for "this is the first cluster
;  of a chain and nothing points at it yet".
;
;  THE ORDER OF THE TWO FAT WRITES IS THE WHOLE SAFETY ARGUMENT.
;
;    1. the new cluster's own entry gets the end-of-chain mark, which is
;       what CLAIMS it. From this instant the allocator cannot hand it
;       out again.
;    2. only then does prev's entry get pointed at it.
;
;  Do it the other way round and a crash between the two leaves a live
;  file whose chain runs into a cluster the FAT says is FREE. The next
;  allocation hands that cluster to somebody else and now two files
;  share it - which is the one FAT failure that a repair tool cannot
;  undo without picking a loser.
;
;  It also breaks WITHOUT a crash, and that is the version the gate
;  measures: growing a file by three clusters in one call asks this
;  procedure for three clusters in a row, and if the claim comes after
;  the link then all three scans find the same free cluster and the
;  chain comes out pointing at itself. The library's own loop check
;  catches it - which is the right answer arriving for the wrong reason.
; ======================================================================

Procedure.i fat_AllocCluster(prev.i)
  Define cl.i
  Define tried.i
  Define v.i
  Define last.i

  If fat_EnsureFreeInfo() = 0
    ProcedureReturn 0
  EndIf

  last = fat_clusterCount + 1
  If fat_nextFree >= 2 And fat_nextFree <= last
    cl = fat_nextFree
  Else
    cl = 2
  EndIf

  ; THE BOUND. One attempt per cluster the volume has, and then it is
  ; out of space - by the pigeonhole principle, not by hope. A scan that
  ; wrapped without a counter would spin forever on a full volume.
  tried = 0
  While tried <= fat_clusterCount
    v = fat_NextCluster(cl)
    If fat_err <> #FAT_ERR_NONE
      ProcedureReturn 0
    EndIf
    If v = #FAT_CLUS_FREE
      If fat_SetEntry(cl, #FAT_CLUS_EOC_W) = 0
        ProcedureReturn 0
      EndIf
      If prev <> 0
        If fat_SetEntry(prev, cl) = 0
          ProcedureReturn 0
        EndIf
      EndIf
      fat_nextFree = cl + 1
      If fat_nextFree > last
        fat_nextFree = 2
      EndIf
      If fat_freeCount > 0
        fat_freeCount = fat_freeCount - 1
      EndIf
      ProcedureReturn cl
    EndIf
    cl = cl + 1
    If cl > last
      cl = 2
    EndIf
    tried = tried + 1
  Wend

  ProcedureReturn fat_Fail(#FAT_ERR_NO_SPACE)
EndProcedure

; ======================================================================
;  fat_ZeroCluster - fill every sector of a cluster with zero bytes.
;
;  Only ever used on a cluster that is about to become part of a
;  DIRECTORY. A data cluster is left with whatever it had, because the
;  caller is about to write over it and zeroing first would double every
;  write; a directory cluster is different, because a directory is read
;  until it hits a $00 entry and one full of somebody's old file
;  contents has no $00 entry in it at all.
; ======================================================================

Procedure.i fat_ZeroCluster(cl.i)
  Define i.i
  Define sec.i
  Define lba.i
  If fat_ClusterValid(cl) = 0
    ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
  EndIf
  i = 0
  While i < #FAT_SECTOR_SIZE
    fat_secBuf[i] = 0
    i = i + 1
  Wend
  lba = fat_ClusterLba(cl)
  sec = 0
  While sec < fat_secPerClus
    If fat_WriteSecBuf(lba + sec) = 0
      ProcedureReturn 0
    EndIf
    sec = sec + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  fat_FreeChain - return a run of clusters to the free pool.
;
;  start is the first cluster to free. Walking stops at an end-of-chain
;  mark, at a bad-cluster mark, or at anything that is not a valid
;  cluster number - and every one of those is a normal end, not an
;  error, because this is called on the TAIL of a chain that has already
;  been cut loose and the tail's last entry is by definition an EOC.
;
;  THE NEXT LINK IS READ BEFORE THE ENTRY IS ZEROED. Obvious once
;  written down and easy to get backwards; zero first and the walk has
;  no idea where it was going.
;
;  BOUNDED, like every other walk in this file. A tail that loops gets
;  partially freed and then refused with #FAT_ERR_CHAINLOOP. Partially
;  freed is lost clusters, which a repair tool fixes; walking forever is
;  a board that has to be power-cycled.
; ======================================================================

Procedure.i fat_FreeChain(start.i)
  Define cl.i
  Define nxt.i
  Define steps.i
  Define freed.i

  cl    = start
  steps = 0
  freed = 0

  While 1
    If cl = #FAT_CLUS_FREE
      Break
    EndIf
    If cl >= #FAT_CLUS_EOC
      Break
    EndIf
    If cl = #FAT_CLUS_BAD
      ; A defective-cluster mark is not free space and must not be
      ; handed out again. Stop here and leave it marked.
      Break
    EndIf
    If fat_ClusterValid(cl) = 0
      ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
    EndIf

    nxt = fat_NextCluster(cl)
    If fat_err <> #FAT_ERR_NONE
      ProcedureReturn 0
    EndIf
    If fat_SetEntry(cl, #FAT_CLUS_FREE) = 0
      ProcedureReturn 0
    EndIf
    freed = freed + 1

    ; A freed cluster is a better hint than whatever we had, if it is
    ; lower - allocation scans upward from the hint.
    If fat_nextFree < 2 Or cl < fat_nextFree
      fat_nextFree = cl
    EndIf

    If nxt = cl
      ProcedureReturn fat_Fail(#FAT_ERR_CHAINLOOP)
    EndIf
    steps = steps + 1
    If steps > fat_clusterCount
      ProcedureReturn fat_Fail(#FAT_ERR_CHAINLOOP)
    EndIf
    cl = nxt
  Wend

  If fat_freeCount >= 0
    fat_freeCount = fat_freeCount + freed
  EndIf
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  8.3 NAME NORMALISATION
;
;  "pmf.img" -> the 11 bytes  P M F <sp> <sp> <sp> <sp> <sp> I M G
;
;  Returns 1, or 0 with #FAT_ERR_NAME. It REFUSES rather than truncates:
;  silently cutting "verylongname.img" down to "VERYLONG" would open a
;  different file than the one asked for, which is the worst possible
;  outcome for a loader.
;
;  A path separator is refused here too, so that FatOpen("boot/pmf.img")
;  says "that name is not usable" rather than "not found" - the second
;  answer sends somebody looking for a missing file instead of for the
;  missing feature.
; ======================================================================

Procedure.i fat_IsNameChar(c.i)
  ; [FATGEN] lists the characters a short name may NOT contain. Refuse
  ; anything below $20, the DEL at $7F, and the punctuation set. '.' is
  ; handled by the caller as the separator, so it is refused here.
  If c < 32
    ProcedureReturn 0
  EndIf
  If c = 127
    ProcedureReturn 0
  EndIf
  If c = 32     ; space - legal as PADDING, never as a character
    ProcedureReturn 0
  EndIf
  If c = 34     ; "
    ProcedureReturn 0
  EndIf
  If c = 42     ; *
    ProcedureReturn 0
  EndIf
  If c = 43     ; +
    ProcedureReturn 0
  EndIf
  If c = 44     ; ,
    ProcedureReturn 0
  EndIf
  If c = 46     ; .
    ProcedureReturn 0
  EndIf
  If c = 47     ; /
    ProcedureReturn 0
  EndIf
  If c = 58     ; :
    ProcedureReturn 0
  EndIf
  If c = 59     ; ;
    ProcedureReturn 0
  EndIf
  If c = 60     ; <
    ProcedureReturn 0
  EndIf
  If c = 61     ; =
    ProcedureReturn 0
  EndIf
  If c = 62     ; >
    ProcedureReturn 0
  EndIf
  If c = 63     ; ?
    ProcedureReturn 0
  EndIf
  If c = 91     ; [
    ProcedureReturn 0
  EndIf
  If c = 92     ; backslash
    ProcedureReturn 0
  EndIf
  If c = 93     ; ]
    ProcedureReturn 0
  EndIf
  If c = 124    ; |
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i fat_MakeName(*name)
  Define i.i
  Define c.i
  Define n.i
  Define dot.i
  Define baseLen.i
  Define extLen.i

  ; Start from eleven spaces - the padding [FATGEN] specifies.
  i = 0
  While i < #FAT_NAME_LEN
    fat_wantName[i] = 32
    i = i + 1
  Wend

  If *name = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NAME)
  EndIf

  ; Length, and where the single dot is. More than one dot is not an
  ; 8.3 name.
  n   = 0
  dot = -1
  While PeekA(*name + n) <> 0
    c = PeekA(*name + n)
    If c = 46
      If dot >= 0
        ProcedureReturn fat_Fail(#FAT_ERR_NAME)
      EndIf
      dot = n
    EndIf
    n = n + 1
    If n > 64
      ProcedureReturn fat_Fail(#FAT_ERR_NAME)
    EndIf
  Wend
  If n = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NAME)
  EndIf

  If dot < 0
    baseLen = n
    extLen  = 0
  Else
    baseLen = dot
    extLen  = n - dot - 1
  EndIf

  If baseLen < 1 Or baseLen > #FAT_NAME_BASE_MAX
    ProcedureReturn fat_Fail(#FAT_ERR_NAME)
  EndIf
  If extLen > #FAT_NAME_EXT_MAX
    ProcedureReturn fat_Fail(#FAT_ERR_NAME)
  EndIf

  ; The base, uppercased into slots 0..7.
  i = 0
  While i < baseLen
    c = PeekA(*name + i)
    If c >= 97 And c <= 122
      c = c - 32
    EndIf
    If fat_IsNameChar(c) = 0
      ProcedureReturn fat_Fail(#FAT_ERR_NAME)
    EndIf
    fat_wantName[i] = c
    i = i + 1
  Wend

  ; The extension, uppercased into slots 8..10.
  i = 0
  While i < extLen
    c = PeekA(*name + dot + 1 + i)
    If c >= 97 And c <= 122
      c = c - 32
    EndIf
    If fat_IsNameChar(c) = 0
      ProcedureReturn fat_Fail(#FAT_ERR_NAME)
    EndIf
    fat_wantName[8 + i] = c
    i = i + 1
  Wend

  ; [FATGEN]: a name whose first byte is really $E5 is stored as $05,
  ; because $E5 in that position means "deleted". Nothing reachable
  ; through this API can produce $E5 - it is not ASCII and
  ; fat_IsNameChar would have refused it - so this is unreachable today
  ; and is written down rather than coded, to be honest about which
  ; direction of the substitution is handled: the READ direction, in
  ; fat_EntryMatches, is the one that matters and it is there.

  ProcedureReturn 1
EndProcedure

; Compare the 11 name bytes of a directory entry at *e with fat_wantName.
Procedure.i fat_EntryMatches(*e)
  Define i.i
  Define a.i
  Define b.i
  i = 0
  While i < #FAT_NAME_LEN
    a = PeekA(*e + i)
    b = fat_wantName[i]
    ; A stored $05 in the FIRST byte means a real leading $E5.
    If i = 0 And a = #FAT_DIRENT_E5
      a = #FAT_DIRENT_FREE
    EndIf
    If a <> b
      ProcedureReturn 0
    EndIf
    i = i + 1
  Wend
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PUBLIC - FatSetBlockReader(addr)
;
;  addr is the address of a procedure with the SdReadBlock signature:
;
;      Procedure.i Reader(lba.i, *buf)   -> 1 ok, 0 failed
;
;  Pass @SdReadBlock to read the SD card. Pass the address of your own
;  procedure to read anything else - a USB mass-storage device, a RAM
;  image, a fabricated test volume.
;
;  Setting a new reader UNMOUNTS. Two media do not share a boot sector,
;  and a mount left standing over a swapped reader is a filesystem that
;  describes a volume nobody is reading any more.
; ======================================================================

Procedure FatSetBlockReader(addr.i)
  *fat_reader    = addr
  fat_mounted    = 0
  fat_open       = 0
  fat_secLba     = -1
  fat_fatBufLba  = -1
  fat_err        = #FAT_ERR_NONE
EndProcedure

Procedure.i FatBlockReader()
  ProcedureReturn *fat_reader
EndProcedure

; ======================================================================
;  PUBLIC - FatMount(partition)
;
;  partition is 1..4, the MBR primary partition slot, counted the way
;  U-Boot counts it: "fatload usb 0:1" is FatMount(1).
;
;  Returns 1, or 0 with FatLastError() set.
;
;  This reads exactly two sectors: the MBR at LBA 0, and the volume's
;  own first sector at the partition's start LBA.
; ======================================================================
Procedure.i FatMount(partition.i)
  Define *mbr
  Define *bs
  Define peOff.i
  Define status.i
  Define rootEntCnt.i
  Define fatSz16.i
  Define totSec16.i
  Define rootDirSecs.i
  Define metaSecs.i
  Define dataSecs.i
  Define extFlags.i
  Define spc.i
  Define fsiSec.i

  fat_mounted = 0
  fat_open    = 0
  fat_type    = 0
  fat_err     = #FAT_ERR_NONE
  fat_secLba    = -1
  fat_fatBufLba = -1

  ; The write side's state belongs to a volume, not to the library. A
  ; mount that lands on a different medium must not inherit the previous
  ; one's free-cluster hint or - far worse - the sector number of a
  ; directory entry that existed on some other disk.
  fat_fsinfoLba   = -1
  fat_fsinfoOk    = 0
  fat_freeCount   = -1
  fat_nextFree    = 0
  fat_freeScanned = 0
  fat_entLba      = -1
  fat_entOff      = -1
  fat_findLba     = -1
  fat_findOff     = -1
  fat_attr        = 0

  If *fat_reader = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_READER)
  EndIf
  If fat_CheckBuffers() = 0
    ProcedureReturn 0
  EndIf
  If partition < 1 Or partition > 4
    ProcedureReturn fat_Fail(#FAT_ERR_PARTNUM)
  EndIf

  ; ---- the MBR ------------------------------------------------------
  If fat_ReadSec(0) = 0
    ProcedureReturn 0
  EndIf
  *mbr = @fat_secBuf[0]

  If fat_U8(*mbr, #FAT_MBR_SIG_OFF) <> $55 Or fat_U8(*mbr, #FAT_MBR_SIG_OFF + 1) <> $AA
    ProcedureReturn fat_Fail(#FAT_ERR_NO_MBR)
  EndIf

  ; $1BE + 16*(n-1). The multiply is written out rather than folded into
  ; a constant because the "- 1" is the U-Boot-facing numbering and it
  ; belongs in view.
  peOff = #FAT_MBR_PART0 + ((partition - 1) * #FAT_MBR_PART_SIZE)

  status = fat_U8(*mbr, peOff + #FAT_PE_STATUS)
  If status <> $00 And status <> $80
    ; [MBR]: the status byte is $80 for the active partition and $00 for
    ; the rest. Anything else means the $55 $AA was a coincidence and
    ; this is not a partition table - which is exactly what a FAT boot
    ; sector at LBA 0 (a "superfloppy", no MBR) looks like from here.
    ProcedureReturn fat_Fail(#FAT_ERR_PART_STATUS)
  EndIf

  fat_partType = fat_U8(*mbr, peOff + #FAT_PE_TYPE)
  If fat_partType = #FAT_PT_EMPTY
    ProcedureReturn fat_Fail(#FAT_ERR_PART_EMPTY)
  EndIf
  If fat_partType = #FAT_PT_GPT
    ProcedureReturn fat_Fail(#FAT_ERR_PART_GPT)
  EndIf
  If fat_partType <> #FAT_PT_FAT32_CHS And fat_partType <> #FAT_PT_FAT32_LBA
    ; Named rather than attempted. A $06 or $0E partition really is a
    ; FAT16 volume and reading it as FAT32 would produce a plausible
    ; boot sector and a wrong root directory.
    ProcedureReturn fat_Fail(#FAT_ERR_PART_TYPE)
  EndIf

  fat_partLba  = fat_U32(*mbr, peOff + #FAT_PE_LBA)
  fat_partSecs = fat_U32(*mbr, peOff + #FAT_PE_COUNT)
  If fat_partLba = 0 Or fat_partSecs = 0
    ; A partition cannot start at LBA 0 - that is the MBR itself.
    ProcedureReturn fat_Fail(#FAT_ERR_PART_GEOM)
  EndIf

  ; ---- the volume's boot sector -------------------------------------
  ; THE ONE ADDITION OF fat_partLba THAT MATTERS. Everything the BPB
  ; says is relative to THIS sector.
  If fat_ReadSec(fat_partLba) = 0
    ProcedureReturn 0
  EndIf
  *bs = @fat_secBuf[0]

  If fat_U8(*bs, #FAT_MBR_SIG_OFF) <> $55 Or fat_U8(*bs, #FAT_MBR_SIG_OFF + 1) <> $AA
    ProcedureReturn fat_Fail(#FAT_ERR_NO_BOOTSEC)
  EndIf

  fat_bytesPerSec = fat_U16(*bs, #FAT_BPB_BYTSPERSEC)
  If fat_bytesPerSec <> #FAT_SECTOR_SIZE
    ; 1024, 2048 and 4096 are legal in [FATGEN] and none of them can be
    ; read through a block reader that returns 512 bytes. Refused rather
    ; than read as 512, which would shred every offset in the volume.
    ProcedureReturn fat_Fail(#FAT_ERR_SECSIZE)
  EndIf

  spc = fat_U8(*bs, #FAT_BPB_SECPERCLUS)
  If spc < 1 Or spc > 128
    ProcedureReturn fat_Fail(#FAT_ERR_SPC)
  EndIf
  ; [FATGEN]: SecPerClus must be a power of two. "x & (x-1)" is zero for
  ; exactly the powers of two, and a non-power-of-two here would make
  ; every cluster-to-sector conversion below wrong in a way that still
  ; produces sector numbers.
  If (spc & (spc - 1)) <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_SPC)
  EndIf
  fat_secPerClus   = spc
  fat_clusterBytes = spc * #FAT_SECTOR_SIZE

  fat_rsvdSecs = fat_U16(*bs, #FAT_BPB_RSVDSECCNT)
  If fat_rsvdSecs < 1
    ProcedureReturn fat_Fail(#FAT_ERR_RESERVED)
  EndIf

  fat_numFats = fat_U8(*bs, #FAT_BPB_NUMFATS)
  If fat_numFats < 1
    ProcedureReturn fat_Fail(#FAT_ERR_NUMFATS)
  EndIf

  rootEntCnt = fat_U16(*bs, #FAT_BPB_ROOTENTCNT)
  fatSz16    = fat_U16(*bs, #FAT_BPB_FATSZ16)
  totSec16   = fat_U16(*bs, #FAT_BPB_TOTSEC16)

  ; ---- the FAT type ladder, [FATGEN] --------------------------------
  ; Computed BEFORE anything FAT32-specific is read, because the whole
  ; point is that the answer decides which fields are even meaningful.
  ; RootDirSectors is 0 on FAT32 and nonzero on FAT12/FAT16; the formula
  ; is written in full so the same code path produces both.
  rootDirSecs = ((rootEntCnt * #FAT_DIRENT_SIZE) + (fat_bytesPerSec - 1)) / fat_bytesPerSec

  fat_fatSecs = fatSz16
  If fat_fatSecs = 0
    fat_fatSecs = fat_U32(*bs, #FAT_BPB_FATSZ32)
  EndIf
  If fat_fatSecs = 0
    ProcedureReturn fat_Fail(#FAT_ERR_FATSZ)
  EndIf

  fat_totSecs = totSec16
  If fat_totSecs = 0
    fat_totSecs = fat_U32(*bs, #FAT_BPB_TOTSEC32)
  EndIf
  If fat_totSecs = 0
    ProcedureReturn fat_Fail(#FAT_ERR_TOTSEC)
  EndIf

  metaSecs = fat_rsvdSecs + (fat_numFats * fat_fatSecs) + rootDirSecs
  If metaSecs >= fat_totSecs
    ProcedureReturn fat_Fail(#FAT_ERR_GEOMETRY)
  EndIf
  If fat_totSecs > fat_partSecs
    ; The BPB claims more sectors than the partition table gave it. One
    ; of the two is lying and reading past the partition is not a repair.
    ProcedureReturn fat_Fail(#FAT_ERR_GEOMETRY)
  EndIf

  dataSecs          = fat_totSecs - metaSecs
  fat_clusterCount  = dataSecs / fat_secPerClus

  If fat_clusterCount <= #FAT_MAX_FAT12_CLUSTERS
    fat_type = 12
    ProcedureReturn fat_Fail(#FAT_ERR_FAT12)
  EndIf
  If fat_clusterCount <= #FAT_MAX_FAT16_CLUSTERS
    fat_type = 16
    ProcedureReturn fat_Fail(#FAT_ERR_FAT16)
  EndIf
  fat_type = 32

  ; ---- FAT32-only fields, now that the type is settled ---------------
  If rootEntCnt <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_ROOTENT)
  EndIf
  If fatSz16 <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_FATSZ16)
  EndIf
  If fat_U16(*bs, #FAT_BPB_FSVER) <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_FSVER)
  EndIf

  ; [FATGEN] BPB_ExtFlags: bit 7 clear means all FATs are mirrored and
  ; the first one is as good as any; bit 7 set means only ONE is live
  ; and bits 3:0 say which. Reading a stale mirror gives a chain that
  ; was correct at some point in the past, which is the worst kind of
  ; wrong - so the field is honoured rather than ignored.
  extFlags = fat_U16(*bs, #FAT_BPB_EXTFLAGS)
  If (extFlags & $0080) = 0
    fat_activeFat  = 0
    fat_mirrorFats = 1
  Else
    fat_activeFat  = extFlags & $000F
    fat_mirrorFats = 0
    If fat_activeFat >= fat_numFats
      ProcedureReturn fat_Fail(#FAT_ERR_ACTIVEFAT)
    EndIf
  EndIf

  ; ---- the two absolute LBAs ----------------------------------------
  ; The SECOND and THIRD uses of fat_partLba. Past this point every
  ; sector number in this file is absolute. There is now a FOURTH, in
  ; fat_ReadFsInfo below, and the header says so.
  fat_fatLba  = fat_partLba + fat_rsvdSecs + (fat_activeFat * fat_fatSecs)
  fat_dataLba = fat_partLba + metaSecs

  ; The write side's fence posts, all DERIVED so that no new addition of
  ; fat_partLba is needed. fat_fatBase walks back from the active FAT to
  ; copy 0; fat_dataEnd is where cluster count+1 ends, which is NOT the
  ; end of the partition - a volume's last few sectors are usually slack
  ; that does not make up a whole cluster, and nothing may be written
  ; there.
  fat_fatBase = fat_fatLba - (fat_activeFat * fat_fatSecs)
  fat_fatEnd  = fat_fatBase + (fat_numFats * fat_fatSecs)
  fat_dataEnd = fat_dataLba + (fat_clusterCount * fat_secPerClus)

  fat_rootClus = fat_U32(*bs, #FAT_BPB_ROOTCLUS)
  If fat_ClusterValid(fat_rootClus) = 0
    ProcedureReturn fat_Fail(#FAT_ERR_ROOTCLUS)
  EndIf

  ; ---- FSInfo -------------------------------------------------------
  ; LAST, because it needs fat_clusterCount to range-check the hints and
  ; because a volume whose FSInfo is damaged still mounts. fsiSec is
  ; read out of *bs before the call, since fat_ReadFsInfo reads a sector
  ; into the same buffer *bs points at.
  fsiSec = fat_U16(*bs, #FAT_BPB_FSINFO)
  If fat_ReadFsInfo(fsiSec) = 0
    ; The signature check failed, or the sector would not read. Neither
    ; stops a mount - but fat_err is left holding #FAT_ERR_FSINFO so a
    ; caller that asks gets told, and fat_fsinfoOk stays 0 so nothing
    ; here will ever write to that sector. Say it out loud rather than
    ; letting a mount look clean when part of it was refused.
    fat_mounted = 1
    ProcedureReturn 1
  EndIf

  fat_mounted = 1
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PUBLIC - FatOpen(name)
;
;  name is an 8.3 short name in the ROOT directory: "PMF.IMG",
;  "KERNEL8.IMG", "CONFIG.TXT". Case does not matter. Returns 1, or 0
;  with FatLastError() set.
;
;  Opening closes whatever was open. There is one file at a time, which
;  is all a loader needs and is one fewer thing to get wrong.
;
;  THE SCAN SKIPS THREE THINGS AND STOPS AT A FOURTH, and getting any of
;  them wrong is a file that cannot be found or a name read out of the
;  wrong bytes:
;
;    $E5 first byte   -> DELETED. Skip and KEEP GOING. Stopping here is
;                        the classic bug: a file deleted before yours
;                        was written makes yours invisible.
;    attr = $0F       -> a VFAT long-name fragment. Its bytes are UCS-2
;                        name characters, not a name field; comparing
;                        against them matches nothing at best and
;                        something wrong at worst.
;    attr & $08       -> the volume label. It lives in the root
;                        directory and its 11 bytes look exactly like a
;                        name.
;    $00 first byte   -> END OF DIRECTORY. Nothing after this has ever
;                        been used. Stop - scanning on reads whatever
;                        the formatter happened to leave there.
; ======================================================================
; ----------------------------------------------------------------------
;  fat_FindEntry - THE ONE directory scan.
;
;  fat_MakeName must have run; this compares against fat_wantName. On a
;  match it leaves the entry's ABSOLUTE sector in fat_findLba and its
;  byte offset within that sector in fat_findOff, and returns 1. It does
;  not interpret the entry at all - not the attribute, not the size, not
;  the first cluster - because FatOpen, FatDelete and FatCreate each
;  want a different subset and each has a different opinion about what
;  makes an entry unusable.
;
;  IT WAS SPLIT OUT OF FatOpen ON PURPOSE, and not for tidiness. Writing
;  needs to find entries too, and the four skip-or-stop rules above are
;  the kind of thing that gets copied with one clause missing. A second
;  copy that stopped at a $E5 entry would make a freshly created file
;  invisible to the very next FatOpen, on a directory that has ever had
;  anything deleted from it - which is every real directory.
; ----------------------------------------------------------------------
Procedure.i fat_FindEntry()
  Define clus.i
  Define sec.i
  Define ent.i
  Define *e
  Define attr.i
  Define lba.i
  Define nxt.i

  fat_findLba  = -1
  fat_findOff  = -1
  clus         = fat_rootClus
  fat_dirSteps = 0

  While 1
    If fat_ClusterValid(clus) = 0
      ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
    EndIf
    lba = fat_ClusterLba(clus)

    sec = 0
    While sec < fat_secPerClus
      If fat_ReadSec(lba + sec) = 0
        ProcedureReturn 0
      EndIf
      ent = 0
      While ent < #FAT_DIRENTS_PER_SEC
        *e = @fat_secBuf[0] + (ent * #FAT_DIRENT_SIZE)
        If PeekA(*e) = #FAT_DIRENT_END
          ProcedureReturn fat_Fail(#FAT_ERR_NOTFOUND)
        EndIf
        If PeekA(*e) <> #FAT_DIRENT_FREE
          attr = fat_U8(*e, #FAT_DIR_ATTR)
          If attr <> #FAT_ATTR_LONG_NAME And (attr & #FAT_ATTR_VOLUME_ID) = 0
            If fat_EntryMatches(*e) = 1
              fat_findLba = lba + sec
              fat_findOff = ent * #FAT_DIRENT_SIZE
              ProcedureReturn 1
            EndIf
          EndIf
        EndIf
        ent = ent + 1
      Wend
      sec = sec + 1
    Wend

    ; Next cluster of the root directory. Bounded - see trap 3.
    nxt = fat_NextCluster(clus)
    If fat_err <> #FAT_ERR_NONE
      ProcedureReturn 0
    EndIf
    If nxt >= #FAT_CLUS_EOC
      ; The directory ended and the name was not in it. This is the
      ; ordinary "no such file" answer for a directory that fills its
      ; last cluster exactly.
      ProcedureReturn fat_Fail(#FAT_ERR_NOTFOUND)
    EndIf
    If nxt = #FAT_CLUS_BAD
      ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS_MARK)
    EndIf
    ; THE TWO O(1) LOOP SHAPES, checked before the counter because they
    ; are the ones that actually occur and because catching them here
    ; costs one compare instead of fat_clusterCount sector reads.
    If nxt = clus Or nxt = fat_rootClus
      ProcedureReturn fat_Fail(#FAT_ERR_DIRLOOP)
    EndIf
    fat_dirSteps = fat_dirSteps + 1
    If fat_dirSteps > fat_clusterCount
      ProcedureReturn fat_Fail(#FAT_ERR_DIRLOOP)
    EndIf
    clus = nxt
  Wend
EndProcedure

Procedure.i FatOpen(*name)
  Define *e
  Define attr.i
  Define first.i
  Define need.i
  Define i.i

  fat_open = 0
  fat_err  = #FAT_ERR_NONE

  If fat_mounted = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NOT_MOUNTED)
  EndIf
  If fat_MakeName(*name) = 0
    ProcedureReturn 0
  EndIf
  If fat_FindEntry() = 0
    ProcedureReturn 0
  EndIf
  ; fat_FindEntry left the sector in fat_secBuf and its tag set, so this
  ; read is a cache hit. It is written out rather than assumed because
  ; the assumption is exactly the kind that survives a refactor and then
  ; reads a directory entry out of a FAT sector.
  If fat_ReadSec(fat_findLba) = 0
    ProcedureReturn 0
  EndIf
  *e = @fat_secBuf[0] + fat_findOff

  attr = fat_U8(*e, #FAT_DIR_ATTR)
  If (attr & #FAT_ATTR_DIRECTORY) <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_IS_DIR)
  EndIf
  fat_fileSize = fat_U32(*e, #FAT_DIR_FILESIZE)
  first = ((fat_U16(*e, #FAT_DIR_FSTCLUSHI) << 16) | fat_U16(*e, #FAT_DIR_FSTCLUSLO))
  ; A size that needs more clusters than the volume has is impossible,
  ; so the entry is corrupt - and refusing it HERE is what stops a
  ; hostile four-billion-byte size from sending the chain walk around a
  ; two-cluster loop sixty five thousand times. See trap 3.
  need = (fat_fileSize + fat_clusterBytes - 1) / fat_clusterBytes
  If need > fat_clusterCount
    ProcedureReturn fat_Fail(#FAT_ERR_FILE_TOO_BIG)
  EndIf
  If fat_fileSize > 0
    If fat_ClusterValid(first) = 0
      ; A nonzero size with no cluster, or a cluster off the volume.
      ; Either way there is nothing to read and the entry is corrupt.
      If first = 0
        ProcedureReturn fat_Fail(#FAT_ERR_FILE_CLUSTER)
      EndIf
      ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
    EndIf
  EndIf
  ; An EMPTY file legitimately has first cluster 0 and no chain at all.
  ; FatRead returns 0 for it, which is EOF, not an error.
  fat_firstClus  = first
  fat_curClus    = first
  fat_pos        = 0
  fat_fileSteps  = 0
  fat_attr       = attr

  ; WHERE THE ENTRY LIVES. This is the line the old FatOverwrite did not
  ; have, and its absence is the entire reason that procedure could not
  ; change a file's length. The eleven name bytes come with it so that
  ; fat_UpdateDirEntry can prove, before every single write, that the
  ; slot still holds the file it was opened on.
  fat_entLba = fat_findLba
  fat_entOff = fat_findOff
  i = 0
  While i < #FAT_NAME_LEN
    fat_entName[i] = PeekA(*e + i)
    i = i + 1
  Wend

  fat_open = 1
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  THE ROOT-DIRECTORY ITERATOR - FatDirRewind / FatDirNext and the
;  accessors for the entry the cursor is sitting on.
;
;  This is the listing walk `fatls` / `ls` rides, and it was the one thing
;  DELIBERATELY LEFT OUT of this file until now ("DIRECTORY LISTING. There
;  is no FatFirst/FatNext"). It is the SAME walk fat_FindEntry does: the
;  root cluster chain, one sector at a time, sixteen 32-byte entries a
;  sector, stopping at the first $00 (never-used marker, nothing after it)
;  and skipping $E5 (deleted), $0F (long-name fragment) and VOLUME_ID (the
;  volume label) entries. The ONLY difference is that fat_FindEntry
;  compares each surviving entry against a wanted name and this hands each
;  one back in turn - so the FAT parsing (fat_ClusterLba, fat_ReadSec,
;  fat_NextCluster and the fat_U8/U16/U32 field reads) is REUSED here, not
;  copied. The cluster-chain advance carries the same bound and the same
;  two O(1) loop refusals fat_FindEntry uses, for the same reason: an
;  in-place directory loop must stop the walk, not hang the board.
;
;  IT WALKS THE ROOT ONLY, the directory FatOpen searches, because the
;  library reads no subdirectory (see DELIBERATELY LEFT OUT). A caller
;  that wants a subdirectory has to be told no; this iterator has no way
;  to descend.
;
;  CONTRACT:
;    FatDirRewind()   1, cursor at the start of the root directory; or 0
;                     with #FAT_ERR_NOT_MOUNTED when nothing is mounted.
;    FatDirNext()     1  a new entry is current - read it with the
;                        accessors below;
;                     0  the directory ended cleanly, no entry is current;
;                    -1  a read or a corrupt chain stopped the walk,
;                        FatLastError() says which. The cursor is left
;                        ENDED after a 0 or a -1, so a caller that keeps
;                        calling gets 0 forever rather than looping.
;    FatDirName(*d)   copy the 11 raw 8.3 name bytes (8 then 3, space
;                     padded, uppercase, no dot) of the current entry to
;                     *d. The stored $05 that means a real leading $E5 is
;                     already corrected, as fat_EntryMatches does on read.
;    FatDirIsDir()    1 if the current entry is a subdirectory.
;    FatDirSize()     its DIR_FileSize in bytes (0 for a directory).
;    FatDirAttr()     its raw DIR_Attr byte, for a caller that wants more.
;
;  IT SHARES fat_secBuf WITH FatOpen/FatMount, so a listing must not be
;  interleaved with an open file. The monitor does one at a time.
; ======================================================================
Procedure.i FatDirRewind()
  If fat_mounted = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NOT_MOUNTED)
  EndIf
  fat_lsClus  = fat_rootClus
  fat_lsSec   = 0
  fat_lsEnt   = 0
  fat_lsSteps = 0
  fat_lsEnd   = 0
  fat_err     = #FAT_ERR_NONE
  ProcedureReturn 1
EndProcedure

Procedure.i FatDirNext()
  Define lba.i
  Define *e
  Define attr.i
  Define b0.i
  Define nxt.i
  Define i.i

  If fat_lsEnd <> 0
    ProcedureReturn 0
  EndIf

  While 1
    If fat_ClusterValid(fat_lsClus) = 0
      fat_lsEnd = 1
      fat_Fail(#FAT_ERR_BADCLUS)
      ProcedureReturn -1
    EndIf
    lba = fat_ClusterLba(fat_lsClus)

    While fat_lsSec < fat_secPerClus
      If fat_ReadSec(lba + fat_lsSec) = 0
        ; fat_ReadSec already set fat_err through fat_Fail.
        fat_lsEnd = 1
        ProcedureReturn -1
      EndIf
      While fat_lsEnt < #FAT_DIRENTS_PER_SEC
        *e = @fat_secBuf[0] + (fat_lsEnt * #FAT_DIRENT_SIZE)
        b0 = PeekA(*e)
        If b0 = #FAT_DIRENT_END
          ; $00 - this slot and every one after it has never been used.
          ; The directory is over; nothing beyond here is real.
          fat_lsEnd = 1
          ProcedureReturn 0
        EndIf
        ; ADVANCE THE CURSOR NOW, before any return below, so the next
        ; call resumes on the entry AFTER this one whether this one is
        ; skipped or handed back.
        fat_lsEnt = fat_lsEnt + 1
        If b0 <> #FAT_DIRENT_FREE
          attr = fat_U8(*e, #FAT_DIR_ATTR)
          If attr <> #FAT_ATTR_LONG_NAME And (attr & #FAT_ATTR_VOLUME_ID) = 0
            ; A real 8.3 entry. Capture its fields out of the buffer now,
            ; so the accessors do not depend on fat_secBuf still holding
            ; this sector on the next call.
            i = 0
            While i < #FAT_NAME_LEN
              fat_lsName[i] = PeekA(*e + i)
              i = i + 1
            Wend
            ; A stored $05 in the first byte is a real leading $E5 - the
            ; read-direction fix fat_EntryMatches makes, made here too.
            If fat_lsName[0] = #FAT_DIRENT_E5
              fat_lsName[0] = #FAT_DIRENT_FREE
            EndIf
            fat_lsAttr  = attr
            fat_lsSize  = fat_U32(*e, #FAT_DIR_FILESIZE)
            fat_lsFirst = ((fat_U16(*e, #FAT_DIR_FSTCLUSHI) << 16) | fat_U16(*e, #FAT_DIR_FSTCLUSLO))
            ProcedureReturn 1
          EndIf
        EndIf
      Wend
      fat_lsEnt = 0
      fat_lsSec = fat_lsSec + 1
    Wend

    ; Off the end of this cluster - hop to the next one in the root chain,
    ; with the bound and the O(1) refusals fat_FindEntry uses.
    nxt = fat_NextCluster(fat_lsClus)
    If fat_err <> #FAT_ERR_NONE
      fat_lsEnd = 1
      ProcedureReturn -1
    EndIf
    If nxt >= #FAT_CLUS_EOC
      ; The directory filled its last cluster exactly and ended. Clean.
      fat_lsEnd = 1
      ProcedureReturn 0
    EndIf
    If nxt = #FAT_CLUS_BAD
      fat_lsEnd = 1
      fat_Fail(#FAT_ERR_BADCLUS_MARK)
      ProcedureReturn -1
    EndIf
    If nxt = fat_lsClus Or nxt = fat_rootClus
      fat_lsEnd = 1
      fat_Fail(#FAT_ERR_DIRLOOP)
      ProcedureReturn -1
    EndIf
    fat_lsSteps = fat_lsSteps + 1
    If fat_lsSteps > fat_clusterCount
      fat_lsEnd = 1
      fat_Fail(#FAT_ERR_DIRLOOP)
      ProcedureReturn -1
    EndIf
    fat_lsClus = nxt
    fat_lsSec  = 0
    fat_lsEnt  = 0
  Wend
EndProcedure

Procedure FatDirName(*d)
  Define i.i
  i = 0
  While i < #FAT_NAME_LEN
    PokeA(*d + i, fat_lsName[i])
    i = i + 1
  Wend
EndProcedure

Procedure.i FatDirIsDir()
  If (fat_lsAttr & #FAT_ATTR_DIRECTORY) <> 0
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i FatDirSize()
  ProcedureReturn fat_lsSize
EndProcedure

Procedure.i FatDirAttr()
  ProcedureReturn fat_lsAttr
EndProcedure

; Captured entry metadata, independent of the shared sector buffer.
Procedure.i FatDirFirstCluster()
  ProcedureReturn fat_lsFirst
EndProcedure

; ======================================================================
;  PUBLIC - FatRead(*dst, max)
;
;  Reads up to max bytes from the current position into *dst and
;  advances. Returns the number of bytes placed, 0 at end of file, or
;  -1 with FatLastError() set.
;
;  IT IS RESUMABLE. FatRead(*p, 512) four times reads the same 2048
;  bytes as FatRead(*p, 2048) once. A loader does the second; a caller
;  streaming into a small buffer does the first. FatTell() says how far
;  it has got and FatRewind() puts it back.
;
;  -1 RATHER THAN 0 FOR AN ERROR, deliberately: 0 is a real and ordinary
;  answer (end of file) and a caller looping "While FatRead(...) > 0"
;  must not treat a chain loop as a clean finish.
;
;  ON -1 THE DESTINATION MAY ALREADY HOLD PART OF THE FILE. A medium
;  that fails on the third sector has already delivered two, and this
;  file does not undo them - it could not, without a copy of the
;  destination. So -1 means "what is in *dst is not the file", and a
;  loader must not jump to a buffer it has seen -1 for. FatTell() says
;  how far it actually got.
;
;  TWO PATHS INTO THE DESTINATION, and the fast one is the reason this
;  can load a multi-megabyte image at a sensible speed:
;
;    DIRECT   - a whole sector, starting on a sector boundary, into a
;               4-byte-aligned destination with at least 512 bytes of
;               room. The reader writes into the caller's memory and
;               nothing is copied twice.
;    BOUNCE   - anything else: a partial first sector, a short tail, a
;               destination that is not aligned. The sector goes into
;               fat_secBuf and the wanted bytes are copied out.
;
;  The alignment test is on *dst PLUS what has already been written, not
;  on *dst, because that is the address the reader will actually be
;  given. Both paths are exercised by the test, on the same file: once
;  into an aligned buffer and once into the same buffer offset by one.
; ======================================================================
Procedure.i FatRead(*dst, max.i)
  Define written.i
  Define remain.i
  Define inClus.i
  Define secInClus.i
  Define inSec.i
  Define chunk.i
  Define lba.i
  Define nxt.i
  Define *here

  If fat_mounted = 0
    fat_err = #FAT_ERR_NOT_MOUNTED
    ProcedureReturn -1
  EndIf
  If fat_open = 0
    fat_err = #FAT_ERR_NO_FILE
    ProcedureReturn -1
  EndIf
  If *dst = 0
    fat_err = #FAT_ERR_NULL_DST
    ProcedureReturn -1
  EndIf
  If max < 0
    fat_err = #FAT_ERR_BAD_MAX
    ProcedureReturn -1
  EndIf

  fat_err = #FAT_ERR_NONE
  written = 0

  While written < max
    remain = fat_fileSize - fat_pos
    If remain <= 0
      Break                      ; end of file - not an error
    EndIf

    If fat_ClusterValid(fat_curClus) = 0
      fat_err = #FAT_ERR_BADCLUS
      ProcedureReturn -1
    EndIf

    inClus    = fat_pos % fat_clusterBytes
    secInClus = inClus / #FAT_SECTOR_SIZE
    inSec     = fat_pos % #FAT_SECTOR_SIZE
    lba       = fat_ClusterLba(fat_curClus) + secInClus

    ; The biggest piece that is inside this sector, inside the file, and
    ; inside what the caller asked for. All three, or one of them gets
    ; overrun.
    chunk = #FAT_SECTOR_SIZE - inSec
    If chunk > remain
      chunk = remain
    EndIf
    If chunk > (max - written)
      chunk = max - written
    EndIf

    *here = *dst + written

    If inSec = 0 And chunk = #FAT_SECTOR_SIZE And (*here & 3) = 0
      ; DIRECT. The reader writes the caller's memory. fat_secBuf's
      ; cache tag is untouched because fat_secBuf was not involved.
      If fat_ReadRaw(lba, *here) = 0
        ProcedureReturn -1
      EndIf
    Else
      ; BOUNCE.
      If fat_ReadSec(lba) = 0
        ProcedureReturn -1
      EndIf
      fat_CopyBytes(*here, @fat_secBuf[0] + inSec, chunk)
    EndIf

    written = written + chunk
    fat_pos = fat_pos + chunk

    ; Has the position walked out of this cluster? Only then does the
    ; chain get walked - and only if there is more file to come, so that
    ; reading a file whose last byte lands exactly on a cluster boundary
    ; does not demand a next cluster that need not exist.
    If (fat_pos % fat_clusterBytes) = 0 And fat_pos < fat_fileSize
      nxt = fat_NextCluster(fat_curClus)
      If fat_err <> #FAT_ERR_NONE
        ProcedureReturn -1
      EndIf
      If nxt = #FAT_CLUS_BAD
        fat_err = #FAT_ERR_BADCLUS_MARK
        ProcedureReturn -1
      EndIf
      If nxt >= #FAT_CLUS_EOC
        ; The chain says the file is over but the directory entry says
        ; there are more bytes. They disagree; say so rather than
        ; returning a short read that looks complete.
        fat_err = #FAT_ERR_SHORT_CHAIN
        ProcedureReturn -1
      EndIf
      If fat_ClusterValid(nxt) = 0
        fat_err = #FAT_ERR_BADCLUS
        ProcedureReturn -1
      EndIf
      ; THE TWO O(1) LOOP SHAPES. A cluster pointing at itself, and a
      ; chain returning to where it started. See trap 3 for what these
      ; catch, what the counter below catches, and what neither does.
      If nxt = fat_curClus Or nxt = fat_firstClus
        fat_err = #FAT_ERR_CHAINLOOP
        ProcedureReturn -1
      EndIf
      ; THE COUNT BOUND. Cumulative since FatOpen, because a per-call
      ; bound is no bound at all for a caller reading in pieces. With
      ; #FAT_ERR_FILE_TOO_BIG refusing an oversized entry at open, a
      ; legitimate read can never reach this - it is here because a
      ; bound that depends on another check having run is not a bound.
      fat_fileSteps = fat_fileSteps + 1
      If fat_fileSteps > fat_clusterCount
        fat_err = #FAT_ERR_CHAINLOOP
        ProcedureReturn -1
      EndIf
      fat_curClus = nxt
    EndIf
  Wend

  ProcedureReturn written
EndProcedure

; ======================================================================
;  PUBLIC - FatRewind / FatClose
; ======================================================================
Procedure.i FatRewind()
  If fat_open = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_FILE)
  EndIf
  fat_pos       = 0
  fat_curClus   = fat_firstClus
  fat_fileSteps = 0
  ProcedureReturn 1
EndProcedure

Procedure FatClose()
  fat_open      = 0
  fat_pos       = 0
  fat_curClus   = 0
  fat_fileSteps = 0
  ; The entry pointer goes with the file. Leaving it set would make
  ; fat_UpdateDirEntry usable after a close, and the name check is a
  ; second line of defence, not the first.
  fat_entLba    = -1
  fat_entOff    = -1
  fat_attr      = 0
EndProcedure

; ======================================================================
; ======================================================================
;
;   W R I T I N G
;
; ======================================================================
; ======================================================================
;  Everything from here to the accessors changes the medium. Read the
;  header sections "WRITING", "THE ORDER OF WRITES", "TIMESTAMPS" and
;  "THE SECOND FAT" before changing any of it - the order in which these
;  procedures touch the FAT, the data and the directory is not stylistic
;  and is the only thing that decides whether an interrupted write costs
;  a file or a filesystem.
; ======================================================================

; ----------------------------------------------------------------------
;  fat_NextOrAlloc - one hop along the OPEN FILE's chain, extending it
;  when grow is 1 and the chain has run out.
;
;  Returns the next cluster, or 0 with fat_err set. Every refusal the
;  read path makes is made here too and by the same code, because a
;  chain that FatRead calls corrupt must not be one FatWrite quietly
;  walks: BAD marks, cluster numbers off the volume, a cluster pointing
;  at itself, and a chain that comes back round to its own start.
; ----------------------------------------------------------------------
Procedure.i fat_NextOrAlloc(cl.i, grow.i)
  Define nxt.i
  nxt = fat_NextCluster(cl)
  If fat_err <> #FAT_ERR_NONE
    ProcedureReturn 0
  EndIf
  If nxt = #FAT_CLUS_BAD
    ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS_MARK)
  EndIf
  If nxt >= #FAT_CLUS_EOC
    If grow = 0
      ProcedureReturn fat_Fail(#FAT_ERR_SHORT_CHAIN)
    EndIf
    ProcedureReturn fat_AllocCluster(cl)
  EndIf
  If fat_ClusterValid(nxt) = 0
    ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
  EndIf
  If nxt = cl Or nxt = fat_firstClus
    ProcedureReturn fat_Fail(#FAT_ERR_CHAINLOOP)
  EndIf
  ProcedureReturn nxt
EndProcedure

; ----------------------------------------------------------------------
;  fat_ChainAt - the cluster holding cluster-INDEX idx of the open file,
;  counting from 0. Allocates the whole way there when grow is 1,
;  including the file's very first cluster when it has none.
;
;  Returns the cluster, or 0 with fat_err set. 0 is never a real answer.
;
;  IT WALKS FROM THE START EVERY TIME, and that is O(chain) per call.
;  A cursor cached across calls was written and taken back out: it has
;  to be invalidated by FatOpen, FatCreate, FatTruncate, FatDelete and
;  by any allocation that lands in the middle of the same chain, and a
;  cursor that is stale by one cluster writes a file's bytes into
;  another file. Walking is slower and cannot be wrong. The one place
;  the cost would show is a caller appending in tiny pieces to a very
;  long file; a loader writes an image in one call and pays for one
;  walk.
;
;  THE STEP BOUND IS THE SAME ONE EVERYTHING ELSE USES. A chain longer
;  than the volume's cluster count has visited a cluster twice.
; ----------------------------------------------------------------------
Procedure.i fat_ChainAt(idx.i, grow.i)
  Define cl.i
  Define nxt.i
  Define steps.i
  Define k.i

  If fat_firstClus = 0
    If grow = 0
      ProcedureReturn fat_Fail(#FAT_ERR_FILE_CLUSTER)
    EndIf
    cl = fat_AllocCluster(0)
    If cl = 0
      ProcedureReturn 0
    EndIf
    fat_firstClus = cl
  EndIf

  cl = fat_firstClus
  If fat_ClusterValid(cl) = 0
    ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
  EndIf

  k     = 0
  steps = 0
  While k < idx
    nxt = fat_NextOrAlloc(cl, grow)
    If nxt = 0
      ProcedureReturn 0
    EndIf
    steps = steps + 1
    If steps > fat_clusterCount
      ProcedureReturn fat_Fail(#FAT_ERR_CHAINLOOP)
    EndIf
    cl = nxt
    k  = k + 1
  Wend

  ProcedureReturn cl
EndProcedure

; ----------------------------------------------------------------------
;  fat_FixCursor - put fat_curClus back in step with fat_pos, using
;  EXACTLY the convention FatRead maintains.
;
;  FatRead advances to the next cluster when the position lands on a
;  cluster boundary AND there is more file after it. So at a boundary
;  that is also the end of the file, the cursor stays in the LAST
;  cluster rather than pointing at one that need not exist. Any writer
;  that leaves a different convention behind makes the next FatRead read
;  one cluster off, silently, and only for files whose length happens to
;  be a multiple of the cluster size.
; ----------------------------------------------------------------------
Procedure.i fat_FixCursor()
  Define idx.i
  Define cl.i

  fat_fileSteps = 0
  If fat_firstClus = 0
    fat_curClus = 0
    ProcedureReturn 1
  EndIf
  idx = fat_pos / fat_clusterBytes
  If fat_pos > 0 And (fat_pos % fat_clusterBytes) = 0 And fat_pos >= fat_fileSize
    idx = idx - 1
  EndIf
  cl = fat_ChainAt(idx, 0)
  If cl = 0
    ProcedureReturn 0
  EndIf
  fat_curClus   = cl
  fat_fileSteps = 0
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  fat_UpdateDirEntry - the ONLY procedure in this file that writes a
;  file's size or first cluster, and the only one that stamps a date.
;
;  THE NAME IS CHECKED FIRST, EVERY TIME. fat_entLba and fat_entOff were
;  recorded when the file was opened, and between then and now the
;  caller may have created or deleted other files in the same directory.
;  Nothing in this library MOVES an entry, so the check should never
;  fail - which is exactly why it is here. A size written into the wrong
;  slot is silent, is permanent, and reads afterwards as though the
;  volume was formatted wrong.
; ----------------------------------------------------------------------
Procedure.i fat_UpdateDirEntry(newSize.i, newFirst.i)
  Define *e
  Define i.i

  If fat_entLba < 0 Or fat_entOff < 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_DIRENT)
  EndIf
  If fat_ReadSec(fat_entLba) = 0
    ProcedureReturn 0
  EndIf
  *e = @fat_secBuf[0] + fat_entOff
  i = 0
  While i < #FAT_NAME_LEN
    If PeekA(*e + i) <> fat_entName[i]
      ProcedureReturn fat_Fail(#FAT_ERR_NO_DIRENT)
    EndIf
    i = i + 1
  Wend

  fat_PutU32(*e, #FAT_DIR_FILESIZE,  newSize)
  fat_PutU16(*e, #FAT_DIR_FSTCLUSHI, (newFirst >> 16) & $FFFF)
  fat_PutU16(*e, #FAT_DIR_FSTCLUSLO, newFirst & $FFFF)
  ; The clock this board does not have. See "TIMESTAMPS" in the header
  ; and #FAT_DATE_SENTINEL.
  fat_PutU16(*e, #FAT_DIR_WRTTIME,    fat_wrTime)
  fat_PutU16(*e, #FAT_DIR_WRTDATE,    fat_wrDate)
  fat_PutU16(*e, #FAT_DIR_LSTACCDATE, fat_wrDate)

  ProcedureReturn fat_WriteSecBuf(fat_entLba)
EndProcedure

; ======================================================================
;  PUBLIC - FatSeek(pos)
;
;  Moves the read/write position. 0 <= pos <= FatSize().
;
;  PAST THE END IS REFUSED, not silently allowed. Seeking beyond a
;  file's length and writing would leave a HOLE, and FAT has no way to
;  express one: the bytes in the gap would be whatever the newly
;  allocated clusters already held, which is somebody's deleted file.
;  A caller that wants zeros there can write zeros there.
;
;  pos = FatSize() is the APPEND position and is the whole reason this
;  exists - without it, adding to a file would mean reading all of it
;  first.
; ======================================================================
Procedure.i FatSeek(pos.i)
  If fat_open = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_FILE)
  EndIf
  If pos < 0 Or pos > fat_fileSize
    ProcedureReturn fat_Fail(#FAT_ERR_BAD_LEN)
  EndIf
  fat_err = #FAT_ERR_NONE
  fat_pos = pos
  ProcedureReturn fat_FixCursor()
EndProcedure

; ======================================================================
;  PUBLIC - FatWrite(*src, len)
;
;  Writes len bytes at the current position, extending the file if it
;  runs past the end. Returns the number of bytes written - which is len
;  or nothing, this is not a short-write API - or -1 with FatLastError()
;  set.
;
;  THE ORDER, and it is the reason this is safe to run against a boot
;  medium:
;
;    1. CLAIM. Clusters are allocated in the FAT as they are needed.
;       Until step 3 the directory still says the old size, so those
;       clusters are chained past the end of the file and NOTHING reads
;       them. A power cut here costs allocated-but-unreferenced clusters
;       - "lost clusters", which every repair tool understands and which
;       leave a filesystem that mounts.
;    2. DATA. The bytes go into those clusters. Still invisible.
;    3. DIRECTORY. The size, and the first cluster if the file had none,
;       go into the entry. THIS is the instant the new data becomes part
;       of the file, and it is one 512-byte sector write - the smallest
;       unit the medium can fail in the middle of.
;    4. FSINFO. A hint, last, because being wrong about it costs a scan
;       and nothing else.
;
;    Reverse 2 and 3 and a power cut leaves a file whose directory entry
;    promises bytes that were never written: a load that succeeds and
;    delivers garbage. That is the failure this ordering exists to
;    prevent, and the gate breaks the order on purpose to prove it is
;    noticed.
;
;  THE DIRECTORY IS UPDATED ON EVERY CALL, not once at the end of a run
;  of them. A caller writing in pieces must be able to lose power
;  between two of them and find a file whose length matches its
;  contents.
;
;  WHAT IS NOT ZEROED, said out loud: when the last sector of a file is
;  partial, the bytes after the end of the file inside that sector are
;  left as they were - and if the cluster was freshly allocated, "as
;  they were" is whatever a deleted file left behind. Every FAT
;  implementation behaves this way and zeroing would double the writes
;  on the tail of every file. It is recorded here rather than discovered
;  later.
; ======================================================================
Procedure.i FatWrite(*src, len.i)
  Define done.i
  Define idx.i
  Define cl.i
  Define at.i
  Define inClus.i
  Define secInClus.i
  Define inSec.i
  Define chunk.i
  Define lba.i
  Define nxt.i
  Define steps.i
  Define need.i
  Define i.i
  Define *here

  If fat_mounted = 0
    fat_err = #FAT_ERR_NOT_MOUNTED
    ProcedureReturn -1
  EndIf
  If fat_open = 0
    fat_err = #FAT_ERR_NO_FILE
    ProcedureReturn -1
  EndIf
  If *src = 0
    fat_err = #FAT_ERR_NULL_DST
    ProcedureReturn -1
  EndIf
  If len < 0
    fat_err = #FAT_ERR_BAD_LEN
    ProcedureReturn -1
  EndIf
  If *fat_writer = 0
    fat_err = #FAT_ERR_NO_WRITER
    ProcedureReturn -1
  EndIf
  If (fat_attr & #FAT_ATTR_READ_ONLY) <> 0
    ; [FATGEN] describes ATTR_READ_ONLY as a flag "writes should refuse
    ; to write to". Honoured, because a loader that overwrites the
    ; file marked read-only is a loader nobody can protect anything
    ; from.
    fat_err = #FAT_ERR_READ_ONLY
    ProcedureReturn -1
  EndIf
  If fat_entLba < 0
    fat_err = #FAT_ERR_NO_DIRENT
    ProcedureReturn -1
  EndIf

  fat_err = #FAT_ERR_NONE
  If len = 0
    ProcedureReturn 0
  EndIf

  ; The same refusal FatOpen makes about a corrupt size, made before the
  ; first cluster is claimed rather than after the volume is full: a
  ; file cannot be longer than the volume can hold.
  need = (fat_pos + len + fat_clusterBytes - 1) / fat_clusterBytes
  If need > fat_clusterCount
    fat_err = #FAT_ERR_FILE_TOO_BIG
    ProcedureReturn -1
  EndIf

  idx = fat_pos / fat_clusterBytes
  cl  = fat_ChainAt(idx, 1)
  If cl = 0
    ProcedureReturn -1
  EndIf

  done  = 0
  steps = 0
  While done < len
    at        = fat_pos + done
    inClus    = at % fat_clusterBytes
    secInClus = inClus / #FAT_SECTOR_SIZE
    inSec     = at % #FAT_SECTOR_SIZE
    lba       = fat_ClusterLba(cl) + secInClus

    chunk = #FAT_SECTOR_SIZE - inSec
    If chunk > (len - done)
      chunk = len - done
    EndIf
    *here = *src + done

    If inSec = 0 And chunk = #FAT_SECTOR_SIZE And (*here & 3) = 0
      ; DIRECT - a whole aligned sector straight out of the caller's
      ; memory, the mirror of FatRead's fast path. The sector cache is
      ; invalidated because fat_secBuf was NOT the source and its tag
      ; would otherwise describe the sector's old contents.
      If fat_secLba = lba
        fat_secLba = -1
      EndIf
      If fat_WriteRaw(lba, *here) = 0
        ProcedureReturn -1
      EndIf
    Else
      ; READ-MODIFY-WRITE. A partial sector at either end, or a source
      ; the reader's alignment rule would refuse. The bytes around what
      ; is being written belong to the file, or to nobody, and either
      ; way they are not ours to change.
      If fat_ReadSec(lba) = 0
        ProcedureReturn -1
      EndIf
      i = 0
      While i < chunk
        PokeA(@fat_secBuf[0] + inSec + i, PeekA(*here + i))
        i = i + 1
      Wend
      If fat_WriteSecBuf(lba) = 0
        ProcedureReturn -1
      EndIf
    EndIf

    done = done + chunk

    If ((fat_pos + done) % fat_clusterBytes) = 0 And done < len
      nxt = fat_NextOrAlloc(cl, 1)
      If nxt = 0
        ProcedureReturn -1
      EndIf
      steps = steps + 1
      If steps > fat_clusterCount
        fat_err = #FAT_ERR_CHAINLOOP
        ProcedureReturn -1
      EndIf
      cl = nxt
    EndIf
  Wend

  fat_pos = fat_pos + len
  If fat_pos > fat_fileSize
    fat_fileSize = fat_pos
  EndIf

  ; STEP 3. Not one line earlier.
  If fat_UpdateDirEntry(fat_fileSize, fat_firstClus) = 0
    ProcedureReturn -1
  EndIf
  ; STEP 4.
  If fat_WriteFsInfo() = 0
    ProcedureReturn -1
  EndIf
  If fat_FixCursor() = 0
    ProcedureReturn -1
  EndIf

  ProcedureReturn len
EndProcedure

; ======================================================================
;  PUBLIC - FatTruncate(newLen)
;
;  Shortens the open file to newLen bytes and returns the tail's
;  clusters to the free pool. Returns 1, or 0 with FatLastError() set.
;
;  IT WILL NOT MAKE A FILE BIGGER. #FAT_ERR_GROW_REFUSED. Growing a file
;  by truncation means inventing bytes, and the only bytes available to
;  invent with are whatever the newly allocated clusters already hold -
;  a deleted file's contents, handed back as though they were zeros.
;  A caller that wants the file longer has FatWrite and knows what
;  should be in it.
;
;  THE DIRECTORY IS WRITTEN BEFORE THE FAT, WHICH IS THE OPPOSITE OF
;  FatWrite, AND BOTH ARE RIGHT. The rule underneath both of them is the
;  one that matters:
;
;      A DIRECTORY ENTRY MUST NEVER POINT AT A CLUSTER THE FAT CALLS
;      FREE.
;
;  Growing: the clusters exist before the entry mentions them, so the
;  directory goes last. Shrinking: the entry must stop mentioning them
;  before they are released, so the directory goes first. Interrupt
;  either one and the worst outcome is clusters that are marked in use
;  and referenced by nothing - lost clusters, repairable, and the volume
;  still mounts.
;
;  Get it backwards on the shrink and an interrupted truncate leaves a
;  live file whose chain runs through free space. The next file created
;  is handed one of those clusters, and now two files own the same
;  sector; no repair tool can undo that, it can only pick a loser.
; ======================================================================
Procedure.i FatTruncate(newLen.i)
  Define keep.i
  Define last.i
  Define tail.i
  Define oldFirst.i

  If fat_mounted = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NOT_MOUNTED)
  EndIf
  If fat_open = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_FILE)
  EndIf
  If *fat_writer = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_WRITER)
  EndIf
  If (fat_attr & #FAT_ATTR_READ_ONLY) <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_READ_ONLY)
  EndIf
  If fat_entLba < 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_DIRENT)
  EndIf
  If newLen < 0
    ProcedureReturn fat_Fail(#FAT_ERR_BAD_LEN)
  EndIf
  If newLen > fat_fileSize
    ProcedureReturn fat_Fail(#FAT_ERR_GROW_REFUSED)
  EndIf

  fat_err = #FAT_ERR_NONE
  If newLen = fat_fileSize
    ; Nothing changed, so nothing is written. A sector write with no
    ; cause is still a sector write to the boot medium.
    ProcedureReturn 1
  EndIf
  If fat_EnsureFreeInfo() = 0
    ProcedureReturn 0
  EndIf

  keep     = (newLen + fat_clusterBytes - 1) / fat_clusterBytes
  oldFirst = fat_firstClus

  If keep = 0
    ; The whole chain goes. [FATGEN]: a zero-length file's first cluster
    ; field is 0 - that is the representation, not a shortcut.
    If fat_UpdateDirEntry(0, 0) = 0
      ProcedureReturn 0
    EndIf
    fat_firstClus = 0
    fat_fileSize  = 0
    tail          = oldFirst
  Else
    last = fat_ChainAt(keep - 1, 0)
    If last = 0
      ProcedureReturn 0
    EndIf
    tail = fat_NextCluster(last)
    If fat_err <> #FAT_ERR_NONE
      ProcedureReturn 0
    EndIf
    If fat_UpdateDirEntry(newLen, fat_firstClus) = 0
      ProcedureReturn 0
    EndIf
    fat_fileSize = newLen
    If tail < #FAT_CLUS_EOC
      ; The kept part needs a new end. Done BEFORE the tail is freed, so
      ; that at no point is there a chain running from a live file into
      ; a cluster marked free.
      If fat_SetEntry(last, #FAT_CLUS_EOC_W) = 0
        ProcedureReturn 0
      EndIf
    EndIf
  EndIf

  If fat_FreeChain(tail) = 0
    ProcedureReturn 0
  EndIf
  If fat_WriteFsInfo() = 0
    ProcedureReturn 0
  EndIf

  If fat_pos > fat_fileSize
    fat_pos = fat_fileSize
  EndIf
  ProcedureReturn fat_FixCursor()
EndProcedure

; ======================================================================
;  PUBLIC - FatOverwrite(*src, len)
;
;  Replaces the entire contents of the open file with len bytes and
;  makes the file exactly that long. Returns 1, or 0 with
;  FatLastError() set.
;
;  THIS USED TO REFUSE ANY LENGTH BUT THE FILE'S OWN, and the caution
;  that refusal came from has not been thrown away - it has been paid
;  for. The old comment said a bug in allocation corrupts a filesystem
;  while a bug here corrupts one file, and that is still true. What
;  changed is that allocation now exists, is ordered so that every
;  interruption leaves a mountable volume, is fenced so that no write
;  can leave the FAT and data regions, and is exercised by a gate that
;  is watched going red for each of those properties in turn.
;
;  #FAT_ERR_SIZE_MISMATCH is therefore no longer raised by anything. The
;  callers that padded their buffers to FatSize() before calling this
;  still work unchanged - an exact length is just one length among many
;  now - and they no longer have to.
;
;  IT IS THREE OPERATIONS AND NOT ONE, deliberately, so that there is
;  one implementation of each rule rather than two:
;
;      FatRewind      - back to byte 0
;      FatWrite       - the new bytes, growing the file if they need it
;      FatTruncate    - drop whatever the old file had past them
;
;  The write comes before the truncate. Doing it the other way would
;  free the tail's clusters and then, for a longer replacement, ask for
;  them straight back - churning the FAT for no reason and widening the
;  window in which the file is neither the old thing nor the new one.
; ======================================================================
Procedure.i FatOverwrite(*src, len.i)
  Define n.i

  If fat_mounted = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NOT_MOUNTED)
  EndIf
  If fat_open = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_FILE)
  EndIf
  If *src = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NULL_DST)
  EndIf
  If len < 0
    ProcedureReturn fat_Fail(#FAT_ERR_BAD_LEN)
  EndIf
  If *fat_writer = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_WRITER)
  EndIf

  If FatRewind() = 0
    ProcedureReturn 0
  EndIf
  fat_err = #FAT_ERR_NONE

  If len > 0
    n = FatWrite(*src, len)
    If n < 0
      ProcedureReturn 0
    EndIf
  EndIf
  If fat_fileSize > len
    If FatTruncate(len) = 0
      ProcedureReturn 0
    EndIf
  EndIf
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  fat_ZeroDirSlot - make the FIRST entry of a directory sector read as
;  "never used". [FATGEN]: a $00 in the first byte of a directory entry
;  means this entry and every entry after it is free, and it is what
;  every directory scan - including this file's - stops at.
; ----------------------------------------------------------------------
Procedure.i fat_ZeroDirSlot(lba.i)
  Define i.i
  If fat_ReadSec(lba) = 0
    ProcedureReturn 0
  EndIf
  i = 0
  While i < #FAT_DIRENT_SIZE
    fat_secBuf[i] = 0
    i = i + 1
  Wend
  ProcedureReturn fat_WriteSecBuf(lba)
EndProcedure

; ======================================================================
;  fat_FindFreeSlot - a 32-byte slot in the ROOT directory that a new
;  entry may go into, extending the directory by a cluster if there is
;  no slot left.
;
;  Leaves the answer in fat_findLba / fat_findOff, and fat_findZeroNext
;  set when the caller must also zero the FOLLOWING slot inside the same
;  sector write.
;
;  THE ORDER OF PREFERENCE IS DELETED SLOT FIRST, AND IT IS NOT AN
;  OPTIMISATION. A $E5 slot is one that used to hold a file, so whatever
;  terminated the directory before still terminates it and there is no
;  end-marker question to get wrong. Taking the $00 slot instead grows
;  the directory by one entry every time and eventually needs a new
;  cluster.
;
;  THE END MARKER IS THE TRAP. [FATGEN] says the entry after the last
;  one in use must have $00 in its first byte, and a scan - this file's
;  included - stops there. Write a new entry over the $00 that was
;  terminating the directory and the scan runs on into whatever the
;  formatter left in the next 32 bytes, reading it as a directory entry.
;  So a new terminator has to be made, and there are three cases,
;  handled separately because they need different numbers of writes:
;
;    * the next slot is in the SAME sector - the caller zeroes it in the
;      same buffer, so the entry and its terminator reach the medium in
;      ONE write and there is no instant in between
;    * the next slot is the first entry of the next SECTOR of this
;      cluster - that sector's first entry is zeroed FIRST, then the
;      caller writes the entry. Marker before entry, so an interruption
;      leaves a directory that is merely unchanged
;    * the next slot would be in the next CLUSTER, and there is not one
;      - a cluster is allocated, ZEROED, and linked; the terminator is
;      then its first entry, already $00
;
;  A directory cluster is zeroed and a data cluster is not. A data
;  cluster is about to be written over; a directory cluster full of a
;  deleted file's bytes has no $00 entry in it anywhere, so the scan
;  would read 16 entries of garbage and then walk off the end of the
;  chain.
; ======================================================================
Procedure.i fat_FindFreeSlot()
  Define clus.i
  Define lastClus.i
  Define sec.i
  Define ent.i
  Define lba.i
  Define b.i
  Define nxt.i
  Define steps.i
  Define e5Lba.i
  Define e5Off.i
  Define zLba.i
  Define zOff.i
  Define zSec.i
  Define zEnt.i
  Define zClus.i
  Define done.i
  Define newc.i

  e5Lba = -1
  e5Off = -1
  zLba  = -1
  zOff  = -1
  zSec  = 0
  zEnt  = 0
  zClus = 0
  done  = 0
  steps = 0
  clus  = fat_rootClus
  lastClus = clus
  fat_findLba      = -1
  fat_findOff      = -1
  fat_findZeroNext = 0

  While 1
    If fat_ClusterValid(clus) = 0
      ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
    EndIf
    lba      = fat_ClusterLba(clus)
    lastClus = clus

    sec = 0
    While sec < fat_secPerClus And done = 0
      If fat_ReadSec(lba + sec) = 0
        ProcedureReturn 0
      EndIf
      ent = 0
      While ent < #FAT_DIRENTS_PER_SEC
        b = PeekA(@fat_secBuf[0] + (ent * #FAT_DIRENT_SIZE))
        If b = #FAT_DIRENT_END
          zLba  = lba + sec
          zOff  = ent * #FAT_DIRENT_SIZE
          zSec  = sec
          zEnt  = ent
          zClus = clus
          done  = 1
          Break
        EndIf
        If b = #FAT_DIRENT_FREE And e5Lba < 0
          e5Lba = lba + sec
          e5Off = ent * #FAT_DIRENT_SIZE
        EndIf
        ent = ent + 1
      Wend
      sec = sec + 1
    Wend
    If done = 1
      Break
    EndIf

    nxt = fat_NextCluster(clus)
    If fat_err <> #FAT_ERR_NONE
      ProcedureReturn 0
    EndIf
    If nxt = #FAT_CLUS_BAD
      ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS_MARK)
    EndIf
    If nxt >= #FAT_CLUS_EOC
      Break                    ; the directory has no $00 entry at all
    EndIf
    If fat_ClusterValid(nxt) = 0
      ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
    EndIf
    If nxt = clus Or nxt = fat_rootClus
      ProcedureReturn fat_Fail(#FAT_ERR_DIRLOOP)
    EndIf
    steps = steps + 1
    If steps > fat_clusterCount
      ProcedureReturn fat_Fail(#FAT_ERR_DIRLOOP)
    EndIf
    clus = nxt
  Wend

  If e5Lba >= 0
    fat_findLba      = e5Lba
    fat_findOff      = e5Off
    fat_findZeroNext = 0
    ProcedureReturn 1
  EndIf

  If done = 1
    If zEnt < (#FAT_DIRENTS_PER_SEC - 1)
      fat_findLba      = zLba
      fat_findOff      = zOff
      fat_findZeroNext = 1
      ProcedureReturn 1
    EndIf
    If zSec < (fat_secPerClus - 1)
      If fat_ZeroDirSlot(zLba + 1) = 0
        ProcedureReturn 0
      EndIf
      fat_findLba      = zLba
      fat_findOff      = zOff
      fat_findZeroNext = 0
      ProcedureReturn 1
    EndIf
    nxt = fat_NextCluster(zClus)
    If fat_err <> #FAT_ERR_NONE
      ProcedureReturn 0
    EndIf
    If nxt = #FAT_CLUS_BAD
      ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS_MARK)
    EndIf
    If nxt >= #FAT_CLUS_EOC
      newc = fat_AllocCluster(zClus)
      If newc = 0
        If fat_err = #FAT_ERR_NO_SPACE
          ProcedureReturn fat_Fail(#FAT_ERR_DIR_FULL)
        EndIf
        ProcedureReturn 0
      EndIf
      If fat_ZeroCluster(newc) = 0
        ProcedureReturn 0
      EndIf
    Else
      If fat_ClusterValid(nxt) = 0
        ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
      EndIf
      If fat_ZeroDirSlot(fat_ClusterLba(nxt)) = 0
        ProcedureReturn 0
      EndIf
    EndIf
    fat_findLba      = zLba
    fat_findOff      = zOff
    fat_findZeroNext = 0
    ProcedureReturn 1
  EndIf

  ; No recycled slot and no end marker anywhere: every one of the
  ; directory's entries is in use and the chain ended.
  newc = fat_AllocCluster(lastClus)
  If newc = 0
    If fat_err = #FAT_ERR_NO_SPACE
      ProcedureReturn fat_Fail(#FAT_ERR_DIR_FULL)
    EndIf
    ProcedureReturn 0
  EndIf
  If fat_ZeroCluster(newc) = 0
    ProcedureReturn 0
  EndIf
  fat_findLba      = fat_ClusterLba(newc)
  fat_findOff      = 0
  fat_findZeroNext = 1
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PUBLIC - FatCreate(name)
;
;  Makes a new, EMPTY file in the root directory and leaves it OPEN, so
;  the usual next line is FatWrite. Returns 1, or 0 with FatLastError()
;  set.
;
;  A NAME THAT ALREADY EXISTS IS REFUSED with #FAT_ERR_EXISTS rather
;  than opened, emptied or duplicated. "Create" that quietly means
;  "open, and by the way your old file is gone" is the sort of
;  convenience that removes a boot image. A caller that wants the old
;  one replaced says so: FatOpen then FatOverwrite, or FatDelete then
;  FatCreate.
;
;  THE NEW FILE HAS NO FIRST CLUSTER, AND THAT IS THE CORRECT
;  REPRESENTATION, not a shortcut. [FATGEN] gives a zero-length file a
;  first cluster of 0 and no chain at all - it is the same thing FatOpen
;  already handles for EMPTY.TXT on any real volume. Allocating a
;  cluster here would produce an entry whose size says zero bytes and
;  whose chain says one cluster, which is precisely the disagreement
;  between the directory and the FAT that #FAT_ERR_SHORT_CHAIN exists to
;  report. The first FatWrite allocates, and FatFirstCluster() is real
;  from that moment.
;
;  THE ATTRIBUTE IS ARCHIVE ($20) and nothing else. [FATGEN] says
;  ATTR_ARCHIVE is set when a file is created or modified; hidden,
;  system and read-only are policy this library has no opinion about,
;  and volume-id and directory would be lies.
; ======================================================================
Procedure.i FatCreate(*name)
  Define *e
  Define i.i
  Define r.i

  fat_err = #FAT_ERR_NONE
  If fat_mounted = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NOT_MOUNTED)
  EndIf
  If *fat_writer = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_WRITER)
  EndIf
  If fat_MakeName(*name) = 0
    ProcedureReturn 0
  EndIf

  r = fat_FindEntry()
  If r = 1
    ProcedureReturn fat_Fail(#FAT_ERR_EXISTS)
  EndIf
  If fat_err <> #FAT_ERR_NOTFOUND
    ; A real failure - a looping directory, a medium error - and not
    ; "the name is available".
    ProcedureReturn 0
  EndIf
  fat_err = #FAT_ERR_NONE

  If fat_FindFreeSlot() = 0
    ProcedureReturn 0
  EndIf
  ; Re-read rather than trust: fat_FindFreeSlot may have allocated and
  ; zeroed a whole cluster since the scan, and fat_secBuf is what it
  ; zeroed it with.
  If fat_ReadSec(fat_findLba) = 0
    ProcedureReturn 0
  EndIf
  *e = @fat_secBuf[0] + fat_findOff

  i = 0
  While i < #FAT_DIRENT_SIZE
    PokeA(*e + i, 0)
    i = i + 1
  Wend
  i = 0
  While i < #FAT_NAME_LEN
    PokeA(*e + i, fat_wantName[i])
    i = i + 1
  Wend
  fat_PutU8(*e,  #FAT_DIR_ATTR,        #FAT_ATTR_ARCHIVE)
  fat_PutU8(*e,  #FAT_DIR_NTRES,       0)
  fat_PutU8(*e,  #FAT_DIR_CRTTIMETNTH, 0)
  fat_PutU16(*e, #FAT_DIR_CRTTIME,     fat_wrTime)
  fat_PutU16(*e, #FAT_DIR_CRTDATE,     fat_wrDate)
  fat_PutU16(*e, #FAT_DIR_LSTACCDATE,  fat_wrDate)
  fat_PutU16(*e, #FAT_DIR_WRTTIME,     fat_wrTime)
  fat_PutU16(*e, #FAT_DIR_WRTDATE,     fat_wrDate)
  fat_PutU16(*e, #FAT_DIR_FSTCLUSHI,   0)
  fat_PutU16(*e, #FAT_DIR_FSTCLUSLO,   0)
  fat_PutU32(*e, #FAT_DIR_FILESIZE,    0)

  If fat_findZeroNext = 1
    ; The new end of directory, in the same buffer and therefore in the
    ; same write as the entry it terminates.
    PokeA(@fat_secBuf[0] + fat_findOff + #FAT_DIRENT_SIZE, #FAT_DIRENT_END)
  EndIf

  If fat_WriteSecBuf(fat_findLba) = 0
    ProcedureReturn 0
  EndIf

  fat_entLba = fat_findLba
  fat_entOff = fat_findOff
  i = 0
  While i < #FAT_NAME_LEN
    fat_entName[i] = fat_wantName[i]
    i = i + 1
  Wend
  fat_fileSize  = 0
  fat_firstClus = 0
  fat_curClus   = 0
  fat_pos       = 0
  fat_fileSteps = 0
  fat_attr      = #FAT_ATTR_ARCHIVE
  fat_open      = 1

  ProcedureReturn fat_WriteFsInfo()
EndProcedure

; ======================================================================
;  PUBLIC - FatDelete(name)
;
;  Removes a file from the root directory and returns its clusters.
;  Returns 1, or 0 with FatLastError() set.
;
;  THE ENTRY IS MARKED $E5 FIRST AND THE CHAIN IS FREED SECOND, for the
;  same reason FatTruncate updates the directory first: a directory
;  entry must never point at a cluster the FAT calls free. Interrupted
;  after the $E5 and before the last cluster is released, the file is
;  gone and some of its clusters are lost - which fsck reports and
;  repairs. Interrupted the other way round, a live directory entry
;  points into free space and the next file created lands on top of it.
;
;  DELETING THE FILE THAT IS OPEN CLOSES IT, rather than leaving a
;  handle on an entry that has just become $E5. The alternative was to
;  refuse, and that is worse: replacing a boot image by delete-then-
;  create is a completely reasonable thing to do, and a refusal there
;  would only teach callers to close first without ever saying why.
;
;  A DIRECTORY IS REFUSED with #FAT_ERR_IS_DIR. Deleting one means
;  recursing into it, and this file does not read subdirectories at all
;  - so it would be freeing a chain whose contents it never looked at,
;  which is how a whole subtree becomes lost clusters.
;
;  A READ-ONLY ENTRY IS REFUSED with #FAT_ERR_READ_ONLY.
; ======================================================================
Procedure.i FatDelete(*name)
  Define *e
  Define attr.i
  Define first.i
  Define lba.i
  Define off.i

  fat_err = #FAT_ERR_NONE
  If fat_mounted = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NOT_MOUNTED)
  EndIf
  If *fat_writer = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NO_WRITER)
  EndIf
  If fat_MakeName(*name) = 0
    ProcedureReturn 0
  EndIf
  If fat_FindEntry() = 0
    ProcedureReturn 0
  EndIf

  lba = fat_findLba
  off = fat_findOff
  If fat_ReadSec(lba) = 0
    ProcedureReturn 0
  EndIf
  *e   = @fat_secBuf[0] + off
  attr = fat_U8(*e, #FAT_DIR_ATTR)
  If (attr & #FAT_ATTR_DIRECTORY) <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_IS_DIR)
  EndIf
  If (attr & #FAT_ATTR_READ_ONLY) <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_READ_ONLY)
  EndIf
  first = ((fat_U16(*e, #FAT_DIR_FSTCLUSHI) << 16) | fat_U16(*e, #FAT_DIR_FSTCLUSLO))

  If fat_EnsureFreeInfo() = 0
    ProcedureReturn 0
  EndIf

  If fat_open = 1 And fat_entLba = lba And fat_entOff = off
    FatClose()
  EndIf

  ; 1. THE ENTRY.
  If fat_ReadSec(lba) = 0
    ProcedureReturn 0
  EndIf
  PokeA(@fat_secBuf[0] + off, #FAT_DIRENT_FREE)
  If fat_WriteSecBuf(lba) = 0
    ProcedureReturn 0
  EndIf

  ; 2. THE CHAIN. A first cluster of 0 is an empty file and there is
  ; nothing to free; anything outside 2..count+1 is a corrupt entry and
  ; is refused rather than walked.
  If first <> 0
    If fat_ClusterValid(first) = 0
      ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
    EndIf
    If fat_FreeChain(first) = 0
      ProcedureReturn 0
    EndIf
  EndIf

  ProcedureReturn fat_WriteFsInfo()
EndProcedure

; ======================================================================
;  PUBLIC - the free-space bookkeeping, exposed
; ======================================================================

; Force the full FAT pass and push the result to FSInfo. This is the
; "I do not believe the hint" call, and it is the only way to correct an
; FSInfo whose free count is in range and simply wrong - nothing cheaper
; can tell that case from a correct one.
Procedure.i FatRescanFree()
  If fat_mounted = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NOT_MOUNTED)
  EndIf
  fat_err = #FAT_ERR_NONE
  If fat_ScanFree() = 0
    ProcedureReturn 0
  EndIf
  If *fat_writer = 0
    ; Scanning is a read. Refusing to scan just because nothing can be
    ; written back would make FatFreeClusters() unavailable to a
    ; read-only caller for no reason.
    ProcedureReturn 1
  EndIf
  ProcedureReturn fat_WriteFsInfo()
EndProcedure

Procedure.i FatSyncFsInfo()
  If fat_mounted = 0
    ProcedureReturn fat_Fail(#FAT_ERR_NOT_MOUNTED)
  EndIf
  fat_err = #FAT_ERR_NONE
  ProcedureReturn fat_WriteFsInfo()
EndProcedure

; ======================================================================
;  PUBLIC - FatSetTimestamp(date, time)
;
;  THE SEAM FOR A CLOCK THIS BOARD DOES NOT HAVE. See "TIMESTAMPS" in
;  the header for the decision and why the default is 1980-01-01.
;
;  Both arguments are already in [FATGEN]'s packed form, because
;  converting from a broken-down date is the caller's problem and
;  because a library that took a year and a month would have to have an
;  opinion about calendars:
;
;      date = ((year - 1980) << 9) | (month << 5) | day
;      time = (hour << 11) | (minute << 5) | (second / 2)
;
;  Out-of-range values are refused rather than masked. A year of 2200
;  masked into seven bits becomes 2092, which is a plausible-looking
;  wrong date - the exact thing the sentinel exists to avoid.
; ======================================================================
Procedure.i FatSetTimestamp(date.i, time.i)
  Define y.i
  Define mo.i
  Define d.i
  Define h.i
  Define mi.i
  Define s.i

  y  = (date >> 9) & $7F
  mo = (date >> 5) & $0F
  d  = date & $1F
  h  = (time >> 11) & $1F
  mi = (time >> 5) & $3F
  s  = time & $1F

  If date <> ((y << 9) | (mo << 5) | d)
    ProcedureReturn fat_Fail(#FAT_ERR_BAD_LEN)
  EndIf
  If time <> ((h << 11) | (mi << 5) | s)
    ProcedureReturn fat_Fail(#FAT_ERR_BAD_LEN)
  EndIf
  If mo < 1 Or mo > 12 Or d < 1 Or d > 31
    ProcedureReturn fat_Fail(#FAT_ERR_BAD_LEN)
  EndIf
  If h > 23 Or mi > 59 Or s > 29
    ProcedureReturn fat_Fail(#FAT_ERR_BAD_LEN)
  EndIf

  fat_wrDate = date
  fat_wrTime = time
  ProcedureReturn 1
EndProcedure

; ======================================================================
;  PUBLIC - accessors. Nothing here reads the medium.
; ======================================================================

Procedure.i FatMounted()
  ProcedureReturn fat_mounted
EndProcedure

; 32 when mounted. 12 or 16 when a FAT12/FAT16 volume was found and
; refused - so a caller can say WHAT it found. 0 if the mount never got
; as far as computing a type.
Procedure.i FatType()
  ProcedureReturn fat_type
EndProcedure

Procedure.i FatPartitionType()
  ProcedureReturn fat_partType
EndProcedure

Procedure.i FatPartitionLba()
  ProcedureReturn fat_partLba
EndProcedure

Procedure.i FatPartitionSectors()
  ProcedureReturn fat_partSecs
EndProcedure

Procedure.i FatBytesPerCluster()
  ProcedureReturn fat_clusterBytes
EndProcedure

; CountofClusters, and therefore the bound every chain walk is held to.
Procedure.i FatClusterCount()
  ProcedureReturn fat_clusterCount
EndProcedure

Procedure.i FatFatLba()
  ProcedureReturn fat_fatLba
EndProcedure

Procedure.i FatDataLba()
  ProcedureReturn fat_dataLba
EndProcedure

Procedure.i FatRootCluster()
  ProcedureReturn fat_rootClus
EndProcedure

; Read one sector of a caller-selected cluster without disturbing the shared
; directory-sector cache or any open-file/directory cursor.  This deliberately
; exposes no arbitrary-volume LBA read: users must name a valid data cluster
; and a sector inside that cluster.  The Pi 3 updater uses the seam for its
; bounded ownership walk while fat_NextCluster keeps using the independent FAT
; cache.  Destination follows the block-reader contract and is 4-byte aligned.
Procedure.i FatReadClusterSector(cluster.i, sector.i, destination.i)
  If destination = 0 Or (destination & 3) <> 0
    ProcedureReturn fat_Fail(#FAT_ERR_BUF_ALIGN)
  EndIf
  If fat_ClusterValid(cluster) = 0 Or sector < 0 Or sector >= fat_secPerClus
    ProcedureReturn fat_Fail(#FAT_ERR_BADCLUS)
  EndIf
  ProcedureReturn fat_ReadRaw(fat_ClusterLba(cluster) + sector, destination)
EndProcedure

Procedure.i FatTotalSectors()
  ProcedureReturn fat_totSecs
EndProcedure

Procedure.i FatIsOpen()
  ProcedureReturn fat_open
EndProcedure

; The size from the directory entry, in bytes. -1 with #FAT_ERR_NO_FILE
; if nothing is open, because 0 is a legal size.
Procedure.i FatSize()
  If fat_open = 0
    fat_err = #FAT_ERR_NO_FILE
    ProcedureReturn -1
  EndIf
  ProcedureReturn fat_fileSize
EndProcedure

Procedure.i FatFirstCluster()
  ProcedureReturn fat_firstClus
EndProcedure

Procedure.i FatTell()
  ProcedureReturn fat_pos
EndProcedure

Procedure.i FatLastError()
  ProcedureReturn fat_err
EndProcedure

; The LBA the last block-reader call asked for. After
; #FAT_ERR_READ_FAIL this is the sector that would not read, and after
; #FAT_ERR_WRITE_FAIL or #FAT_ERR_LBA_RANGE it is the sector a write was
; aimed at.
Procedure.i FatLastLba()
  ProcedureReturn fat_lastLba
EndProcedure

; ----------------------------------------------------------------------
;  The write side, read back. Nothing here touches the medium.
; ----------------------------------------------------------------------

; The DIR_Attr byte of the open entry, or 0 when nothing is open. Bit
; #FAT_ATTR_READ_ONLY is the one that makes FatWrite refuse.
Procedure.i FatAttributes()
  ProcedureReturn fat_attr
EndProcedure

; Where the open file's directory entry lives - absolute sector, and
; byte offset within it. -1 when nothing is open. Exposed so a test can
; check the entry from outside instead of believing this file about it.
Procedure.i FatDirEntryLba()
  ProcedureReturn fat_entLba
EndProcedure

Procedure.i FatDirEntryOffset()
  ProcedureReturn fat_entOff
EndProcedure

; The absolute LBA of the FSInfo sector, or -1 when the volume has none
; or its signatures did not check out.
Procedure.i FatFsInfoLba()
  ProcedureReturn fat_fsinfoLba
EndProcedure

; 1 when there is an FSInfo sector this file is willing to write to.
Procedure.i FatFsInfoValid()
  ProcedureReturn fat_fsinfoOk
EndProcedure

; Free clusters, or -1 for "not known yet". Known becomes true on the
; first allocation or free after a mount, or immediately on a call to
; FatRescanFree().
Procedure.i FatFreeClusters()
  ProcedureReturn fat_freeCount
EndProcedure

; Where the next allocation will start looking. 0 means no hint.
Procedure.i FatNextFreeHint()
  ProcedureReturn fat_nextFree
EndProcedure

; 1 once a full FAT pass has produced the free count in this mount.
Procedure.i FatFreeScanned()
  ProcedureReturn fat_freeScanned
EndProcedure

; 1 when every FAT copy is maintained - BPB_ExtFlags bit 7 clear. 0 when
; the BPB says only one copy is live. See "THE SECOND FAT" in the header.
Procedure.i FatMirrorsFats()
  ProcedureReturn fat_mirrorFats
EndProcedure

; Absolute LBA of FAT copy 0, and one past the last sector of the last
; copy. These two and the data region are the whole of what fat_WriteRaw
; will let a write reach.
Procedure.i FatFatBase()
  ProcedureReturn fat_fatBase
EndProcedure

Procedure.i FatFatEnd()
  ProcedureReturn fat_fatEnd
EndProcedure

Procedure.i FatDataEnd()
  ProcedureReturn fat_dataEnd
EndProcedure

Procedure.i FatNumFats()
  ProcedureReturn fat_numFats
EndProcedure

; The packed date and time every entry this file writes will carry. See
; FatSetTimestamp and "TIMESTAMPS" in the header.
Procedure.i FatTimestampDate()
  ProcedureReturn fat_wrDate
EndProcedure

Procedure.i FatTimestampTime()
  ProcedureReturn fat_wrTime
EndProcedure

; ======================================================================
;  FatErrorText - the address of a NUL-terminated English sentence for
;  FatLastError().
;
;  Print it with whatever PutS the MAIN file's UART library provides.
;  The text names WHAT WAS FOUND, not what to do about it - a library
;  that guessed at fixes in a string would be wrong out loud, and the
;  caller has FatLastLba() and the reader's own error accessor for the
;  rest.
; ======================================================================
Procedure.i FatErrorText()
  Select fat_err
    Case #FAT_ERR_NONE
      ProcedureReturn "fat: ok"
    Case #FAT_ERR_NO_READER
      ProcedureReturn "fat: no block reader - call FatSetBlockReader(@SdReadBlock) first"
    Case #FAT_ERR_NO_WRITER
      ProcedureReturn "fat: no block writer - FatSetBlockWriter was never called"
    Case #FAT_ERR_WRITE_FAIL
      ProcedureReturn "fat: the medium refused a write. FatLastLba() names the block"
    Case #FAT_ERR_SIZE_MISMATCH
      ProcedureReturn "fat: retired code 42 - overwrite used to need the file's exact size and no longer does"
    Case #FAT_ERR_NO_SPACE
      ProcedureReturn "fat: the volume has no free cluster left"
    Case #FAT_ERR_DIR_FULL
      ProcedureReturn "fat: the root directory is full and could not be extended"
    Case #FAT_ERR_EXISTS
      ProcedureReturn "fat: a file of that name is already there - create refuses rather than replacing it"
    Case #FAT_ERR_READ_ONLY
      ProcedureReturn "fat: that entry is marked read-only"
    Case #FAT_ERR_FSINFO
      ProcedureReturn "fat: the FSInfo sector's signatures do not check out - free space will be counted from the FAT and that sector left alone"
    Case #FAT_ERR_BAD_LEN
      ProcedureReturn "fat: negative length, a seek past the end of the file, or a timestamp outside what the format can hold"
    Case #FAT_ERR_LBA_RANGE
      ProcedureReturn "fat: a write was aimed outside the FAT and data regions - refused. FatLastLba names the sector"
    Case #FAT_ERR_RESERVED_CLUS
      ProcedureReturn "fat: something tried to write the FAT entry of cluster 0, cluster 1, or a cluster past the end of the volume"
    Case #FAT_ERR_NO_DIRENT
      ProcedureReturn "fat: the open file's directory entry is not where it was - refused rather than writing into another entry"
    Case #FAT_ERR_GROW_REFUSED
      ProcedureReturn "fat: truncate will not make a file bigger - it would have to invent the new bytes"
    Case #FAT_ERR_READ_FAIL
      ProcedureReturn "fat: the block reader failed - see FatLastLba for which sector"
    Case #FAT_ERR_NO_MBR
      ProcedureReturn "fat: sector 0 has no $55 $AA signature - not an MBR"
    Case #FAT_ERR_PARTNUM
      ProcedureReturn "fat: partition number must be 1 to 4"
    Case #FAT_ERR_PART_STATUS
      ProcedureReturn "fat: partition status byte is neither $00 nor $80 - this is not a partition table"
    Case #FAT_ERR_PART_EMPTY
      ProcedureReturn "fat: that partition slot is empty"
    Case #FAT_ERR_PART_GPT
      ProcedureReturn "fat: protective MBR, type $EE - this disk is GPT and GPT is not supported"
    Case #FAT_ERR_PART_TYPE
      ProcedureReturn "fat: partition type is not FAT32 ($0B or $0C) - FAT12 and FAT16 are not supported"
    Case #FAT_ERR_PART_GEOM
      ProcedureReturn "fat: partition starts at sector 0 or is zero sectors long"
    Case #FAT_ERR_NO_BOOTSEC
      ProcedureReturn "fat: the partition's first sector has no $55 $AA signature"
    Case #FAT_ERR_SECSIZE
      ProcedureReturn "fat: bytes per sector is not 512 - the block reader only moves 512-byte blocks"
    Case #FAT_ERR_SPC
      ProcedureReturn "fat: sectors per cluster is 0, above 128, or not a power of two"
    Case #FAT_ERR_RESERVED
      ProcedureReturn "fat: reserved sector count is 0 - the boot sector is itself reserved, so 0 is impossible"
    Case #FAT_ERR_NUMFATS
      ProcedureReturn "fat: the volume claims zero FATs"
    Case #FAT_ERR_FATSZ
      ProcedureReturn "fat: both FAT size fields are zero"
    Case #FAT_ERR_TOTSEC
      ProcedureReturn "fat: both total sector counts are zero"
    Case #FAT_ERR_GEOMETRY
      ProcedureReturn "fat: the volume's regions do not fit inside it, or it does not fit inside its partition"
    Case #FAT_ERR_FAT12
      ProcedureReturn "fat: this is a FAT12 volume - not implemented, refused rather than half-read"
    Case #FAT_ERR_FAT16
      ProcedureReturn "fat: this is a FAT16 volume - not implemented, refused rather than half-read"
    Case #FAT_ERR_ROOTENT
      ProcedureReturn "fat: root entry count is nonzero on a volume that computes as FAT32 - the BPB contradicts itself"
    Case #FAT_ERR_FATSZ16
      ProcedureReturn "fat: the 16-bit FAT size is nonzero on a FAT32 volume - the BPB contradicts itself"
    Case #FAT_ERR_FSVER
      ProcedureReturn "fat: unknown FAT32 filesystem version - refused rather than guessed at"
    Case #FAT_ERR_ROOTCLUS
      ProcedureReturn "fat: the root cluster number is outside the volume"
    Case #FAT_ERR_ACTIVEFAT
      ProcedureReturn "fat: the BPB names an active FAT copy that does not exist"
    Case #FAT_ERR_BUF_ALIGN
      ProcedureReturn "fat: this library's sector buffers are not 4-byte aligned - the block reader requires it"
    Case #FAT_ERR_NOT_MOUNTED
      ProcedureReturn "fat: not mounted - FatMount did not succeed"
    Case #FAT_ERR_NAME
      ProcedureReturn "fat: that name is not an 8.3 short name - long filenames and subdirectories are not supported"
    Case #FAT_ERR_NOTFOUND
      ProcedureReturn "fat: no such file in the root directory"
    Case #FAT_ERR_IS_DIR
      ProcedureReturn "fat: that name is a directory, not a file"
    Case #FAT_ERR_DIRLOOP
      ProcedureReturn "fat: the root directory chain loops - refused rather than walked forever"
    Case #FAT_ERR_BADCLUS
      ProcedureReturn "fat: a cluster number is outside the volume"
    Case #FAT_ERR_BADCLUS_MARK
      ProcedureReturn "fat: the chain reached a cluster marked defective"
    Case #FAT_ERR_CHAINLOOP
      ProcedureReturn "fat: the file's cluster chain loops - refused rather than walked forever"
    Case #FAT_ERR_SHORT_CHAIN
      ProcedureReturn "fat: the chain ended before the directory's file size - the two disagree"
    Case #FAT_ERR_FILE_CLUSTER
      ProcedureReturn "fat: the entry has a nonzero size and no first cluster"
    Case #FAT_ERR_NO_FILE
      ProcedureReturn "fat: no file is open"
    Case #FAT_ERR_NULL_DST
      ProcedureReturn "fat: null destination"
    Case #FAT_ERR_BAD_MAX
      ProcedureReturn "fat: negative byte count"
    Case #FAT_ERR_FILE_TOO_BIG
      ProcedureReturn "fat: the entry's size needs more clusters than the volume has - the entry is corrupt"
  EndSelect
  ProcedureReturn "fat: unknown error code"
EndProcedure
