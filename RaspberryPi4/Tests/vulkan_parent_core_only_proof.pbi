; No presentation provider is registered; optional child guards remain unset.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/Vulkan/vk_api.pbi"
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_test.pbi"
Procedure.i Main(services.i)
 Define inst.i,phys.i,dev.i,count.i,rc.i,n.i
 For n=0 To 4095 : PokeA(#TC_REPORT+n,0) : Next
 avkTbHeapBase=$6200000 : avkTbHeapBytes=$100000
 rc=AnvilVkInstanceCreate(@inst) : If rc<>0 : ProcedureReturn 1 : EndIf
 count=1 : rc=AnvilVkPhysicalEnumerate(inst,@count,@phys)
 rc=AnvilVkDeviceCreate(phys,@dev) : If rc<>0 : ProcedureReturn 2 : EndIf
 PokeI(#TC_REPORT,$434F5245)
 rc=AnvilVkInstanceDestroy(inst) : PokeI(#TC_REPORT+8,rc)
 PokeI(#TC_REPORT+16,Bool(avkInstSlot(inst)<>0)) : PokeI(#TC_REPORT+24,Bool(avkDevSlot(dev)<>0))
 rc=AnvilVkDeviceDestroy(dev) : PokeI(#TC_REPORT+32,rc)
 rc=AnvilVkInstanceDestroy(inst) : PokeI(#TC_REPORT+40,rc)
 PokeI(#TC_REPORT+48,*avkDeviceChildGuard) : PokeI(#TC_REPORT+56,*avkInstanceChildGuard)
 ProcedureReturn 0
EndProcedure
