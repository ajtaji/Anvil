#!/bin/bash
# ======================================================================
#  deploy_unoq_coreproof.sh - stage the Q core-on-Q proof onto the board,
#  boot it once, read the proof back, and return to Debian. REVERSIBLE.
#
#  This mirrors the PROVEN deploy path from the bring-up probe (vault:
#  "FIRST BARE-METAL IMAGE RAN ON THE A53 - 2026-08-30"): an EFI app under
#  /boot/efi/EFI/anvil/, a systemd-boot Type-1 loader entry, a one-shot
#  boot selection injected into U-Boot's ubootefi.var (efivarfs is
#  read-only under U-Boot, so bootctl set-oneshot cannot be used), reboot,
#  SSH readback, and Debian stays the default so it always comes back.
#
#  SAFETY: DRY-RUN BY DEFAULT. It prints every command without touching the
#  board. Pass --go to actually run. It was NOT executed against live
#  hardware in the session that wrote it (no SSH credential was available),
#  so review it before --go.
#
#  Usage:
#     tools/deploy_unoq_coreproof.sh [--go] [user@host]
#  Default host arduino@192.168.1.112 (SSH over hub ethernet). Requires
#  key-based login and passwordless sudo (/etc/sudoers.d/90-anvil).
# ======================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && { pwd -W 2>/dev/null || pwd; })"
EFI="$ROOT/build/unoq/diagnostics/anvilqcoreproof.efi"

GO=0
HOST="arduino@192.168.1.112"
# AN UNRECOGNISED ARGUMENT IS A STOP, NOT A SHRUG (tid 502's shape, swept
# 2026-09-03). The old loop dropped anything it did not match, so `--Go` or
# `--dry-run` left GO=0, the script printed its dry run, and it exited 0 -
# indistinguishable from a deploy that actually ran.
for a in "$@"; do
  case "$a" in
    --go) GO=1 ;;
    *@*)  HOST="$a" ;;
    *)    echo "!! not an argument this script knows: $a"
          echo "usage: $0 [--go] [user@host]"
          echo "       --go   actually run (without it this is a dry run)"
          exit 2 ;;
  esac
done

# systemd-boot's loader GUID; LoaderEntryOneShot lives under it.
LOADER_GUID="4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"
ENTRY_ID="anvil-qcore"                     # loader/entries/<ENTRY_ID>.conf
ESP="/boot/efi"

run() {
  echo "+ $*"
  if [ "$GO" = "1" ]; then eval "$*"; fi
}

echo "== deploy target: $HOST   (GO=$GO; 0 = dry-run) =="
[ -f "$EFI" ] || { echo "!! build first: bash tools/build_unoq_coreproof.sh"; exit 1; }

# 1. copy the EFI app to a temp on the board, then into the ESP with sudo,
#    keeping a backup dir exactly like the probe deploy did.
run "scp '$EFI' $HOST:/tmp/anvilqcoreproof.efi"
run "ssh $HOST 'sudo mkdir -p $ESP/EFI/anvil /home/arduino/anvil_backup && \
     sudo cp $ESP/EFI/anvil/anvilqcoreproof.efi /home/arduino/anvil_backup/ 2>/dev/null || true && \
     sudo cp /tmp/anvilqcoreproof.efi $ESP/EFI/anvil/anvilqcoreproof.efi'"

# 2. write a Boot Loader Spec type-1 entry for it (Debian stays default).
run "ssh $HOST 'printf \"title Anvil UNO Q core proof\\nefi /EFI/anvil/anvilqcoreproof.efi\\n\" \
     | sudo tee $ESP/loader/entries/$ENTRY_ID.conf >/dev/null'"

# 3. inject LoaderEntryOneShot into U-Boot's ubootefi.var. Pull the store,
#    edit it locally with ubootefi_var.py, push it back. A bad edit fails
#    U-Boot's CRC and the board just boots Debian, so this is
#    non-destructive.
#    NOTE: the one-shot VALUE must be the systemd-boot entry id, which on
#    this board's systemd-boot (257.x) is the .conf FILENAME - i.e.
#    "$ENTRY_ID.conf", NOT "$ENTRY_ID". `bootctl list` shows `id:
#    anvil-qcore.conf`; setting the one-shot to the bare "anvil-qcore"
#    matches no entry, so systemd-boot silently consumes it and boots the
#    default (Debian) - the proof never runs. Confirmed on real silicon
#    2026-08-31 (adding the .conf is what made AnvilQBin/AnvilQTxt appear).
run "scp $HOST:$ESP/ubootefi.var /tmp/ubootefi.var.in"
run "python '$ROOT/tools/ubootefi_var.py' add /tmp/ubootefi.var.in /tmp/ubootefi.var.out \
     $LOADER_GUID LoaderEntryOneShot --str '$ENTRY_ID.conf' --attr 0x7"
run "scp /tmp/ubootefi.var.out $HOST:/tmp/ubootefi.var.out"
run "ssh $HOST 'sudo cp $ESP/ubootefi.var /home/arduino/anvil_backup/ubootefi.var.bak 2>/dev/null || true && \
     sudo cp /tmp/ubootefi.var.out $ESP/ubootefi.var'"

# 4. reboot into the one-shot entry; the proof writes AnvilQBin/AnvilQTxt
#    then ResetSystem back to Debian.
run "ssh $HOST 'sudo systemctl reboot' || true"
echo "+ (waiting for the board to run the proof and return to Debian)"
if [ "$GO" = "1" ]; then
  sleep 20
  for i in $(seq 1 60); do
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$HOST" true 2>/dev/null; then break; fi
    sleep 5
  done
fi

# 5. read the proof back. ubootefi.var now carries the two NV variables.
run "scp $HOST:$ESP/ubootefi.var /tmp/ubootefi.var.proof"
run "python '$ROOT/tools/read_qcore_proof.py' /tmp/ubootefi.var.proof"

echo ""
echo "== to REVERT (remove the entry; Debian was never displaced): =="
echo "   ssh $HOST 'sudo rm -f $ESP/loader/entries/$ENTRY_ID.conf $ESP/EFI/anvil/anvilqcoreproof.efi'"
