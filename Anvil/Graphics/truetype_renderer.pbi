; Single dependency owner for the resident Vulkan text adapter and Anvil font
; commands. Keep parser modules in lifecycle order so every include graph sees
; one consistent T0 -> metrics/cmap/outlines -> raster/layout -> slot set.
XIncludeFile "Anvil/Graphics/truetype.pbi"
XIncludeFile "Anvil/Graphics/truetype_metrics.pbi"
XIncludeFile "Anvil/Graphics/truetype_cmap.pbi"
XIncludeFile "Anvil/Graphics/truetype_outlines.pbi"
XIncludeFile "Anvil/Graphics/truetype_raster.pbi"
XIncludeFile "Anvil/Graphics/truetype_kern.pbi"
XIncludeFile "Anvil/Graphics/truetype_gpos.pbi"
XIncludeFile "Anvil/Graphics/truetype_layout.pbi"
XIncludeFile "Anvil/Graphics/truetype_slots.pbi"
