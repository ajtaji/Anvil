"""Execute real framer, CRC and updater chunk/replay code; UART/time modeled."""
import argparse,os,pathlib,struct,subprocess,sys,tempfile,zlib
from collections import deque
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import a64_core_worker_check as base
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
ROOT=base.ROOT
def frame(off,data,crc=None):return b'P3D1'+struct.pack('<IHI',off,len(data),zlib.crc32(data) if crc is None else crc)+data
def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
    with tempfile.TemporaryDirectory(prefix='pi3-frames-') as tmp:
        image=pathlib.Path(tmp)/'frames.img';env=os.environ.copy();env['PMF_ROOT']=str(ROOT)
        r=subprocess.run([a.compiler,'--compile','RaspberryPi3/Tests/update_integrated_gate.pi3','-t','pi3','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-s','-o',str(image)],cwd=ROOT,env=env,capture_output=True,text=True)
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        sym=base.parse_symbols(image);blob=image.read_bytes();a64=base.load_interp(base.INTERP)
        good=frame(0,b'ab')+frame(2,b'cd');fin=frame(4,b'',0)
        cases=[('normal',good+fin,1,0),('lost-final-ACK',good+frame(2,b'cd')+fin,1,0),
               ('different-replay',good+frame(2,b'XX')+fin,0,None),('partial-header',b'P3D',0,None),
               ('bad-header',b'X3D1'+frame(0,b'ab')[4:]+b'trailing',0,1001),
               ('bad-crc',frame(0,b'ab',0)+b'trailing',0,1003),
               ('bad-length',b'P3D1'+struct.pack('<IHI',0,1025,0)+b'trailing',0,1002),
               ('premature-FIN',fin,0,1002),('bad-FIN-crc',good+frame(4,b'',1),0,1002),
               ('partial-payload',frame(0,b'ab')[:-1],0,1004),('timeout',b'',0,None)]
        for name,data,want,status in cases:
            c=a64.A64();c.memory={base.LOAD+i:b for i,b in enumerate(blob)};c.sp=base.STACK
            for k,v in [('pi3_up_receiving',1),('pi3_up_source',1),('pi3_up_length',4),('pi3_up_stage',0x2000000),('pi3_up_ram',0),('pi3_up_ram_bytes',0x8000000)]:c.store(sym['global_'+k],v,8)
            queue=deque(data);out=[];ticks=0
            c.pc=base.LOAD+sym['pi3ut_receiveframes'];c.x[0]=4;c.x[30]=base.RETURN_PC
            hooks={base.LOAD+sym[n]:n for n in ('pi3uartread','pi3uartwrite','pi3micros')}
            for steps in range(1000000):
                if c.pc==base.RETURN_PC:break
                h=hooks.get(c.pc)
                if h:
                    if h=='pi3uartread':result=queue.popleft() if queue else (1<<64)-1
                    elif h=='pi3uartwrite':out.append(c.x[0]&255);result=1
                    else:ticks+=1000000;result=ticks
                    c.x[0]=result;c.pc=c.x[30]
                else:c.step()
            else:raise AssertionError('unbounded '+name)
            assert c.x[0]==want,(name,c.x[0],out)
            if want:
                assert bytes(c.memory.get(0x2000000+i,0) for i in range(4))==b'abcd'
                assert all(struct.unpack_from('<4sII',bytes(out),i)[2]==0 for i in range(0,len(out),12))
            else:assert c.load(sym['global_pi3_up_receiving'],8)==0
            if status is not None:assert struct.unpack_from('<4sII',bytes(out),len(out)-12)[2]==status,(name,out)
            if name in ('bad-header','bad-crc','bad-length'):assert not queue,'undrained '+name
        print('pi3_update_transport_check PASS eleven emitted receive/replay/FIN/failure cases; no hardware')
if __name__=='__main__':main()
