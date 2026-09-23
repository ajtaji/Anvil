#!/bin/bash
# ======================================================================
#  deploy_unoq_efi.sh - stage ANY Anvil UNO Q UEFI application onto the
#  board, boot it once, and come back to Debian. REVERSIBLE.
#
#  This is deploy_unoq_coreproof.sh generalised. That script proved the
#  path on real silicon (2026-08-31) but hardwired one .efi, one loader
#  entry id and one readback tool; the console work needs to cycle several
#  different images through the same path, so the path itself is the
#  script and the image is an argument.
#
#  The mechanism, unchanged from the proven original:
#    1. scp the .efi into /boot/efi/EFI/anvil/
#    2. write a Boot Loader Spec type-1 entry for it (Debian stays DEFAULT,
#       so a failed image always comes back on the next power cycle)
#    3. inject LoaderEntryOneShot into U-Boot's ubootefi.var - efivarfs is
#       mounted read-only under U-Boot so `bootctl set-oneshot` cannot be
#       used, and the store is edited offline with tools/ubootefi_var.py
#    4. reboot, wait for the board to run the app and reset back to Debian
#    5. pull ubootefi.var (and anything the app wrote to the ESP) back
#
#  THE ONE-SHOT VALUE MUST END IN .conf. On this board's systemd-boot
#  (257.x) the entry id IS the .conf filename; setting the one-shot to the
#  bare id matches no entry, systemd-boot silently consumes it and boots
#  Debian, and the app never runs. Confirmed on silicon 2026-08-31.
#
#  Usage:
#     tools/deploy_unoq_efi.sh <path-to.efi> <entry-id> [user@host] [--go]
#                              [--pull <esp-relative-path> ...]
#
#  DRY-RUN BY DEFAULT: it prints every command and touches nothing until
#  --go is passed.
# ======================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && { pwd -W 2>/dev/null || pwd; })"

GO=0
HOST="arduino@192.168.1.17"
EFI=""
ENTRY_ID=""
PULL=()

usage() {
  echo "usage: $0 <path-to.efi> <entry-id> [user@host] [--go] [--pull <esp-path>]..."
  echo "       --go   actually run (without it this is a dry run and touches nothing)"
}

# AN UNRECOGNISED ARGUMENT IS A STOP, NOT A SHRUG (tid 502's shape, swept
# 2026-09-03). The old parser dropped anything it did not match: `--Go`,
# `--dry`, a stray third path - all silently ignored, the script then
# printed its dry run and exited 0, which reads exactly like a deploy that
# worked. Every unknown word now names itself and exits non-zero.
while [ $# -gt 0 ]; do
  case "$1" in
    --go)   GO=1 ;;
    --pull) shift
            [ $# -gt 0 ] || { echo "!! --pull needs an ESP-relative path"; usage; exit 2; }
            PULL+=("$1") ;;
    -*)     echo "!! not an option this script knows: $1"; usage; exit 2 ;;
    *@*)    HOST="$1" ;;
    *)      if   [ -z "$EFI" ];      then EFI="$1"
            elif [ -z "$ENTRY_ID" ]; then ENTRY_ID="$1"
            else echo "!! too many arguments; did not expect: $1"; usage; exit 2
            fi ;;
  esac
  shift
done

[ -n "$EFI" ]      || { usage; exit 1; }
[ -n "$ENTRY_ID" ] || { echo "!! an entry id is required (it names loader/entries/<id>.conf)"; exit 1; }
[ -f "$EFI" ]      || { echo "!! no such image: $EFI"; exit 1; }

BASE="$(basename "$EFI")"
LOADER_GUID="4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"
ESP="/boot/efi"
OUT="${TMPDIR:-/tmp}"

run() {
  echo "+ $*"
  if [ "$GO" = "1" ]; then eval "$*"; fi
}

echo "== deploy $BASE as '$ENTRY_ID' to $HOST   (GO=$GO; 0 = dry-run) =="

run "scp '$EFI' $HOST:/tmp/$BASE"
run "ssh $HOST 'sudo mkdir -p $ESP/EFI/anvil /home/arduino/anvil_backup && sudo cp /tmp/$BASE $ESP/EFI/anvil/$BASE'"

run "ssh $HOST 'printf \"title Anvil UNO Q $ENTRY_ID\\nefi /EFI/anvil/$BASE\\n\" | sudo tee $ESP/loader/entries/$ENTRY_ID.conf >/dev/null'"

run "scp $HOST:$ESP/ubootefi.var $OUT/ubootefi.var.in"
run "python '$ROOT/tools/ubootefi_var.py' add $OUT/ubootefi.var.in $OUT/ubootefi.var.out $LOADER_GUID LoaderEntryOneShot --str '$ENTRY_ID.conf' --attr 0x7"
run "scp $OUT/ubootefi.var.out $HOST:/tmp/ubootefi.var.out"
run "ssh $HOST 'sudo cp $ESP/ubootefi.var /home/arduino/anvil_backup/ubootefi.var.bak 2>/dev/null || true; sudo cp /tmp/ubootefi.var.out $ESP/ubootefi.var'"

run "ssh $HOST 'sudo systemctl reboot' || true"
echo "+ (waiting for the board to run $BASE and return to Debian)"
if [ "$GO" = "1" ]; then
  sleep 25
  for i in $(seq 1 72); do
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$HOST" true 2>/dev/null; then break; fi
    sleep 5
  done
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" true 2>/dev/null \
    || { echo "!! the board did not come back on SSH. It boots Debian by default, so power-cycle it."; exit 1; }
fi

run "scp $HOST:$ESP/ubootefi.var $OUT/ubootefi.var.after"
for p in ${PULL+"${PULL[@]}"}; do
  # the app may legitimately not have created it; a missing pull is a
  # FINDING, reported, not a failure that aborts the run.
  echo "+ scp $HOST:$ESP/$p $OUT/$(basename "$p")"
  if [ "$GO" = "1" ]; then
    scp "$HOST:$ESP/$p" "$OUT/$(basename "$p")" 2>/dev/null \
      && echo "   pulled $(basename "$p")" \
      || echo "   !! NOT PRESENT on the ESP: $p"
  fi
done

echo ""
echo "== artifacts in $OUT: ubootefi.var.after ${PULL+${PULL[*]}} =="
echo "== to REVERT (Debian was never displaced): =="
echo "   ssh $HOST 'sudo rm -f $ESP/loader/entries/$ENTRY_ID.conf $ESP/EFI/anvil/$BASE'"
