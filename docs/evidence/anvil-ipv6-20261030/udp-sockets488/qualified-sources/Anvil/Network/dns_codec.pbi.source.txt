XIncludeFile "Anvil/Network/byte_order.pbi"
; ======================================================================
;  dns.pi4 - a DNS client, RFC 1035, the query-and-parse half only.
;
;  THE SAME CONTRACT tftp.pi4 AND net.pi4 STATE: this file does no input
;  and no output. It BUILDS a query into its own buffer and PARSES a
;  reply the caller hands it, and it does not know that genet.pi4 or
;  net.pi4 exist. Anvil runs the pump - DnsBuildQuery() then
;  NetUdpBuild() then GenetSend(), and GenetRecvWait() then NetInput()
;  then DnsParseReply() - exactly as it does for TFTP. The price is the
;  same and it buys the same thing: a codec that can be checked with
;  byte-exact vectors and no device underneath.
;
;  WHAT IT DOES AND DOES NOT DO.
;    * Typed queries support A and AAAA (RFC 3596 section 2). QCLASS=IN;
;      no MX, no CNAME chasing OF ITS OWN - though it DOES read through
;      the compression pointers a CNAME answer uses, so a name that is a
;      CNAME to a host with an A record resolves, because the server put
;      the A record in the same answer section. Only records belonging to
;      the question or its bounded CNAME chain are returned. DnsParseReplyFor
;      additionally binds the question to a caller-supplied host name.
;      DnsResultTtl reports the minimum lifetime of that chain and RRset.
;    * Recursion is REQUESTED (RD=1). A monitor talks to a real resolver
;      - the one DHCP handed us, or the one typed at `net dns` - and that
;      resolver does the walking. An authoritative-only server answering
;      RD=1 with its referral is reported honestly as "no address",
;      because there is no A record in the answer and this client does
;      not chase referrals.
;    * ONE QUESTION PER QUERY. RFC 1035 allows more in the packet format
;      but no real server answers more than one, so QDCOUNT is always 1.
;
;  THE COMPRESSION POINTER IS THE ONE THING THAT MUST BE RIGHT. A name
;  in an answer is very often a two-byte pointer (top two bits set) back
;  into the question, and a parser that reads it as a length byte walks
;  off into the rest of the packet and returns a plausible wrong address.
;  dns_SkipName() handles both forms and BOUNDS EVERY READ against the
;  datagram it was given - a length or a pointer that runs past the end
;  is a malformed reply, not a read into the next buffer.
;
;  ENDIANNESS: the 16- and 32-bit fields are big-endian on the wire and
;  use the shared byte_order.pbi NetReadBE16/NetReadBE32 API, which reads
;  one byte at a time most-significant first. An IPv4 address is held the
;  way the rest of this stack holds one - first octet in the most
;  significant byte - so DnsResultIp() feeds straight into PutIp().
; ======================================================================

; ---- sizes and constants [RFC 1035, uncited] ----
#DNS_PORT        = 53
#DNS_HDR         = 12         ; ID, flags, and the four count fields
#DNS_QTYPE_A     = 1          ; a host address
#DNS_QTYPE_AAAA  = 28         ; RFC 3596, 16 network-order address bytes
#DNS_QCLASS_IN   = 1          ; the Internet class
#DNS_TYPE_A      = 1
#DNS_TYPE_CNAME  = 5
#DNS_FLAG_RD     = $0100      ; recursion desired, in the query
#DNS_FLAG_QR     = $8000      ; set in a reply
#DNS_RCODE_MASK  = $000F
#DNS_MAX_NAME    = 255        ; the whole name, RFC 1035 s2.3.4
#DNS_MAX_LABEL   = 63         ; one label; also the pointer-flag boundary
#DNS_PTR_FLAG    = $C0        ; the top two bits mark a compression pointer
#DNS_OUT_MAX     = 300        ; header + a 255-byte name + type + class,
                             ; with room to spare
#DNS_MAX_RESULTS = 8          ; A records we will remember from one reply

; ---- the query buffer this file builds into ----
Global Dim dns_out.a[#DNS_OUT_MAX]
Global dns_outLen.i

; ---- what the last parsed reply yielded ----
Global Dim dns_ip.i[#DNS_MAX_RESULTS]
Global Dim dns_ip6.a[#DNS_MAX_RESULTS*16]
Global dns_resultType.i
Global dns_count.i            ; how many A records were found
Global dns_rcode.i            ; the reply's RCODE, 0 = no error
Global dns_err.i              ; the last refusal, a #DNS_E_*

; ---- refusals. All negative, all distinct. ----
#DNS_E_NONE      =    0
#DNS_E_ARG       = -200       ; a null name, or an empty one
#DNS_E_NAME_LONG = -201       ; the whole name is over 255 bytes
#DNS_E_LABEL     = -202       ; a label is empty or over 63 bytes
#DNS_E_SHORT     = -203       ; the reply is shorter than its own header
#DNS_E_ID        = -204       ; the reply's ID is not the query's
#DNS_E_NOT_REPLY = -205       ; the QR bit says this is a question
#DNS_E_RCODE     = -206       ; the server returned an error code
#DNS_E_MALFORMED = -207       ; a length or pointer runs past the end

; ----------------------------------------------------------------------
;  DnsBuildQuery - encode a query for `name`, tagged with `qid`.
;
;  Returns the query length, or 0 with dns_err set. The caller then
;  sends dns_out[0..len) as the payload of a UDP datagram to the DNS
;  server on port 53.
;
;  THE NAME IS VALIDATED AS IT IS ENCODED, not before, so there is one
;  walk of it and not two. A trailing dot is tolerated (the root label is
;  implicit and written as the terminating zero either way); a leading
;  dot, a double dot, an over-long label or an over-long name are all
;  refused, because each would produce a packet a server rejects and the
;  refusal here names which.
; ----------------------------------------------------------------------
Procedure.i DnsBuildQueryType(name.i, qid.i, qtype.i)
  Protected p.i
  Protected labelStart.i
  Protected i.i
  Protected c.i
  Protected labLen.i
  Protected total.i

  dns_err = #DNS_E_NONE
  dns_outLen = 0
  If qtype<>#DNS_QTYPE_A And qtype<>#DNS_QTYPE_AAAA
    dns_err=#DNS_E_ARG
    ProcedureReturn 0
  EndIf
  If name = 0
    dns_err = #DNS_E_ARG
    ProcedureReturn 0
  EndIf
  If PeekA(name) = 0
    dns_err = #DNS_E_ARG
    ProcedureReturn 0
  EndIf

  ; ---- the 12-byte header ----
  NetWriteBE16(@dns_out[0], qid & $FFFF)
  NetWriteBE16(@dns_out[2], #DNS_FLAG_RD)   ; RD, everything else zero
  NetWriteBE16(@dns_out[4], 1)              ; QDCOUNT, exactly one question
  NetWriteBE16(@dns_out[6], 0)              ; ANCOUNT
  NetWriteBE16(@dns_out[8], 0)              ; NSCOUNT
  NetWriteBE16(@dns_out[10], 0)             ; ARCOUNT

  ; ---- the QNAME, one length-prefixed label at a time ----
  p = #DNS_HDR
  i = 0
  total = 0
  labLen = 0
  labelStart = p
  p = p + 1                                ; leave room for the first
                                           ; label's length byte
  Repeat
    c = PeekA(name + i) & $FF
    If c = 46 Or c = 0                      ; 46 is a full stop
      If labLen = 0
        If c = 0
          ; A trailing dot, or the end after a dot we already closed:
          ; the root is written as the terminating zero below. But an
          ; EMPTY name, or "a..b", is a refusal.
          If i = 0
            dns_err = #DNS_E_ARG
            ProcedureReturn 0
          EndIf
          ; The final dot already reserved the root's length byte. Reuse
          ; it, rather than adding a second root and shifting QTYPE/QCLASS.
          p = labelStart
          Break
        EndIf
        ; c = 46 with no letters since the last dot: "a..b" or a leading
        ; dot. Refuse it rather than emit a zero-length label, which
        ; terminates a name early and would query the wrong thing.
        dns_err = #DNS_E_LABEL
        ProcedureReturn 0
      EndIf
      If labLen > #DNS_MAX_LABEL
        dns_err = #DNS_E_LABEL
        ProcedureReturn 0
      EndIf
      dns_out[labelStart] = labLen & $FF   ; back-fill the length byte
      total = total + labLen + 1
      If total > #DNS_MAX_NAME
        dns_err = #DNS_E_NAME_LONG
        ProcedureReturn 0
      EndIf
      If c = 0
        Break
      EndIf
      labelStart = p
      p = p + 1
      labLen = 0
    Else
      If labLen>=#DNS_MAX_LABEL
        dns_err=#DNS_E_LABEL : ProcedureReturn 0
      EndIf
      If total+labLen+3>#DNS_MAX_NAME
        dns_err=#DNS_E_NAME_LONG : ProcedureReturn 0
      EndIf
      dns_out[p] = c & $FF
      p = p + 1
      labLen = labLen + 1
    EndIf
    i = i + 1
  ForEver

  dns_out[p] = 0                            ; the root label ends the name
  p = p + 1
  NetWriteBE16(@dns_out[p], qtype)
  p = p + 2
  NetWriteBE16(@dns_out[p], #DNS_QCLASS_IN)
  p = p + 2

  dns_outLen = p
  ProcedureReturn p
EndProcedure

Procedure.i DnsBuildQuery(name.i,qid.i)
  ProcedureReturn DnsBuildQueryType(name,qid,#DNS_QTYPE_A)
EndProcedure

Procedure.i DnsQueryBuf()
  ProcedureReturn @dns_out[0]
EndProcedure

Procedure.i DnsQueryLen()
  ProcedureReturn dns_outLen
EndProcedure

; ----------------------------------------------------------------------
;  dns_SkipName - step over a name at `pos`, returning the offset of the
;  byte after it, or -1 if it runs off the end.
;
;  Two forms and both are handled. A compression pointer (top two bits
;  set) is two bytes and ENDS the name where it sits - we do not follow
;  it, because everything after a name is at a fixed offset from the
;  pointer, not from wherever it points. A sequence of length-prefixed
;  labels ends at a zero length byte. EVERY read is bounded against `n`.
; ----------------------------------------------------------------------
Procedure.i dns_SkipName(*p, n.i, pos.i)
  Protected len.i
  Repeat
    If pos >= n
      ProcedureReturn -1
    EndIf
    len = PeekA(*p + pos) & $FF
    If (len & #DNS_PTR_FLAG) = #DNS_PTR_FLAG
      ; A pointer: this byte and the next, then the name is done.
      If (pos + 2) > n
        ProcedureReturn -1
      EndIf
      ProcedureReturn pos + 2
    EndIf
    If len = 0
      ProcedureReturn pos + 1              ; the root label ends it
    EndIf
    pos = pos + 1 + len
  ForEver
EndProcedure

; ----------------------------------------------------------------------
;  DnsParseReply - read a reply for query `qid`. Returns the number of A
;  records found (0 or more), or a negative #DNS_E_* on a malformed or
;  refused reply.
;
;  A RETURN OF ZERO IS NOT AN ERROR AND IS NOT AN ADDRESS. The server
;  answered, said no error, and had no A record for the name - a name
;  that exists only as an MX or a CNAME-to-nothing, or a referral. The
;  caller reports that honestly rather than printing 0.0.0.0.
;
;  A NON-ZERO RCODE IS REPORTED, NOT SWALLOWED. Name Error (3) is the
;  ordinary "no such host"; the others (format error, server failure,
;  refused) mean the resolver, not the name, and the caller says which.
; ----------------------------------------------------------------------
; RFC 1035 sections 4.1 and 7.3; RFC 2181 sections 5 and 8.
; Canonical wire names retain label boundaries. Pointer walks and CNAME
; chains are bounded independently of the packet's claimed record counts.
#DNS_MAX_ANSWERS = 64
#DNS_MAX_ALIASES = 16
#DNS_E_QUESTION = -208
#DNS_E_TRUNCATED = -209
#DNS_E_ALIAS = -210
Global Dim dns_ttl.i[#DNS_MAX_RESULTS]
Global Dim dns_rrOwner.i[#DNS_MAX_ANSWERS]
Global Dim dns_rrType.i[#DNS_MAX_ANSWERS]
Global Dim dns_rrClass.i[#DNS_MAX_ANSWERS]
Global Dim dns_rrData.i[#DNS_MAX_ANSWERS]
Global Dim dns_rrSize.i[#DNS_MAX_ANSWERS]
Global Dim dns_rrTtl.i[#DNS_MAX_ANSWERS]
Global Dim dns_current.a[256]
Global Dim dns_name.a[256]
Global Dim dns_alias.a[256]
Global dns_nameEnd.i

Procedure.i dns_Reject(code.i)
  dns_count=0 : dns_err=code
  ProcedureReturn code
EndProcedure

; Returns canonical wire length, or a negative refusal. nameEnd is the
; first byte following the original encoded name, not its pointer target.
Procedure.i dns_ReadName(packet.i,bytes.i,pos.i,destination.i)
  Define length.i,out.i,nextPos.i,jumps.i,jump.i,i.i,c.i
  nextPos=-1
  Repeat
    If pos<12 Or pos>=bytes : ProcedureReturn #DNS_E_MALFORMED : EndIf
    length=PeekA(packet+pos)
    If (length & $C0)=$C0
      If pos+1>=bytes : ProcedureReturn #DNS_E_MALFORMED : EndIf
      jump=((length & $3F)<<8) | PeekA(packet+pos+1)
      If jump<12 Or jump>=pos Or jumps>=128 : ProcedureReturn #DNS_E_MALFORMED : EndIf
      If nextPos<0 : nextPos=pos+2 : EndIf
      jumps=jumps+1 : pos=jump
    Else
      If length>63 Or pos+1+length>bytes Or out+1+length>255 : ProcedureReturn #DNS_E_MALFORMED : EndIf
      PokeA(destination+out,length) : out=out+1 : pos=pos+1
      If length=0
        If nextPos<0 : nextPos=pos : EndIf
        dns_nameEnd=nextPos
        ProcedureReturn out
      EndIf
      For i=0 To length-1
        c=PeekA(packet+pos+i)
        If c>=65 And c<=90 : c=c+32 : EndIf
        PokeA(destination+out,c) : out=out+1
      Next
      pos=pos+length
    EndIf
  ForEver
EndProcedure

Procedure.i dns_EqualName(left.i,right.i,bytes.i)
  Define i.i
  For i=0 To bytes-1
    If PeekA(left+i)<>PeekA(right+i) : ProcedureReturn 0 : EndIf
  Next
  ProcedureReturn 1
EndProcedure

Procedure.i dns_TextNameMatches(wire.i,text.i)
  Define at.i,pos.i,length.i,i.i,c.i
  Repeat
    length=PeekA(wire+pos) : pos=pos+1
    If length=0
      ProcedureReturn Bool(PeekA(text+at)=0)
    EndIf
    For i=0 To length-1
      If at>=253 : ProcedureReturn 0 : EndIf
      c=PeekA(text+at)
      If c>=65 And c<=90 : c=c+32 : EndIf
      If c=0 Or c=46 Or c<>PeekA(wire+pos) : ProcedureReturn 0 : EndIf
      at=at+1 : pos=pos+1
    Next
    If PeekA(wire+pos)<>0
      If PeekA(text+at)<>46 : ProcedureReturn 0 : EndIf
      at=at+1
    ElseIf PeekA(text+at)=46
      at=at+1
    EndIf
  ForEver
EndProcedure

; expectedName binds the answer to the outstanding host query. Zero retains
; the packet-only API, still restricting answers to its single IN/A question.
Procedure.i DnsParseReplyTypeFor(*p,n.i,qid.i,expectedName.i,qtype.i)
  Define flags.i,an.i,pos.i,i.i,j.i,length.i,currentLength.i,aliasLength.i
  Define kind.i,klass.i,size.i,ttl.i,hops.i,aliasAt.i,aliasTtl.i,chainTtl.i
  Define answerTtl.i,count.i
  dns_err=0 : dns_count=0 : dns_rcode=0 : dns_resultType=0
  If qtype<>#DNS_QTYPE_A And qtype<>#DNS_QTYPE_AAAA : ProcedureReturn dns_Reject(#DNS_E_ARG) : EndIf
  If *p=0 Or n<#DNS_HDR : ProcedureReturn dns_Reject(#DNS_E_SHORT) : EndIf
  If NetReadBE16(*p)<>(qid & $FFFF) : ProcedureReturn dns_Reject(#DNS_E_ID) : EndIf
  flags=NetReadBE16(*p+2)
  If (flags & #DNS_FLAG_QR)=0 Or (flags & $7800)<>0 : ProcedureReturn dns_Reject(#DNS_E_NOT_REPLY) : EndIf
  If NetReadBE16(*p+4)<>1 : ProcedureReturn dns_Reject(#DNS_E_QUESTION) : EndIf
  currentLength=dns_ReadName(*p,n,12,@dns_current[0])
  If currentLength<0 : ProcedureReturn dns_Reject(currentLength) : EndIf
  pos=dns_nameEnd
  If pos+4>n : ProcedureReturn dns_Reject(#DNS_E_MALFORMED) : EndIf
  If NetReadBE16(*p+pos)<>qtype Or NetReadBE16(*p+pos+2)<>#DNS_QCLASS_IN : ProcedureReturn dns_Reject(#DNS_E_QUESTION) : EndIf
  If expectedName<>0
    If dns_TextNameMatches(@dns_current[0],expectedName)=0 : ProcedureReturn dns_Reject(#DNS_E_QUESTION) : EndIf
  EndIf
  If (flags & $0200)<>0 : ProcedureReturn dns_Reject(#DNS_E_TRUNCATED) : EndIf
  dns_rcode=flags & #DNS_RCODE_MASK
  If dns_rcode<>0 : ProcedureReturn dns_Reject(#DNS_E_RCODE) : EndIf
  pos=pos+4 : an=NetReadBE16(*p+6)
  If an>#DNS_MAX_ANSWERS : ProcedureReturn dns_Reject(#DNS_E_MALFORMED) : EndIf
  For i=0 To an-1
    dns_rrOwner[i]=pos
    length=dns_ReadName(*p,n,pos,@dns_name[0])
    If length<0 : ProcedureReturn dns_Reject(length) : EndIf
    pos=dns_nameEnd
    If pos+10>n : ProcedureReturn dns_Reject(#DNS_E_MALFORMED) : EndIf
    kind=NetReadBE16(*p+pos) : klass=NetReadBE16(*p+pos+2)
    ttl=NetReadBE32(*p+pos+4) : size=NetReadBE16(*p+pos+8)
    If ttl>$7FFFFFFF : ttl=0 : EndIf
    pos=pos+10
    If pos+size>n : ProcedureReturn dns_Reject(#DNS_E_MALFORMED) : EndIf
    If klass=#DNS_QCLASS_IN And kind=#DNS_TYPE_A And size<>4 : ProcedureReturn dns_Reject(#DNS_E_MALFORMED) : EndIf
    If klass=#DNS_QCLASS_IN And kind=#DNS_QTYPE_AAAA And size<>16 : ProcedureReturn dns_Reject(#DNS_E_MALFORMED) : EndIf
    If klass=#DNS_QCLASS_IN And kind=#DNS_TYPE_CNAME
      length=dns_ReadName(*p,n,pos,@dns_name[0])
      If length<0 : ProcedureReturn dns_Reject(length) : EndIf
      If dns_nameEnd<>pos+size : ProcedureReturn dns_Reject(#DNS_E_MALFORMED) : EndIf
    EndIf
    dns_rrType[i]=kind : dns_rrClass[i]=klass : dns_rrData[i]=pos
    dns_rrSize[i]=size : dns_rrTtl[i]=ttl : pos=pos+size
  Next
  chainTtl=$7FFFFFFF
  For hops=0 To #DNS_MAX_ALIASES
    count=0 : aliasAt=0 : aliasLength=0 : aliasTtl=$7FFFFFFF : answerTtl=chainTtl
    For i=0 To an-1
      If dns_rrClass[i]=#DNS_QCLASS_IN
        length=dns_ReadName(*p,n,dns_rrOwner[i],@dns_name[0])
        If length=currentLength And dns_EqualName(@dns_current[0],@dns_name[0],length)
          If dns_rrType[i]=qtype
            If dns_rrTtl[i]<answerTtl : answerTtl=dns_rrTtl[i] : EndIf
            If count<#DNS_MAX_RESULTS
              If qtype=#DNS_QTYPE_A
                dns_ip[count]=NetReadBE32(*p+dns_rrData[i])
              Else
                For j=0 To 15 : dns_ip6[count*16+j]=PeekA(*p+dns_rrData[i]+j) : Next
              EndIf
              count=count+1
            EndIf
          ElseIf dns_rrType[i]=#DNS_TYPE_CNAME
            length=dns_ReadName(*p,n,dns_rrData[i],@dns_name[0])
            If aliasAt<>0
              If length<>aliasLength : ProcedureReturn dns_Reject(#DNS_E_ALIAS) : EndIf
              If dns_EqualName(@dns_alias[0],@dns_name[0],length)=0 : ProcedureReturn dns_Reject(#DNS_E_ALIAS) : EndIf
            EndIf
            For j=0 To length-1 : dns_alias[j]=dns_name[j] : Next
            aliasAt=dns_rrData[i] : aliasLength=length
            If dns_rrTtl[i]<aliasTtl : aliasTtl=dns_rrTtl[i] : EndIf
          EndIf
        EndIf
      EndIf
    Next
    If count>0
      If aliasAt<>0 : ProcedureReturn dns_Reject(#DNS_E_ALIAS) : EndIf
      For i=0 To count-1 : dns_ttl[i]=answerTtl : Next
      dns_count=count : dns_resultType=qtype : ProcedureReturn count
    EndIf
    If aliasAt=0 : ProcedureReturn 0 : EndIf
    If aliasTtl<chainTtl : chainTtl=aliasTtl : EndIf
    For j=0 To aliasLength-1 : dns_current[j]=dns_alias[j] : Next
    currentLength=aliasLength
  Next
  ProcedureReturn dns_Reject(#DNS_E_ALIAS)
EndProcedure

Procedure.i DnsParseReplyFor(*p,n.i,qid.i,expectedName.i)
  ProcedureReturn DnsParseReplyTypeFor(*p,n,qid,expectedName,#DNS_QTYPE_A)
EndProcedure

Procedure.i DnsParseReply(*p,n.i,qid.i)
  ProcedureReturn DnsParseReplyFor(*p,n,qid,0)
EndProcedure

Procedure.i DnsResultTtl(i.i)
  If i<0 Or i>=dns_count : ProcedureReturn 0 : EndIf
  ProcedureReturn dns_ttl[i]
EndProcedure

Procedure.i DnsResultCount()
  ProcedureReturn dns_count
EndProcedure

Procedure.i DnsResultIp(i.i)
  If dns_resultType<>#DNS_QTYPE_A Or i < 0 Or i >= dns_count
    ProcedureReturn 0
  EndIf
  ProcedureReturn dns_ip[i]
EndProcedure

; Copies one AAAA result; never exposes storage from an earlier parse.
Procedure.i DnsResultIp6(i.i,destination.i)
  Define j.i
  If destination=0 Or dns_resultType<>#DNS_QTYPE_AAAA Or i<0 Or i>=dns_count : ProcedureReturn #DNS_E_ARG : EndIf
  For j=0 To 15 : PokeA(destination+j,dns_ip6[i*16+j]) : Next
  ProcedureReturn 16
EndProcedure

Procedure.i DnsRcode()
  ProcedureReturn dns_rcode
EndProcedure

Procedure.i DnsError()
  ProcedureReturn dns_err
EndProcedure

; ----------------------------------------------------------------------
;  DnsErrorText - the last refusal as a sentence. A number in a log is a
;  number somebody has to look up; every code above has words here.
; ----------------------------------------------------------------------
Procedure.i DnsErrorText()
  Select dns_err
    Case #DNS_E_NONE
      ProcedureReturn "dns: no refusal recorded"
    Case #DNS_E_ARG
      ProcedureReturn "dns: REFUSED - an empty name, or a null one"
    Case #DNS_E_NAME_LONG
      ProcedureReturn "dns: REFUSED - the name is longer than 255 bytes, which is all a DNS name can be"
    Case #DNS_E_LABEL
      ProcedureReturn "dns: REFUSED - a part of the name between two dots is empty or longer than 63 bytes"
    Case #DNS_E_SHORT
      ProcedureReturn "dns: REFUSED - the reply is shorter than the 12-byte header it must have"
    Case #DNS_E_ID
      ProcedureReturn "dns: REFUSED - the reply's identifier is not this query's, so it answers someone else"
    Case #DNS_E_NOT_REPLY
      ProcedureReturn "dns: REFUSED - the packet is a question, not an answer"
    Case #DNS_E_RCODE
      Select dns_rcode
        Case 1
          ProcedureReturn "dns: the server said the query was malformed (format error)"
        Case 2
          ProcedureReturn "dns: the server failed to answer (server failure) - try again or another server"
        Case 3
          ProcedureReturn "dns: there is no such host - the name does not exist (name error)"
        Case 4
          ProcedureReturn "dns: the server does not implement this kind of query"
        Case 5
          ProcedureReturn "dns: the server refused to answer this query"
        Default
          ProcedureReturn "dns: the server returned an error code"
      EndSelect
    Case #DNS_E_QUESTION
      ProcedureReturn "dns: REFUSED - the response question does not match this host query"
    Case #DNS_E_TRUNCATED
      ProcedureReturn "dns: REFUSED - the response is truncated; retry over TCP"
    Case #DNS_E_ALIAS
      ProcedureReturn "dns: REFUSED - a conflicting or cyclic alias chain"
    Case #DNS_E_MALFORMED
      ProcedureReturn "dns: REFUSED - a length or a compression pointer in the reply runs past its end"
    Default
      ProcedureReturn "dns: an unnumbered refusal, which is itself a defect"
  EndSelect
EndProcedure
