; Shared Ethernet neighbor reachability policy, RFC 4861 sections 7.2/7.3.
; One caller-owned entry, scoped by the caller to an interface and IPv6 target.
; No hardware, clock reads, allocation, packet queues or global scratch.
; All times are monotonic milliseconds. The caller chooses randomized reachable
; time from the interface's advertised base and supplies its retransmit time.
#IPV6_NC_EMPTY = 0
#IPV6_NC_INCOMPLETE = 1
#IPV6_NC_REACHABLE = 2
#IPV6_NC_STALE = 3
#IPV6_NC_DELAY = 4
#IPV6_NC_PROBE = 5
#IPV6_NC_FAILED = 6
#IPV6_NC_MULTICAST = 1
#IPV6_NC_UNICAST = 2
#IPV6_NC_UNREACHABLE = 3
Structure IPv6Reachability
 state.i
 router.i
 deadline.i
 probes.i
 mac.q
EndStructure

Procedure.i IPv6ReachabilityTime(now.i,interval.i)
 If now<0 Or now>$7FFFFFFEFFFFFFFF : ProcedureReturn 0 : EndIf
 If interval<1 Or interval>$FFFFFFFF : ProcedureReturn 0 : EndIf
 ProcedureReturn 1
EndProcedure

Procedure.i IPv6ReachabilityInit(*entry.IPv6Reachability,now.i)
 Define i.i
 If *entry=0 : ProcedureReturn -1 : EndIf
 If IPv6ReachabilityTime(now,1)=0 : ProcedureReturn -1 : EndIf
 For i=0 To SizeOf(IPv6Reachability)-1 : PokeA(*entry+i,0) : Next
 *entry\state=#IPV6_NC_INCOMPLETE : *entry\deadline=now
 ProcedureReturn 0
EndProcedure

; Learn only from an already validated NS addressed to this interface, or RA.
; A missing MAC can mark an existing router but cannot resolve an entry.
; router=-1 preserves existing status (NS); router=1 identifies an RA source.
Procedure.i IPv6ReachabilityLearn(*entry.IPv6Reachability,mac.i,router.i)
 Define i.i,changed.i
 If *entry=0 : ProcedureReturn -1 : EndIf
 If router<>-1 And router<>1 : ProcedureReturn -1 : EndIf
 If mac=0
  If *entry\state<>#IPV6_NC_EMPTY And *entry\state<>#IPV6_NC_FAILED
   If router=1 : *entry\router=1 : EndIf
  EndIf
  ProcedureReturn 0
 EndIf
 If (PeekA(mac)&1)<>0 : ProcedureReturn -1 : EndIf
 changed=0
 For i=0 To 5
  If PeekA(@*entry\mac+i)<>PeekA(mac+i) : changed=1 : EndIf
 Next
 If *entry\state=#IPV6_NC_EMPTY Or *entry\state=#IPV6_NC_FAILED
  *entry\router=0 : changed=1
 EndIf
 If *entry\state=#IPV6_NC_INCOMPLETE : changed=1 : EndIf
 If changed<>0
  For i=0 To 5 : PokeA(@*entry\mac+i,PeekA(mac+i)) : Next
  *entry\state=#IPV6_NC_STALE : *entry\probes=0 : *entry\deadline=0
 EndIf
 If router=1 : *entry\router=1 : EndIf
 ProcedureReturn 1
EndProcedure

; Apply a validated NA to an existing entry. Empty/failed entries are ignored.
; Returns 0 ignored, 1 applied, 2 applied with router->host transition, -1 bad
; arguments. On 2 the owner MUST invalidate routes using this neighbor.
Procedure.i IPv6ReachabilityAdvertise(*entry.IPv6Reachability,mac.i,flags.i,now.i,reachable.i)
 Define i.i,changed.i,solicited.i,override.i,oldRouter.i
 If *entry=0 : ProcedureReturn -1 : EndIf
 If IPv6ReachabilityTime(now,reachable)=0 : ProcedureReturn -1 : EndIf
 If *entry\state=#IPV6_NC_EMPTY Or *entry\state=#IPV6_NC_FAILED : ProcedureReturn 0 : EndIf
 changed=0
 If mac<>0
  If (PeekA(mac)&1)<>0 : ProcedureReturn -1 : EndIf
  For i=0 To 5
   If PeekA(@*entry\mac+i)<>PeekA(mac+i) : changed=1 : EndIf
  Next
 EndIf
 solicited=flags & $40000000 : override=flags & $20000000
 If *entry\state=#IPV6_NC_INCOMPLETE
  If mac=0 : ProcedureReturn 0 : EndIf
  For i=0 To 5 : PokeA(@*entry\mac+i,PeekA(mac+i)) : Next
  *entry\state=#IPV6_NC_STALE : *entry\deadline=0 : *entry\probes=0
 Else
  If override=0 And changed<>0
   If *entry\state=#IPV6_NC_REACHABLE
    *entry\state=#IPV6_NC_STALE : *entry\deadline=0
    ProcedureReturn 1
   EndIf
   ProcedureReturn 0
  EndIf
  If changed<>0
   For i=0 To 5 : PokeA(@*entry\mac+i,PeekA(mac+i)) : Next
   *entry\state=#IPV6_NC_STALE : *entry\deadline=0 : *entry\probes=0
  EndIf
 EndIf
 If solicited<>0
  *entry\state=#IPV6_NC_REACHABLE : *entry\deadline=now+reachable : *entry\probes=0
 EndIf
 oldRouter=*entry\router : *entry\router=0
 If (flags & $80000000)<>0 : *entry\router=1 : EndIf
 If oldRouter=1 And *entry\router=0 : ProcedureReturn 2 : EndIf
 ProcedureReturn 1
EndProcedure

; Acknowledgement of newly sent traffic, not mere inbound traffic, may confirm
; reachability. Do not call for duplicate TCP ACKs or unsolicited packets.
Procedure.i IPv6ReachabilityConfirm(*entry.IPv6Reachability,now.i,reachable.i)
 If *entry=0 : ProcedureReturn -1 : EndIf
 If IPv6ReachabilityTime(now,reachable)=0 : ProcedureReturn -1 : EndIf
 If *entry\state<#IPV6_NC_REACHABLE Or *entry\state>#IPV6_NC_PROBE : ProcedureReturn 0 : EndIf
 *entry\state=#IPV6_NC_REACHABLE : *entry\deadline=now+reachable : *entry\probes=0
 ProcedureReturn 1
EndProcedure

; Call when sending a packet. 1 means the cached MAC is usable, 0 means queue
; pending resolution, -2 means failed/absent. STALE starts a five-second delay.
Procedure.i IPv6ReachabilityUse(*entry.IPv6Reachability,now.i)
 If *entry=0 : ProcedureReturn -1 : EndIf
 If IPv6ReachabilityTime(now,5000)=0 : ProcedureReturn -1 : EndIf
 If *entry\state=#IPV6_NC_REACHABLE And now>=*entry\deadline
  *entry\state=#IPV6_NC_STALE
 EndIf
 If *entry\state=#IPV6_NC_STALE
  *entry\state=#IPV6_NC_DELAY : *entry\deadline=now+5000 : *entry\probes=0
 EndIf
 If *entry\state=#IPV6_NC_INCOMPLETE : ProcedureReturn 0 : EndIf
 If *entry\state>=#IPV6_NC_REACHABLE And *entry\state<=#IPV6_NC_PROBE : ProcedureReturn 1 : EndIf
 ProcedureReturn -2
EndProcedure

; One bounded tick: 0 no action, 1 multicast NS, 2 unicast NS, 3 failed.
; Each returned send action consumes one attempt and must be dispatched once.
; Failed link sends still consume an attempt, preventing unbounded busy retries.
; On failure, the owner fails queued packets and invalidates dependent routes.
Procedure.i IPv6ReachabilityTick(*entry.IPv6Reachability,now.i,retransmit.i)
 Define action.i
 If *entry=0 : ProcedureReturn -1 : EndIf
 If IPv6ReachabilityTime(now,retransmit)=0 : ProcedureReturn -1 : EndIf
 If *entry\state=#IPV6_NC_REACHABLE
  If now>=*entry\deadline : *entry\state=#IPV6_NC_STALE : *entry\deadline=0 : EndIf
  ProcedureReturn 0
 EndIf
 If *entry\state=#IPV6_NC_DELAY
  If now<*entry\deadline : ProcedureReturn 0 : EndIf
  *entry\state=#IPV6_NC_PROBE : *entry\probes=0
 EndIf
 action=0
 If *entry\state=#IPV6_NC_INCOMPLETE : action=#IPV6_NC_MULTICAST : EndIf
 If *entry\state=#IPV6_NC_PROBE : action=#IPV6_NC_UNICAST : EndIf
 If action=0 Or now<*entry\deadline : ProcedureReturn 0 : EndIf
 If *entry\probes>=3
  *entry\state=#IPV6_NC_FAILED : *entry\deadline=0
  ProcedureReturn #IPV6_NC_UNREACHABLE
 EndIf
 *entry\probes=*entry\probes+1 : *entry\deadline=now+retransmit
 ProcedureReturn action
EndProcedure
