"""Compile and execute shared prompt policy on the non-ARM Zentaji ISA.

The test adapters provide deterministic time and service events; this is not a
Zentaji Anvil boot proof or a hardware wake qualification.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
from pmf_compiler import resolve_compiler
from prompt_services_fixture import LANE_BINDING

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = '''; Execute shared scheduler policy with deterministic hardware/service adapters.
; No CPU instruction is replaced inside the shared implementation.
Global test_now.q = 100
Global test_ready.i = 1
Global test_uart.i = 0
Global test_queued.i = 0
Global test_pwm.i = 0
Global test_waits.i = 0
Global test_calls.i = 0
Global test_boardcalls.i = 0
Global test_fired.q = 0

Procedure.q Ticks()
  ProcedureReturn test_now
EndProcedure
Procedure.q TickHz()
  ProcedureReturn 1000
EndProcedure
Procedure.i HwPromptIdleReady()
  ProcedureReturn test_ready
EndProcedure
Procedure HwPromptIdleWait()
  test_waits = test_waits + 1
  test_now = test_now + 250
EndProcedure
Procedure.i UartReadReady()
  ProcedureReturn test_uart
EndProcedure
Procedure.i InputEventsQueued()
  ProcedureReturn test_queued
EndProcedure
Procedure.i HwPwmKind()
  ProcedureReturn test_pwm
EndProcedure
#HW_PWM_KIND_SOFT = 1
#CAP_TOUCH = 1
#CAP_NET = 1
#CAP_PWM = 1
Procedure UartMessageBegin()
  test_fired = test_fired | 1
  test_calls = test_calls + 1
EndProcedure
Procedure UartMessageEnd()
  test_fired = test_fired | 2
  test_calls = test_calls + 1
EndProcedure
Procedure MouseTick()
  test_fired = test_fired | 4
  test_calls = test_calls + 1
EndProcedure
Procedure TouchTick()
  test_fired = test_fired | 8
  test_calls = test_calls + 1
EndProcedure
Procedure TouchKeyboardServiceTick()
  test_fired = test_fired | 16
  test_calls = test_calls + 1
EndProcedure
Procedure ScreenServiceTick()
  test_fired = test_fired | 32
  test_calls = test_calls + 1
EndProcedure
Procedure WifiMaintenanceTick()
  test_fired = test_fired | 64
  test_calls = test_calls + 1
EndProcedure
Procedure NetDhcpTick()
  test_fired = test_fired | 128
  test_calls = test_calls + 1
EndProcedure
Procedure NtpServiceTick()
  test_fired = test_fired | 256
  test_calls = test_calls + 1
EndProcedure
Procedure FanTick()
  test_fired = test_fired | 512
  test_calls = test_calls + 1
EndProcedure
Procedure HwTempSampleTick()
  test_fired = test_fired | 1024
  test_calls = test_calls + 1
EndProcedure
Procedure NetConsoleRearm()
  test_fired = test_fired | 2048
  test_calls = test_calls + 1
EndProcedure
Procedure NetConsolePump()
  test_fired = test_fired | 4096
  test_calls = test_calls + 1
EndProcedure
Procedure NetConsoleLlTick()
  test_fired = test_fired | 8192
  test_calls = test_calls + 1
EndProcedure
Procedure HttpServerPoll()
  test_fired = test_fired | 16384
  test_calls = test_calls + 1
EndProcedure
Procedure TcpTick()
  test_fired = test_fired | 32768
  test_calls = test_calls + 1
EndProcedure

Procedure HwPromptBoardService()
  test_boardcalls = test_boardcalls + 1
EndProcedure

XIncludeFile "Anvil/Core/prompt_scheduler.pbi"

Procedure.i Main()
  Define n.i
  If AnvilCpuUsagePercent() <> -1 Or AnvilCpuUsageHundredths() <> -1
    ProcedureReturn 1
  EndIf
  AnvilSchedulerIdleIfSafe()
  If test_waits <> 1 Or anvil_promptIdleTicks <> 250
    ProcedureReturn 2
  EndIf
  test_ready = 0
  AnvilSchedulerIdleIfSafe()
  test_ready = 1
  test_uart = 1
  AnvilSchedulerIdleIfSafe()
  test_uart = 0
  test_queued = 1
  AnvilSchedulerIdleIfSafe()
  test_queued = 0
  test_pwm = #HW_PWM_KIND_SOFT
  AnvilSchedulerIdleIfSafe()
  test_pwm = 0
  If test_waits <> 1
    ProcedureReturn 3
  EndIf
  test_now = 1100
  AnvilSchedulerAccount()
  If AnvilCpuUsagePercent() <> 75 Or AnvilCpuUsageHundredths() <> 7500
    ProcedureReturn 4
  EndIf
  If anvil_promptIdleTicks <> 0
    ProcedureReturn 5
  EndIf
  ; Five lanes: 3+1+3+2+4 service calls, plus two message brackets each.
  For n = 1 To 5
    AnvilPromptServiceOne()
  Next
  If anvil_promptServiceSlot <> 0 Or test_calls <> 23 Or test_fired <> 32767 Or test_boardcalls <> 1
    ProcedureReturn 6
  EndIf
  ; Clamp idle accounting to elapsed time rather than report negative busy.
  test_now = 2100
  anvil_promptIdleTicks = 2000
  AnvilSchedulerAccount()
  If AnvilCpuUsagePercent() <> 0 Or AnvilCpuUsageHundredths() <> 0
    ProcedureReturn 7
  EndIf
  ; Tick accounting must not truncate when a clock crosses 32 bits.
  test_now = $100000100
  anvil_promptWindowStart = test_now - 1000
  anvil_promptIdleTicks = 100
  AnvilSchedulerAccount()
  If AnvilCpuUsagePercent() <> 90 Or AnvilCpuUsageHundredths() <> 9000
    ProcedureReturn 8
  EndIf
  ProcedureReturn 42
EndProcedure
'''

FIXTURE=FIXTURE.replace('Procedure.i Main()',LANE_BINDING+'Procedure.i Main()\n AnvilPromptServicesBind(@TestPromptServices) : AnvilPromptPumpBind(@TestPromptPump)')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler')
    ap.add_argument('--zenemu', type=Path, required=True)
    a = ap.parse_args()
    # Guard this exact shared path against reintroducing ISA mechanisms.
    import re
    for name in ('Anvil/Core/parse.pbi', 'Anvil/Core/prompt_scheduler.pbi'):
        text = (ROOT / name).read_text(encoding='utf-8')
        assert not re.search(r'^\s*(?:Asm|EndAsm)\b|#PMF_CHIP|MmuEl\(', text, re.M | re.I), name
    compiler = resolve_compiler(a.compiler)
    env = dict(os.environ, PMF_ROOT=str(ROOT))
    with tempfile.TemporaryDirectory(prefix='anvil-prompt-policy-') as tmp:
        td = Path(tmp)
        src, image = td / 'policy.zentaji', td / 'policy.zex'
        src.write_text(FIXTURE, encoding='utf-8')
        p = subprocess.run([str(compiler), '--compile', str(src), '-o', str(image)],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        assert p.returncode == 0 and image.is_file(), p.stdout + p.stderr
        cfg = td / 'machine.txt'
        cfg.write_text('machine $100000 1 1000 0\nimage ' + image.as_posix() + '\n')
        p = subprocess.run([str(a.zenemu.resolve()), str(cfg), '--max', '1000000'],
                           capture_output=True, text=True, timeout=15)
        assert p.returncode == 0 and 'exit=2A ' in p.stdout, p.stdout + p.stderr
        # Compile the same policy for an existing ARM target, and separately
        # compile the real ARM backend. No ARM emulator or board is started.
        arm_src, arm_image = td / 'policy.pi4', td / 'policy.img'
        arm_src.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
        p = subprocess.run([str(compiler), '--compile', str(arm_src), '-t', 'pi4',
                            '--entry-returns', '-o', str(arm_image)], cwd=ROOT,
                           env=env, capture_output=True, text=True, timeout=60)
        assert p.returncode == 0 and arm_image.is_file(), p.stdout + p.stderr
        arm_src.write_text(
            'Procedure.i HwIdEl()\nProcedureReturn 3\nEndProcedure\n'
            'Procedure.q Ticks()\nProcedureReturn 0\nEndProcedure\n'
            'Procedure.q TickHz()\nProcedureReturn 54000000\nEndProcedure\n'
            'IncludeFile "Anvil/Kernel/AArch64/prompt_idle.pbi"\n'
            'Procedure.i Main()\nHwPromptIdleWait()\nProcedureReturn AnvilSchedulerProbeWfe()\nEndProcedure\n',
            encoding='utf-8')
        p = subprocess.run([str(compiler), '--compile', str(arm_src), '-t', 'pi4',
                            '--entry-returns', '-o', str(arm_image)], cwd=ROOT,
                           env=env, capture_output=True, text=True, timeout=60)
        assert p.returncode == 0 and arm_image.is_file(), p.stdout + p.stderr
        assert bytes.fromhex('5f2003d5') in arm_image.read_bytes(), 'ARM backend lost WFE'
    print('PASS shared scheduler on Zentaji: readiness/input/software-PWM admission, '
          'bounded wait accounting, five service lanes, utilization clamps and 64-bit clock; '
          'ARM policy/backend compile (no hardware execution)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
