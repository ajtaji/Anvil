; ======================================================================
; time_cmd.pbi - portable wall-clock settings and monitor command.
;
; Dependency: parse/format/settings/wallclock. On #CAP_NET boards the SNTP
; codec/service are included earlier too. The network branch is removed at
; compile time on boards such as UNO Q; their manual/restored clock and zone
; remain the same common implementation without claiming a network backend.
; ======================================================================

EnableExplicit

#TIME_BOOT_OK = 0
#TIME_BOOT_E_ZONE = 1
#TIME_BOOT_E_RESTORED = 2

Global time_bootError.i

Procedure.i TimeBoot()
  Define *v
  Define epoch.i
  time_bootError = #TIME_BOOT_OK

  ; Public/default behavior is UTC. A saved named/fixed zone is applied only
  ; when its exact grammar is supported; no server address implies location.
  WallClockUseUtcDefault()
  *v = SettingsGet(WallClockZoneSettingsKey())
  If *v <> 0
    If WallClockSetZoneName(*v) = 0
      time_bootError = #TIME_BOOT_E_ZONE
      WallClockUseUtcDefault()
    EndIf
  EndIf

  ; A saved value is a lower-bound floor, never silently promoted to trusted
  ; time. Network or explicit manual input may replace it later.
  *v = SettingsGet(WallClockSettingsKey())
  If *v <> 0
    epoch = WallClockDecode(*v)
    If epoch >= #WALLCLOCK_EPOCH_MIN
      WallClockSet(epoch, #WALLCLOCK_SRC_RESTORED)
    Else
      time_bootError = #TIME_BOOT_E_RESTORED
    EndIf
  EndIf
  ProcedureReturn Bool(time_bootError = #TIME_BOOT_OK)
EndProcedure

Procedure.i TimeBootError()
  ProcedureReturn time_bootError
EndProcedure

Procedure.i TimeBootErrorText()
  Select time_bootError
    Case #TIME_BOOT_OK
      ProcedureReturn "Time status 0: saved wall-clock settings loaded without error."
    Case #TIME_BOOT_E_ZONE
      ProcedureReturn "Time error 1: clock.zone is unsupported, so UTC is active; correct the setting and save it."
    Case #TIME_BOOT_E_RESTORED
      ProcedureReturn "Time error 2: clock.utc is malformed or out of range, so it was not restored; synchronize or set the time."
  EndSelect
  ProcedureReturn "Time error: an unknown saved-clock failure occurred; inspect the settings."
EndProcedure

Procedure.i timecmd_Eq(*a, *b)
  Define i.i
  Define ca.i
  Define cb.i
  If *a = 0 Or *b = 0 : ProcedureReturn 0 : EndIf
  i = 0
  Repeat
    ca = PeekA(*a + i) & $FF
    cb = PeekA(*b + i) & $FF
    If ca >= 65 And ca <= 90 : ca = ca + 32 : EndIf
    If cb >= 65 And cb <= 90 : cb = cb + 32 : EndIf
    If ca <> cb : ProcedureReturn 0 : EndIf
    If ca = 0 : ProcedureReturn 1 : EndIf
    i = i + 1
  ForEver
EndProcedure

Procedure TimeShow()
  UartWriteStr(WallClockLine())
  PrintNl()
  Print("  zone: ")
  UartWriteStr(WallClockZoneName())
  If WallClockZoneConfigured() = 0 : Print(" (UTC default)") : EndIf
  PrintNl()
  Print("  trusted: ")
  If WallClockTrusted() <> 0
    PrintN("yes")
  ElseIf WallClockValid() <> 0
    PrintN("no - restored floor only")
  Else
    PrintN("no - time is not synchronized")
  EndIf
  If time_bootError <> #TIME_BOOT_OK
    Print("  saved settings: ")
    UartWriteStr(TimeBootErrorText())
    PrintNl()
  EndIf

  CompilerIf #CAP_NET = 1
    Print("  SNTP service: ")
    UartWriteStr(NtpServiceStateText())
    PrintNl()
    Print("  server policy: ")
    If NtpServiceConfiguredServer() <> 0
      Print("explicit ")
      UartWriteStr(NtpServiceConfiguredServer())
    ElseIf NtpServiceServerSource() = #NTP_SERVER_DHCP
      Print("DHCP option 42")
    Else
      UartWriteStr(NtpDefaultServer())
      Print(" (default)")
    EndIf
    If NtpServiceServerIp() <> 0
      Print(" -> ")
      PutIp(NtpServiceServerIp())
    EndIf
    PrintNl()
    Print("  synchronization: plain SNTP, not cryptographically authenticated; successes ")
    PrintDec(NtpServiceSuccesses())
    Print(", queries ") : PrintDec(NtpServiceQueries())
    Print(", rejected replies ") : PrintDec(NtpServiceRejects()) : PrintNl()
    If NtpServiceLastError() <> #NTP_SERVICE_OK
      Print("  last service error: ")
      UartWriteStr(NtpServiceErrorText())
      PrintNl()
      If NtpServiceLastError() = #NTP_SERVICE_E_SNTP_REPLY
        Print("  last packet refusal: ")
        UartWriteStr(SntpErrorText())
        PrintNl()
      EndIf
    EndIf
  CompilerElse
    PrintN("  SNTP service: unavailable because this board has no network backend.")
  CompilerEndIf

  If SettingsDirty() <> 0
    PrintN("  Settings changed in memory. Type settings save to persist them.")
  EndIf
EndProcedure

Procedure TimeUsage()
  PrintN("time")
  PrintN("time set <unix-seconds-UTC>")
  PrintN("time zone <UTC | America/Chicago | fixed:+HH:MM | fixed:-HH:MM>")
  CompilerIf #CAP_NET = 1
    PrintN("time sync")
    PrintN("time server <IPv4-or-hostname | default>")
  CompilerEndIf
  PrintN("  Changes are in memory only. Type settings save to persist them.")
EndProcedure

Procedure CmdTime()
  Define *v
  Define epoch.i

  SkipSpace()
  gWordAt = gPos
  SkipWord()
  gWordLen = gPos - gWordAt
  If gWordLen = 0 Or WordIs("status") <> 0 Or WordIs("show") <> 0
    TimeShow()
    ProcedureReturn
  EndIf

  If WordIs("zone") <> 0
    *v = ArgRest()
    If *v = 0
      PrintN("!! time zone needs UTC, America/Chicago, or fixed:+HH:MM; nothing changed.")
      ProcedureReturn
    EndIf
    If WallClockSetZoneName(*v) = 0
      Print("!! ") : UartWriteStr(WallClockErrorText()) : PrintNl()
      PrintN("   Nothing changed. An NTP server location is never used to guess a zone.")
      ProcedureReturn
    EndIf
    If SettingsSet(WallClockZoneSettingsKey(), WallClockZoneName()) = 0
      PrintN("!! The zone is active for this boot, but settings refused to record it in memory.")
      ProcedureReturn
    EndIf
    Print("Time zone is now ") : UartWriteStr(WallClockZoneName()) : PrintN(".")
    PrintN("  This is in memory only. Type settings save to keep it for the next boot.")
    ProcedureReturn
  EndIf

  If WordIs("set") <> 0
    *v = ArgRest()
    If *v = 0
      PrintN("!! time set needs decimal Unix seconds in UTC; nothing changed.")
      ProcedureReturn
    EndIf
    epoch = WallClockDecode(*v)
    If epoch < #WALLCLOCK_EPOCH_MIN Or WallClockSet(epoch, #WALLCLOCK_SRC_MANUAL) = 0
      Print("!! ") : UartWriteStr(WallClockErrorText()) : PrintNl()
      PrintN("   Nothing changed.")
      ProcedureReturn
    EndIf
    SettingsSet(WallClockSettingsKey(), WallClockEncode(epoch))
    Print("Wall time set manually: ") : UartWriteStr(WallClockCaption()) : PrintNl()
    PrintN("  This is trusted manual input, not network synchronization.")
    PrintN("  It is in memory only. Type settings save to keep a restored floor for the next boot.")
    ProcedureReturn
  EndIf

  CompilerIf #CAP_NET = 1
    If WordIs("sync") <> 0
      NtpServiceRequestNow()
      PrintN("SNTP synchronization scheduled. The prompt remains available while it runs.")
      ProcedureReturn
    EndIf
    If WordIs("server") <> 0
      *v = ArgRest()
      If *v = 0
        PrintN("!! time server needs an IPv4 address, hostname, or default; nothing changed.")
        ProcedureReturn
      EndIf
      If timecmd_Eq(*v, "default") <> 0
        If SettingsGet(NtpServerSettingsKey()) <> 0
          SettingsRemove(NtpServerSettingsKey())
        EndIf
        NtpServiceReload()
        Print("SNTP server policy now uses DHCP option 42, then ")
        UartWriteStr(NtpDefaultServer()) : PrintN(".")
      Else
        If NtpServerNameValid(*v) = 0
          PrintN("!! NTP error -22: the server is not a valid unicast IPv4 address or hostname; nothing changed.")
          ProcedureReturn
        EndIf
        If SettingsSet(NtpServerSettingsKey(), *v) = 0
          PrintN("!! The settings table refused ntp.server; nothing changed.")
          ProcedureReturn
        EndIf
        NtpServiceReload()
        Print("SNTP server is now ") : UartWriteStr(*v) : PrintN(".")
      EndIf
      PrintN("  This is in memory only. Type settings save to keep it for the next boot.")
      ProcedureReturn
    EndIf
  CompilerEndIf

  PrintN("!! time did not recognize that subcommand; nothing changed.")
  TimeUsage()
EndProcedure
