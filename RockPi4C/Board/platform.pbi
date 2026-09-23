; ROCK Pi 4C PCB revision 1.2 (not 4C+). Include-only port identity.
; The current direct SD entry owns the EL3 handoff, UART2, EL3 exceptions,
; and architectural timer. EL3 GIC and automatic display startup remain off.
; HDMI can be attempted once from the serial recovery prompt. Display
; capability remains withheld until physical output is verified. It does not
; claim any
; Raspberry Pi mailbox, V3D, GENET or local-interrupt-controller service.
#ANVIL_PORT_IMPLEMENTED = 1
; Identity: rock-pi-4c-v1.2 / ROCK Pi 4C v1.2 / RK3399 / aarch64.
; PureMetal A64 intentionally has no mutable string-variable runtime; the
; machine-readable identity lives in Boards/ROCK_Pi_4C.board instead.

; Capabilities describe implemented Anvil services, not hardware presence.
#CAP_STORAGE = 1
#CAP_NET = 0
#CAP_GPIO = 0
#CAP_I2C = 0
#CAP_TOUCH = 0
#CAP_MMC = 1
#CAP_USB = 0
#CAP_PWM = 0
#CAP_BOOT_EL1 = 0
#CAP_CONSOLE = 1
#CAP_GNSS = 0
#CAP_UART = 1
#CAP_SPI = 0
#CAP_VEHLINK = 0
#CAP_RTC = 0
#CAP_DISPLAY = 0
#ROCK_DIRECTSD_GIC_ENABLED = 0
#ROCK_DIRECTSD_DISPLAY_ENABLED = 0
; The HDMI path is available for an explicit first silicon attempt only.
; Automatic mode remains disabled until physical output is verified.
#ROCK_DIRECTSD_HDMI_ENABLED = 1
#ROCK_DIRECTSD_HDMI_AUTO = 0
