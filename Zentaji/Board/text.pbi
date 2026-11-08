; Native text output. Serial remains the diagnostic transport. The board admits
; a protected RAM extent before Start; no fixed kernel address is a public ABI.
#ZEN_TEXT = $FFFF0000001A0000
#ZEN_DISPLAY = $FFFF0000000C0000
Global zenTextCells.i,zenTextCapacity.i,zenTextUp.i
Global zenTextCode.i,zenTextNeed.i,zenTextMinimum.i,zenTextApplication.i

Procedure.i ZentajiTextRequired(table.i)
 Protected total.i,entries.i,offset.i,count.i,fonts.i,n.i,f.i,p.i,w.i,h.i,fw.i,fh.i,bytes.i,largest.i
 If table<>$FFFF000000010000 Or PeekQ(table)<>$00494A41544E455A : ProcedureReturn 0 : EndIf
 If (PeekW(table+8)&$FFFF)<>1 Or (PeekW(table+10)&$FFFF)<>64 Or PeekL(table+20)<>64 : ProcedureReturn 0 : EndIf
 total=PeekL(table+12)&$FFFFFFFF : entries=PeekL(table+16)&$FFFFFFFF
 If total<64 Or total>65536 Or entries<1 Or entries>(total-64)/64 : ProcedureReturn 0 : EndIf
 If (PeekQ(#ZEN_TEXT)&$FFFF)<>22 Or (PeekQ(#ZEN_DISPLAY)&$FFFF)<>13 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_TEXT+$50)<1 Or PeekQ(#ZEN_TEXT+$58)<1 : ProcedureReturn 0 : EndIf
 For n=0 To entries-1
  p=table+64+n*64
  If (PeekW(p)&$FFFF)=13 And PeekA(p+2)=0 And (PeekA(p+5)&1)<>0 And PeekQ(p+8)=#ZEN_DISPLAY
   count=PeekQ(p+24)
  EndIf
 Next
 offset=PeekQ(table+48) : fonts=PeekQ(#ZEN_TEXT+$D8)
 If count<1 Or count>64 Or offset<64+entries*64 Or offset>total-count*16 : ProcedureReturn 0 : EndIf
 ; The font list consists of 8-byte registers within this 64KB aperture.
 If fonts<1 Or fonts>(65536-4096)/8 : ProcedureReturn 0 : EndIf
 For f=0 To fonts-1
  p=PeekQ(#ZEN_TEXT+$1000+f*8) : fw=p&$FFFF : fh=(p>>16)&$FFFF
  If fw<1 Or fh<1 : ProcedureReturn 0 : EndIf
  For n=0 To count-1
   p=table+offset+n*16 : w=PeekW(p)&$FFFF : h=PeekW(p+2)&$FFFF
   If w<1 Or h<1 : ProcedureReturn 0 : EndIf
   bytes=(w/fw)*(h/fh)*4
   If bytes>largest : largest=bytes : EndIf
  Next
 Next
 ProcedureReturn largest
EndProcedure

Procedure.i ZentajiTextGridFits()
 Protected cols.i=PeekQ(#ZEN_TEXT+$50),rows.i=PeekQ(#ZEN_TEXT+$58)
 If cols<1 Or rows<1 Or cols>65535 Or rows>65535 : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool(cols*rows*4<=zenTextCapacity)
EndProcedure

Procedure.i ZentajiTextOwned()
 If zenTextCells=0 : ProcedureReturn 1 : EndIf
 If zenTextUp=0 Or ZentajiTextGridFits()=0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_TEXT+$40)<>1 Or PeekQ(#ZEN_TEXT+$48)<>zenTextCells Or PeekQ(#ZEN_TEXT+$90)<>0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_TEXT+$A8)<>0 Or PeekQ(#ZEN_TEXT+$B0)<>PeekQ(#ZEN_TEXT+$58) : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_TEXT+$B8)<>$00070020 Or PeekQ(#ZEN_TEXT+$C8)<>$00070000 : ProcedureReturn 0 : EndIf
 If (PeekQ(#ZEN_TEXT+8)&$FF00)<>0 Or PeekQ(#ZEN_TEXT+$20)<>0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_DISPLAY+$10)<>1 Or PeekQ(#ZEN_DISPLAY+$20)<>0 : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiTextResume()
 Protected offset.i
 If zenTextCells=0 : ProcedureReturn 1 : EndIf
 ; Never overwrite a returned application's live text/display owner.
 If zenTextUp<>0 Or PeekQ(#ZEN_TEXT+$40)<>0 Or PeekQ(#ZEN_DISPLAY+$10)<>0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_TEXT+$20)<>0 Or PeekQ(#ZEN_DISPLAY+$20)<>0 Or ZentajiTextGridFits()=0 : ProcedureReturn 0 : EndIf
 PokeQ(#ZEN_TEXT+$48,zenTextCells) : PokeQ(#ZEN_TEXT+$90,0)
 PokeQ(#ZEN_TEXT+$98,0) : PokeQ(#ZEN_TEXT+$A8,0) : PokeQ(#ZEN_TEXT+$B0,0)
 PokeQ(#ZEN_TEXT+$B8,$00070020) : PokeQ(#ZEN_TEXT+$C8,$00070000)
 ; A later mode/font can expose the rest of this extent. Initialise it too,
 ; so growth never renders stale application bytes or uninitialised glyphs.
 For offset=0 To zenTextCapacity-4 Step 4 : PokeL(zenTextCells+offset,$00070020) : Next
 PokeQ(#ZEN_TEXT+$88,$101) : PokeQ(#ZEN_TEXT+$D0,1)
 PokeQ(#ZEN_TEXT+$40,1) : PokeQ(#ZEN_DISPLAY+$10,1)
 zenTextCode=0 : zenTextNeed=0 : zenTextMinimum=0 : zenTextUp=1
 ProcedureReturn ZentajiTextOwned()
EndProcedure

Procedure.i ZentajiTextStart(cells.i,capacity.i)
 Protected ram.i=PeekQ($FFFF000000010018)
 If zenTextCells<>0 Or cells<1 Or (cells&3)<>0 Or capacity<4 Or (capacity&3)<>0 Or cells>ram Or capacity>ram-cells : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_TEXT+$40)<>0 Or PeekQ(#ZEN_DISPLAY+$10)<>0 : ProcedureReturn 0 : EndIf
 If (PeekQ(#ZEN_TEXT+8)&$FF00)<>0 : ProcedureReturn 0 : EndIf
 zenTextCells=cells : zenTextCapacity=capacity
 If ZentajiTextResume()=0
  zenTextCells=0 : zenTextCapacity=0
  ProcedureReturn 0
 EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiTextRelease()
 If zenTextCells=0 : ProcedureReturn 1 : EndIf
 If ZentajiTextOwned()=0 : ProcedureReturn 0 : EndIf
 PokeQ(#ZEN_TEXT+$40,0) : PokeQ(#ZEN_DISPLAY+$10,0)
 zenTextUp=0 : zenTextNeed=0
 ProcedureReturn 1
EndProcedure

Procedure ZentajiTextByte(byte.i)
 Protected code.i
 If zenTextUp=0 Or zenTextApplication<>0 : ProcedureReturn : EndIf
 byte=byte&$FF
 If zenTextNeed<>0
  If byte>=$80 And byte<=$BF
   zenTextCode=(zenTextCode<<6)|(byte&$3F) : zenTextNeed=zenTextNeed-1
   If zenTextNeed=0
    code=zenTextCode
    If code<zenTextMinimum Or code>$FFFF Or (code>=$D800 And code<=$DFFF) : code=$FFFD : EndIf
    PokeQ(#ZEN_TEXT+$C0,code)
   EndIf
   ProcedureReturn
  EndIf
  PokeQ(#ZEN_TEXT+$C0,$FFFD) : zenTextNeed=0
  ; Reprocess a noncontinuation byte so malformed UTF-8 cannot eat CR/LF.
 EndIf
 If byte<$80
  PokeQ(#ZEN_TEXT+$C0,byte)
 ElseIf byte>=$C2 And byte<=$DF
  zenTextCode=byte&$1F : zenTextNeed=1 : zenTextMinimum=$80
 ElseIf byte>=$E0 And byte<=$EF
  zenTextCode=byte&$0F : zenTextNeed=2 : zenTextMinimum=$800
 ElseIf byte>=$F0 And byte<=$F4
  zenTextCode=byte&7 : zenTextNeed=3 : zenTextMinimum=$10000
 Else
  PokeQ(#ZEN_TEXT+$C0,$FFFD)
 EndIf
EndProcedure
