# Touch keyboard key labels

## Smooth labels

The key labels are set in an anti-aliased face - the same kind of glyph the
banner's title is drawn with - rather than in the console's 8x16 cell font
magnified to fit. A one-bit cell font can only be enlarged by whole pixels, and
at three or four times a letter is a staircase; that is what the labels used to
be.

The face is font 3 in `RaspberryPi4/Monitor/anvil_fonts.pi4`: DejaVu Sans Bold
at 30 pixels, baked to four-bit coverage maps by the same private tool that
bakes the three 48-pixel banner faces. **It is a smaller face and not a scaled
one.** Enlarging a finished coverage map softens its edges, and a soft edge is
exactly what the change exists to remove. Thirty pixels clears its descenders
inside a key at the smallest target size the view will lay out.

## A label is centred in a box, and the renderer chooses the face

The view (`Anvil/Graphics/touch_keyboard_view.pbi`) no longer computes a text
extent. A text item in its draw list is a **label and a box**: the key's face
inside its padding. The view also carries the largest whole magnification of the
cell font that would fit that box, for a renderer that has no other face.

The framebuffer composer (`TouchKeyboardComposeCpu` in
`RaspberryPi4/Board/banner_clock.pi4`) decides, per label:

- the **smooth face**, when the box is at least the face's line height tall and
  the label's real width in that face fits the box - centred both ways, with the
  glyphs blended onto the key's own face colour;
- the **cell font at whole magnification**, otherwise - also centred both ways.

A label is never dropped and never clipped: a box the smooth face cannot fit
falls back rather than losing its text. On the bench panel in landscape every
label on both pages takes the smooth face. In the panel's portrait scan the keys
are narrower and the few longest labels (`Home`, `Backspace`) fall back; on the
smallest surface the arrangement still fits, seven of fifty-two do.

The pass restores whatever magnification the display library was on when it
started, because the console is drawn with that.

## The GPU path draws the cell font, deliberately

When the V3D console is the active renderer, the keyboard is composed inside the
GPU frame (`TouchKeyboardComposeNeon` in `RaspberryPi4/Board/v3d_console.pi4`)
with the engine's own text primitive. That engine has **one** face - a one-bit
cell at four integer scales - and it is the face the console text all around the
keys is drawn with on that path. Smooth key labels in a frame of blocky console
text would be the one thing in the picture that did not match, and giving the
engine a coverage-map face is a change to the engine rather than to the
keyboard. The items are still labels in boxes there, and the centring is the
same arithmetic.

## Proof

`tools/keyboard_face_emitted_check.py` lifts the composer verbatim from between
its fences in the adapter, compiles it against the real key model and the real
view, and runs it on the A64 model at six surfaces. For every label it reads the
box the view produced, the face that drew it and what was drawn, and requires
the label to be inside its box, centred both ways, drawn at the baked face's own
advance widths, and present at all. It requires every label on the bench panel
to take the smooth face, and requires the narrow surface to fall back and keep
its labels. Nine mutations of the composer are rejected.
