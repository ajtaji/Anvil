"""Build actual attachment color-load, target lifecycle and keyboard qualification."""
from pathlib import Path
import os,subprocess,json,hashlib,sys,argparse,re
from pmf_compiler import resolve_compiler
from vulkan_state_proof_layouts import state_proof_layout,check_linked_layout
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--compiler',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--filtering',action='store_true');ap.add_argument('--subtract',action='store_true');ap.add_argument('--subtract-vertex',action='store_true');ap.add_argument('--computed-uv',action='store_true');ap.add_argument('--dot',action='store_true');ap.add_argument('--scale',action='store_true');ap.add_argument('--curvature',action='store_true');ap.add_argument('--sine',action='store_true');ap.add_argument('--scanline',action='store_true');ap.add_argument('--curved-scanline',action='store_true');ap.add_argument('--distance',action='store_true');ap.add_argument('--smoothstep',action='store_true');ap.add_argument('--vignette',action='store_true');a=ap.parse_args();assert not a.vignette or a.curved_scanline;assert not a.smoothstep or (a.sine and not a.scanline and not a.distance);assert not a.distance or (a.sine and not a.scanline);assert not a.curved_scanline or a.scanline;assert not a.scanline or a.sine;assert not a.sine or (a.computed_uv and not a.dot and not a.curvature);assert not a.curvature or (a.computed_uv and not a.dot and not a.scale);assert not a.scale or a.dot;assert not a.dot or a.computed_uv;assert not a.subtract_vertex or a.subtract;assert not a.computed_uv or not a.subtract
 r=Path(__file__).resolve().parents[1];d=a.out.resolve();d.mkdir(parents=True,exist_ok=False)
 name='RaspberryPi4/Examples/Diagnostics/vulkanNeonWidgetAll15Proof.pi4'
 original=(r/name).read_bytes();s=original.decode('utf-8-sig')
 for before,after in [('#NW_ARENA             = $0A000000','#NW_ARENA             = $05000000'),('#NW_SURFACE           = $06000000','#NW_SURFACE           = $03000000'),('#NW_WINDOW            = $063E8000','#NW_WINDOW            = $033E8000'),('#NW_BANNER0           = $07000000','#NW_BANNER0           = $04000000'),('#NW_BANNER90          = $07060000','#NW_BANNER90          = $04060000'),('#NW_BANNER270         = $07100000','#NW_BANNER270         = $04100000'),('#NW_BANNER_CHANGED    = $071A0000','#NW_BANNER_CHANGED    = $041A0000'),('#NW_PROOF_MODE        = 0','#NW_PROOF_MODE        = 20')]:
  assert s.count(before)==1,before;s=s.replace(before,after)
 s=s.replace('#NW_WINDOW_BYTES      = $00C00000','#NW_WINDOW_BYTES      = $01000000').replace('#NW_MAP_SPAN          = $00FE8000','#NW_MAP_SPAN          = $013E8000')
 s='#NCT_ATTACHMENT_LOAD_PROOF=6\n#ANVIL_VULKAN_BACKEND=1\nXIncludeFile "RaspberryPi4/Monitor/anvil_boot_ttf.pi4"\n'+s
 inc='XIncludeFile "RaspberryPi4/Lib/Vulkan/vk_v3d_backend.pi4"';assert s.count(inc)==1
 s=s.replace(inc,inc+'\nXIncludeFile "Anvil/Graphics/Vulkan/vk_backend_select.pbi"')
 s=s.replace('  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4 : adapterDraws = 128 : adapterQuads = 512 : EndIf','  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4 Or #NW_PROOF_MODE = 20 : adapterDraws = 128 : adapterQuads = 512 : EndIf')

 fixture=(r/'RaspberryPi4/Tests/Vulkan/neon_canvas_keyboard.pbi').read_text()
 before='Global NcdFailure.i';assert fixture.count(before)==1
 fixture=fixture.replace(before,'XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_canvas_targets.pbi"\n'+before)
 before=r'  image=NcdCanvas\image : memory=NcdCanvas\memory : view=NcdCanvas\view'
 assert fixture.count(before)==1
 fixture=fixture.replace(before,'  If NeonCanvasTargetsProof(@NcdCanvas,@NcdScratch[0],1920000)<>0 : NcdFailure=9009 : PokeI($E1C00010,NcdFailure) : Goto NcdCleanup : EndIf\n'+before)
 if a.filtering:
  fixture=fixture.replace("Global NcdFailure.i",'XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_canvas_filter.pbi"\nGlobal NcdFailure.i')
  marker='  image=NcdCanvas\\image : memory=NcdCanvas\\memory : view=NcdCanvas\\view'
  assert fixture.count(marker)==1
  fixture=fixture.replace(marker,'  If NeonCanvasFilterProof(@NcdCanvas)<>0 : NcdFailure=9010 : PokeI($E1C00010,NcdFailure) : Goto NcdCleanup : EndIf\n'+marker)
 if a.computed_uv:
  fixture=fixture.replace('Global NcdFailure.i','XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi"\nGlobal NcdFailure.i')
  marker='  image=NcdCanvas\\image : memory=NcdCanvas\\memory : view=NcdCanvas\\view'
  assert fixture.count(marker)==1
  fixture=fixture.replace(marker,'  If NeonCanvasComputedUvProof(@NcdCanvas)<>0 : NcdFailure=9011 : PokeI($E1C00010,NcdFailure) : Goto NcdCleanup : EndIf\n'+marker)
 if a.smoothstep:
  fixture=fixture.replace('RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi','RaspberryPi4/Tests/Vulkan/neon_smoothstep.pbi')

 if a.distance:
  fixture=fixture.replace('RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi','RaspberryPi4/Tests/Vulkan/neon_distance.pbi')

 if a.vignette:
  fixture=fixture.replace('RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi','RaspberryPi4/Tests/Vulkan/neon_vignette.pbi')

 if a.curved_scanline:
  fixture=fixture.replace('RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi','RaspberryPi4/Tests/Vulkan/neon_curved_scanline.pbi')

 if a.scanline:
  fixture=fixture.replace('RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi','RaspberryPi4/Tests/Vulkan/neon_scanline.pbi')
 if a.sine:
  fixture=fixture.replace('RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi','RaspberryPi4/Tests/Vulkan/neon_sine.pbi')
 if a.curvature:
  fixture=fixture.replace('RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi','RaspberryPi4/Tests/Vulkan/neon_curvature.pbi')
 if a.dot:
  probe=(r/'RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi').read_text(encoding='utf8')
  probe=probe.replace('    vkUnmapMemory(nvcDevice,nvcUniformMemory)','    If bits<>0 : PokeL(mapped+4,$3F000000) : EndIf\n    vkUnmapMemory(nvcDevice,nvcUniformMemory)')
  marker='    vkUnmapMemory(*primary\\target\\device,*primary\\memory)'
  extra='    PokeI($E1C03F10+trial*24,PeekN(mapped+4* *primary\\pitch))\n    PokeI($E1C03F18+trial*24,PeekN(mapped+4* *primary\\pitch+1*4))\n    PokeI($E1C03F20+trial*24,PeekN(mapped+4* *primary\\pitch+5*4))\n'
  assert probe.count(marker)==1;probe=probe.replace(marker,extra+marker)
  dot_probe=d/'dot_probe.pbi';dot_probe.write_text(probe,encoding='utf8',newline='\n')
  fixture=fixture.replace('XIncludeFile "RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi"','XIncludeFile "'+dot_probe.as_posix()+'"')
 generated=d/'targets_fixture.pbi';generated.write_text(fixture,encoding='utf8',newline='\n')

 anchor='Procedure.i Main()';assert s.count(anchor)==1
 s=s.replace(anchor,'XIncludeFile "'+str(generated).replace("\\","/")+'"\nProcedure.i SceneDiagnosticMain()')
 anchor='  If #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4\n    ; All captures';assert s.count(anchor)==1
 s=s.replace(anchor,'  If #NW_PROOF_MODE = 20\n    NalWsiInstance=inst : rc=NcdFrame(dev,renderPass,framebuffer,imageBase,imagePitch)\n    nwPut(#NW_S_SCENE_RC,rc)\n  ElseIf #NW_PROOF_MODE = 3 Or #NW_PROOF_MODE = 4\n    ; All captures')
 anchor='  ProcedureReturn nwReturn(#NW_OK)\nEndProcedure';assert s.count(anchor)==1
 s=s.replace(anchor,'  If #NW_PROOF_MODE=20 And nwGet(#NW_S_SCENE_RC)<>0 : ProcedureReturn nwReturn(#NW_ERR_SCENE) : EndIf\n'+anchor)
 anchor='  nwPut(#NW_S_STEP, 8)\n  NeonVkChromeDestroy()';assert s.count(anchor)==1
 s=s.replace(anchor,'  nwPut(#NW_S_STEP, 8)\n  rc=NeonVkChromeDestroyChecked()\n  If rc<>0 : ProcedureReturn nwReturn(#NW_ERR_ADAPTER) : EndIf')
 s+='''
Procedure.i Main(services.i)
  Protected report.i,i.i
  For i=0 To 16383 : PokeA($E1C00000+i,0) : Next
  PokeI($E1C00000,$4E434431) : PokeI($E1C00008,2)
  NcdClear[3]=$3F800000
  report=SceneDiagnosticMain()
  If report=0 : ProcedureReturn 199 : EndIf
  PokeI($E1C00020,PeekL(report+4))
  PokeI($E1C00028,AnvilVkFaultCode()) : PokeI($E1C00030,AnvilVkFaultCount())
  If PeekL(report+4)<>0 : ProcedureReturn PeekL(report+4) : EndIf
  ProcedureReturn NcdFailure
EndProcedure
'''
 shader_path=None;shader_text=None;shader_original=None;shader_name='Anvil/Graphics/Vulkan/neon_vk_chrome.pbi'
 if a.subtract:
  shader_original=(r/shader_name).read_bytes();shader_text=shader_original.decode('utf-8-sig')
  start=shader_text.index('Procedure.i nvcBuildFragmentShader()');end=shader_text.index('EndProcedure',start)
  body=shader_text[start:end];assert body.count('vtpHeader(35)')==1
  body=body.replace('vtpHeader(35)','vtpHeader(37)')
  old='  vtpIns(129, 4) : vtpW(5) : vtpW(34) : vtpW(33) : vtpW(30)'
  assert body.count(old)==1
  new='  vtpIns(129, 4) : vtpW(5) : vtpW(35) : vtpW(33) : vtpW(33)\n  vtpIns(131, 4) : vtpW(5) : vtpW(36) : vtpW(35) : vtpW(33)\n'+old.replace('vtpW(33)','vtpW(36)')
  body=body.replace(old,new);shader_text=shader_text[:start]+body+shader_text[end:]
  if a.subtract_vertex:
   vertex=(r/'Anvil/Graphics/Vulkan/vk_spirv_fixtures.pbi').read_text(encoding='utf8')
   start=vertex.index('Procedure.i vtpBuildVsD()');end=vertex.index('EndProcedure',start)+len('EndProcedure')
   vertex=vertex[start:end].replace('vtpBuildVsD','subtractBuildVsD').replace('vtpHeader(28)','vtpHeader(32)')
   construct='  vtpIns(#VTP_OpCompositeConstruct, 6) : vtpW(5) : vtpW(24) : vtpW(22) : vtpW(23) : vtpW(13) : vtpW(14)'
   assert vertex.count(construct)==1
   arithmetic='  vtpIns(129, 4) : vtpW(3) : vtpW(28) : vtpW(22) : vtpW(22)\n  vtpIns(131, 4) : vtpW(3) : vtpW(29) : vtpW(28) : vtpW(22)\n  vtpIns(129, 4) : vtpW(3) : vtpW(30) : vtpW(23) : vtpW(23)\n  vtpIns(131, 4) : vtpW(3) : vtpW(31) : vtpW(30) : vtpW(23)\n'
   vertex=vertex.replace(construct,arithmetic+construct.replace('vtpW(22)','vtpW(29)').replace('vtpW(23)','vtpW(31)'))
   assert shader_text.count('vsBytes = vtpBuildVsD()')==1
   shader_text=shader_text.replace('vsBytes = vtpBuildVsD()','vsBytes = subtractBuildVsD()')
   shader_text=shader_text.replace('Procedure.i nvcBuildFragmentShader()',vertex+'\n\nProcedure.i nvcBuildFragmentShader()',1)
  shader_path=d/'subtract_chrome.pbi';shader_path.write_text(shader_text,encoding='utf8',newline='\n')
  old='XIncludeFile "'+shader_name+'"';assert s.count(old)==1
  s=s.replace(old,'XIncludeFile "'+shader_path.as_posix()+'"')
 if a.computed_uv:
  shader_original=(r/shader_name).read_bytes();shader_text=shader_original.decode('utf-8-sig')
  start=shader_text.index('Procedure.i nvcBuildFragmentShader()');end=shader_text.index('EndProcedure',start)
  body=shader_text[start:end].replace('vtpHeader(35)','vtpHeader(39)')
  sample='  vtpIns(#VTP_OpImageSampleImplicitLod, 4) : vtpW(5) : vtpW(28) : vtpW(26) : vtpW(27)'
  assert body.count(sample)==1;body=body.replace(sample+'\n','')
  load='  vtpIns(#VTP_OpLoad, 3) : vtpW(5) : vtpW(30) : vtpW(29)'
  transform='\n  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(35) : vtpW(30) : vtpW(0)\n  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(36) : vtpW(30) : vtpW(1)\n  vtpIns(#VTP_OpCompositeConstruct, 4) : vtpW(4) : vtpW(37) : vtpW(35) : vtpW(36)\n  vtpIns(129, 4) : vtpW(4) : vtpW(38) : vtpW(27) : vtpW(37)\n'+sample.replace('vtpW(27)','vtpW(38)')
  assert body.count(load)==1;body=body.replace(load,load+transform)
  add='  vtpIns(129, 4) : vtpW(5) : vtpW(34) : vtpW(33) : vtpW(30)'
  assert body.count(add)==1;body=body.replace(add+'\n','').replace('vtpW(13) : vtpW(34)','vtpW(13) : vtpW(33)')
  if a.dot:
   body=body.replace('vtpHeader(39)','vtpHeader(44)')
   function='  vtpIns(#VTP_OpFunction, 4)'
   declaration='  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(39) : vtpW($3F000000)\n  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(40) : vtpW($3E800000)\n  vtpIns(44, 4) : vtpW(4) : vtpW(41) : vtpW(39) : vtpW(40)\n'
   body=body.replace(function,declaration+function,1)
   addition='  vtpIns(129, 4) : vtpW(4) : vtpW(38) : vtpW(27) : vtpW(37)'
   dot='  vtpIns(148, 4) : vtpW(3) : vtpW(42) : vtpW(37) : vtpW(41)\n  vtpIns(#VTP_OpCompositeConstruct, 4) : vtpW(4) : vtpW(43) : vtpW(42) : vtpW(36)\n'
   assert body.count(addition)==1;body=body.replace(addition,dot+addition.replace('vtpW(37)','vtpW(43)'))
  if a.scale:
   body=body.replace('vtpHeader(44)','vtpHeader(46)')
   function='  vtpIns(#VTP_OpFunction, 4)'
   body=body.replace(function,'  vtpIns(#VTP_OpConstant, 3) : vtpW(3) : vtpW(45) : vtpW($40000000)\n'+function,1)
   dot='  vtpIns(148, 4) : vtpW(3) : vtpW(42) : vtpW(37) : vtpW(41)'
   scale='  vtpIns(142, 4) : vtpW(4) : vtpW(44) : vtpW(37) : vtpW(45)\n'
   assert body.count(dot)==1;body=body.replace(dot,scale+dot.replace('vtpW(37)','vtpW(44)'))
  if a.curvature:
   body=body.replace('vtpHeader(39)','vtpHeader(51)')
   function='  vtpIns(#VTP_OpFunction, 4)'
   declarations=[(43,[3,39,0x40000000]),(43,[3,40,0x3f800000]),(43,[3,41,0x3f000000]),(44,[4,42,40,40]),(44,[4,43,41,41])]
   def instruction(op,operands):return '  vtpIns('+str(op)+', '+str(len(operands))+')'+''.join(' : vtpW($'+format(v,'X')+')' for v in operands)+'\n'
   body=body.replace(function,''.join(instruction(op,args) for op,args in declarations)+function,1)
   first=body.index('  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(36)')
   last=body.index('  vtpIns(#VTP_OpImageSampleImplicitLod',first)
   curve=[(142,[4,44,27,39]),(131,[4,45,44,42]),(148,[3,46,45,45]),(142,[4,47,45,46]),(142,[4,48,47,35]),(129,[4,49,45,48]),(142,[4,50,49,41]),(129,[4,38,50,43])]
   body=body[:first]+''.join(instruction(op,args) for op,args in curve)+body[last:]
  if a.sine:
   body=body.replace('vtpHeader(39)','vtpHeader(43)')
   def instruction(op,operands):return '  vtpIns('+str(op)+', '+str(len(operands))+')'+''.join(' : vtpW($'+format(v,'X')+')' for v in operands)+'\n'
   marker='  vtpIns(#VTP_OpMemoryModel, 2)'
   body=body.replace(marker,instruction(11,[39,0x4c534c47,0x6474732e,0x3035342e,0])+marker,1)
   marker='  vtpIns(#VTP_OpFunction, 4)'
   body=body.replace(marker,instruction(43,[3,40,0x3e800000])+marker,1)
   first=body.index('  vtpIns(#VTP_OpCompositeExtract, 4) : vtpW(3) : vtpW(35)')
   last=body.index('  vtpIns(#VTP_OpImageSampleImplicitLod',first)
   body=body[:first]+body[last:]
   body=body.replace('vtpW(28) : vtpW(26) : vtpW(38)','vtpW(28) : vtpW(26) : vtpW(27)')
   marker='  vtpIns(#VTP_OpStore, 2) : vtpW(13) : vtpW(33)'
   arithmetic=instruction(12,[5,41,39,13,30])+instruction(142,[5,42,41,40])+instruction(129,[5,34,33,42])
   assert body.count(marker)==1
   body=body.replace(marker,arithmetic+marker.replace('vtpW(33)','vtpW(34)'))
  if a.scanline:
   body=body.replace('vtpHeader(43)','vtpHeader(57)')
   marker='  vtpIns(#VTP_OpFunction, 4)'
   constants=[(43,[3,44,0x44480000]),(43,[3,45,0x41200000]),(43,[3,46,0x3d23d70a]),(43,[3,47,0])]
   body=body.replace(marker,''.join(instruction(op,args) for op,args in constants)+marker,1)
   first=body.index('  vtpIns(12, 5)')
   last=body.index('  vtpIns(#VTP_OpStore',first)
   graph=[(81,[3,43,27,1]),(133,[3,48,43,44]),(81,[3,49,30,0]),(133,[3,50,49,45]),(131,[3,51,48,50]),(12,[3,52,39,13,51]),(133,[3,53,52,46]),(81,[3,54,30,1]),(133,[3,55,53,54]),(80,[5,56,55,55,55,47]),(131,[5,34,33,56])]
   body=body[:first]+''.join(instruction(op,args) for op,args in graph)+body[last:]
  if a.curved_scanline:
   body=body.replace('vtpHeader(57)','vtpHeader(75)')
   marker='  vtpIns(#VTP_OpFunction, 4)'
   constants=[(43,[3,60,0x40000000]),(43,[3,61,0x3f800000]),(43,[3,62,0x3f000000]),(44,[4,64,61,61]),(44,[4,65,62,62])]
   body=body.replace(marker,''.join(instruction(op,args) for op,args in constants)+marker,1)
   marker='  vtpIns(#VTP_OpImageSampleImplicitLod, 4) : vtpW(5) : vtpW(28) : vtpW(26) : vtpW(27)'
   graph=[(81,[3,74,30,2]),(142,[4,66,27,60]),(131,[4,67,66,64]),(148,[3,68,67,67]),(142,[4,69,67,68]),(142,[4,70,69,74]),(129,[4,71,67,70]),(142,[4,72,71,62]),(129,[4,73,72,65])]
   assert body.count(marker)==1
   body=body.replace(marker,''.join(instruction(op,args) for op,args in graph)+marker.replace('vtpW(27)','vtpW(73)'))
   body=body.replace(instruction(81,[3,43,27,1]),instruction(81,[3,43,73,1]))
  if a.distance:
   body=body.replace('vtpHeader(43)','vtpHeader(48)')
   marker='  vtpIns(#VTP_OpFunction, 4)'
   constants=[(43,[3,41,0x3f000000]),(44,[5,42,40,40,40,40]),(43,[3,43,0])]
   body=body.replace(marker,''.join(instruction(op,args) for op,args in constants)+marker,1)
   first=body.index('  vtpIns(12, 5)');last=body.index('  vtpIns(#VTP_OpStore',first)
   graph=[(12,[3,44,39,67,30,42]),(131,[3,45,44,41]),(133,[3,46,45,40]),(80,[5,47,46,46,46,43]),(129,[5,34,33,47])]
   body=body[:first]+''.join(instruction(op,args) for op,args in graph)+body[last:]
  if a.smoothstep:
   body=body.replace('vtpHeader(43)','vtpHeader(51)')
   marker='  vtpIns(#VTP_OpFunction, 4)'
   constants=[(43,[3,41,0x3e99999a]),(43,[3,42,0x3f4ccccd]),(44,[5,43,41,41,41,41]),(44,[5,44,42,42,42,42]),(43,[3,50,0])]
   body=body.replace(marker,''.join(instruction(op,args) for op,args in constants)+marker,1)
   first=body.index('  vtpIns(12, 5)');last=body.index('  vtpIns(#VTP_OpStore',first)
   graph=[(12,[5,45,39,49,43,44,30]),(81,[3,46,45,0]),(81,[3,47,45,1]),(81,[3,48,45,2]),(80,[5,49,46,47,48,50]),(142,[5,42+9,49,40]),(129,[5,34,33,42+9])]
   body=body.replace('vtpHeader(51)','vtpHeader(52)')
   body=body[:first]+''.join(instruction(op,args) for op,args in graph)+body[last:]
  if a.vignette:
   body=body.replace('vtpHeader(75)','vtpHeader(83)')
   marker='  vtpIns(#VTP_OpFunction, 4)'
   constants=[(43,[3,81,0x3e99999a]),(43,[3,82,0x3f4ccccd])]
   body=body.replace(marker,''.join(instruction(op,args) for op,args in constants)+marker,1)
   marker=instruction(131,[5,34,33,56]);assert body.count(marker)==1
   graph=[(131,[5,75,33,56]),(12,[3,76,39,67,73,65]),(12,[3,77,39,49,81,82,76]),(133,[3,78,77,54]),(131,[3,79,61,78]),(80,[5,80,79,79,79,61]),(133,[5,34,75,80])]
   body=body.replace(marker,''.join(instruction(op,args) for op,args in graph))
  shader_text=shader_text[:start]+body+shader_text[end:]
  lines=[]
  for line in shader_text.splitlines():
   lines.append(line)
   if 'rc = vkCreateShaderModule(' in line or 'rc = vkCreateGraphicsPipelines(' in line:
    lines.append('  If rc<>0 : PokeI($E1C03FA0,rc) : PokeI($E1C03FA8,AnvilVkIrV3d42Error()) : PokeI($E1C03FB0,AnvilVkIrV3d42SourceId()) : PokeI($E1C03FB8,AnvilVkIrV3d42SourceOpcode()) : PokeI($E1C03FC0,AnvilVkIrV3d42Stage()) : PokeI($E1C03FC8,avkqError) : PokeI($E1C03FD0,avkqStage) : EndIf')
  shader_text='\n'.join(lines)+'\n'
  shader_path=d/'computed_uv_chrome.pbi';shader_path.write_text(shader_text,encoding='utf8',newline='\n')
  old='XIncludeFile "'+shader_name+'"';assert s.count(old)==1
  s=s.replace(old,'XIncludeFile "'+shader_path.as_posix()+'"')
 pending=[(s,None)];inputs={};missing=[];seenGenerated=False
 while pending:
  text,owner=pending.pop(0)
  for spelling in re.findall(r'(?mi)^\s*X?IncludeFile\s+"([^"]+)"',text):
   p=r/spelling.replace('\\','/')
   if not p.is_file() and owner:p=(r/owner).parent/spelling
   p=p.resolve()
   if p==generated:
    if not seenGenerated:pending.append((fixture,None));seenGenerated=True
    continue
   if shader_path is not None and p==shader_path:
    if shader_name not in inputs:
     inputs[shader_name]=hashlib.sha256(shader_original).hexdigest();pending.append((shader_text,shader_name))
    continue
   if a.dot and p==dot_probe:
    n='RaspberryPi4/Tests/Vulkan/neon_computed_uv.pbi'
    if n not in inputs:inputs[n]=hashlib.sha256((r/n).read_bytes()).hexdigest();pending.append((probe,n))
    continue
   assert p.is_relative_to(r)
   n=p.relative_to(r).as_posix()
   if n in inputs or n in missing:continue
   assert len(inputs)+len(missing)<256
   if not p.is_file():missing.append(n);continue
   blob=p.read_bytes();inputs[n]=hashlib.sha256(blob).hexdigest();pending.append((blob.decode('utf-8-sig'),n))
 assert not missing,missing
 inputs[name]=hashlib.sha256(original).hexdigest()
 inputs['tools/neon_canvas_keyboard_cases.json']=hashlib.sha256((r/'tools/neon_canvas_keyboard_cases.json').read_bytes()).hexdigest()
 inputs['RaspberryPi4/Tests/Vulkan/neon_canvas_keyboard.pbi']=hashlib.sha256((r/'RaspberryPi4/Tests/Vulkan/neon_canvas_keyboard.pbi').read_bytes()).hexdigest()
 (d/'proof.pi4').write_text(s,encoding='utf8',newline='\n')
 compiler=resolve_compiler(a.compiler)
 q=subprocess.run([str(compiler),'--compile',str(d/'proof.pi4'),'-t','pi4','--load-addr','0x1000000','--stack-addr','0x4F00000','--entry-returns','--wants-services','-o',str(d/'proof.img')],env=dict(os.environ,PMF_ROOT=str(r)),capture_output=True,text=True,encoding='utf8',timeout=200,creationflags=subprocess.CREATE_NO_WINDOW)
 log=q.stdout+q.stderr;(d/'compile.txt').write_text(log,encoding='utf8',newline='\n');print(log[-2000:]);assert q.returncode==0
 assert inputs=={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in inputs}
 ranges=check_linked_layout(state_proof_layout('pi4'),log);ranges.pop('heap')
 ranges.update(report=['0xe1c00000','0xe1c03fff'],surface=['0x03000000','0x033e7fff'],gpu_window=['0x033e8000','0x043e7fff'],neon_arena=['0x05000000','0x05ffffff'])
 items=[(n,*(int(v,16) for v in pair)) for n,pair in ranges.items()]
 for i,(n,first,last) in enumerate(items):
  assert first<=last,n
  for other,of,ol in items[i+1:]:assert last<of or ol<first,n+' overlaps '+other
 p=d/'proof.img.pmf'
 (d/'identity.json').write_text(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),checked_ranges=ranges,source_hashes=inputs,compiler_sha256=hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),scratch_source_hashes={**({'dot_probe.pbi':hashlib.sha256(dot_probe.read_bytes()).hexdigest()} if a.dot else {}),'targets_fixture.pbi':hashlib.sha256(generated.read_bytes()).hexdigest(),**({shader_path.name:hashlib.sha256(shader_path.read_bytes()).hexdigest()} if shader_path else {})},scope='Actual V3D color-load packet and attachment preservation, multi-target lifecycle and original scripted keyboard scene. Idle attached WSI explicit/implicit scopes, parent restoration and stale-owner context retirement. No physical WSI transfer claim. No physical input claim.',executed=False),indent=2),encoding='utf8',newline='\n')
if __name__=='__main__':main()
