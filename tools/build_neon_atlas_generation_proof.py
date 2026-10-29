#!/usr/bin/env python3
"""Build the real Vulkan atlas transaction proof for physical Pi4 execution.

Fixed report: E1C00000:8192, pixels: E2400000:49152. Main returns zero on
success; --reference-adapter reproduces the prior in-place behavior as191.
Uncertain injection does not hang the GPU: it forces the owner to retain
resources after a real successful upload, then retires through real idle.
"""
from pathlib import Path
import subprocess,os,sys,hashlib,json
import argparse
from pmf_compiler import resolve_compiler
ap=argparse.ArgumentParser(description='Build a returning physical Pi4 atlas-generation proof; never runs an emulator.')
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--compiler')
ap.add_argument('--reference-adapter',type=Path,help='Optional prior adapter for the controlled old-behavior reproduction.')
ap.add_argument('--inject-uncertain',action='store_true',help='Test-only unknown-completion/idle refusal after a real successful GPU upload.')
args=ap.parse_args()
if args.reference_adapter and args.inject_uncertain:ap.error('Choose reference reproduction or uncertain-completion injection, not both.')
r=Path(__file__).resolve().parents[1];w=r
d=args.out.resolve();d.mkdir(parents=True,exist_ok=True)
variant='old' if args.reference_adapter else ('uncertain' if args.inject_uncertain else 'candidate')
source=(r/'RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4').read_text(encoding='utf8')
if variant=='old':source=source.replace('Anvil/Graphics/Vulkan/neon_vk_chrome.pbi',args.reference_adapter.resolve().as_posix())
source=source.replace('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 1',1)
helper=(r/'RaspberryPi4/Tests/Vulkan/neon_atlas_generation_proof.pbi').read_text(encoding='utf8');at=source.index('Procedure.i Main()');source=source[:at]+helper+'\n'+source[at:]
if variant=='uncertain':
 adapter=(r/'Anvil/Graphics/Vulkan/neon_vk_chrome.pbi').read_text(encoding='utf8');a=adapter.index('Procedure.i nvcAtlasReplaceGeneration()');b=adapter.index('\nEndProcedure',a);part=adapter[a:b]
 needle='  If rc = #VK_SUCCESS : rc = nvcAtlasUploadImage(image, #VK_IMAGE_LAYOUT_UNDEFINED, 0, 0) : EndIf';assert needle in part
 part=part.replace(needle,needle+'\n  If rc = #VK_SUCCESS And AtlasProofInject <> 0 : rc = #VK_ERROR_DEVICE_LOST : EndIf',1).replace('If vkDeviceWaitIdle(nvcDevice) <> #VK_SUCCESS','If AtlasProofWaitIdle(nvcDevice) <> #VK_SUCCESS',1)
 adapter=adapter[:a]+part+adapter[b:];private=d/'atlas-injected.pi4';private.write_text(adapter,encoding='utf8');source=source.replace('Anvil/Graphics/Vulkan/neon_vk_chrome.pbi',private.resolve().as_posix(),1)
 needle='  rc = NeonFontUse(oldFont, oldW, oldH, oldFirst, oldLast)\n  PokeI($E1C01018, swaps)';assert needle in source
 injected='''  If failure = 0
    oldImage = nvcAtlasImage : oldMemory = nvcAtlasMemory : oldView = nvcAtlasView : oldSet = nvcDescriptorSet
    AtlasProofInject = 1
    rc = NeonFontUse(oldFont, oldW, oldH, oldFirst, oldLast)
    If rc = 0 : rc = NeonVkChromeBegin(@nwClear[0]) : EndIf
    AtlasProofInject = 0
    PokeI($E1C01040, rc) : PokeI($E1C01048, nvcAtlasPendingImage)
    PokeI($E1C01050, atlasProofLiveMemory()) : PokeI($E1C01058, nvcReady)
    If rc <> #VK_ERROR_DEVICE_LOST Or nvcReady <> 0 Or nvcAtlasPendingImage = 0 Or nvcAtlasPendingMemory = 0 Or nvcAtlasPendingSet = 0 Or nvcAtlasPendingView = 0
      failure = 194
    EndIf
    If nvcAtlasImage <> oldImage Or nvcAtlasMemory <> oldMemory Or nvcAtlasView <> oldView Or nvcDescriptorSet <> oldSet : failure = 195 : EndIf
    If atlasProofLiveMemory() <> initialLive + 1 : failure = 196 : EndIf
    NeonVkChromeDestroy()
    PokeI($E1C01060, atlasProofLiveMemory()) : PokeI($E1C01068, nvcAtlasPendingImage)
    If nvcDevice <> 0 Or nvcAtlasPendingImage <> 0 Or nvcAtlasPendingMemory <> 0 Or nvcAtlasPendingView <> 0 Or nvcAtlasPendingSet <> 0 Or atlasProofLiveMemory() <> 1 : failure = 197 : EndIf
  EndIf
'''
 source=source.replace(needle,injected+needle,1)
 source='Global AtlasProofInject.i\nDeclare.i AtlasProofWaitIdle(device.i)\n'+source
 at=source.index('Procedure.i Main()');source=source[:at]+'''Procedure.i AtlasProofWaitIdle(device.i)
 If AtlasProofInject <> 0 : ProcedureReturn #VK_TIMEOUT : EndIf
 ProcedureReturn vkDeviceWaitIdle(device)
EndProcedure
'''+source[at:]
source=source.replace('Procedure.i Main()','Procedure.i AtlasDiagnosticMain()',1)
needle='  ; Destroy the production adapter first:';assert needle in source;source=source.replace(needle,'  PokeI($E1C01000, atlasTransactionProof(imageBase, imagePitch))\n'+needle,1)
source+='''
Procedure.i Main(services.i)
 Define report.i, i.i, status.i
 For i = 0 To 8191 : PokeA($E1C00000 + i, 0) : Next
 PokeI($E1C01000, -1)
 report = AtlasDiagnosticMain()
 PokeI($E1C01070, atlasProofLiveMemory())
 If report = 0 : ProcedureReturn 199 : EndIf
 For i = 0 To 255 : PokeA($E1C00000 + i, PeekA(report + i)) : Next
 status = PeekL($E1C00004)
 If status <> 0 : ProcedureReturn 1000 + status : EndIf
 ProcedureReturn PeekI($E1C01000)
EndProcedure
'''
if variant!='uncertain':source=source.replace(' PokeI($E1C01070, atlasProofLiveMemory())\n','')
(d/'proof.pi4').write_text(source,encoding='utf8');exe=Path(resolve_compiler(args.compiler));env=os.environ.copy();env['PMF_ROOT']=str(r)
q=subprocess.run([str(exe),'--compile',str((d/'proof.pi4').resolve()),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str((d/'proof.img').resolve())],capture_output=True,encoding='utf8',timeout=240,creationflags=subprocess.CREATE_NO_WINDOW,env=env);(d/'compile.txt').write_text(q.stdout+q.stderr);print((q.stdout+q.stderr)[-1200:]);assert q.returncode==0
(d/'identity.json').write_text(json.dumps(dict(variant=variant,bytes=(d/'proof.img.pmf').stat().st_size,sha256=hashlib.sha256((d/'proof.img.pmf').read_bytes()).hexdigest()),indent=2))
