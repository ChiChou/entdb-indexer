import json
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from stages.discover import fetch_ios_firmwares, fetch_mac_firmwares, find_missing
from cli import export_xml, _update_list_json


def prune_old_patches(data_repo: Path, group: str):
    group_dir = data_repo / group
    if not group_dir.exists():
        return

    entries = []
    for d in group_dir.iterdir():
        if not d.is_dir():
            continue
        meta = d / "meta.json"
        if not meta.exists():
            continue
        with meta.open() as fp:
            info = json.load(fp)
        segments = info["version"].split(".")
        if len(segments) < 2:
            continue
        numbers = list(map(int, segments))
        entries.append((numbers, info["version"], info["build"], d))

    groups = defaultdict(list)
    for numbers, version, build, d in entries:
        key = f"{numbers[0]}.{numbers[1]}"
        groups[key].append((numbers, version, build, d))

    removed = []
    for key, group in groups.items():
        group.sort(key=lambda x: x[0])
        for _, version, build, d in group[:-1]:
            shutil.rmtree(d)
            removed.append((version, build))

    if removed:
        _update_list_json(group_dir, [])
        for version, build in removed:
            print(f"Removed old {group} {version}_{build}")


def main():
    data_repo = Path("entdb-data")

    for group, fetch_fn in [("iOS", fetch_ios_firmwares), ("mac", fetch_mac_firmwares)]:
        prune_old_patches(data_repo, group)

        firmwares = fetch_fn(Path("cache"))
        missing = find_missing(firmwares, data_repo, group)

        if not missing:
            print(f"No new {group} versions")
            continue

        print(f"Found {len(missing)} new {group} version(s):")
        for fw in missing:
            print(f"  {fw['version']}_{fw['build']}")

        for fw in missing:
            version = fw["version"]
            build = fw["build"]
            url = fw["url"]
            tag = f"{version}_{build}"

            print(f"Processing {group} {tag}...")

            with tempfile.TemporaryDirectory() as tmpdir:
                ipsw_path = Path(tmpdir) / "firmware.ipsw"
                db_path = Path(tmpdir) / f"{tag}.db"

                subprocess.check_call(["curl", "-L", "-o", str(ipsw_path), url])
                subprocess.check_call([sys.executable, "ipsw-db.py", str(ipsw_path), "-o", tmpdir])
                export_xml(str(db_path), data_repo, group)

            print(f"Done: {group} {tag}")


if __name__ == "__main__":
    main()
