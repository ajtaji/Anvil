#!/bin/bash
# ======================================================================
#  unoq_icc_capture.sh - capture the Arduino UNO Q's interconnect / RPM /
#                        GPU-clock state at one named point, from Debian.
#
#  Runs ON THE BOARD.  Usage:  bash unoq_icc_capture.sh <label> <outdir>
#
#  This is the Debian half of the 11ae diff: the same state is then read
#  from a bare-metal probe at the equivalent points of its own sequence,
#  and the two are diffed.  Everything here is READ-ONLY; the caller, not
#  this script, moves the GPU runtime-PM knob.
#
#  ----------------------------------------------------------------------
#  DANGER - SWEEPING A DEVICE WINDOW RESETS THIS SoC
#  ----------------------------------------------------------------------
#  Measured three times on 2026-09-06, each occurrence attributed by a
#  synced progress file written before the access:
#
#    0x04480000  bimc: interconnect@4480000      one 32-bit read -> reset
#    0x01880000  system_noc: interconnect@1880000 one 32-bit read -> reset
#    0x04690000  qcom,rpm-stats, +0x10000 sweep   -> reset, even though a
#                single read of offset 0 returns 0x000000DC quite happily
#
#  The read never returns; Debian comes back by itself a few seconds later
#  (it is the default boot entry), so the cost is a reboot rather than a
#  power cycle - but it is still a reset of the whole SoC, and the third
#  case proves the hazard is not "the NoC windows are special": a window
#  whose first word reads fine can still contain an address that resets
#  the part.
#
#  So: NO WINDOW IS SWEPT unless the whole of it has been swept before and
#  survived.  Everything else is read as an explicit list of individually
#  justified addresses, each carrying its citation.  0x01900000
#  (config_noc) is never touched at all - it is the same class of window as
#  the two that reset the board and one more data point is not worth one
#  more reset.
#
#  Swept windows, proven on silicon:
#      0x045F0000 +0x7000   rpm_msg_ram (qcom,rpm-msg-ram / mmio-sram)
# ======================================================================
set -u

LABEL="${1:?usage: unoq_icc_capture.sh <label> <outdir>}"
OUT="${2:?usage: unoq_icc_capture.sh <label> <outdir>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"

GPU=/sys/bus/platform/devices/5900000.gpu
GMU=/sys/bus/platform/devices/596a000.gmu
IOMMU=/sys/bus/platform/devices/59a0000.iommu

sudo -n mount -t debugfs none /sys/kernel/debug 2>/dev/null

# --- 1. the semantic state ------------------------------------------------
{
  echo "### unoq_icc_capture label=$LABEL utc=$(date -u +%FT%TZ)"
  echo "### uptime: $(uptime)"
  echo
  echo "### GPU runtime-PM"
  for d in "$GPU" "$GMU" "$IOMMU"; do
    printf '%-46s control=%-6s status=%s\n' "$d" \
      "$(cat $d/power/control 2>/dev/null)" \
      "$(cat $d/power/runtime_status 2>/dev/null)"
  done
  echo
  echo "### interconnect_summary"
  sudo -n cat /sys/kernel/debug/interconnect/interconnect_summary 2>&1
  echo
  echo "### clk_summary"
  sudo -n cat /sys/kernel/debug/clk/clk_summary 2>&1
  echo
  echo "### devfreq"
  for f in /sys/class/devfreq/*/; do
    echo "-- $f"
    for k in governor cur_freq min_freq max_freq available_frequencies; do
      printf '   %-24s %s\n' "$k" "$(cat $f$k 2>/dev/null)"
    done
  done
} > "$OUT/$LABEL.state.txt" 2>&1

# --- 2. the one window that is safe to sweep ------------------------------
: > "$OUT/$LABEL.progress"
echo "TRY rpm_msg_ram 0x045F0000 +0x7000" >> "$OUT/$LABEL.progress"; sync
sudo -n python3 "$HERE/unoq_devmem_dump.py" 0x045F0000 0x7000 \
     "$OUT/$LABEL.rpm_msg_ram.bin" >>"$OUT/$LABEL.progress" 2>&1 \
  && echo "OK  rpm_msg_ram" >> "$OUT/$LABEL.progress" \
  || echo "ERR rpm_msg_ram" >> "$OUT/$LABEL.progress"
sync

# --- 3. the explicit address list -----------------------------------------
# Every address here has been read on this silicon before, from Debian or
# from the bare-metal probe or both, and carries its source citation.  The
# .list file is the diff's unit: the bare-metal probe reads exactly these.
GATE=""
[ "$(cat $GPU/power/runtime_status 2>/dev/null)" = "active" ] && GATE="--gated"
sudo -n python3 "$HERE/unoq_devmem_words.py" $GATE "$HERE/unoq_icc_addrs.txt" \
     "$OUT/$LABEL.words.txt" 2>>"$OUT/$LABEL.progress"
echo "DONE" >> "$OUT/$LABEL.progress"
cat "$OUT/$LABEL.progress"
