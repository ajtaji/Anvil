"""Build a returning physical-CPU proof of Wi-Fi maintenance and payload service order."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    fixture='RaspberryPi4/Tests/payload_net_emitted_gate.pi4'
    s=(r/fixture).read_text(encoding='utf8')
    assert s.count('Procedure.i Main()')==1
    s=s.replace('Procedure.i Main()','Procedure.i PayloadServiceProof()')
    s+='''
Global proofTrace.i
Procedure.i ProofProvider(operation.i)
 proofTrace=proofTrace*10+operation
 ProcedureReturn -73
EndProcedure
Procedure.i ProofReplacement(operation.i)
 proofTrace=proofTrace*10+operation+10
 ProcedureReturn 99
EndProcedure
Procedure.i Main(services.i)
 Define i.i,result.i
 For i=0 To 4095 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$574D3136)
 WifiMaintenanceBind(0)
 WifiMaintenanceTick() : WifiMaintenanceCheckNow()
 PokeI($E1C00008,gate_linkTicks) : PokeI($E1C00010,gate_checkNow)
 WifiMaintenanceBind(@ProofProvider)
 WifiMaintenanceTick() : WifiMaintenanceCheckNow()
 PokeI($E1C00018,proofTrace)
 WifiMaintenanceBind(@HwWifiMaintenanceDispatch)
 UartMessageBegin() : WifiMaintenanceTick() : WifiMaintenanceCheckNow() : UartMessageEnd()
 PokeI($E1C00020,gate_linkTicks) : PokeI($E1C00028,gate_checkNow)
 PokeI($E1C00030,gate_order) : PokeI($E1C00038,gate_outside)
 HwWifiMaintenanceDispatch(0) : HwWifiMaintenanceDispatch(3)
 PokeI($E1C00040,gate_linkTicks) : PokeI($E1C00048,gate_checkNow)
 WifiMaintenanceBind(0) : WifiMaintenanceTick() : WifiMaintenanceCheckNow()
 PokeI($E1C00050,gate_linkTicks) : PokeI($E1C00058,gate_checkNow)
 proofTrace=0 : WifiMaintenanceBind(@ProofReplacement)
 WifiMaintenanceTick() : WifiMaintenanceCheckNow()
 PokeI($E1C00060,proofTrace)
 WifiMaintenanceBind(@HwWifiMaintenanceDispatch)
 gate_linkTicks=0 : gate_checkNow=0 : gate_order=0 : gate_outside=0
 result=PayloadServiceProof()
 PokeI($E1C00068,result)
 PokeI($E1C00070,gate_outside) : PokeI($E1C00078,gate_msgDepth)
 ProcedureReturn result
EndProcedure
'''
    load,stack,report=0x1000000,0x4f00000,0xe1c00000
    source=d/'proof.pi4';source.write_text(s,encoding='utf8')
    inputs={fixture:hashlib.sha256((r/fixture).read_bytes()).hexdigest()};pending=[s]
    while pending:
        for n in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',pending.pop()):
            if n in inputs:continue
            assert len(inputs)<128
            raw=(r/n).read_bytes();inputs[n]=hashlib.sha256(raw).hexdigest();pending.append(raw.decode('utf-8-sig'))
    c=resolve_compiler(a.compiler)
    q=subprocess.run([str(c),'--compile',str(source),'-t','pi4','--load-addr',hex(load),'--stack-addr',hex(stack),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':[hex(stack-0x100000),hex(stack-1)],'report':[hex(report),hex(report+4095)]}
    intervals=[(n,*(int(x,16) for x in pair)) for n,pair in ranges.items()]
    for i,(n,x,y) in enumerate(intervals):
        for other,u,v in intervals[i+1:]:assert y<u or v<x,(n,other)
    p=d/'proof.img.pmf'
    (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=inputs),indent=2),encoding='utf8')
if __name__=='__main__':main()
