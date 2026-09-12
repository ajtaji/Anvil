; Pi3 AArch64 A/B updater. Flat composition: FAT32 read layer, SHA256,
; Pi3SdReadBlock/Pi3SdWriteBlock. No FAT/directory/allocation writes.
; Provision five contiguous, non-overlapping files before first deployment:
; ANVILA.BIN, ANVILB.BIN (equal fixed capacity), P3CTRLA.BIN/P3CTRLB.BIN
; (512 bytes), KERNEL8.IMG (immutable loader). Transport is a separate owner.
#PI3_UPDATE_LOAD = $200000
#PI3_UPDATE_LIMIT = $1000000
#PI3_UPDATE_MAGIC = $42413350
#PI3_UPDATE_PENDING = 1
#PI3_UPDATE_TRIED = 2
#PI3_UPDATE_CONFIRMED = 3
#PI3_UPDATE_HEADER = 256 ; P3SLOT 128 + PMFBOOT v2 128
#PI3_UPDATE_HANDOFF = $1FF0000
Global Dim pi3_up_lba.i[5]
Global Dim pi3_up_span.i[5]
Global Dim pi3_up_size.i[5]
Global Dim pi3_up_record.l[256]
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

; The cold-loader ownership walk is iterative and entirely fixed-storage.  It
; admits ordinary nested boot trees (including overlays/) while bounding every
; corrupt-directory work multiplier.  This storage is in loader BSS; no heap or
; recursive stack growth is involved.
#PI3_UPDATE_DIR_DEPTH_MAX = 8
#PI3_UPDATE_DIR_COUNT_MAX = 256
#PI3_UPDATE_ENTRY_MAX = 16384
#PI3_UPDATE_DIR_CLUSTER_MAX = 8192
#PI3_UPDATE_DIR_SECTOR_MAX = 4096
#PI3_UPDATE_FOREIGN_HOP_MAX = 65536
Global Dim pi3_up_dir_first.i[#PI3_UPDATE_DIR_COUNT_MAX]
Global Dim pi3_up_dir_parent.i[#PI3_UPDATE_DIR_COUNT_MAX]
Global Dim pi3_up_dir_depth.i[#PI3_UPDATE_DIR_COUNT_MAX]
Global Dim pi3_up_dir_seen.i[#PI3_UPDATE_DIR_CLUSTER_MAX]
Global pi3_up_scan_entries.i
Global pi3_up_scan_dir_clusters.i
Global pi3_up_scan_dir_sectors.i
Global pi3_up_scan_hops.i

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
Procedure.i pi3UpCrc(p.i, bytes.i)
  Protected crc.i
  Protected n.i
  Protected bit.i
  crc = $FFFFFFFF
  For n = 0 To bytes - 1
    crc = crc ! (PeekA(p + n) & 255)
    For bit = 0 To 7
      If (crc & 1) <> 0
        crc = (crc >> 1) ! $EDB88320
      Else
        crc = crc >> 1
      EndIf
    Next
  Next
  ProcedureReturn crc ! $FFFFFFFF
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
  Protected cluster.i
  Protected count.i
  Protected n.i
  Protected nextCluster.i
  Protected clusterBytes.i
  If FatOpen(name) = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
  pi3_up_size[index] = FatSize()
  cluster = FatFirstCluster()
  clusterBytes = FatBytesPerCluster()
  If clusterBytes < 512 Or clusterBytes > 65536 Or (clusterBytes & (clusterBytes - 1)) <> 0 Or pi3_up_size[index] < 1 Or pi3_up_size[index] > #PI3_UPDATE_LIMIT - #PI3_UPDATE_LOAD
    FatClose() : ProcedureReturn pi3UpFail(-3)
  EndIf
  count = (pi3_up_size[index] + clusterBytes - 1) / clusterBytes
  pi3_up_span[index] = count * (clusterBytes / 512)
  If fat_ClusterValid(cluster) = 0 : FatClose() : ProcedureReturn pi3UpFail(-3) : EndIf
  pi3_up_lba[index] = fat_ClusterLba(cluster)
  For n = 1 To count
    nextCluster = fat_NextCluster(cluster)
    If n = count
      If nextCluster < $0FFFFFF8 Or nextCluster > $0FFFFFFF
        FatClose() : ProcedureReturn pi3UpFail(-3)
      EndIf
    Else
      If nextCluster <> cluster + 1 Or fat_ClusterValid(nextCluster) = 0
        FatClose() : ProcedureReturn pi3UpFail(-3)
      EndIf
      cluster = nextCluster
    EndIf
  Next
  FatClose()
  ProcedureReturn 1
EndProcedure

; P3SLOT v1 (128 bytes) wraps compiler-owned PMFBOOT v2 (128 bytes).
; Fixed metadata is admission policy, not a signature/authenticity claim.
Procedure.i pi3UpContainer(p.i, bytes.i)
  Protected n.i
  Protected pmf.i
  Protected imageBytes.i
  Protected bssBytes.i
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
  Sha256Of(pmf + 128, imageBytes, @pi3_up_digest[0])
  If pi3UpEqual(@pi3_up_digest[0], pmf + 64, 32) = 0 : ProcedureReturn 0 : EndIf
  Sha256Of(pmf, bytes - 128, @pi3_up_digest[0])
  ProcedureReturn pi3UpEqual(@pi3_up_digest[0], p + 40, 32)
EndProcedure

Procedure.i pi3UpRecordValid(slot.i)
  Protected p.i
  Protected length.i
  p = @pi3_up_record[0] + slot * 512
  If (PeekL(p) & $FFFFFFFF) <> #PI3_UPDATE_MAGIC Or PeekL(p + 4) <> 2 : ProcedureReturn 0 : EndIf
  If PeekI(p + 8) < 1 Or PeekI(p + 8) >= $7FFFFFFFFFFFFFFF : ProcedureReturn 0 : EndIf
  length = PeekI(p + 16)
  If length < #PI3_UPDATE_HEADER + 4 Or length > pi3_up_size[slot] Or length > pi3_up_stage_bytes : ProcedureReturn 0 : EndIf
  If PeekL(p + 24) <> slot Or PeekL(p + 28) <> #PI3_UPDATE_LOAD : ProcedureReturn 0 : EndIf
  If PeekL(p + 64) < #PI3_UPDATE_PENDING Or PeekL(p + 64) > #PI3_UPDATE_CONFIRMED : ProcedureReturn 0 : EndIf
  ProcedureReturn (PeekL(p + 508) & $FFFFFFFF) = pi3UpCrc(p, 508)
EndProcedure

Procedure.i pi3UpVerifySlot(slot.i)
  Protected p.i
  Protected bytes.i
  If pi3UpRecordValid(slot) = 0 : ProcedureReturn 0 : EndIf
  p = @pi3_up_record[0] + slot * 512
  bytes = PeekI(p + 16)
  If pi3UpHashSlot(slot, bytes, pi3_up_stage) = 0 : ProcedureReturn 0 : EndIf
  If pi3UpEqual(@pi3_up_digest[0], p + 32, 32) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn pi3UpContainer(pi3_up_stage, bytes)
EndProcedure

Procedure.i pi3UpHashSlot(slot.i, bytes.i, destination.i)
  Protected offset.i
  Protected take.i
  Protected n.i
  Protected buffer.i
  buffer = @pi3_up_sector[0]
  Sha256Begin()
  offset = 0
  While offset < bytes
    If Pi3SdReadBlock(pi3_up_lba[slot] + offset / 512, buffer) = 0 : ProcedureReturn 0 : EndIf
    take = bytes - offset
    If take > 512 : take = 512 : EndIf
    Sha256Update(buffer, take)
    If destination <> 0
      For n = 0 To take - 1 : PokeA(destination + offset + n, PeekA(buffer + n)) : Next
    EndIf
    offset = offset + take
  Wend
  Sha256End(@pi3_up_digest[0])
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

Procedure.i pi3UpOwnedOverlap(cluster.i)
  Protected lba.i
  Protected span.i
  Protected a.i
  If fat_ClusterValid(cluster) = 0 : ProcedureReturn 1 : EndIf
  lba = fat_ClusterLba(cluster)
  span = FatBytesPerCluster() / 512
  For a = 0 To 4
    If lba < pi3_up_lba[a] + pi3_up_span[a] And pi3_up_lba[a] < lba + span
      ProcedureReturn 1
    EndIf
  Next
  ProcedureReturn 0
EndProcedure

; Insert a directory-chain cluster into a fixed open-addressed set.  A repeat
; means a directory FAT loop or two directory objects sharing metadata.
Procedure.i pi3UpRememberDirCluster(cluster.i)
  Protected slot.i
  Protected probe.i
  slot = (cluster ! (cluster >> 11) ! (cluster >> 22)) & (#PI3_UPDATE_DIR_CLUSTER_MAX - 1)
  For probe = 0 To #PI3_UPDATE_DIR_CLUSTER_MAX - 1
    If pi3_up_dir_seen[slot] = 0
      pi3_up_dir_seen[slot] = cluster
      ProcedureReturn 1
    EndIf
    If pi3_up_dir_seen[slot] = cluster : ProcedureReturn 0 : EndIf
    slot = (slot + 1) & (#PI3_UPDATE_DIR_CLUSTER_MAX - 1)
  Next
  ProcedureReturn 0
EndProcedure

Procedure.i pi3UpQueueDir(first.i, parent.i, depth.i, count.i)
  Protected n.i
  If depth > #PI3_UPDATE_DIR_DEPTH_MAX Or count >= #PI3_UPDATE_DIR_COUNT_MAX Or fat_ClusterValid(first) = 0
    ProcedureReturn -1
  EndIf
  ; Starting-cluster uniqueness catches directory-entry graph cycles before a
  ; child can be queued repeatedly. Mid-chain merges are caught by the set.
  For n = 0 To count - 1
    If pi3_up_dir_first[n] = first : ProcedureReturn -1 : EndIf
  Next
  pi3_up_dir_first[count] = first
  pi3_up_dir_parent[count] = parent
  pi3_up_dir_depth[count] = depth
  ProcedureReturn count + 1
EndProcedure

Procedure.i pi3UpForeignFile(first.i, bytes.i)
  Protected cluster.i
  Protected nextCluster.i
  Protected expected.i
  Protected n.i
  Protected clusterBytes.i
  If bytes = 0 : ProcedureReturn first = 0 : EndIf
  If bytes < 0 Or fat_ClusterValid(first) = 0 : ProcedureReturn 0 : EndIf
  clusterBytes = FatBytesPerCluster()
  expected = (bytes + clusterBytes - 1) / clusterBytes
  If expected < 1 Or expected > FatClusterCount() Or pi3_up_scan_hops > #PI3_UPDATE_FOREIGN_HOP_MAX - expected
    ProcedureReturn 0
  EndIf
  cluster = first
  For n = 1 To expected
    If fat_ClusterValid(cluster) = 0 Or pi3UpOwnedOverlap(cluster) <> 0 : ProcedureReturn 0 : EndIf
    pi3_up_scan_hops = pi3_up_scan_hops + 1
    nextCluster = fat_NextCluster(cluster)
    If n = expected
      If nextCluster < $0FFFFFF8 Or nextCluster > $0FFFFFFF : ProcedureReturn 0 : EndIf
    Else
      If fat_ClusterValid(nextCluster) = 0 : ProcedureReturn 0 : EndIf
      cluster = nextCluster
    EndIf
  Next
  ProcedureReturn 1
EndProcedure

; Cold-loader-only, iterative tree ownership walk.  It validates exact regular
; file chain lengths, dot links, directory-chain uniqueness, and every cluster
; against the updater's five owned extents.  Any bound/refusal returns before a
; write window is enabled, so corrupt media remains read-only.
Procedure.i pi3UpForeignFiles()
  Protected queueCount.i
  Protected queueAt.i
  Protected first.i
  Protected parent.i
  Protected depth.i
  Protected cluster.i
  Protected nextCluster.i
  Protected sector.i
  Protected entry.i
  Protected p.i
  Protected lead.i
  Protected attr.i
  Protected child.i
  Protected bytes.i
  Protected owned.i
  Protected ownedSeen.i
  Protected dotSeen.i
  Protected ended.i
  Protected n.i
  Protected clusterLimit.i
  Protected sectorsPerCluster.i

  For n = 0 To #PI3_UPDATE_DIR_CLUSTER_MAX - 1 : pi3_up_dir_seen[n] = 0 : Next
  pi3_up_scan_entries = 0
  pi3_up_scan_dir_clusters = 0
  pi3_up_scan_dir_sectors = 0
  pi3_up_scan_hops = 0
  clusterLimit = FatClusterCount()
  sectorsPerCluster = FatBytesPerCluster() / 512
  If clusterLimit < 1 Or sectorsPerCluster < 1 : ProcedureReturn 0 : EndIf
  queueCount = pi3UpQueueDir(FatRootCluster(), FatRootCluster(), 0, 0)
  If queueCount < 0 : ProcedureReturn 0 : EndIf

  queueAt = 0
  While queueAt < queueCount
    first = pi3_up_dir_first[queueAt]
    parent = pi3_up_dir_parent[queueAt]
    depth = pi3_up_dir_depth[queueAt]
    queueAt = queueAt + 1
    cluster = first
    dotSeen = 0
    ended = 0
    While 1
      If fat_ClusterValid(cluster) = 0 Or pi3UpOwnedOverlap(cluster) <> 0 : ProcedureReturn 0 : EndIf
      If pi3_up_scan_dir_clusters >= #PI3_UPDATE_DIR_CLUSTER_MAX Or pi3_up_scan_dir_clusters >= clusterLimit : ProcedureReturn 0 : EndIf
      If pi3_up_scan_hops >= #PI3_UPDATE_FOREIGN_HOP_MAX : ProcedureReturn 0 : EndIf
      If pi3UpRememberDirCluster(cluster) = 0 : ProcedureReturn 0 : EndIf
      pi3_up_scan_dir_clusters = pi3_up_scan_dir_clusters + 1
      pi3_up_scan_hops = pi3_up_scan_hops + 1

      If ended = 0
        For sector = 0 To sectorsPerCluster - 1
          If pi3_up_scan_dir_sectors >= #PI3_UPDATE_DIR_SECTOR_MAX : ProcedureReturn 0 : EndIf
          If FatReadClusterSector(cluster, sector, @pi3_up_sector[0]) = 0 : ProcedureReturn 0 : EndIf
          pi3_up_scan_dir_sectors = pi3_up_scan_dir_sectors + 1
          For entry = 0 To 15
            p = @pi3_up_sector[0] + entry * 32
            lead = PeekA(p) & 255
            If lead = 0 : ended = 1 : Break : EndIf
            If pi3_up_scan_entries >= #PI3_UPDATE_ENTRY_MAX : ProcedureReturn 0 : EndIf
            pi3_up_scan_entries = pi3_up_scan_entries + 1
            If lead <> $E5
              attr = PeekA(p + 11) & 255
              If attr <> $0F And (attr & $08) = 0
                child = (fat_U16(p, 20) << 16) | fat_U16(p, 26)
                bytes = fat_U32(p, 28)
                If pi3UpEqual(p, ".          ", 11) <> 0
                  If depth = 0 Or (dotSeen & 1) <> 0 Or (attr & $10) = 0 Or bytes <> 0 Or child <> first : ProcedureReturn 0 : EndIf
                  dotSeen = dotSeen | 1
                ElseIf pi3UpEqual(p, "..         ", 11) <> 0
                  If depth = 0 Or (dotSeen & 2) <> 0 Or (attr & $10) = 0 Or bytes <> 0 : ProcedureReturn 0 : EndIf
                  If child <> parent And Not (parent = FatRootCluster() And child = 0) : ProcedureReturn 0 : EndIf
                  dotSeen = dotSeen | 2
                Else
                  owned = -1
                  If depth = 0 : owned = pi3UpOwnedName(p) : EndIf
                  If owned >= 0
                    If (ownedSeen & (1 << owned)) <> 0 Or (attr & $10) <> 0 Or bytes <> pi3_up_size[owned]
                      ProcedureReturn 0
                    EndIf
                    If fat_ClusterValid(child) = 0 Or fat_ClusterLba(child) <> pi3_up_lba[owned] : ProcedureReturn 0 : EndIf
                    ownedSeen = ownedSeen | (1 << owned)
                  ElseIf (attr & $10) <> 0
                    If bytes <> 0 : ProcedureReturn 0 : EndIf
                    queueCount = pi3UpQueueDir(child, first, depth + 1, queueCount)
                    If queueCount < 0 : ProcedureReturn 0 : EndIf
                  Else
                    If pi3UpForeignFile(child, bytes) = 0 : ProcedureReturn 0 : EndIf
                  EndIf
                EndIf
              EndIf
            EndIf
          Next
          If ended <> 0 : Break : EndIf
        Next
      EndIf

      nextCluster = fat_NextCluster(cluster)
      If nextCluster >= $0FFFFFF8 And nextCluster <= $0FFFFFFF : Break : EndIf
      If fat_ClusterValid(nextCluster) = 0 : ProcedureReturn 0 : EndIf
      cluster = nextCluster
    Wend
    If depth > 0 And dotSeen <> 3 : ProcedureReturn 0 : EndIf
  Wend
  ProcedureReturn ownedSeen = 31
EndProcedure

Procedure.i pi3UpHandoffHeader()
  Protected p.i
  p = #PI3_UPDATE_HANDOFF
  If PeekI(p) <> $0031464F483350 Or PeekL(p + 8) <> 2 : ProcedureReturn 0 : EndIf
  If PeekL(p + 12) < 0 Or PeekL(p + 12) > 1 Or PeekI(p + 16) < 1 : ProcedureReturn 0 : EndIf
  If PeekI(p + 24) <> #PI3_UPDATE_LIMIT : ProcedureReturn 0 : EndIf
  If PeekL(p + 32) <> #PI3_UPDATE_TRIED And PeekL(p + 32) <> #PI3_UPDATE_CONFIRMED : ProcedureReturn 0 : EndIf
  ProcedureReturn (PeekL(p + 124) & $FFFFFFFF) = pi3UpCrc(p, 124)
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
  Protected rootCluster.i
  Protected rootLba.i
  Protected rootNext.i
  Protected steps.i
  If pi3_up_stage = 0 Or pi3_up_receiving <> 0 : ProcedureReturn pi3UpFail(-1) : EndIf
  pi3_up_mounted = 0
  pi3_up_active = -1
  pi3_up_generation = 0
  pi3_up_max_generation = 0
  pi3_up_pending = -1
  pi3_up_baseline = -1
  pi3_up_handoff_ready = 0
  If handoff <> 0
    If pi3UpHandoffHeader() = 0 : ProcedureReturn pi3UpFail(-16) : EndIf
  EndIf
  FatSetBlockReader(@Pi3SdReadBlock)
  FatSetBlockWriter(0)
  If FatMount(1) = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
  If pi3UpMap(0, "ANVILA.BIN") = 0 Or pi3UpMap(1, "ANVILB.BIN") = 0 Or pi3UpMap(2, "P3CTRLA.BIN") = 0 Or pi3UpMap(3, "P3CTRLB.BIN") = 0 Or pi3UpMap(4, "KERNEL8.IMG") = 0 : ProcedureReturn 0 : EndIf
  If pi3_up_size[0] <> pi3_up_size[1] Or (pi3_up_size[0] & 511) <> 0 Or pi3_up_size[2] <> 512 Or pi3_up_size[3] <> 512 Or pi3_up_size[4] > $180000
    ProcedureReturn pi3UpFail(-3)
  EndIf
  For a = 0 To 4
    If pi3_up_lba[a] < FatDataLba() Or pi3_up_lba[a] > FatDataEnd() - pi3_up_span[a] : ProcedureReturn pi3UpFail(-3) : EndIf
    For b = a + 1 To 4
      If pi3_up_lba[a] < pi3_up_lba[b] + pi3_up_span[b] And pi3_up_lba[b] < pi3_up_lba[a] + pi3_up_span[a] : ProcedureReturn pi3UpFail(-3) : EndIf
    Next
  Next
  ; The root directory also lives in the data area. Protect every cluster in
  ; its chain; a corrupt slot entry must never alias directory metadata.
  rootCluster = FatRootCluster()
  For steps = 0 To 4095
    If fat_ClusterValid(rootCluster) = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
    rootLba = fat_ClusterLba(rootCluster)
    For a = 0 To 4
      If rootLba < pi3_up_lba[a] + pi3_up_span[a] And pi3_up_lba[a] < rootLba + FatBytesPerCluster() / 512 : ProcedureReturn pi3UpFail(-3) : EndIf
    Next
    rootNext = fat_NextCluster(rootCluster)
    If rootNext >= $0FFFFFF8 And rootNext <= $0FFFFFFF : Break : EndIf
    rootCluster = rootNext
  Next
  If steps > 4095 : ProcedureReturn pi3UpFail(-3) : EndIf
  ; The immutable loader performs the complete bounded tree walk.  The running
  ; candidate's 15-second watchdog path revalidates the exact mapped extents and
  ; trusted loader handoff, without repeating an unbounded-by-time media scan.
  If handoff = 0
    If pi3UpForeignFiles() = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
  EndIf
  ; Read failure is not a blank record. Refuse mutation of an unknown medium.
  If Pi3SdReadBlock(pi3_up_lba[2], @pi3_up_record[0]) = 0 Or Pi3SdReadBlock(pi3_up_lba[3], @pi3_up_record[128]) = 0 : ProcedureReturn pi3UpFail(-4) : EndIf
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
    If Pi3SdSetWriteWindow(FatDataLba(), FatDataEnd() - FatDataLba()) = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
    pi3_up_handoff_ready = 1 : pi3_up_mounted = 1 : pi3_up_error = 0
    ProcedureReturn 1
  EndIf
  ; Updates always preserve a confirmed baseline. A pending candidate is a
  ; separate boot choice; a tried but unconfirmed candidate is never retried.
  For a = 0 To 1
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
  ; Initial provisioning must install one valid fallback; no blind first write.
  If pi3_up_active < 0 : ProcedureReturn pi3UpFail(-6) : EndIf
  pi3_up_baseline = pi3_up_active
  ; Block layer independently caps this data-only fence at card capacity.
  ; Even an accidental write caller cannot reach MBR/FAT sectors outside
  ; this data area; this updater additionally excludes all directory/other files.
  If Pi3SdSetWriteWindow(FatDataLba(), FatDataEnd() - FatDataLba()) = 0 : ProcedureReturn pi3UpFail(-3) : EndIf
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

Procedure.i Pi3UpdateBegin(bytes.i, expectedSha.i)
  Protected n.i
  If pi3_up_mounted = 0 Or pi3_up_receiving <> 0 : ProcedureReturn pi3UpFail(-1) : EndIf
  If bytes < #PI3_UPDATE_HEADER + 4 Or bytes > pi3_up_size[0] Or bytes > pi3_up_stage_bytes Or pi3UpRam(expectedSha, 32) = 0 : ProcedureReturn pi3UpFail(-7) : EndIf
  If pi3_up_max_generation >= $7FFFFFFFFFFFFFFE : ProcedureReturn pi3UpFail(-7) : EndIf
  If PeekL(@pi3_up_record[0] + pi3_up_active * 512 + 64) <> #PI3_UPDATE_CONFIRMED : ProcedureReturn pi3UpFail(-7) : EndIf
  For n = 0 To 31 : pi3_up_expected[n] = PeekA(expectedSha + n) : Next
  pi3_up_length = bytes
  pi3_up_received = 0
  pi3_up_receiving = 1
  pi3_up_error = 0
  ProcedureReturn 1
EndProcedure

Procedure.i Pi3UpdateChunk(offset.i, source.i, bytes.i)
  Protected n.i
  If pi3_up_receiving = 0 : ProcedureReturn pi3UpFail(-1) : EndIf
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

Procedure Pi3UpdateAbort()
  pi3_up_receiving = 0
  pi3_up_received = 0
  pi3_up_length = 0
EndProcedure

Procedure.i Pi3UpdateCommit()
  Protected target.i
  Protected offset.i
  Protected n.i
  Protected take.i
  Protected p.i
  If pi3_up_mounted = 0 Or pi3_up_receiving = 0 Or pi3_up_received <> pi3_up_length : ProcedureReturn pi3UpFail(-1) : EndIf
  Sha256Of(pi3_up_stage, pi3_up_length, @pi3_up_digest[0])
  If pi3UpEqual(@pi3_up_digest[0], @pi3_up_expected[0], 32) = 0 : ProcedureReturn pi3UpFail(-9) : EndIf
  If pi3UpContainer(pi3_up_stage, pi3_up_length) = 0 : ProcedureReturn pi3UpFail(-13) : EndIf
  target = 1 - pi3_up_active
  ; Once disk mutation starts, any error forces remount before another attempt.
  pi3_up_mounted = 0
  pi3_up_receiving = 0
  offset = 0
  While offset < pi3_up_length
    take = pi3_up_length - offset
    If take > 512 : take = 512 : EndIf
    For n = 0 To 511 : PokeA(@pi3_up_sector[0] + n, 0) : Next
    For n = 0 To take - 1 : PokeA(@pi3_up_sector[0] + n, PeekA(pi3_up_stage + offset + n)) : Next
    If Pi3SdWriteBlock(pi3_up_lba[target] + offset / 512, @pi3_up_sector[0]) = 0 : ProcedureReturn pi3UpFail(-10) : EndIf
    offset = offset + take
  Wend
  If pi3UpHashSlot(target, pi3_up_length, 0) = 0 : ProcedureReturn pi3UpFail(-11) : EndIf
  If pi3UpEqual(@pi3_up_digest[0], @pi3_up_expected[0], 32) = 0 : ProcedureReturn pi3UpFail(-11) : EndIf
  p = @pi3_up_record[0] + target * 512
  For n = 0 To 511 : PokeA(p + n, 0) : Next
  PokeL(p, #PI3_UPDATE_MAGIC)
  PokeL(p + 4, 2)
  PokeI(p + 8, pi3_up_max_generation + 1)
  PokeI(p + 16, pi3_up_length)
  PokeL(p + 24, target)
  PokeL(p + 28, #PI3_UPDATE_LOAD)
  For n = 0 To 31 : PokeA(p + 32 + n, pi3_up_expected[n]) : Next
  PokeL(p + 64, #PI3_UPDATE_PENDING)
  PokeL(p + 508, pi3UpCrc(p, 508))
  If Pi3SdWriteBlock(pi3_up_lba[target + 2], p) = 0 : ProcedureReturn pi3UpFail(-12) : EndIf
  If Pi3SdReadBlock(pi3_up_lba[target + 2], @pi3_up_sector[0]) = 0 Or pi3UpEqual(p, @pi3_up_sector[0], 512) = 0 : ProcedureReturn pi3UpFail(-12) : EndIf
  ; Old slot/control record remain intact. No reset, FAT update or deletion.
  pi3_up_max_generation = pi3_up_max_generation + 1
  pi3_up_pending = target
  pi3_up_mounted = 1
  pi3_up_error = 0
  ProcedureReturn 1
EndProcedure

; The confirmed other record remains untouched through every state write.
Procedure.i pi3UpState(slot.i, state.i)
  Protected p.i
  p = @pi3_up_record[0] + slot * 512
  PokeL(p + 64, state)
  PokeL(p + 508, pi3UpCrc(p, 508))
  If Pi3SdWriteBlock(pi3_up_lba[slot + 2], p) = 0
    pi3_up_mounted = 0 : ProcedureReturn pi3UpFail(-14)
  EndIf
  If Pi3SdReadBlock(pi3_up_lba[slot + 2], @pi3_up_sector[0]) = 0 Or pi3UpEqual(p, @pi3_up_sector[0], 512) = 0
    pi3_up_mounted = 0 : ProcedureReturn pi3UpFail(-14)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i pi3UpPlace(slot.i)
  Protected n.i
  Protected bytes.i
  Protected p.i
  If pi3UpVerifySlot(slot) = 0 : ProcedureReturn pi3UpFail(-11) : EndIf
  p = @pi3_up_record[0] + slot * 512
  bytes = PeekI(p + 16) - #PI3_UPDATE_HEADER
  For n = 0 To bytes - 1
    PokeA(#PI3_UPDATE_LOAD + n, PeekA(pi3_up_stage + #PI3_UPDATE_HEADER + n))
  Next
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
    If PeekI(p + 8) > pi3_up_generation And pi3UpVerifySlot(slot) <> 0
      ; Commit TRIED before copying/branching. A lost or torn acknowledgement
      ; refuses this boot; next boot still has the confirmed fallback.
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
  PokeL(p + 124, pi3UpCrc(p, 124))
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
