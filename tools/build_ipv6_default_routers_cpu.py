'''Build physical default-router table and next-hop policy qualification.'''
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_default_routers.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[];steps=[];state=[1,0,1,0,0];rows=[(0,0,0)]*3
 def wire():
  b=b''
  for n,t,p in rows:b+=(ipaddress.IPv6Address('fe80::'+str(n)).packed if n else bytes(16))+struct.pack('<2q',t,p)
  return b
 def add(name,code,rc,new=None,change=None,reset=False):
  nonlocal state,rows
  if new is not None:state=new
  if reset:rows=[(0,0,0)]*3
  if change:
   for i,v in change.items():rows[i]=v
  cases.append(dict(name=name,expected=[rc]+state,rows=wire().hex()));steps.append(code)
 def app(n,t,life,flags=0,g=1):return f'rc=IPv6DefaultRoutersApply(@ctx,{g},{t},?R{n},{life},{flags})'
 def select(t,mask=0,g=1):return f'rc=IPv6DefaultRoutersSelect(@ctx,{g},{t},{mask})'
 def tick(t,g=1):return f'rc=IPv6DefaultRoutersTick(@ctx,{g},{t})'
 add('initialize three slots','rc=IPv6DefaultRoutersInit(@ctx,1,@rows[0],3,0)',0)
 add('first router',app(1,0,10),0,[1,0,2,0,0],{0:(1,10000,0)})
 add('second high preference router',app(2,1,20,8),0,[1,1,3,0,0],{1:(2,20001,1)})
 add('high preference selected',select(2),2,[1,2,3,2,0])
 add('reachable beats failed high preference',select(3,2),1,[1,3,3,1,2])
 add('third low preference',app(3,4,30,24),0,[1,4,4,1,0],{2:(3,30004,-1)})
 add('full table retains existing routers',app(4,5,10,8),1,[1,5,4,1,0])
 add('refresh does not invalidate unchanged next hop',app(1,6,100),0,[1,6,4,1,0],{0:(1,100006,0)})
 add('reserved preference becomes medium',app(2,7,20,16),0,[1,7,5,1,0],{1:(2,20007,0)})
 add('equal preference rotates first',select(8),2,[1,8,5,2,0])
 add('equal preference rotates second',select(9),1,[1,9,5,1,0])
 add('withdraw one router',app(2,10,0),0,[1,10,6,1,0],{1:(2,0,0)})
 add('remaining reachable low router selected',select(11,1),3,[1,11,6,0,1])
 add('unknown withdrawal preserves others',app(4,12,0),0,[1,12,6,0,0])
 add('free slot reused',app(4,13,4,8),0,[1,13,7,0,0],{1:(4,4013,1)})
 add('exact expiry invalidates cached routes',tick(4013),1,[1,4013,8,0,0],{1:(4,0,1)})
 add('shorten independent lifetime',app(3,4014,1,24),0,[1,4014,8,0,0],{2:(3,5014,-1)})
 add('second independent expiry',tick(5014),1,[1,5014,9,0,0],{2:(3,0,-1)})
 add('last router expiry',tick(100006),1,[1,100006,10,0,0],{0:(1,0,0)})
 add('no default route',select(100007),0,[1,100007,10,0,0])
 add('new generation resets table','rc=IPv6DefaultRoutersInit(@ctx,2,@rows[0],3,0)',0,[2,0,1,0,0],reset=True)
 add('stale generation refuses',app(1,0,1,g=1),-841)
 add('at least two slots required','rc=IPv6DefaultRoutersInit(@ctx,3,@rows[0],1,0)',-840)
 add('backwards time refuses',tick(-1,2),-840)
 add('oversized time refuses',tick(9223372036854775807,2),-840)
 add('source overlap refuses','rc=IPv6DefaultRoutersApply(@ctx,2,0,@rows[0],1,0)',-840)
 add('nonlinklocal source refuses','rc=IPv6DefaultRoutersApply(@ctx,2,0,?GlobalAddr,1,0)',-840)
 add('lifetime width refuses',app(1,0,65536,g=2),-840)
 add('flag width refuses',app(1,0,1,256,2),-840)
 add('invalid failure mask refuses',select(0,8,2),-840)
 add('two slot composition','rc=IPv6DefaultRoutersInit(@ctx,3,@rows[0],2,0)',0,[3,0,1,0,0],reset=True)
 add('maximum lifetime',app(1,0,65535,g=3),0,[3,0,2,0,0],{0:(1,65535000,0)})
 add('before maximum expiry',tick(65534999,3),0,[3,65534999,2,0,0])
 add('at maximum expiry',tick(65535000,3),1,[3,65535000,3,0,0],{0:(1,0,0)})
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_address.pbi"\nXIncludeFile "Anvil/Network/ipv6_default_routers.pbi"\n'+r'''
Global ctx.IPv6DefaultRouters
Global Dim rows.a[112]
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*256
 PokeI(p,rc) : PokeI(p+8,ctx\generation) : PokeI(p+16,ctx\lastNow)
 PokeI(p+24,ctx\revision) : PokeI(p+32,ctx\cursor) : PokeI(p+40,ctx\probeMask)
 For i=0 To 111 : PokeA(p+48+i,rows[i]) : Next
EndProcedure
Procedure.i Main()
 Define rc.i,i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 For i=0 To 111 : rows[i]=$A5 : Next
 PokeI($E1C00000,$44525442)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 for k,code in enumerate(steps):s+=code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for name,ip in [(f'R{i}',f'fe80::{i}') for i in range(1,5)]+[('GlobalAddr','2001:db8::1')]:s+=name+':\n Data.a '+','.join(str(v) for v in ipaddress.IPv6Address(ip).packed)+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
