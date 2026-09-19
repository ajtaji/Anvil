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

**Both renderers use it.** The framebuffer tier took it first; the V3D tier kept
the engine's cell face for a day, on the argument that the engine has one face
and the console text around the keys is drawn in it. That argument was wrong
about which screen matters: the bench panel runs on the V3D tier, so the tier
that kept the cell face was the only tier anybody was looking at. It is fixed
below, and no engine change was needed to fix it.

## A label is centred in a box, and the renderer chooses the face

The view (`Anvil/Graphics/touch_keyboard_view.pbi`) no longer computes a text
extent. A text item in its draw list is a **label and a box**: the key's face
inside its padding. The view also carries the largest whole magnification of the
cell font that would fit that box, for a renderer that has no other face.

The composer (`TouchKeyboardComposeCpu` in `RaspberryPi4/Board/banner_clock.pi4`)
decides, per label:

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

## One composer, two tiers, and how the band reaches a GPU-composed frame

`TouchKeyboardComposeCpu` is the composer on **both** tiers. `gCursorGpuOwned`
says which one is underneath, and it changes three things and nothing else.

**Why the band cannot simply be drawn into the GPU's target.** A picture drawn
by the CPU is drawn in LOGICAL coordinates - that is the only coordinate system
the display library has - and on a turned panel the V3D render target is in
PHYSICAL layout: a logical row is a physical column. There is exactly one
transpose in this monitor, `ScrPresent`'s. Giving the engine a coverage-map face
instead is not cheap either: the V3D 4.2 TMU cannot sample the linear atlas the
baked faces live in, which is the same reason the banner - photo, smooth title
and all - is CPU-blitted rather than textured.

**So the band takes the banner's route, exactly.**

1. The CPU composes the whole band into the console's own logical surface,
   through the ordinary display primitives.
2. `a64_barrier()` drains those writes - the same statement `V3dConBlitBanner`
   makes after drawing the banner, and for the same reason: the framebuffer is
   mapped Normal Non-Cacheable and a store buffer may gather and reorder.
3. `ScrPresent(bandTop, bandBottom)` puts it on the panel through the one
   transpose, with the same damage rectangle the framebuffer tier uses.
4. Every later GPU frame **carries those pixels along**:
   `ScrGpuKeepLogicalBand` (`RaspberryPi4/Board/screen_source.pi4`) copies the
   band's physical rectangle back out of the presented front and into the
   render target, before the present - which is what `ScrGpuKeepBanner` already
   does for the banner. `ConPaintV3d` calls it through
   `V3dConKeepKeyboardBand`.

Nothing writes a byte the GPU is rendering into: the composer's surface is the
console's logical one, and the carry runs after `NeonFrameEnd` has waited.

The three differences the tier makes to the composer:

- **The band is painted whole, every time.** What the seam moves is a range of
  logical rows, and underneath them lies the GPU's physical frame; a pixel in
  those rows that this pass did not paint would be last frame's bytes on the
  glass. It is also cheaper than what the tier did before, which was to redraw
  all ~180 keys inside every console frame.
- **Nothing outside the band is this pass's.** The keyboard button beside the
  prompt lives inside the console rectangle the GPU repaints wholesale, so
  `TouchKeyboardComposeNeon` still draws it with the engine's primitives. Its
  `KB` fallback label is a 16 x 16 box, which could not hold the 30 px face on
  any tier; the fallback rule above puts the cell font in it.
- **The pointer's save-under is not touched, because there is not one.** The
  pointer is inside the GPU's frame on this tier. The mask is written again over
  the finished band through the presented-overlay seam - the same two calls
  `BannerClockTick` makes when the clock advances underneath a pointer.

## Opening it without a finger

`screen keyboard show`, `screen keyboard hide` and `screen keyboard state` drive
the band from any console channel - the serial line, the network console, or the
screen itself. It is the same path a tap takes and not a second one:
`TouchKeyboardRequest` writes the model's intent, exactly as `TouchKeyboardRouteOne`
does for a contact on the button or the prompt line, and then runs
`TouchKeyboardServiceTick`. The focus generation, the viewport move, the
dispatcher's rectangle, the refusal counter and the repaint therefore all happen
the way they do for a finger. It lives inside the fenced integration section, so
the touch keyboard integration gate compiles and executes it.

## Proof

`tools/keyboard_face_emitted_check.py` lifts the composer verbatim from between
its fences in the adapter, compiles it against the real key model and the real
view, and runs it on the A64 model at six surfaces **on the framebuffer tier**.
For every label it reads the box the view produced, the face that drew it and
what was drawn, and requires the label to be inside its box, centred both ways,
drawn at the baked face's own advance widths, and present at all. It requires
every label on the bench panel to take the smooth face, and requires the narrow
surface to fall back and keep its labels. Nine mutations of the composer are
rejected.

`tools/keyboard_gpu_face_emitted_check.py` is the same six surfaces **on the V3D
tier**, and it also lifts `ScrGpuKeepLogicalBand` verbatim and runs it over the
real rotation arithmetic in `screen_geom.pi4`. Beyond the faces it requires, by
execution: that the composer runs at all with the GPU owning the frame (it used
to return at its second line); that the first rectangle covers the whole band
and nothing drawn leaves it; that the rows presented are exactly the band's;
that the drain happens after the last pixel written and before the copy; that no
save-under call is made and the pointer is written back after the present; that
with the band down the pass draws nothing; and that the carried rectangle is the
band's own physical rectangle at 0, 90, 180 and 270, checked against the
checker's own arithmetic over the panel's geometry. Sixteen mutations are
rejected.

`tools/touch_keyboard_integration_emitted_check.py` covers the console command:
after `screen keyboard show` the dispatcher holds the band, the console has
reserved the rows, and a key tapped on the glass still reaches the editor.
