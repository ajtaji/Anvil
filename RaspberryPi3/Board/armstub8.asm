; Copyright (c) 2016-2019 Raspberry Pi (Trading) Ltd.
; Copyright (c) 2016 Stephen Warren <swarren@wwwdotorg.org>
; All rights reserved.
;
; Redistribution and use in source and binary forms, with or without
; modification, are permitted provided that the following conditions are met:
; 1. Redistributions of source code must retain the above copyright notice,
;    this list of conditions and the following disclaimer.
; 2. Redistributions in binary form must reproduce the above copyright notice,
;    this list of conditions and the following disclaimer in the documentation
;    and/or other materials provided with the distribution.
; 3. Neither the name of the copyright holder nor the names of its contributors
;    may be used to endorse or promote products derived from this software
;    without specific prior written permission.
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
; Translation/adaptation of Raspberry Pi's armstubs/armstub8.S at commit
; 439b6198a9b340de5998dd14a26a0d9d38a6bcac. Pi 3-specific values below use
; the BCM2837 branch: local-control timer at 0x40000000, 19.2 MHz source, and
; no GIC setup. This file is assembled in explicit firmware-stub mode.
;
; Anvil's Raspberry Pi 3 BCM2837 AArch64 firmware stub.
; Firmware loads this file at 0 and enters at EL3. Anvil remains at EL3; the
; stub does not prepare an EL2 return context or execute ERET. Keep the fixed
; firmware fields at F8 (DTB) and FC (kernel entry); Main captures x0 first.
; The Pi 3 uses its local-control block at 0x40000000 and 19.2 MHz crystal.
; No BCM2711 GIC registers or Pi 4 timer frequencies belong here.

_start:
  msr daifset, #15
  ; Select the banked EL3 stack explicitly. Keep compiler entry on the
  ; configured 16-byte-aligned stack even if firmware selected SP_EL0.
  msr spsel, #1
  movz x9, #0x01F0, lsl #16
  mov sp, x9

  ; BCM2837 local timer and architectural counter source.
  movz x0, #0x4000, lsl #16
  movz w1, #0
  str w1, [x0]
  movz w1, #0x8000, lsl #16
  str w1, [x0, #8]
  movz x0, #0xF800
  movk x0, #0x0124, lsl #16
  msr cntfrq_el0, x0
  ; Enable FP/SIMD at EL3, and SMP coherency on the Cortex-A53 cluster.
  msr cptr_el3, xzr
  movz x0, #0x40
  msr cpuectlr_el1, x0
  mrs x0, l2ctlr_el1
  movz x1, #0x22
  orr x0, x0, x1
  msr l2ctlr_el1, x0

  ; Keep execution Secure at EL3. SCR.NS describes lower-level state only;
  ; SMD stays set because this monitor has no SMC dispatcher. Route IRQ to
  ; EL3 while DAIF is masked until the monitor installs its vectors. The
  ; BCM2837 legacy interrupt controller is not a GIC and is not initialized.
  movz x0, #0x05B3
  msr scr_el3, x0
  movz x0, #0x0073
  msr actlr_el3, x0
  movz x0, #0x30C5, lsl #16
  movk x0, #0x0830
  msr sctlr_el3, x0
  isb
  msr daifset, #15
  b el3_dispatch

; Firmware-owned spin-table/header layout. Firmware clears the shared
; magic/version word after reading it, leaving slot 3 available for a core.
.org 0xD8
spin_cpu0:
  .quad 0
.org 0xE0
spin_cpu1:
  .quad 0
.org 0xE8
spin_cpu2:
  .quad 0
.org 0xF0
spin_cpu3:
  .word 0x5AFE570B
.org 0xF4
stub_version:
  .word 0
.org 0xF8
dtb_ptr32:
  .word 0
.org 0xFC
kernel_entry32:
  .word 0
.org 0x100
; Keep all executable EL3 dispatch code after the firmware-owned header and
; spin table above. The slot ABI occupies 0xD8..0xFF even when the entry
; stub itself grows beyond one firmware block.
el3_dispatch:
  msr daifset, #15
  mrs x6, mpidr_el1
  movz x7, #3
  and x6, x6, x7
  cbz x6, primary_cpu
  adr x5, spin_cpu0
secondary_spin:
  wfe
  lsl x7, x6, #3
  add x8, x5, x7
  ldr x4, [x8]
  cbz x4, secondary_spin
  movz x0, #0
  b boot_kernel

primary_cpu:
  adr x4, kernel_entry32
  ldr w4, [x4]
  adr x0, dtb_ptr32
  ldr w0, [x0]
boot_kernel:
  movz x1, #0
  movz x2, #0
  movz x3, #0
  br x4

.align 256
