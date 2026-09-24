; Explicit diagnostic operations for wiring into recovery after the read path
; is compiled and reviewed. This file does not alter the recovery grammar.
; The write routine enables the driver's writer only for its single known
; unique-file creation, then disarms it on every return path.

#ROCK_STORAGE_PROOF_BYTES = 22
#ROCK_STORAGE_STAGE_BYTES = $00400000
#ROCK_STORAGE_XFER_CHUNK = 16384
#ROCK_STORAGE_TRUST_COPY_BYTES = $00200000
#ROCK_STORAGE_TRUST_BYTES = $00400000
#ROCK_STORAGE_TRUST_LBA = $00006000
#ROCK_STORAGE_TRUST_COPY_SECTORS = $00001000
#ROCK_STORAGE_TRUST_VERIFY_SECTORS = 256
#ROCK_STORAGE_TRUST_PRIMARY_LBA = $00006000
#ROCK_STORAGE_TRUST_BACKUP_LBA = $00007000
#ROCK_STORAGE_TRUST_HEADER_BYTES = 2048
#ROCK_STORAGE_TRUST_HEAD_BYTES = 800
#ROCK_STORAGE_TRUST_COMPONENT_BYTES = 48
#ROCK_STORAGE_TRUST_ENTRY_BYTES = 16
#ROCK_STORAGE_TRUST_SEGMENTS = 1
#ROCK_STORAGE_TRUST_ANVIL_BASE = $00040000
#ROCK_STORAGE_TRUST_ANVIL_LIMIT = $00240000

Global rock_storage_proof_attempted.i
Global rock_storage_proof_error.i
Global Dim rock_storage_proof_readback.a[#ROCK_STORAGE_PROOF_BYTES]
Global Dim rock_storage_list_name.a[256]
; One compiler-owned bounded staging area for host file traffic and trust
; updates. Recovery reports this address via `map`; the receiver has no
; caller-selected destination, so the serial peer cannot target monitor RAM.
Global Dim rock_storage_stage.a[#ROCK_STORAGE_STAGE_BYTES]
Global Dim rock_storage_verify_sector.a[512]
Global Dim rock_storage_trust_verify.a[#ROCK_STORAGE_TRUST_VERIFY_SECTORS * 512]
Global Dim rock_storage_token.a[256]
Global Dim rock_storage_path.a[256]
Global rock_storage_xfer_error.i
Global rock_storage_xfer_crc.i
Global rock_storage_xfer_bytes.i
Global rock_storage_trust_parts.i
Global Dim rock_storage_hex.a[8]
Global rock_recovery_skip_lf.i

Procedure.i rock_storage_nextToken(*line, lineLength.i, *position, *dst, capacity.i)
  Protected pos.i = PeekI(*position)
  Protected count.i
  While pos < lineLength And (PeekA(*line + pos) = 32 Or PeekA(*line + pos) = 9)
    pos = pos + 1
  Wend
  count = 0
  While pos < lineLength
    If PeekA(*line + pos) = 32 Or PeekA(*line + pos) = 9 : Break : EndIf
    If count >= capacity - 1 : ProcedureReturn -1 : EndIf
    PokeA(*dst + count, PeekA(*line + pos))
    count = count + 1
    pos = pos + 1
  Wend
  PokeA(*dst + count, 0)
  PokeI(*position, pos)
  ProcedureReturn count
EndProcedure

Procedure.i rock_storage_parseHexToken(*line, lineLength.i, *position, *outValue)
  Protected count.i
  Protected digit.i
  Protected accum.i
  Protected c.i
  Protected pos.i = PeekI(*position)
  While pos < lineLength And (PeekA(*line + pos) = 32 Or PeekA(*line + pos) = 9)
    pos = pos + 1
  Wend
  count = 0 : accum = 0
  While pos < lineLength
    c = PeekA(*line + pos) & 255
    If c = 32 Or c = 9 : Break : EndIf
    If c >= 48 And c <= 57
      digit = c - 48
    ElseIf c >= 65 And c <= 70
      digit = c - 55
    ElseIf c >= 97 And c <= 102
      digit = c - 87
    Else
      ProcedureReturn 0
    EndIf
    If count >= 8 : ProcedureReturn 0 : EndIf
    accum = ((accum << 4) | digit) & $FFFFFFFF
    count = count + 1
    pos = pos + 1
  Wend
  If count = 0 : ProcedureReturn 0 : EndIf
  PokeI(*outValue, accum)
  PokeI(*position, pos)
  ProcedureReturn 1
EndProcedure

Procedure.i rock_storage_tokenIs(*token, text.i, length.i)
  Protected index.i
  For index = 0 To length - 1
    If PeekA(*token + index) <> PeekA(text + index) : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn Bool(PeekA(*token + length) = 0)
EndProcedure

Procedure RockStorageHex8(value.i)
  Protected index.i
  Protected digit.i
  For index = 0 To 7
    digit = (value >> (28 - index * 4)) & 15
    If digit < 10
      RockUartByte(48 + digit)
    Else
      RockUartByte(55 + digit)
    EndIf
  Next
EndProcedure

; The mount/filesystem sentence is useful, but the raw DesignWare snapshots
; locate the actual failing operation without asking the user to repower.
Procedure RockStorageDiagnostics()
  RockUartText("SD ERROR=") : RockStorageHex8(rock_sd_error)
  RockUartText(" CMD=") : RockStorageHex8(rock_sd_lastCommand)
  RockUartText(" ARG=") : RockStorageHex8(rock_sd_lastArgument)
  RockUartText(" INTSTS=") : RockStorageHex8(rock_sd_lastIntStatus)
  RockUartText(" STATUS=") : RockStorageHex8(rock_sd_lastControllerStatus)
  RockUartText(" RESP=") : RockStorageHex8(rock_sd_lastResponse0)
  RockUartByte(47) : RockStorageHex8(rock_sd_lastResponse1)
  RockUartByte(47) : RockStorageHex8(rock_sd_lastResponse2)
  RockUartByte(47) : RockStorageHex8(rock_sd_lastResponse3)
  RockUartText(" HZ=") : RockStorageHex8(rock_sd_cardHz)
  RockUartText(" FS=") : RockStorageHex8(FsErrorKind())
  RockUartByte(47) : RockStorageHex8(FsLastError())
  RockUartText(" EXLBA=") : RockStorageHex8(ExFatLastLba())
  RockUartLine("")
EndProcedure

Procedure RockStorageProbeSector(lba.i)
  If RockSdReadBlocks(lba, 1, @rock_storage_verify_sector[0]) = 0
    RockUartText("SDMETA READ FAIL LBA=") : RockStorageHex8(lba) : RockUartLine("")
    RockStorageDiagnostics()
    ProcedureReturn
  EndIf
  RockUartText("SDMETA LBA=") : RockStorageHex8(lba)
  RockUartText(" CRC=") : RockStorageHex8(Crc32(@rock_storage_verify_sector[0], 512))
  RockUartText(" HEAD=")
  RockStorageHex8(PeekL(@rock_storage_verify_sector[0]) & $FFFFFFFF)
  RockUartLine("")
EndProcedure

; Read-only fingerprints for the exact metadata layers used by the mount.
; These LBAs cover MBR, GPT, exFAT boot/checksum, FAT, bitmap, up-case and root.
Procedure RockStorageMetadataProbe()
  If RockSdInit() = 0
    RockUartLine("SDMETA INIT FAILED")
    RockStorageDiagnostics()
    ProcedureReturn
  EndIf
  RockStorageProbeSector(0)
  RockStorageProbeSector(1)
  RockStorageProbeSector(2)
  RockStorageProbeSector(32768)
  RockStorageProbeSector(32779)
  RockStorageProbeSector(34816)
  RockStorageProbeSector(43008)
  RockStorageProbeSector(43264)
  RockStorageProbeSector(43520)
  RockUartLine("SDMETA DONE")
EndProcedure

; After a timed-out body, consume any tail the host had already queued and
; require an idle interval before returning to the text parser.
Procedure rock_storage_resync()
  Protected value.i
  Protected now.i
  Protected quiet.i
  Protected attempt.i
  quiet = RockTimerTicks()
  For attempt = 0 To 4000000
    value = RockUartReceive()
    If value >= 0 Or value = -2
      quiet = RockTimerTicks()
    EndIf
    now = RockTimerTicks()
    If now < quiet Or now - quiet >= rock_timer_frequency / 10 : Break : EndIf
  Next
EndProcedure

Procedure.i RockStorageCrc32Pet(address.i, length.i)
  Protected crc.i = $FFFFFFFF
  Protected offset.i
  Protected take.i
  While offset < length
    take = length - offset
    If take > #ROCK_STORAGE_XFER_CHUNK : take = #ROCK_STORAGE_XFER_CHUNK : EndIf
    crc = Crc32Part(crc, address + offset, take)
    offset = offset + take
    RockWatchdogPet()
  Wend
  ProcedureReturn crc ! $FFFFFFFF
EndProcedure

; Receive a fixed-length binary body into the one owned staging buffer. The
; peer gets a '+' after each 16 KiB window and must wait before continuing.
; RockUartReceiveBurst drains the hardware FIFO into that window without a
; function call and timer read for every byte.
Procedure.i RockStorageReceive(length.i, expectedCrc.i)
  Protected got.i
  Protected value.i
  Protected start.i
  Protected now.i
  Protected inChunk.i
  Protected attempt.i
  Protected burst.i
  Protected remaining.i

  rock_storage_xfer_error = 0
  rock_storage_xfer_bytes = 0
  If length < 0 Or length > #ROCK_STORAGE_STAGE_BYTES
    rock_storage_xfer_error = 1
    ProcedureReturn 0
  EndIf
  ; Recovery accepts CR, LF and CRLF. The RX protocol must not accidentally
  ; treat the LF half of a CRLF command as byte zero of the binary body.
  If rock_recovery_skip_lf <> 0
    start = RockTimerTicks()
    For attempt = 0 To 100000
      value = RockUartReceive()
      If value = 10 : rock_recovery_skip_lf = 0 : Break : EndIf
      If value >= 0 Or value = -2
        rock_recovery_skip_lf = 0
        rock_storage_xfer_error = 5
        RockUartLine("XFER ERROR HEADER FRAMING")
        ProcedureReturn 0
      EndIf
      now = RockTimerTicks()
      If now < start Or now - start >= rock_timer_frequency / 100 : Break : EndIf
    Next
    rock_recovery_skip_lf = 0
  EndIf
  RockUartText("READY ")
  RockStorageHex8(length)
  RockUartText(" ")
  RockStorageHex8(expectedCrc)
  RockUartText(" ")
  RockStorageHex8(#ROCK_STORAGE_XFER_CHUNK)
  RockUartLine("")
  RockUartDrain()
  start = RockTimerTicks()
  got = 0
  inChunk = 0
  While got < length
    remaining = length - got
    If remaining > #ROCK_STORAGE_XFER_CHUNK - inChunk
      remaining = #ROCK_STORAGE_XFER_CHUNK - inChunk
    EndIf
    burst = RockUartReceiveBurst(@rock_storage_stage[0] + got, remaining)
    If burst = -2
      rock_storage_xfer_error = 2
      Break
    ElseIf burst > 0
      got = got + burst
      inChunk = inChunk + burst
      start = RockTimerTicks()
      If inChunk = #ROCK_STORAGE_XFER_CHUNK Or got = length
        If RockUartByte(43) = 0
          rock_storage_xfer_error = 3
          Break
        EndIf
        ; Only acknowledged forward progress may keep the live deadman fed.
        ; A stalled or corrupt upload must still time out and recover.
        RockWatchdogPet()
        inChunk = 0
      EndIf
    Else
      now = RockTimerTicks()
      If now < start Or now - start >= rock_timer_frequency * 2
        rock_storage_xfer_error = 4
        Break
      EndIf
    EndIf
  Wend
  rock_storage_xfer_bytes = got
  If got <> length
    rock_storage_resync()
    RockUartLine("")
    RockUartLine("XFER ERROR INCOMPLETE; RESYNC COMPLETE")
    ProcedureReturn 0
  EndIf
  RockUartLine("")
  ; The full 4 MiB trust checksum must pet the live deadman after each slice.
  rock_storage_xfer_crc = RockStorageCrc32Pet(@rock_storage_stage[0], length)
  If rock_storage_xfer_crc <> expectedCrc
    RockUartLine("XFER ERROR CHECKSUM; NO WRITE")
    ProcedureReturn 0
  EndIf
  RockUartLine("XFER DONE CHECKSUM PASS")
  ProcedureReturn 1
EndProcedure

Procedure.i RockStoragePutFile(*path, length.i, expectedCrc.i)
  Define partition.i
  Define got.i
  Define emmc.i
  If *path = 0 Or length > #ROCK_STORAGE_STAGE_BYTES : ProcedureReturn 0 : EndIf
  If HwStorageUp() = 0
    RockUartLine("STORAGE MOUNT FAILED")
    RockUartLine(RockStorageErrorText())
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  If RockWatchdogArm() = 0
    RockUartLine("FILE WRITE REFUSED: DEADMAN NOT ARMED")
    ProcedureReturn 0
  EndIf
  If RockStorageReceive(length, expectedCrc) = 0 : ProcedureReturn 0 : EndIf

  ; The full transfer checksum passes before either medium's writer is armed.
  ; Recheck eMMC's live partition selector so boot0/boot1 remain inaccessible.
  emmc = RockStorageIsEmmc()
  If emmc<>0
    If RockEmmcArmWrites()=0
      RockUartText("EMMC WRITE REFUSED: ") : RockUartLine(RockEmmcErrorText())
      ProcedureReturn 0
    EndIf
    gHwFileWriter = @RockEmmcWriteBlocks
  Else
    gHwFileWriter = @RockSdWriteBlocks
  EndIf
  gHwFileWritable = 1
  If HwFileWriteAll(*path, @rock_storage_stage[0], length) = 0
    gHwFileWriter = 0 : gHwFileWritable = 0 : FsSetRangeWriter(0)
    RockEmmcDisarmWrites()
    RockUartLine("FILE WRITE FAILED")
    RockUartLine(HwFileErrorText())
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  gHwFileWriter = 0 : gHwFileWritable = 0 : FsSetRangeWriter(0)
  RockEmmcDisarmWrites()
  partition = rock_storage_partition
  If FsUnmount() = 0
    RockUartLine("FILE WRITE FLUSHED; REMOUNT FOR READBACK FAILED")
    RockUartLine(FsErrorText())
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  rock_storage_up = 0 : gHwFileMounted = 0
  If FsSelectPartition(partition) = 0
    RockUartLine("FILE WRITE FLUSHED; REMOUNT FOR READBACK FAILED")
    RockUartLine(FsErrorText())
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  rock_storage_up = 1 : rock_storage_partition = partition : gHwFileMounted = 1
  If HwFileOpen(*path) = 0
    RockUartLine("FILE WRITE FLUSHED; READBACK OPEN FAILED")
    RockUartLine(HwFileErrorText())
    ProcedureReturn 0
  EndIf
  If HwFileSize() <> length
    HwFileClose()
    RockUartLine("FILE WRITE FLUSHED; READBACK SIZE MISMATCH")
    ProcedureReturn 0
  EndIf
  got = HwFileReadAt(0, @rock_storage_stage[0], length)
  HwFileClose()
  If got <> length Or RockStorageCrc32Pet(@rock_storage_stage[0], length) <> expectedCrc
    RockUartLine("FILE WRITE FLUSHED; REMOUNTED READBACK CHECKSUM FAILED")
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  RockUartLine("FILE WRITE, FLUSH AND REMOUNTED READBACK PASS")
  ProcedureReturn 1
EndProcedure

Procedure.i RockStorageWaitSendAck()
  Protected start.i
  Protected now.i
  Protected value.i
  start = RockTimerTicks()
  Repeat
    value = RockUartReceive()
    If value = 43 : ProcedureReturn 1 : EndIf
    If value = -2 Or value >= 0
      rock_storage_xfer_error = 6
      ProcedureReturn 0
    EndIf
    now = RockTimerTicks()
    If now < start Or now - start >= rock_timer_frequency * 5
      rock_storage_xfer_error = 7
      ProcedureReturn 0
    EndIf
  ForEver
EndProcedure

Procedure.i RockStorageGetFile(*path)
  Protected length.i
  Protected got.i
  Protected index.i
  Protected *mirror
  If *path = 0 Or HwStorageUp() = 0 : ProcedureReturn 0 : EndIf
  If HwFileOpen(*path) = 0
    RockUartLine("FILE OPEN FAILED")
    RockUartLine(HwFileErrorText())
    ProcedureReturn 0
  EndIf
  length = HwFileSize()
  If length < 0 Or length > #ROCK_STORAGE_STAGE_BYTES
    HwFileClose()
    RockUartLine("FILE EXCEEDS 4 MIB TRANSFER LIMIT")
    ProcedureReturn 0
  EndIf
  got = HwFileReadAt(0, @rock_storage_stage[0], length)
  HwFileClose()
  If got <> length
    RockUartLine("FILE READ FAILED")
    RockUartLine(HwFileErrorText())
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  rock_storage_xfer_crc = RockStorageCrc32Pet(@rock_storage_stage[0], length)
  RockUartText("DATA ")
  RockStorageHex8(length)
  RockUartText(" ")
  RockStorageHex8(rock_storage_xfer_crc)
  RockUartText(" ")
  RockStorageHex8(#ROCK_STORAGE_XFER_CHUNK)
  RockUartLine("")
  If length > 0
    If RockStorageWaitSendAck() = 0
      RockUartLine("FILE SEND ACK FAILED")
      ProcedureReturn 0
    EndIf
    ; The DATA body is an opaque wire payload, not console text. Temporarily
    ; detach the screen ring while preserving serial transmission byte-for-byte.
    *mirror = RockUartSetMirrorHook(0)
    For index = 0 To length - 1
      If RockUartByte(PeekA(@rock_storage_stage[0] + index) & 255) = 0
        RockUartSetMirrorHook(*mirror)
        RockUartLine("")
        RockUartLine("FILE SEND FAILED")
        ProcedureReturn 0
      EndIf
      If ((index + 1) % #ROCK_STORAGE_XFER_CHUNK) = 0 Or index = length - 1
        If RockStorageWaitSendAck() = 0
          RockUartSetMirrorHook(*mirror)
          RockUartLine("FILE SEND ACK FAILED")
          ProcedureReturn 0
        EndIf
      EndIf
    Next
    RockUartSetMirrorHook(*mirror)
  EndIf
  RockUartLine("")
  RockUartLine("DATA DONE")
  ProcedureReturn 1
EndProcedure

Procedure.i RockStorageTrustImageValid()
  Protected copyOffset.i
  Protected count.i
  Protected headerCount.i
  Protected signOffset.i
  Protected tableOffset.i
  Protected cursor.i
  Protected component.i
  Protected meta.i
  Protected entry.i
  Protected componentAddress.i
  Protected sectors.i
  Protected storedSector.i
  Protected storedSectors.i
  Protected byteLength.i
  Protected data.i
  Protected index.i
  Protected cursorSector.i

  If rock_storage_xfer_bytes <> #ROCK_STORAGE_TRUST_BYTES : ProcedureReturn 0 : EndIf
  copyOffset = #ROCK_STORAGE_TRUST_COPY_BYTES
  For index = 0 To copyOffset - 1
    If PeekA(@rock_storage_stage[0] + index) <> PeekA(@rock_storage_stage[0] + copyOffset + index)
      ProcedureReturn 0
    EndIf
    If (index & $3FFF) = 0 : RockWatchdogPet() : EndIf
  Next
  For component = 0 To 1
    data = @rock_storage_stage[0] + component * copyOffset
    If PeekA(data) <> 66 Or PeekA(data+1) <> 76 Or PeekA(data+2) <> 51 Or PeekA(data+3) <> 88
      ProcedureReturn 0
    EndIf
    If (PeekL(data+4) & $FFFFFFFF) <> $00000100 Or (PeekL(data+8) & $FFFFFFFF) <> $23
      ProcedureReturn 0
    EndIf
    headerCount = PeekL(data+12) & $FFFFFFFF
    count = (headerCount >> 16) & $FFFF
    signOffset = (headerCount & $FFFF) << 2
    If count <> #ROCK_STORAGE_TRUST_SEGMENTS
      ProcedureReturn 0
    EndIf
    If signOffset <> #ROCK_STORAGE_TRUST_HEAD_BYTES + count * #ROCK_STORAGE_TRUST_COMPONENT_BYTES
      ProcedureReturn 0
    EndIf
    tableOffset = signOffset + 256
    If tableOffset + count * #ROCK_STORAGE_TRUST_ENTRY_BYTES > #ROCK_STORAGE_TRUST_HEADER_BYTES
      ProcedureReturn 0
    EndIf

    cursorSector = #ROCK_STORAGE_TRUST_HEADER_BYTES / 512
    For index = 0 To count - 1
      meta = data + #ROCK_STORAGE_TRUST_HEAD_BYTES + index * #ROCK_STORAGE_TRUST_COMPONENT_BYTES
      entry = data + tableOffset + index * #ROCK_STORAGE_TRUST_ENTRY_BYTES
      If (PeekL(entry) & $FFFFFFFF) <> $31334C42 : ProcedureReturn 0 : EndIf
      storedSector = PeekL(entry+4) & $FFFFFFFF
      storedSectors = PeekL(entry+8) & $FFFFFFFF
      componentAddress = PeekL(meta+32) & $FFFFFFFF
      sectors = PeekL(meta+36) & $FFFFFFFF
      If storedSector <> cursorSector Or (storedSector & 3) <> 0 Or storedSectors <= 0 Or sectors <> storedSectors Or (sectors & 3) <> 0
        ProcedureReturn 0
      EndIf
      If (PeekL(meta+40) & $FFFFFFFF) <> 0 Or (PeekL(meta+44) & $FFFFFFFF) <> 0 Or (PeekL(entry+12) & $FFFFFFFF) <> 0
        ProcedureReturn 0
      EndIf
      If sectors > (#ROCK_STORAGE_TRUST_COPY_BYTES / 512) : ProcedureReturn 0 : EndIf
      byteLength = sectors * 512
      If componentAddress <> #ROCK_STORAGE_TRUST_ANVIL_BASE
        ProcedureReturn 0
      EndIf
      If byteLength > #ROCK_STORAGE_TRUST_ANVIL_LIMIT - #ROCK_STORAGE_TRUST_ANVIL_BASE
        ProcedureReturn 0
      EndIf
      cursorSector = cursorSector + sectors
    Next
    If cursorSector > (#ROCK_STORAGE_TRUST_COPY_BYTES / 512) : ProcedureReturn 0 : EndIf
  Next
  rock_storage_trust_parts = count
  ProcedureReturn 1
EndProcedure

Procedure.i RockStorageWriteTrustCopy(lba.i, sourceOffset.i)
  Protected sector.i
  Protected count.i
  Protected index.i
  Protected source.i
  If lba + #ROCK_STORAGE_TRUST_COPY_SECTORS > rock_storage_blocks : ProcedureReturn 0 : EndIf
  sector = 0
  While sector < #ROCK_STORAGE_TRUST_COPY_SECTORS
    count = #ROCK_STORAGE_TRUST_COPY_SECTORS - sector
    If count > #ROCK_STORAGE_TRUST_VERIFY_SECTORS : count = #ROCK_STORAGE_TRUST_VERIFY_SECTORS : EndIf
    source = @rock_storage_stage[0] + sourceOffset + sector * 512
    RockWatchdogPet()
    If RockSdWriteBlocks(lba + sector, count, source) = 0 : ProcedureReturn 0 : EndIf
    RockWatchdogPet()
    If RockSdReadBlocks(lba + sector, count, @rock_storage_trust_verify[0]) = 0 : ProcedureReturn 0 : EndIf
    For index = 0 To count * 512 - 1
      If PeekA(source + index) <> PeekA(@rock_storage_trust_verify[0] + index) : ProcedureReturn 0 : EndIf
      If (index & $FFF) = 0 : RockWatchdogPet() : EndIf
    Next
    RockWatchdogPet()
    RockUartText(".")
    sector = sector + count
  Wend
  ProcedureReturn RockSdFlush()
EndProcedure

Procedure.i RockStorageTrustUpdate(expectedCrc.i)
  Define partition.i
  Define bothVerified.i
  Define partitionStart.i
  Define mounted.i
  bothVerified = 0
  If RockStorageIsEmmc()<>0
    RockUartLine("TRUST UPDATE REFUSED: SELECT SD")
    ProcedureReturn 0
  EndIf
  If HwStorageUp() = 0
    ; A filesystem parser failure must not strand the monitor on an old
    ; image. Reuse exFAT's CRC-checked GPT selector to prove the first Basic
    ; Data boundary, then permit only the fixed raw trust range below it.
    FsSetRangeReader(@RockSdReadBlocks)
    FsSetRangeWriter(0)
    If RockSdInit() = 0
      RockUartLine("TRUST UPDATE REFUSED; SD NOT READY")
      RockStorageDiagnostics()
      ProcedureReturn 0
    EndIf
    rock_storage_blocks = RockSdBlockCount()
    exfat_partBlocks = 0
    If exfat_FindPartition(1) = 0
      RockUartLine("TRUST UPDATE REFUSED; GPT BOUNDARY NOT VERIFIED")
      RockStorageDiagnostics()
      ProcedureReturn 0
    EndIf
    partitionStart = exfat_partLba
    partition = 0
    mounted = 0
  Else
    mounted = 1
    partition = rock_storage_partition
    If FsType() = #FS_EXFAT
      partitionStart = exfat_partLba
    ElseIf FsType() = #FS_FAT
      partitionStart = FatPartitionLba()
    Else
      RockUartLine("TRUST UPDATE REFUSED; NO ACTIVE PARTITION BOUNDARY")
      ProcedureReturn 0
    EndIf
  EndIf
  If rock_storage_blocks < #ROCK_STORAGE_TRUST_BACKUP_LBA + #ROCK_STORAGE_TRUST_COPY_SECTORS
    RockUartLine("TRUST UPDATE REFUSED; SD NOT READY OR TOO SMALL")
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  If partitionStart < #ROCK_STORAGE_TRUST_BACKUP_LBA + #ROCK_STORAGE_TRUST_COPY_SECTORS
    RockUartLine("TRUST UPDATE REFUSED; TRUST RANGE OVERLAPS FILESYSTEM")
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  If RockStorageReceive(#ROCK_STORAGE_TRUST_BYTES, expectedCrc) = 0
    RockUartLine("TRUST IMAGE NOT WRITTEN")
    ProcedureReturn 0
  EndIf
  If RockStorageTrustImageValid() = 0
    RockUartLine("TRUST FORMAT OR LOAD RANGES REFUSED; NO SD WRITE")
    ProcedureReturn 0
  EndIf
  If mounted <> 0
    If FsUnmount() = 0
      RockUartLine("TRUST UPDATE REFUSED; FILESYSTEM WOULD NOT UNMOUNT")
      ProcedureReturn 0
    EndIf
  EndIf
  rock_storage_up = 0
  gHwFileMounted = 0
  RockUartLine("")
  RockUartLine("TRUST BACKUP COPY WRITE AND READBACK")
  If RockStorageWriteTrustCopy(#ROCK_STORAGE_TRUST_BACKUP_LBA, #ROCK_STORAGE_TRUST_COPY_BYTES) = 0
    RockUartLine("")
    RockUartLine("BACKUP COPY FAILED; PRIMARY LEFT UNTOUCHED")
    RockStorageDiagnostics()
  Else
    RockUartLine("")
    RockUartLine("TRUST PRIMARY COPY WRITE AND READBACK")
    If RockStorageWriteTrustCopy(#ROCK_STORAGE_TRUST_PRIMARY_LBA, 0) = 0
      RockUartLine("")
      RockUartLine("PRIMARY COPY FAILED; BACKUP COPY WAS VERIFIED")
      RockStorageDiagnostics()
    Else
      RockUartLine("")
      RockUartLine("BOTH TRUST COPIES READBACK VERIFIED; MANUAL REBOOT REQUIRED")
      bothVerified = 1
    EndIf
  EndIf
  If mounted <> 0 And FsSelectPartition(partition) <> 0
    rock_storage_partition = partition
    rock_storage_up = 1
    gHwFileMounted = 1
    gHwFileWritable = 0
    gHwFileWriter = 0
    FsSetRangeWriter(0)
  ElseIf mounted <> 0
    RockUartLine("FILESYSTEM REMOUNT FAILED AFTER RAW UPDATE")
    RockUartLine(FsErrorText())
    RockStorageDiagnostics()
  EndIf
  ProcedureReturn bothVerified
EndProcedure

Procedure.i RockStorageProofList()
  Define dirResult.i
  Define count.i
  Define nameBytes.i

  If HwStorageUp() = 0
    RockUartLine("STORAGE MOUNT FAILED")
    RockUartLine(RockStorageErrorText())
    RockStorageDiagnostics()
    ProcedureReturn -1
  EndIf
  If HwDirOpen(0) = 0
    RockUartLine("STORAGE LIST FAILED")
    RockUartLine(HwFileErrorText())
    ProcedureReturn -1
  EndIf

  RockUartLine("STORAGE ROOT:")
  count = 0
  Repeat
    dirResult = HwDirNext()
    If dirResult = 0 : Break : EndIf
    If dirResult < 0
      RockUartLine("STORAGE LIST FAILED")
      RockUartLine(HwFileErrorText())
      ProcedureReturn -1
    EndIf
    nameBytes = HwDirNameUtf8(@rock_storage_list_name[0], 256)
    If nameBytes <= 0
      RockUartLine("STORAGE NAME FAILED")
      ProcedureReturn -1
    EndIf
    RockUartText(@rock_storage_list_name[0])
    RockUartLine("")
    count = count + 1
  ForEver
  RockUartLine("STORAGE LIST DONE")
  ProcedureReturn count
EndProcedure

Procedure.i RockStorageProofWriteRead()
  Define index.i

  If RockStorageIsEmmc()<>0
    RockUartLine("STORAGE WRITE PROOF REFUSED: EMMC IS READ ONLY; SELECT SD")
    ProcedureReturn 0
  EndIf

  If rock_storage_proof_attempted <> 0
    RockUartLine("STORAGE PROOF ALREADY ATTEMPTED; REBOOT TO RETRY")
    ProcedureReturn 0
  EndIf
  rock_storage_proof_attempted = 1
  rock_storage_proof_error = 0
  If HwStorageUp() = 0
    rock_storage_proof_error = 1
    RockUartLine("STORAGE MOUNT FAILED")
    RockUartLine(RockStorageErrorText())
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf

  ; Never replace an existing file, even if it happens to have the proof name.
  If HwFileOpen(?rock_storage_proof_name) <> 0
    HwFileClose()
    rock_storage_proof_error = 2
    RockUartLine("STORAGE PROOF FILE ALREADY EXISTS; NO WRITE")
    ProcedureReturn 0
  EndIf
  If gHwFileErr <> #HW_FILE_NOTFOUND
    rock_storage_proof_error = 3
    RockUartLine("STORAGE PROOF PRECHECK FAILED; NO WRITE")
    RockUartLine(HwFileErrorText())
    ProcedureReturn 0
  EndIf

  RockUartLine("STORAGE PROOF WRITE BEGIN")
  gHwFileWriter = @RockSdWriteBlocks
  gHwFileWritable = 1
  If HwFileWriteAll(?rock_storage_proof_name, ?rock_storage_proof_data, #ROCK_STORAGE_PROOF_BYTES) = 0
    gHwFileWriter = 0
    gHwFileWritable = 0
    FsSetRangeWriter(0)
    rock_storage_proof_error = 4
    RockUartLine("STORAGE PROOF WRITE FAILED")
    RockUartLine(HwFileErrorText())
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  gHwFileWriter = 0
  gHwFileWritable = 0
  FsSetRangeWriter(0)

  ; HwFileWriteAll flushes the filesystem, but it leaves format caches live.
  ; Tear down and mount the same partition again so this readback reaches the
  ; card rather than satisfying itself from a cache filled during the write.
  If FsUnmount() = 0
    rock_storage_proof_error = 9
    RockUartLine("STORAGE PROOF REMOUNT FAILED AFTER WRITE")
    RockUartLine(FsErrorText())
    ProcedureReturn 0
  EndIf
  rock_storage_up = 0 : gHwFileMounted = 0
  If FsSelectPartition(rock_storage_partition) = 0
    rock_storage_proof_error = 9
    RockUartLine("STORAGE PROOF REMOUNT FAILED AFTER WRITE")
    RockUartLine(FsErrorText())
    ProcedureReturn 0
  EndIf
  rock_storage_up = 1
  gHwFileMounted = 1

  If HwFileOpen(?rock_storage_proof_name) = 0
    rock_storage_proof_error = 5
    RockUartLine("STORAGE PROOF READBACK OPEN FAILED")
    RockUartLine(HwFileErrorText())
    ProcedureReturn 0
  EndIf
  If HwFileSize() <> #ROCK_STORAGE_PROOF_BYTES
    HwFileClose()
    rock_storage_proof_error = 6
    RockUartLine("STORAGE PROOF READBACK SIZE MISMATCH")
    ProcedureReturn 0
  EndIf
  If HwFileReadAt(0, @rock_storage_proof_readback[0], #ROCK_STORAGE_PROOF_BYTES) <> #ROCK_STORAGE_PROOF_BYTES
    HwFileClose()
    rock_storage_proof_error = 7
    RockUartLine("STORAGE PROOF READBACK FAILED")
    RockUartLine(HwFileErrorText())
    RockStorageDiagnostics()
    ProcedureReturn 0
  EndIf
  HwFileClose()

  For index = 0 To #ROCK_STORAGE_PROOF_BYTES - 1
    If PeekA(@rock_storage_proof_readback[0] + index) <> PeekA(?rock_storage_proof_data + index)
      rock_storage_proof_error = 8
      RockUartLine("STORAGE PROOF READBACK MISMATCH")
      ProcedureReturn 0
    EndIf
  Next
  RockUartLine("STORAGE PROOF WRITE AND READBACK PASS")
  ProcedureReturn 1
EndProcedure

DataSection
rock_storage_proof_name:
  Data.s "RK4CPRF.TXT"
rock_storage_proof_data:
  Data.s "RK3399 STORAGE PROOF 1"
EndDataSection

Procedure.i rock_storage_onlySpace(*line, lineLength.i, pos.i)
  While pos < lineLength
    If PeekA(*line + pos) <> 32 And PeekA(*line + pos) <> 9 : ProcedureReturn 0 : EndIf
    pos = pos + 1
  Wend
  ProcedureReturn 1
EndProcedure

; The recovery parser calls this only outside the fatal-exception path. It
; accepts exact words and simple space-delimited paths; every binary operation
; uses the fixed BSS staging array and the stop-and-wait receiver above.
Procedure.i RockStorageCommand(*line, lineLength.i)
  Protected position.i
  Protected wordLength.i
  Protected pathLength.i
  Protected length.i
  Protected checksum.i
  Protected index.i

  position = 0
  wordLength = rock_storage_nextToken(*line, lineLength, @position, @rock_storage_token[0], 256)
  If wordLength <= 0 : ProcedureReturn 0 : EndIf

  If rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_storage, 7) <> 0
    If rock_storage_onlySpace(*line, lineLength, position) = 0 : ProcedureReturn 0 : EndIf
    If HwStorageUp() = 0
      RockUartLine("STORAGE MOUNT FAILED")
      RockUartLine(RockStorageErrorText())
      RockStorageDiagnostics()
      ProcedureReturn 1
    EndIf
    RockUartText("STORAGE READY PARTITION ")
    RockStorageHex8(rock_storage_partition)
    RockUartText(" SECTORS ")
    RockStorageHex8(rock_storage_blocks)
    RockUartLine("")
    ProcedureReturn 1
  EndIf
  If rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_sdmeta, 6) <> 0
    If rock_storage_onlySpace(*line, lineLength, position) = 0 : ProcedureReturn 0 : EndIf
    RockStorageMetadataProbe()
    ProcedureReturn 1
  EndIf
  If rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_ls, 2) <> 0
    If rock_storage_onlySpace(*line, lineLength, position) = 0 : ProcedureReturn 0 : EndIf
    RockStorageProofList()
    ProcedureReturn 1
  EndIf
  If rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_map, 3) <> 0
    If rock_storage_onlySpace(*line, lineLength, position) = 0 : ProcedureReturn 0 : EndIf
    RockUartText("STAGE ")
    RockStorageHex8(@rock_storage_stage[0])
    RockUartText(" BYTES ")
    RockStorageHex8(#ROCK_STORAGE_STAGE_BYTES)
    RockUartLine("")
    ProcedureReturn 1
  EndIf
  If rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_proof, 10) <> 0
    If rock_storage_onlySpace(*line, lineLength, position) = 0 : ProcedureReturn 0 : EndIf
    RockStorageProofWriteRead()
    ProcedureReturn 1
  EndIf

  If rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_get, 3) <> 0 Or rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_read, 4) <> 0
    pathLength = rock_storage_nextToken(*line, lineLength, @position, @rock_storage_path[0], 256)
    If pathLength <= 0 Or rock_storage_onlySpace(*line, lineLength, position) = 0
      RockUartLine("USAGE: get <path>")
      ProcedureReturn 1
    EndIf
    RockStorageGetFile(@rock_storage_path[0])
    ProcedureReturn 1
  EndIf

  If rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_put, 3) <> 0 Or rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_write, 5) <> 0
    pathLength = rock_storage_nextToken(*line, lineLength, @position, @rock_storage_path[0], 256)
    If pathLength <= 0 Or rock_storage_parseHexToken(*line, lineLength, @position, @length) = 0 Or rock_storage_parseHexToken(*line, lineLength, @position, @checksum) = 0 Or rock_storage_onlySpace(*line, lineLength, position) = 0
      RockUartLine("USAGE: put <path> <length-hex> <crc32-hex>")
      ProcedureReturn 1
    EndIf
    RockStoragePutFile(@rock_storage_path[0], length, checksum)
    ProcedureReturn 1
  EndIf

  If rock_storage_tokenIs(@rock_storage_token[0], ?rock_storage_cmd_trust, 11) <> 0
    If rock_storage_parseHexToken(*line, lineLength, @position, @checksum) = 0 Or rock_storage_onlySpace(*line, lineLength, position) = 0
      RockUartLine("USAGE: trustupdate <crc32-hex>  (fixed 4 MiB BL3X image)")
      ProcedureReturn 1
    EndIf
    RockStorageTrustUpdate(checksum)
    ProcedureReturn 1
  EndIf

  ProcedureReturn 0
EndProcedure

DataSection
rock_storage_cmd_storage: Data.s "storage"
rock_storage_cmd_sdmeta:  Data.s "sdmeta"
rock_storage_cmd_ls:      Data.s "ls"
rock_storage_cmd_map:     Data.s "map"
rock_storage_cmd_proof:   Data.s "writeproof"
rock_storage_cmd_get:     Data.s "get"
rock_storage_cmd_read:    Data.s "read"
rock_storage_cmd_put:     Data.s "put"
rock_storage_cmd_write:   Data.s "write"
rock_storage_cmd_trust:   Data.s "trustupdate"
EndDataSection
