; SPDX-License-Identifier: MIT
; Optional owned-font client. Include the base graphics and file clients.
; Load returns a positive font handle or zero, with a detailed service error.
Procedure.i NeonServiceFontLoadMemory(data.i,bytes.i,role.i,pixels.i)
  Protected request.NeonServiceFontLoadRequest,font.i
  If data<1 Or bytes<1 Or bytes>#NEON_SERVICE_MAX_FONT_BYTES Or role<0 Or role>3 Or pixels<1 Or pixels>512
    NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : ProcedureReturn 0
  EndIf
  request\data=data : request\bytes=bytes : request\role=role : request\pixels=pixels
  font=NeonServiceRequestExtension(#NEON_SERVICE_FONT_LOAD,@request,SizeOf(NeonServiceFontLoadRequest),0,#NEON_SERVICE_FONT_BYTES,#NEON_SERVICE_FONT_BYTES_MINOR,0)
  If font<0 : ProcedureReturn 0 : EndIf
  If font<=3 : NeonServiceExtensionStatus(#NEON_SERVICE_ERR_PROVIDER) : ProcedureReturn 0 : EndIf
  ProcedureReturn font
EndProcedure
Procedure.i NeonServiceFontUnload(font.i)
  Protected request.NeonServiceFontUnloadRequest
  If font<=3 : ProcedureReturn NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : EndIf
  request\font=font
  ProcedureReturn NeonServiceExtensionStatus(NeonServiceRequestExtension(#NEON_SERVICE_FONT_UNLOAD,@request,SizeOf(NeonServiceFontUnloadRequest),0,#NEON_SERVICE_FONT_BYTES,#NEON_SERVICE_FONT_BYTES_MINOR,0))
EndProcedure
Procedure.i NeonServiceFontLoadFile(path.i,buffer.i,capacity.i,role.i,pixels.i)
  Protected bytes.i
  If path=0 Or capacity<1 Or role<0 Or role>3 Or pixels<1 Or pixels>512
    NeonServiceExtensionStatus(#NEON_SERVICE_ERR_ARGS) : ProcedureReturn 0
  EndIf
  If capacity>#NEON_SERVICE_MAX_FONT_BYTES : capacity=#NEON_SERVICE_MAX_FONT_BYTES : EndIf
  bytes=AnvilFileReadWhole(path,buffer,capacity)
  If bytes<0 : NeonServiceExtensionStatus(bytes) : ProcedureReturn 0 : EndIf
  ProcedureReturn NeonServiceFontLoadMemory(buffer,bytes,role,pixels)
EndProcedure
