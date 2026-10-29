; Compile-time validation of an explicitly supplied Vulkan implementation.
; The program includes its backend before this file; shared code never
; imports a board driver. Each real implementation supplies its identity.

#ANVIL_VULKAN_BACKEND_V3D = 1
#ANVIL_VULKAN_BACKEND_SOFTWARE = 2

CompilerIf #ANVIL_VULKAN_BACKEND = #ANVIL_VULKAN_BACKEND_V3D
  CompilerIf #ANVIL_VULKAN_BACKEND_PRESENT <> #ANVIL_VULKAN_BACKEND_V3D
    CompilerError "Selected V3D backend does not match the explicitly included implementation"
  CompilerEndIf
CompilerElseIf #ANVIL_VULKAN_BACKEND = #ANVIL_VULKAN_BACKEND_SOFTWARE
  CompilerIf #ANVIL_VULKAN_BACKEND_PRESENT <> #ANVIL_VULKAN_BACKEND_SOFTWARE
    CompilerError "Selected software backend does not match the explicitly included implementation"
  CompilerEndIf
CompilerElse
  CompilerError "#ANVIL_VULKAN_BACKEND must select exactly one Vulkan backend"
CompilerEndIf
