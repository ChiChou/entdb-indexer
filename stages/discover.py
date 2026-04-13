"""Discover new firmware versions by comparing source APIs against existing data.

Supports iOS (ipsw.me) and macOS (ipsw.me for Apple Silicon, phoeninx.dev for Intel).
OSX is considered complete and is never checked for updates.
"""

import json
import urllib.request
from pathlib import Path
from collections import defaultdict
import os
import sys


def fetch_with_cache(url: str, cache_dir: Path, cache_name: str) -> bytes:
    cache_dir.mkdir(parents=True, exist_ok=True)
    local = cache_dir / cache_name
    if local.exists() and local.is_file():
        import time
        if local.stat().st_mtime + 86400 > time.time():
            with local.open("rb") as fp:
                return fp.read()

    buf = urllib.request.urlopen(url).read()
    with local.open("wb") as fp:
        fp.write(buf)
    return buf


def _min_ios_major(default=18) -> int:
    value = os.environ.get("ENTDB_MIN_IOS_MAJOR")
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("ENTDB_MIN_IOS_MAJOR must be an integer") from exc


def fetch_ios_firmwares(cache_dir: Path, min_major: int | None = None) -> list[dict]:
    if min_major is None:
        min_major = _min_ios_major()

    devices = json.loads(fetch_with_cache(
        "https://api.ipsw.me/v4/devices", cache_dir, "devices.json"
    ))
    models = [dev["identifier"] for dev in devices]
    phones = [m for m in models if m.startswith("iPhone")]

    unified = {}

    for model in phones:
        ipsw = json.loads(fetch_with_cache(
            f"https://api.ipsw.me/v4/device/{model}?type=ipsw",
            cache_dir,
            f"ipsw-{model}.json",
        ))

        for fw in ipsw["firmwares"]:
            version = fw["version"]
            major = int(version.split(".")[0])
            if major < min_major:
                continue

            unified[version] = {
                "url": fw["url"],
                "model": model,
                "version": fw["version"],
                "build": fw["buildid"],
                "releasedate": fw["releasedate"],
                "md5": fw["md5sum"],
                "sha1": fw["sha1sum"],
                "sha256": fw["sha256sum"],
            }

    groups = defaultdict(list)
    for version, fw in unified.items():
        segments = version.split(".")
        numbers = list(map(int, segments))
        major, minor, *_ = segments
        key = f"{major}.{minor}"
        groups[key].append((numbers, fw))

    latest = []
    for key, group in groups.items():
        group.sort(key=lambda x: x[0])
        latest.append(group[-1])

    latest.sort(key=lambda x: x[0])
    return [x[1] for x in latest]


def fetch_mac_firmwares(cache_dir: Path) -> list[dict]:
    devices = json.loads(fetch_with_cache(
        "https://api.ipsw.me/v4/devices", cache_dir, "devices.json"
    ))
    macs = [dev["identifier"] for dev in devices if dev["identifier"].startswith("Mac")]

    unified = {}

    for model in macs:
        try:
            ipsw = json.loads(fetch_with_cache(
                f"https://api.ipsw.me/v4/device/{model}?type=ipsw",
                cache_dir,
                f"ipsw-{model}.json",
            ))
        except Exception:
            continue

        for fw in ipsw.get("firmwares", []):
            version = fw["version"]
            build = fw["buildid"]
            key = f"{version}_{build}"
            if key not in unified:
                unified[key] = {
                    "url": fw["url"],
                    "model": model,
                    "version": version,
                    "build": build,
                    "releasedate": fw.get("releasedate", ""),
                }

    groups = defaultdict(list)
    for key, fw in unified.items():
        segments = fw["version"].split(".")
        numbers = list(map(int, segments))
        minor_key = f"{numbers[0]}.{numbers[1]}"
        groups[minor_key].append((numbers, fw))

    latest = []
    for key, group in groups.items():
        group.sort(key=lambda x: x[0])
        latest.append(group[-1])

    latest.sort(key=lambda x: x[0])
    return [x[1] for x in latest]


def find_missing(firmwares: list[dict], data_repo: Path, group: str) -> list[dict]:
    existing_builds = set()

    group_dir = data_repo / group
    if group_dir.exists():
        for d in group_dir.iterdir():
            if d.is_dir():
                meta = d / "meta.json"
                if meta.exists():
                    with meta.open() as fp:
                        existing_builds.add(json.load(fp)["build"])

    return [fw for fw in firmwares if fw["build"] not in existing_builds]


def split_into_batches(items: list[dict], batch_size: int) -> list[list[dict]]:
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


def fetch_firmware_list(cache_dir: Path | None = None) -> list[dict]:
    if cache_dir is None:
        cache_dir = Path("cache")
    return fetch_ios_firmwares(cache_dir)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Discover new firmware versions")
    parser.add_argument("--data-repo", required=True, help="Path to entdb-data checkout")
    parser.add_argument("--group", default="iOS", choices=["iOS", "mac"], help="Group to check")
    parser.add_argument("--batch-size", type=int, default=3, help="Items per batch")
    parser.add_argument(
        "--min-ios-major",
        type=int,
        default=_min_ios_major(),
        help="Minimum iOS major version to consider for discovery",
    )
    parser.add_argument("--cache-dir", default="cache", help="Cache directory")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)

    if args.group == "iOS":
        firmwares = fetch_ios_firmwares(cache_dir, min_major=args.min_ios_major)
    elif args.group == "mac":
        firmwares = fetch_mac_firmwares(cache_dir)
    else:
        return

    missing = find_missing(firmwares, Path(args.data_repo), args.group)

    if not missing:
        print("No new versions found", file=sys.stderr)
        return

    print(f"Found {len(missing)} new version(s):", file=sys.stderr)
    for fw in missing:
        print(f"  {fw['version']}_{fw['build']}", file=sys.stderr)

    batches = split_into_batches(missing, args.batch_size)
    print(json.dumps({"batches": batches, "total_missing": len(missing)}))


if __name__ == "__main__":
    main()
