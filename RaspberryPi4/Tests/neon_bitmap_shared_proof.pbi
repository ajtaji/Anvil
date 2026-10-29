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
 Define ch.i,row.i,bold.i,i.i,index.i,rc.i
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 NeonFontDefaults()
 NeonFontSetup(1,1,1) : NeonFontSetup(2,2,0) : NeonFontSetup(3,2,-1)
 For i=0 To 1519 : PokeA($E1C01200+i,PeekA(neon_fbits+i)) : Next
 For ch=32 To 126
  For row=0 To 15
   For bold=0 To 1
    PokeA($E1C00400+index,NeonBitmapGlyphRow(ch,row,bold)) : index=index+1
   Next
  Next
 Next
 For i=-1 To 4
  PokeI($E1C01800+(i+1)*32,i)
  PokeI($E1C01808+(i+1)*32,Neon_CharWidth(i))
  PokeI($E1C01810+(i+1)*32,NeonBitmapLineHeight(i))
  PokeI($E1C01818+(i+1)*32,NeonBitmapFontBold(i))
 Next
 PokeI($E1C01010,index)
 PokeI($E1C01018,Neon_FontUI()) : PokeI($E1C01020,Neon_FontSmall())
 PokeI($E1C01028,Neon_FontMono()) : PokeI($E1C01030,Neon_FontBold())
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,128,1024)
 If rc<>0 : ProcedureReturn 801 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc=0 : rc=NeonVkChromeText(0,0,0,"A",$FFFFFFFF) : EndIf
 If rc=0 : rc=NeonVkChromeText(1,16,0,"B",$FF00FF00) : EndIf
 If rc=0 : rc=NeonVkChromeText(2,0,24,"C",$FFFFFF00) : EndIf
 If rc=0 : rc=NeonVkChromeText(3,24,24,"D",$FF00FFFF) : EndIf
 If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 802 : EndIf
 PokeI($E1C01038,Neon_Draws()) : PokeI($E1C01040,Neon_Verts())
 PokeI($E1C01048,nvcDrawCount) : PokeI($E1C01050,nvcVertices)
 SafetyWatchdogPet() : rc=NeonVkChromeEnd()
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : ProcedureReturn 803 : EndIf
 streamCapture(base,pitch,0) : PokeI($E1C01008,1)
 NeonVkChromeDestroy() : ProcedureReturn 0
EndProcedure
