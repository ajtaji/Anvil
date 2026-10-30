"""Compile HTTP/2 frame boundary tests for physical execution."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def cases():
 rows=[]
 def add(n,k,f,stream,error=0,maximum=16384,reserved=False):
  wire=n.to_bytes(3,'big')+bytes([k,f])+(stream|(0x80000000 if reserved else 0)).to_bytes(4,'big')
  rows.append(dict(length=n,kind=k,flags=f,stream=stream,error=error,maximum=maximum,wire=wire.hex(),write_error=(0 if n>maximum else error)))
 add(0,0,1,1);add(0,0,8,1,-3203);add(1,0,8,1);add(0,0,0,0,-3202)
 add(0,1,4,1);add(5,1,32,1);add(4,1,32,1,-3203);add(5,1,40,1,-3203);add(6,1,40,1)
 add(5,2,0,1);add(4,2,0,1,-3203);add(5,2,0,0,-3202)
 add(4,3,0,1);add(5,3,0,1,-3203)
 add(0,4,1,0);add(6,4,1,0,-3203);add(5,4,0,0,-3203);add(12,4,128,0);add(0,4,0,1,-3202)
 add(4,5,0,1);add(3,5,0,1,-3203);add(4,5,8,1,-3203);add(5,5,8,1)
 add(8,6,0,0);add(9,6,0,0,-3203);add(8,6,0,1,-3202)
 add(8,7,0,0);add(7,7,0,0,-3203)
 add(4,8,0,0);add(4,8,0,1);add(0,8,0,0,-3203)
 add(0,9,4,1);add(0,9,4,0,-3202)
 add(0,255,255,0);add(16384,251,128,0x7fffffff,reserved=True)
 add(16384,0,0,1);add(16385,0,0,1,-3203);add(0xffffff,255,0,1,maximum=0xffffff)
 return rows

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/h2_frame.pbi','Anvil/Network/byte_order.pbi'];rows=cases()
 s='XIncludeFile "Anvil/Network/h2_frame.pbi"\n'+r'''
Global h.H2FrameHeader
Global Dim input.a[13]
Global Dim output.a[32]
Procedure Run(index.i,maximum.i)
 Define split.i,p.i,rc.i,i.i
 For split=0 To 9
  p=$E1C00100+index*800+split*80
  rc=H2FrameInit(@h,maximum)
  PokeI(p,H2FrameFeed(@h,@input[0],split))
  PokeI(p+8,H2FrameFeed(@h,@input[split],13-split))
  PokeI(p+16,H2FrameFeed(@h,@input[9],4))
  PokeI(p+24,h\used) : PokeI(p+32,h\length) : PokeI(p+40,h\kind)
  PokeI(p+48,h\flags) : PokeI(p+56,h\stream) : PokeI(p+64,h\error)
 Next
 For i=0 To 31 : output[i]=$A5 : Next
 rc=H2FrameWrite(@output[0],9,h\length,h\kind,h\flags,h\stream)
 p=$E1C0C000+index*32
 PokeI(p,rc)
 For i=0 To 15 : PokeA(p+8+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$48324631)
 For i=0 To 12 : input[i]=$A5 : Next
'''
 for index,c in enumerate(rows):
  for i,v in enumerate(bytes.fromhex(c['wire'])):s+=f'input[{i}]={v}\n'
  s+=f'Run({index},{c["maximum"]})\n'
 s+=r'''
 For i=0 To 31 : output[i]=$A5 : Next
 PokeI($E1C00008,H2ClientPreface(@output[0],23))
 PokeI($E1C00010,output[0]) : PokeI($E1C00018,H2ClientPreface(@output[0],24))
 For i=0 To 31 : PokeA($E1C00080+i,output[i]) : Next
 PokeI($E1C00020,H2FrameInit(@h,16383))
 PokeI($E1C00028,H2FrameFeed(@h,@input[0],9))
 rc=H2FrameInit(@h,16384)
 PokeI($E1C00030,H2FrameFeed(@h,0,1))
 For i=0 To 31 : output[i]=$A5 : Next
 PokeI($E1C00038,H2FrameWrite(@output[0],8,0,4,0,0))
 PokeI($E1C00040,output[0])
 PokeI($E1C00048,H2FrameWrite(@output[0],9,0,4,0,-1))
 PokeI($E1C00050,output[0])
 ProcedureReturn 0
EndProcedure
'''
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=rows),indent=2),encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();build(a.compiler,a.out.resolve())
