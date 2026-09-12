"""Execute a counted updater candidate's diagnostic orchestration; no hardware.

Underlying native MMIO and enumeration have independent emitted gates. Here
those boundaries are controlled to prove command admission, argument ownership,
bounded orchestration, DMA shutdown/quarantine and updater command preservation.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'a64'))
import a64_core_worker_check as base

def main():
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);a=p.parse_args()
    image=Path(a.image);blob=image.read_bytes();sym=base.parse_symbols(image)
    m=base.load_interp(base.INTERP);load=0x200000
    def run(case,command=None,extension=True):
        c=m.A64();c.memory={load+i:b for i,b in enumerate(blob)};c.sp=0x1f00000
        def put(name,value):c.store(sym['global_'+name],value,8)
        put('pi3_ut_command_extension',load+sym['pi3usbdiagcommand'] if extension else load+sym['pi3nocommandextension'])
        if case=='repeat':put('p3diag_used',1)
        if case=='quarantine-command':put('pi3_ut_rx_quarantine',1)
        output=[];calls=[];dma=0;ticks=0
        hooks=('pi3uartwrite','pi3usbhostinit','pi3usbrootportreset','pi3usbnativecontext',
               'pi3updateresetready','pi3usbread','pi3usbwrite','pi3usbtime',
               'pi3usbenumerationbegin','pi3usbenumerationstep')
        addresses={load+sym[n]:n for n in hooks}
        if command is not None:
            ptr=sym['global_pi3_ut_line']
            for i,b in enumerate(command.encode()+b'\0'):c.store(ptr+i,b,1)
            put('pi3_ut_line_len',len(command));c.pc=load+sym['pi3ut_command']
        else:c.pc=load+sym['pi3usbdiagnostic']
        c.x[30]=base.RETURN_PC
        for steps in range(500000):
            if c.pc==base.RETURN_PC:break
            h=addresses.get(c.pc)
            if h is None:c.step();continue
            calls.append(h);r=1
            if h=='pi3uartwrite':output.append(c.x[0]&255)
            elif h=='pi3usbnativecontext':r=0 if case=='context' else 1
            elif h=='pi3updateresetready':r=0 if case=='unconfirmed' else 1
            elif h=='pi3usbhostinit':
                r=0 if case=='init' else 1
                if r:put('p3usb_native_power',1)
            elif h=='pi3usbrootportreset':r=0 if case=='reset' else 1
            elif h=='pi3usbread':r={8:dma,0x440:0x1005,0x500:0x80000000 if case=='owned' else 0}.get(c.x[0],0)
            elif h=='pi3usbwrite':
                assert c.x[0]==8,'orchestrator wrote unrelated register'
                dma=c.x[1]
            elif h=='pi3usbtime':ticks+=100000;r=ticks
            elif h=='pi3usbenumerationbegin':
                assert c.x[0]==0x503 and c.x[1]==0
                assert c.x[2]|0xc0000000==c.x[3]
                assert c.x[4]|0xc0000000==c.x[5]
                assert 0x1100000<=c.x[2]<0x1e00000 and c.x[6]==512
            elif h=='pi3usbenumerationstep':r=-31 if case=='enum' else (3 if case=='deadline' else 4)
            c.x[0]=r&((1<<64)-1);c.pc=c.x[30]
        else:raise AssertionError('unbounded '+case)
        text=bytes(output).decode('ascii')
        if command is None:
            assert c.x[0]==(1 if case=='ok' else 0),(case,c.x[0],text)
        if case in ('context','unconfirmed','repeat','quarantine-command') or (command is not None and (command!='usbdiag' or not extension)):
            assert 'pi3usbhostinit' not in calls,(case,text)
        if case in ('ok','enum','deadline'):assert dma==0,(case,dma)
        if case=='owned':assert dma==0x20 and 'quarantined' in text
        if case=='deadline':assert calls.count('pi3usbenumerationstep')<151
        return text
    for case in ('ok','context','unconfirmed','repeat','init','reset','enum','deadline','owned'):run(case)
    assert 'USB descriptors accepted' in run('ok','usbdiag')
    assert 'unknown command' in run('junk','usbdiag junk')
    assert 'update begin' in run('help','help')
    assert 'unknown command' in run('default','usbdiag',False)
    run('quarantine-command','usbdiag')
    print('PASS 14 emitted candidate orchestration/command cases; MMIO and enumeration mocked at documented boundaries')
if __name__=='__main__':main()
