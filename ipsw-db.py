#!/usr/bin/env -S PYTHONPATH=. uv run --script

from pathlib import Path
import base64
import subprocess
import shutil
import tempfile
import argparse
import sys

from zipfile import ZipFile
from ipsw.reader import Reader
from ipsw.aea import get_key
from ipsw.theapplewiki import get_page_name, fetch_page
from osx.product import name as macos_name
from indexer.db import Writer
from indexer.visitor import FileSystemVisitor
from indexer.detect import is_macho
from indexer.entitlements import xml as entitlements
from indexer.image import ImageBackendError, get_image_backend


# Mount point of each cryptex relative to the device root. macOS 27 added the
# Rosetta cryptex (Cryptex1,RosettaOS), which previously shipped as a separate
# on-demand install on the Data volume.
CRYPTEX_ROOTS = {
    "Cryptex1,SystemOS": "/System/Cryptexes/OS/",
    "Cryptex1,AppOS": "/System/Cryptexes/App/",
    "Cryptex1,RosettaOS": "/System/Cryptexes/Rosetta/",
}


def filesystem_root(name: str):
    """Return the device-root prefix for an image component, or None if unknown.

    Unknown components are skipped (not fatal) so a newly introduced cryptex
    does not abort processing of the rest of the firmware.
    """
    if name in ("OS", "User"):
        return "/"

    return CRYPTEX_ROOTS.get(name)


def build_database(ipsw: str, output: Path, merge: bool):
    # Convert to absolute path so it works when running commands from temp directories
    ipsw = str(Path(ipsw).resolve())
    reader = Reader(ipsw)
    image_backend = get_image_backend()

    dbname = "ent.db" if merge else f'{reader.version}_{reader.build}.db'
    db = str(output / dbname)

    joint_devices = "|".join(reader.devices)
    if "iPhone" in joint_devices:
        product_name = f"iOS {reader.version}"
    elif "Mac" in joint_devices:
        product_name = macos_name(reader.version)
    else:
        raise NotImplementedError(f"Device type {reader.devices} not supported yet")

    writer = Writer(
        db,
        product_name,
        reader.build,
        reader.version,
        reader.devices,
    )

    # Get expected file sizes and extract all images from IPSW first
    expected_sizes = {}
    paths_to_extract = list(reader.images.values())
    with ZipFile(ipsw, "r") as zf:
        for info in zf.infolist():
            expected_sizes[info.filename] = info.file_size

    with tempfile.TemporaryDirectory() as cwd:
        # Phase 1: Extract all images from IPSW
        extracted = {}
        for name, path in reader.images.items():
            try:
                subprocess.check_call(["unzip", reader.ipsw, path], cwd=cwd)
            except FileNotFoundError:
                print("error: unzip not found", file=sys.stderr)
                sys.exit(1)
            except subprocess.CalledProcessError as e:
                print(f"error: unable to extract {path} from {reader.ipsw}", file=sys.stderr)
                sys.exit(e.returncode or 1)

            dmg = Path(cwd) / path
            actual_size = dmg.stat().st_size
            expected_size = expected_sizes.get(path, 0)
            print(f"Extracted {path}: {actual_size} bytes (expected {expected_size})", file=sys.stderr)
            if actual_size != expected_size:
                print(f"error: file size mismatch for {path}: got {actual_size}, expected {expected_size}", file=sys.stderr)
                sys.exit(1)
            extracted[name] = (path, dmg)

        # Phase 2: Delete IPSW to free disk space
        ipsw_path = Path(ipsw)
        ipsw_size = ipsw_path.stat().st_size / (1024**3)
        ipsw_path.unlink()
        print(f"Deleted IPSW ({ipsw_size:.1f} GB freed)", file=sys.stderr)

        # Phase 3: Process each image one by one
        for name, (path, dmg) in extracted.items():
            prefix = filesystem_root(name)
            if prefix is None:
                print(f"warning: unknown image component {name!r}; skipping", file=sys.stderr)
                if dmg.exists():
                    dmg.unlink()
                continue

            dest = Path(cwd) / f"{reader.version}-{name}.dmg"

            if path.endswith(".dmg.aea"):
                with dmg.open("rb") as fp:
                    key = get_key(fp)

                b64key = base64.b64encode(key).decode()
                cmd = [
                        "aea",
                        "decrypt",
                        "-i",
                        str(dmg),
                        "-o",
                        dest,
                        "-key-value",
                        f"base64:{b64key}",
                    ]
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True)
                except FileNotFoundError:
                    print("warning: aea not found; skipping encrypted AEA image", file=sys.stderr)
                    continue
                if result.returncode != 0:
                    print(f"error: aea decrypt failed for {path} (exit {result.returncode})", file=sys.stderr)
                    print(f"  command: {' '.join(str(a) for a in cmd)}", file=sys.stderr)
                    if result.stdout.strip():
                        print(f"  stdout: {result.stdout.strip()}", file=sys.stderr)
                    if result.stderr.strip():
                        print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
                    sys.exit(result.returncode or 1)
                dmg.unlink()

            elif image_backend.probe(str(dmg)).encrypted is True:
                device, *_ = reader.devices
                page_name = get_page_name(device, reader.build)
                content = fetch_page(page_name)
                (key,) = content["rootfs"]["key"]
                vfdecrypt_cmd = ["vfdecrypt", "-k", key, "-i", str(dmg), "-o", dest]
                try:
                    vf_result = subprocess.run(vfdecrypt_cmd, capture_output=True, text=True)
                except FileNotFoundError:
                    print("warning: vfdecrypt not found; skipping encrypted DMG image", file=sys.stderr)
                    continue
                if vf_result.returncode != 0:
                    print(f"error: vfdecrypt failed for {path} (exit {vf_result.returncode}); aborting", file=sys.stderr)
                    print(f"  command: {' '.join(vfdecrypt_cmd)}", file=sys.stderr)
                    if vf_result.stdout.strip():
                        print(f"  stdout: {vf_result.stdout.strip()}", file=sys.stderr)
                    if vf_result.stderr.strip():
                        print(f"  stderr: {vf_result.stderr.strip()}", file=sys.stderr)
                    sys.exit(vf_result.returncode or 1)
                dmg.unlink()

            else:
                shutil.move(dmg, dest)

            try:
                with image_backend.open(str(dest)) as root:
                    visitor = FileSystemVisitor(predicate=is_macho)
                    for path in visitor.visit(Path(root)):
                        relative = path.resolve().relative_to(root)
                        absolute = f"{prefix}{relative}"
                        xml = entitlements(str(path))
                        writer.insert(absolute, xml)
            except ImageBackendError:
                pass
            finally:
                # Clean up decrypted DMG immediately to save disk space
                if dest.exists():
                    dest.unlink()
                    print(f"Cleaned up {dest.name}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="create sqlite entitlements db from ipsw"
    )
    parser.add_argument("ipsws", type=str, nargs="+", help="Path to the .ipsw file(s)")
    parser.add_argument(
        "-o", "--output", type=str, default=".", help="Database output directory"
    )
    parser.add_argument("-m", "--merge", action="store_true", help="merge to one unified sqlite database")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    for ipsw in args.ipsws:
        build_database(ipsw, output, args.merge)


if __name__ == "__main__":
    main()
