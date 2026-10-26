#!/usr/bin/env python3
"""Build a returning physical Pi 4 line-placement proof; does not execute it.

Eight GPU frames: four rotations, reference quads and compact instancing.
Sixteen arithmetic nodes render; seventeen refuse before publication. Report
E1C00000:8192, logical pixel captures E2400000:131072. No emulation.
"""
from pathlib import Path
import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--compiler')
args=ap.parse_args()
r=Path(__file__).resolve().parents[1]
d=args.out.resolve();d.mkdir(parents=True,exist_ok=True)
helper=(r/'Anvil/Graphics/Vulkan/Tests/vertex_shared_vpm_proof.pbi').read_text(encoding='utf8')
s=(r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_text(encoding='utf8').replace('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 1',1)

at=s.index('Procedure.i Main()');s=s[:at]+helper+'\n'+s[at:];s=s.replace('Procedure.i Main()','Procedure.i LineDiagnosticMain()',1)
s=s.replace('  ; Destroy the production adapter first:','  PokeI($E1C01000,lineContractProof(imageBase,imagePitch,framebuffer))\n  ; Destroy the production adapter first:',1)
s+='''
Procedure.i Main(services.i)
 Define report.i,i.i,live.i
 For i=0 To 8191 : PokeA($E1C00000+i,0) : Next
 PokeI($E1C01000,-1)
 report=LineDiagnosticMain()
 If report=0 : ProcedureReturn 199 : EndIf
 For i=0 To 255 : PokeA($E1C00000+i,PeekA(report+i)) : Next
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : live=live+1 : EndIf : Next
 PokeI($E1C01188,live)
 If PeekL($E1C00004)<>0 : ProcedureReturn 1000+PeekL($E1C00004) : EndIf
 ProcedureReturn PeekI($E1C01000)
EndProcedure
'''
(d/'proof.pi4').write_text(s,encoding='utf8')
import subprocess,os,hashlib,json
exe=Path(resolve_compiler(args.compiler));env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(exe),'--compile',str((d/'proof.pi4').resolve()),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str((d/'proof.img').resolve())],capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW,env=env)
(d/'compile.txt').write_text(q.stdout+q.stderr);print((q.stdout+q.stderr)[-1600:]);assert q.returncode==0
(d/'identity.json').write_text(json.dumps(dict(bytes=(d/'proof.img.pmf').stat().st_size,sha256=hashlib.sha256((d/'proof.img.pmf').read_bytes()).hexdigest()),indent=2))
