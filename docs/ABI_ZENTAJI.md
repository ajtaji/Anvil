# Zentaji payload services

The shared Anvil table retains ABI 1.15: the 16-byte little-endian ANVS header
and 208 eight-byte procedure slots. Zentaji uses PMFBOOT v2 ISA 2 / target 1.
Set wants-services and validate the header before calling any slot. These are
Zentaji procedure addresses; machine code is specific to its ISA.

`CallFunctionFast(address, arguments...)` retains inferred conversions for known
typed callbacks. For unresolved foreign targets it uses the native integer ABI: zero to
15 scalar integer/pointer arguments in r1..r15 and a full 64-bit result in r1.
The target expression is evaluated once before the arguments. Floating-point
signatures require a known typed callback; the unresolved native call refuses them. Named callbacks retain
the compiler's signature/conversion checks. No call-graph or naked-leaf check is
bypassed. Pass zero-terminated UTF-8 addresses rather than managed strings.

The CPU boundary enters on core 0 in supervisor mode with STATUS=0 and protection
disabled, the owned monitor vectors installed, interrupts masked, FP state reset,
and the validated, 16-byte-aligned application stack. The argument is the table
address in r1. Return from the application's entry to resume the monitor. The
boundary restores monitor GPR/vector/mask/FP/stack/link/vector-base state without
trusting the returned application stack. SvcReturn itself still returns ENOSYS
when returns-to-monitor was declared, or EFLAG otherwise.

For service-backed applications Anvil retains serial, idle timer and selected
storage ownership, plus native text/display ownership when admitted at boot.
Services are synchronous, with one caller and no callbacks
into the application. Applications must use services instead of reconfiguring
these devices. Return checks owned timer/interrupt/serial/storage state before
resuming the prompt; native text/display changes fail-stop with 0x5B05.
The keyboard/mouse owner is retained for services; return closes any open input
session and fences held input. Foreign mouse capture or device interrupt enables
fail-stop with 0x5B06 before that hardware is reused.
Ordinary applications without services release the text layer and display output,
then must return both disabled with interrupts disabled. Anvil checks that state
before reacquiring and clearing its protected text buffer. The reservation stays
outside all payload/staging windows throughout either kind of application.
This is a trusted
supervisor ABI, not isolation from malicious code or arbitrary DMA recovery.

The board provides shared lifecycle/error/capability, monotonic time, SHA-256,
settings and file/handle services. A new scope resets all eight file handles;
return and failed admission close them. Unsupported services retain their
existing ENOCAP/ENOSYS policy and every reserved slot is nonzero. No graphics,
network, spare UART, GPIO, I2C, SPI, parallel jobs, entropy or
module provider is installed. Serial port 0 remains the monitor console; a
hardware text mirror renders monitor output on admitted display profiles. Text
does not advertise the arbitrary-pixel CAP_CONSOLE API or add service slots.
Slot39 supplies the existing NativeInputApi1.0 protocol: keyboard and mouse,
validated payload buffers, bounded nonblocking polling, focus generations,
physical HID edges, ASCII text/navigation, three mouse buttons and wheel steps.
Host-marked repeats produce typed events without synthetic repeats or duplicate
physical down edges. Held keys/buttons are fenced at open/flush/return; queue
overflow cancels rather than trusting lost releases. A geometry change emits a
cancellation and requires close/reopen. Coordinates clamp to the display; wheel
steps clamp to the existing signed16-bit wire range. Non-ASCII text and mouse
side buttons do not silently change this existing ABI. Gamepad/rumble lanes are
unclaimed. Ordinary payloads receive the input device quiescent and must restore
uncaptured mode with device interrupts disabled. The application text interface
and self-hosted editor/compiler remain future work. UTC/provenance slots read the RTC
through the declared hardware capability. Each UTC record uses a single latched
seconds/nanoseconds sample and contains seven 32-bit fields, including truncated
milliseconds. Manual time/timezone changes affect the monitor software clock;
the application UTC service continues to report the hardware RTC. Invalid samples
return UNSET with a zeroed record. Uncertainty and authoritative-sync time remain
unknown (-1). No RTC alarm, timezone or NVRAM register is written.
The built-in interactive Zentaji-only Forge is still future work.
