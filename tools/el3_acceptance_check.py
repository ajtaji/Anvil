"""Execute acceptance command bytes with modeled IRQ/BRK delivery; not silicon."""
import argparse, importlib.util, os, subprocess, sys, tempfile
from pathlib import Path
import build_count
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
LOAD=0x400000
RETURN=0x7000000

def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
    spec=importlib.util.spec_from_file_location('accept_a64',ROOT/'tools/a64/a64_interp.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory(prefix='el3-accept-') as tmp:
        image=Path(tmp)/'gate.img';src=ROOT/'RaspberryPi4/Tests/el3_acceptance_gate.pi4'
        r=subprocess.run([a.compiler,'--compile',str(src),'-t','pi4','--load-addr',hex(LOAD),'--stack-addr','0x3000000','--entry-returns','-o',str(image),'-s'],cwd=ROOT,env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(src,'pi4',image,by='tools/el3_acceptance_check.py',compiler=a.compiler)
        binary=image.read_bytes()
        symbols=dict(line.split('=',1) for line in Path(str(image)+'.sym').read_text().splitlines() if '=' in line)
        def address(name):return int(symbols[name],0)+(0 if name.startswith('global_') else LOAD)
        class Model(m.A64):
            def __init__(self,mode='ready',data=binary):
                super().__init__();self.memory.update({LOAD+i:b for i,b in enumerate(data)})
                self.sp=0x3000000;self.mode=mode;self.acks=[];self.eois=[];self.inflight=False;self.watch=[]
                self.stop_expected=None;self.stop_checks=0;self.gic_writes=[]
                self.allow_setup_gic=False
                self.frozen_reads=0;self.stormed=False;self.spurious_left=2 if mode=='spurious' else 0
                self.cntpct_per_instruction=0 if mode=='frozen' else 100
                self.enable_system_registers(el=3,preset={0xd51800a0:0,0xd51b4220:960,0xd51e1100:0x5b3,0xd51fe220:2,0xd51fe240:1234,0xd51be000:1000000})
                for at,v in ((0xff841fe8,0x20),(0xff841008,0x43b),(0xff8420fc,0x0202143b),(0xff841004,0x407),(0xff841000,3),(0xff842000,0x1e7),(0xff842004,255),(0xff841080,0xffffffff)):
                    m.A64.store(self,at,v,4)
                # Real polled Pi 4 devices can assert level-sensitive SPIs
                # while those lines remain disabled. They own no delivery
                # path, and acceptance must preserve rather than reject them.
                for at,v in ((0xff841208,0x00000040),(0xff84120c,0x00008400),(0xff841214,0x00004000)):
                    m.A64.store(self,at,v,4)
            def load(self,at,size):
                if at==0xff84200c:
                    if self.spurious_left:
                        self.spurious_left-=1;self.acks.append(1023);return 1023
                    self.acks.append(29);self.inflight=True;return 29
                return super().load(at,size)
            def assert_stop_restored(self):
                e=self.stop_expected;assert e is not None,'watchdog stop had no restoration contract'
                assert self.system_registers[0xd51ec000]==e['vbar'],'Watchdog stopped before VBAR restored'
                assert self.system_registers[0xd51b4220]==e['daif'],'Watchdog stopped before DAIF restored'
                assert self.load(address('global_exception_irq_handler'),8)==e['handler'],'Watchdog stopped before exception handler restored'
                assert self.system_registers[0xd51fe220]&3==e['timer_ctl'],'Watchdog stopped before timer control restored'
                assert self.system_registers[0xd51fe240]==e['timer_compare'],'Watchdog stopped before timer compare restored'
                assert self.load(0xff841100,4)&(1<<29)==e['enabled'],'Watchdog stopped before INTID29 enable restored'
                assert self.load(0xff841200,4)&(1<<29)==e['pending'],'Watchdog stopped before INTID29 pending restored'
                assert self.load(0xff841300,4)&(1<<29)==e['active'],'Watchdog stopped before INTID29 active restored'
                assert self.load(0xff841400+29,1)&255==e['priority'],'Watchdog stopped before INTID29 priority restored'
                assert self.load(address('global_at_ready'),8)==e['at_ready'],'Watchdog stopped before timer claim released'
                assert self.load(address('global_ig_handlers')+29*8,8)==e['ig_handler'],'Watchdog stopped before GIC claim released'
                assert self.load(address('global_ig_enabled')+29*8,8)==e['ig_enabled'],'Watchdog stopped before GIC software enable restored'
                assert self.load(0xff841000,4)==e['dist'] and self.load(0xff842000,4)==e['cpu'] and self.load(0xff842004,4)==e['pmr'],'Watchdog stopped before controller state restored'
                assert self.load(address('global_accept_gic_owner'),8)==2 and self.load(address('global_accept_watchdog_owner'),8)==2,'Acceptance leases released before watchdog stop'
                self.stop_checks+=1
            def store(self,at,value,size):
                if 0xff841000<=at<0xff843000:
                    if not self.allow_setup_gic:
                        assert self.load(address('global_accept_gic_owner'),8)==2,'GIC write without EL3 acceptance lease'
                        assert self.load(address('global_accept_watchdog_owner'),8)==2 and self.load(address('global_safety_wdog_on'),8)==1,'GIC write before recovery watchdog'
                    self.gic_writes.append((at,value,size))
                if at in (0xfe10001c,0xfe100024):
                    assert self.load(address('global_accept_watchdog_owner'),8)==2,'Watchdog write without EL3 acceptance lease'
                if self.mode=='stop_fail' and at==0xff841180 and value&(1<<29):
                    return
                if self.mode=='release_fail' and at==0xff841400+29 and value==0:
                    return
                if at==0xfe10001c:
                    self.watch.append(value)
                    if value==0x5a000102:
                        self.assert_stop_restored()
                if at==0xff842010:self.eois.append(value);self.inflight=False
                if 0xff841100<=at<0xff841120:value=self.load(at,size)|value
                if 0xff841180<=at<0xff8411a0:
                    return super().store(at-0x80,self.load(at-0x80,size)&~value,size)
                return super().store(at,value,size)
            def step(self):
                if self.mode=='frozen' and self.pc==address('e3ticks'):
                    self.frozen_reads+=1
                    if self.frozen_reads==32:
                        # Accelerate only the induction variable; the emitted
                        # loop still has to take its own finite-ceiling edge.
                        super().store(self.x[29]-24,9999999,8)
                if self.mode=='storm' and not self.stormed and self.load(address('global_e3_irq_count'),8)==1 and not (self.system_registers[0xd51b4220]&0x80):
                    self.stormed=True
                    super().store(address('global_ig_enabled')+29*8,1,8)
                    super().store(0xff841100,self.load(0xff841100,4)|(1<<29),4)
                    self.system_registers[0xd51fe240]=self.cntpct+1000
                    self.system_registers[0xd51fe220]=1
                ctl=self.system_registers.get(0xd51fe220,0)
                if ctl&1 and self.cntpct>=self.system_registers.get(0xd51fe240,0):
                    self.system_registers[0xd51fe220]=ctl|4
                    if self.mode!='missing' and not self.inflight and self.load(0xff841100,4)&(1<<29):self.take_irq()
                word=self.load(self.pc,4)
                if word&~31 in (0xd51fe220,0xd51fe240):
                    assert self.load(address('global_accept_gic_owner'),8)==2,'Timer write without EL3 acceptance lease'
                    assert self.load(address('global_accept_watchdog_owner'),8)==2 and self.load(address('global_safety_wdog_on'),8)==1,'Timer write before recovery watchdog'
                if word&~31==0xd51ec000 and self.x[word&31]==address('e3_fault_vectors'):
                    assert self.watch and self.watch[-1]&0x30==0x20, 'Temporary VBAR installed without watchdog'
                if word==0xd420a620:
                    self.system_registers[0xd51e4020]=self.pc
                    self.system_registers[0xd51e4000]=self.pstate()
                    self.system_registers[0xd51e5200]=0xf2000531 if self.mode!='wrong_esr' else 0xf2000532
                    if self.mode=='wrong_pc':self.system_registers[0xd51e4020]+=4
                    if self.mode=='wrong_spsr_mode':self.system_registers[0xd51e4000]&=~1
                    if self.mode=='wrong_spsr_mask':self.system_registers[0xd51e4000]&=~0x80
                    if self.mode=='replay':self.store(address('global_e3_fault_armed'),0,8)
                    self.pc=self.system_registers[0xd51ec000]+(0 if self.mode=='wrong_slot' else 512)
                    return
                return super().step()
        def call(cpu,name,limit=100000):
            cpu.pc=address(name);cpu.x[30]=RETURN
            for _ in range(limit):
                if cpu.pc==RETURN:return cpu.x[0]
                if cpu.pc in (address('e3_fault_park'),address('exception_park_3')):raise AssertionError('fault refused')
                cpu.step()
            raise AssertionError('execution exceeded instruction bound')
        def fresh(mode='ready',data=binary):
            c=Model(mode,data);assert call(c,'exceptioninstall')==3;return c
        def acceptance_call(cpu,name,limit=100000,expect_stop=True):
            saved_sp=cpu.sp
            saved={r:(0x9160000000000000+r) for r in range(19,30)}
            for r,value in saved.items():cpu.x[r]=value
            cpu.stop_expected={
                'vbar':cpu.system_registers[0xd51ec000], 'daif':cpu.system_registers[0xd51b4220],
                'handler':cpu.load(address('global_exception_irq_handler'),8),
                'timer_ctl':cpu.system_registers[0xd51fe220]&3, 'timer_compare':cpu.system_registers[0xd51fe240],
                'enabled':cpu.load(0xff841100,4)&(1<<29), 'pending':cpu.load(0xff841200,4)&(1<<29),
                'active':cpu.load(0xff841300,4)&(1<<29), 'priority':cpu.load(0xff841400+29,1)&255,
                'at_ready':cpu.load(address('global_at_ready'),8),
                'ig_handler':cpu.load(address('global_ig_handlers')+29*8,8),
                'ig_enabled':cpu.load(address('global_ig_enabled')+29*8,8),
                'dist':cpu.load(0xff841000,4), 'cpu':cpu.load(0xff842000,4), 'pmr':cpu.load(0xff842004,4)}
            result=call(cpu,name,limit)
            assert cpu.sp==saved_sp,name+' changed SP'
            for r,value in saved.items():assert cpu.x[r]==value,name+f' changed x{r}'
            if expect_stop:assert cpu.stop_checks==1,name+' did not stop watchdog after restoration'
            return result
        for mode,want in (('ready',1),('missing',(1<<64)-4),('frozen',(1<<64)-4),('spurious',1),('storm',(1<<64)-4)):
            c=fresh(mode);assert acceptance_call(c,'e3accepttimer')==want,(mode,c.x[0])
            if mode=='spurious':
                assert c.acks==[1023,1023,29] and c.eois==[29]
            elif mode=='storm':
                assert c.acks==c.eois==[29,29] and c.stormed
            else:
                assert c.acks==c.eois==([29] if mode=='ready' else [])
            assert c.system_registers[0xd51fe220]&3==2 and c.system_registers[0xd51fe240]==1234
            assert c.system_registers[0xd51b4220]==960
            assert c.load(address('global_ig_ready'),8)==0
            assert c.load(address('global_accept_gic_owner'),8)==0 and c.load(address('global_accept_watchdog_owner'),8)==0
        # Production reaches the prompt with Anvil's masked GIC owner already
        # initialized. Disabled pending SPIs from polled devices remain legal;
        # the timer and fault diagnostics borrow and restore that owner.
        for name in ('e3accepttimer','e3acceptfault'):
            c=fresh();v=call(c,'exceptionvbar');c.x[0]=v;c.allow_setup_gic=True
            assert call(c,'interruptinit')==1;c.allow_setup_gic=False;c.gic_writes.clear()
            assert acceptance_call(c,name)==1
            assert c.load(address('global_ig_ready'),8)==1
            assert c.load(0xff841208,4)==0x40 and c.load(0xff84120c,4)==0x8400 and c.load(0xff841214,4)==0x4000
        c=fresh();v=c.system_registers[0xd51ec000];sp=c.sp
        assert acceptance_call(c,'e3acceptfault')==1
        assert c.sp==sp and c.system_registers[0xd51ec000]==v
        for key,value in (('count',1),('el',3),('slot',4),('esr',0xf2000531),('pc',address('e3_fault_site')),('armed',0)):
            assert c.load(address('global_e3_fault_'+key),8)==value,key
        for mode in ('wrong_esr','wrong_pc','wrong_spsr_mode','wrong_spsr_mask','wrong_slot','replay'):
            c=fresh(mode)
            try:acceptance_call(c,'e3acceptfault',expect_stop=False)
            except AssertionError as e:
                assert str(e)=='fault refused'
                assert c.watch and c.watch[-1]&0x30==0x20, 'Rejected fault disarmed watchdog'
                assert c.load(address('global_accept_gic_owner'),8)==2 and c.load(address('global_accept_watchdog_owner'),8)==2
            else:raise AssertionError('Invalid fault resumed: '+mode)
        # A source-stop failure is fatal in the installed exception policy; it
        # must retain both leases and the watchdog rather than limp onward.
        c=fresh('stop_fail')
        try:acceptance_call(c,'e3accepttimer',expect_stop=False)
        except AssertionError as e:
            assert str(e)=='fault refused' and c.watch and c.watch[-1]&0x30==0x20
            assert c.load(address('global_accept_gic_owner'),8)==2 and c.load(address('global_accept_watchdog_owner'),8)==2
        else:raise AssertionError('AtStop failure returned')
        # Restoration refusal returns -5 for diagnostics, retains the armed
        # watchdog and retains both leases until the resulting restart.
        c=fresh('release_fail')
        assert acceptance_call(c,'e3accepttimer',expect_stop=False)==(1<<64)-5
        assert c.stop_checks==0 and c.watch and c.watch[-1]!=0x5a000102
        assert c.load(address('global_accept_gic_owner'),8)==2 and c.load(address('global_accept_watchdog_owner'),8)==2
        # The outer CPU-interface mask is itself a checked restoration step.
        # Force InterruptStop to refuse: the timer/source cleanup may still
        # succeed later, but the run must remain -5 with recovery ownership.
        mutant=bytearray(binary);at=address('interruptstop')-LOAD
        mutant[at:at+8]=(0xd2800000).to_bytes(4,'little')+(0xd65f03c0).to_bytes(4,'little')
        c=fresh(data=mutant)
        assert acceptance_call(c,'e3accepttimer',expect_stop=False)==(1<<64)-5
        assert c.stop_checks==0 and c.watch and c.watch[-1]!=0x5a000102
        assert c.load(address('global_accept_gic_owner'),8)==2 and c.load(address('global_accept_watchdog_owner'),8)==2
        # Occupied hardware state is observed before InterruptInit's first GIC
        # write; lease acquisition itself writes only the software owner words.
        c=fresh();m.A64.store(c,0xff841100,1<<31,4);c.gic_writes.clear()
        assert acceptance_call(c,'e3accepttimer',expect_stop=False)==(1<<64)-2
        assert not c.gic_writes and not c.watch
        assert c.load(address('global_accept_gic_owner'),8)==0 and c.load(address('global_accept_watchdog_owner'),8)==0
        # Persistent multicore ownership blocks both halves of the command,
        # even if a caller reaches it after multicore stop/fault bookkeeping.
        for name in ('e3accepttimer','e3acceptfault'):
            c=fresh()
            for key,value in (('global_accept_secondary_owner',1),('global_accept_gic_owner',1),('global_accept_watchdog_owner',1)):
                m.A64.store(c,address(key),value,8)
            assert acceptance_call(c,name,expect_stop=False)==(1<<64)-2
            assert not c.watch
        # Exact emitted resume increment mutation must no longer return normally.
        mutant=bytearray(binary);needle=(0x91001042).to_bytes(4,'little');at=mutant.find(needle,address('e3_fault_sync')-LOAD)
        assert at>=0;mutant[at:at+4]=(0xd503201f).to_bytes(4,'little')
        c=fresh(data=mutant)
        try:call(c,'e3acceptfault')
        except AssertionError:pass
        else:raise AssertionError('Missing resume increment mutant survived')
        # Removing watchdog arm is rejected before temporary VBAR publication.
        mutant=bytearray(binary);at=address('safety_wdogarm')-LOAD
        mutant[at:at+4]=(0xd65f03c0).to_bytes(4,'little')
        c=fresh(data=mutant)
        try:call(c,'e3acceptfault')
        except AssertionError as e:assert 'without watchdog' in str(e)
        else:raise AssertionError('Missing watchdog arm mutant survived')
        for el,core in ((2,0),(3,1)):
            c=fresh();c.current_el=el;c.system_registers[0xd51800a0]=core
            assert acceptance_call(c,'e3accepttimer',expect_stop=False)==(1<<64)-1
            assert not c.watch and not c.acks
        print('PASS: timer delivery/missing/frozen/storm/spurious and stop/release failures; read-only GIC and cross-acceptance leases; watchdog-stop restoration and ABI; masked SPSR mode/DAIF, slot/ESR/PC/replay refusals and emitted mutations. Desk model only; watchdog expiry is not modeled.')
if __name__=='__main__':main()
