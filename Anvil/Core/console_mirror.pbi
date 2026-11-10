; Hardware-neutral bounded screen/style and auxiliary output taps.
#UART_MIRROR_BYTES = 8192      ; a comfortable screenful and then some

; SCREEN-ONLY STYLE SIDEBAND. These values never enter the PL011 byte
; stream and never enter the auxiliary/network mirror. They travel beside
; each byte in the primary screen mirror so colouring the framebuffer
; cannot change the console protocol that the host tools consume.
XIncludeFile "Anvil/Core/console_style.pbi"

Global Dim uart_mirror.a[#UART_MIRROR_BYTES]
Global Dim uart_mirrorStyle.a[#UART_MIRROR_BYTES]
Global uart_screenStyle.i
Global uart_mirrorReadStyle.i
; A SECOND, independent output tap. The primary mirror above has one
; consumer (the HDMI console drains it with UartMirrorGet); a wireless
; console needs the same bytes without stealing them from the screen,
; so it drains this parallel ring instead. Generic on purpose - it is
; an 'aux output tap', not a Wi-Fi thing - so any target's second sink
; uses it the same way.
Global Dim uart_aux.a[#UART_MIRROR_BYTES]
Global uart_auxOn.i
Global uart_auxHead.i
Global uart_auxTail.i
Global uart_auxLost.i
; A FLUSH CALLBACK. When output is produced faster than the prompt's
; wait loop drains the aux tap - a long command printing forty lines
; before it returns - the ring would overflow and the far end would
; see only the tail. A consumer (the wireless console) registers a
; flush here and uart_AuxPut calls it on each line and before the ring
; fills, so the output goes out AS IT IS PRODUCED. Generic: uart.pi4
; does not know what the sink is.
Declare.i ConsoleMirrorCallbackIdle()
Procedure.i ConsoleMirrorCallbackIdle() : ProcedureReturn 0 : EndProcedure
Global *uart_auxFlush = @ConsoleMirrorCallbackIdle
*uart_auxFlush = 0
Global uart_auxBusy.i
; BULK MODE. Normally the flush fires on every line boundary so a command's
; output feels live. A bulk dump (the screenshot's tens of thousands of short
; run-lines) would then send one tiny datagram PER LINE - a firehose that
; overruns the radio's and the host's buffers and drops packets mid-stream.
; In bulk mode the per-line trigger is suppressed and only the fill-high rule
; fires, so lines coalesce into full ~1 KB datagrams: same bytes, ~16x fewer
; packets. It changes only WHEN the tap flushes, never WHAT - and the serial
; path never touches this ring, so it is unaffected either way.
Global uart_auxBulk.i
Global uart_mirrorOn.i         ; 0 until somebody asks for it
Global uart_mirrorHead.i       ; next slot to write
Global uart_mirrorTail.i       ; next slot to read
Global uart_mirrorLost.i       ; characters the ring could not hold
; The primary mirror has the same producer-side safety valve as the aux
; tap, but its callback has a deliberately narrower contract: move bytes
; into the terminal MODEL only. It must not paint, poll a network, or print.
; That separation lets a command emit arbitrarily many lines without an
; 8 KiB loss window while still batching the expensive screen render at the
; next ScreenPump after the command returns.
Global *uart_mirrorDrain = @ConsoleMirrorCallbackIdle
*uart_mirrorDrain = 0
Global uart_mirrorBusy.i

; Turn the mirror on or off. Off also empties it: a console that is
; switched on again should show what happens next, not a backlog from
; before it existed.
Procedure UartMirror(on.i)
  uart_mirrorOn = on
  If on = 0
    uart_mirrorHead = 0
    uart_mirrorTail = 0
  EndIf
EndProcedure

Procedure.i UartMirrorOn()
  ProcedureReturn uart_mirrorOn
EndProcedure

; Select the style copied beside subsequently mirrored screen bytes. The
; raw byte is still written once, unchanged, to PL011 and to the network
; tap. Unknown styles are deliberately reduced to normal rather than
; leaking arbitrary state into the renderer.
Procedure UartScreenStyle(style.i)
  If style = #UART_SCREEN_STYLE_PROMPT
    uart_screenStyle = #UART_SCREEN_STYLE_PROMPT
  Else
    uart_screenStyle = #UART_SCREEN_STYLE_NORMAL
  EndIf
EndProcedure

; Register the model-only drain called while output is being produced, or 0
; for none. The callback runs inside UartWrite and MUST NOT print. A guard is
; applied by uart_MirrorPut even though the intended console callback never
; re-enters output.
Procedure UartMirrorSetDrain(*fn)
  *uart_mirrorDrain = *fn
EndProcedure

; The next mirrored character, or -1 if there is nothing waiting.
; -1 and not 0, because 0 is a character.
Procedure.i UartMirrorGet()
  Define c.i
  If uart_mirrorTail = uart_mirrorHead
    ProcedureReturn -1
  EndIf
  c = uart_mirror[uart_mirrorTail] & $FF
  uart_mirrorReadStyle = uart_mirrorStyle[uart_mirrorTail] & $FF
  uart_mirrorTail = uart_mirrorTail + 1
  If uart_mirrorTail >= #UART_MIRROR_BYTES
    uart_mirrorTail = 0
  EndIf
  ProcedureReturn c
EndProcedure

; How many characters the ring had to throw away. Print it somewhere.
Procedure.i UartMirrorLost()
  ProcedureReturn uart_mirrorLost
EndProcedure

; ----------------------------------------------------------------------
;  LOOKING AT THE RING WITHOUT EMPTYING IT
;
;  Added 2026-08-26. UartMirrorGet() consumes, which is right for a
;  console that draws every character as it arrives - and wrong for one
;  that wants to know what is coming BEFORE it starts drawing.
;
;  WHY A CONSOLE WOULD WANT THAT, because it is not obvious and the pair
;  below is otherwise just API surface. A screen console handed more
;  full lines than it has rows will draw every one of them and then
;  scroll all but the last screenful straight off the top. On the Pi 4's
;  HDMI surface a scroll moves several megabytes, so those are the most
;  expensive characters in the system and NOT ONE of them is still on
;  the glass when the drawing stops. A console that can count the line
;  feeds first can skip the doomed ones and draw only what survives,
;  which is the difference between a board that looks hung and one that
;  does not.
;
;  READ ONLY, both of them. Neither moves the tail, so the drawing loop
;  still consumes through UartMirrorGet() exactly as before and nothing
;  that does not call these can behave differently.
;
;  UartMirrorAt(0) is the OLDEST character waiting - the next one
;  UartMirrorGet() would return - and index n-1 is the newest, where n
;  is UartMirrorCount(). An index outside that range returns -1 rather
;  than a byte of whatever the ring last held there: a caller that walks
;  off the end should see something impossible, not a stale character
;  that looks real.
; ----------------------------------------------------------------------
Procedure.i UartMirrorCount()
  Define n.i
  n = uart_mirrorHead - uart_mirrorTail
  If n < 0
    n = n + #UART_MIRROR_BYTES
  EndIf
  ProcedureReturn n
EndProcedure

; Style belonging to the byte most recently returned by UartMirrorGet().
; The consumer reads it after the byte; no second queue cursor can drift.
Procedure.i UartMirrorReadStyle()
  ProcedureReturn uart_mirrorReadStyle
EndProcedure

; Leave two KiB of headroom. Newlines normally drain much sooner; this rule
; is what makes one unusually long line lossless as well.
Procedure.i UartMirrorFillHigh()
  If UartMirrorCount() > (#UART_MIRROR_BYTES - 2048)
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i UartMirrorAt(i.i)
  Define k.i
  If i < 0 Or i >= UartMirrorCount()
    ProcedureReturn -1
  EndIf
  k = uart_mirrorTail + i
  If k >= #UART_MIRROR_BYTES
    k = k - #UART_MIRROR_BYTES
  EndIf
  ProcedureReturn uart_mirror[k] & $FF
EndProcedure

Procedure uart_MirrorPut(c.i)
  Define nxt.i
  nxt = uart_mirrorHead + 1
  If nxt >= #UART_MIRROR_BYTES
    nxt = 0
  EndIf
  If nxt = uart_mirrorTail
    ; Full. Keep what is already queued and count this one lost.
    uart_mirrorLost = uart_mirrorLost + 1
    ProcedureReturn
  EndIf
  uart_mirror[uart_mirrorHead] = c & $FF
  uart_mirrorStyle[uart_mirrorHead] = uart_screenStyle & $FF
  uart_mirrorHead = nxt
  ; Drain into the shared terminal model while a long synchronous command is
  ; printing. Rendering is intentionally NOT done here: one help dump becomes
  ; many cheap model updates followed by one frame, not hundreds of frames.
  If *uart_mirrorDrain <> 0 And uart_mirrorBusy = 0
    If c = 10 Or UartMirrorFillHigh() <> 0
      uart_mirrorBusy = 1
      uart_mirrorDrain()
      uart_mirrorBusy = 0
    EndIf
  EndIf
EndProcedure

; The aux tap. Same ring discipline as the primary mirror.
Procedure UartAuxMirror(on.i)
  uart_auxOn = on
  If on = 0
    uart_auxHead = 0
    uart_auxTail = 0
  EndIf
EndProcedure

; Register the flush to call while output is being produced, or 0 for
; none. The callback MUST NOT print (it runs inside UartWrite), and it is
; re-entry guarded regardless.
Procedure UartAuxSetFlush(*fn)
  *uart_auxFlush = *fn
EndProcedure

; Turn bulk (coalescing) mode on/off for the aux tap. On for a large machine
; dump (the screenshot), off for ordinary interactive output. See the note on
; uart_auxBulk. Off is the default, so nothing changes for normal commands.
Procedure UartAuxBulk(on.i)
  If on <> 0
    uart_auxBulk = 1
  Else
    uart_auxBulk = 0
  EndIf
EndProcedure

; 1 when the aux ring is within 2 KB of full - flush before it drops.
Procedure.i UartAuxFillHigh()
  Define n.i
  n = uart_auxHead - uart_auxTail
  If n < 0
    n = n + #UART_MIRROR_BYTES
  EndIf
  If n > (#UART_MIRROR_BYTES - 2048)
    ProcedureReturn 1
  EndIf
  ProcedureReturn 0
EndProcedure

Procedure.i UartAuxOn()
  ProcedureReturn uart_auxOn
EndProcedure

Procedure.i UartAuxGet()
  Define c.i
  If uart_auxTail = uart_auxHead
    ProcedureReturn -1
  EndIf
  c = uart_aux[uart_auxTail] & $FF
  uart_auxTail = uart_auxTail + 1
  If uart_auxTail >= #UART_MIRROR_BYTES
    uart_auxTail = 0
  EndIf
  ProcedureReturn c
EndProcedure

Procedure uart_AuxPut(c.i)
  Define nxt.i
  nxt = uart_auxHead + 1
  If nxt >= #UART_MIRROR_BYTES
    nxt = 0
  EndIf
  If nxt = uart_auxTail
    uart_auxLost = uart_auxLost + 1
    ProcedureReturn
  EndIf
  uart_aux[uart_auxHead] = c & $FF
  uart_auxHead = nxt
  ; Flush on a line boundary or when the ring is filling, so a long
  ; command's output reaches the far end instead of overflowing. Guarded
  ; against re-entry: a flush that itself printed would recurse here. In
  ; bulk mode the per-line trigger is off, so a many-thousand-line dump
  ; coalesces into full datagrams (fill-high) instead of one per line.
  If *uart_auxFlush <> 0 And uart_auxBusy = 0
    If (uart_auxBulk = 0 And c = 10) Or UartAuxFillHigh() <> 0
      uart_auxBusy = 1
      uart_auxFlush()
      uart_auxBusy = 0
    EndIf
  EndIf
EndProcedure
