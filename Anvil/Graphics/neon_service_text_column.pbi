; SPDX-License-Identifier: MIT
XIncludeFile "Anvil/Graphics/neon_text_column.pbi"
Procedure.i NeonServiceTextColumnInstall()
 If NeonServiceReady()=0 : ProcedureReturn #NEON_COLUMN_ERR_UNBOUND : EndIf
 ProcedureReturn NeonTextColumnBind(@NeonServiceTextWidth)
EndProcedure
