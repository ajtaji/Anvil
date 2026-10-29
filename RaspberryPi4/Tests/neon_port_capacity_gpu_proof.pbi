XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_port.pbi"
Global Dim npcGpuXY.l[8196]
Procedure.i NpcGpuMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure NpcGpuCapture(base.i,pitch.i,frame.i)
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


Procedure.i NpcGpuProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define turn.i,kind.i,i.i,rc.i,lw.i,lh.i,row.i,present.i
 NeonVkChromeDestroy()
 SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,6144,65536)
 If rc<>0 : ProcedureReturn 701 : EndIf
 For i=0 To 4097 : npcGpuXY[i*2]=MathBitsOf(-64.0) : npcGpuXY[i*2+1]=MathBitsOf(-64.0) : Next
 npcGpuXY[8192]=MathBitsOf(4.0) : npcGpuXY[8193]=MathBitsOf(8.0)
 npcGpuXY[8194]=MathBitsOf(28.0) : npcGpuXY[8195]=MathBitsOf(8.0)
 nwClear[0]=0 : nwClear[1]=0 : nwClear[2]=0 : nwClear[3]=$3F800000
 For turn=0 To 3
  lw=800 : lh=1280 : If turn=1 Or turn=3 : lw=1280 : lh=800 : EndIf
  rc=NeonVkChromeRebind(fb,lw,lh,800,1280,pitch,turn*90)
  If rc<>0 : ProcedureReturn 702 : EndIf
  rc=NeonVkPortCanvas(lw,lh,lw,lh)
  If rc<>0 : ProcedureReturn 703 : EndIf
  For kind=0 To 2
   SafetyWatchdogPet()
   rc=NeonVkChromeBegin(@nwClear[0])
   If rc<>0 : ProcedureReturn 704 : EndIf
   If kind=0
    rc=NeonVkPortStaticLines(@npcGpuXY[0],4098,1.0,1.0,1.0,1.0,0)
   Else
    rc=NeonVkPortPolygon(-64.0,-64.0,8.0,8.0,2049,1.0,1.0,1.0,1.0,2-kind,0,1)
    If rc=0 : rc=NeonVkPortBox(4.0,4.0,24.0,24.0,0.0,1.0,0.0,1.0,0,1) : EndIf
   EndIf
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 705+kind : EndIf
   row=$E1C00400+(turn*3+kind)*48
   PokeI(row,rc) : PokeI(row+8,Neon_Verts()) : PokeI(row+16,Neon_Draws())
   PokeI(row+24,NeonVkChromeVertexCount()) : PokeI(row+32,NeonVkChromeDrawCount())
   SafetyWatchdogPet()
   rc=NeonVkChromeEnd() : present=NeonVkChromePresentConsume()
   PokeI(row+40,present)
   If rc<>0 Or present<>1 : ProcedureReturn 708 : EndIf
   NpcGpuCapture(base,pitch,turn*3+kind)
   PokeI($E1C01008,turn*3+kind+1)
  Next
 Next
 rc=NeonVkChromeDestroyChecked()
 If rc<>0 : ProcedureReturn 709 : EndIf
 ProcedureReturn 0
EndProcedure
