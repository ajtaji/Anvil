#!/usr/bin/env python3
"""Check display admission/commit order and emitted fail-stop control flow.

The MMIO/mailbox owners are mocked, not the production facade. This proves
ordering and failure propagation, not physical display timing or visibility.
"""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PHASES = [
    "rockcrudisplayprepare", "rockcrucadencerelease",
    "rockcdnfirmwareload", "rockcdnfirmwareactive", "rockcdnenableevents",
    "rocktcphyup", "rockcdnhotplug", "rockcdnhostcapabilities",
    "rockcdndpcd", "rockcdnreadedid", "rockcdntrain", "video-idle",
    "rockcdnplanvideo", "rockvopmodevalid", "rockcruvpllmode", "rockvoppreparemode",
    "rockcdnvideomode", "video-valid", "rockvopconfigureprimary",
    "rockvopstartprimary", "rockcdnreadlivelinkstatus",
    "rockdisplayframetelemetry",
]


def source_contract():
    display = (ROOT / "RockPi4C/Lib/display.pbi").read_text().lower()
    cdn = (ROOT / "RockPi4C/Lib/cdn_dp.pbi").read_text().lower()
    body = display.split("procedure.i rockdisplayup()", 1)[1].split("endprocedure", 1)[0]
    ordered = ["configured = rockcdnplanvideo()", "if rockvopmodevalid()=0", "if rockcruvpllmode()=0",
               "if rockvoppreparemode()=0", "if rockcdnvideomode()=0",
               "if rockcdnvideostatus(1)=0", "if rockvopconfigureprimary()=0",
               "if rockvopstartprimary()=0", "if rockdisplayframetelemetry()=0",
               "rock_display_ready=1"]
    offsets = [body.index(token) for token in ordered]
    assert offsets == sorted(offsets), "CRTC/encoder/plane commit order differs"
    assert '"dp08 visible ' not in body, "software cannot certify physical visibility"
    plan = cdn.split("procedure.i rockcdnplanvideo()", 1)[1].split("endprocedure", 1)[0]
    for forbidden in ("rockcdnregwrite", "rockcdnsend", "rockcdnwrite", "pokel", "pokea"):
        assert forbidden not in plan, "mode admission must not write hardware"
    video = cdn.split("procedure.i rockcdnvideomode()", 1)[1].split("endprocedure", 1)[0]
    assert video.index("if rockcdnplanvideo()=0") < video.index("rockcdnregwrite")
    sample = display.split("procedure.i rockdisplayframetelemetry()", 1)[1].split("endprocedure", 1)[0]
    assert "procedurereturn bool(frames=9 and faults=0)" in sample


def emitted_contract(image):
    spec = importlib.util.spec_from_file_location("rock_display_lifecycle_a64", ROOT / "tools/a64/a64_interp.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    symbols = {}
    for line in Path(str(image) + ".sym").read_text().splitlines():
        name, value = line.split("=", 1)
        symbols[name.lower()] = int(value)
    load, returned = 0x02000040, 0x06000000
    names = {load + offset: name for name, offset in symbols.items()
             if not name.startswith(("global_", "__", "_l"))}
    blob = image.read_bytes()
    memory = {load + index: value for index, value in enumerate(blob)}
    passive = {"rockcdnwrite", "rockcdninternalclocks", "rocktimerwaitus"}
    phase_names = set(PHASES) - {"video-idle", "video-valid"}

    def run(failure=None, bad_alignment=False):
        cpu = module.A64()
        cpu.memory.update(memory)
        for name, value in {"rock_mode_width": 1920, "rock_mode_height": 1080,
                            "rock_mode_pitch": 7680, "rock_cdn_error": 34}.items():
            cpu.raw_store(symbols["global_" + name], value, 8)
        status = symbols["global_rock_cdn_live_link_status"]
        cpu.raw_store(status, 0x77, 1)
        cpu.raw_store(status + 2, 0 if bad_alignment else 1, 1)
        cpu.sp, cpu.x[30] = 0x05000000, returned
        cpu.pc = load + symbols["rockdisplayup"]
        trace = []
        for _ in range(100000):
            if cpu.pc == returned:
                break
            name = names.get(cpu.pc, "")
            phase = name
            if name == "rockcdnvideostatus":
                phase = "video-valid" if cpu.x[0] else "video-idle"
            if phase in phase_names or phase in ("video-idle", "video-valid"):
                trace.append(phase)
                cpu.x[0] = int(phase != failure)
                cpu.pc = cpu.x[30]
            elif name == "rockvopframebuffer":
                cpu.x[0], cpu.pc = 0x02965000, cpu.x[30]
            elif name in passive or (name.startswith("rockdisplay") and
                    name not in ("rockdisplayup", "rockdisplayfail")) or name.startswith("rockuart"):
                cpu.x[0], cpu.pc = 1, cpu.x[30]
            else:
                cpu.step()
        else:
            raise AssertionError("display facade did not return")
        ready = cpu.raw_load(symbols["global_rock_display_ready"], 8)
        if failure is None and not bad_alignment:
            assert cpu.x[0] == 1 and ready == 1 and trace == PHASES, trace
        else:
            assert cpu.x[0] == 0 and ready == 0, (failure, trace, ready)
            expected = PHASES[:PHASES.index(failure) + 1] if failure else PHASES[:-1]
            assert trace == expected, (failure, trace, expected)

    run()
    for failure in PHASES:
        run(failure)
    run(bad_alignment=True)
    print(f"Emitted lifecycle: success, {len(PHASES)} owner failures and bad link alignment passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path)
    args = parser.parse_args()
    source_contract()
    if args.image:
        emitted_contract(args.image)
    print("Display lifecycle gate passed; physical display not tested")


if __name__ == "__main__":
    main()
