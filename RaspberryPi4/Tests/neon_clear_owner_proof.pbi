; Physical ordered partial clears, including alpha-zero replacement.
Procedure.i streamMemory()
 Define i.i,n.i
 For i=1 To #ANVIL_VK_MAX_MEMORY : If avkMemLive[i]<>0 : n=n+1 : EndIf : Next
 ProcedureReturn n
EndProcedure

Procedure.i streamProof(phys.i,dev.i,queue.i,pool.i,rp.i,fb.i,base.i,pitch.i)
 Define ca.VkClearAttachment
 Define cr.VkClearRect
 Define sc.VkRect2D
 Define rc.i,x.i,y.i,jobs.i
 NeonVkChromeDestroy() : SafetyWatchdogStart(15)
 rc=NeonVkChromeCreateWithCapacities(phys,dev,queue,pool,rp,fb,800,1280,16,64)
 If rc<>0 : ProcedureReturn 841 : EndIf
 rc=NeonVkChromeBegin(@nwClear[0])
 If rc=0 : rc=Neon_Box(4,4,32,32,$FFFF0000) : EndIf
 If rc<>0 : ProcedureReturn 842 : EndIf
 ca\aspectMask=#VK_IMAGE_ASPECT_COLOR_BIT : ca\colorAttachment=0
 ca\clearValue[0]=$3F800000 : ca\clearValue[1]=$3F000000
 ca\clearValue[2]=0 : ca\clearValue[3]=0
 cr\rect\offset\x=8 : cr\rect\offset\y=8
 cr\rect\extent\width=16 : cr\rect\extent\height=16 : cr\layerCount=1
 ; Clear-attachment rectangles do not inherit the application's scissor.
 sc\extent\width=1 : sc\extent\height=1
 vkCmdSetScissor(nvcCommand,0,1,@sc)
 vkCmdClearAttachments(nvcCommand,1,@ca,1,@cr)
 rc=Neon_Box(12,12,8,8,$FF0000FF)
 If rc<>0 : ProcedureReturn 843 : EndIf
 ca\clearValue[0]=0 : ca\clearValue[1]=$3F800000
 cr\rect\offset\x=28 : cr\rect\offset\y=8
 cr\rect\extent\width=12 : cr\rect\extent\height=8
 vkCmdClearAttachments(nvcCommand,1,@ca,1,@cr)
 jobs=avkV3dJobs
 SafetyWatchdogPet() : rc=NeonVkChromeEnd()
 If rc<>0 Or NeonVkChromePresentConsume()<>1 : PokeI($E1C01310,rc) : ProcedureReturn 844 : EndIf
 If AnvilVkV3dLastListCount()<>4 Or AnvilVkV3dLastListPrimitives()<>4 Or avkV3dJobs<>jobs+1 : ProcedureReturn 845 : EndIf
 For y=0 To 63
  For x=0 To 63 : PokeL($E2400000+(y*64+x)*4,PeekL(base+y*pitch+x*4)) : Next
 Next
 PokeI($E1C01008,1) : PokeI($E1C01010,AnvilVkV3dLastListCount())
 PokeI($E1C01018,AnvilVkV3dLastListPrimitives()) : PokeI($E1C01020,avkV3dJobs-jobs)
 NeonVkChromeDestroy()
 ProcedureReturn 0
EndProcedure
