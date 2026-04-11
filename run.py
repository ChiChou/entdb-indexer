import json
import subprocess
import sys
import tempfile
from pathlib import Path

from stages.discover import fetch_ios_firmwares, fetch_mac_firmwares, find_missing
from cli import export_xml


def main():
    data_repo = Path("entdb-data")

    for group, fetch_fn in [("iOS", fetch_ios_firmwares), ("mac", fetch_mac_firmwares)]:
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
