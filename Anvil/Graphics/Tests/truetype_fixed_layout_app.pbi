; SPDX-License-Identifier: MIT
EnableFloatingPoint
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Hal/file_service_client.pbi"
XIncludeFile "Anvil/Graphics/truetype.pbi"
XIncludeFile "Anvil/Graphics/truetype_metrics.pbi"
XIncludeFile "Anvil/Graphics/truetype_cmap.pbi"
XIncludeFile "Anvil/Graphics/truetype_kern.pbi"
XIncludeFile "Anvil/Graphics/truetype_gpos.pbi"
XIncludeFile "Anvil/Graphics/truetype_layout.pbi"
Global Dim tfxFont.q[131072]
Global Dim tfxGlyph.q[18]
Global Dim tfxX.q[18]
Global Dim tfxY.q[18]
Global Dim tfxAdvance.q[18]
Global tfxChecks.i,tfxFailure.i
Procedure TfxCheck(actual.i,expected.i)
 PokeI(#TFX_REPORT+256+tfxChecks*16,actual) : PokeI(#TFX_REPORT+264+tfxChecks*16,expected)
 tfxChecks=tfxChecks+1
 If actual<>expected And tfxFailure=0 : tfxFailure=tfxChecks : EndIf
EndProcedure
Procedure TfxCase(index.i,source.i,bytes.i,mode.i,fixed.i,width.i,align.i,capacity.i)
 Protected i.i,rc.i,count.i=-99,lines.i=-99,measured.i=-99,p.i=#TFX_REPORT+8192+index*768
 For i=0 To 143
  PokeA(@tfxGlyph[0]+i,165) : PokeA(@tfxX[0]+i,165)
  PokeA(@tfxY[0]+i,165) : PokeA(@tfxAdvance[0]+i,165)
 Next
 If mode=0
  rc=AnvilTrueTypeLayoutUtf8(source,bytes,14,width,16,@tfxGlyph[1],@tfxX[1],@tfxY[1],@tfxAdvance[1],align,capacity,@count,@lines,@measured)
 Else
  rc=AnvilTrueTypeLayoutUtf8Fixed(source,bytes,14,width,16,@tfxGlyph[1],@tfxX[1],@tfxY[1],@tfxAdvance[1],align,capacity,@count,@lines,@measured,fixed)
 EndIf
 PokeI(p,rc) : PokeI(p+8,AnvilTrueTypeLayoutError()) : PokeI(p+16,count)
 PokeI(p+24,lines) : PokeI(p+32,measured)
 For i=0 To 143
  PokeA(p+64+i,PeekA(@tfxGlyph[0]+i)) : PokeA(p+208+i,PeekA(@tfxX[0]+i))
  PokeA(p+352+i,PeekA(@tfxY[0]+i)) : PokeA(p+496+i,PeekA(@tfxAdvance[0]+i))
 Next
EndProcedure
Procedure.i Main(services.i)
 Protected i.i
 For i=0 To #TFX_REPORT_BYTES-1 : PokeA(#TFX_REPORT+i,0) : Next
 PokeI(#TFX_REPORT,$54465831) : PokeI(#TFX_REPORT+8,1)
 TfxCheck(AnvilFileBind(services),0)
 TfxCheck(AnvilFileReadWhole("2:/fonts/Lato-Regular.ttf",@tfxFont[0],1048576),656568)
 TfxCheck(AnvilTrueTypeOpen(@tfxFont[0],656568),1)
 TfxCheck(AnvilTrueTypeMetricsOpen(),1) : TfxCheck(AnvilTrueTypeCmapOpen(),1)
 TfxCheck(AnvilTrueTypeKernOpen(),1) : TfxCheck(AnvilTrueTypeGposOpen(),1)
 If tfxFailure<>0 : ProcedureReturn tfxFailure : EndIf
TfxCase(0,?tfxSource0,6,0,0,0,0,16)
TfxCase(1,?tfxSource1,6,0,0,28,2,16)
TfxCase(2,?tfxSource2,5,0,0,0,0,16)
TfxCase(3,?tfxSource3,5,0,0,28,2,16)
TfxCase(4,?tfxSource4,10,0,0,0,0,16)
TfxCase(5,?tfxSource5,10,0,0,28,2,16)
TfxCase(6,?tfxSource6,4,0,0,0,0,16)
TfxCase(7,?tfxSource7,4,0,0,28,2,16)
TfxCase(8,?tfxSource8,6,0,0,0,0,16)
TfxCase(9,?tfxSource9,6,0,0,28,2,16)
TfxCase(10,?tfxSource10,0,0,0,0,0,16)
TfxCase(11,?tfxSource11,0,0,0,28,2,16)
TfxCase(12,?tfxSource12,3,0,0,0,0,16)
TfxCase(13,?tfxSource13,3,0,0,28,2,16)
TfxCase(14,?tfxSource14,14,0,0,0,0,16)
TfxCase(15,?tfxSource15,14,0,0,28,2,16)
TfxCase(16,?tfxSource16,6,1,458752,28,0,16)
TfxCase(17,?tfxSource17,6,1,458752,28,1,16)
TfxCase(18,?tfxSource18,6,1,458752,28,2,16)
TfxCase(19,?tfxSource19,6,1,491520,28,0,16)
TfxCase(20,?tfxSource20,6,1,491520,28,1,16)
TfxCase(21,?tfxSource21,6,1,491520,28,2,16)
TfxCase(22,?tfxSource22,5,1,458752,28,0,16)
TfxCase(23,?tfxSource23,5,1,458752,28,1,16)
TfxCase(24,?tfxSource24,5,1,458752,28,2,16)
TfxCase(25,?tfxSource25,5,1,491520,28,0,16)
TfxCase(26,?tfxSource26,5,1,491520,28,1,16)
TfxCase(27,?tfxSource27,5,1,491520,28,2,16)
TfxCase(28,?tfxSource28,10,1,458752,28,0,16)
TfxCase(29,?tfxSource29,10,1,458752,28,1,16)
TfxCase(30,?tfxSource30,10,1,458752,28,2,16)
TfxCase(31,?tfxSource31,10,1,491520,28,0,16)
TfxCase(32,?tfxSource32,10,1,491520,28,1,16)
TfxCase(33,?tfxSource33,10,1,491520,28,2,16)
TfxCase(34,?tfxSource34,4,1,458752,28,0,16)
TfxCase(35,?tfxSource35,4,1,458752,28,1,16)
TfxCase(36,?tfxSource36,4,1,458752,28,2,16)
TfxCase(37,?tfxSource37,4,1,491520,28,0,16)
TfxCase(38,?tfxSource38,4,1,491520,28,1,16)
TfxCase(39,?tfxSource39,4,1,491520,28,2,16)
TfxCase(40,?tfxSource40,6,1,458752,28,0,16)
TfxCase(41,?tfxSource41,6,1,458752,28,1,16)
TfxCase(42,?tfxSource42,6,1,458752,28,2,16)
TfxCase(43,?tfxSource43,6,1,491520,28,0,16)
TfxCase(44,?tfxSource44,6,1,491520,28,1,16)
TfxCase(45,?tfxSource45,6,1,491520,28,2,16)
TfxCase(46,?tfxSource46,0,1,458752,28,0,16)
TfxCase(47,?tfxSource47,0,1,458752,28,1,16)
TfxCase(48,?tfxSource48,0,1,458752,28,2,16)
TfxCase(49,?tfxSource49,0,1,491520,28,0,16)
TfxCase(50,?tfxSource50,0,1,491520,28,1,16)
TfxCase(51,?tfxSource51,0,1,491520,28,2,16)
TfxCase(52,?tfxSource52,3,1,458752,28,0,16)
TfxCase(53,?tfxSource53,3,1,458752,28,1,16)
TfxCase(54,?tfxSource54,3,1,458752,28,2,16)
TfxCase(55,?tfxSource55,3,1,491520,28,0,16)
TfxCase(56,?tfxSource56,3,1,491520,28,1,16)
TfxCase(57,?tfxSource57,3,1,491520,28,2,16)
TfxCase(58,?tfxSource58,14,1,458752,28,0,16)
TfxCase(59,?tfxSource59,14,1,458752,28,1,16)
TfxCase(60,?tfxSource60,14,1,458752,28,2,16)
TfxCase(61,?tfxSource61,14,1,491520,28,0,16)
TfxCase(62,?tfxSource62,14,1,491520,28,1,16)
TfxCase(63,?tfxSource63,14,1,491520,28,2,16)
TfxCase(64,?tfxSource64,2,1,-1,0,0,16)
TfxCase(65,?tfxSource65,2,1,536870913,0,0,16)
TfxCase(66,?tfxSource66,2,1,458752,0,0,-1)
TfxCase(67,?tfxSource67,2,1,458752,0,0,1)
TfxCase(68,?tfxSource68,2,1,458752,0,0,16)
 PokeI(#TFX_REPORT+16,tfxFailure) : PokeI(#TFX_REPORT+24,tfxChecks) : PokeI(#TFX_REPORT+32,69)
 ProcedureReturn tfxFailure
EndProcedure
DataSection
tfxSource0:
 Data.a 65,86,65,84,65,82,0
tfxSource1:
 Data.a 65,86,65,84,65,82,0
tfxSource2:
 Data.a 84,111,32,87,97,0
tfxSource3:
 Data.a 84,111,32,87,97,0
tfxSource4:
 Data.a 99,97,102,195,169,32,240,159,152,128,0
tfxSource5:
 Data.a 99,97,102,195,169,32,240,159,152,128,0
tfxSource6:
 Data.a 101,204,129,120,0
tfxSource7:
 Data.a 101,204,129,120,0
tfxSource8:
 Data.a 97,13,10,98,10,99,0
tfxSource9:
 Data.a 97,13,10,98,10,99,0
tfxSource10:
 Data.a 0
tfxSource11:
 Data.a 0
tfxSource12:
 Data.a 97,98,10,0
tfxSource13:
 Data.a 97,98,10,0
tfxSource14:
 Data.a 108,111,110,103,32,119,114,97,112,32,116,101,120,116,0
tfxSource15:
 Data.a 108,111,110,103,32,119,114,97,112,32,116,101,120,116,0
tfxSource16:
 Data.a 65,86,65,84,65,82,0
tfxSource17:
 Data.a 65,86,65,84,65,82,0
tfxSource18:
 Data.a 65,86,65,84,65,82,0
tfxSource19:
 Data.a 65,86,65,84,65,82,0
tfxSource20:
 Data.a 65,86,65,84,65,82,0
tfxSource21:
 Data.a 65,86,65,84,65,82,0
tfxSource22:
 Data.a 84,111,32,87,97,0
tfxSource23:
 Data.a 84,111,32,87,97,0
tfxSource24:
 Data.a 84,111,32,87,97,0
tfxSource25:
 Data.a 84,111,32,87,97,0
tfxSource26:
 Data.a 84,111,32,87,97,0
tfxSource27:
 Data.a 84,111,32,87,97,0
tfxSource28:
 Data.a 99,97,102,195,169,32,240,159,152,128,0
tfxSource29:
 Data.a 99,97,102,195,169,32,240,159,152,128,0
tfxSource30:
 Data.a 99,97,102,195,169,32,240,159,152,128,0
tfxSource31:
 Data.a 99,97,102,195,169,32,240,159,152,128,0
tfxSource32:
 Data.a 99,97,102,195,169,32,240,159,152,128,0
tfxSource33:
 Data.a 99,97,102,195,169,32,240,159,152,128,0
tfxSource34:
 Data.a 101,204,129,120,0
tfxSource35:
 Data.a 101,204,129,120,0
tfxSource36:
 Data.a 101,204,129,120,0
tfxSource37:
 Data.a 101,204,129,120,0
tfxSource38:
 Data.a 101,204,129,120,0
tfxSource39:
 Data.a 101,204,129,120,0
tfxSource40:
 Data.a 97,13,10,98,10,99,0
tfxSource41:
 Data.a 97,13,10,98,10,99,0
tfxSource42:
 Data.a 97,13,10,98,10,99,0
tfxSource43:
 Data.a 97,13,10,98,10,99,0
tfxSource44:
 Data.a 97,13,10,98,10,99,0
tfxSource45:
 Data.a 97,13,10,98,10,99,0
tfxSource46:
 Data.a 0
tfxSource47:
 Data.a 0
tfxSource48:
 Data.a 0
tfxSource49:
 Data.a 0
tfxSource50:
 Data.a 0
tfxSource51:
 Data.a 0
tfxSource52:
 Data.a 97,98,10,0
tfxSource53:
 Data.a 97,98,10,0
tfxSource54:
 Data.a 97,98,10,0
tfxSource55:
 Data.a 97,98,10,0
tfxSource56:
 Data.a 97,98,10,0
tfxSource57:
 Data.a 97,98,10,0
tfxSource58:
 Data.a 108,111,110,103,32,119,114,97,112,32,116,101,120,116,0
tfxSource59:
 Data.a 108,111,110,103,32,119,114,97,112,32,116,101,120,116,0
tfxSource60:
 Data.a 108,111,110,103,32,119,114,97,112,32,116,101,120,116,0
tfxSource61:
 Data.a 108,111,110,103,32,119,114,97,112,32,116,101,120,116,0
tfxSource62:
 Data.a 108,111,110,103,32,119,114,97,112,32,116,101,120,116,0
tfxSource63:
 Data.a 108,111,110,103,32,119,114,97,112,32,116,101,120,116,0
tfxSource64:
 Data.a 97,98,0
tfxSource65:
 Data.a 97,98,0
tfxSource66:
 Data.a 97,98,0
tfxSource67:
 Data.a 97,98,0
tfxSource68:
 Data.a 192,128,0
EndDataSection
