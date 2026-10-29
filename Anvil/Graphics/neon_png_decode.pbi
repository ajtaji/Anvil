; SPDX-License-Identifier: MIT
; PNG default-image decoding into straight, top-down RGBA8. Include the
; existing Core/crc.pbi owner first, with its standard #CRC_POLY contract.
XIncludeFile "Anvil/Graphics/neon_sprite_decode.pbi"
XIncludeFile "Anvil/Graphics/neon_inflate_prefix.pbi"
#NEON_PNG_MAX_SOURCE=16777216
#NEON_PNG_ERR_ARGUMENT=-23000
#NEON_PNG_ERR_FORMAT=-23001
#NEON_PNG_ERR_TRUNCATED=-23002
#NEON_PNG_ERR_CAPACITY=-23003
#NEON_PNG_ERR_CHECKSUM=-23004
Structure NeonPngInfo Align #PB_Structure_AlignC
  width.i : height.i : depth.i : kind.i : interlace.i : channels.i
  idatBytes.i : rawBytes.i : workspaceBytes.i
  palette.i : paletteCount.i : transparency.i : transparencyBytes.i
EndStructure
Procedure.i npgBE(p.i,n.i)
  Protected i.i,v.i
  For i=0 To n-1 : v=(v<<8) | (PeekA(p+i) & 255) : Next
  ProcedureReturn v
EndProcedure
Procedure.i npgPass(value.i,step.i,start.i)
  If value<=start : ProcedureReturn 0 : EndIf
  ProcedureReturn (value-start+step-1)/step
EndProcedure
Procedure.i npgRawBytes(w.i,h.i,channels.i,depth.i,interlace.i)
  Protected p.i,sx.i,sy.i,dx.i,dy.i,pw.i,ph.i,total.i,last.i=0
  If interlace<>0 : last=6 : EndIf
  For p=0 To last
    sx=0 : sy=0 : dx=1 : dy=1
    If interlace<>0
      sx=PeekA(?npgAdamX+p) & 255 : sy=PeekA(?npgAdamY+p) & 255
      dx=PeekA(?npgAdamDX+p) & 255 : dy=PeekA(?npgAdamDY+p) & 255
    EndIf
    pw=npgPass(w,dx,sx) : ph=npgPass(h,dy,sy)
    If pw>0 And ph>0 : total=total+(((pw*channels*depth+7)/8)+1)*ph : EndIf
  Next
  ProcedureReturn total
EndProcedure
; Validate the entire bounded container and checksums before publishing info.
; Palette/tRNS pointers borrow immutable encoded storage, not copied metadata.
Procedure.i NeonPngInspect(*out.NeonPngInfo,source.i,bytes.i)
  Protected m.NeonPngInfo,p.i=8,n.i,t.i,i.i,seen.i,idat.i,idatEnd.i,trns.i,finished.i,maxSample.i,v.i
  If *out=0 Or (*out & 7)<>0 Or NeonByteSpan(*out,SizeOf(NeonPngInfo))=0 Or bytes<1 Or bytes>#NEON_PNG_MAX_SOURCE Or NeonByteSpan(source,bytes)=0 : ProcedureReturn #NEON_PNG_ERR_ARGUMENT : EndIf
  If NeonByteOverlap(*out,SizeOf(NeonPngInfo),source,bytes)<>0 : ProcedureReturn #NEON_PNG_ERR_ARGUMENT : EndIf
  If bytes<8 : ProcedureReturn #NEON_PNG_ERR_TRUNCATED : EndIf
  For i=0 To 7 : If (PeekA(source+i) & 255)<>(PeekA(?npgSignature+i) & 255) : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf : Next
  For i=0 To SizeOf(NeonPngInfo)-1 : PokeA(@m+i,0) : Next
  While p<bytes
    If bytes-p<12 : ProcedureReturn #NEON_PNG_ERR_TRUNCATED : EndIf
    n=npgBE(source+p,4) : t=npgBE(source+p+4,4)
    If n>$7FFFFFFF : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
    If n>bytes-p-12 : ProcedureReturn #NEON_PNG_ERR_TRUNCATED : EndIf
    For i=0 To 3
      v=PeekA(source+p+4+i) & 255
      If (v<65 Or v>90) And (v<97 Or v>122) : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
    Next
    If Crc32(source+p+4,n+4)<>npgBE(source+p+8+n,4) : ProcedureReturn #NEON_PNG_ERR_CHECKSUM : EndIf
    If seen=0 And t<>$49484452 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
    If idat<>0 And t<>$49444154 : idatEnd=1 : EndIf
    If t=$49484452
      If seen<>0 Or n<>13 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      seen=1 : m\width=npgBE(source+p+8,4) : m\height=npgBE(source+p+12,4)
      m\depth=PeekA(source+p+16) & 255 : m\kind=PeekA(source+p+17) & 255 : m\interlace=PeekA(source+p+20) & 255
      If m\width<1 Or m\height<1 Or m\width>#NEON_ASSET_MAX_DIM Or m\height>#NEON_ASSET_MAX_DIM Or m\interlace>1 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      If (PeekA(source+p+18) & 255)<>0 Or (PeekA(source+p+19) & 255)<>0 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      If m\kind=0
        m\channels=1 : If m\depth<>1 And m\depth<>2 And m\depth<>4 And m\depth<>8 And m\depth<>16 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      ElseIf m\kind=3
        m\channels=1 : If m\depth<>1 And m\depth<>2 And m\depth<>4 And m\depth<>8 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      ElseIf m\kind=2 Or m\kind=4 Or m\kind=6
        If m\depth<>8 And m\depth<>16 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
        If m\kind=2 : m\channels=3 : ElseIf m\kind=4 : m\channels=2 : Else : m\channels=4 : EndIf
      Else
        ProcedureReturn #NEON_PNG_ERR_FORMAT
      EndIf
    ElseIf t=$504C5445
      If m\palette<>0 Or idat<>0 Or trns<>0 Or n<3 Or n>768 Or n%3<>0 Or m\kind=0 Or m\kind=4 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      m\palette=source+p+8 : m\paletteCount=n/3
      If m\kind=3 And m\paletteCount>(1<<m\depth) : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
    ElseIf t=$74524E53
      If trns<>0 Or idat<>0 Or m\kind=4 Or m\kind=6 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      trns=1 : m\transparency=source+p+8 : m\transparencyBytes=n
      maxSample=(1<<m\depth)-1
      If m\kind=0
        If n<>2 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      ElseIf m\kind=2
        If n<>6 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      ElseIf m\kind=3
        If m\palette=0 Or n>m\paletteCount : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      EndIf
    ElseIf t=$49444154
      If idatEnd<>0 Or (m\kind=3 And m\palette=0) : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      idat=1 : m\idatBytes=m\idatBytes+n
    ElseIf t=$49454E44
      If n<>0 Or idat=0 Or p+12<>bytes : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
      finished=1 : Break
    Else
      If (PeekA(source+p+4) & 32)=0 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
    EndIf
    p=p+n+12
  Wend
  If finished=0 : ProcedureReturn #NEON_PNG_ERR_TRUNCATED : EndIf
  If m\idatBytes<6 : ProcedureReturn #NEON_PNG_ERR_TRUNCATED : EndIf
  m\rawBytes=npgRawBytes(m\width,m\height,m\channels,m\depth,m\interlace)
  m\workspaceBytes=8192+((m\idatBytes+7) & $FFFFFFF8)+((m\rawBytes+7) & $FFFFFFF8)+m\width*m\height*4
  For i=0 To SizeOf(NeonPngInfo)-1 : PokeA(*out+i,PeekA(@m+i)) : Next
  ProcedureReturn 0
EndProcedure
Procedure.i npgPaeth(a.i,b.i,c.i)
  Protected p.i=a+b-c,pa.i,pb.i,pc.i
  pa=p-a : If pa<0 : pa=0-pa : EndIf
  pb=p-b : If pb<0 : pb=0-pb : EndIf
  pc=p-c : If pc<0 : pc=0-pc : EndIf
  If pa<=pb And pa<=pc : ProcedureReturn a : EndIf
  If pb<=pc : ProcedureReturn b : EndIf
  ProcedureReturn c
EndProcedure
Procedure.i npgSample(row.i,x.i,channel.i,channels.i,depth.i)
  Protected index.i=x*channels+channel,bit.i
  If depth=8 : ProcedureReturn PeekA(row+index) & 255 : EndIf
  If depth=16 : ProcedureReturn npgBE(row+index*2,2) : EndIf
  bit=x*depth
  ProcedureReturn ((PeekA(row+bit/8) & 255)>>(8-depth-(bit & 7))) & ((1<<depth)-1)
EndProcedure
Procedure.i npgEight(v.i,depth.i)
  If depth=16 : ProcedureReturn v>>8 : EndIf
  If depth=8 : ProcedureReturn v : EndIf
  ProcedureReturn (v*255)/((1<<depth)-1)
EndProcedure
Procedure.i npgPixels(*m.NeonPngInfo,raw.i,rgba.i,colourKey.i)
  Protected pass.i,last.i=0,sx.i,sy.i,dx.i,dy.i,pw.i,ph.i,rowBytes.i,bpp.i,previous.i,row.i,cursor.i
  Protected y.i,x.i,kind.i,a.i,b.i,c.i,v.i,red.i,green.i,blue.i,alpha.i,index.i,pixel.i
  bpp=(*m\channels* *m\depth+7)/8
  If *m\interlace<>0 : last=6 : EndIf
  For pass=0 To last
    sx=0 : sy=0 : dx=1 : dy=1
    If *m\interlace<>0
      sx=PeekA(?npgAdamX+pass) & 255 : sy=PeekA(?npgAdamY+pass) & 255
      dx=PeekA(?npgAdamDX+pass) & 255 : dy=PeekA(?npgAdamDY+pass) & 255
    EndIf
    pw=npgPass(*m\width,dx,sx) : ph=npgPass(*m\height,dy,sy) : previous=0
    If pw>0 And ph>0
      rowBytes=(pw* *m\channels* *m\depth+7)/8
      For y=0 To ph-1
        kind=PeekA(raw+cursor) & 255 : row=raw+cursor+1
        If kind>4 : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
        For x=0 To rowBytes-1
          a=0 : b=0 : c=0
          If x>=bpp : a=PeekA(row+x-bpp) & 255 : EndIf
          If previous<>0
            b=PeekA(previous+x) & 255
            If x>=bpp : c=PeekA(previous+x-bpp) & 255 : EndIf
          EndIf
          v=PeekA(row+x) & 255
          If kind=1 : v=v+a : ElseIf kind=2 : v=v+b : ElseIf kind=3 : v=v+(a+b)/2 : ElseIf kind=4 : v=v+npgPaeth(a,b,c) : EndIf
          PokeA(row+x,v & 255)
        Next
        For x=0 To pw-1
          alpha=255
          If *m\kind=3
            index=npgSample(row,x,0,1,*m\depth)
            If index>=*m\paletteCount
              red=0 : green=0 : blue=0
            Else
              red=PeekA(*m\palette+index*3) & 255 : green=PeekA(*m\palette+index*3+1) & 255 : blue=PeekA(*m\palette+index*3+2) & 255
              If index<*m\transparencyBytes : alpha=PeekA(*m\transparency+index) & 255 : EndIf
            EndIf
          ElseIf *m\kind=0 Or *m\kind=4
            v=npgSample(row,x,0,*m\channels,*m\depth)
            red=npgEight(v,*m\depth) : green=red : blue=red
            If *m\kind=4
              alpha=npgEight(npgSample(row,x,1,2,*m\depth),*m\depth)
            ElseIf *m\transparency<>0
              If v=(npgBE(*m\transparency,2) & ((1<<*m\depth)-1)) : alpha=0 : EndIf
            EndIf
          Else
            red=npgSample(row,x,0,*m\channels,*m\depth) : green=npgSample(row,x,1,*m\channels,*m\depth) : blue=npgSample(row,x,2,*m\channels,*m\depth)
            If *m\kind=6
              alpha=npgEight(npgSample(row,x,3,4,*m\depth),*m\depth)
            ElseIf *m\transparency<>0
              If red=(npgBE(*m\transparency,2) & ((1<<*m\depth)-1)) And green=(npgBE(*m\transparency+2,2) & ((1<<*m\depth)-1)) And blue=(npgBE(*m\transparency+4,2) & ((1<<*m\depth)-1)) : alpha=0 : EndIf
            EndIf
            red=npgEight(red,*m\depth) : green=npgEight(green,*m\depth) : blue=npgEight(blue,*m\depth)
          EndIf
          If colourKey<>-1 And (red | (green<<8) | (blue<<16))=colourKey : red=0 : green=0 : blue=0 : alpha=0 : EndIf
          pixel=((sy+y*dy)* *m\width+sx+x*dx)*4
          PokeA(rgba+pixel,red) : PokeA(rgba+pixel+1,green) : PokeA(rgba+pixel+2,blue) : PokeA(rgba+pixel+3,alpha)
        Next
        previous=row : cursor=cursor+rowBytes+1
      Next
    EndIf
  Next
  If cursor<>*m\rawBytes : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
  ProcedureReturn 0
EndProcedure
; Scratch is disposable. Info/RGBA/mask publish only after complete success.
Procedure.i NeonPngDecode(*out.NeonSpriteAssetInfo,source.i,bytes.i,rgba.i,capacity.i,colourKey.i,mask.i,maskCapacity.i,scratch.i,scratchCapacity.i)
  Protected m.NeonPngInfo,state.NeonInflateState,rc.i,p.i,n.i,written.i,i.i,pixels.i,outputBytes.i,packed.i,raw.i,temporary.i
  If *out=0 Or (*out & 7)<>0 Or scratch=0 Or (scratch & 7)<>0 Or colourKey<-1 Or colourKey>$FFFFFF : ProcedureReturn #NEON_PNG_ERR_ARGUMENT : EndIf
  rc=NeonPngInspect(@m,source,bytes) : If rc<>0 : ProcedureReturn rc : EndIf
  pixels=m\width*m\height : outputBytes=pixels*4
  If capacity<outputBytes Or scratchCapacity<m\workspaceBytes Or (mask<>0 And maskCapacity<pixels) : ProcedureReturn #NEON_PNG_ERR_CAPACITY : EndIf
  If NeonByteSpan(*out,SizeOf(NeonSpriteAssetInfo))=0 Or NeonByteSpan(rgba,outputBytes)=0 Or NeonByteSpan(scratch,m\workspaceBytes)=0 Or (mask<>0 And NeonByteSpan(mask,pixels)=0) : ProcedureReturn #NEON_PNG_ERR_ARGUMENT : EndIf
  If NeonByteOverlap(*out,SizeOf(NeonSpriteAssetInfo),source,bytes)<>0 Or NeonByteOverlap(*out,SizeOf(NeonSpriteAssetInfo),rgba,outputBytes)<>0 Or NeonByteOverlap(*out,SizeOf(NeonSpriteAssetInfo),scratch,m\workspaceBytes)<>0 : ProcedureReturn #NEON_PNG_ERR_ARGUMENT : EndIf
  If NeonByteOverlap(source,bytes,rgba,outputBytes)<>0 Or NeonByteOverlap(source,bytes,scratch,m\workspaceBytes)<>0 Or NeonByteOverlap(rgba,outputBytes,scratch,m\workspaceBytes)<>0 : ProcedureReturn #NEON_PNG_ERR_ARGUMENT : EndIf
  If mask<>0
    If NeonByteOverlap(mask,pixels,*out,SizeOf(NeonSpriteAssetInfo))<>0 Or NeonByteOverlap(mask,pixels,source,bytes)<>0 Or NeonByteOverlap(mask,pixels,rgba,outputBytes)<>0 Or NeonByteOverlap(mask,pixels,scratch,m\workspaceBytes)<>0 : ProcedureReturn #NEON_PNG_ERR_ARGUMENT : EndIf
  EndIf
  packed=scratch+8192 : raw=packed+((m\idatBytes+7) & $FFFFFFF8) : temporary=raw+((m\rawBytes+7) & $FFFFFFF8)
  p=8
  While p<bytes
    n=npgBE(source+p,4)
    If npgBE(source+p+4,4)=$49444154
      For i=0 To n-1 : PokeA(packed+written+i,PeekA(source+p+8+i)) : Next
      written=written+n
    EndIf
    p=p+n+12
  Wend
  rc=NeonInflateZlibPrefix(@state,scratch,8192,packed,m\idatBytes,raw,m\rawBytes)
  If rc<0 : ProcedureReturn rc : EndIf
  If rc<>m\rawBytes : ProcedureReturn #NEON_PNG_ERR_FORMAT : EndIf
  rc=npgPixels(@m,raw,temporary,colourKey) : If rc<>0 : ProcedureReturn rc : EndIf
  For i=0 To outputBytes-1 : PokeA(rgba+i,PeekA(temporary+i)) : Next
  If mask<>0
    For i=0 To pixels-1 : PokeA(mask+i,Bool((PeekA(temporary+i*4+3) & 255)>0)) : Next
  EndIf
  *out\width=m\width : *out\height=m\height
  ProcedureReturn 0
EndProcedure
DataSection
npgSignature:
  Data.a 137,80,78,71,13,10,26,10
npgAdamX:
  Data.a 0,4,0,2,0,1,0
npgAdamY:
  Data.a 0,0,4,0,2,0,1
npgAdamDX:
  Data.a 8,8,4,4,2,2,1
npgAdamDY:
  Data.a 8,8,8,4,4,2,2
EndDataSection
