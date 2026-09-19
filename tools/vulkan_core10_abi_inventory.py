#!/usr/bin/env python3
"""Inventory Vulkan 1.0 declarations and their AArch64 ABI layout.

The registry oracle is the same pinned Khronos vk.xml used by
``vulkan_dispatch_inventory.py``.  This tool deliberately audits declarations,
not behaviour: ``existing`` means that the PureMetal vocabulary contains the
required constants or an AArch64-layout-equivalent structure.  It never means
that an operation, object, or feature is implemented.

Only the six declaration categories requested by Vulkan 1.0 are reported:
enum, bitmask, handle, struct, union, and function pointer.  AArch64 uses the
standard LP64 C ABI (8-byte pointers/size_t/handles, 4-byte C enums/VkFlags).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass

from vulkan_dispatch_inventory import InventoryError, pinned_registry_bytes

ROOT = pathlib.Path(__file__).resolve().parent.parent
VOCAB = ROOT / "Anvil" / "Graphics" / "Vulkan" / "vk_core_1_0.pbi"
CATEGORIES = ("enum", "bitmask", "handle", "struct", "union", "funcpointer")
SCALARS = {
    "char": (1, 1), "int8_t": (1, 1), "uint8_t": (1, 1),
    "int16_t": (2, 2), "uint16_t": (2, 2),
    "int": (4, 4), "int32_t": (4, 4), "uint32_t": (4, 4),
    "float": (4, 4), "VkBool32": (4, 4),
    "int64_t": (8, 8), "uint64_t": (8, 8), "double": (8, 8),
    "size_t": (8, 8), "void*": (8, 8),
}
PB_SCALARS = {
    "a": (1, 1), "b": (1, 1), "c": (2, 2), "u": (2, 2), "w": (2, 2),
    "l": (4, 4), "f": (4, 4), "q": (8, 8), "d": (8, 8), "i": (8, 8),
}


@dataclass(frozen=True)
class MemberLayout:
    name: str
    type: str
    offset: int
    size: int
    alignment: int
    extent: int = 1


@dataclass(frozen=True)
class TypeLayout:
    size: int
    alignment: int
    members: tuple[MemberLayout, ...] = ()


@dataclass(frozen=True)
class AbiItem:
    name: str
    category: str
    status: str
    expected: TypeLayout
    actual: TypeLayout | None
    details: tuple[str, ...]


def _api_vulkan(node: ET.Element) -> bool:
    api = node.get("api")
    return api is None or "vulkan" in api.split(",")


def _type_name(node: ET.Element) -> str | None:
    return node.get("name") or node.findtext("name") or node.findtext("proto/name")


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & -alignment


def _declaration(node: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(node.itertext()).strip())


def required_core_types(root: ET.Element) -> tuple[str, ...]:
    names: set[str] = set()
    for feature in root.findall("./feature"):
        if feature.get("number") != "1.0" or "vulkan" not in (feature.get("api") or "").split(","):
            continue
        for require in feature.findall("require"):
            if not _api_vulkan(require):
                continue
            for node in require.findall("type"):
                if _api_vulkan(node) and node.get("name"):
                    names.add(node.get("name"))
    return tuple(sorted(names))


def _integer(text: str) -> int:
    text = text.strip()
    sentinels = {"(~0U)": 0xFFFFFFFF, "(~0ULL)": 0xFFFFFFFFFFFFFFFF,
                 "(~0U-1)": 0xFFFFFFFE}
    if text in sentinels:
        return sentinels[text]
    text = re.sub(r"(?i)(ULL|LL|UL|U|L)$", "", text)
    try:
        return int(text, 0)
    except ValueError as exc:
        raise InventoryError("not an integer registry constant: " + text) from exc


def registry_constants(root: ET.Element) -> dict[str, int]:
    nodes: dict[str, tuple[ET.Element, str | None]] = {}
    for group in root.findall("./enums"):
        for node in group.findall("enum"):
            if node.get("name"):
                nodes.setdefault(node.get("name"), (node, None))
    for extension in root.findall("./extensions/extension"):
        for node in extension.findall(".//enum"):
            if node.get("name"):
                nodes.setdefault(node.get("name"), (node, extension.get("number")))
    for feature in root.findall("./feature"):
        for node in feature.findall(".//enum"):
            if node.get("name"):
                nodes.setdefault(node.get("name"), (node, node.get("extnumber")))
    values: dict[str, int] = {}
    active: set[str] = set()

    def value(name: str) -> int:
        if name in values:
            return values[name]
        if name in active or name not in nodes:
            raise InventoryError("unresolvable registry constant " + name)
        active.add(name)
        node, parent_ext = nodes[name]
        if node.get("value") is not None:
            answer = _integer(node.get("value"))
        elif node.get("bitpos") is not None:
            answer = 1 << int(node.get("bitpos"))
        elif node.get("alias"):
            answer = value(node.get("alias"))
        elif node.get("offset") is not None:
            ext = node.get("extnumber") or parent_ext
            if ext is None:
                raise InventoryError("extension-valued constant has no extension number: " + name)
            answer = 1000000000 + (int(ext) - 1) * 1000 + int(node.get("offset"))
            if node.get("dir") == "-":
                answer = -answer
        else:
            raise InventoryError("registry constant has no numeric value: " + name)
        active.remove(name)
        values[name] = answer
        return answer

    for name in nodes:
        try:
            value(name)
        except InventoryError:
            pass
    return values


def required_enumerants(root: ET.Element) -> set[str]:
    result: set[str] = set()
    for feature in root.findall("./feature"):
        if feature.get("number") != "1.0" or "vulkan" not in (feature.get("api") or "").split(","):
            continue
        for require in feature.findall("require"):
            if _api_vulkan(require):
                result.update(node.get("name") for node in require.findall("enum")
                              if _api_vulkan(node) and node.get("name"))
    return result


def enum_members(root: ET.Element, required: set[str], groups_needed: set[str]) -> dict[str, tuple[str, ...]]:
    collected: dict[str, list[str]] = {name: [] for name in groups_needed}
    for group in root.findall("./enums"):
        name = group.get("name")
        if name not in groups_needed:
            continue
        # Values physically in the named group are the group's original core
        # vocabulary. Later promotions/additions live in feature/extension
        # require blocks and are added below only when core 1.0 requires them.
        collected[name].extend(node.get("name") for node in group.findall("enum")
                               if node.get("name") and _api_vulkan(node))
    for feature in root.findall("./feature"):
        if feature.get("number") != "1.0" or "vulkan" not in (feature.get("api") or "").split(","):
            continue
        for node in feature.findall(".//enum"):
            target = node.get("extends")
            name = node.get("name")
            if target in collected and name in required and name not in collected[target]:
                collected[target].append(name)
    return {name: tuple(values) for name, values in collected.items()}


class RegistryLayouts:
    def __init__(self, root: ET.Element, constants: dict[str, int]):
        self.root = root
        self.constants = constants
        self.types = {_type_name(node): node for node in root.findall("./types/type")
                      if _type_name(node)}
        self.cache: dict[str, TypeLayout] = {}
        self.active: set[str] = set()

    def layout(self, name: str) -> TypeLayout:
        if name in self.cache:
            return self.cache[name]
        if name in SCALARS:
            size, align = SCALARS[name]
            return TypeLayout(size, align)
        if name in self.active:
            raise InventoryError("recursive by-value registry type " + name)
        node = self.types.get(name)
        if node is None:
            raise InventoryError("no AArch64 layout rule for " + name)
        self.active.add(name)
        category = node.get("category")
        if category == "basetype":
            target = node.findtext("type")
            answer = self.layout(target)
        elif category == "enum":
            answer = TypeLayout(4, 4)
        elif category == "bitmask":
            answer = self.layout(node.findtext("type") or "VkFlags")
        elif category in ("handle", "funcpointer"):
            answer = TypeLayout(8, 8)
        elif category in ("struct", "union"):
            answer = self._aggregate(node, category == "union")
        else:
            raise InventoryError(f"unsupported layout category {category!r} for {name}")
        self.active.remove(name)
        self.cache[name] = answer
        return answer

    def _member_layout(self, member: ET.Element) -> tuple[int, int, int]:
        raw = "".join(member.itertext())
        ctype = member.findtext("type")
        if "*" in raw or ctype.startswith("PFN_"):
            base = TypeLayout(8, 8)
        else:
            base = self.layout(ctype)
        extents: list[int] = []
        for enum in member.findall("enum"):
            name = enum.text
            if name not in self.constants:
                raise InventoryError("unknown array extent " + str(name))
            extents.append(self.constants[name])
        literal = re.findall(r"\[\s*(\d+)\s*\]", raw)
        extents.extend(int(x) for x in literal)
        extent = 1
        for item in extents:
            extent *= item
        return base.size * extent, base.alignment, extent

    def _aggregate(self, node: ET.Element, union: bool) -> TypeLayout:
        offset = 0
        maximum = 0
        alignment = 1
        members: list[MemberLayout] = []
        for member in node.findall("member"):
            if not _api_vulkan(member):
                continue
            size, align, extent = self._member_layout(member)
            alignment = max(alignment, align)
            if union:
                member_offset = 0
                maximum = max(maximum, size)
            else:
                member_offset = _align(offset, align)
                offset = member_offset + size
            members.append(MemberLayout(member.findtext("name"), member.findtext("type"),
                                        member_offset, size, align, extent))
        size = _align(maximum if union else offset, alignment)
        return TypeLayout(size, alignment, tuple(members))


def parse_pbi_constants(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"\s*#(VK_[A-Z0-9_]+)\s*=\s*([^\s;]+)", line)
        if not match:
            continue
        token = match.group(2)
        try:
            result[match.group(1)] = int(token[1:], 16) if token.startswith("$") else int(token)
        except ValueError:
            pass
    return result


@dataclass(frozen=True)
class PbMember:
    name: str
    kind: str
    extent_token: str | None


def parse_pbi_structs(text: str) -> dict[str, tuple[PbMember, ...]]:
    result: dict[str, tuple[PbMember, ...]] = {}
    current: str | None = None
    members: list[PbMember] = []
    for raw in text.splitlines():
        line = raw.strip()
        start = re.fullmatch(r"Structure\s+(Vk\w+)\s+Align\s+#PB_Structure_AlignC", line)
        if start:
            current, members = start.group(1), []
            continue
        if line == "EndStructure" and current:
            result[current] = tuple(members)
            current = None
            continue
        if not current or not line or line.startswith(";"):
            continue
        pointer = re.fullmatch(r"\*(\w+)(?:\[(#[A-Z0-9_]+|\d+)\])?", line)
        scalar = re.fullmatch(r"(\w+)\.([A-Za-z][A-Za-z0-9_]*)(?:\[(#[A-Z0-9_]+|\d+)\])?", line)
        if pointer:
            members.append(PbMember(pointer.group(1), "pointer", pointer.group(2)))
        elif scalar:
            members.append(PbMember(scalar.group(1), scalar.group(2), scalar.group(3)))
        else:
            members.append(PbMember("<unparsed>", line, None))
    return result


def _pb_abi_kind(token: str | None, pointer: bool = False) -> str:
    if pointer:
        return "i64"
    if token is None:
        return "void"
    sizes = {"a": "i8", "b": "i8", "c": "i16", "u": "i16", "w": "i16",
             "l": "i32", "f": "f32", "q": "i64", "d": "f64", "i": "i64"}
    return sizes.get(token, "unknown:" + token)


def parse_pbi_prototypes(text: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    result: dict[str, tuple[str, tuple[str, ...]]] = {}
    pattern = re.compile(r"(?m)^\s*Prototype(?:\.([A-Za-z]))?\s+(PFN_vk\w+)\s*\(([^)]*)\)")
    for match in pattern.finditer(text):
        params: list[str] = []
        for raw in (x.strip() for x in match.group(3).split(",")):
            if not raw:
                continue
            if raw.startswith("*"):
                params.append("i64")
                continue
            suffix = re.search(r"\.([A-Za-z])$", raw)
            params.append(_pb_abi_kind(suffix.group(1) if suffix else None))
        result[match.group(2)] = (_pb_abi_kind(match.group(1)), tuple(params))
    return result


def registry_pfn_abi(node: ET.Element, layouts: RegistryLayouts) -> tuple[str, tuple[str, ...]]:
    def kind(decl: ET.Element) -> str:
        raw = "".join(decl.itertext())
        ctype = decl.findtext("type")
        if "*" in raw or ctype.startswith("PFN_"):
            return "i64"
        if ctype == "void":
            return "void"
        layout = layouts.layout(ctype)
        if ctype == "float":
            return "f32"
        if ctype == "double":
            return "f64"
        return "i" + str(layout.size * 8)
    proto = node.find("proto")
    if proto is None:
        raise InventoryError("function pointer has no prototype")
    return kind(proto), tuple(kind(param) for param in node.findall("param") if _api_vulkan(param))


class PbLayouts:
    def __init__(self, structs: dict[str, tuple[PbMember, ...]], constants: dict[str, int]):
        self.structs, self.constants = structs, constants
        self.cache: dict[str, TypeLayout] = {}
        self.active: set[str] = set()

    def layout(self, name: str) -> TypeLayout:
        if name in self.cache:
            return self.cache[name]
        if name in self.active:
            raise InventoryError("recursive PureMetal structure " + name)
        if name not in self.structs:
            raise InventoryError("missing PureMetal structure " + name)
        self.active.add(name)
        offset, alignment = 0, 1
        members: list[MemberLayout] = []
        for field in self.structs[name]:
            if field.kind == "pointer":
                base = TypeLayout(8, 8)
            elif field.kind in PB_SCALARS:
                size, align = PB_SCALARS[field.kind]
                base = TypeLayout(size, align)
            elif field.kind in self.structs:
                base = self.layout(field.kind)
            else:
                raise InventoryError(f"unrepresentable PureMetal member {name}.{field.name}: {field.kind}")
            extent = 1
            if field.extent_token:
                token = field.extent_token
                if token.startswith("#"):
                    key = token[1:]
                    if key not in self.constants:
                        raise InventoryError("unknown PureMetal array extent " + token)
                    extent = self.constants[key]
                else:
                    extent = int(token)
            member_offset = _align(offset, base.alignment)
            size = base.size * extent
            members.append(MemberLayout(field.name, field.kind, member_offset, size,
                                        base.alignment, extent))
            offset = member_offset + size
            alignment = max(alignment, base.alignment)
        answer = TypeLayout(_align(offset, alignment), alignment, tuple(members))
        self.active.remove(name)
        self.cache[name] = answer
        return answer


def function_pointer_prototype(node: ET.Element) -> str:
    proto = node.find("proto")
    result = _declaration(proto) if proto is not None else ""
    params = [_declaration(param) for param in node.findall("param") if _api_vulkan(param)]
    return result + "(" + ", ".join(params) + ")"


def _same_aggregate(expected: TypeLayout, actual: TypeLayout) -> tuple[bool, tuple[str, ...]]:
    details: list[str] = []
    if (actual.size, actual.alignment) != (expected.size, expected.alignment):
        details.append(f"layout actual {actual.size}/{actual.alignment}, expected {expected.size}/{expected.alignment}")
    e = tuple((m.name, m.offset, m.size, m.alignment, m.extent) for m in expected.members)
    a = tuple((m.name, m.offset, m.size, m.alignment, m.extent) for m in actual.members)
    if a != e:
        details.append("member name/order/offset/size/alignment/extent differs")
    return not details, tuple(details)


def inventory(registry_data: bytes, pbi_text: str) -> list[AbiItem]:
    root = ET.fromstring(registry_data)
    types = {_type_name(node): node for node in root.findall("./types/type") if _type_name(node)}
    required = required_core_types(root)
    constants = registry_constants(root)
    required_constants = required_enumerants(root)
    groups_needed: set[str] = set()
    for name in required:
        node = types.get(name)
        if node is None:
            continue
        if node.get("category") == "enum":
            groups_needed.add(name)
        elif node.get("category") == "bitmask":
            group = node.get("bitvalues") or node.get("requires")
            if group:
                groups_needed.add(group)
    groups = enum_members(root, required_constants, groups_needed)
    pbi_constants = parse_pbi_constants(pbi_text)
    pbi_structs = parse_pbi_structs(pbi_text)
    registry_layouts = RegistryLayouts(root, constants)
    pbi_layouts = PbLayouts(pbi_structs, pbi_constants)
    prototypes = parse_pbi_prototypes(pbi_text)
    result: list[AbiItem] = []
    for name in required:
        node = types.get(name)
        if node is None or node.get("category") not in CATEGORIES:
            continue
        category = node.get("category")
        expected = registry_layouts.layout(name)
        actual = None
        details: list[str] = []
        if category == "union":
            status = "unrepresentable"
            details.append("PureMetal has no union declaration; no structure substitute is ABI-honest")
        elif category == "struct":
            if name not in pbi_structs:
                status = "missing"
                details.append("no PureMetal structure declaration")
            else:
                try:
                    actual = pbi_layouts.layout(name)
                    exact, mismatch = _same_aggregate(expected, actual)
                    status = "existing" if exact else "missing"
                    details.extend(mismatch)
                except InventoryError as exc:
                    status = "missing"
                    details.append(str(exc))
        elif category in ("enum", "bitmask"):
            group_name = name
            if category == "bitmask":
                group_name = node.get("bitvalues") or node.get("requires") or ""
            names = groups.get(group_name, ())
            absent = [item for item in names if item not in pbi_constants]
            wrong = [item for item in names if item in pbi_constants and
                     pbi_constants[item] != constants.get(item)]
            if names and not absent and not wrong:
                status = "existing"
            else:
                status = "missing"
            if not names:
                details.append("no required named values and no named PureMetal typedef")
            if absent:
                details.append("missing values: " + ", ".join(absent))
            if wrong:
                details.append("wrong values: " + ", ".join(wrong))
            details.append(f"required values {len(names)}")
        elif category == "funcpointer":
            wanted_abi = registry_pfn_abi(node, registry_layouts)
            status = "existing" if prototypes.get(name) == wanted_abi else "missing"
            details.append("prototype: " + function_pointer_prototype(node))
            details.append("AArch64 ABI: " + repr(wanted_abi))
            if name not in prototypes:
                details.append("no named PureMetal Prototype declaration")
            elif status == "missing":
                details.append("PureMetal Prototype ABI differs: " + repr(prototypes[name]))
        else:  # handle
            status = "missing"
            macro = node.findtext("type") or ""
            details.append(("dispatchable" if macro == "VK_DEFINE_HANDLE" else "non-dispatchable") +
                           " 64-bit AArch64 handle; no named PureMetal declaration")
        result.append(AbiItem(name, category, status, expected, actual, tuple(details)))
    return result


def summary(items: list[AbiItem]) -> dict[str, object]:
    statuses = {key: 0 for key in ("existing", "missing", "unrepresentable")}
    categories = {key: {status: 0 for status in statuses} for key in CATEGORIES}
    for item in items:
        statuses[item.status] += 1
        categories[item.category][item.status] += 1
    return {"total": len(items), "statuses": statuses, "categories": categories}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=pathlib.Path)
    parser.add_argument("--pbi", type=pathlib.Path, default=VOCAB)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--missing", action="store_true", help="print gap names after summary")
    args = parser.parse_args(argv)
    try:
        data, source_form = pinned_registry_bytes(args.registry)
        items = inventory(data, args.pbi.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError, InventoryError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1
    report = {"registry": source_form, "architecture": "AArch64 LP64",
              "meaning": "declaration/ABI coverage only; no semantic support inference",
              "summary": summary(items), "items": [asdict(item) for item in items]}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Vulkan core 1.0 AArch64 declaration/ABI inventory")
        print("Registry:", source_form)
        print("Coverage:", json.dumps(report["summary"], sort_keys=True))
        if args.missing:
            for item in items:
                if item.status != "existing":
                    print(f"{item.status:15} {item.category:11} {item.name}: " + "; ".join(item.details))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
