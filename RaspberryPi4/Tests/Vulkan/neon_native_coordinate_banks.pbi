; SPDX-License-Identifier: MIT
; Public rebind/reset paths; copy the private CPU tables only for diagnostics.
Procedure.i NeonNativeCoordinateBankProof(scratch.i,capacity.i,base.i,bytes.i)
  Protected oldBase.i,oldBytes.i,oldW.i,oldH.i,oldPitch.i,oldFormat.i,oldRot.i
  Protected i.i,w.i,h.i,rot.i,pw.i,ph.i,pitch.i,rc.i,restored.i,n.i,off.i,row.i,t0.i,failed.i,table.i
  oldBase=Neon_SurfaceBase() : oldBytes=Neon_SurfaceBytes()
  oldW=Neon_SurfaceW() : oldH=Neon_SurfaceH() : oldPitch=Neon_SurfacePitch()
  oldFormat=Neon_SurfaceFormat() : oldRot=Neon_SurfaceRotation()
  PokeI($E1C03480,$4E434231) : PokeI($E1C03488,scratch)
  For i=0 To 11
    w=800 : h=600 : rot=0
    If (i%2)<>0 : w=1280 : h=800 : rot=90 : EndIf
    Select i
      Case 4 : w=641 : h=479 : rot=180
      Case 6 : w=601 : h=799 : rot=270
      Case 8 : w=799 : h=599 : rot=0 : NeonHardwareCoordinateReset()
      Case 10 : w=799 : h=599 : rot=0
    EndSelect
    pw=w : ph=h
    If rot=90 Or rot=270 : pw=h : ph=w : EndIf
    If pw>Neon_CapacityPhysicalW() Or ph>Neon_CapacityPhysicalH() Or off+(pw+ph)*12>capacity
      failed=1 : Break
    EndIf
    t0=Ticks()
    rc=NeonHardwareRebindSurface(base,w,h,pw*4,bytes,#V3D_OFMT_RGBA8,rot)
    row=$E1C03520+i*64
    PokeI(row,w) : PokeI(row+8,h) : PokeI(row+16,rot)
    PokeI(row+24,pw) : PokeI(row+32,ph) : PokeI(row+40,off)
    PokeI(row+48,(pw+ph)*12) : PokeI(row+56,rc)
    PokeI($E1C03840+i*8,Ticks()-t0)
    If rc<>0 : failed=2 : Break : EndIf
    For n=0 To pw*3-1
      PokeL(scratch+off,PeekN(neon_xcTab+n*4)) : off=off+4
    Next
    For n=0 To ph*3-1
      PokeL(scratch+off,PeekN(neon_ycTab+n*4)) : off=off+4
    Next
  Next
  restored=NeonHardwareRebindSurface(oldBase,oldW,oldH,oldPitch,oldBytes,oldFormat,oldRot)
  PokeI($E1C03490,off) : PokeI($E1C03498,failed)
  PokeI($E1C034A0,restored) : PokeI($E1C034A8,12)
  If restored<>0 : ProcedureReturn 3 : EndIf
  ProcedureReturn failed
EndProcedure
