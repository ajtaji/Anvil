"""Build physical neighbor reachability transition and timer proofs."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_reachability.pbi','RaspberryPi4/Lib/mmu.pi4']
 old=int.from_bytes(bytes.fromhex('0201020304050000'),'little');new=int.from_bytes(bytes.fromhex('02060708090a0000'),'little')
 cases=[];rows=[]
 def add(name,op,state,router,mac,flags,now,interval,deadline,probes,expected):
  rows.append([op,state,router,mac,flags,now,interval,deadline,probes]);cases.append(dict(name=name,expected=expected))
 for state in range(7):
  for router in [0,1]:
   for mac in range(3):
    for bits in range(8):
     flags=bits<<29;sol=bool(bits&2);over=bool(bits&1);r=int(bool(bits&4))
     answer=[0,state,router,1234,2,old]
     if state not in [0,6]:
      if state==1:
       if mac:answer=[2 if router and not r else 1,2 if sol else 3,r,31000 if sol else 0,0,new if mac==2 else old]
      elif mac==2 and not over:
       if state==2:answer=[1,3,router,0,2,old]
      else:
       changed=mac==2
       answer=[2 if router and not r else 1,2 if sol else (3 if changed else state),r,31000 if sol else (0 if changed else 1234),0 if sol or changed else 2,new if changed else old]
     add(f'NA state={state} router={router} mac={mac} flags={bits}',0,state,router,mac,flags,1000,30000,1234,2,answer)
 # Timer boundaries and rate limits. Each row is an independently specified
 # state-machine boundary, not a timing measurement on the host.
 timer=[
 (1,0,0,0,[1,1,0,1000,1,old]),(1,999,1000,1,[0,1,0,1000,1,old]),
 (1,1000,1000,1,[1,1,0,2000,2,old]),(1,2000,2000,2,[1,1,0,3000,3,old]),
 (1,2999,3000,3,[0,1,0,3000,3,old]),(1,3000,3000,3,[3,6,0,0,3,old]),
 (2,29999,30000,0,[0,2,0,30000,0,old]),(2,30000,30000,0,[0,3,0,0,0,old]),
 (3,100000,0,0,[0,3,0,0,0,old]),(4,4999,5000,0,[0,4,0,5000,0,old]),
 (4,5000,5000,0,[2,5,0,6000,1,old]),(5,5999,6000,1,[0,5,0,6000,1,old]),
 (5,6000,6000,1,[2,5,0,7000,2,old]),(5,7000,7000,2,[2,5,0,8000,3,old]),
 (5,8000,8000,3,[3,6,0,0,3,old]),(6,9000,0,3,[0,6,0,0,3,old])]
 for state,now,deadline,probes,e in timer:add(f'timer {state}/{now}',1,state,0,0,0,now,1000,deadline,probes,e)
 for state in range(7):
  e=[1 if state in [2,3,4,5] else (0 if state==1 else -2),4 if state in [2,3] else state,0,6000 if state in [2,3] else 1000,0 if state in [2,3] else 2,old]
  add(f'use expired {state}',2,state,0,0,0,1000,30000,1000,2,e)
  e=[1,2,0,31000,0,old] if state in [2,3,4,5] else [0,state,0,1000,2,old]
  add(f'confirm {state}',3,state,0,0,0,1000,30000,1000,2,e)
 for state in range(7):
  for mac in range(3):
   e=[0,state,1 if state not in [0,6] else 0,1000,2,old] if mac==0 else [1,3 if mac==2 or state in [0,1,6] else state,1,0 if mac==2 or state in [0,1,6] else 1000,0 if mac==2 or state in [0,1,6] else 2,new if mac==2 else old]
   add(f'RA learn {state}/{mac}',4,state,0,mac,1,1000,30000,1000,2,e)
 add('init',5,5,1,0,0,123,0,9000,3,[0,1,0,123,0,0])
 s='\n'.join('XIncludeFile "'+n+'"' for n in names)+'\n'+r'''
Global wtable.i
Global *pet
Global entry.IPv6Reachability
Global oldMac.q
Global newMac.q
Procedure CaptureTable()
 ASM
 adrp x1, global_wtable
 add x1, x1, #:lo12:global_wtable
 str x0, [x1]
 EndASM
EndProcedure
Procedure ReachabilityFixture(index.i,row.i)
 Define op.i,mac.i,rc.i,p.i,now.i,interval.i,flags.i
 op=PeekI(row) : entry\state=PeekI(row+8) : entry\router=PeekI(row+16)
 mac=PeekI(row+24) : flags=PeekI(row+32) : now=PeekI(row+40) : interval=PeekI(row+48)
 entry\deadline=PeekI(row+56) : entry\probes=PeekI(row+64) : entry\mac=oldMac
 If mac=1 : mac=@oldMac : ElseIf mac=2 : mac=@newMac : EndIf
 Select op
  Case 0 : rc=IPv6ReachabilityAdvertise(@entry,mac,flags,now,interval)
  Case 1 : rc=IPv6ReachabilityTick(@entry,now,interval)
  Case 2 : rc=IPv6ReachabilityUse(@entry,now)
  Case 3 : rc=IPv6ReachabilityConfirm(@entry,now,interval)
  Case 4 : rc=IPv6ReachabilityLearn(@entry,mac,flags)
  Case 5 : rc=IPv6ReachabilityInit(@entry,now)
 EndSelect
 p=$E1C00100+index*64
 PokeI(p,rc) : PokeI(p+8,entry\state) : PokeI(p+16,entry\router)
 PokeI(p+24,entry\deadline) : PokeI(p+32,entry\probes) : PokeI(p+40,entry\mac)
 pet()
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 CaptureTable()
 For i=0 To 65535 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C00000,$49503635)
 pet=PeekI(wtable+16+6*8)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''
 s+=f' oldMac={old} : newMac={new}\n For i=0 To {len(rows)-1}\n ReachabilityFixture(i,?ReachabilityVectors+i*72)\n Next\n PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\nReachabilityVectors:\n'
 for row in rows:s+=' Data.q '+','.join(str(x) for x in row)+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
