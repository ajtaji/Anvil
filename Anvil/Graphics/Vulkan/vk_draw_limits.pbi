; One shared recorded-draw ceiling for command snapshots and GPU draw slots.
; An indexed native outline closes with two physical draws. The complete
; native mix is bounded by 2*4096 flat + 2048 textured =10240 raw draws.
; A program that records fewer draws may set the ceiling before it includes
; the Vulkan library: about 1.4 KB of its variables per draw goes with it
; (avkFlightDraw, avkV3dBatchDraw, avkRecordedDraw, avkV3dCacheInterval,
; avkFlightSample, avkFlightBinding and nineteen smaller avkFlight* tables
; are all sized by it - 14,091,160 bytes at 10240, measured 2026-11-26).
; The monitor keeps 10240 for the reason above.
CompilerIf Not Defined(ANVIL_VK_MAX_RECORDED_DRAWS, #PB_Constant)
  #ANVIL_VK_MAX_RECORDED_DRAWS = 10240
CompilerEndIf
