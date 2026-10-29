; Pi4 shader-record/VPM diagnostic. The reference submits explicit triangle
; quads; production LinesBegin/End now uses compact records and is not that
; reference path. The host rational pixel oracle remains independent.
Procedure compactReferenceLineAt(p.i,x0.i,y0.i,x1.i,y1.i)
  Protected dx.i=x1-x0,dy.i=y1-y0,cx.i,cy.i,ex.i,ey.i
  If dx<0 : dx=0-dx : EndIf
  If dy<0 : dy=0-dy : EndIf
  If dx=0 And dy=0
    x1=x0+1 : y1=y0 : cx=x0+1 : cy=y0+1 : ex=x0 : ey=y0+1
  ElseIf dx>=dy
    cx=x1 : cy=y1+1 : ex=x0 : ey=y0+1
  Else
    cx=x1+1 : cy=y1 : ex=x0+1 : ey=y0
  EndIf
  NeonVkChromeTriAt(p,x0,y0,x1,y1,cx,cy)
  NeonVkChromeTriAt(p+72,x0,y0,cx,cy,ex,ey)
EndProcedure
Global Dim compactVs.l[512]
Global compactExtra.i=2
Procedure.i compactBuildVs()
 If compactExtra=2
  PokeL(@compactVs[0]+0,$07230203)
  PokeL(@compactVs[0]+4,$00010000)
  PokeL(@compactVs[0]+8,$00000000)
  PokeL(@compactVs[0]+12,$00000064)
  PokeL(@compactVs[0]+16,$00000000)
  PokeL(@compactVs[0]+20,$00020011)
  PokeL(@compactVs[0]+24,$00000001)
  PokeL(@compactVs[0]+28,$0003000E)
  PokeL(@compactVs[0]+32,$00000000)
  PokeL(@compactVs[0]+36,$00000001)
  PokeL(@compactVs[0]+40,$0009000F)
  PokeL(@compactVs[0]+44,$00000000)
  PokeL(@compactVs[0]+48,$0000001E)
  PokeL(@compactVs[0]+52,$6E69616D)
  PokeL(@compactVs[0]+56,$00000000)
  PokeL(@compactVs[0]+60,$00000014)
  PokeL(@compactVs[0]+64,$00000015)
  PokeL(@compactVs[0]+68,$00000016)
  PokeL(@compactVs[0]+72,$00000017)
  PokeL(@compactVs[0]+76,$00050048)
  PokeL(@compactVs[0]+80,$00000008)
  PokeL(@compactVs[0]+84,$00000000)
  PokeL(@compactVs[0]+88,$0000000B)
  PokeL(@compactVs[0]+92,$00000000)
  PokeL(@compactVs[0]+96,$00030047)
  PokeL(@compactVs[0]+100,$00000008)
  PokeL(@compactVs[0]+104,$00000002)
  PokeL(@compactVs[0]+108,$00040047)
  PokeL(@compactVs[0]+112,$00000014)
  PokeL(@compactVs[0]+116,$0000001E)
  PokeL(@compactVs[0]+120,$00000000)
  PokeL(@compactVs[0]+124,$00040047)
  PokeL(@compactVs[0]+128,$00000015)
  PokeL(@compactVs[0]+132,$0000001E)
  PokeL(@compactVs[0]+136,$00000001)
  PokeL(@compactVs[0]+140,$00040047)
  PokeL(@compactVs[0]+144,$00000016)
  PokeL(@compactVs[0]+148,$0000001E)
  PokeL(@compactVs[0]+152,$00000002)
  PokeL(@compactVs[0]+156,$00020013)
  PokeL(@compactVs[0]+160,$00000001)
  PokeL(@compactVs[0]+164,$00030021)
  PokeL(@compactVs[0]+168,$00000002)
  PokeL(@compactVs[0]+172,$00000001)
  PokeL(@compactVs[0]+176,$00030016)
  PokeL(@compactVs[0]+180,$00000003)
  PokeL(@compactVs[0]+184,$00000020)
  PokeL(@compactVs[0]+188,$00040017)
  PokeL(@compactVs[0]+192,$00000004)
  PokeL(@compactVs[0]+196,$00000003)
  PokeL(@compactVs[0]+200,$00000004)
  PokeL(@compactVs[0]+204,$00040020)
  PokeL(@compactVs[0]+208,$00000005)
  PokeL(@compactVs[0]+212,$00000001)
  PokeL(@compactVs[0]+216,$00000004)
  PokeL(@compactVs[0]+220,$0003001E)
  PokeL(@compactVs[0]+224,$00000008)
  PokeL(@compactVs[0]+228,$00000004)
  PokeL(@compactVs[0]+232,$00040020)
  PokeL(@compactVs[0]+236,$00000009)
  PokeL(@compactVs[0]+240,$00000003)
  PokeL(@compactVs[0]+244,$00000008)
  PokeL(@compactVs[0]+248,$00040020)
  PokeL(@compactVs[0]+252,$0000000A)
  PokeL(@compactVs[0]+256,$00000003)
  PokeL(@compactVs[0]+260,$00000004)
  PokeL(@compactVs[0]+264,$00040015)
  PokeL(@compactVs[0]+268,$0000000B)
  PokeL(@compactVs[0]+272,$00000020)
  PokeL(@compactVs[0]+276,$00000001)
  PokeL(@compactVs[0]+280,$0004002B)
  PokeL(@compactVs[0]+284,$0000000B)
  PokeL(@compactVs[0]+288,$0000000C)
  PokeL(@compactVs[0]+292,$00000000)
  PokeL(@compactVs[0]+296,$0004002B)
  PokeL(@compactVs[0]+300,$00000003)
  PokeL(@compactVs[0]+304,$0000000D)
  PokeL(@compactVs[0]+308,$00000000)
  PokeL(@compactVs[0]+312,$0004002B)
  PokeL(@compactVs[0]+316,$00000003)
  PokeL(@compactVs[0]+320,$0000000E)
  PokeL(@compactVs[0]+324,$3F800000)
  PokeL(@compactVs[0]+328,$0004003B)
  PokeL(@compactVs[0]+332,$00000005)
  PokeL(@compactVs[0]+336,$00000014)
  PokeL(@compactVs[0]+340,$00000001)
  PokeL(@compactVs[0]+344,$0004003B)
  PokeL(@compactVs[0]+348,$00000005)
  PokeL(@compactVs[0]+352,$00000015)
  PokeL(@compactVs[0]+356,$00000001)
  PokeL(@compactVs[0]+360,$0004003B)
  PokeL(@compactVs[0]+364,$00000005)
  PokeL(@compactVs[0]+368,$00000016)
  PokeL(@compactVs[0]+372,$00000001)
  PokeL(@compactVs[0]+376,$0004003B)
  PokeL(@compactVs[0]+380,$00000009)
  PokeL(@compactVs[0]+384,$00000017)
  PokeL(@compactVs[0]+388,$00000003)
  PokeL(@compactVs[0]+392,$00050036)
  PokeL(@compactVs[0]+396,$00000001)
  PokeL(@compactVs[0]+400,$0000001E)
  PokeL(@compactVs[0]+404,$00000000)
  PokeL(@compactVs[0]+408,$00000002)
  PokeL(@compactVs[0]+412,$000200F8)
  PokeL(@compactVs[0]+416,$0000001F)
  PokeL(@compactVs[0]+420,$0004003D)
  PokeL(@compactVs[0]+424,$00000004)
  PokeL(@compactVs[0]+428,$00000020)
  PokeL(@compactVs[0]+432,$00000014)
  PokeL(@compactVs[0]+436,$0004003D)
  PokeL(@compactVs[0]+440,$00000004)
  PokeL(@compactVs[0]+444,$00000021)
  PokeL(@compactVs[0]+448,$00000015)
  PokeL(@compactVs[0]+452,$0004003D)
  PokeL(@compactVs[0]+456,$00000004)
  PokeL(@compactVs[0]+460,$00000022)
  PokeL(@compactVs[0]+464,$00000016)
  PokeL(@compactVs[0]+468,$00050051)
  PokeL(@compactVs[0]+472,$00000003)
  PokeL(@compactVs[0]+476,$00000028)
  PokeL(@compactVs[0]+480,$00000020)
  PokeL(@compactVs[0]+484,$00000000)
  PokeL(@compactVs[0]+488,$00050051)
  PokeL(@compactVs[0]+492,$00000003)
  PokeL(@compactVs[0]+496,$00000029)
  PokeL(@compactVs[0]+500,$00000020)
  PokeL(@compactVs[0]+504,$00000001)
  PokeL(@compactVs[0]+508,$00050051)
  PokeL(@compactVs[0]+512,$00000003)
  PokeL(@compactVs[0]+516,$0000002A)
  PokeL(@compactVs[0]+520,$00000020)
  PokeL(@compactVs[0]+524,$00000002)
  PokeL(@compactVs[0]+528,$00050051)
  PokeL(@compactVs[0]+532,$00000003)
  PokeL(@compactVs[0]+536,$0000002B)
  PokeL(@compactVs[0]+540,$00000020)
  PokeL(@compactVs[0]+544,$00000003)
  PokeL(@compactVs[0]+548,$00050051)
  PokeL(@compactVs[0]+552,$00000003)
  PokeL(@compactVs[0]+556,$0000002C)
  PokeL(@compactVs[0]+560,$00000021)
  PokeL(@compactVs[0]+564,$00000000)
  PokeL(@compactVs[0]+568,$00050051)
  PokeL(@compactVs[0]+572,$00000003)
  PokeL(@compactVs[0]+576,$0000002D)
  PokeL(@compactVs[0]+580,$00000021)
  PokeL(@compactVs[0]+584,$00000001)
  PokeL(@compactVs[0]+588,$00050051)
  PokeL(@compactVs[0]+592,$00000003)
  PokeL(@compactVs[0]+596,$0000002E)
  PokeL(@compactVs[0]+600,$00000021)
  PokeL(@compactVs[0]+604,$00000002)
  PokeL(@compactVs[0]+608,$00050051)
  PokeL(@compactVs[0]+612,$00000003)
  PokeL(@compactVs[0]+616,$0000002F)
  PokeL(@compactVs[0]+620,$00000021)
  PokeL(@compactVs[0]+624,$00000003)
  PokeL(@compactVs[0]+628,$00050051)
  PokeL(@compactVs[0]+632,$00000003)
  PokeL(@compactVs[0]+636,$00000030)
  PokeL(@compactVs[0]+640,$00000022)
  PokeL(@compactVs[0]+644,$00000000)
  PokeL(@compactVs[0]+648,$00050051)
  PokeL(@compactVs[0]+652,$00000003)
  PokeL(@compactVs[0]+656,$00000031)
  PokeL(@compactVs[0]+660,$00000022)
  PokeL(@compactVs[0]+664,$00000001)
  PokeL(@compactVs[0]+668,$00050051)
  PokeL(@compactVs[0]+672,$00000003)
  PokeL(@compactVs[0]+676,$00000032)
  PokeL(@compactVs[0]+680,$00000022)
  PokeL(@compactVs[0]+684,$00000002)
  PokeL(@compactVs[0]+688,$00050051)
  PokeL(@compactVs[0]+692,$00000003)
  PokeL(@compactVs[0]+696,$00000033)
  PokeL(@compactVs[0]+700,$00000022)
  PokeL(@compactVs[0]+704,$00000003)
  PokeL(@compactVs[0]+708,$00050085)
  PokeL(@compactVs[0]+712,$00000003)
  PokeL(@compactVs[0]+716,$0000003C)
  PokeL(@compactVs[0]+720,$00000028)
  PokeL(@compactVs[0]+724,$0000002C)
  PokeL(@compactVs[0]+728,$00050085)
  PokeL(@compactVs[0]+732,$00000003)
  PokeL(@compactVs[0]+736,$0000003D)
  PokeL(@compactVs[0]+740,$00000029)
  PokeL(@compactVs[0]+744,$0000002D)
  PokeL(@compactVs[0]+748,$00050085)
  PokeL(@compactVs[0]+752,$00000003)
  PokeL(@compactVs[0]+756,$0000003E)
  PokeL(@compactVs[0]+760,$0000002A)
  PokeL(@compactVs[0]+764,$0000002E)
  PokeL(@compactVs[0]+768,$00050085)
  PokeL(@compactVs[0]+772,$00000003)
  PokeL(@compactVs[0]+776,$0000003F)
  PokeL(@compactVs[0]+780,$0000002B)
  PokeL(@compactVs[0]+784,$0000002F)
  PokeL(@compactVs[0]+788,$00050081)
  PokeL(@compactVs[0]+792,$00000003)
  PokeL(@compactVs[0]+796,$00000046)
  PokeL(@compactVs[0]+800,$0000003C)
  PokeL(@compactVs[0]+804,$0000003D)
  PokeL(@compactVs[0]+808,$00050081)
  PokeL(@compactVs[0]+812,$00000003)
  PokeL(@compactVs[0]+816,$00000047)
  PokeL(@compactVs[0]+820,$0000003E)
  PokeL(@compactVs[0]+824,$0000003F)
  PokeL(@compactVs[0]+828,$00050081)
  PokeL(@compactVs[0]+832,$00000003)
  PokeL(@compactVs[0]+836,$00000048)
  PokeL(@compactVs[0]+840,$00000046)
  PokeL(@compactVs[0]+844,$00000047)
  PokeL(@compactVs[0]+848,$00050085)
  PokeL(@compactVs[0]+852,$00000003)
  PokeL(@compactVs[0]+856,$00000040)
  PokeL(@compactVs[0]+860,$00000028)
  PokeL(@compactVs[0]+864,$00000030)
  PokeL(@compactVs[0]+868,$00050085)
  PokeL(@compactVs[0]+872,$00000003)
  PokeL(@compactVs[0]+876,$00000041)
  PokeL(@compactVs[0]+880,$00000029)
  PokeL(@compactVs[0]+884,$00000031)
  PokeL(@compactVs[0]+888,$00050085)
  PokeL(@compactVs[0]+892,$00000003)
  PokeL(@compactVs[0]+896,$00000042)
  PokeL(@compactVs[0]+900,$0000002A)
  PokeL(@compactVs[0]+904,$00000032)
  PokeL(@compactVs[0]+908,$00050085)
  PokeL(@compactVs[0]+912,$00000003)
  PokeL(@compactVs[0]+916,$00000043)
  PokeL(@compactVs[0]+920,$0000002B)
  PokeL(@compactVs[0]+924,$00000033)
  PokeL(@compactVs[0]+928,$00050081)
  PokeL(@compactVs[0]+932,$00000003)
  PokeL(@compactVs[0]+936,$00000049)
  PokeL(@compactVs[0]+940,$00000040)
  PokeL(@compactVs[0]+944,$00000041)
  PokeL(@compactVs[0]+948,$00050081)
  PokeL(@compactVs[0]+952,$00000003)
  PokeL(@compactVs[0]+956,$0000004A)
  PokeL(@compactVs[0]+960,$00000042)
  PokeL(@compactVs[0]+964,$00000043)
  PokeL(@compactVs[0]+968,$00050081)
  PokeL(@compactVs[0]+972,$00000003)
  PokeL(@compactVs[0]+976,$0000004B)
  PokeL(@compactVs[0]+980,$00000049)
  PokeL(@compactVs[0]+984,$0000004A)
  PokeL(@compactVs[0]+988,$00050081)
  PokeL(@compactVs[0]+992,$00000003)
  PokeL(@compactVs[0]+996,$0000005A)
  PokeL(@compactVs[0]+1000,$00000048)
  PokeL(@compactVs[0]+1004,$0000000D)
  PokeL(@compactVs[0]+1008,$00050081)
  PokeL(@compactVs[0]+1012,$00000003)
  PokeL(@compactVs[0]+1016,$0000005B)
  PokeL(@compactVs[0]+1020,$0000005A)
  PokeL(@compactVs[0]+1024,$0000000D)
  PokeL(@compactVs[0]+1028,$00070050)
  PokeL(@compactVs[0]+1032,$00000004)
  PokeL(@compactVs[0]+1036,$00000050)
  PokeL(@compactVs[0]+1040,$0000005B)
  PokeL(@compactVs[0]+1044,$0000004B)
  PokeL(@compactVs[0]+1048,$0000000D)
  PokeL(@compactVs[0]+1052,$0000000E)
  PokeL(@compactVs[0]+1056,$00050041)
  PokeL(@compactVs[0]+1060,$0000000A)
  PokeL(@compactVs[0]+1064,$00000051)
  PokeL(@compactVs[0]+1068,$00000017)
  PokeL(@compactVs[0]+1072,$0000000C)
  PokeL(@compactVs[0]+1076,$0003003E)
  PokeL(@compactVs[0]+1080,$00000051)
  PokeL(@compactVs[0]+1084,$00000050)
  PokeL(@compactVs[0]+1088,$000100FD)
  PokeL(@compactVs[0]+1092,$00010038)
  ProcedureReturn 1096
 EndIf
 If compactExtra=3
  PokeL(@compactVs[0]+0,$07230203)
  PokeL(@compactVs[0]+4,$00010000)
  PokeL(@compactVs[0]+8,$00000000)
  PokeL(@compactVs[0]+12,$00000064)
  PokeL(@compactVs[0]+16,$00000000)
  PokeL(@compactVs[0]+20,$00020011)
  PokeL(@compactVs[0]+24,$00000001)
  PokeL(@compactVs[0]+28,$0003000E)
  PokeL(@compactVs[0]+32,$00000000)
  PokeL(@compactVs[0]+36,$00000001)
  PokeL(@compactVs[0]+40,$0009000F)
  PokeL(@compactVs[0]+44,$00000000)
  PokeL(@compactVs[0]+48,$0000001E)
  PokeL(@compactVs[0]+52,$6E69616D)
  PokeL(@compactVs[0]+56,$00000000)
  PokeL(@compactVs[0]+60,$00000014)
  PokeL(@compactVs[0]+64,$00000015)
  PokeL(@compactVs[0]+68,$00000016)
  PokeL(@compactVs[0]+72,$00000017)
  PokeL(@compactVs[0]+76,$00050048)
  PokeL(@compactVs[0]+80,$00000008)
  PokeL(@compactVs[0]+84,$00000000)
  PokeL(@compactVs[0]+88,$0000000B)
  PokeL(@compactVs[0]+92,$00000000)
  PokeL(@compactVs[0]+96,$00030047)
  PokeL(@compactVs[0]+100,$00000008)
  PokeL(@compactVs[0]+104,$00000002)
  PokeL(@compactVs[0]+108,$00040047)
  PokeL(@compactVs[0]+112,$00000014)
  PokeL(@compactVs[0]+116,$0000001E)
  PokeL(@compactVs[0]+120,$00000000)
  PokeL(@compactVs[0]+124,$00040047)
  PokeL(@compactVs[0]+128,$00000015)
  PokeL(@compactVs[0]+132,$0000001E)
  PokeL(@compactVs[0]+136,$00000001)
  PokeL(@compactVs[0]+140,$00040047)
  PokeL(@compactVs[0]+144,$00000016)
  PokeL(@compactVs[0]+148,$0000001E)
  PokeL(@compactVs[0]+152,$00000002)
  PokeL(@compactVs[0]+156,$00020013)
  PokeL(@compactVs[0]+160,$00000001)
  PokeL(@compactVs[0]+164,$00030021)
  PokeL(@compactVs[0]+168,$00000002)
  PokeL(@compactVs[0]+172,$00000001)
  PokeL(@compactVs[0]+176,$00030016)
  PokeL(@compactVs[0]+180,$00000003)
  PokeL(@compactVs[0]+184,$00000020)
  PokeL(@compactVs[0]+188,$00040017)
  PokeL(@compactVs[0]+192,$00000004)
  PokeL(@compactVs[0]+196,$00000003)
  PokeL(@compactVs[0]+200,$00000004)
  PokeL(@compactVs[0]+204,$00040020)
  PokeL(@compactVs[0]+208,$00000005)
  PokeL(@compactVs[0]+212,$00000001)
  PokeL(@compactVs[0]+216,$00000004)
  PokeL(@compactVs[0]+220,$0003001E)
  PokeL(@compactVs[0]+224,$00000008)
  PokeL(@compactVs[0]+228,$00000004)
  PokeL(@compactVs[0]+232,$00040020)
  PokeL(@compactVs[0]+236,$00000009)
  PokeL(@compactVs[0]+240,$00000003)
  PokeL(@compactVs[0]+244,$00000008)
  PokeL(@compactVs[0]+248,$00040020)
  PokeL(@compactVs[0]+252,$0000000A)
  PokeL(@compactVs[0]+256,$00000003)
  PokeL(@compactVs[0]+260,$00000004)
  PokeL(@compactVs[0]+264,$00040015)
  PokeL(@compactVs[0]+268,$0000000B)
  PokeL(@compactVs[0]+272,$00000020)
  PokeL(@compactVs[0]+276,$00000001)
  PokeL(@compactVs[0]+280,$0004002B)
  PokeL(@compactVs[0]+284,$0000000B)
  PokeL(@compactVs[0]+288,$0000000C)
  PokeL(@compactVs[0]+292,$00000000)
  PokeL(@compactVs[0]+296,$0004002B)
  PokeL(@compactVs[0]+300,$00000003)
  PokeL(@compactVs[0]+304,$0000000D)
  PokeL(@compactVs[0]+308,$00000000)
  PokeL(@compactVs[0]+312,$0004002B)
  PokeL(@compactVs[0]+316,$00000003)
  PokeL(@compactVs[0]+320,$0000000E)
  PokeL(@compactVs[0]+324,$3F800000)
  PokeL(@compactVs[0]+328,$0004003B)
  PokeL(@compactVs[0]+332,$00000005)
  PokeL(@compactVs[0]+336,$00000014)
  PokeL(@compactVs[0]+340,$00000001)
  PokeL(@compactVs[0]+344,$0004003B)
  PokeL(@compactVs[0]+348,$00000005)
  PokeL(@compactVs[0]+352,$00000015)
  PokeL(@compactVs[0]+356,$00000001)
  PokeL(@compactVs[0]+360,$0004003B)
  PokeL(@compactVs[0]+364,$00000005)
  PokeL(@compactVs[0]+368,$00000016)
  PokeL(@compactVs[0]+372,$00000001)
  PokeL(@compactVs[0]+376,$0004003B)
  PokeL(@compactVs[0]+380,$00000009)
  PokeL(@compactVs[0]+384,$00000017)
  PokeL(@compactVs[0]+388,$00000003)
  PokeL(@compactVs[0]+392,$00050036)
  PokeL(@compactVs[0]+396,$00000001)
  PokeL(@compactVs[0]+400,$0000001E)
  PokeL(@compactVs[0]+404,$00000000)
  PokeL(@compactVs[0]+408,$00000002)
  PokeL(@compactVs[0]+412,$000200F8)
  PokeL(@compactVs[0]+416,$0000001F)
  PokeL(@compactVs[0]+420,$0004003D)
  PokeL(@compactVs[0]+424,$00000004)
  PokeL(@compactVs[0]+428,$00000020)
  PokeL(@compactVs[0]+432,$00000014)
  PokeL(@compactVs[0]+436,$0004003D)
  PokeL(@compactVs[0]+440,$00000004)
  PokeL(@compactVs[0]+444,$00000021)
  PokeL(@compactVs[0]+448,$00000015)
  PokeL(@compactVs[0]+452,$0004003D)
  PokeL(@compactVs[0]+456,$00000004)
  PokeL(@compactVs[0]+460,$00000022)
  PokeL(@compactVs[0]+464,$00000016)
  PokeL(@compactVs[0]+468,$00050051)
  PokeL(@compactVs[0]+472,$00000003)
  PokeL(@compactVs[0]+476,$00000028)
  PokeL(@compactVs[0]+480,$00000020)
  PokeL(@compactVs[0]+484,$00000000)
  PokeL(@compactVs[0]+488,$00050051)
  PokeL(@compactVs[0]+492,$00000003)
  PokeL(@compactVs[0]+496,$00000029)
  PokeL(@compactVs[0]+500,$00000020)
  PokeL(@compactVs[0]+504,$00000001)
  PokeL(@compactVs[0]+508,$00050051)
  PokeL(@compactVs[0]+512,$00000003)
  PokeL(@compactVs[0]+516,$0000002A)
  PokeL(@compactVs[0]+520,$00000020)
  PokeL(@compactVs[0]+524,$00000002)
  PokeL(@compactVs[0]+528,$00050051)
  PokeL(@compactVs[0]+532,$00000003)
  PokeL(@compactVs[0]+536,$0000002B)
  PokeL(@compactVs[0]+540,$00000020)
  PokeL(@compactVs[0]+544,$00000003)
  PokeL(@compactVs[0]+548,$00050051)
  PokeL(@compactVs[0]+552,$00000003)
  PokeL(@compactVs[0]+556,$0000002C)
  PokeL(@compactVs[0]+560,$00000021)
  PokeL(@compactVs[0]+564,$00000000)
  PokeL(@compactVs[0]+568,$00050051)
  PokeL(@compactVs[0]+572,$00000003)
  PokeL(@compactVs[0]+576,$0000002D)
  PokeL(@compactVs[0]+580,$00000021)
  PokeL(@compactVs[0]+584,$00000001)
  PokeL(@compactVs[0]+588,$00050051)
  PokeL(@compactVs[0]+592,$00000003)
  PokeL(@compactVs[0]+596,$0000002E)
  PokeL(@compactVs[0]+600,$00000021)
  PokeL(@compactVs[0]+604,$00000002)
  PokeL(@compactVs[0]+608,$00050051)
  PokeL(@compactVs[0]+612,$00000003)
  PokeL(@compactVs[0]+616,$0000002F)
  PokeL(@compactVs[0]+620,$00000021)
  PokeL(@compactVs[0]+624,$00000003)
  PokeL(@compactVs[0]+628,$00050051)
  PokeL(@compactVs[0]+632,$00000003)
  PokeL(@compactVs[0]+636,$00000030)
  PokeL(@compactVs[0]+640,$00000022)
  PokeL(@compactVs[0]+644,$00000000)
  PokeL(@compactVs[0]+648,$00050051)
  PokeL(@compactVs[0]+652,$00000003)
  PokeL(@compactVs[0]+656,$00000031)
  PokeL(@compactVs[0]+660,$00000022)
  PokeL(@compactVs[0]+664,$00000001)
  PokeL(@compactVs[0]+668,$00050051)
  PokeL(@compactVs[0]+672,$00000003)
  PokeL(@compactVs[0]+676,$00000032)
  PokeL(@compactVs[0]+680,$00000022)
  PokeL(@compactVs[0]+684,$00000002)
  PokeL(@compactVs[0]+688,$00050051)
  PokeL(@compactVs[0]+692,$00000003)
  PokeL(@compactVs[0]+696,$00000033)
  PokeL(@compactVs[0]+700,$00000022)
  PokeL(@compactVs[0]+704,$00000003)
  PokeL(@compactVs[0]+708,$00050085)
  PokeL(@compactVs[0]+712,$00000003)
  PokeL(@compactVs[0]+716,$0000003C)
  PokeL(@compactVs[0]+720,$00000028)
  PokeL(@compactVs[0]+724,$0000002C)
  PokeL(@compactVs[0]+728,$00050085)
  PokeL(@compactVs[0]+732,$00000003)
  PokeL(@compactVs[0]+736,$0000003D)
  PokeL(@compactVs[0]+740,$00000029)
  PokeL(@compactVs[0]+744,$0000002D)
  PokeL(@compactVs[0]+748,$00050085)
  PokeL(@compactVs[0]+752,$00000003)
  PokeL(@compactVs[0]+756,$0000003E)
  PokeL(@compactVs[0]+760,$0000002A)
  PokeL(@compactVs[0]+764,$0000002E)
  PokeL(@compactVs[0]+768,$00050085)
  PokeL(@compactVs[0]+772,$00000003)
  PokeL(@compactVs[0]+776,$0000003F)
  PokeL(@compactVs[0]+780,$0000002B)
  PokeL(@compactVs[0]+784,$0000002F)
  PokeL(@compactVs[0]+788,$00050081)
  PokeL(@compactVs[0]+792,$00000003)
  PokeL(@compactVs[0]+796,$00000046)
  PokeL(@compactVs[0]+800,$0000003C)
  PokeL(@compactVs[0]+804,$0000003D)
  PokeL(@compactVs[0]+808,$00050081)
  PokeL(@compactVs[0]+812,$00000003)
  PokeL(@compactVs[0]+816,$00000047)
  PokeL(@compactVs[0]+820,$0000003E)
  PokeL(@compactVs[0]+824,$0000003F)
  PokeL(@compactVs[0]+828,$00050081)
  PokeL(@compactVs[0]+832,$00000003)
  PokeL(@compactVs[0]+836,$00000048)
  PokeL(@compactVs[0]+840,$00000046)
  PokeL(@compactVs[0]+844,$00000047)
  PokeL(@compactVs[0]+848,$00050085)
  PokeL(@compactVs[0]+852,$00000003)
  PokeL(@compactVs[0]+856,$00000040)
  PokeL(@compactVs[0]+860,$00000028)
  PokeL(@compactVs[0]+864,$00000030)
  PokeL(@compactVs[0]+868,$00050085)
  PokeL(@compactVs[0]+872,$00000003)
  PokeL(@compactVs[0]+876,$00000041)
  PokeL(@compactVs[0]+880,$00000029)
  PokeL(@compactVs[0]+884,$00000031)
  PokeL(@compactVs[0]+888,$00050085)
  PokeL(@compactVs[0]+892,$00000003)
  PokeL(@compactVs[0]+896,$00000042)
  PokeL(@compactVs[0]+900,$0000002A)
  PokeL(@compactVs[0]+904,$00000032)
  PokeL(@compactVs[0]+908,$00050085)
  PokeL(@compactVs[0]+912,$00000003)
  PokeL(@compactVs[0]+916,$00000043)
  PokeL(@compactVs[0]+920,$0000002B)
  PokeL(@compactVs[0]+924,$00000033)
  PokeL(@compactVs[0]+928,$00050081)
  PokeL(@compactVs[0]+932,$00000003)
  PokeL(@compactVs[0]+936,$00000049)
  PokeL(@compactVs[0]+940,$00000040)
  PokeL(@compactVs[0]+944,$00000041)
  PokeL(@compactVs[0]+948,$00050081)
  PokeL(@compactVs[0]+952,$00000003)
  PokeL(@compactVs[0]+956,$0000004A)
  PokeL(@compactVs[0]+960,$00000042)
  PokeL(@compactVs[0]+964,$00000043)
  PokeL(@compactVs[0]+968,$00050081)
  PokeL(@compactVs[0]+972,$00000003)
  PokeL(@compactVs[0]+976,$0000004B)
  PokeL(@compactVs[0]+980,$00000049)
  PokeL(@compactVs[0]+984,$0000004A)
  PokeL(@compactVs[0]+988,$00050081)
  PokeL(@compactVs[0]+992,$00000003)
  PokeL(@compactVs[0]+996,$0000005A)
  PokeL(@compactVs[0]+1000,$00000048)
  PokeL(@compactVs[0]+1004,$0000000D)
  PokeL(@compactVs[0]+1008,$00050081)
  PokeL(@compactVs[0]+1012,$00000003)
  PokeL(@compactVs[0]+1016,$0000005B)
  PokeL(@compactVs[0]+1020,$0000005A)
  PokeL(@compactVs[0]+1024,$0000000D)
  PokeL(@compactVs[0]+1028,$00050081)
  PokeL(@compactVs[0]+1032,$00000003)
  PokeL(@compactVs[0]+1036,$0000005C)
  PokeL(@compactVs[0]+1040,$0000005B)
  PokeL(@compactVs[0]+1044,$0000000D)
  PokeL(@compactVs[0]+1048,$00070050)
  PokeL(@compactVs[0]+1052,$00000004)
  PokeL(@compactVs[0]+1056,$00000050)
  PokeL(@compactVs[0]+1060,$0000005C)
  PokeL(@compactVs[0]+1064,$0000004B)
  PokeL(@compactVs[0]+1068,$0000000D)
  PokeL(@compactVs[0]+1072,$0000000E)
  PokeL(@compactVs[0]+1076,$00050041)
  PokeL(@compactVs[0]+1080,$0000000A)
  PokeL(@compactVs[0]+1084,$00000051)
  PokeL(@compactVs[0]+1088,$00000017)
  PokeL(@compactVs[0]+1092,$0000000C)
  PokeL(@compactVs[0]+1096,$0003003E)
  PokeL(@compactVs[0]+1100,$00000051)
  PokeL(@compactVs[0]+1104,$00000050)
  PokeL(@compactVs[0]+1108,$000100FD)
  PokeL(@compactVs[0]+1112,$00010038)
  ProcedureReturn 1116
 EndIf
 ProcedureReturn 0
EndProcedure
Global compactLayout.i
Global compactPipeline.i,compactSelector.i,compactSelectorMem.i
Procedure.i compactCreate()
 Define pcr.VkPushConstantRange
 Define plci.VkPipelineLayoutCreateInfo
 Define badVs.i,badPipe.i,badRc.i
 Define k.i
  Define smci.VkShaderModuleCreateInfo
  Define Dim stages.VkPipelineShaderStageCreateInfo[2]
  Define Dim cbinding.VkVertexInputBindingDescription[2]
  Define Dim attrs.VkVertexInputAttributeDescription[3]
  Define vi.VkPipelineVertexInputStateCreateInfo
  Define ia.VkPipelineInputAssemblyStateCreateInfo
  Define vp.VkViewport
  Define vpstate.VkPipelineViewportStateCreateInfo
  Define rs.VkPipelineRasterizationStateCreateInfo
  Define ms.VkPipelineMultisampleStateCreateInfo
  Define cba.VkPipelineColorBlendAttachmentState
  Define cb.VkPipelineColorBlendStateCreateInfo
  Define dyn.VkPipelineDynamicStateCreateInfo
  ; VkDynamicState is a Vulkan enum (32 bits); native-width .i entries make
  ; the API's 4-byte walk read the high half of VIEWPORT twice.
  Dim dynStates.l[2]
  Define gp.VkGraphicsPipelineCreateInfo
  Define vs.i
  Define fs.i
  Define layoutArray.i
  Define mapped.i
  Define rc.i
  Define vsBytes.i
  Define fsBytes.i

  rc=nvcBufferCreate(64,#VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,@compactSelector,@compactSelectorMem)
  If rc<>0 : ProcedureReturn rc : EndIf
  rc=vkMapMemory(nvcDevice,compactSelectorMem,0,64,0,@mapped)
  If rc<>0 : ProcedureReturn rc : EndIf
  For k=0 To 15 : PokeL(mapped+k*4,0) : Next
  ; Strip order c1,c0,c2,c3 preserves the same two triangle regions.
  PokeL(mapped+4,$3F800000) : PokeL(mapped+16,$3F800000)
  PokeL(mapped+32+8,$3F800000) : PokeL(mapped+48+12,$3F800000)
  vkUnmapMemory(nvcDevice,compactSelectorMem)
  pcr\stageFlags=#VK_SHADER_STAGE_FRAGMENT_BIT : pcr\size=16
  plci\sType=#VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO
  plci\pushConstantRangeCount=1 : plci\pPushConstantRanges=@pcr
  rc=vkCreatePipelineLayout(nvcDevice,@plci,0,@compactLayout)
  If rc<>0 : ProcedureReturn rc : EndIf
  vsBytes = compactBuildVs()
  fsBytes = vtpBuildFsA()
  smci\sType = #VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO
  smci\pCode = @compactVs[0] : smci\codeSize = vsBytes
  rc = vkCreateShaderModule(nvcDevice, @smci, 0, @vs)
  If rc = #VK_SUCCESS
    smci\pCode = @vtpFsA[0] : smci\codeSize = fsBytes
    rc = vkCreateShaderModule(nvcDevice, @smci, 0, @fs)
  EndIf
  If rc <> #VK_SUCCESS
    If vs <> 0 : vkDestroyShaderModule(nvcDevice, vs, 0) : EndIf
    If fs <> 0 : vkDestroyShaderModule(nvcDevice, fs, 0) : EndIf
    ProcedureReturn rc
  EndIf

  stages[0]\sType = #VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO
  stages[0]\stage = #VK_SHADER_STAGE_VERTEX_BIT : stages[0]\module = vs
  stages[1]\sType = #VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO
  stages[1]\stage = #VK_SHADER_STAGE_FRAGMENT_BIT : stages[1]\module = fs
  cbinding[0]\binding=0 : cbinding[0]\stride=16 : cbinding[0]\inputRate=#VK_VERTEX_INPUT_RATE_VERTEX
  cbinding[1]\binding=1 : cbinding[1]\stride=32 : cbinding[1]\inputRate=#VK_VERTEX_INPUT_RATE_INSTANCE
  attrs[0]\location=0 : attrs[0]\binding=0 : attrs[0]\format=#VK_FORMAT_R32G32B32A32_SFLOAT
  attrs[1]\location=1 : attrs[1]\binding=1 : attrs[1]\format=#VK_FORMAT_R32G32B32A32_SFLOAT
  attrs[2]\location=2 : attrs[2]\binding=1 : attrs[2]\format=#VK_FORMAT_R32G32B32A32_SFLOAT : attrs[2]\offset=16
  vi\sType=#VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO
  vi\vertexBindingDescriptionCount=2 : vi\pVertexBindingDescriptions=@cbinding[0]
  vi\vertexAttributeDescriptionCount=3 : vi\pVertexAttributeDescriptions=@attrs[0]
  ia\sType = #VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO
  ia\topology = #VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP
  PokeL(@vp\width, GraphicsF32IntBits(nvcWidth))
  PokeL(@vp\height, GraphicsF32IntBits(nvcHeight))
  PokeL(@vp\maxDepth, #NEON_VK_CHROME_F_ONE)
  vpstate\sType = #VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO
  vpstate\viewportCount = 1 : vpstate\pViewports = @vp
  vpstate\scissorCount = 1 : vpstate\pScissors = 0
  dynStates[0] = #VK_DYNAMIC_STATE_VIEWPORT
  dynStates[1] = #VK_DYNAMIC_STATE_SCISSOR
  dyn\sType = #VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO
  dyn\dynamicStateCount = 2 : dyn\pDynamicStates = @dynStates[0]
  rs\sType = #VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO
  rs\polygonMode = #VK_POLYGON_MODE_FILL : rs\cullMode = #VK_CULL_MODE_NONE
  rs\frontFace = #VK_FRONT_FACE_COUNTER_CLOCKWISE
  PokeL(@rs\lineWidth, #NEON_VK_CHROME_F_ONE)
  ms\sType = #VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO
  ms\rasterizationSamples = #VK_SAMPLE_COUNT_1_BIT
  cba\blendEnable = #VK_TRUE
  cba\srcColorBlendFactor = #VK_BLEND_FACTOR_SRC_ALPHA
  cba\dstColorBlendFactor = #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
  cba\colorBlendOp = #VK_BLEND_OP_ADD
  cba\srcAlphaBlendFactor = #VK_BLEND_FACTOR_SRC_ALPHA
  cba\dstAlphaBlendFactor = #VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA
  cba\alphaBlendOp = #VK_BLEND_OP_ADD
  cba\colorWriteMask = #VK_COLOR_COMPONENT_R_BIT | #VK_COLOR_COMPONENT_G_BIT | #VK_COLOR_COMPONENT_B_BIT | #VK_COLOR_COMPONENT_A_BIT
  cb\sType = #VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO
  cb\attachmentCount = 1 : cb\pAttachments = @cba
  gp\sType = #VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO
  gp\stageCount = 2 : gp\pStages = @stages[0]
  gp\pVertexInputState = @vi : gp\pInputAssemblyState = @ia
  gp\pViewportState = @vpstate : gp\pRasterizationState = @rs
  gp\pMultisampleState = @ms : gp\pColorBlendState = @cb : gp\pDynamicState = @dyn
  gp\layout = compactLayout : gp\renderPass = nvcRenderPass : gp\subpass = 0 : gp\basePipelineIndex = -1
  ; Public pipeline refusal at seventeen arithmetic nodes, then a real
  ; sixteen-node shader through the same pipeline and GPU path.
  compactExtra=3 : smci\pCode=@compactVs[0] : smci\codeSize=compactBuildVs()
  badRc=vkCreateShaderModule(nvcDevice,@smci,0,@badVs)
  If badRc=0
    stages[0]\module=badVs
    badRc=vkCreateGraphicsPipelines(nvcDevice,0,1,@gp,0,@badPipe)
    PokeI($E1C01020,badRc) : PokeI($E1C01028,AnvilVkIrV3d42Error())
    PokeI($E1C01030,AnvilVkIrV3d42SourceId()) : PokeI($E1C01038,AnvilVkIrV3d42SourceOpcode())
    PokeI($E1C01040,AnvilVkIrV3d42Stage()) : PokeI($E1C01048,badPipe)
    vkDestroyShaderModule(nvcDevice,badVs,0)
  EndIf
  stages[0]\module=vs
  If badRc<>#VK_ERROR_FEATURE_NOT_PRESENT Or badPipe<>0
    rc=#NEON_VK_CHROME_ERR_STATE
  Else
    AnvilVkFaultClear()
  rc = vkCreateGraphicsPipelines(nvcDevice, 0, 1, @gp, 0, @compactPipeline)
  EndIf
  PokeI($E1C01050,rc) : PokeI($E1C01058,AnvilVkIrV3d42Error())
  PokeI($E1C01060,AnvilVkIrV3d42SourceId()) : PokeI($E1C01068,AnvilVkIrV3d42SourceOpcode())
  PokeI($E1C01070,AnvilVkIrV3d42Stage())

  vkDestroyShaderModule(nvcDevice, vs, 0)
  vkDestroyShaderModule(nvcDevice, fs, 0)
  ProcedureReturn rc
EndProcedure
Procedure.i compactDraw(first.i, count.i, colour.i, setHandle.i)
  Define sc.VkRect2D
  Define Dim push.l[4]
  If nvcBoxBatchActive <> 0 : ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_STATE) : EndIf
  If nvcDrawCount >= nvcMaxQuads Or nvcVertices > nvcMaxVertexQuads * 6
    ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_CAPACITY)
  EndIf
  ; Keep the default full-target path unchanged. A placed viewport maps the
  ; logical scissor's two endpoints into the same physical rectangle.
  If nvcViewportX = 0 And nvcViewportY = 0 And nvcViewportW = nvcPhysicalW And nvcViewportH = nvcPhysicalH
    sc\offset\x = nvcClipX : sc\offset\y = nvcClipY
    sc\extent\width = nvcClipW : sc\extent\height = nvcClipH
  Else
    sc\offset\x = nvcViewportX + (nvcClipX * nvcViewportW + nvcPhysicalW / 2) / nvcPhysicalW
    sc\offset\y = nvcViewportY + (nvcClipY * nvcViewportH + nvcPhysicalH / 2) / nvcPhysicalH
    sc\extent\width = nvcViewportX + ((nvcClipX + nvcClipW) * nvcViewportW + nvcPhysicalW / 2) / nvcPhysicalW - sc\offset\x
    sc\extent\height = nvcViewportY + ((nvcClipY + nvcClipH) * nvcViewportH + nvcPhysicalH / 2) / nvcPhysicalH - sc\offset\y
  EndIf
  vkCmdSetScissor(nvcCommand, 0, 1, @sc)

  nvcTint(colour, @push[0])
  vkCmdPushConstants(nvcCommand, compactLayout, #VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, @push[0])
  vkCmdDraw(nvcCommand, 4, count, 0, 0)
  nvcDrawCount = nvcDrawCount + 1
  ProcedureReturn #NEON_VK_CHROME_OK
EndProcedure

Global Dim lineProofX0.i[8]
Global Dim lineProofY0.i[8]
Global Dim lineProofX1.i[8]
Global Dim lineProofY1.i[8]
Procedure.i lineContractProof(imageBase.i, imagePitch.i, framebuffer.i)
 Define inputs.i,outputs.i,vary.i,table.i
 Define c0.i,c1.i,c2.i,c3.i,dx.i,dy.i,trace.i,traceBase.i,traceMap.i
 Define Dim bufs.i[2]
 Define Dim offsets.i[2]
 Define turn.i, path.i, rotation.i, lw.i, lh.i, rc.i, j.i, first.i, p.i, x.i, y.i, px.i, py.i, frame.i
 lineProofX0[0]=4 : lineProofY0[0]=4 : lineProofX1[0]=28 : lineProofY1[0]=4
 lineProofX0[1]=28 : lineProofY0[1]=8 : lineProofX1[1]=4 : lineProofY1[1]=8
 lineProofX0[2]=4 : lineProofY0[2]=12 : lineProofX1[2]=4 : lineProofY1[2]=28
 lineProofX0[3]=8 : lineProofY0[3]=28 : lineProofX1[3]=8 : lineProofY1[3]=12
 lineProofX0[4]=12 : lineProofY0[4]=12 : lineProofX1[4]=12 : lineProofY1[4]=12
 lineProofX0[5]=20 : lineProofY0[5]=16 : lineProofX1[5]=52 : lineProofY1[5]=24
 lineProofX0[6]=20 : lineProofY0[6]=32 : lineProofX1[6]=28 : lineProofY1[6]=60
 lineProofX0[7]=60 : lineProofY0[7]=44 : lineProofX1[7]=28 : lineProofY1[7]=36
 rc=compactCreate()
 If rc<>0
  PokeI($E1C01018,rc)
  If compactLayout<>0 : vkDestroyPipelineLayout(nvcDevice,compactLayout,0) : EndIf
  If compactSelector<>0 : vkDestroyBuffer(nvcDevice,compactSelector,0) : EndIf
  If compactSelectorMem<>0 : vkFreeMemory(nvcDevice,compactSelectorMem,0) : EndIf
  ProcedureReturn 208
 EndIf
 trace=avkPipeSlot(compactPipeline)
 traceBase=avkqBase[trace]
 PokeI($E1C01F00,traceBase) : PokeI($E1C01F08,avkqCsBytes[trace]) : PokeI($E1C01F10,avkqVsBytes[trace])
 For trace=0 To 2047 : PokeA($E1C01400+trace,PeekA(traceBase+trace)) : Next
 rc=vkMapMemory(nvcDevice,compactSelectorMem,0,64,0,@traceMap)
 If rc<>0 : ProcedureReturn 209 : EndIf
 For trace=0 To 63 : PokeA($E1C01200+trace,PeekA(traceMap+trace)) : Next
 vkUnmapMemory(nvcDevice,compactSelectorMem)
 table=0
 For inputs=0 To 16
  For outputs=4 To 14 Step 2
   For vary=0 To 8 Step 2
    PokeL($E1C00100+table*4,avkqSharedOutSeg(inputs,outputs,vary)) : table=table+1
   Next
  Next
 Next
 PokeI($E1C01078,table)
 For turn=0 To 3
  rotation=turn*90 : lw=800 : lh=1280
  If turn=1 Or turn=3 : lw=1280 : lh=800 : EndIf
  rc=NeonVkChromeRebind(framebuffer,lw,lh,800,1280,imagePitch,rotation)
  If rc<>0 : ProcedureReturn 201 : EndIf
  For path=0 To 1
   rc=NeonVkChromeBegin(@nwClear[0])
   If rc<>0 : ProcedureReturn 202 : EndIf
   If path=0
    first=NeonVkChromeLinesReserve(8)
    If first<0 : ProcedureReturn 203 : EndIf
    For j=0 To 7
      compactReferenceLineAt(nvcMapped+(first+j*6)*24,lineProofX0[j],lineProofY0[j],lineProofX1[j],lineProofY1[j])
    Next
    rc=NeonVkChromeLinesDraw(first,8,Neon_RGBA(255,255,255,255))
   Else
    first=nvcVertices : p=nvcMapped+first*24
    For j=0 To 7
     x=lineProofX0[j] : y=lineProofY0[j] : px=lineProofX1[j] : py=lineProofY1[j]
     dx=Abs(px-x) : dy=Abs(py-y)
     If dx=0 And dy=0
      c0=nvcLinePos(x*2,y*2) : c1=nvcLinePos(x*2+2,y*2)
      c2=nvcLinePos(x*2+2,y*2+2) : c3=nvcLinePos(x*2,y*2+2)
     ElseIf dx>=dy
      c0=nvcLinePos(x*2,y*2) : c1=nvcLinePos(px*2,py*2)
      c2=nvcLinePos(px*2,py*2+2) : c3=nvcLinePos(x*2,y*2+2)
     Else
      c0=nvcLinePos(x*2,y*2) : c1=nvcLinePos(px*2,py*2)
      c2=nvcLinePos(px*2+2,py*2) : c3=nvcLinePos(x*2+2,y*2)
     EndIf
     PokeL(p,c0) : PokeL(p+4,c1) : PokeL(p+8,c2) : PokeL(p+12,c3)
     PokeL(p+16,c0>>32) : PokeL(p+20,c1>>32) : PokeL(p+24,c2>>32) : PokeL(p+28,c3>>32)
     p=p+32
    Next
    If turn=0
      For trace=0 To 255 : PokeA($E1C01300+trace,PeekA(nvcMapped+first*24+trace)) : Next
    EndIf
    nvcVertices=nvcVertices+11
    bufs[0]=compactSelector : bufs[1]=nvcVertexBuffer : offsets[0]=0 : offsets[1]=first*24
    vkCmdBindVertexBuffers(nvcCommand,0,2,@bufs[0],@offsets[0])
    vkCmdBindPipeline(nvcCommand,#VK_PIPELINE_BIND_POINT_GRAPHICS,compactPipeline)
    rc=compactDraw(first,8,$FFFFFFFF,nvcDescriptorSet)
    bufs[0]=nvcVertexBuffer : offsets[0]=0
    vkCmdBindVertexBuffers(nvcCommand,0,1,@bufs[0],@offsets[0])
    vkCmdBindPipeline(nvcCommand,#VK_PIPELINE_BIND_POINT_GRAPHICS,nvcPipeline)
   EndIf
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 204 : EndIf
   If NeonVkChromeDrawCount()<>1 Or NeonVkChromeVertexCount()<>(48-37*path) : NeonVkChromeAbort() : ProcedureReturn 205 : EndIf
   rc=NeonVkChromeEnd()
   If rc<>0 : ProcedureReturn 206 : EndIf
   If NeonVkChromePresentConsume()<>1 : ProcedureReturn 207 : EndIf
   If path=1 And turn=0
    traceBase=AnvilVkV3dLastShaderRecord()
    PokeI($E1C01F18,AnvilVkV3dLastShaderRecordBytes())
    For trace=0 To 319 : PokeA($E1C01C00+trace,PeekA(traceBase+trace)) : Next
   EndIf
   frame=turn*2+path
   For y=0 To 63
    For x=0 To 63
     If rotation=90
      px=lh-1-y : py=x
     ElseIf rotation=180
      px=lw-1-x : py=lh-1-y
     ElseIf rotation=270
      px=y : py=lw-1-x
     Else
      px=x : py=y
     EndIf
     PokeL($E2400000+frame*16384+(y*64+x)*4,PeekL(imageBase+py*imagePitch+px*4))
    Next
   Next
   PokeI($E1C01008,frame+1)
  Next
 Next
 vkDestroyPipeline(nvcDevice,compactPipeline,0)
 vkDestroyPipelineLayout(nvcDevice,compactLayout,0)
 vkDestroyBuffer(nvcDevice,compactSelector,0)
 vkFreeMemory(nvcDevice,compactSelectorMem,0)
 ProcedureReturn 0
EndProcedure
