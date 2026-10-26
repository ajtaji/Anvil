Global Dim lineProofX0.i[8]
Global Dim lineProofY0.i[8]
Global Dim lineProofX1.i[8]
Global Dim lineProofY1.i[8]
Procedure.i lineContractProof(imageBase.i, imagePitch.i, framebuffer.i)
 Define turn.i, path.i, rotation.i, lw.i, lh.i, rc.i, j.i, first.i, p.i, x.i, y.i, px.i, py.i, frame.i
 lineProofX0[0]=4 : lineProofY0[0]=4 : lineProofX1[0]=28 : lineProofY1[0]=4
 lineProofX0[1]=28 : lineProofY0[1]=8 : lineProofX1[1]=4 : lineProofY1[1]=8
 lineProofX0[2]=4 : lineProofY0[2]=12 : lineProofX1[2]=4 : lineProofY1[2]=28
 lineProofX0[3]=8 : lineProofY0[3]=28 : lineProofX1[3]=8 : lineProofY1[3]=12
 lineProofX0[4]=12 : lineProofY0[4]=12 : lineProofX1[4]=12 : lineProofY1[4]=12
 lineProofX0[5]=20 : lineProofY0[5]=16 : lineProofX1[5]=52 : lineProofY1[5]=24
 lineProofX0[6]=20 : lineProofY0[6]=32 : lineProofX1[6]=28 : lineProofY1[6]=60
 lineProofX0[7]=60 : lineProofY0[7]=44 : lineProofX1[7]=28 : lineProofY1[7]=36
 For turn=0 To 3
  rotation=turn*90 : lw=800 : lh=1280
  If turn=1 Or turn=3 : lw=1280 : lh=800 : EndIf
  rc=NeonVkChromeRebind(framebuffer,lw,lh,800,1280,imagePitch,rotation)
  If rc<>0 : ProcedureReturn 201 : EndIf
  For path=0 To 1
   rc=NeonVkChromeBegin(@nwClear[0])
   If rc<>0 : ProcedureReturn 202 : EndIf
   If path=0
    rc=NeonVkChromeLinesBegin()
    If rc=0
     For j=0 To 7 : NeonVkChromeLine(lineProofX0[j],lineProofY0[j],lineProofX1[j],lineProofY1[j]) : Next
     rc=NeonVkChromeLinesEnd(Neon_RGBA(255,255,255,255))
    EndIf
   Else
    first=NeonVkChromeLinesReserve(8)
    If first<0 : NeonVkChromeAbort() : ProcedureReturn 203 : EndIf
    p=NeonVkChromeVertexAddress(first)
    For j=0 To 7 : NeonVkChromeLineQuadAt(p+j*144,lineProofX0[j],lineProofY0[j],lineProofX1[j],lineProofY1[j]) : Next
    rc=NeonVkChromeLinesDraw(first,8,Neon_RGBA(255,255,255,255))
   EndIf
   If rc<>0 : NeonVkChromeAbort() : ProcedureReturn 204 : EndIf
   If NeonVkChromeDrawCount()<>1 Or NeonVkChromeVertexCount()<>48 : NeonVkChromeAbort() : ProcedureReturn 205 : EndIf
   rc=NeonVkChromeEnd()
   If rc<>0 : ProcedureReturn 206 : EndIf
   If NeonVkChromePresentConsume()<>1 : ProcedureReturn 207 : EndIf
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
 ProcedureReturn 0
EndProcedure
