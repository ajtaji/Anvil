; Shared journaled volume. A board selects it through the filesystem facade
; and supplies 512-byte range I/O and a durable 4 KiB write/flush adapter.
XIncludeFile "Anvil/Core/crc.pbi"
XIncludeFile "Anvil/Storage/journal.pbi"

#JF_PARTITION=$DA
#JF_MAGIC=$003153464C564E41 ; ANVLFS1 and NUL
#JF_SLOTS=128
#JF_ENTRY=512
#JF_NAME=24
#JF_NAME_MAX=255
#JF_CRC=#JF_ENTRY-4
#JF_FILE=1
#JF_DIR=2
#JF_LOG=8
#JF_TABLE=#JF_LOG+(#FSJ_MAX_BLOCKS+2)*#FSJ_SECTORS
#JF_DATA=#JF_TABLE+#JF_SLOTS

#JF_E_IO=1
#JF_E_FORMAT=2
#JF_E_JOURNAL=3
#JF_E_NAME=4
#JF_E_MISSING=5
#JF_E_EXISTS=6
#JF_E_TYPE=7
#JF_E_FULL=8
#JF_E_RO=9
#JF_E_CURSOR=10
#JF_E_NOT_EMPTY=11
#JF_E_CYCLE=12

Global jfJournal.FsJournal
Global Dim jfEntries.q[#JF_SLOTS*#JF_ENTRY/8]
Global Dim jfBlock.q[#FSJ_BYTES/8]
Global jfFirst.i,jfLimit.i,jfReader.i,jfWriter.i,jfFlusher.i
Global jfFile.i,jfPosition.i,jfDir.i,jfNext.i,jfCurrent.i
Global jfParent.i,jfName.i,jfNameLength.i,jfError.i,jfNeedsReload.i

Procedure.i jfFail(error.i)
 jfError=error
 ProcedureReturn 0
EndProcedure

Procedure jfCopy(dst.i,src.i,length.i)
 Protected i.i
 For i=0 To length-1 : PokeA(dst+i,PeekA(src+i)) : Next
EndProcedure

Procedure.i jfEqual(left.i,right.i,length.i)
 Protected i.i
 For i=0 To length-1
  If PeekA(left+i)<>PeekA(right+i) : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn 1
EndProcedure

Procedure.i jfEntry(id.i)
 ProcedureReturn @jfEntries[0]+(id-1)*#JF_ENTRY
EndProcedure

Procedure.i jfSectors(length.i)
 ProcedureReturn ((length+#FSJ_BYTES-1)/#FSJ_BYTES)*#FSJ_SECTORS
EndProcedure

; Case-sensitive UTF-8. Reject malformed encodings, path delimiters, ASCII
; control bytes and the two reserved dot components.
Procedure.i jfValidName(name.i,length.i)
 Protected i.i,c.i,trail.i,lo.i,hi.i
 If length<1 Or length>#JF_NAME_MAX : ProcedureReturn 0 : EndIf
 If PeekA(name)=46
  If length=1 : ProcedureReturn 0 : EndIf
  If length=2 And PeekA(name+1)=46 : ProcedureReturn 0 : EndIf
 EndIf
 While i<length
  c=PeekA(name+i) & 255 : i=i+1
  If c<32 Or c=127 Or c=47 Or c=58 Or c=92 : ProcedureReturn 0 : EndIf
  If c>=128
   lo=$80 : hi=$BF
   Select c
    Case $C2 To $DF : trail=1
    Case $E0 To $EF
     trail=2
     If c=$E0 : lo=$A0 : EndIf
     If c=$ED : hi=$9F : EndIf
    Case $F0 To $F4
     trail=3
     If c=$F0 : lo=$90 : EndIf
     If c=$F4 : hi=$8F : EndIf
    Default : ProcedureReturn 0
   EndSelect
   If trail>length-i : ProcedureReturn 0 : EndIf
   While trail>0
    c=PeekA(name+i) & 255
    If c<lo Or c>hi : ProcedureReturn 0 : EndIf
    lo=$80 : hi=$BF : trail=trail-1 : i=i+1
   Wend
  EndIf
 Wend
 ProcedureReturn 1
EndProcedure

Procedure.i jfFind(parent.i,name.i,length.i)
 Protected id.i,entry.i
 For id=1 To #JF_SLOTS
  entry=jfEntry(id)
  If PeekA(entry)<>0 And PeekW(entry+2)=parent And PeekW(entry+4)=length
   If jfEqual(entry+#JF_NAME,name,length)<>0 : ProcedureReturn id : EndIf
  EndIf
 Next
 ProcedureReturn 0
EndProcedure

Procedure.i jfValidate()
 Protected id.i,entry.i,kind.i,parent.i,length.i,start.i,span.i,bytes.i
 Protected other.i,prev.i,ancestor.i,depth.i,prevStart.i,prevSpan.i
 For id=1 To #JF_SLOTS
  entry=jfEntry(id) : kind=PeekA(entry)
  If kind=0
   For other=0 To #JF_ENTRY-8 Step 8
    If PeekQ(entry+other)<>0 : ProcedureReturn 0 : EndIf
   Next
  Else
   If kind<>#JF_FILE And kind<>#JF_DIR : ProcedureReturn 0 : EndIf
   If Crc32(entry,#JF_CRC)<>(PeekL(entry+#JF_CRC)&$FFFFFFFF) : ProcedureReturn 0 : EndIf
   parent=PeekW(entry+2) : length=PeekW(entry+4)
   If parent<0 Or parent>#JF_SLOTS Or jfValidName(entry+#JF_NAME,length)=0 : ProcedureReturn 0 : EndIf
   If jfFind(parent,entry+#JF_NAME,length)<>id : ProcedureReturn 0 : EndIf
   ancestor=parent : depth=0
   While ancestor<>0
    If ancestor<1 Or ancestor>#JF_SLOTS Or ancestor=id Or depth>=#JF_SLOTS : ProcedureReturn 0 : EndIf
    prev=jfEntry(ancestor)
    If PeekA(prev)<>#JF_DIR : ProcedureReturn 0 : EndIf
    ancestor=PeekW(prev+2) : depth=depth+1
   Wend
   start=PeekQ(entry+8) : bytes=PeekQ(entry+16)
   If bytes<0 Or bytes>(jfLimit-jfFirst-#JF_DATA)*512 : ProcedureReturn 0 : EndIf
   If bytes=0
    If start<>0 : ProcedureReturn 0 : EndIf
   Else
    If kind<>#JF_FILE Or start<#JF_DATA Or start>jfLimit-jfFirst Or (start&7)<>0 : ProcedureReturn 0 : EndIf
    span=jfSectors(bytes)
    If span>jfLimit-jfFirst-start : ProcedureReturn 0 : EndIf
    For other=1 To id-1
     prev=jfEntry(other) : prevStart=PeekQ(prev+8) : prevSpan=jfSectors(PeekQ(prev+16))
     If prevSpan<>0 And start<prevStart+prevSpan And prevStart<start+span : ProcedureReturn 0 : EndIf
    Next
   EndIf
  EndIf
 Next
 ProcedureReturn 1
EndProcedure

Procedure jfReset()
 jfFirst=0 : jfFile=0 : jfPosition=0 : jfCurrent=0 : jfDir=-1
 FsJournalUnbind(@jfJournal) : jfNeedsReload=0
EndProcedure

; Return 0 for another format, 1 for a mounted journal volume, -1 for
; an I/O error or invalid journal volume. A selected partition owns recovery.
Procedure.i JfTryMount(partition.i,capacity.i,reader.i,writer.i,flusher.i)
 Protected buffer.i=@jfBlock[0],entry.i,first.i,sectors.i,log.i
 Protected slot.i,otherStart.i,otherSectors.i
 jfReset() : jfError=0
 If reader=0 Or capacity<1 Or partition<1 Or partition>4 : ProcedureReturn 0 : EndIf
 If CallFunctionFast(reader,0,1,buffer)=0 : jfFail(#JF_E_IO) : ProcedureReturn -1 : EndIf
 entry=buffer+446+(partition-1)*16
 If (PeekW(buffer+510)&$FFFF)<>$AA55 Or PeekA(entry+4)<>#JF_PARTITION : ProcedureReturn 0 : EndIf
 first=PeekL(entry+8)&$FFFFFFFF : sectors=PeekL(entry+12)&$FFFFFFFF
 If first<8 Or (first&7)<>0 Or (sectors&7)<>0 Or first>capacity Or sectors>capacity-first Or sectors<#JF_DATA+8
  jfFail(#JF_E_FORMAT) : ProcedureReturn -1
 EndIf
 For slot=1 To 4
  If slot=partition : Continue : EndIf
  entry=buffer+446+(slot-1)*16
  If PeekA(entry+4)=0 : Continue : EndIf
  otherStart=PeekL(entry+8)&$FFFFFFFF : otherSectors=PeekL(entry+12)&$FFFFFFFF
  If otherSectors>0 And first<otherStart+otherSectors And otherStart<first+sectors
   jfFail(#JF_E_FORMAT) : ProcedureReturn -1
  EndIf
 Next
 If CallFunctionFast(reader,first,#FSJ_SECTORS,buffer)=0 : jfFail(#JF_E_IO) : ProcedureReturn -1 : EndIf
 If PeekQ(buffer)<>#JF_MAGIC Or PeekQ(buffer+8)<>sectors Or Crc32(buffer,#FSJ_HEADER_CRC)<>(PeekL(buffer+#FSJ_HEADER_CRC)&$FFFFFFFF)
  jfFail(#JF_E_FORMAT) : ProcedureReturn -1
 EndIf
 log=first+#JF_LOG
 If flusher<>0
  If CallFunctionFast(flusher)=0 : jfFail(#JF_E_IO) : ProcedureReturn -1 : EndIf
 EndIf
 ; This binding admits redo destinations in the metadata table only.
 If FsJournalBind(@jfJournal,log,first+#JF_DATA,log,reader,writer,flusher)=0 Or FsJournalRecover(@jfJournal)=0
  jfFail(#JF_E_JOURNAL) : ProcedureReturn -1
 EndIf
 If CallFunctionFast(reader,first+#JF_TABLE,#JF_SLOTS,@jfEntries[0])=0
  jfFail(#JF_E_IO) : ProcedureReturn -1
 EndIf
 jfFirst=first : jfLimit=first+sectors
 If jfValidate()=0 : jfReset() : jfFail(#JF_E_FORMAT) : ProcedureReturn -1 : EndIf
 jfReader=reader : jfWriter=writer : jfFlusher=flusher
 ProcedureReturn 1
EndProcedure

Procedure.i jfReady()
 jfError=0
 If jfFirst=0 Or jfJournal\state<>#FSJ_READY Or jfNeedsReload<>0 : ProcedureReturn jfFail(#JF_E_JOURNAL) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i JfFlush()
 If jfFirst<>0 And jfNeedsReload<>0
  If jfFile<>0 : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
  If jfJournal\state=#FSJ_RECOVER
   If FsJournalRecover(@jfJournal)=0 : ProcedureReturn jfFail(#JF_E_JOURNAL) : EndIf
  EndIf
  If CallFunctionFast(jfReader,jfFirst+#JF_TABLE,#JF_SLOTS,@jfEntries[0])=0 : ProcedureReturn jfFail(#JF_E_IO) : EndIf
  If jfValidate()=0 : ProcedureReturn jfFail(#JF_E_FORMAT) : EndIf
  jfDir=-1 : jfCurrent=0 : jfNeedsReload=0
 EndIf
 If jfReady()=0 : ProcedureReturn 0 : EndIf
 If jfFlusher<>0
  If CallFunctionFast(jfFlusher)=0 : ProcedureReturn jfFail(#JF_E_IO) : EndIf
 EndIf
 ProcedureReturn 1
EndProcedure

; Resolve into a slot, with zero representing the implicit root. For a
; missing final component, leave its validated name and parent for create.
Procedure.i jfResolve(path.i)
 Protected parent.i,id.i,name.i,length.i,c.i
 jfName=0
 If jfReady()=0 : ProcedureReturn -1 : EndIf
 If path=0 : jfFail(#JF_E_NAME) : ProcedureReturn -1 : EndIf
 Repeat
  c=PeekA(path)
  While c=47 Or c=92 : path=path+1 : c=PeekA(path) : Wend
  If c=0 : ProcedureReturn parent : EndIf
  name=path : length=0
  While c<>0 And c<>47 And c<>92
   path=path+1 : length=length+1
   If length>#JF_NAME_MAX : jfFail(#JF_E_NAME) : ProcedureReturn -1 : EndIf
   c=PeekA(path)
  Wend
  If jfValidName(name,length)=0 : jfFail(#JF_E_NAME) : ProcedureReturn -1 : EndIf
  id=jfFind(parent,name,length)
  While c=47 Or c=92 : path=path+1 : c=PeekA(path) : Wend
  If c=0
   jfParent=parent : jfName=name : jfNameLength=length
   If id<>0 : ProcedureReturn id : EndIf
  ElseIf id<>0
   If PeekA(jfEntry(id))<>#JF_DIR : jfFail(#JF_E_TYPE) : ProcedureReturn -1 : EndIf
   parent=id
  EndIf
  If id=0 : jfFail(#JF_E_MISSING) : ProcedureReturn -1 : EndIf
 ForEver
EndProcedure

Procedure.i jfCanWrite(armed.i)
 If jfReady()=0 : ProcedureReturn 0 : EndIf
 If armed=0 Or jfWriter=0 : ProcedureReturn jfFail(#JF_E_RO) : EndIf
 ProcedureReturn 1
EndProcedure

; Stage a metadata page in scratch. Publish the in-memory entry only after
; the journal commits. After an uncertain I/O failure require a fresh mount.
Procedure.i jfStage(id.i)
 Protected at.i=((id-1)/8)*#FSJ_BYTES
 jfCopy(@jfBlock[0],@jfEntries[0]+at,#FSJ_BYTES)
 ProcedureReturn @jfBlock[0]+((id-1)&7)*#JF_ENTRY
EndProcedure

Procedure.i jfPublish(id.i,entry.i)
 Protected at.i=((id-1)/8)*#FSJ_BYTES
 If PeekA(entry)<>0 : PokeL(entry+#JF_CRC,Crc32(entry,#JF_CRC)) : EndIf
 If FsJournalBegin(@jfJournal)=0 : ProcedureReturn jfFail(#JF_E_JOURNAL) : EndIf
 If FsJournalAdd(@jfJournal,jfFirst+#JF_TABLE+at/512,@jfBlock[0])=0
  FsJournalAbort(@jfJournal)
  ProcedureReturn jfFail(#JF_E_JOURNAL)
 EndIf
 If FsJournalCommit(@jfJournal)=0
  jfNeedsReload=1
  ProcedureReturn jfFail(#JF_E_JOURNAL)
 EndIf
 jfCopy(jfEntry(id),entry,#JF_ENTRY)
 jfCurrent=0 : jfError=0
 ProcedureReturn 1
EndProcedure

Procedure jfStoreName(entry.i)
 Protected at.i
 For at=#JF_NAME To #JF_NAME+#JF_NAME_MAX-1 : PokeA(entry+at,0) : Next
 PokeW(entry+2,jfParent) : PokeW(entry+4,jfNameLength)
 jfCopy(entry+#JF_NAME,jfName,jfNameLength)
EndProcedure

Procedure.i JfCreate(path.i,kind.i,armed.i)
 Protected id.i,entry.i
 If jfCanWrite(armed)=0 : ProcedureReturn 0 : EndIf
 If jfFile<>0 : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 If jfResolve(path)>=0 : ProcedureReturn jfFail(#JF_E_EXISTS) : EndIf
 If jfName=0 : ProcedureReturn 0 : EndIf
 For id=1 To #JF_SLOTS
  If PeekA(jfEntry(id))=0
   entry=jfStage(id) : PokeA(entry,kind) : jfStoreName(entry)
   If jfPublish(id,entry)=0 : ProcedureReturn 0 : EndIf
   If kind=#JF_FILE : jfFile=id : jfPosition=0 : EndIf
   ProcedureReturn 1
  EndIf
 Next
 ProcedureReturn jfFail(#JF_E_FULL)
EndProcedure

Procedure.i JfOpen(path.i)
 Protected id.i
 If jfFile<>0 : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 id=jfResolve(path)
 If id<0 : ProcedureReturn 0 : EndIf
 If id=0 Or PeekA(jfEntry(id))<>#JF_FILE : ProcedureReturn jfFail(#JF_E_TYPE) : EndIf
 jfFile=id : jfPosition=0
 ProcedureReturn 1
EndProcedure

Procedure.i jfOpenReady()
 If jfReady()=0 : ProcedureReturn 0 : EndIf
 If jfFile=0 : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i JfSize()
 If jfOpenReady()=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn PeekQ(jfEntry(jfFile)+16)
EndProcedure

Procedure.i JfSeek(position.i)
 If jfOpenReady()=0 : ProcedureReturn 0 : EndIf
 If position<0 Or position>JfSize() : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 jfPosition=position
 ProcedureReturn 1
EndProcedure

Procedure.i JfRead(dst.i,count.i)
 Protected length.i,start.i,position.i,offset.i,chunk.i,done.i
 If jfOpenReady()=0 : ProcedureReturn -1 : EndIf
 If count<0 Or (count>0 And dst=0) : jfFail(#JF_E_CURSOR) : ProcedureReturn -1 : EndIf
 length=JfSize()-jfPosition
 If count>length : count=length : EndIf
 start=jfFirst+PeekQ(jfEntry(jfFile)+8)
 While done<count
  position=jfPosition+done : offset=position & (#FSJ_BYTES-1)
  If offset=0 And count-done>=#FSJ_BYTES
   chunk=((count-done)/#FSJ_BYTES)*#FSJ_BYTES
   If CallFunctionFast(jfReader,start+position/512,chunk/512,dst+done)=0
    jfFail(#JF_E_IO) : ProcedureReturn -1
   EndIf
  Else
   chunk=#FSJ_BYTES-offset
   If chunk>count-done : chunk=count-done : EndIf
   If CallFunctionFast(jfReader,start+(position-offset)/512,#FSJ_SECTORS,@jfBlock[0])=0
    jfFail(#JF_E_IO) : ProcedureReturn -1
   EndIf
   jfCopy(dst+done,@jfBlock[0]+offset,chunk)
  EndIf
  done=done+chunk
 Wend
 jfPosition=jfPosition+done
 ProcedureReturn done
EndProcedure

; Find a contiguous free extent without releasing any existing allocation.
Procedure.i jfAllocate(span.i)
 Protected start.i=#JF_DATA,endAt.i,id.i,entry.i,other.i,otherEnd.i
 While span<=jfLimit-jfFirst-start
  endAt=start+span
  For id=1 To #JF_SLOTS
   entry=jfEntry(id) : other=PeekQ(entry+8)
   If other<>0
    otherEnd=other+jfSectors(PeekQ(entry+16))
    If other<endAt And start<otherEnd : start=otherEnd : Break : EndIf
   EndIf
  Next
  If id>#JF_SLOTS : ProcedureReturn start : EndIf
 Wend
 ProcedureReturn 0
EndProcedure

; Replace a file by writing its new extent, flushing it, then publishing the
; pointer and length. keep is the old prefix to copy before applying a patch.
Procedure.i jfReplace(length.i,keep.i,src.i,position.i,count.i,armed.i)
 Protected entry.i,old.i,start.i,span.i,at.i,last.i,fromAt.i,toAt.i,buffer.i=@jfBlock[0]
 If jfCanWrite(armed)=0 : ProcedureReturn 0 : EndIf
 If length<0 Or length>(jfLimit-jfFirst-#JF_DATA)*512 : ProcedureReturn jfFail(#JF_E_FULL) : EndIf
 If length>0
  span=jfSectors(length) : start=jfAllocate(span)
  If start=0 : ProcedureReturn jfFail(#JF_E_FULL) : EndIf
  old=jfFirst+PeekQ(jfEntry(jfFile)+8)
  For at=0 To span*512-1 Step #FSJ_BYTES
   last=at+#FSJ_BYTES
   If at>=position And last<=position+count
    If CallFunctionFast(jfWriter,jfFirst+start+at/512,#FSJ_SECTORS,src+at-position)=0 : ProcedureReturn jfFail(#JF_E_IO) : EndIf
    Continue
   EndIf
   If at<keep
    If CallFunctionFast(jfReader,old+at/512,#FSJ_SECTORS,buffer)=0 : ProcedureReturn jfFail(#JF_E_IO) : EndIf
    If keep<last
     For toAt=keep To last-1 : PokeA(buffer+toAt-at,0) : Next
    EndIf
   Else
    fsjZero(buffer)
   EndIf
   fromAt=at : toAt=last
   If fromAt<position : fromAt=position : EndIf
   If toAt>position+count : toAt=position+count : EndIf
   If fromAt<toAt : jfCopy(buffer+fromAt-at,src+fromAt-position,toAt-fromAt) : EndIf
   If CallFunctionFast(jfWriter,jfFirst+start+at/512,#FSJ_SECTORS,buffer)=0 : ProcedureReturn jfFail(#JF_E_IO) : EndIf
  Next
  If CallFunctionFast(jfFlusher)=0 : ProcedureReturn jfFail(#JF_E_IO) : EndIf
 EndIf
 entry=jfStage(jfFile) : PokeQ(entry+8,start) : PokeQ(entry+16,length)
 ProcedureReturn jfPublish(jfFile,entry)
EndProcedure

Procedure.i JfOverwrite(src.i,length.i,armed.i)
 If jfOpenReady()=0 : ProcedureReturn 0 : EndIf
 If length<0 Or (length>0 And src=0) : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 If jfReplace(length,0,src,0,length,armed)=0 : ProcedureReturn 0 : EndIf
 jfPosition=length
 ProcedureReturn 1
EndProcedure

Procedure.i JfWrite(src.i,count.i,armed.i)
 Protected old.i,length.i
 If jfOpenReady()=0 : ProcedureReturn -1 : EndIf
 If count<0 Or (count>0 And src=0) : jfFail(#JF_E_CURSOR) : ProcedureReturn -1 : EndIf
 If count=0 : ProcedureReturn 0 : EndIf
 If count>(jfLimit-jfFirst-#JF_DATA)*512-jfPosition : jfFail(#JF_E_FULL) : ProcedureReturn -1 : EndIf
 old=JfSize() : length=jfPosition+count
 If length<old : length=old : EndIf
 If jfReplace(length,old,src,jfPosition,count,armed)=0 : ProcedureReturn -1 : EndIf
 jfPosition=jfPosition+count
 ProcedureReturn count
EndProcedure

Procedure.i JfTruncate(length.i,armed.i)
 Protected keep.i
 If jfOpenReady()=0 : ProcedureReturn 0 : EndIf
 keep=JfSize()
 If keep=length : ProcedureReturn jfCanWrite(armed) : EndIf
 If keep>length : keep=length : EndIf
 If jfReplace(length,keep,0,0,0,armed)=0 : ProcedureReturn 0 : EndIf
 If jfPosition>length : jfPosition=length : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i JfDirRewind()
 If jfReady()=0 : ProcedureReturn 0 : EndIf
 If jfDir<0 : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 jfNext=1 : jfCurrent=0
 ProcedureReturn 1
EndProcedure

Procedure.i JfDirOpen(path.i)
 Protected id.i=jfResolve(path)
 If id<0 : ProcedureReturn 0 : EndIf
 If id>0
  If PeekA(jfEntry(id))<>#JF_DIR : ProcedureReturn jfFail(#JF_E_TYPE) : EndIf
 EndIf
 jfDir=id
 ProcedureReturn JfDirRewind()
EndProcedure

Procedure.i JfDirNext()
 Protected entry.i
 If jfReady()=0 : ProcedureReturn -1 : EndIf
 If jfDir<0 : jfFail(#JF_E_CURSOR) : ProcedureReturn -1 : EndIf
 jfCurrent=0
 While jfNext<=#JF_SLOTS
  entry=jfEntry(jfNext) : jfNext=jfNext+1
  If PeekA(entry)<>0 And PeekW(entry+2)=jfDir
   jfCurrent=entry : ProcedureReturn 1
  EndIf
 Wend
 ProcedureReturn 0
EndProcedure

Procedure.i JfDirName(dst.i,capacity.i)
 Protected length.i
 If jfCurrent=0 Or dst=0 : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 length=PeekW(jfCurrent+4)
 If capacity<=length : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 jfCopy(dst,jfCurrent+#JF_NAME,length) : PokeA(dst+length,0)
 ProcedureReturn length
EndProcedure

Procedure.i JfRemove(path.i,armed.i)
 Protected id.i,child.i,entry.i,at.i
 If jfCanWrite(armed)=0 : ProcedureReturn 0 : EndIf
 If jfFile<>0 : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 id=jfResolve(path)
 If id<0 : ProcedureReturn 0 : EndIf
 If id=0 : ProcedureReturn jfFail(#JF_E_TYPE) : EndIf
 For child=1 To #JF_SLOTS
  If PeekW(jfEntry(child)+2)=id : ProcedureReturn jfFail(#JF_E_NOT_EMPTY) : EndIf
 Next
 entry=jfStage(id)
 For at=0 To #JF_ENTRY-8 Step 8 : PokeQ(entry+at,0) : Next
 If jfPublish(id,entry)=0 : ProcedureReturn 0 : EndIf
 If jfDir=id : jfDir=-1 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i JfRename(oldPath.i,newPath.i,armed.i)
 Protected id.i,target.i,ancestor.i,entry.i
 If jfCanWrite(armed)=0 : ProcedureReturn 0 : EndIf
 If jfFile<>0 : ProcedureReturn jfFail(#JF_E_CURSOR) : EndIf
 id=jfResolve(oldPath)
 If id<0 : ProcedureReturn 0 : EndIf
 If id=0 : ProcedureReturn jfFail(#JF_E_TYPE) : EndIf
 target=jfResolve(newPath)
 If target=id : ProcedureReturn 1 : EndIf
 If target>=0 : ProcedureReturn jfFail(#JF_E_EXISTS) : EndIf
 If jfName=0 : ProcedureReturn 0 : EndIf
 ancestor=jfParent
 While ancestor<>0
  If ancestor=id : ProcedureReturn jfFail(#JF_E_CYCLE) : EndIf
  ancestor=PeekW(jfEntry(ancestor)+2)
 Wend
 entry=jfStage(id) : jfStoreName(entry)
 ProcedureReturn jfPublish(id,entry)
EndProcedure

Procedure.i JfExtent(path.i,first.i,blocks.i,bytes.i)
 Protected id.i=jfResolve(path),entry.i,length.i
 If id<0 : ProcedureReturn 0 : EndIf
 If id=0 : ProcedureReturn jfFail(#JF_E_TYPE) : EndIf
 entry=jfEntry(id) : length=PeekQ(entry+16)
 If length=0 : ProcedureReturn jfFail(#JF_E_TYPE) : EndIf
 If first<>0 : PokeI(first,jfFirst+PeekQ(entry+8)) : EndIf
 If blocks<>0 : PokeI(blocks,jfSectors(length)) : EndIf
 If bytes<>0 : PokeI(bytes,length) : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i JfErrorText()
 Select jfError
  Case #JF_E_IO : ProcedureReturn "AnvilFS: disk read, write or flush failed"
  Case #JF_E_FORMAT : ProcedureReturn "AnvilFS: invalid volume geometry or directory table"
  Case #JF_E_JOURNAL : ProcedureReturn "AnvilFS: journal unavailable; remount writable media to recover"
  Case #JF_E_NAME : ProcedureReturn "AnvilFS: invalid UTF-8 path component"
  Case #JF_E_MISSING : ProcedureReturn "AnvilFS: path not found"
  Case #JF_E_EXISTS : ProcedureReturn "AnvilFS: destination already exists"
  Case #JF_E_TYPE : ProcedureReturn "AnvilFS: wrong entry type or empty extent"
  Case #JF_E_FULL : ProcedureReturn "AnvilFS: no free entry or contiguous extent"
  Case #JF_E_RO : ProcedureReturn "AnvilFS: no writer is available"
  Case #JF_E_CURSOR : ProcedureReturn "AnvilFS: invalid or busy file or directory cursor"
  Case #JF_E_NOT_EMPTY : ProcedureReturn "AnvilFS: directory is not empty"
  Case #JF_E_CYCLE : ProcedureReturn "AnvilFS: cannot move a directory into its descendant"
 EndSelect
 ProcedureReturn "AnvilFS: no error"
EndProcedure
