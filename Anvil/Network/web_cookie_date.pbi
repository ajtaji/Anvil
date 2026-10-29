; RFC 6265 section 5.1.1 cookie-date tokenization and Gregorian conversion.
; Explicit byte spans; no clock, locale or transport dependency.
#WEB_COOKIE_DATE_INVALID=-999999999999
Procedure.i wcdDelimiter(c.i)
 ProcedureReturn Bool(c=9 Or (c>=32 And c<=47) Or (c>=59 And c<=64) Or (c>=91 And c<=96) Or (c>=123 And c<=126))
EndProcedure
Procedure.i wcdDigits(p.i,n.i)
 Define i.i,c.i,v.i
 If n<1 Or n>4 : ProcedureReturn -1 : EndIf
 For i=0 To n-1
  c=PeekA(p+i) & 255
  If c<48 Or c>57 : ProcedureReturn -1 : EndIf
  v=v*10+c-48
 Next
 ProcedureReturn v
EndProcedure
Procedure.i wcdLeap(y.i)
 ProcedureReturn Bool(y % 4=0 And (y % 100<>0 Or y % 400=0))
EndProcedure
Procedure.i wcdMonthDays(y.i,m.i)
 If m=2 : ProcedureReturn 28+wcdLeap(y) : EndIf
 If m=4 Or m=6 Or m=9 Or m=11 : ProcedureReturn 30 : EndIf
 ProcedureReturn 31
EndProcedure
Procedure.i WebCookieDate(p.i,n.i)
 Define i.i,start.i,k.i,c.i,d.i,m.i,y.i,h.i,minute.i,sec.i,timeFound.i,v.i,j.i,a.i,b.i,months.i,match.i,days.i
 If p=0 Or n<1 Or n>256 : ProcedureReturn #WEB_COOKIE_DATE_INVALID : EndIf
 d=-1 : y=-1 : months="janfebmaraprmayjunjulaugsepoctnovdec"
 While i<n
  If wcdDelimiter(PeekA(p+i) & 255) : i=i+1 : Continue : EndIf
  start=i
  While i<n
   If wcdDelimiter(PeekA(p+i) & 255) : Break : EndIf
   i=i+1
  Wend
  k=i-start : a=-1 : b=-1
  If timeFound=0
   For j=0 To k-1
    If PeekA(p+start+j)=58
     If a<0 : a=j : ElseIf b<0 : b=j : Else : b=-2 : Break : EndIf
    EndIf
   Next
   If a>=1 And a<=2 And b>a And b-a<=3 And k-b>=2 And k-b<=3
    h=wcdDigits(p+start,a) : minute=wcdDigits(p+start+a+1,b-a-1) : sec=wcdDigits(p+start+b+1,k-b-1)
    If h>=0 And minute>=0 And sec>=0 : timeFound=1 : Continue : EndIf
   EndIf
  EndIf
  v=wcdDigits(p+start,k)
  If d<0 And k<=2 And v>=0 : d=v : Continue : EndIf
  If m=0 And k>=3
   For j=0 To 11
    match=1
    For a=0 To 2
     c=PeekA(p+start+a) & 255 : If c>=65 And c<=90 : c=c+32 : EndIf
     If c<>PeekA(months+j*3+a) : match=0 : EndIf
    Next
    If match : m=j+1 : Break : EndIf
   Next
   If m>0 : Continue : EndIf
  EndIf
  If y<0 And k>=2 And v>=0 : y=v : EndIf
 Wend
 If y>=70 And y<=99 : y=y+1900 : ElseIf y>=0 And y<=69 : y=y+2000 : EndIf
 If timeFound=0 Or y<1601 Or y>9999 Or m<1 Or m>12 Or d<1 Or h>23 Or minute>59 Or sec>59 : ProcedureReturn #WEB_COOKIE_DATE_INVALID : EndIf
 If d>wcdMonthDays(y,m) : ProcedureReturn #WEB_COOKIE_DATE_INVALID : EndIf
 If y>=1970
  For j=1970 To y-1 : days=days+365+wcdLeap(j) : Next
 Else
  For j=y To 1969 : days=days-365-wcdLeap(j) : Next
 EndIf
 For j=1 To m-1 : days=days+wcdMonthDays(y,j) : Next
 ProcedureReturn (days+d-1)*86400+h*3600+minute*60+sec
EndProcedure
