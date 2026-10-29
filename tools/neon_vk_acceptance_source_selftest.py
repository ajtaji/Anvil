#!/usr/bin/env python3
"""Hostile source-check tests only: no compiler, interpreter or board access.

These test the acceptance tool's source relationships. They do not execute the
renderer, validate emitted code/shaders or establish GPU/runtime correctness.
"""
from pathlib import Path
import argparse,json,re
import neon_vk_chrome_acceptance_check as gate

def changed(text,name,old,new):
 body=gate.procedure_body(text,name)
 if body.count(old)!=1:raise AssertionError('Mutation anchor drifted: '+name+' / '+old)
 return text.replace(body,body.replace(old,new,1),1)

def run():
 hooks,adapter,hashes=gate.source_inputs()
 scene=gate.REAL_SCENE.read_text(encoding='utf-8-sig')
 counts=dict(hook_checks=gate.neon_hook_source_gate(hooks),adapter_checks=gate.source_gate(adapter),scene_checks=gate.real_scene_gate(scene))
 cases=[]
 def add(label,text,check,reason):cases.append((label,text,check,reason))
 def mutate(label,name,old,new,reason):add(label,changed(adapter,name,old,new),gate.source_gate,reason)
 mutate('PresentValidate omits pending refusal','NeonVkChromePresentValidate','If nvdPresentPending() = 0 : ProcedureReturn 0 : EndIf','If 0 <> 0 : ProcedureReturn 0 : EndIf','loses pending/identity refusal')
 mutate('PresentValidate bypasses identity','NeonVkChromePresentValidate','nvdPresentMatches(nvcTargetGeneration, nvcFramebuffer)','IgnoredPresentMatches(nvcTargetGeneration, nvcFramebuffer)','loses pending/identity refusal')
 mutate('PresentValidate consumes the record','NeonVkChromePresentValidate','ProcedureReturn 1','nvdPresentConsume(nvcTargetGeneration, nvcFramebuffer)\n ProcedureReturn 1','changes presentation ownership')
 mutate('Begin bypasses WSI recording preflight','NeonVkChromeBegin','If nvdWsiRecordingAllowed(nvcDevice, nvcTargetGeneration) = 0','If 0 <> 0','terminal WSI recording preflight')
 mutate('Begin ignores WSI recording refusal','NeonVkChromeBegin','If nvdWsiRecordingAllowed(nvcDevice, nvcTargetGeneration) = 0\n    ProcedureReturn','If nvdWsiRecordingAllowed(nvcDevice, nvcTargetGeneration) = 0\n    IgnoredReturn','terminal WSI recording preflight')
 mutate('Begin refreshes atlas before WSI check','NeonVkChromeBegin','If nvdWsiRecordingAllowed(nvcDevice, nvcTargetGeneration) = 0','rc = nvcAtlasRefresh()\n  If nvdWsiRecordingAllowed(nvcDevice, nvcTargetGeneration) = 0','before WSI recording preflight')
 mutate('WSI recording admits ready image','nvdWsiRecordingAllowed','nvdWsiState <> #NVD_WSI_ACQUIRED','nvdWsiState <> #NVD_WSI_READY','loses acquired-image identity')
 mutate('WSI recording ignores device owner','nvdWsiRecordingAllowed','nvdWsiDevice <> device','0 <> 0','loses acquired-image identity')
 mutate('WSI recording ignores target generation','nvdWsiRecordingAllowed','nvdWsiTargetGeneration <> targetGeneration','0 <> 0','loses acquired-image identity')
 mutate('WSI recording ignores actual image state','nvdWsiRecordingAllowed','= #ANVIL_VK_WSI_IMAGE_ACQUIRED)','= #ANVIL_VK_WSI_IMAGE_RENDER_READY)','loses acquired-image identity')
 mutate('WSI recording mutates bridge state','nvdWsiRecordingAllowed','Define imageKey.i','Define imageKey.i\n nvdWsiTicket = 0','not read-only')
 for name in gate.RESOURCE_MUTATION_ENTRIES:
  for field in ('nvcFramePending','nvcFrameAbortable'):
   mutate(name+' admits '+field,name,' Or '+field+' <> 0','','frame-ownership guard')
  body=gate.procedure_body(adapter,name)
  guard_start=re.search(r'(?m)^\s*If [^\n]*nvcInFrame <> 0[^\n]*',body).start()
  refusal=body.index('ProcedureReturn',guard_start)
  hostile=body[:refusal]+'IgnoredReturn'+body[refusal+len('ProcedureReturn'):]
  add(name+' does not return on busy frame',adapter.replace(body,hostile,1),gate.source_gate,'terminal frame-ownership refusal')
 mutate('Rebind omits target-owner preflight','NeonVkChromeRebind','AnvilVkFramebufferTargetCheck(','IgnoredTargetCheck(','one exact framebuffer-owner')
 mutate('Rebind checks logical instead of physical width','NeonVkChromeRebind','framebuffer, physicalW, physicalH, pitch)','framebuffer, logicalW, physicalH, pitch)','one exact framebuffer-owner')
 mutate('Rebind ignores target-owner refusal','NeonVkChromeRebind','If rc <> #VK_SUCCESS : ProcedureReturn nvcFail(rc) : EndIf','If 0 <> 0 : ProcedureReturn nvcFail(rc) : EndIf','before framebuffer-owner refusal')
 mutate('Rebind publishes metadata early','NeonVkChromeRebind','Define rc.i','Define rc.i\n nvcPitch = pitch','before framebuffer-owner preflight')
 mutate('Create omits target pitch query','NeonVkChromeCreateWithCapacities','AnvilVkFramebufferTargetPitch(','IgnoredTargetPitch(','one exact framebuffer-owner pitch query')
 mutate('Create ignores target pitch refusal','NeonVkChromeCreateWithCapacities','If targetPitch < 1','If 0 <> 0','finish target-pitch refusal')
 mutate('Create accepts a zero pitch result','NeonVkChromeCreateWithCapacities','If targetPitch = 0 : targetPitch = #NEON_VK_CHROME_ERR_STATE : EndIf','If targetPitch = 0 : targetPitch = 0 : EndIf','finish target-pitch refusal')
 mutate('Create publishes target metadata early','NeonVkChromeCreateWithCapacities','Define targetPitch.i','Define targetPitch.i\n nvcPitch = width * 4','before framebuffer-owner pitch query')
 mutate('Create assumes packed rows','NeonVkChromeCreateWithCapacities','nvcPitch = targetPitch','nvcPitch = width * 4','publish the framebuffer-owner row pitch')
 mutate('Destroy accepts new recording during teardown','NeonVkChromeDestroyChecked','nvcReady = 0 : nvcInFrame = 0','nvcReady = 1 : nvcInFrame = 1','quarantine recording')
 mutate('Destroy ignores failed idle wait','NeonVkChromeDestroyChecked','If idleRc <> #VK_SUCCESS','If 0 <> 0','establish completion before WSI rollback')
 mutate('Destroy ignores WSI rollback failure','NeonVkChromeDestroyChecked','If rollbackRc <> #VK_SUCCESS : ProcedureReturn nvcFail(rollbackRc) : EndIf','If 0 <> 0 : ProcedureReturn nvcFail(rollbackRc) : EndIf','ignores WSI rollback refusal')
 mutate('Destroy clears presentation early','NeonVkChromeDestroyChecked','Define idleRc.i, rollbackRc.i','Define idleRc.i, rollbackRc.i\n nvdPresentClear()','before safe rollback')
 mutate('Destroy unmaps before idle','NeonVkChromeDestroyChecked','Define idleRc.i, rollbackRc.i','Define idleRc.i, rollbackRc.i\n vkUnmapMemory(nvcDevice,nvcVertexMemory)','before safe rollback')
 mutate('Destroy drops callback marker early','NeonVkChromeDestroyChecked','Define idleRc.i, rollbackRc.i','Define idleRc.i, rollbackRc.i\n nvcHooksInstalled = 0','before safe rollback')
 destroy=gate.procedure_body(adapter,'NeonVkChromeDestroyChecked')
 early_rollback=destroy.replace('  rollbackRc = nvdWsiRollback()\n','').replace('  nvcReady = 0 : nvcInFrame = 0','  nvcReady = 0 : nvcInFrame = 0\n  rollbackRc = nvdWsiRollback()',1)
 add('Destroy rolls back WSI before completion',adapter.replace(destroy,early_rollback,1),gate.source_gate,'establish completion before WSI rollback')
 mutate('configured bold selection removed','NeonVkChromeText','NeonBitmapFontBold(font)','0','configured NeonFontSetup bold face')
 mutate('comment cannot replace bold selection','NeonVkChromeText','NeonBitmapFontBold(font)','0 ; nvcAtlasMapBitmapUV(@nvcBitmapPlan[i], NeonBitmapFontBold(font))','configured NeonFontSetup bold face')
 mutate('text right UV changed','NeonVkChromeText','nvcBitmapPlan[i]\\right','nvcBitmapPlan[i]\\left','copied glyph right')
 mutate('whole text physical reservation removed','NeonVkChromeText','glyphCount * 6 > nvcMaxVertexQuads * 6 - nvcVertices','0 > 1','complete vertex capacity')
 mutate('logical text budget removed','NeonVkChromeText','nvcBudgetCan(0, 1, logicalVertices)','1','copied-glyph/budget preflight')
 mutate('glyph plan not marked live','NeonVkChromeText','nvcBitmapPlanLive[i] = 1','nvcBitmapPlanLive[i] = 0','copied-glyph/budget preflight')
 mutate('late glyph query after emission begins','NeonVkChromeText','nvcVertices = nvcVertices + 6','Neon_AtlasRasterGlyphUV(ch, @nvcBitmapPlan[i]) : nvcVertices = nvcVertices + 6','re-resolves glyphs')
 mutate('late capacity refusal after text write','NeonVkChromeText','nvcVertices = nvcVertices + 6','nvcVertices = nvcVertices + 6 : ProcedureReturn nvcFail(#NEON_VK_CHROME_ERR_CAPACITY)','after partially writing glyph')
 mutate('textured glyph query repeated after write','NeonVkChromeTextTex','nvcVertices = nvcVertices + 6','Neon_AtlasRasterGlyphUV(ch, @nvcBitmapPlan[i]) : nvcVertices = nvcVertices + 6','re-resolves glyphs')
 mutate('textured glyph bottom lost','NeonVkChromeTextTex','nvcBitmapPlan[i]\\bottom','nvcBitmapPlan[i]\\top','copied glyph bottom')
 mutate('frame publishes twice','nvcFramePublish','If nvdPresentPublish(','nvdPresentPublish(nvcTargetGeneration, nvcFramebuffer, 0, 0, 0, 0, 0, 0, 0)\n  If nvdPresentPublish(','exactly one generation-tagged')
 mutate('End bypasses completed-frame publication','NeonVkChromeEnd','ProcedureReturn nvcFramePublish()','ProcedureReturn #VK_SUCCESS','delegate one completed-frame publication')
 mutate('Finish bypasses completed-frame publication','NeonVkChromeFinish','ProcedureReturn nvcFramePublish()','ProcedureReturn #VK_SUCCESS','delegate one completed-frame publication')
 finish=gate.procedure_body(adapter,'NeonVkChromeFinish')
 early=finish.replace('  nvcFramePending = 0\n','').replace('  If rc <> #VK_SUCCESS : ProcedureReturn nvcFail(rc) : EndIf','  nvcFramePending = 0\n  If rc <> #VK_SUCCESS : ProcedureReturn nvcFail(rc) : EndIf')
 add('failed fence wait releases pending',adapter.replace(finish,early),gate.source_gate,'failed completion wait releases')
 mutate('checked destroy leaves draw family installed','NeonVkChromeDestroyChecked','NeonDrawBackendClear()','IgnoredClear()','clear its installed backend ownership')
 mutate('legacy destroy bypasses checked owner','NeonVkChromeDestroy','NeonVkChromeDestroyChecked()','IgnoredDestroy()','delegate to the checked resource owner')
 mutate('fan fallback omitted','NeonVkChromeFanEnd','rc = nvcFanListDraw(colour)','rc = 0','fan loses an advertised or indexed fallback route')
 mutate('outline bypasses immutable owner','NeonVkChromeFanOutline','nvcOutlineDraw(colour, 0)','IgnoredOutline(colour, 0)','immutable indexed owner')
 mutate('fan preflight loses vertex bound','NeonVkChromeFanEnd','nvcVertices + needed > nvcMaxVertexQuads * 6','0 > 1','whole-primitive capacity preflight')
 mutate('line preflight loses draw bound','NeonVkChromeLinesEnd','nvcDrawCount >= nvcMaxQuads','0 > 1','whole-primitive capacity preflight')
 mutate('line record stride reduced','NeonVkChromeLinesEnd','p = p + 32 : i = i + 2','p = p + 24 : i = i + 2','line storage/draw contract differs')
 mutate('line instance count lost','nvcLineStreamDraw','nvcLineLayout, count)','nvcLineLayout, 1)','compact line draw or state restoration differs')
 mutate('line draw leaves wrong pipeline bound','nvcLineStreamDraw','#VK_PIPELINE_BIND_POINT_GRAPHICS, nvcPipeline)','#VK_PIPELINE_BIND_POINT_GRAPHICS, nvcLinePipeline)','compact line draw or state restoration differs')
 mutate('compact corner component omitted','nvcLineRecordAt','PokeL(p + 28, c3 >> 32)','PokeL(p + 28, c2 >> 32)','drops an exact corner component')
 mutate('outline row reservation removed','nvcOutlinePrepare','rawRows > avkRecordedDrawFreeCount','0 > 1','complete reservation')
 mutate('outline point reservation removed','nvcOutlinePrepare','delta > points - nvcOutlinePointsUsed','0 > 1','complete reservation')
 mutate('outline closing reservation removed','nvcOutlinePrepare','nvcOutlineClosingsUsed >= #NEON_MAX_DRAWS','0 > 1','complete reservation')
 mutate('outline cache recreation on reuse','nvcOutlineEnsure','If nvcOutlineBuffer <> 0 : ProcedureReturn #VK_SUCCESS : EndIf','If 0 <> 0 : ProcedureReturn #VK_SUCCESS : EndIf','cache is not retained')
 mutate('outline ignores preparation failure','nvcOutlineDraw','If rc <> 0 : ProcedureReturn rc : EndIf','If 0 <> 0 : ProcedureReturn rc : EndIf','before successful complete preparation')
 mutate('closing edge points at open-chain range','nvcOutlineDraw','nvcOutlineDrawRange(nvcFanIndexedClose, 6, colour)','nvcOutlineDrawRange(0, 6, colour)','immutable outline draw ranges differ')
 mutate('fallback loses immutable first index','nvcFanListDraw','nvcFanListIndicesUsed, 0, 0)','0, 0, 0)','immutable first-index range')
 mutate('logical fan point limit removed','NeonVkChromeFanPoint','#NEON_VK_CHROME_MAX_PATH_POINTS','999999','logical primitive staging')
 mutate('direct framebuffer bypass injected','NeonVkChromeLinesEnd','Define first.i','Define first.i\n  DisplayBlit(0, 0, 0)','performs display DMA')
 add('duplicate public procedure owner',adapter+'\n'+gate.procedure_body(adapter,'NeonVkChromeBox'),gate.source_gate,'one procedure owner')
 for label,name,old,new,reason in [
  ('null install no longer clears','NeonDrawBackendInstall','NeonDrawBackendClear()','IgnoredClear()','null install'),
  ('partial family check removed','NeonDrawBackendInstall','boxProc = 0 Or textProc = 0','boxProc < 0 Or textProc < 0','partial-family'),
  ('clear loses one callback','NeonDrawBackendClear','@nfc_BackendBoxUnbound','@OtherUnbound','complete native family'),
  ('Box callback arguments changed','Neon_Box','gNeonBackendBox(x, y, w, h, colour)','gNeonBackendBox(y, x, w, h, colour)','exact public arguments'),
 ]:add(label,changed(hooks,name,old,new),gate.neon_hook_source_gate,reason)
 # A source comment is not one of the frozen executable widget calls.
 add('widget call hidden in comment',changed(hooks,'Neon_Frame','Neon_Box(x,         y,         w, 1, colour)', '; Neon_Box(x,         y,         w, 1, colour)'),gate.neon_hook_source_gate,'widget Neon_Box call surface')
 rejected=[]
 for label,text,check,reason in cases:
  try:check(text)
  except AssertionError as exc:
   if reason not in str(exc):raise AssertionError(label+' rejected for unrelated reason: '+str(exc))
   rejected.append(label)
   continue
  raise AssertionError('Broken source accepted: '+label)
 return dict(scope='source-check self-test only',source_status='PASS',source_hashes=hashes,**counts,mutations_rejected=len(rejected),mutations=rejected,emitted='NOT RUN',gpu='NOT RUN',full_acceptance='NOT RUN')

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path);a=ap.parse_args()
 result=run()
 if a.report:a.report.write_text(json.dumps(result,indent=2),encoding='utf8')
 print(json.dumps(result))
if __name__=='__main__':main()
