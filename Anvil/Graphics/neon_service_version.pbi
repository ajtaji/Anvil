; SPDX-License-Identifier: MIT
; Format a complete refusal in caller-owned UTF8 storage. No service is called,
; including when an unfamiliar major changes the meaning of every table slot.
Procedure.i nsvAppend(dst.i,at.i,text.i)
  Protected i.i
  While PeekA(text+i)<>0
    PokeA(dst+at,PeekA(text+i)) : at=at+1 : i=i+1
  Wend
  ProcedureReturn at
EndProcedure

Procedure.i NeonServiceBindingMessage(services.i,status.i,dst.i,capacity.i)
  Protected at.i
  If dst=0 Or capacity<192 : ProcedureReturn -1 : EndIf
  If services=0 Or (services & 7)<>0 : ProcedureReturn NeonServiceVersionMessage(services,dst,capacity) : EndIf
  If (PeekL(services)&$FFFFFFFF)<>$53564E41 Or PeekL(services+4)<>1 Or PeekL(services+8)<8
    ProcedureReturn NeonServiceVersionMessage(services,dst,capacity)
  EndIf
  at=nsvAppend(dst,0,"This Anvil could not bind the required resident Vulkan graphics service. The returned status is recorded in the result block.")
  PokeA(dst+at,0)
  ProcedureReturn at
EndProcedure
Procedure.i nsvNumber(dst.i,at.i,value.i)
  Protected place.i=1000000000
  While place>1 And value<place : place=place/10 : Wend
  While place>0
    PokeA(dst+at,48+value/place) : at=at+1
    value=value%place : place=place/10
  Wend
  ProcedureReturn at
EndProcedure
Procedure.i NeonServiceVersionMessage(services.i,dst.i,capacity.i)
  Protected at.i
  If dst=0 Or capacity<192 : ProcedureReturn -1 : EndIf
  at=nsvAppend(dst,0,"This application needs Anvil service ABI 1.8; this monitor provides ")
  If services=0 Or (services & 7)<>0
    at=nsvAppend(dst,at,"no readable service table")
  ElseIf (PeekL(services)&$FFFFFFFF)<>$53564E41
    at=nsvAppend(dst,at,"an unrecognized service table")
  Else
    at=nsvNumber(dst,at,PeekL(services+4)&$FFFFFFFF)
    at=nsvAppend(dst,at,".")
    at=nsvNumber(dst,at,PeekL(services+8)&$FFFFFFFF)
  EndIf
  at=nsvAppend(dst,at,". Update Anvil before running it.")
  PokeA(dst+at,0)
  ProcedureReturn at
EndProcedure
