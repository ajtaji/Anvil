; Copyright (c) 2016-2019 Raspberry Pi (Trading) Ltd.
; Copyright (c) 2016 Stephen Warren <swarren@wwwdotorg.org>
; All rights reserved.
;
; Redistribution and use in source and binary forms, with or without
; modification, are permitted provided that the following conditions are met:
; * Redistributions of source code must retain the above copyright notice,
;   this list of conditions and the following disclaimer.
; * Redistributions in binary form must reproduce the above copyright notice,
;   this list of conditions and the following disclaimer in the documentation
;   and/or other materials provided with the distribution.
; * Neither the name of the copyright holder nor the names of its contributors
;   may be used to endorse or promote products derived from this software
;   without specific prior written permission.
;
; THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
; AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
; IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
; ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
; LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
; CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
; SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
; INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
; CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
; ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
; POSSIBILITY OF SUCH DAMAGE.
;
; ======================================================================
;  armstub8.asm - Raspberry Pi 4 boot stub that enters Anvil at EL3.
;
;  This is a source translation and modification of Raspberry Pi's
;  tools/armstubs/armstub8.S, pinned for review at commit:
;    439b6198a9b340de5998dd14a26a0d9d38a6bcac
;  https://github.com/raspberrypi/tools/blob/439b6198a9b340de5998dd14a26a0d9d38a6bcac/armstubs/armstub8.S
;
;  The firmware loads this file at address zero and enters it at EL3.
;  The stock BCM2711 GIC stub performs the machine setup below, then
;  executes ERET to EL2 before branching to kernel8.img. This version
;  deliberately omits that exception return, initializes SCTLR_EL3, masks
;  DAIF before routing IRQ to EL3, and enters kernel8.img at EL3. Everything
;  else keeps the stock order and values except that required EL3 IRQ route.
;
;  This file must be assembled only through the external compiler's
;  explicit firmware-stub mode. Ordinary program images remain forbidden
;  below address 0x1000. tools/a64/a64_el3_check.py builds this source,
;  verifies the fixed layout in the bytes, and executes both dispatch paths.
;
;  Firmware-owned fixed layout (stock armstub8.S lines 175-210):
;    0x000 entry
;    0x0D8..0x0F0 four 64-bit secondary-core spin slots
;    0x0F0 magic 0x5AFE570B, sharing the fourth spin slot
;    0x0F4 stub version
;    0x0F8 device-tree pointer written by firmware
;    0x0FC kernel entry written by firmware
;    0x100 GIC setup
;
;  The firmware reads the magic/version and clears those eight bytes
;  before the fourth spin slot is used. The output is padded to a
;  256-byte boundary, matching the upstream Makefile's binary rule.
;
;  CPTR_EL3.TFP is cleared so FP/SIMD cannot be trapped by EL3. SCR_EL3
;  starts from the stock 0x5B1, with IRQ added to make 0x5B3: NS selects
;  the state below EL3, while EL3's own accesses remain Secure. SMD remains
;  set because this phase has no
;  SMC dispatcher. IRQ is added because this stub deliberately remains at
;  EL3: without SCR_EL3.IRQ, a pending physical IRQ is not taken at EL3.
;  Both GIC groups are enabled and all INTIDs are placed in Group 1 exactly
;  as in the stock BCM2711 GIC stub; GICC FIQEn remains clear, so the owned
;  secure timer is delivered through the monitor's IRQ vector.
; ======================================================================

; ----------------------------------------------------------------------
;  Constants. Written out rather than hidden in an include so a reviewer
;  can compare this file line by line with the pinned stock stub without
;  resolving another source file.
; ----------------------------------------------------------------------
;   LOCAL_CONTROL   $FF800000    armstub8.S:37   (BCM2711, low peripheral)
;   LOCAL_PRESCALER $FF800008    armstub8.S:38
;   GIC_DISTB       $FF841000    armstub8.S:49
;   GIC_CPUB        $FF842000    armstub8.S:50
;   OSC_FREQ        54000000     armstub8.S:54   = $0337F980

_start:
  ; Route nothing to an unprepared vector. Firmware usually arrives masked,
  ; but an EL3-retaining stub must establish that fact itself before SCR_EL3
  ; is allowed to route physical IRQ here. InterruptStart is the sole later
  ; owner that clears DAIF.I after the monitor has installed its vectors.
  msr  daifset, #15

  ; --- the local timer: increment by 1, source the 54 MHz crystal -----
  ; Bit 9 clear = increment by one rather than two; bit 8 clear = the
  ; crystal rather than the APB clock. armstub8.S:93-99.
  movz x0, #0xFF80, lsl #16          ; LOCAL_CONTROL
  movz w1, #0
  str  w1, [x0]
  ; LOCAL_PRESCALER: divide-by ($80000000 / value) == 1. armstub8.S:100-102.
  movz w1, #0x8000, lsl #16
  str  w1, [x0, #8]

  ; --- L2 read/write cache latency 3. armstub8.S:104-108 --------------
  mrs  x0, l2ctlr_el1
  movz x1, #0x22
  orr  x0, x0, x1
  msr  l2ctlr_el1, x0

  ; --- the architectural counter frequency. armstub8.S:110-112 --------
  ; 54,000,000 = $0337F980. Read back by RaspberryPi4/Lib/timer.pi4 and
  ; by every gate that computes a timeout.
  movz x0, #0xF980
  movk x0, #0x0337, lsl #16
  msr  cntfrq_el0, x0

  ; --- the virtual counter offset. armstub8.S:114-115 -----------------
  movz x0, #0
  msr  cntvoff_el2, x0

  ; --- floating point and SIMD, on. armstub8.S:117-119 ----------------
  ; CPTR_EL3 = 0 clears TFP at bit 10. See the header: this is the line
  ; an EL3 monitor cannot do without and cannot do for itself, because
  ; the compiler's preamble opens the EL2 gate and not this one.
  movz x0, #0
  msr  cptr_el3, x0

  ; --- SCR_EL3. stock value plus IRQ routing retained at EL3 -----------
  movz x0, #0x05B3
  msr  scr_el3, x0

  ; --- ACTLR_EL3. armstub8.S:68-69, 125-127 ---------------------------
  movz x0, #0x0073
  msr  actlr_el3, x0

  ; --- CPUECTLR_EL1.SMPEN, bit 6. armstub8.S:71-72, 129-131 -----------
  movz x0, #0x0040
  msr  cpuectlr_el1, x0

  ; --- the GIC, exactly as the stock stub leaves it -------------------
  bl   setup_gic

  ; --- SCTLR_EL2, all RES1. armstub8.S:136-141 ------------------------
  movz x0, #0x0830
  movk x0, #0x30C5, lsl #16
  msr  sctlr_el2, x0

  ; --- SCTLR_EL3, the same all-RES1 value, and OURS -------------------
  ; The stock stub does not write this because it is leaving. We are
  ; not. An isb follows because SCTLR governs how the instructions after
  ; it are fetched and translated, and the architecture does not
  ; guarantee the write is in effect for them without one.
  msr  sctlr_el3, x0
  isb

  ; --- assert the entry mask again at the final handoff ----------------
  ; The first mask makes configuring SCR/GIC safe. This second assertion
  ; keeps the final boot contract adjacent to the kernel dispatch it guards.
  msr  daifset, #15

  ; ====================================================================
  ;  THE DISPATCH - the stock stub's `in_el2` block, run AT EL3.
  ;  armstub8.S:149-171, unchanged except that nothing has dropped a
  ;  level to get here.
  ; ====================================================================
  mrs  x6, mpidr_el1
  movz x7, #3
  and  x6, x6, x7                    ; core number, 0..3
  cbz  x6, primary_cpu

  ; --- cores 1..3: park in the spin table -----------------------------
  ; A released core branches at EL3 too. That is the honest consequence
  ; of this stub and it is written down here rather than discovered:
  ; RaspberryPi4/Lib/smp.pi4's trampoline records CurrentEL as a witness
  ; and will now record 3 on a board booted this way.
  adr  x5, spin_cpu0
secondary_spin:
  wfe
  lsl  x7, x6, #3                    ; core * 8
  add  x8, x5, x7
  ldr  x4, [x8]
  cbz  x4, secondary_spin
  movz x0, #0
  b    boot_kernel

primary_cpu:
  ; The firmware wrote both of these into this file before it branched
  ; here - see the layout note. They are 32-bit words on purpose: the
  ; firmware writes .word, and a 64-bit read would pick up the neighbour.
  adr  x4, kernel_entry32
  ldr  w4, [x4]
  adr  x0, dtb_ptr32
  ldr  w0, [x0]

boot_kernel:
  ; The arm64 boot protocol: x0 = the device tree, x1..x3 zero. Anvil
  ; captures x0 in Main()'s first instruction - see
  ; RaspberryPi4/Board/hw_boot.pi4 and RaspberryPi4/Board/board.pi4.
  movz x1, #0
  movz x2, #0
  movz x3, #0
  br   x4

; ----------------------------------------------------------------------
;  THE FIXED BLOCK. Nothing above may grow past $D8; the gate checks it
;  by building this file and reading the bytes, so an overflow is a
;  failed gate rather than a board that does not come back.
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
; spin_cpu3 lives here too - the firmware clears these eight bytes after
; reading the magic and the version, which is what makes one address
; serve both. armstub8.S:187-200.
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
;  setup_gic - transcribed from armstub8.S:214-235.
;
;  Called at EL3, therefore Secure - see the SCR_EL3 note in the header
;  for why NS=1 does not change that. Every interrupt is put in group 1
;  and both groups are enabled at the distributor and the CPU interface.
;
;  WHAT THE MONITOR INHERITS FROM THIS. The resident owner is now
;  RaspberryPi4/Lib/interrupts.pi4; its EL3 path programs and verifies
;  these same secure-view values before it accepts an interrupt claim:
;
;    * GICD_CTLR = 3. In the SECURE view bit 0 is EnableGrp0 and bit 1
;      is EnableGrp1, so 3 is "forward both".
;    * GICC_CTLR = $1E7 = EnableGrp0 | EnableGrp1 | AckCtl | the four
;      bypass-disable bits, with FIQEn CLEAR - so group 0 signals IRQ
;      too, and there is no FIQ path to write a handler for. AckCtl is
;      the bit that lets a Secure reader acknowledge a group 1
;      interrupt through GICC_IAR, which is exactly what an EL3 monitor
;      is doing when it services the timer.
;    * GICC_PMR = $FF, the widest mask. InterruptInit deliberately
;      narrows it to $F0 while it owns the interface and restores the
;      inherited value when that ownership ends.
;    * GICD_IGROUPR0..7 = all ones: INTIDs 0..255 are group 1. That
;      includes PPI 10 / INTID 26, the EL2 physical timer the monitor
;      uses, and PPI 13 / INTID 29, the SECURE physical timer an EL3
;      monitor could use instead. Both are reachable from EL3; the
;      choice follows the pinned stock stub; the offline gate checks it.
;
;  THE PRIMARY CORE DOES NOT WRITE GICD_CTLR, and that is the stock
;  stub's behaviour, not a slip. GICD_CTLR is one global register, cores
;  1..3 all run this, and any one of them setting it is enough. It is
;  transcribed as-is because a stub that "fixed" it would no longer be
;  the machine every other Pi 4 boots into.
; ----------------------------------------------------------------------
setup_gic:
  mrs  x0, mpidr_el1
  movz x3, #3
  and  x1, x0, x3
  cbz  x1, gic_cpu_iface              ; core 0 skips the distributor write

  movz x2, #0xFF84, lsl #16
  movz x3, #0x1000
  add  x2, x2, x3                     ; GIC_DISTB = $FF841000
  movz w0, #3                         ; EnableGrp0 | EnableGrp1 (Secure view)
  str  w0, [x2]                       ; GICD_CTLR

gic_cpu_iface:
  movz x1, #0xFF84, lsl #16
  movz x3, #0x2000
  add  x1, x1, x3                     ; GIC_CPUB = $FF842000
  movz w0, #0x01E7
  str  w0, [x1]                       ; GICC_CTLR
  movz w0, #0x00FF
  str  w0, [x1, #4]                   ; GICC_PMR

  ; Every INTID to group 1. Eight words at GICD_IGROUPR ($080), which is
  ; 256 interrupt IDs - the stock stub's IT_NR of 8 enable-registers.
  movz x2, #0xFF84, lsl #16
  movz x3, #0x1080
  add  x2, x2, x3                     ; GIC_DISTB + GICD_IGROUPR
  movn w1, #0                         ; all ones
  movz x0, #8
gic_group_loop:
  str  w1, [x2]
  add  x2, x2, #4
  sub  x0, x0, #1
  cbnz x0, gic_group_loop
  ret

; ----------------------------------------------------------------------
;  Pad to a 256-byte boundary, as the stock build does.
; ----------------------------------------------------------------------
.align 256
