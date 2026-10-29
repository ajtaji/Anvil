; SPDX-License-Identifier: MIT
; Pure client for the existing file-handle service ABI1.4, slots192..195.
; The resident provider owns storage. Close failure retains the handle.
#ANVIL_FILE_ENOSYS = -100
#ANVIL_FILE_EARG = -102
#ANVIL_FILE_EBUSY = -103
#ANVIL_FILE_EIO = -105
#ANVIL_FILE_EABI = -109
Procedure.i afcNoOpen(name.i)
  ProcedureReturn #ANVIL_FILE_ENOSYS
EndProcedure
Procedure.i afcNoOne(handle.i)
  ProcedureReturn #ANVIL_FILE_ENOSYS
EndProcedure
Procedure.i afcNoRead(handle.i,offset.i,dst.i,bytes.i)
  ProcedureReturn #ANVIL_FILE_ENOSYS
EndProcedure
Global afcOpen.i=@afcNoOpen,afcSize.i=@afcNoOne,afcClose.i=@afcNoOne,afcRead.i=@afcNoRead
Global afcBound.i,afcBusy.i,afcOwned.i,afcRetained.i
Procedure.i AnvilFileBind(services.i)
  Protected openFn.i,sizeFn.i,closeFn.i,readFn.i
  If afcBusy<>0 Or afcOwned<>0 : ProcedureReturn #ANVIL_FILE_EBUSY : EndIf
  If services=0 Or (services & 7)<>0 : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  If (PeekL(services)&$FFFFFFFF)<>$53564E41 Or PeekL(services+4)<>1 Or PeekL(services+8)<4 Or (PeekL(services+12)&$FFFFFFFF)<196
    ProcedureReturn #ANVIL_FILE_EABI
  EndIf
  openFn=PeekI(services+16+192*8) : sizeFn=PeekI(services+16+193*8)
  readFn=PeekI(services+16+194*8) : closeFn=PeekI(services+16+195*8)
  If openFn=0 Or sizeFn=0 Or readFn=0 Or closeFn=0 : ProcedureReturn #ANVIL_FILE_ENOSYS : EndIf
  afcOpen=openFn : afcSize=sizeFn : afcRead=readFn : afcClose=closeFn : afcBound=1
  ProcedureReturn 0
EndProcedure
Procedure.i AnvilFileUnbind()
  If afcBusy<>0 Or afcOwned<>0 : ProcedureReturn #ANVIL_FILE_EBUSY : EndIf
  afcBound=0 : afcOpen=@afcNoOpen : afcSize=@afcNoOne : afcRead=@afcNoRead : afcClose=@afcNoOne
  ProcedureReturn 0
EndProcedure
Procedure.i AnvilFileRetainedHandle()
  ProcedureReturn afcRetained
EndProcedure
Procedure.i AnvilFileOpen(name.i)
  Protected h.i
  If afcBusy<>0 : ProcedureReturn #ANVIL_FILE_EBUSY : EndIf
  If afcBound=0 : ProcedureReturn #ANVIL_FILE_ENOSYS : EndIf
  If name=0 : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  afcBusy=1 : h=afcOpen(name) : afcBusy=0
  If h<0 : ProcedureReturn h : EndIf
  If h<1 Or h>8 : ProcedureReturn #ANVIL_FILE_EIO : EndIf
  If (afcOwned & (1 << (h-1)))<>0 : ProcedureReturn #ANVIL_FILE_EIO : EndIf
  afcOwned=afcOwned | (1 << (h-1))
  ProcedureReturn h
EndProcedure
Procedure.i AnvilFileSize(handle.i)
  Protected rc.i
  If afcBusy<>0 : ProcedureReturn #ANVIL_FILE_EBUSY : EndIf
  If afcBound=0 : ProcedureReturn #ANVIL_FILE_ENOSYS : EndIf
  If handle<1 Or handle>8 : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  If (afcOwned & (1 << (handle-1)))=0 : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  afcBusy=1 : rc=afcSize(handle) : afcBusy=0 : ProcedureReturn rc
EndProcedure
Procedure.i AnvilFileReadAt(handle.i,offset.i,dst.i,bytes.i)
  Protected rc.i
  If afcBusy<>0 : ProcedureReturn #ANVIL_FILE_EBUSY : EndIf
  If afcBound=0 : ProcedureReturn #ANVIL_FILE_ENOSYS : EndIf
  If handle<1 Or handle>8 Or offset<0 Or dst<1 Or bytes<0 : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  If dst>$7FFFFFFFFFFFFFFF-bytes Or offset>$7FFFFFFFFFFFFFFF-bytes : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  If (afcOwned & (1 << (handle-1)))=0 : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  afcBusy=1 : rc=afcRead(handle,offset,dst,bytes) : afcBusy=0
  If rc>bytes : ProcedureReturn #ANVIL_FILE_EIO : EndIf
  ProcedureReturn rc
EndProcedure
Procedure.i AnvilFileClose(handle.i)
  Protected rc.i
  If afcBusy<>0 : ProcedureReturn #ANVIL_FILE_EBUSY : EndIf
  If afcBound=0 : ProcedureReturn #ANVIL_FILE_ENOSYS : EndIf
  If handle<1 Or handle>8 : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  If (afcOwned & (1 << (handle-1)))=0 : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  afcBusy=1 : rc=afcClose(handle) : afcBusy=0
  If rc>0 : rc=#ANVIL_FILE_EIO : EndIf
  If rc=0
    afcOwned=afcOwned & ~(1 << (handle-1))
    If afcRetained=handle : afcRetained=0 : EndIf
  EndIf
  ProcedureReturn rc
EndProcedure
; Read loops permit partial progress and reject oversized provider counts.
; On a failed Close, RetainedHandle identifies the explicit cleanup retry.
Procedure.i AnvilFileReadWhole(name.i,dst.i,capacity.i)
  Protected h.i,size.i,offset.i,count.i,rc.i,result.i
  If afcRetained<>0 : ProcedureReturn #ANVIL_FILE_EBUSY : EndIf
  If name=0 Or dst<1 Or capacity<1 Or dst>$7FFFFFFFFFFFFFFF-capacity : ProcedureReturn #ANVIL_FILE_EARG : EndIf
  h=AnvilFileOpen(name) : If h<1 : ProcedureReturn h : EndIf
  size=AnvilFileSize(h) : result=size
  If size>capacity : result=#ANVIL_FILE_EARG : EndIf
  If size>=0 And size<=capacity
    While offset<size
      count=AnvilFileReadAt(h,offset,dst+offset,size-offset)
      If count<0 : result=count : Break : EndIf
      If count=0 : result=#ANVIL_FILE_EIO : Break : EndIf
      offset=offset+count
    Wend
  EndIf
  rc=AnvilFileClose(h)
  If rc<>0 : afcRetained=h : ProcedureReturn rc : EndIf
  ProcedureReturn result
EndProcedure
