; ----------------------------------------------------------------------
;  NetXferServer - THE ONE ADDRESS A TRANSFER CANNOT DERIVE. Returns the
;  stored TFTP server address, or 0 with the refusal already printed.
;
;  WHAT THIS REPLACES, AND WHY IT IS A CHANGE OF SHAPE AND NOT A RELAXED
;  CHECK. `get` and `put` went through EthConfig() above, which demands
;  FOUR keys - net.address, net.netmask, net.gateway, net.server - and
;  then writes the first three into the WIRED interface's address row.
;  Both halves of that are wrong now and the second one is the worse:
;
;    THE BOARD ALREADY HAS ADDRESSES. Since 2026-09-08 every interface
;    owns its own row, and a board on a bare cable comes up holding a
;    probed link-local address, a served 192.168.137.1 alias, and a
;    lease on the radio - three addresses, none of which is in the
;    settings store, all of which the console answers on. Refusing a
;    transfer for want of net.address on that board is refusing for want
;    of a fact the board is standing on.
;
;    SO THE OPERATOR TYPES THE KEYS, AND THAT IS THE DAMAGE. Measured on
;    2026-09-10 (build 41): four temporary net.* keys had to be typed to
;    get one file off the board, and EthConfig's NetSetIPv4 then wrote
;    them over the wired row - replacing a probed, defended link-local
;    address with an unprobed typed one, with no NetAddressBound tail and
;    therefore no provenance, no console re-derivation and no record in
;    netif.pbi. The keys then had to be removed again by hand.
;
;  WHAT A TRANSFER ACTUALLY NEEDS is the thing nothing on this board can
;  know: WHICH MACHINE IS SERVING THE FILE. Everything else - this
;  board's own address, its netmask, its gateway, and which interface to
;  leave by - is already per-interface state, and NetIfForDest() is the
;  procedure that turns a destination into an interface. That is the
;  shape `tcp connect` has used since 2026-09-08 and it is the one this
;  path should have been converted to at the same time.
;
;  net.address, net.netmask and net.gateway are NOT removed and are not
;  deprecated: they are the SAVED-ADDRESS source, applied at boot and by
;  NetStaticApply through the same tail a lease takes. They simply stop
;  being a precondition for a transfer, because they never described one.
; ----------------------------------------------------------------------
Procedure.i NetXferServer()
  Define s.i
  If SettingsHas(EthKeyServer()) = 0
    PrintN("!! this board does not know which machine is serving the file, so")
    PrintN("   nothing was transferred. That is the one address a transfer cannot")
    PrintN("   work out for itself, and it is set on one line:")
    PrintN("     settings set net.server <a.b.c.d>           the machine serving the files")
    PrintN("   Nothing else is needed. This board's own address, its netmask, its")
    PrintN("   gateway and the interface to send over are all read from the")
    PrintN("   interface that can reach that server - type net to see them.")
    ProcedureReturn 0
  EndIf
  s = ParseDotted(SettingsGet(EthKeyServer()))
  If s < 0
    PrintN("!! the stored server address is not four numbers separated by full")
    PrintN("   stops, so nothing was transferred. Type settings set net.server <a.b.c.d> again.")
    PrintN("   A value can get into the store by hand as well - through settings")
    PrintN("   set, or by editing SETTINGS.TXT on another machine - and that path")
    PrintN("   does not check it, which is why it is checked here.")
    ProcedureReturn 0
  EndIf
  If s = 0
    PrintN("!! the TFTP server address is 0.0.0.0, which is not a machine. Type")
    PrintN("   settings set net.server <address> with the address of the computer that is")
    PrintN("   serving the file. Nothing was transferred.")
    ProcedureReturn 0
  EndIf
  ProcedureReturn s
EndProcedure
