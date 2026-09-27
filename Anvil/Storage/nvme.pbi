; ======================================================================
; nvme.pbi - an NVMe controller behind any PCIe root complex, as the
; block-range seam the shared filesystems read and write through.
; ----------------------------------------------------------------------
; SHARED (Anvil/Storage). No board, no chip, no filesystem code: the board
; brings its PCIe link up, places the endpoint's BAR0, and hands this file
;
;     NvmeAttach(barCpu, arenaCpu, arenaBytes, dmaOffset)
;
;   barCpu      where the CPU sees BAR0 (the controller registers)
;   arenaCpu    ARM physical memory this file may use for queues, identify
;               data, one PRP list and the transfer bounce buffer; 4 KiB
;               aligned, #NVME_ARENA_BYTES long, reachable by the endpoint
;   dmaOffset   what the root complex adds to an ARM physical address on
;               the way in (bus = physical + dmaOffset)
;
; and optionally NvmeSetCacheOps(@clean, @invalidate) - two procedures
; (addr, len) the board supplies when the arena is cacheable; with none
; installed the arena must be mapped non-cacheable. Then:
;
;     FsSetRangeReader(@NvmeReadBlocks)
;     FsSetRangeWriter(@NvmeWriteBlocks)
;     FsSetBlockFlusher(@NvmeFlush)
;
; and FAT32 / exFAT run unchanged (rule 30: this file holds no filesystem
; code). The seam moves 512-byte blocks; a namespace formatted with larger
; logical blocks (up to 4096) is served through the bounce buffer with
; read-modify-write at the edges.
;
; SILICON OWED. Desk gate: tools/a64/a64_nvme_pi5_check.py, which runs this
; file on the A64 interpreter against a modelled controller.
;
; ======================================================================
; EVERY NUMBER, AND WHERE IT IS FROM (raspberrypi/linux 7e030b60, vault
; "Raspberry Pi 5/Sources"):
;   include/linux/nvme.h
;     registers 132-162: CAP 0, VS 8, INTMS $C, CC $14, CSTS $1C, AQA $24,
;       ASQ $28, ACQ $30, DBS $1000
;     CAP 165-171: MQES 15:0, TO 31:24 (500 ms units), DSTRD 35:32,
;       CSS 44:37 (bit 0 NVM, 269), MPSMIN 51:48
;     CC 207-244: EN bit 0, CSS 6:4 (NVM 0), MPS 10:7 (4 KiB = 0), AMS
;       13:11 (RR 0), SHN 15:14, IOSQES 19:16 = 6, IOCQES 23:20 = 4 (199-200)
;     CSTS 253-260: RDY bit 0, CFS bit 1
;     opcodes: admin 1296-1301 (create SQ 1, create CQ 5, identify 6),
;       I/O 946-948 (flush 0, write 1, read 2); CNS 554-555 (NS 0, CTRL 1)
;     the 64-byte command: struct nvme_common_command 1071-1087 (opcode 0,
;       command_id 2, nsid 4, dptr.prp1 24, prp2 32, cdw10 40 ...);
;       nvme_rw_command 1089-1105 (slba 40, length 48 zero-based);
;       nvme_identify 1443-1455 (cns 40); nvme_create_cq/sq 1482-1507 (qid 40,
;       qsize 42 zero-based, flags 44, cqid 46); flags 1358-1362
;       (PHYS_CONTIG 1; IRQ_ENABLED 2 is NOT set - this file polls)
;     the 16-byte completion 2236-2247: result 0, sq_head 8, sq_id 10,
;       command_id 12, status 14 (bit 0 phase, 15:1 status)
;     nvme_id_ctrl 309-: mdts byte 77, nn at 516; nvme_id_ns 434-: nsze 0,
;       flbas 26 (low 4 bits, 595), lbaf[] at 128, 4 bytes each (ds byte 2)
;   drivers/nvme/host/pci.c
;     CAP read lo then hi (3078), doorbells at BAR + 4096 (3083), SQ tail
;     doorbell of qid at dbs[qid * 2 * stride], CQ head at the next
;     (1932), stride = 1 << DSTRD in 32-bit units (3082)
;   drivers/nvme/host/core.c
;     disable: wait RDY = 0 (2696-2697); enable: wait RDY = 1 for
;     (CAP.TO + 1) / 2 seconds (2746-2776)
; ======================================================================

#NVME_REG_CAP   = $00
#NVME_REG_VS    = $08
#NVME_REG_INTMS = $0C
#NVME_REG_CC    = $14
#NVME_REG_CSTS  = $1C
#NVME_REG_AQA   = $24
#NVME_REG_ASQ   = $28
#NVME_REG_ACQ   = $30
#NVME_REG_DBS   = $1000

#NVME_CC_ENABLE = $1
#NVME_CC_IOSQES = 6 << 16
#NVME_CC_IOCQES = 4 << 20
#NVME_CSTS_RDY  = $1
#NVME_CSTS_CFS  = $2

#NVME_ADM_CREATE_SQ = $01
#NVME_ADM_CREATE_CQ = $05
#NVME_ADM_IDENTIFY  = $06
#NVME_IO_FLUSH = $00
#NVME_IO_WRITE = $01
#NVME_IO_READ  = $02
#NVME_CNS_NS   = $00
#NVME_CNS_CTRL = $01
#NVME_Q_PHYS_CONTIG = $1

; The arena, all offsets 4 KiB aligned.
#NVME_PAGE       = 4096
#NVME_ADMIN_SQ   = $0000
#NVME_ADMIN_CQ   = $1000
#NVME_IO_SQ      = $2000
#NVME_IO_CQ      = $3000
#NVME_IDENTIFY   = $4000
#NVME_PRP_LIST   = $5000
#NVME_BOUNCE     = $6000
#NVME_BOUNCE_PAGES = 16
#NVME_ARENA_BYTES  = $16000
#NVME_QDEPTH       = 16

#NVME_CMD_TIMEOUT_MS = 5000

#NVME_ERR_NONE         = 0
#NVME_ERR_NOT_ATTACHED = 1
#NVME_ERR_ARENA        = 2
#NVME_ERR_NO_CONTROLLER = 3
#NVME_ERR_PAGE_SIZE    = 4
#NVME_ERR_NO_NVM_CSS   = 5
#NVME_ERR_RESET_TMO    = 6
#NVME_ERR_ENABLE_TMO   = 7
#NVME_ERR_FATAL        = 8
#NVME_ERR_CMD_TMO      = 9
#NVME_ERR_CMD_STATUS   = 10
#NVME_ERR_LBA_SIZE     = 11
#NVME_ERR_RANGE        = 12
#NVME_ERR_NO_NAMESPACE = 13
#NVME_ERR_QUEUE        = 14
#NVME_ERR_CID          = 15
#NVME_ERR_NO_TIMER     = 16

Global nvme_bar.i
Global nvme_arena.i
Global nvme_dmaOff.i
Global nvme_ready.i
Global nvme_err.i
Global nvme_lastStatus.i
Global nvme_stride.i            ; doorbell stride in bytes
Global nvme_toMs.i              ; CAP.TO in milliseconds
Global nvme_mqes.i
Global nvme_cid.i
Global nvme_aTail.i
Global nvme_aHead.i
Global nvme_aPhase.i
Global nvme_ioTail.i
Global nvme_ioHead.i
Global nvme_ioPhase.i
Global nvme_lbaShift.i          ; log2 of the namespace's logical block
Global nvme_nsBlocks.i          ; namespace size in its own logical blocks
Global nvme_maxBytes.i          ; per-command transfer ceiling
Global nvme_mdts.i
Global nvme_nn.i
Global nvme_vid.i
Global *nvme_clean
Global *nvme_inval

; Time comes from the HAL's declared seam, Ticks() / TickHz() (Anvil/Hal/
; hal.pbi, THE TIME): this file reads no counter of its own.
Procedure.i nvme_Ticks()
  ProcedureReturn Ticks()
EndProcedure

Procedure.i nvme_TickHz()
  ProcedureReturn TickHz()
EndProcedure

Procedure nvme_Barrier()
  ASM
    dsb sy
    isb
  EndASM
EndProcedure

Procedure.i nvme_Fail(code.i)
  nvme_err = code
  ProcedureReturn 0
EndProcedure

Procedure.i nvme_Rd(off.i)
  Define v.i
  nvme_Barrier()
  v = PeekN(nvme_bar + off)
  nvme_Barrier()
  ProcedureReturn v
EndProcedure

Procedure nvme_Wr(off.i, v.i)
  nvme_Barrier()
  PokeL(nvme_bar + off, v & $FFFFFFFF)
  nvme_Barrier()
EndProcedure

; Low word then high word, as lo_hi_writeq does.
Procedure nvme_Wr64(off.i, v.i)
  nvme_Wr(off, v & $FFFFFFFF)
  nvme_Wr(off + 4, (v >> 32) & $FFFFFFFF)
EndProcedure

Procedure nvme_CacheClean(addr.i, len.i)
  If *nvme_clean <> 0
    nvme_clean(addr, len)
  EndIf
  nvme_Barrier()
EndProcedure

Procedure nvme_CacheInval(addr.i, len.i)
  If *nvme_inval <> 0
    nvme_inval(addr, len)
  EndIf
  nvme_Barrier()
EndProcedure

Procedure.i nvme_Bus(cpuAddr.i)
  ProcedureReturn cpuAddr + nvme_dmaOff
EndProcedure

; Copy bytes; 32 bits at a time when both ends and the length allow it
; (the seam's buffers may sit at any address).
Procedure nvme_Copy(src.i, dst.i, bytes.i)
  Define i.i
  i = 0
  If ((src | dst | bytes) & 3) = 0
    While i < bytes
      PokeL(dst + i, PeekN(src + i))
      i = i + 4
    Wend
  Else
    While i < bytes
      PokeB(dst + i, PeekA(src + i))
      i = i + 1
    Wend
  EndIf
EndProcedure

; ----------------------------------------------------------------------
;  NvmeSetCacheOps(clean, invalidate) - optional; see the header.
; ----------------------------------------------------------------------
Procedure NvmeSetCacheOps(clean.i, invalidate.i)
  *nvme_clean = clean
  *nvme_inval = invalidate
EndProcedure

; Wait until (CSTS & mask) = want, CFS aborting, for ms milliseconds.
Procedure.i nvme_WaitCsts(mask.i, want.i, ms.i)
  Define t0.i
  Define budget.i
  Define s.i
  budget = (nvme_TickHz() / 1000) * ms
  t0 = nvme_Ticks()
  Repeat
    s = nvme_Rd(#NVME_REG_CSTS)
    If s = $FFFFFFFF
      ProcedureReturn nvme_Fail(#NVME_ERR_NO_CONTROLLER)
    EndIf
    If (s & #NVME_CSTS_CFS) <> 0
      ProcedureReturn nvme_Fail(#NVME_ERR_FATAL)
    EndIf
    If (s & mask) = want
      ProcedureReturn 1
    EndIf
    If (nvme_Ticks() - t0) > budget
      ProcedureReturn 0
    EndIf
  ForEver
EndProcedure

; ----------------------------------------------------------------------
;  The command path. Admin queue 0 and I/O queue 1, each one SQ and one
;  CQ of #NVME_QDEPTH entries, polled on the phase bit.
; ----------------------------------------------------------------------
Procedure nvme_ClearSqe(sqe.i)
  Define i.i
  i = 0
  While i < 64
    PokeL(sqe + i, 0)
    i = i + 4
  Wend
EndProcedure

; Returns the SQE address to fill for queue qid (0 admin, 1 I/O).
Procedure.i nvme_NextSqe(qid.i)
  Define sqe.i
  If qid = 0
    sqe = nvme_arena + #NVME_ADMIN_SQ + (nvme_aTail * 64)
  Else
    sqe = nvme_arena + #NVME_IO_SQ + (nvme_ioTail * 64)
  EndIf
  nvme_ClearSqe(sqe)
  nvme_cid = (nvme_cid + 1) & $FFFF
  PokeB(sqe + 2, nvme_cid & $FF)
  PokeB(sqe + 3, (nvme_cid >> 8) & $FF)
  ProcedureReturn sqe
EndProcedure

; Ring the SQ tail, poll the CQ entry at head for the expected phase,
; check its command id and status, advance and ring the CQ head.
Procedure.i nvme_Run(qid.i, sqe.i)
  Define cq.i
  Define head.i
  Define phase.i
  Define cqe.i
  Define st.i
  Define cid.i
  Define t0.i
  Define budget.i
  Define s.i
  nvme_CacheClean(sqe, 64)
  If qid = 0
    nvme_aTail = (nvme_aTail + 1) % #NVME_QDEPTH
    nvme_Wr(#NVME_REG_DBS, nvme_aTail)
    cq = nvme_arena + #NVME_ADMIN_CQ
    head = nvme_aHead
    phase = nvme_aPhase
  Else
    nvme_ioTail = (nvme_ioTail + 1) % #NVME_QDEPTH
    nvme_Wr(#NVME_REG_DBS + (2 * nvme_stride), nvme_ioTail)
    cq = nvme_arena + #NVME_IO_CQ
    head = nvme_ioHead
    phase = nvme_ioPhase
  EndIf
  cqe = cq + (head * 16)
  budget = (nvme_TickHz() / 1000) * #NVME_CMD_TIMEOUT_MS
  t0 = nvme_Ticks()
  Repeat
    nvme_CacheInval(cqe, 16)
    st = PeekA(cqe + 14) | (PeekA(cqe + 15) << 8)
    If (st & 1) = phase
      Break
    EndIf
    s = nvme_Rd(#NVME_REG_CSTS)
    If (s & #NVME_CSTS_CFS) <> 0 Or s = $FFFFFFFF
      nvme_ready = 0
      ProcedureReturn nvme_Fail(#NVME_ERR_FATAL)
    EndIf
    If (nvme_Ticks() - t0) > budget
      ProcedureReturn nvme_Fail(#NVME_ERR_CMD_TMO)
    EndIf
  ForEver
  cid = PeekA(cqe + 12) | (PeekA(cqe + 13) << 8)
  head = head + 1
  If head >= #NVME_QDEPTH
    head = 0
    phase = phase ! 1
  EndIf
  If qid = 0
    nvme_aHead = head
    nvme_aPhase = phase
    nvme_Wr(#NVME_REG_DBS + nvme_stride, head)
  Else
    nvme_ioHead = head
    nvme_ioPhase = phase
    nvme_Wr(#NVME_REG_DBS + (3 * nvme_stride), head)
  EndIf
  nvme_lastStatus = (st >> 1) & $7FFF
  If cid <> nvme_cid
    ProcedureReturn nvme_Fail(#NVME_ERR_CID)
  EndIf
  If nvme_lastStatus <> 0
    ProcedureReturn nvme_Fail(#NVME_ERR_CMD_STATUS)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure nvme_PutQ(addr.i, v.i)
  PokeL(addr, v & $FFFFFFFF)
  PokeL(addr + 4, (v >> 32) & $FFFFFFFF)
EndProcedure

Procedure.i nvme_Identify(cns.i, nsid.i)
  Define sqe.i
  sqe = nvme_NextSqe(0)
  PokeB(sqe, #NVME_ADM_IDENTIFY)
  PokeL(sqe + 4, nsid)
  nvme_PutQ(sqe + 24, nvme_Bus(nvme_arena + #NVME_IDENTIFY))
  PokeL(sqe + 40, cns)
  nvme_CacheInval(nvme_arena + #NVME_IDENTIFY, #NVME_PAGE)
  If nvme_Run(0, sqe) = 0
    ProcedureReturn 0
  EndIf
  nvme_CacheInval(nvme_arena + #NVME_IDENTIFY, #NVME_PAGE)
  ProcedureReturn 1
EndProcedure

; Create I/O CQ 1 then I/O SQ 1 on it, physically contiguous, no IRQ.
Procedure.i nvme_CreateIoQueues()
  Define sqe.i
  sqe = nvme_NextSqe(0)
  PokeB(sqe, #NVME_ADM_CREATE_CQ)
  nvme_PutQ(sqe + 24, nvme_Bus(nvme_arena + #NVME_IO_CQ))
  PokeL(sqe + 40, ((#NVME_QDEPTH - 1) << 16) | 1)
  PokeL(sqe + 44, #NVME_Q_PHYS_CONTIG)
  If nvme_Run(0, sqe) = 0
    ProcedureReturn 0
  EndIf
  sqe = nvme_NextSqe(0)
  PokeB(sqe, #NVME_ADM_CREATE_SQ)
  nvme_PutQ(sqe + 24, nvme_Bus(nvme_arena + #NVME_IO_SQ))
  PokeL(sqe + 40, ((#NVME_QDEPTH - 1) << 16) | 1)
  PokeL(sqe + 44, (1 << 16) | #NVME_Q_PHYS_CONTIG)
  ProcedureReturn nvme_Run(0, sqe)
EndProcedure

Procedure nvme_ZeroPages(addr.i, pages.i)
  Define i.i
  i = 0
  While i < (pages * #NVME_PAGE)
    PokeL(addr + i, 0)
    i = i + 4
  Wend
  nvme_CacheClean(addr, pages * #NVME_PAGE)
EndProcedure

; ----------------------------------------------------------------------
;  NvmeAttach - reset, admin queues, enable, identify, I/O queues.
; ----------------------------------------------------------------------
Procedure.i NvmeAttach(barCpu.i, arenaCpu.i, arenaBytes.i, dmaOffset.i)
  Define caplo.i
  Define caphi.i
  Define mpsmin.i
  Define css.i
  Define ds.i
  Define fmt.i
  nvme_ready = 0
  nvme_err = #NVME_ERR_NONE
  If nvme_TickHz() <= 0
    ProcedureReturn nvme_Fail(#NVME_ERR_NO_TIMER)
  EndIf
  If barCpu <= 0 Or arenaCpu <= 0 Or (arenaCpu & (#NVME_PAGE - 1)) <> 0 Or arenaBytes < #NVME_ARENA_BYTES
    ProcedureReturn nvme_Fail(#NVME_ERR_ARENA)
  EndIf
  nvme_bar = barCpu
  nvme_arena = arenaCpu
  nvme_dmaOff = dmaOffset
  caplo = nvme_Rd(#NVME_REG_CAP)
  caphi = nvme_Rd(#NVME_REG_CAP + 4)
  If (caplo = $FFFFFFFF And caphi = $FFFFFFFF) Or (caplo = 0 And caphi = 0)
    ProcedureReturn nvme_Fail(#NVME_ERR_NO_CONTROLLER)
  EndIf
  nvme_mqes = caplo & $FFFF
  nvme_toMs = (((caplo >> 24) & $FF) + 1) * 500
  nvme_stride = 4 << (caphi & $F)
  css = (caphi >> 5) & $FF
  mpsmin = (caphi >> 16) & $F
  If mpsmin <> 0
    ProcedureReturn nvme_Fail(#NVME_ERR_PAGE_SIZE)
  EndIf
  If (css & 1) = 0
    ProcedureReturn nvme_Fail(#NVME_ERR_NO_NVM_CSS)
  EndIf
  If nvme_mqes < (#NVME_QDEPTH - 1)
    ProcedureReturn nvme_Fail(#NVME_ERR_QUEUE)
  EndIf

  ; Disable, and wait for RDY to fall.
  nvme_Wr(#NVME_REG_CC, nvme_Rd(#NVME_REG_CC) & (~#NVME_CC_ENABLE))
  If nvme_WaitCsts(#NVME_CSTS_RDY, 0, nvme_toMs) = 0
    If nvme_err <> #NVME_ERR_NONE
      ProcedureReturn 0
    EndIf
    ProcedureReturn nvme_Fail(#NVME_ERR_RESET_TMO)
  EndIf

  nvme_ZeroPages(nvme_arena, #NVME_ARENA_BYTES / #NVME_PAGE)
  nvme_aTail = 0 : nvme_aHead = 0 : nvme_aPhase = 1
  nvme_ioTail = 0 : nvme_ioHead = 0 : nvme_ioPhase = 1
  nvme_Wr(#NVME_REG_INTMS, $FFFFFFFF)             ; polled: every vector masked
  nvme_Wr(#NVME_REG_AQA, ((#NVME_QDEPTH - 1) << 16) | (#NVME_QDEPTH - 1))
  nvme_Wr64(#NVME_REG_ASQ, nvme_Bus(nvme_arena + #NVME_ADMIN_SQ))
  nvme_Wr64(#NVME_REG_ACQ, nvme_Bus(nvme_arena + #NVME_ADMIN_CQ))
  nvme_Wr(#NVME_REG_CC, #NVME_CC_IOCQES | #NVME_CC_IOSQES | #NVME_CC_ENABLE)
  If nvme_WaitCsts(#NVME_CSTS_RDY, #NVME_CSTS_RDY, nvme_toMs) = 0
    If nvme_err <> #NVME_ERR_NONE
      ProcedureReturn 0
    EndIf
    ProcedureReturn nvme_Fail(#NVME_ERR_ENABLE_TMO)
  EndIf

  ; Identify controller: MDTS, the namespace count.
  If nvme_Identify(#NVME_CNS_CTRL, 0) = 0
    ProcedureReturn 0
  EndIf
  nvme_vid = PeekA(nvme_arena + #NVME_IDENTIFY) | (PeekA(nvme_arena + #NVME_IDENTIFY + 1) << 8)
  nvme_mdts = PeekA(nvme_arena + #NVME_IDENTIFY + 77)
  nvme_nn = PeekN(nvme_arena + #NVME_IDENTIFY + 516)
  nvme_maxBytes = #NVME_BOUNCE_PAGES * #NVME_PAGE
  If nvme_mdts > 0 And nvme_mdts < 5
    If ((1 << nvme_mdts) * #NVME_PAGE) < nvme_maxBytes
      nvme_maxBytes = (1 << nvme_mdts) * #NVME_PAGE
    EndIf
  EndIf
  If nvme_nn < 1
    ProcedureReturn nvme_Fail(#NVME_ERR_NO_NAMESPACE)
  EndIf

  ; Identify namespace 1: size and the formatted logical block size.
  If nvme_Identify(#NVME_CNS_NS, 1) = 0
    ProcedureReturn 0
  EndIf
  nvme_nsBlocks = PeekN(nvme_arena + #NVME_IDENTIFY) | (PeekN(nvme_arena + #NVME_IDENTIFY + 4) << 32)
  fmt = PeekA(nvme_arena + #NVME_IDENTIFY + 26) & $F
  ds = PeekA(nvme_arena + #NVME_IDENTIFY + 128 + (fmt * 4) + 2)
  If nvme_nsBlocks <= 0
    ProcedureReturn nvme_Fail(#NVME_ERR_NO_NAMESPACE)
  EndIf
  If ds < 9 Or ds > 12
    ProcedureReturn nvme_Fail(#NVME_ERR_LBA_SIZE)
  EndIf
  nvme_lbaShift = ds

  If nvme_CreateIoQueues() = 0
    ProcedureReturn 0
  EndIf
  nvme_ready = 1
  ProcedureReturn 1
EndProcedure

; One I/O command over the bounce buffer: opcode, first device LBA, device
; LBAs, the bytes that is. PRP1 is the first page; PRP2 the second page, or
; the PRP list page when more than two pages move.
Procedure.i nvme_Xfer(op.i, slba.i, nlb.i)
  Define bytes.i
  Define pages.i
  Define i.i
  Define sqe.i
  Define bounce.i
  bytes = nlb << nvme_lbaShift
  pages = (bytes + #NVME_PAGE - 1) / #NVME_PAGE
  bounce = nvme_arena + #NVME_BOUNCE
  sqe = nvme_NextSqe(1)
  PokeB(sqe, op)
  PokeL(sqe + 4, 1)
  nvme_PutQ(sqe + 24, nvme_Bus(bounce))
  If pages = 2
    nvme_PutQ(sqe + 32, nvme_Bus(bounce + #NVME_PAGE))
  ElseIf pages > 2
    i = 1
    While i < pages
      nvme_PutQ(nvme_arena + #NVME_PRP_LIST + ((i - 1) * 8), nvme_Bus(bounce + (i * #NVME_PAGE)))
      i = i + 1
    Wend
    nvme_CacheClean(nvme_arena + #NVME_PRP_LIST, #NVME_PAGE)
    nvme_PutQ(sqe + 32, nvme_Bus(nvme_arena + #NVME_PRP_LIST))
  EndIf
  nvme_PutQ(sqe + 40, slba)
  PokeL(sqe + 48, (nlb - 1) & $FFFF)
  If op = #NVME_IO_WRITE
    nvme_CacheClean(bounce, bytes)
  Else
    nvme_CacheInval(bounce, bytes)
  EndIf
  If nvme_Run(1, sqe) = 0
    ProcedureReturn 0
  EndIf
  If op = #NVME_IO_READ
    nvme_CacheInval(bounce, bytes)
  EndIf
  ProcedureReturn 1
EndProcedure

; Move count 512-byte blocks at 512-block lba to/from buf. Chunks never
; exceed the bounce buffer or MDTS; a chunk that does not start and end on
; a device-block boundary is read first, patched, and written back.
Procedure.i nvme_Blocks(lba.i, count.i, *buf, writing.i)
  Define per.i
  Define maxDev.i
  Define byteLo.i
  Define byteHi.i
  Define devLo.i
  Define devN.i
  Define edge.i
  Define take.i
  Define off.i
  Define done.i
  If nvme_ready = 0
    ProcedureReturn nvme_Fail(#NVME_ERR_NOT_ATTACHED)
  EndIf
  If count <= 0 Or lba < 0 Or *buf = 0
    ProcedureReturn nvme_Fail(#NVME_ERR_RANGE)
  EndIf
  per = 1 << (nvme_lbaShift - 9)                   ; 512-blocks per device block
  If ((lba + count + per - 1) / per) > nvme_nsBlocks
    ProcedureReturn nvme_Fail(#NVME_ERR_RANGE)
  EndIf
  maxDev = nvme_maxBytes >> nvme_lbaShift
  done = 0
  While done < count
    byteLo = (lba + done) * 512
    devLo = byteLo >> nvme_lbaShift
    off = byteLo - (devLo << nvme_lbaShift)
    take = count - done
    If ((off + (take * 512) + (1 << nvme_lbaShift) - 1) >> nvme_lbaShift) > maxDev
      take = ((maxDev << nvme_lbaShift) - off) / 512
    EndIf
    byteHi = off + (take * 512)
    devN = (byteHi + (1 << nvme_lbaShift) - 1) >> nvme_lbaShift
    edge = Bool(off <> 0 Or (byteHi & ((1 << nvme_lbaShift) - 1)) <> 0)
    If writing = 0 Or edge <> 0
      If nvme_Xfer(#NVME_IO_READ, devLo, devN) = 0
        ProcedureReturn 0
      EndIf
    EndIf
    If writing = 0
      nvme_Copy(nvme_arena + #NVME_BOUNCE + off, *buf + (done * 512), take * 512)
    Else
      nvme_Copy(*buf + (done * 512), nvme_arena + #NVME_BOUNCE + off, take * 512)
      If nvme_Xfer(#NVME_IO_WRITE, devLo, devN) = 0
        ProcedureReturn 0
      EndIf
    EndIf
    done = done + take
  Wend
  ProcedureReturn 1
EndProcedure

; ----------------------------------------------------------------------
;  THE SEAM. Reader(lba, count, *buf) / Writer(lba, count, *buf) in
;  512-byte blocks, Flusher(), each answering 1 or 0 - the contract of
;  Anvil/Storage/filesystem.pbi's FsSetRangeReader/Writer/BlockFlusher.
; ----------------------------------------------------------------------
Procedure.i NvmeReadBlocks(lba.i, count.i, *buf)
  ProcedureReturn nvme_Blocks(lba, count, *buf, 0)
EndProcedure

Procedure.i NvmeWriteBlocks(lba.i, count.i, *buf)
  ProcedureReturn nvme_Blocks(lba, count, *buf, 1)
EndProcedure

Procedure.i NvmeFlush()
  Define sqe.i
  If nvme_ready = 0
    ProcedureReturn nvme_Fail(#NVME_ERR_NOT_ATTACHED)
  EndIf
  sqe = nvme_NextSqe(1)
  PokeB(sqe, #NVME_IO_FLUSH)
  PokeL(sqe + 4, 1)
  ProcedureReturn nvme_Run(1, sqe)
EndProcedure

Procedure.i NvmeReady()      : ProcedureReturn nvme_ready : EndProcedure
Procedure.i NvmeError()      : ProcedureReturn nvme_err : EndProcedure
Procedure.i NvmeLastStatus() : ProcedureReturn nvme_lastStatus : EndProcedure
Procedure.i NvmeLbaBytes()   : ProcedureReturn 1 << nvme_lbaShift : EndProcedure
Procedure.i NvmeVendor()     : ProcedureReturn nvme_vid : EndProcedure
Procedure.i NvmeMaxBytes()   : ProcedureReturn nvme_maxBytes : EndProcedure

; The namespace in 512-byte blocks - what the seam counts in.
Procedure.i NvmeBlockCount()
  If nvme_ready = 0
    ProcedureReturn 0
  EndIf
  ProcedureReturn nvme_nsBlocks << (nvme_lbaShift - 9)
EndProcedure

Procedure.i NvmeErrorText()
  Select nvme_err
    Case #NVME_ERR_NONE
      ProcedureReturn "nvme: ok"
    Case #NVME_ERR_NOT_ATTACHED
      ProcedureReturn "nvme: no controller attached - NvmeAttach did not succeed"
    Case #NVME_ERR_ARENA
      ProcedureReturn "nvme: the arena is missing, not 4 KiB aligned, or shorter than #NVME_ARENA_BYTES"
    Case #NVME_ERR_NO_CONTROLLER
      ProcedureReturn "nvme: CAP reads all-ones or zero - no controller decodes at that BAR"
    Case #NVME_ERR_PAGE_SIZE
      ProcedureReturn "nvme: the controller's minimum page size (CAP.MPSMIN) is above 4 KiB"
    Case #NVME_ERR_NO_NVM_CSS
      ProcedureReturn "nvme: the controller does not offer the NVM command set (CAP.CSS bit 0)"
    Case #NVME_ERR_RESET_TMO
      ProcedureReturn "nvme: CSTS.RDY did not fall within CAP.TO after CC.EN was cleared"
    Case #NVME_ERR_ENABLE_TMO
      ProcedureReturn "nvme: CSTS.RDY did not rise within CAP.TO after CC.EN was set"
    Case #NVME_ERR_FATAL
      ProcedureReturn "nvme: the controller reports Controller Fatal Status (CSTS.CFS) - refused, nothing more is sent"
    Case #NVME_ERR_CMD_TMO
      ProcedureReturn "nvme: no completion with the expected phase within 5 s"
    Case #NVME_ERR_CMD_STATUS
      ProcedureReturn "nvme: the controller completed the command with a non-zero status - see NvmeLastStatus"
    Case #NVME_ERR_LBA_SIZE
      ProcedureReturn "nvme: namespace 1's logical block size is not 512 to 4096 bytes"
    Case #NVME_ERR_RANGE
      ProcedureReturn "nvme: the block range is outside namespace 1, or the buffer is null"
    Case #NVME_ERR_NO_NAMESPACE
      ProcedureReturn "nvme: the controller has no namespace 1, or it is empty"
    Case #NVME_ERR_QUEUE
      ProcedureReturn "nvme: the controller's maximum queue size (CAP.MQES) is below this file's depth"
    Case #NVME_ERR_CID
      ProcedureReturn "nvme: a completion came back for a command this file did not issue"
    Case #NVME_ERR_NO_TIMER
      ProcedureReturn "nvme: TickHz() is zero, so no wait could be bounded"
  EndSelect
  ProcedureReturn "nvme: unknown error"
EndProcedure
