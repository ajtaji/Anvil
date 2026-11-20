; A module can claim the first spare serial port. The ROM descriptor is
; authoritative. UART0 stays with Anvil even when no host serial peer exists.
Procedure.i ZentajiModuleUart()
 Protected table.i=$FFFF000000010000,bytes.i=PeekL(table+12),count.i=PeekL(table+16),i.i,p.i
 If bytes<64 Or bytes>65536 Or count<1 Or count>(bytes-64)/64 : ProcedureReturn 0 : EndIf
 For i=0 To count-1
  p=table+64+i*64
  If PeekQ(p+8)=$FFFF000000110000 And PeekQ(p+16)=65536
   If (PeekQ($FFFF000000110000)&$FFFFFFFF)=$01010011 : ProcedureReturn $FFFF000000110000 : EndIf
  EndIf
 Next
 ProcedureReturn 0
EndProcedure
Procedure.i HwDevCount() : ProcedureReturn Bool(ZentajiModuleUart()<>0) : EndProcedure
Procedure.i HwDevIdAddr(i.i)
 If i=0 And HwDevCount()<>0 : ProcedureReturn "zentaji,serial-v1" : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i HwDevSeam(i.i)
 If i=0 And HwDevCount()<>0 : ProcedureReturn #SVCCAP_UART : EndIf
 ProcedureReturn -1
EndProcedure
Procedure.i HwDevToken(i.i)
 If i=0 : ProcedureReturn ZentajiModuleUart() : EndIf
 ProcedureReturn 0
EndProcedure
Procedure HwDevSay(i.i)
 If i=0 And HwDevCount()<>0 : Print("Zentaji serial port 1") : EndIf
EndProcedure
Procedure.i HwSeamCore(id.i) : ProcedureReturn 0 : EndProcedure
Procedure.i HwSeamPossible(id.i) : ProcedureReturn Bool(id=#SVCCAP_UART And HwDevCount()<>0) : EndProcedure
ProcedureNaked.i HwModCodeSync(base.i,bytes.i)
 ASM
  FENCE.full
  FENCE.IFENCE
  LI r1,1
  JR r254
 EndASM
EndProcedure
