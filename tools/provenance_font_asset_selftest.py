"""Prove retained font assets cannot conceal implementation code or lost notices."""
from pathlib import Path
import copy
import json
import tempfile
from unittest.mock import patch

import provenance_inventory_check as gate


def main():
    original = json.loads(gate.MANIFEST.read_text(encoding="utf-8"))["third_party"]
    accepted = 0
    refused = 0
    for path, source in sorted(gate.LICENSED_FONT_ASSETS):
        report = gate.Report()
        gate.check_font_asset(path, source, original, report)
        assert not report.failures, report.failures
        accepted += 1

    path = "RaspberryPi4/Monitor/anvil_boot_ttf.pi4"
    source = "dejavu-fonts"
    font_text = (gate.ROOT / path).read_text(encoding="utf-8")
    license_path = original["sources"][source]["license_text"]
    license_bytes = (gate.ROOT / license_path).read_bytes()
    data = copy.deepcopy(original)
    data["sources"] = {source: data["sources"][source]}
    data["classified_files"] = {path: {source: gate.LICENSED_ASSET}}
    data["licensed_font_assets"] = {path: data["licensed_font_assets"][path]}
    with tempfile.TemporaryDirectory(prefix="font-provenance-") as folder:
        root = Path(folder)
        font = root / path
        font.parent.mkdir(parents=True)
        license_file = root / license_path
        license_file.parent.mkdir(parents=True)
        notices = root / "docs/THIRD_PARTY_NOTICES.md"
        notices.parent.mkdir(parents=True)

        def reset():
            font.write_text(font_text, encoding="utf-8")
            license_file.write_bytes(license_bytes)
            notices.write_text("## DejaVu fonts\nRetained DejaVu data.\n", encoding="utf-8")
            return copy.deepcopy(data)

        def expect(test_data, bad):
            nonlocal refused, accepted
            report = gate.Report()
            gate.check_classes(test_data, report)
            assert bool(report.failures) == bad, report.failures
            if bad:
                refused += 1
            else:
                accepted += 1

        with patch.object(gate, "ROOT", root), patch.object(gate, "NOTICES", notices):
            expect(reset(), False)
            for replacement in [
                font_text.replace("Data.b $00", "Data.b $01", 1),
                font_text.replace("705684", "705685", 1),
                font_text + "\nProcedure Run()\nEndProcedure\n",
                font_text.replace("EndDataSection", "", 1),
                font_text + '\nXIncludeFile "implementation.pbi"\n',
                font_text.replace("Data.b $00", "Data.b $100", 1),
            ]:
                d = reset()
                font.write_text(replacement, encoding="utf-8")
                expect(d, True)
            d = reset()
            license_file.unlink()
            expect(d, True)
            d = reset()
            license_file.write_bytes(license_bytes + b" altered")
            expect(d, True)
            for key in ["license_text", "acknowledgment"]:
                d = reset()
                del d["sources"][source][key]
                expect(d, True)
            d = reset()
            notices.write_text("## Another source\n", encoding="utf-8")
            expect(d, True)
            d = reset()
            del d["licensed_font_assets"][path]
            expect(d, True)
            d = reset()
            d["classified_files"] = {"Anvil/implementation.pbi": {source: gate.LICENSED_ASSET}}
            expect(d, True)
            d = reset()
            d["classified_files"][path][source] = "verbatim"
            expect(d, True)
            for cls in ["consulted", "reference-only"]:
                d = reset()
                d["classified_files"][path][source] = cls
                del d["licensed_font_assets"][path]
                expect(d, True)
            d = reset()
            # Comments and CRLF are not executable data or declarations.
            font.write_bytes((font_text.replace("\n", "\r\n") + "; retained comment\r\n").encode())
            expect(d, False)
            d = reset()
            license_file.write_bytes(license_bytes.replace(b"\r\n", b"\n"))
            expect(d, False)
    assert accepted == 5 and refused == 16, (accepted, refused)
    print(json.dumps(dict(accepted=accepted, refused=refused, board_execution=False)))


if __name__ == "__main__":
    main()
