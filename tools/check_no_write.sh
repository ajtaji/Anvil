#!/bin/bash
# ======================================================================
#  check_no_write.sh - prove, from the assembled listing, that an image
#  never STORES to a given 32-bit MMIO address.
#
#  WHY THIS EXISTS AS A SEPARATE TOOL. check_no_secvid.sh proves one
#  address and names it in every message, which is right: that register
#  hung this board three times and the check should be impossible to
#  misread. But "this probe only READS the block" is a claim made about a
#  different address on every campaign round, and the last time such a
#  claim was made from a compile-time constant instead of from the
#  emitted code, the write was still in the image and the board hung.
#  A CONSTANT IS NOT PROOF. Neither is a promise in a comment.
#
#  HOW. Identical detection logic to check_no_secvid.sh, which is the
#  point - one shape, verified once. The compiler materialises a 32-bit
#  address as a decimal pair:
#      movz xN, #<low16>
#      movk xN, #<high16>, lsl #16
#  and the call that follows within a few instructions decides what the
#  address was for: `bl rd32` is a read, `bl wr32` is a write. Both forms
#  are preceded by a `str` of the address onto the stack as a call
#  argument, so looking for `str` alone reports a write for every read.
#
#  A POSITIVE CONTROL runs first, exactly as in check_no_secvid.sh: the
#  same logic is pointed at an address the caller states the image DOES
#  write. If the control does not find that write, the checker is broken
#  and says so rather than passing. A checker with no control is a
#  checker that cannot fail, and one of those reported PASS against a
#  leftover listing once already.
#
#  Usage:
#    tools/check_no_write.sh <listing.asm> <hex-addr-that-must-not-be-written> \
#                            <hex-addr-the-image-does-write> [source]
#
#  Example, the read-only IOMMU survey of section 11t (sACR):
#    tools/check_no_write.sh build/qgpu5.img.asm 059A0010 0593E00C \
#        ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqgpuprobe.unoq
# ======================================================================
set -u

LST="${1:-}"
TARGET="${2:-}"
CONTROL="${3:-}"
SRC="${4:-}"

usage() {
  echo "usage: $0 <listing.asm> <hex-addr-not-written> <hex-addr-control> [source]"
  echo "   the control address must be one this image genuinely DOES write,"
  echo "   otherwise the checker cannot prove it is working and refuses."
}

[ -n "$LST" ] && [ -f "$LST" ]  || { echo "!! no listing: '$LST'"; usage; exit 2; }
[ -n "$TARGET" ]                || { echo "!! no address to check"; usage; exit 2; }
[ -n "$CONTROL" ]               || { echo "!! no control address"; usage; exit 2; }

# REFUSE A STALE LISTING, for the reason written out in check_no_secvid.sh:
# it once reported PASS against a listing left over from the previous
# successful build while the build it was checking had produced nothing.
if [ -n "$SRC" ] && [ -f "$SRC" ] && [ "$SRC" -nt "$LST" ]; then
  echo "!! STALE: $SRC is newer than $LST."
  echo "   The listing does not describe the current source. Rebuild with -S."
  exit 2
fi

# hex -> the decimal low/high halves the compiler actually emits
halves() {   # halves <hex> -> "<low16> <high16>"
  local v
  v=$((16#$1))
  echo "$((v & 0xFFFF)) $(((v >> 16) & 0xFFFF))"
}

scan() {   # scan <low16> <high16> -> "reads=N writes=N"
  awk -v lo="#$1" -v hi="#$2," '
    $1=="movz" && $3==lo { pend=NR; next }
    pend && $1=="movk" && $3==hi { site=NR; pend=0; next }
    site && NR<=site+12 {
      if ($1=="bl" && $2=="wr32") { w++; site=0 }
      else if ($1=="bl" && $2=="rd32") { r++; site=0 }
    }
    NR>site+12 { site=0 }
    END { printf "reads=%d writes=%d", r+0, w+0 }
  ' "$LST"
}

read -r CLO CHI <<<"$(halves "$CONTROL")"
read -r TLO THI <<<"$(halves "$TARGET")"

echo "positive control - an address this image DOES write (0x$CONTROL):"
CTL=$(scan "$CLO" "$CHI")
echo "   $CTL"
case "$CTL" in
  *writes=0) echo "!! CHECKER BROKEN: the control write at 0x$CONTROL was not detected."
             echo "   Either that address is not written by this image, or the"
             echo "   compiler no longer materialises addresses as a movz/movk"
             echo "   pair. Refusing to report a result."; exit 2 ;;
esac
echo "   control found its write, so the checker works."
echo

echo "the address that must never be written (0x$TARGET):"
RES=$(scan "$TLO" "$THI")
echo "   $RES"
case "$RES" in
  reads=0*) echo
            echo "!! NOT PROVEN: the address is never materialised at all."
            echo "   That is not a pass - it usually means the constant is"
            echo "   folded differently, or this listing is not the image you"
            echo "   think it is, and the checker would report PASS for an"
            echo "   address the program has genuinely never heard of."
            exit 2 ;;
esac
case "$RES" in
  *writes=0) echo
             echo "PASS - 0x$TARGET is materialised only for reads."
             echo "       No store in this image reaches it."
             exit 0 ;;
esac
echo
echo "FAIL - a write to 0x$TARGET is present in the image."
echo "       Find it and delete it, do not guard it."
exit 1
