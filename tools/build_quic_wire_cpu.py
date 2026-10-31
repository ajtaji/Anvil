"""Build shared QUIC wire fixtures for physical Anvil targets; no emulator."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler
from quic_wire_cases import cases

def build(compiler,out):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
    rows=cases();assert len(rows)<1000
    names=['Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi']
    s='XIncludeFile "Anvil/Network/quic_wire.pbi"\n'+r'''
Global h.QuicPacketHeader,spec.QuicLongPacketSpec
Global Dim wire.a[2048]
Global Dim output.a[256]
Procedure Run(index.i,op.i,n.i,a.i,b.i,c.i)
 Define i.i,p.i,rc.i,value.i
 p=$E1C00100+index*256
 For i=0 To 255 : output[i]=$A5 : Next
 For i=0 To n-1 : Read.a wire[i] : Next
 value=-777
 Select op
  Case 0 : rc=QuicIntegerRead(@wire[0],n,@value)
  Case 1 : rc=QuicIntegerWrite(a,b,@output[8],c)
  Case 2 : rc=QuicPacketRead(@h,@wire[0],n,a)
  Case 3 : rc=QuicPacketNumberRead(a,b,c,@value)
  Case 4 : rc=QuicLongPacketWrite(@spec,@output[8],a)
  Case 5
   Select a
    Case 0 : rc=QuicIntegerRead(0,1,@value)
    Case 1 : rc=QuicIntegerRead(@wire[0],n,0)
    Case 2 : rc=QuicPacketRead(0,@wire[0],n,0)
    Case 3 : rc=QuicPacketRead(@h,0,1,0)
    Case 4 : rc=QuicIntegerWrite(0,1,0,8)
    Case 5 : rc=QuicPacketNumberRead(0,1,-1,0)
    Case 6 : rc=QuicLongPacketWrite(0,@output[8],128)
    Case 7 : rc=QuicLongPacketWrite(@spec,0,128)
    Case 8 : rc=QuicIntegerRead(@wire[0],-1,@value)
    Case 9 : rc=QuicPacketRead(@h,@wire[0],-1,0)
    Case 10 : rc=QuicPacketRead(@h,@wire[0],n,-1)
   EndSelect
 EndSelect
 PokeI(p,rc) : PokeI(p+8,value)
 If op=2
  For i=0 To SizeOf(QuicPacketHeader)-1 : PokeA(p+16+i,PeekA(@h+i)) : Next
 EndIf
 For i=0 To 127 : PokeA(p+128+i,output[i]) : Next
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 262143 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$51574331)
'''
    s+=f' PokeI($E1C00008,{len(rows)})\n'
    for index,row in enumerate(rows):
        if 'spec' in row:
            for field,value in zip(['kind','destinationBytes','sourceBytes','tokenBytes','number','numberBytes','cipherBytes'],row['spec']):s+=f' spec\\{field}={value}\n'
            s+=' spec\\destination=@wire[0] : spec\\source=@wire[8] : spec\\token=@wire[12]\n'
        args=(row['args']+[0,0,0])[:3]
        s+=f' Restore Case{index}\n Run({index},{row["op"]},{len(bytes.fromhex(row["wire"]))},{args[0]},{args[1]},{args[2]})\n'
    s+=' ProcedureReturn 0\nEndProcedure\nDataSection\n'
    for index,row in enumerate(rows):s+=f'Case{index}:\n Data.a '+','.join(map(str,bytes.fromhex(row['wire']) or b'\0'))+'\n'
    s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s)
    q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1800:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
    payload=(out/'proof.img.pmf').read_bytes()
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c3ffff']}
    (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=rows),indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();build(a.compiler,a.out.resolve())
