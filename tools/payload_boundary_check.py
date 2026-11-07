"""Prove payload argument cleanup and the selected ARM entry/return mechanism.

The gateway executes on Zentaji with a deterministic board adapter. The ARM
trampoline executes directly, with poisoned arguments, a payload destroying SP,
and success/failure recovery providers. No physical board is operated.
"""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]

GATEWAY = r'''
Global gGoX0.i
Global test_arg.i
Global test_entry.i
Global test_refuse.i
Procedure RunAt(a.i)
  test_entry = a
  test_arg = gGoX0
  If test_refuse <> 0
    ProcedureReturn
  EndIf
  gGoX0 = $55
EndProcedure
IncludeFile "Anvil/Kernel/AArch64/payload_gateway.pbi"
Procedure.i Main()
  HwPayloadRun($1000,$1122334455667788)
  If test_entry <> $1000 Or test_arg <> $1122334455667788 Or gGoX0 <> 0
    ProcedureReturn 1
  EndIf
  test_refuse = 1
  HwPayloadRun($2000,$123456789ABCDEF)
  If test_entry <> $2000 Or test_arg <> $123456789ABCDEF Or gGoX0 <> 0
    ProcedureReturn 2
  EndIf
  RunAt($3000)
  If test_arg <> 0
    ProcedureReturn 3
  EndIf
  gGoX0 = $BAD
  HwPayloadRun($4000,0)
  If test_arg <> 0 Or gGoX0 <> 0
    ProcedureReturn 4
  EndIf
  ProcedureReturn 42
EndProcedure
'''
ARM_PRELUDE = r'''
Global gGoAddr.i
Global gGoX0.i
Global gGoRc.i
Global gSp.i
Global test_recovery.i
'''
ARM_TAIL = r'''
Procedure.i HwPayloadReturned()
  ProcedureReturn test_recovery
EndProcedure
Procedure.i Main()
  ProcedureReturn PayloadEnter($1200000)
EndProcedure
'''


ENTER_PRELUDE = r'''
#PMF_FLAG_RETURNS = 1
#PMF_FLAG_WANTS_DTB = 2
#PMF_FLAG_WANTS_SERVICES = 4
#CAP_NET = 0
#SVC_ABI_MAJOR = 1
#SVC_ABI_MINOR = 4
#SVC_SLOT_COUNT = 184
Global gEntry.i, gHaveEntry.i, gPmfEntry.i, gPmfFlags.i, gSvcMayReturn.i
Global test_calls.i, test_arg.i, test_entry.i, test_screen.i, test_build.i, test_files.i
Global test_ge.i, test_gl.i, test_ie.i, test_il.i, test_gfail.i, test_ifail.i
Procedure GatePrint(*s) : EndProcedure
Procedure GatePrintN(*s) : EndProcedure
Procedure PrintDec(v.i) : EndProcedure
Procedure PrintNl() : EndProcedure
Procedure PutAddr(v.i) : EndProcedure
Procedure BuildServiceTable() : test_build=test_build+1 : EndProcedure
Procedure SvcFileHReset() : test_files=test_files+1 : EndProcedure
Procedure.i SvcTableAddr() : ProcedureReturn $1020304050607080 : EndProcedure
Procedure.i GraphicsServiceEnter()
  test_ge=test_ge+1
  ProcedureReturn test_gfail
EndProcedure
Procedure.i GraphicsServiceLeave() : test_gl=test_gl+1 : ProcedureReturn 0 : EndProcedure
Procedure.i InputServiceEnter()
  test_ie=test_ie+1
  ProcedureReturn test_ifail
EndProcedure
Procedure.i InputServiceLeave() : test_il=test_il+1 : ProcedureReturn 0 : EndProcedure
Procedure ScreenServiceTick() : test_screen=test_screen+1 : EndProcedure
Procedure HwPayloadRun(entry.i, argument.i)
  test_calls=test_calls+1
  test_arg=argument
  test_entry=entry
EndProcedure
Procedure TestReset()
  test_calls=0 : test_arg=-1 : test_entry=0 : test_screen=0 : test_build=0 : test_files=0
  test_ge=0 : test_gl=0 : test_ie=0 : test_il=0 : test_gfail=0 : test_ifail=0
EndProcedure
'''
ENTER_MAIN = r'''
Procedure.i Main()
  gPmfEntry=$123000
  TestReset()
  gPmfFlags=0
  PmfEnter()
  If test_calls<>1 Or test_arg<>0 Or test_entry<>gPmfEntry Or test_screen<>1 Or test_files<>0 Or gSvcMayReturn<>0
    ProcedureReturn 1
  EndIf
  TestReset()
  gPmfFlags=5
  PmfEnter()
  If test_calls<>1 Or test_arg<>$1020304050607080 Or test_files<>2 Or test_build<>1 Or gSvcMayReturn<>1
    ProcedureReturn 2
  EndIf
  If test_ge<>1 Or test_gl<>1 Or test_ie<>1 Or test_il<>1
    ProcedureReturn 3
  EndIf
  TestReset()
  test_gfail=-9
  PmfEnter()
  If test_calls<>0 Or test_screen<>0 Or test_ge<>1 Or test_gl<>0 Or test_ie<>0 Or test_files<>1
    ProcedureReturn 4
  EndIf
  TestReset()
  test_ifail=-8
  PmfEnter()
  If test_calls<>0 Or test_screen<>0 Or test_gl<>1 Or test_ie<>1 Or test_il<>0 Or test_files<>1
    ProcedureReturn 5
  EndIf
  TestReset()
  gPmfFlags=0
  PmfEnter()
  If test_calls<>1 Or test_arg<>0
    ProcedureReturn 6
  EndIf
  ProcedureReturn 42
EndProcedure
'''


def run(command,env):
    p=subprocess.run([str(x) for x in command],cwd=ROOT,env=env,
                     capture_output=True,text=True,timeout=60)
    assert p.returncode==0,p.stdout+p.stderr
    return p.stdout


def arm_probe():
    # Record the eight ABI argument registers, then destroy SP and return
    # a full-width value. Instruction words are independent of the compiler.
    words=[0xD2A00000|(0x100<<5)|9]
    words += [0xF9000000|(i<<10)|(9<<5)|i for i in range(8)]
    words += [0xD2800000|(0x1230<<5)|9,0x9100013F,
              0xD2800000|(0x7788<<5),0xF2A00000|(0x5566<<5),
              0xF2C00000|(0x3344<<5),0xF2E00000|(0x1122<<5),0xD65F03C0]
    return b''.join(struct.pack('<I',w) for w in words)


def execute_arm(image,recovery,expect_stop):
    sys.path.insert(0,str(ROOT/'tools/a64'))
    import pi5_desk as d
    from payload_entry_check import SysRegs,symbols,procs_of
    d.no_emulator_link.board('pi4')
    procs=procs_of(image,d.LOAD);sym=symbols(image)
    m=d.Machine(image,procs,lambda a,s,v:0)
    regs=SysRegs(12);m.step=regs.hook(m.cpu,m.step)
    def put(name,value):m.poke(sym[name],struct.pack('<Q',value))
    def get(name):return struct.unpack('<Q',m.peek(sym[name],8))[0]
    put('global_test_recovery',recovery)
    argument=0x1020304050607080
    put('global_ggox0',argument)
    m.poke(0x1200000,arm_probe())
    c=m.cpu;c.pc=procs['payloadenter'];c.sp=m.stack;c.x[30]=d.RETURN
    c.x[0]=0x1200000
    for i in range(1,19):c.x[i]=0xBAD00000+i
    callbacks=[]
    for _ in range(2000):
        if c.pc==d.RETURN:break
        if c.pc==procs['hwpayloadreturned']:
            callbacks.append((c.sp,regs.regs[SysRegs.DAIF]))
        m.step()
    assert len(callbacks)==1,callbacks
    assert callbacks[0]==(get('global_gsp'),0x3C0),callbacks
    captured=struct.unpack('<8Q',m.peek(0x1000000,64))
    assert captured==(argument,0,0,0,0,0,0,0),captured
    assert get('global_ggorc')==0x1122334455667788
    if expect_stop:
        assert c.pc!=d.RETURN,'unsafe recovery returned to the monitor'
        assert regs.regs[SysRegs.DAIF]==0x3C0,'unsafe recovery unmasked interrupts'
        assert SysRegs.DAIF not in regs.writes,'unsafe recovery restored old DAIF'
        assert c.sp==get('global_gsp'),'failure park lost monitor SP'
        # The bounded observation must end in the actual two-instruction park.
        at=c.fetch(c.pc)
        assert at==0xD503205F or at&0xFC000000==0x14000000,hex(at)
    else:
        assert c.pc==d.RETURN,'successful recovery did not return'
        assert c.sp==m.stack and regs.regs[SysRegs.DAIF]==0
        assert get('global_ggox0')==0,'returned payload argument survived'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler');ap.add_argument('--zenemu',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler)
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    with tempfile.TemporaryDirectory(prefix='anvil-payload-boundary-') as tmp:
        td=Path(tmp);src=td/'gateway.zentaji';image=td/'gateway.zex'
        src.write_text(GATEWAY,encoding='utf-8')
        run([cc,'--compile',src,'-o',image],env)
        cfg=td/'machine.txt';cfg.write_text('machine $100000 1 1000 0\nimage '+image.as_posix()+'\n')
        out=run([a.zenemu.resolve(),cfg,'--max','1000000'],env)
        assert 'exit=2A ' in out,out
        print('PASS actual payload gateway on Zentaji: full-width argument, normal/refused cleanup, next plain run, zero argument')
        core=(ROOT/'Anvil/Kernel/AArch64/payload_call.pbi').read_text(encoding='utf-8')
        def build(text,name):
            src=td/(name+'.pi4');img=td/(name+'.img')
            src.write_text(ARM_PRELUDE+text+ARM_TAIL,encoding='utf-8')
            run([cc,'--compile',src,'-t','pi4','--entry-returns',
                 '--load-addr','0x400000','--stack-addr','0x3000000','-o',img],env)
            return img
        # Execute the exact common handoff policy with controlled device owners.
        import re
        from pmfboot_v2_reader_check import procedure
        enter=procedure((ROOT/'Anvil/Core/pmfboot.pbi').read_text(encoding='utf-8'),'PmfEnter')
        assert 'gGoX0' not in enter and '  RunAt(' not in enter
        enter=re.sub(r'\bPrintN\b','GatePrintN',enter)
        enter=re.sub(r'\bPrint\b','GatePrint',enter)
        src=td/'common.pi4';common=td/'common.img'
        src.write_text(ENTER_PRELUDE+enter+ENTER_MAIN,encoding='utf-8')
        run([cc,'--compile',src,'-t','pi4','--entry-returns',
             '--load-addr','0x400000','--stack-addr','0x3000000','-o',common],env)
        sys.path.insert(0,str(ROOT/'tools/a64'))
        import pi5_desk as d
        from payload_entry_check import procs_of
        d.no_emulator_link.board('pi4')
        m=d.Machine(common,procs_of(common,d.LOAD),lambda a,s,v:0)
        assert m.call('Main')==42,'common handoff owner/argument/refusal checks failed'
        print('PASS exact common PmfEnter: zero/table argument, return flag, owner preparation/cleanup and refusals')
        image=build(core,'arm')
        execute_arm(image,1,False);execute_arm(image,0,True)
        # Restore the old bug in a private copy: failure must no longer pass.
        mutant=build(core.replace('If HwPayloadReturned() = 0','If HwPayloadReturned() = -999',1),'mutant')
        try:execute_arm(mutant,0,True)
        except AssertionError as exc:
            assert 'unsafe recovery' in str(exc),exc
        else:raise AssertionError('ignored-recovery mutant survived')
        print('PASS actual ARM trampoline: argument registers, 64-bit result, destroyed-SP recovery, masked recovery callback, failure park; old-bug mutant killed')
    return 0


if __name__=='__main__':raise SystemExit(main())
