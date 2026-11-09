"""ROM -> owned startup -> real ReadLine/parser -> shared storage commands."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
import zentaji_boot_image as B
import zentaji_exfat_oracle as E
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''
#CAP_TOUCH=0
#CAP_PWM=0
#CAP_NET=0
IncludeFile "Zentaji/Board/console.pbi"
IncludeFile "Anvil/Core/state.pbi"
IncludeFile "Anvil/Core/input_events.pbi"
IncludeFile "Anvil/Core/text_edit.pbi"
Global gBootTicks.i
IncludeFile "Anvil/Core/messages.pbi"
IncludeFile "Anvil/Core/parse.pbi"
IncludeFile "Anvil/Core/rxbreak.pbi"
#CAP_STORAGE=1
IncludeFile "Anvil/Kernel/Zentaji/boot_context.pbi"
IncludeFile "Anvil/Hal/hal.pbi"
IncludeFile "Anvil/Core/wallclock.pbi"
IncludeFile "Zentaji/Board/disk.pbi"
IncludeFile "Zentaji/Board/storage.pbi"
IncludeFile "Anvil/Core/format.pbi"
IncludeFile "Zentaji/Board/memory.pbi"
IncludeFile "Anvil/Core/memrange.pbi"
IncludeFile "Anvil/Core/addrsafe.pbi"
IncludeFile "Anvil/Core/settings.pbi"
IncludeFile "Anvil/Core/datapath.pbi"
IncludeFile "Anvil/Core/fs_cmd.pbi"
IncludeFile "Anvil/Core/command_loop.pbi"
Procedure.i HwCommandLoopHook(phase.i)
 If phase=#ACMD_AFTER_PROMPT : UartDrain() : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i HwCommandDispatch(c.i)
 ProcedureReturn DispatchStorageCommand()
EndProcedure
Global visits.i,ranges.i
Global Dim report.q[4]
Procedure.i RangeVisit(lba.i,blocks.i,context.i)
 ranges=ranges+1
 ProcedureReturn Bool(lba>=0 And blocks>0 And lba<=ZentajiDiskSectors()-blocks)
EndProcedure
Procedure.i EntryVisit(*name,depth.i,lba.i,bytes.i,attr.i,context.i)
 visits=visits+1
 ProcedureReturn 1
EndProcedure
Procedure.i Main(table.i,source.i,context.i)
 Protected stage.i,n.i,command.i
 If ZentajiMemoryBind(context)<>1 Or ZentajiStorageFromBoot(context,1)<>1 : ProcedureReturn 1 : EndIf
 PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$220,3) : PokeQ(#ZEN_IDLE_INTC+$228,1) : PokeQ(#ZEN_IDLE_INTC+$F008,514)
 If ZentajiPromptIdlePrepare(2000)<>1 Or UartInit(0)<>1 Or WallClockInit()<>1 Or WallClockSet(1794009600,#WALLCLOCK_SRC_MANUAL)<>1 : ProcedureReturn 2 : EndIf
 If AnvilPromptServicesPresent()<>0 Or AnvilPromptInputsPresent()<>0 Or AnvilPromptPumpPresent()<>0 : ProcedureReturn 8 : EndIf
 MessagesStart()
 stage=HwStageAddr()
 For n=0 To 1799 : PokeA(stage+n,(n*7+n/512+31)&255) : Next
 For command=0 To 5
  If AnvilCommandStep()<>1 : ProcedureReturn 3 : EndIf
  If command=1
   For n=0 To 1799 : PokeA(stage+n,0) : Next
  ElseIf command=2
   For n=0 To 1799
    If PeekA(stage+n)<>((n*7+n/512+31)&255) : ProcedureReturn 4 : EndIf
   Next
  EndIf
 Next
 If FsWalkRoot(@RangeVisit,0)<>0 Or FsLastError()<>#FS_E_ALLOCATION_UNSUPPORTED : ProcedureReturn 5 : EndIf
 If FsWalkAllocations(@EntryVisit,@RangeVisit,0)<>0 Or FsLastError()<>#FS_E_ALLOCATION_UNSUPPORTED Or visits<>0 Or ranges<>0 : ProcedureReturn 6 : EndIf
 report[0]=stage : report[1]=gHaveEntry : report[2]=gEntry : report[3]=HwMonBytes()
 If ZentajiStorageDown()<>1 Or ZentajiConsoleDrain()<>1 Or ZentajiPromptIdleRelease()<>1 : ProcedureReturn 7 : EndIf
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--zen-tools',type=Path,required=True)
    a=ap.parse_args();cc=resolve_compiler(a.compiler);zt=a.zen_tools.resolve();sys.path.insert(0,str(zt))
    import zentaji_native as I
    import zen_native_fixture as L
    import zasm_ref as A
    import zexpack
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-4500:],p.stderr)
        return p.stdout
    with I.NativeRunner() as runner, tempfile.TemporaryDirectory(prefix='anvil-zen-commands-') as tmp:
        td=Path(tmp);src=td/'probe.zentaji';image=td/'probe.zex';src.write_bytes(SOURCE.replace('\n','\r\n').encode())
        run([cc,'--compile',src,'-o',image])
        ref=A.Asm();origin,data=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
        assert image.read_bytes()==zexpack.header(origin,origin,data)+data
        wrapped,meta,_,_=B.pack(image.read_bytes(),zt/('zasm.exe' if os.name=='nt' else 'zasm'),source_map=json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig')))
        stage=(meta['image_end']+4095)&-4096
        boot=zexpack.disk_image(wrapped);assert len(boot)<=4096*512
        medium=E.build(4096);medium[:64]=boot[:64];medium[4096:len(boot)]=boot[4096:]
        commands=['mkdir Folder','save "Folder/Long file name.bin" %X 708'%stage,'load "Folder/Long file name.bin" %X'%stage,'ls Folder','cat "Folder/Missing.txt"','load "Folder/Long file name.bin" 1000']
        m=I.Fixture(ram_size=8<<20,cores=2,disks={15:(bytearray(medium),False)},display_modes=[(1,1,60000)]);m.power_on(1,15)
        assert not L.capture(m,str(td));cfg=td/'machine.txt';cfg.write_text(cfg.read_text().replace('disk-memory ','disk '),encoding='utf-8')
        scheduled=[]
        def operator(observed):
            core=observed.cores[0]
            # Observe only at complete slice boundaries. Choose a future tick
            # beyond that slice, so preloading the same schedule cannot change
            # any earlier instruction/device boundary in the native replay.
            if len(scheduled)>=len(commands):return
            if bytes(observed.serial[0].out).count(b'pmf> ')<=len(scheduled):return
            tick=max(observed.time,core.cr[I.CR['CYCLE']])+100
            line=commands[len(scheduled)]+'\r'
            scheduled.append([(tick,b) for b in line.encode()])
            m.serial[0].incoming.extend(scheduled[-1])
        m=runner.operate(m,operator,16000000,td);c=m.cores[0]
        cfg.write_text(cfg.read_text().replace('disk-memory ','disk '),encoding='utf-8')
        assert len(scheduled)==len(commands) and c.state=='HALTED' and c.r[1]==42,(c.state,c.r[1],bytes(m.serial[0].out)[-2000:])
        out=run([L.EXE,cfg,'--max','16000000','--ram',td/'final.bin'])
        assert ' exit=2A ' in out,('native failed',out[-2500:])
        assert (td/'final.bin').read_bytes()==m.ram
        I.assert_same_state(out,m)
        assert (td/'disk15.img').read_bytes()==bytes(m.disks[15].image)
        expected=bytes((n*7+n//512+31)&255 for n in range(1800))
        assert m.ram[stage:stage+1800]==expected
        assert struct.unpack_from('<4Q',m.ram,ref.sym['GLOBAL_REPORT'])==(stage,1,stage,meta['image_end']-meta['load'])
        for row in json.loads(Path(str(image)+'.zmap').read_text(encoding='utf-8-sig'))['code']:
            pc=int(row['pc'],16);size=row['size'];assert m.ram[pc:pc+size]==data[pc-origin:pc-origin+size],'monitor code overwritten'
        proof=E.check(bytes(m.disks[15].image),medium,expected)
        output=bytes(m.serial[0].out)
        for command in commands:assert ('pmf> '+command+'\r\n').encode() in output,(command,output[-2000:])
        for phrase in (b'Loaded 1800 bytes',b'Directory Folder on the boot medium:',b'1 file, 1800 bytes',b'could not be opened',b'run over',b'Nothing was loaded'):
            assert phrase in output,(phrase,output[-3000:])
        print('PASS ROM disk15 -> real ReadLine/parser/shared file commands: native full state/RAM, independent staged bytes, monitor-overwrite refusal, persisted image; '+proof,flush=True)


if __name__=='__main__':main()
