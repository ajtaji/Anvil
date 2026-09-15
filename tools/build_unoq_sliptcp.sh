#!/bin/bash
# ======================================================================
#  build_unoq_sliptcp.sh - build the Arduino UNO Q ICMP AND TCP RUN and
#                            wrap it as an AArch64 UEFI application.
#
#  Run from the repo root:  bash tools/build_unoq_sliptcp.sh
#
#  Same image contract as the other UNO Q diagnostics: -t unoq (the
#  shared A64 backend), linked into the Q's confirmed-free low-bank DRAM
#  at 0x70000000 with the stack at 0x68000000, and --entry-returns so
#  that x0 and x1 - the UEFI ImageHandle and SystemTable - survive into
#  Main().
#
#  ***UNLIKE EVERY OTHER UNO Q DIAGNOSTIC, THIS ONE WRITES REGISTERS AND
#  CAN HANG THE BOARD.*** It drives QUP serial engine 4 at 0x04A90000
#  directly. ArduinoQ/Board/hw_addr_q.unoq classifies that window as
#  UNKNOWN because on this SoC a read of a block whose clock is gated
#  STALLS THE BUS rather than faulting, and the recovery is the power
#  switch. The image accepts that risk once, deliberately, and says so at
#  the line that takes it. Read the header of
#  ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqsliptcp.unoq before deploying it.
#
#  ***AND IT TAKES THE CONSOLE.*** Serial engine 4 is the firmware
#  console and Debian's ttyMSM0. While this image runs, that wire carries
#  SLIP frames instead of text. The transcript therefore goes to
#  \EFI\anvil\qslipbench.log on the EFI System Partition and to the
#  AnvilQTxt variable; pull it after the run.
#
#  BEFORE DEPLOYING:
#    1. Wire the 1.8 V adapter to JCTL - TX on pin 4, RX on pin 6, ground
#       on pin 1 or 7, crossed, VCCIO measured at 1.8 V FIRST. A 3.3 V or
#       5 V adapter on those pins can destroy the part; the pin table and
#       the two safe options are in the vault note
#       `Arduino UNO Q\UNO Q console UART - the SE4 header pins`.
#    2. Start the host end and leave it running:
#         python tools/q_slip_host.py --port COM<n> --baud 115200 \
#                --dump _work/bench.cap
#
#  GATES, both of which must be green before this is worth deploying:
#    python tools/a64/a64_qgeniuart_check.py
#    python tools/a64/a64_qslipgeni_check.py
# ======================================================================
set -e
ROOT="$(cd "$(dirname "$0")/.." && { pwd -W 2>/dev/null || pwd; })"

# THE COMPILER IS THE ONE APPLICATION, RUN WITH --compile. Pass
# --compiler <PureMetalForge.exe> or set PMF_COMPILER; otherwise PureMetalForge
# is looked up on PATH, as tools/build.py does. The retired console compiler is
# refused by name, for the reason tools/build.py gives.
usage() {
  echo "usage: bash tools/build_unoq_sliptcp.sh [--compiler <PureMetalForge.exe>]"
}
while [ $# -gt 0 ]; do
  case "$1" in
    --compiler) [ $# -ge 2 ] || { echo "The --compiler option needs the path to PureMetalForge.exe."; usage; exit 2; }
                PMF_COMPILER="$2"; shift ;;
    -h|--help)  usage; exit 0 ;;
    *)          echo "This script does not know the argument '$1'."; usage; exit 2 ;;
  esac
  shift
done
PMF="${PMF_COMPILER:-}"
if [ -z "$PMF" ]; then
  for candidate in PureMetalForge.exe PureMetalForge.linux PureMetalForge; do
    PMF="$(command -v "$candidate" 2>/dev/null || true)"
    [ -n "$PMF" ] && break
  done
fi
if [ -z "$PMF" ]; then
  echo "The PureMetal compiler was not found. Pass --compiler <PureMetalForge.exe> or set PMF_COMPILER."
  exit 1
fi
case "$(basename "$PMF" | tr 'A-Z' 'a-z')" in
  pmfc|pmfc.*|pmfc_*)
    echo "$PMF is the retired console compiler. Pass --compiler <PureMetalForge.exe> or set PMF_COMPILER to the application, which compiles with --compile."
    exit 1 ;;
esac
OUTDIR="$ROOT/build/unoq/diagnostics"
mkdir -p "$OUTDIR"
SRC="$ROOT/ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqsliptcp.unoq"
IMG="$OUTDIR/anvilqsliptcp.img"
EFI="$OUTDIR/anvilqsliptcp.efi"

LOAD=0x70000000
STACK=0x68000000

echo ">> compiling the UNO Q SLIP bench run (-t unoq)"
echo ">> This source is in NotBuilding/ because it does not compile against Anvil main. ArduinoQ/Examples/Diagnostics/NotBuilding/README.md says what it needs."
(cd "$ROOT" && PMF_ROOT="$ROOT" "$PMF" --compile "${SRC#"$ROOT"/}" -t unoq --load-addr "$LOAD" --stack-addr "$STACK" --entry-returns -o "$IMG")

echo ">> wrapping as AArch64 UEFI application"
python "$ROOT/tools/unoq_efi_wrap.py" "$IMG" "$EFI" --load-addr "$LOAD"

echo ">> done: $EFI"
echo ">> this image DRIVES SERIAL ENGINE 4 AND TAKES THE CONSOLE - read the"
echo "   header of $SRC before deploying it."
