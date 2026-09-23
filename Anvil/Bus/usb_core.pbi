; ======================================================================
;  USB CORE - the protocol, once, for every board
; ======================================================================
;  WHAT IS IN HERE AND WHY IT IS NOT IN A BOARD FILE. A device descriptor,
;  a configuration descriptor, the chain of interfaces, alternate
;  settings, endpoints and SuperSpeed companions nested inside it, and a
;  string descriptor are USB. They have the same shape over an xHCI
;  controller on a Raspberry Pi 4, over a DWC2 on a Raspberry Pi 3, and
;  over anything else Anvil is built for. Only the way a control transfer
;  is CARRIED differs, and that is the seam at the top of this file.
;
;  Rule 30: every library exists once. This walk had been written four
;  times in this tree before today - the mass-storage bring-up, the
;  human-interface bring-up, the hub attach and the device listing - and
;  a fifth copy was about to be added for `usb devices`. This is the one
;  the others are to be repointed at.
;
;  A .pi4 FILE CANNOT BE INCLUDED BY ANOTHER BOARD'S BUILD. The compiler
;  refuses a cross-chip include by extension, so a protocol living in a
;  chip file is not merely untidy - it is stranded, and the next board
;  physically cannot reach it. That is the practical reason this is a
;  .pbi in Anvil/Bus and not a procedure in a controller driver.
;
; ----------------------------------------------------------------------
;  THE SEAM: TWO FUNCTION POINTERS, SET BY THE BOARD
; ----------------------------------------------------------------------
;  A control transfer is the only thing this file cannot do for itself.
;  The board hands over two procedures - one that carries a control IN
;  into a caller's buffer and one that carries a control OUT from one -
;  and nothing else about the controller is visible here: no ring, no
;  doorbell, no event, no bounce buffer.
;
;  IT REFUSES RATHER THAN CRASHING WHEN NOBODY HAS BOUND IT. A null
;  pointer called is a branch to address zero and a board that stops
;  saying nothing; a refusal names the missing binding. Every entry point
;  here checks.
;
;  THE SHAPES:
;    ctrlIn (bmRequestType, bRequest, wValue, wIndex, *dst, wLength)
;        -> bytes delivered into *dst, or -1
;    ctrlOut(bmRequestType, bRequest, wValue, wIndex, *src, wLength)
;        -> bytes accepted, or -1
;  The IN takes the DESTINATION rather than leaving the bytes in a
;  controller buffer for a second call to fetch: two calls is two chances
;  to read a buffer a later transfer has already overwritten, and that
;  exact shape is what made a stale event read as a good transfer once
;  already in this tree.
; ======================================================================

; ---- descriptor types. USB 2.0 table 9-5.
#USB_DT_DEVICE = $01
#USB_DT_CONFIG = $02
#USB_DT_STRING = $03
#USB_DT_INTERFACE = $04
#USB_DT_ENDPOINT = $05
; USB 3.2 section 9.6.7 - it follows the endpoint it describes.
#USB_DT_SS_ENDPOINT_COMPANION = $30

; ---- how much of a device this file will hold at once.
;
; STATED, NOT HIDDEN. A configuration descriptor longer than this is read
; as far as it fits and REPORTED as truncated; it is never silently cut,
; and it is never a reason to pretend the device is not there. 512 is the
; largest control transfer the controllers in this tree carry in one go,
; so the buffer is not the smaller of the two limits.
#USB_CFG_BYTES = 512
#USB_DEV_BYTES = 32
; One string, flattened to ASCII, with room for its terminator.
#USB_STR_BYTES = 64
#USB_STRINGS   = 3

; What a string row means. THREE STATES AND NOT TWO: a device that has no
; serial number and a device that has one and would not hand it over are
; different facts, and printing a blank line for both is how a reader
; concludes the first when the truth is the second.
#USB_STR_NONE     = 0
#USB_STR_READ     = 1
#USB_STR_NOT_READ = 2
; Which string, in the order the device descriptor names them - USB 2.0
; table 9-8 puts iManufacturer, iProduct and iSerialNumber at 14, 15, 16.
#USB_STR_MANUFACTURER = 0
#USB_STR_PRODUCT      = 1
#USB_STR_SERIAL       = 2

; US English. Every device that has strings at all supports it, and a
; device that answers nothing is a fact the caller prints rather than an
; error to swallow.
#USB_LANGID_EN_US = $0409

Global *usbc_ctrlIn = 0
Global *usbc_ctrlOut = 0

Global Dim usbc_dev.a[#USB_DEV_BYTES]
Global Dim usbc_cfg.a[#USB_CFG_BYTES]
Global Dim usbc_str.a[192]            ; #USB_STRINGS * #USB_STR_BYTES
; A string descriptor may be 255 bytes and is UTF-16, so it is read whole
; into its own scratch and flattened from there. It does NOT borrow a
; string slot: the first version of this did, and the slot it borrowed was
; the serial number's - which would have been overwritten by the read that
; was meant to fill it.
Global Dim usbc_scratch.a[256]
Global Dim usbc_strState.i[#USB_STRINGS]
Global usbc_devLen.i = 0
Global usbc_cfgHeld.i = 0             ; bytes of the STORE'S configuration
                                      ; descriptor - the walk's bound
; How many bytes the LAST UsbGetConfiguration copied, whoever's buffer it
; was copying into. Kept apart from the store's own count on purpose: the
; mass-storage driver reads a configuration descriptor into ITS buffer,
; and if that count became the walk's bound the walk would read this
; file's buffer with somebody else's length.
Global usbc_lastHeld.i = 0
Global usbc_cfgWant.i = 0             ; wTotalLength, as the DEVICE said
Global usbc_loaded.i = 0              ; 1 when the store describes a device

; The board binds itself once, before anything enumerates.
Procedure UsbCoreSetHost(*in, *out)
  *usbc_ctrlIn = *in
  *usbc_ctrlOut = *out
EndProcedure

Procedure.i UsbCoreBound() : ProcedureReturn Bool(*usbc_ctrlIn <> 0) : EndProcedure

; ----------------------------------------------------------------------
;  ONE DESCRIPTOR REQUEST. Standard device-to-host, GET_DESCRIPTOR - USB
;  2.0 section 9.4.3, bmRequestType $80, bRequest 6, wValue the type in
;  the high byte and the index in the low.
; ----------------------------------------------------------------------
Procedure.i UsbGetDescriptor(dtype.i, dindex.i, langid.i, *dst, wLength.i)
  If *usbc_ctrlIn = 0
    ProcedureReturn -1
  EndIf
  ; A leading star on the invocation dereferences the returned byte count.
  ProcedureReturn usbc_ctrlIn($80, 6, ((dtype & $FF) << 8) | (dindex & $FF), langid, *dst, wLength)
EndProcedure

; ----------------------------------------------------------------------
;  UsbGetConfiguration - the WHOLE configuration descriptor.
;
;  TWO STEPS, BECAUSE THE LENGTH IS INSIDE THE THING BEING READ. USB 2.0
;  table 9-10 puts wTotalLength at bytes 2-3, so there is no way to know
;  how much to ask for without first asking for the nine bytes that say.
;  Asking for a fixed number and refusing anything longer is the shape
;  that reported every UAS-capable stick as "not mass storage" without a
;  word (forum 928).
;
;  RETURNS wTotalLength - what the DEVICE says the descriptor is - or -1
;  if it could not be read at all. It copies min(wTotalLength, max)
;  bytes, so a caller whose buffer is too small still learns the size it
;  needed and can refuse BY NAME instead of shrugging. The answer is
;  deliberately not "how many bytes you got": UsbConfigurationHeld() is
;  that, and a caller that conflates them has lost the distinction that
;  makes the refusal sayable.
; ----------------------------------------------------------------------
Procedure.i UsbGetConfiguration(*dst, max.i)
  Define n.i
  Define total.i
  Define want.i

  usbc_lastHeld = 0
  If *dst = 0 Or max < 9 Or *usbc_ctrlIn = 0
    ProcedureReturn -1
  EndIf
  n = UsbGetDescriptor(#USB_DT_CONFIG, 0, 0, *dst, 9)
  If n < 9
    ProcedureReturn -1
  EndIf
  total = PeekA(*dst + 2) | (PeekA(*dst + 3) << 8)
  If total < 9
    ProcedureReturn -1
  EndIf
  want = total
  If want > max
    want = max
  EndIf
  n = UsbGetDescriptor(#USB_DT_CONFIG, 0, 0, *dst, want)
  If n < 9
    ProcedureReturn -1
  EndIf
  If n > want
    n = want
  EndIf
  usbc_lastHeld = n
  ProcedureReturn total
EndProcedure

Procedure.i UsbConfigurationHeld() : ProcedureReturn usbc_lastHeld : EndProcedure

; ----------------------------------------------------------------------
;  UsbGetStringAscii - one string descriptor, flattened to ASCII.
;
;  USB 2.0 section 9.6.7: a string descriptor is UTF-16LE behind a
;  two-byte header, and index 0 is the list of language identifiers
;  rather than any text.
;
;  FLATTENED, NOT DECODED, and the substitution is visible. Anything
;  outside printable ASCII becomes '?' rather than being dropped: a
;  serial number with one odd character must still line up under the one
;  above it, and a silently shortened serial number is worse than a
;  visibly substituted character.
;
;  Returns the number of characters written - 0 is a legitimate empty
;  string - or -1 if the descriptor could not be read.
; ----------------------------------------------------------------------
Procedure.i UsbGetStringAscii(index.i, *dst, max.i)
  Define n.i
  Define len.i
  Define i.i
  Define c.i
  Define out.i

  If *dst = 0 Or max < 1
    ProcedureReturn -1
  EndIf
  PokeA(*dst, 0)
  If index <= 0
    ProcedureReturn 0
  EndIf
  n = UsbGetDescriptor(#USB_DT_STRING, index, #USB_LANGID_EN_US, @usbc_scratch[0], 254)
  If n < 2
    ProcedureReturn -1
  EndIf
  len = usbc_scratch[0]
  If len > n
    len = n
  EndIf
  If len < 2
    ProcedureReturn -1
  EndIf
  out = 0
  i = 2
  While i + 1 < len And out < max - 1
    c = usbc_scratch[i] | (usbc_scratch[i + 1] << 8)
    If c < 32 Or c > 126
      c = 63
    EndIf
    PokeA(*dst + out, c)
    out = out + 1
    i = i + 2
  Wend
  PokeA(*dst + out, 0)
  ProcedureReturn out
EndProcedure

; ----------------------------------------------------------------------
;  THE STORE - one device at a time, loaded on demand.
;
;  The alternative is a table filled at enumeration, which costs a
;  kilobyte per slot for a command nobody may ever type and goes stale
;  the moment a device is reconfigured. This loads the device a caller is
;  about to print and then the next one.
; ----------------------------------------------------------------------
Procedure.i usbc_StrBase(w.i)
  ProcedureReturn @usbc_str[0] + (w * #USB_STR_BYTES)
EndProcedure

; Load the CURRENTLY ADDRESSED device. The caller selects which device
; that is - that is the one thing this file cannot know - and everything
; after the selection is protocol.
;
; Returns 1, or 0 with the whole store cleared. A half-loaded view is the
; one thing a listing must never print from.
Procedure.i UsbLoadDescriptors()
  Define n.i
  Define w.i
  Define idx.i

  usbc_loaded = 0
  usbc_devLen = 0
  usbc_cfgHeld = 0
  usbc_cfgWant = 0
  w = 0
  While w < #USB_STRINGS
    usbc_strState[w] = #USB_STR_NONE
    PokeA(usbc_StrBase(w), 0)
    w = w + 1
  Wend
  If *usbc_ctrlIn = 0
    ProcedureReturn 0
  EndIf

  n = UsbGetDescriptor(#USB_DT_DEVICE, 0, 0, @usbc_dev[0], 18)
  If n < 18
    ProcedureReturn 0
  EndIf
  usbc_devLen = n

  ; A device whose descriptor is longer than the buffer still gets its
  ; front held and is SAID to be truncated; refusing it outright would
  ; hide the very device a driver author is most likely to be looking at.
  usbc_cfgWant = UsbGetConfiguration(@usbc_cfg[0], #USB_CFG_BYTES)
  If usbc_cfgWant < 9
    usbc_cfgWant = 0
    usbc_cfgHeld = 0
  Else
    usbc_cfgHeld = usbc_lastHeld
  EndIf

  ; The strings last, once the two descriptors above are safely in their
  ; own buffers.
  w = 0
  While w < #USB_STRINGS
    idx = PeekA(@usbc_dev[0] + 14 + w)
    If idx = 0
      usbc_strState[w] = #USB_STR_NONE
    Else
      n = UsbGetStringAscii(idx, usbc_StrBase(w), #USB_STR_BYTES)
      If n < 0
        usbc_strState[w] = #USB_STR_NOT_READ
        PokeA(usbc_StrBase(w), 0)
      Else
        usbc_strState[w] = #USB_STR_READ
      EndIf
    EndIf
    w = w + 1
  Wend

  usbc_loaded = 1
  ProcedureReturn 1
EndProcedure

Procedure.i UsbDescLoaded()  : ProcedureReturn usbc_loaded : EndProcedure
Procedure.i UsbDescDevLen()  : ProcedureReturn usbc_devLen : EndProcedure
Procedure.i UsbDescDevByte(k.i)
  If usbc_loaded = 0 Or k < 0 Or k >= usbc_devLen : ProcedureReturn -1 : EndIf
  ProcedureReturn usbc_dev[k]
EndProcedure
Procedure.i UsbDescCfgHeld() : ProcedureReturn usbc_cfgHeld : EndProcedure
Procedure.i UsbDescCfgWant() : ProcedureReturn usbc_cfgWant : EndProcedure
Procedure.i UsbDescStrState(w.i)
  If usbc_loaded = 0 Or w < 0 Or w >= #USB_STRINGS : ProcedureReturn #USB_STR_NONE : EndIf
  ProcedureReturn usbc_strState[w]
EndProcedure
Procedure.i UsbDescStr(w.i)
  If usbc_loaded = 0 Or w < 0 Or w >= #USB_STRINGS : ProcedureReturn "" : EndIf
  ProcedureReturn usbc_StrBase(w)
EndProcedure

; ======================================================================
;  THE WALK - bounded, and it refuses
; ======================================================================
;  A configuration descriptor is a chain of variable-length records. A
;  device that reports a length of zero sends a naive walk round forever;
;  a record that claims to run past what was actually read sends it off
;  the end of the buffer and into whatever is behind it, which then gets
;  printed as an endpoint. Every step goes through UsbCfgNext, which
;  answers -1 for both, and every caller stops and says where.
;
;  A malformed descriptor is not an exotic case. It is what somebody
;  bringing up a new device is most likely to be holding.
; ----------------------------------------------------------------------

; One byte of the loaded configuration descriptor, or -1 past the end.
Procedure.i UsbCfgByte(off.i)
  If off < 0 Or off >= usbc_cfgHeld
    ProcedureReturn -1
  EndIf
  ProcedureReturn usbc_cfg[off]
EndProcedure

; Two bytes, little-endian. -1 IF EITHER IS PAST THE END, never a half
; value built from one byte and a zero - a wMaxPacketSize that reads 64
; because its high byte fell off the end is the wrong kind of wrong.
Procedure.i UsbCfgWord(off.i)
  Define lo.i
  Define hi.i
  lo = UsbCfgByte(off)
  hi = UsbCfgByte(off + 1)
  If lo < 0 Or hi < 0
    ProcedureReturn -1
  EndIf
  ProcedureReturn lo | (hi << 8)
EndProcedure

; The offset of the descriptor after the one at off:
;   >0  the next one
;    0  there is none - the chain ended cleanly
;   -1  the chain is malformed and the walk must stop
Procedure.i UsbCfgNext(off.i)
  Define len.i
  Define held.i
  len = UsbCfgByte(off)
  held = usbc_cfgHeld
  ; A DESCRIPTOR SHORTER THAN ITS OWN HEADER IS NOT A DESCRIPTOR. Two is
  ; bLength plus bDescriptorType; a length of 0 or 1 advances the walk by
  ; nothing and loops forever, which is the failure this refuses.
  If len < 2
    ProcedureReturn -1
  EndIf
  ; And a record that claims to extend past what was read is refused
  ; rather than half-decoded from whatever follows it in memory.
  If off + len > held
    ProcedureReturn -1
  EndIf
  If off + len >= held
    ProcedureReturn 0
  EndIf
  ProcedureReturn off + len
EndProcedure

; A device or interface class, in words. USB-IF assigns these; the ones
; named here are the ones this monitor or a driver written against it is
; likely to meet, and anything else prints as unnamed rather than as a
; guess - a wrong name is worse than no name to somebody reading it to
; decide what their device is.
Procedure.i UsbClassText(cls.i, sub.i, proto.i)
  Select cls
    Case $00 : ProcedureReturn "defined at interface level"
    Case $01 : ProcedureReturn "audio"
    Case $02 : ProcedureReturn "communications"
    Case $03
      If sub = 1 And proto = 1 : ProcedureReturn "human interface, boot keyboard" : EndIf
      If sub = 1 And proto = 2 : ProcedureReturn "human interface, boot mouse" : EndIf
      If sub = 1 : ProcedureReturn "human interface, boot" : EndIf
      ProcedureReturn "human interface"
    Case $05 : ProcedureReturn "physical"
    Case $06 : ProcedureReturn "still imaging"
    Case $07 : ProcedureReturn "printer"
    Case $08
      If sub = 6 And proto = $50 : ProcedureReturn "mass storage, SCSI, Bulk-Only" : EndIf
      If sub = 6 And proto = $62 : ProcedureReturn "mass storage, SCSI, USB Attached SCSI" : EndIf
      If sub = 6 : ProcedureReturn "mass storage, SCSI" : EndIf
      ProcedureReturn "mass storage"
    Case $09 : ProcedureReturn "hub"
    Case $0A : ProcedureReturn "communications data"
    Case $0B : ProcedureReturn "smart card"
    Case $0D : ProcedureReturn "content security"
    Case $0E : ProcedureReturn "video"
    Case $0F : ProcedureReturn "personal healthcare"
    Case $10 : ProcedureReturn "audio/video"
    Case $11 : ProcedureReturn "billboard"
    Case $DC : ProcedureReturn "diagnostic"
    Case $E0
      If sub = 1 And proto = 1 : ProcedureReturn "wireless, Bluetooth" : EndIf
      ProcedureReturn "wireless"
    Case $EF : ProcedureReturn "miscellaneous"
    Case $FE : ProcedureReturn "application specific"
    Case $FF : ProcedureReturn "vendor specific"
  EndSelect
  ProcedureReturn "unnamed class"
EndProcedure

; bmAttributes of an endpoint descriptor, low two bits. USB 2.0 table 9-13.
Procedure.i UsbEpTypeText(attr.i)
  Select attr & 3
    Case 0 : ProcedureReturn "control"
    Case 1 : ProcedureReturn "isochronous"
    Case 2 : ProcedureReturn "bulk"
    Case 3 : ProcedureReturn "interrupt"
  EndSelect
  ProcedureReturn "unnamed"
EndProcedure
