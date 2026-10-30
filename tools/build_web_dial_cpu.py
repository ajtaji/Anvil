"""Qualify the real dual-family HTTP transport adapter on a physical CPU."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess
from pmf_compiler import resolve_compiler

def build(compiler,out):
 root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False)
 names=['Anvil/Network/tcp_dial.pbi','Anvil/Network/web_transport.pbi','Anvil/Network/web_url.pbi','Anvil/Network/ipv6_address.pbi']
 s='#WEB_KERNEL_BINDING=0\nXIncludeFile "Anvil/Network/web_url.pbi"\nXIncludeFile "Anvil/Network/web_transport.pbi"\n'+r'''
Global con.WebConnection
Global Dim fixtureTable.i[256]
Global fixtureMode.i,fixtureAge.i,fixtureNow.i,fixtureStart.i
Global calls4.i,calls6.i,opens4.i,opens6.i,closed4.i,closed6.i,closedTls.i
Procedure.i DialFixtureTime()
 ProcedureReturn fixtureNow*1000
EndProcedure
Procedure.i DialFixtureDns4(name.i)
 calls4=calls4+1
 If fixtureMode=1 Or fixtureMode=2 Or fixtureMode=6 Or fixtureMode=12 : ProcedureReturn -105 : EndIf
 If fixtureMode=10 And fixtureAge<400 : ProcedureReturn -110 : EndIf
 ProcedureReturn $C0000201
EndProcedure
Procedure.i DialFixtureDns6(name.i,out.i)
 Define i.i
 calls6=calls6+1
 If fixtureMode=9 Or fixtureMode=12 : ProcedureReturn -105 : EndIf
 If fixtureMode=10 And fixtureAge<400 : ProcedureReturn -103 : EndIf
 For i=0 To 15 : PokeA(out+i,i) : Next
 ProcedureReturn 16
EndProcedure
Procedure.i DialFixtureOpen4(ip.i,port.i)
 opens4=opens4+1
 If fixtureMode=11 And opens4<3 : ProcedureReturn -103 : EndIf
 ProcedureReturn 1
EndProcedure
Procedure.i DialFixtureOpen6(ip.i,port.i)
 opens6=opens6+1 : ProcedureReturn 2
EndProcedure
Procedure.i DialFixtureState(handle.i)
 If handle=1
  If fixtureMode=3 Or fixtureMode=5 Or fixtureMode=17 : ProcedureReturn 1 : EndIf
  If fixtureMode=4 And fixtureAge<300 : ProcedureReturn 1 : EndIf
  If (fixtureMode=8 Or fixtureMode=9) And fixtureAge<400 : ProcedureReturn 1 : EndIf
  ProcedureReturn 2
 EndIf
 If fixtureMode=8 : ProcedureReturn -105 : EndIf
 If fixtureMode=4 Or fixtureMode=5 : ProcedureReturn 1 : EndIf
 ProcedureReturn 2
EndProcedure
Procedure.i DialFixtureClose(handle.i)
 If handle=1 : closed4=closed4+1 : EndIf
 If handle=2 : closed6=closed6+1 : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i DialFixtureTlsOpen(host.i,port.i)
 ProcedureReturn 3
EndProcedure
Procedure.i DialFixtureTlsState(handle.i)
 ProcedureReturn 4
EndProcedure
Procedure.i DialFixtureTlsClose(handle.i)
 closedTls=closedTls+1 : ProcedureReturn 0
EndProcedure
Procedure.i DialFixtureIo(handle.i,p.i,n.i)
 ProcedureReturn 0
EndProcedure
Procedure.i DialFixtureService(ms.i)
 ProcedureReturn 0
EndProcedure
Procedure DialFixtureRun(index.i)
 Define i.i,p.i,rc.i,chosen.i,minor.i
 fixtureMode=index : fixtureAge=0 : fixtureStart=0
 If index=17 : fixtureStart=$FFFFFF80 : EndIf
 fixtureNow=fixtureStart
 calls4=0 : calls6=0 : opens4=0 : opens6=0 : closed4=0 : closed6=0 : closedTls=0
 For i=0 To SizeOf(WebConnection)-1 : PokeA(@con+i,0) : Next
 For i=0 To 255 : fixtureTable[i]=0 : Next
 minor=12 : If index=0 : minor=6 : EndIf : If index=1 : minor=11 : EndIf
 PokeL(@fixtureTable[0],$53564E41) : PokeL(@fixtureTable[0]+4,1)
 PokeL(@fixtureTable[0]+8,minor) : PokeL(@fixtureTable[0]+12,200)
 fixtureTable[2+11]=@DialFixtureTime
 fixtureTable[2+75]=@DialFixtureDns4 : fixtureTable[2+89]=@DialFixtureDns6
 fixtureTable[2+76]=@DialFixtureOpen4 : fixtureTable[2+88]=@DialFixtureOpen6
 fixtureTable[2+77]=@DialFixtureIo : fixtureTable[2+78]=@DialFixtureIo
 fixtureTable[2+79]=@DialFixtureClose : fixtureTable[2+86]=@DialFixtureState
 fixtureTable[2+80]=@DialFixtureTlsOpen : fixtureTable[2+87]=@DialFixtureTlsState
 fixtureTable[2+81]=@DialFixtureIo : fixtureTable[2+82]=@DialFixtureIo
 fixtureTable[2+83]=@DialFixtureTlsClose : fixtureTable[2+85]=@DialFixtureService
 If index=14 : fixtureTable[2+88]=0 : EndIf
 rc=WebPayloadBind(@fixtureTable[0])
 con\host="example.test" : con\port=80
 If index=6 : con\host="192.0.2.1" : EndIf
 If index=7 : con\host="[2001:db8::1]" : EndIf
 If index=15 : con\secure=1 : con\port=443 : EndIf
 If rc=0 : rc=WebTransportOpen(@con) : EndIf
 If rc=0
  For i=0 To 20
   fixtureAge=i*50 : fixtureNow=(fixtureStart+fixtureAge) & $FFFFFFFF
   rc=WebTransportState(@con)
   If index=5 And fixtureAge=300 : Break : EndIf
   If rc<>0 : Break : EndIf
  Next
 EndIf
 chosen=con\handle
 WebTransportClose(@con)
 If index=16
  rc=WebTransportOpen(@con)
  If rc=0 : rc=WebTransportState(@con) : EndIf
  If rc=0 : rc=WebTransportState(@con) : EndIf
  chosen=con\handle : WebTransportClose(@con)
 EndIf
 p=$E1C00100+index*128
 PokeI(p,rc) : PokeI(p+8,chosen) : PokeI(p+16,opens4) : PokeI(p+24,opens6)
 PokeI(p+32,calls4) : PokeI(p+40,calls6) : PokeI(p+48,closed4) : PokeI(p+56,closed6)
 PokeI(p+64,closedTls) : PokeI(p+72,con\handle) : PokeI(p+80,con\dial\dial4) : PokeI(p+88,con\dial\dial6)
 PokeI(p+96,fixtureAge) : PokeI(p+104,con\dial\allow6)
EndProcedure
Procedure.i Main()
 Define i.i
 For i=0 To 131071 : PokeA($E1C00000+i,$A5) : Next
 PokeI($E1C00000,$4449414C) : PokeI($E1C00008,18)
 For i=0 To 17 : DialFixtureRun(i) : Next
 ProcedureReturn 0
EndProcedure
'''
 source=out/'proof.pi4';source.write_text(s,encoding='utf8')
 q=subprocess.run([str(resolve_compiler(compiler)),'--compile',str(source),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4f00000','--entry-returns','--wants-services','-o',str(out/'proof.img')],env=dict(os.environ,PMF_ROOT=str(root)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 log=q.stdout+q.stderr;(out/'compile.txt').write_text(log,encoding='utf8');print(log[-1400:]);assert q.returncode==0
 code=re.search(r'occupying \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log);bss=re.search(r'bss \$([0-9A-Fa-f]+)\.\.\$([0-9A-Fa-f]+)',log)
 payload=(out/'proof.img.pmf').read_bytes();ranges={'code':['0x'+x for x in code.groups()],'bss':['0x'+x for x in bss.groups()],'stack':['0x4e00000','0x4efffff'],'report':['0xe1c00000','0xe1c1ffff']}
 (out/'identity.json').write_text(json.dumps(dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),checked_ranges=ranges,source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},cases=list(range(18))),indent=2),encoding='utf8')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args();build(args.compiler,args.out.resolve())
