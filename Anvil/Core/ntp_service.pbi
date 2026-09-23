; ======================================================================
; ntp_service.pbi - nonblocking wall-clock synchronization over IPv4.
;
; Dependencies, included earlier by the board:
;   settings.pbi, netfmt.pbi, wallclock.pbi, sntp_codec.pbi
;   net.pi4, dns.pi4, dhcp.pi4, link.pi4, netif.pbi and the HwLink seam.
;
; NtpServiceBoot only reads settings and initializes state. It never sends,
; resolves, waits, or delays. NtpServiceTick advances at most one bounded
; state-machine step. Replies enter through NtpServiceInput in the shared UDP
; dispatcher, which validates/copies state but never builds or transmits a
; packet while NetInput's receive scratch is live.
;
; Server preference is explicit ntp.server, then DHCP option 42 on the
; interface that granted it, then time.cloudflare.com. Cloudflare documents
; that hostname for device NTP use. A server never implies a time zone.
; Plain SNTP is not cryptographically authenticated; packet provenance is
; reported as such by wallclock.pbi.
; ======================================================================

EnableExplicit

#NTP_SERVICE_IDLE      = 0
#NTP_SERVICE_SELECT    = 1
#NTP_SERVICE_DNS_SEND  = 2
#NTP_SERVICE_DNS_WAIT  = 3
#NTP_SERVICE_NTP_SEND  = 4
#NTP_SERVICE_NTP_WAIT  = 5
#NTP_SERVICE_APPLY     = 6
#NTP_SERVICE_HOLD      = 7

#NTP_SERVER_EXPLICIT = 1
#NTP_SERVER_DHCP     = 2
#NTP_SERVER_DEFAULT  = 3

#NTP_SERVICE_OK             = 0
#NTP_SERVICE_E_NO_NETWORK   = -20
#NTP_SERVICE_E_NO_DNS       = -21
#NTP_SERVICE_E_BAD_SERVER   = -22
#NTP_SERVICE_E_LISTENER     = -23
#NTP_SERVICE_E_BUILD        = -24
#NTP_SERVICE_E_SEND         = -25
#NTP_SERVICE_E_TIMEOUT      = -26
#NTP_SERVICE_E_DNS_REPLY    = -27
#NTP_SERVICE_E_SNTP_REPLY   = -28
#NTP_SERVICE_E_CONFIG       = -29
#NTP_SERVICE_E_ADDRESS_LOST = -30

#NTP_DNS_PORT_BASE = 49200
#NTP_LOCAL_PORT_BASE = 49216
#NTP_DNS_TIMEOUT_MS = 3000
#NTP_REPLY_TIMEOUT_MS = 3000
#NTP_RETRY_MIN_MS = 5000
#NTP_RETRY_MAX_MS = 900000
#NTP_REFRESH_MS = 21600000

Global ntps_state.i
Global ntps_kind.i
Global ntps_localIp.i
Global ntps_dnsIp.i
Global ntps_serverIp.i
Global ntps_serverSource.i
Global ntps_dnsPort.i
Global ntps_localPort.i
Global ntps_qid.i
Global gNtpsDue.i
Global ntps_deadline.i
Global ntps_failures.i
Global ntps_queries.i
Global ntps_successes.i
Global ntps_rejects.i
Global ntps_lastError.i
Global ntps_pendingError.i
Global ntps_pendingEpoch.i
Global ntps_pendingFraction.i
Global ntps_sentTick.i
Global ntps_replyTick.i
Global ntps_attemptDeadline.i
Global ntps_lastSyncMs.i
Global ntps_configExplicit.i
Global Dim ntps_configName.a[128]
Global Dim ntps_request.a[#SNTP_PACKET_BYTES]

Procedure.i NtpServerSettingsKey()
  ProcedureReturn "ntp.server"
EndProcedure

Procedure.i NtpDefaultServer()
  ProcedureReturn "time.cloudflare.com"
EndProcedure

Procedure.i ntps_UsableServerIp(ip.i)
  Define first.i
  If ip <= 0 Or ip >= $FFFFFFFF : ProcedureReturn 0 : EndIf
  first = (ip >> 24) & $FF
  If first >= 224 And first <= 239 : ProcedureReturn 0 : EndIf
  ProcedureReturn 1
EndProcedure

; Bounded configuration validation with no DNS or packet-buffer side effect.
; A single-label LAN hostname is allowed; malformed dotted numerics are not
; silently reinterpreted as DNS names.
Procedure.i NtpServerNameValid(*name)
  Define i.i
  Define c.i
  Define label.i
  Define numeric.i
  Define ip.i
  If *name = 0 Or PeekA(*name) = 0 : ProcedureReturn 0 : EndIf
  numeric = 1
  i = 0
  label = 0
  Repeat
    c = PeekA(*name + i) & $FF
    If c = 0 : Break : EndIf
    If i >= 127 : ProcedureReturn 0 : EndIf
    If c <> 46
      If c < 48 Or c > 57 : numeric = 0 : EndIf
    EndIf
    If c = 46
      If label = 0 Or (PeekA(*name + i - 1) & $FF) = 45 : ProcedureReturn 0 : EndIf
      label = 0
    Else
      If (c >= 65 And c <= 90) Or (c >= 97 And c <= 122) Or (c >= 48 And c <= 57) Or c = 45
        If label = 0 And c = 45 : ProcedureReturn 0 : EndIf
        label = label + 1
        If label > 63 : ProcedureReturn 0 : EndIf
      Else
        ProcedureReturn 0
      EndIf
    EndIf
    i = i + 1
  ForEver
  If label = 0 Or (PeekA(*name + i - 1) & $FF) = 45 : ProcedureReturn 0 : EndIf
  If numeric <> 0
    ip = ParseDotted(*name)
    ProcedureReturn ntps_UsableServerIp(ip)
  EndIf
  ProcedureReturn 1
EndProcedure

Procedure ntps_Copy(*dst, *src, limit.i)
  Define i.i
  Define c.i
  i = 0
  If *src <> 0
    c = PeekB(*src) & $FF
    While c <> 0 And i < limit
      PokeB(*dst + i, c)
      i = i + 1
      c = PeekB(*src + i) & $FF
    Wend
  EndIf
  PokeB(*dst + i, 0)
EndProcedure

Procedure.i ntps_Due(now.i, when.i)
  ProcedureReturn (((now - when) & $FFFFFFFF) < $80000000)
EndProcedure

Procedure ntps_CloseListeners()
  If ntps_kind > #HW_LINK_NONE And ntps_kind < #NETIF_KINDS
    If ntps_dnsPort <> 0 : NetUdpListen(ntps_kind, ntps_dnsPort, 0) : EndIf
    If ntps_localPort <> 0 : NetUdpListen(ntps_kind, ntps_localPort, 0) : EndIf
  EndIf
EndProcedure

Procedure ntps_ScheduleFailure(code.i, now.i)
  Define delay.i
  ntps_CloseListeners()
  ntps_lastError = code
  ntps_pendingError = 0
  ntps_failures = ntps_failures + 1
  delay = #NTP_RETRY_MIN_MS
  If ntps_failures > 8
    delay = #NTP_RETRY_MAX_MS
  ElseIf ntps_failures > 1
    delay = delay << (ntps_failures - 1)
  EndIf
  If delay > #NTP_RETRY_MAX_MS : delay = #NTP_RETRY_MAX_MS : EndIf
  gNtpsDue = (now + delay) & $FFFFFFFF
  ntps_state = #NTP_SERVICE_SELECT
  ntps_kind = #HW_LINK_NONE
  ntps_localIp = 0
  ntps_attemptDeadline = 0
EndProcedure

Procedure.i ntps_DnsForKind(kind.i)
  Define ip.i
  Define *s
  ip = NetIfDns(kind)
  If ip <> 0 : ProcedureReturn ip : EndIf
  *s = SettingsGet(EthKeyDns())
  If *s = 0 : ProcedureReturn 0 : EndIf
  ip = ParseDotted(*s)
  If ip <= 0 : ProcedureReturn 0 : EndIf
  If NetIfForDest(ip) <> kind : ProcedureReturn 0 : EndIf
  ProcedureReturn ip
EndProcedure

; Selects one request path without sending. A DHCP-provided NTP address stays
; on the interface that supplied it. Hostnames use an interface with an actual
; resolver and route, so a direct-cable link cannot starve a working radio.
Procedure.i ntps_SelectPath()
  Define kind.i
  Define preferred.i
  Define ip.i
  Define dns.i
  Define *name

  ntps_serverIp = 0
  ntps_dnsIp = 0
  ntps_kind = #HW_LINK_NONE
  ntps_localIp = 0

  *name = @ntps_configName[0]
  If ntps_configExplicit <> 0
    If NtpServerNameValid(*name) = 0
      ProcedureReturn #NTP_SERVICE_E_BAD_SERVER
    EndIf
    ip = ParseDotted(*name)
    If ip >= 0
      kind = NetIfForDest(ip)
      If kind = #HW_LINK_NONE : ProcedureReturn #NTP_SERVICE_E_NO_NETWORK : EndIf
      ntps_kind = kind
      ntps_serverIp = ip
      ntps_serverSource = #NTP_SERVER_EXPLICIT
      ntps_state = #NTP_SERVICE_NTP_SEND
      ProcedureReturn 1
    EndIf
  Else
    ; Prefer option 42 on the normal preferred interface, then any other
    ; usable lease row. The address disappears with that lease.
    preferred = NetIfPreferred()
    If preferred <> #HW_LINK_NONE
      ip = DhcpClientNtp(preferred)
      If ip <> 0
        ntps_kind = preferred
        ntps_serverIp = ip
        ntps_serverSource = #NTP_SERVER_DHCP
        ntps_state = #NTP_SERVICE_NTP_SEND
        ProcedureReturn 1
      EndIf
    EndIf
    kind = NetIfNext(0)
    While kind <> #HW_LINK_NONE
      If kind <> preferred
        ip = DhcpClientNtp(kind)
        If ip <> 0
          ntps_kind = kind
          ntps_serverIp = ip
          ntps_serverSource = #NTP_SERVER_DHCP
          ntps_state = #NTP_SERVICE_NTP_SEND
          ProcedureReturn 1
        EndIf
      EndIf
      kind = NetIfNext(kind)
    Wend
    *name = NtpDefaultServer()
  EndIf

  ; A hostname needs a resolver. Walk all usable interfaces instead of
  ; blindly following the global preference to a direct cable with no route.
  kind = NetIfNext(0)
  While kind <> #HW_LINK_NONE
    dns = ntps_DnsForKind(kind)
    If dns <> 0 And NetNextHop(kind, dns) <> 0
      ntps_kind = kind
      ntps_dnsIp = dns
      If ntps_configExplicit <> 0
        ntps_serverSource = #NTP_SERVER_EXPLICIT
      Else
        ntps_serverSource = #NTP_SERVER_DEFAULT
      EndIf
      ntps_state = #NTP_SERVICE_DNS_SEND
      ProcedureReturn 1
    EndIf
    kind = NetIfNext(kind)
  Wend
  If NetIfUsableCount() = 0
    ProcedureReturn #NTP_SERVICE_E_NO_NETWORK
  EndIf
  ProcedureReturn #NTP_SERVICE_E_NO_DNS
EndProcedure

Procedure.i ntps_SendArp(kind.i, dst.i)
  Define hop.i
  hop = NetNextHop(kind, dst)
  If hop = 0 : ProcedureReturn 0 : EndIf
  If NetArpRequest(kind, hop) = 0 : ProcedureReturn 0 : EndIf
  ProcedureReturn LinkTxStagedOn(kind)
EndProcedure

Procedure ntps_DnsSend(now.i)
  Define *name
  Define n.i
  If ntps_attemptDeadline = 0
    ntps_attemptDeadline = (now + #NTP_DNS_TIMEOUT_MS) & $FFFFFFFF
  ElseIf ntps_Due(now, ntps_attemptDeadline) <> 0
    ntps_ScheduleFailure(#NTP_SERVICE_E_TIMEOUT, now)
    ProcedureReturn
  EndIf
  ntps_dnsPort = #NTP_DNS_PORT_BASE + ntps_kind
  If NetUdpListen(ntps_kind, ntps_dnsPort, 1) = 0
    ntps_ScheduleFailure(#NTP_SERVICE_E_LISTENER, now)
    ProcedureReturn
  EndIf
  If ntps_configExplicit <> 0
    *name = @ntps_configName[0]
  Else
    *name = NtpDefaultServer()
  EndIf
  ntps_qid = ((millis() ! Ticks() ! (ntps_queries << 7)) & $FFFF)
  If ntps_qid = 0 : ntps_qid = 1 : EndIf
  n = DnsBuildQuery(*name, ntps_qid)
  If n <= 0
    ntps_ScheduleFailure(#NTP_SERVICE_E_BAD_SERVER, now)
    ProcedureReturn
  EndIf
  ntps_localIp = NetSrcFor(ntps_kind, ntps_dnsIp)
  If NetUdpBuild(ntps_kind, ntps_dnsIp, #DNS_PORT, ntps_dnsPort, DnsQueryBuf(), n) = 0
    If NetError() = #NET_E_NO_ARP
      ntps_SendArp(ntps_kind, ntps_dnsIp)
      gNtpsDue = (now + 250) & $FFFFFFFF
      ProcedureReturn
    EndIf
    ntps_ScheduleFailure(#NTP_SERVICE_E_BUILD, now)
    ProcedureReturn
  EndIf
  If LinkTxStagedOn(ntps_kind) = 0
    ntps_ScheduleFailure(#NTP_SERVICE_E_SEND, now)
    ProcedureReturn
  EndIf
  ntps_queries = ntps_queries + 1
  ntps_deadline = (now + #NTP_DNS_TIMEOUT_MS) & $FFFFFFFF
  ntps_attemptDeadline = 0
  ntps_state = #NTP_SERVICE_DNS_WAIT
EndProcedure

Procedure ntps_NtpSend(now.i)
  Define nonceSeconds.i
  Define nonceFraction.i
  Define n.i
  If ntps_dnsPort <> 0
    NetUdpListen(ntps_kind, ntps_dnsPort, 0)
    ntps_dnsPort = 0
  EndIf
  If ntps_attemptDeadline = 0
    ntps_attemptDeadline = (now + #NTP_REPLY_TIMEOUT_MS) & $FFFFFFFF
  ElseIf ntps_Due(now, ntps_attemptDeadline) <> 0
    ntps_ScheduleFailure(#NTP_SERVICE_E_TIMEOUT, now)
    ProcedureReturn
  EndIf
  ntps_localPort = #NTP_LOCAL_PORT_BASE + ntps_kind
  If NetUdpListen(ntps_kind, ntps_localPort, 1) = 0
    ntps_ScheduleFailure(#NTP_SERVICE_E_LISTENER, now)
    ProcedureReturn
  EndIf
  nonceSeconds = (Ticks() >> 16) & $FFFFFFFF
  nonceFraction = (Ticks() ! (ntps_queries * 1103515245) ! (ntps_kind << 24)) & $FFFFFFFF
  If nonceSeconds = 0 And nonceFraction = 0 : nonceFraction = 1 : EndIf
  n = SntpBuildRequest(@ntps_request[0], #SNTP_PACKET_BYTES, nonceSeconds, nonceFraction)
  If n <= 0
    ntps_ScheduleFailure(#NTP_SERVICE_E_BUILD, now)
    ProcedureReturn
  EndIf
  ntps_localIp = NetSrcFor(ntps_kind, ntps_serverIp)
  If NetUdpBuild(ntps_kind, ntps_serverIp, #SNTP_PORT, ntps_localPort, @ntps_request[0], n) = 0
    If NetError() = #NET_E_NO_ARP
      ntps_SendArp(ntps_kind, ntps_serverIp)
      gNtpsDue = (now + 250) & $FFFFFFFF
      ProcedureReturn
    EndIf
    ntps_ScheduleFailure(#NTP_SERVICE_E_BUILD, now)
    ProcedureReturn
  EndIf
  ntps_sentTick = Ticks()
  If LinkTxStagedOn(ntps_kind) = 0
    ntps_ScheduleFailure(#NTP_SERVICE_E_SEND, now)
    ProcedureReturn
  EndIf
  ntps_queries = ntps_queries + 1
  ntps_deadline = (now + #NTP_REPLY_TIMEOUT_MS) & $FFFFFFFF
  ntps_attemptDeadline = 0
  ntps_state = #NTP_SERVICE_NTP_WAIT
EndProcedure

; Called only by the common UDP dispatcher. It never transmits and never
; retains NetUdpRxData's pointer beyond the call.
Procedure.i NtpServiceInput(kind.i)
  Define c.i
  If kind <> ntps_kind Or NetRxTo() <> ntps_localIp
    ProcedureReturn 0
  EndIf
  If ntps_state = #NTP_SERVICE_DNS_WAIT And NetUdpRxDstPort() = ntps_dnsPort
    If NetUdpRxFrom() <> ntps_dnsIp Or NetUdpRxPort() <> #DNS_PORT
      ntps_rejects = ntps_rejects + 1
      ProcedureReturn 1
    EndIf
    c = DnsParseReply(NetUdpRxData(), NetUdpRxLen(), ntps_qid)
    If c > 0
      ntps_serverIp = DnsResultIp(0)
      ntps_attemptDeadline = 0
      ntps_state = #NTP_SERVICE_NTP_SEND
      gNtpsDue = millis()
    Else
      ntps_rejects = ntps_rejects + 1
      ntps_lastError = #NTP_SERVICE_E_DNS_REPLY
    EndIf
    ProcedureReturn 1
  EndIf
  If ntps_state = #NTP_SERVICE_NTP_WAIT And NetUdpRxDstPort() = ntps_localPort
    c = SntpParseReply(NetUdpRxData(), NetUdpRxLen(), NetUdpRxFrom(), NetUdpRxPort(), NetUdpRxDstPort(), ntps_serverIp, ntps_localPort)
    If c <> 0
      ntps_pendingEpoch = SntpReplyEpoch()
      ntps_pendingFraction = SntpReplyFraction()
      ntps_replyTick = Ticks()
      ntps_state = #NTP_SERVICE_APPLY
      gNtpsDue = millis()
    Else
      ntps_rejects = ntps_rejects + 1
      ntps_lastError = #NTP_SERVICE_E_SNTP_REPLY
    EndIf
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure NtpServiceTick()
  Define now.i
  Define rc.i
  Define rtt.i
  Define half.i
  Define advance.i
  now = millis()
  If ntps_state = #NTP_SERVICE_IDLE
    ProcedureReturn
  EndIf

  If ntps_kind <> #HW_LINK_NONE
    If NetIfUsable(ntps_kind) = 0 Or (ntps_localIp <> 0 And NetIfHoldsIp(ntps_kind, ntps_localIp) = 0)
      ntps_ScheduleFailure(#NTP_SERVICE_E_ADDRESS_LOST, now)
      ProcedureReturn
    EndIf
  EndIf

  If ntps_state = #NTP_SERVICE_DNS_WAIT Or ntps_state = #NTP_SERVICE_NTP_WAIT
    If ntps_Due(now, ntps_deadline) <> 0
      ntps_ScheduleFailure(#NTP_SERVICE_E_TIMEOUT, now)
    EndIf
    ProcedureReturn
  EndIf
  If ntps_Due(now, gNtpsDue) = 0
    ProcedureReturn
  EndIf

  If ntps_state = #NTP_SERVICE_SELECT Or ntps_state = #NTP_SERVICE_HOLD
    rc = ntps_SelectPath()
    If rc < 0
      ntps_ScheduleFailure(rc, now)
    EndIf
    ProcedureReturn
  EndIf
  If ntps_state = #NTP_SERVICE_DNS_SEND
    ntps_DnsSend(now)
    ProcedureReturn
  EndIf
  If ntps_state = #NTP_SERVICE_NTP_SEND
    ntps_NtpSend(now)
    ProcedureReturn
  EndIf
  If ntps_state = #NTP_SERVICE_APPLY
    ntps_CloseListeners()
    ; The server transmit timestamp predates client receipt by roughly one
    ; one-way path. Use half the observed request/reply interval as a bounded
    ; first-order estimate, then anchor at the captured receive tick. This is
    ; ordinary SNTP accuracy, not a hardware or authentication claim.
    rtt = ntps_replyTick - ntps_sentTick
    If rtt < 0 : rtt = 0 : EndIf
    If WallClockHz() > 0 And rtt > WallClockHz() * 3
      rtt = WallClockHz() * 3
    EndIf
    half = rtt / 2
    advance = 0
    If WallClockHz() > 0
      advance = (half * 4294967296) / WallClockHz()
    EndIf
    ntps_pendingFraction = ntps_pendingFraction + advance
    If ntps_pendingFraction > 4294967295
      ntps_pendingFraction = ntps_pendingFraction - 4294967296
      ntps_pendingEpoch = ntps_pendingEpoch + 1
    EndIf
    If WallClockSetNtpAt(ntps_pendingEpoch, ntps_pendingFraction, ntps_replyTick) = 0
      ntps_ScheduleFailure(#NTP_SERVICE_E_SNTP_REPLY, now)
      ProcedureReturn
    EndIf
    ; Update the in-memory restored floor. Persistence remains the ordinary,
    ; explicit `settings save` operation; this tick never blocks on storage.
    SettingsSet(WallClockSettingsKey(), WallClockEncode(WallClockNow()))
    ntps_successes = ntps_successes + 1
    ntps_failures = 0
    ntps_lastError = #NTP_SERVICE_OK
    ntps_lastSyncMs = now
    gNtpsDue = (now + #NTP_REFRESH_MS) & $FFFFFFFF
    ntps_state = #NTP_SERVICE_HOLD
    ntps_kind = #HW_LINK_NONE
    ntps_localIp = 0
  EndIf
EndProcedure

Procedure NtpServiceReload()
  Define *v
  ntps_CloseListeners()
  ntps_configExplicit = 0
  ntps_Copy(@ntps_configName[0], "", 127)
  *v = SettingsGet(NtpServerSettingsKey())
  If *v <> 0
    ntps_Copy(@ntps_configName[0], *v, 127)
    ntps_configExplicit = 1
  EndIf
  ntps_state = #NTP_SERVICE_SELECT
  ntps_kind = #HW_LINK_NONE
  ntps_localIp = 0
  ntps_failures = 0
  ntps_attemptDeadline = 0
  gNtpsDue = millis()
EndProcedure

Procedure NtpServiceBoot()
  ntps_state = #NTP_SERVICE_IDLE
  ntps_kind = #HW_LINK_NONE
  ntps_lastError = #NTP_SERVICE_OK
  NtpServiceReload()
EndProcedure

Procedure NtpServiceRequestNow()
  ntps_CloseListeners()
  ntps_state = #NTP_SERVICE_SELECT
  ntps_kind = #HW_LINK_NONE
  ntps_localIp = 0
  ntps_failures = 0
  ntps_attemptDeadline = 0
  gNtpsDue = millis()
EndProcedure

Procedure.i NtpServiceState() : ProcedureReturn ntps_state : EndProcedure
Procedure.i NtpServiceKind() : ProcedureReturn ntps_kind : EndProcedure
Procedure.i NtpServiceServerIp() : ProcedureReturn ntps_serverIp : EndProcedure
Procedure.i NtpServiceServerSource() : ProcedureReturn ntps_serverSource : EndProcedure
Procedure.i NtpServiceQueries() : ProcedureReturn ntps_queries : EndProcedure
Procedure.i NtpServiceSuccesses() : ProcedureReturn ntps_successes : EndProcedure
Procedure.i NtpServiceRejects() : ProcedureReturn ntps_rejects : EndProcedure
Procedure.i NtpServiceLastError() : ProcedureReturn ntps_lastError : EndProcedure
Procedure.i NtpServiceLastSyncMs() : ProcedureReturn ntps_lastSyncMs : EndProcedure

Procedure.i NtpServiceConfiguredServer()
  If ntps_configExplicit <> 0 : ProcedureReturn @ntps_configName[0] : EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i NtpServiceStateText()
  Select ntps_state
    Case #NTP_SERVICE_IDLE : ProcedureReturn "idle"
    Case #NTP_SERVICE_SELECT : ProcedureReturn "waiting for a usable network path"
    Case #NTP_SERVICE_DNS_SEND : ProcedureReturn "preparing a DNS query"
    Case #NTP_SERVICE_DNS_WAIT : ProcedureReturn "waiting for the DNS reply"
    Case #NTP_SERVICE_NTP_SEND : ProcedureReturn "preparing an SNTP request"
    Case #NTP_SERVICE_NTP_WAIT : ProcedureReturn "waiting for the SNTP reply"
    Case #NTP_SERVICE_APPLY : ProcedureReturn "applying a validated SNTP reply"
    Case #NTP_SERVICE_HOLD : ProcedureReturn "synchronized; holding until refresh"
  EndSelect
  ProcedureReturn "unknown service state"
EndProcedure

Procedure.i NtpServiceErrorText()
  Select ntps_lastError
    Case #NTP_SERVICE_OK
      ProcedureReturn "NTP status 0: no service error is recorded."
    Case #NTP_SERVICE_E_NO_NETWORK
      ProcedureReturn "NTP error -20: no usable network route exists; check Ethernet or Wi-Fi addressing."
    Case #NTP_SERVICE_E_NO_DNS
      ProcedureReturn "NTP error -21: no usable DNS resolver exists; check DHCP or net.dns."
    Case #NTP_SERVICE_E_BAD_SERVER
      ProcedureReturn "NTP error -22: ntp.server is not a valid address or hostname; check the setting."
    Case #NTP_SERVICE_E_LISTENER
      ProcedureReturn "NTP error -23: no UDP listener slot is available; check active network services."
    Case #NTP_SERVICE_E_BUILD
      ProcedureReturn "NTP error -24: the network stack refused the request; check the selected route."
    Case #NTP_SERVICE_E_SEND
      ProcedureReturn "NTP error -25: the selected interface did not transmit the request; check link status."
    Case #NTP_SERVICE_E_TIMEOUT
      ProcedureReturn "NTP error -26: the DNS or SNTP reply timed out; check server reachability."
    Case #NTP_SERVICE_E_DNS_REPLY
      ProcedureReturn "NTP error -27: DNS answered without a usable IPv4 address; check ntp.server."
    Case #NTP_SERVICE_E_SNTP_REPLY
      ProcedureReturn "NTP error -28: the SNTP reply failed validation; inspect the packet refusal."
    Case #NTP_SERVICE_E_CONFIG
      ProcedureReturn "NTP error -29: a clock setting is malformed; check clock.utc and clock.zone."
    Case #NTP_SERVICE_E_ADDRESS_LOST
      ProcedureReturn "NTP error -30: the request interface lost its address; the service will retry after recovery."
  EndSelect
  ProcedureReturn "NTP error: an unknown service failure occurred; inspect the last error code."
EndProcedure
