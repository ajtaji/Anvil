#MON_SHOT_OFF_MAGIC  = 0
#MON_SHOT_OFF_SEQ    = 8       ; rises by one on every completed capture
#MON_SHOT_OFF_W      = 16      ; logical width  - what `shot` streams
#MON_SHOT_OFF_H      = 24      ; logical height
#MON_SHOT_OFF_PITCH  = 32      ; physical bytes per row of the copy
#MON_SHOT_OFF_ROT    = 40      ; 0, 90, 180 or 270
#MON_SHOT_OFF_TIER   = 48      ; #HW_TIER_CPU / _DMA / _V3D (native or Vulkan GPU)
#MON_SHOT_OFF_X0     = 56      ; the payload's x0, for a capture on return
#MON_SHOT_OFF_PANELW = 64      ; physical raster width of the copy
#MON_SHOT_OFF_PANELH = 72      ; physical raster height
#MON_SHOT_OFF_BPP    = 80      ; bytes per pixel; 4 or the capture refused
#MON_SHOT_OFF_SRC    = 88      ; #SCR_SRC_HDMI / #SCR_SRC_DSI
#MON_SHOT_OFF_WHO    = 96      ; 0 the payload asked, 1 the monitor took it
#MON_SHOT_OFF_BYTES  = 104     ; pixel bytes copied

; Who took the picture, for #MON_SHOT_OFF_WHO. Two words rather than a
; bare 0/1 so that the console line and the host tool say the same thing
; about a capture, and so a third source later is an added constant
; rather than a re-interpreted flag.
#MON_SHOT_WHO_PAYLOAD = 0      ; the payload called the service slot
#MON_SHOT_WHO_RETURN  = 1      ; the monitor took it as the payload returned
