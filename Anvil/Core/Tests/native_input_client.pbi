; SPDX-License-Identifier: MIT
; Actual portable client, controlled provider. No physical device claim.
XIncludeFile "Anvil/Hal/input_service_client.pbi"
XIncludeFile "Anvil/Core/input_hid_keys.pbi"
Global ncChecks.i,ncFailure.i,ncClose.i,ncPoll.i,ncCaps.i=7,ncWidth.i=800,ncHeight.i=1280,ncGen.i=10
Global ncWire.NativeInputEvent,ncOutput.NativeInputEvent
Global Dim ncTable.q[42]
Procedure NcCheck(actual.i,expected.i)
  ncChecks=ncChecks+1
  PokeI(#NIP_REPORT+112+ncChecks*16,actual)
  PokeI(#NIP_REPORT+120+ncChecks*16,expected)
  If actual<>expected And ncFailure=0 : ncFailure=ncChecks : EndIf
  PokeI(#NIP_REPORT+16,ncChecks) : PokeI(#NIP_REPORT+24,ncFailure)
EndProcedure
Procedure.i NcProvider(op.i,context.i,request.i,bytes.i)
  Protected *api.NativeInputApi,*open.NativeInputOpenRequest,i.i
  Select op
    Case #NUI_QUERY
      *api=request : *api\magic=#NUI_MAGIC : *api\major=1 : *api\minor=0
      *api\bytes=32 : *api\flags=7 : *api\dispatch=@NcProvider
      ProcedureReturn 0
    Case #NUI_OPEN
      *open=request : *open\capabilities=ncCaps : *open\width=ncWidth
      *open\height=ncHeight : *open\generation=ncGen
      ProcedureReturn 73
    Case #NUI_POLL
      For i=0 To 40 Step 8 : PokeI(request+i,PeekI(@ncWire+i)) : Next
      ProcedureReturn ncPoll
    Case #NUI_FLUSH
      ProcedureReturn 0
    Case #NUI_CLOSE
      ProcedureReturn ncClose
  EndSelect
  ProcedureReturn -22400
EndProcedure
Procedure.i Main(services.i)
  Protected i.i
  For i=0 To 8191 Step 8 : PokeI(#NIP_REPORT+i,0) : Next
  PokeI(#NIP_REPORT,$4E494331) : PokeI(#NIP_REPORT+8,1)
  NcCheck(AnvilInputOpen(),-22406)
  NcCheck(AnvilInputPoll(@ncOutput),-22401)
  NcCheck(AnvilInputClose(),0)
  NcCheck(AnvilInputBind(0,0),-22400)
  NcCheck(AnvilInputBind(@ncTable[0]+1,0),-22400)
  NcCheck(AnvilInputBind($7FFFFFFFFFFFFFE0,0),-22400)
  PokeL(@ncTable[0],$53564E41) : PokeL(@ncTable[0]+4,1)
  PokeL(@ncTable[0]+8,8) : PokeL(@ncTable[0]+12,200)
  PokeI(@ncTable[0]+16+39*8,@NcProvider)
  NcCheck(AnvilInputBind(@ncTable[0],0),-22403)
  PokeL(@ncTable[0]+8,9) : PokeL(@ncTable[0]+12,39)
  NcCheck(AnvilInputBind(@ncTable[0],0),-22403)
  PokeL(@ncTable[0]+12,200)
  NcCheck(AnvilInputBind(@ncTable[0],8),-22400)
  NcCheck(AnvilInputBind(@ncTable[0],7),0)
  PokeL(@ncTable[0],0)
  NcCheck(AnvilInputBind(@ncTable[0],0),-22403)
  NcCheck(AnvilInputOpen(),0)
  NcCheck(AnvilInputContext(),73)
  NcCheck(AnvilInputCapabilities(),7)
  NcCheck(AnvilInputWidth(),800)
  NcCheck(AnvilInputHeight(),1280)
  NcCheck(AnvilInputGeneration(),10)
  NcCheck(AnvilInputOpen(),-22402)
  NcCheck(AnvilInputBind(@ncTable[0],0),-22402)
  NcCheck(AnvilInputPoll(0),-22400)
  NcCheck(AnvilInputPoll(@ncOutput+1),-22400)
  ncOutput\code=12345 : ncPoll=0
  NcCheck(AnvilInputPoll(@ncOutput),0)
  NcCheck(ncOutput\code,12345)
  ncPoll=2
  NcCheck(AnvilInputPoll(@ncOutput),-22404)
  NcCheck(ncOutput\code,12345)
  ncPoll=1 : ncWire\kind=1 : ncWire\source=1 : ncWire\code=65
  ncWire\x=-1 : ncWire\y=-1 : ncWire\ticks=1 : ncWire\generation=9
  NcCheck(AnvilInputPoll(@ncOutput),-22404)
  NcCheck(ncOutput\code,12345)
  ncWire\generation=10 : ncWire\reserved=1
  NcCheck(AnvilInputPoll(@ncOutput),-22404)
  ncWire\reserved=0
  NcCheck(AnvilInputPoll(@ncOutput),1)
  NcCheck(ncOutput\code,65)
  ncWire\kind=4 : ncWire\code=7 : ncWire\generation=11
  NcCheck(AnvilInputPoll(@ncOutput),1)
  NcCheck(AnvilInputGeneration(),11)
  ncWire\kind=1 : ncWire\code=66 : ncWire\generation=10
  NcCheck(AnvilInputPoll(@ncOutput),-22404)
  NcCheck(ncOutput\code,7)
  NcCheck(AnvilInputFlush(),0)
  NcCheck(AnvilInputGeneration(),11)
  ncClose=-22404
  NcCheck(AnvilInputClose(),-22404)
  NcCheck(AnvilInputContext(),73)
  ncClose=0
  NcCheck(AnvilInputClose(),0)
  NcCheck(AnvilInputContext(),0)
  NcCheck(AnvilInputCapabilities(),0)
  ncCaps=2 : ncWidth=0 : ncHeight=0
  NcCheck(AnvilInputOpen(),-22404)
  NcCheck(AnvilInputContext(),73)
  NcCheck(AnvilInputClose(),0)
  ncCaps=7 : ncWidth=800 : ncHeight=1280 : ncGen=2147483648
  NcCheck(AnvilInputOpen(),-22404)
  NcCheck(AnvilInputClose(),0)
  ncGen=10 : ncWidth=8193
  NcCheck(AnvilInputOpen(),-22404)
  NcCheck(AnvilInputClose(),0)
  NcCheck(InputHidNamedKey(40,0),1)
  NcCheck(InputHidNamedKey(41,0),9)
  NcCheck(InputHidNamedKey(42,0),2)
  NcCheck(InputHidNamedKey(43,0),8)
  NcCheck(InputHidNamedKey(73,0),15)
  NcCheck(InputHidNamedKey(74,0),6)
  NcCheck(InputHidNamedKey(75,0),13)
  NcCheck(InputHidNamedKey(76,0),3)
  NcCheck(InputHidNamedKey(77,0),7)
  NcCheck(InputHidNamedKey(78,0),14)
  NcCheck(InputHidNamedKey(79,0),5)
  NcCheck(InputHidNamedKey(80,0),4)
  NcCheck(InputHidNamedKey(81,0),12)
  NcCheck(InputHidNamedKey(82,0),11)
  NcCheck(InputHidNamedKey(88,0),1)
  NcCheck(InputHidNamedKey(89,0),7)
  NcCheck(InputHidNamedKey(90,0),12)
  NcCheck(InputHidNamedKey(91,0),14)
  NcCheck(InputHidNamedKey(92,0),4)
  NcCheck(InputHidNamedKey(94,0),5)
  NcCheck(InputHidNamedKey(95,0),6)
  NcCheck(InputHidNamedKey(96,0),11)
  NcCheck(InputHidNamedKey(97,0),13)
  NcCheck(InputHidNamedKey(98,0),15)
  NcCheck(InputHidNamedKey(99,0),3)
  NcCheck(InputHidNamedKey(89,1),0)
  NcCheck(InputHidNamedKey(90,1),0)
  NcCheck(InputHidNamedKey(91,1),0)
  NcCheck(InputHidNamedKey(92,1),0)
  NcCheck(InputHidNamedKey(93,1),0)
  NcCheck(InputHidNamedKey(94,1),0)
  NcCheck(InputHidNamedKey(95,1),0)
  NcCheck(InputHidNamedKey(96,1),0)
  NcCheck(InputHidNamedKey(97,1),0)
  NcCheck(InputHidNamedKey(98,1),0)
  NcCheck(InputHidNamedKey(99,1),0)
  NcCheck(InputHidNamedKey(-1,0),-1)
  NcCheck(InputHidNamedKey(256,0),-1)
  NcCheck(InputHidNamedKey(4,2),-1)
  NcCheck(InputHidNamedKey(4,0),0)
  ProcedureReturn ncFailure
EndProcedure
