"""Prompt registration and real unbound ReadLine/live idle on Zentaji."""
import argparse
from collections import deque
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_commands_check as C
ROOT=Path(__file__).resolve().parents[1]
UNIT=r'''
IncludeFile "Anvil/Core/prompt_services.pbi"
Global works.i,inputs.i,claims.i,pumps.i
Procedure.i InputProvider(operation.i)
 inputs=inputs+1
 If AnvilPromptInputsBind(0)<>0 Or AnvilPromptServicesBind(0)<>0 Or AnvilPromptPumpBind(0)<>0 : ProcedureReturn -99 : EndIf
 If operation=#APS_KEYBOARD : ProcedureReturn 65 : EndIf
 If operation=#APS_NET_INPUT : ProcedureReturn 3 : EndIf
 claims=claims+1 : ProcedureReturn 0
EndProcedure
Procedure.i WorkProvider(operation.i)
 works=works+1
 If AnvilPromptServicesBind(0)<>0 Or AnvilPromptInputsBind(0)<>0 Or AnvilPromptPumpBind(0)<>0 : ProcedureReturn -99 : EndIf
 ProcedureReturn AnvilPromptInput(#APS_KEYBOARD)
EndProcedure
Procedure.i PumpProvider(operation.i)
 pumps=pumps+1
 If AnvilPromptServicesBind(0)<>0 Or AnvilPromptInputsBind(0)<>0 Or AnvilPromptPumpBind(0)<>0 : ProcedureReturn -99 : EndIf
 ProcedureReturn AnvilPromptInput(#APS_NET_INPUT)
EndProcedure
Procedure.i Main()
 Protected op.i
 If AnvilPromptServicesPresent()<>0 Or AnvilPromptInputsPresent()<>0 : ProcedureReturn 1 : EndIf
 For op=1 To 15
  If op=#APS_NET_INPUT
   If AnvilPromptInput(op)<>-1 : ProcedureReturn 2 : EndIf
  ElseIf op=#APS_NET_PUMP
   If AnvilPromptPump()<>0 : ProcedureReturn 13 : EndIf
  ElseIf op=#APS_KEYBOARD Or op=#APS_CLAIM_LOCAL
   If AnvilPromptInput(op)<>0 : ProcedureReturn 3 : EndIf
  Else
   If AnvilPromptService(op)<>0 : ProcedureReturn 4 : EndIf
  EndIf
 Next
 If AnvilPromptService(0)<>-2 Or AnvilPromptServicesLastError()<>#APS_ERR_OPERATION : ProcedureReturn 5 : EndIf
 If AnvilPromptService(#APS_KEYBOARD)<>-2 Or AnvilPromptInput(#APS_SCREEN)<>-2 : ProcedureReturn 6 : EndIf
 If AnvilPromptServicesBind(@WorkProvider)<>1 Or AnvilPromptInputsBind(@InputProvider)<>1 : ProcedureReturn 7 : EndIf
 If AnvilPromptService(#APS_SCREEN)<>65 Or works<>1 Or inputs<>1 Or AnvilPromptServicesLastError()<>#APS_ERR_ACTIVE : ProcedureReturn 8 : EndIf
 If AnvilPromptServicesPresent()<>1 Or AnvilPromptInputsPresent()<>1 : ProcedureReturn 9 : EndIf
 If AnvilPromptInput(#APS_NET_INPUT)<>3 Or AnvilPromptInput(#APS_CLAIM_LOCAL)<>0 Or claims<>1 Or inputs<>3 : ProcedureReturn 10 : EndIf
 If AnvilPromptServicesBind(0)<>1 Or AnvilPromptService(#APS_SCREEN)<>0 Or works<>1 Or AnvilPromptInputsPresent()<>1 : ProcedureReturn 11 : EndIf
 If AnvilPromptPumpBind(@PumpProvider)<>1 Or AnvilPromptPump()<>3 Or pumps<>1 Or inputs<>4 : ProcedureReturn 14 : EndIf
 If AnvilPromptPumpBind(0)<>1 Or AnvilPromptPump()<>0 Or pumps<>1 Or AnvilPromptPumpPresent()<>0 : ProcedureReturn 15 : EndIf
 If AnvilPromptInputsBind(0)<>1 Or AnvilPromptInput(#APS_NET_INPUT)<>-1 Or inputs<>4 : ProcedureReturn 12 : EndIf
 ProcedureReturn 42
EndProcedure
'''
LIVE=C.SOURCE.split('#CAP_STORAGE=1')[0]+r'''
Procedure.i Main(scenario.i)
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(2000)<>1 Or UartInit(0)<>1 : ProcedureReturn 1 : EndIf
 If AnvilPromptServicesPresent()<>0 Or AnvilPromptInputsPresent()<>0 Or AnvilPromptPumpPresent()<>0 Or *wifiMaintenanceProvider<>0 Or *gMsgLineHook<>0 : ProcedureReturn 2 : EndIf
 MessagesStart()
 Print("pmf> ") : ReadLine()
 If gLineLen<>2 Or gLine[0]<>79 Or gLine[1]<>75 : ProcedureReturn 3 : EndIf
 If scenario=21 And AnvilCpuUsagePercent()<0 : ProcedureReturn 4 : EndIf
 UartMessageBegin() : PrintN("unbound file notification") : UartMessageEnd()
 If MessagesTotal()<>1 Or gMsgKept<>1 Or UartMessageLost()<>0 : ProcedureReturn 5 : EndIf
 If ZentajiConsoleDrain()<>1 Or ZentajiPromptIdleRelease()<>1 : ProcedureReturn 6 : EndIf
 ProcedureReturn 42
EndProcedure
'''

CANCEL=C.SOURCE.split('#CAP_STORAGE=1')[0]+r'''
Procedure.i Main(scenario.i)
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$F008,2)
 If ZentajiPromptIdlePrepare(2000)<>1 Or UartInit(0)<>1 : ProcedureReturn 1 : EndIf
 OutBreakArm()
 If OutBreak()<>1 Or OutBroke()<>1 Or OutBreak()<>1 Or UartRead()<>89 : ProcedureReturn 2 : EndIf
 OutBreakArm()
 If OutBreakCtrlC()<>0 Or OutBroke()<>0 Or OutBreakCtrlC()<>1 Or OutBreakCtrlC()<>1 Or UartRead()<>90 : ProcedureReturn 3 : EndIf
 OutBreakArm()
 If OutBreak()<>0 Or UartReadReady()<>0 : ProcedureReturn 4 : EndIf
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
    import zen_sleep_check as S
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4000:],p.stderr)
        return p.stdout
    def states(out):return [s for s in out.splitlines() if s.startswith('STATE ')]
    with tempfile.TemporaryDirectory(prefix='anvil-zen-prompt-services-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex'
        for name,source in [('registration',UNIT),('cancel',CANCEL),('unbound-live',LIVE)]:
            src.write_bytes(source.replace('\n','\r\n').encode());run([cc,'--compile',src,'-o',image])
            ref=A.Asm();origin,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
            assert image.read_bytes()==zexpack.header(origin,origin,data)+data
            def machine(scenario):
                m=I.Machine(ram_size=1<<20,display_modes=[(1,1,60000)]);m.load_image(image.read_bytes());m.cores[0].r[1]=scenario;m.cores[0].r[255]=0xf0000
                if name=='cancel':m.serial[0].incoming=[(0,b) for b in b'XYa\x03Z']
                if name=='unbound-live':m.serial[0].incoming=[(200000000 if scenario==21 else 0,b) for b in b'OK\r']
                return m
            def match(m,out):
                c=m.cores[0];assert c.state=='HALTED' and c.r[1]==42,(name,c.state,c.r[1])
                assert (td/'final.bin').read_bytes()==m.ram
                assert states(out)[0][6:].split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
            if name=='registration':
                m=machine(0);assert not L.capture(m,str(td));out=run([L.EXE,td/'machine.txt','--max','100000','--ram',td/'final.bin']);m.run(100000);match(m,out)
                print('PASS registration: absent defaults, bound routing, work-to-input calls, active rebinding refusal, independent unregister and invalid operations; native/twin state/RAM',flush=True)
                continue
            if name=='cancel':
                m=machine(0);assert not L.capture(m,str(td));out=run([L.EXE,td/'machine.txt','--max','100000','--ram',td/'final.bin']);m.run(100000);match(m,out)
                assert bytes(m.serial[0].out)==(b'Stopped, because a key was pressed. What is printed above this line is\r\n'
                    b'only part of the answer, not all of it. Run the command again to see\r\n'
                    b'the whole of it.\r\n')
                print('PASS real UART cancellation: any-byte and Ctrl-C, sticky abort without extra byte consumption, rearm and exact output; native/twin state/RAM',flush=True)
                continue
            # No test Mouse/Screen/Network/Fan providers exist in this image.
            for label in ('ZPROC_MOUSETICK','ZPROC_SCREENSERVICETICK','ZPROC_NETCONSOLEGETC','ZPROC_FANTICK'):
                assert label.replace(' ','') not in ref.sym,label
            results=[]
            for scenario in (20,21):
                m=machine(scenario);assert not L.capture(m,str(td));rec=td/('recorded%d.txt'%scenario)
                live,wall,cpu=S.run([str(zt/('zenwin.exe' if os.name=='nt' else 'zenwin')),str(td/'machine.txt'),'--headless','--live','--mute','--record',str(rec),'--max','4000000'],timeout=30)
                out=run([L.EXE,rec,'--max','4000000','--ram',td/'final.bin']);assert states(live)==states(out)
                m.clock_samples=deque((int(s.split()[1][1:],16),int(s.split()[2]),int(s.split()[3]) if len(s.split())>3 else -1) for s in rec.read_text().splitlines() if s.startswith(('clock ','work ')))
                m.clock_complete=True;m.run(4000000);match(m,out)
                assert bytes(m.serial[0].out)==b'pmf> OK\r\n'
                results.append((wall,cpu))
            wall=results[1][0]-results[0][0];cpu=max(0,results[1][1]-results[0][1]);assert wall>=1.8 and cpu<0.4,(wall,cpu)
            print('PASS unbound real ReadLine live: startup-adjusted wall=%.6fs CPU=%.6fs; no optional providers/test adapters, real timer/WFI, message log with no file hook and exact recorded native/twin replay'%(wall,cpu),flush=True)


if __name__=='__main__':main()
