#!/usr/bin/env python3
"""Structural contract for the observation-only RK3399 Mali-T860 probe."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "RockPi4C/Lib/gpu_probe.pbi"


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def procedure(source: str, name: str) -> str:
    found = re.search(
        rf"(?ims)^Procedure(?:\.i)?\s+{re.escape(name)}\b.*?^EndProcedure\s*$",
        source,
    )
    need(found is not None, f"missing {name}")
    return found.group(0).lower()


def admits(values: dict[str, int | bool]) -> bool:
    return (
        bool(values["el3"]) and bool(values["cache_off"]) and
        bool(values["power_on"]) and bool(values["idle_released"]) and
        bool(values["pre_clock"]) and bool(values["leaf_clock"]) and
        0 <= int(values["parent"]) <= 4 and
        1 <= int(values["divider"]) <= 32 and bool(values["reset_clear"])
    )


def main() -> None:
    source = DRIVER.read_text(encoding="utf-8")
    lower = source.lower()
    board = (ROOT / "RockPi4C/Board/board.rockpi4c").read_text(encoding="utf-8")
    recovery_source = (ROOT / "RockPi4C/Lib/recovery.pbi").read_text(encoding="utf-8")
    recovery = recovery_source.lower()

    for token in (
        "rk3399-base.dtsi", "clk-rk3399.c", "pm-domains.c",
        "rk3399-cru.h", "panfrost_regs.h", "panfrost_gpu.c",
        "#rock_gpu_base = $ff9a0000", "#rock_gpu_product_t860 = $0860",
        "#rock_gpu_pmu_power_bit = 15", "#rock_gpu_pmu_idle_bit = 0",
        "#rock_gpu_softrst18_mask = $0007",
    ):
        need(token in lower, f"missing reference-backed token: {token}")

    capture = procedure(source, "RockGpuCaptureInfrastructure")
    reach = procedure(source, "RockGpuProbeReachability")
    probe = procedure(source, "RockGpuProbeReadOnly")
    job = procedure(source, "RockGpuProbeJobSlot")
    mmu = procedure(source, "RockGpuProbeAddressSpace")

    for forbidden in (
        "pokel(", "pokea(", "rockcruwrite(", "rockcrufield(",
        "rockcrugate(", "rockcrureset(", "rockpmupoweron(",
        "rockpmuidlerelease(",
    ):
        need(forbidden not in lower, f"read-only probe gained a write: {forbidden}")

    evidence = (
        "rock_gpu_pmu_pwrdn_con=", "rock_gpu_pmu_pwrdn_st=",
        "rock_gpu_pmu_idle_req=", "rock_gpu_pmu_idle_st=",
        "rock_gpu_pmu_idle_ack=", "rock_gpu_clksel13=",
        "rock_gpu_clkgate13=", "rock_gpu_clkgate30=",
        "rock_gpu_softrst18=", "rock_gpu_infrastructure_ready=1",
    )
    positions = [capture.find(token) for token in evidence]
    need(all(position >= 0 for position in positions) and positions == sorted(positions),
         "PMU/CRU evidence is not captured before readiness")
    for token in (
        "rock_current_el<>12", "(rock_sctlr_el3 & $1005)<>0",
        "#rock_gpu_error_power", "#rock_gpu_error_idle",
        "#rock_gpu_error_clock", "#rock_gpu_error_reset",
        "(rock_gpu_pmu_pwrdn_con & powermask)<>0",
        "(rock_gpu_pmu_pwrdn_st & powermask)<>0",
        "(rock_gpu_pmu_idle_req & idlemask)<>0",
        "(rock_gpu_pmu_idle_st & idlemask)<>0",
        "(rock_gpu_pmu_idle_ack & idlemask)<>0",
        "(rock_gpu_clkgate13 & premask)<>0",
        "(rock_gpu_clkgate30 & aclkmask)<>0",
        "(rock_gpu_softrst18 & #rock_gpu_softrst18_mask)<>0",
    ):
        need(token in capture, f"infrastructure admission lost: {token}")

    need(reach.find("rockgpucaptureinfrastructure()") <
         reach.find("rockgpuread(#rock_gpu_id)"),
         "GPU MMIO precedes infrastructure admission")
    minimal_reads = re.findall(r"rockgpuread\((#rock_gpu_[a-z0-9_]+)\)", reach)
    need(minimal_reads == [
        "#rock_gpu_id", "#rock_gpu_mmu_features", "#rock_gpu_as_present",
        "#rock_gpu_js_present", "#rock_gpu_status",
        "#rock_gpu_job_int_js_state", "#rock_gpu_mmu_int_stat",
    ], f"silicon-proven reachability read set/order changed: {minimal_reads}")
    for token in (
        "rock_gpu_product=(rock_gpu_id >> 16) & $ffff",
        "rock_gpu_product<>#rock_gpu_product_t860",
        "rock_gpu_as_present=0", "rock_gpu_js_present=0",
        "rock_gpu_mmu_va_bits=0", "rock_gpu_mmu_pa_bits=0",
        "rock_gpu_reachability_ready=1",
    ):
        need(token in reach, f"minimal identity/JM/MMU discovery lost: {token}")
    for token in (
        "rockgpuprobereachability()", "rock_gpu_shader_present=0",
        "rock_gpu_tiler_present=0", "rock_gpu_l2_present=0",
        "rock_gpu_probe_ready=1", "#rock_gpu_job_int_rawstat",
        "#rock_gpu_mmu_int_rawstat",
    ):
        need(token in probe, f"expanded read-only discovery lost: {token}")

    need("#rock_gpu_max_job_slots" in job and "rock_gpu_js_present" in job,
         "job-slot bounds or presence check missing")
    need("#rock_gpu_max_address_spaces" in mmu and "rock_gpu_as_present" in mmu,
         "address-space bounds or presence check missing")
    need("base=#rock_gpu_js_base+slot*#rock_gpu_js_stride" in job,
         "job-slot stride changed")
    need("base=#rock_gpu_mmu_base+(addressspace << #rock_gpu_mmu_as_shift)" in mmu,
         "MMU address-space stride changed")
    need(0x1800 + 15 * 0x80 + 0x58 < 0x2000, "job-slot oracle overlaps MMU")
    need(0x2400 + 15 * 0x40 + 0x28 < 0x10000, "MMU oracle exceeds aperture")

    baseline: dict[str, int | bool] = {
        "el3": True, "cache_off": True, "power_on": True,
        "idle_released": True, "pre_clock": True, "leaf_clock": True,
        "parent": 2, "divider": 3, "reset_clear": True,
    }
    need(admits(baseline), "valid infrastructure model refused")
    for field in ("el3", "cache_off", "power_on", "idle_released",
                  "pre_clock", "leaf_clock", "reset_clear"):
        need(not admits(baseline | {field: False}), f"{field} refusal not causal")
    for field, value in (("parent", 5), ("divider", 0), ("divider", 33)):
        need(not admits(baseline | {field: value}), f"{field} bound not causal")
    silicon_id = 0x08602000
    silicon_mmu = 0x00002830
    need((silicon_id >> 16) == 0x0860 and (silicon_id & 0xffff) == 0x2000,
         "recorded silicon GPU_ID no longer decodes as T860 revision 0x2000")
    need((silicon_mmu & 0xff) == 48 and ((silicon_mmu >> 8) & 0xff) == 40,
         "recorded silicon MMU_FEATURES no longer decodes as VA48/PA40")

    include = 'XIncludeFile "RockPi4C/Lib/gpu_probe.pbi"'
    need(include in board, "board does not compile the probe")
    need(board.index('XIncludeFile "RockPi4C/Lib/cru.pbi"') < board.index(include),
         "probe is before its CRU dependency")
    gpu_predicate = procedure(recovery_source, "RockRecoveryLineIsGpuInfo").lower()
    need("rock_recovery_length<>7" in gpu_predicate and
         all(f")={value}" in gpu_predicate
             for value in (103, 112, 117, 105, 110, 102, 111)),
         "gpuinfo predicate is not exact lowercase grammar")
    gpu_command = procedure(recovery_source, "RockRecoveryGpuInfo").lower()
    need("rockgpuprobereachability()" in gpu_command and
         "rockgpuprobereadonly()" not in gpu_command and
         "rockgpuprobejobslot" not in gpu_command and
         "rockgpuprobeaddressspace" not in gpu_command,
         "gpuinfo escaped the silicon-proven minimal read set")
    need(gpu_command.index("rockwatchdogarm()") <
         gpu_command.index("rockgpuprobereachability()") and
         "gpuinfo refused: deadman not armed" in gpu_command,
         "gpuinfo can reach MMIO before deadman admission")
    need("err gpuinfo disabled in fatal recovery" in recovery and
         "commands: help hdmi payload gpuinfo reboot" in recovery,
         "gpuinfo fatal/help grammar is missing")
    need("rockgpuprobereadonly" not in recovery and
         "rockgpuprobejobslot" not in recovery and
         "rockgpuprobeaddressspace" not in recovery,
         "recovery exposes expanded GPU reads or command submission state")
    need("rockgpuprobe" not in board[board.index("Procedure Main()") :].lower(),
         "boot executes the unproved probe")

    print("rockpi4c Mali-T860 read-only probe contract: PASS")
    print("  PMU/CRU admission precedes bounded GPU/JM/MMU reads")
    print("  gpuinfo is deadman-guarded and restricted to the silicon-proven reads")
    print("  no GPU/PMU/CRU/MMU/job hardware write or boot call is present")


if __name__ == "__main__":
    main()
