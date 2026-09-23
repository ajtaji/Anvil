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
;    * It asks for an A record (IPv4) only. QTYPE=1, QCLASS=IN. No AAAA,
;      no MX, no CNAME chasing OF ITS OWN - though it DOES read through
;      the compression pointers a CNAME answer uses, so a name that is a
;      CNAME to a host with an A record resolves, because the server put
;      the A record in the same answer section.
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
;  are touched only through net.pi4's net_GetBE16/net_GetBE32, which read
;  one byte at a time most-significant first. An IPv4 address is held the
;  way the rest of this stack holds one - first octet in the most
;  significant byte - so DnsResultIp() feeds straight into PutIp().
; ======================================================================

; ---- sizes and constants [RFC 1035, uncited] ----
#DNS_PORT        = 53
#DNS_HDR         = 12         ; ID, flags, and the four count fields
#DNS_QTYPE_A     = 1          ; a host address
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
Procedure.i DnsBuildQuery(name.i, qid.i)
  Protected p.i
  Protected labelStart.i
  Protected i.i
  Protected c.i
  Protected labLen.i
  Protected total.i

  dns_err = #DNS_E_NONE
  dns_outLen = 0
  If name = 0
    dns_err = #DNS_E_ARG
    ProcedureReturn 0
  EndIf
  If PeekA(name) = 0
    dns_err = #DNS_E_ARG
    ProcedureReturn 0
  EndIf

  ; ---- the 12-byte header ----
  net_PutBE16(@dns_out[0], qid & $FFFF)
  net_PutBE16(@dns_out[2], #DNS_FLAG_RD)   ; RD, everything else zero
  net_PutBE16(@dns_out[4], 1)              ; QDCOUNT, exactly one question
  net_PutBE16(@dns_out[6], 0)              ; ANCOUNT
  net_PutBE16(@dns_out[8], 0)              ; NSCOUNT
  net_PutBE16(@dns_out[10], 0)             ; ARCOUNT

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
      dns_out[p] = c & $FF
      p = p + 1
      labLen = labLen + 1
    EndIf
    i = i + 1
  ForEver

  dns_out[p] = 0                            ; the root label ends the name
  p = p + 1
  net_PutBE16(@dns_out[p], #DNS_QTYPE_A)
  p = p + 2
  net_PutBE16(@dns_out[p], #DNS_QCLASS_IN)
  p = p + 2

  dns_outLen = p
  ProcedureReturn p
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
Procedure.i DnsParseReply(*p, n.i, qid.i)
  Protected flags.i
  Protected qd.i
  Protected an.i
  Protected pos.i
  Protected i.i
  Protected rtype.i
  Protected rclass.i
  Protected rdlen.i

  dns_err = #DNS_E_NONE
  dns_count = 0
  dns_rcode = 0

  If *p = 0 Or n < #DNS_HDR
    dns_err = #DNS_E_SHORT
    ProcedureReturn #DNS_E_SHORT
  EndIf
  If net_GetBE16(*p + 0) <> (qid & $FFFF)
    dns_err = #DNS_E_ID
    ProcedureReturn #DNS_E_ID
  EndIf
  flags = net_GetBE16(*p + 2)
  If (flags & #DNS_FLAG_QR) = 0
    dns_err = #DNS_E_NOT_REPLY
    ProcedureReturn #DNS_E_NOT_REPLY
  EndIf
  dns_rcode = flags & #DNS_RCODE_MASK
  If dns_rcode <> 0
    dns_err = #DNS_E_RCODE
    ProcedureReturn #DNS_E_RCODE
  EndIf

  qd = net_GetBE16(*p + 4)
  an = net_GetBE16(*p + 6)
  pos = #DNS_HDR

  ; ---- step over the questions ----
  i = 0
  While i < qd
    pos = dns_SkipName(*p, n, pos)
    If pos < 0
      dns_err = #DNS_E_MALFORMED
      ProcedureReturn #DNS_E_MALFORMED
    EndIf
    If (pos + 4) > n                        ; QTYPE + QCLASS
      dns_err = #DNS_E_MALFORMED
      ProcedureReturn #DNS_E_MALFORMED
    EndIf
    pos = pos + 4
    i = i + 1
  Wend

  ; ---- read the answers, keeping the A records ----
  i = 0
  While i < an
    pos = dns_SkipName(*p, n, pos)
    If pos < 0
      dns_err = #DNS_E_MALFORMED
      ProcedureReturn #DNS_E_MALFORMED
    EndIf
    If (pos + 10) > n                       ; TYPE,CLASS,TTL,RDLENGTH
      dns_err = #DNS_E_MALFORMED
      ProcedureReturn #DNS_E_MALFORMED
    EndIf
    rtype  = net_GetBE16(*p + pos + 0)
    rclass = net_GetBE16(*p + pos + 2)
    ; TTL is *p+pos+4 for four bytes - not needed here
    rdlen  = net_GetBE16(*p + pos + 8)
    pos = pos + 10
    If (pos + rdlen) > n
      dns_err = #DNS_E_MALFORMED
      ProcedureReturn #DNS_E_MALFORMED
    EndIf
    If rtype = #DNS_TYPE_A And rclass = #DNS_QCLASS_IN And rdlen = 4
      If dns_count < #DNS_MAX_RESULTS
        dns_ip[dns_count] = net_GetBE32(*p + pos)
        dns_count = dns_count + 1
      EndIf
    EndIf
    pos = pos + rdlen
    i = i + 1
  Wend

  ProcedureReturn dns_count
EndProcedure

Procedure.i DnsResultCount()
  ProcedureReturn dns_count
EndProcedure

Procedure.i DnsResultIp(i.i)
  If i < 0 Or i >= dns_count
    ProcedureReturn 0
  EndIf
  ProcedureReturn dns_ip[i]
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
    Case #DNS_E_MALFORMED
      ProcedureReturn "dns: REFUSED - a length or a compression pointer in the reply runs past its end"
    Default
      ProcedureReturn "dns: an unnumbered refusal, which is itself a defect"
  EndSelect
EndProcedure
