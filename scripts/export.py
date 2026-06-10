#!/usr/bin/env python3
"""Export database to XML and prune old patches."""

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import export_xml
from indexer.db import Reader


def _prune_list_json(group_dir: Path, removed_builds: set):
    """Drop pruned builds from list.json so it stays in sync with disk."""
    list_path = group_dir / "list.json"
    if not list_path.exists():
        return
    with list_path.open() as fp:
        entries = json.load(fp)
    kept = [e for e in entries if e["build"] not in removed_builds]
    with list_path.open("w") as fp:
        json.dump(kept, fp, indent=2)
        fp.write("\n")


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
        entries.append((numbers, info["version"], info["build"], bool(info.get("beta")), d))

    groups = defaultdict(list)
    for numbers, version, build, beta, d in entries:
        key = f"{numbers[0]}.{numbers[1]}"
        groups[key].append((numbers, version, build, beta, d))

    removed_builds = set()
    removed = []
    for key, version_group in groups.items():
        # Within a major.minor bucket keep a single build. A stable build always
        # wins over a beta of the same version (so a beta is auto-pruned once its
        # GA ships); among same-status builds the latest version/build wins.
        stable = [e for e in version_group if not e[3]]
        keep_pool = stable if stable else version_group
        keep = max(keep_pool, key=lambda x: (x[0], x[2]))
        for numbers, version, build, beta, d in version_group:
            if d == keep[4]:
                continue
            shutil.rmtree(d)
            removed_builds.add(build)
            removed.append((version, build))

    if removed:
        _prune_list_json(group_dir, removed_builds)
        for version, build in removed:
            print(f"Removed old {group} {version}_{build}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("db", help="Path to database file")
    parser.add_argument("group", help="Platform group (iOS or mac)")
    parser.add_argument("--data-repo", default="entdb-data", help="Data repo path")
    parser.add_argument("--beta", action="store_true", help="Tag entries as pre-release betas")
    args = parser.parse_args()

    data_repo = Path(args.data_repo)
    validate_database(args.db)
    export_xml(args.db, data_repo, args.group, beta=args.beta)
    prune_old_patches(data_repo, args.group)
    print(f"Exported {args.db} to {data_repo}/{args.group}", file=sys.stderr)


if __name__ == "__main__":
    main()
