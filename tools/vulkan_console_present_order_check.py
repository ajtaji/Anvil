#!/usr/bin/env python3
"""Source ownership-chain checks; no compiler, board, DMA or emulator."""
from pathlib import Path
import argparse,hashlib,json
from neon_vk_chrome_acceptance_check import procedure_body,code_without_comments
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'RaspberryPi4/Board/vulkan_console.pi4'

def verify(text):
 text=code_without_comments(text)
 transfer=procedure_body(text,'avcPresentRenderedFrame')
 validate='If NeonVkChromePresentValidate() <> 1 : ProcedureReturn 0 : EndIf'
 mark='avcDisplayCopyPending = DmaReady()'
 refusal='If ok = 0 : ProcedureReturn 0 : EndIf'
 clear='avcDisplayCopyPending = 0'
 consume='If NeonVkChromePresentConsume() <> 1 : ProcedureReturn 0 : EndIf'
 assert all(transfer.count(s)==1 for s in [validate,mark,refusal,clear,consume]),'transfer ownership guard differs'
 assert transfer.count('NeonVkChromePresentConsume(')==1,'transfer consumes more than once'
 copies=[transfer.index(s) for s in ['ok = avcCopyBannerToDisplay(avcBanBase','ok = avcCopyBannerToDisplay(avcImageBase','ok = avcCopyToDisplay()']]
 assert transfer.index(validate)<transfer.index(mark)<min(copies)<=max(copies)<transfer.index(refusal)<transfer.index(clear)<transfer.index(consume),'transfer releases ownership before copy success'
 banner=procedure_body(text,'avcPumpBannerOnly')
 warm='rc = NeonVkChromeWarmTrueTypeText(16, @gBannerClockText[0])'
 assert banner.count(warm)==1 and banner.index(warm)<banner.index('NeonVkChromeBegin('),'changing banner text not warmed before Begin'
 warmed=banner[banner.index(warm):banner.index('NeonVkChromeBegin(')]
 assert 'If rc < 0 : ProcedureReturn 0 : EndIf' in warmed,'failed banner warm enters frame'
 call='rc = avcPresentRenderedFrame(1, own)'
 idle='*gScrFrameWaitIdle = @avcGpuWaitIdle'
 clear_idle='*gScrFrameWaitIdle = 0'
 assert banner.count(idle)==1 and banner.count(clear_idle)==1,'banner idle callback lifetime differs'
 assert banner.index(idle)<banner.index(call)<banner.index(clear_idle),'banner idle provider not scoped to presentation'
 assert banner[banner.index(call)+len(call):banner.index(clear_idle)].strip()=='','banner returns with idle callback retained'
 assert 'If rc = 0 : ProcedureReturn 0 : EndIf' in banner[banner.index(clear_idle):banner.rindex('NeonVkChromeRebind(avcFramebuffer')],'banner ignores presentation refusal'
 assert banner.count(call)==1 and 'NeonVkChromePresentConsume(' not in banner,'banner bypasses transfer owner'
 between=banner[banner.index('endRc = NeonVkChromeEnd()'):banner.index(call)]
 assert 'NeonVkChromeRebind(' not in between and 'avcCopy' not in between,'banner retargets before transfer'
 assert banner.rindex('NeonVkChromeRebind(avcFramebuffer')>banner.index(call),'banner does not restore after transfer'
 pump=procedure_body(text,'VulkanConsolePump')
 assert pump.count('avcPresentRenderedFrame(0, 0)')==1 and 'NeonVkChromePresentConsume(' not in pump and 'avcCopyToDisplay(' not in pump,'full pump bypasses transfer owner'
 assert 'Or avcDisplayCopyPending <> 0' in pump[:pump.index('avcPumpBannerOnly()')],'pump admits work during pending copy'
 attempt=pump[pump.index('If avcPumpBannerOnly()'):pump.index('  avcBannerDirty = 0\n  st0 = Ticks()')]
 assert 'avcFailover(#AVC_ERR_PRESENT)\n      ProcedureReturn' in attempt,'failed banner falls into another frame'
 destroy=procedure_body(text,'VulkanConsoleDestroy')
 # code_without_comments preserves indentation from source: the nested guards
 # are inspected as normalized whitespace, keeping their terminal refusal.
 import re
 compact=re.sub(r'\s+',' ',destroy)
 assert 'If avcDisplayCopyPending <> 0 If DmaQuarantined() <> 0 avcDeviceUnsafe = 1 : ProcedureReturn 0 EndIf If DmaQuiescent() = 0 avcDeviceUnsafe = 1 : ProcedureReturn 0 EndIf avcDisplayCopyPending = 0 EndIf' in compact,'destroy lacks terminal DMA ownership refusal'
 assert destroy.index('DmaQuarantined()')<destroy.index('DmaQuiescent()')<destroy.index('avcDisplayCopyPending = 0')<destroy.index('vkDeviceWaitIdle(')<destroy.index('NeonVkChromeDestroyChecked()'),'destroy retires before DMA/GPU completion'
 assert 'If ScrFrameRestore() = 0 avcDeviceUnsafe = 1 : ProcedureReturn 0 EndIf' in compact,'destroy ignores display buffer ownership'
 assert destroy.index('ScrFrameRestore()')<destroy.index('vkDeviceWaitIdle('),'display ownership checked after resource retirement'
 fail=procedure_body(text,'avcFailover')
 assert 'idleSafe = VulkanConsoleDestroy()' in fail and 'If idleSafe = 0' in fail,'failover bypasses checked owner'
 unsafe=fail[fail.index('If idleSafe = 0'):fail.index('v3dSafe = V3dConInvalidate()')]
 assert 'avcQuarantined = 1' in unsafe and 'ProcedureReturn 0' in unsafe,'failover paints after unsafe teardown'
 return dict(source_checks=19,scope='source ordering only; runtime providers separately controlled')

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--self-test',action='store_true');ap.add_argument('--report',type=Path);a=ap.parse_args()
 text=SOURCE.read_text(encoding='utf8');result=verify(text)
 if a.self_test:
  def banner_mutant(old,new):
   begin=text.index('Procedure.i avcPumpBannerOnly()');end=text.index('EndProcedure',begin)
   body=text[begin:end];assert body.count(old)==1
   return text[:begin]+body.replace(old,new,1)+text[end:]
  mutants=[text.replace('avcDisplayCopyPending = DmaReady()','avcDisplayCopyPending = 0',1),
    text.replace('If ok = 0 : ProcedureReturn 0 : EndIf','If 0 <> 0 : ProcedureReturn 0 : EndIf',1),
    text.replace('avcDisplayCopyPending = DmaReady()','NeonVkChromePresentConsume()\n avcDisplayCopyPending = DmaReady()',1),
    text.replace('rc = avcPresentRenderedFrame(1, own)','NeonVkChromeRebind(avcFramebuffer,0,0,0,0,0,0)\n rc = avcPresentRenderedFrame(1, own)',1),
    text.replace('If avcPresentRenderedFrame(0, 0) = 0','NeonVkChromePresentConsume()\n If avcPresentRenderedFrame(0, 0) = 0',1),
    text.replace('Or avcDisplayCopyPending <> 0','',1),
    text.replace('If DmaQuarantined() <> 0','If 0 <> 0',1),
    text.replace('If DmaQuiescent() = 0','If 0 <> 0',1),
    banner_mutant('rc = NeonVkChromeWarmTrueTypeText(16, @gBannerClockText[0])','rc = 0'),
    banner_mutant('    If rc < 0 : ProcedureReturn 0 : EndIf','    If rc < 0 : rc = 0 : EndIf'),
    text.replace('If ScrFrameRestore() = 0','If 0 <> 0',1),
    banner_mutant('*gScrFrameWaitIdle = 0','; retained idle callback'),
    banner_mutant('*gScrFrameWaitIdle = 0','If rc = 0 : ProcedureReturn 0 : EndIf\n  *gScrFrameWaitIdle = 0')]
  for i,mutant in enumerate(mutants):
   try:verify(mutant)
   except AssertionError:continue
   raise AssertionError('Unsafe console source accepted: mutant '+str(i))
  result['source_mutants_rejected']=len(mutants)
 result['source_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
 if a.report:a.report.write_text(json.dumps(result,indent=2),encoding='utf8')
 print(json.dumps(result))
if __name__=='__main__':main()
