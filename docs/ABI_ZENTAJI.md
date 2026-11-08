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
storage ownership. Services are synchronous, with one caller and no callbacks
into the application. Applications must use services instead of reconfiguring
these devices. Return checks owned timer/interrupt/serial/storage state before
resuming the prompt; unsafe recovery fail-stops. Ordinary applications without
services retain their separate release/reacquire policy. This is a trusted
supervisor ABI, not isolation from malicious code or arbitrary DMA recovery.

The board provides shared lifecycle/error/capability, monotonic time, SHA-256,
settings and file/handle services. A new scope resets all eight file handles;
return and failed admission close them. Unsupported services retain their
existing ENOCAP/ENOSYS policy and every reserved slot is nonzero. No graphics,
normalized input, network, spare UART, GPIO, I2C, SPI, parallel jobs, entropy or
module provider is installed. Serial port 0 remains the monitor console; a
pixel-console or spare-UART capability is not invented for it. UTC/provenance slots read the RTC
through the declared hardware capability. Each UTC record uses a single latched
seconds/nanoseconds sample and contains seven 32-bit fields, including truncated
milliseconds. Manual time/timezone changes affect the monitor software clock;
the application UTC service continues to report the hardware RTC. Invalid samples
return UNSET with a zeroed record. Uncertainty and authoritative-sync time remain
unknown (-1). No RTC alarm, timezone or NVRAM register is written.
The built-in interactive Zentaji-only Forge is still future work.
