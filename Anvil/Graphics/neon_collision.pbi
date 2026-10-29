; SPDX-License-Identifier: MIT
; Renderer-independent Neon collision and geometry. Caller owns all buffers.
; API semantics reference: Neon GlMath.pbi; corrected conservative pixel bounds.
XIncludeFile "Anvil/Math/float32.pbi"
XIncludeFile "Anvil/Math/float32_convert.pbi"
#NCO_ERR_ARGS=-22500
#NCO_ERR_GEOMETRY=-22501
#NCO_ERR_CAPACITY=-22502
#NCO_ERR_BUDGET=-22503
Structure NeonCollisionPoint Align #PB_Structure_AlignC
  x.f : y.f
EndStructure
Structure NeonCollisionMask Align #PB_Structure_AlignC
  data.i : bytes.i : width.i : height.i : stride.i
EndStructure
Structure NeonCollisionTransform Align #PB_Structure_AlignC
  x.f : y.f : angle.f : scale.f
EndStructure
Structure NeonCollisionBounds Align #PB_Structure_AlignC
  left.f : top.f : right.f : bottom.f : cx.f : cy.f : cosine.f : sine.f
EndStructure
Procedure.i ncoFinite(v.f)
  ProcedureReturn Bool((MathBitsOf(v) & $7FFFFFFF)<=$49742400)
EndProcedure
Procedure.i ncoRange(p.i,bytes.i,alignment.i)
  ProcedureReturn Bool(p<>0 And (p & (alignment-1))=0 And bytes>0 And p+bytes>p)
EndProcedure
Procedure.i ncoOverlap(a.i,ab.i,b.i,bb.i)
  ProcedureReturn Bool(a<b+bb And b<a+ab)
EndProcedure
Procedure.i NeonCollisionAABB(x1.f,y1.f,w1.f,h1.f,x2.f,y2.f,w2.f,h2.f)
  If ncoFinite(x1)=0 Or ncoFinite(y1)=0 Or ncoFinite(w1)=0 Or ncoFinite(h1)=0 Or ncoFinite(x2)=0 Or ncoFinite(y2)=0 Or ncoFinite(w2)=0 Or ncoFinite(h2)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  If w1<0.0 Or h1<0.0 Or w2<0.0 Or h2<0.0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  If w1=0.0 Or h1=0.0 Or w2=0.0 Or h2=0.0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(x1<x2+w2 And x1+w1>x2 And y1<y2+h2 And y1+h1>y2)
EndProcedure
Procedure.i NeonCollisionCircle(x1.f,y1.f,r1.f,x2.f,y2.f,r2.f)
  Protected dx.f,dy.f,r.f
  If ncoFinite(x1)=0 Or ncoFinite(y1)=0 Or ncoFinite(r1)=0 Or ncoFinite(x2)=0 Or ncoFinite(y2)=0 Or ncoFinite(r2)=0 Or r1<0.0 Or r2<0.0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  dx=x1-x2 : dy=y1-y2 : r=r1+r2
  ProcedureReturn Bool(dx*dx+dy*dy<=r*r)
EndProcedure
Procedure.i NeonCollisionLineLine(x1.f,y1.f,x2.f,y2.f,x3.f,y3.f,x4.f,y4.f,*hit.NeonCollisionPoint)
  Protected den.f,t.f,u.f
  If ncoFinite(x1)=0 Or ncoFinite(y1)=0 Or ncoFinite(x2)=0 Or ncoFinite(y2)=0 Or ncoFinite(x3)=0 Or ncoFinite(y3)=0 Or ncoFinite(x4)=0 Or ncoFinite(y4)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  If *hit<>0 : If ncoRange(*hit,8,4)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf : EndIf
  den=(x1-x2)*(y3-y4)-(y1-y2)*(x3-x4)
  If den=0.0 : ProcedureReturn 0 : EndIf
  t=((x1-x3)*(y3-y4)-(y1-y3)*(x3-x4))/den
  u=(0.0-((x1-x2)*(y1-y3)-(y1-y2)*(x1-x3)))/den
  If t<=0.0 Or t>=1.0 Or u<=0.0 Or u>=1.0 : ProcedureReturn 0 : EndIf
  If *hit<>0 : *hit\x=x1+t*(x2-x1) : *hit\y=y1+t*(y2-y1) : EndIf
  ProcedureReturn 1
EndProcedure
Procedure.i NeonCollisionLineCircle(x1.f,y1.f,x2.f,y2.f,cx.f,cy.f,r.f)
  Protected dx.f,dy.f,len.f,t.f
  If ncoFinite(x1)=0 Or ncoFinite(y1)=0 Or ncoFinite(x2)=0 Or ncoFinite(y2)=0 Or ncoFinite(cx)=0 Or ncoFinite(cy)=0 Or ncoFinite(r)=0 Or r<0.0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  dx=x2-x1 : dy=y2-y1 : len=dx*dx+dy*dy
  If len=0.0 : ProcedureReturn NeonCollisionCircle(x1,y1,0.0,cx,cy,r) : EndIf
  t=((cx-x1)*dx+(cy-y1)*dy)/len
  If t<0.0 : t=0.0 : ElseIf t>1.0 : t=1.0 : EndIf
  ProcedureReturn NeonCollisionCircle(x1+t*dx,y1+t*dy,0.0,cx,cy,r)
EndProcedure
Procedure.i NeonCollisionBezier(t.f,x0.f,y0.f,x1.f,y1.f,x2.f,y2.f,x3.f,y3.f,*out.NeonCollisionPoint)
  Protected u.f,tt.f,uu.f,uuu.f,ttt.f
  If ncoRange(*out,8,4)=0 Or ncoFinite(t)=0 Or t<0.0 Or t>1.0 Or ncoFinite(x0)=0 Or ncoFinite(y0)=0 Or ncoFinite(x1)=0 Or ncoFinite(y1)=0 Or ncoFinite(x2)=0 Or ncoFinite(y2)=0 Or ncoFinite(x3)=0 Or ncoFinite(y3)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  u=1.0-t : tt=t*t : uu=u*u : uuu=uu*u : ttt=tt*t
  *out\x=uuu*x0+3.0*uu*t*x1+3.0*u*tt*x2+ttt*x3
  *out\y=uuu*y0+3.0*uu*t*y1+3.0*u*tt*y2+ttt*y3
  ProcedureReturn 0
EndProcedure
Procedure.i ncoMaskValid(*m.NeonCollisionMask)
  Protected needed.i
  If ncoRange(*m,SizeOf(NeonCollisionMask),8)=0 : ProcedureReturn 0 : EndIf
  If *m\width<1 Or *m\width>4096 Or *m\height<1 Or *m\height>4096 Or *m\stride<*m\width Or *m\stride>65536 : ProcedureReturn 0 : EndIf
  needed=(*m\height-1)* *m\stride+*m\width
  If *m\bytes<needed Or *m\bytes>268435456 Or ncoRange(*m\data,*m\bytes,1)=0 : ProcedureReturn 0 : EndIf
  ProcedureReturn Bool(ncoOverlap(*m,SizeOf(NeonCollisionMask),*m\data,*m\bytes)=0)
EndProcedure
Procedure.i NeonCollisionMaskBind(*m.NeonCollisionMask,data.i,bytes.i,width.i,height.i,stride.i)
  Protected temp.NeonCollisionMask,i.i
  If ncoRange(*m,SizeOf(NeonCollisionMask),8)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  temp\data=data : temp\bytes=bytes : temp\width=width : temp\height=height : temp\stride=stride
  If ncoMaskValid(@temp)=0 Or ncoOverlap(*m,SizeOf(NeonCollisionMask),data,bytes)<>0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  For i=0 To SizeOf(NeonCollisionMask)-1 : PokeA(*m+i,PeekA(@temp+i)) : Next
  ProcedureReturn 0
EndProcedure
; RGBA byte input; any nonzero alpha is solid, matching Neon's loader.
Procedure.i NeonCollisionMaskFromRGBA(*m.NeonCollisionMask,rgba.i,bytes.i,pitch.i)
  Protected needed.i,x.i,y.i
  If ncoMaskValid(*m)=0 Or pitch<*m\width*4 Or pitch>65536 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  needed=(*m\height-1)*pitch+*m\width*4
  If bytes<needed Or ncoRange(rgba,bytes,1)=0 Or ncoOverlap(*m\data,*m\bytes,rgba,bytes)<>0 Or ncoOverlap(*m,SizeOf(NeonCollisionMask),rgba,bytes)<>0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  For y=0 To *m\height-1
    For x=0 To *m\width-1 : PokeA(*m\data+y* *m\stride+x,Bool(PeekA(rgba+y*pitch+x*4+3)<>0)) : Next
  Next
  ProcedureReturn 0
EndProcedure
Procedure.f ncoCross(*o.NeonCollisionPoint,*a.NeonCollisionPoint,*b.NeonCollisionPoint)
  ProcedureReturn (*a\x-*o\x)*(*b\y-*o\y)-(*a\y-*o\y)*(*b\x-*o\x)
EndProcedure
Procedure.i NeonCollisionHullScratchBytes(width.i)
  If width<1 Or width>4096 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  ProcedureReturn (6*width+2)*8
EndProcedure
; Lexicographically ordered column extrema suffice for the hull of all solid centres.
; Scratch is disposable. Output stays unchanged on refusal or a degenerate hull.
Procedure.i NeonCollisionHull(*m.NeonCollisionMask,out.i,capacity.i,scratch.i,scratchBytes.i)
  Protected needed.i,x.i,y.i,top.i,bottom.i,n.i,k.i,i.i,lower.i,points.i,chain.i
  Protected *p.NeonCollisionPoint,*a.NeonCollisionPoint,*b.NeonCollisionPoint,*c.NeonCollisionPoint
  If ncoMaskValid(*m)=0 Or capacity<3 Or capacity>8192 Or ncoRange(out,capacity*8,4)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  needed=NeonCollisionHullScratchBytes(*m\width)
  If scratchBytes<needed : ProcedureReturn #NCO_ERR_CAPACITY : EndIf
  If ncoRange(scratch,scratchBytes,4)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  If ncoOverlap(scratch,scratchBytes,out,capacity*8)<>0 Or ncoOverlap(scratch,scratchBytes,*m\data,*m\bytes)<>0 Or ncoOverlap(scratch,scratchBytes,*m,SizeOf(NeonCollisionMask))<>0 Or ncoOverlap(out,capacity*8,*m\data,*m\bytes)<>0 Or ncoOverlap(out,capacity*8,*m,SizeOf(NeonCollisionMask))<>0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  points=scratch : chain=scratch+*m\width*2*8
  For x=0 To *m\width-1
    top=-1 : bottom=-1
    For y=0 To *m\height-1
      If PeekA(*m\data+y* *m\stride+x)<>0 : top=y : Break : EndIf
    Next
    If top<0 : Continue : EndIf
    For y=*m\height-1 To top Step -1
      If PeekA(*m\data+y* *m\stride+x)<>0 : bottom=y : Break : EndIf
    Next
    *p=points+n*8 : *p\x=MathFFromInt(x)-MathFFromInt(*m\width)/2.0 : *p\y=MathFFromInt(top)-MathFFromInt(*m\height)/2.0 : n=n+1
    If bottom<>top : *p=points+n*8 : *p\x=MathFFromInt(x)-MathFFromInt(*m\width)/2.0 : *p\y=MathFFromInt(bottom)-MathFFromInt(*m\height)/2.0 : n=n+1 : EndIf
  Next
  If n<3 : ProcedureReturn 0 : EndIf
  For i=0 To n-1
    *c=points+i*8
    While k>=2
      *a=chain+(k-2)*8 : *b=chain+(k-1)*8
      If ncoCross(*a,*b,*c)>0.0 : Break : EndIf
      k=k-1
    Wend
    PokeL(chain+k*8,PeekL(*c)) : PokeL(chain+k*8+4,PeekL(*c+4)) : k=k+1
  Next
  lower=k+1
  For i=n-2 To 0 Step -1
    *c=points+i*8
    While k>=lower
      *a=chain+(k-2)*8 : *b=chain+(k-1)*8
      If ncoCross(*a,*b,*c)>0.0 : Break : EndIf
      k=k-1
    Wend
    PokeL(chain+k*8,PeekL(*c)) : PokeL(chain+k*8+4,PeekL(*c+4)) : k=k+1
  Next
  k=k-1 : If k<3 : ProcedureReturn 0 : EndIf
  If k>capacity : ProcedureReturn #NCO_ERR_CAPACITY : EndIf
  For i=0 To k*8-1 : PokeA(out+i,PeekA(chain+i)) : Next
  ProcedureReturn k
EndProcedure
; Check ALL vertices against ALL edge halfplanes: rejects concavity and star order.
Procedure.i NeonCollisionPolygonValidate(points.i,count.i)
  Protected i.i,j.i,side.i,want.i,*a.NeonCollisionPoint,*b.NeonCollisionPoint,*p.NeonCollisionPoint,cross.f
  If count<3 Or count>8192 Or ncoRange(points,count*8,4)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  For i=0 To count-1
    *p=points+i*8
    If ncoFinite(*p\x)=0 Or ncoFinite(*p\y)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  Next
  For i=0 To count-1
    *a=points+i*8
    For j=i+1 To count-1
      *p=points+j*8
      If *a\x=*p\x And *a\y=*p\y : ProcedureReturn #NCO_ERR_GEOMETRY : EndIf
    Next
    *b=points+((i+1) % count)*8
    If *a\x=*b\x And *a\y=*b\y : ProcedureReturn #NCO_ERR_GEOMETRY : EndIf
    For j=0 To count-1
      *p=points+j*8 : cross=ncoCross(*a,*b,*p)
      If cross=0.0 : Continue : EndIf
      side=1 : If cross<0.0 : side=-1 : EndIf
      If want=0 : want=side : ElseIf side<>want : ProcedureReturn #NCO_ERR_GEOMETRY : EndIf
    Next
  Next
  If want=0 : ProcedureReturn #NCO_ERR_GEOMETRY : EndIf
  ProcedureReturn 0
EndProcedure
Procedure.i NeonCollisionSAT(a.i,an.i,ax.f,ay.f,b.i,bn.i,bx.f,by.f)
  Protected rc.i,pass.i,i.i,j.i,points.i,count.i,*p.NeonCollisionPoint,*next.NeonCollisionPoint
  Protected nx.f,ny.f,v.f,amin.f,amax.f,bmin.f,bmax.f
  If ncoFinite(ax)=0 Or ncoFinite(ay)=0 Or ncoFinite(bx)=0 Or ncoFinite(by)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  rc=NeonCollisionPolygonValidate(a,an) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=NeonCollisionPolygonValidate(b,bn) : If rc<>0 : ProcedureReturn rc : EndIf
  For pass=0 To 1
    points=a : count=an : If pass=1 : points=b : count=bn : EndIf
    For i=0 To count-1
      *p=points+i*8 : *next=points+((i+1) % count)*8 : nx=0.0-(*next\y-*p\y) : ny=*next\x-*p\x
      For j=0 To an-1
        *p=a+j*8 : v=(*p\x+ax)*nx+(*p\y+ay)*ny
        If j=0 : amin=v : amax=v : Else : If v<amin : amin=v : EndIf : If v>amax : amax=v : EndIf : EndIf
      Next
      For j=0 To bn-1
        *p=b+j*8 : v=(*p\x+bx)*nx+(*p\y+by)*ny
        If j=0 : bmin=v : bmax=v : Else : If v<bmin : bmin=v : EndIf : If v>bmax : bmax=v : EndIf : EndIf
      Next
      If amax<bmin Or bmax<amin : ProcedureReturn 0 : EndIf
    Next
  Next
  ProcedureReturn 1
EndProcedure
Procedure.i ncoBounds(*m.NeonCollisionMask,*t.NeonCollisionTransform,*out.NeonCollisionBounds)
  Protected angle.f,halfW.f,halfH.f,ex.f,ey.f
  If ncoMaskValid(*m)=0 Or ncoRange(*t,16,4)=0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  If ncoFinite(*t\x)=0 Or ncoFinite(*t\y)=0 Or ncoFinite(*t\angle)=0 Or ncoFinite(*t\scale)=0 Or *t\scale<0.0009765625 Or *t\scale>1024.0 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  halfW=MathFFromInt(*m\width)* *t\scale/2.0 : halfH=MathFFromInt(*m\height)* *t\scale/2.0
  angle=*t\angle-MathFFromInt(MathFToI32(*t\angle/6.283185307))*6.283185307
  *out\cosine=Cos(angle) : *out\sine=Sin(angle)
  *out\cx=*t\x+halfW : *out\cy=*t\y+halfH
  ex=Abs(*out\cosine)*halfW+Abs(*out\sine)*halfH : ey=Abs(*out\sine)*halfW+Abs(*out\cosine)*halfH
  *out\left=*out\cx-ex : *out\right=*out\cx+ex : *out\top=*out\cy-ey : *out\bottom=*out\cy+ey
  ProcedureReturn 0
EndProcedure
Procedure.i ncoFloor(v.f)
  Protected i.i=MathFToI32(v)
  If MathFFromInt(i)>v : i=i-1 : EndIf
  ProcedureReturn i
EndProcedure
Procedure.i ncoCeil(v.f)
  Protected i.i=MathFToI32(v)
  If MathFFromInt(i)<v : i=i+1 : EndIf
  ProcedureReturn i
EndProcedure
Procedure.i ncoSolid(*m.NeonCollisionMask,*t.NeonCollisionTransform,*b.NeonCollisionBounds,x.f,y.f)
  Protected dx.f=x-*b\cx,dy.f=y-*b\cy,lx.f,ly.f,ix.i,iy.i
  lx=(dx* *b\cosine+dy* *b\sine)/ *t\scale+MathFFromInt(*m\width)/2.0
  ly=(dy* *b\cosine-dx* *b\sine)/ *t\scale+MathFFromInt(*m\height)/2.0
  If lx<0.0 Or ly<0.0 Or lx>=MathFFromInt(*m\width) Or ly>=MathFFromInt(*m\height) : ProcedureReturn 0 : EndIf
  ix=MathFToI32(lx) : iy=MathFToI32(ly)
  ProcedureReturn Bool(PeekA(*m\data+iy* *m\stride+ix)<>0)
EndProcedure
; Shared world-pixel centre samples, bounded by caller's explicit work budget.
Procedure.i NeonCollisionPixel(*a.NeonCollisionMask,*at.NeonCollisionTransform,*b.NeonCollisionMask,*bt.NeonCollisionTransform,maxSamples.i)
  Protected aa.NeonCollisionBounds,bb.NeonCollisionBounds,rc.i,l.f,t.f,r.f,bottom.f,x.i,y.i,left.i,top.i,right.i,last.i,w.i,h.i
  If maxSamples<1 Or maxSamples>16777216 : ProcedureReturn #NCO_ERR_ARGS : EndIf
  rc=ncoBounds(*a,*at,@aa) : If rc<>0 : ProcedureReturn rc : EndIf
  rc=ncoBounds(*b,*bt,@bb) : If rc<>0 : ProcedureReturn rc : EndIf
  l=aa\left : If bb\left>l : l=bb\left : EndIf
  t=aa\top : If bb\top>t : t=bb\top : EndIf
  r=aa\right : If bb\right<r : r=bb\right : EndIf
  bottom=aa\bottom : If bb\bottom<bottom : bottom=bb\bottom : EndIf
  If l>=r Or t>=bottom : ProcedureReturn 0 : EndIf
  left=ncoFloor(l) : top=ncoFloor(t) : right=ncoCeil(r)-1 : last=ncoCeil(bottom)-1
  w=right-left+1 : h=last-top+1
  If w>maxSamples/h : ProcedureReturn #NCO_ERR_BUDGET : EndIf
  For y=top To last
    For x=left To right
      If ncoSolid(*a,*at,@aa,MathFFromInt(x)+0.5,MathFFromInt(y)+0.5)<>0
        If ncoSolid(*b,*bt,@bb,MathFFromInt(x)+0.5,MathFFromInt(y)+0.5)<>0 : ProcedureReturn 1 : EndIf
      EndIf
    Next
  Next
  ProcedureReturn 0
EndProcedure
