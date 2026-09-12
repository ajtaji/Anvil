"""Validate pinned Pi3 firmware; optionally create a NEW staging folder.

Never enumerates, partitions, formats or selects disks. No compiler is invoked.
The image hash must come from an independently accepted counted build.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

BOOT = Path(__file__).resolve().parents[1] / "RaspberryPi3" / "Boot"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(firmware, image, expected):
    manifest = json.loads((BOOT / "firmware.json").read_text())
    sources = {}
    for name, digest in manifest["files"].items():
        path = firmware / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"Pinned firmware mismatch: {name}")
        sources[name] = path
    if not image.is_file() or not image.stat().st_size or sha(image) != expected.lower():
        raise ValueError("Image missing, empty or different from the supplied accepted SHA256.")
    sources.update({"kernel8.img": image, "config.txt": BOOT / "config.txt",
                    "README.txt": BOOT / "README.txt",
                    "firmware.json": BOOT / "firmware.json"})
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", required=True, type=Path, help="directory containing official boot files")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--output", type=Path, help="new staging directory only; omit for read-only validation")
    args = parser.parse_args()
    sources = validate(args.firmware, args.image, args.image_sha256)
    hashes = {name: sha(path) for name, path in sources.items()}
    if args.output:
        output = args.output.absolute()
        if output.exists() or output.parent.resolve() == output.resolve():
            raise ValueError("Output must be a new directory, never an existing folder or drive root.")
        output.mkdir(parents=False, exist_ok=False)
        for name, source in sources.items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if sha(target) != hashes[name]:
                raise ValueError(f"Copy verification failed: {name}; incomplete staging directory retained.")
        (output / "SHA256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(json.dumps(hashes, indent=2))
    print("PASS: pinned bytes verified. This does not prove firmware entry, placement or hardware boot.")


if __name__ == "__main__":
    main()
