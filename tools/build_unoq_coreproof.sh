#!/bin/bash
# ======================================================================
#  build_unoq_coreproof.sh - build the Arduino UNO Q CORE-ON-Q proof and
#                            wrap it as an AArch64 UEFI application.
#
#  Run from the repo root:  bash tools/build_unoq_coreproof.sh
#
#  Unlike the older build_unoq_probe.sh (which used -t pi4 as a stopgap
#  before the unoq generator was wired), this builds with -t unoq. That
#  target reuses the SAME A64 backend and Architecture string as pi4 and
#  is verified byte-identical to it; the A53 runs the same ARMv8.0-A ISA
#  as the Pi 4's A72. The image touches only architectural system
#  registers, DRAM and the runtime UEFI SystemTable - no BCM2711
#  peripheral - so it is fully portable to the Q.
#
#  Output paths are Q-specific (under build/unoq/diagnostics/) so a concurrent
#  compile for another target does not clobber these intermediates.
# ======================================================================
set -e
# PureMetalForge.exe is a native Windows binary, so ROOT must be a Windows-form path
# (C:/...). Under MSYS/Git-Bash `pwd -W` yields that; elsewhere fall back.
ROOT="$(cd "$(dirname "$0")/.." && { pwd -W 2>/dev/null || pwd; })"

# THE COMPILER IS THE ONE APPLICATION, RUN WITH --compile. Pass
# --compiler <PureMetalForge.exe> or set PMF_COMPILER; otherwise PureMetalForge
# is looked up on PATH, as tools/build.py does. The retired console compiler is
# refused by name, for the reason tools/build.py gives.
usage() {
  echo "usage: bash tools/build_unoq_coreproof.sh [--compiler <PureMetalForge.exe>]"
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
SRC="$ROOT/ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqcoreproof.unoq"
IMG="$OUTDIR/anvilqcoreproof.img"
EFI="$OUTDIR/anvilqcoreproof.efi"

# Link base in the Q's free low-bank DRAM (0x63900000-0x7d9fffff). The
# image is position-independent so UEFI may load it anywhere; this only
# has to pass the target's load-base check. Stack top is absolute and
# inside the confirmed free block.
LOAD=0x70000000
STACK=0x68000000

echo ">> compiling core-on-Q proof (shared A64 backend, -t unoq)"
echo ">> This source is in NotBuilding/ because it does not compile against Anvil main. ArduinoQ/Examples/Diagnostics/NotBuilding/README.md says what it needs."
(cd "$ROOT" && PMF_ROOT="$ROOT" "$PMF" --compile "${SRC#"$ROOT"/}" -t unoq --load-addr "$LOAD" --stack-addr "$STACK" --entry-returns -o "$IMG")

echo ">> wrapping as AArch64 UEFI application"
python "$ROOT/tools/unoq_efi_wrap.py" "$IMG" "$EFI" --load-addr "$LOAD"

echo ">> done: $EFI"
