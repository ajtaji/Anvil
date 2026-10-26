#!/usr/bin/env python3
"""Compare the physical guard report with the actual linked storage extent."""
from pathlib import Path
import argparse,json,struct

def read_symbols(text):
    result={}
    for line in text.splitlines():
        if '=' in line:
            a,b=line.split('=',1)
            try:result[a.strip().lower()]=int(b)
            except ValueError:pass
    return result

def verify(report,container,symbol_text):
    assert len(report)==256 and len(container)>=128, 'Incomplete report or PMF container.'
    symbols=read_symbols(symbol_text)
    for name in ['__bss_start__','__bss_end__','__noclear_end__','global_mapproofpad','global_mapproofkeep']:
        assert name in symbols, 'Missing linked symbol '+name
    base,size=struct.unpack_from('<2Q',container,40)
    end=symbols['__noclear_end__'];zero_end=symbols['__bss_end__']
    assert base==symbols['__bss_start__']==0x02000000 and base+size==end, 'PMF and linker extent disagree.'
    expected_hi=max(0x02ffffff,((end+0xfffff)//0x100000)*0x100000-1)
    q=struct.unpack_from('<9q',report)
    assert q==(0x3150414d,end,expected_hi,symbols['global_mapproofpad'],symbols['global_mapproofkeep'],base,expected_hi,9,1), 'Native map or guard checks disagree.'
    assert base<=q[3]<zero_end<=q[4]<end, 'The test does not span ordinary and preserved storage.'
    return dict(native_guard_checks=9,linked_end=end,reserved_hi=expected_hi,preserved_storage_included=True,pmf_matches_linker=True)

def self_test(report,container,symbols):
    variants=[]
    for off in range(0,72,8):
        bad=bytearray(report);bad[off]^=1;variants.append((bad,container,symbols))
    for off in [40,48]:
        bad=bytearray(container);bad[off]^=1;variants.append((report,bad,symbols))
    variants.append((report,container,'\n'.join(x for x in symbols.splitlines() if not x.startswith('__noclear_end__='))))
    variants.append((report[:-1],container,symbols))
    for args in variants:
        try:verify(*args)
        except AssertionError:continue
        raise AssertionError('Corrupted proof accepted.')
    return len(variants)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--container',type=Path,required=True)
    ap.add_argument('--symbols',type=Path,required=True)
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args();report=args.report.read_bytes();container=args.container.read_bytes();symbols=args.symbols.read_text()
    result=verify(report,container,symbols)
    if args.self_test:result['rejected_mutations']=self_test(report,container,symbols)
    print('Pi4 linked variables PASS',json.dumps(result))
