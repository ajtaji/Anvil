#!/usr/bin/env python3
"""Structural and encoder contract for the bounded RK3399 PL330 driver."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "RockPi4C/Lib/dma_pl330.pbi"


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def procedure(source: str, name: str) -> str:
    found = re.search(
        rf"(?ims)^Procedure(?:\.i)?\s+{re.escape(name)}\b.*?^EndProcedure\s*$",
        source,
    )
    need(found is not None, f"missing {name}")
    return found.group(0)


def mov(destination: int, value: int) -> bytes:
    return bytes((0xBC, destination)) + value.to_bytes(4, "little")


def model(words: int, revision: int) -> bytes:
    need(1 <= words <= 65536, "model word bound")
    need(words <= 256 or words % 256 == 0, "model loop shape")
    body = bytes((0x04, 0x08)) if revision >= 1 else bytes((0x04, 0x12, 0x08, 0x13))
    code = bytearray()
    code += mov(1, 0x00414105)
    code += mov(0, 0x11223344)
    code += mov(2, 0x55667788)
    if words <= 256:
        code += bytes((0x22, words - 1))
        code += body
        code += bytes((0x3C, len(body)))
    else:
        code += bytes((0x20, words // 256 - 1, 0x22, 0xFF))
        code += body
        code += bytes((0x3C, len(body), 0x38, len(body) + 4))
    code += bytes((0x34, 0x00, 0x00))
    return bytes(code)


def main() -> None:
    source = DRIVER.read_text(encoding="utf-8")
    lower = source.lower()

    # Authority and exact instance.
    for token in (
        "release-4.4-rockpi4 drivers/dma/pl330.c",
        "arch/arm64/boot/dts/rockchip/rk3399.dtsi",
        "drivers/clk/rockchip/clk-rk3399.c",
        "rk3399 trm figure 1-1",
        "#rock_dma_pl330_base = $fffc0000",
        "#rock_dma_pl330_part_designer = $41330",
    ):
        need(token in lower, f"missing authority/identity token: {token}")

    init = procedure(source, "RockDmaPl330Init").lower()
    run = procedure(source, "RockDmaPl330RunProgram").lower()
    kill = procedure(source, "RockDmaPl330Kill").lower()
    debug = procedure(source, "RockDmaPl330DebugExecute").lower()
    transfer = procedure(source, "RockDmaPl330Transfer").lower()
    build = procedure(source, "RockDmaPl330BuildProgram").lower()
    fill = procedure(source, "RockDmaPl330Fill32").lower()
    generic_copy = procedure(source, "RockDmaCopy").lower()
    generic_fill = procedure(source, "RockDmaFill32").lower()

    # Clock/security/reset ownership. The pinned DTS assigns 100 MHz to
    # ACLK_PERILP0, while the three observed boot paths use 400/594/800 MHz
    # GPLL rates. Derive a ceiling divider so none can exceed that assignment.
    # The GPLL source, parent, NoC and leaf read back enabled (active-low).
    for token in (
        "rocksecurityreleasedma()",
        "rock_dma_pl330_gpll_rate=rockcrupllrate($80,1,47)",
        "rock_dma_pl330_gpll_rate<>400000000",
        "rock_dma_pl330_gpll_rate<>594000000",
        "rock_dma_pl330_gpll_rate<>800000000",
        "aclkdivider=rockcruceilingdivider(rock_dma_pl330_gpll_rate,#rock_dma_pl330_aclk_target)",
        "aclkdivider<1 or aclkdivider>32",
        "rock_dma_pl330_aclk_rate=rock_dma_pl330_gpll_rate/aclkdivider",
        "clksel23plan=#rock_dma_pl330_clksel23_gpll_base | (aclkdivider-1)",
        "rock_dma_pl330_clksel23_before=rockcruread(#rock_cru_clksel+23*4)",
        "rock_dma_pl330_gate7_before=rockcruread(#rock_cru_clkgate+7*4)",
        "rock_dma_pl330_gate25_before=rockcruread(#rock_cru_clkgate+25*4)",
        "rockcrufield(#rock_cru_clksel+23*4,#rock_dma_pl330_clksel23_mask,clksel23plan)",
        "rockcrugate(7,0,1)",
        "rockcrugate(7,2,1)",
        "rockcrugate(25,7,1)",
        "rockcrugate(25,5,1)",
        "rock_dma_pl330_clksel23=rockcruread(#rock_cru_clksel+23*4)",
        "#rock_cru_clkgate+7*4",
        "#rock_cru_clkgate+25*4",
        "#rock_cru_softrst+10*4",
        "(rock_dma_pl330_reset10 & #rock_dma_pl330_reset_perilp0_noc)<>0",
        "(rock_dma_pl330_reset10 & #rock_dma_pl330_reset_dmac0)<>0",
        "(rock_dma_pl330_clksel23 & #rock_dma_pl330_clksel23_mask)<>clksel23plan",
        "(rock_dma_pl330_gate7 & $5)<>0",
        "(rock_dma_pl330_gate25 & $a0)<>0",
    ):
        need(token in init, f"init lost clock/security/readback contract: {token}")
    # EL3 uses the TRM's secure APB aperture. Silicon identity proved that
    # alias directly, so the driver has no reason to rewrite SGRF tie-offs or
    # pulse either PL330/reset fabric while HDMI is starting.
    need("$ff6d0000" not in lower and "$ff6e0000" not in lower and
         "$fffd0000" not in lower,
         "EL3 PL330 driver gained a normal-world or DMAC1 aperture")
    need("rockdmapl330secureadmission" not in lower and
         "#rock_dma_pl330_sgrf" not in lower,
         "secure-alias driver retained obsolete SGRF admission writes")
    need("rockcrureset(" not in lower and
         "#rock_dma_pl330_reset_dmac0_id" not in lower,
         "secure-alias driver must observe reset state without pulsing reset")
    need("#rock_dma_pl330_clksel23_mask = $739f" in lower,
         "CLKSEL23 ownership mask no longer matches U-Boot")
    need("#rock_dma_pl330_clksel23_gpll_base = $1080" in lower,
         "CLKSEL23 GPLL/HCLK/PCLK base no longer matches RK3399 clock data")
    need("#rock_dma_pl330_aclk_target = 100000000" in lower,
         "ACLK_PERILP0 target no longer matches the pinned DTS assignment")
    need("#rock_dma_pl330_reset_perilp0_noc = $1" in lower,
         "PERILP0 NoC reset mask no longer matches the RK3399 reset binding")
    need("#rock_dma_pl330_reset_dmac0 = $8" in lower,
         "DMAC0 reset mask no longer matches the RK3399 reset binding")
    # EL3 and coherency admission, secure manager and capability checks.
    for token in (
        "rock_current_el<>12",
        "(rock_sctlr_el3 & $1005)<>0",
        "rock_timer_frequency<1000000",
        "rock_dma_pl330_pid0=rockdmapl330read(#rock_dma_pl330_pid0)",
        "rock_dma_pl330_pid1=rockdmapl330read(#rock_dma_pl330_pid1)",
        "rock_dma_pl330_pid2=rockdmapl330read(#rock_dma_pl330_pid2)",
        "rock_dma_pl330_pid3=rockdmapl330read(#rock_dma_pl330_pid3)",
        "rock_dma_pl330_cid0=rockdmapl330read(#rock_dma_pl330_cid0)",
        "rock_dma_pl330_cid1=rockdmapl330read(#rock_dma_pl330_cid1)",
        "rock_dma_pl330_cid2=rockdmapl330read(#rock_dma_pl330_cid2)",
        "rock_dma_pl330_cid3=rockdmapl330read(#rock_dma_pl330_cid3)",
        "rock_dma_pl330_pid=0 and rock_dma_pl330_cid=0",
        "(rock_dma_pl330_pid & $fffff)<>#rock_dma_pl330_part_designer",
        "rock_dma_pl330_cid<>#rock_dma_pl330_component_id",
        "rock_dma_pl330_channels",
        "rock_dma_pl330_events",
        "rock_dma_pl330_bus_width",
        "rock_dma_pl330_buffer_depth",
        "(rock_dma_pl330_cr0 & #rock_dma_pl330_boot_man_ns)<>0",
    ):
        need(token in init, f"init lost EL3/capability contract: {token}")
    need("#rock_dma_pl330_component_id = $b105f00d" in lower,
         "PrimeCell component ID contract changed")
    need("#rock_dma_pl330_error_unreachable = 18" in lower,
         "all-zero admission failure no longer has a distinct error")
    for token in (
        "rock_dma_pl330_ds",
        "rock_dma_pl330_fsm",
        "rock_dma_pl330_fsc",
        "rock_dma_pl330_ftm",
        "rock_dma_pl330_cs0",
        "rock_dma_pl330_ftc0",
        "rock_dma_pl330_es",
        "rock_dma_pl330_intstatus",
    ):
        need(token in init, f"init lost idle/activity admission: {token}")

    # Public transfer bounds, physical-address limits and doubling fill.
    for token in (
        "(bytes & 3)<>0",
        "(destination & 3)<>0",
        "(source & 3)<>0",
        "destination>$100000000-bytes",
        "if chunkremaining>#rock_dma_pl330_max_chunk : chunkremaining=#rock_dma_pl330_max_chunk : endif",
        "batchwords=65536",
        "batchwords=(words/256)*256",
        "rock_dma_pl330_completed_bytes",
    ):
        need(token in transfer, f"transfer lost bound/alignment contract: {token}")
    need("#rock_dma_pl330_max_chunk = $100000" in lower, "chunk cap is not 1 MiB")
    need("physical 32-bit addresses, four-byte aligned lengths up to 1 mib" not in lower,
         "header still describes the old public 1 MiB request limit")
    need("procedurereturn rockdmapl330copy(destination,source,bytes)" in generic_copy,
         "generic copy wrapper does not delegate to bounded PL330 copy")
    need("procedurereturn rockdmapl330fill32(destination,value,bytes)" in generic_fill,
         "generic fill wrapper does not delegate to bounded PL330 fill")
    need("#rock_dma_pl330_ccr_secure_copy = $00414105" in lower,
         "copy CCR is not secure privileged noncacheable 32-bit incrementing")
    need("$00414104" not in lower and "fixedsource" not in lower,
         "unsupported fixed-memory-source fill path returned")
    for token in (
        "for index=0 to seedbytes/4-1",
        "pokel(destination+index*4,value & $ffffffff)",
        "if seedbytes>#rock_dma_pl330_fill_seed_bytes : seedbytes=#rock_dma_pl330_fill_seed_bytes : endif",
        "copybytes=completed",
        "if copybytes>bytes-completed : copybytes=bytes-completed : endif",
        "rockdmapl330copy(destination+completed,destination,copybytes)",
        "rock_dma_pl330_completed_bytes=completed+rock_dma_pl330_completed_bytes",
    ):
        need(token in fill, f"fill lost bounded doubling-copy contract: {token}")
    need("#rock_dma_pl330_fill_seed_bytes = 256" in lower and
         "global dim rock_dma_pl330_fill_block" not in lower,
         "fill must seed the destination without a dedicated 64 KiB BSS buffer")
    full_hd = 1920 * 1080 * 4
    completed = min(full_hd, 256)
    dma_jobs = 0
    while completed < full_hd:
        copied = min(completed, full_hd - completed)
        need(copied <= completed, "fill source and destination spans overlap")
        dma_jobs += (copied + 0x100000 - 1) // 0x100000
        completed += copied
    need(dma_jobs <= 20, "full-HD fill exceeds the bounded DMA-job budget")

    # Radxa encoder: MOV order, finite loops, R0P0 barriers, SEV0 and END.
    ordered = [
        "#rock_dma_pl330_mov_ccr",
        "#rock_dma_pl330_mov_sar",
        "#rock_dma_pl330_mov_dar",
        "rockdmapl330emitlp(",
        "rockdmapl330emitburst(",
        "rockdmapl330emitlpend(",
        "#rock_dma_pl330_cmd_sev",
        "#rock_dma_pl330_cmd_end",
    ]
    positions = [build.find(token) for token in ordered]
    need(all(p >= 0 for p in positions) and positions == sorted(positions),
         "microcode setup/order no longer matches Radxa request encoder")
    burst = procedure(source, "RockDmaPl330EmitBurst").lower()
    for token in ("#rock_dma_pl330_cmd_ld", "#rock_dma_pl330_cmd_rmb",
                  "#rock_dma_pl330_cmd_st", "#rock_dma_pl330_cmd_wmb"):
        need(token in burst, f"missing Radxa R0P0 sequence element: {token}")
    need(burst.find("cmd_ld") < burst.find("cmd_rmb") < burst.find("cmd_st") < burst.find("cmd_wmb"),
         "R0P0 workaround order changed")

    # Validate known byte streams independently of the source implementation.
    need(model(1, 1).hex() ==
         "bc0105414100bc0044332211bc0288776655220004083c02340000",
         "R1P0 single-copy encoder oracle changed")
    need(model(256, 0).hex() ==
         "bc0105414100bc0044332211bc028877665522ff041208133c04340000",
         "R0P0 incrementing-copy encoder oracle changed")
    nested = model(65536, 1)
    need(nested[-13:] == bytes((0x20, 0xFF, 0x22, 0xFF, 0x04, 0x08,
                                0x3C, 0x02, 0x38, 0x06, 0x34, 0x00, 0x00)),
         "nested-loop back-jump oracle changed")

    # Debug execution and bounded recovery follow Radxa's register ordering.
    need(debug.find("dbgstatus") < debug.find("dbginst0") < debug.find("dbginst1") < debug.find("dbgcmd"),
         "debug instruction register order changed")
    for token in ("rocktimerticks()", "#rock_dma_pl330_debug_timeout_us",
                  "#rock_dma_pl330_dbg_busy"):
        need(token in debug, f"debug submission lost finite bound: {token}")
    need("rockdmapl330debugexecute(#rock_dma_pl330_cmd_kill,0,0)" in kill,
         "bounded channel-0 KILL is missing")
    need("#rock_dma_pl330_debug_timeout_us" in kill and "rocktimerticks()" in kill,
         "KILL completion is unbounded")
    for token in ("#rock_dma_pl330_cmd_go", "goargument,1", "rockwatchdogpet()",
                  "#rock_dma_pl330_job_timeout_us", "rockdmapl330snapshotfault()",
                  "rockdmapl330kill()"):
        need(token in run, f"run lost secure/bounded/deadman contract: {token}")
    need(run.find("rockdmapl330snapshotfault()") < run.find("rockdmapl330kill()"),
         "first-fault telemetry is no longer frozen before KILL")
    for token in ("rock_dma_pl330_ds", "rock_dma_pl330_fsm", "rock_dma_pl330_fsc",
                  "rock_dma_pl330_ftm", "rock_dma_pl330_cs0", "rock_dma_pl330_ftc0"):
        need(token in run, f"run lost live fault telemetry: {token}")
    need("rockwatchdogpet()" not in kill,
         "KILL wait must stay bounded by the armed deadman rather than feeding it")

    print("rockpi4c PL330 contract: PASS")
    print("  silicon-proven SDMAC0 alias, identity/gates/readback and cache-off EL3 admission present")
    print("  SGRF and reset writes absent; normal-world/DMAC1 apertures unowned")
    print("  Radxa R1P0 and R0P0 encoders, secure GO, fault polling and bounded KILL present")
    print(f"  256-byte seed and doubling copies cap a full-HD clear at {dma_jobs} bounded jobs")


if __name__ == "__main__":
    main()
