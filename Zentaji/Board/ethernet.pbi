; Zentaji slot $0F Ethernet queue. Core zero owns the rings and private
; buffers. TX retires at its doorbell and RX publishes its head after writing
; the descriptor. All addresses below are guest physical addresses.
#ZEN_ETH_BASE=$FFFF0000000F0000
#ZEN_ETH_ID=$10010
#ZEN_ETH_TX=2
#ZEN_ETH_RX=8
#ZEN_ETH_FRAME=1514
#ZEN_ETH_SLOT=1536

Global Dim zeTxSpace.a[#ZEN_ETH_TX*16+15]
Global Dim zeRxSpace.a[#ZEN_ETH_RX*16+15]
Global Dim zeTxBytes.a[#ZEN_ETH_FRAME]
Global Dim zeRxBytes.a[#ZEN_ETH_RX*#ZEN_ETH_SLOT]
Global Dim zeMac.a[6]
Global zeOpen.i,zeRam.i,zeTx.i,zeRx.i,zeTxTail.i,zeRxNext.i,zeRxTail.i
Global zeRxRejects.i

Procedure.i ZentajiEthernetPresent()
 ProcedureReturn Bool((PeekQ(#ZEN_ETH_BASE)&$FFFFFF)=#ZEN_ETH_ID)
EndProcedure

Procedure.i ZentajiEthernetCarrier()
 If ZentajiEthernetPresent()=0 : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool((PeekQ(#ZEN_ETH_BASE+$90)&1)<>0)
EndProcedure

Procedure.i zeContext()
 ProcedureReturn Bool(ZenCpuCoreId()=0 And ZenCpuStatus()=0)
EndProcedure

Procedure.i ZentajiEthernetOwned()
 If zeOpen=0 Or zeContext()=0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_ETH_BASE+$10)<>1 Or PeekQ(#ZEN_ETH_BASE+$20)<>0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_ETH_BASE+$50)<>zeTx Or PeekQ(#ZEN_ETH_BASE+$58)<>#ZEN_ETH_TX : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_ETH_BASE+$70)<>zeRx Or PeekQ(#ZEN_ETH_BASE+$78)<>#ZEN_ETH_RX : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_ETH_BASE+$60)<>zeTxTail Or PeekQ(#ZEN_ETH_BASE+$68)<>zeTxTail : ProcedureReturn 0 : EndIf
 ProcedureReturn Bool(PeekQ(#ZEN_ETH_BASE+$80)=zeRxTail And PeekQ(#ZEN_ETH_BASE+$88)<#ZEN_ETH_RX)
EndProcedure

Procedure zePost(index.i)
 Protected desc.i=zeRx+16*index
 PokeQ(desc,@zeRxBytes[0]+index*#ZEN_ETH_SLOT)
 PokeQ(desc+8,#ZEN_ETH_FRAME)
EndProcedure

Procedure.i ZentajiEthernetOpen()
 Protected i.i,mac.q
 If zeOpen<>0 : ProcedureReturn ZentajiEthernetOwned() : EndIf
 If zeContext()=0 Or ZentajiEthernetCarrier()=0 Or PeekQ(#ZEN_ETH_BASE+$48)<>1500 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_ETH_BASE+$10)<>0 Or PeekQ(#ZEN_ETH_BASE+$20)<>0 Or PeekQ(#ZEN_ETH_BASE+8)<>0 : ProcedureReturn 0 : EndIf
 If PeekQ(#ZEN_ETH_BASE+$50)<>0 Or PeekQ(#ZEN_ETH_BASE+$58)<>0 Or PeekQ(#ZEN_ETH_BASE+$70)<>0 Or PeekQ(#ZEN_ETH_BASE+$78)<>0 : ProcedureReturn 0 : EndIf
 zeRam=PeekQ($FFFF000000010018)
 zeTx=(@zeTxSpace[0]+15)&-16 : zeRx=(@zeRxSpace[0]+15)&-16
 If zeTx<1 Or zeTx>zeRam-#ZEN_ETH_TX*16 Or zeRx<1 Or zeRx>zeRam-#ZEN_ETH_RX*16 : ProcedureReturn 0 : EndIf
 If @zeTxBytes[0]<1 Or @zeTxBytes[0]>zeRam-#ZEN_ETH_FRAME Or @zeRxBytes[0]<1 Or @zeRxBytes[0]>zeRam-#ZEN_ETH_RX*#ZEN_ETH_SLOT : ProcedureReturn 0 : EndIf
 mac=PeekQ(#ZEN_ETH_BASE+$40)&$FFFFFFFFFFFF
 If mac=0 Or (mac&1)<>0 : ProcedureReturn 0 : EndIf
 For i=0 To 5 : zeMac[i]=(mac>>(8*i))&255 : Next
 For i=0 To #ZEN_ETH_TX*16-8 Step 8 : PokeQ(zeTx+i,0) : Next
 For i=0 To #ZEN_ETH_RX-1 : zePost(i) : Next
 zeTxTail=0 : zeRxNext=0 : zeRxTail=#ZEN_ETH_RX-1
 PokeQ(#ZEN_ETH_BASE+$50,zeTx) : PokeQ(#ZEN_ETH_BASE+$58,#ZEN_ETH_TX)
 PokeQ(#ZEN_ETH_BASE+$70,zeRx) : PokeQ(#ZEN_ETH_BASE+$78,#ZEN_ETH_RX)
 PokeQ(#ZEN_ETH_BASE+$10,1)
 If PeekQ(#ZEN_ETH_BASE+$10)<>1
  PokeQ(#ZEN_ETH_BASE+8,$FF00) : PokeQ(#ZEN_ETH_BASE+$18,8)
  PokeQ(#ZEN_ETH_BASE+$50,0) : PokeQ(#ZEN_ETH_BASE+$58,0)
  PokeQ(#ZEN_ETH_BASE+$70,0) : PokeQ(#ZEN_ETH_BASE+$78,0)
  ProcedureReturn 0
 EndIf
 zeOpen=1
 PokeQ(#ZEN_ETH_BASE+$80,zeRxTail)
 ProcedureReturn ZentajiEthernetOwned()
EndProcedure

Procedure.i ZentajiEthernetClose()
 If ZentajiEthernetOwned()=0 : ProcedureReturn 0 : EndIf
 PokeQ(#ZEN_ETH_BASE+$10,0)
 If PeekQ(#ZEN_ETH_BASE+$10)<>0 : ProcedureReturn 0 : EndIf
 PokeQ(#ZEN_ETH_BASE+$18,3)
 PokeQ(#ZEN_ETH_BASE+$50,0) : PokeQ(#ZEN_ETH_BASE+$58,0)
 PokeQ(#ZEN_ETH_BASE+$70,0) : PokeQ(#ZEN_ETH_BASE+$78,0)
 zeOpen=0
 ProcedureReturn 1
EndProcedure

Procedure.i ZentajiEthernetSend(source.i,length.i)
 Protected desc.i,i.i
 If length<14 Or length>#ZEN_ETH_FRAME Or source<1 Or source>zeRam-length : ProcedureReturn 0 : EndIf
 If ZentajiEthernetOwned()=0 : ProcedureReturn 0 : EndIf
 For i=0 To length-1 : zeTxBytes[i]=PeekA(source+i) : Next
 desc=zeTx+16*zeTxTail
 PokeQ(desc,@zeTxBytes[0]) : PokeQ(desc+8,length)
 zeTxTail=(zeTxTail+1)&(#ZEN_ETH_TX-1)
 PokeQ(#ZEN_ETH_BASE+$60,zeTxTail)
 If PeekQ(#ZEN_ETH_BASE+$68)<>zeTxTail : ProcedureReturn 0 : EndIf
 PokeQ(#ZEN_ETH_BASE+$18,1)
 ProcedureReturn Bool(PeekU(desc+12)=1 And PeekU(desc+14)=0)
EndProcedure

; Consume a completed RX descriptor and post the old sentinel only after
; copying its predecessor. The caller can keep the result independently of
; the NIC. A zero time budget polls once.
Procedure.i ZentajiEthernetReceive(destination.i,capacity.i,waitMs.i)
 Protected desc.i,source.i,i.i,length.i,start.q,now.q
 If capacity<14 Or capacity>zeRam Or destination<1 Or destination>zeRam-capacity Or waitMs<0 : ProcedureReturn 0 : EndIf
 If ZentajiEthernetOwned()=0 : ProcedureReturn 0 : EndIf
 If waitMs>1000 : waitMs=1000 : EndIf
 start=HwMicros()
 While PeekQ(#ZEN_ETH_BASE+$88)=zeRxNext
  If waitMs=0 Or HwPromptIdleReady()=0 : ProcedureReturn 0 : EndIf
  now=HwMicros()
  If now<start Or now-start>=waitMs*1000 : ProcedureReturn 0 : EndIf
  HwPromptIdleWait()
  If ZentajiEthernetOwned()=0 : ProcedureReturn 0 : EndIf
 Wend
 desc=zeRx+zeRxNext*16
 If PeekU(desc+12)<>1 : ProcedureReturn 0 : EndIf
 length=PeekU(desc+10)
 If PeekU(desc+14)<>0 Or length<14 Or length>#ZEN_ETH_FRAME Or length>capacity
  zeRxRejects=zeRxRejects+1 : length=0
 Else
  source=@zeRxBytes[0]+zeRxNext*#ZEN_ETH_SLOT
  For i=0 To length-1 : PokeA(destination+i,PeekA(source+i)) : Next
 EndIf
 zePost(zeRxTail)
 zeRxNext=(zeRxNext+1)&(#ZEN_ETH_RX-1)
 zeRxTail=(zeRxTail+1)&(#ZEN_ETH_RX-1)
 PokeQ(#ZEN_ETH_BASE+$80,zeRxTail)
 PokeQ(#ZEN_ETH_BASE+$18,2)
 ProcedureReturn length
EndProcedure
