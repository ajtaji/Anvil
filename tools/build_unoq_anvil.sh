#!/bin/bash
# ======================================================================
#  build_unoq_anvil.sh - build ANVIL for the Arduino UNO Q and wrap it as
#                        an AArch64 UEFI application.
#
#  Run from the repo root:  bash tools/build_unoq_anvil.sh
#
#  This is the Q's counterpart to the Pi 4's monitor build. The compile
#  target is ArduinoQ/Board/board.unoq, which pulls in the Q's HAL backends
#  and the SHARED Anvil core - the same core files the Pi 4 builds, not a
#  copy of them.
#
#  The image contract, and why each part is what it is:
#    -t unoq          the A64 backend, shared with pi4 (A53 and A72 are
#                     both ARMv8.0-A). Only the image contract differs.
#    --entry-returns  the whole reason this works. UEFI enters at
#                     x0 = ImageHandle, x1 = SystemTable, and this is what
#                     preserves them into Main(). It is a CONTRACT with
#                     the loader, not a placement, so it stays a flag.
#
#  WHERE THE IMAGE GOES IS NO LONGER PASSED HERE. This script used to
#  carry --load-addr 0x70000000 --stack-addr 0x68000000; ArduinoQ/Board/
#  board.pi4 now declares LoadAddress / BssAddress / StackAddress itself,
#  which is the only way the IDE can get them right - it embeds the
#  compiler and has no command line. Proven by building both ways and
#  comparing: byte-identical.
#
#  LOAD is still needed by unoq_efi_wrap.py below, which is a separate
#  program wrapping a finished image and cannot read a compiler
#  statement out of the source. If it is ever changed, change the
#  LoadAddress line in board.pi4 in the same edit - and if the two ever
#  disagree the EFI header will describe an image that was linked
#  somewhere else, which nothing here can catch.
# ======================================================================
set -e
ROOT="$(cd "$(dirname "$0")/.." && { pwd -W 2>/dev/null || pwd; })"
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "usage: bash tools/build_unoq_anvil.sh [--compiler <PureMetalForge.exe>]"
  exit 0
fi
if [ "${1:-}" = "--compiler" ]; then
  [ $# -ge 2 ] || { echo "The --compiler option needs the path to PureMetalForge.exe."; exit 2; }
  export PMF_COMPILER="$2"; shift 2
fi
[ $# -eq 0 ] || { echo "This script does not know the argument '$1'."; exit 2; }
IMG="$ROOT/build/unoq/anvil.img"
EFI="$ROOT/build/unoq/anvil.efi"

# Must match the LoadAddress line in ArduinoQ/Board/board.unoq - used
# only by the EFI wrapper below, not by the compile.
LOAD=0x70000000

# THE MONITOR IS BUILT BY tools/build.py AND NOTHING ELSE. It stages the
# compiler, pins PMF_ROOT, and raises the board's build number through
# tools/build_count.py; a second path that compiled board.unoq directly
# would produce a build nobody could tell apart from the last one.
echo ">> building Anvil for the Arduino UNO Q with tools/build.py unoq"
python "$ROOT/tools/build.py" unoq

echo ">> wrapping as AArch64 UEFI application"
python "$ROOT/tools/unoq_efi_wrap.py" "$IMG" "$EFI" --load-addr "$LOAD"

echo ">> done: $EFI"
