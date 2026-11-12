; Built-in editor and compiler shell. Anvil supplies input, files and verified
; payload entry. The generated program executes through Zentaji's CPU.
XIncludeFile "Zentaji/Forge/compiler.pbi"

Global Dim zfProgram.a[#ZF_SOURCE_BYTES]
Global Dim zfIncoming.a[#ZF_SOURCE_BYTES]
Global Dim zfImage.q[(#ZF_CODE_BYTES+#PMF_HDR_LEN_V2)/8]
Global zfProgramBytes.i

Procedure ZfDiagnostic()
 Print("!! Forge line ") : PrintDec(zfLine)
 Print(", column ") : PrintDec(zfPos-zfLineStart+1)
 Print(": ") : UartWriteStr(zfError) : PrintNl()
EndProcedure

Procedure.i ZfContainer(source.i,n.i)
 Protected header.i=@zfImage[0],code.i,bytes.i,load.i,stack.i,i.i
 code=header+#PMF_HDR_LEN_V2
 bytes=ZfCompile(source,n,code,#ZF_CODE_BYTES,0)
 If bytes=0 : ZfDiagnostic() : ProcedureReturn 0 : EndIf
 load=HwStageAddr()
 stack=((load+bytes+15)&-16)+HwPmfInitialStackBytes()
 If load=0 Or InPayload(load,stack-1)=0
  PrintN("!! Forge needs a payload window for the code and the initial stack.")
  ProcedureReturn 0
 EndIf
 For i=0 To #PMF_HDR_LEN_V2-8 Step 8 : PokeQ(header+i,0) : Next
 PokeQ(header+#PMF_OFF_MAGIC,$00544F4F42464D50)
 PokeL(header+#PMF_OFF_VERSION,#PMF_VERSION_V2)
 PokeL(header+#PMF_OFF_HDRLEN,#PMF_HDR_LEN_V2)
 PokeQ(header+#PMF_OFF_LOAD,load) : PokeQ(header+#PMF_OFF_ENTRY,load)
 PokeQ(header+#PMF_OFF_IMGLEN,bytes) : PokeQ(header+#PMF_OFF_BSSBASE,load+bytes)
 PokeL(header+#PMF_OFF_FLAGS,#PMF_FLAG_RETURNS)
 PokeL(header+#PMF_OFF_ARCH,#PMF_ARCH_ZENTAJI) : PokeL(header+#PMF_OFF_TARGET,#PMF_TARGET_ZENTAJI)
 PokeQ(header+#PMF_OFF_STACK,stack)
 Sha256Of(code,bytes,header+#PMF_OFF_SHA)
 ProcedureReturn #PMF_HDR_LEN_V2+bytes
EndProcedure

; The in-memory compiler emits a leaf with only ALU instructions, literal
; words and the return. Its registers are volatile under the Zentaji ABI.
; Enter only this compiler-owned buffer. Saved programs use Anvil's PMF loader.
Procedure ZfRun(source.i,n.i,immediate.i)
 Protected code.i=@zfImage[0]+#PMF_HDR_LEN_V2,value.q
 If ZfCompile(source,n,code,#ZF_CODE_BYTES,immediate)=0
  ZfDiagnostic()
  ProcedureReturn
 EndIf
 value=CallFunctionFast(code)
 Print("Forge result ") : PrintDec(value) : PrintNl()
EndProcedure

Procedure ZfStorageError()
 Print("!! Forge storage: ") : UartWriteStr(HwFileErrorText()) : PrintNl()
EndProcedure

Procedure.i ZfPath()
 Protected n.i=ParseStoragePath()
 SkipSpace()
 If n<1 Or gLine[gPos]<>0
  PrintN("!! Forge expects one storage path. Quote paths containing spaces.")
  ProcedureReturn 0
 EndIf
 ProcedureReturn 1
EndProcedure

Procedure ZfLoad()
 Protected bytes.i,got.i,i.i,c.i
 If HwFileOpen(@gName[0])=0 : ZfStorageError() : ProcedureReturn : EndIf
 bytes=HwFileSize()
 If bytes<0 Or bytes>#ZF_SOURCE_BYTES
  HwFileClose()
  PrintN("!! Forge source exceeds the 8192-byte editor limit.")
  ProcedureReturn
 EndIf
 If bytes>0 : got=HwFileReadAt(0,@zfIncoming[0],bytes) : EndIf
 If got<>bytes
  ZfStorageError() : HwFileClose() : ProcedureReturn
 EndIf
 HwFileClose()
 For i=0 To bytes-1
  c=zfIncoming[i]
  If (c<32 And c<>9 And c<>10 And c<>13) Or c>126
   PrintN("!! Forge source must use ASCII text.")
   ProcedureReturn
  EndIf
 Next
 For i=0 To bytes-1 : zfProgram[i]=zfIncoming[i] : Next
 zfProgramBytes=bytes
 Print("Forge loaded ") : PrintDec(bytes) : PrintN(" bytes")
EndProcedure

Procedure ZfList()
 Protected i.i,c.i
 While i<zfProgramBytes
  c=zfProgram[i]
  If c=13 Or c=10
   PrintNl()
   If c=13 And i+1<zfProgramBytes And zfProgram[i+1]=10 : i=i+1 : EndIf
  Else
   UartWrite(c)
  EndIf
  i=i+1
 Wend
 If i>0 And zfProgram[i-1]<>10 And zfProgram[i-1]<>13 : PrintNl() : EndIf
EndProcedure

Procedure ZfAppend(start.i)
 Protected n.i=gLineLen-start,i.i,separator.i,last.i
 If zfProgramBytes>0
  last=zfProgram[zfProgramBytes-1]
  separator=Bool(last<>10 And last<>13)
 EndIf
 If n<0 Or n+separator>=#ZF_SOURCE_BYTES-zfProgramBytes
  PrintN("!! Forge editor is full.")
  ProcedureReturn
 EndIf
 If separator<>0
  zfProgram[zfProgramBytes]=10
  zfProgramBytes=zfProgramBytes+1
 EndIf
 For i=0 To n-1 : zfProgram[zfProgramBytes+i]=gLine[start+i]&255 : Next
 zfProgram[zfProgramBytes+n]=10
 zfProgramBytes=zfProgramBytes+n+1
EndProcedure

Procedure ZfHelp()
 PrintN("Forge for Zentaji")
 PrintN("  print <integer expression>      compile and run an immediate expression")
 PrintN("  add <source>                    append a line to the program")
 PrintN("  list | new | run                view, clear or run the current program")
 PrintN("  load <path> | save <path>        read or write PureMetal source")
 PrintN("  compile <path.pmf>              write a Zentaji PMFBOOT image")
 PrintN("  exit                            return to Anvil")
 PrintN("Enter source lines directly at forge>. Use Procedure.q Main(),")
 PrintN("Protected name.q = expression, assignment, ProcedureReturn and EndProcedure.")
EndProcedure

Procedure.i ZfCommand(interactive.i)
 Protected start.i,n.i,pathBytes.i
 If gLineCtrlC<>0 : ProcedureReturn 1 : EndIf
 If gLineTrunc<>0 : PrintN("!! Forge input line was truncated.") : ProcedureReturn 1 : EndIf
 SkipSpace() : start=gPos
 While gLine[gPos]<>0 And gLine[gPos]<>32 And gLine[gPos]<>9 : gPos=gPos+1 : Wend
 gWordAt=start : gWordLen=gPos-start
 SkipSpace()
 If gWordLen=0 : ProcedureReturn 1 : EndIf
 If WordIs("print")<>0
  ZfRun(@gLine[0]+gPos,gLineLen-gPos,1)
 ElseIf WordIs("add")<>0
  ZfAppend(gPos)
 ElseIf WordIs("load")<>0
  If ZfPath()<>0 And HwStorageUp()<>0 : ZfLoad() : EndIf
 ElseIf WordIs("save")<>0
  If ZfPath()<>0 And HwStorageUp()<>0
   If HwFileWriteAll(@gName[0],@zfProgram[0],zfProgramBytes)=0 : ZfStorageError()
   Else : PrintN("Forge source saved") : EndIf
  EndIf
 ElseIf WordIs("compile")<>0
  If ZfPath()<>0 And HwStorageUp()<>0
   While gName[pathBytes]<>0 : pathBytes=pathBytes+1 : Wend
   If pathBytes<5 Or gName[pathBytes-4]<>46 Or ZfLower(gName[pathBytes-3])<>112 Or ZfLower(gName[pathBytes-2])<>109 Or ZfLower(gName[pathBytes-1])<>102
    PrintN("!! Forge output requires a .pmf path.")
   Else
    n=ZfContainer(@zfProgram[0],zfProgramBytes)
    If n>0
     If HwFileWriteAll(@gName[0],@zfImage[0],n)=0 : ZfStorageError()
     Else : Print("Forge wrote ") : PrintDec(n) : PrintN(" bytes") : EndIf
    EndIf
   EndIf
  EndIf
 ElseIf WordIs("list")<>0 Or WordIs("new")<>0 Or WordIs("run")<>0 Or WordIs("exit")<>0 Or WordIs("help")<>0
  If gLine[gPos]<>0
   PrintN("!! This Forge command takes no arguments.")
  ElseIf WordIs("list")<>0
   ZfList()
  ElseIf WordIs("new")<>0
   zfProgramBytes=0
  ElseIf WordIs("run")<>0
   ZfRun(@zfProgram[0],zfProgramBytes,0)
  ElseIf WordIs("exit")<>0
   ProcedureReturn 0
  Else
   ZfHelp()
  EndIf
 ElseIf interactive<>0
  ZfAppend(0)
 Else
  PrintN("!! Unknown Forge command. Type forge help.")
 EndIf
 ProcedureReturn 1
EndProcedure

Procedure CmdZentajiForge()
 SkipSpace()
 If gLine[gPos]<>0
  ZfCommand(0)
  ProcedureReturn
 EndIf
 PrintN("Zentaji PureMetal Forge. Type help for commands.")
 Repeat
  UartScreenStyle(#UART_SCREEN_STYLE_PROMPT)
  Print("forge> ")
  UartScreenStyle(#UART_SCREEN_STYLE_NORMAL)
  UartDrain()
  ReadLine()
  gPos=0
  OutBreakArm()
 Until ZfCommand(1)=0
EndProcedure
