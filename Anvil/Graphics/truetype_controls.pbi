; SPDX-License-Identifier: MIT
; Pure control policy and a visible fallback independent of the loaded face.
; Legacy mode preserves CR/LF layout. Hide/show match Neon's C0/DEL policy;
; C1 and ordinary missing Unicode glyphs still belong to the face cmap.
XIncludeFile "Anvil/Graphics/neon_byte_ranges.pbi"
#ANVIL_TTC_CONTROLS_LEGACY=0
#ANVIL_TTC_CONTROLS_HIDE=1
#ANVIL_TTC_CONTROLS_SHOW=2
#ANVIL_TTC_CONTROL_GLYPH=-1
Procedure.i AnvilTrueTypeIsControl(codepoint.i)
  ProcedureReturn Bool(codepoint>=0 And (codepoint<32 Or codepoint=127))
EndProcedure
Procedure.i AnvilTrueTypeControlWidth(pixels.i)
  Protected width.i
  If pixels<1 Or pixels>512 : ProcedureReturn 0 : EndIf
  width=(pixels*3)/5
  If width<3 : width=3 : EndIf
  ProcedureReturn width
EndProcedure
Procedure.i AnvilTrueTypeControlHeight(pixels.i)
  If pixels<1 Or pixels>512 : ProcedureReturn 0 : EndIf
  If pixels<3 : ProcedureReturn 3 : EndIf
  ProcedureReturn pixels
EndProcedure
Procedure.i AnvilTrueTypeControlAdvance(pixels.i)
  Protected width.i=AnvilTrueTypeControlWidth(pixels)
  If width=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn (width+1)*65536
EndProcedure
; Returns written bytes, or0 without changing output. No padding/tail writes;
; 1pixel opaque border around transparent interior, no font/parser dependency.
Procedure.i AnvilTrueTypeControlRaster(pixels.i,alpha.i,capacity.i)
  Protected width.i=AnvilTrueTypeControlWidth(pixels)
  Protected height.i=AnvilTrueTypeControlHeight(pixels),x.i,y.i,needed.i
  If width=0 Or height=0 Or capacity<0 : ProcedureReturn 0 : EndIf
  needed=width*height
  If capacity<needed Or NeonByteSpan(alpha,needed)=0 : ProcedureReturn 0 : EndIf
  For y=0 To height-1
    For x=0 To width-1
      If x=0 Or x=width-1 Or y=0 Or y=height-1
        PokeA(alpha+y*width+x,255)
      Else
        PokeA(alpha+y*width+x,0)
      EndIf
    Next
  Next
  ProcedureReturn needed
EndProcedure
