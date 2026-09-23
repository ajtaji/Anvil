#!/usr/bin/env python3
"""Check the Windows Pi 3 card-root admission policy without writing a volume."""

from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pi3_provision", ROOT / "tools" / "pi3_provision.py")
PROVISION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PROVISION)


def refused(*args, **kwargs) -> bool:
    try:
        PROVISION.validate_windows_card_root(*args, **kwargs)
    except PROVISION.ProvisionError:
        return True
    return False


def main() -> None:
    checks = 0
    for fs in ("FAT", "FAT32"):
        PROVISION.validate_windows_card_root(
            "E:\\", "E:\\", 2, fs, "C:\\", confirmed=True,
        )
        checks += 1

    cases = (
        (("E:\\", "E:\\", 2, "FAT32", "C:\\"), {"confirmed": False}),
        (("C:\\", "C:\\", 2, "FAT32", "C:\\"), {"confirmed": True}),
        (("D:\\", "D:\\", 3, "FAT32", "C:\\"), {"confirmed": True}),
        (("E:\\", "E:\\", 2, "exFAT", "C:\\"), {"confirmed": True}),
        (("E:\\boot", "E:\\", 2, "FAT32", "C:\\"), {"confirmed": True}),
        (("E:", "E:\\", 2, "FAT32", "C:\\"), {"confirmed": True}),
    )
    for args, kwargs in cases:
        assert refused(*args, **kwargs), (args, kwargs)
        checks += 1
    print(f"pi3_provision_volume_check: PASS ({checks} read-only policy cases)")


if __name__ == "__main__":
    main()
