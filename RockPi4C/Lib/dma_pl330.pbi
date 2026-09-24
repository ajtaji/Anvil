; Bounded RK3399 PL330 memory DMA for Anvil's EL3, cache-off environment.
;
; Controller identity, registers, debug execution, instruction encodings and
; the R0P0 LD/RMB/ST/WMB workaround follow Radxa's official
; release-4.4-rockpi4 drivers/dma/pl330.c.  DMAC0's address and clock come
; from the dmac_bus node at arch/arm64/boot/dts/rockchip/rk3399.dtsi; its GPLL
; ACLK_PERILP0 divider chain, assigned rates, parent, NoC and
; ACLK_DMAC0_PERILP gates come from drivers/clk/rockchip/clk-rk3399.c and the
; RK3399 CRU node on that branch. The DTS address is the normal-world APB
; aperture. RK3399 TRM figure 1-1 also maps the secure DMAC0 APB aperture at
; $FFFC0000. Anvil executes at EL3 with the MMU off and therefore uses that
; secure alias. A read-only silicon proof returned PID $00241330 and CID
; $B105F00D from it. This driver observes reset state and never pulses reset.
;
; This module deliberately owns only channel 0 and event 0. It accepts
; framebuffer-sized requests over physical 32-bit addresses, splits them into
; aligned chunks no larger than 1 MiB, and emits noncacheable secure-manager
; programs. Fill seeds 256 bytes at the destination, then doubles the filled
; span with the incrementing-copy program: the upstream PL330 driver does not
; advertise a memory-set operation, and silicon faulted its fixed-memory-source
; form. The doubling fill and a separate 1024-byte blit passed the live
; private-buffer silicon proof under Anvil's armed deadman. EL3
; I-cache, D-cache or MMU enable makes the memory/microcode coherency contract
; ambiguous and is refused.

#ROCK_DMA_PL330_BASE = $FFFC0000
#ROCK_DMA_PL330_CLKSEL23_MASK = $739F
#ROCK_DMA_PL330_CLKSEL23_GPLL_BASE = $1080
#ROCK_DMA_PL330_ACLK_TARGET = 100000000
#ROCK_DMA_PL330_RESET_PERILP0_NOC = $1
#ROCK_DMA_PL330_RESET_DMAC0 = $8
#ROCK_DMA_PL330_DS = $000
#ROCK_DMA_PL330_DPC = $004
#ROCK_DMA_PL330_INTEN = $020
#ROCK_DMA_PL330_ES = $024
#ROCK_DMA_PL330_INTSTATUS = $028
#ROCK_DMA_PL330_INTCLR = $02C
#ROCK_DMA_PL330_FSM = $030
#ROCK_DMA_PL330_FSC = $034
#ROCK_DMA_PL330_FTM = $038
#ROCK_DMA_PL330_FTC0 = $040
#ROCK_DMA_PL330_CS0 = $100
#ROCK_DMA_PL330_CPC0 = $104
#ROCK_DMA_PL330_SA0 = $400
#ROCK_DMA_PL330_DA0 = $404
#ROCK_DMA_PL330_CC0 = $408
#ROCK_DMA_PL330_LC00 = $40C
#ROCK_DMA_PL330_LC10 = $410
#ROCK_DMA_PL330_DBGSTATUS = $D00
#ROCK_DMA_PL330_DBGCMD = $D04
#ROCK_DMA_PL330_DBGINST0 = $D08
#ROCK_DMA_PL330_DBGINST1 = $D0C
#ROCK_DMA_PL330_CR0 = $E00
#ROCK_DMA_PL330_CR1 = $E04
#ROCK_DMA_PL330_CR2 = $E08
#ROCK_DMA_PL330_CR3 = $E0C
#ROCK_DMA_PL330_CR4 = $E10
#ROCK_DMA_PL330_CRD = $E14
#ROCK_DMA_PL330_PID0 = $FE0
#ROCK_DMA_PL330_PID1 = $FE4
#ROCK_DMA_PL330_PID2 = $FE8
#ROCK_DMA_PL330_PID3 = $FEC
#ROCK_DMA_PL330_CID0 = $FF0
#ROCK_DMA_PL330_CID1 = $FF4
#ROCK_DMA_PL330_CID2 = $FF8
#ROCK_DMA_PL330_CID3 = $FFC

#ROCK_DMA_PL330_PART_DESIGNER = $41330
#ROCK_DMA_PL330_COMPONENT_ID = $B105F00D
#ROCK_DMA_PL330_BOOT_MAN_NS = $4
#ROCK_DMA_PL330_STATE_STOP = $0
#ROCK_DMA_PL330_STATE_FLTCMP = $E
#ROCK_DMA_PL330_STATE_FAULT = $F
#ROCK_DMA_PL330_EVENT0 = $1
#ROCK_DMA_PL330_DBG_BUSY = $1

#ROCK_DMA_PL330_CMD_END = $00
#ROCK_DMA_PL330_CMD_KILL = $01
#ROCK_DMA_PL330_CMD_LD = $04
#ROCK_DMA_PL330_CMD_ST = $08
#ROCK_DMA_PL330_CMD_RMB = $12
#ROCK_DMA_PL330_CMD_WMB = $13
#ROCK_DMA_PL330_CMD_LP = $20
#ROCK_DMA_PL330_CMD_LPEND = $28
#ROCK_DMA_PL330_CMD_SEV = $34
#ROCK_DMA_PL330_CMD_MOV = $BC
#ROCK_DMA_PL330_CMD_GO = $A0
#ROCK_DMA_PL330_MOV_SAR = 0
#ROCK_DMA_PL330_MOV_CCR = 1
#ROCK_DMA_PL330_MOV_DAR = 2

#ROCK_DMA_PL330_CCR_SECURE_COPY = $00414105
#ROCK_DMA_PL330_MAX_CHUNK = $100000
#ROCK_DMA_PL330_MAX_PROGRAM = 96
#ROCK_DMA_PL330_FILL_SEED_BYTES = 256
#ROCK_DMA_PL330_DEBUG_TIMEOUT_US = 5000
#ROCK_DMA_PL330_JOB_TIMEOUT_US = 100000

#ROCK_DMA_PL330_ERROR_EL = 1
#ROCK_DMA_PL330_ERROR_CACHE = 2
#ROCK_DMA_PL330_ERROR_TIMER = 3
#ROCK_DMA_PL330_ERROR_RESET = 4
#ROCK_DMA_PL330_ERROR_CLOCK = 5
#ROCK_DMA_PL330_ERROR_ID = 6
#ROCK_DMA_PL330_ERROR_CAPABILITY = 7
#ROCK_DMA_PL330_ERROR_MANAGER_NS = 8
#ROCK_DMA_PL330_ERROR_BUSY = 9
#ROCK_DMA_PL330_ERROR_ARGUMENT = 10
#ROCK_DMA_PL330_ERROR_PROGRAM = 11
#ROCK_DMA_PL330_ERROR_DEBUG = 12
#ROCK_DMA_PL330_ERROR_FAULT = 13
#ROCK_DMA_PL330_ERROR_TIMEOUT = 14
#ROCK_DMA_PL330_ERROR_KILL = 15
#ROCK_DMA_PL330_ERROR_SECURITY = 16
#ROCK_DMA_PL330_ERROR_PARENT_RESET = 17
#ROCK_DMA_PL330_ERROR_UNREACHABLE = 18

Global rock_dma_pl330_ready.i
Global rock_dma_pl330_error.i
Global rock_dma_pl330_pid.i
Global rock_dma_pl330_cid.i
Global rock_dma_pl330_revision.i
Global rock_dma_pl330_cr0.i
Global rock_dma_pl330_cr1.i
Global rock_dma_pl330_cr2.i
Global rock_dma_pl330_cr3.i
Global rock_dma_pl330_cr4.i
Global rock_dma_pl330_crd.i
Global rock_dma_pl330_channels.i
Global rock_dma_pl330_events.i
Global rock_dma_pl330_bus_width.i
Global rock_dma_pl330_buffer_depth.i
Global rock_dma_pl330_clksel23.i
Global rock_dma_pl330_clksel23_before.i
Global rock_dma_pl330_gate7.i
Global rock_dma_pl330_gate7_before.i
Global rock_dma_pl330_gate25.i
Global rock_dma_pl330_gate25_before.i
Global rock_dma_pl330_reset10.i
Global rock_dma_pl330_gpll_rate.i
Global rock_dma_pl330_aclk_rate.i
Global rock_dma_pl330_pid0.i
Global rock_dma_pl330_pid1.i
Global rock_dma_pl330_pid2.i
Global rock_dma_pl330_pid3.i
Global rock_dma_pl330_cid0.i
Global rock_dma_pl330_cid1.i
Global rock_dma_pl330_cid2.i
Global rock_dma_pl330_cid3.i
Global rock_dma_pl330_ds.i
Global rock_dma_pl330_fsm.i
Global rock_dma_pl330_fsc.i
Global rock_dma_pl330_ftm.i
Global rock_dma_pl330_cs0.i
Global rock_dma_pl330_ftc0.i
Global rock_dma_pl330_inten.i
Global rock_dma_pl330_es.i
Global rock_dma_pl330_intstatus.i
Global rock_dma_pl330_cpc0.i
Global rock_dma_pl330_sa0.i
Global rock_dma_pl330_da0.i
Global rock_dma_pl330_cc0.i
Global rock_dma_pl330_lc00.i
Global rock_dma_pl330_lc10.i
Global rock_dma_pl330_fault_valid.i
Global rock_dma_pl330_fault_ds.i
Global rock_dma_pl330_fault_dpc.i
Global rock_dma_pl330_fault_fsm.i
Global rock_dma_pl330_fault_fsc.i
Global rock_dma_pl330_fault_ftm.i
Global rock_dma_pl330_fault_cs0.i
Global rock_dma_pl330_fault_ftc0.i
Global rock_dma_pl330_fault_cpc0.i
Global rock_dma_pl330_fault_sa0.i
Global rock_dma_pl330_fault_da0.i
Global rock_dma_pl330_fault_cc0.i
Global rock_dma_pl330_program_address.i
Global rock_dma_pl330_program_bytes.i
Global rock_dma_pl330_completed_bytes.i
Global Dim rock_dma_pl330_program_storage.a[#ROCK_DMA_PL330_MAX_PROGRAM+7]

Procedure.i RockDmaPl330Read(offset.i)
  ProcedureReturn PeekL(#ROCK_DMA_PL330_BASE+offset) & $FFFFFFFF
EndProcedure

Procedure RockDmaPl330Write(offset.i,value.i)
  PokeL(#ROCK_DMA_PL330_BASE+offset,value & $FFFFFFFF)
EndProcedure

Procedure RockDmaPl330Barrier()
  ASM
    dsb sy
  ENDASM
EndProcedure

Procedure RockDmaPl330CaptureActivity()
  rock_dma_pl330_ds=RockDmaPl330Read(#ROCK_DMA_PL330_DS)
  rock_dma_pl330_fsm=RockDmaPl330Read(#ROCK_DMA_PL330_FSM)
  rock_dma_pl330_fsc=RockDmaPl330Read(#ROCK_DMA_PL330_FSC)
  rock_dma_pl330_ftm=RockDmaPl330Read(#ROCK_DMA_PL330_FTM)
  rock_dma_pl330_cs0=RockDmaPl330Read(#ROCK_DMA_PL330_CS0)
  rock_dma_pl330_ftc0=RockDmaPl330Read(#ROCK_DMA_PL330_FTC0)
  rock_dma_pl330_inten=RockDmaPl330Read(#ROCK_DMA_PL330_INTEN)
  rock_dma_pl330_es=RockDmaPl330Read(#ROCK_DMA_PL330_ES)
  If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
  rock_dma_pl330_intstatus=RockDmaPl330Read(#ROCK_DMA_PL330_INTSTATUS)
  rock_dma_pl330_cpc0=RockDmaPl330Read(#ROCK_DMA_PL330_CPC0)
  rock_dma_pl330_sa0=RockDmaPl330Read(#ROCK_DMA_PL330_SA0)
  rock_dma_pl330_da0=RockDmaPl330Read(#ROCK_DMA_PL330_DA0)
  rock_dma_pl330_cc0=RockDmaPl330Read(#ROCK_DMA_PL330_CC0)
  rock_dma_pl330_lc00=RockDmaPl330Read(#ROCK_DMA_PL330_LC00)
  rock_dma_pl330_lc10=RockDmaPl330Read(#ROCK_DMA_PL330_LC10)
EndProcedure

Procedure RockDmaPl330SnapshotFault()
  ; Freeze the first failure before the bounded KILL changes channel state.
  rock_dma_pl330_fault_ds=RockDmaPl330Read(#ROCK_DMA_PL330_DS)
  rock_dma_pl330_fault_dpc=RockDmaPl330Read(#ROCK_DMA_PL330_DPC)
  rock_dma_pl330_fault_fsm=RockDmaPl330Read(#ROCK_DMA_PL330_FSM)
  rock_dma_pl330_fault_fsc=RockDmaPl330Read(#ROCK_DMA_PL330_FSC)
  rock_dma_pl330_fault_ftm=RockDmaPl330Read(#ROCK_DMA_PL330_FTM)
  rock_dma_pl330_fault_cs0=RockDmaPl330Read(#ROCK_DMA_PL330_CS0)
  rock_dma_pl330_fault_ftc0=RockDmaPl330Read(#ROCK_DMA_PL330_FTC0)
  rock_dma_pl330_fault_cpc0=RockDmaPl330Read(#ROCK_DMA_PL330_CPC0)
  rock_dma_pl330_fault_sa0=RockDmaPl330Read(#ROCK_DMA_PL330_SA0)
  rock_dma_pl330_fault_da0=RockDmaPl330Read(#ROCK_DMA_PL330_DA0)
  rock_dma_pl330_fault_cc0=RockDmaPl330Read(#ROCK_DMA_PL330_CC0)
  rock_dma_pl330_fault_valid=1
EndProcedure

Procedure.i RockDmaPl330EmitByte(offset.i,value.i)
  If offset<0 Or offset>=#ROCK_DMA_PL330_MAX_PROGRAM : ProcedureReturn -1 : EndIf
  PokeA(rock_dma_pl330_program_address+offset,value & $FF)
  ProcedureReturn offset+1
EndProcedure

Procedure.i RockDmaPl330EmitMov(offset.i,destination.i,value.i)
  Protected index.i
  index=RockDmaPl330EmitByte(offset,#ROCK_DMA_PL330_CMD_MOV)
  If index<0 : ProcedureReturn -1 : EndIf
  index=RockDmaPl330EmitByte(index,destination)
  If index<0 : ProcedureReturn -1 : EndIf
  index=RockDmaPl330EmitByte(index,value)
  If index<0 : ProcedureReturn -1 : EndIf
  index=RockDmaPl330EmitByte(index,value >> 8)
  If index<0 : ProcedureReturn -1 : EndIf
  index=RockDmaPl330EmitByte(index,value >> 16)
  If index<0 : ProcedureReturn -1 : EndIf
  ProcedureReturn RockDmaPl330EmitByte(index,value >> 24)
EndProcedure

Procedure.i RockDmaPl330EmitLp(offset.i,loop.i,count.i)
  Protected index.i
  If count<1 Or count>256 : ProcedureReturn -1 : EndIf
  index=RockDmaPl330EmitByte(offset,#ROCK_DMA_PL330_CMD_LP | ((loop & 1) << 1))
  If index<0 : ProcedureReturn -1 : EndIf
  ProcedureReturn RockDmaPl330EmitByte(index,count-1)
EndProcedure

Procedure.i RockDmaPl330EmitLpEnd(offset.i,loop.i,jump.i)
  Protected index.i
  If jump<1 Or jump>255 : ProcedureReturn -1 : EndIf
  index=RockDmaPl330EmitByte(offset,#ROCK_DMA_PL330_CMD_LPEND | $10 | ((loop & 1) << 2))
  If index<0 : ProcedureReturn -1 : EndIf
  ProcedureReturn RockDmaPl330EmitByte(index,jump)
EndProcedure

Procedure.i RockDmaPl330EmitBurst(offset.i)
  Protected index.i=RockDmaPl330EmitByte(offset,#ROCK_DMA_PL330_CMD_LD)
  If index<0 : ProcedureReturn -1 : EndIf
  ; Radxa's R0P0 path inserts barriers to avoid the original lockup erratum.
  If rock_dma_pl330_revision=0
    index=RockDmaPl330EmitByte(index,#ROCK_DMA_PL330_CMD_RMB)
    If index<0 : ProcedureReturn -1 : EndIf
  EndIf
  index=RockDmaPl330EmitByte(index,#ROCK_DMA_PL330_CMD_ST)
  If index<0 : ProcedureReturn -1 : EndIf
  If rock_dma_pl330_revision=0
    index=RockDmaPl330EmitByte(index,#ROCK_DMA_PL330_CMD_WMB)
  EndIf
  ProcedureReturn index
EndProcedure

Procedure.i RockDmaPl330BuildProgram(source.i,destination.i,words.i)
  Protected offset.i
  Protected loopStart.i
  Protected innerStart.i
  Protected outerCount.i
  Protected bodyBytes.i
  Protected clear.i
  If words<1 Or words>65536 : ProcedureReturn 0 : EndIf
  If words>256 And (words & 255)<>0 : ProcedureReturn 0 : EndIf
  For clear=0 To #ROCK_DMA_PL330_MAX_PROGRAM-1
    PokeA(rock_dma_pl330_program_address+clear,0)
    If clear = 47 And rock_uart_ready <> 0 : RockUartPump(64) : EndIf
  Next
  If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
  offset=RockDmaPl330EmitMov(0,#ROCK_DMA_PL330_MOV_CCR,#ROCK_DMA_PL330_CCR_SECURE_COPY)
  offset=RockDmaPl330EmitMov(offset,#ROCK_DMA_PL330_MOV_SAR,source)
  offset=RockDmaPl330EmitMov(offset,#ROCK_DMA_PL330_MOV_DAR,destination)
  If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
  If offset<0 : ProcedureReturn 0 : EndIf
  If words<=256
    offset=RockDmaPl330EmitLp(offset,1,words)
    loopStart=offset
    offset=RockDmaPl330EmitBurst(offset)
    If offset<0 : ProcedureReturn 0 : EndIf
    offset=RockDmaPl330EmitLpEnd(offset,1,offset-loopStart)
  Else
    outerCount=words/256
    offset=RockDmaPl330EmitLp(offset,0,outerCount)
    loopStart=offset
    offset=RockDmaPl330EmitLp(offset,1,256)
    innerStart=offset
    offset=RockDmaPl330EmitBurst(offset)
    If offset<0 : ProcedureReturn 0 : EndIf
    bodyBytes=offset-innerStart
    offset=RockDmaPl330EmitLpEnd(offset,1,bodyBytes)
    If offset<0 : ProcedureReturn 0 : EndIf
    offset=RockDmaPl330EmitLpEnd(offset,0,offset-loopStart)
  EndIf
  If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
  If offset<0 : ProcedureReturn 0 : EndIf
  offset=RockDmaPl330EmitByte(offset,#ROCK_DMA_PL330_CMD_SEV)
  offset=RockDmaPl330EmitByte(offset,0)
  offset=RockDmaPl330EmitByte(offset,#ROCK_DMA_PL330_CMD_END)
  If offset<0 : ProcedureReturn 0 : EndIf
  rock_dma_pl330_program_bytes=offset
  RockDmaPl330Barrier()
  If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockDmaPl330DebugExecute(opcode.i,argument.i,asManager.i)
  Protected instruction0.i=(opcode & $FF) << 16
  Protected start.i
  Protected now.i
  Protected timeout.i
  If asManager=0 : instruction0=instruction0 | 1 : EndIf
  ; Never replace a pending debug instruction. First prove the debug port is
  ; idle with the same finite five-millisecond policy as the Radxa driver.
  start=RockTimerTicks()
  timeout=(rock_timer_frequency/1000000)*#ROCK_DMA_PL330_DEBUG_TIMEOUT_US
  If timeout<1 : timeout=1 : EndIf
  rock_uart_rx_context = 11
  Repeat
    If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
    If (RockDmaPl330Read(#ROCK_DMA_PL330_DBGSTATUS) & #ROCK_DMA_PL330_DBG_BUSY)=0 : Break : EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=timeout
      rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_DEBUG
      ProcedureReturn 0
    EndIf
  ForEver
  RockDmaPl330Write(#ROCK_DMA_PL330_DBGINST0,instruction0)
  RockDmaPl330Write(#ROCK_DMA_PL330_DBGINST1,argument)
  RockDmaPl330Barrier()
  RockDmaPl330Write(#ROCK_DMA_PL330_DBGCMD,0)
  RockDmaPl330Barrier()
  rock_uart_rx_context = 12
  If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i RockDmaPl330Kill()
  Protected start.i
  Protected now.i
  Protected timeout.i
  RockDmaPl330CaptureActivity()
  If (rock_dma_pl330_cs0 & $F)=#ROCK_DMA_PL330_STATE_STOP : ProcedureReturn 1 : EndIf
  If RockDmaPl330DebugExecute(#ROCK_DMA_PL330_CMD_KILL,0,0)=0 : ProcedureReturn 0 : EndIf
  start=RockTimerTicks()
  timeout=(rock_timer_frequency/1000000)*#ROCK_DMA_PL330_DEBUG_TIMEOUT_US
  If timeout<1 : timeout=1 : EndIf
  Repeat
    If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
    RockDmaPl330CaptureActivity()
    If (rock_dma_pl330_cs0 & $F)=#ROCK_DMA_PL330_STATE_STOP : ProcedureReturn 1 : EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=timeout : Break : EndIf
  ForEver
  rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_KILL
  ProcedureReturn 0
EndProcedure

Procedure.i RockDmaPl330RunProgram()
  Protected start.i
  Protected now.i
  Protected timeout.i
  Protected state.i
  Protected managerState.i
  Protected goArgument.i
  rock_dma_pl330_fault_valid=0
  rock_uart_rx_context = 6
  If rock_dma_pl330_program_address<=0 Or rock_dma_pl330_program_address>$FFFFFFFF
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_PROGRAM : ProcedureReturn 0
  EndIf
  If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
  RockDmaPl330CaptureActivity()
  rock_uart_rx_context = 7
  If (rock_dma_pl330_cs0 & $F)<>#ROCK_DMA_PL330_STATE_STOP Or rock_dma_pl330_fsc<>0 Or rock_dma_pl330_ftc0<>0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_BUSY : ProcedureReturn 0
  EndIf
  ; Channel 0 uses event 0.  Clear its old latch, then enable only that bit
  ; while preserving every event outside this driver's ownership.
  RockDmaPl330Write(#ROCK_DMA_PL330_INTCLR,#ROCK_DMA_PL330_EVENT0)
  RockDmaPl330Write(#ROCK_DMA_PL330_INTEN,rock_dma_pl330_inten | #ROCK_DMA_PL330_EVENT0)
  RockDmaPl330Barrier()
  If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
  ; DMAGO is six bytes. DBGINST0 carries secure GO+channel 0; DBGINST1 carries
  ; the physical microcode address. Bit 1 is deliberately clear (manager-secure).
  goArgument=rock_dma_pl330_program_address & $FFFFFFFF
  RockWatchdogPet()
  rock_uart_rx_context = 8
  If RockDmaPl330DebugExecute(#ROCK_DMA_PL330_CMD_GO,goArgument,1)=0
    RockDmaPl330Write(#ROCK_DMA_PL330_INTEN,rock_dma_pl330_inten & $FFFFFFFE)
    ProcedureReturn 0
  EndIf
  start=RockTimerTicks()
  timeout=(rock_timer_frequency/1000000)*#ROCK_DMA_PL330_JOB_TIMEOUT_US
  If timeout<1 : timeout=1 : EndIf
  Repeat
    rock_uart_rx_context = 9
    If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
    RockDmaPl330CaptureActivity()
    state=rock_dma_pl330_cs0 & $F
    managerState=rock_dma_pl330_ds & $F
    If rock_dma_pl330_fsm<>0 Or rock_dma_pl330_fsc<>0 Or rock_dma_pl330_ftm<>0 Or rock_dma_pl330_ftc0<>0 Or managerState=#ROCK_DMA_PL330_STATE_FLTCMP Or managerState=#ROCK_DMA_PL330_STATE_FAULT Or state=#ROCK_DMA_PL330_STATE_FLTCMP Or state=#ROCK_DMA_PL330_STATE_FAULT
      rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_FAULT
      Break
    EndIf
    If (rock_dma_pl330_intstatus & #ROCK_DMA_PL330_EVENT0)<>0 And state=#ROCK_DMA_PL330_STATE_STOP
      RockDmaPl330Write(#ROCK_DMA_PL330_INTCLR,#ROCK_DMA_PL330_EVENT0)
      RockDmaPl330Write(#ROCK_DMA_PL330_INTEN,rock_dma_pl330_inten & $FFFFFFFE)
      RockDmaPl330Barrier()
      RockWatchdogPet()
      rock_uart_rx_context = 10
      If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
      ProcedureReturn 1
    EndIf
    now=RockTimerTicks()
    If now<start Or now-start>=timeout
      rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_TIMEOUT
      Break
    EndIf
  ForEver
  RockDmaPl330SnapshotFault()
  RockDmaPl330Kill()
  RockDmaPl330Write(#ROCK_DMA_PL330_INTCLR,#ROCK_DMA_PL330_EVENT0)
  RockDmaPl330Write(#ROCK_DMA_PL330_INTEN,rock_dma_pl330_inten & $FFFFFFFE)
  RockDmaPl330Barrier()
  ProcedureReturn 0
EndProcedure

Procedure.i RockDmaPl330Init()
  Protected aclkDivider.i
  Protected clksel23Plan.i
  rock_dma_pl330_ready=0
  rock_dma_pl330_error=0
  rock_dma_pl330_completed_bytes=0
  If rock_current_el<>12
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_EL : ProcedureReturn 0
  EndIf
  If (rock_sctlr_el3 & $1005)<>0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_CACHE : ProcedureReturn 0
  EndIf
  If rock_timer_frequency<1000000
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_TIMER : ProcedureReturn 0
  EndIf
  ; U-Boot's RK3399 XPL path removes the BootROM's DDR/slave DMA security
  ; regions before starting a bus master. Reuse the shared, readback-checked
  ; implementation rather than reproducing PMUSGRF writes in this driver.
  If RockSecurityReleaseDma()=0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_SECURITY : ProcedureReturn 0
  EndIf
  ; The pinned DTS assigns ACLK/HCLK/PCLK_PERILP0 to 100/100/50 MHz. Derive
  ; the ACLK divider from the verified live GPLL: direct-SD startup uses
  ; 400 MHz while the two pinned U-Boot paths use 594 or 800 MHz. This is the
  ; same ceiling-divider policy as their clock drivers and never overclocks
  ; the 100 MHz assigned rate.
  rock_dma_pl330_gpll_rate=RockCruPllRate($80,1,47)
  If rock_dma_pl330_gpll_rate<>400000000 And rock_dma_pl330_gpll_rate<>594000000 And rock_dma_pl330_gpll_rate<>800000000
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_CLOCK : ProcedureReturn 0
  EndIf
  aclkDivider=RockCruCeilingDivider(rock_dma_pl330_gpll_rate,#ROCK_DMA_PL330_ACLK_TARGET)
  If aclkDivider<1 Or aclkDivider>32
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_CLOCK : ProcedureReturn 0
  EndIf
  rock_dma_pl330_aclk_rate=rock_dma_pl330_gpll_rate/aclkDivider
  clksel23Plan=#ROCK_DMA_PL330_CLKSEL23_GPLL_BASE | (aclkDivider-1)
  rock_dma_pl330_clksel23_before=RockCruRead(#ROCK_CRU_CLKSEL+23*4)
  rock_dma_pl330_gate7_before=RockCruRead(#ROCK_CRU_CLKGATE+7*4)
  rock_dma_pl330_gate25_before=RockCruRead(#ROCK_CRU_CLKGATE+25*4)
  RockCruField(#ROCK_CRU_CLKSEL+23*4,#ROCK_DMA_PL330_CLKSEL23_MASK,clksel23Plan)
  RockCruGate(7,0,1)
  RockCruGate(7,2,1)
  RockCruGate(25,7,1)
  RockCruGate(25,5,1)
  RockDmaPl330Barrier()
  rock_dma_pl330_clksel23=RockCruRead(#ROCK_CRU_CLKSEL+23*4)
  rock_dma_pl330_gate7=RockCruRead(#ROCK_CRU_CLKGATE+7*4)
  rock_dma_pl330_gate25=RockCruRead(#ROCK_CRU_CLKGATE+25*4)
  rock_dma_pl330_reset10=RockCruRead(#ROCK_CRU_SOFTRST+10*4)
  If (rock_dma_pl330_reset10 & #ROCK_DMA_PL330_RESET_PERILP0_NOC)<>0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_PARENT_RESET : ProcedureReturn 0
  EndIf
  If (rock_dma_pl330_reset10 & #ROCK_DMA_PL330_RESET_DMAC0)<>0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_RESET : ProcedureReturn 0
  EndIf
  If (rock_dma_pl330_clksel23 & #ROCK_DMA_PL330_CLKSEL23_MASK)<>clksel23Plan Or (rock_dma_pl330_gate7 & $5)<>0 Or (rock_dma_pl330_gate25 & $A0)<>0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_CLOCK : ProcedureReturn 0
  EndIf
  ; Retain every raw word. A composite zero alone cannot tell a clock/reset
  ; admission failure from one malformed PrimeCell byte lane.
  rock_dma_pl330_pid0=RockDmaPl330Read(#ROCK_DMA_PL330_PID0)
  rock_dma_pl330_pid1=RockDmaPl330Read(#ROCK_DMA_PL330_PID1)
  rock_dma_pl330_pid2=RockDmaPl330Read(#ROCK_DMA_PL330_PID2)
  rock_dma_pl330_pid3=RockDmaPl330Read(#ROCK_DMA_PL330_PID3)
  rock_dma_pl330_cid0=RockDmaPl330Read(#ROCK_DMA_PL330_CID0)
  rock_dma_pl330_cid1=RockDmaPl330Read(#ROCK_DMA_PL330_CID1)
  rock_dma_pl330_cid2=RockDmaPl330Read(#ROCK_DMA_PL330_CID2)
  rock_dma_pl330_cid3=RockDmaPl330Read(#ROCK_DMA_PL330_CID3)
  rock_dma_pl330_pid=(rock_dma_pl330_pid0 & $FF) | ((rock_dma_pl330_pid1 & $FF) << 8) | ((rock_dma_pl330_pid2 & $FF) << 16) | ((rock_dma_pl330_pid3 & $FF) << 24)
  rock_dma_pl330_cid=(rock_dma_pl330_cid0 & $FF) | ((rock_dma_pl330_cid1 & $FF) << 8) | ((rock_dma_pl330_cid2 & $FF) << 16) | ((rock_dma_pl330_cid3 & $FF) << 24)
  rock_dma_pl330_revision=(rock_dma_pl330_pid >> 20) & $F
  If rock_dma_pl330_pid=0 And rock_dma_pl330_cid=0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_UNREACHABLE : ProcedureReturn 0
  EndIf
  If (rock_dma_pl330_pid & $FFFFF)<>#ROCK_DMA_PL330_PART_DESIGNER Or rock_dma_pl330_cid<>#ROCK_DMA_PL330_COMPONENT_ID
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_ID : ProcedureReturn 0
  EndIf
  rock_dma_pl330_cr0=RockDmaPl330Read(#ROCK_DMA_PL330_CR0)
  rock_dma_pl330_cr1=RockDmaPl330Read(#ROCK_DMA_PL330_CR1)
  rock_dma_pl330_cr2=RockDmaPl330Read(#ROCK_DMA_PL330_CR2)
  rock_dma_pl330_cr3=RockDmaPl330Read(#ROCK_DMA_PL330_CR3)
  rock_dma_pl330_cr4=RockDmaPl330Read(#ROCK_DMA_PL330_CR4)
  rock_dma_pl330_crd=RockDmaPl330Read(#ROCK_DMA_PL330_CRD)
  rock_dma_pl330_channels=((rock_dma_pl330_cr0 >> 4) & 7)+1
  rock_dma_pl330_events=((rock_dma_pl330_cr0 >> 17) & $1F)+1
  rock_dma_pl330_bus_width=8*(1 << (rock_dma_pl330_crd & 7))
  rock_dma_pl330_buffer_depth=((rock_dma_pl330_crd >> 20) & $3FF)+1
  If rock_dma_pl330_channels<1 Or rock_dma_pl330_events<1 Or rock_dma_pl330_bus_width<8 Or rock_dma_pl330_buffer_depth<1
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_CAPABILITY : ProcedureReturn 0
  EndIf
  If (rock_dma_pl330_cr0 & #ROCK_DMA_PL330_BOOT_MAN_NS)<>0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_MANAGER_NS : ProcedureReturn 0
  EndIf
  RockDmaPl330CaptureActivity()
  If (rock_dma_pl330_ds & $F)<>#ROCK_DMA_PL330_STATE_STOP Or rock_dma_pl330_fsm<>0 Or rock_dma_pl330_fsc<>0 Or rock_dma_pl330_ftm<>0 Or (rock_dma_pl330_cs0 & $F)<>#ROCK_DMA_PL330_STATE_STOP Or rock_dma_pl330_ftc0<>0 Or (rock_dma_pl330_inten & #ROCK_DMA_PL330_EVENT0)<>0 Or (rock_dma_pl330_es & #ROCK_DMA_PL330_EVENT0)<>0 Or (rock_dma_pl330_intstatus & #ROCK_DMA_PL330_EVENT0)<>0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_BUSY : ProcedureReturn 0
  EndIf
  rock_dma_pl330_program_address=(@rock_dma_pl330_program_storage[0]+7) & ~$7
  If rock_dma_pl330_program_address<=0 Or rock_dma_pl330_program_address>$FFFFFFFF
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_PROGRAM : ProcedureReturn 0
  EndIf
  rock_dma_pl330_ready=1
  ProcedureReturn 1
EndProcedure

Procedure.i RockDmaPl330Transfer(destination.i,source.i,bytes.i)
  Protected remaining.i=bytes
  Protected chunkRemaining.i
  Protected words.i
  Protected batchWords.i
  Protected batchBytes.i
  If rock_dma_pl330_ready=0 Or bytes<=0 Or (bytes & 3)<>0 Or (destination & 3)<>0 Or (source & 3)<>0
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_ARGUMENT : ProcedureReturn 0
  EndIf
  If destination<0 Or source<0 Or destination>$100000000-bytes Or source>$100000000-bytes
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_ARGUMENT : ProcedureReturn 0
  EndIf
  If destination<source+bytes And source<destination+bytes
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_ARGUMENT : ProcedureReturn 0
  EndIf
  rock_dma_pl330_error=0
  rock_dma_pl330_completed_bytes=0
  While remaining>0
    chunkRemaining=remaining
    If chunkRemaining>#ROCK_DMA_PL330_MAX_CHUNK : chunkRemaining=#ROCK_DMA_PL330_MAX_CHUNK : EndIf
    While chunkRemaining>0
      rock_uart_rx_context = 1
      If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
      words=chunkRemaining/4
      If words>65536
        batchWords=65536
      ElseIf words>256
        batchWords=(words/256)*256
      Else
        batchWords=words
      EndIf
      batchBytes=batchWords*4
      rock_uart_rx_context = 2
      If RockDmaPl330BuildProgram(source,destination,batchWords)=0
        rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_PROGRAM : ProcedureReturn 0
      EndIf
      rock_uart_rx_context = 3
      If rock_uart_ready <> 0 : RockUartPump(64) : EndIf
      rock_uart_rx_context = 4
      If RockDmaPl330RunProgram()=0 : ProcedureReturn 0 : EndIf
      rock_uart_rx_context = 5
      destination=destination+batchBytes
      source=source+batchBytes
      remaining=remaining-batchBytes
      chunkRemaining=chunkRemaining-batchBytes
      rock_dma_pl330_completed_bytes=rock_dma_pl330_completed_bytes+batchBytes
    Wend
  Wend
  ProcedureReturn 1
EndProcedure

Procedure.i RockDmaPl330Copy(destination.i,source.i,bytes.i)
  ProcedureReturn RockDmaPl330Transfer(destination,source,bytes)
EndProcedure

Procedure.i RockDmaPl330Fill32(destination.i,value.i,bytes.i)
  Protected index.i
  Protected seedBytes.i
  Protected copyBytes.i
  Protected completed.i
  If rock_dma_pl330_ready=0 Or bytes<=0 Or (bytes & 3)<>0 Or (destination & 3)<>0 Or destination<0 Or destination>$100000000-bytes
    rock_dma_pl330_error=#ROCK_DMA_PL330_ERROR_ARGUMENT : ProcedureReturn 0
  EndIf
  seedBytes=bytes
  If seedBytes>#ROCK_DMA_PL330_FILL_SEED_BYTES : seedBytes=#ROCK_DMA_PL330_FILL_SEED_BYTES : EndIf
  For index=0 To seedBytes/4-1
    PokeL(destination+index*4,value & $FFFFFFFF)
  Next
  RockDmaPl330Barrier()
  completed=seedBytes
  rock_dma_pl330_completed_bytes=completed
  While completed<bytes
    copyBytes=completed
    If copyBytes>bytes-completed : copyBytes=bytes-completed : EndIf
    ; Each source span ends at or before this destination span begins.
    If RockDmaPl330Copy(destination+completed,destination,copyBytes)=0
      rock_dma_pl330_completed_bytes=completed+rock_dma_pl330_completed_bytes
      ProcedureReturn 0
    EndIf
    completed=completed+copyBytes
  Wend
  rock_dma_pl330_completed_bytes=completed
  ProcedureReturn 1
EndProcedure

; Board renderers use the generic DMA names so their policy does not depend on
; which controller implements the operation. Keep these wrappers deliberately
; thin: all bounds, progress telemetry and failure handling stay in PL330.
Procedure.i RockDmaCopy(destination.i,source.i,bytes.i)
  ProcedureReturn RockDmaPl330Copy(destination,source,bytes)
EndProcedure

Procedure.i RockDmaFill32(destination.i,value.i,bytes.i)
  ProcedureReturn RockDmaPl330Fill32(destination,value,bytes)
EndProcedure
