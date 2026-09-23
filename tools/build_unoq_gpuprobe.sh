#!/bin/bash
# ======================================================================
#  build_unoq_gpuprobe.sh - build the Arduino UNO Q GPU CLOCK LADDER
#                           (milestone 1) and wrap it as an AArch64 UEFI
#                           application.
#
#  Run from the repo root:  bash tools/build_unoq_gpuprobe.sh
#
#  Same contract as build_unoq_conprobe.sh: -t unoq (shared A64 backend),
#  linked into the Q's confirmed-free low-bank DRAM, --entry-returns so
#  x0/x1 (ImageHandle/SystemTable) survive into Main().
#
#  READ ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqgpuprobe.unoq BEFORE FLASHING
#  THIS. On this SoC a register read of an unclocked block stalls the bus
#  and costs a power cycle; the program is built as a ladder that refuses
#  rather than falls through, and the reasoning is in its header and in
#  the vault note "Adreno 702 bring-up plan".
# ======================================================================
set -e
ROOT="$(cd "$(dirname "$0")/.." && { pwd -W 2>/dev/null || pwd; })"

# THE COMPILER IS THE ONE APPLICATION, RUN WITH --compile. Pass
# --compiler <PureMetalForge.exe> or set PMF_COMPILER; otherwise PureMetalForge
# is looked up on PATH, as tools/build.py does. The retired console compiler is
# refused by name, for the reason tools/build.py gives.
usage() {
  echo "usage: bash tools/build_unoq_gpuprobe.sh [--compiler <PureMetalForge.exe>]"
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
SRC="$ROOT/ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqgpuprobe.unoq"
IMG="$OUTDIR/anvilqgpuprobe.img"
EFI="$OUTDIR/anvilqgpuprobe.efi"

LOAD=0x70000000
STACK=0x68000000

echo ">> compiling UNO Q GPU clock ladder (shared A64 backend, -t unoq)"
echo ">> This source is in NotBuilding/ because it does not compile against Anvil main. ArduinoQ/Examples/Diagnostics/NotBuilding/README.md says what it needs."
(cd "$ROOT" && PMF_ROOT="$ROOT" "$PMF" --compile "${SRC#"$ROOT"/}" -t unoq --load-addr "$LOAD" --stack-addr "$STACK" --entry-returns -o "$IMG")

echo ">> wrapping as AArch64 UEFI application"
python "$ROOT/tools/unoq_efi_wrap.py" "$IMG" "$EFI" --load-addr "$LOAD"

echo ">> done: $EFI"
