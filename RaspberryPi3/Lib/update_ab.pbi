; Pi3 AArch64 A/B updater. Flat composition: FAT32 read layer, SHA256,
; Pi3SdReadBlock/Pi3SdWriteBlock. No FAT/directory/allocation writes.
; Provision five contiguous, non-overlapping files before first deployment:
; ANVILA.BIN, ANVILB.BIN (equal fixed capacity), P3CTRLA.BIN/P3CTRLB.BIN
; (512 bytes), KERNEL8.IMG (immutable loader). Transport is a separate owner.
; The shared A/B record owns the on-disk format. Keep these names as source
; Compatibility aliases for the updater's older call sites.
#PI3_UPDATE_LOAD = #P3AB_LOAD
#PI3_UPDATE_LIMIT = $1000000
#PI3_UPDATE_MAGIC = #P3AB_MAGIC
#PI3_UPDATE_PENDING = #P3AB_PENDING
#PI3_UPDATE_TRIED = #P3AB_TRIED
#PI3_UPDATE_CONFIRMED = #P3AB_CONFIRMED
#PI3_UPDATE_HEADER = #P3AB_HEADER ; P3SLOT 128 + PMFBOOT v2 128
#PI3_UPDATE_HANDOFF = #P3AB_HANDOFF
#PI3_UPDATE_SOURCE_NONE = 0
#PI3_UPDATE_SOURCE_SERIAL = 1
#PI3_UPDATE_SOURCE_ETHERNET = 2
Global Dim pi3_up_lba.i[5]
Global Dim pi3_up_span.i[5]
Global Dim pi3_up_size.i[5]
Global Dim pi3_up_record.l[256] ; two record cache; validation/layout are shared
Global Dim pi3_up_sector.l[128]
Global Dim pi3_up_expected.a[32]
Global Dim pi3_up_digest.a[32]
Global Dim pi3_up_dir_name.a[12]
Global pi3_up_stage.i
Global pi3_up_stage_bytes.i
Global pi3_up_ram.i
Global pi3_up_ram_bytes.i
Global pi3_up_mounted.i
Global pi3_up_active.i = -1
Global pi3_up_generation.i
Global pi3_up_length.i
Global pi3_up_received.i
Global pi3_up_receiving.i
Global pi3_up_error.i
Global pi3_up_loaded.i
Global pi3_up_max_generation.i
Global pi3_up_pending.i = -1
Global pi3_up_baseline.i = -1
Global pi3_up_handoff_ready.i
Global pi3_up_boot_phase.i
Global pi3_up_source.i
Global pi3_up_mount_phase.i
Global pi3_up_work_token.i
Global pi3_up_work_failed.i
Global *pi3_up_work_handler
#PI3_UP_HASH_CHUNK = 4096

; One monotonic progress contract feeds the cold-storage watchdog. The token
; is reset on registration and only advances after completed bounded work.
Procedure.i Pi3UpdateWorkProgressHandler(handler.i)
  pi3_up_work_handler = handler
  pi3_up_work_token = 0
  pi3_up_work_failed = 0
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3UpdateWorkToken()
  ProcedureReturn pi3_up_work_token
EndProcedure
Procedure.i Pi3UpdateWorkProgress(completed.i)
  If pi3_up_work_failed<>0 : ProcedureReturn 0 : EndIf
  If completed<1 Or completed>$7FFFFFFFFFFFFFFF-pi3_up_work_token
    pi3_up_work_failed=1 : ProcedureReturn 0
  EndIf
  pi3_up_work_token=pi3_up_work_token+completed
  If pi3_up_work_handler<>0
    If pi3_up_work_handler(pi3_up_work_token)=0
      pi3_up_work_failed=1 : ProcedureReturn 0
    EndIf
  EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3UpdateSdProgress(completed.i)
  ProcedureReturn Pi3UpdateWorkProgress(completed)
EndProcedure

Procedure.i Pi3NoMountProgress()
  ProcedureReturn 1
EndProcedure
Global pi3_up_mount_progress.i = @Pi3NoMountProgress

Procedure.i Pi3UpdateMountProgressHandler(handler.i)
  pi3_up_mount_progress = handler
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UpdateMountPhase()
  ProcedureReturn pi3_up_mount_phase
EndProcedure

Procedure pi3UpMountMark(phase.i)
  pi3_up_mount_phase = phase
  If pi3_up_mount_progress <> 0 : pi3_up_mount_progress() : EndIf
EndProcedure

Procedure.i Pi3NoBootProgress()
  ProcedureReturn 1
EndProcedure
Global pi3_up_boot_progress.i = @Pi3NoBootProgress

Procedure.i Pi3UpdateBootProgressHandler(handler.i)
  If pi3_up_receiving<>0 Or pi3_up_loaded<>0 Or handler=0 : ProcedureReturn 0 : EndIf
  pi3_up_boot_progress=handler
  ProcedureReturn 1
EndProcedure

Procedure.i pi3UpBootProgress(phase.i)
  If phase<1 Or phase>4 : ProcedureReturn 0 : EndIf
  pi3_up_boot_phase=phase
  ; Direct unit/emulator entry does not execute the image initializer. A zero
  ; hook means observe the phase only; the immutable loader installs its hook.
  If pi3_up_boot_progress=0 : ProcedureReturn 1 : EndIf
  ProcedureReturn pi3_up_boot_progress()
EndProcedure

Procedure.i pi3UpFail(code.i)
  pi3_up_error = code
  ProcedureReturn 0
EndProcedure
Procedure.i Pi3UpdateError()
  ProcedureReturn pi3_up_error
EndProcedure
Procedure.i Pi3UpdateReceived()
  ProcedureReturn pi3_up_received
EndProcedure
Procedure.i Pi3UpdateSource()
  ProcedureReturn pi3_up_source
EndProcedure
Procedure.i Pi3UpdateSlot()
  ProcedureReturn pi3_up_active
EndProcedure
Procedure.i Pi3UpdateGeneration()
  ProcedureReturn pi3_up_generation
EndProcedure
Procedure.i Pi3UpdatePendingSlot()
  ProcedureReturn pi3_up_pending
EndProcedure
Procedure.i Pi3UpdatePendingGeneration()
  If pi3_up_pending < 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn PeekI(@pi3_up_record[0] + pi3_up_pending * 512 + 8)
EndProcedure
Procedure.i Pi3UpdateResetReady()
  If pi3_up_mounted = 0 Or pi3_up_receiving <> 0 Or pi3_up_handoff_ready <> 0 Or pi3_up_active < 0 : ProcedureReturn 0 : EndIf
  If pi3UpRecordValid(pi3_up_active) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn PeekL(@pi3_up_record[0] + pi3_up_active * 512 + 64) = #PI3_UPDATE_CONFIRMED
EndProcedure
Procedure.i pi3UpRam(p.i, bytes.i)
  If bytes < 0 Or p < pi3_up_ram Or bytes > pi3_up_ram_bytes : ProcedureReturn 0 : EndIf
  ProcedureReturn p - pi3_up_ram <= pi3_up_ram_bytes - bytes
EndProcedure
Procedure.i pi3UpEqual(a.i, b.i, bytes.i)
  Protected n.i
  For n = 0 To bytes - 1
    If PeekA(a + n) <> PeekA(b + n) : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure
Procedure.i Pi3UpdateConfigure(stageBase.i, stageBytes.i, ramBase.i, ramBytes.i, dtbBase.i, dtbBytes.i)
  If pi3_up_mounted <> 0 Or pi3_up_receiving <> 0 : ProcedureReturn pi3UpFail(-1) : EndIf
  ; The caller supplies firmware-validated RAM/DTB extents. Require the DTB at
  ; its current pinned location and keep image destination below it.
  If ramBase <> 0 Or ramBytes < $3000000 Or ramBytes > $3F000000
    ProcedureReturn pi3UpFail(-2)
  EndIf
  If dtbBase <> #PI3_UPDATE_LIMIT Or dtbBytes < 40 Or dtbBytes > $100000
    ProcedureReturn pi3UpFail(-2)
  EndIf
  If stageBase < $2000000 Or (stageBase & 511) <> 0 Or stageBytes < 512 Or stageBytes > #PI3_UPDATE_LIMIT - #PI3_UPDATE_LOAD
    ProcedureReturn pi3UpFail(-2)
  EndIf
  If stageBase > ramBytes - stageBytes : ProcedureReturn pi3UpFail(-2) : EndIf
  pi3_up_ram = ramBase
  pi3_up_ram_bytes = ramBytes
  pi3_up_stage = stageBase
  pi3_up_stage_bytes = stageBytes
  pi3_up_error = 0
  ProcedureReturn 1
EndProcedure

Procedure.i pi3UpMap(index.i, name.i)
  Protected firstLba.i
  Protected blocks.i
  Protected bytes.i
  If FsExtentOf(name, @firstLba, @blocks, @bytes) = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
  If bytes < 1 Or bytes > #PI3_UPDATE_LIMIT - #PI3_UPDATE_LOAD Or blocks < 1
    ProcedureReturn pi3UpFail(-3)
  EndIf
  pi3_up_lba[index] = firstLba
  pi3_up_span[index] = blocks
  pi3_up_size[index] = bytes
  pi3UpMountMark(12 + index)
  ProcedureReturn 1
EndProcedure

; P3SLOT v1 (128 bytes) wraps compiler-owned PMFBOOT v2 (128 bytes).
; Fixed metadata is admission policy, not a signature/authenticity claim.
Procedure.i pi3UpContainer(p.i, bytes.i)
  Protected n.i
  Protected pmf.i
  Protected imageBytes.i
  Protected bssBytes.i
  Protected take.i
  If bytes < #PI3_UPDATE_HEADER + 4 Or bytes > pi3_up_stage_bytes : ProcedureReturn 0 : EndIf
  If PeekI(p) <> $0000544F4C533350 Or PeekL(p + 8) <> 1 Or PeekL(p + 12) <> 128 : ProcedureReturn 0 : EndIf
  If PeekL(p + 16) <> 2837 Or PeekL(p + 20) <> 64 Or PeekI(p + 24) <> $1F00000 : ProcedureReturn 0 : EndIf
  If PeekI(p + 32) <> bytes - 128 : ProcedureReturn 0 : EndIf
  For n = 72 To 127 : If PeekA(p + n) <> 0 : ProcedureReturn 0 : EndIf : Next
  pmf = p + 128
  If PeekI(pmf) <> $00544F4F42464D50 Or PeekL(pmf + 8) <> 2 Or PeekL(pmf + 12) <> 128 : ProcedureReturn 0 : EndIf
  If PeekI(pmf + 16) <> #PI3_UPDATE_LOAD Or PeekI(pmf + 24) <> #PI3_UPDATE_LOAD : ProcedureReturn 0 : EndIf
  imageBytes = PeekI(pmf + 32)
  If imageBytes < 4 Or imageBytes <> bytes - #PI3_UPDATE_HEADER Or imageBytes > #PI3_UPDATE_LIMIT - #PI3_UPDATE_LOAD : ProcedureReturn 0 : EndIf
  bssBytes = PeekI(pmf + 48)
  If PeekI(pmf + 40) <> $1100000 Or bssBytes < 0 Or bssBytes > $D00000 : ProcedureReturn 0 : EndIf
  ; Nonreturning, no service-table ABI. DTB handoff is the P3SLOT contract;
  ; current PMFBOOT emitters do not expose its reserved WANTS_DTB flag.
  If PeekL(pmf + 56) <> 0 Or PeekL(pmf + 60) <> 0 : ProcedureReturn 0 : EndIf
  ; Reject a correctly-shaped image for another A64 board. This metadata is
  ; compiler-owned so the wrapper cannot relabel a Pi 4 image as Pi 3 code.
  If PeekL(pmf + 96) <> 1 Or PeekL(pmf + 100) <> 2837 Or PeekI(pmf + 104) <> $1F00000 : ProcedureReturn 0 : EndIf
  For n = 112 To 127 : If PeekA(pmf + n) <> 0 : ProcedureReturn 0 : EndIf : Next
  pi3UpMountMark(50)
  If pi3UpHashRam(pmf+128,imageBytes)=0 : ProcedureReturn 0 : EndIf
  If pi3UpEqual(@pi3_up_digest[0], pmf + 64, 32) = 0 : ProcedureReturn 0 : EndIf
  pi3UpMountMark(51)
  If pi3UpHashRam(pmf,bytes-128)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn pi3UpEqual(@pi3_up_digest[0], p + 40, 32)
EndProcedure

Procedure.i pi3UpRecordValid(slot.i)
  Protected p.i
  Protected maximum.i
  If slot < 0 Or slot > 1 : ProcedureReturn 0 : EndIf
  p = @pi3_up_record[0] + slot * 512
  maximum = pi3_up_size[slot]
  If maximum > pi3_up_stage_bytes : maximum = pi3_up_stage_bytes : EndIf
  ProcedureReturn AbRecordValid(p, slot, maximum)
EndProcedure

; Control records are addressed by their explicit FAT32 names. The read side
; may use the normal file facade; the write side must use FsOverwriteFixed so
; no truncate, allocation, directory, or FAT metadata operation can occur.






Procedure.i pi3UpVerifySlot(slot.i)
  Protected p.i
  Protected bytes.i
  If pi3UpRecordValid(slot) = 0 : ProcedureReturn 0 : EndIf
  p = @pi3_up_record[0] + slot * 512
  bytes = PeekI(p + 16)
  pi3UpMountMark(20 + slot)
  If pi3UpHashSlot(slot, bytes, pi3_up_stage) = 0 : ProcedureReturn 0 : EndIf
  If pi3UpEqual(@pi3_up_digest[0], p + 32, 32) = 0 : ProcedureReturn 0 : EndIf
  pi3UpMountMark(30 + slot)
  ProcedureReturn pi3UpContainer(pi3_up_stage, bytes)
EndProcedure

; Reading a slot used to cost one single-block call per 512 bytes AND a copy of
; every byte, one PokeA/PeekA at a time, into staging. With the MMU and caches
; off every one of those is an uncached Device-memory access, so a 14 MiB slot
; cost about 29 million of them on top of its 28,672 reads - and the loader does
; this at L1, again at L3 and once more at L4. That is where the minutes went.
;
; When there is somewhere to put the image, the blocks are read STRAIGHT INTO IT
; as one contiguous range and hashed from there. The copy disappears entirely
; rather than getting faster. The slot's extent is already proven contiguous by
; pi3UpMap before this can run, which is what makes one range legal.
;
; Note what this does NOT claim: the block driver still issues one command per
; block, so the number of SD commands is unchanged. The saving here is the
; 29 million byte accesses, not the read count.
Procedure.i pi3UpHashRam(p.i, bytes.i)
  Protected offset.i
  Protected take.i
  Sha256Begin()
  offset = 0
  While offset < bytes
    take = bytes - offset
    If take > #PI3_UP_HASH_CHUNK : take = #PI3_UP_HASH_CHUNK : EndIf
    Sha256Update(p + offset, take)
    If Pi3UpdateWorkProgress(take)=0 : ProcedureReturn 0 : EndIf
    offset = offset + take
  Wend
  Sha256End(@pi3_up_digest[0])
  ProcedureReturn 1
EndProcedure

Procedure.i pi3UpHashSlot(slot.i, bytes.i, destination.i)
  Protected offset.i
  Protected take.i
  Protected blocks.i
  Protected buffer.i
  If bytes < 1 : ProcedureReturn 0 : EndIf
  blocks = (bytes + 511) / 512
  ; A trailing partial block still lands whole, so staging must have room for
  ; the rounded-up length, not just for `bytes`.
  If destination <> 0 And blocks * 512 > pi3_up_stage_bytes : ProcedureReturn 0 : EndIf
  If blocks > pi3_up_span[slot] : ProcedureReturn 0 : EndIf
  If destination <> 0
    If Pi3SdReadBlocks(pi3_up_lba[slot], blocks, destination) = 0 : ProcedureReturn 0 : EndIf
    ; The read has completed; the next operation is pure SHA work over RAM.
    pi3UpMountMark(40 + slot)
    If pi3UpHashRam(destination, bytes)=0 : ProcedureReturn 0 : EndIf
  Else
    Sha256Begin()
    ; Verification with nowhere to stage: one sector of scratch, as before.
    buffer = @pi3_up_sector[0]
    offset = 0
    While offset < bytes
      If Pi3SdReadBlock(pi3_up_lba[slot] + offset / 512, buffer) = 0 : ProcedureReturn 0 : EndIf
      take = bytes - offset
      If take > 512 : take = 512 : EndIf
      Sha256Update(buffer, take)
      If Pi3UpdateWorkProgress(take)=0 : ProcedureReturn 0 : EndIf
      offset = offset + take
    Wend
  EndIf
  If destination = 0 : Sha256End(@pi3_up_digest[0]) : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i pi3UpOwnedName(p.i)
  If pi3UpEqual(p, "ANVILA  BIN", 11) <> 0 : ProcedureReturn 0 : EndIf
  If pi3UpEqual(p, "ANVILB  BIN", 11) <> 0 : ProcedureReturn 1 : EndIf
  If pi3UpEqual(p, "P3CTRLA BIN", 11) <> 0 : ProcedureReturn 2 : EndIf
  If pi3UpEqual(p, "P3CTRLB BIN", 11) <> 0 : ProcedureReturn 3 : EndIf
  If pi3UpEqual(p, "KERNEL8 IMG", 11) <> 0 : ProcedureReturn 4 : EndIf
  ProcedureReturn -1
EndProcedure

Global pi3_up_ownedSeen.i

Procedure.i pi3UpAllocationEntry(name.i, depth.i, firstLba.i, bytes.i, attr.i, context.i)
  Protected owned.i
  owned = -1
  If depth = 0 : owned = pi3UpOwnedName(name) : EndIf
  If owned < 0 : ProcedureReturn 1 : EndIf
  If (attr & $10) <> 0 Or bytes <> pi3_up_size[owned] Or firstLba <> pi3_up_lba[owned] : ProcedureReturn 0 : EndIf
  If (pi3_up_ownedSeen & (1 << owned)) <> 0 : ProcedureReturn 0 : EndIf
  pi3_up_ownedSeen = pi3_up_ownedSeen | (1 << owned)
  ProcedureReturn 2
EndProcedure

Procedure.i pi3UpAllocationRange(firstLba.i, blocks.i, context.i)
  Protected a.i
  For a = 0 To 4
    If firstLba < pi3_up_lba[a] + pi3_up_span[a] And pi3_up_lba[a] < firstLba + blocks : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i pi3UpForeignFiles()
  pi3_up_ownedSeen = 0
  If FsWalkAllocations(@pi3UpAllocationEntry, @pi3UpAllocationRange, 0) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn pi3_up_ownedSeen = 31
EndProcedure

Procedure.i pi3UpHandoffHeader()
  Protected p.i
  p = #PI3_UPDATE_HANDOFF
  If PeekI(p) <> $0031464F483350 Or PeekL(p + 8) <> 2 : ProcedureReturn 0 : EndIf
  If PeekL(p + 12) < 0 Or PeekL(p + 12) > 1 Or PeekI(p + 16) < 1 : ProcedureReturn 0 : EndIf
  If PeekI(p + 24) <> #PI3_UPDATE_LIMIT : ProcedureReturn 0 : EndIf
  If PeekL(p + 32) <> #PI3_UPDATE_TRIED And PeekL(p + 32) <> #PI3_UPDATE_CONFIRMED : ProcedureReturn 0 : EndIf
  ProcedureReturn (PeekL(p + 124) & $FFFFFFFF) = Crc32(p, 124)
EndProcedure
Procedure.i pi3UpHandoffMatches()
  Protected h.i
  Protected p.i
  Protected slot.i
  If pi3UpHandoffHeader() = 0 : ProcedureReturn 0 : EndIf
  h = #PI3_UPDATE_HANDOFF : slot = PeekL(h + 12)
  If pi3UpRecordValid(slot) = 0 : ProcedureReturn 0 : EndIf
  p = @pi3_up_record[0] + slot * 512
  If PeekI(p + 8) <> PeekI(h + 16) Or PeekL(p + 64) <> PeekL(h + 32) Or PeekI(p + 16) <> PeekI(h + 40) : ProcedureReturn 0 : EndIf
  ProcedureReturn pi3UpEqual(p + 32, h + 48, 32)
EndProcedure
Procedure.i pi3UpMountCommon(handoff.i)
  Protected a.i
  Protected b.i
  Protected validA.i
  Protected validB.i
  Protected p.i
  If pi3_up_stage = 0 Or pi3_up_receiving <> 0 : ProcedureReturn pi3UpFail(-1) : EndIf
  pi3_up_mounted = 0
  pi3_up_active = -1
  pi3_up_generation = 0
  pi3_up_max_generation = 0
  pi3_up_pending = -1
  pi3_up_baseline = -1
  pi3_up_handoff_ready = 0
  pi3UpMountMark(1)
  If handoff <> 0
    If pi3UpHandoffHeader() = 0 : ProcedureReturn pi3UpFail(-16) : EndIf
  EndIf
  FsSetRangeReader(@Pi3SdReadBlocks)
  FsSetRangeWriter(0)
  If FsMount(1) = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
  pi3UpMountMark(2)
  If pi3UpMap(0, "ANVILA.BIN") = 0 Or pi3UpMap(1, "ANVILB.BIN") = 0 Or pi3UpMap(2, "P3CTRLA.BIN") = 0 Or pi3UpMap(3, "P3CTRLB.BIN") = 0 Or pi3UpMap(4, "KERNEL8.IMG") = 0 : ProcedureReturn 0 : EndIf
  If pi3_up_size[0] <> pi3_up_size[1] Or (pi3_up_size[0] & 511) <> 0 Or pi3_up_size[2] <> 512 Or pi3_up_size[3] <> 512 Or pi3_up_size[4] > $180000
    ProcedureReturn pi3UpFail(-3)
  EndIf
  For a = 0 To 4
    If pi3_up_lba[a] < FsDataLba() Or pi3_up_lba[a] > FsDataEnd() - pi3_up_span[a] : ProcedureReturn pi3UpFail(-3) : EndIf
    For b = a + 1 To 4
      If pi3_up_lba[a] < pi3_up_lba[b] + pi3_up_span[b] And pi3_up_lba[b] < pi3_up_lba[a] + pi3_up_span[a] : ProcedureReturn pi3UpFail(-3) : EndIf
    Next
  Next
  pi3UpMountMark(3)
  If FsWalkRoot(@pi3UpAllocationRange, 0) = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
  ; The loader proves the full tree; the trusted handoff retains its bounded
  ; root-only recheck inside the candidate watchdog window.
  If handoff = 0
    pi3UpMountMark(4)
    If pi3UpForeignFiles() = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
  EndIf
  ; Read failure is not a blank record. Refuse mutation of an unknown medium.
  pi3UpMountMark(5)
  pi3UpMountMark(60)
  If Pi3BootReadRecord(0, @pi3_up_record[0]) = 0 : ProcedureReturn pi3UpFail(-4) : EndIf
  pi3UpMountMark(61)
  If Pi3BootReadRecord(1, @pi3_up_record[128]) = 0 : ProcedureReturn pi3UpFail(-4) : EndIf
  validA = pi3UpRecordValid(0)
  validB = pi3UpRecordValid(1)
  If validA <> 0 And validB <> 0 And PeekI(@pi3_up_record[0] + 8) = PeekI(@pi3_up_record[128] + 8) : ProcedureReturn pi3UpFail(-5) : EndIf
  If handoff <> 0
    ; The immutable loader just hashed this exact container and handed off
    ; its record identity. Revalidate metadata/ownership, not 42 MiB under a
    ; 15-second watchdog. Never infer the running slot from disk ordering.
    If pi3UpHandoffMatches() = 0 : ProcedureReturn pi3UpFail(-16) : EndIf
    a = PeekL(#PI3_UPDATE_HANDOFF + 12)
    p = @pi3_up_record[0] + a * 512
    If PeekL(p + 64) = #PI3_UPDATE_TRIED
      b = 1 - a
      If pi3UpRecordValid(b) = 0 Or PeekL(@pi3_up_record[0] + b * 512 + 64) <> #PI3_UPDATE_CONFIRMED : ProcedureReturn pi3UpFail(-6) : EndIf
      pi3_up_baseline = b
    Else
      pi3_up_baseline = a
    EndIf
    pi3_up_active = a : pi3_up_generation = PeekI(p + 8)
    pi3_up_max_generation = pi3_up_generation
    For b = 0 To 1
      If pi3UpRecordValid(b) <> 0
        If PeekI(@pi3_up_record[0] + b * 512 + 8) > pi3_up_max_generation : pi3_up_max_generation = PeekI(@pi3_up_record[0] + b * 512 + 8) : EndIf
      EndIf
    Next
    Pi3SdSetWriteWindow(0, 0)
    pi3UpMountMark(8)
    pi3_up_handoff_ready = 1 : pi3_up_mounted = 1 : pi3_up_error = 0
    ProcedureReturn 1
  EndIf
  ; Updates always preserve a confirmed baseline. A pending candidate is a
  ; separate boot choice; a tried but unconfirmed candidate is never retried.
  For a = 0 To 1
    pi3UpMountMark(10 + a)
    If (a = 0 And validA <> 0) Or (a = 1 And validB <> 0)
      p = @pi3_up_record[0] + a * 512
      If PeekI(p + 8) > pi3_up_max_generation : pi3_up_max_generation = PeekI(p + 8) : EndIf
      If pi3UpVerifySlot(a) <> 0
        If PeekL(p + 64) = #PI3_UPDATE_CONFIRMED
          If PeekI(p + 8) > pi3_up_generation
            pi3_up_active = a
            pi3_up_generation = PeekI(p + 8)
          EndIf
        ElseIf PeekL(p + 64) = #PI3_UPDATE_PENDING
          pi3_up_pending = a
        EndIf
      EndIf
    EndIf
  Next
  If pi3_up_work_failed<>0 : ProcedureReturn pi3UpFail(-17) : EndIf
  ; Initial provisioning must install one valid fallback; no blind first write.
  If pi3_up_active < 0 : ProcedureReturn pi3UpFail(-6) : EndIf
  pi3_up_baseline = pi3_up_active
  ; Block layer independently caps this data-only fence at card capacity.
  ; Even an accidental write caller cannot reach MBR/FAT sectors outside
  ; this data area; this updater additionally excludes all directory/other files.
  Pi3SdSetWriteWindow(0, 0)
  pi3UpMountMark(8)
  pi3_up_mounted = 1
  pi3_up_error = 0
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UpdateMount()
  ProcedureReturn pi3UpMountCommon(0)
EndProcedure
Procedure.i Pi3UpdateMountHandoff()
  ProcedureReturn pi3UpMountCommon(1)
EndProcedure

Procedure.i Pi3UpdateBeginFrom(source.i,bytes.i,expectedSha.i)
  Protected n.i
  If source<>#PI3_UPDATE_SOURCE_SERIAL And source<>#PI3_UPDATE_SOURCE_ETHERNET : ProcedureReturn pi3UpFail(-18) : EndIf
  If pi3_up_mounted = 0 Or pi3_up_receiving <> 0 : ProcedureReturn pi3UpFail(-1) : EndIf
  If bytes < #PI3_UPDATE_HEADER + 4 Or bytes > pi3_up_size[0] Or bytes > pi3_up_stage_bytes Or pi3UpRam(expectedSha, 32) = 0 : ProcedureReturn pi3UpFail(-7) : EndIf
  If pi3_up_max_generation >= $7FFFFFFFFFFFFFFE : ProcedureReturn pi3UpFail(-7) : EndIf
  If PeekL(@pi3_up_record[0] + pi3_up_active * 512 + 64) <> #PI3_UPDATE_CONFIRMED : ProcedureReturn pi3UpFail(-7) : EndIf
  For n = 0 To 31 : pi3_up_expected[n] = PeekA(expectedSha + n) : Next
  pi3_up_length = bytes
  pi3_up_received = 0
  pi3_up_source = source
  pi3_up_receiving = 1
  pi3_up_error = 0
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UpdateBegin(bytes.i,expectedSha.i)
  ProcedureReturn Pi3UpdateBeginFrom(#PI3_UPDATE_SOURCE_SERIAL,bytes,expectedSha)
EndProcedure

Procedure.i Pi3UpdateChunkFrom(owner.i,offset.i,source.i,bytes.i)
  Protected n.i
  If pi3_up_receiving = 0 : ProcedureReturn pi3UpFail(-1) : EndIf
  If owner<>pi3_up_source : ProcedureReturn pi3UpFail(-18) : EndIf
  If offset < 0 Or bytes < 1 Or bytes > 1024 Or bytes > pi3_up_length Or offset > pi3_up_length - bytes Or pi3UpRam(source, bytes) = 0 : ProcedureReturn pi3UpFail(-8) : EndIf
  If offset < pi3_up_received
    If offset + bytes > pi3_up_received Or pi3UpEqual(pi3_up_stage + offset, source, bytes) = 0 : ProcedureReturn pi3UpFail(-8) : EndIf
    ProcedureReturn 1
  EndIf
  If offset <> pi3_up_received : ProcedureReturn pi3UpFail(-8) : EndIf
  ; Reject overlapping input unless exact destination (the transport normally
  ; uses its separate small receive buffer). Forward copy must not self-corrupt.
  If source <> pi3_up_stage + offset And source < pi3_up_stage + offset + bytes And pi3_up_stage + offset < source + bytes : ProcedureReturn pi3UpFail(-8) : EndIf
  For n = 0 To bytes - 1 : PokeA(pi3_up_stage + offset + n, PeekA(source + n)) : Next
  pi3_up_received = pi3_up_received + bytes
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UpdateChunk(offset.i,source.i,bytes.i)
  ProcedureReturn Pi3UpdateChunkFrom(pi3_up_source,offset,source,bytes)
EndProcedure

Procedure.i Pi3UpdateAbortFrom(owner.i)
  If pi3_up_receiving<>0 And owner<>pi3_up_source : ProcedureReturn pi3UpFail(-18) : EndIf
  pi3_up_receiving = 0
  pi3_up_received = 0
  pi3_up_length = 0
  pi3_up_source = #PI3_UPDATE_SOURCE_NONE
  ProcedureReturn 1
EndProcedure

Procedure Pi3UpdateAbort()
  Pi3UpdateAbortFrom(pi3_up_source)
EndProcedure

Procedure.i Pi3UpdateCommitFrom(owner.i)
  Protected target.i
  Protected offset.i
  Protected n.i
  Protected take.i
  Protected p.i
  If pi3_up_mounted = 0 Or pi3_up_receiving = 0 Or pi3_up_received <> pi3_up_length : ProcedureReturn pi3UpFail(-1) : EndIf
  If owner<>pi3_up_source : ProcedureReturn pi3UpFail(-18) : EndIf
  Sha256Of(pi3_up_stage, pi3_up_length, @pi3_up_digest[0])
  If pi3UpEqual(@pi3_up_digest[0], @pi3_up_expected[0], 32) = 0 : ProcedureReturn pi3UpFail(-9) : EndIf
  If pi3UpContainer(pi3_up_stage, pi3_up_length) = 0 : ProcedureReturn pi3UpFail(-13) : EndIf
  target = 1 - pi3_up_active
  ; Once disk mutation starts, any error forces remount before another attempt.
  pi3_up_mounted = 0
  pi3_up_receiving = 0
  pi3_up_source = #PI3_UPDATE_SOURCE_NONE
  Pi3SdSetWriteWindow(0, 0)
  offset = 0
  If Pi3SdSetWriteWindow(pi3_up_lba[target], pi3_up_span[target]) = 0 : ProcedureReturn pi3UpFail(-10) : EndIf
  While offset < pi3_up_length
    take = pi3_up_length - offset
    If take > 512 : take = 512 : EndIf
    For n = 0 To 511 : PokeA(@pi3_up_sector[0] + n, 0) : Next
    For n = 0 To take - 1 : PokeA(@pi3_up_sector[0] + n, PeekA(pi3_up_stage + offset + n)) : Next
    If Pi3SdWriteBlock(pi3_up_lba[target] + offset / 512, @pi3_up_sector[0]) = 0
      Pi3SdSetWriteWindow(0, 0)
      ProcedureReturn pi3UpFail(-10)
    EndIf
    offset = offset + take
  Wend
  Pi3SdSetWriteWindow(0, 0)
  If pi3UpHashSlot(target, pi3_up_length, 0) = 0 : ProcedureReturn pi3UpFail(-11) : EndIf
  If pi3UpEqual(@pi3_up_digest[0], @pi3_up_expected[0], 32) = 0 : ProcedureReturn pi3UpFail(-11) : EndIf
  p = @pi3_up_record[0] + target * 512
  If AbRecordInit(p, target, pi3_up_max_generation + 1, pi3_up_length, @pi3_up_expected[0], #P3AB_PENDING) = 0 : ProcedureReturn pi3UpFail(-12) : EndIf
  AbSetIo(@Pi3BootReadRecord, @Pi3BootWriteRecord)
  If AbWriteRecord(target, p) = 0 : ProcedureReturn pi3UpFail(-12) : EndIf
  ; Old slot/control record remain intact. No reset, FAT update or deletion.
  pi3_up_max_generation = pi3_up_max_generation + 1
  pi3_up_pending = target
  pi3_up_mounted = 1
  pi3_up_error = 0
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UpdateCommit()
  ProcedureReturn Pi3UpdateCommitFrom(pi3_up_source)
EndProcedure

; The confirmed other record remains untouched through every state write.
Procedure.i pi3UpState(slot.i, state.i)
  Protected p.i
  p = @pi3_up_record[0] + slot * 512
  AbSetIo(@Pi3BootReadRecord, @Pi3BootWriteRecord)
  If AbSetRecordState(slot, p, state) = 0
    pi3_up_mounted = 0 : ProcedureReturn pi3UpFail(-14)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i pi3UpPlace(slot.i)
  Protected n.i
  Protected bytes.i
  Protected p.i
  Protected offset.i
  Protected take.i
  If pi3UpBootProgress(3)=0 : ProcedureReturn pi3UpFail(-17) : EndIf
  If pi3UpVerifySlot(slot) = 0 : ProcedureReturn pi3UpFail(-11) : EndIf
  p = @pi3_up_record[0] + slot * 512
  bytes = PeekI(p + 16) - #PI3_UPDATE_HEADER
  If pi3UpBootProgress(4)=0 : ProcedureReturn pi3UpFail(-17) : EndIf
  offset=0
  While offset<bytes
    take=bytes-offset : If take>4096 : take=4096 : EndIf
    For n=offset To offset+take-1
      PokeA(#PI3_UPDATE_LOAD + n, PeekA(pi3_up_stage + #PI3_UPDATE_HEADER + n))
    Next
    If Pi3UpdateWorkProgress(take)=0 : ProcedureReturn pi3UpFail(-17) : EndIf
    offset=offset+take
  Wend
  pi3_up_active = slot
  pi3_up_generation = PeekI(p + 8)
  pi3_up_loaded = bytes
  ProcedureReturn bytes
EndProcedure

Procedure.i Pi3UpdateLoad()
  Protected slot.i
  Protected p.i
  If pi3_up_mounted = 0 Or pi3_up_receiving <> 0 : ProcedureReturn pi3UpFail(-1) : EndIf
  slot = pi3_up_pending
  If slot >= 0
    p = @pi3_up_record[0] + slot * 512
    If PeekI(p + 8) > pi3_up_generation
      If Pi3UpBootProgress(1)=0 : ProcedureReturn pi3UpFail(-17) : EndIf
    EndIf
    If PeekI(p + 8) > pi3_up_generation And pi3UpVerifySlot(slot) <> 0
      ; Commit TRIED before copying/branching. A lost or torn acknowledgement
      ; refuses this boot; next boot still has the confirmed fallback.
      If Pi3UpBootProgress(2)=0 : ProcedureReturn pi3UpFail(-17) : EndIf
      If pi3UpState(slot, #PI3_UPDATE_TRIED) = 0 : ProcedureReturn 0 : EndIf
      ProcedureReturn pi3UpPlace(slot)
    EndIf
  EndIf
  If PeekL(@pi3_up_record[0] + pi3_up_active * 512 + 64) <> #PI3_UPDATE_CONFIRMED : ProcedureReturn pi3UpFail(-15) : EndIf
  ProcedureReturn pi3UpPlace(pi3_up_active)
EndProcedure

Procedure.i Pi3UpdateLoadFallback()
  Protected slot.i
  slot = pi3_up_baseline
  ; Before a normal confirmed boot F selects the older confirmed record.
  ; After pending/tried selection/failure, baseline is the known-good owner.
  If pi3_up_pending < 0 And pi3_up_active = pi3_up_baseline : slot = 1 - pi3_up_baseline : EndIf
  If pi3_up_mounted = 0 Or pi3_up_receiving <> 0 Or slot < 0 Or slot > 1 : ProcedureReturn pi3UpFail(-1) : EndIf
  If pi3UpRecordValid(slot) = 0 : ProcedureReturn pi3UpFail(-15) : EndIf
  If PeekL(@pi3_up_record[0] + slot * 512 + 64) <> #PI3_UPDATE_CONFIRMED : ProcedureReturn pi3UpFail(-15) : EndIf
  ProcedureReturn pi3UpPlace(slot)
EndProcedure

; Only the boot composition calls this with its captured running-slot identity,
; after SD mount and prompt readiness. Never infer identity from newest record.
Procedure.i Pi3UpdateConfirm(slot.i, generation.i)
  Protected p.i
  If pi3_up_mounted = 0 Or pi3_up_receiving <> 0 Or slot < 0 Or slot > 1 : ProcedureReturn pi3UpFail(-1) : EndIf
  p = @pi3_up_record[0] + slot * 512
  If pi3UpRecordValid(slot) = 0 Or PeekI(p + 8) <> generation : ProcedureReturn pi3UpFail(-15) : EndIf
  If PeekL(p + 64) <> #PI3_UPDATE_TRIED And PeekL(p + 64) <> #PI3_UPDATE_CONFIRMED : ProcedureReturn pi3UpFail(-15) : EndIf
  If pi3UpVerifySlot(slot) = 0 : ProcedureReturn pi3UpFail(-11) : EndIf
  If PeekL(p + 64) = #PI3_UPDATE_TRIED
    If pi3UpState(slot, #PI3_UPDATE_CONFIRMED) = 0 : ProcedureReturn 0 : EndIf
  EndIf
  pi3_up_active = slot
  pi3_up_generation = generation
  pi3_up_baseline = slot
  pi3_up_pending = -1
  pi3_up_error = 0
  ProcedureReturn 1
EndProcedure

; Fixed handoff page is above the downward stack and below staging. Loader
; writes it only after placement; updater consumes it only after mount/health.
Procedure.i Pi3UpdatePrepareHandoff(dtb.i)
  Protected n.i
  Protected p.i
  If pi3_up_mounted = 0 Or pi3_up_loaded < 4 Or dtb <> #PI3_UPDATE_LIMIT : ProcedureReturn pi3UpFail(-16) : EndIf
  p = #PI3_UPDATE_HANDOFF
  For n = 0 To 127 : PokeA(p + n, 0) : Next
  PokeI(p, $0031464F483350)
  PokeL(p + 8, 2)
  PokeL(p + 12, pi3_up_active)
  PokeI(p + 16, pi3_up_generation)
  PokeI(p + 24, dtb)
  PokeL(p + 32, PeekL(@pi3_up_record[0] + pi3_up_active * 512 + 64))
  PokeI(p + 40, PeekI(@pi3_up_record[0] + pi3_up_active * 512 + 16))
  For n = 0 To 31 : PokeA(p + 48 + n, PeekA(@pi3_up_record[0] + pi3_up_active * 512 + 32 + n)) : Next
  PokeL(p + 124, Crc32(p, 124))
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UpdateConfirmHandoff()
  Protected p.i
  Protected state.i
  p = #PI3_UPDATE_HANDOFF
  If pi3_up_mounted = 0 Or pi3_up_handoff_ready = 0 Or pi3UpHandoffMatches() = 0 : ProcedureReturn pi3UpFail(-16) : EndIf
  state = PeekL(p + 32)
  If state <> #PI3_UPDATE_TRIED And state <> #PI3_UPDATE_CONFIRMED : ProcedureReturn pi3UpFail(-16) : EndIf
  If state = #PI3_UPDATE_TRIED
    If pi3UpState(PeekL(p + 12), #PI3_UPDATE_CONFIRMED) = 0 : ProcedureReturn 0 : EndIf
  EndIf
  pi3_up_active = PeekL(p + 12)
  pi3_up_generation = PeekI(p + 16)
  pi3_up_baseline = pi3_up_active
  pi3_up_pending = -1
  pi3_up_handoff_ready = 0
  PokeI(p, 0)
  ProcedureReturn 1
EndProcedure
