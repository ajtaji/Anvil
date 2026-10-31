"""Physical application PN ownership, receipt timestamps and ACK serialization."""
from pathlib import Path
import argparse,hashlib,json,os,random,re,subprocess
from pmf_compiler import resolve_compiler
from build_quic_handshake_frames_cpu import vi

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['tools/build_quic_application_state_cpu.py','Anvil/Network/quic_application_state.pbi','Anvil/Network/quic_packet_ack.pbi','Anvil/Network/quic_wire.pbi','Anvil/Network/byte_order.pbi','RaspberryPi4/Lib/mmu.pi4']
 cases=[];steps=[];processed=set();largest=-1;stamp=0;authenticated=-1;demand=0;pending=0
 def code(s):steps.append(s)
 def check(name,expr,want):code(f'PokeI($E1C00100+{len(cases)*8},{expr})');cases.append(dict(name=name,expected=want))
 def groups():
  g=[]
  for pn in sorted(processed):
   if g and pn==g[-1][1]+1:g[-1][1]=pn
   else:g.append([pn,pn])
  return g[::-1]
 def observe():
  for f,v in [('largestAuthenticated',authenticated),('largestProcessed',largest),('receivedAt',stamp),('ack\\count',len(groups())),('ack\\demand',demand),('ack\\pending',pending)]:check(f,'s\\'+f,v)
 def fresh():
  nonlocal processed,largest,stamp,authenticated,demand,pending
  processed=set();largest=-1;stamp=0;authenticated=-1;demand=0;pending=0
  code('For j=0 To SizeOf(QuicApplicationState)-1 : PokeA(@s+j,0) : Next')
  check('initialize','QuicApplicationStateInit(@s)',0)
  check('inline storage','Bool(s\\ack\\entries=@s\\ranges)',1);check('range capacity','s\\ack\\capacity',64)
  observe()
 def unchanged(expr,error):
  code('Snapshot()');check('refusal '+expr,expr,error);check('whole owner unchanged','Unchanged()',1)
 def auth(pn):
  nonlocal authenticated
  check('authenticated '+str(pn),f'QuicApplicationAuthenticated(@s,{pn})',int(pn in processed));authenticated=max(authenticated,pn);observe()
 def receipt(pn,t,eliciting=1):
  nonlocal largest,stamp,demand,pending
  check('processed '+str(pn),f'QuicApplicationProcessed(@s,{pn},{eliciting},{t})',int(pn not in processed))
  processed.add(pn)
  if pn>largest:largest=pn;stamp=t
  if eliciting:demand+=1;pending=1
  observe()
 def write(now,exponent):
  g=groups();delay=(now-stamp)>>exponent
  wire=b'\2'+vi(g[0][1])+vi(delay)+vi(len(g)-1)+vi(g[0][1]-g[0][0])
  for (previous,_),(lo,hi) in zip(g,g[1:]):wire+=vi(previous-hi-2)+vi(hi-lo)
  code('For j=0 To 1099 : output[j]=$A5 : Next\ntoken=-7\nSnapshot()')
  check('ACK length',f'QuicApplicationAckWrite(@s,@output[0],1100,@token,{now},{exponent})',len(wire))
  check('owner unchanged by write','Unchanged()',1);check('ACK token','token',demand)
  for i,c in enumerate(wire):check('ACK byte '+str(i),f'output[{i}]',c)
  code(f'different=0\nFor j={len(wire)} To 1099 : If output[j]<>$A5 : different=1 : EndIf : Next')
  check('ACK output guard','different',0)
  code('For j=0 To 1099 : output[j]=$A5 : Next\ntoken=-7')
  check('short ACK capacity',f'QuicApplicationAckWrite(@s,@output[0],{len(wire)-1},@token,{now},{exponent})',-3444)
  check('short capacity token unchanged','token',-7);check('short capacity owner unchanged','Unchanged()',1)
  code('different=0\nFor j=0 To 1099 : If output[j]<>$A5 : different=1 : EndIf : Next')
  check('short capacity output unchanged','different',0)
 for expression in ['QuicApplicationNumberReserve(@s)','QuicApplicationAuthenticated(@s,0)','QuicApplicationProcessed(@s,0,1,0)','QuicApplicationAckDelay(@s,0,3)']:unchanged(expression,-3592)
 check('null initialize','QuicApplicationStateInit(0)',-3591)
 fresh();unchanged('QuicApplicationStateInit(@s)',-3592)
 for n in range(34):check('irreversible reservation '+str(n),'QuicApplicationNumberReserve(@s)',n)
 check('reservation counter','s\\nextNumber',34);unchanged('QuicApplicationStateInit(@s)',-3592)
 code('s\\nextNumber=$3FFFFFFFFFFFFFFE')
 check('penultimate PN','QuicApplicationNumberReserve(@s)',(1<<62)-2)
 check('last PN','QuicApplicationNumberReserve(@s)',(1<<62)-1)
 unchanged('QuicApplicationNumberReserve(@s)',-3593);unchanged('QuicApplicationNumberReserve(@s)',-3593)
 code('s\\nextNumber=-1');unchanged('QuicApplicationNumberReserve(@s)',-3593)
 fresh();unchanged('QuicApplicationAuthenticated(@s,-1)',-3441);unchanged('QuicApplicationAuthenticated(@s,$4000000000000000)',-3441)
 auth(5);auth(5);unchanged('QuicApplicationAckDelay(@s,100,3)',-3592)
 unchanged('QuicApplicationProcessed(@s,6,1,100)',-3591);unchanged('QuicApplicationProcessed(@s,5,1,-1)',-3591);unchanged('QuicApplicationProcessed(@s,5,2,100)',-3441)
 receipt(5,100);auth(5);receipt(5,200);auth(9);auth(7);receipt(7,90);auth(1);receipt(1,5000,0)
 write(6000,3)
 for exp in [-1,21]:unchanged(f'QuicApplicationAckDelay(@s,6000,{exp})',-3591)
 unchanged('QuicApplicationAckDelay(@s,89,3)',-3591)
 for expr in ['QuicApplicationAckWrite(@s,@s\\nextNumber,8,@token,6000,3)','QuicApplicationAckWrite(@s,@output[0],1100,@s\\nextNumber,6000,3)','QuicApplicationAckWrite(@s,@s\\ranges,16,@token,6000,3)']:unchanged(expr,-3591)
 fresh();rng=random.Random(1777)
 for i in range(100):
  pn=rng.randrange(64);auth(pn)
  if i%3:receipt(pn,1000+i*13,i%2)
  if i%17==16:write(10000+i*19,i%21)
 # A write snapshot does not clear subsequent demand.
 code('token=s\\ack\\demand');old=demand;auth(99);receipt(99,20000)
 check('stale completion','QuicPacketAckSent(@s\\ack,token)',0);observe()
 check('current completion',f'QuicPacketAckSent(@s\\ack,{demand})',1);pending=0;observe()
 fresh()
 for pn in range(0,128,2):auth(pn);receipt(pn,100+pn)
 auth(128);unchanged('QuicApplicationProcessed(@s,128,1,900)',-3443);observe()
 auth(1);receipt(1,800);receipt(128,900);write(1100,3)
 fresh();auth(0);receipt(0,0,0)
 unchanged('QuicApplicationAckDelay(@s,$7FFFFFFFFFFFFFFF,0)',-3593)
 for exp in [1,3,20]:write((1<<63)-1,exp)
 assert 256+8*len(cases)<=65536
 s=r'''XIncludeFile "RaspberryPi4/Lib/mmu.pi4"
XIncludeFile "Anvil/Network/quic_application_state.pbi"
Global s.QuicApplicationState,token.i
Global Dim output.a[1100]
Global Dim guard.a[1120]
Procedure Snapshot()
 Define i.i
 For i=0 To SizeOf(QuicApplicationState)-1 : guard[i]=PeekA(@s+i) : Next
EndProcedure
Procedure.i Unchanged()
 Define i.i
 For i=0 To SizeOf(QuicApplicationState)-1 : If guard[i]<>PeekA(@s+i) : ProcedureReturn 0 : EndIf : Next
 ProcedureReturn 1
EndProcedure
Procedure.i Main()
 Define rc.i,j.i,different.i
 If SizeOf(QuicApplicationState)<>1120 : ProcedureReturn 74 : EndIf
 For j=0 To 65535 : PokeA($E1C00000+j,$A5) : Next
 PokeI($E1C00000,$55445331)
 MmuClearNc() : MmuAddNc($08A00000,$09200000) : MmuAddNc($08100000,$08180000)
 rc=MmuBuildTables($4F80000) : If rc<>0 : ProcedureReturn 2 : EndIf
 MmuEnableCached()
'''+ '\n'.join(steps)+f'\nPokeI($E1C00008,{len(cases)})\nMmuDisableCachedFlushed()\nProcedureReturn 0\nEndProcedure\n'
 source=out/'proof.pi4';source.write_text(s)
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log);print(log[-1200:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c0ffff'],'tables':['0x4f80000','0x4f82fff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=cases),indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
