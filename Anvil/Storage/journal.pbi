; Shared redo journal. Include Anvil/Core/crc.pbi before this file.
; The callbacks follow the FsSetRangeReader/Writer and FsSetBlockFlusher
; contracts. One owner serializes all writes to the volume. The backend
; must preserve completed flushes across reset and write a 4 KiB aligned
; range without modifying other ranges. A crash may tear the current range.
#FSJ_BYTES=4096
#FSJ_SECTORS=8
#FSJ_MAX_BLOCKS=16
#FSJ_MAGIC=$00314C4E4A464D50 ; PMFJNL1 and NUL
#FSJ_HEADER_CRC=#FSJ_BYTES-4
#FSJ_ENTRY=16
#FSJ_ENTRY_BYTES=16

#FSJ_RECOVER=1
#FSJ_READY=2
#FSJ_BUILD=3
#FSJ_E_STATE=1
#FSJ_E_RANGE=2
#FSJ_E_FULL=3
#FSJ_E_IO=4
#FSJ_E_CORRUPT=5
#FSJ_E_DUPLICATE=6
#FSJ_E_READONLY=7

Structure FsJournal
 reader.i
 writer.i
 flusher.i
 first.i
 limit.i                         ; exclusive
 log.i
 logLimit.i                      ; exclusive
 state.i
 uncertain.i                     ; failed operation may have left buffered writes
 error.i
 count.i
 home.q[#FSJ_MAX_BLOCKS]
 firstMarker.q[#FSJ_BYTES/8]
 secondMarker.q[#FSJ_BYTES/8]
 blocks.q[#FSJ_BYTES/8*#FSJ_MAX_BLOCKS]
EndStructure

Procedure.i fsjFail(*j.FsJournal,error.i)
 *j\error=error
 ProcedureReturn 0
EndProcedure

; The two marker blocks and a full transaction's payload are reserved.
; The caller obtains the volume bounds independently of journal contents.
; A missing writer and flusher admit only a clean read-only journal.
Procedure.i FsJournalBind(*j.FsJournal,first.i,limit.i,log.i,reader.i,writer.i,flusher.i)
 Protected span.i=(#FSJ_MAX_BLOCKS+2)*#FSJ_SECTORS
 If *j=0 : ProcedureReturn 0 : EndIf
 If *j\state<>0 : ProcedureReturn fsjFail(*j,#FSJ_E_STATE) : EndIf
 If reader=0 Or Bool(writer=0)<>Bool(flusher=0) Or first<0 Or limit<=first Or log<first
  ProcedureReturn fsjFail(*j,#FSJ_E_RANGE)
 EndIf
 If ((first|limit|log)&(#FSJ_SECTORS-1))<>0 Or log>limit Or span>limit-log
  ProcedureReturn fsjFail(*j,#FSJ_E_RANGE)
 EndIf
 *j\reader=reader : *j\writer=writer : *j\flusher=flusher
 *j\first=first : *j\limit=limit : *j\log=log : *j\logLimit=log+span
 *j\state=#FSJ_RECOVER : *j\uncertain=0 : *j\error=0
 ProcedureReturn 1
EndProcedure

Procedure.i fsjHomeValid(*j.FsJournal,lba.q)
 If lba<*j\first Or lba>*j\limit-#FSJ_SECTORS Or (lba&(#FSJ_SECTORS-1))<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool(lba<*j\log Or lba>=*j\logLimit)
EndProcedure

Procedure fsjZero(marker.i)
 Protected at.i
 For at=0 To #FSJ_BYTES-8 Step 8 : PokeQ(marker+at,0) : Next
EndProcedure

Procedure.i fsjRead(*j.FsJournal,lba.i,buffer.i)
 ProcedureReturn CallFunctionFast(*j\reader,lba,#FSJ_SECTORS,buffer)
EndProcedure

Procedure.i fsjWrite(*j.FsJournal,lba.i,buffer.i)
 ProcedureReturn CallFunctionFast(*j\writer,lba,#FSJ_SECTORS,buffer)
EndProcedure

Procedure.i fsjFlush(*j.FsJournal)
 ProcedureReturn CallFunctionFast(*j\flusher)
EndProcedure

; Both copies use the same bytes. At most one marker may be torn by a
; write interruption. A good copy commits the redo record. If neither
; copy is good, at least one must be blank before recovery may discard it.
Procedure.i fsjMarker(marker.i)
 Protected at.i,count.i
 If PeekQ(marker)=#FSJ_MAGIC And PeekL(marker+12)=0
  count=PeekL(marker+8)
  If count>=1 And count<=#FSJ_MAX_BLOCKS
   If Crc32(marker,#FSJ_HEADER_CRC)=(PeekL(marker+#FSJ_HEADER_CRC)&$FFFFFFFF)
    ProcedureReturn count
   EndIf
  EndIf
 EndIf
 For at=0 To #FSJ_BYTES-8 Step 8
  If PeekQ(marker+at)<>0 : ProcedureReturn -1 : EndIf
 Next
 ProcedureReturn 0
EndProcedure

; Erasing the two markers is ordered and begins only once home blocks are
; durable. An error keeps the handle in recovery state, even if the last
; write reached disk before the error was reported.
Procedure.i fsjClear(*j.FsJournal)
 Protected marker.i=@*j\firstMarker[0]
 fsjZero(marker)
 If fsjWrite(*j,*j\log,marker)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 If fsjFlush(*j)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 If fsjWrite(*j,*j\log+#FSJ_SECTORS,marker)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 If fsjFlush(*j)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i fsjApply(*j.FsJournal)
 Protected index.i,source.i=@*j\blocks[0]
 For index=0 To *j\count-1
  If fsjWrite(*j,*j\home[index],source+index*#FSJ_BYTES)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 Next
 If fsjFlush(*j)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 ProcedureReturn fsjClear(*j)
EndProcedure

; Validate the complete record and every logged block before touching any
; home block. Replay is idempotent and may itself be interrupted.
Procedure.i FsJournalRecover(*j.FsJournal)
 Protected first.i,second.i,a.i,b.i,index.i,prior.i,at.i,source.i,lba.q
 If *j\state<>#FSJ_RECOVER : ProcedureReturn fsjFail(*j,#FSJ_E_STATE) : EndIf
 first=@*j\firstMarker[0] : second=@*j\secondMarker[0]
 If fsjRead(*j,*j\log,first)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 If fsjRead(*j,*j\log+#FSJ_SECTORS,second)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 a=fsjMarker(first) : b=fsjMarker(second)
 If a<0 And b<0 : ProcedureReturn fsjFail(*j,#FSJ_E_CORRUPT) : EndIf
 If *j\writer=0 And (a<>0 Or b<>0) : ProcedureReturn fsjFail(*j,#FSJ_E_READONLY) : EndIf
 If a>0 And b>0
  For at=0 To #FSJ_BYTES-8 Step 8
   If PeekQ(first+at)<>PeekQ(second+at) : ProcedureReturn fsjFail(*j,#FSJ_E_CORRUPT) : EndIf
  Next
 EndIf
 If a>0 Or b>0
  If a<=0 : first=second : a=b : EndIf
  *j\count=a
  For index=0 To a-1
   at=first+#FSJ_ENTRY+index*#FSJ_ENTRY_BYTES
   lba=PeekQ(at)
   If fsjHomeValid(*j,lba)=0 Or PeekL(at+12)<>0 : ProcedureReturn fsjFail(*j,#FSJ_E_CORRUPT) : EndIf
   For prior=0 To index-1
    If *j\home[prior]=lba : ProcedureReturn fsjFail(*j,#FSJ_E_CORRUPT) : EndIf
   Next
   *j\home[index]=lba
   source=@*j\blocks[0]+index*#FSJ_BYTES
   If fsjRead(*j,*j\log+(index+2)*#FSJ_SECTORS,source)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
   If Crc32(source,#FSJ_BYTES)<>(PeekL(at+8)&$FFFFFFFF) : ProcedureReturn fsjFail(*j,#FSJ_E_CORRUPT) : EndIf
  Next
  *j\uncertain=1
  ; A failed flush may leave the marker visible only in the device cache.
  If fsjFlush(*j)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
  If fsjApply(*j)=0 : ProcedureReturn 0 : EndIf
 ElseIf a<0 Or b<0
  *j\uncertain=1
  If fsjClear(*j)=0 : ProcedureReturn 0 : EndIf
 ElseIf *j\uncertain<>0
  ; Blank reads can be cached clears. The next transaction must not replace
  ; the logged payload while an earlier marker could survive on disk.
  If fsjFlush(*j)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 EndIf
 *j\state=#FSJ_READY : *j\uncertain=0 : *j\count=0 : *j\error=0
 ProcedureReturn 1
EndProcedure

Procedure.i FsJournalBegin(*j.FsJournal)
 If *j\state<>#FSJ_READY : ProcedureReturn fsjFail(*j,#FSJ_E_STATE) : EndIf
 If *j\writer=0 : ProcedureReturn fsjFail(*j,#FSJ_E_READONLY) : EndIf
 *j\state=#FSJ_BUILD : *j\count=0 : *j\error=0
 ProcedureReturn 1
EndProcedure

Procedure.i FsJournalAbort(*j.FsJournal)
 If *j\state<>#FSJ_BUILD : ProcedureReturn fsjFail(*j,#FSJ_E_STATE) : EndIf
 *j\state=#FSJ_READY : *j\count=0 : *j\error=0
 ProcedureReturn 1
EndProcedure

; Each home address is staged once. Callers combine edits to the same
; block before staging. The snapshot is independent of caller memory.
Procedure.i FsJournalAdd(*j.FsJournal,lba.i,source.i)
 Protected index.i,at.i,target.i
 If *j\state<>#FSJ_BUILD : ProcedureReturn fsjFail(*j,#FSJ_E_STATE) : EndIf
 If source=0 Or fsjHomeValid(*j,lba)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_RANGE) : EndIf
 For index=0 To *j\count-1
  If *j\home[index]=lba : ProcedureReturn fsjFail(*j,#FSJ_E_DUPLICATE) : EndIf
 Next
 If *j\count>=#FSJ_MAX_BLOCKS : ProcedureReturn fsjFail(*j,#FSJ_E_FULL) : EndIf
 target=@*j\blocks[0]+*j\count*#FSJ_BYTES
 For at=0 To #FSJ_BYTES-1 : PokeA(target+at,PeekA(source+at)) : Next
 *j\home[*j\count]=lba : *j\count=*j\count+1 : *j\error=0
 ProcedureReturn 1
EndProcedure

Procedure.i FsJournalCommit(*j.FsJournal)
 Protected index.i,at.i,source.i,marker.i=@*j\firstMarker[0]
 If *j\state<>#FSJ_BUILD Or *j\count=0 : ProcedureReturn fsjFail(*j,#FSJ_E_STATE) : EndIf
 *j\state=#FSJ_RECOVER : *j\uncertain=1
 fsjZero(marker)
 PokeQ(marker,#FSJ_MAGIC) : PokeL(marker+8,*j\count)
 For index=0 To *j\count-1
  source=@*j\blocks[0]+index*#FSJ_BYTES
  at=marker+#FSJ_ENTRY+index*#FSJ_ENTRY_BYTES
  PokeQ(at,*j\home[index]) : PokeL(at+8,Crc32(source,#FSJ_BYTES))
  If fsjWrite(*j,*j\log+(index+2)*#FSJ_SECTORS,source)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 Next
 If fsjFlush(*j)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 PokeL(marker+#FSJ_HEADER_CRC,Crc32(marker,#FSJ_HEADER_CRC))
 If fsjWrite(*j,*j\log,marker)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 If fsjFlush(*j)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 If fsjWrite(*j,*j\log+#FSJ_SECTORS,marker)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 If fsjFlush(*j)=0 : ProcedureReturn fsjFail(*j,#FSJ_E_IO) : EndIf
 If fsjApply(*j)=0 : ProcedureReturn 0 : EndIf
 *j\state=#FSJ_READY : *j\uncertain=0 : *j\count=0 : *j\error=0
 ProcedureReturn 1
EndProcedure
