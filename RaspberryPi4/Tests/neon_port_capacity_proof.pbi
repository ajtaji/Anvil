; Controlled backend for the actual float port entry points. No GPU or display.
Global npcBeginResult.i = 77
Global npcBegin.i, npcPoints.i, npcEnd.i, npcLastX.i, npcLastY.i, npcCalls.i
Global Dim npcXY.l[8196]
Procedure.i NpcFanBegin()
 npcBegin=npcBegin+1 : ProcedureReturn npcBeginResult
EndProcedure
Procedure NpcFanPoint(x.i,y.i)
 npcPoints=npcPoints+1 : npcLastX=x : npcLastY=y
EndProcedure
Procedure.i NpcFanEnd(colour.i)
 npcEnd=npcEnd+1 : ProcedureReturn 0
EndProcedure
Procedure.i NpcLinesBegin()
 npcBegin=npcBegin+1 : ProcedureReturn npcBeginResult
EndProcedure
Procedure NpcLine(x0.i,y0.i,x1.i,y1.i)
 npcPoints=npcPoints+2 : npcCalls=npcCalls+1 : npcLastX=x1 : npcLastY=y1
EndProcedure
Procedure.i NpcLinesEnd(colour.i)
 npcEnd=npcEnd+1 : ProcedureReturn 0
EndProcedure
; NPC_ACTUAL_PORT
Procedure NpcReset(result.i)
 npcBeginResult=result : npcBegin=0 : npcPoints=0 : npcEnd=0 : npcLastX=0 : npcLastY=0 : npcCalls=0
EndProcedure
Procedure NpcRecord(row.i,rc.i)
 Define p.i = #NPC_REPORT+256+row*64
 PokeI(p,rc) : PokeI(p+8,npcBegin) : PokeI(p+16,npcPoints) : PokeI(p+24,npcEnd)
 PokeI(p+32,npcLastX) : PokeI(p+40,npcLastY) : PokeI(p+48,npcCalls) : PokeI(p+56,$55AA)
EndProcedure
Procedure.i Main(services.i)
 Define i.i,rc.i
 For i=0 To 4095 : PokeA(#NPC_REPORT+i,0) : Next
 PokeI(#NPC_REPORT,$4E504343)
 rc=NeonVkPortCanvas(64,64,64,64)
 For i=0 To 4097 : npcXY[i*2]=MathBitsOf(4.0) : npcXY[i*2+1]=MathBitsOf(4.0) : Next
 npcXY[8194]=MathBitsOf(28.0) : npcXY[8195]=MathBitsOf(8.0)
; NPC_CASES
 PokeI(#NPC_REPORT+8,19)
 ProcedureReturn 0
EndProcedure
