#!/usr/bin/env python3
"""Discover missing firmware versions and emit the full queue as JSON.

The queue is ordered by priority: stable builds first, betas last. The
download step walks this queue and takes the first firmware whose URL is still
served by Apple's CDN, so an expired build (which 403s) no longer fails the run
-- it is simply skipped in favour of the next entry.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.discover import (
    fetch_ios_firmwares,
    fetch_mac_firmwares,
    find_missing,
    _min_ios_major,
)
from stages.betas import fetch_ios_betas, fetch_mac_betas


def main():
    data_repo = Path("entdb-data")
    min_ios_major = _min_ios_major()

    queue = []
    for group, fetch_fn in [("iOS", fetch_ios_firmwares), ("mac", fetch_mac_firmwares)]:
        if group == "iOS":
            firmwares = fetch_ios_firmwares(Path("cache"), min_major=min_ios_major)
        else:
            firmwares = fetch_fn(Path("cache"))

        for fw in find_missing(firmwares, data_repo, group):
            queue.append({
                "group": group,
                "version": fw["version"],
                "build": fw["build"],
                "url": fw["url"],
                "beta": fw.get("beta", False),
            })

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

        for fw in find_missing(firmwares, data_repo, group):
            queue.append({
                "group": group,
                "version": fw["version"],
                "build": fw["build"],
                "url": fw["url"],
                "beta": fw.get("beta", False),
            })

    if queue:
        print(f"Found {len(queue)} missing version(s)", file=sys.stderr)
        for fw in queue:
            print(f"  {fw['group']} {fw['version']}_{fw['build']}", file=sys.stderr)
    else:
        print("No new versions", file=sys.stderr)

    # Emit the whole queue; download.py takes the first URL that works.
    print(json.dumps(queue))


if __name__ == "__main__":
    main()
