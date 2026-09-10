# Early Pi 4 V3D boot console

The Pi 4 boot sequence now activates the preferred V3D console after the
configured screen and touch probe are complete, but before the network starts.
The retained touch trace therefore keeps its previous cache-off physical timing.
The initial log queue remains open until after V3D activation, so network and
later boot progress are first painted through the selected fast renderer.

`ScreenUp()` must still establish a real surface before V3D can bind it. Its
initial DSI banner is consequently drawn once by the CPU/DMA framebuffer tier;
this change does not claim that the earliest pixels are GPU-rendered. DMA may
already accelerate scrolling, large fills and DSI presentation, while V3D owns
text-grid rendering after activation. The first V3D activation also retains its
existing optional cache enablement.

If V3D setup fails, `V3dConAutoStart()` leaves the DMA/CPU renderer active and
boot continues. No display, DMA, V3D or cache driver algorithm changed.

`tools/boot_v3d_order_check.py` is an intentionally structural gate. It proves
one guarded activation and the order: settings, surface, touch, trace disable,
V3D activation, early-log finish, progress hooks, first service paint, network,
then both autoboot waits. Six source mutations must be rejected. Hardware
speed and appearance require the separately owned normal boot observation.
