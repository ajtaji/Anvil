EnableFloatingPoint
; SPDX-License-Identifier: MIT
XIncludeFile "Anvil/Graphics/neon_canvas_input.pbi"
Global s.NeonCanvasInput
Global v.NeonCanvasViewport
Global e.NativeInputEvent
Global row.i
Procedure Save(rc.i)
 Protected p.i
 p=$E1C00040+row*96
 PokeI(p,rc) : PokeI(p+8,s\pointer\down) : PokeI(p+16,s\pointer\pressed)
 PokeI(p+24,s\pointer\released) : PokeI(p+32,s\blockedMouse) : PokeI(p+40,s\pointer\cancelled)
 PokeI(p+48,MathBitsOf(s\pointer\x)) : PokeI(p+56,MathBitsOf(s\pointer\y))
 PokeI(p+64,s\input\wheel) : PokeI(p+72,s\pointer\lastTicks) : PokeI(p+80,s\retro)
 PokeI(p+88,s\pointer\contact) : row=row+1
EndProcedure
Procedure NcirEvent(kind.i,x.i,y.i,buttons.i,value.i,ticks.i)
 e\kind=kind : e\source=#NUI_SOURCE_MOUSE : e\code=0 : e\generation=1
 e\x=x : e\y=y : e\buttons=buttons : e\value=value : e\ticks=ticks
 Save(NeonCanvasInputFeed(@s,@e))
EndProcedure
Procedure.i Main(services.i)
 Protected i.i
 For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
 NeonCanvasFit(@v,800,600,1280,800)
 Save(NeonCanvasInputConfigureRetro(@s,@v))
 NcirEvent(#NUI_POINTER,640,400,1,0,10)
 Save(NeonCanvasInputConfigure(@s,@v))
 NcirEvent(#NUI_POINTER,107,0,1,1,11)
 NcirEvent(#NUI_POINTER,107,0,0,2,12)
 NcirEvent(#NUI_POINTER,107,0,1,0,13)
 NcirEvent(#NUI_POINTER,640,400,1,1,14)
 NcirEvent(#NUI_POINTER,640,400,0,2,15)
 NcirEvent(#NUI_POINTER,640,400,1,0,16)
 NcirEvent(#NUI_POINTER,200,150,1,1,15)
 NcirEvent(#NUI_POINTER,-1,-1,0,3,17)
 NcirEvent(#NUI_WHEEL,107,0,0,2,18)
 NcirEvent(#NUI_WHEEL,640,400,0,2,19)
 Save(NeonCanvasInputConfigure(@s,@v))
 NcirEvent(#NUI_POINTER,107,0,1,0,20)
 PokeI($E1C00000,$43495231) : PokeI($E1C00008,row)
 ProcedureReturn 0
EndProcedure
