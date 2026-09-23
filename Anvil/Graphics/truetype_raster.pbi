; T4 bounded monochrome-outline to 8-bit grayscale coverage rasterizer.
; Four-by-four area sampling over 16.16 fixed-point contour edges. Caller
; supplies the output bytes; no framebuffer or Vulkan dependency exists here.

#ANVIL_TTR_E_NONE = 0
#ANVIL_TTR_E_NOT_OPEN = 1
#ANVIL_TTR_E_ARGUMENT = 2
#ANVIL_TTR_E_GLYPH = 3
#ANVIL_TTR_E_CAPACITY = 4
#ANVIL_TTR_E_COMPLEX = 5
#ANVIL_TTR_MAX_PIXELS = 1024
#ANVIL_TTR_MAX_POINTS = 4096
#ANVIL_TTR_MAX_CONTOURS = 2048
#ANVIL_TTR_MAX_EDGES = 16384

Global anvil_ttr_error.i
Global anvil_ttr_count.i
Global anvil_ttr_edges.i
Global anvil_ttr_revision.i
Global *anvil_ttr_alpha_handler = 0
Global Dim anvil_ttr_points.a[#ANVIL_TTR_MAX_POINTS*12]
Global Dim anvil_ttr_contours.i[#ANVIL_TTR_MAX_CONTOURS]
Global Dim anvil_ttr_x1.i[#ANVIL_TTR_MAX_EDGES]
Global Dim anvil_ttr_y1.i[#ANVIL_TTR_MAX_EDGES]
Global Dim anvil_ttr_x2.i[#ANVIL_TTR_MAX_EDGES]
Global Dim anvil_ttr_y2.i[#ANVIL_TTR_MAX_EDGES]
Global Dim anvil_ttr_intersections.q[#ANVIL_TTR_MAX_EDGES]
Global Dim anvil_ttr_winding.i[#ANVIL_TTR_MAX_EDGES]

Procedure.q anvil_ttr_FloorDiv(value.q,divisor.q)
  If value<0 : ProcedureReturn -((-value+divisor-1)/divisor) : EndIf
  ProcedureReturn value/divisor
EndProcedure
Procedure.q anvil_ttr_CeilDiv(value.q,divisor.q)
  If value>0 : ProcedureReturn (value+divisor-1)/divisor : EndIf
  ProcedureReturn -((-value)/divisor)
EndProcedure
Procedure.i anvil_ttr_AddEdge(x1.i,y1.i,x2.i,y2.i)
  If anvil_ttr_edges>=#ANVIL_TTR_MAX_EDGES : ProcedureReturn 0 : EndIf
  anvil_ttr_x1[anvil_ttr_edges]=x1 : anvil_ttr_y1[anvil_ttr_edges]=y1
  anvil_ttr_x2[anvil_ttr_edges]=x2 : anvil_ttr_y2[anvil_ttr_edges]=y2
  anvil_ttr_edges+1 : ProcedureReturn 1
EndProcedure
Procedure.i anvil_ttr_Line(x1.i,y1.i,x2.i,y2.i)
  ProcedureReturn anvil_ttr_AddEdge(x1,y1,x2,y2)
EndProcedure
Procedure.i anvil_ttr_Quad(x0.i,y0.i,qx.i,qy.i,x2.i,y2.i)
  Protected t.i, steps.i=1, prevX.i=x0, prevY.i=y0, nextX.i, nextY.i, u.i
  Protected flatness.q, xx.q, yy.q, denominator.q
  xx=x0-2*qx+x2 : yy=y0-2*qy+y2
  If xx<0 : xx=-xx : EndIf
  If yy<0 : yy=-yy : EndIf
  flatness=xx : If yy>flatness : flatness=yy : EndIf
  ; For N equal quadratic pieces the maximum chord error is bounded by
  ; |P0 - 2Q + P2| / (4*N^2). Keep it below one eighth pixel.
  While flatness>32768*steps*steps And steps<64 : steps*2 : Wend
  If flatness>32768*steps*steps : ProcedureReturn 0 : EndIf
  denominator=steps*steps
  For t=1 To steps
    u=steps-t
    nextX=((u*u*x0)+(2*u*t*qx)+(t*t*x2))/denominator
    nextY=((u*u*y0)+(2*u*t*qy)+(t*t*y2))/denominator
    If anvil_ttr_AddEdge(prevX,prevY,nextX,nextY)=0 : ProcedureReturn 0 : EndIf
    prevX=nextX : prevY=nextY
  Next
  ProcedureReturn 1
EndProcedure
Procedure.i anvil_ttr_PointX(index.i)
  ProcedureReturn PeekL(@anvil_ttr_points[index*12])
EndProcedure
Procedure.i anvil_ttr_PointY(index.i)
  ProcedureReturn PeekL(@anvil_ttr_points[index*12+4])
EndProcedure
Procedure.i anvil_ttr_On(index.i)
  ProcedureReturn PeekL(@anvil_ttr_points[index*12+8])&1
EndProcedure
Procedure.q anvil_ttr_Mid16(a.q,b.q)
  ProcedureReturn (a+b)/2
EndProcedure

; Transform one contour into bounded fixed-pixel edges, preserving TrueType's
; implied on-curve midpoint between consecutive off-curve control points.
Procedure.i anvil_ttr_Contour(first.i,last.i,left.i,top.i,pixelHeight.i,units.i)
  Protected p.i, nextPoint.i, currentX.i, currentY.i
  Protected fx.i,fy.i,prevX.i,prevY.i
  Protected startX.q,startY.q,x.q,y.q,qx.q,qy.q,nx.q,ny.q,scale.q
  scale=pixelHeight
  If anvil_ttr_On(first)
    startX=anvil_ttr_PointX(first)<<16 : startY=anvil_ttr_PointY(first)<<16
    p=first
  ElseIf anvil_ttr_On(last)
    startX=anvil_ttr_PointX(last)<<16 : startY=anvil_ttr_PointY(last)<<16
    p=first
  Else
    startX=(anvil_ttr_PointX(first)+anvil_ttr_PointX(last))<<15
    startY=(anvil_ttr_PointY(first)+anvil_ttr_PointY(last))<<15
    p=first
  EndIf
  currentX=anvil_ttr_FloorDiv(startX*scale,units)-(left<<16)
  currentY=(top<<16)-anvil_ttr_FloorDiv(startY*scale,units)
  While p<=last
    x=anvil_ttr_PointX(p)<<16 : y=anvil_ttr_PointY(p)<<16
    If anvil_ttr_On(p)
      fx=anvil_ttr_FloorDiv(x*scale,units)-(left<<16)
      fy=(top<<16)-anvil_ttr_FloorDiv(y*scale,units)
      If anvil_ttr_Line(currentX,currentY,fx,fy)=0 : ProcedureReturn 0 : EndIf
      currentX=fx : currentY=fy : p+1
    Else
      qx=anvil_ttr_FloorDiv(x*scale,units)-(left<<16)
      qy=(top<<16)-anvil_ttr_FloorDiv(y*scale,units)
      nextPoint=p+1 : If nextPoint>last : nextPoint=first : EndIf
      If anvil_ttr_On(nextPoint)
        nx=anvil_ttr_PointX(nextPoint)<<16 : ny=anvil_ttr_PointY(nextPoint)<<16
        fx=anvil_ttr_FloorDiv(nx*scale,units)-(left<<16)
        fy=(top<<16)-anvil_ttr_FloorDiv(ny*scale,units)
        If anvil_ttr_Quad(currentX,currentY,qx,qy,fx,fy)=0 : ProcedureReturn 0 : EndIf
        currentX=fx : currentY=fy
        If nextPoint=first : p=last+1 : Else : p=nextPoint+1 : EndIf
      Else
        nx=anvil_ttr_Mid16(x,anvil_ttr_PointX(nextPoint)<<16)
        ny=anvil_ttr_Mid16(y,anvil_ttr_PointY(nextPoint)<<16)
        fx=anvil_ttr_FloorDiv(nx*scale,units)-(left<<16)
        fy=(top<<16)-anvil_ttr_FloorDiv(ny*scale,units)
        If anvil_ttr_Quad(currentX,currentY,qx,qy,fx,fy)=0 : ProcedureReturn 0 : EndIf
        currentX=fx : currentY=fy
        If nextPoint=first : p=last+1 : Else : p+1 : EndIf
      EndIf
    EndIf
  Wend
  If currentX<>anvil_ttr_FloorDiv(startX*scale,units)-(left<<16) Or currentY<>(top<<16)-anvil_ttr_FloorDiv(startY*scale,units)
    If anvil_ttr_Line(currentX,currentY,anvil_ttr_FloorDiv(startX*scale,units)-(left<<16),(top<<16)-anvil_ttr_FloorDiv(startY*scale,units))=0 : ProcedureReturn 0 : EndIf
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure.i anvil_ttr_SortIntersections(count.i)
  Protected gap.i, n.i, j.i, x.q, w.i
  gap=count/2
  While gap>0
    For n=gap To count-1
      x=anvil_ttr_intersections[n] : w=anvil_ttr_winding[n] : j=n
      While j>=gap
        If anvil_ttr_intersections[j-gap]<=x : Break : EndIf
        anvil_ttr_intersections[j]=anvil_ttr_intersections[j-gap]
        anvil_ttr_winding[j]=anvil_ttr_winding[j-gap] : j-gap
      Wend
      anvil_ttr_intersections[j]=x : anvil_ttr_winding[j]=w
    Next
    gap=gap/2
  Wend
  ProcedureReturn 1
EndProcedure

; Install an optional trusted converter; zero always selects scalar.
Procedure.i AnvilTrueTypeRasterAlphaHandlerSet(*handler)
  *anvil_ttr_alpha_handler=*handler
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeCoverageCountsToAlpha(buffer.i,pixelCount.i,capacity.i)
  Protected n.i, value.i
  If pixelCount<0 Or capacity<pixelCount Or (pixelCount>0 And buffer=0)
    ProcedureReturn 0
  EndIf
  If *anvil_ttr_alpha_handler<>0
    ProcedureReturn anvil_ttr_alpha_handler(buffer,pixelCount,capacity)
  EndIf
  For n=0 To pixelCount-1
    value=PeekA(buffer+n)&$FF
    If value>16 : ProcedureReturn 0 : EndIf
  Next
  For n=0 To pixelCount-1
    value=PeekA(buffer+n)&$FF
    PokeA(buffer+n,(value*255+8)/16)
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i AnvilTrueTypeRasterizeGlyph(glyph.i,pixelHeight.i,coverage.i,capacity.i,widthOut.i,heightOut.i,strideOut.i,bearingXOut.i,bearingYOut.i,advanceOut.i)
  Protected points.i, contours.i, pointCount.i=0, contourCount.i=0
  Protected n.i, c.i, first.i, last.i, xMin.i, xMax.i, yMin.i, yMax.i
  Protected units.i, width.i, height.i, stride.i, left.i, top.i, advance.i, lsb.i
  Protected scaledMinX.q, scaledMaxX.q, scaledMinY.q, scaledMaxY.q
  Protected subY.i, subX.i, edge.i, hitCount.i, dir.i, winding.i, hit.i
  Protected sampleY.q, ix.q, xSample.q, pixel.i, value.i
  If AnvilTrueTypeOutlinesOpenState()=0 Or AnvilTrueTypeMetricsOpenState()=0
    anvil_ttr_error=#ANVIL_TTR_E_NOT_OPEN : ProcedureReturn 0
  EndIf
  If widthOut=0 Or heightOut=0 Or strideOut=0 Or bearingXOut=0 Or bearingYOut=0 Or advanceOut=0 Or pixelHeight<1 Or pixelHeight>512
    anvil_ttr_error=#ANVIL_TTR_E_ARGUMENT : ProcedureReturn 0
  EndIf
  If glyph<0 Or glyph>=AnvilTrueTypeGlyphCount() : anvil_ttr_error=#ANVIL_TTR_E_GLYPH : ProcedureReturn 0 : EndIf
  If AnvilTrueTypeGlyphOutline(glyph,@anvil_ttr_points[0],#ANVIL_TTR_MAX_POINTS,@anvil_ttr_contours[0],#ANVIL_TTR_MAX_CONTOURS,@pointCount,@contourCount)=0
    anvil_ttr_error=#ANVIL_TTR_E_COMPLEX : ProcedureReturn 0
  EndIf
  If AnvilTrueTypeHorizontalMetric(glyph,@advance,@lsb)=0 : anvil_ttr_error=#ANVIL_TTR_E_GLYPH : ProcedureReturn 0 : EndIf
  units=AnvilTrueTypeUnitsPerEm()
  advance=(advance*pixelHeight+units/2)/units
  width=0 : height=0 : left=0 : top=0
  If pointCount>0
    xMin=anvil_ttr_PointX(0) : xMax=xMin : yMin=anvil_ttr_PointY(0) : yMax=yMin
    For n=1 To pointCount-1
      value=anvil_ttr_PointX(n) : If value<xMin : xMin=value : EndIf : If value>xMax : xMax=value : EndIf
      value=anvil_ttr_PointY(n) : If value<yMin : yMin=value : EndIf : If value>yMax : yMax=value : EndIf
    Next
    scaledMinX=anvil_ttr_FloorDiv(xMin*pixelHeight,units)
    scaledMaxX=anvil_ttr_CeilDiv(xMax*pixelHeight,units)
    scaledMinY=anvil_ttr_FloorDiv(yMin*pixelHeight,units)
    scaledMaxY=anvil_ttr_CeilDiv(yMax*pixelHeight,units)
    If scaledMinX<-2147483648 Or scaledMinX>2147483647 Or scaledMaxX<-2147483648 Or scaledMaxX>2147483647 Or scaledMinY<-2147483648 Or scaledMinY>2147483647 Or scaledMaxY<-2147483648 Or scaledMaxY>2147483647
      anvil_ttr_error=#ANVIL_TTR_E_COMPLEX : ProcedureReturn 0
    EndIf
    left=scaledMinX : top=scaledMaxY
    width=scaledMaxX-scaledMinX : height=scaledMaxY-scaledMinY
    If width<0 Or height<0 Or width>#ANVIL_TTR_MAX_PIXELS Or height>#ANVIL_TTR_MAX_PIXELS
      anvil_ttr_error=#ANVIL_TTR_E_COMPLEX : ProcedureReturn 0
    EndIf
    stride=width
  Else
    stride=0
  EndIf
  PokeI(widthOut,width) : PokeI(heightOut,height) : PokeI(strideOut,stride)
  PokeI(bearingXOut,left) : PokeI(bearingYOut,top) : PokeI(advanceOut,advance)
  If width=0 Or height=0
    anvil_ttr_error=#ANVIL_TTR_E_NONE : anvil_ttr_count+1 : anvil_ttr_revision=AnvilTrueTypeRevision()
    ProcedureReturn 1
  EndIf
  If coverage=0 Or capacity<width*height : anvil_ttr_error=#ANVIL_TTR_E_CAPACITY : ProcedureReturn 0 : EndIf
  For n=0 To width*height-1 : PokeA(coverage+n,0) : Next
  anvil_ttr_edges=0 : first=0
  For c=0 To contourCount-1
    last=PeekL(@anvil_ttr_contours[0]+c*4)
    If last<first Or last>=pointCount : anvil_ttr_error=#ANVIL_TTR_E_COMPLEX : ProcedureReturn 0 : EndIf
    If anvil_ttr_Contour(first,last,left,top,pixelHeight,units)=0 : anvil_ttr_error=#ANVIL_TTR_E_COMPLEX : ProcedureReturn 0 : EndIf
    first=last+1
  Next
  If first<>pointCount : anvil_ttr_error=#ANVIL_TTR_E_COMPLEX : ProcedureReturn 0 : EndIf
  For subY=0 To height*4-1
    sampleY=subY*16384+8192 : hitCount=0
    For edge=0 To anvil_ttr_edges-1
      If (anvil_ttr_y1[edge]<=sampleY And sampleY<anvil_ttr_y2[edge]) Or (anvil_ttr_y2[edge]<=sampleY And sampleY<anvil_ttr_y1[edge])
        If anvil_ttr_y2[edge]>anvil_ttr_y1[edge] : dir=1 : Else : dir=-1 : EndIf
        ix=anvil_ttr_x1[edge]+((sampleY-anvil_ttr_y1[edge])*(anvil_ttr_x2[edge]-anvil_ttr_x1[edge]))/(anvil_ttr_y2[edge]-anvil_ttr_y1[edge])
        anvil_ttr_intersections[hitCount]=ix : anvil_ttr_winding[hitCount]=dir : hitCount+1
      EndIf
    Next
    anvil_ttr_SortIntersections(hitCount) : winding=0 : hit=0
    For subX=0 To width*4-1
      xSample=subX*16384+8192
      While hit<hitCount
        If anvil_ttr_intersections[hit]>xSample : Break : EndIf
        winding+anvil_ttr_winding[hit] : hit+1
      Wend
      If winding<>0
        pixel=(subY/4)*stride+(subX/4)
        PokeA(coverage+pixel,(PeekA(coverage+pixel)&$FF)+1)
      EndIf
    Next
  Next
  If AnvilTrueTypeCoverageCountsToAlpha(coverage,width*height,capacity)=0
    anvil_ttr_error=#ANVIL_TTR_E_COMPLEX : ProcedureReturn 0
  EndIf
  anvil_ttr_error=#ANVIL_TTR_E_NONE : anvil_ttr_count+1
  anvil_ttr_revision=AnvilTrueTypeRevision()
  ProcedureReturn 1
EndProcedure
Procedure.i AnvilTrueTypeRasterError()
  ProcedureReturn anvil_ttr_error
EndProcedure
Procedure.i AnvilTrueTypeRasterCount()
  ProcedureReturn anvil_ttr_count
EndProcedure
Procedure.i AnvilTrueTypeRasterCountReset()
  anvil_ttr_count=0 : ProcedureReturn 1
EndProcedure
