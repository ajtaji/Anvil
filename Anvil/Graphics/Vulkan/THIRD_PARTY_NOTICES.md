# Vulkan foundation third-party notices

## Khronos Vulkan Registry

`vk_core_1_0.pbi` and the registry generator derive names, values, type/member
relationships and ordering from the Khronos Vulkan API Registry:

- Copyright (c) 2015-2023 The Khronos Group Inc.
- SPDX-License-Identifier: Apache-2.0 OR MIT
- Source: `https://github.com/KhronosGroup/Vulkan-Headers/tree/v1.4.350/registry`
- Pinned commit: `a33416ed2ce6bf8ef48b4eda821825f66d1850d3`

The registry file itself is not vendored in this source closure. The generator
accepts the pinned `vk.xml` and verifies its byte-exact SHA-256 before emitting
anything. This distribution selects the MIT option. The complete, unmodified
Khronos MIT text is retained in
`licenses/Khronos-Vulkan-Registry-MIT.txt`.

## PureBasic XML generator reference

The XML traversal in `tools/vulkan_registry_generator.pb` was informed by
`vkXMLDumper.pb` by Booger of Purebasic Forums:

> Copyright 2026 Booger of Purebasic Forums
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the “Software”), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.
