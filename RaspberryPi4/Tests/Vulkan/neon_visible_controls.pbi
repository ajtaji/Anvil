; SPDX-License-Identifier: MIT
; Actual native control-policy/core-raster/Vulkan acceptance.
XIncludeFile "Anvil/Graphics/Vulkan/neon_vk_retained_ui.pbi"
#NFP_REPORT=$E1C00200
#NFP_PIXELS=$E2400000
#NFP_PIXEL_BYTES=368640
Global nfpChecks.i,nfpFailure.i,nfpRetained.i
Global nfpPlain.NeonVkPortFontRef,nfpHide.NeonVkPortFontRef,nfpShow.NeonVkPortFontRef,nfpStale.NeonVkPortFontRef
Global Dim nfpFonts.q[21]
Global Dim nfpArena.q[256]
Global Dim nfpGlyph.q[40]
Global Dim nfpX.q[40]
Global Dim nfpY.q[40]
Global Dim nfpAdv.q[40]
Global Dim nfpAlpha.a[157200]
Procedure NfpCheck(actual.i,expected.i)
 PokeI(#NFP_REPORT+512+nfpChecks*16,actual) : PokeI(#NFP_REPORT+520+nfpChecks*16,expected)
 nfpChecks=nfpChecks+1
 If actual<>expected And nfpFailure=0 : nfpFailure=nfpChecks : EndIf
 PokeI(#NFP_REPORT+16,nfpFailure) : PokeI(#NFP_REPORT+24,nfpChecks)
EndProcedure

Procedure NfpReference(x.f,y.f,gold.i)
 Protected r.f=1.0,g.f=1.0,b.f=1.0
 If gold<>0 : g=0.8 : b=0.2 : EndIf
 NfpCheck(NeonVkPortFontText(@nfpPlain,x,y,?nfpA,r,g,b,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(x+16.0,y,12.0,1.0,r,g,b,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(x+16.0,y+19.0,12.0,1.0,r,g,b,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(x+16.0,y+1.0,1.0,18.0,r,g,b,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(x+27.0,y+1.0,1.0,18.0,r,g,b,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpPlain,x+32.0,y,?nfpV,r,g,b,1.0,1,1),0)
EndProcedure
Procedure.i NfpFrame(imageBase.i,pitch.i,framebuffer.i)
 Protected i.i,j.i,row.i,part.i,src.i,dst.i,copied.i,poisoned.i,old.i,count.i,lc.i,mw.i,rc.i,bad.i
 Protected Dim clear.l[4]
 PokeI(#NFP_REPORT,$4E465031) : PokeI(#NFP_REPORT+8,3) : PokeI(#NFP_REPORT+32,6)
 NfpCheck(NeonVkPortCanvas(800,1280,800,1280),0)
 NfpCheck(SizeOf(NeonVkPortFontRef),56)
 NfpCheck(NeonVkPortFontBind(@nfpPlain,0,1,20),0)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpPlain,16.0),0)
 NfpCheck(NeonVkPortFontControlMode(@nfpPlain),0)
 NfpCheck(NeonVkPortFontBind(@nfpHide,0,1,20),0)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpHide,16.0),0)
 NfpCheck(NeonVkPortFontControlMode(@nfpHide),0)
 NfpCheck(NeonVkPortFontBind(@nfpShow,0,1,20),0)
 NfpCheck(NeonVkPortFontSetFixedAdvance(@nfpShow,16.0),0)
 NfpCheck(NeonVkPortFontControlMode(@nfpShow),0)
 NfpCheck(NeonVkPortFontSetShowControls(@nfpHide,0),0)
 NfpCheck(NeonVkPortFontControlMode(@nfpHide),1)
 NfpCheck(NeonVkPortFontSetShowControls(@nfpShow,1),0)
 NfpCheck(NeonVkPortFontControlMode(@nfpShow),2)
 NfpCheck(NeonVkPortFontSetShowControls(@nfpShow,2),-21312)
 NfpCheck(NeonVkPortFontSetControlMode(@nfpShow,3),-21312)
 NfpCheck(NeonVkPortFontSetControlMode(@nfpShow,-1),-21312)
 NfpCheck(NeonVkPortFontControlMode(@nfpShow),2)
 NfpCheck(NeonVkPortFontSetControlMode(@nfpShow,0),0)
 NfpCheck(NeonVkPortFontControlMode(@nfpShow),0)
 NfpCheck(NeonVkPortFontSetControlMode(@nfpShow,2),0)
 For i=0 To SizeOf(NeonVkPortFontRef)-1 : PokeA(@nfpStale+i,PeekA(@nfpShow+i)) : Next
 nfpStale\generation=nfpStale\generation+1
 NfpCheck(NeonVkPortFontSetShowControls(@nfpStale,0),-21310)
 NfpCheck(NeonVkPortFontControlMode(@nfpStale),-1)
 NfpCheck(AnvilTrueTypeIsControl(0),1)
 NfpCheck(AnvilTrueTypeIsControl(1),1)
 NfpCheck(AnvilTrueTypeIsControl(2),1)
 NfpCheck(AnvilTrueTypeIsControl(3),1)
 NfpCheck(AnvilTrueTypeIsControl(4),1)
 NfpCheck(AnvilTrueTypeIsControl(5),1)
 NfpCheck(AnvilTrueTypeIsControl(6),1)
 NfpCheck(AnvilTrueTypeIsControl(7),1)
 NfpCheck(AnvilTrueTypeIsControl(8),1)
 NfpCheck(AnvilTrueTypeIsControl(9),1)
 NfpCheck(AnvilTrueTypeIsControl(10),1)
 NfpCheck(AnvilTrueTypeIsControl(11),1)
 NfpCheck(AnvilTrueTypeIsControl(12),1)
 NfpCheck(AnvilTrueTypeIsControl(13),1)
 NfpCheck(AnvilTrueTypeIsControl(14),1)
 NfpCheck(AnvilTrueTypeIsControl(15),1)
 NfpCheck(AnvilTrueTypeIsControl(16),1)
 NfpCheck(AnvilTrueTypeIsControl(17),1)
 NfpCheck(AnvilTrueTypeIsControl(18),1)
 NfpCheck(AnvilTrueTypeIsControl(19),1)
 NfpCheck(AnvilTrueTypeIsControl(20),1)
 NfpCheck(AnvilTrueTypeIsControl(21),1)
 NfpCheck(AnvilTrueTypeIsControl(22),1)
 NfpCheck(AnvilTrueTypeIsControl(23),1)
 NfpCheck(AnvilTrueTypeIsControl(24),1)
 NfpCheck(AnvilTrueTypeIsControl(25),1)
 NfpCheck(AnvilTrueTypeIsControl(26),1)
 NfpCheck(AnvilTrueTypeIsControl(27),1)
 NfpCheck(AnvilTrueTypeIsControl(28),1)
 NfpCheck(AnvilTrueTypeIsControl(29),1)
 NfpCheck(AnvilTrueTypeIsControl(30),1)
 NfpCheck(AnvilTrueTypeIsControl(31),1)
 NfpCheck(AnvilTrueTypeIsControl(32),0)
 NfpCheck(AnvilTrueTypeIsControl(126),0)
 NfpCheck(AnvilTrueTypeIsControl(127),1)
 NfpCheck(AnvilTrueTypeIsControl(128),0)
 NfpCheck(AnvilTrueTypeIsControl(159),0)
 NfpCheck(AnvilTrueTypeIsControl(160),0)
 NfpCheck(AnvilTrueTypeIsControl(128578),0)
 NfpCheck(AnvilTrueTypeIsControl(-1),0)
 NfpCheck(AnvilTrueTypeDecodeUtf8Controls(?nfpMixed,11,@nfpGlyph[1],6,1),6)
 NfpCheck(nfpGlyph[1]-AnvilTrueTypeGlyphForCodepoint(65),0)
 NfpCheck(nfpGlyph[2]-AnvilTrueTypeGlyphForCodepoint(86),0)
 NfpCheck(nfpGlyph[3]-AnvilTrueTypeGlyphForCodepoint(65),0)
 NfpCheck(nfpGlyph[4]-AnvilTrueTypeGlyphForCodepoint(84),0)
 NfpCheck(nfpGlyph[5]-AnvilTrueTypeGlyphForCodepoint(65),0)
 NfpCheck(nfpGlyph[6]-AnvilTrueTypeGlyphForCodepoint(82),0)
 NfpCheck(AnvilTrueTypeDecodeUtf8Controls(?nfpControls,5,@nfpGlyph[1],0,1),0)
 NfpCheck(AnvilTrueTypeDecodeUtf8Controls(?nfpControls,5,@nfpGlyph[1],5,2),5)
 NfpCheck(nfpGlyph[1],-1)
 NfpCheck(nfpGlyph[2],-1)
 NfpCheck(nfpGlyph[3],-1)
 NfpCheck(nfpGlyph[4],-1)
 NfpCheck(nfpGlyph[5],-1)
 For i=0 To 39 : nfpGlyph[i]=12345 : Next
 NfpCheck(AnvilTrueTypeDecodeUtf8Controls(?nfpShowText,3,@nfpGlyph[1],2,2),-1)
 NfpCheck(AnvilTrueTypeDecodeUtf8Controls(?nfpBad,2,@nfpGlyph[1],30,1),-1)
 NfpCheck(AnvilTrueTypeDecodeUtf8Controls(?nfpBad,2,@nfpGlyph[1],30,2),-1)
 NfpCheck(AnvilTrueTypeDecodeUtf8Controls(?nfpMixed,11,@nfpGlyph[1],30,3),-1)
 NfpCheck(nfpGlyph[0],12345)
 NfpCheck(nfpGlyph[1],12345)
 NfpCheck(nfpGlyph[2],12345)
 NfpCheck(nfpGlyph[3],12345)
 NfpCheck(nfpGlyph[4],12345)
 NfpCheck(nfpGlyph[5],12345)
 NfpCheck(nfpGlyph[6],12345)
 NfpCheck(nfpGlyph[7],12345)
 NfpCheck(nfpGlyph[8],12345)
 NfpCheck(nfpGlyph[9],12345)
 NfpCheck(nfpGlyph[10],12345)
 NfpCheck(nfpGlyph[11],12345)
 NfpCheck(nfpGlyph[12],12345)
 NfpCheck(nfpGlyph[13],12345)
 NfpCheck(nfpGlyph[14],12345)
 NfpCheck(nfpGlyph[15],12345)
 NfpCheck(nfpGlyph[16],12345)
 NfpCheck(nfpGlyph[17],12345)
 NfpCheck(nfpGlyph[18],12345)
 NfpCheck(nfpGlyph[19],12345)
 NfpCheck(nfpGlyph[20],12345)
 NfpCheck(nfpGlyph[21],12345)
 NfpCheck(nfpGlyph[22],12345)
 NfpCheck(nfpGlyph[23],12345)
 NfpCheck(nfpGlyph[24],12345)
 NfpCheck(nfpGlyph[25],12345)
 NfpCheck(nfpGlyph[26],12345)
 NfpCheck(nfpGlyph[27],12345)
 NfpCheck(nfpGlyph[28],12345)
 NfpCheck(nfpGlyph[29],12345)
 NfpCheck(nfpGlyph[30],12345)
 NfpCheck(nfpGlyph[31],12345)
 NfpCheck(nfpGlyph[32],12345)
 NfpCheck(nfpGlyph[33],12345)
 NfpCheck(nfpGlyph[34],12345)
 NfpCheck(nfpGlyph[35],12345)
 NfpCheck(nfpGlyph[36],12345)
 NfpCheck(nfpGlyph[37],12345)
 NfpCheck(nfpGlyph[38],12345)
 NfpCheck(nfpGlyph[39],12345)
 NfpCheck(AnvilTrueTypeDecodeUtf8Controls(?nfpC1,2,@nfpGlyph[1],1,2),1)
 NfpCheck(nfpGlyph[1]-AnvilTrueTypeGlyphForCodepoint(128),0)
 NfpCheck(AnvilTrueTypeDecodeUtf8Controls(?nfpNul,1,@nfpGlyph[1],1,2),1)
 NfpCheck(nfpGlyph[1],-1)
 NfpCheck(AnvilTrueTypeLayoutUtf8Controls(?nfpShowText,3,20,0,22,@nfpGlyph[1],@nfpX[1],@nfpY[1],@nfpAdv[1],0,30,@count,@lc,@mw,1048576,2),1)
 NfpCheck(count,3)
 NfpCheck(lc,1)
 NfpCheck(mw,3145728)
 NfpCheck(nfpGlyph[2],-1)
 NfpCheck(nfpX[2],1048576)
 NfpCheck(nfpY[2],0)
 NfpCheck(AnvilTrueTypeLayoutUtf8Controls(?nfpControls,5,20,0,22,@nfpGlyph[1],@nfpX[1],@nfpY[1],@nfpAdv[1],0,30,@count,@lc,@mw,0,2),1)
 NfpCheck(count,5)
 NfpCheck(lc,1)
 NfpCheck(mw,4259840)
 NfpCheck(AnvilTrueTypeLayoutUtf8Controls(?nfpBreaks,4,20,0,22,@nfpGlyph[1],@nfpX[1],@nfpY[1],@nfpAdv[1],0,30,@count,@lc,@mw,1048576,0),1)
 NfpCheck(count,2)
 NfpCheck(lc,2)
 NfpCheck(mw,1048576)
 NfpCheck(nfpY[2],-1441792)
 NfpCheck(AnvilTrueTypeControlWidth(1),3)
 NfpCheck(AnvilTrueTypeControlHeight(1),3)
 NfpCheck(AnvilTrueTypeControlAdvance(1),262144)
 For i=0 To 157199 : nfpAlpha[i]=165 : Next
 NfpCheck(AnvilTrueTypeControlRaster(1,@nfpAlpha[16],9),9)
 bad=0
 For i=0 To 8
  If (i % 3)=0 Or (i % 3)=2 Or i<3 Or i>=6
   If (nfpAlpha[16+i] & 255)<>255 : bad=bad+1 : EndIf
  Else
   If (nfpAlpha[16+i] & 255)<>0 : bad=bad+1 : EndIf
  EndIf
 Next
 For i=0 To 15 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 For i=25 To 157199 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 NfpCheck(bad,0)
 NfpCheck(AnvilTrueTypeControlWidth(2),3)
 NfpCheck(AnvilTrueTypeControlHeight(2),3)
 NfpCheck(AnvilTrueTypeControlAdvance(2),262144)
 For i=0 To 157199 : nfpAlpha[i]=165 : Next
 NfpCheck(AnvilTrueTypeControlRaster(2,@nfpAlpha[16],9),9)
 bad=0
 For i=0 To 8
  If (i % 3)=0 Or (i % 3)=2 Or i<3 Or i>=6
   If (nfpAlpha[16+i] & 255)<>255 : bad=bad+1 : EndIf
  Else
   If (nfpAlpha[16+i] & 255)<>0 : bad=bad+1 : EndIf
  EndIf
 Next
 For i=0 To 15 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 For i=25 To 157199 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 NfpCheck(bad,0)
 NfpCheck(AnvilTrueTypeControlWidth(3),3)
 NfpCheck(AnvilTrueTypeControlHeight(3),3)
 NfpCheck(AnvilTrueTypeControlAdvance(3),262144)
 For i=0 To 157199 : nfpAlpha[i]=165 : Next
 NfpCheck(AnvilTrueTypeControlRaster(3,@nfpAlpha[16],9),9)
 bad=0
 For i=0 To 8
  If (i % 3)=0 Or (i % 3)=2 Or i<3 Or i>=6
   If (nfpAlpha[16+i] & 255)<>255 : bad=bad+1 : EndIf
  Else
   If (nfpAlpha[16+i] & 255)<>0 : bad=bad+1 : EndIf
  EndIf
 Next
 For i=0 To 15 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 For i=25 To 157199 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 NfpCheck(bad,0)
 NfpCheck(AnvilTrueTypeControlWidth(20),12)
 NfpCheck(AnvilTrueTypeControlHeight(20),20)
 NfpCheck(AnvilTrueTypeControlAdvance(20),851968)
 For i=0 To 157199 : nfpAlpha[i]=165 : Next
 NfpCheck(AnvilTrueTypeControlRaster(20,@nfpAlpha[16],240),240)
 bad=0
 For i=0 To 239
  If (i % 12)=0 Or (i % 12)=11 Or i<12 Or i>=228
   If (nfpAlpha[16+i] & 255)<>255 : bad=bad+1 : EndIf
  Else
   If (nfpAlpha[16+i] & 255)<>0 : bad=bad+1 : EndIf
  EndIf
 Next
 For i=0 To 15 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 For i=256 To 157199 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 NfpCheck(bad,0)
 NfpCheck(AnvilTrueTypeControlWidth(512),307)
 NfpCheck(AnvilTrueTypeControlHeight(512),512)
 NfpCheck(AnvilTrueTypeControlAdvance(512),20185088)
 For i=0 To 157199 : nfpAlpha[i]=165 : Next
 NfpCheck(AnvilTrueTypeControlRaster(512,@nfpAlpha[16],157184),157184)
 bad=0
 For i=0 To 157183
  If (i % 307)=0 Or (i % 307)=306 Or i<307 Or i>=156877
   If (nfpAlpha[16+i] & 255)<>255 : bad=bad+1 : EndIf
  Else
   If (nfpAlpha[16+i] & 255)<>0 : bad=bad+1 : EndIf
  EndIf
 Next
 For i=0 To 15 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 For i=157200 To 157199 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 NfpCheck(bad,0)
 For i=0 To 157199 : nfpAlpha[i]=165 : Next
 NfpCheck(AnvilTrueTypeControlRaster(0,@nfpAlpha[16],240),0)
 NfpCheck(AnvilTrueTypeControlRaster(513,@nfpAlpha[16],240),0)
 NfpCheck(AnvilTrueTypeControlRaster(20,@nfpAlpha[16],239),0)
 NfpCheck(AnvilTrueTypeControlRaster(20,0,240),0)
 NfpCheck(AnvilTrueTypeControlRaster(20,-8,240),0)
 NfpCheck(AnvilTrueTypeControlRaster(20,$7FFFFFFFFFFFFF80,240),0)
 bad=0
 For i=0 To 157199 : If (nfpAlpha[i] & 255)<>165 : bad=bad+1 : EndIf : Next
 NfpCheck(bad,0)
 NfpCheck(MathBitsOf(NeonVkPortFontTextWidth(@nfpHide,?nfpMixed,1)),1119879168)
 NfpCheck(MathBitsOf(NeonVkPortFontTextWidth(@nfpHide,?nfpControls,1)),0)
 NfpCheck(MathBitsOf(NeonVkPortFontTextWidth(@nfpShow,?nfpShowText,1)),1111490560)
 NfpCheck(MathBitsOf(NeonVkPortFontTextWidth(@nfpShow,?nfpBreaks,1)),1115684864)
 NfpCheck(NeonVkRetainedFontBytes(3),168)
 NfpCheck(NeonVkRetainedFontsConfigure(@nfpFonts[0],168,3),0)
 nfpRetained=NeonVkRetainedFontRegister(0,1,20)
 NfpCheck(Bool(nfpRetained>3),1)
 NfpCheck(NeonVkRetainedFontSetFixedAdvance(nfpRetained,16.0),0)
 NfpCheck(NeonVkRetainedFontSetShowControls(nfpRetained,1),0)
 NfpCheck(NeonVkRetainedFontSetShowControls(nfpRetained,2),-21312)
 NfpCheck(NeonVkRetainedInstall(),0)
 NfpCheck(NeonRetainedConfigure(@nfpArena[0],2048,2,128),0)
 NfpCheck(NeonRetainedViewport(0.0,0.0,800.0,1280.0,800.0,1280.0),0)
 NfpCheck(NeonRetainedFontSet(nfpRetained),0)
 old=NeonRetainedAddLabel(1,20.0,220.0,?nfpDelText)
 NfpCheck(Bool(old>0),1)
 NfpCheck(NeonVkPortFontWarm(@nfpPlain,?nfpPlainText),0)
 NfpCheck(NeonVkPortFontWarm(@nfpPlain,?nfpAV),0)
 NfpCheck(NeonVkPortFontWarm(@nfpHide,?nfpMixed),0)
 NfpCheck(NeonVkPortFontWarm(@nfpHide,?nfpControls),0)
 NfpCheck(NeonVkPortFontWarm(@nfpHide,?nfpShowText),0)
 NfpCheck(NeonVkPortFontWarm(@nfpShow,?nfpShowText),0)
 NfpCheck(NeonVkPortFontWarm(@nfpShow,?nfpBreaks),0)
 NfpCheck(NeonRetainedUpdateInput(1000.0,1500.0,0,0,0,0,0),0)
 NfpCheck(NeonRetainedPrepare(),0)
 NfpCheck(NeonVkChromeRebind(framebuffer,800,1280,800,1280,pitch,0),0)
 clear[0]=$3D23D70A : clear[1]=$3D4CCCCD : clear[2]=$3D8F5C29 : clear[3]=$3F800000
 NfpCheck(NeonVkChromeBegin(@clear[0]),0)
 NfpCheck(NeonVkPortFontSetControlMode(@nfpShow,1),-21311)
 NfpCheck(NeonVkRetainedFontSetShowControls(nfpRetained,0),-21311)
 NfpCheck(NeonVkPortFontText(@nfpHide,20.0,40.0,?nfpMixed,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpPlain,400.0,40.0,?nfpPlainText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpShow,20.0,100.0,?nfpShowText,1.0,1.0,1.0,1.0,1,1),0)
 NfpReference(400.0,100.0,0)
 NfpCheck(NeonVkPortFontText(@nfpShow,20.0,160.0,?nfpBreaks,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpPlain,400.0,160.0,?nfpA,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(416.0,160.0,12.0,1.0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(416.0,179.0,12.0,1.0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(416.0,161.0,1.0,18.0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(427.0,161.0,1.0,18.0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(432.0,160.0,12.0,1.0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(432.0,179.0,12.0,1.0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(432.0,161.0,1.0,18.0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortBox(443.0,161.0,1.0,18.0,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpPlain,448.0,160.0,?nfpV,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonRetainedDrawUI(0.0),0)
 NfpReference(400.0,220.0,1)
 NfpCheck(NeonVkPortFontText(@nfpHide,20.0,280.0,?nfpControls,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpHide,20.0,340.0,?nfpShowText,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkPortFontText(@nfpPlain,400.0,340.0,?nfpAV,1.0,1.0,1.0,1.0,1,1),0)
 NfpCheck(NeonVkChromeEnd(),0)
 NfpCheck(NeonVkChromeFrameRasterDelta(),0)
 NfpCheck(NeonVkChromeFrameUploadDelta(),0)
 NfpCheck(NeonVkChromeDrawCount(),30)
 NfpCheck(NeonVkChromeVertexCount(),306)
 NfpCheck(NeonVkChromePresentConsume(),1)
 For i=0 To #NFP_PIXEL_BYTES+24 Step 8 : PokeI(#NFP_PIXELS+i,$A5A5A5A5A5A5A5A5) : poisoned=poisoned+8 : Next
 For row=0 To 5
  For part=0 To 1
   src=imageBase+(40+row*60)*pitch+(20+part*380)*4
   dst=#NFP_PIXELS+16+(row*2+part)*30720
   For i=0 To 31
    For j=0 To 952 Step 8
     PokeI(dst+i*960+j,PeekI(src+i*pitch+j)) : copied=copied+8
    Next
   Next
  Next
 Next
 PokeI(#NFP_REPORT+40,copied) : PokeI(#NFP_REPORT+48,poisoned)
 PokeI(#NFP_REPORT+112,NeonVkChromeDrawCount()) : PokeI(#NFP_REPORT+120,NeonVkChromeVertexCount())
 ProcedureReturn nfpFailure
EndProcedure

Procedure NfpRetired(report.i)
 Protected count.l=12345,rc.i
 PokeI(#NFP_REPORT+80,AnvilVkFaultCount())
 NfpCheck(NeonVkChromeReady(),0)
 NfpCheck(NeonDrawBackendActive(),0)
 NfpCheck(Neon_Ready(),0)
 rc=vkDeviceWaitIdle(PeekL(report+24))
 NfpCheck(rc,-20002)
 rc=vkEnumeratePhysicalDevices(PeekL(report+16),@count,0)
 NfpCheck(rc,-20002)
 NfpCheck(count,12345)
 PokeI(#NFP_REPORT+88,AnvilVkFaultCount())
EndProcedure

DataSection
nfpMixed:
 Data.a 65,9,86,10,65,13,84,127,65,1,82,0
nfpControls:
 Data.a 9,10,13,127,1,0
nfpShowText:
 Data.a 65,9,86,0
nfpBreaks:
 Data.a 65,13,10,86,0
nfpDelText:
 Data.a 65,127,86,0
nfpPlainText:
 Data.a 65,86,65,84,65,82,0
nfpAV:
 Data.a 65,86,0
nfpA:
 Data.a 65,0
nfpV:
 Data.a 86,0
nfpBad:
 Data.a 192,175,0
nfpC1:
 Data.a 194,128,0
nfpNul:
 Data.a 0,0
EndDataSection
