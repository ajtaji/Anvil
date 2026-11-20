XIncludeFile "Anvil/Kernel/Zentaji/code_sync.pbi"

Procedure CacheFlushRange(lo.i,hi.i)
 ZentajiCodeSync()
EndProcedure


Procedure ZentajiCmdCache()

 SkipSpace() : gWordAt=gPos : SkipWord() : gWordLen=gPos-gWordAt
 SkipSpace()
 If gLine[gPos]<>0 : PrintN("Usage: cache status or cache sync") : ProcedureReturn : EndIf
 If gWordLen=0 Or WordIs("show")<>0 Or WordIs("status")<>0
  PrintN("Zentaji data RAM is coherent. Modified instructions require a fence on each executing core.")
  Print("Core 0 instruction fences since counter clear: ") : PrintDec(PeekQ($FFFF000000070170)) : PrintNl()
 ElseIf WordIs("sync")<>0
  CacheFlushRange(0,0)
  PrintN("Core 0 data and instruction fences completed.")
 ElseIf WordIs("on")<>0 Or WordIs("off")<>0
  PrintN("Zentaji has no data-cache enable switch. Use cache sync to publish modified code on core 0.")
 Else
  PrintN("Usage: cache status or cache sync")
 EndIf
EndProcedure

