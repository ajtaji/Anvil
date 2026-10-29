"""Check all retained boot-stub sources and refuse lost or bypassed notices."""
from pathlib import Path
import copy
import json
import tempfile
from unittest.mock import patch
import provenance_inventory_check as gate


def main():
    original = json.loads(gate.MANIFEST.read_text(encoding="utf8"))["third_party"]
    data = copy.deepcopy(original)
    data["classified_files"] = {}
    data["licensed_font_assets"] = {}
    for path, source in sorted(gate.LICENSED_ADAPTATIONS):
        data["classified_files"].setdefault(path, {})[source] = gate.LICENSED_ADAPTATION
    report = gate.Report()
    gate.check_classes(data, report)
    assert not report.failures and report.passed == 4, report.failures
    names = set(data["classified_files"])
    names.update(original["sources"][source]["license_text"]
                 for _, source in gate.LICENSED_ADAPTATIONS)
    names.add("docs/THIRD_PARTY_NOTICES.md")
    blobs = {name: (gate.ROOT / name).read_bytes() for name in names}
    refused = 0
    valid = 4
    with tempfile.TemporaryDirectory(prefix="stub-provenance-") as folder:
        root = Path(folder)

        def reset():
            for name, blob in blobs.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(blob)
            return copy.deepcopy(data)

        def check(d, bad=True):
            nonlocal refused, valid
            result = gate.Report()
            gate.check_classes(d, result)
            assert bool(result.failures) == bad, result.failures
            if bad:
                refused += 1
            else:
                valid += 1

        with patch.object(gate, "ROOT", root), patch.object(gate, "NOTICES", root / "docs/THIRD_PARTY_NOTICES.md"):
            for path, source in sorted(gate.LICENSED_ADAPTATIONS):
                notice = original["sources"][source]["required_copyright_notices"][0]
                d = reset()
                p = root / path
                p.write_text(p.read_text(encoding="utf8").replace(notice, "removed notice"), encoding="utf8")
                check(d)
                d = reset()
                p = root / d["sources"][source]["license_text"]
                p.write_text(p.read_text(encoding="utf8") + "changed terms", encoding="utf8")
                check(d)
                d = reset()
                d["classified_files"][path][source] = "consulted"
                check(d)
            for field in ["license_text", "acknowledgment", "required_copyright_notices", "retained_license_sha256"]:
                d = reset()
                del d["sources"]["rpi-tfa-bcm2712"][field]
                check(d)
            d = reset()
            (root / d["sources"]["rpi-tfa-bcm2712"]["license_text"]).unlink()
            check(d)
            d = reset()
            (root / "docs/THIRD_PARTY_NOTICES.md").write_text("## Unrelated\n", encoding="utf8")
            check(d)
            d = reset()
            d["classified_files"]["Anvil/unknown.pbi"] = {"rpi-tfa-bcm2712": gate.LICENSED_ADAPTATION}
            check(d)
            d = reset()
            for source in ["rpi-armstub8", "rpi-tfa-bcm2712"]:
                p = root / d["sources"][source]["license_text"]
                p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))
            check(d, False)
    assert valid == 5 and refused == 19, (valid, refused)
    print(json.dumps(dict(accepted=valid, refused=refused, board_execution=False)))


if __name__ == "__main__":
    main()
