# The banner's status row

The identity row of the banner - the row the build label sits on - carries a
caption that is composed once a second and redrawn only when its text changed.
It holds, in this order:

1. the wall clock's own caption (see [WALL_CLOCK.md](WALL_CLOCK.md));
2. the part's temperature, in whole degrees Fahrenheit, when the board has a
   thermometer;
3. the fan's duty, as a whole percent, when a pulse-width modulator is actually
   being driven.

Each part is separated from the last by four spaces, so the row reads as three
readings rather than one run-on string. Nothing is abbreviated and nothing is
padded to a fixed width: a caption that is not there takes no room.

    2026-09-11 06:53:40 CDT    112 F    fan 63%

## The temperature

The reading comes from the hardware layer's temperature seam in millidegrees
Celsius and is converted once, by `HwTempWholeF()` in `Anvil/Hal/hal.pbi`, which
is the only conversion in the tree. `#HW_TEMP_NONE` means the board has no
thermometer answering; it is not a reading and it is never shown - the row
simply has no temperature on it. A board whose thermal implementation arrives
later, as a loaded driver module, starts showing a temperature without anything
else changing.

## The fan

The duty is read back from the modulator rather than remembered from the last
value written, so the row states what the pin is doing and not what a policy
believes it asked for. "Being used" is the modulator's own kind not being
`#HW_PWM_KIND_NONE`: a board where nobody has claimed a pin shows nothing about
a fan, and a pin that was claimed and released shows nothing again even if the
hardware still reads back its last duty. A claimed pin sitting at rest shows
`fan 0%`, because a hidden fan and a stopped fan look the same on the glass and
are not the same thing.

Most boards have no modulated fan at all. `#ANVIL_BANNER_FAN` in the board file
is the compile-time switch: at `0` the fan half is not compiled, and the text it
would have written is not in the image. It is `1` on the Pi 4.

## Where the temperature is read, and why not where it is shown

**The caption reads a published sample. It never calls the temperature seam.**

A seam call is a call through a pointer held in the service table, so the
compiler has to treat it as a call to every procedure whose address that table
can hold - which includes the USB enumeration the boot walk reaches. The caption
is composed from the screen service tick, and the boot walk reaches the screen
service tick, so a seam call in the caption closes a call loop that cannot
happen at run time and the build is refused. The refusal is correct twice over:
parameters live in globals rather than in per-call frames, so a loop the
compiler cannot rule out would return a plausible wrong number rather than
crash - and taking a reading means touching hardware, which a repaint is not the
place for.

So the reading and the reader are separated:

- `Anvil/Hal/hal.pbi` declares the published sample and `HwTempSampled()`. The
  unit and the sentinel are the hardware layer's vocabulary, so the sample is
  too, and every board defines it whether or not it has a fan.
- `Anvil/Core/fan_cmd.pbi` owns the sampling. `HwTempSampleNow()` is the one
  place in the monitor that reads the seam periodically; it publishes what the
  seam said and returns it. `HwTempSampleTick()` calls it once a second.
- `Anvil/Core/parse.pbi`'s prompt spin calls `HwTempSampleTick()` beside
  `FanTick()`. That loop is reached from nothing in the service table, which is
  why the fan policy has always been able to read the seam from there.
- The policy's own read goes through `HwTempSampleNow()` as well, so an armed
  board reads the seam once and the row agrees with the policy acting on it.

`BannerCaption()` composes; `BannerCaptionLast()` returns what the last tick
composed and is what a repaint draws. A repaint happens on every printed line
and on every geometry change, and the caption changes at most once a second.

## Fitting

The row is clipped from the right at the width the banner gives it, so on a
narrow surface the fan is lost first, then the temperature, and the clock is
what survives. Nothing is dropped deliberately to make room.

## Proof

`tools/banner_status_emitted_check.py` compiles the real caption over the real
hardware-layer conversion, runs it on the A64 model and grades fourteen
compositions - present, absent, rounded either side of a whole degree, either
side of freezing, the bound at a full row, and the repaint accessor. It supplies
the temperature seam as a counting stub and requires the count to still be zero,
which is the "never calls the seam" statement proven by execution rather than by
reading the source. It then rebuilds the same fixture with `#ANVIL_BANNER_FAN`
at `0` and requires the fan text to be absent from the image, not merely
skipped.
