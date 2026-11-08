"""Shared command-loop lifecycle and parser policy on real Zentaji UART/WFI."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_commands_check as C
ROOT=Path(__file__).resolve().parents[1]
SOURCE=C.SOURCE.split('#CAP_STORAGE=1')[0]+r'''
IncludeFile "Anvil/Hal/hal.pbi"
IncludeFile "Anvil/Core/format.pbi"
IncludeFile "Zentaji/Board/memory.pbi"
IncludeFile "Anvil/Core/addrsafe.pbi"
IncludeFile "Anvil/Core/command_loop.pbi"
Global scenario.i,completed.i,dispatched.i,probes.i,phaseCount.i
Global Dim phases.a[80]
Global Dim report.q[12]
Procedure.i HwCommandLoopHook(phase.i)
 phases[phaseCount]=phase : phaseCount=phaseCount+1
 If scenario=1 And phase=#ACMD_BEFORE_PROMPT : ProcedureReturn 0 : EndIf
 If scenario=2 And phase=#ACMD_AFTER_INPUT : ProcedureReturn 0 : EndIf
 If phase=#ACMD_AFTER_COMMAND
  completed=completed+1
  If completed=11 : ProcedureReturn 0 : EndIf
 EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i HwCommandDispatch(c.i)
 dispatched=dispatched+1
 If WordIs("force")<>0
  CmdForce()
 ElseIf WordIs("probe")<>0
  report[probes*3]=gMemWidth
  report[probes*3+1]=AddrForceArmedFor($1234)
  report[probes*3+2]=gWordLen
  probes=probes+1
 Else
  ProcedureReturn 0
 EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i Main(which.i)
 scenario=which
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(2000)<>1 Or UartInit(0)<>1 : ProcedureReturn 1 : EndIf
 MessagesStart()
 If scenario<>0 : gMemWidth=77 : gForceOn=1 : gForceAt=$1234 : gForceAge=0 : EndIf
 AnvilCommandLoop()
 If scenario=0
  If completed<>11 Or probes<>4 Or dispatched<>8 Or phaseCount<>55 : ProcedureReturn 2 : EndIf
 ElseIf scenario=1
  If dispatched<>0 Or phaseCount<>1 Or UartReadReady()<>1 Or UartRead()<>88 Or gMemWidth<>77 Or gForceAge<>0 : ProcedureReturn 3 : EndIf
 Else
  If dispatched<>0 Or phaseCount<>4 Or completed<>0 Or gMemWidth<>77 Or gForceAge<>0 : ProcedureReturn 4 : EndIf
 EndIf
 If ZentajiConsoleDrain()<>1 Or ZentajiPromptIdleRelease()<>1 : ProcedureReturn 5 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zen_interp as I
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-3500:],p.stderr)
        return p.stdout
    commands=['force 1234','probe.B','probe','measure probe.W','measure','measure measure probe','nonesuch','','probe.l','probe.bx','abcdefghijklmnopqrstuvwxyz123456']
    with tempfile.TemporaryDirectory(prefix='anvil-command-loop-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex';src.write_bytes(SOURCE.replace('\n','\r\n').encode());run([cc,'--compile',src,'-o',image])
        ref=A.Asm();origin,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(origin,origin,data)+data
        for scenario in (0,1,2):
            m=I.Machine(ram_size=1<<20,display_modes=[(1,1,60000)]);m.load_image(image.read_bytes());m.cores[0].r[1]=scenario;m.cores[0].r[255]=0xf0000
            incoming='\r'.join(commands)+'\r' if scenario==0 else ('X' if scenario==1 else 'probe.B\r')
            m.serial[0].incoming=[(0,b) for b in incoming.encode()]
            assert not L.capture(m,str(td));out=run([L.EXE,td/'machine.txt','--max','4000000','--ram',td/'final.bin']);assert ' exit=2A ' in out,(scenario,out[-1800:])
            m.run(4000000);c=m.cores[0];assert c.state=='HALTED' and c.r[1]==42,(scenario,c.state,c.r[1])
            assert (td/'final.bin').read_bytes()==m.ram
            state=next(s[6:] for s in out.splitlines() if s.startswith('STATE '));assert state.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
            output=bytes(m.serial[0].out)
            if scenario==0:
                expected=[1,1,5,0,0,5,2,0,5,4,0,5]
                assert list(struct.unpack_from('<12Q',m.ram,ref.sym['GLOBAL_REPORT']))==expected
                at=ref.sym['GLOBAL_PHASES'];assert m.ram[at:at+55]==bytes([1,2,3,4,5]*11)
                assert output.count(b'pmf> ')==11
                for phrase in (b'measure:',b'measure needs a command',b'measure cannot measure itself',b'? this monitor does not know the command nonesuch,',b'? this monitor does not know the command probe.bx,',b'? this monitor does not know the command abcdefghijklmnopqrstuvwx,'):
                    assert phrase in output,(phrase,output[-2000:])
            elif scenario==1:assert output==b''
            else:assert output==b'pmf> probe.B\r\n'
            print('PASS shared command loop case%d: suffix/reset/force aging, measure/refusal/unknown and hook order/stop boundaries; native/twin state/RAM/exact expected fields/output'%scenario,flush=True)


if __name__=='__main__':main()
