; SPDX-License-Identifier: MIT
; One normalized key/source/modifier/cancellation vocabulary for kernel and clients.
; Existing values are retained; additional navigation keys append after 10.
#AIE_TEXT     = 1
#AIE_KEY_DOWN = 2
#AIE_KEY_UP   = 3
#AIE_CANCEL   = 4

; The named keys. These numbers are the shared vocabulary of all three
; lanes of this feature and they are not renumbered.
#AIK_ENTER          = 1
#AIK_BACKSPACE      = 2
#AIK_DELETE         = 3
#AIK_LEFT           = 4
#AIK_RIGHT          = 5
#AIK_HOME           = 6
#AIK_END            = 7
#AIK_TAB            = 8
#AIK_ESC            = 9
#AIK_CANCEL_COMMAND = 10          ; Ctrl+C semantics
#AIK_UP             = 11
#AIK_DOWN           = 12
#AIK_PAGE_UP        = 13
#AIK_PAGE_DOWN      = 14
#AIK_INSERT         = 15
#AIK_MAX            = 15

; Where an event came from. IT IS NOT DECORATION: the network console's
; ownership rules key off it - a soft keystroke is LOCAL input and
; claims the console the way a serial byte does, a byte that arrived
; from the peer does not, and merely DRAWING a keyboard claims nothing.
#AIS_PHYSICAL       = 1
#AIS_NETWORK        = 2
#AIS_TOUCH_KEYBOARD = 3
#AIS_MAX            = 3

#AIM_SHIFT = 1
#AIM_CTRL  = 2
#AIM_ALT = 4
#AIM_GUI = 8

#AIC_NONE          = 0
#AIC_FOCUS_CHANGE  = 1
#AIC_QUEUE_FULL    = 2
#AIC_TOUCH_LOST    = 3
#AIC_SCREEN_CHANGE = 4
#AIC_LAYOUT_CHANGE = 5
#AIC_CONTACT_LOST  = 6
#AIC_PAYLOAD       = 7
#AIC_DEVICE_LOST   = 8
#AIC_MAX           = 8
