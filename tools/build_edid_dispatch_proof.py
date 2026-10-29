"""Build a returning shared EDID dispatch proof; no emulator execution."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,re
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
from edid_parse_check import fixture_edid,dtd_1080p60
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--target',choices=['pi4','unoq'],required=True);a=ap.parse_args()
r=Path(__file__).resolve().parents[1];layout=state_proof_layout(a.target)
cases=[
(fixture_edid(),128,1,0,{1:1,2:1024,3:768,5:1,8:1,9:0,10:65000,13:1,14:1048,15:1184,16:1344,17:771,18:777,19:806,20:0,21:1,22:1,23:1}),
(fixture_edid(bad_porch=True),128,1,0,{1:1,13:0}),
(fixture_edid(interlaced=True),128,1,0,{1:1,13:1,20:1,11:0}),
(fixture_edid(preferred_dtd=dtd_1080p60()),128,1,0,{1:1,2:1920,3:1080,10:148500,11:60000,13:1,14:2008,15:2052,16:2200,17:1084,18:1089,19:1125}),
(fixture_edid(extension=True),256,2,0,{1:1,2:1024,3:768,8:2,9:1,6:0}),
(fixture_edid(extension=True),128,1,1,{1:1,6:1,5:1}),
(fixture_edid(extension=True,bad_ext=True),256,2,0,{1:1,5:1,6:1,7:5}),
(fixture_edid(bad_base=True),128,1,0,{1:0,5:0,7:3}),
(bytes([1])+fixture_edid()[1:],128,1,0,{1:0,5:0,7:2}),
(fixture_edid(),127,1,0,{1:0,5:0,7:1}),
(fixture_edid(),128,9,0,{1:0,5:0,7:1}),
]
s='''XIncludeFile "Anvil/Graphics/edid.pbi"
XIncludeFile "Anvil/Graphics/Tests/edid_parse_gate.pbi"
Global Dim dispatchControl.i[9]
Global dispatchData.i,dispatchChecks.i,dispatchFailure.i
Procedure.i Dispatch(selector.i)
 dispatchControl[0]=selector
 ProcedureReturn EdidParseGateDispatch(@dispatchControl[0],dispatchData)
EndProcedure
Procedure C(actual.i,expected.i)
 dispatchChecks=dispatchChecks+1
 If actual<>expected And dispatchFailure=0 : dispatchFailure=dispatchChecks : EndIf
EndProcedure
Procedure.i Main(services.i)
 Protected index.i,count.i,found.i,bad.i
'''
checks=0
for i,(data,size,blocks,trunc,expected) in enumerate(cases):
 s+=f' dispatchData=?case{i} : dispatchControl[1]={size} : dispatchControl[2]={blocks} : dispatchControl[3]={trunc}\n'
 for selector,value in expected.items():s+=f' C(Dispatch({selector}),{value})\n';checks+=1
 if i==4:
  s+=''' count=Dispatch(4) : found=0 : bad=0
 For index=0 To count-1
  dispatchControl[1]=index
  If Dispatch(12)<>1 : bad=1 : EndIf
  If dispatchControl[5]=1920 And dispatchControl[6]=1080 : found=1 : EndIf
 Next
 C(found,1) : C(bad,0)
''';checks+=2
s+=' dispatchControl[1]=9999\n C(Dispatch(12),0)\n C(Dispatch(999),-1)\n';checks+=2
s+=f' PokeI(${layout["report"]:X},$45444944) : PokeI(${layout["report"]+8:X},dispatchChecks) : PokeI(${layout["report"]+16:X},dispatchFailure)\n ProcedureReturn dispatchFailure\nEndProcedure\nDataSection\n'
for i,(data,*_) in enumerate(cases):s+=f'case{i}:\n Data.a '+','.join('$%02X'%v for v in data)+'\n'
s+='EndDataSection\n';d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);(d/'proof.pbi').write_text(s,encoding='utf8',newline='\n')
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
payload=(d/'proof.img.pmf').read_bytes();names=['Anvil/Graphics/edid.pbi','Anvil/Graphics/Tests/edid_parse_gate.pbi','tools/edid_parse_check.py'];(d/'identity.json').write_text(json.dumps(dict(target=a.target,checks=checks,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},checked_ranges=check_linked_layout(layout,log),executed=False),indent=2),encoding='utf8')