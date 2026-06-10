#!/usr/bin/env -S PYTHONPATH=. uv run --script

import argparse
import json
import sys
from pathlib import Path

from indexer.db import Reader, Writer


def _update_list_json(group_dir: Path, new_entries: list[dict]):
    list_path = group_dir / "list.json"
    existing = []
    if list_path.exists():
        with list_path.open() as fp:
            existing = json.load(fp)

    existing_builds = {e["build"] for e in existing}
    for entry in new_entries:
        if entry["build"] not in existing_builds:
            existing.append(entry)
            existing_builds.add(entry["build"])

    with list_path.open("w") as fp:
        json.dump(existing, fp, indent=2)
        fp.write("\n")


def export_xml(db_path: str, output: Path, group: str, beta: bool = False):
    reader = Reader(db_path)
    new_entries = []

    for os_info in reader.all_os():
        if beta:
            os_info["beta"] = True
        build = os_info["build"]
        version = os_info["version"]
        tag = f"{version}_{build}"

        version_dir = output / group / tag
        version_dir.mkdir(parents=True, exist_ok=True)

        bin_dir = version_dir / "bin"
        bin_dir.mkdir(exist_ok=True)

        paths = reader.paths(build)
        (version_dir / "paths.txt").write_text("\n".join(paths))

        with (version_dir / "meta.json").open("w") as fp:
            json.dump(os_info, fp)

        for path_str in paths:
            xml_path = bin_dir / path_str.lstrip("/")
            xml_path = xml_path.with_suffix(xml_path.suffix + ".xml")

            xml_path.parent.mkdir(parents=True, exist_ok=True)

        for b in reader.binaries(build):
            xml_path = bin_dir / b["path"].lstrip("/")
            xml_path = xml_path.with_suffix(xml_path.suffix + ".xml")
            xml_path.parent.mkdir(parents=True, exist_ok=True)
            xml_path.write_bytes(b["xml"])

        new_entries.append(os_info)
        print(f"exported {group}/{tag}", file=sys.stderr)

    group_dir = output / group
    group_dir.mkdir(parents=True, exist_ok=True)
    _update_list_json(group_dir, new_entries)


def main():
    parser = argparse.ArgumentParser(description="entdb indexer CLI")
    sub = parser.add_subparsers(dest="command")

    export = sub.add_parser("export-xml", help="Export XML files from SQLite database")
    export.add_argument("db", help="Path to SQLite database")
    export.add_argument("-o", "--output", default=".", help="Output directory")
    export.add_argument("-g", "--group", required=True, help="Group name (iOS, mac, osx)")
    export.add_argument("--beta", action="store_true", help="Tag entries as pre-release betas")

    args = parser.parse_args()

    if args.command == "export-xml":
        export_xml(args.db, Path(args.output), args.group, beta=args.beta)
    else:
        parser.print_help(sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
