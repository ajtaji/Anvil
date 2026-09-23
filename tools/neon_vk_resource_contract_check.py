#!/usr/bin/env python3
"""Host model gate for the Neon Vulkan resource and present contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "RaspberryPi4/Tests/neon_vk_resource_contract.json"


class ContractError(Exception):
    pass


class Model:
    def __init__(self, limits: dict[str, int]):
        self.limits = limits
        self.used = {key: 0 for key in limits}
        self.frame = False
        self.completed_frame = False
        self.target_generation = 1
        self.target_staged = 0
        self.target_lost = False
        self.atlas_generation = 1
        self.atlas_pending = 0
        self.atlas_retired: dict[int, int] = {}
        self.present = "free"
        self.present_target = 0
        self.present_image = 0
        self.present_atlas = 0
        self.live = 0

    def snapshot(self):
        return (self.used.copy(), self.frame, self.completed_frame,
                self.target_generation, self.target_staged, self.target_lost,
                self.atlas_generation, self.atlas_pending,
                self.atlas_retired.copy(), self.present, self.present_target,
                self.present_image, self.present_atlas, self.live)

    def restore(self, state):
        (self.used, self.frame, self.completed_frame, self.target_generation,
         self.target_staged, self.target_lost, self.atlas_generation,
         self.atlas_pending, retired, self.present, self.present_target,
         self.present_image, self.present_atlas, self.live) = state
        self.atlas_retired = retired

    def run(self, op: dict):
        name = op["op"]
        if name == "frame_begin":
            if self.frame or self.present != "free":
                raise ContractError("frame begin while busy")
            self.used = {key: 0 for key in self.limits}
            self.frame = True
            self.completed_frame = False
        elif name == "frame_end":
            if not self.frame:
                raise ContractError("frame end without frame")
            self.frame = False
            self.completed_frame = True
        elif name == "preflight":
            if not self.frame:
                raise ContractError("preflight outside frame")
            requested = {key: int(op.get(key, 0)) for key in self.limits}
            if any(value < 0 for value in requested.values()):
                raise ContractError("negative capacity request")
            if any(self.used[key] + requested[key] > self.limits[key]
                   for key in self.limits):
                raise ContractError("capacity refusal")
            self.used = {key: self.used[key] + requested[key]
                         for key in self.limits}
        elif name == "atlas_replace":
            generation = int(op["generation"])
            if generation <= self.atlas_generation or self.atlas_pending:
                raise ContractError("invalid atlas replacement")
            self.atlas_pending = generation
            self.atlas_retired[generation] = int(op.get("submit_refs", 0))
            self.live += 1
        elif name == "atlas_complete":
            generation = int(op["generation"])
            if generation != self.atlas_pending:
                raise ContractError("atlas completion generation mismatch")
            if self.atlas_retired.get(generation, 0) < 0:
                raise ContractError("invalid atlas references")
            old = self.atlas_generation
            old_refs = self.atlas_retired.pop(generation, 0)
            self.atlas_generation = generation
            self.atlas_pending = 0
            if old_refs:
                self.atlas_retired[old] = old_refs
            else:
                self.live -= 1
        elif name == "atlas_rollback":
            generation = int(op["generation"])
            if generation != self.atlas_pending:
                raise ContractError("atlas rollback without pending generation")
            if self.atlas_pending == generation:
                self.atlas_pending = 0
                self.atlas_retired.pop(generation, None)
                self.live -= 1
        elif name == "atlas_release":
            generation = int(op["generation"])
            count = int(op["count"])
            refs = self.atlas_retired.get(generation)
            if refs is None or count <= 0 or count > refs:
                raise ContractError("invalid atlas release")
            refs -= count
            if refs:
                self.atlas_retired[generation] = refs
            else:
                del self.atlas_retired[generation]
                self.live -= 1
        elif name == "atlas_use":
            if int(op["generation"]) != self.atlas_generation:
                raise ContractError("stale atlas descriptor")
        elif name == "target_rebind_begin":
            generation = int(op["generation"])
            if (generation <= self.target_generation or self.target_staged or
                    self.target_lost):
                raise ContractError("invalid target rebind")
            self.target_staged = generation
        elif name == "target_rebind_commit":
            generation = int(op["generation"])
            if generation != self.target_staged:
                raise ContractError("target commit generation mismatch")
            self.target_generation = generation
            self.target_staged = 0
            self.target_lost = False
        elif name == "target_rollback":
            generation = int(op["generation"])
            if generation != self.target_staged:
                raise ContractError("target rollback is not a staged change")
            self.target_staged = 0
        elif name == "target_loss":
            self.target_lost = True
            if self.present != "free":
                self.present = "free"
                self.present_target = 0
                self.present_image = 0
                self.present_atlas = 0
                self.live -= 1
        elif name == "present_reserve":
            if (self.present != "free" or self.target_lost or
                    not self.completed_frame):
                raise ContractError("present reservation refused")
            target = int(op["target_generation"])
            atlas = int(op["atlas_generation"])
            if target != self.target_generation or atlas != self.atlas_generation:
                raise ContractError("stale target present")
            self.present = "reserved"
            self.present_target = target
            self.present_image = int(op["image"])
            self.present_atlas = atlas
            self.live += 1
        elif name == "present_commit":
            if (self.present != "reserved" or self.target_lost or
                    self.present_target != self.target_generation or
                    self.present_atlas != self.atlas_generation):
                raise ContractError("present commit refused")
            self.present = "committed"
        elif name == "present_consume":
            if self.present != "committed" or self.target_lost:
                raise ContractError("present consume refused")
            self.present = "free"
            self.present_target = 0
            self.present_image = 0
            self.present_atlas = 0
            self.completed_frame = False
            self.live -= 1
        elif name == "resource_retain":
            count = int(op["count"])
            if count < 0:
                raise ContractError("negative retain")
            self.live += count
        elif name == "teardown":
            if (self.frame or self.present != "free" or self.atlas_pending or
                    self.atlas_retired or self.target_staged or self.live):
                raise ContractError("teardown leaked live resources")
        else:
            raise ContractError("unknown operation: " + name)


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    limits = data.get("limits", {})
    expected = {"flat_draws": 4096, "flat_vertices": 262144,
                "textured_draws": 2048, "textured_vertices": 98304}
    if limits != expected:
        raise ContractError(f"capacity contract drift: {limits!r}")
    return data


def run_ops(data: dict, ops: list[dict], expect_success: bool,
            expected_index: int | None = None,
            expected_error: str | None = None) -> None:
    model = Model(data["limits"])
    for index, op in enumerate(ops):
        before = model.snapshot()
        try:
            model.run(op)
        except ContractError:
            model.restore(before)
            if expect_success:
                raise
            if expected_index is None or expected_error is None:
                raise ContractError("hostile mutation lacks exact failure contract")
            if index != expected_index:
                raise ContractError(
                    f"mutation failed at operation {index}, expected {expected_index}")
            try:
                model.run(op)
            except ContractError as exc:
                if str(exc) != expected_error:
                    raise ContractError(
                        f"mutation error {str(exc)!r}, expected {expected_error!r}")
                return
            raise ContractError("mutation failure was not reproducible")
    if not expect_success:
        raise ContractError("hostile mutation escaped")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    data = load(args.fixture.resolve())
    run_ops(data, data["baseline"], True)
    for control in data.get("controls", []):
        run_ops(data, control["ops"], True)
    for mutation in data["mutations"]:
        try:
            run_ops(data, mutation["ops"], False,
                    int(mutation["expected_index"]), mutation["expected_error"])
        except ContractError as exc:
            raise ContractError(mutation["name"] + ": " + str(exc)) from exc
    print("neon_vk_resource_contract_check: PASS")
    print(f"  baseline operations: {len(data['baseline'])}")
    print(f"  positive controls passed: {len(data.get('controls', []))}")
    print(f"  hostile mutations rejected: {len(data['mutations'])}")
    print("  capacities: flat 4096/262144, textured 2048/98304")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        print("neon_vk_resource_contract_check: FAIL - " + str(exc))
        raise SystemExit(1)
