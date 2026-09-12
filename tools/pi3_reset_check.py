"""Actual reset command parser/ACK/drain ordering, with bounded I/O doubles."""
import argparse,os,pathlib,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'a64'))
import a64_core_worker_check as base
ROOT=base.ROOT
def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='pi3-reset-') as tmp:
        image=pathlib.Path(tmp)/'reset.img';env=os.environ.copy();env['PMF_ROOT']=str(ROOT)
        r=subprocess.run([a.compiler,'--compile','RaspberryPi3/Tests/update_transport_compile.pi3','-t','pi3','--entry-returns','--load-addr',hex(base.LOAD),'--stack-addr',hex(base.STACK),'-s','-o',str(image)],cwd=ROOT,env=env,capture_output=True,text=True)
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        sym=base.parse_symbols(image);blob=image.read_bytes();a64=base.load_interp(base.INTERP)
        for command,ready,ack,drain,want in [('reset',1,1,1,1),('reset',0,1,1,0),('reset extra',1,1,1,0),('reset',1,0,1,0),('reset',1,1,0,0)]:
            c=a64.A64();c.memory={base.LOAD+i:b for i,b in enumerate(blob)};c.sp=base.STACK
            for i,b in enumerate(command.encode()):c.memory[sym['global_pi3_ut_line']+i]=b
            c.store(sym['global_pi3_ut_line_len'],len(command),8)
            c.pc=base.LOAD+sym['pi3ut_command'];c.x[30]=base.RETURN_PC;events=[];out=[]
            hooks={base.LOAD+sym[n]:n for n in ('pi3updateresetready','pi3updateresetnow','pi3uartwrite','pi3uartwaitclear')}
            for _ in range(200000):
                if c.pc==base.RETURN_PC:break
                h=hooks.get(c.pc)
                if h:
                    result=1
                    if h=='pi3updateresetready':result=ready
                    elif h=='pi3updateresetnow':events.append('reset');result=0
                    elif h=='pi3uartwrite':
                        if ack:out.append(c.x[0]&255)
                        result=ack
                    else:
                        assert c.x[0]==8
                        assert bytes(out)==b'resetting\r\n'
                        events.append('drain');result=drain
                    c.x[0]=result;c.pc=c.x[30]
                else:c.step()
            else:raise AssertionError('unbounded parser')
            assert ('reset' in events)==bool(want),(command,events,out)
            if want:assert events==['drain','reset']
        print('pi3_reset_check PASS five emitted command cases; ACK then drain then reset; no hardware')
if __name__=='__main__':main()
