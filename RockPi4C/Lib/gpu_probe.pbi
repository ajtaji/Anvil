; Read-only RK3399 Mali-T860 bring-up probe.
;
; Instance, clock, power, reset and register data come from Linux
; rk3399-base.dtsi, clk-rk3399.c, Rockchip pm-domains.c, rk3399-cru.h,
; and Panfrost's panfrost_regs.h/panfrost_gpu.c. This layer performs no
; writes. It observes PMU/CRU state first and touches GPU MMIO only when the
; domain, idle handshake, clock gates and resets prove accessible. A returning
; deadman payload proved the minimal reachability sequence on the original
; ROCK Pi 4C v1.2: GPU_ID 08602000, MMU_FEATURES 00002830, AS_PRESENT
; 000000FF, JS_PRESENT 00000007 and zero global/JM/MMU status. The recovery
; `gpuinfo` command is restricted to that same read-only sequence.

#ROCK_GPU_BASE = $FF9A0000
#ROCK_GPU_BYTES = $00010000
#ROCK_GPU_PRODUCT_T860 = $0860
#ROCK_GPU_PMU_POWER_BIT = 15
#ROCK_GPU_PMU_IDLE_BIT = 0
#ROCK_GPU_CLKSEL13_MUX_MASK = $00E0
#ROCK_GPU_CLKSEL13_DIV_MASK = $001F
#ROCK_GPU_CLKSEL13_MAX_PARENT = 4
#ROCK_GPU_CLKGATE13_PRE_BIT = 0
#ROCK_GPU_CLKGATE30_ACLK_BIT = 8
#ROCK_GPU_SOFTRST18_MASK = $0007
#ROCK_GPU_MAX_JOB_SLOTS = 16
#ROCK_GPU_MAX_ADDRESS_SPACES = 16

#ROCK_GPU_ID = $0000
#ROCK_GPU_L2_FEATURES = $0004
#ROCK_GPU_CORE_FEATURES = $0008
#ROCK_GPU_TILER_FEATURES = $000C
#ROCK_GPU_MEM_FEATURES = $0010
#ROCK_GPU_MMU_FEATURES = $0014
#ROCK_GPU_AS_PRESENT = $0018
#ROCK_GPU_JS_PRESENT = $001C
#ROCK_GPU_INT_RAWSTAT = $0020
#ROCK_GPU_INT_MASK = $0028
#ROCK_GPU_INT_STAT = $002C
#ROCK_GPU_STATUS = $0034
#ROCK_GPU_FAULT_STATUS = $003C
#ROCK_GPU_FAULT_ADDRESS_LO = $0040
#ROCK_GPU_FAULT_ADDRESS_HI = $0044
#ROCK_GPU_THREAD_MAX_THREADS = $00A0
#ROCK_GPU_THREAD_MAX_WORKGROUP = $00A4
#ROCK_GPU_THREAD_MAX_BARRIER = $00A8
#ROCK_GPU_THREAD_FEATURES = $00AC
#ROCK_GPU_SHADER_PRESENT_LO = $0100
#ROCK_GPU_SHADER_PRESENT_HI = $0104
#ROCK_GPU_TILER_PRESENT_LO = $0110
#ROCK_GPU_TILER_PRESENT_HI = $0114
#ROCK_GPU_L2_PRESENT_LO = $0120
#ROCK_GPU_L2_PRESENT_HI = $0124
#ROCK_GPU_COHERENCY_FEATURES = $0300
#ROCK_GPU_THREAD_TLS_ALLOC = $0310

#ROCK_GPU_JOB_INT_RAWSTAT = $1000
#ROCK_GPU_JOB_INT_MASK = $1008
#ROCK_GPU_JOB_INT_STAT = $100C
#ROCK_GPU_JOB_INT_JS_STATE = $1010
#ROCK_GPU_JOB_INT_THROTTLE = $1014
#ROCK_GPU_JS_BASE = $1800
#ROCK_GPU_JS_STRIDE = $0080
#ROCK_GPU_JS_HEAD_LO = $00
#ROCK_GPU_JS_HEAD_HI = $04
#ROCK_GPU_JS_TAIL_LO = $08
#ROCK_GPU_JS_TAIL_HI = $0C
#ROCK_GPU_JS_AFFINITY_LO = $10
#ROCK_GPU_JS_AFFINITY_HI = $14
#ROCK_GPU_JS_CONFIG = $18
#ROCK_GPU_JS_XAFFINITY = $1C
#ROCK_GPU_JS_STATUS = $24
#ROCK_GPU_JS_HEAD_NEXT_LO = $40
#ROCK_GPU_JS_HEAD_NEXT_HI = $44
#ROCK_GPU_JS_CONFIG_NEXT = $58

#ROCK_GPU_MMU_INT_RAWSTAT = $2000
#ROCK_GPU_MMU_INT_MASK = $2008
#ROCK_GPU_MMU_INT_STAT = $200C
#ROCK_GPU_MMU_BASE = $2400
#ROCK_GPU_MMU_AS_SHIFT = 6
#ROCK_GPU_AS_TRANSTAB_LO = $00
#ROCK_GPU_AS_TRANSTAB_HI = $04
#ROCK_GPU_AS_MEMATTR_LO = $08
#ROCK_GPU_AS_MEMATTR_HI = $0C
#ROCK_GPU_AS_LOCKADDR_LO = $10
#ROCK_GPU_AS_LOCKADDR_HI = $14
#ROCK_GPU_AS_FAULTSTATUS = $1C
#ROCK_GPU_AS_FAULTADDRESS_LO = $20
#ROCK_GPU_AS_FAULTADDRESS_HI = $24
#ROCK_GPU_AS_STATUS = $28

#ROCK_GPU_ERROR_EL = 1
#ROCK_GPU_ERROR_CPU_STATE = 2
#ROCK_GPU_ERROR_POWER = 3
#ROCK_GPU_ERROR_IDLE = 4
#ROCK_GPU_ERROR_CLOCK = 5
#ROCK_GPU_ERROR_RESET = 6
#ROCK_GPU_ERROR_PRODUCT = 7
#ROCK_GPU_ERROR_FEATURES = 8
#ROCK_GPU_ERROR_NOT_READY = 9
#ROCK_GPU_ERROR_JOB_SLOT = 10
#ROCK_GPU_ERROR_ADDRESS_SPACE = 11

Global rock_gpu_infrastructure_ready.i
Global rock_gpu_reachability_ready.i
Global rock_gpu_probe_ready.i
Global rock_gpu_error.i
Global rock_gpu_pmu_pwrdn_con.i
Global rock_gpu_pmu_pwrdn_st.i
Global rock_gpu_pmu_idle_req.i
Global rock_gpu_pmu_idle_st.i
Global rock_gpu_pmu_idle_ack.i
Global rock_gpu_clksel13.i
Global rock_gpu_clkgate13.i
Global rock_gpu_clkgate30.i
Global rock_gpu_softrst18.i
Global rock_gpu_clock_parent.i
Global rock_gpu_clock_divider.i
Global rock_gpu_id.i
Global rock_gpu_product.i
Global rock_gpu_revision.i
Global rock_gpu_l2_features.i
Global rock_gpu_core_features.i
Global rock_gpu_tiler_features.i
Global rock_gpu_mem_features.i
Global rock_gpu_mmu_features.i
Global rock_gpu_mmu_va_bits.i
Global rock_gpu_mmu_pa_bits.i
Global rock_gpu_as_present.i
Global rock_gpu_js_present.i
Global rock_gpu_thread_max_threads.i
Global rock_gpu_thread_max_workgroup.i
Global rock_gpu_thread_max_barrier.i
Global rock_gpu_thread_features.i
Global rock_gpu_thread_tls_alloc.i
Global rock_gpu_coherency_features.i
Global rock_gpu_shader_present.i
Global rock_gpu_tiler_present.i
Global rock_gpu_l2_present.i
Global rock_gpu_status.i
Global rock_gpu_fault_status.i
Global rock_gpu_fault_address.i
Global rock_gpu_int_rawstat.i
Global rock_gpu_int_mask.i
Global rock_gpu_int_stat.i
Global rock_gpu_job_int_rawstat.i
Global rock_gpu_job_int_mask.i
Global rock_gpu_job_int_stat.i
Global rock_gpu_job_int_js_state.i
Global rock_gpu_job_int_throttle.i
Global rock_gpu_job_slot.i
Global rock_gpu_job_head.i
Global rock_gpu_job_tail.i
Global rock_gpu_job_affinity.i
Global rock_gpu_job_config.i
Global rock_gpu_job_xaffinity.i
Global rock_gpu_job_status.i
Global rock_gpu_job_head_next.i
Global rock_gpu_job_config_next.i
Global rock_gpu_mmu_int_rawstat.i
Global rock_gpu_mmu_int_mask.i
Global rock_gpu_mmu_int_stat.i
Global rock_gpu_address_space.i
Global rock_gpu_as_transtab.i
Global rock_gpu_as_memattr.i
Global rock_gpu_as_lockaddr.i
Global rock_gpu_as_faultstatus.i
Global rock_gpu_as_faultaddress.i
Global rock_gpu_as_status.i

Procedure.i RockGpuRead(offset.i)
  ProcedureReturn PeekL(#ROCK_GPU_BASE+offset) & $FFFFFFFF
EndProcedure

Procedure.i RockGpuCaptureInfrastructure()
  Protected powerMask.i=1 << #ROCK_GPU_PMU_POWER_BIT
  Protected idleMask.i=1 << #ROCK_GPU_PMU_IDLE_BIT
  Protected preMask.i=1 << #ROCK_GPU_CLKGATE13_PRE_BIT
  Protected aclkMask.i=1 << #ROCK_GPU_CLKGATE30_ACLK_BIT
  rock_gpu_infrastructure_ready=0
  rock_gpu_reachability_ready=0
  rock_gpu_probe_ready=0
  rock_gpu_error=0
  rock_gpu_pmu_pwrdn_con=0
  rock_gpu_pmu_pwrdn_st=0
  rock_gpu_pmu_idle_req=0
  rock_gpu_pmu_idle_st=0
  rock_gpu_pmu_idle_ack=0
  rock_gpu_clksel13=0
  rock_gpu_clkgate13=0
  rock_gpu_clkgate30=0
  rock_gpu_softrst18=0
  rock_gpu_clock_parent=0
  rock_gpu_clock_divider=0
  If rock_current_el<>12 : rock_gpu_error=#ROCK_GPU_ERROR_EL : ProcedureReturn 0 : EndIf
  If (rock_sctlr_el3 & $1005)<>0 : rock_gpu_error=#ROCK_GPU_ERROR_CPU_STATE : ProcedureReturn 0 : EndIf
  rock_gpu_pmu_pwrdn_con=PeekL(#ROCK_PMU+#ROCK_PMU_PWRDN_CON) & $FFFFFFFF
  rock_gpu_pmu_pwrdn_st=PeekL(#ROCK_PMU+#ROCK_PMU_PWRDN_ST) & $FFFFFFFF
  rock_gpu_pmu_idle_req=PeekL(#ROCK_PMU+#ROCK_PMU_BUS_IDLE_REQ) & $FFFFFFFF
  rock_gpu_pmu_idle_st=PeekL(#ROCK_PMU+#ROCK_PMU_BUS_IDLE_ST) & $FFFFFFFF
  rock_gpu_pmu_idle_ack=PeekL(#ROCK_PMU+#ROCK_PMU_BUS_IDLE_ACK) & $FFFFFFFF
  rock_gpu_clksel13=RockCruRead(#ROCK_CRU_CLKSEL+13*4)
  rock_gpu_clkgate13=RockCruRead(#ROCK_CRU_CLKGATE+13*4)
  rock_gpu_clkgate30=RockCruRead(#ROCK_CRU_CLKGATE+30*4)
  rock_gpu_softrst18=RockCruRead(#ROCK_CRU_SOFTRST+18*4)
  rock_gpu_clock_parent=(rock_gpu_clksel13 & #ROCK_GPU_CLKSEL13_MUX_MASK) >> 5
  rock_gpu_clock_divider=(rock_gpu_clksel13 & #ROCK_GPU_CLKSEL13_DIV_MASK)+1
  If (rock_gpu_pmu_pwrdn_con & powerMask)<>0 Or (rock_gpu_pmu_pwrdn_st & powerMask)<>0
    rock_gpu_error=#ROCK_GPU_ERROR_POWER : ProcedureReturn 0
  EndIf
  If (rock_gpu_pmu_idle_req & idleMask)<>0 Or (rock_gpu_pmu_idle_st & idleMask)<>0 Or (rock_gpu_pmu_idle_ack & idleMask)<>0
    rock_gpu_error=#ROCK_GPU_ERROR_IDLE : ProcedureReturn 0
  EndIf
  If (rock_gpu_clkgate13 & preMask)<>0 Or (rock_gpu_clkgate30 & aclkMask)<>0 Or rock_gpu_clock_parent>#ROCK_GPU_CLKSEL13_MAX_PARENT Or rock_gpu_clock_divider<1 Or rock_gpu_clock_divider>32
    rock_gpu_error=#ROCK_GPU_ERROR_CLOCK : ProcedureReturn 0
  EndIf
  If (rock_gpu_softrst18 & #ROCK_GPU_SOFTRST18_MASK)<>0
    rock_gpu_error=#ROCK_GPU_ERROR_RESET : ProcedureReturn 0
  EndIf
  ASM
    dsb sy
  ENDASM
  rock_gpu_infrastructure_ready=1
  ProcedureReturn 1
EndProcedure

Procedure.i RockGpuProbeReachability()
  rock_gpu_reachability_ready=0
  rock_gpu_probe_ready=0
  rock_gpu_id=0
  rock_gpu_product=0
  rock_gpu_revision=0
  rock_gpu_mmu_features=0
  rock_gpu_mmu_va_bits=0
  rock_gpu_mmu_pa_bits=0
  rock_gpu_as_present=0
  rock_gpu_js_present=0
  rock_gpu_status=0
  rock_gpu_job_int_js_state=0
  rock_gpu_mmu_int_stat=0
  If RockGpuCaptureInfrastructure()=0 : ProcedureReturn 0 : EndIf
  rock_gpu_id=RockGpuRead(#ROCK_GPU_ID)
  rock_gpu_product=(rock_gpu_id >> 16) & $FFFF
  rock_gpu_revision=rock_gpu_id & $FFFF
  rock_gpu_mmu_features=RockGpuRead(#ROCK_GPU_MMU_FEATURES)
  rock_gpu_mmu_va_bits=rock_gpu_mmu_features & $FF
  rock_gpu_mmu_pa_bits=(rock_gpu_mmu_features >> 8) & $FF
  rock_gpu_as_present=RockGpuRead(#ROCK_GPU_AS_PRESENT)
  rock_gpu_js_present=RockGpuRead(#ROCK_GPU_JS_PRESENT)
  rock_gpu_status=RockGpuRead(#ROCK_GPU_STATUS)
  rock_gpu_job_int_js_state=RockGpuRead(#ROCK_GPU_JOB_INT_JS_STATE)
  rock_gpu_mmu_int_stat=RockGpuRead(#ROCK_GPU_MMU_INT_STAT)
  If rock_gpu_product<>#ROCK_GPU_PRODUCT_T860
    rock_gpu_error=#ROCK_GPU_ERROR_PRODUCT : ProcedureReturn 0
  EndIf
  If rock_gpu_as_present=0 Or rock_gpu_js_present=0 Or rock_gpu_mmu_va_bits=0 Or rock_gpu_mmu_pa_bits=0
    rock_gpu_error=#ROCK_GPU_ERROR_FEATURES : ProcedureReturn 0
  EndIf
  rock_gpu_reachability_ready=1
  ProcedureReturn 1
EndProcedure

Procedure.i RockGpuProbeReadOnly()
  rock_gpu_probe_ready=0
  If RockGpuProbeReachability()=0 : ProcedureReturn 0 : EndIf
  rock_gpu_l2_features=RockGpuRead(#ROCK_GPU_L2_FEATURES)
  rock_gpu_core_features=RockGpuRead(#ROCK_GPU_CORE_FEATURES)
  rock_gpu_tiler_features=RockGpuRead(#ROCK_GPU_TILER_FEATURES)
  rock_gpu_mem_features=RockGpuRead(#ROCK_GPU_MEM_FEATURES)
  rock_gpu_thread_max_threads=RockGpuRead(#ROCK_GPU_THREAD_MAX_THREADS)
  rock_gpu_thread_max_workgroup=RockGpuRead(#ROCK_GPU_THREAD_MAX_WORKGROUP)
  rock_gpu_thread_max_barrier=RockGpuRead(#ROCK_GPU_THREAD_MAX_BARRIER)
  rock_gpu_thread_features=RockGpuRead(#ROCK_GPU_THREAD_FEATURES)
  rock_gpu_thread_tls_alloc=RockGpuRead(#ROCK_GPU_THREAD_TLS_ALLOC)
  rock_gpu_coherency_features=RockGpuRead(#ROCK_GPU_COHERENCY_FEATURES)
  rock_gpu_shader_present=RockGpuRead(#ROCK_GPU_SHADER_PRESENT_LO) | (RockGpuRead(#ROCK_GPU_SHADER_PRESENT_HI) << 32)
  rock_gpu_tiler_present=RockGpuRead(#ROCK_GPU_TILER_PRESENT_LO) | (RockGpuRead(#ROCK_GPU_TILER_PRESENT_HI) << 32)
  rock_gpu_l2_present=RockGpuRead(#ROCK_GPU_L2_PRESENT_LO) | (RockGpuRead(#ROCK_GPU_L2_PRESENT_HI) << 32)
  rock_gpu_fault_status=RockGpuRead(#ROCK_GPU_FAULT_STATUS)
  rock_gpu_fault_address=RockGpuRead(#ROCK_GPU_FAULT_ADDRESS_LO) | (RockGpuRead(#ROCK_GPU_FAULT_ADDRESS_HI) << 32)
  rock_gpu_int_rawstat=RockGpuRead(#ROCK_GPU_INT_RAWSTAT)
  rock_gpu_int_mask=RockGpuRead(#ROCK_GPU_INT_MASK)
  rock_gpu_int_stat=RockGpuRead(#ROCK_GPU_INT_STAT)
  rock_gpu_job_int_rawstat=RockGpuRead(#ROCK_GPU_JOB_INT_RAWSTAT)
  rock_gpu_job_int_mask=RockGpuRead(#ROCK_GPU_JOB_INT_MASK)
  rock_gpu_job_int_stat=RockGpuRead(#ROCK_GPU_JOB_INT_STAT)
  rock_gpu_job_int_throttle=RockGpuRead(#ROCK_GPU_JOB_INT_THROTTLE)
  rock_gpu_mmu_int_rawstat=RockGpuRead(#ROCK_GPU_MMU_INT_RAWSTAT)
  rock_gpu_mmu_int_mask=RockGpuRead(#ROCK_GPU_MMU_INT_MASK)
  If rock_gpu_shader_present=0 Or rock_gpu_tiler_present=0 Or rock_gpu_l2_present=0
    rock_gpu_error=#ROCK_GPU_ERROR_FEATURES : ProcedureReturn 0
  EndIf
  rock_gpu_probe_ready=1
  ProcedureReturn 1
EndProcedure

Procedure.i RockGpuProbeJobSlot(slot.i)
  Protected base.i
  If rock_gpu_probe_ready=0 : rock_gpu_error=#ROCK_GPU_ERROR_NOT_READY : ProcedureReturn 0 : EndIf
  If slot<0 Or slot>=#ROCK_GPU_MAX_JOB_SLOTS Or (rock_gpu_js_present & (1 << slot))=0
    rock_gpu_error=#ROCK_GPU_ERROR_JOB_SLOT : ProcedureReturn 0
  EndIf
  base=#ROCK_GPU_JS_BASE+slot*#ROCK_GPU_JS_STRIDE
  rock_gpu_job_slot=slot
  rock_gpu_job_head=RockGpuRead(base+#ROCK_GPU_JS_HEAD_LO) | (RockGpuRead(base+#ROCK_GPU_JS_HEAD_HI) << 32)
  rock_gpu_job_tail=RockGpuRead(base+#ROCK_GPU_JS_TAIL_LO) | (RockGpuRead(base+#ROCK_GPU_JS_TAIL_HI) << 32)
  rock_gpu_job_affinity=RockGpuRead(base+#ROCK_GPU_JS_AFFINITY_LO) | (RockGpuRead(base+#ROCK_GPU_JS_AFFINITY_HI) << 32)
  rock_gpu_job_config=RockGpuRead(base+#ROCK_GPU_JS_CONFIG)
  rock_gpu_job_xaffinity=RockGpuRead(base+#ROCK_GPU_JS_XAFFINITY)
  rock_gpu_job_status=RockGpuRead(base+#ROCK_GPU_JS_STATUS)
  rock_gpu_job_head_next=RockGpuRead(base+#ROCK_GPU_JS_HEAD_NEXT_LO) | (RockGpuRead(base+#ROCK_GPU_JS_HEAD_NEXT_HI) << 32)
  rock_gpu_job_config_next=RockGpuRead(base+#ROCK_GPU_JS_CONFIG_NEXT)
  ProcedureReturn 1
EndProcedure

Procedure.i RockGpuProbeAddressSpace(addressSpace.i)
  Protected base.i
  If rock_gpu_probe_ready=0 : rock_gpu_error=#ROCK_GPU_ERROR_NOT_READY : ProcedureReturn 0 : EndIf
  If addressSpace<0 Or addressSpace>=#ROCK_GPU_MAX_ADDRESS_SPACES Or (rock_gpu_as_present & (1 << addressSpace))=0
    rock_gpu_error=#ROCK_GPU_ERROR_ADDRESS_SPACE : ProcedureReturn 0
  EndIf
  base=#ROCK_GPU_MMU_BASE+(addressSpace << #ROCK_GPU_MMU_AS_SHIFT)
  rock_gpu_address_space=addressSpace
  rock_gpu_as_transtab=RockGpuRead(base+#ROCK_GPU_AS_TRANSTAB_LO) | (RockGpuRead(base+#ROCK_GPU_AS_TRANSTAB_HI) << 32)
  rock_gpu_as_memattr=RockGpuRead(base+#ROCK_GPU_AS_MEMATTR_LO) | (RockGpuRead(base+#ROCK_GPU_AS_MEMATTR_HI) << 32)
  rock_gpu_as_lockaddr=RockGpuRead(base+#ROCK_GPU_AS_LOCKADDR_LO) | (RockGpuRead(base+#ROCK_GPU_AS_LOCKADDR_HI) << 32)
  rock_gpu_as_faultstatus=RockGpuRead(base+#ROCK_GPU_AS_FAULTSTATUS)
  rock_gpu_as_faultaddress=RockGpuRead(base+#ROCK_GPU_AS_FAULTADDRESS_LO) | (RockGpuRead(base+#ROCK_GPU_AS_FAULTADDRESS_HI) << 32)
  rock_gpu_as_status=RockGpuRead(base+#ROCK_GPU_AS_STATUS)
  ProcedureReturn 1
EndProcedure
