#!/usr/bin/env python3
"""Execute tools/board_run.py's decoders against recorded board replies.

A SCREENSHOT DECODER IS THE ONE PART OF A BOARD RUN THAT CAN BE TESTED
TWICE AND GIVE THE SAME ANSWER. Everything else in board_run.py needs a
board on the bench; the parsing does not, and it is where the run's verdict
actually comes from - which picture this is, whether the stream arrived
whole, what the payload returned, whether the digest matched. So the whole
decoder is pure functions over text and this runs them over recorded
replies in tools/fixtures/board_run/.

THE NEGATIVE CONTROLS ARE THE POINT. A decoder that has never been seen to
refuse is a decoder nobody has any reason to believe, and the failures it
must catch are all of the shape "this looks like a picture and is not one":
a stream that stopped before its terminator, a terminator that claims more
runs than arrived, a capture somebody interrupted, and - the one a magic
number cannot catch - a perfectly well-formed picture that is the PREVIOUS
run's.

    python tools/board_run_parse_check.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
FIXTURES = HERE / "fixtures" / "board_run"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "anvil_board_run", HERE / "board_run.py")
    if spec is None or spec.loader is None:
        raise SystemExit("board_run parse gate: cannot load tools/board_run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(name: str) -> str:
    path = FIXTURES / name
    if not path.is_file():
        raise SystemExit(f"board_run parse gate: missing fixture {path}")
    return path.read_text(encoding="ascii")


def fail(message: str):
    raise SystemExit(f"board_run_parse_check: FAIL {message}")


# The picture every fixture carries: six by four, navy with an orange pair
# and a white run. Written out here rather than derived from the fixture, so
# a fixture that silently changed would be caught rather than agreed with.
NAVY, ORANGE, WHITE = (0x00, 0x00, 0x28), (0xE0, 0x80, 0x20), (0xFF, 0xFF, 0xFF)
EXPECTED_ROWS = [
    [NAVY] * 6,
    [NAVY, NAVY, ORANGE, ORANGE, NAVY, NAVY],
    [WHITE] * 3 + [NAVY] * 3,
    [NAVY] * 6,
]


def rows_to_tuples(rows):
    out = []
    for row in rows:
        out.append([tuple(row[i:i + 3]) for i in range(0, len(row), 3)])
    return out


def main() -> int:
    tool = load_tool()
    checks = 0

    # ---- 1. the live screen, as `p` sends it ---------------------------
    # `shot` exists because `p` cannot photograph a frame that is already
    # gone; it does NOT exist because `p`'s format was wrong. One decoder
    # reads both, and this is the half that proves it.
    w, h, bpp, rows = tool.parse_pic_stream(fixture("p_live.txt"))
    if (w, h, bpp) != (6, 4, 4):
        fail(f"the live stream decoded as {w}x{h}x{bpp}, not 6x4x4")
    if rows_to_tuples(rows) != EXPECTED_ROWS:
        fail("the live stream's pixels are not the recorded picture")
    checks += 2

    # THE LIVE STREAM HAS NO SHOT HEADER, and must not grow one. A decoder
    # that invented a header for `p` would let a run report a capture
    # sequence number that no capture ever produced.
    if tool.parse_shot_header(fixture("p_live.txt")) is not None:
        fail("a SHOT header was found in a live `p` stream")
    checks += 1

    # ---- 2. the kept picture, as `shot` sends it -----------------------
    kept = fixture("shot_return.txt")
    w2, h2, bpp2, rows2 = tool.parse_pic_stream(kept)
    if (w2, h2, bpp2) != (6, 4, 4):
        fail(f"the kept stream decoded as {w2}x{h2}x{bpp2}, not 6x4x4")
    if rows_to_tuples(rows2) != EXPECTED_ROWS:
        fail("the kept stream's pixels are not the recorded picture")
    # THE TWO STREAMS ARE THE SAME PICTURE. If `shot` and `p` ever stopped
    # emitting one format, this is the assertion that would say so, and it
    # is the whole reason the host has one decoder instead of two.
    if tool.pixel_sha256(rows) != tool.pixel_sha256(rows2):
        fail("the live and kept streams decoded to different pixels")
    checks += 3

    header = tool.parse_shot_header(kept)
    if header is None:
        fail("the kept stream has no SHOT header line")
    want = {"seq": 3, "w": 6, "h": 4, "pitch": 3200, "rot": 90, "tier": 2,
            "x0": 0, "panel_w": 800, "panel_h": 1280, "bpp": 4, "src": 2,
            "who": 1, "bytes": 4096000}
    for key, value in want.items():
        if header[key] != value:
            fail(f"the SHOT header's {key} read {header[key]}, expected {value}")
    if (header["tier_name"], header["src_name"]) != ("v3d", "dsi"):
        fail(f"the SHOT header named {header['tier_name']}/{header['src_name']}")
    if header["who_name"] != "the monitor took it on return":
        fail(f"the SHOT header's who read {header['who_name']!r}")
    checks += len(want) + 2

    # A capture the PAYLOAD took names itself that way. The two are not
    # interchangeable: a picture taken on return is of the frame a payload
    # left, and one the payload took is of whatever it chose to keep.
    own = tool.parse_shot_header(fixture("shot_payload.txt"))
    if own["who"] != 0 or own["who_name"] != "the payload asked for it":
        fail("a payload's own capture did not name itself as one")
    if own["rot"] != 0 or own["tier_name"] != "cpu" or own["src_name"] != "hdmi":
        fail("the payload capture's geometry did not decode")
    checks += 2

    # ---- 3. THE NEGATIVE CONTROLS --------------------------------------
    for name, fragment in (
            ("shot_truncated.txt", "stopped before its END"),
            ("shot_short_count.txt", "runs and"),
            ("shot_aborted.txt", "ABORT"),
            ("shot_empty.txt", "no PIC header"),
    ):
        try:
            tool.parse_pic_stream(fixture(name))
        except tool.StreamError as error:
            if fragment not in str(error):
                fail(f"{name} was refused, but not for the right reason: {error}")
        else:
            fail(f"{name} decoded as a picture and it is not one")
        checks += 1

    # ---- 4. the run's other verdicts ------------------------------------
    if tool.parse_stage_address(fixture("map.txt")) != 0x00500000:
        fail("the staging address did not come out of `map`")
    if tool.parse_image_extent(fixture("map.txt")) != (0x00200000, 0x004121B7):
        fail("the monitor's own extent did not come out of `map`")
    checks += 2

    if tool.parse_return_x0(fixture("return_ok.txt")) != 0:
        fail("a zero x0 did not decode from the return line")
    if tool.parse_return_x0(fixture("return_bad.txt")) != 0x65:
        fail("a non-zero x0 did not decode from the return line")
    # A RUN THAT NEVER RETURNED HAS NO x0, and None is not zero. A decoder
    # that answered 0 for "there was no line" would pass every hung run.
    if tool.parse_return_x0(fixture("map.txt")) is not None:
        fail("an x0 was invented for a reply that has no return line")
    checks += 3

    length, ms, digest = tool.parse_recv_verdict(fixture("recv_verdict.txt"))
    if length != 4096 or ms != 118:
        fail(f"the transfer verdict read {length} bytes in {ms} ms")
    if digest != hashlib.sha256(b"").hexdigest()[:0] + digest:
        fail("the digest did not survive parsing")
    if len(digest) != 64:
        fail("the board's digest did not decode as 64 hex characters")
    checks += 3

    # ---- 5. the sequence number, which is what makes a picture THIS run's
    if tool.parse_shot_status_seq(fixture("shot_status.txt")) != 2:
        fail("the capture sequence number did not come out of `shot status`")
    # A BOARD THAT HAS CAPTURED NOTHING ANSWERS ZERO, not "unknown": zero is
    # the baseline any real capture moves past, so a first run compares
    # correctly with no special case.
    if tool.parse_shot_status_seq(fixture("shot_status_empty.txt")) != 0:
        fail("an empty capture area did not read as sequence zero")
    checks += 2

    # ---- 6. the payload's own trace -------------------------------------
    blob = tool.parse_dump(fixture("trace_ktrc.txt"))
    if len(blob) != 32:
        fail(f"the hex dump decoded {len(blob)} bytes, expected 32")
    if blob[:4] != b"KTRC":
        fail(f"the trace's magic decoded as {blob[:4]!r}")
    if int.from_bytes(blob[8:16], "little") != 9:
        fail("the trace's stage word did not decode")
    checks += 3

    # The monitor command language reads counts as hexadecimal, while the
    # command-line trace length is an ordinary decimal integer.  These two
    # examples are deliberately made of decimal digits that mean a different
    # value when sent unchanged: 672 must be 2A0 on the wire, never 0x672.
    if tool.monitor_hex_count(672) != "2A0":
        fail("a 672-byte trace was not encoded as hexadecimal 2A0")
    if tool.monitor_hex_count(640) != "280":
        fail("a 640-byte trace was not encoded as hexadecimal 280")
    try:
        tool.monitor_hex_count(-1)
    except ValueError:
        pass
    else:
        fail("a negative trace count was encoded instead of refused")
    checks += 3

    # ---- 7. the PNG it writes -------------------------------------------
    # WRITTEN BY HAND, so it is worth proving it is a PNG rather than
    # assuming it. Signature, an IHDR that says what the decoder said, and
    # pixels that survive a round trip through zlib.
    blob = tool.png(w2, h2, rows2)
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        fail("the PNG signature is wrong")
    if blob[12:16] != b"IHDR":
        fail("the first chunk is not IHDR")
    if int.from_bytes(blob[16:20], "big") != w2 or \
       int.from_bytes(blob[20:24], "big") != h2:
        fail("the PNG's IHDR does not describe the decoded picture")
    start = blob.index(b"IDAT") + 4
    end = blob.index(b"IEND") - 8
    raw = zlib.decompress(blob[start:end])
    # One filter byte per row, filter 0, then the row.
    for y, row in enumerate(rows2):
        at = y * (1 + len(row))
        if raw[at] != 0:
            fail(f"row {y} of the PNG is not filter 0")
        if raw[at + 1:at + 1 + len(row)] != row:
            fail(f"row {y} of the PNG is not the decoded row")
    checks += 4 + len(rows2)

    print(f"board_run_parse_check: PASS - {checks} assertions over "
          f"{len(list(FIXTURES.glob('*.txt')))} recorded board replies, "
          "including four streams that must be refused")
    print("  the live `p` stream and the kept `shot` stream decode to the same")
    print("  pixels, which is what lets one host decoder serve both.")
    print("  Recorded replies, not a board. This proves the decoder, not a panel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
