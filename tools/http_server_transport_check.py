#!/usr/bin/env python3
"""Native TCP adapter lifecycle with explicit fake TCP; emitted epoch prefix gate."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import build_count
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);args=p.parse_args()
    spec=importlib.util.spec_from_file_location('tcp_adapter_a64',ROOT/'tools/a64/a64_interp.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory(prefix='http-transport-') as td:
        td=Path(td)
        def run(source,name,expected):
            image=td/(name+'.img')
            r=subprocess.run([args.compiler,'--compile',str(source),'-t','pi4','--load-addr','0x400000',
                              '--stack-addr','0x3000000','--entry-returns','-o',str(image)],cwd=ROOT,
                             env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
            assert r.returncode==0 and image.exists(),r.stdout+r.stderr
            build_count.record_build(source,'pi4',image,by='tools/http_server_transport_check.py',compiler=args.compiler)
            c=m.A64();c.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
            c.pc,c.sp,c.x[30]=0x400000,0x3000000,0x7000000
            for steps in range(1000000):
                if c.pc==0x7000000:break
                c.step()
            else:raise AssertionError('Fixture did not return.')
            assert (c.load(0x6000000,8),c.load(0x6000008,8))==(expected,0),(name,c.load(0x6000000,8),c.load(0x6000008,8))
            print(f'PASS: {name}: {expected} assertions, {steps} emitted instructions.')
        run(ROOT/'Anvil/Services/Http/Tests/transport.pi4','adapter',35)
        text=(ROOT/'RaspberryPi4/Lib/tcp.pi4').read_text()
        start=text.index('Global Dim tcp_generation.i[#TCP_SOCKETS]')
        stop=text.index('  tcp_state = #TCP_CLOSED',start)
        prefix=text[start:stop]+'EndProcedure\n'
        lease_start=text.index('  If tcp_listener_generation[tcp_s] =',text.index('Procedure.i TcpListen('))
        lease_stop=text.index('  TcpWipe()',lease_start)
        lease='Procedure.i LeaseTake()\n'+text[lease_start:lease_stop]+'  ProcedureReturn 0\nEndProcedure\n'
        source=td/'epoch.pi4'
        source.write_text('#TCP_SOCKETS=4\n#NET_TCP_E_STATE=-99\nGlobal tcp_s.i\nGlobal tcp_listen_port.i\n'+prefix+lease+'''
Procedure Main()
  Protected first.i
  Protected failures.i
  TcpWipe()
  first = TcpGeneration()
  If first <> 1 : failures = failures + 1 : EndIf
  TcpWipe()
  If TcpGeneration() <> 2 : failures = failures + 1 : EndIf
  tcp_s = 1
  TcpWipe()
  If TcpGeneration() <> 1 : failures = failures + 1 : EndIf
  tcp_s = 0
  If TcpGeneration() <> 2 : failures = failures + 1 : EndIf
  tcp_generation[0] = $7FFFFFFFFFFFFFFE
  TcpWipe()
  If TcpGeneration() <> 0 : failures = failures + 1 : EndIf
  TcpWipe()
  If TcpGeneration() <> 0 : failures = failures + 1 : EndIf
  tcp_s = -1
  TcpWipe()
  If TcpGeneration() <> 0 : failures = failures + 1 : EndIf
  tcp_s = 1
  If LeaseTake() <> 0 : failures = failures + 1 : EndIf
  If TcpListenerGeneration() <> 1 : failures = failures + 1 : EndIf
  TcpWipe()
  If TcpListenerGeneration() <> 1 : failures = failures + 1 : EndIf
  tcp_listener_generation[1] = $7FFFFFFFFFFFFFFF
  If LeaseTake() <> #NET_TCP_E_STATE : failures = failures + 1 : EndIf
  If TcpListenerGeneration() <> $7FFFFFFFFFFFFFFF : failures = failures + 1 : EndIf
  PokeI($6000000, 12)
  PokeI($6000008, failures)
EndProcedure
''')
        run(source,'real-epoch-and-lease-prefixes',12)
if __name__=='__main__':main()
