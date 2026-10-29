"""Check physical console WSI acquisition, completion and teardown ordering."""
from pathlib import Path
import json,re
from neon_vk_chrome_acceptance_check import procedure_body,code_without_comments
ROOT=Path(__file__).resolve().parents[1]
def verify(text):
 s=code_without_comments(text)
 destroy=procedure_body(s,'VulkanConsoleDestroy')
 assert destroy.index('NeonVkChromeDestroyChecked()')<destroy.index('NeonVkPresentTargetDestroy(avcInstance, avcDevice, @avcWsiBanner)')<destroy.index('NeonVkPresentTargetDestroy(avcInstance, avcDevice, @avcWsiMain)')<destroy.index('avcDestroyBannerTarget()')<destroy.index('vkDestroyImage(avcDevice, avcImage'),'provider image released before rollback/chain destruction'
 for name in ['avcWsiBanner','avcWsiMain']:
  pos=destroy.index('NeonVkPresentTargetDestroy(avcInstance, avcDevice, @'+name+')')
  assert 'avcDeviceUnsafe = 1' in destroy[pos:destroy.index('EndIf',pos)] and 'ProcedureReturn 0' in destroy[pos:destroy.index('EndIf',pos)],'provider cleanup refusal ignored'
 assert s.count('NeonVkPresentTargetAcquire(avcDevice, avcImage, @avcWsiMain)')==2,'full-image source acquire missing in main/banner fallback'
 pump=procedure_body(s,'VulkanConsolePump')
 assert pump.index('rc = avcWarmGrid()')<pump.index('NeonVkPresentTargetAcquire(avcDevice, avcImage, @avcWsiMain)')<pump.index('NeonVkChromeBegin('),'full frame records before acquire/attach'
 banner=procedure_body(s,'avcPumpBannerOnly')
 assert banner.index('NeonVkChromeRebind(avcBanFramebuffer')<banner.index('NeonVkPresentTargetAcquire(avcDevice, avcBanImage, @avcWsiBanner)')<banner.index('NeonVkChromeBegin('),'banner acquires wrong target generation'
 assert banner.index('rc = NeonVkChromeWarmTrueTypeText')<banner.index('NeonVkPresentTargetAcquire('),'banner mutates resources while source acquired'
 transfer=procedure_body(s,'avcPresentRenderedFrame')
 assert transfer.index('If ok = 0 : ProcedureReturn 0 : EndIf')<transfer.index('NeonVkChromePresentConsume()')<transfer.index('avcWsiPresentN = avcWsiPresentN + 1'),'source counted complete before physical confirmation'
 return dict(source_checks=8)
def main():
 s=(ROOT/'RaspberryPi4/Board/vulkan_console.pi4').read_text(encoding='utf8');out=verify(s)
 mutants=[s.replace('NeonVkChromeDestroyChecked()','IgnoredChromeTeardown()',1),s.replace('NeonVkPresentTargetAcquire(avcDevice, avcImage, @avcWsiMain)','SkippedSourceAcquire()',1),s.replace('NeonVkPresentTargetAcquire(avcDevice, avcBanImage, @avcWsiBanner)','SkippedBannerAcquire()',1),s.replace('If ok = 0 : ProcedureReturn 0 : EndIf','If ok = 0 : ok = 1 : EndIf',1)]
 for text in mutants:
  try:verify(text)
  except (AssertionError,ValueError):continue
  raise AssertionError('Unsafe integration accepted')
 out['source_mutants_rejected']=len(mutants);print(json.dumps(out))
if __name__=='__main__':main()
