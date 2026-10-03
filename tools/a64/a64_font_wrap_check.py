"""Check the Pi4 proportional console's 16.16 wrap arithmetic with a real font.

This is a host-side numeric regression gate. It reads TrueType cmap/hmtx data
without third-party packages and uses the same public metric inputs and wrap
threshold as ScreenProportionalAdvance and ConGridPutPrintable. It also injects
the previous pair-lookup failure value to show why it must never enter layout.
It does not run the Pi4 binary or GPOS pair positioning.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import struct


BOOT_LINE = "Everything this monitor prints from now on goes to both the screen and"
FIXED_ONE = 65536
OLD_PAIR_FAILURE = 0x7FFFFFFF


class TrueTypeMetrics:
    def __init__(self, path: Path):
        self.data = path.read_bytes()
        if self.data[:4] not in (b"\x00\x01\x00\x00", b"true"):
            raise ValueError(f"{path}: expected a TrueType font")
        table_count = self.u16(4)
        self.tables: dict[bytes, tuple[int, int]] = {}
        for index in range(table_count):
            at = 12 + index * 16
            tag, _, offset, length = struct.unpack_from(">4sIII", self.data, at)
            if offset + length > len(self.data):
                raise ValueError(f"{path}: invalid {tag!r} table bounds")
            self.tables[tag] = (offset, length)
        head = self.table(b"head")
        hhea = self.table(b"hhea")
        maxp = self.table(b"maxp")
        self.units_per_em = self.u16(head + 18)
        self.horizontal_metrics = self.u16(hhea + 34)
        self.glyph_count = self.u16(maxp + 4)
        if not (self.units_per_em and 0 < self.horizontal_metrics <= self.glyph_count):
            raise ValueError(f"{path}: invalid font metrics")
        self.hmtx = self.table(b"hmtx")
        self.cmap = self._cmap4()

    def u16(self, at: int) -> int:
        return struct.unpack_from(">H", self.data, at)[0]

    def table(self, tag: bytes) -> int:
        if tag not in self.tables:
            raise ValueError(f"missing {tag.decode('ascii')} table")
        return self.tables[tag][0]

    def _cmap4(self) -> int:
        cmap = self.table(b"cmap")
        count = self.u16(cmap + 2)
        for index in range(count):
            platform, encoding, offset = struct.unpack_from(">HHI", self.data, cmap + 4 + index * 8)
            subtable = cmap + offset
            if (platform, encoding) in ((3, 1), (0, 3)) and self.u16(subtable) == 4:
                return subtable
        raise ValueError("font lacks a Unicode BMP cmap format 4 subtable")

    def glyph(self, codepoint: int) -> int:
        cmap = self.cmap
        segments = self.u16(cmap + 6) // 2
        end_codes = cmap + 14
        start_codes = end_codes + segments * 2 + 2
        deltas = start_codes + segments * 2
        ranges = deltas + segments * 2
        for index in range(segments):
            if codepoint > self.u16(end_codes + index * 2):
                continue
            if codepoint < self.u16(start_codes + index * 2):
                return 0
            delta = self.u16(deltas + index * 2)
            range_pos = ranges + index * 2
            displacement = self.u16(range_pos)
            if displacement:
                glyph = self.u16(range_pos + displacement + 2 * (codepoint - self.u16(start_codes + index * 2)))
                return (glyph + delta) & 0xFFFF if glyph else 0
            return (codepoint + delta) & 0xFFFF
        return 0

    def advance_fixed(self, character: str, pixels: int) -> int:
        glyph = self.glyph(ord(character))
        if glyph == 0 or glyph >= self.glyph_count:
            raise ValueError(f"font has no glyph for {character!r}")
        metric = min(glyph, self.horizontal_metrics - 1)
        advance_units = self.u16(self.hmtx + metric * 4)
        return advance_units * pixels * FIXED_ONE // self.units_per_em


def wrap(advances: list[int], width: int, columns: int) -> list[int]:
    """Model console.pi4's fixed-point width and bounded-cell wrap decisions."""
    rows = [0]
    pen = 0
    for advance in advances:
        if rows[-1] and pen + advance > width * FIXED_ONE:
            rows.append(0)
            pen = 0
        rows[-1] += 1
        pen += advance
        if rows[-1] >= columns:
            rows.append(0)
            pen = 0
    return [count for count in rows if count]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "DejaVuSans-Bold.ttf")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2] / "RaspberryPi4" / "Board" / "screen_cmd.pi4")
    parser.add_argument("--layout-source", type=Path, default=Path(__file__).resolve().parents[2] / "Anvil" / "Graphics" / "truetype_layout.pbi")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--pixels", type=int, default=16)
    args = parser.parse_args()
    if args.width < 1 or args.pixels < 1:
        parser.error("width and pixels must be positive")

    source = args.source.read_text(encoding="utf-8")
    if not re.search(r'PrintN\("' + re.escape(BOOT_LINE) + r'"\)', source):
        raise AssertionError("the selected Pi4 boot line is absent from screen_cmd.pi4")
    if "ProcedureReturn $7FFFFFFF" in source:
        raise AssertionError("pair lookup failure still enters console layout as a huge glyph advance")
    if not re.search(r"ConGridInit\(#CON_MAXCOLS,\s*DisplayRows\(\)\)", source):
        raise AssertionError("TrueType console is not using the bounded storage grid")
    if not re.search(r"ConGridProportionalSet\(DisplayWidth\(\),\s*1\)", source):
        raise AssertionError("TrueType wrap threshold is not the display pixel width")
    clear_console_pair = "For pairIndex = 0 To 7 : gScreenPairValues[pairIndex] = 0 : Next"
    if clear_console_pair not in source or source.index(clear_console_pair) > source.index("pairRc = AnvilTrueTypePairPosition"):
        raise AssertionError("console metric cache does not clear stale pair values before lookup")
    layout_source = args.layout_source.read_text(encoding="utf-8")
    if not re.search(r"If pairResult=0\s*:\s*anvil_ttl_error=#ANVIL_TTL_E_PAIR", layout_source):
        raise AssertionError("renderer no longer reports a true pair lookup failure")
    clear_pair = "For pairIndex=0 To 7 : anvil_ttl_pairValues[pairIndex]=0 : Next"
    if clear_pair not in layout_source or layout_source.index(clear_pair) > layout_source.index("pairResult=AnvilTrueTypePairPosition"):
        raise AssertionError("renderer does not clear stale pair values before lookup")
    if "If pairStep<0 Or pairStep>pixelHeight*4*65536" not in layout_source:
        raise AssertionError("renderer has no bound for corrupt pair positioning")
    font = TrueTypeMetrics(args.font)
    advances = [font.advance_fixed(character, args.pixels) for character in BOOT_LINE]
    rows = wrap(advances, args.width, 512)
    measured = sum(advances) / FIXED_ONE
    print(f"font={args.font} unitsPerEm={font.units_per_em} pixels={args.pixels}")
    print(f"screenWidth={args.width}px bootLine={len(BOOT_LINE)} chars measured={measured:.2f}px rows={rows}")
    if len(rows) != 1:
        raise AssertionError(f"real font advances wrapped the boot line into {len(rows)} rows")
    if rows[0] <= 2:
        raise AssertionError("two-character wrap regression")
    # The former pair failure was interpreted as 32768px. One failed pair
    # turns a perfectly ordinary 70-character line into a premature wrap.
    # The current code retains the measured hmtx advance for that pair.
    faulty = advances.copy()
    faulty[2] = OLD_PAIR_FAILURE
    if len(wrap(faulty, args.width, 512)) < 2:
        raise AssertionError("the old failure injection did not reproduce a wrap")
    recovered = faulty.copy()
    recovered[2] = advances[2]
    if wrap(recovered, args.width, 512) != rows:
        raise AssertionError("measured-advance recovery changed the line geometry")
    print("PASS: the real-font numeric wrap baseline fits on one row")
    print("PASS: an injected old pair failure wraps; retaining hmtx advance restores the row")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
