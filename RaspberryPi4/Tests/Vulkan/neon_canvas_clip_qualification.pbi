; SPDX-License-Identifier: MIT
; Actual existing Neon widget scene, virtual canvas and physical DSI transfer.
#CRC_POLY=$EDB88320
XIncludeFile "Anvil/Core/crc.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_canvas.pbi"
Global NcdFailure.i,NcdChecks.i,NcdCanvas.NeonVkCanvas
Global Dim NcdScratch.q[240000]
Global Dim NcdClear.l[4]
Global Dim NcdRgbRow.a[2400]
Procedure NcdCheck(actual.i,expected.i)
  PokeI($E1C00400+NcdChecks*16,actual)
  PokeI($E1C00408+NcdChecks*16,expected)
  NcdChecks=NcdChecks+1
  If actual<>expected And NcdFailure=0 : NcdFailure=NcdChecks : EndIf
  PokeI($E1C00010,NcdFailure) : PokeI($E1C00018,NcdChecks)
EndProcedure
Procedure.i NcdRgbCrc(base.i,pitch.i)
  Protected crc.i=$FFFFFFFF,x.i,y.i,colour.i
  For y=0 To 1279
    For x=0 To 799
      colour=PeekL(base+y*pitch+x*4)
      PokeA(@NcdRgbRow[0]+x*3,(colour>>16)&255)
      PokeA(@NcdRgbRow[0]+x*3+1,(colour>>8)&255)
      PokeA(@NcdRgbRow[0]+x*3+2,colour&255)
    Next
    crc=Crc32Part(crc,@NcdRgbRow[0],2400)
  Next
  ProcedureReturn crc!$FFFFFFFF
EndProcedure


Global Dim NcdClipBytes.q[40]
Procedure.i NcdClipQualification()
  Protected d.i,r.i,j.i,k.i,x.i,y.i,tx.i,ty.i,bits.i,wanted.i,count.i,fail.i
  Protected ow.i=nvcPhysicalW,oh.i=nvcPhysicalH,lw.i=nvcLogicalW,lh.i=nvcLogicalH,rot.i=nvcRotation
  Protected mapped.i=nvcMapped,vertices.i=nvcVertices
  For d=0 To 5
    nvcPhysicalW=800 : nvcPhysicalH=600
    If d=1 Or d=4 : nvcPhysicalH=1280 : EndIf
    If d=3 : nvcPhysicalW=513 : nvcPhysicalH=777 : EndIf
    nvcClipXBits2(nvcPhysicalW) : nvcClipYBits2(nvcPhysicalH)
    For r=0 To 3
      nvcRotation=r*90
      nvcLogicalW=nvcPhysicalW : nvcLogicalH=nvcPhysicalH
      If r=1 Or r=3 : nvcLogicalW=nvcPhysicalH : nvcLogicalH=nvcPhysicalW : EndIf
      For j=0 To 79
        x=-10000+j*257 : y=10000-j*233
        tx=x : ty=y
        If r=1 : tx=nvcLogicalH*2-y : ty=x : EndIf
        If r=2 : tx=nvcLogicalW*2-x : ty=nvcLogicalH*2-y : EndIf
        If r=3 : tx=y : ty=nvcLogicalW*2-x : EndIf
        wanted=(GraphicsF32RatioBits(tx-nvcPhysicalW,nvcPhysicalW)&$FFFFFFFF) | ((GraphicsF32RatioBits(ty-nvcPhysicalH,nvcPhysicalH)&$FFFFFFFF)<<32)
        bits=nvcLinePosW(x,y) : count=count+1 : If bits<>wanted : fail=fail+1 : EndIf
        bits=nvcLinePos(x,y) : count=count+1 : If bits<>wanted : fail=fail+1 : EndIf
      Next
      For j=0 To 7
        x=7+j*31 : y=23+j*17
        nvcMapped=@NcdClipBytes[0]+4 : nvcVertices=0
        nvcLineQuad(x,y,x+31-j*7,y+j*13)
        NeonVkChromeLineQuadAt(@NcdClipBytes[20],x,y,x+31-j*7,y+j*13)
        For k=0 To 143
          count=count+1
          If PeekA(@NcdClipBytes[0]+4+k)<>PeekA(@NcdClipBytes[20]+k) : fail=fail+1 : EndIf
        Next
      Next
    Next
  Next
  nvcPhysicalW=ow : nvcPhysicalH=oh : nvcLogicalW=lw : nvcLogicalH=lh : nvcRotation=rot
  nvcMapped=mapped : nvcVertices=vertices
  PokeI($E1C000E8,fail) : PokeI($E1C000F0,count)
  ProcedureReturn fail
EndProcedure
Procedure.i NcdFrame(dev.i,renderPass.i,framebuffer.i,base.i,pitch.i)
  Protected rc.i,i.i,scratch.i,ops.i,fallbacks.i,refusals.i,k.i,t0.i,t1.i,t2.i,t3.i
  Protected image.i,memory.i,view.i,target.NeonVkTargetInfo,point.NeonCanvasPoint
  PokeI($E1C00040,TickHz()) : PokeI($E1C00048,3)
  PokeI($E1C00050,48) : PokeI($E1C00058,800) : PokeI($E1C00060,600)
  PokeI($E1C000B0,4096000) : PokeI($E1C000E0,1920000)

  If NcdClipQualification()<>0 : NcdFailure=9002 : Goto NcdCleanup : EndIf
  NcdCheck(NeonVkChromeRebind(framebuffer,1280,800,800,1280,pitch,90),0)
  NcdCheck(NeonVkCanvasInit(@NcdCanvas,SizeOf(NeonVkCanvas)),0)
  t0=Ticks()
  NcdCheck(NeonVkCanvasCreate(@NcdCanvas,800,600,1,@NcdScratch[0],1920000),0)
  PokeI($E1C000C0,Ticks()-t0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  image=NcdCanvas\image : memory=NcdCanvas\memory : view=NcdCanvas\view
  PokeI($E1C00068,NcdCanvas\viewport\x) : PokeI($E1C00070,NcdCanvas\viewport\y)
  PokeI($E1C00078,NcdCanvas\viewport\width) : PokeI($E1C00080,NcdCanvas\viewport\height)

  NcdCheck(NeonVkCanvasMapPoint(@NcdCanvas,640,400,@point),1)
  NcdCheck(point\xQ16,26214400)
  NcdCheck(point\yQ16,19660800)
  NcdCheck(DisplayAdopt(#NW_DSI_SCAN,#NW_SURFACE_PITCH,#NVWA_WIDTH,#NVWA_HEIGHT,32),1)
  scratch=@nwDmaScratch[0]+255 : scratch=scratch-(scratch%256)
  NcdCheck(DmaSetScratch(scratch,512),1)
  NcdCheck(DisplayDmaBind(),1)
  NcdCheck(DmaInit(),1)
  DisplayDmaReadback(1) : DisplayUseDma(1)
  NcdCheck(NeonVkChromeAsync(1),0)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  i=0 : t0=Ticks()
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  PokeI($E1C01000+i*128+0,Ticks())
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NvwaCompose(),0)
  PokeI($E1C01000+i*128+8,Ticks())
  NcdCheck(Neon_Box(48,480,32,16,$FF20A0F0),0)
  NcdCheck(NeonVkChromeDrawCount(),48)
  PokeI($E1C000B8,NeonVkChromeVertexCount())
  NcdCheck(NeonVkCanvasEnd(@NcdCanvas),0)
  PokeI($E1C01000+i*128+16,Ticks())
  For k=0 To 5 : PokeI($E1C02000+i*128+k*8,avkV3dProf[k]) : Next
  PokeI($E1C02400+i*64+0,Neon_UsBegin()) : PokeI($E1C02408+i*64+0,Neon_UsClean())
  PokeI($E1C02410+i*64+0,Neon_UsBin()) : PokeI($E1C02418+i*64+0,Neon_UsRender())
  PokeI($E1C02800+i*128+0,v3d_tProf0)
  PokeI($E1C02800+i*128+8,v3d_tProf1)
  PokeI($E1C02800+i*128+16,v3d_tProf2)
  PokeI($E1C02800+i*128+24,v3d_tProf3)
  PokeI($E1C02800+i*128+32,v3d_tProf4)
  PokeI($E1C02800+i*128+40,v3d_tProf5)
  PokeI($E1C02800+i*128+48,v3d_tProf6)
  t1=Ticks()
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NeonVkChromeBegin(@NcdClear[0]),0)
  PokeI($E1C01000+i*128+24,Ticks())
  NcdCheck(NeonVkCanvasDrawPassthrough(@NcdCanvas),0)
  PokeI($E1C01000+i*128+32,Ticks())
  NcdCheck(NeonVkChromeEnd(),0)
  PokeI($E1C01000+i*128+40,Ticks())
  NcdCheck(NeonVkChromeFinish(),0)
  PokeI($E1C01000+i*128+48,Ticks())
  NcdCheck(NeonVkChromePresentValidate(),1)
  For k=0 To 5 : PokeI($E1C02040+i*128+k*8,avkV3dProf[k]) : Next
  PokeI($E1C02400+i*64+32,Neon_UsBegin()) : PokeI($E1C02408+i*64+32,Neon_UsClean())
  PokeI($E1C02410+i*64+32,Neon_UsBin()) : PokeI($E1C02418+i*64+32,Neon_UsRender())
  PokeI($E1C02800+i*128+64,v3d_tProf0)
  PokeI($E1C02800+i*128+72,v3d_tProf1)
  PokeI($E1C02800+i*128+80,v3d_tProf2)
  PokeI($E1C02800+i*128+88,v3d_tProf3)
  PokeI($E1C02800+i*128+96,v3d_tProf4)
  PokeI($E1C02800+i*128+104,v3d_tProf5)
  PokeI($E1C02800+i*128+112,v3d_tProf6)
  t2=Ticks()
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  ops=DisplayDmaOps() : fallbacks=DisplayDmaFallbacks() : refusals=DisplayDmaRefusals()
  DisplayBlit(base,pitch,0,0,800,1280)
  NcdCheck(DisplayDmaOps()-ops,1)
  NcdCheck(DisplayDmaFallbacks()-fallbacks,0)
  NcdCheck(DisplayDmaRefusals()-refusals,0)
  NcdCheck(NeonVkChromePresentConsume(),1)
  t3=Ticks()
  PokeI($E1C00100+i*32,t0) : PokeI($E1C00108+i*32,t1)
  PokeI($E1C00110+i*32,t2) : PokeI($E1C00118+i*32,t3)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  i=1 : t0=Ticks()
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  PokeI($E1C01000+i*128+0,Ticks())
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NvwaCompose(),0)
  PokeI($E1C01000+i*128+8,Ticks())
  NcdCheck(Neon_Box(48,480,40,16,$FF20A0F0),0)
  NcdCheck(NeonVkChromeDrawCount(),48)
  PokeI($E1C000B8,NeonVkChromeVertexCount())
  NcdCheck(NeonVkCanvasEnd(@NcdCanvas),0)
  PokeI($E1C01000+i*128+16,Ticks())
  For k=0 To 5 : PokeI($E1C02000+i*128+k*8,avkV3dProf[k]) : Next
  PokeI($E1C02400+i*64+0,Neon_UsBegin()) : PokeI($E1C02408+i*64+0,Neon_UsClean())
  PokeI($E1C02410+i*64+0,Neon_UsBin()) : PokeI($E1C02418+i*64+0,Neon_UsRender())
  PokeI($E1C02800+i*128+0,v3d_tProf0)
  PokeI($E1C02800+i*128+8,v3d_tProf1)
  PokeI($E1C02800+i*128+16,v3d_tProf2)
  PokeI($E1C02800+i*128+24,v3d_tProf3)
  PokeI($E1C02800+i*128+32,v3d_tProf4)
  PokeI($E1C02800+i*128+40,v3d_tProf5)
  PokeI($E1C02800+i*128+48,v3d_tProf6)
  t1=Ticks()
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NeonVkChromeBegin(@NcdClear[0]),0)
  PokeI($E1C01000+i*128+24,Ticks())
  NcdCheck(NeonVkCanvasDrawPassthrough(@NcdCanvas),0)
  PokeI($E1C01000+i*128+32,Ticks())
  NcdCheck(NeonVkChromeEnd(),0)
  PokeI($E1C01000+i*128+40,Ticks())
  NcdCheck(NeonVkChromeFinish(),0)
  PokeI($E1C01000+i*128+48,Ticks())
  NcdCheck(NeonVkChromePresentValidate(),1)
  For k=0 To 5 : PokeI($E1C02040+i*128+k*8,avkV3dProf[k]) : Next
  PokeI($E1C02400+i*64+32,Neon_UsBegin()) : PokeI($E1C02408+i*64+32,Neon_UsClean())
  PokeI($E1C02410+i*64+32,Neon_UsBin()) : PokeI($E1C02418+i*64+32,Neon_UsRender())
  PokeI($E1C02800+i*128+64,v3d_tProf0)
  PokeI($E1C02800+i*128+72,v3d_tProf1)
  PokeI($E1C02800+i*128+80,v3d_tProf2)
  PokeI($E1C02800+i*128+88,v3d_tProf3)
  PokeI($E1C02800+i*128+96,v3d_tProf4)
  PokeI($E1C02800+i*128+104,v3d_tProf5)
  PokeI($E1C02800+i*128+112,v3d_tProf6)
  t2=Ticks()
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  ops=DisplayDmaOps() : fallbacks=DisplayDmaFallbacks() : refusals=DisplayDmaRefusals()
  DisplayBlit(base,pitch,0,0,800,1280)
  NcdCheck(DisplayDmaOps()-ops,1)
  NcdCheck(DisplayDmaFallbacks()-fallbacks,0)
  NcdCheck(DisplayDmaRefusals()-refusals,0)
  NcdCheck(NeonVkChromePresentConsume(),1)
  t3=Ticks()
  PokeI($E1C00100+i*32,t0) : PokeI($E1C00108+i*32,t1)
  PokeI($E1C00110+i*32,t2) : PokeI($E1C00118+i*32,t3)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  i=2 : t0=Ticks()
  NcdCheck(NeonVkCanvasBegin(@NcdCanvas,@NcdClear[0]),0)
  PokeI($E1C01000+i*128+0,Ticks())
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NvwaCompose(),0)
  PokeI($E1C01000+i*128+8,Ticks())
  NcdCheck(Neon_Box(48,480,48,16,$FF20A0F0),0)
  NcdCheck(NeonVkChromeDrawCount(),48)
  PokeI($E1C000B8,NeonVkChromeVertexCount())
  NcdCheck(NeonVkCanvasEnd(@NcdCanvas),0)
  PokeI($E1C01000+i*128+16,Ticks())
  For k=0 To 5 : PokeI($E1C02000+i*128+k*8,avkV3dProf[k]) : Next
  PokeI($E1C02400+i*64+0,Neon_UsBegin()) : PokeI($E1C02408+i*64+0,Neon_UsClean())
  PokeI($E1C02410+i*64+0,Neon_UsBin()) : PokeI($E1C02418+i*64+0,Neon_UsRender())
  PokeI($E1C02800+i*128+0,v3d_tProf0)
  PokeI($E1C02800+i*128+8,v3d_tProf1)
  PokeI($E1C02800+i*128+16,v3d_tProf2)
  PokeI($E1C02800+i*128+24,v3d_tProf3)
  PokeI($E1C02800+i*128+32,v3d_tProf4)
  PokeI($E1C02800+i*128+40,v3d_tProf5)
  PokeI($E1C02800+i*128+48,v3d_tProf6)
  t1=Ticks()
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(NeonVkChromeBegin(@NcdClear[0]),0)
  PokeI($E1C01000+i*128+24,Ticks())
  NcdCheck(NeonVkCanvasDrawPassthrough(@NcdCanvas),0)
  PokeI($E1C01000+i*128+32,Ticks())
  NcdCheck(NeonVkChromeEnd(),0)
  PokeI($E1C01000+i*128+40,Ticks())
  NcdCheck(NeonVkChromeFinish(),0)
  PokeI($E1C01000+i*128+48,Ticks())
  NcdCheck(NeonVkChromePresentValidate(),1)
  For k=0 To 5 : PokeI($E1C02040+i*128+k*8,avkV3dProf[k]) : Next
  PokeI($E1C02400+i*64+32,Neon_UsBegin()) : PokeI($E1C02408+i*64+32,Neon_UsClean())
  PokeI($E1C02410+i*64+32,Neon_UsBin()) : PokeI($E1C02418+i*64+32,Neon_UsRender())
  PokeI($E1C02800+i*128+64,v3d_tProf0)
  PokeI($E1C02800+i*128+72,v3d_tProf1)
  PokeI($E1C02800+i*128+80,v3d_tProf2)
  PokeI($E1C02800+i*128+88,v3d_tProf3)
  PokeI($E1C02800+i*128+96,v3d_tProf4)
  PokeI($E1C02800+i*128+104,v3d_tProf5)
  PokeI($E1C02800+i*128+112,v3d_tProf6)
  t2=Ticks()
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  ops=DisplayDmaOps() : fallbacks=DisplayDmaFallbacks() : refusals=DisplayDmaRefusals()
  DisplayBlit(base,pitch,0,0,800,1280)
  NcdCheck(DisplayDmaOps()-ops,1)
  NcdCheck(DisplayDmaFallbacks()-fallbacks,0)
  NcdCheck(DisplayDmaRefusals()-refusals,0)
  NcdCheck(NeonVkChromePresentConsume(),1)
  t3=Ticks()
  PokeI($E1C00100+i*32,t0) : PokeI($E1C00108+i*32,t1)
  PokeI($E1C00110+i*32,t2) : PokeI($E1C00118+i*32,t3)
  If NcdFailure<>0 : Goto NcdCleanup : EndIf
  NcdCheck(Bool(NcdCanvas\image=image),1)
  NcdCheck(Bool(NcdCanvas\memory=memory),1)
  NcdCheck(Bool(NcdCanvas\view=view),1)
  NcdCheck(NeonVkCanvasClose(@NcdCanvas),0)
  NcdCheck(NeonVkChromeImageSpriteAllocatedId(1),0)
  NcdCheck(AnvilVkFaultCode(),0)
  NcdCleanup:
  ; This fixture owns the final frame too. On failure, abandon only completed
  ; work and preserve a refusal rather than reporting a successful present.
  If NeonVkChromeFramePending()<>0 : NeonVkChromeFinish() : EndIf
  If NeonVkChromeFrameAbortable()<>0 : NeonVkChromeAbort() : EndIf
  If NeonVkChromePresentPending()<>0 : NeonVkChromePresentConsume() : EndIf
  If NcdCanvas\phase<>#NEON_VK_CANVAS_CLOSED
    rc=NeonVkCanvasClose(@NcdCanvas)
    If rc<>0 And NcdFailure=0 : NcdFailure=9001 : EndIf
  EndIf
  DisplayUseDma(0) : DisplayFlush()
  PokeI($E1C00098,AnvilVkFaultCount()) : PokeI($E1C000C8,AnvilVkFaultCode())
  ProcedureReturn NcdFailure
EndProcedure
