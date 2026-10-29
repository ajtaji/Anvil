; SPDX-License-Identifier: MIT
XIncludeFile "Anvil/Graphics/neon_canvas_retro.pbi"
Global v.NeonCanvasViewport
Global point.NeonCanvasPoint
Global row.i
Procedure Probe(cw.i,ch.i,tw.i,th.i,x.i,y.i)
  Protected fit.i,rc.i
  fit=NeonCanvasFit(@v,cw,ch,tw,th)
  point\xQ16=1234567 : point\yQ16=-7654321
  rc=NeonCanvasMapRetroPoint(@v,x,y,@point)
  PokeI($E1C00040+row*32,fit) : PokeI($E1C00048+row*32,rc)
  PokeI($E1C00050+row*32,point\xQ16) : PokeI($E1C00058+row*32,point\yQ16)
  row=row+1
EndProcedure
Procedure.i Main(services.i)
  Protected i.i
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  Probe(800,600,1280,800,640,400)
  Probe(800,600,1280,800,107,0)
  Probe(800,600,1280,800,200,150)
  Probe(800,600,1280,800,1050,650)
  Probe(800,600,1280,800,50,400)
  Probe(800,600,1280,800,1279,799)
  Probe(8192,8192,8192,8192,4096,4096)
  Probe(8192,8192,8192,8192,1000,6000)
  Probe(8192,8192,8192,8192,8191,8191)
  Probe(1,1,100,100,50,50)
  Probe(100,200,800,600,300,300)
  Probe(100,200,800,600,399,450)
  Probe(256,256,256,256,0,128)
  Probe(256,256,256,256,255,128)
  Probe(256,256,256,256,128,128)
  Probe(256,256,256,256,10,128)
  PokeI($E1C00000,$43525431) : PokeI($E1C00008,row)
  ProcedureReturn 0
EndProcedure
