Global Dim streamX0.i[8]
Global Dim streamY0.i[8]
Global Dim streamX1.i[8]
Global Dim streamY1.i[8]
Global Dim streamSeed.i[5]
Global Dim streamLayoutSeed.i[7]

Procedure streamSegments()
 streamX0[0]=4 : streamY0[0]=4 : streamX1[0]=28 : streamY1[0]=4
 streamX0[1]=28 : streamY0[1]=8 : streamX1[1]=4 : streamY1[1]=8
 streamX0[2]=4 : streamY0[2]=12 : streamX1[2]=4 : streamY1[2]=28
 streamX0[3]=8 : streamY0[3]=28 : streamX1[3]=8 : streamY1[3]=12
 streamX0[4]=12 : streamY0[4]=12 : streamX1[4]=12 : streamY1[4]=12
 streamX0[5]=20 : streamY0[5]=16 : streamX1[5]=52 : streamY1[5]=24
 streamX0[6]=20 : streamY0[6]=32 : streamX1[6]=28 : streamY1[6]=60
 streamX0[7]=60 : streamY0[7]=44 : streamX1[7]=28 : streamY1[7]=36
EndProcedure

Procedure.i streamMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure streamCapture(base.i,pitch.i,frame.i)
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


Global Dim outlineX.i[5]
Global Dim outlineY.i[5]

Procedure.i outlineReference(n.i,colour.i)
 Define first.i,p.i,i.i,j.i
 first=NeonVkChromeLinesReserve(n)
 If first<0 : ProcedureReturn first : EndIf
 p=NeonVkChromeVertexAddress(first)
 For i=0 To n-1
  j=i+1 : If j=n : j=0 : EndIf
  NeonVkChromeLineQuadAt(p+i*144,outlineX[i],outlineY[i],outlineX[j],outlineY[j])
 Next
 ProcedureReturn NeonVkChromeLinesDraw(first,n,colour)
EndProcedure

Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define turn.i,path.i,i.i,rc.i,lw.i,lh.i,old.i,slots.i,row.i,unchanged.i,newBase.i
 Define pixel.l
 outlineX[0]=8 : outlineY[0]=8 : outlineX[1]=36 : outlineY[1]=8
 outlineX[2]=36 : outlineY[2]=36 : outlineX[3]=36 : outlineY[3]=36
 outlineX[4]=8 : outlineY[4]=36
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,64,128)
 If rc<>0 : ProcedureReturn 731 : EndIf
 pixel=$FFFFFFFF : rc=NeonVkChromeImageSpriteReplaceBGRAId(1,@pixel,1,1)
 If rc<>0 : ProcedureReturn 732 : EndIf
 For turn=0 To 3
  lw=800 : lh=1280 : If turn=1 Or turn=3 : lw=1280 : lh=800 : EndIf
  rc=NeonVkChromeRebind(fb,lw,lh,800,1280,pitch,turn*90)
  If rc<>0 : ProcedureReturn 733 : EndIf
  For path=0 To 1
   SafetyWatchdogPet() : rc=NeonVkChromeBegin(@nwClear[0])
   If rc=0 : rc=NeonVkChromeImageSpriteDrawId(1,0,0,0,0,1,1,64,64,$FFFF0000) : EndIf
   If rc=0 : rc=Neon_Box(2,2,60,60,$FF000080) : EndIf
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 734 : EndIf
   If path=0
    rc=NeonFanBegin()
    For i=0 To 3 : NeonFanPoint(outlineX[i],outlineY[i]) : Next
    If rc=0 : rc=NeonFanOutline($80FFFFFF) : EndIf
    If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 735 : EndIf
    old=nvcFanIndexedClose : slots=nvcVertices
    For i=0 To 23 : PokeA($E1C00800+turn*32+i,PeekA(nvcOutlineMapped+old*4+i)) : Next
    rc=NeonFanOutline($80FFFF00)
    If rc<>0 Or nvcVertices<>slots Or nvcOutlinePointsUsed<>4 Or nvcOutlineClosingsUsed<>1 : NeonVkChromeAbort() : ProcedureReturn 736 : EndIf
   Else
    rc=outlineReference(4,$80FFFFFF)
    If rc=0 : rc=outlineReference(4,$80FFFF00) : EndIf
    If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 737 : EndIf
   EndIf
   rc=Neon_Box(50,4,4,4,$FF00FFFF)
   If rc=0 : rc=NeonVkChromeImageSpriteDrawId(1,52,52,0,0,1,1,8,8,$FFFFFF00) : EndIf
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 738 : EndIf
   Neon_ScissorSet(0,20,64,44)
   If path=0
    NeonFanPoint(outlineX[4],outlineY[4])
    rc=NeonFanOutline($FF00FF00)
    unchanged=1
    For i=0 To 23 : If PeekA($E1C00800+turn*32+i)<>PeekA(nvcOutlineMapped+old*4+i) : unchanged=0 : EndIf : Next
    newBase=PeekL(nvcOutlineMapped+nvcOutlinePointBase+(nvcFanIndexedStart+4)*4)
    If rc<>0 Or unchanged<>1 Or old=nvcFanIndexedClose Or newBase<>90 Or nvcOutlinePointsUsed<>5 Or nvcOutlineClosingsUsed<>2 : NeonVkChromeAbort() : ProcedureReturn 739 : EndIf
   Else
    rc=outlineReference(5,$FF00FF00)
    If rc=0 : rc=NeonFanBegin() : EndIf
    For i=0 To 4 : NeonFanPoint(outlineX[i],outlineY[i]) : Next
   EndIf
   If rc=0 : rc=NeonFanEnd($800000FF) : EndIf
   Neon_ScissorClear()
   If rc=0 : rc=Neon_Box(44,16,8,8,$FF00FF00) : EndIf
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 740 : EndIf
   If path=0
    row=$E1C00400+turn*96
    PokeI(row,Neon_Draws()) : PokeI(row+8,Neon_Verts())
    PokeI(row+16,Neon_TexDraws()) : PokeI(row+24,Neon_TexVerts())
    PokeI(row+32,nvcDrawCount) : PokeI(row+40,nvcVertices)
    PokeI(row+48,nvcOutlinePointsUsed) : PokeI(row+56,nvcOutlineClosingsUsed)
    PokeI(row+64,nvcOutlineEdgesUsed) : PokeI(row+72,1)
    PokeI(row+80,unchanged) : PokeI(row+88,newBase)
    If Neon_Draws()<>7 Or Neon_Verts()<>23 Or Neon_TexDraws()<>2 Or Neon_TexVerts()<>12 Or nvcDrawCount<>12 Or nvcVertices<>38 Or nvcOutlineEdgesUsed<>4 : NeonVkChromeAbort() : ProcedureReturn 741 : EndIf
   EndIf
   SafetyWatchdogPet() : rc=NeonVkChromeEnd()
   If rc<>0 Or NeonVkChromePresentConsume()<>1 : PokeI($E1C01310,rc) : ProcedureReturn 742 : EndIf
   streamCapture(base,pitch,turn*2+path) : PokeI($E1C01008,turn*2+path+1)
  Next
 Next
 NeonVkChromeDestroy()
 ProcedureReturn 0
EndProcedure
