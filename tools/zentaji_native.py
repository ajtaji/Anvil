"""Data-only Anvil fixtures and observations from the real ASM Zentaji core."""
from dataclasses import dataclass
from pathlib import Path
import subprocess
import zen_native_fixture as F
import opcodes as Z
from zen_native_device_probe import NativeDeviceProbe

DEV=Z.DEVICE_BASE
EXE=F.EXE
CR=F.CR
C=F.C
M64=F.M64
BIP=F.BIP
IE=1
U=2
capture=F.capture

class Fixture(F.Fixture):
    def __init__(self,*args,**kwargs):
        kwargs.setdefault('seed',0)
        super().__init__(*args,**kwargs)

@dataclass(frozen=True)
class DiskSnapshot:
    image:bytes
    fields:tuple

    def __getattr__(self,name):
        names=('busy','held','phase','ctrl','irq_enable','irq_status','sq_base','sq_n','sq_tail','sq_head','cq_base','cq_n','cq_head','cq_tail')
        if name not in names:raise AttributeError(name)
        return self.fields[names.index(name)]

@dataclass(frozen=True)
class Observation:
    result:F.NativeResult
    fields:dict
    disks:dict
    rtc_reads:tuple
    hostfiles:tuple
    rtc_nano_reads:tuple
    frames:tuple
    read_witness:tuple

    def __getattr__(self,name):
        return getattr(self.result,name)


def assert_same_state(native,observed):
    """Compare two native executions; semantic expectations belong in each gate."""
    def state(output):
        line=next(s for s in output.splitlines() if s.startswith('STATE '))
        return line[6:].split(' ',1)[1]
    assert state(native)==state(observed.output),(native[-2500:],observed.output[-2500:])

class NativeRunner(NativeDeviceProbe):
    def execute(self,fixture,budget,folder,ram_stop=None):
        folder=Path(folder)
        config=fixture.write(folder)
        return self.execute_config(config,budget,folder,read_witness=getattr(fixture,'read_witness',None),ram_stop=ram_stop)

    def execute_config(self,config,budget,folder,read_witness=None,ram_stop=None):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        media=folder/'observed-media';media.mkdir(exist_ok=True)
        rtc=folder/'observed-rtc.txt';frames=folder/'observed-frames.txt'
        witness=None
        if read_witness is not None:
            low,high,addresses=read_witness;witness=folder/'read-witness.txt'
            witness.write_text(' '.join('$%X'%value for value in (low,high,*addresses))+'\n',encoding='ascii')
        stop=None
        if ram_stop is not None:
            stop=folder/'ram-stop.txt'
            values=ram_stop[:4] if len(ram_stop)>3 else ram_stop
            stop.write_text(' '.join('$%X'%v for v in values)+'\n'+(ram_stop[4] if len(ram_stop)>4 else '')+'\n',encoding='ascii')
        native=super().execute(config,budget,folder,ram_stop=stop,read_witness=witness,inspect_vectors=True,media_dumps=media,rtc_log=rtc,frame_log=frames)
        disks={int(name[4:]):DiskSnapshot((media/('observed-disk'+name[4:]+'.img')).read_bytes(),tuple(fields))
               for name,fields in native.fields.items() if name.startswith('disk')}
        reads=tuple(int(line,16) for line in rtc.read_text().splitlines() if not line.startswith('NANO '))
        nanos=tuple(int(line[5:],16) for line in rtc.read_text().splitlines() if line.startswith('NANO '))
        files=tuple(((media/('observed-hf%d.name'%i)).read_text(encoding='utf-8'),
                     (media/('observed-hf%d.bin'%i)).read_bytes(),bool(fields[0]))
                    for i,fields in sorted((int(name[6:]),fields) for name,fields in native.fields.items() if name.startswith('hfmeta')))
        return Observation(native.result,native.fields,disks,reads,files,nanos,tuple(frames.read_text().splitlines()),tuple(tuple(int(word,16) for word in line.split()) for line in Path(str(witness)+'.log').read_text().splitlines()) if witness else ())

    def debug_snapshot(self,fixture,commands,folder):
        """Inspect an actual native breakpoint, with no Python execution callback."""
        folder=Path(folder);config=fixture.write(folder)
        script=folder/'boundary-debug.txt';ram=folder/'boundary-ram.bin'
        inspection=[]
        for core in range(len(fixture.cores)):
            inspection.extend('vector %d %d'%(core,n) for n in range(64))
            inspection.extend(('masks %d'%core,'controls %d'%core,'counters %d'%core))
        script.write_text('\n'.join(list(commands)+inspection)+'\n',encoding='utf-8')
        p=subprocess.run([str(EXE),str(config),'--debug',str(script),'--dump','--ram',str(ram)],
                         capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        if p.returncode or 'error:' in p.stdout.lower():raise RuntimeError(p.stdout+p.stderr)
        return F.parse_result(p.stdout,ram.read_bytes())

    def operate(self,fixture,operator,budget,folder):
        """Schedule input from actual native prefix observations, then replay fully.

        Each prefix starts from the original input and media. The callback may
        append future input data; it cannot execute instructions or devices.
        """
        total=0;increment=fixture.slice_len
        marker=getattr(fixture,'observe_ram',None)
        previous=int.from_bytes(fixture.ram[marker:marker+8],'little') if marker is not None else None
        token=getattr(fixture,'observe_serial',None);occurrences=0
        while total<budget:
            if marker is not None:
                stop=(marker,previous,total,occurrences,token) if token else (marker,previous,total)
                observed=self.execute(fixture,budget,folder,ram_stop=stop)
                if observed.steps<=total:break
                total=observed.steps
                previous=int.from_bytes(observed.ram[marker:marker+8],'little')
                if token:occurrences=observed.serial[0].out.count(token.encode('ascii'))
            else:
                total=min(budget,total+increment)
                observed=self.execute(fixture,total,folder)
            if all(core.state in ('HALTED','PARKED') for core in observed.cores):break
            before=(len(fixture.directives),tuple(len(port.incoming) for port in fixture.serial))
            operator(observed)
            after=(len(fixture.directives),tuple(len(port.incoming) for port in fixture.serial))
            increment=fixture.slice_len if before!=after else min(increment*2,getattr(fixture,'operator_stride',1000000))
        # Use the full acceptance budget, exactly as the shipped CLI will do.
        final=self.execute(fixture,budget,folder)
        fixture.write(folder)
        return final
