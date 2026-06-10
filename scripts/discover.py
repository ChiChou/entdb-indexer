#!/usr/bin/env python3
"""Discover missing firmware versions and output the first one to process."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.discover import fetch_ios_firmwares, fetch_mac_firmwares, find_missing
from stages.betas import fetch_ios_betas, fetch_mac_betas


# Firmwares that are no longer available from Apple CDN (403 errors)
SKIP_BUILDS = {
    "24C2101",  # mac 15.2 - 403 from CDN
}


def _min_ios_major(default=18) -> int:
    value = os.environ.get("ENTDB_MIN_IOS_MAJOR")
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("ENTDB_MIN_IOS_MAJOR must be an integer") from exc


def main():
    data_repo = Path("entdb-data")
    min_ios_major = _min_ios_major()

    all_missing = []
    for group, fetch_fn in [("iOS", fetch_ios_firmwares), ("mac", fetch_mac_firmwares)]:
        if group == "iOS":
            firmwares = fetch_ios_firmwares(Path("cache"), min_major=min_ios_major)
        else:
            firmwares = fetch_fn(Path("cache"))

        missing = find_missing(firmwares, data_repo, group)
        for fw in missing:
            if fw["build"] in SKIP_BUILDS:
                print(f"Skipping {group} {fw['version']}_{fw['build']} (unavailable)", file=sys.stderr)
                continue
            all_missing.append((group, fw))

    # Betas (scraped from ipsw.dev) live in the same iOS/mac groups as stable
    # so the frontend lists and diffs them like any other build; they carry a
    # beta flag so pruning prefers the stable build of a version once it ships.
    # Appended after stable so stable work is always prioritised.
    for group, fetch_fn in [("iOS", fetch_ios_betas), ("mac", fetch_mac_betas)]:
        try:
            firmwares = fetch_fn(Path("cache"))
        except Exception as exc:
            print(f"Beta discovery failed for {group}: {exc}", file=sys.stderr)
            continue

        missing = find_missing(firmwares, data_repo, group)
        for fw in missing:
            if fw["build"] in SKIP_BUILDS:
                print(f"Skipping {group} {fw['version']}_{fw['build']} (unavailable)", file=sys.stderr)
                continue
            all_missing.append((group, fw))

    if not all_missing:
        print("No new versions", file=sys.stderr)
        return

    print(f"Found {len(all_missing)} missing version(s)", file=sys.stderr)

    # Output first one as JSON for next step
    group, fw = all_missing[0]
    result = {
        "group": group,
        "version": fw["version"],
        "build": fw["build"],
        "url": fw["url"],
        "beta": fw.get("beta", False),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
