; SPDX-License-Identifier: MIT
; Borrowed native Chrome target snapshot; no resource ownership is transferred.
Structure NeonVkTargetInfo Align #PB_Structure_AlignC
  device.i : renderPass.i : framebuffer.i
  logicalW.i : logicalH.i : physicalW.i : physicalH.i
  pitch.i : rotation.i : generation.i : wsi.i
EndStructure
