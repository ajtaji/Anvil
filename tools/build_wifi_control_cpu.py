"""Build a physical CPU test of control dispatch without operating the radio."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
from pmf_compiler import resolve_compiler

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compiler',required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();r=Path(__file__).resolve().parents[1];d=a.out.resolve()
    d.mkdir(parents=True,exist_ok=False)
    names=['Anvil/Services/wifi_control.pbi','RaspberryPi4/Board/wifi_control_service.pi4']
    service,adapter=[(r/n).read_text(encoding='utf8') for n in names]
    s=service+'''\nGlobal calls.i,seen.i,arg1.i,arg2.i
Procedure Observe(op.i,a.i,b.i)
 calls=calls+1 : seen=op : arg1=a : arg2=b
EndProcedure
Procedure WifiEpManualBegin(a.i) : Observe(1,a,0) : EndProcedure
Procedure WifiEpManualFailed(a.i,b.i) : Observe(2,a,b) : EndProcedure
Procedure WifiEpisodeRecovered() : Observe(3,0,0) : EndProcedure
Procedure WifiDeaf(a.i,b.i) : Observe(4,a,b) : EndProcedure
Procedure.i WifiRekeyAsk(a.i) : Observe(5,a,0) : ProcedureReturn -77 : EndProcedure
'''
    s+='\n'.join(x for x in adapter.splitlines() if not x.startswith('XIncludeFile') and not x.startswith('WifiControlBind('))+'\n'
    s+='''Procedure Record(index.i,op.i,a.i,b.i)
 Define rc.i,p.i
 calls=0 : seen=0 : arg1=0 : arg2=0
 rc=WifiControlCall(op,a,b) : p=$E1C00100+index*48
 PokeI(p,rc) : PokeI(p+8,calls) : PokeI(p+16,seen)
 PokeI(p+24,arg1) : PokeI(p+32,arg2) : PokeI(p+40,WifiControlAvailable())
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 16383 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$57464331)
 WifiControlBind(0) : Record(0,1,2,0)
 WifiControlBind(@HwWifiControlDispatch)
'''
    cases=[(1,1,0),(1,2,0),(2,1,1),(2,2,2),(3,0,0),(4,1,0),(4,600,1),(5,0,0),(5,1,0),(0,0,0),(6,0,0),(1,0,0),(1,3,0),(2,1,0),(2,2,3),(4,0,0),(4,601,0),(4,1,-1),(4,1,2),(5,-1,0),(5,2,0)]
    for i,(op,x,y) in enumerate(cases,1):s+=f' Record({i},{op},{x},{y})\n'
    s+=f' WifiControlBind(0) : Record({len(cases)+1},5,0,0)\n PokeI($E1C00008,{len(cases)+2})\n ProcedureReturn 0\nEndProcedure\n'
    source=d/'proof.pi4';source.write_text(s,encoding='utf8')
    c=resolve_compiler(a.compiler)
    q=subprocess.run([str(c),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c03fff']}
    p=d/'proof.img.pmf'
    (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names}),indent=2),encoding='utf8')
if __name__=='__main__':main()
