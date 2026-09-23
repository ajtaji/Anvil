#!/usr/bin/env python3
"""Real net/link/TCP/HTTP over scripted checksum-correct network frames."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import build_count
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);args=p.parse_args(); args.compiler = _pmfpath.Path(resolve_compiler(args.compiler)) if args.compiler else args.compiler
    prefix=(ROOT/'RaspberryPi4/Tests/tcp_multiif_emitted_gate.pi4').read_text().split('; mode0:')[0]
    prefix=prefix.replace('XIncludeFile "Anvil/Core/sha256.pbi"','').replace('XIncludeFile "Anvil/Core/netrecv.pbi"','')
    prefix='Global Dim gate_wire.a[4096]\nGlobal gate_wire_size.i\n'+prefix
    witness='''
  If n >= 54 And PeekA(*buf + 23) = 6
    Define head.i
    Define count.i
    Define j.i
    head = ((PeekA(*buf + 46) >> 4) & 15) * 4
    count = ((PeekA(*buf + 16) << 8) | PeekA(*buf + 17)) - 20 - head
    For j = 0 To count - 1
      If gate_wire_size < 4096
        gate_wire[gate_wire_size] = PeekA(*buf + 34 + head + j)
        gate_wire_size = gate_wire_size + 1
      EndIf
    Next
  EndIf
'''
    prefix=prefix.replace('  gate_txKind = kind','  gate_txKind = kind'+witness,1)
    with tempfile.TemporaryDirectory(prefix='http-queued-') as td:
        td=Path(td); source=td/'queued.pi4';image=td/'queued.img'
        source.write_text(prefix+'\n'+(ROOT/'Anvil/Services/Http/Tests/queued_http_body.pi4').read_text())
        r=subprocess.run([args.compiler,'--compile',str(source),'-t','pi4','--load-addr','0x400000',
                          '--stack-addr','0x3000000','--entry-returns','-o',str(image),'-s'],cwd=ROOT,
                         env=dict(os.environ,PMF_ROOT=str(ROOT)),capture_output=True,text=True)
        assert r.returncode==0 and image.exists(),r.stdout+r.stderr
        build_count.record_build(source,'pi4',image,by='tools/http_server_queued_check.py',compiler=args.compiler)
        spec=importlib.util.spec_from_file_location('queued_a64',ROOT/'tools/a64/a64_interp.py')
        m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
        c=m.A64();c.memory.update({0x400000+i:b for i,b in enumerate(image.read_bytes())})
        c.pc,c.sp,c.x[30]=0x400000,0x3000000,0x7000000
        for steps in range(15000000):
            if c.pc==0x7000000:break
            c.step()
        else:raise AssertionError('Wire fixture exceeded execution bound.')
        assert c.x[0]==0,('wire fixture failed at assertion',c.x[0],steps)
        print(f'PASS: 15 sequential plus 2 simultaneous real TCP+HTTP connections, TIME-WAIT retention, pool-full refusal, {steps} instructions.')
if __name__=='__main__':main()
