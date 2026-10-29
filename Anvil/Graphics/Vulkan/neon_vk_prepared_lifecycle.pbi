; SPDX-License-Identifier: MIT
; Optional bridge for a caller lending an already prepared native context to
; Chrome. Include after neon_lifecycle.pbi and neon_vk_chrome.pbi. It preserves
; the caller's prepared native ownership contract; core Chrome needs neither
; this bridge nor a native provider on a target without a graphics device.

Procedure.i NeonVkChromeLifecycleInstallPrepared()
  If nvcReady = 0 Or nvcInFrame <> 0 Or nvcHooksInstalled = 0 Or NeonVkChromePresentPending() <> 0
    ProcedureReturn #NEON_ERR_BACKEND
  EndIf
  ProcedureReturn NeonLifecycleInstallPrepared(@nvcLifecycleInit, @nvcLifecycleBegin, @nvcLifecycleEnd, @nvcLifecycleShutdown)
EndProcedure
