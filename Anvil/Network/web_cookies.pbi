; Bounded HTTP cookie storage, RFC 6265 sections 5.1-5.4.
; SameSite and prefix policy follows draft-ietf-httpbis-rfc6265bis-22 (draft).
; No hidden global jar, persistence or clock. Caller supplies trusted Unix time,
; request site context and a public-suffix-aware domain authorization callback.
; Without that callback, only host-only scope is accepted (an equal Domain is
; narrowed to host-only). Partitioned cookies are explicitly unsupported.
XIncludeFile "Anvil/Network/web_request.pbi"
XIncludeFile "Anvil/Network/web_cookie_date.pbi"
#WEB_COOKIE_ARGUMENT=-660
#WEB_COOKIE_SYNTAX=-661
#WEB_COOKIE_LIMIT=-662
#WEB_COOKIE_SCOPE=-663
#WEB_COOKIE_UNSUPPORTED=-664
#WEB_COOKIE_STRIDE=3584
#WEB_COOKIE_NAME=96
#WEB_COOKIE_VALUE=224
#WEB_COOKIE_DOMAIN=2272
#WEB_COOKIE_PATH=2528
Structure WebCookies
 storage.i
 slots.i
 serial.i
 domainPolicy.i
EndStructure
Procedure wckWipe(p.i,n.i)
 Define i.i
 For i=0 To n-1 : PokeA(p+i,0) : Next
EndProcedure
Procedure.i wckEqual(a.i,an.i,b.i,bn.i,lower.i)
 Define i.i,x.i,y.i
 If an<>bn : ProcedureReturn 0 : EndIf
 For i=0 To an-1
  x=PeekA(a+i) & 255 : y=PeekA(b+i) & 255
  If lower : x=webUrlLower(x) : y=webUrlLower(y) : EndIf
  If x<>y : ProcedureReturn 0 : EndIf
 Next
 ProcedureReturn 1
EndProcedure
Procedure.i wckDomain(host.i,hn.i,domain.i,dn.i,hostOnly.i)
 Define i.i,numeric.i
 If wckEqual(host,hn,domain,dn,1) : ProcedureReturn 1 : EndIf
 If hostOnly Or hn<=dn : ProcedureReturn 0 : EndIf
 numeric=1
 For i=0 To hn-1
  If (PeekA(host+i)<48 Or PeekA(host+i)>57) And PeekA(host+i)<>46 : numeric=0 : EndIf
 Next
 If numeric Or PeekA(host+hn-dn-1)<>46 : ProcedureReturn 0 : EndIf
 ProcedureReturn wckEqual(host+hn-dn,dn,domain,dn,1)
EndProcedure
Procedure.i wckPath(path.i,pn.i,target.i,tn.i)
 If tn<pn : ProcedureReturn 0 : EndIf
 If wckEqual(path,pn,target,pn,0)=0 : ProcedureReturn 0 : EndIf
 If tn=pn Or PeekA(path+pn-1)=47 : ProcedureReturn 1 : EndIf
 ProcedureReturn Bool(PeekA(target+pn)=47 Or PeekA(target+pn)=63)
EndProcedure
Procedure.i WebCookiesInit(*jar.WebCookies,storage.i,slots.i,domainPolicy.i)
 If *jar=0 Or storage=0 Or slots<1 Or slots>64 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 *jar\storage=storage : *jar\slots=slots : *jar\serial=0 : *jar\domainPolicy=domainPolicy
 wckWipe(storage,slots*#WEB_COOKIE_STRIDE) : ProcedureReturn 0
EndProcedure
Procedure.i WebCookiesClear(*jar.WebCookies)
 If *jar=0 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 If *jar\storage=0 Or *jar\slots<1 Or *jar\slots>64 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 wckWipe(*jar\storage,*jar\slots*#WEB_COOKIE_STRIDE) : *jar\serial=0 : ProcedureReturn 0
EndProcedure
Procedure.i WebCookieStore(*jar.WebCookies,*url.WebUrl,field.i,bytes.i,now.i)
 Define i.i,j.i,c.i,end.i,eq.i,start.i,finish.i,at.i,an.i,av.i,vn.i,name.i,nn.i,value.i,nv.i,domain.i,dn.i,path.i,pn.i,hostOnly.i,domainSeen.i,pathSeen.i,secure.i,httpOnly.i,sameSite.i,expiry.i,age.i,ageSeen.i,negative.i,valid.i,slot.i,free.i,p.i,serial.i,*policy
 If *jar=0 Or *url=0 Or field=0 Or bytes<1 Or bytes>8192 Or now<0 Or now>253402300799 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 If *jar\storage=0 Or *jar\slots<1 Or *jar\slots>64 Or *url\host=0 Or *url\hostLength<1 Or *url\hostLength>253 Or *url\target=0 Or *url\targetLength<1 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 For i=0 To bytes-1
  c=PeekA(field+i) & 255
  If c<32 And c<>9 : ProcedureReturn #WEB_COOKIE_SYNTAX : EndIf
  If c=127 Or c>=128 : ProcedureReturn #WEB_COOKIE_SYNTAX : EndIf
 Next
 end=0 : While end<bytes : If PeekA(field+end)=59 : Break : EndIf : end=end+1 : Wend
 eq=-1
 For i=0 To end-1 : If PeekA(field+i)=61 : eq=i : Break : EndIf : Next
 If eq<0 : ProcedureReturn #WEB_COOKIE_SYNTAX : EndIf
 start=0 : finish=eq
 While start<finish
  If PeekA(field+start)<>32 And PeekA(field+start)<>9 : Break : EndIf
  start=start+1
 Wend
 While finish>start
  If PeekA(field+finish-1)<>32 And PeekA(field+finish-1)<>9 : Break : EndIf
  finish=finish-1
 Wend
 name=field+start : nn=finish-start
 start=eq+1 : finish=end
 While start<finish
  If PeekA(field+start)<>32 And PeekA(field+start)<>9 : Break : EndIf
  start=start+1
 Wend
 While finish>start
  If PeekA(field+finish-1)<>32 And PeekA(field+finish-1)<>9 : Break : EndIf
  finish=finish-1
 Wend
 value=field+start : nv=finish-start
 If nn<1 Or nn>128 Or nv>2048 : ProcedureReturn #WEB_COOKIE_LIMIT : EndIf
 For i=0 To nn-1 : If wqToken(PeekA(name+i) & 255)=0 : ProcedureReturn #WEB_COOKIE_SYNTAX : EndIf : Next
 For i=0 To nv-1
  c=PeekA(value+i) & 255
  If c=34 And nv>=2 And (i=0 Or i=nv-1) And PeekA(value)=34 And PeekA(value+nv-1)=34 : Continue : EndIf
  If c<33 Or c=34 Or c=44 Or c=59 Or c=92 : ProcedureReturn #WEB_COOKIE_SYNTAX : EndIf
 Next
 domain=*url\host : dn=*url\hostLength : hostOnly=1 : expiry=-1 : sameSite=1
 path=*url\target : pn=1
 For i=1 To *url\targetLength-1
  c=PeekA(path+i) : If c=63 : Break : EndIf
  If c=47 : pn=i : EndIf
 Next
 at=end+1
 While at<bytes
  end=at : While end<bytes : If PeekA(field+end)=59 : Break : EndIf : end=end+1 : Wend
  start=at : finish=end
  While start<finish
   If PeekA(field+start)<>32 And PeekA(field+start)<>9 : Break : EndIf
   start=start+1
  Wend
  While finish>start
   If PeekA(field+finish-1)<>32 And PeekA(field+finish-1)<>9 : Break : EndIf
   finish=finish-1
  Wend
  eq=start : While eq<finish : If PeekA(field+eq)=61 : Break : EndIf : eq=eq+1 : Wend
  an=eq-start
  While an>0
   If PeekA(field+start+an-1)<>32 And PeekA(field+start+an-1)<>9 : Break : EndIf
   an=an-1
  Wend
  av=eq+1 : If av>finish : av=finish : EndIf
  While av<finish
   If PeekA(field+av)<>32 And PeekA(field+av)<>9 : Break : EndIf
   av=av+1
  Wend
  vn=finish-av
  If wqEqual(field+start,an,"secure")
   secure=1
  ElseIf wqEqual(field+start,an,"httponly")
   httpOnly=1
  ElseIf wqEqual(field+start,an,"partitioned")
   ProcedureReturn #WEB_COOKIE_UNSUPPORTED
  ElseIf wqEqual(field+start,an,"domain")
   If vn>0
    domainSeen=1 : domain=field+av : dn=vn
    If PeekA(domain)=46 : domain=domain+1 : dn=dn-1 : EndIf
   EndIf
  ElseIf wqEqual(field+start,an,"path")
   If vn>0
    If PeekA(field+av)=47 : path=field+av : pn=vn : pathSeen=1 : EndIf
   EndIf
  ElseIf wqEqual(field+start,an,"samesite")
   sameSite=1
   If wqEqual(field+av,vn,"strict") : sameSite=2 : ElseIf wqEqual(field+av,vn,"none") : sameSite=0 : EndIf
  ElseIf wqEqual(field+start,an,"expires")
   j=WebCookieDate(field+av,vn)
   If j<>#WEB_COOKIE_DATE_INVALID : expiry=j : If expiry<0 : expiry=0 : EndIf : EndIf
  ElseIf wqEqual(field+start,an,"max-age")
   j=0 : negative=0 : valid=1 : age=0
   If vn=0 : valid=0 : ElseIf PeekA(field+av)=45 : negative=1 : j=1 : If vn=1 : valid=0 : EndIf : EndIf
   While j<vn
    c=PeekA(field+av+j) & 255
    If c<48 Or c>57 : valid=0 : Break : EndIf
    If age<253402300799 : age=age*10+c-48 : If age>253402300799 : age=253402300799 : EndIf : EndIf
    j=j+1
   Wend
   If valid
    ageSeen=1
    If negative Or age=0 : age=0 : Else : age=now+age : If age>253402300799 : age=253402300799 : EndIf : EndIf
    serial=age
   EndIf
  EndIf
  at=end+1
 Wend
 If ageSeen : expiry=serial : EndIf
 If dn<1 Or dn>253 Or pn<1 Or pn>1024 : ProcedureReturn #WEB_COOKIE_LIMIT : EndIf
 If domainSeen
  If wckDomain(*url\host,*url\hostLength,domain,dn,0)=0 : ProcedureReturn #WEB_COOKIE_SCOPE : EndIf
  If *jar\domainPolicy=0
   If wckEqual(*url\host,*url\hostLength,domain,dn,1)=0 : ProcedureReturn #WEB_COOKIE_SCOPE : EndIf
  Else
   *policy=*jar\domainPolicy
   If policy(domain,dn)<>1 : ProcedureReturn #WEB_COOKIE_SCOPE : EndIf
   hostOnly=0
  EndIf
 EndIf
 If secure And *url\secure=0 : ProcedureReturn #WEB_COOKIE_SCOPE : EndIf
 If sameSite=0 And secure=0 : ProcedureReturn #WEB_COOKIE_SCOPE : EndIf
 If nn>=9
  If wckEqual(name,9,"__Secure-",9,1) And secure=0 : ProcedureReturn #WEB_COOKIE_SCOPE : EndIf
 EndIf
 If nn>=7
  If wckEqual(name,7,"__Host-",7,1)
   If secure=0 Or domainSeen Or pathSeen=0 Or pn<>1 Or PeekA(path)<>47 : ProcedureReturn #WEB_COOKIE_SCOPE : EndIf
  EndIf
 EndIf
 slot=-1 : free=-1
 For i=0 To *jar\slots-1
  p=*jar\storage+i*#WEB_COOKIE_STRIDE
  If PeekI(p)>0 And PeekI(p+8)<>-1 And PeekI(p+8)<=now : wckWipe(p,#WEB_COOKIE_STRIDE) : EndIf
  If PeekI(p)=0
   If free<0 : free=i : EndIf
  ElseIf wckEqual(name,nn,p+#WEB_COOKIE_NAME,PeekI(p+16),0)
   If *url\secure=0 And PeekI(p+56) And (wckDomain(domain,dn,p+#WEB_COOKIE_DOMAIN,PeekI(p+32),0) Or wckDomain(p+#WEB_COOKIE_DOMAIN,PeekI(p+32),domain,dn,0)) And wckPath(p+#WEB_COOKIE_PATH,PeekI(p+40),path,pn)
    ProcedureReturn #WEB_COOKIE_SCOPE
   EndIf
   If wckEqual(domain,dn,p+#WEB_COOKIE_DOMAIN,PeekI(p+32),1) And wckEqual(path,pn,p+#WEB_COOKIE_PATH,PeekI(p+40),0) : slot=i : EndIf
  EndIf
 Next
 If expiry<>-1 And expiry<=now
  If slot>=0 : wckWipe(*jar\storage+slot*#WEB_COOKIE_STRIDE,#WEB_COOKIE_STRIDE) : EndIf
  ProcedureReturn 0
 EndIf
 serial=0
 If slot>=0 : serial=PeekI(*jar\storage+slot*#WEB_COOKIE_STRIDE) : Else : slot=free : EndIf
 If slot<0 Or *jar\serial=$7FFFFFFF : ProcedureReturn #WEB_COOKIE_LIMIT : EndIf
 p=*jar\storage+slot*#WEB_COOKIE_STRIDE : wckWipe(p,#WEB_COOKIE_STRIDE)
 If serial=0 : *jar\serial=*jar\serial+1 : serial=*jar\serial : EndIf
 PokeI(p,serial) : PokeI(p+8,expiry) : PokeI(p+16,nn) : PokeI(p+24,nv) : PokeI(p+32,dn) : PokeI(p+40,pn)
 PokeI(p+48,hostOnly) : PokeI(p+56,secure) : PokeI(p+64,sameSite) : PokeI(p+72,httpOnly)
 For i=0 To nn-1 : PokeA(p+#WEB_COOKIE_NAME+i,PeekA(name+i)) : Next
 For i=0 To nv-1 : PokeA(p+#WEB_COOKIE_VALUE+i,PeekA(value+i)) : Next
 For i=0 To dn-1 : PokeA(p+#WEB_COOKIE_DOMAIN+i,webUrlLower(PeekA(domain+i) & 255)) : Next
 For i=0 To pn-1 : PokeA(p+#WEB_COOKIE_PATH+i,PeekA(path+i)) : Next
 ProcedureReturn 0
EndProcedure

; sameSite is explicit request context; topLevelSafe permits Lax cookies on a
; safe top-level navigation. This HTTP API may send HttpOnly cookies.
; Measure with dst=0/capacity=0. Short output is refused before any output write.
Procedure.i WebCookieHeader(*jar.WebCookies,*url.WebUrl,now.i,sameSite.i,topLevelSafe.i,dst.i,capacity.i)
 Define i.i,j.i,p.i,n.i,count.i,pass.i,best.i,bestLength.i,bestSerial.i,previousLength.i,previousSerial.i,length.i,serial.i,eligible.i
 If *jar=0 Or *url=0 Or now<0 Or now>253402300799 Or capacity<0 Or (capacity>0 And dst=0) Or sameSite<0 Or sameSite>1 Or topLevelSafe<0 Or topLevelSafe>1 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 If *jar\storage=0 Or *jar\slots<1 Or *jar\slots>64 Or *url\host=0 Or *url\target=0 Or *url\hostLength<1 Or *url\targetLength<1 : ProcedureReturn #WEB_COOKIE_ARGUMENT : EndIf
 For pass=0 To 1
  previousLength=1025 : previousSerial=0 : n=0 : count=0
  While count<*jar\slots
   best=0 : bestLength=-1 : bestSerial=$7FFFFFFF
   For i=0 To *jar\slots-1
    p=*jar\storage+i*#WEB_COOKIE_STRIDE : serial=PeekI(p) : length=PeekI(p+40)
    eligible=Bool(serial>0 And (PeekI(p+8)=-1 Or PeekI(p+8)>now))
    If PeekI(p+56) And *url\secure=0 : eligible=0 : EndIf
    If sameSite=0 And (PeekI(p+64)=2 Or (PeekI(p+64)=1 And topLevelSafe=0)) : eligible=0 : EndIf
    If length>previousLength Or (length=previousLength And serial<=previousSerial) : eligible=0 : EndIf
    If eligible
     If wckDomain(*url\host,*url\hostLength,p+#WEB_COOKIE_DOMAIN,PeekI(p+32),PeekI(p+48))=0 Or wckPath(p+#WEB_COOKIE_PATH,length,*url\target,*url\targetLength)=0 : eligible=0 : EndIf
    EndIf
    If eligible And (length>bestLength Or (length=bestLength And serial<bestSerial)) : best=p : bestLength=length : bestSerial=serial : EndIf
   Next
   If best=0 : Break : EndIf
   If pass=0
    If count>0 : n=n+2 : EndIf
    n=n+PeekI(best+16)+1+PeekI(best+24)
   Else
    If count>0 : PokeA(dst+n,59) : PokeA(dst+n+1,32) : n=n+2 : EndIf
    For j=0 To PeekI(best+16)-1 : PokeA(dst+n,PeekA(best+#WEB_COOKIE_NAME+j)) : n=n+1 : Next
    PokeA(dst+n,61) : n=n+1
    For j=0 To PeekI(best+24)-1 : PokeA(dst+n,PeekA(best+#WEB_COOKIE_VALUE+j)) : n=n+1 : Next
   EndIf
   previousLength=bestLength : previousSerial=bestSerial : count=count+1
  Wend
  If pass=0
   If dst=0 And capacity=0 : ProcedureReturn n : EndIf
   If n>capacity : ProcedureReturn #WEB_COOKIE_LIMIT : EndIf
  EndIf
 Next
 ProcedureReturn n
EndProcedure
