# Vulkan foundation third-party notices

## Khronos Vulkan Registry

`vk_core_1_0.pbi` and the registry generator derive names, values, type/member
relationships and ordering from the Khronos Vulkan API Registry:

- Copyright (c) 2015-2023 The Khronos Group Inc.
- SPDX-License-Identifier: Apache-2.0 OR MIT
- Source: `https://github.com/KhronosGroup/Vulkan-Headers/tree/v1.4.350/registry`
- Pinned commit: `8864cdc896bbc2a9b6eb36b3218fc9ef57908d77`

The registry file itself is not vendored in this source closure. The generator
accepts the pinned `vk.xml` and verifies its byte-exact SHA-256 before emitting
anything. This distribution selects the MIT option. The complete, unmodified
Khronos MIT text is retained in
`licenses/Khronos-Vulkan-Registry-MIT.txt`.

`vk_surface.pbi` independently implements the surface contract from the official
Vulkan specification. Its command names, revision and C structure member order
and widths use the same registry interface facts and MIT election above. The
existing Khronos notice and complete license text are retained; no driver or
other implementation code was consulted or copied.

## Khronos SPIR-V specification

`vk_spirv.pbi` and `vk_spirv_fixtures.pbi` take the SPIR-V binary layout, the
opcode numbers and the enumerants from the Khronos SPIR-V specification and its
registry, and the shader-module validation boundary from the Vulkan
specification's environment appendix:

- Copyright (c) 2014-2024 The Khronos Group Inc.
- Source: `https://registry.khronos.org/SPIR-V/`
- Environment: `https://docs.vulkan.org/spec/latest/appendices/spirvenv.html`

The values are transcribed the way a header's values are. Nothing from
SPIRV-Tools, from glslang, from any other SPIR-V tool or from any driver was
read, translated or copied: the walker, the validation rules, the refusal set,
the plan and the emitted QPU programs are this tree's own.
