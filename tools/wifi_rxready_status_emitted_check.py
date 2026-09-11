#!/usr/bin/env python3
"""Compile and execute the focused Wi-Fi rxready status/delta gate."""
from __future__ import annotations
import argparse, os, re, shutil, sys, tempfile
from pathlib import Path
import tcp_multiif_emitted_check as emitted

ROOT=Path(__file__).resolve().parents[1]
WIFI=ROOT/'RaspberryPi4/Lib/wifi.pi4'
CMD=ROOT/'Anvil/Core/wifi_cmd.pbi'
FIX=ROOT/'RaspberryPi4/Tests/wifi_rxready_status_emitted_gate.pi4'

def proc(src,name):
    one=re.search(rf'(?m)^Procedure(?:\.i)? {re.escape(name)}\([^\n]*EndProcedure\s*$',src)
    if one: return one.group(0)
    m=re.search(rf'(?ms)^Procedure(?:\.i)? {re.escape(name)}\([^\n]*\).*?^EndProcedure\s*$',src)
    if not m: raise SystemExit(f'rxready status gate: missing procedure {name}')
    return m.group(0)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--pmfc',default=os.environ.get('PMFC')); ap.add_argument('--interp',default=os.environ.get('PMF_A64_INTERP')); a=ap.parse_args()
    pmfc=emitted.required_path(a.pmfc,'PMFC'); interp=emitted.required_path(a.interp,'PMF_A64_INTERP'); a64=emitted.load_interpreter(interp)
    ws=WIFI.read_text(encoding='utf-8'); cs=CMD.read_text(encoding='utf-8'); out=FIX.read_text(encoding='utf-8')
    gl='\n'.join(x for x in ws.splitlines() if x.startswith('Global gWifiRxReady'))+'\nGlobal gWifiRinitGeneration.i'
    names=('WifiRxReadyActive','WifiRxReadyGeneration','WifiRxReadyGenerationValid','WifiRxReadyElapsed','WifiRxReadyRawDelta','WifiRxReadyFrameDelta','WifiRxReadyEmptyDelta','WifiRxReadyFirstDelta','WifiRxReadyCmd53Delta','WifiRxReadyFirstPendingDelta','WifiRxReadyFirstQuietDelta','WifiRxReadyNonPendingDelta','WifiRxReadyNonQuietDelta','WifiRxReadyEmptyPendingDelta','WifiRxReadyEmptyQuietDelta')
    names += ('WifiRxReadyInheritedDelta','WifiRxReadyNewDelta','WifiRxReadyQDataDelta','WifiRxReadyQControlDelta','WifiRxReadyQEventDelta','WifiRxReadyQGlomDelta','WifiRxReadyQUnknownDelta','WifiRxReadyQMalformedDelta','WifiRxReadyQPrevNextDelta','WifiRxReadyQSeqOkDelta','WifiRxReadyQSeqGapDelta','WifiRxReadyQPostPendingDelta','WifiRxReadyQPostQuietDelta','WifiRxReadyQPostFailDelta')
    helpers='\n'.join(proc(ws,n) for n in names)
    status=proc(cs,'WifiRxReadyStatus').replace('PrintN(','GatePrintN(').replace('Print(','GatePrint(')
    out=out.replace('; @@GLOBALS@@',gl).replace('; @@HELPERS@@',helpers).replace('; @@STATUS@@',status)
    with tempfile.TemporaryDirectory(prefix='anvil-rxready-status-') as td:
        image=emitted.build(pmfc,Path(td),mutation='') if False else None
        src=Path(td)/'gate.pi4'; src.write_text(out,encoding='utf-8'); staged=Path(td)/pmfc.name; shutil.copy2(pmfc,staged)
        import subprocess
        img=Path(td)/'gate.img'; env=os.environ.copy(); env['PMF_ROOT']=str(ROOT)
        r=subprocess.run([str(staged),str(src),'-t','pi4','--load-addr',hex(emitted.LOAD),'--stack-addr',hex(emitted.STACK),'--entry-returns','-o',str(img),'-s'],cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if r.returncode or 'pmfc: OK' not in r.stdout: raise SystemExit('rxready status gate: compile failed\n'+r.stdout)
        result,steps=emitted.execute(a64,img)
    if result: print(f'wifi_rxready_status_emitted_check: FAIL assertion {result} after {steps:,} instructions'); return 1
    print(f'wifi_rxready_status_emitted_check: PASS - off/pending/current/mismatch and 20 session delta cells, {steps:,} instructions'); return 0
if __name__=='__main__': sys.exit(main())
