; Raspberry Pi 3 Model B PCB revision 1.2. Include-only port stub.
; NOT an entry point. No startup, MMIO, reset or memory layout is supplied.
; Include exactly one platform.pbi in a future board composition root.
#ANVIL_PORT_IMPLEMENTED = 0
#ANVIL_PORT_ID = "raspberry-pi-3-b-v1.2"
#ANVIL_PORT_NAME = "Raspberry Pi 3 Model B v1.2"
#ANVIL_PORT_SOC = "BCM2837"
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
