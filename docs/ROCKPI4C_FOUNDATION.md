# Original ROCK Pi 4C v1.2 foundation

Status: desk proof only. No line in this document claims a hardware run.

## Identity and ownership

This target is the original ROCK Pi 4C PCB v1.2 with RK3399. It is not a
Raspberry Pi 4 and not the RK3399-T 4C+. The `rockpi4c` compiler profile uses
the existing ARMv8-A A64 IR/emitter/assembler and its own RK3399 intrinsic
file. It does not import BCM2711 mailbox, V3D, GENET, interrupt-controller or
MMIO definitions.

U-Boot and TF-A retain DRAM discovery, board clocks, pin mux, PSCI and secure
firmware ownership. Anvil enters at Non-secure EL2 and never resets those
subsystems in this milestone.

## Exact U-Boot handoff

The wrapper is a 64-byte little-endian arm64 `Image` header followed by the
flat compiler payload linked at `0x02000040`. Header instruction zero branches
to byte 64. `text_offset` is zero, `image_size` is the exact file length,
flags bit 3 asks U-Boot to respect the load placement, and magic is `ARM\x64`.

Load the exact board DTB at `0x12000000` and the Image at `0x02000000`, then:

```text
booti 0x02000000 - 0x12000000
```

No initrd is permitted in the first contract. At entry x0 is the FDT and
x1-x3 are zero. The runtime requires EL2, the boot CPU, the exact FDT address,
a bounded valid FDT header/structure/reserve map, and identity strings for
`radxa,rockpi4c`, `rockchip,rk3399`, `serial2:1500000n8`, and `arm,gic-v3`.
It parks on every disagreement.

## Memory contract

| Range | Owner |
|---|---|
| `0x02000000..0x0200003f` | arm64 Image header |
| `0x02000040..0x027fffff` | linked code window |
| `0x02800000..0x02bfffff` | compiler BSS window |
| `0x02f00000..0x02ffffff` | primary cold-entry stack, 1 MiB |
| `0x03000000..0x030fffff` | held for later exception/multicore ownership |
| `0x12000000..0x121fffff` | exact external FDT handoff window |

The compiler refuses placement outside the conservative
`0x02000000..0x11ffffff` bootstrap envelope. The runtime rejects an FDT or
firmware reserve-map entry that intersects `0x02000000..0x030fffff`.
Installed 4 GiB is not treated as permission to allocate it; widening memory
ownership requires parsing the live memory and reserved-memory nodes.

## Earliest witness, vectors, timer and GIC

U-Boot configures RK3399 UART2 at `0xff1a0000` for 1,500,000 8N1. Anvil adopts
that state and emits its board-specific witness before FDT parsing. It does not
guess CRU, GRF, reset or divisor programming.

The architectural counter supplies every deadline; frequency and monotonicity
are validated first. All polling also has a finite iteration ceiling.

Anvil installs a 2 KiB-aligned EL2 vector table while every DAIF mask remains
set. Every vector captures ESR/FAR/ELR/SPSR once and parks. There is no IRQ
return until dispatch has hardware proof.

The GICv3 foundation uses GICD `0xfee00000` and six 128 KiB GICR frames from
`0xfef00000`. It finds the current frame by comparing GICR_TYPER affinity with
MPIDR, wakes only that redistributor, and owns only hypervisor physical timer
INTID 26. The board root deliberately leaves IRQ masked and never arms CNTHP
in this milestone.

## Desk gates and first board run

```text
python tools/rockpi4c_foundation_check.py --compiler <candidate>
python tools/build.py rockpi4c --compiler <candidate>
```

Before the first board run, verify the generated `Image.json` hash and retain
the proven stock-U-Boot recovery media. First-run acceptance is only:

1. the early UART witness appears at 1,500,000 baud;
2. no refusal appears;
3. `FOUNDATION READY; IRQ STILL MASKED` appears;
4. U-Boot recovery still works after a power cycle.

That run does not prove timer interrupts, secondary cores, storage, display,
networking or Mali.

## Primary references and clean implementation

- Arm, *A-profile Architecture Reference Manual*, architectural exception,
  timer and GIC system-register definitions.
- Arm, *Generic Interrupt Controller Architecture Specification*, GICv3.
- Linux kernel documentation, `Documentation/arch/arm64/booting.rst`, arm64
  Image header and register handoff.
- Devicetree bindings and DTS for `rk3399-rock-pi-4c`, `arm,gic-v3`,
  `arm,armv8-timer` and `snps,dw-apb-uart`.
- Mainline U-Boot `booti` implementation and ROCK Pi 4C defconfig/DTS.

Those references establish interfaces and facts. This MIT repository contains
an original implementation; no GPL implementation code was copied.
