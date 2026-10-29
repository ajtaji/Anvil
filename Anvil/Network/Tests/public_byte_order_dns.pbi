; SPDX-License-Identifier: MIT
; Standalone DNS and byte-order qualification; no packet driver or network stack.
XIncludeFile "Anvil/Network/dns_codec.pbi"
Global nbcChecks.i,nbcFailure.i
Global Dim nbcBytes.a[32]
Global Dim nbcReply.a[64]
Procedure NbcCheck(actual.i,expected.i)
  nbcChecks=nbcChecks+1
  PokeI(#NBC_REPORT+112+nbcChecks*16,actual)
  PokeI(#NBC_REPORT+120+nbcChecks*16,expected)
  If actual<>expected And nbcFailure=0 : nbcFailure=nbcChecks : EndIf
  PokeI(#NBC_REPORT+16,nbcChecks) : PokeI(#NBC_REPORT+24,nbcFailure)
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,start.i,finish.i
  For i=0 To 8191 Step 8 : PokeI(#NBC_REPORT+i,0) : Next
  PokeI(#NBC_REPORT,$4E424331) : PokeI(#NBC_REPORT+8,1)
  CompilerIf #NBC_CLOCK=1
  PokeI(#NBC_REPORT+64,AnvilSchedulerCounterHz())
  start=AnvilSchedulerCounterValue() : PokeI(#NBC_REPORT+72,start)
  CompilerEndIf
  For i=0 To 31 : nbcBytes[i]=165 : Next
  NetWriteBE16(@nbcBytes[1],$80FF)
  NbcCheck(NetReadBE16(@nbcBytes[1]),33023)
  NbcCheck(nbcBytes[0],165)
  NbcCheck(nbcBytes[1],128)
  NbcCheck(nbcBytes[2],255)
  NbcCheck(nbcBytes[3],165)
  NetWriteBE32(@nbcBytes[3],$FEDCBA98)
  NbcCheck(NetReadBE32(@nbcBytes[3]),4275878552)
  NbcCheck(nbcBytes[2],255)
  NbcCheck(nbcBytes[3],254)
  NbcCheck(nbcBytes[4],220)
  NbcCheck(nbcBytes[5],186)
  NbcCheck(nbcBytes[6],152)
  NbcCheck(nbcBytes[7],165)
  NetWriteBE16(@nbcBytes[9],-1) : NetWriteBE32(@nbcBytes[11],-1)
  NbcCheck(NetReadBE16(@nbcBytes[9]),65535)
  NbcCheck(NetReadBE32(@nbcBytes[11]),4294967295)
  NetWriteBE16(@nbcBytes[17],$123456) : NetWriteBE32(@nbcBytes[19],$123456789A)
  NbcCheck(NetReadBE16(@nbcBytes[17]),13398)
  NbcCheck(NetReadBE32(@nbcBytes[19]),878082202)
  NbcCheck(nbcBytes[16],165)
  NbcCheck(nbcBytes[23],165)
  NbcCheck(DnsBuildQuery("example.com",$1234),29)
  NbcCheck(DnsQueryLen(),29)
  NbcCheck(DnsError(),0)
  NbcCheck(PeekA(DnsQueryBuf()+0),18)
  NbcCheck(PeekA(DnsQueryBuf()+1),52)
  NbcCheck(PeekA(DnsQueryBuf()+2),1)
  NbcCheck(PeekA(DnsQueryBuf()+3),0)
  NbcCheck(PeekA(DnsQueryBuf()+4),0)
  NbcCheck(PeekA(DnsQueryBuf()+5),1)
  NbcCheck(PeekA(DnsQueryBuf()+6),0)
  NbcCheck(PeekA(DnsQueryBuf()+7),0)
  NbcCheck(PeekA(DnsQueryBuf()+8),0)
  NbcCheck(PeekA(DnsQueryBuf()+9),0)
  NbcCheck(PeekA(DnsQueryBuf()+10),0)
  NbcCheck(PeekA(DnsQueryBuf()+11),0)
  NbcCheck(PeekA(DnsQueryBuf()+12),7)
  NbcCheck(PeekA(DnsQueryBuf()+13),101)
  NbcCheck(PeekA(DnsQueryBuf()+14),120)
  NbcCheck(PeekA(DnsQueryBuf()+15),97)
  NbcCheck(PeekA(DnsQueryBuf()+16),109)
  NbcCheck(PeekA(DnsQueryBuf()+17),112)
  NbcCheck(PeekA(DnsQueryBuf()+18),108)
  NbcCheck(PeekA(DnsQueryBuf()+19),101)
  NbcCheck(PeekA(DnsQueryBuf()+20),3)
  NbcCheck(PeekA(DnsQueryBuf()+21),99)
  NbcCheck(PeekA(DnsQueryBuf()+22),111)
  NbcCheck(PeekA(DnsQueryBuf()+23),109)
  NbcCheck(PeekA(DnsQueryBuf()+24),0)
  NbcCheck(PeekA(DnsQueryBuf()+25),0)
  NbcCheck(PeekA(DnsQueryBuf()+26),1)
  NbcCheck(PeekA(DnsQueryBuf()+27),0)
  NbcCheck(PeekA(DnsQueryBuf()+28),1)
  NbcCheck(DnsBuildQuery("example.com.",$1234),29)
  NbcCheck(PeekA(DnsQueryBuf()+0),18)
  NbcCheck(PeekA(DnsQueryBuf()+1),52)
  NbcCheck(PeekA(DnsQueryBuf()+2),1)
  NbcCheck(PeekA(DnsQueryBuf()+3),0)
  NbcCheck(PeekA(DnsQueryBuf()+4),0)
  NbcCheck(PeekA(DnsQueryBuf()+5),1)
  NbcCheck(PeekA(DnsQueryBuf()+6),0)
  NbcCheck(PeekA(DnsQueryBuf()+7),0)
  NbcCheck(PeekA(DnsQueryBuf()+8),0)
  NbcCheck(PeekA(DnsQueryBuf()+9),0)
  NbcCheck(PeekA(DnsQueryBuf()+10),0)
  NbcCheck(PeekA(DnsQueryBuf()+11),0)
  NbcCheck(PeekA(DnsQueryBuf()+12),7)
  NbcCheck(PeekA(DnsQueryBuf()+13),101)
  NbcCheck(PeekA(DnsQueryBuf()+14),120)
  NbcCheck(PeekA(DnsQueryBuf()+15),97)
  NbcCheck(PeekA(DnsQueryBuf()+16),109)
  NbcCheck(PeekA(DnsQueryBuf()+17),112)
  NbcCheck(PeekA(DnsQueryBuf()+18),108)
  NbcCheck(PeekA(DnsQueryBuf()+19),101)
  NbcCheck(PeekA(DnsQueryBuf()+20),3)
  NbcCheck(PeekA(DnsQueryBuf()+21),99)
  NbcCheck(PeekA(DnsQueryBuf()+22),111)
  NbcCheck(PeekA(DnsQueryBuf()+23),109)
  NbcCheck(PeekA(DnsQueryBuf()+24),0)
  NbcCheck(PeekA(DnsQueryBuf()+25),0)
  NbcCheck(PeekA(DnsQueryBuf()+26),1)
  NbcCheck(PeekA(DnsQueryBuf()+27),0)
  NbcCheck(PeekA(DnsQueryBuf()+28),1)
  NbcCheck(DnsBuildQuery("x.",$1234),19)
  NbcCheck(NetReadBE16(DnsQueryBuf()+15),1)
  NbcCheck(NetReadBE16(DnsQueryBuf()+17),1)
  NbcCheck(DnsBuildQuery("bad..name",$1234),0)
  NbcCheck(DnsError(),-202)
  NbcCheck(DnsBuildQuery("",$1234),0)
  NbcCheck(DnsError(),-200)
  For i=0 To 44 : nbcReply[i]=PeekA(?nbcReplyData+i) : Next
  NbcCheck(DnsParseReply(@nbcReply[0],45,$1234),1)
  NbcCheck(DnsResultCount(),1)
  NbcCheck(DnsResultIp(0),3221225985)
  NbcCheck(DnsResultIp(1),0)
  NbcCheck(DnsError(),0)
  NbcCheck(DnsParseReply(@nbcReply[0],45,$4321),-204)
  NbcCheck(DnsResultCount(),0)
  nbcReply[2]=1
  NbcCheck(DnsParseReply(@nbcReply[0],45,$1234),-205)
  nbcReply[2]=129 : nbcReply[3]=131
  NbcCheck(DnsParseReply(@nbcReply[0],45,$1234),-206)
  NbcCheck(DnsRcode(),3)
  NbcCheck(DnsParseReply(@nbcReply[0],11,$1234),-203)
  nbcReply[3]=128
  NbcCheck(DnsParseReply(@nbcReply[0],44,$1234),-207)
  For i=0 To 31 : PokeA(#NBC_REPORT+2048+i,nbcBytes[i]) : Next

  CompilerIf #NBC_CLOCK=1
  finish=AnvilSchedulerCounterValue() : PokeI(#NBC_REPORT+80,finish)
  If AnvilSchedulerCounterHz()<>54000000 Or start<=0 Or finish<=start : ProcedureReturn 1000 : EndIf
  CompilerEndIf
  ProcedureReturn nbcFailure
EndProcedure
DataSection
nbcReplyData:
  Data.a 18,52,129,128,0,1,0,1,0,0,0,0,7,101,120,97,109,112,108,101,3,99,111,109,0,0,1,0,1,192,12,0,1,0,1,0,0,1,44,0,4,192,0,2,1
EndDataSection
