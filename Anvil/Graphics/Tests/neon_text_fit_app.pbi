; SPDX-License-Identifier: MIT
; Measured UTF8 fitting, refusal preservation and native prepared-font equivalence.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_text_fit.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_text_fit.pbi"
Global Dim nftOutput.q[18]
Global Dim nftScratch.q[34]
Global Dim nftNative.a[128]
Global Dim nftReference.a[128]
Global nftChecks.i,nftFailure.i,nftMode.i,nftReentered.i
Procedure NftCheck(actual.i,expected.i)
 PokeI(#NFT_REPORT+256+nftChecks*16,actual) : PokeI(#NFT_REPORT+264+nftChecks*16,expected)
 nftChecks=nftChecks+1
 If actual<>expected And nftFailure=0 : nftFailure=nftChecks : EndIf
EndProcedure
Procedure.f NftWidth(font.i,text.i)
 Protected n.i=NeonUtf8Length(text,256),i.i,count.i
 If nftMode=1 : ProcedureReturn -1.0 : EndIf
 If nftMode=2 : ProcedureReturn MathFromBits($7FC00000) : EndIf
 If nftMode=3
  nftMode=0
  NftCheck(NeonTextFitUnbind(),#NEON_TEXT_FIT_ERR_BUSY)
  NftCheck(NeonTextFitBind(@NftWidth),#NEON_TEXT_FIT_ERR_BUSY)
  nftReentered=1
 EndIf
 While i<n : i=NeonUtf8Next(text,n,i) : count=count+1 : Wend
 ProcedureReturn MathFFromInt(count*7)
EndProcedure
Procedure NftFill()
 Protected i.i
 For i=0 To 143 : PokeA(@nftOutput[0]+i,165) : Next
 For i=0 To 271 : PokeA(@nftScratch[0]+i,60) : Next
EndProcedure
Procedure NftCase(index.i,source.i,sourceBytes.i,tail.i,tailBytes.i,room.f,capacity.i,expected.i)
 Protected p.i=#NFT_REPORT+8192+index*512,rc.i,i.i
 NftFill()
 rc=NeonTextFit(@nftOutput[1],capacity,@nftScratch[1],256,source,sourceBytes,tail,tailBytes,0,room)
 NftCheck(rc,expected)
 PokeI(p,rc) : PokeI(p+8,capacity) : PokeI(p+16,sourceBytes) : PokeI(p+24,tailBytes)
 PokeL(p+32,MathBitsOf(room))
 PokeI(p+40,PeekI(@nftScratch[0])) : PokeI(p+48,PeekI(@nftScratch[33]))
 For i=0 To 143 : PokeA(p+64+i,PeekA(@nftOutput[0]+i)) : Next
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,n.i,j.i,cut.i,best.i,font.i,rc.i,source.i,p.i=#NFT_REPORT+49152,width.f
 For i=0 To #NFT_REPORT_BYTES-1 : PokeA(#NFT_REPORT+i,0) : Next
 PokeI(#NFT_REPORT,$4E465431) : PokeI(#NFT_REPORT+8,1)
 NftCheck(NeonTextFitBind(@NftWidth),0)
 NftCase(0,?nftSource0,1,?nftTail0,4,0.0,128,0)
 NftCase(1,?nftSource1,1,?nftTail1,4,21.0,128,0)
 NftCase(2,?nftSource2,1,?nftTail2,4,35.0,128,0)
 NftCase(3,?nftSource3,1,?nftTail3,4,63.0,128,0)
 NftCase(4,?nftSource4,1,?nftTail4,4,0.0,128,0)
 NftCase(5,?nftSource5,1,?nftTail5,4,21.0,128,0)
 NftCase(6,?nftSource6,1,?nftTail6,4,35.0,128,0)
 NftCase(7,?nftSource7,1,?nftTail7,4,63.0,128,0)
 NftCase(8,?nftSource8,10,?nftTail8,4,0.0,128,0)
 NftCase(9,?nftSource9,10,?nftTail9,4,21.0,128,3)
 NftCase(10,?nftSource10,10,?nftTail10,4,35.0,128,5)
 NftCase(11,?nftSource11,10,?nftTail11,4,63.0,128,9)
 NftCase(12,?nftSource12,10,?nftTail12,4,0.0,128,0)
 NftCase(13,?nftSource13,10,?nftTail13,4,21.0,128,5)
 NftCase(14,?nftSource14,10,?nftTail14,4,35.0,128,7)
 NftCase(15,?nftSource15,10,?nftTail15,4,63.0,128,9)
 NftCase(16,?nftSource16,14,?nftTail16,4,0.0,128,0)
 NftCase(17,?nftSource17,14,?nftTail17,4,21.0,128,3)
 NftCase(18,?nftSource18,14,?nftTail18,4,35.0,128,5)
 NftCase(19,?nftSource19,14,?nftTail19,4,63.0,128,9)
 NftCase(20,?nftSource20,14,?nftTail20,4,0.0,128,0)
 NftCase(21,?nftSource21,14,?nftTail21,4,21.0,128,5)
 NftCase(22,?nftSource22,14,?nftTail22,4,35.0,128,6)
 NftCase(23,?nftSource23,14,?nftTail23,4,63.0,128,10)
 NftCase(24,?nftSource24,16,?nftTail24,4,0.0,128,0)
 NftCase(25,?nftSource25,16,?nftTail25,4,21.0,128,3)
 NftCase(26,?nftSource26,16,?nftTail26,4,35.0,128,8)
 NftCase(27,?nftSource27,16,?nftTail27,4,63.0,128,15)
 NftCase(28,?nftSource28,16,?nftTail28,4,0.0,128,0)
 NftCase(29,?nftSource29,16,?nftTail29,4,21.0,128,8)
 NftCase(30,?nftSource30,16,?nftTail30,4,35.0,128,13)
 NftCase(31,?nftSource31,16,?nftTail31,4,63.0,128,15)
 NftCase(32,?nftSource32,13,?nftTail32,4,0.0,128,0)
 NftCase(33,?nftSource33,13,?nftTail33,4,21.0,128,3)
 NftCase(34,?nftSource34,13,?nftTail34,4,35.0,128,6)
 NftCase(35,?nftSource35,13,?nftTail35,4,63.0,128,10)
 NftCase(36,?nftSource36,13,?nftTail36,4,0.0,128,0)
 NftCase(37,?nftSource37,13,?nftTail37,4,21.0,128,6)
 NftCase(38,?nftSource38,13,?nftTail38,4,35.0,128,8)
 NftCase(39,?nftSource39,13,?nftTail39,4,63.0,128,12)
 NftCase(40,?nftSource40,14,?nftTail40,4,0.0,128,0)
 NftCase(41,?nftSource41,14,?nftTail41,4,21.0,128,3)
 NftCase(42,?nftSource42,14,?nftTail42,4,35.0,128,7)
 NftCase(43,?nftSource43,14,?nftTail43,4,63.0,128,11)
 NftCase(44,?nftSource44,14,?nftTail44,4,0.0,128,0)
 NftCase(45,?nftSource45,14,?nftTail45,4,21.0,128,7)
 NftCase(46,?nftSource46,14,?nftTail46,4,35.0,128,9)
 NftCase(47,?nftSource47,14,?nftTail47,4,63.0,128,13)
 NftCase(48,?nftSource48,21,?nftTail48,4,0.0,128,0)
 NftCase(49,?nftSource49,21,?nftTail49,4,21.0,128,3)
 NftCase(50,?nftSource50,21,?nftTail50,4,35.0,128,3)
 NftCase(51,?nftSource51,21,?nftTail51,4,63.0,128,17)
 NftCase(52,?nftSource52,21,?nftTail52,4,0.0,128,0)
 NftCase(53,?nftSource53,21,?nftTail53,4,21.0,128,3)
 NftCase(54,?nftSource54,21,?nftTail54,4,35.0,128,15)
 NftCase(55,?nftSource55,21,?nftTail55,4,63.0,128,19)
 NftCase(56,?nftSource56,2,?nftTail56,4,35.0,128,-23101)
 NftCase(57,?nftSource57,3,?nftTail57,4,35.0,128,-23101)
 NftCase(58,?nftSource58,4,?nftTail58,4,35.0,128,-23101)
 NftCase(59,?nftSource59,5,?nftTail59,4,35.0,128,-23101)
 NftCase(60,?nftSource60,3,?nftTail60,4,35.0,128,-23101)
 NftCase(61,?nftSource61,10,?nftTail61,4,35.0,1,-23102)
 NftCase(62,?nftSource62,10,?nftTail62,4,35.0,4,-23102)
 NftCase(63,?nftSource63,10,?nftTail63,4,35.0,7,5)
 NftFill()
 NftCheck(NeonTextFitUnbind(),0)
 NftCheck(NeonTextFit(@nftOutput[1],128,@nftScratch[1],256,"abcdef",7,"...",4,0,21.0),#NEON_TEXT_FIT_ERR_UNBOUND)
 NftCheck(NeonTextFitBind(0),#NEON_TEXT_FIT_ERR_ARGS)
 NftCheck(NeonTextFitBind(@NftWidth),0)
 NftCheck(NeonTextFit(0,128,@nftScratch[1],256,"abcdef",7,"...",4,0,21.0),#NEON_TEXT_FIT_ERR_ARGS)
 NftCheck(NeonTextFit(@nftOutput[1],128,@nftOutput[1],256,"abcdef",7,"...",4,0,21.0),#NEON_TEXT_FIT_ERR_ARGS)
 NftCheck(NeonTextFit(@nftOutput[1],128,@nftScratch[1],256,"abcdef",0,"...",4,0,21.0),#NEON_TEXT_FIT_ERR_ARGS)
 NftCheck(NeonTextFit(@nftOutput[1],128,@nftScratch[1],256,"abcdef",7,"...",4,-1,21.0),#NEON_TEXT_FIT_ERR_ARGS)
 NftCheck(NeonTextFit(@nftOutput[1],128,@nftScratch[1],256,"abcdef",7,"...",4,0,MathFromBits($7FC00000)),#NEON_TEXT_FIT_ERR_ARGS)
 NftCheck(NeonTextFit(@nftOutput[1],128,@nftScratch[1],1,"abcdef",7,"...",4,0,21.0),#NEON_TEXT_FIT_ERR_CAPACITY)
 nftMode=1
 NftCheck(NeonTextFit(@nftOutput[1],128,@nftScratch[1],256,"abcdef",7,"...",4,0,21.0),#NEON_TEXT_FIT_ERR_METRICS)
 nftMode=2
 NftCheck(NeonTextFit(@nftOutput[1],128,@nftScratch[1],256,"abcdef",7,"...",4,0,21.0),#NEON_TEXT_FIT_ERR_METRICS)
 For i=0 To 143 : PokeA(#NFT_REPORT+4096+i,PeekA(@nftOutput[0]+i)) : Next
 nftMode=3
 NftCheck(NeonTextFit(@nftOutput[1],128,@nftScratch[1],256,"abcdef",7,"...",4,0,21.0),3)
 NftCheck(nftReentered,1)
 NftCheck(NeonServiceBind(services,35),0) : NftCheck(NeonServiceOpen(),0)
 NftCheck(NeonServiceCanvas(640,400),0)
 font=NeonServiceFontRegister(0,1,14) : NftCheck(Bool(font>3),1)
 source="Neon settings and display configuration" : n=NeonUtf8Length(source,128)
 NftCheck(NeonServicePrepare(font,source),0) : NftCheck(NeonServicePrepare(font,"..."),0)
 NftCheck(NeonServiceTextFitInstall(),0)
 rc=NeonTextFit(@nftNative[0],128,@nftScratch[1],256,source,n+1,"...",4,font,140.0)
 NftCheck(Bool(rc>=0),1)
 PokeI(p,rc) : PokeI(p+8,n) : PokeI(p+16,font)
 PokeL(p+24,MathBitsOf(NeonServiceTextWidth(font,source)))
 PokeL(p+28,MathBitsOf(NeonServiceTextWidth(font,@nftNative[0])))
 For i=0 To 127 : PokeA(p+64+i,PeekA(@nftNative[0]+i)) : Next
 ; Independent linear enumeration, not the fitter's binary search/prefix helper.
 best=-1
 For i=0 To n-1
  cut=i
  While cut>0
   If (PeekA(source+cut-1) & 255)<>32 : Break : EndIf
   cut=cut-1
  Wend
  For j=0 To cut-1 : PokeA(@nftReference[0]+j,PeekA(source+j)) : Next
  PokeA(@nftReference[0]+cut,46) : PokeA(@nftReference[0]+cut+1,46)
  PokeA(@nftReference[0]+cut+2,46) : PokeA(@nftReference[0]+cut+3,0)
  width=NeonServiceTextWidth(font,@nftReference[0])
  PokeL(p+512+i*4,MathBitsOf(width))
  If width<=140.0 : best=cut : EndIf
 Next
 NftCheck(Bool(best>=0),1)
 For j=0 To best-1 : PokeA(@nftReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nftReference[0]+best,46) : PokeA(@nftReference[0]+best+1,46)
 PokeA(@nftReference[0]+best+2,46) : PokeA(@nftReference[0]+best+3,0)
 PokeI(p+32,best)
 For i=0 To 127 : PokeA(p+256+i,PeekA(@nftReference[0]+i)) : Next
 NftCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
 NftCheck(NeonServiceText(font,20.0,80.0,@nftNative[0],1.0,1.0,1.0,1.0),0)
 NftCheck(NeonServiceText(font,340.0,80.0,@nftReference[0],1.0,1.0,1.0,1.0),0)
 NftCheck(NeonServiceEnd(),0) : NftCheck(NeonTextFitUnbind(),0)
 PokeI(#NFT_REPORT+16,nftFailure) : PokeI(#NFT_REPORT+24,nftChecks)
 ProcedureReturn nftFailure
EndProcedure
DataSection
nftSource0:
 Data.a 0
nftTail0:
 Data.a 46,46,46,0
nftSource1:
 Data.a 0
nftTail1:
 Data.a 46,46,46,0
nftSource2:
 Data.a 0
nftTail2:
 Data.a 46,46,46,0
nftSource3:
 Data.a 0
nftTail3:
 Data.a 46,46,46,0
nftSource4:
 Data.a 0
nftTail4:
 Data.a 226,128,166,0
nftSource5:
 Data.a 0
nftTail5:
 Data.a 226,128,166,0
nftSource6:
 Data.a 0
nftTail6:
 Data.a 226,128,166,0
nftSource7:
 Data.a 0
nftTail7:
 Data.a 226,128,166,0
nftSource8:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail8:
 Data.a 46,46,46,0
nftSource9:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail9:
 Data.a 46,46,46,0
nftSource10:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail10:
 Data.a 46,46,46,0
nftSource11:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail11:
 Data.a 46,46,46,0
nftSource12:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail12:
 Data.a 226,128,166,0
nftSource13:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail13:
 Data.a 226,128,166,0
nftSource14:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail14:
 Data.a 226,128,166,0
nftSource15:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail15:
 Data.a 226,128,166,0
nftSource16:
 Data.a 111,110,101,32,116,119,111,32,116,104,114,101,101,0
nftTail16:
 Data.a 46,46,46,0
nftSource17:
 Data.a 111,110,101,32,116,119,111,32,116,104,114,101,101,0
nftTail17:
 Data.a 46,46,46,0
nftSource18:
 Data.a 111,110,101,32,116,119,111,32,116,104,114,101,101,0
nftTail18:
 Data.a 46,46,46,0
nftSource19:
 Data.a 111,110,101,32,116,119,111,32,116,104,114,101,101,0
nftTail19:
 Data.a 46,46,46,0
nftSource20:
 Data.a 111,110,101,32,116,119,111,32,116,104,114,101,101,0
nftTail20:
 Data.a 226,128,166,0
nftSource21:
 Data.a 111,110,101,32,116,119,111,32,116,104,114,101,101,0
nftTail21:
 Data.a 226,128,166,0
nftSource22:
 Data.a 111,110,101,32,116,119,111,32,116,104,114,101,101,0
nftTail22:
 Data.a 226,128,166,0
nftSource23:
 Data.a 111,110,101,32,116,119,111,32,116,104,114,101,101,0
nftTail23:
 Data.a 226,128,166,0
nftSource24:
 Data.a 195,169,230,176,180,240,159,152,128,97,98,99,100,101,102,0
nftTail24:
 Data.a 46,46,46,0
nftSource25:
 Data.a 195,169,230,176,180,240,159,152,128,97,98,99,100,101,102,0
nftTail25:
 Data.a 46,46,46,0
nftSource26:
 Data.a 195,169,230,176,180,240,159,152,128,97,98,99,100,101,102,0
nftTail26:
 Data.a 46,46,46,0
nftSource27:
 Data.a 195,169,230,176,180,240,159,152,128,97,98,99,100,101,102,0
nftTail27:
 Data.a 46,46,46,0
nftSource28:
 Data.a 195,169,230,176,180,240,159,152,128,97,98,99,100,101,102,0
nftTail28:
 Data.a 226,128,166,0
nftSource29:
 Data.a 195,169,230,176,180,240,159,152,128,97,98,99,100,101,102,0
nftTail29:
 Data.a 226,128,166,0
nftSource30:
 Data.a 195,169,230,176,180,240,159,152,128,97,98,99,100,101,102,0
nftTail30:
 Data.a 226,128,166,0
nftSource31:
 Data.a 195,169,230,176,180,240,159,152,128,97,98,99,100,101,102,0
nftTail31:
 Data.a 226,128,166,0
nftSource32:
 Data.a 101,204,129,97,98,99,100,101,102,103,104,105,0
nftTail32:
 Data.a 46,46,46,0
nftSource33:
 Data.a 101,204,129,97,98,99,100,101,102,103,104,105,0
nftTail33:
 Data.a 46,46,46,0
nftSource34:
 Data.a 101,204,129,97,98,99,100,101,102,103,104,105,0
nftTail34:
 Data.a 46,46,46,0
nftSource35:
 Data.a 101,204,129,97,98,99,100,101,102,103,104,105,0
nftTail35:
 Data.a 46,46,46,0
nftSource36:
 Data.a 101,204,129,97,98,99,100,101,102,103,104,105,0
nftTail36:
 Data.a 226,128,166,0
nftSource37:
 Data.a 101,204,129,97,98,99,100,101,102,103,104,105,0
nftTail37:
 Data.a 226,128,166,0
nftSource38:
 Data.a 101,204,129,97,98,99,100,101,102,103,104,105,0
nftTail38:
 Data.a 226,128,166,0
nftSource39:
 Data.a 101,204,129,97,98,99,100,101,102,103,104,105,0
nftTail39:
 Data.a 226,128,166,0
nftSource40:
 Data.a 65,239,184,143,97,98,99,100,101,102,103,104,105,0
nftTail40:
 Data.a 46,46,46,0
nftSource41:
 Data.a 65,239,184,143,97,98,99,100,101,102,103,104,105,0
nftTail41:
 Data.a 46,46,46,0
nftSource42:
 Data.a 65,239,184,143,97,98,99,100,101,102,103,104,105,0
nftTail42:
 Data.a 46,46,46,0
nftSource43:
 Data.a 65,239,184,143,97,98,99,100,101,102,103,104,105,0
nftTail43:
 Data.a 46,46,46,0
nftSource44:
 Data.a 65,239,184,143,97,98,99,100,101,102,103,104,105,0
nftTail44:
 Data.a 226,128,166,0
nftSource45:
 Data.a 65,239,184,143,97,98,99,100,101,102,103,104,105,0
nftTail45:
 Data.a 226,128,166,0
nftSource46:
 Data.a 65,239,184,143,97,98,99,100,101,102,103,104,105,0
nftTail46:
 Data.a 226,128,166,0
nftSource47:
 Data.a 65,239,184,143,97,98,99,100,101,102,103,104,105,0
nftTail47:
 Data.a 226,128,166,0
nftSource48:
 Data.a 240,159,145,169,226,128,141,240,159,146,187,97,98,99,100,101,102,103,104,105,0
nftTail48:
 Data.a 46,46,46,0
nftSource49:
 Data.a 240,159,145,169,226,128,141,240,159,146,187,97,98,99,100,101,102,103,104,105,0
nftTail49:
 Data.a 46,46,46,0
nftSource50:
 Data.a 240,159,145,169,226,128,141,240,159,146,187,97,98,99,100,101,102,103,104,105,0
nftTail50:
 Data.a 46,46,46,0
nftSource51:
 Data.a 240,159,145,169,226,128,141,240,159,146,187,97,98,99,100,101,102,103,104,105,0
nftTail51:
 Data.a 46,46,46,0
nftSource52:
 Data.a 240,159,145,169,226,128,141,240,159,146,187,97,98,99,100,101,102,103,104,105,0
nftTail52:
 Data.a 226,128,166,0
nftSource53:
 Data.a 240,159,145,169,226,128,141,240,159,146,187,97,98,99,100,101,102,103,104,105,0
nftTail53:
 Data.a 226,128,166,0
nftSource54:
 Data.a 240,159,145,169,226,128,141,240,159,146,187,97,98,99,100,101,102,103,104,105,0
nftTail54:
 Data.a 226,128,166,0
nftSource55:
 Data.a 240,159,145,169,226,128,141,240,159,146,187,97,98,99,100,101,102,103,104,105,0
nftTail55:
 Data.a 226,128,166,0
nftSource56:
 Data.a 128,0
nftTail56:
 Data.a 46,46,46,0
nftSource57:
 Data.a 192,128,0
nftTail57:
 Data.a 46,46,46,0
nftSource58:
 Data.a 237,160,128,0
nftTail58:
 Data.a 46,46,46,0
nftSource59:
 Data.a 244,144,128,128,0
nftTail59:
 Data.a 46,46,46,0
nftSource60:
 Data.a 226,130,0
nftTail60:
 Data.a 46,46,46,0
nftSource61:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail61:
 Data.a 46,46,46,0
nftSource62:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail62:
 Data.a 46,46,46,0
nftSource63:
 Data.a 97,98,99,100,101,102,103,104,105,0
nftTail63:
 Data.a 46,46,46,0
EndDataSection
