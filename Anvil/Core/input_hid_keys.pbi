; SPDX-License-Identifier: MIT
; Protocol facts only: USB-IF HUT1.5, section10, printed pp90..91.
; https://usb.org/sites/default/files/hut1_5.pdf
; Numeric usages mapped to the shared vocabulary; no upstream code copied.
XIncludeFile "Anvil/Hal/input_codes.pbi"
Procedure.i InputHidNamedKey(usage.i,numLock.i)
  If usage<0 Or usage>255 Or numLock<0 Or numLock>1 : ProcedureReturn -1 : EndIf
  Select usage
    Case $28 : ProcedureReturn #AIK_ENTER
    Case $29 : ProcedureReturn #AIK_ESC
    Case $2A : ProcedureReturn #AIK_BACKSPACE
    Case $2B : ProcedureReturn #AIK_TAB
    Case $49 : ProcedureReturn #AIK_INSERT
    Case $4A : ProcedureReturn #AIK_HOME
    Case $4B : ProcedureReturn #AIK_PAGE_UP
    Case $4C : ProcedureReturn #AIK_DELETE
    Case $4D : ProcedureReturn #AIK_END
    Case $4E : ProcedureReturn #AIK_PAGE_DOWN
    Case $4F : ProcedureReturn #AIK_RIGHT
    Case $50 : ProcedureReturn #AIK_LEFT
    Case $51 : ProcedureReturn #AIK_DOWN
    Case $52 : ProcedureReturn #AIK_UP
    Case $58 : ProcedureReturn #AIK_ENTER
  EndSelect
  If numLock=0
    Select usage
      Case $59 : ProcedureReturn #AIK_END
      Case $5A : ProcedureReturn #AIK_DOWN
      Case $5B : ProcedureReturn #AIK_PAGE_DOWN
      Case $5C : ProcedureReturn #AIK_LEFT
      Case $5E : ProcedureReturn #AIK_RIGHT
      Case $5F : ProcedureReturn #AIK_HOME
      Case $60 : ProcedureReturn #AIK_UP
      Case $61 : ProcedureReturn #AIK_PAGE_UP
      Case $62 : ProcedureReturn #AIK_INSERT
      Case $63 : ProcedureReturn #AIK_DELETE
    EndSelect
  EndIf
  ProcedureReturn 0
EndProcedure
