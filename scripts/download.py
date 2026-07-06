#!/usr/bin/env python3
"""Download the first available firmware from the discovery queue.

Apple's CDN routinely 403s older or superseded builds. Instead of failing the
whole run on the first dead URL, walk the queue and take the first firmware
that downloads successfully. The selected build's metadata is written to
GITHUB_OUTPUT so the process/export steps know what was fetched; if the queue
is empty or every URL is unavailable, ``skip=true`` is emitted and downstream
steps are no-ops.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def emit_output(**outputs):
    """Append key=value pairs to GITHUB_OUTPUT (a no-op when unset locally)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a") as fp:
        for key, value in outputs.items():
            fp.write(f"{key}={value}\n")


def download(url: str, dest: Path) -> bool:
    result = subprocess.run(["curl", "--fail", "-L", "-o", str(dest), url])
    return result.returncode == 0


def main():
    queue_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("queue.json")
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("firmware.ipsw")

    queue = json.loads(queue_path.read_text())

    for fw in queue:
        tag = f"{fw['version']}_{fw['build']}"
        print(f"Downloading {fw['group']} {tag}", file=sys.stderr)
        if download(fw["url"], dest):
            print(f"Downloaded {tag} ({dest.stat().st_size} bytes)", file=sys.stderr)
            emit_output(
                skip="false",
                group=fw["group"],
                version=fw["version"],
                build=fw["build"],
                beta=str(fw.get("beta", False)).lower(),
            )
            return
        print(
            f"warning: {fw['group']} {tag} unavailable ({fw['url']}); trying next",
            file=sys.stderr,
        )
        dest.unlink(missing_ok=True)

    print("No downloadable firmware in queue; nothing to do", file=sys.stderr)
    emit_output(skip="true")


if __name__ == "__main__":
    main()
