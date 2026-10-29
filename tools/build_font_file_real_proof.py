"""Build the incremental owner against real TrueType modules and font bytes."""
from pathlib import Path
import argparse,re,json,hashlib,os,subprocess
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
r=Path(__file__).resolve().parents[1];source=(r/'Anvil/Core/font_cmd.pbi').read_text(encoding='utf8')
modules=['Anvil/Graphics/truetype.pbi','Anvil/Graphics/truetype_metrics.pbi','Anvil/Graphics/truetype_cmap.pbi','Anvil/Graphics/truetype_outlines.pbi','Anvil/Graphics/truetype_raster.pbi','Anvil/Graphics/truetype_kern.pbi','Anvil/Graphics/truetype_gpos.pbi','Anvil/Graphics/truetype_controls.pbi','Anvil/Graphics/truetype_layout.pbi','Anvil/Graphics/truetype_slots.pbi','RaspberryPi4/Monitor/anvil_boot_ttf.pi4']
s=''.join('XIncludeFile "'+n+'"\n' for n in modules)
s+=source[:source.index('; Begin an incremental file load')]
for name in ['AnvilFontFileBegin','AnvilFontFileCancel','AnvilFontFileStep','anvil_font_SlotAddress','anvil_font_CopySlotPath']:
 found=re.findall(r'(?ms)^Procedure\.\w+ '+name+r'\(.*?^EndProcedure',source);assert len(found)==1;s+=found[0]+'\n'
s+='XIncludeFile "Anvil/Core/font_boot_embedded.pbi"\n'
s+='''
Global handle.i,reads.i,corrupt.i,checks.i,failure.i
Procedure str_print_at(text.i)
EndProcedure
Procedure PrintNl()
EndProcedure
Procedure PrintDec(value.i)
EndProcedure
Procedure.i HwStorageUp()
 ProcedureReturn 1
EndProcedure
Procedure.i HwFileOpen(path.i)
 handle=handle+1
 ProcedureReturn 1
EndProcedure
Procedure.i HwFileSize()
 ProcedureReturn #ANVIL_BOOT_TTF_BYTES
EndProcedure
Procedure HwFileClose()
 handle=handle-1
EndProcedure
Procedure.i HwFileReadAt(offset.i,target.i,bytes.i)
 Protected i.i
 reads=reads+1
 For i=0 To bytes-1 : PokeA(target+i,PeekA(?anvilBootTtf+offset+i)) : Next
 If corrupt And offset=0 : PokeA(target,$FF) : EndIf
 ProcedureReturn bytes
EndProcedure
Procedure C(actual.i,expected.i)
 checks=checks+1
 If actual<>expected And failure=0 : failure=checks : EndIf
EndProcedure
Procedure.i Main(services.i)
 Protected token.i,rc.i,steps.i,bad.i,i.i,glyph.i,advance.i,bearing.i,oldAdvance.i
 C(AnvilFontBootEmbeddedInit(),1)
 C(AnvilTrueTypeSlotSelected(),#ANVIL_TTS_BOOT_SLOT)
 C(AnvilTrueTypeSlotParserBound(),1)
 glyph=AnvilTrueTypeGlyphForCodepoint(65)
 C(AnvilTrueTypeHorizontalMetric(glyph,@oldAdvance,@bearing),1)
 token=AnvilFontFileBegin(0,"memory-font",11,#ANVIL_FONT_MAX_BYTES)
 C(Bool(token>0),1)
 rc=1 : steps=0 : bad=0
 While rc=1 And steps<300
  rc=AnvilFontFileStep(0,token,4096) : steps=steps+1
  If handle<>0 Or AnvilTrueTypeSlotSelected()<>#ANVIL_TTS_BOOT_SLOT Or AnvilTrueTypeSlotParserBound()<>1 : bad=1 : EndIf
 Wend
 C(rc,2)
 C(bad,0)
 C(reads,(#ANVIL_BOOT_TTF_BYTES+4095)/4096)
 C(AnvilTrueTypeSlotBytes(0),#ANVIL_BOOT_TTF_BYTES)
 C(AnvilTrueTypeSlotSelect(0),1)
 C(AnvilTrueTypeHorizontalMetric(glyph,@advance,@bearing),1)
 C(advance,oldAdvance)
 For i=0 To #ANVIL_BOOT_TTF_BYTES-1
  If PeekA(anvil_font_SlotAddress(0)+i)<>PeekA(?anvilBootTtf+i) : bad=1 : EndIf
 Next
 C(bad,0)
 C(anvil_font_slot_path[0],109)
 C(anvil_font_slot_path[11],0)
 corrupt=1
 token=AnvilFontFileBegin(1,"broken-font",11,#ANVIL_FONT_MAX_BYTES)
 C(Bool(token>0),1)
 rc=1 : steps=0 : bad=0
 While rc=1 And steps<300
  rc=AnvilFontFileStep(1,token,4096) : steps=steps+1
  If handle<>0 Or AnvilTrueTypeSlotSelected()<>0 Or AnvilTrueTypeSlotParserBound()<>1 : bad=1 : EndIf
 Wend
 C(rc,0)
 C(bad,0)
 C(AnvilTrueTypeSlotBytes(1),0)
 C(anvil_font_slot_path[#ANVIL_FONT_PATH_BYTES],0)
 C(AnvilTrueTypeHorizontalMetric(glyph,@advance,@bearing),1)
 C(advance,oldAdvance)
 C(AnvilFontFileCancel(1,token),0)
 C(AnvilTrueTypeSlotSelect(#ANVIL_TTS_BOOT_SLOT),1)
 C(AnvilTrueTypeSlotUnload(0),1)
 C(handle,0)
'''
checks=len(re.findall(r'(?m)^ C\(',s));layout=state_proof_layout('pi4')
s+=f' PokeI(${layout["report"]:X},$46524541) : PokeI(${layout["report"]+8:X},checks) : PokeI(${layout["report"]+16:X},failure)\n ProcedureReturn failure\nEndProcedure\n'
d=a.out.resolve();d.mkdir(parents=True,exist_ok=False);(d/'proof.pbi').write_text(s,encoding='utf8',newline='\n')
q=subprocess.run([str(resolve_compiler(a.compiler)),'--compile',str(d/'proof.pbi'),'-t','pi4','--load-addr',hex(layout['load']),'--stack-addr',hex(layout['stack']),'--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8');print(log[-1800:]);assert q.returncode==0
payload=(d/'proof.img.pmf').read_bytes();modules+=['Anvil/Core/font_cmd.pbi','Anvil/Core/font_boot_embedded.pbi'];(d/'identity.json').write_text(json.dumps(dict(target='pi4',checks=checks,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),source_hashes={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in modules},checked_ranges=check_linked_layout(layout,log),executed=False,scope='Actual parser/font/slot owner; storage reads from immutable embedded bytes, not a filesystem device'),indent=2),encoding='utf8')