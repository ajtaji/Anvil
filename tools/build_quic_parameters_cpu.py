"""Build physical QUIC transport-parameter validation; no emulator."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from quic_parameter_cases import cases
def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 rows=cases();assert len(rows)<=113
 names=['Anvil/Network/quic_parameters.pbi','Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi']
 s='XIncludeFile "Anvil/Network/quic_parameters.pbi"\n'+r'''
Global job.QuicParameters
Global Dim wire.a[2048]
Global Dim original.a[2048]
Global Dim entries.a[2064]
Global Dim ids.a[60]
Global table.i,*pet,*clock
Procedure CaptureTable()
 ASM
 adrp x1, global_table
 add x1, x1, #:lo12:global_table
 str x0, [x1]
 EndASM
EndProcedure
Procedure Run(index.i,n.i,server.i,capacity.i,cancel.i,alias.i,initialN.i,originalN.i,retryN.i,usedRetry.i)
 Define i.i,p.i,rc.i,steps.i,guard.i,changed.i,visible.i,idsrc.i,t.i,cost.i,maxStep.i,src.i
 p=$E1C00100+index*2304
 For i=0 To 2047 : wire[i]=$A5 : original[i]=$A5 : Next
 For i=0 To 2063 : entries[i]=$A5 : Next
 For i=0 To SizeOf(QuicParameters)-1 : PokeA(@job+i,0) : Next
 For i=0 To n-1 : Read.a wire[8+i] : original[8+i]=wire[8+i] : Next
 For i=0 To 59 : ids[i]=0 : Next
 For i=0 To initialN-1 : Read.a ids[i] : Next
 For i=0 To originalN-1 : Read.a ids[20+i] : Next
 For i=0 To retryN-1 : Read.a ids[40+i] : Next
 src=@wire[8] : If alias : src=@entries[8] : EndIf
 rc=QuicParametersBegin(@job,src,n,server,@entries[8],capacity)
 While rc=0 And steps<100
  pet() : t=clock() : rc=QuicParametersStep(@job) : cost=clock()-t
  If cost>maxStep : maxStep=cost : EndIf
  steps=steps+1
  If rc=0 And QuicParametersFind(@job,15)<>0 : visible=1 : EndIf
  If cancel And steps=1 : QuicParametersCancel(@job) : rc=QuicParametersStep(@job) : EndIf
 Wend
 idsrc=QuicParametersCheckIds(@job,@ids[0],initialN,@ids[20],originalN,@ids[40],retryN,usedRetry)
 For i=0 To 7
  If wire[i]<>$A5 Or wire[8+n+i]<>$A5 Or entries[i]<>$A5 Or entries[8+capacity*32+i]<>$A5 : guard=guard+1 : EndIf
 Next
 For i=0 To n-1 : If wire[8+i]<>original[8+i] : changed=changed+1 : EndIf : Next
 If rc<>1 And QuicParametersFind(@job,15)<>0 : visible=1 : EndIf
 PokeI(p,rc) : PokeI(p+8,QuicParametersStep(@job)) : PokeI(p+16,job\count) : PokeI(p+24,job\cursor)
 PokeI(p+32,steps) : PokeI(p+40,guard) : PokeI(p+48,changed) : PokeI(p+56,visible) : PokeI(p+64,idsrc) : PokeI(p+72,maxStep)
 For i=0 To 2047 : PokeA(p+256+i,entries[8+i]) : Next
EndProcedure
Procedure.i Main()
 Define i.i
 CaptureTable() : *pet=PeekI(table+16+6*8) : *clock=PeekI(table+16+11*8)
 For i=0 To 262143 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$51545031)
'''
 s+=f' PokeI($E1C00008,{len(rows)})\n'
 for i,c in enumerate(rows):
  args=[i,len(bytes.fromhex(c['wire'])),c['server'],c['capacity'],c['cancel'],c['alias']]+[len(bytes.fromhex(c[k])) for k in ('initial','original','retry')]+[c['used_retry']]
  s+=f' Restore Case{i}\n Run('+','.join(map(str,args))+')\n'
 s+=' ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for i,c in enumerate(rows):s+=f'Case{i}:\n Data.a '+','.join(map(str,bytes.fromhex(c['wire']+c['initial']+c['original']+c['retry']) or b'\0'))+'\n'
 s+='EndDataSection\n';src=out/'proof.pi4';src.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(src),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1400:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes()
 ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c3ffff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},checked_ranges=ranges,cases=rows),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);p.add_argument('--out',required=True,type=Path);a=p.parse_args();build(a.compiler,a.out.resolve())
