"""Build exact incremental font-owner procedures with controlled storage/slot seams."""
from pathlib import Path
import argparse,re,json,hashlib,os,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--target',choices=['pi4','pi3'],required=True);a=ap.parse_args()
r=Path(__file__).resolve().parents[1];rel='Anvil/Core/font_cmd.pbi';raw=(r/rel).read_bytes();source=raw.decode('utf8').replace('\r\n','\n')
names=['AnvilFontFileBegin','AnvilFontFileCancel','AnvilFontFileStep','AnvilFontLoadMemory','anvil_font_SlotAddress','anvil_font_CopySlotPath','anvil_font_ClearSlotPath','anvil_font_LoadFile']
s='#ANVIL_TTS_MAX_BYTES=1048576\n'+source[:source.index('; Begin an incremental file load')]
for name in names:
 matches=re.findall(r'(?ms)^Procedure\.\w+ '+name+r'\(.*?^EndProcedure',source);assert len(matches)==1,name;s+=matches[0]+'\n'
s+='''
Global Dim tBytes.i[4]
Global Dim tGeneration.i[4]
Global tSelected.i=3,tStorage.i=1,tOpenOk.i=1,tSize.i=10,tShort.i,tInvalid.i,tHandle.i,tReads.i,tLoads.i,tMaxRead.i
Global checks.i,failure.i,token.i,oldToken.i
Procedure.i AnvilTrueTypeSlotBytes(slot.i)
 ProcedureReturn tBytes[slot]
EndProcedure
Procedure.i AnvilTrueTypeSlotGeneration(slot.i)
 ProcedureReturn tGeneration[slot]
EndProcedure
Procedure.i AnvilTrueTypeSlotSelected()
 ProcedureReturn tSelected
EndProcedure
Procedure.i AnvilTrueTypeSlotLoad(slot.i,data.i,bytes.i)
 tLoads=tLoads+1
 If tInvalid : ProcedureReturn 0 : EndIf
 tBytes[slot]=bytes : tGeneration[slot]=tGeneration[slot]+1
 ProcedureReturn 1
EndProcedure
Procedure.i HwStorageUp()
 ProcedureReturn tStorage
EndProcedure
Procedure.i HwFileOpen(path.i)
 If tOpenOk=0 : ProcedureReturn 0 : EndIf
 tHandle=tHandle+1
 ProcedureReturn 1
EndProcedure
Procedure.i HwFileSize()
 ProcedureReturn tSize
EndProcedure
Procedure HwFileClose()
 tHandle=tHandle-1
EndProcedure
Procedure.i HwFileReadAt(offset.i,target.i,bytes.i)
 Protected i.i
 tReads=tReads+1
 If bytes>tMaxRead : tMaxRead=bytes : EndIf
 If tShort : ProcedureReturn bytes-1 : EndIf
 For i=0 To bytes-1 : PokeA(target+i,offset+i+10) : Next
 ProcedureReturn bytes
EndProcedure
Procedure C(actual.i,expected.i)
 checks=checks+1
 If actual<>expected And failure=0 : failure=checks : EndIf
EndProcedure
Procedure.i Main(services.i)
'''
steps=[
'C(AnvilFontFileBegin(-1,"font",4,32),0)',
'C(AnvilFontFileBegin(4,"font",4,32),0)',
'C(AnvilFontFileBegin(0,0,4,32),0)',
'C(AnvilFontFileBegin(0,"font",0,32),0)',
'C(AnvilFontFileBegin(0,"font",5,32),0)',
'C(AnvilFontFileBegin(0,"font",4,0),0)',
'C(AnvilFontFileBegin(3,"font",4,32),0)',
' tBytes[1]=10',
'C(AnvilFontFileBegin(1,"font",4,32),0)',
' token=AnvilFontFileBegin(0,"font",4,32)',
'C(Bool(token>0),1)',
'C(AnvilFontFileBegin(0,"other",5,32),0)',
'C(AnvilFontLoadMemory(0,"data",4),0)',
'C(anvil_font_LoadFile(0,"other",5),0)',
'C(AnvilFontFileStep(0,token+1,4),0)',
'C(AnvilFontFileStep(0,token,0),0)',
'C(AnvilFontFileStep(0,token,4097),0)',
'C(AnvilFontFileStep(0,token,4),1)',
'C(tHandle,0)',
'C(tBytes[0],0)',
'C(anvil_font_slot_path[0],0)',
'C(AnvilFontFileStep(0,token,4),1)',
'C(AnvilFontFileStep(0,token,4),2)',
'C(tHandle,0)',
'C(tBytes[0],10)',
'C(tSelected,3)',
'C(tMaxRead,4)',
'C(PeekA(anvil_font_SlotAddress(0)+9),19)',
'C(anvil_font_slot_path[0],102)',
'C(anvil_font_slot_path[4],0)',
'C(AnvilFontFileStep(0,token,4),0)',
'C(AnvilFontFileCancel(0,token),0)',
' oldToken=token : tBytes[0]=0 : tGeneration[0]=tGeneration[0]+1',
' token=AnvilFontFileBegin(0,"font",4,32)',
'C(Bool(token>oldToken),1)',
'C(AnvilFontFileCancel(0,oldToken),0)',
'C(AnvilFontFileStep(0,token,4),1)',
' tSize=11',
'C(AnvilFontFileStep(0,token,4),0)',
'C(tHandle,0)',
'C(tBytes[0],0)',
' tSize=10 : token=AnvilFontFileBegin(0,"font",4,32) : tShort=1',
'C(AnvilFontFileStep(0,token,4),0)',
'C(tHandle,0)',
' tShort=0 : token=AnvilFontFileBegin(0,"font",4,32) : tStorage=0',
'C(AnvilFontFileStep(0,token,4),0)',
'C(tHandle,0)',
' tStorage=1 : token=AnvilFontFileBegin(0,"font",4,32) : tOpenOk=0',
'C(AnvilFontFileStep(0,token,4),0)',
'C(tHandle,0)',
' tOpenOk=1 : token=AnvilFontFileBegin(0,"font",4,32) : tGeneration[0]=tGeneration[0]+1',
'C(AnvilFontFileStep(0,token,4),0)',
'C(tHandle,0)',
' token=AnvilFontFileBegin(0,"font",4,32) : tInvalid=1',
'C(AnvilFontFileStep(0,token,32),0)',
'C(tBytes[0],0)',
'C(tHandle,0)',
'C(tSelected,3)',
' tInvalid=0 : token=AnvilFontFileBegin(0,"font",4,8)',
'C(AnvilFontFileStep(0,token,4),0)',
'C(tHandle,0)',
' token=AnvilFontFileBegin(0,"font",4,32)',
'C(AnvilFontFileCancel(0,token),1)',
'C(AnvilFontFileStep(0,token,4),0)',
'C(anvil_font_LoadFile(0,"font",4),1)',
'C(tHandle,0)',
'C(tSelected,3)',
]
s+='\n'.join(steps);layout=state_proof_layout(a.target)
s+=f'\n PokeI(${layout["report"]:X},$46494C45) : PokeI(${layout["report"]+8:X},checks) : PokeI(${layout["report"]+16:X},failure)\n ProcedureReturn failure\nEndProcedure\n'
d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);(d/'proof.pbi').write_text(s,encoding='utf8',newline='\n')
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t',a.target,'--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
payload=(d/'proof.img.pmf').read_bytes();(d/'identity.json').write_text(json.dumps(dict(target=a.target,checks=sum(x.startswith('C(') for x in steps),bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),source_hashes={rel:hashlib.sha256(raw).hexdigest()},checked_ranges=check_linked_layout(layout,log),executed=False,scope='Production file-owner procedures with controlled storage/parser seams; not real font-parser validation'),indent=2),encoding='utf8')