"""Check multicast controls through real CYW43 iovar serialization on Pi."""
from pathlib import Path
import argparse,hashlib,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Net/cyw43_multicast.pbi','Anvil/Net/cyw43.pbi','RaspberryPi4/Lib/mmu.pi4']
 raw=(root/names[1]).read_text()
 def proc(n):
  m=re.search(r'^Procedure(?:\.i)? '+n+r'\([^\n]*\n.*?^EndProcedure',raw,re.M|re.S);assert m,n
  return m.group()+'\n'
 cases=[];steps=[];vectors=[]
 def vec(b):vectors.append(b);return '?V'+str(len(vectors)-1)
 def add(name,code,rc,wire=b'',output=None,kind=0,ms=0):
  cases.append(dict(name=name,rc=rc,wire=wire.hex(),output=(output if output is not None else b'\xa5'*174).hex(),kind=kind,ms=ms));steps.append(code)
 macs=[bytes([0x33,0x33,0,0,0,i+1]) for i in range(30)]
 def setcase(name,b,count,expected=0,ms=100,pointer=None):
  p=pointer or vec(b or b'\0')
  add(name,f'rc=Cyw43MulticastSet({p},{count},{ms})',expected,b'mcast_list\0'+struct.pack('<I',count)+b if expected==0 else b'',kind=263 if expected==0 else 0,ms=ms if expected==0 else 0)
 for count in [0,1,2,29]:setcase('set count '+str(count),b''.join(macs[:count]),count)
 setcase('clear null',b'',0,pointer='0')
 for name,b,count,ms,p in [('too many',b''.join(macs),30,100,None),('negative count',b'',-1,100,None),('null list',b'',1,100,'0'),('unicast',bytes.fromhex('020102030405'),1,100,None),('broadcast',bytes([255])*6,1,100,None),('duplicate',macs[0]*2,2,100,None),('zero timeout',macs[0],1,0,None),('long timeout',macs[0],1,101,None)]:
  setcase(name,b,count,-790,ms,p)
 wire=b'mcast_list\0'+struct.pack('<I',1)+macs[0]
 for err in [-1,-3,-6,-7,-8]:add('set driver result '+str(err),f'fakeRc={err}\n rc=Cyw43MulticastSet({vec(macs[0])},1,25)',err,wire,kind=263,ms=25)
 def getcase(name,b,cap=29,rc=None,off=0,length=None,result=0,pointer='@output[0]',ms=50):
  if length is None:length=len(b)
  before='For i=0 To 2047 : PokeA(@cyw43_rx[0]+i,0) : Next\n'
  if 0<=off<=2048-len(b):before+=f'For i=0 To {len(b)-1} : PokeA(@cyw43_rx[0]+{off}+i,PeekA({vec(b)}+i)) : Next\n'
  before+=f'cyw43_replyOff={off} : cyw43_replyLen={length} : fakeRc={result}\n rc=Cyw43MulticastGet({pointer},{cap},{ms})'
  if rc is None:rc=int.from_bytes(b[:4],'little')
  requested=not (cap<1 or cap>29 or pointer!='@output[0]' or ms<1 or ms>100)
  o=b[4:4+rc*6]+b'\xa5'*(174-rc*6) if rc>=0 else None
  add(name,before,rc,b'mcast_list\0'+bytes(167) if requested else b'',o,262 if requested else 0,ms if requested else 0)
 for count in [0,1,29]:getcase('get count '+str(count),struct.pack('<I',count)+b''.join(macs[:count]),off=3)
 getcase('get short header',b'\1\0\0',rc=-791)
 getcase('get truncated list',struct.pack('<I',2)+macs[0],rc=-791)
 getcase('get too many',struct.pack('<I',30)+b''.join(macs),rc=-791)
 getcase('get output too small',struct.pack('<I',2)+b''.join(macs[:2]),cap=1,rc=-791)
 getcase('get unicast',struct.pack('<I',1)+bytes.fromhex('020102030405'),rc=-791)
 getcase('get duplicate',struct.pack('<I',2)+macs[0]*2,rc=-791)
 getcase('get upper count bits',bytes([255])*4,rc=-791)
 getcase('get negative offset',bytes(4),off=-1,rc=-791)
 getcase('get exceeds receive buffer',bytes(4),off=2046,length=4,rc=-791)
 getcase('get negative length',bytes(4),length=-1,rc=-791)
 getcase('get null output',bytes(4),pointer='0',rc=-790)
 getcase('get RX alias',bytes(4),pointer='@cyw43_rx[0]',rc=-790)
 getcase('get argument alias',bytes(4),pointer='@cyw43_arg[0]',rc=-790)
 getcase('get excessive capacity',bytes(4),cap=30,rc=-790)
 getcase('get zero capacity',bytes(4),cap=0,rc=-790)
 getcase('get timeout refused',bytes(4),ms=101,rc=-790)
 for err in [-1,-3,-6]:getcase('get driver error '+str(err),bytes(4),result=err,rc=err)
 for enabled in [0,1]:
  add('neighbor offload '+str(enabled),f'rc=Cyw43NeighborOffload({enabled},100)',0,b'ndoe\0'+struct.pack('<I',enabled),kind=263,ms=100)
 add('neighbor offload invalid','rc=Cyw43NeighborOffload(2,100)',-790)
 add('neighbor offload timeout','rc=Cyw43NeighborOffload(0,0)',-790)
 add('neighbor offload failure','fakeRc=-3\n rc=Cyw43NeighborOffload(0,100)',-3,b'ndoe\0'+bytes(4),kind=263,ms=100)
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\n'+r'''
#CYW43_RXBUF=2048
#CYW43_ARGBUF=192
#CYW43_C_GET_VAR=262
#CYW43_C_SET_VAR=263
#CYW43_IO_TOOBIG=-2
Global Dim cyw43_rx.l[512]
Global Dim cyw43_arg.l[48]
Global cyw43_replyOff.i,cyw43_replyLen.i
Global Dim output.a[174]
Global Dim captured.a[192]
Global capturedBytes.i,capturedKind.i,capturedMs.i,fakeRc.i
Procedure.i Capture(cmd.i,p.i,n.i,ms.i)
 Define i.i
 capturedBytes=n : capturedKind=cmd : capturedMs=ms
 If n>192 : ProcedureReturn -999 : EndIf
 For i=0 To n-1 : captured[i]=PeekA(p+i) : Next
 ProcedureReturn fakeRc
EndProcedure
Procedure.i Cyw43IoctlSet(cmd.i,p.i,n.i,ms.i)
 ProcedureReturn Capture(cmd,p,n,ms)
EndProcedure
Procedure.i Cyw43IoctlGet(cmd.i,p.i,n.i,ms.i)
 ProcedureReturn Capture(cmd,p,n,ms)
EndProcedure
'''
 for name in ['cyw43_PutLE32','cyw43_PutName','Cyw43ReplyPtr','Cyw43ReplyLen','Cyw43SetIovarU32','Cyw43SetIovarData','Cyw43GetIovarData']:s+=proc(name)
 s+='XIncludeFile "Anvil/Net/cyw43_multicast.pbi"\n'+r'''
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*512
 PokeI(p,rc) : PokeI(p+8,capturedKind) : PokeI(p+16,capturedBytes) : PokeI(p+24,capturedMs)
 For i=0 To 191 : PokeA(p+32+i,captured[i]) : Next
 For i=0 To 173 : PokeA(p+224+i,output[i]) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 131071 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$4D434334)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):s+=' For i=0 To 173 : output[i]=$A5 : Next\n For i=0 To 191 : captured[i]=0 : Next\n capturedBytes=0 : capturedKind=0 : capturedMs=0 : fakeRc=0\n'+code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for k,b in enumerate(vectors):
  s+=f'V{k}:\n'
  for i in range(0,len(b),24):s+=' Data.a '+','.join(str(v) for v in b[i:i+24])+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
