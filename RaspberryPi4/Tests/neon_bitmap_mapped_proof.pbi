XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pbi"
Procedure.i NbmMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure NbmCapture(base.i,pitch.i,frame.i)
 Define x.i,y.i,px.i,py.i
 For y=0 To 63
  For x=0 To 63
   If nvcRotation=90 : px=nvcLogicalH-1-y : py=x
   ElseIf nvcRotation=180 : px=nvcLogicalW-1-x : py=nvcLogicalH-1-y
   ElseIf nvcRotation=270 : px=y : py=nvcLogicalW-1-x
   Else : px=x : py=y : EndIf
   PokeL($E2400000+frame*16384+(y*64+x)*4,PeekL(base+py*pitch+px*4))
  Next
 Next
EndProcedure



Procedure.i NbmRefusalClean(freeRows.i)
 Define i.i
 If nvcVertices<>0 Or nvcDrawCount<>0 Or Neon_Verts()<>0 Or Neon_Draws()<>0 Or nvcGlyphs<>0 Or nvcRuns<>0 Or avkRecordedDrawFreeCount<>freeRows : ProcedureReturn 0 : EndIf
 For i=0 To 15 : If PeekA(nvcMapped+i)<>$A5 : ProcedureReturn 0 : EndIf : Next
 ProcedureReturn 1
EndProcedure

Procedure.i NbmProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define turn.i,kind.i,i.i,rc.i,lw.i,lh.i,row.i,present.i,oldLimit.i,freeRows.i,oldGeneration.i,uvAddress.i,savedUV.i,checkRow.i
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 NeonFontDefaults() : NeonFontSetup(1,1,1)
 For i=0 To 1519 : PokeA($E1C01400+i,PeekA(neon_fbits+i)) : Next
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,128,1024)
 If rc<>0 : ProcedureReturn 901 : EndIf
 nwClear[0]=0 : nwClear[1]=0 : nwClear[2]=0 : nwClear[3]=$3F800000
 For turn=0 To 3
  lw=800 : lh=1280 : If turn=1 Or turn=3 : lw=1280 : lh=800 : EndIf
  rc=NeonVkChromeRebind(fb,lw,lh,800,1280,pitch,turn*90)
  If rc<>0 : ProcedureReturn 902 : EndIf
  For kind=0 To 5
   SafetyWatchdogPet()
   rc=NeonVkChromeBegin(@nwClear[0])
   If rc<>0 : ProcedureReturn 903 : EndIf
   If kind=1
    rc=NeonVkPortCanvas(lw,lh,lw,lh)
    If rc=0 : rc=NeonVkPortCamera(MathFFromInt(8-lw/4),MathFFromInt(8-lh/4),2.0) : EndIf
    If rc=0 : rc=NeonVkPortText(1,10.0,10.0,"AB",0.0,1.0,0.0,1.0,0,0) : EndIf
   ElseIf kind=4
    rc=NeonVkPortCanvas(lw*2,lh*2,lw,lh)
    If rc=0 : rc=NeonVkPortText(0,8.0,8.0,"A",1.0,1.0,1.0,1.0,1,1) : EndIf
   Else
    rc=NeonVkPortCanvas(lw/2,lh/2,lw,lh)
    If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 904 : EndIf
    If kind=0
     PokeI($E1C01010,MathFToInt(NeonVkPortTextWidth(0,"A A",1)))
     rc=NeonVkPortTextRight(0,26.0,2.0,"A A",1.0,1.0,1.0,1.0,1,1)
    ElseIf kind=2
     rc=NeonVkPortTextCentre(0,0.0,27.0,2.0,"A A",1.0,1.0,1.0,1.0,1,1)
    ElseIf kind=3
     Neon_ScissorSet(12,8,16,16)
     rc=NeonVkPortText(0,2.0,2.0,"A",1.0,1.0,1.0,1.0,1,1)
    Else
     oldLimit=nvcMaxVertexQuads : freeRows=avkRecordedDrawFreeCount
     For i=0 To 15 : PokeA(nvcMapped+i,$A5) : Next
     nvcMaxVertexQuads=1
     rc=NeonVkPortText(0,2.0,2.0,"AB",1.0,1.0,1.0,1.0,1,1)
     If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or nvcVertices<>0 Or nvcDrawCount<>0 Or Neon_Verts()<>0 Or nvcGlyphs<>0 Or nvcRuns<>0 Or avkRecordedDrawFreeCount<>freeRows : NeonVkChromeAbort() : ProcedureReturn 905 : EndIf
     For i=0 To 15 : If PeekA(nvcMapped+i)<>$A5 : NeonVkChromeAbort() : ProcedureReturn 906 : EndIf : Next
     nvcMaxVertexQuads=oldLimit
     checkRow=$E1C00C00+turn*128
     PokeI(checkRow,1)
     rc=NeonVkChromeTextMapped(0,131072,131072,"AB",$FFFFFFFF,0,lh/2,lw,lh,0,0,65536,1)
     PokeI(checkRow+8,rc)
     If rc<>#NEON_VK_CHROME_ERR_ARGS Or NbmRefusalClean(freeRows)=0 : NeonVkChromeAbort() : ProcedureReturn 915 : EndIf
     rc=NeonVkChromeTextMapped(0,65536000001,131072,"AB",$FFFFFFFF,lw/2,lh/2,lw,lh,0,0,65536,1)
     PokeI(checkRow+16,rc)
     If rc<>#NEON_VK_CHROME_ERR_CAPACITY Or NbmRefusalClean(freeRows)=0 : NeonVkChromeAbort() : ProcedureReturn 916 : EndIf
     rc=NeonVkChromeTextMapped(0,131072,131072,"AB",$FFFFFFFF,lw/2,lh/2,lw,lh,0,0,1048577,1)
     PokeI(checkRow+24,rc)
     If rc<>#NEON_VK_CHROME_ERR_ARGS Or NbmRefusalClean(freeRows)=0 : NeonVkChromeAbort() : ProcedureReturn 917 : EndIf
     oldGeneration=nvcAtlasGeneration : nvcAtlasGeneration=oldGeneration-1
     rc=NeonVkPortText(0,2.0,2.0,"AB",1.0,1.0,1.0,1.0,1,1)
     nvcAtlasGeneration=oldGeneration : PokeI(checkRow+32,rc)
     If rc<>#NEON_VK_CHROME_ERR_ATLAS Or NbmRefusalClean(freeRows)=0 : NeonVkChromeAbort() : ProcedureReturn 918 : EndIf
     nvcGridBatchActive=1
     rc=NeonVkPortText(0,2.0,2.0,"AB",1.0,1.0,1.0,1.0,1,1)
     nvcGridBatchActive=0 : PokeI(checkRow+40,rc)
     If rc<>#NEON_VK_CHROME_ERR_STATE Or NbmRefusalClean(freeRows)=0 : NeonVkChromeAbort() : ProcedureReturn 919 : EndIf
     uvAddress=neon_glyphUV+(66-neon_ffirst)*16+4
     savedUV=PeekL(uvAddress) : PokeL(uvAddress,$40000000)
     rc=NeonVkPortText(0,2.0,2.0,"AB",1.0,1.0,1.0,1.0,1,1)
     PokeL(uvAddress,savedUV) : PokeI(checkRow+48,rc)
     If rc<>#NEON_VK_CHROME_ERR_ATLAS Or NbmRefusalClean(freeRows)=0 : NeonVkChromeAbort() : ProcedureReturn 920 : EndIf
     Neon_ScissorSet(0,0,0,0)
     rc=NeonVkPortText(0,2.0,2.0,"AB",1.0,1.0,1.0,1.0,1,1)
     Neon_ScissorClear() : PokeI(checkRow+56,rc)
     PokeI(checkRow+80,nvcClipped)
     If nvcClipped<>1 : NeonVkChromeAbort() : ProcedureReturn 923 : EndIf
     If rc<>0 Or NbmRefusalClean(freeRows)=0 : NeonVkChromeAbort() : ProcedureReturn 921 : EndIf
     rc=NeonVkPortText(0,2.0,2.0,"AB",1.0,1.0,1.0,0.0,1,1)
     PokeI(checkRow+64,rc)
     If rc<>0 Or NbmRefusalClean(freeRows)=0 : NeonVkChromeAbort() : ProcedureReturn 922 : EndIf
     PokeI(checkRow+72,1)
     rc=NeonVkPortText(0,2.0,2.0,"AB",1.0,1.0,1.0,1.0,1,1)
    EndIf
   EndIf
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 907+kind : EndIf
   row=$E1C00400+(turn*6+kind)*64
   PokeI(row,rc) : PokeI(row+8,Neon_Verts()) : PokeI(row+16,Neon_Draws())
   PokeI(row+24,NeonVkChromeVertexCount()) : PokeI(row+32,NeonVkChromeDrawCount())
   PokeI(row+40,nvcGlyphs) : PokeI(row+48,nvcRuns)
   Neon_ScissorClear() : SafetyWatchdogPet()
   rc=NeonVkChromeEnd() : present=NeonVkChromePresentConsume() : PokeI(row+56,present)
   If rc<>0 Or present<>1 : ProcedureReturn 913 : EndIf
   NbmCapture(base,pitch,turn*6+kind) : PokeI($E1C01008,turn*6+kind+1)
  Next
 Next
 rc=NeonVkChromeDestroyChecked()
 If rc<>0 : ProcedureReturn 914 : EndIf
 ProcedureReturn 0
EndProcedure
