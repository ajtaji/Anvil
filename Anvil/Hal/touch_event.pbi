; SPDX-License-Identifier: MIT
; Portable service touch vocabulary. Coordinates are logical screen pixels;
; the resident board/display owner performs rotation and scaling once.
#HW_TOUCH_DOWN   = 0
#HW_TOUCH_MOVE   = 1
#HW_TOUCH_UP     = 2
#HW_TOUCH_CANCEL = 3
Structure AnvilTouchEvent Align #PB_Structure_AlignC
  x.l : y.l : id.l : state.l
  ticks.q
  pressure.l : reserved.l
EndStructure
