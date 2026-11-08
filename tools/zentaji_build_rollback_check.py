"""Fault the real counted Zentaji artifact publication and require exact rollback."""
import argparse
from pathlib import Path
import sys
from pmf_compiler import resolve_compiler
import build
import build_count
ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler');a=ap.parse_args();cc=resolve_compiler(a.compiler)
    output=ROOT/'build/zentaji/anvil.zex'
    artifacts=[output]+[Path(str(output)+suffix) for suffix in ('.boot.json','.asm','.zmap','.compiled.zex','.compiled.asm')]
    source=ROOT/'Zentaji/Board/board.zentaji';ledger=ROOT/'build/BUILDS.log'
    before={p:p.read_bytes() for p in artifacts+[source,ledger]};number=build_count.current('zentaji')
    destinations={p.resolve() for p in artifacts};original=build.os.replace;attempts=0;failed=False
    def replace(src,dst):
        nonlocal attempts,failed
        if Path(dst).resolve() in destinations and '.build-stage-' in Path(src).name:
            attempts+=1
            if attempts==3:
                failed=True
                raise OSError('controlled publication failure at the third Zentaji artifact')
        return original(src,dst)
    build.os.replace=replace
    try:
        try:build.build(cc,'zentaji')
        except OSError as exc:assert 'controlled publication failure' in str(exc),exc
        else:raise AssertionError('publication did not encounter the injected failure')
    finally:build.os.replace=original
    assert failed and attempts==3
    for path,data in before.items():assert path.read_bytes()==data,('rollback changed',path)
    assert build_count.current('zentaji')==number
    print('PASS real counted compile/publication fault: six prior artifacts, board identity and ledger restored byte-for-byte; successful build%d remains published'%number)


if __name__=='__main__':main()
