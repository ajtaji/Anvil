"""BCM2837 SDHOST actual-emission PIO gate, explicit fake controller/card."""
import argparse,hashlib,os,pathlib,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import a64_core_worker_check as base
ROOT=base.ROOT
def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='pi3-sdhost-') as tmp:
        image=pathlib.Path(tmp)/'sd.img';env=os.environ.copy();env['PMF_ROOT']=str(ROOT)
        r=subprocess.run([args.compiler,'--compile','RaspberryPi3/Tests/sdhost_gate.pi3','-t','pi3','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-s','-o',str(image)],cwd=ROOT,env=env,capture_output=True,text=True)
        if r.returncode or not image.exists():raise AssertionError(r.stdout+r.stderr)
        sym=base.parse_symbols(image);blob=image.read_bytes();a64=base.load_interp(base.INTERP);checks=0
        class SD(a64.A64):
            def __init__(self,mode='normal',el=2,affinity=0,sctlr=0,code=None,symbols=None):
                super().__init__();self.mode=mode;self.device_regs={};self.gpio_regs={};self.ticks=0;self.command=-1;self.words=0;self.writes=[];self.data=[]
                self.forced=0;self.status_cmds=0;self.completion_polls=0
                self.symbols=symbols if symbols is not None else sym
                self.memory={base.LOAD+i:b for i,b in enumerate(code if code is not None else blob)};self.sp=base.STACK
                self.enable_system_registers(el=el,preset={0xD51800A0:affinity,0xD51C1000:sctlr,0xD51E1000:0,0xD51B4220:0x3c0})
            def load(self,addr,size):
                if addr==0x3f003008:return 0
                if addr==0x3f003004:self.ticks+=1000;return self.ticks
                if addr in (0x3f200010,0x3f200014):return self.gpio_regs.get(addr-0x3f200000,0xffffffff)
                if 0x3f202000<=addr<=0x3f202050:
                    assert size==4,'MMIO width';off=addr-0x3f202000
                    if off==0:return 0x8000 if self.mode=='command-timeout' and self.command==8 else self.command&63
                    if off==0x20:
                        if self.mode=='crc' and self.command==17:return 0x20
                        return 0x400 if self.command==7 and self.mode!='busy-timeout' else 0
                    if off==0x34:
                        if self.command==17 and self.words<128:return 2|(8<<4)
                        if self.command==24 and self.words<128:return 3
                        # The FSM parks in its wait state after a single-block
                        # transfer and this mode NEVER reports it leaving, even
                        # after FORCE_DATA_MODE.
                        #
                        # THIS IS A CONTRACT, NOT A TIMING CLAIM. The vendor
                        # driver writes FORCE_DATA_MODE on that state and breaks
                        # in the same statement, without ever re-reading the
                        # FSM - so a driver may not depend on observing the
                        # transition, and one that waits for it is waiting for
                        # something it has no right to expect. What that costs
                        # on real silicon is measured on the board, not here.
                        if self.mode=='readwait':
                            # Counted only when a wait state is actually
                            # handed back, so the number is "how many times did
                            # the driver look at the parked FSM", not "how many
                            # times did anything read SDEDM".
                            if self.command==17:self.completion_polls+=1;return 4
                            if self.command==24:self.completion_polls+=1;return 10
                        return 1
                    if off==0x40:self.words+=1;return 0xa5000000+self.words-1
                    if off==0x10:
                        return {8:0x1aa,55:0x20,41:0x80ff8000 if self.mode=='sdsc' else 0xc0ff8000,3:0x12340000,13:0xe00 if self.mode=='program-timeout' else 0x900}.get(self.command,0)
                    if off==0x14:return (0x34560000 if self.mode=='wide-csd' else 2047<<16) if self.command==9 else 0
                    if off==0x18:return 0x12 if self.command==9 and self.mode=='wide-csd' else 0
                    if off==0x1c:return 0x40000000 if self.command==9 and self.mode!='bad-csd' else 0
                    return self.device_regs.get(off,0)
                return super().load(addr,size)
            def store(self,addr,value,size):
                if 0x3f000000<=addr<0x40000000:
                    assert size==4,'MMIO width';self.writes.append((addr,value&0xffffffff))
                    if addr in (0x3f200010,0x3f200014):
                        self.gpio_regs[addr-0x3f200000]=value&0xffffffff
                    if 0x3f202000<=addr<=0x3f202050:
                        off=addr-0x3f202000;self.device_regs[off]=value&0xffffffff
                        if off==0 and value&0x8000:
                            self.command=value&63;self.words=0
                            if self.command==13:self.status_cmds+=1
                        if off==0x34 and value&0x80000:self.forced+=1
                        if off==0x40:self.data.append(value&0xffffffff);self.words+=1
                    return
                assert not 0xfe000000<=addr<0xff000000,'Pi4 alias touched'
                return super().store(addr,value,size)
            def call(self,name,*args):
                self.pc=base.LOAD+self.symbols[name.lower()];self.x[30]=base.RETURN_PC
                for i,v in enumerate(args):self.x[i]=v
                for n in range(3000000):
                    if self.pc==base.RETURN_PC:return self.x[0]
                    self.step()
                raise AssertionError('unbounded '+name)
        c=SD();assert c.call('Pi3SdInit',400000000,0,0x8000000)==1;checks+=1
        assert c.call('Pi3SdBlockCount')==2097152;checks+=1
        assert (0x3f200010,0xe4ffffff) in c.writes and (0x3f200014,0xfffff924) in c.writes;checks+=1
        # Firmware may leave the alternate EMMC2 pin group selected. The
        # Wi-Fi probe must be able to establish the source-backed SDHOST
        # route before any card mount, preserving every unrelated FSEL bit.
        c=SD();c.gpio_regs[0x10]=0x3f200924;c.gpio_regs[0x14]=0x00000fff
        assert c.call('Pi3SdSetBootClock',250000000)==1
        before=len(c.writes)
        assert c.call('Pi3SdRoutePins')==1
        assert c.gpio_regs[0x10]==0x24200924 and c.gpio_regs[0x14]==0x00000924
        assert c.writes[before:]==[(0x3f200010,0x24200924),(0x3f200014,0x00000924)]
        before=len(c.writes);assert c.call('Pi3SdRoutePins')==1
        assert c.gpio_regs[0x10]==0x24200924 and c.gpio_regs[0x14]==0x00000924
        assert c.writes[before:]==[(0x3f200010,0x24200924),(0x3f200014,0x00000924)]
        checks+=5
        c=SD();assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
        b=sym['global_sd_gate_buffer'];assert c.call('Pi3SdReadBlock',42,b)==1;checks+=1
        assert all(c.load(b+i*4,4)==0xa5000000+i for i in range(128));checks+=128
        assert c.call('Pi3SdSetWriteWindow',40,10)==1
        assert c.call('Pi3SdWriteBlock',42,b)==1 and c.data==[0xa5000000+i for i in range(128)];checks+=2
        assert c.call('Pi3SdInit',400000000,0,0x8000000)==0;checks+=1
        c=SD('wide-csd');assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
        assert c.call('Pi3SdBlockCount')==(0x123456+1)*1024;checks+=1
        for mode in ('command-timeout','busy-timeout','sdsc','program-timeout','bad-csd'):
            c=SD(mode);assert c.call('Pi3SdInit',400000000,0,0x8000000)==0,mode;checks+=1
        # Direct monitor is EL2 with MMU+caches enabled before first SD use.
        # It must have installed the actual firmware CORE rate beforehand;
        # the cached path must never call the mailbox-backed clock service.
        query=sym['global_sd_gate_clock_queries']
        c=SD(sctlr=5)
        assert c.call('Pi3SdInit',400000000,0,0x8000000)==0,'cached SD init without remembered clock was accepted'
        assert c.load(query,8)==0,'cached refusal called the mailbox clock service';checks+=2
        c=SD(sctlr=5)
        assert c.call('Pi3SdSetBootClock',250000000)==1
        assert c.call('Pi3SdInit',400000000,0,0x8000000)==1,'cached SD init refused explicit clock handoff'
        assert c.load(query,8)==0,'cached SD init called the mailbox clock service';checks+=3
        c=SD(sctlr=5)
        assert c.call('Pi3SdSetBootClock',999)==0,'invalid remembered clock was accepted'
        assert c.call('Pi3SdInit',400000000,0,0x8000000)==0,'invalid handoff authorized cached SD init'
        assert c.load(query,8)==0;checks+=3
        for mixed in (1,4):
            c=SD(sctlr=mixed)
            assert c.call('Pi3SdSetBootClock',250000000)==1
            assert c.call('Pi3SdInit',400000000,0,0x8000000)==0,'mixed MMU/cache state was accepted'
            assert c.load(query,8)==0,'mixed-state refusal called clock service';checks+=3
        c=SD(sctlr=0)
        assert c.call('Pi3SdInit',400000000,0,0x8000000)==1,'legacy cache-off path refused'
        assert c.load(query,8)==1,'cache-off path did not use the clock service';checks+=2
        c=SD();assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
        c.mode='crc';assert c.call('Pi3SdReadBlock',42,b)==0
        count=len(c.writes);assert c.call('Pi3SdWriteBlock',42,b)==0 and len(c.writes)==count;checks+=2
        for el,aff in ((1,0),(2,0x100),(2,1<<32)):
            c=SD(el=el,affinity=aff);assert c.call('Pi3SdInit',400000000,0,0x8000000)==0 and not c.writes;checks+=1
        for lba in (39,50,2097152):
            c=SD();assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
            assert c.call('Pi3SdSetWriteWindow',40,10)==1
            before=len(c.writes);assert c.call('Pi3SdWriteBlock',lba,b)==0 and len(c.writes)==before;checks+=1
        # --- what a read costs, which is the whole of the 15-second story ---
        # The controller parks in READWAIT after a single-block read. The
        # driver must end that with one FORCE_DATA_MODE write and stop looking:
        # polling on for IDENTMODE/DATAMODE runs every transfer to its
        # one-second deadline, which is how a 1,039-read mount missed a
        # 15-second watchdog thirteen times out of thirteen.
        c=SD('readwait');assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
        before=c.status_cmds
        assert c.call('Pi3SdReadBlock',42,b)==1,'a read did not complete out of READWAIT'
        assert c.forced==1,'FORCE_DATA_MODE was written %d times, not once'%c.forced
        assert c.completion_polls<=2,'the completion wait polled %d times, so it is waiting for a transition it may not observe'%c.completion_polls
        assert c.status_cmds==before,'a successful READ polled the card with CMD13; only writes leave it programming'
        checks+=4
        c=SD('readwait');assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
        assert c.call('Pi3SdSetWriteWindow',40,10)==1
        before=c.status_cmds;c.forced=0
        assert c.call('Pi3SdWriteBlock',42,b)==1,'a write did not complete out of WRITESTART1'
        assert c.forced==1,'a write did not end its wait state exactly once'
        assert c.status_cmds>before,'a WRITE did not wait for the card to finish programming'
        checks+=3
        # --- the filesystems' ranged seam -----------------------------------
        # A range is a loop of single-block commands here, so the only thing a
        # range adds is the question of what happens when it runs off the end
        # of the armed write window. The answer has to be "nothing was
        # written", because a half-applied range leaves a filesystem
        # inconsistent with no record of where it stopped.
        def armed(window=(40,10)):
            m=SD();assert m.call('Pi3SdInit',400000000,0,0x8000000)==1
            if window is not None:assert m.call('Pi3SdSetWriteWindow',*window)==1
            m.data=[];return m
        c=armed();assert c.call('Pi3SdReadBlocks',42,3,b)==1;checks+=1
        assert all(c.load(b+i*4,4)==0xa5000000+(i%128) for i in range(384)),'ranged read did not land whole';checks+=384
        c=armed();assert c.call('Pi3SdWriteBlocks',42,3,b)==1,'in-window range refused';checks+=1
        assert len(c.data)==384,'ranged write did not send three whole blocks';checks+=1
        for lba,n,window,why in (
            (48,3,(40,10),'range runs past the window end'),
            (39,2,(40,10),'range starts before the window'),
            (40,11,(40,10),'range is longer than the whole window'),
            (42,0,(40,10),'empty range'),
            (42,1,None,'no window armed'),
        ):
            c=armed(window);before=len(c.writes)
            assert c.call('Pi3SdWriteBlocks',lba,n,b)==0,why+' was accepted'
            assert len(c.writes)==before and not c.data,why+' wrote something first';checks+=2
        # The mutant: take the range pre-check out and the first blocks of a
        # range that overruns the window DO leave, which is the whole point.
        with tempfile.TemporaryDirectory(prefix='pi3-sdhost-mutant-') as mut:
            mroot=pathlib.Path(mut)
            for rel in ('RaspberryPi3/Lib/timer.pbi','RaspberryPi3/Lib/sdhost.pbi','RaspberryPi3/Tests/sdhost_gate.pi3','RaspberryPi3/Intrinsics/bcm2837_hardware.def'):
                dst=mroot/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                dst.write_bytes((ROOT/rel).read_bytes())
            src=mroot/'RaspberryPi3/Lib/sdhost.pbi';text=src.read_text(encoding='utf-8')
            guard=[line for line in text.splitlines() if 'p3sd_write_count - count' in line]
            assert len(guard)==1,'the ranged write guard is no longer a single line'
            src.write_text(text.replace(guard[0],'  ; guard removed by the gate'),encoding='utf-8')
            mimg=mroot/'mutant.img'
            mr=subprocess.run([args.compiler,'--compile','RaspberryPi3/Tests/sdhost_gate.pi3','-t','pi3','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-s','-o',str(mimg)],cwd=mroot,env=dict(os.environ,PMF_ROOT=str(mroot)),capture_output=True,text=True)
            assert mr.returncode==0 and mimg.exists(),mr.stdout+mr.stderr
            msym=base.parse_symbols(mimg);mblob=mimg.read_bytes()
            c=SD(code=mblob,symbols=msym);assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
            assert c.call('Pi3SdSetWriteWindow',40,10)==1;c.data=[]
            assert c.call('Pi3SdWriteBlocks',48,3,msym['global_sd_gate_buffer'])==0,'mutant somehow accepted the overrun'
            assert c.data,'mutant wrote nothing, so this case does not prove the pre-check';checks+=1

            def mutate(edit,label):
                '''Recompile sdhost.pbi with one line changed and hand it back.'''
                src.write_bytes((ROOT/'RaspberryPi3/Lib/sdhost.pbi').read_bytes())
                text=src.read_text(encoding='utf-8')
                after=edit(text)
                assert after!=text,'the '+label+' mutation matched nothing'
                src.write_text(after,encoding='utf-8')
                img=mroot/(label+'.img')
                r=subprocess.run([args.compiler,'--compile','RaspberryPi3/Tests/sdhost_gate.pi3','-t','pi3','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-s','-o',str(img)],cwd=mroot,env=dict(os.environ,PMF_ROOT=str(mroot)),capture_output=True,text=True)
                assert r.returncode==0 and img.exists(),r.stdout+r.stderr
                return base.parse_symbols(img),img.read_bytes()

            # MUTANT: put the per-read poll back. Forcing the FSM out of
            # READWAIT and then continuing to poll is the defect that cost
            # >14 ms a read; with the controller modelled honestly the read
            # must now fail rather than quietly succeed.
            msym,mblob=mutate(lambda s:s.replace('p3sdWrite($34, edm | $80000)\n      Break\n','p3sdWrite($34, edm | $80000)\n',1),'poll')
            c=SD('readwait',code=mblob,symbols=msym)
            assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
            assert c.call('Pi3SdReadBlock',42,msym['global_sd_gate_buffer'])==0,'the per-read poll mutant still succeeded, so this case proves nothing'
            checks+=1

            # MUTANT: poll the card after a successful read as well as a write.
            msym,mblob=mutate(lambda s:s.replace('  If writing <> 0\n    If p3sdCardReady() = 0 : ProcedureReturn 0 : EndIf\n  EndIf','  If p3sdCardReady() = 0 : ProcedureReturn 0 : EndIf',1),'cmd13')
            c=SD('readwait',code=mblob,symbols=msym)
            assert c.call('Pi3SdInit',400000000,0,0x8000000)==1
            before=c.status_cmds
            c.call('Pi3SdReadBlock',42,msym['global_sd_gate_buffer'])
            assert c.status_cmds>before,'the extra-status mutant issued no CMD13, so this case proves nothing'
            checks+=1
        print('pi3_sdhost_check PASS',checks,'checks; real emitted MMIO/PIO, twelve refusal cases, three mutants; no silicon claim')
        print('compiler SHA256',hashlib.sha256(pathlib.Path(args.compiler).read_bytes()).hexdigest())
if __name__=='__main__':main()
