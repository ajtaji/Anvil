"""Physical mixed-family socket regression, production TCP with scripted links."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/tcp.pbi','Anvil/Network/net.pbi','Anvil/Network/ipv6_tcp.pbi','Anvil/Network/ipv6_packet.pbi','RaspberryPi4/Tests/tcp_multiif_emitted_gate.pi4','RaspberryPi4/Tests/tcp_ipv6_socket_gate.pi4','RaspberryPi4/Lib/mmu.pi4']
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'+(root/names[4]).read_text().replace('Procedure.i Main()','Procedure.i FourGate()')
 s+='\n'+(root/names[5]).read_text()+'''
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$534F434B)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
 rc=FourGate() : PokeI($E1C00008,rc)
 If rc=0 : rc=SixGate() : PokeI($E1C00010,rc) : EndIf
 MmuDisableCachedFlushed()
 ProcedureReturn 0
EndProcedure
'''
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2500:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=['IPv4 multi-interface regression','IPv6 active/passive/socket ownership']),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
