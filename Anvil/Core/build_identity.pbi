; One compact identity label for graphical and text banners on every board.
; The caller supplies its own compiled build constants. No runtime file, host
; date or cached settings can change which image this label describes.
; The returned buffer is owned by the main-thread banner renderer, not by a
; caller. Maximum length is 49 ASCII bytes plus NUL on a 64-bit target.
Global Dim gAnvilBuildLabel.a[64]

Procedure.i AnvilBuildCopy(*out, *text)
  Define c.i
  Repeat
    c = PeekA(*text)
    If c = 0
      Break
    EndIf
    PokeA(*out, c)
    *out = *out + 1
    *text = *text + 1
  ForEver
  ProcedureReturn *out
EndProcedure

Procedure.i AnvilBuildDec(*out, value.i, width.i)
  Define divisor.i
  Define remaining.i
  Define digits.i
  divisor = 1
  remaining = value
  digits = 1
  While remaining >= 10
    remaining = remaining / 10
    divisor = divisor * 10
    digits = digits + 1
  Wend
  While digits < width
    PokeA(*out, 48)
    *out = *out + 1
    digits = digits + 1
  Wend
  While divisor > 0
    PokeA(*out, 48 + ((value / divisor) % 10))
    *out = *out + 1
    divisor = divisor / 10
  Wend
  ProcedureReturn *out
EndProcedure

Procedure.i AnvilBuildLabel(build.i, date.i, time.i)
  Define p.i
  p = @gAnvilBuildLabel
  If build < 0 Or date < 0 Or date > 99999999 Or time < 0 Or time > 235959 Or (time / 100) % 100 > 59 Or time % 100 > 59
    p = AnvilBuildCopy(p, "Build identity invalid")
  Else
    p = AnvilBuildCopy(p, "Build ")
    p = AnvilBuildDec(p, build, 1)
    p = AnvilBuildCopy(p, "  |  ")
    p = AnvilBuildDec(p, date / 10000, 4)
    p = AnvilBuildCopy(p, "-")
    p = AnvilBuildDec(p, (date / 100) % 100, 2)
    p = AnvilBuildCopy(p, "-")
    p = AnvilBuildDec(p, date % 100, 2)
    p = AnvilBuildCopy(p, " ")
    p = AnvilBuildDec(p, time / 10000, 2)
    p = AnvilBuildCopy(p, ":")
    p = AnvilBuildDec(p, (time / 100) % 100, 2)
    p = AnvilBuildCopy(p, ":")
    p = AnvilBuildDec(p, time % 100, 2)
  EndIf
  PokeA(p, 0)
  ProcedureReturn @gAnvilBuildLabel
EndProcedure
