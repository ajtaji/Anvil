#!/usr/bin/env python3
"""Check display admission/commit order, emitted fail-stop control flow and the
one cold 1024x768 fallback after a failed native (host-trained) attempt.

The MMIO/mailbox owners are mocked, not the production facade. This proves
ordering and failure propagation, not physical display timing or visibility.
"""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
# One attempt of the cold-to-visible chain. RockDisplayUp runs it natively
# (host link training), and after a failure at or past link training runs it
# ONCE more from the CRU resets as the fallback: established 1024x768 mode,
# firmware training on the cold PHY, SET_VIDEO idle/valid.
COLD = [
    "rockcrudisplayprepare", "rockcrucadencerelease",
    "rockcdnfirmwareload", "rockcdnfirmwareactive", "rockcdnenableevents",
    "rocktcphyup", "rockcdnhotplug", "rockcdnhostcapabilities",
    "rockcdndpcd", "rockcdnreadedid",
]
COMMIT = [
    "rockcdnplanvideo", "rockvopmodevalid", "rockcruvpllmode", "rockvoppreparemode",
    "rockcdnvideomode",
]
PLANE = [
    "rockvopconfigureprimary", "rockvopstartprimary", "rockcdnreadlivelinkstatus",
]
TRACED = set(COLD + COMMIT + PLANE) | {
    "rockcdntrainlink", "rockcdntrain", "rockmodefallback", "rockmodeselect",
    "rockdisplayframetelemetry", "rockdisplaystopscanout",
}
PHASES = COLD + ["rockcdntrainlink", "video-idle"] + COMMIT + ["video-valid"] + PLANE + [
    "rockdisplayframetelemetry"]


def expected_run(fail, native_fw, valid_link, mode_fallback_ok=True):
    """The designed control flow: returns (trace, result, fallback_used)."""
    counts = {}
    trace = []

    def call(phase):
        counts[phase] = counts.get(phase, 0) + 1
        trace.append(phase)
        if phase == "rockmodefallback" and not mode_fallback_ok:
            return False
        return counts[phase] not in fail.get(phase, ())

    def attempt(native):
        for phase in COLD:
            if not call(phase):
                return False, False
        if native:
            if not call("rockcdntrainlink"):
                return False, True
            fw = native_fw
        else:
            if not call("rockmodefallback"):
                if not call("rockmodeselect"):
                    return False, True
            if not call("rockcdntrain"):
                return False, True
            fw = True
        if fw and not call("video-idle"):
            return False, True
        for phase in COMMIT:
            if not call(phase):
                return False, True
        if fw and not call("video-valid"):
            return False, True
        for phase in PLANE:
            if not call(phase):
                return False, True
        if not valid_link:
            return False, True
        if not call("rockdisplayframetelemetry"):
            return False, True
        return True, True

    done, reached = attempt(True)
    if done:
        return trace, 1, 0
    if not reached:
        return trace, 0, 0
    call("rockdisplaystopscanout")
    done, _ = attempt(False)
    return trace, int(done), 1


def source_contract():
    display = (ROOT / "RockPi4C/Lib/display.pbi").read_text().lower()
    cdn = (ROOT / "RockPi4C/Lib/cdn_dp.pbi").read_text().lower()
    vop = (ROOT / "RockPi4C/Lib/vop.pbi").read_text().lower()
    body = display.split("procedure.i rockdisplayupattempt(native.i)", 1)[1].split("endprocedure", 1)[0]
    publication_clear = ["rock_display_ready=0", "rock_display_width=0",
                         "rock_display_height=0", "rock_display_pitch=0",
                         "rock_display_buffer=0"]
    clear_offsets = [body.index(token) for token in publication_clear]
    assert clear_offsets == sorted(clear_offsets)
    assert max(clear_offsets) < body.index("rockdisplaystage(")
    ordered = ["configured = rockcdnplanvideo()", "if rockvopmodevalid()=0", "if rockcruvpllmode()=0",
               "if rockvoppreparemode()=0", "if rockcdnvideomode()=0",
               "if rockcdnvideostatus(1)=0", "if rockvopconfigureprimary()=0",
               "if rockvopstartprimary()=0", "if rockdisplayframetelemetry()=0",
               "rock_display_ready=1"]
    offsets = [body.index(token) for token in ordered]
    assert offsets == sorted(offsets), "CRTC/encoder/plane commit order differs"
    assert '"dp08 visible ' not in body, "software cannot certify physical visibility"
    wrapper = display.split("procedure.i rockdisplayup()", 1)[1].split("endprocedure", 1)[0]
    assert wrapper.count("rockdisplayupattempt(") == 2, "exactly one fallback attempt"
    tokens = ("rockdisplayupattempt(1)", "rock_display_link_reached=0",
              "rockdisplaystopscanout()", "rockdisplayupattempt(0)")
    for token in tokens:
        assert token in wrapper, f"RockDisplayUp is missing {token}"
    marks = [wrapper.index(token) for token in tokens]
    assert marks == sorted(marks), "native, link-stage test, WIN0 stop, fallback"
    plan = cdn.split("procedure.i rockcdnplanvideo()", 1)[1].split("endprocedure", 1)[0]
    for forbidden in ("rockcdnregwrite", "rockcdnsend", "rockcdnwrite", "pokel", "pokea"):
        assert forbidden not in plan, "mode admission must not write hardware"
    video = cdn.split("procedure.i rockcdnvideomode()", 1)[1].split("endprocedure", 1)[0]
    assert video.index("if rockcdnplanvideo()=0") < video.index("rockcdnregwrite")
    sample = display.split("procedure.i rockdisplayframetelemetry()", 1)[1].split("endprocedure", 1)[0]
    assert "procedurereturn bool(frames=9 and faults=0)" in sample
    lane_mask = display.split("procedure.i rockdisplaylinklanemask()", 1)[1].split("endprocedure", 1)[0]
    assert "case 1 : procedurereturn $07" in lane_mask
    assert "case 2 : procedurereturn $77" in lane_mask
    assert "procedurereturn 0" in lane_mask
    assert "linklanemask=rockdisplaylinklanemask()" in body
    assert "if linklanemask=0 or (rock_cdn_live_link_status[0] & linklanemask)<>linklanemask" in body
    configure = vop.split("procedure.i rockvopconfigureprimary()", 1)[1].split("endprocedure", 1)[0]
    start = vop.split("procedure.i rockvopstartprimary()", 1)[1].split("endprocedure", 1)[0]
    assert configure.index("rock_vop_configured=0") < configure.index("rock_vop_prepared=0")
    assert start.index("rock_vop_ready=0") < start.index("rock_vop_prepared=0 or rock_vop_configured=0")


def emitted_contract(image):
    spec = importlib.util.spec_from_file_location("rock_display_lifecycle_a64", ROOT / "tools/a64/a64_interp.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    symbols = {}
    for line in Path(str(image) + ".sym").read_text().splitlines():
        name, value = line.split("=", 1)
        symbols[name.lower()] = int(value)
    load, returned = 0x00041000, 0x06000000
    names = {load + offset: name for name, offset in symbols.items()
             if not name.startswith(("global_", "__", "_l"))}
    blob = image.read_bytes()
    memory = {load + index: value for index, value in enumerate(blob)}
    passive = {"rockcdnwrite", "rockcdninternalclocks", "rocktimerwaitus"}
    # RockDisplayLinkLaneMask is pure logic under test, not an MMIO owner.
    # Mocking it with the other rockdisplay* telemetry returned 1 for every
    # lane count, so the invalid-lane cases could never fail as asserted.
    not_mocked = ("rockdisplayup", "rockdisplayupattempt", "rockdisplayfail",
                  "rockdisplaylinklanemask")
    cases = 0

    def run(fail=None, bad_alignment=False, lanes=2, lane_status=None,
            stale_publication=False, native_fw=0, mode_fallback_ok=True):
        nonlocal cases
        fail = fail or {}
        cpu = module.A64()
        cpu.memory.update(memory)
        for name, value in {"rock_mode_width": 1920, "rock_mode_height": 1080,
                            "rock_mode_pitch": 7680, "rock_cdn_error": 34,
                            "rock_cdn_link_lanes": lanes,
                            "rock_cdn_use_fw_training": native_fw}.items():
            cpu.raw_store(symbols["global_" + name], value, 8)
        if stale_publication:
            for name, value in {"rock_display_ready": 1,
                                "rock_display_width": 1024,
                                "rock_display_height": 768,
                                "rock_display_pitch": 4096,
                                "rock_display_buffer": 0x02965000}.items():
                cpu.raw_store(symbols["global_" + name], value, 8)
        status = symbols["global_rock_cdn_live_link_status"]
        if lane_status is None:
            lane_status = 0x07 if lanes == 1 else 0x77
        cpu.raw_store(status, lane_status, 1)
        cpu.raw_store(status + 2, 0 if bad_alignment else 1, 1)
        cpu.sp, cpu.x[30] = 0x05000000, returned
        cpu.pc = load + symbols["rockdisplayup"]
        counts = {}
        trace = []
        for _ in range(200000):
            if cpu.pc == returned:
                break
            name = names.get(cpu.pc, "")
            phase = name
            if name == "rockcdnvideostatus":
                phase = "video-valid" if cpu.x[0] else "video-idle"
            if phase in TRACED or phase in ("video-idle", "video-valid"):
                trace.append(phase)
                counts[phase] = counts.get(phase, 0) + 1
                ok = counts[phase] not in fail.get(phase, ())
                if phase == "rockmodefallback" and not mode_fallback_ok:
                    ok = False
                cpu.x[0] = int(ok)
                cpu.pc = cpu.x[30]
            elif name == "rockvopframebuffer":
                cpu.x[0], cpu.pc = 0x02965000, cpu.x[30]
            elif (name in passive or name.startswith("rockuart") or
                  (name.startswith("rockdisplay") and name not in not_mocked)):
                cpu.x[0], cpu.pc = 1, cpu.x[30]
            else:
                cpu.step()
        else:
            raise AssertionError("display facade did not return")
        valid_link = (lanes in (1, 2) and not bad_alignment and
                      (lane_status & (0x07 if lanes == 1 else 0x77)) == (0x07 if lanes == 1 else 0x77))
        want, result, fallback = expected_run(fail, native_fw, valid_link, mode_fallback_ok)
        ready = cpu.raw_load(symbols["global_rock_display_ready"], 8)
        used = cpu.raw_load(symbols["global_rock_display_fallback_used"], 8)
        native_error = cpu.raw_load(symbols["global_rock_display_native_error"], 8)
        assert trace == want, (fail, native_fw, lanes, lane_status, bad_alignment, valid_link, trace, want)
        assert cpu.x[0] == result and ready == result, (fail, cpu.x[0], ready, result)
        assert used == fallback, (fail, used, fallback)
        assert (native_error != 0) == bool(fallback), (fail, native_error, fallback)
        if fallback:
            # WIN0 stops before the second cold prepare holds the VOPL resets.
            second_prepare = [i for i, p in enumerate(trace) if p == "rockcrudisplayprepare"][1]
            assert trace.index("rockdisplaystopscanout") < second_prepare
        if stale_publication:
            for name in ("rock_display_width", "rock_display_height",
                         "rock_display_pitch", "rock_display_buffer"):
                assert cpu.raw_load(symbols["global_" + name], 8) == 0, name
        cases += 1
        return fallback, result

    # Native success, host-trained and firmware-trained (inside RockCdnTrainLink).
    assert run() == (0, 1)
    assert run(native_fw=1) == (0, 1)
    assert run(lanes=1) == (0, 1)
    # Every phase failing once: a cold failure stops; a link-stage failure is
    # recovered by the fallback and ends with a picture.
    recovered = 0
    for native_fw in (0, 1):
        for phase in PHASES:
            if phase in ("video-idle", "video-valid") and not native_fw:
                continue
            fallback, result = run(fail={phase: {1}}, native_fw=native_fw)
            if phase in COLD:
                assert (fallback, result) == (0, 0), phase
            else:
                assert (fallback, result) == (1, 1), phase
                recovered += 1
    # A link-stage phase failing in BOTH attempts ends with no picture and no
    # third attempt; a cold phase failing only in the fallback also stops.
    for phase in COMMIT + PLANE + ["rockdisplayframetelemetry"]:
        assert run(fail={phase: {1, 2}}) == (1, 0), phase
    assert run(fail={"video-idle": {1, 2}}, native_fw=1) == (1, 0)
    assert run(fail={"rockcdntrainlink": {1}, "rockcdntrain": {1}}) == (1, 0)
    for phase in COLD:
        assert run(fail={"rockcdnplanvideo": {1}, phase: {2}}) == (1, 0), phase
    # The fallback keeps the EDID mode when 1024x768 is not advertised.
    assert run(fail={"rockvopstartprimary": {1}}, mode_fallback_ok=False) == (1, 1)
    assert run(fail={"rockvopstartprimary": {1}, "rockmodeselect": {1}},
               mode_fallback_ok=False) == (1, 0)
    # Link validation failures (lanes, alignment) fall back and fail again.
    assert run(lanes=1, lane_status=0) == (1, 0)
    assert run(lanes=0) == (1, 0)
    assert run(lanes=3) == (1, 0)
    assert run(bad_alignment=True) == (1, 0)
    run(fail={COLD[0]: {1}}, stale_publication=True)
    print(f"Emitted lifecycle: {cases} runs; {recovered} single link-stage failures recovered "
          f"by the cold 1024x768 fallback; cold failures stop; double failures stop after one retry")


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
