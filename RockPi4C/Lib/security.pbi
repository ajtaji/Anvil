; RK3399 BootROM leaves DDR/SRAM security regions enabled for its own first
; stage.  Anvil owns EL3 after direct-SD entry, so release those regions before
; any peripheral is allowed to DMA.  This is the same PMUSGRF initialization
; performed by mainline U-Boot arch_cpu_init() for an RK3399 XPL build.

#ROCK_PMUSGRF = $FF330000
#ROCK_PMUSGRF_DDR_RGN_CON16 = $0040
#ROCK_PMUSGRF_SLV_SECURE_CON4 = $E3D4
#ROCK_PMUSGRF_DDR_REGION_MASK = $01FF
#ROCK_PMUSGRF_SLV_SECURE_MASK = $2000

Global rock_security_ddr_before.i
Global rock_security_ddr_after.i
Global rock_security_slave_before.i
Global rock_security_slave_after.i

Procedure.i RockSecurityReleaseDma()
  rock_security_ddr_before=PeekL(#ROCK_PMUSGRF+#ROCK_PMUSGRF_DDR_RGN_CON16) & $FFFFFFFF
  rock_security_slave_before=PeekL(#ROCK_PMUSGRF+#ROCK_PMUSGRF_SLV_SECURE_CON4) & $FFFFFFFF
  ; RK3399 GRF/SGRF fields use upper-halfword write masks.  Clear DDR region
  ; bits 0..8 and slave-security bit 13 while preserving every other field.
  PokeL(#ROCK_PMUSGRF+#ROCK_PMUSGRF_DDR_RGN_CON16,#ROCK_PMUSGRF_DDR_REGION_MASK << 16)
  PokeL(#ROCK_PMUSGRF+#ROCK_PMUSGRF_SLV_SECURE_CON4,#ROCK_PMUSGRF_SLV_SECURE_MASK << 16)
  ASM
    dsb sy
  ENDASM
  rock_security_ddr_after=PeekL(#ROCK_PMUSGRF+#ROCK_PMUSGRF_DDR_RGN_CON16) & $FFFFFFFF
  rock_security_slave_after=PeekL(#ROCK_PMUSGRF+#ROCK_PMUSGRF_SLV_SECURE_CON4) & $FFFFFFFF
  If (rock_security_ddr_after & #ROCK_PMUSGRF_DDR_REGION_MASK)<>0
    ProcedureReturn 0
  EndIf
  If (rock_security_slave_after & #ROCK_PMUSGRF_SLV_SECURE_MASK)<>0
    ProcedureReturn 0
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure RockSecurityTelemetry()
  If rock_uart_ready=0
    ProcedureReturn
  EndIf
  RockUartText("RK3399 DMA SECURITY DDR=")
  RockDisplayHexLong(rock_security_ddr_before)
  RockUartByte(62)
  RockDisplayHexLong(rock_security_ddr_after)
  RockUartText(" SLAVE=")
  RockDisplayHexLong(rock_security_slave_before)
  RockUartByte(62)
  RockDisplayHexLong(rock_security_slave_after)
  RockUartByte(13) : RockUartByte(10)
EndProcedure
