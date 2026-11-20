; File-backed autoboot policy for machines whose ROM reloads the monitor
; and probes guest RAM at startup. BootFileWait owns the countdown, full
; image hash, target validation, interruption and failed-boot limit.
Procedure CmdFileAutoboot()
 Protected savedPos.i=gPos,n.i,i.i,bytes.i,headerBytes.i
 Protected *name
 SkipSpace() : gWordAt=gPos : SkipWord() : gWordLen=gPos-gWordAt
 If gWordLen=0 Or WordIs("status")<>0 Or WordIs("clear")<>0
  SkipSpace()
  If gLine[gPos]<>0 : PrintN("!! autoboot status and clear take no other arguments.") : ProcedureReturn : EndIf
  gPos=savedPos : CmdBoot() : ProcedureReturn
 EndIf
 If WordIs("file")=0
  PrintN("Use autoboot file NAME.PMF, autoboot status, or autoboot clear.") : ProcedureReturn
 EndIf
 *name=ArgWord()
 If *name=0 Or ArgWord()<>0 : PrintN("!! autoboot file needs a single guest PMF filename.") : ProcedureReturn : EndIf
 While n<=30 And PeekA(*name+n)<>0 : n=n+1 : Wend
 If n=0 Or n>30 : PrintN("!! the boot filename must fit 30 bytes.") : ProcedureReturn : EndIf
 If HwStorageUp()=0 : PrintN("!! the boot medium is unavailable.") : ProcedureReturn : EndIf
 If HwFileOpen(*name)=0 : PrintN("!! the boot target could not be opened.") : ProcedureReturn : EndIf
 bytes=HwFileSize() : headerBytes=bytes
 If headerBytes>#PMF_HDR_LEN_V2 : headerBytes=#PMF_HDR_LEN_V2 : EndIf
 If headerBytes<#PMF_HDR_LEN_V1
  HwFileClose() : PrintN("!! the file is too short for a PMF header.") : ProcedureReturn
 EndIf
 For i=0 To #PMF_HDR_LEN_V2-1 : gPmfHdr[i]=0 : Next
 i=HwFileReadAt(0,@gPmfHdr[0],headerBytes) : HwFileClose()
 If i<>headerBytes Or PmfMagicOk(@gPmfHdr[0])=0 : PrintN("!! the boot target has no readable PMF header.") : ProcedureReturn : EndIf
 PmfParseAt(@gPmfHdr[0])
 If PmfCheckHeader(bytes)=0 : ProcedureReturn : EndIf
 If PmfCheckPlacement()=0 : ProcedureReturn : EndIf
 If SettingsLoad()=0 And SettingsLastError()<>#SET_ERR_NO_FILE : SettingsSayWhyNot() : ProcedureReturn : EndIf
 If SettingsSet(PmfKeyFile(),*name)=0 : SettingsSayWhyNot() : ProcedureReturn : EndIf
 ; Commit the selected file and its fresh failure counter in one save.
 If PmfSetFails(0)=0
  SettingsSayWhyNot() : SettingsLoad() : ProcedureReturn
 EndIf
 Print("Autoboot target saved: ") : UartWriteStr(*name) : PrintNl()
EndProcedure
