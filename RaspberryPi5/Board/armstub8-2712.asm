; ======================================================================
;  armstub8-2712.asm - Raspberry Pi 5 boot stub that enters Anvil at EL3.
;
;  Port of RaspberryPi4/Board/armstub8.asm (itself a translation of
;  Raspberry Pi's tools/armstubs/armstub8.S, Copyright (c) 2016 Stephen
;  Warren, BSD-3-Clause; that notice is carried in the Pi 4 file). The
;  BCM2712 machine setup is transcribed from the stub the Pi 5 firmware
;  ships, Raspberry Pi's TF-A fork, pinned for review at:
;    raspberrypi/arm-trusted-firmware branch bcm2712
;    commit fc45bc492dd655f9ea4893a384527341a48cf03d
;  and cited below as TF-A:<path>:<line>. TF-A is BSD-3-Clause.
;
;  The firmware loads this file at address zero and enters it at EL3 on
;  ALL FOUR cores (TF-A:plat/rpi/rpi5/platform.mk:38-39,
;  COLD_BOOT_SINGLE_CPU := 0). The stock stub sets the machine up, then
;  returns to EL2 (rpi5_get_spsr_for_bl33_entry) before branching to the
;  kernel. This stub omits that return: Anvil is entered at EL3, as the
;  Anvil EL3 rule requires, with x0 = the device tree.
;
;  Assemble only through the compiler's firmware-stub mode:
;    PureMetalForge --compile --armstub -t pi4 armstub8-2712.asm -o armstub8-2712.bin
;  and load it with `armstub=armstub8-2712.bin` in config.txt.
;
;  Firmware-owned fixed layout (TF-A:plat/rpi/rpi5/aarch64/armstub8_header.S,
;  identical to the Pi 4 stub's):
;    0x000 entry
;    0x0D8..0x0F0 four 64-bit secondary-core spin slots (ours, Pi 4 layout)
;    0x0F0 magic 0x5AFE570B, sharing the fourth spin slot
;    0x0F4 stub version
;    0x0F8 device-tree pointer written by firmware
;    0x0FC kernel entry written by firmware
;    0x100 subroutines
;  The firmware clears the magic when it has written both pointers
;  (TF-A:plat/rpi/rpi5/rpi5_bl31_setup.c:77-89). If it has not, this stub
;  says so on the debug UART and parks, rather than branching to zero.
;
;  DIFFERENCES FROM THE PI 4 STUB, each one read in the pinned source:
;    * The core number is MPIDR Aff1, bits 15:8, not Aff0: the A76 sets
;      MPIDR.MT. TF-A:plat/rpi/rpi5/aarch64/plat_helpers.S:52-53. The Pi 4
;      `and #3` would read 0 on every core and boot four primaries.
;    * No L2CTLR_EL1 write: that is an A72 register, done on Pi 4 only
;      (plat_helpers.S:241-261).
;    * No CPUECTLR_EL1.SMPEN or ACTLR_EL3 = $73: A72 values. The A76 is
;      coherent in hardware (platform.mk HW_ASSISTED_COHERENCY := 1). The
;      stock stub instead writes CPUECTLR_EL1 = $2000000960023000 and
;      CLUSTERECTLR_EL1 = $500 on every core (plat_helpers.S:15-18,136-142).
;    * Erratum 1946160 register sequence, for r3p0..r4p1 cores
;      (TF-A:lib/cpus/aarch64/cortex_a76.S:443-486; enabled at
;      platform.mk:62). 1286807 and 1165522 are also enabled there but
;      have no reset-time write: they govern TLB maintenance and lower-EL
;      context switches, which Anvil's own MMU code must honour later.
;    * Local timer control at $107C280000, GIC-400 at $107FFF9000 /
;      $107FFFA000 (TF-A:plat/rpi/rpi5/include/rpi_hw.h:98-102).
;    * The number of GICD_IGROUPR words comes from GICD_TYPER, not a fixed 8:
;      BCM2712 has more than 256 interrupt IDs.
;
;  CPTR_EL3, SCR_EL3 ($5B3), SCTLR_EL2/EL3 (all RES1), CNTFRQ_EL0
;  (54 MHz), CNTVOFF_EL2 and the GIC group/enable values are the Pi 4
;  stub's, for the reasons given in its header. The RES1 set of SCTLR_EL3
;  is the same in ARMv8.2.
; ======================================================================

; ----------------------------------------------------------------------
;  Constants. Written out so the file can be compared with its sources.
; ----------------------------------------------------------------------
;   LOCAL_CONTROL    $107C280000   rpi_hw.h:101
;   LOCAL_PRESCALER  $107C280008   rpi_hw.h:102
;   GIC_DISTB        $107FFF9000   rpi_hw.h:98
;   GIC_CPUB         $107FFFA000   rpi_hw.h:99
;   PL011 (UART10)   $107D001000   rpi_hw.h:83, the debug connector
;   OSC_FREQ         54000000      platform_def.h:134 = $0337F980

_start:
  msr  daifset, #15

  ; A76 control registers and erratum 1946160, every core. Kept after $100
  ; because the code before the fixed block has only $D8 bytes.
  bl   a76_setup

  ; --- the local timer: increment by 1, the crystal, divide-by-1 ------
  ; rpi5_bl31_setup.c:118-126. Global registers; every core writing the
  ; same values is harmless, as on Pi 4.
  movz x0, #0x7C28, lsl #16
  movk x0, #0x0010, lsl #32          ; $107C280000
  movz w1, #0
  str  w1, [x0]
  movz w1, #0x8000, lsl #16
  str  w1, [x0, #8]

  ; --- the architectural counter frequency, 54 MHz --------------------
  movz x0, #0xF980
  movk x0, #0x0337, lsl #16
  msr  cntfrq_el0, x0
  movz x0, #0
  msr  cntvoff_el2, x0

  ; --- floating point and SIMD untrapped, SCR_EL3 as on Pi 4 -----------
  movz x0, #0
  msr  cptr_el3, x0
  movz x0, #0x05B3
  msr  scr_el3, x0

  bl   setup_gic

  ; --- SCTLR_EL2 and SCTLR_EL3, all RES1 -------------------------------
  movz x0, #0x0830
  movk x0, #0x30C5, lsl #16
  msr  sctlr_el2, x0
  msr  sctlr_el3, x0
  isb
  msr  daifset, #15

  ; ====================================================================
  ;  THE DISPATCH, at EL3. Core number = MPIDR Aff1.
  ; ====================================================================
  mrs  x6, mpidr_el1
  lsr  x6, x6, #8
  movz x7, #0xFF
  and  x6, x6, x7                    ; core number, 0..3
  cbz  x6, primary_cpu

  ; --- cores 1..3: park in the spin table -----------------------------
  adr  x5, spin_cpu0
secondary_spin:
  wfe
  lsl  x7, x6, #3
  add  x8, x5, x7
  ldr  x4, [x8]
  cbz  x4, secondary_spin
  movz x0, #0
  b    boot_kernel

primary_cpu:
  ; The firmware's delay, then the debug UART the stock stub would have
  ; opened, then this stub's own line. See primary_prepare.
  bl   primary_prepare

  ; The firmware clears the magic once it has written both words below.
  ; A non-zero magic means they were never written: say so, do not jump.
  adr  x4, stub_magic
  ldr  w4, [x4]
  cbnz w4, magic_not_cleared
  adr  x4, kernel_entry32
  ldr  w4, [x4]
  adr  x0, dtb_ptr32
  ldr  w0, [x0]

boot_kernel:
  movz x1, #0
  movz x2, #0
  movz x3, #0
  br   x4

; ----------------------------------------------------------------------
;  THE FIXED BLOCK. Nothing above may grow past $D8.
; ----------------------------------------------------------------------
.org 0xd8
spin_cpu0:
  .quad 0
.org 0xe0
spin_cpu1:
  .quad 0
.org 0xe8
spin_cpu2:
  .quad 0
.org 0xf0
spin_cpu3:
stub_magic:
  .word 0x5AFE570B
.org 0xf4
stub_version:
  .word 0
.org 0xf8
dtb_ptr32:
  .word 0
.org 0xfc
kernel_entry32:
  .word 0

.org 0x100
; ----------------------------------------------------------------------
;  setup_gic - the Pi 4 stub's values at the BCM2712 addresses.
;  Cores 1..3 write GICD_CTLR (as stock); every core writes its banked
;  GICC_CTLR/PMR and IGROUPR0; IGROUPR1..n are global.
;  n + 1 words = GICD_TYPER.ITLinesNumber (bits 4:0) + 1.
; ----------------------------------------------------------------------
setup_gic:
  movz x2, #0x9000
  movk x2, #0x7FFF, lsl #16
  movk x2, #0x0010, lsl #32          ; GIC_DISTB = $107FFF9000
  mrs  x0, mpidr_el1
  lsr  x0, x0, #8
  movz x3, #0xFF
  and  x1, x0, x3
  cbz  x1, gic_cpu_iface
  movz w0, #3
  str  w0, [x2]                      ; GICD_CTLR = EnableGrp0 | EnableGrp1

gic_cpu_iface:
  movz x1, #0xA000
  movk x1, #0x7FFF, lsl #16
  movk x1, #0x0010, lsl #32          ; GIC_CPUB = $107FFFA000
  movz w0, #0x01E7
  str  w0, [x1]                      ; GICC_CTLR
  movz w0, #0x00FF
  str  w0, [x1, #4]                  ; GICC_PMR

  ldr  w0, [x2, #4]                  ; GICD_TYPER
  movz w3, #0x1F
  and  w0, w0, w3
  add  w0, w0, #1                    ; IGROUPR word count
  add  x2, x2, #0x80                 ; GICD_IGROUPR0
  movn w1, #0
gic_group_loop:
  str  w1, [x2]
  add  x2, x2, #4
  sub  w0, w0, #1
  cbnz w0, gic_group_loop
  ret

; ----------------------------------------------------------------------
;  a76_setup - CPUECTLR_EL1 and CLUSTERECTLR_EL1 as the stock stub writes
;  them on every core (plat_helpers.S:15-18,136-142), then erratum
;  1946160 (cortex_a76.S:443-486), only on r3p0..r4p1: MIDR_EL1 variant
;  23:20 and revision 3:0 -> (variant << 4) | revision, $30..$41.
; ----------------------------------------------------------------------
a76_setup:
  movz x0, #0x3000
  movk x0, #0x6002, lsl #16
  movk x0, #0x0009, lsl #32
  movk x0, #0x2000, lsl #48          ; $2000000960023000
  msr  s3_0_c15_c1_4, x0             ; CPUECTLR_EL1
  isb
  movz x0, #0x0500
  msr  s3_0_c15_c3_4, x0             ; CLUSTERECTLR_EL1
  isb

  mrs  x0, midr_el1
  lsr  x1, x0, #16
  movz x2, #0xF0
  and  x1, x1, x2                    ; variant << 4
  movz x2, #0x0F
  and  x0, x0, x2                    ; revision
  orr  x0, x0, x1
  cmp  x0, #0x30
  b.lo errata_done
  cmp  x0, #0x41
  b.hi errata_done

  movz x0, #3
  msr  s3_6_c15_c8_0, x0
  movz x0, #0x0002
  movk x0, #0xE390, lsl #16
  movk x0, #0x0010, lsl #32          ; $10E3900002
  msr  s3_6_c15_c8_2, x0
  movz x0, #0x0083
  movk x0, #0xFFF0, lsl #16
  movk x0, #0x0010, lsl #32          ; $10FFF00083
  msr  s3_6_c15_c8_3, x0
  movz x0, #0x03FF
  movk x0, #0x0010, lsl #16
  movk x0, #0x0002, lsl #32          ; $2001003FF
  msr  s3_6_c15_c8_1, x0

  movz x0, #4
  msr  s3_6_c15_c8_0, x0
  movz x0, #0x0082
  movk x0, #0xE380, lsl #16
  movk x0, #0x0010, lsl #32          ; $10E3800082
  msr  s3_6_c15_c8_2, x0
  movz x0, #0x0083
  movk x0, #0xFFF0, lsl #16
  movk x0, #0x0010, lsl #32          ; $10FFF00083
  msr  s3_6_c15_c8_3, x0
  movz x0, #0x03FF
  movk x0, #0x0010, lsl #16
  movk x0, #0x0002, lsl #32          ; $2001003FF
  msr  s3_6_c15_c8_1, x0

  movz x0, #5
  msr  s3_6_c15_c8_0, x0
  movz x0, #0x0200
  movk x0, #0xE380, lsl #16
  movk x0, #0x0010, lsl #32          ; $10E3800200
  msr  s3_6_c15_c8_2, x0
  movz x0, #0x03E0
  movk x0, #0xFFF0, lsl #16
  movk x0, #0x0010, lsl #32          ; $10FFF003E0
  msr  s3_6_c15_c8_3, x0
  movz x0, #0x03FF
  movk x0, #0x0010, lsl #16
  movk x0, #0x0002, lsl #32          ; $2001003FF
  msr  s3_6_c15_c8_1, x0
  isb
errata_done:
  ret

; ----------------------------------------------------------------------
;  primary_prepare - core 0 only, before it reads the firmware's words.
;
;  1. "Early GPU firmware revisions need a little break here" - the stock
;     stub's ldelay(100000). rpi5_bl31_setup.c:128-129.
;  2. Open the debug UART exactly as the stock stub does, because this
;     stub replaces the code that did it: rpi5_console_init() ->
;     console_pl011_core_init (TF-A drivers/arm/pl011/aarch64/
;     pl011_console.S). Clock 921600*16*3 = 44,236,800 Hz
;     (rpi_hw.h:220), 115200 baud: divisor = clock*4/baud = 1536,
;     IBRD = 1536 >> 6 = 24, FBRD = 1536 & $3F = 0. LCR_H = FEN|WLEN_8 =
;     $70, ECR cleared, CR = RXE|TXE|UARTEN = $301. First silicon boot,
;     2026-09-26, with no UART setup anywhere: zero bytes on the wire.
;  3. Say "ANVIL EL3 STUB" so a silent board can be told apart from a
;     board whose stub ran and whose kernel did not.
; ----------------------------------------------------------------------
primary_prepare:
  mov  x15, x30
  movz x0, #0x86A0
  movk x0, #0x0001, lsl #16          ; 100000
primary_delay:
  sub  x0, x0, #1
  cbnz x0, primary_delay

  movz x9, #0x1000
  movk x9, #0x7D00, lsl #16
  movk x9, #0x0010, lsl #32          ; PL011 $107D001000
  str  wzr, [x9, #0x30]              ; UARTCR: disable before programming
  movz w1, #24
  str  w1, [x9, #0x24]               ; UARTIBRD
  str  wzr, [x9, #0x28]              ; UARTFBRD
  movz w1, #0x70
  str  w1, [x9, #0x2C]               ; UARTLCR_H: FEN | WLEN_8
  str  wzr, [x9, #0x04]              ; UARTECR: clear errors
  movz w1, #0x0301
  str  w1, [x9, #0x30]               ; UARTCR: RXE | TXE | UARTEN

  adr  x10, stub_text
  bl   uart_puts
  mov  x30, x15
  ret

; ----------------------------------------------------------------------
;  uart_puts - x10 = NUL-terminated string. Uses x9..x13.
; ----------------------------------------------------------------------
uart_puts:
  movz x9, #0x1000
  movk x9, #0x7D00, lsl #16
  movk x9, #0x0010, lsl #32          ; PL011 DR $107D001000
puts_next:
  ldrb w11, [x10]
  cbz  w11, puts_done
puts_wait:
  ldr  w12, [x9, #0x18]              ; FR
  movz w13, #0x20                    ; TXFF
  and  w12, w12, w13
  cbnz w12, puts_wait
  str  w11, [x9]
  add  x10, x10, #1
  b    puts_next
puts_done:
  ret

; ----------------------------------------------------------------------
;  magic_not_cleared - the firmware never wrote the kernel/DTB words.
;  Say so on the debug UART (opened by primary_prepare) and park. Loud,
;  not a branch to address zero.
; ----------------------------------------------------------------------
magic_not_cleared:
  adr  x10, magic_text
  bl   uart_puts
magic_park:
  wfe
  b    magic_park

stub_text:
  .byte 65, 78, 86, 73, 76, 32, 69, 76, 51, 32, 83, 84, 85, 66, 13, 10, 0  ; "ANVIL EL3 STUB\r\n"
magic_text:
  .byte 83, 84, 85, 66, 32, 77, 65, 71, 73, 67, 13, 10, 0  ; "STUB MAGIC\r\n"

.align 256
