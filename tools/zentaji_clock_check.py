"""Real Zentaji RTC and shared clock slots; independent calendar/native twin proof."""
import argparse
import datetime
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''#CAP_RTC=CAPABILITY
XIncludeFile "Zentaji/Board/console.pbi"
XIncludeFile "Anvil/Hal/hal.pbi"
XIncludeFile "Anvil/Hal/service_errors.pbi"
XIncludeFile "Anvil/Core/wallclock.pbi"
XIncludeFile "Zentaji/Board/rtc_clock.pbi"
Global gSvcDetail.i
Global Dim report.q[9]
Global Dim buffer.a[40]
CLOCK_SLOTS
Procedure.q Main(deadline.q,sample.q,nanos.q,format.i)
 Protected i.i
 If ZentajiClockSampleValid(315532800,0)<>1 Or ZentajiClockSampleValid(4102444799,999999999)<>1 : ProcedureReturn 1 : EndIf
 If ZentajiClockSampleValid(315532799,0)<>0 Or ZentajiClockSampleValid(4102444800,0)<>0 Or ZentajiClockSampleValid(-1,0)<>0 : ProcedureReturn 2 : EndIf
 If ZentajiClockSampleValid(1767225600,-1)<>0 Or ZentajiClockSampleValid(1767225600,1000000000)<>0 : ProcedureReturn 3 : EndIf
 If deadline>0
  PokeQ(#ZEN_IDLE_INTC+$120,3) : PokeQ(#ZEN_IDLE_INTC+$220,3)
  PokeQ(#ZEN_IDLE_INTC+$228,1) : PokeQ(#ZEN_IDLE_INTC+$F008,514)
  PokeQ(#ZEN_IDLE_TIMER,deadline) : PokeQ(#ZEN_IDLE_TIMER+$10,3)
  ZenCpuWait()
  PokeQ(#ZEN_IDLE_TIMER+$10,0) : PokeQ(#ZEN_IDLE_TIMER+$18,1)
 EndIf
 If WallClockInit()<>1 Or WallClockSet(1794009600,#WALLCLOCK_SRC_RESTORED)<>1 : ProcedureReturn 4 : EndIf
 CompilerIf #CAP_RTC=1
 report[0]=ZentajiClockSeed()
 CompilerEndIf
 report[1]=WallClockSource()
 If WallClockSet(1800000000,#WALLCLOCK_SRC_MANUAL)<>1 Or WallClockSetZone(19800)<>1 : ProcedureReturn 5 : EndIf
 report[2]=SvcClockProvenance() : report[3]=SvcUtc(0)
 report[4]=SvcClockUncertaintyMs() : report[5]=SvcUtcLastSyncTicks()
 For i=0 To 39 : buffer[i]=$A5 : Next
 report[6]=SvcUtc(@buffer[4]) : report[8]=-1
 If format<>0 : report[8]=ZentajiClockRecord(@buffer[4],sample,nanos) : EndIf
 report[7]=WallClockSource()
 ProcedureReturn 42
EndProcedure
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');ap.add_argument('--case');ap.add_argument('--zen-tools',type=Path,required=True);a=ap.parse_args()
    cc=resolve_compiler(a.compiler);sys.path.insert(0,str(a.zen_tools.resolve()))
    import zen_interp as I
    import zen_devices as D
    import zen_lockstep_check as L
    import zasm_ref as A
    import zexpack
    assert D.EPOCH==1767225600 and D.TIME_HZ==100000000
    abi=(ROOT/'Anvil/Hal/abi.pbi').read_text(encoding='utf-8')
    names=('SvcClockProv','SvcTicks','SvcUtc','SvcClockProvenance','SvcClockUncertaintyMs','SvcUtcLastSyncTicks')
    slots=[]
    for name in names:
        m=re.search(r'^Procedure\.i '+name+r'\(.*?^EndProcedure',abi,re.M|re.S);assert m,name;slots.append(m.group())
    slots='\n'.join(slots)
    assert '#PMF_CHIP' not in slots
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    def run(args):
        p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        assert p.returncode==0,(p.returncode,p.stdout[-3000:],p.stderr)
        return p.stdout
    checked=0
    with tempfile.TemporaryDirectory(prefix='anvil-rtc-') as tmp:
        td=Path(tmp);src=td/'clock.zentaji';image=td/'clock.zex'
        for capability in (1,0):
            src.write_text(SOURCE.replace('CAPABILITY',str(capability)).replace('CLOCK_SLOTS',slots),encoding='utf-8')
            run([cc,'--compile',src,'-o',image])
            ref=A.Asm();org,body=ref.assemble(Path(str(image)+'.asm').read_text(encoding='utf-8-sig'))
            assert image.read_bytes()==zexpack.header(org,org,body)+body
            samples=[('initial',0,0,0,0),('second-edge',100000000-20,0,0,0)]
            for name,epoch,nanos in [('epoch-floor',315532800,0),('leap-day',1835395200,987654321),('century-leap',951782400,123456789),('range-edge',4102444799,999999999),('before-floor',315532799,0),('out-of-range',4102444800,0),('negative-nanos',1767225600,-1),('nanos-overflow',1767225600,1000000000)]:
                samples.append((name,0,epoch,nanos,1))
            if not capability:samples=[('no-provider',0,0,0,0)]
            for name,deadline,epoch,nanos,formatter in samples:
                if a.case and a.case not in name:continue
                m=I.Machine(ram_size=1<<20,cores=2,display_modes=[(1,1,60000)]);m.load_image(image.read_bytes())
                for index,value in enumerate((deadline,epoch,nanos,formatter),1):m.cores[0].r[index]=value&((1<<64)-1)
                m.ram[:32]=bytes([204])*32
                assert not L.capture(m,str(td))
                reads=[];nano_reads=[];original=m.rtc.rd
                def observe(core,reg):
                    if reg==0x40:reads.append(m.time_now())
                    if reg==0x48:nano_reads.append(m.time_now())
                    return original(core,reg)
                m.rtc.rd=observe;m.run(2000000);c=m.cores[0]
                assert c.state=='HALTED' and c.exit==42,(name,c.state,c.exit)
                assert m.ram[:32]==bytes([204])*32,'null output wrote address zero'
                if name=='second-edge':
                    gap=nano_reads[-1]-reads[-1];assert gap>0
                    samples.append(('second-edge-latched',100000000-(reads[-1]-deadline)-max(1,gap//2),0,0,0))
                if name=='second-edge-latched':assert reads[-1]<100000000<=nano_reads[-1],(reads,nano_reads)
                got=struct.unpack_from('<9q',m.ram,ref.sym['GLOBAL_REPORT'])
                raw=bytes(m.ram[ref.sym['GLOBAL_BUFFER']:ref.sym['GLOBAL_BUFFER']+40])
                assert raw[:4]==bytes([165])*4 and raw[32:]==bytes([165])*8
                assert got[0:2]==((1,4) if capability else (0,2)),(name,got)
                assert got[2:8]==(2 if capability else 0,-102,-1,-1,2 if capability else 0,1),(name,got)
                assert len(reads)==(3 if capability else 0)
                if formatter:
                    available=315532800<=epoch<4102444800 and 0<=nanos<1000000000
                    assert got[8]==int(available),(name,got)
                    milliseconds=nanos//1000000
                else:
                    available=bool(capability);assert got[8]==-1
                    if available:
                        tick=reads[-1];epoch=D.EPOCH+tick//D.TIME_HZ;milliseconds=(tick%D.TIME_HZ)*1000//D.TIME_HZ
                if available:
                    dt=datetime.datetime.fromtimestamp(epoch,datetime.timezone.utc)
                    expected=(dt.year,dt.month,dt.day,dt.hour,dt.minute,dt.second,milliseconds)
                    assert struct.unpack('<7i',raw[4:32])==expected,(name,struct.unpack('<7i',raw[4:32]),expected)
                else:assert raw[4:32]==bytes(28),(name,raw)
                assert m.rtc.alarm==m.rtc.alarm_ctrl==m.rtc.alarm_status==0 and m.rtc.nvram==bytes(256)
                out=run([L.EXE,td/'machine.txt','--max','2000000','--ram',td/'final.bin'])
                assert (td/'final.bin').read_bytes()==m.ram
                state=next(line[6:] for line in out.splitlines() if line.startswith('STATE '));assert state.split(' ',1)[1]==L.state_line(m,0,-1).split(' ',1)[1]
                assert m.cores[1].state=='PARKED'
                checked+=1
                print('PASS RTC '+name+': '+('production snapshot formatter' if formatter else 'actual hardware/shared clock slots')+', independent UTC/subseconds, bounds/guards/manual separation and full native/twin state/RAM',flush=True)

    assert checked,'no RTC case matched'


if __name__=='__main__':main()
