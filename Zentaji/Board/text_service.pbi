; SPDX-License-Identifier: MIT
; Cell-text provider. All requests and nested cell spans are checked against
; the real payload memory HAL before any RAM/register write. The protected
; monitor cells remain private. Hardware SCROLL is synchronous, then its
; temporary region/fill registers are restored before another owner can run.
XIncludeFile "Anvil/Hal/text_service.pbi"
#ZEN_TEXT_WRITE_MAX=4096
Global ztEpoch.i,ztColumns.i,ztRows.i,ztCellWidth.i,ztCellHeight.i
Procedure.i ZentajiTextRequest(request.i,bytes.i,want.i)
 If bytes<>want : ProcedureReturn 0 : EndIf
 If want=0 : ProcedureReturn Bool(request=0) : EndIf
 If request<=0 Or (request&7)<>0 Or request>$7FFFFFFFFFFFFFFF-want : ProcedureReturn 0 : EndIf
 ProcedureReturn InPayload(request,request+want-1)
EndProcedure
Procedure.i ZentajiTextRect(x.i,y.i,w.i,h.i)
 If x<0 Or y<0 Or w<1 Or h<1 Or x>=ztColumns Or y>=ztRows : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool(w<=ztColumns-x And h<=ztRows-y)
EndProcedure
Procedure ZentajiTextClearReservation()
 Protected offset.i
 ; A shrink hides rows but does not release their RAM. Clear the entire
 ; protected capacity so later mode/font growth cannot expose an old session.
 For offset=0 To zenTextCapacity-4 Step 4 : PokeL(zenTextCells+offset,$00070020) : Next
 PokeQ(#ZEN_TEXT+$98,0) : PokeQ(#ZEN_TEXT+$D0,1)
EndProcedure
Procedure.i ZentajiTextSessionReset()
 If zenTextApplication=0 : ProcedureReturn 0 : EndIf
 ; A corrupt owner is not repaired by overwriting it. Payload return must
 ; fail-stop before this text/display state or a false prompt is reused.
 If ZentajiTextOwned()=0 : ProcedureReturn #NTX_ERR_PROVIDER : EndIf
 ZentajiTextClearReservation()
 PokeQ(#ZEN_TEXT+$88,$101)
 zenTextCode=0 : zenTextNeed=0 : zenTextMinimum=0 : zenTextApplication=0
 ProcedureReturn 0
EndProcedure
Procedure.i ZentajiTextDispatch(op.i,context.i,request.i,bytes.i)
 Protected *api.NativeTextApi,*open.NativeTextOpenRequest,*write.NativeTextWriteRequest
 Protected *fill.NativeTextFillRequest,*cursor.NativeTextCursorRequest,*scroll.NativeTextScrollRequest
 Protected x.i,y.i,w.i,h.i,row.i,col.i,src.i,dst.i,stride.i,span.i,origin.i,cell.i
 Protected frame.i,started.i,hz.i
 If zenTextUp=0 Or ZentajiTextOwned()=0 : ProcedureReturn #NTX_ERR_PROVIDER : EndIf
 If op=#NTX_QUERY
  If ZentajiTextRequest(request,bytes,SizeOf(NativeTextApi))=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
  *api=request : *api\magic=#NTX_MAGIC : *api\major=#NTX_MAJOR : *api\minor=#NTX_MINOR
  *api\bytes=SizeOf(NativeTextApi) : *api\format=#NTX_CELL_BMP_XTERM256
  *api\maxWriteCells=#ZEN_TEXT_WRITE_MAX : *api\dispatch=@TextServiceCall
  ProcedureReturn 0
 EndIf
 If op=#NTX_OPEN
  If ZentajiTextRequest(request,bytes,SizeOf(NativeTextOpenRequest))=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
  If zenTextApplication<>0 : ProcedureReturn #NTX_ERR_BUSY : EndIf
  If ztEpoch>=2147483647 : ProcedureReturn #NTX_ERR_STATE : EndIf
  ztColumns=PeekQ(#ZEN_TEXT+$50) : ztRows=PeekQ(#ZEN_TEXT+$58)
  ztCellWidth=PeekQ(#ZEN_TEXT+$68) : ztCellHeight=PeekQ(#ZEN_TEXT+$70)
  *open=request : *open\columns=ztColumns : *open\rows=ztRows
  *open\cellWidth=ztCellWidth : *open\cellHeight=ztCellHeight
  ztEpoch=ztEpoch+1 : zenTextApplication=1
  ZentajiTextClearReservation() : PokeQ(#ZEN_TEXT+$88,0)
  ProcedureReturn ztEpoch
 EndIf
 If zenTextApplication=0 Or context<>ztEpoch : ProcedureReturn #NTX_ERR_STATE : EndIf
 If op=#NTX_CLOSE
  If ZentajiTextRequest(request,bytes,0)=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
  ProcedureReturn ZentajiTextSessionReset()
 EndIf
 ; A new font can retain COLS/ROWS while changing cell metrics. Check all four.
 If PeekQ(#ZEN_TEXT+$50)<>ztColumns Or PeekQ(#ZEN_TEXT+$58)<>ztRows Or PeekQ(#ZEN_TEXT+$68)<>ztCellWidth Or PeekQ(#ZEN_TEXT+$70)<>ztCellHeight : ProcedureReturn #NTX_ERR_GEOMETRY : EndIf
 Select op
  Case #NTX_WRITE
   If ZentajiTextRequest(request,bytes,SizeOf(NativeTextWriteRequest))=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
   *write=request : x=*write\x : y=*write\y : w=*write\width : h=*write\height
   If ZentajiTextRect(x,y,w,h)=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
   If w>#ZEN_TEXT_WRITE_MAX/h : ProcedureReturn #NTX_ERR_ARGS : EndIf
   stride=*write\stride : src=*write\cells
   If stride<w Or stride>$7FFFFFFFFFFFFFFF/4/h Or src<=0 Or (src&3)<>0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
   span=((h-1)*stride+w)*4
   If src>$7FFFFFFFFFFFFFFF-span : ProcedureReturn #NTX_ERR_ARGS : EndIf
   If InPayload(src,src+span-1)=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
   origin=PeekQ(#ZEN_TEXT+$98)%ztRows
   For row=0 To h-1
    dst=zenTextCells+(((origin+y+row)%ztRows)*ztColumns+x)*4
    For col=0 To w-1 : PokeL(dst+col*4,PeekL(src+(row*stride+col)*4)) : Next
   Next
  Case #NTX_FILL
   If ZentajiTextRequest(request,bytes,SizeOf(NativeTextFillRequest))=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
   *fill=request : x=*fill\x : y=*fill\y : w=*fill\width : h=*fill\height : cell=*fill\cell
   If ZentajiTextRect(x,y,w,h)=0 Or cell<0 Or cell>$FFFFFFFF : ProcedureReturn #NTX_ERR_ARGS : EndIf
   If w>#ZEN_TEXT_WRITE_MAX/h : ProcedureReturn #NTX_ERR_ARGS : EndIf
   origin=PeekQ(#ZEN_TEXT+$98)%ztRows
   For row=0 To h-1
    dst=zenTextCells+(((origin+y+row)%ztRows)*ztColumns+x)*4
    For col=0 To w-1 : PokeL(dst+col*4,cell) : Next
   Next
  Case #NTX_CURSOR
   If ZentajiTextRequest(request,bytes,SizeOf(NativeTextCursorRequest))=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
   *cursor=request
   If ZentajiTextRect(*cursor\x,*cursor\y,1,1)=0 Or *cursor\style<0 Or (*cursor\style & $FFFFFFFFFF00FEFC)<>0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
   PokeQ(#ZEN_TEXT+$78,*cursor\x) : PokeQ(#ZEN_TEXT+$80,*cursor\y) : PokeQ(#ZEN_TEXT+$88,*cursor\style)
  Case #NTX_SCROLL
   If ZentajiTextRequest(request,bytes,SizeOf(NativeTextScrollRequest))=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
   *scroll=request : y=*scroll\top : h=*scroll\bottom : row=*scroll\lines : cell=*scroll\cell
   If y<0 Or h<=y Or h>ztRows Or row< -ztRows Or row>ztRows Or cell<0 Or cell>$FFFFFFFF : ProcedureReturn #NTX_ERR_ARGS : EndIf
   PokeQ(#ZEN_TEXT+$A8,y) : PokeQ(#ZEN_TEXT+$B0,h) : PokeQ(#ZEN_TEXT+$B8,cell)
   PokeQ(#ZEN_TEXT+$A0,row)
   PokeQ(#ZEN_TEXT+$A8,0) : PokeQ(#ZEN_TEXT+$B0,0) : PokeQ(#ZEN_TEXT+$B8,$00070020)
  Case #NTX_PRESENT
   If ZentajiTextRequest(request,bytes,0)=0 : ProcedureReturn #NTX_ERR_ARGS : EndIf
   If HwPromptIdleReady()=0 : ProcedureReturn #NTX_ERR_PROVIDER : EndIf
   frame=PeekQ(#ZEN_DISPLAY+$98) : started=Ticks() : hz=TickHz()
   If hz<4 : ProcedureReturn #NTX_ERR_PROVIDER : EndIf
   ; Wait for one composed frame, using the monitor-owned timer/WFI path.
   ; Both a quarter-second deadline and a finite wake count bound failures.
   For row=1 To 256
    If ZentajiTextOwned()=0 Or HwPromptIdleReady()=0 : ProcedureReturn #NTX_ERR_PROVIDER : EndIf
    If PeekQ(#ZEN_TEXT+$50)<>ztColumns Or PeekQ(#ZEN_TEXT+$58)<>ztRows Or PeekQ(#ZEN_TEXT+$68)<>ztCellWidth Or PeekQ(#ZEN_TEXT+$70)<>ztCellHeight : ProcedureReturn #NTX_ERR_GEOMETRY : EndIf
    If PeekQ(#ZEN_DISPLAY+$98)<>frame : ProcedureReturn 0 : EndIf
    If Ticks()-started>=hz/4 : ProcedureReturn #NTX_ERR_TIMEOUT : EndIf
    HwPromptIdleWait()
   Next
   ProcedureReturn #NTX_ERR_TIMEOUT
  Default
   ProcedureReturn #NTX_ERR_ARGS
 EndSelect
 ProcedureReturn 0
EndProcedure
Procedure.i ZentajiTextServiceStart()
 If zenTextUp=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool(TextServiceBind(@ZentajiTextDispatch,@ZentajiTextSessionReset)=0)
EndProcedure
