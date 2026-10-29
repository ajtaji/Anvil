; SPDX-License-Identifier: MIT
; Font-reference caret queries and GPU marker alignment against fixed cells.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_font_port.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_font_caret.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_service_caret.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_canvas_retro.pbi"
#NFP_REPORT=$E1C00200
#NFP_PIXELS=$E2400000
Global nfpChecks.i,nfpFailure.i
Global nfpFont.NeonVkPortFontRef,nfpStale.NeonVkPortFontRef,nfpProp.NeonVkPortFontRef
Global Dim nfpLong.a[4097]
Procedure NfpCheck(actual.i,expected.i)
 PokeI(#NFP_REPORT+512+nfpChecks*16,actual) : PokeI(#NFP_REPORT+520+nfpChecks*16,expected)
 nfpChecks+1
 If actual<>expected And nfpFailure=0 : nfpFailure=nfpChecks : EndIf
 PokeI(#NFP_REPORT+16,nfpFailure) : PokeI(#NFP_REPORT+24,nfpChecks)
EndProcedure
Global nfpCaret.NeonServiceFontCaretRequest,nfpApi.NeonServiceApi,nfpMockMode.i
Procedure.i NfpCaretDispatch(op.i,context.i,request.i,bytes.i)
 If context<>99 : ProcedureReturn #NEON_SERVICE_ERR_STATE : EndIf
 If nfpMockMode<>0
   PokeI(request+48,999)
   If nfpMockMode=1 : ProcedureReturn #NEON_SERVICE_ERR_BUSY : EndIf
   ProcedureReturn 1
 EndIf
 ProcedureReturn NeonVkServiceCaret(op,@nfpProp,request,bytes)
EndProcedure
; Successful native draws before the Vulkan service takes ownership.
; Eight 64x32 crops retain every pixel around the small independent glyphs.
; Bounded workload timing; one warm frame plus three samples per path.
Procedure.i NfpWorkloadReturn(rc.i)
 MmuDisableCachedFlushed()
 PokeI($E2520030,MmuSctlr() & $1005)
 ProcedureReturn rc
EndProcedure
Procedure.i NfpNativeTextWorkload()
 Protected kind.i,frame.i,i.i,row.i,rc.i,t0.i,t1.i,t2.i,t3.i,t4.i,out.i
 For i=0 To 4088 Step 8 : PokeI($E2520000+i,0) : Next
 PokeI($E2520000,$4E545731) : PokeI($E2520008,2)
 PokeI($E2520010,V3dCounterHz()) : PokeI($E2520018,8)
 PokeI($E2520020,MmuSctlr() & $1005)
 If (MmuSctlr() & $1005)<>0 : ProcedureReturn 201 : EndIf
 MmuClearNc()
 MmuAddNc($03000000,$04200000)
 MmuAddNc($08A00000,$08E00000)
 rc=MmuBuildTables($E2530000)
 If rc<>0 : ProcedureReturn rc : EndIf
 MmuEnableCached()
 PokeI($E2520028,MmuSctlr() & $1005)
 If (MmuSctlr() & $1005)<>$1005 : ProcedureReturn NfpWorkloadReturn(202) : EndIf
 For kind=0 To 1
  For frame=0 To 3
   t0=V3dTicks() : rc=NeonFrameBegin($FF000000) : t1=V3dTicks()
   If rc<>0 : ProcedureReturn NfpWorkloadReturn(rc) : EndIf
   For i=0 To 3504
    rc=Neon_Box((i-(i/100)*100)*7,(i/100)*7,4,4,$FF303030)
    If rc<>0 : NeonFrameEnd() : ProcedureReturn NfpWorkloadReturn(rc) : EndIf
   Next
   t2=V3dTicks()
   For row=0 To 29
    If kind=0
     If row<29 : rc=Neon_Text(0,10,10+row*18,?nfpWork48,$FFFFFFFF) : Else : rc=Neon_Text(0,10,10+row*18,?nfpWork42,$FFFFFFFF) : EndIf
    Else
     If row<29 : rc=Neon_TextTex(0,10,10+row*18,?nfpWork48,$FFFFFFFF) : Else : rc=Neon_TextTex(0,10,10+row*18,?nfpWork42,$FFFFFFFF) : EndIf
    EndIf
    If rc<>0 : NeonFrameEnd() : ProcedureReturn NfpWorkloadReturn(rc) : EndIf
   Next
   t3=V3dTicks() : rc=NeonFrameEnd() : t4=V3dTicks()
   If rc<>0 : ProcedureReturn NfpWorkloadReturn(rc) : EndIf
   out=$E2520040+(kind*4+frame)*128
   PokeI(out,kind) : PokeI(out+8,frame)
   PokeI(out+16,t1-t0) : PokeI(out+24,t2-t1) : PokeI(out+32,t3-t2)
   PokeI(out+40,t4-t3) : PokeI(out+48,t4-t0)
   PokeI(out+56,Neon_Boxes()) : PokeI(out+64,Neon_Glyphs()) : PokeI(out+72,Neon_TexGlyphs())
   PokeI(out+80,Neon_Draws()) : PokeI(out+88,Neon_TexDraws())
   PokeI(out+96,Neon_Verts()) : PokeI(out+104,Neon_TexVerts())
   PokeI(out+112,Neon_Error()) : PokeI(out+120,Neon_Runs())
  Next
 Next
 ProcedureReturn NfpWorkloadReturn(0)
EndProcedure
DataSection
 nfpWork48: Data.a 65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,0
 nfpWork42: Data.a 65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,0
EndDataSection
Procedure.i NfpNativeTextSuccess(surface.i,pitch.i)
 Protected kind.i,mode.i,i.i,j.i,rc.i,dst.i
 NfpCheck(Neon_SurfaceRotation(),0)
 NfpCheck(NeonFontUse(?nfpSuccessBits,8,4,65,66),0)
 For i=0 To 65560 Step 8 : PokeI($E2500000+i,$A5A5A5A5A5A5A5A5) : Next
 For kind=0 To 1
  For mode=0 To 3
   rc=NeonFrameBegin($FF000000) : NfpCheck(rc,0)
   If rc<>0 : ProcedureReturn rc : EndIf
   If mode=1
    If kind=0 : neon_nVerts=#NEON_MAX_VERTS-48 : Else : neon_nTVerts=#NEON_MAX_TVERTS-18 : EndIf
   EndIf
   If mode=2
    If kind=0 : neon_nDraws=#NEON_MAX_DRAWS-1 : Else : neon_nTDraws=#NEON_MAX_TDRAWS-1 : EndIf
   EndIf
   If mode=3 : Neon_ScissorSet(12,11,18,2) : EndIf
   If kind=0
    NfpCheck(Neon_Text(0,10,10,?nfpSuccessText,$FFFFFFFF),0)
    If mode=1 : NfpCheck(Neon_Verts(),#NEON_MAX_VERTS) : Else : NfpCheck(Neon_Verts(),48) : EndIf
    If mode=2 : NfpCheck(Neon_Draws(),#NEON_MAX_DRAWS) : Else : NfpCheck(Neon_Draws(),1) : EndIf
    NfpCheck(Neon_Glyphs(),3) : NfpCheck(Neon_Runs(),8)
   Else
    NfpCheck(Neon_TextTex(0,10,10,?nfpSuccessText,$FFFFFFFF),0)
    If mode=1 : NfpCheck(Neon_TexVerts(),#NEON_MAX_TVERTS) : Else : NfpCheck(Neon_TexVerts(),18) : EndIf
    If mode=2 : NfpCheck(Neon_TexDraws(),#NEON_MAX_TDRAWS) : Else : NfpCheck(Neon_TexDraws(),1) : EndIf
    NfpCheck(Neon_TexGlyphs(),3) : NfpCheck(Neon_Runs(),0)
   EndIf
   rc=NeonFrameEnd() : NfpCheck(rc,0) : NfpCheck(Neon_Error(),0)
   If rc<>0 : ProcedureReturn rc : EndIf
   dst=$E2500010+(kind*4+mode)*8192
   For i=0 To 31
    For j=0 To 248 Step 8 : PokeI(dst+i*256+j,PeekI(surface+i*pitch+j)) : Next
   Next
  Next
 Next
 NfpCheck(NeonFontUse(?dsp_font8x16,8,16,32,126),0)
 NfpCheck(NfpNativeTextWorkload(),0)
 ProcedureReturn nfpFailure
EndProcedure
DataSection
 nfpSuccessBits: Data.a $F0,$F0,$A0,$A0,$CC,$CC,$CC,$CC
 nfpSuccessText: Data.a 65,66,65,0
EndDataSection
Global Dim nfpNativeGuard.q[32]
Procedure NfpNativeBoxCapacity()
 Protected backend.i=gNeonBackendActive,state.i=gNeonStateActive
 Protected frame.i=neon_inFrame,draws.i=neon_nDraws,verts.i=neon_nVerts,boxes.i=neon_nBoxes
 Protected clipped.i=neon_nClipped,clip.i=neon_clipOn,error.i=neon_err,base.i=gNeonVerts,i.i
 gNeonBackendActive=0 : gNeonStateActive=0
 NfpCheck(gNeonNativeDrawActive,1)
 neon_inFrame=1 : neon_nDraws=#NEON_MAX_DRAWS : neon_nVerts=0 : neon_nBoxes=7
 neon_nClipped=11 : neon_clipOn=0 : neon_err=0 : gNeonVerts=@nfpNativeGuard[4]
 For i=0 To 31 : nfpNativeGuard[i]=$6A6A6A6A6A6A6A6A : Next
 NfpCheck(Neon_Box(10,10,8,8,$FFFFFFFF),8)
 NfpCheck(Neon_Verts(),0) : NfpCheck(Neon_Boxes(),7) : NfpCheck(Bool(Neon_Draws()=#NEON_MAX_DRAWS),1)
 NfpCheck(Neon_Clipped(),11) : NfpCheck(Neon_Error(),8)
 For i=0 To 31 : NfpCheck(nfpNativeGuard[i],$6A6A6A6A6A6A6A6A) : Next
 ; Empty boxes still succeed without requiring a draw record.
 NfpCheck(Neon_Box(10,10,0,8,$FFFFFFFF),0)
 NfpCheck(Neon_Verts(),0) : NfpCheck(Neon_Boxes(),7)
 neon_inFrame=frame : neon_nDraws=draws : neon_nVerts=verts : neon_nBoxes=boxes
 neon_nClipped=clipped : neon_clipOn=clip : neon_err=error : gNeonVerts=base
 gNeonBackendActive=backend : gNeonStateActive=state
EndProcedure
Procedure NfpNativeTextCapacity()
 Protected backend.i=gNeonBackendActive,state.i=gNeonStateActive,frame.i=neon_inFrame
 Protected draws.i=neon_nDraws,verts.i=neon_nVerts,runs.i=neon_nRuns,glyphs.i=neon_nGlyphs
 Protected td.i=neon_nTDraws,tv.i=neon_nTVerts,tg.i=neon_nTGlyphs,tbase.i=neon_tverts
 Protected clipped.i=neon_nClipped,clip.i=neon_clipOn,error.i=neon_err,base.i=gNeonVerts
 Protected fb.i=neon_fbits,fw.i=neon_fw,fh.i=neon_fh,fr.i=neon_frb,ff.i=neon_ffirst,fl.i=neon_flast
 Protected built.i=neon_texBuilt,rev.i=neon_texRevision,kind.i,capacity.i,i.i,expected.i,rc.i
 Protected bits.a=255
 gNeonBackendActive=0 : gNeonStateActive=0 : neon_inFrame=1 : neon_clipOn=0
 neon_fbits=@bits : neon_fw=8 : neon_fh=1 : neon_frb=1 : neon_ffirst=65 : neon_flast=65
 For kind=0 To 1
  For capacity=0 To 1
   neon_nDraws=#NEON_MAX_DRAWS : neon_nTDraws=#NEON_MAX_TDRAWS
   neon_nVerts=0 : neon_nTVerts=0 : neon_nRuns=17 : neon_nGlyphs=19 : neon_nTGlyphs=23
   neon_nClipped=29 : neon_err=0 : neon_texBuilt=0 : neon_texRevision=123
   expected=8
   If capacity=1
    neon_nVerts=#NEON_MAX_VERTS-6 : neon_nTVerts=#NEON_MAX_TVERTS-6 : expected=7
   EndIf
   ; Redirect the next available six vertices into guarded storage.
   gNeonVerts=@nfpNativeGuard[4]-neon_nVerts*16
   neon_tverts=@nfpNativeGuard[4]-neon_nTVerts*#NEON_TVERT_BYTES
   For i=0 To 31 : nfpNativeGuard[i]=$6A6A6A6A6A6A6A6A : Next
   If kind=0
    rc=Neon_Text(-1,10,10,?nfpCapacityText,$FFFFFFFF)
   Else
    rc=Neon_TextTex(-1,10,10,?nfpCapacityText,$FFFFFFFF)
   EndIf
   NfpCheck(rc,expected) : NfpCheck(Neon_Error(),expected)
   NfpCheck(Neon_Verts(),capacity*(#NEON_MAX_VERTS-6))
   NfpCheck(Neon_TexVerts(),capacity*(#NEON_MAX_TVERTS-6))
   NfpCheck(Neon_Runs(),17) : NfpCheck(Neon_Glyphs(),19) : NfpCheck(Neon_TexGlyphs(),23)
   NfpCheck(Bool(Neon_Draws()=#NEON_MAX_DRAWS),1)
   NfpCheck(Bool(Neon_TexDraws()=#NEON_MAX_TDRAWS),1)
   NfpCheck(Neon_Clipped(),29) : NfpCheck(neon_texBuilt,0) : NfpCheck(neon_texRevision,123)
   For i=0 To 31 : NfpCheck(nfpNativeGuard[i],$6A6A6A6A6A6A6A6A) : Next
   ; Transparent and empty strings do not consume capacity or build an atlas.
   NfpCheck(Neon_Text(-1,10,10,?nfpCapacityText,0),0)
   NfpCheck(Neon_TextTex(-1,10,10,?nfpCapacityText,0),0)
   NfpCheck(Neon_Text(-1,10,10,?nfpCapacityEmpty,$FFFFFFFF),0)
   NfpCheck(Neon_TextTex(-1,10,10,?nfpCapacityEmpty,$FFFFFFFF),0)
   NfpCheck(neon_texBuilt,0) : NfpCheck(neon_texRevision,123)
  Next
 Next
 neon_inFrame=frame : neon_nDraws=draws : neon_nVerts=verts : neon_nRuns=runs : neon_nGlyphs=glyphs
 neon_nTDraws=td : neon_nTVerts=tv : neon_nTGlyphs=tg : neon_tverts=tbase
 neon_nClipped=clipped : neon_clipOn=clip : neon_err=error : gNeonVerts=base
 neon_fbits=fb : neon_fw=fw : neon_fh=fh : neon_frb=fr : neon_ffirst=ff : neon_flast=fl
 neon_texBuilt=built : neon_texRevision=rev : gNeonBackendActive=backend : gNeonStateActive=state
EndProcedure
DataSection
 nfpCapacityText: : Data.a 65,65,65,0
 nfpCapacityEmpty: : Data.a 0
EndDataSection
Procedure NfpEarlyRetro()
 Protected canvas.NeonVkCanvas,point.NeonCanvasPoint,pipeline.i,generation.i
 NfpCheck(NeonVkCanvasInit(@canvas,SizeOf(NeonVkCanvas)),0)
 NfpCheck(NeonVkCanvasCreateBlank(@canvas,32,32,16),0)
 NfpCheck(canvas\hasFrame,0)
 NfpCheck(NeonVkCanvasRetroPrepare(@canvas),0)
 pipeline=nvcRetroPipeline
 NfpCheck(Bool(pipeline<>0),1)
 NfpCheck(NeonVkCanvasRetroPrepare(@canvas),0)
 NfpCheck(Bool(nvcRetroPipeline=pipeline),1)
 NfpCheck(canvas\hasFrame,0)
 NfpCheck(Bool(NeonVkCanvasDrawRetro(@canvas,0)=#NEON_CANVAS_ERR_STATE),1)
 point\xQ16=123 : point\yQ16=456
 NfpCheck(Bool(NeonVkCanvasMapRetroPoint(@canvas,0,0,@point)=#NEON_CANVAS_ERR_STATE),1)
 NfpCheck(point\xQ16,123) : NfpCheck(point\yQ16,456)
 generation=canvas\textureGeneration : canvas\textureGeneration=canvas\textureGeneration+1
 NfpCheck(Bool(NeonVkCanvasRetroPrepare(@canvas)=#NEON_CANVAS_ERR_STALE),1)
 canvas\textureGeneration=generation
 NfpCheck(NeonVkCanvasRetroPrepare(@canvas),0)
 NfpCheck(NeonVkCanvasClose(@canvas),0)
 NfpCheck(Bool(NeonVkCanvasRetroPrepare(@canvas)=#NEON_CANVAS_ERR_STATE),1)
EndProcedure
Procedure.i NfpFrame(imageBase.i,pitch.i,framebuffer.i)
 Protected i.i,j.i,row.i,part.i,src.i,dst.i,x.i,y.i,offset.i,position.f
 Protected Dim clear.l[4]
 PokeI(#NFP_REPORT,$43465031) : PokeI(#NFP_REPORT+8,1)
 NfpNativeBoxCapacity()
 NfpNativeTextCapacity()
 NfpEarlyRetro()
 NfpCheck(NeonVkPortCanvas(400,640,800,1280),0)
 NfpCheck(NeonVkPortFontBind(@nfpFont,0,1,12),0)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFont,7.5),0)
 NfpCheck(NeonVkPortFontSetShowControls(@nfpFont,0),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?hidden,3,@x,@y,@offset),0)
 NfpCheck(x,983040)
 NfpCheck(y,0)
 NfpCheck(offset,6)
 NfpCheck(MathBitsOf(NeonVkPortFontTextXForColumn(@nfpFont,?hidden,4)),1102315520)
 NfpCheck(MathBitsOf(NeonVkPortFontTextXForColumn(@nfpFont,?hidden,6)),1108738048)
 NfpCheck(NeonVkPortFontTextColumnForX(@nfpFont,?hidden,3.75),2)
 NfpCheck(NeonVkPortFontTextColumnForX(@nfpFont,?hidden,1000.0),4)
 NfpCheck(NeonVkPortFontTextColumnForX(@nfpFont,?hidden,-1.0),0)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpFont,?hidden,1,0),-21312)
 x=123 : y=456 : offset=789
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?hidden,5,@x,@y,@offset),-21312)
 NfpCheck(x,123)
 NfpCheck(y,456)
 NfpCheck(offset,789)
 For i=0 To SizeOf(NeonVkPortFontRef)-1 : PokeA(@nfpStale+i,PeekA(@nfpFont+i)) : Next
 nfpStale\generation=nfpStale\generation+1
 NfpCheck(NeonVkPortFontCaretPoint(@nfpStale,?hidden,0,@x,@y,@offset),-21310)
 NfpCheck(x,123)
 NfpCheck(NeonVkPortFontTextColumnForX(@nfpStale,?hidden,1.0),-21310)
 NfpCheck(NeonVkPortFontCaretPoint(0,?hidden,0,@x,@y,@offset),-21309)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,0,0,@x,@y,@offset),-21312)
 NfpCheck(NeonVkPortFontSetControlMode(@nfpFont,0),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?multiline,2,@x,@y,@offset),0)
 NfpCheck(x,0)
 NfpCheck(y,-917504)
 NfpCheck(offset,2)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpFont,?multiline,1,0),2)
 NfpCheck(NeonVkPortFontTextColumnForX(@nfpFont,?multiline,1.0),-21312)
 NfpCheck(MathBitsOf(NeonVkPortFontTextXForColumn(@nfpFont,?multiline,1)),3212836864)
 NfpCheck(NeonVkPortFontSetShowControls(@nfpFont,0),0)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpFont,16.0),0)
 NfpCheck(NeonVkPortFontWarm(@nfpFont,?text),0)
 NfpCheck(NeonVkChromeRebind(framebuffer,800,1280,800,1280,pitch,0),0)
 clear[3]=$3F800000
 NfpCheck(NeonVkPortFontBind(@nfpProp,0,1,12),0)
 NfpCheck(NeonVkPortFontSetShowControls(@nfpProp,0),0)
 NfpCheck(NeonVkPortFontSetSnapToPixel(@nfpProp,0),0)
 NfpCheck(NeonVkPortFontTextColumnForX(@nfpProp,?text,1000001.0),-21312)
 NfpCheck(MathBitsOf(NeonVkPortFontTextXForColumn(@nfpProp,?text,2049)),3212836864)
 NfpCheck(MathBitsOf(NeonVkPortFontTextXForColumn(@nfpProp,?text,-1)),0)
 For i=0 To 4095 : nfpLong[i]=9 : Next
 NfpCheck(NeonVkPortFontCaretPoint(@nfpProp,@nfpLong[0],0,@x,@y,@offset),-21312)
 nfpLong[2049]=0
 NfpCheck(NeonVkPortFontCaretPoint(@nfpProp,@nfpLong[0],0,@x,@y,@offset),-21312)
 NfpCheck(NeonVkPortFontWarm(@nfpProp,?text),0)
 NfpCheck(NeonVkChromeBegin(@clear[0]),0)
 NfpCheck(NeonVkPortFontText(@nfpFont,10.0,20.0,?text,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFont,200.0,20.0,?char0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFont,216.0,20.0,?char1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFont,232.0,20.0,?char2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFont,248.0,20.0,?char3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFont,264.0,20.0,?char4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpFont,280.0,20.0,?char5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?text,0,@x,@y,@offset),0)
 NfpCheck(x,0)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(200.0,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?text,1,@x,@y,@offset),0)
 NfpCheck(x,1048576)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(216.0,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?text,2,@x,@y,@offset),0)
 NfpCheck(x,2097152)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(232.0,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?text,3,@x,@y,@offset),0)
 NfpCheck(x,3145728)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(248.0,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?text,4,@x,@y,@offset),0)
 NfpCheck(x,4194304)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(264.0,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?text,5,@x,@y,@offset),0)
 NfpCheck(x,5242880)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(280.0,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpFont,?text,6,@x,@y,@offset),0)
 NfpCheck(x,6291456)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(296.0,34.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProp,10.0,60.0,?text,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProp,200.0000000000,60.0,?char0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProp,208.4726562500,60.0,?char1,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProp,216.9453125000,60.0,?char2,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProp,225.3007812500,60.0,?char3,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProp,232.5546875000,60.0,?char4,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpProp,241.8417968750,60.0,?char5,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpProp,?text,0,@x,@y,@offset),0)
 NfpCheck(x,0)
 NfpCheck(offset,0)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(200.0000000000,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,277631),0)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,277632),1)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpProp,?text,1,@x,@y,@offset),0)
 NfpCheck(x,555264)
 NfpCheck(offset,1)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(208.4726562500,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,832895),1)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,832896),2)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpProp,?text,2,@x,@y,@offset),0)
 NfpCheck(x,1110528)
 NfpCheck(offset,2)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(216.9453125000,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,1384319),2)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,1384320),3)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpProp,?text,3,@x,@y,@offset),0)
 NfpCheck(x,1658112)
 NfpCheck(offset,3)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(225.3007812500,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,1895807),3)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,1895808),4)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpProp,?text,4,@x,@y,@offset),0)
 NfpCheck(x,2133504)
 NfpCheck(offset,4)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(232.5546875000,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,2437823),4)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,2437824),5)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpProp,?text,5,@x,@y,@offset),0)
 NfpCheck(x,2742144)
 NfpCheck(offset,5)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(241.8417968750,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,3044927),5)
 NfpCheck(NeonVkPortFontCaretColumnForX(@nfpProp,?text,0,3044928),6)
 NfpCheck(NeonVkPortFontCaretPoint(@nfpProp,?text,6,@x,@y,@offset),0)
 NfpCheck(x,3347712)
 NfpCheck(offset,6)
 position=10.0+MathFFromInt(x)/65536.0
 NfpCheck(NeonVkPortBox(position,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(251.0820312500,74.0,1.0,1.0,0.0,1.0,0.0,1.0,1,1),0)
 nfpCaret\font=65537 : nfpCaret\text=?text : nfpCaret\textBytes=7 : nfpCaret\column=3
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_CARET_POINT,@nfpProp,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(nfpCaret\resultY,0)
 NfpCheck(nfpCaret\resultByte,3)
 NfpCheck(nfpCaret\resultColumn,0)
 nfpCaret\line=0 : nfpCaret\xQ16=1384320
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_CARET_HIT,@nfpProp,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_TEXT_X,@nfpProp,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_TEXT_COLUMN,@nfpProp,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 nfpCaret\resultX=123 : nfpCaret\resultY=456 : nfpCaret\resultByte=789 : nfpCaret\resultColumn=17
 NfpCheck(NeonVkServiceCaret(99,@nfpProp,@nfpCaret,80),-21500)
 NfpCheck(NeonVkServiceCaret(48,@nfpProp,@nfpCaret,79),-21500)
 NfpCheck(NeonVkServiceCaret(48,@nfpProp,0,80),-21500)
 NfpCheck(NeonVkServiceCaret(48,@nfpProp,@nfpCaret+1,80),-21500)
 nfpCaret\textBytes=0
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_CARET_POINT,@nfpProp,@nfpCaret,80),-21500)
 nfpCaret\textBytes=6
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_CARET_POINT,@nfpProp,@nfpCaret,80),-21500)
 nfpCaret\textBytes=8
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_CARET_POINT,@nfpProp,@nfpCaret,80),-21500)
 nfpCaret\textBytes=4097
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_CARET_POINT,@nfpProp,@nfpCaret,80),-21500)
 nfpCaret\textBytes=7 : nfpCaret\text=@nfpCaret
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_CARET_POINT,@nfpProp,@nfpCaret,80),-21500)
 nfpCaret\text=?text : nfpCaret\column=7
 NfpCheck(NeonVkServiceCaret(#NEON_SERVICE_FONT_CARET_POINT,@nfpProp,@nfpCaret,80),-21312)
 nfpCaret\column=3
 NfpCheck(NeonVkServiceCaret(48,@nfpStale,@nfpCaret,80),-21310)
 NfpCheck(nfpCaret\resultX,123)
 NfpCheck(nfpCaret\resultY,456)
 NfpCheck(nfpCaret\resultByte,789)
 NfpCheck(nfpCaret\resultColumn,17)
 nfpApi\magic=#NEON_SERVICE_MAGIC : nfpApi\major=1 : nfpApi\minor=12
 nfpApi\bytes=48 : nfpApi\flags=#NEON_SERVICE_FONT_CARETS|#NEON_SERVICE_FONT_REFS : nfpApi\maxFonts=32 : nfpApi\dispatch=@NfpCaretDispatch
 NfpCheck(NeonServiceBindApi(@nfpApi,48,#NEON_SERVICE_FONT_CARETS),-21501)
 nfpApi\minor=13 : nfpApi\flags=#NEON_SERVICE_FONT_CARETS
 NfpCheck(NeonServiceBindApi(@nfpApi,48,#NEON_SERVICE_FONT_CARETS),-21501)
 nfpApi\flags=#NEON_SERVICE_FONT_CARETS|#NEON_SERVICE_FONT_REFS
 NfpCheck(NeonServiceBindApi(@nfpApi,48,#NEON_SERVICE_FONT_CARETS),0)
 nscReady=1 : nscContext=99 : nscFrame=1
 NfpCheck(NeonServiceFontCaretQuery(48,@nfpCaret),0)
 NfpCheck(nfpCaret\resultX,1658112)
 nfpMockMode=1
 NfpCheck(NeonServiceFontCaretQuery(48,@nfpCaret),-21505)
 NfpCheck(nfpCaret\resultX,1658112)
 nfpMockMode=2
 NfpCheck(NeonServiceFontCaretQuery(48,@nfpCaret),-21504)
 NfpCheck(nfpCaret\resultX,1658112)
 nfpMockMode=0 : nscFrame=2
 NfpCheck(NeonServiceFontCaretQuery(48,@nfpCaret),-21503)
 nscFrame=0 : nscNativeMinor=12
 NfpCheck(NeonServiceFontCaretQuery(48,@nfpCaret),-21501)
 nscNativeMinor=13 : nscCallBusy=1
 NfpCheck(NeonServiceFontCaretQuery(48,@nfpCaret),-21505)
 nscCallBusy=0 : nfpCaret\font=3
 NfpCheck(NeonServiceFontCaretQuery(48,@nfpCaret),-21501)
 nscReady=0 : nscContext=0 : nscFrame=0
 NfpCheck(NeonVkChromeFontSelect(0,nfpProp\generation,0,12),0)
 nfpCaret\font=0 : nfpCaret\column=3 : nfpCaret\line=0 : nfpCaret\xQ16=1384320
 NfpCheck(NeonVkServiceCaret(48,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(NeonVkServiceCaret(49,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 NfpCheck(NeonVkServiceCaret(50,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(NeonVkServiceCaret(51,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 NfpCheck(NeonVkChromeFontPixelHeight(0),12)
 NfpCheck(NeonVkChromeFontSelect(0,nfpProp\generation,1,12),0)
 nfpCaret\font=1 : nfpCaret\column=3 : nfpCaret\line=0 : nfpCaret\xQ16=1384320
 NfpCheck(NeonVkServiceCaret(48,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(NeonVkServiceCaret(49,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 NfpCheck(NeonVkServiceCaret(50,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(NeonVkServiceCaret(51,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 NfpCheck(NeonVkChromeFontPixelHeight(1),12)
 NfpCheck(NeonVkChromeFontSelect(0,nfpProp\generation,2,12),0)
 nfpCaret\font=2 : nfpCaret\column=3 : nfpCaret\line=0 : nfpCaret\xQ16=1384320
 NfpCheck(NeonVkServiceCaret(48,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(NeonVkServiceCaret(49,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 NfpCheck(NeonVkServiceCaret(50,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(NeonVkServiceCaret(51,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 NfpCheck(NeonVkChromeFontPixelHeight(2),12)
 NfpCheck(NeonVkChromeFontSelect(0,nfpProp\generation,3,12),0)
 nfpCaret\font=3 : nfpCaret\column=3 : nfpCaret\line=0 : nfpCaret\xQ16=1384320
 NfpCheck(NeonVkServiceCaret(48,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(NeonVkServiceCaret(49,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 NfpCheck(NeonVkServiceCaret(50,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultX,1658112)
 NfpCheck(NeonVkServiceCaret(51,0,@nfpCaret,80),0)
 NfpCheck(nfpCaret\resultColumn,3)
 NfpCheck(NeonVkChromeFontPixelHeight(3),12)
 nfpApi\minor=13 : nfpApi\flags=#NEON_SERVICE_FONT_REFS|#NEON_SERVICE_FONT_CARETS|#NEON_SERVICE_ROLE_CARETS
 NfpCheck(NeonServiceBindApi(@nfpApi,48,#NEON_SERVICE_ROLE_CARETS),-21501)
 nfpApi\minor=14 : nfpApi\flags=#NEON_SERVICE_FONT_REFS|#NEON_SERVICE_ROLE_CARETS
 NfpCheck(NeonServiceBindApi(@nfpApi,48,#NEON_SERVICE_ROLE_CARETS),-21501)
 nfpApi\flags=#NEON_SERVICE_FONT_REFS|#NEON_SERVICE_FONT_CARETS|#NEON_SERVICE_ROLE_CARETS
 NfpCheck(NeonServiceBindApi(@nfpApi,48,#NEON_SERVICE_ROLE_CARETS),0)
 nscReady=1 : nscContext=99 : nscFrame=1
 NfpCheck(NeonServiceFontCaretQuery(48,@nfpCaret),0)
 NfpCheck(nfpCaret\resultX,1658112)
 nscReady=0 : nscContext=0 : nscFrame=0
 NfpCheck(NeonVkChromeEnd(),0)
 NfpCheck(NeonVkChromeFrameRasterDelta(),0)
 NfpCheck(NeonVkChromeFrameUploadDelta(),0)
 NfpCheck(NeonVkChromePresentConsume(),1)
 For i=0 To 122904 Step 8 : PokeI(#NFP_PIXELS+i,$A5A5A5A5A5A5A5A5) : Next
 For row=0 To 1
 For part=0 To 1
  src=imageBase+(40+row*80)*pitch+(20+part*380)*4
  dst=#NFP_PIXELS+16+(row*2+part)*30720
  For i=0 To 31
   For j=0 To 952 Step 8 : PokeI(dst+i*960+j,PeekI(src+i*pitch+j)) : Next
  Next
 Next
 Next
 ProcedureReturn nfpFailure
EndProcedure
Procedure NfpRetired(report.i)
 NfpCheck(NeonVkChromeReady(),0)
 NfpCheck(NeonDrawBackendActive(),0)
 NfpCheck(Neon_Ready(),0)
EndProcedure
DataSection
text: Data.a 65,86,65,84,65,82,0
hidden: Data.a 65,9,240,159,152,128,66,0
multiline: Data.a 65,10,66,0
char0: Data.a 65,0
char1: Data.a 86,0
char2: Data.a 65,0
char3: Data.a 84,0
char4: Data.a 65,0
char5: Data.a 82,0
EndDataSection
