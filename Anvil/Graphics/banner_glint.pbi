; Shared Anvil logo glint: the existing Pi4 eight-step,350ms sequence.
#BANNER_ANIM_MS = 350
#BANNER_ANIM_PHASES = 8
#BANNER_ANIM_PATCH = 5

Procedure.i BannerGlintX(phase.i)
  ProcedureReturn 13 + phase * 7
EndProcedure

Procedure.i BannerGlintY(phase.i)
  If phase < 3
    ProcedureReturn 17 - phase * 3
  EndIf
  If phase < 6
    ProcedureReturn 9 + (phase - 3)
  EndIf
  ProcedureReturn 13 + (phase - 6) * 2
EndProcedure

