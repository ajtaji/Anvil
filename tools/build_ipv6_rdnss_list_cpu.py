"""Build physical lifecycle and interface-isolation tests of RDNSS storage."""
from pathlib import Path
import argparse,hashlib,ipaddress,json,os,re,struct,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/ipv6_rdnss_list.pbi','Anvil/Network/ipv6_rdnss.pbi','Anvil/Network/ipv6_neighbor.pbi','Anvil/Network/ipv6_packet.pbi','Anvil/Network/ipv6_address.pbi','Anvil/Network/byte_order.pbi','Anvil/Network/internet_checksum.pbi','RaspberryPi4/Lib/mmu.pi4']
 addr=lambda name:ipaddress.IPv6Address(name).packed
 A,B,C,D,E,F,I=['fe80::'+str(i) for i in range(1,8)]
 infinity=0x7fffffffffffffff;limit=0x7ffff00000000000
 states=[None,None];cases=[];steps=[];vectors=[]
 def state(which,kind,gen,now,rev,rows):states[which]=(kind,gen,now,rev,rows)
 def record_state(st):
  if st is None:return bytes(48)+b'\xa5'*88
  kind,gen,now,rev,rows=st
  return struct.pack('<6q',gen,kind,now,rev,3,len(rows))+b''.join(addr(a)+struct.pack('<q',t) for a,t in rows)+bytes(72-len(rows)*24)+b'\xa5'*16
 def add(name,code,rc=0,selected=None):
  raw=b''.join(record_state(st) for st in states)+(addr(selected) if selected else b'\xa5'*16)
  cases.append(dict(name=name,rc=rc,state=raw.hex()));steps.append(code)
 def batch(rows):
  i=len(vectors);vectors.append(b''.join(addr(a)+struct.pack('<q',t) for a,t in rows));return f'?R{i},{len(rows)}'
 def apply(rows,now,gen=1,kind=1,which=0):return f'rc=IPv6RdnssListApply(@s{which},{kind},{gen},{now},{batch(rows)})'
 state(0,1,1,100,1,[]);add('initialize first interface','rc=IPv6RdnssListInit(@s0,1,1,@entries0[0],3,100)')
 state(0,1,1,100,4,[(A,3100),(B,5100),(C,7100)]);add('packet server order',apply([(A,3),(B,5),(C,7)],100))
 state(0,1,1,200,5,[(A,3100),(B,20200),(C,7100)]);add('renew without reordering',apply([(B,20)],200))
 add('first server selection','rc=IPv6RdnssListGet(@s0,1,1,200,0,@selected[0])',16,A)
 add('invalid later row prevents all mutation',apply([(D,2),('ff02::1',1)],300),-913)
 add('wrong interface','rc=IPv6RdnssListTick(@s0,2,1,300)',-914)
 add('old generation','rc=IPv6RdnssListTick(@s0,1,2,300)',-914)
 add('clock rollback','rc=IPv6RdnssListTick(@s0,1,1,199)',-913)
 state(0,1,1,300,7,[(D,8300),(B,20200),(C,7100)]);add('full table evicts earliest expiry',apply([(D,8)],300))
 state(0,1,1,400,11,[(F,2400),(D,8300),(B,20200)]);add('eviction of earlier new row keeps ordering',apply([(E,1),(F,2)],400))
 state(0,1,1,500,12,[(F,2400),(B,20200)]);add('withdraw compacts and clears tail',apply([(D,0)],500))
 state(0,1,1,2400,13,[(B,20200)]);add('expiry before selection','rc=IPv6RdnssListGet(@s0,1,1,2400,0,@selected[0])',16,B)
 add('absent withdrawal is not insertion',apply([(A,0)],2400))
 state(0,1,1,2500,14,[(I,infinity),(B,20200)]);add('infinite entry',apply([(I,4294967295)],2500))
 add('missing index leaves destination untouched','rc=IPv6RdnssListGet(@s0,1,1,2500,2,@selected[0])')
 state(0,1,1,20200,15,[(I,infinity)]);add('finite expiry retains infinity','rc=IPv6RdnssListTick(@s0,1,1,20200)',1)
 state(0,1,1,20300,16,[(I,21300)]);add('renew infinite to finite',apply([(I,1)],20300))
 state(0,1,1,21300,17,[]);add('exact expiration boundary','rc=IPv6RdnssListTick(@s0,1,1,21300)',1)
 state(0,1,1,30000,18,[(A,4294967324000)]);add('largest finite lifetime',apply([(A,4294967294)],30000))
 state(0,1,1,4294976295,18,[(A,4294967324000)]);add('extended clock past 32 bits','rc=IPv6RdnssListTick(@s0,1,1,4294976295)')
 add('same generation cannot reset','rc=IPv6RdnssListInit(@s0,1,1,@entries0[0],3,0)',-914)
 state(0,1,2,0,1,[]);add('new link generation clears learned addresses','rc=IPv6RdnssListInit(@s0,1,2,@entries0[0],3,0)')
 add('old callback cannot repopulate',apply([(A,1)],0),-914)
 state(0,1,2,0,2,[(A,infinity)]);add('first link learns scoped address',apply([(A,4294967295)],0,2))
 state(1,2,1,0,1,[]);add('second interface independent init','rc=IPv6RdnssListInit(@s1,2,1,@entries1[0],3,0)')
 state(1,2,1,0,2,[(A,1000)]);add('same address on second link',apply([(A,1)],0,1,2,1))
 state(1,2,1,1000,3,[]);add('second link expiry leaves first unchanged','rc=IPv6RdnssListTick(@s1,2,1,1000)',1)
 add('cross-link lookup refused','rc=IPv6RdnssListGet(@s0,2,2,1000,0,@selected[0])',-914)
 state(0,1,2,1000,2,[(A,infinity)]);add('first link still eligible','rc=IPv6RdnssListGet(@s0,1,2,1000,0,@selected[0])',16,A)
 add('input alias refused','rc=IPv6RdnssListApply(@s0,1,2,1000,@entries0[0],1)',-913)
 add('output alias refused','rc=IPv6RdnssListGet(@s0,1,2,1000,0,@entries0[0])',-913)
 add('init context alias refused','rc=IPv6RdnssListInit(@s0,1,3,@s0,3,0)',-913)
 add('too-small repository refused','rc=IPv6RdnssListInit(@s0,1,3,@entries0[0],2,0)',-913)
 state(0,1,2,1100,2,[(A,infinity)]);add('empty batch ticks safely','rc=IPv6RdnssListApply(@s0,1,2,1100,0,0)')
 add('negative batch count','rc=IPv6RdnssListApply(@s0,1,2,1100,0,-1)',-913)
 add('excessive batch count','rc=IPv6RdnssListApply(@s0,1,2,1100,0,4097)',-913)
 add('null nonempty batch','rc=IPv6RdnssListApply(@s0,1,2,1100,0,1)',-913)
 add('unspecified address refused',apply([('::',1)],1200,2),-913)
 add('negative lifetime refused',apply([(A,-1)],1200,2),-913)
 add('overlong lifetime refused',apply([(A,4294967296)],1200,2),-913)
 add('unsafe clock limit refused',f'rc=IPv6RdnssListTick(@s0,1,2,{limit+1})',-913)
 state(0,1,3,limit,1,[]);add('maximum clock initialization',f'rc=IPv6RdnssListInit(@s0,1,3,@entries0[0],3,{limit})')
 state(0,1,3,limit,2,[(A,limit+4294967294000)]);add('finite lifetime addition cannot overflow',apply([(A,4294967294)],limit,3))
 add('safe clock lookup',f'rc=IPv6RdnssListGet(@s0,1,3,{limit},0,@selected[0])',16,A)
 # A fresh epoch isolates tie policy and link-down cleanup from earlier clocks.
 state(0,1,4,0,1,[]);add('fresh epoch for tie policy','rc=IPv6RdnssListInit(@s0,1,4,@entries0[0],3,0)')
 state(0,1,4,0,4,[(A,infinity),(B,infinity),(C,infinity)]);add('equal expiry initial order',apply([(A,4294967295),(B,4294967295),(C,4294967295)],0,4))
 state(0,1,4,1,8,[(D,infinity),(E,infinity),(A,infinity)]);add('equal expiry evicts least preferred',apply([(D,4294967295),(E,4294967295)],1,4))
 add('stale clear cannot delete live entries','rc=IPv6RdnssListClear(@s0,1,3,1)',-914)
 state(0,1,4,2,9,[]);add('link unavailable clears current epoch','rc=IPv6RdnssListClear(@s0,1,4,2)')
 state(0,1,4,3,9,[]);add('repeated clear is idempotent','rc=IPv6RdnssListClear(@s0,1,4,3)')
 add('cleared address no longer selected','rc=IPv6RdnssListGet(@s0,1,4,3,0,@selected[0])')
 s='XIncludeFile "RaspberryPi4/Lib/mmu.pi4"\nXIncludeFile "Anvil/Network/ipv6_rdnss_list.pbi"\n'+r"""
Global s0.IPv6RdnssList,s1.IPv6RdnssList
Global Dim entries0.a[88]
Global Dim entries1.a[88]
Global Dim selected.a[16]
Procedure StoreState(p.i,*s.IPv6RdnssList,rows.i)
 Define i.i
 PokeI(p,*s\generation) : PokeI(p+8,*s\kind) : PokeI(p+16,*s\lastNow)
 PokeI(p+24,*s\revision) : PokeI(p+32,*s\capacity) : PokeI(p+40,*s\count)
 For i=0 To 87 : PokeA(p+48+i,PeekA(rows+i)) : Next
EndProcedure
Procedure Save(index.i,rc.i)
 Define p.i,i.i
 p=$E1C00100+index*384 : PokeI(p,rc)
 StoreState(p+8,@s0,@entries0[0]) : StoreState(p+144,@s1,@entries1[0])
 For i=0 To 15 : PokeA(p+280+i,selected[i]) : Next
EndProcedure
Procedure.i Main()
 Define i.i,rc.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 For i=0 To 87 : entries0[i]=$A5 : entries1[i]=$A5 : Next
 PokeI($E1C00000,$52444C53)
 MmuClearNc() : rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
"""
 for k,code in enumerate(steps):s+=' For i=0 To 15 : selected[i]=$A5 : Next\n'+code+f'\n Save({k},rc)\n'
 s+=f' PokeI($E1C00008,{len(cases)})\n MmuDisableCachedFlushed()\n ProcedureReturn 0\nEndProcedure\nDataSection\n'
 for k,b in enumerate(vectors):
  s+=f' R{k}:\n'
  for i in range(0,len(b),24):s+=' Data.a '+','.join(map(str,b[i:i+24]))+'\n'
 s+='EndDataSection\n';source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-2000:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2),encoding='utf8')

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
