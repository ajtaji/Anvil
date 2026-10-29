"""Source ordering of parent destruction and optional read-only WSI guards."""
from pathlib import Path
import json
from neon_vk_chrome_acceptance_check import procedure_body,code_without_comments
ROOT=Path(__file__).resolve().parents[1]
def verify(command,wsi,api):
 c=code_without_comments(command);w=code_without_comments(wsi);a=code_without_comments(api)
 device=procedure_body(c,'AnvilVkDeviceDestroy');inst=procedure_body(c,'AnvilVkInstanceDestroy')
 assert device.index('rc = avkDeviceChildGuard(device)')<device.index('avkSemaphoreResetDevice(device)')<device.index('avkDevLive[d] = 0'),'device child guard is not before mutation'
 assert 'If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf' in device[device.index('rc = avkDeviceChildGuard'):device.index('avkSemaphoreResetDevice')],'device guard refusal ignored'
 assert inst.index('rc = avkInstanceChildGuard(instance)')<inst.index('avkPhysLive[p] = 0')<inst.index('avkInstLive[s] = 0'),'instance child guard is late'
 assert 'AnvilVkDeviceDestroy(' not in inst,'instance cascades into child destruction'
 assert 'If rc <> #VK_SUCCESS : ProcedureReturn rc : EndIf' in inst and 'still owns a live device' in inst,'instance refusal missing'
 d=procedure_body(w,'avkWsiGuardDeviceChildren');i=procedure_body(w,'avkWsiGuardInstanceChildren')
 assert 'avkWsiSwapDevGen[n] = avkTokenGen(device)' in d and 'avkWsiSurfInstGen[n] = avkTokenGen(instance)' in i,'extension checks ignore generations'
 register=procedure_body(w,'avkWsiProviderRegister')
 assert register.index('*avkDeviceChildGuard = @avkWsiGuardDeviceChildren')<register.index('avkWsiProvLive[p] = 1') and register.index('*avkInstanceChildGuard = @avkWsiGuardInstanceChildren')<register.index('avkWsiProvLive[p] = 1'),'extension children published before guard installation'
 wrapper=procedure_body(a,'vkDestroyInstance');assert 'AnvilVkInstanceDestroy(instance)' in wrapper and 'avkFault(' not in wrapper,'wrapper replaces original refusal'
 return dict(source_checks=8)
def main():
 c=(ROOT/'Anvil/Graphics/Vulkan/vk_command.pbi').read_text(encoding='utf8');w=(ROOT/'Anvil/Graphics/Vulkan/vk_wsi.pbi').read_text(encoding='utf8');a=(ROOT/'Anvil/Graphics/Vulkan/vk_api.pbi').read_text(encoding='utf8');out=verify(c,w,a)
 mutants=[(c.replace('rc = avkDeviceChildGuard(device)','rc = 0',1),w,a),(c.replace('rc = avkInstanceChildGuard(instance)','rc = 0',1),w,a),(c,w.replace('avkWsiSwapDevGen[n] = avkTokenGen(device)','1 = 1',1),a),(c,w,a.replace('  AnvilVkInstanceDestroy(instance)','  avkFault(-20002,"masked") : AnvilVkInstanceDestroy(instance)',1))]
 for args in mutants:
  try:verify(*args)
  except (AssertionError,ValueError):continue
  raise AssertionError('Unsafe parent lifetime mutation accepted')
 out['mutants_rejected']=len(mutants);print(json.dumps(out))
if __name__=='__main__':main()
