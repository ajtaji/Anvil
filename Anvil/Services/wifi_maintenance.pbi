; Monitor-internal Wi-Fi maintenance service, separate from frame transport.
; Bind one synchronous provider before servicing payloads or the prompt; change
; it only while those callers are stopped. Operation 1 advances the driver's
; existing bounded maintenance step; operation 2 requests its next health check.
; Neither operation promises a connected radio or successful recovery. An
; unbound service is a no-op for compositions without radio maintenance.
#WIFI_MAINTENANCE_TICK = 1
#WIFI_MAINTENANCE_CHECK_NOW = 2
Global *wifiMaintenanceProvider = 0

Procedure WifiMaintenanceBind(*provider)
  *wifiMaintenanceProvider = *provider
EndProcedure

Procedure WifiMaintenanceTick()
  Define ignored.i
  If *wifiMaintenanceProvider <> 0
    ignored = wifiMaintenanceProvider(#WIFI_MAINTENANCE_TICK)
  EndIf
EndProcedure

Procedure WifiMaintenanceCheckNow()
  Define ignored.i
  If *wifiMaintenanceProvider <> 0
    ignored = wifiMaintenanceProvider(#WIFI_MAINTENANCE_CHECK_NOW)
  EndIf
EndProcedure
