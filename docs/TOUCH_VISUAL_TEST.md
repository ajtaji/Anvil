# Visual multitouch test

Run `touch test` after the monitor reports that touch is ready. The test uses
the already-running Goodix controller without an additional probe, reset or
pin configuration beyond normal polling. The I2C protocol is unchanged.

The screen states the controller's reported contact capacity (ten on the
current GT9271), current live count, peak simultaneous count, and DOWN/MOVE/UP
counter deltas. Each tracking ID owns a coloured numbered marker and leaves a
trail while it moves; a released ID gets a white endpoint. This makes ten
simultaneous fingers visible independently instead of reducing them to the
normal console's single primary-contact cursor.

Each diagnostic frame goes through `ScrPresentAll`, including the initial
screen. Rotated DSI draws into a logical buffer distinct from physical scanout;
drawing without presenting can count all ten contacts while displaying none.

Press any serial, network-console, or already-attached USB-keyboard key to exit.
Both a 1,500-poll bound and an
independent 30-second counter deadline apply, so slow drawing cannot turn it
into a minutes-long command. The prior console region, colours, cursor location,
cursor visibility and renderer are restored and repainted. The diagnostic is
visual hardware evidence, not a synthetic input test, and it performs no
additional probe, reset, or pin configuration beyond normal touch polling.
On rotated DSI the restored banner is explicitly presented to the scanned
surface before V3D repaint resumes, so V3D preserves the Anvil banner rather
than the diagnostic pixels that previously occupied its strip.
