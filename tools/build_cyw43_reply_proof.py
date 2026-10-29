"""Build a physical CPU proof of bounded CYW43 replies and the real iovar branch."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

CASES=[(0,4,0,0),(0,4,0xffffffff,0),(1,4,0x80000000,0),(2044,4,0x7fffffff,0),(10,7,0x78563412,0),(0,3,0xdeadbeef,0),(0,0,0xdeadbeef,0),(0,-1,0,0),(2045,4,0,0),(-1,4,0,0),(2044,5,0,0),(0,2049,0,0),(0x7fffffffffffffff,4,0,0),(0,0x7fffffffffffffff,0,0),(0,4,0,1)]

def proc(text,name):
    match=re.search(r'(?ms)^Procedure(?:\.i)? '+re.escape(name)+r'\(.*?^EndProcedure',text)
    assert match,name
    return match[0]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
    driver='Anvil/Net/cyw43.pbi';command='Anvil/Core/wifi_cmd.pbi'
    raw=(r/driver).read_text(encoding='utf8');cmd=(r/command).read_text(encoding='utf8')
    rx=re.search(r'(?m)^#CYW43_RXBUF\s*=\s*(\d+)',raw);assert rx and int(rx[1])==2048
    branch=cmd[cmd.index('  If WordIs("iovar")'):cmd.index('  ; rekey [on|off]')]
    branch=branch.replace('PrintDec(', 'ProbeDec(').replace('PrintN(', 'ProbePrintN(').replace('Print(', 'ProbePrint(')
    s='''#CYW43_RXBUF=2048
#CYW43_IO_OK=0
Global Dim cyw43_rx.l[#CYW43_RXBUF/4]
Global cyw43_replyOff.i,cyw43_replyLen.i,cyw43_ioctlStatus.i
Global gWifiUp.i,probeRow.i,probeText.i,probeLen.i,probeRc.i,probeName.i
'''
    for name in ['cyw43_RxLE32','cyw43_Signed32','Cyw43IoctlStatus','Cyw43ReplyI32']:s+=proc(raw,name)+'\n'
    s+='''Procedure.i WordIs(*word) : ProcedureReturn 1 : EndProcedure
Procedure.i ArgWord() : ProcedureReturn probeName : EndProcedure
Procedure ProbePrint(*text)
 Define i.i
 ; Output may service the network and reuse the borrowed control-reply buffer.
 cyw43_replyLen=0 : cyw43_ioctlStatus=0 : PokeL(@cyw43_rx[0],$12345678)
 i=0
 While PeekA(*text+i)<>0 And probeLen<380
  PokeA(probeText+probeLen,PeekA(*text+i)) : probeLen=probeLen+1 : i=i+1
 Wend
 PokeA(probeText+probeLen,0)
EndProcedure
Procedure ProbePrintN(*text)
 ProbePrint(*text)
 If probeLen<380 : PokeA(probeText+probeLen,10) : probeLen=probeLen+1 : EndIf
 PokeA(probeText+probeLen,0)
EndProcedure
Procedure str_print_at(*text) : ProbePrint(*text) : EndProcedure
Procedure ProbeDec(value.i)
 Define count.i
 count=PeekI(probeRow+8)
 If count<2 : PokeI(probeRow+16+count*8,value) : EndIf
 PokeI(probeRow+8,count+1)
EndProcedure
Procedure.i Cyw43GetIovarData(src.i,namelen.i,buflen.i,timeoutMs.i)
 PokeI(probeRow,PeekI(probeRow)+1)
 PokeI(probeRow+32,namelen) : PokeI(probeRow+40,buflen) : PokeI(probeRow+48,timeoutMs)
 ProcedureReturn probeRc
EndProcedure
Procedure ProbeCommand()
 Define k.i,n.i,r.i,v.i,replyStatus.i,replyValueOk.i
'''+branch+'''EndProcedure
Procedure DirectRow(index.i,off.i,length.i,word.i,nullOut.i)
 Define base.i,i.i,out.i
 base=$E1C00100+index*32
 For i=0 To #CYW43_RXBUF-1 : PokeA(@cyw43_rx[0]+i,$E7) : Next
 If off>=0 And off<=#CYW43_RXBUF-4
  For i=0 To 3 : PokeA(@cyw43_rx[0]+off+i,(word>>(8*i)) & $FF) : Next
 EndIf
 cyw43_replyOff=off : cyw43_replyLen=length
 out=base+8 : If nullOut<>0 : out=0 : EndIf
 PokeI(base,Cyw43ReplyI32(out))
 If index % 3=0 : cyw43_ioctlStatus=$FFFFFFFC
 ElseIf index % 3=1 : cyw43_ioctlStatus=$80000000
 Else : cyw43_ioctlStatus=7 : EndIf
 PokeI(base+16,Cyw43IoctlStatus())
EndProcedure
Procedure CommandRow(index.i,length.i,rc.i,up.i,name.i)
 Define i.i
 probeRow=$E1C00400+index*512 : probeText=probeRow+64 : probeLen=0
 For i=0 To 55 : PokeA(probeRow+i,0) : Next
 PokeA(probeText,0)
 cyw43_replyOff=0 : cyw43_replyLen=length : cyw43_ioctlStatus=$FFFFFFFC
 PokeL(@cyw43_rx[0],$FFFFFFFF)
 probeRc=rc : gWifiUp=up : probeName=name
 ProbeCommand()
EndProcedure
Procedure.i Main(services.i)
 Define i.i
 For i=0 To 4095 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$43595231) : PokeI($E1C00008,15) : PokeI($E1C00010,5)
'''
    for i,case in enumerate(CASES):s+=f' DirectRow({i},'+','.join(str(v) for v in case)+')\n'
    s+=''' CommandRow(0,4,0,1,"bcn_timeout")
 CommandRow(1,3,0,1,"bcn_timeout")
 CommandRow(2,4,-123,1,"bcn_timeout")
 CommandRow(3,4,0,0,"bcn_timeout")
 CommandRow(4,4,0,1,0)
 ProcedureReturn 0
EndProcedure
'''
    source=d/'proof.pi4';source.write_text(s,encoding='utf8');c=resolve_compiler(a.compiler)
    q=subprocess.run([str(c),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1700:]);assert q.returncode==0
    code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);assert code and bss
    ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c00fff']}
    for name,pair in ranges.items():assert int(pair[0],16)<=int(pair[1],16),name
    p=d/'proof.img.pmf'
    (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in [driver,command]}),indent=2),encoding='utf8')
if __name__=='__main__':main()
