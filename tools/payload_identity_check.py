"""Execute the production ISA-neutral payload identity policy on Zentaji.

Explicit expected outcomes cover board/ISA mismatch, backend refusal and
stack geometry. This does not execute a payload or claim PMFBOOT support
for a new ISA; the fixture's non-ARM identity is test data only.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
from pmf_compiler import resolve_compiler
ROOT = Path(__file__).resolve().parents[1]

# arch, target, stack, required-arch, required-target, alignment, error
CASES = [
 (1,2711,0x8000000,1,2711,16,0),
 (1,2712,0x8000000,1,2711,16,3),
 (1,2711,0x8000000,1,2712,16,3),
 (1,2837,0x8000000,1,2837,16,0),
 (1,2290,0x8000000,1,2290,16,0),
 (0,2711,0x8000000,1,2711,16,2),
 (77,2711,0x8000000,1,2711,16,2),
 (1,9999,0x8000000,1,2711,16,3),
 (1,0,0x8000000,1,2711,16,3),
 (1,2711,0,1,2711,16,4),
 (1,2711,-16,1,2711,16,4),
 (1,2711,0x8000001,1,2711,16,4),
 (1,2711,0x8000008,1,2711,16,4),
 (77,901,0x10008,77,901,8,0),
 (1,901,0x10008,77,901,8,2),
 (77,902,0x10008,77,901,8,3),
 (77,901,0x10004,77,901,8,4),
 (77,901,0x100000008,77,901,8,0),
 (77,901,0x10001,77,901,1,0),
 (77,901,0x10000,0,901,8,1),
 (77,901,0x10000,77,0,8,1),
 (77,901,0x10000,77,901,0,1),
 (77,901,0x10000,77,901,-8,1),
 (77,901,0x10000,77,901,3,1),
]
GEOMETRY = [(16,16,1),(16,32,1),(8,8,1),(1,1,1),(4096,8192,1),
            (0,16,0),(-1,16,0),(3,24,0),(16,0,0),(16,8,0),(16,24,0)]


def run(command, env):
    p = subprocess.run([str(x) for x in command], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    return p.stdout


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler')
    ap.add_argument('--zenemu',type=Path,required=True)
    a=ap.parse_args(); compiler=resolve_compiler(a.compiler)
    env=dict(os.environ,PMF_ROOT=str(ROOT))
    lines=['IncludeFile "Anvil/Core/payload_identity.pbi"','Procedure.i Main()']
    for n,row in enumerate(CASES,1):
        args=','.join(str(x) for x in row[:-1])
        lines += [f'If PmfIdentityCheck({args}) <> {row[-1]}',f'ProcedureReturn {n}','EndIf']
    for n,(alignment,extent,want) in enumerate(GEOMETRY,100):
        lines += [f'If PmfStackContractValid({alignment},{extent}) <> {want}',f'ProcedureReturn {n}','EndIf']
    lines += ['ProcedureReturn 42','EndProcedure']
    with tempfile.TemporaryDirectory(prefix='anvil-payload-identity-') as tmp:
        td=Path(tmp); src=td/'identity.zentaji'; image=td/'identity.zex'
        src.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        run([compiler,'--compile',src,'-o',image],env)
        cfg=td/'machine.txt';cfg.write_text('machine $100000 1 1000 0\nimage '+image.as_posix()+'\n')
        out=run([a.zenemu.resolve(),cfg,'--max','1000000'],env)
        assert 'exit=2A ' in out,out
    print(f'PASS payload identity on Zentaji: {len(CASES)} identity/stack decisions and {len(GEOMETRY)} backend geometry cases')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
