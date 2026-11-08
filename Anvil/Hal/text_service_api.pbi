; SPDX-License-Identifier: MIT
; Portable cell-text protocol. Cells are u32: BMP code point in bits0..15,
; foreground xterm256 index16..23, background index24..31. No raw kernel RAM
; or device address is exposed. Coordinates and extents are in cells, not pixels.
#NTX_SERVICE_SLOT=208
#NTX_SERVICE_ABI_MINOR=16
#NTX_MAGIC=$3158544E ; little-endian NTX1
#NTX_MAJOR=1
#NTX_MINOR=0
#NTX_QUERY=0
#NTX_OPEN=1
#NTX_WRITE=2
#NTX_FILL=3
#NTX_CURSOR=4
#NTX_SCROLL=5
#NTX_PRESENT=6
#NTX_CLOSE=7
#NTX_ERR_ARGS=-22500
#NTX_ERR_STATE=-22501
#NTX_ERR_BUSY=-22502
#NTX_ERR_PROVIDER=-22503
#NTX_ERR_GEOMETRY=-22504
#NTX_ERR_UNBOUND=-22505
#NTX_ERR_TIMEOUT=-22506
#NTX_CELL_BMP_XTERM256=1
Structure NativeTextApi Align #PB_Structure_AlignC
 magic.l : major.l : minor.l : bytes.l
 format.i : maxWriteCells.i : dispatch.i
EndStructure
Structure NativeTextOpenRequest Align #PB_Structure_AlignC
 columns.i : rows.i : cellWidth.i : cellHeight.i
EndStructure
Structure NativeTextWriteRequest Align #PB_Structure_AlignC
 x.i : y.i : width.i : height.i : cells.i : stride.i
EndStructure
Structure NativeTextFillRequest Align #PB_Structure_AlignC
 x.i : y.i : width.i : height.i : cell.i
EndStructure
Structure NativeTextCursorRequest Align #PB_Structure_AlignC
 x.i : y.i : style.i
EndStructure
Structure NativeTextScrollRequest Align #PB_Structure_AlignC
 top.i : bottom.i : lines.i : cell.i
EndStructure
