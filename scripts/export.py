#!/usr/bin/env python3
"""Export database to XML and prune old patches."""

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import export_xml, _update_list_json
from indexer.db import Reader


def validate_database(db_path: str):
    """Ensure database has actual content before exporting."""
    reader = Reader(db_path)
    os_entries = reader.all_os()
    if not os_entries:
        print(f"error: database {db_path} has no OS entries", file=sys.stderr)
        sys.exit(1)

    for os_info in os_entries:
        paths = reader.paths(os_info["build"])
        if not paths:
            print(f"error: database {db_path} has no binary entries for {os_info['build']}", file=sys.stderr)
            sys.exit(1)
        print(f"Validated {db_path}: {len(paths)} binaries for {os_info['version']}_{os_info['build']}", file=sys.stderr)


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
    for key, version_group in groups.items():
        version_group.sort(key=lambda x: x[0])
        for _, version, build, d in version_group[:-1]:
            shutil.rmtree(d)
            removed.append((version, build))

    if removed:
        _update_list_json(group_dir, [])
        for version, build in removed:
            print(f"Removed old {group} {version}_{build}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("db", help="Path to database file")
    parser.add_argument("group", help="Platform group (iOS or mac)")
    parser.add_argument("--data-repo", default="entdb-data", help="Data repo path")
    args = parser.parse_args()

    data_repo = Path(args.data_repo)
    validate_database(args.db)
    export_xml(args.db, data_repo, args.group)
    prune_old_patches(data_repo, args.group)
    print(f"Exported {args.db} to {data_repo}/{args.group}", file=sys.stderr)


if __name__ == "__main__":
    main()
