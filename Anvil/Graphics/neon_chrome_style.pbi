; SPDX-License-Identifier: MIT
; Shared chrome palette and motion preference. No renderer or device ownership.
; Derived semantics/defaults: Neon GlUIChrome.pbi PALETTE and Neon_Animate.
XIncludeFile "Anvil/Math/float32.pbi"
#NSTY_ERR_ARGS=-22400
#NSTY_ERR_BUSY=-22401
Structure NeonChromeColour Align #PB_Structure_AlignC
  r.f : g.f : b.f
EndStructure
Structure NeonChromePalette Align #PB_Structure_AlignC
  bg.NeonChromeColour
  panel.NeonChromeColour
  head.NeonChromeColour
  line.NeonChromeColour
  text.NeonChromeColour
  dim.NeonChromeColour
  faint.NeonChromeColour
  accent.NeonChromeColour
  amber.NeonChromeColour
  green.NeonChromeColour
  red.NeonChromeColour
  violet.NeonChromeColour
  list.NeonChromeColour
  field.NeonChromeColour
  thumb.NeonChromeColour
EndStructure
Global nstyPalette.NeonChromePalette,nstyReady.i,nstyBusy.i,nstyRevision.i,nstyAnimations.i=1
Procedure.i nstyAddress(p.i)
  ProcedureReturn Bool(p<>0 And (p & 3)=0 And p+SizeOf(NeonChromePalette)>p)
EndProcedure
Procedure.i nstyDefaults(*p.NeonChromePalette)
  *p\bg\r=0.129 : *p\bg\g=0.133 : *p\bg\b=0.145
  *p\panel\r=0.145 : *p\panel\g=0.149 : *p\panel\b=0.161
  *p\head\r=0.169 : *p\head\g=0.173 : *p\head\b=0.184
  *p\line\r=0.196 : *p\line\g=0.2 : *p\line\b=0.212
  *p\text\r=0.863 : *p\text\g=0.863 : *p\text\b=0.863
  *p\dim\r=0.576 : *p\dim\g=0.596 : *p\dim\b=0.635
  *p\faint\r=0.435 : *p\faint\g=0.459 : *p\faint\b=0.498
  *p\accent\r=0.353 : *p\accent\g=0.741 : *p\accent\b=0.816
  *p\amber\r=0.882 : *p\amber\g=0.647 : *p\amber\b=0.259
  *p\green\r=0.361 : *p\green\g=0.749 : *p\green\b=0.596
  *p\red\r=0.867 : *p\red\g=0.494 : *p\red\b=0.494
  *p\violet\r=0.663 : *p\violet\g=0.596 : *p\violet\b=0.878
  *p\list\r=0.118 : *p\list\g=0.122 : *p\list\b=0.133
  *p\field\r=0.09 : *p\field\g=0.093 : *p\field\b=0.102
  *p\thumb\r=0.31 : *p\thumb\g=0.33 : *p\thumb\b=0.36
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeStyleDefaults(*p.NeonChromePalette)
  If nstyBusy<>0 : ProcedureReturn #NSTY_ERR_BUSY : EndIf
  If nstyAddress(*p)=0 : ProcedureReturn #NSTY_ERR_ARGS : EndIf
  If *p<@nstyPalette+SizeOf(NeonChromePalette) And *p+SizeOf(NeonChromePalette)>@nstyPalette : ProcedureReturn #NSTY_ERR_ARGS : EndIf
  ProcedureReturn nstyDefaults(*p)
EndProcedure
Procedure nstyEnsure()
  If nstyReady=0
    nstyDefaults(@nstyPalette) : nstyRevision=1 : nstyReady=1
  EndIf
EndProcedure
Procedure nstyChanged()
  nstyRevision=nstyRevision+1
  If nstyRevision>2147483646 : nstyRevision=1 : EndIf
EndProcedure
Procedure.i NeonChromeStylePaletteGet(*p.NeonChromePalette)
  Protected i.i
  If nstyBusy<>0 : ProcedureReturn #NSTY_ERR_BUSY : EndIf
  If nstyAddress(*p)=0 : ProcedureReturn #NSTY_ERR_ARGS : EndIf
  nstyEnsure()
  ; A caller cannot partially alias the internal published palette.
  If *p<@nstyPalette+SizeOf(NeonChromePalette) And *p+SizeOf(NeonChromePalette)>@nstyPalette : ProcedureReturn #NSTY_ERR_ARGS : EndIf
  For i=0 To SizeOf(NeonChromePalette)-1 : PokeA(*p+i,PeekA(@nstyPalette+i)) : Next
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeStylePaletteSet(*p.NeonChromePalette)
  Protected i.i,bits.i,v.f,changed.i
  If nstyBusy<>0 : ProcedureReturn #NSTY_ERR_BUSY : EndIf
  If nstyAddress(*p)=0 : ProcedureReturn #NSTY_ERR_ARGS : EndIf
  nstyEnsure()
  If *p<@nstyPalette+SizeOf(NeonChromePalette) And *p+SizeOf(NeonChromePalette)>@nstyPalette : ProcedureReturn #NSTY_ERR_ARGS : EndIf
  ; Validate every colour before publishing any field; alpha remains widget-owned.
  For i=0 To SizeOf(NeonChromePalette)-4 Step 4
    bits=PeekL(*p+i) : v=MathFromBits(bits)
    If (bits & $7FFFFFFF)>$3F800000 Or v<0.0 : ProcedureReturn #NSTY_ERR_ARGS : EndIf
    If PeekL(@nstyPalette+i)<>bits : changed=1 : EndIf
  Next
  If changed<>0
    For i=0 To SizeOf(NeonChromePalette)-1 : PokeA(@nstyPalette+i,PeekA(*p+i)) : Next
    nstyChanged()
  EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeStyleAnimationsSet(enabled.i)
  If nstyBusy<>0 : ProcedureReturn #NSTY_ERR_BUSY : EndIf
  If enabled<>0 And enabled<>1 : ProcedureReturn #NSTY_ERR_ARGS : EndIf
  nstyEnsure()
  If nstyAnimations<>enabled : nstyAnimations=enabled : nstyChanged() : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NeonChromeStyleAnimationsGet()
  nstyEnsure() : ProcedureReturn nstyAnimations
EndProcedure
Procedure.i NeonChromeStyleRevision()
  nstyEnsure() : ProcedureReturn nstyRevision
EndProcedure
; Internal synchronous callback guard; nested list->scroll drawing is permitted.
Procedure nstyEnter()
  nstyEnsure() : nstyBusy=nstyBusy+1
EndProcedure
Procedure nstyLeave()
  nstyBusy=nstyBusy-1
EndProcedure
