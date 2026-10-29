; SPDX-License-Identifier: MIT
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_text_column.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
XIncludeFile "Anvil/Graphics/neon_service_text_column.pbi"
Global Dim nclOut.q[4]
Global Dim nclScratch.q[18]
Global Dim nclReference.a[128]
Global Dim nclNativeX.f[32]
Global nclMode.i,nclChecks.i,nclFailure.i,nclBusyBind.i,nclBusyUnbind.i
Procedure NclCheck(actual.i,expected.i)
 PokeI(#NCL_REPORT+256+nclChecks*16,actual) : PokeI(#NCL_REPORT+264+nclChecks*16,expected)
 nclChecks=nclChecks+1
 If actual<>expected And nclFailure=0 : nclFailure=nclChecks : EndIf
EndProcedure
Procedure.f NclWidth(font.i,text.i)
 Protected bytes.i=NeonUtf8Length(text,128),i.i,cp.i,prev.i,n.i,width.f
 If nclMode=1 : ProcedureReturn -1.0 : EndIf
 If nclMode=2 : ProcedureReturn MathFromBits($7FC00000) : EndIf
 If nclMode=4 : ProcedureReturn 16777218.0 : EndIf
 If nclMode=5
  nclBusyBind=NeonTextColumnBind(@NclWidth)
  nclBusyUnbind=NeonTextColumnUnbind()
 EndIf
 While i<bytes
  cp=NeonUtf8ScalarAt(text,bytes,i) : i=NeonUtf8Next(text,bytes,i) : n=n+1
  If cp=65 : width=width+9.0
  ElseIf cp=86 : width=width+7.0
  ElseIf cp=84 : width=width+8.0
  ElseIf cp=97 : width=width+6.0
  ElseIf cp=32 : width=width+3.0
  ElseIf cp>=32 And (cp<768 Or cp>879) : width=width+5.0
  EndIf
  If prev=65 And cp=86 : width=width-1.0 : EndIf
  prev=cp
 Wend
 If nclMode=3
  If n=1 : ProcedureReturn 10.0 : Else : ProcedureReturn 5.0 : EndIf
 EndIf
 ProcedureReturn width
EndProcedure
Procedure NclCase(index.i,source.i,budget.i,capacity.i,font.i,mode.i,column.i,x.f,fixedAdvance.f,metric.i,bound.i,alias.i,expected.i)
 Protected i.i,rc.i,result.i=@nclOut[1],p.i=#NCL_REPORT+8192+index*160
 For i=0 To 31 : PokeA(@nclOut[0]+i,165) : Next
 For i=0 To 143 : PokeA(@nclScratch[0]+i,60) : Next
 If bound<>0 : NeonTextColumnBind(@NclWidth) : Else : NeonTextColumnUnbind() : EndIf
 nclMode=metric
 If alias<>0 : result=@nclScratch[1] : EndIf
 If mode=0
  rc=NeonTextXForColumn(result,@nclScratch[1],capacity,source,budget,font,column,fixedAdvance)
 Else
  rc=NeonTextColumnForX(result,@nclScratch[1],capacity,source,budget,font,x,fixedAdvance)
 EndIf
 NclCheck(rc,expected)
 PokeI(p,rc)
 For i=0 To 31 : PokeA(p+8+i,PeekA(@nclOut[0]+i)) : Next
 PokeI(p+40,PeekI(@nclScratch[0])) : PokeI(p+48,PeekI(@nclScratch[17]))
 For i=0 To budget-1 : PokeA(p+64+i,PeekA(source+i)) : Next
EndProcedure
Procedure.i Main(services.i)
 Protected i.i,j.i,font.i,source.i,offset.i,rc.i,column.i,p.i=#NCL_REPORT+24576,x.f
 For i=0 To #NCL_REPORT_BYTES-1 : PokeA(#NCL_REPORT+i,0) : Next
 PokeI(#NCL_REPORT,$4E434C31) : PokeI(#NCL_REPORT+8,1)
 NclCheck(SizeOf(NeonTextColumnResult),16)
NclCase(0,?nclSource0,1,128,0,0,0,0.0,0.0,0,1,0,0)
NclCase(1,?nclSource1,1,128,0,0,1,0.0,0.0,0,1,0,0)
NclCase(2,?nclSource2,1,128,0,0,2,0.0,0.0,0,1,0,0)
NclCase(3,?nclSource3,1,128,0,0,20,0.0,0.0,0,1,0,0)
NclCase(4,?nclSource4,1,128,0,1,0,-1.0,0.0,0,1,0,0)
NclCase(5,?nclSource5,1,128,0,1,0,0.0,0.0,0,1,0,0)
NclCase(6,?nclSource6,1,128,0,1,0,2.5,0.0,0,1,0,0)
NclCase(7,?nclSource7,1,128,0,1,0,4.5,0.0,0,1,0,0)
NclCase(8,?nclSource8,1,128,0,1,0,9.0,0.0,0,1,0,0)
NclCase(9,?nclSource9,1,128,0,1,0,13.0,0.0,0,1,0,0)
NclCase(10,?nclSource10,1,128,0,1,0,100.0,0.0,0,1,0,0)
NclCase(11,?nclSource11,7,128,0,0,0,0.0,0.0,0,1,0,0)
NclCase(12,?nclSource12,7,128,0,0,1,0.0,0.0,0,1,0,0)
NclCase(13,?nclSource13,7,128,0,0,2,0.0,0.0,0,1,0,0)
NclCase(14,?nclSource14,7,128,0,0,20,0.0,0.0,0,1,0,0)
NclCase(15,?nclSource15,7,128,0,1,0,-1.0,0.0,0,1,0,0)
NclCase(16,?nclSource16,7,128,0,1,0,0.0,0.0,0,1,0,0)
NclCase(17,?nclSource17,7,128,0,1,0,2.5,0.0,0,1,0,0)
NclCase(18,?nclSource18,7,128,0,1,0,4.5,0.0,0,1,0,0)
NclCase(19,?nclSource19,7,128,0,1,0,9.0,0.0,0,1,0,0)
NclCase(20,?nclSource20,7,128,0,1,0,13.0,0.0,0,1,0,0)
NclCase(21,?nclSource21,7,128,0,1,0,100.0,0.0,0,1,0,0)
NclCase(22,?nclSource22,9,128,0,0,0,0.0,0.0,0,1,0,0)
NclCase(23,?nclSource23,9,128,0,0,1,0.0,0.0,0,1,0,0)
NclCase(24,?nclSource24,9,128,0,0,2,0.0,0.0,0,1,0,0)
NclCase(25,?nclSource25,9,128,0,0,20,0.0,0.0,0,1,0,0)
NclCase(26,?nclSource26,9,128,0,1,0,-1.0,0.0,0,1,0,0)
NclCase(27,?nclSource27,9,128,0,1,0,0.0,0.0,0,1,0,0)
NclCase(28,?nclSource28,9,128,0,1,0,2.5,0.0,0,1,0,0)
NclCase(29,?nclSource29,9,128,0,1,0,4.5,0.0,0,1,0,0)
NclCase(30,?nclSource30,9,128,0,1,0,9.0,0.0,0,1,0,0)
NclCase(31,?nclSource31,9,128,0,1,0,13.0,0.0,0,1,0,0)
NclCase(32,?nclSource32,9,128,0,1,0,100.0,0.0,0,1,0,0)
NclCase(33,?nclSource33,5,128,0,0,0,0.0,0.0,0,1,0,0)
NclCase(34,?nclSource34,5,128,0,0,1,0.0,0.0,0,1,0,0)
NclCase(35,?nclSource35,5,128,0,0,2,0.0,0.0,0,1,0,0)
NclCase(36,?nclSource36,5,128,0,0,20,0.0,0.0,0,1,0,0)
NclCase(37,?nclSource37,5,128,0,1,0,-1.0,0.0,0,1,0,0)
NclCase(38,?nclSource38,5,128,0,1,0,0.0,0.0,0,1,0,0)
NclCase(39,?nclSource39,5,128,0,1,0,2.5,0.0,0,1,0,0)
NclCase(40,?nclSource40,5,128,0,1,0,4.5,0.0,0,1,0,0)
NclCase(41,?nclSource41,5,128,0,1,0,9.0,0.0,0,1,0,0)
NclCase(42,?nclSource42,5,128,0,1,0,13.0,0.0,0,1,0,0)
NclCase(43,?nclSource43,5,128,0,1,0,100.0,0.0,0,1,0,0)
NclCase(44,?nclSource44,4,128,0,0,0,0.0,0.0,0,1,0,0)
NclCase(45,?nclSource45,4,128,0,0,1,0.0,0.0,0,1,0,0)
NclCase(46,?nclSource46,4,128,0,0,2,0.0,0.0,0,1,0,0)
NclCase(47,?nclSource47,4,128,0,0,20,0.0,0.0,0,1,0,0)
NclCase(48,?nclSource48,4,128,0,1,0,-1.0,0.0,0,1,0,0)
NclCase(49,?nclSource49,4,128,0,1,0,0.0,0.0,0,1,0,0)
NclCase(50,?nclSource50,4,128,0,1,0,2.5,0.0,0,1,0,0)
NclCase(51,?nclSource51,4,128,0,1,0,4.5,0.0,0,1,0,0)
NclCase(52,?nclSource52,4,128,0,1,0,9.0,0.0,0,1,0,0)
NclCase(53,?nclSource53,4,128,0,1,0,13.0,0.0,0,1,0,0)
NclCase(54,?nclSource54,4,128,0,1,0,100.0,0.0,0,1,0,0)
NclCase(55,?nclSource55,8,128,0,0,0,0.0,0.0,0,1,0,0)
NclCase(56,?nclSource56,8,128,0,0,1,0.0,0.0,0,1,0,0)
NclCase(57,?nclSource57,8,128,0,0,2,0.0,0.0,0,1,0,0)
NclCase(58,?nclSource58,8,128,0,0,20,0.0,0.0,0,1,0,0)
NclCase(59,?nclSource59,8,128,0,1,0,-1.0,0.0,0,1,0,0)
NclCase(60,?nclSource60,8,128,0,1,0,0.0,0.0,0,1,0,0)
NclCase(61,?nclSource61,8,128,0,1,0,2.5,0.0,0,1,0,0)
NclCase(62,?nclSource62,8,128,0,1,0,4.5,0.0,0,1,0,0)
NclCase(63,?nclSource63,8,128,0,1,0,9.0,0.0,0,1,0,0)
NclCase(64,?nclSource64,8,128,0,1,0,13.0,0.0,0,1,0,0)
NclCase(65,?nclSource65,8,128,0,1,0,100.0,0.0,0,1,0,0)
NclCase(66,?nclSource66,8,128,0,0,0,0.0,7.0,0,1,0,0)
NclCase(67,?nclSource67,8,128,0,0,1,0.0,7.0,0,1,0,0)
NclCase(68,?nclSource68,8,128,0,0,2,0.0,7.0,0,1,0,0)
NclCase(69,?nclSource69,8,128,0,0,8,0.0,7.0,0,1,0,0)
NclCase(70,?nclSource70,8,128,0,1,0,-1.0,7.0,0,1,0,0)
NclCase(71,?nclSource71,8,128,0,1,0,0.0,7.0,0,1,0,0)
NclCase(72,?nclSource72,8,128,0,1,0,3.49,7.0,0,1,0,0)
NclCase(73,?nclSource73,8,128,0,1,0,3.5,7.0,0,1,0,0)
NclCase(74,?nclSource74,8,128,0,1,0,10.5,7.0,0,1,0,0)
NclCase(75,?nclSource75,8,128,0,1,0,20.9,7.0,0,1,0,0)
NclCase(76,?nclSource76,8,128,0,1,0,100.0,7.0,0,1,0,0)
NclCase(77,?nclSource77,3,128,0,0,1,0.0,0.0,0,0,0,-23405)
NclCase(78,?nclSource78,3,128,-1,0,1,0.0,0.0,0,1,0,-23400)
NclCase(79,?nclSource79,3,2,0,0,1,0.0,0.0,0,1,0,-23402)
NclCase(80,?nclSource80,3,128,0,0,1,0.0,0.0,0,1,1,-23400)
NclCase(81,?nclSource81,3,128,0,0,-1,0.0,0.0,0,1,0,-23400)
NclCase(82,?nclSource82,3,128,0,0,0,0.0,0.0,0,1,0,-23401)
NclCase(83,?nclSource83,4,128,0,0,0,0.0,0.0,0,1,0,-23401)
NclCase(84,?nclSource84,4,128,0,0,0,0.0,0.0,0,1,0,-23401)
NclCase(85,?nclSource85,2,128,0,0,0,0.0,0.0,0,1,0,-23401)
NclCase(86,?nclSource86,3,128,0,0,2,0.0,0.0,1,1,0,-23403)
NclCase(87,?nclSource87,3,128,0,0,2,0.0,0.0,2,1,0,-23403)
NclCase(88,?nclSource88,3,128,0,0,2,0.0,0.0,3,1,0,-23403)
NclCase(89,?nclSource89,3,128,0,0,2,0.0,0.0,4,1,0,-23403)
NclCase(90,?nclSource90,4,128,0,0,2,0.0,0.0,5,1,0,0)

 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(0,@nclScratch[1],128,?nclNative,13,0,1,0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+0*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1]+1,@nclScratch[1],128,?nclNative,13,0,1,0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+1*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],0,128,?nclNative,13,0,1,0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+2*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclOut[0],32,?nclNative,13,0,1,0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+3*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],?nclNative,13,?nclNative,13,0,1,0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+4*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,0,13,0,1,0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+5*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,?nclNative,0,0,1,0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+6*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,?nclNative,4097,0,1,0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+7*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,?nclNative,13,0,1,-1.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+8*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,?nclNative,13,0,1,MathFromBits($7FC00000)),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+9*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextColumnForX(@nclOut[1],@nclScratch[1],128,?nclNative,13,0,MathFromBits($7F800000),0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+10*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextColumnForX(@nclOut[1],@nclScratch[1],128,?nclNative,13,0,MathFromBits($7FC00000),0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+11*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,?nclNative,13,0,65536,0.0),-23400)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+12*32+j,PeekA(@nclOut[0]+j)) : Next
 For j=0 To 31 : PokeA(@nclOut[0]+j,165) : Next
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,?nclNative,13,0,65535,8192.0),-23403)
 For j=0 To 31 : PokeA(#NCL_REPORT+23040+13*32+j,PeekA(@nclOut[0]+j)) : Next
 NclCheck(nclBusyBind,#NEON_COLUMN_ERR_BUSY) : NclCheck(nclBusyUnbind,#NEON_COLUMN_ERR_BUSY)
 NclCheck(NeonServiceBind(services,35),0) : NclCheck(NeonServiceOpen(),0)
 NclCheck(NeonServiceCanvas(640,400),0)
 font=NeonServiceFontRegister(0,1,14) : NclCheck(Bool(font>3),1)
 NclCheck(NeonServiceTextColumnInstall(),0)
 source=?nclNative
 NclCheck(NeonServicePrepare(font,source),0)
 PokeI(p,font)
 ; Reference prefixes built from literal UTF8 endpoints, not the column helper.

 For j=0 To -1 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+0,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[0]=x : PokeL(p+64+0*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,0,0.0),0)
 PokeI(p+256+0*16,PeekI(@nclOut[1])) : PokeI(p+264+0*16,PeekI(@nclOut[2]))

 For j=0 To 0 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+1,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[1]=x : PokeL(p+64+1*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,1,0.0),0)
 PokeI(p+256+1*16,PeekI(@nclOut[1])) : PokeI(p+264+1*16,PeekI(@nclOut[2]))

 For j=0 To 1 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+2,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[2]=x : PokeL(p+64+2*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,2,0.0),0)
 PokeI(p+256+2*16,PeekI(@nclOut[1])) : PokeI(p+264+2*16,PeekI(@nclOut[2]))

 For j=0 To 2 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+3,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[3]=x : PokeL(p+64+3*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,3,0.0),0)
 PokeI(p+256+3*16,PeekI(@nclOut[1])) : PokeI(p+264+3*16,PeekI(@nclOut[2]))

 For j=0 To 3 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+4,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[4]=x : PokeL(p+64+4*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,4,0.0),0)
 PokeI(p+256+4*16,PeekI(@nclOut[1])) : PokeI(p+264+4*16,PeekI(@nclOut[2]))

 For j=0 To 4 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+5,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[5]=x : PokeL(p+64+5*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,5,0.0),0)
 PokeI(p+256+5*16,PeekI(@nclOut[1])) : PokeI(p+264+5*16,PeekI(@nclOut[2]))

 For j=0 To 5 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+6,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[6]=x : PokeL(p+64+6*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,6,0.0),0)
 PokeI(p+256+6*16,PeekI(@nclOut[1])) : PokeI(p+264+6*16,PeekI(@nclOut[2]))

 For j=0 To 6 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+7,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[7]=x : PokeL(p+64+7*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,7,0.0),0)
 PokeI(p+256+7*16,PeekI(@nclOut[1])) : PokeI(p+264+7*16,PeekI(@nclOut[2]))

 For j=0 To 7 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+8,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[8]=x : PokeL(p+64+8*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,8,0.0),0)
 PokeI(p+256+8*16,PeekI(@nclOut[1])) : PokeI(p+264+8*16,PeekI(@nclOut[2]))

 For j=0 To 8 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+9,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[9]=x : PokeL(p+64+9*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,9,0.0),0)
 PokeI(p+256+9*16,PeekI(@nclOut[1])) : PokeI(p+264+9*16,PeekI(@nclOut[2]))

 For j=0 To 9 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+10,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[10]=x : PokeL(p+64+10*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,10,0.0),0)
 PokeI(p+256+10*16,PeekI(@nclOut[1])) : PokeI(p+264+10*16,PeekI(@nclOut[2]))

 For j=0 To 11 : PokeA(@nclReference[0]+j,PeekA(source+j)) : Next
 PokeA(@nclReference[0]+12,0)
 x=NeonServiceTextWidth(font,@nclReference[0])
 nclNativeX[11]=x : PokeL(p+64+11*4,MathBitsOf(x))
 NclCheck(NeonTextXForColumn(@nclOut[1],@nclScratch[1],128,source,13,font,11,0.0),0)
 PokeI(p+256+11*16,PeekI(@nclOut[1])) : PokeI(p+264+11*16,PeekI(@nclOut[2]))

 For i=1 To 11
  x=nclNativeX[i-1]+(nclNativeX[i]-nclNativeX[i-1])*0.5
  NclCheck(NeonTextColumnForX(@nclOut[1],@nclScratch[1],128,source,13,font,x,0.0),0)
  PokeL(p+512+i*24,MathBitsOf(x))
  PokeI(p+520+i*24,PeekI(@nclOut[1])) : PokeI(p+528+i*24,PeekI(@nclOut[2]))
 Next
 NclCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
 NclCheck(NeonServiceText(font,20.0,80.0,source,1.0,1.0,1.0,1.0),0)
 NclCheck(NeonServiceText(font,340.0,80.0,source,1.0,1.0,1.0,1.0),0)

 x=MathFromBits(PeekL(p+264+1*16))
 NclCheck(NeonServiceBox(20.0+x,100.0,1.0,12.0,0.2,0.8,0.9,1.0),0)
 NclCheck(NeonServiceBox(340.0+nclNativeX[1],100.0,1.0,12.0,0.2,0.8,0.9,1.0),0)

 x=MathFromBits(PeekL(p+264+2*16))
 NclCheck(NeonServiceBox(20.0+x,100.0,1.0,12.0,0.2,0.8,0.9,1.0),0)
 NclCheck(NeonServiceBox(340.0+nclNativeX[2],100.0,1.0,12.0,0.2,0.8,0.9,1.0),0)

 x=MathFromBits(PeekL(p+264+5*16))
 NclCheck(NeonServiceBox(20.0+x,100.0,1.0,12.0,0.2,0.8,0.9,1.0),0)
 NclCheck(NeonServiceBox(340.0+nclNativeX[5],100.0,1.0,12.0,0.2,0.8,0.9,1.0),0)

 x=MathFromBits(PeekL(p+264+11*16))
 NclCheck(NeonServiceBox(20.0+x,100.0,1.0,12.0,0.2,0.8,0.9,1.0),0)
 NclCheck(NeonServiceBox(340.0+nclNativeX[11],100.0,1.0,12.0,0.2,0.8,0.9,1.0),0)

 NclCheck(NeonServiceEnd(),0) : NclCheck(NeonTextColumnUnbind(),0)
 PokeI(#NCL_REPORT+16,nclFailure) : PokeI(#NCL_REPORT+24,nclChecks)
 ProcedureReturn nclFailure
EndProcedure
DataSection
nclSource0:
 Data.a 0
nclSource1:
 Data.a 0
nclSource2:
 Data.a 0
nclSource3:
 Data.a 0
nclSource4:
 Data.a 0
nclSource5:
 Data.a 0
nclSource6:
 Data.a 0
nclSource7:
 Data.a 0
nclSource8:
 Data.a 0
nclSource9:
 Data.a 0
nclSource10:
 Data.a 0
nclSource11:
 Data.a 65,86,65,84,65,82,0
nclSource12:
 Data.a 65,86,65,84,65,82,0
nclSource13:
 Data.a 65,86,65,84,65,82,0
nclSource14:
 Data.a 65,86,65,84,65,82,0
nclSource15:
 Data.a 65,86,65,84,65,82,0
nclSource16:
 Data.a 65,86,65,84,65,82,0
nclSource17:
 Data.a 65,86,65,84,65,82,0
nclSource18:
 Data.a 65,86,65,84,65,82,0
nclSource19:
 Data.a 65,86,65,84,65,82,0
nclSource20:
 Data.a 65,86,65,84,65,82,0
nclSource21:
 Data.a 65,86,65,84,65,82,0
nclSource22:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource23:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource24:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource25:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource26:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource27:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource28:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource29:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource30:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource31:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource32:
 Data.a 65,195,169,240,159,152,128,90,0
nclSource33:
 Data.a 101,204,129,120,0
nclSource34:
 Data.a 101,204,129,120,0
nclSource35:
 Data.a 101,204,129,120,0
nclSource36:
 Data.a 101,204,129,120,0
nclSource37:
 Data.a 101,204,129,120,0
nclSource38:
 Data.a 101,204,129,120,0
nclSource39:
 Data.a 101,204,129,120,0
nclSource40:
 Data.a 101,204,129,120,0
nclSource41:
 Data.a 101,204,129,120,0
nclSource42:
 Data.a 101,204,129,120,0
nclSource43:
 Data.a 101,204,129,120,0
nclSource44:
 Data.a 65,9,86,0
nclSource45:
 Data.a 65,9,86,0
nclSource46:
 Data.a 65,9,86,0
nclSource47:
 Data.a 65,9,86,0
nclSource48:
 Data.a 65,9,86,0
nclSource49:
 Data.a 65,9,86,0
nclSource50:
 Data.a 65,9,86,0
nclSource51:
 Data.a 65,9,86,0
nclSource52:
 Data.a 65,9,86,0
nclSource53:
 Data.a 65,9,86,0
nclSource54:
 Data.a 65,9,86,0
nclSource55:
 Data.a 233,155,182,240,159,152,128,0
nclSource56:
 Data.a 233,155,182,240,159,152,128,0
nclSource57:
 Data.a 233,155,182,240,159,152,128,0
nclSource58:
 Data.a 233,155,182,240,159,152,128,0
nclSource59:
 Data.a 233,155,182,240,159,152,128,0
nclSource60:
 Data.a 233,155,182,240,159,152,128,0
nclSource61:
 Data.a 233,155,182,240,159,152,128,0
nclSource62:
 Data.a 233,155,182,240,159,152,128,0
nclSource63:
 Data.a 233,155,182,240,159,152,128,0
nclSource64:
 Data.a 233,155,182,240,159,152,128,0
nclSource65:
 Data.a 233,155,182,240,159,152,128,0
nclSource66:
 Data.a 65,240,159,152,128,195,169,0
nclSource67:
 Data.a 65,240,159,152,128,195,169,0
nclSource68:
 Data.a 65,240,159,152,128,195,169,0
nclSource69:
 Data.a 65,240,159,152,128,195,169,0
nclSource70:
 Data.a 65,240,159,152,128,195,169,0
nclSource71:
 Data.a 65,240,159,152,128,195,169,0
nclSource72:
 Data.a 65,240,159,152,128,195,169,0
nclSource73:
 Data.a 65,240,159,152,128,195,169,0
nclSource74:
 Data.a 65,240,159,152,128,195,169,0
nclSource75:
 Data.a 65,240,159,152,128,195,169,0
nclSource76:
 Data.a 65,240,159,152,128,195,169,0
nclSource77:
 Data.a 97,98,0
nclSource78:
 Data.a 97,98,0
nclSource79:
 Data.a 97,98,0
nclSource80:
 Data.a 97,98,0
nclSource81:
 Data.a 97,98,0
nclSource82:
 Data.a 192,128,0
nclSource83:
 Data.a 237,160,128,0
nclSource84:
 Data.a 97,240,159,0
nclSource85:
 Data.a 97,98
nclSource86:
 Data.a 97,98,0
nclSource87:
 Data.a 97,98,0
nclSource88:
 Data.a 97,98,0
nclSource89:
 Data.a 97,98,0
nclSource90:
 Data.a 97,98,99,0
nclNative:
 Data.a 65,86,65,84,65,82,32,99,97,102,195,169,0
EndDataSection
