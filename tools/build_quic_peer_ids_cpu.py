"""Physical peer connection-ID state, independent byte-level expected records."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,struct
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['tools/build_quic_peer_ids_cpu.py','Anvil/Network/quic_peer_ids.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[];steps=[];blobs=[];records=[None]*4;floor=0;selected=0;zero=0
 def code(s):steps.append(s)
 def check(name,expr,want):
  code(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def observe():
  for f,v in [('phase',1),('capacity',4),('limit',2),('floor',floor),('selected',selected),('zero',zero)]:check(f,'s\\'+f,v)
  check('pinned storage','Bool(s\\records=@records[0])',1)
  raw=b''
  for e in records:
   raw+=bytes(72) if e is None else struct.pack('<qqqq',e['seq'],len(e['id']),e['status'],int(e['token'] is not None))+e['id'].ljust(20,b'\0')+(e['token'] or bytes(16))+bytes(4)
  label='Expected'+str(len(blobs));blobs.append((label,raw));check('whole record image',f'Different(?{label})',0)
  owed=[e['seq'] for e in records if e and e['status']==2]
  check('next retirement','QuicPeerIdsRetireNext(@s)',min(owed) if owed else -1)
 def inputs(seed,length=8):
  code(f'For j=0 To 19 : id[j]=({seed}+j)&255 : Next\nFor j=0 To 15 : token[j]=({seed}+77+j)&255 : Next')
  return bytes((seed+i)%256 for i in range(length)),bytes((seed+77+i)%256 for i in range(16))
 def unchanged(expr,error):
  code('Snapshot()');check('refusal',expr,error);check('all state unchanged','Unchanged()',1)
 def fresh(z=False,with_token=False):
  nonlocal records,floor,selected,zero
  code('For j=0 To SizeOf(QuicPeerIds)-1 : PokeA(@s+j,0) : Next')
  cid,tok=inputs(10,0 if z else 8);records=[dict(seq=0,id=cid,token=tok if with_token else None,status=1),None,None,None];floor=selected=0;zero=int(z)
  check('initialize',f'QuicPeerIdsInit(@s,@records[0],4,2,@id[0],{len(cid)},{'@token[0]' if with_token else '0'})',0);observe()
 def add(seq,retire,seed,length=8):
  nonlocal floor,selected
  cid,tok=inputs(seed,length);expr=f'QuicPeerIdsAdd(@s,{seq},{retire},@id[0],{length},@token[0])'
  nf=max(floor,retire);found=next((i for i,e in enumerate(records) if e and e['seq']==seq),None)
  conflict=zero or any(e and ((e['seq']==seq and (e['id']!=cid or e['token'] not in (None,tok))) or (e['seq']!=seq and e['id']==cid)) for e in records)
  active=sum(e is not None and e['status']==1 and e['seq']>=nf for e in records)+int(found is None and seq>=nf)
  error=-3604 if conflict else (-3605 if active>2 else (-3606 if found is None and None not in records else None))
  if error is not None:unchanged(expr,error);observe();return
  check('add or duplicate',expr,int(found is None))
  if found is None:found=records.index(None);records[found]=dict(seq=seq,id=cid,token=tok,status=1)
  elif records[found]['token'] is None:records[found]['token']=tok
  for e in records:
   if e and e['seq']<nf:e['status']=2
  floor=nf
  if selected<floor:selected=min(e['seq'] for e in records if e and e['status']==1)
  observe()
 def ack(seq):
  index=next((i for i,e in enumerate(records) if e and e['seq']==seq),None)
  expr=f'QuicPeerIdsRetiredAck(@s,{seq})'
  if index is None:check('absent retirement',expr,0)
  elif records[index]['status']!=2:unchanged(expr,-3602)
  else:check('acknowledged retirement',expr,1);records[index]=None
  observe()
 check('null initialize','QuicPeerIdsInit(0,@records[0],4,2,0,0,0)',-3601)
 unchanged('QuicPeerIdsAdd(@s,1,0,@id[0],8,@token[0])',-3602)
 fresh();unchanged('QuicPeerIdsInit(@s,@records[0],4,2,0,0,0)',-3602)
 for expr in ['QuicPeerIdsAdd(@s,-1,0,@id[0],8,@token[0])','QuicPeerIdsAdd(@s,1,2,@id[0],8,@token[0])','QuicPeerIdsAdd(@s,1,0,@id[0],0,@token[0])','QuicPeerIdsAdd(@s,1,0,@id[0],21,@token[0])']:unchanged(expr,-3603)
 for expr in ['QuicPeerIdsAdd(@s,1,0,@s,8,@token[0])','QuicPeerIdsAdd(@s,1,0,@id[0],8,@records[0])','QuicPeerIdsAdd(@s,1,0,0,8,@token[0])','QuicPeerIdsAdd(@s,1,0,@id[0],8,$7FFFFFFFFFFFFFF8)']:unchanged(expr,-3601)
 add(0,0,10);add(0,0,10);add(0,0,11);add(1,0,20);add(1,0,20);add(2,0,20);add(2,0,30)
 add(2,1,30);add(1,0,20);ack(1);add(2,2,30);ack(0);ack(1);ack(1)
 add(0,0,10);ack(0);add(3,0,40,20);add(4,4,50,1);add(5,5,60)
 add(6,6,70);ack(2);add(6,6,70);ack(3);ack(4);ack(5)
 for n in range(7,25):add(n,n,n+100,(n%20)+1);ack(n-1)
 fresh(True);add(1,0,20);ack(0)
 fresh(True,True);add(1,0,20);ack(0)
 assert len(cases)*8+256<=65536
 s=r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/quic_peer_ids.pbi"
Global s.QuicPeerIds
Global Dim records.a[288]
Global Dim id.a[20]
Global Dim token.a[16]
Global Dim saved.a[344]
Procedure Snapshot()
 Define i.i
 For i=0 To 55 : saved[i]=PeekA(@s+i) : Next
 For i=0 To 287 : saved[56+i]=records[i] : Next
EndProcedure
Procedure.i Unchanged()
 Define i.i
 For i=0 To 55 : If saved[i]<>PeekA(@s+i) : ProcedureReturn 0 : EndIf : Next
 For i=0 To 287 : If saved[56+i]<>records[i] : ProcedureReturn 0 : EndIf : Next
 ProcedureReturn 1
EndProcedure
Procedure.i Different(p.i)
 Define i.i,d.i
 For i=0 To 287 : If records[i]<>PeekA(p+i) : d=d+1 : EndIf : Next
 ProcedureReturn d
EndProcedure
Procedure.i Main()
 Define rc.i,j.i
 If SizeOf(QuicPeerIds)<>56 : ProcedureReturn 74 : EndIf
 For j=0 To 65535 : PokeA($E1C00000+j,$A5) : Next
 PokeI($E1C00000,$55445331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''+ '\n'.join(steps)+f'\nPokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\nDataSection\n'
 for label,raw in blobs:
  s+=label+':\n'
  for start in range(0,len(raw),24):s+=' Data.a '+','.join(str(n) for n in raw[start:start+24])+'\n'
 s+='EndDataSection\n'
 source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
