; ROCK Pi 4C PCB revision 1.2 (not 4C+). Include-only port stub.
; NOT an entry point. No startup, MMIO, reset or memory layout is supplied.
; Include exactly one platform.pbi in a future board composition root.
#ANVIL_PORT_IMPLEMENTED = 0
#ANVIL_PORT_ID = "rock-pi-4c-v1.2"
#ANVIL_PORT_NAME = "ROCK Pi 4C v1.2"
#ANVIL_PORT_SOC = "RK3399"
#ANVIL_PORT_ARCH = "aarch64"

; Capabilities describe implemented Anvil services, not hardware presence.
#CAP_STORAGE = 0
#CAP_NET = 0
#CAP_GPIO = 0
#CAP_I2C = 0
#CAP_TOUCH = 0
#CAP_MMC = 0
#CAP_USB = 0
#CAP_PWM = 0
#CAP_BOOT_EL1 = 0
#CAP_CONSOLE = 0
#CAP_GNSS = 0
#CAP_UART = 0
#CAP_SPI = 0
#CAP_VEHLINK = 0
#CAP_RTC = 0
