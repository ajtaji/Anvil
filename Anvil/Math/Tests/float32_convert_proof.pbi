; SPDX-License-Identifier: MIT
; Real CPU conversion comparisons; software reference remains unchanged.
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Math/float32_convert.pbi"
Global fcpCount.i,fcpFailures.i
Procedure FcpCase(bits.i)
  Protected value.f,expected.i,actual.i
  value=MathFromBits(bits) : expected=Int(value) : actual=MathFToI32(value)
  fcpCount=fcpCount+1
  If actual<>expected
    fcpFailures=fcpFailures+1
    If fcpFailures=1
      PokeI(#FCP_REPORT+32,bits) : PokeI(#FCP_REPORT+40,actual) : PokeI(#FCP_REPORT+48,expected)
    EndIf
  EndIf
EndProcedure
Procedure.i Main(services.i)
  Protected exponent.i,mantissa.i,sign.i,i.i,seed.i=123456789,bits.i
  For i=0 To 4095 Step 8 : PokeI(#FCP_REPORT+i,0) : Next
  For exponent=0 To 255
    For i=0 To 3
      mantissa=0
      If i=1 : mantissa=1 : EndIf
      If i=2 : mantissa=$400000 : EndIf
      If i=3 : mantissa=$7FFFFF : EndIf
      For sign=0 To 1 : FcpCase((sign<<31) | (exponent<<23) | mantissa) : Next
    Next
  Next
  For i=0 To 65535
    seed=(seed*1664525+1013904223) & $FFFFFFFF
    FcpCase(seed)
  Next
  ; A selected raw-bit table is checked independently by the host.
  For i=0 To 31
    bits=PeekN(?fcpCases+i*4)
    PokeI(#FCP_REPORT+128+i*16,bits)
    PokeI(#FCP_REPORT+136+i*16,MathFToI32(MathFromBits(bits)))
  Next
  PokeI(#FCP_REPORT,$46435031) : PokeI(#FCP_REPORT+8,1)
  PokeI(#FCP_REPORT+16,fcpFailures) : PokeI(#FCP_REPORT+24,fcpCount)
  ProcedureReturn fcpFailures
EndProcedure
DataSection
fcpCases:
  Data.l $00000000,$80000000,$00000001,$80000001,$007FFFFF,$807FFFFF,$00800000,$80800000
  Data.l $3F000000,$BF000000,$3F7FFFFF,$BF7FFFFF,$3F800000,$BF800000,$3FC00000,$BFC00000
  Data.l $4EFFFFFF,$CEFFFFFF,$4F000000,$CF000000,$4F000001,$CF000001,$7F7FFFFF,$FF7FFFFF
  Data.l $7F800000,$FF800000,$7FC00000,$FFC00000,$7F800001,$FF800001,$437F8000,$C37F8000
EndDataSection
