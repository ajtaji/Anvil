; Ordered native GPU lists over one permanently pinned command page.
; SPDX-License-Identifier: MIT
; Whole-list admission precedes any launch or command-page write. The portable
; engine owns immutable flight snapshots and retains ALL referenced resources
; until our final retirement. Coherent Zentaji RAM needs no cache-line flushes.
; One item's real GPU fence retires before we overwrite metadata for the next.

Procedure.i avkZenClearRectPreflight(*d.AnvilVkBackendDraw)
 If avkZenClientRange(*d,SizeOf(AnvilVkBackendDraw))=0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 If *d\kind<>#ANVIL_VK_RENDER_OP_CLEAR_RECT Or (*d\loadColor<>0 And *d\loadColor<>1) : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 If avkBackendDrawSupported(*d\targetBase,*d\targetBytes,*d\width,*d\height,*d\pitch)<>#VK_SUCCESS : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 If *d\clearRectX<-$80000000 Or *d\clearRectX>$7FFFFFFF Or *d\clearRectY<-$80000000 Or *d\clearRectY>$7FFFFFFF : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 If *d\clearRectW<0 Or *d\clearRectW>$FFFFFFFF Or *d\clearRectH<0 Or *d\clearRectH>$FFFFFFFF : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkZenListPreflight(*list.AnvilVkBackendDrawList)
 Protected n.i,bytes.i,rc.i,*first.AnvilVkBackendDraw,*d.AnvilVkBackendDraw
 If avkZenClientRange(*list,SizeOf(AnvilVkBackendDrawList))=0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 If *list\drawCount<1 Or *list\drawCount>#ANVIL_VK_MAX_RECORDED_DRAWS : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 bytes=*list\drawCount*SizeOf(AnvilVkBackendDraw)
 If avkZenClientRange(*list\draws,bytes)=0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 *first=*list\draws
 If avkBackendDrawSupported(*first\targetBase,*first\targetBytes,*first\width,*first\height,*first\pitch)<>#VK_SUCCESS : ProcedureReturn #VK_ERROR_FEATURE_NOT_PRESENT : EndIf
 ; A GPU write must not corrupt a later flight record or nested snapshot.
 If avkZenOverlaps(*first\targetBase,*first\targetBytes,*list,SizeOf(AnvilVkBackendDrawList))<>0 Or avkZenOverlaps(*first\targetBase,*first\targetBytes,*list\draws,bytes)<>0 : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
 For n=0 To *list\drawCount-1
  *d=*list\draws+n*SizeOf(AnvilVkBackendDraw)
  If *d\targetBase<>*first\targetBase Or *d\targetBytes<>*first\targetBytes Or *d\width<>*first\width Or *d\height<>*first\height Or *d\pitch<>*first\pitch Or *d\clearBgra<>*first\clearBgra Or *d\loadColor<>*first\loadColor : ProcedureReturn #ANVIL_VK_ERR_ARGS : EndIf
  If *d\kind=#ANVIL_VK_RENDER_OP_DRAW
   rc=avkZenDrawPreflight(*d)
  ElseIf *d\kind=#ANVIL_VK_RENDER_OP_CLEAR_RECT
   rc=avkZenClearRectPreflight(*d)
  Else
   rc=#ANVIL_VK_ERR_ARGS
  EndIf
  If rc<>#VK_SUCCESS : ProcedureReturn rc : EndIf
 Next
 ProcedureReturn #VK_SUCCESS
EndProcedure

Procedure.i avkZenSubmitRect(*d.AnvilVkBackendDraw,preserve.i)
 Protected rc.i,pitch.i,x.i,y.i,right.i,bottom.i
 rc=avkZenClearRectPreflight(*d)
 If rc<>#VK_SUCCESS : ProcedureReturn avkBackendRefuseBeforeLaunch(rc) : EndIf
 If avkZenLease<>#ANVIL_VK_GPU_LEASE_QUEUE Or avkZenPending<>0 Or avkZenQueue\state<>1 Or ZentajiGraphicsOwned(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 pitch=*d\pitch : If pitch=0 : pitch=*d\width*4 : EndIf
 If ZentajiGraphicsBegin(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenBlankCommand() : avkZenCommand[0]=1 : avkZenCommand[1]=*d\targetBase
 PokeL(@avkZenCommand[0]+16,pitch) : PokeW(@avkZenCommand[0]+20,*d\width) : PokeW(@avkZenCommand[0]+22,*d\height) : PokeA(@avkZenCommand[0]+24,2)
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenBlankCommand() : avkZenCommand[0]=4
 PokeL(@avkZenCommand[0]+16,*d\width) : PokeL(@avkZenCommand[0]+20,*d\height)
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 If *d\loadColor=0 And preserve=0
  avkZenBlankCommand() : avkZenCommand[0]=$105 : PokeL(@avkZenCommand[0]+8,*d\clearBgra)
  If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 EndIf
 x=*d\clearRectX : y=*d\clearRectY : right=x+*d\clearRectW : bottom=y+*d\clearRectH
 If x<0 : x=0 : EndIf : If y<0 : y=0 : EndIf
 If right>*d\width : right=*d\width : EndIf : If bottom>*d\height : bottom=*d\height : EndIf
 If right<x : right=x : EndIf : If bottom<y : bottom=y : EndIf
 avkZenBlankCommand() : avkZenCommand[0]=4
 PokeL(@avkZenCommand[0]+8,x) : PokeL(@avkZenCommand[0]+12,y)
 PokeL(@avkZenCommand[0]+16,right) : PokeL(@avkZenCommand[0]+20,bottom)
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenBlankCommand() : avkZenCommand[0]=$105 : PokeL(@avkZenCommand[0]+8,*d\clearRectBgra)
 If avkZenAppendCommand()=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 If ZentajiGraphicsSubmit(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 avkZenPending=1 : avkZenNativeError=0
 ProcedureReturn #ANVIL_VK_JOB_PENDING
EndProcedure

Procedure.i avkZenListKick()
 Protected *d.AnvilVkBackendDraw
 *d=avkZenListBase+avkZenListIndex*SizeOf(AnvilVkBackendDraw)
 If *d\kind=#ANVIL_VK_RENDER_OP_CLEAR_RECT : ProcedureReturn avkZenSubmitRect(*d,Bool(avkZenListIndex<>0)) : EndIf
 ProcedureReturn avkZenSubmitOne(*d,Bool(avkZenListIndex<>0))
EndProcedure

Procedure.i avkBackendSubmitDraw(*list.AnvilVkBackendDrawList)
 Protected rc.i
 If avkZenListActive<>0 Or avkZenPending<>0 Or avkZenLease<>#ANVIL_VK_GPU_LEASE_QUEUE Or avkZenQueue\state<>1 Or ZentajiGraphicsOwned(@avkZenQueue)=0 : ProcedureReturn avkBackendRefuseBeforeLaunch(#VK_ERROR_DEVICE_LOST) : EndIf
 rc=avkZenListPreflight(*list)
 If rc<>#VK_SUCCESS : ProcedureReturn avkBackendRefuseBeforeLaunch(rc) : EndIf
 avkZenListBase=*list\draws : avkZenListCount=*list\drawCount : avkZenListIndex=0
 rc=avkZenListKick()
 If rc=#ANVIL_VK_JOB_PENDING
  avkZenListActive=1
 Else
  avkZenListBase=0 : avkZenListCount=0
 EndIf
 ProcedureReturn rc
EndProcedure

Procedure.i avkBackendPoll()
 Protected rc.i
 If avkZenListActive<0 : ProcedureReturn -1 : EndIf
 rc=avkZenPollOne()
 If rc<0
  If avkZenListActive<>0 : avkZenListActive=-1 : EndIf
  ProcedureReturn -1
 EndIf
 If rc=0 : ProcedureReturn 0 : EndIf
 If avkZenListActive=0 : ProcedureReturn 1 : EndIf
 avkZenListIndex=avkZenListIndex+1
 If avkZenListIndex=avkZenListCount
  avkZenListActive=0 : avkZenListBase=0 : avkZenListCount=0
  ProcedureReturn 1
 EndIf
 rc=avkZenListKick()
 If rc<>#ANVIL_VK_JOB_PENDING
  ; Earlier items have launched. This is never a retryable no-launch refusal.
  ; The portable flight will quarantine the lease and all retained resources.
  avkZenNativeError=avkBackendRefusalCode : avkZenListActive=-1
  ProcedureReturn -1
 EndIf
 ProcedureReturn 0
EndProcedure

Procedure.i avkBackendFenceProgress()
 ProcedureReturn avkZenListIndex
EndProcedure
