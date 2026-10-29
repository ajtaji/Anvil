; SPDX-License-Identifier: MIT
; Legacy integer Chrome key domain, shared by native rendering compositions.
XIncludeFile "Anvil/Hal/input_codes.pbi"
#NEON_KEY_BACK   = 8
#NEON_KEY_TAB    = 9
#NEON_KEY_RETURN = 13
#NEON_KEY_ESCAPE = 27
#NEON_KEY_DELETE = 127
#NEON_KEY_LEFT   = 256
#NEON_KEY_RIGHT  = 257
#NEON_KEY_UP     = 258
#NEON_KEY_DOWN   = 259
#NEON_KEY_HOME   = 260
#NEON_KEY_END    = 261
; Translate a normalized AIK named key, not an NCE editor command or HID
; usage. Call for accepted AIE_KEY_DOWN events only. Typed text stays in its
; independent scalar channel; unsupported named keys return zero.
Procedure.i NeonLegacyKeyFromNative(key.i)
  Select key
    Case #AIK_ENTER : ProcedureReturn #NEON_KEY_RETURN
    Case #AIK_BACKSPACE : ProcedureReturn #NEON_KEY_BACK
    Case #AIK_DELETE : ProcedureReturn #NEON_KEY_DELETE
    Case #AIK_LEFT : ProcedureReturn #NEON_KEY_LEFT
    Case #AIK_RIGHT : ProcedureReturn #NEON_KEY_RIGHT
    Case #AIK_HOME : ProcedureReturn #NEON_KEY_HOME
    Case #AIK_END : ProcedureReturn #NEON_KEY_END
    Case #AIK_TAB : ProcedureReturn #NEON_KEY_TAB
    Case #AIK_ESC : ProcedureReturn #NEON_KEY_ESCAPE
    Case #AIK_UP : ProcedureReturn #NEON_KEY_UP
    Case #AIK_DOWN : ProcedureReturn #NEON_KEY_DOWN
  EndSelect
  ProcedureReturn 0
EndProcedure
