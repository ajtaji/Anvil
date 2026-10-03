; ======================================================================
;  Compile-time Vulkan backend selection
; ======================================================================
; The public API has one backend seam. Select exactly one implementation
; before this file is included; selecting none or an unknown value fails
; at compile time instead of producing duplicate or accidental symbols.

#ANVIL_VULKAN_BACKEND_V3D = 1
#ANVIL_VULKAN_BACKEND_SOFTWARE = 2

CompilerIf #ANVIL_VULKAN_BACKEND = #ANVIL_VULKAN_BACKEND_V3D
XIncludeFile "Anvil/Graphics/Vulkan/vk_v3d_backend.pi4"
CompilerElseIf #ANVIL_VULKAN_BACKEND = #ANVIL_VULKAN_BACKEND_SOFTWARE
XIncludeFile "Anvil/Graphics/Vulkan/vk_backend_software.pbi"
CompilerElse
CompilerError "#ANVIL_VULKAN_BACKEND must select exactly one Vulkan backend"
CompilerEndIf
