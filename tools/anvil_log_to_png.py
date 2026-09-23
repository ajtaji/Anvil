#!/usr/bin/env python3
"""
anvil_log_to_png.py - render an Anvil session transcript to a PNG.

WHY THIS EXISTS. On the Raspberry Pi 4 a screenshot is a real screenshot:
`screenshot` RLE-encodes the framebuffer over the wire and tools/pmfshot.py
turns it into a PNG. The Arduino UNO Q cannot do that, and the reason is
measured rather than assumed - ArduinoQ/Examples/Diagnostics/NotBuilding/anvilqconprobe.unoq
asked the firmware for EFI_GRAPHICS_OUTPUT_PROTOCOL and got EFI_NOT_FOUND.
There is no framebuffer under UEFI on this board, so there is no image to
capture.

What the Q does have is a real console session, written to \\EFI\\anvil\\anvil.log
on the EFI System Partition and read back over SSH. This renders that
transcript into something a person can look at.

BE CLEAR ABOUT WHAT THE PICTURE IS. It is a rendering of text the board
produced, not a photograph of a screen the board drove. The header it
stamps on every image says so, so that an image separated from its
description cannot be mistaken for a framebuffer capture.

Usage:
    python tools/anvil_log_to_png.py <anvil.log> <out.png> [--title "..."]
    python tools/anvil_log_to_png.py <anvil.log> <out.png> --head 60
"""
import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("!! this needs Pillow:  python -m pip install Pillow")

# A terminal palette, deliberately not pure black on pure white: this is a
# picture of a console session and it should read as one.
BG      = (18, 20, 24)
FG      = (208, 214, 222)
PROMPT  = (126, 200, 132)      # the "pmf> " lines - what was typed
BANNER  = (150, 180, 230)      # Anvil's own identification
REFUSE  = (232, 168, 106)      # RequireCap's honest refusals
HEADER  = (120, 128, 140)
RULE    = (52, 58, 68)


def pick_font(size: int):
    """A monospace face, or Pillow's bitmap default if none is installed."""
    for name in ("consola.ttf", "DejaVuSansMono.ttf", "cour.ttf",
                 "LiberationMono-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def colour_for(line: str):
    s = line.lstrip()
    if line.startswith("pmf> "):
        return PROMPT
    if s.startswith("!!"):
        return REFUSE
    if "PureMetal Forge - Anvil" in line:
        return BANNER
    return FG


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("out")
    ap.add_argument("--title", default="Anvil on the Arduino UNO Q")
    ap.add_argument("--head", type=int, default=0,
                    help="render only the first N lines")
    ap.add_argument("--size", type=int, default=15)
    args = ap.parse_args()

    raw = Path(args.log).read_bytes().decode("latin-1")
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    total = len(lines)
    if args.head and total > args.head:
        lines = lines[:args.head]
        lines.append("")
        lines.append(f"... {total - args.head} more lines in the transcript ...")

    font = pick_font(args.size)
    hfont = pick_font(args.size - 2)

    # Measure with the real font rather than guessing a cell size.
    probe = Image.new("RGB", (8, 8))
    d0 = ImageDraw.Draw(probe)
    bb = d0.textbbox((0, 0), "M" * 100, font=font)
    cw = (bb[2] - bb[0]) / 100.0
    lh = int((bb[3] - bb[1]) * 1.55) or args.size + 4

    cols = max((len(x) for x in lines), default=80)
    cols = max(cols, 78)
    pad = 22

    # The three header lines are longer than most transcript lines and are
    # drawn in a different font, so the canvas has to be sized against them
    # too. Sizing on the transcript alone clipped the header off the right
    # edge of the first capture this tool produced.
    sub = (f"{Path(args.log).name}   -  {total} lines, {len(raw)} bytes, "
           f"read off the board's EFI System Partition over SSH")
    note = ("This is a rendering of the session TEXT. The UNO Q publishes no "
            "UEFI GOP framebuffer, so there is no screen image to capture.")
    head_w = max(d0.textlength(t, font=hfont) for t in (args.title, sub, note))

    head_h = lh * 3 + 10
    w = int(max(cols * cw, head_w)) + pad * 2
    h = head_h + lh * len(lines) + pad * 2

    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)

    d.text((pad, pad), args.title, font=hfont, fill=BANNER)
    d.text((pad, pad + lh), sub, font=hfont, fill=HEADER)
    d.text((pad, pad + lh * 2), note, font=hfont, fill=HEADER)
    d.line([(pad, pad + head_h - 6), (w - pad, pad + head_h - 6)], fill=RULE, width=1)

    y = pad + head_h
    for ln in lines:
        if ln:
            d.text((pad, y), ln, font=font, fill=colour_for(ln))
        y += lh

    img.save(args.out)
    print(f"wrote {args.out}  ({w}x{h}, {len(lines)} lines rendered of {total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
