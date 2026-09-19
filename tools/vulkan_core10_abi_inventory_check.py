#!/usr/bin/env python3
"""Hostile gate for the Vulkan 1.0 AArch64 ABI inventory."""

from __future__ import annotations

import argparse
import pathlib
import sys
import xml.etree.ElementTree as ET

import vulkan_core10_abi_inventory as abi
from vulkan_dispatch_inventory import InventoryError, pinned_registry_bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def item_map(items: list[abi.AbiItem]) -> dict[str, abi.AbiItem]:
    return {item.name: item for item in items}


def mutate_xml(data: bytes, callback) -> bytes:
    root = ET.fromstring(data)
    callback(root)
    return ET.tostring(root, encoding="utf-8")


def run(registry: pathlib.Path, pbi: pathlib.Path) -> int:
    data, _ = pinned_registry_bytes(registry)
    text = pbi.read_text(encoding="utf-8")
    baseline = abi.inventory(data, text)
    by_name = item_map(baseline)
    checks = 0

    # Exact pinned scope: this prevents silently auditing only a convenient
    # subset when Khronos splits or rearranges <feature number="1.0"> blocks.
    expected_categories = {"enum": 82, "bitmask": 58, "handle": 25,
                           "struct": 108, "union": 2, "funcpointer": 6}
    got_categories = {key: sum(x.category == key for x in baseline) for key in abi.CATEGORIES}
    require(got_categories == expected_categories, f"core category drift: {got_categories}")
    checks += 1
    require(len(baseline) == 281, "core declaration inventory is not 281 items")
    require(set(abi.summary(baseline)["statuses"]) == {"existing", "missing", "unrepresentable"},
            "dishonest status vocabulary")
    checks += 2

    # Authoritative LP64 sentinels exercise scalar, pointer, nested aggregate,
    # fixed array, handle, enum, bitmask, union, and function-pointer rules.
    sentinels = {
        "VkExtent3D": (12, 4, (0, 4, 8)),
        "VkApplicationInfo": (48, 8, (0, 8, 16, 24, 32, 40, 44)),
        "VkExtensionProperties": (260, 4, (0, 256)),
        "VkPhysicalDeviceMemoryProperties": (520, 8, (0, 4, 260, 264)),
    }
    for name, (size, align, offsets) in sentinels.items():
        item = by_name[name]
        require((item.expected.size, item.expected.alignment) == (size, align), name + " ABI size/alignment")
        require(tuple(m.offset for m in item.expected.members) == offsets, name + " ABI offsets")
        checks += 2
    require((by_name["VkInstance"].expected.size, by_name["VkInstance"].expected.alignment) == (8, 8),
            "dispatchable handle is not 8/8")
    require((by_name["VkBuffer"].expected.size, by_name["VkBuffer"].expected.alignment) == (8, 8),
            "non-dispatchable handle is not 8/8")
    require((by_name["VkResult"].expected.size, by_name["VkResult"].expected.alignment) == (4, 4),
            "C enum is not 4/4")
    checks += 3
    for name in ("VkClearColorValue", "VkClearValue"):
        require(by_name[name].status == "unrepresentable", name + " must not masquerade as a structure")
        require(all(m.offset == 0 for m in by_name[name].expected.members), name + " union offsets")
        checks += 2
    require(by_name["PFN_vkAllocationFunction"].expected == abi.TypeLayout(8, 8), "function pointer ABI")
    require("size_t size" in by_name["PFN_vkAllocationFunction"].details[0], "function prototype lost parameter")
    checks += 2

    # Baseline classification must be evidence-bearing but must not claim
    # semantics. Handles and PFNs lack named declarations today.
    require(all(by_name[name].status == "missing" for name in by_name if by_name[name].category == "handle"),
            "scalar field use was mistaken for a named handle declaration")
    require(all(by_name[name].status == "missing" for name in by_name if by_name[name].category == "funcpointer"),
            "pointer field use was mistaken for an exact PFN prototype")
    require("implemented" not in str(abi.summary(baseline)).lower(), "inventory claimed implementation")
    checks += 3

    # Hostile source drift: values, scalar width, pointer width, member order,
    # member kind, and fixed-array extent must change a classification/layout.
    enum_mut = text.replace("#VK_SUCCESS = 0", "#VK_SUCCESS = 99", 1)
    require(item_map(abi.inventory(data, enum_mut))["VkResult"].status == "missing", "enum-value mutant survived")
    checks += 1
    suffix_mut = text.replace("Structure VkExtent3D Align #PB_Structure_AlignC\n  width.l",
                              "Structure VkExtent3D Align #PB_Structure_AlignC\n  width.q", 1)
    require(item_map(abi.inventory(data, suffix_mut))["VkExtent3D"].status == "missing", "scalar-width mutant survived")
    checks += 1
    pointer_mut = text.replace("  *pApplicationName", "  pApplicationName.l", 1)
    require(item_map(abi.inventory(data, pointer_mut))["VkApplicationInfo"].status == "missing", "pointer-width mutant survived")
    checks += 1
    order_mut = text.replace("  width.l\n  height.l\n  depth.l", "  height.l\n  width.l\n  depth.l", 1)
    require(item_map(abi.inventory(data, order_mut))["VkExtent3D"].status == "missing", "member-order mutant survived")
    checks += 1
    array_mut = text.replace("extensionName.a[#VK_MAX_EXTENSION_NAME_SIZE]", "extensionName.a[8]", 1)
    require(item_map(abi.inventory(data, array_mut))["VkExtensionProperties"].status == "missing", "array-extent mutant survived")
    checks += 1
    nested_mut = text.replace("  extent.VkExtent2D", "  extent.VkExtent3D", 1)
    require(item_map(abi.inventory(data, nested_mut))["VkRect2D"].status == "missing", "nested-layout mutant survived")
    checks += 1
    fake_proto = text + "\nPrototype.i PFN_vkAllocationFunction(*pUserData, size.i, alignment.i, allocationScope.l)\n"
    require(item_map(abi.inventory(data, fake_proto))["PFN_vkAllocationFunction"].status == "existing",
            "exact named Prototype declaration was not recognized")
    checks += 1
    wrong_proto = text + "\nPrototype PFN_vkAllocationFunction(*pUserData, size.i, alignment.i, allocationScope.l)\n"
    require(item_map(abi.inventory(data, wrong_proto))["PFN_vkAllocationFunction"].status == "missing",
            "wrong function-pointer return ABI survived")
    checks += 1

    # Hostile registry drift bypasses the pin only inside the pure layout unit;
    # each change must affect the expected ABI. The public entry point still
    # rejects altered bytes via pinned_registry_bytes below.
    def change_member(root: ET.Element) -> None:
        node = next(t for t in root.findall("./types/type") if abi._type_name(t) == "VkExtent3D")
        node.findall("member")[0].find("type").text = "uint64_t"
    changed = item_map(abi.inventory(mutate_xml(data, change_member), text))["VkExtent3D"]
    require(changed.expected.size != by_name["VkExtent3D"].expected.size, "registry member-width mutant survived")
    checks += 1

    def change_array(root: ET.Element) -> None:
        group = next(g for g in root.findall("./enums") if g.get("name") == "API Constants")
        node = next(e for e in group.findall("enum") if e.get("name") == "VK_MAX_EXTENSION_NAME_SIZE")
        node.set("value", "8")
    changed = item_map(abi.inventory(mutate_xml(data, change_array), text))["VkExtensionProperties"]
    require(changed.expected.size == 12, "registry array mutant did not alter expected layout")
    checks += 1

    def change_handle(root: ET.Element) -> None:
        node = next(t for t in root.findall("./types/type") if abi._type_name(t) == "VkInstance")
        node.find("type").text = "VK_DEFINE_NON_DISPATCHABLE_HANDLE"
    changed = item_map(abi.inventory(mutate_xml(data, change_handle), text))["VkInstance"]
    require("non-dispatchable" in changed.details[0], "handle-kind mutant survived")
    checks += 1

    def change_union(root: ET.Element) -> None:
        node = next(t for t in root.findall("./types/type") if abi._type_name(t) == "VkClearColorValue")
        member = node.findall("member")[0]
        member.find("type").text = "uint64_t"
    changed = item_map(abi.inventory(mutate_xml(data, change_union), text))["VkClearColorValue"]
    require(changed.expected.size == 32 and changed.status == "unrepresentable", "union mutant survived")
    checks += 1

    def change_pfn(root: ET.Element) -> None:
        node = next(t for t in root.findall("./types/type") if abi._type_name(t) == "PFN_vkAllocationFunction")
        node.findall("param")[1].find("type").text = "uint32_t"
    changed = item_map(abi.inventory(mutate_xml(data, change_pfn), text))["PFN_vkAllocationFunction"]
    require("uint32_t size" in changed.details[0], "function-pointer prototype mutant survived")
    checks += 1

    try:
        pinned_registry_bytes(pathlib.Path(__file__))
    except InventoryError:
        checks += 1
    else:
        raise AssertionError("registry pin accepted hostile non-registry bytes")

    report = abi.summary(baseline)
    print(f"PASS: {checks} Vulkan core 1.0 ABI inventory checks")
    print("Coverage:", report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=pathlib.Path)
    parser.add_argument("--pbi", type=pathlib.Path, default=abi.VOCAB)
    args = parser.parse_args(argv)
    try:
        return run(args.registry, args.pbi)
    except (AssertionError, InventoryError, OSError, ET.ParseError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
