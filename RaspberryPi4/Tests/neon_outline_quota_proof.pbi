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


Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define i.i,rc.i,flatRc.i,textRc.i,verts.i,draws.i,rows.i,unchanged.i=1,start.i
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,10240,4096)
 If rc<>0 : ProcedureReturn 761 : EndIf
 NeonFontSetup(#NEON_FONT_UI,1,0)
 For i=0 To 15 : PokeA($E1C01800+i,PeekA(neon_fbits+(65-32)*16+i)) : Next
 rc=NeonVkChromeBegin(@nwClear[0]) : If rc=0 : rc=NeonFanBegin() : EndIf
 If rc<>0 : ProcedureReturn 762 : EndIf
 NeonFanPoint(4,4) : NeonFanPoint(28,4)
 Neon_ScissorSet(0,0,0,0)
 For i=0 To #NEON_MAX_DRAWS-2
  rc=NeonFanOutline($FFFFFFFF)
  If rc<>0 : NeonVkChromeAbort() : PokeI($E1C01310,rc) : ProcedureReturn 763 : EndIf
  If (i & 127)=0 : SafetyWatchdogPet() : EndIf
 Next
 Neon_ScissorClear()
 rc=NeonFanOutline($FFFFFFFF)
 If rc=0 : rc=NeonFanEnd($FF00FF00) : EndIf
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 764 : EndIf
 For i=0 To #NEON_MAX_TDRAWS-1
  If i=#NEON_MAX_TDRAWS-1
   rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",$FF00FF00)
  Else
   rc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",$FFFFFFFF)
  EndIf
  If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 765 : EndIf
  If (i & 127)=0 : SafetyWatchdogPet() : EndIf
 Next
 verts=nvcVertices : draws=nvcDrawCount : rows=avkRecordedDrawFreeCount
 For i=0 To 15 : PokeA(nvcMapped+verts*24+i,$A5) : Next
 flatRc=Neon_Box(50,50,1,1,$FFFFFFFF)
 textRc=Neon_TextTex(#NEON_FONT_UI,0,0,"A",$FFFF0000)
 If nvcVertices<>verts Or nvcDrawCount<>draws Or avkRecordedDrawFreeCount<>rows Or flatRc<>#NEON_VK_CHROME_ERR_CAPACITY Or textRc<>#NEON_VK_CHROME_ERR_CAPACITY : unchanged=0 : EndIf
 For i=0 To 15 : If PeekA(nvcMapped+verts*24+i)<>$A5 : unchanged=0 : EndIf : Next
 PokeI($E1C01010,Neon_Draws()) : PokeI($E1C01018,Neon_Verts())
 PokeI($E1C01020,Neon_TexDraws()) : PokeI($E1C01028,Neon_TexVerts())
 PokeI($E1C01030,draws) : PokeI($E1C01038,verts) : PokeI($E1C01040,rows)
 PokeI($E1C01048,flatRc) : PokeI($E1C01050,textRc) : PokeI($E1C01058,unchanged)
 PokeI($E1C01060,nvcOutlinePointsUsed) : PokeI($E1C01068,nvcOutlineClosingsUsed)
 If Neon_Draws()<>4096 Or Neon_Verts()<>2 Or Neon_TexDraws()<>2048 Or Neon_TexVerts()<>12288 Or draws<>10240 Or verts<>12291 Or rows<>0 Or unchanged<>1 Or nvcOutlinePointsUsed<>2 Or nvcOutlineClosingsUsed<>1 : NeonVkChromeAbort() : ProcedureReturn 766 : EndIf
 PokeI($E1C01700,Neon_BclBytes())
 SafetyWatchdogPet() : start=Micros() : rc=NeonVkChromeEnd() : PokeI($E1C01078,Micros()-start)
 PokeI($E1C01400,rc) : PokeI($E1C01408,nvcSubmitStage) : PokeI($E1C01410,nvcSubmitRc)
 PokeI($E1C01418,avkV3dNative) : PokeI($E1C01420,AnvilVkFaultCode()) : PokeI($E1C01428,AnvilVkFaultText())
 PokeI($E1C01430,avkFlightActive) : PokeI($E1C01438,avkFlightQuarantined)
 PokeI($E1C01440,avkV3dPend) : PokeI($E1C01448,V3dError())
 PokeI($E1C01450,neon_hwInFrame) : PokeI($E1C01458,neon_inFrame)
 PokeI($E1C01460,avkV3dAsync) : PokeI($E1C01468,#AVKQ_MAX_DRAW_SLOTS)
 For i=0 To 5 : PokeI($E1C01500+i*8,avkV3dProf[i]) : Next
 start=AnvilVkFaultText()
 If start<>0
  For i=0 To 255
   PokeA($E1C01600+i,PeekA(start+i))
   If PeekA(start+i)=0 : Break : EndIf
  Next
 EndIf
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : PokeI($E1C01318,rc) : ProcedureReturn 767 : EndIf
 streamCapture(base,pitch,0) : PokeI($E1C01008,1)
 NeonVkChromeDestroy() : PokeI($E1C01080,avkRecordedDrawFreeCount)
 ProcedureReturn 0
EndProcedure
